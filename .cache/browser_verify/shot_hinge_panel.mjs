import { launch, Page, CDP } from './cdp_client.mjs';

/**
 * 截图 HingePanel —— 因为内置浏览器在这个 3D 重页面上连续三次超时
 * （`BROWSER_OPERATION_TIMEOUT` 275s / `BROWSER_RESULT_TOO_LARGE` 64 KiB），
 * 拿不到任何视觉证据。而「判据过」与「页面看起来对」是两件事：
 * 判据读的是 innerText，证不了排版。
 *
 * 所以这里**截一张图**，让人眼过一遍。
 * 顺带把面板滚进视口，否则它在长长的 aside 底部、截不到。
 */
const URL = process.env.BV_URL || 'http://127.0.0.1:10370/';
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_shot_' + process.pid;
const OUT = process.env.SHOT_OUT
  || '/Users/zhourui/code/steer3d/.cache/mutbak/hinge_panel.png';
const sleep = ms => new Promise(r => setTimeout(r, ms));

const { proc, version } = await launch({
  port: 9492, userDataDir: PROFILE, windowSize: '1500,2200', url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  await sleep(10000);

  // ⚠ page.eval 已经把结果序列化成 JSON 字符串，**外面不要再套引号** ——
  //   第一版多套了一层，拿到的是 '"ready"'，于是 `st !== 'ready'` 恒真，
  //   脚本自己 print 了 `面板状态: "ready"` 然后又说「未 ready」。
  const st = await page.eval(`(() => {
    const e = document.querySelector('[data-hinge]');
    return e ? e.getAttribute('data-hinge') : null; })()`);
  console.log('面板状态:', st);
  if (st !== 'ready') { console.log('面板未 ready，不截图'); process.exit(6); }

  // 滚进视口 + 展开可能折叠的段（why 默认是折的）
  await page.eval(`(() => {
    const e = document.querySelector('[data-hinge]');
    e.scrollIntoView({block:'start'});
    const w = document.querySelector('[data-hinge="why"]');
    if (w) w.open = true;
    return true; })()`);
  await sleep(1200);

  const box = await page.eval(`(() => {
    const e = document.querySelector('[data-hinge]');
    e.scrollIntoView({block:'start'});
    const r = e.getBoundingClientRect();
    return {x: Math.max(0, r.x - 8), y: Math.max(0, r.y - 8),
            w: r.width + 16, h: r.height + 16}; })()`);
  await sleep(600);
  console.log('面板盒子:', JSON.stringify(box));

  const shot = await page.send('Page.captureScreenshot', {
    format: 'png',
    captureBeyondViewport: true,
    clip: { x: box.x, y: box.y, width: box.w, height: Math.min(box.h, 2400),
            scale: 1 },
  });
  const { writeFileSync } = await import('node:fs');
  writeFileSync(OUT, Buffer.from(shot.data, 'base64'));
  console.log('wrote', OUT);
} finally {
  await cdp.send('Browser.close').catch(() => {});
  proc.kill?.();
}
process.exit(0);
