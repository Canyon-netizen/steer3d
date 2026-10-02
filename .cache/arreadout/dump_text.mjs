import { launch, CDP, Page } from '../browser_verify/cdp_client.mjs';
import { writeFileSync } from 'node:fs';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const reg = await (await fetch('http://127.0.0.1:8917/latent/models.json')).json();
const big = reg.models.find(m => m.d_model === 2048);
const { proc, version } = await launch({ port: 9383,
  userDataDir: '/Users/zhourui/code/steer3d/.cache/arreadout/dumpprofile', url: 'about:blank' });
const cdp = await CDP.connect(`ws://127.0.0.1:9383/devtools/browser/${version.webSocketDebuggerUrl.split('/').pop()}`);
const page = await Page.create(cdp);
await page.send('Network.enable');
await page.send('Page.navigate', { url: `http://127.0.0.1:8917/latent/index.html?orient=reset&m=${big.id}` });
await page.waitForEvent('Page.loadEventFired', 40000);
await sleep(1000);
if (await page.eval(`(()=>{const o=document.getElementById('orientation');return !!(o&&getComputedStyle(o).display!=='none')})()`)) {
  await page.click('#orientClose'); await sleep(700);
}
await page.click('#tabDelta'); await sleep(3000);
const txt = await page.eval(`(()=>{
  const e=document.querySelector('[data-aroot]');
  return e ? e.innerText : '(no block)';})()`);
writeFileSync('.cache/arreadout/block_text.txt', txt);
console.log('答案位移正文屏全文 %d 字符，已写入 .cache/arreadout/block_text.txt', txt.length);
const ar = await (await fetch(`http://127.0.0.1:8917/latent/${big.base}answer_readout.json`)).json();
const top = await page.eval(`(()=>{
  const root=document.querySelector('[data-aroot]');
  // 块之前最近的说明文字（导读层）
  let n=root, prev=null;
  while(n){ if(n.previousElementSibling){prev=n.previousElementSibling;break;} n=n.parentElement; }
  return prev ? prev.innerText.slice(0,1500) : '';})()`);
writeFileSync('.cache/arreadout/block_above.txt', top);
console.log('块上方 %d 字符', top.length);
process.exit(0);
