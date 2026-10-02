import { launch, Page, CDP } from './cdp_client.mjs';
import { readFileSync } from 'node:fs';

const URL = process.env.T3D_URL || 'http://127.0.0.1:10251/';
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_slider_' + process.pid;
const LENS = JSON.parse(readFileSync(
  '/Users/zhourui/code/steer3d/frontend/public/latent/data/logit_lens.json', 'utf8'));
const BY_ID = new Map(LENS.trajectories.map(t => [t.id, t]));
const sleep = ms => new Promise(r => setTimeout(r, ms));

const recId = 'aime__1983__1983_I_1__think';
const other = LENS.trajectories.find(t => t.id !== recId && t.mode === 'think'
                                      && t.window[0] === BY_ID.get(recId).window[0]);
const otherT = other.window[0] + 2;
console.log('recId=', recId, ' win=', BY_ID.get(recId).window);
console.log('other=', other.id, ' win=', other.window, ' otherT=', otherT);

const { proc, version } = await launch({ port: 9477, userDataDir: PROFILE,
  windowSize: '1600,1000', url: 'about:blank' });
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  await sleep(4000);

  const pick = (id) => page.eval(`(() => {
    const s = [...document.querySelectorAll('select')].find(x =>
      [...x.options].some(o => /^aime__/.test(o.value)));
    const opt = [...s.options].find(o => o.value === ${JSON.stringify(id)});
    if (!opt) return 'NO_OPTION';
    s.value = opt.value;
    s.dispatchEvent(new Event('change', { bubbles: true }));
    return 'SET';
  })()`);
  const click = (re) => page.eval(`(() => {
    const b = [...document.querySelectorAll('button')].find(x => ${re}.test(x.textContent||''));
    if (!b) return 'NO_BTN'; b.click(); return 'CLICKED';
  })()`);
  const slider = () => page.eval(`(() => {
    const r = document.querySelector('[data-deriv-step]');
    if (!r) return null;
    const el = document.querySelector('[data-derivation]');
    return { min: r.min, max: r.max, step: r.step, value: r.value,
             state: el.getAttribute('data-derivation'),
             head: (el.innerText||'').split('\\n').slice(0,4).join(' | ') };
  })()`);

  console.log('\n--- pick recId, reset, start ---');
  await pick(recId); await click('/reset/i'); await click('/start|play|run/i');
  await sleep(6000);
  console.log('  slider:', JSON.stringify(await slider()));

  console.log('\n--- pick OTHER, reset, start, then set slider to', otherT, '---');
  await pick(other.id); await click('/reset/i'); await click('/start|play|run/i');
  await sleep(6000);
  console.log('  after start:', JSON.stringify(await slider()));

  const set = await page.eval(`(() => {
    const r = document.querySelector('[data-deriv-step]');
    if (!r) return 'NO_SLIDER';
    const before = { min: r.min, max: r.max, value: r.value };
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, 'value').set;
    setter.call(r, ${otherT});
    const afterSet = r.value;          // 浏览器可能按 min/max 夹取
    r.dispatchEvent(new Event('input', { bubbles: true }));
    r.dispatchEvent(new Event('change', { bubbles: true }));
    return JSON.stringify({ before, afterSet, dispatched: ${otherT} });
  })()`);
  console.log('  set result:', set);
  for (let i = 0; i < 6; i++) {
    await sleep(900);
    console.log(`   t+${(i+1)*0.9}s:`, JSON.stringify(await slider()));
  }
} catch (e) { console.log('crash', e); }
finally { cdp.close(); proc.kill('SIGKILL'); }
