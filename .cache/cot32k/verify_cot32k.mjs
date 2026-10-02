// Does the page tell the truth about the 32k re-run, and does it stop
// claiming the thing that run overturned?
//
// Background. The CoT block shipped with one experiment: a 60-step-budget
// family (168 runs) in which 0/168 traces ever closed `</think>` and only
// 7/168 yielded a parseable answer. Its closing line read
//
//     "改的是词，不是思路，也不是长度"  (it changes the words, not the
//                                      reasoning, and not the length)
//
// The 32k-budget re-run contradicts two halves of that. 56/72 traces now
// close and 54/72 yield an answer, so the answer dimension stops being
// "unmeasured" and becomes a genuine null. And the free-run length ratio
// (intervened arm vs the zero-vector arm of the same problem) is bimodal:
// the runs that finish are SHORTER than control, the runs that don't finish
// run up to 15.6x longer. Neither half is visible in the shipped
// `reason_len_ratio`, which compares against the teacher-forced shadow and
// is pinned to ~1 by construction.
//
// So the checks here are deliberately two-sided:
//   * the new block's numbers are on screen with their denominators, and
//   * the sentence the 32k data refuted is no longer on the page at all.
//
// A check that only asserted the new block would still pass if the old
// claim stayed, leaving the page contradicting itself. Hence the explicit
// `not.test` below.
import { launch, CDP, Page } from '../browser_verify/cdp_client.mjs';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';

const URL = 'http://127.0.0.1:8917/latent/index.html';
const sleep = ms => new Promise(r => setTimeout(r, ms));

const fails = [];
const chk = (c, label, extra = '') => {
  console.log((c ? '  ok   ' : '  FAIL ') + label + (extra ? '   ' + extra : ''));
  if (!c) fails.push(label);
};

const bytes = readFileSync('frontend/public/latent/index.html');
const HASH = createHash('sha256').update(bytes).digest('hex');
console.log('index.html sha256:', HASH.slice(0, 16), `(${bytes.length} bytes)`);

// ---- the shipped payload, checked before the page is even opened ---------
const reg = await (await fetch('http://127.0.0.1:8917/latent/models.json')).json();
const big = reg.models.find(m => m.d_model === 2048);
const c32 = await (await fetch(`http://127.0.0.1:8917/latent/${big.base}cot_effect_32k.json`)).json();
const c60 = await (await fetch(`http://127.0.0.1:8917/latent/${big.base}cot_effect.json`)).json();

console.log('\n===== 产物本身 =====');
chk(c32.control_is_identity === true, '32k 产物自带「对照臂恒等」标记');
chk(c60.n_runs === 168 && c60.coverage.closed_think === 0,
    '60 步那批仍是 168 次 / 0 次闭合（没被 32k 覆盖）',
    `${c60.n_runs} / ${c60.coverage.closed_think}`);
chk(c32.coverage.closed_think > 0, '32k 批次确实有闭合的轨迹',
    `${c32.coverage.closed_think}/${c32.coverage.runs}`);
chk(c32.coverage.answer_known > c60.coverage.answer_known * 5,
    '32k 的答案可解析数远高于 60 步那批',
    `${c60.coverage.answer_known}/${c60.runs} -> ${c32.coverage.answer_known}/${c32.runs}`);
const fr = c32.free_run_len_by_closure || {};
chk(!!fr.closed && !!fr.open, '按闭合与否分组的自由生成长度比存在',
    JSON.stringify(fr));
// The whole point of splitting by closure: the two groups must differ, or the
// split is decoration.
chk(fr.closed && fr.open && fr.open.median > fr.closed.median * 1.5,
    '没跑完的那组明显更长（分组不是装饰）',
    fr.closed && fr.open ? `${fr.closed.median}x vs ${fr.open.median}x` : '');
// And one direction must actually fail to close, else there is no story.
const up = c32.rows.find(r => r.direction === 'confidence_up');
const dn = c32.rows.find(r => r.direction === 'confidence_down');
chk(up && up.closed_think / up.n < 0.5, 'confidence_up 多数运行没跑完',
    up ? `${up.closed_think}/${up.n}` : '');
chk(dn && dn.closed_think / dn.n >= 0.8, 'confidence_down 几乎都跑完了',
    dn ? `${dn.closed_think}/${dn.n}` : '');

// ---- now the page --------------------------------------------------------
const { proc, version } = await launch({
  port: 9371, userDataDir: '/Users/zhourui/code/steer3d/.cache/cot32k/profile',
  url: 'about:blank',
});
console.log('chromium:', version.Browser);
const cdp = await CDP.connect(
  `ws://127.0.0.1:9371/devtools/browser/${version.webSocketDebuggerUrl.split('/').pop()}`);
const page = await Page.create(cdp);
await page.send('Network.enable');
await page.send('Network.setCacheDisabled', { cacheDisabled: true });
await page.send('Emulation.setDeviceMetricsOverride',
  { width: 1600, height: 1100, deviceScaleFactor: 1, mobile: false });
const exceptions = [];
cdp.on(m => { if (m.method === 'Runtime.exceptionThrown')
  exceptions.push(m.params.exceptionDetails?.exception?.description
                  || m.params.exceptionDetails?.text || 'unknown'); });

await page.send('Page.navigate', { url: `${URL}?orient=reset&m=${big.id}` });
await page.waitForEvent('Page.loadEventFired', 40000);
await sleep(7000);
if (await page.eval(`(()=>{const o=document.getElementById('orientation');
    return !!(o&&getComputedStyle(o).display!=='none');})()`)) {
  await page.click('#orientClose'); await sleep(800);
}
await page.click('#tabDelta'); await sleep(2600);

// Read BOTH the marker div and its whole wrapper. The 32k block used to be
// appended after the marker's closing tag, where a `[data-cotblock]`-scoped
// read could not see it — a selector too narrow looks exactly like a feature
// that was never implemented.
const READ = `(()=>{
  const b=document.querySelector('[data-cotblock]');
  const w=document.getElementById('tblTop');
  return { has: !!b,
           text: [b?b.innerText:'', w?w.innerText:''].filter(Boolean).join(' || '),
           inBlock: b ? b.innerText : '' };
})()`;
const g = await page.eval(READ);
const T = g.text;

console.log('\n===== 页面上 =====');
chk(g.has, '思维链面板渲染出来了');
chk(T.includes('32k 预算重跑'), '新块的标题在');
chk(g.inBlock.includes('32k 预算重跑'), '新块在 data-cotblock 内部（不是兄弟节点）');
chk(T.includes(String(c32.n_runs)) && T.includes(String(c32.n_problems)),
    `新块写明规模（${c32.n_runs} 次 / ${c32.n_problems} 题）`);

// coverage, both sides
chk(T.includes(`${c32.coverage.closed_think}/${c32.coverage.runs}`),
    `跑完 </think> ${c32.coverage.closed_think}/${c32.coverage.runs} 在面板上`);
chk(T.includes(`${c60.coverage.closed_think}/${c60.coverage.runs}`),
    `60 步那批的 0/168 也并排给出（读者能看出差别在哪）`);
chk(T.includes(`${c32.coverage.answer_known}/${c32.coverage.runs}`),
    `能解析答案 ${c32.coverage.answer_known}/${c32.coverage.runs} 在面板上`);

// the bimodal split, with both medians
if (fr.closed && fr.open) {
  chk(T.includes(String(fr.closed.median)) && T.includes(String(fr.open.median)),
      `双峰两个中位数都在（${fr.closed.median}× / ${fr.open.median}×）`);
  chk(T.includes(String(fr.open.max)), `最高倍数 ${fr.open.max}× 在面板上`);
}

// ---- the two-sided part: the refuted sentence must be GONE --------------
console.log('\n--- 32k 推翻的那句话必须消失 ---');
chk(!/改的是词，不是思路，也不是长度/.test(T),
    '旧的「改的是词，不是思路，也不是长度」整句已删除');
chk(!/推理的条数、长度和自查次数都没动/.test(T),
    '旧的「长度和自查次数都没动」整句已删除');
// ...and the replacement must say *why* the old number could not see it.
chk(/影子臂|teacher-forced/.test(T) && /恒等于 ?1|测不出啰嗦/.test(T),
    '新块说明旧的长度比是对影子臂比的、恒等于 1，测不出啰嗦');
chk(/双峰/.test(T), '新块点明这是双峰分布');
// ...and the scoping must be present, so a reader cannot apply the old
// wording to the new run.
chk(/只对下面这张表成立|已.{0,4}被下一块推翻|被下一块推翻/.test(T),
    '旧结论被显式限定在 60 步那批范围内，并说明已被推翻');

// ---- the answer dimension, and the caveat that must stay ---------------
console.log('\n--- 答案这一维：现在是真阴性，但分母仍要跟着 ---');
chk(T.includes('一次都没变') || /全同/.test(T), '答案"一次都没变"在面板上');
chk(/写不完的那些不参与|不参与这个比较/.test(T),
    '仍写明"写不完的那些不参与这个比较"（不能简化成"干预不影响答案"）');
chk(!/干预不影响答案(?!.*仍然错)/.test(T) || /仍然是错的/.test(T),
    '没有把"答案没变"直接说成"干预不影响答案"');

// ---- the batch is still running, and the panel must say so --------------
// This block's headline is a NEGATIVE result: the answers did not change.
// A negative result computed on 76 of a planned 96 runs is a different claim
// from one computed on all 96, and a later shard can overturn it. The
// denominator alone ("76 runs") does not tell a reader that anything is
// outstanding -- it reads as a finished count.
console.log('\n--- 这一批还没跑完，页面必须说出来 ---');
const planned = c32.planned_runs || 0;
chk(planned > c32.n_runs, '数据文件里记着计划总量，且确实还没跑完',
    `planned=${planned} landed=${c32.n_runs}`);
chk(/这一批还没跑完/.test(T), '面板明说这一批尚未跑完');
chk(T.includes(String(planned)) && T.includes(String(c32.n_runs)),
    `面板同时给出计划 ${planned} 次与已落盘 ${c32.n_runs} 次`);
chk(/下面所有数字都会变|还会变/.test(T), '明说下面这些数字会随批次变化');
chk(/不参与这个比较|写不完/.test(T) && /这一批还没跑完/.test(T),
    '「未跑完」与「写不完不参与比较」两处限定都在，读者不会被误导');

console.log('\n--- 阴性对照仍在 ---');
chk(/零向量/.test(T), '说明对照组是零向量');
chk(/测不出差别|不等于没有差别/.test(T), '自我检查仍标着 p 值与"测不出差别"');

chk(exceptions.length === 0, '无未捕获异常', exceptions.join(' | '));

console.log('\n---------------------------------------');
console.log(fails.length ? `失败 ${fails.length} 条` : 'ALL PASS');
process.exit(fails.length ? 1 : 0);
