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

  // ---------- F 组：可见性 ----------
  // 加这组是因为截图打脸过一次：判据全绿，但 Δ=20 与「最强对手」被裁掉了。
  const bad = (P.over || []).filter(o => o.rowOver > 1 || o.cellClip > 1 || o.spill > 1);
  check('F1 每一行都不横向溢出，也没有单元格被内部截断',
    Array.isArray(P.over) && P.over.length === truth.rows.length + truth.transfer.length
    && bad.length === 0,
    bad.length
      ? bad.map(o => `${o.key} 行溢${o.rowOver}/格裁${o.cellClip}/越界${o.spill}`).join('；')
      : `${(P.over || []).length} 行全部无溢出`);
} catch (e) {
  check('装置', false, String(e && e.message ? e.message : e));
} finally {
  try { await cdp.send('Browser.close'); } catch {}
  try { proc.kill(); } catch {}
}

const failed = results.filter(r => !r.ok);
console.log(`\nRESULT ${failed.length ? 'FAIL' : 'PASS'} ${results.length - failed.length}/${results.length}`);
process.exit(failed.length ? 1 : 0);
