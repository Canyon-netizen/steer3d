// Why is the left column 25px taller than the viewport?
//
// Guessing at this cost two rounds (short option text, vertical-align) before
// the obvious thing: measure which box grew, and by how much. Prints the
// header panel and each of its line boxes, so the answer is a number instead
// of a hypothesis.
import { launch, CDP, Page } from '../browser_verify/cdp_client.mjs';

const sleep = ms => new Promise(r => setTimeout(r, ms));
const { proc, version } = await launch({
  port: 9356,
  userDataDir: '/Users/zhourui/code/steer3d/.cache/probe_line/profile',
  url: 'about:blank',
});
const cdp = await CDP.connect(
  `ws://127.0.0.1:9356/devtools/browser/${version.webSocketDebuggerUrl.split('/').pop()}`);
const page = await Page.create(cdp);
await page.send('Emulation.setDeviceMetricsOverride',
  { width: 1600, height: 1000, deviceScaleFactor: 1, mobile: false });
await page.send('Page.navigate',
  { url: 'http://localhost:8917/latent/index.html?orient=off' });
await page.waitForEvent('Page.loadEventFired', 40000);
await sleep(5000);

const r = await page.eval(`(()=>{
  const app = document.getElementById('app');
  const col = document.querySelector('#app .col');
  const head = document.querySelector('#app .col .panel');
  const sub = head && head.querySelector('.sub');
  const sel = document.getElementById('selModel');
  const btn = document.getElementById('btnOrient');
  const box = e => { if(!e) return null; const b = e.getBoundingClientRect();
    const cs = getComputedStyle(e);
    return {h: +b.height.toFixed(1), w: +b.width.toFixed(1),
            lh: cs.lineHeight, fs: cs.fontSize, disp: cs.display,
            va: cs.verticalAlign, mar: cs.margin}; };
  return {
    app: {sh: app.scrollHeight, ch: app.clientHeight, over: app.scrollHeight - app.clientHeight},
    col: {sh: col.scrollHeight, ch: col.clientHeight, over: col.scrollHeight - col.clientHeight},
    head: box(head), sub: box(sub), sel: box(sel), btn: box(btn),
    subChildren: sub ? [...sub.childNodes].map(n =>
      n.nodeType === 3 ? {t:'#text', len:n.textContent.trim().length}
                       : {t:n.tagName, ...box(n)}) : [],
  };
})()`);

const F = o => o ? JSON.stringify(o) : 'null';
console.log('app  溢出', r.app.over, ' sh', r.app.sh, 'ch', r.app.ch);
console.log('col  溢出', r.col.over, ' sh', r.col.sh, 'ch', r.col.ch);
console.log('head', F(r.head));
console.log('sub ', F(r.sub));
console.log('sel ', F(r.sel));
console.log('btn ', F(r.btn));
console.log('sub 子节点:');
for (const c of r.subChildren) console.log('   ', F(c));
proc.kill('SIGKILL');
