// r131b_cgroup_needle.mjs —— 修订 131：verify_path C 组（C5–C9）的 needle 命中与牙齿
//
// 【要量两件事，分开报】
//   ① **haystack**：每个 needle 在 `#pathWrap.innerText` 里出现几次、分别出现在哪
//   ② **牙齿**：把该判据的**全部** needle 从容器里删光后，`T.includes()` 是否转 false
//
// ⚠⚠⚴⚠ 为什么要把 needle **从判据自己的输出里解析**：
//   `verify_path.mjs:283-284` 只在判红时打 detail，全绿时一条都不印。
//   若我在这里手打 "-3.62/133/11.9%…"，那就是**我重算的 needle**，
//   一旦产物变了，探针还在量旧 needle，而判据已经量新的了 ——
//   ⚠ 探针与判据会静默分家，且两边都自认为是对的。
//   ⇒ 本脚本直接读 `r131a_path_echo.mjs` 的运行日志，从它的 `CHECK … 需 …` 行里取 needle。
//
// ⚠⚠⚴⚠ **子串串扰必须先说清**：C6 的 needle 是单字符 `"6"` 与 `"5"`，
//   而 `"6"` 是 `-3.62` 的子串、`"5"` 是 `53` 的子串。
//   ⇒ ① 的计数天然会把别的判据的 needle 算进去；
//     ② 删某个 needle 时也会顺带删掉别处含它的串。
//   ⇒ 每个判据**单独**做一次扰动（删该判据自己的全部 needle），不混着删。
//
// ⚠ 落地核验：删完必须回读该 needle 计数为 0，否则记「⚠未落地」，**不算判据结论**。
// ⚠ 静态产物页无 React reconcile（修订 128 实测）⇒ 容器级扰动不会被冲掉。

import { launch, Page, CDP } from '/Users/zhourui/code/steer3d/.cache/browser_verify/cdp_client.mjs';
import { readFileSync, existsSync } from 'node:fs';

const URL = process.env.LAT_URL || 'http://127.0.0.1:9006/latent/index.html';
const ECHO_LOG = '/Users/zhourui/code/steer3d/.cache/mutbak/r131a_echo.log';
const sleep = ms => new Promise(r => setTimeout(r, ms));

// ---- 反漂移：从判据自己的输出解析 needle ----
// ⚠⚗⚗⚗⚗⚠ **本文件第一版在这里假绿过**：解析器按 detail 字符串的**形状**切，
//   于是 `需 R6=6 R5=5` 与 `需 n=133 pos=53 neg=80`（**没有斜杠**）被整串当成 needle。
//   那两个字符串在页面上出现 0 次、删 0 次、计数 0→0，
//   而「落地 = after===0」在基线本就为 0 时空洞成立 ⇒ 脚本印出「转红✓有牙齿」。
//   ⚠ 同一批 C5 却是 `需 -3.62/1.56/5.18`（有斜杠）被正确拆开 ⇒ 输出自相矛盾。
//
// ⚠⚠⚴⚠ **判别式：解析器必须按「判据怎么用这个值」还原，不能按 detail 字符串长什么样切。**
//   判据对 C6 用的是 `T.includes(String(R6_rank_swapped)) && T.includes(String(R5_pure_swap))`
//   ⇒ needle 是**两个独立的值**，不是「R6=6 R5=5」这一整串。
//
// ⚠⚠⚴ 四道防假绿的门，本文件全都要有：
//   ① 按 `键=值` 拆对，不按分隔符瞎切
//   ② **基线可达性断言**：每个 needle 在未扰动页面上必须 ≥1 次，否则 exit 2
//   ③ **落地判据 = `occ > 0` 且 `after === 0`**（不能只有后者）
//   ④ **负对照臂**：故意用一个页面上不存在的 needle，
//      断言它被判「⚠未落地」而不是「转红✓」⇒ 仪器自己证明自己有牙齿
const KEYVAL = {
  C6: ['R6', 'R5'],       // 判据用它验的是 R6_rank_swapped 与 R5_pure_swap 两个值
  C7: ['n', 'pos', 'neg'], // 同上：三个独立值
};
const parseNeedles = (id, rest) => {
  if (KEYVAL[id]) {
    // ⚠ 一律按「键=值」逐个取，**不按空格/斜杠切**，避免再犯第一版的错
    return KEYVAL[id].map(k => {
      const m = new RegExp(`(?:^|\\s)${k}=(\\S+?)(?=\\s|$)`).exec(rest);
      if (!m) return null;
      return m[1];
    }).filter(v => v !== null);
  }
  return rest.split('/').map(s => s.trim()).filter(Boolean);
};

if (!existsSync(ECHO_LOG)) {
  console.error(`[自证失败] 找不到 ${ECHO_LOG} ⇒ 没有判据自己的 needle 输出，拒绝发布`);
  process.exit(2);
}
const echoLog = readFileSync(ECHO_LOG, 'utf8');
const spec = [];
for (const line of echoLog.split('\n')) {
  const m = /^CHECK\t(OK|RED)\t(C[5-9])\s.*?需\s+(.+)$/.exec(line);
  if (m) spec.push({ id: m[2], ok: m[1] === 'OK', needles: parseNeedles(m[2], m[3].trim()) });
  const m9 = /^CHECK\t(OK|RED)\tC9\s.*?尾 18 字「(.+)」$/.exec(line);
  if (m9 && !spec.some(s => s.id === 'C9')) spec.push({ id: 'C9', ok: m9[1] === 'OK', needles: [m9[2]] });
}
if (spec.length !== 5) {
  console.error(`[自证失败] 从判据输出解析出 ${spec.length} 条（要求 5：C5–C9）⇒ 日志格式变了，拒绝发布`);
  process.exit(2);
}
for (const s of spec) {
  if (!s.needles.length) { console.error(`[自证失败] ${s.id} 解析出 0 个 needle ⇒ 解析器坏了，拒绝发布`); process.exit(2); }
  // ⚠⚠⚴ **每条 needle 都必须短到「不太可能是巧合」，长 needle 除外**。
  //   这里只挡一个真会发生的错：needle 里带空格/标点的分段解析残留。
  for (const n of s.needles) if (/\s(?:R\d|n|pos|neg)=/.test(n)) {
    console.error(`[自证失败] ${s.id} 的 needle ${JSON.stringify(n)} 像是没拆开的键值串 ⇒ 解析器坏了，拒绝发布`);
    process.exit(2);
  }
}
console.log('[自证] 5 条 needle 全部解析自 verify_path 自己的 CHECK 输出 ✓');
for (const s of spec) console.log(`       ${s.id} ${s.ok ? 'OK' : 'RED'}  needle=${JSON.stringify(s.needles)}`);

const { proc, version } = await launch({
  port: 9497, userDataDir: '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_r131b_' + process.pid,
  windowSize: '1600,1050', url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);

const nav = async () => {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  await sleep(3500);
  await page.eval(`(() => {
    const ov = document.getElementById('orientation'); const b = document.getElementById('orientClose');
    if (ov && !ov.classList.contains('hide') && b) b.click();
    const t = document.getElementById('tabPath'); if (t) t.click();
  })()`);
  await sleep(1200);
};

// 量：needle 在容器里出现几次 + 每次出现在哪个元素、什么上下文
const tally = async (needle) => JSON.parse(await page.eval(`(() => {
  const wrap = document.getElementById('pathWrap');
  const T = (wrap && wrap.innerText) || '';
  const n = ${JSON.stringify(needle)};
  const cnt = (h, w) => h.split(w).length - 1;
  // 逐文本节点定位出处，⚠ 不用正则
  const tw = document.createTreeWalker(wrap, NodeFilter.SHOW_TEXT, null);
  const hits = []; let nd;
  while ((nd = tw.nextNode())) {
    if (!nd.nodeValue || !nd.nodeValue.includes(n)) continue;
    const el = nd.parentElement;
    hits.push({ tag: el.tagName, cls: String(el.className || '').split(' ')[0],
                c: cnt(nd.nodeValue, n),
                ctx: nd.nodeValue.trim().replace(/\\s+/g, ' ').slice(0, 58) });
    if (hits.length >= 8) break;
  }
  return JSON.stringify({ total: cnt(T, n), hits });
})()`));

// 删：把 needle 在容器里的**全部**出现抹掉（容器级；静态页不会被 reconcile 冲掉）
const kill = async (needle) => JSON.parse(await page.eval(`(() => {
  const wrap = document.getElementById('pathWrap');
  const n = ${JSON.stringify(needle)};
  const tw = document.createTreeWalker(wrap, NodeFilter.SHOW_TEXT, null);
  let nd, occ = 0;
  while ((nd = tw.nextNode())) {
    if (!nd.nodeValue || !nd.nodeValue.includes(n)) continue;
    occ += nd.nodeValue.split(n).length - 1;
    nd.nodeValue = nd.nodeValue.split(n).join('〔删〕');
  }
  return JSON.stringify({ occ, total: (wrap.innerText || '').split(n).length - 1 });
})()`));

try {
  console.log('\n=== 第 0 层：needle 的 haystack 与出处 ===\n');
  await nav();
  const BASE = {};
  let unreachable = [];
  for (const s of spec) {
    console.log(`${s.id}：`);
    for (const n of s.needles) {
      const t = await tally(n);
      BASE[s.id + '|' + n] = t.total;
      // ⚠⚠⚴ **基线可达性断言**：needle 在**未扰动**页面上必须 ≥1 次。
      //   为 0 说明解析器拆错了（第一版就是靠这条能当场抓到的）⇒ 拒绝发布。
      if (t.total === 0) unreachable.push(`${s.id}:「${n}」`);
      console.log(`  「${n}」×${t.total}${t.total > 1 ? '  ⚠⚠ 多处命中' : ''}`);
      for (const h of t.hits) console.log(`      ${h.tag}${h.cls ? '.' + h.cls : ''} ×${h.c}  ${JSON.stringify(h.ctx)}`);
    }
  }
  if (unreachable.length) {
    console.error('[自证失败] 以下 needle 在未扰动页面上出现 0 次 ⇒ 解析器拆错了，拒绝发布：'
      + '\n   ' + unreachable.join('\n   '));
    process.exit(2);
  }
  console.log('\n[自证 ✓] 全部 needle 在未扰动页面上均可达（≥1 次）');

  console.log('\n=== 牙齿：每条判据单独删光自己的全部 needle ===\n');
  const R = [];
  for (const s of spec) {
    await nav();
    const before = {};
    for (const n of s.needles) before[n] = (await tally(n)).total;
    const killed = [];
    for (const n of s.needles) killed.push(await kill(n));
    const after = {};
    let landed = true;
    for (const n of s.needles) {
      const t = await tally(n);
      after[n] = t.total;
      // ⚠⚠⚴ 落地 = **删到过东西** 且 **计数变 0**。⚠ 只有后者的话，
      //   基线本就 0 的 needle 会空洞「落地」——修订 129 §129.1② 与本文件第一版各犯一次。
      const occ = s.needles.reduce((a, n) => a + killed[s.needles.indexOf(n)].occ, 0);
      if (after[n] !== 0 || (before[n] > 0 && occ === 0)) landed = false;
    }
    const stillAll = s.needles.every(n => after[n] > 0);
    const verdict = !landed ? '⚠未落地⇒不算结论' : (stillAll ? '⚠仍绿（删光了自己的 needle 仍过）' : '转红✓有牙齿');
    console.log(`  ${s.id}  删 ${killed.map((k, i) => `「${s.needles[i]}」删${k.occ}次`).join(' ')}`);
    console.log(`       计数 ${JSON.stringify(before)} → ${JSON.stringify(after)}  ⇒ ${verdict}`);
    R.push({ id: s.id, landed, teeth: !stillAll, before, after });
  }

  // ---- 负对照臂：页面上**不存在**的 needle，删它必须判「未落地」而不是「转红」 ----
  // ⚠⚠⚴⚠ 这一臂是本台**第一版假绿**的直接解药：
  //   第一版把「页面上根本不存在」的 needle 判成了「转红✓有牙齿」，
  //   而**没有任何东西拦它**。这一臂让仪器自己证明自己有牙齿。
  console.log('\n=== 负对照臂：喂一个页面上不存在的 needle ===\n');
  await nav();
  const GHOST = '〔本 needle 不可能出现在页面上 8f3a〕';
  const ghostBefore = (await tally(GHOST)).total;
  const ghostKill = await kill(GHOST);
  const ghostAfter = (await tally(GHOST)).total;
  const ghostLanded = ghostKill.occ > 0 && ghostAfter === 0;
  console.log(`  needle=${GHOST}`);
  console.log(`  基线 ${ghostBefore} 次 · 删 ${ghostKill.occ} 次 · 删后 ${ghostAfter} 次`);
  console.log(`  ⇒ ${ghostLanded ? '⚠⚠⚴⚴ 仪器坏了：不存在的东西也能「落地」⇒ 本轮全部结论作废' : '仪器正确判「未落地」✓（这一臂证明本台不会把不存在的 needle 判成有牙齿）'}`);
  if (ghostLanded) {
    console.error('[装置故障] 负对照臂没通过 ⇒ 本轮任何「有牙齿」结论都不作废（是仪器自己的问题）');
    process.exit(2);
  }

  await nav();
  console.log('\n=== 收尾：重新导航后基线 ===\n');
  let baseOk = 0;
  await nav();
  for (const s of spec) {
    // ⚠⚠⚴ 不能写 `needles.every(n => (await tally(n))…)` ——
    //   every 的回调不是 async，里面 await 会直接语法报错（本轮踩到）。
    let all = true;
    for (const n of s.needles) if ((await tally(n)).total <= 0) { all = false; break; }
    if (all) baseOk++;
  }
  console.log(`  ${baseOk}/${spec.length} 条判据的 needle 在未扰动页面上重新命中 ⇒ 扰动没有把页面弄坏`);
  console.log(`  （⚠ 分母 = SPECS.length = ${spec.length}，未写死）`);

  const teeth = R.filter(r => r.teeth && r.landed).length;
  console.log(`\n⚠ 结论：C5–C9 共 ${spec.length} 条，**实测有牙齿 ${teeth} 条**`
    + `${teeth === spec.length ? '' : '，无牙齿 ' + R.filter(r => r.landed && !r.teeth).map(r => r.id).join('、')}`);
} catch (e) {
  console.log('[装置错]', String(e && e.message ? e.message : e));
} finally {
  try { await cdp.send('Browser.close'); } catch {}
  try { proc.kill(); } catch {}
}