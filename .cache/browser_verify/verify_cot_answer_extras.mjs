import { launch, Page, CDP } from './cdp_client.mjs';
import { readFileSync } from 'fs';

/**
 * 第二十三笔 W 组：**三块从 drawDeltaSide() 搬进 #extras 之后，它们真的渲染吗。**
 *
 * ## 为什么要有这一组
 *
 * 第二十三笔要修的病是「块在源码里、判据也可能读它，但默认视图永远不渲染」。
 * ⇒ 判据主体必须是**渲染层**：数 DOM 里的块、读它印出来的字、点它的芯片。
 *   只扫源码会给出假绿 —— 源码里那 16 个 data-cot* / data-ar* 一个都不少。
 *
 * ## 病根（写在这里，免得下一轮重新查一遍）
 *
 *   drawDeltaSide()  --if(!p || !S.pMeta) return-->  之后才调
 *     renderCotEffect()  --内部调-->  renderAnswerReadout() / renderCotTexts()
 *
 *   S.pMeta 要用户点开「干预 vs 对照」某个配对才加载，
 *   于是默认视图里这三块一个都不在。数据（S.cot / S.cotTexts / S.ansRead）
 *   反而是 boot 里就取回好的 —— 东西在，只是没地方显示。
 *
 * ## 判据不许证明什么
 *
 * - **不许证明排版好看**。本环境是沙箱 Chromium，没有 WebGL，
 *   也没有人看过这三块并排之后的观感 ⇒ 排版必须由用户在真浏览器里看。
 * - **不许把「块存在」当成「读者看得到」**。W1–W3 要求 innerText 有实质长度，
 *   就是为了排除「元素在、内容是空壳」。
 */
const URL = process.env.LAT_URL || 'http://127.0.0.1:22113/latent/index.html';
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_w_' + process.pid;
const sleep = ms => new Promise(r => setTimeout(r, ms));

let pass = 0, total = 0;
const rows = [];
function rec(name, ok, detail) {
  total++; if (ok) pass++;
  rows.push([ok, name, detail]);
  console.log('[%s] %s\n       %s', ok ? 'PASS' : 'FAIL', name, detail);
}

const { proc, version } = await launch({
  port: 9800 + (process.pid % 180), userDataDir: PROFILE,
  windowSize: '1900,3200', url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);

try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});

  // 等 #extras 里出现思维链块，而不是等固定秒数。
  let waited = 0, st = null;
  while (waited < 45000) {
    st = await page.eval(`(() => {
      const host = document.getElementById('extras');
      if(!host) return { host: false };
      const txt = s => { const e = host.querySelector(s);
                         return e ? (e.innerText || '').trim() : null; };
      const len = s => { const e = host.querySelector(s);
                         return e ? (e.innerText || '').replace(/\\s+/g,' ').trim().length : 0; };
      const n = s => host.querySelectorAll(s).length;
      return {
        host: true,
        hostLen: (host.innerText || '').replace(/\\s+/g,' ').trim().length,
        cotLen: len('[data-cotblock]'), ansLen: len('[data-aroot]'),
        txtLen: len('[data-cottext]'),
        cotDirs: n('[data-cotdir]'), arPicks: n('[data-arpick]'),
        cotPick: !!host.querySelector('[data-cotpick]'),
        dvRoot: host.querySelector('[data-dvroot]') ? 1 : 0,
        // ⚠ W4 第一版把「游离的 <tr>」写成「DOM 里 <tr> 数为 0」。
        //   那是**判据自己写反了**：我给 renderCotEffect() 包了一张 <table>，
        //   所以 4 个 <tr> 出现恰恰是**正确**的（包表就是为了让它们不被丢掉）。
        //   真正要验的不变式是：**浏览器丢没丢行** ——
        //   innerHTML 里有几个 <tr，DOM 里就该有几个；少了就是被静默丢掉了。
        trInHtml: (host.innerHTML.match(/<tr[\\s>]/gi) || []).length,
        trInDom: host.querySelectorAll('tr').length,
        trInTable: host.querySelectorAll('table tr').length,
        cotText: (txt('[data-cotblock]') || '').slice(0, 90),
        ansText: (txt('[data-aroot]') || '').slice(0, 90),
        // 方向/题号相关的正文**全文**（用来判「点了真的换了」）
        cotFull: (txt('[data-cotblock]') || '').replace(/\\s+/g, ' ').trim(),
        ansFull: (txt('[data-aroot]') || '').replace(/\\s+/g, ' ').trim(),
      };
    })()`);
    if (st.host && st.cotLen > 200) break;
    await sleep(1200);
    waited += 1200;
  }

  rec('W0 #extras 面板存在，且不是空壳',
      !!(st && st.host && st.hostLen > 500),
      st && st.host ? `#extras 正文 ${st.hostLen} 字，等了 ${waited}ms`
                    : `等了 ${waited}ms 仍无 #extras`);

  rec('W1 思维链层面那块渲染出实质内容（不是元素在、内容空）',
      !!(st && st.cotLen > 200),
      st ? `[data-cotblock] 正文 ${st.cotLen} 字：${(st.cotText || '').replace(/\n/g, ' ')}`
         : '没读到');

  rec('W2 答案位移逐篇读那块渲染出实质内容',
      !!(st && st.ansLen > 200),
      st ? `[data-aroot] 正文 ${st.ansLen} 字：${(st.ansText || '').replace(/\n/g, ' ')}`
         : '没读到');

  rec('W3 逐字读那块渲染出实质内容',
      !!(st && st.txtLen > 200),
      st ? `[data-cottext] 正文 ${st.txtLen} 字` : '没读到');

  rec('W4 浏览器不许静默丢掉 <tr> 行（#extras 是 div，不包表的话整块连「没有数据」一起消失）',
      !!(st && st.trInHtml > 0 && st.trInHtml === st.trInDom
                && st.trInDom === st.trInTable),
      st ? `HTML 里 <tr> ${st.trInHtml} 个 / DOM 里 ${st.trInDom} 个 / 表内 ${st.trInTable} 个`
           + '（三者相等 = 一行没丢）'
         : '没读到');

  // W5：点方向芯片，正文必须真的变。
  // ⚠⚠ 第一版只比**前 80 个字**，而那 80 字是块标题（「向量把思维链改成了什么样 …」），
  //   它本来就不随芯片变 ⇒ 点对了也判红。
  //   那一版还恰好把真信号印在诊断行里（高亮从别的芯片移到了 confidence_up），
  //   却让判据去比一个**与芯片无关**的量。
  // ⇒ 改比**全文**，并额外要求高亮芯片真的换了人。
  // ⚠ 先确认有 ≥2 个芯片 —— 只有一个芯片时「点了没变」是**正确行为**，
  //   拿它当判据会得到一个永远红的判据。
  const NORM = `e => (e ? e.innerText : '').replace(/\\s+/g,' ').trim()`;
  const clicked = await page.eval(`(() => {
    const host = document.getElementById('extras');
    const norm = ${NORM};
    const chips = host.querySelectorAll('[data-cotdir]');
    if(chips.length < 2) return { n: chips.length, skip: true };
    const onBefore = [...chips].filter(c => c.className.includes('on'))
                                .map(c => c.getAttribute('data-cotdir'));
    const other = [...chips].find(c => !c.className.includes('on')) || chips[1];
    return { n: chips.length, skip: false, onBefore,
             target: other.getAttribute('data-cotdir'),
             fullBefore: norm(host.querySelector('[data-cotblock]')) };
  })()`);
  if (clicked.skip) {
    rec('W5 点方向芯片后思维链那块必须换内容（证明重绑生效，不是「看得到点了没反应」）',
        false, `只有 ${clicked.n} 个芯片 ⇒ 本数据上无法成立，不许当成产品缺陷`);
  } else {
    await page.eval(`(() => { const host = document.getElementById('extras');
      const t = [...host.querySelectorAll('[data-cotdir]')]
        .find(c => c.getAttribute('data-cotdir') === ${JSON.stringify(clicked.target)});
      if(t) t.click(); })()`);
    await sleep(1500);
    const after = await page.eval(`(() => {
      const host = document.getElementById('extras');
      const norm = ${NORM};
      const on = [...host.querySelectorAll('[data-cotdir]')]
        .filter(c => c.className.includes('on')).map(c => c.getAttribute('data-cotdir'));
      return { on, full: norm(host.querySelector('[data-cotblock]')) };
    })()`);
    const moved = JSON.stringify(clicked.onBefore) !== JSON.stringify(after.on);
    rec('W5 点方向芯片后思维链那块必须换内容（证明重绑生效，不是「看得到点了没反应」）',
        moved && after.full !== clicked.fullBefore,
        `${clicked.n} 个芯片；高亮 ${JSON.stringify(clicked.onBefore)} → `
        + `${JSON.stringify(after.on)}（点了 ${clicked.target}）；`
        + `正文全文 ${clicked.fullBefore.length} → ${after.full.length} 字，`
        + `内容${after.full === clicked.fullBefore ? '**没变**' : '已变'}`);
  }

  // W6：点题号芯片。同样比全文。
  const ar = await page.eval(`(() => {
    const host = document.getElementById('extras');
    const norm = ${NORM};
    const bs = host.querySelectorAll('[data-arpick]');
    if(bs.length < 2) return { n: bs.length, skip: true };
    const other = [...bs].find(b => !b.className.includes('on')) || bs[1];
    return { n: bs.length, skip: false, target: other.getAttribute('data-arpick'),
             fullBefore: norm(host.querySelector('[data-aroot]')) };
  })()`);
  if (ar.skip) {
    rec('W6 点题号芯片后答案那块必须换内容', false,
        `只有 ${ar.n} 个题号按钮 ⇒ 本数据上无法成立（不许当成产品缺陷）`);
  } else {
    await page.eval(`(() => { const host = document.getElementById('extras');
      const t = host.querySelector('[data-arpick="' + ${JSON.stringify(ar.target)} + '"]');
      if(t) t.click(); })()`);
    await sleep(1500);
    const arAfter = await page.eval(`(() => {
      const host = document.getElementById('extras');
      return { full: (${NORM})(host.querySelector('[data-aroot]')) };
    })()`);
    rec('W6 点题号芯片后答案那块必须换内容',
        arAfter.full !== ar.fullBefore,
        `${ar.n} 个题号按钮；点了第 ${ar.target} 题；`
        + `正文全文 ${ar.fullBefore.length} → ${arAfter.full.length} 字，`
        + `内容${arAfter.full === ar.fullBefore ? '**没变**' : '已变'}`);
  }

  // W7：DELTA 专属的四个跳转锚点**不该**出现在 #extras。
  // 它们是 drawDeltaSide() 自己 h += 的两行，不在 renderCotEffect() 里，
  // 所以 #extras 那份天然没有 —— 这条是把这个「有意不带」钉住，
  // 免得下一轮有人看到源码里有、DOM 里没有，又当成 bug 搬一遍。
  const jump = await page.eval(`(() => {
    const host = document.getElementById('extras');
    return ['data-jump','data-jumphint','data-cotjump','data-arjump']
      .filter(a => host.querySelector('[' + a + ']'));
  })()`);
  rec('W7 #extras 里不许出现 DELTA 专属的四个跳转锚点（它们只在 DELTA 视图里存在）',
      jump.length === 0,
      jump.length ? `#extras 里混进了：${jump.join(', ')}` : '四个都不在（与设计一致）');

  // W8：dv 块的题号标记必须在**有数据**的主路径上。
  // 它原来只在两个「没有数据」的早退分支上，等于「块坏了才打这个标记」。
  rec('W8 候选词读出块必须带 data-dvroot（表达「在讲第几题」，不是「这块坏了」）',
      !!(st && st.dvRoot === 1),
      st ? `data-dvroot ${st.dvRoot} 个` : '没读到');

  // W9：真的从 CDP 事件流里取 console error。
  // ⚠⚠ 第二十五笔：这一条原来只收 `Runtime.consoleAPICalled` 且 type==='error'，
  //   报出来是「console error 0 条」—— 而那一刻页面**是坏的**：
  //   我把 `const LASTL` 声明放在了第一次使用之后，TDZ 抛 ReferenceError，
  //   整块 #extras 静默消失（W0 那条 45.6 秒超时才抓到）。
  //   原因：页面有全局错误兜底，它把 render 里的异常接住之后**不往 console 写**，
  //   所以这一类异常根本不走 `consoleAPICalled`。
  // ⇒ 必须同时收 `Runtime.exceptionThrown`。
  //   一般形态：**「无异常」的判据要先问「异常会以什么形式出现」**；
  //   只监听一种通道，等于给另一种通道开了静默的口子。
  const errs = page.events
    .filter(e => (e.method === 'Runtime.consoleAPICalled' && e.params.type === 'error')
              || e.method === 'Runtime.exceptionThrown')
    .map(e => {
      if (e.method === 'Runtime.exceptionThrown') {
        const d = e.params.exceptionDetails || {};
        const ex = d.exception || {};
        return 'exceptionThrown: ' + (ex.description || ex.value || d.text || '?');
      }
      return (e.params.args || []).map(a => a.value ?? a.description ?? '').join(' ');
    })
    .filter(t => t && !/favicon|Failed to load resource/i.test(t));
  rec('W9 搬运过程中不得有 console error 或未捕获异常'
      + '（抛异常的 render 会让整块静默消失，而页面兜底不往 console 写）',
      errs.length === 0,
      `共收 ${page.events.length} 条 CDP 事件、其中 error/异常 ${errs.length} 条`
      + (errs.length ? '：' + errs.slice(0, 3).join(' | ') : ''));

  // ---- 源码侧：这三块的入口必须真的在 renderExtras 里 ----
  // 判据读哪一层要和它防的东西同层：W1–W9 都在**渲染层**，
  // 这一条在**源码层**，防的是「有人把 h += renderCotEffect() 删了，
  // 而浏览器里那块恰好还因为别的原因在」—— 那种情况上面几条会假绿。
  const src = readFileSync('/Users/zhourui/code/steer3d/frontend/public/latent/'
    + 'index.html', 'utf8');
  const exIdx = src.indexOf('function renderExtras');
  const exEnd = src.indexOf('function bindExtraEvents', exIdx);
  const exBody = src.slice(exIdx, exEnd > 0 ? exEnd : exIdx + 4000);
  // ⚠ 诊断行第一版用 `exBody.match(/.*renderCotEffect.*/)` 取第一处匹配，
  //   而第一处是我自己写的**注释**（「而 renderCotEffect() 只被 drawDeltaSide() 调用」），
  //   于是它印出来的是一句说明、判据却是过的 —— 诊断行与判据说的不是一回事。
  // ⇒ 只在**非注释行**里找。
  const realLine = exBody.split('\n')
    .map(l => l.trim())
    .filter(l => l.includes('renderCotEffect')
                 && !l.startsWith('//') && !l.startsWith('*') && !l.startsWith('/*'))
    .find(l => l.includes('h +=')) || '';
  rec('W10 renderExtras() 里必须真的调了 renderCotEffect（源码层，防「浏览器里恰好还在」）',
      /h \+= .*renderCotEffect\(\)/.test(realLine),
      realLine ? '找到调用行：' + realLine.slice(0, 90)
               : 'renderExtras() 里没有 h += renderCotEffect()（非注释行）');

  console.log('\n=== %d/%d passed ===', pass, total);
  process.exitCode = (pass === total) ? 0 : 1;
} catch (e) {
  console.log('[FAIL] W 组脚本崩了：%s\n%s', e.message, e.stack);
  process.exitCode = 1;
} finally {
  try { await cdp.send('Browser.close'); } catch {}
  try { proc.kill(); } catch {}
}

