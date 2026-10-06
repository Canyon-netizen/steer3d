// 第 5 屏「逐步路径」的诊断探针。
//
// ⚠ 为什么等条件不等时长：固定 sleep 会在这块上重演 dump_rc 那一轮的老问题 ——
//   面板还在 loading 就去读，读出「块不存在」，我差点当成「没渲染」。
//   每一处等待都是轮询一个具体的 data-* 出现，且记下轮询了几次。
//
// ⚠ 为什么查可见性而不只是查 innerText：这一页已经吃过一次亏 —— 反例被塞进
//   折叠的 <details>，判据用 textContent 查到就判绿，而读者根本看不见。
//   所以每条断言都同时要 innerText 和 getBoundingClientRect().height > 0。
import { launch, CDP, Page } from './cdp_client.mjs';
import { mkdirSync } from 'node:fs';

const sleep = ms => new Promise(r => setTimeout(r, ms));
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_diag_path';
const PORT = Number(process.env.CDP_PORT || 9461);
mkdirSync(PROFILE, { recursive: true });

const { proc, version } = await launch({
  port: PORT, userDataDir: PROFILE, windowSize: '1600,1000', url: 'about:blank' });
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
await page.send('Page.enable');
await page.send('Runtime.enable');

const url = process.env.T3D_URL
  ? process.env.T3D_URL.replace(/\/$/, '') + '/latent/index.html'
  : 'http://127.0.0.1:22223/latent/index.html';
await page.send('Page.navigate', { url });
await page.waitForEvent('Page.loadEventFired', 60000).catch(() => {});

// 1) 页面自身水合完成。
// ⚠⚠ 第一版这里等的是 `window.S && S.path && S.pm` —— 而 S 是 <script> 里的
//   `const`，**不在 window 上**。于是这个条件恒为 false，40s 全耗在等一个
//   永远不会出现的信号，最后读到 null。
//   判据装的不是被测对象时，它不会「红」，它会**超时**——和判绿一样危险。
//   改成等 DOM 上真正由 boot() 填出来的东西：轨迹下拉 + 配对下拉都有选项。
let boot = false, bootN = 0;
for (let i = 0; i < 80; i++) {
  boot = await page.eval(
    `document.querySelectorAll('#selTraj option').length > 0` +
    ` && document.querySelectorAll('#selPair option').length > 0`);
  if (boot) { bootN = i; break; }
  await sleep(500);
}
console.log(`等 boot（两个下拉都填上）：${boot ? `就绪（第 ${bootN} 次轮询）` : '40s 内没就绪'}`);
if (!boot) {
  console.log(JSON.stringify(await page.eval(`JSON.stringify({
    selTraj: document.querySelectorAll('#selTraj option').length,
    selPair: document.querySelectorAll('#selPair option').length,
    hasTabPath: !!document.querySelector('#tabPath')})`)));
  process.exit(2);
}

// 2) 点第 5 个标签
await page.eval(`document.querySelector('#tabPath').click(); true`);
let block = '', state = '', onN = 0;
for (let i = 0; i < 60; i++) {
  const st = await page.eval(`(()=>{const b=document.querySelector('[data-pathblock]');
    return b? b.getAttribute('data-pathstate')||'' : '';})()`);
  if (st) { state = st; onN = i; break; }
  await sleep(400);
}
console.log(`等 [data-pathblock]：${state ? `出现 state=${state}（第 ${onN} 次轮询）` : '没出现'}`);

const out = await page.eval(`(() => {
  const vis = el => !!(el && el.getBoundingClientRect().height > 0);
  const wrap = document.querySelector('#pathWrap');
  const blk  = document.querySelector('[data-pathblock]');
  const rows = [...document.querySelectorAll('[data-patht]')];
  const fork = rows.filter(r => r.getAttribute('data-pathfork') === '1');
  // 可见文案（innerText）而不是 textContent：textContent 会把折叠/隐藏里的也算进来
  const wrapText = wrap ? wrap.innerText : '';
  return JSON.stringify({
    pathWrapDisplay: wrap ? getComputedStyle(wrap).display : 'ABSENT',
    pathWrapVisible: vis(wrap),
    pathWrapH: wrap ? Math.round(wrap.getBoundingClientRect().height) : 0,
    blockVisible: vis(blk),
    state: blk ? blk.getAttribute('data-pathstate') : 'ABSENT',
    pid: blk ? blk.getAttribute('data-pathpid') : null,
    k: blk ? blk.getAttribute('data-pathk') : null,
    nRows: rows.length,
    forkRows: fork.length,
    forkT: fork.map(r => r.getAttribute('data-patht')),
    mainTitle: (document.querySelector('#mainTitle')||{}).textContent || '',
    pairRowShown: getComputedStyle(document.querySelector('#pairRow')).display,
    cvHidden: getComputedStyle(document.querySelector('#cv')).display,
    textLen: wrapText.length,
    // 可见文案里必须出现的几段，逐条给布尔，判据直接读这些
    has_heading:  wrapText.includes('每一步各自在考虑哪几个词'),
    has_cred:     wrapText.includes('这份表凭什么可信'),
    has_mech:     wrapText.includes('干预在这一步做的事'),
    has_swap:     wrapText.includes('交换了名次'),
    has_r5r6:     wrapText.includes('两个数不一样，别混着引'),
    has_prefix:   wrapText.includes('每一步都真的改了打分'),
    has_notmono:  wrapText.includes('站得住的说法只有一句'),
    has_jac:      wrapText.includes('别把它读成'),
    has_score:    wrapText.includes('原始打分、不是概率'),
    // 表头必须印出两臂的色例约定
    has_colhdr:   wrapText.includes('对照臂（灰）') && wrapText.includes('干预臂（绿）'),
    // 默认只显示 2 个候选：数第一行里有几个 span
    // ⚠ 只数**直属** span：querySelectorAll('span') 会把每个候选里那个放小字分数的
    //   内层 span 也数进去，top-2 数出 3、top-8 数出 15 —— 数字看着合理，含义是错的。
    candPerArm: (() => {
      const r = rows[rows.length - 1];
      if (!r) return 0;
      const cells = r.children;
      return cells[1] ? cells[1].children.length : -1;
    })(),
  }, null, 1);
})()`);
console.log(out);

// 3) 点分叉行 → 应该展开到 8 个
const before = await page.eval(`(()=>{const r=document.querySelector('[data-pathfork="1"]');
  return r? r.children[1].children.length : -1;})()`);
await page.eval(`(()=>{const r=document.querySelector('[data-pathfork="1"]'); if(r) r.click(); return true;})()`);
await sleep(700);
const after = await page.eval(`(()=>{const r=document.querySelector('[data-pathfork="1"]');
  return r? r.children[1].children.length : -1;})()`);
console.log(`点分叉行展开：每臂候选数 ${before} → ${after}  ${after > before ? 'OK' : '!! 没展开'}`);

// 4) 切「看全部」→ 行数应变成 k+1
const rowsFork = await page.eval(`document.querySelectorAll('[data-patht]').length`);
await page.eval(`(()=>{const b=document.querySelector('[data-pathbtn="all"]'); if(b) b.click(); return true;})()`);
await sleep(700);
const rowsAll = await page.eval(`document.querySelectorAll('[data-patht]').length`);
console.log(`切「看全部」：行数 ${rowsFork} → ${rowsAll}  ${rowsAll > rowsFork ? 'OK' : '!! 没变多'}`);

// 5) 切题：换到另一道有记录的题，看 pid 和 k 是否**真的**变了。
// ⚠ 第一版把 sel.options 的 value（索引 "0".."5"）和 data-pathpid（题号
//   "1983_I_1"）比大小 —— 两者不同口径，find 恒为真，target 恒等于索引 0，
//   于是 sel.value="0" 切回的还是原来那道，探针却打印出 before==after 就算过。
//   两个读数口径不同的时候，"跑通了"和"验到了"是两件事。
const switched = await page.eval(`(async () => {
  const sel = document.querySelector('#selPair');
  const blk = () => document.querySelector('[data-pathblock]');
  if (!sel || sel.options.length < 2) return 'ONLY_ONE_PAIR';
  const before = blk().getAttribute('data-pathpid');
  const beforeK = blk().getAttribute('data-pathk');
  // 先把「哪几个索引对应别的题」从选项文本里读出来（选项文本含题号）
  const other = [...sel.options].map((o,i) => ({ i, txt: o.textContent }))
    .find(o => o.txt.indexOf(before) < 0);
  if (!other) return 'NO_OTHER';
  sel.value = String(other.i);
  sel.dispatchEvent(new Event('change'));
  for (let w = 0; w < 40; w++) {
    await new Promise(r => setTimeout(r, 250));
    if (blk() && blk().getAttribute('data-pathpid') !== before) break;
  }
  const b = blk();
  const after = b.getAttribute('data-pathpid');
  return JSON.stringify({ before, after, changed: after !== before,
    k_before: beforeK, k_after: b.getAttribute('data-pathk'),
    rows: document.querySelectorAll('[data-patht]').length,
    mainTitle: (document.querySelector('#mainTitle')||{}).textContent || '' });
})()`);
const sw = JSON.parse(switched);
console.log('切题：', switched);
console.log(`  切题真的换了吗：${sw.changed ? 'OK' : '!! 没换（判据装错对象）'}`);

// 6) 离开这一屏再回来，别把 canvas 弄丢
await page.eval(`document.querySelector('#tabXY').click(); true`);
await sleep(600);
const backXY = await page.eval(`(()=>({cv:getComputedStyle(document.querySelector('#cv')).display,
  wrap:getComputedStyle(document.querySelector('#pathWrap')).display,
  title:(document.querySelector('#mainTitle')||{}).textContent||''}))()`);
console.log('切回隐空间 2D：', JSON.stringify(backXY));

// 7) 控制台有没有报错（render 抛异常会让整块静默消失而页面照常）
const errs = await page.eval(`JSON.stringify((window.__errs||[]).slice(0,10))`);
console.log('页面自记错误：', errs);

try { proc.kill('SIGKILL'); } catch (e) {}
process.exit(0);
