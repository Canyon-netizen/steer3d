import { launch, CDP, Page } from '../browser_verify/cdp_client.mjs';
import { writeFileSync } from 'node:fs';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const reg = await (await fetch('http://127.0.0.1:8917/latent/models.json')).json();
const big = reg.models.find(m => m.d_model === 2048);
const { proc, version } = await launch({ port: 9387,
  userDataDir: '/Users/zhourui/code/steer3d/.cache/arreadout/fullprofile', url: 'about:blank' });
const cdp = await CDP.connect(`ws://127.0.0.1:9387/devtools/browser/${version.webSocketDebuggerUrl.split('/').pop()}`);
const page = await Page.create(cdp);
await page.send('Network.enable');
await page.send('Page.navigate', { url: `http://127.0.0.1:8917/latent/index.html?orient=reset&m=${big.id}` });
await page.waitForEvent('Page.loadEventFired', 40000);
await sleep(1200);
if (await page.eval(`(()=>{const o=document.getElementById('orientation');return !!(o&&getComputedStyle(o).display!=='none')})()`)) {
  await page.click('#orientClose'); await sleep(800);
}
// 首屏（未点任何 tab）
const first = await page.eval(`(()=>document.body.innerText||'')()`);
writeFileSync('.cache/arreadout/page_firstscreen.txt', first);
console.log('首屏 %d 字符', first.length);
await page.click('#tabDelta'); await sleep(3200);
const full = await page.eval(`(()=>document.body.innerText||'')()`);
writeFileSync('.cache/arreadout/page_full.txt', full);
console.log('整页 %d 字符', full.length);
const tabs = await page.eval(`(()=>[...document.querySelectorAll('[id^=tab]')].map(t=>t.id+':'+t.innerText.trim().slice(0,12)))()`);
console.log('tabs:', tabs.join('  '));
process.exit(0);
