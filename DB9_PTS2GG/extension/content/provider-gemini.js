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

  function hasAllText(el, tokens) {
    const hay = textOf(el);
    return tokens.every((token) => hay.includes(normalizeText(token)));
  }
  function isUploadText(el) {
    const hay = textOf(el);
    return hay.includes('upload') || hay.includes('file') || hay.includes('tep') || hay.includes('tệp') || (hay.includes('tai') && hay.includes('len')) || (hay.includes('tải') && hay.includes('lên'));
  }
  function scoreUploadCandidate(el) {
    if (!el || !visible(el)) return -1;
    const text = textOf(el);
    const isExcluded = /drive|photo|notebook|setting|cai dat|google|anh/i.test(text);
    if (isExcluded) return -1;

    let score = 0;
    if (text.includes('tai tep len') || text.includes('tải tệp lên') || text.includes('upload file') || text.includes('upload images & files')) {
      score += 100;
    } else if (text.includes('tai len') || text.includes('tải lên') || text.includes('upload')) {
      score += 80;
    } else if (text.includes('tep') || text.includes('tệp') || text.includes('file')) {
      score += 50;
    } else if (isUploadText(el)) {
      score += 30;
    }

    const tagName = (el.tagName || '').toLowerCase();
    const role = el.getAttribute('role') || '';
    if (tagName === 'button' || role === 'button' || role === 'menuitem') {
      score += 20;
    }

    return score;
  }
  function isToolsText(el) {
    const hay = textOf(el);
    return hay.includes('upload and tools') || hay.includes('tools') || hay.includes('noi dung') || hay.includes('nội dung') || (hay.includes('tai') && hay.includes('cong cu')) || (hay.includes('tải') && hay.includes('công cụ'));
  }
  const log = (text) => {
    console.log('[DB9-Gemini]', text);
    try { chrome.runtime.sendMessage({ type: 'log', text: '[gemini] ' + text }); } catch (e) {}
  };

  const reportProgress = (status, percent, details = '') => {
    const jobId = window.__DB9_PROVIDER?.activeJobId;
    if (!jobId) return;
    try {
      chrome.runtime.sendMessage({
        type: 'job-progress',
        jobId: jobId,
        status: status,
        progress: percent,
        details: details
      });
    } catch (e) {}
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
      'button[aria-label*="GÃƒÆ’Ã‚Â¡Ãƒâ€šÃ‚Â»Ãƒâ€šÃ‚Â­i tin nhÃƒÆ’Ã‚Â¡Ãƒâ€šÃ‚ÂºÃƒâ€šÃ‚Â¯n" i], ' +
      'button[data-test-id="send-button"], ' +
      'button[data-test-id*="send" i], ' +
      'button[data-test-id*="submit" i], ' +
      'button:has(mat-icon[data-mat-icon-name="arrow_upward"]), ' +
      '[data-mat-icon-name="arrow_upward"]'
    ) || qAllDeep('button,[role="button"]').find((el) =>
      textMatches(el, ['Send', 'Gui', 'Submit', 'Run', 'GÃƒÆ’Ã‚Â¡Ãƒâ€šÃ‚Â»Ãƒâ€šÃ‚Â­i']) && !el.disabled
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
      
      // BUG-102 FIX: Exclude upload preview images
      // Upload previews are inside xap-file-selector, .input-preview, or uploader-file-preview containers, or have specific alt text
      const isUploadAlt = /bản xem trước hình ảnh|uploaded image|upload preview|tai len|upload|xem truoc/i.test(alt.toLowerCase());
      const parent = img.closest('xap-file-selector, xap-file-preview, xap-uploaded-file, .input-preview, .uploader-file-preview, .thumbnail-container, .image-thumbnail, [class*="upload"], [class*="preview"]');
      if (isUploadAlt || parent || (src.startsWith('blob:') && alt.includes('tải lên'))) {
        console.log('[DB9] BUG-102 FIX: Excluding upload preview image:', src.substring(0, 60), 'alt:', alt);
        return false;
      }
      
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
    return qDeep('button[aria-label*="upload and tools" i]')
        || qDeep('button[aria-label="Tools"]')
        || qDeep('button[aria-label*="Open tools" i]')
        || qAllDeep('button,[role="button"]').find((el) => isToolsText(el) || textMatches(el, ['+']));
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
        const cleanup = () => {
          try { document.removeEventListener('db9-probe-result', domHandler); } catch (e) {}
          try { window.removeEventListener('message', messageHandler); } catch (e) {}
        };
        const done = (detail) => {
          cleanup();
          resolve({
            ok: !!detail.ok,
            hasFileInput: !!detail.hasFileInput,
            automationActive: !!detail.automationActive,
            stagedFile: !!detail.stagedFile,
            lastUploadAt: detail.lastUploadAt || 0
          });
        };
        const domHandler = (ev) => {
          if (!ev.detail || ev.detail.id !== id) return;
          done(ev.detail);
        };
        const messageHandler = (ev) => {
          const data = ev.data || {};
          if (data.source !== 'db9-monitor' || data.type !== 'db9-probe-result') return;
          if (!data.detail || data.detail.id !== id) return;
          done(data.detail);
        };
        document.addEventListener('db9-probe-result', domHandler);
        window.addEventListener('message', messageHandler);
        document.dispatchEvent(new CustomEvent('db9-probe-request', { detail: { id } }));
        window.postMessage({ source: 'db9-extension', type: 'db9-probe-request', id }, '*');
        setTimeout(() => { cleanup(); resolve({ ok: false, hasFileInput: false, automationActive: false, stagedFile: false }); }, 500);
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

  function editorPlainText(el) {
    return String(el?.innerText || el?.textContent || '').replace(/\s+/g, ' ').trim();
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

  // Upload method: drag & drop directly onto the prompt input area
  // Confirmed working on Gemini VN UI 2026-05-28 (manual drag & drop accepted)
  async function uploadViaDragDrop(file) {
    const dropTarget = qDeep('rich-textarea, div[contenteditable="true"]') || promptInput();
    if (!dropTarget) { log('drag-drop: no drop target found'); return false; }

    try {
      const dt = new DataTransfer();
      dt.items.add(file);

      const rect = dropTarget.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      const evtOpts = { bubbles: true, cancelable: true, composed: true, clientX: cx, clientY: cy };

      dropTarget.dispatchEvent(new DragEvent('dragenter', { ...evtOpts, dataTransfer: dt }));
      await sleep(80);
      dropTarget.dispatchEvent(new DragEvent('dragover',  { ...evtOpts, dataTransfer: dt }));
      await sleep(80);
      dropTarget.dispatchEvent(new DragEvent('drop',      { ...evtOpts, dataTransfer: dt }));
      await sleep(200);
      dropTarget.dispatchEvent(new DragEvent('dragleave', { ...evtOpts, dataTransfer: dt }));

      log('drag-drop events dispatched onto ' + (dropTarget.tagName || 'element'));
      return true;
    } catch (e) {
      log('drag-drop failed: ' + e.message);
      return false;
    }
  }

  // Upload primary method: open menu -> click Upload files -> showOpenFilePicker intercept
  async function uploadViaMenu(file, base64) {
    reportProgress('uploading', 40, 'Staging image payload for dynamic dialog interception...');
    // v0.4.7.4: Stage file for showOpenFilePicker override BEFORE clicking menu
    log('menu path: Tools ("Nội dung tải lên và công cụ") -> "Tải tệp lên" -> showOpenFilePicker intercept');

    // Stage the file in page-world so showOpenFilePicker override can return it
    document.dispatchEvent(new CustomEvent('db9-stage-file', {
      detail: { base64: base64, mime: file.type, filename: file.name }
    }));
    try { window.postMessage({ source: 'db9-extension', type: 'db9-stage-file', detail: { base64: base64, mime: file.type, filename: file.name } }, '*'); } catch (e) {}
    log('file staged for showOpenFilePicker intercept');

    // 1. Check if the menu is already open to avoid toggling it closed
    const isMenuOpen = () => {
      return !!(
        qDeep('[data-test-id="uploader-images-files-button-advanced"]') ||
        qDeep('[data-test-id="local-images-files-uploader-button"]') ||
        qDeep('[data-test-id*="uploader-images"]') ||
        qDeep('[data-test-id*="local-images"]') ||
        qAllDeep('[role="menu"], [role="listbox"], mat-menu-content, .cdk-overlay-container, .mat-mdc-menu-panel, toolbox-drawer-item button').some(el => {
          return isUploadText(el) && visible(el);
        })
      );
    };

    reportProgress('uploading', 43, 'Opening upload panel...');

    const toolsBtn = toolsButton();
    if (isMenuOpen()) {
      log('Upload menu/tools panel is already open; skipping tools button click to avoid closing it');
    } else if (toolsBtn) {
      log('Clicking tools button to open menu: ' + (toolsBtn.getAttribute('aria-label') || toolsBtn.innerText.trim()));
      realClick(toolsBtn);
      await sleep(500);
    } else {
      log('Tools button not found, scanning for open menu...');
    }

    // 2. Scan for "Upload images & files" (Tải tệp lên) item inside the entire document (since overlay menus are attached to body)
    // We poll for up to 1.5s in case of anims
    let uploadItem = null;
    const menuStart = Date.now();
    while (Date.now() - menuStart < 1500) {
      const candidates = qAllDeep('span.menu-text.gem-menu-item-label, div.label.gem-menu-item-label, button, [role="menuitem"], toolbox-drawer-item button, [role="menuitem"] span, .mdc-list-item__primary-text')
        .map((el) => ({ el, score: scoreUploadCandidate(el) }))
        .filter(c => c.score > 0)
        .sort((a, b) => b.score - a.score);

      if (candidates.length > 0) {
        uploadItem = candidates[0].el;
        const bestScore = candidates[0].score;
        const rect = uploadItem.getBoundingClientRect();
        log(`Scored ${candidates.length} candidates. Best candidate: "${textOf(uploadItem)}" score=${bestScore} role=${uploadItem.getAttribute('role') || ''} tag=${uploadItem.tagName} coords=${Math.round(rect.left)},${Math.round(rect.top)}`);
        break;
      }
      uploadItem = qDeep('[data-test-id="uploader-images-files-button-advanced"]')
        || qDeep('[data-test-id="local-images-files-uploader-button"]')
        || qDeep('[data-test-id*="uploader-images"]')
        || qDeep('[data-test-id*="local-images"]');
      if (uploadItem) break;
      await sleep(100);
    }

    if (uploadItem) {
      log('chosen upload candidate text="' + (uploadItem.innerText || '').trim() + '" tagName=' + uploadItem.tagName + ' outerHTML=' + uploadItem.outerHTML.slice(0, 150));
      
      // Upgrade: ascend to the actual clickable button/menuitem container to ensure event handler hits
      let clickable = uploadItem;
      const parentBtn = uploadItem.closest('button, [role="menuitem"], [role="button"], toolbox-drawer-item');
      if (parentBtn) {
        clickable = parentBtn;
      }
      log('resolved clickable container tagName=' + clickable.tagName + ' outerHTML=' + clickable.outerHTML.slice(0, 150));

      const directInput = qDeep('input[type="file"]', clickable) || qDeep('input', clickable);
      if (directInput) {
        const dt = new DataTransfer();
        dt.items.add(file);
        setNativeFiles(directInput, dt.files);
        log('direct file input found inside upload item');
        return true;
      }
      log('requesting background CDP file injection on selected upload candidate');
      reportProgress('uploading', 48, 'Invoking debugger channel for programmatic file paste...');
      try {
        const clickResult = await chrome.runtime.sendMessage({ type: 'debugger-click-upload-item', provider: 'gemini' });
        if (clickResult && clickResult.ok) {
          log('background CDP file injection succeeded: ' + JSON.stringify(clickResult));
          reportProgress('uploading', 52, 'Programmatic paste executed successfully...');
        } else {
          log('background CDP file injection failed: ' + (clickResult && clickResult.error ? clickResult.error : 'unknown'));
        }
      } catch (e) {
        log('background CDP file injection message failed: ' + e.message);
      }
      await sleep(1000);
      let stateAfterTrustedClick = await getUploadMonitorState();
      log('monitor after CDP file injection: ' + JSON.stringify(stateAfterTrustedClick));

      if (!stateAfterTrustedClick.ok && !stateAfterTrustedClick.hasFileInput) {
        log('CDP file injection did not trigger picker/input; trying synthetic fallback click');
        reportProgress('uploading', 54, 'Trying synthetic DOM fallback events...');
        try { realClick(clickable); } catch (_) {}
        try { clickable.click(); } catch (_) {}
        await sleep(500);
        if (uploadItem !== clickable) {
          try { realClick(uploadItem); } catch (_) {}
          try { uploadItem.click(); } catch (_) {}
          await sleep(300);
        }
        stateAfterTrustedClick = await getUploadMonitorState();
        log('monitor after synthetic fallback click: ' + JSON.stringify(stateAfterTrustedClick));
      }
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
      reportProgress('uploading', 56, 'Bypassing frame controls to inject base64 state...');
      document.dispatchEvent(new CustomEvent('db9-inject-file-base64', {
        detail: { base64: base64, mime: file.type, filename: file.name }
      }));
      try { window.postMessage({ source: 'db9-extension', type: 'db9-inject-file-base64', detail: { base64: base64, mime: file.type, filename: file.name } }, '*'); } catch (e) {}
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

  async function uploadImage(base64, mime, baselinePreviews = null) {
    reportProgress('uploading', 30, 'Initiating canvas image reference upload...');
    
    // BUG-102 FIX: capture baseline previews and URLs at the start of uploadImage
    if (!baselinePreviews) {
      baselinePreviews = uploadPreviewImages();
    }
    const baselineUrls = new Set(baselinePreviews.map(p => p.src).filter(Boolean));
    log(`[BUG-102] uploadImage captured baseline previews count=${baselinePreviews.length}`);

    // v0.4.7.1: SEQUENTIAL XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX try one method, wait, only fallback if upload NOT confirmed.
    // Avoids "7 candidates" duplicate uploads.
    const input = promptInput();
    if (!input) throw new Error('prompt input not found');
    input.focus();
    await sleep(150);

    try { document.dispatchEvent(new CustomEvent('db9-reset-upload')); } catch (e) {}
    try { window.postMessage({ source: 'db9-extension', type: 'db9-reset-upload' }, '*'); } catch (e) {}
    try { document.dispatchEvent(new CustomEvent('db9-automation-start')); } catch (e) {}
    try { window.postMessage({ source: 'db9-extension', type: 'db9-automation-start' }, '*'); } catch (e) {}

    const file = base64ToFile(base64, mime);

    try {
      // METHOD 1: Drag & Drop (confirmed working on Gemini VN UI 2026-05-28)
      try {
        const ok = await uploadViaDragDrop(file);
        if (ok) {
          for (let i = 0; i < 20; i++) {
            await sleep(300);
            if (await quickPreviewCheck(baselinePreviews, baselineUrls)) {
              log('upload confirmed via drag-drop');
              return;
            }
          }
          log('drag-drop dispatched but no preview detected, trying next method');
        }
      } catch (e) { log('drag-drop threw: ' + e.message); }

      // METHOD 2: Menu ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ "TÃƒÆ’Ã‚Â¡Ãƒâ€šÃ‚ÂºÃƒâ€šÃ‚Â£i tÃƒÆ’Ã‚Â¡Ãƒâ€šÃ‚Â»ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¡p lÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Âªn" ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ native file input setter
      try {
        const ok = await uploadViaMenu(file, base64);
        if (ok) {
          for (let i = 0; i < 16; i++) {
            await sleep(300);
            if (await quickPreviewCheck(baselinePreviews, baselineUrls)) {
              log('upload confirmed via menu method');
              return;
            }
          }
        }
      } catch (e) { log('method menu threw: ' + e.message); }

      // METHOD 3 FALLBACK: clipboard paste
      log('menu method failed, falling back to clipboard paste');
      try {
        const dt1 = new DataTransfer();
        dt1.items.add(file);
        const evt = new ClipboardEvent('paste', { bubbles: true, cancelable: true, composed: true });
        Object.defineProperty(evt, 'clipboardData', { value: dt1 });
        input.dispatchEvent(evt);
        log('paste event dispatched');
        // Gemini processing paste takes a while, wait up to 9 seconds
        for (let i = 0; i < 30; i++) {
          await sleep(300);
          if (await quickPreviewCheck(baselinePreviews, baselineUrls)) {
            log('upload confirmed via paste method');
            return;
          }
        }
      } catch (e) { log('paste threw: ' + e.message); }

      log('all upload methods failed, waiting for waitForUploadPreview');
      await waitForUploadPreview(30000);
    } finally {
      try { document.dispatchEvent(new CustomEvent('db9-automation-end')); } catch (e) {}
      try { window.postMessage({ source: 'db9-extension', type: 'db9-automation-end' }, '*'); } catch (e) {}
    }
  }

  async function quickPreviewCheck(baselinePreviews = [], baselineUrls = new Set()) {
    if (await getUploadMonitorOk()) return true;
    const found = uploadPreviewImages();
    const newPreviews = found.filter(p => !baselinePreviews.includes(p) && !baselineUrls.has(p.src));
    return newPreviews.length > 0;
  }

  async function waitForUploadPreview(baselinePreviews = [], timeoutMs = 30000) {
    reportProgress('uploading', 62, 'Waiting for image upload confirmation...');
    if (typeof baselinePreviews === 'number') {
      timeoutMs = baselinePreviews;
      baselinePreviews = [];
    }
    if (!Array.isArray(baselinePreviews)) baselinePreviews = [];
    
    const start = Date.now();
    const baselineUrls = new Set(baselinePreviews.map(p => p.src).filter(Boolean));
    while (Date.now() - start < timeoutMs) {
      if (await getUploadMonitorOk()) {
        log('upload confirmed via network monitor');
        log('new upload confirmed key=network_monitor');
        return true;
      }
      const candidates = uploadPreviewImages();
      const newPreviews = candidates.filter(p => !baselinePreviews.includes(p) && !baselineUrls.has(p.src));
      if (newPreviews.length > 0) {
        const key = newPreviews[0].src || 'preview_img';
        log('new upload confirmed key=' + key);
        return true;
      }
      await sleep(500);
    }
    throw new Error('upload preview not detected within ' + (timeoutMs / 1000) + 's');
  }

  async function submitPrompt(promptText) {
    reportProgress('generating', 68, 'Submitting prompt parameters...');
    const input = promptInput();
    if (!input) throw new Error('prompt input not found');
    await humanType(input, promptText);
    const editorText = editorPlainText(input);
    const targetText = String(promptText || '').replace(/\s+/g, ' ').trim();
    const editorNorm = editorText.replace(/\s+/g, ' ').trim();
    const targetNeedle = targetText.slice(0, Math.min(80, targetText.length));
    if (targetText && (!editorNorm || editorNorm.length < Math.min(12, targetText.length) || (targetNeedle && !editorNorm.includes(targetNeedle)))) {
      throw new Error('prompt verification failed: editor chars=' + editorNorm.length + ' target chars=' + targetText.length);
    }
    log('prompt verified: editor chars=' + editorNorm.length + ' target chars=' + targetText.length);
    await sleep(rand(400, 800));

    const btn = sendButton();
    if (btn && !btn.disabled) {
      realClick(btn);
      log('submit clicked after upload+prompt verification');
      return;
    }
    input.focus();
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true }));
    input.dispatchEvent(new KeyboardEvent('keypress', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true }));
    input.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true }));
    log('submit clicked after upload+prompt verification');
  }
  async function waitForOutput(baselineCount, timeoutMs = 420000) {
    const start = Date.now();
    const baselineOutputs = new Set([...generatedImages(), ...generatedVideos()].map(outputKey));
    let firstImageSeenAt = 0;
    let lastArea = 0;
    let stableCount = 0;
    let lastWaitLog = 0;
    
    reportProgress('generating', 72, 'Waiting for Gemini generation...');

    while (Date.now() - start < timeoutMs) {
      const videos = generatedVideos().filter((video) => !baselineOutputs.has(outputKey(video)));
      if (videos.length) {
        const bestVideo = videos[videos.length - 1];
        log('new output detected key=' + outputKey(bestVideo));
        reportProgress('generating', 88, 'Generation output complete...');
        return bestVideo;
      }

      const imgs = generatedImages();
      
      // Dynamic details checking (CDP/DOM inspection for data analysis / sandbox run)
      const hasSandbox = document.body.innerText.includes('Đang tải') || document.body.innerText.includes('data_analysis_tool');
      if (firstImageSeenAt) {
        reportProgress('generating', 82, 'Image preview detected, waiting for full resolution...');
      } else if (hasSandbox) {
        reportProgress('generating', 78, 'Gemini sandbox: running Python code interpreter...');
      } else {
        if (Date.now() - lastWaitLog > 10000) {
          reportProgress('generating', 74, 'Gemini is synthesizing creative image variants...');
        }
      }

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
          log('new output detected key=' + outputKey(best));
          reportProgress('generating', 88, 'High-resolution render stable...');
          return best;
        }
      }
      await sleep(1000);
    }
    throw new Error('no generated image/video within ' + (timeoutMs / 1000) + 's');
  }

  async function downloadBlobViaPageWorld(blobUrl) {
    return new Promise((resolve, reject) => {
      const id = 'db9-blob-' + Math.random().toString(36).slice(2);
      let done = false;
      let timer = null;
      const cleanup = () => {
        try { document.removeEventListener('db9-download-blob-response', domHandler); } catch (e) {}
        try { window.removeEventListener('message', messageHandler); } catch (e) {}
        if (timer) clearTimeout(timer);
      };
      const finish = (detail) => {
        if (done || !detail || detail.id !== id) return;
        done = true;
        cleanup();
        if (detail.success) {
          resolve({ base64: detail.base64, mime: detail.mime });
        } else {
          reject(new Error(detail.error || 'Failed to download blob via page-world'));
        }
      };
      const domHandler = (ev) => finish(ev.detail);
      const messageHandler = (ev) => {
        const data = ev.data || {};
        if (data.source !== 'db9-monitor' || data.type !== 'db9-download-blob-response') return;
        finish(data.detail);
      };
      document.addEventListener('db9-download-blob-response', domHandler);
      window.addEventListener('message', messageHandler);
      document.dispatchEvent(new CustomEvent('db9-download-blob-request', {
        detail: { id, blobUrl }
      }));
      try { window.postMessage({ source: 'db9-extension', type: 'db9-download-blob-request', detail: { id, blobUrl } }, '*'); } catch (e) {}
      timer = setTimeout(() => {
        cleanup();
        reject(new Error('Timeout downloading blob via page-world'));
      }, 15000);
    });
  }
  async function downloadHD(mediaEl) {
    reportProgress('downloading', 90, 'Resolving variant downloads and redirects...');
    
    const candidates = [];
    
    // 1. Check container of the media element
    const container = mediaEl.closest('.image-container, .image-card, .video-container, .video-card, [class*="image"], [class*="video"], [class*="card"], [class*="bubble"], [class*="element"]');
    if (container) {
      // Find all buttons or links inside the container that could be download triggers
      const containerButtons = qAllDeep('button, a', container).filter(el => {
        if (!visible(el)) return false;
        const text = textOf(el);
        const ariaLabel = (el.getAttribute('aria-label') || '').toLowerCase();
        return ariaLabel.includes('kích thước') || ariaLabel.includes('full size') || ariaLabel.includes('full-size') ||
               ariaLabel.includes('download') || ariaLabel.includes('tải xuống') ||
               text.includes('kích thước') || text.includes('full size') || text.includes('full-size') ||
               text.includes('download') || text.includes('tải xuống') || el.hasAttribute('download');
      });
      
      for (const btn of containerButtons) {
        const url = btn.getAttribute('href') || btn.getAttribute('data-url') || btn.getAttribute('url') || btn.href;
        if (url) {
          candidates.push({ url, source: `container_button (${textOf(btn).slice(0, 30)})` });
        }
      }
    }
    
    // 2. Also check document-wide download buttons as fallback/extra candidates
    const docButtons = qAllDeep('button[aria-label*="Download full size image" i], button[aria-label*="kích thước" i], a[download]').filter(visible);
    for (const btn of docButtons) {
      const url = btn.getAttribute('href') || btn.getAttribute('data-url') || btn.getAttribute('url') || btn.href;
      if (url) {
        candidates.push({ url, source: `doc_button (${textOf(btn).slice(0, 30)})` });
      }
    }

    // 3. Add the primary media src/currentSrc
    const mediaSrc = mediaEl.currentSrc || mediaEl.src;
    if (mediaSrc) {
      candidates.push({ url: mediaSrc, source: 'media_src' });
    }
    
    // 4. Parse source elements inside video, if applicable
    if ((mediaEl.tagName || '').toLowerCase() === 'video') {
      const sources = qAll('source', mediaEl);
      for (const source of sources) {
        const url = source.src;
        if (url) {
          candidates.push({ url, source: 'video_source_tag' });
        }
      }
    }

    // 5. Parse srcset for images, if applicable
    if (mediaEl.srcset) {
      const srcsetUrls = mediaEl.srcset.split(',').map(s => s.trim().split(' ')[0]).filter(Boolean);
      for (const url of srcsetUrls) {
        candidates.push({ url, source: 'media_srcset' });
      }
    }

    // Deduplicate candidates and resolve relative URLs
    const seenUrls = new Set();
    const uniqueCandidates = [];
    for (const c of candidates) {
      let resolved = c.url;
      if (!resolved) continue;
      if (!resolved.startsWith('http') && !resolved.startsWith('blob') && !resolved.startsWith('data')) {
        try { resolved = new URL(resolved, window.location.href).href; } catch (e) {}
      }
      if (!seenUrls.has(resolved)) {
        seenUrls.add(resolved);
        uniqueCandidates.push({ url: resolved, source: c.source });
      }
    }

    log(`Collected ${uniqueCandidates.length} unique download candidates:`);
    uniqueCandidates.forEach((c, idx) => {
      log(`Candidate [${idx}]: source=${c.source}, url=${c.url.slice(0, 100)}`);
    });

    if (uniqueCandidates.length === 0) {
      throw new Error('No valid download candidates found for generated media');
    }

    let lastError = null;
    for (const cand of uniqueCandidates) {
      try {
        log(`Trying download candidate from ${cand.source}: ${cand.url.slice(0, 80)}`);
        
        let targetSrc = cand.url;
        if (targetSrc.startsWith('blob:')) {
          log('blob URL detected, downloading via page-world to bypass isolated-world CSP constraints');
          const res = await downloadBlobViaPageWorld(targetSrc);
          if (!res || !res.base64 || res.base64.length < 100) {
            throw new Error(`Blob fetch returned empty or tiny base64 (${res ? res.base64.length : 0} bytes)`);
          }
          log('download full quality mime=' + res.mime + ' bytes=' + res.base64.length);
          
          // Verify final byteLength/size is valid (image > 10KB, or non-zero video)
          const byteLength = Math.round(res.base64.length * 0.75); // approx size in bytes from base64
          const isImage = res.mime.startsWith('image/');
          if (isImage && byteLength < 10240) {
            throw new Error(`Blob image body is too tiny (${byteLength} bytes, minimum is 10KB)`);
          } else if (byteLength === 0) {
            throw new Error('Blob media body is completely empty (0 bytes)');
          }
          
          reportProgress('downloading', 96, 'Downloading asset binary package...');
          return res;
        }

        // Apply quality suffix transformations for googleusercontent if applicable
        if (/googleusercontent\.com\//.test(targetSrc) && /=[swh]\d+/.test(targetSrc)) {
          targetSrc = targetSrc.replace(/=[swh]\d+[^?&]*/g, '=s0');
          log('stripped size suffix ➔ fetching full resolution from googleusercontent: ' + targetSrc.slice(0, 80));
        } else if (/googleusercontent\.com\//.test(targetSrc)) {
          // If it doesn't already have =s0, let's split by ? and append =s0
          if (!targetSrc.includes('=s0')) {
            targetSrc = targetSrc.split('?')[0] + '=s0';
            log('appended =s0 for full resolution: ' + targetSrc.slice(0, 80));
          }
        }

        log('BUG-103 FIX v2: Using CDP Network.getResponseBody for: ' + targetSrc.slice(0, 80));
        
        const filename = 'db9-generated-' + Date.now() + (targetSrc.includes('video') ? '.mp4' : '.png');
        const response = await new Promise((resolve, reject) => {
          chrome.runtime.sendMessage({
            action: 'download-via-cdp',
            url: targetSrc,
            filename: filename
          }, (response) => {
            if (chrome.runtime.lastError) {
              reject(new Error(chrome.runtime.lastError.message));
            } else if (!response || !response.ok) {
              reject(new Error(response?.error || 'CDP download failed'));
            } else {
              resolve(response);
            }
          });
        });
        
        if (!response.base64 || response.base64.length < 100) {
          throw new Error(`CDP returned empty or tiny base64 (${response.base64 ? response.base64.length : 0} bytes)`);
        }
        
        log('BUG-103 FIX v2: CDP download successful, base64 length=' + response.base64.length);
        reportProgress('downloading', 96, 'Download complete via CDP...');
        
        return { 
          base64: response.base64, 
          mime: response.mime || 'image/png',
          downloaded: true,
          downloadId: response.downloadId
        };
      } catch (err) {
        log(`Candidate from ${cand.source} failed: ${err.message}`);
        lastError = err;
      }
    }
    
    // If all candidates failed, fallback to page-world download of the first candidate
    log('All candidates failed, trying page-world download fallback...');
    if (uniqueCandidates.length > 0) {
      const fallbackUrl = uniqueCandidates[0].url;
      try {
        log('downloading via page-world from: ' + fallbackUrl.slice(0, 80));
        const res = await downloadBlobViaPageWorld(fallbackUrl);
        log('download full quality mime=' + res.mime + ' bytes=' + res.base64.length);
        
        const byteLength = Math.round(res.base64.length * 0.75);
        const isImage = res.mime.startsWith('image/');
        if (isImage && byteLength < 10240) {
          throw new Error(`Fallback image body is too tiny (${byteLength} bytes, minimum is 10KB)`);
        } else if (byteLength === 0) {
          throw new Error('Fallback media body is completely empty (0 bytes)');
        }
        
        reportProgress('downloading', 96, 'Downloading asset binary package...');
        return res;
      } catch (fallbackErr) {
        log('page-world fetch failed: ' + fallbackErr.message);
        throw fallbackErr;
      }
    }
    
    throw lastError || new Error('No valid download candidates found');
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
    let found = false;
    while (Date.now() - start < timeoutMs) {
      if (promptInput()) {
        found = true;
        break;
      }
      await sleep(500);
    }
    if (found) {
      log('prompt input found, waiting 3s for Angular bootstrap and event handlers to stabilize...');
      await sleep(3000);
      return true;
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
    uploadPreviewImages,
  };

  log('provider module loaded');
  } catch (err) {
    console.error('[DB9-Gemini] FATAL ERROR IN PROVIDER INIT:', err);
  }
})();
