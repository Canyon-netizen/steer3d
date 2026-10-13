// r129b2_patch_layered.mjs —— 修订 129 第二刀 v2：P9/P10/P11 的**分层删除**（文本节点级）
//
// 【v1 三处病，本版逐条修掉】
//   ① ⚠⚠⚴⚴ 枚举用 `e.children.length === 0` 的**叶子元素** ⇒ 混排元素（`<td>主量 <b>x</b></td>`）
//      里的裸文本整段漏掉。证据：v1 印 `主量 L1=12 L2=1 全容器=15`，12+1=13 ≠ 15（缺口 2），
//      `次量` 同样缺 2 ⇒ v1 的 P9[L1] 臂只删掉 12/15，**「仍绿」是没删干净，不是判据不灵**。
//      修法：改用 TreeWalker 走**文本节点**（NodeFilter.SHOW_TEXT），混排元素的裸文本必被覆盖。
//   ② ⚠⚠⚴ 落地断言 `after===0` 在**该层基线本就是 0** 时空洞成立。
//      证据：v1 的 P11[L1] 删了 0 个叶子却判「落地 ⇒ ⚠仍绿」。
//      修法：落地 = 「删到过东西（hits>0）」**且**「该层该词计数变 0」，否则记 `不适用`（基线本就 0）。
//   ③ ⚠⚠⚴⚠ 结论表判定逻辑反了。v1:166 `a.wouldPass ? '锁在 L2' : '被 L1 喂饱'`
//      —— 「被 L1 喂饱」要看的是**删 L2 是否仍绿**，代码看的却是删 L1。本轮未触发，但会误导下轮。
//      修法：三分支按「删 L2 是否仍绿」判锚点，写清读法。
//
// 【v2 新增：口径钉死 —— 两个数不是同一个量】
//   判据读的是 `innerText`（受渲染影响：隐藏元素不计入、空白归一）；
//   文本节点读的是 `nodeValue`（含隐藏节点）。两者**可能不等**。
//   ⇒ 每词同时印 `container`(innerText) 与 `nodeAll`(文本节点) 三个数，
//     落地判据用**层内文本节点计数变 0**（内层口径，判定更严），
//     并显式印出 `container - nodeAll` 的缺口；若缺口>0 ⇒ 在该词上「层内清零」**不等于**
//     「容器内清零」，此时容器口径的转红结论必须降级为「无法判定」。
//
// 【决定性设计：两层互斥，结论唯一】
//   L1 = 判决表容器内（`[data-gate]` 行所在的 `<table>`，用 closest 判**归属**不用数目相等）
//   L2 = 判决表容器外、仍在 `#patchWrap` 内的说明块
//   扰动 A：**只删 L1 的**（L2 一字不动）   扰动 B：**只删 L2 的**（L1 一字不动）
//
//   读法（v1 读法是错的，以本版为准）：
//     删 L1 转红 ⇒ L1 是**必要**来源（缺 L1 就红）
//     删 L2 转红 ⇒ L2 是**必要**来源（缺 L2 就红）⇒ 该词锁在说明块 ✓ 作用域正确
//     删 L1 仍绿 ⇒ **L2 单独就能满足**（L1 不是锚点）
//     删 L2 仍绿 ⇒ **L1 单独就能满足**（L2 不是锚点）⇒ ⚠ 被判决表重复文案喂饱
//     两个都仍绿 ⇒ 两层各自独立可满足 ⇒ 判据**没有任何层锚点**
//
// ⚠⚠⚴⚠⚴ **内建阳性对照**：P11 的「陌生度」全容器仅 1 次且在 L2
//   ⇒ P11[L2] 那一臂若不转红，就是仪器坏了（不是判据不灵）。
//   本版每轮都跑它，任何一次不红都直接 exit 2 拒绝发布。

import { launch, Page, CDP } from '/Users/zhourui/code/steer3d/.cache/browser_verify/cdp_client.mjs';
import { readFileSync } from 'node:fs';

const URL = process.env.LAT_URL || 'http://127.0.0.1:9006/latent/index.html';
const VER = '/Users/zhourui/code/steer3d/.cache/browser_verify/verify_patch.mjs';
const sleep = ms => new Promise(r => setTimeout(r, ms));

// ---- 反漂移守卫下半道：谓词逐字出自已提交判据文件，且解析条数须 == 源文件条数 ----
const src = readFileSync(VER, 'utf8');
const SPECS = [
  { id: 'P9',  line: "const hasBoth = /主量/.test(txt) && /次量/.test(txt);",           words: ['主量', '次量'] },
  { id: 'P10', line: "const saysCtrl = /幅度配平/.test(txt) && /逐节点相等/.test(txt);", words: ['幅度配平', '逐节点相等'] },
  { id: 'P11', line: "const warnsNoise = /陌生度/.test(txt);",                        words: ['陌生度'] },
];
for (const s of SPECS) if (!src.includes(s.line)) { console.error(`[自证失败] ${s.id} 谓词抽不到 ⇒ 漂移，拒绝发布`); process.exit(2); }
{
  // 源文件里这三处 `/xxx/.test(txt)` 的实际条数，须与 SPECS 解析出的 word 数一致
  // ⚠⚠⚴ 源文件里 `/xxx/.test(txt)` 共 **9 处**，但那是 5 个**不同的词** ——
  //   P9/P10/P11 在 `detail` 模板串里把同一批谓词又求值了一遍（9 = 2+2+2+2+1）。
  //   ⇒ 守卫必须比**去重后的词集**，比「出现次数」会把 9 当成 9 条判据。
  //   （本版第一稿正是比了次数 ⇒ 被自己写的守卫当场拦下，这正是下半道的作用。）
  const hit = [...src.matchAll(/\/([^\/\n]+)\/\.test\(txt\)/g)].map(m => m[1]);
  const want = SPECS.flatMap(s => s.words);
  const hitSet = [...new Set(hit)].sort(), wantSet = [...new Set(want)].sort();
  if (JSON.stringify(hitSet) !== JSON.stringify(wantSet)) {
    console.error(`[自证失败] 源文件去重词集 ${JSON.stringify(hitSet)} ≠ SPECS ${JSON.stringify(wantSet)} ⇒ 漂移，拒绝发布`);
    process.exit(2);
  }
  if (hit.length !== want.length + 4) {   // 4 = detail 串里重复求值的 4 次（陌生度不在 detail 里）
    console.error(`[自证失败] 源文件 ${hit.length} 处，去重 ${hitSet.length} 个词，SPECS ${want.length} 个 ⇒ 关系变了，重复次数需重新核对`);
    process.exit(2);
  }
  console.log(`[自证] 源文件 /…/.test(txt) ${hit.length} 处 = 去重 ${hitSet.length} 词（其中 4 次是 detail 串里重复求值）`);
}
console.log(`[自证] 三处谓词逐字出自 verify_patch.mjs ✓；源文件 /…/.test(txt) ${SPECS.flatMap(s => s.words).length} 个词与 SPECS 一一对应 ✓`);

// ---- 页面侧公共段：文本节点级遍历（不写正则；层归属用 closest，不用数目相等）----
const WALK_FN = `
  const wrap = document.getElementById('patchWrap');
  if (!wrap) return JSON.stringify({ fatal: 'no-wrap' });
  const anchor = document.querySelector('#patchWrap [data-gate]');
  const tbl = anchor ? anchor.closest('table') : null;
  const tw = document.createTreeWalker(wrap, NodeFilter.SHOW_TEXT, null);
  const layerOf = el => (tbl && (tbl === el || tbl.contains(el))) ? 'L1' : 'L2';
  const nodes = [];
  let n;
  while ((n = tw.nextNode())) {
    if (!n.nodeValue || !n.nodeValue.trim()) continue;
    nodes.push({ v: n.nodeValue, layer: layerOf(n.parentElement),
                 el: n.parentElement.tagName + (n.parentElement.className ? '.' + String(n.parentElement.className).split(' ')[0] : '') });
  }
  const count = (hay, w) => hay.split(w).length - 1;
`;

const tally = async (word) => JSON.parse(await page.eval(`(() => { ${WALK_FN}
  const w = ${JSON.stringify(word)};
  const nodeL1 = nodes.filter(x => x.layer === 'L1').reduce((a, x) => a + count(x.v, w), 0);
  const nodeL2 = nodes.filter(x => x.layer === 'L2').reduce((a, x) => a + count(x.v, w), 0);
  const samples = [];
  for (const x of nodes) { const c = count(x.v, w); if (c && samples.length < 4) samples.push(x.layer + '|' + x.el + '|' + JSON.stringify(x.v.trim().slice(0, 34))); }
  return JSON.stringify({
    container: count(wrap.innerText || '', w),          // ⚠ 判据口径
    nodeAll: nodeL1 + nodeL2, nodeL1, nodeL2,            // ⚠ 文本节点口径
    tblInner: tbl ? count(tbl.innerText || '', w) : null,
    samples,
  });
})()`));

const { proc, version } = await launch({
  port: 9495, userDataDir: '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_r129b2_' + process.pid,
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
    const t = document.getElementById('tabPatch'); if (t) t.click();
  })()`);
  await sleep(1200);
};

// 真删：TreeWalker 走文本节点，命中即改 nodeValue
const realKill = async (word, layer) => JSON.parse(await page.eval(`(() => { ${WALK_FN}
  const w = ${JSON.stringify(word)}, want = ${JSON.stringify(layer)};
  let hit = 0, occ = 0;
  const tw2 = document.createTreeWalker(wrap, NodeFilter.SHOW_TEXT, null);
  let nd;
  while ((nd = tw2.nextNode())) {
    if (!nd.nodeValue || !nd.nodeValue.includes(w)) continue;
    if (layerOf(nd.parentElement) !== want) continue;
    occ += nd.nodeValue.split(w).length - 1;
    nd.nodeValue = nd.nodeValue.split(w).join('〔已删〕');
    hit++;
  }
  return JSON.stringify({ hit, occ });
})()`));

const judge = async (s) => JSON.parse(await page.eval(`(() => {
  const txt = (document.getElementById('patchWrap')||{}).innerText || '';
  const r = {};
  for (const [k, w] of Object.entries(${JSON.stringify(Object.fromEntries(s.words.map(w => [w, w])))})) r[k] = txt.split(w).length - 1;
  return JSON.stringify(r);
})()`));

const R = [];
try {
  console.log('\n=== 第 0 层：每词的口径对账（innerText vs 文本节点）===\n');
  const BASE = {};
  await nav();
  for (const s of SPECS) {
    console.log(`${s.id}：`);
    for (const w of s.words) {
      const t = await tally(w); BASE[w] = t;
      const gap = t.container - t.nodeAll;
      console.log(`  「${w}」 判据口径 innerText=${t.container} · 文本节点 L1=${t.nodeL1} L2=${t.nodeL2} 合计=${t.nodeAll}`
        + ` · 判决表自身 innerText=${t.tblInner} · 缺口(container-nodeAll)=${gap}${gap ? ' ⚠≠0' : ' ✓'}`);
      for (const sm of t.samples) console.log(`      ${sm}`);
    }
  }

  for (const layer of ['L1', 'L2']) {
    console.log(`\n=== 扰动 ${layer}：只删该层里的目标词 ===\n`);
    for (const s of SPECS) {
      await nav();
      const beforeJudge = await judge(s);
      const arm = [];
      for (const w of s.words) {
        const baseNode = BASE[w][layer === 'L1' ? 'nodeL1' : 'nodeL2'];
        if (baseNode === 0) { arm.push({ w, hits: 0, occ: 0, before: 0, after: 0, status: '不适用（本层基线 0）' }); continue; }
        const k = await realKill(w, layer);
        const t = await tally(w);
        const after = layer === 'L1' ? t.nodeL1 : t.nodeL2;
        const landed = k.occ > 0 && after === 0;
        arm.push({ w, hits: k.hit, occ: k.occ, before: baseNode, after,
                   container: t.container, status: landed ? '落地' : '⚠未落地' });
      }
      const now = await judge(s);
      const anyNa = arm.some(a => a.status.startsWith('不适用'));
      const allLanded = arm.every(a => a.status === '落地');
      const wouldPass = s.words.every(w => now[w] > 0);
      let verdict;
      if (anyNa) verdict = '本臂不适用（至少一个词在该层本就 0）';
      else if (!allLanded) verdict = '⚠未落地 ⇒ 不算判据结论';
      else verdict = wouldPass ? '⚠仍绿' : '转红✓';
      console.log(`  ${s.id} [${layer}] ` + arm.map(a => `「${a.w}」${a.status}${a.status === '落地' ? `(删${a.hits}节点/${a.occ}次, ${a.before}→${a.after}, 容器余${a.container})` : `(${a.status})`}`).join(' '));
      console.log(`      谓词：${JSON.stringify(beforeJudge)} → ${JSON.stringify(now)} ⇒ ${verdict}`);
      R.push({ id: s.id, layer, landed: allLanded && !anyNa, wouldPass, na: anyNa });
    }
  }

  // ---- 内建阳性对照：P11[L2] 必须转红，否则仪器坏了 ----
  const pc = R.find(r => r.id === 'P11' && r.layer === 'L2');
  if (!pc || !pc.landed || pc.wouldPass) { console.error('\n[仪器坏了] 阳性对照 P11[L2] 没能转红 ⇒ 拒绝发布（不是判据不灵）'); process.exit(2); }
  console.log(`\n[阳性对照 ✓] P11[L2] 落地且转红 ⇒ 仪器在本层有牙齿`);

  console.log('\n=== 收尾：重新导航后基线 ===\n');
  const okAll = R.filter(r => r.landed && !r.wouldPass).length;
  console.log(`  落地且转红 ${okAll}/${R.length}（⚠ 分母含「不适用」臂，不能当通过率读）`);

  console.log(`\n⚠ 结论表（v2 读法；v1 的读法是错的）：`);
  for (const s of SPECS) {
    const a = R.find(r => r.id === s.id && r.layer === 'L1');   // 只删 L1
    const b = R.find(r => r.id === s.id && r.layer === 'L2');   // 只删 L2
    if (!a?.landed || !b?.landed) { console.log(`  ${s.id}：有一臂不适用/未落地 ⇒ 本项无法判定`); continue; }
    const L1anchor = !a.wouldPass;   // 删 L1 转红 ⇒ L1 必要
    const L2anchor = !b.wouldPass;   // 删 L2 转红 ⇒ L2 必要
    const s1 = L1anchor ? '转红' : '仍绿', s2 = L2anchor ? '转红' : '仍绿';
    const verdict = L2anchor && !L1anchor ? '锁在 L2 说明块 ✓ 作用域正确'
      : (L1anchor && !L2anchor ? '锁在 L1 判决表 ⚠ 名字说说明块、实际锁判决表'
      : (L1anchor && L2anchor ? '⚠⚴ 两层都必要 ⇒ 判据跨层取词，无法归因到说明块'
      : '⚠⚴⚴ 两层各自独立可满足 ⇒ 判据无任何层锚点'));
    console.log(`  ${s.id}：只删 L1 ${s1} · 只删 L2 ${s2}  ⇒ ${verdict}`);
  }
} catch (e) {
  console.log('[装置错]', String(e && e.message ? e.message : e));
} finally {
  try { await cdp.send('Browser.close'); } catch {}
  try { proc.kill(); } catch {}
}