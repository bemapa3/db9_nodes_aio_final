app.registerExtension({
  name: "db9.live_editor",
  async setup(app) {

    // ─── State ───────────────────────────────────────────────────────────────
    const state = {
      sessionId: null,
      panel: null,
      originalImg: new Image(),
      editedImg:   new Image(),
      params: {
        exposure: 0, contrast: 0, highlights: 0, shadows: 0,
        whites: 0, blacks: 0, vibrance: 0, saturation: 0,
        temperature: 0, tint: 0,
        red_balance: 0, green_balance: 0, blue_balance: 0,
        curve_lift: 0, curve_gamma: 1.0, curve_gain: 1.0,
      },
      compare: { mode: "vertical", splitPosition: 0.5, differenceGain: 4.0 },
      autosave: { enabled: false, delayMs: 700, timer: null },
      applyTimer: null,
      drag: { active: false },
      sliderRefs: {},   // key → { input, valSpan }
    };

    // ─── API helper ──────────────────────────────────────────────────────────
    function api(path, opts = {}) {
      return fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
    }

    function sid() { return state.sessionId; }
    function imgUrl(kind) { return `/db9/live_editor/session/${sid()}/image?kind=${kind}&ts=${Date.now()}`; }

    // ─── Status bar ──────────────────────────────────────────────────────────
    function setStatus(txt) {
      const el = document.getElementById("db9-status");
      if (el) el.textContent = txt;
    }

    // ─── Canvas split renderer ───────────────────────────────────────────────
    function getCanvas() { return document.getElementById("db9-canvas"); }

    function drawCanvas() {
      const canvas = getCanvas();
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
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
    function scheduleApply() {
      if (state.applyTimer) return;
      state.applyTimer = setTimeout(async () => {
        state.applyTimer = null;
        if (!sid()) return;
        const r = await api(`/db9/live_editor/session/${sid()}/apply`, {
          method: "POST",
          body: JSON.stringify({ params: state.params }),
        });
        const j = await r.json();
        if (j.ok) {
          state.editedImg = new Image();
          state.editedImg.onload = () => { reloadDifferenceAndDraw(); debounceAutosave(); };
          state.editedImg.src = j.preview_url;
          setStatus("Preview updated");
        }
      }, 80);
    }

    // ─── Autosave ─────────────────────────────────────────────────────────────
    function debounceAutosave() {
      if (!state.autosave.enabled || !sid()) return;
      clearTimeout(state.autosave.timer);
      state.autosave.timer = setTimeout(async () => {
        const r = await api(`/db9/live_editor/session/${sid()}/autosave`, {
          method: "POST", body: JSON.stringify({}),
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
      const defaults = {
        exposure: 0, contrast: 0, highlights: 0, shadows: 0,
        whites: 0, blacks: 0, vibrance: 0, saturation: 0,
        temperature: 0, tint: 0,
        red_balance: 0, green_balance: 0, blue_balance: 0,
        curve_lift: 0, curve_gamma: 1.0, curve_gain: 1.0,
      };
      Object.assign(state.params, defaults);
      // update all slider DOMs
      for (const [key, ref] of Object.entries(state.sliderRefs)) {
        ref.input.value    = String(defaults[key]);
        ref.valSpan.textContent = String(defaults[key]);
      }
      state.editedImg = new Image();
      state.editedImg.onload = drawCanvas;
      state.editedImg.src = j.preview_url;
      setStatus("Reset to defaults");
    }

    async function closeEditor() {
      if (sid()) {
        await api(`/db9/live_editor/session/${sid()}/close`, { method: "POST", body: JSON.stringify({}) });
      }
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
        scheduleApply();
      };

      state.sliderRefs[key] = { input, valSpan };
      wrap.append(top, input);
      return wrap;
    }

    // ─── Build Panel ──────────────────────────────────────────────────────────
    function buildPanel() {
      const panel = css(document.createElement("div"),
        `position:fixed;right:18px;top:56px;width:500px;max-height:90vh;overflow-y:auto;
         background:#18181c;color:#e0e0e0;border:1px solid #3a3a3a;border-radius:12px;
         padding:14px;z-index:999999;box-shadow:0 12px 40px rgba(0,0,0,.55);
         font-family:system-ui,sans-serif;`);
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

      // ── action buttons ──
      const actions = row(
        btn("💾 Save Now", saveNow, "background:#2a4a2a;border-color:#3a7a3a;"),
        btn("↩ Reset", resetEditor),
        btn("✕ Close", closeEditor, "background:#4a2020;border-color:#7a3a3a;margin-left:auto;")
      );

      // ── canvas (drag-split view) ──
      const canvasWrap = css(document.createElement("div"),
        "position:relative;margin:10px 0;border-radius:8px;overflow:hidden;border:1px solid #333;");
      const canvas = css(document.createElement("canvas"), "display:block;width:100%;");
      canvas.id     = "db9-canvas";
      canvas.width  = 800;
      canvas.height = 500;
      canvasWrap.appendChild(canvas);

      // ── compare mode bar ──
      const modes = ["vertical","horizontal","side_by_side","difference","original","edited"];
      const modeBar = css(document.createElement("div"),
        "display:flex;gap:4px;flex-wrap:wrap;margin:6px 0;");
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
          // update cursor
          const c = getCanvas();
          if (c) c.style.cursor = m === "horizontal" ? "row-resize" : m === "vertical" ? "col-resize" : "default";
          // highlight active
          modeBar.querySelectorAll("button").forEach(x =>
            x.style.background = x.dataset.mode === m ? "#3366aa" : "#2a2a2e");
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
        if (state.compare.mode === "difference") await reloadDifferenceAndDraw();
      };

      // ── autosave row ──
      const autosaveRow = row();
      const asLabel = css(document.createElement("label"),
        "font-size:12px;color:#ccc;flex:1;display:flex;gap:6px;align-items:center;cursor:pointer;");
      const asCheck = document.createElement("input");
      asCheck.type = "checkbox";
      asCheck.onchange = () => { state.autosave.enabled = asCheck.checked; };
      asLabel.append(asCheck, document.createTextNode("Autosave"));
      const asDelay = css(document.createElement("input"),
        "width:80px;padding:3px 6px;background:#252528;border:1px solid #444;border-radius:4px;color:#eee;font-size:12px;");
      asDelay.type = "number"; asDelay.value = "700"; asDelay.min = "100"; asDelay.max = "5000";
      asDelay.onchange = () => { state.autosave.delayMs = parseInt(asDelay.value || "700"); };
      const asUnit = css(document.createElement("span"), "font-size:11px;color:#888;");
      asUnit.textContent = "ms";
      autosaveRow.append(asLabel, asDelay, asUnit);

      // ── save options ──
      function inlineSelect(id, opts, def) {
        const s = css(document.createElement("select"),
          "background:#252528;border:1px solid #444;border-radius:4px;color:#eee;font-size:12px;padding:3px 4px;");
        s.id = id;
        opts.forEach(v => { const o = document.createElement("option"); o.value=v; o.textContent=v; if(v===def)o.selected=true; s.appendChild(o); });
        return s;
      }
      function inlineText(id, def, w) {
        const i = css(document.createElement("input"),
          `width:${w||"120px"};padding:3px 6px;background:#252528;border:1px solid #444;border-radius:4px;color:#eee;font-size:12px;`);
        i.id = id; i.value = def;
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
      panel.append(
        header, actions, hr(),
        canvasWrap,
        modeBar,
        diffGainWrap,
        hr(),
        autosaveRow, saveRow1, saveRow2,
        hr(),
        sliders,
      );

      document.body.appendChild(panel);
      state.panel = panel;
      attachCanvasDrag(canvas);
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

      // set canvas aspect ratio from image dimensions
      const canvas = getCanvas();
      if (canvas && j.width && j.height) {
        const ratio = j.height / j.width;
        canvas.height = Math.round(canvas.width * ratio);
      }

      reloadImages(() => { setStatus(`Session ${sessionId} ready — drag the split line`); });
    }

    // ─── Hook into ComfyUI node ───────────────────────────────────────────────
    function findSessionId(node) {
      return (node?.widgets || []).find(w => w.name === "session_id")?.value || null;
    }

    // Add "Open Live Editor" button widget directly on node
    const origNodeCreated = app.graph?.onNodeAdded;
    app.registerExtension && true; // already registered, hook below

    const origMenu = LiteGraph.LGraphNode.prototype.getExtraMenuOptions;
    LiteGraph.LGraphNode.prototype.getExtraMenuOptions = function(_, options) {
      options = origMenu ? (origMenu.apply(this, arguments) || options || []) : (options || []);
      const title = this.comfyClass || this.type || "";
      if (title.includes("DB9LiveToneEditor") || title.includes("DB9 Live Tone Editor")) {
        options.push({
          content: "🎨 Open DB9 Live Editor",
          callback: () => {
            const sid = findSessionId(this);
            if (sid) openEditor(sid);
            else alert("Run the node first to get a session_id, then open the editor.");
          },
        });
      }
      return options;
    };

    // Also add a dedicated button widget on the node
    const origOnNodeCreated = app.nodeCreated;
    app.nodeCreated = function(node) {
      if (origOnNodeCreated) origOnNodeCreated.call(this, node);
      const title = node?.comfyClass || node?.type || "";
      if (title.includes("DB9LiveToneEditor") || title.includes("DB9 Live Tone Editor")) {
        node.addWidget("button", "🎨 Open Live Editor", null, () => {
          const sid = findSessionId(node);
          if (sid) openEditor(sid);
          else alert("Run the node first to generate session_id.");
        });
      }
    };
  },
});
