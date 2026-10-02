import { launch, CDP, Page } from '../browser_verify/cdp_client.mjs';
import { writeFileSync } from 'node:fs';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const reg = await (await fetch('http://127.0.0.1:8917/latent/models.json')).json();
const big = reg.models.find(m => m.d_model === 2048);
const { proc, version } = await launch({ port: 9383,
  userDataDir: '/Users/zhourui/code/steer3d/.cache/arreadout/shotprofile4', url: 'about:blank' });
const cdp = await CDP.connect(
  `ws://127.0.0.1:9383/devtools/browser/${version.webSocketDebuggerUrl.split('/').pop()}`);
const page = await Page.create(cdp);
await page.send('Network.enable');
await page.send('Page.setDeviceMetricsOverride',
  { width: 1440, height: 1000, deviceScaleFactor: 2, mobile: false });
await page.send('Page.navigate',
  { url: `http://127.0.0.1:8917/latent/index.html?orient=reset&m=${big.id}` });
await page.waitForEvent('Page.loadEventFired', 40000);
await sleep(900);
if (await page.eval(`(()=>{const o=document.getElementById('orientation');
  return !!(o && getComputedStyle(o).display!=='none')})()`)) {
  await page.click('#orientClose'); await sleep(800);
}
await page.click('#tabDelta'); await sleep(3000);

// Scroll the inner scroller so the declaration's TOP is at the window's top,
// then report whether its WHOLE height fits. This is the measurement the
// presence check cannot make: an element can be present, 222px tall, and
// still be unreadable if the window it lives in is shorter than that.
const fit = await page.eval(`(()=>{
  const d=document.querySelector('[data-aroot] [data-problemset]');
  let sc=d.parentElement;
  for(let e=d.parentElement;e;e=e.parentElement){
    const cs=getComputedStyle(e);
    if(cs.overflow!=='visible'||cs.overflowY!=='visible'){ sc=e; break; }
  }
  const sr=sc.getBoundingClientRect(), dr=d.getBoundingClientRect();
  sc.scrollTop += (dr.top - sr.top) - 4;
  const sr2=sc.getBoundingClientRect(), dr2=d.getBoundingClientRect();
  return {scrollerH:Math.round(sr.height), scrollerClientH:sc.clientHeight,
          declH:Math.round(dr2.height),
          fits: dr2.height <= sc.clientHeight,
          declTopInWin: Math.round(dr2.top-sr2.top),
          declBottomInWin: Math.round(dr2.bottom-sr2.top),
          sliver: Math.max(0, Math.round(dr2.bottom-sr2.bottom))};
})()`);
console.log('answer_readout decl fit:', JSON.stringify(fit));
await sleep(600);
let r = await page.send('Page.captureScreenshot', { format: 'png' });
writeFileSync('.cache/arreadout/shot_decl_answer_full.png', Buffer.from(r.data,'base64'));

const fit2 = await page.eval(`(()=>{
  const d=document.querySelector('[data-problemset="cot_effect_32k"]');
  let sc=d.parentElement;
  for(let e=d.parentElement;e;e=e.parentElement){
    const cs=getComputedStyle(e);
    if(cs.overflow!=='visible'||cs.overflowY!=='visible'){ sc=e; break; }
  }
  const sr=sc.getBoundingClientRect(), dr=d.getBoundingClientRect();
  sc.scrollTop += (dr.top - sr.top) - 4;
  const sr2=sc.getBoundingClientRect(), dr2=d.getBoundingClientRect();
  return {scrollerH:Math.round(sr.height), declH:Math.round(dr2.height),
          fits: dr2.height <= sc.clientHeight,
          sliver: Math.max(0, Math.round(dr2.bottom-sr2.bottom))};
})()`);
console.log('32k decl fit:', JSON.stringify(fit2));
await sleep(600);
r = await page.send('Page.captureScreenshot', { format: 'png' });
writeFileSync('.cache/arreadout/shot_decl_32k_full.png', Buffer.from(r.data,'base64'));
console.log('shots written');
await page.send('Browser.close').catch(()=>{}); proc.kill('SIGKILL'); process.exit(0);
