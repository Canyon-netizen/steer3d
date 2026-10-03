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
//
// 后来的两组把同一类错误往上追了一层：
//  H 组（§4.13）盯「两臂合并后差异被盖住」
//  I 组（§4.14）盯「净变化 0 被读成零效应」
// I 组是最需要反向断言的一组：数字本来就全对，错的是**这个 0 允许被
// 读成什么**。所以 I2/I5/I8 断言的是「哪些话不许出现」，而不是
// 「哪个数等于几」。
import { launch, Page, CDP } from './cdp_client.mjs';
import { readFileSync } from 'node:fs';

const URL = process.env.T3D_URL || 'http://127.0.0.1:10100/';
const PROFILE = process.env.T3D_PROFILE
  || '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_outcome_' + process.pid;
const DATA = '/Users/zhourui/code/steer3d/frontend/public/latent/data';

const COT = JSON.parse(readFileSync(DATA + '/cot_texts.json', 'utf8'));
const ANS = JSON.parse(readFileSync(DATA + '/answer_readout.json', 'utf8'));
const ARM = JSON.parse(readFileSync(DATA + '/arm_asymmetry.json', 'utf8'));
const PW  = JSON.parse(readFileSync(DATA + '/answer_power.json', 'utf8'));
const SD  = JSON.parse(readFileSync(DATA + '/steer_directions.json', 'utf8'));
const RP  = JSON.parse(readFileSync(DATA + '/steer_repetition.json', 'utf8'));
const CA  = JSON.parse(readFileSync(DATA + '/claim_audit.json', 'utf8'));

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
        power: (() => {
          const p = el.querySelector('[data-answer-power]');
          // ⚠ 缺失时返回**完整**的键（值置 null），不能让下游
          //   P.items.invariant 抛 TypeError 被外层 catch 吞掉 ——
          //   那会把 I 组后面几条一起记成「装置错」，看着像「只有 I0 红」。
          // ⚠ 这整段在一个**模板字面量**里：反斜杠要写两遍（\\s），
          //   且注释里绝不能出现反引号 —— 两者都会以很难看懂的方式
          //   把整个 eval 打挂，报错还指在第 64 行的开头。
          if (!p) return { missing: true, text: '', items: {}, notClaimed: null,
                           net: null, nComplete: null, nIncomplete: null,
                           nShipped: null, changed: null, w2w: null,
                           flips: null, needed: null, maxFlips: null,
                           baseRight: null, steerRight: null };
          const g = a => p.getAttribute(a);
          const items = {};
          p.querySelectorAll('[data-power-item]').forEach(li => {
            items[li.getAttribute('data-power-item')] =
              (li.innerText || '').replace(/\\s+/g, ' ').trim();
          });
          const nc = p.querySelector('[data-power-not-claimed]');
          return {
            missing: false,
            text: (p.innerText || '').replace(/\\s+/g, ' ').trim(),
            items,
            notClaimed: nc ? (nc.innerText || '').replace(/\\s+/g, ' ').trim() : null,
            net: g('data-net-change'), nComplete: g('data-n-complete'),
            nIncomplete: g('data-n-incomplete'), nShipped: g('data-n-shipped'),
            changed: g('data-changed'), w2w: g('data-wrong2wrong'),
            flips: g('data-flips'), needed: g('data-flips-needed'),
            maxFlips: g('data-max-flips'),
            baseRight: g('data-base-right'), steerRight: g('data-steer-right'),
          };
        })(),
        dir: (() => {
          const d = el.querySelector('[data-direction-compare]');
          if (!d) return { missing: true, text: '', items: {}, trap: null,
                           n: null, zeroIdentical: null, zeroClosed: null,
                           downClosed: null, upClosed: null, upOnly: null,
                           downOnly: null, mcnemarP: null, upRw: null,
                           upNet: null, opposite: null, lenP: null };
          const g = a => d.getAttribute(a);
          const items = {};
          d.querySelectorAll('[data-dir-item]').forEach(li => {
            items[li.getAttribute('data-dir-item')] =
              (li.innerText || '').replace(/\\s+/g, ' ').trim();
          });
          const tr = d.querySelector('[data-dir-trap]');
          return {
            missing: false,
            text: (d.innerText || '').replace(/\\s+/g, ' ').trim(),
            items, table: {},
            trap: tr ? (tr.innerText || '').replace(/\\s+/g, ' ').trim() : null,
            n: g('data-n'), zeroIdentical: g('data-zero-identical'),
            zeroClosed: g('data-zero-closed'), downClosed: g('data-down-closed'),
            upClosed: g('data-up-closed'), upOnly: g('data-up-only'),
            downOnly: g('data-down-only'), mcnemarP: g('data-mcnemar-p'),
            upRw: g('data-up-rw'), upNet: g('data-up-net'),
            opposite: g('data-opposite'), lenP: g('data-len-p'),
          };
        })(),
        rep: (() => {
          const d = el.querySelector('[data-repetition]');
          if (!d) return { missing: true, text: '', items: {}, cannot: null,
                           mechanism: null };
          const g = a => d.getAttribute(a);
          const items = {};
          d.querySelectorAll('[data-rep-item]').forEach(li => {
            items[li.getAttribute('data-rep-item')] =
              (li.innerText || '').replace(/\\s+/g, ' ').trim();
          });
          const cn = d.querySelector('[data-rep-cannot]');
          const mc = d.querySelector('[data-rep-mechanism]');
          return {
            missing: false,
            text: (d.innerText || '').replace(/\\s+/g, ' ').trim(),
            items,
            cannot: cn ? (cn.innerText || '').replace(/\\s+/g, ' ').trim() : null,
            mechanism: mc ? (mc.innerText || '').replace(/\\s+/g, ' ').trim() : null,
            words: g('data-rep-words'), plus: g('data-rep-plus'),
            zero: g('data-rep-zero'), minus: g('data-rep-minus'),
            p: g('data-rep-p'), pMinus: g('data-rep-p-minus'),
            sameSet: g('data-rep-same-set'), dirtyCuts: g('data-rep-dirty-cuts'),
            maxPlus: g('data-rep-max-plus'), maxZero: g('data-rep-max-zero'),
            maxMinus: g('data-rep-max-minus'),
            k: g('data-rep-k'), thresh: g('data-rep-thresh'),
            n: g('data-rep-n'),
          };
        })(),
        ca: (() => {
          const d = el.querySelector('[data-claim-audit]');
          if (!d) return { missing: true, text: '', items: {}, why: null,
                           ceiling: null, coverage: null };
          const g = a => d.getAttribute(a);
          const items = {};
          d.querySelectorAll('[data-ca-item]').forEach(li => {
            items[li.getAttribute('data-ca-item')] =
              (li.innerText || '').replace(/\\s+/g, ' ').trim();
          });
          const q = sel => { const n = d.querySelector(sel);
            return n ? (n.innerText || '').replace(/\\s+/g, ' ').trim() : null; };
          return {
            missing: false,
            text: (d.innerText || '').replace(/\\s+/g, ' ').trim(),
            items, why: q('[data-ca-why]'),
            ceiling: q('[data-ca-ceiling]'),
            coverage: q('[data-ca-coverage]'),
            n: g('data-ca-n'), nlevels: g('data-ca-nlevels'),
            l0declared: g('data-ca-l0-declared'),
            l0supported: g('data-ca-l0-supported'),
            l0survives: g('data-ca-l0-survives'),
            l2declared: g('data-ca-l2-declared'),
            l2supported: g('data-ca-l2-supported'),
            selfDeclared: g('data-ca-self-declared'),
            selfSupported: g('data-ca-self-supported'),
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

  // ==================== I 组：「净变化 0」是什么 ====================
  // 这一块盯的不是数字对不对（数字本来就对），盯的是
  // **这个 0 被允许读成什么**。
  //
  // v2（§4.15）把 §4.14 的三条结论推翻了，所以 I 组也重写了：
  //  v1 只看了 10 个入表题，于是把「上界 43.5%」「上限只有 10 个翻转」
  //     当成事实印在页面上。查了 20 个完整配对之后：
  //     43.5% 是错的（改变率是 10/20 = 50% 的点估计），
  //     「上限 10 个」也是错的（20 个配对够得着 6 个）。
  //  更重要的是 v1 最大的担心（分母被筛过）**可以证伪**：
  //     被剔除的题两臂答案相同 ⇒ verdict 恒为 X->X ⇒ 贡献恒为 0。
  const P = state.power || {};
  const NC = P.notClaimed || '';
  const f3 = n => Number(n).toFixed(3);
  const esc = s => String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const V = PW.full_verdicts || {};
  const pctTxt = x => `${(x * 100).toFixed(1)}%`;  // ⚠ 必须与页面 pct() 同为 1 位

  rec('I0 功效块存在，且 11 个关键数字与 answer_power.json 逐值相同',
      !P.missing
      && Number(P.net) === PW.net_change
      && Number(P.nComplete) === PW.n_complete_pairs
      && Number(P.nIncomplete) === PW.n_incomplete_pairs
      && Number(P.nShipped) === PW.n_shipped
      && Number(P.changed) === PW.changed_n
      && Number(P.w2w) === PW.changed_but_still_wrong
      && Number(P.flips) === PW.flips
      && Number(P.needed) === PW.flips_needed_for_p05
      && Number(P.maxFlips) === PW.max_possible_flips
      && Number(P.baseRight) === PW.baseline_correct
      && Number(P.steerRight) === PW.steered_correct,
      P.missing ? '缺 [data-answer-power]'
        : `net=${P.net} 完整=${P.nComplete} 未闭合=${P.nIncomplete} 入表=${P.nShipped} `
          + `changed=${P.changed} w2w=${P.w2w} flips=${P.flips} need=${P.needed} `
          + `max=${P.maxFlips} 对=${P.baseRight}->${P.steerRight} | 产物 `
          + `net=${PW.net_change} 完整=${PW.n_complete_pairs} `
          + `未闭合=${PW.n_incomplete_pairs} 入表=${PW.n_shipped} `
          + `changed=${PW.changed_n} w2w=${PW.changed_but_still_wrong} `
          + `flips=${PW.flips} need=${PW.flips_needed_for_p05} `
          + `max=${PW.max_possible_flips} 对=${PW.baseline_correct}->${PW.steered_correct}`);

  // ⚠ 渲染完整性：这块是**纯 JSX**，不是 markdown 渲染器。
  //   我把产物 verdict 字符串里的 `**强调**` 直接抄进了 JSX，
  //   于是页面原样印出 `**不是数据碰巧**` —— 判据全绿，因为
  //   「文字在」这一条它查得出；判据查不出的是「渲染对了没有」。
  //   是截图看出来的。⇒ 这类缺陷必须有一条专门的守卫。
  // ⚠ 守卫范围从「功效块」扩到**整块面板**。
  //   原版只查 P.text，而 markdown 泄漏完全可能发生在方向对照块、
  //   离线横幅、折叠说明里的任何一处。
  rec('I0b 整块面板不得出现未渲染的 markdown 强调记号 **',
      !P.missing && !state.text.includes('**') && !state.omitted.includes('**')
      && !state.banner.includes('**') && !state.note.includes('**'),
      state.text.includes('**') || (state.omitted || '').includes('**')
        ? `面板内出现 **：${(state.text.match(/.{0,40}\*\*.{0,40}/) || [''])[0]}`
        : '整块面板无 ** （纯 JSX 渲染，markdown 记号会原样印出）');

  // 任何一处漂移，读者就会看到两个互相打架的净变化。
  const chipNum = k => {
    const v = state.verdicts.find(x => x.k === k);
    const m = v && v.t.match(/\d+/);
    return m ? Number(m[0]) : NaN;
  };
  const netFromChips = chipNum('wrong->right') - chipNum('right->wrong');
  const netFromAns = (ANS.selection.by_verdict['wrong->right'] || 0)
                   - (ANS.selection.by_verdict['right->wrong'] || 0);
  // 20 对全表自洽：四类之和 = 完整配对数；答对数两种算法相等；净变化 = 差
  const fullSum = Object.values(V).reduce((a, b) => a + b, 0);
  const baseV = (V['right->right'] || 0) + (V['right->wrong'] || 0);
  const steerV = (V['right->right'] || 0) + (V['wrong->right'] || 0);
  rec('I1 净变化在四处一致（verdict 标签 / data-* / 完整 20 对全表 / 另一份产物）',
      Number.isFinite(netFromChips)
      && netFromChips === netFromAns
      && netFromChips === Number(P.net)
      && netFromChips === PW.net_change
      && fullSum === PW.n_complete_pairs
      && baseV === PW.baseline_correct
      && steerV === PW.steered_correct
      && baseV - steerV === -PW.net_change
      // ⚠ 这一条是 O21 逼出来的：O21 把**印出来的**基线答对数写死成 10，
      //   而 data-* 属性仍诚实 ⇒ 前面的算术全部照样通过。
      //   ⇒ 凡是「属性诚实 / 文案撒谎」那一类变异，判据**必须**同时
      //     读可见文案，不能只读属性。同族的教训见 O14 与 §4.15.6。
      && new RegExp('基线答对\\s*' + esc(PW.baseline_correct)).test(P.text)
      && new RegExp('注入后答对\\s*' + esc(PW.steered_correct)).test(P.text),
      `标签 ${netFromChips} | data-net-change=${P.net} | 产物=${PW.net_change} `
      + `| 完整 20 对全表 四类和=${fullSum}(应=${PW.n_complete_pairs}) `
      + `答对 ${baseV}/${steerV}(应=${PW.baseline_correct}/${PW.steered_correct})`
      + ` | 可见「基线答对 ${PW.baseline_correct}」=`
      + `${new RegExp('基线答对\\s*' + esc(PW.baseline_correct)).test(P.text)}`);

  // ⚠ 反向断言：零效应读法**只能**以否定句形式出现。
  const zeroClaimCount = (NC.match(/干预对答案正确性无影响/g) || []).length;
  rec('I2 「净变化 0」必须标为欠功效，且「无影响」只允许出现在否定句里',
      !/did not make them better/i.test(state.text)
      && /欠功效/.test(P.text)
      && /不是零效应/.test(P.text)
      && zeroClaimCount === 1
      && new RegExp('不能说[^。]*干预对答案正确性无影响').test(NC),
      `欠功效=${/欠功效/.test(P.text)} 不是零效应=${/不是零效应/.test(P.text)} `
      + `「无影响」出现 ${zeroClaimCount} 次且被「不能说」领着=`
      + `${new RegExp('不能说[^。]*干预对答案正确性无影响').test(NC)}`
      + ` | 旧零效应句仍在=${/did not make them better/i.test(state.text)}`);

  // 为什么 0 不是零效应：核心算术必须印在屏幕上。
  // ⚠「上限够得着」这一条是 v2 撤回 v1 错误的地方，判据要盯住。
  const PWITEM = P.items.power || '';
  rec('I3 必须印出「需 N 个同向翻转」，且 20 对**够得着**（v1 说上限只有 10，已撤回）',
      new RegExp('需要\\s*' + esc(PW.flips_needed_for_p05) + '\\s*个同向翻转').test(PWITEM)
      && new RegExp('够得着').test(PWITEM)
      && new RegExp('最多\\s*' + esc(PW.max_possible_flips) + '\\s*个').test(PWITEM)
      && new RegExp('符号检验').test(PWITEM)
      && new RegExp('p\\s*<\\s*0\\.05').test(PWITEM)
      && PWITEM.includes(String(PW.two_sided_sign_p_if_all_same_direction)),
      PWITEM ? PWITEM.slice(0, 190) : '缺 [data-power-item="power"]');

  // 破坏率/修复率的 95% 区间。v1 用的是 1/10 的单侧区间，v2 换成
  // 诚实分母下的 1/7 与 1/13 —— 两个都要与产物逐位相同。
  rec('I4 破坏率 1/基线答对数 与 修复率 1/（完整数−基线答对数）两对 CI 与产物一致',
      new RegExp('破坏率是\\s*1\\/' + esc(PW.break_denominator)).test(PWITEM)
      && new RegExp('修复率是\\s*1\\/' + esc(PW.fix_denominator)).test(PWITEM)
      && PWITEM.includes(f3(PW.break_rate_ci95[0]))
      && PWITEM.includes(f3(PW.break_rate_ci95[1]))
      && PWITEM.includes(f3(PW.fix_rate_ci95[0]))
      && PWITEM.includes(f3(PW.fix_rate_ci95[1]))
      && PW.break_denominator + PW.fix_denominator === PW.n_complete_pairs
      && (PW.break_rate_ci95[1] - PW.break_rate_ci95[0]) > 0.1,
      PWITEM.slice(-190));

  // 「不能说的话」：非随机轴 / 单档 / 正臂缺失 / L7 未测 /
  // 不能说准确率没下降 / 那 3 题完全未知。
  rec('I5 「不能说的话」必须含：不能说准确率没下降 / 非随机样本 / L7 未测 / 3 题未知',
      !!NC
      && /不能说[^。]*准确率没有下降/.test(NC)
      && /1 修 1 破/.test(NC)
      && /随机样本|筛过|挑出来/.test(NC)
      && NC.includes(PW.direction)
      && NC.includes(String(PW.strength))
      && /confidence_up/.test(NC)
      && /L7/.test(NC)
      && /一次都没测/.test(NC)
      // 两条必须与实际文案逐字对齐：配对数后面跟「不是…随机样本」，
      // 被剔掉的题数后面跟「不是随机抽掉的」。
      && new RegExp(esc(PW.n_complete_pairs) + '\\s*个配对也?不是').test(NC)
      && new RegExp(esc(PW.n_incomplete_pairs)
                    + '\\s*题\\s*不是随机抽掉的').test(NC),
      NC ? NC.slice(0, 280) : '缺 [data-power-not-claimed]');

  // 去向分解必须逐项印出，且 0 那一类也要印 —— 「解析不出 0 题」
  // 是一条被 v1 猜错、v2 查实的事实。
  const UK = P.items.unknown || '';
  rec('I6 完整/未闭合的划分与去向分解（只跑完一臂 / 都没跑完 / 解析不出）逐项与产物一致',
      Number(P.nComplete) + Number(P.nIncomplete) === PW.n_problems_in_batch
      && UK.includes(String(PW.incomplete_breakdown.one_arm_closed))
      && UK.includes(String(PW.incomplete_breakdown.neither_closed))
      && new RegExp('解析不出的是\\s*' + esc(PW.incomplete_breakdown.unparseable) + '\\s*题').test(UK)
      && new RegExp('真正未知的只有\\s*' + esc(PW.n_incomplete_pairs) + '\\s*题').test(UK)
      // ⚠ 这一条是 O15 逼出来的：O15 把**正文里**的「20 题」改成「10 题」
      //   （即 v1 那个被 §4.15 查实为错的分母），而 data-n-complete 仍诚实
      //   ⇒ 只读属性的判据全绿。⇒ 分母这类数必须两处都查。
      && new RegExp('整批\\s*' + esc(PW.n_problems_in_batch)
                    + '\\s*题里，\\s*' + esc(PW.n_complete_pairs)
                    + '\\s*题两臂都跑完').test(P.text),
      UK ? UK.slice(0, 130) + ' …｜ 可见「整批 23 题里，20 题两臂都跑完」='
           + new RegExp('整批\\s*' + esc(PW.n_problems_in_batch)
                         + '\\s*题里，\\s*' + esc(PW.n_complete_pairs)
                         + '\\s*题两臂都跑完').test(P.text)
        : '缺 [data-power-item="unknown"]');

  // ⚠ v2 最重要的新增：不变性定理。这是读者最该怀疑的那一条
  //   （「这个 0 会不会是筛出来的」），必须把定理和实测并排印出。
  const IV = P.items.invariance || '';
  rec('I7 不变性定理必须印出：被剔除的题贡献恒为 0，且入表/完整两个净变化逐位相同',
      /不是数据碰巧|定理/.test(IV)
      && /答案都相同/.test(IV)
      && /贡献恒为\s*0/.test(IV)
      && Number(P.nComplete) - Number(P.nShipped) === PW.n_complete_pairs - PW.n_shipped
      && PW.net_change_invariance.holds === true
      && PW.net_change_invariance.net_over_shipped_10 === PW.net_change
      && PW.net_change_invariance.net_over_complete_20 === PW.net_change
      && PW.net_change_invariance.unchanged_pairs_contribution === 0
      && IV.includes(String(PW.net_change_invariance.net_over_shipped_10))
      && IV.includes(String(PW.net_change_invariance.net_over_complete_20)),
      IV ? IV.slice(0, 210) : '缺 [data-power-item="invariance"]');

  // ⚠ 「答案变了 ≠ 概念变了」：这是 50% 改变率最容易被读错的地方。
  const SM = P.items.semantic || '';
  const MG = PW.changed_but_still_wrong_magnitude;
  rec('I8 「答案变了 ≠ 概念变了」必须印出，并给出 wrong→wrong 次数与 |Δ| 中位数',
      /不等于「概念变了」/.test(SM)
      && SM.includes(`${PW.changed_n}/${PW.n_complete_pairs}`)
      && SM.includes(pctTxt(PW.answer_change_rate_complete))
      && SM.includes(String(PW.changed_but_still_wrong))
      && SM.includes(String(MG.median))
      && SM.includes(String(MG.min))
      && SM.includes(String(MG.max))
      && SM.includes(String(MG.n_below_100))
      && PW.changed_n - PW.changed_but_still_wrong === 2,
      SM ? SM.slice(0, 220) : '缺 [data-power-item="semantic"]');

  // ⚠ 真正存在的那次选择效应：未知的 3 题是撞 token 上限（跑飞）那批。
  rec('I9 未知那几题与撞 token 上限的关联必须印出（含分母 4/6）',
      new RegExp('撞了\\s*' + esc(PW.token_cap) + '\\s*token').test(UK)
      && UK.includes(String(PW.incomplete_arms_at_token_cap))
      && UK.includes(String(PW.incomplete_arms_total))
      && /跑飞/.test(UK)
      && PW.incomplete_arms_at_token_cap > 0
      && PW.incomplete_arms_at_token_cap < PW.incomplete_arms_total,
      UK ? UK.slice(-200) : '缺 [data-power-item="unknown"]');

  const DM = P.items.domain || '';
  rec('I10 域外答案的题必须被点名，并说明「域外判定、对净变化没有贡献」',
      DM.includes(String(MG.out_of_domain_labels.length))
      && MG.out_of_domain_labels.every(l => DM.includes(l))
      && /答案域之外/.test(DM)
      && /没有贡献/.test(DM)
      && /域外判定/.test(DM),
      DM ? DM.slice(0, 200) : '缺 [data-power-item="domain"]');

  // ==================== J 组：同一根轴换符号 ====================
  // 上面整块只看了 −v。disk 上还有同 23 题的 +v 臂，而两个方向的
  // **零强度臂逐字相同**（23/23）⇒ 共享同一份对照，配对里没有
  // 「两次运行」的噪声源，只差注入向量这一个变量。
  // 结论对预期是反的：+v 把分布推得**更近**却让 **18/23** 的题跑不完，
  // −v 把分布推得**更远**却只让 1 题跑不完。
  const D = state.dir || {};
  const T = (D.table || {});

  rec('J0 方向对照块存在，且 9 个关键数字与 steer_directions.json 逐值相同',
      !D.missing
      && Number(D.n) === SD.n_problems
      && Number(D.zeroIdentical) === SD.shared_control.n_identical_zero_arms
      && Number(D.zeroClosed) === SD.closed_counts.zero_shared
      && Number(D.downClosed) === SD.closed_counts.down_minus_v
      && Number(D.upClosed) === SD.closed_counts.up_plus_v
      && Number(D.upOnly) === SD.blew_up.table_on_shared_zero_control.up_only_blew_up
      && Number(D.downOnly) === SD.blew_up.table_on_shared_zero_control.down_only_blew_up
      && Math.abs(Number(D.mcnemarP) - SD.blew_up.mcnemar_exact_p) < 1e-12
      && D.opposite === String(SD.kl_contrast.opposite),
      D.missing ? '缺 [data-direction-compare]'
        : `n=${D.n} 零臂相同=${D.zeroIdentical} 闭合 零/−v/+v=`
          + `${D.zeroClosed}/${D.downClosed}/${D.upClosed} upOnly=${D.upOnly} `
          + `downOnly=${D.downOnly} p=${D.mcnemarP} opposite=${D.opposite} | 产物 `
          + `n=${SD.n_problems} 相同=${SD.shared_control.n_identical_zero_arms} `
          + `${SD.closed_counts.zero_shared}/${SD.closed_counts.down_minus_v}/`
          + `${SD.closed_counts.up_plus_v} upOnly=`
          + `${SD.blew_up.table_on_shared_zero_control.up_only_blew_up} downOnly=`
          + `${SD.blew_up.table_on_shared_zero_control.down_only_blew_up} `
          + `p=${SD.blew_up.mcnemar_exact_p} opposite=${SD.kl_contrast.opposite}`);

  rec('J1 共享对照必须被印出（零臂逐字相同 n/23），否则不是配对设计',
      !!D.text
      && /零强度臂逐字相同/.test(D.text)
      && D.text.includes(String(SD.shared_control.n_identical_zero_arms))
      && D.text.includes(String(SD.n_problems))
      && SD.shared_control.holds === true
      && SD.shared_control.n_identical_zero_arms === SD.n_problems,
      D.text ? D.text.slice(0, 170) : '缺块');

  // 三个闭合率必须都印出，且 +v 那个不能被弱化成「掉了一点」
  rec('J2 三个闭合率（零臂 / −v / +v）必须并排印出，且 +v 那格不许淡化',
      D.text
      && D.text.includes(`${SD.closed_counts.zero_shared}/${SD.n_problems}`)
      && D.text.includes(`${SD.closed_counts.down_minus_v}/${SD.n_problems}`)
      && D.text.includes(`${SD.closed_counts.up_plus_v}/${SD.n_problems}`)
      && /大面积跑飞/.test(D.text)
      && SD.closed_counts.up_plus_v < SD.closed_counts.zero_shared / 2,
      D.text ? D.text.slice(0, 200) : '缺块');

  const MC = D.items.mcnemar || '';
  rec('J3 四格表的关键三格与 McNemar 精确 p 必须与产物一致（可见文案 + 属性两处）',
      MC.includes(String(SD.blew_up.table_on_shared_zero_control.n_zero_closed))
      && MC.includes(String(SD.blew_up.table_on_shared_zero_control.up_only_blew_up))
      && MC.includes(String(SD.blew_up.table_on_shared_zero_control.down_only_blew_up))
      && MC.includes(String(SD.blew_up.table_on_shared_zero_control.both_blew_up))
      && MC.includes(String(SD.blew_up.n_up_vs_shared_control))
      && MC.includes(String(SD.blew_up.n_down_vs_shared_control))
      // ⚠ J3 把**印出来的** p 换成 0.42，而 data-mcnemar-p 仍诚实
      //   ⇒ 只查属性的判据全绿。这是 O15 / O21 / J3 第三次同一条教训：
      //   **判据必须同时读可见文案和 data-*。**
      && MC.includes(SD.blew_up.mcnemar_exact_p.toExponential(2))
      && Number(D.mcnemarP) === SD.blew_up.mcnemar_exact_p
      && SD.blew_up.mcnemar_exact_p < 0.001,
      MC ? MC.slice(0, 210) : '缺 [data-dir-item="mcnemar"]');

  const KL = D.items.kl || '';
  rec('J4 「注入幅度与跑飞方向相反」必须印出，两个 KL 与产物一致',
      /与注入幅度相反/.test(KL)
      && KL.includes(SD.kl_contrast.mean_logit_kl_down.toFixed(4))
      && KL.includes(SD.kl_contrast.mean_logit_kl_up.toFixed(4))
      && /更远/.test(KL) && /更少跑飞/.test(KL)
      && /相反/.test(KL)
      && SD.kl_contrast.larger_kl_direction === 'confidence_down'
      && SD.kl_contrast.more_blew_up_direction === 'confidence_up'
      && SD.kl_contrast.opposite === true,
      KL ? KL.slice(0, 200) : '缺 [data-dir-item="kl"]');

  // ⚠ 反向断言：配对符号检验 p = 0.093 **没到 0.05**。
  //   这一条是本组最容易犯的错 —— 中位数 2.21× 对 1.20× 看着很清楚，
  //   很容易被印成一个结论。它只能印成「弱证据」。
  const LN = D.items.length || '';
  rec('J5 长度差必须标为弱证据：p 未到 0.05 时必须原样印出 p 并说「没到 0.05」',
      SD.length.sign_test_p > 0.05
      && LN.includes(SD.length.ratio_median_up.toFixed(2))
      && LN.includes(SD.length.ratio_median_down.toFixed(2))
      && LN.includes(String(SD.length.n_up_ratio_gt_down))
      && LN.includes(SD.length.sign_test_p.toFixed(3))
      && /没到\s*0\.05/.test(LN)
      && /弱证据/.test(LN),
      LN ? LN.slice(0, 220) : '缺 [data-dir-item="length"]');

  // ⚠ 本支最重要的一条：+v 的 verdict 表「right->wrong 0、净变化 0」
  //   是 18/23 未闭合制造出来的假象。不许让读者把它读成「+v 最安全」。
  const TR = D.trap || '';
  rec('J6 必须点破陷阱：+v 的 right->wrong=0 / 净变化=0 是未闭合造成的假象',
      !!TR
      && TR.includes(String(SD.per_direction.up.verdicts['right->wrong'] || 0))
      && TR.includes(String(SD.per_direction.up.net_change))
      && TR.includes(String(SD.per_direction.up.n_incomplete))
      && /破坏没有消失/.test(TR)
      && /看不见/.test(TR)
      && /根本没有产出答案/.test(TR)
      && Number(D.upRw) === (SD.per_direction.up.verdicts['right->wrong'] || 0)
      && Number(D.upNet) === SD.per_direction.up.net_change
      && SD.per_direction.up.n_complete < SD.n_problems / 2,
      TR ? TR.slice(0, 230) : '缺 [data-dir-trap]');

  rec('J7 不能说的两条必须印出：只有一个强度点 / 缺同范数随机方向臂',
      !!TR
      && new RegExp('只有\\s*s\\s*=\\s*' + esc(SD.strength)).test(TR)
      && /一个强度点/.test(TR)
      && /假设/.test(TR)
      && /随机方向臂/.test(TR)
      && /吸引域/.test(TR),
      TR ? TR.slice(-230) : '缺 [data-dir-trap]');

  // ==================== K 组：「跑飞」的机制 ====================
  // 方向块只说了 +v 撞上限，**没说怎么坏的**。K 组钉住机制，
  // 并且钉住一个更要紧的东西：**长度受控之后这个效应还剩多少**。
  const R2 = state.rep || {};
  const cleanCuts = RP.cut_sweep.filter(c => c.same_problem_set);
  const dirtyCuts = RP.cut_sweep.filter(c => !c.same_problem_set);
  const bestCut = cleanCuts.reduce(
    (a, b) => ((a.fisher_p_plus_vs_zero ?? 1) <= (b.fisher_p_plus_vs_zero ?? 1) ? a : b));
  const armOf = n => RP.summary.find(s => s.arm === n);

  rec('K0 重复退化块存在，且受控切点上的 5 个数字与产物逐值相同（可见文案 + 属性两处）',
      !R2.missing
      && Number(R2.words) === bestCut.words
      && Number(R2.plus) === bestCut.plus_v.n_strong
      && Number(R2.zero) === bestCut.zero.n_strong
      && Number(R2.minus) === bestCut.minus_v.n_strong
      && Math.abs(Number(R2.p) - bestCut.fisher_p_plus_vs_zero) < 1e-9
      && Number(R2.maxPlus) === armOf('plus_v').rep_k_max
      && Number(R2.maxZero) === armOf('zero').rep_k_max
      && Number(R2.maxMinus) === armOf('minus_v').rep_k_max
      && Number(R2.k) === RP.k_grams
      && Number(R2.thresh) === RP.strong_repeat_threshold,
      R2.missing ? '缺 [data-repetition]'
        : `words=${R2.words} ${R2.zero}/${R2.minus}/${R2.plus} `
          + `p=${R2.p} max=${R2.maxZero}/${R2.maxMinus}/${R2.maxPlus} `
          + `k=${R2.k} thresh=${R2.thresh} | 产物 words=${bestCut.words} `
          + `${bestCut.zero.n_strong}/${bestCut.minus_v.n_strong}/`
          + `${bestCut.plus_v.n_strong} `
          + `p=${bestCut.fisher_p_plus_vs_zero} max=`
          + `${armOf('zero').rep_k_max}/${armOf('minus_v').rep_k_max}/`
          + `${armOf('plus_v').rep_k_max}`);

  // 机制必须说清楚是「逐字重复」，且把三臂的最强重复次数都印出来。
  rec('K1 机制必须印出「逐字重复」并给出三臂的最强重复次数',
      !!R2.mechanism
      && /逐字重复/.test(R2.mechanism)
      && R2.mechanism.includes(String(armOf('plus_v').rep_k_max))
      && R2.mechanism.includes(String(armOf('zero').rep_k_max))
      && R2.mechanism.includes(String(armOf('minus_v').rep_k_max))
      && R2.mechanism.includes(String(RP.k_grams))
      && R2.mechanism.includes(String(RP.strong_repeat_threshold))
      // 机制层面的硬事实：+v 的最强重复必须明显超过两个对照臂。
      // 这是**不依赖 p** 的那一半结论，必须由判据守住。
      && armOf('plus_v').rep_k_max > 3 * armOf('zero').rep_k_max,
      R2.mechanism ? R2.mechanism.slice(0, 230) : '缺 [data-rep-mechanism]');

  const CTRL = R2.items.controlled || '';
  rec('K2 长度受控那一格必须印出，且 p 未到 0.05 时必须标「弱证据」（不许多余地写成已证实）',
      bestCut.fisher_p_plus_vs_zero > 0.05
      && CTRL.includes(String(bestCut.plus_v.n_strong))
      && CTRL.includes(String(bestCut.zero.n_strong))
      && CTRL.includes(String(bestCut.minus_v.n_strong))
      && CTRL.includes(bestCut.fisher_p_plus_vs_zero.toFixed(3))
      && /没到\s*0\.05/.test(CTRL)
      && /弱证据/.test(CTRL)
      && !/已过\s*0\.05/.test(CTRL)
      // ⚠ 这里原本写的是 Number(R2.sameSet) === true，而面板给的是
      //   String(true) = "true"，Number("true") 是 **NaN**，NaN === true 恒假
      //   ⇒ 判据在干净源码上就是红的。布尔量不能靠 String()/Number() 过属性。
      && Number(R2.sameSet) === 1
      && bestCut.plus_v.n_eligible === bestCut.zero.n_eligible
      && bestCut.plus_v.n_eligible === bestCut.minus_v.n_eligible,
      CTRL ? CTRL.slice(0, 240) : '缺 [data-rep-item="controlled"]');

  // ⚠ 本组最容易犯的错：把 3200 词那档的 p=0.016 印成结论。
  //   那一档三臂入选的题集不同（按长度筛题），是**选择效应**。
  const CF = R2.items.confounded || '';
  rec('K3 必须点名「窗口放大后的更小 p 不能引用」，并印出被污染的切点',
      !!CF
      && dirtyCuts.length > 0
      && dirtyCuts.every(c => R2.dirtyCuts.includes(String(c.words)))
      && /不能引用/.test(CF)
      && /题集不同/.test(CF)
      && /筛/.test(CF)
      && dirtyCuts.every(c => CF.includes(c.fisher_p_plus_vs_zero.toFixed(3)))
      // 反向断言：任何一档被标为 CONFIRMED 的，都必须真的是同题入选
      && dirtyCuts.every(c => c.same_problem_set === false),
      CF ? CF.slice(0, 240) : '缺 [data-rep-item="confounded"]');

  // 机制结论必须**分两层**：可见的重复（不依赖 p）与统计分离（只有弱证据）。
  const WY = R2.items.why || '';
  rec('K4 机制结论必须分两层：重复可见 ≠ 重复显著，强的证据仍是闭合率',
      !!WY
      && /不依赖那个\s*p|不依赖.{0,6}p/.test(WY)
      && /弱证据/.test(WY)
      && WY.includes(SD.blew_up.mcnemar_exact_p.toExponential(2))
      && /闭合率/.test(WY)
      && /不受文本长度影响/.test(WY),
      WY ? WY.slice(0, 240) : '缺 [data-rep-item="why"]');

  const CN = R2.cannot || '';
  rec('K5 不能说的必须印出：缺同范数随机方向臂 / 只是一个强度点一层 / 重复不是全部机制',
      !!CN
      && /随机方向臂/.test(CN)
      && /缺同范数/.test(CN)
      && /一个强度点/.test(CN)
      && /一层|一\s*层/.test(CN)
      // 面板上写的是「不能说『重复就是跑飞的全部机制』」——
      // 判据必须读**页面上真有的那串字**，不是我脑子里转述过的那句。
      && /重复就是跑飞的全部机制/.test(CN)
      && /不能说/.test(CN),
      CN ? CN.slice(0, 240) : '缺 [data-rep-cannot]');

  // ==================== M 组：主张降级器 ====================
  // 这组盯的是一把**反过来用**的尺子：拿到一句已经写好的结论，
  // 报出它实际站得住的第几级。M 组最容易出的错是**只印工具、不印限制** ——
  // 产物自己写明了「对外部文献的判定力未经检验」，页面就必须也印。
  const C3 = state.ca || {};
  const SA = CA.samples;
  const byId = id => SA.find(x => x.id === id);

  rec('M0 主张降级块存在，且三个样本的声明/实测级别与产物逐值相同（可见文案 + 属性两处）',
      !C3.missing
      && Number(C3.n) === SA.length
      && Number(C3.nlevels) === CA.levels.length
      && Number(C3.l0declared) === byId('l0-only').audit.declared_level
      && Number(C3.l0supported) === byId('l0-only').audit.max_level_supported
      && Number(C3.l2declared) === byId('l2-no-specificity').audit.declared_level
      && Number(C3.l2supported) === byId('l2-no-specificity').audit.max_level_supported
      && Number(C3.selfDeclared) === byId('project-confidence-claim').audit.declared_level
      && Number(C3.selfSupported) === byId('project-confidence-claim').audit.max_level_supported
      && CA.levels.length === 8,
      C3.missing ? '缺 [data-claim-audit]'
        : `n=${C3.n} levels=${C3.nlevels} l0=${C3.l0declared}/${C3.l0supported} `
          + `l2=${C3.l2declared}/${C3.l2supported} self=${C3.selfDeclared}/${C3.selfSupported} `
          + `| 产物 n=${SA.length} levels=${CA.levels.length} `
          + `l0=${byId('l0-only').audit.declared_level}/${byId('l0-only').audit.max_level_supported} `
          + `l2=${byId('l2-no-specificity').audit.declared_level}/${byId('l2-no-specificity').audit.max_level_supported} `
          + `self=${byId('project-confidence-claim').audit.declared_level}/${byId('project-confidence-claim').audit.max_level_supported}`);

  const ML0 = C3.items.l0 || '';
  rec('M1 换方向存活测试必须印出，且 L0 样本在产物里确实存活',
      byId('l0-only').audit.max_level_supported === 0
      && byId('l0-only').audit.survives_direction_substitution === true
      && ML0.includes(String(byId('l0-only').audit.declared_level))
      && ML0.includes(String(byId('l0-only').audit.max_level_supported))
      && /换个随机方向逐字成立/.test(ML0)
      && Number(C3.l0survives) === 1
      // 反向断言：只有 L0/L1 允许存活
      && CA.levels.filter(l => l.level <= 1).length === 2,
      ML0 ? ML0.slice(0, 220) : '缺 [data-ca-item="l0"]');

  const ML6 = C3.items.l6 || '';
  rec('M2 「声明 L6 ⇒ 实测降到 L4」必须印出，并点名缺的是随机臂',
      byId('l6-no-random-arm').audit.declared_level === 6
      && byId('l6-no-random-arm').audit.max_level_supported < 6
      && ML6.includes('6') && ML6.includes(String(byId('l6-no-random-arm').audit.max_level_supported))
      && /随机方向臂/.test(ML6)
      && /排除不了/.test(ML6)
      && !!byId('l6-no-random-arm').audit.cheapest_next_step,
      ML6 ? ML6.slice(0, 230) : '缺 [data-ca-item="l6"]');

  const MSL = C3.items.self || '';
  rec('M3 本项目自己的那句话必须被这把尺子量过，并印出实测级别',
      MSL.includes(String(byId('project-confidence-claim').audit.declared_level))
      && MSL.includes(String(byId('project-confidence-claim').audit.max_level_supported))
      && /只到/.test(MSL)
      && /随机臂/.test(MSL)
      // 诚实性：尺子对自己的判定必须是**降级**，不能给高分
      && byId('project-confidence-claim').audit.overreach_vs_declared === true,
      MSL ? MSL.slice(0, 220) : '缺 [data-ca-item="self"]');

  const MCC = C3.coverage || '';
  rec('M4 覆盖限制必须印出：对外部文献的判定力未经检验（不许只印工具不印限制）',
      !!MCC
      && /覆盖限制/.test(MCC)
      && /不.{0,3}凭印象编造|未经检验/.test(MCC)
      && MCC.includes(CA.coverage_limitation.consequence.slice(0, 12))
      && CA.coverage_limitation.status === "本轮未纳入",
      MCC ? MCC.slice(0, 230) : '缺 [data-ca-coverage]');

  const MCE = C3.ceiling || '';
  rec('M5 随机臂分位数上限必须印出，且不许出现魔法阈值式的「n≥8 就够」',
      !!MCE
      && /不设魔法阈值/.test(MCE)
      && MCE.includes('n/(n+1)')
      && /换.{0,4}随机方向/.test(MCE)
      // 反向断言：产物里真的没有魔法阈值这句话
      && !/n\s*[≥>=]\s*\d+\s*(就够|足够)/.test(CA.random_ceiling_note),
      MCE ? MCE.slice(0, 230) : '缺 [data-ca-ceiling]');
} catch (e) {
  rec('X 脚本崩了', false, String((e && e.stack) || e).slice(0, 300));
} finally {
  cdp.close(); proc.kill('SIGKILL');
}

const pass = R.filter(x => x.p).length;
console.log(`\n=== ${pass}/${R.length} passed ===`);
R.filter(x => !x.p).forEach(x => console.log('FAIL: ' + x.n));
process.exit(pass === R.length ? 0 : 1);
