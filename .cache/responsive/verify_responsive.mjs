// Responsive acceptance, with the two negative controls it needs to be worth
// anything.
//
// The page is a three-column `height:100vh` instrument panel with an internal
// scroller in the right column. Both of those collapse under pressure, and
// neither complained when they did:
//
//   width  -- 300px + 320px + gaps + padding is 668px of fixed track, so the
//             middle column (the scatter plot) was 74px at 768 and 65px below
//             720. The grid's intrinsic width also put a 747px floor on the
//             document: on a 390px phone the right column sat at x=427,
//             entirely off-screen, so the "why this word" readout was
//             unreachable rather than merely small.
//
//   height -- the right column's scroller was `min-height:0`, making it the
//             only shrinkable item. Measured band height: 405px at 1100, 205px
//             at 900, 105px at 800, 25px at 720, 0px at 640. A 13" laptop's
//             usable browser height is around 800.
//
// The negative controls matter because "no horizontal scrollbar" and "band is
// taller than 0" are exactly the kind of conditions that pass by accident.
import { launch, CDP, Page } from '../browser_verify/cdp_client.mjs';
import { mkdirSync } from 'node:fs';

// Point at the clean-room server to check the DELIVERED tarball. The working
// tree being green says nothing about the artefact the user downloads.
const URL = process.env.RESP_URL || 'http://localhost:8917/latent/index.html';
const SHOTS = process.env.RESP_SHOTS || '/Users/zhourui/code/steer3d/.cache/responsive_shots';
mkdirSync(SHOTS, { recursive: true });
const sleep = ms => new Promise(r => setTimeout(r, ms));

const fails = [];
const chk = (c, label, extra = '') => {
  console.log((c ? '  ok   ' : '  FAIL ') + label + (extra ? '   ' + extra : ''));
  if (!c) fails.push(label);
};

const WIDTHS = [1600, 1280, 1100, 1024, 900, 768, 720, 560, 430, 390];
const HEIGHTS = [1100, 1000, 900, 800, 720, 640];

const { proc, version } = await launch({
  port: Number(process.env.RESP_PORT || 9363),
  userDataDir: '/Users/zhourui/code/steer3d/.cache/responsive/profile',
  url: 'about:blank' });
const cdp = await CDP.connect(
  `ws://127.0.0.1:9363/devtools/browser/${version.webSocketDebuggerUrl.split('/').pop()}`);
const page = await Page.create(cdp);
await page.send('Network.enable');
await page.send('Network.setCacheDisabled', { cacheDisabled: true });
const exceptions = [];
cdp.on(m => { if (m.method === 'Runtime.exceptionThrown')
  exceptions.push(m.params.exceptionDetails?.exception?.description
                  || m.params.exceptionDetails?.text || 'unknown'); });

// Everything the checks need, in one round trip. DOMRects are copied out as
// plain numbers: a raw DOMRect has no own enumerable properties, so CDP
// serialises it to {} and every field reads NaN -- which reads as a broken
// page rather than a broken probe.
const PROBE = `(()=>{
  const vw = window.innerWidth, vh = window.innerHeight;
  const doc = document.documentElement;
  const B = s => { const e=document.querySelector(s); if(!e) return null;
    const r=e.getBoundingClientRect();
    return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height),
            right:Math.round(r.right),bottom:Math.round(r.bottom)}; };
  const b=document.querySelector('[data-dvblock]');
  const sc=b?b.closest('div[style*="overflow-y"]'):null;
  let ctl=null, ste=null, band=null, rows=0;
  if(b && sc){
    band=B('[data-dvblock]').h? (()=>{const r=sc.getBoundingClientRect();
        return {top:Math.round(r.top),bot:Math.round(r.bottom),h:Math.round(r.height)};})() : null;
    const rr=[...b.querySelectorAll('div')].filter(d=>d.querySelectorAll(':scope > span').length>=4);
    rows=rr.length;
    if(rr[0]){const q=rr[0].getBoundingClientRect(); ctl={top:Math.round(q.top),bot:Math.round(q.bottom)};}
    if(rr[Math.floor(rr.length/2)]){const q=rr[Math.floor(rr.length/2)].getBoundingClientRect();
      ste={top:Math.round(q.top),bot:Math.round(q.bottom)};}
  }
  const cols=[...document.querySelectorAll('.wrap > .col')].map(c=>{
    const r=c.getBoundingClientRect();
    return {x:Math.round(r.x),w:Math.round(r.width),right:Math.round(r.right)};});
  return { vw, vh, docW: doc.scrollWidth, docH: doc.scrollHeight,
           hScroll: doc.scrollWidth > vw + 1,
           mid:B('.wrap > .col:nth-child(2)'), canvas:B('#cv'),
           right:B('.wrap > .col:nth-child(3)'), cols, band, ctl, ste, rows,
           stacked: cols.length>1 && cols[1].x === cols[0].x };
})()`;

async function open(w, h) {
  await page.send('Emulation.setDeviceMetricsOverride',
    { width: w, height: h, deviceScaleFactor: 1, mobile: w < 700 });
  await page.send('Page.navigate', { url: `${URL}?orient=reset&m=qwen3-1p7b` });
  await page.waitForEvent('Page.loadEventFired', 40000);
  await sleep(4200);
  if (await page.eval(`(()=>{const o=document.getElementById('orientation');
      return !!(o&&getComputedStyle(o).display!=='none');})()`)) {
    await page.click('#orientClose'); await sleep(700);
  }
  await page.click('#tabDelta'); await sleep(1700);
  return page.eval(PROBE);
}

console.log('===== 宽度：横向可达性 =====');
for (const w of WIDTHS) {
  const r = await open(w, 900);
  chk(!r.hScroll, `w=${w} 没有横向滚动`, `docW=${r.docW}`);
  chk(r.canvas && r.canvas.w >= 300, `w=${w} 主画布宽度可用`,
      r.canvas ? `${r.canvas.w}px` : 'null');
  chk(r.right && r.right.x + 1 < r.vw,
      `w=${w} 右栏在视口内`, r.right ? `x=${r.right.x} w=${r.right.w}` : 'null');
  if (w <= 1024) {
    chk(r.stacked, `w=${w} 切换成单列堆叠`,
        r.cols.map(c => `${c.x}/${c.w}`).join(' '));
  }
}

console.log('\n===== 高度：读出面板的滚动窗口 =====');
for (const h of HEIGHTS) {
  const r = await open(1600, h);
  chk(r.band && r.band.h >= 290, `h=${h} 滚动窗口有地板`,
      r.band ? `${r.band.h}px` : 'null');
  chk(r.rows > 0, `h=${h} 读出块渲染`, `${r.rows} 行`);
  const inBand = q => q && r.band && q.bot <= r.band.bot + 1;
  chk(inBand(r.ctl), `h=${h} 对照臂第一候选同屏可见`,
      r.ctl ? `@${r.ctl.bot} band=${r.band && r.band.bot}` : 'null');
  chk(inBand(r.ste), `h=${h} 干预臂第一候选同屏可见`,
      r.ste ? `@${r.ste.bot} band=${r.band && r.band.bot}` : 'null');
}

for (const [w, h, tag] of [[390, 844, 'phone'], [768, 1024, 'tablet'],
                           [1280, 800, 'laptop'], [1600, 1000, 'desktop']]) {
  await open(w, h);
  await page.screenshot(`${SHOTS}/r_${tag}_${w}x${h}.png`, { fullPage: false });
  const b = await page.eval(`(()=>{const e=document.querySelector('[data-dvblock]');
    return e?(e.getBoundingClientRect().top|0):null;})()`);
  if (b != null) {
    await page.eval(`(()=>{document.querySelector('[data-dvblock]')
      .scrollIntoView({block:'center'});return 1;})()`);
    await sleep(600);
    await page.screenshot(`${SHOTS}/r_${tag}_readout.png`, { fullPage: false });
  }
}
chk(exceptions.length === 0, '全程无 JS 异常', exceptions.slice(0, 2).join(' | ').slice(0, 160));

console.log(`\n失败 ${fails.length} 条`);
fails.forEach(f => console.log('  - ' + f));
try { await page.close(); } catch {} try { proc.kill(); } catch {}
process.exit(fails.length ? 1 : 0);
