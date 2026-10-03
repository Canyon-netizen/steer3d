import { readFileSync } from 'node:fs';
import { launch, Page, CDP } from './cdp_client.mjs';

/**
 * 判据：4 条命名轴之外还剩多少方向（SubspacePanel）。
 *
 * 与 verify_axis_readout.mjs 同一个原则：
 *   判据主体是**页面上读者看到的那段文字**；`data-*` 只用来交叉核对
 *   「属性说的」与「印出来的」。外部真值取磁盘上的 readable_subspace.json。
 *
 * 这块面板的价值全在**三样并排的东西**上，所以 B/C 组专门守它们：
 *   · 地板（打乱后还能预测多少）—— 缺了它 0.86 只是好看
 *   · 同表最高的别人 —— 缺了它一条方向可能不是自己的读出（caution 就这么塌的）
 *   · 位置轴对照不衰减 —— 缺了它「六条都塌」和「装置测不出持续方向」分不开
 * 把任何一栏删掉，页面照样渲染、看起来完全正常，B/C 组会红。
 */
const URL = process.env.BV_URL || 'http://127.0.0.1:10410/';
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_sub_' + process.pid;
const sleep = ms => new Promise(r => setTimeout(r, ms));

const truth = JSON.parse(readFileSync(
  '/Users/zhourui/code/steer3d/frontend/public/latent/data/readable_subspace.json', 'utf8'));
const ROWS = truth.surface_directions.map(r => r.key);

const results = [];
const check = (name, ok, detail) => {
  results.push({ name, ok: !!ok });
  console.log(`[${ok ? 'PASS' : 'FAIL'}] ${name}: ${detail}`);
};

const { proc, version } = await launch({
  port: 9486, userDataDir: PROFILE, windowSize: '1700,1300', url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  await sleep(12000);

  const root = await page.eval(`(() => {
    const el = document.querySelector('[data-subspace]');
    if (!el) return JSON.stringify({missing: true});
    const r = el.getBoundingClientRect();
    return JSON.stringify({
      present: true, state: el.getAttribute('data-subspace'),
      w: Math.round(r.width), h: Math.round(r.height),
      lowerBound: el.getAttribute('data-lower-bound'),
      namedAxes: el.getAttribute('data-named-axes'),
      nRows: el.getAttribute('data-n-rows'),
      headline: (el.querySelector('[data-headline-verdict]')?.innerText || '').trim(),
      dn: el.querySelector('[data-cos-digit-newline]')?.getAttribute('data-cos-digit-newline'),
      dnText: (el.querySelector('[data-cos-digit-newline]')?.innerText || '').trim(),
      verdict: (el.querySelector('[data-verdict]')?.innerText || '').trim(),
      notClaimed: (el.querySelector('[data-not-claimed]')?.innerText || '').trim(),
      ctrlRow: el.querySelector('[data-control-row]')?.getAttribute('data-control-row'),
      ctrlText: (el.querySelector('[data-control-row]')?.innerText || '').trim(),
      ctrlVal: el.querySelector('[data-control-delta="100"]')
        ?.getAttribute('data-control-value'),
    });
  })()`);
  const P = JSON.parse(root);

  check('A1 面板已就绪且有非零包围盒',
    P.present && P.state === 'ready' && P.w > 0 && P.h > 0,
    `state=${P.state} ${P.w}x${P.h}px`);

  check('A2 下界与命名轴数都印出且与产物一致',
    Number(P.lowerBound) === truth.headline.readable_directions_lower_bound
    && Number(P.namedAxes) === truth.headline.named_axes
    && Number(P.nRows) === truth.surface_directions.length,
    `下界 ${P.lowerBound} / 命名轴 ${P.namedAxes} / 行数 ${P.nRows}`);

  // A3：下界必须**大于**命名轴数，而且这个比较要出现在**可见文字**里。
  // 写成 data-lower-bound=4 页面照样渲染，但结论就反了。
  const dn = String(truth.char_pairwise_abs_cos['digit_mass|newline_mass']);
  check('A3 「不是一条轴」的结论印在可见文字里，且数字↔换行余弦与产物一致',
    P.headline.includes(String(truth.headline.readable_directions_lower_bound))
    && P.dn === dn && P.dnText.includes(Number(dn).toFixed(4)),
    `属性 ${P.dn} / 文字「${P.dnText}」/ 产物 ${dn}`);

  for (const key of ROWS) {
    const r = truth.surface_directions.find(x => x.key === key);
    const got = JSON.parse(await page.eval(`(() => {
      const row = document.querySelector('[data-subspace-row="${key}"]');
      if (!row) return JSON.stringify({missing: true});
      const g = n => {
        const e = row.querySelector('[data-guard="${key}-' + n + '"]');
        return e ? { attr: e.querySelector('[data-value]')?.getAttribute('data-value'),
                    text: (e.innerText || '').replace(/\\s+/g, ' ').trim() } : null;
      };
      const cells = {};
      row.querySelectorAll('[data-delta-cell]').forEach(e => {
        const d = e.getAttribute('data-delta-cell').split('-').pop();
        cells[d] = { attr: e.querySelector('[data-delta-value]')?.getAttribute('data-delta-value'),
                     text: (e.innerText || '').replace(/\\s+/g, ' ').trim() };
      });
      return JSON.stringify({
        diag: g('diag'), floor: g('floor'), offdiag: g('offdiag'), cells,
        decay: row.querySelector('[data-decay-value]')?.getAttribute('data-decay-value'),
        maxAxis: row.querySelector('[data-kind="max-axis"]')?.getAttribute('data-value'),
        text: (row.innerText || '').replace(/\\s+/g, ' ').trim(),
      });
    })()`));

    // B1：三栏都在，且属性与可见文字**都**与产物一致。
    // 只查属性会漏掉「文案撒谎、属性诚实」——上一轮变异 M3 专打这一条。
    const want = {
      diag: r.diagnostic.diagonal, floor: r.diagnostic.floor,
      offdiag: r.diagnostic.offdiag_worst,
    };
    const names = { diag: '自己', floor: '地板', offdiag: '同表最高别人' };
    for (const n of ['diag', 'floor', 'offdiag']) {
      const ok = got[n]
        && Number(got[n].attr) === want[n]
        && got[n].text.includes(want[n].toFixed(4));
      check(`B1 ${key} ${names[n]} 栏 属性与文字都与产物一致`, ok,
        got[n] ? `属性 ${got[n].attr} / 文字「${got[n].text}」/ 产物 ${want[n]}`
               : '整栏缺失');
    }

    const dOk = ['0', '20', '100'].every(dd =>
      got.cells[dd] && Number(got.cells[dd].attr) === r.delta[dd]
      && got.cells[dd].text.includes(r.delta[dd].toFixed(4)));
    check(`B2 ${key} Δ=0/20/100 三个格 属性与文字都与产物一致`, dOk,
      ['0', '20', '100'].map(dd => got.cells[dd] ? `Δ${dd}=${got.cells[dd].attr}` : `Δ${dd}缺`).join(' '));

    check(`B3 ${key} 衰减倍数与对命名轴的最高 cos 都印出且一致`,
      Number(got.decay) === r.decay_x20
      && Number(got.maxAxis) === r.diagnostic.max_cos_to_named
      && got.text.includes(`${r.decay_x20}×`),
      `衰减 ${got.decay}（产物 ${r.decay_x20}）/ maxAxis ${got.maxAxis}（产物 ${r.diagnostic.max_cos_to_named}）`);
  }

  // C 组：位置轴对照 —— 没有它，「六条都塌」和「装置测不出持续方向」是同一个现象
  // C0 补这条是因为第一版 M3 只把 data-control-row 改成 "removed" 而没真删那一块，
  // 而 C1/C2 当时只按里面的 span 读 ⇒ 判据全绿。**变异绿 = 变异没落在判据读的路径上。**
  check('C0 对照行必须被标记为对照（data-control-row="true"）',
    P.ctrlRow === 'true', `data-control-row=${P.ctrlRow}`);

  check('C1 位置轴对照行必须在页面上，且 Δ=100 的数与产物一致',
    !!P.ctrlText && P.ctrlVal === String(truth.control.delta['100'])
    && P.ctrlText.includes(Number(truth.control.delta['100']).toFixed(4)),
    `属性 ${P.ctrlVal} / 产物 ${truth.control.delta['100']}`);

  check('C2 对照必须被说明是「装置能测出持续方向」的证据',
    P.ctrlText.includes('几乎不塌'),
    P.ctrlText.slice(0, 70) || '（对照行没有印出来）');

  check('C3 判决与「不是因果性」的边界都必须印在可见文字里',
    P.verdict.includes('非循环') && P.verdict.includes('专属')
    && P.notClaimed.includes('可读性') && P.notClaimed.includes('因果性')
    && P.notClaimed.includes('GPU'),
    `判决 ${P.verdict.length} 字 / 边界「${P.notClaimed.slice(0, 40)}」`);
} catch (e) {
  check('装置', false, String(e && e.message ? e.message : e));
} finally {
  try { await cdp.send('Browser.close'); } catch {}
  try { proc.kill(); } catch {}
}

const failed = results.filter(r => !r.ok);
console.log(`\nRESULT ${failed.length ? 'FAIL' : 'PASS'} ${results.length - failed.length}/${results.length}`);
process.exit(failed.length ? 1 : 0);
