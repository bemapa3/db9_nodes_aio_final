// PTS2GG Inpaint HUD — Photoshop UXP Plugin v0.5.0
// Extremely stripped down, robust automation client.

const photoshop = require('photoshop');
const uxp = require('uxp');

const fsLfs = uxp.storage.localFileSystem;
let formats = null;
try { formats = uxp.storage && uxp.storage.formats; } catch (e) {}
if (!formats) formats = { binary: 'binary' };

const { app, action, core } = photoshop;
const { batchPlay } = action;
const { executeAsModal } = core;

// ===== Constants / state =====
const VERSION = '0.5.0';
const BRIDGE = 'http://127.0.0.1:8765';

let bridgeOnline = false;
let providersOnline = [];
let lastBridgeError = null;
let activeJob = null;
let lastInpaintContext = null; // { squareBounds, dims, prompt, provider, mode, smartObjectLayerId, imageBase64 }
let bridgeAutostartAttempted = false;
let splashScreenActive = true;

let settings = {
  useStructuredPrompt: false,
  autoTranslateVN: true,
  selectionExpandMode: 'auto',
  selectionExpandPx: 96,
};

// ===== DOM helpers =====
const $ = (id) => document.getElementById(id);

function log(msg) {
  const el = $('progressLog');
  if (!el) return;
  const ts = new Date().toLocaleTimeString();
  el.textContent += `[${ts}] ${msg}\n`;
  el.scrollTop = el.scrollHeight;
  console.log('[PTS2GG]', msg);
}

function setDot(id, state) {
  const el = $(id);
  if (!el) return;
  el.className = 'db9-dot db9-dot-' + state; // off|on|busy|err
}

function syncGenerateAvailability() {
  const btn = $('btn-generate');
  if (!btn) return;
  const providerReady = bridgeOnline && providersOnline.includes('gemini');
  btn.disabled = !providerReady || !!activeJob;
  if (activeJob) btn.textContent = 'GENERATING...';
  else btn.textContent = 'GENERATE INPAINT';
  
  if (!bridgeOnline) {
    btn.title = 'Bridge offline - start bridge server';
  } else if (!providerReady) {
    btn.title = 'Gemini is not connected in Chrome extension';
  } else {
    btn.title = '';
  }
}

// ===== Splash Screen Manager =====
function updateSplashProgress(percent, statusText) {
  const bar = $('splash-bar');
  const text = $('splash-status');
  if (bar) bar.style.width = percent + '%';
  if (text) text.textContent = statusText;
}

function dismissSplashScreen() {
  if (!splashScreenActive) return;
  splashScreenActive = false;
  updateSplashProgress(100, 'TUNNEL ESTABLISHED! READY.');
  setTimeout(() => {
    const splash = $('db9-splash');
    if (splash) {
      splash.style.display = 'none';
    }
    const header = $('main-header');
    if (header) header.style.display = 'flex';
    const pane = $('main-pane');
    if (pane) pane.style.display = 'flex';
  }, 400);
}

// ===== Vietnamese detection + structured prompt =====
function detectVietnamese(text) {
  if (!text) return false;
  return /[ăâêôơưđĂÂÊÔƠƯĐàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵÀÁẢÃẠẰẮClarIFYẰẮẲẴẶẦẤẨẪẬÈÉẺẼẸỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌỒỐỔỖỘỜỚỞỠỢÙÚỦŨỤỪỨỬỮỰỲÝỶỸỴ]/.test(text);
}

function buildStructuredPrompt(state) {
  const p = (state.userPrompt || '').trim();
  return p || 'Seamlessly fill this area with matching background and lighting.';
}

function selectionWorkflowOptionsFromUI() {
  const mode = $('selectionExpandMode')?.value || settings.selectionExpandMode || 'auto';
  const pxRaw = Number($('selectionExpandPx')?.value ?? settings.selectionExpandPx ?? 96);
  const px = Number.isFinite(pxRaw) ? Math.max(0, Math.min(1024, Math.round(pxRaw))) : 96;
  settings.selectionExpandMode = mode;
  settings.selectionExpandPx = px;
  try { localStorage.setItem('pts2gg_settings', JSON.stringify(settings)); } catch (_) {}
  return { mode, px };
}

function getStateFromUI() {
  const userPrompt = $('promptInput')?.value || '';
  const modeElement = document.querySelector('input[name="mode"]:checked');
  const mode = modeElement ? modeElement.value : 'new';
  return { userPrompt, provider: 'gemini', mode };
}

// ===== Health polling =====
function xhrGet(url, timeoutMs = 4000) {
  return new Promise((resolve, reject) => {
    try {
      const xhr = new XMLHttpRequest();
      xhr.open('GET', url, true);
      xhr.timeout = timeoutMs;
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) resolve(xhr.responseText);
        else reject(new Error('HTTP ' + xhr.status));
      };
      xhr.onerror = () => reject(new Error('xhr network error'));
      xhr.ontimeout = () => reject(new Error('xhr timeout'));
      xhr.send();
    } catch (e) { reject(e); }
  });
}

function xhrPost(url, bodyStr, timeoutMs = 30000) {
  return new Promise((resolve, reject) => {
    try {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', url, true);
      xhr.timeout = timeoutMs;
      xhr.setRequestHeader('Content-Type', 'application/json');
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) resolve(xhr.responseText);
        else reject(new Error('HTTP ' + xhr.status + ': ' + xhr.responseText.slice(0,200)));
      };
      xhr.onerror = () => reject(new Error('xhr network error'));
      xhr.ontimeout = () => reject(new Error('xhr timeout'));
      xhr.send(bodyStr);
    } catch (e) { reject(e); }
  });
}

async function ensureBridgeServerStarted() {
  if (bridgeAutostartAttempted) return;
  bridgeAutostartAttempted = true;
  updateSplashProgress(45, 'STARTING LOCAL BRIDGE SERVER...');
  log('[SYSTEM] Bridge offline on startup. Attempting to auto-start bridge server...');
  try {
    const pluginFolder = await fsLfs.getPluginFolder();
    const nativePath = pluginFolder.nativePath;
    let batPath = '';
    if (nativePath.endsWith('uxp-plugin')) {
      batPath = nativePath.replace('uxp-plugin', 'bridge\\start-bridge.bat');
    } else if (nativePath.endsWith('uxp-plugin\\')) {
      batPath = nativePath.replace('uxp-plugin\\', 'bridge\\start-bridge.bat');
    } else {
      batPath = nativePath + '\\..\\bridge\\start-bridge.bat';
    }
    log(`[FILES] Resolved bat path: ${batPath}`);
    await uxp.shell.openPath(batPath);
    log('[SHELL] Launched start-bridge.bat. Please click "Allow" if Photoshop prompts you.');
    updateSplashProgress(75, 'AWAITING LOCAL BRIDGE SERVER ONLINE...');
  } catch (e) {
    log('[ERR] Failed to auto-start bridge: ' + e.message);
    updateSplashProgress(75, 'BRIDGE LAUNCH ERROR. RETRYING...');
  }
}

async function pollHealth() {
  try {
    const text = await xhrGet(BRIDGE + '/health', 3500);
    const data = JSON.parse(text);
    if (!bridgeOnline) log('[OK] bridge ONLINE v' + data.version + ' providers=[' + (data.providers || []).join(',') + ']');
    bridgeOnline = true;
    lastBridgeError = null;
    setDot('dot-bridge', 'on');
    providersOnline = data.providers || [];
    setDot('dot-gemini', providersOnline.includes('gemini') ? 'on' : 'off');
    setDot('dot-chatgpt', providersOnline.includes('chatgpt') ? 'on' : 'off');
    syncGenerateAvailability();
    
    // Dismiss loading overlay on active server confirmation
    if (splashScreenActive) {
      dismissSplashScreen();
    }
  } catch (e) {
    const errMsg = e.message || String(e);
    if (bridgeOnline !== false || lastBridgeError !== errMsg) {
      log('[WARN] bridge OFFLINE: ' + errMsg);
      lastBridgeError = errMsg;
    }
    bridgeOnline = false;
    setDot('dot-bridge', 'err');
    setDot('dot-gemini', 'off');
    setDot('dot-chatgpt', 'off');
    syncGenerateAvailability();
    
    if (splashScreenActive) {
      updateSplashProgress(30, 'BRIDGE OFFLINE. INITIALIZING...');
      ensureBridgeServerStarted();
    }
  }
}

function startHealthPolling() {
  pollHealth();
  setInterval(pollHealth, 2000);
}

// ===== Photoshop selection → Smart Object → base64 =====
function unitValue(v) {
  return typeof v === 'number' ? v : Number(v?._value ?? v) || 0;
}

function clampSquareBounds(left, top, right, bottom, docW, docH, options) {
  const selW = Math.max(1, right - left);
  const selH = Math.max(1, bottom - top);
  
  if (options?.mode === 'none') {
    const S = Math.min(Math.max(selW, selH), Math.min(docW, docH));
    const cx = (left + right) / 2;
    const cy = (top + bottom) / 2;
    let sLeft = Math.round(cx - S / 2);
    let sTop = Math.round(cy - S / 2);
    let sRight = sLeft + S;
    let sBottom = sTop + S;
    if (sLeft < 0) { sRight -= sLeft; sLeft = 0; }
    if (sTop < 0) { sBottom -= sTop; sTop = 0; }
    if (sRight > docW) { sLeft -= (sRight - docW); sRight = docW; }
    if (sBottom > docH) { sTop -= (sBottom - docH); sBottom = docH; }
    sLeft = Math.max(0, sLeft); sTop = Math.max(0, sTop);
    return { left: sLeft, top: sTop, right: sRight, bottom: sBottom, size: sRight - sLeft, pad: 0 };
  }

  const autoPad = Math.round(Math.max(selW, selH) * 0.18);
  const pad = options?.mode === 'manual' ? Number(options.px || 0) : Math.max(Number(options?.px || 0), autoPad);
  left -= pad; top -= pad; right += pad; bottom += pad;
  const expandedW = Math.max(1, right - left);
  const expandedH = Math.max(1, bottom - top);
  const S = Math.min(Math.max(expandedW, expandedH), Math.min(docW, docH));
  const cx = (left + right) / 2;
  const cy = (top + bottom) / 2;
  let sLeft = Math.round(cx - S / 2);
  let sTop = Math.round(cy - S / 2);
  let sRight = sLeft + S;
  let sBottom = sTop + S;
  if (sLeft < 0) { sRight -= sLeft; sLeft = 0; }
  if (sTop < 0) { sBottom -= sTop; sTop = 0; }
  if (sRight > docW) { sLeft -= (sRight - docW); sRight = docW; }
  if (sBottom > docH) { sTop -= (sBottom - docH); sBottom = docH; }
  sLeft = Math.max(0, sLeft); sTop = Math.max(0, sTop);
  return { left: sLeft, top: sTop, right: sRight, bottom: sBottom, size: sRight - sLeft, pad };
}

async function selectRectangle(bounds) {
  await batchPlay([{
    _obj: 'set',
    _target: [{ _ref: 'channel', _property: 'selection' }],
    to: { _obj: 'rectangle', top: { _unit: 'pixelsUnit', _value: bounds.top }, left: { _unit: 'pixelsUnit', _value: bounds.left }, bottom: { _unit: 'pixelsUnit', _value: bounds.bottom }, right: { _unit: 'pixelsUnit', _value: bounds.right } }
  }], { synchronousExecution: true });
}

async function prepareSelectionSmartObject(squareBounds, hasSelection) {
  try {
    const doc = app.activeDocument;
    const originalLayer = doc.activeLayers[0];
    if (!originalLayer) throw new Error('No active layer');
    const originalLayerId = originalLayer.id;

    let selectionLayerId = null;
    if (hasSelection) {
      await batchPlay([{ _obj: 'copyToLayer' }], { synchronousExecution: true });
      const selLayer = doc.activeLayers[0];
      if (selLayer) selectionLayerId = selLayer.id;
      await selectLayerById(originalLayerId);
    }

    await selectRectangle(squareBounds);
    await batchPlay([{ _obj: 'copyToLayer' }], { synchronousExecution: true });
    const contextLayer = doc.activeLayers[0];
    if (!contextLayer) throw new Error('Failed to create context layer');

    await batchPlay([{ _obj: 'newPlacedLayer' }], { synchronousExecution: true });
    const smartObjectLayer = doc.activeLayers[0];
    if (!smartObjectLayer) throw new Error('Failed to create Smart Object layer');
    if (smartObjectLayer) {
      smartObjectLayer.name = 'PTS2GG Inpaint Smart Object ' + new Date().toLocaleTimeString();
    }

    if (hasSelection && selectionLayerId) {
      try {
        await selectLayerById(selectionLayerId);
        await batchPlay([{
          _obj: 'set',
          _target: [{ _ref: 'channel', _property: 'selection' }],
          to: { _ref: 'channel', _enum: 'channel', _value: 'transparencyEnum' }
        }], { synchronousExecution: true });

        await selectLayerById(smartObjectLayer.id);

        try {
          await batchPlay([{
            _obj: 'make',
            new: { _class: 'channel' },
            at: { _ref: 'channel', _enum: 'channel', _value: 'mask' },
            using: { _enum: 'userMaskEnabled', _value: 'revealSelection' }
          }], { synchronousExecution: true });
        } catch (maskError) {
          log('  ⚠ smart object mask skipped: ' + maskError.message);
        }
      } finally {
        try {
          await batchPlay([{
            _obj: 'delete',
            _target: [{ _ref: 'layer', _id: selectionLayerId }]
          }], { synchronousExecution: true });
        } catch (cleanupError) {
          log('  ⚠ temp selection layer cleanup skipped: ' + cleanupError.message);
        }
      }
    }

    return smartObjectLayer ? smartObjectLayer.id : null;
  } catch (e) {
    log('  ⚠ smart object preparation skipped: ' + e.message);
    return null;
  }
}

function base64ToBytes(base64) {
  const bin = atob(base64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes;
}

async function writeTempPng(base64, prefix = 'pts2gg_result_') {
  const tmpFolder = await fsLfs.getTemporaryFolder();
  const outFile = await tmpFolder.createFile(prefix + Date.now() + '.png', { overwrite: true });
  const bytes = base64ToBytes(base64);
  await outFile.write(bytes.buffer, { format: formats.binary });
  return outFile;
}

async function exportSelectionAsPng(options = {}) {
  let base64 = null;
  let dims = null;
  let squareBounds = null;
  let smartObjectLayerId = null;
  await executeAsModal(async (ctx) => {
    const doc = app.activeDocument;
    if (!doc) throw new Error('No document open in Photoshop');

    let sel = null;
    try {
      const r = await batchPlay([{ _obj: 'get', _target: [{ _property: 'selection' }, { _ref: 'document', _enum: 'ordinal', _value: 'targetEnum' }] }], { synchronousExecution: true, modalBehavior: 'execute' });
      sel = r[0]?.selection;
    } catch (e) {}

    let left, top, right, bottom;
    if (sel) {
      left = unitValue(sel.left); top = unitValue(sel.top);
      right = unitValue(sel.right); bottom = unitValue(sel.bottom);
    } else {
      left = 0; top = 0; right = unitValue(doc.width); bottom = unitValue(doc.height);
    }
    const selW = right - left;
    const selH = bottom - top;
    squareBounds = clampSquareBounds(left, top, right, bottom, unitValue(doc.width), unitValue(doc.height), options);
    dims = { w: squareBounds.size, h: squareBounds.size, originalW: selW, originalH: selH, pad: squareBounds.pad };
    log(`[BOUNDS] selection ${Math.round(selW)}x${Math.round(selH)} +${squareBounds.pad}px -> square ${dims.w}x${dims.h} at (${squareBounds.left},${squareBounds.top})`);

    smartObjectLayerId = await prepareSelectionSmartObject(squareBounds, sel !== null);

    await selectRectangle(squareBounds);
    await batchPlay([{ _obj: 'copyMerged' }], { synchronousExecution: true });

    const tmpFolder = await fsLfs.getTemporaryFolder();
    const outFile = await tmpFolder.createFile('pts2gg_sel_' + Date.now() + '.png', { overwrite: true });

    const newDoc = await app.createDocument({
      width: squareBounds.size, height: squareBounds.size,
      resolution: doc.resolution, fill: 'transparent', mode: 'RGBColorMode'
    });
    await batchPlay([{ _obj: 'paste' }], { synchronousExecution: true });
    await batchPlay([{ _obj: 'flattenImage' }], { synchronousExecution: true });
    await newDoc.saveAs.png(outFile);
    await newDoc.closeWithoutSaving();

    const buf = await outFile.read({ format: formats.binary });
    const bytes = new Uint8Array(buf);

    const view = new DataView(bytes.buffer);
    const pngW = view.getUint32(16, false);
    const pngH = view.getUint32(20, false);
    if (pngW !== dims.w || pngH !== dims.h) {
      throw new Error(`Export dimension mismatch: got ${pngW}x${pngH}, expected ${dims.w}x${dims.h}. Aborting.`);
    }
    log(`[OK] export validated ${pngW}x${pngH} ${Math.round(bytes.byteLength/1024)}KB smartObjectId=${smartObjectLayerId}`);
    
    let bin = '';
    for (let i = 0; i < bytes.byteLength; i++) bin += String.fromCharCode(bytes[i]);
    base64 = btoa(bin);
  }, { commandName: 'PTS2GG prepare selection Smart Object + export 1:1' });
  return { base64, dims, squareBounds, smartObjectLayerId };
}

async function selectLayerById(layerId) {
  if (!layerId) return false;
  try {
    await batchPlay([{
      _obj: 'select',
      _target: [{ _ref: 'layer', _id: layerId }],
      makeVisible: false
    }], { synchronousExecution: true });
    return true;
  } catch (e) {
    log('  ⚠ select smart object skipped: ' + e.message);
    return false;
  }
}

async function replaceSmartObjectContents(base64, label, context = lastInpaintContext, variantIndex = -1) {
  if (!context?.smartObjectLayerId) return false;
  const outFile = await writeTempPng(base64, 'pts2gg_smart_replace_');
  const token = await fsLfs.createSessionToken(outFile);
  
  await executeAsModal(async () => {
    const selected = await selectLayerById(context.smartObjectLayerId);
    if (!selected) throw new Error('Target Smart Object layer is not available');
    
    await batchPlay([{ _obj: 'placedLayerEditContents' }], { synchronousExecution: true });
    const soDoc = app.activeDocument;
    
    await batchPlay([{
      _obj: 'placeEvent',
      null: { _path: token, _kind: 'local' },
      freeTransformCenterState: { _enum: 'quadCenterState', _value: 'QCSAverage' }
    }], { synchronousExecution: true });
    
    const layer = soDoc.activeLayers[0];
    if (layer) {
      if (variantIndex >= 0) {
        layer.name = `PTS2GG Variant ${variantIndex + 1}`;
      } else {
        layer.name = 'PTS2GG ' + (label || 'Gemini') + ' Result ' + new Date().toLocaleTimeString();
      }
    }
    
    try {
      await batchPlay([{ _obj: 'save', _target: [{ _ref: 'document', _enum: 'ordinal', _value: 'targetEnum' }] }], { synchronousExecution: true });
    } catch (saveErr) {
      log('  [WARN] Save with layers failed (legacy format). Flattening...');
      await batchPlay([{ _obj: 'flattenImage' }], { synchronousExecution: true });
      await batchPlay([{ _obj: 'save', _target: [{ _ref: 'document', _enum: 'ordinal', _value: 'targetEnum' }] }], { synchronousExecution: true });
    }
    await soDoc.close();
  }, { commandName: 'PTS2GG Smart Object replace content' });
  
  log('[SUCCESS] updated Smart Object with auto-scaling' + (label ? ' (' + label + ')' : ''));
  return true;
}

async function applyResultToPS(base64, label, placementBounds, context = lastInpaintContext, variantIndex = -1) {
  try {
    if (await replaceSmartObjectContents(base64, label, context, variantIndex)) return;
  } catch (e) {
    log('  [WARN] smart object replace failed, placing result layer: ' + e.message);
  }

  await executeAsModal(async (ctx) => {
    const outFile = await writeTempPng(base64);
    const token = await fsLfs.createSessionToken(outFile);
    await batchPlay([{
      _obj: 'placeEvent',
      null: { _path: token, _kind: 'local' },
      freeTransformCenterState: { _enum: 'quadCenterState', _value: 'QCSAverage' }
    }], { synchronousExecution: true });
    log('[SUCCESS] placed new layer' + (label ? ' (' + label + ')' : '') + (placementBounds ? ` at ${placementBounds.left},${placementBounds.top} size ${placementBounds.size}` : ''));

    if (placementBounds) {
      try {
        const doc = app.activeDocument;
        const layer = doc.activeLayers[0];
        if (layer) {
          const docCx = unitValue(doc.width) / 2;
          const docCy = unitValue(doc.height) / 2;
          const targetCx = (placementBounds.left + placementBounds.right) / 2;
          const targetCy = (placementBounds.top + placementBounds.bottom) / 2;
          const dx = targetCx - docCx;
          const dy = targetCy - docCy;
          if (Math.abs(dx) > 0.5 || Math.abs(dy) > 0.5) {
            await batchPlay([{
              _obj: 'move',
              _target: [{ _ref: 'layer', _enum: 'ordinal', _value: 'targetEnum' }],
              to: { _obj: 'offset', horizontal: { _unit: 'pixelsUnit', _value: dx }, vertical: { _unit: 'pixelsUnit', _value: dy } }
            }], { synchronousExecution: true });
            log(`  ↪ moved layer to selection center (Δ ${Math.round(dx)},${Math.round(dy)})`);
          }
          layer.name = 'PTS2GG ' + (label || 'gen') + ' ' + new Date().toLocaleTimeString();
        }
      } catch (e) { log('  ⚠ post-place adjust skipped: ' + e.message); }
    }
  }, { commandName: 'PTS2GG apply result as new layer' });
}

let generatedVariants = [null, null, null];

async function runGenerate() {
  if (activeJob) { log('[WARN] job in progress, please wait'); return; }
  if (!bridgeOnline) { log('[ERR] bridge offline'); return; }
  activeJob = 'local-preflight';
  syncGenerateAvailability();

  const state = getStateFromUI();
  const finalPrompt = buildStructuredPrompt(state);
  log(`[RUN] generate 3 variants provider=${state.provider} mode=${state.mode}`);
  console.log('[PTS2GG] final prompt:\n' + finalPrompt);

  $('progressLog').textContent = '';
  $('progressSteps').innerHTML = '<div class="db9-step active">Exporting selection…</div>';

  try {
    const { base64, dims, squareBounds, smartObjectLayerId } = await exportSelectionAsPng(selectionWorkflowOptionsFromUI());
    window.__db9_lastSquareBounds = squareBounds;
    lastInpaintContext = {
      squareBounds,
      dims,
      prompt: finalPrompt,
      provider: state.provider,
      mode: state.mode,
      smartObjectLayerId,
      imageBase64: base64
    };
    const btnRegen = $('btn-regenerate');
    if (btnRegen) btnRegen.disabled = false;
    log(`[OK] exported ${dims?.w}x${dims?.h} (${Math.round((base64?.length || 0) * 0.75 / 1024)} KB)`);

    // Reset thumbnails and UI state
    generatedVariants = [null, null, null];
    const body = {
      imageBase64: base64,
      prompt: finalPrompt,
      provider: state.provider,
      mode: state.mode,
    };
    
    $('progressSteps').innerHTML += `<div class="db9-step active">Posting job to bridge…</div>`;
    const respText = await xhrPost(BRIDGE + '/generate', JSON.stringify(body), 20000);
    const data = JSON.parse(respText);
    log(`[OK] generate job ` + (data.jobId || data.parentId) + ' queued');

    const resultBase64 = await runSinglePollingWithoutApply(data.jobId, state.provider, finalPrompt, 1);
    
    if (resultBase64) {
      generatedVariants[0] = resultBase64;
      // Auto-apply as layer into the Smart Object
      await applyResultToPS(resultBase64, state.provider, window.__db9_lastSquareBounds, lastInpaintContext, 0);
      applyVariant(0);
    }
    
    $('progressSteps').innerHTML += '<div class="db9-step done">Generation complete.</div>';

  } catch (e) {
    log('[ERR] ' + e.message);
    $('progressSteps').innerHTML += '<div class="db9-step error">[ERR] ' + e.message + '</div>';
  } finally {
    activeJob = null;
    syncGenerateAvailability();
  }
}

async function runSinglePollingWithoutApply(jobId, provider, prompt, variantNum) {
  activeJob = jobId;
  $('progressSteps').innerHTML += `<div class="db9-step active">Generating variant ${variantNum}…</div>`;
  for (let i = 0; i < 240; i++) { // up to ~8 min
    await new Promise(r => setTimeout(r, 2000));
    let j;
    try {
      const txt = await xhrGet(BRIDGE + '/job/' + jobId, 5000);
      j = JSON.parse(txt);
    } catch (e) { continue; }
    const resultBase64 = j.resultBase64 || j.imageBase64 || null;
    if (j.status === 'done' && resultBase64) {
      log(`[OK] variant ${variantNum} received`);
      $('progressSteps').innerHTML += `<div class="db9-step done">Variant ${variantNum} Done</div>`;
      return resultBase64;
    }
    if (j.status === 'error') throw new Error(j.error || 'job error');
  }
  throw new Error('timeout');
}

async function applyVariant(index) {
  if (!generatedVariants[index]) return;
  for (let i = 1; i <= 3; i++) {
    const thumb = $('thumb-' + i);
    if (thumb) {
      if (i - 1 === index) thumb.classList.add('active');
      else thumb.classList.remove('active');
    }
  }
  
  if (!lastInpaintContext?.smartObjectLayerId) return;
  
  log(`[SYSTEM] toggling variant ${index+1} visibility...`);
  
  try {
    await executeAsModal(async () => {
      const selected = await selectLayerById(lastInpaintContext.smartObjectLayerId);
      if (!selected) return;
      
      await batchPlay([{ _obj: 'placedLayerEditContents' }], { synchronousExecution: true });
      const soDoc = app.activeDocument;
      
      const variantLayers = soDoc.layers.filter(l => l.name.startsWith('PTS2GG Variant '));
      
      for (let i = 0; i < variantLayers.length; i++) {
        const expectedName = `PTS2GG Variant ${index + 1}`;
        variantLayers[i].visible = (variantLayers[i].name === expectedName);
      }
      
      try {
        await batchPlay([{ _obj: 'save', _target: [{ _ref: 'document', _enum: 'ordinal', _value: 'targetEnum' }] }], { synchronousExecution: true });
      } catch (saveErr) {
        // Ignore save errs during silent toggle
      }
      await soDoc.close();
    }, { commandName: 'PTS2GG Toggle Variant', interactive: false });
  } catch (e) {
    log('[ERR] ' + e.message);
  }
}

async function runRegenerate() {
  if (activeJob) { log('[WARN] job in progress, please wait'); return; }
  if (!bridgeOnline) { log('[ERR] bridge offline'); return; }
  if (!lastInpaintContext || !lastInpaintContext.smartObjectLayerId || !lastInpaintContext.imageBase64) {
    log('[ERR] No active Smart Object context to regenerate');
    return;
  }

  activeJob = 'local-preflight';
  syncGenerateAvailability();

  const state = getStateFromUI();
  const finalPrompt = buildStructuredPrompt(state);
  log(`[RUN] regenerate provider=${state.provider} mode=${state.mode} smartObjectId=${lastInpaintContext.smartObjectLayerId}`);

  $('progressLog').textContent = '';
  $('progressSteps').innerHTML = '<div class="db9-step active">Posting regenerate to bridge…</div>';

  try {
    // Reset thumbnails
    generatedVariants = [null, null, null];
    for (let i = 1; i <= 3; i++) {
      const thumb = $('thumb-' + i);
      if (thumb) {
        thumb.style.backgroundImage = 'none';
        thumb.textContent = '...';
        thumb.classList.remove('active');
      }
    }

    const body = {
      imageBase64: lastInpaintContext.imageBase64,
      prompt: finalPrompt,
      provider: state.provider,
      mode: state.mode,
    };
    
    for (let variantIndex = 0; variantIndex < 3; variantIndex++) {
      $('progressSteps').innerHTML += `<div class="db9-step active">Posting variant ${variantIndex+1}/3 to bridge…</div>`;
      
      const isRetry = variantIndex > 0;
      const payload = {
        ...body,
        imageBase64: isRetry ? null : lastInpaintContext.imageBase64,
        mode: isRetry ? 'retry' : state.mode
      };
      
      const respText = await xhrPost(BRIDGE + '/generate', JSON.stringify(payload), 20000);
      const data = JSON.parse(respText);
      log(`[OK] variant ${variantIndex+1} job ` + (data.jobId || data.parentId) + (isRetry ? ' (retry)' : '') + ' queued');

      const resultBase64 = await runSinglePollingWithoutApply(data.jobId, state.provider, finalPrompt, variantIndex+1);
      
      if (resultBase64) {
        generatedVariants[variantIndex] = resultBase64;
        const thumb = $('thumb-' + (variantIndex + 1));
        if (thumb) {
          thumb.style.backgroundImage = `url(data:image/png;base64,${resultBase64})`;
          thumb.textContent = '';
        }
        // Auto-apply all variants as layers into the Smart Object
        await applyResultToPS(resultBase64, state.provider, window.__db9_lastSquareBounds, lastInpaintContext, variantIndex);
        applyVariant(variantIndex);
      }
    }
    
    $('progressSteps').innerHTML += '<div class="db9-step done">Regeneration complete.</div>';
    lastInpaintContext.prompt = finalPrompt;

  } catch (e) {
    log('[ERR] ' + e.message);
    $('progressSteps').innerHTML += '<div class="db9-step error">[ERR] ' + e.message + '</div>';
  } finally {
    activeJob = null;
    syncGenerateAvailability();
  }
}

// ===== Wire up DOM events =====
function wire() {
  const btnRegen = $('btn-regenerate');
  if (btnRegen) {
    btnRegen.onclick = () => runRegenerate().catch(e => log('[ERR] ' + e.message));
  }

  $('btn-generate').onclick = () => runGenerate().catch(e => log('[ERR] ' + e.message));
  
  // Reconnect button
  const recBtn = $('btn-reconnect');
  if (recBtn) {
    recBtn.onclick = () => { log('[SYSTEM] forcing reconnect...'); pollHealth(); };
  }

  // Thumbnails
  for (let i = 1; i <= 3; i++) {
    const thumb = $('thumb-' + i);
    if (thumb) {
      thumb.onclick = () => applyVariant(i - 1);
    }
  }

  // Server Control
  const btnStart = $('btn-start-server');
  if (btnStart) {
    btnStart.onclick = async () => {
      try {
        log('[SYSTEM] Starting bridge server...');
        const lfs = require("uxp").storage.localFileSystem;
        const pluginFolder = await lfs.getPluginFolder();
        const entry = await pluginFolder.getEntry('start_server.bat');
        const { shell } = require("uxp");
        await shell.openPath(entry);
        log('[OK] Start request sent. Please allow the popup if Photoshop asks.');
      } catch (e) {
        log('[ERR] Start Server failed: ' + (e.message || e));
      }
    };
  }

  const btnStop = $('btn-stop-server');
  if (btnStop) {
    btnStop.onclick = async () => {
      try {
        log('[SYSTEM] Shutting down bridge server...');
        await fetch(BRIDGE + '/shutdown');
        log('[OK] Shutdown signal sent.');
      } catch (e) {
        log('[ERR] Server might already be off: ' + e.message);
      }
    };
  }
  
  const btnRestart = $('btn-restart-server');
  if (btnRestart) {
    btnRestart.onclick = async () => {
      if (btnStop) await btnStop.onclick();
      setTimeout(() => {
        if (btnStart) btnStart.onclick();
      }, 1500);
    };
  }

  // Dynamic selection bounds UI controls
  const modeSel = $('selectionExpandMode');
  const marginInput = $('selectionExpandPx');
  if (modeSel && marginInput) {
    const updateMarginState = () => {
      if (modeSel.value === 'manual') {
        marginInput.removeAttribute('disabled');
        marginInput.style.opacity = '1.0';
      } else {
        marginInput.setAttribute('disabled', 'true');
        marginInput.style.opacity = '0.35';
      }
    };
    modeSel.onchange = () => {
      updateMarginState();
      selectionWorkflowOptionsFromUI();
    };
    marginInput.onchange = () => {
      selectionWorkflowOptionsFromUI();
    };
    
    // Set initial values from saved settings
    if (settings.selectionExpandMode) modeSel.value = settings.selectionExpandMode;
    if (settings.selectionExpandPx !== undefined) marginInput.value = settings.selectionExpandPx;
    
    updateMarginState();
  }

  // Dynamic character count
  const promptInput = $('promptInput');
  const promptCounter = $('prompt-counter');
  if (promptInput && promptCounter) {
    const updateCounter = () => {
      const val = promptInput.value || '';
      const len = val.length;
      promptCounter.textContent = `${len} / 250`;
    };
    promptInput.oninput = updateCounter;
    updateCounter();
  }
}

// ===== Init =====
async function init() {
  log('[SYSTEM] PTS2GG Inpaint HUD v' + VERSION + ' starting…');
  
  // Simulated initial loading animations for splash loading screen
  updateSplashProgress(15, 'INITIALIZING ADOBE UXP ENGINE...');
  setTimeout(() => {
    if (splashScreenActive) updateSplashProgress(35, 'CONNECTING SECURE TUNNEL...');
  }, 350);
  
  // Fallback: dismiss splash after 3 seconds so UI is never permanently blocked
  setTimeout(() => {
    if (splashScreenActive) {
      log('[SYSTEM] Splash timeout reached, revealing UI...');
      dismissSplashScreen();
    }
  }, 3000);
  
  try {
    const s = localStorage.getItem('pts2gg_settings');
    if (s) {
      const saved = JSON.parse(s);
      settings = { ...settings, ...saved };
    }
  } catch (e) {}
  
  wire();
  startHealthPolling();
  log('[SYSTEM] core ready');
}

init().catch(e => log('[ERR] init: ' + e.message));
