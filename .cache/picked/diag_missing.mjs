import { launch, CDP, Page } from '../browser_verify/cdp_client.mjs';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const PORT = Number(process.env.BV_PORT || 9810);
const { proc, version } = await launch({ port: PORT, userDataDir: new URL('./profile_'+PORT, import.meta.url).pathname, windowSize: '1600,1000', url: 'about:blank' });
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
await page.send('Network.enable'); await page.send('Network.setCacheDisabled',{cacheDisabled:true});
await page.send('Page.enable'); await page.send('Runtime.enable');
await page.send('Page.navigate', { url: 'http://127.0.0.1:8917/latent/index.html' });
for (let i=0;i<30;i++){ await sleep(1000);
  const ok = await page.eval(`(()=>{try{return !!(window.S||S)&&S.m&&S.m.trajectories.length>0}catch(e){return false}})()`);
  if(ok) break; }
await page.eval(`(()=>{ S.tok=60; S.view="XY"; render(); })()`);
await sleep(800);
const r = await page.eval(`(()=>{
  const t = S.m.trajectories[S.ti].tokens;
  let m=0; for(let k=0;k<t.length;k++) if(t[k].ent>m) m=t[k].ent;
  const cv=document.querySelector('#cv'), W=cv.clientWidth, H=cv.clientHeight;
  // recompute the scatter's own mapping is not exposed; sample the same
  // loop drawXY uses by re-deriving sx/sy from the canvas size
  const out=[];
  for(let k=0;k<60;k++){
    const c = entColor(t[k].ent, m).replace(/^rgb\\(|\\)$/g,'');
    // where would it land? ask the page for the drawn pixel neighbourhood is
    // not possible, so report colour + entropy only
    out.push([k, c, +t[k].ent.toFixed(4)]);
  }
  return {W,H,out};
})()`);
console.log('canvas', r.W+'x'+r.H);
console.log('step  colour           entropy');
for(const [k,c,e] of r.out.slice(0,12)) console.log(`  ${String(k).padStart(2)}   ${c.padEnd(16)} ${e}`);
try{proc.kill('SIGKILL');}catch{} cdp.ws.close();
