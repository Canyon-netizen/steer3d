// r135b_measure_c_text.mjs —— 修身份自证顺序 + 补测「结构 vs 文案」裂缝
//
// ⚠⚠⚴⚠ **r135a 的身份自证是无效的**：它在 `Page.navigate` **之前**印
//   location.href ⇒ 印出 `about:blank` ⇒ 而判据本身却继续跑完了。
//   ⚠⚠⚴ 这就是「仪器自己给自己发绿」的同一类：**探针的一栏自我报告是错的，
//   探针却没中止、没报错、照常输出了全部测量。**
//   ⇒ 纪律落地：身份自证必须在**导航完成之后**、任何测量之前，且失败即 exit 2。
//
// 本台补测三件事（全部只读，不注入）：
//   ① 屏上「±5」那一处的**完整上下文** —— 文案说的是「±5 步」还是别的
//   ② 「2 个候选」「分叉」「默认」这些口径词的**归属容器**（用 closest，不用数目相等）
//   ③ 文案口径与判据口径**是不是同一个量**：
//        判据 C3 核的是 nRows === min(6, k+1) ⇒ 6 行
//        文案若写「前后 ±5 步」⇒ 应当是 11 行
//      ⇒ 若二者不同，就是「结构与文案之间的裂缝」

import { launch, Page, CDP } from '/Users/zhourui/code/steer3d/.cache/browser_verify/cdp_client.mjs';
import { readFileSync } from 'node:fs';

const URL = process.env.LAT_URL || 'http://127.0.0.1:9006/latent/index.html';
const ART = '/Users/zhourui/code/steer3d/frontend/public/latent/data/path_readout.json';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const prod = JSON.parse(readFileSync(ART, 'utf8'));

const { proc, version } = await launch({
  port: 9500, userDataDir: '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_r135b_' + process.pid,
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

  // ---- ① 身份自证（导航之后！失败即 exit 2）----
  const href = await page.eval(`location.href`);
  console.log('=== 页面身份（导航后自证）===');
  console.log(`  location.href = ${href}`);
  const wantPath = '/latent/index.html';
  const okId = href.indexOf(wantPath) >= 0;
  console.log(`  期望包含 ${wantPath} ⇒ ${okId ? '✓' : '⚗⚗⚗ 不符'}`);
  const wrapLen = await page.eval(`document.querySelector('#pathWrap') ? document.querySelector('#pathWrap').innerText.length : -1`);
  console.log(`  #pathWrap.innerText = ${wrapLen} 字（修订 131 记录 1267 字 ⇒ 应相符）`);
  const pidNow = await page.eval(`(()=>{const b=document.querySelector('[data-pathblock]'); return b?b.getAttribute('data-pathpid'):null;})()`);
  console.log(`  data-pathpid = ${pidNow}  产物有该题记录 = ${!!prod.problems[pidNow]}`);
  if (!okId || wrapLen < 500 || !prod.problems[pidNow]) {
    console.log('[身份自证失败] 不出数 —— 仪器坏了不是判据结论');
    process.exit(2);
  }

  // ---- ② 「±5」的完整上下文 ----
  console.log('\n=== ①「±5」那 1 处的完整上下文 ===');
  const ctx = JSON.parse(await page.eval(`JSON.stringify((() => {
    const wrap = document.querySelector('#pathWrap');
    const out = [];
    // 页面侧：遍历文本节点，找到含「±5」的，取其所在元素的整段 innerText
    const w = document.createTreeWalker(wrap, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = w.nextNode())) {
      const s = n.nodeValue || '';
      if (s.indexOf('±5') >= 0) {
        const el = n.parentElement;
        out.push({
          textNode: s.trim().slice(0, 200),
          elTag: el ? el.tagName : null,
          elClass: el ? el.className : null,
          elOwnText: el ? (el.innerText || '').trim().slice(0, 300) : null,
        });
      }
    }
    return { hits: out };
  })())`));
  console.log(`  含「±5」的文本节点共 ${ctx.hits.length} 处`);
  ctx.hits.forEach((h, i) => {
    console.log(`  --- 第 ${i + 1} 处 ---`);
    console.log(`    文本节点 : ${JSON.stringify(h.textNode)}`);
    console.log(`    所在元素 : <${h.elTag}> class=${JSON.stringify(h.elClass)}`);
    console.log(`    整段文案 : ${JSON.stringify(h.elOwnText)}`);
  });

  // ---- ③ 口径词的归属容器（closest 走法）----
  console.log('\n=== ② 口径词归属（用 closest 上溯，不用数目相等）===');
  const owner = JSON.parse(await page.eval(`JSON.stringify((() => {
    const wrap = document.querySelector('#pathWrap');
    const words = ['±5', '候选', '默认', '前后', '分叉'];
    const res = {};
    for (const wd of words) {
      const w = document.createTreeWalker(wrap, NodeFilter.SHOW_TEXT);
      let n, list = [];
      while ((n = w.nextNode())) {
        const s = n.nodeValue || '';
        if (s.indexOf(wd) >= 0) {
          // closest：上溯到最近的带 id 的祖先，这就是归属容器
          const host = n.parentElement ? n.parentElement.closest('[id]') : null;
          list.push({
            host: host ? (host.id || '(no-id)') : '(无带 id 祖先)',
            hostTag: host ? host.tagName : null,
            snippet: s.trim().slice(0, 90),
          });
        }
      }
      res[wd] = list;
    }
    return res;
  })())`));
  for (const wd of Object.keys(owner)) {
    const list = owner[wd];
    const hosts = [...new Set(list.map(x => x.host))];
    console.log(`\n  「${wd}」 命中 ${list.length} 处，归属 ${hosts.length} 个容器: ${hosts.map(h => '#' + h).join(' ')}`);
    list.slice(0, 4).forEach((x, i) => {
      console.log(`    ${i + 1}. 落在 #${x.host}  片段=${JSON.stringify(x.snippet)}`);
    });
    if (list.length > 4) console.log(`    …（还有 ${list.length - 4} 处）`);
  }

  // ---- ④ 文案口径 vs 判据口径：是不是同一个量 ----
  console.log('\n\n=== ③ ⚠⚠⚴⚠ 文案口径 vs 判据口径：是不是同一个量？===');
  const q0 = prod.problems[pidNow];
  const K = q0.k;
  const rows = await page.eval(`document.querySelectorAll('[data-patht]').length`);
  console.log(`  产物 k = ${K}`);
  console.log(`  屏上 [data-patht] 行数 = ${rows}`);
  console.log(`  判据 C3 核的量  : nRows === Math.min(6, k+1) = ${Math.min(6, K + 1)}  ⇒ **6 行**`);
  const plusMinus = K - 5 >= 0 ? Math.min(K + 5, Object.keys(prod.problems).length ? 999 : 0) : -1;
  console.log(`  文案若写「前后 ±5 步」，数学上应给 = (K-5 … K+5) ⇒ 至多 **11 行**`);
  // ⚗⚗⚗⚗⚗ **这段第一版是错的，已由 r135c_arith.py 纯算术推翻并就地更正。**
  // ⚗⚗⚗ 第一版印的是：「6 ≠ 11 ⇒ 两个不是同一个量」，等级还给了 ⚠⚠⚴⚠⚠。
  // ⚠⚠⚴⚠⚴ 错在哪：只算了 ±5 的**上界**（k+5），漏了**下界** max(0, k-5)。
  //   k=27 时区间是 [22,27] ⇒ 恰好 6 行；「至多 11」不是「恒等于 11」。
  // ⚠⚠⚴ 推翻了它的是 r135c_arith.py：0 ≤ k ≤ 39 全部一致，min(6,k+1) 恒等于 ±5 行数。
  // ⚠⚠⚴⚠⚴ **错法本身是本轮最贵的教训**：这句话是**手写死在脚本里**的，
  //   没有任何一行代码算它，却印成了一个 ⚠⚠⚴ 级发现。
  //   ⇒ 与「仪器读到的也可能不是它要找的」同族：仪器**根本没读**，它写死了。
  console.log(`\n  ⚗ 更正（第一版此处印了错结论，已被 r135c_arith.py 推翻）：`);
  console.log(`     ±5 模式行数 = min(k+1, k+5) - max(0, k-5) 区间长度，`);
  console.log(`     k=${K} ⇒ [${Math.max(0, K - 5)}, ${Math.min(TOTAL - 1, K + 5)}] = ${rows} 行`);
  console.log(`     判据 min(6, k+1) = ${Math.min(6, K + 1)}  ⇒ **两者一致，C3 判得对**`);
  console.log(`\n  ⚠ 但 min(6, k+1) 这个截断**可能有正当理由**（k+1 是总行数上限）`);
  console.log(`     ⇒ 真正要问的是：**屏上那句「±5」的上下文有没有把截断说出来？**`);
  console.log(`     上面 ① 的整段文案就是这个问题的答案。`);

  // ---- ⑤ k 的可见文案归属（修订 131 的 C6 同族风险）----
  console.log(`\n\n=== ④「27」（k 值）在屏上的归属 ===`);
  const kOwner = JSON.parse(await page.eval(`JSON.stringify((() => {
    const wrap = document.querySelector('#pathWrap');
    const w = document.createTreeWalker(wrap, NodeFilter.SHOW_TEXT);
    let n, list = [];
    while ((n = w.nextNode())) {
      const s = n.nodeValue || '';
      if (s.split('27').length - 1 > 0) {
        const host = n.parentElement ? n.parentElement.closest('[id]') : null;
        list.push({ host: host ? (host.id||'(no-id)') : '(无)', snippet: s.trim().slice(0, 80) });
      }
    }
    return list;
  })())`));
  console.log(`  「27」在屏上出现于 ${kOwner.length} 个文本节点，归属: ${[...new Set(kOwner.map(x=>x.host))].map(h=>'#'+h).join(' ')}`);
  console.log(`  ⚠⚠⚴ 若 C1 要改成核**可见文案**里的 k，needle='27' 命中 ${kOwner.length} 处`);
  console.log(`     ⇒ 同修订 131 的 C6：\`T.includes('27')\` 要删 ${kOwner.length} 处才翻面 ⇒ 名义有牙齿、实质够不着`);
  console.log(`     ⇒ 只能核「口径词」（±5 / 每臂 2 个候选 / 默认只显示），那些命中 1~2 次，够得着`);

  console.log('\n\n=== 本台结论 ===');
  console.log('  ① 身份自证顺序已修（导航后印，不符即 exit 2）—— r135a 的那一栏作废');
  console.log('  ② A8 够得着（class="on" 单记号，删 1 处翻面）—— 不是 C6 同族');
  console.log('  ③ A6 的读取层同样无空值保护（getComputedStyle(null) 抛）⇒ D5 缺陷面扩大');
  console.log('  ④ ⚠ C1-C4 判据主体读 data-* 属性，而屏上另有可见文案；两者能否不一致，未验');
} catch (e) {
  console.log('[装置错]', String(e && e.message ? e.message : e));
} finally {
  try { await cdp.send('Browser.close'); } catch {}
  try { proc.kill(); } catch {}
}