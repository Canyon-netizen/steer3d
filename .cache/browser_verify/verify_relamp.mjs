import { readFileSync } from 'node:fs';
import { launch, Page, CDP } from './cdp_client.mjs';

/**
 * 判据：注入口径说明必须真的算出来，而不是把 1.18 写死。
 *
 * 背景：向量从 hidden_states[:,L]（第 L 个 block 的**输出**）提取，而在线注入走
 * block L 的 forward_pre_hook，写进 hidden_states[:,L-1]。被扰动的那份残差比标定
 * 用的那份小，所以真实相对幅度 = s·rms(L)/rms(L-1) ≈ 1.18s。
 *
 * 判据主体是**页面上读者看到的那行文字**；`data-relamp*` 属性只用来交叉核对
 * 「属性说的数」与「画/印出来的数」是否一致。外部真值取磁盘上的
 * layer_profiles.json（layer_rms 的来源），不取页面自己报的值。
 *
 * R4 是最重要的一条：换强度档位，显示的百分比必须跟着变。
 *   —— 这一条专门防「把比值写死」。写死的版本在所有强度下都显示同一个数，
 *      而页面**看起来完全正常**。
 */
const URL = process.env.BV_URL || 'http://127.0.0.1:10330/';
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_relamp_' + process.pid;
const sleep = ms => new Promise(r => setTimeout(r, ms));

const prof = JSON.parse(readFileSync(
  '/Users/zhourui/code/steer3d/backend/examples/output/layer_profiles.json', 'utf8'));
const rmsAt = L => prof.layers[L].mean_norm;

const results = [];
const check = (name, ok, detail) => {
  results.push({ name, ok: !!ok, detail });
  console.log(`[${ok ? 'PASS' : 'FAIL'}] ${name}: ${detail}`);
};

const { proc, version } = await launch({
  port: 9483, userDataDir: PROFILE, windowSize: '1600,1000', url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  await sleep(11000);

  const read = `(() => {
    const el = document.querySelector('[data-relamp]');
    if (!el) return JSON.stringify({present:false});
    const r = el.getBoundingClientRect();
    return JSON.stringify({
      present:true,
      text: (el.innerText||'').replace(/\\s+/g,' ').trim(),
      attr_relamp: el.getAttribute('data-relamp'),
      attr_ratio: el.getAttribute('data-relamp-ratio'),
      attr_layer: el.getAttribute('data-relamp-layer'),
      w: Math.round(r.width), h: Math.round(r.height),
    });
  })()`;

  const first = JSON.parse(await page.eval(read));
  check('R1 说明行存在', first.present, first.present ? `text="${first.text}"` : 'not found');

  if (!first.present) {
    console.log('\nRESULT FAIL  1/6');
  } else {
    check('R1b 有非零包围盒（不是隐藏元素）',
      first.w > 0 && first.h > 0, `${first.w}x${first.h}px`);

    const L = Number(first.attr_layer);
    const expectRatio = rmsAt(L) / rmsAt(L - 1);
    check('R2 属性里的比值 = 外部真值 rms(L)/rms(L-1)',
      Math.abs(Number(first.attr_ratio) - expectRatio) < 5e-3,
      `页面 ${first.attr_ratio} vs layer_profiles.json ${expectRatio.toFixed(5)} ` +
      `(rms(${L})=${rmsAt(L).toFixed(3)} rms(${L - 1})=${rmsAt(L - 1).toFixed(3)})`);

    // 交叉核对：文字里印出来的百分数，必须与属性一致（读者看到的 vs 页面自称的）
    const printed = (first.text.match(/([\d.]+)%/) || [])[1];
    const attrPct = Number(first.attr_relamp) * 100;
    check('R3 文字里的百分数与属性一致（读者所见 vs 页面自称）',
      printed != null && Math.abs(Number(printed) - attrPct) < 0.15,
      `文字 ${printed}% vs 属性 ${attrPct.toFixed(2)}%`);

    check('R4 文字说明了注入写的是 block 的输入',
      /输入/.test(first.text), first.text.slice(0, 90));

    // R5 最重要：换强度，百分数必须跟着变（防写死）
    // 档位是 STRENGTH_PRESETS = [0.02, 0.05, 0.1, 0.2, 0.4]，默认 0.1。
    // 用 0.4 这个档，因为它离默认值最远。
    const TARGET_S = 0.4;
    const grab = async () => JSON.parse(await page.eval(`(() => {
      const el = document.querySelector('[data-relamp]');
      return JSON.stringify({r: el && el.getAttribute('data-relamp'),
                             t: el && (el.innerText||'').replace(/\\s+/g,' ').trim()});
    })()`));
    const before = await grab();
    const clicked = await page.eval(`(() => {
      const b = [...document.querySelectorAll('button')]
        .find(x => x.textContent.trim() === '${TARGET_S}');
      if (!b) return 'no-button';
      b.click(); return 'clicked';
    })()`);
    await sleep(900);
    const after = clicked === 'clicked' ? await grab() : { r: null, t: '' };
    check('R5 换强度后显示的相对幅度跟着变（未写死）',
      after.r != null && before.r != null && after.r !== before.r,
      `${clicked}: ${before.r} -> ${after.r}`);

    if (after.r != null && Number(after.r) > 0) {
      const ratio = Number(first.attr_ratio);
      const implied = Number(after.r) / TARGET_S;
      check('R6 换档后比值仍等于 rms(L)/rms(L-1)',
        Math.abs(implied - ratio) < 5e-3,
        `${TARGET_S} 档隐含比值 ${implied.toFixed(5)} vs ${ratio.toFixed(5)}`);
    }
  }
} catch (e) {
  check('装置', false, String(e && e.message ? e.message : e));
} finally {
  try { await page.close(); } catch {}
  cdp.close();
  proc.kill('SIGKILL');
}

const pass = results.filter(r => r.ok).length;
console.log(`\nRESULT ${pass === results.length ? 'PASS' : 'FAIL'}  ${pass}/${results.length}`);
process.exit(pass === results.length ? 0 : 1);
