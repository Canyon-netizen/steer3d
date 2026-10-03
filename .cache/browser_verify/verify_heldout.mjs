import { readFileSync } from 'node:fs';
import { launch, Page, CDP } from './cdp_client.mjs';

/**
 * 判据：这套判据在**没参与过调参**的观测量上还灵吗（HeldoutPanel）。
 *
 * 沿用前两个判据的原则：
 *   判据主体是**页面上读者看到的那段文字**；`data-*` 只用来交叉核对
 *   「属性说的」与「印出来的」。外部真值取磁盘上的 heldout_readability.json。
 *
 * 这一块有三处是专门为**已经犯过的错**加的，不要删：
 *
 *  1. B3 —— 上一轮 §4.9.1 的「倍数」列是手算的，写成 128/113/110×，
 *     而正确值是 128.6/112.3/244.4×（把三条地板混着当分母了）。
 *     ⇒ 这里在判据里**独立复算** |ρ|÷|地板|，页面上写错一个数就红。
 *     只比对产物的 ratio 字段不够：那正是手算错时一起错的东西。
 *
 *  2. C4 —— Δ=20 对三个留出量**根本没测**。渲染成 0.0000 的话，
 *     「没测」与「测出零」在页面上是同一个数。
 *     ⇒ 产物为 null 的行必须显示「未测」，且**不得带 data-value**。
 *
 *  3. C5 —— 只查属性会漏掉「文案撒谎、属性诚实」。
 *
 * 另外 D4 是一次对照：§4.9.2 里 0.9839 那个数只印在脚本 stdout 上，
 * 没有产物。若不做「逐轨迹平均 vs 整段拼接」的对照，
 * 那个数可能只是跨轨迹拼接造出来的伪影。
 */
const URL = process.env.BV_URL || 'http://127.0.0.1:10462/';
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_heldout_' + process.pid;
const sleep = ms => new Promise(r => setTimeout(r, ms));

const truth = JSON.parse(readFileSync(
  '/Users/zhourui/code/steer3d/frontend/public/latent/data/heldout_readability.json', 'utf8'));
// 第十八笔：not_claimed 里那七个数（2 / 12 / 14 / 20 / 0.5 / 0.45 / 退回几条）
// 的源是**另外两份产物**。判据必须自己把它们读进来现算，
// 而不是拿 truth 里的散文去和 truth 里的结构比对 —— 那只能证明自洽。
const DATA_D = '/Users/zhourui/code/steer3d/frontend/public/latent/data/';
const SUB = JSON.parse(readFileSync(DATA_D + 'readable_subspace.json', 'utf8'));
const AXR = JSON.parse(readFileSync(DATA_D + 'axis_readouts.json', 'utf8'));
const AX_KEYS = Object.keys(AXR.axes || {});

const results = [];
const check = (name, ok, detail) => {
  results.push({ name, ok: !!ok });
  console.log(`[${ok ? 'PASS' : 'FAIL'}] ${name}: ${detail}`);
};

const near = (a, b, eps = 1e-9) => Number.isFinite(a) && Math.abs(a - b) <= eps;

const { proc, version } = await launch({
  port: 9487, userDataDir: PROFILE, windowSize: '1700,1700', url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});


  // ---- X0 存活前置 + 早退出（§8.9 第十笔）----
  //   死 URL 上「先崩再判红」会污染判红计数，所以这里判红就立刻退出，
  //   让「一条都没跑」与「跑红了几条」在自报里彻底分开。
  //   ⚠ 这一段在九个脚本里各有一份**逐字相同**的副本，而不是抽共享模块 ——
  //     共享模块放在 .cache/ 下会被 .gitignore 排除，而这九个脚本是**已跟踪**的，
  //     让它们 import 一个进不了仓库的文件 ⇒ 新克隆直接跑不起来；
  //     而按规矩不 force-add，所以只能就地内联。
  //     代价是九份副本会漂移 —— 已用 scan_live_blocks.py 把「九份必须逐字相同」
  //     做成会变红的判据（与第八笔「表格 0.35→9 vs 散文 0.35→7」同一族的处置：
  //     重复必须可核，而不是靠自觉）。
  //   ⚠ 阈值只到「页面在」这一步，**不含「数据取回来了」** ——
  //     Next 取数完成前的外壳只有 bodyLen≈1190，而本条在导航后立刻跑；
  //     越权到数据就绪的结果不是更严，是误报（我第一版在活页面上判过红）。
  {
    const L = JSON.parse(await page.eval(`(() => JSON.stringify({
      href: location.href,
      bodyLen: (document.body.innerText || '').length,
      outcome: (document.querySelector('[data-outcome]') || {getAttribute: () => ''})
                 .getAttribute('data-outcome') || '',
      canvases: document.querySelectorAll('canvas').length,
      scripts: document.querySelectorAll('script[src]').length,
    }))()`));
    const isErr = /^chrome-(error|extension)/.test(String(L.href));
    const isLoopback = /^https?:\/\/127\.0\.0\.1:\d+\//.test(String(L.href));
    const liveOk = isLoopback && L.bodyLen > 0 && L.scripts >= 1;
    check('X0 页面必须真的加载出来（死 URL 不得让本脚本报 PASS/SKIP）', liveOk,
      `href=${L.href} bodyLen=${L.bodyLen} `
      + `data-outcome="${L.outcome}" canvas=${L.canvases} script[src]=${L.scripts}`
      + (isErr ? '  ← chrome-error 页：继续跑下去只会崩，红的计数会被污染'
               : (!isLoopback ? '  ← 不是 127.0.0.1 的页面（环境变量传错了？）' : '')));
    if (!liveOk) {
      try { cdp.close(); } catch {}
      try { proc.kill('SIGKILL'); } catch {}
      console.log(`\n=== 0/${results.length} passed ===`);
      console.log('页面没加载 ⇒ 后面的判据**一条都没跑**（这不是「通过」，也不是「装置崩」）');
      process.exit(1);
    }
  }
  await sleep(12000);

  const root = await page.eval(`(() => {
    const el = document.querySelector('[data-heldout]');
    if (!el) return JSON.stringify({missing: true});
    const r = el.getBoundingClientRect();
    const sd = el.querySelector('[data-selfdup-verdict]');
    return JSON.stringify({
      present: true, state: el.getAttribute('data-heldout'),
      w: Math.round(r.width), h: Math.round(r.height),
      total: el.getAttribute('data-heldout-total'),
      transferTargets: el.getAttribute('data-transfer-targets'),
      sameDir: el.getAttribute('data-same-direction'),
      newClean: el.getAttribute('data-new-clean'),
      newWeak: el.getAttribute('data-new-weak'),
      ratioMin: el.getAttribute('data-ratio-min'),
      ratioMax: el.getAttribute('data-ratio-max'),
      nRows: el.getAttribute('data-n-rows'),
      headline: (el.querySelector('[data-heldout-headline]')?.innerText || '').trim(),
      verdict: (el.querySelector('[data-heldout-verdict-text]')?.innerText || '').trim(),
      notClaimed: (el.querySelector('[data-heldout-not-claimed]')?.innerText || '').trim(),
      dupText: (sd ? sd.innerText : '').replace(/\\s+/g, ' ').trim(),
      dupVerdict: sd?.getAttribute('data-selfdup-verdict'),
      dupSame: sd?.getAttribute('data-selfdup-same'),
      dupLag1: sd?.getAttribute('data-selfdup-lag1'),
      dupPerTraj: sd?.getAttribute('data-selfdup-per-traj'),
      dupNTraj: sd?.getAttribute('data-selfdup-n-traj'),
      dupCellSame: (sd?.querySelector('[data-selfdup-cell="same"]')?.innerText || '').trim(),
      dupCellLag1: (sd?.querySelector('[data-selfdup-cell="lag1"]')?.innerText || '').trim(),
      dupCellPer: (sd?.querySelector('[data-selfdup-cell="per-traj"]')?.innerText || '').trim(),
      // F 组：可见性。第一版判据 50/50 全绿，而截图里 emitted_tok_len 那一行的
      // 「最强对手 digit_frac_top64」和几行的 Δ=20 **已经被侧栏宽度裁掉了**。
      // ⇒ 数值在 DOM 里 ≠ 读者看得见。这里同时量两种溢出：
      //   rowOver  整行横向溢出
      //   cellClip 单元格内部内容超出自己的盒子（truncate / nowrap 裁切）
      //   spill    单元格右缘越过面板右缘
      over: (() => {
        const pr = el.getBoundingClientRect();
        return [...el.querySelectorAll('[data-transfer-row], [data-heldout-row]')]
          .map(r => {
            const cells = [...r.querySelectorAll('[data-kind]')];
            const right = cells.length
              ? Math.max(...cells.map(c => c.getBoundingClientRect().right)) : 0;
            return {
              key: r.getAttribute('data-transfer-row') || r.getAttribute('data-heldout-row'),
              rowOver: Math.round(r.scrollWidth - r.clientWidth),
              cellClip: Math.round(Math.max(0, ...cells.map(
                c => c.scrollWidth - c.clientWidth))),
              spill: Math.round(right - pr.right),
            };
          });
      })(),
    });
  })()`);
  const P = JSON.parse(root);

  check('A1 面板已就绪且有非零包围盒',
    P.present && P.state === 'ready' && P.w > 0 && P.h > 0,
    `state=${P.state} ${P.w}x${P.h}px`);

  check('A2 四个计数与行数都与产物一致',
    Number(P.total) === truth.headline.heldout_total
    && Number(P.transferTargets) === truth.headline.transfer_targets
    && Number(P.sameDir) === truth.headline.same_direction
    && Number(P.newClean) === truth.headline.new_clean
    && Number(P.newWeak) === truth.headline.new_weak
    && Number(P.nRows) === truth.rows.length,
    `总数 ${P.total} / 迁移 ${P.transferTargets} / 同向 ${P.sameDir} / 新(净) ${P.newClean} / 新(弱) ${P.newWeak} / 行 ${P.nRows}`);

  // A3：结论必须印在**可见文字**里，不只是属性。
  const rMin = Math.round(truth.headline.ratio_min);
  const rMax = Math.round(truth.headline.ratio_max);
  check('A3 headline 文字里印出倍数区间与「新方向」计数',
    P.headline.includes(String(rMin)) && P.headline.includes(String(rMax))
    && P.headline.includes(String(truth.headline.new_clean + truth.headline.new_weak))
    && P.headline.includes('新方向'),
    `文字「${P.headline}」/ 期望含 ${rMin} ${rMax} ${truth.headline.new_clean + truth.headline.new_weak}`);

  check('A4 倍数区间属性等于产物原值（不是取整值）',
    near(Number(P.ratioMin), truth.headline.ratio_min)
    && near(Number(P.ratioMax), truth.headline.ratio_max),
    `属性 ${P.ratioMin}–${P.ratioMax} / 产物 ${truth.headline.ratio_min}–${truth.headline.ratio_max}`);

  // ---------- B 组：① 迁移 ----------
  check('B0 三个迁移目标都印在页面上',
    truth.transfer.length === 3,
    `产物 ${truth.transfer.length} 个：${truth.transfer.map(t => t.target).join(', ')}`);

  for (const t of truth.transfer) {
    const got = JSON.parse(await page.eval(`(() => {
      const row = document.querySelector('[data-transfer-row="${t.target}"]');
      if (!row) return JSON.stringify({missing: true});
      const g = k => row.querySelector('[data-kind="' + k + '"]');
      const v = k => g(k)?.getAttribute('data-value');
      const x = k => (g(k)?.innerText || '').trim();
      return JSON.stringify({
        rho: v('rho'), floor: v('floor'), ratio: v('ratio'),
        rhoText: x('rho'), floorText: x('floor'), ratioText: x('ratio'),
      });
    })()`));

    // B3 在最前面：独立复算，不信产物的 ratio 字段。
    // 上一轮页面上写 110× 而产物是 244.4× 时，只有这条会红。
    const want = Math.abs(t.rho) / Math.abs(t.floor);
    const attrOk = near(Number(got.ratio), want, 1e-9) && near(Number(got.rho), t.rho, 1e-9)
      && near(Number(got.floor), t.floor, 1e-9);
    check(`B3 ${t.target} 倍数=|ρ|÷|地板| 独立复算一致`, attrOk && near(want, t.ratio, 1e-9),
      `复算 ${want.toFixed(1)}× / 产物 ${Number(t.ratio).toFixed(1)}× / 属性 ${got.ratio}`);

    check(`B2 ${t.target} ρ 与地板 属性+文字 都与产物一致`,
      got.rhoText.includes(Number(t.rho).toFixed(4))
      && got.floorText.includes(Number(t.floor).toFixed(4))
      && got.ratioText.includes(`${Number(t.ratio).toFixed(1)}×`),
      `ρ「${got.rhoText}」/ 地板「${got.floorText}」/ 倍数「${got.ratioText}」`);
  }

  const transferBlock = await page.eval(`(() => {
    const el = document.querySelector('[data-block="transfer"]');
    return JSON.stringify({ text: (el?.innerText || '').replace(/\\s+/g, ' ').trim() });
  })()`);
  const TB = JSON.parse(transferBlock);
  check('B4 必须写明「倍数分母逐行独立估计」',
    TB.text.includes('逐行独立估计') && TB.text.includes('自己的打乱地板'),
    TB.text.slice(-70) || '（迁移块没有印出来）');

  // ---------- C 组：② 归属 ----------
  for (const r of truth.rows) {
    const got = JSON.parse(await page.eval(`(() => {
      const row = document.querySelector('[data-heldout-row="${r.key}"]');
      if (!row) return JSON.stringify({missing: true});
      const g = k => row.querySelector('[data-kind="' + k + '"]');
      const d20 = row.querySelector('[data-kind="delta20"]');
      const d20m = row.querySelector('[data-kind="delta20-missing"]');
      return JSON.stringify({
        verdict: row.getAttribute('data-heldout-verdict'),
        verdictText: (g('verdict-text')?.innerText || '').trim(),
        margin: g('margin')?.getAttribute('data-value'),
        marginText: (g('margin')?.innerText || '').replace(/\\s+/g, ' ').trim(),
        worst: g('worst-other')?.getAttribute('data-value'),
        worstText: (g('worst-other')?.innerText || '').replace(/\\s+/g, ' ').trim(),
        d20: d20?.getAttribute('data-value'),
        d20Text: (d20?.innerText || '').trim(),
        d20Missing: (d20m?.innerText || '').trim(),
      });
    })()`));

    check(`C1 ${r.key} 判定属性与产物一致`,
      got.verdict === r.verdict,
      `属性 ${got.verdict} / 产物 ${r.verdict}`);

    // C5：属性绿、文字错 —— 只查属性会漏
    const vWord = r.verdict === 'same_direction' ? '同一个方向'
      : r.verdict === 'new_clean' ? '新方向（干净）' : '新方向（弱）';
    check(`C5 ${r.key} 判定文字与属性一致`, got.verdictText === vWord,
      `文字「${got.verdictText}」/ 期望「${vWord}」`);

    // 余量独立复算
    const wantMargin = r.rho_self / Math.abs(r.worst_other_value);
    check(`C2 ${r.key} 余量独立复算且属性+文字一致`,
      near(Number(got.margin), r.margin, 1e-9) && near(wantMargin, r.margin, 1e-9)
      && got.marginText.includes(`余量 ${Number(r.margin).toFixed(2)}×`),
      `复算 ${wantMargin.toFixed(3)} / 产物 ${Number(r.margin).toFixed(3)} / 文字「${got.marginText}」`);

    check(`C3 ${r.key} 最强对手与产物一致`,
      near(Number(got.worst), r.worst_other_value, 1e-9)
      && got.worstText.includes(r.worst_other),
      `属性 ${got.worst}（产物 ${r.worst_other_value}）/ 文字「${got.worstText}」`);

    // C4：未测必须显示「未测」且不带 data-value；测了的必须属性+文字都对
    if (r.rho_delta20 === null) {
      check(`C4 ${r.key} Δ=20 产物为 null ⇒ 必须显示「未测」且无 data-value`,
        got.d20 === undefined && got.d20Missing.includes('未测'),
        `data-value=${got.d20} / 文字「${got.d20Missing || got.d20Text}」`);
    } else {
      check(`C4 ${r.key} Δ=20 属性+文字都与产物一致`,
        near(Number(got.d20), r.rho_delta20, 1e-9)
        && got.d20Text.includes(Number(r.rho_delta20).toFixed(4)),
        `属性 ${got.d20} / 文字「${got.d20Text}」/ 产物 ${r.rho_delta20}`);
    }
  }

  // ---------- D 组：③ 自我纠正 ----------
  const S = truth.selfdup;
  check('D1 自我纠正块的属性与产物一致',
    P.dupVerdict === S.verdict
    && near(Number(P.dupSame), S.pooled.same_step, 1e-9)
    && near(Number(P.dupLag1), S.pooled.lag1, 1e-9)
    && near(Number(P.dupPerTraj), S.per_traj_mean.same_step, 1e-9)
    && Number(P.dupNTraj) === S.n_traj,
    `verdict ${P.dupVerdict} / 同一步 ${P.dupSame} / 错开 ${P.dupLag1} / 逐轨迹 ${P.dupPerTraj} / 轨迹 ${P.dupNTraj}`);

  check('D2 同一步与错开一步两个数都印在可见文字里',
    P.dupCellSame.includes(Number(S.pooled.same_step).toFixed(4))
    && P.dupCellLag1.includes(Number(S.pooled.lag1).toFixed(4)),
    `同一步「${P.dupCellSame}」/ 错开「${P.dupCellLag1}」`);

  check('D3 必须印出「就是同一个观测量」这个结论',
    P.dupText.includes('就是同一个观测量') && P.dupText.includes('设计失误'),
    P.dupText.slice(0, 60) || '（自我纠正块没有印出来）');

  // D4：对照口径。差得远 ⇒ 那个数是跨轨迹拼接造出来的，不能上页面。
  const drift = Math.abs(S.pooled.same_step - S.per_traj_mean.same_step);
  check('D4 逐轨迹平均与整段拼接接近 ⇒ 不是拼接伪影',
    P.dupCellPer.includes(Number(S.per_traj_mean.same_step).toFixed(4)) && drift < 0.01,
    `页面逐轨迹格「${P.dupCellPer || '（空）'}」/ 逐轨迹 ${S.per_traj_mean.same_step.toFixed(4)} / 拼接 ${S.pooled.same_step.toFixed(4)} / 差 ${drift.toFixed(4)}`);

  check('D5 同一步远高于错开一步（这条数才有信息）',
    S.pooled.same_step - S.pooled.lag1 > 0.5,
    `落差 ${(S.pooled.same_step - S.pooled.lag1).toFixed(4)}`);

  // ---------- E 组：边界 ----------
  // E1 第一版写成「判决段里同时出现『非循环』与『余量』」，判红。
  // 查下来是**守卫问错了地方**，不是产品回归：「非循环」住在 headline 段，
  // 「余量」住在判决段，面板本来就是分开印的。
  // 但不能顺手放宽成「在页面任意地方出现即可」——那等于不查。
  // 真正要守的是：**两个结论必须分属不同元素，不能被合成一句**。
  check('E1 迁移结论与归属结论都印出，且分属两个不同元素',
    P.headline.includes('非循环') && P.verdict.includes('余量')
    && P.headline !== P.verdict && P.verdict.length > P.headline.length,
    `headline「${P.headline.slice(0, 28)}…」(${P.headline.length}字) / 判决「${P.verdict.slice(0, 28)}…」(${P.verdict.length}字)`);

  check('E1b 判决段必须同时包含「迁移」与「归属」两侧的措辞',
    P.verdict.includes('①') && P.verdict.includes('②')
    && P.verdict.includes('数字内容') && P.verdict.includes('同一条方向的重新构造'),
    P.verdict.slice(0, 80) || '（判决没有印出来）');

  check('E2 边界必须写明「可读性 ≠ 因果性」且指出下界已从 12 抬到 14',
    P.notClaimed.includes('可读性') && P.notClaimed.includes('因果性')
    && P.notClaimed.includes('下界') && P.notClaimed.includes('14')
    && P.notClaimed.includes('12') && P.notClaimed.includes('门槛'),
    `边界 ${P.notClaimed.length} 字`);

  // ---------- G 组：跨产物那七个数，以及「同向行」的账 ----------
  // 第十八笔的起点：not_claimed 里「门槛 0.45 就退回 12 条」这句话
  // 混了**两个估计量**。头条「至少 14 条」用的是 perm_min（第十五笔确认），
  // 同一口径下 0.45 那一档是 **11**；12 是那一档的 greedy 估法。
  // ⇒ 一句「退回 12 条」在同屏上与 SubspacePanel 的敏感性表
  //   （0.45 → 「12 条（随机顺序 11–12）」）并排出现，读者无法分辨说的是哪个。
  const sh = SUB.headline, sens = sh.threshold_sensitivity;
  const selKey = Object.keys(sens).find(
    k => Math.abs(Number(k) - Number(sh.separation_threshold)) < 1e-12);
  const underKeys = Object.keys(sens).filter(k => Number(k) < Number(selKey));
  const worstKey = underKeys.sort((a, b) => Number(b) - Number(a))[0];   // 紧邻的下一档
  const gOld = sh.readable_directions_lower_bound_old;
  const gNew = sh.readable_directions_lower_bound;
  const gCand = sh.n_candidates;
  const gThr = sh.separation_threshold;
  const gWorst = sens[worstKey].perm_min;
  const gGreedy = sens[worstKey].greedy;
  const gPermRange = `${sens[worstKey].perm_min}–${sens[worstKey].perm_max}`;
  const NC = P.notClaimed || '', VD = P.verdict || '';
  const gNewClean = truth.headline.new_clean, gNewWeak = truth.headline.new_weak;

  check('G0 前置：选定门槛在敏感性表里，且「紧邻的下一档」存在',
      !!selKey && underKeys.length > 0 && sens[selKey].perm_min === gNew,
      `选定门槛=${selKey}（表键 ${selKey}）perm_min=${sens[selKey].perm_min} 头条=${gNew}`
      + ` | 下一档=${worstKey} perm_min=${gWorst} greedy=${gGreedy} 随机顺序=${gPermRange}`);

  // ⚠ 七个数逐个用**带词锚点**的正则取，不许 includes('14')：
  //   E2 就是 includes('14')/includes('12')，而 '12' 在这段文字里出现多次
  //   （12→14 的 12、0.45 退回的 12、20 个候选、0.5）⇒ 改对了仍会绿。
  check('G1 not_claimed 的「补进来 N 条」与 headline 的干净+弱一致',
      new RegExp('补进来 ' + (gNewClean + gNewWeak) + ' 条').test(NC),
      `现算 ${gNewClean} + ${gNewWeak} = ${gNewClean + gNewWeak}；`
      + `原文片段：${(NC.match(/补进来[^，。]*/) || ['<没抓到>'])[0]}`);

  check('G2 「下界从 A 抬到 B」必须等于 readable_subspace 的 old/lower_bound',
      new RegExp('从 ' + gOld + ' 抬到 \\*\\*' + gNew + '\\*\\*').test(NC),
      `现算 old=${gOld} new=${gNew}；原文：${(NC.match(/下界因此从[^（]*/) || ['<没抓到>'])[0]}`);

  check('G3 「N 个候选、|cos|<T」必须等于 readable_subspace 的 n_candidates / 选定门槛',
      new RegExp('\\*\\*' + gNew + '\\*\\*（' + gCand + ' 个候选、\\|cos\\|<' + gThr + '）').test(NC),
      `现算 n_candidates=${gCand} 选定门槛=${gThr}；`
      + `原文：${(NC.match(/\*\*\d+\*\*（[^）]*）/) || ['<没抓到>'])[0]}`);

  // ---- 本笔的核心：0.45 那一句必须落在**同一个**估计量上 ----
  check('G4 「门槛 X 就退回 N 条」必须用 perm_min 口径，且必须与 perm_min 现算一致',
      new RegExp('门槛 ' + worstKey + ' 就退回 \\*\\*' + gWorst + '\\*\\* 条').test(NC)
      && new RegExp('同一 perm_min 口径').test(NC),
      `现算：门槛 ${worstKey} → perm_min ${gWorst}（greedy 给 ${gGreedy}，perm ${gPermRange}）`
      + `；原文：${(NC.match(/门槛 [\d.]+ 就退回[^）]*）/) || ['<没抓到>'])[0]}`);

  check('G5 两种估计量不许被混用：下一档 greedy 的数必须与 perm_min **不同**才值得说明',
      gGreedy !== gWorst && new RegExp('greedy 估法给 ' + gGreedy).test(NC)
      && /不是一回事/.test(NC),
      gGreedy === gWorst
        ? `⚠ 下一档的 greedy(${gGreedy}) 与 perm_min(${gWorst}) 相同 ⇒ 那句话已成赘述`
        : `greedy=${gGreedy} vs perm_min=${gWorst}，原文已分别印出并说「不是一回事」`);

  // ---- 「N 个同向」的账：判决里原来写「其中三个」，而表里有 4 行同向 ----
  const sameRows = truth.rows.filter(r => r.verdict === 'same_direction');
  const mLo = Math.min(...sameRows.map(r => r.margin));
  const mHi = Math.max(...sameRows.map(r => r.margin));
  const transferKeys = truth.transfer.map(t => t.target);
  const fromNewFam = sameRows.filter(r => !transferKeys.includes(r.key));
  check('G6 判决里的「N 个判成同一条方向」必须等于 rows 里 same_direction 的行数',
      new RegExp('把 ' + sameRows.length + ' 个判成同一条方向').test(VD)
      && new RegExp('另 ' + (gNewClean + gNewWeak) + ' 个才是新方向').test(VD)
      && sameRows.length + gNewClean + gNewWeak === truth.rows.length,
      `现算 same_direction=${sameRows.length}、新方向=${gNewClean + gNewWeak}、`
      + `rows 共 ${truth.rows.length} 行；原文：${(VD.match(/专属性把[^，]*/) || ['<没抓到>'])[0]}`);

  check('G7 同向行的余量区间必须等于那些行余量的 min–max（不许写死「≈ 1.0×」）',
      new RegExp('余量 ≈ ' + mLo.toFixed(2) + '–' + mHi.toFixed(2) + '×').test(VD),
      `现算 min–max = ${mLo.toFixed(4)}–${mHi.toFixed(4)}；`
      + `原文：${(VD.match(/余量 ≈ [\d.]+–[\d.]+×/) || ['<没抓到>'])[0]}`);

  // ---- 那个「没被判决提到」的行必须被点名，并说清它为什么同向 ----
  const sdSame = truth.selfdup.pooled.same_step;
  check('G8 同向行里来自新家族的那一条必须被点名，且它的「同一个观测量」证据'
      + '必须等于 selfdup 的 same_step（不许只写一个 r）',
      fromNewFam.length === 1
      && new RegExp(fromNewFam[0].key).test(VD)
      && new RegExp('同一步 r = ' + sdSame.toFixed(3)).test(VD)
      && new RegExp('不是「换函数形式」那 ' + transferKeys.length + ' 个').test(VD),
      `现算：同向 ${sameRows.length} 行里来自新家族的是 ${fromNewFam.map(r => r.key).join() || '（无）'}`
      + `，transfer 名单 ${transferKeys.length} 条，same_step=${sdSame.toFixed(6)}`);

  // ---- 命名轴条数：判据不许拿 named_axis_readouts 的长度冒充轴数 ----
  check('G9 「对 N 条命名轴」里的 N 必须等于 axis_readouts 的轴数'
      + '（不是 named_axis_readouts 的长度——那个只有表面方向那几条）',
      sh.named_axes === AX_KEYS.length
      && new RegExp('对 ' + AX_KEYS.length + ' 条命名轴').test(VD)
      && new RegExp('对 ' + sh.named_axes + ' 条命名轴').test(VD)
      && SUB.named_axis_readouts.length !== AX_KEYS.length,
      `axis_readouts 实际 ${AX_KEYS.length} 条（${AX_KEYS.join()}）`
      + `；readable_subspace.named_axes=${sh.named_axes}`
      + `；named_axis_readouts.length=${SUB.named_axis_readouts.length}（**不是轴数**）`
      + `；原文：${(VD.match(/对 \d+ 条命名轴/) || ['<没抓到>'])[0]}`);

  // ---------- F 组：可见性 ----------
  // 加这组是因为截图打脸过一次：判据全绿，但 Δ=20 与「最强对手」被裁掉了。
  const bad = (P.over || []).filter(o => o.rowOver > 1 || o.cellClip > 1 || o.spill > 1);
  check('F1 每一行都不横向溢出，也没有单元格被内部截断',
    Array.isArray(P.over) && P.over.length === truth.rows.length + truth.transfer.length
    && bad.length === 0,
    bad.length
      ? bad.map(o => `${o.key} 行溢${o.rowOver}/格裁${o.cellClip}/越界${o.spill}`).join('；')
      : `${(P.over || []).length} 行全部无溢出`);

  // ---------- I 组：④「可读 ≠ 有配方 ≠ 可注入」 ----------
  // 这一块存在是因为上面把 emitted_is_upper 标成「新方向（干净）」，
  // 读者很容易理解成「那是一条可以拿去注入的轴」—— 而第三关没过。
  const R = truth.recipe;
  const rc = JSON.parse(await page.eval(`(() => {
    const el = document.querySelector('[data-block="recipe"]');
    // ⚠ 缺失分支也必须给 cells / verdict 一个空对象：
    //   否则下面的 rc.cells['caution-axis'] 抛 TypeError，被外层 catch 记成
    //   「装置错」，I3/I4/I5 一条都跑不到 —— 看着像「只有 3 条红」。
    if (!el) return JSON.stringify({missing: true, cells: {}, verdict: '', text: '', margPara: '', swapPara: '', variants: {missing: true, text: ''}});
    const box = el.getBoundingClientRect();
    const cells = [...el.querySelectorAll('[data-recipe-cell]')];
    return JSON.stringify({
      text: (el.innerText || '').replace(/\\s+/g, ' ').trim(),
      loo: el.getAttribute('data-recipe-loo'),
      floor: el.getAttribute('data-recipe-floor'),
      margin: el.getAttribute('data-recipe-margin'),
      cos: el.getAttribute('data-recipe-selfcheck-cos'),
      cells: Object.fromEntries(cells.map(c => [c.getAttribute('data-recipe-cell'),
        // ⚠ ?? 和 || 混用**必须**加括号，否则整个 eval 抛 SyntaxError，
        //   外层 catch 把它记成「装置错」，I 组后面几条一条都跑不到。
        { attr: (c.getAttribute('data-value') ?? (c.innerText || '')).trim(),
          text: (c.innerText || '').trim() }])),
      verdict: (el.querySelector('[data-recipe-verdict]')?.innerText || '').trim(),
      // ⚠ 那两段以前没人读。单独再 eval 一次取它们，第一版返回全 null
      //   （而探针已证明两个 data-* 都在页面上）⇒ 装置自己的问题。
      //   正确做法是把选择器并进**这一次** eval。
      margPara: (el.querySelector('[data-marg-para]')?.innerText || '').trim(),
      swapPara: (el.querySelector('[data-swap-para]')?.innerText || '').trim(),
      variants: (() => {
        const v = el.querySelector('[data-recipe-variants]');
        if (!v) return { missing: true, text: '', rows: [] };
        return {
          best: v.getAttribute('data-best-margin'),
          threshold: v.getAttribute('data-clean-threshold'),
          swapped: v.getAttribute('data-binding-swapped'),
          text: (v.innerText || '').replace(/\\s+/g, ' ').trim(),
          rows: [...v.querySelectorAll('[data-variant-row]')].map(li => ({
            name: li.getAttribute('data-variant-row'),
            margin: li.getAttribute('data-variant-margin'),
            tie: li.getAttribute('data-variant-tie'),
            worst: li.getAttribute('data-variant-worst'),
            text: (li.innerText || '').replace(/\\s+/g, ' ').trim(),
          })),
        };
      })(),
      rowOver: Math.round(el.scrollWidth - el.clientWidth),
      cellClip: Math.round(Math.max(0, ...cells.map(c => c.scrollWidth - c.clientWidth))),
      spill: Math.round(Math.max(0, ...cells.map(c => c.getBoundingClientRect().right))
                        - box.right),
    });
  })()`));

  check('I1 配方块存在，留一 rho / 地板 / 专一余量 属性+文字 都与产物一致',
    !rc.missing
    && near(Number(rc.loo), R.loo_rho, 1e-9) && near(Number(rc.floor), R.loo_floor, 1e-9)
    && near(Number(rc.margin), R.specificity_margin, 1e-9)
    && rc.cells.loo?.text.includes(R.loo_rho.toFixed(4))
    && (rc.text || '').includes(R.loo_floor.toFixed(4))
    && rc.cells.entropy?.text.includes(R.recipe_loo_on_entropy.toFixed(4))
    && rc.cells.margin?.text.includes(R.specificity_margin.toFixed(2)),
    rc.missing ? '整块缺失'
      : `loo ${rc.loo} / 地板 ${rc.floor} / 余量 ${rc.margin} / 格 ${Object.keys(rc.cells).join(',')}`);

  check('I2 配方自证 cos 必须印出且等于产物（复制来的配方要先复现已存在的向量）',
    near(Number(rc.cos), R.selfcheck_cos, 1e-9)
    && (rc.text || '').includes(R.selfcheck_cos.toFixed(9)),
    `页面 cos ${rc.cos} / 产物 ${R.selfcheck_cos}`);

  check('I3 「轴 ≠ 读出」必须印出，且两个 cos 都要在（0.73 那个数极易被误读）',
    (rc.text || '').includes('轴 ≠ 读出')
    && rc.cells['caution-axis']?.text.includes(R.cos_recipe_vs_caution_axis.toFixed(4))
    && rc.cells['caution-readout']?.text.includes(R.cos_recipe_vs_caution_readout.toFixed(4)),
    `轴 ${rc.cells['caution-axis']?.text} / 读出 ${rc.cells['caution-readout']?.text}`);

  check('I4 判决必须显式写「可注入 ✗」，不能只印正面的数',
    (rc.verdict || '').includes('可读') && (rc.verdict || '').includes('有配方')
    && (rc.verdict || '').includes('可注入')
    && /可注入\s*[✗✘×x]/.test(rc.verdict || ''),
    `判决「${rc.verdict || '（没有印出来）'}」`);

  check('I5 配方块不横向溢出、单元格不被内部截断',
    rc.rowOver <= 1 && rc.cellClip <= 1 && rc.spill <= 1,
    `行溢${rc.rowOver}/格裁${rc.cellClip}/越界${rc.spill}`);

  // I6 每个变体必须印出三样：余量、**谁在约束**、这个归属分不分得开。
  //    只查余量不够 —— 两个竞争者并列时 max 选中谁是任意的，
  //    只印余量会把「并列」印成「结论」。
  const V = rc.variants || {};
  const vRows = V.rows || [];
  check('I6 三个变体的余量 / 约束方 / tie 标记与产物逐项一致',
    near(Number(V.best), R.best_margin, 1e-9)
    && near(Number(V.threshold), R.clean_threshold, 1e-9)
    && R.variants.every(v => {
      const r = vRows.find(x => x.name === v.name);
      return r && near(Number(r.margin), v.margin, 1e-9)
        && r.worst === v.worst_name
        && r.tie === String(v.tie)
        && r.text.includes(v.worst_rho.toFixed(3))
        && r.text.includes(v.margin.toFixed(2))
        // tie 的行必须说清「并列 + 差多少 sem」，非 tie 的必须说清「领先多少 sem」
        && (v.tie
          ? r.text.includes('并列') && r.text.includes(v.gap_over_sem.toFixed(2))
          : r.text.includes(v.gap_over_sem.toFixed(1)));
    }),
    V.missing ? '变体块缺失'
      : vRows.map(r => `${r.name}:${r.margin}/${r.worst}/tie=${r.tie}`).join(' ')
        + ` | 产物 ${R.variants.map(v => `${v.name}:${v.margin.toFixed(4)}/${v.worst_name}/tie=${v.tie}`).join(' ')}`);

  // I7 对照组：余量全 < 1 是事实，但**约束方换过人**这件事必须一起印出来。
  //    少了后半句，读者会得出「caution 的配方方向本来就是熵的」——
  //    而这正是这一轮推翻的东西：朴素时熵只领先 1.7 sem（不显著），
  //    去混杂后约束方确定地变成 emitted_is_upper。
  check('I7 对照组三个余量全 < 1，且「约束方从熵换成 is_upper」必须印在页面上',
    R.control_self_check.every(v => v.margin < 1)
    && String(R.control_binding_swapped) === V.swapped
    && (V.text || '').includes('emitted_is_upper')
    && (V.text || '').includes('1.7')
    && (V.text || '').includes('不能说'),
    `产物 swapped=${R.control_binding_swapped} / 页 data-binding-swapped=${V.swapped} / `    + R.control_self_check.map(v => `${v.name}=${v.margin.toFixed(3)} worst=${v.worst_name}(${v.gap_over_sem.toFixed(2)}sem)`).join(' '));

  // I9 那三个 sem 必须逐个来自产物，**不许判据自己写死**。
  //    I7 里那个 `.includes('1.7')` 就是反例：产品侧那几个数是写死的字面量，
  //    判据侧也写死，两边**互相背书** —— 产物一变，两边一起变成错的且没人红。
  //    那是 §8.3 ⑨ 的同一种病，只是长在判据上。
  const SW = { swap: rc.swapPara, marg: rc.margPara };
  const csc = R.control_self_check;
  const need = [
    ['朴素约束方名字', csc[0].worst_name],
    ['朴素 sem', csc[0].gap_over_sem.toFixed(1)],
    ['去混杂后约束方名字', csc[1].worst_name],
    ['去混杂后 sem1', csc[1].gap_over_sem.toFixed(1)],
    ['去混杂后 sem2', csc[2].gap_over_sem.toFixed(1)],
  ].filter(([, v]) => v != null);
  const miss = need.filter(([, v]) => !(SW.swap || '').includes(String(v)))
                 .map(([w]) => w);
  const margNeed = [
    ['best_margin', R.best_margin.toFixed(2)],
    ['clean_threshold', R.clean_threshold.toFixed(1)],
    ['own_change_pct', R.margin_gain_attribution.own_change_pct.toFixed(1)],
    ['worst_change_pct', Math.abs(R.margin_gain_attribution.worst_change_pct).toFixed(1)],
  ];
  const margMiss = margNeed.filter(([, v]) => !(SW.marg || '').includes(String(v)))
                     .map(([w]) => w);
  check('I9 「约束方换人」段的三个 sem 与约束方名字必须逐个来自产物（不许任何一边写死）',
    SW.swap != null && SW.marg != null && miss.length === 0 && margMiss.length === 0,
    (miss.length || margMiss.length)
      ? `swap 段缺：${miss.join('、') || '无'}；margin 段缺：${margMiss.join('、') || '无'}`
      : `逐个命中：${need.map(([, v]) => v).join(' / ')}`
        + `　margin 段：${margNeed.map(([, v]) => v).join(' / ')}`
        + `　⚠ I7 里的 includes('1.7') 是判据侧写死，将来应一并换成产物值`);

  // I8 涨幅归因：页面印的「N% 来自竞争者」必须等于产物，且自身涨幅也要印。
  //    不印这个分解，读者会把 1.15×→1.68× 的功劳记在配方结构上，
  //    而它几乎全是竞争者被压下去造成的。
  const A = R.margin_gain_attribution;
  const ownTxt = (V.text || '').match(/只涨\s*([\d.]+)%/)?.[1];
  const shareTxt = (V.text || '').match(/的\s*(\d+)%\s*来自竞争者/)?.[1];
  check('I8 余量涨幅归因：自身 +N% 与「M% 来自竞争者」都与产物一致',
    ownTxt != null && shareTxt != null
    && near(A.own_change_pct, Number(ownTxt), 0.05)
    && near(A.share_from_competitor, Number(shareTxt), 0.5),
    `产物 own+${A.own_change_pct.toFixed(1)}% competitor${A.worst_change_pct.toFixed(1)}% `
    + `share=${A.share_from_competitor.toFixed(1)}% / 页面读到 own=${ownTxt} share=${shareTxt}`);
} catch (e) {
  check('装置', false, String(e && e.message ? e.message : e));
} finally {
  try { await cdp.send('Browser.close'); } catch {}
  try { proc.kill(); } catch {}
}

const failed = results.filter(r => !r.ok);
console.log(`\nRESULT ${failed.length ? 'FAIL' : 'PASS'} ${results.length - failed.length}/${results.length}`);
process.exit(failed.length ? 1 : 0);
