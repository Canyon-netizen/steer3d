// 验收：3D 页面上的「干预结果」面板（What the vector did）。
//
// 这块面板回答用户那句「告诉我向量到底是起到什么作用的」。它读的
// 是离线 32k 批次（cot_texts.json / answer_readout.json），不是本页
// 滑块的实时结果 —— 后者只推 3D 坐标、不改 token。
//
// 判据盯三件事，一件比一件难：
//  1. 面板在，且如实标注「离线、不是这个滑块」（G1/G2）
//  2. 屏幕上的每个数字与产物逐值相同（G3/G4）
//  3. 面板**没有**把循环论证当证据展示（G5）
//
// 第 3 条是这一块最容易犯的错：vector_roles.json 里
// `in_sample_circular` 的 passes_gate=true 看起来像个漂亮的 PASS，
// 但那个向量就是用这批 token 的分组均值差定义的，再拿回同一批
// token 与定义它的标签求相关 —— 通过与否是恒等式。渲染成 PASS 等于
// 把循环判定当发现。
import { launch, Page, CDP } from './cdp_client.mjs';
import { readFileSync } from 'node:fs';

const URL = process.env.T3D_URL || 'http://127.0.0.1:10100/';
const PROFILE = process.env.T3D_PROFILE
  || '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_outcome_' + process.pid;
const DATA = '/Users/zhourui/code/steer3d/frontend/public/latent/data';

const COT = JSON.parse(readFileSync(DATA + '/cot_texts.json', 'utf8'));
const ANS = JSON.parse(readFileSync(DATA + '/answer_readout.json', 'utf8'));
const ARM = JSON.parse(readFileSync(DATA + '/arm_asymmetry.json', 'utf8'));

const sleep = ms => new Promise(r => setTimeout(r, ms));
const R = [];
const rec = (n, p, d) => {
  R.push({ n, p });
  console.log(`[${p ? 'PASS' : 'FAIL'}] ${n}\n       ${d}`);
};

const { proc, version } = await launch({ port: 9450, userDataDir: PROFILE,
  windowSize: '1600,1000', url: 'about:blank' });
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);

try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});

  let mounted = false;
  for (let i = 0; i < 15; i++) {
    mounted = await page.eval(`!!document.querySelector('[data-outcome]')`);
    if (mounted) break;
    await sleep(1200);
  }
  rec('G0 干预结果面板已挂载', mounted, mounted ? '' : '等了 ~18s');

  let state = null;
  for (let i = 0; i < 15; i++) {
    await sleep(1000);
    state = await page.eval(`(() => {
      const el = document.querySelector('[data-outcome]');
      if (!el) return { state: 'absent' };
      return {
        state: el.getAttribute('data-outcome'),
        text: (el.innerText || '').replace(/\\s+/g, ' '),
        banner: (() => { const b = el.querySelector('[data-offline-banner]');
          return b ? (b.innerText||'').replace(/\\s+/g,' ') : null; })(),
        note: (() => { const b = el.querySelector('[data-invisible-note]');
          return b ? (b.innerText||'').replace(/\\s+/g,' ') : null; })(),
        omitted: (() => { const d = el.querySelector('[data-omitted]');
          return d ? (d.textContent||'').replace(/\\s+/g,' ') : null; })(),
        verdicts: [...el.querySelectorAll('[data-verdict]')].map(s => ({
          k: s.getAttribute('data-verdict'), t: (s.textContent||'').trim() })),
        arm: (() => {
          const a = el.querySelector('[data-arm-asymmetry]');
          // ⚠ 缺失分支必须返回**完整**的键，否则下面的 a.rows 抛 TypeError
          //   被外层 catch 记成「装置错」，H 组后面几条一条都跑不到 ——
          //   看着像「只有 H1 红」。这已经是本轮第三次犯同一个错。
          if (!a) return { missing: true, rows: [], limitation: null, text: '' };
          return {
            missing: false,
            nPairs: a.getAttribute('data-n-pairs'),
            cos: a.getAttribute('data-cos-up-down'),
            maxAbsSum: a.getAttribute('data-max-abs-sum'),
            text: (a.innerText || '').replace(/\\s+/g, ' ').trim(),
            limitation: (() => { const l = a.querySelector('[data-arm-limitation]');
              return l ? (l.innerText||'').replace(/\\s+/g,' ') : null; })(),
            rows: [...a.querySelectorAll('[data-arm-metric]')].map(li => ({
              m: li.getAttribute('data-arm-metric'),
              diff: li.getAttribute('data-arm-diff'),
              t: li.getAttribute('data-arm-t'),
              dist: li.getAttribute('data-arm-distinguishable'),
              text: (li.innerText||'').replace(/\\s+/g,' ').trim(),
            })),
          };
        })(),
        rows: el.querySelectorAll('[data-answer-rows] > div').length,
      };
    })()`);
    if (state.state === 'ready') break;
  }
  rec('G1 面板加载完成', state.state === 'ready', `state=${state.state}`);

  /* ---------------------------------------------------------------- */
  rec('G2 顶部横幅明说「离线 32k 批次、不是本页滑块」',
      !!state.banner
      && /offline/i.test(state.banner)
      && /not this page/i.test(state.banner)
      && /32k/i.test(state.banner),
      String(state.banner).slice(0, 150));

  /* ---------------------------------------------------------------- */
  // 与产物逐值比对。
  const steered = COT.runs.filter(r => r.strength > 0);
  const control = COT.runs.filter(r => r.strength === 0);
  const fd = steered.map(r => r.first_diverged_step)
    .filter(x => x != null).sort((a, b) => a - b);
  const median = xs => xs[Math.floor(xs.length / 2)];
  const agree = steered.map(r => r.token_agreement).sort((a, b) => a - b);
  const kl = steered.map(r => r.mean_logit_kl).sort((a, b) => a - b);

  const wantFd = `~${median(fd)}`;
  const wantAgree = `${(median(agree) * 100).toFixed(1)}%`;
  const wantKl = median(kl).toFixed(3);
  rec('G3 首个分歧步 / token 一致率 / KL 与 cot_texts.json 逐值相同',
      state.text.includes(wantFd) && state.text.includes(wantAgree)
      && state.text.includes(wantKl),
      `want ${wantFd} / ${wantAgree} / ${wantKl} | 产物 n_steered=${steered.length} n_control=${control.length}`);

  const clean = control.filter(
    r => r.first_diverged_step == null && r.token_agreement === 1);
  rec('G4 面板写出了对照臂的分母与「对照未移动」的事实',
      state.text.includes(`${clean.length}/${control.length}`)
      && /never moved|never/i.test(state.text),
      `want ${clean.length}/${control.length} 个对照臂 first_diverged=null 且 agreement=1`);

  /* ---------------------------------------------------------------- */
  // 答案对照：verdict 标签必须与产物一致，且不得少于产物。
  const wantV = ANS.selection.by_verdict || {};
  const missing = Object.entries(wantV).filter(
    ([k, n]) => !state.verdicts.some(v => v.k === k && v.t.includes(`×${n}`)));
  rec('G5 每种 verdict 的计数与 answer_readout.json 相同',
      missing.length === 0,
      missing.length ? `缺 ${JSON.stringify(missing)}`
                     : JSON.stringify(state.verdicts.map(v => v.t).join(' ')));

  rec('G6 面板如实说「净变化为 0」，不只展示变好的那几例',
      /net zero|Net change in correct answers:\s*0/i.test(state.text),
      String(state.text).match(/Net change[^.]*\./i)?.[0] || '未见 net 变化陈述');

  /* ---------------------------------------------------------------- */
  // 红线：循环论证不能被当成证据展示。
  rec('G7 面板解释了为什么不展示 in-sample 必要性数字',
      !!state.omitted && /circular/i.test(state.omitted),
      String(state.omitted).slice(0, 130));
  rec('G8 页面上不出现任何"必要性已通过"之类的判定',
      !/necessity.{0,40}(pass|gate)/i.test(state.text)
      && !/passes_gate/i.test(state.text),
      '未发现把循环判定渲染成结论的文案');

  /* ---------------------------------------------------------------- */
  rec('G9 解释了为什么注入在 3D 里几乎看不见（并给出量级）',
      !!state.note && /0\.3%|0\.3/.test(state.note) && /30\.4|29\.8/.test(state.note),
      String(state.note).slice(0, 140));

  const errs = page.events
    .filter(e => e.method === 'Runtime.consoleAPICalled' && e.params.type === 'error')
    .map(e => (e.params.args || []).map(a => a.value ?? a.description ?? '').join(' '))
    .filter(t => !/favicon|Failed to load resource/i.test(t));
  rec('G10 页面无 console error', errs.length === 0,
      errs.length ? errs.slice(0, 2).join(' | ') : 'none');

  /* ==================== H 组：±v 配对检验 ==================== */
  // 这一块是补 §G3 的：面板原来把 up/down **合并**取中位数，
  // 两臂之间显著的差异被盖住，而且没有分母、没有不确定性。
  const A = ARM, H = state.arm || {};

  rec('H1 配对块存在，且前置条件（两臂恰好互为负）与产物一致',
      !H.missing
      && Number(H.nPairs) === A.n_pairs
      && Math.abs(Number(H.cos) - A.cos_up_down) < 1e-6
      && Number(H.maxAbsSum) === A.max_abs_up_plus_down,
      H.missing ? '配对块缺失'
                : `n=${H.nPairs} cos=${H.cos} max|up+down|=${H.maxAbsSum} | `
                  + `产物 n=${A.n_pairs} cos=${A.cos_up_down.toFixed(15)} `
                  + `max=${A.max_abs_up_plus_down}`);

  // 逐项：配对差 / t / 可分性三样都要与产物一致。
  // 断言「等于产物」而不是「看起来合理」—— 差一个符号也要红。
  rec('H2 三个量的配对差 / t / 可分性与产物逐项一致',
      H.rows.length === A.metrics.length
      && A.metrics.every(am => {
          const r = H.rows.find(x => x.m === am.metric);
          return r
            && Math.abs(Number(r.diff) - am.paired_diff) < 1e-9
            && Math.abs(Number(r.t) - am.t) < 1e-9
            && r.dist === String(am.distinguishable)
            // 文字侧也要对：差值带符号、两个均值都印出来
            && r.text.includes((am.paired_diff >= 0 ? '+' : '')
                               + am.paired_diff.toFixed(4))
            && r.text.includes(am.up_mean.toFixed(4))
            && r.text.includes(am.down_mean.toFixed(4));
        }),
      H.rows.map(r => `${r.m}:${r.diff}/t=${r.t}/dist=${r.dist}`).join(' ')
        + ' | 产物 '
        + A.metrics.map(a => `${a.metric}:${a.paired_diff.toFixed(4)}/t=${a.t.toFixed(2)}/dist=${a.distinguishable}`).join(' '));

  // ⚠ 最关键的一条：**CI 跨 0 的量不许被印成一个结论**。
  //   first_diverged_step 的 CI 是 [-6.04, +12.17]，跨 0。
  //   面板必须印「分不开」，不许只印一个 +3.52 让读者以为有差异。
  const fdMetric = A.metrics.find(m => m.metric === 'first_diverged_step');
  const fdRow = H.rows.find(x => x.m === 'first_diverged_step');
  rec('H3 CI 跨 0 的量必须标「分不开」并印出跨 0 的 CI 区间',
      !!fdMetric && !!fdMetric.distinguishable === false
      && !!fdRow && fdRow.dist === 'false'
      && /分不开/.test(fdRow.text)
      && fdRow.text.includes(fdMetric.ci95_lo.toFixed(1))
      && fdRow.text.includes(fdMetric.ci95_hi.toFixed(1))
      && fdRow.text.includes('跨 0'),
      fdRow ? fdRow.text.slice(0, 150)
            : `产物 distinguishable=${fdMetric && fdMetric.distinguishable}`);

  // 反向：可分的量不许被印成「分不开」
  const klRow = H.rows.find(x => x.m === 'mean_logit_kl');
  const klMetric = A.metrics.find(m => m.metric === 'mean_logit_kl');
  rec('H4 可分的量必须标「分得开」（不许反向压制）',
      !!klMetric && klMetric.distinguishable === true
      && !!klRow && klRow.dist === 'true' && /分得开/.test(klRow.text)
      && !/分不开/.test(klRow.text),
      klRow ? klRow.text.slice(0, 120) : '缺 mean_logit_kl 行');

  // 缺随机对照这条限制必须印在页面上，且要给出补齐它需要的那一格
  rec('H5 「没有同范数随机对照 ⇒ 不构成方向专属性」必须印出，且给出补齐条件',
      !!H.limitation
      && /随机/.test(H.limitation)
      && /不构成方向专属性|方向特有/.test(H.limitation)
      && H.limitation.includes(String(A.layer))
      && H.limitation.includes(String(A.strength))
      && H.limitation.includes(String(A.n_pairs)),
      H.limitation ? H.limitation.slice(0, 200) : '缺 [data-arm-limitation]');
} catch (e) {
  rec('X 脚本崩了', false, String((e && e.stack) || e).slice(0, 300));
} finally {
  cdp.close(); proc.kill('SIGKILL');
}

const pass = R.filter(x => x.p).length;
console.log(`\n=== ${pass}/${R.length} passed ===`);
R.filter(x => !x.p).forEach(x => console.log('FAIL: ' + x.n));
process.exit(pass === R.length ? 0 : 1);
