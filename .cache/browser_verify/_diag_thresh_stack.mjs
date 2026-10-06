// 查遮挡链：threshWrap 与那个导读段在 DOM 里到底是不是兄弟/父子，
// 谁的 position/z-index 把它压在下面。纯读，不改。
import { launch, Page, CDP } from './cdp_client.mjs';
const URL = process.env.LAT_URL || 'http://127.0.0.1:22234/latent/index.html';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const { proc, version } = await launch({ port: 9492,
  userDataDir: '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_diagstack_' + process.pid,
  windowSize: '1600,1050', url: 'about:blank' });
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  await sleep(3500);
  await page.eval(`document.getElementById('tabThresh').click()`);
  await sleep(2500);
  const out = await page.eval(`JSON.stringify((() => {
    const tw = document.getElementById('threshWrap');
    const lead = document.querySelector('[data-lead-seg="4"]');
    const cs = e => { const c = getComputedStyle(e); const r = e.getBoundingClientRect();
      return { pos:c.position, z:c.zIndex, disp:c.display, ovf:c.overflow,
               rect:[Math.round(r.x),Math.round(r.y),Math.round(r.width),Math.round(r.height)] }; };
    // 祖先链
    const chain = e => { const o=[]; while(e && e!==document.body){ o.push(
      e.tagName+(e.id?'#'+e.id:'')+(typeof e.className==='string'&&e.className?'.'+e.className.split(' ')[0]:'')
      +' ['+getComputedStyle(e).position+'/'+getComputedStyle(e).display+']'); e=e.parentElement; } return o; };
    const desc = e => e ? (e.tagName+(e.id?'#'+e.id:'')
      +(typeof e.className==='string'&&e.className?'.'+e.className.split(' ')[0]:'')) : 'null';
    let a = tw, b = lead; const sa = new Set();
    while (a) { sa.add(a); a = a.parentElement; }
    let common = 'none';
    while (b) { if (sa.has(b)) { common = desc(b); break; } b = b.parentElement; }
    return { thresh: cs(tw), lead: cs(lead),
             threshChain: chain(tw), leadChain: chain(lead),
             sameParent: tw.parentElement === lead.parentElement,
             commonAncestor: common };
  })())`);
  const o = JSON.parse(out);
  console.log('threshWrap :', JSON.stringify(o.thresh));
  console.log('lead-seg=4 :', JSON.stringify(o.lead));
  console.log('同父节点?  :', o.sameParent);
  console.log('共同祖先  :', o.commonAncestor);
  console.log('\nthreshWrap 祖先链:'); o.threshChain.forEach((x,i)=>console.log('  '.repeat(i+1)+x));
  console.log('\nlead-seg=4 祖先链:'); o.leadChain.forEach((x,i)=>console.log('  '.repeat(i+1)+x));
} finally { cdp.close(); proc.kill('SIGKILL'); }
