// 量一组"可以写进导读层的真实数字"。导读层里的例子必须来自真实渲染状态，
// 并且 verify 脚本会拿这里的取值去核对页面，免得例子和页面各说各话。
import { launch, CDP, Page } from '../browser_verify/cdp_client.mjs';

const ROOT = '/Users/zhourui/code/steer3d';
const PORT = 9362;
const { proc, version } = await launch({
  port: PORT, userDataDir: `${ROOT}/.cache/readability/profile_probe`, url: 'about:blank',
});
const cdp = await CDP.connect(
  `ws://127.0.0.1:${PORT}/devtools/browser/${version.webSocketDebuggerUrl.split('/').pop()}`);
const page = await Page.create(cdp);
await page.nav('http://localhost:8917/latent/index.html');
for (let i = 0; i < 120; i++) {
  const st = await page.eval(`(()=>({l:getComputedStyle(document.getElementById('loading')).display,
    a:getComputedStyle(document.getElementById('app')).visibility,
    r:document.querySelectorAll('#tblTop tr').length}))()`);
  if (st.l === 'none' && st.a === 'visible' && st.r > 0) break;
  await new Promise(r => setTimeout(r, 250));
}
await new Promise(r => setTimeout(r, 800));

function readState() {
  const t = (s) => { const e = document.querySelector(s); return e ? e.textContent.trim() : null; };
  const rows = [...document.querySelectorAll('#tblTop tr')].slice(0, 4).map(r => {
    const c = [...r.querySelectorAll('td')].map(x => x.textContent.replace(/\s+/g, ' ').trim());
    return c;
  });
  return {
    layer: t('#valLayer'), tok: t('#valTok'), raw: t('#stRaw'),
    ent: t('#stEnt'), norm: t('#stNorm'), move: t('#stMove'),
    mainSub: t('#mainSub'), sideTitle: t('#sideTitle'), story: t('#layerStory'),
    top4: rows,
  };
}
const snap = [];
snap.push({ tok: 0, ...await page.eval(readState) });
for (const k of [1, 2, 3, 5]) {
  await page.eval(`(()=>{const e=document.getElementById('rngTok');
    e.value=${k};e.dispatchEvent(new Event('input',{bubbles:true}));
    e.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  await new Promise(r => setTimeout(r, 350));
  snap.push({ tok: k, ...await page.eval(readState) });
}
// 换一道题看看题目/答案/生成文本的真实样子
const opt = await page.eval(`(()=>{const s=document.getElementById('selTraj');
  return [...s.options].map(o=>o.textContent).slice(0,12)})()`);
const pairs = await page.eval(`(()=>fetch('data/pairs/pairs.json').then(r=>r.json()).then(j=>({
  n:j.pairs.length, ids:j.pairs.map(p=>p.id), layer:j.pairs[0].inject_layer,
  dir:j.direction, strength:j.pairs[0].strength})))()`);
const layers = await page.eval(`(()=>{const s=document.getElementById('rngLayer');
  return {min:s.min,max:s.max}})()`);
console.log(JSON.stringify({ snap, opt, pairs, layers }, null, 1));
page.close(); cdp.close(); proc.kill('SIGKILL');
