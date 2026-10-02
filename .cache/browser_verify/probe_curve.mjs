import { launch, Page, CDP } from './cdp_client.mjs';
const URL = process.env.T3D_URL || 'http://127.0.0.1:10021/';
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_curve_' + process.pid;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const { proc, version } = await launch({ port: 9474, userDataDir: PROFILE,
  windowSize: '1600,1000', url: 'about:blank' });
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  await sleep(7000);
  const r = await page.eval(`(() => {
    const el = document.querySelector('[data-law]');
    const p = el.querySelector('[data-curve="analytic"]');
    const svg = p.ownerSVGElement;
    const pb = p.getBoundingClientRect();
    const sb = svg.getBoundingClientRect();
    const ctm = p.getScreenCTM();
    const raw = p.getBBox ? p.getBBox() : null;
    return { d: p.getAttribute('d').slice(0, 120) + ' ...',
             rect: [pb.x, pb.y, pb.width, pb.height].map(v=>+v.toFixed(2)),
             svgRect: [sb.x, sb.y, sb.width, sb.height].map(v=>+v.toFixed(2)),
             viewBox: svg.getAttribute('viewBox'),
             ctmA: ctm ? +ctm.a.toFixed(4) : null,
             rawBBox: raw ? [raw.x, raw.y, raw.width, raw.height].map(v=>+v.toFixed(2)) : null };
  })()`);
  console.log(JSON.stringify(r, null, 1));
} catch (e) { console.log('crash', e); }
finally { cdp.close(); proc.kill('SIGKILL'); }
