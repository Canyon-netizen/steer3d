// `ready_wait.mjs` 的自检 —— 用假 readOne 驱动，**不需要浏览器**。
//
// ⚠⚠⚴ 为什么要给它写自检：本轮的改动是「让『没等到』变得可见」。
// ⚠⚠⚴ 而这类改动的失效模式恰恰是「看不见」—— 如果 ok 永远是 true，
// ⚠⚠⚴ 自报字段就成了又一层装饰，**没有任何东西会发现**。
// ⚗⇒ R2/R3 是**反向项**：必须能红，且红在预期的那一项上。
//
// 运行：node .cache/browser_verify/ready_wait_selftest.mjs
// 退出码：0 全过 / 1 有项红

import { waitReady, readyWhenAttr, readyWhenPresent } from './ready_wait.mjs';

const FAILS = [];
let CHECKS = 0;
const check = (name, cond, detail = '') => {
  CHECKS++;
  console.log('  ' + name.padEnd(52) + ' ' + (cond ? 'PASS' : 'FAIL')
    + (detail && !cond ? '  <- ' + detail : ''));
  if (!cond) FAILS.push(name);
};

// 假时钟：每次 sleep 推进虚拟时间
function fakeClock() {
  let t = 0;
  return {
    now: () => t,
    sleep: async ms => { t += ms; },
    advance: ms => { t += ms; },
  };
}

console.log('=== R1：信号第 k 次出现 ⇒ ok=true，且轮询次数正好 k ===');
{
  const ck = fakeClock();
  let n = 0;
  const r = await waitReady(async () => (++n >= 4 ? 'ready' : 'loading'),
    readyWhenAttr('data-outcome'), { maxMs: 24000, pollMs: 1200, sleep: ck.sleep, now: ck.now });
  check('R1a ok=true', r.ok === true, JSON.stringify(r));
  check('R1b polls=4（不多读一次）', r.polls === 4, 'polls=' + r.polls);
  check('R1c waitedMs=3×1200=3600', r.waitedMs === 3600, 'waited=' + r.waitedMs);
}

console.log('\n=== R2：⛔ 信号永不到 ⇒ ok=false，且 waitedMs 必须被记下来 ===');
{
  const ck = fakeClock();
  let n = 0;
  const r = await waitReady(async () => (++n, 'never'),
    readyWhenAttr('data-outcome'), { maxMs: 24000, pollMs: 1200, sleep: ck.sleep, now: ck.now });
  check('R2a ⛔ ok=false（不能静默当成功）', r.ok === false, JSON.stringify(r));
  check('R2b ⛔ waitedMs 必须在 [24000, 25200]（不许是 0/undefined）',
    r.waitedMs >= 24000 && r.waitedMs <= 25200, 'waited=' + r.waitedMs);
  check('R2c ⛔ last 必须保留最后读到的值（供诊断）', r.last === 'never', JSON.stringify(r.last));
}

console.log('\n=== R3：⛔ 预算边界 —— 恰好在边界前一刻出现必须算等到 ===');
{
  // maxMs=5000, pollMs=1000 ⇒ 应读 6 次（t=0,1000,…,5000）
  const ck = fakeClock();
  let n = 0;
  const r = await waitReady(async () => (++n >= 6 ? 'ready' : 'loading'),
    readyWhenAttr('data-outcome'), { maxMs: 5000, pollMs: 1000, sleep: ck.sleep, now: ck.now });
  check('R3a ⛔ 第 6 次读到 ready ⇒ ok=true', r.ok === true, JSON.stringify(r));
  const ck2 = fakeClock();
  let m = 0;
  const r2 = await waitReady(async () => (++m >= 6 ? 'ready' : 'loading'),
    readyWhenAttr('data-outcome'), { maxMs: 5000, pollMs: 1000, sleep: ck2.sleep, now: ck2.now });
  check('R3b ⛔ polls=6（不多不少，边界不吞）', r2.polls === 6, 'polls=' + r2.polls);
  void r;
}

console.log('\n=== R4：存在性形态（latent 页）===');
{
  const ck = fakeClock();
  let n = 0;
  const r = await waitReady(async () => (++n >= 2 ? true : false),
    readyWhenPresent, { maxMs: 6000, pollMs: 1000, sleep: ck.sleep, now: ck.now });
  check('R4a ok=true', r.ok === true, JSON.stringify(r));
  check('R4b polls=2', r.polls === 2, 'polls=' + r.polls);
  const ck2 = fakeClock();
  const r2 = await waitReady(async () => false, readyWhenPresent,
    { maxMs: 3000, pollMs: 1000, sleep: ck2.sleep, now: ck2.now });
  check('R4c ⛔ 一直 false ⇒ ok=false 且 waited≥3000',
    r2.ok === false && r2.waitedMs >= 3000, JSON.stringify(r2));
}

console.log('\n=== R5：⛔ 假信号不得被当成就绪 ===');
{
  const ck = fakeClock();
  // data-outcome 可能是 'loading'/'error'/'ready'；只有 'ready' 算就绪。
  const r = await waitReady(async () => 'error', readyWhenAttr('data-outcome'),
    { maxMs: 3000, pollMs: 1000, sleep: ck.sleep, now: ck.now });
  check('R5a ⛔ data-outcome="error" 不得算就绪', r.ok === false, JSON.stringify(r));
  check('R5b ⛔ 且 last 记下 "error" 供排查', r.last === 'error', JSON.stringify(r.last));
}

console.log('\n=== 汇总 ===');
if (FAILS.length) {
  console.log('RESULT ready_wait_selftest  FAIL  ' + FAILS.length + '/' + CHECKS
    + ' 项红：' + JSON.stringify(FAILS));
  process.exit(1);
}
console.log('RESULT ready_wait_selftest  OK  ' + CHECKS + '/' + CHECKS);
