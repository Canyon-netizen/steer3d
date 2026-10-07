import { launch, Page, CDP } from './cdp_client.mjs';
import { readFileSync } from 'fs';

/**
 * 第二十五笔 L 组：**逐层 logit lens 那一块的散文，数字与句子从哪来。**
 *
 * ## 为什么先做这一块
 *
 * 覆盖扫描的 C4 报出 24 个「渲染了但没有任何判据读过」的标记，
 * `data-lensroot / lenschart / lenshist / lenspick / lensstep` 五个都在里面。
 * 而这一块正是用户诉求里那句
 * 「各个 hidden states 到底最后是如何推导出这个 token 的」**最直接的答案**
 * —— 把最后一层的读出方式套到每一层，看它自己会说出哪个词。
 * 搬进 #extras 之后它第一次默认可见，却**一个数都没有判据**。
 *
 * ## 本组防的具体六处（第二十五笔当场查出来的）
 *
 *   L3  「约 0.09 个 logit」——**全仓没有任何产物记过这个数**。
 *       产物自己的 honest_caveat 只说「top1-top2 间距低于 float16 重建误差」
 *       这个**关系**、不给量级 ⇒ 当时就没钉死。⇒ 必须删，不能换成另一个猜的数。
 *   L5  「这批是 16k 采集的数据」——产物里没有记批次上下文长度的字段。
 *   L4  层号「0–27 / 第 27 层 / 28 层」全写死（值恰好对，来源是 model.n_layers）。
 *   L6  「峰值在 L20–L21」——counts 的 argmax 实测是 **21**，写死值已过期。
 *   L7  「L27 前 ${cum}%」——cum 是把 counts 整个加完，那是「到最后为止」，
 *       标签与口径差一层。
 *   L8  那个 `l === 20` 的标记：产物里没有 inject_layer 字段，
 *       所以它不能自称「注入层」。
 *
 * ## 判据主体必须在渲染层
 *
 * 要防的正是「字都在页面上，但那些字是手打的」。只扫源码抓不到：
 * 手打与现算在源码里长得一模一样。
 */
const URL = process.env.LAT_URL || 'http://127.0.0.1:22113/latent/index.html';
const DATA = '/Users/zhourui/code/steer3d/frontend/public/latent/data/';
const SRC = '/Users/zhourui/code/steer3d/frontend/public/latent/index.html';
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_l_' + process.pid;
const sleep = ms => new Promise(r => setTimeout(r, ms));

const rows = [];
let pass = 0, total = 0;
function rec(name, ok, detail) {
  total++; if (ok) pass++;
  rows.push([ok, name, detail]);
  console.log('[%s] %s\n       %s', ok ? 'PASS' : 'FAIL', name, detail);
}
const j = f => JSON.parse(readFileSync(DATA + f, 'utf8'));

/**
 * 剥掉 JS 注释，保留字符串字面量内容。
 * ⚠ 第三轮同款：L8 直接扫源码时扫到了**我自己写的注释**。
 *   `//` 前面是 `:` 时不算注释头，否则 `http://` 会被整行切掉。
 */
function stripJsComments(src) {
  let out = '', i = 0; const n = src.length;
  while (i < n) {
    const c = src[i];
    if (c === '/' && src[i + 1] === '/' && src[i - 1] !== ':') {
      const j2 = src.indexOf('\n', i); i = j2 < 0 ? n : j2; continue;
    }
    if (c === '/' && src[i + 1] === '*') {
      const j2 = src.indexOf('*/', i + 2); i = j2 < 0 ? n : j2 + 2; continue;
    }
    if (c === '"' || c === "'" || c === '`') {
      const q = c, start = i; i++;
      while (i < n) {
        if (src[i] === '\\') { i += 2; continue; }
        if (src[i] === q) { i++; break; }
        i++;
      }
      out += src.slice(start, i); continue;
    }
    out += c; i++;
  }
  return out;
}

// ---------- 装置事故前置：连不上就不报 N/M ----------
let reach = null;
try { reach = await fetch(URL, { method: 'GET' }); } catch (e) { /* 下面统一处理 */ }
if (!reach || !reach.ok) {
  console.log('[FAIL] L0 页面不可达 ⇒ **装置事故，不是被测物判红**');
  console.log(`       URL = ${URL}  状态 = ${reach ? reach.status : '连不上'}`);
  console.log('       下面一条都没执行 ⇒ **不报 N/M**，退出码 4。');
  process.exit(4);
}

// ---------- 产物层的期望值：从被测物自己的字段现算，不写死 ----------
const L = j('logit_lens.json');
const NL = Number(L.model.n_layers);
const LASTL = NL - 1;
const fc = L.aggregate.first_layer_correct_hist;
const c = fc.counts;
const tot = fc.total;
const PEAK = c.indexOf(Math.max(...c));
const pct = n => Math.round(n / tot * 100);
const cumTo = k => c.slice(0, k).reduce((a, b) => a + b, 0);
const cumAll = c.reduce((a, b) => a + b, 0);

const { proc, version } = await launch({
  port: 9600 + (process.pid % 90), userDataDir: PROFILE,
  windowSize: '1900,3200', url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});

  let waited = 0, st = null;
  while (waited < 45000) {
    st = await page.eval(`(() => {
      const host = document.getElementById('extras');
      if(!host) return { host: false };
      const r = host.querySelector('[data-lensroot]');
      if(!r) return { host: true, root: false };
      const norm = e => (e ? e.innerText : '').replace(/\\s+/g, ' ').trim();
      return { host: true, root: true, len: norm(r).length,
        lens: norm(r),
        chart: !!host.querySelector('[data-lenschart]'),
        hist: !!host.querySelector('[data-lenshist]'),
        picks: host.querySelectorAll('[data-lenspick]').length,
        steps: !!host.querySelector('[data-lensstep]'),
      };
    })()`);
    if (st.root && st.len > 800) break;
    await sleep(1200);
    waited += 1200;
  }

  rec('L0 logit-lens 块渲染出来了（不是空壳）',
      !!(st && st.root && st.len > 800),
      st && st.root ? `正文 ${st.len} 字，等了 ${waited}ms；`
        + `chart=${st.chart} hist=${st.hist} 题目按钮 ${st.picks} 个 步滑块=${st.steps}`
        : `等了 ${waited}ms 仍无 [data-lensroot]`);

  // ---- L1：重建误差的量级必须现算，不能是手打的 ----
  // ⚠⚠ 第一版这条写的是「产物原文里不许出现 0.09」，**它本身是错的**：
  //   产物有 1536 个逐步 anchor_logit_err，其中一堆是 0.0905 / 0.09205 / 0.0944…
  //   ⇒ `/0\\.09/.test(raw)` 恒为真，于是这条判据永远红。
  //   真正该判的是：**页面上那个量级是不是由逐步字段算出来的**。
  //   顺带把真相记下来：原来的「约 0.09」离实测中位数差 13%（0.079 vs 0.09），
  //   所以它不只是没源，**也是错的**。
  const allErrs = [];
  for (const t of (L.trajectories || []))
    for (const stp of (t.steps || []))
      if (typeof stp.anchor_logit_err === 'number') allErrs.push(stp.anchor_logit_err);
  allErrs.sort((a, b) => a - b);
  const med = a => a.length
    ? (a.length % 2 ? a[(a.length - 1) / 2]
                    : (a[a.length / 2 - 1] + a[a.length / 2]) / 2) : null;
  const wantMed = med(allErrs), wantMax = allErrs[allErrs.length - 1];
  const missM = [];
  for (const t of (L.trajectories || []))
    for (const stp of (t.steps || []))
      if (stp.anchor_ok === false && typeof stp.real_margin === 'number')
        missM.push(stp.real_margin);
  missM.sort((a, b) => a - b);
  const wantMiss = med(missM);
  rec('L1 重建误差的量级必须由逐步 anchor_logit_err 现算（原来手打的 0.09 差 13%）',
      st.lens.includes(`中位数 <b>${wantMed}</b>`) || st.lens.includes(`中位数 ${wantMed}`),
      `产物现算：中位 ${wantMed} / 上界 ${wantMax}（${allErrs.length} 步）；`
      + `没中 ${missM.length} 步的 margin 中位 ${wantMiss}；`
      + `而原页面写的是「约 0.09」⇒ 离中位数差 `
      + `${(100 * (0.09 - wantMed) / wantMed).toFixed(1)}%`);

  // ---- L2：页面上界必须等于产物字段 ----
  const errTxt = (st.lens.match(/与记录的 logits 相比最大误差\s*([\d.]+)/) || [])[1] || null;
  rec('L2 页面印的「最大误差」必须等于 anchor.max_logit_error_vs_stored_topk',
      errTxt === String(L.anchor.max_logit_error_vs_stored_topk),
      `页面印「${errTxt}」；产物 anchor.max_logit_error_vs_stored_topk = `
      + `${L.anchor.max_logit_error_vs_stored_topk}`);

  // ---- L3：层号必须现算（LASTL 由 model.n_layers 推）----
  rec('L3 页面印的末层号必须等于 model.n_layers − 1',
      st.lens.includes(`第 ${LASTL} 层`) && st.lens.includes(`0–${LASTL} 层`),
      `期望「第 ${LASTL} 层」与「0–${LASTL} 层」；`
      + `页面 ${st.lens.includes(`第 ${LASTL} 层`) ? '有' : '无'} / `
      + `${st.lens.includes(`0–${LASTL} 层`) ? '有' : '无'}`);

  // ---- L4：判定口径必须逐字来自产物 definition ----
  rec('L4 可判定步的口径必须逐字来自产物 decidable_steps.definition',
      st.lens.includes(L.anchor.decidable_steps.definition),
      st.lens.includes(L.anchor.decidable_steps.definition)
        ? `找到「${L.anchor.decidable_steps.definition}」`
        : `没找到；产物 definition = 「${L.anchor.decidable_steps.definition}」`);

  // ---- L5：峰值必须等于 counts 的 argmax ----
  // 这一条第二十五笔是**真红**过的：页面写死「L20–L21」，实测 argmax = 21。
  const mPeak = st.lens.match(/峰值在\s*L(\d+)/);
  const shownPeak = mPeak ? Number(mPeak[1]) : null;
  rec('L5 页面印的峰值层必须等于 first_layer_correct_hist.counts 的 argmax',
      shownPeak === PEAK,
      `页面印 L${shownPeak}；counts argmax = ${PEAK}`
      + `（邻域 c[${PEAK - 1}]=${c[PEAK - 1]}, c[${PEAK}]=${c[PEAK]}, c[${PEAK + 1}]=${c[PEAK + 1]}）`);

  // ---- L6：累计百分比必须与口径一一对应 ----
  // 「L{k} 前」= c.slice(0,k) 之和。上一版那个 cum 是全部层之和却标成「L27 前」。
  const LASTC = c.length - 1;
  const want = `L${PEAK} 前 ${pct(cumTo(PEAK))}%、L${PEAK + 1} 前 ${pct(cumTo(PEAK + 1))}%`
    + `、到最后一层（L${LASTC}）为止 ${pct(cumAll)}%`;
  // ⚠⚠ 这条判红过两次，两次都是**空格**，不是数字：
  //   第一版期望串拼成一行，而页面模板串中间有换行 + 缩进 ⇒ `includes` 必然不命中；
  //   第二版把空白压成**一个**空格，可页面那个换行正好落在「、」后面
  //   ⇒ 压完是「71%、 到最后…」，而期望串里是「71%、到最后…」⇒ 还是不命中。
  // ⇒ 两侧都**去掉全部空白**再比：这句要核的是标签与数字，不是排版。
  //   （排版归排版判据管，判数值时把排版当噪声是不对的，但当**障碍**同样不对。）
  const flat = x => x.replace(/\s+/g, '');
  rec('L6 三个累计百分比必须分别等于 cum(0..k-1) / cum(全部)，且标签与口径对齐',
      flat(st.lens).includes(flat(want)),
      flat(st.lens).includes(flat(want)) ? `找到「${want}」`
        : `没找到；期望「${want}」；页面实际是「${
            (st.lens.match(/峰值在.{0,100}/) || ['（无）'])[0]}」`);

  // ---- L7：never_correct 那一行的层数必须用 counts.length ----
  rec('L7 「N 层全都没说对」里的 N 必须等于 counts.length',
      st.lens.includes(`${c.length} 层全都没说对`),
      st.lens.includes(`${c.length} 层全都没说对`)
        ? `找到「${c.length} 层全都没说对」`
        : `没找到；期望「${c.length} 层全都没说对」`);

  // ---- L8：源码层不许再出现那六个写死值 ----
  // ⚠⚠ 第三轮同款：这一条原来直接扫源码，于是扫到了**我自己写的注释**
  //   （「上一版那个 cum 是全部层之和却标成 L27 前」那两行）。
  //   判据要防的是「有人把那句话重新打进会印出去的字符串」，
  //   不是「源码里不许提到这件事」⇒ 剥注释再扫。
  const pageSrc = stripJsComments(readFileSync(SRC, 'utf8'));
  const leftovers = [];
  if (/峰值在 <b style="color:#3ddc97">L\d+–L\d+<\/b>/.test(pageSrc)) leftovers.push('写死的峰值区间');
  if (/L27 前/.test(pageSrc)) leftovers.push('写死的「L27 前」');
  if (/这批是 16k 采集的数据/.test(pageSrc)) leftovers.push('写死的「16k 采集」');
  rec('L8 页面源码里不许再出现那几处写死文案（判据要在能翻转的方向上）',
      leftovers.length === 0,
      leftovers.length ? '仍有：' + leftovers.join('、') : '三处都已改成现算或明说未记录');

  // ---- 兜底：块内不许有 undefined / NaN ----
  const junk = ['undefined', 'NaN', '[object Object]'].filter(t => st.lens.includes(t));
  rec('L9 块内不许出现 undefined / NaN / [object Object]',
      junk.length === 0,
      junk.length ? '出现：' + junk.join('、') : `正文 ${st.len} 字，扫过一遍`);

  const errs = page.events
    .filter(e => (e.method === 'Runtime.consoleAPICalled' && e.params.type === 'error')
              || e.method === 'Runtime.exceptionThrown')
    .map(e => e.method === 'Runtime.exceptionThrown'
      ? 'exceptionThrown: ' + ((e.params.exceptionDetails || {}).exception || {}).description
      : (e.params.args || []).map(a => a.value ?? a.description ?? '').join(' '))
    .filter(t => t && !/favicon|Failed to load resource/i.test(t));
  rec('L10 块内不得有 console error 或未捕获异常'
      + '（页面全局兜底会吞掉 render 的异常，且不往 console 写）',
      errs.length === 0,
      `收 ${page.events.length} 条 CDP 事件、error/异常 ${errs.length} 条`
      + (errs.length ? '：' + errs.slice(0, 2).join(' | ') : ''));

  console.log('\n=== %d/%d passed ===', pass, total);
  rows.filter(r => !r[0]).forEach(r => console.log('FAIL: ' + r[1]));
  process.exitCode = (pass === total) ? 0 : 1;
} catch (e) {
  console.log('[FAIL] L 组脚本崩了：%s\n%s', e.message, e.stack);
  process.exitCode = 1;
} finally {
  try { await cdp.send('Browser.close'); } catch {}
  try { proc.kill(); } catch {}
}
