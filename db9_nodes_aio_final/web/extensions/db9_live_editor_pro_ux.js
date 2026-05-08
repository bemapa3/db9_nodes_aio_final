import { app } from "../../../scripts/app.js";

const db9LiveEditorRuntime = {
  extractSessionId: null,
  widgetValue: null,
  openEditor: null,
};

app.registerExtension({
  name: "db9.live_editor",
  async setup(app) {
    console.log("[DB9 Live Editor] Pro UX extension loaded");

    const DEFAULT_PARAMS = {
      exposure: 0, contrast: 0, highlights: 0, shadows: 0,
      whites: 0, blacks: 0, vibrance: 0, saturation: 0,
      temperature: 0, tint: 0,
      red_balance: 0, green_balance: 0, blue_balance: 0,
      curve_lift: 0, curve_gamma: 1.0, curve_gain: 1.0,
    };
    const DEFAULT_COMPARE = { mode: "vertical", splitPosition: 0.5, differenceGain: 4.0 };
    const DEFAULT_SETTINGS = {
      filename_prefix: "DB9_Live_Edit",
      autosave: false,
      autosave_delay_ms: 700,
      save_mode: "versioned",
      output_format: "PNG",
      jpeg_quality: 95,
    };

    function cloneDefaultParams() {
      return { ...DEFAULT_PARAMS };
    }

    function cloneDefaultCompare() {
      return { ...DEFAULT_COMPARE };
    }

    function storageKey(prefix) {
      return `db9.live_editor.v4:${prefix || "__last__"}`;
    }

    // ─── State ───────────────────────────────────────────────────────────────
    const state = {
      sessionId: null,
      panel: null,
      originalImg: new Image(),
      editedImg: new Image(),
      params: cloneDefaultParams(),
      compare: cloneDefaultCompare(),
      autosave: { enabled: false, delayMs: 700, timer: null },
      applyTimer: null,
      applyInFlight: false,
      applyPending: false,
      applySeq: 0,
      renderedSeq: 0,
      drag: { active: false },
      sliderRefs: {},   // key → { input, valSpan }
      diffGainRef: null,
      modeBar: null,
      currentNode: null,
      sessionMeta: null,
      isMinimized: false,
      isMaximized: false,
      imageRatio: 0.625,
    };

    // ─── API helper ──────────────────────────────────────────────────────────
    function api(path, opts = {}) {
      return fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
    }

    function sid() { return state.sessionId; }
    function imgUrl(kind) { return `/db9/live_editor/session/${sid()}/image?kind=${kind}&ts=${Date.now()}`; }
    function isLiveEditorNode(node) {
      const title = node?.comfyClass || node?.type || "";
      return title.includes("DB9LiveToneEditor") || title.includes("DB9 Live Tone Editor");
    }

    function findWidget(node, name) {
      return (node?.widgets || []).find(w => w?.name === name) || null;
    }

    function widgetValue(node, name, fallback = null) {
      const w = findWidget(node, name);
      return w && w.value !== undefined ? w.value : fallback;
    }

    function extractSessionId(value) {
      if (typeof value === "string") {
        const match = value.match(/\b[a-f0-9]{12}\b/i);
        return match ? match[0] : null;
      }
      if (Array.isArray(value)) {
        for (const item of value) {
          const sid = extractSessionId(item);
          if (sid) return sid;
        }
        return null;
      }
      if (value && typeof value === "object") {
        for (const item of Object.values(value)) {
          const sid = extractSessionId(item);
          if (sid) return sid;
        }
      }
      return null;
    }

    function readPersistedState(prefix) {
      const keys = [storageKey(prefix), storageKey("__last__")];
      for (const key of keys) {
        try {
          const raw = window.localStorage?.getItem(key);
          if (!raw) continue;
          const parsed = JSON.parse(raw);
          if (parsed && typeof parsed === "object") return parsed;
        } catch (_) {
        }
      }
      return null;
    }

    function currentPrefix() {
      return document.getElementById("db9-prefix")?.value || state.sessionMeta?.filename_prefix || DEFAULT_SETTINGS.filename_prefix;
    }

    function currentPanelSettings() {
      return {
        filename_prefix: document.getElementById("db9-prefix")?.value || DEFAULT_SETTINGS.filename_prefix,
        autosave: !!document.getElementById("db9-autosave")?.checked,
        autosave_delay_ms: parseInt(document.getElementById("db9-autosave-delay")?.value || String(DEFAULT_SETTINGS.autosave_delay_ms)),
        save_mode: document.getElementById("db9-savemode")?.value || DEFAULT_SETTINGS.save_mode,
        output_format: document.getElementById("db9-format")?.value || DEFAULT_SETTINGS.output_format,
        jpeg_quality: parseInt(document.getElementById("db9-jpeg-q")?.value || String(DEFAULT_SETTINGS.jpeg_quality)),
      };
    }

    function persistEditorState(prefixOverride = null) {
      const prefix = prefixOverride || currentPrefix();
      const payload = {
        params: { ...state.params },
        compare: { ...state.compare },
        settings: currentPanelSettings(),
      };
      try {
        window.localStorage?.setItem(storageKey(prefix), JSON.stringify(payload));
        window.localStorage?.setItem(storageKey("__last__"), JSON.stringify(payload));
      } catch (_) {
      }
    }

    function setSliderValue(key, value) {
      const ref = state.sliderRefs[key];
      if (!ref) return;
      ref.input.value = String(value);
      ref.valSpan.textContent = String(value);
    }

    function syncCompareButtons() {
      if (!state.modeBar) return;
      state.modeBar.querySelectorAll("button").forEach((button) => {
        button.style.background = button.dataset.mode === state.compare.mode ? "#3366aa" : "#2a2a2e";
      });
      const canvas = getCanvas();
      if (canvas) {
        canvas.style.cursor = state.compare.mode === "horizontal" ? "row-resize" : state.compare.mode === "vertical" ? "col-resize" : "default";
      }
    }

    function syncPanelControlsFromState() {
      for (const [key, value] of Object.entries(state.params)) {
        setSliderValue(key, value);
      }
      if (state.diffGainRef) {
        state.diffGainRef.input.value = String(state.compare.differenceGain);
        state.diffGainRef.valSpan.textContent = String(state.compare.differenceGain);
      }
      const settings = currentPanelSettings();
      const prefix = document.getElementById("db9-prefix");
      const autosave = document.getElementById("db9-autosave");
      const autosaveDelay = document.getElementById("db9-autosave-delay");
      const saveMode = document.getElementById("db9-savemode");
      const format = document.getElementById("db9-format");
      const jpegQ = document.getElementById("db9-jpeg-q");
      if (prefix) prefix.value = settings.filename_prefix;
      if (autosave) autosave.checked = !!settings.autosave;
      if (autosaveDelay) autosaveDelay.value = String(settings.autosave_delay_ms);
      if (saveMode) saveMode.value = settings.save_mode;
      if (format) format.value = settings.output_format;
      if (jpegQ) jpegQ.value = String(settings.jpeg_quality);
      state.autosave.enabled = !!settings.autosave;
      state.autosave.delayMs = parseInt(settings.autosave_delay_ms || "700");
      syncCompareButtons();
    }

    function applyPersistedState(saved) {
      if (!saved || typeof saved !== "object") return false;
      let changed = false;
      if (saved.params && typeof saved.params === "object") {
        for (const key of Object.keys(DEFAULT_PARAMS)) {
          if (saved.params[key] === undefined) continue;
          if (state.params[key] !== saved.params[key]) changed = true;
          state.params[key] = saved.params[key];
        }
      }
      if (saved.compare && typeof saved.compare === "object") {
        state.compare.mode = saved.compare.mode || state.compare.mode;
        state.compare.splitPosition = Number.isFinite(saved.compare.splitPosition) ? saved.compare.splitPosition : state.compare.splitPosition;
        state.compare.differenceGain = Number.isFinite(saved.compare.differenceGain) ? saved.compare.differenceGain : state.compare.differenceGain;
      }
      if (saved.settings && typeof saved.settings === "object") {
        const merged = { ...DEFAULT_SETTINGS, ...saved.settings };
        const prefix = document.getElementById("db9-prefix");
        const autosave = document.getElementById("db9-autosave");
        const autosaveDelay = document.getElementById("db9-autosave-delay");
        const saveMode = document.getElementById("db9-savemode");
        const format = document.getElementById("db9-format");
        const jpegQ = document.getElementById("db9-jpeg-q");
        if (prefix) prefix.value = merged.filename_prefix;
        if (autosave) autosave.checked = !!merged.autosave;
        if (autosaveDelay) autosaveDelay.value = String(merged.autosave_delay_ms);
        if (saveMode) saveMode.value = merged.save_mode;
        if (format) format.value = merged.output_format;
        if (jpegQ) jpegQ.value = String(merged.jpeg_quality);
        state.autosave.enabled = !!merged.autosave;
        state.autosave.delayMs = parseInt(merged.autosave_delay_ms || "700");
      }
      return changed;
    }

    async function findLatestSessionForNode(node) {
      const filenamePrefix = widgetValue(node, "filename_prefix", "") || "";
      const r = await api("/db9/live_editor/session/find_latest", {
        method: "POST",
        body: JSON.stringify({
          filename_prefix: filenamePrefix,
          max_age_sec: 3600,
        }),
      });
      if (!r.ok) return null;
      const j = await r.json();
      return j.ok ? (j.session_id || null) : null;
    }

    function syncPanelFromSession(meta = {}) {
      state.sessionMeta = meta;
      const prefix = document.getElementById("db9-prefix");
      const saveMode = document.getElementById("db9-savemode");
      const format = document.getElementById("db9-format");
      const jpegQ = document.getElementById("db9-jpeg-q");
      const autosaveCheck = document.getElementById("db9-autosave");
      const autosaveDelay = document.getElementById("db9-autosave-delay");

      if (prefix && meta.filename_prefix != null) prefix.value = String(meta.filename_prefix);
      if (saveMode && meta.save_mode != null) saveMode.value = String(meta.save_mode);
      if (format && meta.output_format != null) format.value = String(meta.output_format);
      if (jpegQ && meta.jpeg_quality != null) jpegQ.value = String(meta.jpeg_quality);
      if (autosaveCheck && meta.autosave != null) autosaveCheck.checked = !!meta.autosave;
      if (autosaveDelay && meta.autosave_delay_ms != null) autosaveDelay.value = String(meta.autosave_delay_ms);

      if (meta.autosave != null) state.autosave.enabled = !!meta.autosave;
      if (meta.autosave_delay_ms != null) state.autosave.delayMs = parseInt(meta.autosave_delay_ms || "700");
    }

    // ─── Status bar ──────────────────────────────────────────────────────────
    function setStatus(txt) {
      const el = document.getElementById("db9-status");
      if (el) el.textContent = txt;
    }

    // ─── Canvas split renderer ───────────────────────────────────────────────
    function getCanvas() { return document.getElementById("db9-canvas"); }

    function refreshCanvasSize() {
      const canvas = getCanvas();
      if (!canvas) return;
      const wrap = canvas.parentElement;
      const ratio = Math.max(state.imageRatio || 0.625, 0.1);
      const wrapWidth = Math.max(Math.round(wrap?.clientWidth || 0) - 2, state.isMaximized ? 960 : 420);
      const maxHeight = state.isMaximized ? Math.max(window.innerHeight - 240, 620) : Math.min(Math.max(window.innerHeight - 320, 360), 640);
      let width = wrapWidth;
      let height = Math.round(width * ratio);
      if (height > maxHeight) {
        height = maxHeight;
        width = Math.max(320, Math.round(height / ratio));
      }
      canvas.width = Math.max(1, width);
      canvas.height = Math.max(1, height);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      drawCanvas();
    }

    function applyPanelLayout() {
      if (!state.panel) return;
      if (state.isMaximized) {
        state.panel.style.left = "18px";
        state.panel.style.right = "18px";
        state.panel.style.top = "18px";
        state.panel.style.width = "auto";
        state.panel.style.height = "calc(100vh - 36px)";
        state.panel.style.maxHeight = "calc(100vh - 36px)";
        state.panel.style.borderRadius = "16px";
      } else {
        state.panel.style.left = "";
        state.panel.style.right = "18px";
        state.panel.style.top = "56px";
        state.panel.style.width = "min(560px, calc(100vw - 36px))";
        state.panel.style.height = "auto";
        state.panel.style.maxHeight = "90vh";
        state.panel.style.borderRadius = "12px";
      }
      const body = document.getElementById("db9-panel-body");
      if (body) body.style.display = state.isMinimized ? "none" : "";
      refreshCanvasSize();
    }

    function drawCanvas() {
      const canvas = getCanvas();
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = "high";
      const W = canvas.width, H = canvas.height;
      const mode = state.compare.mode;
      const sp   = state.compare.splitPosition;

      if (!state.originalImg.complete || !state.editedImg.complete) return;

      ctx.clearRect(0, 0, W, H);

      if (mode === "original") {
        ctx.drawImage(state.originalImg, 0, 0, W, H);
        return;
      }
      if (mode === "edited") {
        ctx.drawImage(state.editedImg, 0, 0, W, H);
        return;
      }
      if (mode === "side_by_side") {
        ctx.drawImage(state.originalImg, 0,   0, W / 2, H);
        ctx.drawImage(state.editedImg,   W/2, 0, W / 2, H);
        // divider
        ctx.strokeStyle = "#fff";
        ctx.lineWidth   = 2;
        ctx.beginPath(); ctx.moveTo(W/2, 0); ctx.lineTo(W/2, H); ctx.stroke();
        return;
      }
      if (mode === "difference") {
        // difference is computed server-side — show compare image
        if (state.compareImg && state.compareImg.complete) {
          ctx.drawImage(state.compareImg, 0, 0, W, H);
        }
        return;
      }

      // vertical (default) — left = original, right = edited
      if (mode === "vertical") {
        const cut = Math.round(W * sp);
        ctx.save();
        ctx.beginPath(); ctx.rect(0, 0, cut, H); ctx.clip();
        ctx.drawImage(state.originalImg, 0, 0, W, H);
        ctx.restore();

        ctx.save();
        ctx.beginPath(); ctx.rect(cut, 0, W - cut, H); ctx.clip();
        ctx.drawImage(state.editedImg, 0, 0, W, H);
        ctx.restore();

        // draggable divider
        ctx.strokeStyle = "#fff";
        ctx.lineWidth   = 2;
        ctx.beginPath(); ctx.moveTo(cut, 0); ctx.lineTo(cut, H); ctx.stroke();

        // handle circle
        const cy = H / 2;
        ctx.fillStyle = "rgba(255,255,255,0.9)";
        ctx.beginPath(); ctx.arc(cut, cy, 14, 0, Math.PI * 2); ctx.fill();
        ctx.strokeStyle = "#333"; ctx.lineWidth = 1.5;
        ctx.stroke();
        ctx.fillStyle = "#333"; ctx.font = "bold 16px sans-serif";
        ctx.textAlign = "center"; ctx.textBaseline = "middle";
        ctx.fillText("⇔", cut, cy);

        // labels
        ctx.fillStyle = "rgba(0,0,0,0.55)";
        ctx.fillRect(6, 6, 68, 22);
        ctx.fillRect(W - 74, 6, 68, 22);
        ctx.fillStyle = "#fff"; ctx.font = "11px sans-serif";
        ctx.textAlign = "left";  ctx.fillText("ORIGINAL", 10, 20);
        ctx.textAlign = "right"; ctx.fillText("EDITED",  W - 8, 20);
        return;
      }

      // horizontal — top = original, bottom = edited
      if (mode === "horizontal") {
        const cut = Math.round(H * sp);
        ctx.save();
        ctx.beginPath(); ctx.rect(0, 0, W, cut); ctx.clip();
        ctx.drawImage(state.originalImg, 0, 0, W, H);
        ctx.restore();

        ctx.save();
        ctx.beginPath(); ctx.rect(0, cut, W, H - cut); ctx.clip();
        ctx.drawImage(state.editedImg, 0, 0, W, H);
        ctx.restore();

        ctx.strokeStyle = "#fff"; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.moveTo(0, cut); ctx.lineTo(W, cut); ctx.stroke();

        const cx = W / 2;
        ctx.fillStyle = "rgba(255,255,255,0.9)";
        ctx.beginPath(); ctx.arc(cx, cut, 14, 0, Math.PI * 2); ctx.fill();
        ctx.strokeStyle = "#333"; ctx.lineWidth = 1.5; ctx.stroke();
        ctx.fillStyle = "#333"; ctx.font = "bold 16px sans-serif";
        ctx.textAlign = "center"; ctx.textBaseline = "middle";
        ctx.fillText("⇕", cx, cut);

        ctx.fillStyle = "rgba(0,0,0,0.55)";
        ctx.fillRect(6, 6, 68, 22); ctx.fillRect(6, H - 28, 68, 22);
        ctx.fillStyle = "#fff"; ctx.font = "11px sans-serif";
        ctx.textAlign = "left";
        ctx.fillText("ORIGINAL", 10, 20);
        ctx.fillText("EDITED",   10, H - 14);
      }
    }

    // ─── Mouse drag on canvas ─────────────────────────────────────────────────
    function canvasMousePos(e, canvas) {
      const r = canvas.getBoundingClientRect();
      return { x: e.clientX - r.left, y: e.clientY - r.top };
    }

    function attachCanvasDrag(canvas) {
      canvas.style.cursor = "col-resize";

      canvas.addEventListener("mousedown", e => {
        state.drag.active = true;
        canvas.style.userSelect = "none";
      });

      window.addEventListener("mousemove", e => {
        if (!state.drag.active) return;
        const pos = canvasMousePos(e, canvas);
        const mode = state.compare.mode;
        if (mode === "vertical") {
          state.compare.splitPosition = Math.max(0.01, Math.min(0.99, pos.x / canvas.width));
        } else if (mode === "horizontal") {
          state.compare.splitPosition = Math.max(0.01, Math.min(0.99, pos.y / canvas.height));
          canvas.style.cursor = "row-resize";
        }
        drawCanvas();
      });

      window.addEventListener("mouseup", () => {
        if (state.drag.active) {
          state.drag.active = false;
          canvas.style.userSelect = "";
          persistEditorState();
        }
      });

      // touch support
      canvas.addEventListener("touchmove", e => {
        e.preventDefault();
        const t = e.touches[0];
        const pos = canvasMousePos(t, canvas);
        const mode = state.compare.mode;
        if (mode === "vertical") {
          state.compare.splitPosition = Math.max(0.01, Math.min(0.99, pos.x / canvas.width));
        } else if (mode === "horizontal") {
          state.compare.splitPosition = Math.max(0.01, Math.min(0.99, pos.y / canvas.height));
        }
        drawCanvas();
      }, { passive: false });
    }

    // ─── Load images into canvas ──────────────────────────────────────────────
    function reloadImages(cb) {
      let loaded = 0;
      function onLoad() { loaded++; if (loaded >= 2 && cb) cb(); drawCanvas(); }

      state.originalImg = new Image();
      state.editedImg   = new Image();
      state.originalImg.onload = onLoad;
      state.editedImg.onload   = onLoad;
      state.originalImg.src = imgUrl("reference");
      state.editedImg.src   = imgUrl("current");
    }

    async function reloadDifferenceAndDraw() {
      if (state.compare.mode !== "difference") { drawCanvas(); return; }
      const r = await api(`/db9/live_editor/session/${sid()}/compare`, {
        method: "POST",
        body: JSON.stringify({
          mode: "difference",
          split_position: 0.5,
          difference_gain: state.compare.differenceGain,
        }),
      });
      const j = await r.json();
      if (j.ok) {
        state.compareImg = new Image();
        state.compareImg.onload = drawCanvas;
        state.compareImg.src = j.compare_url;
      }
    }

    // ─── Apply params (debounced 80ms) ────────────────────────────────────────
    async function runApply() {
      if (!sid()) return;
      if (state.applyInFlight) {
        state.applyPending = true;
        return;
      }
      state.applyInFlight = true;
      const requestSeq = ++state.applySeq;
      try {
        const r = await api(`/db9/live_editor/session/${sid()}/apply`, {
          method: "POST",
          body: JSON.stringify({ params: state.params, ...currentPanelSettings() }),
        });
        const j = await r.json();
        if (j.ok && requestSeq >= state.renderedSeq) {
          state.renderedSeq = requestSeq;
          state.editedImg = new Image();
          state.editedImg.onload = () => { reloadDifferenceAndDraw(); debounceAutosave(); };
          state.editedImg.src = j.preview_url;
          setStatus("Preview updated");
        }
      } finally {
        state.applyInFlight = false;
        if (state.applyPending) {
          state.applyPending = false;
          runApply();
        }
      }
    }

    function scheduleApply() {
      if (state.applyTimer) clearTimeout(state.applyTimer);
      setStatus("Updating preview...");
      state.applyTimer = setTimeout(() => {
        state.applyTimer = null;
        runApply();
      }, 16);
    }

    // ─── Autosave ─────────────────────────────────────────────────────────────
    function debounceAutosave() {
      if (!state.autosave.enabled || !sid()) return;
      clearTimeout(state.autosave.timer);
      state.autosave.timer = setTimeout(async () => {
        const r = await api(`/db9/live_editor/session/${sid()}/autosave`, {
          method: "POST", body: JSON.stringify(currentPanelSettings()),
        });
        const j = await r.json();
        setStatus(`Autosaved → ${j.saved_path || "ok"}`);
      }, state.autosave.delayMs);
    }

    // ─── Save / Reset / Close ─────────────────────────────────────────────────
    async function saveNow() {
      if (!sid()) return;
      const prefix  = document.getElementById("db9-prefix")?.value  || "DB9_Live_Edit";
      const saveMode= document.getElementById("db9-savemode")?.value || "versioned";
      const fmt     = document.getElementById("db9-format")?.value   || "PNG";
      const q       = parseInt(document.getElementById("db9-jpeg-q")?.value || "95");
      persistEditorState(prefix);
      const r = await api(`/db9/live_editor/session/${sid()}/save`, {
        method: "POST",
        body: JSON.stringify({ filename_prefix: prefix, save_mode: saveMode, output_format: fmt, jpeg_quality: q }),
      });
      const j = await r.json();
      setStatus(`Saved → ${j.saved_path || "ok"}`);
    }

    async function resetEditor() {
      if (!sid()) return;
      const r = await api(`/db9/live_editor/session/${sid()}/reset`, { method: "POST", body: JSON.stringify({}) });
      const j = await r.json();
      if (!j.ok) return;
      const defaults = cloneDefaultParams();
      Object.assign(state.params, defaults);
      // update all slider DOMs
      for (const [key, ref] of Object.entries(state.sliderRefs)) {
        ref.input.value    = String(defaults[key]);
        ref.valSpan.textContent = String(defaults[key]);
      }
      persistEditorState();
      state.editedImg = new Image();
      state.editedImg.onload = drawCanvas;
      state.editedImg.src = j.preview_url;
      setStatus("Reset to defaults");
    }

    async function closeEditor() {
      if (sid()) {
        await api(`/db9/live_editor/session/${sid()}/close`, { method: "POST", body: JSON.stringify({}) });
      }
      clearTimeout(state.applyTimer);
      state.applyTimer = null;
      state.applyPending = false;
      state.applyInFlight = false;
      if (state.panel) { state.panel.remove(); state.panel = null; }
      state.sessionId = null;
    }

    // ─── UI helpers ──────────────────────────────────────────────────────────
    const css = (el, s) => { el.style.cssText = s; return el; };
    function el(tag, s) { return css(document.createElement(tag), s || ""); }

    function btn(label, onClick, extra) {
      const b = css(document.createElement("button"),
        `padding:5px 12px;border-radius:6px;cursor:pointer;font-size:12px;background:#333;
         color:#eee;border:1px solid #555;${extra||""}`);
      b.textContent = label;
      b.onclick = onClick;
      return b;
    }

    function row(...children) {
      const d = css(document.createElement("div"),
        "display:flex;gap:6px;align-items:center;margin:4px 0;");
      children.forEach(c => d.appendChild(c));
      return d;
    }

    function hr() {
      const h = document.createElement("hr");
      h.style.cssText = "border:none;border-top:1px solid #3a3a3a;margin:10px 0;";
      return h;
    }

    function sectionLabel(txt) {
      const d = css(document.createElement("div"),
        "font-size:11px;font-weight:600;letter-spacing:.06em;color:#aaa;margin:10px 0 4px;text-transform:uppercase;");
      d.textContent = txt;
      return d;
    }

    function makeSlider(label, key, min, max, step, defaultVal) {
      const wrap = css(document.createElement("div"),
        "display:flex;flex-direction:column;gap:1px;margin:3px 0;");
      const top = css(document.createElement("div"),
        "display:flex;justify-content:space-between;align-items:center;");
      const lab = css(document.createElement("span"), "font-size:12px;color:#ccc;");
      lab.textContent = label;
      const valSpan = css(document.createElement("span"),
        "font-size:11px;color:#88d;min-width:44px;text-align:right;font-variant-numeric:tabular-nums;");
      valSpan.textContent = String(defaultVal);
      top.append(lab, valSpan);

      const input = css(document.createElement("input"),
        "width:100%;accent-color:#6699cc;cursor:pointer;");
      input.type = "range";
      input.min  = String(min);
      input.max  = String(max);
      input.step = String(step);
      input.value= String(defaultVal);
      input.oninput = () => {
        const v = parseFloat(input.value);
        valSpan.textContent = input.value;
        state.params[key] = v;
        persistEditorState();
        scheduleApply();
      };

      state.sliderRefs[key] = { input, valSpan };
      wrap.append(top, input);
      return wrap;
    }

    // ─── Build Panel ──────────────────────────────────────────────────────────
    function buildPanel() {
      const panel = css(document.createElement("div"),
        `position:fixed;right:18px;top:56px;width:min(560px, calc(100vw - 36px));max-height:90vh;
         background:#18181c;color:#e0e0e0;border:1px solid #3a3a3a;border-radius:12px;
         padding:14px;z-index:999999;box-shadow:0 12px 40px rgba(0,0,0,.55);
         font-family:system-ui,sans-serif;display:flex;flex-direction:column;`);
      panel.id = "db9-live-panel";

      // ── header ──
      const header = css(document.createElement("div"),
        "display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;");
      const title = css(document.createElement("h3"), "margin:0;font-size:15px;");
      title.textContent = "DB9 Live Tone Editor";
      const statusEl = css(document.createElement("span"), "font-size:11px;color:#aaa;");
      statusEl.id = "db9-status";
      statusEl.textContent = "Idle";
      header.append(title, statusEl);

      const maxBtn = btn("□ Maximize", () => {
        state.isMaximized = !state.isMaximized;
        maxBtn.textContent = state.isMaximized ? "❐ Restore" : "□ Maximize";
        applyPanelLayout();
      });
      const minBtn = btn("â€” Minimize", () => {
        const body = document.getElementById("db9-panel-body");
        state.isMinimized = !state.isMinimized;
        minBtn.textContent = state.isMinimized ? "+ Expand" : "â€” Minimize";
        if (body) body.style.display = state.isMinimized ? "none" : "";
        if (!state.isMinimized) refreshCanvasSize();
      });

      // ── action buttons ──
      const actions = row(
        maxBtn,
        btn("💾 Save Now", saveNow, "background:#2a4a2a;border-color:#3a7a3a;"),
        minBtn,
        btn("↩ Reset", resetEditor),
        btn("✕ Close", closeEditor, "background:#4a2020;border-color:#7a3a3a;margin-left:auto;")
      );

      // ── canvas (drag-split view) ──
      const canvasWrap = css(document.createElement("div"),
        "position:relative;margin:10px 0;border-radius:8px;overflow:auto;border:1px solid #333;min-height:320px;background:#101014;display:flex;align-items:center;justify-content:center;");
      const canvas = css(document.createElement("canvas"), "display:block;width:100%;height:auto;");
      canvas.id     = "db9-canvas";
      canvas.width  = 800;
      canvas.height = 500;
      canvasWrap.appendChild(canvas);

      // ── compare mode bar ──
      const modes = ["vertical","horizontal","side_by_side","difference","original","edited"];
      const modeBar = css(document.createElement("div"),
        "display:flex;gap:4px;flex-wrap:wrap;margin:6px 0;");
      state.modeBar = modeBar;
      modes.forEach(m => {
        const b = css(document.createElement("button"),
          `padding:3px 9px;border-radius:5px;cursor:pointer;font-size:11px;
           background:${m===state.compare.mode?"#3366aa":"#2a2a2e"};
           color:#eee;border:1px solid #444;`);
        b.textContent = { vertical:"↕ Split V", horizontal:"↔ Split H", side_by_side:"Side-by-Side",
                          difference:"Diff", original:"Original", edited:"Edited" }[m];
        b.dataset.mode = m;
        b.onclick = async () => {
          state.compare.mode = m;
          syncCompareButtons();
          persistEditorState();
          await reloadDifferenceAndDraw();
        };
        modeBar.appendChild(b);
      });

      // difference gain
      const diffGainWrap = makeSlider("Difference Gain", "__diffgain__", 1, 16, 0.1, 4.0);
      // override oninput for this special slider
      const diffGainInput = diffGainWrap.querySelector("input");
      diffGainInput.oninput = async () => {
        state.compare.differenceGain = parseFloat(diffGainInput.value);
        diffGainWrap.querySelector("span:last-child").textContent = diffGainInput.value;
        persistEditorState();
        if (state.compare.mode === "difference") await reloadDifferenceAndDraw();
      };
      state.diffGainRef = {
        input: diffGainInput,
        valSpan: diffGainWrap.querySelector("span:last-child"),
      };

      // ── autosave row ──
      const autosaveRow = row();
      const asLabel = css(document.createElement("label"),
        "font-size:12px;color:#ccc;flex:1;display:flex;gap:6px;align-items:center;cursor:pointer;");
      const asCheck = document.createElement("input");
      asCheck.id = "db9-autosave";
      asCheck.type = "checkbox";
      asCheck.onchange = () => {
        state.autosave.enabled = asCheck.checked;
        persistEditorState();
      };
      asLabel.append(asCheck, document.createTextNode("Autosave"));
      const asDelay = css(document.createElement("input"),
        "width:80px;padding:3px 6px;background:#252528;border:1px solid #444;border-radius:4px;color:#eee;font-size:12px;");
      asDelay.id = "db9-autosave-delay";
      asDelay.type = "number"; asDelay.value = "700"; asDelay.min = "100"; asDelay.max = "5000";
      asDelay.onchange = () => {
        state.autosave.delayMs = parseInt(asDelay.value || "700");
        persistEditorState();
      };
      const asUnit = css(document.createElement("span"), "font-size:11px;color:#888;");
      asUnit.textContent = "ms";
      autosaveRow.append(asLabel, asDelay, asUnit);

      // ── save options ──
      function inlineSelect(id, opts, def) {
        const s = css(document.createElement("select"),
          "background:#252528;border:1px solid #444;border-radius:4px;color:#eee;font-size:12px;padding:3px 4px;");
        s.id = id;
        opts.forEach(v => { const o = document.createElement("option"); o.value=v; o.textContent=v; if(v===def)o.selected=true; s.appendChild(o); });
        s.onchange = () => persistEditorState();
        return s;
      }
      function inlineText(id, def, w) {
        const i = css(document.createElement("input"),
          `width:${w||"120px"};padding:3px 6px;background:#252528;border:1px solid #444;border-radius:4px;color:#eee;font-size:12px;`);
        i.id = id; i.value = def;
        i.oninput = () => persistEditorState(id === "db9-prefix" ? i.value : null);
        return i;
      }
      const saveRow1 = row(
        css(Object.assign(document.createElement("span"), { textContent:"File:" }),
          "font-size:12px;color:#ccc;"),
        inlineText("db9-prefix", "DB9_Live_Edit", "140px"),
        inlineSelect("db9-savemode", ["versioned","overwrite"], "versioned"),
      );
      const saveRow2 = row(
        css(Object.assign(document.createElement("span"), { textContent:"Format:" }),
          "font-size:12px;color:#ccc;"),
        inlineSelect("db9-format", ["PNG","JPEG","WEBP"], "PNG"),
        css(Object.assign(document.createElement("span"), { textContent:"Q:" }),
          "font-size:12px;color:#888;"),
        inlineText("db9-jpeg-q", "95", "50px"),
      );

      // ── tone sliders ──
      const sliders = document.createElement("div");
      sliders.append(
        sectionLabel("Exposure & Tone"),
        makeSlider("Exposure",   "exposure",   -2,  2,    0.01, 0),
        makeSlider("Contrast",   "contrast",   -1,  1,    0.01, 0),
        makeSlider("Highlights", "highlights", -1,  1,    0.01, 0),
        makeSlider("Shadows",    "shadows",    -1,  1,    0.01, 0),
        makeSlider("Whites",     "whites",     -1,  1,    0.01, 0),
        makeSlider("Blacks",     "blacks",     -1,  1,    0.01, 0),
        hr(),
        sectionLabel("Color"),
        makeSlider("Vibrance",    "vibrance",    -1, 1, 0.01, 0),
        makeSlider("Saturation",  "saturation",  -1, 1, 0.01, 0),
        makeSlider("Temperature", "temperature", -1, 1, 0.01, 0),
        makeSlider("Tint",        "tint",        -1, 1, 0.01, 0),
        hr(),
        sectionLabel("RGB Balance"),
        makeSlider("Red",   "red_balance",   -1, 1, 0.01, 0),
        makeSlider("Green", "green_balance", -1, 1, 0.01, 0),
        makeSlider("Blue",  "blue_balance",  -1, 1, 0.01, 0),
        hr(),
        sectionLabel("Curves"),
        makeSlider("Lift",  "curve_lift",  -1,  1,   0.01, 0),
        makeSlider("Gamma", "curve_gamma",  0.2,3.0, 0.01, 1.0),
        makeSlider("Gain",  "curve_gain",   0.2,3.0, 0.01, 1.0),
      );

      // ── assemble panel ──
      const body = css(document.createElement("div"), "flex:1 1 auto;min-height:0;overflow-y:auto;");
      body.id = "db9-panel-body";
      body.append(
        canvasWrap,
        modeBar,
        diffGainWrap,
        hr(),
        autosaveRow, saveRow1, saveRow2,
        hr(),
        sliders,
      );

      panel.append(header, actions, hr(), body);

      document.body.appendChild(panel);
      state.panel = panel;
      attachCanvasDrag(canvas);
      applyPanelLayout();
    }

    // ─── Open editor with session ─────────────────────────────────────────────
    async function openEditor(sessionId) {
      state.sessionId = sessionId;
      if (!state.panel) buildPanel();
      else state.panel.style.display = "";

      const r = await api("/db9/live_editor/session/init", {
        method: "POST",
        body: JSON.stringify({ session_id: sessionId }),
      });
      const j = await r.json();
      if (!j.ok) { setStatus("Session init failed"); return; }
      syncPanelFromSession(j);
      const saved = readPersistedState(j.filename_prefix);
      const shouldReapply = applyPersistedState(saved);
      for (const [key, value] of Object.entries(state.params)) {
        setSliderValue(key, value);
      }
      if (state.diffGainRef) {
        state.diffGainRef.input.value = String(state.compare.differenceGain);
        state.diffGainRef.valSpan.textContent = String(state.compare.differenceGain);
      }
      syncCompareButtons();
      persistEditorState(j.filename_prefix);

      // set canvas aspect ratio from image dimensions
      const canvas = getCanvas();
      if (canvas && j.width && j.height) {
        state.imageRatio = j.height / j.width;
        refreshCanvasSize();
      }

      reloadImages(() => {
        if (shouldReapply) scheduleApply();
        else reloadDifferenceAndDraw();
        setStatus(`Session ${sessionId} ready — drag the split line`);
        if (state.autosave.enabled) debounceAutosave();
      });
    }

    db9LiveEditorRuntime.extractSessionId = extractSessionId;
    db9LiveEditorRuntime.widgetValue = widgetValue;
    db9LiveEditorRuntime.openEditor = openEditor;
    window.addEventListener("resize", () => {
      if (state.panel && !state.isMinimized) refreshCanvasSize();
    });

  },

  async beforeRegisterNodeDef(nodeType, nodeData, app) {
    const isTarget =
      nodeData?.name === "DB9LiveToneEditor" ||
      nodeData?.name === "DB9 Live Tone Editor";
    if (!isTarget) return;
    console.log("[DB9 Live Editor] Hooking node definition:", nodeData?.name, nodeType?.type || nodeType?.title || "unknown");

    function findSessionId(node) {
      return node?._db9SessionId || (node?.widgets || []).find(w => w?.name === "session_id")?.value || null;
    }

    const origOnNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function() {
      const r = origOnNodeCreated ? origOnNodeCreated.apply(this, arguments) : undefined;
      const hasButton = (this.widgets || []).some(w => w?.name === "🎨 Open Live Editor");
      if (!hasButton) {
        console.log("[DB9 Live Editor] Adding node button to:", this?.comfyClass || this?.type || "unknown");
        this.addWidget("button", "🎨 Open Live Editor", null, () => {
          const sid = findSessionId(this);
          console.log("[DB9 Live Editor] Button clicked. session_id =", sid);
          if (sid) {
            this._db9OpenEditor?.(sid);
          } else {
            alert("Run the node first to generate session_id.");
          }
        });
      }
      const hasFallbackButton = (this.widgets || []).some(w => w?.name === "Open Last DB9 Session");
      if (!hasFallbackButton) {
        this.addWidget("button", "Open Last DB9 Session", null, async () => {
          const sid = await findLatestSessionForNode(this);
          console.log("[DB9 Live Editor] Manual fallback session_id =", sid);
          if (sid) {
            this._db9SessionId = sid;
            this._db9OpenEditor?.(sid);
          } else {
            alert("No recent DB9 live editor session was found.");
          }
        });
      }
      return r;
    };

    const origOnExecuted = nodeType.prototype.onExecuted;
    nodeType.prototype.onExecuted = function(message) {
      if (origOnExecuted) origOnExecuted.apply(this, arguments);
      console.log("[DB9 Live Editor] onExecuted payload:", message);
      const sid = db9LiveEditorRuntime.extractSessionId?.(message) || null;
      console.log("[DB9 Live Editor] Extracted session_id:", sid);
      if (!sid) return;
      this._db9SessionId = sid;
      this._db9OpenEditor = db9LiveEditorRuntime.openEditor;
      if (db9LiveEditorRuntime.widgetValue?.(this, "enable_live_editor", true) !== false) {
        console.log("[DB9 Live Editor] Auto-opening editor for session:", sid);
        setTimeout(() => db9LiveEditorRuntime.openEditor?.(sid), 30);
      }
    };

    const origGetExtraMenuOptions = nodeType.prototype.getExtraMenuOptions;
    nodeType.prototype.getExtraMenuOptions = function(_, options) {
      options = origGetExtraMenuOptions ? (origGetExtraMenuOptions.apply(this, arguments) || options || []) : (options || []);
      options.push({
        content: "🎨 Open DB9 Live Editor",
        callback: () => {
          const sid = findSessionId(this);
          if (sid) db9LiveEditorRuntime.openEditor?.(sid);
          else alert("Run the node first to get a session_id, then open the editor.");
        },
      });
      return options;
    };
  },
});
