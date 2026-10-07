// 验收：latent 页第 8 屏「阈值向量（LTV）」。
//
// 背景：ltv.json 是这一轮新提取的一个**方法**，判决已经在
// .cache/xcheck/verify_ltv.py 里判完了（23 条独立重算）。但在这之前，
// 那份产物**没有任何页面消费者** —— 方法算完了、判完了，读者在网站上
// 看不到。这一屏就是把它接上。所以本判据要防的不是「画得好看不好看」，
// 而是**接上去之后有没有把结论传错**。
//
// 这一屏要防的**具体**错误，按危险程度排：
//   1. 判决切片被抹掉 —— G-a 的 claim 与预登记表都写着「留出」，
//      而第一版的判决跑在全量 36 个上下文上（含约一半抽取题）。
//      页面若只印一个总数，就把「抽取集上不显著」这个事实藏起来了。→ L6
//   2. na（G-c，没测）被当成 fail 印出去                    → L4、L5
//   3. 页面自己另判一次，与产物不一致                       → L2
//   4. 并列口径（全量）被当成判决印出去                    → L7
//   5. 逐上下文表张冠李戴（数值配错行 / 切片标反）         → L8
//   6. 敏感性表里 degenerate_untested 被显示成通过          → L9
//   7. 诚实边界少印几条（后 3 条正是口径偏离的披露）        → L10
//   8. 句子轴的 3 条负对照被删掉                            → L11
//
// 判据主体是**读者看到的可见文案**。data-* 只作交叉核对：
// 它能证明「节点在」，证明不了「人看得见」。
//
// ⚠ 本判据有**独立重算**（第三层防护）：L8 不信产物自己写的 alpha_star_pred，
//   而是用同一份 JSON 里的 m_p 与 g_v 现场算 m_p/g_v 再比；
//   L6 用 n_monotone/n_ctx 现场算适用率；L9 用上下文行现场数出
//   holdout / extract 各多少条，与各门 evidence 里写的 n_ctx 对账。
//   这样「产物自己错了」和「页面抄错了」会落到不同的红条上。
import { launch, Page, CDP } from './cdp_client.mjs';
import { readFileSync } from 'node:fs';

const URL = process.env.LAT_URL || 'http://127.0.0.1:22234/latent/index.html';
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_ltv_'
  + process.pid;
const ART = '/Users/zhourui/code/steer3d/frontend/public/latent/data/ltv.json';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const R = [];
const rec = (n, p, d) => { R.push({ n, p }); console.log(`[${p ? 'PASS' : 'FAIL'}] ${n}\n       ${d}`); };

const { proc, version } = await launch({ port: 9492, userDataDir: PROFILE,
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
  rec('L0 页面真的加载出来（死 URL 不得让本脚本报 PASS）',
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
  rec('L0b 导读浮层已关掉（否则量到的是浮层，不是这一屏）',
    closed.wasShown === true && closed.nowHidden === true,
    `加载后弹出=${closed.wasShown} 点击后已隐藏=${closed.nowHidden}`);

  // ---- 1 四合一：容器可见 + 块在 + 标签高亮 + 产物在 ---------------
  // 四条缺一不可：display 可见而内容空（块不在）、内容在而容器仍 hidden、
  // 容器可见而标签没高亮（读者不知道自己在第 8 屏）—— 这三种
  // 在「看起来有东西」的前提下都发生过。
  await page.eval(`(() => {
    const b = document.getElementById('tabLtv');
    if(!b) throw new Error('没有 tabLtv 按钮');
    b.click();
  })()`);
  await sleep(2500);
  const st = JSON.parse(await page.eval(`JSON.stringify({
    wrap: (() => { const w=document.getElementById('ltvWrap');
      return { display: w ? w.style.display : 'missing',
               hasBlock: !!(w && w.querySelector('[data-ltvblock]')),
               state: w && w.querySelector('[data-ltvstate]')
                        ? w.querySelector('[data-ltvstate]').getAttribute('data-ltvstate') : null };
    })(),
    tabOn: document.getElementById('tabLtv')?.classList.contains('on') || false,
    title: (document.getElementById('mainTitle')||{}).textContent || ''
  })`));
  rec('L1 点「阈值向量」标签后四合一：容器可见 + 块在 + 标签高亮 + 产物已就绪',
    st.wrap.display !== 'none' && st.wrap.hasBlock && st.tabOn && st.wrap.state === 'ready',
    `display=${st.wrap.display} hasBlock=${st.wrap.hasBlock} state=${st.wrap.state} `
    + `tabOn=${st.tabOn} title="${st.title}"`);
  if (st.wrap.state !== 'ready') {
    rec('L2..L11 本屏在 ready 态下才有意义', false,
      `产物没载入（state=${st.wrap.state}）—— 这是「没验」，不是「通过」`);
    throw new Error('no ready state');
  }

  const art = JSON.parse(readFileSync(ART, 'utf8'));
  const gates = art.gates || {};
  // 门序从产物读，不在本脚本里硬编码第二份。
  const order = (art.gate_order || Object.keys(gates)).filter(k => gates[k]);

  // ---- 2 判决表按门键逐行与产物对账 -------------------------------
  // **唯一结论字段** data-verdict 必须与产物 gates[].verdict 逐字相同。
  // 页面不许自己另判一次 —— 那是上一轮「stable=true 与判决不稳并存」的同族错误。
  const rows = JSON.parse(await page.eval(`JSON.stringify(
    [...document.querySelectorAll('[data-ltvgate]')].map(tr => ({
      gate: tr.getAttribute('data-ltvgate'),
      verdict: tr.getAttribute('data-verdict'),
      cells: [...tr.querySelectorAll('td')].map(td => td.textContent.trim()),
      nameCell: tr.children[0] ? tr.children[0].textContent : '',
      verdictCell: tr.children[1] ? tr.children[1].textContent.trim() : '',
      evidence: tr.children[2] ? tr.children[2].textContent.trim() : ''
    })))`));
  const mism = [];
  const seenKeys = new Set();
  for (const r of rows) {
    const g = gates[r.gate];
    if (!g) { mism.push([r.gate, '页面有这道门，产物里没有']); continue; }
    if (seenKeys.has(r.gate)) mism.push([r.gate, '同一个门键出现了两行']);
    seenKeys.add(r.gate);
    if (r.verdict !== g.verdict) mism.push([r.gate, `页面 ${r.verdict} ≠ 产物 ${g.verdict}`]);
    if (!r.nameCell.includes(g.name))
      mism.push([r.gate, `门名不匹配：页面 ${JSON.stringify(r.nameCell.slice(0,30))}`]);
  }
  for (const k of order) if (!seenKeys.has(k)) mism.push([k, '产物有这道门，页面上没有']);
  rec('L2 判决表按**门键**与产物 gates[] 逐行一致（页面不另判、不漏门、不重门）',
    rows.length === order.length && mism.length === 0,
    `DOM ${rows.length} 行 / 产物 ${order.length} 门；不一致 ${JSON.stringify(mism).slice(0,400)}`);

  // ---- 3 三态用的都是人看得见的字 ----------------------------------
  const vis = JSON.parse(await page.eval(`JSON.stringify((() => {
    const vis = el => { if(!el) return {ok:false,why:'缺元素'};
      const r = el.getBoundingClientRect();
      if(r.height<=0||r.width<=0) return {ok:false,why:'尺寸为 0'};
      const top = document.elementFromPoint(r.left+r.width/2, r.top+r.height/2);
      if(!top) return {ok:false,why:'elementFromPoint 返回 null（视口外）'};
      if(!(el===top||el.contains(top)||top.contains(el))) return {ok:false,why:'被别的层盖住'};
      return {ok:true, txt:(el.innerText||'').trim().slice(0,90)};
    };
    const f = document.querySelector('[data-ltv-fails]');
    return { fails: vis(f),
             failsTxt: f ? (f.innerText||'').trim() : '',
             verdictWords: [...document.querySelectorAll('[data-ltvgate]')]
               .map(tr => tr.children[1] ? tr.children[1].textContent.trim() : '') };
  })())`));
  const gatesHas = v => order.some(k => gates[k] && gates[k].verdict === v);
  const need = { pass: '成立', fail: '不成立', na: '没测' };
  const seen = {};
  vis.verdictWords.forEach(w => { for (const k in need) if (w === need[k]) seen[k] = (seen[k]||0)+1; });
  rec('L3 判决表三态用的都是人看得见的字（成立/不成立/没测），不是只有 data-*',
    ['pass','fail','na'].every(k => !gatesHas(k) || (seen[k]||0) > 0),
    `页面出现：${JSON.stringify(seen)}；产物里 pass/fail/na 的门数：`
    + `${order.filter(k=>gates[k]&&gates[k].verdict==='pass').length}/`
    + `${order.filter(k=>gates[k]&&gates[k].verdict==='fail').length}/`
    + `${order.filter(k=>gates[k]&&gates[k].verdict==='na').length}`);

  const fails = order.filter(k => gates[k] && gates[k].verdict === 'fail');
  const nas    = order.filter(k => gates[k] && gates[k].verdict === 'na');
  rec('L4 「N/M 道门没有通过」那一块**可见且把判否/没测都点了名**',
    vis.fails.ok && (fails.length + nas.length === 0
      ? /没有通过/.test(vis.failsTxt)
      : fails.length + nas.length === 0 || /没测/.test(vis.failsTxt)),
    `可见性=${JSON.stringify(vis.fails)}；产物 fail=${JSON.stringify(fails)} na=${JSON.stringify(nas)}；`
    + `块内文本="${vis.failsTxt.slice(0,120)}"`);

  // ---- 5 na 必须带理由且看得见 ------------------------------------
  const naBad = [];
  for (const k of nas) {
    if (!gates[k].why_na) { naBad.push([k, '产物里 na 但没有 why_na']); continue; }
    const r = rows.find(x => x.gate === k);
    if (!r) { naBad.push([k, '页面上找不到这道门']); continue; }
    if (r.evidence.length < 6) { naBad.push([k, '页面上 na 行没有理由']); continue; }
    // 理由必须是**产物那句话**，不是页面自己编的一句。
    if (!r.evidence.includes(gates[k].why_na.slice(0, 20)))
      naBad.push([k, `na 理由不是产物原文：${JSON.stringify(r.evidence.slice(0, 40))}`]);
  }
  rec('L5 「没测」的门都带着**产物原文**的理由（没测说成不成立是伪造结论）',
    naBad.length === 0,
    naBad.length ? JSON.stringify(naBad)
      : `na 门 ${nas.length} 道，逐条与产物 why_na 前 20 字逐字相符：`
        + JSON.stringify(nas.map(k => gates[k].why_na.slice(0,24))));

  // ---- 6 判决切片必须**可见且逐字** --------------------------------
  // 这一屏最贵的一条。G-a 的 claim 与预登记表都写着「留出」，
  // 而第一版的判决跑在全量 36 个（含约一半抽取题）上。
  // 页面必须把切片和它的说明原样印出来 —— 否则读者无从知道
  // 数字是按哪一批上下文算的。
  const slice = JSON.parse(await page.eval(`JSON.stringify((() => {
    const el = document.querySelector('[data-ltv-slice]');
    if(!el) return {ok:false, txt:''};
    const r = el.getBoundingClientRect();
    return { ok: r.height>0, txt: (el.innerText||'').trim() };
  })())`));
  // note 逐字（取前 24 字，够抓住「换了口径/换了切片/整句被删」）+
  // 「留出」二字必须在**可见文本**里出现：note 里带着它，
  // 而 claim 本身也写着留出（下面 L10 已从数据侧另查一次 n_ctx）。
  const sliceTxt = slice.txt.replace(/\s+/g, '');
  const noteTxt = String(art.judge_slice_note).replace(/\s+/g, '');
  const okSlice = slice.ok
    && sliceTxt.includes(String(art.judge_slice).replace(/\s+/g, ''))
    && noteTxt.slice(0, 24) !== ''
    && sliceTxt.includes(noteTxt.slice(0, 24))
    && sliceTxt.includes('留出');
  rec('L6 判决切片块可见，且 judge_slice 与 judge_slice_note **逐字取自产物**',
    okSlice,
    `可见=${slice.ok}；产物 judge_slice="${art.judge_slice}"`
    + ` note 前 24 字="${String(art.judge_slice_note).slice(0,24)}…"`
    + `；页面文本="${slice.txt.slice(0, 110)}"`);

  // ---- 7 并列口径必须与判决口径**印在同一块**，且标成不是判决 -------
  // 只印全量那组数字 = 把「抽取集上不显著」藏起来；
  // 只印留出那组数字 = 把「换个切片就不成立」藏起来。两条都要印。
  const va = (gates['G-b']||{}).evidence && gates['G-b'].evidence.variant_all_ctx;
  const vb = JSON.parse(await page.eval(`JSON.stringify((() => {
    const el = document.querySelector('[data-ltv-variant]');
    if(!el) return {ok:false, txt:''};
    const r = el.getBoundingClientRect();
    return { ok: r.height>0, txt: (el.innerText||'').trim() };
  })())`));
  const ge = gates['G-b'].evidence;
  const pExp = x => Number(x.sign_test_p).toExponential(3);
  const recAll = vb.txt.includes(`+1 ${va.n_plus}`) && vb.txt.includes(`−1 ${va.n_minus}`)
    && vb.txt.includes(pExp(va));
  const recJud = vb.txt.includes(`+1 ${ge.n_plus}`) && vb.txt.includes(`−1 ${ge.n_minus}`)
    && vb.txt.includes(pExp(ge));
  const marked = /不是判决/.test(vb.txt);
  rec('L7 G-b 的并列口径与判决口径印在**同一块**，且显式标注「不是判决」',
    vb.ok && recAll && recJud && marked,
    `可见=${vb.ok} 并列(${va.n_ctx} 上下文 +1 ${va.n_plus}/−1 ${va.n_minus} p=${pExp(va)})`
    + ` 印出=${recAll}；判决(${ge.n_ctx} 上下文 +1 ${ge.n_plus}/−1 ${ge.n_minus} p=${pExp(ge)})`
    + ` 印出=${recJud}；标了「不是判决」=${marked}`);

  // ---- 8 逐上下文表逐格对账 + **独立重算** ---------------------------
  // 独立重算的两处：
  //   (a) α*预测 = m_p / g_v —— 用 JSON 里的 m_p 与 g_v **现场算**，
  //       不信产物自己写的 alpha_star_pred。g_v≤0 时必须无预测（「—」）。
  //   (b) 切片计数 —— 数 DOM 上标「留出（参与判决）」的行数，
  //       与 G-a0.n_ctx / G-b.n_ctx 对账。
  const ctxRows = JSON.parse(await page.eval(`JSON.stringify(
    [...document.querySelectorAll('[data-ltvctx]')].map(tr => ({
      key: tr.getAttribute('data-ltvctx'),
      slice: tr.getAttribute('data-ltvslice'),
      cells: [...tr.querySelectorAll('td')].map(td => td.textContent.trim())
    })))`));
  const fmt3 = v => v == null ? '—' : Number(v).toFixed(3);
  const fmt4 = v => v == null ? '—' : Number(v).toFixed(4);
  const ctxBad = [];
  for (const d of ctxRows) {
    const c = (art.contexts||[]).find(x => x.pid + '@' + x.pos === d.key);
    if (!c) { ctxBad.push([d.key, 'DOM 有这行，产物 contexts[] 里没有']); continue; }
    // cells: 0=pid 1=pos 2=token 3=m_p 4=g_v 5=α*预测 6=α*实测 7=对照 8=切片 9=备注
    if (d.cells[0] !== c.pid) ctxBad.push([d.key, `题号：页面 ${d.cells[0]} vs 产物 ${c.pid}`]);
    if (d.cells[1] !== String(c.pos)) ctxBad.push([d.key, `pos：页面 ${d.cells[1]} vs 产物 ${c.pos}`]);
    if (d.cells[3] !== fmt4(c.m_p)) ctxBad.push([d.key, `m_p：页面 ${d.cells[3]} vs 产物 ${fmt4(c.m_p)}`]);
    if (d.cells[4] !== fmt4(c.g_v)) ctxBad.push([d.key, `g_v：页面 ${d.cells[4]} vs 产物 ${fmt4(c.g_v)}`]);
    if (d.cells[6] !== fmt3(c.alpha_star_meas)) ctxBad.push([d.key, `α*实测：页面 ${d.cells[6]} vs ${fmt3(c.alpha_star_meas)}`]);
    const ctl = c.ctl_all && (c.ctl_all.nm0 != null ? c.ctl_all.nm0 : c.ctl_all.nm1);
    if (d.cells[7] !== fmt3(ctl)) ctxBad.push([d.key, `对照 α*：页面 ${d.cells[7]} vs ${fmt3(ctl)}`]);
    // (a) 独立重算：α*预测 必须是 m_p / g_v 现场算出来的那个数
    const recomputed = c.g_v > 0 ? c.m_p / c.g_v : null;
    if (fmt3(recomputed) !== fmt3(c.alpha_star_pred))
      ctxBad.push([d.key, `产物自己的 α*预测 对不上重算：重算 ${fmt3(recomputed)} vs 产物 ${fmt3(c.alpha_star_pred)}`]);
    if (d.cells[5] !== fmt3(recomputed))
      ctxBad.push([d.key, `α*预测：页面 ${d.cells[5]} vs 独立重算 ${fmt3(recomputed)}`]);
    // 切片必须印在行上，且与产物 in_judge_slice 一致
    const wantSlice = c.in_judge_slice ? 'holdout' : 'extract';
    if (d.slice !== wantSlice) ctxBad.push([d.key, `切片：页面 ${d.slice} vs 产物 ${wantSlice}`]);
    if (c.in_judge_slice && !/留出/.test(d.cells[8])) ctxBad.push([d.key, '留出行没印「留出」']);
    if (!c.in_judge_slice && !/抽取/.test(d.cells[8])) ctxBad.push([d.key, '抽取行没印「抽取」']);
  }
  // (b) 独立数切片 —— ⚠⚠ 这里**必须数可见文案**，不能数 data-ltvslice。
  //   第一版读的是 `r.slice`（data-* 属性），判据名字却写着
  //   「页面上『留出（参与判决）』的行数」。变异台当场把这一版抓穿了：
  //   m3 把页面那一格改成硬编码的 `留出（参与判决）`（36 行全标留出），
  //   data-ltvslice 一个字没动 ⇒ **L9 照样绿**，
  //   而读者看到的是一张「全部都参与判决」的表。
  //   这就是「代理 ≠ 属性」：data 属性对不对，不等于读者看到什么。
  //   名字承诺可见文案，装置就得读可见文案；data-* 降级成交叉核对。
  const domHoldout = ctxRows.filter(r => /留出（参与判决）/.test(r.cells[8] || '')).length;
  const domExtract = ctxRows.filter(r => /抽取（不参与判决）/.test(r.cells[8] || '')).length;
  const attrHoldout = ctxRows.filter(r => r.slice === 'holdout').length;
  const artHoldout = (art.contexts||[]).filter(c => c.in_judge_slice).length;
  rec('L8 逐上下文表与产物 contexts[] **逐格**对账，且 α*预测 由判据用 m_p÷g_v 独立重算',
    ctxRows.length === (art.contexts||[]).length && ctxBad.length === 0,
    `DOM ${ctxRows.length} 行 / 产物 ${(art.contexts||[]).length} 行；错 ${ctxBad.length} 条`
    + (ctxBad.length ? `：${JSON.stringify(ctxBad).slice(0,400)}`
      : `；g_v≤0 的 ${(art.contexts||[]).filter(c=>c.g_v<=0).length} 行 α*预测 全部为「—」`));

  const sliceBad = [];
  for (const k of ['G-a0','G-b']) {
    if (gates[k].evidence.n_ctx !== artHoldout)
      sliceBad.push([k, `evidence.n_ctx=${gates[k].evidence.n_ctx} ≠ 上下文中 holdout 行数 ${artHoldout}`]);
  }
  rec('L9 页面上印着「留出（参与判决）」的行数 = 产物上下文里的 holdout 行数'
    + ' = 各门 evidence 写的 n_ctx（三方对账，**数可见文案**，不数 data-*）',
    domHoldout === artHoldout && domHoldout + domExtract === ctxRows.length
      && sliceBad.length === 0 && attrHoldout === domHoldout,
    `页面可见文案：留出 ${domHoldout} / 抽取 ${domExtract}（合计 ${ctxRows.length} 行）；`
    + `data-ltvslice=holdout ${attrHoldout}（只作交叉核对）；`
    + `contexts[].in_judge_slice ${artHoldout}；`
    + `G-a0.n_ctx=${gates['G-a0'].evidence.n_ctx} G-b.n_ctx=${gates['G-b'].evidence.n_ctx}；`
    + `不一致 ${JSON.stringify(sliceBad)}`);
  // G-a0 的适用率也独立重算一次（用 evidence 自己的两个分量）
  const e0 = gates['G-a0'].evidence;
  const appRecalc = e0.n_monotone / e0.n_ctx;
  const appShown = await page.eval(`(() => {
    const tr = document.querySelector('[data-ltvgate="G-a0"]');
    return tr ? (tr.children[2]||{}).textContent || '' : '';
  })()`);
  rec('L10 G-a0 的适用率由判据用 n_monotone÷n_ctx 独立重算，且与页面印出的对得上',
    Math.abs(appRecalc - e0.applicability) < 5e-4
      && appShown.includes((appRecalc*100).toFixed(1) + '%')
      && appShown.includes((e0.threshold*100).toFixed(1) + '%'),
    `重算 ${e0.n_monotone}/${e0.n_ctx} = ${(appRecalc*100).toFixed(1)}%（产物写 ${e0.applicability}，`
    + `门槛 ${(e0.threshold*100).toFixed(1)}%）；页面该行="${appShown.trim().slice(0,90)}"`);

  // ---- 11 敏感性表：degenerate_untested 不许被显示成通过 ----------
  const sens = ((gates['G-a']||{}).evidence||{}).fit_window_sensitivity || [];
  const sRows = JSON.parse(await page.eval(`JSON.stringify(
    [...document.querySelectorAll('[data-ltvsens]')].map(tr => ({
      win: tr.getAttribute('data-ltvsens'),
      verdict: tr.getAttribute('data-verdict'),
      cells: [...tr.querySelectorAll('td')].map(td => td.textContent.trim())
    })))`));
  const sBad = [];
  for (const s of sens) {
    const key = (s.fit_alphas||[]).join(',');
    const d = sRows.find(x => x.win === key);
    if (!d) { sBad.push([key, 'DOM 缺行']); continue; }
    if (d.verdict !== s.verdict) sBad.push([key, `判决：页面 ${d.verdict} vs 产物 ${s.verdict}`]);
    // cells: 0=窗 1=可判 2=窗内改口 3=差≤1档 4=同判删失 5=失败 6=判决
    const want = [String(s.n_judged), String(s.n_circular), String(s.n_within_one_notch),
                  String(s.n_both_censored), String(s.n_fail)];
    for (let i = 0; i < want.length; i++)
      if (d.cells[1+i] !== want[i]) sBad.push([key, `第${i+2}格：页面 ${d.cells[1+i]} vs 产物 ${want[i]}`]);
  }
  const degRows = sRows.filter(x => x.verdict === 'degenerate_untested');
  const degLeaked = degRows.filter(x => /通过|成立|^pass$/.test(x.cells[6] || ''));
  rec('L11 拟合窗敏感性表逐行与产物一致，且 degenerate_untested **不许**被显示成通过',
    sRows.length === sens.length && sBad.length === 0 && degLeaked.length === 0,
    `DOM ${sRows.length} 行 / 产物 ${sens.length} 行；不可判档 ${degRows.length} 条，`
    + `被误显示成通过的 ${degLeaked.length} 条；不一致 ${JSON.stringify(sBad).slice(0,300)}`);

  // ---- 12 诚实边界：条数相等且逐条逐字 ---------------------------
  const cav = JSON.parse(await page.eval(`JSON.stringify((() => {
    const el = document.querySelector('[data-ltv-caveats]');
    if(!el) return {ok:false, items:[]};
    const r = el.getBoundingClientRect();
    return { ok: r.height>0,
             items: [...el.querySelectorAll('li')].map(li => li.textContent.trim()) };
  })())`));
  const cavArt = art.caveats || [];
  const cavBad = [];
  if (cav.items.length !== cavArt.length)
    cavBad.push([`条数：页面 ${cav.items.length} vs 产物 ${cavArt.length}`]);
  cavArt.forEach((t, i) => {
    const got = cav.items[i];
    if (got == null) { cavBad.push([i+1, 'DOM 缺这一条']); return; }
    // HTML 会把空白折叠，两边都压掉空白再比
    const norm = s => s.replace(/\s+/g, ' ').trim();
    if (norm(got) !== norm(t)) cavBad.push([i+1, `页面 ${JSON.stringify(norm(got).slice(0,40))} vs 产物 ${JSON.stringify(norm(t).slice(0,40))}`]);
  });
  rec('L12 诚实边界**逐条逐字**转述且条数相等（后 3 条正是判决切片的披露）',
    cav.ok && cavBad.length === 0,
    `页面 ${cav.items.length} 条 / 产物 ${cavArt.length} 条；可见=${cav.ok}；`
    + `不一致 ${JSON.stringify(cavBad).slice(0,300)}`);

  // ---- 13 句子轴：11 条轴，其中 3 条必须被标成负对照 ---------------
  const sRows2 = JSON.parse(await page.eval(`JSON.stringify(
    [...document.querySelectorAll('[data-ltvsent]')].map(tr => ({
      key: tr.getAttribute('data-ltvsent'),
      neg: tr.getAttribute('data-ltvneg'),
      cells: [...tr.querySelectorAll('td')].map(td => td.textContent.trim())
    })))`));
  const axisBad = [];
  for (const s of art.sentence_diffs || []) {
    const d = sRows2.find(x => x.key === s.key);
    if (!d) { axisBad.push([s.key, 'DOM 缺行']); continue; }
    if (d.neg !== (s.negative_control ? '1' : '0'))
      axisBad.push([s.key, `负对照标记：页面 ${d.neg} vs 产物 ${s.negative_control}`]);
    if (s.negative_control && !/负对照/.test(d.cells[0]))
      axisBad.push([s.key, '负对照那行没印「负对照」字样']);
    // cells: 0=key 1=S 2=S' 3=‖S−S′‖
    if (d.cells[1] !== s.S) axisBad.push([s.key, `S 不符：页面 ${JSON.stringify(d.cells[1].slice(0,26))}`]);
    if (d.cells[2] !== s.Sp) axisBad.push([s.key, `S′ 不符：页面 ${JSON.stringify(d.cells[2].slice(0,26))}`]);
    if (d.cells[3] !== Number(s.norm).toFixed(3))
      axisBad.push([s.key, `范数：页面 ${d.cells[3]} vs 产物 ${Number(s.norm).toFixed(3)}`]);
  }
  const negArt = (art.sentence_diffs||[]).filter(s => s.negative_control).length;
  rec('L13 句子轴逐行对账，3 条**负对照**都在且被标出来（只挑有利的轴 = 名字是编的）',
    sRows2.length === (art.sentence_diffs||[]).length && axisBad.length === 0
      && sRows2.filter(x => x.neg === '1').length === negArt,
    `DOM ${sRows2.length} 行（其中标负对照 ${sRows2.filter(x=>x.neg==='1').length} 条）/ `
    + `产物 ${(art.sentence_diffs||[]).length} 轴（其中负对照 ${negArt} 条）；`
    + `不一致 ${JSON.stringify(axisBad).slice(0,300)}`);

  // ---- 14 产物自陈的诚实边界：S1 那道门必须看得见 ------------------
  const wrapTxt = await page.eval(`(document.getElementById('ltvWrap')||{}).innerText || ''`);
  const saysIdentity = /恒等自证/.test(wrapTxt);
  rec('L14 S1 自检门在页面上看得见（恒等自证 n/n 个上下文输出不变）', saysIdentity,
    `产物 S1：n_identity_ok=${gates['S1'].evidence.n_identity_ok}/${gates['S1'].evidence.n_ctx}；`
    + `页面提到「恒等自证」=${saysIdentity}`);

  // ---- 15 可见文本里每个 `**` 都得在产物里找到出处 -----------------
  // ⚠⚠ 这条是**被一个真 bug 逼出来的**，不是补形式：
  //   本判据第一次跑出 16/16 全绿，而页面上肉眼可见的两处自己的文案
  //   把 Markdown 的 `**` 原样印了出来（HTML 不渲染 Markdown）。
  //   16/16 全绿 + 肉眼能看见的破字 = **覆盖缺口**，不是「判据够严了」。
  //
  //   这里查的不是「有没有 `**`」——产物文案里本来就有（第 7 屏有 14 处，
  //   逐字转述要求不许改它）。查的是**数目对不对**：
  //   页面上出现的每一个 `**` 都必须能在「页面逐字转述的那些产物字段」里
  //   找到出处，一个都不许多。自己的文案漏转 ⇒ 多出来的，无出处 ⇒ 红。
  const countStars = s => (s.match(/\*\*/g) || []).length;
  const transcribed = [];
  for (const k of order) {
    const g = gates[k];
    // ⚠⚠ 清单里必须包含页面**逐字转述的每一个**产物字段，一个都不能漏。
    //   第一版这份清单只有 claim / role / why_na / verdict_reason，漏了 `name` ——
    //   而判决表第一格印的就是 `g.name`。后来 S1 的 name 里带了 `**`（产品文案用
    //   Markdown 标重点的既有约定），页面原样印出 2 个星号，而清单没这一项
    //   ⇒ L15 报 22 vs 20。**是清单漏了，不是页面多印了。**
    //   这条纪律的一般形式：**「页面转述了哪些字段」必须由字段清单驱动，
    //   而不是靠人记得有几个。**
    for (const f of ['name', 'claim', 'role', 'why_na', 'verdict_reason']) {
      if (g && g[f]) transcribed.push([`gates.${k}.${f}`, g[f]]);
    }
  }
  for (const f of ['judge_slice_note']) if (art[f]) transcribed.push([f, art[f]]);
  (art.caveats || []).forEach((t, i) => transcribed.push([`caveats[${i}]`, t]));
  const expectStars = transcribed.reduce((n, [, t]) => n + countStars(String(t)), 0);
  const domStars = countStars(wrapTxt);
  const starSrc = transcribed.filter(([, t]) => countStars(String(t)))
    .map(([n, t]) => `${n}×${countStars(String(t))}`);
  rec('L15 可见文本里每个 `**` 都能在产物里找到出处（自己的文案漏转 Markdown 就会多出来）',
    domStars === expectStars,
    `页面 ${domStars} 个 \\*\\* / 产物转述字段合计 ${expectStars} 个；`
    + `带星号的字段：${starSrc.join('、')}`);

  // ---- 16..18 ① 稀疏分解：否定结论不许被折叠，系数不许被抄错 ----------
  // ⚠ 这一段对应的是上一版屏上那句**假话**：「它们和另外 8 条一起进稀疏分解」。
  //   分解当时从未被执行过（探针只算出 d_k）。现在补算了，结论是**否定**的
  //   （全解只解释 7.807%，前 8 条里 2 条负对照）。
  //   ⇒ 否定结论与肯定结论**同等对待**：必须在页面上看得见、且数对。
  const dc = art.decomp;
  const dblk = JSON.parse(await page.eval(`JSON.stringify((() => {
    const el = document.querySelector('[data-ltv-decomp]');
    if(!el) return {ok:false, txt:''};
    const r = el.getBoundingClientRect();
    return { ok: r.height>0, txt: (el.innerText||'').trim() };
  })())`));
  const p1 = x => (x * 100).toFixed(3) + '%';
  rec('L16 「这个分解没有交付」那块**可见**，且解释率/截断能量与产物 decomp 逐字相符',
    !!dc && dblk.ok
      && dblk.txt.includes(p1(dc.explained_energy))
      && dblk.txt.includes(p1(dc.top_k_energy)),
    `可见=${dblk.ok}；产物 explained_energy=${dc ? p1(dc.explained_energy) : '—'} `
    + `top_k_energy=${dc ? p1(dc.top_k_energy) : '—'}；`
    + `页面文本="${dblk.txt.slice(0, 110)}"`);

  // 逐轴：cos² 与 c_k 必须与产物一致，且负对照行同样印着它们的数
  const sRows3 = JSON.parse(await page.eval(`JSON.stringify(
    [...document.querySelectorAll('[data-ltvsent]')].map(tr => ({
      key: tr.getAttribute('data-ltvsent'),
      neg: tr.getAttribute('data-ltvneg'),
      top: tr.getAttribute('data-ltvsenttop'),
      cells: [...tr.querySelectorAll('td')].map(td => td.textContent.trim())
    })))`));
  const axByKey = {};
  for (const a of ((dc||{}).axes||[])) axByKey[a.key] = a;
  const axBad = [];
  for (const d of sRows3) {
    const a = axByKey[d.key];
    if (!a) { axBad.push([d.key, '产物 decomp.axes 里没有这一轴']); continue; }
    if (d.cells[4] !== (a.cos*100).toFixed(2)+'%')
      axBad.push([d.key, `cos²：页面 ${d.cells[4]} vs 产物 ${(a.cos*100).toFixed(2)}%`]);
    if (d.cells[5] !== Number(a.c).toFixed(5))
      axBad.push([d.key, `c_k：页面 ${d.cells[5]} vs 产物 ${Number(a.c).toFixed(5)}`]);
    const wantTop = (dc.top_k||[]).indexOf(d.key) >= 0;
    if ((d.top === '1') !== wantTop)
      axBad.push([d.key, `入选标记：页面 ${d.top} vs 产物 ${wantTop}`]);
  }
  rec('L17 句子轴逐行印出 cos² 与 c_k，与产物 decomp.axes 逐条相符',
    !!dc && sRows3.length === (art.sentence_diffs||[]).length && axBad.length === 0,
    `DOM ${sRows3.length} 行 / 产物 ${(art.sentence_diffs||[]).length} 轴；`
    + `错 ${axBad.length} 条${axBad.length ? '：' + JSON.stringify(axBad).slice(0,300) : ''}`);

  // 负对照进了选中 —— 这条是「名字可疑」最直接的证据，必须**可数**，
  // 而且判据数的是**可见文案**（同行第一格里的「被 |c| 前 K 选中」），
  // 不是 data-ltvsenttop。
  const negInTopVis = sRows3.filter(r => r.neg === '1'
    && /被 \|c\| 前 \d+ 选中/.test(r.cells[0] || '')).map(r => r.key);
  const negInTopAttr = sRows3.filter(r => r.neg === '1' && r.top === '1').map(r => r.key);
  const wantNeg = (dc ? dc.top_k : []).filter(k => (axByKey[k]||{}).negative_control);
  rec('L18 负对照进了选中——**数可见文案**（数的是「被 |c| 前 K 选中」那行字，不是 data-*）',
    !!dc && JSON.stringify(negInTopVis.slice().sort())
      === JSON.stringify(wantNeg.slice().sort())
      && JSON.stringify(negInTopAttr.slice().sort())
        === JSON.stringify(negInTopVis.slice().sort()),
    `产物 top_k 里的负对照 = ${JSON.stringify(wantNeg)}（${wantNeg.length} 条）；`
    + `页面可见文案数出 ${JSON.stringify(negInTopVis)}；data-* 数出 ${JSON.stringify(negInTopAttr)}`);

  // ---- G-c：这一轮真被测了，判决是 fail ---------------------------------
  // ⚠ 这一段的由来：G-c 原本是 build_ltv 里**写死的 na**，页面也写死了
  //   「那一道门本轮仍是「没测」」。现在它真跑了，判 fail。
  //   判据盯两件事：① 逐档读数块**可见**且逐格对得上产物
  //             ② 页面不再印那句已经过时的「仍是没测」。
  //   同样地，取的是**可见文本**（innerText），data-* 只作交叉核对。
  const gc = (art.gates || {})['G-c'] || {};
  const gcEv = gc.evidence || {};
  const gcA = Object.keys(gcEv.per_alpha || {});
  const gcSeen = JSON.parse(await page.eval(`JSON.stringify((() => {
    const blk = document.querySelector('[data-ltvgc]');
    const rows = Array.from(document.querySelectorAll('[data-ltvgcalpha]'));
    return {
      hasBlock: !!blk,
      verdict: blk ? (blk.getAttribute('data-ltvgcverdict') || '') : '',
      text: blk ? (blk.innerText || '') : '',
      rows: rows.map(r => ({
        alpha: r.getAttribute('data-ltvgcalpha') || '',
        all: r.getAttribute('data-ltvgcall') || '',
        cells: Array.from(r.querySelectorAll('td')).map(td => (td.innerText || '').trim())
      })),
      stale: /那一道门本轮仍是/.test(document.body.innerText || '')
    };
  })())`));

  const gcBad = [];
  for (const a of gcA) {
    const r = (gcEv.per_alpha || {})[a] || {};
    const row = gcSeen.rows.find(x => x.alpha === a);
    if (!row) { gcBad.push([a, '页面上没有这一档的行']); continue; }
    // 前 5 格是 α / arm / rand / zero / Δ
    // ⚠ 比较必须按**数值**：`Number("0.000")` 是 0，与字符串 "0.000" 做
    //   JSON 严格比较会判不符 —— 那是判据自己的类型错，不是页面印错。
    const want = ['arm', 'rand', 'zero'].map(k => Number((r.rates || {})[k] || 0));
    const gotN = row.cells.slice(1, 4).map(s => (Number.isFinite(Number(s)) ? Number(s) : NaN));
    for (let i = 0; i < 3; i++) {
      if (!(Math.abs(gotN[i] - want[i]) <= 5e-4)) {
        gcBad.push([a, ['arm', 'rand', 'zero'][i] + ' 率', row.cells[i + 1], want[i]]);
      }
    }
    const shownD = Number((row.cells[4] || '').replace('+', ''));
    const wantD = Number(r.d_arm_minus_rand || 0);
    if (!(Math.abs(shownD - wantD) <= 5e-4)) gcBad.push([a, 'Δ', row.cells[4], wantD]);
    const marks = row.cells.slice(5, 8);
    const wantM = [r.c1_direction, r.c2_per_problem, r.c3_negative_control];
    for (let i = 0; i < 3; i++) {
      const isYes = (marks[i] || '').trim().startsWith('✓');
      if (wantM[i] && !isYes) gcBad.push([a, `子判据 ${i + 1} 应为 ✓，页面是`, marks[i]]);
      if (!wantM[i] && isYes) gcBad.push([a, `子判据 ${i + 1} 应为 ✗，页面却显示 ✓`]);
    }
    // 第 8 格「该档总：成立／不成立」也要对账。
    // ⚠ 这一格是第一版漏掉的：变异 M3 把 `r.all_three_hold` 换成 `true`
    //   （页面把三档全不成立印成「成立」），L19 当时 22/22 全绿 ——
    //   查了三条子判据却没查汇总结论，而汇总结论正是读者最先看的那一格。
    const tot = (row.cells[8] || '').trim();
    const wantTot = r.all_three_hold;
    if (wantTot && tot !== '成立') gcBad.push([a, '该档总应为「成立」，页面是', tot]);
    if (!wantTot && tot !== '不成立') {
      gcBad.push([a, '该档总应为「不成立」，页面却是', tot,
                  '⚠ 把不成立显示成成立 = 假绿']);
    }
    // data-ltvgcall 只作交叉核对
    if ((row.all === '1') !== !!wantTot) {
      gcBad.push([a, 'data-ltvgcall 与产物 all_three_hold 不符', row.all, wantTot]);
    }
  }
  rec('L19 G-c 逐档读数块**可见**，三臂率/Δ/三条子判据与产物逐格相符'
    + '（取可见文本 innerText，data-* 只作交叉核对）',
    gcSeen.hasBlock && gcSeen.rows.length === gcA.length && gcBad.length === 0,
    `产物判决=${gc.verdict}（data-* 读回 ${gcSeen.verdict}）；`
    + `档数 产物 ${gcA.length} / 页面 ${gcSeen.rows.length}；`
    + `不成立档=${JSON.stringify(gcEv.failed_alphas || [])}；`
    + `不符 ${gcBad.length} 处`
    + (gcBad.length ? '：' + JSON.stringify(gcBad).slice(0, 300) : '')
    + (gcSeen.text ? '｜可见文本前 80 字="' + gcSeen.text.replace(/\s+/g, ' ').slice(0, 80) + '"' : ''));

  rec('L20 G-c 真被测过之后，页面不再印「那一道门本轮仍是没测」'
    + '（⚠ 这句在 G-c 还是 na 时是对的，测了之后它就是假陈述）',
    gcSeen.hasBlock && !gcSeen.stale,
    `产物 G-c verdict=${gc.verdict}（判过 ⇒ 不是 na）；`
    + `逐档读数块存在=${gcSeen.hasBlock}；页面仍含「那一道门本轮仍是」=${gcSeen.stale}`);

} catch (e) {
  console.log('[FAIL] 脚本中断：' + e.message);
  R.push({ n: '脚本中断', p: false });
} finally {
  const red = R.filter(r => !r.p);
  // ⚠ 汇总行**必须**是 `=== N/M passed ===`。run_chain.sh 只认 `^RESULT`
  //   与 `^=== [0-9]+/` ⇒ 自创格式会被判成 NORUN（读法是「一条都没跑」），
  //   也就是：一个全绿、真在浏览器里点过的判据，在汇总里与「压根没执行」
  //   长得一模一样。房里的 node 判据统一用 `=== N/M passed ===`。
  console.log(`\n=== ${R.length - red.length}/${R.length} passed ===`);
  if (red.length) red.forEach(r => console.log('   红：' + r.n));
  try { proc.kill(); } catch {}
  process.exit(red.length ? 1 : 0);
}
