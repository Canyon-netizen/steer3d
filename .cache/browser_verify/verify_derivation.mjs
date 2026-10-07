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

/* ⚠⚠ 第四态：前置未建立（NOT-ESTABLISHED）。
 *
 * 这一支有 13 条检查，其中 5 条问的是「**实时回放进行中**面板怎么表现」。
 * 那 5 条的前提是后端在跑（ws://host:9503/ws 有东西应答）。
 * 后端不在时：
 *   · 旧写法把它们记成 FAIL —— 而 FAIL 的意思是「**验过了，不合格**」，
 *     它明明一次都没验过；
 *   · 更糟的是 F3b 在旧面板上**蒙对过**：面板卡在 no-traj 时 0 根柱子，
 *     「窗口外不许画柱子」这条恰好成立，于是它拿到了一个假的绿。
 * 「没验过」和「验过但不合格」在 RED 计数里长得一模一样 ——
 * 与 run_chain 第四版那个「UNJUDGED 提前 return」的洞同族。
 *
 * ⇒ 单独一态，不进 pass 也不进 fail，且**在汇总行里显式报出条数**。
 *   判据自己也不许在「大部分没验过」时报通过。
 */
const NA = [];
const recNA = (n, why) => {
  NA.push(n);
  console.log(`[  NA ] ${n}\n       前置未建立：${why}`);
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
  /* ⚠⚠ F0 原来是一条**复合断言**：「轨迹选择器**与**逐层面板都已挂载」。
   *   两半的前置完全不同 ——
   *     · 面板挂载：只依赖 logit_lens.json 取到，与后端无关；
   *     · 选择器：只在实时后端报出录制名时才出现（ControlPanel 的 pickList）。
   *   合在一起时，后端不在 ⇒ 整条判红 ⇒ 「面板没挂载」这个**错误的推论**
   *   会被读者读出来。旧面板停在 no-traj 时它红，读者会以为面板坏了；
   *   而它的真实原因是选择器不在。
   *   ⇒ 拆成两条：能验的照验，验不了的单列。
   */
  const panelMounted = await page.eval(`(() => {
    const el = document.querySelector('[data-derivation]');
    return !!el && el.getAttribute('data-derivation') !== 'loading';
  })()`);
  rec('F0a 逐层面板已挂载（不是 loading）', panelMounted,
      `state=${(await readPanel()).state}`);

  /* 连接状态读**读者能看见的那行字**，不读 store。
   * page.tsx:136 渲染的就是 "connected" / "disconnected" 两个字。
   * 判据主体必须是可见文案 —— 读 store 的话，判据和产品共用一份真相，
   * store 错了两边一起错，假绿。 */
  const conn = await page.eval(`(() => {
    const hit = [...document.querySelectorAll('span,div')]
      .map(e => (e.textContent || '').trim())
      .find(t => t === 'connected' || t === 'disconnected');
    return hit || 'absent';
  })()`);

  const pickerPresent = await page.eval(`!!([...document.querySelectorAll('select')]
      .find(x => [...x.options].some(o => /^aime__/.test(o.value))))`);
  if (pickerPresent) {
    rec('F0b 轨迹选择器已挂载', true, `conn=${conn}`);
  } else if (conn === 'disconnected') {
    /* 后端真的不在 ⇒ 选择器「还没出现」是事实，不是缺陷。 */
    recNA('F0b 轨迹选择器已挂载',
      '页面显示 disconnected，后端确实不在；选择器只在实时后端报出录制名时渲染');
  } else {
    /* ⚠⚠ 这一支是补上的：后端**在线**却没给出 `aime__` 开头的录制名，
     *   那是后端报错了东西，是红，不是「前置没建立」。
     *   原来这两种都报 NA，于是一个坏掉的后端可以让整套判据安静地
     *   全部退回 NA —— 不产生任何红，却看上去只是「环境不可用」。
     *   判据不吭声的时候和判绿一样危险。 */
    rec('F0b 轨迹选择器已挂载', false,
      `页面显示 ${conn}（后端在线），却没有含 aime__ 选项的选择器 `
      + '⇒ 后端报出的录制名与产物 logit_lens.json 对不上，这是错不是缺');
  }

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
  // 「实时回放在场吗」这一条，是后面 5 条的**共同前提**。
  //
  // 判据用面板自己印的那个标记（`data-deriv-default`）而不是去猜：
  // 面板在没有实时流时会自己打开一条录制并**声明**这是它自己挑的。
  // 有这个声明 ⇒ 面板不在跟踪任何实时帧 ⇒ 播放期的断言无法建立。
  const panelLive = await page.eval(`(() => {
    const el = document.querySelector('[data-derivation]');
    return {
      present: !!el,
      selfOpened: !!(el && el.querySelector('[data-deriv-default]')),
      state: el ? el.getAttribute('data-derivation') : null,
      traj: el ? el.getAttribute('data-traj') : null,
    };
  })()`);
  const livePrecondition = panelLive.present && !panelLive.selfOpened;
  /* 这一支**不能**照 F0b 那样直接判红：页面显示 connected 但还没点 Run，
   * 帧确实一帧都没来，这是正常的时序，不是缺陷。所以仍然报 NA ——
   * 但必须把连接状态**印出来**，否则「后端不在」和「后端在线但没开始播」
   * 这两种完全不同的局面在账上长得一模一样，而后者是需要人去查的。
   * 少一个红没关系，把两种局面混成同一条账才是问题。 */
  const naWhy = livePrecondition ? ''
    : `面板声明它自己打开了录制（data-deriv-default），说明没有实时帧在流；`
      + `页面此刻显示 conn=${conn}`
      + (conn === 'connected'
          ? '（后端已连上 ⇒ 是还没开始播/帧没到，不是环境缺失）'
          : '（后端确实没连上 ⇒ 这是环境不可验，不是产品缺陷）');

  // 选一条记录并播放。
  let recId = null;
  if (livePrecondition) {
    recId = await pickAndStart('/__think$/.test(o.value)');
    rec('F2 选中一条 think 记录', !!recId && BY_ID.has(recId), `id=${recId}`);
  } else {
    recNA('F2 选中一条 think 记录', naWhy);
    // 没有选择器时也要有 recId，否则下面 `BY_ID.get(recId).window` 会崩 ——
    // 崩掉的后果是 F3c 之后**七条**检查全部连带不跑，而汇总行只印一句
    // 「X 脚本崩了」。用面板当前展示的那条记录顶上。
    recId = panelLive.traj;
  }

  // 先证明帧真的在流，否则后面每一条都是空断言 —— 上一版就是死在这：
  // reset 之后没点 Run，latest 恒为 null，6 条连带全红，而页面是好的。
  //
  // ⚠ 没有实时流时**不要**在这里空等 24 秒再记 FAIL：等的是一个不会来的帧。
  //   那是 F2b 自己的前提不成立，记 FAIL 等于说「验过、不合格」。
  let moving = false, sp = null;
  if (livePrecondition) {
    sp = await setSpeedMax();
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
  } else {
    recNA('F2b 选记录并 Run 之后帧真的在流', naWhy);
  }

  let early = null;
  if (!livePrecondition) {
    recNA('F3 播放初期面板诚实说"在窗口外"，不画空链', naWhy);
    recNA('F3b 窗口外时一根柱子都没画', naWhy);
    // early 仍要读：它给 F3c 之前的诊断留一份当前状态，
    // 而且下面那句「不画空链」在这里仍然**可判**——只是对象换了：
    // 面板在自己挑的录制上，不许画出该步在产物里没有的层。
    early = await readPanel();
  } else {
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
  }

  /* ---------------------------------------------------------------- */
  // 拖步滑块直接定位到窗口内。
  //
  // 不用「等播放自己走到窗口」：实测 speed=4 下约 8 步/秒，1024 步的轨迹
  // 要 ~2 分钟，而 T 最短的轨迹只有 265 步。判据等两分钟只为看一张图，
  // 既慢又不稳定。第一版就是这么写的，F4 差临门一脚判红。
  //
  // 滑块是面板自己的控件，所以这条判据顺带证明了"任何一步都能直接看"。
  const traj = BY_ID.get(recId);
  // ⚠⚠ 旧写法直接 `traj.window`：recId 取不到时抛 TypeError，
  //   而它在 try 块里 ⇒ catch 收成一条「X 脚本崩了」，
  //   **F3c 之后七条检查一条都没跑**，汇总行却只印得出这一句。
  //   一个装置故障把七条判决一起吞掉，而读者看到的是「脚本崩了」不是「没验」。
  //   ⇒ 取不到就明说，并把这七条记成前置未建立。
  if (!traj) {
    recNA('F3c 步滑块存在且可拖到窗口内任一步', `产物里没有记录 ${recId}`);
    recNA('F4b 面板落地的这一步就是滑块指定的那一步（没读错步）', `产物里没有记录 ${recId}`);
    recNA('F5 每根柱子的 p_final、correct 与实际绘制高度都与 JSON 一致', `产物里没有记录 ${recId}`);
    recNA('F5b 面板自称的层数 == 产物层数', `产物里没有记录 ${recId}`);
    recNA('F6 首个说对的层与 JSON 的 first_layer_correct 一致', `产物里没有记录 ${recId}`);
    recNA('F6b 跨 8 步扫描：绿柱逐层等于 JSON 的 correct[]', `产物里没有记录 ${recId}`);
    recNA('F7 文案诚实标注这是 probe 而非 forward pass', `产物里没有记录 ${recId}`);
    recNA('F9 换记录后链条跟着换成新记录的数据', `产物里没有记录 ${recId}`);
    recNA('F9b 请求 reset 之后选的步，不会被后端 reset_ack 抹掉', `产物里没有记录 ${recId}`);
    throw new Error('__NA_ONLY__');   // 交给 finally 收尾，不再往下走
  }
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
  // F9b 钉死 reset 的 ack 不抹掉「请求之后才选的那一步」。
  //
  // 为什么必须单开一条：F9 走的是「换记录 → reset → start」，ack 落在选步的
  // 前面还是后面取决于网络往返的时序，**约 50% 概率**才红（实测）。判据间歇
  // 咬不住，就等于没有这条判据 —— 而这里恰恰有一个**确定**的构造：
  // ack 必须走一次 WebSocket 往返，所以只要**同一拍**里「点 reset + 选步」，
  // ack 就**必然**落在选步之后。
  //
  // 这也是读者会做的事：按下 reset 之后顺手拖一下步滑块。
  // 修之前的实测症状：设的时候成功（afterSet="994"），几百毫秒后滑块被抹回
  // 窗口起点（sliderValue="992"），面板 state 退回 out-of-window、bars=0。
  //
  // ⚠ 不换记录：换了记录，组件里那条「选步在新窗口外就清掉」的 effect 也会
  //   参与结果，那就不是「只有 ack 能清它」了。留在同一条记录上，
  //   唯一能抹掉这个选步的就是 ack。
  const f9bWant = win[0] + 5;
  const f9bSet = await page.eval(`(() => {
    const rst = [...document.querySelectorAll('button')]
      .find(b => /reset/i.test(b.textContent || ''));
    const r = document.querySelector('[data-deriv-step]');
    if (!rst || !r) return { err: 'missing reset or slider' };
    rst.click();                               // 请求 reset：ack 要走一次往返
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, 'value').set;
    setter.call(r, ${f9bWant});                // 同一拍选步 —— ack 必然在它之后
    r.dispatchEvent(new Event('input', { bubbles: true }));
    r.dispatchEvent(new Event('change', { bubbles: true }));
    return { setNow: r.value, min: r.min, max: r.max, want: ${f9bWant} };
  })()`);
  await sleep(2500);                           // 足够 ack 往返落地
  const f9bAfter = await page.eval(`(() => {
    const r = document.querySelector('[data-deriv-step]');
    const el = document.querySelector('[data-derivation]');
    return { sliderValue: r ? r.value : null,
             state: el ? el.getAttribute('data-derivation') : null,
             stepId: el ? el.getAttribute('data-step-id') : null };
  })()`);
  rec('F9b 请求 reset 之后选的步，不会被后端 reset_ack 抹掉',
      String(f9bAfter.sliderValue) === String(f9bWant) && f9bAfter.state === 'ready',
      `set=${JSON.stringify(f9bSet)} after=${JSON.stringify(f9bAfter)} want=${f9bWant}`);

  /* ---------------------------------------------------------------- */
  // 换记录：链必须换成新记录的数据。
  // 这一条专门防"链画的是上一条记录" —— 那种错在存在性判据下 100% 绿。
  const other = LENS.trajectories.find(
    (t) => t.id !== recId && t.mode === 'think' && t.window[0] === win[0]);
  // ⚠ 必须连 pickerPresent 一起判：旧写法只看 `other`，找不到选择器时
  //   pickAndStart() 里的 `[...x.options]` 会在 undefined 上抛 TypeError，
  //   整段被 catch 收成「X 脚本崩了」—— 一条装置故障盖掉 F9 的真实判决。
  if (other && pickerPresent) {
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
    //
    const winWait0 = Date.now();
    const winMoved = await (async () => {
      for (let i = 0; i < 20; i++) {
        await sleep(500);
        const p = await readPanel();
        if (p.win && p.win[0] === other.window[0]
            && p.win[1] === other.window[1]) return true;
      }
      return false;
    })();
    // ⚠ 实测（2026-10-07，两次各 502ms 就中）：**等待从来不是 F9 的瓶颈** ——
    //   预算从 10s 提到 30s 是**没证据的改动**，已撤回。红在后面的滑块/取样那几步。
    console.log('   · F9 等面板换窗口：等了 %dms／预算 10000ms%s',
                Date.now() - winWait0, winMoved ? '' : ' ⇒ 没等到');
    const winWaitMs = Date.now() - winWait0;
    console.log('   · F9 等面板换窗口：等了 %dms（预算 30000ms）%s',
                winWaitMs, winMoved ? '' : ' ⇒ 没等到');

    // ⚠⚠⚠ 设滑块**必须验是否真的生效**，没生效就重设。
    //   2026-10-07 抓到实锤：`set.afterSet="994"`（设置当时成功了），
    //   而几百毫秒后 `after.sliderValue="992"` —— 被 React 的 reset() 抹回窗口起点，
    //   于是 state=out-of-window、bars=0，F9 转红。
    //   原因就是本段上面注释预言的那条竞态：`pickAndStart` 是
    //   「换记录 → reset → start」同步连发，reset 的 `focusedStep: null`
    //   **可能晚于**我们等 winMoved 落地 —— winMoved 只证明 currentTrajectory
    //   换了，**证明不了 reset 已经落地**。
    //   ⇒ 不加大等待预算（实测等窗口只要 502ms，不是瓶颈），
    //     改成「设 → 读回 → 不对就再设」，最多 6 轮。
    const want = otherT;
    let setRes = null, appliedAt = -1, attempts = 0;
    for (let a = 0; a < 6; a++) {
      attempts = a + 1;
      setRes = await page.eval(`(() => {
        const r = document.querySelector('[data-deriv-step]');
        if (!r) return { err: 'no slider' };
        const setter = Object.getOwnPropertyDescriptor(
          window.HTMLInputElement.prototype, 'value').set;
        setter.call(r, ${want});
        const afterSet = r.value;      // 浏览器会按 min/max 夹取
        r.dispatchEvent(new Event('input', { bubbles: true }));
        r.dispatchEvent(new Event('change', { bubbles: true }));
        return { min: r.min, max: r.max, want: ${want}, afterSet };
      })()`);
      await sleep(700);
      const back = await page.eval(
        `(() => { const r = document.querySelector('[data-deriv-step]');`
        + ` return r ? r.value : null; })()`);
      if (String(back) === String(want)) { appliedAt = a; break; }
    }

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
            + `sliderSetAttempts=${attempts} 第${appliedAt+1}轮读回=${appliedAt>=0 ? '生效' : '仍被重置'} `
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
  } else if (!pickerPresent) {
    // 「换记录」这个动作本身要有一个选择器才能做。没有选择器时
    // 旧写法记 FAIL，而 FAIL 说的是「验过、不合格」——它一次都没验。
    // 更糟的是它会把「没有选择器」误报成「没有可对照的记录」。
    recNA('F9 换记录后链条跟着换成新记录的数据',
      '没有录制选择器（后端不在），这个动作做不了；'
      + '注意这与「产物里没有对照记录」是两回事，不要混');
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
    // ⚠ 没有选择器 ⇒ 「切记录」这个动作做不了 ⇒ 后面那串
    //   `[...x.options]` 会在 undefined 上抛 TypeError，整段被 catch 收成
    //   「X 脚本崩了」。那不是判决，是装置在半路摔了一跤。
    if (!pickerPresent) {
      recNA('F11 切记录时清掉上一条记录的步号（不经 reset）',
        '没有录制选择器（后端不在），切记录这个动作做不了');
    } else if (!B) {
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
    if (!pickerPresent) {
      recNA('F12 窗口重叠时保留在新记录里仍合法的步号',
        '没有录制选择器（后端不在），切记录这个动作做不了');
    } else if (!B2) {
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
  // `__NA_ONLY__` 是上面那条「产物里没有这条记录」的**主动退出**，
  // 不是装置故障 —— 它已经把该记的 NA 都记完了。
  if (String((e && e.message) || e) !== '__NA_ONLY__')
    rec('X 脚本崩了', false, String((e && e.stack) || e).slice(0, 300));
} finally {
  cdp.close(); proc.kill('SIGKILL');
}

const pass = R.filter((x) => x.p).length;
const red = R.length - pass;
console.log('');
R.filter((x) => !x.p).forEach((x) => console.log('FAIL: ' + x.n));
if (NA.length) {
  console.log(`前置未建立 ${NA.length} 条（不是红，也不是绿 —— 它们一次都没验）：`);
  NA.forEach((n) => console.log('  NA: ' + n));
}
/* ⚠ 汇总行必须同时说清三件事，run_chain 只认 N/M 与 RESULT <状态>。
 *   状态取 NOT-ESTABLISHED 的条件是「一条都没验过」——
 *   判据全 NA 报成 OK，比全红更坏：它会让门禁在一块根本没跑的东西上变绿。 */
const status = red > 0 ? 'FAIL' : (pass === 0 && NA.length > 0 ? 'NOT-ESTABLISHED' : 'PASS');
console.log(`RESULT ${status} ${pass}/${R.length}`);
process.exit(red > 0 ? 1 : 0);
