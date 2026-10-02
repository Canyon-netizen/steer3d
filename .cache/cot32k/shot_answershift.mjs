import { launch, CDP, Page } from '../browser_verify/cdp_client.mjs';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const P = 9427;
const { proc, version } = await launch({ port: P,
  userDataDir: '/Users/zhourui/code/steer3d/.cache/cottext/profile_shot2', url: 'about:blank' });
const cdp = await CDP.connect(`ws://127.0.0.1:${P}/devtools/browser/${version.webSocketDebuggerUrl.split('/').pop()}`);
const page = await Page.create(cdp);
await page.send('Network.enable');
await page.send('Network.setCacheDisabled', { cacheDisabled: true });
await page.send('Emulation.setDeviceMetricsOverride', { width: 1600, height: 1100, deviceScaleFactor: 2, mobile: false });
const reg = await (await fetch('http://127.0.0.1:8917/latent/models.json')).json();
const big = reg.models.find(m => m.d_model === 2048);
await page.send('Page.navigate', { url: `http://127.0.0.1:8917/latent/index.html?orient=reset&m=${big.id}` });
await page.waitForEvent('Page.loadEventFired', 40000);
await sleep(7000);
if (await page.eval(`(()=>{const o=document.getElementById('orientation');
  return !!(o&&getComputedStyle(o).display!=='none');})()`)) { await page.click('#orientClose'); await sleep(800); }
await page.click('#tabDelta'); await sleep(3000);

// The answer-shift block is identified by its own heading text, not by an id:
// a hook would be one more thing the render could forget to emit.
const found = await page.eval(`(() => {
  const walk = document.createTreeWalker(document.getElementById('tblTop'), NodeFilter.SHOW_ELEMENT);
  let n, hit = null;
  while ((n = walk.nextNode())) {
    if (n.children.length === 0 && n.textContent.includes('换个问法，答案其实会变')) { hit = n; break; }
  }
  if (!hit) return null;
  hit.scrollIntoView({block:'start'});
  let box = hit; while (box && getComputedStyle(box).overflowY !== 'auto') box = box.parentElement;
  const b = box.getBoundingClientRect();
  return { x: b.left, y: b.top - 6, w: b.width, h: Math.min(box.clientHeight + 12, 320) };
})()`);
if (!found) { console.log('找不到「换个问法」块'); process.exit(1); }
await sleep(500);
const p = await page.screenshot('.cache/cottext/shots/answer_shift.png',
  { clip: { x: found.x - 6, y: found.y, width: found.w + 12, height: found.h, scale: 2 } });
console.log('answer_shift shot:', p);
await cdp.close(); proc.kill('SIGKILL');
