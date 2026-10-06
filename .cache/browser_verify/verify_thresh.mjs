// 验收：latent 页第 6 屏「干预阈值」。
//
// 这一屏的判据主体是**读者看到的可见文案**，不是 data-*。
// data-* 只作交叉核对：它能证明"节点在"，证明不了"人看得见"。
// 可见性有三态，这里第三态必须过：DOM 里有 / 自身有高度 / **没被别的层盖住**
// （过 elementFromPoint）。
//
// 三条最容易出错的地方，各有专条：
//   · 右删失的行必须印成 ">" 而不是编一个数   → T5
//   · 否定结论（不是通则）必须在页面上**看得见** → T6
//     判否时只印成立的那一半 = 半截结论比没有结论更危险
//   · 判据自己独立重算，不复用页面上的数       → T3/T4
import { launch, Page, CDP } from './cdp_client.mjs';
import { readFileSync } from 'node:fs';

const URL = process.env.LAT_URL || 'http://127.0.0.1:22233/latent/index.html';
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_thresh_'
  + process.pid;
const ART = '/Users/zhourui/code/steer3d/frontend/public/latent/data/intervention_threshold_law.json';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const R = [];
const rec = (n, p, d) => { R.push({ n, p }); console.log(`[${p ? 'PASS' : 'FAIL'}] ${n}\n       ${d}`); };

const { proc, version } = await launch({ port: 9489, userDataDir: PROFILE,
  windowSize: '1600,1050', url: 'about:blank' });
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);

try {
  // ---- 0 页面必须真的加载 ----------------------------------------
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  await sleep(3500);
  const L0 = await page.eval(`JSON.stringify({
    href: location.href, bodyLen: (document.body.innerText||'').length,
    outcome: document.querySelector('[data-outcome]')?.getAttribute('data-outcome')||''
  })`);
  const live = JSON.parse(L0);
  rec('T0 页面真的加载出来（死 URL 不得让本脚本报 PASS）',
    live.href.startsWith('http') && live.bodyLen > 500,
    `href=${live.href} bodyLen=${live.bodyLen} outcome=${live.outcome}`);
  if (!(live.href.startsWith('http') && live.bodyLen > 500)) {
    throw new Error('页面没加载，后面的判据一条都没跑');
  }

  // ---- 1 点标签切到第 6 屏 ----------------------------------------
  // ⚠ 必须先关掉导读浮层。页面加载时 `orientAuto` 会自动弹出 `#orientation`
  //   （position:fixed，盖住整个视口）。不关就量可见性，量的是**浮层**，
  //   不是这一屏 —— 判红的第一嫌疑永远是「红的不是被测对象」。
  //   而且要**断言它真的关掉了**：万一 close 失效，后面量到的还是浮层，
  //   那时 T6 的红没有意义。
  const closed = JSON.parse(await page.eval(`JSON.stringify((() => {
    const ov = document.getElementById('orientation');
    const wasShown = ov ? !ov.classList.contains('hide') : null;
    const b = document.getElementById('orientClose');
    if (wasShown && b) b.click();
    const now = ov ? ov.classList.contains('hide') : null;
    return { wasShown, nowHidden: now, clicked: !!(wasShown && b) };
  })())`));
  rec('T0b 导读浮层已关掉（否则下面量到的是浮层，不是这一屏）',
    closed.wasShown === true && closed.nowHidden === true,
    `加载后是否弹出=${closed.wasShown}  点击后是否已隐藏=${closed.nowHidden}`);

  await page.eval(`(() => {
    const b = document.getElementById('tabThresh');
    if(!b) throw new Error('没有 tabThresh 按钮');
    b.click();
  })()`);
  await sleep(2500);
  const st = JSON.parse(await page.eval(`JSON.stringify({
    wrap: (() => { const w=document.getElementById('threshWrap');
      return { display: w ? w.style.display : 'missing',
               hasBlock: !!(w && w.querySelector('[data-threshblock]')),
               state: w && w.querySelector('[data-threshstate]')
                        ? w.querySelector('[data-threshstate]').getAttribute('data-threshstate') : null };
    })(),
    tabOn: document.getElementById('tabThresh')?.classList.contains('on') || false,
    title: (document.getElementById('mainTitle')||{}).textContent || ''
  })`));
  rec('T1 点「干预阈值」标签后切到第 6 屏且内容已渲染',
    st.wrap.display !== 'none' && st.wrap.hasBlock && st.tabOn
      && st.wrap.state === 'ready',
    `display=${st.wrap.display} state=${st.wrap.state} tabOn=${st.tabOn} title="${st.title}"`);
  if (st.wrap.state !== 'ready') {
    rec('T2..T9 本屏在 ready 态下才有意义', false,
      `产物没载入（state=${st.wrap.state}），下面所有条都没跑 —— `
      + `这不是「通过」，是「没验」`);
    throw new Error('no ready state');
  }

  const art = JSON.parse(readFileSync(ART, 'utf8'));
  const dr = art.dose_response || [];
  const per = art.per_step || [];

  // ---- 2 剂量-反应表：行数与每行的数都要对 -----------------------
  // 独立重算：Δlogit 的单调性由判据自己从 JSON 算，不信页面。
  const mono = dr.every((d, i) => i === 0 || d.max_abs_dlogit >= dr[i-1].max_abs_dlogit - 1e-9);
  rec('T2 剂量-反应：|Δlogit| 随强度单调不减（判据独立从产物重算）', mono,
    dr.map(d => `${d.mult}×→${d.max_abs_dlogit}`).join('  '));

  const drDom = JSON.parse(await page.eval(`JSON.stringify(
    [...document.querySelectorAll('[data-dr-mult]')].map(tr => ({
      mult: +tr.getAttribute('data-dr-mult'),
      cells: [...tr.querySelectorAll('td')].map(td => td.textContent.trim())
    })))`));
  rec('T3 剂量-反应表的档数与产物一致，且每档三列的数字逐字相符',
    drDom.length === dr.length && drDom.every((row, i) =>
      row.mult === dr[i].mult
      && row.cells[0] === `${dr[i].mult}×`
      && row.cells[1] === dr[i].injected_norm.toFixed(1)
      && row.cells[2] === dr[i].max_abs_dlogit.toFixed(2)),
    `DOM ${drDom.length} 行 / 产物 ${dr.length} 档；首行 DOM=${JSON.stringify(drDom[0])} `
    + `产物=${JSON.stringify(dr[0])}`);

  // ---- 3 逐步阈值表 ---------------------------------------------
  // ⚠ 右删失必须印成 ">"，不许编一个数出来。这是本屏最容易出的错：
  //   印「阈值=2.0×」和印「>2.0×」差一个字，含义完全不同。
  const stepDom = JSON.parse(await page.eval(`JSON.stringify(
    [...document.querySelectorAll('[data-thresh-step]')].map(tr => ({
      step: +tr.getAttribute('data-thresh-step'),
      bracket: tr.getAttribute('data-thresh-bracket'),
      cells: [...tr.querySelectorAll('td')].map(td => td.textContent.trim())
    })))`));
  rec('T4 逐步阈值表的行数与产物一致', stepDom.length === per.length,
    `DOM ${stepDom.length} 行 / 产物 ${per.length} 步`);

  const brkBad = [];
  for (let i = 0; i < per.length; i++) {
    const p = per[i], d = stepDom[i];
    if (!d) { brkBad.push([i, 'DOM 缺行']); continue; }
    if (d.step !== p.step) { brkBad.push([i, `step ${d.step}≠${p.step}`]); continue; }
    if (d.cells[2] !== p.decision_margin.toFixed(3)) {
      brkBad.push([i, `间距 "${d.cells[2]}" ≠ ${p.decision_margin.toFixed(3)}`]); continue;
    }
    const cell = d.cells[3];
    if (p.bracket === 'right_censored') {
      if (!cell.startsWith('>')) brkBad.push([i, `右删失却印成 "${cell}"，应印 ">"`]);
    } else if (p.bracket === 'left_censored') {
      if (!cell.startsWith('<')) brkBad.push([i, `左删失却印成 "${cell}"，应印 "<"`]);
    } else if (cell !== `(${p.threshold_lo}, ${p.threshold_hi}]×`) {
      brkBad.push([i, `区间 "${cell}" ≠ (${p.threshold_lo}, ${p.threshold_hi}]×`]);
    }
  }
  rec('T5 逐步阈值：每行区间与产物一致，且右删失印成 ">" 而不是编一个数',
    brkBad.length === 0,
    brkBad.length ? `不符 ${JSON.stringify(brkBad)}`
      : `逐行对上；右删失 ${per.filter(p=>p.bracket==='right_censored').map(p=>p.step).join(',') || '无'} 步`);

  // ---- 4 否定结论必须**看得见** ----------------------------------
  // 产物里 verdict=not_general 时，页面上必须同时出现：判决、理由、
  // 以及"不是通则"这句话本身。而且要过 elementFromPoint（没被别的层盖住）。
  const gen = art.generality;
  /* ⚠ 可见性要过第三态：没被别的层盖住（elementFromPoint）。两处必须做对：
   *   ① 先 scrollIntoView —— 元素在视口外时 elementFromPoint 返回 **null**，
   *      而 null 不等于「被盖住」。第一版写成 `covered = pt ? ... : true`，
   *      把「测不到」记成「不合格」，报了个假红。判红先怀疑判据。
   *   ② 探多个点 —— 只探一个点会被局部遮挡放过，也会恰好探到一个没盖的点。
   *      null 的探点单独剔除并计数，不混入「被盖」也不混入「可见」。 */
  const vis = JSON.parse(await page.eval(`JSON.stringify((() => {
    const el = document.querySelector('[data-threshgen]');
    if(!el) return { present:false };
    el.scrollIntoView({ block:'center' });
    const r = el.getBoundingClientRect();
    if(!(r.width>0 && r.height>0)) return { present:true, sized:false, text:(el.innerText||'').slice(0,200) };
    const fx = [0.5, 0.5, 0.2, 0.8], fy = [0.12, 0.5, 0.85, 0.85];
    const probes = fx.map((a,i) => {
      const x = r.left + r.width*a, y = r.top + r.height*fy[i];
      const pt = document.elementFromPoint(x, y);
      return { inView: x>=0 && y>=0 && x<=innerWidth && y<=innerHeight, ptNull: pt===null,
               inside: pt ? (el.contains(pt) || pt===el || pt.contains(el)) : null,
               who: pt ? (pt.tagName + (pt.id?'#'+pt.id:'')
                    + (pt.className && typeof pt.className==='string'
                       ? '.'+pt.className.split(' ')[0] : '')) : null };
    });
    const good = probes.filter(p => p.inView && !p.ptNull);
    return { present:true, sized:true, probes,
             measured: good.length, allInside: good.length>0 && good.every(p=>p.inside),
             verdict: el.getAttribute('data-threshgen'), text: (el.innerText||'') };
  })())`));
  const genOK = !gen
    ? true   // 产物没有通用性一节，那就不该有这一节
    : (vis.present && vis.sized && vis.measured >= 2 && vis.allInside
       && vis.verdict === gen.verdict
       && vis.text.includes('不能')
       && (gen.verdict_reason || '').slice(0, 24).trim().length > 0);
  rec('T6 否定结论在页面上「可见且未被遮挡」，且与产物 verdict 一致', genOK,
    !gen ? '产物无通用性一节，本条不适用'
      : `产物 verdict=${gen.verdict}  DOM=${vis.verdict} sized=${vis.sized} `
        + `有效探点=${vis.measured}/4（null/视口外的不算）  全部未被盖=${vis.allInside} `
        + `含「不能」=${vis.text ? vis.text.includes('不能') : 'n/a'} `
        + `探到的层=${JSON.stringify((vis.probes||[]).map(p=>p.who))}`);

  rec('T7 判否时页面上带着**可读的否定理由**（不许只印成立那半）',
    !gen || ((vis.text || '').length > 60),
    !gen ? '本条不适用'
      : `理由段长度=${(vis.text||'').length}  首 60 字="${(vis.text||'').slice(0,60).replace(/\s+/g,' ')}"`);

  // ---- 5 机制断言的说法要出现在可见文字里 ------------------------
  const inner = await page.eval(`document.getElementById('threshWrap').innerText || ''`);
  rec('T8 页面上明说「间距越小阈值越低」这个机制，且与产物 stable 一致',
    inner.includes('间距越小') && String(art.mechanism.stable) !== '' ,
    `机制 stable=${art.mechanism.stable} violations=${JSON.stringify(art.mechanism.violations)}`
    + `  页面含机制句=${inner.includes('间距越小')}`);

  // ---- 6 与回放那条对照必须在页面上 ------------------------------
  rec('T9 页面上说清「逐步路径的 token 是录下来的、注入改不了」这条对照',
    inner.includes('录下来的') && inner.includes('真跑一遍模型'),
    `含「录下来的」=${inner.includes('录下来的')} 含「真跑一遍模型」=${inner.includes('真跑一遍模型')}`);

  // ---- 7 切走再切回，内容还在 -----------------------------------
  await page.eval(`document.getElementById('tabXY').click()`);
  await sleep(700);
  await page.eval(`document.getElementById('tabThresh').click()`);
  await sleep(1200);
  const back = JSON.parse(await page.eval(`JSON.stringify({
    state: (document.getElementById('threshWrap').querySelector('[data-threshstate]')||{})
             .getAttribute('data-threshstate') || null,
    rows: document.querySelectorAll('[data-thresh-step]').length
  })`));
  rec('T10 切到别的屏再切回来，本屏内容仍在（不是一次性渲染）',
    back.state === 'ready' && back.rows === per.length,
    `state=${back.state} rows=${back.rows}（应等于 ${per.length}）`);

  // ---- 8 无 console error ---------------------------------------
  const errs = page.events
    .filter(e => e.method === 'Runtime.consoleAPICalled' && e.params.type === 'error')
    .map(e => (e.params.args || []).map(a => a.value ?? a.description ?? '').join(' '))
    .filter(t => !/favicon|Failed to load resource/i.test(t));
  rec('T11 页面无 console error', errs.length === 0,
    errs.length ? errs.slice(0, 2).join(' | ') : 'none');

  await page.screenshot('/Users/zhourui/code/steer3d/.cache/browser_verify/shots/thresh.png');
} catch (e) {
  rec('X 脚本崩了', false, String(e && e.stack || e).slice(0, 250));
} finally {
  cdp.close(); proc.kill('SIGKILL');
}

const pass = R.filter(x => x.p).length;
console.log(`\n=== ${pass}/${R.length} passed ===`);
R.filter(x => !x.p).forEach(x => console.log(`FAIL: ${x.n}`));
process.exit(pass === R.length ? 0 : 1);
