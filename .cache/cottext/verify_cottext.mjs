// Does the new "read it word by word" block tell the truth, and does it avoid
// the one misreading that block is built to cause?
//
// Why this block exists. Everything the page said about the effect of the
// steering vector on the chain of thought was a percentage: 94% of tokens
// unchanged, this much verbatim overlap, that length ratio. The user asked what
// the vector did to the chain of thought. A percentage cannot answer that, and
// the raw texts -- present in every run all along -- were never shipped.
//
// The trap. `run_intervention.py` lines 272-282 take the shadow's own argmax
// but then feed BOTH streams the primary's token. So `shadow_text` is the
// primary's prose with individual words patched in, not an essay the unsteered
// model would have written. Shown as prose it breaks grammar at every patch
// ("We need looking for all pairs", "the greatest common divisor ( m and n is
// 1"), and a reader concludes the unsteered model got dumber -- the exact
// opposite of the finding. So the checks here are two-sided:
//
//   * the block ships the real text, and every number on screen equals the
//     number in the payload (read out of the DOM and compared, not asserted
//     by the presence of an element), and
//   * the block refuses to present the shadow as an alternative essay.
//
// The second half is the half a presence-check cannot do. Asserting "a warning
// element exists" passes just as happily when the warning is about something
// else, so the checks here assert *what* the warning says and that the
// artefact it describes is visible on the page at the same time.
//
// On failure: MUTATION.md lists which mutation each check was proved against.
import { launch, CDP, Page } from '../browser_verify/cdp_client.mjs';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';

const URL = 'http://127.0.0.1:8917/latent/index.html';
const PORT = 9401;
const PROFILE = '.cache/cottext/profile';
const sleep = ms => new Promise(r => setTimeout(r, ms));

const fails = [];
const chk = (c, label, extra = '') => {
  console.log((c ? '  ok   ' : '  FAIL ') + label + (extra ? '   ' + extra : ''));
  if (!c) fails.push(label);
};

// ---- 产物本身，先在开页面之前查 ------------------------------------------
const bytes = readFileSync('frontend/public/latent/index.html');
const HASH = createHash('sha256').update(bytes).digest('hex');
console.log('index.html sha256:', HASH.slice(0, 16), `(${bytes.length} bytes)`);

const reg = await (await fetch('http://127.0.0.1:8917/latent/models.json')).json();
const big = reg.models.find(m => m.d_model === 2048);
const BASE = `http://127.0.0.1:8917/latent/${big.base}`;
const T = await (await fetch(BASE + 'cot_texts.json')).json();

console.log('\n===== 产物：cot_texts.json =====');
const steered = T.runs.filter(r => parseFloat(r.strength) !== 0);
const zeros = T.runs.filter(r => parseFloat(r.strength) === 0);
// Structural, not a hard-coded head count. Pinning `=== 76` meant the batch
// growing to 84 turned the check red -- and the only way to "fix" it would have
// been to edit the number, which is precisely the habit that lets a check stop
// meaning anything. These hold at 76, at 84, and at 96.
chk(T.n_runs === T.runs.length,
    '头部声明的运行数与数组实际长度一致', `${T.n_runs} vs ${T.runs.length}`);
chk(steered.length === zeros.length,
    '干预臂与零向量对照一一配对（每题各一次）', `${steered.length} / ${zeros.length}`);
chk(T.runs.length === 2 * steered.length,
    '总运行数 == 干预臂数 × 2', `${T.runs.length} = 2 × ${steered.length}`);
// batch_complete must follow from the count, not be maintained by hand.
chk(T.batch_complete === (T.n_runs >= T.planned_runs),
    '「已跑完」标记与 计划/实到 数一致（不是手工维护的）',
    `n_runs=${T.n_runs} planned=${T.planned_runs} complete=${T.batch_complete}`);
// Every steered run must name the same layer and strength as its control, or
// the "this is the same question, one vector apart" framing is false.
const byKey = {};
T.runs.forEach(r => { byKey[`${r.label}|${r.direction}`] ||= []; byKey[`${r.label}|${r.direction}`].push(r); });
chk(Object.values(byKey).every(g => new Set(g.map(r => r.layer)).size === 1),
    '同一题同一方向的所有运行注入层一致');
chk(Object.values(byKey).every(g => g.some(r => parseFloat(r.strength) === 0)
                                   && g.some(r => parseFloat(r.strength) !== 0)),
    '每一组都同时含零向量对照与干预臂（没有孤儿运行）');
chk(zeros.every(z => z.zero_strength_control.texts_identical),
    '每个零向量对照的两臂逐字相同（采集链路是干净的）');
chk(steered.every(s => s.first_diverged_step !== null),
    '每个干预臂都量到了 first_diverged_step');
chk(steered.every(s => s.token_agreement > 0 && s.token_agreement <= 1),
    'token_agreement 落在 (0,1]');

// The payload must not be able to imply a claim it cannot support. If some
// run had no divergence, shipping it with a "they differ here" window would be
// a lie; the builder says so, and this asserts it stayed said.
chk(steered.every(s => s.primary_head.note === '分岔处'),
    '所有分岔窗口都标注了这是分岔处');

// 零向量对照必须是「没有分岔」的状态，而不是被塞进同一套分岔叙事里。
const z0 = zeros[0];
chk(z0.first_diverged_step === null && z0.token_agreement === 1.0,
    '零向量对照记录 first_diverged_step=null（不是 0，也不是某个假分岔点）',
    `fd=${z0.first_diverged_step} agree=${z0.token_agreement}`);

// ---- 开页面 --------------------------------------------------------------
const { proc, version } = await launch({
  port: PORT, userDataDir: PROFILE, windowSize: '1600,1000', url: 'about:blank',
});
console.log('chromium:', version.Browser);
const cdp = await CDP.connect(
  `ws://127.0.0.1:${PORT}/devtools/browser/${version.webSocketDebuggerUrl.split('/').pop()}`);
const page = await Page.create(cdp);
await page.send('Network.enable');
// Mutation testing edits the shipped HTML. A cached copy of the page would
// make every mutation silently pass, which is the exact failure this project
// has already paid for once on the Next.js bundle. One flag removes the
// possibility rather than hoping the server sends no-cache.
await page.send('Network.setCacheDisabled', { cacheDisabled: true });
await page.send('Emulation.setDeviceMetricsOverride',
  { width: 1600, height: 1100, deviceScaleFactor: 1, mobile: false });

// The CoT payloads only exist under the 1.7B data directory. The page defaults
// to a smaller model whose directory 404s them, and `S.cot` is then legitimately
// null -- so a run that forgot this would report "the block never rendered" and
// blame the feature instead of the model selector.
await page.send('Page.navigate', { url: `${URL}?orient=reset&m=${big.id}` });
await page.waitForEvent('Page.loadEventFired', 40000);
await sleep(7000);
if (await page.eval(`(()=>{const o=document.getElementById('orientation');
    return !!(o&&getComputedStyle(o).display!=='none');})()`)) {
  await page.click('#orientClose'); await sleep(800);
}
await page.click('#tabDelta'); await sleep(2800);

const block0 = await page.eval(`(() => {
  const el = document.querySelector('[data-cottext]');
  return el ? el.innerText : null;
})()`);

console.log('\n===== 页面：这一块在不在 =====');
chk(!!block0, '[data-cottext] 渲染出来了');
if (!block0) { console.log('\n没有这一块，后面的判据全部无意义。'); process.exit(1); }
console.log('  块长度 ' + block0.length + ' 字符');

// ---- 页面上的数字必须等于产物里的数字 ------------------------------------
// 这一段是整个判据的核心。把选择器读回来的字符串跟 JSON 比，而不是断言
// "某个 span 存在"——后者在数字写错时照样全绿。
async function readShown(index) {
  return page.eval(`(() => {
    const sel = document.querySelector('[data-cotpick]');
    if (sel) { sel.value = ${index}; sel.dispatchEvent(new Event('change', {bubbles:true})); }
    return new Promise(r => setTimeout(() => {
      const el = document.querySelector('[data-cottext]');
      r(el ? el.innerText : null);
    }, 500));
  })()`);
}

// The page is supposed to open on the run that diverged earliest: that is
// where the shared prefix is longest and a beginner can most easily see the
// event. This is asserted rather than assumed -- the state field starts at -1
// precisely so the renderer's "pick the best" branch is reachable, and a 0
// there silently disables it while the code comment still claims otherwise.
const best = steered.reduce((a, b) =>
  (b.first_diverged_step < a.first_diverged_step ? b : a));
const bestIdx = steered.indexOf(best);
const firstShown = await page.eval(
  `document.querySelector('[data-cotpick]').value`);
chk(parseInt(firstShown, 10) === bestIdx,
    '首次打开就落在分岔最早的那一次运行上',
    `页面=${firstShown} 期望=${bestIdx}（第 ${best.first_diverged_step} 步）`);

const block = await readShown(bestIdx);
chk(!!block && block === block0, '切到该次运行后内容与首次渲染一致（选择器可往返）');

const checks = [
  [`页面上写着「第 ${best.first_diverged_step} 步」`,
   block.includes(`第 ${best.first_diverged_step} 步`), block.slice(0, 60)],
  [`一致率 ${(best.token_agreement * 100).toFixed(1)}%`,
   block.includes(`${(best.token_agreement * 100).toFixed(1)}%`)],
  [`每 100 个换掉 ${((1 - best.token_agreement) * 100).toFixed(1)} 个`,
   block.includes(`${((1 - best.token_agreement) * 100).toFixed(1)} 个`)],
  [`KL ${(best.mean_logit_kl || 0).toFixed(4)}`,
   block.includes((best.mean_logit_kl || 0).toFixed(4))],
  [`熵 ${best.mean_entropy_primary.toFixed(3)}`,
   block.includes(best.mean_entropy_primary.toFixed(3))],
  [`熵对照 ${best.mean_entropy_shadow.toFixed(3)}`,
   block.includes(best.mean_entropy_shadow.toFixed(3))],
  [`题号 ${best.label}`, block.includes(best.label)],
  [`注入层 L${best.layer}`, block.includes(`L${best.layer}`)],
  [`强度 ${best.strength}`, block.includes(String(best.strength))],
];
console.log('\n===== 页面数字 == 产物数字 =====');
for (const [label, ok, extra] of checks) chk(ok, label, ok ? '' : (extra || ''));

// ---- 原文真的在页面上，而且就是数据里那两段 -------------------------------
// Read the two arm blocks back out of the DOM *separately*. Comparing the
// payload's two strings to each other would pass no matter what the page
// rendered: feeding the primary's continuation into both arms leaves the
// payload untouched and the prose self-consistent, and only a check that
// measures the page can see it. That is mutation M2.
console.log('\n===== 原文 =====');
const arms = await page.eval(`(() => {
  const g = k => { const e = document.querySelector('[data-cotarm="'+k+'"]');
    return e ? e.innerText : null; };
  const p = document.querySelector('[data-cotpre]');
  return { primary: g('primary'), shadow: g('shadow'), pre: p ? p.innerText : null };
})()`);
chk(!!arms.primary && arms.primary.length > 20, '干预臂那一段在页面上且非空',
    arms.primary ? arms.primary.length + ' 字符' : 'MISSING');
chk(!!arms.shadow && arms.shadow.length > 20, '对照臂那一段在页面上且非空',
    arms.shadow ? arms.shadow.length + ' 字符' : 'MISSING');
chk(!!arms.primary && !!arms.shadow && arms.primary !== arms.shadow,
    '页面上这两段文字真的不同（不是同一段贴了两遍）');
// Every read below is guarded. A `null.includes` here aborts the whole script,
// and an aborted script reports nothing about the checks after it -- which is
// how a page with one missing element silently passes as "no news".
const has = (s, frag) => !!s && typeof frag === 'string' && s.includes(frag);
const cut = t => (t || '').trim().slice(0, 40);
chk(has(arms.primary, cut(best.primary_head.after_primary)),
    '干预臂那段原文确实在页面上（取前 40 字符）',
    JSON.stringify(best.primary_head.after_primary.slice(0, 40)));
chk(has(arms.shadow, cut(best.primary_head.after_shadow)),
    '对照臂那段原文确实在页面上',
    JSON.stringify(best.primary_head.after_shadow.slice(0, 40)));
chk(has(arms.pre, cut(best.primary_head.before)),
    '分岔前的共同原文单独成块，且就是数据里那段');
// The block's central promise is "identical up to the split". If the shared
// prefix were missing, or were the shadow's own text, that promise would be
// unfalsifiable on the page.
chk(!!arms.pre && !arms.pre.startsWith('干预臂'),
    '共同原文那块的正文就是原文本身（不是标题被算进去）');

// 「分岔前两臂一字不差」是这一块的结构性承诺。`before` 是从分岔点往回截的
// 一段，所以它不可能比分岔点更靠后；这条能从产物证伪。
chk(best.primary_head.split_char >= best.primary_head.before.length,
    '共同原文不会越过分岔点（before 是从分岔处往回截的）',
    `split_char=${best.primary_head.split_char} before=${best.primary_head.before.length}`);
chk(best.primary_head.split_char >= 0, 'split_char >= 0（-1 表示两臂相同，这里不该出现）');
// The two continuations must actually differ in their very first character --
// otherwise the "split" is somewhere the page is not showing.
chk(best.primary_head.after_primary[0] !== best.primary_head.after_shadow[0],
    '两臂在切出来的第一个字符上就不同（分岔点就在这个位置）',
    JSON.stringify([best.primary_head.after_primary[0],
                    best.primary_head.after_shadow[0]]));

// ---- 两条限制必须写在正文旁边，且说的就是这件事 --------------------------
console.log('\n===== 防误读的免责声明 =====');
chk(/不是.*没有向量时模型会写/.test(block),
    '明说对照臂不是「没加向量时会写的文章」');
chk(/接缝|补丁/.test(block),
    '解释了换词处的语法断裂是补丁接缝，不是模型变笨');
chk(/零向量/.test(block), '给出了零向量对照这条采集链路证据');
chk(/逐字完全相同|并不相同/.test(block), '对零向量对照给出了明确判定');
chk(/token/.test(block) && /字符/.test(block),
    '同时出现 token 步数与字符位置两个单位');
// The two numbers are both on screen; what stops a reader treating them as the
// same quantity is the sentence saying so. Assert the claim, not just the
// vocabulary -- a check for "字符 appears somewhere" passes just as happily
// when the block has quietly stopped saying the units differ.
// Match the one sentence the claim rests on, not a disjunction of near-synonyms.
// The looser version was satisfied by "还有两个单位别搞混" -- a heading phrase
// the unit-inverting mutation never touches -- so it stayed green while the
// block's actual claim had been reversed. A check written as an OR is only as
// strong as its weakest branch, and one unreachable branch makes the whole
// thing vacuous.
chk(block.includes('它们不是一回事'),
    '明说 token 步数与字符位置不是一回事（该句必须在，而不是只把两个词印出来）');
chk(new RegExp(`第\\s*${best.primary_head.split_char}\\s*个字符`).test(block),
    '字符位置带上了「个字符」的单位标注',
    `期望 第 ${best.primary_head.split_char} 个字符`);

// 免责声明不能是空壳：它点名的那个现象必须真的在页面上。
const shadowsInData = steered.map(s => s.primary_head.after_shadow).filter(t => /\(\s|\s\)|need looking|divisor \(/.test(t));
console.log(`  产物里含断裂痕迹的对照臂片段：${shadowsInData.length}/${steered.length}`);
chk(shadowsInData.length > 0,
    '产物里确实存在会读成「语法断裂」的对照片段（免责声明有实指）');

// ---- 切到另一次运行，数字和原文都必须跟着变 -------------------------------
// ---- 布局：这一块必须真的看得见 -------------------------------------------
// Every check above reads innerText, which is blind to layout. The block
// measured 1212px tall starting 2350px down a 300px-tall scroll window, with
// all three text parts reporting visibleInBox=false on arrival -- and every
// innerText check in this file still passed. These two check the pixels.
// `closest('div')` returns the element ITSELF when the element is a div, so the
// first version of this measured the block (clientHeight 1211 == scrollHeight
// 1211, offTop 0) and every layout conclusion drawn from it was about the wrong
// element. Walk up to the nearest ancestor that actually scrolls.
const SCROLLBOX = `(() => {
  let e = document.querySelector('[data-cottext]');
  while (e && e !== document.body) {
    if (getComputedStyle(e).overflowY === 'auto' || getComputedStyle(e).overflowY === 'scroll') return e;
    e = e.parentElement;
  }
  return null;
})()`;
console.log('\n===== 布局：这一块能不能被看到 =====');
const lay = await page.eval(`(() => {
  const blk = document.querySelector('[data-cottext]');
  let e = blk;
  while (e && getComputedStyle(e).overflowY !== 'auto' && getComputedStyle(e).overflowY !== 'scroll') e = e.parentElement;
  const box = e;
  const bx = box.getBoundingClientRect();
  const bb = blk.getBoundingClientRect();
  return {
    clientH: box.clientHeight, scrollH: box.scrollHeight,
    offTop: Math.round(bb.top - bx.top),
    docScrolls: document.documentElement.scrollHeight > innerHeight,
  };
})()`);
console.log(`  滚动窗口 ${lay.clientH}px / 内容 ${lay.scrollH}px，块距顶 ${lay.offTop}px`);
chk(lay.clientH > 0 && lay.scrollH > lay.clientH,
    '面板确实是一个需要滚动的内层窗口（前提成立，不是没滚却以为要滚）');
chk(!lay.docScrolls,
    '整页不滚动（所以跳转必须滚内层窗口，滚 window 会是死按钮）');

// The jump link has to exist before it can be tested, and its hint has to carry
// a measured offset rather than a plausible-looking constant.
const jumpTxt = await page.eval(
  `(()=>{const b=document.querySelector('[data-jump="cottext"]');
    const h=document.querySelector('[data-jumphint]');
    return {btn: b?b.innerText:null, hint: h?h.innerText:null};})()`);
chk(!!jumpTxt.btn, '顶部有跳转到这一块的入口', jumpTxt.btn);
await sleep(400);   // the hint is written in a rAF, after layout settles
const jumpTxt2 = await page.eval(
  `(()=>{const h=document.querySelector('[data-jumphint]');
    return {hint: h?h.innerText:null};})()`);
const hint = jumpTxt2.hint;
chk(!!hint && /px/.test(hint), '入口下方写明了距离与窗口高度', hint);
chk(!!hint && new RegExp(`${lay.offTop}\\s*px`).test(hint),
    '提示里的距离与实测一致（不是写死的数字，也不是布局没稳定时量的）', hint);
chk(!!jumpTxt.btn && jumpTxt.btn.includes(`第 ${best.first_diverged_step} 步`),
    '跳转按钮上的步数 == 块实际打开的那一次（两个控件不能说不同的运行）',
    `${jumpTxt.btn}  vs  第 ${best.first_diverged_step} 步`);

// Click it, then re-measure. This is the check a `scrollTo` on the wrong
// element fails, and that no innerText check could ever catch.
await page.click('[data-jump="cottext"]');
await sleep(700);
const jumped = await page.eval(`(() => {
  const blk = document.querySelector('[data-cottext]');
  let e = blk;
  while (e && getComputedStyle(e).overflowY !== 'auto' && getComputedStyle(e).overflowY !== 'scroll') e = e.parentElement;
  const box = e;
  const bx = box.getBoundingClientRect();
  // Fraction of an element's height inside the window, not a boolean. The
  // boolean version counted a one-pixel sliver as "in view", which is how a
  // 200px arm whose last 2px poked above the fold passed a check whose whole
  // subject is whether the reader can read it.
  const frac = k => { const e = blk.querySelector('[data-cotarm="'+k+'"]');
    if(!e) return 0;
    const r = e.getBoundingClientRect();
    const h = Math.max(1, r.height);
    return Math.max(0, Math.min(r.bottom, bx.bottom) - Math.max(r.top, bx.top)) / h; };
  const pre = blk.querySelector('[data-cotpre]');
  const pr = pre ? pre.getBoundingClientRect() : null;
  return { shadowF: frac('shadow'), primaryF: frac('primary'),
           preIn: !!pr && pr.top < bx.bottom && pr.bottom > bx.top,
           scrollTop: box.scrollTop,
           preTop: pr ? Math.round(pr.top - bx.top) : null };
})()`);
console.log(`  点击后 scrollTop=${jumped.scrollTop}，共同原文距顶 ${jumped.preTop}px，`
          + `干预臂可见 ${(jumped.primaryF*100).toFixed(0)}%，对照臂可见 ${(jumped.shadowF*100).toFixed(0)}%`);
chk(jumped.scrollTop > 0, '点击后内层窗口真的滚动了（不是点了没反应）');
// The block is ~1212px tall in a 300px window, so "the block is in view" is a
// weak and misleading target: the first version scrolled to the block's top,
// which put a heading and four numbers on screen and left the prose 400-700px
// further down. What has to land in view is the text itself.
chk(jumped.preIn,
    '跳转后「分岔前的共同原文」进入视野（跳的是正文，不是块的标题）',
    `preTop=${jumped.preTop} 窗口=${lay.clientH}`);
// Both arms, not one: the block exists to compare them, and a view that shows
// the steered arm in full and the unsteered one only as a sliver cannot.
chk(jumped.shadowF > 0.5,
    '跳转后对照臂正文有一半以上在视野内（不是只露出一条边）',
    `对照臂可见 ${(jumped.shadowF*100).toFixed(0)}%`);
chk(jumped.primaryF > 0.5,
    '跳转后干预臂正文有一半以上在视野内',
    `干预臂可见 ${(jumped.primaryF*100).toFixed(0)}%`);

// Back to the top, so the remaining checks read the same tree as the earlier ones.
await page.eval(`(()=>{let e=document.querySelector('[data-cottext]');
  while(e && getComputedStyle(e).overflowY!=='auto' && getComputedStyle(e).overflowY!=='scroll') e=e.parentElement;
  if(e) e.scrollTop = 0;})()`);
await sleep(400);

// The picker must be able to show which run is selected: a native select clips
// an option that does not fit, and a clipped label makes the control unreadable
// while still looking like a control.
const pick = await page.eval(`(()=>{const s=document.querySelector('[data-cotpick]');
  return {w: s.clientWidth, sw: s.scrollWidth, len: s.options[s.selectedIndex].text.length};})()`);
chk(pick.sw <= pick.w + 2,
    '下拉框能显示完整的选项文字（原生 select 不会把它裁掉）',
    `clientWidth=${pick.w} scrollWidth=${pick.sw} 选中的选项 ${pick.len} 字`);

console.log('\n===== 换一次运行 =====');
const other = steered.find(s => s.label !== best.label) || steered[steered.length - 1];
const otherIdx = steered.indexOf(other);
const after = await readShown(otherIdx);
chk(!!after && after !== block, '切换选择器后内容真的变了');
chk(has(after, `第 ${other.first_diverged_step} 步`),
    `新的一次显示它自己的步数（第 ${other.first_diverged_step} 步）`);
chk(has(after, cut(other.primary_head.after_primary)), '新的一次显示它自己的原文');
chk(has(after, other.label), '新的一次显示它自己的题号');
chk(!!after && !after.includes(cut(best.primary_head.after_primary)),
    '不再显示上一次的原文（没残留）');

// 选项数量必须等于非零强度运行数，否则有一批是选不到的。
const optCount = await page.eval(
  `document.querySelectorAll('[data-cotpick] option').length`);
chk(optCount === steered.length, '下拉框里每一次干预运行都能选到',
    `${optCount} / ${steered.length}`);

// ---- 截图留证 -------------------------------------------------------------
const shot = '.cache/cottext/shots/cottext.png';
await page.screenshot(shot, { fullPage: true });
console.log('\n截图:', shot);

await cdp.close(); proc.kill("SIGKILL");

console.log('\n' + '='.repeat(60));
if (fails.length) {
  console.log(`FAIL ${fails.length}/${checks.length + 18} 条：`);
  fails.forEach(f => console.log('  - ' + f));
  process.exit(1);
}
console.log('ALL PASS');
