// 回归：确认「干预 vs 对照」那一屏没被 loadNarrative 拆分改坏。
//
// 为什么要专门验：这次把 loadPairMeta() 拆成了两半（配对数据 + 叙述性数据）。
// 拆分点落在函数中间，最典型的失败是 loadPairMeta() 提前 return 或者
// S.pm 没被填上 —— 页面会照常渲染，只是那一屏空着。
// 这里不验「元素存在」，验「点进去真的拿到了配对数据」。
import { launch, Page, CDP } from './cdp_client.mjs';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const R = [];
const rec = (n, p, d) => { R.push({n, p}); console.log(`[${p?'PASS':'FAIL'}] ${n}\n       ${d}`); };

const { proc, version } = await launch({ port: 9415,
  userDataDir: '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_delta',
  windowSize: '1600,1000', url: 'about:blank' });
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
try {
  await page.send('Page.navigate', { url: 'http://127.0.0.1:8917/latent/index.html' });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(()=>{});
  // 等首屏稳定
  for (let i=0;i<25;i++){
    const ok = await page.eval(`!!document.getElementById('extras') &&
      document.getElementById('extras').innerHTML.length > 400`);
    if (ok) break; await sleep(1200);
  }
  rec('R1 首屏先带上了 #extras（叙述性数据已在 boot 里加载）',
      await page.eval(`document.getElementById('extras').innerHTML.length > 400`),
      'len=' + await page.eval(`document.getElementById('extras').innerHTML.length`));

  // 点「干预 vs 对照」标签
  await page.eval(`document.getElementById('tabDelta').click()`);
  let ok = false;
  for (let i=0;i<30;i++){
    ok = await page.eval(`(() => {
      const t = document.getElementById('mainTitle');
      return !!t && /同一条题/.test(t.textContent||'');
    })()`);
    if (ok) break; await sleep(1200);
  }
  const st = await page.eval(`(() => {
    const g=id=>document.getElementById(id);
    return {
      title: (g('mainTitle')||{}).textContent||'',
      sub: (g('mainSub')||{}).textContent||'',
      sideTitle: (g('sideTitle')||{}).textContent||'',
      pairOpts: (g('selPair')||{}).options ? g('selPair').options.length : -1,
      pairRowShown: (g('pairRow')||{style:{}}).style.display,
    };
  })()`);
  rec('R2 点标签后进入 DELTA 视图', ok, `title=${st.title.slice(0,50)}`);
  rec('R3 配对下拉被填了（S.pm 加载成功）', st.pairOpts > 1, `pairOpts=${st.pairOpts}`);
  rec('R4 配对行可见', st.pairRowShown === 'flex', `display=${st.pairRowShown}`);
  rec('R5 侧栏标题是配对内容而非「请选择配对题目」',
      !/请选择配对题目/.test(st.sideTitle) && st.sideTitle.length > 0,
      `sideTitle=${st.sideTitle.slice(0,60)}`);

  // 切回非 DELTA，确认 extras 还在（loadNarrative 幂等，不该被清掉）
  await page.eval(`document.getElementById('tabXY').click()`);
  await sleep(1500);
  rec('R6 切回隐空间视图后 extras 仍在（叙述性数据没被清空）',
      await page.eval(`document.getElementById('extras').innerHTML.length > 400`),
      'len=' + await page.eval(`document.getElementById('extras').innerHTML.length`));

  // 叙述性数据只应 fetch 一次
  const once = await page.eval(`(() => {
    const r=document.querySelector('[data-bmroot]');
    return !!r;
  })()`);
  rec('R7 切来切去之后 backmap 块仍在', once, 'data-bmroot=' + once);
} catch(e){ rec('X 脚本崩了', false, String(e).slice(0,200)); }
finally { cdp.close(); proc.kill('SIGKILL'); }
const p = R.filter(r=>r.p).length;
console.log(`\n=== ${p}/${R.length} passed ===`);
process.exit(p===R.length?0:1);
