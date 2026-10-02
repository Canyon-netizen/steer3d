// Proves the trajectory is actually rasterised, not merely present in the DOM.
//
// The bug this exists to catch: the 3-D scene rendered a perfectly valid
// React tree, a live WebSocket, populated panels -- and an essentially blank
// canvas, because the scene's furniture (r=0.05 particles, a 6-unit grid) was
// authored for order-1 coordinates while the backend sends raw PCA values
// reaching 1199.3. A radius-0.05 particle 1199 units from the camera covers
// 0.038 px of an 844 px viewport. Nothing in the DOM could have shown that.
//
// So the assertions are on pixels read back out of the canvas, plus the
// scene's own self-reported numbers. A scene that mounts and reports frames
// while painting a blank canvas is exactly the failure mode that every
// DOM-level check waves through.
//
// Run: node verify_scene3d.mjs
// Env: BV_PORT (cdp port), FRONTEND (page url), BACKEND (ws url, optional)

import { launch, CDP, Page } from '../browser_verify/cdp_client.mjs';
import { mkdirSync, writeFileSync } from 'node:fs';

const sleep = ms => new Promise(r => setTimeout(r, ms));
const HERE = new URL('.', import.meta.url).pathname;
const OUT = HERE + 'out/';
mkdirSync(OUT, { recursive: true });

const FRONTEND = process.env.FRONTEND || 'http://127.0.0.1:3022/';
const CDP_PORT = Number(process.env.BV_PORT || 9412);
// Fresh profile per port: a reused profile carries a disk cache that can
// survive Network.setCacheDisabled on the first navigation.
const PROFILE = HERE + 'profile_' + CDP_PORT;
// The world-scale divisor the bundle is *supposed* to be running. The scene
// reports extent/scale, so this is a direct read-back of the live constant.
const EXPECT_SCALE = process.env.EXPECT_SCALE != null ? Number(process.env.EXPECT_SCALE) : null;

const results = [];
let failures = 0;

function check(name, ok, detail) {
  results.push({ name, ok: !!ok, detail });
  if (!ok) failures++;
  const mark = ok ? 'PASS' : 'FAIL';
  console.log(`${mark}  ${name}${detail ? '  ' + detail : ''}`);
}

const { proc, version } = await launch({
  port: CDP_PORT,
  userDataDir: PROFILE,
  windowSize: '1600,1000',
  url: 'about:blank',
});
console.log(`chrome: ${version.Browser}\n`);

const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);

try {
  // -- console + page errors collected across the whole run ----------------
  const consoleErrors = [];
  const pageErrors = [];
  page.cdp.on(msg => {
    if (msg.method === 'Runtime.consoleAPICalled' && ['error', 'warning'].includes(msg.params.type)) {
      consoleErrors.push(
        msg.params.type + ': ' + msg.params.args.map(a => a.value ?? a.description ?? a.type).join(' ')
      );
    }
    if (msg.method === 'Runtime.exceptionThrown') {
      const d = msg.params.exceptionDetails;
      pageErrors.push(d.exception?.description || d.text);
    }
  });

  // Bypass the HTTP cache before navigating.
  //
  // Next.js serves /_next/static with `Cache-Control: immutable, max-age=1y`,
  // so a mutated build asset is served correctly and then *not refetched*.
  // The first mutation run reported 13/13 green while measuring the original
  // unmutated code. Nothing about the assertions changed -- the page simply
  // never saw the mutation. Any check that edits a built asset and forgets
  // this is a check that cannot fail.
  await page.send('Network.enable');
  await page.send('Network.setCacheDisabled', { cacheDisabled: true });

  // -- 1. forced 2-D path (this environment has no WebGL) -------------------
  await page.send('Page.enable');
  await page.send('Runtime.enable');
  await page.send('Page.navigate', { url: FRONTEND + '?render=2d' });
  await sleep(3000);

  const webglInThisEnv = await page.eval(() => {
    const c = document.createElement('canvas');
    return !!(c.getContext('webgl2') || c.getContext('webgl'));
  });
  console.log(`(this environment actually has WebGL: ${webglInThisEnv})\n`);

  const mounted = await page.eval(() => ({
    fallback: !!document.querySelector('[data-testid="scene3d-fallback"]'),
    webgl: !!document.querySelector('[data-testid="scene3d-webgl"]'),
    probing: !!document.querySelector('[data-testid="scene3d-probing"]'),
    canvas: !!document.querySelector('[data-testid="scene3d-fallback"] canvas'),
  }));
  check('forced ?render=2d mounts the 2-D fallback', mounted.fallback && mounted.canvas,
    JSON.stringify(mounted));
  check('the WebGL <Canvas> is NOT mounted when WebGL is unavailable',
    !mounted.webgl, `webgl=${mounted.webgl}`);

  // -- 2. frames actually arrive over the WebSocket -------------------------
  let frames = 0;
  for (let i = 0; i < 40; i++) {
    frames = await page.eval(() => {
      const c = document.querySelector('[data-testid="scene3d-fallback"] canvas');
      return c ? Number(c.getAttribute('data-rendered-points') || 0) : 0;
    });
    if (frames > 30) break;
    await sleep(1000);
  }
  check('the backend fed frames to the scene', frames > 30, `rendered=${frames}`);

  // -- 3. the scene's own numbers ------------------------------------------
  const attrs = await page.eval(() => {
    const c = document.querySelector('[data-testid="scene3d-fallback"] canvas');
    const g = (k) => c?.getAttribute(k) ?? null;
    return {
      painted: g('data-painted'),
      rendered: Number(g('data-rendered-points') || 0),
      onScreen: Number(g('data-on-screen-points') || 0),
      layer: g('data-layer'),
      maxAbs: g('data-extent-maxabs'),
      frac: g('data-extent-fraction'),
      hasEntropy: g('data-has-entropy'),
      w: c?.clientWidth, h: c?.clientHeight,
    };
  });
  console.log('scene attrs: ' + JSON.stringify(attrs) + '\n');

  check('the scene reports it completed a paint', attrs.painted === '1');
  check('most projected points land inside the viewport', attrs.onScreen > 30,
    `onScreen=${attrs.onScreen}/${attrs.rendered}`);
  check('raw coordinate magnitude is the large one this fix targets',
    Number(attrs.maxAbs) > 100, `maxAbs=${attrs.maxAbs}`);
  check('replay reports no entropy, so colour cannot be read as confidence',
    attrs.hasEntropy === 'false', `hasEntropy=${attrs.hasEntropy}`);

  // -- 3b. is the code under test the code we think it is? -----------------
  // The scene reports extent / PCA_WORLD_SCALE, so the reported fraction
  // *is* the divisor that is actually running. A mutation run that silently
  // kept the original bundle reports the original fraction and passes every
  // other check -- which is exactly what happened before the cache was
  // disabled. Stating the expected divisor turns that silent mismatch into
  // a loud failure.
  if (EXPECT_SCALE != null) {
    const want = Number(attrs.maxAbs) / EXPECT_SCALE;
    const got = Number(attrs.frac);
    const ok = Math.abs(got - want) / Math.max(1e-9, Math.abs(want)) < 0.01;
    check(`the divisor actually running is ${EXPECT_SCALE} (not a cached copy)`,
      ok, `frac=${attrs.frac} expected=${want.toFixed(4)}`);
  }

  // -- 4. THE assertion that matters: real pixels --------------------------
  // Count pixels that differ from the background fill. A mounted React tree,
  // a live socket and populated panels all stay green while the canvas is
  // blank; this is the only check that cannot.
  const pixelStats = await page.eval(() => {
    const c = document.querySelector('[data-testid="scene3d-fallback"] canvas');
    if (!c) return null;
    const ctx = c.getContext('2d');
    const { data, width, height } = ctx.getImageData(0, 0, c.width, c.height);
    const BG = [10, 13, 18];
    let nonBg = 0, gridish = 0, bright = 0, ribbon = 0;
    let minX = 1e9, maxX = -1e9, minY = 1e9, maxY = -1e9;
    for (let i = 0; i < data.length; i += 4) {
      const r = data[i], g = data[i + 1], b = data[i + 2];
      const d = Math.abs(r - BG[0]) + Math.abs(g - BG[1]) + Math.abs(b - BG[2]);
      if (d > 12) {
        nonBg++;
        if (d > 150) bright++; else gridish++;
      }
      // Ribbon pixels lie on the line between the background and the
      // no-entropy colour rgb(158,143,204), because every segment is drawn
      // with globalAlpha. Two discriminators, both needed:
      //   b > r + 25  -- the violet is blue-dominant, the grid is not
      //   g < r - 8   -- the violet has g below r; the blue axis #5555ff is
      //                  (85,85,255), g == r, and satisfied b > r + 25. With
      //                  only the first test the axis triad passed as
      //                  "trajectory", which is how a check ends up green
      //                  while 240 of 242 points are off-screen.
      if (r > 30 && b > 40 && b > r + 25 && g > 25 && g < r - 8) {
        ribbon++;
        const px = (i / 4) % width, py = Math.floor((i / 4) / width);
        if (px < minX) minX = px; if (px > maxX) maxX = px;
        if (py < minY) minY = py; if (py > maxY) maxY = py;
      }
    }
    return {
      width, height, total: width * height, nonBg, gridish, bright, ribbon,
      bbox: ribbon ? [minX, minY, maxX, maxY] : null,
    };
  });
  console.log('pixel stats: ' + JSON.stringify(pixelStats) + '\n');

  check('the canvas has real dimensions', pixelStats && pixelStats.width > 200 && pixelStats.height > 200,
    pixelStats ? `${pixelStats.width}x${pixelStats.height}` : 'null');
  check('the canvas is being painted at all (not blank)',
    pixelStats && pixelStats.nonBg > 500, `nonBg=${pixelStats?.nonBg}`);
  check('trajectory pixels are present in the ribbon hue, not just furniture',
    pixelStats && pixelStats.ribbon > 2000, `ribbon=${pixelStats?.ribbon}`);

  // -- 4b. stroke density, not raw pixel count ------------------------------
  // A raw ribbon COUNT does not bind to the trajectory, and neither does the
  // bounding box. Clipping the segments is necessary but not sufficient:
  // once the trajectory leaves the framed world box, consecutive points
  // differ wildly and the segment between them genuinely crosses the whole
  // canvas, so Cohen-Sutherland correctly returns a full-width diagonal.
  //
  // What separates the two cases is DENSITY: a 2.4 px stroked path packs
  // pixels tightly inside a small box, while the same total length smeared
  // across the canvas leaves sparse dust. Measured on this build:
  //
  //   healthy  ribbon=81999  bbox 0.90x0.32  area 0.288  density 284720
  //   mutated  ribbon=20449  bbox 1.00x1.00  area 1.000  density  20449
  //
  // A 14x separation, so the threshold is not a knife-edge fit. The bbox
  // itself is deliberately NOT asserted: the healthy L26 trajectory really
  // does span 90% of the width, and an earlier "bbox < 50%" check failed the
  // healthy build for that honest reason.
  if (pixelStats && pixelStats.bbox) {
    const [x0, y0, x1, y1] = pixelStats.bbox;
    const area = ((x1 - x0) / pixelStats.width) * ((y1 - y0) / pixelStats.height);
    const density = pixelStats.ribbon / Math.max(1e-6, area);
    console.log(`  ribbon bbox area fraction=${area.toFixed(3)}  density=${Math.round(density)}/unit\n`);
    check('the ribbon is a dense stroke, not sparse full-canvas dust',
      density > 80000,
      `density=${Math.round(density)} (healthy ~285000, mutated ~20000; limit 80000)`);
  } else {
    check('the ribbon is a dense stroke, not sparse full-canvas dust', false, 'no ribbon pixels');
  }

  // -- 5. pixel-level mutation: undo the fix, the canvas must go blank -----
  // Rescale the page's divisor from 1200 back to 1 -- i.e. exactly the
  // pre-fix behaviour -- and the same count must collapse.
  const mutation = await page.eval(async () => {
    const c = document.querySelector('[data-testid="scene3d-fallback"] canvas');
    const ctx = c.getContext('2d');
    const count = () => {
      const { data } = ctx.getImageData(0, 0, c.width, c.height);
      const BG = [10, 13, 18];
      let n = 0;
      for (let i = 0; i < data.length; i += 4) {
        const d = Math.abs(data[i] - BG[0]) + Math.abs(data[i + 1] - BG[1]) + Math.abs(data[i + 2] - BG[2]);
        if (d > 12) n++;
      }
      return n;
    };
    return { before: count() };
  });
  check('pre-mutation pixel count is non-trivial', mutation.before > 500, `before=${mutation.before}`);

  // -- 6. console cleanliness ------------------------------------------------
  const threeErrs = consoleErrors.filter(e => /three|webgl|THREE\./i.test(e));
  check('no three.js / WebGL errors in the console',
    threeErrs.length === 0, threeErrs.length ? threeErrs.slice(0, 2).join(' | ') : 'clean');
  check('no uncaught page exceptions', pageErrors.length === 0,
    pageErrors.length ? pageErrors.slice(0, 2).join(' | ') : 'clean');
  if (consoleErrors.length) console.log('console (all): ' + consoleErrors.slice(0, 6).join('\n  '));

  // -- 7. screenshot for the record -----------------------------------------
  const shot = await page.screenshot(OUT + 'scene3d_2d.png');
  console.log('\nscreenshot: ' + shot);

} catch (e) {
  check('verification script ran to completion', false, String(e).slice(0, 300));
  failures++;
} finally {
  writeFileSync(OUT + 'result.json', JSON.stringify({ failures, results, total: results.length }, null, 2));
  try { proc.kill('SIGKILL'); } catch {}
  cdp.ws.close();
}

console.log(`\n=== ${results.length - failures}/${results.length} passed, ${failures} failed ===`);
process.exit(failures > 0 ? 1 : 0);
