import { launch, Page, CDP } from './cdp_client.mjs';

/**
 * 功效块（[data-answer-power]）的实际截图 —— 只看代码不算验收。
 * 同时把整个干预结果面板截一张，确认新块没有把下面的答案表挤出视口。
 */
const URL = process.env.BV_URL || 'http://127.0.0.1:10470/';
const OUT = process.env.BV_OUT || '/Users/zhourui/code/steer3d/.cache/browser_verify/power';
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_shotpow_' + process.pid;
const sleep = ms => new Promise(r => setTimeout(r, ms));

const { proc, version } = await launch({
  port: 9491, userDataDir: PROFILE, windowSize: '1700,2600', url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  await sleep(13000);

  // 等面板真的 ready（它在 fetch 四份 JSON）
  for (let i = 0; i < 15; i++) {
    const s = await page.eval(
      `(document.querySelector('[data-outcome]')||{}).getAttribute`
      + `?document.querySelector('[data-outcome]').getAttribute('data-outcome'):''`);
    if (s === 'ready') break;
    await sleep(1200);
  }

  const box = JSON.parse(await page.eval(`(() => {
    const el = document.querySelector('[data-answer-power]');
    if (!el) return JSON.stringify({missing: true});
    el.scrollIntoView({block: 'center'});
    const r = el.getBoundingClientRect();
    return JSON.stringify({x: Math.max(0, Math.floor(r.x) - 8),
                           y: Math.max(0, Math.floor(r.y) - 8),
                           w: Math.ceil(r.width) + 16,
                           h: Math.ceil(r.height) + 16,
                           text: (el.innerText || '').replace(/\\s+/g, ' ')});
  })()`));
  if (box.missing) { console.log('功效块没找到'); process.exit(2); }
  await sleep(700);

  await page.screenshot(OUT + '_block.png', {
    clip: { x: box.x, y: box.y, width: box.w, height: box.h, scale: 2 },
  });
  console.log('功效块截图', OUT + '_block.png', `${box.w}x${box.h}`);

  // 整块面板，确认答案表还在下面
  const panel = JSON.parse(await page.eval(`(() => {
    const el = document.querySelector('[data-outcome]');
    el.scrollIntoView({block: 'start'});
    const r = el.getBoundingClientRect();
    return JSON.stringify({x: Math.max(0, Math.floor(r.x) - 8),
                           y: Math.max(0, Math.floor(r.y) - 8),
                           w: Math.ceil(r.width) + 16,
                           h: Math.ceil(r.height) + 16,
                           rows: el.querySelectorAll('[data-answer-rows] > div').length});
  })()`));
  await sleep(500);
  await page.screenshot(OUT + '_panel.png', {
    clip: { x: panel.x, y: panel.y, width: panel.w, height: panel.h, scale: 1 },
  });
  console.log('整面板截图', OUT + '_panel.png', `${panel.w}x${panel.h}`,
              '答案行数', panel.rows);

  console.log('\n功效块可见文字全文：');
  console.log(box.text);
} finally {
  try { await cdp.send('Browser.close'); } catch {}
  try { proc.kill(); } catch {}
}
