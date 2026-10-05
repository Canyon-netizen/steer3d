// ⚠ 第一版用固定 sleep(9000) 就去读 —— 那一轮面板还在 loading，
// 于是读出「NULDIST-ABSENT」，我差点当成「面板没渲染这个块」。
// ⇒ 装置要**等条件**（等 `[data-rc=ok]` 出现），不是等时长。
// 与「抓 DOM 抓早了」同源，但方向相反：那次是判据抓早，这次是诊断抓早。
import { launch, CDP, Page } from './cdp_client.mjs';
import { mkdirSync } from 'node:fs';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_dump_rc';
mkdirSync(PROFILE, { recursive: true });
const { proc, version } = await launch({ port: 9453, userDataDir: PROFILE, windowSize: '1600,1000', url: 'about:blank' });
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
await page.send('Page.navigate', { url: process.env.T3D_URL || 'http://127.0.0.1:22210/' });
await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});

let ready = false;
for (let i = 0; i < 50; i++) {
  ready = await page.eval(`!!document.querySelector('[data-rc="ok"]')`);
  if (ready) break;
  await sleep(500);
}
console.log('等 [data-rc=ok]：', ready ? `出现（第 ${'~' + ''}次轮询内）` : '25s 内没出现');
const out = await page.eval(`(() => {
  const rc = document.querySelector('[data-rc]');
  const nd = document.querySelector('[data-rc="nulldist"]');
  return JSON.stringify({
    rcAttr: rc ? rc.getAttribute('data-rc') : 'ABSENT',
    nulldist: nd ? nd.innerText : 'ABSENT',
    allMarks: [...document.querySelectorAll('[data-rc]')].map(n => n.getAttribute('data-rc')),
    occ: (document.querySelector('[data-rc="occurrence"]') || {}).innerText || 'ABSENT',
    occCx: (document.querySelector('[data-rc="occurrence-counterexample"]') || {}).innerText || 'ABSENT',
  });
})()`);
const d = JSON.parse(out);
console.log('面板 data-rc =', d.rcAttr);
console.log('面板里的 data-rc 块 =', JSON.stringify(d.allMarks));
console.log('--- [data-rc=nulldist] innerText ---');
console.log(d.nulldist);
console.log('--- [data-rc=occurrence] innerText ---');
console.log(d.occ);
console.log('--- [data-rc=occurrence-counterexample] innerText ---');
console.log(d.occCx);
proc.kill(); process.exit(0);
