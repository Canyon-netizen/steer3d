import { launch, Page, CDP } from './cdp_client.mjs';
import { readFileSync } from 'fs';

/**
 * 第二十四笔 X 组：**latent 页上那三块解释的散文，数字与句子从哪来。**
 *
 * ## 这一组存在的理由
 *
 * 第二十三笔把 `data-cotblock` / `data-aroot` / `data-cottext` 从
 * `drawDeltaSide()` 搬进 `#extras` 之后，它们第一次出现在默认视图里 ——
 * 于是 C4 立刻多出 24 个「渲染了但没有任何判据读过」的标记，
 * 其中这三个块的散文合计上万字，**承载判决的数字一个都没有判据**。
 *
 * 搬出来 ≠ 有人核。这一组就是来核它们的。
 *
 * ## 判据主体必须在**渲染层**
 *
 * 因为要防的正是「块在页面上、字也在页面上，但那些字是手打的」。
 * 只扫源码抓不到：源码里 `data-cot*` / `data-ar*` 一个都不少，
 * 而手打的字面量读起来和现算的字面量在源码里长得一模一样。
 *
 * ## 本组要防的具体三处（都是第二十四笔当场查出来的）
 *
 *   X4  「答对数的净变化是 0」原来是一个**写死的常数 0**
 *       —— 它恰好是真的，所以「核这个数对不对」永远查不出问题，
 *          核的是常数本身。
 *   X6  题库自述的中文转述把 "answers verified" 整句丢了
 *       ⇒ 读者看到的题库自述比题库自己的自述**更弱**。
 *   X7  「答案在 0–999 内」在两个生成脚本里是两种措辞、页面上是第三份。
 *
 * ## 本组不能证明什么
 *
 * 判据核的是「页面印的 = 产物字段的」。它**不核产物本身对不对**
 * —— 那是产物层判据的事。两者要分开记账。
 */
const URL = process.env.LAT_URL || 'http://127.0.0.1:22113/latent/index.html';
const DATA = '/Users/zhourui/code/steer3d/frontend/public/latent/data/';
const SRC = '/Users/zhourui/code/steer3d/frontend/public/latent/index.html';
const LOADER = '/Users/zhourui/code/steer3d/backend/core/aime_loader.py';
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_x_' + process.pid;
const sleep = ms => new Promise(r => setTimeout(r, ms));

const rows = [];
let pass = 0, total = 0;
function rec(name, ok, detail) {
  total++; if (ok) pass++;
  rows.push([ok, name, detail]);
  console.log('[%s] %s\n       %s', ok ? 'PASS' : 'FAIL', name, detail);
}
/**
 * 剥掉 **Python** 的注释（`#` 到行尾、以及三引号块）。
 *
 * ## 为什么 X8 需要另一个剥法
 *
 * 我第一版对 `build_cot_effect.py` 用了上面的 **JS** 剥注释器 ——
 * 而那两个生成脚本是 Python，`#` 注释它根本不处理。
 * 于是 X8 抓到的「手抄」是第 73–76 行那段**溯源论证**：
 *
 *     #   "inspired by AIME 1983-2024 problems. Re-worded but mathematically
 *     #    faithful; answers verified."
 *
 * 那段注释在解释「题库就是源头」这条链，**有解释价值，不该为了让判据绿而删掉**。
 * ⇒ 一个文件一种语言就要用对应的那把刀。把 JS 的刀用在 .py 上，
 *   判据看起来在扫、其实一行 Python 注释都没剥。
 *
 * ⚠ `#` 也要避开字符串内部的（`"a # b"`），所以带引号状态。
 * ⚠ 三引号块按注释处理：本文件里那些是 docstring / 说明块，
 *   同样不是会印出去的字符串。
 */
function stripPyComments(src) {
  const lines = src.split('\n');
  const out = [];
  let inTriple = null;
  for (let line of lines) {
    if (inTriple) {
      if (line.includes(inTriple)) inTriple = null;
      continue;
    }
    const t = line.match(/("""|''')/);
    if (t && !stripHashOutsideQuotes(line.slice(0, line.indexOf(t[1])))) {
      inTriple = t[1];
      continue;
    }
    out.push(stripHashOutsideQuotes(line));
  }
  return out.join('\n');
}
function stripHashOutsideQuotes(line) {
  let q = null;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (q) {
      if (c === '\\') { i++; continue; }
      if (c === q) q = null;
      continue;
    }
    if (c === '"' || c === "'") { q = c; continue; }
    if (c === '#') return line.slice(0, i);
  }
  return line;
}

const j = f => JSON.parse(readFileSync(DATA + f, 'utf8'));

/**
 * 剥掉 JS 注释，保留字符串字面量的**内容**。
 *
 * ## 为什么 X8 / X9 第一版会假红
 *
 * X8 扫 `build_cot_effect.py` 里的 `0–999`，扫到的是一段**注释**：
 *   “The 0-999 in-domain filter has the same shape of problem: …”
 * X9 扫 `index.html` 里的「受 AIME 1983-2024 启发」，扫到的是我**自己**
 * 写的那段交代来历的注释：
 *   //   「受 AIME 1983-2024 启发、改写过但数学上忠实」——
 *
 * ⇒ 两段注释都**有解释价值，不该为了让判据变绿而删掉**。
 *   判据要防的是「有人把那句话重新打进会印出去的字符串」，
 *   不是「源码里不许提到这件事」。
 *   （同族：第二十二笔的「判据扫源码先剥注释」、
 *     第二十三笔的「判据自己也是源码，扫它同样要先剥注释」。）
 *
 * ⚠ `//` 前面是 `:` 时不算注释头 —— 否则 `http://` 会被切掉一整行。
 */
function stripJsComments(src) {
  let out = '', i = 0;
  const n = src.length;
  while (i < n) {
    const c = src[i];
    if (c === '/' && src[i + 1] === '/' && src[i - 1] !== ':') {
      const j2 = src.indexOf('\n', i);
      i = j2 < 0 ? n : j2;
      continue;
    }
    if (c === '/' && src[i + 1] === '*') {
      const j2 = src.indexOf('*/', i + 2);
      i = j2 < 0 ? n : j2 + 2;
      continue;
    }
    if (c === '"' || c === "'" || c === '`') {
      const q = c, start = i;
      i++;
      while (i < n) {
        if (src[i] === '\\') { i += 2; continue; }
        if (src[i] === q) { i++; break; }
        i++;
      }
      out += src.slice(start, i);   // 字面量内容原样保留
      continue;
    }
    out += c; i++;
  }
  return out;
}

// ---------- 装置事故前置：连不上就不报 N/M ----------
let reach = null;
try {
  reach = await fetch(URL, { method: 'GET' });
} catch (e) { /* 下面统一处理 */ }
if (!reach || !reach.ok) {
  console.log('[FAIL] X0 页面不可达 ⇒ **装置事故，不是被测物判红**');
  console.log(`       URL = ${URL}  状态 = ${reach ? reach.status : '连不上'}`);
  console.log('       下面 10 条一条都没执行 ⇒ **不报 N/M**（报 0/10 会让「没跑」');
  console.log('       在汇总里长得像「跑了而且全红」），退出码 4。');
  console.log(`\n=== unreached (LAT_URL=${URL}) ===`);
  process.exit(4);
}

const ans = j('answer_readout.json');
const cot = j('cot_effect_32k.json');

// 产物层的期望值：从被测物自己的字段现算，不写死
const bv = ans.selection.by_verdict || {};
const N = k => (bv[k] == null ? null : Number(bv[k]));
const wantNet = (-(N('right->wrong') || 0) + (N('wrong->right') || 0)
                 + (N('right->right') || 0) * 0 + (N('wrong->wrong') || 0) * 0);
const wantSum = ['right->wrong', 'wrong->right', 'right->right', 'wrong->wrong']
  .reduce((a, k) => a + (N(k) || 0), 0);
const wantNElig = Number(ans.selection.n_eligible);

const { proc, version } = await launch({
  port: 9700 + (process.pid % 90), userDataDir: PROFILE,
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
      const norm = s => { const e = host.querySelector(s);
        return e ? (e.innerText || '').replace(/\\s+/g, ' ').trim() : null; };
      return { host: true,
        ar: norm('[data-aroot]') || '',
        cotb: norm('[data-cotblock]') || '',
        // ⚠ 第三十三笔之二：这一块（2141 字，「这个向量到底在做什么」）
        //   **早就在 #extras 里**（renderExtras → renderVectorRoles），
        //   缺的只是本文件的选择器名单里没有它 ⇒ 它整整 2141 字零判据覆盖。
        //   与探针 roots、C4 口径同属「名单写死」的第三例。
        roles: norm('[data-rolesroot]') || '',
        ps: [...host.querySelectorAll('[data-problemset]')]
              .map(e => ({ where: e.getAttribute('data-problemset'),
                           txt: (e.innerText || '').replace(/\\s+/g, ' ').trim() })),
        // ---- 第三十三笔之三：「本页不主张的 4 种说法」那块（判决性）----
        // ⚠⚠ **它不在 #extras 里**。它在 #orientation 浮层内（index.html:245 起），
        //    而 #orientation 初始 class="hide"、CSS 是 .hide{display:none!important}。
        //    ⇒ 上面那个 host 作用域的 norm() 读它必然读到 null。
        //    这是「作用域/名单写死」这一族的**第四例**（前三：探针 roots、C4 口径、
        //    本文件的 norm() 名单）。修法同前：不写名单，从 document 上问。
        // ⚠⚠ 这一段是**模板串**，所以上面这些 // 不是注释，是字符串内容。
        //    C2b 就是为这件事设的：模板串里带标记名的 // 会被提取成
        //    「判据读过的标记」⇒ 判据会拿到一份它其实没读过的引用。
        //    ⇒ 这里刻意不写那个标记名，真正的引用在下面的 querySelector 里。
        nc: (() => {
          const e = document.querySelector('[data-latent-not-claimed]');
          if(!e) return { found: false };
          const ov  = document.getElementById('orientation');
          const ne  = document.querySelector('[data-f="neff"]');
          const txt = s => ((s||'') + '').replace(/\\s+/g, ' ').trim();
          return {
            found: true,
            /* 可见性：判据主体必须是**读者看得见**的文案。
               首次访问 orientAuto 会自动弹出（localStorage 空 ⇒ orientRead() 假），
               所以这里量的是「弹出来之后是不是真的 display 了」。 */
            orientInDom: !!ov,
            orientHiddenClass: ov ? ov.classList.contains('hide') : null,
            orientDisplay: ov ? getComputedStyle(ov).display : null,
            orientVisibility: ov ? getComputedStyle(ov).visibility : null,
            /* 这一段的框：宽高非 0 才说明它真的参与了布局（不是被压成 0 的隐藏块） */
            rect: (() => { const r = e.getBoundingClientRect();
                           return { w: Math.round(r.width), h: Math.round(r.height) }; })(),
            inExtras: !!(document.getElementById('extras') || {}).contains
                        ? document.getElementById('extras').contains(e) : false,
            noitems: [...document.querySelectorAll('.noitem')].map(n => txt(n.innerText)),
            /* 标题自称「4 种说法」——那个 4 是手打的中文数字，必须与 DOM 里的条数对上 */
            h2Text: txt([...document.querySelectorAll('h2')]
                          .filter(h => h.innerText.includes('不主张'))
                          .map(h => h.innerText)[0]),
            neffText: ne ? txt(ne.textContent) : null,
            /* 紧跟在 neff 槽后面的那截文字 —— 「个」在这里就是在钉读法 */
            neffNext: (ne && ne.nextSibling) ? txt(ne.nextSibling.textContent) : null,
            retText: txt((document.querySelector('[data-f="ret"]')||{}).textContent),
            dText:   txt((document.querySelector('[data-f="d"]')||{}).textContent),
            labelText: txt((document.querySelector('[data-f="label"]')||{}).textContent),
            /* 运行时启动信号：trace() 写进 #dbg，静态文案证明不了 boot 跑过 */
            dbgTail: txt((document.getElementById('dbg')||{}).textContent).slice(-60),
            modelId: (typeof S !== 'undefined' && S.model) ? S.model.id : null,
          };
        })(),
      };
    })()`);
    if (st.host && st.ar.length > 500) break;
    await sleep(1200);
    waited += 1200;
  }

  rec('X0 #extras 已就绪（不是空壳），等待 ' + waited + 'ms',
      !!(st && st.ar && st.ar.length > 500),
      st ? `data-aroot ${st.ar.length} 字 / data-cotblock ${st.cotb.length} 字` : '没读到');

  // ---- X4：净变化必须是现算的，且等于 by_verdict 推出来的值 ----
  // ⚠ 判据不能只核「页面上写着 0」—— 那正是常数。要核的是
  //   「页面印的数 == 由 selection.by_verdict 现算的数」。
  const mNet = st.ar.match(/净变化是\s*([^\s，。]+)/);
  const printedNet = mNet ? mNet[1] : null;
  rec('X1 页面印的「答对数净变化」必须等于由 selection.by_verdict 现算的值',
      printedNet === String(wantNet),
      `页面印「${printedNet}」；by_verdict 现算 = `
      + `−${N('right->wrong') || 0} + ${N('wrong->right') || 0} = ${wantNet}`);

  // ---- X2：by_verdict 四类之和必须等于 n_eligible（分母自洽）----
  rec('X2 by_verdict 四类之和必须等于 n_eligible（不然现算的分母不成立）',
      wantSum === wantNElig,
      `${JSON.stringify(bv)} 合计 ${wantSum} vs n_eligible ${wantNElig}`);

  // ---- X3：页面必须把四类的数都印出来（可回推）----
  // ⚠ 缺项按 0 计，**不是**按「—」：产物只列非零项，
  //   键不存在就是 0（X2 的「四类之和 == n_eligible」已经独立确认了这一点）。
  //   我第一版期望「两边都对 —」，页面印的也是「—」，判据是绿的 ——
  //   但那样净变化的 −1+1 里就有一个「不知道是 0 还是没量」的项。
  const CATS = ['right->wrong', 'wrong->right', 'right->right', 'wrong->wrong'];
  const miss = CATS.filter(k => bv[k] == null);
  const wantParts = `原对变错 ${N('right->wrong') ?? 0}、`
    + `原错变对 ${N('wrong->right') ?? 0}、`
    + `两边都对 ${N('right->right') ?? 0}、`
    + `两边都错 ${N('wrong->wrong') ?? 0}`
    + (miss.length ? `；产物只列非零项，缺项 ${miss.length} 个按 0 计` : '');
  rec('X3 页面必须把 by_verdict 的四类逐项印出（净变化要能被回推，缺项按 0 计）',
      st.ar.includes(wantParts),
      st.ar.includes(wantParts) ? `找到「${wantParts}」`
        : `没找到；页面上是「${
            (st.ar.match(/.{0,30}原对变错.{0,80}/) || ['（无）'])[0]}」`);

  // ---- X6：题库自述必须**照抄产物字段**，不许是中文转述 ----
  // 判据主体是页面印的字：要求它逐字包含产物的英文字段。
  const wantSelf = ans.problem_set.loader_self_description;
  const cotSelf = cot.problem_set.loader_self_description;
  const selfOnPage = st.ps.some(p => p.txt.includes(wantSelf));
  rec('X4 题库自述必须逐字照抄产物字段（中文转述会把 "answers verified" 丢掉）',
      selfOnPage,
      selfOnPage ? `页面逐字含「${wantSelf.slice(0, 58)}…」`
        : `${st.ps.length} 个 data-problemset 里都没有产物原文；`
          + `转述会丢掉「answers verified」`);

  // ---- X7：答案域约定必须与产物逐字相同，且两份产物之间也要相同 ----
  const wantRule = ans.problem_set.answer_domain_rule;
  const ruleOnPage = st.ps.some(p => p.txt.includes(wantRule));
  const twoArtifactsAgree = wantRule === cot.problem_set.answer_domain_rule;
  rec('X5 答案域约定必须逐字照抄产物，且两份产物的措辞必须相同',
      ruleOnPage && twoArtifactsAgree,
      `页面命中=${ruleOnPage}；answer_readout == cot_effect_32k → ${twoArtifactsAgree}；`
      + `原文「${wantRule}」`);

  // ---- X6 变体：两份产物的题库自述也必须逐字相同 ----
  rec('X6 两份产物的 loader_self_description 必须逐字相同（否则「自述」有两份）',
      wantSelf === cotSelf,
      `answer_readout「${wantSelf}」\n       cot_effect_32k「${cotSelf}」`);

  // ---- 源码层：源头必须只有一处 ----
  // 判据读哪一层要和它防的东西同层：X4/X5 在产物+渲染层，
  // 这一条在生成器源码层，防的是「有人又把那句英文抄回某个生成脚本」。
  const loaderSrc = readFileSync(LOADER, 'utf8');
  rec('X7 源头常量必须在 aime_loader.py 里（不在就说明它被搬走了）',
      /LOADER_SELF_DESCRIPTION\s*=/.test(loaderSrc)
      && /ANSWER_DOMAIN_RULE\s*=/.test(loaderSrc),
      `LOADER_SELF_DESCRIPTION 定义 ${(loaderSrc.match(/LOADER_SELF_DESCRIPTION\s*=/g) || []).length} 次，`
      + `ANSWER_DOMAIN_RULE 定义 ${(loaderSrc.match(/ANSWER_DOMAIN_RULE\s*=/g) || []).length} 次`);

  const gens = ['build_answer_readout.py', 'build_cot_effect.py'];
  const copyLeft = [];
  for (const g of gens) {
    // .py 用 **Python** 的刀剥注释（见 stripPyComments 上方：JS 的刀对 .py 无效）
    const body = stripPyComments(readFileSync(
      '/Users/zhourui/code/steer3d/backend/examples/' + g, 'utf8'))
      .split('\n').filter(l => !/aime_loader import/.test(l)
                             && !/^\s*(ANSWER_DOMAIN_RULE|LOADER_SELF_DESCRIPTION|_BUILTIN)\b/.test(l))
      .join('\n');
    if (/inspired by AIME/.test(body)) copyLeft.push(g);
    if (/0–999/.test(body)) copyLeft.push(g + ' (0–999)');
  }
  rec('X8 两个生成脚本里不许再手抄题库自述或答案域约定（import 与注释都不算）',
      copyLeft.length === 0,
      copyLeft.length ? '仍有手抄：' + copyLeft.join(', ')
        : `${gens.join(' / ')} 都只 import，不再手抄（.py 注释已剥）`);

  // ---- 页面源码层：散文里不许再出现那两句转述 ----
  const pageSrc = stripJsComments(readFileSync(SRC, 'utf8'));
  const transLeft = [];
  if (/受 AIME 1983-2024 启发/.test(pageSrc)) transLeft.push('题库自述转述');
  if (/页面里出现的「答案在 0–999 内」/.test(pageSrc)) transLeft.push('答案域约定转述');
  if (/净变化是 0[。；]/.test(pageSrc)) transLeft.push('写死的「净变化是 0」');
  rec('X9 页面源码里不许再出现那三句手打文案（注释已剥，判据要在能翻转的方向上）',
      transLeft.length === 0,
      transLeft.length ? '仍有：' + transLeft.join('、')
        : '三句都已改成读字段/现算');

  // ---- 兜底：这三块里不许出现 undefined / NaN / [object Object] ----
  const junk = ['undefined', 'NaN', '[object Object]']
    .filter(t => st.ar.includes(t) || st.cotb.includes(t));
  rec('X10 三块正文里不许出现 undefined / NaN / [object Object]',
      junk.length === 0,
      junk.length ? '出现：' + junk.join('、')
        : `data-aroot ${st.ar.length} 字 / data-cotblock ${st.cotb.length} 字，各扫过一遍`);

  // ==================================================================
  // Y 组（第三十三笔之二）：[data-rolesroot] —— 必要性/充分性/特异性
  // ==================================================================
  // ⚠ 这组存在的理由不是「补覆盖率」，而是**核一个已经抓到的缺陷**：
  //   `renderVectorRoles()` 原来只取 `sc[ks[0]]`（**第一折**），
  //   而 folds 里有**两个折**（fit0_score1 / fit1_score0，题目是不同半集）。
  //   ⇒ 页面上「ρ -0.655（n=33030）通过」会被读成
  //     「在 33030 步上 ρ=-0.655 且通过」，而真实是
  //     「两个半集上分别 -0.6553 与 -0.6845，**两折都**通过」。
  //   两折的差实测到 0.218（creativity 折0=+0.7441 / 折1=+0.5260），
  //   而 `ks[0]` 恰好是折0 ⇒ 页面**只印更乐观的那一折**。
  //   ⇒ 判据必须核「**每一折**的数都在页面上」，且核 `n` 分折。
  const RR = j('vector_roles.json');
  const NESS = RR.necessity || {};
  const FOLDS = (NESS.heldout_non_circular || {}).folds || {};
  const rt = st.roles || '';
  rec('Y0 [data-rolesroot] 必须在页面上且非空'
      + '（它曾因取错层级而整段静默不渲染）',
      rt.length > 500,
      `[data-rolesroot] ${rt.length} 字`
      + `　⚠ 之前它不在本文件的 norm() 里 ⇒ 2141 字零判据覆盖`
      + `（同一失败模式的第三例：探针 roots / C4 口径 / 本文件的 norm() 名单）`);

  const y1miss = [];
  for (const dir in FOLDS) {
    const sc = (FOLDS[dir] || {}).scores || {};
    for (const k of Object.keys(sc)) {
      const v = sc[k];
      // 页面：有 AUC 用 AUC 三个小数，没有用带符号的 ρ
      const want = (v.auc_within_traj != null)
        ? v.auc_within_traj.toFixed(3)
        : ((v.rho >= 0 ? '+' : '') + v.rho.toFixed(3));
      if (!rt.includes(want)) y1miss.push(`${dir}/${k}=${want}`);
    }
  }
  const nFoldAll = Object.values(FOLDS).map(d => Object.keys((d || {}).scores || {}).length);
  rec('Y1 留出法**每一折**的 ρ/AUC 都必须印在页面上（不许只印第一折）',
      y1miss.length === 0 && nFoldAll.every(n => n >= 2),
      y1miss.length
        ? `缺 ${y1miss.length} 个（两折的数差到 0.218，ks[0] 恰好是折0）：${y1miss.join('、')}`
        : `逐折命中；每方向折数=${[...new Set(nFoldAll)].join('/')}`);

  // n 必须分折印：两个半集的步数不同（33030 / 36125）
  const y2miss = [];
  for (const dir in FOLDS) {
    const sc = (FOLDS[dir] || {}).scores || {};
    for (const k of Object.keys(sc)) {
      const n = (sc[k] || {}).n_steps_scored;
      if (n == null) continue;
      if (!rt.includes(String(n))) y2miss.push(`${dir}/${k}=n:${n}`);
    }
  }
  rec('Y2 每一折的步数都必须印出来（n 是一个半集的步数，不是留出法总量）',
      y2miss.length === 0,
      y2miss.length ? `缺 ${y2miss.length} 个：${y2miss.join('、')}`
                    : `逐折命中；示例两折步数 `
                      + `${Object.values(FOLDS).map(d => Object.keys(d.scores).map(k => d.scores[k].n_steps_scored).join('/')).slice(0,2).join(' ｜ ')}`);

  // 门槛段：它取的是 random_direction_control[L20]（两层嵌套）
  const RCD = (NESS.random_direction_control || {}).L20 || {};
  const one = RCD[Object.keys(RCD)[0]] || {};
  const y3need = [
    ['n_random_directions', one.n_random_directions],
    ['random_min', one.random_min != null ? one.random_min.toFixed(3) : null],
    ['random_max', one.random_max != null ? one.random_max.toFixed(3) : null],
    ['empirical_floor_max_random', one.empirical_floor_max_random != null ? one.empirical_floor_max_random.toFixed(3) : null],
    ['naive_floor_1_over_sqrt_n_minus_3', one.naive_floor_1_over_sqrt_n_minus_3 != null ? one.naive_floor_1_over_sqrt_n_minus_3.toFixed(3) : null],
  ].filter(([, v]) => v != null);
  const y3miss = y3need.filter(([, v]) => !rt.includes(String(v))).map(([w]) => w);
  rec('Y3 门槛段的五个数必须逐个来自 random_direction_control[L20]'
      + '（它是两层嵌套，取错层会整段静默不渲染）',
      y3need.length === 5 && y3miss.length === 0,
      y3miss.length ? `缺：${y3miss.join('、')}`
                    : `逐个命中：${y3need.map(([, v]) => v).join(' / ')}`);

  // 源级：不许退回单折取法
  const rolesSrc = stripJsComments(readFileSync(SRC, 'utf8'));
  const singleFold = /sc\[ks\[0\]\]\s*\.\s*(n_steps_scored|rho|auc_within_traj|n_positive_steps)/.test(rolesSrc);
  rec('Y4 源级：渲染不许退回 `sc[ks[0]].…` 这种**只取第一折**的写法',
      !singleFold,
      singleFold ? '仍有一处按 ks[0] 取数 ⇒ 另一折的数不上页面'
                 : '两折都取（aucs/rhos/ns/nposs 四个数组）并都印');

  // ==================================================================
  // Z 组（第三十三笔之三）：[data-latent-not-claimed]
  //                     ——「本页不主张的 4 种说法」
  // ==================================================================
  // ## 这块在还什么账
  //
  // 56 字、**判决性**：它声明本页否掉了哪 4 种新手最自然的理解。
  // 「否掉了」是硬判决，每条后面都跟着「否掉的依据」。
  // C4 一直把它记在「页面上有、判据没读过」的账上（第四例的同一块）。
  //
  // ## 查这 56 字时抓到的东西（两条，**都不是数错**）
  //
  // ① **三个数都不是手抄。** 源码里是静态兜底（`0.0%–20.7%` / `587–831` /
  //    `2048`），但 `applyModelFacts()`（index.html:619）在 boot 末尾拿
  //    `models.json` 的 `retention_text` / `n_eff_text` / `d_model`
  //    **运行时覆盖** `[data-f]`。实测切 `?m=0p6b` 三个数全变：
  //      587–831 → 225–420 ｜ 0.0%–20.7% → 0.4%–16.9% ｜ 2048 → 1024
  //    ⇒ 我第一遍只搜 `latent/data/*.json` 就断定「无源」并**删掉了这两段
  //      判决性文案**，那是错的：漏搜了 `frontend/public/latent/models.json`。
  //      （第二十九笔同一族：`/dims[587]/d = 587` 是数值巧合，不是证据。）
  //      Z7 就是为这条加的 —— 它能在「覆盖回退成静态兜底」时立刻报红。
  //
  // ② **`n_eff` 是「个数」还是「编号区间」——原文两种读法都通。**
  //    原文写「真正参与的维度是 587–831 / 2048」，中文里「维度是 587–831」
  //    最自然的读法是「第 587 号到第 831 号」。四条独立证据表明是**个数**：
  //      a) analyse_spread.py:30 "(sum|c|)^2/sum(c^2) -- the participation
  //         ratio ... **the number of equally-weighted dimensions**"
  //      b) analyse_spread.py:32 "bounded by the width (2048 for 1.7B)"
  //      c) build_model_registry.py:117 `n_eff_pct = pct(n_eff / width)`
  //         实测 587/2048=28.66%→28.7、831/2048=40.58%→40.6，逐位吻合
  //      d) index.html:3155 同一页自己写「等效 587–831 维」
  //    ⇒ 数是对的，**措辞**有歧义。已改成「摊在 587–831 个维度上」并就地
  //      解释「参与比」。**只加措辞，一个数都没动。**
  //      Z8 钉住读法、Z9 钉住产物侧的定义 —— 两条一起，页面上那句
  //      「等效 N 个维度」才是有出处的，而不是我们自己加的一句漂亮话。

  const MODELS = JSON.parse(readFileSync(
    '/Users/zhourui/code/steer3d/frontend/public/latent/models.json', 'utf8')).models;
  const M17 = MODELS.find(x => x.id === '1p7b') || {};
  const M06 = MODELS.find(x => x.id === '0p6b') || {};

  // 等 boot 真跑完。**不许拿静态文案当就绪信号** ——
  // 我第一版探针用 `[data-f="label"]` 的文本（源码里就写着 Qwen3-1.7B）当条件，
  // 于是在 `applyModelFacts()` 还没跑时就读了值，读回来的全是 HTML 兜底字面量，
  // 差点把「0.6B 切不进去」当成真实缺陷。运行时信号是 `S.model.id`。
  const BOOTED = `(() => ({
    id: (typeof S !== 'undefined' && S.model) ? S.model.id : null,
    found: !!document.querySelector('[data-latent-not-claimed]'),
  }))()`;
  let bootWait = 0, bootId = null;
  while (bootWait < 30000) {
    const b = await page.eval(BOOTED);
    bootId = b && b.id;
    if (b && b.found && bootId) break;
    await sleep(1200); bootWait += 1200;
  }
  // boot 之后重读一次 nc（前一次读到的可能还是 boot 前的静态兜底）
  st = await page.eval(`(() => {
    const e = document.querySelector('[data-latent-not-claimed]');
    if(!e) return { nc: { found: false } };
    const ov = document.getElementById('orientation');
    const ne = document.querySelector('[data-f="neff"]');
    const t = s => ((s||'') + '').replace(/\\s+/g, ' ').trim();
    return { nc: {
      found: true,
      orientInDom: !!ov,
      orientHiddenClass: ov ? ov.classList.contains('hide') : null,
      orientDisplay: ov ? getComputedStyle(ov).display : null,
      orientVisibility: ov ? getComputedStyle(ov).visibility : null,
      rect: (() => { const r = e.getBoundingClientRect();
                     return { w: Math.round(r.width), h: Math.round(r.height) }; })(),
      inExtras: document.getElementById('extras')
                  ? document.getElementById('extras').contains(e) : false,
      noitems: [...document.querySelectorAll('.noitem')].map(n => t(n.innerText)),
      h2Text: t([...document.querySelectorAll('h2')]
                  .filter(h => h.innerText.includes('不主张'))
                  .map(h => h.innerText)[0]),
      neffText: ne ? t(ne.textContent) : null,
      neffNext: (ne && ne.nextSibling) ? t(ne.nextSibling.textContent) : null,
      retText: t((document.querySelector('[data-f="ret"]')||{}).textContent),
      dText:   t((document.querySelector('[data-f="d"]')||{}).textContent),
      labelText: t((document.querySelector('[data-f="label"]')||{}).textContent),
      modelId: (typeof S !== 'undefined' && S.model) ? S.model.id : null,
      /* ⚠ 全集**从 DOM 反推**，不写名单（第四例的同一条纪律）。
         页面实测 14 个槽 / 6 种键：d x8、label x2、ret / neff / near / c4 各 1。
         ⚠ near 与 c4 在 index.html:439-440，**不在 #orientation 里** ——
           只查浮层内的 4 种会漏掉它们，而 C4 是按**标记名**判覆盖的，
           读了 ret/neff 就算「data-f 已覆盖」⇒ 那会把 2 个没人读的槽一起洗白。*/
      allSlots: [...document.querySelectorAll('[data-f]')].map(e => ({
        k: e.getAttribute('data-f'),
        t: String(e.textContent || '').replace(/\s+/g, ' ').trim(),
        inOrient: !!(document.getElementById('orientation')
                     && document.getElementById('orientation').contains(e)),
      })),
    } };
  })()`);
  const NC = st.nc || {};

  // ---- Z5：块在、条数与标题自称的「4」一致、每条都带依据、无渲染垃圾 ----
  // ⚠ 标题里的「4」是手打的中文数字，DOM 里的条数是另一个来源 ——
  //   两者必须互相钉住，否则「标题说 4、页面只有 3 条」没人会发现。
  const h2n = NC.h2Text ? (NC.h2Text.match(/(\d+)\s*种说法/) || [])[1] : null;
  const thin = (NC.noitems || []).map((t, i) => [i, (t.match(/否掉的依据/) || [''])[0],
      t.replace(/^.*?否掉的依据/, '').trim().length])
    .filter(([, has, len]) => !has || len < 12).map(([i, , len]) => `#${i + 1}(依据 ${len} 字)`);
  const junkNc = ['undefined', 'NaN', '[object Object]']
    .filter(w => (NC.noitems || []).some(t => t.includes(w)));
  rec('Z5 「本页不主张的 4 种说法」必须在页面上，且条数与标题自称的一致、每条都带依据'
      + '（⚠ 它不在 #extras 里，在 #orientation 浮层内 ⇒ 不能用 #extras 作用域去读）',
      !!(NC.found && (NC.noitems || []).length === 4 && h2n === '4'
         && thin.length === 0 && junkNc.length === 0),
      `DOM ${(NC.noitems || []).length} 条 / 标题「${h2n || '?'} 种说法」`
      + `　inExtras=${NC.inExtras}`
      + (thin.length ? `　依据不足：${thin.join('、')}` : '　4 条依据齐全')
      + (junkNc.length ? `　渲染垃圾：${junkNc.join('、')}` : ''));

  // ---- Z6：这块必须**真的显示出来**（不是 display:none 的隐藏块）----
  // ⚠ 为什么单独一条：`.hide{display:none!important}`，而这一段连同术语表
  //   （data-term x14）、data-f x8 全在那个浮层里。首次访问 orientAuto 会自动弹，
  //   回访则要点 #btnOrient —— 而**全链 21 条判据、两页探针、覆盖扫描里
  //   没有一处提到 orientation**。⇒ 「在 DOM 里」不等于「读者看得见」。
  //   这条不核样式表，只核「打开它之后，它是不是真的参与了布局」。
  const vis = await page.eval(`(() => {
    const ov = document.getElementById('orientation');
    const e  = document.querySelector('[data-latent-not-claimed]');
    if(!ov || !e) return { ok:false, why:'no orientation / no block' };
    const btn = document.getElementById('btnOrient');
    const wasHidden = ov.classList.contains('hide');
    if(wasHidden && btn) btn.click();          // 模拟读者点「怎么读」
    const cs = getComputedStyle(ov), r = e.getBoundingClientRect();
    return { ok: true, wasHidden,
             display: cs.display, visibility: cs.visibility,
             w: Math.round(r.width), h: Math.round(r.height),
             opacity: cs.opacity };
  })()`);
  rec('Z6 这一段必须**真的显示给读者**（在 #orientation 浮层内，默认 .hide'
      + ' ⇒ 判「在 DOM 里」不够，必须量它打开后有没有参与布局）',
      !!(vis.ok && vis.display && vis.display !== 'none'
         && vis.visibility !== 'hidden' && vis.w > 0 && vis.h > 0),
      vis.ok ? `打开前 hidden=${vis.wasHidden} → display=${vis.display}`
             + ` / visibility=${vis.visibility} / 框 ${vis.w}x${vis.h}`
             + (vis.w > 0 && vis.h > 0 ? '（已参与布局，读者看得见）'
                                       : '（框是 0 ⇒ 仍然看不见）')
            : vis.why);

  // ---- Z7：切到 0.6B，这三个数必须**全变**（证明 applyModelFacts 真覆盖到这块）----
  // ⚠ 这是本组最硬的一条：源码里的静态兜底就是 1.7B 的数，
  //   而这一段的判决建立在这三个数上。若某天 `applyModelFacts()` 漏了这个块，
  //   页面在 0.6B 上会**自信地、可核地报错**——`applyModelFacts` 的注释
  //   （:613-618）自己写着「说 2048 而页面在显示 1024 宽的模型，比没有导读更糟」。
  //   只核「1.7B 下这三个数对」是**发现不了**这个缺陷的：静态兜底也长那样。
  const M06URL = URL + (URL.includes('?') ? '&' : '?') + 'm=0p6b';
  await page.send('Page.navigate', { url: M06URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  // ⚠⚠ 就绪条件必须能区分「已经跑完」和「刚挑好模型」。这条判据在写它的时候
  //   连续踩了**三个**坑，每一个都会在 `[data-f]` 还停在源码里的 1.7B 静态
  //   兜底时就 break，然后把兜底当成「切不过去」的证据：
  //   ① `S.model.id === '0p6b'` —— `S.model` 在 `loadModelRegistry()`（:678）
  //      就设好了，中间隔着整个轨迹加载，`applyModelFacts()` 要到 :749 才跑。
  //   ② `#dbg` 里找 `model facts applied: …` —— `trace()`（:561）是
  //      `textContent =` **覆盖**式的，只留最后一条，boot 后面「post-canvas」
  //      等几条会把那行冲掉 ⇒ 等 40 秒也等不到。
  //   ③ `document.title` 的 `OK … dim=…` —— `health()` 看着在 :754（晚于 :749），
  //      但 `render()`（:3940/:3972）里也调 `health()`，而 boot 在 :738 就
  //      `await loadTraj(0)`，它内部 :801 调 `render()` ⇒ 标题**提前**就有了。
  //   ⇒ 用 `#walkTok`：静态值是「—」，只有 `applyWalkthroughFacts()`（:750，
  //     紧接 `applyModelFacts()` 的 :749 之后、同一个同步块里）会把它填成数字。
  //     0.6B 的 trajectories[0].n_tokens_total = 384。
  //     ⚠ 别拿 1024 当「0.6B 的宽度」去对：1.7B 的**步数**正好也是 1024。
  const wantWalk = '384';
  let w6 = 0, s6 = null, booted = false;
  while (w6 < 40000) {
    s6 = await page.eval(`(() => {
      const g = k => { const e = document.querySelector('[data-f="'+k+'"]');
                       return e ? String(e.textContent||'').trim() : null; };
      return { id: (typeof S !== 'undefined' && S.model) ? S.model.id : null,
               walkTok: String((document.getElementById('walkTok')||{}).textContent||'').trim(),
               allSlots: [...document.querySelectorAll('[data-f]')].map(e => ({
                 k: e.getAttribute('data-f'),
                 t: String(e.textContent || '').replace(/\s+/g, ' ').trim() })),
               ret: g('ret'), neff: g('neff'), d: g('d'), label: g('label') };
    })()`);
    booted = !!(s6 && s6.id === '0p6b' && s6.walkTok === wantWalk);
    if (booted) break;
    await sleep(1200); w6 += 1200;
  }
  const stale = [];
  if (s6 && s6.ret   === M17.retention_text) stale.push(`ret 仍是 1.7B 的 ${M17.retention_text}`);
  if (s6 && s6.neff  === M17.n_eff_text)     stale.push(`neff 仍是 1.7B 的 ${M17.n_eff_text}`);
  if (s6 && String(s6.d) === String(M17.d_model)) stale.push(`d 仍是 1.7B 的 ${M17.d_model}`);
  rec('Z7 切到 0.6B 后这一段的三个数必须**全变成 0.6B 的实测值**'
      + '（只核 1.7B 下对是发现不了这个缺陷的：静态兜底也长那样）',
      !!(booted && s6.ret === M06.retention_text
         && s6.neff === M06.n_eff_text && String(s6.d) === String(M06.d_model)),
      // ⚠ 「仪器没到位」与「被测物坏了」必须分开说：
      //   等不到 title 那行时，读到的**必然**是源码里的 1.7B 兜底，
      //   而那不是「切不过去」的证据 —— 报告成后者就是我上面写的那次误判。
      !booted
        ? `⚠ 仪器没到位：等了 ${w6}ms，walkTok=${(s6 && s6.walkTok) || '(空)'}`
          + `（#walkTok 还是「—」⇒ applyWalkthroughFacts 尚未跑，读到的是源码`
          + `静态兜底，**不能**据此说切不过去）`
        : `?m=0p6b（walkTok=${s6.walkTok} 已确认 0.6B 走完 applyWalkthroughFacts）读到 `
          + `ret=${s6.ret} / neff=${s6.neff} / d=${s6.d} / ${s6.label}`
          + `　期望 ${M06.retention_text} / ${M06.n_eff_text} / ${M06.d_model}`
          + (stale.length ? `　⚠ 没变的：${stale.join('、')}` : '　三个全变 ⇒ 不是静态兜底'));

  // ---- Z8：`n_eff` 的读法必须被钉成「个数」----
  // ⚠ 判法是**结构**不是抄字面量：数后面紧跟的必须是量词「个」。
  //   原文「维度是 587–831 / 2048」紧跟的是「 / 」⇒ 会被读成编号区间。
  //   改成「维度是 587–831 / 2048」以外的任何写法都不必关心，
  //   只要「数」和「个」之间没有别的词，这条就红。
  const noitem0 = (NC.noitems || [])[0] || '';
  const unitOk = !!NC.neffNext && /^\s*个/.test(NC.neffNext);
  const disclaims = noitem0.includes('不是「第几号到第几号」');
  rec('Z8 「参与的维度」这个数后面必须紧跟量词「个」，且同一条里明说不是编号区间'
      + '（原句「维度是 587–831 / 2048」会被读成第 587 号到第 831 号）',
      unitOk && disclaims,
      `neff 槽后面接「${(NC.neffNext || '').slice(0, 14)}…」`
      + `　量词${unitOk ? '已钉住' : '❌ 缺失（仍可被读成编号区间）'}`
      + `　${disclaims ? '已明说不是编号区间' : '❌ 缺「不是编号区间」那句'}`);

  // ---- Z9：产物侧必须仍然把 n_eff 定义成「个数、上界是宽度」----
  // ⚠ 页面新加的「等效 N 个维度」这句话**只在 n_eff 真是那个量时才成立**。
  //   把 n_eff 换成「超过阈值的维数」是 analyse_spread.py 里自己讨论过并否决的
  //   方案（:41 起 "Why participation ratio and not count of dims above a
  //   threshold"）。⇒ 判据要钉住**定义**，否则页面会静默变成假话。
  const spreadSrc = readFileSync(
    '/Users/zhourui/code/steer3d/backend/examples/analyse_spread.py', 'utf8');
  const defCount  = /the number of\s*\n?\s*equally-weighted dimensions/.test(spreadSrc);
  const defBound  = /bounded\s*\n?\s*by the width/.test(spreadSrc);
  rec('Z9 产物侧必须仍然把 n_eff 定义成「等权维数的个数」且「上界是宽度」'
      + '（页面那句「等效 N 个维度」只有在这个定义下才成立）',
      defCount && defBound,
      `analyse_spread.py：个数定义${defCount ? '在' : '❌ 不在'}`
      + ` / 上界是宽度${defBound ? '在' : '❌ 不在'}`);

  // ---- Z10：n_eff_pct 必须等于 n_eff / d_model（两个模型都算）----
  // ⚠ 这是「个数」这个读法的**算术证据**，不是措辞证据：
  //   注册表自己把 n_eff 除以宽度存成了百分比，两侧独立算的。
  //   若 n_eff 变成编号区间，这个恒等式立刻不成立。
  const pctBad = [];
  for (const m of MODELS) {
    const w = m.d_model;
    [0, 1].forEach(i => {
      const want = +(m.n_eff[i] / w * 100).toFixed(1);
      if (Math.abs(want - m.n_eff_pct[i]) > 0.051) {
        pctBad.push(`${m.label} n_eff_pct[${i}]=${m.n_eff_pct[i]} 而 ${m.n_eff[i]}/${w}=${want}`);
      }
      if (m.n_eff[i] > w) pctBad.push(`${m.label} n_eff[${i}]=${m.n_eff[i]} > 宽度 ${w}`);
    });
  }
  rec('Z10 n_eff_pct 必须逐位等于 n_eff / d_model（这是「个数」这个读法的算术证据）',
      pctBad.length === 0,
      pctBad.length ? pctBad.join('；')
        : MODELS.map(m => `${m.label} ${m.n_eff[0]}/${m.d_model}=${m.n_eff_pct[0]}%`
                        + `、${m.n_eff[1]}/${m.d_model}=${m.n_eff_pct[1]}%`).join('　｜　'));

  // ---- Z11：**每一个** [data-f] 槽都必须显示当前模型的实测值（两个模型都量）----
  // ⚠⚠ 这条是为了堵一个**虚假的减债**。
  //   C4 是按**标记名**判覆盖的：只要有判据里出现过 `data-f` 这三个字符，
  //   整条 `data-f`（页面上 14 个槽）就从欠账清单里消失。
  //   而 Z5–Z8 只读了浮层内的 4 种键（d / label / ret / neff），
  //   `near`（4 题）和 `c4`（16%）在 index.html:439-440、**不在浮层里** ——
  //   ⇒ 判据会在只覆盖 12/14 的情况下宣布 14/14 已覆盖。
  //   这与第三十二笔「`C4` 恒绿」是同一族的毛病，只是这次绿的是**减债**那一侧。
  // ⇒ 所以全集必须从 DOM 反推（不写名单），且**两个模型都要逐槽对**。
  //   键 → 注册表字段的映射也不手抄：直接从 `applyModelFacts()` 的 `v` 字面量解析，
  //   免得有人给 `v` 加了键却忘了在页面上有槽（那样新槽会静默停在静态兜底上）。
  const pageSrcZ = stripJsComments(readFileSync(SRC, 'utf8'));
  const vBody = (pageSrcZ.match(/const v = \{([\s\S]*?)\n {2}\};/) || [])[1] || '';
  const vMap = {};
  for (const m of vBody.matchAll(/(\w+)\s*:\s*m\.(\w+)/g)) vMap[m[1]] = m[2];
  // ⚠⚠ 这张表是**判据侧手写的期望**，而且必须手写。
  //   我第一版把期望值从 `v` 里解析出来 —— 也就是**从被测代码推导期望**。
  //   变异 `M-Q`（把 `near: m.near_miss_text` 改成 `near: m.c4_short`）当场打脸：
  //   槽里显示 `c4_short` 的值（16%），而「期望」也变成了 `c4_short` 的值（16%）
  //   ⇒ 两者照样相等 ⇒ **23/23 全绿**，判据完全没反应。
  //   这是「判据与被测物共用同一份来源 ⇒ 假绿」的第三例：
  //     第一例是判据与产品共用同一份**手抄数字**；
  //     第二例是 C4 的 `isinstance(unread, list)`（恒真）；
  //     第三例是这一条 —— 判据**动态地**从被测代码读出期望，
  //     于是「路由错了」这件事会同时改掉实际值和期望值，永远相等。
  // ⇒ 原则：**判据要核的东西，必须由判据侧独立写死；能被改的那一半只能是产物。**
  //   而「核哪些槽」仍然从 DOM 反推（不写名单）—— 期望手写、枚举反推，两件事。
  const EXPECT_SLOT = {
    d: 'd_model', label: 'label', ret: 'retention_text',
    neff: 'n_eff_text', near: 'near_miss_text', c4: 'c4_short',
  };
  const slotKeys = [...new Set((NC.allSlots || []).map(s => s.k))];
  const orphan = slotKeys.filter(k => !(k in vMap) && k !== 'nmodels');
  const routeBad = slotKeys
    .filter(k => k in EXPECT_SLOT && k in vMap && vMap[k] !== EXPECT_SLOT[k])
    .map(k => `${k} 被接到 m.${vMap[k]}，应是 m.${EXPECT_SLOT[k]}`);
  const bad = [];
  for (const [slots, M, tag] of [[NC.allSlots, M17, M17.label],
                                 [s6.allSlots, M06, M06.label]]) {
    for (const s of (slots || [])) {
      if (!(s.k in EXPECT_SLOT)) continue;
      const want = String(M[EXPECT_SLOT[s.k]]);
      if (s.t !== want) bad.push(`${tag} 槽 ${s.k}：页面「${s.t}」≠ ${EXPECT_SLOT[s.k]}「${want}」`);
    }
  }
  const slotN = (NC.allSlots || []).length;
  const inOrientN = (NC.allSlots || []).filter(s => s.inOrient).length;
  rec('Z11 页面上**每一个** [data-f] 槽都必须显示当前模型**它自己那个字段**的值，'
      + '两个模型各逐槽对；且 applyModelFacts() 的路由不许接错'
      + '（⚠ 期望值必须由判据侧写死：从 v 里解析期望 = 从被测代码推导期望 ⇒ 变异 M-Q 全绿）',
      orphan.length === 0 && routeBad.length === 0 && bad.length === 0
        && slotN === 14 && (s6.allSlots || []).length === 14,
      `applyModelFacts() 实际路由：${JSON.stringify(vMap)}`
      + `　槽 ${slotN} 个（浮层内 ${inOrientN} / 浮层外 ${slotN - inOrientN}）`
      + (orphan.length ? `　⚠ 页面有槽但 v 里没有：${orphan.join('、')}` : '')
      + (routeBad.length ? `　⚠ 路由错：${routeBad.join('；')}` : '　6 种键的路由都对')
      + (bad.length ? `　⚠ ${bad.join('；')}` : '　两个模型逐槽对上 ✅'));

  // ==================================================================
  // Z12–Z14（第三十三笔之十）：导读浮层的**骨架**也必须有人读
  // ==================================================================
  // C6 的真孤儿清单里，导读浮层占 11 条：h1 / 导语 p / 五个 h2 /
  // 两条「否掉的说法」/ 按钮栏 + 提示行。它们的性质与「图表标签、
  // <select> 选项」那一类**不同** —— 读者靠那五个 h2 知道自己在读第几节，
  // 而那两条「否掉的说法」是**判决性散文**（它们声明本页否掉了哪两种理解）。
  //
  // ⚠⚠⚠ 加标记时**没有复用** `data-latent-not-claimed`：
  //   本文件 :222 / :513 / :578 三处都用
  //   `querySelector('[data-latent-not-claimed]')` 取**第一个**，
  //   Z6 靠它量那一段的包围盒。复用会让 first-match 静默漂到 h1 上
  //   ⇒ 判据**认错对象**（与属性 first-match 换人是同一族，只是这次在加标记）。
  //   ⇒ 另起 `data-orient-part`，那三处语义一个都不动。
  //   验证方式不是「我觉得没动」，是**数**：`grep -c data-latent-not-claimed`
  //   仍为 1，且它在文档序里仍**先于**两个 data-orient-part="claim"。
  const ORI = await page.eval(`(() => {
    const ov = document.getElementById('orientation');
    if (!ov) return { err: 'no #orientation' };
    if (ov.classList.contains('hide')) {
      const b = document.getElementById('btnOrient'); if (b) b.click();
    }
    const t = s => ((s || '') + '').replace(/\\s+/g, ' ').trim();
    const parts = [...ov.querySelectorAll('[data-orient-part]')].map(e => ({
      role: e.getAttribute('data-orient-part'),
      tag: e.tagName.toLowerCase(),
      len: t(e.innerText).length,
      head: t(e.innerText).slice(0, 40),
      // 下一节标题自称的编号（中文数字）—— Z12 用它钉「不许跳号」
      num: (t(e.innerText).match(/^([一二三四五六七八九十])/) || [])[1] || null,
    }));
    // Z13：每个 sec 后面紧跟的那个内容块有多长（0 = 空节）
    const secFill = {};
    for (const e of ov.querySelectorAll('[data-orient-part^="sec"]')) {
      let n = e.nextElementSibling, n2 = 0;
      while (n && n2 < 200) { n2 += 1; if (n.textContent.trim().length > 0) break; n = n.nextElementSibling; }
      secFill[e.getAttribute('data-orient-part')] = n ? t(n.innerText).length : 0;
    }
    // 四条「否掉的说法」里，哪些带了新标记（可读标记）
    const noitems = [...ov.querySelectorAll('.noitem')].map(n => ({
      marked: !!n.querySelector('[data-orient-part]') || n.hasAttribute('data-orient-part'),
      hasNumSlot: !!n.querySelector('[data-f]'),
      len: t(n.innerText).length,
    }));
    return JSON.stringify({ parts, secFill, noitems });
  })()`);
  // ⚠⚠ `page.eval` 返回什么类型，取决于**页面侧 return 的是什么**：
  //   上面几处直接 `return {...}`，拿回来就是对象；我这里 `return JSON.stringify(...)`，
  //   拿回来是**字符串**，必须自己 parse。
  //   ⚠ 本文件两种写法都存在，而第一版我抄了 `JSON.stringify` 却没抄配对的
  //     `JSON.parse` ⇒ O.parts / O.secFill / O.noitems 全是 undefined
  //     ⇒ Z12/Z13/Z14 **三条一起红**，而红的原因是判据读不到东西，不是页面坏了。
  //   （同族：[[差异比对器必须先证明它读到了东西]]。）
  //   ⇒ 一条判据「三条同时红」时，先问「是不是同一个取数环节炸了」。
  const O = (() => {
    try { return JSON.parse(ORI) || {}; }
    catch (e) { return { err: 'JSON.parse 失败：' + e.message, raw: String(ORI).slice(0, 120) }; }
  })();
  const PARTS = O.parts || [];
  const byRole = r => PARTS.filter(p => p.role === r);
  const CN = ['一', '二', '三', '四', '五'];

  // ---- Z12：骨架完整 + 五个小节编号连续 ----
  // ⚠ 期望**只钉骨架的形状**（哪些角色各该有几条、编号是不是 一…五），
  //   文本内容一律从 DOM 反推 —— 写死文本就成了「判据与产品共用同一份手抄」。
  const shape = { h1: 1, lead: 1, sec1: 1, sec2: 1, sec3: 1, sec4: 1, sec5: 1,
                  claim: 2, foot: 1 };
  const shapeBad = Object.keys(shape).filter(r => byRole(r).length !== shape[r]);
  const extraRole = PARTS.map(p => p.role).filter(r => !(r in shape));
  const secNums = ['sec1', 'sec2', 'sec3', 'sec4', 'sec5']
    .map(r => (byRole(r)[0] || {}).num);
  const numsOk = secNums.every((v, i) => v === CN[i]);
  rec('Z12 导读浮层的**骨架**必须逐块有可读标记：标题 1 + 导语 1 + 五个小节 1×5'
      + ' + 两条无数字的「否掉的说法」2 + 按钮栏 1；且五个小节自称的编号必须是 一…五 连续',
      !O.err && !shapeBad.length && !extraRole.length && numsOk,
      (O.err ? `⚠ 取数失败：${O.err}　${O.raw || ''}` : '')
      + `实到 ${PARTS.length} 条：${PARTS.map(p => p.role + '/' + p.tag).join('、')}`
      + (shapeBad.length ? `　⚠ 条数不对：${shapeBad.join('、')}` : '　各角色条数都对')
      + (extraRole.length ? `　⚠ 出现没登记的角色：${[...new Set(extraRole)].join('、')}` : '')
      + (numsOk ? '　编号 一二三四五 连续' : `　⚠ 小节编号是 ${secNums.join('、')}，不是 一…五`));

  // ---- Z13：每个小节不许是空节 ----
  const fillBad = Object.keys(O.secFill || {})
    .filter(r => (O.secFill[r] || 0) < 40);
  rec('Z13 导读的每个小节标题后面必须紧跟**有实质内容**的块（≥40 字）'
      + '——只有标题没有内容的小节，读者点进来看到的是空的',
      Object.keys(O.secFill || {}).length === 5 && fillBad.length === 0,
      Object.keys(O.secFill || {}).map(r => `${r}=${O.secFill[r]}字`).join('、')
      + (fillBad.length ? `　⚠ 空节：${fillBad.join('、')}` : '　五节都有内容')
      + (Object.keys(O.secFill || {}).length !== 5
         ? `　⚠ 只量到 ${Object.keys(O.secFill || {}).length} 个 sec` : ''));

  // ---- Z14：四条「否掉的说法」必须**每一条都可达** ----
  // ⚠⚠ 这条针对的是一个具体的漏法：`#2`、`#4` 之所以在 C6 里是真孤儿，
  //   是因为**它们内部没有 [data-f] 数字槽** —— 探针的 `hasDataDesc`
  //   把带数字槽的 #1、#3 结构性排除了，于是「没绑数字」被当成了
  //   「不是论断」。这两条同样是判决性散文。
  //
  // ⚠⚠⚠ 期望值**第一版写错了**：写成「4 条都自带 data-orient-part」，
  //   实测 Z14 红。判红先分清是「页面在撒谎」还是「判据问错了」——
  //   这次是**判据问错**：#1、#3 内部有 [data-f] 槽，Z11 已经**逐槽**核过
  //   它们的值，它们本来就可达，不该被要求再加一遍标记。
  //   ⇒ 正确的性质是「每一条都**落在某个可读标记的覆盖范围内**」。
  //   而且必须**分开报**「自带标记的」与「靠数字槽可达的」——
  //   混成一个数就看不出「该补的那两条到底补上没有」。
  const ni = O.noitems || [];
  const niUnreach = ni.filter(n => !n.marked && !n.hasNumSlot);
  const niByOwn = ni.filter(n => n.marked);
  const niBySlot = ni.filter(n => !n.marked && n.hasNumSlot);
  rec('Z14 四条「本页不主张的说法」每一条都要**可达**：要么自带可读标记，'
      + '要么内部有 [data-f] 数字槽（Z11 逐槽核过）'
      + '（⚠ 其中两条没有数字槽，探针的 hasDataDesc 会把它们与「不是论断」'
      + '混为一谈 —— 没绑数字不等于不是论断）',
      ni.length === 4 && niUnreach.length === 0,
      `实到 ${ni.length} 条：自带标记 ${niByOwn.length} 条`
      + `　靠 [data-f] 槽可达 ${niBySlot.length} 条`
      + `　不可达 ${niUnreach.length} 条`
      + (niUnreach.length
         ? `　⚠ 不可达的是第 ${niUnreach.map(n => ni.indexOf(n) + 1).join('、')} 条`
         : '　四条全部可达')
      + (ni.length !== 4 ? `　⚠ 条数不是 4` : ''));

  // ==================================================================
  // W 组（第三十三笔之四）：[data-arm] / [data-armtext] / [data-cotarm]
  //                  —— 同一道题跑两遍，两臂逐字对照（承载判决）
  // ==================================================================
  // ## 先说查出来的那个缺陷（本轮修的）
  //
  // 页面在每张卡的末尾说「…下文略，原文还有 M 字符…」。
  // 实测第 1 题印的是 **7203**，正确值是 **7143**：
  //     chars(7623) − 真实起点(60) − 实际显示(420) = 7143
  // 而印出来的是 7623 − 0 − 420 = 7203。
  //
  // 根因是 `show(text, win, total)` 用 `win.start` 当「这段文本的起点」，
  // 可调用方已经先 `hinge()` 切掉了前 `split_char` 个字：
  //     win = it.split.zero，其 .start = 0（节选本身从全文 0 开始）
  //     实际显示的 = hinge(...)[1] = text.slice(60)，真实起点是 60
  // ⇒ 多算了整整一个 split_char，**10 道题 × 两臂 = 20 个印出来的数全错**
  //   （split_char 实测 14–126）。
  //
  // ⚠ 与本函数上方注释里记的「180 常量」是同一族的毛病：
  //   那一处修的是「head_chars 是不是真的 N 个字」，
  //   而「这段截取还剩多少字」这个记账**从来没被核过**。
  //   ⇒ 同一个函数里，两件相邻的事，一件修了另一件没修。
  //
  // ## W2 就是为它写的
  //
  // 判法：**页面印的 M 必须等于「按产物的真实起点与真实显示长度现算出来的值」**。
  // 这条是「印出来的数必须能被另一个印出来的数现算复核」那一类，
  // 常数满足不了它 —— 而常数恰恰是这块历史上出过错的东西。

  const AR = j('answer_readout.json');
  const ARsel = AR.selection || {};
  const NITEM = (AR.items || []).length;

  // ⚠⚠ 必须先把页面**导航回 1.7B**：Z7 为了核「切到 0.6B 三个数全变」把页面
  //   导航到了 ?m=0p6b，而 answer_readout.json / cot_texts 只在 1.7B 的
  //   data/ 里，0.6B 的 data06/ 没有 ⇒ 这一组会扫到**空的** #extras。
  //   而我第一版的 W2/W3/W5 写的是「一条错都没有 ⇒ PASS」，
  //   在 0 条上就是**空真** —— 正是第三十二笔给 C4 记过的那条病，自己又犯了一次。
  // ⇒ 下面每一条 W 判据都额外要求 `swept === NITEM`，
  //   「扫到 0 条」必须报红而不是通过。
  //   就绪信号用「模型 id + walkTok 都对上」，两个条件缺一不可：
  //   0.6B 的 d_model 也是 1024，而 1.7B 的 walkTok 正好也是 1024，
  //   单看任一个都会被另一模型顶替。
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  let backWait = 0, backOk = false;
  while (backWait < 40000) {
    const b = await page.eval(`(() => ({
      id: (typeof S !== 'undefined' && S.model) ? S.model.id : null,
      walkTok: String((document.getElementById('walkTok')||{}).textContent||'').trim(),
      picks: document.querySelectorAll('#extras [data-arpick]').length,
    }))()`);
    backOk = !!(b && b.id === '1p7b' && b.walkTok === '1024' && b.picks > 0);
    if (backOk) break;
    await sleep(1200); backWait += 1200;
  }
  rec('W0 这一组跑之前必须**导航回 1.7B**，且 #extras 里真的渲染出了题号选择器'
      + '（Z7 把页面切到 ?m=0p6b 了，而 answer_readout.json 只在 1.7B 的 data/ 里）',
      backOk,
      backOk ? `已回到 1.7B（walkTok=1024，#extras 里 ${NITEM} 个 [data-arpick]），等了 ${backWait}ms`
             : `⚠ 等了 ${backWait}ms 仍不满足：页面不在 1.7B，或 #extras 没有 [data-arpick]`
               + `（此时下面所有 W 判据都只能空跑，必须当作未验）`);

  // 两臂原文的公共前缀长度（现算，不信 split_char 自报）
  const commonPrefix = (a, b) => {
    const n = Math.min(a.length, b.length); let i = 0;
    while (i < n && a[i] === b[i]) i++;
    return i;
  };
  const numEq = (a, b) => {
    const x = Number(a), y = Number(b);
    if (Number.isFinite(x) && Number.isFinite(y)) return Math.abs(x - y) < 1e-9;
    return String(a).trim() === String(b).trim();
  };
  // 由 (标准答案, 对照臂答案, 干预臂答案) 现算四类判定之一
  const verdictOf = (ref, za, sa) => (numEq(za, ref) && numEq(sa, ref)) ? 'right->right'
    : numEq(za, ref) ? 'right->wrong'
    : numEq(sa, ref) ? 'wrong->right' : 'wrong->wrong';

  // ---- 遍历 10 道：点 data-arpick 会同步重渲染（renderExtras），不用重载页面 ----
  // ⚠ 不写"只查当前选中那一道"：这个缺陷是系统性的（同一段代码走所有题），
  //   查一道只能证明代码路径，查十道才能证明没有某道题的数据例外。
  const SWEEP = `(() => {
    const t = e => e ? (e.innerText || '').replace(/\\s+/g, ' ').trim() : '';
    const root0 = document.getElementById('extras');
    if (!root0 || !root0.querySelector('[data-arpick]')) return { err: '没有 [data-arpick]' };
    const nb = root0.querySelectorAll('[data-arpick]').length;
    const out = [];
    for (let i = 0; i < nb; i++) {
      // ⚠⚠ 每一次都**重新**取 #extras，不许缓存。
      //   renderExtras() 重建的是整个容器的 innerHTML（点一下换档整个 #extras 被换掉），
      //   缓存下来的 host 是一个已脱离文档的旧节点 —— 里面还留着上一次渲染的
      //   臂卡（所以 W1 看着是对的），但承载正文的那一整块在新渲染里
      //   已经不是同一个节点了。
      //   我第一版缓存了 host，于是 W2–W5 全部读到 null，
      //   而页面明明把那些数印出来了（探针 dump 里清清楚楚）。
      const host = document.getElementById('extras');
      const btns = host ? host.querySelectorAll('[data-arpick]') : [];
      if (!btns[i]) { out.push({ pick: i, err: '按钮没了' }); continue; }
      btns[i].click();
      const host2 = document.getElementById('extras');
      const root = host2 ? host2.querySelector('[data-aroot]') : null;
      const txt = t(root);
      const g = re => { const m = txt.match(re); return m ? m[1] : null; };
      out.push({
        pick: i,
        txtLen: txt.length,
        label: (txt.match(/(\\S+?)\\s*·\\s*标准答案/) || [])[1] || null,
        ref: g(/标准答案\\s*(\\S+?)\\s*·/),
        verdict: (txt.match(/标准答案\\s*\\S+?\\s*·\\s*([^先]{2,20}?)\\s*先说题目本身/) || [])[1] || null,
        splitChar: g(/一致到第\\s*(\\d+)\\s*个字符才分岔/),
        elided: [...txt.matchAll(/原文还有\\s*(\\d+)\\s*字符/g)].map(m => Number(m[1])),
        lens: (() => { const m = txt.match(/它们长度不同（(\\d+) 与 (\\d+) 字符）/);
                       return m ? [Number(m[1]), Number(m[2])] : null; })(),
        armLines: [...txt.matchAll(/写了\\s*(\\d+)\\s*步\\s*·\\s*(\\d+)\\s*字符\\s*·\\s*答案\\s*(\\S+?)\\s*（boxed）/g)]
                    .map(m => ({ steps: Number(m[1]), chars: Number(m[2]), answer: m[3] })),
        armKeys: host2 ? [...host2.querySelectorAll('[data-arm]')]
                          .map(e => e.getAttribute('data-arm')) : [],
        armtextKeys: host2 ? [...host2.querySelectorAll('[data-armtext]')]
                          .map(e => e.getAttribute('data-armtext')) : [],
      });
    }
    const back = document.getElementById('extras');
    const b0 = back ? back.querySelectorAll('[data-arpick]') : [];
    if (b0[0]) b0[0].click();   // 切回第 0 个，别给后面的判据留下改过的页面状态
    return { out };
  })()`;
  const sweep = await page.eval(SWEEP);
  const SW = (sweep && sweep.out) || [];

  const wantKeys = ['post:zero', 'post:steered', 'tail:zero', 'tail:steered'];
  const keyBad = SW.filter(s => s.armKeys.length !== 4 || s.armtextKeys.length !== 4
    || wantKeys.some(k => !s.armKeys.includes(k) || !s.armtextKeys.includes(k)));
  rec('W1 四张臂卡（post:zero / post:steered / tail:zero / tail:steered）必须齐全'
      + '，且 data-arm 与 data-armtext 一一对应（渲染层）',
      SW.length === NITEM && NITEM > 0 && keyBad.length === 0,
      `逐题点过 ${SW.length} 道　每题 data-arm ${(SW[0] || {}).armKeys ? (SW[0].armKeys || []).length : 0} 个`
      + ` / data-armtext ${(SW[0] || {}).armtextKeys ? (SW[0].armtextKeys || []).length : 0} 个`
      + (keyBad.length ? `　⚠ 第 ${keyBad.map(s => s.pick).join('、')} 张不齐` : '　10 道全齐')
      + (sweep && sweep.err ? `　（${sweep.err}）` : ''));

  // ---- W2：「原文还有 M 字符」必须等于现算的剩余量（本轮修的那个缺陷）----
  const elBad = [];
  for (const s of SW) {
    const it = (AR.items || [])[s.pick];
    if (!it) continue;
    const sc = it.split_char || 0;
    for (const [k, arm, sp] of [['post:zero', 'zero', 'zero'],
                                ['post:steered', 'steered', 'steered']]) {
      const w = it.split[sp];
      const start = (w.start || 0) + sc;              // 真实起点
      const shown = w.text.length - sc;               // 实际显示
      const want = it[arm].chars - start - shown;
      const got = s.elided[wantKeys.indexOf(k)];
      if (got !== want) {
        elBad.push(`${it.label}/${k} 印 ${got}，现算 ${want}（差 ${got - want} = split_char）`);
      }
    }
  }
  rec('W2 每张 post 卡末尾的「原文还有 M 字符」必须等于现算的剩余量'
      + '（M = chars − 真实起点 − 实际显示长度；⚠ 真实起点是 split.start + split_char）',
      elBad.length === 0 && SW.length === NITEM && NITEM > 0,
      (SW.length !== NITEM || NITEM === 0)
        ? `⚠ 只扫到 ${SW.length}/${NITEM} 道 ⇒ 下面「无错」是**空真**，本条不计通过`
        : elBad.length ? `错 ${elBad.length} 处：${elBad.slice(0, 3).join('；')}`
        : `逐题逐臂核过 ${SW.length * 2} 个数（起点 = split.start + split_char），全对`);

  // ---- W3：「一致到第 N 个字符才分岔」的 N 必须等于两臂正文的现算公共前缀 ----
  const cpBad = [];
  for (const s of SW) {
    const it = (AR.items || [])[s.pick];
    if (!it) continue;
    const want = commonPrefix(it.split.zero.text, it.split.steered.text);
    if (Number(s.splitChar) !== want) {
      cpBad.push(`${it.label} 印 ${s.splitChar}，现算 ${want}`);
    }
    if (it.shared_prefix_chars != null && it.shared_prefix_chars !== want) {
      cpBad.push(`${it.label} 产物自报 shared_prefix_chars=${it.shared_prefix_chars}，现算 ${want}`);
    }
  }
  rec('W3「一致到第 N 个字符才分岔」的 N 必须等于两臂正文的**现算公共前缀长度**'
      + '（不信 split_char 自报；源码注释记着这一块曾把 180 写死而实际第 14 个字符就分岔）',
      cpBad.length === 0 && SW.length === NITEM && NITEM > 0,
      SW.length !== NITEM
        ? `⚠ 只扫到 ${SW.length}/${NITEM} 道 ⇒ 空真，不计通过`
        : cpBad.length ? cpBad.join('；')
        : `${SW.length} 道题的 N 全部现算吻合`
          + `（${Math.min(...SW.map(s => Number(s.splitChar)))}–${Math.max(...SW.map(s => Number(s.splitChar)))}）`);

  // ---- W4：页面印的判定必须能由**它自己印的**标准答案 + 两臂答案现算复核 ----
  // ⚠⚠ 这条**不抄页面的措辞表**。页面上有一张 VD 表（index.html:2427），
  //   四类各配一句中文。我第一版把那四句手抄进判据，抄错了 wrong->wrong 那一行
  //   （页面写「两边都错，只是错得不一样」，我写「两遍都答错」）⇒ 8 道题假红。
  //   而改成「从页面源码解析那张表」也不行 —— 那正是本组刚记下的
  //   「判据从被测代码推导期望 ⇒ 假绿」：表里任何一行写错都会同时改掉
  //   实际值与期望值，永远相等。
  // ⇒ 分成两层：
  //   ① **无标签的结构检查**（不需要知道措辞）：由三个数重算出类别后，
  //      「类别 → 印出的那一句」必须是个**函数**（同一类别在 10 道题里
  //      永远印同一句），且不同类别不许印同一句。
  //      抄错/写串了一行，这两条立刻红。
  //   ② **只对两个方向性类别手写期望**：变好与变坏是这块的判决句，
  //      它们的含义必须能从字面看出来（「答错…答对」/「答对…答错」）。
  const vdBad = [], vdCalc = {}, vdTable = {};
  for (const s of SW) {
    const it = (AR.items || [])[s.pick];
    if (!it) continue;
    const zeroAns = s.armLines[0] && s.armLines[0].answer;
    const steerAns = s.armLines[1] && s.armLines[1].answer;
    if (zeroAns == null || steerAns == null || s.ref == null || s.verdict == null) {
      vdBad.push(`${it.label} 页面上没读到四个数/句（ref=${s.ref} zero=${zeroAns} steer=${steerAns} verdict=${s.verdict}）`);
      continue;
    }
    const calc = verdictOf(s.ref, zeroAns, steerAns);
    vdCalc[calc] = (vdCalc[calc] || 0) + 1;
    if (vdTable[calc] === undefined) vdTable[calc] = s.verdict;
    else if (vdTable[calc] !== s.verdict) {
      vdBad.push(`${it.label} 同为 ${calc} 却印了两句：「${vdTable[calc]}」与「${s.verdict}」`
        + '（⇒ 类别→措辞不是函数）');
    }
  }
  // ① 不同类别不许印同一句
  const seen = {};
  for (const [k, v] of Object.entries(vdTable)) {
    if (seen[v] !== undefined) vdBad.push(`${k} 与 ${seen[v]} 印了同一句「${v}」（⇒ 撞串）`);
    seen[v] = k;
  }
  // ② 两个方向性类别的手写期望（只查方向，不查具体措辞）
  const dirWant = { 'right->wrong': /答对.*答错/, 'wrong->right': /答错.*答对/ };
  for (const [k, re] of Object.entries(dirWant)) {
    if (vdTable[k] === undefined) continue;          // 本批没出现该类别，不算错
    if (!re.test(vdTable[k])) {
      vdBad.push(`${k} 印「${vdTable[k]}」，方向读不出来（应含 ${re.source}）`);
    }
  }
  const selfCensus = Object.keys(ARsel.by_verdict || {})
    .reduce((o, k) => (ARsel.by_verdict[k] ? (o[k] = ARsel.by_verdict[k], o) : o), {});
  const censusOk = JSON.stringify(vdCalc) === JSON.stringify(selfCensus);
  if (!censusOk) vdBad.push(`分布对不上：现算 ${JSON.stringify(vdCalc)} vs 页面 by_verdict ${JSON.stringify(selfCensus)}`);
  rec('W4 页面印的判定必须能由**它自己印的**标准答案 + 两臂答案现算复核；'
      + '「类别→措辞」必须是个函数且不撞串；两个方向性类别的方向必须读得出来'
      + '（⚠ 不抄措辞表：抄错会假红，从源码解析又会假绿）',
      vdBad.length === 0 && SW.length === NITEM && NITEM > 0,
      SW.length !== NITEM
        ? `⚠ 只扫到 ${SW.length}/${NITEM} 道 ⇒ 空真，不计通过`
        : (vdBad.length ? `问题 ${vdBad.length} 处：${vdBad.slice(0, 2).join('；')}`
          : `逐题现算分布 ${JSON.stringify(vdCalc)} 与页面 by_verdict 一致 ✅\n`
            + `       观察到的类别→措辞：${Object.entries(vdTable).map(([k, v]) => `${k}=「${v}」`).join('　')}`));

  // ---- W5：每张臂卡印的「步数 / 字符数」必须等于该臂产物的 steps / chars ----
  const stBad = [];
  for (const s of SW) {
    const it = (AR.items || [])[s.pick];
    if (!it) continue;
    [[0, 'zero'], [1, 'steered']].forEach(([i, arm]) => {
      const L = s.armLines[i];
      if (!L) { stBad.push(`${it.label}/${arm} 页面上没读到那一行`); return; }
      if (L.chars !== it[arm].chars) stBad.push(`${it.label}/${arm} 字符数 ${L.chars}≠${it[arm].chars}`);
      if (L.steps !== it[arm].steps) stBad.push(`${it.label}/${arm} 步数 ${L.steps}≠${it[arm].steps}`);
      if (!numEq(L.answer, it[arm].answer)) stBad.push(`${it.label}/${arm} 答案 ${L.answer}≠${it[arm].answer}`);
    });
    if (s.lens && (s.lens[0] !== it.zero.chars || s.lens[1] !== it.steered.chars)) {
      stBad.push(`${it.label}「它们长度不同」印 ${s.lens.join(' 与 ')}，产物 ${it.zero.chars} 与 ${it.steered.chars}`);
    }
  }
  rec('W5 每张臂卡印的「写了 N 步 · M 字符 · 答案 X」必须逐项等于该臂产物的 steps/chars/answer；'
      + '「它们长度不同（X 与 Y 字符）」的 X/Y 也必须等于两臂的 chars',
      stBad.length === 0 && SW.length === NITEM && NITEM > 0,
      SW.length !== NITEM
        ? `⚠ 只扫到 ${SW.length}/${NITEM} 道 ⇒ 空真，不计通过`
        : stBad.length ? stBad.slice(0, 3).join('；')
        : `逐题两臂共 ${SW.length * 2} 行 ×3 个数全对`
          + `（字符数 ${Math.min(...SW.map(s => s.armLines[0].chars))}–${Math.max(...SW.map(s => s.armLines[1].chars))}）`);

  // ---- W6：data-cotarm 两个臂（primary / shadow）必须都在、非空、且**正文**确实不同 ----
  // ⚠⚠ 第一版比的是整段 innerText，而 `data-cotarm` 那个 div 里
  //   **臂名也在里面**（「加了向量（干预臂）」/「没加向量（对照臂）」），
  //   所以两臂正文一字不差时整段文本仍然不等 ⇒ 这条恒真。
  //   变异 `M-W`（把 shadow 也印 H.after_primary）当场打脸：30/30 全绿。
  // ⇒ 只比**正文**那一个子 div，臂名不算。
  const cotTxt = await page.eval(`(() => {
    const t = e => e ? (e.innerText || '').replace(/\\s+/g, ' ').trim() : null;
    return [...document.querySelectorAll('[data-cotarm]')].map(e => {
      // arm() 的结构是：外层 div 上带那个标记，里面第一个子 div 是臂名、
      // 最后一个子 div 才是正文。
      // ⚠ 这里刻意不把标记名写进注释 —— 模板串里的 // 不是注释，
      //   会被覆盖扫描当成「判据读过的标记」（C2b 就是为这件事设的）。
      const kids = [...e.children];
      const bodyEl = kids.length >= 2 ? kids[kids.length - 1] : null;
      return { key: e.getAttribute('data-cotarm'),
               label: t(kids[0]),
               body: t(bodyEl),
               bodyLen: (t(bodyEl) || '').length };
    });
  })()`);
  const cotKeys = (cotTxt || []).map(x => x.key);
  const cotOk = cotKeys.length === 2 && ['primary', 'shadow'].every(k => cotKeys.includes(k))
    && (cotTxt || []).every(x => x.body && x.body.length >= 40);
  // ⚠ 比正文，不比整段（含臂名）—— 见上面那条
  const bodies = (cotTxt || []).map(x => x.body);
  const cotDiff = bodies.length === 2 && bodies[0] && bodies[1] && bodies[0] !== bodies[1];
  // 再加一条：正文不许只差一点点（差 <5% 的话「逐字对照」几乎没信息量）
  let nearSame = false;
  if (bodies.length === 2 && bodies[0] && bodies[1]) {
    const a = bodies[0], b = bodies[1];
    let same = 0;
    const n = Math.min(a.length, b.length);
    for (let i = 0; i < n; i++) if (a[i] === b[i]) same++;
    if (same / n > 0.95) nearSame = true;
  }
  rec('W6 data-cotarm 的两个臂（primary / shadow）必须都在、正文都非空，'
      + '而且**正文**必须确实不同（⚠ 只比正文：臂名也在那个 div 里，比整段会恒真）',
      cotOk && cotDiff && !nearSame,
      `键 ${JSON.stringify(cotKeys)}　正文字数 ${bodies.map(x => (x || '').length).join(' / ')}`
      + `　臂名 ${(cotTxt || []).map(x => x.label).join(' / ')}`
      + (cotDiff ? (nearSame ? '　⚠ 前缀 95% 相同 ⇒ 逐字对照几乎没信息量'
                              : '　两臂正文确实不同 ✅') : '　❌ 两臂正文一字不差 ⇒ 这块什么也没证明'));

  // ==================================================================
  // T 组（第三十三笔之五）：[data-term] —— 术语表与「首次出现就地解释」
  // ==================================================================
  // ## 这组在还什么账，同时修页面里一句**从来没为真过**的话
  //
  // `index.html:182`（改动前）写着：
  //     「verify 脚本找的是『某术语首次可见处所在的块里有没有 .inline-gloss』」
  // 实测：`inline-gloss` / `data-term` 在整个 git 历史里**只出现在 c9ee868**
  // —— 就是「给隐空间观察台加导读层」那个提交，也就是 index.html 自己。
  // **没有任何判据脚本提过它们。** ⇒ 那句话是凭空写的守卫。
  //
  // 规则本体在页面第三节上方（:242）：「术语的**第一次**出现必须就地有白话解释」。
  // 这组就是那个从未存在的判据。
  //
  // ## 这一块在隐藏浮层里
  //
  // 14 个 `[data-term]` 全在 `#orientation` 内，而那个浮层初始 `class="hide"`。
  // ⇒ 判据**必须先打开它**（点 #btnOrient），否则量的是一个读者看不到的块。
  //   这也是全链第一条真正打开那个浮层的判据（Z6 只量了其中一个块的可见性）。
  //
  // ## 判法：为什么不能只问「同块里有没有 gloss」
  //
  // 我第一版就只问「4 跳之内有没有 .inline-gloss」，结果 **11/14 合格** ——
  // 但其中 干预/对照、logit、残差流 三个是**假合格**：
  // 上一笔我给「不主张的 4 种说法」加的**「参与比」gloss 恰好在旁边**，
  // 而那个 gloss 讲的是参与比，不是它们。
  // ⇒ 「同块里有 gloss」是**形状相邻**，不是真检查。
  //   真正的判法：那个 gloss **自己的文本里得出现这个词**。
  //
  // ## 「空真」要单独算一类
  //
  // 隐空间/隐状态、范数 ‖h‖、位移 Δ 这三个词在导读正文里**一次都没出现过**，
  // 它们的首次出现就是术语表那一项 —— 而术语表项本身就是解释。
  // ⇒ 这既不是违规，也不是靠一个 gloss 撑着的合格，是**空真满足**。
  //   判据要把它单列，否则要么误报 3 个，要么为了让它们变绿去加无意义的 gloss。

  const TERMS = await page.eval(`(() => {
    const ov = document.getElementById('orientation');
    if(!ov) return { err: '没有 #orientation' };
    if(ov.classList.contains('hide')){
      const b = document.getElementById('btnOrient');
      if(b) b.click();
    }
    const shown = e => { for(let p=e; p && p!==document.body; p=p.parentElement){
        const cs = getComputedStyle(p);
        if(cs.display==='none' || cs.visibility==='hidden') return false; } return true; };
    // 阅读顺序 = TreeWalker 的顺序（文档序）
    const flow = [];
    const w = document.createTreeWalker(ov, NodeFilter.SHOW_TEXT);
    let n;
    while((n = w.nextNode())){
      const t = (n.textContent||'').replace(/\\s+/g,' ').trim();
      if(!t) continue;
      const el = n.parentElement;
      if(!el || !shown(el)) continue;
      flow.push({ el, t });
    }
    const t_ = e => (e.innerText || e.textContent || '').replace(/\\s+/g,' ').trim();
    const terms = [...ov.querySelectorAll('[data-term]')].map(e => ({
      key: e.getAttribute('data-term'),
      gterm: t_(e.querySelector('.gterm')),
      def: t_(e.querySelector('.gdef .plain')),
      where: t_(e.querySelector('.gdef .where')),
    }));
    const out = terms.map(term => {
      const words = term.gterm.split(/[\\/<｜|]/).map(s => s.trim()).filter(Boolean);
      let hit = null;
      for(let i=0;i<flow.length && !hit;i++){
        if(flow[i].el.closest('[data-term]')) continue;
        const w2 = words.find(x => x && flow[i].t.includes(x));
        if(w2) hit = { i, word:w2, text:flow[i].t, el:flow[i].el };
      }
      let glossTexts = [], aboutIt = false, aboutItOld = false;
        const restOf = gt => gt.split('')
            .filter(ch => !words.some(x => x.includes(ch)))
            .filter(ch => !/[（）()「」『』:：=＝·，,。.、;；\\s]/.test(ch))
            .join('');
        const subjectAt = gt => {
          const ps = words
            .map(x => x ? gt.indexOf(x) : -1)
            .filter(p => p >= 0);
          return ps.length ? Math.min(...ps) : -1;
        };
      if(hit){
        let q = hit.el, hop = 0;
        while(q && hop < 4){
          q.querySelectorAll('.inline-gloss').forEach(g => glossTexts.push(t_(g)));
          if(q.classList && q.classList.contains('inline-gloss')) glossTexts.push(t_(q));
          q = q.parentElement; hop++;
        }
        // ---- 「这个 gloss 是不是在**定义**这个词」，而不是「它**含有**这个词」
        //
        // ⚠⚠ 变异 M-X 揭出的是与 M-Y 不同的另一个面。
        //   M-Y：gloss 在、但只重复了术语名      ⇒ 靠「剥掉后 ≥6 字」抓到
        //   M-X：gloss 被整个删掉，判据**仍绿**   ⇒ 靠下面这条「主语位」抓到
        //
        //   M-X 怎么漏的：残差流那处真正的解释在边界段的 li 元素里（那一处
        //   gloss 是上一笔刚补上的），可正文里**更早**有个讲「干预 / 对照」的
        //   gloss，写着「人为往残差流里推一把」—— 那个 gloss 的主语是「干预」，
        //   残差流只是宾语，读者在那里**拿不到残差流的任何解释**。
        //   删掉那处真解释后，因为「含有残差流」这个条件被顺带满足了，
        //   判据照样 34/34。
        //
        // ⇒ 机械判据：该词必须落在 gloss 的**主语位**（起始位置 ≤ 4 字），
        //   且其后还剩实质内容。
        //   ⚠ 不用「=／：／，」这些符号去猜连接关系 —— 写法一变就失效，
        //     那又回到「形状匹配」。问的是「这个词是不是这段解释在讲的」，
        //     用位置判，且判据侧独立于页面的具体措辞。
        // ⚠⚠ 这段代码在 page.eval 的**模板串**里，有三个坑，每个都踩过：
        //   ① 反斜杠被再解释一层 —— 文件里写两个，页面里只剩一个，
        //      '\\' 就成了未终止字符串 ⇒ SyntaxError: Invalid or unexpected token
        //      （我第一版用 replace 做正则转义，崩在这里）
        //   ② 美元号紧跟左花括号会被当插值 ⇒ Missing } in template expression
        //   ③ 反引号会**截断**整个模板串
        //   ⇒ 干脆一个正则都不写：indexOf 就是字面匹配，既没有转义问题，
        //     又比 new RegExp 更严 —— 术语名里的 ‖h‖、Δ 本来就不该被当正则。
        // 旧口径只留作诊断对照（它就是让 M-X 漏过去的那个条件）
        aboutItOld = glossTexts.some(gt =>
          words.some(x => x && gt.includes(x)) && restOf(gt).length >= 6);
        aboutIt = glossTexts.some(gt => {
          const p = subjectAt(gt);
          return p >= 0 && p <= 4 && restOf(gt).length >= 6;
        });
      }
      return { key:term.key, gterm:term.gterm, words,
               firstAt: hit ? hit.i : null, firstWord: hit ? hit.word : null,
               ctx: hit ? hit.text.slice(0,40) : null,
               aboutIt, aboutItOld,
               subjectAt: hit ? subjectAt(glossTexts[0] || '') : -1,
               glossSample: glossTexts.slice(0,2).map(x => x.slice(0,28)),
               def: term.def, where: term.where };
    });
    return { flowLen: flow.length, count: terms.length, out,
             opened: !ov.classList.contains('hide') };
  })()`);
  const TL = (TERMS && TERMS.out) || [];

  rec('T0 这一组跑之前必须**打开 #orientation 浮层**（14 个 [data-term] 全在里面，'
      + '而它初始 class="hide"）—— 这是全链第一条真正打开那个浮层的判据',
      !!(TERMS && !TERMS.err && TERMS.opened && TERMS.count === 14 && TERMS.flowLen > 50),
      (TERMS && TERMS.err) ? TERMS.err
        : `浮层已展开=${TERMS.opened}　文本节点 ${TERMS.flowLen} 个　术语 ${TERMS.count} 条`);

  console.log('\n--- T 组逐条诊断：14 条术语的首次出现落点 + 新旧两套 gloss 判定 ---');
  for (const t of TL) {
    console.log('  ' + String(t.gterm).padEnd(17)
      + 'firstAt=' + String(t.firstAt).padEnd(5)
      + ' 旧=' + (t.aboutItOld ? 'Y' : 'n')
      + ' 新=' + (t.aboutIt ? 'Y' : 'n')
      + ' gloss[0]主语位=' + String(t.subjectAt).padEnd(3)
      + ' 首个 gloss=「' + (t.glossSample[0] || '—').slice(0, 24) + '」');
  }
  const vacT = TL.filter(t => t.firstAt === null).map(t => t.gterm);
  const badT = TL.filter(t => t.firstAt !== null && !t.aboutIt);
  const okT  = TL.filter(t => t.firstAt !== null && t.aboutIt);
  // ⚠ 期望的三个数是**回归锁**，改它们要写清为什么。
  //   写下这一组时实测是 合格 8 / 空真 3 / 违规 3（残差流、干预-对照、logit
  //   在判决性段落里首次出现而附近没有讲它们的 gloss）⇒ 已给那三处补上，
  //   所以现在是 11 / 3 / 0。
  //   「空真 3」不该动：隐空间/隐状态、范数 ‖h‖、位移 Δ 在导读正文里一次都没出现，
  //   它们的首次出现就是术语表那一项，而那一项本身就是解释。
  //   ⇒ 要让这三个从「空真」变成「合格」，唯一的办法是在正文里先用它们，
  //      而不是为了凑数去加一个无意义的 gloss（我第一版给残差流写的
  //      `<i class="inline-gloss">残差流</i>` 就是这种东西：它让判据变绿，
  //      却没给读者多一个字 —— 那叫骗判据，不叫修）。
  rec('T1 每个术语的**第一次出现**处必须有一个**在讲它自己**的 .inline-gloss'
      + '（⚠ 不能只问「同块里有没有 gloss」：上一笔加的「参与比」gloss 就在旁边，'
      + '会把 干预/对照、logit、残差流 三个假合格）',
      badT.length === 0 && TL.length === 14 && vacT.length === 3 && okT.length === 11,
      `合格 ${okT.length}（期望 11）　空真 ${vacT.length}（${vacT.join('、') || '无'}，期望 3）`
      + `　违规 ${badT.length}（期望 0）`
      + (badT.length ? '　⚠ ' + badT.map(t => `${t.gterm}@「${(t.ctx || '').slice(0, 16)}」`).join('；') : '')
      + (TL.length !== 14 ? `　⚠ 只读到 ${TL.length} 条 ⇒ 空真` : ''));

  // ---- T2：术语表每一项都要有「白话解释」和「在哪儿看」两栏，且都非空 ----
  // ⚠ `data-term` 存在的意义就是「这个词在这里被解释」。
  //   只印术语名、不印解释的条目，读者点进来什么也没得到。
  const thinT = TL.filter(t => !t.def || t.def.length < 8 || !t.where || t.where.length < 4)
                  .map(t => `${t.gterm}（释义 ${(t.def || '').length} 字 / 去哪看 ${(t.where || '').length} 字）`);
  rec('T2 术语表每一项都必须同时有「白话解释」与「在哪儿看」两栏，且都非空',
      thinT.length === 0 && TL.length === 14,
      thinT.length ? `残缺 ${thinT.length} 条：${thinT.slice(0, 3).join('；')}`
                   : `14 项的释义与去向都非空（最长释义 ${
        Math.max(...TL.map(t => (t.def || '').length))} 字）`);

  // ---- T3：术语表里指认的界面元素必须真的在页面上（否则「在哪儿看」指了个不存在的东西）----
  // ⚠ 「在哪儿看：左边「当前层」滑块」这类指引如果指向一个不存在的控件，
  //   比没有指引更糟。核法：从「在哪儿看」那栏里抠出所有「」里的引号短语，
  //   逐个问「页面上可见文字里有没有它」。
  //
  // ⚠⚠ 变异 M-AA 揭出这条判据**自己**是恒真的。原先匹配集取
  //   document.body.innerText —— **整页**，而术语表第 2 项的「在哪儿看」
  //   原文就写着「左边「当前 token」滑块」：
  //     :286  术语表自己（被判的那句话本身）
  //     :276  浮层内导读文案「把「当前 token」滑块拖到第 5 步」
  //   ⇒ 把那个 label 改成「当前词」，T3 照样 34/34。
  //   **被判句自己算命中** —— 这跟 T1 最早那版「同块里有 gloss」是同一个病。
  // ⇒ 修法：匹配集必须**排除整个 #orientation 浮层**。
  //   理由不是「排除自己」这种技术性理由，而是有原则的那条：
  //   术语表「在哪儿看」指认的控件**全部在浮层之外**（左边滑块、右上表、
  //   中间图）。拿浮层里的文字去证明「那个控件还在」，逻辑上就说不通 ——
  //   读者是被指引**走出**这张表去按那个滑块的。
  // ⇒ T1 不同：它要量的是「正文里首次出现有没有解释」，而浮层内的导读文案
  //   **就是正文**，所以 T1 只排 [data-term] 那一格，不排整层。
  const UI = TL.map(t => ({
    key: t.key,
    quoted: [...(t.where || '').matchAll(/「([^」]+)」/g)].map(m => m[1]),
  })).filter(x => x.quoted.length);
  // ⚠ 匹配集 = 整页可见文字 **减去整个 #orientation 浮层**（理由见上）。
  //   逐文本节点走 because 要逐个判可见性；innerText 取不到「排除某棵子树」。
  const visible = await page.eval(`(() => {
    const shown = e => { for(let p=e; p && p!==document.body; p=p.parentElement){
      const cs = getComputedStyle(p);
      if(cs.display==='none' || cs.visibility==='hidden') return false; } return true; };
    const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const out = []; let n;
    while((n = w.nextNode())){
      const p = n.parentElement;
      if(!p || !shown(p)) continue;
      if(p.closest('#orientation')) continue;
      const s = (n.textContent||'').replace(/\\s+/g,' ').trim();
      if(s) out.push(s);
    }
    return out.join(' ');
  })()`);
  const missUI = [];
  for (const u of UI) {
    for (const q of u.quoted) {
      // 「中间图上方那行」这类是指路而不是控件名，跳过明显不是控件的
      if (q.length < 2) continue;
      if (!visible.includes(q)) missUI.push(`${u.key} 指的「${q}」在页面上找不到`);
    }
  }
  rec('T3 术语表「在哪儿看」里点名的界面文字，必须在页面上真的找得到'
      + '（指了个不存在的控件比没有指引更糟）',
      missUI.length === 0 && UI.length >= 8,
      UI.length < 8 ? `⚠ 只解析出 ${UI.length} 条指引 ⇒ 空真，不计通过`
        : (missUI.length ? `${missUI.length} 处找不到：${missUI.slice(0, 3).join('；')}`
                         : `${UI.length} 条指引共点到 ${UI.reduce((a, b) => a + b.quoted.length, 0)} 个界面文字，全部找得到`));

  // ================= U 组：导读「用页面上真实的数字走一遍」 =================
  //
  // ## 为什么单独一组
  //
  // T 组刚把第三节那 14 块术语表还掉。剩下的是第二节那 **10 段**，
  // 而它们**连 data-* 标记都没有** —— :262 那条注释只登记了「两段」
  // （data-latent-lead 与 data-latent-not-claimed），**完全没提这 10 段**
  // ⇒ 既没标记、也没被判据读、也没被注释覆盖。
  // 它们是全页**唯一**一处把动态数字串成可跟读路径的地方。
  //
  // ## 这一组当场揭出的是一条**写在页面上的错数**
  //
  // 第二节有两处把白话绑死在具体数上。实测（manifest.json 的
  // trajectories[0]；applyWalkthroughFacts 硬钉它，换题也不跟着变）：
  //
  //              1.7B      0.6B      导读说的
  //   top1@0   1.0000    0.9995     「100% 确定」    两模型都成立
  //   tok@5    's        's         「正在写 's」     两模型都成立
  //   top1@5   0.7773    0.6776     「七次半」=0.75   **两个模型都不对**
  //
  // 而 :624-629 的注释自己写着："a guide that says 2048 while the page is
  // showing a 1024-wide model is worse than no guide: it is confidently,
  // checkably false." ⇒ **页面定了这条规则，导读违反了它。**
  // 已改成「它最有把握写 's，但远没到确定——同一行第二个数就是这个把握」。
  //
  // ## 期望值一律判据侧手写
  //
  // ⚠ 不从导读里抽期望值（那等于「判据与产品共用同一份手抄」）：
  //   token 文本、top1 阈值、禁用的量词全部写死在这里；
  //   而**枚举**（有哪些模型）从 models.json 反推。
  const EXP_TOK0  = '<think>';   // 导读说「模型正准备写 <think>」
  const EXP_TOK5  = "'s";        // 导读说「它正在写 's」
  const EXP_T0MIN = 0.99;        // 导读说「100% 确定」
  const BANNED    = ['次半'];    // 把概率绑死成「N 次半」的说法

  const MANIFEST = {
    '1p7b': JSON.parse(readFileSync(DATA + 'manifest.json', 'utf8')),
    '0p6b': JSON.parse(readFileSync(DATA + '../data06/manifest.json', 'utf8')),
  };
  const fac = (mid, k) => {
    const t0 = MANIFEST[mid].trajectories[0];
    const tk = t0.tokens[k];
    return { nTotal: t0.n_tokens_total, s: tk.s, ent: tk.ent, top1: tk.top1 };
  };
  const pairTxt = f => f.ent.toFixed(3) + ' / ' + f.top1.toFixed(3);

  const READ = `(() => {
    const ov = document.getElementById('orientation');
    if(ov && ov.classList.contains('hide')){
      const b = document.getElementById('btnOrient'); if(b) b.click();
    }
    const lead = document.querySelector('[data-latent-lead]');
    const ex = document.querySelector('#orientBody .ex');
    // ⚠ 按 [data-lead-seg] 取，**不按位置**（按位置取是位置依赖的选择器）。
    //   ⚠⚠ 这几行注释在 page.eval 的**模板串**里，写反引号会把模板串**截断**
    //     —— 症状是 ReferenceError: div is not defined，出现在注释里那个
    //     选择器的**最后一个词**上，看着像代码出错，其实是字符串提前闭合了。
    //     （这一轮第三次踩：判据名里的裸单引号、更早的注释里的反引号。）
    //   has0/has5 记下哪一段装着 walkEnt0 / walkEnt5 两个槽 ——
    //   U1 也据此定位，不用「第 1 段 / 第 5 段」这种下标。
    const segs = ex ? [...ex.querySelectorAll('[data-lead-seg]')].map(d => ({
      id: d.getAttribute('data-lead-seg'),
      n: (d.innerText||'').replace(/\\s+/g,' ').trim().length,
      bs: [...d.querySelectorAll('b')].map(b => (b.textContent||'').trim()),
      has0: !!d.querySelector('#walkEnt0'),
      has5: !!d.querySelector('#walkEnt5'),
    })) : [];
    const g = id => String((document.getElementById(id)||{}).textContent||'').trim();
    return {
      open: ov ? !ov.classList.contains('hide') : false,
      leadLen: lead ? lead.innerText.trim().length : 0,
      nSeg: segs.length, segs,
      walkEnt0: g('walkEnt0'), walkEnt5: g('walkEnt5'), walkTok: g('walkTok'),
      exText: ex ? (ex.innerText||'').replace(/\\s+/g,' ') : '',
      modelId: (typeof S !== 'undefined' && S.model) ? S.model.id : null,
    };
  })()`;

  // ⚠ 两个 token 的定位机制**故意不同**，因为它们在页面上的位置就不同：
  //   第 0 步的 `<think>` 在**第一条**导览里，那一段**不含任何 walkEnt 槽**
  //   第 5 步的 's 在**装着 walkEnt5 那个槽**的那一段里
  // 我第一版把两者都用 has0/has5 定位 ⇒ U1/U6 直接红：
  // walkEnt0 落在第 4 段（不是第 1 段），取它的 bs[1] 拿到的是 undefined。
  // ⇒ 「第 0 步」按标记值最小者（语义上就是「页面刚打开时的状态」），
  //   「第 5 步」按槽定位（最稳：槽的 id 是全局唯一的）。
  const segWith = (g, key) => g.segs.find(x => x[key]) || null;
  const firstSeg = g => g.segs.slice()
    .sort((a, b) => Number(a.id) - Number(b.id))[0] || null;
  const tokAt0 = g => (firstSeg(g) && firstSeg(g).bs[1]) || null;
  const tokAt5 = g => (segWith(g, 'has5') && segWith(g, 'has5').bs[1]) || null;

  // ---------------- 1.7B ----------------
  const g17 = await page.eval(READ);
  const u0 = fac('1p7b', 0), u5 = fac('1p7b', 5);
  const uThin = g17.segs.filter(s => s.n < 10);

  rec('U0 导读第二节那 10 段必须**全部在 DOM、可见、且各有实质文字**'
      + '（⚠ 它们连 data-* 标记都没有，:262 的注释也只登记了「两段」——'
      + '「没标记」不等于「没人读」—— 第三十三笔之六给它们真加了 data-lead-seg）',
      g17.open && g17.leadLen >= 40 && g17.nSeg === 10 && uThin.length === 0,
      `浮层展开=${g17.open}　data-latent-lead ${g17.leadLen} 字　第二节 ${g17.nSeg} 段`
      + (uThin.length ? `　⚠ ${uThin.length} 段不足 10 字` : '')
      + (g17.nSeg !== 10 ? `　⚠ 期望 10 段` : ''));

  rec('U1 导读点名的两个 token（`<think>` 与单引号 s）必须是该模型产物的真实值'
      + '（导读把它们写死在 HTML 里；换题/换模型后可能不再成立）',
      tokAt0(g17) === u0.s && tokAt5(g17) === u5.s
        && u0.s === EXP_TOK0 && u5.s === EXP_TOK5,
      `页面上写 第0步=「${tokAt0(g17)}」 第5步=「${tokAt5(g17)}」`
      + `　产物 第0步=「${u0.s}」 第5步=「${u5.s}」`
      + `　判据期望 「${EXP_TOK0}」/「${EXP_TOK5}」`);

  rec('U2 导读说「它 100% 确定要写这个词」——tokens[0].top1 必须 ≥ 0.99'
      + '（阈值判据侧手写；白话里的「100%」对应 ≥0.99，不是恰好 1）',
      u0.top1 >= EXP_T0MIN && g17.exText.includes('100% 确定'),
      `tokens[0].top1 = ${u0.top1}（熵 ${u0.ent.toFixed(4)}）　阈值 ≥${EXP_T0MIN}`
      + `　导读写着「100% 确定」=${g17.exText.includes('100% 确定')}`);

  rec('U3 `walkEnt0` / `walkEnt5` 印的「熵 / top1」必须逐位等于产物里那两个数'
      + '（⚠ 期望值取自 manifest，**不是**从页面读回来再比自己）',
      g17.walkEnt0 === pairTxt(u0) && g17.walkEnt5 === pairTxt(u5),
      `walkEnt0 页面「${g17.walkEnt0}」 vs 产物「${pairTxt(u0)}」　`
      + `walkEnt5 页面「${g17.walkEnt5}」 vs 产物「${pairTxt(u5)}」`);

  const ban17 = BANNED.filter(w => g17.exText.includes(w));
  rec('U4 导读不许把 top1 概率绑死成「N 次半」这种量词'
      + '（⚠ 只堵这个量词形，不是通用检测；写「0.75 的把握」它就漏了 —— '
      + 'U3 兜的是页面那个数，兜不住白话那句话）',
      ban17.length === 0,
      ban17.length ? `⚠ 导读里出现 ${ban17.join('、')}　实测 top1@5 = ${u5.top1}`
        : `无禁用量词　实测 top1@5 = ${u5.top1}（1.7B）`);

  // ---------------- 切到 0.6B ----------------
  const U06URL = URL + (URL.includes('?') ? '&' : '?') + 'm=0p6b';
  await page.send('Page.navigate', { url: U06URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  // ⚠⚠ 预算：原来写死 40000ms（40s）。实测它在**全链里**不够用 ——
  //   2026-10-07 第 26 条全链，U5 红一次；而同一份代码**独立**连跑 3 次
  //   全是 53/53。差别是它紧跟在 20 分钟的软件光栅臂之后，机器是热的。
  //   ⇒ 这是**预算估小了**，不是被测物坏了 —— 与 scene_link 那次
  //     「150s 是按一个假停估出来的」是同一族。
  //   120s 的依据：实测独立跑 3 次的等待都在 3.6~7.2s 量级，
  //   留 ~15 倍余量给热机器；每轮把**实际等了多久**印出来，
  //   下次再红就能一眼看出是「超预算」还是「真不对」。
  const U06_BUDGET_MS = 120000;
  let wU = 0, okU = false, g06 = null;
  while (wU < U06_BUDGET_MS) {
    g06 = await page.eval(READ);
    // 双条件：模型 id 对上 **且** walkTok 变成 0.6B 自己的总步数
    // （静态值是「—」，只有 applyWalkthroughFacts 跑过才会变）
    if (g06 && g06.modelId === '0p6b' && g06.walkTok === '384' && g06.open) { okU = true; break; }
    await sleep(1200); wU += 1200;
  }
  const u0b = fac('0p6b', 0), u5b = fac('0p6b', 5);

  // ⚠⚠⚠ 这一条**只**问「仪器到位没有」。数值对不对是下一条 U5b 的事。
  //   原来两者合成一条，于是「页面没在预算内切到 0.6B」与「导览数值是错的」
  //   报出**同一个判决**：都是 FAIL，都占一个 N/M。
  //   而这两种红的**责任方不同** —— 前者要查页面加载/服务器，后者要查文案。
  //   合并的那版，理由行写「仪器没到位」、判决却写 FAIL，
  //   正是本仓反复出现的那类「消息与代码各说各话」。
  //   ⇒ 拆开。U5a 红了就说明「这一组还没测成」，不必再猜是哪一种。
  rec('U5a 0.6B 那一页必须在预算内切到目标状态（**前置**；它红不代表导览数值错）'
      + `（预算 ${U06_BUDGET_MS}ms，实测空闲时约 1.2s）`,
      okU,
      okU ? `等了 ${wU}ms　modelId=${g06.modelId} walkTok=${g06.walkTok} open=${g06.open}`
        : `⚠ 仪器没到位：等了 ${wU}ms（预算 ${U06_BUDGET_MS}ms），`
          + `modelId=${(g06 && g06.modelId)} walkTok=${(g06 && g06.walkTok)}`
          + ` open=${(g06 && g06.open)}`
          + `　（open=false ＝ 导读还没展开；walkTok 仍是「—」＝ applyWalkthroughFacts 没跑完。`
          + `这一条 2026-10-07 在全链里红过一次、同一份代码独立跑 3 次全绿，`
          + `**根因未查明** —— 本条的存在就是为了下次红时能一眼定位。）`);

  rec('U5b 切到 0.6B 后同一批导览必须**换成 0.6B 自己的数**'
      + '（只核 1.7B 下对是发现不了「七次半」那类缺陷的：静态文案两个模型都一样长）',
      okU && g06.walkEnt0 === pairTxt(u0b) && g06.walkEnt5 === pairTxt(u5b)
        && g06.walkEnt0 !== g17.walkEnt0 && g06.walkEnt5 !== g17.walkEnt5,
      okU ? `?m=0p6b（walkTok=${g06.walkTok}，等了 ${wU}ms）　`
            + `walkEnt0「${g06.walkEnt0}」vs 产物「${pairTxt(u0b)}」　`
            + `walkEnt5「${g06.walkEnt5}」vs 产物「${pairTxt(u5b)}」`
          : `未判：前置 U5a 没成立，页面还没切到 0.6B 状态，`
            + `此时比 walkEnt 会拿 1.7B 的数去对 0.6B 的产物，判红是假的`);

  rec('U6 0.6B 下导读点名的两个 token 仍须等于 0.6B 产物的真实值',
      tokAt0(g06) === u0b.s && tokAt5(g06) === u5b.s
        && u0b.s === EXP_TOK0 && u5b.s === EXP_TOK5,
      `页面上写 第0步=「${tokAt0(g06)}」 第5步=「${tokAt5(g06)}」`
      + `　0.6B 产物 第0步=「${u0b.s}」 第5步=「${u5b.s}」`
      + `　⚠ 注意两者 top1@5 不同：1.7B ${u5.top1} / 0.6B ${u5b.top1}`);

  rec('U7 0.6B 下导读仍不许把概率绑死成量词'
      + '（这一条在改文案之前是红的：实测 0.6B 的 top1@5 = '
      + `${u5b.top1}，与 1.7B 的 ${u5.top1} 也不同 ⇒ 任何写死的次数都不可能对）`,
      BANNED.every(w => !g06.exText.includes(w)),
      BANNED.filter(w => g06.exText.includes(w)).length
        ? `⚠ 出现 ${BANNED.filter(w => g06.exText.includes(w)).join('、')}`
        : `无禁用量词　0.6B 实测 top1@5 = ${u5b.top1}`);

  // ---------------- 切回 1.7B ----------------
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  let wB = 0, okB = false;
  while (wB < 40000) {
    const b = await page.eval(READ);
    if (b && b.modelId === '1p7b' && b.walkTok === '1024') { okB = true; break; }
    await sleep(1200); wB += 1200;
  }
  rec('U8 这一组跑完必须**导航回 1.7B**'
      + '（它把页面切到 ?m=0p6b 了；Z7 切、U5 又切，不切回来下一组读到的是 0.6B 的数）',
      okB, okB ? `已回到 1.7B（walkTok=${1024}，等了 ${wB}ms）`
               : `⚠ 等了 ${wB}ms 仍没回到 1.7B`);

  // ================= V 组：导读「五 · 这些数字的边界」的 4 条声明 =================
  //
  // ## 为什么单独一组
  //
  // 普查发现：`scan_panel_coverage.py` **从头到尾没有出现过 orientation /
  // btnOrient** ⇒ 它从不打开那个浮层 ⇒ **C5 的「26 段」与 C6 的
  // 「真孤儿 0」都只对浮层外成立**。把同一套口径搬进浮层重跑，
  // 那里有 20 个「C6 口径下的真孤儿」，其中 14 条子树也没有标记。
  //
  // 这 14 条里最要紧的是**「五 · 这些数字的边界」整节 4 条 `<li>`** ——
  // 它是全页的诚实性清单（「我只在多小的范围内测过」），
  // 而它**一条都没有 data-* 标记**，因此不在 C4 的矩阵里、不在欠账表上、
  // 也没有任何判据读过。
  //
  // ## 这一组当场抓到的是一条**三重错的边界声明**
  //
  // 原文：「只有 6 道题做过"干预 vs 对照"（题号 1983 到 1988 连续 6 道）」
  // 实测自 answer_readout.json：
  //     n_in_screen = 10        items = 10 条
  //     题号 = 1984/1987/1990/1991/1994/2000/2004/2014/2020/2025
  //   ⇒ 道数错（6→10）、区间错（1983–1988→1984–2025）、而且**根本不连续**。
  //   而**同一屏**另一处就写着「这 10 道题不是历年 AIME 原题」
  //   ⇒ 读者能同时看到 6 和 10 两个数。
  //
  // ⚠ 这比「七次半」严重：那是数值偏了 0.027，这是**边界声明本身错了**，
  //   而它的作用恰恰是「限制主张」。
  //
  // ## 期望值一律判据侧手写；枚举（有哪些模型）从 models.json 反推。
  const V_EXP = {
    nProblems: 10,      // 这一屏做过干预 vs 对照的题数
    idMin: 1984,        // 题号下界
    idMax: 2025,        // 题号上界
    dirLayer: 20,       // 唯一的干预方向在第几层
    dirStrength: 0.2,   // 强度
  };
  const vAR = JSON.parse(readFileSync(
    '/Users/zhourui/code/steer3d/frontend/public/latent/data/answer_readout.json', 'utf8'));
  const vSD = JSON.parse(readFileSync(
    '/Users/zhourui/code/steer3d/frontend/public/latent/data/steer_directions.json', 'utf8'));
  const vREG = JSON.parse(readFileSync(
    '/Users/zhourui/code/steer3d/frontend/public/latent/models.json', 'utf8')).models;
  const m17 = vREG.find(x => x.id === '1p7b') || {};
  const m06 = vREG.find(x => x.id === '0p6b') || {};

  // 题号：label 形如 1984_I_1
  const idOf = it => {
    const m = String(it.label || '').match(/^(\d{4})_/);
    return m ? Number(m[1]) : null;
  };
  const IDS = vAR.items.map(idOf).filter(x => x != null).sort((a, b) => a - b);
  const contiguous = IDS.every((x, i) => i === 0 || x - IDS[i - 1] === 1);

  const VBOUND = `(() => {
    const ov = document.getElementById('orientation');
    if(ov && ov.classList.contains('hide')){
      const b = document.getElementById('btnOrient'); if(b) b.click();
    }
    const t = e => (e.innerText || '').replace(/\\s+/g, ' ').trim();
    const out = {};
    for(const e of document.querySelectorAll('[data-bound]')){
      out[e.getAttribute('data-bound')] = t(e);
    }
    // ⚠⚠ 槽必须**限定在这条声明自己身上**，不能用全页第一个匹配。
    //   页面里有**两个** [data-f="label"]：声明里 index.html:314 一个、
    //   h1 标题 :334 一个。文档序里声明在前，所以全页 querySelector
    //   在**基线下恰好读对**。
    //   但一旦声明里那个槽被删掉（变异 M-AK），取法会**静默漂移到 h1**，
    //   而 h1 照样被 applyModelFacts() 填成 0.6B ⇒ **V5 假绿**。
    //   这就是「判据认的是对象，不是属性」：同一个属性值有两个宿主时，
    //   「第一个」不是判据想要的那个，且它在变异下会自己换人。
    const liM = document.querySelector('[data-bound="model"]');
    const slotM = liM ? liM.querySelector('[data-f="label"]') : null;
    return { texts: out, n: Object.keys(out).length,
             liModel: liM ? t(liM) : null,
             slotModel: slotM ? t(slotM) : null,
             nLabelSlots: document.querySelectorAll('[data-f="label"]').length };
  })()`;

  const vB = await page.eval(VBOUND);
  const vWantKeys = ['n-problems', 'model', 'n-dirs', 'summary'];
  const vMissKeys = vWantKeys.filter(k => !vB.texts[k]);
  const vThinB = vWantKeys.filter(k => vB.texts[k] && vB.texts[k].length < 20);

  rec('V0 「五 · 这些数字的边界」那 4 条必须**全部在 DOM、可见、各有实质文字**'
      + '（⚠ 普查发现它们原先一个 data-* 都没有 ⇒ 不进 C4 矩阵、不在欠账表上、无人读）',
      vB.n === 4 && vMissKeys.length === 0 && vThinB.length === 0,
      `读到 ${vB.n} 条（期望 4）`
      + (vMissKeys.length ? `　⚠ 缺 ${vMissKeys.join('、')}` : '')
      + (vThinB.length ? `　⚠ ${vThinB.length} 条不足 20 字` : ''));

  rec('V1 「只有 N 道题做过干预 vs 对照」——N 必须等于 answer_readout 的 '
      + '`problem_set.n_in_screen`，而且页面上印的就是它（⚠ 别拿 `both_in_domain` '
      + '顶替：它是「两臂答案都在定义域内」，不是「两臂都跑完」）',
      vAR.problem_set.n_in_screen === V_EXP.nProblems
        && vAR.items.length === V_EXP.nProblems
        && /\b10\b/.test(vB.texts['n-problems'] || ''),
      `产物 n_in_screen=${vAR.problem_set.n_in_screen}　items=${vAR.items.length}`
      + `　期望 ${V_EXP.nProblems}　页面写「${(vB.texts['n-problems'] || '').slice(0, 18)}…」`);

  rec('V2 「题号从 lo 到 hi，且**不连续**」——lo/hi 与「不连续」三件事都要与产物吻合'
      + '（⚠ 原文写的是「1983 到 1988 连续 6 道」，而产物里 1983 根本不在这一批）',
      IDS.length === V_EXP.nProblems && IDS[0] === V_EXP.idMin
        && IDS[IDS.length - 1] === V_EXP.idMax && contiguous === false
        && (vB.texts['n-problems'] || '').includes('1984')
        && (vB.texts['n-problems'] || '').includes('2025')
        && (vB.texts['n-problems'] || '').includes('不连续'),
      `产物题号 ${IDS[0]}–${IDS[IDS.length - 1]}（${IDS.length} 个，`
      + `连续=${contiguous}）　期望 ${V_EXP.idMin}–${V_EXP.idMax} 且连续=false`);

  rec('V3 「本页是 X；两个尺寸都收录了（层数相同、只差宽度）」——两个模型的层数必须真的相同、'
      + '宽度必须真的不同；且这句话必须写的是**当前**模型的名字（读**声明自己**的文字，'
      + '并要求不含另一个模型的名字；⚠ 本条**只核 1.7B 下的内容**，'
      + '「这句到底绑没绑」由 V5 核——静态文本在这一条下是查不出来的）',
      m17.n_layers === m06.n_layers && Number(m17.d_model) !== Number(m06.d_model)
        && !!m17.label && !!m06.label
        && (vB.liModel || '').includes(m17.label)
        && !(vB.liModel || '').includes(m06.label),
      `models.json 层数 1.7B=${m17.n_layers} / 0.6B=${m06.n_layers}`
      + `（相同=${m17.n_layers === m06.n_layers}）　宽度 ${m17.d_model} vs ${m06.d_model}`
      + `（不同=${Number(m17.d_model) !== Number(m06.d_model)}）`
      + `　那条声明写「${(vB.liModel || '').slice(0, 22)}…」`);

  rec('V4 「只有 1 个干预方向（第 L 层，强度 S）」——L 与 S 必须等于 '
      + '`steer_directions.json` 的 layer / strength（⚠ 本条**只核 L 与 S**，'
      + '「只有 1 个」核不了，见下一条）',
      vSD.layer === V_EXP.dirLayer && Number(vSD.strength) === V_EXP.dirStrength
        && (vB.texts['n-dirs'] || '').includes('20')
        && (vB.texts['n-dirs'] || '').includes('0.2'),
      `产物 layer=${vSD.layer} strength=${vSD.strength}`
      + `　期望 ${V_EXP.dirLayer} / ${V_EXP.dirStrength}`
      + `　页面写「${(vB.texts['n-dirs'] || '').slice(0, 24)}…」`);

  // ---- 切到 0.6B，核 data-f="label" 真的跟着变 ----
  const V06URL = URL + (URL.includes('?') ? '&' : '?') + 'm=0p6b';
  await page.send('Page.navigate', { url: V06URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  let wV = 0, okV = false, vB6 = null;
  // ⚠ 就绪信号**只**用本条自己的条件。原来还带一个 `vB6.n === 4`，
  //   那是 V0 的「4 条都在」—— 于是 M-AJ（删掉一个 data-bound）会把 V5 一起带红，
  //   像是 V5 也依赖那条声明，其实只是就绪条件抄了 V0 的（判据耦合）。
  //   静态 HTML 里那个槽写着 "Qwen3-1.7B"，所以「槽 == 0.6B 名字」本身
  //   就不会在 applyModelFacts() 跑之前误触发。
  while (wV < 40000) {
    vB6 = await page.eval(VBOUND);
    if (vB6 && vB6.slotModel === (m06.label || '')) { okV = true; break; }
    await sleep(1200); wV += 1200;
  }
  rec('V5 切到 0.6B 后「本页是 X」这句必须**换成 0.6B 自己的名字**，'
      + '而且这个槽必须**长在这条声明里面**（⚠ 槽若被换成静态文本，全页第一个 '
      + '[data-f="label"] 会漂移到 h1 标题，判据就会看错对象而假绿 —— 实测 M-AK 就是这样）',
      okV,
      okV ? `?m=0p6b 声明里那个槽读到「${vB6.slotModel}」`
          : `⚠ 等了 ${wV}ms，声明里那个槽读到 ${JSON.stringify(vB6 && vB6.slotModel)}`
            + `（期望 ${m06.label}）　全页 [data-f="label"] 共 `
            + `${vB6 && vB6.nLabelSlots} 个　4 条声明里读到 ${vB6 && vB6.n} 条`);

  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  let wV2 = 0, okV2 = false;
  while (wV2 < 40000) {
    const b = await page.eval(`(() => ({
      id: (typeof S !== 'undefined' && S.model) ? S.model.id : null,
      walkTok: String((document.getElementById('walkTok')||{}).textContent||'').trim(),
    }))()`);
    if (b && b.id === '1p7b' && b.walkTok === '1024') { okV2 = true; break; }
    await sleep(1200); wV2 += 1200;
  }
  rec('V6 这一组跑完必须**导航回 1.7B**（V5 把页面切到 ?m=0p6b 了，'
      + '而 answer_readout.json / steer_directions.json 只在 1.7B 的 data/ 里）',
      okV2, okV2 ? `已回到 1.7B（walkTok=1024，等了 ${wV2}ms）`
                 : `⚠ 等了 ${wV2}ms 仍没回到 1.7B`);

  console.log('\n=== %d/%d passed ===', pass, total);
  rows.filter(r => !r[0]).forEach(r => console.log('FAIL: ' + r[1]));
  process.exitCode = (pass === total) ? 0 : 1;
} catch (e) {
  console.log('[FAIL] X 组脚本崩了：%s\n%s', e.message, e.stack);
  process.exitCode = 1;
} finally {
  try { await cdp.send('Browser.close'); } catch {}
  try { proc.kill(); } catch {}
}
