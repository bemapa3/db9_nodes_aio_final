// DB9 Multi-Provider Auto - Background Service Worker (v0.4.7.1)
// Maintains persistent WebSocket to local bridge, routes jobs to the correct
// provider tab (gemini or chatgpt) based on job.provider.

const BRIDGE_WS = 'ws://127.0.0.1:8765/ws';
let ws = null;
let reconnectTimer = null;

function log(...args) { console.log('[DB9-bg]', ...args); }

// Map URL → provider name
function providerForUrl(url) {
  if (!url) return null;
  if (url.startsWith('https://gemini.google.com/')) return 'gemini';
  if (url.startsWith('https://chatgpt.com/') || /^https:\/\/[^/]+\.chatgpt\.com\//.test(url)) return 'chatgpt';
  return null;
}

async function listProviderTabs() {
  // Returns { gemini: [tab,...], chatgpt: [tab,...] }
  const tabs = await chrome.tabs.query({ url: [
    'https://gemini.google.com/*',
    'https://chatgpt.com/*',
    'https://*.chatgpt.com/*'
  ] });
  const out = { gemini: [], chatgpt: [] };
  for (const t of tabs) {
    const p = providerForUrl(t.url || '');
    if (p && out[p]) out[p].push(t);
  }
  return out;
}

async function connectedProviders() {
  const tabs = await listProviderTabs();
  return Object.entries(tabs)
    .filter(([_, list]) => list.length > 0)
    .map(([name]) => name);
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
    sendToBridge({ type: 'hello-extension', version: '0.4.7.1', providers });
  };

  ws.onmessage = async (e) => {
    let msg;
    try { msg = JSON.parse(e.data); } catch { return; }
    if (msg.type === 'hello') { log('bridge hello:', msg.version); return; }
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
  const url = provider === 'chatgpt' ? 'https://chatgpt.com/' : 'https://gemini.google.com/app';
  log(`no ${provider} tab found, opening ${url}...`);
  const tab = await chrome.tabs.create({ url, active: false });
  // Wait a bit for content script to load
  await new Promise(r => setTimeout(r, 4500));
  return tab;
}

async function dispatchToProviderTab(job, provider) {
  if (provider !== 'gemini' && provider !== 'chatgpt') {
    log(`unknown provider "${provider}", rejecting`);
    sendToBridge({ type: 'job-error', jobId: job.jobId, error: `unknown provider: ${provider}` });
    return;
  }
  const tab = await ensureProviderTab(provider);
  log(`forwarding job ${job.jobId.slice(0, 8)} → tab ${tab.id} (${provider})`);
  try {
    await chrome.tabs.sendMessage(tab.id, { type: 'run-job', job });
    sendToBridge({ type: 'job-status', jobId: job.jobId, status: 'running', provider });
  } catch (e) {
    log('failed to forward job:', e.message);
    sendToBridge({ type: 'job-error', jobId: job.jobId, provider, error: 'no content script: ' + e.message });
  }
}

// Receive results from content scripts (any provider)
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'job-result' || msg.type === 'job-error' || msg.type === 'job-status' || msg.type === 'log') {
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
