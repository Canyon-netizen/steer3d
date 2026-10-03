// 验收：token 反向映射这一块在真实页面里。
//
// 判据要钉住的东西（都是这一轮真踩到的坑）：
//   1. 块真的渲染出来了，且**不是**被 catch 吞掉的空串。
//      页面有全局错误兜底，一个抛异常的 render 函数会让整块消失而页面照常。
//   2. 负面结果真的印在页面上：「零空间是空的」这件事如果不显示，
//      读者只会记住「我们把 token 映回去了」——那正是被推翻的说法。
//   3. 两种 regime 分开显示，且各带分母。合并成一个平均数会同时
//      稀释厚锥（2.20×）和夸大小锥的可移动性。
//   4. 实测网格的点数来自产物，不是插值出来的固定值。
//   5. 点了步按钮之后，网格必须真的换掉（DOM 判据不覆盖交互）。
//
// ⚠ 第二十一笔加的 B0 前置：先证明**页面连得上**，再谈块渲没渲染。
//   这一份的默认 URL 曾经指向一个早就没人监听的端口，不设环境变量直接跑
//   会得到 `data-bmroot 不存在` 的 0/8 —— 看上去像「这一块整块坏了」，
//   实际是我把环境变量给错了名（本文件读 LAT_URL，串联器给的是 T3D_URL）。
//   ⇒ **判红先怀疑判据**的又一条，而更一般的形态是：
//   「装置没到位」和「被测物坏了」必须分开，否则会有人去修一个没坏的东西。
//   连不上时本脚本**不报 N/M**，让串联器记成「一条都没跑」并整链非零退出；
//   报一个 0/14 才是撒谎 —— 那 14 条根本没有执行过。
import { launch, Page, CDP } from './cdp_client.mjs';
import { readFileSync } from 'node:fs';

const URL = process.env.LAT_URL || 'http://127.0.0.1:22113/latent/index.html';
const PROFILE = process.env.LAT_PROFILE
  || '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_bm';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const R = [];

function rec(name, pass, detail) {
  R.push({ name, pass });
  console.log(`[${pass ? 'PASS' : 'FAIL'}] ${name}\n       ${detail}`);
}

// ---- B0 可达性前置：不通过就不往下走 ----
let reachable = null;
try {
  const resp = await fetch(URL, { method: 'GET' });
  reachable = { ok: resp.ok, status: resp.status };
} catch (e) {
  reachable = { ok: false, status: String(e && e.message || e) };
}
if (!reachable.ok) {
  console.log(`[FAIL] B0 页面不可达 ⇒ **装置事故，不是被测物判红**`);
  console.log(`       URL = ${URL}  状态 = ${reachable.status}`);
  console.log(`       本文件的判据读 LAT_URL（不是 T3D_URL / BV_URL）。`);
  console.log(`       下面 14 条一条都没执行，所以**不报 N/M** ——`);
  console.log(`       报一个 0/N 会让「没跑」看起来像「跑了而且全红」。`);
  console.log(`\n=== unreached (LAT_URL=${URL}) ===`);
  process.exit(4);
}
console.log(`[PASS] B0 页面可达\n       ${URL} → ${reachable.status}`);
R.push({ name: 'B0 页面可达', pass: true });

const { proc, version } = await launch({
  port: 9411, userDataDir: PROFILE, windowSize: '1600,1000', url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);

try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  // 数据是 fetch 进来的，等它落地。这里等 block 出现，而不是等固定秒数——
  // 固定等待在慢机器上会假阴性，在快机器上白等。
  let waited = 0;
  let st = null;
  while (waited < 45000) {
    st = await page.eval(`(() => {
      const r = document.querySelector('[data-bmroot]');
      return r ? { has: true, len: r.innerHTML.length,
                   text: (r.innerText || '').slice(0, 4000) } : { has: false };
    })()`);
    if (st.has && st.len > 400) break;
    await sleep(1200);
    waited += 1200;
  }
  rec('B1 块渲染出来了（不是空串）', !!(st && st.has && st.len > 400),
      st && st.has ? `len=${st.len} waited=${waited}ms` : 'data-bmroot 不存在');

  const txt = (st && st.text) || '';

  /* ---------------------------------------------------- 负面结果必须显示 */
  rec('B2 页面上写了「零空间是空的」',
      /零空间/.test(txt) && /(空|不存在)/.test(txt),
      (txt.match(/.{0,40}零空间.{0,60}/) || ['<未找到>'])[0].replace(/\s+/g, ' '));

  rec('B3 印出了最小奇异值与条件数（可核对的数）',
      // 上一版只查 /4\.4/，而 4.4217 是 σ_min 的值：即使我把字段名写成
      // rk.condition（实际叫 rk.cond），σ_min 照样渲染出来，正则照样匹配，
      // 判据报 PASS 而页面上「条件数只有 —」。这里必须让条件数自己
      // 出现一个像样的数值（32.999… → 33.0），且秩的分母也必须在。
      /最小奇异值/.test(txt) && /条件数/.test(txt)
      && /最小奇异值\s*4\.42/.test(txt)
      && /条件数只有\s*3[0-9](\.[0-9])?/.test(txt)
      && /秩\s*2048\/2048/.test(txt),
      (txt.match(/最小奇异值[^。]{0,80}/) || ['<未找到>'])[0].replace(/\s+/g, ' '));

  /* ---------------------------------------------------- 两种 regime 分开 */
  const regimes = await page.eval(`(() => {
    const r = document.querySelector('[data-bmroot]');
    if(!r) return null;
    const rows = [...r.querySelectorAll('tr')].map(tr => tr.innerText.replace(/\\s+/g,' ').trim());
    return rows;
  })()`);
  const hasThick = regimes && regimes.some(r => /读出已指向该词/.test(r));
  const hasThin = regimes && regimes.some(r => /靠微调才指向该词/.test(r));
  rec('B4 厚锥/薄锥两行都在，且没有合并成一行平均',
      !!(hasThick && hasThin),
      (regimes || []).filter(r => /指向该词/.test(r)).join(' || ') || '<无>');

  rec('B5 两行都带分母（步数 + >1× 次数/总次数）',
      !!(hasThick && hasThin
         && /\d+\/\d+/.test(regimes.find(r => /读出已指向该词/.test(r)) || '')
         && /\d+\/\d+/.test(regimes.find(r => /靠微调才指向该词/.test(r)) || '')),
      (regimes || []).filter(r => /指向该词/.test(r)).join(' || '));

  /* ---------------------------------------------------- 实测网格 */
  const grid = await page.eval(`(() => {
    const r = document.querySelector('[data-bmroot]');
    if(!r) return null;
    const svg = r.querySelector('[data-bmgrid]');
    const n = r.querySelector('[data-bmgridn]');
    const rects = svg ? svg.querySelectorAll('rect').length : 0;
    return { hasSvg: !!svg, rects, declared: n ? n.textContent : null,
             w: svg ? svg.getBoundingClientRect().width : 0,
             h: svg ? svg.getBoundingClientRect().height : 0 };
  })()`);
  rec('B6 实测网格画出来了，且 rect 数 = 声明的采样点数',
      !!(grid && grid.hasSvg && grid.rects > 4
         && String(grid.rects) === String(grid.declared)),
      grid ? `rects=${grid.rects} declared=${grid.declared} size=${grid.w.toFixed(0)}x${grid.h.toFixed(0)}`
           : '无 svg');

  rec('B7 网格有实际像素高度（不是 0 高的隐形元素）',
      !!(grid && grid.h >= 30 && grid.w >= 150),
      grid ? `${grid.w.toFixed(0)}x${grid.h.toFixed(0)}` : '无');

  /* ---------------------------------------------------- 交互：点按钮要换图 */
  const before = await page.eval(`(() => {
    const s=document.querySelector('[data-bmgridn]');
    const r=document.querySelector('[data-bmroot]');
    return { n: s?s.textContent:null,
             step: (r.innerText.match(/第 (\\d+) 步/)||[])[1] || null };
  })()`);
  const clicked = await page.eval(`(() => {
    const bs=[...document.querySelectorAll('[data-bmstep]')];
    if(bs.length<2) return { n: bs.length };
    // 点一个黄区（需要 delta 的步），序号靠后
    bs[bs.length-1].click();
    return { n: bs.length, clicked: bs[bs.length-1].textContent };
  })()`);
  await sleep(1200);
  const after = await page.eval(`(() => {
    const s=document.querySelector('[data-bmgridn]');
    const r=document.querySelector('[data-bmroot]');
    // 读完整 innerText。上一版只取前 600 字符，而"并列"两个字落在
    // 步信息之后、网格之前 —— 600 字符窗口刚好把它切掉，判据于是
    // 报"页面没说并列"，实际页面说了。判据自己少读了字段，
    // 却报成产品缺陷。
    return { n: s?s.textContent:null,
             step: (r.innerText.match(/第 (\\d+) 步/)||[])[1] || null,
             txt: r.innerText };
  })()`);
  rec('B8 点步按钮后选中步真的变了',
      !!(before && after && after.step && before.step !== after.step),
      `before step=${before && before.step} -> after step=${after && after.step} (clicked ${clicked.clicked})`);

  /* ---------------------------------------------------- 边界必须如实说 */
  rec('B9 边界写明是「并列」而不是翻转',
      /并列/.test(after.txt || '') || /恰好为 0/.test(after.txt || ''),
      ((after.txt || '').match(/.{0,30}(并列|恰好为 0).{0,50}/) || ['<未找到>'])[0].replace(/\s+/g, ' '));

  rec('B10 说明了「词没变 ≠ logits 没变」',
      /logits 相对变化/.test(txt) || /读出没变/.test(txt),
      (txt.match(/.{0,25}logits 相对变化.{0,60}/) || ['<未找到>'])[0].replace(/\s+/g, ' '));

  /* ---------------------------------------------------- 无 console error */
  const errs = page.events
    .filter(e => e.method === 'Runtime.consoleAPICalled' && e.params.type === 'error')
    .map(e => (e.params.args || []).map(a => a.value ?? a.description ?? '').join(' '))
    .filter(t => !/favicon|Failed to load resource/i.test(t));
  rec('B11 页面无 console error', errs.length === 0,
      errs.length ? errs.slice(0, 2).join(' | ') : 'none');

  /* ---------------------------------------------------- 没有未替换的占位 */
  // 字段名写错时 nfmt(undefined) 返回 "—"，整块照常渲染、所有存在性
  // 判据都绿，只有数字是破折号。专门盯这个：任何「实测值」位置出现
  // —，都意味着取错了 key 而不是"这项没测到"。
  const dashes = await page.eval(`(() => {
    const r = document.querySelector('[data-bmroot]');
    if(!r) return null;
    const out = [];
    // 不按字符形态找破折号：innerText 会把 "——"（两个 U+2014）规范化成
    // "—" + 零宽字符，按正则区分"占位符"和"中文破折号"因此不可靠——
    // 上一版就是这么把 "0.20 倍——" 报成 nfmt 占位符的。
    //
    // 改成结构性判据：nfmt(undefined) 的输出是一个**孤立的 <b> 里只有破折号**，
    // 也就是"这一格该有数字却只有破折号"。真正的中文破折号在 </b> 之外。
    for(const b of r.querySelectorAll('b')){
      const t = (b.textContent || '').trim();
      if(t === '—' || t === '-' || t === '') out.push('<b>' + t + '</b> 紧邻：'
        + (b.previousSibling ? b.previousSibling.textContent.slice(-12) : '?'));
    }
    return out;
  })()`);
  rec('B12 实测值位置没有「—」（字段名取错会在这里露出来）',
      dashes !== null && dashes.length === 0,
      dashes && dashes.length ? dashes.join(' | ') : 'none');

  /* ---------------------------------------------------- 语义正确，不只存在 */
  // 前面几条盯的是"在不在、是不是空"，这一条盯"说的是不是对的"。
  // 真实事故：产物里字段叫 top64_denom，值是 151936（分母），
  // 页面直接拿它渲染成「用存下来的 top-151936 还原」——
  // 151936 正好是全词表数，而同一段上一句刚说全词表能精确还原，
  // 两句话自相矛盾。存在性判据全绿，文本也"有内容"。
  const semantics = await page.eval(`(() => {
    const r = document.querySelector('[data-bmroot]');
    if(!r) return null;
    const t = r.innerText;
    const i = t.indexOf('单位向量');
    const line = i >= 0 ? t.slice(i, i + 60) : '';
    return {
      hasTop64: /top-64/.test(t),
      // 「用存下来的 top-151936」这类拿分母冒充宽度的写法
      badTop: (t.match(/top-\\d+/g) || []).filter(x => x !== 'top-64'),
      sigmaLine: line,
      // 布尔判断放在页面侧算好再传出来。放到 Node 侧的话，
      // 这段正则要穿过「JS 模板字符串 -> 页面 eval -> 正则」两层转义，
      // 反斜杠层数一数错就静默失配 —— 判据报红而页面明明写着 4.4217。
      sigmaOk: /满足 .* 4\\.42/.test(line),
    };
  })()`);
  rec('B13 top-K 写的是真实截断宽度 64，不是分母 151936',
      !!(semantics && semantics.hasTop64 && semantics.badTop.length === 0),
      semantics ? `hasTop64=${semantics.hasTop64} 异常=${JSON.stringify(semantics.badTop)}`
                : '无块');

  rec('B14 「单位向量 n 满足 ‖W·n‖ ≥ 」后面是一个真实数值',
      !!(semantics && semantics.sigmaOk),
      semantics ? semantics.sigmaLine.replace(/\s+/g, ' ') : '无');

  /* ================= F 组：两段散文与它们的字段（第二十一笔） ================= */
  // ⚠ 先说层级，而且这一组**整组在产物层**。
  //   `post_norm_note` **全仓没有任何消费方**（既不渲染、也不进面板），
  //   `unembedding_note` 只出现在一个 title= 悬浮提示里，
  //   两者都不是读者看到的正文 ⇒ 这里不可能有渲染层判据。
  //   同样，B1–B14 是**渲染层**的，它们核的是页面上那 14 个数；
  //   F 组核的是**产物里**那两段散文。两者不互相顶替：
  //   「页面上的数对」不能替「散文里的数对」作证。
  //
  // 这一组存在的理由：`post_norm_note` 原来整段是**没有测量的断言**——
  //   "(measured max|diff| = 0)" 里 "measured" 承担了计算的工作，
  //   而 `build_token_backmap.py` 里 `last_hidden` 与 `max|diff|` 这两个
  //   词**只出现在这句字符串内部**，没有任何一行代码读它们；
  //   "worth 16-19 logits; see analyse_divergence_logits.py" 更是**假引用**：
  //   那个脚本把 "16-19" 在自己的散文里又抄了三遍，从未计算它。
  // ⇒ 判据要能抓住「散文说了什么」与「字段是什么」之间的分叉。
  const TB = JSON.parse(readFileSync(
    '/Users/zhourui/code/steer3d/frontend/public/latent/data/token_backmap.json', 'utf8'));
  const fPm = TB.postnorm_measured || {};
  const fNote = TB.post_norm_note || '';
  const fUnote = TB.unembedding_note || '';
  const fRank = (TB.aggregate || {}).rank || {};
  const fAgg = TB.aggregate || {};

  rec('F0 [产物层] 两段散文都存在，且 post_norm_measured 已就位（本组整组在产物层）',
      fNote.length > 0 && fUnote.length > 0
      && fPm.max_abs_diff_vs_last_hidden !== undefined
      && fPm.n_steps !== undefined,
      `post_norm_note ${fNote.length} 字、unembedding_note ${fUnote.length} 字；`
      + `postnorm_measured 键 ${Object.keys(fPm).length} 个。`
      + `两者都不作为可见正文渲染（前者无消费方，后者只在 title= 里）`);

  // F1：分母必须和这份产物其余部分同一个，否则「17 步」是另一个 17。
  rec('F1 [产物层] postnorm_measured 的分母 = aggregate.n_steps = steps.length',
      fPm.n_steps === fAgg.n_steps && fPm.n_steps === (TB.steps || []).length
      && fPm.renorm_argmax_flip_denom === fPm.n_steps,
      `postnorm_measured.n_steps=${fPm.n_steps}、`
      + `aggregate.n_steps=${fAgg.n_steps}、steps.length=${(TB.steps || []).length}；`
      + `flip 分母=${fPm.renorm_argmax_flip_denom}`);

  // F2 是这一组最要紧的一条：散文**声称**的那个事实必须真的成立。
  // 阴性结论要有分母 —— 「0 处不同」要说成「17 处里有 0 处不同」。
  rec('F2 [产物层] 「post-norm 且与 last_hidden 相同」必须真的成立，且带分母',
      fPm.max_abs_diff_vs_last_hidden === 0
      && fPm.n_diff_exactly_zero === fPm.n_steps
      && fPm.n_steps > 0
      && new RegExp('max deviation from last_hidden is 0').test(fNote)
      && new RegExp(fPm.n_diff_exactly_zero + ' of ' + fPm.n_steps + ' exactly 0')
            .test(fNote),
      `max|diff|=${fPm.max_abs_diff_vs_last_hidden}，`
      + `恰好为 0 的步数 ${fPm.n_diff_exactly_zero}/${fPm.n_steps}`);

  // F3：argmax 翻转是这批数字里最刺眼的一个，散文必须印出**带分母**的它。
  rec('F3 [产物层] argmax 翻转必须带分母印进散文，不许只印一个计数',
      fPm.renorm_argmax_flips > 0
      && fPm.renorm_argmax_flip_denom === fPm.n_steps
      && new RegExp('flipping the argmax on ' + fPm.renorm_argmax_flips
                    + ' of ' + fPm.renorm_argmax_flip_denom + ' steps').test(fNote),
      `翻转 ${fPm.renorm_argmax_flips}/${fPm.renorm_argmax_flip_denom}；`
      + `（阴性/阳性结论都必须带分母：「17 步全翻」与「翻了 17 次」不是同一句话）`);

  // F4：散文里印的量级必须等于字段，且**带词锚点**取数。
  // 第十八笔：光 includes('19.35') 会在同一段里另一个 19.35 出现时假绿。
  rec('F4 [产物层] 散文里印的 top1 logit 中位数 = 字段（带词锚点）',
      new RegExp('top-1 logit by a median of '
                 + fPm.renorm_delta_top1_logit_median.toFixed(2)).test(fNote)
      && new RegExp('margin by a median of '
                    + fPm.renorm_delta_margin_median.toFixed(3)).test(fNote),
      `字段中位数 top1=${fPm.renorm_delta_top1_logit_median.toFixed(2)}、`
      + `margin=${fPm.renorm_delta_margin_median.toFixed(3)}；`
      + `两个量级差 ${(fPm.renorm_delta_top1_logit_median
                     / fPm.renorm_delta_margin_median).toFixed(1)} 倍，`
      + `所以「worth N logits」必须说清是哪一个`);

  // F5：悬浮提示里的数不许与页面上可见的数分叉。
  // 两者同源于奇异值，但格式是各自写的；一边改了另一边不会跟。
  rec('F5 [产物层] unembedding_note 印的 sigma_min/cond 必须与页面取用的 rank 字段同值',
      fUnote.includes('sigma_min = ' + fRank.sigma_min.toFixed(6))
      && fUnote.includes('cond = ' + fRank.cond.toFixed(2)),
      `note: sigma_min=${fRank.sigma_min.toFixed(6)} cond=${fRank.cond.toFixed(2)}`
      + `；页面取 sigma_min=${fRank.sigma_min.toFixed(4)} cond=${fRank.cond.toFixed(1)}`
      + `（同一对数、两种位数，提示与正文各自格式化 ⇒ 正是会分叉的地方）`);

  // F6：独立复算 cond，不信「它自己说 cond = sigma_max/sigma_min」。
  rec('F6 [产物层] cond 必须真的等于 sigma_max / sigma_min（独立复算）',
      Math.abs(fRank.cond - fRank.sigma_max / fRank.sigma_min) < 1e-9
      && fRank.cond_denom === fRank.hidden
      && fRank.numerical_rank === fRank.hidden,
      `现算 ${(fRank.sigma_max / fRank.sigma_min).toFixed(9)} vs 字段 `
      + `${fRank.cond.toFixed(9)}；numerical_rank ${fRank.numerical_rank}/`
      + `${fRank.hidden}（满秩 ⇒ 零空间为空，页面上那句话的根据）`);

  // ⚠ F7 不能写 === ：两个字段在第 13 位上不同（4.421699266129733 vs
  //   4.4216992661298），那是一条 BLAS 路径的浮点残差。用绝对相等会
  //   得到一条永远红的判据 —— 而永远红的判据会被直接关掉。
  const fRel = Math.abs(fRank.min_wnorm_over_unit_n - fRank.sigma_min)
    / Math.abs(fRank.sigma_min);
  rec('F7 [产物层] min_wnorm_over_unit_n ≈ sigma_min（相对容差，不是绝对相等）',
      fRel < 1e-9 && fRank.min_wnorm_denom === 1,
      `min_wnorm=${fRank.min_wnorm_over_unit_n}、sigma_min=${fRank.sigma_min}、`
      + `相对差 ${fRel.toExponential(2)}（绝对相等在这里是错的）`);

  // F8 源级：假引用必须真的被删掉，而不是换个地方再抄一遍。
  //
  // ⚠ 第一版扫**整份源码**，判红了 4/5 —— 而那四个词都在我为了交代来历
  //   而写的**注释**里（引述了旧文案）。**判红先怀疑判据**：这条要防的是
  //   「有人把假引用重新打进会印出去的字符串」，不是「源码里不许提到这件事」。
  //   ⇒ 改成先剥 Python 行注释再扫，并**额外**直接扫产物里的那段散文
  //     （产物那一条没有假阳性的余地，它才是真正要守的东西）。
  const fStripPy = t => t.replace(/^\s*#.*$/gm, '');
  const fSrcRaw = readFileSync('/Users/zhourui/code/steer3d/backend/examples/'
    + 'build_token_backmap.py', 'utf8');
  const fSrc = fStripPy(fSrcRaw);
  const fBanned = ['16-19', '16–19', 'analyse_divergence_logits.py',
    'worth 16', 'measured max|diff| = 0'];
  const fHitSrc = fBanned.filter(s => fSrc.includes(s));
  const fHitArt = fBanned.filter(s => fNote.includes(s) || fUnote.includes(s));
  rec('F8 [源级] 剥注释后源码里没有「16-19」与假引用；产物两段散文里也没有',
      fHitSrc.length === 0 && fHitArt.length === 0,
      `源码（剥 # 注释后）残留 ${fHitSrc.length}/${fBanned.length}`
      + `${fHitSrc.length ? '：' + fHitSrc.join(' / ') : ''}；`
      + `产物残留 ${fHitArt.length}/${fBanned.length}`
      + `${fHitArt.length ? '：' + fHitArt.join(' / ') : ''}；`
      + `注释里保留旧文案 ${fBanned.filter(s => fSrcRaw.includes(s)).length} 处（有意留，`
      + `交代来历，不是会被印出去的东西）；`
      + `现算入口在位：postnorm_measured=${fSrc.includes('postnorm_measured')}、`
      + `read_steps 实测=${fSrc.includes('postnorm_diff.append')}`);

  const shot = await page.screenshot(
    '/Users/zhourui/code/steer3d/.cache/browser_verify/shots/backmap.png',
    { fullPage: true });
  console.log('\nscreenshot ->', shot);
} catch (e) {
  rec('X 脚本自身没跑完', false, String(e && e.stack || e).slice(0, 300));
} finally {
  cdp.close(); proc.kill('SIGKILL');
}

const pass = R.filter(r => r.pass).length;
console.log(`\n=== ${pass}/${R.length} passed ===`);
R.filter(r => !r.pass).forEach(r => console.log(`FAIL: ${r.name}`));
process.exit(pass === R.length ? 0 : 1);
