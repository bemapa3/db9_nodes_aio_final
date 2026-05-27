// DB9 page-world network monitor - Google Flow
(() => {
  if (window.__db9FlowMonitorInstalled) return;
  window.__db9FlowMonitorInstalled = true;
  window.__db9FlowLastGenerate = null;

  const isGenerateUrl = (url) => {
    try { return String(url || '').includes('/v1/video:batchAsyncGenerateVideoStartImage'); }
    catch (_) { return false; }
  };

  const summarize = async (response) => {
    let preview = '';
    try { preview = await response.clone().text(); } catch (_) {}
    let parsed = null;
    try { parsed = preview ? JSON.parse(preview) : null; } catch (_) {}
    const error = parsed && parsed.error ? parsed.error : null;
    const details = Array.isArray(error && error.details) ? error.details : [];
    const unusual = /PUBLIC_ERROR_UNUSUAL_ACTIVITY/i.test(JSON.stringify(details));
    return {
      status: response.status,
      ok: response.ok,
      errorCode: error && error.code || null,
      errorMessage: error && error.message || '',
      unusualActivity: unusual,
      preview: preview.slice(0, 1200)
    };
  };

  const remember = (detail) => {
    window.__db9FlowLastGenerate = { ...detail, at: Date.now() };
    try {
      window.dispatchEvent(new CustomEvent('db9-flow-generate-result', { detail: window.__db9FlowLastGenerate }));
    } catch (_) {}
  };

  const origFetch = window.fetch;
  window.fetch = function(input, init) {
    let url = '';
    try { url = typeof input === 'string' ? input : (input && input.url) || ''; } catch (_) {}
    const watching = isGenerateUrl(url);
    const p = origFetch.apply(this, arguments);
    if (watching) {
      p.then(async response => {
        try {
          const summary = await summarize(response);
          remember({ url, ...summary });
          console.log('[DB9-Monitor] flow generate fetch', response.status, summary.errorMessage || '', summary.unusualActivity ? 'PUBLIC_ERROR_UNUSUAL_ACTIVITY' : '');
        } catch (_) {}
      }).catch(error => {
        remember({ url, status: 0, ok: false, errorMessage: error && error.message || String(error), unusualActivity: false, preview: '' });
      });
    }
    return p;
  };

  const OrigXHR = window.XMLHttpRequest;
  function PatchedXHR() {
    const xhr = new OrigXHR();
    let xhrUrl = '';
    const origOpen = xhr.open;
    xhr.open = function(method, url) {
      xhrUrl = String(url || '');
      return origOpen.apply(xhr, arguments);
    };
    xhr.addEventListener('load', () => {
      try {
        if (!isGenerateUrl(xhrUrl)) return;
        const preview = String(xhr.responseText || '').slice(0, 1200);
        let parsed = null;
        try { parsed = preview ? JSON.parse(preview) : null; } catch (_) {}
        const error = parsed && parsed.error ? parsed.error : null;
        const details = Array.isArray(error && error.details) ? error.details : [];
        const unusual = /PUBLIC_ERROR_UNUSUAL_ACTIVITY/i.test(JSON.stringify(details));
        remember({
          url: xhrUrl,
          status: xhr.status,
          ok: xhr.status >= 200 && xhr.status < 400,
          errorCode: error && error.code || null,
          errorMessage: error && error.message || '',
          unusualActivity: unusual,
          preview
        });
        console.log('[DB9-Monitor] flow generate XHR', xhr.status, error && error.message || '', unusual ? 'PUBLIC_ERROR_UNUSUAL_ACTIVITY' : '');
      } catch (_) {}
    });
    return xhr;
  }
  PatchedXHR.prototype = OrigXHR.prototype;
  window.XMLHttpRequest = PatchedXHR;

  window.addEventListener('db9-flow-generate-probe-request', (ev) => {
    try {
      const id = ev && ev.detail && ev.detail.id;
      window.dispatchEvent(new CustomEvent('db9-flow-generate-probe-result', { detail: { id, last: window.__db9FlowLastGenerate } }));
    } catch (_) {}
  });

  window.addEventListener('db9-flow-generate-reset', () => { window.__db9FlowLastGenerate = null; });

  console.log('[DB9-Monitor] page-world fetch/XHR monitor installed (flow)');
})();
