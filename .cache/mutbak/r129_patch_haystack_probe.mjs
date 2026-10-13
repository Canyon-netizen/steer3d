// r129_patch_haystack_probe.mjs —— 修订 129：量 `verify_patch` 的 P9/P10/P11 判据
// 到底锁在哪一句（**先量事实，再决定要不要扰动**）
//
// 【为什么先量而不是直接扰动】
//   P9/P10/P11 都是「**存在即真**」谓词：
//     P9  = /主量/.test(txt) && /次量/.test(txt)
//     P10 = /幅度配平/.test(txt) && /逐节点相等/.test(txt)
//     P11 = /陌生度/.test(txt)
//   `txt = document.getElementById('patchWrap').innerText`（`verify_patch.mjs:235`）
//   ⚠⚠ `includes`/`test` 在**整块容器**上命中 ⇒ **若同一个词在屏上出现多次，
//   删掉其中一处它照样绿。**
//   ⚠ 而修订 126/127/128 已经在 React 页与静态 path 屏上抓到同族：
//     「haystack 比作用域大 ⇒ 删掉那一处它照样绿」。
//   ⇒ ⚠ **先数清每个词在屏上出现几次**，才知道「删一处」型扰动够不够、
//     该不该改成「全删」。
//
// ⚠ 反漂移守卫：不复写判据，从已提交的 `verify_patch.mjs` 抽三处谓词原文；
//   抽不到 ⇒ 拒绝发布（修订 128 那次正则漏条的教训）。
//
// ⚠⚠⚴⚠⚴ **页面侧不写正则**（修订 127 的四级转义假绿教训）：
//   这里的「数出现几次」**也不写正则** —— 用 split().join() 数，
//   计数只认「非重叠、不跨边界」的整串匹配，与 `/词/.test` 的语义一致。

import { launch, Page, CDP } from '/Users/zhourui/code/steer3d/.cache/browser_verify/cdp_client.mjs';
import { readFileSync } from 'node:fs';

const URL = process.env.LAT_URL || 'http://127.0.0.1:9006/latent/index.html';
const VER = '/Users/zhourui/code/steer3d/.cache/browser_verify/verify_patch.mjs';
const sleep = ms => new Promise(r => setTimeout(r, ms));

// ---------- 反漂移守卫：从已提交判据文件抽三处谓词原文 ----------
const src = readFileSync(VER, 'utf8');
const spec = [];
for (const [id, line] of [
  ['P9 主量',   "const hasBoth = /主量/.test(txt) && /次量/.test(txt);"],
  ['P10 对照',  "const saysCtrl = /幅度配平/.test(txt) && /逐节点相等/.test(txt);"],
  ['P11 陌生度', "const warnsNoise = /陌生度/.test(txt);"],
]) {
  if (!src.includes(line)) { console.error(`[自证失败] 抽不到 ${id} 的谓词原文 ⇒ 本台已漂移，拒绝发布`); process.exit(2); }
  const words = [...line.matchAll(/\/([^/]+)\/\.test/g)].map(m => m[1]);
  spec.push({ id, words });
}
console.log('[自证] 三处谓词逐字出自 verify_patch.mjs：');
for (const s of spec) console.log(`  ${s.id}：${s.words.map(w => `「${w}」`).join(' + ')}`);

const ALL_WORDS = [...new Set(spec.flatMap(s => s.words))];
console.log(`[自证] 共 ${ALL_WORDS.length} 个待数词：${JSON.stringify(ALL_WORDS)}`);

const { proc, version } = await launch({
  port: 9495, userDataDir: '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_r129_' + process.pid,
  windowSize: '1600,1050', url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  await sleep(3500);
  await page.eval(`(() => {
    const ov = document.getElementById('orientation');
    const b = document.getElementById('orientClose');
    if (ov && !ov.classList.contains('hide') && b) b.click();
    const t = document.getElementById('tabPatch');
    if (t) t.click();
  })()`);
  await sleep(1200);

  console.log('\n=== 每个词在 #patchWrap 可见文字里出现几次 ===\n');
  const q = JSON.parse(await page.eval(`JSON.stringify((() => {
    const w = document.getElementById('patchWrap');
    const t = (w ? w.innerText : '') || '';
    const count = (hay, needle) => hay.split(needle).length - 1;   // 不写正则
    const out = { found: !!w, len: t.length, counts: {}, ctx: {} };
    for (const [k, needle] of Object.entries(${JSON.stringify(Object.fromEntries(ALL_WORDS.map(w => [w, w])))})) {
      out.counts[k] = count(t, needle);
      const i = t.indexOf(needle);
      out.ctx[k] = i >= 0 ? t.slice(Math.max(0, i - 30), i + needle.length + 30).split(String.fromCharCode(10)).join(' ').split(String.fromCharCode(9)).join(' ').trim() : null;
    }
    return out;
  })())`));

  console.log(`  #patchWrap ${q.found ? '存在' : '⚠ 不存在'} · innerText ${q.len} 字\n`);
  let anyMulti = false;
  for (const w of ALL_WORDS) {
    const n = q.counts[w];
    if (n === 0) { console.log(`  ⚠⚴ 「${w}」屏上 0 次 ⇒ 判据本来就红？`); continue; }
    if (n > 1) anyMulti = true;
    console.log(`  「${w}」×${n}${n > 1 ? '  ⚠⚴ **多处命中** ⇒ 删一处型扰动必然仍绿' : '  ✅ 唯一命中 ⇒ 删它即转红'}`);
    if (n > 1) console.log(`      首处上下文：…${q.ctx[w]}…`);
  }

  console.log('\n=== 结论 ===\n');
  for (const s of spec) {
    const ns = s.words.map(w => q.counts[w] ?? 0);
    const multi = ns.some(n => n > 1);
    const zero = ns.some(n => n === 0);
    console.log(`  ${s.id}：${JSON.stringify(ns)} ⇒ `
      + (zero ? '⚠ 有词基线就 0 次（判据红，先查环境）'
         : multi ? '⚠⚴ 有词多处命中 ⇒ 「删一处」验不出牙齿，必须「全删」'
                 : '✅ 每个词唯一命中 ⇒ 删它即可验出牙齿'));
  }
  console.log(`\n  ⚠⚴ 存在多处命中的词：${anyMulti ? '有' : '无'}`);
  console.log(`  ⚠ 口径：本台只量事实（「命中几次」），不做扰动、不下红绿结论。`);
  console.log(`  ⚠ 下一台是否要「全删」型扰动，看这次量出来的数再定。`);
} catch (e) {
  console.log('[装置错]', String(e && e.message ? e.message : e));
} finally {
  try { await cdp.send('Browser.close'); } catch {}
  try { proc.kill(); } catch {}
}
