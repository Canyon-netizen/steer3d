// 紧凑版事实探针：只打一行一个 token，供导读层选例子用。
import { launch, CDP, Page } from '../browser_verify/cdp_client.mjs';
const ROOT = '/Users/zhourui/code/steer3d';
const PORT = 9363;
const { proc, version } = await launch({
  port: PORT, userDataDir: `${ROOT}/.cache/readability/profile_probe2`, url: 'about:blank',
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
function line() {
  const t = s => (document.querySelector(s) || {}).textContent || '';
  const rows = [...document.querySelectorAll('#tblTop tr')].slice(0, 3);
  const top = rows.map(r => [...r.querySelectorAll('td')]
    .map(x => x.textContent.replace(/\s+/g, ' ').trim())
    .filter((v, i) => i !== 2).join('|'));
  return [t('#valLayer').trim(), t('#stRaw').trim(), t('#stEnt').trim(),
          t('#stNorm').trim(), t('#stMove').trim(), top.join('  ')].join('   ');
}
for (let k = 0; k <= 8; k++) {
  if (k) {
    await page.eval(`(()=>{const e=document.getElementById('rngTok');e.value=${k};
      e.dispatchEvent(new Event('input',{bubbles:true}));})()`);
    await new Promise(r => setTimeout(r, 300));
  }
  console.log('tok=' + String(k).padStart(2), await page.eval(line));
}
// L0 与 L27 的对比（"点云随层变化"的真实数字）
for (const L of [0, 7, 14, 21, 27]) {
  await page.eval(`(()=>{const e=document.getElementById('rngLayer');e.value=${L};
    e.dispatchEvent(new Event('input',{bubbles:true}));})()`);
  await new Promise(r => setTimeout(r, 350));
  console.log('L' + String(L).padStart(2), await page.eval(line));
}
const gen = await page.eval(`(()=>{const e=document.getElementById('genTxt');
  return (e.textContent||'').replace(/\\s+/g,' ').trim().slice(0,200)})()`);
console.log('GEN:', gen);
page.close(); cdp.close(); proc.kill('SIGKILL');
