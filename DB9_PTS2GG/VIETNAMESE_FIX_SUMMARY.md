# 🇻🇳 VIETNAMESE ACCENT FIX SUMMARY (v0.4.7.7)

## 🔴 The Issue
Gemini's Vietnamese UI displays the local image uploader button as **"Tải tệp lên"** (accented).
The content script was searching for the unaccented equivalent **`'tai tep len'`** to score and identify the best upload element candidate:
```javascript
if (text.includes('tai tep len') || text.includes('upload file') || text.includes('upload images & files')) { ... }
```
Under some system configurations, Unicode normalization (`.normalize('NFD')`) or pre-composed text handling behaved differently, causing a mismatch where the button was not identified (`Upload menu item not found after waiting 1.5s`).

---

## 🟢 The Solution
We updated **`DB9_PTS2GG/extension/content/provider-gemini.js`** to natively match **both accented and unaccented** Vietnamese phrases:

1. **`isUploadText`**: Added support for `tệp` and `tải`/`lên`.
2. **`scoreUploadCandidate`**: Added check for `tải tệp lên`, `tải lên`, and `tệp`.
3. **`isToolsText`**: Added check for `nội dung` and `công cụ`.

Additionally, we **cleaned up multiple Unicode mojibakes** across the entire file, restoring clear, readable log strings and comments:
- Changed `Quay lÃƒÆ’Ã‚Â¡Ãƒâ€šÃ‚ÂºÃƒâ€šÃ‚Â¡i` ➔ `Quay lại`
- Changed `ÃƒÆ’Ã¢â‚¬Å¾Ãƒâ€šÃ‚Â` ➔ `Đóng`
- Changed `XÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³a` ➔ `Xóa`
- Fixed header comments and console logs containing corrupted strings.

---

## 📦 Version Bump
- Bumped the build version of the entire codebase from **`0.4.7.6`** to **`0.4.7.7`** across all UXP plugin, Chrome extension, and Bridge files to ensure version alignment.
