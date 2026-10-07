import { readFileSync } from 'node:fs';
import { launch, Page, CDP } from './cdp_client.mjs';

/**
 * 探针：第十二笔 —— 「删掉重复标记」这件事**在渲染层真的发生了吗**。
 *
 * 背景：这一轮从 SubspacePanel / AxisReadoutPanel 删掉 8 个 `data-*`，
 * 它们都是同一个事实的第二个来源（行级 data-diagonal/floor/decay、
 * data-lower-bound-old、data-bound-caveat-text、data-decay-label、
 * data-control-delta100、data-strongest）。
 *
 * ⚠ 为什么不能用「grep 源码里没有它们」当证据：
 *   源码里没有 ≠ 渲染出来没有。构建缓存、SSR 产物、chunk 复用都可能
 *   让旧标记继续出现在 DOM 里。所以这一条只认**活页面 DOM 里的精确计数**。
 *
 * ⚠ 为什么必须是**精确**计数而不是「> 0」：
 *   `> 0` 只证明「至少有一个」，删到只剩一个也照样绿。
 *   而「恰好 0 个」是这批判据的主张 ⇒ 用 === 0 判；
 *   「恰好 N 个」也一样用 === N，且 N 从产物里数出来，不写死。
 *
 * 判红优先怀疑判据：探针自己有 bug 时输出的是一个看起来很像事实的数字。
 *   所以每条都打印它实际读到的值，而不是只打印 PASS/FAIL。
 */
const URL = process.env.BV_URL || 'http://127.0.0.1:10410/';
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_dd_' + process.pid;
const sleep = ms => new Promise(r => setTimeout(r, ms));

const sub = JSON.parse(readFileSync(
  '/Users/zhourui/code/steer3d/frontend/public/latent/data/readable_subspace.json', 'utf8'));
const NROW = sub.surface_directions.length;

const results = [];
const check = (name, ok, detail) => {
  results.push({ name, ok: !!ok });
  console.log(`[${ok ? 'PASS' : 'FAIL'}] ${name}: ${detail}`);
};

const { proc, version } = await launch({
  port: 9497, userDataDir: PROFILE, windowSize: '1700,1300', url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});

  // ---- X0 存活前置 + 早退出（与九个判据脚本同形）----
  {
    const L = JSON.parse(await page.eval(`(() => JSON.stringify({
      href: location.href,
      bodyLen: (document.body.innerText || '').length,
      outcome: (document.querySelector('[data-outcome]') || {getAttribute: () => ''})
                 .getAttribute('data-outcome') || '',
      canvases: document.querySelectorAll('canvas').length,
      scripts: document.querySelectorAll('script[src]').length,
    }))()`));
    const alive = /127\.0\.0\.1/.test(L.href) && L.bodyLen > 0 && L.scripts >= 1;
    if (!alive) {
      console.log(`[FAIL] X0 存活前置: ${JSON.stringify(L)}`);
      console.log('RESULT FAIL  0/1 一条都没跑（页面没加载，不是被测对象有问题）');
      process.exitCode = 1;
      throw new Error('x0');
    }
    console.log(`[PASS] X0 存活前置: href=${L.href} bodyLen=${L.bodyLen} script[src]=${L.scripts}`);
    results.push({ name: 'X0', ok: true });
  }

  // 等 SubspacePanel 真正挂载（data-subspace="ready"）—— 不是「页面在」而是「这块在」
  let ready = false;
  for (let i = 0; i < 60; i++) {
    ready = await page.eval(`!!document.querySelector('[data-subspace="ready"]')`);
    if (ready) break;
    await sleep(500);
  }
  if (!ready) {
    console.log('[FAIL] 前置：SubspacePanel 未挂载（data-subspace="ready" 60 次轮询都没出现）');
    console.log('RESULT FAIL  1/1');
    process.exitCode = 1;
    throw new Error('not-mounted');
  }

  // ---- 读一次活 DOM ----
  // ⚠ 第一版这里有**两个探针自身的 bug**，判出的 5 条红全是假的：
  //   ① vals() 用 `e.getAttribute(sel.slice(1, -1))`，而对 `[data-kind="diagonal"]`
  //      切出来的是 `data-kind="diagonal"`（整条选择器）不是属性名 ⇒ 四个 D3 全 null。
  //      只有 `[data-decay-value]` 恰好切对了，所以只有它「通过」—— 那种
  //      一半真一半假的输出看起来最像事实。
  //   ② 选择器是**全页作用域**，而 HeldoutPanel.tsx:242 也发 data-kind="floor"
  //      ⇒ 4 行 + 3 个对照格 = 7，于是「恰好 4 个」判红。
  //      与「子串匹配作用域必须与被核量一致」同族：这里错的是**选择器作用域**。
  // ⇒ 修法：属性名显式传，不再从选择器反推；
  //   「已删」按**全页**判 0（这个主张本来就该是「DOM 里任何地方都没有」，
  //   若按面板子树判就会因为作用域太窄而**恒真**、判据越权）；
  //   「保活」按**面板子树**判精确条数（不跨面板）。
  const D = JSON.parse(await page.eval(`(() => {
    const root = document.querySelector('[data-subspace="ready"]');
    if (!root) return JSON.stringify({ error: 'no-root' });
    const pcnt = sel => document.querySelectorAll(sel).length;          // 全页
    const scnt = sel => root.querySelectorAll(sel).length;              // 面板子树
    const svals = (sel, attr) => Array.from(root.querySelectorAll(sel))
      .map(e => e.getAttribute(attr));
    return JSON.stringify({
      panelsRead: ['[data-subspace="ready"] 子树（保活项）', '全页（已删项）'],
      removed: {
        'data-diagonal':          pcnt('[data-diagonal]'),
        'data-floor':             pcnt('[data-floor]'),
        'data-decay':             pcnt('[data-decay]'),
        'data-decay-label':       pcnt('[data-decay-label]'),
        'data-lower-bound-old':   pcnt('[data-lower-bound-old]'),
        'data-bound-caveat-text': pcnt('[data-bound-caveat-text]'),
        'data-control-delta100':  pcnt('[data-control-delta100]'),
        'data-strongest':         pcnt('[data-strongest]'),
      },
      kept: {
        rows:         scnt('[data-subspace-row]'),
        decayValue:   svals('[data-decay-value]', 'data-decay-value'),
        diag:         svals('[data-kind="diagonal"]', 'data-value'),
        floor:        svals('[data-kind="floor"]', 'data-value'),
        offdiag:      svals('[data-kind="offdiag"]', 'data-value'),
        maxAxis:      svals('[data-kind="max-axis"]', 'data-value'),
        boundOld:     svals('[data-bound-old]', 'data-bound-old'),
        controlDelta: svals('[data-control-delta]', 'data-control-delta'),
        controlValue: svals('[data-control-value]', 'data-control-value'),
      },
    });
  })()`));

  if (D.error) {
    console.log('[FAIL] 前置：读 DOM 时 root 已不在（面板被卸载？）');
    console.log('RESULT FAIL  1/1');
    process.exitCode = 1;
    throw new Error('root-gone');
  }
  console.log('[info] 取样范围：' + JSON.stringify(D.panelsRead));
  console.log('[info] 活 DOM 全页实读（已删项）：' + JSON.stringify(D.removed));
  console.log('[info] 活 DOM 保活项计数：' + JSON.stringify({
    rows: D.kept.rows, decayValue: D.kept.decayValue.length, diag: D.kept.diag.length,
    floor: D.kept.floor.length, offdiag: D.kept.offdiag.length, maxAxis: D.kept.maxAxis.length,
    boundOld: D.kept.boundOld.length, controlDelta: D.kept.controlDelta.length,
  }));

  // ---- D1：八个已删属性在活 DOM 里必须**恰好 0 个** ----
  for (const [k, n] of Object.entries(D.removed)) {
    check(`D1 ${k} 在渲染层恰好 0 个`, n === 0, `实测 ${n} 个`);
  }

  // ---- D2：保活的唯一来源必须还在，且数量与产物一致（精确等号）----
  check('D2 行数 = 产物 surface_directions 长度', D.kept.rows === NROW,
    `页面 ${D.kept.rows} / 产物 ${NROW}`);
  for (const k of ['decayValue', 'diag', 'floor', 'offdiag', 'maxAxis']) {
    check(`D2 data-${k} 恰好 ${NROW} 个`, D.kept[k].length === NROW,
      `实测 ${D.kept[k].length} 个`);
  }

  // ---- D3：保活来源的**值**必须与产物逐个相等（不是「有个值」）----
  const eq = (got, want) => got.length === want.length && got.every((v, i) => v === String(want[i]));
  const wantDecay = sub.surface_directions.map(r => r.decay_x20);
  const wantDiag  = sub.surface_directions.map(r => r.diagnostic.diagonal);
  const wantFloor = sub.surface_directions.map(r => r.diagnostic.floor);
  const wantOff   = sub.surface_directions.map(r => r.diagnostic.offdiag_worst);
  const wantMaxA  = sub.surface_directions.map(r => r.diagnostic.max_cos_to_named);
  check('D3 data-decay-value 逐个等于 decay_x20', eq(D.kept.decayValue, wantDecay),
    `页面 ${JSON.stringify(D.kept.decayValue)} vs 产物 ${JSON.stringify(wantDecay)}`);
  check('D3 data-kind=diagonal 逐个等于 diagonal', eq(D.kept.diag, wantDiag),
    `页面 ${JSON.stringify(D.kept.diag)} vs 产物 ${JSON.stringify(wantDiag)}`);
  check('D3 data-kind=floor 逐个等于 floor', eq(D.kept.floor, wantFloor),
    `页面 ${JSON.stringify(D.kept.floor)} vs 产物 ${JSON.stringify(wantFloor)}`);
  check('D3 data-kind=offdiag 逐个等于 offdiag_worst', eq(D.kept.offdiag, wantOff),
    `页面 ${JSON.stringify(D.kept.offdiag)} vs 产物 ${JSON.stringify(wantOff)}`);
  check('D3 data-kind=max-axis 逐个等于 max_cos_to_named', eq(D.kept.maxAxis, wantMaxA),
    `页面 ${JSON.stringify(D.kept.maxAxis)} vs 产物 ${JSON.stringify(wantMaxA)}`);
  check('D3 data-bound-old = 旧下界', D.kept.boundOld.length === 1
    && D.kept.boundOld[0] === String(sub.headline.readable_directions_lower_bound_old),
    `页面 ${JSON.stringify(D.kept.boundOld)} vs 产物 ${sub.headline.readable_directions_lower_bound_old}`);
  check('D3 data-control-value = control.delta[100]', D.kept.controlValue.length === 1
    && D.kept.controlValue[0] === String(sub.control.delta['100']),
    `页面 ${JSON.stringify(D.kept.controlValue)} vs 产物 ${sub.control.delta['100']}`);

  // ---- D4：可见文字里那些被删属性的**值**仍然印着（删属性 ≠ 删事实）----
  // ⚠ needle 必须是**足够长**的片段：我第一版写 innerText.includes('12')，
  //   而 12 在这块面板里到处都是（12 个字符、0.12、下界旧值…）⇒ 恒真，等于没判。
  //   短值必然被邻近的相同值喂饱，所以只判整句/四位小数这种够长的 token。
  const txt = await page.eval(`document.querySelector('[data-subspace="ready"]').innerText`);
  const mustAppear = [
    ['旧下界那句整句', `它是 ${sub.headline.readable_directions_lower_bound_old} 条`],
    ['对照 Δ=100 四位小数', '0.7087'],
  ];
  for (const [label, needle] of mustAppear) {
    check(`D4 可见文字里仍有 ${label}`, txt.includes(needle),
      `needle="${needle}" innerText.includes=${txt.includes(needle)}`);
  }

  const passed = results.filter(r => r.ok).length;
  const total = results.length;
  console.log(`RESULT ${passed === total ? 'PASS' : 'FAIL'}  ${passed}/${total}`);
  if (passed !== total) process.exitCode = 1;
} catch (e) {
  if (String(e.message) !== 'x0' && String(e.message) !== 'not-mounted') console.log(e);
} finally {
  try { proc.kill('SIGKILL'); } catch {}
}
