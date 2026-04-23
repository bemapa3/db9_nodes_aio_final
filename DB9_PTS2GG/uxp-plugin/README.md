# DB9 Gemini Auto — Photoshop UXP Plugin

A Photoshop panel that automates the i8 Studio "Photoshop → Gemini Nano Banana Pro" workflow:

1. You make a selection in Photoshop.
2. Click **🚀 Generate** in the panel.
3. The plugin duplicates the selection to a new layer, wraps it in a **Smart Object**, exports it as PNG, and sends it through the local **DB9 bridge server** to the **DB9 Chrome extension**, which automates a Gemini chat.
4. The generated image is downloaded back and **replaces the Smart Object contents** — so you keep non-destructive editability and can re-run the AI as many times as you like.

## Architecture (recap)

```
Photoshop Panel (UXP)
   ↓ HTTP POST /generate { imageBase64, prompt, mode }
DB9 Bridge Server (Node.js, 127.0.0.1:8765)
   ↓ WebSocket push
DB9 Chrome Extension (content script on gemini.google.com)
   ↓ DOM automation
Gemini → image generated
   ↑ result POST back to bridge
Photoshop Panel polls /job/:id → receives base64 PNG
   ↓ replaceContents on Smart Object
✅ Done
```

## Prerequisites

1. **Adobe Photoshop 2024 (v25)** or newer — recommended **Photoshop 2026 (v27.5)**.
2. **Adobe UXP Developer Tool (UDT)** — download from Adobe Creative Cloud Desktop → "Apps" → search "UXP Developer Tool".
3. **Node.js 18+** for the bridge server.
4. **Google Chrome** with the DB9 extension loaded (see `../extension/`).
5. The **DB9 bridge server** must be running before you click Generate.

## Install

### 1. Run the bridge server

```bash
cd ../bridge
npm install
node server.js     # listens on http://127.0.0.1:8765
```

### 2. Load the Chrome extension

1. Open `chrome://extensions`.
2. Enable **Developer mode** (top-right toggle).
3. Click **Load unpacked** → pick `../extension/`.
4. Pin the extension. Open its popup → **Presets** tab to (optionally) select default archviz presets that auto-prepend to every prompt.
5. Open `https://gemini.google.com/app` in a tab and leave it open. Make sure you're signed into a Gemini account that has Nano Banana Pro / image generation access.

### 3. Load the UXP plugin in Photoshop

1. Launch **Adobe UXP Developer Tool (UDT)**.
2. Click **Add Plugin…** → select this folder's `manifest.json` (`uxp-plugin/manifest.json`).
3. The plugin appears in UDT's list. Click the **•••** action menu → **Load** to inject it into Photoshop.
4. In Photoshop: **Plugins menu → DB9 Gemini Auto** to open the panel. Dock it like any other panel.

> Tip: in UDT click the **•••** menu → **Watch** to auto-reload on file changes during development.

## Usage

1. Open a photo or scene in Photoshop.
2. Make a selection (marquee, lasso, quick selection — anything).
3. In the panel:
   - Type a **prompt** (e.g. *"add cinematic golden hour lighting and 12 business pedestrians walking"*).
   - Pick a **mode**:
     - **New chat** — fresh Gemini session, uses your selection as the input.
     - **Regen** — re-runs the same prompt against the active Smart Object on the last chat (useful for sampling variations).
     - **Refine** — keeps the chat context but sends a new prompt (e.g. *"now make the lighting cooler and remove the people"*).
   - Click **🚀 Generate**.
4. Watch the progress steps. When it finishes the Smart Object updates in place — your underlying photo is untouched.

## Bridge URL

Default `http://127.0.0.1:8765`. Change in **Settings** at the bottom of the panel if you proxy the bridge elsewhere.

## Presets

Archviz presets (style / mood / people / objects / architecture / environment) are configured **once** in the Chrome extension popup. Selected presets are automatically **prepended** to every prompt the bridge forwards to Gemini, so the panel stays minimal.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| "Bridge: OFF" red dot | Start the bridge: `node bridge/server.js`. Check `http://127.0.0.1:8765/health`. |
| "No active selection" | Make a marquee/lasso selection first. Required only for **New chat** mode. |
| Plugin won't load in UDT | Photoshop must be running; check Photoshop minVersion in `manifest.json` matches your install. |
| Gemini returns nothing / job times out | Open the Gemini tab manually, make sure you're logged in and Image Generation is enabled. Check the extension popup → bridge connected. |
| `placedLayerReplaceContents` error | The active layer must still be the Smart Object created by the plugin — don't click off it during processing. |
| `network` permission denied | UXP enforces the `requiredPermissions.network.domains` allowlist. To use a non-localhost bridge, edit `manifest.json`. |

## Known caveats (v0.1.0)

- The export step duplicates the document briefly (used to flatten the SO to PNG) — large docs add a couple seconds.
- "Regen" / "Refine" assume the active layer is the previous SO; clicking off it loses context.
- Chat history thumbnails in the panel are heavily truncated previews (real saving of result PNGs to disk = todo).
- No auth on the bridge server — only bind to 127.0.0.1.
