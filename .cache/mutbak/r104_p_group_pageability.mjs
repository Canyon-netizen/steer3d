// r104_p_group_pageability.mjs —— 修订 104
//
// 目的：修订 103 把 P1–P8 标成「恒绿（读产物不读页面）」，但**没量过**
//       「把它们改成读页面之后，今天到底是绿是红」。
//       ⇒ 这正是「要不要修」所缺的那条信息。本探针只提供该信息，**不改任何判据**。
//
// 两条硬要求：
//   1) 读**真实渲染后的 DOM**，不是产物、不是扁平文本
//   2) 每条都要给**变异对照** —— 喂一个被污染的同形状字符串，
//      断言必须转红，否则这条对页面文本同样没有分辨力。
//      ⚠ 「今天是绿的」不等于「有牙」；两条都要量。

import { launch, Page, CDP } from '/Users/zhourui/code/steer3d/.cache/browser_verify/cdp_client.mjs';
import { readFileSync } from 'node:fs';

const URL = process.env.BV_URL || 'http://127.0.0.1:9005/';
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_r104_' + process.pid;
const ART = '/Users/zhourui/code/steer3d/frontend/public/latent/data/readable_subspace.json';
const AX = '/Users/zhourui/code/steer3d/frontend/public/latent/data/axis_readouts.json';

const die = (m) => { console.log('[自证失败] ' + m); process.exit(2); };
const truth = JSON.parse(readFileSync(ART, 'utf8'));
const ax = JSON.parse(readFileSync(AX, 'utf8'));
const H = truth.headline, SEP = H.separation_threshold, TS = H.threshold_sensitivity;
const seatKey = Object.keys(TS).find(k => Math.abs(Number(k) - SEP) < 1e-9);

// 每条断言写成 (s) => [ok, 读到的东西]，**与 verify_subspace.mjs 逐字同口径**
const A = {
  P1: s => { const g = (s.match(/至少\s*(\d+)\s*条/) || [])[1];
             return [Number(g) === TS[seatKey]?.perm_min, `读「至少 ${g} 条」，期望 ${TS[seatKey]?.perm_min}`]; },
  P2: s => { const g = (s.match(/这\s*(\d+)\s*个/) || [])[1];
             return [Number(g) === H.n_candidates, `读「这 ${g} 个」，期望 ${H.n_candidates}`]; },
  P3: s => { const g = (s.match(/\|cos\|\s*<\s*([\d.]+)/) || [])[1];
             return [Math.abs(Number(g) - SEP) < 1e-9, `读 |cos|<${g}，期望 ${SEP}`]; },
  P4: s => { const allKeys = Object.keys(TS).sort((a,b)=>Number(a)-Number(b));
             const listed = (s.match(/(\d\.\d+)→(\d+)\s*条/g) || []);
             const lk = listed.map(x => x.match(/(\d\.\d+)→/)[1]);
             const complete = lk.length === allKeys.length && allKeys.every(k => lk.includes(k));
             const consistent = listed.every(x => { const m = x.match(/(\d\.\d+)→(\d+)/);
               return Math.abs(Number(m[1]) - SEP) < 1e-9 || TS[m[1]]?.greedy === Number(m[2]); });
             return [complete && consistent, `页面里「k→N 条」内联格式命中 ${listed.length} 处（共需 ${allKeys.length} 档）`]; },
  P5: s => { const g = (s.match(/cos\(confidence,\s*caution\)\s*=\s*([\d.]+)/) || [])[1];
             const want = Number(ax?.axes?.caution?.specificity?.pair_cos_confidence_caution).toFixed(4);
             return [g === want, `读 ${g}，期望 ${want}`]; },
  P6: s => { const t = (s.match(/超过\s*([\d.]+)\s*门槛/) || [])[1];
             const n = (s.match(/还有\s*(\d+)\s*条/) || [])[1];
             return [Math.abs(Number(t) - SEP) < 1e-9 && Number(n) === H.absorbed.length,
                     `读「超过 ${t} 门槛，还有 ${n} 条」，期望 ${SEP} / ${H.absorbed.length}`]; },
  P7: s => { const g100 = (s.match(/Δ=100\s*仍有\s*([\d.]+)/) || [])[1];
             const want100 = truth.control.delta['100'];
             const gN = Number((s.match(/下面\s*(\d+)\s*条/) || [])[1]);
             const wantN = truth.surface_directions.length + (truth.named_axis_readouts||[]).length;
             return [Math.abs(Number(g100)-want100) < 5e-5 && gN === wantN,
                     `读 Δ=100 ${g100} / 下面 ${gN} 条，期望 ${want100} / ${wantN}`]; },
};

const { proc, version } = await launch({
  port: 9488, userDataDir: PROFILE, windowSize: '1700,1300', url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  await new Promise(r => setTimeout(r, 3500));

  const raw = await page.eval(`(() => {
    const g = s => { const e = document.querySelector(s);
      return e ? (e.innerText || '').replace(/\\s+/g,' ').trim() : null; };
    return JSON.stringify({
      state: (document.querySelector('[data-subspace]')||{}).getAttribute
               ? document.querySelector('[data-subspace]').getAttribute('data-subspace') : null,
      caveat: g('[data-bound-caveat]'),
      absorbed: g('[data-absorbed-note]'),
      control: g('[data-control-note]'),
      verdict: g('[data-verdict]'),
      headline: g('[data-headline-verdict]'),
      nRows: document.querySelectorAll('[data-threshold-row]').length,
    });
  })()`);
  const P = JSON.parse(raw);

  if (P.state !== 'ready') die('面板状态 ' + P.state + '，没读到数据');
  for (const k of ['caveat','absorbed','control']) if (!P[k]) die(`页面上取不到 [${k}]`);

  const SRC = { P1:P.caveat, P2:P.caveat, P3:P.caveat, P4:P.caveat,
                P5:P.absorbed, P6:P.absorbed, P7:P.control };

  console.log('面板状态 ' + P.state + '；阈值行 ' + P.nRows + '（DOM 实取）');
  console.log('');
  console.log('=== A. 今天若把 P 组改成读页面，会不会红 ===');
  const red = [];
  for (const k of Object.keys(A)) {
    const [ok, d] = A[k](SRC[k]);
    console.log('  ' + k + '  ' + (ok ? '绿' : '🔴 红') + '  ' + d);
    if (!ok) red.push(k);
  }

  console.log('');
  console.log('=== B. 变异对照：每条在**页面文本**上有没有牙齿 ===');
  // 污染：把同一形状的字符串改掉一个数字，断言必须转红
  const MUT = {
    P1: s => s.replace(/至少\s*(\d+)\s*条/, (m,n)=>`至少 ${Number(n)+1} 条`),
    P2: s => s.replace(/这\s*(\d+)\s*个/, (m,n)=>`这 ${Number(n)+1} 个`),
    P3: s => s.replace(/\|cos\|\s*<\s*([\d.]+)/, (m,n)=>`|cos| < ${Number(n)+0.1}`),
    P4: s => s + ' 0.35→9 条、0.45→12 条、0.60→16 条',
    P5: s => s.replace(/(cos\(confidence,\s*caution\)\s*=\s*)([\d.]+)/, (m,a,b)=>`${a}${Number(b)+0.1}`),
    P6: s => s.replace(/还有\s*(\d+)\s*条/, (m,n)=>`还有 ${Number(n)+1} 条`),
    P7: s => s.replace(/Δ=100\s*仍有\s*([\d.]+)/, (m,n)=>`Δ=100 仍有 ${Number(n)+0.1}`),
  };
  const toothless = [];
  for (const k of Object.keys(A)) {
    const [ok0] = A[k](SRC[k]);
    const [okM] = A[k](MUT[k](SRC[k]));
    const hasTooth = (okM === false);
    console.log('  ' + k + '  ' + (hasTooth ? '有牙（变异后转红 ✓）' : '⚠ 无牙（变异后仍绿）'));
    if (!hasTooth) toothless.push(k);
  }

  console.log('');
  console.log('=== C. 页面那个阈值表在 innerText 里长什么样（决定 P4 能否落地） ===');
  console.log('  ' + JSON.stringify(P.caveat.slice(0, 220)));
  console.log('');
  console.log('小结：改读页面会红 ' + (red.length ? red.join(',') : '无')
    + '；在页面文本上无牙 ' + (toothless.length ? toothless.join(',') : '无'));
} catch (e) {
  die('装置错：' + String(e && e.message ? e.message : e));
} finally {
  try { await cdp.send('Browser.close'); } catch {}
  try { proc.kill(); } catch {}
}