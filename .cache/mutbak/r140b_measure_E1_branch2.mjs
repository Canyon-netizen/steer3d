// r140b_measure_E1_branch2.mjs —— 只读测量：E1 那个「缺数据时会喊缺」的**第二个空值分支**
//
// ⚠ r140a 只打到了 `!S.path` 那一个分支（拦掉 json）。但 `renderPathPanel`
//   有**两个**空值分支（`index.html:1581-1594`）：
//     ① `!S.path`                     → data-pathstate="no-data"
//     ② `!problems[pid]`（数据在、但这一题没记录）→ data-pathstate="no-problem"
//   ⚠⚠⚴ 只验①就下「缺数据时会喊缺」的结论，是**只验了一半**。
//   ⇒ 本台打②：数据**照常载入**，只把当前这道题从 `S.path.problems` 里摘掉
//   （**页面实例级扰动，不改任何文件**）。
//
// ⚠ 若②也出可见文案 ⇒ 「喊缺」是**两处都实现了**，不是只有一处。
// ⚠ 若②只出属性不出文案 ⇒ 得记成「两个分支的可见性不对称」。
//
// ⚠ 本台只读，不改判据、不改产品、不碰产物、不下判决。

import { launch, Page, CDP } from '/Users/zhourui/code/steer3d/.cache/browser_verify/cdp_client.mjs';

const URL = process.env.LAT_URL || 'http://127.0.0.1:9006/latent/index.html';
const sleep = ms => new Promise(r => setTimeout(r, ms));

const { proc, version } = await launch({
  port: 9522, userDataDir: '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_r140b_' + process.pid,
  windowSize: '1600,1050', url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);

try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 60000).catch(() => {});

  // ⚠ 身份自证：导航之后、任何测量之前，失败即 exit 2
  const here = await page.eval('location.href');
  if (!String(here).endsWith('/latent/index.html')) {
    console.log('[错误] 页面身份不对，here =', here, '⇒ exit 2');
    process.exit(2);
  }
  for (let i = 0; i < 80; i++) {
    const boot = await page.eval(`(()=>{const o=document.querySelector('#app');
      return !!o && getComputedStyle(o).visibility === 'visible';})()`);
    if (boot) break;
    await sleep(400);
  }

  // 扰动：只摘掉**当前选中那道题**在 S.path 里的记录，数据本身照常载入
  const cut = JSON.parse(await page.eval(`(() => {
    const pid = (S.pm && S.pm.pairs && S.pm.pairs[S.pi]) ? S.pm.pairs[S.pi].id : null;
    const had = !!(S.path && S.path.problems && S.path.problems[pid]);
    if (had) delete S.path.problems[pid];
    return JSON.stringify({ pid, hadBefore: had, hadAfter: !!(S.path.problems && S.path.problems[pid]) });
  })()`));
  console.log('=== 扰动事实 ===');
  for (const [k, v] of Object.entries(cut)) console.log(`  ${k.padEnd(11)}: ${v}`);
  // ⚠⚠⚴ 落地核验两半：**摘之前确实在**，且**摘之后确实不在**
  if (!(cut.hadBefore && !cut.hadAfter)) {
    console.log('[错误] 扰动未落地 ⇒ 仪器/装置问题，不发数');
    process.exit(2);
  }

  const out = JSON.parse(await page.eval(`(async () => {
    document.querySelector('#tabPath').click();
    await new Promise(r => setTimeout(r, 1200));
    const b = document.querySelector('[data-pathblock]');
    const txt = b ? (b.innerText || '') : '';
    return JSON.stringify({
      hasHandler: typeof window.renderPathPanel,
      pathState: b ? (b.getAttribute('data-pathstate') || '') : '(无)',
      saysNotLoaded: txt.indexOf('未载入') >= 0,
      saysMissingFile: txt.indexOf('path_readout.json') >= 0,
      saysNoProblem: txt.indexOf('没有题目') >= 0,
      saysHowMany: txt.indexOf('逐步路径只覆盖') >= 0,
      textLen: txt.length,
      textHead: txt.split('\\n').slice(0, 3).join(' / ').slice(0, 150),
    });
  })()`));

  console.log('\n=== 第二分支（数据在、这一题没记录）===');
  for (const [k, v] of Object.entries(out)) console.log(`  ${k.padEnd(14)}: ${v}`);
  console.log('\n⚗⚗ 与 r140a 的第一分支对照：'
    + '第一分支 pathState=' + '"no-data"（有可见文案）');
  console.log('⚗⚗ 本台 pathState=' + JSON.stringify(out.pathState)
    + '，可见文案长度 ' + out.textLen + ' 字');
} finally {
  try { await page.send('Page.close'); } catch {}
  try { cdp.close(); } catch {}
  try { proc.kill('SIGKILL'); } catch {}
}