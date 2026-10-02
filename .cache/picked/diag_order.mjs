import { launch, CDP, Page } from '../browser_verify/cdp_client.mjs';
import { readFileSync } from 'node:fs';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const DATA = 'frontend/public/latent/data/';
const K = 64;
const f32 = new Float32Array(readFileSync(DATA+'topk_00.bin').buffer);
const i32 = new Int32Array(readFileSync(DATA+'topki_00.bin').buffer);
const ids = JSON.parse(readFileSync(DATA+'vocab.json','utf8')).ids;
const file = [];
for (let k=0;k<K;k++) file.push({l:f32[k], id:i32[k]});
console.log('--- 文件前 10（未排序）---');
file.slice(0,10).forEach((r,i)=>console.log(` #${i+1} logit=${r.l.toFixed(3)} ${JSON.stringify(ids[r.id])}`));
const sorted = [...file].sort((a,b)=>b.l-a.l);
console.log('--- 文件前 10（按 logit 降序）---');
sorted.slice(0,10).forEach((r,i)=>console.log(` #${i+1} logit=${r.l.toFixed(3)} ${JSON.stringify(ids[r.id])}`));
const reg = await (await fetch('http://127.0.0.1:8917/latent/models.json')).json();
const big = reg.models.find(m => m.d_model === 2048);
const { proc, version } = await launch({ port: 9389,
  userDataDir: '/Users/zhourui/code/steer3d/.cache/picked/diagprofile', url: 'about:blank' });
const cdp = await CDP.connect(`ws://127.0.0.1:9389/devtools/browser/${version.webSocketDebuggerUrl.split('/').pop()}`);
const page = await Page.create(cdp);
await page.send('Network.enable');
await page.send('Page.navigate', { url: `http://127.0.0.1:8917/latent/index.html?orient=reset&m=${big.id}` });
await page.waitForEvent('Page.loadEventFired', 40000);
await sleep(2500);
await page.eval(`(()=>{const b=[...document.querySelectorAll('button')].find(x=>/开始看|我读完了/.test(x.textContent)); if(b) b.click();})()`);
await sleep(600);
const out = await page.eval(`(()=>{
  S.ti=0; S.tok=0; S.view='BAR'; render();
  const rows=[...document.querySelectorAll('#tblTop tr')].slice(1,11)
    .map(tr=>[tr.querySelector('td.n')?tr.querySelector('td.n').textContent:null,
              tr.querySelector('td.tok')?tr.querySelector('td.tok').textContent:null,
              tr.querySelectorAll('td')[2]?tr.querySelectorAll('td')[2].textContent:null]);
  const raw=[]; for(let k=0;k<10;k++) raw.push([S.topk[k], S.topki[k]]);
  return {rows, raw};
})()`);
console.log('--- 页面渲染的前 10 ---');
out.rows.forEach(r=>console.log(` #${r[0]} ${JSON.stringify(r[1])}  ${r[2]}`));
console.log('--- 页面 S.topk[0..10] ---');
out.raw.forEach((r,i)=>console.log(` [${i}] logit=${r[0].toFixed(3)} id=${r[1]} ${JSON.stringify(ids[r[1]])}`));
process.exit(0);
