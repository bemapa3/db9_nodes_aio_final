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

  window.addEventListener('db9-probe-request', (ev) => {
    try {
      const id = ev && ev.detail && ev.detail.id;
      window.dispatchEvent(new CustomEvent('db9-probe-result', { detail: { id, ok: !!window.__db9LastUploadOk } }));
    } catch (e) {}
  });

  window.addEventListener('db9-reset-upload', () => {
    window.__db9LastUploadOk = false;
    window.__db9LastUploadAt = 0;
  });

  console.log('[DB9-Monitor] page-world fetch/XHR monitor installed (gemini, external)');
})();
