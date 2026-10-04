import { launch, Page, CDP } from './cdp_client.mjs';

/**
 * **只读探针**：验一个前提 —— 加上 swiftshader 两个 flag 之后，
 * `scan_panel_coverage.py` 的 `CONDITIONAL_3D` 那 16 个标记
 * 到底会不会真的出现在 DOM 里。
 *
 * ⚠ 为什么要先验这个再改 C3 的声明：
 *   C3 那句「本环境无法验证」是**写在判据里的能力声明**。
 *   改它之前必须知道新能力**实际覆盖到哪一步**，
 *   否则就是把一句过期的话换成一句同样不准的话。
 * ⚠ 名单从 python 侧**抄一份**过来只为打印，不参与判决 ——
 *   两处各写一份名单正是本项目反复踩的坑（见 C2 的分页假设注释）。
 *   这里只用来「看一眼」，真判决仍以 python 侧那份为准。
 */
const URL = process.env.BV_URL || 'http://127.0.0.1:22208/';
const WEBGL = process.env.STEER3D_WEBGL === '1';
// ⚠⚠ 第一次只测了根页 ⇒ `data-bm*` 六条全部报「不在 DOM」。
//   而 `verify_backmap.mjs` 读的是 **LAT_URL** —— 这六个标记是
//   **latent 页**的 backmap 块，根页上本来就不该有。
//   ⇒ 「不在 DOM」这句话在只测一页时是**半句**，会让人误判成产品缺陷。
//   这与本项目反复出现的「一条判据只打开一页」是同一族（C2 的分页假设）。
const IS_LATENT = /\/latent\//.test(URL);
const READY_SEL = IS_LATENT ? '[data-dvblock]' : '[data-outcome="ready"]';
const READY_ATTR = IS_LATENT ? null : 'data-outcome';
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_cond_'
  + process.pid;
const sleep = ms => new Promise(r => setTimeout(r, ms));

const { proc, version } = await launch({
  port: 9600 + (process.pid % 240), userDataDir: PROFILE,
  windowSize: '1900,3200', url: 'about:blank',
  extraArgs: WEBGL
    ? ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] : [],
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  await sleep(12000);
  for (let i = 0; i < 20; i++) {
    const s = await page.eval(READY_ATTR
      ? `(document.querySelector('[${READY_ATTR}]')||{getAttribute:()=>''})`
        + `.getAttribute('${READY_ATTR}')||''`
      : `!!document.querySelector('${READY_SEL}')`);
    if (READY_ATTR ? s === 'ready' : s) break;
    await sleep(1200);
  }
  // 再给 3D 场景一点时间：软件光栅比真 GPU 慢，绘制是异步的
  await sleep(8000);

  const NAMES = ['data-scene-loaded', 'data-scene-focus', 'data-scene-focus-miss',
    'data-scene-focus-state', 'data-scene-focus-step', 'data-scene-focus-token',
    'data-scene-window-high', 'data-scene-window-low',
    'data-bmroot', 'data-bmstep', 'data-bmgrid', 'data-bmgridn',
    'data-drawn', 'data-frac', 'data-pfinal', 'data-ok'];

  const r = await page.eval(`(() => {
    const gl = (() => { const c = document.createElement('canvas');
      const g = c.getContext('webgl2') || c.getContext('webgl');
      if (!g) return 'NO CONTEXT';
      const d = g.getExtension('WEBGL_debug_renderer_info');
      return d ? String(g.getParameter(d.UNMASKED_RENDERER_WEBGL))
               : String(g.getParameter(g.RENDERER)); })();
    const out = {};
    for (const n of ${JSON.stringify(NAMES)}) {
      out[n] = document.querySelectorAll('[' + n + ']').length;
    }
    out['__webgl'] = gl;
    out['__fallback'] = document.querySelectorAll('[data-testid="scene3d-fallback"]').length;
    out['__canvas3d'] = document.querySelectorAll('canvas').length;
    return JSON.stringify(out);
  })()`);
  const o = JSON.parse(r);
  console.log(`== ${IS_LATENT ? 'latent 页' : '根页'}`
            + `　${WEBGL ? '开了 swiftshader' : '没开（默认）'} ==`);
  console.log('   WebGL 渲染器 : ' + o.__webgl);
  console.log('   canvas 数    : ' + o.__canvas3d
              + '　2D 降级块 data-testid=scene3d-fallback : ' + o.__fallback);
  let present = 0, absent = [];
  for (const n of NAMES) {
    if (o[n] > 0) { present++; console.log(`   ✓ ${n.padEnd(24)} ${o[n]}`); }
    else absent.push(n);
  }
  console.log(`\n   ⇒ ${present}/${NAMES.length} 个条件标记真的在 DOM 里`);
  if (absent.length) console.log('   仍不在：' + absent.join('、'));
} finally {
  try { if (cdp && cdp.close) await cdp.close(); } catch (e) { /* 收尾失败不影响判决 */ }
  proc.kill('SIGKILL');
}
