// r135a_measure_acec.mjs —— A5-A8 + C1-C4 的**只读测量**
//
// 目的：在做派生副本之前，先量清每条判据的
//   ① 读取层是什么（可见文案 / DOM 属性 / computedStyle）
//   ② needle 在页面上的命中次数
//   ③ 有没有「名义有牙齿、实质够不着」的结构（同修订 131 的 C6）
//
// ⚠⚠⚴ 本台**不注入、不扰动、不下判决**，只读页面状态。
// ⚠⚠⚴ 纪律：不自己写正则猜引号配对；页面侧只用 split/join 与 querySelector。
// ⚠⚠⚴ 归属判断用 closest()，不用数目相等。
// ⚠ 开头印 location.href 自证页面身份。

import { launch, Page, CDP } from '/Users/zhourui/code/steer3d/.cache/browser_verify/cdp_client.mjs';
import { readFileSync } from 'node:fs';

const URL = process.env.LAT_URL || 'http://127.0.0.1:9006/latent/index.html';
const ART = '/Users/zhourui/code/steer3d/frontend/public/latent/data/path_readout.json';
const sleep = ms => new Promise(r => setTimeout(r, ms));

const prod = JSON.parse(readFileSync(ART, 'utf8'));

const { proc, version } = await launch({
  port: 9499, userDataDir: '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_r135a_' + process.pid,
  windowSize: '1600,1050', url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);

// 页面侧小工具：数一个子串出现几次（split，不写正则）
const COUNT_FN = `
  window.__count = function (s, sub) {
    if (sub === undefined || sub === '' || sub === null) return -1;
    return String(s).split(sub).length - 1;
  };
`;

try {
  // ---- 页面身份自证 ----
  const href = await page.eval(`location.href`);
  const urlVar = (URL.match(/\/\/[^/]+/) || [''])[0];
  console.log('=== 页面身份 ===');
  console.log(`  location.href = ${href}`);
  console.log(`  探针 URL 变量 = ${urlVar}   ⇒ ${href.indexOf('/latent/') >= 0 ? '✓ 静态产物页' : '⚗ 不是 latent 页'}`);
  console.log(`  被验脚本读的是 LAT_URL（不是 BV_URL）`);

  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  await sleep(3500);

  // 关引导页 + 切到第 5 屏（复刻 verify_path.mjs:86）
  await page.eval(`(() => {
    const ov = document.getElementById('orientation'); const b = document.getElementById('orientClose');
    if (ov && !ov.classList.contains('hide') && b) b.click();
    document.querySelector('#tabPath').click();
  })()`);
  await sleep(2500);
  await page.eval(COUNT_FN);

  const state = await page.eval(`document.querySelector('[data-pathblock]') ? document.querySelector('[data-pathblock]').getAttribute('data-pathstate') : 'ABSENT'`);
  const pid = await page.eval(`(()=>{const b=document.querySelector('[data-pathblock]'); return b?b.getAttribute('data-pathpid'):null;})()`);
  const q0 = prod.problems[pid];
  console.log(`  state=${state}  pid=${pid}  产物 k=${q0 && q0.k}  n_cand=${prod.n_cand}`);
  console.log('');

  // ================= A 组 =================
  console.log('=== A 组读取层（逐条：判据表达式 / 读什么 / 实测值）===');

  const A = JSON.parse(await page.eval(`JSON.stringify((() => {
    const q = s => document.querySelector(s);
    const mt = q('#mainTitle');
    const tab = q('#tabPath');
    const pr = q('#pairRow');
    const cv = q('#cv');
    return {
      mainTitle: (mt||{}).textContent || '',
      mainTitleTag: mt ? mt.tagName : 'ABSENT',
      tabClass: (tab||{}).className || '',
      tabClassTag: tab ? tab.tagName : 'ABSENT',
      pairRowDisplay: pr ? getComputedStyle(pr).display : 'ELEMENT_ABSENT',
      cvDisplay: cv ? getComputedStyle(cv).display : 'ELEMENT_ABSENT',
      T: q('#pathWrap') ? q('#pathWrap').innerText : '',
    };
  })())`));

  // A5
  const a5a = A.mainTitle.split('逐步路径').length - 1;
  const a5b = A.mainTitle.split(String(pid)).length - 1;
  console.log(`\n  A5  主标题指明这是哪一题`);
  console.log(`      判据   : mainTitle.includes('逐步路径') && mainTitle.includes(pid||'?')`);
  console.log(`      读取层 : <${A.mainTitleTag}> 的 textContent（**可见文案**）`);
  console.log(`      实测   : "${A.mainTitle}"`);
  console.log(`      needle : '逐步路径' ×${a5a}   pid='${pid}' ×${a5b}`);
  console.log(`      ⇒ 删除 1 处即可翻面：${a5a >= 1 && a5b >= 1 ? '✓ 够得着' : '⚗ 有 0 次项（空洞风险）'}`);

  // A6
  console.log(`\n  A6  配对题目下拉可见（读者能换题）`);
  console.log(`      判据   : d.pairRow === 'flex'`);
  console.log(`      读取层 : getComputedStyle(#pairRow).display`);
  console.log(`      实测   : display=${A.pairRowDisplay}`);
  console.log(`      扰动   : 把 display 改成 'none' 即可翻面（元素须保留）`);
  console.log(`      ⚗⚗⚗ 若**删掉** #pairRow：getComputedStyle(null) 抛 TypeError`);
  console.log(`             ⇒ 与 D5 同族（崩而非红），但 A6 的读取层同样没有空值保护`);

  // A7
  console.log(`\n  A7  画布已让位`);
  console.log(`      判据   : d.cv === 'none'`);
  console.log(`      读取层 : getComputedStyle(#cv).display`);
  console.log(`      实测   : display=${A.cvDisplay}`);
  console.log(`      ⚠⚠⚴ 极性与其他条相反：它断言的是 display==='none'`);
  console.log(`      ⇒ 扰动方向必须是把 #cv 变回可见（block/flex），**不是删元素**`);

  // A8 —— 重点
  console.log(`\n  A8  第 5 个标签是高亮的`);
  console.log(`      判据   : String(d.tabOn).includes('on')`);
  console.log(`      读取层 : <${A.tabClassTag}> 的 className（**属性，不是可见文案**）`);
  console.log(`      实测   : class="${A.tabClass}"`);
  const onCount = A.tabClass.split('on').length - 1;
  const toks = A.tabClass.split(/\s+/).filter(Boolean);
  console.log(`      class 切成 ${toks.length} 个记号: ${toks.map(t => '[' + t + ']').join(' ')}`);
  console.log(`      ⚠⚠⚴⚠ 子串 'on' 在整串里出现 ${onCount} 次`);
  const onToks = toks.filter(t => t.split('on').length - 1 > 0);
  console.log(`      含 'on' 的记号共 ${onToks.length} 个: ${onToks.map(t => '[' + t + ']').join(' ')}`);
  if (onToks.length > 1) {
    console.log(`      ⚠⚠⚴⚠⚠ **命中 ${onCount} 处、来自 ${onToks.length} 个不同记号**`);
    console.log(`         ⇒ 删掉「真的高亮记号」一个，剩余记号里的 'on' 仍能让 includes() 为真`);
    console.log(`         ⇒ 同修订 131 的 C6：**名义有牙齿、实质够不着**（要删 ${onCount} 处才翻面）`);
  } else if (onCount >= 1) {
    console.log(`      ⇒ 'on' 全部来自同一个记号 ⇒ 删 1 处就翻面 ✓ 够得着`);
  } else {
    console.log(`      ⚗ 0 次 ⇒ 基线就通不过，与 D5/修订 131 同族的空洞风险`);
  }

  // ================= C 组：纪律检查 =================
  console.log('\n\n=== C 组 C1-C4：读的是 data-* 属性还是可见文案？===');
  const C = JSON.parse(await page.eval(`JSON.stringify((() => {
    const rows = [...document.querySelectorAll('[data-patht]')];
    const forks = rows.filter(r => r.getAttribute('data-pathfork') === '1');
    const blk = document.querySelector('[data-pathblock]');
    return {
      k: blk ? blk.getAttribute('data-pathk') : null,
      nRows: rows.length,
      nForks: forks.length,
      forkT: forks.map(r => r.getAttribute('data-patht')),
      candPerArm: rows.length ? rows[rows.length-1].children[1].children.length : -1,
      firstForkCand: forks.length ? forks[0].children[1].children.length : -1,
      nForkRows: forks.length,
    };
  })())`));

  console.log(`\n  C1 屏上 k 与产物一致`);
  console.log(`      判据   : String(q0.k) === String(d.k)`);
  console.log(`      读取层 : [data-pathblock] 的 **data-pathk 属性**`);
  console.log(`      实测   : 屏 ${C.k} / 产物 ${q0.k}`);
  console.log(`      ⚠⚠⚴ 纪律冲突候选：判据主体是 **data-* 属性**，不是可见文案`);
  console.log(`      ⚠ 读者在屏上能看到「k=${q0.k}」这个数吗？下面单量。`);

  console.log(`\n  C2 分叉行恰好 1 行且 t=k`);
  console.log(`      判据   : d.nForks === 1 && d.forkT[0] === String(q0.k)`);
  console.log(`      读取层 : [data-patht] 中 data-pathfork==='1' 的行数与它们的 data-patht`);
  console.log(`      实测   : nForks=${C.nForks} @${JSON.stringify(C.forkT)} / 产物 k=${q0.k}`);
  console.log(`      ⚠⚠⚴ 同样只读 data-* 属性，屏上无对应文案`);

  console.log(`\n  C3 默认只看分叉前后 ±5 步`);
  console.log(`      判据   : d.nRows === Math.min(6, q0.k+1)`);
  console.log(`      读取层 : [data-patht] 的**行数**`);
  console.log(`      实测   : nRows=${C.nRows} / 期望 ${Math.min(6, q0.k + 1)}`);
  console.log(`      ⚠⚠⚴⚠ 行数是**结构属性**。判据名说「±5 步」，读者看到的是文字「±5 步」还是只看到 6 行？`);

  console.log(`\n  C4 默认每臂 2 个候选`);
  console.log(`      判据   : d.candPerArm === 2`);
  console.log(`      读取层 : 最后一行的 children[1].children.length`);
  console.log(`      实测   : 末行 candPerArm=${C.candPerArm} / 分叉行 candPerArm=${C.firstForkCand}`);
  console.log(`      ⚠⚠⚴ 「每臂 2 个候选」这个口径，屏上有没有**印出来**？下面单量。`);

  // ---- 纪律检查：这些口径在可见文案里有没有 ----
  console.log('\n\n=== ⚠⚠⚴⚠ 纪律检查：C1-C4 的口径，读者在屏上能不能看见？===');
  console.log(`（本页 #pathWrap.innerText 共 ${A.T.length} 字）\n`);
  const probes = [
    ['C1 k 值', String(q0.k)],
    ['C1 口径词「步」', '步'],
    ['C3 口径词「±5」', '±5'],
    ['C3 口径词「+5」', '+5'],
    ['C3 口径词「前后」', '前后'],
    ['C3 口径词「默认」', '默认'],
    ['C4 口径词「候选」', '候选'],
    ['C4 口径词「2 个」', '2 个'],
    ['C4 口径词「两个」', '两个'],
    ['C2 口径词「分叉」', '分叉'],
  ];
  for (const [label, needle] of probes) {
    const n = A.T.split(needle).length - 1;
    console.log(`  ${label.padEnd(22, ' ')} needle=${JSON.stringify(needle).padEnd(12)} 屏上 ×${n}`);
  }

  // 「±5 步」这类口径的归属：用 closest 判断它落在哪一屏
  const owner = JSON.parse(await page.eval(`JSON.stringify((() => {
    const q = s => document.querySelector(s);
    const T = q('#pathWrap') ? q('#pathWrap').innerText : '';
    // 逐屏看有没有 ±5 / 候选 这类口径词
    const screens = [...document.querySelectorAll('[data-screen], .screen, section, [id^=screen]')].map(e => ({
      id: e.id || e.getAttribute('data-screen') || '(no-id)', len: (e.innerText||'').length,
    }));
    return { screens: screens.slice(0, 12) };
  })())`));
  console.log(`\n  页面上的候选容器（供定位口径归属用）:`);
  for (const s of owner.screens) console.log(`    ${String(s.id).padEnd(20)} innerText ${s.len} 字`);

  console.log('\n\n=== 汇总：本台只读，未注入 ===');
  console.log('  A5 读可见文案   ⇒ 扰动：改 #mainTitle 的 textContent（删 pid 或删「逐步路径」）');
  console.log('  A6/A7 读 computedStyle ⇒ 扰动：改 display，**保留元素**（删元素会崩，同 D5 族）');
  console.log('  A8 读 className  ⇒ 见上：命中次数决定够不够得着');
  console.log('  C1/C2/C3/C4 读 data-* 属性 ⇒ 扰动改属性即可，但触发纪律问题（见上）');
} catch (e) {
  console.log('[装置错]', String(e && e.message ? e.message : e));
} finally {
  try { await cdp.send('Browser.close'); } catch {}
  try { proc.kill(); } catch {}
}