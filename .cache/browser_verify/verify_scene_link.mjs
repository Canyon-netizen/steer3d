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
const check = (name, ok, detail) => {
  results.push({ name, ok: !!ok });
  console.log(`[${ok ? 'PASS' : 'FAIL'}] ${name}: ${detail}`);
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

const { proc, version } = await launch({
  port: 9485, userDataDir: PROFILE, windowSize: '1700,1100', url: 'about:blank',
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
        paint = JSON.parse(await page.eval(`(() => {
          const cs = [...document.querySelectorAll('canvas')]
            .filter(c => c.getAttribute('data-painted') !== null
                      || c.getAttribute('data-rendered-points') !== null);
          const c = cs[0];
          if (!c) return JSON.stringify({ found: false });
          const g = n => c.getAttribute('data-' + n);
          return JSON.stringify({
            found: true, painted: g('painted'),
            rendered: g('rendered-points'), onScreen: g('on-screen-points'),
            extentMaxabs: g('extent-maxabs'), extentFraction: g('extent-fraction'),
            hasEntropy: g('has-entropy'), layer: g('layer'),
          });
        })()`));
        if (paint.found && paint.rendered !== null) break;
        await new Promise(r => setTimeout(r, 900));
      }
      const nRendered = Number(paint && paint.rendered);
      check('J11 2D 降级画布必须自证「真的画过」（proof-of-paint 属性可读且点数 > 0）',
        !!(paint && paint.found) && paint.painted === '1'
        && Number.isFinite(nRendered) && nRendered > 0,
        paint && paint.found
          ? `painted=${paint.painted} rendered=${paint.rendered} onScreen=${paint.onScreen}`
            + ` extentMaxabs=${paint.extentMaxabs} extentFraction=${paint.extentFraction}`
            + ` hasEntropy=${paint.hasEntropy} layer=${paint.layer}`
          : '画布上没有任何 data-painted / data-rendered-points ⇒ 绘制循环没跑过，'
            + '或属性已被删（本环境 3D 验不了，这是唯一能自动取证的画布证据）');
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
        focusMiss: scene.getAttribute('data-scene-focus-miss'),
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
  const inWin = Math.max(0, Math.min(s0.scene.high, s0.rangeMax));
  await page.eval(setSlider.replace('${TARGET}', String(inWin)));
  await sleep(1500);
  const s1 = JSON.parse(await page.eval(readBoth));

  check('J6 步号在 3D 窗口内时，珠子标签出现',
    !!s1.badge,
    s1.badge ? `step=${s1.badge.step} token=${JSON.stringify(s1.badge.token)} 「${s1.badge.text}」`
            : '未出现 [data-scene-focus]');
  if (s1.badge) {
    check('J7 标签有非零包围盒（不是隐藏元素）',
      s1.badge.w > 0 && s1.badge.h > 0, `${s1.badge.w}x${s1.badge.h}px`);
    check('J8 3D 与链指向同一个步号（联动一致）',
      s1.badge.step === s1.chain?.step,
      `3D=${s1.badge.step} 链=${s1.chain?.step} 目标=${inWin}`);
    const want = s1.chain?.traj ? tokenOf(s1.chain.traj, Number(s1.badge.step)) : null;
    check('J9 标签里的 token 与 sidecar 真值一致',
      want != null && s1.badge.token === want,
      `页面 ${JSON.stringify(s1.badge.token)} / sidecar ${JSON.stringify(want)}`);
  }

  // 再拖一次，验证「不是只跟了一次」
  const inWin2 = Math.max(0, Math.min(s0.scene.high, s0.rangeMax) - 1);
  await page.eval(setSlider.replace('${TARGET}', String(inWin2)));
  await sleep(1400);
  const s2 = JSON.parse(await page.eval(readBoth));
  check('J10 第二次拖动，3D 标签跟着变（不是只跟了一次）',
    !!s2.badge && !!s1.badge && s2.badge.step !== s1.badge.step,
    `${s1.badge?.step} -> ${s2.badge?.step}（目标 ${inWin2}）`);

  // 接线自证：源码里确实有 onClick 调 setFocusedStep（光线拾取本身验不了）
  const src = readFileSync(
    '/Users/zhourui/code/steer3d/frontend/components/Scene3D.tsx', 'utf8');
  const wired = /onClick=\{\(e\) => \{[\s\S]{0,200}?setFocusedStep\(f\.step_id\)/.test(src);
  check('J9 珠子上的 onClick 已接线到 setFocusedStep（只验接线，不验射线拾取）',
    wired, wired ? '源码里 onClick → setFocusedStep(f.step_id)' : '未找到接线');
} catch (e) {
  check('装置', false, String(e && e.message ? e.message : e));
} finally {
  try { await page.close(); } catch {}
  cdp.close();
  proc.kill('SIGKILL');
}

const pass = results.filter(r => r.ok).length;
console.log(`\nRESULT ${pass === results.length ? 'PASS' : 'FAIL'}  ${pass}/${results.length}`);
console.log('注：珠子上的**光线拾取点击**未验（沙箱读不到 WebGL 像素），只验到接线。');
process.exit(pass === results.length ? 0 : 1);
