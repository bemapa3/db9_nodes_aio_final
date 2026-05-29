# 🔄 HOW TO RELOAD AND TEST THE EXTENSION (v0.4.7.7)

Follow these steps to deploy and test the latest Vietnamese normalization fix:

## 1. Deploy Files
Copy the updated files from the clean worktree (`j:\!!_BAOTAPCODE\DB9_PTS2GG_Clean\DB9_PTS2GG\extension`) to your actual active extension folder:
- `extension/manifest.json`
- `extension/background/worker.js`
- `extension/content/provider-gemini.js`
- `extension/content/content-script.js`
- `extension/popup/popup.html`
- `extension/popup/popup.js`

---

## 2. Reload Extension in Chrome
1. Open Google Chrome.
2. Navigate to **`chrome://extensions/`**.
3. Toggle **Developer mode** in the top-right corner if it is not already on.
4. Locate the card for **"DB9 Multi-Provider Auto"**.
5. Verify the version has changed to **`0.4.7.7`** (or click the reload arrow button 🔄).
6. Click **Inspect views: Service worker** to open the background inspector (useful for viewing debugger attachment logs).

---

## 3. Run the Test
1. Hard-refresh your Gemini tab (**Ctrl + Shift + R**).
2. Generate an image in Photoshop and click **Generate** to invoke the upload state machine.
3. The script will automatically trigger tools, look for the **"Tải tệp lên"** button, and attach the CDP debugger to inject the image file cleanly!
4. Check the console log (`F12`) on your Gemini tab for:
   ```
   [DB9-Gemini] chosen upload candidate text="Tải tệp lên" tagName=BUTTON
   [DB9-Gemini] requesting background CDP file injection on selected upload candidate
   [DB9-Gemini] upload confirmed via network monitor
   ```
