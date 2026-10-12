// r125_probe_verdict_dom.mjs —— 诊断：[data-axis-row] 下面到底有没有 [data-verdict]
//
// 为什么查这个：K2 台在 D2 上读到 null，而 verify_axis_readout.mjs 的 D2
//   `const v = el && el.querySelector('[data-verdict]'); return v ? … : ''`
//   ⇒ el 不为 null 但 v 为 null ⇒ **posText 是空字符串**
//   ⇒ 谓词 `!posText.includes('token 局部')` 恒真 ⇒ D2 被平凡满足。
// ⚠ 而同一文件的 D3（confidence 行）在实跑里打出了真实句子
//   ⇒ 说明 `[data-verdict]` 确实是 `[data-axis-row]` 的后代
//   ⇒ 差别只能来自**行**：reasoning 行没有这个子元素。
import { launch, Page, CDP } from '/Users/zhourui/code/steer3d/.cache/browser_verify/cdp_client.mjs';

const URL = process.env.BV_URL || 'http://127.0.0.1:9006/';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const { proc, version } = await launch({
  port: 9496, userDataDir: '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_r125p_' + process.pid,
  windowSize: '1700,1200', url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 60000).catch(() => {});
  await sleep(13000);

  const out = JSON.parse(await page.eval(`(() => {
    const rows = [...document.querySelectorAll('[data-axis-row]')];
    return JSON.stringify({
      nRows: rows.length,
      rows: rows.map(r => ({
        key: r.getAttribute('data-axis-row'),
        ownAttrs: [...r.attributes].map(a => a.name).filter(n => n !== 'class'),
        nVerdictDesc: r.querySelectorAll('[data-verdict]').length,
        verdictText: [...r.querySelectorAll('[data-verdict]')]
          .map(v => (v.innerText||'').replace(/\\s+/g,' ').trim().slice(0,44)),
        rowTextHead: (r.innerText||'').replace(/\\s+/g,' ').trim().slice(0, 70),
      })),
      // 全页有没有 [data-verdict]（不在任何 axis-row 里的）
      verdictTotal: document.querySelectorAll('[data-verdict]').length,
      verdictOutsideRows: [...document.querySelectorAll('[data-verdict]')]
        .filter(v => !v.closest('[data-axis-row]')).length,
    });
  })()`));

  console.log('[data-axis-row] 行数 =', out.nRows);
  console.log('[data-verdict] 全页 =', out.verdictTotal,
              '其中不在任何 axis-row 内 =', out.verdictOutsideRows);
  console.log();
  for (const r of out.rows) {
    console.log(`  行 ${String(r.key).padEnd(11)} [data-verdict] 后代数 = ${r.nVerdictDesc}`);
    console.log(`     该行自身属性: ${JSON.stringify(r.ownAttrs)}`);
    if (r.verdictText.length) r.verdictText.forEach(t => console.log(`     verdict 文字: 「${t}」`));
    console.log(`     行首文字: 「${r.rowTextHead}」`);
  }
  console.log();
  console.log('⚠ D2 读的是 `[data-axis-row="reasoning"] [data-verdict]`：');
  const reasoning = out.rows.find(r => r.key === 'reasoning');
  console.log('   reasoning 行的 [data-verdict] 后代数 =', reasoning ? reasoning.nVerdictDesc : '(该行不存在)');
  console.log('   ⇒ 若为 0，则 verify_axis_readout.mjs 的 posText === ""，');
  console.log('     谓词 !posText.includes(\'token 局部\') 恒真 ⇒ D2 被平凡满足');
} catch (e) {
  console.log('[装置错]', String(e && e.message ? e.message : e));
} finally {
  try { await cdp.send('Browser.close'); } catch {}
  try { proc.kill(); } catch {}
}