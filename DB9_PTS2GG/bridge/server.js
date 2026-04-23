// DB9 Multi-Provider Bridge - v0.4.7.1
// Local server connecting Photoshop UXP plugin and Chrome extension.
// Port 8765 HTTP for Photoshop, WebSocket /ws for extension.
//
// v0.4.7.1 changes:
//   • CORS preflight (OPTIONS) handled, Access-Control-Allow-* on every response
//   • provider="both" → spawns child jobs for gemini + chatgpt in parallel
//   • New /job/:parentId/dual endpoint returns combined status of both children
//   • /presets endpoint REMOVED — preset library now lives in the UXP plugin
//   • /health reports {ok, version, providers, extensionsConnected, activeJobs}

const http = require('http');
const { WebSocketServer } = require('ws');
const crypto = require('crypto');

const VERSION = '0.4.7.1';
const PORT = 8765;
const SUPPORTED_PROVIDERS = new Set(['gemini', 'chatgpt']);

// jobs: jobId -> { id, status, createdAt, prompt, mode, chatId, provider, parentId? }
const jobs = new Map();
// dualParents: parentId -> { id, createdAt, childJobs:[{jobId,provider}] }
const dualParents = new Map();
const extSockets = new Set();
const recentResults = new Map();   // jobId -> { imageBase64, mime, sourceUrl, provider, finishedAt, error? }
const connectedProviders = new Set();

function broadcast(obj) {
  const msg = JSON.stringify(obj);
  for (const ws of extSockets) {
    if (ws.readyState === ws.OPEN) ws.send(msg);
  }
}

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization',
  'Access-Control-Max-Age': '600'
};

function jsonRes(res, code, obj) {
  res.writeHead(code, { 'Content-Type': 'application/json', ...CORS_HEADERS });
  res.end(JSON.stringify(obj));
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on('data', c => chunks.push(c));
    req.on('end', () => {
      try { resolve(JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}')); }
      catch (e) { reject(e); }
    });
    req.on('error', reject);
  });
}

function dispatchSingle(provider, body) {
  const jobId = crypto.randomUUID();
  const presetIds = Array.isArray(body.presetIds) ? body.presetIds.slice(0, 16) : [];
  const job = {
    id: jobId,
    status: 'pending',
    createdAt: Date.now(),
    prompt: body.prompt,
    mode: body.mode || 'new',
    chatId: body.chatId || null,
    provider,
    presetIds,
    parentId: body._parentId || null
  };
  jobs.set(jobId, job);
  broadcast({
    type: 'job',
    jobId,
    provider,
    prompt: body.prompt,
    mode: body.mode || 'new',
    chatId: body.chatId || null,
    model: body.model || (provider === 'chatgpt' ? 'gpt-4o-image' : 'nano-banana-pro'),
    imageBase64: body.imageBase64,
    mime: body.mime || 'image/png',
    presetIds
  });
  return jobId;
}

const server = http.createServer(async (req, res) => {
  // CORS preflight
  if (req.method === 'OPTIONS') {
    res.writeHead(204, CORS_HEADERS);
    return res.end();
  }

  // --- Health ---
  if (req.url === '/health') {
    return jsonRes(res, 200, {
      ok: true,
      version: VERSION,
      extensionsConnected: extSockets.size,
      providers: Array.from(connectedProviders),
      activeJobs: jobs.size
    });
  }

  // --- Submit a generation job ---
  // POST /generate { imageBase64, mime, prompt, mode, provider?, chatId?, model?, presetIds?[] }
  // provider may be "gemini" | "chatgpt" | "both"
  if (req.url === '/generate' && req.method === 'POST') {
    try {
      const body = await readBody(req);
      if (!body.imageBase64 || !body.prompt) {
        return jsonRes(res, 400, { error: 'imageBase64 and prompt required' });
      }
      const provider = (body.provider || 'gemini').toLowerCase();
      if (provider !== 'both' && !SUPPORTED_PROVIDERS.has(provider)) {
        return jsonRes(res, 400, {
          error: `unsupported provider "${provider}". Supported: gemini, chatgpt, both`
        });
      }
      if (extSockets.size === 0) {
        return jsonRes(res, 503, {
          error: 'No DB9 extension connected. Open the extension and a provider tab.'
        });
      }

      // ---- DUAL MODE ----
      if (provider === 'both') {
        const parentId = crypto.randomUUID();
        const childGem = dispatchSingle('gemini', { ...body, _parentId: parentId });
        const childChat = dispatchSingle('chatgpt', { ...body, _parentId: parentId });
        dualParents.set(parentId, {
          id: parentId,
          createdAt: Date.now(),
          childJobs: [
            { jobId: childGem, provider: 'gemini' },
            { jobId: childChat, provider: 'chatgpt' }
          ]
        });
        return jsonRes(res, 200, {
          jobId: parentId,
          status: 'queued',
          provider: 'both',
          childJobs: dualParents.get(parentId).childJobs
        });
      }

      // ---- SINGLE ----
      const providerOnline = connectedProviders.has(provider);
      const jobId = dispatchSingle(provider, body);
      return jsonRes(res, 200, { jobId, status: 'queued', provider, providerOnline });
    } catch (e) {
      return jsonRes(res, 500, { error: e.message });
    }
  }

  // --- Dual-job poll: GET /job/:parentId/dual ---
  const dualMatch = req.url.match(/^\/job\/([^/]+)\/dual$/);
  if (dualMatch && req.method === 'GET') {
    const parentId = dualMatch[1];
    const parent = dualParents.get(parentId);
    if (!parent) return jsonRes(res, 404, { error: 'parent job not found (or expired)' });
    const children = parent.childJobs.map(c => {
      const result = recentResults.get(c.jobId);
      const job = jobs.get(c.jobId);
      if (result) {
        return { provider: c.provider, jobId: c.jobId, status: result.error ? 'error' : 'done', ...result };
      }
      if (job) return { provider: c.provider, jobId: c.jobId, status: job.status };
      return { provider: c.provider, jobId: c.jobId, status: 'unknown' };
    });
    const results = Object.fromEntries(children.map(child => [child.provider, child]));
    const allDone = children.every(c => c.status === 'done' || c.status === 'error');
    const status = allDone
      ? (children.every(c => c.status === 'done') ? 'complete'
         : children.some(c => c.status === 'done') ? 'partial' : 'error')
      : 'pending';
    return jsonRes(res, 200, { parentId, status, children, results });
  }

  // --- Single job poll ---
  if (req.url.startsWith('/job/') && req.method === 'GET') {
    const id = req.url.split('/')[2];
    const job = jobs.get(id);
    const result = recentResults.get(id);
    if (result) {
      return jsonRes(res, 200, { status: result.error ? 'error' : 'done', ...result });
    }
    if (!job) return jsonRes(res, 404, { error: 'job not found' });
    return jsonRes(res, 200, {
      status: job.status,
      provider: job.provider,
      createdAt: job.createdAt,
      ageMs: Date.now() - job.createdAt
    });
  }

  return jsonRes(res, 404, { error: 'not found' });
});

const wss = new WebSocketServer({ server, path: '/ws' });
wss.on('connection', (ws) => {
  extSockets.add(ws);
  console.log(`[bridge] extension connected (total: ${extSockets.size})`);
  ws.send(JSON.stringify({ type: 'hello', version: VERSION }));

  ws.on('message', (data) => {
    let msg;
    try { msg = JSON.parse(data.toString()); } catch { return; }

    if (msg.type === 'hello-extension' || msg.type === 'providers-update') {
      connectedProviders.clear();
      (msg.providers || []).forEach(p => connectedProviders.add(p));
      console.log(`[bridge] providers online: ${Array.from(connectedProviders).join(', ') || '(none)'}`);
    }
    if (msg.type === 'job-status') {
      const job = jobs.get(msg.jobId);
      if (job) {
        job.status = msg.status;
        console.log(`[bridge] job ${msg.jobId.slice(0, 8)} → ${msg.status} (${msg.provider || job.provider})`);
      }
    }
    if (msg.type === 'job-result') {
      const { jobId, imageBase64, mime, sourceUrl, chatId, provider, text, description } = msg;
      const job = jobs.get(jobId);
      recentResults.set(jobId, {
        imageBase64,
        resultBase64: imageBase64 || null,
        mime: mime || 'image/png',
        sourceUrl: sourceUrl || '',
        chatId: chatId || null,
        provider: provider || (job && job.provider) || 'gemini',
        text: text || description || null,
        finishedAt: Date.now()
      });
      jobs.delete(jobId);
      console.log(`[bridge] ✅ job ${jobId.slice(0, 8)} done [${provider || (job && job.provider)}] (${(imageBase64?.length || 0) / 1024 | 0} KB)`);
      setTimeout(() => recentResults.delete(jobId), 5 * 60 * 1000);
    }
    if (msg.type === 'job-error') {
      const { jobId, error, provider } = msg;
      const job = jobs.get(jobId);
      if (job) job.status = 'error';
      recentResults.set(jobId, {
        error: error || 'unknown',
        provider: provider || (job && job.provider) || 'gemini',
        finishedAt: Date.now()
      });
      console.log(`[bridge] ❌ job ${jobId.slice(0, 8)} error [${provider || (job && job.provider)}]: ${error}`);
      setTimeout(() => recentResults.delete(jobId), 5 * 60 * 1000);
    }
    if (msg.type === 'log') {
      console.log(`[ext] ${msg.text}`);
    }
  });

  ws.on('close', () => {
    extSockets.delete(ws);
    if (extSockets.size === 0) connectedProviders.clear();
    console.log(`[bridge] extension disconnected (total: ${extSockets.size})`);
  });
});

// Cleanup stale jobs (>5 min) and dual parents (>10 min)
setInterval(() => {
  const now = Date.now();
  for (const [id, job] of jobs) {
    if (now - job.createdAt > 5 * 60 * 1000) {
      jobs.delete(id);
      console.log(`[bridge] gc stale job ${id.slice(0, 8)}`);
    }
  }
  for (const [id, parent] of dualParents) {
    if (now - parent.createdAt > 10 * 60 * 1000) {
      dualParents.delete(id);
    }
  }
}, 60 * 1000);

server.listen(PORT, '127.0.0.1', () => {
  console.log(`╔════════════════════════════════════════════╗`);
  console.log(`║  DB9 Multi-Provider Bridge v${VERSION}         ║`);
  console.log(`║  HTTP:  http://127.0.0.1:${PORT}              ║`);
  console.log(`║  WS:    ws://127.0.0.1:${PORT}/ws             ║`);
  console.log(`║  Providers: gemini, chatgpt, both          ║`);
  console.log(`╚════════════════════════════════════════════╝`);
  console.log(`Waiting for extension to connect...`);
});
