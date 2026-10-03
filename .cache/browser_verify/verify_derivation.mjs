// 验收：3D 页面上的「逐层推导链」面板。
//
// 这块面板回答的是原始问题里那句「各个 hidden states 到底最后是如何
// 推导出这个 token」。3D 场景只画残差流走到哪，逐层链回答每层各自已经
// 决定了什么。
//
// 判据盯的是**数值**，不是"元素在不在"。理由很直接：这块面板最容易出的
// 错不是不显示，而是显示一条看起来很像样的链、其实来自另一条轨迹或另
// 一个 step。那种错在 DOM 存在性判据下 100% 全绿。
//
// 三段设计：
//   1. 面板状态诚实：窗口外不许画一条空链冒充"没有一层说对"
//   2. 窗口内画出来时，柱高/绿柱/首对层与 logit_lens.json 逐值相等
//   3. 换记录后链跟着换（不同记录同一步的 per_layer 不同）
import { launch, Page, CDP } from './cdp_client.mjs';
import { readFileSync } from 'node:fs';

const URL = process.env.T3D_URL || 'http://127.0.0.1:9973/';
const PROFILE = process.env.T3D_PROFILE
  || '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_deriv_' + process.pid;
const LENS_PATH =
  '/Users/zhourui/code/steer3d/frontend/public/latent/data/logit_lens.json';

const LENS = JSON.parse(readFileSync(LENS_PATH, 'utf8'));
// ⚠⚠ 第二十七笔：这一支原来把 28 **抄了九处**（bars.length 的 ===/!==/>=
//   共 6 处、逐层循环上界 l < 28 三处，外加判据名与两条诊断文案里的
//   「28 层」「28/28」——我第一版注释写的是「四处」，数错了；
//   一个自己都数错的计数，正好是这一族缺陷的缩影），
//   而产品侧 LayerDerivationPanel 同样写着 `const N_LAYERS = 28`。
//   ⇒ 与第十三/二十六笔完全同形：判据与产品共用同一份手抄字面量，
//     产物换模型、层数变了，两边**一起错**而判据自己不会红。
//   现在判据从产物取，并要求两条独立证据一致（不一致本身就是该看见的事）。
const NL_MODEL = LENS.model?.n_layers ?? null;
const NL_VALUES = Array.isArray(LENS.per_layer_mean_p_final?.values)
  ? LENS.per_layer_mean_p_final.values.length : null;
const NL = NL_MODEL ?? NL_VALUES;
const BY_ID = new Map((LENS.trajectories || []).map((t) => [t.id, t]));

const sleep = ms => new Promise(r => setTimeout(r, ms));
const R = [];
const rec = (n, p, d) => {
  R.push({ n, p });
  console.log(`[${p ? 'PASS' : 'FAIL'}] ${n}\n       ${d}`);
};

const { proc, version } = await launch({ port: 9440, userDataDir: PROFILE,
  windowSize: '1600,1000', url: 'about:blank' });
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);

// 选一条记录并播放。播放从 step 0 开始，逐层数据只在最后 32 步，
// 所以要一路等它进窗口。
//
// reset 和 Run 必须都点。第一版只点了 reset：reset 会停掉流，于是
// `latest` 永远是 null，面板一直显示 "Waiting for the first frame…"，
// F4–F9 连带全红。那是判据自己的流程错，不是页面坏 —— 同一时刻
// verify_real_replay.mjs 在同一个页面上 12/12 全绿。
const pickAndStart = (pred) => page.eval(`(() => {
  const s = [...document.querySelectorAll('select')].find(x =>
    [...x.options].some(o => /^aime__/.test(o.value)));
  if (!s) return null;
  const opt = [...s.options].find(o => ${pred});
  if (!opt) return null;
  s.value = opt.value;
  s.dispatchEvent(new Event('change', { bubbles: true }));
  const btn = (re) => [...document.querySelectorAll('button')]
    .find(b => re.test(b.textContent || ''));
  const rst = btn(/reset/i); if (rst) rst.click();
  const run = btn(/start|play|run/i); if (run) run.click();
  return opt.value;
})()`);

// 从面板里读当前状态：data-derivation 属性 + 画出来的柱子
//
// text 截取长度：读整段 innerText。第一版截 200 字符，于是 F7 判红 —
// 「这是 probe 而非 forward pass」那句声明写在面板最底部，被截掉了。
// 判据红不等于页面缺东西，判据只能证明它读到的东西。
const readPanel = () => page.eval(`(() => {
  const el = document.querySelector('[data-derivation]');
  if (!el) return { state: 'absent' };
  const state = el.getAttribute('data-derivation');
  const bars = [...el.querySelectorAll('rect[data-layer]')].map(r => ({
    layer: Number(r.getAttribute('data-layer')),
    ok: r.getAttribute('data-ok') === '1',
    p: Number(r.getAttribute('data-pfinal')),
  }));
  return { state, bars, text: (el.innerText || '').replace(/\\s+/g, ' '),
           head: (el.innerText || '').replace(/\\s+/g, ' ').slice(0, 200),
           // 当前记录窗口。F9 要靠它确认"面板真的切到新记录了"——
           // 没有它就只能盲等，而盲等正是 50% flake 的来源。
           win: (() => { const m = /steps (\\d+)[–-](\\d+)/.exec(el.innerText || '');
             return m ? [Number(m[1]), Number(m[2]) + 1] : null; })() };
})()`);

// 柱子的**实际绘制高度**。必须单独读：`data-pfinal` 是面板拿到的数字，
// 而读者看到的是 rect 的 height。两者可以是两回事 —— 变异 D1 把 height
// 全改成常数而 data-pfinal 不变，只查 data-pfinal 的判据 14/14 全绿，
// 屏幕上却是一排等高的柱子，正好是"判据测的不是读者看到的东西"。
const readDrawn = () => page.eval(`(() => {
  const el = document.querySelector('[data-derivation]');
  if (!el) return [];
  return [...el.querySelectorAll('rect[data-layer]')].map(r => ({
    layer: Number(r.getAttribute('data-layer')),
    h: Number(r.getAttribute('data-drawn')),
    y: Number(r.getAttribute('y')),
    hAttr: Number(r.getAttribute('height')),
  }));
})()`);

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

  // 等轨迹选择器 + 面板出现
  let ready = false;
  for (let i = 0; i < 15; i++) {
    ready = await page.eval(`!!document.querySelector('[data-derivation]')
      && !!([...document.querySelectorAll('select')].find(x =>
        [...x.options].some(o => /^aime__/.test(o.value))))`);
    if (ready) break;
    await sleep(1200);
  }
  rec('F0 轨迹选择器与逐层面板都已挂载', ready, ready ? '' : '等了 ~18s 仍未出现');

  // logit_lens.json 从 3D 页面真的取到了
  const lensState = await page.eval(`(async () => {
    const r = await fetch('/latent/data/logit_lens.json');
    if (!r.ok) return { ok: false, status: r.status };
    const j = await r.json();
    return { ok: true, n: (j.trajectories || []).length };
  })()`);
  rec('F1 logit_lens.json 从 3D 页面路径可取且含 48 条',
      lensState.ok && lensState.n === 48, JSON.stringify(lensState));

  // 速度滑块是 range input，max=4。992 步按 0.05s/步 的节拍，1x 要
  // 接近一分钟；拉到 4x 才在可接受的等待内。
  const setSpeedMax = () => page.eval(`(() => {
    const r = [...document.querySelectorAll('input[type=range]')][0];
    if (!r) return false;
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, 'value').set;
    setter.call(r, r.max);
    r.dispatchEvent(new Event('input', { bubbles: true }));
    r.dispatchEvent(new Event('change', { bubbles: true }));
    return r.value;
  })()`);

  /* ---------------------------------------------------------------- */
  // 选一条记录并播放。
  const recId = await pickAndStart('/__think$/.test(o.value)');
  rec('F2 选中一条 think 记录', !!recId && BY_ID.has(recId), `id=${recId}`);

  // 先证明帧真的在流，否则后面每一条都是空断言 —— 上一版就是死在这：
  // reset 之后没点 Run，latest 恒为 null，6 条连带全红，而页面是好的。
  const sp = await setSpeedMax();
  let moving = false;
  for (let i = 0; i < 20; i++) {
    await sleep(1200);
    const n = await page.eval(`(() => {
      const m = (document.body.innerText || '').match(/(\\d+)\\s+tokens/);
      return m ? parseInt(m[1], 10) : 0;
    })()`);
    if (n >= 3) { moving = true; break; }
  }
  rec('F2b 选记录并 Run 之后帧真的在流（speed=' + sp + '）', moving,
      moving ? '' : '等了 ~24s 面板上仍是 0 tokens');

  let early = null;
  for (let i = 0; i < 20; i++) {
    await sleep(1200);
    early = await readPanel();
    if (early.state === 'out-of-window' || early.state === 'ready') break;
  }
  rec('F3 播放初期面板诚实说"在窗口外"，不画空链',
      early.state === 'out-of-window',
      `state=${early.state} | ${String(early.head).slice(0, 120)}`);
  rec('F3b 窗口外时一根柱子都没画',
      early.bars.length === 0, `bars=${early.bars.length}`);

  /* ---------------------------------------------------------------- */
  // 拖步滑块直接定位到窗口内。
  //
  // 不用「等播放自己走到窗口」：实测 speed=4 下约 8 步/秒，1024 步的轨迹
  // 要 ~2 分钟，而 T 最短的轨迹只有 265 步。判据等两分钟只为看一张图，
  // 既慢又不稳定。第一版就是这么写的，F4 差临门一脚判红。
  //
  // 滑块是面板自己的控件，所以这条判据顺带证明了"任何一步都能直接看"。
  const traj = BY_ID.get(recId);
  const win = traj.window;
  const targetT = win[0] + 2;
  const target = traj.steps.find((s) => s.t === targetT);

  const slid = await page.eval(`(() => {
    const r = document.querySelector('[data-deriv-step]');
    if (!r) return null;
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, 'value').set;
    setter.call(r, ${targetT});
    r.dispatchEvent(new Event('input', { bubbles: true }));
    r.dispatchEvent(new Event('change', { bubbles: true }));
    return r.value;
  })()`);
  rec('F3c 步滑块存在且可拖到窗口内任一步', slid != null && Number(slid) === targetT,
      `slider=${slid} target=${targetT} window=[${win[0]},${win[1]})`);

  let got = null, landedT = null;
  for (let i = 0; i < 12; i++) {
    await sleep(700);
    got = await readPanel();
    if (got.state === 'ready' && got.bars.length >= NL) {
      const m = String(got.text).match(/Step\s+(\d+)/);
      landedT = m ? Number(m[1]) : null;
      break;
    }
  }

  rec(`F4 定位到窗口内步后面板画出 ${NL} 层链条`,
      got.state === 'ready' && got.bars.length === NL,
      `state=${got.state} bars=${got.bars.length} t=${landedT} slider=${slid}`);

  /* ---------------------------------------------------------------- */
  // 核心：逐值比对。不比"有没有 28 根柱子"，比每一根的 p_final 和 correct。
  rec('F4b 面板落地的这一步就是滑块指定的那一步（没读错步）',
      landedT === targetT,
      `panel t=${landedT} slider=${slid} json has t=${targetT}: ${!!target}`);

  if (got.bars.length === NL && target) {
    const pl = target.per_layer;
    const drawn = await readDrawn();
    const bad = [];
    for (let l = 0; l < NL; l++) {
      const wantP = pl.p_final[l];
      const wantOk = !!pl.correct[l];
      const g = got.bars[l];
      if (Math.abs(g.p - wantP) > 1e-6) bad.push(`L${l} p ${g.p} != ${wantP}`);
      else if (g.ok !== wantOk) bad.push(`L${l} ok ${g.ok} != ${wantOk}`);
      else if (g.layer !== l) bad.push(`L${l} layer index ${g.layer}`);
      // 画出来的高度必须由 p_final 决定。plotH = 132-12-20 = 100，
      // 且 Math.max(1.5, ...) 给极小值一个 1.5px 的地板。
      else if (drawn[l]) {
        const wantH = Math.max(0.015, Math.min(wantP, 1));
        if (Math.abs(drawn[l].h - wantH) > 2e-3) {
          bad.push(`L${l} drawn height ${drawn[l].h} != p_final ${wantP}`);
        }
      }
    }
    rec('F5 每根柱子的 p_final、correct 与实际绘制高度都与 JSON 一致',
        bad.length === 0 && drawn.length === NL,
        bad.length ? bad.slice(0, 4).join(' | ')
                   : `${NL}/${NL} 一致 (t=${target.t}, 高度也由 p_final 决定)`);

    // ⚠⚠ 第二十七笔新增：判据核**输入**（面板认为自己有几层），不只核答案。
    //   第二十六笔 S18 的同款：把 N_LAYERS 换成别的数而柱高仍按同样比例缩放，
    //   答案是对的，可「一共几层」这件事已经错了。
    //   两条独立证据（model.n_layers 与 per_layer 逐层长度）必须一致 ——
    //   不一致本身就是该看见的事，那时「取其一」会把矛盾藏起来。
    const nlPage = JSON.parse(await page.eval(`(() => {
      const el = document.querySelector('[data-derivation]');
      const v = el.getAttribute('data-n-layers');
      return JSON.stringify({ state: el.getAttribute('data-derivation'),
                              nLayers: v === null ? null : Number(v) });
    })()`));
    rec('F5b 面板自称的层数 == 产物层数（判输入；两条产物证据须一致）',
        NL_MODEL != null && NL_VALUES === NL_MODEL
        && nlPage.state === 'ready' && nlPage.nLayers === NL,
        `产物 model.n_layers=${NL_MODEL}  per_layer_mean_p_final.values.length=${NL_VALUES}  `
        + `页面 data-n-layers=${nlPage.nLayers}（state=${nlPage.state}）  `
        + (NL_MODEL !== NL_VALUES
           ? '❌ 两条产物证据不一致 ⇒ 「取其一」会把矛盾藏起来'
           : '两条产物证据一致'));

    const flc = target.first_layer_correct;
    const firstGreen = got.bars.findIndex((b) => b.ok);
    rec('F6 首个说对的层与 JSON 的 first_layer_correct 一致',
        firstGreen === flc,
        `page first green=L${firstGreen} json first_layer_correct=${flc}`);

    /* ---------------------------------------------------------------- */
    // F6b：跨多步扫一遍绿柱规则。
    //
    // 为什么必须多步：单步判据在这个数据集上有 66% 的概率白送通过。
    // 变异 D2 把绿柱规则从 `correct[l]` 换成 `p_final > 0.5`，两者在
    // 1536 步里有 521 步不同 —— 但判据只看了 t=994 那一步，而那一步
    // 两个数组**完全相同**（前 20 层 0、后 8 层 1），于是 D2 14/14 全绿。
    //
    // 一条判据若只在一步上比对，它的通过与否有一部分来自运气。扫多步
    // 之后这个比例降到 0。
    let scanBad = [], scanSteps = 0;
    for (const st of traj.steps.slice(0, 8)) {
      await page.eval(`(() => {
        const r = document.querySelector('[data-deriv-step]');
        if (!r) return null;
        const setter = Object.getOwnPropertyDescriptor(
          window.HTMLInputElement.prototype, 'value').set;
        setter.call(r, ${st.t});
        r.dispatchEvent(new Event('input', { bubbles: true }));
        r.dispatchEvent(new Event('change', { bubbles: true }));
        return r.value;
      })()`);
      await sleep(450);
      const p = await readPanel();
      if (p.state !== 'ready' || p.bars.length !== NL) {
        scanBad.push(`t=${st.t} state=${p.state} bars=${p.bars.length}`);
        continue;
      }
      scanSteps++;
      for (let l = 0; l < NL; l++) {
        if (p.bars[l].ok !== !!st.per_layer.correct[l]) {
          scanBad.push(`t=${st.t} L${l}`);
        }
      }
    }
    rec('F6b 跨 8 步扫描：绿柱逐层等于 JSON 的 correct[]',
        scanBad.length === 0 && scanSteps >= 6,
        scanBad.length ? scanBad.slice(0, 4).join(' | ')
                       : `${scanSteps} 步 × ${NL} 层 = ${scanSteps * NL} 格全对`);

    rec('F7 文案诚实标注这是 probe 而非 forward pass',
        /probe, not a forward pass/.test(got.text),
        /probe, not a forward pass/.test(got.text) ? '已标注' : '缺 probe 声明');
  } else {
    rec('F5 每根柱子的 p_final、correct 与实际绘制高度都与 JSON 一致',
        false, `柱子数 ${got.bars.length}, target=${!!target}`);
    rec('F6 首个说对的层与 JSON 的 first_layer_correct 一致', false, '同上');
    rec('F6b 跨 8 步扫描：绿柱逐层等于 JSON 的 correct[]', false, '同上');
    rec('F7 文案诚实标注这是 probe 而非 forward pass', false, '同上');
  }

  /* ---------------------------------------------------------------- */
  // 换记录：链必须换成新记录的数据。
  // 这一条专门防"链画的是上一条记录" —— 那种错在存在性判据下 100% 绿。
  const other = LENS.trajectories.find(
    (t) => t.id !== recId && t.mode === 'think' && t.window[0] === win[0]);
  if (other) {
    await pickAndStart(
      `/^${other.id.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$/.test(o.value)`);
    const otherT = other.window[0] + 2;
    const ot = other.steps.find((s) => s.t === otherT);

    // 必须等面板**真的切到**新记录之后再设滑块。
    //
    // pickAndStart 是「换记录 → reset → start」同步连发，而 React 的
    // state 更新是异步落地的。第一版在这里紧接着就 dispatch 滑块的
    // input 事件（setFocusedStep(994)），于是和 reset() 的
    // `focusedStep: null` 抢同一个 state：谁后落地谁赢。reset 晚落地
    // 时 pick 被抹掉，stepId 退回 latest.step_id —— 而新流刚开头，
    // 那时 step_id 约 96，落在窗口 992–1023 之外，面板就永远停在
    // out-of-window。表现为 F9 约 50% 概率转红。
    //
    // 等的是**面板的窗口**变成新记录的窗口：这一步只有 currentTrajectory
    // 已经更新、且 reset 已经落地之后才会发生。
    const winMoved = await (async () => {
      for (let i = 0; i < 20; i++) {
        await sleep(500);
        const p = await readPanel();
        if (p.win && p.win[0] === other.window[0]
            && p.win[1] === other.window[1]) return true;
      }
      return false;
    })();

    const setRes = await page.eval(`(() => {
      const r = document.querySelector('[data-deriv-step]');
      if (!r) return { err: 'no slider' };
      const setter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype, 'value').set;
      setter.call(r, ${otherT});
      const afterSet = r.value;      // 浏览器会按 min/max 夹取
      r.dispatchEvent(new Event('input', { bubbles: true }));
      r.dispatchEvent(new Event('change', { bubbles: true }));
      return { min: r.min, max: r.max, want: ${otherT}, afterSet };
    })()`);

    let sig = null, sigState = null, sigText = '';
    for (let i = 0; i < 12; i++) {
      await sleep(700);
      const p = await readPanel();
      sigState = p.state;
      sigText = String(p.head || '');
      if (p.state === 'ready' && p.bars.length >= NL) { sig = p; break; }
    }
    const after = await page.eval(`(() => {
      const r = document.querySelector('[data-deriv-step]');
      const el = document.querySelector('[data-derivation]');
      return { sliderValue: r ? r.value : null,
               min: r ? r.min : null, max: r ? r.max : null,
               state: el ? el.getAttribute('data-derivation') : null };
    })()`);
    let ok = false;
    // 失败时把面板说的整段话 + 滑块状态一起打出来。只报 bars=0 分不清是
    // "没进窗口"、"JSON 没 join 上"还是"画错了"——三种修法完全不同；
    // 而"没进窗口"又要分清是判据没等、还是面板真没切过去。
    let why = `other=${other.id} winMoved=${winMoved} want t=${otherT} `
            + `set=${JSON.stringify(setRes)} after=${JSON.stringify(after)} | `
            + `state=${sigState} bars=${sig ? sig.bars.length : 0} | ${sigText.slice(0, 130)}`;
    if (sig && sig.bars.length === NL && ot) {
      const bad = [];
      for (let l = 0; l < NL; l++) {
        if (Math.abs(sig.bars[l].p - ot.per_layer.p_final[l]) > 1e-6) bad.push(`L${l}`);
      }
      ok = bad.length === 0;
      why = ok ? `${NL}/${NL} 匹配 ${other.id} t=${otherT}` : `不符层: ${bad.slice(0, 5).join(',')}`;
    } else if (!ot) {
      why += ` (JSON 里没有 t=${otherT})`;
    }
    rec('F9 换记录后链条跟着换成新记录的数据', ok, why);
  } else {
    rec('F9 换记录后链条跟着换成新记录的数据', false, '找不到对照记录');
  }

  /* ---------------------------------------------------------------- */
  // F11：轨迹切换本身要清掉陈旧 pick —— **不经过 reset**。
  //
  // 为什么必须单列一条：F9 的流程里 pickAndStart 会点 reset，而 reset()
  // 本来就把 focusedStep 清成 null。所以 F9 就算等稳了，也测不到
  // "换记录不清陈旧 pick"这个缺陷 —— 修好 F9 的等待之后，D7/D8 两条
  // 变异反而双双变绿。判据变稳的同时变弱了，这不行。
  //
  // 这里直接走 select 的 change，**不点 reset**：
  //   1. 在记录 A 上把滑块拖到 A 窗口内的某一步（面板画出来）
  //   2. 只 dispatch change 切到记录 B
  //   3. 断言面板自报的步号是 B 的步，或者是 null（等第一帧）
  // 缺陷状态下，面板会继续报 A 的步号 —— 一个在 B 里根本不存在的 t。
  {
    const A = BY_ID.get(recId) || LENS.trajectories.find(t => t.mode === 'think');
    // 必须挑**窗口不相交**的 B。第一版只要求 window[0] 不同，结果选到
    // window[0] 相同、窗口完全重叠的记录，于是 A 的 pick 在 B 里也"合法"，
    // 判据根本分不清修好没修好。
    const disjoint = (x, y) => y.window[0] >= x.window[1] || y.window[1] <= x.window[0];
    const B = LENS.trajectories.find(
      (t) => t.id !== A.id && t.mode === 'think' && disjoint(A, t));
    if (!B) {
      rec('F11 切记录时清掉上一条记录的步号（不经 reset）', false,
          '找不到窗口与 A 不相交的记录');
    } else {
      const aT = A.window[0] + 5;
      await page.eval(`(() => {
        const s = [...document.querySelectorAll('select')].find(x =>
          [...x.options].some(o => /^aime__/.test(o.value)));
        const opt = [...s.options].find(o => o.value === ${JSON.stringify(A.id)});
        if (opt) { s.value = opt.value; s.dispatchEvent(new Event('change', { bubbles: true })); }
        const r = document.querySelector('[data-deriv-step]');
        if (r) {
          const setter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value').set;
          setter.call(r, ${aT});
          r.dispatchEvent(new Event('input', { bubbles: true }));
          r.dispatchEvent(new Event('change', { bubbles: true }));
        }
        return r ? r.value : null;
      })()`);
      await sleep(1500);
      const onA = await page.eval(`(() => {
        const el = document.querySelector('[data-derivation]');
        return { traj: el.getAttribute('data-traj'),
                 step: el.getAttribute('data-step-id') };
      })()`);

      // 只切记录，不点 reset
      await page.eval(`(() => {
        const s = [...document.querySelectorAll('select')].find(x =>
          [...x.options].some(o => /^aime__/.test(o.value)));
        const opt = [...s.options].find(o => o.value === ${JSON.stringify(B.id)});
        if (!opt) return null;
        s.value = opt.value;
        s.dispatchEvent(new Event('change', { bubbles: true }));
        return opt.value;
      })()`);

      let saw = null;
      for (let i = 0; i < 20; i++) {
        await sleep(400);
        saw = await page.eval(`(() => {
          const el = document.querySelector('[data-derivation]');
          return { traj: el.getAttribute('data-traj'),
                   step: el.getAttribute('data-step-id'),
                   state: el.getAttribute('data-derivation') };
        })()`);
        if (saw.traj === B.id) break;
      }
      // 口径：面板自报的步**不得落在 A 的窗口里**。
      //
      // 第一版去查 `B 的 steps 里有没有这个 t`，是错的：logit_lens.json
      // 的 `steps` 只含**读出窗口那 32 步**，而新流开头的 step_id（比如
      // 64）是 B 轨迹里真实存在、只是还没到窗口的步。拿窗口的步集合当
      // "合法步"的全集，会把正确的行为判成红的。
      //
      // 真正对应缺陷的是：读者在 A 上选的步一定落在 A 的窗口内；面板在
      // 切到 B 之后还报着它，就说明陈旧 pick 没被清掉。A、B 窗口不相交，
      // 所以「报的步是否落在 A 的窗口内」是一个干净的判别式。
      const stepNum = saw.step === '' || saw.step == null ? null : Number(saw.step);
      const inAWin = stepNum != null
                     && stepNum >= A.window[0] && stepNum < A.window[1];
      rec('F11 切记录时清掉上一条记录的步号（不经 reset）',
          saw.traj === B.id && !inAWin,
          `A=${A.id} win=${JSON.stringify(A.window)} 在 A 上选 t=${aT} -> `
          + `面板 ${JSON.stringify(onA)}; `
          + `切到 B=${B.id} win=${JSON.stringify(B.window)}（不相交）后 面板 `
          + `${JSON.stringify(saw)}; `
          + `报的步 ${stepNum} 落在 A 窗口内? ${inAWin}`
          + (inAWin ? `  <-- 还在报 A 的步` : ''));
    }
  }

  /* ---------------------------------------------------------------- */
  // F12：窗口**重叠**时，读者在新记录里也合法的那个 pick 必须存活。
  //
  // F11 管的是"该清的清掉"，F12 管的是"不该清的别清"。两者一起，产品
  // 行为才是完整的：在新记录里无意义的步要丢，在新记录里仍然成立的步
  // 留着（读者不必重新选）。
  //
  // 有了 F12 之后，变异 D8（无条件全清）才有牙齿：它会把这个合法的
  // pick 也抹掉。没有 F12 的话，D8 天然满足 F11，判据"没红"并不说明
  // 缺陷不存在，只说明那条判据测的不是这件事 —— 那是**变异指错了
  // 判据**，不是判据没牙齿。
  {
    const A2 = BY_ID.get(recId) || LENS.trajectories.find(t => t.mode === 'think');
    const overlap = (x, y) => y.window[0] < x.window[1] && y.window[1] > x.window[0];
    const B2 = LENS.trajectories.find(
      (t) => t.id !== A2.id && t.mode === 'think' && overlap(A2, t));
    if (!B2) {
      rec('F12 窗口重叠时保留在新记录里仍合法的步号', false,
          '找不到窗口与 A 重叠的记录');
    } else {
      const a2T = A2.window[0] + 5;
      await page.eval(`(() => {
        const s = [...document.querySelectorAll('select')].find(x =>
          [...x.options].some(o => /^aime__/.test(o.value)));
        const opt = [...s.options].find(o => o.value === ${JSON.stringify(A2.id)});
        if (opt) { s.value = opt.value; s.dispatchEvent(new Event('change', { bubbles: true })); }
        const r = document.querySelector('[data-deriv-step]');
        if (r) {
          const setter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value').set;
          setter.call(r, ${a2T});
          r.dispatchEvent(new Event('input', { bubbles: true }));
          r.dispatchEvent(new Event('change', { bubbles: true }));
        }
      })()`);
      await sleep(1500);
      const before2 = await page.eval(`(() => {
        const el = document.querySelector('[data-derivation]');
        return { traj: el.getAttribute('data-traj'),
                 step: el.getAttribute('data-step-id') };
      })()`);
      await page.eval(`(() => {
        const s = [...document.querySelectorAll('select')].find(x =>
          [...x.options].some(o => /^aime__/.test(o.value)));
        const opt = [...s.options].find(o => o.value === ${JSON.stringify(B2.id)});
        if (!opt) return null;
        s.value = opt.value;
        s.dispatchEvent(new Event('change', { bubbles: true }));
        return opt.value;
      })()`);
      let saw2 = null;
      for (let i = 0; i < 20; i++) {
        await sleep(400);
        saw2 = await page.eval(`(() => {
          const el = document.querySelector('[data-derivation]');
          return { traj: el.getAttribute('data-traj'),
                   step: el.getAttribute('data-step-id'),
                   state: el.getAttribute('data-derivation') };
        })()`);
        if (saw2.traj === B2.id) break;
      }
      rec('F12 窗口重叠时保留在新记录里仍合法的步号',
          saw2.traj === B2.id && Number(saw2.step) === a2T,
          `A=${A2.id} win=${JSON.stringify(A2.window)} 选 t=${a2T} -> ${JSON.stringify(before2)}; `
          + `切到 B=${B2.id} win=${JSON.stringify(B2.window)}（重叠）后 ${JSON.stringify(saw2)}; `
          + `pick 是否存活 ${Number(saw2.step) === a2T}`
          + (Number(saw2.step) === a2T ? '' : '  <-- 合法 pick 被误清'));
    }
  }

  const errs = page.events
    .filter(e => e.method === 'Runtime.consoleAPICalled' && e.params.type === 'error')
    .map(e => (e.params.args || []).map(a => a.value ?? a.description ?? '').join(' '))
    .filter(t => !/favicon|Failed to load resource/i.test(t));
  /* ==================== D 组：sampling 的恒等式 ==================== */
  // ⚠ **这一组在产物层**：LayerDerivationPanel 只读 `lens.trajectories`，
  //   全组件 0 次出现 `sampling` ⇒ 这些字段**不渲染**，渲染层判据够不着。
  //   与 A7 / B8 同一处置：必须说清层级。
  //
  // 第十九笔的起点：`sampling.identity` 是一句**印出来的断言**
  //   「n_tokens == n_steps * n_layers: 43008 == 1536 * 28」
  // 而它只是一个 f-string —— n_steps / n_layers 若变了而 n_tokens 的算法没跟上，
  // 它照样把「X == Y * Z」印出来，X ≠ Y*Z 时**没有任何东西会红**。
  // ⇒ 判据必须自己把这条恒等式算一遍，并且核对那句字符串。
  const SP = LENS.sampling || {};
  const TR = LENS.trajectories || [];
  const widths = [...new Set(TR.map(t => t.window[1] - t.window[0]))];
  const dProbs = new Set(TR.map(t => t.problem)).size;
  const dModes = new Set(TR.map(t => t.mode)).size;
  const dSteps = TR.length * (widths.length === 1 ? widths[0] : NaN);
  const dTokens = dSteps * SP.n_layers;

  rec('D0 前置：sampling 字段齐全，窗口宽度**唯一**，且层数与 model 一致',
      SP.n_traj != null && SP.n_steps != null && SP.n_layers != null
      && SP.n_tokens != null && widths.length === 1
      && SP.n_layers === LENS.model.n_layers
      && SP.n_layers === LENS.aggregate.n_layers,
      `窗口宽度集合=${JSON.stringify(widths)} | 层数 sampling=${SP.n_layers} `
      + `model=${LENS.model.n_layers} aggregate=${LENS.aggregate.n_layers}`);

  rec('D1 n_traj / steps_per_traj / n_steps 必须与 trajectories 现算一致',
      SP.n_traj === TR.length
      && SP.steps_per_traj === widths[0]
      && SP.n_steps === dSteps
      && SP.n_problems === dProbs && SP.n_modes === dModes
      && dProbs * dModes === TR.length,
      `现算 traj=${TR.length} 宽=${widths[0]} n_steps=${dSteps} 题=${dProbs} 模式=${dModes}`
      + `（题×模式=${dProbs * dModes}）| 产物 n_traj=${SP.n_traj} `
      + `steps_per_traj=${SP.steps_per_traj} n_steps=${SP.n_steps} `
      + `n_problems=${SP.n_problems} n_modes=${SP.n_modes}`);

  // ---- 本笔的核心：那句被印出来的等式 ----
  rec('D2 **恒等式 n_tokens == n_steps × n_layers** 必须真的成立（不是只印出来）',
      SP.n_tokens === dTokens && SP.n_tokens === SP.n_steps * SP.n_layers,
      `现算 ${dSteps} × ${SP.n_layers} = ${dTokens} | 产物 n_tokens=${SP.n_tokens}`
      + ` | sampling 印的是：${SP.identity}`);

  rec('D3 identity 那句字符串必须印出与现算**相同**的三个数（它有能力印一个假等式）',
      SP.identity === `n_tokens == n_steps * n_layers: ${SP.n_tokens} == ${SP.n_steps} * ${SP.n_layers}`
      && SP.identity.includes(String(dTokens)) && SP.identity.includes(String(dSteps))
      && SP.identity.includes(String(SP.n_layers)),
      `期望「n_tokens == n_steps * n_layers: ${dTokens} == ${dSteps} * ${SP.n_layers}」`
      + `；实际：${SP.identity}`);

  // ---- rule 散文里的三个数（48 / 24 / 32）不许再有一个是写死的 ----
  rec('D4 rule 散文里的 traj / 题数 / 窗口宽必须等于现算值（带锚点取数，非 includes）',
      new RegExp('all ' + TR.length + ' trajectories').test(SP.rule || '')
      && new RegExp('\\(' + dProbs + ' problems x').test(SP.rule || '')
      && new RegExp('LAST ' + widths[0] + ' steps').test(SP.rule || ''),
      `现算 ${TR.length} / ${dProbs} / ${widths[0]}；原文：${SP.rule}`);

  rec('D5 n_tokens_meaning 说的口径必须与恒等式一致（read-outs = 每步每层一次 unembedding）',
      /n_steps \* n_layers/.test(SP.n_tokens_meaning || '')
      && /one unembedding per step per layer/.test(SP.n_tokens_meaning || '')
      && SP.n_tokens === SP.n_steps * SP.n_layers,
      SP.n_tokens_meaning || '（缺）');

  rec('F10 页面无 console error', errs.length === 0,
      errs.length ? errs.slice(0, 2).join(' | ') : 'none');

  // F8 源级：「layers 0–27」里的上界必须由 N_LAYERS 推出来，不许手写。
  //   这一段随播放进度变化（Step N is outside the readout window…），
  //   所以它在 C5 的「有实质文字但没被登记」名单里；而 N_LAYERS=28 时
  //   写死 27 与真值相同 ⇒ 任何渲染层判据都抓不到「值恰好正确却写死」那一类。
  rec('F8 源级：读出窗口说明里的层跨度必须取自 N_LAYERS，不许写死 0–27',
    (() => {
      const raw = readFileSync('/Users/zhourui/code/steer3d/frontend/components/'
                               + 'LayerDerivationPanel.tsx', 'utf8');
      const code = raw.replace(/\{\/\*[\s\S]*?\*\/\}/g, '')
                       .split('\n').map(l => l.replace(/\/\/.*$/, '')).join('\n');
      const i = code.indexOf('steps were probed');
      if (i < 0) return false;
      const seg = code.slice(Math.max(0, i - 200), i + 220);
      // ⚠ 防真空通过：修复后的写法必须在场
      return /N_LAYERS\s*-\s*1/.test(seg) && !/0[–-]27\b/.test(seg);
    })(),
    '层跨度上界写成字面量 0–27 时与现算的真值相同，渲染层在构造上无解；'
  + '第二十七笔已把它改成现算，本条守的是「那个字面量不许回来」');
} catch (e) {
  rec('X 脚本崩了', false, String((e && e.stack) || e).slice(0, 300));
} finally {
  cdp.close(); proc.kill('SIGKILL');
}

const pass = R.filter((x) => x.p).length;
console.log(`\n=== ${pass}/${R.length} passed ===`);
R.filter((x) => !x.p).forEach((x) => console.log('FAIL: ' + x.n));
process.exit(pass === R.length ? 0 : 1);
