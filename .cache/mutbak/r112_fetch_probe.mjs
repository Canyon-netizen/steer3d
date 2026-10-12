// r112_fetch_probe.mjs —— 修订 112
//
// 目的：待办里挂了很久的一条 ——「面板 fetch 是否失败」。
//   它挂着的理由记在预登记里是「FilePanel 两次 275 s 超时」，
//   ⚠ 而**空结果当时没敢报成「无失败」** —— 这个悬案必须结掉。
//   修订 101 已证明：实点通道受阻时可以自带 headless Chrome 走 CDP。
//
// ⚠⚠ 本脚本的核心纪律：**「0 失败」必须先自证它能报出 1 次失败。**
//   否则「没抓到失败」与「仪器瞎了」在输出上一模一样。
//   ⇒ 内置阴性对照：在页面里故意 fetch 一个不存在的路径，
//     要求探针**必须**把它记成失败。记不到 ⇒ 整个结论作废。
//
// 两个对照都写死：
//   阳性对照：必须观测到 ≥1 个 `data/*.json` 200 ⇒ 证明网络事件确实被捕获
//   阴性对照：必须观测到不存在的探测路径 404 ⇒ 证明仪器能报失败
//
// ⚠ 只写文件、不把几十万字打进上下文；正文只印统计与异常清单。

import { launch, Page, CDP } from '/Users/zhourui/code/steer3d/.cache/browser_verify/cdp_client.mjs';
import { writeFileSync } from 'node:fs';

const URL = process.env.BV_URL || 'http://127.0.0.1:9005/';
const OUT = process.env.BV_OUT || '/Users/zhourui/code/steer3d/.cache/mutbak/r112_fetch_events.json';
const SETTLE = Number(process.env.BV_SETTLE || 14000);
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_r112_' + process.pid;

// 阴性对照用的假路径：带时间戳，确保任何缓存都不可能命中
const NEG = 'data/__r112_negctl_' + process.pid + '.json';

const die = (m) => { console.log('[对照失败] ' + m); process.exit(2); };
const sleep = ms => new Promise(r => setTimeout(r, ms));

const { proc, version } = await launch({
  port: 9491, userDataDir: PROFILE, windowSize: '1700,4000', url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
try {
  // ⚠ Network 必须**在导航之前**打开，否则漏掉首屏的请求
  await page.send('Network.enable');
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 60000).catch(() => {});
  await sleep(SETTLE);

  // ---- 阴性对照：故意制造一次失败 ----
  const negStatus = await page.eval(`(async () => {
    try { const r = await fetch('${NEG}'); return r.status; }
    catch (e) { return 'threw:' + e.name; }
  })()`);
  await sleep(1200);   // 等 Network 事件回填

  // ---- 页面自曝的错误文案（第二路证据，与网络事件独立）----
  // ⚠⚠ 第一版用 `document.querySelectorAll('*')` 逐元素读 `innerText`，
  //   而 `<script>` 未被渲染 ⇒ 规范规定此时 `innerText` **退回 `textContent`**
  //   ⇒ 把 Next 的 RSC 载荷 `self.__next_f.push([1,"2:I[1438…` 当成了「页面文案」。
  //   ⚠ 那不是页面缺陷，是**仪器污染**。⇒ 必须跳过不可渲染元素。
  //
  // ⚠⚴ 但「跳过更多元素」会**削弱检测器**，而削弱后的检测器报 0 是最危险的形态。
  //   ⇒ 第三道对照：先往页面里注入一条**真的**错误文案，
  //     要求扫描器**必须**抓到它；抓不到 ⇒ 这一路的「0 条」是空的，不得发布。
  const dom = await page.eval(`(() => {
    const RE = /读不到|载入中|加载中|Failed to fetch|Unexpected token|(^|[^.\d])404($|[^.\d])|(^|[^.\w])NaN($|[^.\w])|(^|[^\w])undefined($|[^\w])/;
    const SKIP = new Set(['SCRIPT','STYLE','NOSCRIPT','TEMPLATE']);
    const probe = document.createElement('div');
    probe.id = '__r112_domctl__';
    probe.textContent = '面板读不到数据（自证用，请忽略）';
    document.body.appendChild(probe);
    const bad = [];
    for (const e of document.body.querySelectorAll('*')) {
      if (SKIP.has(e.tagName)) continue;
      if (e.querySelector('script,style,noscript,template')) continue;  // 祖先里裹着载荷的也不取
      const t = (e.innerText || '');
      if (!t || t.length > 4000) continue;
      if (RE.test(t)) bad.push(t.replace(/\\s+/g, ' ').slice(0, 160));
    }
    const caught = bad.some(x => x.includes('__r112_domctl__') || x.includes('自证用'));
    probe.remove();
    return JSON.stringify({
      bodyLen: (document.body.innerText || '').length,
      pageHeight: document.body.scrollHeight,
      title: document.title,
      domControlCaught: caught,
      bad: [...new Set(bad)].filter(x => !x.includes('自证用')).slice(0, 40),
    });
  })()`);
  const D = JSON.parse(dom);

  // ---- 汇总网络事件 ----
  const reqUrl = new Map();
  const responses = [];
  const failed = [];
  for (const ev of page.events) {
    if (ev.method === 'Network.requestWillBeSent') {
      reqUrl.set(ev.params.requestId, ev.params.request.url);
    } else if (ev.method === 'Network.responseReceived') {
      const u = ev.params.response.url;
      responses.push({ url: u, status: ev.params.response.status,
                       mime: ev.params.response.mimeType, type: ev.params.type });
    } else if (ev.method === 'Network.loadingFailed') {
      failed.push({ url: reqUrl.get(ev.params.requestId) || '(未知 requestId)',
                    error: ev.params.errorText, type: ev.params.type });
    }
  }
  const exceptions = page.events
    .filter(e => e.method === 'Runtime.exceptionThrown')
    .map(e => (e.params.exceptionDetails?.exception?.description
             || e.params.exceptionDetails?.text || '').slice(0, 200));
  const consoleErr = page.events
    .filter(e => e.method === 'Runtime.consoleAPICalled' && e.params.type === 'error')
    .map(e => e.params.args.map(a => a.value ?? a.description ?? '').join(' ').slice(0, 200));

  writeFileSync(OUT, JSON.stringify({ url: URL, settleMs: SETTLE, responses, failed,
                                      exceptions, consoleErr, dom: D }, null, 2), 'utf8');

  const json200 = responses.filter(r => /\.json(\?|$)/.test(r.url) && r.status === 200);
  const jsonBad = responses.filter(r => /\.json(\?|$)/.test(r.url) && r.status !== 200);
  const realFail = failed.filter(f => !String(f.url).includes('__r112_negctl_'));

  console.log('页面：' + URL);
  console.log('  整页可见文案 ' + D.bodyLen + ' 字符 / 页面高 ' + D.pageHeight + 'px / title=' + D.title);
  console.log('  事件：响应 ' + responses.length + ' / 加载失败 ' + failed.length +
              ' / 异常 ' + exceptions.length + ' / console.error ' + consoleErr.length);
  console.log('  json 200：' + json200.length + ' 个；json 非 200：' + jsonBad.length + ' 个');
  console.log('  完整事件已写出 ' + OUT);

  // ================= 阳性对照 =================
  if (json200.length < 1) die('阳性对照失败：一个 data/*.json 200 都没观测到 ⇒ 网络捕获是瞎的');
  console.log('\n[阳性对照 ✓] 观测到 ' + json200.length + ' 个 json 200 ⇒ 捕获通道有效');

  // ================= 阴性对照 =================
  const negSeen = responses.some(r => r.url.includes('__r112_negctl_')) ||
                  failed.some(f => String(f.url).includes('__r112_negctl_'));
  const negFailed = failed.some(f => String(f.url).includes('__r112_negctl_'));
  const negStatusSeen = responses.some(r => r.url.includes('__r112_negctl_') && r.status >= 400);
  if (!negSeen || !(negFailed || negStatusSeen)) {
    die('阴性对照失败：故意制造的失败（' + NEG + '，页面侧返回 ' + negStatus +
        '）探针没记下来 ⇒ 本仪器报不出失败，「0 失败」是空的');
  }
  console.log('[阴性对照 ✓] 故意制造的失败被记下（页面侧 status=' + negStatus +
              '，探针记 ' + (negFailed ? 'loadingFailed' : 'HTTP 4xx/5xx') +
              '）⇒ 「0 失败」不是瞎报');

  // ================= 第三道对照：DOM 扫描器自身有牙齿吗 =================
  if (!D.domControlCaught) {
    die('DOM 对照失败：注入的「读不到数据」没被抓到 ⇒ 这一路的「0 条」是空的，不得发布');
  }
  console.log('[DOM 对照 ✓] 注入的错误文案被抓到 ⇒ DOM 扫描器报得出「不是干净」');

  // ================= 正文结论 =================
  console.log('\n=== 真实失败（已剔除阴性对照那一条）===');
  if (!realFail.length) console.log('  0 个');
  for (const f of realFail) console.log('  ' + f.type + '  ' + f.error + '  ' + f.url);
  console.log('\n=== json 非 200 ===');
  if (!jsonBad.length) console.log('  0 个');
  for (const r of jsonBad) console.log('  ' + r.status + '  ' + r.url);
  console.log('\n=== 页面异常 ===');
  if (!exceptions.length) console.log('  0 个');
  for (const e of exceptions) console.log('  ' + e.replace(/\s+/g, ' '));
  console.log('\n=== console.error ===');
  if (!consoleErr.length) console.log('  0 个');
  for (const e of consoleErr) console.log('  ' + e.replace(/\s+/g, ' '));
  console.log('\n=== 页面自曝的疑似报错文案 ===');
  if (!D.bad.length) console.log('  0 条');
  for (const e of D.bad) console.log('  ' + e);
} catch (e) {
  die('装置错：' + String(e && e.message ? e.message : e));
} finally {
  try { await cdp.send('Browser.close'); } catch {}
  try { proc.kill(); } catch {}
}