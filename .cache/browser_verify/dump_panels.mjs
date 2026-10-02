import { launch, Page, CDP } from './cdp_client.mjs';
const URL = process.env.T3D_URL || 'http://127.0.0.1:10020/';
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_dump_' + process.pid;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const { proc, version } = await launch({ port: 9471, userDataDir: PROFILE,
  windowSize: '1600,1000', url: 'about:blank' });
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  await sleep(9000);
  for (const sel of ['[data-structure]', '[data-outcome]', '[data-derivation]']) {
    const t = await page.eval(`(() => {
      const el = document.querySelector('${sel}');
      if (!el) return '(absent)';
      const lines = (el.innerText||'').split('\\n').map(s=>s.trim()).filter(Boolean);
      const svg = [...el.querySelectorAll('svg text')].map(x=>x.textContent.trim());
      return JSON.stringify({lines, svg}, null, 1);
    })()`);
    console.log('======== ' + sel + ' ========');
    console.log(t);
  }
} catch (e) { console.log('crash', e); }
finally { cdp.close(); proc.kill('SIGKILL'); }
