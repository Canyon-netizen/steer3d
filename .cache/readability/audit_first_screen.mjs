// 可读性审计：在真实浏览器里量"读者实际能读到的文本"，不靠印象。
//
// 为什么放在 .cache/ 下、用 .cache/browser_verify/cdp_client.mjs 的 launch() 起
// 浏览器（它已经封装了 --single-process；手写启动器会漏 flag，Chromium 起不来）：
// 审计结论会被当验收证据，证据不能由被审对象自己产出。
//
// 可见性判据见 probe_lib.mjs 顶部（几何 + 裁剪 + 遮挡三重判据；遮挡用
// elementFromPoint 判定，否则导读层一开，浮层底下的页面文字会被算进"首屏"）。
// 阅读顺序 = DOM 顺序：本页是三列 grid（300px / 1fr / 320px），DOM 顺序即
// "左列由上到下 → 中列 → 右列"，与视觉阅读顺序一致。
//
// 用法：
//   node .cache/readability/audit_first_screen.mjs --tag=before
//   node .cache/readability/audit_first_screen.mjs --tag=after_app  --url=...?orient=off
//   node .cache/readability/audit_first_screen.mjs --tag=after_orient
// 术语表与锚点与 verify_readability.mjs 同源（都从实测的首屏文本里长出来的）。

import { launch, CDP, Page } from '../browser_verify/cdp_client.mjs';
import { writeFileSync, mkdirSync, readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import * as P from './probe_lib.mjs';

const ROOT = '/Users/zhourui/code/steer3d';
const OUT = '.cache/readability';
const argv = process.argv.slice(2);
const arg = (k, d) => {
  const hit = argv.find(a => a.startsWith('--' + k + '='));
  return hit ? hit.slice(k.length + 3) : d;
};
const TAG = arg('tag', 'run');
const URL = arg('url', 'http://localhost:8917/latent/index.html');
const PORT = 9360 + (TAG === 'before' ? 0 : TAG === 'after_app' ? 1 : 2);
const sleep = ms => new Promise(r => setTimeout(r, ms));
mkdirSync(`${ROOT}/${OUT}`, { recursive: true });

const bytes = readFileSync(`${ROOT}/frontend/public/latent/index.html`);
const HASH = createHash('sha256').update(bytes).digest('hex').slice(0, 16);

// 术语表：不懂 ML 的中文母语读者第一次看到会卡住的词（判据写在这里，不含糊）
const TERMS = [
  { t: 'token',    anchor: '模型一次写的一个词的碎片' },
  { t: '熵',        anchor: '模型有多犹豫' },
  { t: 'top1 概率', anchor: '排名第一的那个词有多大概率被选中' },
  { t: '候选词',    anchor: '模型此刻心里排队的字' },
  { t: '层',        anchor: '一次加工工序' },
  { t: '维度',      anchor: '一份状态里数字的个数' },
  { t: '投影',      anchor: '压成 2 个数字' },
  { t: 'PCA',      anchor: '最能解释差异的方向' },
  { t: 'PC1',      anchor: '它找到的前两根轴' },
  { t: 'PC2',      anchor: '它找到的前两根轴' },
  { t: 'embedding', anchor: '查表把词变成一串数字' },
  { t: '隐空间',    anchor: '模型脑子里那份' },
  { t: '残差流',    anchor: '新加上去的那部分' },
  { t: '残差',      anchor: '新加上去的那部分' },
  { t: '范数',      anchor: '草稿有多长' },
  { t: '干预',      anchor: '人为往草稿里推一把' },
  { t: '对照',      anchor: '什么都不做地跑一遍' },
  { t: '位移',      anchor: '被推了多远' },
  { t: 'logit',    anchor: '还没归一化的原始打分' },
  { t: 'block',    anchor: '一次加工工序' },
];

const call = (page, fn, ...args) =>
  page.eval('(' + fn.toString() + ')(' + args.map(a => JSON.stringify(a)).join(',') + ')');

const { proc, version } = await launch({
  port: PORT, userDataDir: `${ROOT}/${OUT}/profile_audit_${TAG}`, url: 'about:blank',
});
console.log(`[${TAG}] index.html sha256 ${HASH} | ${version.Browser} | ${URL}`);
const cdp = await CDP.connect(
  `ws://127.0.0.1:${PORT}/devtools/browser/${version.webSocketDebuggerUrl.split('/').pop()}`);
const page = await Page.create(cdp);
const exceptions = [];
cdp.on(m => {
  if (m.method === 'Runtime.exceptionThrown')
    exceptions.push(m.params.exceptionDetails?.exception?.description || m.params.exceptionDetails?.text);
});

await page.send('Storage.clearDataForOrigin',
  { origin: 'http://localhost:8917', storageTypes: 'local_storage' });
await page.nav(URL);
for (let i = 0; i < 160; i++) {
  const st = await page.eval(`(()=>({l:getComputedStyle(document.getElementById('loading')).display,
    a:getComputedStyle(document.getElementById('app')).visibility,
    r:document.querySelectorAll('#tblTop tr').length}))()`);
  if (st.l === 'none' && st.a === 'visible' && st.r > 0) break;
  await sleep(250);
}
await sleep(800);

const { blocks, vw, vh, dpr } = await call(page, P.collectVisible, null);
const expl = await call(page, P.collectExplanatory);
const overflow = await call(page, P.layoutOverflow, '.panel,.col,.wrap');
const bleed = await call(page, P.horizontalBleed);
const po = await call(page, P.pageOverflow);

// 句长分布：中文句末标点切句；只数"说明性文字"，数据载荷（题面/生成文本/候选词表）
// 不算散文，所以不参与。
function splitSentences(items) {
  const out = [];
  for (const it of items) {
    for (const raw of it.text.split(/[。！？；\n]+/)) {
      const t = raw.trim();
      if (!t) continue;
      const zh = (t.match(/[一-鿿]/g) || []).length;
      if (zh < 4) continue;
      out.push({ n: t.length, zh, text: t, from: it.sel });
    }
  }
  return out;
}
// 页面本体文案（不含导读层）与导读层文案分开统计
const appExpl = expl.filter(e => !e.inOrient);
const orientExpl = expl.filter(e => e.inOrient);
const stat = list => {
  const s = splitSentences(list).map(x => x.n).sort((a, b) => a - b);
  if (!s.length) return { count: 0, median: 0, max: 0 };
  const med = s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2;
  const longs = splitSentences(list).sort((a, b) => b.n - a.n);
  return { count: s.length, median: med, max: longs[0].n, longestText: longs[0].text,
           longestFrom: longs[0].from, over40: s.filter(x => x > 40).length };
};

// 术语覆盖：首屏出现 + 该处所在说明容器里有没有白话解释
const termRows = TERMS.map(({ t, anchor }) => {
  const b = blocks.find(x => x.ctx.includes(t));
  return {
    term: t, anchor,
    onScreen: !!b,
    at: b ? `${b.sel} @(${b.x},${b.y})` : '',
    inContext: b ? b.ctxSel : '',
    explainedHere: b ? b.ctx.includes(anchor) : false,
  };
});

const report = {
  tag: TAG, url: URL, indexSha: HASH, browser: version.Browser, viewport: `${vw}x${vh}`, dpr,
  visibleBlockCount: blocks.length,
  visibleText: blocks.map(b => `[${b.i}] ${b.sel} @(${b.x},${b.y})  ${b.text}`),
  sentences: { app: stat(appExpl), orientation: stat(orientExpl) },
  terms: termRows,
  termsExplained: termRows.filter(r => r.explainedHere).length,
  termsOnScreen: termRows.filter(r => r.onScreen).length,
  layout: {
    pageVOver: po.vOver, pageHOver: po.hOver,
    panelMaxVOver: Math.max(0, ...overflow.map(x => x.vOver)),
    panelMaxHOver: Math.max(0, ...overflow.map(x => Math.max(x.hOverVsParent, x.hOverSelf))),
    hOver: overflow.filter(x => x.vOver > 0 || x.hOverVsParent > 1 || x.hOverSelf > 1)
      .map(x => `${x.sel} vOver=${x.vOver} hSelf=${x.hOverSelf} hParent=${x.hOverVsParent}`),
    bleed,
  },
};
writeFileSync(`${ROOT}/${OUT}/audit_${TAG}.json`, JSON.stringify(report, null, 2));

console.log(`\n=== [${TAG}] 首屏可见文本块 ${blocks.length} 个（视口 ${vw}x${vh}） ===`);
blocks.forEach(b => console.log(`[${b.i}] ${b.sel} @(${b.x},${b.y})  ${b.text}`));
const A = report.sentences.app, O = report.sentences.orientation;
console.log(`\n=== [${TAG}] 说明性句长 ===`);
console.log(`  页面本体: ${A.count} 句 | 中位数 ${A.median} 字 | 最长 ${A.max} 字 | >40字 ${A.over40} 句`);
if (A.longestText) console.log(`     最长句(${A.longestFrom}): ${A.longestText}`);
if (O.count) {
  console.log(`  导读层  : ${O.count} 句 | 中位数 ${O.median} 字 | 最长 ${O.max} 字 | >40字 ${O.over40} 句`);
  console.log(`     最长句(${O.longestFrom}): ${O.longestText}`);
}
console.log(`\n=== [${TAG}] 术语覆盖：首屏出现 ${report.termsOnScreen}/${TERMS.length}，` +
            `在首屏就地带解释 ${report.termsExplained} ===`);
console.log('术语          首屏  就地解释  所在容器');
for (const r of termRows)
  console.log(r.term.padEnd(12, '　') + (r.onScreen ? '是' : '否').padEnd(5, ' ') +
              (r.explainedHere ? '是' : '否').padEnd(9, ' ') + (r.inContext || r.at));
console.log(`\n=== [${TAG}] 布局实测 ===`);
console.log(`  页面级 scrollHeight-clientHeight = ${po.vOver} | scrollWidth-clientWidth = ${po.hOver}`);
console.log(`  panel 最大纵向溢出 = ${report.layout.panelMaxVOver} | 最大横向越界 = ${report.layout.panelMaxHOver}`);
console.log(`  横向越界元素 ${bleed.length} 处` + (bleed.length ? '：' + JSON.stringify(bleed.slice(0, 3)) : ''));
if (exceptions.length) console.log('\n!! page exceptions:', exceptions.slice(0, 3));
page.close(); cdp.close(); proc.kill('SIGKILL');
console.log(`\nwritten: ${OUT}/audit_${TAG}.json`);
