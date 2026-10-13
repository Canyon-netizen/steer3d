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
import { launch, CDP, Page } from '/Users/zhourui/code/steer3d/.cache/browser_verify/cdp_client.mjs';
import { mkdirSync } from 'node:fs';

const sleep = ms => new Promise(r => setTimeout(r, ms));
const MUT = (process.argv.find(a => a.startsWith('--mutate=')) || '').split('=')[1] || null;
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_verify_path';
const PORT = Number(process.env.CDP_PORT || 9471);
mkdirSync(PROFILE, { recursive: true });

const checks = [];
const check = (name, ok, detail = '') => { checks.push({ name, ok: !!ok, detail }); };

// ⚠⚴ 修订 118：**「跳过」不是「通过」**，不得进红绿分母。
// 处置照抄 verify_scene_link.mjs 的 checkPrecond —— 单独记、不进 checks。
// ⚠ 原写法 `check('D3 …', true, '只有一道题，跳过')` 会把「没验」记成「验过了」。
// ⚠ 但跳过**不许掩盖真红**：真红仍然 push 进 checks、仍然 exit 1。
const skips = [];
const skip = (name, why) => {
  skips.push({ name, why });
  console.log(`[SKIP] ${name}: ${why}`);
};

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
if (sw.skipped) skip('D3 切题后 pid 跟着换', '只有一道题，无从切');
else {
  check('D3 切题后 pid 真的换了', sw.before !== sw.after, `${sw.before} → ${sw.after}`);
  const q1 = prod.problems[sw.after];
  check('D4 切题后 k 跟着换成那一道题的', q1 && String(q1.k) === String(sw.k),
    `屏 ${sw.k} / 产物 ${q1 ? q1.k : '该题无记录'}`);
}

// ⚠ 第一版在 Node 侧拼字符串再传进页面，模板字面量里的 '\n' 是**真换行**，
//   页面里就成了跨行的单引号字符串 → SyntaxError，整条判据崩在装置上。
//   在页面里直接 JSON.stringify，不要跨进程拼 JS 字面量。
// ⚠⚠⚴⚠⁴ 修订 144：这一段原本只有一句裸的「点 #tabXY」。元素一被拆掉，就在页内抛异常；
//   异常一路冒到 Node 顶层 ⇒ **整份判决作废、压根不打印 RESULT 行**。
//   ⚗ 实测证据：专门拆掉 #tabXY 的那个臂跑出来只有 12 行、无 RESULT 行
//   （那不是「D5 没牙齿」，是**这一条把整份判决掀了桌**）。
//   ⇒ 改成「页内失败 = 这一条红」：其余 38 条照跑，分子分母仍是同一个量。
//   ⚠⚠⚴⚠⁴⚠⁴ **下面这整块（含注释）处在 page.eval 的模板字面量内部，
//     一个反引号都不能有** —— 反引号会**提前终止模板** ⇒ 语法错误。
//     （修订 133 / 134 / 142 在同一个地方踩过三次。）
let back;
try {
// ===== r134b 注入：拆掉 D 组依赖的点击目标（按 R134_ARM 选臂） =====
// ⚠ 只改页面状态，不做任何判定 ⇒ 结论全部由下面未改动的原判据给出。
const __arm = (process.env.R134_ARM || 'fork').toLowerCase();
const __r134b = JSON.parse(await page.eval(`JSON.stringify((() => {
  const q = s => document.querySelector(s);
  const gone = {};
  if (${JSON.stringify(__arm)} === 'fork') { const e = q('[data-pathfork="1"]'); const before = !!e; if (e) e.remove(); gone.fork = { before, after: !!q('[data-pathfork="1"]') }; }
  else if (${JSON.stringify(__arm)} === 'all') { const e = q('[data-pathbtn="all"]'); const before = !!e; if (e) e.remove(); gone.all = { before, after: !!q('[data-pathbtn="all"]') }; }
  else if (${JSON.stringify(__arm)} === 'pair') {
    const sel = q('#selPair');
    // ⚠⚠⚴⚠ before **必须在删之前**读。第一版写在 while 之后 ⇒ 恒为 1
    //   ⇒ 落地核验永远判「未落地」，而**原因不是页面没拆掉，是我读错了时机**。
    // ⚠⚠⚴⚠⚠⚠ 顺带一条硬纪律：**注入块里不许出现反引号** ——
    //   整个注入块处在 page.eval 的**模板字面量**里，反引号会**提前终止模板**，
    //   ⇒ 语法错误。本轮为此踩了一次（本该写「before」却写成 「」before「」）。
    const before = sel ? sel.options.length : -1;
    if (sel) { while (sel.options.length > 1) sel.remove(1); sel.selectedIndex = 0; }
    gone.pairOpts = { before, after: sel ? sel.options.length : -1 };
  }
  else if (${JSON.stringify(__arm)} === 'xy') { const e = q('#tabXY'); const before = !!e; if (e) e.remove(); gone.xy = { before, after: !!q('#tabXY') }; }
  else return { bad: true, arm: ${JSON.stringify(__arm)} };
  return { gone, arm: ${JSON.stringify(__arm)} };
})())`));

// ⚠⚠⚴ **落地核验**：拆掉了必须**真的没了**（或真的只剩一个 option）。
//   拆不掉却继续跑 ⇒ 判据全绿会被读成「判据扛住了扰动」，正是修订 133 的病。
// ⚠⚗⚗⚗⚗⚠ 第一版写成 「」gone.all = !q(...)「」 ⇒ **元素本来就不存在时也判「已落地」**
//   （「」!null === true「」）——**空落地**。本轮实测：「」all「」 臂印「已落地」却 RESULT OK 36/36，
//   就是因为 「」[data-pathbtn="all"]「」 在那一屏**根本不存在**，什么都没拆掉。
//   ⇒ 落地判据必须是「**拆之前确实存在**」且「**拆之后确实不存在**」，两半都要。
const __g = __r134b.gone || {};
const __k = Object.keys(__g)[0];
const __v = __g[__k] || {};
const __ok = !__r134b.bad && (
  (__v.before === true  && __v.after === false) ||        // 单元素臂：存在 → 消失
  (__v.before > 1 && __v.after === 1));                    // pair 臂：多个 → 只剩 1
if (!__ok) { console.log('[扰动未落地] ' + JSON.stringify(__r134b)); process.exit(2); }
console.log('[扰动已落地] 臂 ' + __arm + '：' + JSON.stringify(__r134b.gone));
  back = JSON.parse(await page.eval(`(async () => {
  const q = s => document.querySelector(s);
  const tabXY = q('#tabXY');
  if (!tabXY) return JSON.stringify({ err: '页内找不到 #tabXY（点击目标已被拆掉）' });
  const cv = q('#cv'), wrap = q('#pathWrap');
  if (!cv || !wrap) return JSON.stringify({ err: '页内找不到 #cv 或 #pathWrap' });
  tabXY.click();
  await new Promise(r => setTimeout(r, 500));
  return JSON.stringify({
    cv: getComputedStyle(cv).display,
    wrap: getComputedStyle(wrap).display,
    title: (document.querySelector('#mainTitle')||{}).textContent || ''
  });
})()`));
} catch (e) {
  // ⚠⚠⁴ 页内**真的抛了**异常（不是上面那两条主动返回）⇒ 也只让 D5 红，不掀桌。
  //   后面的 E2/E3/E4 块自己有页内 try/catch（修订 142 加的），会把失败收成红。
  back = { err: '页内抛异常：' + String((e && e.message) || e) };
}
check('D5 切回 2D 后画布恢复、路径容器收起',
  !back.err && back.cv === 'block' && back.wrap === 'none' && back.title.includes('隐空间'),
  back.err || JSON.stringify(back));

// ---- E 组：数据没载入时必须**明说**，不能静默消失 -----------------------
const missing = JSON.parse(await page.eval(`(() => {
  const savePath = window.__pathSaved;
  return JSON.stringify({ hasHandler: typeof renderPathPanel === 'function' });
})()`));
check('E1 渲染函数存在（缺数据时才有人喊缺）', missing.hasHandler, JSON.stringify(missing));

// ⚠⚠⚴⚠⚴ E2/E3/E4（修订 141 新增）。E1 只证明「函数在」，**证不了它名字里那半句**：
//   实测（修订 140）「typeof renderPathPanel」在「数据在」与「数据缺」两种情形下
//   **都是「function」** ⇒ 分不开 ⇒ 这就是 E1 落「第四档」的**机制**（不是它的描述）。
//   ⇒ 这里把页面**拨到缺数据的两种情形**各一次，核**读者看得见的文案**：
//     ① 整份 path_readout 取不到 → 屏上须说「逐步路径数据未载入」
//     ② 数据在、当前这道题没记录 → 屏上须说「这份…里没有题目…只覆盖 N 道题」
//   ⚠⚠⚴ **两个情形都要测** —— 只测一个就是「只验了一半」。
//   ⚠「data-pathstate」**只作交叉核对**（证明节点在）；**主体断言是可见文字**。
//   ⚠⚠⚴ 拨完必须**原样还原**：不还原会污染紧随其后的变异台（M0–M2）。
//   ⚠⚠⚴⚠⚴ **下面这段注释里一个字都不能出现反引号**：它整体在 page.eval 的
//     模板字面量内部，反引号会**提前终止模板** ⇒ 整条判据崩在语法错误上
//     （修订 133/134 踩过；派生台会剥注释里的反引号，但主文件不会）。
const said = JSON.parse(await page.eval(`(async () => {
  const wrap = document.querySelector('#pathWrap');
  const savePath = S.path;
  const saveText = wrap ? wrap.innerText : '';
  const pid = (S.pm && S.pm.pairs && S.pm.pairs[S.pi]) ? S.pm.pairs[S.pi].id : null;
  const grab = () => {
    wrap.innerHTML = renderPathPanel();
    const b = wrap.querySelector('[data-pathblock]');
    return { text: (b ? (b.innerText || '') : ''),
             state: (b ? (b.getAttribute('data-pathstate') || '') : '(无块)') };
  };
  const out = {};
  try{
    // ① 整份数据取不到
    S.path = null;
    out.noData = grab();
    S.path = savePath;
    // ② 数据在、这一题没记录
    const saved = (pid && savePath && savePath.problems) ? savePath.problems[pid] : null;
    if (saved) delete savePath.problems[pid];
    out.noProblem = grab();
    if (saved) savePath.problems[pid] = saved;
    // 还原面板，并**自证还原成功**
    wrap.innerHTML = renderPathPanel();
    out.restoredOK = (wrap.innerText === saveText);
    out.pathIntact = (S.path === savePath);
    out.beforeLen = saveText.length;
    out.afterLen = wrap.innerText.length;
  }catch(e){
    // ⚗⚠⚴⚠⚴ **页内失败必须变成一条红，不能变成掀桌。**
    //   D5 的教训（修订 134 §134.5）：「#tabXY.click()」没有空值保护，
    //   元素一被删就抛异常 ⇒ 脚本直接崩、**压根不打印 RESULT** ⇒ 判决变成一段堆栈。
    //   ⇒ 这里 catch 住并把消息带出去，交给下面的 check 判红。
    out.err = String((e && e.message) || e);
  }
  return JSON.stringify(out);
})()`));
const saidNoData = !said.err && said.noData.text.indexOf('未载入') >= 0
  && said.noData.text.indexOf('path_readout.json') >= 0;
const saidNoProblem = !said.err && said.noProblem.text.indexOf('没有题目') >= 0
  && said.noProblem.text.indexOf('逐步路径只覆盖') >= 0;
const d0 = said.err ? '页内失败：' + said.err
  : `state=${said.noData.state} ${said.noData.text.length} 字`;
const d1 = said.err ? '页内失败：' + said.err
  : `state=${said.noProblem.state} ${said.noProblem.text.length} 字`;
check('E2 整份路径数据取不到时，屏上明说缺什么（可见文案）', saidNoData, d0);
check('E3 这一题没记录时，屏上明说并给出换题指引（可见文案）', saidNoProblem, d1);
// ⚗⚠⚴ E4 是**台架自检**，不是产品性质：拨完必须原样还原，否则污染后面的变异台。
check('E4 【台架自检】上面两次拨动已原样还原',
  !said.err && said.pathIntact && said.restoredOK,
  said.err ? '页内失败：' + said.err
    : `pathIntact=${said.pathIntact} ${said.beforeLen} → ${said.afterLen} 字`);

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
// ⚠⚠⚴⚠⁴ 修订 144：自曝**判据名单**。为什么这一行不是多余的：
//   实测里一个臂把分母从 39 压到 37，而日志只印了**一条** [SKIP] D3 ——
//   数字差 2、行数差 1。⚗⚠⁴ 那第 2 条是 **D4 落在 if/else 的另一侧、压根没执行**，
//   ⚠⚠⁴⚠⁴ 它**一行都不打印** ⇒「被跳过的」与「压根没跑的」在日志上完全同形，
//   ⚠⚠⁴ 分母相等、相减，**任何只看数字和 [SKIP] 行的对账都分不开它们**。
//   ⇒ 跑台拿这一行做「基线名单 − 臂上名单」的差集，才能把两者分开记账。
//   ⚠⚠⚴⚠⚴⚠⁴ 它**不是新增判据**：不改任何断言、不翻面、不进分母（分母仍是 39）。
//     ⚠⚠⁴ 它唯一的副作用是让仪器**吐出它本来就知道的东西** ——
//     ⚠⚠⁴⚠⁴⚠⁴ 而「仪器本来就知道却没吐」正是修订 143 记账反转的根因之一。
console.log('判据名单 ' + mainChecks.length + ' 条：' + mainChecks.map(c => c.name).join(' | '));
console.log('名单口径 mainChecks + skips（跳过的那几条不在 mainChecks 里，skip() 不进 checks）'
  + '；全集是 mainChecks，跳过名单只是它的一**注释**，不是并列的第二份全集');
if (skips.length) {
  // ⚠⚠⁴⚠⁴ 修订 144 的**当场自曝**：改这一块时我先把 `for (const s of skips) console.log('[SKIP] …')`
  //   整段删掉了，理由是「名单行已经覆盖了」。⚗⚠⁴ 而跑台的 `parse()` 是靠
  //   `RE_SKIP = /^\[?SKIP\]?\s+(\S+)/` 抓跳过列表的 ⇒ **删掉它，跳过机制当场失聪**，
  //   ⚠⚠⁴⚠⁴ 而**日志上完全看不出来**（只是 skip 列表变空，不会报错）。
  //   ⚠⚠⁴⚠⁴⚠⁴ ⇒ 纪律：**改判据里已被跑台解析的那几行之前，先把跑台的正则读出来**
  //     （修订 133/134/141/143 已在同一个「改判据顺手改坏仪器」的族里栽过）。
  console.log(`跳过 ${skips.length} 条（**不进分母**，N/M 里不含它们）：`);
  for (const s of skips) console.log(`  [SKIP] ${s.name} —— ${s.why}`);
  // ⚠⚠⁴ 跳过的那几条**不在 mainChecks 里**（skip() 不进 checks），所以要**另外列**。
  //   ⚠⚠⚴⚠⁴ 只列 mainChecks 是不够的：跳过的正是「分母变小」的第一种机制，
  //   ⚠⚠⁴ 不列它，差集里就会把「跳过」误判成「消失」。
  console.log('跳过名单 ' + skips.length + ' 条：' + skips.map(s => s.name).join(' | '));
}
if (mutVerdict) {
  // 变异方向与主判据相反：这里「RED 0 / 判过」= 变异生效了。
  console.log(`变异 ${mutVerdict.name}：${mutVerdict.applied ? '已生效' : '!! 没生效'}`
    + `  (${mutVerdict.why})  —— 此处判过 = 变异台工作正常，与上面的 RED 计数不同向`);
}
try { proc.kill('SIGKILL'); } catch (e) {}
if (redMain.length) process.exit(1);
if (mutVerdict && !mutVerdict.applied) process.exit(3);   // 变异没生效 = 装置故障
process.exit(0);
