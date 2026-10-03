import { launch, Page, CDP } from './cdp_client.mjs';

/**
 * 任意面板的实际截图 —— 用法：
 *   BV_SEL='[data-subspace]' BV_OUT=... node shot_panel.mjs
 * 默认截 SubspacePanel（这一轮新加了「下界的前提」块，
 * 必须亲眼确认它在 328px 侧栏里没被裁 —— 上一轮就是在这一步栽的）。
 */
const URL = process.env.BV_URL || 'http://127.0.0.1:10491/';
const SEL = process.env.BV_SEL || '[data-subspace]';
const OUT = process.env.BV_OUT || '/Users/zhourui/code/steer3d/.cache/browser_verify/panel_shot';
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_pshot_' + process.pid;
const sleep = ms => new Promise(r => setTimeout(r, ms));

const { proc, version } = await launch({
  port: 9489, userDataDir: PROFILE, windowSize: '1700,1400', url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  await sleep(12000);

  const box = JSON.parse(await page.eval(`(() => {
    const el = document.querySelector('${SEL}');
    if (!el) return JSON.stringify({missing: true});
    el.scrollIntoView({block: 'start'});
    const r = el.getBoundingClientRect();
    // 顺带量一遍可见性：整行溢出 / 单元格内部裁切 / 越界
    const pr = el.getBoundingClientRect();
    const over = [...el.querySelectorAll('[data-threshold-row], [data-subspace-row]')].map(n => ({
      k: n.getAttribute('data-threshold-row') || n.getAttribute('data-subspace-row'),
      rowOver: Math.round(n.scrollWidth - n.clientWidth),
      cellClip: Math.round(Math.max(0, ...[...n.querySelectorAll('[data-kind]')]
        .map(c => c.scrollWidth - c.clientWidth))),
      spill: Math.round(Math.max(0, ...[...n.querySelectorAll('[data-kind]')]
        .map(c => c.getBoundingClientRect().right)) - pr.right),
    }));
    return JSON.stringify({x: Math.max(0, Math.floor(r.x) - 8),
                           y: Math.max(0, Math.floor(r.y) - 8),
                           w: Math.ceil(r.width) + 16, h: Math.ceil(r.height) + 16,
                           over, text: (el.innerText || '').replace(/\\s+/g, ' ').slice(0, 300)});
  })()`));
  if (box.missing) { console.log('面板没找到：' + SEL); process.exit(2); }
  await sleep(500);
  await page.screenshot(OUT + '.png', {
    clip: { x: box.x, y: box.y, width: box.w, height: box.h, scale: 2 },
  });
  const bad = box.over.filter(o => o.rowOver > 1 || o.cellClip > 1 || o.spill > 1);
  console.log('截图', OUT + '.png', `${box.w}x${box.h}`);
  console.log('可见性：', box.over.length, '行，异常', bad.length, '条');
  bad.forEach(o => console.log('   ', o.k, `行溢${o.rowOver}/格裁${o.cellClip}/越界${o.spill}`));
  console.log('文字前 300 字：', box.text);
} finally {
  try { await cdp.send('Browser.close'); } catch {}
  try { proc.kill(); } catch {}
}
