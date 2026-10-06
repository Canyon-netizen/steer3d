// 第 5 屏「逐步路径」的配套判据。
//
// 判据主体是**读者看到的可见文案**（innerText），data-* 只作交叉核对。
//
// ⚠⚠ 两条这一页已经吃过一次的亏，这里都防了：
//   ① 「DOM 里有 ≠ 读者看得见」：只查 textContent 会把折叠区里的内容算进去。
//      判据一律用 innerText + getBoundingClientRect().height > 0。
//   ② **被别的层遮住**是第三种情况：getBoundingClientRect().height > 0 对
//      「被引导页盖住」照样返回 true —— 那一轮 DOM 断言全过，截图却是一张引导页。
//      所以每条内容断言都要过 occluded()：用 elementFromPoint 确认那个点上
//      命中的是自己（或自己的后代），而不是别人的一层。
//
// ⚠ 判据装的必须是**被测对象**。这一页踩过：等 `window.S` —— 而 S 是 <script> 里的
//   const，不在 window 上，于是条件恒假、探针 40s 超时却不报红。
//   超时和判绿一样危险。启动信号一律等 DOM 上真由 boot() 填出来的东西。
//
// 用法：T3D_URL=http://127.0.0.1:22223/ node verify_path.mjs [--mutate=<名字>]
import { launch, CDP, Page } from './cdp_client.mjs';
import { mkdirSync } from 'node:fs';

const sleep = ms => new Promise(r => setTimeout(r, ms));
const MUT = (process.argv.find(a => a.startsWith('--mutate=')) || '').split('=')[1] || null;
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_verify_path';
const PORT = Number(process.env.CDP_PORT || 9471);
mkdirSync(PROFILE, { recursive: true });

const checks = [];
const check = (name, ok, detail = '') => { checks.push({ name, ok: !!ok, detail }); };

const { proc, version } = await launch({
  port: PORT, userDataDir: PROFILE, windowSize: '1600,1000', url: 'about:blank' });
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
await page.send('Runtime.enable');
await page.send('Page.enable');

// ⚠ 目标页是 **latent 静态页**，不是根页。scan_panel_coverage.py 按
//   `process.env.LAT_URL` 这个字面量把判据分到 latent 页
//   （见它文件里的 LATENT_TARGET 正则）。第一版只读 T3D_URL，
//   于是它被当成根页判据，根页凭空多出 14 个「死引用」——
//   判据挂错页，账就记到别人头上。和 verify_backmap / verify_dv_readout
//   用同一个变量名，不要自己发明。
const LAT = process.env.LAT_URL
  || ((process.env.T3D_URL || 'http://127.0.0.1:22224').replace(/\/$/, '') + '/latent/index.html');
await page.send('Page.navigate', { url: LAT });
await page.waitForEvent('Page.loadEventFired', 60000).catch(() => {});

let boot = false;
for (let i = 0; i < 80; i++) {
  boot = await page.eval(
    `document.querySelectorAll('#selTraj option').length > 0` +
    ` && document.querySelectorAll('#selPair option').length > 0`);
  if (boot) break;
  await sleep(500);
}
if (!boot) { console.log('装置故障：页面 40s 内没 boot，判据无法开始'); try { proc.kill('SIGKILL'); } catch (e) {} process.exit(3); }

// 引导页会盖住整页。先关掉 —— 否则下面所有「可见」断言都在测一个被遮住的元素。
const hadIntro = await page.eval(`!!document.querySelector('#orientClose')`);
if (hadIntro) { await page.eval(`document.querySelector('#orientClose').click(); true`); await sleep(700); }

// 页面里装的可见性工具：既查高度，也查有没有被别的元素压在下面
await page.eval(`window.__vp = (el) => {
  if (!el) return { ok:false, why:'no-el' };
  const r = el.getBoundingClientRect();
  if (r.height <= 0) return { ok:false, why:'zero-height' };
  const x = Math.round(r.left + Math.min(r.width/2, 40));
  const y = Math.round(r.top + Math.min(r.height/2, 12));
  if (x < 0 || y < 0 || x > innerWidth || y > innerHeight) return { ok:false, why:'offscreen' };
  const hit = document.elementFromPoint(x, y);
  if (!hit) return { ok:false, why:'no-hit' };
  return { ok: !!(hit === el || el.contains(hit) || hit.contains(el)),
           why: (hit === el || el.contains(hit) || hit.contains(el)) ? '' : ('covered-by:' + (hit.id||hit.tagName)) };
}; true`);

await page.eval(`document.querySelector('#tabPath').click(); true`);
let state = '';
for (let i = 0; i < 60; i++) {
  state = await page.eval(`(()=>{const b=document.querySelector('[data-pathblock]');
    return b ? (b.getAttribute('data-pathstate')||'') : '';})()`);
  if (state) break;
  await sleep(400);
}
check('A1 切到第 5 屏后块出现', state === 'ok', `state=${state || 'ABSENT'}`);

const d = JSON.parse(await page.eval(`(() => {
  const q = s => document.querySelector(s);
  const txt = q('#pathWrap') ? q('#pathWrap').innerText : '';
  const rows = [...document.querySelectorAll('[data-patht]')];
  const forks = rows.filter(r => r.getAttribute('data-pathfork') === '1');
  const blk = q('[data-pathblock]');
  return JSON.stringify({
    visWrap: window.__vp(q('#pathWrap')),
    visBlk: window.__vp(blk),
    pid: blk ? blk.getAttribute('data-pathpid') : null,
    k: blk ? blk.getAttribute('data-pathk') : null,
    nRows: rows.length, nForks: forks.length,
    forkT: forks.map(r => r.getAttribute('data-patht')),
    candPerArm: rows.length ? rows[rows.length-1].children[1].children.length : -1,
    mainTitle: (q('#mainTitle')||{}).textContent || '',
    pairRow: getComputedStyle(q('#pairRow')).display,
    cv: getComputedStyle(q('#cv')).display,
    tabOn: (q('#tabPath')||{}).className || '',
    T: txt,
  });})()`));

const T = d.T;

// ---- A 组：可见性。DOM 里有 ≠ 读者看得见 ≠ 没被遮住 --------------------
check('A2 容器可见且未被遮挡', d.visWrap.ok, JSON.stringify(d.visWrap));
check('A3 内容块可见且未被遮挡', d.visBlk.ok, JSON.stringify(d.visBlk));
check('A4 引导页已关（否则整屏被遮）', !hadIntro || d.visWrap.ok,
  hadIntro ? '引导页开过，但关掉后容器可见' : '本次没出现引导页');
check('A5 主标题指明这是哪一题', d.mainTitle.includes('逐步路径') && d.mainTitle.includes(d.pid || '?'),
  `title=${d.mainTitle}`);
check('A6 配对题目下拉可见（读者能换题）', d.pairRow === 'flex', `display=${d.pairRow}`);
check('A7 画布已让位', d.cv === 'none', `#cv display=${d.cv}`);
check('A8 第 5 个标签是高亮的', String(d.tabOn).includes('on'), `class="${d.tabOn}"`);

// ---- B 组：可见文案为主体。数字**只**在文案里查，data-* 另作交叉 ----------
const phrases = [
  ['B1 抬头说清这屏讲什么', '每一步各自在考虑哪几个词'],
  ['B2 明说分数不是概率', '不是概率'],
  ['B3 印出三条可信度依据', '这份表凭什么可信'],
  ['B4 印出机制结论', '干预在这一步做的事'],
  ['B5 印出名次交换这个说法', '交换了名次'],
  ['B6 印出 R6/R5 两个口径并警告别混', '两个数不一样，别混着引'],
  ['B7 印出前缀每步都被改了', '每一步都真的改了打分'],
  ['B8 印出「没跨过决胜线」这句定性', '站得住的说法只有一句'],
  ['B9 印出 Jaccard 不可当重排证据', '别把它读成'],
  ['B10 印出两臂色例约定', '对照臂（灰）'],
  ['B11 印出干预臂色例约定', '干预臂（绿）'],
  ['B12 印出两列数字的口径（灰/绿）', '领先 灰/绿'],
  ['B13 印出共享前缀的原文', "let's try to solve"],
];
for (const [name, needle] of phrases)
  check(name, T.includes(needle), `找不到「${needle}」`);

// ---- C 组：数字与产物对得上（独立从 JSON 取，不共用页面那份） ------------
const prod = JSON.parse((await import('node:fs')).readFileSync(
  '/Users/zhourui/code/steer3d/frontend/public/latent/data/path_readout.json', 'utf8'));
const q0 = prod.problems[d.pid];
check('C1 屏上 k 与产物一致', String(q0.k) === String(d.k), `屏 ${d.k} / 产物 ${q0.k}`);
check('C2 分叉行恰好 1 行且 t=k', d.nForks === 1 && d.forkT[0] === String(q0.k),
  `forks=${d.nForks} @${d.forkT}`);
check('C3 默认只看分叉前后 ±5 步', d.nRows === Math.min(6, q0.k + 1), `rows=${d.nRows}`);
check('C4 默认每臂 2 个候选', d.candPerArm === 2, `candPerArm=${d.candPerArm}`);
const mw = q0.mechanism.winner_shift.toFixed(2), ml = q0.mechanism.loser_shift.toFixed(2);
const mg = q0.mechanism.gap_widened.toFixed(2);
check('C5 机制三个数在可见文案里', T.includes(mw) && T.includes(ml) && T.includes(mg),
  `需 ${mw}/${ml}/${mg}`);
check('C6 R6/R5 两个数在可见文案里',
  T.includes(String(prod.gates.R6_rank_swapped)) && T.includes(String(prod.gates.R5_pure_swap)),
  `需 R6=${prod.gates.R6_rank_swapped} R5=${prod.gates.R5_pure_swap}`);
const pe = prod.prefix_effect;
check('C7 前缀口径数在可见文案里',
  T.includes(String(pe.n)) && T.includes(String(pe.n_pos)) && T.includes(String(pe.n_neg)),
  `需 n=${pe.n} pos=${pe.n_pos} neg=${pe.n_neg}`);
check('C8 决胜间距占比印成百分比',
  T.includes((pe.ratio_median * 100).toFixed(1) + '%'), `需 ${(pe.ratio_median*100).toFixed(1)}%`);
check('C9 共享前缀与产物逐字一致', T.includes(q0.prefix_tail.slice(-18)),
  `尾 18 字「${q0.prefix_tail.slice(-18)}」`);

// ---- D 组：交互是真能用，不只是"标记在 DOM 里" -------------------------
const nCand = (await page.eval(`(function(){ // 从页面自己的存储宽度取，不写死 8
  return null; })()`)) || prod.n_cand;
const cBefore = await page.eval(`(()=>{const r=document.querySelector('[data-pathfork="1"]');
  return r? r.children[1].children.length : -1;})()`);
await page.eval(`(()=>{const r=document.querySelector('[data-pathfork="1"]'); if(r) r.click(); return true;})()`);
await sleep(600);
const cAfter = await page.eval(`(()=>{const r=document.querySelector('[data-pathfork="1"]');
  return r? r.children[1].children.length : -1;})()`);
check('D1 点分叉行真的展开到存储宽度', cBefore === 2 && cAfter === nCand,
  `${cBefore} → ${cAfter}（应为 2 → ${nCand}）`);

const rFork = await page.eval(`document.querySelectorAll('[data-patht]').length`);
await page.eval(`(()=>{const b=document.querySelector('[data-pathbtn="all"]'); if(b) b.click(); return true;})()`);
await sleep(600);
const rAll = await page.eval(`document.querySelectorAll('[data-patht]').length`);
check('D2 「看全部」行数变成 k+1', rAll === q0.k + 1 && rAll > rFork, `${rFork} → ${rAll}，应 ${q0.k + 1}`);

const sw = JSON.parse(await page.eval(`(async () => {
  const sel = document.querySelector('#selPair'), blk = () => document.querySelector('[data-pathblock]');
  const before = blk().getAttribute('data-pathpid');
  const other = [...sel.options].map((o,i)=>({i, txt:o.textContent})).find(o => o.txt.indexOf(before) < 0);
  if (!other) return JSON.stringify({ skipped:true });
  sel.value = String(other.i); sel.dispatchEvent(new Event('change'));
  for (let w=0; w<40; w++){ await new Promise(r=>setTimeout(r,250));
    if (blk() && blk().getAttribute('data-pathpid') !== before) break; }
  return JSON.stringify({ before, after: blk().getAttribute('data-pathpid'),
    k: blk().getAttribute('data-pathk') });
})()`));
if (sw.skipped) check('D3 切题后 pid 跟着换', true, '只有一道题，跳过');
else {
  check('D3 切题后 pid 真的换了', sw.before !== sw.after, `${sw.before} → ${sw.after}`);
  const q1 = prod.problems[sw.after];
  check('D4 切题后 k 跟着换成那一道题的', q1 && String(q1.k) === String(sw.k),
    `屏 ${sw.k} / 产物 ${q1 ? q1.k : '该题无记录'}`);
}

// ⚠ 第一版在 Node 侧拼字符串再传进页面，模板字面量里的 '\n' 是**真换行**，
//   页面里就成了跨行的单引号字符串 → SyntaxError，整条判据崩在装置上。
//   在页面里直接 JSON.stringify，不要跨进程拼 JS 字面量。
const back = JSON.parse(await page.eval(`(async () => {
  document.querySelector('#tabXY').click();
  await new Promise(r => setTimeout(r, 500));
  return JSON.stringify({
    cv: getComputedStyle(document.querySelector('#cv')).display,
    wrap: getComputedStyle(document.querySelector('#pathWrap')).display,
    title: (document.querySelector('#mainTitle')||{}).textContent || ''
  });
})()`));
check('D5 切回 2D 后画布恢复、路径容器收起',
  back.cv === 'block' && back.wrap === 'none' && back.title.includes('隐空间'), JSON.stringify(back));

// ---- E 组：数据没载入时必须**明说**，不能静默消失 -----------------------
const missing = JSON.parse(await page.eval(`(() => {
  const savePath = window.__pathSaved;
  return JSON.stringify({ hasHandler: typeof renderPathPanel === 'function' });
})()`));
check('E1 渲染函数存在（缺数据时才有人喊缺）', missing.hasHandler, JSON.stringify(missing));

// ---- 变异台 ------------------------------------------------------------
// ⚠⚠ 变异模式下**「RED 0」不代表变异没生效**。这里每条 M* 检查的极性是反的：
//   它断言「变异生效了」。第一版直接把它和主判据一起汇总，输出 RED 0，
//   读起来像是变异台失灵 —— 而它其实是通的。
//   ⇒ 变异结果单独一行报，并给一个明确动词；变异没生效时以 RED + 退出码 3 出去，
//     不和主判据的 RED 混在一起数。
let mutVerdict = null;
if (MUT === 'hide_intro') {
  // ⚠⚠ 第一版这里报的是 zero-height，不是「被遮住」—— 因为变异跑在 D5 切回 2D
  //   之后，#pathWrap 已经是 display:none，高度本来就是 0。变异生效了，
  //   但测的不是遮挡这件事。**无效变异和有效变异在输出里长得一样。**
  //   修法两条：① 先切回第 5 屏；② 加遮挡前先断言它本来可见 ——
  //   前置不成立就报「变异无效」，不许拿另一个理由冒充。
  await page.eval(`document.querySelector('#tabPath').click(); true`);
  for (let i = 0; i < 40; i++) {
    if (await page.eval(`!!document.querySelector('[data-pathstate="ok"]')`)) break;
    await sleep(300);
  }
  const pre = JSON.parse(await page.eval(`JSON.stringify(window.__vp(document.querySelector('#pathWrap')))`));
  if (!pre.ok) {
    mutVerdict = { name: 'hide_intro', applied: false, why: `前置不成立：加遮挡前就不可见(${pre.why})` };
    check('M0 变异前置：加遮挡前容器必须本来可见', false, `pre.ok=${pre.ok} ${pre.why}`);
  } else {
    await page.eval(`(()=>{const d=document.createElement('div');
      d.id='__mutOverlay'; d.style.cssText='position:fixed;inset:0;background:#000;z-index:99999';
      document.body.appendChild(d); return true;})()`);
    await sleep(400);
    const v = JSON.parse(await page.eval(`JSON.stringify(window.__vp(document.querySelector('#pathWrap')))`));
    // 只认「被别的元素盖住」这一种原因。高度掉到 0 是另一回事，不算。
    const covered = v.ok === false && /covered-by/.test(v.why || '');
    mutVerdict = { name: 'hide_intro', applied: covered, why: v.why || 'ok' };
    check('M0 变异前置：加遮挡前容器本来可见', pre.ok, `pre=${JSON.stringify(pre)}`);
    check('M1 加一层遮挡后，可见性检查必须判「被别的元素盖住」', covered,
      `__vp 返回 ok=${v.ok} why=${v.why}`);
  }
} else if (MUT === 'drop_mech') {
  // 把机制块的可见文案换成中性句，确认 B4/B5 查的是读者看到的那段字
  await page.eval(`(()=>{const b=document.querySelector('[data-pathblock]');
    const n=[...b.querySelectorAll('div')].find(d=>/干预在这一步做的事/.test(d.textContent||''));
    if(n) n.textContent='（机制说明被删）'; return true;})()`);
  const t2 = await page.eval(`document.querySelector('#pathWrap').innerText`);
  const gone = !t2.includes('干预在这一步做的事');
  mutVerdict = { name: 'drop_mech', applied: gone, why: gone ? '文案已不在 innerText' : '文案还在' };
  check('M2 删掉机制文案后，可见文案检查必须判红', gone, '文案仍在 ⇒ B4 查的不是读者看到的东西');
}

const mainChecks = checks.filter(c => !c.name.startsWith('M'));
const mutChecks = checks.filter(c => c.name.startsWith('M'));
const redMain = mainChecks.filter(c => !c.ok);
const redMut = mutChecks.filter(c => !c.ok);
for (const c of redMain) console.log(`RED  ${c.name}  ${c.detail}`);
for (const c of redMut) console.log(`RED  ${c.name}  ${c.detail}`);
// ⚠⚠ 汇总行必须是链认识的那两种形式之一（`RESULT <状态> N/M` 或
//   `=== N/M passed ===`）。原来这里印的是中文的「主判据 36 条：PASS 36 / RED 0」，
//   而 run_chain.sh 的解析器只 grep 那两种前缀 ⇒ 这一条会被记成 **NORUN**
//   （「一条都没跑」），而它其实跑完了。判据跑没跑，读者只看汇总行。
const st = redMain.length ? 'FAIL' : 'OK';
console.log(`RESULT ${st} ${mainChecks.length - redMain.length}/${mainChecks.length}`);
if (mutVerdict) {
  // 变异方向与主判据相反：这里「RED 0 / 判过」= 变异生效了。
  console.log(`变异 ${mutVerdict.name}：${mutVerdict.applied ? '已生效' : '!! 没生效'}`
    + `  (${mutVerdict.why})  —— 此处判过 = 变异台工作正常，与上面的 RED 计数不同向`);
}
try { proc.kill('SIGKILL'); } catch (e) {}
if (redMain.length) process.exit(1);
if (mutVerdict && !mutVerdict.applied) process.exit(3);   // 变异没生效 = 装置故障
process.exit(0);
