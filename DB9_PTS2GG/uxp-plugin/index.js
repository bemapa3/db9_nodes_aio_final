// DB9 Multi-Provider — Photoshop UXP Plugin v0.4.7.5
// All preset/negative state lives in the plugin. Bridge is a dumb pipe.

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
const VERSION = '0.4.7.5';
const BRIDGE = 'http://127.0.0.1:8765';
const PRESET_MAX = 6;

let presetLib = null;       // {version, categories: {Cat: [{id,...}]}}
let negativeLib = null;
let selectedPositive = new Set();
let selectedNegative = new Set();
let history = [];           // {jobId, prompt, thumb, ts, provider}
let savedCombos = [];       // {id, name, positive[], negative[], userPrompt, userNegative, provider}
let providersOnline = [];
let bridgeOnline = false;
let lastBridgeError = null;
let activeJob = null;
let refImage = null; // { base64, mime, description }
let lastInpaintContext = null; // { squareBounds, dims, prompt, provider, mode, smartObjectLayerId }
let presetSearchQ = '';
let negativeSearchQ = '';
let dualState = null;       // {parentId, gemini:{status,base64}, chatgpt:{status,base64}}
let settings = {
  useStructuredPrompt: true,
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
  console.log('[DB9]', msg);
}

function setDot(id, state) {
  const el = $(id);
  if (!el) return;
  el.className = 'db9-dot db9-dot-' + state; // off|on|busy|err
}

function sanitizeUiCopy() {
  const setText = (id, text) => {
    const el = $(id);
    if (el) el.textContent = text;
  };
  const setPlaceholder = (id, text) => {
    const el = $(id);
    if (el) el.placeholder = text;
  };
  const setSectionTitle = (sectionId, text) => {
    const el = document.querySelector(`#${sectionId} .db9-section-title`);
    if (el) el.textContent = text;
  };

  setText('db9-title', 'DB9 Multi-Provider');
  setText('btn-reconnect', 'Reconnect');
  setText('btn-settings', 'Settings');
  setPlaceholder('promptInput', 'Describe the edit or render idea. Vietnamese is still accepted and translated automatically.');
  setPlaceholder('negativeSearch', 'Filter negatives...');
  setPlaceholder('presetSearch', 'Search...');
  setText('btn-clear', 'Clear all');
  setText('btn-save-custom', 'Save combo...');
  setText('btn-export', 'Export JSON');
  setText('btn-import', 'Import JSON');
  setText('btn-ref-upload', 'Upload reference');
  setText('btn-ref-describe', 'Describe via Gemini');
  setText('btn-ref-clear', 'Clear');
  setText('btn-ref-save-preset', 'Save as preset');
  setText('btn-open-gemini', 'Open Gemini');
  setText('btn-open-chatgpt', 'Open ChatGPT');
  setText('dual-cancel', 'Cancel');
  setText('dual-use-gemini', 'Use Gemini');
  setText('dual-use-chatgpt', 'Use ChatGPT');

  setSectionTitle('sec-selection', 'Selection');
  setSectionTitle('sec-prompt', 'Prompt');
  setSectionTitle('sec-negative', 'Negative');
  setSectionTitle('sec-presets', 'Presets');
  setSectionTitle('sec-custom', 'Saved combos');
  setSectionTitle('sec-mode', 'Mode');
  setSectionTitle('sec-provider', 'Provider');
  setSectionTitle('sec-progress', 'Progress');
  setSectionTitle('sec-history', 'History');
  const refTitle = document.querySelector('#pane-reference .db9-section-title');
  if (refTitle) refTitle.textContent = 'Reference image';

  const refHelp = document.querySelector('#pane-reference .small');
  if (refHelp) refHelp.textContent = 'Upload a reference image, let Gemini describe it, then inject that description into the prompt.';

  const savedEmpty = document.querySelector('#customList .small');
  if (savedEmpty) savedEmpty.textContent = 'No combos saved yet - pick presets/negatives then click "Save combo...".';

  const dualHeader = document.querySelector('.db9-modal-header');
  if (dualHeader) dualHeader.textContent = 'Compare results and choose one to apply';
  const dualTitles = document.querySelectorAll('.db9-modal-cell h4');
  if (dualTitles[0]) dualTitles[0].textContent = 'Gemini';
  if (dualTitles[1]) dualTitles[1].textContent = 'ChatGPT';

  const modeLabels = document.querySelectorAll('input[name="mode"]');
  modeLabels.forEach((input) => {
    const label = input.closest('label');
    if (!label) return;
    const text = input.value === 'new' ? 'New' : input.value === 'regen' ? 'Regen' : 'Refine';
    label.innerHTML = '';
    label.appendChild(input);
    label.appendChild(document.createTextNode(' ' + text));
  });

  const providerLabels = document.querySelectorAll('input[name="provider"]');
  providerLabels.forEach((input) => {
    const label = input.closest('label');
    if (!label) return;
    const text = input.value === 'gemini' ? 'Gemini' : input.value === 'chatgpt' ? 'ChatGPT' : 'Both (compare)';
    label.innerHTML = '';
    label.appendChild(input);
    label.appendChild(document.createTextNode(' ' + text));
  });

  document.querySelectorAll('.db9-tab').forEach((tab) => {
    const map = {
      'pane-main': 'Main',
      'pane-prompt': 'Prompt',
      'pane-presets': 'Style',
      'pane-negative': 'Negative',
      'pane-reference': 'Reference',
      'pane-saved': 'Combos',
      'pane-log': 'Logs',
    };
    tab.textContent = map[tab.dataset.tab] || 'Tab';
  });
}

function selectedProviderFromUI() {
  return document.querySelector('input[name="provider"]:checked')?.value || 'gemini';
}

function providerReadyForSelection() {
  const selected = selectedProviderFromUI();
  if (!bridgeOnline) return false;
  if (selected === 'both') {
    return providersOnline.includes('gemini') && providersOnline.includes('chatgpt');
  }
  return providersOnline.includes(selected);
}

function syncGenerateAvailability() {
  const btn = $('btn-generate');
  if (!btn) return;
  const providerReady = providerReadyForSelection();
  btn.disabled = !providerReady || !!activeJob;
  if (activeJob) btn.textContent = 'GENERATING...';
  else btn.textContent = 'GENERATE';
  if (!bridgeOnline) {
    btn.title = 'Bridge offline - start bridge server and open provider tab';
  } else if (!providerReady) {
    btn.title = 'Selected provider is not connected in Chrome';
  } else {
    btn.title = '';
  }
}

// ===== Local FS read for presets/negatives =====
// UXP quirk: fetch() on relative paths doesn't work in all PS versions.
// We try 4 strategies in order: plugin://, fetch(name), fs read with utf8 format, fs read with plain string.
async function loadJsonFile(name) {
  const attempts = [];

  // A: fetch with plugin: URL
  try {
    const r = await fetch('plugin:/' + name);
    if (r && r.ok) { const t = await r.text(); return JSON.parse(t); }
  } catch (e) { attempts.push('plugin:/ ' + e.message); }

  // B: fetch relative
  try {
    const r = await fetch(name);
    if (r && r.ok) { const t = await r.text(); return JSON.parse(t); }
  } catch (e) { attempts.push('fetch ' + e.message); }

  // C: pluginFolder.getEntry + read with formats.utf8
  try {
    const pluginFolder = await fsLfs.getPluginFolder();
    const file = await pluginFolder.getEntry(name);
    const fmt = (formats && formats.utf8) || 'utf-8';
    const text = await file.read({ format: fmt });
    return JSON.parse(text);
  } catch (e) { attempts.push('fs.utf8 ' + e.message); }

  // D: same but with { format: "utf8" } legacy
  try {
    const pluginFolder = await fsLfs.getPluginFolder();
    const file = await pluginFolder.getEntry(name);
    const text = await file.read();
    return JSON.parse(text);
  } catch (e) { attempts.push('fs.default ' + e.message); }

  log('❌ failed to load ' + name + '\n  ' + attempts.join('\n  '));
  return null;
}

async function loadBundledBinaryImage(name) {
  const pluginFolder = await fsLfs.getPluginFolder();
  const file = await pluginFolder.getEntry(name);
  const buf = await file.read({ format: formats.binary });
  const bytes = new Uint8Array(buf);
  let bin = '';
  for (let i = 0; i < bytes.byteLength; i++) bin += String.fromCharCode(bytes[i]);
  const lower = name.toLowerCase();
  const mime = lower.endsWith('.png') ? 'image/png'
    : lower.endsWith('.webp') ? 'image/webp'
    : 'image/jpeg';
  return { imageBase64: btoa(bin), mime, name };
}

async function loadPresets() {
  presetLib = await loadJsonFile('presets.json');
  if (!presetLib) { log('❌ presets.json missing'); return; }
  log('✓ loaded presets ' + (presetLib.version || ''));
  renderPresetGroups();
}

async function loadNegatives() {
  negativeLib = await loadJsonFile('negatives.json');
  if (!negativeLib) { log('❌ negatives.json missing'); return; }
  log('✓ loaded negatives ' + (negativeLib.version || ''));
  // Apply defaults on first load
  for (const cat of Object.keys(negativeLib.categories || {})) {
    for (const item of negativeLib.categories[cat]) {
      if (item.default) selectedNegative.add(item.id);
    }
  }
  renderNegativeGroups();
}

function renderPresetGroups() {
  const root = $('presetGroups');
  if (!root || !presetLib) return;
  root.innerHTML = '';
  for (const cat of Object.keys(presetLib.categories)) {
    const items = presetLib.categories[cat] || [];
    const det = document.createElement('details');
    det.style.cssText = 'border:1px solid var(--db9-border);border-radius:var(--db9-radius-sm);margin-bottom:4px;background:var(--db9-surface);';
    const sum = document.createElement('summary');
    sum.style.cssText = 'padding:6px 8px;cursor:pointer;font-size:11px;color:#94a3b8;font-weight:500;';
    const selCount = items.filter(i => selectedPositive.has(i.id)).length;
    sum.textContent = `${cat} (${selCount}/${items.length})`;
    det.appendChild(sum);
    const wrap = document.createElement('div');
    wrap.style.cssText = 'padding:6px 8px;display:flex;flex-wrap:wrap;gap:4px;';
    for (const item of items) {
      if (presetSearchQ) {
        const hay = (item.label + ' ' + (item.labelEn||'') + ' ' + (item.prompt||'')).toLowerCase();
        if (!hay.includes(presetSearchQ)) continue;
      }
      const chip = document.createElement('span');
      const isOn = selectedPositive.has(item.id);
      chip.className = 'db9-chip';
      chip.style.cssText = `display:inline-block;padding:3px 8px;border-radius:var(--db9-radius-sm);font-size:10px;cursor:pointer;border:1px solid ${isOn ? 'var(--db9-accent)' : 'var(--db9-border)'};background:${isOn ? 'rgba(59, 130, 246, 0.15)' : 'rgba(255, 255, 255, 0.02)'};color:${isOn ? '#ffffff' : '#cbd5e1'};transition:background 120ms, border-color 120ms;`;
      chip.textContent = (item.icon || '') + ' ' + (item.label || item.labelEn || item.id);
      chip.title = item.prompt || '';
      chip.onclick = () => {
        if (selectedPositive.has(item.id)) {
          selectedPositive.delete(item.id);
        } else {
          if (selectedPositive.size >= PRESET_MAX) { log('⚠ max ' + PRESET_MAX + ' presets'); return; }
          selectedPositive.add(item.id);
        }
        renderPresetGroups();
        updatePresetCount();
      };
      wrap.appendChild(chip);
    }
    det.appendChild(wrap);
    root.appendChild(det);
  }
  updatePresetCount();
}

function renderNegativeGroups() {
  const root = $('negativeGroups');
  if (!root || !negativeLib) return;
  root.innerHTML = '';
  for (const cat of Object.keys(negativeLib.categories)) {
    const items = negativeLib.categories[cat] || [];
    const det = document.createElement('details');
    det.style.cssText = 'border:1px solid var(--db9-border);border-radius:var(--db9-radius-sm);margin-bottom:4px;background:var(--db9-surface);';
    const sum = document.createElement('summary');
    sum.style.cssText = 'padding:6px 8px;cursor:pointer;font-size:11px;color:#94a3b8;font-weight:500;';
    const selCount = items.filter(i => selectedNegative.has(i.id)).length;
    sum.textContent = `${cat} (${selCount}/${items.length})`;
    det.appendChild(sum);
    const wrap = document.createElement('div');
    wrap.style.cssText = 'padding:6px 8px;display:flex;flex-wrap:wrap;gap:4px;';
    for (const item of items) {
      if (negativeSearchQ) {
        const hay = (item.label + ' ' + (item.labelEn||'') + ' ' + (item.prompt||'')).toLowerCase();
        if (!hay.includes(negativeSearchQ)) continue;
      }
      const chip = document.createElement('span');
      const isOn = selectedNegative.has(item.id);
      chip.style.cssText = `display:inline-block;padding:3px 8px;border-radius:var(--db9-radius-sm);font-size:10px;cursor:pointer;border:1px solid ${isOn ? 'var(--db9-danger)' : 'var(--db9-border)'};background:${isOn ? 'rgba(239, 68, 68, 0.15)' : 'rgba(255, 255, 255, 0.02)'};color:${isOn ? '#ffffff' : '#cbd5e1'};transition:background 120ms, border-color 120ms;`;
      chip.textContent = (item.icon || '🚫') + ' ' + (item.label || item.labelEn || item.id);
      chip.title = item.prompt || '';
      chip.onclick = () => {
        if (selectedNegative.has(item.id)) selectedNegative.delete(item.id);
        else selectedNegative.add(item.id);
        renderNegativeGroups();
      };
      wrap.appendChild(chip);
    }
    det.appendChild(wrap);
    root.appendChild(det);
  }
}

function updatePresetCount() {
  const el = $('presetCount');
  if (el) el.textContent = `${selectedPositive.size}/${PRESET_MAX} presets selected`;
}

// ===== Vietnamese detection + structured prompt =====
function detectVietnamese(text) {
  if (!text) return false;
  return /[ăâêôơưđĂÂÊÔƠƯĐàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵÀÁẢÃẠẰẮẲẴẶẦẤẨẪẬÈÉẺẼẸỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌỒỐỔỖỘỜỚỞỠỢÙÚỦŨỤỪỨỬỮỰỲÝỶỸỴ]/.test(text);
}

function buildStructuredPrompt(state) {
  const { userPrompt, userNegative, positiveItems, negativeItems } = state;
  let intent = (userPrompt || '').trim();
  if (state.selectionContext) {
    intent = (intent ? intent + '. ' : '') + state.selectionContext;
  }
  // v0.4.7.2: inject reference description if present
  if (typeof refImage !== 'undefined' && refImage && refImage.description) {
    intent = (intent ? intent + '. ' : '') + 'Match style/mood of reference: ' + refImage.description;
  }
  const isVN = detectVietnamese(intent);
  const intentField = (isVN && settings.autoTranslateVN)
    ? `Translate this Vietnamese intent to natural English architectural-visualization terminology, then render: "${intent}"`
    : intent;

  const stylePresets = positiveItems.map(p => p.prompt || p.labelEn || p.label).filter(Boolean);
  const negativeMerged = [
    ...(userNegative ? [userNegative.trim()] : []),
    ...negativeItems.map(n => n.prompt || n.labelEn || n.label).filter(Boolean)
  ].join(', ');

  if (!settings.useStructuredPrompt) {
    // Plain text mode: presets prepended, then intent, then negative trailer
    const parts = [];
    if (stylePresets.length) parts.push(stylePresets.join('. '));
    parts.push((intentField || '(no prompt)') + ', 1024x1024 square image (aspect ratio 1:1)');
    if (negativeMerged) parts.push(`Avoid: ${negativeMerged}.`);
    return parts.join('\n\n');
  }

  // Structured JSON payload
  const payload = {
    intent: intentField || '(no prompt)',
    style_presets: stylePresets,
    negative: negativeMerged,
    output: '1024x1024 photoreal architectural visualization, square image (aspect ratio 1:1)',
  };
  return [
    'ROLE: architectural visualization render assistant.',
    'LANGUAGE: respond in English using architectural terminology.',
    'INPUT (JSON):',
    JSON.stringify(payload, null, 2),
    'INSTRUCTION: render the intent using all preset cues; strictly avoid anything in `negative`.',
  ].join('\n');
}

function selectionWorkflowOptionsFromUI() {
  const mode = $('selectionExpandMode')?.value || settings.selectionExpandMode || 'auto';
  const pxRaw = Number($('selectionExpandPx')?.value ?? settings.selectionExpandPx ?? 96);
  const px = Number.isFinite(pxRaw) ? Math.max(0, Math.min(1024, Math.round(pxRaw))) : 96;
  settings.selectionExpandMode = mode;
  settings.selectionExpandPx = px;
  try { localStorage.setItem('db9_settings', JSON.stringify(settings)); } catch (_) {}
  return { mode, px };
}

function buildSelectionContext(dims, squareBounds, options) {
  if (!dims || !squareBounds) return '';
  return [
    'Edit only the masked central selection while preserving the surrounding architectural context.',
    'The input image is a square 1:1 crop expanded around the user selection.',
    `Original selection ${Math.round(dims.originalW)}x${Math.round(dims.originalH)} px; expanded square ${Math.round(dims.w)}x${Math.round(dims.h)} px.`,
    `Expansion mode ${options?.mode || 'auto'}, margin ${Math.round(options?.px || 0)} px before square fitting.`,
    'Match perspective, lighting direction, materials, scale, camera angle, color temperature, shadows, reflections, and edge continuity with the visible surroundings.',
    'Generate a seamless replacement suitable for being clipped by the original Photoshop selection mask.'
  ].join(' ');
}
function getStateFromUI() {
  const userPrompt = $('promptInput')?.value || '';
  const userNegative = $('negativePrompt')?.value || '';
  const provider = selectedProviderFromUI();
  const mode = document.querySelector('input[name="mode"]:checked')?.value || 'new';
  const positiveItems = [];
  const negativeItems = [];
  if (presetLib) {
    for (const cat of Object.keys(presetLib.categories)) {
      for (const it of presetLib.categories[cat]) {
        if (selectedPositive.has(it.id)) positiveItems.push(it);
      }
    }
  }
  if (negativeLib) {
    for (const cat of Object.keys(negativeLib.categories)) {
      for (const it of negativeLib.categories[cat]) {
        if (selectedNegative.has(it.id)) negativeItems.push(it);
      }
    }
  }
  return { userPrompt, userNegative, provider, mode, positiveItems, negativeItems };
}

// ===== Saved combos =====
function loadSavedCombos() {
  try {
    const raw = localStorage.getItem('db9_custom_presets');
    savedCombos = raw ? JSON.parse(raw) : [];
  } catch (e) { savedCombos = []; }
  renderSavedCombos();
}

function persistSavedCombos() {
  localStorage.setItem('db9_custom_presets', JSON.stringify(savedCombos));
}

function renderSavedCombos() {
  const root = $('customList');
  if (!root) return;
  if (!savedCombos.length) {
    root.innerHTML = '<span class="small">No combos saved yet — pick presets/negatives then click "Save combo as…"</span>';
    return;
  }
  root.innerHTML = '';
  root.style.cssText = 'display:flex;flex-wrap:wrap;gap:4px;';
  for (const c of savedCombos) {
    const chip = document.createElement('span');
    chip.style.cssText = 'display:inline-block;padding:4px 8px;border-radius:var(--db9-radius-sm);font-size:10px;cursor:pointer;border:1px solid var(--db9-accent);background:rgba(59, 130, 246, 0.1);color:#ffffff;';
    chip.textContent = '💾 ' + c.name;
    chip.title = `${c.positive?.length || 0} presets · ${c.negative?.length || 0} negatives · provider=${c.provider}`;
    chip.onclick = () => loadCombo(c.id);
    chip.oncontextmenu = (e) => {
      e.preventDefault();
      if (confirm('Delete combo "' + c.name + '"?')) {
        savedCombos = savedCombos.filter(x => x.id !== c.id);
        persistSavedCombos();
        renderSavedCombos();
      }
    };
    root.appendChild(chip);
  }
}

function saveCurrentCombo() {
  const name = prompt('Tên combo:');
  if (!name) return;
  const state = getStateFromUI();
  const combo = {
    id: 'custom-' + Date.now(),
    name: name.trim(),
    positive: [...selectedPositive],
    negative: [...selectedNegative],
    userPrompt: state.userPrompt,
    userNegative: state.userNegative,
    provider: state.provider,
  };
  savedCombos.push(combo);
  persistSavedCombos();
  renderSavedCombos();
  log('💾 saved combo "' + combo.name + '"');
}

function loadCombo(id) {
  const c = savedCombos.find(x => x.id === id);
  if (!c) return;
  selectedPositive = new Set(c.positive || []);
  selectedNegative = new Set(c.negative || []);
  $('promptInput').value = c.userPrompt || '';
  $('negativePrompt').value = c.userNegative || '';
  const r = document.querySelector(`input[name="provider"][value="${c.provider}"]`);
  if (r) r.checked = true;
  renderPresetGroups();
  renderNegativeGroups();
  log('📂 loaded combo "' + c.name + '"');
}

function exportCombos() {
  const json = JSON.stringify(savedCombos, null, 2);
  try {
    navigator.clipboard.writeText(json);
    log('⬆ exported ' + savedCombos.length + ' combo(s) to clipboard');
  } catch (e) {
    prompt('Copy this JSON:', json);
  }
}

function importCombos() {
  const json = prompt('Paste combos JSON:');
  if (!json) return;
  try {
    const arr = JSON.parse(json);
    if (!Array.isArray(arr)) throw new Error('not an array');
    let added = 0;
    for (const c of arr) {
      if (!savedCombos.find(x => x.id === c.id)) {
        savedCombos.push(c);
        added++;
      }
    }
    persistSavedCombos();
    renderSavedCombos();
    log('⬇ imported ' + added + ' combo(s)');
  } catch (e) {
    log('❌ import failed: ' + e.message);
  }
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

async function pollHealth() {
  try {
    // v0.4.7.2: use XMLHttpRequest — UXP PS has better localhost support via XHR than fetch
    const text = await xhrGet(BRIDGE + '/health', 3500);
    const data = JSON.parse(text);
    if (!bridgeOnline) log('✓ bridge ONLINE v' + data.version + ' providers=[' + (data.providers || []).join(',') + ']');
    bridgeOnline = true;
    lastBridgeError = null;
    setDot('dot-bridge', 'on');
    providersOnline = data.providers || [];
    setDot('dot-gemini', providersOnline.includes('gemini') ? 'on' : 'off');
    setDot('dot-chatgpt', providersOnline.includes('chatgpt') ? 'on' : 'off');
    syncGenerateAvailability();
  } catch (e) {
    const errMsg = e.message || String(e);
    if (bridgeOnline !== false || lastBridgeError !== errMsg) {
      log('⚠ bridge OFFLINE: ' + errMsg);
      lastBridgeError = errMsg;
    }
    bridgeOnline = false;
    setDot('dot-bridge', 'err');
    setDot('dot-gemini', 'off');
    setDot('dot-chatgpt', 'off');
    syncGenerateAvailability();
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
      // 1. Copy the original selection to a temporary layer (Ctrl+J-like layer)
      await batchPlay([{ _obj: 'copyToLayer' }], { synchronousExecution: true });
      const selLayer = doc.activeLayers[0];
      if (selLayer) selectionLayerId = selLayer.id;
      
      // Select the original layer again to copy the square bounds context
      await selectLayerById(originalLayerId);
    }

    // 2. Select the squareBounds
    await selectRectangle(squareBounds);

    // 3. Copy square bounds to a new layer
    await batchPlay([{ _obj: 'copyToLayer' }], { synchronousExecution: true });
    const contextLayer = doc.activeLayers[0];
    if (!contextLayer) throw new Error('Failed to create context layer');

    // 4. Convert context layer to a Smart Object
    await batchPlay([{ _obj: 'newPlacedLayer' }], { synchronousExecution: true });
    const smartObjectLayer = doc.activeLayers[0];
    if (!smartObjectLayer) throw new Error('Failed to create Smart Object layer');
    if (smartObjectLayer) {
      smartObjectLayer.name = 'DB9 Inpaint Smart Object ' + new Date().toLocaleTimeString();
    }

    // 5. Apply the mask if there was a selection
    if (hasSelection && selectionLayerId) {
      try {
        // Load the temporary layer transparency as the active document selection.
        await selectLayerById(selectionLayerId);
        await batchPlay([{
          _obj: 'set',
          _target: [{ _ref: 'channel', _property: 'selection' }],
          to: { _ref: 'channel', _enum: 'channel', _value: 'transparencyEnum' }
        }], { synchronousExecution: true });

        // Select the Smart Object layer again, keeping the loaded selection active.
        await selectLayerById(smartObjectLayer.id);

        // Create the user mask revealing the original selection.
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

async function writeTempPng(base64, prefix = 'db9_result_') {
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
    log(`📐 selection ${Math.round(selW)}x${Math.round(selH)} +${squareBounds.pad}px -> square ${dims.w}x${dims.h} at (${squareBounds.left},${squareBounds.top})`);

    smartObjectLayerId = await prepareSelectionSmartObject(squareBounds, sel !== null);

    // CORRECT APPROACH: select squareBounds on original doc, copy merged, save
    await selectRectangle(squareBounds);
    await batchPlay([{ _obj: 'copyMerged' }], { synchronousExecution: true });

    const tmpFolder = await fsLfs.getTemporaryFolder();
    const outFile = await tmpFolder.createFile('db9_sel_' + Date.now() + '.png', { overwrite: true });

    // Create new doc from clipboard at exact squareBounds size, save, close
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

    // Validate PNG header dimensions (bytes 16-23 = IHDR width/height)
    const view = new DataView(bytes.buffer);
    const pngW = view.getUint32(16, false);
    const pngH = view.getUint32(20, false);
    if (pngW !== dims.w || pngH !== dims.h) {
      throw new Error(`Export dimension mismatch: got ${pngW}x${pngH}, expected ${dims.w}x${dims.h}. Aborting.`);
    }
    log(`✓ export validated ${pngW}x${pngH} ${Math.round(bytes.byteLength/1024)}KB smartObjectId=${smartObjectLayerId}`);
    if (bytes.byteLength > 10 * 1024 * 1024) {
      throw new Error(`Export too large: ${Math.round(bytes.byteLength/1024/1024)}MB. Reduce selection size.`);
    }

    let bin = '';
    for (let i = 0; i < bytes.byteLength; i++) bin += String.fromCharCode(bytes[i]);
    base64 = btoa(bin);
  }, { commandName: 'DB9 prepare selection Smart Object + export 1:1' });
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

async function replaceSmartObjectContents(base64, label, context = lastInpaintContext) {
  if (!context?.smartObjectLayerId) return false;
  const outFile = await writeTempPng(base64, 'db9_smart_replace_');
  const token = await fsLfs.createSessionToken(outFile);
  
  await executeAsModal(async () => {
    const selected = await selectLayerById(context.smartObjectLayerId);
    if (!selected) throw new Error('Target DB9 smart object layer is not available');
    
    // 1. Open the smart object
    await batchPlay([{ _obj: 'placedLayerEditContents' }], { synchronousExecution: true });
    
    const soDoc = app.activeDocument;
    
    // 2. Place the new image (Photoshop auto-scales to fit the canvas bounds)
    await batchPlay([{
      _obj: 'placeEvent',
      null: { _path: token, _kind: 'local' },
      freeTransformCenterState: { _enum: 'quadCenterState', _value: 'QCSAverage' }
    }], { synchronousExecution: true });
    
    // 3. Rename the newly placed layer
    const layer = soDoc.activeLayers[0];
    if (layer) layer.name = 'DB9 ' + (label || 'Gemini') + ' Smart Result ' + new Date().toLocaleTimeString();
    
    // 4. Save and close the smart object to update the parent document
    await soDoc.save();
    await soDoc.close();
  }, { commandName: 'DB9 Smart Object auto-scale replace' });
  
  log('✅ updated Smart Object with auto-scaling' + (label ? ' (' + label + ')' : ''));
  return true;
}

async function applyResultToPS(base64, label, placementBounds, context = lastInpaintContext) {
  try {
    if (await replaceSmartObjectContents(base64, label, context)) return;
  } catch (e) {
    log('  ⚠ smart object replace failed, placing result layer: ' + e.message);
  }

  await executeAsModal(async (ctx) => {
    const outFile = await writeTempPng(base64);
    const token = await fsLfs.createSessionToken(outFile);
    await batchPlay([{
      _obj: 'placeEvent',
      null: { _path: token, _kind: 'local' },
      freeTransformCenterState: { _enum: 'quadCenterState', _value: 'QCSAverage' }
    }], { synchronousExecution: true });
    log('✅ placed new layer' + (label ? ' (' + label + ')' : '') + (placementBounds ? ` at ${placementBounds.left},${placementBounds.top} size ${placementBounds.size}` : ''));

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
          layer.name = 'DB9 ' + (label || 'gen') + ' ' + new Date().toLocaleTimeString();
        }
      } catch (e) { log('  ⚠ post-place adjust skipped: ' + e.message); }
    }
  }, { commandName: 'DB9 apply result as new layer' });
}
async function runGenerate() {
  if (activeJob) { log('⚠ job in progress, please wait'); return; }
  if (!bridgeOnline) { log('❌ bridge offline'); return; }
  activeJob = 'local-preflight';
  syncGenerateAvailability();

  const state = getStateFromUI();
  const finalPrompt = buildStructuredPrompt(state);
  log(`▶ generate provider=${state.provider} mode=${state.mode} presets=${state.positiveItems.length} negatives=${state.negativeItems.length}`);
  console.log('[DB9] structured prompt:\n' + finalPrompt);

  // sec-progress is now always visible
  $('progressLog').textContent = '';
  $('progressSteps').innerHTML = '<div class="db9-step active">📤 Exporting selection…</div>';

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
    log(`✓ exported ${dims?.w}x${dims?.h} (${Math.round((base64?.length || 0) * 0.75 / 1024)} KB)`);

    $('progressSteps').innerHTML += '<div class="db9-step active">📡 Posting to bridge…</div>';
    const body = {
      imageBase64: base64,
      prompt: finalPrompt,
      provider: state.provider,
      mode: state.mode,
    };
    log('📡 POST /generate provider=' + body.provider + ' bytes=' + (body.imageBase64?.length || 0));
    const respText = await xhrPost(BRIDGE + '/generate', JSON.stringify(body), 20000);
    const data = JSON.parse(respText);
    log('✓ job ' + (data.jobId || data.parentId) + ' queued');

    if (state.provider === 'both') {
      await runDualPolling(data.parentId || data.jobId, finalPrompt);
    } else {
      await runSinglePolling(data.jobId, state.provider, finalPrompt);
    }
  } catch (e) {
    log('❌ ' + e.message);
    $('progressSteps').innerHTML += '<div class="db9-step error">❌ ' + e.message + '</div>';
  } finally {
    activeJob = null;
    syncGenerateAvailability();
  }
}

async function runSinglePolling(jobId, provider, prompt) {
  activeJob = jobId;
  $('progressSteps').innerHTML += '<div class="db9-step active">🎨 Generating in ' + provider + '…</div>';
  for (let i = 0; i < 240; i++) { // up to ~8 min
    await new Promise(r => setTimeout(r, 2000));
    let j;
    try {
      const txt = await xhrGet(BRIDGE + '/job/' + jobId, 5000);
      j = JSON.parse(txt);
    } catch (e) { continue; }
    const resultBase64 = j.resultBase64 || j.imageBase64 || null;
    if (j.status === 'done' && resultBase64) {
      log('✓ result received');
      await applyResultToPS(resultBase64, provider, window.__db9_lastSquareBounds);
      pushHistory({ jobId, prompt, provider, base64: resultBase64 });
      $('progressSteps').innerHTML += '<div class="db9-step done">✅ Done</div>';
      return;
    }
    if (j.status === 'error') throw new Error(j.error || 'job error');
  }
  throw new Error('timeout');
}

async function runDualPolling(parentId, prompt) {
  activeJob = parentId;
  $('progressSteps').innerHTML += '<div class="db9-step active">⚔ Dual generating (Gemini + ChatGPT)…</div>';
  openDualModal();
  dualState = { parentId, gemini: { status: 'pending' }, chatgpt: { status: 'pending' } };

  for (let i = 0; i < 240; i++) {
    await new Promise(r => setTimeout(r, 2000));
    let j;
    try {
      const txt = await xhrGet(BRIDGE + '/job/' + parentId + '/dual', 5000);
      j = JSON.parse(txt);
    } catch (e) { continue; }
    for (const p of ['gemini', 'chatgpt']) {
      const child = j.results?.[p];
      if (!child) continue;
      const statusEl = $('dual-status-' + p);
      const imgEl = $('dual-img-' + p);
      const useBtn = $('dual-use-' + p);
      const resultBase64 = child.resultBase64 || child.imageBase64 || null;
      if (child.status === 'done' && resultBase64) {
        if (dualState[p].status !== 'done') {
          dualState[p] = { status: 'done', base64: resultBase64 };
          imgEl.src = 'data:image/png;base64,' + resultBase64;
          statusEl.textContent = '✓ ready';
          useBtn.disabled = false;
          pushHistory({ jobId: parentId + '-' + p, prompt, provider: p, base64: resultBase64 });
          log('✓ ' + p + ' done');
        }
      } else if (child.status === 'error') {
        dualState[p] = { status: 'error' };
        statusEl.textContent = '❌ ' + (child.error || 'error');
      } else {
        statusEl.textContent = child.status || 'running…';
      }
    }
    if (j.status === 'complete' || (dualState.gemini.status !== 'pending' && dualState.chatgpt.status !== 'pending')) {
      $('progressSteps').innerHTML += '<div class="db9-step done">✅ Both finished — choose result</div>';
      return;
    }
  }
  throw new Error('dual timeout');
}

function openDualModal() {
  $('dualModal').style.display = 'flex';
  $('dual-img-gemini').src = '';
  $('dual-img-chatgpt').src = '';
  $('dual-status-gemini').textContent = 'waiting…';
  $('dual-status-chatgpt').textContent = 'waiting…';
  $('dual-use-gemini').disabled = true;
  $('dual-use-chatgpt').disabled = true;
}
function closeDualModal() { $('dualModal').style.display = 'none'; dualState = null; }

// ===== History =====
function pushHistory(entry) {
  history.unshift({ ...entry, ts: Date.now() });
  if (history.length > 30) history.pop();
  renderHistory();
}
function renderHistory() {
  const root = $('historyGrid');
  if (!root) return;
  if (!history.length) { root.innerHTML = '<div class="db9-history-empty">No generations yet</div>'; return; }
  root.innerHTML = '';
  for (const h of history) {
    const cell = document.createElement('div');
    cell.className = 'db9-history-cell';
    cell.title = h.provider + ' · ' + new Date(h.ts).toLocaleString();
    const img = document.createElement('img');
    img.src = 'data:image/png;base64,' + h.base64;
    cell.appendChild(img);
    cell.onclick = async () => {
      log('🔁 re-applying from history');
      await applyResultToPS(h.base64, h.provider, null);
    };
    root.appendChild(cell);
  }
}

async function runRegenerate() {
  if (activeJob) { log('⚠ job in progress, please wait'); return; }
  if (!bridgeOnline) { log('❌ bridge offline'); return; }
  if (!lastInpaintContext || !lastInpaintContext.smartObjectLayerId || !lastInpaintContext.imageBase64) {
    log('❌ No active Smart Object context to regenerate');
    return;
  }

  activeJob = 'local-preflight';
  syncGenerateAvailability();

  const state = getStateFromUI();
  const finalPrompt = buildStructuredPrompt(state);
  log(`▶ regenerate provider=${state.provider} mode=${state.mode} smartObjectId=${lastInpaintContext.smartObjectLayerId}`);
  console.log('[DB9] structured prompt:\n' + finalPrompt);

  $('progressLog').textContent = '';
  $('progressSteps').innerHTML = '<div class="db9-step active">📡 Posting regenerate to bridge…</div>';

  try {
    const body = {
      imageBase64: lastInpaintContext.imageBase64,
      prompt: finalPrompt,
      provider: state.provider,
      mode: state.mode,
    };
    log('📡 POST /generate provider=' + body.provider + ' bytes=' + (body.imageBase64?.length || 0));
    const respText = await xhrPost(BRIDGE + '/generate', JSON.stringify(body), 20000);
    const data = JSON.parse(respText);
    log('✓ regenerate job ' + (data.jobId || data.parentId) + ' queued');

    // Update the prompt in the context
    lastInpaintContext.prompt = finalPrompt;

    if (state.provider === 'both') {
      await runDualPolling(data.parentId || data.jobId, finalPrompt);
    } else {
      await runSinglePolling(data.jobId, state.provider, finalPrompt);
    }
  } catch (e) {
    log('❌ ' + e.message);
    $('progressSteps').innerHTML += '<div class="db9-step error">❌ ' + e.message + '</div>';
  } finally {
    activeJob = null;
    syncGenerateAvailability();
  }
}

// ===== Wire up DOM events =====
function wire() {
  const btnRegen = $('btn-regenerate');
  if (btnRegen) {
    btnRegen.onclick = () => runRegenerate().catch(e => log('❌ ' + e.message));
  }

  $('btn-generate').onclick = () => runGenerate().catch(e => log('❌ ' + e.message));
  $('btn-clear').onclick = () => {
    selectedPositive.clear();
    renderPresetGroups();
    log('🧹 cleared presets');
  };
  $('btn-save-custom').onclick = () => saveCurrentCombo();
  $('btn-export').onclick = () => exportCombos();
  $('btn-import').onclick = () => importCombos();
  $('btn-open-gemini').onclick = () => {
    try { uxp.shell.openExternal('https://gemini.google.com/app'); } catch (e) { log('❌ ' + e.message); }
  };
  $('btn-open-chatgpt').onclick = () => {
    try { uxp.shell.openExternal('https://chatgpt.com/'); } catch (e) { log('❌ ' + e.message); }
  };
  // Tab switching
  document.querySelectorAll('.db9-tab').forEach(t => {
    t.onclick = () => {
      const target = t.dataset.tab;
      document.querySelectorAll('.db9-tab').forEach(x => x.classList.remove('active'));
      t.classList.add('active');
      document.querySelectorAll('.db9-pane').forEach(p => p.classList.remove('active'));
      // For main tab, activate all 3 main panes (header sections)
      if (target === 'pane-main') {
        ['pane-main','pane-main-bottom','pane-main-history'].forEach(id => {
          const e = document.getElementById(id); if (e) e.classList.add('active');
        });
      } else {
        const e = document.getElementById(target); if (e) e.classList.add('active');
      }
    };
  });

  // Test buttons (send dummy prompt to each provider)
  const testGem = document.createElement('button');
  testGem.textContent = 'Test Gemini';
  testGem.style.cssText = 'font-size:10px;padding:3px 6px;margin-left:4px;border-radius:var(--db9-radius-sm);';
  testGem.onclick = () => testProvider('gemini');
  const testCG = document.createElement('button');
  testCG.textContent = 'Test ChatGPT';
  testCG.style.cssText = 'font-size:10px;padding:3px 6px;margin-left:4px;border-radius:var(--db9-radius-sm);';
  testCG.onclick = () => testProvider('chatgpt');
  const providerExtra = document.querySelector('.provider-extra');
  if (providerExtra) { providerExtra.appendChild(testGem); providerExtra.appendChild(testCG); }

  $('btn-settings').onclick = () => {
    settings.useStructuredPrompt = !settings.useStructuredPrompt;
    localStorage.setItem('db9_settings', JSON.stringify(settings));
    log('⚙ structured prompt: ' + (settings.useStructuredPrompt ? 'on' : 'off'));
    updateHint();
  };
  $('promptInput').oninput = updateHint;
  const ps = $('presetSearch');
  if (ps) ps.oninput = (e) => { presetSearchQ = e.target.value.toLowerCase(); renderPresetGroups(); };
  const ns = $('negativeSearch');
  if (ns) ns.oninput = (e) => { negativeSearchQ = e.target.value.toLowerCase(); renderNegativeGroups(); };

  // Dual modal handlers
  $('dual-use-gemini').onclick = async () => {
    if (dualState?.gemini?.base64) {
      await applyResultToPS(dualState.gemini.base64, 'gemini', window.__db9_lastSquareBounds);
      closeDualModal();
    }
  };
  $('dual-use-chatgpt').onclick = async () => {
    if (dualState?.chatgpt?.base64) {
      await applyResultToPS(dualState.chatgpt.base64, 'chatgpt', window.__db9_lastSquareBounds);
      closeDualModal();
    }
  };
  $('dual-cancel').onclick = () => closeDualModal();

  // Persist provider choice
  for (const r of document.querySelectorAll('input[name="provider"]')) {
    r.onchange = () => {
      localStorage.setItem('db9_provider', r.value);
      syncGenerateAvailability();
    };
  }
  const savedProvider = localStorage.getItem('db9_provider');
  if (savedProvider) {
    const r = document.querySelector(`input[name="provider"][value="${savedProvider}"]`);
    if (r) r.checked = true;
  }
}

function updateHint() {
  const el = $('promptHint');
  if (!el) return;
  const txt = $('promptInput')?.value || '';
  const isVN = detectVietnamese(txt);
  el.innerHTML = `Auto-translate VN→EN: <b>${settings.autoTranslateVN ? 'on' : 'off'}</b> · Structured: <b>${settings.useStructuredPrompt ? 'on' : 'off'}</b> · Detected: <b>${isVN ? 'VN' : 'EN'}</b> · ${txt.length} chars`;
}

// ===== Init =====
async function testProvider(provider) {
  log('🧪 testing ' + provider + '...');
  try {
    let payload;
    try {
      payload = await loadBundledBinaryImage('Gemini_Generated_Image_tielljtielljtiel.jpg');
      log('✓ loaded bundled test image: ' + payload.name);
    } catch (e) {
      // Fallback if the bundled test image is missing
      payload = {
        imageBase64: 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==',
        mime: 'image/png',
        name: 'fallback-red-pixel.png',
      };
      log('⚠ bundled test image missing, using fallback pixel: ' + e.message);
    }
    const body = {
      imageBase64: payload.imageBase64,
      mime: payload.mime,
      prompt: 'thêm 1 con mèo vào',
      provider,
      mode: 'new',
    };
    const txt = await xhrPost(BRIDGE + '/generate', JSON.stringify(body), 15000);
    const data = JSON.parse(txt);
    log('✓ test job queued: ' + (data.jobId || data.parentId));
  } catch (e) {
    log('❌ test failed: ' + e.message);
  }
}


  // Reference image handlers (v0.4.7.2)
  const refBtn = $('btn-ref-upload');
  if (refBtn) refBtn.onclick = async () => {
    try {
      const file = await fsLfs.getFileForOpening({ types: ['jpg','jpeg','png','webp'] });
      if (!file) return;
      const buf = await file.read({ format: formats.binary });
      const bytes = new Uint8Array(buf);
      let bin = '';
      for (let i = 0; i < bytes.byteLength; i++) bin += String.fromCharCode(bytes[i]);
      const b64 = btoa(bin);
      const mime = file.name.toLowerCase().endsWith('.png') ? 'image/png' : 'image/jpeg';
      refImage = { base64: b64, mime, description: '' };
      const img = $('refImagePreview');
      img.src = 'data:' + mime + ';base64,' + b64;
      img.classList.add('has-image');
      $('btn-ref-describe').disabled = false;
      log('📂 reference loaded: ' + file.name + ' (' + Math.round(b64.length * 0.75 / 1024) + ' KB)');
    } catch (e) { log('❌ ref upload: ' + e.message); }
  };
  const refDescBtn = $('btn-ref-describe');
  if (refDescBtn) refDescBtn.onclick = async () => {
    if (!refImage) return;
    log('🤖 requesting description via Gemini tab...');
    try {
      // Send to bridge with a special "describe" provider flag
      const body = {
        imageBase64: refImage.base64,
        prompt: 'You are an architectural visualization expert. Describe this reference image in ENGLISH, covering: architectural style, materials, lighting, mood, color palette, composition, notable details. Keep it concise (3-5 sentences) and use terminology suitable for image-gen prompting.',
        provider: 'gemini',
        mode: 'describe-only',
      };
      const txt = await xhrPost(BRIDGE + '/generate', JSON.stringify(body), 20000);
      const data = JSON.parse(txt);
      log('  ✓ describe job queued ' + (data.jobId || '?') + ' — waiting for result...');
      // Poll
      for (let i = 0; i < 120; i++) {
        await new Promise(r => setTimeout(r, 2000));
        try {
          const t = await xhrGet(BRIDGE + '/job/' + data.jobId, 4000);
          const j = JSON.parse(t);
          if (j.status === 'done') {
            refImage.description = j.text || j.description || '(empty description)';
            const box = $('refDescBox');
            box.textContent = refImage.description;
            box.classList.add('has-desc');
            log('  ✓ description ready (' + refImage.description.length + ' chars)');
            return;
          }
          if (j.status === 'error') { log('  ❌ describe failed: ' + j.error); return; }
        } catch (e) {}
      }
      log('  ⚠ describe timeout');
    } catch (e) { log('❌ describe: ' + e.message); }
  };
  const refClearBtn = $('btn-ref-clear');
  if (refClearBtn) refClearBtn.onclick = () => {
    refImage = null;
    const img = $('refImagePreview');
    img.src = ''; img.classList.remove('has-image');
    const box = $('refDescBox');
    box.textContent = ''; box.classList.remove('has-desc');
    $('btn-ref-describe').disabled = true;
    log('🗑 reference cleared');
  };
  const refSaveBtn = $('btn-ref-save-preset');
  if (refSaveBtn) refSaveBtn.onclick = () => {
    if (!refImage || !refImage.description) { log('⚠ need reference + description first'); return; }
    const cat = prompt('Category (Architecture / Furniture / People / Custom):', 'Architecture');
    const name = prompt('Preset name:');
    if (!name) return;
    const preset = {
      id: 'ref-' + Date.now(),
      name: name.trim(),
      category: cat || 'Custom',
      kind: 'reference',
      description: refImage.description,
      thumbBase64: refImage.base64.slice(0, 2000), // store tiny thumb only
    };
    savedCombos.push({ id: preset.id, name: preset.name, positive: [], negative: [], userPrompt: preset.description, userNegative: '', provider: 'gemini', kind: 'reference' });
    persistSavedCombos();
    renderSavedCombos();
    log('💾 saved reference preset "' + name + '"');
  };

  // Reconnect button
  const recBtn = $('btn-reconnect');
  if (recBtn) recBtn.onclick = () => { log('🔄 forcing reconnect...'); pollHealth(); };

  // Auto horizontal layout when panel wide (landscape orientation)
  const applyLayout = () => {
    if (window.innerWidth > window.innerHeight) document.body.classList.add('h-layout');
    else document.body.classList.remove('h-layout');
  };
  applyLayout();
  window.addEventListener('resize', applyLayout);

async function init() {
  log('🍌 DB9 Multi-Provider v' + VERSION + ' starting…');
  try {
    const s = localStorage.getItem('db9_settings');
    if (s) settings = { ...settings, ...JSON.parse(s) };
  } catch (e) {}
  sanitizeUiCopy();
  wire();
  await loadPresets();
  await loadNegatives();
  loadSavedCombos();
  startHealthPolling();
  updateHint();
  syncGenerateAvailability();
  log('✓ ready');
}

init().catch(e => log('❌ init: ' + e.message));
