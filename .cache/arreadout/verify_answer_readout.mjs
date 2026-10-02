// Does the answer-readout screen render, switch problems, and stay honest?
//
// The block ships two real essays per problem. What can go wrong without a
// crash: the hinge lands at the wrong column, both columns show the same arm,
// the shared head is not actually shared, the verdict badge contradicts the
// reference answer, or a click silently does nothing because the handler was
// bound before the elements existed.
import { launch, CDP, Page } from '../browser_verify/cdp_client.mjs';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';

const sleep = ms => new Promise(r => setTimeout(r, ms));
const fails = [];
const chk = (c, label, extra = '') => {
  console.log((c ? '  ok   ' : '  FAIL ') + label + (extra ? '   ' + extra : ''));
  if (!c) fails.push(label);
};

const bytes = readFileSync('frontend/public/latent/index.html');
console.log('index.html sha256:', createHash('sha256').update(bytes).digest('hex').slice(0, 16),
  `(${bytes.length} bytes)`);

// ---- the payload first: a screen that reads the wrong data is the failure
// mode that matters, and it is invisible in a screenshot.
const reg = await (await fetch('http://127.0.0.1:8917/latent/models.json')).json();
const big = reg.models.find(m => m.d_model === 2048);
const ar = await (await fetch(`http://127.0.0.1:8917/latent/${big.base}answer_readout.json`)).json();
const c32 = await (await fetch(`http://127.0.0.1:8917/latent/${big.base}cot_effect_32k.json`)).json();

console.log('\n===== 产物本身 =====');
chk(ar && Array.isArray(ar.items) && ar.items.length > 0, '产物带着若干道题的正文',
  `${ar.items ? ar.items.length : 0} 项`);
chk(ar.strength > 0 && ar.zero_strength === 0, '两个臂的强度写在产物里（页面不写死）',
  `${ar.zero_strength} vs ${ar.strength}`);
chk((ar.caveats || []).length >= 3, '限制条款随产物落盘，不只写在页面上',
  `${(ar.caveats || []).length} 条`);

// Every item must carry a real split, and the two arms must NOT be the same
// text. An item whose arms are identical would render two columns of one
// essay and call it a comparison.
ar.items.forEach(it => {
  const z = it.split.zero.text, s = it.split.steered.text;
  chk(it.split_char > 0 && it.split_char < Math.min(it.zero.chars, it.steered.chars),
      `${it.label} 分岔点在两篇之内`, `第 ${it.split_char} 字符 / ${it.zero.chars}·${it.steered.chars}`);
  chk(z !== s, `${it.label} 两臂的窗口不是同一段文字`);
  chk(it.heads.zero === it.heads.steered, `${it.label} 两遍的开头逐字相同（共有前缀是真的）`);
  // The head must stop AT the split. Shipping a fixed 180 characters while the
  // arms part at character 14 makes the page claim "the first 180 characters
  // are identical" above 180 characters that are not.
  chk(it.head_chars === Math.min(it.split_char, it.heads.zero.length),
      `${it.label} 共同开头截在分岔点上（没有多给）`,
      `head_chars=${it.head_chars} split=${it.split_char}`);
  chk(!!it.heads.zero.startsWith(it.heads.steered.slice(0, it.head_chars))
      || it.heads.zero === it.heads.steered,
      `${it.label} 共同开头确实是原文的前缀`);
  chk(it.zero.answer !== it.steered.answer, `${it.label} 两个答案确实不同`);
  chk(!!it.ref && !!it.verdict, `${it.label} 带标准答案与判定`, `${it.ref} ${it.verdict}`);
  chk(it.zero.steps > 0 && it.steered.steps > 0, `${it.label} 两臂步数都是实测值`,
    `${it.zero.steps} / ${it.steered.steps}`);
  // The hinge must fall inside the window the page will slice. If the window
  // start moved past the split, the page's pre/post split puts everything in
  // the "before" column and the hinge silently disappears.
  [it.split.zero, it.split.steered].forEach(w => {
    chk(w.start <= it.split_char && it.split_char < w.start + w.text.length,
        `${it.label} 分岔点落在窗口内`, `start=${w.start} len=${w.text.length} split=${it.split_char}`);
  });
});
// The screen must not ship more problems than it says it does.
const sel = ar.selection || {};
chk(sel.n_shipped === ar.items.length, '声明的条数与实际条数一致',
  `${sel.n_shipped} vs ${ar.items.length}`);

// ---- the page ------------------------------------------------------------
const { proc, version } = await launch({
  port: 9373, userDataDir: '/Users/zhourui/code/steer3d/.cache/arreadout/profile',
  url: 'about:blank',
});
console.log('\nchromium:', version.Browser);
const cdp = await CDP.connect(
  `ws://127.0.0.1:9373/devtools/browser/${version.webSocketDebuggerUrl.split('/').pop()}`);
const page = await Page.create(cdp);
await page.send('Network.enable');
await page.send('Network.setCacheDisabled', { cacheDisabled: true });
await page.send('Emulation.setDeviceMetricsOverride',
  { width: 1600, height: 1100, deviceScaleFactor: 1, mobile: false });
const exceptions = [];
cdp.on(m => { if (m.method === 'Runtime.exceptionThrown')
  exceptions.push(m.params.exceptionDetails?.exception?.description
                  || m.params.exceptionDetails?.text || 'unknown'); });

// Same entry path the other verifiers use: dismiss the orientation gate, then
// open the tab the CoT panel hangs off. The panel is empty until a trajectory
// is selected, and an empty panel makes every check below pass for the wrong
// reason.
await page.send('Page.navigate',
  { url: `http://127.0.0.1:8917/latent/index.html?orient=reset&m=${big.id}` });
await page.waitForEvent('Page.loadEventFired', 40000);
await sleep(900);
if (await page.eval(`(()=>{const o=document.getElementById('orientation');
  return !!(o && getComputedStyle(o).display!=='none')})()`)) {
  await page.click('#orientClose'); await sleep(800);
}
await page.click('#tabDelta'); await sleep(2800);

const T = await page.eval(() => (document.body.innerText || ''));
const root = await page.eval(() => {
  const e = document.querySelector('[data-aroot]');
  if (!e) return null;
  const r = e.getBoundingClientRect();
  return { w: Math.round(r.width), h: Math.round(r.height), text: e.innerText };
});

console.log('\n===== 页面上 =====');
chk(!!root, '答案位移正文屏渲染出来了', root ? `${root.w}x${root.h}` : '找不到 [data-aroot]');
chk(root && root.h > 200, '这一块有实际内容（不是空壳）', root ? `${root.h}px` : '');
chk(/逐篇读|两篇文章并排/.test(T), '顶部有跳转入口');
chk(/没有采样/.test(T) && /argmax/.test(T), '明说解码是贪心、没有采样');
chk(/逐字相同/.test(T), '明说两遍开头逐字相同');

const chips = await page.eval(() =>
  [...document.querySelectorAll('[data-arpick]')].map(b => b.dataset.arpick));
chk(chips.length === ar.items.length, '题号按钮数量与产物一致',
  `${chips.length} vs ${ar.items.length}`);

const it0 = ar.items[0];

// Both arms must be on screen, with different text. Two cards showing the
// same string is the failure this screen exists to rule out.
const cols = await page.eval(`(()=>{
  const g = k => { const e=document.querySelector('[data-armtext="'+k+'"]');
                   return e ? e.textContent : null; };
  return { post: [g('post:zero'), g('post:steered')],
           tail: [g('tail:zero'), g('tail:steered')] };
})()`);
chk(!!cols.post[0] && cols.post[0].length > 0 && cols.post[1].length > 0,
    '分岔之后两臂都渲染了非空文本',
    `${cols.post[0] ? cols.post[0].length : 0} / ${cols.post[1] ? cols.post[1].length : 0} 字符`);
chk(!!cols.post[0] && cols.post[0] !== cols.post[1],
    '分岔之后两臂内容不同');
// The rendered text carries the excerpt markers ("…上文略…", "…下文略…"),
// so the on-screen length is the window plus the marker, not the window. Strip
// them before comparing, or this check measures the marker.
const strip = t => (t || '').replace(/…上文略…/g, '').replace(/…下文略，原文还有 \d+ 字符…/g, '').trim();
chk(!!cols.tail[0] && cols.tail[1]
    && strip(cols.tail[0]) === (it0.landing.zero || '').trim()
    && strip(cols.tail[1]) === (it0.landing.steered || '').trim(),
    '两臂结尾的原文与产物一致（剥掉截断标记之后）',
    `${strip(cols.tail[0] || '').length} / ${strip(cols.tail[1] || '').length} 字符`);
// And the markers must actually be there when the window really is an excerpt.
// A window that silently stops mid-sentence is indistinguishable from a model
// that stopped writing, and the first version of this block rendered exactly
// that: "Now, since m and n are positive i" with no indication it was cut.
chk(!!cols.post[0] && /…下文略，原文还有 \d+ 字符…/.test(cols.post[0])
    && /…下文略，原文还有 \d+ 字符…/.test(cols.post[1]),
    '截断的窗口标出了「下文还有多少」',
    (cols.post[0] || '').match(/…下文略[^\n]*/)?.[0] || '');
chk(!!cols.tail[0] && /…上文略…/.test(cols.tail[0]),
    '从中间开始的窗口标出了「上文略」（否则像 LaTeX 命令被劈开）');
// The split text on screen must start at the split, not at the window start:
// the hinge is what turns two blobs into a comparison.
const it0split = it0.split.zero;
chk(!!cols.post[0] && strip(cols.post[0]) === it0split.text.slice(it0.split_char - it0split.start).trim(),
    '页面上的分岔后文本正好从分岔点开始（铰链没偏）');

// A stacked layout, not two 143px columns. At 11px a 143px column is about
// four Chinese characters per line: every text check below passes on it and
// it is unreadable. This block lives in the page's 320px right-hand column
// (.wrap is `300px 1fr 320px`), so each arm gets the full width.
const widths = await page.eval(`(()=>{
  const e=document.querySelector('[data-aroot]');
  const block=e.getBoundingClientRect().width;
  const arms=[...e.querySelectorAll('[data-armtext]')].map(x=>
    Math.round(x.getBoundingClientRect().width));
  return {block: Math.round(block), arms};
})()`);
chk(widths.block <= 340, '这一块确实处在 320px 侧栏里（宽度前提成立）', `${widths.block}px`);
chk(widths.arms.length >= 4 && widths.arms.every(w => w > widths.block * 0.85),
    '每臂占满整块宽度，没有被切成两半', widths.arms.join(' / ') + ` (块宽 ${widths.block})`);

// The head the page shows must be the payload's head, and the payload's two
// heads are byte-identical by construction.
const head = await page.eval(() => {
  const e = document.querySelector('[data-arhead]');
  return e ? e.textContent : null;
});
chk(!!head && head.replace(/\s+$/, '') === String(it0.heads.zero).replace(/\s+$/, ''),
    '页面上那段共同原文就是产物里的那段', head ? `${head.length} 字符` : '');

// A click must actually change the screen. A handler bound before the
// elements existed is silent, and every other check here would still pass.
if (chips.length > 1) {
  // page.eval's second parameter is an OPTIONS object, not a function
  // argument -- passing the key there made the selector read
  // `[data-armtext="undefined"]`, so both reads came back null and the check
  // reported "the text did not change" about two missing elements.
  const armTxt = k => page.eval(
    `document.querySelector('[data-armtext="${k}"]')?.textContent ?? null`);
  const before = await armTxt('post:zero');
  const headBefore = await page.eval(() => {
    const e = document.querySelector('[data-arhead]');
    return e ? e.textContent : null;
  });
  await page.eval(() => {
    const b = document.querySelectorAll('[data-arpick]')[1];
    if (b) b.click();
  });
  await sleep(700);
  const after = await armTxt('post:zero');
  const headAfter = await page.eval(() => {
    const e = document.querySelector('[data-arhead]');
    return e ? e.textContent : null;
  });
  chk(!!after && after !== before, '点第二个题号，正文真的换了',
    before && after ? `${String(before).slice(0, 24)} -> ${String(after).slice(0, 24)}` : '');
  chk(headAfter !== headBefore, '点第二个题号，共同开头也换了');
  // The chip row renders all eight labels, so "the block's text mentions
  // 1984_I_1" is true before any click at all. Two checks written that way
  // were passing for the wrong reason. Compare against the payload's own
  // per-item numbers, which appear exactly once and only for the item shown.
  const shown = await page.eval(() => {
    const e = document.querySelector('[data-arm="post:zero"]');
    return e ? e.innerText : null;
  });
  chk(!!shown && shown.includes(`写了 ${ar.items[1].zero.steps} 步`)
      && shown.includes(String(ar.items[1].zero.answer)),
      '换题后卡片上写的是新那一题自己的步数与答案',
      `期望 ${ar.items[1].zero.steps} 步 / ${ar.items[1].zero.answer}`);
  chk(!!shown && !shown.includes(`写了 ${ar.items[0].zero.steps} 步`),
      '旧那一题的步数不再出现在卡片上',
      `旧题 ${ar.items[0].zero.steps} 步`);
}

// The block is over 3000px tall inside a 300px scroll window, so the payoff --
// where the two essays actually write the answer -- is far below the fold. The
// in-block jump has to move the inner box, and it has to actually land on the
// tail rather than on the block's own top.
const jumpRes = await page.eval(`(()=>{
  const b=document.querySelector('[data-arto="tail"]');
  if(!b) return {err:'no button'};
  let sc=null,n=b; while(n&&n!==document.body){const o=getComputedStyle(n);
    if(o.overflowY==='auto'||o.overflowY==='scroll'){sc=n;break;} n=n.parentElement;}
  if(!sc) return {err:'no scroll box'};
  const tail=document.querySelector('[data-arm="tail:zero"]');
  const beforeTop=tail.getBoundingClientRect().top;
  const beforeScroll=sc.scrollTop;
  b.click();
  // Where the tail ended up RELATIVE TO THE BOX, not how far it moved. The
  // first version of this check asserted on the movement (4821px) and called
  // it a failure while the jump had in fact landed the tail at the top of the
  // window -- a correct jump measured by the wrong quantity.
  const boxTop=sc.getBoundingClientRect().top;
  const afterRel=tail.getBoundingClientRect().top - boxTop;
  return {moved: sc.scrollTop>beforeScroll, afterRel: Math.round(afterRel),
          beforeTop: Math.round(beforeTop), beforeScroll,
          afterScroll: sc.scrollTop, winH: sc.clientHeight,
          maxScroll: sc.scrollHeight - sc.clientHeight};
})()`);
chk(jumpRes && jumpRes.moved, '块内「跳到结尾」真的滚动了内层滚动框',
  jumpRes ? `scrollTop ${jumpRes.beforeScroll} -> ${jumpRes.afterScroll}` : '');
chk(jumpRes && jumpRes.afterRel >= 0 && jumpRes.afterRel < jumpRes.winH,
    '跳过去之后结尾落在窗口内（不是跳了个寂寞）',
  jumpRes ? `结尾距窗口顶 ${jumpRes.afterRel}px / 窗口 ${jumpRes.winH}px` : '');

// The three caveats must be next to the text, not in a footnote elsewhere.
chk(/字符位置/.test(T) && /不是 token 步数/.test(T), '限制一：字符位置 ≠ token 步数');
chk(/不是 token 同步/.test(T), '限制二：两臂不是 token 同步的');
chk(/答案变了不等于变好了/.test(T), '限制三：变了不等于变好了');
chk(/净变化是 0/.test(T), '正文旁边写出这批的净变化');
chk(/只做示意/.test(T), '明说文本只是示意，数字才来自实测');

// Nothing on this screen may claim the intervention improved the model -- but
// the phrase also appears inside the panel's own retraction ("不能支持「向量
// 让模型答得更准或更不准」"), and a bare `match()` flags that too. So each
// occurrence has to be checked for a negation in front of it, rather than the
// whole string being banned. Banning the literal would have pushed the fix
// into deleting the retraction, which is the sentence doing the most work.
const OVER = /让模型答得更准|提高了准确率|提升了正确率/g;
const NEG = /不能|不支持|无法|不足以|并非|不等于/;
const bare = [];
for (const m of T.matchAll(OVER)) {
  const before = T.slice(Math.max(0, m.index - 24), m.index);
  if (!NEG.test(before)) bare.push(T.slice(m.index, m.index + 12));
}
chk(bare.length === 0, '「更准」这类断言若出现必须在否定句里', bare.join(' | '));
chk(/不能支持/.test(T), '并且那句否定的说法确实在页面上（不是靠删掉断言过关）');

chk(exceptions.length === 0, '无未捕获异常', exceptions.join(' | '));

console.log('\n---------------------------------------');
console.log(fails.length ? `失败 ${fails.length} 条` : 'ALL PASS');
process.exit(fails.length ? 1 : 0);
