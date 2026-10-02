// Browser verification of the 24-trajectory latent bundle.
//
// Checks, all read back out of the live page rather than from a screenshot:
//   * #selTraj has 24 <option> elements and their text lists 24 distinct
//     problem ids;
//   * the 2-D scatter canvas (#cv) actually paints for every one of the 24
//     trajectories -- measured as a non-background pixel count, and cross
//     checked against the manifest's own n_proj for that trajectory;
//   * zero uncaught errors and zero unhandled rejections, collected by an
//     installer injected before any page script runs.
//
// Usage: node .cache/dataexp/verify_24.mjs <baseUrl> <cdpPort> <profileDir>

import { launch, CHROME, CDP, Page } from '../browser_verify/cdp_client.mjs';
import { writeFileSync, mkdirSync } from 'node:fs';
import { spawn } from 'node:child_process';

const base = process.argv[2];
const cdpPort = +(process.argv[3] || 8958);
const profile = process.argv[4];
const sleep = ms => new Promise(r => setTimeout(r, ms));

// cdp_client.mjs launch() polls http://127.0.0.1:<port> only. Chrome binds its
// DevTools endpoint to whichever localhost family the OS hands it, and on this
// box it lands on [::1] often enough that the IPv4 poll times out and the
// helper declares the browser dead while it is actually serving. Poll both.
async function launchDualStack(port, userDataDir) {
  mkdirSync(userDataDir, { recursive: true });
  const proc = spawn(CHROME, [
    '--single-process', `--remote-debugging-port=${port}`,
    `--user-data-dir=${userDataDir}`, '--window-size=1600,1000',
    '--force-device-scale-factor=1', '--no-first-run', '--no-default-browser-check',
    '--disable-sync', '--disable-crash-reporter', '--hide-scrollbars', '--mute-audio',
    '--disable-background-timer-throttling', '--disable-renderer-backgrounding',
    '--disable-backgrounding-occluded-windows',
    '--disable-features=Translate,BackForwardCache', 'about:blank',
  ], { stdio: ['ignore', 'pipe', 'pipe'] });
  let stderr = '';
  proc.stderr.on('data', d => { stderr += d.toString(); });
  proc.stdout.on('data', () => {});
  for (let i = 0; i < 120; i++) {
    for (const host of ['127.0.0.1', '[::1]']) {
      try {
        const r = await fetch(`http://${host}:${port}/json/version`);
        if (r.ok) return { proc, version: await r.json() };
      } catch {}
    }
    await sleep(100);
  }
  proc.kill('SIGKILL');
  throw new Error('devtools never came up on 127.0.0.1 or [::1]\n' + stderr.slice(-800));
}

const { proc, version } = await launchDualStack(cdpPort, profile);
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);

// Install the error collector before any page script executes, otherwise an
// exception thrown during boot is lost.
await page.send('Page.addScriptToEvaluateOnNewDocument', {
  source: `
    window.__errs = [];
    window.addEventListener('error', e => window.__errs.push(
      'error: ' + (e.message || '') + ' @' + (e.filename||'') + ':' + (e.lineno||'')));
    window.addEventListener('unhandledrejection', e => window.__errs.push(
      'rejection: ' + ((e.reason && (e.reason.stack || e.reason.message)) || e.reason)));
    const _ce = console.error;
    console.error = function(){ window.__errs.push('console.error: ' +
      Array.from(arguments).map(String).join(' ')); _ce.apply(console, arguments); };
  `,
});

await page.nav(`${base}/latent/index.html`);

// Readiness is decided by the page's own loading overlay, not by loadEventFired.
let ready = false;
for (let i = 0; i < 300; i++) {
  ready = await page.eval(`(()=>{const l=document.querySelector('#loading');
    return !!(l && l.classList.contains('hide'));})()`);
  if (ready) break;
  await sleep(500);
}
if (!ready) {
  console.log('FAIL loading overlay never hid');
  writeFileSync('.cache/dataexp/verify_24_result.json',
    JSON.stringify({ ready, errors: await page.eval('window.__errs') }, null, 2));
  process.exit(1);
}

// Dismiss the walkthrough overlay; it is position:fixed z-index:200 and would
// sit on top of everything we screenshot, though it does not block the DOM.
await page.eval(`(()=>{try{document.querySelector('#orientClose').click();}catch(e){}
  return true;})()`);
await sleep(300);

const fail = [];
const ok = (label, cond, detail = '') => {
  console.log(`[${cond ? 'ok' : 'FAIL'}] ${label}` + (detail ? ` -- ${detail}` : ''));
  if (!cond) fail.push(label);
};

// --- selector --------------------------------------------------------------
const sel = await page.eval(`(()=>{
  const o=[...document.querySelectorAll('#selTraj option')];
  return {n:o.length, ids:o.map(x=>x.textContent.trim().split('  ')[0])};
})()`);
ok('#selTraj has 24 options', sel.n === 24, `got ${sel.n}`);
ok('selector lists 24 distinct problem ids',
   new Set(sel.ids).size === 24, `${new Set(sel.ids).size} distinct`);

const man = await page.eval(`(()=>{const m=S.m;return {
  n:m.trajectories.length,
  variant:m.variant,
  pid:m.trajectories.map(t=>t.problem_id),
  nproj:m.trajectories.map(t=>t.layers[0].n_proj)};})()`);
ok('in-page manifest has 24 trajectories', man.n === 24, `got ${man.n}, variant=${man.variant}`);

// --- the scatter paints for all 24 ---------------------------------------
// Non-background pixels: the canvas clears to one flat colour, so any pixel
// that differs from the top-left sample was drawn.
const paint = `(()=>{
  const c=document.querySelector('#cv');
  const g=c.getContext('2d');
  const d=g.getImageData(0,0,c.width,c.height).data;
  const W=c.width, bg=[d[0],d[1],d[2]];
  let n=0;
  for(let i=0;i<d.length;i+=4){
    if(Math.abs(d[i]-bg[0])+Math.abs(d[i+1]-bg[1])+Math.abs(d[i+2]-bg[2])>12) n++;
  }
  return {w:W,h:c.height,nonbg:n,bg};
})()`;

// Silence the health beacon: 24 trajectory switches would otherwise saturate
// the 6-connections-per-origin pool the data fetches need.
await page.eval(`(()=>{S.quiet=true;return true;})()`);

const perTraj = [];
for (let i = 0; i < 24; i++) {
  const info = await page.eval(`(async()=>{
    const s=document.querySelector('#selTraj');
    s.value=${i};
    await loadTraj(${i});
    render();
    await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
    return {i:S.ti, id:S.m.trajectories[S.ti].problem_id,
            nproj:S.m.trajectories[S.ti].layers[0].n_proj,
            hs:S.hs?S.hs.length:0, title:document.title};
  })()`);
  const p = await page.eval(paint);
  perTraj.push({ ...info, nonbg: p.nonbg, w: p.w, h: p.h });
  console.log(`  [${String(i).padStart(2)}] ${info.id}  hs=${info.hs}  `
            + `nonbg px=${p.nonbg}  nproj=${info.nproj}  title="${info.title}"`);
}

const blank = perTraj.filter(r => r.nonbg < 200);
ok('2-D scatter painted for all 24 trajectories', blank.length === 0,
   blank.length ? `blank: ${blank.map(r => r.id).join(',')}`
                : `min nonbg px = ${Math.min(...perTraj.map(r => r.nonbg))}`);
// Compare the page's in-memory manifest against the on-disk manifest.json, so
// this is a cross-check rather than a comparison of the same object with itself.
const disk = JSON.parse(
  (await import('node:fs')).readFileSync('frontend/public/latent/data/manifest.json', 'utf8'));
const diskNproj = disk.trajectories.map(t => t.layers[0].n_proj);
ok('scatter point budget matches the on-disk manifest n_proj for all 24',
   perTraj.every((r, i) => r.nproj === diskNproj[i]),
   `nproj values: ${[...new Set(perTraj.map(r => r.nproj))].join(',')}`);
ok('raw hidden states loaded for all 24',
   perTraj.every(r => r.hs > 0), `min hs = ${Math.min(...perTraj.map(r => r.hs))}`);
ok('selected trajectory id order matches manifest order',
   perTraj.every((r, i) => r.id === man.pid[i]));

// --- errors ----------------------------------------------------------------
const errs = await page.eval('window.__errs');
ok('no uncaught errors / unhandled rejections / console.error',
   errs.length === 0, errs.length ? JSON.stringify(errs.slice(0, 5)) : 'none');

const result = { base, cdpPort, ready, sel, man, perTraj, errs, fail };
writeFileSync('.cache/dataexp/verify_24_result.json', JSON.stringify(result, null, 2));
await page.screenshot('.cache/dataexp/shot_24.png');

console.log('');
console.log(fail.length ? `FAILED ${fail.length}: ${fail.join('; ')}` : 'ALL BROWSER CHECKS PASSED');
await page.close();
cdp.close();
proc.kill('SIGKILL');
process.exit(fail.length ? 1 : 0);
