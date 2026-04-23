// DB9 Multi-Provider — Gemini provider module
// Loaded first on https://gemini.google.com/*, BEFORE content-script.js.
// Exposes window.__DB9_PROVIDER = { name, selectors, submitPrompt, uploadImage,
// waitForOutput, downloadHD, toggleCreateImage, startNewChat, promptInput,
// installNetworkMonitor, getUploadMonitorOk } — the shared orchestrator in
// content-script.js calls into this object so the same run-loop works for
// every provider.
//
// All selectors here are the ones that were verified working through v0.2.1
// on Gemini's Angular UI. Do not change them without re-testing Gemini.

(() => {
  if (window.__DB9_PROVIDER && window.__DB9_PROVIDER.name === 'gemini') return;

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
    return document.querySelector(
      'button[aria-label*="Send message" i], ' +
      'button[aria-label*="Submit" i], ' +
      'button[aria-label="Send"]'
    );
  }

  function newChatButton() {
    return [...document.querySelectorAll('button,a')].find(b =>
      /new chat/i.test(b.getAttribute('aria-label') || b.textContent || '')
    );
  }

  function downloadButtons() {
    return qAll('button[aria-label*="Download full size image" i]').filter(visible);
  }

  function generatedImages() {
    return qAll('img').filter(i =>
      visible(i) && /AI generated/i.test(i.alt || '') && i.naturalWidth > 200
    );
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
    return qDeep('button[aria-label="Tools"]')
        || qDeep('button[aria-label*="Tools" i]')
        || qAllDeep('button,[role="button"]').find((el) =>
          textMatches(el, ['Tools'])
        );
  }

  function uploadPreviewImages() {
    return qAll('img').filter((img) =>
      visible(img) &&
      img.src.startsWith('blob:') &&
      img.naturalWidth > 50 &&
      !/AI generated/i.test(img.alt || '')
    );
  }

  async function dedupeUploadPreviews(maxAllowed = 1) {
    const previews = uploadPreviewImages();
    if (previews.length > maxAllowed) {
      log(`⚠ upload preview duplicated (${previews.length}), continuing with newest preview`);
    }
    return previews.slice(-maxAllowed);
  }

  // ===== Page-world fetch/XHR monitor (Gemini-specific: content-push.googleapis.com) =====
  // v0.3.1 — CSP-safe: load monitor as external file via web_accessible_resources.
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
  async function getUploadMonitorOk() {
    return new Promise((resolve) => {
      try {
        const id = 'db9-probe-' + Math.random().toString(36).slice(2);
        const handler = (ev) => {
          if (!ev.detail || ev.detail.id !== id) return;
          window.removeEventListener('db9-probe-result', handler);
          resolve(!!ev.detail.ok);
        };
        window.addEventListener('db9-probe-result', handler);
        window.dispatchEvent(new CustomEvent('db9-probe-request', { detail: { id } }));
        setTimeout(() => { try { window.removeEventListener('db9-probe-result', handler); } catch (e) {} resolve(false); }, 250);
      } catch (e) { resolve(false); }
    });
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
      log('▶️ started new chat');
    } else {
      log('⚠ new chat button not found, trying URL navigation');
      location.href = 'https://gemini.google.com/app';
      await sleep(2500);
    }
  }

  async function toggleCreateImage() {
    const active = isCreateImageActive();
    if (active) { log('✓ Create image mode already on'); return; }
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
      log('✓ enabled Create image mode');
    } else {
      log('⚠ Create image toggle not found (may be auto-detect on image input)');
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
    // but the native setter still works — so offsetParent is NOT a disqualifier.
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

  // Upload primary method: open menu → click Upload files → native setter on hidden input
  async function uploadViaMenu(file) {
    // v0.4.7.1: recorder path + REAL MouseEvent clicks + longer poll + multiple file-input re-scan
    log('📎 menu path: Tools → Open upload file menu → Upload images & files');

    // 1. Tools button — may already be expanded; try anyway
    const toolsBtn = toolsButton();
    if (toolsBtn) { realClick(toolsBtn); await sleep(400); }

    // 2. Open upload file menu
    const openUpload = qDeep('[aria-label="Open upload file menu" i]')
      || qDeep('button[aria-label*="upload" i][aria-label*="menu" i]')
      || qDeep('uploader button');
    if (openUpload) { realClick(openUpload); await sleep(500); }
    else { log('⚠ "Open upload file menu" not found'); }

    // 3. Click "Upload images & files"
    const uploadItem = qDeep('[data-test-id="uploader-images-files-button-advanced"]')
      || qDeep('[data-test-id="local-images-files-uploader-button"]')
      || qDeep('[data-test-id*="uploader-images"]')
      || qDeep('[data-test-id*="local-images"]')
      || qAllDeep('button,[role="menuitem"],toolbox-drawer-item button').find((el) =>
        textMatches(el, ['Upload files', 'Upload images', 'Tai len tep', 'Tai len anh'])
      );
    if (uploadItem) {
      const directInput = qDeep('input[type="file"]', uploadItem) || qDeep('input', uploadItem);
      if (directInput) {
        const dt = new DataTransfer();
        dt.items.add(file);
        setNativeFiles(directInput, dt.files);
        log('📎 direct file input found inside upload item');
        return true;
      }
      realClick(uploadItem);
      await sleep(500);
    }

    // 4. Poll for file input up to 5s — Angular injects into cdk-overlay/shadow late
    let fileInput = null;
    const deadline = Date.now() + 5000;
    while (Date.now() < deadline) {
      fileInput = findFileInput();
      if (fileInput) break;
      await sleep(120);
    }
    if (!fileInput) {
      log('⚠ no <input type="file"> found after 5s polling (including shadow roots)');
      return false;
    }

    const dt = new DataTransfer();
    dt.items.add(file);
    setNativeFiles(fileInput, dt.files);
    log('📎 file injected via native setter on ' + (fileInput.id || fileInput.name || '<unnamed input>'));
    return true;
  }

  async function uploadImage(base64, mime) {
    // v0.4.7.1: SEQUENTIAL — try one method, wait, only fallback if upload NOT confirmed.
    // Avoids "7 candidates" duplicate uploads.
    const input = promptInput();
    if (!input) throw new Error('prompt input not found');
    input.focus();
    await sleep(150);

    try { window.dispatchEvent(new CustomEvent('db9-reset-upload')); } catch (e) {}
    const file = base64ToFile(base64, mime);

    // METHOD 3 first (recorder-validated path) — clean & deterministic
    try {
      const ok = await uploadViaMenu(file);
      if (ok) {
        // wait long enough to let the upload network round-trip
        for (let i = 0; i < 16; i++) {
          await sleep(300);
          if (await quickPreviewCheck()) {
            await dedupeUploadPreviews(1);
            log('✓ upload confirmed via menu+native');
            return;
          }
        }
      }
    } catch (e) { log('method 3 threw: ' + e.message); }

    // FALLBACK: paste (only if method 3 failed to confirm)
    log('⚠ method 3 not confirmed — trying paste fallback');
    try {
      const dt1 = new DataTransfer();
      dt1.items.add(file);
      const evt = new ClipboardEvent('paste', { bubbles: true, cancelable: true, composed: true });
      Object.defineProperty(evt, 'clipboardData', { value: dt1 });
      input.dispatchEvent(evt);
      log('📎 paste dispatched');
      for (let i = 0; i < 12; i++) {
        await sleep(300);
        if (await quickPreviewCheck()) {
          await dedupeUploadPreviews(1);
          log('✓ upload confirmed via paste fallback');
          return;
        }
      }
    } catch (e) { log('paste threw: ' + e.message); }

    log('⚠ all upload methods exhausted, will wait for monitor');
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
        log('✓ upload confirmed by page-world fetch/XHR monitor');
        return true;
      }
      const candidates = [
        ...qAll('img').filter(i => visible(i) && /uploaded image preview|upload/i.test(i.alt || '')),
        ...qAll('[data-test-id*="upload"], [aria-label*="uploaded" i], [class*="upload-preview"]').filter(visible),
        ...qAll('img').filter(i => visible(i) && i.src.startsWith('blob:') && i.naturalWidth > 50 && !/AI generated/i.test(i.alt || ''))
      ];
      if (candidates.length > 0) {
        log(`✓ upload preview detected (${candidates.length} candidates)`);
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
      btn.click();
      log('▶️ submit clicked');
      return;
    }
    input.focus();
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    log('▶️ submit via Enter key');
  }

  async function waitForOutput(baselineCount, timeoutMs = 180000) {
    // v0.4.7.1: wait for HD — poll until image res stabilizes (no growth for 3 consecutive checks)
    const start = Date.now();
    let firstSeenAt = 0;
    let lastArea = 0;
    let stableCount = 0;
    while (Date.now() - start < timeoutMs) {
      const imgs = generatedImages();
      if (imgs.length > baselineCount) {
        if (!firstSeenAt) {
          firstSeenAt = Date.now();
          log('▶️ first image appeared, waiting for HD to load...');
        }
        const newOnes = imgs.slice(baselineCount);
        const best = newOnes.sort((a, b) => (b.naturalWidth * b.naturalHeight) - (a.naturalWidth * a.naturalHeight))[0];
        const area = best.naturalWidth * best.naturalHeight;
        if (area > lastArea) {
          lastArea = area;
          stableCount = 0;
          log(`  ⏳ loading ${best.naturalWidth}x${best.naturalHeight}...`);
        } else if (area === lastArea && area > 0) {
          stableCount++;
        }
        // Accept when: stable for 3 polls OR waited 8s since first-seen OR already at >= 1024x1024
        const hdEnough = (best.naturalWidth >= 1024 && best.naturalHeight >= 1024);
        const stableWaited = stableCount >= 3;
        const longWaited = firstSeenAt && (Date.now() - firstSeenAt > 8000);
        if (stableWaited || longWaited || hdEnough) {
          log(`✅ got generated image ${best.naturalWidth}x${best.naturalHeight}`);
          return best;
        }
      }
      await sleep(1000);
    }
    throw new Error('no generated image within ' + (timeoutMs / 1000) + 's');
  }

  async function downloadHD(imgEl) {
    // v0.4.7.1: use REAL "Download generated image" button from recorder
    // data-test-id="download-generated-image-button" triggers native download of full-res image
    let targetSrc = imgEl.src;

    // Try: find the download button associated with this image, click it, intercept blob
    try {
      // Find any visible download-generated-image-button
      const dlBtn = document.querySelector('[data-test-id="download-generated-image-button"]')
        || document.querySelector('button[aria-label*="Download" i][aria-label*="image" i]');
      if (dlBtn) {
        // Intercept: monkey-patch <a>.click() to capture the object URL before download triggers
        let capturedUrl = null;
        const origCreate = URL.createObjectURL;
        URL.createObjectURL = function(obj) {
          const url = origCreate.apply(this, arguments);
          try { if (obj instanceof Blob) capturedUrl = url; } catch (e) {}
          return url;
        };
        try { dlBtn.click(); } catch (e) {}
        await sleep(600);
        URL.createObjectURL = origCreate;
        if (capturedUrl) {
          log('  ✓ captured download blob URL');
          const resp = await fetch(capturedUrl);
          const blob = await resp.blob();
          return await blobToBase64(blob);
        }
      }
    } catch (e) { log('  ⚠ download-button path: ' + e.message); }

    // Fallback: open lightbox, grab biggest <img>
    try {
      imgEl.scrollIntoView({ block: 'center' });
      imgEl.click();
      await sleep(700);
      const lbImgs = Array.from(document.querySelectorAll('[role="dialog"] img, .lightbox img, .image-viewer img'))
        .filter(i => i.naturalWidth > 512);
      if (lbImgs.length) {
        const big = lbImgs.sort((a,b) => (b.naturalWidth*b.naturalHeight) - (a.naturalWidth*a.naturalHeight))[0];
        if (big.naturalWidth > imgEl.naturalWidth) {
          targetSrc = big.src;
          log('  ✓ lightbox HD: ' + big.naturalWidth + 'x' + big.naturalHeight);
        }
      }
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      await sleep(200);
    } catch (e) {}

    // Strip size suffix
    if (/googleusercontent\.com\//.test(targetSrc) && /=[swh]\d+/.test(targetSrc)) {
      targetSrc = targetSrc.replace(/=[swh]\d+[^?&]*/g, '=s0');
      log('  ✓ stripped size suffix');
    }

    const resp = await fetch(targetSrc);
    const blob = await resp.blob();
    return await blobToBase64(blob);
  }

  async function blobToBase64(blob) {
    return await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => {
        const dataUrl = reader.result;
        const base64 = dataUrl.split(',')[1];
        resolve({ base64, mime: blob.type || 'image/png' });
      };
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  }

  function countBaseline() { return generatedImages().length; }

  async function waitReady(timeoutMs = 10000) {
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
})();
