import { launch, CDP, Page } from '../browser_verify/cdp_client.mjs';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const P = 9413;
const { proc, version } = await launch({ port: P,
  userDataDir: '/Users/zhourui/code/steer3d/.cache/cottext/profile_meas', url: 'about:blank' });
const cdp = await CDP.connect(`ws://127.0.0.1:${P}/devtools/browser/${version.webSocketDebuggerUrl.split('/').pop()}`);
const page = await Page.create(cdp);
await page.send('Network.enable');
await page.send('Network.setCacheDisabled', { cacheDisabled: true });
await page.send('Emulation.setDeviceMetricsOverride',
  { width: 1600, height: 1100, deviceScaleFactor: 1, mobile: false });
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

const m = await page.eval(`(() => {
  const blk = document.querySelector('[data-cottext]');
  const tbl = document.querySelector('#tblTop');
  // the scroll box that holds the table
  const box = tbl.parentElement;
  const cs = getComputedStyle(box);
  const bb = blk.getBoundingClientRect();
  const bx = box.getBoundingClientRect();
  // which of the block's key parts are actually inside the visible box?
  const parts = [...blk.querySelectorAll('[data-cotarm],[data-cotpre]')].map(e => {
    const r = e.getBoundingClientRect();
    return { key: e.dataset.cotarm || 'pre',
             top: Math.round(r.top), bottom: Math.round(r.bottom),
             visibleInBox: r.top < bx.bottom && r.bottom > bx.top };
  });
  // horizontal overflow of the block
  return {
    box: { tag: box.tagName, clientH: box.clientHeight, scrollH: box.scrollHeight,
           overflowY: cs.overflowY, rectTop: Math.round(bx.top), rectBottom: Math.round(bx.bottom) },
    block: { h: Math.round(bb.height), scrollW: blk.scrollWidth, clientW: blk.clientWidth,
             rectTop: Math.round(bb.top), rectBottom: Math.round(bb.bottom) },
    tableH: Math.round(tbl.getBoundingClientRect().height),
    parts,
    docScrollH: document.documentElement.scrollHeight,
    winH: innerHeight,
  };
})()`);
console.log(JSON.stringify(m, null, 1));
await cdp.close(); proc.kill('SIGKILL');
