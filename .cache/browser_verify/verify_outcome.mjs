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
const LIT = JSON.parse(readFileSync(DATA + '/lit_audit.json', 'utf8'));
// ⚠ 第二十八笔：提到模块层，因为**渲染层**也要用它（见 K6/K7）。
//   E 组在下面另有一处同名局部变量，那是刻意保持 E 组「纯产物层」的自述；
//   那里改成复用这一份，声明本身不动。
const VR = JSON.parse(readFileSync(DATA + '/vector_roles.json', 'utf8'));

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
    rec('X0 页面必须真的加载出来（死 URL 不得让本脚本报 PASS/SKIP）', liveOk,
      `href=${L.href} bodyLen=${L.bodyLen} `
      + `data-outcome="${L.outcome}" canvas=${L.canvases} script[src]=${L.scripts}`
      + (isErr ? '  ← chrome-error 页：继续跑下去只会崩，红的计数会被污染'
               : (!isLoopback ? '  ← 不是 127.0.0.1 的页面（环境变量传错了？）' : '')));
    if (!liveOk) {
      try { cdp.close(); } catch {}
      try { proc.kill('SIGKILL'); } catch {}
      console.log(`\n=== 0/${R.length} passed ===`);
      console.log('页面没加载 ⇒ 后面的判据**一条都没跑**（这不是「通过」，也不是「装置崩」）');
      process.exit(1);
    }
  }

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
                           upNet: null, opposite: null, lenP: null,
                           downOwn: null, upOwn: null,
                           zeroClosedDownBlew: null, downClosedZeroBlew: null };
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
            // 第十七笔：两个口径的属性。缺分支必须返回**完整**的键，
            //   否则下面 B 组取到 undefined 会打成 NaN 而不是 null。
            downOwn: g('data-down-own'), upOwn: g('data-up-own'),
            zeroClosedDownBlew: g('data-zero-closed-down-blew'),
            downClosedZeroBlew: g('data-down-closed-zero-blew'),
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
            l6declared: g('data-ca-l6-declared'),
            l6supported: g('data-ca-l6-supported'),
            selfDeclared: g('data-ca-self-declared'),
            selfSupported: g('data-ca-self-supported'),
          };
        })(),
        lit: (() => {
          const d = el.querySelector('[data-lit-audit]');
          if (!d) return { missing: true, text: '', items: {}, rule: null,
                           detail: null, rows: [] };
          const g = a => d.getAttribute(a);
          const items = {};
          d.querySelectorAll('[data-lit-item]').forEach(li => {
            items[li.getAttribute('data-lit-item')] =
              (li.innerText || '').replace(/\\s+/g, ' ').trim();
          });
          const q = sel => { const n = d.querySelector(sel);
            return n ? (n.innerText || '').replace(/\\s+/g, ' ').trim() : null; };
          const rows = [];
          d.querySelectorAll('[data-lit-row]').forEach(li => {
            rows.push({ id: li.getAttribute('data-lit-row'),
                        // ⚠ 必须用 textContent，**不能用 innerText**：
                        //   引述在折叠的 <details> 里，而 innerText 尊重渲染 ——
                        //   折叠时它只给 <summary> 的可见文字，
                        //   于是 N4 在**干净源码上**就红了。
                        //   N4 验的是「引述有没有被改写」（数据忠实度），
                        //   不是「读者看不看得见」；后者由渲染守卫负责。
                        text: (li.textContent || '').replace(/\\s+/g, ' ').trim() });
          });
          return {
            missing: false,
            text: (d.innerText || '').replace(/\\s+/g, ' ').trim(),
            items, rule: q('[data-lit-rule]'),
            // <details> 折叠 ⇒ innerText 只给 <summary>，必须用 textContent
            detail: (d.querySelector('[data-lit-detail]')?.textContent || '')
                      .replace(/\\s+/g, ' ').trim(),
            rows,
            n: g('data-lit-n'), claim: g('data-lit-claim'),
            ctrl: g('data-lit-ctrl'),
            sameNorm: g('data-lit-samenorm'),
            sameNormUnknown: g('data-lit-samenorm-unknown'),
            renderedFields: g('data-lit-rendered-fields'),
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
  // ⚠⚠⚠ 第二十九笔：这一条原来**要求那几个字面量出现在页面上**：
  //     !!state.note && /0\.3%|0\.3/.test(state.note) && /30\.4|29\.8/.test(state.note)
  //   那五个数（0.02 / 5.4 / 0.3% / 29.8 / 30.4）在仓库里找不到任何源，
  //   而散文写着「Measured on this recording」—— 可它们是编译期常量，
  //   对每条录制都一样 ⇒ 那句话按构造是假的。
  //   ⇒ 旧判据不是「漏了检查」，它是**把缺陷钉死了**：
  //     页面一改对（不再印不可复现的数），判据反而转红。
  //   这与第十三/二十六笔「判据与产品共用同一份手抄」是同一族，
  //   但方向相反：那边是判据也抄了一份所以核不出，
  //   这边是**判据要求那一份必须存在**。
  // 现在核三件事：① 回答了那个问题 ② 明说这个比较**没有**在这里复现
  //              ③ 那个不可复现的数与「实测」说法不许回来。
  // ⚠ 诊断行逐项列，不只印原文：第二十六笔 S9 那个教训
  //   （三段嵌套三元只报第一个非零原因，把同批的独立信号盖住了）。
  const nt = state.note || '';
  const g9 = {
    回答了问题: /inject/i.test(nt),
    提到三维: /3-?D|three dimensions/i.test(nt),
    明说未复现: /not recomputed|does not print a number/i.test(nt),
    '无 29.8/30.4': !/29\.8|30\.4/.test(nt),
    '无 0.3%': !/0\.3\s*%/.test(nt),
    '无 L1 distance': !/L1\s+distance/i.test(nt),
    '无 Measured on this recording': !/Measured on this recording/i.test(nt),
  };
  rec('G9 解释「注入在 3D 里几乎看不见」时，不许印无法复现的数，也不许自称实测',
      !!state.note && Object.values(g9).every(Boolean),
      `逐项：${Object.entries(g9).map(([k, v]) => `${k}=${v ? '✓' : '✗'}`).join('  ')}`
      + `　| 原文 ${nt.slice(0, 150)}`);

  const errs = page.events
    .filter(e => e.method === 'Runtime.consoleAPICalled' && e.params.type === 'error')
    .map(e => (e.params.args || []).map(a => a.value ?? a.description ?? '').join(' '))
    .filter(t => !/favicon|Failed to load resource/i.test(t));
  rec('G10 页面无 console error', errs.length === 0,
      errs.length ? errs.slice(0, 2).join(' | ') : 'none');

  /* ==================== A 组：arm_asymmetry 的覆盖面声明与散文 ==================== */
  // ⚠ **这一组读的是产物层，不是渲染层** —— 与下面的 H 组正好相反，说清楚：
  //
  //   H 组问「面板上印的那个数对不对」（读 DOM）
  //   A 组问「产物自己那两个没人看的散文段有没有说谎」（读 JSON 文件）
  //
  // 为什么值得单列一组：`arm_asymmetry.json` 的 `verdict` / `not_claimed`
  // 在 `InterventionOutcomePanel.tsx` 里**只声明了类型、一行都没渲染**
  // （面板那块是从 layer / strength / n_pairs / metrics 现写的）。
  // 所以全仓没有任何渲染层判据能碰到这两段散文 —— 第十六笔之前，
  // 那五个数（-0.0344 / 0.0060 / +0.0392 / 0.0046 / 0.74）**无人核**。
  // ⇒ 本组能证明「产物散文与 cot_texts 现算一致」，
  //   **不能**证明「读者在页面上看到的就是这些数」—— 后者是 H 组的活。
  const axAXES = JSON.parse(readFileSync(DATA + '/axis_readouts.json', 'utf8'));
  const axAX = Object.keys(axAXES.axes || {}).sort();
  const axOTHER = axAX.filter(x => !x.startsWith('confid'));

  // 从 cot_texts 现算，不读 arm_asymmetry 的任何字段。
  // 强度档 / 层 / 符号数都**由数据唯一确定**，取不到唯一值就不判（报未判）。
  const axNzS = [...new Set(COT.runs.map(r => Number(r['strength'])).filter(s => s !== 0))];
  const axStr = axNzS.length === 1 ? axNzS[0] : null;
  const axLy = [...new Set(COT.runs.map(r => r['layer']))];
  const axDir = [...new Set(COT.runs.map(r => r['direction']))].sort();
  const axByL = {};
  for (const r of COT.runs) (axByL[r.label] = axByL[r.label] || {})[r.direction + '|' + Number(r['strength'])] = r;
  const axPairs = axStr === null ? [] : Object.values(axByL)
    .filter(v => v['confidence_up|' + axStr] && v['confidence_down|' + axStr]);
  // ⚠ first_diverged_step 的空值代换必须与生成器**逐字同语义**：
  //   Python 写的是 `r["first_diverged_step"] or 10**9`，
  //   JS 侧对应 `|| 1e9` —— 连「0 也会被代换」这个副作用一起复刻。
  const axMF = {
    mean_logit_kl: r => r.mean_logit_kl,
    token_agreement: r => r.token_agreement,
    first_diverged_step: r => r.first_diverged_step || 1e9,
  };
  const axRC = {};
  for (const am of ARM.metrics) {
    const f = axMF[am.metric];
    if (!f) continue;
    const ds = axPairs.map(v => f(v['confidence_up|' + axStr]) - f(v['confidence_down|' + axStr]));
    const n = ds.length;
    if (n < 2) continue;
    const m = ds.reduce((a, b) => a + b, 0) / n;
    const sem = Math.sqrt(ds.reduce((a, b) => a + (b - m) * (b - m), 0) / (n - 1)) / Math.sqrt(n);
    axRC[am.metric] = { n, mean: m, sem, t: sem ? m / sem : null };
  }
  // 数值比对按**打印精度**给容差（半个末位），不是字符串相等 ——
  // 散文改对了精度、判据不该跟着红；散文算错了，差一个末位也必红。
  const axNear = (a, b, dp) => Number.isFinite(a) && Number.isFinite(b)
    && Math.abs(a - b) <= 0.5 * Math.pow(10, -dp);

  rec('A0 前置：层唯一 / 非零强度唯一 / 恰好 ±v 两臂 / 23 个完整配对（取不到就不判）',
      axLy.length === 1 && axStr !== null && axDir.length === 2
      && axDir.join() === 'confidence_down,confidence_up' && axPairs.length === ARM.n_pairs,
      `层=${JSON.stringify(axLy)} 非零强度=${JSON.stringify(axNzS)} 方向=${JSON.stringify(axDir)} `
      + `现算配对=${axPairs.length} 产物 n_pairs=${ARM.n_pairs}`);

  rec('A1 metrics 的配对差 / 标准误 / t 与 cot_texts 现算逐个吻合（±半个末位）',
      Object.keys(axRC).length === ARM.metrics.length
      && ARM.metrics.every(am => {
          const r = axRC[am.metric];
          return r && axNear(am.paired_diff, r.mean, 10) && axNear(am.paired_sem, r.sem, 10)
            && axNear(am.t, r.t, 10);
        }),
      Object.keys(axRC).map(k => `${k} diff ${ARM.metrics.find(a => a.metric === k).paired_diff}`
        + ` vs ${axRC[k].mean} / sem ${ARM.metrics.find(a => a.metric === k).paired_sem}`
        + ` vs ${axRC[k].sem} / t ${ARM.metrics.find(a => a.metric === k).t} vs ${axRC[k].t}`).join('\n       '));

  // ---- A2：那五个**散文里**的数 ----
  // 判据读的是产物层，所以要**按字段切作用域**：先用锚点短语定位到
  // 具体那一句，再解析数字。朴素 haystack 在这里会造假绿
  // （`0.0344` 在别处也出现过，改对一处仍全绿）。
  const axVD = ARM.verdict || '';
  const axGrab = (s, re) => { const m = s.match(re); return m ? m.slice(1).map(Number) : null; };
  const axKl = axGrab(axVD, /KL 配对差\s*([+-][\d.]+)\s*±\s*([\d.]+)\)/);
  const axAg = axGrab(axVD, /一致率也更低\s*\(([+-][\d.]+)\s*±\s*([\d.]+)\)/);
  // ⚠ t 这里**不能**照抄上面两处的 `[+-]`：判决里 KL 差与一致率差是
  //   `%+.4f`（强制带号），而 t 是 `%.2f` —— 正的 t 印成 `0.74`，没有 +。
  //   第一版写死 `[+-][\d.]+` ⇒ 这条判据在**干净数据上就抓不到 t**，
  //   而报出来的形态是「散文 t=未抓到」，看着像产物坏了，其实是判据坏了。
  const axTv = axGrab(axVD, /\(t=([+-]?\d+(?:\.\d+)?),\s*CI 跨 0\)/);
  rec('A2 散文 verdict ① 的四个数（KL 差±误、一致率差±误）与现算吻合',
      !!axKl && !!axAg && !!axRC.mean_logit_kl && !!axRC.token_agreement
      && axNear(axKl[0], axRC.mean_logit_kl.mean, 4) && axNear(axKl[1], axRC.mean_logit_kl.sem, 4)
      && axNear(axAg[0], axRC.token_agreement.mean, 4) && axNear(axAg[1], axRC.token_agreement.sem, 4),
      axKl && axAg ? `散文 KL ${axKl[0]}±${axKl[1]} / 一致率 ${axAg[0]}±${axAg[1]} | 现算 `
        + `${axRC.mean_logit_kl.mean.toFixed(4)}±${axRC.mean_logit_kl.sem.toFixed(4)} / `
        + `${axRC.token_agreement.mean.toFixed(4)}±${axRC.token_agreement.sem.toFixed(4)}`
        : `锚点没抓到（KL=${!!axKl} 一致率=${!!axAg}）`);

  // ---- A3：「分不开」这句话必须挂在数据说分不开的那个量上 ----
  //   这是把散文的**语义归属**也钉住：光对上 t=0.74 没用 ——
  //   如果哪天换成另一个量分不开而散文还写 0.74，A2 仍会绿。
  const axInd = ARM.metrics.filter(x => !x.distinguishable);
  const axFd = axRC.first_diverged_step;
  rec('A3 散文 ② 的「分不开 + t=… + CI 跨 0」必须挂在数据里不可分的那一个量上',
      axInd.length === 1 && axInd[0].metric === 'first_diverged_step' && !!axTv && !!axFd
      && axNear(axTv[0], axInd[0].t, 2) && axNear(axTv[0], axFd.t, 2)
      && /首次分岔步数/.test(axVD) && /分不开/.test(axVD),
      `不可分的量=${axInd.map(x => x.metric).join() || '（无）'} 散文 t=${axTv ? axTv[0] : '未抓到'} `
      + `产物 t=${axInd[0] ? axInd[0].t : 'NA'} 现算 t=${axFd ? axFd.t.toFixed(4) : 'NA'}`);

  // ---- A4：可分性标记与 CI 的关系必须自洽 ----
  //   这是**关系**而不是数值：CI 跨 0 ⇔ distinguishable=false，
  //   换 bootstrap 种子也不该变 ⇒ 判据不依赖某一次抽样的具体端点。
  rec('A4 每个量的 distinguishable 必须等于「CI 不跨 0」，不许只靠抽样端点',
      ARM.metrics.length > 0 && ARM.metrics.every(x =>
        x.distinguishable === !(x.ci95_lo < 0 && 0 < x.ci95_hi)),
      ARM.metrics.map(x => `${x.metric}: lo=${x.ci95_lo.toFixed(3)} hi=${x.ci95_hi.toFixed(3)}`
        + ` dist=${x.distinguishable}`).join(' '));

  // ---- A5：覆盖面声明里的层 / 强度 / 轴数，源必须是被测物自己 ----
  //   「同层 20 / ±0.2 / 另外 3 条」这三个数以前是手抄字面量，
  //   现在由 arm_asymmetry.py 与 answer_power.py 各自从输入现算。
  //   本条独立现算第三遍，三方必须一致 ——
  //   **判据不许复用产物里那个数**，否则改了产物判据会跟着改。
  const axNPW = PW.n_other_named_axes, axNARM = ARM.n_other_named_axes;
  rec('A5 覆盖面声明的层/强度/「另外 N 条命名轴」三方一致（判据独立现算第三遍）',
      axLy.length === 1 && axStr !== null
      && ARM.layer === axLy[0] && ARM.strength === axStr && PW.strength === axStr
      && ARM.named_axes_total === axAX.length
      && ARM.n_dirs === axDir.length
      && axNARM === axOTHER.length && axNPW === axOTHER.length
      && axOTHER.length === axAX.length - 1
      && JSON.stringify(ARM.other_named_axes) === JSON.stringify(axOTHER)
      && JSON.stringify(PW.other_named_axes) === JSON.stringify(axOTHER),
      `层 产物=${ARM.layer}/现算=${JSON.stringify(axLy)} | 强度 产物=${ARM.strength}/${PW.strength}`
      + ` vs 现算=${axStr} | 符号数 产物=${ARM.n_dirs}/现算=${axDir.length} | 命名轴 ${axAX.length} 条 → 另外应 ${axOTHER.length} 条，`
      + `arm=${axNARM} power=${axNPW}`);

  // ---- A6：页面上印的那个 N 也必须等于现算值 ----
  //   A5 只核产物；这一条核**读者看到的那句**。用带锚点的正则取数，
  //   不用 includes —— 「3」在页面上出现过几十次。
  //   ⚠ 不能用下面 I 组的 `NC`：它在本文档后半才声明（const 有 TDZ），
  //     在这里引用会把整条判据打成 ReferenceError。
  const axNCtxt = (state.power && state.power.notClaimed) || '';
  const axShown = axNCtxt.match(/另外\s*(\d+)\s*条命名轴/);
  rec('A6 页面上「另外 N 条命名轴」的 N 必须等于现算值（带锚点取数，非 includes）',
      !!axShown && Number(axShown[1]) === axOTHER.length,
      axShown ? `页面印「另外 ${axShown[1]} 条命名轴」 | 现算 = ${axOTHER.length}`
            : `没在 [data-power-not-claimed] 里抓到锚点；原文片段：${axNCtxt.slice(-140)}`);

  // ---- A7：产物散文**未渲染**这件事必须被说出来 ----
  //   防的是下一位读者把 A2/A3 当成「页面已核」。反向断言：
  //   页面上不许出现这两段散文的原文（否则就变成另一套文案，得单独核）。
  //   ⚠ 锚点取**短而独有**的片段，不是整句 —— 整句匹配一旦将来
  //     标点微调就会假绿，而 A7 的作用恰恰是「证明没渲染」。
  const axVFrag = '不再是两个并排的中位数';
  const axNFrag = '不能把配对差的 t 值读成';
  rec('A7 产物那两段散文确实未渲染到页面（本组只核产物层，必须说清）',
      !(state.text || '').includes(axVFrag) && !(state.text || '').includes(axNFrag),
      `页面含 verdict 独有片段「${axVFrag}」=${(state.text || '').includes(axVFrag)}；`
      + `含 not_claimed 独有片段「${axNFrag}」=${(state.text || '').includes(axNFrag)}`);


  /* ==================== B 组：steer_directions 的两个闭合口径 ==================== */
  // ⚠ 同样先说清层级：B 组**大半在产物层**（从已发布的 cot_texts.json 独立
  //   现算 19 个量），只有 B5/B6 读 DOM。与 A 组一样，这里任何一条都**不能**
  //   单独当作「读者看到的就是这些数」的证据。
  //
  // ⚠ 为什么全部从 cot_texts.json 算，而不是生成器读的那个 journal：
  //   生成器读 `.cache/32k_journal/cot_divergence_32k.json`（本地中间产物），
  //   判据若也读它，两边就共用同一份**没被核过的**输入。
  //   已逐条核对：journal 的 92 条 run 与 cot_texts 的 92 条在
  //   `closed_think` / `n_steps` / `mean_logit_kl` 上**零处不一致**
  //   ⇒ 用已发布的那份是等价且更强的选择（它至少经过 json_strict 与面板渲染）。
  const bxBy = {};
  for (const r of COT.runs) {
    (bxBy[r.label] = bxBy[r.label] || {})[r.direction + '|' + Number(r['strength'])] = r;
  }
  const bxLabels = Object.keys(bxBy).sort();
  const bxC = (l, dirn, st) => {
    const r = bxBy[l][dirn + '|' + st];
    return r ? !!r.closed_think_primary : false;
  };
  const bxN = (l, dirn, st) => {
    const r = bxBy[l][dirn + '|' + st];
    return r ? Number(r.n_steps) : 0;
  };
  const bxStrs = [...new Set(COT.runs.map(r => Number(r['strength'])).filter(s => s !== 0))];
  const bxSt = bxStrs.length === 1 ? bxStrs[0] : null;
  const bxLayers = [...new Set(COT.runs.map(r => r['layer']))];
  const bxZc = bxLabels.filter(l => bxC(l, 'confidence_up', 0) && bxC(l, 'confidence_down', 0));
  const bxOwn = dirn => bxLabels.filter(l => bxC(l, dirn, bxSt)).length;
  const bxComp = dirn => bxLabels.filter(l => bxC(l, dirn, 0) && bxC(l, dirn, bxSt)).length;
  // 四格：只在零臂闭合的题里，按 (up 闭合?, down 闭合?) 分
  const bxBoth = bxZc.filter(l => bxC(l, 'confidence_up', bxSt) && bxC(l, 'confidence_down', bxSt));
  const bxUpOnly = bxZc.filter(l => !bxC(l, 'confidence_up', bxSt) && bxC(l, 'confidence_down', bxSt));
  const bxDownOnly = bxZc.filter(l => bxC(l, 'confidence_up', bxSt) && !bxC(l, 'confidence_down', bxSt));
  const bxNeither = bxZc.filter(l => !bxC(l, 'confidence_up', bxSt) && !bxC(l, 'confidence_down', bxSt));
  // 步数比：生成器用 n_steps（不是 reason_len_ratio），且跳过 0
  const bxRatio = dirn => bxLabels
    .map(l => [bxN(l, dirn, 0), bxN(l, dirn, bxSt)])
    .filter(([a, b]) => a && b).map(([a, b]) => b / a);
  // 中位数：Python statistics.median 对偶数长度取中间两个的均值
  const bxMedian = arr => {
    const s = [...arr].sort((x, y) => x - y), h = s.length >> 1;
    return s.length % 2 ? s[h] : (s[h - 1] + s[h]) / 2;
  };
  // 组合数：Pascal 表，避免任何浮点近似（n ≤ 64 足够这批数据）
  const bxCmb = (() => {
    const T = [[1]];
    for (let n = 1; n <= 64; n++) {
      const row = [1]; const prev = T[n - 1];
      for (let k = 1; k < n; k++) row.push(prev[k - 1] + prev[k]);
      row.push(1); T[n] = row;
    }
    return (n, k) => (k < 0 || k > n ? 0 : T[n][k]);
  })();
  // ⚠ 必须与生成器 mcnemar_exact() **逐字同语义**（含 n==0 返回 1.0）
  const bxMcnemar = (b, c) => {
    const n = b + c;
    if (n === 0) return 1.0;
    let tail = 0;
    for (let i = 0; i <= Math.min(b, c); i++) tail += bxCmb(n, i);
    return Math.min(1.0, 2.0 * tail / Math.pow(2, n));
  };
  const bxCC = SD.closed_counts;

  rec('B0 前置：层唯一 / 非零强度唯一 / 恰好 ±v 两臂 / 题数一致（取不到就不判）',
      bxLayers.length === 1 && bxSt !== null && bxLabels.length === SD.n_problems
      && bxLayers[0] === SD.layer && bxSt === SD.strength,
      `层=${JSON.stringify(bxLayers)} 强度=${JSON.stringify(bxStrs)} 题数=${bxLabels.length}`
      + ` | 产物 layer=${SD.layer} strength=${SD.strength} n=${SD.n_problems}`);

  rec('B1 零臂 / 两臂各自闭合 / 两个口径的配对交集，四格划分：全部与 cot_texts 现算吻合',
      bxCC.zero_shared === bxZc.length
      && bxCC.down_arm_own === bxOwn('confidence_down')
      && bxCC.up_arm_own === bxOwn('confidence_up')
      && bxCC.down_minus_v === bxComp('confidence_down')
      && bxCC.up_plus_v === bxComp('confidence_up')
      && bxCC.zero_closed_down_blew === bxZc.filter(l => !bxC(l, 'confidence_down', bxSt)).length
      && bxCC.down_closed_zero_blew
        === bxLabels.filter(l => bxC(l, 'confidence_down', bxSt) && !bxC(l, 'confidence_up', 0)).length
      && SD.blew_up.table_on_shared_zero_control.n_zero_closed === bxZc.length
      && SD.blew_up.table_on_shared_zero_control.both_closed === bxBoth.length
      && SD.blew_up.table_on_shared_zero_control.up_only_blew_up === bxUpOnly.length
      && SD.blew_up.table_on_shared_zero_control.down_only_blew_up === bxDownOnly.length
      && SD.blew_up.table_on_shared_zero_control.both_blew_up === bxNeither.length,
      `零臂=${bxZc.length} | −v 自己=${bxOwn('confidence_down')} 交集=${bxComp('confidence_down')}`
      + ` | +v 自己=${bxOwn('confidence_up')} 交集=${bxComp('confidence_up')}`
      + ` | 四格 ${bxBoth.length}/${bxUpOnly.length}/${bxDownOnly.length}/${bxNeither.length}`
      + ` (合计 ${bxBoth.length + bxUpOnly.length + bxDownOnly.length + bxNeither.length} 应=${bxZc.length})`
      + ` | 产物 零臂=${bxCC.zero_shared} −v=${bxCC.down_minus_v} +v=${bxCC.up_plus_v}`
      + ` −v自己=${bxCC.down_arm_own} +v自己=${bxCC.up_arm_own}`);

  rec('B2 四格必须是零臂闭合题的**划分**，且两个破坏数 = discordant + 两臂都没跑完',
      bxBoth.length + bxUpOnly.length + bxDownOnly.length + bxNeither.length === bxZc.length
      && SD.blew_up.n_up_vs_shared_control === bxUpOnly.length + bxNeither.length
      && SD.blew_up.n_down_vs_shared_control === bxDownOnly.length + bxNeither.length,
      `四格合计 ${bxBoth.length + bxUpOnly.length + bxDownOnly.length + bxNeither.length} / 零臂 ${bxZc.length}`
      + ` | +v 破坏 ${SD.blew_up.n_up_vs_shared_control}（应 ${bxUpOnly.length + bxNeither.length}）`
      + ` | −v 破坏 ${SD.blew_up.n_down_vs_shared_control}（应 ${bxDownOnly.length + bxNeither.length}）`);

  rec('B3 McNemar 精确 p 必须由四格表现算，不得是印出来的数',
      axNear(SD.blew_up.mcnemar_exact_p, bxMcnemar(bxUpOnly.length, bxDownOnly.length), 12)
      && SD.blew_up.mcnemar_exact_p < 1e-3,
      `产物 p=${SD.blew_up.mcnemar_exact_p} | 现算 mcnemar(up_only=${bxUpOnly.length},`
      + ` down_only=${bxDownOnly.length}) = ${bxMcnemar(bxUpOnly.length, bxDownOnly.length)}`);

  rec('B4 步数比中位数 / 更长的题数 / 符号检验 p 与现算吻合（步数不是 reason_len_ratio）',
      axNear(SD.length.ratio_median_down, bxMedian(bxRatio('confidence_down')), 9)
      && axNear(SD.length.ratio_median_up, bxMedian(bxRatio('confidence_up')), 9)
      && (() => {
          const rd = bxRatio('confidence_down'), ru = bxRatio('confidence_up');
          const gt = rd.filter((v, i) => ru[i] > v).length;
          return SD.length.n_up_ratio_gt_down === gt
            && axNear(SD.length.sign_test_p, bxMcnemar(gt, bxLabels.length - gt), 12);
        })(),
      `中位数 现算 −v=${bxMedian(bxRatio('confidence_down')).toFixed(6)}`
      + ` +v=${bxMedian(bxRatio('confidence_up')).toFixed(6)}`
      + ` | 产物 −v=${SD.length.ratio_median_down} +v=${SD.length.ratio_median_up}`
      + ` | 更长题数 产物=${SD.length.n_up_ratio_gt_down} p=${SD.length.sign_test_p}`);

  rec('B5 撞 token 上限的题数与 KL 均值与现算吻合（CAP 来自产物 token_cap）',
      SD.blew_up.zero_arm_at_cap
        === bxLabels.filter(l => bxN(l, 'confidence_down', 0) >= SD.token_cap).length
      && SD.per_direction.up.arms_at_token_cap
        === bxLabels.filter(l => bxN(l, 'confidence_up', bxSt) >= SD.token_cap).length
      && SD.per_direction.down.arms_at_token_cap
        === bxLabels.filter(l => bxN(l, 'confidence_down', bxSt) >= SD.token_cap).length
      && axNear(SD.kl_contrast.mean_logit_kl_up,
                bxLabels.reduce((a, l) => a + bxBy[l]['confidence_up|' + bxSt].mean_logit_kl, 0) / bxLabels.length, 9)
      && axNear(SD.kl_contrast.mean_logit_kl_down,
                bxLabels.reduce((a, l) => a + bxBy[l]['confidence_down|' + bxSt].mean_logit_kl, 0) / bxLabels.length, 9)
      // 「幅度大的方向」必须真的是大的那个，且 opposite 必须在语义上成立
      && SD.kl_contrast.larger_kl_direction
        === (SD.kl_contrast.mean_logit_kl_down > SD.kl_contrast.mean_logit_kl_up
             ? 'confidence_down' : 'confidence_up')
      && SD.kl_contrast.opposite === true,
      `撞上限 零臂=${SD.blew_up.zero_arm_at_cap} +v=${SD.per_direction.up.arms_at_token_cap}`
      + ` −v=${SD.per_direction.down.arms_at_token_cap} | KL 产物 up=${SD.kl_contrast.mean_logit_kl_up}`
      + ` down=${SD.kl_contrast.mean_logit_kl_down}`);

  // ---- B6：本笔的核心。down_arm_own 与 down_minus_v **不等**，页面必须
  //   把两个口径都印出来，并说清那 1 题的去向；否则「−v 配对 20 < 零臂 21」
  //   会被读成「−v 跑飞了一题」，与整块结论相反。
  const BX = state.dir || {};
  const bxCal = BX.items['paired-caliber'] || '';
  rec('B6 两个闭合口径在页面上必须分开印，并说清差的那 1 题是对称的（核心判据）',
      !!BX.text
      && bxCal.length > 0
      // 三格必须是「自己跑完」口径
      && Number(BX.downOwn) === bxCC.down_arm_own && Number(BX.upOwn) === bxCC.up_arm_own
      && /−v 臂自己跑完/.test(BX.text) && /\+v 臂自己跑完/.test(BX.text)
      // 另一口径那行必须印出两个交集数，并给出对称差
      && bxCal.includes(`${bxCC.down_minus_v}/${SD.n_problems}`)
      && bxCal.includes(`${bxCC.up_plus_v}/${SD.n_problems}`)
      // ⚠ 下面三条**不许**写成 `bxCal.includes(String(1))`：
      //   对称差那个数恰好是 1，而「1」在这段文字里出现过好几次
      //   （20/23、5/23 里没有，但「1 题」有三处）⇒ 改对了仍会绿。
      //   换成带词锚点的正则，把数与它所在的句子绑在一起。
      && new RegExp('少 ' + bxCC.zero_closed_down_blew + ' 题').test(bxCal)
      && new RegExp(bxCC.zero_closed_down_blew + ' 题零臂跑完而 .v 没跑完').test(bxCal)
      && new RegExp('另有 ' + bxCC.down_closed_zero_blew + ' 题反过来').test(bxCal)
      && /对称/.test(bxCal) && /不构成/.test(bxCal)
      // 前置：只有当两个口径真的不等时，这条才要求「分开印」
      && (bxCC.down_arm_own === bxCC.down_minus_v || /另一口径/.test(bxCal)),
      `页面三格 downOwn=${BX.downOwn} upOwn=${BX.upOwn} | 另一口径行：${bxCal.slice(0, 190)}`);

  // ---- B7：跨产物一致性（arm / power / steer_directions 三方）
  rec('B7 层与强度在三份产物间三方一致（判据独立从 cot_texts 现算）',
      bxLayers.length === 1 && bxSt !== null
      && SD.layer === bxLayers[0] && ARM.layer === bxLayers[0] && PW.strength === bxSt
      && SD.strength === bxSt && ARM.strength === bxSt
      && SD.n_problems === ARM.n_pairs,
      `层 产物 steer=${SD.layer}/arm=${ARM.layer} 现算=${JSON.stringify(bxLayers)}`
      + ` | 强度 steer=${SD.strength}/arm=${ARM.strength}/power=${PW.strength} 现算=${bxSt}`
      + ` | 题数 steer=${SD.n_problems} arm=${ARM.n_pairs}`);

  // ---- B8：产物那两段散文**未渲染** —— 与 A7 同一件事，必须自报层级
  const bxVFrag = '同一条轴，符号一换，行为完全不同';
  const bxNFrag = '不能说「+v 更差」是普遍规律';
  rec('B8 产物 verdict / not_claimed 确实未渲染到页面（本组大半在产物层，必须说清）',
      !(state.text || '').includes(bxVFrag) && !(state.text || '').includes(bxNFrag),
      `页面含 verdict 独有片段「${bxVFrag}」=${(state.text || '').includes(bxVFrag)}；`
      + `含 not_claimed 独有片段「${bxNFrag}」=${(state.text || '').includes(bxNFrag)}`);

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

  // ⚠ 第十七笔改写：原来这条叫「三个闭合率（零臂 / −v / +v）并排印出」，
  //   并用 `21/23`、`20/23`、`5/23` 三个数判。而 20/23 那个数是
  //   **与零臂配对后的交集**，不是 −v 臂自己的闭合数 ⇒
  //   判据**自己**把两个口径当成一个口径在要求，名字也在替它背书。
  //   现在三格取「各臂自己跑完」，交集那对数由 B6 在另一行里要求。
  rec('J2 三格必须是「各臂自己跑完」（不是配对交集），且 +v 那格不许淡化',
      D.text
      && D.text.includes(`${SD.closed_counts.zero_shared}/${SD.n_problems}`)
      && D.text.includes(`${SD.closed_counts.down_arm_own}/${SD.n_problems}`)
      && D.text.includes(`${SD.closed_counts.up_arm_own}/${SD.n_problems}`)
      && /大面积跑飞/.test(D.text)
      && SD.closed_counts.up_arm_own < SD.closed_counts.zero_shared / 2,
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
  const L6A = byId('l6-no-random-arm').audit;
  // ⚠ 原来这一条是 `ML6.includes('6') && ML6.includes(String(supported))`。
  //   那是个**子串谓词，作用域大于被核量** —— 同一句里有两个诱饵数字：
  //     「声明 **L6**」      ← declared，喂 includes('6')
  //     「升到 **L5** 只需」  ← cheapest_next_step.to_level，喂 includes('5')
  //   实测（对真实渲染文本跑这个谓词）：
  //     supported=5 ⇒ 谓词绿，页面却印 L4   ← 假绿
  //     supported=6 ⇒ 谓词绿，页面却印 L4   ← 假绿
  //   supported=1 / 8 才正确判红（句中根本没有那两个数）。
  // ⇒ 而组件**早就发了** data-ca-l6-declared / data-ca-l6-supported，
  //   与 l0 / l2 / self 三行同款，却只有 l6 这一行退回子串匹配。
  //   修法：读那两个属性，并把文本断言**锚定到句子结构**而不是裸 includes。
  rec('M2 「声明 L6 ⇒ 实测降到 L4」必须印出，并点名缺的是随机臂',
      L6A.declared_level === 6
      && L6A.max_level_supported < 6
      // ① 属性侧：逐值等于产物（l0/l2/self 已经是这个口径）
      && Number(C3.l6declared) === L6A.declared_level
      && Number(C3.l6supported) === L6A.max_level_supported
      // ② 文本侧：**锚定结构**「声明 L6 ⇒ L4」，裸 includes 已被上面证明会被喂饱
      && new RegExp(`声明\\s*L${L6A.declared_level}\\s*⇒\\s*L${L6A.max_level_supported}(?![0-9])`)
             .test(ML6)
      && /随机方向臂/.test(ML6)
      && /排除不了/.test(ML6)
      && !!L6A.cheapest_next_step,
      ML6 ? `属性 l6declared=${C3.l6declared} l6supported=${C3.l6supported}`
             + `（产物 ${L6A.declared_level}/${L6A.max_level_supported}）; `
             + ML6.slice(0, 190)
           : '缺 [data-ca-item="l6"]');

  const MSL = C3.items.self || '';
  rec('M3 本项目自己的那句话必须被这把尺子量过，并印出实测级别',
      MSL.includes(String(byId('project-confidence-claim').audit.declared_level))
      && MSL.includes(String(byId('project-confidence-claim').audit.max_level_supported))
      && /只到/.test(MSL)
      && /随机臂/.test(MSL)
      // 诚实性：尺子对自己的判定必须是**降级**，不能给高分
      && byId('project-confidence-claim').audit.overreach_vs_declared === true,
      MSL ? MSL.slice(0, 220) : '缺 [data-ca-item="self"]');

  /* ---------------------------------------------------------------- */
  // ⚠⚠ 第二十八笔：M3 原来只查**级别**，不查**引文本身** ——
  //   而页面那一格是把产物的 quote **转述**过的，且转述时把两个口径并成了一个：
  //     产物原文：「…（闭合率 5/23 vs **共享对照 21/23**），而 −v 几乎不变（20/23）…」
  //     页面转述：「（±v 闭合率 5/23 vs **20/23**，破坏模式是逐字重复退化）」
  //   ⇒ 页面那句与它**所引用的原文**自相矛盾：20 是 −v 臂自己的数，
  //     不是那个对照臂的数（21 才是）。而 M3 全程绿。
  //   所以「引文必须逐字等于产物」这条要单独成立，不能指望级别那条顺带核到。
  const selfQuote = byId('project-confidence-claim').quote;
  rec('M3b 「本项目自己那句话」必须**逐字**等于产物 quote（不许转述后并口径）',
      !!selfQuote
      && MSL.includes(selfQuote)
      // 反向断言：那个被并过的形式不许回来。
      // ⚠ 锚点要够紧 —— 段里另有 5/23 与 20/23 两个数（它们各自都对），
      //   只查 includes('5/23') 会被别处的 5/23 喂饱（第九笔同款）。
      && !/5\/23\s*vs\s*20\/23/.test(MSL)
      && !/±v\s*闭合率/.test(MSL),
      `产物 quote=${selfQuote.slice(0, 90)}  页面逐字含它=${MSL.includes(selfQuote)}  `
      + `含被并过的 "5/23 vs 20/23"=${/5\/23\s*vs\s*20\/23/.test(MSL)}`);

  /* ---------------------------------------------------------------- */
  // 第二十八笔·缺陷 A：那段话原来印「argmax reproduces the recorded token on
  // **99.5%** of sampled steps, max logit error 0.125」——
  // 99.5% 既不是产物值（anchor.all_steps.rate = 0.9974），
  // 口径也错（不是抽样，是全部 1536 步）。
  // 而 vector_roles.json 的 unmeasured.lm_head_anchor.pre_existing_measurement
  // **已经把正确的那整句写好了**（两个口径分开、末尾自带「引用而非复现」）。
  // ⇒ 判据核「页面逐字渲染了那句话」，并反向断言 99.5% 不许回来。
  const anchorNote = VR.unmeasured?.lm_head_anchor?.pre_existing_measurement || '';
  const omittedTxt = state.omitted || '';
  rec('K6 lm_head 那段必须逐字渲染产物的 pre_existing_measurement（99.5% 不许回来）',
      !!anchorNote
      && omittedTxt.includes(anchorNote)
      && !/99\.5\s*%/.test(omittedTxt)
      && !/sampled steps/.test(omittedTxt)
      // 产物那句里自带的两个口径必须都在（这是它比手抄强的地方）
      && /1532\/1536\s*=\s*0\.9974/.test(anchorNote)
      && /1420\/1420\s*=\s*1\.0/.test(anchorNote),
      `产物 pre_existing_measurement 长度=${anchorNote.length}  `
      + `页面逐字含它=${omittedTxt.includes(anchorNote)}  `
      + `页面仍含 99.5%=${/99\.5\s*%/.test(omittedTxt)}  `
      + `页面仍含 "sampled steps"=${/sampled steps/.test(omittedTxt)}`);

  // 「One direction rests on 3 trajectories out of 48」原来两个数都手抄。
  // 源在 necessity.in_sample_circular（第一个层）里 **分子最小**的方向。
  // 判据自己现算那个最小值，不接受页面报一个别的数。
  const circByDir = Object.values(VR.necessity?.in_sample_circular ?? {})[0] ?? {};
  const vThin = Object.entries(circByDir)
    .map(([d, r]) => ({ d, n: r.n_traj_within_which_rho_is_defined, pool: r.n_traj_pooled }))
    .filter((x) => x.n != null && x.pool != null)
    .sort((a, b) => a.n - b.n)[0] || null;
  // ⚠⚠ 第二十八笔：这条判据**第一版是假红，而假红的是判据**。
  //   我第一版除了正向断言，还加了反向断言 `!/3 trajectories out of 48/`，
  //   想把「手写的那句」挡在外面 —— 可现算出来的值**恰好就是 3/48**，
  //   于是页面逐字渲染出同一串字，反向断言恒红。
  //   ⇒ 同一个字符串既可能是手抄、也可能是现算，**在输出层无法区分**
  //     （与第二十六笔 F5b 同一个道理的反面：那里是输出不变而输入变了，
  //      这里是输出与手抄完全一致 —— 两种情况下「看输出」都判不出来）。
  //   ⇒ 正向断言保留（页面印的 == 产物现算的），反向断言**删掉**，
  //     改在**源码层**防回流 —— 与 L13/L14（读 .tsx 剥注释）同一处置。
  rec('K7 「最薄的那个方向」的分子/分母必须由 necessity.in_sample_circular 现算',
      !!vThin
      && omittedTxt.includes(vThin.d)
      && omittedTxt.includes(` ${vThin.n} trajectories out of ${vThin.pool} `),
      `产物现算最薄 = ${vThin ? `${vThin.d} ${vThin.n}/${vThin.pool}` : '（无）'}  `
      + `页面含该方向名=${vThin ? omittedTxt.includes(vThin.d) : '—'}  `
      + `页面含 "${vThin?.n} trajectories out of ${vThin?.pool}"=`
      + `${vThin ? omittedTxt.includes(` ${vThin.n} trajectories out of ${vThin.pool} `) : '—'}`
      + `　⚠ 本条**没有**「3 trajectories out of 48 不许出现」那条反向断言：`
      + `现算值恰好就是 3/48，两种写法输出逐字相同 ⇒ 只能去源码层判`);

  rec('K7b 源级：那句不许退回手写（3 / 48 都必须从产物取）',
      (() => {
        const raw = readFileSync('/Users/zhourui/code/steer3d/frontend/components/'
                                 + 'InterventionOutcomePanel.tsx', 'utf8');
        // 与 L13 同一把刀：先剥块注释再剥行注释，否则扫到的是我自己写的解释。
        const code = raw.replace(/\/\*[\s\S]*?\*\//g, '')
                         .split('\n').map(l => l.replace(/\/\/.*$/, '')).join('\n');
        // 修复后的写法必须在场，否则一次改名就让本条空转（第十四笔的教训）。
        const hasDerivation =
          /n_traj_within_which_rho_is_defined/.test(code)
          && /n_traj_pooled/.test(code);
        // 手写形态：把 3 与 48 直接写进 JSX 文案
        const hasLiteral = /3\s+trajectories out of\s+48/.test(code)
                        || /rests on\s*\{?3\}?\s*trajectories/.test(code);
        return hasDerivation && !hasLiteral;
      })(),
      '源码里必须出现 n_traj_within_which_rho_is_defined 与 n_traj_pooled 的取数，'
      + '且不许出现「3 trajectories out of 48」这种写死形态');


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

  // ==================== N 组：把尺子指向真实论文 ====================
  // 这一组最容易出的错不是数字错，而是**语气错** ——
  // 把「摘要里没写」印成「论文没做」。
  const L = state.lit || {};
  const LH = LIT.headline;

  rec('N0 文献审计块存在，且 5 个计数与产物逐值相同（可见文案 + 属性两处）',
      !L.missing
      && Number(L.n) === LIT.source.n_papers
      && Number(L.claim) === LH.n_with_verbatim_claim
      && Number(L.ctrl) === LH.n_naming_any_control_in_abstract
      && Number(L.sameNorm) === LH.n_with_same_norm_random_control_known
      && Number(L.sameNormUnknown) === LH.same_norm_unknown
      && Number(L.renderedFields) === LIT.rendered_fields.length
      && LIT.source.only_abstracts === true
      // 内部一致性：known + unknown 必须等于总数
      && LH.n_with_same_norm_random_control_known + LH.same_norm_unknown
           === LIT.source.n_papers,
      L.missing ? '缺 [data-lit-audit]'
        : `n=${L.n} claim=${L.claim} ctrl=${L.ctrl} `
          + `sameNorm=${L.sameNorm} unknown=${L.sameNormUnknown} `
          + `rendered=${L.renderedFields} | 产物 n=${LIT.source.n_papers} `
          + `claim=${LH.n_with_verbatim_claim} ctrl=${LH.n_naming_any_control_in_abstract} `
          + `sameNorm=${LH.n_with_same_norm_random_control_known} `
          + `unknown=${LH.same_norm_unknown} `
          + `rendered=${LIT.rendered_fields.length}`);

  // ⚠ 全组最要紧的一条：0 篇可判**不等于** 0 篇没做。
  const NL = L.items.headline || '';
  rec('N1 「0 篇可判」必须紧跟「未知不是没有」，不许印成「论文都没做」',
      !!NL
      && NL.includes(String(LH.n_papers))
      && NL.includes(String(LH.n_naming_any_control_in_abstract))
      && NL.includes(String(LH.n_with_same_norm_random_control_known))
      && /未知.*不是.*没有|不是没有/.test(NL)
      // 反向断言：产物里 0 是「可判数」，不是「做过数」
      && LH.n_with_same_norm_random_control_known === 0
      && LH.same_norm_unknown > 0
      && !/没有一篇|全部没有|都没做/.test(NL),
      NL ? NL.slice(0, 230) : '缺 [data-lit-item="headline"]');

  const NA = L.items.notaccuse || '';
  rec('N2 必须明写「这不是指控」，并说清 unknown 是「摘要里没写」',
      !!NA
      && /这不是指控/.test(NA)
      && /摘要里没写/.test(NA)
      && /方法章节/.test(NA)
      && NA.includes(LIT.headline.what_this_is_not.slice(0, 10)),
      NA ? NA.slice(0, 230) : '缺 [data-lit-item="notaccuse"]');

  // 硬规矩必须印出来：不许替论文填摘要里没有的东西
  const NR = L.rule || '';
  rec('N3 硬规矩必须印出：摘要里没有的不许替论文填，并给出来源与查询式',
      !!NR
      && /摘要里没有的东西，不许替论文填/.test(NR)
      && NR.includes(LIT.source.api)
      && NR.includes(LIT.source.query)
      && /只入库摘要/.test(NR),
      NR ? NR.slice(0, 230) : '缺 [data-lit-rule]');

  // 逐字引述必须真的是摘要的子串 —— 判据自己在产物上复核一遍
  const LQ = LIT.rows.filter(x => x.claim_verbatim);
  const NVD = L.detail || '';
  const norm = t => (t || '').replace(/\\s+/g, ' ').trim();
  const byPaper = {};
  LIT.rows.forEach(x => { byPaper[x.arxiv_id] = x; });
  // ⚠ N4 的第一版只核了三件**与页面无关**的事：
  //   「产物里引述是摘要子串」「DOM 行数 = 产物条数」「每个 id 出现在展开区」。
  //   三件全都不看**页面上真正渲染出来的那句话** ——
  //   于是 N4 变异把引述整句改写成「本文证明该方向确实编码了目标概念」，
  //   N4 依然 53/53 全绿。
  //   这就是「只查属性」那条老毛病的又一例：查了一堆**元数据**，
  //   唯独没查**读者看到的那句话**。
  const mismatched = L.rows.filter(r => {
    const a = byPaper[r.id];
    return !a || !a.claim_verbatim || !r.text.includes(norm(a.claim_verbatim));
  });
  rec('N4 逐字引述必须真的是对应摘要的子串，**且页面上渲染的就是那句话**'
      + '（判据自己复核产物，不信脚本自证）',
      LQ.length > 0
      && LQ.every(x => x.abstract.indexOf(x.claim_verbatim) >= 0)
      && L.rows.length === LQ.length
      && L.rows.every(r => NVD.includes(r.id))
      // 反向断言：不能有引述等于整段摘要
      && LQ.every(x => x.claim_verbatim.length <= 0.6 * x.abstract.length)
      && NVD.includes(String(LQ.length))
      // ★ 缺的就是这一条：渲染文本必须**包含**产物里那句逐字引述
      && mismatched.length === 0,
      `产物内 ${LQ.length} 条引述全部是摘要子串；页面列出 ${L.rows.length} 条；`
      + `渲染与产物不一致 ${mismatched.length} 条`
      + (mismatched.length
         ? ` —— 例如 ${mismatched[0].id} 渲染成「${mismatched[0].text.slice(0, 60)}」`
         : ` | notaccuse: ${NA.slice(0, 30)}`));

  /* ============ E 组：vector_roles.necessity 的三段散文（第二十笔） ============ */
  // ⚠ 先说层级，而且这一组**整组都在产物层**。
  //   这三段散文在页面上是**故意不渲染**的：
  //   InterventionOutcomePanel.tsx:40-47 把它写成面板的第四条 refusal
  //   —— in_sample_circular 按构造就是循环论证，passes_gate=true 是恒等式
  //   不是发现 —— 于是面板不渲染 necessity 的任何东西，并说明原因。
  //   ⇒ 这里**不可能**有渲染层判据。第十六笔的教训：判错的层，
  //     判据再多也够不着。A7/B8 那种反向断言只能证明「没渲染」，
  //     证不了「印出来的数对不对」。
  //   所以 E 组全部核**产物层**，每条判据名里都自报层级。
  //
  // E 组能证明什么、不能证明什么（别把这两句读反）：
  //   能 —— 这份 JSON 里那 13 个数，每一个都能从**同一份 JSON 的别的字段**
  //         现算回来，且口径（哪一层、哪个可观测量）被钉死到唯一一格；
  //         生成器源码里不再有手抄副本。
  //   不能 —— 读者在页面上看不到它们。面板拒绝渲染。所以
  //         「读者看到的数是对的」在这一块是**不适用**，不是「已核」。
  const E = VR.necessity;
  const VDen = VR.denominators, VSc = VR.observable_audit.self_check;
  const VWS = E.which_statistic_and_why, VRC = E.random_control_is_the_real_null;
  const VLC = E.label_confounds;
  const VInj = 'L' + VR.layers.journal_injection;
  const VNat = 'L' + VR.layers.native_extraction;
  const Vrtl = VR.necessity.random_direction_control;
  const vcell = (layer, obs) => Object.entries(Vrtl[layer])
    .filter(([, v]) => v.observable === obs);
  // 唯一一格 —— 散话说的是「self_check 上它们…」，若自_check 由两个方向
  // 携带，这句话就没有确定的所指，必须拒绝而不是挑一格。
  const eSelfCells = vcell(VInj, 'self_check');
  const eEntCells = vcell(VInj, 'entropy');
  const eF2 = x => x.toFixed(2), eF3 = x => x.toFixed(3), eF4 = x => x.toFixed(4);
  // 生成器那句链是「先印基率，再由**印出来的那个基率**推出压缩因子，
  // 再由压缩因子推出所需效应量」——这样纸上可手算复核。所以这里
  // 必须复刻同一条链：先 round 到 4 位再用，而不是用真值。
  // （真值 0.005654 给出 0.0750 → d=1.99；0.0057 给出 0.0753 → d=1.98。
  //   差在末位，句子也会因此不是同一句。）
  const eP4 = Math.round(VSc.frac_steps_positive * 1e4) / 1e4;
  const eComp = Math.sqrt(eP4 * (1 - eP4));
  const eN3 = VDen.n_trajectories - 3;
  const eFloor = 1 / Math.sqrt(eN3);
  const eD = eFloor / eComp;
  const eNpos = Math.round(VSc.frac_steps_positive * VSc.n_steps);
  const eNrand = [...new Set(Object.values(Vrtl).flatMap(
    L => Object.values(L).map(c => c.n_random_directions)))];
  // 带词锚点的正则 —— 第十八笔的教训：光 `includes('0.21')` 会在同段落里
  // 另一个 0.21 出现时假绿。锚点取紧邻的数字。
  const eHas = (s, re) => re.test(s);

  // ⚠ 判据自己连着踩了三次的坑，留在这里免得下一个人重写一遍：
  //   ① IOP.tsx 那句是 `deliberately does not\n * render` —— 中间有换行，
  //      按整串 `includes('deliberately does not render')` 永远判红。
  //   ② 归一化**不能**借用本文件里已有的 `norm`：它的正则是 `/\\s+/g`，
  //      在 JS 正则字面量里 `\\` 是一个**字面反斜杠**，所以它匹配的是
  //      「反斜杠后跟若干 s」，不是空白折叠。我第一版直接拿它用，
  //      归一化没生效，E0 判红。
  //   ③ 光折叠空白还是不够：JSDoc 每行前缀是 ` * `，折行处折叠出来是
  //      `not * render`，星号夹在中间 —— 我第二版「删掉全部空白」也照样
  //      判红，因为删空白得到的是 `not*render`。要判「源里有这句话」，
  //      得**先剥行首注释符再压空白**（先 `/^\s*\*+/gm` 再 `/\s+/g`）。
  //      顺序反过来不行：压完空白就再也认不出哪些 `*` 是行首的了。
  //   ④ 这条的诊断行第一版硬写了 `在场=${true}` —— 一个自己会显得成立的
  //      假值。判据的诊断行比判据本身更容易骗人：它每轮都印，且没人复核。
  //      改掉之后它如实报 false，才把上面三次判红引到了真因上。
  const eIop = readFileSync('/Users/zhourui/code/steer3d/frontend/components/'
    + 'InterventionOutcomePanel.tsx', 'utf8')
    .replace(/^\s*\*+/gm, '').replace(/\s+/g, '');
  const eRefusal = eIop.includes('deliberatelydoesnotrenderanyofit');
  rec('E0 这三段散文在源里被声明为「故意不渲染」，E 组整组只核产物层（自报层级）',
      eRefusal && eSelfCells.length === 1 && eEntCells.length >= 1,
      `IOP.tsx 第四条 refusal 在场=${eRefusal}（剥行首注释符+压空白后匹配）；`
      + `journal 层 self_check 格数=${eSelfCells.length}（须恰好 1，散话说的是「它们」）；`
      + `entropy 格数=${eEntCells.length}（散文只说「entropy」，多格必须同值，见 E3）`);

  rec('E1 [产物层] 基率/压缩因子/1/sqrt(n-3)/所需效应量 四者可现算复现，且是同一条链',
      eHas(VWS, new RegExp('基率 ' + eF4(eP4) + '、压缩因子 ' + eF3(eComp)))
      && eHas(VWS, new RegExp('1/sqrt\\(' + eN3 + '\\)=' + eF3(eFloor)
                              + ' 实际要求 d=' + eF2(eD)))
      && Math.abs(eFloor - VDen.null_floor_by_traj) < 1e-12
      && Math.abs(eD - VDen.null_floor_by_traj / eComp) < 1e-12,
      `p→${eF4(eP4)} 压缩因子→${eF3(eComp)} n-3→${eN3} 地板→${eF3(eFloor)} `
      + `所需 d→${eF2(eD)}；产物 null_floor_by_traj=${eF3(VDen.null_floor_by_traj)}`);

  rec('E2 [产物层] 门槛那句里的随机方向数 = 每一格 n_random_directions（且全等）',
      eNrand.length === 1
      && eHas(VWS, new RegExp('max\\(' + eNrand[0] + ' 个随机方向里的最大值'))
      && eHas(VRC, new RegExp('全部 ' + eNrand[0] + ' 个随机方向')),
      `全稿 n_random_directions 取值集合=${JSON.stringify(eNrand)}`
      + `（必须唯一，否则散文里那个 N 没有所指）`);

  // E3/E4 是**口径钉**：数字不仅要对，而且必须是**注入层**那一格。
  // 散文里「L20 的 entropy」「self_check 上」不带可核的口径标记；
  // 一旦将来重跑换层，这两句话会安静地开始描述另一格。
  const eEntMax = Math.max(...eEntCells.map(([, v]) => v.random_max));
  const eNatEntMax = Math.max(...vcell(VNat, 'entropy').map(([, v]) => v.random_max));
  rec('E3 [产物层] entropy 那句的层号=注入层，且随机方向最大值=该层 entropy 格的现算值',
      VWS.includes('在 ' + VInj + ' 的 entropy 上')
      && VWS.includes('随机方向最大能到 ' + eF4(eEntMax))
      && eNatEntMax !== undefined && eF4(eEntMax) !== eF4(eNatEntMax),
      `散文层号=${VInj}（注入层=${VInj}, 抽取层=${VNat}）；`
      + `注入层 entropy random_max=${eF4(eEntMax)}，抽取层=${eF4(eNatEntMax)}`
      + `（两格必须不同，否则这条判据钉不住口径）`);

  // ⚠ E4 第一版要求 min 与 max **都**能钉住层，判红了。查下去是判据错：
  //   抽取层 0.2080、注入层 0.2088，两位小数下**都是 0.21** ——
  //   散文的「从 0.21 散到」这一端根本不携带层信息，能钉住的只有上端。
  //   ⇒ 口径钉只挂 max；min 的巧合在诊断行里明写，不当成钉子。
  const eSc = eSelfCells[0][1];
  const eNatSc = vcell(VNat, 'self_check')[0][1];
  const eMinPins = eF2(eSc.random_min) !== eF2(eNatSc.random_min);
  rec('E4 [产物层] self_check 散布区间=注入层该格 min/max；上端能钉住层，下端不能',
      VRC.includes('在 ' + VInj + ' 上同样偏小')
      && eHas(VRC, new RegExp('auc_within 从 ' + eF2(eSc.random_min) + ' 散到 '
                             + eF2(eSc.random_max)))
      && eNatSc !== undefined
      && eF2(eSc.random_max) !== eF2(eNatSc.random_max),
      `注入层 ${eF2(eSc.random_min)}–${eF2(eSc.random_max)}，`
      + `抽取层 ${eF2(eNatSc.random_min)}–${eF2(eNatSc.random_max)}；`
      + `上端能钉层=${eF2(eSc.random_max) !== eF2(eNatSc.random_max)}，`
      + `下端能钉层=${eMinPins}`
      + (eMinPins ? '' : '（两位小数下相同，散文那一端不携带层信息 —— 照实说）'));

  rec('E5 [产物层] 正例步数 = frac_steps_positive × n_steps 的现算值',
      eHas(VRC, new RegExp('——' + eNpos + ' 个正例每一个都是孤立的单步')),
      `frac ${VSc.frac_steps_positive} × n_steps ${VSc.n_steps} → ${eNpos}`);

  // E6 是这一笔最要紧的一条：「只分布在 27 条轨迹里」这句话，
  // 改之前**全仓没有任何字段是它的来源** —— 27 既不是 n_traj（48）
  // 也不是 n_traj−n_traj_constant_inside（那个恰好也等于 27，
  // 但只有「没有一条轨迹全程为正」时才相等）。它是新加的
  // n_traj_with_any_positive。
  rec('E6 [产物层] 「分布在 N 条轨迹里」= n_traj_with_any_positive，且严格小于总轨迹数',
      VSc.n_traj_with_any_positive !== undefined
      && VSc.n_traj_with_any_positive < VDen.n_trajectories
      && eHas(VRC, new RegExp('只分布在 ' + VSc.n_traj_with_any_positive + ' 条轨迹里')),
      `n_traj_with_any_positive=${VSc.n_traj_with_any_positive} < `
      + `n_trajectories=${VDen.n_trajectories}；`
      + `（巧合提醒：n_traj−n_traj_constant_inside=`
      + `${VDen.n_trajectories - VSc.n_traj_constant_inside}，本数据上与它相等，`
      + `但只有不存在「全程为正」的轨迹时才相等，判据不依赖这个等式）`);

  rec('E7 [产物层] mean+3sd 的不可达阈值 = 该格现算值，且 reachable 标记为假',
      VRC.includes('会算出 ' + eF3(eSc.empirical_floor_mean_plus_3sd))
      && eSc.mean_plus_3sd_reachable === false
      && eSc.empirical_floor_mean_plus_3sd > 1,
      `mean+3sd=${eF3(eSc.empirical_floor_mean_plus_3sd)}（>1 即任何 AUC 都够不到）；`
      + `产物 reachable=${eSc.mean_plus_3sd_reachable}`);

  rec('E8 [产物层] label_confounds 的轨迹数 = denominators.n_trajectories = in_think 审计的分母',
      eHas(VLC, new RegExp('在这 ' + VDen.n_trajectories + ' 条轨迹上'))
      && VR.observable_audit.in_think.n_traj === VDen.n_trajectories,
      `n_trajectories=${VDen.n_trajectories}，in_think 审计 n_traj=`
      + `${VR.observable_audit.in_think.n_traj}`);

  // E9：源级禁令。散文的源头是**生成脚本**，只改产物会被下次重跑覆盖
  // （老毛病的源头）。所以要卡在生成器那一层：这些数一旦被手抄回去，
  // 判据必须红。表要显式列出来，并同时**正向**要求占位符在源码里，
  // 否则「把三段散文整段删掉」也能让这一条绿（第十八笔：恒假/恒真的合取项）。
  const eSrc = readFileSync('/Users/zhourui/code/steer3d/backend/examples/'
    + 'analyse_vector_roles.py', 'utf8');
  const eBanned = ['基率 0.0057', '压缩因子 0.075', '实际要求 d=1.98',
    'max(16 个随机方向', '随机方向最大能到 0.2548', '从 0.21 散到',
    '散到 0.75', '会算出 1.128', '全部 16 个随机方向',
    '16 个随机方向是这批数据上', '在这 48 条轨迹上'];
  const eHole = eBanned.filter(s => eSrc.includes(s));
  const eWant = ['{sc_p:.4f}', '{sc_compress:.3f}', '{sc_d:.2f}', '{n_rand}',
    "{ent_ctl['random_max']:.4f}", "{sc_ctl['random_min']:.2f}",
    "{sc_ctl['random_max']:.2f}", '{sc_n_pos}', '{sc_n_traj}',
    "{sc_ctl['empirical_floor_mean_plus_3sd']:.3f}", '{n_traj}'];
  const eMiss = eWant.filter(s => !eSrc.includes(s));
  rec('E9 [源级] 生成器源码里没有这 11 个手抄副本，且 11 个插值占位符都在',
      eHole.length === 0 && eMiss.length === 0,
      `手抄副本残留 ${eHole.length} 个${eHole.length ? '：' + eHole.join(' / ') : ''}；`
      + `缺失占位符 ${eMiss.length} 个${eMiss.length ? '：' + eMiss.join(' / ') : ''}`);

  // E10：反向断言 —— 与 A7/B8 同型。这一条只证明「没渲染」，
  // **证不了数对不对**（那是 E1–E8 的活），两件事不许互相顶替。
  const eFrags = ['压缩因子', '个随机方向是这批数据上真正的零假设',
    '孤立的单步', '实际要求 d='];
  const eHit = eFrags.filter(f => (state.text || '').includes(f));
  rec('E10 [渲染层·反向] 这三段散文的独有片段都不在页面上（只证明未渲染，不证明数对）',
      eHit.length === 0,
      `页面命中独有片段 ${eHit.length}/${eFrags.length}：`
      + `${JSON.stringify(eHit)}；面板第四节 refusal 明确不渲染 necessity`);

  /* ============ AP 组：answer_power 的 verdict / not_claimed / what（第二十二笔） ============ */
  // ⚠ 整组在产物层：这三个字段**都没有被渲染** ——
  //   面板读的是 answer_power.json 的**字段**（net_change / n_complete_pairs /
  //   n_other_named_axes …，见 IOP.tsx:583-589），散文那三段字符串
  //   （IOP.tsx / index.html 里 0 次出现 `pw.verdict` / `pw.not_claimed` / `pw.what`）
  //   一个字都没进页面。⇒ I 组（渲染层，11 条）核的是面板上那 11 个数，
  //   **不能**替 AP 组（产物层）作证。
  //
  // ⚠ 这一组的设计要点来自一次**失败的做法**：
  //   我先写了个扫描器，把 verdict/not_claimed 里每个数字拿去和「某个字段的值」
  //   比对，结果 **46/46 全部对上**，看起来一个缺口都没有。
  //   但那个扫描**分不清用的是哪个字段** —— 这一份产物里 `6` 既是
  //   `full_verdicts["right->right"]` 又是 `incomplete_arms_total`，
  //   `2` 既是 `flips_up` 又是 `incomplete_breakdown.one_arm_closed`。
  //   ⇒ **按值匹配会给出虚假的信心。** 下面每一条都必须带词锚点，
  //     钉住「这句里的这个数」对应「**这个**字段」。
  const APw = PW, AJv = APw.verdict || '', AJn = APw.not_claimed || '',
        AJw = APw.what || '';
  const jRe = (s, re) => re.test(s);
  const jMag = APw.changed_but_still_wrong_magnitude || {};
  const jFb = APw.full_verdicts || {}, jInv = APw.net_change_invariance || {};
  // net_change 的**带符号**写法。这一份产物里同一个量曾经印成两种形状：
  //   not_claimed 两处是「净变化 0」、verdict 的行内是「**净变化 +0**」，
  //   what 与 verdict 开头又都是「净变化 0」⇒ 同一个产物、同一个量、三种写法。
  const jNet = (APw.net_change >= 0 ? '+' : '') + APw.net_change;

  rec('AP0 [产物层] 三段散文都存在，且 I 组核的字段齐备（本组自报层级：不渲染）',
      AJv.length > 0 && AJn.length > 0 && AJw.length > 0
      && jFb && jMag && jInv,
      `verdict ${AJv.length} 字 / not_claimed ${AJn.length} 字 / what ${AJw.length} 字；`
      + `I 组核的是字段（n_complete_pairs=${APw.n_complete_pairs} 等），`
      + `AP 组核的是这三段散文本身`);

  rec('AP1 [产物层] verdict ① 的题数与配对数 = n_problems_in_batch / n_complete_pairs',
      jRe(AJv, new RegExp('① ' + APw.n_problems_in_batch + ' 题里 '
                          + APw.n_complete_pairs + ' 题两臂都跑完'))
      && jRe(AJw, new RegExp(APw.n_problems_in_batch + ' 题逐题去向 \\+ '
                            + APw.n_complete_pairs + ' 个完整配对')),
      `① ${APw.n_problems_in_batch} 题里 ${APw.n_complete_pairs} 题；`
      + `what 同源=${APw.n_problems_in_batch}/${APw.n_complete_pairs}`);

  // J2 是这一组最要紧的一条：**「净变化」在行内与在引号里必须是同一个写法**。
  rec('AP2 [产物层] 「净变化」在三段散文里必须是**同一个带符号写法**（本轮的真发现）',
      (AJv.match(new RegExp('净变化 ' + jNet.replace('+', '\\+'), 'g')) || []).length >= 2
      && !/净变化 0(?![.\d])/.test(AJv.replace('净变化 +0', '净变化 #'))
      && (AJn.match(/净变化 \+0/g) || []).length === 2
      && AJw.includes('净变化 ' + jNet),
      `net_change=${APw.net_change} ⇒ 应写作「净变化 ${jNet}」；`
      + `verdict 出现 ${(AJv.match(/净变化 /g) || []).length} 次、`
      + `not_claimed ${(AJn.match(/净变化 /g) || []).length} 次、`
      + `what ${(AJw.match(/净变化 /g) || []).length} 次；`
      + `仍存在不带号的「净变化 0」=${/净变化 0(?![\d.])/.test(AJv + AJn + AJw)}`
      + `（本轮之前 verdict 开头/what 是「净变化 0」而行内是「+0」，同一产物三种写法）`);

  rec('AP3 [产物层] verdict ① 的 verdict 全表 + 基线/注入答对数 + 净变化，逐项钉字段',
      jRe(AJv, new RegExp('right->right ' + jFb['right->right']
                          + '、right->wrong ' + jFb['right->wrong']
                          + '、wrong->right ' + jFb['wrong->right']
                          + '、wrong->wrong ' + jFb['wrong->wrong']))
      && jRe(AJv, new RegExp('基线答对 ' + APw.baseline_correct
                             + '、注入后答对 ' + APw.steered_correct
                             + ' ⇒ \\*\\*净变化 ' + jNet.replace('+', '\\+') + '\\*\\*'))
      && Object.values(jFb).reduce((s, x) => s + x, 0) === APw.n_complete_pairs,
      `全表 rr=${jFb['right->right']} rw=${jFb['right->wrong']} `
      + `wr=${jFb['wrong->right']} ww=${jFb['wrong->wrong']} `
      + `合计 ${Object.values(jFb).reduce((s, x) => s + x, 0)}（须 = n_complete_pairs `
      + `${APw.n_complete_pairs}）；基线 ${APw.baseline_correct} → 注入 `
      + `${APw.steered_correct}，差 ${APw.steered_correct - APw.baseline_correct}`);

  rec('AP4 [产物层] verdict ② 的不变性声明：三处净变化逐位相同，且分母对得上',
      jInv.net_over_shipped_10 === jInv.net_over_complete_20
      && jInv.net_over_complete_20 === APw.net_change
      && jRe(AJv, new RegExp('入表 ' + APw.n_shipped + ' 题净 ' + jNet.replace('+', '\\+')
                            + ' / 完整 ' + APw.n_complete_pairs + ' 题净 '
                            + jNet.replace('+', '\\+') + '，逐位相同'))
      && jRe(AJv, new RegExp('被剔除的 ' + (APw.n_complete_pairs - APw.n_shipped)
                            + ' 题 verdict 恒为 X->X')),
      `入表 ${APw.n_shipped} 净 ${jInv.net_over_shipped_10} / 完整 `
      + `${APw.n_complete_pairs} 净 ${jInv.net_over_complete_20} / 字段 `
      + `${APw.net_change}；被剔除 ${APw.n_complete_pairs - APw.n_shipped} 题`
      + `（**完整配对**里没入表的那些。第一版我按「总题数 − 入表数」算成 `
      + `${APw.n_problems_in_batch - APw.n_shipped}，那是把 `
      + `${APw.n_incomplete_pairs} 道未闭合的题也算进去了，判据红而散文没红）`);

  rec('AP5 [产物层] verdict ③ 的 答案改变率 = changed_n / n_complete_pairs，且百分数由字段算出',
      jRe(AJv, new RegExp('答案改变率 = \\*\\*' + APw.changed_n + '/'
                            + APw.n_complete_pairs + ' = '
                            + (APw.answer_change_rate_complete * 100).toFixed(0) + '%\\*\\*'))
      && Math.abs(APw.changed_n / APw.n_complete_pairs
                  - APw.answer_change_rate_complete) < 5e-2,
      `字段 ${APw.changed_n}/${APw.n_complete_pairs} = `
      + `${(APw.changed_n / APw.n_complete_pairs).toFixed(3)}，`
      + `字段 answer_change_rate_complete=${APw.answer_change_rate_complete}`
      + `（容差 5e-2：印出的是取整后的百分数）`);

  rec('AP6 [产物层] verdict ④ 的 wrong→wrong 次数/中位/门槛/域外次数，逐项钉字段',
      jRe(AJv, new RegExp('wrong->wrong 那 ' + APw.changed_but_still_wrong
                          + ' 次的中位 \\|Δ\\| = ' + jMag.median.toFixed(1)))
      && jRe(AJv, new RegExp(jMag.n_below_100 + ' 次只动了不到 '
                            + jMag.small_magnitude_threshold))
      && jRe(AJv, new RegExp('其中 ' + jMag.out_of_domain_labels.length
                            + ' 次两臂答案都落在 AIME 答案域外'))
      && jMag.n === APw.changed_but_still_wrong,
      `w2w=${APw.changed_but_still_wrong}（= mags.n=${jMag.n}）；中位 ${jMag.median.toFixed(1)}；`
      + `门槛 ${jMag.small_magnitude_threshold}（<它的有 ${jMag.n_below_100} 次）；`
      + `域外 ${jMag.out_of_domain_labels.length} 题`);

  rec('AP7 [产物层] verdict ⑤ 的未闭合分解与撞上限计数，每个数都带分母',
      jRe(AJv, new RegExp('真正未知的只有 \\*\\*' + APw.n_incomplete_pairs
        + '\\*\\* 题（' + APw.incomplete_breakdown.one_arm_closed + ' 题只跑完一臂、'
        + APw.incomplete_breakdown.neither_closed + ' 题都没跑完）'))
      && jRe(AJv, new RegExp('它们的 ' + APw.incomplete_arms_total
        + ' 条 arm 里有 \\*\\*' + APw.incomplete_arms_at_token_cap
        + ' 条撞了 ' + APw.token_cap + ' token 上限'))
      && APw.incomplete_breakdown.one_arm_closed
         + APw.incomplete_breakdown.neither_closed
         + APw.incomplete_breakdown.unparseable === APw.n_incomplete_pairs,
      `未闭合 ${APw.n_incomplete_pairs} = ${APw.incomplete_breakdown.one_arm_closed}`
      + `+${APw.incomplete_breakdown.neither_closed}+${APw.incomplete_breakdown.unparseable}；`
      + `撞上限 ${APw.incomplete_arms_at_token_cap}/${APw.incomplete_arms_total}`
      + `（须带分母）`);

  rec('AP8 [产物层] verdict ⑥ 的翻转/p/所需数 = 三个字段，且 p 与字段同位小数',
      jRe(AJv, new RegExp('功效仍然不够：' + APw.flips + ' 次正确性翻转（'
        + APw.flips_up + ' 正 ' + APw.flips_down + ' 反）'))
      && jRe(AJv, new RegExp('双侧 p = '
        + APw.two_sided_sign_p_if_all_same_direction.toFixed(3)))
      && jRe(AJv, new RegExp('需要 \\*\\*' + APw.flips_needed_for_p05 + '\\*\\* 个同向翻转'))
      && APw.flips_up + APw.flips_down === APw.flips
      && APw.flips_needed_for_p05 <= APw.max_possible_flips,
      `翻转 ${APw.flips} = ${APw.flips_up}+${APw.flips_down}；p=${APw.flips_needed_for_p05
        ? APw.two_sided_sign_p_if_all_same_direction : '?'}；`
      + `需 ${APw.flips_needed_for_p05} 个，上限 ${APw.max_possible_flips} 个`);

  // J9 交叉核对：那句覆盖面声明的 N 必须**同时**等于产物字段与
  // axis_readouts.json 自己声明的名单长度 —— 两份产物各自声明同一个事实。
  const jAxes = (function () {
    try {
      // ⚠ axes 是**字典**（轴名 → 定义），不是数组。
      //   Python 的 sorted(dict) 给的是键，JS 的 .filter 会直接 TypeError —-
      //   而判据崩掉时脚本报的是「X 脚本崩了」，看不出是哪一行。
      return Object.keys(
        JSON.parse(readFileSync(DATA + '/axis_readouts.json', 'utf8')).axes);
    } catch (e) { return null; }
  })();
  const jOther = jAxes ? jAxes.filter(a => !a.startsWith('confid')) : null;
  rec('AP9 [产物层] not_claimed ⑤ 的「另外 N 条命名轴」= n_other_named_axes'
      + ' = axis_readouts.axes 现算（独立交叉核对）',
      jRe(AJn, new RegExp('只覆盖 ' + APw.direction + ' 一条轴的 −'
                          + Number(APw.strength).toFixed(1) + ' 单档；'
                          + '另外 ' + APw.n_other_named_axes + ' 条命名轴'))
      && jOther !== null && jOther.length === APw.n_other_named_axes
      && APw.other_named_axes.join(',') === jOther.slice().sort().join(','),
      `N=${APw.n_other_named_axes}；axis_readouts.axes=${JSON.stringify(jAxes)} → `
      + `除 confidence 外 ${jOther === null ? '?' : jOther.length} 条 `
      + `${JSON.stringify(APw.other_named_axes)}（两份产物各自声明同一个事实）`);

  // AP10：那半句「正的 <名字> 臂」必须是一个**日志里真实出现过**的方向，
  // 而不是写死的字符串。
  //
  // ⚠ 第一版用 `direction.replace(/_(up|down)$/, '_$1')` 去「翻转」后缀 ——
  //   那个替换把 `_down` 换成了 `_down` 自己（$1 就是捕获到的 down），
  //   于是正则找的是「与正的 confidence_down 臂」，而散文写的是
  //   confidence_up，判红。**判红先怀疑判据** —— 而且这里是我写的正则不对，
  //   不是产物错。翻转要显式写，且**从日志的方向集合里取**而不是拼字符串。
  const jDirs = [...new Set(COT.runs.map(r => r.direction))].sort();
  const jOtherDir = jDirs.filter(d => d !== APw.direction);
  rec('AP10 [产物层] not_claimed ⑤ 说的「正的 <名字> 臂」必须在日志的方向集合里，'
      + '且与本产物测的那条不同',
      jOtherDir.length === 1 && jDirs.length === 2
      && jRe(AJn, new RegExp('与正的 ' + jOtherDir[0] + ' 臂都不在这里')),
      `日志里出现过的方向=${JSON.stringify(jDirs)}；本产物测的是 `
      + `${APw.direction}，句子里指的是 ${JSON.stringify(jOtherDir)}`);

  // AP11 源级：手抄一旦打回源码，红。
  //
  // ⚠ 剥的范围要覆盖 **docstring**：`#` 行注释只是其中一种。
  //   这个文件的模块 docstring 里也写着「23 题 / 20 个完整配对」，
  //   而那是**文档**——它说明这个脚本在算什么，删掉它比留着它更坏。
  //   ⇒ 判据只该守「会被写进产物 / 印到控制台的那些字面量」，
  //     所以 `#` 注释与 `"""…"""` 块都要剥掉。
  //   （同第二十一笔 F8：先剥注释再扫，且额外直接扫产物。）
  const jSrcRaw = readFileSync('/Users/zhourui/code/steer3d/.cache/xcheck/'
    + 'answer_power.py', 'utf8');
  const jStripPy = t => t.replace(/^\s*#.*$/gm, '').replace(/"""[\s\S]*?"""/g, '');
  const jSrc = jStripPy(jSrcRaw);
  const jBanned = ['23 题', '20 个完整配对', '另外 3 条命名轴', '的 −0.2 单档',
    '「净变化 0」', 'n_below_100": sum(1 for m in mag_vals if m < 100'];
  const jHit = jBanned.filter(s => jSrc.includes(s));
  const jWant = ['{npb}', '{noax}', '{st:.1f}', '{odir}', '{small}', '{net:+d}',
    'SMALL_MAG', 'opposite_direction'];
  const jMiss = jWant.filter(s => !jSrc.includes(s));
  rec('AP11 [源级] 生成器里（剥行注释与 docstring 后）没有这 6 个手抄副本，'
      + '且 8 个插值占位符/常量都在',
      jHit.length === 0 && jMiss.length === 0,
      `手抄残留 ${jHit.length}/${jBanned.length}`
      + `${jHit.length ? '：' + jHit.join(' / ') : ''}；`
      + `缺失占位符 ${jMiss.length}/${jWant.length}`
      + `${jMiss.length ? '：' + jMiss.join(' / ') : ''}；`
      + `docstring 与注释里保留旧文案（有意留，交代来历）`
      + `${jBanned.filter(s => jSrcRaw.includes(s)).length} 处`);
} catch (e) {
  rec('X 脚本崩了', false, String((e && e.stack) || e).slice(0, 300));
} finally {
  cdp.close(); proc.kill('SIGKILL');
}

const pass = R.filter(x => x.p).length;
console.log(`\n=== ${pass}/${R.length} passed ===`);
R.filter(x => !x.p).forEach(x => console.log('FAIL: ' + x.n));
process.exit(pass === R.length ? 0 : 1);
