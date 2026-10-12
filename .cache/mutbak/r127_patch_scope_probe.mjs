// r127_patch_scope_probe.mjs —— 修订 127 的**第二刀**（重写版）
//
// ⚠⚴⚴⚴ 上版（r127_scope_probe.mjs）测错了页面，这里记下错在哪：
//   它跑 `http://127.0.0.1:9006/`（Next.js 的 **React 页**），
//   却想验 `verify_patch.mjs` —— 后者用 `LAT_URL`，验的是
//   `http://127.0.0.1:9006/latent/index.html`（**静态产物页**）。
//   ⇒ 两个不同页面、同一个端口、靠路径区分。
//   ⇒ 上版「没有非 patch 面板命中」对 `verify_patch.mjs` **不构成证据**，已作废。
//
// ⚠⚴⚴⚴ 本版自己踩过的两个仪器 bug（一并记下，都是「仪器坏了却输出好消息」）：
//   ① `q.inVerdict` 拼错，正确是 `q.inGate` ⇒ 会把「同一批元素」**误报成不是**。
//   ② 模板字符串里写 `\\\\s` ⇒ 页面侧拿到 `/\\s+/` ⇒ 匹配**字面反斜杠**
//      ⇒ 空白根本没被折叠 ⇒ 各行换行差异会**假装成**区分度
//      ⇒ 会报出「每行可见文字都不同」的**假绿**。
//   ⇒ 修法：不写正则，改 `split/join`；并让页面侧**自报折叠前后长度**，
//     折叠无效则本台当场作废（不拿坏仪器的输出下结论）。
//
// 【要量的四件事】
//   2' 裸 `[data-verdict]` 是不是判决表**同一批元素**（数目相等可能是巧合）
//   3  **双层区分度**：产物 29 道门只有 8 种 name / 15 种三元组；
//      页面侧要分列量 —— 若首列印着机器门键，
//      「29 行文字不同」是**门键**给的区分度，不是人话给的。
//   4  `[word]`/`[num]` 只存在于**门键**（产物字段值里 0 处），
//      看它有没有变成读者可见文案。

import { launch, Page, CDP } from '/Users/zhourui/code/steer3d/.cache/browser_verify/cdp_client.mjs';
import { readFileSync } from 'node:fs';

const URL = process.env.LAT_URL || 'http://127.0.0.1:9006/latent/index.html';
const ART = '/Users/zhourui/code/steer3d/frontend/public/latent/data/path_patching.json';
const sleep = ms => new Promise(r => setTimeout(r, ms));

const art = JSON.parse(readFileSync(ART, 'utf8'));
const gates = art.gates || {};
const order = (art.gate_order || Object.keys(gates)).filter(k => gates[k]);

// 页面侧：折叠空白（不用正则，避开转义地狱）+ 自报折叠是否生效
const FOLD = `
  const fold = s => String(s||'').split(String.fromCharCode(10)).map(x=>x.split(String.fromCharCode(9)).join(' ').trim()).filter(Boolean).join(' ');
  let foldWorked = true;
  {
    const probe = String.fromCharCode(97,10,32,98);      // "a\\n b"
    if (fold(probe) !== 'a b') foldWorked = false;
    if (String.fromCharCode(97,9,32,98) && fold(String.fromCharCode(97,9,98)) !== 'a b') foldWorked = false;
  }
`;

const { proc, version } = await launch({
  port: 9498, userDataDir: '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_r127p_' + process.pid,
  windowSize: '1600,1050', url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  await sleep(3500);
  const l0 = JSON.parse(await page.eval(`JSON.stringify({
    href: location.href, bodyLen: (document.body.innerText||'').length })`));
  console.log(`[自证] 页面 = ${l0.href}  bodyLen=${l0.bodyLen}`);
  if (!(l0.href.startsWith('http') && l0.bodyLen > 500)) throw new Error('页面没加载，本台作废');

  await page.eval(`(() => {
    const ov = document.getElementById('orientation');
    const b = document.getElementById('orientClose');
    if (ov && !ov.classList.contains('hide') && b) b.click();
    const t = document.getElementById('tabPatch');
    if (t) t.click();
  })()`);
  await sleep(1500);

  // ================= 问题 2' =================
  console.log('\n=== 问题 2\'：`[data-verdict]` 是不是判决表那一批 ===\n');
  const q = JSON.parse(await page.eval(`(() => { ${FOLD}
    const all = [...document.querySelectorAll('[data-verdict]')];
    const rows = [...document.querySelectorAll('[data-gate]')];
    return JSON.stringify({
      foldWorked,
      nVerdict: all.length,
      nGateRow: rows.length,
      inGate: all.filter(e => e.closest('[data-gate]')).length,
      gateHasVerdict: rows.filter(tr => tr.getAttribute('data-verdict') !== null).length,
      domKeys: rows.map(tr => tr.getAttribute('data-key')),
      cells: rows.map(tr => [...tr.children].map(td => fold(td.innerText))),
      rowKey: rows.map(tr => tr.getAttribute('data-key')),
    });
  })()`));
  if (!q.foldWorked) throw new Error('页面侧空白折叠自检失败 ⇒ 本台作废（空白未折叠会把换行差异当成区分度）');
  console.log('  [自检] 页面侧空白折叠：生效 ✓（这一条不过，下面全部作废）');

  const same = q.inGate === q.nVerdict && q.nVerdict > 0;
  console.log(`  [data-verdict] ${q.nVerdict} 个 · [data-gate] 行 ${q.nGateRow} 个`);
  console.log(`  其中在 [data-gate] 行内：${q.inGate}/${q.nVerdict}  ⇒ `
    + (same ? '✅ **同一批元素**（数目相等不是巧合）' : '⚠⚴ **不是同一批** ⇒ 裸选择器会读到判决表之外'));
  console.log(`  [data-gate] 行自带 data-verdict：${q.gateHasVerdict}/${q.nGateRow}`);
  const domSet = new Set(q.domKeys), artSet = new Set(order);
  console.log(`  门键对账：DOM ${q.domKeys.length} / 产物 ${order.length}`
    + ` · 只在 DOM ${JSON.stringify(q.domKeys.filter(k => !artSet.has(k)))}`
    + ` · 只在产物 ${JSON.stringify(order.filter(k => !domSet.has(k)))}`);

  // ================= 问题 3：分列量区分度 =================
  console.log('\n=== 问题 3：判决表逐列 —— 哪一列给了读者区分度 ===\n');
  const nCell = Math.max(...q.cells.map(c => c.length));
  console.log(`  每行单元格数：${[...new Set(q.cells.map(c => c.length))].join('/')}（列数不齐时按 ${nCell} 算）\n`);
  for (let ci = 0; ci < nCell; ci++) {
    const vals = q.cells.map(c => c[ci] ?? '');
    const uniq = new Map();
    vals.forEach((v, i) => { if (!uniq.has(v)) uniq.set(v, []); uniq.get(v).push(q.rowKey[i]); });
    const uniqN = uniq.size;
    // 这一列是不是「机器键列」：值与 data-key 相同或含方括号
    const isMachine = vals.every((v, i) => v === q.rowKey[i] || /\[[a-z]+\]/.test(v));
    const tag = isMachine ? '⚠ 机器键列' : (uniqN === vals.length ? '✅ 人话列·逐行不同' : '⚠⚴ 人话列·有重复');
    console.log(`  第 ${ci + 1} 列：${uniqN} 种不同值 / ${vals.length} 行  ${tag}`);
    if (uniqN < vals.length) {
      [...uniq.entries()].filter(([, ks]) => ks.length > 1)
        .sort((a, b) => b[1].length - a[1].length).slice(0, 3).forEach(([v, ks]) => {
          console.log(`      ×${ks.length} 值=「${v.slice(0, 44)}」 门键=${JSON.stringify(ks.slice(0, 6))}`);
        });
      if (uniq.size > 3) console.log(`      …另有 ${uniq.size - 3} 组重复`);
    } else {
      console.log(`      样例：「${(vals[0] || '（空）').slice(0, 44)}」`);
    }
    console.log();
  }
  // 「剔掉机器列后还剩多少区分度」
  // ⚠ 按行索引取 rowKey —— 不用 cells.indexOf(c)（相同数组会取到第一行，静默给错归属）
  const humanOnly = q.cells.map((c, ri) => c
    .filter(v => !/\[[a-z]+\]/.test(v) && v !== q.rowKey[ri])
    .join('｜'));
  const hSet = new Set(humanOnly);
  console.log(`  ⚠ 只看**人话**（剔掉含方括号记号的值）⇒ ${hSet.size} 种不同可见文字 / ${humanOnly.length} 行`);
  if (hSet.size < humanOnly.length) {
    const m = new Map();
    humanOnly.forEach((v, i) => { if (!m.has(v)) m.set(v, []); m.get(v).push(q.rowKey[i]); });
    [...m.entries()].filter(([, ks]) => ks.length > 1)
      .sort((a, b) => b[1].length - a[1].length).forEach(([v, ks]) =>
        console.log(`    ×${ks.length}「${v.slice(0, 46)}」=${JSON.stringify(ks)}`));
  }

  // ================= 问题 4 =================
  console.log('\n=== 问题 4：`[word]`/`[num]` 有没有印给读者 ===\n');
  const blk = JSON.parse(await page.eval(`(() => { ${FOLD}
    const f = document.querySelector('[data-patch-fails]');
    return JSON.stringify({ foldWorked, failsTxt: f ? fold(f.innerText) : null });
  })()`));
  if (!blk.foldWorked) throw new Error('汇总块折叠自检失败 ⇒ 本台作废');
  const cW = (blk.failsTxt.match(/\[word\]/g) || []).length;
  const cN = (blk.failsTxt.match(/\[num\]/g) || []).length;
  console.log(`  汇总块全文（${blk.failsTxt.length} 字，未截断）：`);
  console.log(`  「${blk.failsTxt}」`);
  console.log();
  console.log(`  汇总块含 \`[word]\` ${cW} 次 · \`[num]\` ${cN} 次`);
  const rowHit = q.cells.map((c, i) => [i, c.filter(v => /\[[a-z]+\]/.test(v)).length]).filter(([, n]) => n > 0);
  console.log(`  判决表含方括号记号的行：${rowHit.length}/${q.rowTextN || q.rowKey.length}`);
  console.log(`  ⚠ 产物里 \`[word]\`/\`[num]\` **只存在于门键**（字段值里 0 处，本轮实测）`);
  console.log(`  ⚠ 产物同名的 \`arm_label\` 是人话：`
    + JSON.stringify([...new Set(order.map(k => gates[k].arm_label))]));
  console.log(`  ⇒ ${cW + cN + rowHit.length > 0
    ? '⚠⚴⚴ 机器门键进了读者可见文案；`verify_patch` 13/13 全绿、无一抓它'
    : '✅ 机器门键没进可见文案'}`);
  console.log(`\n  ⚠ 口径：本探针只量事实，不替判据或产品做对错判决。`);
} catch (e) {
  console.log('[装置错]', String(e && e.message ? e.message : e));
} finally {
  try { await cdp.send('Browser.close'); } catch {}
  try { proc.kill(); } catch {}
}
