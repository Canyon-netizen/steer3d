// r127_latent_markdown_probe.mjs —— 修订 127 的**第三刀**
//
// ⚠ 上一版（r127_scope_probe.mjs）栽在「跑错页面」上。
//   本版跑**静态产物页**，逐屏数读者可见文字里有没有 `**` 露出来。
//
// ⚠⚠ 为什么这个数不能从源码推断：
//   源码里没有 `<strong>`、没有 `split("**")`，**只说明没有那两种处理**，
//   不说明页面上没有别的处理方式（CSS、另一层包装、或者某屏压根没印）。
//   ⇒ 「仪器读不到 ≠ 对象不存在」的反面：**源码没找到 ≠ 页面上没有**。
//   ⇒ 必须实测每一屏的 innerText。
//
// ⚠⚴⚴ 8 个屏里只有 2 个有判据（tabPath 36 条 / tabPatch 13 条）。
//   本版顺带把「哪几屏有判据」这个事实与「哪几屏露出 **」并排印出来。
//
// ⚠⚴⚴ 转义纪律（上一版栽过）：页面侧一律用 `split/join`，
//   **不写正则**；`\n` 在模板字符串里要写成 `\\n`。
//   计数用 String.fromCharCode(42,42)（即 "**"），避免任何转义争议。

import { launch, Page, CDP } from '/Users/zhourui/code/steer3d/.cache/browser_verify/cdp_client.mjs';

const URL = process.env.LAT_URL || 'http://127.0.0.1:9006/latent/index.html';
const sleep = ms => new Promise(r => setTimeout(r, ms));

// 哪些屏有判据（从 .cache/browser_verify 的脚本里读出来的）
const HAS_JUDGE = { tabPath: 'verify_path.mjs(36 条)', tabPatch: 'verify_patch.mjs(13 条)' };

const { proc, version } = await launch({
  port: 9499, userDataDir: '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_r127m_' + process.pid,
  windowSize: '1600,1050', url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  await sleep(3500);
  const l0 = JSON.parse(await page.eval(`JSON.stringify({
    href: location.href, bodyLen: (document.body.innerText||'').length })`));
  console.log(`[自证] 页面 = ${l0.href}  bodyLen=${l0.bodyLen}`);
  if (!(l0.href.startsWith('http') && l0.bodyLen > 500)) throw new Error('页面没加载，本台作废');

  const l0b = JSON.parse(await page.eval(`JSON.stringify((() => {
    const b = String.fromCharCode(42,42);
    const t = document.body.innerText || '';
    let n = 0, i = 0;
    while ((i = t.indexOf(b, i)) !== -1) { n++; i += 2; }
    return { total: n };
  })())`));
  console.log(`[自证] 默认屏整页可见文字里 \`**\` 共 ${l0b.total} 次（未切屏）\n`);

  const tabs = ['tabBar', 'tabDelta', 'tabDim', 'tabLtv', 'tabPatch', 'tabPath', 'tabThresh', 'tabXY'];
  console.log('屏'.padEnd(11) + '可见字数'.padEnd(10) + '`**`次数'.padEnd(10) + '有判据？');
  console.log('-'.repeat(62));
  const rows = [];
  for (const tab of tabs) {
    await page.eval(`(() => { const t = document.getElementById('${tab}'); if (t) t.click(); })()`);
    await sleep(700);
    const r = JSON.parse(await page.eval(`(() => {
      const b = String.fromCharCode(42,42);
      // 只量**当前屏可见**的部分：取 active 的 wrap
      const wraps = [...document.querySelectorAll('div,section')]
        .filter(e => e.id && /^wrap/.test(e.id));
      let host = null;
      for (const w of wraps) {
        const cs = getComputedStyle(w);
        if (cs.display !== 'none' && w.innerText && w.innerText.trim()) { host = w; break; }
      }
      const visEl = host || document.body;
      const t = visEl.innerText || '';
      let n = 0, i = 0;
      while ((i = t.indexOf(b, i)) !== -1) { n++; i += 2; }
      const r0 = visEl.getBoundingClientRect();
      return JSON.stringify({
        len: t.length, star: n, hostId: visEl.id || '(body)',
        visible: r0.height > 0 && r0.width > 0,
        sample: n > 0 ? t.substr(Math.max(0, t.indexOf(b) - 34), 76) : null,
      });
    })()`));
    rows.push([tab, r]);
    console.log(tab.padEnd(11) + String(r.len).padEnd(10) + String(r.star).padEnd(10)
      + (HAS_JUDGE[tab] ? `✅ ${HAS_JUDGE[tab]}` : '⚗ 无判据'));
    if (r.sample) console.log('            ⚠ 样例：…' + r.sample.replace(/[\n\r]+/g, ' ') + '…');
  }

  const noJudge = rows.filter(([t, r]) => !HAS_JUDGE[t]);
  const leaked = noJudge.filter(([, r]) => r.star > 0);
  console.log('\n=== 结论 ===');
  console.log(`  8 屏里有判据的 ${rows.length - noJudge.length} 屏、无判据的 ${noJudge.length} 屏`);
  console.log(`  无判据且实测露出 \`**\` 的：${leaked.length} 屏 ⇒ ${leaked.map(([t]) => t).join('、') || '无'}`);
  console.log(`  有判据的 2 屏：`);
  for (const [t] of rows) if (HAS_JUDGE[t]) {
    const r = rows.find(x => x[0] === t)[1];
    const nJudgeStar = await (async () => {
      await page.eval(`(() => { const b = document.getElementById('${t}'); if (b) b.click(); })()`);
      await sleep(700);
      const s = JSON.parse(await page.eval(`(() => {
        const b = String.fromCharCode(42,42);
        const t = document.body.innerText || '';
        let n = 0, i = 0;
        while ((i = t.indexOf(b, i)) !== -1) { n++; i += 2; }
        return JSON.stringify({ star: n });
      })()`));
      return s.star;
    })();
    console.log(`    ${t}  该屏可见 \`**\` ${nJudgeStar} 次 —— ⚠ 该屏判据里有核 markdown 残留的：`
      + (nJudgeStar > 0 ? '⚠⚴ 有露出且被判据放过' : '✅ 无露出'));
  }
  console.log(`\n  ⚠ 口径：本探针只量「读者可见文字里有没有 \`**\`」，`);
  console.log(`  ⚠ **不判产品对错** —— 要不要渲染掉是设计选择，需拍板。`);
  console.log(`  ⚠ 另：本台量的是 \`wrap*\` 里第一个可见容器，不是逐屏精确包裹；`);
  console.log(`  ⚠   若某屏的 wrap 未被取到，该屏 \`**\` 数会被记成 0（**仪器读不到 ≠ 没有**）。`);
} catch (e) {
  console.log('[装置错]', String(e && e.message ? e.message : e));
} finally {
  try { await cdp.send('Browser.close'); } catch {}
  try { proc.kill(); } catch {}
}
