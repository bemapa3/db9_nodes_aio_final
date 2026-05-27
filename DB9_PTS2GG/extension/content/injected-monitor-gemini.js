// DB9 page-world network monitor — Gemini
// Injected as an external <script src> (via web_accessible_resources) to match
// the CSP-safe pattern used for ChatGPT. Gemini's CSP is currently permissive,
// but using external file injection everywhere keeps the design uniform.
(() => {
  if (window.__db9MonitorInstalled) return;
  window.__db9MonitorInstalled = true;
  window.__db9LastUploadOk = false;
  window.__db9LastUploadAt = 0;

  const isUploadUrl = (url) => {
    try {
      const s = String(url || '');
      return s.includes('content-push.googleapis.com/upload/') ||
             s.includes('push.googleapis.com/upload/') ||
             (s.includes('/upload/') && s.includes('googleapis.com'));
    } catch (e) { return false; }
  };

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
            window.dispatchEvent(new CustomEvent('db9-upload-ok', { detail: { url, status: r.status, provider: 'gemini' } }));
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
          window.dispatchEvent(new CustomEvent('db9-upload-ok', { detail: { url: _url, status: xhr.status, provider: 'gemini' } }));
        }
      } catch (e) {}
    });
    return xhr;
  }
  PatchedXHR.prototype = OrigXHR.prototype;
  window.XMLHttpRequest = PatchedXHR;

  // Intercept file input click to prevent OS file dialog blocking during automation (for unappended inputs)
  const origInputClick = HTMLInputElement.prototype.click;
  HTMLInputElement.prototype.click = function() {
    if (this.type === 'file' && window.__db9AutomationActive) {
      this.id = 'db9-hijacked-file-input';
      window.__db9LastFileInput = this;
      console.log('[DB9] Blocked native file dialog via prototype.click on', this);
      return; // prevent OS dialog
    }
    return origInputClick.apply(this, arguments);
  };

  // Intercept file input clicks via capturing listener to block OS dialog if triggered via UI
  document.addEventListener('click', (ev) => {
    if (window.__db9AutomationActive && ev.target && ev.target.tagName === 'INPUT' && ev.target.type === 'file') {
      ev.preventDefault();
      ev.stopPropagation();
      ev.target.id = 'db9-hijacked-file-input';
      window.__db9LastFileInput = ev.target;
      console.log('[DB9] Blocked native file dialog via click capture on', ev.target);
    }
  }, true);

  // Fallback: intercept dynamic creation just in case it's never clicked but we need it
  const origCreateElement = document.createElement;
  document.createElement = function(tagName) {
    const el = origCreateElement.apply(this, arguments);
    if (typeof tagName === 'string' && tagName.toLowerCase() === 'input') {
      setTimeout(() => {
        if (el.type === 'file' && window.__db9AutomationActive) {
          el.id = 'db9-hijacked-file-input';
          window.__db9LastFileInput = el;
        }
      }, 0);
    }
    return el;
  };

  // Listen for extension declaring automation active
  window.addEventListener('db9-automation-start', () => { window.__db9AutomationActive = true; });
  window.addEventListener('db9-automation-end', () => { window.__db9AutomationActive = false; });

  // Listen for base64 file injection to bypass cross-world instanceof File checks
  window.addEventListener('db9-inject-file-base64', (ev) => {
    try {
      const { base64, mime, filename } = ev.detail;
      const fileInput = window.__db9LastFileInput;
      if (!fileInput) return;
      
      const bstr = atob(base64);
      let n = bstr.length;
      const u8arr = new Uint8Array(n);
      while (n--) { u8arr[n] = bstr.charCodeAt(n); }
      
      const file = new File([u8arr], filename || 'image.png', { type: mime || 'image/png' });
      const dt = new DataTransfer();
      dt.items.add(file);
      fileInput.files = dt.files;
      
      fileInput.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
      fileInput.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
      console.log('[DB9] file injected from base64 in page-world', fileInput);
    } catch (e) {
      console.error('[DB9] base64 inject failed:', e);
    }
  });

  window.addEventListener('db9-probe-request', (ev) => {
    try {
      const id = ev && ev.detail && ev.detail.id;
      window.dispatchEvent(new CustomEvent('db9-probe-result', { detail: { id, ok: !!window.__db9LastUploadOk, hasFileInput: !!window.__db9LastFileInput } }));
    } catch (e) {}
  });

  window.addEventListener('db9-reset-upload', () => {
    window.__db9LastUploadOk = false;
    window.__db9LastUploadAt = 0;
  });

  console.log('[DB9-Monitor] page-world fetch/XHR monitor installed (gemini, external)');
})();
