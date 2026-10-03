// 验收：3D 页面上的「强度定律」面板（Strength law）。
//
// 这块面板是整个 steering 故事里唯一一条**可迁移**的结论：注入造成的
// 几何失真 ≈ ½(s·rms/‖h‖)²，式子里没有方向。于是它给出一个可证伪的
// 推论 —— 随机方向应当落在同一条曲线上。
//
// 判据盯四件事：
//  1. 面板在，且数字与 linearity_law.json 逐值相同
//  2. **实测几何**（点的 y 位置、随机区间的长度）而不是只读 data 属性
//     —— 变异若只改几何不改属性，读属性的判据会全绿
//  3. 面板没有把「定律成立区间」偷偷缩到好看的范围：s=0.5 的失效点
//     必须在页面上
//  4. 红线：不得把「随机方向代价相同」包装成对向量的支持
import { launch, Page, CDP } from './cdp_client.mjs';
import { readFileSync } from 'node:fs';

const URL = process.env.T3D_URL || 'http://127.0.0.1:10021/';
const PROFILE = process.env.T3D_PROFILE
  || '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_law_' + process.pid;
const DATA = '/Users/zhourui/code/steer3d/frontend/public/latent/data';

const LAW = JSON.parse(readFileSync(DATA + '/linearity_law.json', 'utf8'));
// L12 要核的那句是**跨产物**声明：边界来自 linearity_law，
// 而 32k 批次的强度在 steer_directions 里。判据必须两边都读，
// 否则就是「判据与产品引用同一份东西」——等于没有独立参照。
const DIR = JSON.parse(readFileSync(DATA + '/steer_directions.json', 'utf8'));
const SHOW_LAYER = 20;

const sleep = ms => new Promise(r => setTimeout(r, ms));
const R = [];
const rec = (n, p, d) => {
  R.push({ n, p });
  console.log(`[${p ? 'PASS' : 'FAIL'}] ${n}\n       ${d}`);
};

const { proc, version } = await launch({ port: 9473, userDataDir: PROFILE,
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
    mounted = await page.eval(`!!document.querySelector('[data-law]')`);
    if (mounted) break;
    await sleep(1200);
  }
  rec('L0 强度定律面板已挂载', mounted, mounted ? '' : '等了 ~18s');

  let st = null;
  // ⚠⚠ 第二十六笔 C2b：下面 `g()` 的说明**原来写在 page.eval 的模板串内部** ——
  //   那里 `//` 不是注释，是要发给浏览器 eval 的字符串。页面侧不会坏
  //   （每条只注释自己那一行），坏在扫描器：`markers_in()` 刻意
  //   「保留字符串字面量内容」⇒ 注释里提到的 data-gap 会被当成真的读取引用。
  //   今天无害，可页面一旦删掉那个属性，C2 就会报一个由注释制造的假死引用。
  for (let i = 0; i < 15; i++) {
    await sleep(1000);
    st = await page.eval(`(() => {
      const el = document.querySelector('[data-law]');
      if (!el) return { state: 'absent' };
      const g = (sel, attrs) => {
        const n = el.querySelector(sel); if (!n) return null;
        const o = { text: (n.textContent || '').trim() };
        // attrs 传**完整**属性名。第一版传的是 'gap'/'spread'（短名），
        //   getAttribute 拿不到带前缀的属性，判据恒红而页面好好的。
        for (const a of attrs) o[a] = n.getAttribute(a);
        const b = n.getBoundingClientRect();
        o.cx = b.x + b.width / 2; o.cy = b.y + b.height / 2;
        o.w = b.width; o.h = b.height;
        return o;
      };
      return {
        state: el.getAttribute('data-law'),
        text: (el.innerText || '').replace(/\\s+/g, ' '),
        gap: g('[data-gap]', ['data-gap']),
        spread: g('[data-spread]', ['data-spread']),
        nRandom: g('[data-law-random]', ['data-law-random']),
        outOfDepth: g('[data-outofdepth-from]', ['data-outofdepth-from']),
        // L12 用：失效区那段里的「32k 批次强度」那句。
        // ⚠ 第一版我另起一次 page.eval 去取，返回 null 而元素其实在
        //   （探针已证明）⇒ 装置自己的问题。选择器要并进**这一次** eval。
        boundaryNote: (() => { const n = el.querySelector('[data-law-boundary-note]');
          return n ? (n.innerText || '').replace(/\\s+/g, ' ').trim() : null; })(),
        curve: (() => { const p = el.querySelector('[data-curve="analytic"]');
          if (!p) return null;
          const b = p.getBoundingClientRect();
          return { d: p.getAttribute('d'), w: b.width, h: b.height }; })(),
        named: [...el.querySelectorAll('[data-named]')].map(n => ({
          s: Number(n.getAttribute('data-named')),
          dev: Number(n.getAttribute('data-dev')),
          pred: Number(n.getAttribute('data-pred')),
          cy: n.getBoundingClientRect().y + n.getBoundingClientRect().height / 2,
        })),
        rnd: [...el.querySelectorAll('[data-rnd-span]')].map(n => ({
          s: Number(n.getAttribute('data-rnd-span')),
          lo: Number(n.getAttribute('data-rnd-lo')),
          hi: Number(n.getAttribute('data-rnd-hi')),
          h: n.getBoundingClientRect().height,
        })),
      };
    })()`);
    if (st.state === 'ready') break;
  }
  rec('L1 面板加载完成', st.state === 'ready', `state=${st.state}`);

  const rows = LAW.rows.filter(r => r.layer === SHOW_LAYER)
                        .sort((a, b) => a.strength - b.strength);

  /* ---------------------------------------------------------------- */
  // 数字与产物逐值相同。
  const badDev = st.named.filter(n => {
    const r = rows.find(x => x.strength === n.s);
    return !r || Math.abs(n.dev - r.real_dev_mean) > 1e-9;
  });
  rec('L2 每个实测点的失真值与 linearity_law.json 逐值相同',
      st.named.length === rows.length && badDev.length === 0,
      badDev.length ? JSON.stringify(badDev)
                    : `n=${st.named.length} ` +
                      st.named.map(n => `s=${n.s}:${n.dev.toFixed(3)}%`).join('  '));

  rec('L3 「随机 vs 命名」之差与「跨命名方向极差」与产物相同',
      Number(st.gap?.['data-gap']) === LAW.conclusions.safe_regime.max_real_vs_random_gap_pp
      && Number(st.spread?.['data-spread']) === LAW.conclusions.safe_regime.max_direction_spread_pp
      && st.text.includes(LAW.conclusions.safe_regime.max_real_vs_random_gap_pp.toFixed(3) + ' pp')
      && st.text.includes(LAW.conclusions.safe_regime.max_direction_spread_pp.toFixed(3) + ' pp'),
      `产物 gap=${LAW.conclusions.safe_regime.max_real_vs_random_gap_pp} ` +
      `spread=${LAW.conclusions.safe_regime.max_direction_spread_pp}  ` +
      `页面 gap=${st.gap?.['data-gap']} spread=${st.spread?.['data-spread']}`);

  /* ---------------------------------------------------------------- */
  // 实测几何：点的 y 必须随失真单调下降（图是 y 向上的话，y 越小值越大）。
  // 这条抓的是"圆点全画在同一行"这种变异。
  const byS = [...st.named].sort((a, b) => a.s - b.s);
  const mono = byS.every((p, i) => i === 0 || p.cy <= byS[i - 1].cy + 0.5);
  // y 向上为正，所以值越大 y 越小；按 s 升序排 y 是**下降**的，
  // 跨度取 first - last。第一版写成 last - first，得到 -69px 就判红。
  const spreadY = byS.length ? byS[0].cy - byS[byS.length - 1].cy : 0;
  rec('L4 实测圆点的 y 随失真单调，且真的拉开了距离',
      mono && spreadY > 8,
      `y 序列 ${byS.map(p => p.cy.toFixed(1)).join(' > ')}  跨度 ${spreadY.toFixed(1)}px`);

  // 随机区间的高度必须与产物的 (max-min) 成比例。
  // 换算系数不能拍脑袋写：每百分点多少像素 = SVG 屏幕高 × 绘图区占比 ÷ 纵轴满量程。
  // 第一版写死 /15.0*100，与实际差 1.35 倍，只是被 ±3px 的容差盖住了。
  const geo = await page.eval(`(() => {
    const el = document.querySelector('[data-law]');
    const svg = el.querySelector('[data-named]').ownerSVGElement;
    const b = svg.getBoundingClientRect();
    return { h: b.height, viewBoxH: parseFloat(svg.getAttribute('viewBox').split(' ')[3]) };
  })()`);
  const PLOT_FRAC = (120 - 8 - 22) / 120;              // 与组件里的 PAD_T/PAD_B 一致
  const maxY = Math.max(...rows.map(r => r.pred_pct),
                        ...rows.map(r => r.real_dev_mean)) * 1.12;
  const pxPerPct = (geo.h * PLOT_FRAC) / maxY;
  const rndOK = st.rnd.every(r => {
    const want = rows.find(x => x.strength === r.s);
    if (!want) return false;
    return Math.abs(r.h - (want.random_dev_max - want.random_dev_min) * pxPerPct) < 1.0
           && r.h >= 0;
  });
  rec('L5 随机方向的实测区间高度与产物 (max−min) 成比例',
      st.rnd.length === rows.length && rndOK,
      `每百分点 ${pxPerPct.toFixed(2)}px  ` +
      st.rnd.map(r => `s=${r.s}:${r.h.toFixed(2)}px`).join('  '));

  // 解析曲线必须真的是条**有高度**的曲线。
  // 第一版只查宽度，于是「曲线被压平成贴着底边的一条线」照样全绿 ——
  // 而那正是 ½a² 少乘 100 时的实际渲染。宽度通过、高度 0.8px。
  const plotPx = geo.h * PLOT_FRAC;
  rec('L6 解析曲线 ½a² 画成了有高度的曲线，不是贴在底边的一条线',
      !!st.curve && (st.curve.d || '').split(/[ML]/).filter(Boolean).length >= 20
      && st.curve.w > 20 && st.curve.h > plotPx * 0.35,
      `段数 ${(st.curve?.d || '').split(/[ML]/).filter(Boolean).length}  ` +
      `包围盒 ${st.curve ? st.curve.w.toFixed(0) + '×' + st.curve.h.toFixed(0) : '?'}px  ` +
      `绘图区高 ${plotPx.toFixed(0)}px  ` +
      `（压平的线会得到 ≈1px，那必须判红）`);

  /* ---------------------------------------------------------------- */
  // 失效点必须在页面上，且带边界。
  //
  // 第一版用 /out of depth|not counterexample|out of its depth/ 这个**或**，
  // 结果 W4 把正文改成"只是噪声，定律处处成立"之后判据照样全绿 ——
  // 因为图表上那个 "approximation out of depth" 标签命中了第一个分支。
  // 一个能被任一分支满足的析取，等于三个断言都松。
  // 现在：必须命中被 W4 删掉的那句正文，并且反向断言"处处成立"不在页面上。
  const beyond = LAW.conclusions.beyond_safe_regime;
  const overclaim = /law holds everywhere|holds for all|no counterexample(?!s)/i;
  rec('L7 页面明说定律在 s>0.2 失效，且没有反过来声称处处成立',
      /not counterexamples/i.test(st.text)
      && !overclaim.test(st.text)
      && st.text.includes(beyond.max_direction_spread_pp.toFixed(2) + ' pp')
      && st.text.includes(beyond.max_real_vs_random_gap_pp.toFixed(2) + ' pp')
      && !!st.outOfDepth,
      `产物 跨方向 ${beyond.max_direction_spread_pp.toFixed(2)}pp / ` +
      `随机差 ${beyond.max_real_vs_random_gap_pp.toFixed(2)}pp；` +
      `失效带起点 a=${st.outOfDepth?.['data-outofdepth-from']}；` +
      `页面含 "not counterexamples"=${/not counterexamples/i.test(st.text)} ` +
      `含过度声称=${overclaim.test(st.text)}`);

  rec('L8 失效区被画出来（不是只在文字里说）',
      !!st.outOfDepth && Number(st.outOfDepth['data-outofdepth-from']) > 0
      && st.outOfDepth.w > 5 && st.outOfDepth.h > 5,
      `失效带 ${st.outOfDepth ? st.outOfDepth.w.toFixed(1) + '×' + st.outOfDepth.h.toFixed(1) + 'px' : 'null'}`);

  /* ---------------------------------------------------------------- */
  // 红线：这是**反**对方向命名的一条证据，不能被写成支持。
  rec('L9 页面把「随机方向代价相同」写成对方向含义的否定，不是支持',
      /costs exactly as much/i.test(st.text)
      && /carries no information/i.test(st.text)
      && !/confirms|supports the (meaning|naming)/i.test(st.text),
      String(st.text.match(/So a random vector[^]*/)?.[0] || '未见该陈述').slice(0, 140));

  rec('L10 装置自检结果如实展示（玩具输入先跑通）',
      /toy input/i.test(st.text) && st.text.includes(LAW.toy_selfcheck),
      `产物 toy_selfcheck=${LAW.toy_selfcheck}`);

  const errs = page.events
    .filter(e => e.method === 'Runtime.consoleAPICalled' && e.params.type === 'error')
    .map(e => (e.params.args || []).map(a => a.value ?? a.description ?? '').join(' '))
    .filter(t => !/favicon|Failed to load resource/i.test(t));
  // L12 失效区那句话里的批强度必须**来自 steer_directions.json**，不是字面量。
//     第一版那句是 `strength 0.2, just inside the boundary` 的硬编码，
//     而 0.2 恰好等于 safe_regime.strength_max ⇒ 页面看着全对、判据全绿。
//     产品侧已改为真去取；判据侧必须独立地从另一份产物核。
rec('L12 跨产物声明：32k 批次的强度必须来自 steer_directions，且不许是字面量',
  (() => {
    const t = st.boundaryNote;
    if (t == null) return false;
    // ⚠ 不能用 `t.includes(String(DIR.strength))` ——
    //   同一段里还有「the boundary of 0.2」，那个 0.2 会把 includes 喂饱。
    //   我第一版就是这么写的，变异把批次强度改成 0.5、这一条**照样绿**。
    // ⇒ 必须把「sits at strength 后面的那个数」单独**抠出来**比。
    const got = t.match(/sits at strength\s*([\d.]+)/)?.[1];
    const gotLayer = t.match(/\(L(\d+)\)/)?.[1];
    return got === String(DIR.strength) && gotLayer === String(DIR.layer)
        && t.includes(String(LAW.conclusions.safe_regime.strength_max));
  })(),
  `产物 steer_directions.strength=${DIR.strength} layer=${DIR.layer}；`
  + `linearity safe_regime.strength_max=${LAW.conclusions.safe_regime.strength_max}；`
  + `页面「${st.boundaryNote == null ? '（该段不存在）' : st.boundaryNote.slice(0, 96)}」`);

// L13 源级：L12 抓得住「值写错」，**抓不住「值恰好正确却写死」** ——
//     那种情况下渲染逐字相同，L12 必然绿。这正是 §8.3 ⑨ 说的那一类，
//     只能问源码。本条直接读组件源码，禁止 `sits at strength` 后面跟字面量。
rec('L13 源级：失效区那句话的批次强度不许是字面量（L12 在这一层无解）',
  (() => {
    const raw = readFileSync('/Users/zhourui/code/steer3d/frontend/components/'
                             + 'StrengthLawPanel.tsx', 'utf8');
    // ⚠ 必须先**剥掉 // 注释**再查。
    //   我第一版直接 indexOf('sits at strength')，命中的居然是自己写的中文注释
    //   ——「…sits at strength 0.2」里的 0.2 是**写死的字面量**，而它恰好等于…
    //   ⇒ 于是在**正确源码上**就判红。注释里提旧字面量是合法的。
    const code = raw.split('\n').map(l => l.replace(/\/\/.*$/, '')).join('\n');
    if (!/\{batch\.strength\}/.test(code)) return false;
    // 剥完注释后，任何 `sits at strength` 后面都不该紧跟数字字面量
    return !/sits at strength\s+\d/.test(code);
  })(),
  '源码里 sits at strength 后面必须写 {batch.strength}；'
  + '写成字面量时页面与真值相同，L12 那一层在构造上无解');

rec('L14 源级：图例里的命名方向条数必须取自 design.real_directions，不许写死「四个」',
  (() => {
    const raw = readFileSync('/Users/zhourui/code/steer3d/frontend/components/'
                             + 'StrengthLawPanel.tsx', 'utf8');
    const code = raw.split('\n').map(l => l.replace(/\/\/.*$/, '')).join('\n');
    const i = code.indexOf('data-rnd-span');
    if (i < 0) return false;
    // 图例 <p>：从「●」到「随机」那一小段，作用域与被核量一致
    const seg = code.slice(i, code.indexOf('</p>', i));
    // ⚠ 防真空通过：修复后的取数写法必须在场，否则一次改名就让本条空转
    return /law\.design\.real_directions\.length/.test(seg)
        && !/[一二三四五六七八九十]个命名/.test(seg);
  })(),
  '图例里「N 个命名方向」的 N 必须来自 linearity_law.design.real_directions.length；'
  + '写死时页面与真值相同（design 里正好是 4），渲染层在构造上无解');

rec('L11 页面无 console error', errs.length === 0,
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
