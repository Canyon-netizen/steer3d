// Verify the two new blocks (per-layer logit lens + vector roles) actually
// render, and measure the geometry the eye sees.
//
// The failure mode this file exists for: a 320px right-hand column, where a
// previous version put two 143px columns side by side and EVERY textContent
// check still passed while a human could not read it. So this measures widths
// and takes shots, and it takes more than one: a long block shot at its top
// shows nothing of what is below.
import { launch, CDP, Page } from '../browser_verify/cdp_client.mjs';
import { writeFileSync } from 'node:fs';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const URL0 = process.argv[2] || 'http://127.0.0.1:8917/latent/index.html';

const { proc, version } = await launch({
  port: 9411, userDataDir: '/Users/zhourui/code/steer3d/.cache/lens/shotprofile',
  url: 'about:blank',
});
const cdp = await CDP.connect(
  `ws://127.0.0.1:9411/devtools/browser/${version.webSocketDebuggerUrl.split('/').pop()}`);
const page = await Page.create(cdp);
await page.send('Network.enable');
await page.send('Runtime.enable');
await page.send('Page.setDeviceMetricsOverride',
  { width: 1440, height: 1100, deviceScaleFactor: 2, mobile: false });

const errs = [];
await page.eval(`(()=>{window.__e=[];window.onerror=(m)=>window.__e.push(String(m));
  window.addEventListener('unhandledrejection',e=>window.__e.push('rej:'+e.reason));})()`);
await page.send('Page.navigate', { url: URL0 });
await page.waitForEvent('Page.loadEventFired', 40000);
await sleep(1000);
if (await page.eval(`(()=>{const o=document.getElementById('orientation');
  return !!(o && getComputedStyle(o).display!=='none')})()`)) {
  await page.click('#orientClose'); await sleep(700);
}
await page.click('#tabDelta'); await sleep(3500);

const fails = [];
const chk = (c, label, extra = '') => {
  console.log((c ? '  ok   ' : '  FAIL ') + label + (extra ? '   ' + extra : ''));
  if (!c) fails.push(label);
};

// ---- presence, with content read off the rendered DOM, not the payload ----
const g = await page.eval(`(()=>{
  const lr=document.querySelector('[data-lensroot]');
  const rr=document.querySelector('[data-rolesroot]');
  const chart=document.querySelector('[data-lenschart]');
  const hist=document.querySelector('[data-lenshist]');
  const box=e=>{if(!e)return null;const r=e.getBoundingClientRect();
    return {w:Math.round(r.width),h:Math.round(r.height)};};
  return {
    lens: !!lr, roles: !!rr,
    lensText: lr?lr.innerText:'',
    rolesText: rr?rr.innerText:'',
    chart: box(chart), hist: box(hist),
    bars: chart?chart.querySelectorAll('rect').length:-1,
    histBars: hist?hist.querySelectorAll('rect').length:-1,
    picks: document.querySelectorAll('[data-lenspick]').length,
    stepSlider: !!document.querySelector('[data-lensstep]'),
    // widest descendant that would overflow the sidebar
    maxW: lr?Math.max(...[...lr.querySelectorAll('*')]
        .map(e=>e.getBoundingClientRect().width)):0,
    errs: window.__e,
  };
})()`);

console.log('--- 逐层 logit lens ---');
chk(g.lens, '逐层 lens 块渲染出来了');
chk(g.bars === 28, `28 根柱子都在（0..27 层）`, `bars=${g.bars}`);
chk(g.chart && g.chart.w >= 280, `柱状图撑满侧栏宽度`, `w=${g.chart && g.chart.w}`);
chk(g.histBars === 28, `直方图 28 根柱子都在`, `bars=${g.histBars}`);
chk(g.hist && g.hist.w >= 280, `直方图撑满侧栏宽度`, `w=${g.hist && g.hist.w}`);
// The anchor is the reason this curve means anything. It must be on screen
// with its denominators, not just present in the JSON.
chk(/第 27 层/.test(g.lensText) && /1420|1532/.test(g.lensText),
    '锚点（第 27 层复现真实 top-1）带分母显示在页面上');
chk(/没中的那几步没有被丢掉/.test(g.lensText), '锚点没中那几步如实说明，不静默丢弃');
// The anchor caveat must be in Chinese. Echoing the payload's English string
// verbatim put five lines of English inside an otherwise Chinese panel, and a
// regex on the English text passed while the panel was unreadable to the
// audience it is written for.
chk(!/the misses are steps|reconstruction error/i.test(g.lensText),
    '锚点说明是中文（不是把产物的英文串直接贴上来）');
// M2 lives here: the held-out gate passes creativity at ~1.8 sigma, so without
// the in-sample cross-reference a marginal win is presented as a clean PASS.
chk(/循环口径下不通过/.test(g.rolesText),
    '循环口径下不通过的那一格被标出来（否则勉强胜出显示成干净通过）');
chk(/高出随机上限/.test(g.rolesText), '给出超出随机控制上限的幅度（σ）');
chk(g.picks >= 8, '题号选择器有选项', `${g.picks} 个`);
chk(g.stepSlider, '步滑块在');
// The layer where the decision is made is the whole point of the block.
chk(/L20|L21/.test(g.lensText), '峰��层（L20–L21）在页面上');
// Overflow: any child wider than the block means horizontal clipping.
chk(g.maxW <= 300, '没有元素超出侧栏宽度（不会被横向裁掉）', `maxW=${g.maxW}`);

console.log('--- 向量三角色 ---');
chk(g.roles, '三角色块渲染出来了');
chk(/必要性/.test(g.rolesText), '必要性在');
chk(/充分性/.test(g.rolesText), '充分性在');
chk(/特异性/.test(g.rolesText), '特异性在');
// The empirical random-direction floor, NOT 1/sqrt(n-3). If the page prints
// only the textbook floor, a reader will believe the margin is 10x larger
// than it is.
chk(/打败全部/.test(g.rolesText) && /随机方向/.test(g.rolesText),
    '门槛写的是「打败全部随机方向」而不是 1/√(n−3)');
chk(/留出/.test(g.rolesText), '必要性标明用了留出法（不是循环论证）');
chk(/不通过|通过/.test(g.rolesText), '每项带通过/不通过判定');
// The measured-and-contradicted claim must be on the page, not smoothed over.
chk(/全局/.test(g.rolesText) && /不吻合/.test(g.rolesText),
    '「效应是全局的」这个与原解读冲突的结论写出来了');
chk(/测不了|NOT_MEASURABLE|没存/.test(g.rolesText), '测不了的那项如实标注');

console.log('--- 交互 ---');
const READSTEP = `(()=>{const e=document.querySelector('[data-lensroot]');
  if(!e) return '';
  const m=(e.innerText.match(/第 \\d+ 步[^\\n]*/)||[''])[0];
  const h=(e.querySelector('[data-lenschart]')||{innerHTML:''}).innerHTML;
  return m+' ||| '+h;})()`;
const before = await page.eval(READSTEP);
const btns = await page.eval(`(()=>document.querySelectorAll('[data-lenspick]').length)()`);
await page.eval(`(()=>{document.querySelectorAll('[data-lenspick]')[3].click();})()`);
await sleep(700);
const after = await page.eval(READSTEP);
chk(before !== after, '点第 4 个题号，逐层 readout 真的换了', btns + ' 个可选');
chk(/^第 \d+ 步/.test(after), '换题后仍然显示步号', after.split(' ||| ')[0]);
// The old step's readout must be gone. A screenshot of the step line alone is
// not enough: if only the header changed and the 28 bars did not, the page is
// showing the previous problem's layers under the new problem's name.
chk(before.split(' ||| ')[1] !== after.split(' ||| ')[1],
    '换题后 28 根柱子的内容也真的换了（不只是标题）');
// Switching problems must reset the step, or the new problem shows a step
// index borrowed from the old one.
const stepReset = await page.eval(`(()=>{
  const s=document.querySelector('[data-lensstep]');
  return s?{value:s.value, max:s.max}:null;})()`);
chk(stepReset && Number(stepReset.value) <= Number(stepReset.max),
    '换题后步号在新题的范围内', JSON.stringify(stepReset));

// page.eval returns the value as-is; window.__e is an array on the page side
// but came back as an object through the CDP bridge, so Array.isArray first.
const e2 = await page.eval(`(()=>{const e=window.__e||[]; return {n:e.length, msg:Array.from(e).join(' | ')};})()`);
chk(e2.n === 0, '无未捕获异常', e2.msg || '');

// ---- shots: the block top AND something below it ----
const shot = async (name) => {
  const r = await page.send('Page.captureScreenshot', { format: 'png' });
  writeFileSync(`.cache/lens/${name}.png`, Buffer.from(r.data, 'base64'));
  console.log('  wrote .cache/lens/' + name + '.png');
};
await page.eval(`(()=>{const e=document.querySelector('[data-lensroot]');
  if(e) e.scrollIntoView({block:'start'});})()`);
await sleep(600); await shot('shot_lens_top');
await page.eval(`(()=>{const e=document.querySelector('[data-lenshist]');
  if(e) e.scrollIntoView({block:'center'});})()`);
await sleep(600); await shot('shot_lens_hist');
await page.eval(`(()=>{const e=document.querySelector('[data-rolesroot]');
  if(e) e.scrollIntoView({block:'start'});})()`);
await sleep(600); await shot('shot_roles_top');
await page.eval(`(()=>{const e=document.querySelector('[data-rolesroot]');
  const rows=e?[...e.querySelectorAll('.kv')]:[];
  if(rows.length) rows[rows.length-1].scrollIntoView({block:'center'});})()`);
await sleep(600); await shot('shot_roles_deep');

console.log('\n---------------------------------------');
console.log(fails.length ? `失败 ${fails.length} 条` : 'ALL PASS');
await page.send('Browser.close').catch(()=>{});
proc.kill('SIGKILL');
process.exit(fails.length ? 1 : 0);
