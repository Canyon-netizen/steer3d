// 一次性排查：导读层打开时，哪些"可见块"没被标成 inOrient？
import { launch, CDP, Page } from '../browser_verify/cdp_client.mjs';
import * as P from './probe_lib.mjs';
const ROOT = '/Users/zhourui/code/steer3d';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const { proc, version } = await launch({
  port: 9395, userDataDir: `${ROOT}/.cache/readability/profile_dbg`, url: 'about:blank',
});
const cdp = await CDP.connect(
  `ws://127.0.0.1:9395/devtools/browser/${version.webSocketDebuggerUrl.split('/').pop()}`);
const page = await Page.create(cdp);
await page.send('Storage.clearDataForOrigin',
  { origin: 'http://localhost:8917', storageTypes: 'local_storage' });
await page.nav('http://localhost:8917/latent/index.html');
for (let i = 0; i < 160; i++) {
  const st = await page.eval(`(()=>({l:getComputedStyle(document.getElementById('loading')).display,
    r:document.querySelectorAll('#tblTop tr').length}))()`);
  if (st.l === 'none' && st.r > 0) break;
  await sleep(250);
}
await sleep(900);
const r = await page.eval(`(()=>{const f=${P.collectVisible.toString()};
  return f(null);})()`);
const bad = r.blocks.filter(b => !b.inOrient);
console.log('total', r.blocks.length, 'notInOrient', bad.length);
for (const b of bad) console.log('  ', b.sel, '@', b.x, b.y, '|', b.text.slice(0, 60));
const hit = await page.eval(`(()=>{const e=document.elementFromPoint(800,500);
  return e?e.tagName+'.'+e.className+'#'+e.id:'null';})()`);
console.log('elementFromPoint(800,500) =', hit);
page.close(); cdp.close(); proc.kill('SIGKILL');
