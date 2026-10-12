// r116_n1_selftest.mjs —— 修订 116：把 N1 的功效验证从**逻辑级**升到**活 DOM 级**
//
// 起因：修订 114 只做了逻辑级验证（谓词抽出来判构造字符串），
//   并明确写了「端到端变异本轮未做」。
// ⚠⚴ 但同一仓里已有现成的正确做法：`verify_hinge_panel.mjs` 的 `selftest` 模式
//   （`:299-368`）**直接改页面实例上的 innerText**（不动源码、不动产物、不重建），
//   然后要求对应断言变红。
// ⇒ 也就是说「端到端扰动需要重新构建」这个前提**是错的**，本轮把它改掉。
//
// 口径（必须说清，否则会读成比它实际更强的结论）：
//   本脚本做的是**页面实例级**扰动 —— 改的是浏览器里那一棵已渲染的 DOM。
// ⚠⚠ 它**不是**组件代码级变异：真实缺陷是组件把错值渲染出来，
//   而这里是把已渲染的 DOM 改掉。React 重渲染会把改动冲掉。
//   ⇒ 能证明「N1 读的确实是**页面上读者看到的那句话**」，
//     **不能**证明「组件写错时 N1 一定红」—— 后者仍需改源码 + 重建。
//
// 三个对照（缺一不可）：
//   阳性：真实 DOM 上 N1 必须为绿（证明谓词对真页面成立）
//   阴性：在**同一元素**上把命名轴数改错 ⇒ N1 必须转红（证明它读的就是这句）
//   污染对照：改**别的**元素 ⇒ N1 必须**仍然绿**
//         （否则「任何改动都让它红」= 仪器只会喊叫，不是在测量）

import { launch, Page, CDP } from '/Users/zhourui/code/steer3d/.cache/browser_verify/cdp_client.mjs';
import { readFileSync } from 'node:fs';

const URL = process.env.BV_URL || 'http://127.0.0.1:9006/';
const VER = '/Users/zhourui/code/steer3d/.cache/browser_verify/verify_subspace.mjs';
const ART = '/Users/zhourui/code/steer3d/frontend/public/latent/data/readable_subspace.json';
const PORT = 9493;
const sleep = ms => new Promise(r => setTimeout(r, ms));

const die = (m) => { console.log('[闸门失败] ' + m); process.exit(2); };

// ---------- 从已提交的判据文件里抽 N1 的谓词原文（不复写）----------
const src = readFileSync(VER, 'utf8');
const pm = src.match(/hits\.length\s*>\s*0\s*&&\s*hits\.every\(v\s*=>\s*v\s*===\s*nAx\)/);
if (!pm) die('在 verify_subspace.mjs 里找不到 N1 的谓词原文 ⇒ 抽不到判据');
const hx = src.match(/matchAll\(\/命名轴只有\\s\*\(\\d\+\)\\s\*条\/g\)/);
if (!hx) die('找不到 N1 的 matchAll 正则原文');
console.log('[自证] N1 谓词原文：' + pm[0]);
console.log('[自证] N1 正则原文：/命名轴只有\\s*(\\d+)\\s*条/g');

const nAx = JSON.parse(readFileSync(ART, 'utf8')).headline.named_axes;
console.log('[自证] 产物 named_axes = ' + nAx);

const { proc, version } = await launch({
  port: PORT, userDataDir: '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_r116_' + process.pid,
  windowSize: '1700,1200', url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);

try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 60000).catch(() => {});
  await sleep(12000);

  // 读页面上真实的那句话（就是 verify_subspace.mjs 里 P.headline 读的那一个元素）
  const READ = `(() => {
    const e = document.querySelector('[data-headline-verdict]');
    return e ? (e.innerText || '').replace(/\\s+/g,' ').trim() : null;
  })()`;

  const judge = (t) => {
    const hits = t ? [...t.matchAll(/命名轴只有\s*(\d+)\s*条/g)].map(m => Number(m[1])) : [];
    return [hits.length > 0 && hits.every(v => v === nAx), hits];
  };

  const real = await page.eval(READ);
  if (!real || real.length < 40) die('页面上读不到 headline（' + JSON.stringify(real) + '）');
  const [okReal, hReal] = judge(real);
  console.log();
  console.log('=== 真实页面 ===');
  console.log('  读到 ' + JSON.stringify(hReal) + ' ⇒ ' + (okReal ? '绿 ✓' : '红 ✗ 应绿却红了'));
  if (!okReal) die('真实页面判红 ⇒ N1 今天有活缺陷，或谓词抽取错了');

  // ---------- 阴性对照：改**同一元素**上的命名轴数 ----------
  const WRONG = nAx === 6 ? 9 : 6;
  const mutated = await page.eval(`(() => {
    const e = document.querySelector('[data-headline-verdict]');
    if (!e) return null;
    const before = e.innerText;
    const after = before.replace(new RegExp('命名轴只有\\\\s*${nAx}\\\\s*条'),
                                 '命名轴只有 ${WRONG} 条');
    e.innerText = after;
    const now = (e.innerText || '').replace(/\\s+/g,' ').trim();
    const changed = now !== before.replace(/\\s+/g,' ').trim();
    return JSON.stringify({changed, now, orig: before.replace(/\\s+/g,' ').trim()});
  })()`);
  const M = JSON.parse(mutated);
  if (!M.changed) die('变异没生效（页面那句话改不动）⇒ 无法验证');
  const [okMut, hMut] = judge(M.now);
  console.log();
  console.log('=== 阴性对照：把同一句话里的命名轴数改错 ===');
  console.log('  原句 …' + M.orig.slice(Math.max(0, M.orig.indexOf('命名轴') - 10), M.orig.indexOf('命名轴') + 18) + '…');
  console.log('  改后 …' + M.now.slice(Math.max(0, M.now.indexOf('命名轴') - 10), M.now.indexOf('命名轴') + 18) + '…');
  console.log('  读到 ' + JSON.stringify(hMut) + ' ⇒ ' + (okMut ? '绿 ✗ 竟然绿了' : '红 ✓'));
  if (okMut) die('改了页面上那句话 N1 仍绿 ⇒ N1 读的不是读者看到的那句话');

  // ---------- 还原对照：⚠ 必须还原，否则下一步测的是「还在变异状态」 ----------
  // ⚠⚴ 第一版**忘了还原**，于是污染对照读到的仍是变异后的 [6] ⇒ 闸门红了。
  //   ⚠ 那道闸门拦的是**我的脚本**，不是 N1 —— 教训是：
  //   阴性对照之后的任何对照，都必须先证明**基线已恢复**。
  const restored = await page.eval(`(() => {
    const e = document.querySelector('[data-headline-verdict]');
    if (!e) return null;
    e.innerText = ${JSON.stringify(M.orig)};
    return (e.innerText || '').replace(/\\s+/g,' ').trim();
  })()`);
  if (!restored) die('还原失败 ⇒ 无法继续');
  const [okBack, hBack] = judge(restored);
  console.log();
  console.log('=== 还原对照：把那句话改回去 ===');
  console.log('  读到 ' + JSON.stringify(hBack) + ' ⇒ ' + (okBack ? '重新变绿 ✓' : '仍红 ✗ 变异不可逆'));
  if (!okBack) die('还原后仍红 ⇒ 刚才那次「转红」另有原因，不能归因到变异');

  // ---------- 污染对照：改**别的**元素，N1 必须仍然绿 ----------
  const polluted = await page.eval(`(() => {
    const els = [...document.querySelectorAll('[data-subspace] p, [data-subspace] h3, [data-subspace] b')];
    const e = els.find(x => !/命名轴/.test(x.innerText || '') && (x.innerText || '').length > 4);
    if (!e) return JSON.stringify({skipped: true});
    const before = e.innerText;
    e.innerText = before + '（污染对照：这句话不该影响 N1）';
    const h = document.querySelector('[data-headline-verdict]');
    return JSON.stringify({
      touched: (e.innerText || '').slice(0, 60),
      headline: h ? (h.innerText || '').replace(/\\s+/g,' ').trim() : null,
    });
  })()`);
  const Poll = JSON.parse(polluted);
  if (Poll.skipped) {
    console.log();
    console.log('=== 污染对照 ===\n  ⚠ 找不到可污染的其它元素 ⇒ 本条未判，不发布');
  } else {
    const [okPoll, hPoll] = judge(Poll.headline);
    console.log();
    console.log('=== 污染对照：改**别的**元素 ===');
    console.log('  动的是「' + Poll.touched.slice(0, 34) + '…」');
    console.log('  N1 读到 ' + JSON.stringify(hPoll) + ' ⇒ ' + (okPoll ? '仍绿 ✓' : '红 ✗ 它不该红'));
    if (!okPoll) die('改无关元素就让 N1 转红 ⇒ 仪器在喊叫而不是在测量');
  }

  console.log();
  console.log('[功效 ✓] 真实绿 + 同句改错转红 + 还原后重新变绿 + 改无关元素仍绿');
  console.log('⚠ 口径：这是**页面实例级**扰动，不是组件代码级变异。');
  console.log('⚠ 仍不能证明「组件写错时 N1 一定红」—— 那要改源码 + 重建。');
} catch (e) {
  die('装置错：' + String(e && e.message ? e.message : e));
} finally {
  try { await cdp.send('Browser.close'); } catch {}
  try { proc.kill(); } catch {}
}