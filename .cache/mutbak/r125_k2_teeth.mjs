// r125_k2_teeth.mjs —— 修订 125：通用「页面实例级」判据功效台（K2）
//
// 为什么要有它（修订 121 §121.1 的直接后果）：
//   K1 = doctored 产物，**结构上测不了** PAGE_TEXT / PAGE_ATTR 桶 ——
//   页面上的字和判据的期望值读同一个文件 ⇒ 一起变 ⇒ 恒绿。
//   ⇒ PAGE 桶只能靠 K2 = **改已渲染 DOM 的 innerText**（不动源码、不动产物、不重建）。
//
// 本台的四道对照（缺一不可，抄自 r116_n1_selftest.mjs 的骨架）：
//   ① 阳性：真实 DOM 上该判据必须为绿（谓词对真页面成立）
//   ② 阴性：把**同一元素**上该判据锚定的那个点改错 ⇒ 必须转红
//   ③ 还原：改回原句 ⇒ 必须重新变绿（⚠ r116 第一版就栽在这一步之后）
//   ④ 污染：改**别的**元素 ⇒ 该判据必须**仍然绿**
//      （否则「什么改动都让它红」= 仪器在喊叫，不是在测量）
//
// ⚠⚠ 反漂移守卫：每条谓词都是**从已提交判据文件里逐字抽出来的**，
//   启动时断言 `src.includes(verbatim)`；抽不到就 exit 2。
//   ⇒ 判据改了而本台没跟 ⇒ 立刻炸，不会默默测一个已经不存在的东西。
//
// ⚠⚠ 口径（与 r116 同款，必须随结论一起说）：
//   这是**页面实例级**扰动 —— 把已渲染的 DOM 改掉。
//   它能证明「该判据读的确实是**页面上读者看到的那句话**」，
//   **不能**证明「组件写错时该判据一定红」—— 后者要改源码 + 重建。
//   ⚠ React 重渲染会把改动冲掉，所以每条都在**同一帧内**读完再还原。

import { launch, Page, CDP } from '/Users/zhourui/code/steer3d/.cache/browser_verify/cdp_client.mjs';
import { readFileSync } from 'node:fs';

const URL = process.env.BV_URL || 'http://127.0.0.1:9006/';
const VER = '/Users/zhourui/code/steer3d/.cache/browser_verify/verify_heldout.mjs';
const D = '/Users/zhourui/code/steer3d/frontend/public/latent/data/';
const PORT = 9495;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const die = m => { console.log('[闸门失败] ' + m); process.exit(2); };

const truth = JSON.parse(readFileSync(D + 'heldout_readability.json', 'utf8'));
const SUB = JSON.parse(readFileSync(D + 'readable_subspace.json', 'utf8'));
const AXR = JSON.parse(readFileSync(D + 'axis_readouts.json', 'utf8'));

// ---- 判据要用的期望值：**全部从产物现取**，不写死 ----
const sh = SUB.headline, sens = sh.threshold_sensitivity;
const selKey = Object.keys(sens).find(k => Math.abs(+k - +sh.separation_threshold) < 1e-12);
const underKeys = Object.keys(sens).filter(k => +k < +selKey).sort((a, b) => +b - +a);
const worstKey = underKeys[0];
const gNewClean = truth.headline.new_clean, gNewWeak = truth.headline.new_weak;
const gGreedy = sens[worstKey].greedy, gWorst = sens[worstKey].perm_min;
const sameRows = truth.rows.filter(r => r.verdict === 'same_direction');
const mLo = Math.min(...sameRows.map(r => r.margin));
const mHi = Math.max(...sameRows.map(r => r.margin));
const AX_KEYS = Object.keys(AXR.axes || {});

// ---- 待验判据：每条的 `verbatim` 必须逐字出现在**对应的已提交判据文件**里 ----
// textVar = 谓词里那个「页面文字」变量的名（机械替换成 T，不重新实现谓词）
// extras  = 该谓词还需要的额外绑定（如 D6 要拿产物里的 sp.note 比对）
// ⚠ mut 两种方向：
//    · 替换型（删/改某个片断）—— 用于正向断言
//    · 注入型（往元素里塞一段）—— 用于**否定性断言**（D2 要求「不许出现」，
//      只能靠「放进去看它红不红」来验；否则它被平凡满足）
const AXR_ = '/Users/zhourui/code/steer3d/.cache/browser_verify/verify_axis_readout.mjs';
const AXT = JSON.parse(readFileSync(D + 'axis_readouts.json', 'utf8'));

const SPECS = [
  { id: 'E1b', sel: '[data-heldout-verdict-text]', textVar: 'P.verdict',
    verbatim: "P.verdict.includes('①') && P.verdict.includes('②') && P.verdict.includes('数字内容') && P.verdict.includes('同一条方向的重新构造')",
    mut: `T.replace('数字内容', '数字内码')` },
  { id: 'D3', sel: '[data-selfdup-verdict]', textVar: 'P.dupText',
    verbatim: "P.dupText.includes('就是同一个观测量') && P.dupText.includes('设计失误')",
    mut: `T.replace('就是同一个观测量', '不是同一个观测量')` },
  { id: 'I4', sel: '[data-recipe-verdict]', textVar: 'rc.verdict',
    verbatim: "(rc.verdict || '').includes('可读') && (rc.verdict || '').includes('有配方') && (rc.verdict || '').includes('可注入') && /可注入\\s*[✗✘×x]/.test(rc.verdict || '')",
    mut: `T.replace(/可注入\\s*[✗✘×x]/, '可注入 ✓')` },
  { id: 'B4', sel: '[data-block="transfer"]', textVar: 'TB.text',
    verbatim: "TB.text.includes('逐行独立估计') && TB.text.includes('自己的打乱地板')",
    mut: `T.replace('逐行独立估计', '逐行统一估计')` },
  { id: 'G1', sel: '[data-heldout-not-claimed]', textVar: 'NC',
    verbatim: "new RegExp('补进来 ' + (gNewClean + gNewWeak) + ' 条').test(NC)",
    mut: `T.replace('补进来 ' + (gNewClean + gNewWeak) + ' 条', '补进来 9 条')` },
  { id: 'G5', sel: '[data-heldout-not-claimed]', textVar: 'NC',
    verbatim: "new RegExp('greedy 估法给 ' + gGreedy).test(NC) && /不是一回事/.test(NC)",
    mut: `T.replace('不是一回事', '是同一回事')` },
  { id: 'G6', sel: '[data-heldout-verdict-text]', textVar: 'VD',
    verbatim: "new RegExp('把 ' + sameRows.length + ' 个判成同一条方向').test(VD) && new RegExp('另 ' + (gNewClean + gNewWeak) + ' 个才是新方向').test(VD)",
    mut: `T.replace('把 ' + sameRows.length + ' 个判成同一条方向', '把 ' + (sameRows.length + 1) + ' 个判成同一条方向')` },
  { id: 'G7', sel: '[data-heldout-verdict-text]', textVar: 'VD',
    verbatim: "new RegExp('余量 ≈ ' + mLo.toFixed(2) + '–' + mHi.toFixed(2) + '×').test(VD)",
    mut: `T.replace('余量 ≈ ' + mLo.toFixed(2) + '–' + mHi.toFixed(2) + '×', '余量 ≈ 1.00×')` },
  { id: 'G9', sel: '[data-heldout-verdict-text]', textVar: 'VD',
    verbatim: "new RegExp('对 ' + AX_KEYS.length + ' 条命名轴').test(VD)",
    mut: `T.replace('对 ' + AX_KEYS.length + ' 条命名轴', '对 ' + (AX_KEYS.length + 2) + ' 条命名轴')` },
];

// ---- 第二组：verify_axis_readout.mjs（⚠ 每个文件的元素选择器与 textVar 都不同）----
const SPECS2 = [
  { id: 'C1', file: AXR_, sel: '[data-axis]', textVar: 'P.text',
    verbatim: "P.text.includes('对照') && P.text.includes('step_frac')",
    // ⚠ C1/C2 读的是**整块面板**的 innerText（haystack 很大）⇒ 这是本组最值得测的
    mut: `T.split('step_frac').join('那个量')` },
  { id: 'C2', file: AXR_, sel: '[data-axis]', textVar: 'P.text',
    verbatim: "P.text.includes('搜索') || P.text.includes('付过钱')",
    mut: `T.split('搜索').join('筛选').split('付过钱').join('给过费')` },
  { id: 'D2', file: AXR_, sel: '[data-axis-row="reasoning"] [data-verdict]', textVar: 'posText',
    verbatim: "!posText.includes('token 局部')",
    // ⚠ 否定性断言：必须**注入**才验得了；否则它被平凡满足
    mut: `T + '（注入：token 局部）'` },
  { id: 'D3', file: AXR_, sel: '[data-axis-row="confidence"] [data-verdict]', textVar: 'confText',
    verbatim: "confText.includes('token 局部')",
    mut: `T.split('token 局部').join('整段局部')` },
  { id: 'D5', file: AXR_, sel: '[data-retraction]', textVar: 'P.retraction',
    verbatim: "P.retraction.includes('已撤回') && P.retraction.includes('0.3341') && P.retraction.includes('0.3077')",
    mut: `T.replace('0.3341', '0.3342')` },
  { id: 'D6-caution', file: AXR_, sel: '[data-spec-note="caution"]', textVar: 'printed',
    verbatim: "!!sp && !!printed && printed === String(sp.note).replace(/\\s+/g, ' ').trim()",
    mut: `T.replace('0.5537', '0.5538')`,
    extras: { sp: AXT.axes.caution.specificity } },
];
for (const x of SPECS2) x.file = x.file || VER;
// ⚠⚠⚴ 容器级扰动（C1/C2 动的是 [data-axis] 整块面板）会**重建整棵子树**：
//   `el.innerText = x` 会重新解析出**新节点**，而这些节点不被 React 持有；
//   React 下一次 reconcile 会把它们清掉 ⇒ 排在后面的判据读到的是**被冲掉的结构**。
//   ⚠ 本轮就是这样：D2/D3/D6 读到 null，害我差点误判成「D2 被平凡满足」。
//   ⇒ 处置：① 容器级 spec 排到最后  ② 跑完一个就**重新导航**再继续。
const LEAF2 = SPECS2.filter(x => x.sel !== '[data-axis]');
const CONT2 = SPECS2.filter(x => x.sel === '[data-axis]');
for (const x of CONT2) x.reloadAfter = true;
const ALL = SPECS.concat(LEAF2, CONT2);

// ---- 反漂移守卫：谓词必须逐字出自已提交判据文件 ----
// ⚠ 比对前**折叠空白**：判据里的谓词在源文件里是**跨行**的（`&& ` 换行续写），
//   而本台按单行写片段。折叠只抹掉换行/缩进，**表达式内容一个字符都不放松**
//   ⇒ 改表达式仍会被抓住；只改排版不会（这是有意的代价，已写明）。
// ⚠ 首版就是没折叠 ⇒ 守卫**当场拦下**（`找不到 E1b 的谓词原文 ⇒ 本台已漂移`），
//   这正是守卫该有的行为：宁可拒绝发布，也不默默测一个对不上的东西。
const norm = s => s.replace(/\s+/g, ' ');
const SRC_CACHE = {};
const srcOf = f => (SRC_CACHE[f] ??= norm(readFileSync(f, 'utf8')));
// 基线绑定的名字表（全部来自产物，**不写死**）
const BASE = ['gNewClean', 'gNewWeak', 'gGreedy', 'gWorst', 'sameRows', 'mLo', 'mHi', 'AX_KEYS'];
const BASEVAL = () => [gNewClean, gNewWeak, gGreedy, gWorst, sameRows, mLo, mHi, AX_KEYS];

const rows = [];
for (const sp of ALL) {
  sp.file = sp.file || VER;          // ⚠ 第一组不带 file（默认 verify_heldout）
  if (!srcOf(sp.file).includes(norm(sp.verbatim)))
    die(`${sp.file.split('/').pop()} 里找不到 ${sp.id} 的谓词原文 ⇒ 本台已漂移，拒绝发布`);
  sp.expr = norm(sp.verbatim).split(sp.textVar).join('T');
  const names = BASE.concat(Object.keys(sp.extras || {}));
  const mk = body => new Function('T', ...names, body);
  sp.judge = mk('return (' + sp.expr + ');');
  // ⚠ 变异式也要真的能改到东西（否则「转红」是因为别的理由）
  sp.mutFn = mk('return ' + sp.mut + ';');
  sp.args = () => BASEVAL().concat(Object.values(sp.extras || {}));
}
const byFile = {};
for (const sp of ALL) (byFile[sp.file.split('/').pop()] ??= []).push(sp.id);
for (const [f, ids] of Object.entries(byFile))
  console.log(`[自证] ${ids.length} 条谓词逐字出自 ${f}（折叠空白后比对）：${ids.join(' ')}`);
console.log('[自证] textVar→T 是机械替换，谓词本身未重写');

const { proc, version } = await launch({
  port: PORT, userDataDir: '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_r125_' + process.pid,
  windowSize: '1700,1200', url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);


try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 60000).catch(() => {});
  await sleep(13000);

  console.log('\n=== 逐条：真实绿 → 同句改错转红 → 还原重新变绿 ===\n');
  for (const s of ALL) {
    const read = `(() => { const e = document.querySelector(${JSON.stringify(s.sel)});`
      + ` return e ? (e.innerText || '').replace(/\\s+/g,' ').trim() : null; })()`;
    const real = await page.eval(read);
    if (!real || real.length < 10) {
      console.log(`[FAIL] ${s.id}：${s.sel} 读不到东西（${JSON.stringify(real)}）`);
      die('⚠ 若前面跑过容器级扰动，先怀疑**结构被 innerText 重建后又被 React 清掉**，'
        + '而不是先怀疑页面 —— 本轮就为这个差点误判 D2。');
    }

    const okReal = s.judge(real, ...s.args());
    const mutated = s.mutFn(real, ...s.args());

    // ⚠ DOM 级扰动：**把 innerText 改掉并回读**，
    //   判定用的是**回读到的 dom.now**，不是 JS 里那个 mutated 字符串。
    // ⚠⚴ 首版判的是 mutated（JS 串）⇒ 那测的是「我的字符串」，不是页面。
    //   浏览器可能规范化空白 ⇒ mutated 与 dom.now 可以不同，
    //   而「转红」若出于后者，原因就与「判据有没有牙齿」无关了。
    //   ⇒ 必须判 dom.now，且断言 dom.now 逐字等于 mutated（落地不保真 ⇒ 本条作废）。
    const dom = JSON.parse(await page.eval(`(() => {
      const e = document.querySelector(${JSON.stringify(s.sel)});
      if (!e) return JSON.stringify({missing:true});
      const before = (e.innerText||'').replace(/\\s+/g,' ').trim();
      e.innerText = ${JSON.stringify(mutated)};
      const now = (e.innerText||'').replace(/\\s+/g,' ').trim();
      const changed = now !== before;
      e.innerText = ${JSON.stringify(real)};
      const back = (e.innerText||'').replace(/\\s+/g,' ').trim();
      return JSON.stringify({changed, now, back, ok: back === before});
    })()`));
    if (dom.missing) die(`${s.id} 的元素在扰动前消失`);
    if (!dom.changed) die(`${s.id} 的变异**没有改到 DOM 上** ⇒ 转红原因不明，本条作废`);
    if (dom.now !== mutated) {
      die(`${s.id}：DOM 回读值与预期变异串**不同** ⇒ 落地不保真，本条作废\n`
        + `     预期 ${JSON.stringify(mutated.slice(0, 60))}\n`
        + `     实得 ${JSON.stringify(dom.now.slice(0, 60))}`);
    }
    const okMut = s.judge(dom.now, ...s.args());      // ⚠ 判 DOM 回读值，不是 JS 串
    const okBack = s.judge(dom.back, ...s.args());

    const pass = okReal && okMut === false && okBack && dom.ok;
    rows.push({ id: s.id, okReal, okMut, domOk: dom.ok, pass });
    console.log(`  ${s.id.padEnd(4)} 真实绿=${okReal ? '✓' : '✗'}`
      + `  同句改错转红=${okMut === false ? '✓' : '✗ 竟然绿'}`
      + `  还原回读=${dom.ok && okBack ? '✓' : '✗'}`
      + `  落地保真=${dom.now === mutated ? '✓' : '✗'}`
      + `  文字 ${real.length} 字 → 变异后 ${dom.now.length} 字`);
  }

  // ---------- 容器级扰动之后必须重新导航（否则后面读到的是被 React 清掉的结构）----------
  if (ALL[ALL.length - 1] && ALL[ALL.length - 1].reloadAfter) {
    console.log('\n[重载] 最后一条是容器级扰动 ⇒ 重新导航后再做污染对照');
    await page.send('Page.navigate', { url: URL });
    await page.waitForEvent('Page.loadEventFired', 60000).catch(() => {});
    await sleep(13000);
  }

  // ---------- 污染对照：改**别的**元素，全部判据必须**仍然绿** ----------
  console.log('\n=== 污染对照：改一个与判据无关的元素 ===');
  const poll = JSON.parse(await page.eval(`(() => {
    const h = document.querySelector('[data-heldout]');
    const cands = [...h.querySelectorAll('p, div, span')].filter(x => {
      const t = (x.innerText||'').trim();
      return t.length > 6 && t.length < 120
        && !/命名轴|逐行独立估计|补进来|greedy 估法|判成同一条方向|余量 ≈|可注入/.test(t);
    });
    const e = cands[0];
    if (!e) return JSON.stringify({skipped:true});
    const before = e.innerText;
    e.innerText = before + '（污染对照：这段文字与任何判据无关）';
    return JSON.stringify({touched:(e.innerText||'').slice(0,50),
      verdict:(document.querySelector('[data-heldout-verdict-text]')?.innerText||'')
                .replace(/\\s+/g,' ').trim(),
      notClaimed:(document.querySelector('[data-heldout-not-claimed]')?.innerText||'')
                .replace(/\\s+/g,' ').trim(),
      transfer:(document.querySelector('[data-block="transfer"]')?.innerText||'')
                .replace(/\\s+/g,' ').trim(),
      axis:(document.querySelector('[data-axis]')?.innerText||'')
                .replace(/\\s+/g,' ').trim(),
      retraction:(document.querySelector('[data-retraction]')?.innerText||'')
                .replace(/\\s+/g,' ').trim()});
  })()`));
  if (poll.skipped) {
    console.log('  ⚠ 找不到可污染的元素 ⇒ 本项未判，不发布');
  } else {
    console.log('  动的是：「' + poll.touched.slice(0, 40) + '…」');
    let allGreen = true;
    for (const s of ALL) {
      const t = s.sel === '[data-heldout-verdict-text]' ? poll.verdict
              : s.sel === '[data-heldout-not-claimed]' ? poll.notClaimed
              : s.sel === '[data-block="transfer"]' ? poll.transfer
              : s.sel === '[data-axis]' ? poll.axis
              : s.sel === '[data-retraction]' ? poll.retraction
              : null;
      if (t == null) continue;                 // 面板外的元素（recipe / selfdup）未污染
      const ok = s.judge(t, ...s.args());
      if (!ok) allGreen = false;
      console.log(`    ${s.id.padEnd(4)} ${ok ? '仍绿 ✓' : '红 ✗ 它不该红'}`);
    }
    if (!allGreen) die('改无关元素就让某条判据转红 ⇒ 仪器在喊叫而不是在测量');
    console.log('  ⇒ 受污染覆盖的判据全部仍绿 ✓');
  }

  const bad = rows.filter(r => !r.pass);
  console.log('\nRESULT ' + (bad.length ? 'FAIL' : 'PASS') + '  ' + (rows.length - bad.length) + '/' + rows.length
    + '（真实绿 + 同句改错转红 + 还原回读，三道同时成立才算过）');
  if (bad.length) console.log('  ⚠ 未过：' + bad.map(r => r.id).join('、'));
  console.log('\n⚠ 口径：这是**页面实例级**扰动。');
  console.log('⚠ 它证明「判据读的就是读者看到的那句话」；');
  console.log('⚠ **不**证明「组件写错时一定红」—— 那要改源码 + 重建。');
} catch (e) {
  die('装置错：' + String(e && e.message ? e.message : e));
} finally {
  try { await cdp.send('Browser.close'); } catch {}
  try { proc.kill(); } catch {}
}