// DB9 Multi-Provider — Shared Orchestrator (v0.4.7.1)
// Loaded AFTER one of the provider-*.js modules (which sets window.__DB9_PROVIDER).
// Drives the same job lifecycle for every provider via the provider interface:
//   { name, installNetworkMonitor, waitReady, startNewChat, toggleCreateImage,
//     uploadImage, waitForUploadPreview, submitPrompt, waitForOutput,
//     downloadHD, countBaseline, promptInput }

(() => {
  if (window.__db9OrchestratorLoaded) return;
  window.__db9OrchestratorLoaded = true;

  const provider = window.__DB9_PROVIDER;
  if (!provider) {
    console.error('[DB9] no provider module found on window.__DB9_PROVIDER. ' +
                  'Did provider-gemini.js or provider-chatgpt.js load first?');
    return;
  }

  const PROVIDER_NAME = provider.name;
  console.log(`[DB9-Orchestrator] v0.4.7.1 loaded for provider="${PROVIDER_NAME}" on`, location.href);

  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const rand = (min, max) => min + Math.random() * (max - min);

  function log(text) {
    console.log(`[DB9-${PROVIDER_NAME}]`, text);
    try { chrome.runtime.sendMessage({ type: 'log', text: `[${PROVIDER_NAME}] ${text}` }); } catch (e) {}
  }

  // Install the per-provider page-world monitor as early as possible.
  try { provider.installNetworkMonitor && provider.installNetworkMonitor(); } catch (e) {
    log('installNetworkMonitor threw: ' + e.message);
  }

  // ===== Main job runner =====
  // v0.4.7.1: presets/negatives are now composed on the UXP side. The extension
  // receives the final prompt string as-is and just drives the browser UI.
  async function runJob(job) {
    const { jobId, mode, imageBase64, mime } = job;
    const prompt = job.prompt || '';
    log(`▶️ runJob ${jobId.slice(0, 8)} mode=${mode} promptChars=${prompt.length}`);

    try {
      if (mode === 'new') {
        await provider.startNewChat();
      }

      // Wait for the page to render the prompt input
      const ready = await provider.waitReady(15000);
      if (!ready) throw new Error('prompt input never appeared');

      const baseline = provider.countBaseline();
      log(`baseline generated images: ${baseline}`);

      // v0.4.7.1: describe-only mode — upload image, ask for text only, no Create Image
      const isDescribeOnly = (mode === 'describe-only');

      if (!isDescribeOnly) await provider.toggleCreateImage();
      await provider.uploadImage(imageBase64, mime);
      await provider.waitForUploadPreview();
      await sleep(rand(300, 600));

      await provider.submitPrompt(prompt);

      if (isDescribeOnly) {
        // Wait for text response (no image generated)
        const text = await waitForTextResponse(40000);
        log('  ✓ description received (' + text.length + ' chars)');
        chrome.runtime.sendMessage({
          type: 'job-result',
          jobId,
          provider: PROVIDER_NAME,
          text,
          chatId: location.pathname.split('/').pop()
        });
        log(`✅ describe job ${jobId.slice(0, 8)} completed`);
        return;
      }

      const imgEl = await provider.waitForOutput(baseline);
      const { base64, mime: outMime } = await provider.downloadHD(imgEl);

      chrome.runtime.sendMessage({
        type: 'job-result',
        jobId,
        provider: PROVIDER_NAME,
        imageBase64: base64,
        mime: outMime,
        sourceUrl: imgEl.src,
        chatId: location.pathname.split('/').pop()
      });
      log(`✅ job ${jobId.slice(0, 8)} completed`);
    } catch (e) {
      log(`❌ job ${jobId.slice(0, 8)} failed: ${e.message}`);
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

  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
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
      sendResponse({ ok: true, provider: PROVIDER_NAME });
    }
    return true;
  });

  log(`ready, waiting for jobs (v0.4.7.1, provider=${PROVIDER_NAME})`);
})();
