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

  // ---- C5 的输入：有没有「大段文字、但自己一个 data-* 都不带」的 <p> ----
  // ⚠ 覆盖矩阵**天生看不见**这类洞：它统计的是「有标记的块」，
  //   而 D6 / G7 那两个洞正是两段**完全没有标记**的 <p> ——
  //   没有标记 ⇒ 不进矩阵 ⇒ 永远不会被「未被读过」那一栏列出来。
  //   矩阵只能报「读过没有」，报不了「有没有被登记过」。
  //   ⇒ 这里单独量一遍：面板根里，文字 ≥40 字、自身无 data-*、且无 data-* 后代的 <p>。
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
    for (const p of document.querySelectorAll('p')) {
      const t = (p.innerText || '').replace(/\\s+/g, ' ').trim();
      if (t.length < 40) continue;
      if (hasData(p) || hasDataDesc(p)) continue;
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
      out.push({ panel: pn, len: t.length, head: t.slice(0, 70),
                 ancestors: chain, orphan: chain.length === 0 });
    }
    return JSON.stringify(out);
  })()`));

  for (const d of Object.keys(B).map(Number).sort((a, b) => a - b)) {
    console.log('\\n=== data 树深度 %s，共 %d 个 ===', d, B[d].length);
    for (const b of B[d]) {
      console.log('  %-26s tc=%-6d it=%-6d  %s', b.data, b.tc_len, b.it_len, b.heading);
    }
  }
  // 供 python 侧读取
  const fs = await import('fs');
  // ⚠ page 字段不是装饰：python 侧靠它把清单分回「根页 / latent 页」，
  //   而这正是第二十三笔 C2 假红的根因（拿两页的东西互相对账）。
  fs.writeFileSync(OUT, JSON.stringify({
    page: IS_LATENT ? 'latent' : 'root', url: URL,
    byDepth: B, unmarked,
    beforeNames, afterNames, appeared, clicked: clickSweep.length,
  }, null, 2));
  console.log('\n=== 有实质文字、但**自己不带任何 data-\\*** 的 <p>（%d 个）===', unmarked.length);
  for (const u of unmarked) {
    console.log('  [%s] %d 字  %s', u.panel, u.len, u.head);
  }
  console.log('已写出 %s（page=%s，加载后 %d 个标记 / 交互后 %d 个）',
              OUT, IS_LATENT ? 'latent' : 'root', beforeNames.length, afterNames.length);
} finally {
  try { await cdp.send('Browser.close'); } catch {}
  try { proc.kill(); } catch {}
}
