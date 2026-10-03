// 验收：3D 页面上的「方向是不是随机的」面板（Are these directions arbitrary?）。
//
// 这块面板回答的是审稿人第一个会问的问题：steering vector 那个漂亮的
// 效应，会不会只是随便一个方向恰好相关。做法是把每个方向投影到
// 「模型自己 hidden states 走过的 top-3 主子空间」上，看它落进去多少，
// 再和 200 个定长随机方向的**分布**比 —— 不是和一个随机值比。
//
// 判据盯四层真值，一层比一层不靠页面自证：
//  1. 挂载 / 加载完成
//  2. 每根柱子的 data-frac 与产物 JSON 逐值相同
//  3. **画出来的宽度**与 data-frac 成比例（D1 教训：只读数据属性，
//     把宽度改成常数，判据会全绿，而读者看到的是一排等长柱）
//  4. 「几对反向向量」这句话与 .npy 真值一致 —— 这里真值是 cos = -1.0，
//     页面曾经写「三对」，而注册表里只有两对
import { launch, Page, CDP } from './cdp_client.mjs';
import { readFileSync } from 'node:fs';

const URL = process.env.T3D_URL || 'http://127.0.0.1:9994/';
const PROFILE = process.env.T3D_PROFILE
  || '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_struct_' + process.pid;
const DATA = '/Users/zhourui/code/steer3d/frontend/public/latent/data';
const VECD = '/Users/zhourui/code/steer3d/backend/examples/output/steering_vectors';

const RC = JSON.parse(readFileSync(DATA + '/vector_random_control.json', 'utf8'));
const REG = JSON.parse(readFileSync(VECD + '/steering_vectors.json', 'utf8'));
// 真值来源：注册表里每条 derived_from 记一次"这个方向是另一个取反来的"。
// 页面说几对，必须和这里数出来的一样。
const derived = Object.entries(REG).filter(([, v]) => v.derived_from).map(([k]) => k);
const npairs = derived.length;
const unpairedCos = Object.values(RC.unpaired_cosine)[0].cosine;
const INJECT_LAYER = '20';
const LAYERS = ['12', '14', '16', '20', '24'];

const sleep = ms => new Promise(r => setTimeout(r, ms));
const R = [];
const rec = (n, p, d) => {
  R.push({ n, p });
  console.log(`[${p ? 'PASS' : 'FAIL'}] ${n}\n       ${d}`);
};

const { proc, version } = await launch({ port: 9462, userDataDir: PROFILE,
  windowSize: '1600,1000', url: 'about:blank' });
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);

try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});

  let mounted = false;
  for (let i = 0; i < 15; i++) {
    mounted = await page.eval(`!!document.querySelector('[data-structure]')`);
    if (mounted) break;
    await sleep(1200);
  }
  rec('S0 结构面板已挂载', mounted, mounted ? '' : '等了 ~18s');

  let st = null;
  for (let i = 0; i < 15; i++) {
    await sleep(1000);
    st = await page.eval(`(() => {
      const el = document.querySelector('[data-structure]');
      if (!el) return { state: 'absent' };
      const bars = [...el.querySelectorAll('[data-dir]')].map(r => ({
        dir: r.getAttribute('data-dir'),
        frac: parseFloat(r.getAttribute('data-frac')),
        drawn: parseFloat(r.getAttribute('data-drawn')),
        top: parseFloat(r.getAttribute('data-top')),
        flip: r.getAttribute('data-flip') || '',
        // 真·渲染出来的几何：getBoundingClientRect 与 data-drawn 必须一致，
        // 否则 data-drawn 自己就是个谎。
        rectW: r.getBoundingClientRect().width,
        rectH: r.getBoundingClientRect().height,
      }));
      const ln = el.querySelector('[data-rnd-line]');
      return {
        state: el.getAttribute('data-structure'),
        text: (el.innerText || '').replace(/\\s+/g, ' '),
        bars,
        top3var: parseFloat(el.querySelector('[data-top3var]')?.getAttribute('data-top3var')),
        ratio: parseFloat(el.querySelector('[data-ratio]')?.getAttribute('data-ratio')),
        rnd: ln ? parseFloat(ln.getAttribute('data-rnd')) : null,
        rndX: ln ? parseFloat(ln.getAttribute('data-rnd-line')) : null,
        // 表头里的对照数量。写死 200 而产物改了 n_random，页面会继续说
        // "200 random controls" —— 分母错了，整段结论的分母就错了。
        nRandomHdr: el.querySelector('[data-n-random]')?.getAttribute('data-n-random') ?? null,
        // 线的**实际绘制几何**。只读 data-rnd-line 不够：V2 那条变异
        // 只把 x1/x2 换成满宽、属性原封不动，于是读属性的判据全绿，
        // 而屏幕上是一条横贯全图的线 —— 正好与事实相反。
        // 竖线的包围盒宽≈0；横线宽≈整条绘图区。
        lnBox: ln ? (() => { const b = ln.getBoundingClientRect();
          return { w: b.width, h: b.height, left: b.left, right: b.right }; })() : null,
        peaks: [...el.querySelectorAll('[data-peak]')].map(s => ({
          dir: s.getAttribute('data-peak-dir'),
          l: s.getAttribute('data-peak'),
          f: parseFloat(s.getAttribute('data-peak-frac')),
          t: (s.textContent || '').trim() })),
      };
    })()`);
    if (st.state === 'ready') break;
  }
  rec('S1 面板加载完成', st.state === 'ready', `state=${st.state}`);

  /* ---------------------------------------------------------------- */
  // 第 2 层：每根柱子的数值与产物逐值相同。
  const want = RC.per_layer[INJECT_LAYER].real;
  const bad = st.bars.filter(b => !(b.dir in want) || b.frac !== want[b.dir]);
  rec('S2 六根柱子的 subspace_frac 与产物 JSON 逐值相同',
      st.bars.length === 6 && bad.length === 0,
      bad.length ? JSON.stringify(bad)
                 : `n=${st.bars.length} ` +
                   st.bars.map(b => `${b.dir}=${b.frac}`).join(' '));

  /* ---------------------------------------------------------------- */
  // 第 3 层：画出来的宽度必须与数值成比例。
  // 这一层是专门为「宽度被换成常数」那种变异准备的。只断言 data-frac
  // 的话，那条变异会全绿 —— 而页面上是一排等长柱。
  const BAR_X = 92, BAR_W = 340 - 96;
  const drawnOk = st.bars.every(b => {
    const wantW = (b.frac / b.top) * BAR_W;
    return Math.abs(b.drawn - wantW) < 0.06 && b.drawn > 0;
  });
  // 排序一致性：frac 大的必须画得更宽。一排等长柱（"宽度换成常数"
  // 那条变异）在这里和 drawnOk 一样会红，但两条红的原因不同 ——
  // drawnOk 抓比例错，这一条抓顺序错。
  const byFrac = [...st.bars].sort((a, b) => a.frac - b.frac).map(b => b.drawn);
  const ordered = byFrac.every((w, i) => i === 0 || w >= byFrac[i - 1] - 1e-9);
  // 不同宽度的个数不是任意的：每有一条 derived_from 翻转记录，
  // 就会有两根柱子取值相同。所以期望值 = 6 - 对数，从注册表数出来，
  // 不是拍脑袋写 5。第一版这里写死 >=5，和 S8「翻转对完全相同」
  // 自相矛盾（6 根柱里必然有 2 根重复），判的是我的想当然。
  const nDistinct = new Set(st.bars.map(b => b.drawn)).size;
  const wantDistinct = 6 - npairs;
  rec('S3 柱宽与 subspace_frac 成比例、顺序一致、重复数等于翻转对数',
      drawnOk && ordered && nDistinct === wantDistinct,
      `distinct widths=${nDistinct} 期望=${wantDistinct}（6 根柱 - ${npairs} 对翻转）  ` +
      st.bars.map(b => `${b.dir}:${b.frac}->${b.drawn}px`).join('  '));

  // data-drawn 也不能自己撒谎：它必须等于浏览器真正画出来的宽度。
  // 两者单位都是 px，viewBox 缩放会同时作用，所以比值应当为 1。
  const scale = st.bars.length ? st.bars[0].rectW / st.bars[0].drawn : 0;
  const geomOk = st.bars.every(b => Math.abs(b.rectW / scale - b.drawn) < 0.06)
                 && scale > 0 && Number.isFinite(scale);
  rec('S4 data-drawn 与浏览器实测 rect 宽度一致（缩放一致）',
      geomOk, `viewBox scale=${scale.toFixed(4)}  ` +
      st.bars.map(b => `${b.dir}:${b.rectW.toFixed(2)}px`).join('  '));

  /* ---------------------------------------------------------------- */
  // 随机上限线的位置：它必须落在**它自己的数值**上，而不是画到最右边。
  // 画满宽是个会误导读者的错误 —— 看起来像「所有方向都只刚过随机」。
  //
  // 三重断言，缺一不可：
  //   (a) 属性 data-rnd / data-rnd-line 仍与产物一致（防止"改属性不改图"
  //       或反过来）
  //   (b) **浏览器实测的包围盒是竖的**（宽≈0）—— V2 变异只改 x1/x2，
  //       属性原封不动，只有这一条能抓住它
  //   (c) 实测左边缘落在期望 x 上（把 SVG 缩放算进去）
  const rnd = RC.per_layer[INJECT_LAYER].random_max;
  const wantRndX = BAR_X + (rnd / st.bars[0].top) * BAR_W;
  const box = st.lnBox;
  const svg = await page.eval(`(() => {
    const ln = document.querySelector('[data-rnd-line]');
    if (!ln) return null;
    const svg = ln.ownerSVGElement;
    const m = svg.getScreenCTM();
    const b = ln.getBoundingClientRect();
    const sx = svg.getBoundingClientRect();
    return { scale: m ? m.a : 1, svgLeft: sx.left, svgTop: sx.top,
             lineLeft: b.left, lineW: b.width, lineH: b.height };
  })()`);
  const wantLeftScreen = svg ? svg.svgLeft + wantRndX * svg.scale : NaN;
  rec('S5 随机上限线画成**竖线**且落在它自己的数值上（量浏览器实测几何）',
      st.rnd === rnd && st.rndX != null
      && Math.abs(st.rndX - wantRndX) < 0.06
      && box && box.w < 3 && box.h > 20
      && svg && Math.abs(box.left - wantLeftScreen) < 1.5,
      `属性 x=${st.rndX}（期望 ${wantRndX.toFixed(2)}）  ` +
      `实测包围盒 ${box ? box.w.toFixed(1) + '×' + box.h.toFixed(1) + 'px' : 'null'}  ` +
      `实测左缘 ${box ? box.left.toFixed(1) : '?'} vs 期望 ${wantLeftScreen.toFixed(1)}  ` +
      `viewBox 缩放 ${svg ? svg.scale.toFixed(4) : '?'}`);

  /* ---------------------------------------------------------------- */
  // 第 4 层：页面自称「几对反向向量」必须与 .npy 真值一致。
  // 这里不用 JSON 自证 —— JSON 是我们自己生成的。真的判据是从
  // steering_vectors.json 的 derived_from 字段数出对数，再用 .npy
  // 逐对验余弦是不是 -1。
  rec('S6 页面对「反向向量对数」的说法与注册表 + .npy 真值一致',
      npairs === 2
      && /two of the six are sign flips/i.test(st.text)
      && /four vectors/i.test(st.text)
      && !/three (opposite |sign-?flipped )?pairs?/i.test(st.text),
      `steering_vectors.json 里 derived_from 记了 ${npairs} 条翻转 ` +
      `(${derived.join(', ')})；caution·creativity cos=${unpairedCos.toFixed(4)} 不是反向`);

  // .npy 逐对复核：cos 必须真的是 -1，而不是"页面说是"。
  {
    const { execFileSync } = await import('node:child_process');
    const py = `
import json,numpy as np
d=${JSON.stringify(VECD)}
reg=json.load(open(d+'/steering_vectors.json'))
out={}
for k,v in reg.items():
    if 'derived_from' in v:
        a=np.load(d+'/'+k+'.npy').astype(np.float64)
        b=np.load(d+'/'+v['derived_from']+'.npy').astype(np.float64)
        out[k+'|'+v['derived_from']]=float(a@b/(np.linalg.norm(a)*np.linalg.norm(b)))
print(json.dumps(out))
`;
    const raw = execFileSync('python3', ['-c', py], { encoding: 'utf8' });
    const cos = JSON.parse(raw);
    const allFlip = Object.values(cos).every(c => Math.abs(c + 1) < 1e-9);
    rec('S7 .npy 逐对复核：每条 derived_from 的余弦确为 -1',
        Object.keys(cos).length === npairs && allFlip,
        Object.entries(cos).map(([k, c]) => `${k} cos=${c}`).join('  '));
  }

  // 页面上成对的两根柱，data-frac 必须完全相同（投影长度不看符号）。
  const flipBars = st.bars.filter(b => b.flip);
  const byDir = Object.fromEntries(st.bars.map(b => [b.dir, b.frac]));
  const flipEq = flipBars.every(b => byDir[b.flip] === b.frac);
  rec('S8 标为翻转的柱子与其本体 data-frac 完全相同',
      flipBars.length === 2 && flipEq,
      flipBars.map(b => `${b.dir}=${b.frac} vs ${b.flip}=${byDir[b.flip]}`).join('  '));

  /* ---------------------------------------------------------------- */
  // 峰层：六个方向是否都在 L14（定义层）。
  const peakWant = {};
  for (const n of Object.keys(want)) {
    const vals = LAYERS.map(L => RC.per_layer[L].real[n]);
    peakWant[n] = LAYERS[vals.indexOf(Math.max(...vals))];
  }
  // ⚠ 这里原来写着 `st.peaks.filter(p => p.l !== peakWant[p.dir] && false)`
  //   —— `X && false` 恒为 false，于是 peakBad **永远是空数组**，可判据名却写着
  //   「且与产物一致」。我以为它只是死代码、去掉不影响结论 —— **错了**：
  //   去掉之后 S9 立刻转红，原因是探针与组件**都没有这个方向的身份**
  //   （组件只发 data-peak / data-peak-frac，探针也只取 l/f/t），
  //   于是 `peakWant[p.dir]` 恒为 undefined，六行全被判成「不一致」。
  //   ⇒ 那行 `&& false` 掩盖的是一条**结构上就跑不了的检查**，
  //   而「判据恒绿」与「判据根本没法跑」在自报里长得一模一样。
  //   两处都补：组件发 data-peak-dir，探针取 dir，并显式要求 dir 齐全 ——
  //   缺 dir 时必须判红，不能让它退化成「空集即通过」。
  const noDir = st.peaks.filter(p => !p.dir);
  const peakBad = noDir.length ? [] : st.peaks.filter(p => p.l !== peakWant[p.dir]);
  const allPeak14 = Object.values(peakWant).every(v => v === '14')
                   && st.peaks.length === 6
                   && st.peaks.every(p => p.l === '14');
  rec('S9 六个方向的峰值层都是 L14，且与产物一致',
      allPeak14 && peakBad.length === 0 && noDir.length === 0,
      noDir.length
        ? `❌ ${noDir.length} 个 [data-peak] 没有 data-peak-dir ⇒ 逐方向核对结构上跑不了`
          + `（空集会被当成「无不一致」）`
        : `产物算出 ${JSON.stringify(peakWant)}；页面 ${st.peaks.map(p => p.l).join(',')}`);

  /* ---------------------------------------------------------------- */
  // 页面上两个数据驱动的数字：top-3 方差占比、比值。
  rec('S10 页面上的 top-3 方差占比与产物一致',
      st.top3var === RC.top3_variance_frac[INJECT_LAYER]
      && st.text.includes((RC.top3_variance_frac[INJECT_LAYER] * 100).toFixed(1) + '%'),
      `产物 L${INJECT_LAYER} top3_var=${RC.top3_variance_frac[INJECT_LAYER]} ` +
      `页面 data-top3var=${st.top3var}`);

  rec('S11 页面上的「最大真实/随机上限」比值与产物一致',
      st.ratio === RC.per_layer[INJECT_LAYER].best_over_random_max
      && st.text.includes(RC.per_layer[INJECT_LAYER].best_over_random_max.toFixed(1) + '×'),
      `产物=${RC.per_layer[INJECT_LAYER].best_over_random_max} 页面=${st.ratio}`);

  /* ---------------------------------------------------------------- */
  // 红线：不能把「非随机」说成「语义正确」。
  rec('S12 面板明说这不能证明「结构就是 confidence 的含义」',
      /does not say/i.test(st.text) && /naming/i.test(st.text),
      String(st.text.match(/What this does[^]*/)?.[0] || '未见该声明').slice(0, 130));

  rec('S13 表头的随机对照数量与产物一致（分母不许写死）',
      Number(st.nRandomHdr) === RC.n_random
      && st.text.includes(`${RC.n_random} seeded random directions`),
      `产物 n_random=${RC.n_random}  页面表头=${st.nRandomHdr}`);

  const errs = page.events    .filter(e => e.method === 'Runtime.consoleAPICalled' && e.params.type === 'error')
    .map(e => (e.params.args || []).map(a => a.value ?? a.description ?? '').join(' '))
    .filter(t => !/favicon|Failed to load resource/i.test(t));
  rec("S14 页面无 console error", errs.length === 0,
      errs.length ? errs.slice(0, 2).join(' | ') : 'none');
} catch (e) {
  rec('X 脚本崩了', false, String((e && e.stack) || e).slice(0, 400));
} finally {
  cdp.close(); proc.kill('SIGKILL');
}

const pass = R.filter(x => x.p).length;
console.log(`\n=== ${pass}/${R.length} passed ===`);
R.filter(x => !x.p).forEach(x => console.log('FAIL: ' + x.n));
process.exit(pass === R.length ? 0 : 1);
