// Screenshot the two new provenance/budget blocks and report the geometry the
// eye actually sees.
//
// Both blocks live in the page's 320px right-hand column (.wrap is
// `300px 1fr 320px`). A previous version put two 143px columns side by side
// there and every textContent check still passed -- only a screenshot showed
// it was four Chinese characters per line. So this reports width AND takes
// the shot, and it takes more than one: a long block shot at its top shows
// nothing of what is below.
import { launch, CDP, Page } from '../browser_verify/cdp_client.mjs';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const reg = await (await fetch('http://127.0.0.1:8917/latent/models.json')).json();
const big = reg.models.find(m => m.d_model === 2048);
const { proc, version } = await launch({
  port: 9379, userDataDir: '/Users/zhourui/code/steer3d/.cache/arreadout/shotprofile2',
  url: 'about:blank',
});
const cdp = await CDP.connect(
  `ws://127.0.0.1:9379/devtools/browser/${version.webSocketDebuggerUrl.split('/').pop()}`);
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

// Geometry first. These are the numbers that decide whether the block is
// readable, and they are the ones a DOM-content check never looks at.
const geo = await page.eval(`(()=>{
  const q = s => document.querySelector(s);
  const box = e => { if(!e) return null; const r=e.getBoundingClientRect();
    return {w:Math.round(r.width), h:Math.round(r.height), top:Math.round(r.top)}; };
  const notes=[...document.querySelectorAll('[data-problemset]')];
  const budget=q('[data-problemset="cot_effect_32k"]');
  return {
    sidebar: box(q('[data-cotblock]')),
    problemsetCount: notes.length,
    problemsets: notes.map(n=>({where:n.getAttribute('data-problemset'),
                                ...box(n),
                                text:(n.innerText||'').length})),
    // The 标准答案 line and the declaration under it, measured.
    arStd: box([...document.querySelectorAll('[data-aroot] div')]
                 .find(d=>[...d.childNodes].some(t=>t.nodeType===3 && /标准答案/.test(t.nodeValue)))),
    arDec: box(q('[data-aroot] [data-problemset]')),
    budgetBudget: (()=>{
      const rows=[...document.querySelectorAll('[data-cotblock] .kv')]
        .filter(d=>/「32k」是什么|真的用满|实际长度/.test(d.innerText||''));
      return rows.map(box);
    })(),
  };
})()`);
console.log(JSON.stringify(geo, null, 1));

// Scroll the answer-readout block into view and shoot it, then shoot lower
// down: the block is far taller than one viewport, and a single top-of-block
// screenshot is exactly how the previous truncation bug stayed invisible.
const shots = await page.eval(`(()=>{
  const root=document.querySelector('[data-aroot]');
  if(!root) return null;
  const sc=root.closest('[style*="overflow"], .scroll, #tblTop') || root.parentElement;
  root.scrollIntoView({block:'start'});
  return {tag:sc.tagName, id:sc.id, cls:sc.className, sh:sc.scrollHeight, ch:sc.clientHeight};
})()`);
console.log('scroll container:', JSON.stringify(shots));
await sleep(700);

const shot = async (name) => {
  const r = await page.send('Page.captureScreenshot', { format: 'png' });
  const { writeFileSync } = await import('node:fs');
  writeFileSync(`.cache/arreadout/${name}.png`, Buffer.from(r.data, 'base64'));
  console.log('wrote .cache/arreadout/' + name + '.png');
};
await shot('shot_problemset_answer');

// Now the 32k block, and specifically the part BELOW the fold.
await page.eval(`(()=>{
  const d=document.querySelector('[data-problemset="cot_effect_32k"]');
  if(d) d.scrollIntoView({block:'start'});
})()`);
await sleep(700);
await shot('shot_problemset_32k');

const deep = await page.eval(`(()=>{
  const kv=[...document.querySelectorAll('[data-cotblock] .kv')]
    .find(d=>/实际长度（中位数）/.test(d.innerText||''));
  if(!kv) return 'not found';
  kv.scrollIntoView({block:'center'});
  return kv.innerText;
})()`);
console.log('deep anchor:', JSON.stringify(deep));
await sleep(700);
await shot('shot_budget_rows');

await page.send('Browser.close').catch(()=>{});
proc.kill('SIGKILL');
process.exit(0);
