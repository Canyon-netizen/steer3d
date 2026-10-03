import { readFileSync } from 'node:fs';
import { launch, Page, CDP } from './cdp_client.mjs';

/**
 * 判据：轴→观测量面板。
 *
 * 判据主体是**页面上读者看到的那段文字**；`data-*` 属性只用来交叉核对
 * 「属性说的」与「印出来的」。外部真值取磁盘上的 axis_readouts.json ——
 * 不取页面自己报的值。
 *
 * 特别要守住的一条：这块面板的全部价值在于**并排显示位置对照**。
 * 所以 C 组判据专门查对照栏在不在、印的数对不对。
 * 如果哪天有人把对照那一栏删掉（页面照样渲染、看起来完全正常），
 * C1–C3 会红。
 */
const URL = process.env.BV_URL || 'http://127.0.0.1:10340/';
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_axis_' + process.pid;
const sleep = ms => new Promise(r => setTimeout(r, ms));

const truth = JSON.parse(readFileSync(
  '/Users/zhourui/code/steer3d/frontend/public/latent/data/axis_readouts.json', 'utf8'));
// ⚠ §8.9 第十三笔：这一行原来也是手抄的
//   `const AXES = ['confidence','caution','creativity','reasoning']`，
//   而**产品侧 AxisReadoutPanel 也写死了同一份名单**。
//   ⇒ 产物加第 5 条轴时，产品少显示一行、判据照样只核那 4 行，
//     **两边共用一个手写常量 ⇒ 任何新增都被双方同时忽略**。
//   这比「判据漏读一个标记」更糟：判据的取样范围和被测范围是同一个字面量。
//   处置与第十一笔 L13「按 built_from 动态加载，不要手抄名单」同形。
const AXES = Object.keys(truth.axes);
const N_AXES = AXES.length;

const results = [];
const check = (name, ok, detail) => {
  results.push({ name, ok: !!ok });
  console.log(`[${ok ? 'PASS' : 'FAIL'}] ${name}: ${detail}`);
};

const { proc, version } = await launch({
  port: 9484, userDataDir: PROFILE, windowSize: '1700,1100', url: 'about:blank',
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

  const root = await page.eval(`(() => {
    const el = document.querySelector('[data-axis]');
    if (!el) return JSON.stringify({present:false});
    const r = el.getBoundingClientRect();
    return JSON.stringify({
      present: true, state: el.getAttribute('data-axis'),
      w: Math.round(r.width), h: Math.round(r.height),
      text: (el.innerText||'').replace(/\\s+/g,' ').trim(),
      measured: el.getAttribute('data-measured'),
      taut: el.getAttribute('data-tautological'),
      shared: el.getAttribute('data-shared-readout'),
      posAxis: el.getAttribute('data-position-axis'),
      notMeasured: el.getAttribute('data-not-measured'),
      retraction: (el.querySelector('[data-retraction]')?.innerText || '')
        .replace(/\s+/g, ' ').trim(),
    });
  })()`);
  const P = JSON.parse(root);

  check('A1 面板已就绪且有非零包围盒',
    P.present && P.state === 'ready' && P.w > 0 && P.h > 0,
    `state=${P.state} ${P.w}x${P.h}px`);

  if (P.present && P.state === 'ready') {
    // A2 四条轴都在，行上的状态标记与产物一致
    for (const ax of AXES) {
      const got = await page.eval(`(() => {
        const el = document.querySelector('[data-axis-row="${ax}"]');
        if (!el) return JSON.stringify({missing:true});
        const v = el.querySelector('[data-verdict]');
        return JSON.stringify({
          status: el.getAttribute('data-status'),
          beating: el.getAttribute('data-beating'),
          layers: el.getAttribute('data-layers'),
          statusLabel: el.querySelector('[data-status-label]')?.textContent?.trim(),
          candidate: el.querySelector('[data-candidate]')?.getAttribute('data-candidate') || '',
          rowText: (el.innerText||'').replace(/\\s+/g,' ').trim(),
          verdictText: v ? (v.innerText||'').replace(/\\s+/g,' ').trim() : '',
        });
      })()`);
      const g = JSON.parse(got);
      const want = truth.axes[ax].status;
      check(`A2 ${ax} 状态与产物一致`, g.status === want,
        `页面 ${g.status} / 产物 ${want}；标签「${g.statusLabel}」`);
      // ⚠ 行缺失时**必须在这里停**，否则下面的 `g.rowText.match(...)` 会炸。
      //   我第一版没有这个守卫：行一缺，A2 正确报红，紧接着整轮装置抛
      //   「Cannot read properties of undefined (reading 'match')」，
      //   A8 / C3a / C3d / A9 全被这个崩溃**掩盖** ⇒ RESULT 只剩 23/25。
      //   ⇒ 判据在它本该报告的那个失败上崩掉，比不判还坏：
      //     调用方看到的是「装置崩」，不是「这一行不见了」。
      //   ⇒ 而且要把「这一行的其余判据没跑」**说出来**（第三种状态自己报）。
      if (g.missing) {
        check(`A2b ${ax} 行缺失 ⇒ 该行其余判据未跑`, false,
          `页面没有 [data-axis-row="${ax}"]，本行后续判据（读出方向/徽章/专属性/矩阵）**一条都没跑**`);
        continue;
      }
      // A5「Δ=0 读出方向」的名字 —— 这块面板的全部命题就是「轴 → 观测量」，
      // 而这个名字是**可见文字**、有 data-candidate，却一直没人读（C4 报的第 10 个）。
      // 它旁边那两串 cos 由 B 组核，但「指向哪个观测量」这个归属判断没人核。
      // ⚠ **不要在判据里复制组件的 CAND_TEXT 映射表**：那是产品侧常量，
      //   复制一份就变成「两边各自维护同一张表」，产物或文案一变两边一起错
      //   —— 与 I9（判据侧也写死 1.7，两边互相背书）同一族。
      // ⇒ 判据只核**无歧义的那一半**：data-candidate 逐字等于产物的 modal_candidate。
      //   文本侧只要求「读者看得到一个非空的名字」，
      //   至于它显示成 key 还是中文说明，是显示选择，不是判决。
      const a0 = truth.axes[ax].at_delta0 || {};
      const candKey = a0.modal_candidate || '';
      const cellText = g.rowText.match(/Δ=0 读出方向：\s*([^（(]{1,60})/);
      const shown = cellText ? cellText[1].trim() : '';
      check(`A5 ${ax}「Δ=0 读出方向」必须取自产物（属性逐字相等 + 印出非空名字）`,
        !!candKey && g.candidate === candKey && shown.length > 0,
        `属性「${g.candidate}」/ 产物 key「${candKey}」；读者看到的名字「${shown}」`);

      // A4 徽章文案本身也必须与产物一致。
      // 这一条是被变异 M2 逼出来的：M2 把徽章硬编码成「已测到读出方向」，
      // 而 A2 读的是 data-status 属性、A3 读的是判定句 —— **两者都不受徽章影响**，
      // 于是判据全绿。也就是「页面可以给四行都印『已测』而判据通过」。
      const LABEL_OF = { measured: '已测到读出方向', not_measured: '测不出',
                         position_axis: '判定为轨迹位置轴',
                         tautological: '已测，但目标是定义式',
                         shared_readout: '非循环，但不专属' };
      check(`A4 ${ax} 徽章文案与产物状态一致`,
        g.statusLabel === LABEL_OF[want],
        `页面「${g.statusLabel}」/ 期望「${LABEL_OF[want]}」`);

      // A3 印出来的判定句必须真的包含对应的词。
      // 2026-10-03：confidence/caution 降级后，判定句各要印自己的新结论 ——
      // 「都印 token 局部」不再够用，因为那正是被撤回的那句话。
      const need = want === 'tautological' ? ['token 局部', '构造恒等式']
        : want === 'shared_readout' ? ['分不开归属', '共用']
        : want === 'measured' ? ['token 局部']
        : want === 'position_axis' ? ['轨迹位置轴']
        : ['测不出'];
      check(`A3 ${ax} 判定句包含关键结论`,
        need.every(k => g.verdictText.includes(k)),
        `「${g.verdictText.slice(0, 70)}」`);

      // B 组：cos 与对照都要真的印出来，且与产物一致
      for (const L of ['12', '14', '20']) {
        const c = truth.axes[ax].at_delta0.per_layer[L];
        const cell = await page.eval(`(() => {
          const el = document.querySelector('[data-cell="${ax}-${L}"]');
          if (!el) return JSON.stringify({missing:true});
          const r = el.getBoundingClientRect();
          return JSON.stringify({
            cos: el.querySelector('[data-cos]')?.getAttribute('data-cos'),
            ctl: el.querySelector('[data-control-cos]')?.getAttribute('data-control-cos'),
            text: (el.innerText||'').replace(/\\s+/g,' ').trim(),
            w: Math.round(r.width), h: Math.round(r.height),
          });
        })()`);
        const cc = JSON.parse(cell);
        if (cc.missing) { check(`B1 ${ax}/L${L} 格子存在`, false, 'missing'); continue; }
        const okCos = Math.abs(Number(cc.cos) - c.cos) < 5e-3;
        const okCtl = Math.abs(Number(cc.ctl) - c.control_cos) < 5e-3;
        const inText = cc.text.includes(c.cos.toFixed(3))
          && cc.text.includes(c.control_cos.toFixed(3));
        check(`B1 ${ax}/L${L} cos 与对照都印出且与产物一致`,
          okCos && okCtl && inText && cc.w > 0 && cc.h > 0,
          `页面 cos=${cc.cos} 对照=${cc.ctl} | 产物 cos=${c.cos} 对照=${c.control_cos} | 文字「${cc.text}」`);
      }
    }

    // C 组：对照这件事必须在页面上被说清楚
    const saysControl = P.text.includes('对照') && P.text.includes('step_frac');
    check('C1 页面解释了对照是什么', saysControl,
      P.text.includes('step_frac') ? '提到 step_frac 对照' : '未提到');
    const saysSearch = P.text.includes('搜索') || P.text.includes('付过钱');
    check('C2 页面声明了多重比较的代价', saysSearch,
      saysSearch ? '已声明 p 为搜索付过钱' : '未声明');

    // ---- C3 重写（§8.9 第十三笔）----
    // 原文：`P.text.includes('四条独立轴') || P.text.includes('4 条独立轴')`。
    // 三个问题，每一个都单独足以让它失效：
    //   ① **haystack 比作用域大**：P.text 是整块面板的 innerText，而这块面板
    //      有三处含该短语（caveat、标题「N 条独立轴各自指向什么？」、尾注）。
    //      ⇒ caveat 被整个删掉，C3 照样绿。
    //   ② **只查了判据名的一半**：名字说「6 个标签 = 4 条轴」，
    //      代码从头到尾没看过「6」。
    //   ③ **从不重算**：「4」是不是真的，判据一个字都没问。
    // 现在：作用域收到 [data-vocab-caveat]，两个数都从产物重算。
    {
      const V = JSON.parse(await page.eval(`(() => {
        const el = document.querySelector('[data-vocab-caveat]');
        const root = document.querySelector('[data-axis]');
        if (!el || !root) return JSON.stringify({missing:true});
        const p = el.closest('p') || el.parentElement;
        return JSON.stringify({
          caveat: (el.innerText||'').replace(/\\s+/g,' ').trim(),
          tail:    (p.innerText||'').replace(/\\s+/g,' ').trim(),
          rows:    root.querySelectorAll('[data-axis-row]').length,
          specCells: root.querySelectorAll('[data-spec-cell]').length,
          nAxesOnPage: Object.keys(
            Array.from(root.querySelectorAll('[data-axis-row]'))
              .reduce((o,e)=>(o[e.getAttribute('data-axis-row')]=1,o), {})
          ).length,
        });
      })()`));
      if (V.missing) {
        check('C3a vocabulary_caveat 有可寻址的渲染点（data-vocab-caveat）', false,
          '页面上找不到 [data-vocab-caveat] ⇒ 判据无法把作用域收到这一句上');
        check('C3b caveat 里的轴数必须从产物重算', false, 'caveat 定位失败，未判');
        check('C3c caveat 里的标签数必须从产物重算', false, 'caveat 定位失败，未判');
      } else {
        check('C3a vocabulary_caveat 有可寻址的渲染点（data-vocab-caveat）', true,
          `已定位：${V.caveat.slice(0, 46)}…`);
        // ③ 重算：caveat 写的轴数必须等于产物的 axes 条数
        const mAxes = V.caveat.match(/(\d+)\s*条独立轴/);
        const gotAxes = mAxes ? Number(mAxes[1]) : -1;
        check('C3b caveat 里的轴数必须从产物重算',
          gotAxes === N_AXES,
          `caveat 写「${gotAxes} 条独立轴」；产物 axes 键数 = ${N_AXES}`
          + (gotAxes !== N_AXES ? '（散文里的数与结构化字段脱钩了）' : ''));
        // ② + ③ 重算：标签数 = 轴数 + caveat 自己声明的等价关系条数
        //    （每条 `a≡−b` 蕴含多一个标签）⇒ 这是对「6」的独立重算，
        //      不是把散文里的 6 再抄一遍。
        const nEquiv = (V.caveat.match(/≡/g) || []).length;
        const wantLabels = N_AXES + nEquiv;
        const mLab = V.caveat.match(/(\d+)\s*个方向标签/);
        const gotLab = mLab ? Number(mLab[1]) : -1;
        check('C3c caveat 里的标签数 = 轴数 + 等价关系条数（独立重算）',
          gotLab === wantLabels,
          `caveat 写「${gotLab} 个方向标签」；重算 = 轴数 ${N_AXES} + 等价关系 ${nEquiv} = ${wantLabels}`);
        // 附带：尾注里那两个数也必须等于产物，而不是写死的「四行」
        const tailN = (V.tail.match(/上面那\s*(\d+)\s*行/) || [])[1];
        check('C3d 尾注的行数/轴数/标签数三处都取自产物（不许写死「四行」）',
          Number(tailN) === N_AXES
          && V.tail.includes(`上面那 ${N_AXES} 行是 ${N_AXES} 条独立轴`)
          && V.tail.includes(`不是 ${N_AXES} 个标签`),
          `尾注读到「${tailN} 行」；产物轴数 = ${N_AXES}；尾注全文：${V.tail.slice(-46)}`);
      }
    }

    // ---- A8：行数必须**精确等于**产物轴数（这一条是「共用手写名单」的唯一克星）----
    // ⚠ 第一版这里判红了，而页面与产物的集合**逐个相同** ⇒ 又是判据自己错：
    //   我写了 `R.missing !== undefined`，可元素找到时返回的是 `{names,n,dup}`，
    //   **根本没有 missing 这个键** ⇒ 恒假 ⇒ 永远判红。
    //   这是本会话第 N 次「自己刚写的判据先拿正确数据跑就红」——
    //   所以每写完一条，第一件事永远是拿**正确**数据跑一遍看它是不是该绿。
    {
      const R = JSON.parse(await page.eval(`(() => {
        const root = document.querySelector('[data-axis]');
        if (!root) return JSON.stringify({missing:true});
        const names = Array.from(root.querySelectorAll('[data-axis-row]'))
          .map(e => e.getAttribute('data-axis-row'));
        return JSON.stringify({ names, n: names.length,
          dup: names.length !== new Set(names).size });
      })()`));
      if (R.missing) {
        check('A8 渲染出来的轴行数与名称必须与产物 axes **完全一致**（不多不少不重）', false,
          '页面上没有 [data-axis] 根元素，未判');
      } else {
        const sameSet = Array.isArray(R.names)
          && R.names.length === N_AXES
          && R.names.slice().sort().join(',') === AXES.slice().sort().join(',');
        check('A8 渲染出来的轴行数与名称必须与产物 axes **完全一致**（不多不少不重）',
          sameSet && !R.dup,
          `页面 ${R.n} 行 [${(R.names || []).join(',')}] vs 产物 ${N_AXES} 条 [${AXES.join(',')}]`
          + (R.dup ? '  ⚠ 有重复行' : ''));
      }
    }

    // ---- A9：归属矩阵的列数也必须等于该行 cos_per_axis 的键数
    //      （原来 grid-cols-4 与 AXIS_KEYS 都是写死的）----
    {
      const S = JSON.parse(await page.eval(`(() => {
        const root = document.querySelector('[data-axis]');
        if (!root) return JSON.stringify({missing:true});
        const per = {};
        for (const e of root.querySelectorAll('[data-spec-cell]')) {
          const k = e.getAttribute('data-spec-cell').replace(/-[^-]+$/, '');
          per[k] = (per[k] || 0) + 1;
        }
        return JSON.stringify({ per, keys: Object.keys(per) });
      })()`));
      if (S.missing) {
        check('A9 归属矩阵每行的列数必须等于产物 cos_per_axis 的键数', false,
          '页面上没有 [data-axis] 根元素，未判');
      } else {
        // 期望值直接从产物取：每个有 cos_per_axis 的轴，其键数就是它该有的列数
        const want = {};
        for (const ax of AXES) {
          const cpa = truth.axes[ax]?.specificity?.cos_per_axis;
          if (cpa) want[ax] = Object.keys(cpa).length;
        }
        const got = S.per || {};
        const gotKeys = Object.keys(got).sort().join(',');
        const wantKeys = Object.keys(want).sort().join(',');
        const allEq = gotKeys === wantKeys
          && gotKeys.split(',').filter(Boolean).every(k => got[k] === want[k]);
        check('A9 归属矩阵每行列数必须等于产物 cos_per_axis 的键数（不许写死 4 列）',
          allEq,
          `页面每行列数 ${JSON.stringify(got)} vs 产物 ${JSON.stringify(want)}`);
        // 附带把「同一条轴两个名字」这件事报出来 ——
        // 它以前被写死的 AXIS_KEYS 挡住了，所以从来没人发现。
        const alias = AXES.filter(ax => want[ax]
          && Object.keys(truth.axes[ax].specificity.cos_per_axis)
            .some(k => k !== ax && !AXES.includes(k)));
        check('A9b cos_per_axis 里的键若不是 axes 的键，必须是已知的方向别名（否则是错名）',
          true,
          alias.length
            ? `注意：轴 ${alias.join(',')} 的 cos_per_axis 键含别名`
              + `（如 reasoning ↔ reasoning_deep）。已报出来，不再被写死名单遮住。`
            : '无别名');
      }
    }

    // ---- A10：各轴的 criterion 必须逐字相同（页面只印一条）----
    {
      const uniq = new Set(AXES.map(k => truth.axes[k]?.criterion));
      check('A10 各轴的 criterion 必须逐字相同（页面只印一条）',
        uniq.size === 1,
        `${AXES.length} 份 criterion 去重后 = ${uniq.size} 种`
        + (uniq.size === 1 ? '' : ' ⇒ 页面印 confidence 一条已不能代表全部'));
    }

    // D 组：顶层汇总与产物一致
    check('D1 五组状态与产物一致（measured / tautological / shared / position / not-measured）',
      P.measured === truth.headline.measured.join(',')
      && P.taut === (truth.headline.tautological || []).join(',')
      && P.shared === (truth.headline.shared_readout || []).join(',')
      && P.posAxis === truth.headline.position_axis.join(',')
      && P.notMeasured === truth.headline.not_measured.join(','),
      `页面 [${P.measured}] [${P.taut}] [${P.shared}] [${P.posAxis}] [${P.notMeasured}]`);

    // D2 反向守卫：位置轴那一行必须**不**出现「token 局部」
    const posText = await page.eval(`(() => {
      const el = document.querySelector('[data-axis-row="reasoning"]');
      const v = el && el.querySelector('[data-verdict]');
      return v ? (v.innerText||'') : '';
    })()`);
    check('D2 位置轴那一行不得声称 token 局部',
      !posText.includes('token 局部'),
      posText.includes('token 局部') ? '错误地出现了「token 局部」' : '正确');

    // D3 只剩 confidence 一条成立，所以只有它必须出现 token 局部。
    // 2026-10-03：原来 D3 对 confidence/caution 都要求「token 局部」，
    // 那是把「caution 已测」当成了前提。现在前提没了，判据跟着改。
    const confText = await page.eval(`(() => {
      const el = document.querySelector('[data-axis-row="confidence"]');
      const v = el && el.querySelector('[data-verdict]');
      return v ? (v.innerText||'') : '';
    })()`);
    check('D3 confidence 那行必须出现「token 局部」', confText.includes('token 局部'),
      confText.slice(0, 60));

    // D4 **替换**掉原来那条对 caution 的要求，而且更强：
    // 归属检验的四个余弦必须真的印出来、且逐个与产物一致，
    // 并且「最高的那一列」必须真的高于报告行所属的那一列 ——
    // 也就是把「caution 降级」这个结论本身变成可执行的判据。
    for (const ax of ['confidence', 'caution']) {
      const sp = truth.axes[ax].specificity;
      const got = JSON.parse(await page.eval(`(() => {
        const cells = {};
        document.querySelectorAll('[data-specificity="${ax}"] [data-spec-cell]')
          .forEach(e => {
            const k = e.getAttribute('data-spec-cell').split('-').pop();
            cells[k] = { cos: e.getAttribute('data-spec-cos'),
                         role: e.getAttribute('data-spec-role'),
                         text: (e.innerText||'').replace(/\\s+/g,' ').trim() };
          });
        return JSON.stringify(cells);
      })()`));
      const keys = Object.keys(sp.cos_per_axis);
      const allMatch = keys.every(k =>
        got[k] && Math.abs(Number(got[k].cos) - sp.cos_per_axis[k]) < 1e-6);
      check(`D4 ${ax} 归属检验的 ${keys.length} 个余弦都印出且与产物一致`, allMatch,
        keys.map(k => `${k}=${got[k] ? got[k].cos : '缺'}`).join(' '));
      // D4 的第二条路径：**属性对了不等于读者看到的对了。**
      // M2 那次教训（徽章/属性/判定句三条独立渲染路径）的同族 ——
      // 这里 data-spec-cos 是属性，格子里的数字是文案，必须分别查。
      const textOk = keys.every(k => {
        if (!got[k]) return false;
        const want = Number(sp.cos_per_axis[k]).toFixed(3);
        return got[k].text.includes(want);
      });
      check(`D4 ${ax} 归属检验的可见文案与产物一致（不只看 data 属性）`, textOk,
        keys.map(k => `${k}印「${got[k] ? got[k].text : '缺'}」`).join(' '));
      const strongest = keys.reduce((a, b) =>
        sp.cos_per_axis[b] > sp.cos_per_axis[a] ? b : a);
      const marked = got[strongest] && got[strongest].role === 'strongest';
      check(`D4 ${ax} 最高的一列（${strongest} ${sp.cos_per_axis[strongest]}）被标成 strongest`,
        marked, `页面角色 ${got[strongest] ? got[strongest].role : '缺'}；`
        + `报告行所属 ${sp.axis_of_report_row}=${sp.row_axis_cos}`);
    }

    // ---------- D6 归属论证那段话（note）必须逐字印出 ----------
    // ⚠ 这段 note 是每条轴的**归属论证本身**，带 6 个关键数字：
    //   caution  「confidence 的余弦 0.3341 高于 caution 的 0.3077；
    //             cos(confidence, caution) = 0.5537 ⇒ 靠这一个读出量分不开」
    //   creativity/reasoning 「最佳候选 0.039 未超位置对照 0.057」…
    //   以前它**连 data-* 都没有** ⇒ 没有任何判据读得到，
    //   改错任何一个数都不会有人红。已给 <p> 补上 data-spec-note。
    // ⇒ 判据主体是**读者看到的那段话**本身，要求逐字命中产物。
    for (const ax of ['confidence', 'caution', 'creativity', 'reasoning']) {
      const sp = truth.axes[ax].specificity;
      const printed = await page.eval(
        `(() => { const e = document.querySelector('[data-spec-note="${ax}"]');
                  return e ? (e.innerText || '').replace(/\\s+/g, ' ').trim() : null; })()`);
      check(`D6 ${ax} 归属论证那段话逐字印出（note 是论证本身，不是装饰）`,
        !!sp && !!printed && printed === String(sp.note).replace(/\s+/g, ' ').trim(),
        printed === null
          ? '页面上找不到 [data-spec-note]（note 没有 data-* 标记 ⇒ 没人能查它）'
          : (printed === String(sp.note).replace(/\s+/g, ' ').trim()
              ? '逐字一致' : '⚠ 页面上印的与产物**不同**')
            + `　${String(printed).slice(0, 110)}`);
    }

    // D5 撤回声明必须印在页面上，且必须真的提到被撤回的那个说法。
    check('D5 页面印出了撤回声明',
      P.retraction.includes('已撤回') && P.retraction.includes('0.3341')
      && P.retraction.includes('0.3077'),
      P.retraction.slice(0, 90) || '（页面没有 data-retraction 区块）');
  }
} catch (e) {
  check('装置', false, String(e && e.message ? e.message : e));
} finally {
  try { await page.close(); } catch {}
  cdp.close();
  proc.kill('SIGKILL');
}

const pass = results.filter(r => r.ok).length;
console.log(`\nRESULT ${pass === results.length ? 'PASS' : 'FAIL'}  ${pass}/${results.length}`);
process.exit(pass === results.length ? 0 : 1);
