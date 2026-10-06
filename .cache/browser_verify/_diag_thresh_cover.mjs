// 诊断：T6 的 covered=true 到底是页面真被盖，还是判据的假红。
// 关键分界：elementFromPoint 对**视口外**的点返回 null。
// 我上一版写成 `covered = pt ? ... : true`，把 null 当成「被盖」——
// 那是把「测不到」记成「不合格」，和本项目反复修的第四态是同一族错误。
import { launch, Page, CDP } from './cdp_client.mjs';
const URL = process.env.LAT_URL || 'http://127.0.0.1:22234/latent/index.html';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const { proc, version } = await launch({ port: 9491,
  userDataDir: '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_diagcov_' + process.pid,
  windowSize: '1600,1050', url: 'about:blank' });
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  await sleep(3500);
  await page.eval(`document.getElementById('tabThresh').click()`);
  await sleep(2500);
  const before = await page.eval(`JSON.stringify((() => {
    const el = document.querySelector('[data-threshgen]');
    if(!el) return {present:false};
    const r = el.getBoundingClientRect();
    return { present:true, rect:{x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)},
             vh: window.innerHeight, vw: window.innerWidth,
             inViewport: r.top >= 0 && r.bottom <= window.innerHeight };
  })())`);
  console.log('滚动前:', before);
  // 把它滚进视口再测
  const after = await page.eval(`JSON.stringify((() => {
    const el = document.querySelector('[data-threshgen]');
    el.scrollIntoView({block:'center'});
    const r = el.getBoundingClientRect();
    const px = r.left + r.width/2, py = r.top + Math.min(12, r.height/2);
    const pt = document.elementFromPoint(px, py);
    return { rect:{x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)},
             probePoint:{x:Math.round(px),y:Math.round(py)},
             elementFromPoint: pt ? (pt.tagName + (pt.className? '.'+String(pt.className).slice(0,40):'')) : null,
             ptIsInside: pt ? (el.contains(pt) || pt===el || pt.contains(el)) : null,
             ptText: pt ? (pt.textContent||'').trim().slice(0,50) : null };
  })())`);
  console.log('滚入视口后:', JSON.stringify(after, null, 2));
  await page.screenshot('/Users/zhourui/code/steer3d/.cache/browser_verify/shots/thresh_gen.png');
} finally { cdp.close(); proc.kill('SIGKILL'); }
