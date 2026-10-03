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
          // ⚠ 同上面 arm 分支的老教训：缺失时返回**完整**的键（值置
          //   null），不能让下游 P.items.flips 抛 TypeError 被外层
          //   catch 吞掉 —— 那会把 I 组后面几条一起记成「装置错」，
          //   看着像「只有 I0 红」。
          // ⚠ 这整段在一个**模板字面量**里：反斜杠要写两遍（\\s），
          //   且注释里绝不能出现反引号 —— 两者都会以很难看懂的方式
          //   把整个 eval 打挂，报错还指在第 64 行的开头。
          if (!p) return { missing: true, text: '', items: {}, notClaimed: null,
                           net: null, flips: null, needed: null,
                           shipped: null, batch: null, ciLo: null, ciHi: null,
                           outDomain: null };
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
            net: g('data-net-change'), flips: g('data-flips'),
            needed: g('data-flips-needed'), shipped: g('data-n-shipped'),
            batch: g('data-n-batch'), ciLo: g('data-ci-lo'), ciHi: g('data-ci-hi'),
            outDomain: g('data-out-domain'),
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

  /* ==================== I 组：「净变化 0」是欠功效不是零效应 ==================== */
  // 这一块补的是面板**自己**的头条数字。原来印的是
  //   「Net change in correct answers: 0. Steering moved things; it did
  //    not make them better.」
  // 后半句把「没算出来」读成了「没有」—— 而这 10 题的分母是按
  // 「两臂答案不同」筛出来的，符号检验要 10 里 6 个同向翻转才够 p<0.05，
  // 实测 2 个一正一反。判据盯的不是数字对不对（数字本来就对），
  // 盯的是**这个 0 被允许读成什么**。
  const P = state.power || {};
  const NC = P.notClaimed || '';
  const f3 = n => Number(n).toFixed(3);
  const esc = s => String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

  rec('I0 功效块存在，且六个关键数字与 answer_power.json 逐值相同',
      !P.missing
      && Number(P.net) === PW.net_change
      && Number(P.flips) === PW.flips
      && Number(P.needed) === PW.flips_needed_for_p05
      && Number(P.shipped) === PW.n_shipped
      && Number(P.batch) === PW.n_problems_in_batch
      && Math.abs(Number(P.ciLo) - PW.up_rate_ci95[0]) < 1e-12
      && Math.abs(Number(P.ciHi) - PW.up_rate_ci95[1]) < 1e-12,
      P.missing ? '缺 [data-answer-power]'
        : `net=${P.net} flips=${P.flips} needed=${P.needed} `
          + `n=${P.shipped}/${P.batch} ci=[${P.ciLo}, ${P.ciHi}] | 产物 `
          + `net=${PW.net_change} flips=${PW.flips} needed=${PW.flips_needed_for_p05} `
          + `n=${PW.n_shipped}/${PW.n_problems_in_batch} `
          + `ci=[${PW.up_rate_ci95[0]}, ${PW.up_rate_ci95[1]}]`);

  // 屏幕上三个地方说同一件事：verdict 标签、功效块的 data-net-change、
  // 另一份产物。任一处漂移都会让读者看到两个互相打架的净变化。
  const chipNum = k => {
    const v = state.verdicts.find(x => x.k === k);
    const m = v && v.t.match(/\d+/);
    return m ? Number(m[0]) : NaN;
  };
  const netFromChips = chipNum('wrong->right') - chipNum('right->wrong');
  const netFromAns = (ANS.selection.by_verdict['wrong->right'] || 0)
                   - (ANS.selection.by_verdict['right->wrong'] || 0);
  rec('I1 屏幕上的「净变化」必须等于同屏 verdict 标签推出的净变化（三处一致）',
      Number.isFinite(netFromChips)
      && netFromChips === netFromAns
      && netFromChips === Number(P.net)
      && netFromChips === PW.net_change,
      `verdict 标签 ${chipNum('wrong->right')}−${chipNum('right->wrong')}`
      + `=${netFromChips} | data-net-change=${P.net} | answer_power=${PW.net_change}`
      + ` | answer_readout 推出=${netFromAns}`);

  // ⚠ 反向断言：零效应读法**只能**以否定句形式出现。
  //   「干预对答案正确性无影响」这句话在正确版本里出现且仅出现一次，
  //   并且被「不能说」领着；一旦被改成正面陈述，这条立刻红。
  const zeroClaimCount = (NC.match(/干预对答案正确性无影响/g) || []).length;
  rec('I2 「净变化 0」必须标为欠功效，且「无影响」只允许出现在否定句里',
      !/did not make them better/i.test(state.text)
      && /欠功效/.test(P.text)
      && /不是零效应/.test(P.text)
      && zeroClaimCount === 1
      && new RegExp('不能说[^。]*干预对答案正确性无影响').test(NC),
      `欠功效=${/欠功效/.test(P.text)} 不是零效应=${/不是零效应/.test(P.text)} `
      + `「无影响」出现 ${zeroClaimCount} 次（在 not_claimed 内，`
      + `被「不能说」领着=${new RegExp('不能说[^。]*干预对答案正确性无影响').test(NC)}）`
      + ` | 旧零效应句仍在=${/did not make them better/i.test(state.text)}`);

  // 为什么 0 不是零效应：**核心算术必须印在屏幕上**。
  const FI = P.items.flips || '';
  rec('I3 必须印出「要 p<0.05 需要 N 个同向翻转」与本设计上限',
      new RegExp('需要\\s*' + esc(PW.flips_needed_for_p05) + '\\s*个同向翻转').test(FI)
      && new RegExp('上限只有\\s*' + esc(PW.n_shipped) + '\\s*个').test(FI)
      && new RegExp('符号检验').test(FI)
      && new RegExp('p\\s*<\\s*0\\.05').test(FI)
      && FI.includes(String(PW.flips))
      && FI.includes(String(PW.two_sided_sign_p_if_all_same_direction)),
      FI ? FI.slice(0, 170) : '缺 [data-power-item="flips"]');

  const CI = P.items.ci || '';
  rec('I4 翻转率 95% CI 两端与产物一致（上界宽这件事不许被压窄）',
      CI.includes(f3(PW.up_rate_ci95[0]))
      && CI.includes(f3(PW.up_rate_ci95[1]))
      && new RegExp('Clopper').test(CI)
      && (PW.up_rate_ci95[1] - PW.up_rate_ci95[0]) > 0.1,
      CI ? CI.slice(0, 170) : '缺 [data-power-item="ci"]');

  // 「不能说的话」四条：非随机样本 / 单轴单档 / 正臂缺失 / L7 未测。
  rec('I5 「不能说的话」必须含：非随机样本 / 单轴单档 / L7 一次都没测',
      !!NC
      && /随机样本/.test(NC)
      && /筛过|挑出来/.test(NC)
      && NC.includes(PW.direction)
      && NC.includes(String(PW.strength))
      && /confidence_up/.test(NC)
      && /L7/.test(NC)
      && /一次都没测/.test(NC),
      NC ? NC.slice(0, 210) : '缺 [data-power-not-claimed]');

  rec('I6 必须印出选择效应：入选条件之一是「两臂答案不同」，且 23→10 与产物一致',
      Number(P.batch) === PW.n_problems_in_batch
      && Number(P.shipped) === PW.n_shipped
      && P.text.includes(String(PW.n_problems_in_batch))
      && P.text.includes(String(PW.n_shipped))
      && /两臂答案不同/.test(P.text),
      P.text.slice(0, 150));

  const LN = P.items.length || '';
  rec('I7 长度偏倚必须印出，步数比区间与产物一致',
      /长度偏倚/.test(LN)
      && /步数比/.test(LN)
      && LN.includes(String(PW.steps_ratio_min))
      && LN.includes(String(PW.steps_ratio_max)),
      LN ? LN.slice(0, 170) : '缺 [data-power-item="length"]');

  // ⚠ 阴性结论必须交代分母的去向。这 13 题**在产物里没有分开记**，
  //   所以正确写法是承认「不知道」，不是编一个「答案未变」。
  const CE = P.items.ceiling || '';
  rec('I8 剩余题的去向必须承认「没分开记」，不许替它编',
      /上界/.test(CE)
      && /没有分开记|没分开记/.test(CE)
      && /不替它编|不能编/.test(CE)
      && CE.includes(String(PW.n_problems_in_batch - PW.n_shipped))
      && CE.includes(`${PW.n_shipped}/${PW.n_problems_in_batch}`),
      CE ? CE.slice(0, 190) : '缺 [data-power-item="ceiling"]');

  // ⚠ 入选的 10 题里有 2 题的两臂答案都超出 AIME 答案域（0–999，
  //   表里能看到 3069 → 1007）。它们被归进 wrong->wrong，
  //   对净变化**贡献 0**，所以 §4.14 的任何结论都不受影响。
  //   但面板必须说清「这两题的错是域外判定」—— 不说的话，
  //   读者会以为它们是与一个合法答案比对后判错的。
  const DM = P.items.domain || '';
  rec('I9 域外答案的题必须被点名，并说明「域外判定、对净变化无贡献」',
      Number(P.outDomain) === PW.labels_not_both_in_domain.length
      && PW.labels_not_both_in_domain.length > 0
      && DM.includes(String(PW.labels_not_both_in_domain.length))
      && PW.labels_not_both_in_domain.every(l => DM.includes(l))
      && /答案域之外/.test(DM)
      && /没有贡献/.test(DM)
      && /域外判定/.test(DM),
      DM ? DM.slice(0, 200) : '缺 [data-power-item="domain"]'
        + ` | 产物 out-of-domain = ${JSON.stringify(PW.labels_not_both_in_domain)}`);
} catch (e) {
  rec('X 脚本崩了', false, String((e && e.stack) || e).slice(0, 300));
} finally {
  cdp.close(); proc.kill('SIGKILL');
}

const pass = R.filter(x => x.p).length;
console.log(`\n=== ${pass}/${R.length} passed ===`);
R.filter(x => !x.p).forEach(x => console.log('FAIL: ' + x.n));
process.exit(pass === R.length ? 0 : 1);
