(() => {
  const PROVIDER_BUILD = 'flow-upload-no-drop-20260518-2205';
  if (window.__DB9_PROVIDER && window.__DB9_PROVIDER.name === 'flow' && window.__DB9_PROVIDER.build === PROVIDER_BUILD) return;

  const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));
  const rand = (min, max) => min + Math.random() * (max - min);
  async function humanPause(minMs, maxMs, reason = '') {
    const duration = Math.round(rand(minMs, maxMs));
    if (reason) log('humanPause: ' + reason + ' ' + duration + 'ms');
    await sleep(duration);
  }
  const visible = (el) => !!el && !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  const log = (text) => {
    console.log('[DB9-Flow]', text);
    try { chrome.runtime.sendMessage({ type: 'log', text: '[flow] ' + text }); } catch (_) {}
  };

  function allOpenRoots(root = document, out = []) {
    out.push(root);
    const nodes = root.querySelectorAll ? root.querySelectorAll('*') : [];
    for (const node of nodes) if (node && node.shadowRoot) allOpenRoots(node.shadowRoot, out);
    return out;
  }

  function qAllDeep(selector, root = document) {
    const seen = new Set();
    const found = [];
    for (const scope of allOpenRoots(root, [])) {
      try {
        for (const el of scope.querySelectorAll(selector)) {
          if (!seen.has(el)) { seen.add(el); found.push(el); }
        }
      } catch (_) {}
    }
    return found;
  }

  function qDeep(selector, root = document) {
    return qAllDeep(selector, root)[0] || null;
  }
  function installNetworkMonitor() {
    try {
      if (window.__db9FlowMonitorInjected) return;
      window.__db9FlowMonitorInjected = true;
      const s = document.createElement('script');
      s.src = chrome.runtime.getURL('content/injected-monitor-flow.js');
      s.onload = () => { try { s.remove(); } catch (_) {} };
      s.onerror = (error) => console.warn('[DB9-Flow] monitor script failed to load', error);
      (document.head || document.documentElement).appendChild(s);
    } catch (error) {
      console.warn('[DB9-Flow] failed to inject page-world monitor', error);
    }
  }

  function resetGenerateAttempt() {
    flowLastGenerateAttempt = null;
    try { window.dispatchEvent(new CustomEvent('db9-flow-generate-reset')); } catch (_) {}
  }

  async function getGenerateAttempt() {
    if (flowLastGenerateAttempt) return flowLastGenerateAttempt;
    return new Promise((resolve) => {
      try {
        const id = 'db9-flow-probe-' + Math.random().toString(36).slice(2);
        const handler = (ev) => {
          if (!ev.detail || ev.detail.id !== id) return;
          window.removeEventListener('db9-flow-generate-probe-result', handler);
          resolve(ev.detail.last || null);
        };
        window.addEventListener('db9-flow-generate-probe-result', handler);
        window.dispatchEvent(new CustomEvent('db9-flow-generate-probe-request', { detail: { id } }));
        setTimeout(() => {
          try { window.removeEventListener('db9-flow-generate-probe-result', handler); } catch (_) {}
          resolve(null);
        }, 250);
      } catch (_) {
        resolve(null);
      }
    });
  }

  function wireGenerateMonitorEvents() {
    if (window.__db9FlowGenerateEventsWired) return;
    window.__db9FlowGenerateEventsWired = true;
    window.addEventListener('db9-flow-generate-result', (ev) => {
      if (ev && ev.detail) {
        flowLastGenerateAttempt = ev.detail;
        log('generate monitor: status=' + ev.detail.status + ' unusual=' + !!ev.detail.unusualActivity + ' message=' + String(ev.detail.errorMessage || '').slice(0, 160));
      }
    });
  }

  function norm(value) {
    return String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
  }

  function textOf(el) {
    return norm([el?.textContent, el?.getAttribute?.('aria-label'), el?.getAttribute?.('placeholder'), el?.getAttribute?.('data-testid')].filter(Boolean).join(' '));
  }

  function isSceneBuilderPage() {
    const cleanText = norm(document.body?.innerText || '');
    return (location.href.includes('/scene/') || location.href.includes('/edit/')) && /them cac doan video|quay lai|add videos|scene/.test(cleanText);
  }

  function realClick(el) {
    if (!el) return false;
    try {
      const rect = el.getBoundingClientRect();
      const opts = { bubbles: true, cancelable: true, composed: true, view: window, clientX: rect.left + rect.width / 2, clientY: rect.top + rect.height / 2, button: 0 };
      el.dispatchEvent(new PointerEvent('pointerdown', { ...opts, pointerType: 'mouse' }));
      el.dispatchEvent(new MouseEvent('mousedown', opts));
      el.dispatchEvent(new PointerEvent('pointerup', { ...opts, pointerType: 'mouse' }));
      el.dispatchEvent(new MouseEvent('mouseup', opts));
      el.dispatchEvent(new MouseEvent('click', opts));
      return true;
    } catch (_) {
      try { el.click(); return true; } catch (_) { return false; }
    }
  }

  function backToProjectButton() {
    return qAllDeep('button,[role="button"]').find(el => {
      if (!visible(el) || el.disabled || el.getAttribute('aria-disabled') === 'true') return false;
      return /quay lai|back/.test(textOf(el));
    }) || null;
  }

  function projectUrlFromScene() {
    const match = location.href.match(/^(https:\/\/labs\.google\/fx\/[^/]+\/tools\/flow\/project\/[^/?#]+)/);
    return match ? match[1] : location.href.replace(/\/(scene|edit)\/[^/?#]+/, '');
  }

  async function leaveSceneBuilder() {
    if (!isSceneBuilderPage()) return;
    const button = backToProjectButton();
    if (button) {
      log('ensureEditorReady: leaving scene builder via back-to-project button');
      realClick(button);
      await sleep(1800);
    }
    if (isSceneBuilderPage()) {
      const projectUrl = projectUrlFromScene();
      if (projectUrl && projectUrl !== location.href) {
        log('ensureEditorReady: navigating back to project editor via history.back()');
        history.back();
        await sleep(1000);
        if (isSceneBuilderPage()) {
           log('ensureEditorReady: navigating back via location.assign');
           location.assign(projectUrl);
           await sleep(2500);
        }
      }
    }
  }

  function newProjectButton() {
    return qAllDeep('button,[role="button"]').find(el => visible(el) && /du an moi|new project|create project|add_2/.test(textOf(el)) && !el.disabled && el.getAttribute('aria-disabled') !== 'true') || null;
  }

  async function ensureEditorReady(timeoutMs = 30000) {
    await leaveSceneBuilder();
    const existing = promptInput();
    if (existing && visible(existing)) return true;
    const create = newProjectButton();
    if (create) {
      log('ensureEditorReady: clicking new project');
      realClick(create);
      await sleep(1500);
    }
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      await leaveSceneBuilder();
      const input = promptInput();
      if (input && visible(input)) return true;
      await sleep(500);
    }
    return false;
  }

  function promptInput() {
    const selectors = [
      'textarea[placeholder*="prompt" i]',
      'textarea[aria-label*="prompt" i]',
      'textarea[placeholder*="describe" i]',
      'textarea[aria-label*="describe" i]',
      'input[placeholder*="prompt" i]',
      'input[aria-label*="prompt" i]',
      '[role="textbox"][contenteditable="true"]',
      '[role="textbox"]',
      '[contenteditable="true"][aria-label*="prompt" i]',
      '[contenteditable="true"][aria-label*="describe" i]',
      '.ProseMirror[contenteditable="true"]',
      '.ql-editor[contenteditable="true"]',
      '[contenteditable="true"]',
      'textarea'
    ];
    const hiddenFallbacks = [];
    for (const selector of selectors) {
      const candidates = qAllDeep(selector).filter(el => !el.disabled && el.getAttribute('aria-disabled') !== 'true');
      const visibleCandidates = candidates.filter(visible);
      const el = visibleCandidates.find(candidate => candidate.isContentEditable || candidate.getAttribute('role') === 'textbox') || visibleCandidates[0];
      if (el) {
        log('promptInput matched ' + selector + ' tag=' + (el.tagName || '').toLowerCase() + ' visible=' + visible(el));
        return el;
      }
      const hidden = candidates.find(candidate => candidate.isContentEditable || candidate.getAttribute('role') === 'textbox') || candidates[0];
      if (hidden) hiddenFallbacks.push({ selector, el: hidden });
    }
    if (hiddenFallbacks.length) {
      const first = hiddenFallbacks[0];
      log('promptInput hidden candidates ignored: ' + first.selector + ' tag=' + (first.el.tagName || '').toLowerCase());
    }
    const sample = qAllDeep('textarea,input,[contenteditable="true"],[role="textbox"]').slice(0, 8).map(el => {
      const label = el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.getAttribute('data-testid') || '';
      return (el.tagName || '').toLowerCase() + ':' + label.slice(0, 60) + ':visible=' + visible(el);
    });
    if (sample.length) log('promptInput candidates: ' + sample.join(' | '));
    return null;
  }

  function readInputValue(el) {
    if (!el) return '';
    if (el.isContentEditable) return String(el.innerText || el.textContent || '').trim();
    return String(el.value || el.getAttribute('value') || '').trim();
  }

  function setInputValue(el, value) {
    const nextValue = String(value || '');
    el.focus();
    if (el.isContentEditable) {
      try {
        const selection = window.getSelection();
        const range = document.createRange();
        range.selectNodeContents(el);
        selection.removeAllRanges();
        selection.addRange(range);
        
        // Use native paste event which is the primary way Lexical ingests text programmatically
        const dt = new DataTransfer();
        dt.setData('text/plain', nextValue);
        const pasteEvent = new ClipboardEvent('paste', {
          clipboardData: dt,
          bubbles: true,
          cancelable: true
        });
        el.dispatchEvent(pasteEvent);
        
        // Fallback to insertText if paste was ignored
        if (el.textContent.length < nextValue.length) {
           document.execCommand('insertText', false, nextValue);
        }
        
        // Ensure cursor is at the end
        range.selectNodeContents(el);
        range.collapse(false);
        selection.removeAllRanges();
        selection.addRange(range);
      } catch (_) {}

      // Fire events
      el.dispatchEvent(new InputEvent('input', { bubbles: true, composed: true, inputType: 'insertText', data: nextValue }));
      el.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
      el.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, composed: true, key: ' ', code: 'Space', keyCode: 32 }));
      el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, composed: true, key: ' ', code: 'Space', keyCode: 32 }));
      
      log('setInputValue contenteditable chars=' + readInputValue(el).length);
      return;
    }
    const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
    if (setter) setter.call(el, nextValue); else el.value = nextValue;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  }

  async function ensurePromptValue(expected, timeoutMs = 4000) {
    const wanted = String(expected || '').trim();
    const start = Date.now();
    let lastSeen = '';
    while (Date.now() - start < timeoutMs) {
      const input = promptInput();
      if (!input) {
        await sleep(150);
        continue;
      }
      const current = readInputValue(input);
      lastSeen = current;
      if (current === wanted || (wanted.length > 32 && current.includes(wanted.slice(0, 32)))) {
        log('ensurePromptValue: verified prompt in editor chars=' + current.length);
        return input;
      }
      setInputValue(input, wanted);
      await sleep(250);
    }
    throw new Error('Flow prompt editor did not keep expected prompt; lastSeenChars=' + lastSeen.length);
  }

  function describeButton(el) {
    const rect = el.getBoundingClientRect();
    return `${textOf(el).slice(0, 80) || '(no text)'}@${Math.round(rect.left)},${Math.round(rect.top)} ${Math.round(rect.width)}x${Math.round(rect.height)}`;
  }

  function manualStartButton() {
    return qAllDeep('button,[role="button"],div[type="button"]').find(el => {
      if (!visible(el) || el.disabled || el.getAttribute('aria-disabled') === 'true') return false;
      const label = textOf(el);
      return /(^| )bat dau($| )|start/.test(label) && !/tao|generate|arrow_forward|upload|tai len/.test(label);
    }) || null;
  }

  function uploadButtonNearComposer() {
    const input = promptInput();
    const inputRect = input?.getBoundingClientRect?.();
    const candidates = qAllDeep('button,[role="button"],div[type="button"],i').filter(el => {
      if (!visible(el)) return false;
      const label = textOf(el);
      if (!/upload|tai len|add_photo|image|hinh anh/.test(label)) return false;
      if (inputRect) {
        const r = el.getBoundingClientRect();
        if (Math.abs((r.top + r.height / 2) - (inputRect.top + inputRect.height / 2)) > 420) return false;
      }
      return true;
    }).map(el => {
      const r = el.getBoundingClientRect();
      let score = /upload|tai len/.test(textOf(el)) ? 20 : 8;
      if (inputRect) score -= Math.min(12, Math.abs((r.top + r.height / 2) - (inputRect.top + inputRect.height / 2)) / 80);
      return { el, score, desc: describeButton(el) };
    }).sort((a, b) => b.score - a.score);
    if (candidates.length) {
      log('uploadButtonNearComposer matched: ' + candidates[0].desc);
      return candidates[0].el;
    }
    return null;
  }

  async function ensureManualUploadPanelReady() {
    const start = manualStartButton();
    if (start) {
      log('uploadImage: clicking manual Start/Bat dau button -> ' + describeButton(start));
      realClick(start);
      await humanPause(900, 1600, 'after opening Start composer');
    }
    const upload = uploadButtonNearComposer();
    if (upload) {
      log('uploadImage: clicking composer upload button');
      realClick(upload);
      await humanPause(500, 1100, 'after composer upload click');
    }
  }

  async function focusComposerAfterUpload() {
    const input = promptInput();
    if (input) {
      realClick(input);
      try { input.focus(); } catch (_) {}
      log('uploadImage: focused composer after upload');
      await humanPause(700, 1400, 'after composer focus post-upload');
    }
  }
  function sendButton(input) {
    const buttons = qAllDeep('button,[role="button"]').filter(visible);
    const inputRect = input?.getBoundingClientRect?.();
    const blocked = /tao canh|create scene|scene|canh|quay|back|du an|project|agree|thanks|cookie|them cac doan video|add videos/;
    const positive = /tao video|create video|generate|submit|send|run|gui|tao|arrow_forward|play_arrow|auto_awesome/;
    const scored = buttons
      .filter(el => !el.disabled && el.getAttribute('aria-disabled') !== 'true')
      .map(el => {
        const label = textOf(el);
        if (!positive.test(label) || blocked.test(label)) return { el, score: -1, label };
        let score = /tao video|create video|generate|submit|send|run|gui/.test(label) ? 20 : 10;

        if (/arrow_forward/.test(label)) score += 8;
        if (/play_arrow|auto_awesome/.test(label)) score += 4;
        if (/add_2/.test(label)) score -= 20;
        if (inputRect) {
          const rect = el.getBoundingClientRect();
          const inputMidY = inputRect.top + inputRect.height / 2;
          const buttonMidY = rect.top + rect.height / 2;
          const dy = Math.abs(buttonMidY - inputMidY);
          if (dy < 160) score += 8;
          if (rect.top >= inputRect.top - 220 && rect.top <= inputRect.bottom + 220) score += 4;
          score -= Math.min(8, dy / 220);
        }
        return { el, score, label };
      })
      .filter(item => item.score > 0)
      .sort((a, b) => b.score - a.score);
    if (scored.length) {
      log('sendButton top candidates: ' + scored.slice(0, 5).map(item => Math.round(item.score) + ':' + describeButton(item.el)).join(' | '));
      log('sendButton matched: ' + describeButton(scored[0].el));
      return scored[0].el;
    }
    log('sendButton candidates rejected: ' + buttons.slice(0, 12).map(describeButton).join(' | '));
    return null;
  }

  function flowButtons() {
    return qAllDeep('button,[role="button"],[role="tab"]').filter(el => visible(el) && !el.disabled && el.getAttribute('aria-disabled') !== 'true');
  }

  function findControl(regex, options = {}) {
    const blocked = options.blocked || /trinh tao canh|tao canh|create scene|scene builder/;
    return flowButtons().find(el => {
      const label = textOf(el);
      if (!label || blocked.test(label)) return false;
      return regex.test(label);
    }) || null;
  }

  async function clickControl(regex, label, options = {}) {
    const control = findControl(regex, options);
    if (!control) {
      if (options.required) throw new Error('Flow control not found: ' + label);
      log('ensureVideoMode: optional control not found: ' + label);
      return false;
    }
    realClick(control);
    log('ensureVideoMode: clicked ' + label + ' -> ' + describeButton(control));
    await sleep(options.waitMs || 450);
    return true;
  }

  function videoModeSummaryButton() {
    return findControl(/video.*(crop_16_9|16:9|x2)|crop_16_9.*x2|videocrop_16_9x2|nano banana.*crop_16_9/, {
      blocked: /trinh tao canh|tao canh|create scene|scene builder/
    });
  }

  function currentModeText() {
    const buttons = flowButtons()
      .map(el => textOf(el))
      .filter(label => /video|veo|banana|crop_16_9|16:9|x2/.test(label));
    return buttons.join(' | ');
  }

  function scoreVeoModelOption(el) {
    const label = textOf(el);
    let score = -1;
    if (/veo/.test(label)) score = 30;
    if (/veo.*3\.1|3\.1.*veo/.test(label)) score += 15;
    if (/lite/.test(label)) score += 10;
    if (/fast/.test(label)) score += 6;
    if (/quality/.test(label)) score += 4;
    if (/lower priority/.test(label)) score -= 2;
    if (/banana|image|hinh anh|nano/.test(label)) score -= 80;
    if (/tao|generate|submit|send|run|gui|project|du an|scene|canh|back|quay|settings|search/.test(label)) score -= 50;
    return { el, label, score };
  }

  function visibleModelMenuRoots() {
    const selectors = [
      '[role="menu"]',
      '[role="listbox"]',
      '[role="dialog"]',
      '[data-radix-popper-content-wrapper]',
      '.DropdownMenuContent',
      '.PopoverContent',
      '[cmdk-list]'
    ].join(',');
    return qAllDeep(selectors)
      .filter(visible)
      .filter(el => {
        const label = textOf(el);
        return /veo|banana|nano|model|video|image|hinh anh/.test(label);
      })
      .sort((a, b) => b.getBoundingClientRect().width * b.getBoundingClientRect().height - a.getBoundingClientRect().width * a.getBoundingClientRect().height);
  }

  function scanVeoCandidates(root, scopeLabel) {
    const optionSelector = 'button,[role="button"],[role="menuitem"],[role="option"],[cmdk-item],div,span,a';
    const options = (root === document ? qAllDeep(optionSelector) : Array.from(root.querySelectorAll(optionSelector)))
      .filter(visible)
      .map(scoreVeoModelOption)
      .filter(item => item.score > 0)
      .sort((a, b) => b.score - a.score);
    if (options.length) {
      log('ensureVideoMode: veo candidates ' + scopeLabel + ' ' + options.slice(0, 8).map(item => Math.round(item.score) + ':' + describeButton(item.el)).join(' | '));
      return options[0].el;
    }
    return null;
  }

  function veoModelCandidate() {
    const menus = visibleModelMenuRoots();
    for (const menu of menus) {
      const candidate = scanVeoCandidates(menu, 'scoped');
      if (candidate) return candidate;
    }
    if (!menus.length) log('ensureVideoMode: no open model menu found; trying global visible Veo scan');
    else {
      const sample = menus.flatMap(menu => Array.from(menu.querySelectorAll('button,[role="button"],[role="menuitem"],[role="option"],[cmdk-item],div,span,a')).filter(visible).map(el => textOf(el)).filter(Boolean).slice(0, 12)).slice(0, 30);
      log('ensureVideoMode: no Veo candidate in scoped menus; menu sample=' + sample.join(' | ').slice(0, 500));
    }
    const globalCandidate = scanVeoCandidates(document, 'global');
    if (globalCandidate) return globalCandidate;
    log('ensureVideoMode: no visible Veo model candidate in scoped or global scan');
    return null;
  }

  async function openModelMenu() {
    const modelButtons = qAllDeep('button[aria-haspopup], [role="button"][aria-haspopup], [role="combobox"], button, [role="button"]').filter(visible).map(el => {
      const label = textOf(el);
      let score = -1;
      if (/video/.test(label) && /(crop_16_9|16:9)/.test(label)) score = 40;
      if (/x2/.test(label)) score += 8;
      if (/banana|nano/.test(label)) score += 12;
      if (/veo/.test(label)) score += 10;
      if (/model|mode|che do/.test(label)) score += 6;
      if (/tao|generate|submit|send|run|gui|project|du an|scene|canh|back|quay|settings|search|upload|tai len/.test(label)) score -= 50;
      return { el, label, score };
    }).filter(item => item.score > 0).sort((a, b) => b.score - a.score);
    if (!modelButtons.length) {
      log('ensureVideoMode: no exact model menu opener found');
      return false;
    }
    const target = modelButtons[0].el;
    log('ensureVideoMode: opening model menu -> ' + describeButton(target));
    realClick(target);
    await sleep(1200);
    return true;
  }

  async function ensureVeoModel() {
    let modeText = currentModeText();
    if (/veo/.test(modeText) && !/nano banana/.test(modeText.replace(/veo[^|]*/g, ''))) return true;

    await openModelMenu();
    let veo = veoModelCandidate();
    if (!veo) {
      await clickControl(/play_circle.*video|(^| )video($| )|video video/, 'Video tab', { required: false, waitMs: 700 });
      await openModelMenu();
      veo = veoModelCandidate();
    }
    if (!veo) {
      log('ensureVideoMode: no visible Veo model candidate after opening model menu');
      return false;
    }
    realClick(veo);
    log('ensureVideoMode: clicked Veo model -> ' + describeButton(veo));
    await sleep(1200);
    return /veo/.test(currentModeText());
  }
  async function ensureVideoMode() {
    const summary = videoModeSummaryButton();
    if (summary) {
      realClick(summary);
      log('ensureVideoMode: opened current mode row -> ' + describeButton(summary));
      await sleep(700);
    } else {
      log('ensureVideoMode: compact video mode row not found, trying visible controls');
    }

    await clickControl(/play_circle.*video|(^| )video($| )|video video/, 'Video tab', { required: false });
    await ensureVeoModel();
    await clickControl(/crop_16_9|16:9/, '16:9 aspect', { required: false });
    await clickControl(/(^| )x2($| )|x2x2/, 'x2 length/quality', { required: false });
    await clickControl(/(^| )4s($| )|4s4s/, '4s duration', { required: false });

    const after = videoModeSummaryButton();
    if (!after) throw new Error('Flow video mode row not visible after selecting controls');
    const summaryText = textOf(after);
    const modeText = currentModeText();
    log('ensureVideoMode: summary=' + summaryText.slice(0, 100));
    log('ensureVideoMode: mode controls=' + modeText.slice(0, 240));
    if (/nano banana/.test(summaryText + ' ' + modeText) && !/veo/.test(summaryText + ' ' + modeText)) {
      throw new Error('Flow still selected image model Nano Banana Pro instead of video model: ' + modeText.slice(0, 180));
    }
    if (!/video|veo/.test(summaryText + ' ' + modeText)) throw new Error('Flow mode summary is not Video: ' + summaryText);
    return true;
  }

  function base64ToFile(base64, mime) {
    if (!base64) throw new Error('missing imageBase64 payload');
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
    const type = mime || 'image/png';
    return new File([new Blob([bytes], { type })], `db9-flow-${Date.now()}.png`, { type });
  }

  function setNativeFiles(input, files) {
    const proto = HTMLInputElement.prototype;
    const desc = Object.getOwnPropertyDescriptor(proto, 'files');
    if (desc?.set) desc.set.call(input, files);
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  }

  let lastUploadPreviewSignature = '';

  async function uploadImage(base64, mime) {
    const file = base64ToFile(base64, mime);
    log(`uploadImage: file ${Math.round(file.size / 1024)}KB ${file.type}`);

    await ensureManualUploadPanelReady();

    lastUploadPreviewSignature = composerPreviewSignature();

    clearComposerAttachments();
    await sleep(800);

    const afterClearSignature = composerPreviewSignature();
    log(`uploadImage: before signature changed after clear=${String(afterClearSignature !== lastUploadPreviewSignature)}`);

    const inputs = qAllDeep('input[type="file"]').filter(input => {
      const accept = (input.getAttribute('accept') || '').toLowerCase();
      return !accept || /image|png|jpg|jpeg|webp|\*\/\*/.test(accept);
    });

    if (!inputs.length) throw new Error('Flow file input not found');

    const rankedInputs = inputs
      .map((input, index) => {
        const rect = input.getBoundingClientRect();
        const style = window.getComputedStyle(input);
        const accept = (input.getAttribute('accept') || '').toLowerCase();
        let score = 0;

        if (visible(input)) score += 50;
        if (rect && rect.width > 0 && rect.height > 0) score += 20;
        if (style.display !== 'none' && style.visibility !== 'hidden') score += 10;
        if (/image|png|jpg|jpeg|webp|\*\/\*/.test(accept)) score += 10;

        return {
          input,
          score,
          desc: '#' + index + ' ' + (accept || '(no-accept)') + ' ' + Math.round(rect.width) + 'x' + Math.round(rect.height) + ' visible=' + visible(input)
        };
      })
      .sort((a, b) => b.score - a.score);

    log('uploadImage: file input candidates ' + rankedInputs.slice(0, 5).map(x => x.score + ':' + x.desc).join(' | '));

    const targetInput = rankedInputs[0].input;

    const dt = new DataTransfer();
    dt.items.add(file);

    log('uploadImage: skipping synthetic drop event; using native file input only');

    if (targetInput) {
      setNativeFiles(targetInput, dt.files);
      log('uploadImage: assigned native file input');
    }

    log('uploadImage: waiting for image to auto-attach to prompt...');
    let attached = false;
    const startWait = Date.now();
    while (Date.now() - startWait < 15000) {
      await sleep(1000);
      const currentSig = composerPreviewSignature();
      if (currentSig && currentSig !== afterClearSignature && currentSig !== lastUploadPreviewSignature) {
        log('uploadImage: image attached near composer sig=' + currentSig);
        attached = true;
        break;
      }
    }

    if (!attached) {
      log('uploadImage: first wait did not show composer attachment; focusing composer and waiting again');
      await focusComposerAfterUpload();
      const refocusStart = Date.now();
      while (Date.now() - refocusStart < 20000) {
        await sleep(1000);
        const currentSig = composerPreviewSignature();
        if (currentSig && currentSig !== afterClearSignature && currentSig !== lastUploadPreviewSignature) {
          log('uploadImage: image attached near composer after refocus sig=' + currentSig);
          attached = true;
          break;
        }
      }
    }

    if (!attached) {
      throw new Error('Flow upload succeeded but image did not appear in Start/composer box; not clicking gallery thumbnails');
    }

    await humanPause(8000, 15000, 'after upload before submit');
  }

  function assetThumbCandidates() {
    const prompt = promptInput();
    const promptRect = prompt?.getBoundingClientRect?.();

    return qAllDeep('img').filter(el => {
      if (!visible(el)) return false;
      const src = mediaSrc(el);
      if (!src) return false;
      const rect = el.getBoundingClientRect();
      // Ignore small icons
      if (!rect || rect.width < 24 || rect.height < 24) return false;

      // Ignore header profile / icons
      if (rect.top < 60) return false;

      if (promptRect && rect.top > promptRect.top + 40) return false;

      return true;
    }).map(el => {
      const rect = el.getBoundingClientRect();
      let score = 0;

      if (rect.left < 180) score += 80;
      if (rect.width <= 120 && rect.height <= 120) score += 30;
      if (rect.width >= 40 && rect.height >= 40) score += 10;

      // Prefer the selected/lower latest thumbnail in the left list.
      score += Math.round(rect.top / 10);

      return {
        el,
        score,
        desc: Math.round(rect.left) + ',' + Math.round(rect.top) + ' ' + Math.round(rect.width) + 'x' + Math.round(rect.height) + ' src=' + mediaSrc(el).slice(0, 80)
      };
    }).sort((a, b) => b.score - a.score);
  }
  async function attachLatestAssetThumbnail() {
    const candidates = assetThumbCandidates();
    log('uploadImage: asset thumbnail candidates ' + candidates.slice(0, 8).map(x => x.score + ':' + x.desc).join(' | '));

    if (!candidates.length) return false;

    const target = candidates[0].el;
    realClick(target);
    await sleep(900);

    log('uploadImage: clicked asset thumbnail ' + candidates[0].desc);
    return true;
  }
  async function waitForUploadPreview(timeoutMs = 30000) {
    const start = Date.now();
    const baselineSignature = lastUploadPreviewSignature;

    while (Date.now() - start < timeoutMs) {
            const previews = composerPreviewItems();
      const currentSignature = composerPreviewSignature();

      if (previews.length && currentSignature && currentSignature !== baselineSignature) {
        log(`composer upload preview updated (${previews.length})`);
        return true;
      }

      await sleep(500);
    }

    throw new Error('Flow upload did not attach new master image to composer');
  }
  function isGenerating() {
    const body = textOf(document.body || document.documentElement || null);
    if (/dang tao|dang xu ly|generating|creating|rendering|processing|please wait|veo/.test(body) && !/ban muon tao gi?|what do you want to create?/.test(body)) return true;
    const btn = sendButton(promptInput() || null);
    const btnLabel = btn ? textOf(btn) : '';
    if (btn && (/stop|cancel|huy|dang tao|generating|creating/.test(btnLabel))) return true;
    return false;
  }

  let flowLastGenerateAttempt = null;

  function summarizeGenerateResponse(bodyText) {
    const text = String(bodyText || '').slice(0, 4000);
    let parsed = null;
    try { parsed = text ? JSON.parse(text) : null; } catch (_) {}
    const error = parsed?.error || null;
    const details = Array.isArray(error?.details) ? error.details : [];
    const unusual = details.find(item => /PUBLIC_ERROR_UNUSUAL_ACTIVITY/i.test(JSON.stringify(item || {})));
    return {
      raw: text,
      code: error?.code || null,
      message: error?.message || '',
      unusual: !!unusual,
      details
    };
  }

  async function generateAwareFetch(input, init) {
    const url = String(input?.url || input || '');
    const isGenerate = /\/v1\/video:batchAsyncGenerateVideoStartImage(?:\?|$)/.test(url);
    const startedAt = Date.now();
    const response = await fetch(input, init);
    if (!isGenerate) return response;

    let preview = '';
    try { preview = await response.clone().text(); } catch (_) {}

    const summary = summarizeGenerateResponse(preview);
    flowLastGenerateAttempt = {
      url,
      status: response.status,
      ok: response.ok,
      startedAt,
      finishedAt: Date.now(),
      preview: summary.raw,
      errorCode: summary.code,
      errorMessage: summary.message,
      unusualActivity: summary.unusual,
      details: summary.details
    };

    log('generateAwareFetch: status=' + response.status + ' unusual=' + summary.unusual + ' message=' + (summary.message || '').slice(0, 160));
    return response;
  }

  function showManualSubmitNotice(timeoutMs) {
    try {
      const old = document.getElementById('db9-flow-manual-submit-notice');
      if (old) old.remove();
      const box = document.createElement('div');
      box.id = 'db9-flow-manual-submit-notice';
      box.textContent = 'DB9 da chuan bi anh va prompt. Hay bam Tao thu cong trong ' + Math.round(timeoutMs / 1000) + ' giay de DB9 tiep tuc lay ket qua.';
      box.style.cssText = 'position:fixed;z-index:2147483647;left:50%;bottom:24px;transform:translateX(-50%);background:#111;color:#fff;font:14px/1.4 Arial,sans-serif;padding:12px 16px;border-radius:8px;box-shadow:0 8px 28px rgba(0,0,0,.35);max-width:560px;text-align:center';
      document.documentElement.appendChild(box);
      setTimeout(() => { try { box.remove(); } catch (_) {} }, timeoutMs + 1000);
    } catch (_) {}
  }

  async function waitForManualSubmit(timeoutMs = 90000) {
    showManualSubmitNotice(timeoutMs);
    log('submitPrompt: waiting for manual Tao click fallback up to ' + Math.round(timeoutMs / 1000) + 's');
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      flowLastGenerateAttempt = flowLastGenerateAttempt || await getGenerateAttempt();
      if (flowLastGenerateAttempt) {
        log('submitPrompt: manual submit fallback observed backend generate request status=' + flowLastGenerateAttempt.status);
        return true;
      }
      if (isGenerating()) {
        log('submitPrompt: manual submit fallback observed generating state');
        return true;
      }
      await sleep(1000);
    }
    return false;
  }
  function dispatchSubmitKeys(input, key, modifiers = {}) {
    input.focus();
    const eventInit = {
      bubbles: true,
      cancelable: true,
      composed: true,
      key,
      code: key === 'Enter' ? 'Enter' : key,
      keyCode: key === 'Enter' ? 13 : 0,
      which: key === 'Enter' ? 13 : 0,
      ctrlKey: !!modifiers.ctrlKey,
      metaKey: !!modifiers.metaKey,
      shiftKey: !!modifiers.shiftKey,
      altKey: !!modifiers.altKey
    };
    input.dispatchEvent(new KeyboardEvent('keydown', eventInit));
    input.dispatchEvent(new KeyboardEvent('keypress', eventInit));
    input.dispatchEvent(new KeyboardEvent('keyup', eventInit));
  }

  async function submitPrompt(prompt) {
    wireGenerateMonitorEvents();
    resetGenerateAttempt();
    const wanted = String(prompt || '').trim();
    if (!wanted) throw new Error('Flow prompt text is empty');
    let input = promptInput();
    if (!input) throw new Error('Flow prompt input not found');
    input = await ensurePromptValue(wanted, 5000);
    await humanPause(3000, 7000, 'after prompt fill before submit');
    const actual = readInputValue(input);
    log('submitPrompt: editor chars=' + actual.length + ' target chars=' + wanted.length);
    const button = sendButton(input);
    if (!button) throw new Error('Flow generate/send button not found');
    const label = textOf(button);
    if (/tao canh|create scene|trinh tao canh|scene/.test(label)) {
      throw new Error('Flow selected scene-builder button instead of generate button');
    }
    realClick(button);
    log('submitPrompt: clicked Flow generate button label=' + label.slice(0, 80));
    await humanPause(1800, 3200, 'after primary submit click');
    if (isGenerating()) {
      log('submitPrompt: generating state detected after click');
      return;
    }

    const fallbackButton = sendButton(input);
    const fallbackLabel = fallbackButton ? textOf(fallbackButton) : '';
    if (
      fallbackButton &&
      fallbackButton !== button &&
      /add_2|arrow_forward|tao|generate|submit|send|run|gui/.test(fallbackLabel)
    ) {
      log('submitPrompt: primary click did not show generating, trying alternate button label=' + fallbackLabel.slice(0, 80));
      realClick(fallbackButton);
      await humanPause(1800, 3200, 'after alternate submit click');
      if (isGenerating()) {
        log('submitPrompt: generating state detected after alternate button');
        return;
      }
    }
    const earlyGenerateAttempt = flowLastGenerateAttempt || await getGenerateAttempt();
    if (earlyGenerateAttempt) {
      flowLastGenerateAttempt = earlyGenerateAttempt;
      log('submitPrompt: skipping keyboard fallbacks because generate request already reached backend status=' + earlyGenerateAttempt.status);
    } else {
      log('submitPrompt: no backend generate request after click; not using Enter fallback to avoid spam');
    }
    if (isGenerating()) {
      log('submitPrompt: generating state detected after click/backend check');
      return;
    }
    flowLastGenerateAttempt = flowLastGenerateAttempt || await getGenerateAttempt();
    if (!flowLastGenerateAttempt) {
      const manualStarted = await waitForManualSubmit(90000);
      if (manualStarted && isGenerating()) return;
      flowLastGenerateAttempt = flowLastGenerateAttempt || await getGenerateAttempt();
    }
    if (flowLastGenerateAttempt) {
      if (flowLastGenerateAttempt.unusualActivity) {
        throw new Error('Flow backend rejected generate request: PUBLIC_ERROR_UNUSUAL_ACTIVITY (HTTP ' + flowLastGenerateAttempt.status + '). Wait, reduce automation-like behavior, or try a different network/profile.');
      }
      if (!flowLastGenerateAttempt.ok) {
        const backendMessage = flowLastGenerateAttempt.errorMessage || flowLastGenerateAttempt.preview || 'unknown backend error';
        throw new Error('Flow backend rejected generate request: HTTP ' + flowLastGenerateAttempt.status + ' ' + backendMessage.slice(0, 220));
      }
    }
    log('submitPrompt: no generating state detected after all submit attempts');
    throw new Error('Flow did not start generation after submit; check if the prompt has an attached image and the create button is enabled');
  }

  function isPromptAttachment(el) {
    const tag = (el.tagName || '').toLowerCase();
    const label = textOf(el.closest?.('[role="button"],button,[aria-label],div') || el);
    return tag === 'img' && /uploaded|tai len|n?i dung nghe nh?n|noi dung nghe nhin|image reference|reference|xem n?i dung nghe nh?n|xem noi dung nghe nhin/.test(label);
  }

  function describeMedia(el) {
    const rect = el.getBoundingClientRect();
    const tag = (el.tagName || '').toLowerCase();
    const src = el.currentSrc || el.src || '';
    return tag + '@' + Math.round(rect.left) + ',' + Math.round(rect.top) + ' ' + Math.round(rect.width) + 'x' + Math.round(rect.height) + ' src=' + src.slice(0, 80);
  }

  function outputs(options = {}) {
    const includePromptAttachments = !!options.includePromptAttachments;
    const requireVideo = !!options.requireVideo;
    return qAllDeep('video,img').filter(el => {
      if (!visible(el)) return false;
      const tag = (el.tagName || '').toLowerCase();
      const src = el.currentSrc || el.src || '';
      const rect = el.getBoundingClientRect();
      const mediaReady = tag === 'video'
        ? (!!src || !!el.querySelector?.('source[src]') || !!el.poster)
        : !!src;
      if (!mediaReady || src.startsWith('data:') || rect.width < 160 || rect.height < 120) return false;
      if (requireVideo && tag !== 'video') return false;
      if (!includePromptAttachments && isPromptAttachment(el)) return false;
      return true;
    });
  }

  function countBaseline() { return outputs({ includePromptAttachments: true }).length; }
  async function toggleCreateImage() {
    log('Flow mode: ensuring video controls');
    await ensureVideoMode();
  }
  async function startNewChat() { log('Flow mode: continuing current project'); }
  async function waitReady(timeoutMs = 30000) {
    return await ensureEditorReady(timeoutMs);
  }
  function mediaSrc(el) {
    return String(el?.currentSrc || el?.src || '');
  }

  function composerPreviewItems() {
    const input = promptInput();
    const inputRect = input?.getBoundingClientRect?.();
    return qAllDeep('img, video').filter(el => {
      const src = mediaSrc(el);
      if (!src) return false;
      const r = el.getBoundingClientRect();
      if (!r || r.width < 32 || r.height < 32) return false;
      if (inputRect) {
        const nearY = r.top >= inputRect.top - 360 && r.top <= inputRect.bottom + 220;
        const nearX = r.left >= inputRect.left - 260 && r.left <= inputRect.right + 260;
        if (!nearY || !nearX) return false;
      }
      const host = el.closest?.('[role="button"],button,[aria-label],div') || el;
      const label = textOf(host);
      if (/gallery|history|recent|project|media library|thu vien|lich su/.test(label) && inputRect) {
        const dy = Math.abs((r.top + r.height / 2) - (inputRect.top + inputRect.height / 2));
        if (dy > 220) return false;
      }
      return true;
    });
  }

  function composerPreviewSignature() {
    return composerPreviewItems()
      .map(el => mediaSrc(el))
      .filter(Boolean)
      .join('|');
  }

  function clearComposerAttachments() {
    const seen = new Set();
    const buttons = [];

    for (const el of [...qAllDeep('button'), ...qAllDeep('[role=button]')]) {
      if (!seen.has(el)) {
        seen.add(el);
        buttons.push(el);
      }
    }

    const candidates = buttons.filter(el => {
      const label = textOf(el);
      if (!label) return false;
      return /remove|delete|clear|close|dismiss|xoa|go bo|huy|cancel/.test(label);
    });

    for (const btn of candidates) {
      try {
        realClick(btn);
      } catch (_) {}
    }
  }
  async function waitForOutput(baseline = 0, timeoutMs = 360000, options = {}) {
    const start = Date.now();
    const requireVideo = options.mode === 'image-to-video' || options.requireVideo === true;
    const initialVideoSrcs = new Set(outputs({ requireVideo: true }).map(mediaSrc).filter(Boolean));
    let lastSignature = '';
    let stableVideo = null;
    let stableVideoSeenAt = 0;

    while (Date.now() - start < timeoutMs) {
      // Flow now automatically navigates to /edit/ when generating, so we cannot throw an error here.
      const errorTextRaw = document.body?.innerText || '';
      const errorText = norm(errorTextRaw);
      const errMatch = errorText.match(/da co loi xay ra|loi he thong|khong the tao|something went wrong|xay ra su co|vuot qua/);
      if (errMatch) {
        log('waitForOutput: flow error detected: ' + errMatch[0]);
        const toasts = Array.from(document.querySelectorAll('[role="alert"], [role="status"]')).map(el => norm(el.innerText || ''));
        log('waitForOutput: alerts/toasts: ' + toasts.join(' | '));
        setTimeout(() => location.reload(), 3500);
        throw new Error('Flow popup error detected: ' + errMatch[0] + '. Reloading tab.');
      }

      const allMedia = outputs();
      const acceptable = outputs({ requireVideo });
      const signature = allMedia.map(describeMedia).join(' | ');

      if (signature && signature !== lastSignature) {
        log('waitForOutput media candidates: ' + signature);
        lastSignature = signature;
      }

      if (requireVideo) {
        const newVideos = acceptable.filter(el => {
          const src = mediaSrc(el);
          return src && !initialVideoSrcs.has(src);
        });

        if (newVideos.length) {
          log('waitForOutput: selected new video ' + describeMedia(newVideos[0]));
          return newVideos[0];
        }

        const bestVisibleVideo = acceptable[0] || null;
        if (bestVisibleVideo) {
          if (stableVideo !== bestVisibleVideo) {
            stableVideo = bestVisibleVideo;
            stableVideoSeenAt = Date.now();
            log('waitForOutput: visible video fallback candidate ' + describeMedia(bestVisibleVideo));
          } else if (Date.now() - stableVideoSeenAt >= 4000) {
            log('waitForOutput: using stable visible video fallback ' + describeMedia(bestVisibleVideo));
            return bestVisibleVideo;
          }
        }
      } else if (acceptable.length > baseline) {
        return acceptable[0] || acceptable[acceptable.length - 1];
      }

      await sleep(1000);
    }

    throw new Error(requireVideo ? 'Flow video output not detected within timeout' : 'Flow output not detected within timeout');
  }
  async function blobToBase64(blob, fallbackMime) {
    const dataUrl = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
    return { base64: dataUrl.split(',')[1] || '', mime: blob.type || fallbackMime || 'application/octet-stream' };
  }
  async function downloadHD(mediaEl) {
    const tag = (mediaEl.tagName || '').toLowerCase();
    const directSource = mediaEl.currentSrc || mediaEl.src || mediaEl.querySelector?.('source[src]')?.src || '';
    const src = directSource || mediaEl.poster || '';
    if (!src) throw new Error('Flow output has no src');
    let response;
    try { response = await generateAwareFetch(src); }
    catch (error) { throw new Error('Flow output fetch failed: ' + error.message); }
    if (!response.ok) throw new Error('Flow output HTTP ' + response.status);
    const fallback = tag === 'video' ? 'video/mp4' : 'image/png';
    return await blobToBase64(await response.blob(), fallback);
  }

  window.__DB9_PROVIDER = {
    name: 'flow',
    build: PROVIDER_BUILD,
    promptInput,
    installNetworkMonitor,
    getUploadMonitorOk: async () => false,
    startNewChat,
    toggleCreateImage,
    uploadImage,
    waitForUploadPreview,
    submitPrompt,
    waitForOutput,
    downloadHD,
    countBaseline,
    waitReady,
    promptInput,
    leaveSceneBuilder
  };

  log('provider module loaded build=' + PROVIDER_BUILD);
})();







