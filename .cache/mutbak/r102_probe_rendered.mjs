// r102_probe_rendered.mjs —— 修订 102 的 G6 补证
//
// 为什么需要它（这是本轮最重要的一条）：
//   verify_subspace.mjs:389 是 `const caveat = H.bound_caveat || ''`
//   ⇒ **P1–P8 读的是产物自己的字段，一行页面都没读**
//   而 :188 的页面检查 `includes("|cos| < 0.5")` 没有右锚点，
//   "0.50" 也命中 ⇒ 它对「改了没改」没有分辨力。
//   ⇒ 51/51 通过**不能**当作「JSX 那三处已被实点证明」。
//
// 本探针只做一件事：从**真实渲染后**的页面上读 SubspacePanel 的 innerText，
// 逐处列出 `|cos| < ` 后面那个数，并给出两种写法的计数。
//
// ⚠ 自证：拿不到面板 / 面板不是 ready / 一种写法都数不到 ⇒ exit 2，
//   绝不把「0 处」报成「页面上没有」。

import { launch, Page, CDP } from '/Users/zhourui/code/steer3d/.cache/browser_verify/cdp_client.mjs';

const URL = process.env.BV_URL || 'http://127.0.0.1:9005/';
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_r102_' + process.pid;

const die = (m) => { console.log('[自证失败] ' + m); process.exit(2); };

const { proc, version } = await launch({
  port: 9487, userDataDir: PROFILE, windowSize: '1700,1300', url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  await new Promise(r => setTimeout(r, 3500));

  const raw = await page.eval(`(() => {
    const el = document.querySelector('[data-subspace]');
    if (!el) return JSON.stringify({ err: 'no-panel' });
    const rows = [...document.querySelectorAll('[data-threshold-row]')].map(r => ({
      key: r.getAttribute('data-threshold-row'),
      cells: [...r.querySelectorAll('span')].map(s => (s.innerText || '').trim()),
    }));
    return JSON.stringify({
      state: el.getAttribute('data-subspace'),
      text: (el.innerText || ''),
      nRows: rows.length,
      rows,
    });
  })()`);
  const P = JSON.parse(raw);

  if (P.err) die('页面上找不到 [data-subspace]：' + P.err);
  if (P.state !== 'ready') die(`面板状态是 ${P.state}，不是 ready ⇒ 没读到数据，不算数`);
  if (!P.text || P.text.length < 500) die('面板文本过短（' + P.text.length + ' 字符），像是没渲染');

  const text = P.text;

  // ---- A: 散文里的门槛 ----
  const prose = [...text.matchAll(/\|cos\|\s*<\s*([0-9.]+)/g)].map(m => m[1]);
  // ---- B: 表格行 —— 这里必须按 DOM 的格子取，不能按扁平文本 ----
  const cells = [];
  for (const r of P.rows) for (const c of r.cells) cells.push(c);
  const cellThresholds = P.rows.map(r => r.cells[0]).filter(t => /^\|cos\|\s*</.test(t || ''));

  console.log('面板状态        : ' + P.state + '（文本 ' + text.length + ' 字符）');
  console.log('阈值行数        : ' + P.nRows + '（DOM 实取，非文本推断）');
  console.log('');
  console.log('[B] 表格每行第 1 格（DOM 逐行实读）：');
  for (let i = 0; i < P.rows.length; i++) {
    console.log('    key=' + P.rows[i].key + '  cells=' + JSON.stringify(P.rows[i].cells));
  }
  console.log('');

  const bare = prose.filter(v => v === '0.5');
  const two = prose.filter(v => v === '0.50');
  const absorbed = [...text.matchAll(/已超过\s*([0-9.]+)\s*门槛/g)].map(m => m[1]);

  console.log('[A] 文本流里 `|cos| < ` 逐处：', JSON.stringify(prose));
  console.log('    其中 0.5 =', bare.length, '处；0.50 =', two.length, '处');
  console.log('[C] 「已超过 X 门槛」：', JSON.stringify(absorbed));

  // ---- 自证：两种写法各至少出现一次，否则这台探针量不到东西 ----
  if (two.length === 0) die('页面上一个 `0.50` 都没有 ⇒ 这台探针量不到修复后的形态');
  if (absorbed.length === 0) die('找不到「已超过 X 门槛」⇒ 面板没渲染全');

  const allSame = bare.length === 0 && absorbed.every(v => v === '0.50');
  console.log('');
  if (allSame) {
    console.log('⇒ 页面上同一个门槛的**每一种写法**都是 0.50，不再有 0.5 ✓');
  } else {
    console.log('⇒ ⚠ 仍有写法不一致：' + JSON.stringify({ bare, absorbed }));
    process.exitCode = 1;
  }
} catch (e) {
  die('装置错：' + String(e && e.message ? e.message : e));
} finally {
  try { await cdp.send('Browser.close'); } catch {}
  try { proc.kill(); } catch {}
}
