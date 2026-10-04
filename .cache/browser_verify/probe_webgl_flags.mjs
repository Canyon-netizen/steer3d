/**
 * 能不能让沙箱里的 headless shell 拿到 WebGL？（3D 联动一直因此无法验证）
 *
 * ## 为什么值得试
 *
 * `cdp_client.mjs` 拉的是 Playwright 的 **chrome-headless-shell**，
 * 它不带 GPU 栈 ⇒ `canvas.getContext('webgl2')` 返回 null
 * ⇒ `verify_scene_link` 恒 SKIP 8/8，3D 那一整块**从来没被验过**。
 *
 * headless shell 默认关掉 WebGL，但 Chromium 有**软件光栅**这条路：
 * `--use-angle=swiftshader --enable-unsafe-swiftshader --ignore-gpu-blocklist`
 * ⇒ 真的用 CPU 画。如果这条通，3D 联动就能在沙箱里验，不必等用户开真机。
 *
 * ## 它验什么
 * 只验「能不能拿到上下文 + 报的是什么 renderer」，不验像素。
 * 拿到上下文只是**必要条件**；像素对不对是另一回事。
 */
import { spawn } from 'child_process';
import { mkdirSync, writeFileSync } from 'fs';
import { CDP, CHROME, Page } from './cdp_client.mjs';

const PORT = 9850;
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_gl_' + process.pid;
mkdirSync(PROFILE, { recursive: true });

const VARIANTS = [
  ['基线（无额外 flag）', []],
  ['swiftshader 三件套', [
    '--use-gl=angle', '--use-angle=swiftshader',
    '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist',
  ]],
  ['只加 swiftshader 两个', [
    '--use-angle=swiftshader', '--enable-unsafe-swiftshader',
  ]],
  ['老式软件 GL', [
    '--use-gl=swiftshader', '--enable-unsafe-swiftshader',
  ]],
];

const sleep = ms => new Promise(r => setTimeout(r, ms));

async function probe(label, extra) {
  const port = PORT + VARIANTS.findIndex(v => v[0] === label);
  const args = [
    '--single-process',
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${PROFILE}_${port}`,
    '--window-size=800,600',
    '--no-first-run', '--no-default-browser-check',
    ...extra,
    'about:blank',
  ];
  const proc = spawn(CHROME, args, { stdio: ['ignore', 'pipe', 'pipe'] });
  let stderr = '';
  proc.stderr.on('data', d => { stderr += d.toString(); });
  try {
    // 等 devtools 起来
    let ver = null;
    for (let i = 0; i < 40 && !ver; i++) {
      await sleep(500);
      try {
        ver = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json();
      } catch { /* 还没起来 */ }
    }
    if (!ver) return { label, ok: false, why: 'devtools 没起来', stderr: stderr.slice(0, 200) };
    const cdp = await CDP.connect(ver.webSocketDebuggerUrl);
    const page = await Page.create(cdp);
    await page.send('Page.navigate', { url: 'data:text/html,<canvas id=c></canvas>' });
    await page.waitForEvent('Page.loadEventFired', 20000).catch(() => {});
    const r = await page.eval(`(() => {
      const c = document.getElementById('c');
      const gl = c.getContext('webgl2') || c.getContext('webgl');
      if (!gl) return { has: false };
      const dbg = gl.getExtension('WEBGL_debug_renderer_info');
      return { has: true, version: gl.getParameter(gl.VERSION),
               renderer: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL)
                             : gl.getParameter(gl.RENDERER),
               maxTex: gl.getParameter(gl.MAX_TEXTURE_SIZE) };
    })()`);
    try { await cdp.send('Browser.close'); } catch { /* ignore */ }
    return { label, ok: !!r.has, info: r };
  } catch (e) {
    return { label, ok: false, why: e.message, stderr: stderr.slice(0, 200) };
  } finally {
    try { proc.kill(); } catch { /* ignore */ }
  }
}

const out = [];
for (const [label, extra] of VARIANTS) {
  const r = await probe(label, extra);
  out.push(r);
  console.log('%s %s', r.ok ? '✅' : '❌', label);
  if (r.ok) console.log('     %s ｜ renderer = %s ｜ maxTex = %s',
    r.info.version, r.info.renderer, r.info.maxTex);
  else console.log('     %s %s', r.why || '', r.stderr || '');
}
const anyOk = out.some(r => r.ok);
writeFileSync('/Users/zhourui/code/steer3d/.cache/logs/gl_probe.json',
              JSON.stringify(out, null, 2));
console.log('\n结论：%s', anyOk
  ? '沙箱里能拿到 WebGL ⇒ 3D 联动**可以**在这里验（还需真去验一次像素）'
  : '这四组 flag 都拿不到 WebGL ⇒ 3D 仍只能由用户在真机 Chrome 验收');
process.exit(0);
