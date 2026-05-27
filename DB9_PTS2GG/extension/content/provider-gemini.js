// DB9 Multi-Provider XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX Gemini provider module
// Loaded first on https://gemini.google.com/*, BEFORE content-script.js.
// Exposes window.__DB9_PROVIDER = { name, selectors, submitPrompt, uploadImage,
// waitForOutput, downloadHD, toggleCreateImage, startNewChat, promptInput,
// installNetworkMonitor, getUploadMonitorOk } XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX the shared orchestrator in
// content-script.js calls into this object so the same run-loop works for
// every provider.
//
// All selectors here are the ones that were verified working through v0.2.1
// on Gemini's Angular UI. Do not change them without re-testing Gemini.

(() => {
  if (window.__DB9_PROVIDER && window.__DB9_PROVIDER.name === 'gemini') return;

  try {
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const rand = (min, max) => min + Math.random() * (max - min);
  const visible = (e) => e && e.offsetParent !== null;
  const qAll = (sel, root = document) => [...root.querySelectorAll(sel)];
  function allOpenRoots(root = document, out = []) {
    out.push(root);
    const nodes = root.querySelectorAll ? root.querySelectorAll('*') : [];
    for (const node of nodes) {
      if (node && node.shadowRoot) allOpenRoots(node.shadowRoot, out);
    }
    return out;
  }
  function qAllDeep(sel, root = document) {
    const seen = new Set();
    const found = [];
    for (const scope of allOpenRoots(root, [])) {
      try {
        for (const el of scope.querySelectorAll(sel)) {
          if (!seen.has(el)) {
            seen.add(el);
            found.push(el);
          }
        }
      } catch (e) {}
    }
    return found;
  }
  function qDeep(sel, root = document) {
    return qAllDeep(sel, root)[0] || null;
  }
  const normalizeText = (value) => (value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim();
  const textOf = (el) => normalizeText((el?.textContent || '') + ' ' + (el?.getAttribute?.('aria-label') || ''));
  const textMatches = (el, phrases) => {
    const hay = textOf(el);
    return phrases.some((phrase) => hay.includes(normalizeText(phrase)));
  };

  const log = (text) => {
    console.log('[DB9-Gemini]', text);
    try { chrome.runtime.sendMessage({ type: 'log', text: '[gemini] ' + text }); } catch (e) {}
  };

  // v0.4.7.1: Angular Material needs real MouseEvents, not el.click()
  function realClick(el) {
    if (!el) return false;
    try {
      const rect = el.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      const opts = { bubbles: true, cancelable: true, composed: true, view: window, clientX: cx, clientY: cy, button: 0 };
      el.dispatchEvent(new PointerEvent('pointerdown', { ...opts, pointerType: 'mouse' }));
      el.dispatchEvent(new MouseEvent('mousedown', opts));
      el.dispatchEvent(new PointerEvent('pointerup', { ...opts, pointerType: 'mouse' }));
      el.dispatchEvent(new MouseEvent('mouseup', opts));
      el.dispatchEvent(new MouseEvent('click', opts));
      return true;
    } catch (e) {
      try { el.click(); return true; } catch (_) { return false; }
    }
  }

  // qAll/visible helpers

  // ===== Selectors =====
  function promptInput() {
    return qDeep(
      'div[role="textbox"][aria-label*="prompt for Gemini" i], ' +
      'div[contenteditable="true"][aria-label*="prompt" i], ' +
      'div[contenteditable="true"][aria-label*="Enter a prompt for Gemini" i], ' +
      'rich-textarea div[contenteditable="true"], ' +
      'div.ql-editor[contenteditable="true"]'
    );
  }

  function createImageToggle() {
    return [...document.querySelectorAll('button,[role="menuitem"],toolbox-drawer-item button')].find((el) =>
      textMatches(el, ['Create image', 'Tao hinh anh'])
    );
  }

  function isCreateImageActive() {
    const btn = createImageToggle();
    if (!btn) return false;
    const a = btn.getAttribute('aria-label') || '';
    return /^deselect/i.test(a);
  }

  function sendButton() {
    return qDeep(
      'button[aria-label*="Send message" i], ' +
      'button[aria-label*="Submit" i], ' +
      'button[aria-label="Send" i], ' +
      'button[aria-label*="Run" i], ' +
      'button[aria-label*="Gửi tin nhắn" i], ' +
      'button[data-test-id="send-button"], ' +
      'button[data-test-id*="send" i], ' +
      'button[data-test-id*="submit" i], ' +
      'button:has(mat-icon[data-mat-icon-name="arrow_upward"]), ' +
      '[data-mat-icon-name="arrow_upward"]'
    ) || qAllDeep('button,[role="button"]').find((el) =>
      textMatches(el, ['Send', 'Gui', 'Submit', 'Run', 'Gửi']) && !el.disabled
    ) || null;
  }
  function newChatButton() {
    return [...document.querySelectorAll('button,a')].find(b =>
      /new chat/i.test(b.getAttribute('aria-label') || b.textContent || '')
    );
  }

  function downloadButtons() {
    return qAll('button[aria-label*="Download full size image" i]').filter(visible);
  }


  function generatedVideos() {
    return qAllDeep('video').filter((video) => {
      if (!visible(video)) return false;
      const src = video.currentSrc || video.src || '';
      const rect = video.getBoundingClientRect();
      const hasSize = rect.width >= 160 && rect.height >= 120;
      return hasSize && !!src && !src.startsWith('data:');
    });
  }

  function outputKey(el) {
    return [el.tagName || '', el.currentSrc || el.src || '', el.getAttribute('aria-label') || '', el.getAttribute('alt') || '', el.textContent || ''].join('|');
  }

  function generatedImages() {
    return qAllDeep('img').filter((img) => {
      if (!visible(img)) return false;
      const width = img.naturalWidth || img.width || 0;
      const height = img.naturalHeight || img.height || 0;
      if (width < 200 || height < 200) return false;
      const src = img.currentSrc || img.src || '';
      const alt = img.alt || '';
      if (src.startsWith('data:')) return false;
      if (/avatar|profile|logo|icon/i.test(alt + ' ' + src)) return false;
      const looksGenerated = /AI generated|generated image|image generated|do AI tao|do AI to/i.test(alt);
      const isLargeBlob = src.startsWith('blob:') && width >= 512 && height >= 512;
      return looksGenerated
        || isLargeBlob
        || /googleusercontent\.com|gemini|usercontent|lh3\.google/i.test(src)
        || width * height >= 160000;
    });
  }
  let baselineImageKeys = new Set();
  function imageKey(img) {
    return [img.currentSrc || img.src || '', img.alt || '', img.naturalWidth || img.width || 0, img.naturalHeight || img.height || 0].join('|');
  }

  function uploadMenuButton() {
    return qDeep('button[aria-label="Open upload file menu"]')
        || qDeep('button[aria-label*="upload file menu" i]')
        || qDeep('button[aria-label*="Add files" i]')
        || qDeep('button[aria-label*="Attach" i]')
        || qAllDeep('button,[role="button"]').find((el) =>
          textMatches(el, ['Open upload file menu', 'Upload files', 'Tai len tep'])
        );
  }

  function toolsButton() {
    // v0.4.7.3: added Vietnamese "Nội dung tải lên và công cụ" (confirmed DOM evidence 2026-05-27)
    return qDeep('button[aria-label="Nội dung tải lên và công cụ"]')
        || qDeep('button[aria-label*="tải lên và công cụ" i]')
        || qDeep('button[aria-label*="upload and tools" i]')
        || qDeep('button[aria-label="Tools"]')
        || qDeep('button[aria-label="Open tools" i]')
        || qDeep('button[aria-label*="công cụ" i]')
        || qAllDeep('button.mat-mdc-tooltip-trigger, button.mdc-icon-button').find(b => textMatches(b, ['+']));
  }

  function uploadPreviewImages() {
    return [
      ...qAll('uploader-file-preview, .file-preview-chip, .uploader-file-preview-container, [data-test-id="uploaded-img"]'),
      ...qAll('img').filter((img) => img.src.startsWith('blob:') && img.naturalWidth > 50 && !/AI generated/i.test(img.alt || ''))
    ].filter(visible);
  }

  async function dedupeUploadPreviews(maxAllowed = 1) {
    const previews = uploadPreviewImages();
    if (previews.length > maxAllowed) {
      log(`deduping ${previews.length} upload previews, keeping last ${maxAllowed}`);
      // Remove excess previews by clicking their delete/close buttons
      const excess = previews.slice(0, previews.length - maxAllowed);
      for (const preview of excess) {
        const closeBtn = preview.querySelector('button[aria-label*="Remove" i], button[aria-label*="Delete" i], button[aria-label*="Xóa" i], button[aria-label*="close" i]')
          || preview.closest('[data-test-id="uploaded-img"]')?.querySelector('button')
          || preview.parentElement?.querySelector('button');
        if (closeBtn) { realClick(closeBtn); await sleep(200); }
      }
    }
    return previews.slice(-maxAllowed);
  }

  // ===== Page-world fetch/XHR monitor (Gemini-specific: content-push.googleapis.com) =====
  // v0.3.1 XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX CSP-safe: load monitor as external file via web_accessible_resources.
  function installNetworkMonitor() {
    try {
      if (window.__db9MonitorInjected) return;
      window.__db9MonitorInjected = true;
      const s = document.createElement('script');
      s.src = chrome.runtime.getURL('content/injected-monitor-gemini.js');
      s.onload = () => { try { s.remove(); } catch (e) {} };
      s.onerror = (e) => console.warn('[DB9-Gemini] monitor script failed to load', e);
      (document.head || document.documentElement).appendChild(s);
    } catch (e) {
      console.warn('[DB9-Gemini] failed to inject page-world monitor', e);
    }
  }

  // CSP-safe probe: dispatch a request event; page-world listener replies.
  async function getUploadMonitorState() {
    return new Promise((resolve) => {
      try {
        const id = 'db9-probe-' + Math.random().toString(36).slice(2);
        const handler = (ev) => {
          if (!ev.detail || ev.detail.id !== id) return;
          window.removeEventListener('db9-probe-result', handler);
          resolve({ ok: !!ev.detail.ok, hasFileInput: !!ev.detail.hasFileInput });
        };
        window.addEventListener('db9-probe-result', handler);
        window.dispatchEvent(new CustomEvent('db9-probe-request', { detail: { id } }));
        setTimeout(() => { try { window.removeEventListener('db9-probe-result', handler); } catch (e) {} resolve({ ok: false, hasFileInput: false }); }, 250);
      } catch (e) { resolve({ ok: false, hasFileInput: false }); }
    });
  }

  async function getUploadMonitorOk() {
    const s = await getUploadMonitorState();
    return s.ok;
  }

  // ===== Native file input setter (Angular-safe) =====
  function setNativeFiles(fileInput, fileList) {
    try {
      const proto = Object.getPrototypeOf(fileInput);
      const desc = Object.getOwnPropertyDescriptor(proto, 'files') ||
                   Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'files');
      if (desc && typeof desc.set === 'function') {
        desc.set.call(fileInput, fileList);
      } else {
        fileInput.files = fileList;
      }
    } catch (e) {
      try { fileInput.files = fileList; } catch (_) {}
    }
    try { fileInput.dispatchEvent(new Event('input', { bubbles: true, composed: true })); } catch (e) {}
    try { fileInput.dispatchEvent(new Event('change', { bubbles: true, composed: true })); } catch (e) {}
  }

  // ===== Primitive actions =====
  async function humanType(el, text) {
    el.focus();
    document.execCommand && document.execCommand('insertText', false, text);
    if ((el.textContent || '').indexOf(text) === -1) {
      el.textContent = text;
      el.dispatchEvent(new InputEvent('input', { bubbles: true, data: text }));
    }
    await sleep(rand(150, 300));
  }

  async function startNewChat() {
    const btn = newChatButton();
    if (btn) {
      btn.click();
      await sleep(800);
      log('new chat started');
    } else {
      log('new chat button not found, reloading page');
      await sleep(500);
    }
  }

  async function toggleCreateImage() {
    const active = isCreateImageActive();
    if (active) { log('create image already active'); return; }
    let btn = createImageToggle();
    if (!btn) {
      const tools = toolsButton();
      if (tools) {
        realClick(tools);
        await sleep(350);
        btn = createImageToggle();
      }
    }
    if (btn) {
      realClick(btn);
      await sleep(500);
      log('create image toggled');
    } else {
      log('create image toggle button not found');
    }
  }

  function base64ToFile(base64, mime) {
    const byteString = atob(base64);
    const bytes = new Uint8Array(byteString.length);
    for (let i = 0; i < byteString.length; i++) bytes[i] = byteString.charCodeAt(i);
    const blob = new Blob([bytes], { type: mime || 'image/png' });
    return new File([blob], `db9-${Date.now()}.png`, { type: mime || 'image/png' });
  }

  // v0.4.1: expanded file-input scan (Angular cdk-overlay-container + polling)
  function findFileInput() {
    // Try multiple selector strategies across document AND any overlay containers
    const selectorList = [
      'mat-menu-content input[type="file"]',
      '.cdk-overlay-container input[type="file"]',
      '[role="menu"] input[type="file"]',
      '[role="dialog"] input[type="file"]',
      '[role="listbox"] input[type="file"]',
      'body > div input[type="file"]',
      'input[type="file"]'
    ];
    const seen = new Set();
    const found = [];
    for (const sel of selectorList) {
      try {
        qAllDeep(sel).forEach(el => {
          if (!seen.has(el)) { seen.add(el); found.push(el); }
        });
      } catch (e) {}
    }
    if (found.length === 0) return null;

    // Filter: prefer inputs whose `accept` allows images (or has no accept at all).
    // Gemini typically visually hides the input (display:none / offsetParent null)
    // but the native setter still works XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX so offsetParent is NOT a disqualifier.
    const scored = found.map(el => {
      const accept = (el.getAttribute('accept') || '').toLowerCase();
      let score = 0;
      if (!accept) score += 1;
      if (/image|\*\/\*|png|jpeg|jpg|webp/.test(accept)) score += 3;
      if (el.multiple) score += 1;
      // Prefer the most recently added (Angular usually appends fresh inputs)
      return { el, score };
    });
    scored.sort((a, b) => b.score - a.score);
    return scored[0].el;
  }

  // Upload primary method: open menu -> click Upload files -> native setter on hidden input
  async function uploadViaMenu(file, base64) {
    // v0.4.7.3: use toolsButton() directly (DOM-confirmed aria-label "Nội dung tải lên và công cụ")
    // inputArea guard removed — Gemini no longer uses <chat-input> wrapper element
    log('menu path: Tools ("Nội dung tải lên và công cụ") -> "Tải tệp lên" -> native setter on hidden input');

    // 1. Find and click the Tools/Upload button (searches full document via toolsButton())
    const toolsBtn = toolsButton();

    if (toolsBtn) {
      log('Clicking tools button: ' + (toolsBtn.getAttribute('aria-label') || toolsBtn.innerText.trim()));
      realClick(toolsBtn);
      await sleep(500);
    } else {
      log('Tools button not found, checking if upload menu is already open...');
    }

    // 2. Scan for "Upload images & files" (Tải tệp lên) item inside the entire document (since overlay menus are attached to body)
    // We poll for up to 1.5s in case of anims
    let uploadItem = null;
    const menuStart = Date.now();
    while (Date.now() - menuStart < 1500) {
      uploadItem = qDeep('[data-test-id="uploader-images-files-button-advanced"]')
        || qDeep('[data-test-id="local-images-files-uploader-button"]')
        || qDeep('[data-test-id*="uploader-images"]')
        || qDeep('[data-test-id*="local-images"]')
        || qAllDeep('span.menu-text.gem-menu-item-label, div.label.gem-menu-item-label, button, [role="menuitem"], toolbox-drawer-item button, [role="menuitem"] span, .mdc-list-item__primary-text').find((el) =>
          textMatches(el, ['Upload', 'Tai len', 'Tải tệp lên', 'Tải lên'])
        );
      if (uploadItem) break;
      await sleep(100);
    }

    if (uploadItem) {
      log('Found upload menu item, checking for direct input or clicking...');
      
      // Upgrade: ascend to the actual clickable button/menuitem container to ensure event handler hits
      let clickable = uploadItem;
      const parentBtn = uploadItem.closest('button, [role="menuitem"], [role="button"], toolbox-drawer-item');
      if (parentBtn) {
        clickable = parentBtn;
      }

      const directInput = qDeep('input[type="file"]', clickable) || qDeep('input', clickable);
      if (directInput) {
        const dt = new DataTransfer();
        dt.items.add(file);
        setNativeFiles(directInput, dt.files);
        log('direct file input found inside upload item');
        return true;
      }
      realClick(clickable);
      await sleep(500);
    } else {
      log('Upload menu item ("Tải tệp lên") not found after waiting 1.5s');
    }

    // 3. Poll for page-world file input up to 5s
    let captured = false;
    const deadline = Date.now() + 5000;
    while (Date.now() < deadline) {
      const state = await getUploadMonitorState();
      if (state.hasFileInput) {
        captured = true;
        break;
      }
      await sleep(120);
    }
    
    if (captured) {
      window.dispatchEvent(new CustomEvent('db9-inject-file-base64', {
        detail: { base64: base64, mime: file.type, filename: file.name }
      }));
      log('file injected via page-world base64 event');
      return true;
    }

    // 4. Fallback to DOM search if page-world didn't catch it
    let fileInput = findFileInput();
    if (!fileInput) {
      log('no <input type="file"> found after 5s polling');
      return false;
    }

    const dt = new DataTransfer();
    dt.items.add(file);
    setNativeFiles(fileInput, dt.files);
    log('file injected via native setter on ' + (fileInput.id || fileInput.name || '<unnamed input>'));
    return true;
  }

  async function uploadImage(base64, mime) {
    // v0.4.7.1: SEQUENTIAL XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX try one method, wait, only fallback if upload NOT confirmed.
    // Avoids "7 candidates" duplicate uploads.
    const input = promptInput();
    if (!input) throw new Error('prompt input not found');
    input.focus();
    await sleep(150);

    try { window.dispatchEvent(new CustomEvent('db9-reset-upload')); } catch (e) {}
    try { window.dispatchEvent(new CustomEvent('db9-automation-start')); } catch (e) {}
    
    const file = base64ToFile(base64, mime);

    try {
      // METHOD 3 first (recorder-validated path) XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX clean & deterministic
      try {
        const ok = await uploadViaMenu(file, base64);
        if (ok) {
          // wait long enough to let the upload network round-trip
          for (let i = 0; i < 16; i++) {
            await sleep(300);
            if (await quickPreviewCheck()) {
              await dedupeUploadPreviews(1);
              log('upload confirmed via menu method');
              return;
            }
          }
        }
      } catch (e) { log('method 3 threw: ' + e.message); }

      // FALLBACK: paste (only if method 3 failed to confirm)
      log('method 3 failed or no preview, falling back to clipboard paste');
      try {
        const dt1 = new DataTransfer();
        dt1.items.add(file);
        const evt = new ClipboardEvent('paste', { bubbles: true, cancelable: true, composed: true });
        Object.defineProperty(evt, 'clipboardData', { value: dt1 });
        input.dispatchEvent(evt);
        log('paste event dispatched');
        for (let i = 0; i < 12; i++) {
          await sleep(300);
          if (await quickPreviewCheck()) {
            await dedupeUploadPreviews(1);
            log('upload confirmed via paste method');
            return;
          }
        }
      } catch (e) { log('paste threw: ' + e.message); }

      log('all upload methods failed, waiting for waitForUploadPreview');
      // IF nothing worked, we still do a final wait, which will throw if missing
      await waitForUploadPreview(30000);
    } finally {
      try { window.dispatchEvent(new CustomEvent('db9-automation-end')); } catch (e) {}
    }
  }

  async function quickPreviewCheck() {
    if (await getUploadMonitorOk()) return true;
    const found = uploadPreviewImages();
    return found.length > 0;
  }

  async function waitForUploadPreview(timeoutMs = 30000) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      if (await getUploadMonitorOk()) {
        log('upload confirmed via network monitor');
        return true;
      }
      const candidates = [
        ...qAll('uploader-file-preview, .file-preview-chip, .uploader-file-preview-container, [data-test-id="uploaded-img"]').filter(visible),
        ...qAll('img').filter(i => visible(i) && /uploaded image preview|upload/i.test(i.alt || '')),
        ...qAll('[data-test-id*="upload"], [aria-label*="uploaded" i], [class*="upload-preview"]').filter(visible),
        ...qAll('img').filter(i => visible(i) && i.src.startsWith('blob:') && i.naturalWidth > 50 && !/AI generated/i.test(i.alt || ''))
      ];
      if (candidates.length > 0) {
        log('upload preview element detected in DOM');
        return true;
      }
      await sleep(500);
    }
    throw new Error('upload preview not detected within ' + (timeoutMs / 1000) + 's');
  }

  async function submitPrompt(promptText) {
    const input = promptInput();
    if (!input) throw new Error('prompt input not found');
    await humanType(input, promptText);
    await sleep(rand(400, 800));

    const btn = sendButton();
    if (btn && !btn.disabled) {
      realClick(btn);
      log('submit clicked');
      return;
    }
    input.focus();
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true }));
    input.dispatchEvent(new KeyboardEvent('keypress', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true }));
    input.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true }));
    log('submit via Enter key');
  }
  async function waitForOutput(baselineCount, timeoutMs = 420000) {
    const start = Date.now();
    const baselineOutputs = new Set([...generatedImages(), ...generatedVideos()].map(outputKey));
    let firstImageSeenAt = 0;
    let lastArea = 0;
    let stableCount = 0;
    let lastWaitLog = 0;
    while (Date.now() - start < timeoutMs) {
      const videos = generatedVideos().filter((video) => !baselineOutputs.has(outputKey(video)));
      if (videos.length) {
        const bestVideo = videos[videos.length - 1];
        log('got generated video output');
        return bestVideo;
      }

      const imgs = generatedImages();
      if (Date.now() - lastWaitLog > 10000) {
        lastWaitLog = Date.now();
        log('waiting for generated output: images=' + imgs.length + ', videos=' + generatedVideos().length + ', baseline images=' + baselineCount);
      }
      const newImgs = imgs.filter((img) => !baselineImageKeys.has(imageKey(img)) && !baselineOutputs.has(outputKey(img)));
      if (newImgs.length > 0 || imgs.length > baselineCount) {
        if (!firstImageSeenAt) {
          firstImageSeenAt = Date.now();
          log('first image appeared, waiting for full media to load');
        }
        const newOnes = newImgs.length > 0 ? newImgs : imgs.slice(baselineCount);
        const best = newOnes.sort((a, b) => (b.naturalWidth * b.naturalHeight) - (a.naturalWidth * a.naturalHeight))[0];
        const area = best.naturalWidth * best.naturalHeight;
        if (area > lastArea) {
          lastArea = area;
          stableCount = 0;
          log(`image loading ${best.naturalWidth}x${best.naturalHeight}`);
        } else if (area === lastArea && area > 0) {
          stableCount++;
        }
        const hdEnough = (best.naturalWidth >= 1024 && best.naturalHeight >= 1024);
        const stableWaited = stableCount >= 3;
        const longWaited = firstImageSeenAt && (Date.now() - firstImageSeenAt > 8000);
        if (stableWaited || longWaited || hdEnough) {
          log(`got generated image ${best.naturalWidth}x${best.naturalHeight}`);
          return best;
        }
      }
      await sleep(1000);
    }
    throw new Error('no generated image/video within ' + (timeoutMs / 1000) + 's');
  }

  async function downloadHD(mediaEl) {
    if ((mediaEl.tagName || '').toLowerCase() === 'video') {
      let targetSrc = mediaEl.currentSrc || mediaEl.src;
      if (!targetSrc) {
        const source = mediaEl.querySelector('source[src]');
        targetSrc = source && source.src;
      }
      if (!targetSrc) throw new Error('generated video has no downloadable src');
      const resp = await fetch(targetSrc);
      if (!resp.ok) throw new Error('video download HTTP ' + resp.status);
      const blob = await resp.blob();
      return await blobToBase64(blob, blob.type || 'video/mp4');
    }

    let targetSrc = mediaEl.currentSrc || mediaEl.src;
    if (/googleusercontent\.com\//.test(targetSrc) && /=[swh]\d+/.test(targetSrc)) {
      targetSrc = targetSrc.replace(/=[swh]\d+[^?&]*/g, '=s0');
      log('stripped size suffix');
    }

    const resp = await fetch(targetSrc);
    if (!resp.ok) throw new Error('image download HTTP ' + resp.status);
    const blob = await resp.blob();
    return await blobToBase64(blob, blob.type || 'image/png');
  }

  async function blobToTransparentPngBase64(blob) {
    return await blobToBase64(blob, blob.type || 'image/png');
  }

  async function blobToBase64(blob, forcedMime) {
    return await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => {
        const dataUrl = String(reader.result || '');
        const base64 = dataUrl.split(',')[1] || '';
        resolve({ base64, mime: forcedMime || blob.type || 'application/octet-stream' });
      };
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  }
  function countBaseline() {
    const images = generatedImages();
    const videos = generatedVideos();
    baselineImageKeys = new Set(images.map(imageKey));
    log(`baseline: ${images.length} generated images, ${videos.length} generated videos`);
    return images.length + videos.length;
  }

  async function ensureCloseImageViewer() {
    try {
      const backBtn = qDeep('button[aria-label*="Back" i]')
        || qDeep('button[aria-label*="Quay lại" i]')
        || qDeep('button[aria-label*="Close" i]')
        || qDeep('button[aria-label*="Đóng" i]')
        || qDeep('button[aria-label*="close" i]')
        || qAllDeep('button').find(b => {
          const icon = b.querySelector('mat-icon');
          const name = icon?.getAttribute('data-mat-icon-name') || icon?.textContent || '';
          return /arrow_back|close/i.test(name) || textMatches(b, ['arrow_back', 'close', 'quay lai', 'dong']);
        });

      const viewerActive = qDeep('.immersive-viewer, [class*="immersive"], [class*="viewer-container"], [class*="lightbox"]');

      if (backBtn && (viewerActive || visible(backBtn))) {
        log('Immersive image viewer detected. Clicking back button to return to chat...');
        realClick(backBtn);
        await sleep(1200);
      }
    } catch (e) {
      log('ensureCloseImageViewer error: ' + e.message);
    }
  }

  async function waitReady(timeoutMs = 10000) {
    await ensureCloseImageViewer();
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      if (promptInput()) return true;
      await sleep(500);
    }
    return false;
  }

  window.__DB9_PROVIDER = {
    name: 'gemini',
    promptInput,
    installNetworkMonitor,
    getUploadMonitorOk,
    startNewChat,
    toggleCreateImage,
    uploadImage,
    waitForUploadPreview,
    submitPrompt,
    waitForOutput,
    downloadHD,
    countBaseline,
    waitReady,
  };

  log('provider module loaded');
  } catch (err) {
    console.error('[DB9-Gemini] FATAL ERROR IN PROVIDER INIT:', err);
  }
})();
