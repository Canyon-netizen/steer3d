// The 2-D scatter now colours each generated point by that step's measured
// entropy. Before this it drew every point in one flat #4a5a78, with 1024
// per-step entropies sitting unused in the same file.
//
// The check that matters is pixel-level and relational: it is not enough that
// the canvas has many colours on it, because the grid, the axes and the depth
// trail are all coloured too. So it samples the scatter's own pixels, groups
// them by hue, and then verifies that the *reddest* cluster really is the
// high-entropy end -- by matching those pixels back to the entropy of the step
// they came from. A pretty gradient that does not track the data fails.
//
// Run: node verify_entcolor.mjs

import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { launch, CDP, Page } from '../browser_verify/cdp_client.mjs';

const sleep = ms => new Promise(r => setTimeout(r, ms));
const HERE = new URL('.', import.meta.url).pathname;
const DATA = '/Users/zhourui/code/steer3d/frontend/public/latent/data/';
const PAGE_URL = process.env.FRONTEND || 'http://127.0.0.1:8917/latent/index.html';
const CDP_PORT = Number(process.env.BV_PORT || 9800);
const STEP = Number(process.env.STEP || 60);

mkdirSync(HERE + 'out/', { recursive: true });
const results = [];
let failures = 0;
const check = (name, ok, detail) => {
  results.push({ name, ok: !!ok, detail });
  if (!ok) failures++;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? '  ' + detail : ''}`);
};

const manifest = JSON.parse(readFileSync(DATA + 'manifest.json', 'utf8'));
const traj = manifest.trajectories[0];
const entMax = Math.max(...traj.tokens.map(t => t.ent));
// The steps we expect to be the reddest, straight from the file.
const byEnt = traj.tokens.slice(0, STEP).map((t, i) => ({ i, ent: t.ent }))
  .sort((a, b) => b.ent - a.ent);
const topEnt = byEnt.slice(0, 5);
console.log(`reference from ${DATA}manifest.json, trajectory 0, ${STEP} steps:`);
console.log(`  entropy max over the whole trajectory = ${entMax.toFixed(4)} nats`);
console.log(`  the 5 most uncertain steps under ${STEP}: ` +
  topEnt.map(t => `#${t.i}(${t.ent.toFixed(3)})`).join(' '));
console.log('');

const { proc, version } = await launch({
  port: CDP_PORT,
  userDataDir: HERE + 'profile_' + CDP_PORT,
  windowSize: '1600,1000',
  url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);

try {
  const errors = [];
  page.cdp.on(m => {
    if (m.method === 'Runtime.exceptionThrown') {
      const d = m.params.exceptionDetails;
      errors.push(d.exception?.description || d.text);
    }
  });
  await page.send('Network.enable');
  await page.send('Network.setCacheDisabled', { cacheDisabled: true });
  await page.send('Page.enable');
  await page.send('Runtime.enable');
  await page.send('Page.navigate', { url: PAGE_URL });
  for (let i = 0; i < 30; i++) {
    await sleep(1000);
    const ok = await page.eval(`(()=>{try{return !!(window.S||S)&&S.m&&S.m.trajectories.length>0}catch(e){return false}})()`);
    if (ok) break;
  }
  check('page loaded with no uncaught exception', errors.length === 0,
    errors.length ? errors[0].slice(0, 140) : 'clean');

  await page.eval(`(()=>{ S.tok = ${STEP}; S.view = "XY"; render(); return S.tok; })()`);
  await sleep(800);

  // -- 1. the scatter actually uses a range of hues -----------------------
  const hues = await page.eval(`(()=>{
    const c = document.querySelector('#cv');
    const g = c.getContext('2d');
    const {data} = g.getImageData(0,0,c.width,c.height);
    const seen = {};
    for(let i=0;i<data.length;i+=4){
      const r=data[i],gg=data[i+1],b=data[i+2];
      // saturated-ish pixels only: the grid is near-grey, the axes are thin
      if(Math.max(r,gg,b)-Math.min(r,gg,b) < 40) continue;
      const k = r+','+gg+','+b;
      seen[k] = (seen[k]||0)+1;
    }
    return Object.entries(seen).sort((a,b)=>b[1]-a[1]);
  })()`);
  const scatterHues = hues.filter(([k, n]) => n >= 6);
  check('the canvas contains a spread of saturated colours, not one flat fill',
    scatterHues.length >= 8, `${scatterHues.length} hues with >=6 px (top: ` +
    scatterHues.slice(0, 4).map(([k, n]) => `${k}x${n}`).join(' ') + ')');

  // -- 2. the legend ramp is a real gradient built from entColor ----------
  const ramp = await page.eval(`(()=>{
    const el = document.querySelector('#lgEntRamp');
    return el ? getComputedStyle(el).backgroundImage : '';
  })()`);
  check('the legend shows a continuous ramp', /linear-gradient/.test(ramp),
    ramp.slice(0, 90));

  // -- 2b. the legend's left-to-right LABELS match the ramp's direction ----
  // The ramp samples the entropy axis from small to large, so its first stop
  // is the most certain step (blue) and its last is the most uncertain (red).
  // The caption originally read "拿不准 → 笃定", which is the other way
  // round: a reader would have read a red dot as "safe". Only visible by
  // looking at the rendered legend -- every colour check passed either way.
  const legend = await page.eval(`(()=>{
    // parentElement, not closest('span'): #lgEntRamp *is* a span, so
    // closest() returns the element itself and the caption reads back empty.
    const el = document.querySelector('#lgEntRamp').parentElement;
    return el ? el.innerText.replace(/\\s+/g,' ').trim() : '';
  })()`);
  check('the legend caption runs in the same direction as the ramp',
    /笃定 → 拿不准/.test(legend),
    legend.slice(0, 70));
  // And confirm the first gradient stop really is the blue (certain) end.
  const firstStop = (ramp.match(/rgb\([^)]+\)\s+0%/) || [''])[0];
  const firstRgb = (firstStop.match(/rgb\([^)]+\)/) || [''])[0].replace(/[^0-9,]/g, '');
  const [fr, , fb] = firstStop ? firstStop.match(/\d+/g).map(Number) : [0, 0, 255];
  check('the ramp starts at the certain (blue) end, matching the caption',
    fb > fr, `first stop ${firstRgb || firstStop} -> blue-dominant=${fb > fr}`);

  // -- 3. THE assertion: the reddest pixels are the high-entropy steps ----
  // Walk the same entColor() the page uses, ask it for the colour of each
  // step's entropy, then require that the canvas contains exactly those
  // colours, with the highest-entropy steps being the reddest.
  const mapping = await page.eval(`(()=>{
    const t = S.m.trajectories[S.ti].tokens;
    let m = 0; for(let k=0;k<t.length;k++) if(t[k].ent > m) m = t[k].ent;
    const out = [];
    for(let k=0;k<${STEP};k++) out.push([k, entColor(t[k].ent, m), t[k].ent]);
    return out;
  })()`);
  // -- 3. THE assertion: the colour ordering must track the entropy -------
  // First attempt at this compared each step's exact RGB against a histogram
  // of "saturated" canvas pixels and reported 6/60 absent, including
  // rgb(255,242,242). That colour was on the canvas; the histogram's own
  // saturation filter (max-min >= 40) had discarded it -- and the ramp passes
  // through exactly that near-white at its midpoint, so the filter threw away
  // the middle of the very scale under test. Matching exact pixels also
  // depends on antialiasing, which is a rendering detail, not the claim.
  //
  // The claim is: colour is a monotone function of entropy. So check that
  // directly. For every pair of steps, a higher entropy must not produce a
  // less-red colour. Inversions are the failures.
  const redness = (c) => { const m = c.match(/[\d.]+/g).map(Number); return m[0] - m[2]; };
  const rows = mapping.map(([k, c, e]) => ({ k, e, r: redness(c) }));
  let inversions = 0, ties = 0, worst = null, worstTie = null;
  for (let a = 0; a < rows.length; a++) {
    for (let b = 0; b < rows.length; b++) {
      if (rows[a].e <= rows[b].e) continue;      // a is the more uncertain
      if (rows[a].r < rows[b].r) {              // but strictly LESS red: wrong
        inversions++;
        if (!worst || Math.abs(rows[a].e - rows[b].e) > Math.abs(worst.ea - worst.eb)) {
          worst = { ka: rows[a].k, ea: rows[a].e, ra: rows[a].r, kb: rows[b].k, eb: rows[b].e, rb: rows[b].r };
        }
      } else if (rows[a].r === rows[b].r) {     // indistinguishable at 8 bits
        ties++;
        if (!worstTie || Math.abs(rows[a].e - rows[b].e) > Math.abs(worstTie.ea - worstTie.eb)) {
          worstTie = { ka: rows[a].k, ea: rows[a].e, r: rows[a].r, kb: rows[b].k, eb: rows[b].e };
        }
      }
    }
  }
  const pairs = rows.length * (rows.length - 1) / 2;
  check('no more-uncertain step is ever less red than a less-uncertain one',
    inversions === 0,
    inversions === 0 ? `${pairs} pairs, 0 inversions` :
    `${inversions}/${pairs} inverted, worst: #${worst.ka}(e=${worst.ea.toFixed(3)}, r-b=${worst.ra})` +
    ` vs #${worst.kb}(e=${worst.eb.toFixed(3)}, r-b=${worst.rb})`);

  // Ties are 8-bit quantisation at the saturated end, not a broken ramp: the
  // blue channel clips at 255 while red is still 0 or 1, so entropy
  // differences of 0.002 nats land on the same byte. That is acceptable only
  // where the steps were already indistinguishable as "certain". Requiring the
  // ties to sit in the deep blue is what stops this from becoming a loophole
  // for a genuinely flat ramp, which would tie everywhere.
  const tieRed = worstTie ? worstTie.r : 255;
  check('indistinguishable steps occur only where both were already certain',
    ties === 0 || (worstTie && tieRed <= -200),
    ties === 0 ? 'no ties' :
    `${ties}/${pairs} tied; the largest tied gap is #${worstTie.ka}(e=${worstTie.ea.toFixed(4)}) vs ` +
    `#${worstTie.kb}(e=${worstTie.eb.toFixed(4)}), both at r-b=${tieRed} (deep blue)`);

  // And the ramp must actually span a visible range, not be flat.
  const spread = Math.max(...rows.map(r => r.r)) - Math.min(...rows.map(r => r.r));
  check('the ramp spans a visible range of hue across the drawn steps',
    spread > 200, `r-b spread = ${spread}`);

  // -- 3b. tie the DRAWN PIXELS to the entropy of the step ---------------
  // Everything above measures entColor(), i.e. the ramp function. Mutation M1
  // puts back a flat fill and leaves entColor untouched -- and the whole suite
  // stayed 8/8 green, because the canvas still had the axes, the grid, the
  // depth trail and the current-token marker on it, and the ramp function
  // still had perfect monotonicity. The check was measuring the right
  // function and the wrong thing: a colour scale nobody draws with.
  //
  // So: count exact matches on the canvas, with no hue filter, for the
  // colours of the most uncertain drawn steps. A scatter that paints by
  // entropy must put those exact bytes down; a flat fill cannot.
  const exact = await page.eval(`(()=>{
    const t = S.m.trajectories[S.ti].tokens;
    let m = 0; for(let k=0;k<t.length;k++) if(t[k].ent > m) m = t[k].ent;
    // Key on "r,g,b": canvas pixels come out that way, while entColor returns
    // "rgb(r,g,b)". Keying on the raw return value matched nothing and the
    // first version of this check reported 0/5 while the page was correct.
    const want = {};
    for(let k=0;k<${STEP};k++){
      const key = entColor(t[k].ent, m).replace(/^rgb\\(|\\)$/g,'');
      want[key] = k;
    }
    const c = document.querySelector('#cv');
    const {data} = c.getContext('2d').getImageData(0,0,c.width,c.height);
    const hits = {};
    for(let i=0;i<data.length;i+=4){
      const key = data[i]+','+data[i+1]+','+data[i+2];
      if(key in want) hits[key] = (hits[key]||0)+1;
    }
    return {want, hits};
  })()`);
  const topKeys = mapping
    .filter(([k]) => topEnt.some(t => t.i === k))
    .map(([, c]) => c.replace(/^rgb\(|\)$/g, ''));
  const painted = topKeys.filter(kk => (exact.hits[kk] || 0) >= 3);
  const missingKey = topKeys.find(kk => (exact.hits[kk] || 0) < 3);
  check('the exact colour of each most-uncertain step is actually painted on canvas',
    painted.length === topKeys.length,
    `${painted.length}/${topKeys.length} present with >=3 px` +
    (missingKey
      ? `; missing e.g. rgb(${missingKey}) which had ${exact.hits[missingKey] || 0} px`
      : ` (counts: ${topKeys.map(kk => exact.hits[kk] || 0).join('/')})`));

  // -- 3c. the ramp spans a visible range, not flat -----------------------
  // (the grey-fallback check follows below)
  // -- 4. no step is silently grey ----------------------------------------
  const greys = mapping.filter(([, c]) => c === 'rgb(122,134,158)');
  check('no drawn step falls back to the "no entropy" grey',
    greys.length === 0, greys.length ? `${greys.length} grey` : 'all coloured');

  // The first-run orientation overlay covers the app; a screenshot taken
  // before dismissing it shows the primer instead of the scatter under test.
  await page.eval(`(()=>{
    const b=[...document.querySelectorAll('button')].find(x=>/开始看|我读完了/.test(x.textContent));
    if(b) b.click();
    return !!b;
  })()`);
  await sleep(900);
  await page.screenshot(HERE + 'out/entcolor.png');
  check('no uncaught exception during the run', errors.length === 0,
    errors.length ? errors[0].slice(0, 140) : 'clean');
} catch (e) {
  check('the script ran to completion', false, String(e).slice(0, 220));
  failures++;
} finally {
  writeFileSync(HERE + 'out/result_entcolor.json', JSON.stringify({ failures, results }, null, 2));
  try { proc.kill('SIGKILL'); } catch {}
  cdp.ws.close();
}
console.log(`\n=== ${results.length - failures}/${results.length} passed, ${failures} failed ===`);
process.exit(failures ? 1 : 0);
