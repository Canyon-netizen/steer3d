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
  await sleep(12000);

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
      dn: el.querySelector('[data-cos-digit-newline]')?.getAttribute('data-cos-digit-newline'),
      dnText: (el.querySelector('[data-cos-digit-newline]')?.innerText || '').trim(),
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
  const dn = String(truth.char_pairwise_abs_cos['digit_mass|newline_mass']);
  check('A3 「不是一条轴」的结论印在可见文字里，且数字↔换行余弦与产物一致',
    P.headline.includes(String(truth.headline.readable_directions_lower_bound))
    && P.dn === dn && P.dnText.includes(Number(dn).toFixed(4)),
    `属性 ${P.dn} / 文字「${P.dnText}」/ 产物 ${dn}`);

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

  // E4 同一个量在页面上出现两次，就必须处处一致。
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
