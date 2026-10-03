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
const ROLES = JSON.parse(readFileSync(DATA + '/vector_roles.json', 'utf8'));
const AP = JSON.parse(readFileSync(DATA + '/answer_power.json', 'utf8'));
const REG = JSON.parse(readFileSync(VECD + '/steering_vectors.json', 'utf8'));
// 真值来源：注册表里每条 derived_from 记一次"这个方向是另一个取反来的"。
// 页面说几对，必须和这里数出来的一样。
const derived = Object.entries(REG).filter(([, v]) => v.derived_from).map(([k]) => k);
const npairs = derived.length;
const unpairedCos = Object.values(RC.unpaired_cosine)[0].cosine;
// ⚠⚠ 第二十六笔：这三行原来也是手抄的 ——
//   const INJECT_LAYER = '20';
//   const LAYERS = ['12', '14', '16', '20', '24'];
// 写死它们的**双重**代价：产物换一层，判据与产品**两边一起错**，
// 于是「产品说 L16、产物说 L20」这种错，在这个文件里**核不出来** ——
// 判据自己就假绿。第十三轮修 AXES 时是这个形状，LAYERS/INJECT_LAYER 被漏了。
// ⇒ 判据与产品必须从**同一个字段**派生，且下面 S9/S13 会核「页面那一份也等于它」。
const INJECT_LAYER = String(ROLES.layers.journal_injection);
const EXTRACT_LAYER = String(ROLES.layers.native_extraction);
const LAYERS = RC.layers.map(String);

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
    mounted = await page.eval(`!!document.querySelector('[data-structure]')`);
    if (mounted) break;
    await sleep(1200);
  }
  rec('S0 结构面板已挂载', mounted, mounted ? '' : '等了 ~18s');

  // ⚠⚠ 第二十六笔 C2b：下面这段采集的说明**原来写在 page.eval 的模板串内部** ——
  //   那里 `//` 不是注释，是要发给浏览器 eval 的字符串。
  //   页面侧不会坏（每条只注释自己那一行），坏在扫描器：
  //   `markers_in()` 刻意「保留字符串字面量内容」，于是注释里的
  //   data-drawn / data-rnd-line 会被当成**真的读取引用**。
  //   今天无害（那几个标记页面上都有），可一旦页面删掉其中一个，
  //   C2 就会报一个由注释制造的假死引用 ⇒ 注释必须写在真正的注释位置。
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
        lnBox: ln ? (() => { const b = ln.getBoundingClientRect();
          return { w: b.width, h: b.height, left: b.left, right: b.right }; })() : null,
        peaks: [...el.querySelectorAll('[data-peak]')].map(s => ({
          dir: s.getAttribute('data-peak-dir'),
          l: s.getAttribute('data-peak'),
          f: parseFloat(s.getAttribute('data-peak-frac')),
          // 每一行都要报出它用的提取层。缺这个属性时下面 S13 无法区分
          // 「页面用了别的层」与「页面根本没接这个字段」。
          x: s.getAttribute('data-extract-layer'),
          t: (s.textContent || '').trim() })),
        // 散文里那个「N of the M peak at LK」——第二十六笔新增的现算断言。
        peakAtExtract: el.querySelector('[data-peak-at-extract]')
          ? parseInt(el.querySelector('[data-peak-at-extract]').getAttribute('data-peak-at-extract'), 10) : null,
        nDirs: el.querySelector('[data-n-dirs]')
          ? parseInt(el.querySelector('[data-n-dirs]').getAttribute('data-n-dirs'), 10) : null,
        extractLayer: el.querySelector('[data-peak-at-extract]')
          ? el.querySelector('[data-peak-at-extract]').getAttribute('data-extract-layer') : null,
        // ⚠⚠ 第二十六笔变异台加的：页面**实际扫了哪几层**。
        //   只核答案（峰值层）有个盲区：把层名单从 5 层截断成前 2 层，
        //   六个方向的 argmax **一个都不变**（L14 在 L12/L14 里恒为最大）
        //   ⇒ 页面输出逐字相同，核 peak 的判据全绿。
        //   ⇒ 判据必须落在**输入**上：扫的层数/层名 == 产物的 layers。
        layersScanned: (() => {
          const s = el.querySelector('[data-layers-scanned]');
          const raw = s ? s.getAttribute('data-layers-scanned') : null;
          return raw === null || raw === '' ? null : raw.split(',');
        })(),
        // 第二十四笔那个「净变化 = 0」的**第二份副本**。属性值为空串表示
        // 「产物没到」—— 与「实测就是 0」必须能区分开。
        netChange: (() => {
          const n = el.querySelector('[data-net-change]');
          if (!n) return null;
          const v = n.getAttribute('data-net-change');
          return v === '' ? 'unavailable' : Number(v);
        })(),
      };
    })()`);
    if (st.state === 'ready') break;
  }
  rec('S1 面板加载完成', st.state === 'ready', `state=${st.state}`);

  /* ---------------------------------------------------------------- */
  // 第 2 层：每根柱子的数值与产物逐值相同。
  const want = RC.per_layer[INJECT_LAYER].real;
  // ⚠ 第二十六笔：这里原来写死 `st.bars.length === 6` 与 `wantDistinct = 6 - npairs`。
  //   产物若换一组方向（条数变了），判据与产品会一起按 6 算而双双对不上，
  //   但因为两边都写死，**判据自己不会红** —— 它会拿 6 去要求一个 5 根柱的页面。
  const nDirsWant = Object.keys(want).length;
  const bad = st.bars.filter(b => !(b.dir in want) || b.frac !== want[b.dir]);
  rec('S2 柱子的 subspace_frac 与产物 JSON 逐值相同（条数也由产物定）',
      st.bars.length === nDirsWant && bad.length === 0,
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
  const wantDistinct = nDirsWant - npairs;
  rec('S3 柱宽与 subspace_frac 成比例、顺序一致、重复数等于翻转对数',
      drawnOk && ordered && nDistinct === wantDistinct,
      `distinct widths=${nDistinct} 期望=${wantDistinct}（${nDirsWant} 根柱 - ${npairs} 对翻转）  ` +
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
      // ⚠ 第二十六笔：原来这两条正则写的是英文**词** —— /two of the six are
      //   sign flips/ 与 /four vectors/。页面上那两句散文原来也是手抄的
      //   「Two of the six」「The six labels are four vectors」，于是判据与产品
      //   共用同一份手抄：产品把 four 改成 five，判据**跟着一起要 five**，
      //   核不出来。现在页面改成现算，判据就核那个**算出来的数**，
      //   散文措辞只用来确认那段话真的印出来了。
      && st.text.includes(`${npairs} of the ${nDirsWant} are sign flips`)
      && st.text.includes(`The ${nDirsWant} labels are ${nDirsWant - npairs} vectors`)
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
  // ⚠⚠ 第二十六笔：原来这里要求 `every(v => v === '14')` —— 把「六个方向全部
  //   峰在 L14」当成**判据**。可那是一条**经验断言**，不是不变式：
  //   产物若换成一组峰层分散的方向，产品会如实印「5 of the 6」而**完全正确**，
  //   这条判据却会转红 ⇒ 一个只在数据变了时才正确、平时恒绿的判据，
  //   等于把「数据必须长成今天这样」写成红线（永远红的判据会被直接关掉）。
  // 现在页把那一句改成**现算的计数**，判据核的是「这个计数 == 产物算出来的计数」。
  const wantPeakAtExtract = Object.values(peakWant)
    .filter(v => v === EXTRACT_LAYER).length;
  // 每行的「← extracted here」标记必须与该行自己的峰值层一致
  // （原来它判的是写死的 "14"，产物换层就静默全灭）。
  const markBad = st.peaks.filter(p => {
    const marked = /←\s*extracted here/.test(p.t);
    return marked !== (p.l === p.x);
  });
  const extractBad = st.peaks.filter(p => p.x !== EXTRACT_LAYER);
  rec('S9 每个方向的峰值层与产物逐值一致，且「extracted here」标记逐行自洽',
      st.peaks.length === nDirsWant && peakBad.length === 0
      && noDir.length === 0 && markBad.length === 0 && extractBad.length === 0,
      // ⚠⚠ 第二十六笔：这一行原来写成三段嵌套三元，只报**第一个**非零的原因。
      //   变异台一次改三处时，提取层错会盖住「峰值层也算错」这个独立信号 ——
      //   判据红了，可诊断行指向的病因只覆盖了一半，另一半没被看见。
      // ⇒ 四个计数**一起报**（同族：「收集齐再报」，不是遇到第一条就中止）。
      `峰值层与产物不符 ${peakBad.length} 行；无 data-peak-dir ${noDir.length} 行；`
      + `标记与自身峰值层不符 ${markBad.length} 行；提取层号 != 产物 ${extractBad.length} 行`
      + `　| 产物 ${JSON.stringify(peakWant)}`
      + `　| 页面 ${st.peaks.map(p => `${p.dir}=L${p.l}/x${p.x}`).join(' ')}`
      + `　| 提取层 ${EXTRACT_LAYER}，其中 ${wantPeakAtExtract} 个峰在该层`);

  /* ---------------------------------------------------------------- */
  // 第二十六笔：散文里「N of the M peak at LK」必须是**现算的**，
  // 且 K 必须等于 vector_roles.json 的 native_extraction（不是写死的 14）。
  // 判它「是现算的」而不是「恰好为真」的方式：核 N 与 M 各自等于产物算出的值。
  // 只核 N === 6 是不够的 —— 那个 6 正是本条要防的手抄。
  rec('S15 散文的「N of the M peak at LK」现算自产物（K 取自 vector_roles）',
      st.peakAtExtract === wantPeakAtExtract
      && st.nDirs === nDirsWant
      && st.extractLayer === EXTRACT_LAYER
      && st.text.includes(`${wantPeakAtExtract} of the ${nDirsWant} peak at L${EXTRACT_LAYER}`),
      `产物算出 ${wantPeakAtExtract}/${nDirsWant} 峰在 L${EXTRACT_LAYER}`
      + `（roles.native_extraction=${ROLES.layers.native_extraction}）  `
      + `页面 data-peak-at-extract=${st.peakAtExtract} data-n-dirs=${st.nDirs}`
      + ` data-extract-layer=${st.extractLayer}`);

  // 「← extracted here」不能是判据自己的层号：逐行 x 必须都是产物那个。
  rec('S16 注入层取自 vector_roles.journal_injection（页面 top3var 也核在这一层）',
      st.text.includes(`at L${INJECT_LAYER}, which holds only`)
      && st.top3var === RC.top3_variance_frac[INJECT_LAYER],
      `roles.journal_injection=${ROLES.layers.journal_injection}  页面散文中出现 "at L${INJECT_LAYER},"`
      + `  data-top3var=${st.top3var}  产物=${RC.top3_variance_frac[INJECT_LAYER]}`);

  // ⚠⚠ 这一条判的是**输入**（扫了哪几层），不是答案（峰值层）。
  //   变异台的教训：把层名单截断成前 2 层，六个方向的 argmax 一个都不变
  //   （L14 恒大于 L12），页面输出**逐字相同** ⇒ 核 peak 的判据全绿。
  //   「名单被截断」这件事在输出不变时**没有任何其他判据看得见**。
  //   逐项比而不是只比个数：只比个数的话，截断成
  //   ['12','14','16','20','24','99'] 这种也躲得过。
  rec('S18 页面实际扫过的层名单逐项等于产物 layers（判输入，不只判答案）',
      Array.isArray(st.layersScanned)
      && st.layersScanned.length === LAYERS.length
      && st.layersScanned.every((L, i) => L === LAYERS[i]),
      `产物 layers=[${LAYERS.join(',')}]  页面 data-layers-scanned=`
      + `[${Array.isArray(st.layersScanned) ? st.layersScanned.join(',') : st.layersScanned}]`
      + `　（层数 ${Array.isArray(st.layersScanned) ? st.layersScanned.length : '—'} / ${LAYERS.length}）`);

  // 第二十四笔那个「净变化是 0」的**第二份副本**：这里印的必须是
  // answer_power.json 的 net_change，且「没取到」与「实测为 0」必须可区分。
  rec('S17 「净变化」这份副本接的是 answer_power.net_change（未取到不许印 0）',
      st.netChange === AP.net_change
      && st.text.includes(AP.net_change > 0 ? `+${AP.net_change}` : `${AP.net_change}`)
      && st.text.includes(`over ${AP.n_complete_pairs} complete pairs`),
      `产物 net_change=${AP.net_change}（${AP.n_complete_pairs} 个完整配对）  `
      + `页面 data-net-change=${JSON.stringify(st.netChange)}`);

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
