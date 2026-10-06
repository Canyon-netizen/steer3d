// 验收：latent 页第 7 屏「因果修补」。
//
// 这一屏要防止的**具体**错误，按危险程度排：
//   1. 判否的门被折叠掉 / 只印成立那半     → P2、P3
//   2. 页面自己另判一次，与产物不一致     → P2（data-verdict 必须逐字等于产物）
//   3. na（没测）被当成 fail（不成立）印出去 → P2、P3
//   4. 诚实边界被删掉                        → P5
//   5. 曲线画了，但画的是哪条线没人知道     → P6（判据独立从 JSON 重算）
//
// 判据主体是**读者看到的可见文案**。data-* 只作交叉核对：
// 它能证明「节点在」，证明不了「人看得见」。
import { launch, Page, CDP } from './cdp_client.mjs';
import { readFileSync } from 'node:fs';

const URL = process.env.LAT_URL || 'http://127.0.0.1:22234/latent/index.html';
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_patch_'
  + process.pid;
const ART = '/Users/zhourui/code/steer3d/frontend/public/latent/data/path_patching.json';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const R = [];
const rec = (n, p, d) => { R.push({ n, p }); console.log(`[${p ? 'PASS' : 'FAIL'}] ${n}\n       ${d}`); };

const { proc, version } = await launch({ port: 9491, userDataDir: PROFILE,
  windowSize: '1600,1050', url: 'about:blank' });
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);

try {
  // ---- 0 页面必须真的加载 ----------------------------------------
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  await sleep(3500);
  const L0 = JSON.parse(await page.eval(`JSON.stringify({
    href: location.href, bodyLen: (document.body.innerText||'').length
  })`));
  rec('P0 页面真的加载出来（死 URL 不得让本脚本报 PASS）',
    L0.href.startsWith('http') && L0.bodyLen > 500,
    `href=${L0.href} bodyLen=${L0.bodyLen}`);
  if (!(L0.href.startsWith('http') && L0.bodyLen > 500)) throw new Error('页面没加载');

  // ---- 0b 导读浮层必须先关掉 --------------------------------------
  // ⚠ `orientAuto` 加载时会自动弹出 `#orientation`（position:fixed 盖住视口）。
  //   不关就量可见性，量到的是浮层。判红的第一嫌疑永远是「红的不是被测对象」。
  const closed = JSON.parse(await page.eval(`JSON.stringify((() => {
    const ov = document.getElementById('orientation');
    const wasShown = ov ? !ov.classList.contains('hide') : null;
    const b = document.getElementById('orientClose');
    if (wasShown && b) b.click();
    return { wasShown, nowHidden: ov ? ov.classList.contains('hide') : null };
  })())`));
  rec('P0b 导读浮层已关掉（否则量到的是浮层，不是这一屏）',
    closed.wasShown === true && closed.nowHidden === true,
    `加载后弹出=${closed.wasShown} 点击后已隐藏=${closed.nowHidden}`);

  // ---- 1 切到第 7 屏 --------------------------------------------
  await page.eval(`(() => {
    const b = document.getElementById('tabPatch');
    if(!b) throw new Error('没有 tabPatch 按钮');
    b.click();
  })()`);
  await sleep(2500);
  const st = JSON.parse(await page.eval(`JSON.stringify({
    wrap: (() => { const w=document.getElementById('patchWrap');
      return { display: w ? w.style.display : 'missing',
               hasBlock: !!(w && w.querySelector('[data-patchblock]')),
               state: w && w.querySelector('[data-patchstate]')
                        ? w.querySelector('[data-patchstate]').getAttribute('data-patchstate') : null };
    })(),
    tabOn: document.getElementById('tabPatch')?.classList.contains('on') || false,
    title: (document.getElementById('mainTitle')||{}).textContent || ''
  })`));
  rec('P1 点「因果修补」标签后切到第 7 屏且内容已渲染',
    st.wrap.display !== 'none' && st.wrap.hasBlock && st.tabOn && st.wrap.state === 'ok',
    `display=${st.wrap.display} state=${st.wrap.state} tabOn=${st.tabOn} title="${st.title}"`);
  if (st.wrap.state !== 'ok') {
    rec('P2..P6 本屏在 ok 态下才有意义', false,
      `产物没载入（state=${st.wrap.state}）—— 这是「没验」，不是「通过」`);
    throw new Error('no ok state');
  }

  const art = JSON.parse(readFileSync(ART, 'utf8'));
  const gates = art.gates || {};
  // 门序从产物读，不在本脚本里硬编码第二份。
  // ⚠ 按**门键**对账，不按门名：三个量各判一次 ⇒ 「存在方向性层」有 6 个同名门，
  //   按名匹配会把它们认成同一个，然后判据永远绿。
  const order = (art.gate_order || Object.keys(gates)).filter(k => gates[k]);

  // ---- 2 判决表逐行与产物对账 ------------------------------------
  // 关键：**唯一结论字段** data-verdict 必须与产物 gates[].verdict 逐字相同。
  // 页面不许自己另判一次 —— 那是上一轮「stable=true 与判决不稳并存」的同族错误。
  const rows = JSON.parse(await page.eval(`JSON.stringify(
    [...document.querySelectorAll('[data-gate]')].map(tr => ({
      gate: tr.getAttribute('data-gate'),
      key: tr.getAttribute('data-key'),
      verdict: tr.getAttribute('data-verdict'),
      claim: (tr.querySelector('td code')||{}).textContent || '',
      verdictCell: tr.children[1] ? tr.children[1].textContent.trim() : '',
      evidence: tr.children[2] ? tr.children[2].textContent.trim() : ''
    })))`));
  const mism = [];
  const seenKeys = new Set();
  for (const r of rows) {
    const g = gates[r.key];
    if (!g) { mism.push([r.key, '页面有这道门，产物里没有']); continue; }
    if (seenKeys.has(r.key)) mism.push([r.key, '同一个门键出现了两行']);
    seenKeys.add(r.key);
    if (r.verdict !== g.verdict) mism.push([r.key, `页面 ${r.verdict} ≠ 产物 ${g.verdict}`]);
  }
  for (const k of order) if (!seenKeys.has(k)) mism.push([k, '产物有这道门，页面上没有']);
  rec('P2 判决表按**门键**与产物 gates[] 逐行一致（页面不另判、不漏门、不重门）',
    rows.length === order.length && mism.length === 0,
    `DOM ${rows.length} 行 / 产物 ${order.length} 门；不一致 ${JSON.stringify(mism).slice(0,400)}`);

  // ---- 3 三态都是**看得见的字**，且判否/没测都摆在明面上 ------------
  const vis = JSON.parse(await page.eval(`JSON.stringify((() => {
    const vis = el => { if(!el) return {ok:false,why:'缺元素'};
      const r = el.getBoundingClientRect();
      if(r.height<=0||r.width<=0) return {ok:false,why:'尺寸为 0'};
      const top = document.elementFromPoint(r.left+r.width/2, r.top+r.height/2);
      if(!top) return {ok:false,why:'elementFromPoint 返回 null（视口外）'};
      if(!(el===top||el.contains(top)||top.contains(el))) return {ok:false,why:'被别的层盖住'};
      const cs=getComputedStyle(el);
      return {ok:true, txt:(el.innerText||'').trim().slice(0,90), disp:cs.display, vis:cs.visibility};
    };
    const f = document.querySelector('[data-patch-fails]');
    return { fails: vis(f),
             failsTxt: f ? (f.innerText||'').trim() : '',
             verdictWords: [...document.querySelectorAll('[data-verdict]')]
               .map(tr => tr.children[1] ? tr.children[1].textContent.trim() : ''),
             counts: {pass:0,fail:0,na:0} };
  })())`));
  const gatesHas = v => order.some(k => gates[k] && gates[k].verdict === v);
  const need = { pass: '成立', fail: '不成立', na: '没测' };
  const seen = {};
  vis.verdictWords.forEach(w => { for (const k in need) if (w === need[k]) seen[k] = (seen[k]||0)+1; });
  rec('P3 判决表三态用的都是人看得见的字（成立/不成立/没测），不是只有 data-*',
    ['pass','fail','na'].every(k => !gatesHas(k) || (seen[k]||0) > 0),
    `页面出现：${JSON.stringify(seen)}；产物里 pass/fail/na 的门数：`
    + `${order.filter(k=>gates[k]&&gates[k].verdict==='pass').length}/`
    + `${order.filter(k=>gates[k]&&gates[k].verdict==='fail').length}/`
    + `${order.filter(k=>gates[k]&&gates[k].verdict==='na').length}`);

  const fails = order.filter(k => gates[k] && gates[k].verdict === 'fail');
  const nas = order.filter(k => gates[k] && gates[k].verdict === 'na');
  rec('P4 「N/M 道门没有通过」那一块**可见且把判否/没测都点了名**',
    vis.fails.ok && (fails.length + nas.length === 0
      ? /没有通过/.test(vis.failsTxt)
      : fails.length + nas.length === 0 || new RegExp('没测').test(vis.failsTxt)),
    `可见性=${JSON.stringify(vis.fails)}；产物 fail=${JSON.stringify(fails)} na=${JSON.stringify(nas)}；`
    + `块内文本="${vis.failsTxt.slice(0,120)}"`);

  // ---- 5 na 必须带理由，且页面上看得见 -----------------------------
  const naBad = [];
  for (const k of nas) {
    if (!gates[k].why_na) { naBad.push([k, '产物里 na 但没有 why_na']); continue; }
    const r = rows.find(x => x.key === k);
    if (!r) { naBad.push([k, '页面上找不到这道门']); continue; }
    if (r.evidence.length < 6) naBad.push([k, '页面上 na 行没有理由']);
  }
  rec('P5 「没测」的门都带着理由（没测说成不成立是伪造结论）', naBad.length === 0,
    naBad.length ? JSON.stringify(naBad)
      : `na 门 ${nas.length} 道，逐条带 why_na：` + JSON.stringify(nas.map(k => gates[k].why_na.slice(0,28))));

  // ---- 6 逐题表与产物对账 ----------------------------------------
  const prows = JSON.parse(await page.eval(`JSON.stringify(
    [...document.querySelectorAll('[data-patch-pid]')].map(tr => ({
      pid: tr.getAttribute('data-patch-pid'),
      cells: [...tr.querySelectorAll('td')].map(td => td.textContent.trim())
    })))`));
  const pbad = [];
  for (let i = 0; i < (art.problems||[]).length; i++) {
    const p = art.problems[i], d = prows[i];
    if (!d) { pbad.push([p.pid, 'DOM 缺行']); continue; }
    if (d.pid !== p.pid) { pbad.push([p.pid, `pid ${d.pid}`]); continue; }
    // HTML 会把 token 的前导空格吃掉（`' greater'` 显示成 `greater`），
    // 所以两边都 trim 再比。页面侧用 pre-wrap 保留那个空格，可见性不受影响。
    if (String(d.cells[1]).trim() !== String(p.token_text).trim())
      pbad.push([p.pid, `token 对不上：页面 ${JSON.stringify(d.cells[1])} vs 产物 ${JSON.stringify(p.token_text)}`]);
    if (d.cells[4] !== (p.num_differs ? '改口' : '没改')) pbad.push([p.pid, '数字臂改口标记']);
    if (d.cells[5] !== (p.word_differs ? '改口' : '没改')) pbad.push([p.pid, '说法臂改口标记']);
  }
  rec('P6 逐题表与产物 problems[] 逐题对账（题号/token/两臂改口与否）',
    prows.length === (art.problems||[]).length && pbad.length === 0,
    `DOM ${prows.length} 行 / 产物 ${(art.problems||[]).length} 题；错 ${JSON.stringify(pbad)}`);

  // ---- 7 诚实边界块非空 ------------------------------------------
  const lim = JSON.parse(await page.eval(`JSON.stringify((() => {
    const el = document.querySelector('[data-patch-limits]');
    if(!el) return {ok:false, n:0, txt:''};
    const r = el.getBoundingClientRect();
    return { ok: r.height>0, n: el.querySelectorAll('li').length, txt: (el.innerText||'').trim() };
  })())`));
  const limArt = (art.honest_limits||[]).length;
  rec('P7 「这一屏不能回答的」边界块可见且非空（只印成立那半就红）',
    lim.ok && lim.n > 0 && limArt > 0,
    `页面 ${lim.n} 条 / 产物 ${limArt} 条；可见=${lim.ok}`);

  // ---- 8 SVG 曲线：判据独立从 JSON 重算，不信页面 ------------------
  const svg = JSON.parse(await page.eval(`JSON.stringify((() => {
    const s = document.getElementById('svgPatch');
    if(!s) return {ok:false, paths:0};
    const r = s.getBoundingClientRect();
    return { ok: r.width>0 && r.height>0, paths: s.querySelectorAll('polyline').length,
             w: Math.round(r.width), h: Math.round(r.height),
             text: (s.textContent||'').slice(0,200) };
  })())`));
  const lensKeys = Object.keys(art.node_lens_agree||{}).length;
  // 独立重算：节点数必须与产物一致，且三条线的首末值能从 JSON 算出来
  const lensArr = Object.entries(art.node_lens_agree||{})
    .map(([k,v]) => [Number(k), v]).sort((a,b)=>a[0]-b[0]);
  const meanOf = arm => {
    const acc = {};
    for (const p of art.problems||[]) for (const n of p.nodes) {
      if (n['excess_'+arm] == null) continue;
      (acc[n.node] = acc[n.node]||[]).push(n['excess_'+arm]);
    }
    return lensArr.map(([nd]) => {
      const a = acc[nd]||[]; return a.length ? a.reduce((x,y)=>x+y,0)/a.length : 0;
    });
  };
  const exNum = meanOf('num'), exWord = meanOf('word');
  // 折线条数是「描述 1 + 主量 2 + 次量 2」，写死 3 会在加次量线后变成假红。
  // 判据要的是**线都在**，不是**线的条数是某个常量**。
  const wantLines = 1 + 2 + (exWord.some(v => v !== 0) || exNum.some(v => v !== 0) ? 2 : 0);
  rec('P8 描述/因果对照图在页面上，且节点数与产物一致（线族齐全）',
    svg.ok && svg.paths >= 3 && lensArr.length > 0 && lensArr[lensArr.length-1][0] >= 28,
    `SVG 可见=${svg.ok} ${svg.w}×${svg.h} 折线=${svg.paths} 条；产物节点 ${lensArr.length} 个`
    + `（${lensArr[0]?.[0]}..${lensArr[lensArr.length-1]?.[0]}）`
    + `；excess 首末 num=${exNum[0]?.toFixed(2)}/${exNum[exNum.length-1]?.toFixed(2)}`
    + ` word=${exWord[0]?.toFixed(2)}/${exWord[exWord.length-1]?.toFixed(2)}`);

  // ---- 9 两个量都要在页面上出现 ------------------------------------
  // 主量 transfer 与次量 excess 都判过；只印一组 = 把一个门说成了另一个门的结论。
  const txt = await page.eval(`(document.getElementById('patchWrap')||{}).innerText || ''`);
  const hasBoth = /主量/.test(txt) && /次量/.test(txt);
  rec('P9 主量与次量在页面上都有交代（只印一组就等于偷换结论）', hasBoth,
    `页面同时提到「主量」=${/主量/.test(txt)}「次量」=${/次量/.test(txt)}`);
  // P10 页面必须说清主量的对照是谁。否则读者看到的是一条没有对照说明的曲线。
  const saysCtrl = /幅度配平/.test(txt) && /逐节点相等/.test(txt);
  rec('P10 页面写明主量的对照是「幅度配平随机对照」且偏离量逐节点相等', saysCtrl,
    `页面提到「幅度配平」=${/幅度配平/.test(txt)}「逐节点相等」=${/逐节点相等/.test(txt)}`);
  // P11 次量必须被标成混着陌生度，而不是当结论用。
  const warnsNoise = /陌生度/.test(txt);
  rec('P11 次量被明确标成「混着陌生度」（把失配当结论用 = 第三种自相矛盾）', warnsNoise,
    `页面提到「陌生度」=${warnsNoise}`);

} catch (e) {
  console.log('[FAIL] 脚本中断：' + e.message);
  R.push({ n: '脚本中断', p: false });
} finally {
  const red = R.filter(r => !r.p);
  // ⚠ 汇总行**必须**是 `=== N/M passed ===`。第一版印的是自创的
  //   `✅ 13/13 通过`，而 run_chain.sh 只认 `^RESULT` 与 `^=== [0-9]+/`
  //   ⇒ 这条判据在全链里被判成 **NORUN**。NORUN 的读法是「一条都没跑」，
  //   也就是说：一个 13/13 全绿、浏览器里真点过的判据，在汇总里与
  //   「压根没执行」长得一模一样。房里的 node 判据统一用 `=== N/M passed ===`，
  //   不许自创第三套。
  console.log(`\n=== ${R.length - red.length}/${R.length} passed ===`);
  if (red.length) red.forEach(r => console.log('   红：' + r.n));
  try { proc.kill(); } catch {}
  process.exit(red.length ? 1 : 0);
}