# DB9 Multi-Provider Bridge — Quick Start (v0.4.0)

v0.4.0 ships a **unified 176-preset library** across 11 categories
(Style, Mood, Camera, People, Objects, Architecture, Environment, Lighting,
Materials, Photographer, RealEstate) with tag filtering, search, and curated
defaults. Both the Chrome extension popup and the Photoshop UXP panel now
browse the same library.

Previous highlights:
- v0.3.x added **ChatGPT** as a second provider alongside **Gemini**.

## Cấu trúc
```
db9-gemini-bridge/
├── bridge/                     # Local Node.js server (port 8765)
│   └── server.js               # + GET /presets (v0.4.0)
├── extension/                  # Chrome MV3 extension
│   ├── presets/presets.json    # 176 presets, 11 categories (v0.4.0)
│   ├── popup/                  # Search + tag filter + defaults button
│   └── content/
│       ├── provider-gemini.js
│       ├── provider-chatgpt.js
│       └── content-script.js
└── uxp-plugin/                 # Photoshop UXP panel
    └── index.{html,js}         # Inline preset browser (v0.4.0)
```

## Cài đặt

### 1. Bridge server
```cmd
cd bridge
npm install
npm start
```
Phải thấy:
```
DB9 Multi-Provider Bridge v0.4.0
HTTP:  http://127.0.0.1:8765
Providers: gemini, chatgpt
```

### 2. Chrome extension
1. Vào `chrome://extensions`
2. Bật **Developer mode**
3. Click **Load unpacked** → chọn folder `extension/`
4. Badge **ON** (xanh) = connected.

### 3. Mở provider tabs
- Gemini: `https://gemini.google.com/app`
- ChatGPT: `https://chatgpt.com/` (đảm bảo model 4o image-gen được chọn)

### 4. Photoshop
Mở panel **DB9 Multi-Provider** → chọn provider ở dropdown đầu panel → bấm
**🎨 Presets** để mở preset library inline (search/tag/default) → chọn tối đa
4 preset → Generate.

## Preset library (v0.4.0)
- **176 presets** across **11 categories**.
- Schema per entry:
  ```json
  {
    "id": "hyperreal_dbox",
    "category": "Style",
    "label": "Hyperreal Editorial (Dbox)",
    "labelEn": "Hyperreal Editorial (Dbox)",
    "icon": "💠",
    "prompt": "...",
    "tags": ["archviz", "editorial", "luxury"],
    "default": false
  }
  ```
- Curated **⭐ default** flagged in each category so "Load defaults" gives a
  solid starting stack (1 per category, capped to 4).
- **Categories**: Style (31) · Mood (21) · Camera (18) · People (20) ·
  Objects (14) · Architecture (14) · Environment (14) · Lighting (12) ·
  Materials (12) · Photographer (10) · RealEstate (10).

## Endpoints
- `GET  /health` — bridge + providers online
- `GET  /presets` — full preset library (v0.4.0)
- `POST /generate` — submit job. Payload:
  ```json
  {
    "imageBase64": "...",
    "mime": "image/png",
    "prompt": "...",
    "mode": "new",
    "provider": "gemini",
    "presetIds": ["hyperreal_dbox", "magic_hour"]
  }
  ```
- `GET  /job/:id` — poll job status; response includes `provider`.

## Modes
- `new` — tạo chat mới
- `regen` — gửi prompt cũ vào chat hiện tại
- `refine` — gửi prompt mới vào chat cũ

## ⚠ ChatGPT selectors are UNVERIFIED
ChatGPT's UI changes often. See inline comments in `provider-chatgpt.js` for
every selector marked UNVERIFIED. If an action fails, inspect the element in
DevTools and update the corresponding selector function.
