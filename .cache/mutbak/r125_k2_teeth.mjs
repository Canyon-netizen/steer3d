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

// ---- 待验判据：每条的 `verbatim` 必须逐字出现在已提交的 verify_heldout.mjs 里 ----
// textVar = 谓词里那个「页面文字」变量的名（机械替换成 T，不重新实现谓词）
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

// ---- 反漂移守卫：谓词必须逐字出自已提交判据文件 ----
// ⚠ 比对前**折叠空白**：判据里的谓词在源文件里是**跨行**的（`&& ` 换行续写），
//   而本台按单行写片段。折叠只抹掉换行/缩进，**表达式内容一个字符都不放松**
//   ⇒ 改表达式仍会被抓住；只改排版不会（这是有意的代价，已写明）。
// ⚠ 首版就是没折叠 ⇒ 守卫**当场拦下**（`找不到 E1b 的谓词原文 ⇒ 本台已漂移`），
//   这正是守卫该有的行为：宁可拒绝发布，也不默默测一个对不上的东西。
const norm = s => s.replace(/\s+/g, ' ');
const src = readFileSync(VER, 'utf8');
const srcN = norm(src);
const rows = [];
for (const s of SPECS) {
  if (!srcN.includes(norm(s.verbatim))) die(`verify_heldout.mjs 里找不到 ${s.id} 的谓词原文 ⇒ 本台已漂移，拒绝发布`);
  s.expr = norm(s.verbatim).split(s.textVar).join('T');
  s.judge = new Function('T', 'gNewClean', 'gNewWeak', 'gGreedy', 'gWorst',
    'sameRows', 'mLo', 'mHi', 'AX_KEYS', 'return (' + s.expr + ');');
  // ⚠ 变异式也要真的能改到东西（否则「转红」是因为别的理由）
  s.mutFn = new Function('T', 'gNewClean', 'gNewWeak', 'gGreedy', 'gWorst',
    'sameRows', 'mLo', 'mHi', 'AX_KEYS', 'return ' + s.mut + ';');
}
console.log('[自证] ' + SPECS.length + ' 条谓词逐字出自 ' + VER.split('/').pop()
  + '（折叠空白后比对）；textVar→T 是机械替换，谓词本身未重写');

const { proc, version } = await launch({
  port: PORT, userDataDir: '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_r125_' + process.pid,
  windowSize: '1700,1200', url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);

const ARGS = () => [gNewClean, gNewWeak, gGreedy, gWorst, sameRows, mLo, mHi, AX_KEYS];

try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 60000).catch(() => {});
  await sleep(13000);

  console.log('\n=== 逐条：真实绿 → 同句改错转红 → 还原重新变绿 ===\n');
  for (const s of SPECS) {
    const read = `(() => { const e = document.querySelector(${JSON.stringify(s.sel)});`
      + ` return e ? (e.innerText || '').replace(/\\s+/g,' ').trim() : null; })()`;
    const real = await page.eval(read);
    if (!real || real.length < 10) die(`${s.id} 在 ${s.sel} 上读不到东西（${JSON.stringify(real)}）`);

    const okReal = s.judge(real, ...ARGS());
    const mutated = s.mutFn(real, ...ARGS());

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
    const okMut = s.judge(dom.now, ...ARGS());      // ⚠ 判 DOM 回读值，不是 JS 串
    const okBack = s.judge(dom.back, ...ARGS());

    const pass = okReal && okMut === false && okBack && dom.ok;
    rows.push({ id: s.id, okReal, okMut, domOk: dom.ok, pass });
    console.log(`  ${s.id.padEnd(4)} 真实绿=${okReal ? '✓' : '✗'}`
      + `  同句改错转红=${okMut === false ? '✓' : '✗ 竟然绿'}`
      + `  还原回读=${dom.ok && okBack ? '✓' : '✗'}`
      + `  落地保真=${dom.now === mutated ? '✓' : '✗'}`
      + `  文字 ${real.length} 字 → 变异后 ${dom.now.length} 字`);
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
                .replace(/\\s+/g,' ').trim()});
  })()`));
  if (poll.skipped) {
    console.log('  ⚠ 找不到可污染的元素 ⇒ 本项未判，不发布');
  } else {
    console.log('  动的是：「' + poll.touched.slice(0, 40) + '…」');
    let allGreen = true;
    for (const s of SPECS) {
      const t = s.sel === '[data-heldout-verdict-text]' ? poll.verdict
              : s.sel === '[data-heldout-not-claimed]' ? poll.notClaimed
              : s.sel === '[data-block="transfer"]' ? poll.transfer
              : null;
      if (t == null) continue;                 // 面板外的元素（recipe / selfdup）未污染
      const ok = s.judge(t, ...ARGS());
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