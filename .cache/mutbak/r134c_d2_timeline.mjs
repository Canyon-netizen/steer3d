// r134c_d2_timeline.mjs —— D2「看全部」的时间线取证
//
// ⚠⚠⚴⚠ 事实：`R134_ARM=all` 把 `[data-pathbtn="all"]` **确实拆掉了**
//   （落地核验回读 `before:true → after:false`），**D2 仍然绿**。
//   ⇒ `rAll === q0.k+1 && rAll > rFork` **不需要点那个按钮也成立**。
//
// ⚠ 两种互斥可能，本台用**时间线**分开：
//   ① 页面自己就已是 k+1 行 ⇒ `rFork` 本来就等于 `q0.k+1`，
//      但那样 `rAll > rFork` 应当**为假** ⇒ D2 应该红 ⇒ 与实测矛盾
//   ② **D1 的点击引发了异步展开**，而 `rFork` 量得太早
//      ⇒ 行数在 `rFork` 之后、`rAll` 之前自己涨上去
//      ⇒ ⚠⚠⚴ D2 的「变多了」可能来自**时间差**，不是来自「看全部」
//
// ⚠ 本台只读页面状态，不下判决；结论由下面的数字决定。
// ⚠ 页面侧不写正则，一律 split/join 与 querySelector。

import { launch, Page, CDP } from '/Users/zhourui/code/steer3d/.cache/browser_verify/cdp_client.mjs';
import { readFileSync } from 'node:fs';

const URL = process.env.LAT_URL || 'http://127.0.0.1:9006/latent/index.html';
const ART = '/Users/zhourui/code/steer3d/frontend/public/latent/data/path_readout.json';
const sleep = ms => new Promise(r => setTimeout(r, ms));

const prod = JSON.parse(readFileSync(ART, 'utf8'));

const { proc, version } = await launch({
  port: 9498, userDataDir: '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_r134c_' + process.pid,
  windowSize: '1600,1050', url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);

const nRows = () => page.eval(`document.querySelectorAll('[data-patht]').length`);

try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  await sleep(3500);
  await page.eval(`(() => {
    const ov = document.getElementById('orientation'); const b = document.getElementById('orientClose');
    if (ov && !ov.classList.contains('hide') && b) b.click();
    document.querySelector('#tabPath').click();
  })()`);
  await sleep(2500);
  const state = await page.eval(`document.querySelector('[data-pathblock]') ? document.querySelector('[data-pathblock]').getAttribute('data-pathstate') : 'ABSENT'`);
  const pid = await page.eval(`(()=>{const b=document.querySelector('[data-pathblock]'); return b?b.getAttribute('data-pathpid'):null;})()`);
  const k = Number(await page.eval(`(()=>{const b=document.querySelector('[data-pathblock]'); return b?b.getAttribute('data-pathk'):-1;})()`));
  const q0 = prod.problems[pid];
  console.log(`页面 state=${state} pid=${pid} 屏上 k=${k} 产物 k=${q0.k} ⇒ 产物期望行数 k+1=${q0.k + 1}`);

  console.log('\n=== 时间线（每步都打当前 [data-patht] 行数）===');
  console.log(`  初始（切屏后）           : ${await nRows()}`);

  const btnExists = await page.eval(`!!document.querySelector('[data-pathbtn="all"]')`);
  console.log(`  [data-pathbtn="all"] 存在: ${btnExists}`);
  const forkExists = await page.eval(`!!document.querySelector('[data-pathfork="1"]')`);
  console.log(`  [data-pathfork="1"] 存在: ${forkExists}`);

  // 复刻 verify_path.mjs:179 的 D1 点击
  await page.eval(`(()=>{const r=document.querySelector('[data-pathfork="1"]'); if(r) r.click(); return true;})()`);
  await sleep(600);
  const afterD1 = await nRows();
  console.log(`  D1 点击分叉行 + 600ms    : ${afterD1}`);

  // ⚠ 在**不点「看全部」**的前提下，继续观察行数会不会自己涨
  for (const w of [600, 1200, 2400, 4000]) {
    await sleep(w === 600 ? 600 : w - 600);
    console.log(`  再等 ${String(w).padStart(4)}ms（**仍未点「看全部」**）: ${await nRows()}`);
  }
  const beforeBtn = await nRows();

  // 现在才点「看全部」
  await page.eval(`(()=>{const b=document.querySelector('[data-pathbtn="all"]'); if(b) b.click(); return true;})()`);
  await sleep(600);
  const afterBtn = await nRows();
  console.log(`  点「看全部」+ 600ms      : ${afterBtn}`);

  console.log('\n=== 对账 ===');
  console.log(`  rFork（verify_path 量到的「点之前」）      ≈ ${afterD1}`);
  console.log(`  rAll （verify_path 量到的「点之后」）      ≈ ${afterBtn}`);
  console.log(`  产物期望 q0.k + 1                          = ${q0.k + 1}`);
  console.log(`\n  ⚠ D2 的判据是 rAll === ${q0.k + 1} && rAll > rFork`);
  console.log(`  ⚠⚠⚴ **在「看全部」之前行数就已经是 ${beforeBtn}**`);
  console.log(`     ⇒ ${beforeBtn === q0.k + 1 ? '⚠⚠⚴⚠ 行数在点按钮之前就已到位 ⇒「变多」不是按钮的功劳' : '行数尚未到位'}`);
  console.log(`  ⚠ 点按钮带来的增量 = ${afterBtn - beforeBtn}（0 表示点它没用）`);
} catch (e) {
  console.log('[装置错]', String(e && e.message ? e.message : e));
} finally {
  try { await cdp.send('Browser.close'); } catch {}
  try { proc.kill(); } catch {}
}