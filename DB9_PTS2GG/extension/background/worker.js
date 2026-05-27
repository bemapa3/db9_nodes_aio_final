// DB9 Multi-Provider Auto - Background Service Worker (v0.4.7.1)
// Maintains persistent WebSocket to local bridge, routes jobs to the correct
// provider tab (gemini, chatgpt, or flow) based on job.provider.

const BRIDGE_WS = 'ws://127.0.0.1:8765/ws';
let ws = null;
let reconnectTimer = null;

function log(...args) { console.log('[DB9-bg]', ...args); }

// Map URL → provider name
function providerForUrl(url) {
  if (!url) return null;
  if (url.startsWith('https://gemini.google.com/')) return 'gemini';
  if (url.startsWith('https://chatgpt.com/') || /^https:\/\/[^/]+\.chatgpt\.com\//.test(url)) return 'chatgpt';
  if (url.startsWith('https://labs.google/fx/')) return 'flow';
  return null;
}

async function listProviderTabs() {
  // Returns { gemini: [tab,...], chatgpt: [tab,...], flow: [tab,...] }
  const tabs = await chrome.tabs.query({ url: [
    'https://gemini.google.com/*',
    'https://chatgpt.com/*',
    'https://*.chatgpt.com/*',
    'https://labs.google/fx/tools/*',
    'https://labs.google/fx/*/tools/*',
    'https://labs.google/fx/*'
  ] });
  const out = { gemini: [], chatgpt: [], flow: [] };
  for (const t of tabs) {
    const p = providerForUrl(t.url || '');
    if (p && out[p]) out[p].push(t);
  }
  return out;
}

async function connectedProviders() {
  const tabs = await listProviderTabs();
  return Object.entries(tabs)
    .filter(([, list]) => list.length > 0)
    .map(([name]) => name);
}

function tabSummary(tab) {
  return { id: tab.id, windowId: tab.windowId, active: !!tab.active, title: tab.title || '', url: tab.url || '', provider: providerForUrl(tab.url || '') };
}

async function inspectDomInTab(tabId) {
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => {
      const visible = (el) => !!el && !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
      const textOf = (el) => String([el.innerText, el.textContent, el.getAttribute?.('aria-label'), el.getAttribute?.('placeholder'), el.getAttribute?.('data-testid')].filter(Boolean).join(' ')).replace(/\s+/g, ' ').trim();
      const item = (el) => ({ tag: (el.tagName || '').toLowerCase(), type: el.getAttribute?.('type') || '', role: el.getAttribute?.('role') || '', ariaLabel: el.getAttribute?.('aria-label') || '', placeholder: el.getAttribute?.('placeholder') || '', testId: el.getAttribute?.('data-testid') || '', contenteditable: el.getAttribute?.('contenteditable') || '', disabled: !!el.disabled || el.getAttribute?.('aria-disabled') === 'true', visible: visible(el), text: textOf(el).slice(0, 180) });
      const buttons = Array.from(document.querySelectorAll('button,[role="button"]')).slice(0, 80).map(item);
      const inputs = Array.from(document.querySelectorAll('textarea,input,[contenteditable="true"],[role="textbox"]')).slice(0, 80).map(item);
      const fileInputs = Array.from(document.querySelectorAll('input[type="file"]')).slice(0, 40).map(item);
      return { href: location.href, title: document.title, readyState: document.readyState, bodyTextStart: (document.body?.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 1000), counts: { buttons: buttons.length, inputs: inputs.length, fileInputs: fileInputs.length, videos: document.querySelectorAll('video').length, images: document.querySelectorAll('img').length }, buttons, inputs, fileInputs };
    }
  });
  return result;
}

async function inspectFlowControlsInTab(tabId) {
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => {
      const visible = (el) => !!el && !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
      const norm = (value) => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/\s+/g, ' ').trim();
      const textOf = (el) => norm([el?.innerText, el?.textContent, el?.getAttribute?.('aria-label'), el?.getAttribute?.('placeholder'), el?.getAttribute?.('data-testid')].filter(Boolean).join(' '));
      const rectOf = (el) => {
        const r = el.getBoundingClientRect();
        return { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) };
      };
      const describe = (el, index) => ({
        index,
        tag: (el.tagName || '').toLowerCase(),
        type: el.getAttribute?.('type') || '',
        role: el.getAttribute?.('role') || '',
        ariaLabel: el.getAttribute?.('aria-label') || '',
        placeholder: el.getAttribute?.('placeholder') || '',
        testId: el.getAttribute?.('data-testid') || '',
        contenteditable: el.getAttribute?.('contenteditable') || '',
        disabled: !!el.disabled || el.getAttribute?.('aria-disabled') === 'true',
        visible: visible(el),
        rect: rectOf(el),
        text: textOf(el).slice(0, 220)
      });
      const allButtons = Array.from(document.querySelectorAll('button,[role="button"]'));
      const allInputs = Array.from(document.querySelectorAll('textarea,input,[contenteditable="true"],[role="textbox"]'));
      const fileInputs = Array.from(document.querySelectorAll('input[type="file"]'));
      const promptCandidates = allInputs.map(describe).filter(item => item.visible && !item.disabled && (item.contenteditable === 'true' || item.role === 'textbox' || item.tag === 'textarea'));
      const createCandidates = allButtons.map(describe).filter(item => item.visible && !item.disabled && /(^| )(tao|create|generate|arrow_forward|send|submit|play_arrow)( |$)/.test(item.text));
      const videoModeCandidates = allButtons.map(describe).filter(item => item.visible && /video|crop_16_9|x2|16:9/.test(item.text));
      const blockedCreateCandidates = allButtons.map(describe).filter(item => item.visible && /(tao canh|create scene|trinh tao canh|scene|canh)/.test(item.text));
      const mediaCandidates = Array.from(document.querySelectorAll('video,img')).map(describe).filter(item => item.visible && item.rect.w >= 120 && item.rect.h >= 90);
      return {
        href: location.href,
        title: document.title,
        readyState: document.readyState,
        bodyTextStart: norm(document.body?.innerText || '').slice(0, 1500),
        counts: { buttons: allButtons.length, inputs: allInputs.length, fileInputs: fileInputs.length, videos: document.querySelectorAll('video').length, images: document.querySelectorAll('img').length },
        promptCandidates,
        fileInputs: fileInputs.map(describe),
        createCandidates,
        videoModeCandidates,
        blockedCreateCandidates,
        mediaCandidates,
        topVisibleButtons: allButtons.map(describe).filter(item => item.visible).slice(0, 50)
      };
    }
  });
  return result;
}

async function inspectFlowMediaDetailsInTab(tabId) {
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => {
      const visible = (el) => !!el && !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
      const normText = (el) => String([el?.innerText, el?.textContent, el?.getAttribute?.('aria-label'), el?.getAttribute?.('title'), el?.getAttribute?.('data-testid')].filter(Boolean).join(' ')).replace(/\s+/g, ' ').trim();
      const rectOf = (el) => { const r = el.getBoundingClientRect(); return { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) }; };
      const attrsOf = (el) => {
        const attrs = {};
        for (const name of ['src','currentSrc','href','aria-label','title','role','type','data-testid','data-media-id','data-id']) {
          const value = name === 'currentSrc' ? el.currentSrc : el.getAttribute?.(name);
          if (value) attrs[name] = String(value).slice(0, 500);
        }
        return attrs;
      };
      const brief = (el) => el ? ({ tag: (el.tagName || '').toLowerCase(), visible: visible(el), rect: rectOf(el), text: normText(el).slice(0, 260), attrs: attrsOf(el) }) : null;
      const media = Array.from(document.querySelectorAll('video,img')).filter(el => visible(el) && el.getBoundingClientRect().width >= 120 && el.getBoundingClientRect().height >= 90);
      const items = media.map((el, index) => {
        let card = el;
        for (let i = 0; i < 6 && card?.parentElement; i++) {
          const p = card.parentElement;
          const r = p.getBoundingClientRect();
          if ((p.getAttribute('role') === 'button' || p.querySelector?.('button,[role="button"],a[href]')) && r.width >= 120 && r.height >= 90) { card = p; break; }
          card = p;
        }
        const scoped = card || el;
        const controls = Array.from(scoped.querySelectorAll?.('button,[role="button"],a[href],video,img,source') || []).slice(0, 30).map(brief);
        return { index, media: brief(el), card: brief(scoped), controls };
      });
      return { href: location.href, title: document.title, counts: { media: items.length, videos: document.querySelectorAll('video').length, images: document.querySelectorAll('img').length }, latest: items[0] || null, items: items.slice(0, 12) };
    }
  });
  return result;
}
async function openLatestFlowMediaInTab(tabId) {
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => {
      const visible = (el) => !!el && !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
      const media = Array.from(document.querySelectorAll('img')).filter(el => visible(el) && el.getBoundingClientRect().width >= 120 && el.getBoundingClientRect().height >= 90);
      const img = media[0] || null;
      const link = img ? img.closest('a[href]') : null;
      if (!link) return { ok: false, error: 'latest media link not found' };
      const href = link.href;
      link.click();
      return { ok: true, href };
    }
  });
  await new Promise(r => setTimeout(r, 2500));
  const [{ result: details }] = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => {
      const visible = (el) => !!el && !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
      const textOf = (el) => String([el?.innerText, el?.textContent, el?.getAttribute?.('aria-label'), el?.getAttribute?.('title'), el?.getAttribute?.('data-testid')].filter(Boolean).join(' ')).replace(/\s+/g, ' ').trim();
      const rectOf = (el) => { const r = el.getBoundingClientRect(); return { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) }; };
      const attrsOf = (el) => {
        const attrs = {};
        for (const name of ['src','currentSrc','href','aria-label','title','role','type','data-testid','download']) {
          const value = name === 'currentSrc' ? el.currentSrc : el.getAttribute?.(name);
          if (value) attrs[name] = String(value).slice(0, 500);
        }
        return attrs;
      };
      const brief = (el) => ({ tag: (el.tagName || '').toLowerCase(), visible: visible(el), rect: rectOf(el), text: textOf(el).slice(0, 260), attrs: attrsOf(el) });
      return {
        href: location.href,
        title: document.title,
        bodyTextStart: (document.body?.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 1800),
        counts: { videos: document.querySelectorAll('video').length, images: document.querySelectorAll('img').length, anchors: document.querySelectorAll('a[href]').length, buttons: document.querySelectorAll('button,[role="button"]').length },
        media: Array.from(document.querySelectorAll('video,source,img')).filter(visible).slice(0, 30).map(brief),
        controls: Array.from(document.querySelectorAll('button,[role="button"],a[href]')).filter(visible).slice(0, 80).map(brief)
      };
    }
  });
  return { navigation: result, details };
}
async function inspectFlowModelMenuInTab(tabId) {
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId },
    func: async () => {
      const sleep = (ms) => new Promise(r => setTimeout(r, ms));
      const visible = (el) => !!el && !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
      const norm = (value) => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/\s+/g, ' ').trim();
      const textOf = (el) => norm([el?.innerText, el?.textContent, el?.getAttribute?.('aria-label'), el?.getAttribute?.('title'), el?.getAttribute?.('data-testid')].filter(Boolean).join(' '));
      const rectOf = (el) => { const r = el.getBoundingClientRect(); return { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) }; };
      const brief = (el) => ({ tag: (el.tagName || '').toLowerCase(), role: el.getAttribute?.('role') || '', type: el.getAttribute?.('type') || '', visible: visible(el), rect: rectOf(el), text: textOf(el).slice(0, 260) });
      const controlsBefore = Array.from(document.querySelectorAll('button,[role="button"],[role="option"],[role="menuitem"],[role="tab"]')).filter(visible).map(brief).slice(0, 120);
      const model = Array.from(document.querySelectorAll('button,[role="button"]')).filter(visible).find(el => /banana|veo|video|crop_16_9|16:9/.test(textOf(el)));
      if (model) model.click();
      await sleep(900);
      const controlsAfter = Array.from(document.querySelectorAll('button,[role="button"],[role="option"],[role="menuitem"],[role="tab"],mat-option,[data-testid]')).filter(visible).map(brief).slice(0, 180);
      return { href: location.href, clicked: model ? brief(model) : null, controlsBefore, controlsAfter, bodyTextStart: norm(document.body?.innerText || '').slice(0, 2500) };
    }
  });
  return result;
}
async function handleInspectRequest(msg) {
  try {
    if (msg.action === 'tabs') {
      const tabs = await listProviderTabs();
      sendToBridge({ type: 'inspect-response', requestId: msg.requestId, result: { tabs: Object.fromEntries(Object.entries(tabs).map(([k, list]) => [k, list.map(tabSummary)])) } });
      return;
    }
    if (msg.action === 'dom') {
      const provider = msg.provider || 'flow';
      const tab = await ensureProviderTab(provider);
      let snapshot;
      try { snapshot = await inspectDomInTab(tab.id); }
      catch (_) { await injectProviderScripts(tab.id, provider).catch(() => {}); snapshot = await inspectDomInTab(tab.id); }
      sendToBridge({ type: 'inspect-response', requestId: msg.requestId, result: { provider, tab: tabSummary(tab), snapshot } });
      return;
    }
    if (msg.action === 'flow-diagnostics') {
      const tab = await ensureProviderTab('flow');
      let diagnostics;
      try { diagnostics = await inspectFlowControlsInTab(tab.id); }
      catch (_) { await injectProviderScripts(tab.id, 'flow').catch(() => {}); diagnostics = await inspectFlowControlsInTab(tab.id); }
      sendToBridge({ type: 'inspect-response', requestId: msg.requestId, result: { provider: 'flow', tab: tabSummary(tab), diagnostics } });
      return;
    }
    if (msg.action === 'flow-media-details') {
      const tab = await ensureProviderTab('flow');
      let mediaDetails;
      try { mediaDetails = await inspectFlowMediaDetailsInTab(tab.id); }
      catch (_) { await injectProviderScripts(tab.id, 'flow').catch(() => {}); mediaDetails = await inspectFlowMediaDetailsInTab(tab.id); }
      sendToBridge({ type: 'inspect-response', requestId: msg.requestId, result: { provider: 'flow', tab: tabSummary(tab), mediaDetails } });
      return;
    }
    if (msg.action === 'flow-open-latest-media') {
      const tab = await ensureProviderTab('flow');
      const opened = await openLatestFlowMediaInTab(tab.id);
      sendToBridge({ type: 'inspect-response', requestId: msg.requestId, result: { provider: 'flow', tab: tabSummary(tab), opened } });
      return;
    }
    if (msg.action === 'flow-model-menu') {
      const tab = await ensureProviderTab('flow');
      const modelMenu = await inspectFlowModelMenuInTab(tab.id);
      sendToBridge({ type: 'inspect-response', requestId: msg.requestId, result: { provider: 'flow', tab: tabSummary(tab), modelMenu } });
      return;
    }
    if (msg.action === 'evaluate') {
      const tab = await ensureProviderTab(msg.provider || 'gemini');
      let result;
      try {
        const codeToEval = msg.code || `
          (() => {
            const els = Array.from(document.querySelectorAll('*')).filter(el => {
              const t = el.tagName.toLowerCase();
              const a = (el.getAttribute('aria-label') || '').toLowerCase();
              const c = (el.className && typeof el.className === 'string') ? el.className.toLowerCase() : '';
              return t.includes('preview') || t.includes('chip') || t.includes('thumbnail') || a.includes('upload') || c.includes('upload');
            });
            return els.map(el => ({ tag: el.tagName, ariaLabel: el.getAttribute('aria-label'), testId: el.getAttribute('data-test-id'), class: el.className }));
          })()
        `;
        const results = await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          args: [codeToEval],
          func: (codeStr) => {
            try {
              return window.eval(codeStr);
            } catch (err) { return 'Error: ' + err.message; }
          }
        });
        result = results[0]?.result;
      } catch (err) { result = 'Execution Error: ' + err.message; }
      sendToBridge({ type: 'inspect-response', requestId: msg.requestId, result });
      return;
    }
    sendToBridge({ type: 'inspect-response', requestId: msg.requestId, error: 'unknown inspect action: ' + msg.action });
  } catch (error) {
    sendToBridge({ type: 'inspect-response', requestId: msg.requestId, error: error.message });
  }
}

function connect() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
  log('connecting to bridge...');
  ws = new WebSocket(BRIDGE_WS);

  ws.onopen = async () => {
    log('✅ connected to bridge');
    chrome.action.setBadgeText({ text: 'ON' });
    chrome.action.setBadgeBackgroundColor({ color: '#16a34a' });
    // Announce which providers we have tabs for
    const providers = await connectedProviders();
    log('hello providers=', providers);
    sendToBridge({ type: 'hello-extension', version: '0.4.7.1', providers });
  };

  ws.onmessage = async (e) => {
    let msg;
    try { msg = JSON.parse(e.data); } catch { return; }
    if (msg.type === 'hello') { log('bridge hello:', msg.version); return; }
    if (msg.type === 'inspect-request') {
      await handleInspectRequest(msg);
      return;
    }
    if (msg.type === 'job') {
      const provider = msg.provider || 'gemini';
      log(`📦 received job ${msg.jobId.slice(0, 8)} (${msg.mode}) provider=${provider}`);
      await dispatchToProviderTab(msg, provider);
    }
  };

  ws.onclose = () => {
    log('❌ disconnected, retry in 3s');
    chrome.action.setBadgeText({ text: 'OFF' });
    chrome.action.setBadgeBackgroundColor({ color: '#dc2626' });
    clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(connect, 3000);
  };

  ws.onerror = (e) => { log('ws error', e); };
}

function sendToBridge(obj) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
}

async function ensureProviderTab(provider) {
  const tabs = await listProviderTabs();
  if (tabs[provider] && tabs[provider].length > 0) return tabs[provider][0];

  // Open one
  const url = provider === 'chatgpt'
    ? 'https://chatgpt.com/'
    : provider === 'flow'
      ? 'https://labs.google/fx/tools/flow'
      : 'https://gemini.google.com/app';
  log(`no ${provider} tab found, opening ${url}...`);
  const tab = await chrome.tabs.create({ url, active: false });
  // Wait a bit for content script to load
  await new Promise(r => setTimeout(r, 4500));
  return tab;
}

async function injectProviderScripts(tabId, provider) {
  const providerFile = provider === 'chatgpt'
    ? 'content/provider-chatgpt.js'
    : provider === 'flow'
      ? 'content/provider-flow.js'
      : 'content/provider-gemini.js';
  log(`injecting content scripts into tab ${tabId} for ${provider}`);
  await chrome.scripting.executeScript({ target: { tabId }, files: [providerFile] });
  await chrome.scripting.executeScript({ target: { tabId }, files: ['content/content-script.js'] });
  await new Promise(r => setTimeout(r, 500));
}

async function ensureProviderReady(tabId, provider) {
  // Inject first, then ping — not ping-then-inject
  log(`injecting scripts into tab ${tabId} for ${provider}`);
  try { await injectProviderScripts(tabId, provider); } catch (e) {
    log(`initial inject warning: ${e.message}`);
  }
  await new Promise(r => setTimeout(r, 2000)); // wait for orchestrator to register listener

  for (let attempt = 1; attempt <= 5; attempt++) {
    try {
      const resp = await chrome.tabs.sendMessage(tabId, { type: 'who-are-you' });
      if (resp && resp.ok && resp.provider === provider && resp.ready !== false) {
        log(`✓ provider ${provider} ready in tab ${tabId} (attempt ${attempt})`);
        return true;
      }
      if (resp && resp.ok && resp.ready === false) {
        log(`provider ${provider} listener alive but not ready yet (attempt ${attempt}), waiting...`);
        await new Promise(r => setTimeout(r, 1000));
        continue;
      }
    } catch (e) {
      log(`ping attempt ${attempt} failed: ${e.message}`);
      if (attempt === 3) {
        // Re-inject once if mid-run pings keep failing
        try { await injectProviderScripts(tabId, provider); } catch (_) {}
        await new Promise(r => setTimeout(r, 1500));
      }
    }
    await new Promise(r => setTimeout(r, 800));
  }
  throw new Error(`provider ${provider} did not become ready in tab ${tabId}`);
}

async function dispatchToProviderTab(job, provider) {
  if (provider === 'auto') {
    const [active] = await chrome.tabs.query({ active: true, currentWindow: true });
    provider = providerForUrl(active && active.url) || 'gemini';
  }
  if (provider !== 'gemini' && provider !== 'chatgpt' && provider !== 'flow') {
    log(`unknown provider "${provider}", rejecting`);
    sendToBridge({ type: 'job-error', jobId: job.jobId, error: `unknown provider: ${provider}` });
    return;
  }

  try {
    const tab = await ensureProviderTab(provider);
    log(`selected tab ${tab.id} for provider ${provider}. URL: ${tab.url || '(none)'}`);

    // Ensure the content script and provider script are active and responsive before proceeding
    await ensureProviderReady(tab.id, provider);

    // Large payload storage indirection
    const LARGE_PAYLOAD_THRESHOLD = 1 * 1024 * 1024; // 1MB base64
    const imageB64 = job.imageBase64 || '';
    let messageJob = { ...job };
    if (imageB64.length > LARGE_PAYLOAD_THRESHOLD) {
      const storageKey = 'db9_payload_' + job.jobId;
      await chrome.storage.session.set({ [storageKey]: imageB64 });
      messageJob = { ...job, imageBase64: null, imageStorageKey: storageKey };
      log(`large payload stored in session storage key=${storageKey} size=${imageB64.length}`);
    }

    log(`forwarding job ${job.jobId.slice(0, 8)} → tab ${tab.id} (${provider})`);
    await chrome.tabs.sendMessage(tab.id, { type: 'run-job', job: messageJob });
    sendToBridge({ type: 'job-status', jobId: job.jobId, status: 'running', provider });
  } catch (err) {
    log(`failed to forward job to ${provider}: ${err.message}`);
    sendToBridge({ type: 'job-error', jobId: job.jobId, provider, error: 'no content script: ' + err.message });
  }
}

// Receive results from content scripts (any provider)
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'job-result' || msg.type === 'job-error' || msg.type === 'job-status' || msg.type === 'log' || msg.type === 'action-log') {
    sendToBridge(msg);
  }
  if (msg.type === 'ping-bridge') {
    (async () => {
      const providers = await connectedProviders();
      sendResponse({
        connected: ws && ws.readyState === WebSocket.OPEN,
        providers
      });
    })();
    return true; // async
  }
  return true;
});

// React to tab updates so the bridge can know provider availability changes
chrome.tabs.onUpdated.addListener(async (tabId, info, tab) => {
  if (info.status === 'complete' && providerForUrl(tab.url || '')) {
    const providers = await connectedProviders();
    log('providers-update providers=', providers);
    sendToBridge({ type: 'providers-update', providers });
  }
});
chrome.tabs.onRemoved.addListener(async () => {
  const providers = await connectedProviders();
  sendToBridge({ type: 'providers-update', providers });
});

connect();

// Keep service worker alive
setInterval(() => { if (ws && ws.readyState === WebSocket.OPEN) ws.send('{"type":"ping"}'); }, 25000);


