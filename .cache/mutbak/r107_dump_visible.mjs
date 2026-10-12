// r107_dump_visible.mjs —— 修订 107
//
// 目的：修订 106 量到「74 个字段的『已渲染』判定靠类型声明/注释撑起来」，
//   但**真实盲区大小未知**。要把它量出来，得有两样东西：
//   ① 整页**真实可见**的文案（不是源码、不是产物、不是扁平文本的猜测）
//   ② 74 个字段的全部**值**
//
// ⚠ 本脚本只干 ①，且**只写文件、不打印** —— 整页文案有几十万字，
//   打进上下文既费又会让我「用看到的片段代替全部」。
// ⚠ 自证：必须证明页面真的加载出数据（面板 ready），否则落盘的是空壳。

import { launch, Page, CDP } from '/Users/zhourui/code/steer3d/.cache/browser_verify/cdp_client.mjs';
import { writeFileSync } from 'node:fs';

const URL = process.env.BV_URL || 'http://127.0.0.1:9005/';
const OUT = process.env.BV_OUT || '/Users/zhourui/code/steer3d/.cache/mutbak/r107_visible_all.txt';
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_r107_' + process.pid;

const die = (m) => { console.log('[自证失败] ' + m); process.exit(2); };

const { proc, version } = await launch({
  port: 9489, userDataDir: PROFILE, windowSize: '1700,4000', url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  await new Promise(r => setTimeout(r, 5000));      // 给所有面板的 fetch 留时间

  const raw = await page.eval(`(() => {
    const vis = el => el ? (el.innerText || '') : '';
    const panels = {};
    const named = ['subspace','heldout','evidence','axis','intervention','control',
                   'verdict','absorbed','bpath','random','strength','layer','roles',
                   'derivation','token','law','audit','topk','hinge','arm'];
    for (const n of named) {
      for (const el of document.querySelectorAll('[data-' + n + ']')) {
        panels[n + '@' + el.getAttribute('data-' + n)] = vis(el);
      }
    }
    // ⚠ 「[data-*]」不是合法选择器 —— 第一版写了这行，eval 直接抛 SyntaxError。
    //   好在它是**报错**而不是静默返回空 ⇒ 自证没被绕过。
    const errs = [...document.querySelectorAll('main *')]
      .filter(e => /读不到 |载入中|Failed to fetch|Unexpected token/i.test(e.innerText || ''))
      .map(e => (e.innerText || '').slice(0, 120));
    return JSON.stringify({
      bodyLen: (document.body.innerText || '').length,
      body: document.body.innerText || '',
      panels,
      errs: [...new Set(errs)],
      pageHeight: document.body.scrollHeight,
    });
  })()`);
  const R = JSON.parse(raw);

  if (!R.body || R.bodyLen < 3000) die('整页文本过短（' + R.bodyLen + '），像是没渲染');
  if (R.errs && R.errs.length) {
    console.log('[注意] 页面里有 ' + R.errs.length + ' 处疑似报错/未载入：');
    for (const e of R.errs.slice(0, 8)) console.log('   ', e.replace(/\s+/g, ' ').slice(0, 100));
  }
  writeFileSync(OUT, R.body, 'utf8');
  console.log('已写出 ' + OUT);
  console.log('  整页可见文案 ' + R.bodyLen + ' 字符 / 页面高 ' + R.pageHeight + 'px');
  console.log('  抓到的具名面板 ' + Object.keys(R.panels).length + ' 个');
  const withText = Object.entries(R.panels).filter(([, v]) => v.length > 0);
  console.log('  其中有文字的 ' + withText.length + ' 个');
} catch (e) {
  die('装置错：' + String(e && e.message ? e.message : e));
} finally {
  try { await cdp.send('Browser.close'); } catch {}
  try { proc.kill(); } catch {}
}