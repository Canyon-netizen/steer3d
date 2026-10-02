import { launch, CDP, Page } from '../browser_verify/cdp_client.mjs';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const PORT = Number(process.env.BV_PORT || 9560);
const { proc, version } = await launch({ port: PORT, userDataDir: new URL('./profile_'+PORT, import.meta.url).pathname, windowSize: '1600,800', url: 'about:blank' });
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
await page.send('Network.enable'); await page.send('Network.setCacheDisabled',{cacheDisabled:true});
await page.send('Page.enable'); await page.send('Runtime.enable');
await page.send('Page.navigate', { url: (process.env.FRONTEND||'http://127.0.0.1:8917/latent/index.html') });
for (let i=0;i<30;i++){ await sleep(1000);
  const ok = await page.eval(`(()=>{try{return !!(window.S||S)&&S.m&&S.m.trajectories.length>0}catch(e){return false}})()`);
  if(ok) break; }
const m = await page.eval(`(()=>{
  const tb=document.querySelector('#tblTop'), sc=tb.parentElement;
  const col=sc.closest('aside')||sc.parentElement;
  const rows=[...document.querySelectorAll('#tblTop tr')];
  const note=rows[rows.length-1];
  const picked=document.querySelector('#picked');
  return {
    winH: innerHeight,
    scrollH: sc.scrollHeight, clientH: sc.clientHeight, overflow: sc.scrollHeight-sc.clientHeight,
    nRows: rows.length,
    rowsH: rows.slice(0,-1).reduce((a,r)=>a+r.getBoundingClientRect().height,0),
    noteH: note ? note.getBoundingClientRect().height : 0,
    pickedH: picked ? picked.getBoundingClientRect().height : 0,
    colH: col.getBoundingClientRect().height,
    colScroll: col.scrollHeight,
  };
})()`);
console.log(JSON.stringify(m, null, 2));
try{proc.kill('SIGKILL');}catch{} cdp.ws.close();
