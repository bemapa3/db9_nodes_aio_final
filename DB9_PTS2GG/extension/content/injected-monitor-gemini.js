// DB9 page-world network monitor — Gemini
// Injected as an external <script src> (via web_accessible_resources) to match
// the CSP-safe pattern used for ChatGPT. Gemini's CSP is currently permissive,
// but using external file injection everywhere keeps the design uniform.
//
// CRITICAL FIX v0.4.8: All events are now listened on BOTH document and window,
// and responses dispatched on BOTH, to fix content-world ↔ page-world mismatch.
(() => {
  if (window.__db9MonitorInstalled) return;
  window.__db9MonitorInstalled = true;
  window.__db9LastUploadOk = false;
  window.__db9LastUploadAt = 0;
  window.__db9AutomationActive = false;
  window.__db9StagedFile = null;
  window.__db9LastFileInput = null;

  const isUploadUrl = (url) => {
    try {
      const s = String(url || '');
      return s.includes('content-push.googleapis.com/upload/') ||
             s.includes('push.googleapis.com/upload/') ||
             (s.includes('/upload/') && s.includes('googleapis.com'));
    } catch (e) { return false; }
  };

  // ===== Fetch/XHR upload monitor =====
  const origFetch = window.fetch;
  window.fetch = function(input, init) {
    let url = '';
    try { url = (typeof input === 'string') ? input : (input && input.url) || ''; } catch (e) {}
    const watching = isUploadUrl(url);
    const p = origFetch.apply(this, arguments);
    if (watching) {
      p.then(r => {
        try {
          if (r && r.ok) {
            window.__db9LastUploadOk = true;
            window.__db9LastUploadAt = Date.now();
            console.log('[DB9-Monitor] gemini upload fetch OK', url, r.status);
            broadcastEvent('db9-upload-ok', { url, status: r.status, provider: 'gemini' });
          }
        } catch (e) {}
      }).catch(() => {});
    }
    return p;
  };

  const OrigXHR = window.XMLHttpRequest;
  function PatchedXHR() {
    const xhr = new OrigXHR();
    let _url = '';
    const origOpen = xhr.open;
    xhr.open = function(method, url) {
      _url = url;
      return origOpen.apply(xhr, arguments);
    };
    xhr.addEventListener('load', () => {
      try {
        if (isUploadUrl(_url) && xhr.status >= 200 && xhr.status < 400) {
          window.__db9LastUploadOk = true;
          window.__db9LastUploadAt = Date.now();
          console.log('[DB9-Monitor] gemini upload XHR OK', _url, xhr.status);
          broadcastEvent('db9-upload-ok', { url: _url, status: xhr.status, provider: 'gemini' });
        }
      } catch (e) {}
    });
    return xhr;
  }
  PatchedXHR.prototype = OrigXHR.prototype;
  window.XMLHttpRequest = PatchedXHR;

  // ===== Helper: broadcast event on BOTH document and window =====
  function broadcastEvent(name, detail) {
    try { document.dispatchEvent(new CustomEvent(name, { detail })); } catch (e) {}
    try { window.dispatchEvent(new CustomEvent(name, { detail })); } catch (e) {}
  }

  // ===== Helper: listen on BOTH document, window, and postMessage =====
  function listenBoth(eventName, handler) {
    document.addEventListener(eventName, handler);
    window.addEventListener(eventName, handler);
  }

  // ===== Intercept file input click to prevent OS file dialog =====
  const origInputClick = HTMLInputElement.prototype.click;
  HTMLInputElement.prototype.click = function() {
    if (this.type === 'file' && window.__db9AutomationActive) {
      this.id = 'db9-hijacked-file-input';
      window.__db9LastFileInput = this;
      console.log('[DB9-Monitor] Blocked native file dialog via prototype.click on', this);
      return; // prevent OS dialog
    }
    return origInputClick.apply(this, arguments);
  };

  // Intercept file input clicks via capturing listener
  document.addEventListener('click', (ev) => {
    if (window.__db9AutomationActive && ev.target && ev.target.tagName === 'INPUT' && ev.target.type === 'file') {
      ev.preventDefault();
      ev.stopPropagation();
      ev.target.id = 'db9-hijacked-file-input';
      window.__db9LastFileInput = ev.target;
      console.log('[DB9-Monitor] Blocked native file dialog via click capture on', ev.target);
    }
  }, true);

  // Intercept dynamic creation
  const origCreateElement = document.createElement;
  document.createElement = function(tagName) {
    const el = origCreateElement.apply(this, arguments);
    if (typeof tagName === 'string' && tagName.toLowerCase() === 'input') {
      setTimeout(() => {
        if (el.type === 'file' && window.__db9AutomationActive) {
          el.id = 'db9-hijacked-file-input';
          window.__db9LastFileInput = el;
          console.log('[DB9-Monitor] Captured dynamically created file input');
        }
      }, 0);
    }
    return el;
  };

  // ===== Intercept dynamic high-res anchor downloads and window.open =====
  const origAnchorClick = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function() {
    try {
      const href = this.href || '';
      if (window.__db9AutomationActive && href && href.includes('googleusercontent.com')) {
        console.log('[DB9-Monitor] High-res anchor click detected (NOT blocking):', href.slice(0, 100));
        broadcastEvent('db9-high-res-url-detected', { url: href });
        // BUG-106 FIX: Let the native download proceed - don't block it!
        // The browser will download with proper auth cookies.
      }
    } catch (e) {}
    return origAnchorClick.apply(this, arguments);
  };

  const origWindowOpen = window.open;
  window.open = function(url, target, features) {
    try {
      const sUrl = String(url || '');
      if (window.__db9AutomationActive && sUrl && sUrl.includes('googleusercontent.com')) {
        console.log('[DB9-Monitor] Intercepted high-res window.open:', sUrl.slice(0, 100));
        broadcastEvent('db9-high-res-url-detected', { url: sUrl });
        return null; // prevent new tab opening
      }
    } catch (e) {}
    return origWindowOpen.apply(this, arguments);
  };

  // ===== showOpenFilePicker override =====
  if (window.showOpenFilePicker) {
    const origShowOpenFilePicker = window.showOpenFilePicker.bind(window);
    window.showOpenFilePicker = async function(...args) {
      if (window.__db9AutomationActive && window.__db9StagedFile) {
        console.log('[DB9-Monitor] showOpenFilePicker intercepted, returning staged file:', window.__db9StagedFile.name);
        const file = window.__db9StagedFile;
        window.__db9StagedFile = null;
        // Return a FileSystemFileHandle-like array
        return [{
          kind: 'file',
          name: file.name,
          getFile: async () => file,
        }];
      }
      return origShowOpenFilePicker.apply(window, args);
    };
    console.log('[DB9-Monitor] showOpenFilePicker override installed');
  }

  // ===== Helper: create File from base64 =====
  function base64ToFile(base64, mime, filename) {
    const bstr = atob(base64);
    let n = bstr.length;
    const u8arr = new Uint8Array(n);
    while (n--) { u8arr[n] = bstr.charCodeAt(n); }
    return new File([u8arr], filename || 'db9-upload.png', { type: mime || 'image/png' });
  }

  // ===== db9-stage-file handler (CustomEvent on document/window) =====
  function handleStageFile(detail) {
    try {
      const { base64, mime, filename } = detail;
      if (!base64) { console.warn('[DB9-Monitor] db9-stage-file: no base64 data'); return; }
      window.__db9StagedFile = base64ToFile(base64, mime, filename);
      console.log('[DB9-Monitor] File staged for intercept:', filename || 'image.png', mime || 'image/png', 'size=' + Math.round(base64.length * 0.75 / 1024) + 'KB');
    } catch (e) {
      console.error('[DB9-Monitor] Failed to stage file:', e);
    }
  }

  listenBoth('db9-stage-file', (ev) => {
    if (ev.detail) handleStageFile(ev.detail);
  });

  // ===== db9-automation-start/end (listen on BOTH document and window) =====
  listenBoth('db9-automation-start', () => {
    window.__db9AutomationActive = true;
    console.log('[DB9-Monitor] Automation ACTIVE');
  });
  listenBoth('db9-automation-end', () => {
    window.__db9AutomationActive = false;
    console.log('[DB9-Monitor] Automation ENDED');
  });

  // ===== db9-reset-upload =====
  listenBoth('db9-reset-upload', () => {
    window.__db9LastUploadOk = false;
    window.__db9LastUploadAt = 0;
    window.__db9LastFileInput = null;
    console.log('[DB9-Monitor] Upload state reset');
  });

  // ===== db9-inject-file-base64 handler =====
  listenBoth('db9-inject-file-base64', (ev) => {
    try {
      const { base64, mime, filename } = ev.detail;
      const fileInput = window.__db9LastFileInput;
      if (!fileInput) {
        console.warn('[DB9-Monitor] db9-inject-file-base64: no captured file input to inject into');
        return;
      }

      const file = base64ToFile(base64, mime, filename);
      const dt = new DataTransfer();
      dt.items.add(file);
      fileInput.files = dt.files;

      fileInput.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
      fileInput.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
      console.log('[DB9-Monitor] File injected from base64 into file input', fileInput);
    } catch (e) {
      console.error('[DB9-Monitor] base64 inject failed:', e);
    }
  });

  // ===== Blob download handler (CSP blocks fetch(blob:), use canvas instead) =====
  async function handleBlobDownload(detail) {
    const { id, blobUrl } = detail;
    try {
      console.log('[DB9-Monitor] Downloading blob via canvas:', blobUrl?.slice(0, 60));
      
      // Find the existing img/video element with this blob src (already loaded in DOM)
      let img = document.querySelector(`img[src="${CSS.escape(blobUrl)}"]`);
      if (!img) {
        // Search all images for matching currentSrc
        img = Array.from(document.querySelectorAll('img')).find(i => 
          (i.currentSrc || i.src) === blobUrl
        );
      }
      
      const isVideo = !img;
      let videoEl = null;
      if (!img) {
        videoEl = Array.from(document.querySelectorAll('video')).find(v => 
          (v.currentSrc || v.src) === blobUrl
        );
      }

      if (!img && !videoEl) {
        // Create a new Image and load the blob URL (img-src is not restricted by connect-src)
        console.log('[DB9-Monitor] No existing element found, creating new Image for blob');
        img = new Image();
        await new Promise((resolve, reject) => {
          img.onload = resolve;
          img.onerror = () => reject(new Error('Image load from blob URL failed'));
          const timer = setTimeout(() => reject(new Error('Image load timeout (10s)')), 10000);
          img.addEventListener('load', () => clearTimeout(timer));
          img.src = blobUrl;
        });
      }

      if (img) {
        // Wait for complete load if needed
        if (!img.complete || !img.naturalWidth) {
          await new Promise((resolve, reject) => {
            if (img.complete && img.naturalWidth) return resolve();
            img.onload = resolve;
            img.onerror = () => reject(new Error('Image not fully loaded'));
            setTimeout(resolve, 3000); // force after 3s
          });
        }

        // BUG-106 FIX: Wait up to 5s for full resolution (2048x2048) to load
        const resStart = Date.now();
        while ((img.naturalWidth < 2048 || img.naturalHeight < 2048) && (Date.now() - resStart < 5000)) {
          console.log('[DB9-Monitor] Waiting for full resolution... current:', img.naturalWidth + 'x' + img.naturalHeight);
          await new Promise(r => setTimeout(r, 500));
        }

        const w = img.naturalWidth || img.width || 0;
        const h = img.naturalHeight || img.height || 0;
        
        if (w < 2048 || h < 2048) {
          console.warn('[DB9-Monitor] WARNING: Image resolution is below 2048x2048:', w + 'x' + h, '- canvas capture may be low quality');
        }
        
        const canvas = document.createElement('canvas');
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0, w, h);
        
        const dataUrl = canvas.toDataURL('image/png');
        const base64 = dataUrl.split(',')[1] || '';
        const mime = 'image/png';
        
        console.log('[DB9-Monitor] Blob downloaded via canvas:', w + 'x' + h, 'base64 length:', base64.length);
        broadcastEvent('db9-download-blob-response', { id, success: true, base64, mime });
        try { window.postMessage({ source: 'db9-monitor', type: 'db9-download-blob-response', detail: { id, success: true, base64, mime } }, '*'); } catch (e) {}
      } else if (videoEl) {
        // Video: capture current frame via canvas
        const w = videoEl.videoWidth || 1920;
        const h = videoEl.videoHeight || 1080;
        const canvas = document.createElement('canvas');
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(videoEl, 0, 0, w, h);
        
        const dataUrl = canvas.toDataURL('image/png');
        const base64 = dataUrl.split(',')[1] || '';
        
        console.log('[DB9-Monitor] Video frame captured via canvas:', w + 'x' + h, 'base64 length:', base64.length);
        broadcastEvent('db9-download-blob-response', { id, success: true, base64, mime: 'image/png' });
        try { window.postMessage({ source: 'db9-monitor', type: 'db9-download-blob-response', detail: { id, success: true, base64, mime: 'image/png' } }, '*'); } catch (e) {}
      } else {
        throw new Error('No img or video element found for blob URL');
      }
    } catch (e) {
      console.error('[DB9-Monitor] Blob download failed:', e);
      broadcastEvent('db9-download-blob-response', { id, success: false, error: e.message });
      try { window.postMessage({ source: 'db9-monitor', type: 'db9-download-blob-response', detail: { id, success: false, error: e.message } }, '*'); } catch (e2) {}
    }
  }

  listenBoth('db9-download-blob-request', (ev) => {
    if (ev.detail) handleBlobDownload(ev.detail);
  });

  // ===== Probe request/response =====
  function handleProbeRequest(id) {
    const detail = {
      id,
      ok: !!window.__db9LastUploadOk,
      hasFileInput: !!window.__db9LastFileInput,
      automationActive: !!window.__db9AutomationActive,
      stagedFile: !!window.__db9StagedFile,
      lastUploadAt: window.__db9LastUploadAt || 0
    };
    // Respond on ALL channels so provider definitely receives it
    try { document.dispatchEvent(new CustomEvent('db9-probe-result', { detail })); } catch (e) {}
    try { window.dispatchEvent(new CustomEvent('db9-probe-result', { detail })); } catch (e) {}
    try { window.postMessage({ source: 'db9-monitor', type: 'db9-probe-result', detail }, '*'); } catch (e) {}
  }

  // Listen for probe on document CustomEvent
  document.addEventListener('db9-probe-request', (ev) => {
    const id = ev && ev.detail && ev.detail.id;
    handleProbeRequest(id);
  });
  // Listen for probe on window CustomEvent
  window.addEventListener('db9-probe-request', (ev) => {
    const id = ev && ev.detail && ev.detail.id;
    handleProbeRequest(id);
  });

  // ===== postMessage handler for ALL extension→page-world events =====
  window.addEventListener('message', (ev) => {
    const data = ev.data || {};
    if (data.source !== 'db9-extension') return;

    switch (data.type) {
      case 'db9-stage-file':
        if (data.detail) handleStageFile(data.detail);
        break;
      case 'db9-automation-start':
        window.__db9AutomationActive = true;
        console.log('[DB9-Monitor] Automation ACTIVE (via postMessage)');
        break;
      case 'db9-automation-end':
        window.__db9AutomationActive = false;
        console.log('[DB9-Monitor] Automation ENDED (via postMessage)');
        break;
      case 'db9-reset-upload':
        window.__db9LastUploadOk = false;
        window.__db9LastUploadAt = 0;
        window.__db9LastFileInput = null;
        break;
      case 'db9-probe-request':
        handleProbeRequest(data.id);
        break;
      case 'db9-inject-file-base64':
        if (data.detail) {
          try {
            const { base64, mime, filename } = data.detail;
            const fileInput = window.__db9LastFileInput;
            if (!fileInput) return;
            const file = base64ToFile(base64, mime, filename);
            const dt = new DataTransfer();
            dt.items.add(file);
            fileInput.files = dt.files;
            fileInput.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
            fileInput.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
            console.log('[DB9-Monitor] File injected via postMessage into file input');
          } catch (e) {
            console.error('[DB9-Monitor] postMessage base64 inject failed:', e);
          }
        }
        break;
      case 'db9-download-blob-request':
        if (data.detail) handleBlobDownload(data.detail);
        break;
    }
  });

  console.log('[DB9-Monitor] page-world fetch/XHR monitor installed (gemini, v0.4.8 fixed)');
})();
