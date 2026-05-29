// DB9 Multi-Provider â€” Shared Orchestrator (v0.4.7.6)
// Loaded AFTER one of the provider-*.js modules (which sets window.__DB9_PROVIDER).
// Drives the same job lifecycle for every provider via the provider interface:
//   { name, installNetworkMonitor, waitReady, startNewChat, toggleCreateImage,
//     uploadImage, waitForUploadPreview, submitPrompt, waitForOutput,
//     downloadHD, countBaseline, promptInput }

(async () => {
  const ORCHESTRATOR_BUILD = 'orchestrator-reloadable-20260516-1148';
  if (window.__db9OrchestratorCleanup) {
    try { window.__db9OrchestratorCleanup(); } catch (_) {}
  }
  window.__db9OrchestratorLoaded = true;
  window.__db9OrchestratorBuild = ORCHESTRATOR_BUILD;

  // STEP 1: Register who-are-you responder immediately — before any async wait
  let _providerName = null;
  let _providerReady = false;
  const earlyMessageHandler = (msg, sender, sendResponse) => {
    if (msg.type === 'who-are-you') {
      sendResponse({ ok: true, provider: _providerName, ready: _providerReady });
      return true;
    }
    return true;
  };
  chrome.runtime.onMessage.addListener(earlyMessageHandler);
  window.__db9OrchestratorCleanup = () => {
    try { chrome.runtime.onMessage.removeListener(earlyMessageHandler); } catch (_) {}
  };

  function detectProviderFromDOM() {
    const url = location.href;

    // Gemini
    if (url.includes('gemini.google.com')) {
      const hasComposer = !!(
        document.querySelector('rich-textarea, [data-testid="text-input"], textarea[aria-label], [contenteditable="true"]') ||
        document.querySelector('.ql-editor, [data-placeholder], p[data-placeholder]') ||
        document.querySelector('model-picker, gemini-header, .gemini-header')
      );
      return hasComposer ? 'gemini' : null;
    }

    // ChatGPT
    if (url.includes('chatgpt.com')) {
      const hasComposer = !!(
        document.querySelector('#prompt-textarea, [data-testid="send-button"], [data-id="root"]')
      );
      return hasComposer ? 'chatgpt' : null;
    }

    return null;
  }

  async function detectProviderWithDOM(timeoutMs = 8000) {
    if (window.__DB9_PROVIDER) return window.__DB9_PROVIDER;

    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      if (window.__DB9_PROVIDER) return window.__DB9_PROVIDER;

      const domProvider = detectProviderFromDOM();
      if (domProvider) {
        console.log(`[DB9 content] DOM scan detected provider=${domProvider} at ${location.href}`);
        return { name: domProvider, _domDetected: true };
      }

      await new Promise(r => setTimeout(r, 300));
    }
    return null;
  }

  let provider = null;
  const providerResult = await detectProviderWithDOM();
  if (!providerResult) {
    console.error('[DB9] no provider module detected via DOM scan or window.__DB9_PROVIDER after wait.');
    window.__db9OrchestratorLoaded = false;
    return; // listener stays registered, responds ready:false
  }

  if (window.__DB9_PROVIDER) {
    provider = window.__DB9_PROVIDER;
  }

  // Remove the early listener as we are switching to the main orchestrator handler
  chrome.runtime.onMessage.removeListener(earlyMessageHandler);

  const PROVIDER_NAME = providerResult.name;
  _providerName = PROVIDER_NAME;
  _providerReady = true;
  console.log(`[DB9-Orchestrator] v0.4.7.6 build=${ORCHESTRATOR_BUILD} loaded for provider="${PROVIDER_NAME}" on`, location.href);

  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const rand = (min, max) => min + Math.random() * (max - min);

  function log(text) {
    console.log(`[DB9-${PROVIDER_NAME}]`, text);
    try { chrome.runtime.sendMessage({ type: 'log', text: `[${PROVIDER_NAME}] ${text}` }); } catch (e) {}
  }

  // Install the per-provider page-world monitor as early as possible.
  if (provider) {
    try { provider.installNetworkMonitor && provider.installNetworkMonitor(); } catch (e) {
      log('installNetworkMonitor threw: ' + e.message);
    }
  }

  // ===== Main job runner =====
  // v0.4.7.2: presets/negatives are now composed on the UXP side. The extension
  // receives the final prompt string as-is and just drives the browser UI.
  async function runJob(job) {
    // If provider is not loaded yet, wait up to 4000ms
    if (!provider) {
      log('job received but window.__DB9_PROVIDER not set yet. Waiting up to 4000ms...');
      const startWait = Date.now();
      while (Date.now() - startWait < 4000) {
        if (window.__DB9_PROVIDER) {
          provider = window.__DB9_PROVIDER;
          break;
        }
        await sleep(200);
      }
    }
    if (!provider) {
      throw new Error('window.__DB9_PROVIDER automation module is missing or failed to load');
    }

    if (job.imageStorageKey) {
      try {
        log(`retrieving large payload from storage key=${job.imageStorageKey} useLocalStore=${!!job.useLocalStore}`);
        const store = job.useLocalStore ? chrome.storage.local : (chrome.storage.session || chrome.storage.local);
        if (!store) throw new Error('No storage API available in content script');
        
        const result = await store.get(job.imageStorageKey);
        job.imageBase64 = result[job.imageStorageKey] || null;
        await store.remove(job.imageStorageKey);
        log(`storage retrieved: key=${job.imageStorageKey} length=${job.imageBase64 ? job.imageBase64.length : 'NULL'}`);
      } catch (storageError) {
        throw new Error('Storage retrieval failed for key=' + job.imageStorageKey + ': ' + storageError.message);
      }
      if (!job.imageBase64) {
        throw new Error('Storage retrieval returned null for key=' + job.imageStorageKey + '. Extension may need reload.');
      }
    }
    const { jobId, mode, imageBase64, mime, skipUpload } = job;
    const prompt = job.prompt || '';
    log(`▶ runJob ${jobId.slice(0, 8)} mode=${mode} promptChars=${prompt.length}`);
    if (provider) provider.activeJobId = jobId;

    try {
      if (mode === 'new') {
        await provider.startNewChat();
      }

      // Wait for the page to render the prompt input
      const ready = await provider.waitReady(15000);
      if (!ready) throw new Error('prompt input never appeared');

      // v0.4.7.2: describe-only mode â€” upload image, ask for text only, no Create Image
      const isDescribeOnly = (mode === 'describe-only');

      if (!isDescribeOnly) await provider.toggleCreateImage();
      
      // Capture baseline previews and output count BEFORE upload
      const baselinePreviews = provider.uploadPreviewImages ? provider.uploadPreviewImages() : [];
      const baseline = provider.countBaseline();
      
      if (skipUpload) {
        log('text-to-image job: skipping image upload');
      } else {
        log(`baseline upload previews=${baselinePreviews.length} output=${baseline}`);
        if (!imageBase64 || imageBase64.length < 64) throw new Error('uploadImage: missing imageBase64 payload');
        log(`uploadImage: payload=${Math.round(imageBase64.length / 1024)}KB mime=${mime || 'image/png'}`);

        try {
          await provider.uploadImage(imageBase64, mime, baselinePreviews);
        } catch (e) {
          throw new Error('uploadImage failed: ' + (e && e.message ? e.message : e));
        }
        try {
          await provider.waitForUploadPreview(baselinePreviews);
        } catch (e) {
          throw new Error('waitForUploadPreview failed: ' + (e && e.message ? e.message : e));
        }
        await sleep(rand(300, 600));
      }

      try {
        await provider.submitPrompt(prompt);
      } catch (e) {
        throw new Error('submitPrompt failed: ' + (e && e.message ? e.message : e));
      }

      if (isDescribeOnly) {
        // Wait for text response (no image generated)
        const text = await waitForTextResponse(40000);
        log('  âœ“ description received (' + text.length + ' chars)');
        chrome.runtime.sendMessage({
          type: 'job-result',
          jobId,
          provider: PROVIDER_NAME,
          text,
          chatId: location.pathname.split('/').pop()
        });
        log(`âœ… describe job ${jobId.slice(0, 8)} completed`);
        return;
      }

      const imgEl = await provider.waitForOutput(baseline, undefined, { mode });
      const { base64, mime: outMime } = await provider.downloadHD(imgEl);
      const isVideo = /^video\//i.test(outMime || '');

      chrome.runtime.sendMessage({
        type: 'job-result',
        jobId,
        provider: PROVIDER_NAME,
        imageBase64: isVideo ? null : base64,
        videoBase64: isVideo ? base64 : null,
        mime: outMime,
        sourceUrl: imgEl.src,
        chatId: location.pathname.split('/').pop()
      });
      log(`âœ… job ${jobId.slice(0, 8)} completed`);

      // Always return to the main project directory after completion
      try {
        if (typeof provider.leaveSceneBuilder === 'function') {
          log('Job finished. Returning to project root directory...');
          await provider.leaveSceneBuilder();
        }
      } catch (_) {}
    } catch (e) {
      log(`â Œ job ${jobId.slice(0, 8)} failed: ${e.message}`);
      chrome.runtime.sendMessage({
        type: 'job-error',
        jobId,
        provider: PROVIDER_NAME,
        error: e.message
      });
    }
  }


  async function waitForTextResponse(timeoutMs) {
    const start = Date.now();
    let lastLen = 0;
    let stable = 0;
    while (Date.now() - start < timeoutMs) {
      // Get last assistant message text
      const candidates = [
        ...document.querySelectorAll('[data-message-author-role="assistant"]'),
        ...document.querySelectorAll('model-response, .model-response-text'),
        ...document.querySelectorAll('message-content'),
      ];
      const last = candidates[candidates.length - 1];
      if (last) {
        const txt = (last.innerText || '').trim();
        if (txt.length > 30) {
          if (txt.length === lastLen) stable++;
          else { stable = 0; lastLen = txt.length; }
          if (stable >= 3) return txt;
        }
      }
      await sleep(1500);
    }
    throw new Error('no text response within ' + (timeoutMs/1000) + 's');
  }

  const messageHandler = (msg, sender, sendResponse) => {
    if (msg.type === 'run-job') {
      // Per-tab gating: only handle if the job's provider matches THIS tab.
      // Default behaviour (no provider field) routes to gemini for backward compat.
      const jobProvider = (msg.job && msg.job.provider) || 'gemini';
      if (jobProvider !== PROVIDER_NAME) {
        log(`skipping job ${(msg.job.jobId || '').slice(0,8)}: targets ${jobProvider}, this tab is ${PROVIDER_NAME}`);
        sendResponse({ ok: false, reason: 'wrong-provider', tabProvider: PROVIDER_NAME });
        return true;
      }
      runJob(msg.job);
      sendResponse({ ok: true, provider: PROVIDER_NAME });
    } else if (msg.type === 'who-are-you') {
      // Background can ask any tab which provider it hosts (used for routing).
      sendResponse({ ok: true, provider: PROVIDER_NAME, ready: true });
    }
    return true;

  };

  chrome.runtime.onMessage.addListener(messageHandler);
  window.__db9OrchestratorCleanup = () => {
    try { chrome.runtime.onMessage.removeListener(messageHandler); } catch (_) {}
  };

  log(`ready, waiting for jobs (v0.4.7.6, build=${ORCHESTRATOR_BUILD}, provider=${PROVIDER_NAME})`);
})();

