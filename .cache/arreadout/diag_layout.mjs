import { launch, CDP, Page } from '../browser_verify/cdp_client.mjs';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const reg = await (await fetch('http://127.0.0.1:8917/latent/models.json')).json();
const big = reg.models.find(m => m.d_model === 2048);
const { proc, version } = await launch({
  port: 9377, userDataDir: '/Users/zhourui/code/steer3d/.cache/arreadout/diagprofile',
  url: 'about:blank',
});
const cdp = await CDP.connect(
  `ws://127.0.0.1:9377/devtools/browser/${version.webSocketDebuggerUrl.split('/').pop()}`);
const page = await Page.create(cdp);
await page.send('Network.enable');
await page.send('Page.navigate',
  { url: `http://127.0.0.1:8917/latent/index.html?orient=reset&m=${big.id}` });
await page.waitForEvent('Page.loadEventFired', 40000);
await sleep(900);
if (await page.eval(`(()=>{const o=document.getElementById('orientation');
  return !!(o && getComputedStyle(o).display!=='none')})()`)) {
  await page.click('#orientClose'); await sleep(800);
}
await page.click('#tabDelta'); await sleep(3000);

const info = await page.eval(`(()=>{
  const e=document.querySelector('[data-aroot]');
  if(!e) return {err:'no aroot'};
  const r=e.getBoundingClientRect();
  // Walk up and report the width of each ancestor, so the narrow column can be
  // named instead of guessed at.
  const chain=[]; let n=e;
  while(n && n!==document.documentElement){
    const q=n.getBoundingClientRect();
    chain.push({tag:n.tagName, cls:(n.className||'').toString().slice(0,28),
                w:Math.round(q.width), h:Math.round(q.height), ox:getComputedStyle(n).overflowX});
    n=n.parentElement;
  }
  // Direct children of the block, with their size and how much text they hold.
  const kids=[...e.children].map(c=>{
    const q=c.getBoundingClientRect();
    return {tag:c.tagName, w:Math.round(q.width), h:Math.round(q.height),
            chars:(c.innerText||'').length, head:(c.innerText||'').slice(0,46).replace(/\\n/g,' ')};
  });
  const tails=[...e.querySelectorAll('[data-artail]')].map(x=>({
    t:x.dataset.artail, chars:(x.textContent||'').length}));
  return {block:{w:Math.round(r.width),h:Math.round(r.height)}, chain, kids, tails};
})()`);
console.log(JSON.stringify(info, null, 1));
process.exit(0);
