// DB9 Multi-Provider — ChatGPT provider module
// Loaded first on https://chatgpt.com/*, BEFORE content-script.js.
// Exposes the same interface as provider-gemini.js so the shared orchestrator
// in content-script.js can drive ChatGPT identically.
//
// !! UNVERIFIED SELECTORS !!
// ChatGPT's UI changes frequently. Every selector below is marked UNVERIFIED
// and may need user adjustment. Inline comments call out which selector to
// inspect first when something breaks. Run a snapshot in DevTools and update.

(() => {
  if (window.__DB9_PROVIDER && window.__DB9_PROVIDER.name === 'chatgpt') return;

  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const rand = (min, max) => min + Math.random() * (max - min);
  const visible = (e) => e && e.offsetParent !== null;
  const qAll = (sel, root = document) => [...root.querySelectorAll(sel)];
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
    console.log('[DB9-ChatGPT]', text);
    try { chrome.runtime.sendMessage({ type: 'log', text: '[chatgpt] ' + text }); } catch (e) {}
  };

  // ========================================================================
  // SELECTORS — UNVERIFIED, all sourced from public DevTools recon as of
  // April 2026. Inspect chatgpt.com and adjust if any return null.
  // ========================================================================

  // UNVERIFIED: prompt input — ChatGPT uses a contenteditable ProseMirror div
  // with id="prompt-textarea". Some rollouts wrap it differently; broaden if needed.
  function promptInput() {
    return document.querySelector('#prompt-textarea')
        || document.querySelector('div[contenteditable="true"][id*="prompt" i]')
        || document.querySelector('div[contenteditable="true"][data-id*="prompt" i]')
        || document.querySelector('main div[contenteditable="true"]');
  }

  // UNVERIFIED: send / submit button. ChatGPT uses data-testid="send-button"
  // and aria-label "Send prompt" on most builds. Stop button has same testid
  // when generating, so we check disabled/aria too.
  function sendButton() {
    return document.querySelector('button[data-testid="send-button"]')
        || document.querySelector('button[aria-label="Send prompt"]')
        || document.querySelector('button[aria-label*="Send" i]:not([disabled])');
  }

  // UNVERIFIED: "+" upload menu trigger near the prompt. Different rollouts
  // expose: data-testid="composer-plus-btn", aria-label "Upload files and more",
  // or simply "Attach files".
  function uploadMenuButton() {
    return document.querySelector('button[data-testid="composer-plus-btn"]')
        || document.querySelector('button[aria-label="Upload files and more"]')
        || document.querySelector('button[aria-label*="Attach" i]')
        || document.querySelector('button[aria-label*="Upload" i]')
        || document.querySelector('button[data-testid*="upload" i]');
  }

  // UNVERIFIED: "New chat" button. Sidebar usually has either a link to "/"
  // labelled "New chat" or a dedicated icon button.
  function newChatButton() {
    return [...document.querySelectorAll('a,button')].find(b => {
      const t = (b.getAttribute('aria-label') || b.textContent || '').trim();
      return /^new chat$/i.test(t) || /\bnew chat\b/i.test(b.getAttribute('aria-label') || '');
    }) || document.querySelector('a[href="/"]');
  }

  // Generated images live inside assistant messages. We restrict to
  // data-message-author-role="assistant" and ignore avatars/icons.
  // UNVERIFIED: alt text "Generated image" is the most common pattern.
  function generatedImages() {
    const root = document.querySelector('main') || document;
    return qAll('div[data-message-author-role="assistant"] img', root)
      .concat(qAll('img[alt*="Generated image" i]', root))
      // de-dupe
      .filter((img, i, arr) => arr.indexOf(img) === i)
      .filter(i =>
        visible(i) &&
        i.naturalWidth > 200 &&
        // Filter out tiny avatars/icons even if they match
        !/avatar|icon|profile/i.test((i.alt || '') + ' ' + (i.className || ''))
      );
  }

  // UNVERIFIED: model switcher. We only USE this to log a warning when the
  // active model isn't image-capable. Detection failure is non-fatal.
  function activeModelLabel() {
    const el = document.querySelector('[data-testid="model-switcher-dropdown-button"]')
            || document.querySelector('button[aria-label*="Model selector" i]')
            || document.querySelector('button[aria-haspopup="menu"][aria-label*="Model" i]');
    return el ? (el.textContent || '').trim() : '';
  }

  // ===== Page-world fetch/XHR monitor (ChatGPT-specific endpoints) =====
  // UNVERIFIED endpoints: ChatGPT's image upload typically posts to
  // /backend-api/files (signed URL request) and then the actual bytes go to
  // files.oaiusercontent.com or storage.googleapis.com. We accept any of these
  // 200-OK responses as proof of upload.
  // v0.3.1 — CSP-safe: load monitor as external file via web_accessible_resources.
  // ChatGPT's page CSP forbids inline <script>textContent, so we must use src=.
  function installNetworkMonitor() {
    try {
      if (window.__db9MonitorInjected) return;
      window.__db9MonitorInjected = true;
      const s = document.createElement('script');
      s.src = chrome.runtime.getURL('content/injected-monitor-chatgpt.js');
      s.onload = () => { try { s.remove(); } catch (e) {} };
      s.onerror = (e) => console.warn('[DB9-ChatGPT] monitor script failed to load', e);
      (document.head || document.documentElement).appendChild(s);
    } catch (e) {
      console.warn('[DB9-ChatGPT] failed to inject page-world monitor', e);
    }
  }

  // CSP-safe probe: dispatch a request event that the page-world monitor
  // listens for, and wait for the matching result event back.
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

  // ===== Native file input setter (React-safe, same trick as Gemini) =====
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
    // React listens via SyntheticEvent on native change; bubbles+composed crucial.
    try { fileInput.dispatchEvent(new Event('input', { bubbles: true, composed: true })); } catch (e) {}
    try { fileInput.dispatchEvent(new Event('change', { bubbles: true, composed: true })); } catch (e) {}
  }

  // React-safe contenteditable text insertion
  // ChatGPT uses ProseMirror; the safest way to insert text and have React/PM
  // pick it up is execCommand('insertText') after focusing.
  async function humanType(el, text) {
    el.focus();
    // Move caret to end first
    try {
      const sel = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(el);
      range.collapse(false);
      sel.removeAllRanges();
      sel.addRange(range);
    } catch (e) {}
    let inserted = false;
    try {
      inserted = document.execCommand('insertText', false, text);
    } catch (e) {}
    if (!inserted || (el.textContent || '').indexOf(text) === -1) {
      // Fallback: dispatch InputEvent with inputType=insertText (ProseMirror handles)
      const evt = new InputEvent('input', { bubbles: true, cancelable: true, composed: true, data: text, inputType: 'insertText' });
      el.dispatchEvent(evt);
      if ((el.textContent || '').indexOf(text) === -1) {
        // Last resort: set textContent (may break PM tracking but at least sends)
        el.textContent = text;
        el.dispatchEvent(new InputEvent('input', { bubbles: true, data: text }));
      }
    }
    await sleep(rand(150, 300));
  }

  function base64ToFile(base64, mime) {
    const byteString = atob(base64);
    const bytes = new Uint8Array(byteString.length);
    for (let i = 0; i < byteString.length; i++) bytes[i] = byteString.charCodeAt(i);
    const blob = new Blob([bytes], { type: mime || 'image/png' });
    return new File([blob], `db9-${Date.now()}.png`, { type: mime || 'image/png' });
  }

  async function startNewChat() {
    const btn = newChatButton();
    if (btn) {
      btn.click();
      await sleep(800);
      log('▶️ started new chat');
    } else {
      log('⚠ new chat button not found, navigating to /');
      location.href = 'https://chatgpt.com/';
      await sleep(2500);
    }
  }

  // v0.4.7.1: explicitly enable "Tạo hình ảnh" / "Create image" mode via composer-plus menu
  async function toggleCreateImage() {
    log('▶️ enabling Create Image mode...');
    const menu = uploadMenuButton();
    if (!menu) {
      log('⚠ composer-plus button not found');
      return;
    }
    try { menu.click(); } catch (e) {}
    await sleep(350);

    // Look for menu item "Tạo hình ảnh" / "Create image" / "Generate image"
    const items = qAll('button,[role="menuitem"],div[role="menuitem"],li').filter(visible);
    const item = items.find((el) => textMatches(el, [
      'Tao hinh anh',
      'Create image',
      'Generate image',
      'Make image',
      'Image generation'
    ]));
    if (item) {
      try { item.click(); } catch (e) {}
      log('✓ enabled Create Image mode');
      await sleep(400);
    } else {
      // Close menu — fallback: assume 4o auto-handles
      try { document.body.click(); } catch (e) {}
      const m = activeModelLabel();
      log('⚠ create-image menu item not found; relying on model auto-detect' + (m ? ' (active: ' + m + ')' : ''));
    }
  }

  async function uploadImage(base64, mime) {
    // v0.4.7.1: ChatGPT — recorder confirms #upload-files is the canonical input id.
    const file = base64ToFile(base64, mime);

    try { window.dispatchEvent(new CustomEvent('db9-reset-upload')); } catch (e) {}

    // STRATEGY 1: target #upload-files directly (always present, hidden)
    let fileInput = document.getElementById('upload-files') || document.querySelector('input[type="file"]');
    if (fileInput) {
      const dt = new DataTransfer();
      dt.items.add(file);
      setNativeFiles(fileInput, dt.files);
      log('📎 strategy 1: #upload-files set via native setter');
      await sleep(900);
      return;
    }

    // STRATEGY 2: open "+" menu → click "Upload images & files" → input mounts
    log('📎 strategy 2: opening composer-plus menu...');
    const menu = uploadMenuButton();
    if (menu) {
      menu.click();
      await sleep(350);
      const items = qAll('button,[role="menuitem"],div[role="menuitem"]').filter(visible);
      const item = items.find((el) => textMatches(el, [
        'Tai len anh',
        'Upload from computer',
        'Upload file',
        'Upload image',
        'Image and file',
        'From computer'
      ]));
      if (item) {
        try { item.click(); } catch (e) {}
        await sleep(400);
      }
      // Re-check #upload-files
      fileInput = document.getElementById('upload-files') || document.querySelector('input[type="file"]');
      if (fileInput) {
        const dt = new DataTransfer();
        dt.items.add(file);
        setNativeFiles(fileInput, dt.files);
        log('📎 strategy 2: set fileInput.files after opening menu');
        await sleep(900);
        return;
      }
    }

    // STRATEGY 3: paste fallback
    const input = promptInput();
    if (input) {
      try {
        const dt1 = new DataTransfer();
        dt1.items.add(file);
        const evt = new ClipboardEvent('paste', { bubbles: true, cancelable: true, composed: true });
        Object.defineProperty(evt, 'clipboardData', { value: dt1 });
        input.dispatchEvent(evt);
        log('📎 strategy 3: paste dispatched (fallback)');
        await sleep(1200);
        return;
      } catch (e) { log('paste fallback failed: ' + e.message); }
    }

    log('⚠ all upload strategies failed');
  }

    async function waitForUploadPreview(timeoutMs = 30000) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      if (await getUploadMonitorOk()) {
        log('✓ upload confirmed by page-world fetch/XHR monitor');
        return true;
      }
      // UNVERIFIED preview selectors: ChatGPT shows attached files as small
      // thumbnails above the prompt with role="presentation" or class containing
      // "attachment". Broad query to be resilient.
      const candidates = [
        ...qAll('[data-testid*="file-attachment" i]').filter(visible),
        ...qAll('[class*="attachment" i] img').filter(visible),
        ...qAll('div[role="presentation"] img').filter(i => visible(i) && i.naturalWidth > 30 && i.naturalWidth < 400),
        ...qAll('img[alt*="attachment" i], img[alt*="uploaded" i]').filter(visible)
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
    if (btn && !btn.disabled && btn.getAttribute('aria-disabled') !== 'true') {
      btn.click();
      log('▶️ submit clicked');
      return;
    }
    // Fallback: press Enter
    input.focus();
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
    log('▶️ submit via Enter key');
  }

  async function waitForOutput(baselineCount, timeoutMs = 240000) {
    // ChatGPT image gen can take 30-90s. Also wait for image to be "stable":
    // not blob:, no loading spinner near it.
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      const imgs = generatedImages();
      const newOnes = imgs.slice(baselineCount);
      // Pick first image whose src is a real https URL (not blob:, not data:)
      const ready = newOnes.find(i =>
        i.src && i.src.startsWith('http') && i.naturalWidth > 200
      );
      if (ready) {
        // Confirm it's stable: same src after 2s
        const src1 = ready.src;
        await sleep(2000);
        if (ready.src === src1) {
          log(`✅ got generated image ${ready.naturalWidth}x${ready.naturalHeight}`);
          return ready;
        }
      }
      await sleep(1000);
    }
    throw new Error('no generated image within ' + (timeoutMs / 1000) + 's');
  }

  async function downloadHD(imgEl) {
    // v0.4.7.1: try the image-gen overlay download button first (recorder selector)
    try {
      const dlBtn = document.querySelector('[data-testid="image-gen-overlay-right-actions"] button')
        || Array.from(document.querySelectorAll('[aria-label*="download" i], [aria-label*="tải" i]')).find(b => b.offsetParent);
      if (dlBtn) {
        let capturedUrl = null;
        const origCreate = URL.createObjectURL;
        URL.createObjectURL = function(obj) {
          const url = origCreate.apply(this, arguments);
          try { if (obj instanceof Blob && (obj.type||'').startsWith('image/')) capturedUrl = url; } catch (e) {}
          return url;
        };
        try { dlBtn.click(); } catch (e) {}
        await sleep(700);
        URL.createObjectURL = origCreate;
        if (capturedUrl) {
          log('  ✓ captured download blob URL via overlay button');
          const r = await fetch(capturedUrl);
          const b = await r.blob();
          return await new Promise((resolve) => {
            const fr = new FileReader();
            fr.onloadend = () => resolve({ base64: fr.result.split(',')[1], mime: b.type || 'image/png' });
            fr.readAsDataURL(b);
          });
        }
      }
    } catch (e) { log('  ⚠ overlay download skipped: ' + e.message); }

    // Existing fallback: direct fetch of img.src (signed OpenAI URL)
    const src = imgEl.src;
    try {
      const resp = await fetch(src);
      if (resp.ok) {
        const blob = await resp.blob();
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
      log(`⚠ direct fetch returned ${resp.status}, falling back to canvas`);
    } catch (e) {
      log(`⚠ direct fetch threw: ${e.message}, falling back to canvas`);
    }

    // Canvas fallback (works when the img has crossOrigin or is same-origin)
    try {
      const canvas = document.createElement('canvas');
      canvas.width = imgEl.naturalWidth;
      canvas.height = imgEl.naturalHeight;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(imgEl, 0, 0);
      const dataUrl = canvas.toDataURL('image/png');
      const base64 = dataUrl.split(',')[1];
      return { base64, mime: 'image/png' };
    } catch (e) {
      throw new Error('downloadHD failed (fetch and canvas both): ' + e.message);
    }
  }

  function countBaseline() { return generatedImages().length; }

  async function waitReady(timeoutMs = 15000) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      if (promptInput()) return true;
      await sleep(500);
    }
    return false;
  }

  window.__DB9_PROVIDER = {
    name: 'chatgpt',
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

  log('provider module loaded (selectors UNVERIFIED — see comments)');
})();
