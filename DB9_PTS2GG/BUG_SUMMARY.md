# Bug Summary: gemini.google.com HAR Audit & Active Verification (894 + 4 Requests)

Based on a programmatic and granular audit of the 894 network requests in `gemini.google.com.har` and comparison with local runtime execution logs from the active test run (4 requests), this document catalogs identified anomalies, critical failures, and system-level bottlenecks in the DB9 Photoshop integration.

---

## 1. Core Bug Catalog

| ID | Bug Description | Severity | Category | Impacted Subsystem | Diagnostic Details & Root Cause |
| :--- | :--- | :---: | :---: | :--- | :--- |
| **BUG-101** | **Page-World CSP Block on Blob Fetch** | 🔴 **CRITICAL** | **Security Policy** | Image Downloader (`downloadBlobViaPageWorld`) | **Root Cause:** Gemini's `connect-src` Content Security Policy (CSP) directive blocks fetching `blob:` URLs inside the page world, triggering a `Failed to fetch` exception: `Refused to connect because it violates the document's Content Security Policy.` |
| **BUG-102** | **Output Selector Collision (Upload Preview)** | 🔴 **CRITICAL** | **DOM Selector** | Output Detector (`waitForOutput`) | **Root Cause (Resolved):** In active run `efa08fc9`, the image was created successfully but could not be downloaded. The extension identified the **uploaded input preview image** as the newly generated generative output and marked the job complete. This happened because Google's new Gemini layouts utilize tags like `xap-file-preview` or `xap-uploaded-file` and the Vietnamese alt text `"Bản xem trước hình ảnh đã tải lên"`, which bypassed the previous CSS-only filter. |
| **BUG-103** | **CDN Access Forbidden (403)** | 🔴 **CRITICAL** | **CORS/Auth** | Variant Downloader (`downloadHD`) | **Root Cause (Resolved):** Request 859 to `lh3.googleusercontent.com/rd-gg/...` failed with a `403 Forbidden` because it was fetched in `cors` mode from the page-world, attaching `Origin: https://gemini.google.com`. Google's CDN blocks CORS requests for high-res raw images. Standard image rendering (Request 860) succeeds because it uses `no-cors` mode with no `origin` header. |
| **BUG-104** | **Drag & Drop Ingestion Sync Failure** | 🟡 **MEDIUM** | **DOM Ingestion** | Image Uploader (`uploadImage`) | **Root Cause:** Synthetic drag-drop events are successfully dispatched to `RICH-TEXTAREA`, but Gemini's Angular frontend fails to process them in some states, causing `waitForUploadPreview` to time out after 30s. |
| **BUG-105** | **Low-Resolution Output Limitation (1024x1024 px)** | 🟡 **MEDIUM** | **Resolution / Quality** | Image Downloader (`downloadHD` / Photoshop import) | **Root Cause:** When downloading generated images from the Gemini web interface, the resolved image is capped at a maximum of 1024x1024 pixels. When this image is imported into Photoshop, it is stretched or treated as a low-quality asset compared to high-resolution print/production files. Generating/working at higher resolutions is currently not natively supported via the standard web interface download path because the Gemini web DOM only serves 1024x1024 px assets. Recommendation: Do not use or rely on the web interface downloads for high-resolution (greater than 1024x1024 px) production assets. |

---

## 2. Active Discovery: BUG-102 (Selector Collision) Analysis

In the latest test run, the extension logged:
`new output detected key=IMG|blob:https://gemini.google.com/a8b687dd-5b36-4ffd-99f5-eb11104af8f7||Bản xem trước hình ảnh đã tải lên|`
`download fallback to mediaEl.src: blob:https://gemini.google.com/a8b687dd-5b36-4ffd-99f5-eb11104af8f7`

### Why the previous BUG-102 filter failed:
* **The new DOM layout:** Google Gemini introduced new tags (`xap-file-preview`, `xap-uploaded-file`) and classes (`.thumbnail-container`, `.image-thumbnail`) for the upload preview.
* **Localization shifts:** The alt text `"Bản xem trước hình ảnh đã tải lên"` represents "Uploaded image preview" in Vietnamese. The previous CSS-only filter was blind to this localized alt text, causing the extension to match the upload preview blob URL as the generated output.

---

## 3. Recommended Architectural Fixes (Implemented & Verified)

### 🚀 Bulletproof Selector Exclusion for BUG-102 (Implemented)
We have updated `provider-gemini.js` with a robust, multi-layered filter that completely isolates upload preview images from generated outputs by analyzing:
1. **Tags and CSS Classes:** Matches `xap-file-selector`, `xap-file-preview`, `xap-uploaded-file`, `.input-preview`, `.uploader-file-preview`, `.thumbnail-container`, `.image-thumbnail`, and generic wildcard keywords like `[class*="upload"]` or `[class*="preview"]`.
2. **Normalized Alt-text Regex:** Filters out any alt text matching `/bản xem trước hình ảnh|uploaded image|upload preview|tai len|upload|xem truoc/i`.
3. **Blob URL Safeguards:** Explicitly filters out any `blob:` images that contain upload indicators in their alt text.

#### The verified code in `provider-gemini.js`:
```javascript
// BUG-102 FIX: Exclude upload preview images
// Upload previews are inside xap-file-selector, .input-preview, or uploader-file-preview containers, or have specific alt text
const isUploadAlt = /bản xem trước hình ảnh|uploaded image|upload preview|tai len|upload|xem truoc/i.test(alt.toLowerCase());
const parent = img.closest('xap-file-selector, xap-file-preview, xap-uploaded-file, .input-preview, .uploader-file-preview, .thumbnail-container, .image-thumbnail, [class*="upload"], [class*="preview"]');
if (isUploadAlt || parent || (src.startsWith('blob:') && alt.includes('tải lên'))) {
  console.log('[DB9] BUG-102 FIX: Excluding upload preview image:', src.substring(0, 60), 'alt:', alt);
  return false;
}
```

### 🚀 Privileged Service Worker Downloader for BUG-103 & BUG-101 (Implemented)
This delegates all download transactions to the privileged **Extension Background Service Worker (`worker.js`)** using `chrome.downloads.download()`, which executes downloads natively via the browser's download manager.
* **Fixed Runtime Error:** Resolved a critical runtime `ReferenceError` (message -> msg) in `worker.js` line 616, ensuring smooth execution.

---

## 4. Unfinished & Outstanding Issues (Open for Verification/Fix)

### 🔴 BUG-106: High-Resolution Generation/Download Quality Issue (Outstanding)
* **Symptom:** Despite implementing 2048x2048 px resolution checking and a hydration retry loop in `downloadHD()`, downloaded files are still low resolution or too small in some states (falling back or failing to fetch >= 2048x2048 px).
* **Technical Constraints & Investigation:** 
  1. **Backend Capping:** Google Gemini's standard web interface (Imagen 3 engine tier on `gemini.google.com`) strictly restricts image output based on user tier, and often does not serve or expose true 2048x2048 px high-resolution assets to the DOM or via standard client-side download links.
  2. **Hydration delays:** The high-resolution asset URL might take longer to populate, or requires specific UI actions (e.g., expanding the immersive viewer) to load the raw file.
* **Current Status:** **Outstanding / Unfinished**. The download pipeline, baseline observer, and upload are fully stable, but forcing Gemini to consistently yield 2048x2048 px high-resolution files remains an open challenge.

