// 连接状态点是否诚实。⚠ 别用 /\bconnected\b/ 查：外层是模板字面量，
// \b 会被当成退格转义，正则变成 /(退格)connected(退格)/ —— 永远不匹配。
// 上一版探针就是这样读出 ABSENT 的，差一步就把它当成「状态点没渲染」。
import { launch, CDP, Page } from './cdp_client.mjs';
import { mkdirSync } from 'node:fs';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_conn';
mkdirSync(PROFILE, { recursive: true });
const { proc, version } = await launch({ port: 9475, userDataDir: PROFILE, windowSize: '1600,1000', url: 'about:blank' });
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
await page.send('Runtime.enable'); await page.send('Page.enable');
await page.send('Page.navigate', { url: process.env.T3D_URL || 'http://127.0.0.1:22226/' });
await page.waitForEvent('Page.loadEventFired', 60000).catch(()=>{});
for (const t of [2500, 5000, 8000]) {
  await sleep(t === 2500 ? 2500 : 2500);
  console.log(`t=${t}ms`, await page.eval(`(() => {
    const t = document.body.innerText || '';
    const dis = t.indexOf('disconnected') >= 0, con = t.indexOf('connected') >= 0;
    const dot = [...document.querySelectorAll('span')].find(s =>
      /w-2 h-2 rounded-full/.test(s.className || ''));
    return JSON.stringify({
      saysDisconnected: dis, saysConnected: con && !dis,
      dotClass: dot ? dot.className : 'DOT-ABSENT',
      dotRed: dot ? /bg-red-500/.test(dot.className) : null,
      dotGreen: dot ? /bg-green-400/.test(dot.className) : null,
      derivation: (document.querySelector('[data-derivation]')||{}).getAttribute
        ? document.querySelector('[data-derivation]').getAttribute('data-derivation') : 'ABSENT',
      bars: document.querySelectorAll('[data-derivation="ready"] rect').length,
    });
  })()`));
}
try { proc.kill('SIGKILL'); } catch(e) {}
process.exit(0);
