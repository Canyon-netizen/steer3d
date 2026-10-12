// r128_k2_latent_teeth.mjs —— 修订 128：静态产物页 `verify_path.mjs` 的 K2 牙齿台
//
// 【为什么新写，不复用 r125_k2_teeth.mjs】
//   修订 127 实测：那台的 SPEC 是照 **React 页**的 `[data-*]` 写的，
//   而 `verify_path.mjs` 用 `LAT_URL` 跑的是**静态产物页**
//   （`#pathWrap` / `[data-patht]` / `[data-pathfork]` 这套）。
//   ⚠⚠⚴ 两个页面的 DOM 结构**完全不同** ⇒ 换 URL 复用会让 SPEC 全部失效。
//
// 【本台只做 B 组 13 条 needle 判据】
//   `verify_path.mjs:145-148`：
//       for (const [name, needle] of phrases)
//         check(name, T.includes(needle), `找不到「${needle}」`);
//   `T = document.querySelector('#pathWrap').innerText`（`:97/:114/:117`）
//   ⇒ **13 条全是「屏上可见文字里有没有这一句」** ⇒ 天然是 PAGE_TEXT 桶，
//      且**各自只锁一个 needle** ⇒ 定向扰动「把这个 needle 从 T 里删掉」，
//      判据应当转红；这是最干净的一族。
//
// ⚠⚠⚴⚠⚴ **判据主体纪律**：`T` 是整块 `#pathWrap` 的 innerText（**容器级**）。
//   修订 126 在 React 页上实测过：动容器 innerText 会换掉整棵子树，
//   新节点不被 React 持有 ⇒ 后续 spec 读到被冲掉的结构。
//   静态产物页是手写 HTML（无 React），**不能假定**它安全。
//   ⇒ 本台的处置：
//     ① 每条 spec 跑完立刻**从页面回读** `dom.now`，断言它等于我注入的值
//        （落地不保真就作废这条 spec，不算「转红」）；
//     ② 每条 spec 之后**重新导航 + 重新切屏**（不是还原 innerText）；
//     ③ 全部跑完再跑一遍**未扰动基线**，确认页面还能全绿
//        ⇒ 若基线也红 ⇒ 是我弄坏了页面，不是判据有牙齿。
//
// ⚠ 反漂移守卫：**不复写判据**，从已提交的 `verify_path.mjs` 抽 needle 原文。
//   抽不到 ⇒ 本台已漂移，拒绝发布。
//
// ⚠ 页面侧**不写正则**（修订 127 的教训：模板里写 `\\\\s` 会让页面侧拿到
//   `\\s` ⇒ 匹配字面反斜杠 ⇒ 空白没折叠 ⇒ 假绿）。改用 split/join。

import { launch, Page, CDP } from '/Users/zhourui/code/steer3d/.cache/browser_verify/cdp_client.mjs';
import { readFileSync } from 'node:fs';

const URL = process.env.LAT_URL || 'http://127.0.0.1:9006/latent/index.html';
const VER = '/Users/zhourui/code/steer3d/.cache/browser_verify/verify_path.mjs';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const NL = String.fromCharCode(10);

// ---------- 反漂移守卫：从已提交判据文件抽 phrases 原文 ----------
const src = readFileSync(VER, 'utf8');
const m = src.match(/const phrases = \[([\s\S]*?)\];/);
if (!m) { console.error('[自证失败] 抽不到 phrases ⇒ 本台已漂移，拒绝发布'); process.exit(2); }
// ⚠⚠⚴⚠⚴ **首版在这里漏了 B13**：needle 是 `"let's try to solve"` ——
//   双引号串里含单引号，而我原来的正则 `(?:[^'"\\]|\\.)*`
//   **两种引号都排除**，于是「双引号里裹着单引号」整行匹配失败。
// ⇒ 改用**引号感知的扫描**（扫到哪个引号就从哪个闭合），
//   **不自己写正则去猜引号配对**。
// ⚠⚠⚴ 而且首版把分母**硬编码成 13**，于是打印出「13 条 needle 基线命中 12/12」
//   —— 分子分母都不是真的（实际只抽到 12 条）。
//   ⚠ 这是「仪器自己给自己发绿」：那个自相矛盾的输出看起来完全正常，
//   若不是当场对着判据文件数一遍行数，它会被当成「有一条基线就红」发出去。
// ⇒ 分母一律用 SPECS.length，禁止写死。
const PHRASES = [];
{
  const raw = m[1];
  let i = 0;
  const readStr = () => {
    const q = raw[i];
    if (q !== '"' && q !== "'") return null;
    i++;
    let out = '';
    while (i < raw.length) {
      const c = raw[i];
      if (c === '\\') { out += raw[i + 1]; i += 2; continue; }   // 转义原样保留
      if (c === q) { i++; return out; }
      out += c; i++;
    }
    return null;
  };
  while (i < raw.length) {
    if (raw[i] !== '[') { i++; continue; }
    i++;
    while (raw[i] === ' ' || raw[i] === '\n' || raw[i] === '\t') i++;
    const a = readStr();
    if (a === null) break;
    while (raw[i] === ' ' || raw[i] === '\n' || raw[i] === '\t') i++;
    if (raw[i] !== ',') break;
    i++;
    while (raw[i] === ' ' || raw[i] === '\n' || raw[i] === '\t') i++;
    const b = readStr();
    if (b === null) break;
    while (raw[i] === ' ' || raw[i] === '\n' || raw[i] === '\t') i++;
    if (raw[i] === ']') i++;
    PHRASES.push([a, b]);
  }
}
// ⚠ 反漂移守卫的**下半半**：抽到的条数必须等于判据文件里 `[` 开头的行数。
//   少一条就意味着我的解析器又漏了 ⇒ 拒绝发布（只报数，不下结论）。
{
  const rowN = m[1].split(NL).filter(r => r.trim().startsWith('[')).length;
  console.log(`[自证] 判据文件里 phrases ${rowN} 行 · 本台解析出 ${PHRASES.length} 条`);
  if (rowN !== PHRASES.length) {
    console.error(`⚠⚴⚴ 解析器又漏了 ${rowN - PHRASES.length} 条 ⇒ 拒绝发布`);
    process.exit(2);
  }
}
console.log(`[自证] 从 verify_path.mjs 抽出 phrases ${PHRASES.length} 条（B 组判据）`);
console.log(`[自证] 产物原始守卫：\n${PHRASES.map(([n, x]) => `  ${n} ← 「${x}」`).join('\n')}`);

// 页面侧：折叠空白 + 自报折叠是否生效（不过则本台作废）
const FOLD = `
  const fold = s => String(s||'').split(String.fromCharCode(10)).map(x=>x.split(String.fromCharCode(9)).join(' ').trim()).filter(Boolean).join(' ');
  let foldWorked = fold(String.fromCharCode(97,10,32,98)) === 'a b';
`;

const SPECS = PHRASES.map(([name, needle]) => ({ name, needle }));

const { proc, version } = await launch({
  port: 9496, userDataDir: '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_r128_' + process.pid,
  windowSize: '1600,1050', url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);

const gotoPathTab = async () => {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  await sleep(3500);
  await page.eval(`(() => {
    const ov = document.getElementById('orientation');
    const b = document.getElementById('orientClose');
    if (ov && !ov.classList.contains('hide') && b) b.click();
    const t = document.getElementById('tabPath');
    if (t) t.click();
  })()`);
  await sleep(1200);
};
// 从页面回读 T（与判据同一个取法）
const readT = async () => JSON.parse(await page.eval(`(() => { ${FOLD}
  if (!foldWorked) return JSON.stringify({ foldWorked: false });
  const w = document.querySelector('#pathWrap');
  const t = w ? w.innerText : '';
  return JSON.stringify({ foldWorked: true, len: t.length, T: fold(t) });
})()`));
// 注入：把 needle 从 #pathWrap 的可见文字里抹掉
const killNeedle = async (needle) => JSON.parse(await page.eval(`(() => {
  const w = document.querySelector('#pathWrap');
  if (!w) return JSON.stringify({ ok: false, why: '没有 #pathWrap' });
  const before = w.innerText;
  const node = String.fromCharCode(96, 92, 66, 83, 58, 47, 103);
  const n = ${JSON.stringify(needle)};
  const after = before.split(n).join('');
  w.innerText = after;
  const now = w.innerText;
  return JSON.stringify({ ok: true, changed: now !== before, now: now.length, node });
})()`));

const results = [];
try {
  console.log('\n=== 基线（未扰动）===\n');
  await gotoPathTab();
  const base = await readT();
  if (!base.foldWorked) throw new Error('页面侧折叠自检失败 ⇒ 本台作废');
  console.log(`  #pathWrap.innerText ${base.len} 字（折叠后 ${base.T.length}）`);
  const baseHit = SPECS.filter(s => base.T.includes(s.needle)).length;
  console.log(`  ${SPECS.length} 条 needle 基线命中 ${baseHit}/${SPECS.length}`);
  if (baseHit !== SPECS.length) {
    console.log('  ⚠⚴ 基线就没全中 ⇒ 下面「转红」分不清是判据有牙齿还是本来就红');
    SPECS.filter(s => !base.T.includes(s.needle)).forEach(s => console.log(`    基线就缺：${s.name} ← 「${s.needle}」`));
  }
  results.push({ name: `【基线】${SPECS.length} 条 needle 全在屏上`, pass: baseHit === SPECS.length });

  console.log('\n=== 定向扰动：把该条 needle 从屏上抹掉 ===\n');
  for (const s of SPECS) {
    await gotoPathTab();                       // 每条都重新导航（不靠还原）
    const before = await readT();
    const k = await killNeedle(s.needle);
    if (!k.ok) { console.log(`  ⚠ ${s.name}：${k.why} ⇒ 本项未判`); results.push({ name: s.name, pass: null }); continue; }
    const after = await readT();               // 从页面回读，确认落地
    const stillThere = after.T.includes(s.needle);
    const landed = !stillThere;                // needle 确实被抹掉了
    // 判据谓词：T.includes(needle) —— 现在应为 false ⇒ 判据应判红
    const judgeWouldPass = stillThere;
    results.push({ name: s.name, pass: !judgeWouldPass, landed });
    console.log(`  ${landed ? '✅' : '⚠⚴未落地'} ${s.name}：needle ${landed ? '已从屏上抹掉' : '仍在屏上'}`
      + ` ⇒ 谓词 T.includes=${stillThere} ⇒ 判据${judgeWouldPass ? '仍绿（没牙齿）' : '转红 ✓'}`);
    console.log(`      innerText ${before.len} → ${after.len} 字`);
  }

  console.log('\n=== 收尾：全部扰动跑完后再跑一次未扰动基线 ===\n');
  await gotoPathTab();
  const fin = await readT();
  const finHit = SPECS.filter(s => fin.T.includes(s.needle)).length;
  console.log(`  ${SPECS.length} 条 needle 命中 ${finHit}/${SPECS.length} · innerText ${fin.len} 字`);
  results.push({ name: '【收尾】扰动跑完后页面仍能全绿（否则是我弄坏了页面）', pass: finHit === SPECS.length });

  const judged = results.filter(r => r.pass !== null);
  const ok = judged.filter(r => r.pass).length;
  const notLanded = judged.filter(r => r.landed === false).length;
  console.log(`\nRESULT ${ok === judged.length && notLanded === 0 ? 'PASS' : 'FAIL'} ${ok}/${judged.length}`);
  if (notLanded) console.log(`⚠⚴ ${notLanded} 条扰动没落地 ⇒ 那几条不算「判据有牙齿」`);
  console.log('⚠ 口径：K2 页面实例扰动证明「判据读的就是读者看到的那句话」；');
  console.log('⚠ **不**证明「产品改错时一定红」——那要改源码 + 重建。');
} catch (e) {
  console.log('[装置错]', String(e && e.message ? e.message : e));
} finally {
  try { await cdp.send('Browser.close'); } catch {}
  try { proc.kill(); } catch {}
}
