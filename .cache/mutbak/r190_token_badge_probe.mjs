/**
 * data-scene-token-badge 到底「永远不出现」还是「快照拍早了」？
 *
 * ⚠ 修订 190 的起因：C2 报它是「真死引用」，而它的渲染条件是
 *   `Scene3D.tsx:232  if (!latest)`，而 `latest` 只在
 *   `store.ts:119 ingestFrame()` 里被置位、`store.ts:165 reset()` 里清空。
 *   ⇒ 它要等**第一帧 ingest 之后**才出现，与 WebGL、与降级路径都无关。
 *
 * ⚠⚠⚴ 而面板探针 `probe_panels.mjs` 的根页就绪信号是 `[data-outcome="ready"]`，
 * ⚠⚠⚴ 那是 **InterventionOutcomePanel**，**与 Scene3D 的 frame 流没有因果关系**。
 * ⚠⚠⚴ ⇒ 「存档里没有这个标记」与「这个标记永远不存在」是**两件事**，
 * ⚠⚠⚴ 而 C2 报的是后者。本探针去分辨它们。
 *
 * 判法：不设就绪门，直接轮询 N 秒，看它**有没有出现过**。
 *
 * 用法：
 *   BV_URL=http://127.0.0.1:22655/ node r190_token_badge_probe.mjs
 */

import { launch, Page, CDP } from '/Users/zhourui/code/steer3d/.cache/browser_verify/cdp_client.mjs';

const URL = process.env.BV_URL || 'http://127.0.0.1:22655/';
const WAIT_S = Number(process.env.PROBE_WAIT_S || 150);
// ⚠ Scene3D 只在 WebGL 可用时渲染真 3D 路径；关掉就走降级组件。
// ⚠ 必须开着，否则量的是另一条路径（修订 188 已把这条写进 C0 的档位一致性）。
const WEBGL_FLAGS = ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'];
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_badge_' + process.pid;
const sleep = ms => new Promise(r => setTimeout(r, ms));

const { proc, version } = await launch({
  port: 9950 + (process.pid % 40),
  userDataDir: PROFILE,
  windowSize: '1900,1400',
  url: 'about:blank',
  extraArgs: WEBGL_FLAGS,
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);

try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});

  console.log(`=== ${URL} （开 WebGL，轮询 ${WAIT_S}s，不设就绪门）===`);
  const seen = [];
  let badge = null, frames = 0, webgl = null;
  for (let i = 0; i < WAIT_S; i += 3) {
    await sleep(3000);
    const st = await page.eval(`JSON.stringify((() => {
      const b = document.querySelector('[data-scene-token-badge]');
      const l = document.querySelector('[data-scene-loaded]');
      const c = document.querySelector('canvas');
      return {
        badge: b ? (b.getAttribute('data-scene-token-badge') + '|' + b.textContent.trim()) : null,
        loaded: l ? l.getAttribute('data-scene-loaded') : null,
        canvas: !!c,
        fallback: !!document.querySelector('[data-scene-fallback]'),
      };
    })())`);
    const s = JSON.parse(st);
    badge = s.badge;
    frames = s.loaded === null ? null : Number(s.loaded);
    webgl = s;
    if (s.badge && !seen.includes('badge')) seen.push('badge');
    if (s.loaded !== null && Number(s.loaded) > 0 && !seen.includes('frames')) seen.push('frames');
    console.log(`  t=${String(i + 3).padStart(3)}s  token-badge=${s.badge === null ? '（无）' : s.badge}`
      + `  data-scene-loaded=${s.loaded}  canvas=${s.canvas}  fallback=${s.fallback}`);
    if (s.badge) break;
  }

  console.log('\n=== 结论 ===');
  if (badge !== null) {
    console.log(`  ✅ data-scene-token-badge **出现了**：${badge}`);
    console.log('  ⇒ C2 那条「真死引用」**判错理由**：它不是死引用，');
    console.log('    而是探针的快照**早于第一帧 ingest**。');
  } else {
    console.log(`  ⚠⚠ 等了 ${WAIT_S}s 仍**没有** data-scene-token-badge。`);
    console.log(`     此刻 data-scene-loaded=${frames}`
      + `（frames=${frames} ⇒ ${frames > 0 ? '有帧却仍无徽章 ⇒ 真死引用' : '一帧都没进来 ⇒ 是就绪时序，不是死引用'}）`);
  }
  console.log(`  见过的事件：${JSON.stringify(seen)}`);
  console.log('RESULT badge_probe  DONE');
} catch (e) {
  console.log('页内异常：' + String((e && e.message) || e));
  console.log('RESULT badge_probe  ERROR');
} finally {
  try { await cdp.close(); } catch (_) {}
  try { proc.kill(); } catch (_) {}
}