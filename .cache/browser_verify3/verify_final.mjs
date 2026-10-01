// Final-hash re-verification of the last three UI fixes.
//
// The earlier pass (report.md) endorsed hash 225487af and separately confirmed
// the #layerStory fix on 15b5b5b6. Three fixes landed after both:
//   commit 2373fb6 — pointer names an existing layer; unsteered panel hidden in
//                    screen 4; #pairRow label no longer wraps one glyph per line
// plus the dimension rows moved to flex in d435305.
//
// This script re-runs only what those touches could have broken, against the
// hash that actually ships, and says so in its output. It deliberately does not
// re-run the full 10-item sweep: that is already recorded, and a re-run that
// gets reported as "10/10 again" would blur which version it speaks for.

import { launch, CDP, Page } from '../browser_verify/cdp_client.mjs';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { createHash } from 'node:crypto';

const URL = 'http://localhost:8917/latent/index.html';
const OUT = '.cache/browser_verify3/shots';
const sleep = ms => new Promise(r => setTimeout(r, ms));
mkdirSync(OUT, { recursive: true });

const indexBytes = readFileSync('frontend/public/latent/index.html');
const HASH = createHash('sha256').update(indexBytes).digest('hex');
console.log('index.html sha256:', HASH.slice(0, 16), `(${indexBytes.length} bytes)`);

const fails = [];
const say = (...a) => console.log(a.join(' '));
const chk = (c, label, extra = '') => {
  if (c) say('  ok   ' + label + (extra ? '   ' + extra : ''));
  else { say('  FAIL ' + label + (extra ? '   ' + extra : '')); fails.push(label); }
};

const { proc, version } = await launch({
  port: 9350,
  userDataDir: '/Users/zhourui/code/steer3d/.cache/browser_verify3/profile_final',
  url: 'about:blank',
});
say('chromium:', version.Browser, 'port 9350');
const cdp = await CDP.connect(`ws://127.0.0.1:9350/devtools/browser/${version.webSocketDebuggerUrl.split('/').pop()}`);
const page = await Page.create(cdp);
const exceptions = [];
cdp.on(m => {
  if (m.method === 'Runtime.exceptionThrown') {
    exceptions.push(m.params.exceptionDetails?.exception?.description
                    || m.params.exceptionDetails?.text || 'unknown');
  }
});

await page.nav(URL);
await sleep(4500);

// The orientation layer is a fixed full-screen overlay, so every click below
// used to land on it instead of the app. Navigating with ?orient=off would
// hide the problem; going through the real path (a first-time visitor clicks
// "我读完了") both fixes the harness and checks the thing that actually
// matters -- that closing the guide hands the page back fully interactive.
const orient = await page.eval(`(()=>{const o=document.getElementById('orientation');
  if(!o) return {present:false};
  return {present:true, blocking: getComputedStyle(o).display !== 'none'};})()`);
chk(orient.present, '首次访问弹出导读层');
chk(orient.blocking, '导读层默认挡住页面（会拦截点击）');
if (orient.blocking) { await page.click('#orientClose'); await sleep(700); }
const afterClose = await page.eval(`(()=>{const o=document.getElementById('orientation');
  return {hidden: getComputedStyle(o).display === 'none',
          topEl: (document.elementFromPoint(innerWidth/2, innerHeight/2)||{}).id || ''};})()`);
chk(afterClose.hidden, '点「我读完了」后导读层消失');
chk(!/^orientation$/.test(afterClose.topEl), '关闭后页面中心不再被浮层占据',
    'elementFromPoint=' + afterClose.topEl);

// Enter screen 4 by clicking the real tab, coordinates read from the page.
await page.click('#tabDelta');
await sleep(2500);
const ready = await page.eval(`(()=>{const S=window.__latentState||null; return {
  view: document.querySelector('#tabDelta') ? 'ok' : 'no-tab',
  mainTitle: document.querySelector('#mainTitle')?.textContent,
  sub: document.querySelector('#mainSub')?.textContent,
  selLayer: document.querySelector('#valLayer')?.textContent,
  pairOpts: [...document.querySelectorAll('#selPair option')].map(o=>o.textContent),
};})()`);
say('\n[enter] ' + ready.mainTitle);
chk(/L26/.test(ready.mainTitle || ''), '默认层是 L26（注入点之上第一层）', ready.mainTitle);
chk((ready.pairOpts || []).length === 6, `下拉列出 6 个配对`, (ready.pairOpts || []).length + '');

// ---- Fix 1: the pointer must name a layer that exists --------------------
const avail = JSON.parse(readFileSync('frontend/public/latent/data/pairs/pairs.json', 'utf8'))
  .pairs[0].layers;
const injected = JSON.parse(readFileSync('frontend/public/latent/data/pairs/pairs.json', 'utf8'))
  .pairs[0].inject_layer;
say('\n[fix 1] 注入块指路（可用层 ' + avail.join('/') + '，注入点 L' + injected + '）');

await page.eval(`(()=>{const S=window.__latent; return 0;})()`).catch(() => {});
await page.click('#rngLayer', { dx: 0, dy: 0 }).catch(() => {});

// Move the layer slider with a real drag to the injection layer.
const dragTo = async (target) => {
  const info = await page.eval(`(()=>{const e=document.querySelector('#rngLayer');
    const r=e.getBoundingClientRect(); return {min:+e.min,max:+e.max,w:r.width,h:r.height,
      top:r.top,left:r.left,val:+e.value,thumb:15};})()`);
  const xFor = v => info.left + info.thumb/2 + (v-info.min)/(info.max-info.min)*(info.w-info.thumb);
  const y = info.top + info.h/2;
  await page.mouse('mouseMoved', xFor(info.val), y, { buttons: 0 });
  await page.mouse('mousePressed', xFor(info.val), y);
  for (let i = 1; i <= 6; i++) {
    const v = info.val + (target - info.val) * (i/6);
    await page.mouse('mouseMoved', xFor(v), y);
    await sleep(30);
  }
  await page.mouse('mouseReleased', xFor(target), y);
  await sleep(600);
};
await dragTo(injected);

const inj = await page.eval(`(()=>{
  const side = document.querySelector('#tblTop')?.innerHTML || '';
  const sub  = document.querySelector('#mainSub')?.textContent || '';
  const flat = side.replace(/<[^>]+>/g,' ').replace(/\\s+/g,' ').trim();
  // Full text for assertions, a short head for the human-readable line. These
  // used to be the same string, and the 400-char slice quietly became a
  // correctness constraint the moment the page grew: a sentence that moved
  // past character 400 read as "the page does not say it", which is the one
  // conclusion a growing page must never produce.
  return { sideText: flat, sideHead: flat.slice(0,400),
           sub, layer: document.querySelector('#valLayer')?.textContent,
           pushed: (side.match(/被推了<\\/td><td class="tok"><b[^>]*>([\\d.]+)%/)||[])[1] || null };
})()`);
say('  侧栏: ' + inj.sideHead);
const layersNamed = [...(inj.sideText + ' ' + inj.sub).matchAll(/L(\d+)/g)].map(m => +m[1]);
const bogus = layersNamed.filter(L => !avail.includes(L));
chk(bogus.length === 0, '注入块的指路指向真实存在的层',
    bogus.length ? '指向了 L' + bogus.join(',L') : '提到 ' + [...new Set(layersNamed)].join('/'));
chk(!/L21/.test(inj.sideText + inj.sub), '不再出现不存在的 L21');
chk(inj.pushed === '0.00' || inj.pushed === '0.0' || inj.pushed === '0',
    '注入块读数仍精确为 0%', inj.pushed);
chk(/没有任何维度被推动/.test(inj.sideText), '注入块明说没有维度被推动');

// ---- Fix 2: only one problem visible in screen 4 -------------------------
say('\n[fix 2] 第 4 屏不该同时摆两道题');
const twoProbs = await page.eval(`(()=>{
  const tp = document.querySelector('#trajPanel');
  const pp = document.querySelector('#pairRow');
  return { trajPanelDisplay: tp ? getComputedStyle(tp).display : 'missing',
           trajVisible: tp ? tp.getBoundingClientRect().height > 0 : false,
           pairVisible: pp ? pp.getBoundingClientRect().height > 0 : false,
           selPair: document.querySelector('#selPair')?.value,
           selPairText: document.querySelector('#selPair')?.selectedOptions?.[0]?.textContent };
})()`);
chk(twoProbs.trajPanelDisplay === 'none' || !twoProbs.trajVisible,
    '无干预的「题目」面板在第 4 屏已隐藏', 'display=' + twoProbs.trajPanelDisplay);
chk(twoProbs.pairVisible, '配对面板可见', twoProbs.selPairText || '');

// And it must come back on the other screens.
await page.click('#tabXY');
await sleep(1200);
const backOnXY = await page.eval(`(()=>{const tp=document.querySelector('#trajPanel');
  return {display: tp?getComputedStyle(tp).display:'missing',
          visible: tp?tp.getBoundingClientRect().height>0:false,
          opts: document.querySelector('#selTraj')?.options?.length||0};})()`);
chk(backOnXY.visible && backOnXY.opts > 0,
    '切回「隐空间 2D」后无干预题目面板恢复且可选',
    `display=${backOnXY.display} 可选 ${backOnXY.opts} 项`);
await page.click('#tabDelta');
await sleep(1200);

// ---- Fix 3: label no longer one glyph per line ---------------------------
say('\n[fix 3] 「配对题目」标签不应竖排');
const label = await page.eval(`(()=>{const l=document.querySelector('#pairRow label');
  if(!l) return null; const r=l.getBoundingClientRect();
  const cs=getComputedStyle(l);
  return {text:l.textContent.trim(), w:r.width, h:r.height,
          sameRow: (()=>{const s=document.querySelector('#selPair');
            if(!s) return null; const sr=s.getBoundingClientRect();
            return Math.abs(sr.top - r.top) < sr.height*0.6;})()};})()`);
chk(label && label.text === '配对题目', '标签文本完整', label && label.text);
chk(label && label.h < 34, '标签高度 < 34px（不是每字一行）',
    label ? `${label.w.toFixed(0)}×${label.h.toFixed(0)}px` : 'null');
chk(label && label.sameRow, '标签与下拉框同一行');

// ---- Regression spot-checks ----------------------------------------------
say('\n[回归抽查]');
await dragTo(26);
const l26 = await page.eval(`(()=>{const side=document.querySelector('#tblTop')?.innerHTML||'';
  return {pushed:(side.match(/被推了<\\/td><td class="tok"><b[^>]*>([\\d.]+)%/)||[])[1]||null,
          dimrows:document.querySelectorAll('.dimrow').length,
          names:[...document.querySelectorAll('.dimname')].map(e=>e.textContent.trim()),
          bars:[...document.querySelectorAll('.dimbar > i')].map(e=>parseFloat(e.style.width)),
          story:document.querySelector('#layerStory')?.textContent?.trim().slice(0,80)};})()`);
chk(l26.dimrows === 10, 'L26 有 10 行维度', l26.dimrows + ' 行');
chk(l26.bars.every(w => w >= 0 && w <= 100), '条宽全部落在 0–100%',
    l26.bars.length ? Math.min(...l26.bars).toFixed(1) + '–' + Math.max(...l26.bars).toFixed(1) + '%' : '');
chk(new Set(l26.bars.map(b => b.toFixed(0))).size > 1, '条长有区分',
    [...new Set(l26.bars.map(b => b.toFixed(0)))].join(','));
chk(l26.names.every(n => n.length >= 4), '词名不是 1–2 字符残片',
    l26.names.slice(0, 3).map(n => n.slice(0, 18)).join(' / '));
chk(!/L(?!26)\d/.test(l26.story || '') && /不适用|配对/.test(l26.story || ''),
    '「这一层在做什么」跟随当前层', l26.story);

// Out-of-range token slider must still refuse to show a per-step number.
const tokInfo = await page.dragRange('#rngTok', 0, 30);
const oor = await page.eval(`(()=>{const side=document.querySelector('#tblTop')?.innerHTML||'';
  return {text: side.replace(/<[^>]+>/g,' ').replace(/\\s+/g,' ').trim().slice(0,260),
          hasPct: /被推了<\\/td><td class="tok"><b/.test(side)};})()`);
chk(/无对照可比/.test(oor.text), '越界时说明没有可比的对照', oor.text.slice(0, 90));
chk(oor.hasPct === false, '越界时不显示该步的百分数');

// ---- The divergence row: does it show THIS pair's tokens? ----------------
// The bug this catches is not hypothetical: the id arrays used to be fetched
// for the first pair only, so every other problem displayed problem 1's
// tokens under its own title. Check pair 5 specifically, and compare against
// the shipped .bin files rather than against the page's own claims.
{
  const truth = await page.eval(`(async () => {
    const mf = await (await fetch('data/pairs/pairs.json')).json();
    const V = (await (await fetch('data/vocab.json')).json()).ids;
    const read = async (f) => new Int32Array(await (await fetch('data/pairs/'+f)).arrayBuffer());
    const out = [];
    for (const p of mf.pairs) {
      const c = await read(p.arms._ids.control.file);
      const s = await read(p.arms._ids.steered.file);
      const k = p.n_common_prefix;
      out.push({ id: p.id, k,
        ctl: (V[c[k]] ?? '#'+c[k]).trim(), ste: (V[s[k]] ?? '#'+s[k]).trim() });
    }
    return out;
  })()`);
  const rowsSeen = [];
  const opts = await page.eval(`document.querySelector('#selPair').options.length`);
  for (let i = 0; i < opts; i++) {
    await page.eval(`(()=>{const s=document.querySelector('#selPair');
      s.value='${i}';
      s.dispatchEvent(new Event('change'));
      return 0;})()`);
    await sleep(900);
    const r = await page.eval(`(()=>{const h=document.querySelector('#tblTop').innerHTML;
      const a=h.indexOf('分叉点');
      if(a<0) return {anchor:false};
      const t=h.slice(a);
      const g=(l)=>{const m=t.match(new RegExp('<td class="n"[^>]*>'+l+'<\\/td>[\\s\\S]*?<td class="tok"[^>]*>([^<]*)<'));
        return m?m[1].trim():null;};
      // 用 [0-9] 而不是 \\d：本文件把 eval 代码写在 Node 模板字符串里，
      // 单反斜杠 \\d 会被模板字面量吃成字面字母 d，正则就永远不匹配。
      return {anchor:true, step:(t.match(/分叉点：第 ([0-9]+) 步/)||[])[1]||null,
              ctl:g('对照'), ste:g('干预'),
              title:document.querySelector('#selPair').selectedOptions[0].textContent.trim()};})()`);
    rowsSeen.push({ i, ...r });
  }
  const bad = [];
  truth.forEach((t, i) => {
    const seen = rowsSeen[i];
    if (!seen || !seen.anchor) { bad.push(`${t.id}: 没有分叉点区块`); return; }
    if (String(t.k) !== String(seen.step)) bad.push(`${t.id}: 步号 ${seen.step} != ${t.k}`);
    if (t.ctl !== seen.ctl || t.ste !== seen.ste)
      bad.push(`${t.id}: 页面 ${seen.ctl}/${seen.ste} != 数据 ${t.ctl}/${t.ste}`);
  });
  chk(bad.length === 0, '逐题分叉点与 id 文件一致（没有串题）',
      bad.length ? bad.slice(0, 3).join('; ')
                 : truth.map(t => `${t.id}@${t.k} ${t.ctl}→${t.ste}`).join('  '));
  await page.eval(`(()=>{const s=document.querySelector('#selPair');
    s.value='4'; s.dispatchEvent(new Event('change')); return 0;})()`);
  await sleep(900);
  const txt = await page.eval(`(()=>{const e=document.querySelector('#genTxt');
    return {hasC:/对照/.test(e.innerHTML), hasS:/干预/.test(e.innerHTML),
            head:/共同部分/.test(e.innerHTML)};})()`);
  chk(txt.hasC && txt.hasS && txt.head, '「生成的文本」显示两臂对照',
      `共同部分=${txt.head} 对照=${txt.hasC} 干预=${txt.hasS}`);
  await page.screenshot(`${OUT}/final-04-divergence-pair5.png`);
  say('  shot -> final-04-divergence-pair5.png');
}

// ---- Finding 13/14: the page must not assert a causal link the data refutes ----
// Three sentences were removed because measurement contradicted them. Checking
// that a string is *absent* is the only assertion that can catch a re-introduced
// claim, and checking that the replacement number is *present* is what stops the
// caveat being quietly dropped in a later edit.
{
  say('\n[Finding 13/14] 页面不得断言数据不支持的因果');
  await page.click('#tabDelta');
  await sleep(1000);
  // Scope: the whole side panel, not just #tblTop. The note under the table is
  // a *sibling* of the scroll container, so a check reading only the table's
  // innerHTML could not see it — and would have reported "the caveat is
  // missing" for text that is on screen.
  const notes = await page.eval(`(()=>{
    const t0=document.querySelector('#tblTop');
    const panel=t0.parentElement.parentElement;
    const t=panel.innerHTML;
    return {hasResult:/换词是位移的结果/.test(t),
            hasGraphIsCause:/上面的图是原因/.test(t),
            hasRandomNull:/16%/.test(t),
            ctxPointer:/理由见本面板下方/.test(t),
            dupCount:(t.match(/干预关系不大/g)||[]).length,
            saysNotResult:/换词.{0,4}不是.{0,4}位移的结果/.test(t),
            hasDimsCaveat:/这些维度不解释 token 的选择/.test(t),
            hasCancel:/0\.0%[–-]20\.7%/.test(t),
            oldFooter:/干预向量就是要把这些分数重新排序/.test(t),
            newFooter:/这张表不解释/.test(t),
            tail:[...document.querySelectorAll('td.note')]
                  .filter(e=>/这些维度不解释/.test(e.innerHTML))
                  .map(e=>e.innerHTML.length + ' >>> ' + e.innerHTML)};})()`);
  chk(!notes.hasResult, '不再说「换词是位移的结果」', String(notes.hasResult));
  chk(!notes.hasGraphIsCause, '不再说「上面的图是原因」', String(notes.hasGraphIsCause));
  chk(notes.saysNotResult, '明确写出「换词不是位移的结果」');
  chk(notes.hasRandomNull, '给出同范数随机方向 16% 这个零假设');
  chk(notes.ctxPointer, '分叉点处留一行指路，而不是重复整段');
  chk(notes.dupCount === 1, '完整警告只出现一次（上下文处不重复）',
      `出现 ${notes.dupCount} 次`);
  chk(notes.hasDimsCaveat, '维度区写明这些维度不解释 token 的选择');
  chk(!notes.oldFooter, '删掉「干预向量就是要把这些分数重新排序」（Finding 14 已否掉）',
      String(notes.oldFooter));
  chk(notes.newFooter, '表下说明改成「这张表不解释为什么是这个 token」');
  chk(notes.hasCancel, '维度区给出净效果/总运动 0.0%–20.7% 的抵消比例');
  for (const t of [].concat(notes.tail)) say('  维度警告: ' + String(t));
  {
    // Is the tail line being covered by the dimension rows, or merely cut?
    // Measure the geometry rather than guess from the pixels.
    const geo = await page.eval(`(()=>{
      const td = [...document.querySelectorAll('td.note')]
        .find(e=>/这些维度不解释/.test(e.innerHTML));
      const first = td.parentElement.parentElement.nextElementSibling;
      const rows = [...document.querySelectorAll('.dimrow')];
      const tb = td.getBoundingClientRect();
      const sc = td.closest('div[style*="overflow"]');
      const sb = sc.getBoundingClientRect();
      const t = document.querySelector('#tblTop');
      return { tdH: Math.round(tb.height), tdBottom: Math.round(tb.bottom),
               tdTop: Math.round(tb.top), tdW: Math.round(tb.width),
               tableW: Math.round(t.getBoundingClientRect().width),
               panelW: Math.round(sb.width),
               panelScrollW: sc.scrollWidth, panelClientW: sc.clientWidth,
               overflowX: getComputedStyle(sc).overflowX,
               firstRowTop: rows.length ? Math.round(rows[0].getBoundingClientRect().top) : null,
               panelBottom: Math.round(sb.bottom),
               nRows: rows.length };})()`);
    say('  几何: ' + JSON.stringify(geo));
    // Who is the 332px-wide element? 38px of horizontal overflow in a 294px
    // panel, with the table itself now at 294, so it is something else.
    const wide = await page.eval(`(()=>{const sc=document.querySelector('#tblTop').parentElement;
      const lim=sc.getBoundingClientRect().right;
      return [...sc.querySelectorAll('*')]
        .map(e=>({t:e.tagName+'.'+(e.className||''), r:Math.round(e.getBoundingClientRect().width),
                  over:Math.round(e.getBoundingClientRect().right-lim), w:e.innerText?.slice(0,18)}))
        .filter(o=>o.over>2).slice(0,6);})()`);
    for (const w of [].concat(wide))
      say('    溢出: ' + JSON.stringify(w));
    chk([].concat(wide).length === 0, '侧栏里没有元素越出面板右缘',
        [].concat(wide).map(w => `${w.t} 超出 ${w.over}px «${w.w}»`).join('; ') || '无');
    // Screen 1 shares #tblTop, and table-layout:fixed is not scoped to screen 4.
    await page.click('#tabBar');
    await sleep(1200);
    const s1 = await page.eval(`(()=>{const sc=document.querySelector('#tblTop').parentElement;
      const rows=document.querySelectorAll('#tblTop tr').length;
      const cells=[...document.querySelectorAll('#tblTop td')].map(e=>Math.round(e.getBoundingClientRect().width));
      return {rows, tblW:Math.round(document.querySelector('#tblTop').getBoundingClientRect().width),
              panelW:sc.clientWidth, scrollW:sc.scrollWidth,
              minCell:Math.min(...cells), maxCell:Math.max(...cells)};})()`);
    say('  第1屏候选词: ' + JSON.stringify(s1));
    await page.screenshot(`${OUT}/final-06-screen1-fixed.png`);
    say('  shot -> final-06-screen1-fixed.png');
    await page.click('#tabDelta');
    await sleep(1000);
    // Crop the caveat at 3x so the last line can actually be read. The full-page
    // shot is 1600px wide; 199 characters of Chinese in a 294px column is
    // simply not legible there, and "looks truncated" was my first reading of a
    // perfectly complete element.
    const box = await page.eval(`(()=>{const td=[...document.querySelectorAll('td.note')]
        .find(e=>/这些维度不解释/.test(e.innerHTML));
      const r = td.getBoundingClientRect();
      return {x:Math.round(r.left)-6, y:Math.round(r.top)-6,
              width:Math.round(r.width)+12, height:Math.round(r.height)+12};})()`);
    await page.screenshot(`${OUT}/final-05-dim-caveat.png`, { clip: {...box, scale: 3} });
    say('  shot -> final-05-dim-caveat.png');
  }

  await page.click('#tabXY');
  await sleep(1200);
  const story = await page.eval(`(()=>{const s=document.querySelector('#layerStory').innerHTML;
    return {hasCompress:/压到少数几个方向/.test(s),
            hasZeroOut:/其余清零/.test(s),
            hasSeparable:/几乎完全线性可分/.test(s),
            saysShape:/二维投影的形状统计/.test(s),
            saysNotDims:/不告诉你信息被压进了多少维/.test(s)};})()`);
  chk(!story.hasCompress, '层解说不再说「压到少数几个方向」', String(story.hasCompress));
  chk(!story.hasZeroOut, '层解说不再说「其余清零」', String(story.hasZeroOut));
  chk(!story.hasSeparable, '层解说不再从 2D 散点断言「线性可分」', String(story.hasSeparable));
  chk(story.saysShape, '层解说点明这是二维投影的形状统计');
  chk(story.saysNotDims, '层解说声明它不回答维度压缩问题');

  // A caveat that is present in the DOM but cut off below the fold has not
  // been delivered. Every string assertion above passed while the sidebar was
  // visibly truncating both caveats mid-sentence, so measure the layout too.
  const fit = await page.eval(`(()=>{
    const out = [];
    const tb = document.querySelector('#tblTop');
    const sc = tb?.parentElement;
    if (sc) out.push(['第4屏侧栏', sc.scrollHeight, sc.clientHeight,
                      sc.scrollWidth, sc.clientWidth]);
    out.push(['#tblTop 宽', 0, 0, tb.getBoundingClientRect().width,
              sc?.clientWidth || 0]);
    for (const id of ['#layerStory']) {
      const e = document.querySelector(id);
      if (e) out.push([id, e.scrollHeight, e.clientHeight,
                       e.scrollWidth, e.clientWidth]);
    }
    return out;})()`);
  // Both axes. Checking only the vertical one let a caveat through that was
  // clipped horizontally: #tblTop is wider than the panel that scrolls it, so
  // the tail of the sentence sat past the visible edge while every string
  // assertion still passed.
  const clipped = fit.filter(([, sh, ch, sw, cw]) =>
    (sh - ch > 24) || (sw - cw > 4));
  chk(clipped.length === 0, '警告文案没有被折叠到看不见（两个方向都量）',
      clipped.length
        ? clipped.map(([id, sh, ch, sw, cw]) =>
            `${id} 纵向 ${sh}/${ch} 横向 ${sw}/${cw}`).join('; ')
        : fit.map(([id, sh, ch, sw, cw]) =>
            `${id} ${sh}/${ch}·${sw}/${cw}`).join('  '));
}

await page.screenshot(`${OUT}/final-01-L26-dims.png`);
say('  shot -> final-01-L26-dims.png');
await dragTo(injected);
await page.screenshot(`${OUT}/final-02-L20-inject.png`);
say('  shot -> final-02-L20-inject.png');
await dragTo(26);
await page.click('#tabXY');
await sleep(900);
await page.click('#tabDelta');
await sleep(1200);
await page.screenshot(`${OUT}/final-03-screen4-top.png`);
say('  shot -> final-03-screen4-top.png');

chk(exceptions.length === 0, '无未捕获异常', exceptions.slice(0, 2).join(' | '));

const summary = { hash: HASH, browser: version.Browser, fails, checkedAt: new Date().toISOString() };
writeFileSync('.cache/browser_verify3/result_final.json', JSON.stringify(summary, null, 2));
say('\nhash ' + HASH.slice(0, 16) + ' | ' + (fails.length ? fails.length + ' 项失败: ' + fails.join(' | ') : '全部通过'));
page.close(); cdp.close(); proc.kill('SIGKILL');
process.exit(fails.length ? 1 : 0);
