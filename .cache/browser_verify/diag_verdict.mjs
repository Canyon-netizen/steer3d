// 读页面内判据的**逐条**判决：RandomControlPanel 配套的 verifyRandomControl。
//
// ⚠ 为什么单独写：diag_select 只读了 `data-rc-verify` 的**汇总**属性，
//   而它本轮是 `BAD` —— 汇总说「有红的」，没说「哪几条红」。
//   扫覆盖的 C4 只数「有没有判据读过这些标记」，**不核判决本身绿不绿**。
//   ⇒ 一个带 BAD 的判据完全可以让 C4 变绿。两者是不同的东西。
//
// ⚠ 判据主体是 `data-rc-verify-line` 的**可见文本**（ok/BAD + 读了什么），
//   不是 data-* 属性名。属性名只用来定位。
import { launch, CDP, Page } from './cdp_client.mjs';
import { mkdirSync, writeFileSync } from 'node:fs';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const URL = process.env.T3D_URL || 'http://127.0.0.1:22210/';
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_diag_verdict';
mkdirSync(PROFILE, { recursive: true });

const { proc, version } = await launch({
  port: 9452, userDataDir: PROFILE, windowSize: '1600,1000', url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
await page.send('Page.navigate', { url: URL });
await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
// 判据自己最多等 20s（它轮询到 [data-rc=ok] 才抓）
await sleep(9000);

const out = await page.eval(`(() => {
  const root = document.querySelector('[data-rc-verify]');
  if (!root) return JSON.stringify({ found: false });
  const lines = [...root.querySelectorAll('[data-rc-verify-line]')]
    .map(n => n.textContent || '');
  return JSON.stringify({
    found: true,
    verdict: root.getAttribute('data-rc-verify'),
    n: root.getAttribute('data-rc-verify-n'),
    bad: root.getAttribute('data-rc-verify-bad'),
    sawPanel: root.getAttribute('data-rc-verify-saw-panel'),
    lines,
  });
})()`);

const d = JSON.parse(out);
console.log('判决 =', d.verdict, ' 条数 =', d.n, ' BAD 条数 =', d.bad,
            ' 看到面板 =', d.sawPanel);
console.log('');
for (const l of d.lines || []) console.log('  ' + l);
const bads = (d.lines || []).filter((l) => l.startsWith('BAD'));
console.log('');
console.log(bads.length ? `⇒ ${bads.length} 条红：` : '⇒ 全绿');
writeFileSync('/Users/zhourui/code/steer3d/.cache/browser_verify/diag_verdict.json',
  JSON.stringify(d, null, 2));
proc.kill();
process.exit(0);
