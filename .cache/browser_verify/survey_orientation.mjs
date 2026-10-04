import { launch, Page, CDP } from './cdp_client.mjs';

/**
 * 普查 #orientation 浮层内「有实质文字、但自己或祖先都没有任何 data-* 标记」的块。
 *
 * ## 为什么要有这个探针
 *
 * 第三十三笔之六发现：导读第二节那 10 段**既没有 data-* 标记，
 * 也不在 C4 的欠账清单上**，而 C6 报的是「真孤儿 0 段」。
 *
 * 查 `scan_panel_coverage.py` 的源码，它**从头到尾没有出现过
 * `orientation` / `btnOrient`** ⇒ 它从不打开那个浮层
 * （`#orientation` 初始带 `.hide`）⇒
 * **C5 的「26 段」与 C6 的「真孤儿 0」都只对浮层外成立。**
 *
 * ⇒ 这个探针把同一套口径搬到浮层内重跑一遍，看那里到底剩多少。
 *
 * ## 它只做普查，不判红
 *
 * 一段「有文字、没标记」本身不一定是缺口 ——
 * 判它是不是缺口要看它承载的信息有没有别的判据覆盖。
 * 所以这里只**列名 + 计数**，结论留给下一步逐段看。
 */
const URL = process.env.LAT_URL || 'http://127.0.0.1:22208/latent/index.html';
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_ov_' + process.pid;
const sleep = ms => new Promise(r => setTimeout(r, ms));

const { proc, version } = await launch({
  port: 9700 + (process.pid % 90), userDataDir: PROFILE,
  windowSize: '1900,3200', url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});

  // 等 boot 真的跑完 —— 浮层内容是静态 HTML，但 autoShow 依赖 boot
  let waited = 0, st = null;
  while (waited < 40000) {
    st = await page.eval(`(() => ({
      id: (typeof S !== 'undefined' && S.model) ? S.model.id : null,
      walkTok: String((document.getElementById('walkTok')||{}).textContent||'').trim(),
    }))()`);
    if (st && st.id && st.walkTok !== '—' && st.walkTok !== '') break;
    await sleep(1200); waited += 1200;
  }

  // 打开浮层 —— 这一步是 scan_panel_coverage 从来没做过的
  const opened = await page.eval(`(() => {
    const ov = document.getElementById('orientation');
    if(!ov) return 'no #orientation';
    if(ov.classList.contains('hide')){
      const b = document.getElementById('btnOrient'); if(b) b.click();
    }
    return ov.classList.contains('hide') ? 'clicked but still .hide' : 'open';
  })()`);
  await sleep(1000);

  const survey = await page.eval(`(() => {
    const ov = document.getElementById('orientation');
    if(!ov) return { err: '没有 #orientation' };
    const shown = e => { for(let p=e; p && p!==document.body; p=p.parentElement){
      const cs = getComputedStyle(p);
      if(cs.display==='none' || cs.visibility==='hidden') return false; } return true; };
    const txt = e => (e.innerText || e.textContent || '').replace(/\\s+/g,' ').trim();
    const SEL = 'p, li, div, h1, h2, h3';
    const rows = [];
    for(const e of ov.querySelectorAll(SEL)){
      const t = txt(e);
      if(t.length < 6) continue;
      if(!shown(e)) continue;
      const own = [...e.attributes].map(a=>a.name).filter(n=>n.startsWith('data-'));
      // 祖先链上最近的一层 data-*（C6 的口径）
      const chain = [];
      for(let p=e; p && p!==document.body; p=p.parentElement){
        const ds = [...p.attributes].map(a=>a.name).filter(n=>n.startsWith('data-'));
        if(ds.length){ chain.push(...ds); break; }
      }
      const hasDesc = !!e.querySelector('[data-latent-lead],[data-lead-seg],[data-term],[data-latent-not-claimed],[data-f]');
      rows.push({ tag: e.tagName.toLowerCase(), len: t.length, own, chain, hasDesc, head: t.slice(0, 52) });
    }
    const orphan = rows.filter(r => r.chain.length === 0);
    // C6 口径的第二个缺陷：它只问「祖先链有没有标记」，不问「子树有没有」
    const containerMisjudged = orphan.filter(r => r.hasDesc);
    return {
      nRows: rows.length, nOrphan: orphan.length, orphan, containerMisjudged, rows,
      dataAttrs: [...new Set([...ov.querySelectorAll('*')]
        .flatMap(e => [...e.attributes].map(a=>a.name).filter(n=>n.startsWith('data-'))))],
    };
  })()`);

  console.log('boot：modelId=%s walkTok=%s（等了 %dms）', st && st.id, st && st.walkTok, waited);
  console.log('浮层打开状态：%s', opened);
  if (survey.err) { console.log('ERR %s', survey.err); }
  else {
    console.log('浮层内「最外层 + 有实质文字(≥6字) + 可见」的块：%d', survey.nRows);
    console.log('其中 C6 口径下祖先链为空的（真孤儿）：%d\n', survey.nOrphan);
    console.log('=== 真孤儿（C6 当前口径）逐条 ===');
    survey.orphan.forEach((r, i) =>
      console.log('  ' + String(i + 1).padStart(2) + '. <' + r.tag + '> ' + r.len
        + ' 字  子树有标记=' + r.hasDesc + '  ' + r.head));
    console.log('\n  ⚠ 其中「子树有标记=true」的 ' + survey.containerMisjudged.length
      + ' 条是 **C6 口径本身的缺陷**（只问祖先、不问子树）——\n'
      + '    它们内部全都有已标记的块，判据却会说它们是没人读的真孤儿。');
    console.log('\n=== 浮层内出现的全部 data-* ===');
    console.log('  %s', survey.dataAttrs.join(', '));
  }
} catch (e) {
  console.log('[FAIL] %s\n%s', e.message, e.stack);
  process.exitCode = 1;
} finally {
  try { await cdp.send('Browser.close'); } catch {}
  try { proc.kill(); } catch {}
}
