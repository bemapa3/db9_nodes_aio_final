app.registerExtension({
  name: "db9.live_editor",
  async setup(app) {
    const state = {
      sessionId: null,
      panel: null,
      params: {
        exposure: 0, contrast: 0, highlights: 0, shadows: 0,
        whites: 0, blacks: 0, vibrance: 0, saturation: 0,
        temperature: 0, tint: 0, red_balance: 0, green_balance: 0,
        blue_balance: 0, curve_lift: 0, curve_gamma: 1, curve_gain: 1,
      },
      compare: { mode: "vertical", splitPosition: 0.5, differenceGain: 4.0 },
      autosave: { enabled: false, delayMs: 700, timer: null },
      applyTimer: null,
    };

    function api(path, options={}) {
      return fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
    }

    function updateStatus(text) {
      const el = document.getElementById("db9-live-status");
      if (el) el.textContent = text;
    }

    function imgUrl(kind) {
      return `/db9/live_editor/session/${state.sessionId}/image?kind=${kind}&ts=${Date.now()}`;
    }

    async function renderCompare() {
      if (!state.sessionId) return;
      const r = await api(`/db9/live_editor/session/${state.sessionId}/compare`, {
        method: "POST",
        body: JSON.stringify({
          mode: state.compare.mode,
          split_position: state.compare.splitPosition,
          difference_gain: state.compare.differenceGain,
        }),
      });
      const j = await r.json();
      const img = document.getElementById("db9-live-compare");
      if (img && j.ok) img.src = j.compare_url;
    }

    function debounceAutosave() {
      if (!state.autosave.enabled || !state.sessionId) return;
      clearTimeout(state.autosave.timer);
      state.autosave.timer = setTimeout(async () => {
        const r = await api(`/db9/live_editor/session/${state.sessionId}/autosave`, {
          method: "POST",
          body: JSON.stringify({ reason: "debounced" }),
        });
        const j = await r.json();
        updateStatus(`Autosaved: ${j.saved_path || "ok"}`);
      }, state.autosave.delayMs);
    }

    function scheduleApply() {
      if (state.applyTimer) return;
      state.applyTimer = setTimeout(async () => {
        state.applyTimer = null;
        if (!state.sessionId) return;
        const r = await api(`/db9/live_editor/session/${state.sessionId}/apply`, {
          method: "POST",
          body: JSON.stringify({ params: state.params }),
        });
        const j = await r.json();
        if (j.ok) {
          const img = document.getElementById("db9-live-edited");
          if (img) img.src = j.preview_url;
          await renderCompare();
          debounceAutosave();
          updateStatus("Preview updated");
        }
      }, 80);
    }

    function row() {
      const d = document.createElement("div");
      d.style.cssText = "display:flex;gap:8px;align-items:center;margin:4px 0;";
      return d;
    }

    function button(text, onClick) {
      const b = document.createElement("button");
      b.textContent = text;
      b.style.cssText = "padding:6px 10px;";
      b.onclick = onClick;
      return b;
    }

    function slider(label, key, min, max, step, value, onChange=null) {
      const wrap = document.createElement("div");
      wrap.style.cssText = "display:flex;flex-direction:column;gap:2px;margin:6px 0;";
      const top = row();
      const lab = document.createElement("label");
      lab.textContent = label;
      lab.style.flex = "1";
      const val = document.createElement("span");
      val.textContent = String(value);
      val.style.minWidth = "56px";
      val.style.textAlign = "right";
      const input = document.createElement("input");
      input.type = "range";
      input.min = String(min); input.max = String(max); input.step = String(step); input.value = String(value);
      input.oninput = async () => {
        const v = parseFloat(input.value);
        val.textContent = input.value;
        if (onChange) await onChange(v);
        else { state.params[key] = v; scheduleApply(); }
      };
      top.append(lab, val);
      wrap.append(top, input);
      return wrap;
    }

    function select(label, options, current, onChange) {
      const wrap = row();
      const lab = document.createElement("label");
      lab.textContent = label;
      lab.style.flex = "1";
      const sel = document.createElement("select");
      options.forEach(v => {
        const o = document.createElement("option");
        o.value = v; o.textContent = v;
        if (v === current) o.selected = true;
        sel.appendChild(o);
      });
      sel.onchange = () => onChange(sel.value);
      wrap.append(lab, sel);
      return wrap;
    }

    async function saveNow() {
      if (!state.sessionId) return;
      const prefix = document.getElementById("db9-live-prefix")?.value || "DB9_Live_Edit";
      const saveMode = document.getElementById("db9-live-save-mode")?.value || "versioned";
      const fmt = document.getElementById("db9-live-format")?.value || "PNG";
      const q = parseInt(document.getElementById("db9-live-jpeg-q")?.value || "95");
      const r = await api(`/db9/live_editor/session/${state.sessionId}/save`, {
        method: "POST",
        body: JSON.stringify({ filename_prefix: prefix, save_mode: saveMode, output_format: fmt, jpeg_quality: q }),
      });
      const j = await r.json();
      updateStatus(`Saved: ${j.saved_path || "ok"}`);
    }

    async function resetEditor() {
      if (!state.sessionId) return;
      const r = await api(`/db9/live_editor/session/${state.sessionId}/reset`, { method: "POST", body: JSON.stringify({}) });
      const j = await r.json();
      if (j.ok) {
        Object.assign(state.params, {
          exposure: 0, contrast: 0, highlights: 0, shadows: 0, whites: 0, blacks: 0,
          vibrance: 0, saturation: 0, temperature: 0, tint: 0,
          red_balance: 0, green_balance: 0, blue_balance: 0,
          curve_lift: 0, curve_gamma: 1, curve_gain: 1,
        });
        const edited = document.getElementById("db9-live-edited");
        if (edited) edited.src = j.preview_url;
        await renderCompare();
        updateStatus("Reset");
      }
    }

    async function closeEditor() {
      if (state.sessionId) {
        await api(`/db9/live_editor/session/${state.sessionId}/close`, { method: "POST", body: JSON.stringify({}) });
      }
      if (state.panel) state.panel.remove();
      state.panel = null;
      state.sessionId = null;
    }

    function buildPanel() {
      const panel = document.createElement("div");
      panel.id = "db9-live-editor-panel";
      panel.style.cssText = "position:fixed;right:18px;top:56px;width:470px;max-height:88vh;overflow:auto;background:#1b1b1f;color:#fff;border:1px solid #444;border-radius:12px;padding:12px;z-index:999999;box-shadow:0 10px 30px rgba(0,0,0,0.35);";
      const title = document.createElement("h3");
      title.textContent = "DB9 Live Tone Editor";
      title.style.margin = "0 0 8px 0";
      const status = document.createElement("div");
      status.id = "db9-live-status";
      status.style.cssText = "font-size:12px;opacity:0.85;margin-bottom:8px;";
      status.textContent = "Idle";

      const actions = row();
      actions.append(button("Save Now", saveNow), button("Reset", resetEditor), button("Close", closeEditor));

      const autos = row();
      const autosLabel = document.createElement("label");
      autosLabel.textContent = "Autosave";
      autosLabel.style.flex = "1";
      const autosCheck = document.createElement("input");
      autosCheck.type = "checkbox";
      autosCheck.onchange = () => { state.autosave.enabled = autosCheck.checked; };
      const autosDelay = document.createElement("input");
      autosDelay.type = "number";
      autosDelay.value = "700";
      autosDelay.min = "100";
      autosDelay.max = "5000";
      autosDelay.style.width = "90px";
      autosDelay.onchange = () => { state.autosave.delayMs = parseInt(autosDelay.value || "700"); };
      autos.append(autosLabel, autosCheck, autosDelay);

      const prefixRow = row();
      const prefixLabel = document.createElement("label");
      prefixLabel.textContent = "Filename";
      prefixLabel.style.flex = "1";
      const prefixInput = document.createElement("input");
      prefixInput.id = "db9-live-prefix";
      prefixInput.value = "DB9_Live_Edit";
      prefixRow.append(prefixLabel, prefixInput);

      const modeRow = row();
      const modeLabel = document.createElement("label");
      modeLabel.textContent = "Save Mode";
      modeLabel.style.flex = "1";
      const modeSelect = document.createElement("select");
      modeSelect.id = "db9-live-save-mode";
      ["versioned", "overwrite"].forEach(v => {
        const o = document.createElement("option"); o.value = v; o.textContent = v; modeSelect.appendChild(o);
      });
      modeRow.append(modeLabel, modeSelect);

      const fmtRow = row();
      const fmtLabel = document.createElement("label");
      fmtLabel.textContent = "Format";
      fmtLabel.style.flex = "1";
      const fmt = document.createElement("select");
      fmt.id = "db9-live-format";
      ["PNG", "JPEG", "WEBP"].forEach(v => {
        const o = document.createElement("option"); o.value = v; o.textContent = v; fmt.appendChild(o);
      });
      const q = document.createElement("input");
      q.id = "db9-live-jpeg-q";
      q.type = "number"; q.value = "95"; q.min = "1"; q.max = "100"; q.style.width = "70px";
      fmtRow.append(fmtLabel, fmt, q);

      const orig = document.createElement("img");
      orig.id = "db9-live-original";
      orig.style.cssText = "width:100%;margin-top:8px;border-radius:8px;border:1px solid #333;";
      const edited = document.createElement("img");
      edited.id = "db9-live-edited";
      edited.style.cssText = "width:100%;margin-top:8px;border-radius:8px;border:1px solid #333;";
      const compare = document.createElement("img");
      compare.id = "db9-live-compare";
      compare.style.cssText = "width:100%;margin-top:8px;border-radius:8px;border:1px solid #333;";

      panel.append(
        title, status, actions, autos, prefixRow, modeRow, fmtRow,
        orig, edited,
        select("Compare Mode", ["original", "edited", "vertical", "horizontal", "side_by_side", "difference"], "vertical", async v => { state.compare.mode = v; await renderCompare(); }),
        slider("Split Position", null, 0, 1, 0.01, 0.5, async v => { state.compare.splitPosition = v; await renderCompare(); }),
        slider("Difference Gain", null, 1, 16, 0.1, 4.0, async v => { state.compare.differenceGain = v; await renderCompare(); }),
        compare,
        document.createElement("hr"),
        slider("Exposure", "exposure", -2, 2, 0.01, 0),
        slider("Contrast", "contrast", -1, 1, 0.01, 0),
        slider("Highlights", "highlights", -1, 1, 0.01, 0),
        slider("Shadows", "shadows", -1, 1, 0.01, 0),
        slider("Whites", "whites", -1, 1, 0.01, 0),
        slider("Blacks", "blacks", -1, 1, 0.01, 0),
        slider("Vibrance", "vibrance", -1, 1, 0.01, 0),
        slider("Saturation", "saturation", -1, 1, 0.01, 0),
        slider("Temperature", "temperature", -1, 1, 0.01, 0),
        slider("Tint", "tint", -1, 1, 0.01, 0),
        slider("Red Balance", "red_balance", -1, 1, 0.01, 0),
        slider("Green Balance", "green_balance", -1, 1, 0.01, 0),
        slider("Blue Balance", "blue_balance", -1, 1, 0.01, 0),
        slider("Curve Lift", "curve_lift", -1, 1, 0.01, 0),
        slider("Curve Gamma", "curve_gamma", 0.2, 3.0, 0.01, 1.0),
        slider("Curve Gain", "curve_gain", 0.2, 3.0, 0.01, 1.0)
      );
      document.body.appendChild(panel);
      state.panel = panel;
    }

    async function openEditor(sessionId) {
      state.sessionId = sessionId;
      if (!state.panel) buildPanel();
      const r = await api("/db9/live_editor/session/init", {
        method: "POST",
        body: JSON.stringify({ session_id: sessionId }),
      });
      const j = await r.json();
      if (!j.ok) {
        updateStatus("Session init failed");
        return;
      }
      document.getElementById("db9-live-original").src = imgUrl("reference");
      document.getElementById("db9-live-edited").src = imgUrl("current");
      await renderCompare();
      updateStatus(`Session ${sessionId} ready`);
    }

    function findSessionId(node) {
      const widgets = node?.widgets || [];
      const w = widgets.find(x => x.name === "session_id");
      return w && w.value ? w.value : null;
    }

    const origMenu = LiteGraph.LGraphNode.prototype.getExtraMenuOptions;
    LiteGraph.LGraphNode.prototype.getExtraMenuOptions = function(_, options) {
      options = origMenu ? (origMenu.apply(this, arguments) || options || []) : (options || []);
      const title = this.comfyClass || this.type || "";
      if (title.includes("DB9 Live Tone Editor")) {
        options.push({
          content: "Open DB9 Live Editor",
          callback: () => {
            const sid = findSessionId(this);
            if (sid) openEditor(sid);
            else updateStatus("Run the node first to create session_id");
          }
        });
      }
      return options;
    };
  }
});
