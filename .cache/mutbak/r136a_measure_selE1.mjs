// r136a_measure_selE1.mjs —— 只读测量：E1 的扰动可行性 + D3/D4 为何跳过
//
// 两条待查：
//   ① E1 判 `typeof renderPathPanel === 'function'`，而它读的是**裸名**。
//      扰动只能设 `window.renderPathPanel`。若页面用 `let/const` 声明（不挂 window），
//      裸名仍指向原声明 ⇒ 扰动**无效** ⇒ 这个臂验不了。必须先查清。
//   ② 产物 `path_readout.json` 有 **6 道**题（共享台刚因「只有 1 道」报错退出），
//      而实测 `#selPair` 找不到第二个选项 ⇒ 页面只让选 1 道。
//      ⚠⚠⚴ 这两件事对不上：读者到底能不能看到其余 5 道？
//
// ⚠ 本台只读，不注入、不扰动、不下判决。
// ⚠ 身份自证在导航**之后**，失败即 exit 2（修订 135 固化）。
// ⚠ 页面侧不写正则，用 split/join。

import { launch, Page, CDP } from '/Users/zhourui/code/steer3d/.cache/browser_verify/cdp_client.mjs';
import { readFileSync } from 'node:fs';

const URL = process.env.LAT_URL || 'http://127.0.0.1:9006/latent/index.html';
const ART = '/Users/zhourui/code/steer3d/frontend/public/latent/data/path_readout.json';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const prod = JSON.parse(readFileSync(ART, 'utf8'));

const { proc, version } = await launch({
  port: 9501, userDataDir: '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_r136a_' + process.pid,
  windowSize: '1600,1050', url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);

try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  await sleep(3500);
  await page.eval(`(() => {
    const ov = document.getElementById('orientation'); const b = document.getElementById('orientClose');
    if (ov && !ov.classList.contains('hide') && b) b.click();
    document.querySelector('#tabPath').click();
  })()`);
  await sleep(2500);

  // ---- 身份自证（导航后；任一不过即 exit 2）----
  const href = await page.eval(`location.href`);
  const wrapLen = await page.eval(`document.querySelector('#pathWrap') ? document.querySelector('#pathWrap').innerText.length : -1`);
  const pid = await page.eval(`(()=>{const b=document.querySelector('[data-pathblock]'); return b?b.getAttribute('data-pathpid'):null;})()`);
  console.log('=== 页面身份 ===');
  console.log(`  location.href = ${href}`);
  console.log(`  #pathWrap = ${wrapLen} 字（应为 1267）   pid=${pid}`);
  const idOK = href.indexOf('/latent/index.html') >= 0 && wrapLen === 1267 && !!prod.problems[pid];
  console.log(`  ⇒ ${idOK ? '✓ 三道交叉自证全过' : '⚗ 不符'}`);
  if (!idOK) { console.log('[身份自证失败] 不出数'); process.exit(2); }

  // ---- ① 产物里有几道题 ----
  const pids = Object.keys(prod.problems);
  console.log(`\n=== ① 产物 path_readout.json ===`);
  console.log(`  problems 的键共 ${pids.length} 个：`);
  for (const k of pids) console.log(`    ${k}   k=${prod.problems[k].k}`);

  // ---- ② 页面上能选几道 ----
  const sel = JSON.parse(await page.eval(`JSON.stringify((() => {
    const s = document.querySelector('#selPair');
    if (!s) return { absent: true };
    return {
      tagName: s.tagName,
      optionCount: s.options.length,
      options: [...s.options].map((o, i) => ({ i, value: o.value, text: o.textContent })),
      selectedIndex: s.selectedIndex,
      // 页面上还提到别的 pid 吗？逐个查
      presentOnPage: {},
    };
  })())`));
  console.log(`\n=== ② 页面上的 #selPair ===`);
  if (sel.absent) {
    console.log(`  ⚗ #selPair 不存在`);
  } else {
    console.log(`  <${sel.tagName}>  optionCount = **${sel.optionCount}**  selectedIndex=${sel.selectedIndex}`);
    sel.options.forEach(o => console.log(`    [${o.i}] value=${JSON.stringify(o.value)}  text=${JSON.stringify(o.text)}`));
    console.log(`\n  ⚠⚠⚴⚠ 产物有 ${pids.length} 道题，而下拉只有 **${sel.optionCount}** 个选项。`);
  }

  // ---- ③ 其余 pid 在页面上有没有任何痕迹 ----
  const traces = JSON.parse(await page.eval(`JSON.stringify((() => {
    const wrap = document.querySelector('#pathWrap');
    const T = wrap ? wrap.innerText : '';
    const doc = document.documentElement.innerHTML;
    const out = {};
    for (const k of ${JSON.stringify(pids)}) {
      out[k] = {
        inPathWrapText: T.indexOf(k) >= 0,
        inWholePageHtml: doc.indexOf(k) >= 0,
      };
    }
    return out;
  })())`));
  console.log(`\n=== ③ 每一道题的 pid 在页面上出现过吗 ===`);
  console.log(`  ${'pid'.padEnd(12)} ${'#pathWrap 文案'.padEnd(16)} 整页 HTML`);
  for (const k of pids) {
    const t = traces[k];
    console.log(`  ${k.padEnd(12)} ${(t.inPathWrapText ? '有' : '—').padEnd(18)} ${t.inWholePageHtml ? '有' : '—'}`);
  }
  const invisible = pids.filter(k => !traces[k].inWholePageHtml);
  console.log(`\n  ⚠⚠⚴⚠ **整页 HTML 里找不到的 pid：${invisible.length} 个** → ${invisible.join(', ') || '（无）'}`);
  if (invisible.length) {
    console.log(`  ⇒ **读者在页面上无法访问这 ${invisible.length} 道题**，`);
    console.log(`     而产物里有它们的完整读出。⚠⚠⚴ 这是产品侧的可见性问题，不是判据问题。`);
  }

  // ---- ④ E1 的扰动可行性：裸名 vs window. ----
  const e1 = JSON.parse(await page.eval(`JSON.stringify({
    bare: typeof renderPathPanel,
    win: typeof window.renderPathPanel,
    same: (typeof renderPathPanel) === (typeof window.renderPathPanel),
  })`));
  console.log(`\n=== ④ E1 的读取层与扰动可行性 ===`);
  console.log(`  判据 E1：check('E1 渲染函数存在…', typeof renderPathPanel === 'function')`);
  console.log(`  裸名  typeof renderPathPanel      = ${e1.bare}`);
  console.log(`  window typeof window.renderPathPanel = ${e1.win}`);
  console.log(`  两者是否一致 = ${e1.same}`);
  if (e1.same) {
    console.log(`  ⇒ ⚠ 设 \`window.renderPathPanel = undefined\` 会让裸名也变 undefined ⇒ E1 可扰动`);
    console.log(`  ⇒ occ 可定义为 String(typeof window.renderPathPanel).split('function').length-1`);
  } else {
    console.log(`  ⚠⚠⚴⚠⚠ 两者不一致 ⇒ 裸名不是 window 上的属性（多半是 let/const 顶层声明）`);
    console.log(`     ⇒ 设 window.renderPathPanel **不会影响裸名** ⇒ 该扰动无效 ⇒ E1 验不了`);
    console.log(`     ⇒ 需要换扰动手法，或按「无法判定」记`);
  }

  // ---- ⑤ E1 核的是「函数存在」，不是「缺数据时会喊缺」 ----
  console.log(`\n=== ⑤ E1 的名义 vs 实际 ===`);
  console.log(`  判据名：'E1 渲染函数存在（缺数据时才有人喊缺）'`);
  console.log(`  实际断言：\`typeof renderPathPanel === 'function'\``);
  console.log(`  ⚠⚠⚴ 只证明「函数在」，**不证明「缺数据时它会喊缺」**。`);
  console.log(`  ⇒ 删除函数能让 E1 转红（够得着），`);
  console.log(`  ⇒ 但「够得着」≠「核到了判据名说的那件事」。`);
} catch (e) {
  console.log('[装置错]', String(e && e.message ? e.message : e));
} finally {
  try { await cdp.send('Browser.close'); } catch {}
  try { proc.kill(); } catch {}
}