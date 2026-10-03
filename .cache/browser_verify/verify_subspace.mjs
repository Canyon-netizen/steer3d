import { readFileSync } from 'node:fs';
import { launch, Page, CDP } from './cdp_client.mjs';

/**
 * 判据：4 条命名轴之外还剩多少方向（SubspacePanel）。
 *
 * 与 verify_axis_readout.mjs 同一个原则：
 *   判据主体是**页面上读者看到的那段文字**；`data-*` 只用来交叉核对
 *   「属性说的」与「印出来的」。外部真值取磁盘上的 readable_subspace.json。
 *
 * 这块面板的价值全在**三样并排的东西**上，所以 B/C 组专门守它们：
 *   · 地板（打乱后还能预测多少）—— 缺了它 0.86 只是好看
 *   · 同表最高的别人 —— 缺了它一条方向可能不是自己的读出（caution 就这么塌的）
 *   · 位置轴对照不衰减 —— 缺了它「六条都塌」和「装置测不出持续方向」分不开
 * 把任何一栏删掉，页面照样渲染、看起来完全正常，B/C 组会红。
 */
const URL = process.env.BV_URL || 'http://127.0.0.1:10410/';
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_sub_' + process.pid;
const sleep = ms => new Promise(r => setTimeout(r, ms));

const truth = JSON.parse(readFileSync(
  '/Users/zhourui/code/steer3d/frontend/public/latent/data/readable_subspace.json', 'utf8'));
const ROWS = truth.surface_directions.map(r => r.key);

const results = [];
const check = (name, ok, detail) => {
  results.push({ name, ok: !!ok });
  console.log(`[${ok ? 'PASS' : 'FAIL'}] ${name}: ${detail}`);
};

const { proc, version } = await launch({
  port: 9486, userDataDir: PROFILE, windowSize: '1700,1300', url: 'about:blank',
});
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
    check('X0 页面必须真的加载出来（死 URL 不得让本脚本报 PASS/SKIP）', liveOk,
      `href=${L.href} bodyLen=${L.bodyLen} `
      + `data-outcome="${L.outcome}" canvas=${L.canvases} script[src]=${L.scripts}`
      + (isErr ? '  ← chrome-error 页：继续跑下去只会崩，红的计数会被污染'
               : (!isLoopback ? '  ← 不是 127.0.0.1 的页面（环境变量传错了？）' : '')));
    if (!liveOk) {
      try { cdp.close(); } catch {}
      try { proc.kill('SIGKILL'); } catch {}
      console.log(`\n=== 0/${results.length} passed ===`);
      console.log('页面没加载 ⇒ 后面的判据**一条都没跑**（这不是「通过」，也不是「装置崩」）');
      process.exit(1);
    }
  }
  await sleep(12000);

  // ⚠⚠ 第二十六笔：下面那两行注释原来写在 page.eval 的**模板字符串内部**。
  //   那里 `//` **不是注释**，是要发给浏览器 eval 的字符串 ——
  //   而扫描器 `markers_in()` 有一条刻意的规则：「字符串字面量要保留内容」
  //   （把字符串也剥掉的话，提取结果会是空的，而空集合恒绿）。
  //   ⇒ 写在里面的标记名会被**当成真的读取引用**提取出来。
  //   实测后果：那个重复块已从页面删掉，而 C2 报「root 页死引用 1 个」，
  //   死的是我这两行注释。更糟的是 C2a（负控，本意是抓「剥注释吃掉了标记」）
  //   恰恰被这一行**喂饱**了 ⇒ 负控被一个字符串里的假引用顶账。
  //   ⇒ 注释只能写在真正的注释位置，且不要用方括号包住已删标记名。
  const root = await page.eval(`(() => {
    const el = document.querySelector('[data-subspace]');
    if (!el) return JSON.stringify({missing: true});
    const r = el.getBoundingClientRect();
    return JSON.stringify({
      present: true, state: el.getAttribute('data-subspace'),
      w: Math.round(r.width), h: Math.round(r.height),
      lowerBound: el.getAttribute('data-lower-bound'),
      namedAxes: el.getAttribute('data-named-axes'),
      nRows: el.getAttribute('data-n-rows'),
      headline: (el.querySelector('[data-headline-verdict]')?.innerText || '').trim(),
      verdict: (el.querySelector('[data-verdict]')?.innerText || '').trim(),
      notClaimed: (el.querySelector('[data-not-claimed]')?.innerText || '').trim(),
      ctrlRow: el.querySelector('[data-control-row]')?.getAttribute('data-control-row'),
      ctrlText: (el.querySelector('[data-control-row]')?.innerText || '').trim(),
      ctrlVal: el.querySelector('[data-control-delta="100"]')
        ?.getAttribute('data-control-value'),
    });
  })()`);
  const P = JSON.parse(root);

  check('A1 面板已就绪且有非零包围盒',
    P.present && P.state === 'ready' && P.w > 0 && P.h > 0,
    `state=${P.state} ${P.w}x${P.h}px`);

  check('A2 下界与命名轴数都印出且与产物一致',
    Number(P.lowerBound) === truth.headline.readable_directions_lower_bound
    && Number(P.namedAxes) === truth.headline.named_axes
    && Number(P.nRows) === truth.surface_directions.length,
    `下界 ${P.lowerBound} / 命名轴 ${P.namedAxes} / 行数 ${P.nRows}`);

  // ---------- G 组：下界的前提 ----------
  // 「至少 N 条」单独印出来会被读成「可读方向就是 N 条」。
  // 0.5 这个分隔门槛是**选定的**，候选集合也是有限的 —— 两者都必须和下界同屏。
  const g = JSON.parse(await page.eval(`(() => {
    const el = document.querySelector('[data-bound-caveat]');
    if (!el) return JSON.stringify({missing: true});
    const rows = {};
    el.querySelectorAll('[data-threshold-row]').forEach(e => {
      const sep = e.getAttribute('data-threshold-row');
      rows[sep] = { attr: e.querySelector('[data-kind="threshold-count"]')
                        ?.getAttribute('data-value'),
                    text: (e.innerText || '').replace(/\\s+/g, ' ').trim() };
    });
    return JSON.stringify({
      text: (el.innerText || '').replace(/\\s+/g, ' ').trim(),
      old: el.getAttribute('data-bound-old'),
      perm: el.getAttribute('data-order-perm'),
      rows,
    });
  })()`));

  check('G1 下界的前提块存在，且两个前提都印在可见文字里',
    !g.missing && g.text.includes('候选集合') && g.text.includes('门槛')
    && g.text.includes('选定的'),
    g.missing ? '整块缺失' : g.text.slice(0, 78));

  // ---------- G6 caveat 段里的**数字**必须逐个对得上 ----------
  // ⚠ G1 只核了那段散文的**措辞**（候选集合 / 门槛 / 选定的），
  //   里面的**数字**一个都没核。而下界、旧值、候选数、门槛
  //   各自的属性（data-lower-bound / data-bound-old / data-n-candidates）
  //   在**别的元素**上 —— 属性全对、这段话撒谎，没有任何判据会红。
  //   这就是 N4「只查属性不看渲染文本」的同一个洞，只是换了个块。
  // ⇒ 判据主体必须是**读者看到的那段话**本身。
  const H = truth.headline;
  const need = [
    [`至少 ${H.readable_directions_lower_bound} 条`, '当前下界'],
    [`这 ${H.n_candidates} 个`, '候选数'],
    [`它是 ${H.readable_directions_lower_bound_old} 条`, '旧值（须带「上一版」框定）'],
    [`|cos| < ${H.separation_threshold}`, '分隔门槛'],
  ];
  const miss = need.filter(([s]) => !g.text.includes(s)).map(([, w]) => w);
  // 旧值必须**只**出现在「上一版」这一句里，不能被当成当前结论。
  const oldBare = (g.text.match(new RegExp('(?<!上一版候选只有 20 个里的 14 个时，)'
    + `它是?\\s*${H.readable_directions_lower_bound_old}\\s*条`, 'g')) || []).length;
  const oldFramed = g.text.includes(`上一版候选只有 20 个里的 14 个时，`
    + `它是 ${H.readable_directions_lower_bound_old} 条`);
  check('G6 caveat 段里印的每个数字都必须与产物一致（属性对≠文案对）',
    !g.missing && miss.length === 0 && oldFramed && oldBare <= 1,
    g.missing ? '整块缺失'
      : (miss.length ? '缺：' + miss.join('、')
         : `全部对上（14 / 20 / 12 / 0.5），旧值带「上一版」框定=${oldFramed}`)
        + `　段文：${g.text.slice(0, 120)}`);

  // ---------- G9 操作点所在档位必须印对（渲染层） ----------
  // 这一句是我自己在修第八笔时新加的（「而且第 N 档 |cos| < 0.5 就是那个 14 条的操作点」），
  // 第一版用 indexOf(String(h.separation_threshold)) 找档位 ——
  // 键是 "0.50" 而 String(0.5) 是 "0.5" ⇒ -1 ⇒ 页面印出**「第 0 档」**。
  // 编译通过、探针在渲染文本里看到才发现。
  // ⇒ 这一类（键是字符串、数是数字）是**渲染层**缺陷，就该在渲染层判：
  //   判据独立地从产物按数值重算一次档位，再和页面上印出来的那个数比。
  {
    const keys = Object.keys(H.threshold_sensitivity);
    const wantIdx = keys.findIndex(k => Number(k) === Number(H.separation_threshold));
    const gotIdx = g.missing ? null
      : Number((g.text.match(/第\s*(\d+)\s*档/) || [])[1]);
    check('G9 「操作点在第几档」必须与产物按数值重算的结果一致',
      !g.missing && wantIdx >= 0 && gotIdx === wantIdx + 1
      && g.text.includes(`|cos| < ${H.separation_threshold}`),
      g.missing ? '整块缺失'
        : `产物 keys=${JSON.stringify(keys)}，separation_threshold=${H.separation_threshold}`
          + ` ⇒ 应为第 ${wantIdx + 1} 档；页面读到第 ${gotIdx} 档`
          + (gotIdx !== wantIdx + 1 ? '（字符串比数字 ⇒ 第 0 档就是这么来的）' : ''));
  }

  // ---------- G7 两段「承载判决的话」必须逐字印出 ----------
  // ⚠ 它们以前连 data-* 都没有 ⇒ 没有任何判据读得到，而两段都带关键数字：
  //   caution_absorbed  cos(confidence,caution)=0.5537 已超 0.5 门槛 / 被吸收 6 条 / 其中 4 条同源
  //   control.note       Δ=100 仍有 0.7087 ⇒ 装置有能力测出持续方向（**阳性对照论证**）
  //   已有判据只核了同一面板的 4 个 cos 格子与 caveat 段的数字，
  //   这两段承载的是**归属与阳性对照两个判决**，一个都没核。
  // ⇒ 判据主体是**读者看到的那两段话**本身，要求逐字命中产物。
  const notes = JSON.parse(await page.eval(`(() => {
    const g = s => { const e = document.querySelector(s);
                     return e ? (e.innerText||'').replace(/\\s+/g,' ').trim() : null; };
    return JSON.stringify({
      absorbed: g('[data-absorbed-note]'),
      control : g('[data-control-note]'),
    });
  })()`));
  const flat = t => String(t || '').replace(/\s+/g, ' ').trim();
  const pairs = [
    ['caution_absorbed', truth.headline.caution_absorbed, notes.absorbed],
    ['control.note', truth.control.note, notes.control],
  ];
  for (const [name, want, got] of pairs) {
    check(`G7 ${name} 逐字印出（它承载判决，不是装饰）`,
      !!want && !!got && flat(got) === flat(want),
      got == null
        ? `页面上找不到该段（没有 data-* 标记 ⇒ 没人能查它）`
        : (flat(got) === flat(want) ? '逐字一致'
           : '⚠ 页面上印的与产物**不同**') + `　${flat(got).slice(0, 104)}`);
  }

  // ⚠ 块缺失时 `g.rows` 是 undefined。第一版直接 `g.rows[sep]` ⇒ TypeError
  // 被外层 catch 记成「装置错」，结果 G3/G4/G5 **根本没跑**。
  // 断言必须在被检验对象缺失时**干净地红**，而不是把后面的检查一起吞掉。
  const grow = g.rows || {};
  check('G2 六个阈值的条数与产物一致（属性+文字）',
    Object.keys(truth.headline.threshold_sensitivity).length > 0
    && Object.keys(grow).length === Object.keys(truth.headline.threshold_sensitivity).length
    && Object.entries(truth.headline.threshold_sensitivity).every(([sep, v]) =>
      grow[sep] && Number(grow[sep].attr) === v.greedy
      && grow[sep].text.includes(`${v.greedy} 条`)),
    Object.entries(grow).map(([s, v]) => `${s}→${v.attr}`).join(' ')
    || `（阈值行全缺，页面有 0 行 / 产物 ${Object.keys(truth.headline.threshold_sensitivity).length} 行）`);

  check('G3 必须印出「不能读成可读方向就是这么多条」这个结论',
    (g.text || '').includes('不能读成'),
    (g.text || '').match(/.{0,26}不能读成.{0,26}/)?.[0] || '（没有印出该结论）');

  const od = truth.headline.order_dependence;
  check('G4 顺序无关的声明与产物的 200 次随机范围一致',
    Number(g.perm) === od.n_perm
    && (g.text || '').includes(String(od.n_perm))
    && (g.text || '').includes(`恒为 ${od.new_range[0]} 条`),
    `页面 perm=${g.perm} / 产物 ${od.n_perm}，新口径范围 ${od.new_range[0]}–${od.new_range[1]}`);

  check('G5 被吸收的条数与产物一致，且必须印出来',
    (g.text || '').includes(`被吸收 ${truth.headline.absorbed.length} 条`)
    && truth.headline.absorbed.length > 0,
    `页面找「被吸收 N 条」N=${truth.headline.absorbed.length} / 产物 ${truth.headline.absorbed.length}`);

  // A3：下界必须**大于**命名轴数，而且这个比较要出现在**可见文字**里。
  // 写成 data-lower-bound=4 页面照样渲染，但结论就反了。
  // ⚠ 第二十六笔：这条原来核的是那个**已删除**的重复块里的元素（标记名见
  //   git show 67a9f1e 删掉的那段），而那个块已删。改核 `d.verdict` **本身** ——
  //   它才是这个结论的唯一来源，而且它是产物的字段、逐字可核。
  //   ⇒ 这条判据因此变强了：原来「结论 + 余弦」分两处核，
  //     现在核的是「页面上那句判决 == 产物那句判决，且余弦与条数在其中」。
  // ⚠⚠ 这里**刻意不写**那个已删标记名的方括号形式：C2a 是「raw 里方括号里的
  //   标记必须出现在剥完注释的文本里」的负控，而负控的输入是**未剥注释**的原文
  //   ⇒ 真注释里写 `[已删标记]` 会被 C2a 判成「剥注释吃掉了它」而恒红。
  const dn = String(truth.char_pairwise_abs_cos['digit_mass|newline_mass']);
  const nSD = truth.surface_directions.length;
  check('A3 「不是一条轴」的结论印在可见文字里，且条数与余弦都与产物一致',
    P.headline.includes(String(truth.headline.readable_directions_lower_bound))
    && P.verdict === truth.verdict
    && P.verdict.includes(dn) && P.verdict.includes(`${nSD} 条`),
    `判决逐字等于产物 verdict=${P.verdict === truth.verdict}；`
    + `判决含余弦 ${dn}=${P.verdict.includes(dn)}；`
    + `含条数 ${nSD} 条=${P.verdict.includes(`${nSD} 条`)}；`
    + `headline 含下界 ${truth.headline.readable_directions_lower_bound}`
    + `=${P.headline.includes(String(truth.headline.readable_directions_lower_bound))}`);

  for (const key of ROWS) {
    const r = truth.surface_directions.find(x => x.key === key);
    const got = JSON.parse(await page.eval(`(() => {
      const row = document.querySelector('[data-subspace-row="${key}"]');
      if (!row) return JSON.stringify({missing: true});
      const g = n => {
        const e = row.querySelector('[data-guard="${key}-' + n + '"]');
        return e ? { attr: e.querySelector('[data-value]')?.getAttribute('data-value'),
                    text: (e.innerText || '').replace(/\\s+/g, ' ').trim() } : null;
      };
      const cells = {};
      row.querySelectorAll('[data-delta-cell]').forEach(e => {
        const d = e.getAttribute('data-delta-cell').split('-').pop();
        cells[d] = { attr: e.querySelector('[data-delta-value]')?.getAttribute('data-delta-value'),
                     text: (e.innerText || '').replace(/\\s+/g, ' ').trim() };
      });
      return JSON.stringify({
        diag: g('diag'), floor: g('floor'), offdiag: g('offdiag'), cells,
        decay: row.querySelector('[data-decay-value]')?.getAttribute('data-decay-value'),
        maxAxis: row.querySelector('[data-kind="max-axis"]')?.getAttribute('data-value'),
        text: (row.innerText || '').replace(/\\s+/g, ' ').trim(),
      });
    })()`));

    // B1：三栏都在，且属性与可见文字**都**与产物一致。
    // 只查属性会漏掉「文案撒谎、属性诚实」——上一轮变异 M3 专打这一条。
    const want = {
      diag: r.diagnostic.diagonal, floor: r.diagnostic.floor,
      offdiag: r.diagnostic.offdiag_worst,
    };
    const names = { diag: '自己', floor: '地板', offdiag: '同表最高别人' };
    for (const n of ['diag', 'floor', 'offdiag']) {
      const ok = got[n]
        && Number(got[n].attr) === want[n]
        && got[n].text.includes(want[n].toFixed(4));
      check(`B1 ${key} ${names[n]} 栏 属性与文字都与产物一致`, ok,
        got[n] ? `属性 ${got[n].attr} / 文字「${got[n].text}」/ 产物 ${want[n]}`
               : '整栏缺失');
    }

    const dOk = ['0', '20', '100'].every(dd =>
      got.cells[dd] && Number(got.cells[dd].attr) === r.delta[dd]
      && got.cells[dd].text.includes(r.delta[dd].toFixed(4)));
    check(`B2 ${key} Δ=0/20/100 三个格 属性与文字都与产物一致`, dOk,
      ['0', '20', '100'].map(dd => got.cells[dd] ? `Δ${dd}=${got.cells[dd].attr}` : `Δ${dd}缺`).join(' '));

    check(`B3 ${key} 衰减倍数与对命名轴的最高 cos 都印出且一致`,
      Number(got.decay) === r.decay_x20
      && Number(got.maxAxis) === r.diagnostic.max_cos_to_named
      && got.text.includes(`${r.decay_x20}×`),
      `衰减 ${got.decay}（产物 ${r.decay_x20}）/ maxAxis ${got.maxAxis}（产物 ${r.diagnostic.max_cos_to_named}）`);
  }

  // C 组：位置轴对照 —— 没有它，「六条都塌」和「装置测不出持续方向」是同一个现象
  // C0 补这条是因为第一版 M3 只把 data-control-row 改成 "removed" 而没真删那一块，
  // 而 C1/C2 当时只按里面的 span 读 ⇒ 判据全绿。**变异绿 = 变异没落在判据读的路径上。**
  check('C0 对照行必须被标记为对照（data-control-row="true"）',
    P.ctrlRow === 'true', `data-control-row=${P.ctrlRow}`);

  check('C1 位置轴对照行必须在页面上，且 Δ=100 的数与产物一致',
    !!P.ctrlText && P.ctrlVal === String(truth.control.delta['100'])
    && P.ctrlText.includes(Number(truth.control.delta['100']).toFixed(4)),
    `属性 ${P.ctrlVal} / 产物 ${truth.control.delta['100']}`);

  check('C2 对照必须被说明是「装置能测出持续方向」的证据',
    P.ctrlText.includes('几乎不塌'),
    P.ctrlText.slice(0, 70) || '（对照行没有印出来）');

  check('C3 判决与「不是因果性」的边界都必须印在可见文字里',
    P.verdict.includes('非循环') && P.verdict.includes('专属')
    && P.notClaimed.includes('可读性') && P.notClaimed.includes('因果性')
    && P.notClaimed.includes('GPU'),
    `判决 ${P.verdict.length} 字 / 边界「${P.notClaimed.slice(0, 40)}」`);

  // ---- C3b 判决里的 decay 区间必须**从那 4 条自己重算**（§8.9 第十三笔）----
  // 原句写「Δ=20 塌 6.4×–42.1×」，而下界 6.4 取自
  // **named_axis_readouts[0]**（top1_prob_renorm，一条**命名轴**），
  // 句子主语却是「这 4 条」= surface_directions（11.8/18.7/42.1/12.9）。
  // ⇒ 区间应为 11.8–42.1。判据原来只 includes('非循环')/('专属')，从不看数。
  // ⚠ 判据必须**按范围比对**而不是 includes 那个写死的串 ——
  //   includes('6.4') 在改对之后仍然会绿（6.4 在别处也出现过）。
  {
    const decays = truth.surface_directions.map(r => r.decay_x20);
    const lo = Math.min(...decays), hi = Math.max(...decays);
    const m = P.verdict.match(/Δ=20\s*塌\s*([\d.]+)×\s*[–-]\s*([\d.]+)×/);
    const gotLo = m ? Number(m[1]) : NaN, gotHi = m ? Number(m[2]) : NaN;
    check('C3b 判决里的「Δ=20 塌 X×–Y×」必须等于那 4 条 decay_x20 的最小/最大',
      m && Math.abs(gotLo - lo) < 0.05 && Math.abs(gotHi - hi) < 0.05,
      `判决写「${gotLo}×–${gotHi}×」；从 surface_directions[].decay_x20 重算 = `
      + `${lo}–${hi}（${decays.join(', ')}）`
      + (m ? '' : '  ⚠ 判决里根本没有「Δ=20 塌 X×–Y×」这个句式'));
    // 顺带核另一个归属：下界不许取自命名轴（那是 2026-10-04 修掉的那个错）
    const namedDecays = (truth.named_axis_readouts || []).map(x => x.decay_x20);
    if (namedDecays.length) {
      check('C3c 判决的 decay 区间不得混入命名轴的 decay（那是另一个集合）',
        !namedDecays.some(v => Math.abs(v - gotLo) < 1e-9 && v < lo),
        `命名轴 decay = ${namedDecays.join(', ')}；判决下界 = ${gotLo}；`
        + `surface 下界 = ${lo}`
        + (namedDecays.some(v => Math.abs(v - gotLo) < 1e-9 && v < lo)
           ? '  ⚠ 下界取自命名轴' : ''));
    }
  }

  // ---- P 组：产物里**手写散文**的数字必须能现算（§8.9 第十五笔）----
  // 与 C3b/C3c 同族但覆盖面更大：C3 只核了判决那一句，
  // 而 `bound_caveat` / `caution_absorbed` / `control.note` 三段里的数
  // 全是生成器里的**字面量**，且此前**一条判据都没碰**。
  // ⚠ P10 是这一组的关键：它把判据卡在**生成器那一层**。
  //   只核产物会漏 —— 那些字面量在生成器里，下次重跑就又出现。
  {
    const H = truth.headline;
    const SEP = H.separation_threshold;
    const TS = H.threshold_sensitivity;
    const seatKey = Object.keys(TS).find(k => Math.abs(Number(k) - SEP) < 1e-9);
    const caveat = H.bound_caveat || '';
    const absorbedNote = H.caution_absorbed || '';

    // P1 「至少 N 条」== 选定门槛那一档的 perm_min
    const wantN = TS[seatKey]?.perm_min;
    const gotN = (caveat.match(/至少\s*(\d+)\s*条/) || [])[1];
    check('P1 bound_caveat 的「至少 N 条」== 选定门槛那一档的下界',
      Number(gotN) === wantN,
      `caveat 写「至少 ${gotN} 条」；${seatKey} 档 perm_min = ${wantN}`
      + `（separation_threshold=${SEP}）`);

    // P2 「候选集合是这 M 个」== n_candidates
    const wantM = H.n_candidates;
    const gotM = (caveat.match(/这\s*(\d+)\s*个/) || [])[1];
    check('P2 bound_caveat 的「候选集合是这 M 个」== headline.n_candidates',
      Number(gotM) === wantM,
      `caveat 写 ${gotM}；n_candidates = ${wantM}`);

    // P3 「|cos|<T」== separation_threshold
    const gotT = (caveat.match(/\|cos\|\s*<\s*([\d.]+)/) || [])[1];
    check('P3 bound_caveat 的门槛必须等于 headline.separation_threshold',
      Math.abs(Number(gotT) - SEP) < 1e-9,
      `caveat 写 |cos|<${gotT}；separation_threshold = ${SEP}`);

    // P4 门槛敏感性必须**列全每一档**且数一致 —— 不许手挑
    // ⚠ 旧文案只列了 0.35/0.45/0.55/0.60，**跳过了 0.50**，
    //   而 0.50 正是产出头条数字的那一档 ⇒ 读者没有可比的那一行。
    {
      const allKeys = Object.keys(TS).sort((a, b) => Number(a) - Number(b));
      const listed = (caveat.match(/(\d\.\d+)→(\d+)\s*条/g) || []);
      const listedKeys = listed.map(x => x.match(/(\d\.\d+)→/)[1]);
      const complete = listedKeys.length === allKeys.length
        && allKeys.every(k => listedKeys.includes(k));
      const consistent = listed.every(x => {
        const m = x.match(/(\d\.\d+)→(\d+)/);
        return Math.abs(Number(m[1]) - SEP) < 1e-9 || TS[m[1]]?.greedy === Number(m[2]);
      });
      check('P4 bound_caveat 必须列出**全部**门槛档位（不许手挑），且每档的数与结构化表一致',
        complete && consistent,
        `结构化表有 ${allKeys.length} 档（${allKeys.join('/')}）；`
        + `caveat 列了 ${listedKeys.length} 档（${listedKeys.join('/')}）`
        + (complete ? '' : ' ⇒ 有档位被跳过，其中可能正是选定那一档')
        + (consistent ? '' : ' ⇒ 有档位的数与表不一致'));
    }

    // P5 caution_absorbed 的余弦 —— 跨产物单份来源
    {
      let pair = null;
      try {
        const ax = JSON.parse(readFileSync(
          '/Users/zhourui/code/steer3d/frontend/public/latent/data/axis_readouts.json', 'utf8'));
        pair = ax?.axes?.caution?.specificity?.pair_cos_confidence_caution;
      } catch (e) { /* 读不到 → 下面报未判 */ }
      const gotC = (absorbedNote.match(/cos\(confidence,\s*caution\)\s*=\s*([\d.]+)/) || [])[1];
      if (pair === undefined || pair === null) {
        check('P5 caution_absorbed 的余弦必须等于 axis_readouts 里那一对的实测值', false,
          'axis_readouts.json 读不到 pair_cos_confidence_caution ⇒ 未判');
      } else {
        const want = Number(pair).toFixed(4);
        check('P5 caution_absorbed 的余弦必须等于 axis_readouts 里那一对的实测值',
          gotC === want,
          `caveat 写 ${gotC}；axis_readouts pair_cos = ${pair}（四位小数 ${want}）`
          + `；⚠ 这份手抄过去在两个产物里各有一份，谁先改谁不会红`);
      }
    }

    // P6 caution_absorbed 的门槛与条数
    {
      const gotT2 = (absorbedNote.match(/超过\s*([\d.]+)\s*门槛/) || [])[1];
      const gotN2 = (absorbedNote.match(/还有\s*(\d+)\s*条/) || [])[1];
      check('P6 caution_absorbed 的门槛与条数必须现算',
        Math.abs(Number(gotT2) - SEP) < 1e-9 && Number(gotN2) === H.absorbed.length,
        `caveat 写「超过 ${gotT2} 门槛，还有 ${gotN2} 条」；`
        + `separation_threshold = ${SEP}；len(absorbed) = ${H.absorbed.length}`);
    }

    // P7 control.note 的 Δ=100 数与「N 条」
    {
      const note = truth.control.note || '';
      const got100 = (note.match(/Δ=100\s*仍有\s*([\d.]+)/) || [])[1];
      const want100 = truth.control.delta['100'];
      const gotN3 = Number((note.match(/下面\s*(\d+)\s*条/) || [])[1]);
      const wantN3 = truth.surface_directions.length + (truth.named_axis_readouts || []).length;
      check('P7 control.note 的 Δ=100 数与「下面 N 条」必须现算',
        Math.abs(Number(got100) - want100) < 5e-5 && gotN3 === wantN3,
        `note 写 Δ=100 仍有 ${got100}、下面 ${gotN3} 条；`
        + `control.delta["100"] = ${want100}；`
        + `len(surface_directions)+len(named_axis_readouts) = ${wantN3}`);
    }

    // P8 question / named_axes == axis_readouts 的轴数（跨产物）
    {
      let nAx = null;
      try {
        const ax = JSON.parse(readFileSync(
          '/Users/zhourui/code/steer3d/frontend/public/latent/data/axis_readouts.json', 'utf8'));
        nAx = Object.keys(ax?.axes || {}).length;
      } catch (e) { /* 未判 */ }
      const gotQ = Number((String(truth.question).match(/(\d+)\s*条命名轴/) || [])[1]);
      if (nAx === null) {
        check('P8 question 与 named_axes 的轴数必须等于 axis_readouts 的轴数', false, '读不到 axis_readouts ⇒ 未判');
      } else {
        check('P8 question 与 named_axes 的轴数必须等于 axis_readouts 的轴数',
          gotQ === nAx && H.named_axes === nAx,
          `question 写 ${gotQ}；named_axes = ${H.named_axes}；axis_readouts.axes 键数 = ${nAx}`);
      }
    }

    // P10 **源级**：生成器里这些散文段不得再有裸数字字面量
    // ⚠ 这是这一组最关键的一条：上面九条只核**产物**，
    //   而字面量在**生成器**里 —— 只核产物的话，下次重跑字面量又回来。
    {
      const gen = '/Users/zhourui/code/steer3d/.cache/xcheck/build_subspace_readout.py';
      let src = null;
      try { src = readFileSync(gen, 'utf8'); } catch (e) { /* 未判 */ }
      if (src === null) {
        check('P10 生成器里这些散文段不得有裸数字字面量（判据要卡在生成器那一层）', false,
          '读不到 %s ⇒ 未判' % gen);
      } else {
        // 抽出 bound_caveat / caution_absorbed / control.note 三段
        // ⚠⚠⚠ 三次踩坑才做对，每次都是同一个毛病：
        //  ① `lastIndexOf('(')` 当块起点 ⇒ 抓到**上一个 key** 里那个 `(`。
        //  ② 只按 `indexOf('(')` 往前找 ⇒ 值里没括号时会跨到别的块。
        //  ③ 「下一个同级 key」的正则**不看缩进** ⇒ 把 8 空格的内部字段
        //     当成了 4 空格的同级字段，于是 control 块只取到 `key`+`label`
        //     共 43 字符，**根本没盖到 note**，却照样报「无字面量」。
        //     ⚠ 而「看起来绿」的判据比「红着」更坏：它宣称核过的那段它没核。
        // ⇒ 终版：**按锚点所在行的缩进找下一个同级 key**（缩进是结构，不是格式符号）。
        const grabIndented = (anchor) => {
          const i = src.indexOf(anchor);
          if (i < 0) return '';
          const lineStart = src.lastIndexOf('\n', i) + 1;
          const indent = src.slice(lineStart, i).match(/^[ \t]*/)[0];
          // ⚠ `\n` + 缩进 **不要求缩进从行首开始** ⇒ 12 空格的后续行
          //   前 8 个空格也能匹配上，于是块被截成 26 字符。
          //   ⇒ 要求 `indent` 之后**紧接**引号（多一个空格就不算同级）。
          const re = new RegExp('\\n' + indent + '"');
          const rest = src.slice(i);
          const m = re.exec(rest);
          if (m) {
            return rest.slice(0, m.index + 1 + indent.length);
          }
          // 没有下一个同级 key（它是最后一个字段）⇒ 取到本 dict 的收尾
          const close = rest.search(/\n[ \t]*\}/);
          return close > 0 ? rest.slice(0, close) : rest;
        };
        const blocks = [
          grabIndented('"bound_caveat"'),
          grabIndented('"caution_absorbed"'),
          grabIndented('"control": {'),
        ];
        const found = blocks.filter(Boolean).length;
        // ⚠ 每段都必须**够长**才算数：太短说明锚点没定位到整段，
        //   那时判红没有意义（那是「没核到」，不是「核过了」）。
        const tooShort = blocks.map((b, k) => [k, b.length]).filter(([, n]) => n < 120);
        if (found < 3 || tooShort.length) {
          check('P10 生成器里这三段散文不得有裸数字字面量（判据要卡在生成器那一层）', false,
            `定位到 ${found}/3 段，长度 ${blocks.map(b => b.length).join('/')}`
            + (tooShort.length
              ? ` ⇒ 第 ${tooShort.map(([k]) => k + 1).join('、')} 段短于 120 字符，`
                + `说明锚点没定位到整段，未判（不是「没有字面量」）`
              : ' ⇒ 锚点失效，未判'));
        } else {
          const lits = [];
          // ⚠ **显式豁免**：文档节号（§4.9 / §8.3 / L12）不是观测量，
          //   重算它没有意义 —— 就像「Δ=0」是设置名而不是读数。
          //   豁免必须**带理由印出来**，否则「被判据放过」和「没人看见」是同一件事。
          let exempt = 0;
          for (const b of blocks) {
            for (const m of b.matchAll(/"([^"\\]*)"/g)) {
              const raw = m[1];
              for (const n of raw.matchAll(/(?<![\w.])\d+\.\d+|(?<![\w.])\d+(?![\w.])/g)) {
                // 命中的是**紧跟在 § 后面**的节号（如「§4.9」里的 4.9）
                if (/§\s*$/.test(raw.slice(0, n.index))) { exempt++; continue; }
                lits.push(n[0]);
              }
            }
          }
          check('P10 生成器里这三段散文不得有裸数字字面量（必须插值，否则下次重跑字面量又回来）',
            lits.length === 0,
            lits.length === 0
              ? `三段都定位到（长度 ${blocks.map(b => b.length).join('/')}）且没有裸数字字面量；`
                + `豁免 ${exempt} 处文档节号（节号不是观测量）；`
                + `插值来源：SEP / N_CAND / TSENS / PAIR_CONF_CAUT / N_COLLAPSED / D_MAX / N_HELDOUT_ABSORBED`
              : `仍有 ${lits.length} 个裸数字字面量：${JSON.stringify(lits.slice(0, 12))}`
                + `（另豁免 ${exempt} 处节号）`);
        }
      }
    }
  }


  // 这一条是被**截图**逼出来的：顶部已经改成「至少 14 条」，
  // 而底部 not_claimed 还写着「这 12 条」—— 页面自相矛盾，
  // 而上面 31 条判据全绿（它们各自都核对了自己那段，没人会去互相比）。
  const LB = truth.headline.readable_directions_lower_bound;
  const LB_OLD = truth.headline.readable_directions_lower_bound_old;
  // 详情要**指出出错的句子**，不是打印段尾 —— 段尾永远是那句免责声明。
  const badHit = (P.notClaimed.match(/.{0,18}这 \d+ 条.{0,12}/g) || []).join(' ／ ');
  check('E4 边界里引用的下界必须与 headline 一致（不得残留旧值）',
    P.notClaimed.includes(`这 ${LB} 条`)
    && (LB === LB_OLD || !P.notClaimed.includes(`这 ${LB_OLD} 条`)),
    `headline=${LB} / 旧值=${LB_OLD} / 边界里出现的「这 N 条」：${badHit || '（一处都没有）'}`);

  // ---------- G8 源级：caveat 块里不许再出现手写的门槛计数 ----------
  // 背景（第八笔洞，变异实测）：把散文里的「0.35→9 条、0.45→12 条、0.60→16 条」
  // 改成「0.35→7 条、0.45→20 条、0.60→2 条」，页面在**同一块内**与正上方那张
  // 数据驱动的门槛表直接打架（表印 0.35→9，散文印 0.35→7），而
  //   verify_subspace 37/37、verify_outcome 53/53、全量 248 条判据 **0 条红**。
  // G6 抓的是「caveat 段里印的每个数字」—— 而这些数字压根不在带 data-* 的
  // caveat-text 段里，它们在一段**没标记**的兄弟段落中，G6 的作用域够不着。
  // ⇒ 与 L12/L13 同一结论：这一类**只能问源码**，渲染层在构造上无解
  //   （值写错时同屏自相矛盾，但没有任何判据同时读这两处）。
  // ⚠ 必须先剥注释：源码里我自己写的说明注释就含「表说 0.35→9，散文说 0.35→7」，
  //   而注释里提旧字面量是合法的 —— 那段注释同时就是这条判据的**负控**。
  // ⚠ 作用域必须与被核量一致：只查 caveat 块，不查整个文件（§L12 教训）。
  // ⚠ 防真空通过：切片必须非空、且必须含「修复后应当出现的取数写法」，
  //   否则一次改名就能让本条变成 0===0 的空转（peakBad `&& false` 那种）。
  {
    const raw = readFileSync(
      '/Users/zhourui/code/steer3d/frontend/components/SubspacePanel.tsx', 'utf8');
    const strip = s => s
      .replace(/\{\/\*[\s\S]*?\*\/\}/g, '')   // JSX 注释（可跨行）
      .replace(/\/\*[\s\S]*?\*\//g, '')        // 普通块注释
      .split('\n').map(l => l.replace(/\/\/.*$/, '')).join('\n');
    const code = strip(raw);
    const i = code.indexOf('data-bound-caveat="true"');
    const j = code.indexOf('data-absorbed-note', i + 1);
    const slice = i >= 0 && j > i ? code.slice(i, j) : '';
    const handSweep = slice.match(/门槛\s*0\.\d+\s*→\s*\d+\s*条/g) || [];
    const handAbsorb = slice.match(/含\s*\d+\s*条/g) || [];
    // 作用域分两层，各按被核量取：
    //   块内（caveat 那段）—— 手写数字有没有混进来；
    //   全文件 —— 档位是不是按**数值**找的。opIdx 定义在组件顶部、不在块内，
    //   拿块内去核它等于核错层（又一次「作用域必须与被核量一致」）。
    const liveOk = /h\.absorbed\.join\(/.test(slice)
                && /h\.threshold_sensitivity/.test(slice)
                && /h\.readable_directions_lower_bound/.test(slice);
    const numCmp = /findIndex\(k\s*=>\s*Number\(k\)\s*===\s*Number\(h\.separation_threshold\)\)/.test(code);
    const strCmp = /indexOf\(String\(h\.separation_threshold\)\)/.test(code);
    check('G8 源级：caveat 块里的门槛计数与「含 N 条」必须取自产物，不许手写',
      slice.length > 0 && liveOk && numCmp && !strCmp
      && handSweep.length === 0 && handAbsorb.length === 0,
      slice.length === 0
        ? '取不到 caveat 块（data-bound-caveat / data-absorbed-note 定位失败）'
        : (liveOk ? '' : '修复后的取数写法不在块内 —— 本条可能已空转，请复查')
          + (numCmp ? '' : ' 未找到按数值比较的档位查找（findIndex(Number(k) === Number(...))）')
          + (strCmp ? ' 档位用 indexOf(String(...)) 比 —— 键是 "0.50" 时会印成「第 0 档」' : '')
          + ` 手写门槛扫描 ${handSweep.length} 处、手写「含 N 条」${handAbsorb.length} 处`
          + (handSweep.length ? `：${handSweep.join(' / ')}` : '')
          + (handAbsorb.length ? `：${handAbsorb.join(' / ')}` : ''));
  }

  check('E5 边界必须说清「可读维度数 ≠ 需要干预验证的轴数」',
    P.notClaimed.includes('可读维度数') && P.notClaimed.includes('干预'),
    P.notClaimed.slice(-52) || '（边界没有印出来）');
} catch (e) {
  check('装置', false, String(e && e.message ? e.message : e));
} finally {
  try { await cdp.send('Browser.close'); } catch {}
  try { proc.kill(); } catch {}
}

const failed = results.filter(r => !r.ok);
console.log(`\nRESULT ${failed.length ? 'FAIL' : 'PASS'} ${results.length - failed.length}/${results.length}`);
process.exit(failed.length ? 1 : 0);
