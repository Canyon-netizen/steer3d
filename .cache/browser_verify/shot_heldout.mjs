import { launch, Page, CDP } from './cdp_client.mjs';

/**
 * HeldoutPanel 的实际截图 —— 只看代码不算验收。
 * 把面板滚进视口、截它自己的包围盒，再截一张带周边面板的定位图。
 */
const URL = process.env.BV_URL || 'http://127.0.0.1:10470/';
const OUT = process.env.BV_OUT || '/Users/zhourui/code/steer3d/.cache/browser_verify/heldout_shot';
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_shot_' + process.pid;
const sleep = ms => new Promise(r => setTimeout(r, ms));

const { proc, version } = await launch({
  port: 9488, userDataDir: PROFILE, windowSize: '1700,1400', url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  await sleep(12000);

  const box = JSON.parse(await page.eval(`(() => {
    const el = document.querySelector('[data-heldout]');
    if (!el) return JSON.stringify({missing: true});
    el.scrollIntoView({block: 'center'});
    const r = el.getBoundingClientRect();
    return JSON.stringify({x: Math.max(0, Math.floor(r.x) - 8),
                           y: Math.max(0, Math.floor(r.y) - 8),
                           w: Math.ceil(r.width) + 16,
                           h: Math.ceil(r.height) + 16,
                           text: (el.innerText || '').replace(/\\s+/g, ' ').slice(0, 400)});
  })()`));
  if (box.missing) { console.log('面板没找到'); process.exit(2); }
  await sleep(600);

  await page.screenshot(OUT + '_panel.png', {
    clip: { x: box.x, y: box.y, width: box.w, height: box.h, scale: 2 },
  });
  console.log('面板截图', OUT + '_panel.png', `${box.w}x${box.h}`);
  console.log('可见文字前 400 字：');
  console.log(box.text);
} finally {
  try { await cdp.send('Browser.close'); } catch {}
  try { proc.kill(); } catch {}
}
