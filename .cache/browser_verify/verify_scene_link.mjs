import { readFileSync, readdirSync } from 'node:fs';
import { launch, Page, CDP } from './cdp_client.mjs';

/**
 * 判据：3D 珠子与逐层推导链的双向联动。
 *
 * 共享状态只有一个（`lib/store` 里的 `focusedStep`），所以两个方向都是
 * 「谁改了它，另一边跟着变」。这一支验**链 → 3D** 那条：
 * 拖推导链的滑块 ⇒ 3D 上聚焦态标签出现，且步号与链一致。
 *
 * 外部真值：token 文本取自 sidecar JSON（`datasets/aime_qwen3_1p7b_16k_fp16/aime/`），
 * 不取页面自己报的字符串。
 *
 * 验不了的（不假装验了）：**珠子上的光线拾取点击**。WebGL 画的东西在沙箱里
 * 读不到像素，我无法证明 `onClick` 真的被射线命中。那条只验到「接线存在」。
 */
const URL = process.env.BV_URL || 'http://127.0.0.1:10370/';
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_scene_' + process.pid;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const DATA = '/Users/zhourui/code/steer3d/datasets/aime_qwen3_1p7b_16k_fp16/aime';

const results = [];
// ⚠⚠ 第三十三笔之十一：加**第三态**「前提未建立 ⇒ 未判」。
//   原来只有 pass/fail 两态，于是 J3b（等 3D 数据流停下来）失败之后，
//   J4/J6/J8/J9a/J10 仍然照跑 —— 它们的**前提正是「流已停」**，
//   于是每个数都是流式阶段的快照，红的到底是页面还是读数没赶上，
//   **分不出来**。
//   实测：同一条脚本连跑三次是 12/13、11/13、7/9 —— 后一次里
//   `data-scene-window-high/low` 已经读成 undefined。
//   ⇒ 前提不成立时给一个数，会被误读成判决（与 run() 的 NORUN 同一族）。
//   ⇒ 三态分开计数，汇总行把「未判」**显式印出来**，不许混进分母假装验过。
const PRECOND = { failed: false, why: '' };
// ⚠⚠ `indep=true` = 「这条**与前提无关**」，前提不成立时它照样该判。
//   第一版我把一把开关盖住后面所有判据，结果 J9（读 Scene3D.tsx 源码、
//   验 onClick 接线，**根本不碰运行时**）也被标成「未判」。
//   ⇒ 一条判据被判成「没判」，可能是「确实不能判」也可能是「被我一起盖住了」。
//     后者更坏：它把**能判的**也一起藏起来了，而这与「前提不成立要诚实」
//     是相反的方向。⇒ 前提只影响**依赖它**的那些，逐条点名，不许一刀切。
const check = (name, ok, detail, indep) => {
  if (PRECOND.failed && !indep) {
    results.push({ name, ok: false, state: 'precond' });
    console.log(`[未判 ] ${name}: ${PRECOND.why}`);
    return;
  }
  results.push({ name, ok: !!ok, state: ok ? 'pass' : 'fail' });
  console.log(`[${ok ? 'PASS' : 'FAIL'}] ${name}: ${detail}`);
};
const precondFailed = why => { PRECOND.failed = true; PRECOND.why = why; };
// 前提检查自己超时时，它**不是判红** —— 它是「没等停」。
//   原来它记成 FAIL，于是「环境慢」被读成「3D 坏了」，
//   整条脚本 exit 1、链里判红。⇒ 单独记成 precond。
const checkPrecond = (name, ok, detail, why) => {
  if (ok) {
    results.push({ name, ok: true, state: 'pass' });
    console.log(`[PASS] ${name}: ${detail}`);
  } else {
    results.push({ name, ok: false, state: 'precond' });
    console.log(`[未判 ] ${name}: ${detail}`);
    console.log(`　　　　（前提未建立：${why}）`);
  }
};

// sidecar：step -> token
const sidecars = readdirSync(DATA).filter(f => f.endsWith('.json'));
const tokenOf = (traj, step) => {
  const f = sidecars.find(s => s.startsWith(traj));
  if (!f) return null;
  const j = JSON.parse(readFileSync(`${DATA}/${f}`, 'utf8'));
  const t = (j.tokens || []).find(x => x.step_id === step);
  return t ? t.token : null;
};

// ⚠ 第三十三笔之十：默认**不开**。设 `STEER3D_WEBGL=1` 才给 Chrome
//   软件光栅那两个 flag（`cdp_client.mjs` 的 `extraArgs`，默认空 ⇒ 行为不变）。
//
//   为什么加这个开关：本脚本从第三十二笔起一直报 `SKIP 8/8`，
//   理由写的是「本环境没有 WebGL，页面走 2D 降级」。
//   而实测（`probe_webgl_flags.mjs`）：**只加两个 flag 就能拿到 WebGL 2.0**
//   （renderer = ANGLE / SwiftShader driver，maxTex 8192）。
//   ⇒ 那句理由只对「**没传 flag**」成立，不是环境事实。
//
//   ⚠ 打开它 ≠ 「3D 验过了」。软件光栅只保证能画，不保证画出来对；
//     而且这一支的判据**从来没在 3D 分支上跑过**（全是 2D 下写的），
//     所以第一次打开很可能报红 —— 那要分清是页面缺陷还是判据缺陷。
const WEBGL_FLAGS = process.env.STEER3D_WEBGL === '1'
  ? ['--use-angle=swiftshader', '--enable-unsafe-swiftshader']
  : [];

const { proc, version } = await launch({
  port: 9485, userDataDir: PROFILE, windowSize: '1700,1100', url: 'about:blank',
  extraArgs: WEBGL_FLAGS,
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  await sleep(14000);

  // ---- 环境前置条件：没有 WebGL 就无法验 3D ----
  // 这个沙箱的 Chromium 报 hasWebgl2=false / hasWebgl1=false，于是页面渲染的是
  // Scene3DFallback，**Scene3D 的代码根本不挂载**。
  // 此时判据全红是**假红**（红的不是页面，是环境）。
  // 所以必须先探 WebGL，缺了就 SKIP 而不是 FAIL ——
  // 判据「恒红」和「变异没进页面」是同一类错误：红的对象不是被测对象。
  // 不要用 ?render=webgl 强开：use-webgl.ts 的注释说得很清楚，
  // three.js 在建上下文时 throw，会把整棵 React 树连带面板一起掀掉。
  const wgl = JSON.parse(await page.eval(`(() => {
    const c = document.createElement('canvas');
    const gl = c.getContext('webgl2') || c.getContext('webgl');
    return JSON.stringify({
      hasWebgl: !!gl,
      branch: document.querySelector('[data-testid=scene3d-webgl]') ? 'webgl'
            : document.querySelector('[data-testid=scene3d-probing]') ? 'probing'
            : 'fallback',
    });
  })()`));

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

  // 不依赖 WebGL 的一条：源码接线自证
  const src0 = readFileSync(
    '/Users/zhourui/code/steer3d/frontend/components/Scene3D.tsx', 'utf8');
  const wired0 = /onClick=\{\(e\) => \{[\s\S]{0,200}?setFocusedStep\(f\.step_id\)/.test(src0);
  const hasOutNote = /data-scene-focus-miss/.test(src0);
  const hasProgress = /data-scene-loaded/.test(src0);

  if (!wgl.hasWebgl || wgl.branch !== 'webgl') {
    check('E1 源码里 onClick → setFocusedStep(f.step_id) 已接线', wired0, String(wired0));
    check('E2 源码里窗口外提示已实现', hasOutNote, String(hasOutNote));
    check('E3 源码里加载进度读数已实现', hasProgress, String(hasProgress));
    check('E4 页面确实走了 2D fallback（说明不是页面坏了）',
      wgl.branch === 'fallback' || wgl.branch === 'probing',
      `WebGL=${wgl.hasWebgl} 分支=${wgl.branch}`);

    // J11 降级画布的 proof-of-paint —— C4 报的 6 个未读标记就是它们
    //   （data-painted / -rendered-points / -on-screen-points / -extent-maxabs /
    //     -extent-fraction / -has-entropy），它们由 Scene3DFallback 的 rAF 绘制循环写入。
    //   为什么这条必须在这里、而且**不能 SKIP**：
    //     3D 像素在本环境验不了（C3 把那 14 个 WebGL 条件块标为「既不算死引用，
    //     也不许算通过」），但**降级路径恰恰是本环境唯一真正跑起来的那条**。
    //     ⇒ 「画布上真的有珠子」是这里唯一能自动取证的画布证据，
    //       而它此前无人读 ⇒ 一个空白画布不会有任何判据红。
    //   ⚠ 这 6 个属性在 draw() 里逐帧写，所以必须**等**它跑起来，不能只查一次。
    {
      let paint = null;
      for (let i = 0; i < 12; i++) {
        // ⚠⚠ 第二十六笔：这里原来写的是
        //   const g = n => c.getAttribute('data-' + n);
        //   ... g('on-screen-points') / g('extent-maxabs') / ...
        // 运行时**读的是对的**，但 C4 是拿正则 `data-[a-z0-9-]+` 扫判据源码的
        // ⇒ 拼名的那四个名字在源码里**一个都不字面存在** ⇒ C4 把它们报成
        // 「页面上有、没人读过」的覆盖缺口。子智能体审计把它标成假阳性，是对的：
        // 判据确实读了，只是以 C4 看不见的写法读的。
        // 处置不是去改 C4 的正则（那会让扫描器猜运行时语义），而是**把这四个
        // 名字写出来**：C4 看得见，判据也确实读，两边都不用让步。
        paint = JSON.parse(await page.eval(`(() => {
          const cs = [...document.querySelectorAll('canvas')]
            .filter(c => c.getAttribute('data-painted') !== null
                      || c.getAttribute('data-rendered-points') !== null);
          const c = cs[0];
          if (!c) return JSON.stringify({ found: false });
          return JSON.stringify({
            found: true,
            painted: c.getAttribute('data-painted'),
            rendered: c.getAttribute('data-rendered-points'),
            onScreen: c.getAttribute('data-on-screen-points'),
            extentMaxabs: c.getAttribute('data-extent-maxabs'),
            extentFraction: c.getAttribute('data-extent-fraction'),
            hasEntropy: c.getAttribute('data-has-entropy'),
            layer: c.getAttribute('data-layer'),
          });
        })()`));
        // 退出条件从「属性出现了」改成「**画完了**」。
        // 原来 `rendered !== null` 在第一帧就成立，而 rAF 还在继续；
        // 改成同时要求 onScreen > 0，等画布真的稳定出可见点再取样。
        if (paint.found && paint.rendered !== null
            && Number(paint.onScreen) > 0) break;
        await new Promise(r => setTimeout(r, 900));
      }
      const nRendered = Number(paint && paint.rendered);
      const nOnScreen = Number(paint && paint.onScreen);
      check('J11 2D 降级画布必须自证「真的画过」（proof-of-paint 属性可读且点数 > 0）',
        !!(paint && paint.found) && paint.painted === '1'
        && Number.isFinite(nRendered) && nRendered > 0,
        paint && paint.found
          ? `painted=${paint.painted} rendered=${paint.rendered} onScreen=${paint.onScreen}`
            + ` extentMaxabs=${paint.extentMaxabs} extentFraction=${paint.extentFraction}`
            + ` hasEntropy=${paint.hasEntropy} layer=${paint.layer}`
          : '画布上没有任何 data-painted / data-rendered-points ⇒ 绘制循环没跑过，'
            + '或属性已被删（本环境 3D 验不了，这是唯一能自动取证的画布证据）');

      // ⚠⚠ 第二十六笔新增：J11 原来把上面那四个属性**只印在诊断行里**，
      //   断言只有 painted==='1' && rendered>0 ⇒ 「所有点都投影到屏外」
      //   （onScreen=0，屏幕上什么都没有）这一种坏法**照样绿**。
      //   而 onScreen 恰恰是「画布上真的有珠子」这句话唯一直接对应的那个数 ——
      //   rendered 数的是**算出来的**点，不是**看得见的**点。
      //   ⇒ 判据必须落在 onScreen 上。实测本环境 rendered=onScreen=193。
      check('J11b 画布上必须有**投在屏内**的点（rendered 数的是算出来的，onScreen 才是看得见的）',
        !!(paint && paint.found) && paint.painted === '1'
        && Number.isFinite(nOnScreen) && nOnScreen > 0
        && nOnScreen <= nRendered,
        paint && paint.found
          ? `onScreen=${paint.onScreen} / rendered=${paint.rendered}`
            + `（屏内占 ${nRendered > 0 ? (100 * nOnScreen / nRendered).toFixed(1) : '—'}%）`
            + ` extentFraction=${paint.extentFraction}`
          : '画布没找到，无法核屏内点数');

      // 那三个属性若为 null，说明绘制循环在写 data-painted 之前就断了
      // （或属性被改名）。getAttribute 对「已写入但值为空串」返回 ""，
      // 对「属性不存在」返回 null ⇒ 两者可区分，这条判的就是这个区别。
      const attrsPresent = paint && paint.found
        && paint.extentMaxabs !== null && paint.extentFraction !== null
        && paint.hasEntropy !== null && paint.layer !== null;
      check('J11c 轨迹范围/熵/层号三个属性都必须被写进 DOM（null = 绘制循环半途而废）',
        attrsPresent,
        paint && paint.found
          ? `data-extent-maxabs=${JSON.stringify(paint.extentMaxabs)}`
            + ` data-extent-fraction=${JSON.stringify(paint.extentFraction)}`
            + ` data-has-entropy=${JSON.stringify(paint.hasEntropy)}`
            + ` data-layer=${JSON.stringify(paint.layer)}`
          : '画布没找到');
    }

    const pass0 = results.filter(r => r.ok).length;
    const fail0 = results.length - pass0;
    // ⚠ 汇总行自己也不能撒谎。修之前这一支无论有没有红都印
    //   「RESULT SKIP n/m **源码级检查通过**」——
    //   于是「E0 判红（死页面）」与「全部通过」在最后一行长得一样。
    //   SKIP 只能用来表达「因环境不可验而跳过」，不能用来掩盖真红。
    console.log(fail0
      ? `\nRESULT FAIL  ${pass0}/${results.length}　有 ${fail0} 条判红，不能用 SKIP 解释`
      : `\nRESULT SKIP  ${pass0}/${results.length} 源码级检查通过`);
    if (!fail0) {
    console.log('原因：本浏览器**没有 WebGL**（hasWebgl2/1 均为 false），页面渲染的是');
    console.log('Scene3DFallback，Scene3D 的代码不会挂载 ⇒ 3D 联动在此环境**无法验证**。');
    console.log('这不是 FAIL：红的对象不是被测对象。请用有 WebGL 的普通 Chrome 复跑：');
    }
    console.log(`  BV_URL=${URL} node .cache/browser_verify/verify_scene_link.mjs`);
    cdp.close();
    proc.kill('SIGKILL');
    process.exit(2);
  }

  // ⚠️ 滑块必须**在推导链面板里**选。页面上至少有两个 range：
  // 推导链的步号滑块，和注入控件的**强度滑块**（min=0.25 max=4）。
  // 第一版用 document.querySelector('input[type=range]') 抓到了强度那个，
  // 于是 J3–J8 全红 —— 是判据选错元素，不是页面坏。
  const readBoth = `(() => {
    const badge = document.querySelector('[data-scene-focus]');
    const chain = document.querySelector('[data-derivation]');
    const scene = document.querySelector('[data-scene-loaded]');
    // ⚠⚠ 第三十三笔之十：data-scene-focus-miss 挂在**内层 <span>** 上
    //   （Scene3D.tsx:188），而 data-scene-focus-state 挂在外层 div（:171）。
    //   我原来两个都用 scene.getAttribute 读 ⇒ miss 恒为 null
    //   ⇒ J4 在**页面已经用可见文字明说「第 N 步不在 3D 窗口内」**的情况下
    //   仍然报红。这与第三十三笔之七 V5 是**同一族**：
    //   **判据读的是元素，不是属性** —— 属性在 A 上，判据却去 B 上读。
    const miss = document.querySelector('[data-scene-focus-miss]');
    const br = badge && badge.getBoundingClientRect();
    const sr = scene && scene.getBoundingClientRect();
    const slider = chain && chain.querySelector('input[type=range]');
    return JSON.stringify({
      badge: badge ? {
        step: badge.getAttribute('data-scene-focus-step'),
        token: badge.getAttribute('data-scene-focus-token'),
        text: (badge.innerText||'').replace(/\\s+/g,' ').trim(),
        w: Math.round(br.width), h: Math.round(br.height),
      } : null,
      chain: chain ? {
        state: chain.getAttribute('data-derivation'),
        traj: chain.getAttribute('data-traj'),
        step: chain.getAttribute('data-step-id'),
      } : null,
      scene: scene ? {
        loaded: Number(scene.getAttribute('data-scene-loaded')),
        low: Number(scene.getAttribute('data-scene-window-low')),
        high: Number(scene.getAttribute('data-scene-window-high')),
        focusState: scene.getAttribute('data-scene-focus-state'),
        focusMiss: miss ? miss.getAttribute('data-scene-focus-miss') : null,
        missText: miss ? (miss.innerText||'').replace(/\\s+/g,' ').trim() : null,
        text: (scene.innerText||'').replace(/\\s+/g,' ').trim(),
        w: Math.round(sr.width), h: Math.round(sr.height),
      } : null,
      hasRange: !!slider,
      rangeValue: slider?.value ?? null,
      rangeMin: slider?.min ?? null,
      rangeMax: slider?.max ?? null,
      allRangeCount: document.querySelectorAll('input[type=range]').length,
    });
  })()`;

  const setSlider = `(() => {
    const chain = document.querySelector('[data-derivation]');
    const el = chain && chain.querySelector('input[type=range]');
    if (!el) return JSON.stringify({missing:true});
    const target = ${'${TARGET}'};
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, 'value').set;
    setter.call(el, String(target));
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    return JSON.stringify({target, lo: parseInt(el.min,10), hi: parseInt(el.max,10)});
  })()`;

  const s0 = JSON.parse(await page.eval(readBoth));
  // 不要求 ready：流式加载时链会先落在 out-of-window，那也是正常态
  check('J1 推导链面板在（ready 或流式中的 out-of-window 都算）',
    !!s0.chain && !!s0.chain.state,
    s0.chain ? `state=${s0.chain.state} traj=${s0.chain.traj} step=${s0.chain.step}`
             : '推导链不在');
  check('J2 推导链的步号滑块存在（页面上共 '
    + `${s0.allRangeCount} 个 range，必须选对那个）`,
    s0.hasRange,
    s0.hasRange ? `链内滑块 min=${s0.rangeMin} max=${s0.rangeMax}` : '链内无 range');
  check('J3 3D 报出了自己的加载进度与可见窗口',
    !!s0.scene && s0.scene.loaded > 0,
    s0.scene ? `已加载 ${s0.scene.loaded} 步，可见 ${s0.scene.low}–${s0.scene.high}`
             : '场景没有进度读数');

  // ---- 分支 A：把链拖到 3D 窗口**外** ----
  // 3D 只画最后 80 帧，而数据流可能远没到 784 步。窗口外时页面必须**明说**，
  // 静默什么都不显示是最坏的一种（读者会以为联动坏了）。
  await page.eval(setSlider.replace('${TARGET}', String(s0.rangeMax)));
  await sleep(1500);
  const sOut = JSON.parse(await page.eval(readBoth));
  const outOk = (sOut.scene?.focusState === 'out-of-window'
    && sOut.scene?.focusMiss != null)
    || (sOut.badge != null && Number(sOut.badge.step) === Number(s0.rangeMax));
  check('J4 步号在 3D 窗口外时，页面明说（出珠子标签或出「不在窗口」提示）',
    outOk,
    sOut.scene
      ? `focusState=${sOut.scene.focusState} focusMiss=${sOut.scene.focusMiss} 「${sOut.scene.text}」`
      : '场景读数消失');
  check('J5 窗口外时不出现错误的珠子标签',
    !(sOut.badge != null && Number(sOut.badge.step) !== Number(s0.rangeMax)),
    sOut.badge ? `标签 step=${sOut.badge.step}` : '无标签（正确）');

  // ---- 分支 B：把链拖到 3D 窗口**内** ----
  // ⚠⚠ 第三十三笔之十：**先等数据流停下来，再测联动。**
  //   实测这个 3D 场景是**边解码边画**的：J3 读到「已加载 208 步」，
  //   几秒后 J4 读到「已加载 242 步」—— 每秒前进约 30 步，
  //   而窗口只有 80 帧宽 ⇒ 我设进去的步号会在**一秒内**滑出窗口。
  //   这不是页面坏，是**被测对象在动**；判据必须在它停下来之后再问。
  //   做法：轮询 data-scene-loaded，连续 3 次读数不变就认为流结束。
  // ⚠⚠⚠ 第三十三笔之十一：**预算按实测重标**。
  //   原来 60000ms 是在**空闲机器**上标定的（40s 稳定在 385 步）。
  //   机器一忙就超时 —— 实测连跑三次：
  //     负载下：等 60000ms 仍在增长（769 / 721 步）→ 报 FAIL
  //     空闲时：等 40000ms 稳定在 385 步
  //   同一个脚本、同一台服务器、同一份数据，差别只在机器忙不忙
  //   ⇒ 那个 60 秒不是「3D 有问题」，是**预算不够**。
  //   150s 的来历：空闲 40s × 3.5 的余量。⚠ 这仍会拖慢链，
  //   所以**超时也不能报 FAIL**，要报「前提未建立」（见上）。
  const waitStreamIdle = async (maxMs = 150000) => {
    let last = -1, stable = 0, waited = 0;
    while (waited < maxMs) {
      const c = JSON.parse(await page.eval(readBoth));
      const n = c.scene ? c.scene.loaded : -1;
      stable = (n === last && n > 0) ? stable + 1 : 0;
      last = n;
      if (stable >= 3) return { idle: true, waited, loaded: n };
      await sleep(1000); waited += 1000;
    }
    return { idle: false, waited, loaded: last };
  };
  const idle = await waitStreamIdle();
  // ⚠ 用 checkPrecond 而不是 check：等不到停**不是判红**，
  //   它是「本环境这一轮没等停」。记成 FAIL 会让「环境慢」被读成「3D 坏了」。
  checkPrecond('J3b 3D 的数据流会**停下来**（联动判据的前提：窗口不再滚）',
    idle.idle,
    idle.idle ? `等了 ${idle.waited}ms 后稳定在 ${idle.loaded} 步`
              : `等了 ${idle.waited}ms 仍在增长（${idle.loaded} 步）`
                + `——下面的联动判据在流式阶段本来就读不稳`,
    `软件光栅慢，150s 预算内没等停（已到 ${idle.loaded} 步仍在涨）`);
  if (!idle.idle) {
    precondFailed(`3D 数据流在 ${idle.waited}ms 内没停下来（已到 ${idle.loaded} 步仍在涨）`
      + `——本环境是软件光栅，慢；这不是「3D 坏了」的判决`);
    console.log('⚠ 前提未建立：下面**依赖「流已停」**的判据（J4/J6/J7/J8/J9a/J10）'
      + '一律记为未判，不记红也不记绿。');
    console.log('　（不依赖前提的照判：J9 读的是 Scene3D.tsx 源码，不碰运行时。）');
  }

  // ⚠⚠⚠ 第三十三笔之十二：这里原来写的是 `if (s.badge) return s;`。
  //
  //   那是**拿到「有标签」就返回** —— 而 `data-scene-focus` 是 3D 的
  //   **聚焦标签**，上一次拖动留下的那个**不会立刻消失**。
  //   ⇒ 第二次拖动一进去，第一次轮询就捞到了**上一轮的旧标签**并直接返回。
  //   实测症状：J10 印 `752 -> 752`（两次拿到同一个步号），
  //   而 nudge 明明是 1 与 6，目标相差 5 步。
  //   ⇒ 修法：必须等到 badge 的步号**等于这次设的目标**才返回；
  //     步号对不上的那些一律当作**陈旧读数**继续等，并把次数报出来。
  //
  //   （与「读快照 vs 等它停」同族：不是被测对象不动，是**读数没赶上**。
  //     但症状在汇总行里长得一模一样——都印成 `FAIL`。）
  const focusInWindow = async (nudge) => {
    let stale = 0, last = null;
    for (let attempt = 0; attempt < 3; attempt++) {
      const cur = JSON.parse(await page.eval(readBoth));
      if (!cur.scene || !cur.scene.high) return null;
      const target = Math.max(0, Math.min(cur.scene.high, cur.rangeMax) - nudge);
      const set = JSON.parse(await page.eval(setSlider.replace('${TARGET}', String(target))));
      if (set && set.missing) return null;
      for (let w = 0; w < 14; w++) {
        await sleep(400);
        const s = JSON.parse(await page.eval(readBoth));
        last = s;
        if (s.badge && Number(s.badge.step) === target) {
          return { ...s, target, stale, sliderMoved: s.chain?.step === String(target) };
        }
        // 有标签但步号不是这次的目标 ⇒ **陈旧读数**，继续等
        if (s.badge) stale++;
      }
    }
    return last ? { ...last, target: null, stale, sliderMoved: null } : null;
  };
  const s1 = await focusInWindow(1);
  const inWin = s1?.badge?.step ?? s1?.chain?.step ?? null;

  check('J6 步号在 3D 窗口内时，珠子标签出现',
    !!s1?.badge,
    s1?.badge ? `step=${s1.badge.step} token=${JSON.stringify(s1.badge.token)} 「${s1.badge.text}」`
            : `流停后试了 3 轮（每轮重读窗口 + 轮询 5.6s）仍无 [data-scene-focus]；`
              + `最后一次窗口 ${s1?.scene?.low}–${s1?.scene?.high}`);
  if (s1?.badge) {
    check('J7 标签有非零包围盒（不是隐藏元素）',
      s1.badge.w > 0 && s1.badge.h > 0, `${s1.badge.w}x${s1.badge.h}px`);
    check('J8 3D 与链指向同一个步号（联动一致）',
      s1.badge.step === s1.chain?.step,
      `3D=${s1.badge.step} 链=${s1.chain?.step} 目标=${inWin}`);
    const want = s1.chain?.traj ? tokenOf(s1.chain.traj, Number(s1.badge.step)) : null;
    check('J9a 标签里的 token 与 sidecar 真值一致',
      want != null && s1.badge.token === want,
      `页面 ${JSON.stringify(s1.badge.token)} / sidecar ${JSON.stringify(want)}`);
  }

  // 再拖一次，验证「不是只跟了一次」
  // ⚠ 与 J6 同一个坑：3D 窗口会滚，所以第二次也必须**重读窗口**再选步号，
  //   且要与第一次选到**不同**的那个（靠 nudge 不同保证）。
  const s2 = await focusInWindow(6);
  const inWin2 = s2?.badge?.step ?? null;
  check('J10 第二次拖动，3D 标签跟着变（不是只跟了一次）',
    !!s2?.badge && !!s1?.badge && s2.badge.step !== s1.badge.step,
    // ⚠⚠ 第三十三笔之十一：这里原来写的是 `${s1.badge?.step}` ——
    //   可选链只护住了 `.badge`，**没护住 `s1` 本身**。
    //   s1 为 null（没拿到标签）时照样抛 TypeError，
    //   于是整段被 `catch` 吞成「装置: Cannot read properties of null
    //   (reading 'badge')」——**红的是一个异常，不是判决**。
    //   ⇒ 可选链要一路写到根：s1?.badge?.step。
    `${s1?.badge?.step} -> ${s2?.badge?.step}`
    + `　目标 ${s1?.target} / ${s2?.target}`
    + `　陈旧读数 ${s1?.stale} / ${s2?.stale} 次`
    + `　滑杆真的动了吗 ${s1?.sliderMoved} / ${s2?.sliderMoved}`
    + `${s2?.badge ? '' : '（第二次没拿到标签）'}`);

  // 接线自证：源码里确实有 onClick 调 setFocusedStep（光线拾取本身验不了）
  const src = readFileSync(
    '/Users/zhourui/code/steer3d/frontend/components/Scene3D.tsx', 'utf8');
  const wired = /onClick=\{\(e\) => \{[\s\S]{0,200}?setFocusedStep\(f\.step_id\)/.test(src);
  check('J9 珠子上的 onClick 已接线到 setFocusedStep（只验接线，不验射线拾取）',
    wired, wired ? '源码里 onClick → setFocusedStep(f.step_id)' : '未找到接线',
    // ⚠ indep=true：这条读的是**源码**（readFileSync），不碰运行时，
    //   所以「3D 数据流没停」与它无关。第一版漏了这个 flag，
    //   它被一并盖成「未判」—— 那就把**能判的也藏起来了**，
    //   与「前提不成立要诚实」正好是相反的方向。
    true);
} catch (e) {
  check('装置', false, String(e && e.message ? e.message : e));
} finally {
  try { await page.close(); } catch {}
  cdp.close();
  proc.kill('SIGKILL');
}

// ⚠⚠ 第三十三笔之十一：三态分开计数。
//   「未判」**不进分母**（它压根没被判），但**必须显式印出来** ——
//   混进分母会让人以为跑过了，藏起来会让 8/8 看起来比 8/9 强。
const judged = results.filter(r => r.state !== 'precond');
const unjudged = results.filter(r => r.state === 'precond');
const pass = judged.filter(r => r.ok).length;
const fail = judged.length - pass;
if (fail) {
  console.log(`\nRESULT FAIL  ${pass}/${judged.length}　有 ${fail} 条判红`
    + (unjudged.length ? `　另有 ${unjudged.length} 条因前提未建立未判` : ''));
} else if (unjudged.length) {
  console.log(`\nRESULT SKIP  ${pass}/${judged.length}　另有 ${unjudged.length} 条因前提未建立**未判**`);
} else {
  console.log(`\nRESULT PASS  ${pass}/${judged.length}`);
}
if (unjudged.length) {
  console.log(`　未判的 ${unjudged.length} 条：${unjudged.map(r => r.name.split(' ')[0]).join('、')}`);
  console.log('　原因：' + PRECOND.why);
}
console.log('注：珠子上的**光线拾取点击**未验（沙箱读不到 WebGL 像素），只验到接线。');
process.exit(fail ? 1 : 0);
