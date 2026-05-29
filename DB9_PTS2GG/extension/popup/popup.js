// DB9 Multi-Provider — Extension Popup (v0.4.7.7)
// Presets/negatives are now owned by the UXP plugin. This popup is just a
// bridge-status indicator + a quick test-job sender.

const dot = document.getElementById('dot');
const statusEl = document.getElementById('status');
const log = document.getElementById('log');

chrome.runtime.sendMessage({ type: 'ping-bridge' }, (resp) => {
  if (resp && resp.connected) {
    dot.classList.add('on');
    const provs = (resp.providers || []).join(', ') || '(no provider tabs open)';
    statusEl.textContent = 'Bridge connected ✓ · ' + provs;
  } else {
    statusEl.textContent = 'Bridge offline — start server!';
  }
});

document.getElementById('testBtn').onclick = async () => {
  log.textContent = 'Generating test image 512x512...';
  const canvas = document.createElement('canvas');
  canvas.width = 512; canvas.height = 512;
  const ctx = canvas.getContext('2d');
  const grad = ctx.createLinearGradient(0, 0, 512, 512);
  grad.addColorStop(0, '#f59e0b'); grad.addColorStop(1, '#7c3aed');
  ctx.fillStyle = grad; ctx.fillRect(0, 0, 512, 512);
  ctx.fillStyle = 'white'; ctx.font = 'bold 80px sans-serif'; ctx.textAlign = 'center';
  ctx.fillText('DB9', 256, 230);
  ctx.font = '30px sans-serif'; ctx.fillText('test image', 256, 290);
  const base64 = canvas.toDataURL('image/png').split(',')[1];

  log.textContent = 'Sending job to bridge...';
  try {
    const r = await fetch('http://127.0.0.1:8765/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        imageBase64: base64, mime: 'image/png',
        prompt: 'turn this into a realistic photo of a cat wearing a tiny hat',
        mode: 'new',
        provider: 'gemini'
      })
    });
    const j = await r.json();
    log.textContent = 'Job: ' + (j.jobId || JSON.stringify(j)).slice(0, 20) + '\nCheck the Gemini tab';
  } catch (e) { log.textContent = 'Error: ' + e.message; }
};
