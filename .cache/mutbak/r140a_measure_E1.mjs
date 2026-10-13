// r140a_measure_E1.mjs —— 只读测量：E1 第四档的**可行性**（不是判决）
//
// ⚠⚠⚴ 待拍板项是「E1 这个第四档怎么处置」：补一条独立断言核「缺数据时会喊缺」，
//   还是把判据名改成只说它真核的那件事。
// ⚠⚠⚴⚠⚴ **在拍板之前必须先回答「这条断言立得起来吗」** ——
//   立不起来的话，选项 B（改名）就是唯一选项。⇒ 本台只量可行性，不下判决。
//
// ⚠ 已从源码核到的（不是记忆）：
//   `index.html:1581-1594` 有**两个空值分支**：
//     !S.path              → data-pathstate="no-data"，可见文案「逐步路径数据未载入…」
//     !problems[pid]       → data-pathstate="no-problem"，可见文案「这份逐步路径数据里没有题目…」
//   ⇒ **「缺数据时会喊缺」在代码里为真**，只是 E1 判的是
//     `typeof renderPathPanel === 'function'`，**证明不了它**。
//   ⇒ E1 属「说法为真但没验」，不是「说法为假」。
//
// ⚠ 要量的是：用 K2（页面实例级）让 path_readout.json 取不到，
//   页面**会不会自己说出那句可见文案**。
// ⚠ 手法：CDP `Network.setBlockedURLs` 拦这一个 URL（**只读，不改任何文件**）。
//
// ⚠ 本台只读：注入、扰动、下判决三样都不做，只量「拦掉之后屏幕上是什么」。
// ⚠ 身份自证在导航**之后**、任何测量之前，失败即 exit 2（修订 135 固化）。
// ⚠ 页面侧不写正则，用 indexOf/split（修订 128 固化）。

import { launch, Page, CDP } from '/Users/zhourui/code/steer3d/.cache/browser_verify/cdp_client.mjs';

const URL = process.env.LAT_URL || 'http://127.0.0.1:9006/latent/index.html';
const BLOCK = '*path_readout.json*';
const sleep = ms => new Promise(r => setTimeout(r, ms));

const { proc, version } = await launch({
  port: 9521, userDataDir: '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_r140a_' + process.pid,
  windowSize: '1600,1050', url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);

// 量一屏：页面切到第 5 屏后，[data-pathblock] 的状态与**读者看得见的文字**
const MEASURE = `(async () => {
  const tab = document.querySelector('#tabPath');
  if (!tab) return JSON.stringify({ fatal: '没有 #tabPath' });
  tab.click();
  await new Promise(r => setTimeout(r, 1200));
  const b = document.querySelector('[data-pathblock]');
  const txt = b ? (b.innerText || '') : '';
  return JSON.stringify({
    hasHandler: typeof window.renderPathPanel,
    blockPresent: !!b,
    pathState: b ? (b.getAttribute('data-pathstate') || '') : '(无)',
    // ⚠ 只量「这句话在不在屏幕上」，不判断它对不对
    saysNotLoaded: txt.indexOf('未载入') >= 0,
    saysMissingFile: txt.indexOf('path_readout.json') >= 0,
    saysNoProblem: txt.indexOf('没有题目') >= 0,
    textLen: txt.length,
    textHead: txt.split('\\n').slice(0, 3).join(' / ').slice(0, 120),
  });
})()`;

async function scenario(label, urls) {
  await page.send('Network.enable').catch(() => {});
  await page.send('Network.setBlockedURLs', { urls }).catch(e => {
    console.log('[错误] setBlockedURLs 崩了 ⇒ 仪器坏了，不发数:', e.message);
    process.exit(2);
  });
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 60000).catch(() => {});

  // ⚠ 身份自证：必须在导航之后、任何测量之前
  const here = await page.eval('location.href');
  if (!String(here).endsWith('/latent/index.html')) {
    console.log('[错误] 页面身份不对，here =', here, '⇒ exit 2');
    process.exit(2);
  }
  for (let i = 0; i < 80; i++) {
    const boot = await page.eval(`(()=>{const o=document.querySelector('#app');
      return !!o && getComputedStyle(o).visibility === 'visible';})()`);
    if (boot) break;
    await sleep(400);
  }
  const out = JSON.parse(await page.eval(MEASURE));
  console.log(`\n=== ${label} ===`);
  console.log('  拦掉的 URL :', urls.length ? urls.join(', ') : '(无)');
  console.log('  href       :', here);
  for (const [k, v] of Object.entries(out)) console.log(`  ${k.padEnd(14)}: ${v}`);
  return out;
}

try {
  const base = await scenario('对照：不拦（数据在）', []);
  const cut = await scenario('扰动：拦掉 path_readout.json', [BLOCK]);

  // ---- 对账：这台不下判决，只报「可区分 / 不可区分」------------------
  const dist = (k) => base[k] !== cut[k];
  const keys = ['hasHandler', 'blockPresent', 'pathState',
                'saysNotLoaded', 'saysMissingFile', 'saysNoProblem'];
  console.log('\n=== 可区分性（哪一个量能把两种情形分开）===');
  for (const k of keys) {
    console.log(`  ${dist(k) ? '✅ 可区分' : '⚠ 分不开'}  ${k.padEnd(16)} `
      + `对照=${JSON.stringify(base[k])}  扰动=${JSON.stringify(cut[k])}`);
  }
  console.log('\n⚗⚠ 结论留给判据与拍板，本台只给上表：'
    + '若 pathState / saysNotLoaded / saysMissingFile 三者皆可区分，'
    + '则「补一条独立断言」在装置上可行。');
} finally {
  try { await page.send('Page.close'); } catch {}
  try { cdp.close(); } catch {}
  try { proc.kill('SIGKILL'); } catch {}
}