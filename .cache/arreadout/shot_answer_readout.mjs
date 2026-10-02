import { launch, CDP, Page } from '../browser_verify/cdp_client.mjs';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const reg = await (await fetch('http://127.0.0.1:8917/latent/models.json')).json();
const big = reg.models.find(m => m.d_model === 2048);
const { proc, version } = await launch({
  port: 9375, userDataDir: '/Users/zhourui/code/steer3d/.cache/arreadout/shotprofile',
  url: 'about:blank',
});
const cdp = await CDP.connect(
  `ws://127.0.0.1:9375/devtools/browser/${version.webSocketDebuggerUrl.split('/').pop()}`);
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

// Click the jump button so the block is actually in view, then report the
// geometry the eye will see. A 294px-wide two-column layout passes every
// textContent check and is unreadable.
const jump = await page.eval(`(()=>{
  const b=document.querySelector('[data-jump="ansread"]'); if(!b) return 'no jump';
  b.click(); return 'clicked';})()`);
console.log('jump:', jump);
await sleep(900);

const geo = await page.eval(`(()=>{
  const e=document.querySelector('[data-aroot]'); if(!e) return null;
  const r=e.getBoundingClientRect();
  const cols=[...e.querySelectorAll('[data-arpre],[data-arpost]')].map(x=>{
    const q=x.getBoundingClientRect();
    return {tag:x.dataset.arpre?'pre':'post', w:Math.round(q.width), h:Math.round(q.height)};
  });
  const box=e.closest('*');
  // Find the nearest scrollable ancestor and report it: the page itself does
  // not scroll, so a block far down an inner box is invisible until jumped to.
  let sc=null, n=e;
  while(n && n!==document.body){ const o=getComputedStyle(n);
    if(o.overflowY==='auto'||o.overflowY==='scroll'){ sc=n; break; } n=n.parentElement; }
  return { x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height),
           inViewport: r.y>=0 && r.y<window.innerHeight,
           cols, scrollBox: sc? {h:Math.round(sc.clientHeight), sh:Math.round(sc.scrollHeight)} : null };
})()`);
console.log('geometry:', JSON.stringify(geo, null, 1));

// Two shots: the top of the block (the shared head + the hinge) and the
// landing tails further down. One 1000px clip of a 3300px block shows a
// third of it, which is how the earlier layout problem stayed invisible.
const vpH = 1100;
const top = await page.eval(`(()=>{const e=document.querySelector('[data-aroot]');
  const r=e.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y)};})()`);
const x = Math.max(0, top.x - 14), w = Math.min(1500, 1600 - x);
await page.screenshot('.cache/arreadout/shot_top.png',
  { clip: { x, y: Math.max(0, top.y - 14), width: w, height: vpH } });
// Scroll the inner box down to the landing section and shoot that too.
const tailY = await page.eval(`(()=>{
  const e=document.querySelector('[data-arm="tail:zero"]');
  if(!e) return null; const r=e.getBoundingClientRect(); return Math.round(r.y);})()`);
if (tailY !== null) {
  await page.eval(`(()=>{const e=document.querySelector('[data-arm="tail:zero"]');
    let n=e; while(n && getComputedStyle(n).overflowY!=='auto') n=n.parentElement;
    if(n) n.scrollTop += e.getBoundingClientRect().top - n.getBoundingClientRect().top - 10;})()`);
  await sleep(500);
  await page.screenshot('.cache/arreadout/shot_tail.png',
    { clip: { x, y: 0, width: w, height: vpH } });
}
console.log('wrote shot_top.png' + (tailY !== null ? ' and shot_tail.png' : ''));
process.exit(0);
