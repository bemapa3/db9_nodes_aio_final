# v0.4.7 CHECKLIST

Rules from user (Ân):
1. Phải check kỹ, sai ở đâu DỪNG TASK KHÁC lại để fix trước
2. Quản lý checklist, trả đúng yêu cầu
3. Code chạy mượt, không giật lag

## Issues from real test (log v0.4.6)

### 🔴 CRITICAL: Plugin NOT connected to bridge
- [ ] Panel shows "bridge OFF" → plugin cannot POST /generate
- [ ] Root cause suspect: UXP localhost fetch CORS, or pollHealth error swallowed
- [ ] BEFORE anything else: fix bridge connection + write visible diagnostic

### 🔴 CRITICAL: Gemini upload still fails "no input type=file"
- [ ] Recorder path Tools → Open upload file menu → uploader-images-files-button-advanced IS correct
- [ ] But code logs "no input after 1.5s" → timing or click dispatch issue
- [ ] Need: use real native MouseEvent instead of .click(), or wait longer after uploader button

### 🟡 HD image only 1024×559
- [ ] Image IS full res at that size — Gemini returns 1024x559 for aspect ratio ~16:9 by default
- [ ] download-generated-image-button click needs better blob capture
- [ ] Possibly need to force aspect ratio 1:1 in prompt

### 🟡 ChatGPT not tested
- [ ] Log doesn't show chatgpt runs → need Test ChatGPT button visible

## Features requested

### 🆕 1. Panel orientation: vertical AND horizontal
- [ ] CSS: detect container aspect, switch layout
- [ ] When wide: 2-column (preview left, controls right)
- [ ] When tall: single column (current)

### 🆕 2. Reference image upload
- [ ] New section "📎 Reference" — user uploads a reference image
- [ ] AI describes reference (either local vision or send via bridge to LLM)
- [ ] Description auto-appended to prompt as "match style/mood of: <desc>"
- [ ] Can save reference+description as preset (architecture / furniture / people categories)

### 🆕 3. PS selection → 1:1 square crop → new layer workflow
- [ ] When user clicks Generate:
  - Read PS selection bounds
  - If not 1:1, expand shorter side to square (pad with transparent or content-aware)
  - Export as 1024x1024 PNG
  - Send to provider
  - On result: place as NEW LAYER above original (not replace Smart Object)

### 🆕 6. Design panel đẹp hơn
- [ ] More Adobe-native look: softer gradients, better typography
- [ ] Icon polish, spacing consistency
- [ ] Tab indicators with real icons

## Execution order (STOP if any fails)
1. FIX bridge connection (#1)
2. VERIFY by curl → if bridge accessible, problem is UXP network permissions
3. FIX Gemini upload (#2) with better click dispatch
4. ONLY THEN: implement new features
