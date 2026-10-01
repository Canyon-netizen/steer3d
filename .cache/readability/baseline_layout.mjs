// 基线对照：把 index.html 换回 HEAD 版本量一遍布局，换回新版再量一遍，
// 回答"导读层有没有引入新的布局溢出"。只量几何，不看字符串。
import { launch, CDP, Page } from '../browser_verify/cdp_client.mjs';
import * as P from './probe_lib.mjs';

const ROOT = '/Users/zhourui/code/steer3d';
const SIZES = [{ w: 1600, h: 1000, port: 9381 }, { w: 1280, h: 800, port: 9382 }];
const sleep = ms => new Promise(r => setTimeout(r, ms));
const tag = process.argv[2] || 'x';

for (const S of SIZES) {
  const { proc, version } = await launch({
    port: S.port, userDataDir: `${ROOT}/.cache/readability/profile_base_${S.port}`,
    windowSize: `${S.w},${S.h}`, url: 'about:blank',
  });
  const cdp = await CDP.connect(
    `ws://127.0.0.1:${S.port}/devtools/browser/${version.webSocketDebuggerUrl.split('/').pop()}`);
  const page = await Page.create(cdp);
  await page.send('Storage.clearDataForOrigin',
    { origin: 'http://localhost:8917', storageTypes: 'local_storage' });
  await page.nav('http://localhost:8917/latent/index.html?orient=off');
  for (let i = 0; i < 160; i++) {
    const st = await page.eval(`(()=>({l:getComputedStyle(document.getElementById('loading')).display,
      a:getComputedStyle(document.getElementById('app')).visibility,
      r:document.querySelectorAll('#tblTop tr').length}))()`);
    if (st.l === 'none' && st.a === 'visible' && st.r > 0) break;
    await sleep(250);
  }
  await sleep(600);
  const po = await page.eval(P.pageOverflow);
  const lo = await page.eval(P.layoutOverflow);
  const bleed = await page.eval(P.horizontalBleed);
  const worst = lo.slice().sort((a, b) => (b.vOver - a.vOver) || (b.hOverVsParent - a.hOverVsParent))[0];
  console.log(JSON.stringify({
    tag, size: S.w + 'x' + S.h,
    pageVOver: po.vOver, pageHOver: po.hOver, bodyVOver: po.bodyVOver,
    panelMaxVOver: Math.max(0, ...lo.map(x => x.vOver)),
    panelMaxHOver: Math.max(0, ...lo.map(x => Math.max(x.hOverVsParent, x.hOverSelf))),
    wrap: lo.find(x => x.sel === '.wrap'),
    worst,
    bleed: bleed.length,
  }));
  page.close(); cdp.close(); proc.kill('SIGKILL');
}
