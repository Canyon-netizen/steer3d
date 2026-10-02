import { launch, Page, CDP } from './cdp_client.mjs';
import { readFileSync } from 'node:fs';

const URL = process.env.T3D_URL || 'http://127.0.0.1:10008/';
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_f9probe_' + process.pid;
const LENS = JSON.parse(readFileSync(
  '/Users/zhourui/code/steer3d/frontend/public/latent/data/logit_lens.json', 'utf8'));
const sleep = ms => new Promise(r => setTimeout(r, ms));

const { proc, version } = await launch({ port: 9466, userDataDir: PROFILE,
  windowSize: '1600,1000', url: 'about:blank' });
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);

const readPanel = () => page.eval(`(() => {
  const el = document.querySelector('[data-derivation]');
  if (!el) return { state: 'absent' };
  return { state: el.getAttribute('data-derivation'),
           head: (el.innerText||'').split('\\n').slice(0,3).join(' | ') };
})()`);

try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  await sleep(4000);

  // 选一条默认记录 + start
  const first = await page.eval(`(() => {
    const s = [...document.querySelectorAll('select')].find(x =>
      [...x.options].some(o => /^aime__/.test(o.value)));
    if (!s) return null;
    const opts = [...s.options].filter(o => /^aime__/.test(o.value));
    return { n: opts.length, sample: opts.slice(0,3).map(o=>o.value), sel: s.value };
  })()`);
  console.log('select:', JSON.stringify(first));

  const pick = (id) => page.eval(`(() => {
    const s = [...document.querySelectorAll('select')].find(x =>
      [...x.options].some(o => /^aime__/.test(o.value)));
    if (!s) return 'NO_SELECT';
    const opt = [...s.options].find(o => o.value === ${JSON.stringify(id)});
    if (!opt) return 'NO_OPTION_' + ${JSON.stringify(id)};
    s.value = opt.value;
    s.dispatchEvent(new Event('change', { bubbles: true }));
    return 'SET_' + s.value;
  })()`);
  const click = (re) => page.eval(`(() => {
    const b = [...document.querySelectorAll('button')].find(x => ${re}.test(x.textContent||''));
    if (!b) return 'NO_BTN';
    b.click(); return 'CLICKED_' + (b.textContent||'').trim();
  })()`);

  const recId = LENS.trajectories[0].id;
  const other = LENS.trajectories.find(t => t.id !== recId && t.mode === 'think');
  console.log('recId =', recId, ' win =', LENS.trajectories[0].window);
  console.log('other =', other.id, ' win =', other.window);

  console.log('\n--- stage 1: pick first + reset + start ---');
  console.log(await pick(recId), '|', await click('/reset/i'), '|', await click('/start|play|run/i'));
  await sleep(6000);
  console.log('  panel:', JSON.stringify(await readPanel()));

  console.log('\n--- stage 2: pick OTHER, reset, start, then WAIT ---');
  console.log(await pick(other.id));
  await sleep(500);
  console.log('  immediately after change:', JSON.stringify(await readPanel()));
  console.log('  reset:', await click('/reset/i'));
  await sleep(500);
  console.log('  after reset:', JSON.stringify(await readPanel()));
  console.log('  start:', await click('/start|play|run/i'));
  for (let i = 0; i < 10; i++) {
    await sleep(1200);
    const p = await readPanel();
    console.log(`  t+${(i+1)*1.2}s:`, JSON.stringify(p));
    if (p.state === 'ready' && /steps 101/.test(p.head)) break;
  }
} catch (e) { console.log('crash', e); }
finally { cdp.close(); proc.kill('SIGKILL'); }
