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
           head: (el.innerText || '').replace(/\\s+/g, ' ').slice(0, 200) };
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
    if (got.state === 'ready' && got.bars.length >= 28) {
      const m = String(got.text).match(/Step\s+(\d+)/);
      landedT = m ? Number(m[1]) : null;
      break;
    }
  }

  rec('F4 定位到窗口内步后面板画出 28 层链条',
      got.state === 'ready' && got.bars.length === 28,
      `state=${got.state} bars=${got.bars.length} t=${landedT} slider=${slid}`);

  /* ---------------------------------------------------------------- */
  // 核心：逐值比对。不比"有没有 28 根柱子"，比每一根的 p_final 和 correct。
  rec('F4b 面板落地的这一步就是滑块指定的那一步（没读错步）',
      landedT === targetT,
      `panel t=${landedT} slider=${slid} json has t=${targetT}: ${!!target}`);

  if (got.bars.length === 28 && target) {
    const pl = target.per_layer;
    const drawn = await readDrawn();
    const bad = [];
    for (let l = 0; l < 28; l++) {
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
        bad.length === 0 && drawn.length === 28,
        bad.length ? bad.slice(0, 4).join(' | ')
                   : `28/28 一致 (t=${target.t}, 高度也由 p_final 决定)`);

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
      if (p.state !== 'ready' || p.bars.length !== 28) {
        scanBad.push(`t=${st.t} state=${p.state} bars=${p.bars.length}`);
        continue;
      }
      scanSteps++;
      for (let l = 0; l < 28; l++) {
        if (p.bars[l].ok !== !!st.per_layer.correct[l]) {
          scanBad.push(`t=${st.t} L${l}`);
        }
      }
    }
    rec('F6b 跨 8 步扫描：绿柱逐层等于 JSON 的 correct[]',
        scanBad.length === 0 && scanSteps >= 6,
        scanBad.length ? scanBad.slice(0, 4).join(' | ')
                       : `${scanSteps} 步 × 28 层 = ${scanSteps * 28} 格全对`);

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
    await page.eval(`(() => {
      const r = document.querySelector('[data-deriv-step]');
      if (!r) return null;
      const setter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype, 'value').set;
      setter.call(r, ${otherT});
      r.dispatchEvent(new Event('input', { bubbles: true }));
      r.dispatchEvent(new Event('change', { bubbles: true }));
      return r.value;
    })()`);
    let sig = null, sigState = null, sigText = '';
    for (let i = 0; i < 12; i++) {
      await sleep(700);
      const p = await readPanel();
      sigState = p.state;
      sigText = String(p.head || '');
      if (p.state === 'ready' && p.bars.length >= 28) { sig = p; break; }
    }
    let ok = false;
    // 失败时把面板说的整段话打出来。只报 bars=0 分不清是"没进窗口"、
    // "JSON 没 join 上"还是"画错了"——三种修法完全不同。
    let why = `other=${other.id} state=${sigState} bars=${sig ? sig.bars.length : 0} | ${sigText.slice(0, 130)}`;
    if (sig && sig.bars.length === 28 && ot) {
      const bad = [];
      for (let l = 0; l < 28; l++) {
        if (Math.abs(sig.bars[l].p - ot.per_layer.p_final[l]) > 1e-6) bad.push(`L${l}`);
      }
      ok = bad.length === 0;
      why = ok ? `28/28 匹配 ${other.id} t=${otherT}` : `不符层: ${bad.slice(0, 5).join(',')}`;
    } else if (!ot) {
      why += ` (JSON 里没有 t=${otherT})`;
    }
    rec('F9 换记录后链条跟着换成新记录的数据', ok, why);
  } else {
    rec('F9 换记录后链条跟着换成新记录的数据', false, '找不到对照记录');
  }

  const errs = page.events
    .filter(e => e.method === 'Runtime.consoleAPICalled' && e.params.type === 'error')
    .map(e => (e.params.args || []).map(a => a.value ?? a.description ?? '').join(' '))
    .filter(t => !/favicon|Failed to load resource/i.test(t));
  rec('F10 页面无 console error', errs.length === 0,
      errs.length ? errs.slice(0, 2).join(' | ') : 'none');
} catch (e) {
  rec('X 脚本崩了', false, String((e && e.stack) || e).slice(0, 300));
} finally {
  cdp.close(); proc.kill('SIGKILL');
}

const pass = R.filter((x) => x.p).length;
console.log(`\n=== ${pass}/${R.length} passed ===`);
R.filter((x) => !x.p).forEach((x) => console.log('FAIL: ' + x.n));
process.exit(pass === R.length ? 0 : 1);
