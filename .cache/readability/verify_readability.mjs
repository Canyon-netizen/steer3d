// 可读性验收脚本。在真实浏览器里跑，能红。
//
//   node .cache/readability/verify_readability.mjs
//       跑两档视口（1600x1000 / 1280x800），全绿则 exit 0。
//   node .cache/readability/verify_readability.mjs --negctl=gloss,number,hidden
//       负控：故意在页面上制造三处破坏，确认对应断言真的会红。红了才算通过
//       （负控自身红 = 脚本在工作；负控自身绿 = 脚本恒绿，没有判别力）。
//
// 三条设计原则，都是这个项目被坑出来的：
//  1. 量布局，不查字符串。文案在 DOM 里 ≠ 读者看得到。纵向用
//     scrollHeight - clientHeight，横向对每个元素用 getBoundingClientRect().right
//     与最近的裁剪祖先右边界比。
//  2. 判"就地解释"而不是"页面上某处有"：一个术语的**首次可见处**所在容器里
//     必须带着它的白话解释，容器取该文本块最近的 .gitem / .ex>div / .noitem /
//     li / p。术语在后面的某一屏才被解释，一律算 FAIL。
//  3. 页面内要注入的函数一律以真实 JS 源码传入（Function#toString），带参数的
//     调用用 JSON.stringify 编参数，绝不把正则拼进模板字符串 —— verify_final.mjs
//     里的 /\d/ 被模板字面量吃成字母 d，那条断言其实一直没在跑。

import { launch, CDP, Page } from '../browser_verify/cdp_client.mjs';
import { writeFileSync, mkdirSync, readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import * as P from './probe_lib.mjs';

const ROOT = '/Users/zhourui/code/steer3d';
const URL = 'http://localhost:8917/latent/index.html';
const ORIGIN = 'http://localhost:8917';
const OUT = '.cache/readability';
const ORIENT_KEY = 'qwen3-latent-orientation-read-v1';
const sleep = ms => new Promise(r => setTimeout(r, ms));
mkdirSync(`${ROOT}/${OUT}/shots`, { recursive: true });

const argv = process.argv.slice(2);
const negctlArg = argv.find(a => a.startsWith('--negctl='));
const NEG = negctlArg ? negctlArg.slice(9).split(',').filter(Boolean) : [];
const SIZES = [
  { w: 1600, h: 1000, port: 9371, dir: 'p1600' },
  { w: 1280, h: 800,  port: 9372, dir: 'p1280' },
];

const bytes = readFileSync(`${ROOT}/frontend/public/latent/index.html`);
const HASH = createHash('sha256').update(bytes).digest('hex').slice(0, 16);

// ---------------------------------------------------------------- 术语表
// 判据：一个不懂机器学习的中文母语读者，在页面上第一次看到这个词会卡住、
// 必须回看或查资料才敢往下读。anchor 是该术语**首次可见处**必须同时出现的
// 白话解释，逐字取自导读层文案 —— 抄错了就红，这正是要的效果。
const TERMS = [
  { t: 'token',      anchor: '模型一次写的一个词的碎片' },
  { t: '熵',          anchor: '模型有多犹豫' },
  { t: 'top1 概率',   anchor: '排名第一的那个词有多大概率被选中' },
  { t: '候选词',      anchor: '模型此刻心里排队的字' },
  { t: '层',          anchor: '一次加工工序' },
  { t: '维度',        anchor: '一份状态里数字的个数' },
  { t: '投影',        anchor: '压成 2 个数字' },
  { t: 'PCA',        anchor: '最能解释差异的方向' },
  { t: 'PC1',        anchor: '它找到的前两根轴' },
  { t: 'embedding',  anchor: '查表把词变成一串数字' },
  { t: '隐空间',      anchor: '模型脑子里那份' },
  { t: '残差流',      anchor: '新加上去的那部分' },
  { t: '残差',        anchor: '新加上去的那部分' },
  { t: '范数',        anchor: '草稿有多长' },
  { t: '干预',        anchor: '人为往草稿里推一把' },
  { t: '对照',        anchor: '什么都不做地跑一遍' },
  { t: '位移',        anchor: '被推了多远' },
  { t: 'logit',      anchor: '还没归一化的原始打分' },
  { t: 'block',      anchor: '一次加工工序' },
  { t: 'PC2',        anchor: '它找到的前两根轴' },
];
// 英文行话：页面首屏一旦出现这些词，就必须有对应中文词条。新增一个英文术语
// 而忘了加词条 → 红。中文行话无法可靠分词，靠这张人工表，见报告的局限说明。
const JARGON_LATIN = ['token', 'tokens', 'PCA', 'PC1', 'PC2', 'embedding', 'logit',
                      'logits', 'block', 'blocks', 'dimension', 'dimensions',
                      'hidden', 'state', 'states'];

const results = [];
let failed = 0, passed = 0;
function chk(ok, label, extra = '') {
  results.push({ ok: !!ok, label, extra });
  if (ok) passed++; else failed++;
  const tag = ok ? '  ok  ' : '  FAIL';
  console.log(tag + ' ' + label + (extra ? '   [' + extra + ']' : ''));
  return !!ok;
}
const head = t => console.log('\n=== ' + t + ' ===');

/** 带参数调用页内函数：参数走 JSON.stringify，正则不经过字符串拼接。 */
const call = (page, fn, ...args) =>
  page.eval('(' + fn.toString() + ')(' + args.map(a => JSON.stringify(a)).join(',') + ')');

async function ready(page) {
  for (let i = 0; i < 160; i++) {
    const st = await page.eval(`(()=>({l:getComputedStyle(document.getElementById('loading')).display,
      a:getComputedStyle(document.getElementById('app')).visibility,
      r:document.querySelectorAll('#tblTop tr').length}))()`);
    if (st.l === 'none' && st.a === 'visible' && st.r > 0) return true;
    await sleep(250);
  }
  throw new Error('page never became ready');
}
const clearLS = page => page.send('Storage.clearDataForOrigin',
  { origin: ORIGIN, storageTypes: 'local_storage' });

/** 可见文本块 + 每块的"说明容器文本"（就地解释判据用）。 */
const visPage = page => call(page, P.collectVisible, null);
// 导读层整篇（放开视口那一跳，保留遮挡/裁剪判据）= 读者往下滚能读到的全部
const visOrient = page => call(page, P.collectVisible, { whole: true, root: '#orientBody' });

// ---------------------------------------------------------------- 主流程

async function runSize(S) {
  head(`视口 ${S.w}x${S.h}  index.html sha256 ${HASH}`);
  const { proc, version } = await launch({
    port: S.port,
    userDataDir: `${ROOT}/${OUT}/profile_${S.dir}`,
    windowSize: `${S.w},${S.h}`,
    url: 'about:blank',
  });
  const cdp = await CDP.connect(
    `ws://127.0.0.1:${S.port}/devtools/browser/${version.webSocketDebuggerUrl.split('/').pop()}`);
  const page = await Page.create(cdp);
  const exceptions = [];
  cdp.on(m => {
    if (m.method === 'Runtime.exceptionThrown')
      exceptions.push(m.params.exceptionDetails?.exception?.description ||
                      m.params.exceptionDetails?.text || '?');
  });

  await clearLS(page);
  await page.nav(URL);
  await ready(page);
  await sleep(600);

  /* ---------- A. 导读层默认就在视口里 ---------------------------------- */
  head('A 导读层默认可见（几何判据，不是查字符串）');
  const oGeo = await call(page, P.probeVisible, '#orientation');
  chk(oGeo.found, 'A1 #orientation 存在');
  chk(!oGeo.hasHideClass && oGeo.display === 'flex',
      'A2 默认未隐藏', 'hide=' + oGeo.hasHideClass + ' display=' + oGeo.display);
  chk(oGeo.rect.w > 0 && oGeo.rect.h > 0, 'A3a 浮层有实际尺寸',
      oGeo.rect.w + 'x' + oGeo.rect.h);
  const vp = await page.eval(`(()=>({w:window.innerWidth,h:window.innerHeight}))()`);
  chk(oGeo.rect.x >= -0.5 && oGeo.rect.y >= -0.5 &&
      oGeo.rect.x + oGeo.rect.w <= vp.w + 0.5 && oGeo.rect.y + oGeo.rect.h <= vp.h + 0.5,
      'A3 浮层完整落在视口内', JSON.stringify(oGeo.rect) + ' vs ' + vp.w + 'x' + vp.h);
  const titleGeo = await call(page, P.probeVisible, '#orientTitle');
  chk(titleGeo.inView && !titleGeo.clipped, 'A4 标题在视口内且未被裁剪',
      JSON.stringify(titleGeo.rect) + (titleGeo.clipped ? ' 被 ' + titleGeo.clipped.by + ' 裁' : ''));
  const leadGeo = await call(page, P.probeVisible, '.olead');
  chk(leadGeo.inView && !leadGeo.clipped, 'A5 一句话在视口内（打开就能读到第一句）',
      JSON.stringify(leadGeo.rect));
  const footGeo = await call(page, P.probeVisible, '#orientFoot');
  chk(footGeo.inView && !footGeo.clipped, 'A6 底部按钮在视口内（读者知道怎么关）',
      JSON.stringify(footGeo.rect));
  const scrollGeo = await call(page, P.probeVisible, '#orientScroll');
  chk(scrollGeo.vOver > 0, 'A7 长文确实靠 #orientScroll 自己滚动（不是被截断）',
      'scrollHeight-clientHeight=' + scrollGeo.vOver);
  chk(oGeo.vOver === 0, 'A8 浮层自身不滚动', 'vOver=' + oGeo.vOver);
  const orientBleed = await page.eval(P.horizontalBleed);
  chk(orientBleed.length === 0, 'A9 导读层内无横向越界（逐元素量）',
      orientBleed.length ? JSON.stringify(orientBleed.slice(0, 3)) : '0 个元素越界');
  const poOpen = await page.eval(P.pageOverflow);
  chk(poOpen.vOver === 0 && poOpen.hOver === 0, 'A10 浮层不撑出页面级滚动条',
      'vOver=' + poOpen.vOver + ' hOver=' + poOpen.hOver);

  /* ---------- B. 术语在首次可见处就地有白话解释 ------------------------ */
  head('B 术语首次可见处就地有白话解释（不是"页面上某处有"）');
  // 首屏 = 导读层打开时读者第一眼看到的东西。探针带遮挡判据（elementFromPoint），
  // 所以浮层底下的页面文字不会被算进来。
  const first = await visPage(page);
  const whole = await visOrient(page);
  chk(first.blocks.length > 0 && first.blocks.every(b => b.inOrient),
      'B-0 首屏取到的是导读层本身（浮层底下的页面文字已被遮挡判据排除）',
      first.blocks.length + ' 块，样例 ' + (first.blocks[0] || {}).sel +
      (first.blocks.every(b => b.inOrient) ? '' : ' | 混入了非导读层块'));
  const tFirst = [], tWhole = [];
  for (const { t, anchor } of TERMS) {
    const fb = first.blocks.find(x => x.ctx.includes(t));
    if (fb) tFirst.push({ t, anchor, ok: fb.ctx.includes(anchor), at: fb.sel, y: fb.y,
                          where: fb.gitemTerm ? 'gitem[' + fb.gitemTerm + ']' : fb.ctxSel });
    const wb = whole.blocks.find(x => x.ctx.includes(t));
    tWhole.push({ t, anchor, ok: wb ? wb.ctx.includes(anchor) : false,
                  at: wb ? wb.sel : '(导读层里没出现)', y: wb ? wb.y : -1,
                  where: wb ? (wb.gitemTerm ? 'gitem[' + wb.gitemTerm + ']' : wb.ctxSel) : '' });
  }
  for (const r of tFirst)
    chk(r.ok, 'B1 首屏术语 "' + r.t + '" 首次可见处带白话解释',
        r.ok ? ('@' + r.where + ' y=' + r.y) : ('缺 "' + r.anchor + '" @' + r.at));
  for (const r of tWhole)
    chk(r.ok, 'B2 导读层里 "' + r.t + '" 的首次出现带白话解释',
        r.ok ? ('@' + r.where) : (r.at === '(导读层里没出现)' ? '全文未出现' : '缺 "' + r.anchor + '"'));
  chk(tFirst.length >= 8, 'B3 首屏确实带解释的术语 ≥ 8（非空跑）',
      '首屏术语 ' + tFirst.length + ' 个 / 全表 ' + TERMS.length + ' 个');
  chk(tWhole.every(r => r.ok), 'B4 全部 ' + TERMS.length + ' 个术语均就地解释',
      tWhole.filter(r => r.ok).length + '/' + tWhole.length);
  // 词条表与导读层正文必须双向自洽：词条里的词在正文里都解释到，正文用的词都有词条
  const wholeStream = whole.blocks.map(b => b.text).join('   ');
  const orphan = TERMS.filter(x => !wholeStream.includes(x.t));
  chk(orphan.length === 0, 'B5 词条表里的词在导读层正文中都出现',
      orphan.length ? '缺: ' + orphan.map(o => o.t).join(',') : '全部出现');

  /* ---------- C. 例子里的数字 == 页面真实数字 ---------------------------- */
  head('C 导读层例子用的是页面真实数字');
  const st = await page.eval(P.readOrientationStruct);
  const setTok = k => page.eval(`(()=>{const e=document.getElementById('rngTok');
    e.value=${k};e.dispatchEvent(new Event('input',{bubbles:true}));return 1;})()`);
  const readRow = () => page.eval(`(()=>{
    const t=s=>{const e=document.querySelector(s);return e?e.textContent.replace(/\\s+/g,' ').trim():'';};
    const rows=[...document.querySelectorAll('#tblTop tr')].slice(0,2)
      .map(r=>[...r.querySelectorAll('td')].map(x=>x.textContent.replace(/\\s+/g,' ').trim()));
    return {raw:t('#stRaw'),ent:t('#stEnt'),d:t('#stD'),max:document.getElementById('rngLayer').max,
            top1:rows[0]?rows[0][1]:'',top2:rows[1]?rows[1][1]:''};})()`);
  await setTok(0); await sleep(350);
  const r0 = await readRow();
  const exText = st.ex.join(' ');
  chk(r0.raw === '<think>', 'C0 默认 token 0 的原词已读到', r0.raw);
  chk(r0.ent === '0.001 / 1.000', 'C1 默认 token 0 的熵/top1 概率已读到', r0.ent);
  chk(exText.includes(r0.ent), 'C2 导读层写着这个真实读数', r0.ent);
  chk(exText.includes('<think>'), 'C3 导读层写着 <think>', '<think>');
  await setTok(5); await sleep(350);
  const r5 = await readRow();
  chk(r5.raw === "'s", 'C4 第 5 步原词已读到', r5.raw);
  chk(r5.ent === '0.530 / 0.777', 'C5 第 5 步熵/top1 概率已读到', r5.ent);
  chk(exText.includes(r5.ent), 'C6 导读层写着第 5 步的真实读数', r5.ent);
  chk(exText.includes("'s"), 'C7 导读层写着第 1 候选词', "'s");
  chk(r5.top1 === "'s" && r5.top2 === 'me', 'C8 候选词表第 1/2 名已读到',
      r5.top1 + ' / ' + r5.top2);
  chk(exText.includes('me'), 'C9 导读层写着第 2 候选词', r5.top2);  chk(r0.d === '2048', 'C10 原始向量维度 2048', r0.d);
  chk(exText.includes(r0.d), 'C11 导读层写着 2048', r0.d);
  chk(r0.max === '27', 'C12 层滑块上限 27（=28 道工序）', 'max=' + r0.max);
  chk(exText.includes('28'), 'C13 导读层写着 28 道工序', '28');
  const pairs = await page.eval(`fetch('data/pairs/pairs.json').then(r=>r.json()).then(j=>({
    n:j.pairs.length,first:j.pairs[0].id,last:j.pairs[j.pairs.length-1].id,
    layer:j.pairs[0].inject_layer,strength:j.pairs[0].strength,dir:j.pairs[0].direction}))`);
  chk(pairs.n === 6, 'C14 干预 vs 对照真的只有 6 道题', 'n=' + pairs.n);
  chk(pairs.first === '1983_I_1' && pairs.last === '1988_I_1',
      'C15 题号区间 1983–1988', pairs.first + '..' + pairs.last);
  chk(pairs.layer === 20 && pairs.strength === 0.2,
      'C16 干预层 20 / 强度 0.2', 'L' + pairs.layer + ' / ' + pairs.strength);
  const limAll = await page.eval(`(()=>[...document.querySelectorAll('#orientBody .lim li')]
    .map(x=>x.textContent.replace(/\\s+/g,' ').trim()).join('   '))()`);
  chk(limAll.includes('6') && limAll.includes('1983') && limAll.includes('1988'),
      'C17 数据边界写明 n=6 与题号区间', limAll.slice(0, 60));
  chk(limAll.includes('Qwen3-1.7B'), 'C18 数据边界写明只有 1 个模型');
  chk(limAll.includes('20') && limAll.includes('0.2') && limAll.includes(pairs.dir === 'confidence_up' ? '自信' : pairs.dir),
      'C19 数据边界写明唯一干预方向/层/强度');
  chk(st.no.length === 4, 'C20 本页不主张的 4 种说法都在', '条数=' + st.no.length);
  chk(st.no[0] && st.no[0].includes('0.0%–20.7%') && st.no[0].includes('587–831'),
      'C21 第 1 条否证带真实数字', (st.no[0] || '').slice(0, 40));

  /* ---------- D. 关掉能记住、能重置 ------------------------------------ */
  head('D 关闭 / 记住 / 重置');
  const lsq = k => page.eval(`(()=>{try{return localStorage.getItem(${JSON.stringify(k)});}catch(e){return 'ERR';}})()`);
  await page.click('#orientClose'); await sleep(300);
  const gClose = await call(page, P.probeVisible, '#orientation');
  chk(gClose.hasHideClass, 'D1 点「我读完了」后浮层隐藏');
  chk((await lsq(ORIENT_KEY)) === '1', 'D2 localStorage 记下已读', String(await lsq(ORIENT_KEY)));
  const closedBleed = await page.eval(P.horizontalBleed);
  chk(closedBleed.length === 0, 'D3 关闭后页面无横向越界',
      closedBleed.length ? JSON.stringify(closedBleed.slice(0, 2)) : '0');
  await page.nav(URL); await ready(page); await sleep(500);
  const gReload = await call(page, P.probeVisible, '#orientation');
  chk(gReload.hasHideClass, 'D4 重新打开页面不再弹（记住了）');
  const btn = await call(page, P.probeVisible, '#btnOrient');
  chk(btn.inView && !btn.hasHideClass, 'D5 「📖 导读」按钮可见可点（随时重读）',
      JSON.stringify(btn.rect));
  await page.click('#btnOrient'); await sleep(300);
  const gReopen = await call(page, P.probeVisible, '#orientation');
  chk(!gReopen.hasHideClass, 'D6 点按钮能重新打开导读');
  await page.click('#orientReset'); await sleep(300);
  chk((await lsq(ORIENT_KEY)) === null, 'D7 重置按钮清掉 localStorage', String(await lsq(ORIENT_KEY)));
  const gReset = await call(page, P.probeVisible, '#orientation');
  chk(!gReset.hasHideClass, 'D8 重置后浮层仍打开');
  await page.nav(URL); await ready(page); await sleep(500);
  const gAfterReset = await call(page, P.probeVisible, '#orientation');
  chk(!gAfterReset.hasHideClass, 'D9 重置后再打开页面默认又弹（可复验）');
  // ?orient=off 便于自动化复验时关掉导读层
  await page.nav(URL + '?orient=off'); await ready(page); await sleep(400);
  chk((await call(page, P.probeVisible, '#orientation')).hasHideClass,
      'D10 ?orient=off 能强制不弹（脚本与截图用）');
  await page.nav(URL + '?orient=off'); await ready(page); await sleep(500);
  await page.screenshot(`${ROOT}/${OUT}/shots/app_first_screen_${S.w}x${S.h}.png`);

  /* ---------- E. 导读层有没有引入新的布局溢出 -------------------------- */
  head('E 布局：开/关两状态逐项比对（不查字符串，量几何）');
  const poClosed = await page.eval(P.pageOverflow);
  chk(poClosed.vOver === 0 && poClosed.hOver === 0, 'E1 关闭后页面仍无级联滚动',
      'vOver=' + poClosed.vOver + ' hOver=' + poClosed.hOver);
  const PAGE_SEL = '.wrap,.panel,.col';
  const loClosed = await call(page, P.layoutOverflow, PAGE_SEL);
  await page.nav(URL + '?orient=show'); await ready(page); await sleep(500);
  const loOpen = await call(page, P.layoutOverflow, PAGE_SEL);
  // 只比页面本体：#orientation / #orientBody 这些浮层元素本来就该在开与关之间
  // 变形，把它们放进比较里，这条断言就变成了永远失败的同义反复。
  const same = JSON.stringify(loClosed) === JSON.stringify(loOpen);
  chk(same, 'E2 导读层开/关，.wrap 与各 panel 的几何与溢出逐字段相同',
      same ? loClosed.length + ' 个元素完全一致' : '几何不同');
  // HEAD 基线在 1280x800 下左上面板本来就有 1px 纵向溢出（attribute_overflow.mjs
  // 实测：HEAD panel:1 → 本版必须仍然是 1）。所以这里比的是"不许变差"，不是绝对 0。
  const BASELINE_PANEL_VOVER = 1;
  const vOverList = loClosed.filter(x => x.vOver > 0);
  const maxPanelVOver = Math.max(0, ...loClosed.map(x => x.vOver));
  chk(maxPanelVOver <= BASELINE_PANEL_VOVER,
      'E3 面板纵向溢出不超过 HEAD 基线（scrollHeight-clientHeight）',
      vOverList.length ? (vOverList.map(x => x.sel + ':' + x.vOver).join(',') +
        ' | 基线 ' + BASELINE_PANEL_VOVER) : '0 个溢出');
  const hOverList = loClosed.filter(x => x.hOverVsParent > 1 || x.hOverSelf > 1);
  chk(hOverList.length === 0, 'E4 无横向越界（元素右边界 vs 父容器右边界）',
      hOverList.length ? JSON.stringify(hOverList.slice(0, 3)) : '0 个越界');
  // 导读层正文比容器高是设计如此（它就该滚动），但必须由 #orientScroll 承担，
  // 且正文右边界不得越出滚动容器。
  const loOrient = await call(page, P.layoutOverflow, '#orientBody,#orientScroll,.gitem');
  const ob = loOrient.find(x => x.sel.endsWith('#orientBody'));
  chk(ob && ob.hOverSelf === 0 && ob.hOverVsParent <= 1,
      'E5 导读层正文不横向越界（靠 max-width + 换行，不是靠裁剪）',
      ob ? ('hOverSelf=' + ob.hOverSelf + ' hOverVsParent=' + ob.hOverVsParent) : '未取到');
  const gOver = loOrient.filter(x => x.sel.endsWith('.gitem') && (x.vOver > 0 || x.hOverSelf > 1));
  chk(gOver.length === 0, 'E6 每条词条自身不溢出（长解释不靠裁剪显示）',
      gOver.length ? JSON.stringify(gOver.slice(0, 2)) : loOrient.length + ' 个词条均无溢出');
  const maxV = Math.max(0, ...loClosed.map(x => x.vOver));
  const maxH = Math.max(0, ...loClosed.map(x => Math.max(x.hOverVsParent, x.hOverSelf)));
  console.log('  实测：' + S.w + 'x' + S.h +
    ' | 页面级 vOver=' + poClosed.vOver + ' hOver=' + poClosed.hOver +
    ' | panel 最大 vOver=' + maxV + ' 最大 hOver=' + maxH +
    ' | 导读层内横向越界 ' + orientBleed.length + ' 处');

  /* ---------- F. 英文行话覆盖（防新增术语漏词条） ---------------------- */
  head('F 页面首屏英文行话必须有中文词条');
  await page.click('#orientClose'); await sleep(250);
  const appVis = await visPage(page);
  const appText = appVis.blocks.map(b => b.text).join('   ');
  const latin = [...new Set((appText.match(/[A-Za-z][A-Za-z0-9_]{1,}/g) || [])
    .filter(w => JARGON_LATIN.includes(w)))];
  const missing = latin.filter(w => !TERMS.some(t => t.t === w));
  chk(missing.length === 0, 'F1 页面首屏英文行话都进了词条表',
      latin.length ? ('见到: ' + latin.join(',') + (missing.length ? ' | 缺: ' + missing.join(',') : ' | 全有词条'))
                   : '首屏无英文行话');
  // F2 用 textContent 而不是 innerText：innerText 只含**渲染出来**的文本，页面里
  // 大量说明在别的 tab / 别的状态上。还要先把 token 挪到第 5 步：logit 只出现在
  // 右栏「这一层在做什么」的**动态**文案里（token>1 时才生成），停在第 0 步去查，
  // 会得到一个假的"空条目"。
  await page.eval(`(()=>{const e=document.getElementById('rngTok');e.value=5;
    e.dispatchEvent(new Event('input',{bubbles:true}));return 1;})()`);
  await sleep(500);
  const appSrc = await page.eval(`(()=>document.getElementById('app').textContent||'')()`);
  const dead = TERMS.filter(t => !appSrc.includes(t.t));
  chk(dead.length === 0, 'F2 词条表没有空条目（每条都是页面真在用的词）',
      dead.length ? '空条目: ' + dead.map(d => d.t).join(',') : TERMS.length + ' 条全部在用');
  const gStruct = await page.eval(P.readOrientationStruct);
  const thin = gStruct.items.filter(i => i.plain.length < 12 || !i.where);
  chk(thin.length === 0, 'F3 每条词条都有白话解释和「在哪儿看」',
      thin.length ? '不合格: ' + thin.map(i => i.term).join(',')
                  : gStruct.items.length + ' 条词条合格');
  // 20 个术语合并成 14 条词条（干预/对照、层/block、残差流/残差、PCA/PC1/PC2 等
  // 逐对合并），所以条数不等于术语数。
  chk(gStruct.items.length >= 14, 'F4 词条数 ≥ 14（20 个术语合并成 14 条）',
      '词条数=' + gStruct.items.length);

  /* ---------- 负控：故意破坏，确认脚本会红 ------------------------------ */
  if (NEG.length) {
    head('负控（页面被人为破坏后，对应断言必须变红）');
      // probe() 收的是**真实判据的结果**：红 = 判据失败 = 负控生效。
      // （第一版这里传的是取反后的值，于是"负控红 0/绿 2"——把"还是绿的"当成了
      //  报红。这正是恒绿脚本最容易骗过自己的地方。）
      for (const mode of NEG) {
        const marks = { passed: 0, failed: 0, lines: [] };
        // 行首标 negctl> 是有意的：这些 FAIL 是**期望中的红**，不是本次验收的失败。
        // 验收的结论只看下一行「负控 X 确实报红」。
        const probe = (ok, label) => {
          marks.lines.push('  negctl> ' + (ok ? '判据仍然绿(←负控没生效)' : '判据变红(←负控生效)') +
                           '  ' + label);
          ok ? marks.passed++ : marks.failed++;
        };
      await clearLS(page);
      await page.nav(URL); await ready(page); await sleep(500);
      if (mode === 'gloss') {
        // 破坏：把 §2 例子里的「熵」白话解释删掉（模拟"解释丢了"）
        await page.eval(`(()=>{const s=[...document.querySelectorAll('#orientBody .ex .inline-gloss')]
          .find(e=>e.textContent.includes('模型有多犹豫'));
          if(s) s.textContent='';return 1;})()`);
        const b = await visOrient(page);
        const hit = TERMS.find(t => t.t === '熵');
        const firstHit = b.blocks.find(x => x.ctx.includes(hit.t));
        probe(!!(firstHit && firstHit.ctx.includes(hit.anchor)),
              'NEG[gloss] 熵 的解释被删 → B2「首次出现带白话解释」应 FAIL');
        const f = await visPage(page);
        const fb = f.blocks.find(x => x.ctx.includes(hit.t));
        probe(!!(fb && fb.ctx.includes(hit.anchor)),
              'NEG[gloss] B1 首屏同一条也应 FAIL');
      } else if (mode === 'number') {
        // 破坏：把例子里的真实读数改错（模拟"例子和页面各说各话"）
        await page.eval(`(()=>{const d=[...document.querySelectorAll('#orientBody .ex > div')]
          .find(e=>e.textContent.includes('0.530 / 0.777'));
          if(d) d.innerHTML=d.innerHTML.replace('0.530 / 0.777','0.530 / 0.999');
          return 1;})()`);
        const stx = await page.eval(P.readOrientationStruct);
        const ex = stx.ex.join(' ');
        probe(ex.includes('0.530 / 0.777'),
              'NEG[number] 例子被改成 0.777→0.999 → C6「例子=真实读数」应 FAIL');
      } else if (mode === 'hidden') {
        // 破坏：让导读层默认打不开（模拟"加了但看不见"）
        await page.eval(`(()=>{document.getElementById('orientation').classList.add('hide');return 1;})()`);
        const g = await call(page, P.probeVisible, '#orientation');
        probe(g.hasHideClass && g.display === 'flex',
              'NEG[hidden] 浮层被 hide → A2「默认未隐藏」应 FAIL');
        probe(g.inView && !g.clipped,
              'NEG[hidden] 浮层不可见 → A4/A5/A6 应 FAIL');
        const f = await visPage(page);
        const fb = f.blocks.find(x => x.ctx.includes('熵'));
        probe(!!(fb && fb.ctx.includes('模型有多犹豫')),
              'NEG[hidden] 首屏不再是导读层 → B1/B3 应 FAIL');
      } else {
        console.log('  ?? 未知负控模式: ' + mode);
        continue;
      }
      const red = marks.failed > 0;
      chk(red, `负控 ${mode} 确实报红`, `红 ${marks.failed} / 绿 ${marks.passed}`);
      marks.lines.forEach(l => console.log(l));
      writeFileSync(`${ROOT}/${OUT}/negctl_${mode}_${S.w}.txt`, marks.lines.join('\n') + '\n');
    }
  }

  chk(exceptions.length === 0, 'Z 页面无未捕获异常',
      exceptions.length ? exceptions[0].slice(0, 120) : '0');
  // 转义自检：本脚本有一批走模板字符串发进浏览器的表达式，若 \\d 被吃成字母 d，
  // 那些断言会"永远不匹配"却一直绿。verify_final.mjs 就死在这上面。这里让浏览器
  // 自己回读它编出来的正则，确认 Node 侧的双写反斜杠到位。
  const esc = await page.eval(`(()=>({src:String(/第 (\\d+) 步/),
    hit:/第 (\\d+) 步/.test('分叉点：第 27 步')}))()`);
  chk(esc.hit === true && esc.src.indexOf('\\d') >= 0,
      'Z1 转义自检：浏览器里跑的正则确实含 \\d 而不是字母 d',
      JSON.stringify(esc));
  page.close(); cdp.close(); proc.kill('SIGKILL');
}

for (const S of SIZES) await runSize(S);

console.log('\n==================================================');
console.log(`断言 ${passed + failed} 条：绿 ${passed} / 红 ${failed}`);
console.log('index.html sha256:', HASH);
writeFileSync(`${ROOT}/${OUT}/verify_result.json`, JSON.stringify(
  { hash: HASH, passed, failed, results }, null, 2));
process.exit(failed ? 1 : 0);
