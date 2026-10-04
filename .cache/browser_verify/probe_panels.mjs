import { launch, Page, CDP } from './cdp_client.mjs';

/**
 * 面板覆盖矩阵的第一步：**页面上真实存在哪些块**。
 *
 * ⚠ 这份探针只报「DOM 里有什么」，**不报「它被不被判据读」** ——
 *   那半张表在 python 侧做（scan_panel_coverage.py），两边用 data-* 交叉核对。
 * ⚠ 判据主体必须是**读者看到的可见文案**。这里刻意同时报 `textContent` 长度与
 *   `innerText` 长度：折叠 `<details>` 里 innerText 只给 summary，
 *   两者的差就是一个「看得见但被折叠」的量。
 *
 * ⚠⚠ 第二十三笔：这份探针原来只跑**一个页面**（Next.js 根页），
 *   而 scan_panel_coverage.py 的「判据读过的标记」集合是把**所有**
 *   verify*.mjs 的 data-* **无差别合并**的 —— 于是打 `/latent/index.html`
 *   的两条判据（backmap / divergence_readout）读的标记，在根页 DOM 里
 *   根本不存在，被 C2 报成 5 个「死引用」。
 *   ⇒ 死的是**扫描器的分页假设**，不是判据，也不是产品。
 *   ⇒ 现在探针按页参数化（PROBE_OUT / PROBE_PAGE），两页都出清单，
 *     python 侧把两页 DOM 合并后再对账；并新增「源码里有、
 *     交互后仍不渲染」这一类（C7）—— 本轮发现的那块
 *     「为什么最后吐出的是这个词」正是这一类，旧的探针看不见它。
 */
const URL = process.env.BV_URL || 'http://127.0.0.1:21540/';
const OUT = process.env.PROBE_OUT
  || '/Users/zhourui/code/steer3d/.cache/browser_verify/panel_blocks.json';
// 就绪信号分页：根页等干预结果面板 ready（它要 fetch 五份 JSON）；
// latent 静态页没有 data-outcome，等候选词读出块（data-dvblock）出现。
const IS_LATENT = /\/latent\//.test(URL);
const READY_SEL = IS_LATENT ? '[data-dvblock]' : '[data-outcome="ready"]';
const READY_ATTR = IS_LATENT ? null : 'data-outcome';
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_cov_' + process.pid;
const sleep = ms => new Promise(r => setTimeout(r, ms));

const { proc, version } = await launch({
  // 端口按 pid 派生：两页要各跑一次，固定端口会撞上上一次没退干净的 Chromium。
  port: 9600 + (process.pid % 240), userDataDir: PROFILE,
  windowSize: '1900,3200', url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  await sleep(12000);

  // 等就绪信号。⚠ 根页原来写死等 data-outcome=ready，latent 页没有这个属性，
  //   照抄会空转 24 秒然后照常收工 —— 「等超时」和「等到了」长得一模一样。
  for (let i = 0; i < 20; i++) {
    const s = await page.eval(READY_ATTR
      ? `(document.querySelector('[${READY_ATTR}]')||{getAttribute:()=>''})`
        + `.getAttribute('${READY_ATTR}')||''`
      : `!!document.querySelector('${READY_SEL}')`);
    if (READY_ATTR ? s === 'ready' : s) break;
    await sleep(1200);
  }

  const B = JSON.parse(await page.eval(`(() => {
    // ⚠ 第一版把「块」定义为「没有 data-* 子节点」——
    //   结果把**面板容器自己**全排除了（data-lit-audit / data-outcome 里有
    //   data-lit-item / data-answer-power 等子节点）。266 个「顶层块」里
    //   一个面板都不是。⇒ 改成按**在 data 树里的深度**判，深度 0 才是面板根。
    const isData = e => Array.from(e.attributes).some(a => a.name.startsWith('data-'));
    const firstName = e => (Array.from(e.attributes)
      .find(a => a.name.startsWith('data-')) || {}).name;
    const depth = e => { let d = 0, p = e.parentElement; while (p) { if (isData(p)) d++; p = p.parentElement; } return d; };
    const all = Array.from(document.querySelectorAll('*')).filter(isData);
    const byDepth = {};
    for (const e of all) {
      const d = depth(e);
      // ⚠ 必须记**全部** data-* 属性名，不能只记第一个。
      //   第一版用 firstName()，于是那个 li 上的
      //   data-arm-metric / data-arm-diff / data-arm-t / data-arm-distinguishable
      //   只被记成第一个，另外三个凭空消失 ⇒ 覆盖矩阵里
      //   130 个「判据提到、页面不存在」，其中绝大多数是我漏记的。
      //   这已经是同一个探针第三次犯「少记 ⇒ 看起来像产品 bug」的错了。
      // WARNING 注释里不许出现反引号：整段 eval 体是 JS 模板字符串，
      //   注释里任何一对反引号都会把它提前截断，报 SyntaxError。
      //   而我写这条警告时自己又带上了两对，于是第二次 SyntaxError。
      //   更糟的是那次重跑我用了 > /dev/null 2>&1，失败被吞掉，
      //   Python 于是读到了上一次跑出来的旧 JSON，数字一模一样地「没变」。
      const names = Array.from(e.attributes)        .map(a => a.name).filter(n => n.startsWith('data-'));
      (byDepth[d] = byDepth[d] || []).push({
        data: names[0], all_data: names, depth: d,
        tag: e.tagName.toLowerCase(),
        tc_len: (e.textContent || '').length,
        it_len: (e.innerText || '').length,
        heading: ((e.innerText || '').split('\\n').find(l => l.trim()) || '').slice(0, 46),
      });
    }
    return JSON.stringify(byDepth);
  })()`));

  // ---- 第二十三笔新增：交互扫描 ----
  // ⚠ 为什么要点一遍：latent 静态页有一批块是**按需渲染**的
  //   （层按钮 / 方向芯片 / 题号切换之后才建 DOM）。只收「加载完那一瞬」的
  //   DOM，会把它们记成「源码里有、页面上没有」—— 那是**假红**。
  // ⇒ 收两遍：加载后 / 点过之后，两遍并集才是这一页真实的标记面。
  // ⚠⚠ 两遍的顺序是「先收 before，再点，再收 after」。
  //   我第一版把 beforeNames 也放在点击之后才采，于是两个集合必然相同、
  //   appeared 恒为空 —— 而「恒为空」看起来恰好像「交互没带出任何东西」，
  //   是一个完全合理的结果，所以它不会自己暴露。
  // ⚠ 反过来的坑更要紧：第二十三笔发现的那块
  //   「为什么最后吐出的是这个词」在源码里躺了很久、判据也读它，
  //   但**默认视图永远不渲染** ⇒ 它在第一遍里也不在。
  //   所以 python 侧要比的不是「源码 vs DOM」，而是
  //   「源码 ∧ 任何判据读过」却两遍 DOM 都没有 ⇒ 那才是真死代码。
  const NAMES_EVAL = `(() => {
    const out = [];
    for (const e of document.querySelectorAll('*')) {
      for (const a of e.attributes) {
        if (a.name.startsWith('data-') && out.indexOf(a.name) < 0) out.push(a.name);
      }
    }
    return JSON.stringify(out.sort());
  })()`;
  const beforeNames = JSON.parse(await page.eval(NAMES_EVAL));
  const clickSweep = JSON.parse(await page.eval(`(() => {
    const SEL = ['[data-dvl]', '[data-cotdir]', '[data-arpick]', '[data-bmstep]',
                 '[data-lensstep]', '[data-lenspick]', '[data-jump]', '[data-arm]',
                 '[data-cotarm]', '[data-problemset]', '[data-cotjump]',
                 '[data-arjump]'];
    const clicked = [];
    for (const s of SEL) {
      for (const e of document.querySelectorAll(s)) {
        try { e.click(); clicked.push(s); } catch (err) { /* 不可点的忽略 */ }
      }
    }
    return JSON.stringify(clicked);
  })()`));
  await sleep(2500);
  const afterNames = JSON.parse(await page.eval(NAMES_EVAL));
  const appeared = afterNames.filter(n => beforeNames.indexOf(n) < 0);
  console.log('交互扫描：点了 %d 个控件，带出 %d 个新标记 %s',
              clickSweep.length, appeared.length,
              appeared.length ? '(' + appeared.join(', ') + ')' : '');

  // ---- 第三十三笔之六：口径普查（阈值必须是量出来的，不是拍出来的）----
  // ⚠⚠ 这一步是**先量后选**的纪律：第三十三笔之六的原口径是
  //   「只扫 <p>、且 ≥40 字」，而导读浮层里 11 个真缺口有 10 个是
  //   h1/h2/div，且最短的只有 11 字 ⇒ 它们**结构性不可见**。
  //   但反过来把门槛降到 0、把元素集扩到全部标签，
  //   两页的「未读」清单会膨胀到几百条 —— 清单太长就等于没有信息。
  // ⇒ 这里把「元素集 × 长度阈值」的规模矩阵**一次量出来**写进产物，
  //   阈值的选择必须能指着这张表说清为什么。
  const CENSUS = JSON.parse(await page.eval(`(() => {
    const SEL = 'h1,h2,h3,p,li,div';
    const THRS = [0, 6, 10, 12, 16, 20, 30, 40];
    const hasData = e => Array.from(e.attributes).some(a => a.name.startsWith('data-'));
    const hasDataDesc = e => Array.from(e.querySelectorAll('*'))
      .some(c => Array.from(c.attributes).some(a => a.name.startsWith('data-')));
    const byTag = {}; const total = {}; const orphan = {};
    for (const e of document.querySelectorAll(SEL)) {
      if (hasData(e) || hasDataDesc(e)) continue;
      const t = (e.innerText || '').replace(/\\s+/g, ' ').trim();
      if (!t) continue;
      let chain = 0;
      for (let a = e.parentElement; a && a !== document.body; a = a.parentElement) {
        if (Array.from(a.attributes).some(x => x.name.startsWith('data-'))) chain++;
      }
      const tag = e.tagName.toLowerCase();
      for (const th of THRS) {
        if (t.length < th) continue;
        total[th] = (total[th] || 0) + 1;
        if (chain === 0) orphan[th] = (orphan[th] || 0) + 1;
        (byTag[tag] = byTag[tag] || {})[th] = ((byTag[tag] || {})[th] || 0) + 1;
      }
    }
    return JSON.stringify({ sel: SEL, thrs: THRS, byTag, total, orphan });
  })()`));
  // ⚠ node 的 console.log **不认** %-14s / %2d 这类带 flag 的宽度占位符
  //   （util.format 只会把 %-14 里的 -14 当普通文本，把 %d 单独消费），
  //   打印出来是一行乱码。下面一律用 padEnd/padStart 自己拼。
  console.log('口径普查（元素集 %s）：阈值 → 段数（其中祖先链为空）', CENSUS.sel);
  for (const th of CENSUS.thrs) {
    const byT = CENSUS.byTag;
    const parts = Object.keys(byT).sort().map(tg => tg + '=' + ((byT[tg][th]) || 0));
    console.log('  >= ' + String(th).padStart(2) + ' 字：合计 ' + String(CENSUS.total[th] || 0).padStart(4)
      + '（孤儿 ' + String(CENSUS.orphan[th] || 0).padStart(3) + '）  ' + parts.join(' '));
  }

  // ---- C5 的输入：有没有「大段文字、但自己一个 data-* 都不带」的块 ----
  // ⚠ 覆盖矩阵**天生看不见**这类洞：它统计的是「有标记的块」，
  //   而 D6 / G7 那两个洞正是几段**完全没有标记**的散文 ——
  //   没有标记 ⇒ 不进矩阵 ⇒ 永远不会被「未被读过」那一栏列出来。
  //   矩阵只能报「读过没有」，报不了「有没有被登记过」。
  //   ⇒ 这里单独量一遍：自身无 data-*、且无 data-* 后代、带文字的块。
  // ⚠⚠ 第三十三笔之六：元素集与阈值的**口径**变了，理由与实测规模：
  //   ① 元素集从「只扫 p」扩到 'h1,h2,h3,p,li,div'。
  //      实测（port 22208 普查）：导读浮层 #orientation 里 11 个真缺口有
  //      **10 个根本不是 <p>**（h1×1 / h2×5 / div×4），只扫 <p> 时它们
  //      一个都进不来 —— 这不是「浮层没打开」造成的（.hide 是 visibility，
  //      innerText 读得到），是**标签集太窄**造成的。
  //   ② 长度阈值从 40 降到 THRESH（见下）。
  // ⚠⚠ **阈值为什么是 10：它不是挑的，是被那 11 条决定的。**
  //   那 11 条真缺口的字数是 16 / 66 / 12 / 16 / 14 / 16 / 11 / 54 / 60 / 50 / 29
  //   ⇒ 最小的 11（`<h2>五 · 这些数字的边界`）把阈值顶死在 **≤11**：
  //     取 12 就丢掉它；取 16 一次丢 3 条；取 20 把 h1 和 5 个 h2 全丢光；
  //     取 30 连 29 字的提示语也丢。⇒ 10（留一点余量，免得「刚好 11」像运气）。
  //   规模代价（上面 census 实测，两页合计，去重前）：
  //     阈值 0 → 565 段（孤儿 140）  10 → 451（128）  20 → 325（77）
  //     阈值 30 → 224（52）         40 → 182（44）  ← 40 是旧口径量级
  //   去重后实际收 444 段（孤儿 122）。
  //   ⇒ 清单变长**不靠抬阈值**消化（那正是这个项目反复栽的坑：
  //     为了让数字好看而收窄口径），改用两条结构规则 + python 侧分层打印：
  //        - 自身无 data-* 且**无 data-* 后代**（容器不进清单，否则一个
  //          容器 + 它的 20 个子块会被重复计 21 次，清单直接失效）；
  //        - 文本**完全等于**某个候选后代 ⇒ 纯包裹元素，丢弃。
  //      留下的才是「页面上真的印着、但没有标记能定位到它」的文字。
  const THRESH = 10;
  const unmarked = JSON.parse(await page.eval(`(() => {
    const hasData = e => Array.from(e.attributes).some(a => a.name.startsWith('data-'));
    const hasDataDesc = e => [].concat(...Array.from(e.querySelectorAll('*')))
      .some(c => Array.from(c.attributes).some(a => a.name.startsWith('data-')));
    // ⚠⚠ 第三十一笔：原来这里是**写死的 8 个面板名单**
    //   ['[data-outcome]','[data-subspace]','[data-ladder]','[data-axis]',
    //    '[data-heldout]','[data-structure]','[data-law]','[data-derivation]']
    //   而根页 import 了 **15 个组件** ⇒ 名单外的面板对 C5/C6 **完全隐形**：
    //   它们既不进覆盖矩阵（无 data-*），也不进这份清单（不在 roots），
    //   而 C6 印出来的「真孤儿 0 段」读起来像是**全页面**的结论。
    //   被吞掉的当口就有实锤：ArchivedExperiments（整块 0 个 data-*）
    //   里那句「sits about 6% below the inert control」是手写的，
    //   而产物里**根本没有** inert control 的 token_agreement 字段。
    //   ⇒ 处置：**不写名单**。扫全页面 <p>，面板归属由「最近带标记祖先」反推。
    //     名单一写死，名单外就永远没人看 —— 与「抽取器变少下游缺失数变好看」同族。
    const out = [];
    // ⚠ 第三十三笔之六：候选元素集。
    //   原来只有 'p' ⇒ 导读浮层里 10 个真缺口（h1/h2/div）结构性不可见。
    //   这几个标签是**浮层里真实存在的那些**（实测：h1 / h2 / p / li / div），
    //   不含 span/em/b（它们几乎总是长在有标记的祖先里，带进来只会成倍重复）。
    const SEL = 'h1,h2,h3,p,li,div';
    // ⚠⚠ 第三十三笔之十一：**必须判可见性**，否则把看不见的文字算成缺口。
    //   实测（_probe_vis.mjs）：latent 页有两条含「正在加载隐空间数据…」的 div，
    //   一条自己 display:none、一条祖先被藏（它自己 display:block、visibility:visible），
    //   两条 innerText 都**不是空**（我原以为隐藏元素 innerText 会返回空串，实测不是）
    //   ⇒ 只要不查可见性它们就进清单，而**读者永远看不到它们**。
    //   一个读者看不到的占位符不是覆盖缺口，是**噪声**。
    //   这一套逻辑与 survey_orientation.mjs 里的 shown() 相同 ——
    //   而两支探针**各写各的**，结果只有一支查了可见性。
    //   ⇒ 教训：同一段判据逻辑在两处各存一份时，
    //     **先问「另一份有没有这份检查」**，别只保证自己这份有。
    //   ⚠⚠ 而且**整段都在 page.eval 的模板串里**：注释里也不能出现反引号，
    //     它会**截断模板串**，报出来的是 "missing ) after argument list"
    //     —— 位置指向模板串开头那一行，离真凶很远。node --check 抓得到这个。
    const shown = e => {
      for (let p = e; p && p !== document.body; p = p.parentElement) {
        const cs = getComputedStyle(p);
        if (cs.display === 'none' || cs.visibility === 'hidden') return false;
      }
      return true;
    };
    const cands = Array.from(document.querySelectorAll(SEL))
      .filter(e => !hasData(e) && !hasDataDesc(e) && shown(e));
    for (const p of cands) {
      const t = (p.innerText || '').replace(/\\s+/g, ' ').trim();
      if (t.length < ${THRESH}) continue;
      // ⚠ 纯包裹元素去重：文本与某个候选后代**完全相同** ⇒ 这个元素
      //   只是壳（<div><span>…</span></div>、<li><div>…</div></li>），
      //   记两份会让同一句话在清单里出现两次。留最内层那个。
      let wrap = false;
      for (const c of p.querySelectorAll(SEL)) {
        if (cands.indexOf(c) < 0) continue;
        const ct = (c.innerText || '').replace(/\\s+/g, ' ').trim();
        if (ct === t) { wrap = true; break; }
      }
      if (wrap) continue;
      // ⚠ 第一版这里写的是 r.getAttribute(<第一个 data-* 名>)，
      //   那是**值**（如 'ready'）而不是**名字**，而 find 有时又落空 ⇒ 退化成
      //   r.tagName，整列都印成 'div'，看不出是哪块面板。
      // ⚠ 加上「最近带标记祖先」：C5 原来宣称这些段「连标记都没有 ⇒
      //   永远不会被「未被读过」那一栏列出来」。实测 **27/27 全在带标记祖先里**
      //   （祖先属性往往就带着同一句话的机器可读真值，如
      //   data-cos-up-down=-0.9999999999999997 对应散文里的 cos = -1.0000）。
      //   ⇒ 那句宣称是错的，必须带祖先信息才能判「有没有人读」。
      const chain = [];
      for (let a = p.parentElement; a && a !== document.body; a = a.parentElement) {
        const at = Array.from(a.attributes).filter(x => x.name.startsWith('data-'))
                           .map(x => x.name);
        if (at.length) chain.push(at);
      }
      // ⚠ 祖先链为空时**不要**给它编一个面板名（如 '?'）：
      //   那会让 C6 的分组把「真孤儿」混进普通面板里数。
      const pn = (chain[0] || [])[0] || '（祖先链为空）';
      out.push({ tag: p.tagName.toLowerCase(), panel: pn, len: t.length,
                 head: t.slice(0, 70),
                 ancestors: chain, orphan: chain.length === 0 });
    }
    return JSON.stringify(out);
  })()`));

  for (const d of Object.keys(B).map(Number).sort((a, b) => a - b)) {
    console.log('\n=== data 树深度 ' + d + '，共 ' + B[d].length + ' 个 ===');
    for (const b of B[d]) {
      // ⚠ padEnd/padStart 而不是 %-26s：node 的 console.log 不支持宽度占位符
      console.log('  ' + String(b.data).padEnd(26) + ' tc=' + String(b.tc_len).padStart(5)
        + ' it=' + String(b.it_len).padStart(5) + '  ' + b.heading);
    }
  }
  // 供 python 侧读取
  const fs = await import('fs');
  // ⚠ page 字段不是装饰：python 侧靠它把清单分回「根页 / latent 页」，
  //   而这正是第二十三笔 C2 假红的根因（拿两页的东西互相对账）。
  // ⚠⚠ 第三十三笔之六：census / thresh 也不装饰。python 侧 C5 要印
  //   「阈值是怎么选出来的」那张表，靠的就是这份 census；
  //   而 thresh 记下**这次实际用的门槛**，免得 C5 印的数
  //   与产物里的清单来自两个不同口径（换过一次而没人知道）。
  fs.writeFileSync(OUT, JSON.stringify({
    page: IS_LATENT ? 'latent' : 'root', url: URL,
    byDepth: B, unmarked, census: CENSUS, thresh: THRESH,
    beforeNames, afterNames, appeared, clicked: clickSweep.length,
  }, null, 2));
  console.log('\n=== 有实质文字、但**自己不带任何 data-\\* 的块**（>= ' + THRESH
    + ' 字，' + CENSUS.sel + '，共 ' + unmarked.length + ' 个）===');
  for (const u of unmarked) {
    console.log('  <' + String(u.tag).padEnd(4) + '> [' + u.panel + '] '
      + String(u.len).padStart(4) + ' 字  ' + u.head);
  }
  console.log('已写出 %s（page=%s，加载后 %d 个标记 / 交互后 %d 个）',
              OUT, IS_LATENT ? 'latent' : 'root', beforeNames.length, afterNames.length);
} finally {
  try { await cdp.send('Browser.close'); } catch {}
  try { proc.kill(); } catch {}
}
