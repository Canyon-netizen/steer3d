// 一次性诊断：根页到底有没有 JS 异常、`aime__` 那个 <select> 为什么不在。
//
// ⚠ 为什么不能用现成探针：`probe_panels.mjs` 只记 data-* 属性，
//   `<select>` 与 console 都不在它的口径里。而这次的红**不是** data-* 缺口，
//   是「一个 client 渲染出来的 <select> 不存在」。
//
// ⚠ 照抄既有约定，不自己发明 API：
//   console/异常走 `page.events`（cdp_client.mjs:160-162 自动收），
//   启用域用 `page.send('Runtime.enable')`（cdp_client.mjs:171 同款）。
//   **第一版照 `cdp.on(method, fn)` 的印象写-import 了 `Runtime` 和 `sleep`
//   —— 两者都不是本文件的导出 ⇒ 装置自己跑不起来。**
//   与「写 batch_provenance.py 时两次装置故障」同族：
//   **装置没过自检就报结果，报的是装置的错。**
//
// ⚠ 只回答两个问题，不做判决：
//   ① 控制台/异常里有没有我的组件炸了
//   ② 页面在 0/2/5/10/20s 各时刻，select 与 derivation 面板的实况
import { launch, CDP, Page } from './cdp_client.mjs';
import { mkdirSync, writeFileSync } from 'node:fs';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const URL = process.env.T3D_URL || 'http://127.0.0.1:22210/';
const PROFILE = process.env.T3D_PROFILE
  || '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_diag_select';
mkdirSync(PROFILE, { recursive: true });

const { proc, version } = await launch({
  port: 9451, userDataDir: PROFILE, windowSize: '1600,1000', url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
await page.send('Runtime.enable');
await page.send('Page.navigate', { url: URL });
await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});

const snap = () => page.eval(`(() => {
  const sels = [...document.querySelectorAll('select')];
  const der = document.querySelector('[data-derivation]');
  const rv = document.querySelector('[data-rc-verify]');
  const rc = document.querySelector('[data-rc]');
  return JSON.stringify({
    bodyLen: (document.body.innerText || '').length,
    selectCount: sels.length,
    selects: sels.map(s => ({
      nOpt: s.options.length,
      firstOpts: [...s.options].slice(0, 3).map(o => o.value),
      hasAime: [...s.options].some(o => /^aime__/.test(o.value)),
    })),
    derivation: der ? der.getAttribute('data-derivation') : 'ABSENT',
    rcAttr: rc ? rc.getAttribute('data-rc') : 'ABSENT',
    rcVerify: rv ? rv.getAttribute('data-rc-verify') : 'ABSENT',
    rcVerifyN: rv ? rv.getAttribute('data-rc-verify-n') : null,
    rcVerifySaw: rv ? rv.getAttribute('data-rc-verify-saw-panel') : null,
  });
})()`);

const timeline = [];
for (const t of [0, 2000, 3000, 5000, 10000, 20000]) {
  const prev = timeline.length ? timeline[timeline.length - 1].t : 0;
  if (t) await sleep(t - prev);
  let raw = '';
  try { raw = await snap(); } catch (e) { raw = 'EVAL_ERR ' + String(e); }
  timeline.push({ t, raw });
  console.log(`t=${String(t).padStart(5)}ms  ${raw}`);
}

const errs = page.events.filter((e) => e.method === 'Runtime.exceptionThrown'
  || (e.method === 'Runtime.consoleAPICalled' && e.params?.type === 'error'));
const warns = page.events.filter((e) => e.method === 'Runtime.consoleAPICalled'
  && ['warning', 'warn'].includes(e.params?.type));

console.log('\n=== error / exception ===');
console.log(errs.length
  ? errs.slice(0, 12).map((e) => JSON.stringify(e.params).slice(0, 300)).join('\n')
  : '（无）');
console.log('\n=== warning ===');
console.log(warns.length
  ? warns.slice(0, 8).map((e) => JSON.stringify(e.params).slice(0, 240)).join('\n')
  : '（无）');

const OUT = '/Users/zhourui/code/steer3d/.cache/browser_verify/diag_select.json';
writeFileSync(OUT, JSON.stringify(
  { url: URL, timeline, errs: errs.map((e) => e.params), warns: warns.map((e) => e.params) },
  null, 2));
console.log('\n写 ' + OUT);
proc.kill();
process.exit(0);
