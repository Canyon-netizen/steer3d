// A full-page screenshot is 1600xN and the CoT block sits in a narrow right
// column; at that scale the prose is a grey smear and "it looks fine" is not a
// judgement anyone can make. This clips to the block's own bounding box so the
// actual sentences are legible at native resolution.
import { launch, CDP, Page } from '../browser_verify/cdp_client.mjs';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const P = 9423;
const { proc, version } = await launch({ port: P,
  userDataDir: '/Users/zhourui/code/steer3d/.cache/cottext/profile_shot', url: 'about:blank' });
const cdp = await CDP.connect(`ws://127.0.0.1:${P}/devtools/browser/${version.webSocketDebuggerUrl.split('/').pop()}`);
const page = await Page.create(cdp);
await page.send('Network.enable');
await page.send('Network.setCacheDisabled', { cacheDisabled: true });
await page.send('Emulation.setDeviceMetricsOverride',
  { width: 1600, height: 1100, deviceScaleFactor: 2, mobile: false });

const reg = await (await fetch('http://127.0.0.1:8917/latent/models.json')).json();
const big = reg.models.find(m => m.d_model === 2048);
await page.send('Page.navigate',
  { url: `http://127.0.0.1:8917/latent/index.html?orient=reset&m=${big.id}` });
await page.waitForEvent('Page.loadEventFired', 40000);
await sleep(7000);
if (await page.eval(`(()=>{const o=document.getElementById('orientation');
  return !!(o&&getComputedStyle(o).display!=='none');})()`)) {
  await page.click('#orientClose'); await sleep(800);
}
await page.click('#tabDelta'); await sleep(3000);

// Two shots, because the defect this change was made to fix is not visible in
// one: what the reader sees on ARRIVAL, and what they see after clicking the
// jump link. A single full-page capture shows the block fine and proves
// nothing about whether it can be reached.
const r1 = await page.rect('[data-jump="cottext"]');
if (!r1) { console.log('跳转入口不存在'); process.exit(1); }
console.log('跳转按钮 bbox', JSON.stringify(r1), 'inViewport=',
  r1.y >= 0 && r1.y + r1.h <= 1100);
await page.screenshot('.cache/cottext/shots/arrival.png', { clip: { x: r1.x - 40, y: 360, width: 420, height: 330, scale: 2 } });
console.log('arrival shot ok');

await page.click('[data-jump="cottext"]');
await sleep(800);
const abs = await page.eval(`(() => { const e=document.querySelector('[data-cotpre]');
  const b=e.getBoundingClientRect();
  let box=e; while(box && getComputedStyle(box).overflowY!=='auto') box=box.parentElement;
  const bx=box.getBoundingClientRect();
  return {x: bx.left, y: bx.top - 10, w: bx.width, h: Math.min(box.clientHeight + 20, 320)}; })()`);
const path = await page.screenshot('.cache/cottext/shots/after_jump.png', {
  clip: { x: abs.x - 8, y: abs.y, width: abs.w + 16, height: abs.h, scale: 2 },
});
console.log('after_jump shot:', path);
await cdp.close(); proc.kill('SIGKILL');
