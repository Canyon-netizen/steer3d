import { launch, CDP, Page } from './cdp_client.mjs';
import { mkdirSync } from 'node:fs';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const fs = await import('node:fs');
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_shot_deriv';
mkdirSync(PROFILE, { recursive: true });
const { proc, version } = await launch({ port: 9479, userDataDir: PROFILE, windowSize: '1600,1000', url: 'about:blank' });
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
await page.send('Runtime.enable'); await page.send('Page.enable');
await page.send('Page.navigate', { url: process.env.T3D_URL || 'http://127.0.0.1:22226/' });
await page.waitForEvent('Page.loadEventFired', 60000).catch(()=>{});
for (let i=0;i<30;i++){
  if(await page.eval(`(()=>{const e=document.querySelector('[data-derivation="ready"]');
    return !!(e && e.querySelectorAll('rect[data-layer]').length===28);})()`)) break;
  await sleep(600);
}
await sleep(1200);
let s = await page.send('Page.captureScreenshot', { format: 'png' });
fs.writeFileSync('/Users/zhourui/code/steer3d/.cache/browser_verify/derivation_panel.png', Buffer.from(s.data,'base64'));
console.log('面板截图写完');
try { proc.kill('SIGKILL'); } catch(e) {}
process.exit(0);
