// 变异台：证明 verify_derivation 的新检查真的会红。
//
// ⚠ 每一路都必须**先自证装置本来是绿的**，否则「变异后仍然绿」可能只是
//   因为环境本来就坏。装置自检不过 ⇒ 报「变异无效」，不许算成功。
//   （与「无判据超时」同族：装置坏了时红与不红都没有意义。）
//
// 用法：node mut_derivation_precond.mjs [变异名]
//   none        只跑装置自检（绿侧）
//   bars_fake   把每根柱子的 data-pfinal 改成常数 0.5 ⇒ F5 必须红
//   first_layer 改掉「首个说对的层」文案里的层号 ⇒ F6 必须红
//   correct8    把一根「原来说对」的柱子翻成说错 ⇒ F6b 必须红
//
// ⚠ 变异打在 **DOM 属性**上而不是源码上：判据读的是 data-pfinal / data-ok /
//   可见文案，这三样正是读者看到的东西的机器可读真值。
//   改源码再重建要 3 分钟且会污染构建产物，而这一层已经足够。
import { launch, CDP, Page } from './cdp_client.mjs';
import { mkdirSync } from 'node:fs';

const sleep = ms => new Promise(r => setTimeout(r, ms));
const MUT = process.argv[2] || 'none';
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_mut_deriv';
mkdirSync(PROFILE, { recursive: true });

const { proc, version } = await launch({
  port: 9477, userDataDir: PROFILE, windowSize: '1600,1000', url: 'about:blank' });
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
await page.send('Runtime.enable');
await page.send('Page.enable');
await page.send('Page.navigate', { url: process.env.T3D_URL || 'http://127.0.0.1:22226/' });
await page.waitForEvent('Page.loadEventFired', 60000).catch(() => {});

let ok = false;
for (let i = 0; i < 20; i++) {
  ok = await page.eval(`(() => {
    const e = document.querySelector('[data-derivation="ready"]');
    return !!(e && e.querySelectorAll('rect[data-layer]').length === 28);
  })()`);
  if (ok) break;
  await sleep(600);
}
console.log('装置自检：面板 ready 且 28 根柱子 =', ok);
if (!ok) { console.log('!! 装置不绿 ⇒ 变异无效'); try { proc.kill('SIGKILL'); } catch (e) {} process.exit(3); }

let applied = 'none';
if (MUT === 'bars_fake') {
  const n = await page.eval(`(() => {
    const rs = document.querySelectorAll('[data-derivation] rect[data-layer]');
    rs.forEach(r => r.setAttribute('data-pfinal', '0.5'));
    return rs.length;
  })()`);
  applied = `data-pfinal 全部改成 0.5（${n} 根）`;
} else if (MUT === 'first_layer') {
  applied = await page.eval(`(() => {
    const e = document.querySelector('[data-derivation]');
    const n = [...e.querySelectorAll('*')].find(x =>
      x.children.length === 0 && /first one that says it/.test(x.textContent || ''));
    if (!n) return 'no-node';
    // 把「layer 18」改成「layer 3」；18 与产物一致，3 不一致。
    n.textContent = (n.textContent || '').replace('layer 18', 'layer 3');
    return n.textContent;
  })()`);
} else if (MUT === 'correct8') {
  applied = await page.eval(`(() => {
    const rs = [...document.querySelectorAll('[data-derivation] rect[data-layer]')];
    const t = rs.find(r => r.getAttribute('data-ok') === '1');
    if (!t) return 'no-green-bar';
    t.setAttribute('data-ok', '0');
    return 'flipped layer ' + t.getAttribute('data-layer');
  })()`);
}
await sleep(500);

const st = await page.eval(`(() => {
  const e = document.querySelector('[data-derivation]');
  const rs = [...e.querySelectorAll('rect[data-layer]')];
  return JSON.stringify({
    pfinal0: rs.length ? rs[0].getAttribute('data-pfinal') : null,
    okCount: rs.filter(r => r.getAttribute('data-ok') === '1').length,
    head: (e.innerText || '').replace(/\\s+/g, ' ').slice(0, 150),
  });
})()`);
console.log('变异：', applied);
console.log('变异后 DOM：', st);
try { proc.kill('SIGKILL'); } catch (e) {}
process.exit(0);
