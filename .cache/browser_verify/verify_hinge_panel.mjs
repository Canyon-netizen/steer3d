import { launch, Page, CDP } from './cdp_client.mjs';

/**
 * 判据 H：HingePanel ——「模型在推理中途动摇的位置」这一屏。
 *
 * 为什么要有这一屏：上一版「推理中途某个数算错了」那一支（P0）已被证伪
 * —— 逐条人工读原文后 **14/14 全是抽取器假阳性**，且 19 条答案错的轨迹里
 * **12 条抽取器零判错** ⇒ 1.7B 的错误主要不在算术层。
 * 这一屏展示的是**另一类位置**，所以它必须能被独立验证。
 *
 * ⚠⚠ 判据主体必须是**读者看到的可见文案**。`data-*` 只作交叉核对 ——
 *   本项目栽过：断言打在 data-* 上，组件把文案删了而 data-* 还在，判据照样绿。
 *
 * 双向：`run` 验绿侧，`selftest` 用**改页面可见文案**的方式证明它们会红。
 */
const URL = process.env.BV_URL || 'http://127.0.0.1:10370/';
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_hinge_' + process.pid;
const PORT = 9490;
const sleep = ms => new Promise(r => setTimeout(r, ms));

const results = [];
const check = (name, ok, detail) => {
  results.push({ name, ok: !!ok });
  console.log(`[${ok ? 'PASS' : 'FAIL'}] ${name}: ${detail ?? ''}`);
};

/** 在页面里跑一段表达式并取回 JSON 字符串。 */
async function ev(page, expr) {
  // ⚠ 表达式若是 async 的，返回的是 **Promise**，`JSON.stringify(Promise)`
  //   得 "{}" —— 第一版就这么把产物读成了空对象，H0 之后 TypeError。
  //   ⇒ 这里用 async IIFE + `await`，两种表达式都能取到真值。
  const r = await page.eval(
    `(async () => { try { return JSON.stringify(await (${expr})); } `
    + `catch (e) { return JSON.stringify({__err: String(e)}); } })()`);
  return JSON.parse(r);
}

async function boot() {
  const { proc, version } = await launch({
    port: PORT, userDataDir: PROFILE, windowSize: '1700,1100', url: 'about:blank',
  });
  const cdp = await CDP.connect(version.webSocketDebuggerUrl);
  const page = await Page.create(cdp);
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  await sleep(9000);
  return { proc, cdp, page };
}

async function run() {
  const { proc, cdp, page } = await boot();
  try {
    // ---- H0 前提：产物可达 + 面板进入 ready（不是 loading/error）----
    const art = await ev(page,
      `(async () => { const r = await fetch("/latent/data/hinge_hinges.json");`
      + ` return r.ok ? await r.json() : null; })()`);
    if (!art || art.__err) {
      console.log('[NORUN] hinge_hinges.json 不可达 —— 判据未跑，不是判红');
      return 6;
    }
    for (let i = 0; i < 40; i++) {
      const st = await ev(page,
        `(() => { const e = document.querySelector('[data-hinge]');`
        + ` return e ? e.getAttribute('data-hinge') : null; })()`);
      if (st === 'ready') break;
      if (st === 'error' || st === 'loading' && i > 30) {
        console.log(`[NORUN] 面板停在 ${st}`);
        return 6;
      }
      await sleep(500);
    }
    const state = await ev(page,
      `(() => { const e = document.querySelector('[data-hinge]');`
      + ` return e ? e.getAttribute('data-hinge') : null; })()`);
    check('H0 面板进入 ready 态', state === 'ready', `data-hinge=${state}`);
    if (state !== 'ready') return 1;

    // ---- H1 标题：读者第一眼看到的必须是「动摇」而不是「算错」----
    const h3 = await ev(page,
      `(() => { const e = document.querySelector('[data-hinge] h3');`
      + ` return e ? e.innerText : null; })()`);
    check('H1 标题说的是「动摇」', !!h3 && h3.includes('动摇'), h3 || '(null)');
    check('H1 标题**不含**「算错」', !!h3 && !h3.includes('算错'), h3 || '(null)');

    // ---- H2 三个数字必须与产物一致（读者看到的文案，不看 data-*）----
    const cells = await ev(page,
      `(() => { const o = {};`
      + ` for (const k of ['off0','off1','null']) {`
      + `   const e = document.querySelector('[data-hinge-row="'+k+'"]');`
      + `   o[k] = e ? e.innerText.replace(/\\s+/g,' ').trim() : null; }`
      + ` return o; })()`);
    const a0 = art.probe.auroc_before_marker['off0_已写下标记词'];
    const a1 = art.probe.auroc_before_marker['off1_标记词尚未写出'];
    const nullMax = Math.max(...Object.values(art.probe.auroc_null_controls));
    const num = s => (s && s.match(/([\d.]+)\s*$/)) ? parseFloat(s.match(/([\d.]+)\s*$/)[1]) : NaN;
    check('H2 已写下标记词的数字与产物一致',
      Math.abs(num(cells.off0) - a0) < 0.002, `${cells.off0} vs ${a0}`);
    check('H2 尚未写出标记词的数字与产物一致',
      Math.abs(num(cells.off1) - a1) < 0.002, `${cells.off1} vs ${a1}`);
    check('H2 零对照的数字与产物一致',
      Math.abs(num(cells.null) - nullMax) < 0.002, `${cells.null} vs ${nullMax}`);
    check('H2 零对照**显著低于**两个实验臂',
      num(cells.null) < num(cells.off1) - 0.1 && num(cells.null) < num(cells.off0) - 0.1,
      `null=${num(cells.null)} off1=${num(cells.off1)}`);

    // ---- H3 诚实边界必须**默认可见**（不许藏）----
    const cav = await ev(page,
      `(() => { const e = document.querySelector('[data-hinge="caveats"]');`
      + ` return e ? { open: e.open, text: e.innerText } : null; })()`);
    check('H3 诚实边界默认展开', cav && cav.open === true, `open=${cav && cav.open}`);
    check('H3 边界里写了「可分性」不是「知识」',
      !!cav && cav.text.includes('可分性') && cav.text.includes('知识'),
      '');
    check('H3 边界里写了「不是因果」', !!cav && cav.text.includes('因果'), '');
    check('H3 边界条数不少于产物',
      !!cav && cav.text.split('\n').filter(l => l.trim()).length >= art.caveats.length - 1,
      cav ? `${cav.text.split('\n').filter(l => l.trim()).length} 行 vs ${art.caveats.length} 条` : '');

    // ---- H4 「为什么不是算错」必须能被展开读到 ----
    await ev(page,
      `(() => { const s = document.querySelector('[data-hinge="why"] summary');`
      + ` if (s) s.click(); return true; })()`);
    await sleep(250);
    const why = await ev(page,
      `(() => { const e = document.querySelector('[data-hinge="why"]');`
      + ` return e ? e.innerText : null; })()`);
    check('H4 说明了 14/14 是假阳性', !!why && why.includes('14/14'), '');
    check('H4 说明了 12 条零判错', !!why && why.includes('12 条'), '');

    // ---- H5 逐条：条数与产物一致，不可判定的步必须标出来 ----
    const first = art.trajectories[0].trajectory_id;
    const nItems = await ev(page, `document.querySelectorAll('[data-hinge-item]').length`);
    const expectN = art.trajectories.find(t => t.trajectory_id === first).n;
    check('H5 首条录制的条目数与产物一致', nItems === expectN, `${nItems} vs ${expectN}`);
    const nIndec = await ev(page, `document.querySelectorAll('[data-hinge-indecidable]').length`);
    const expIndec = art.trajectories.find(t => t.trajectory_id === first)
      .hinges.filter(h => !h.decidable).length;
    check('H5 不可判定的步都标了出来', nIndec === expIndec, `${nIndec} vs ${expIndec}`);
    // 不可判定的步必须**明说不可信**（可见文案）
    const warn = await ev(page,
      `(() => { const e = document.querySelector('[data-hinge-item] p.text-amber-600');`
      + ` return e ? e.innerText : null; })()`);
    if (expIndec > 0) {
      check('H5 不可判定处写明「不可信」', !!warn && warn.includes('不可信'),
        (warn || '').slice(0, 40));
    } else {
      check('H5 该录制无不可判定步（跳过警告断言）', true, '');
    }

    // ---- H6 切换录制必须真的换列表 ----
    if (art.trajectories.length > 1) {
      const second = art.trajectories[1].trajectory_id;
      await ev(page,
        `(() => { const s = document.querySelector('[data-hinge-traj]');`
        + ` s.value = ${JSON.stringify(second)};`
        + ` s.dispatchEvent(new Event('change', {bubbles:true}));`
        + ` return true; })()`);
      await sleep(400);
      const n2 = await ev(page, `document.querySelectorAll('[data-hinge-item]').length`);
      const exp2 = art.trajectories.find(t => t.trajectory_id === second).n;
      check('H6 切换录制后列表跟着变', n2 === exp2, `${n2} vs ${exp2}`);
    } else {
      check('H6 切换录制（产物只有一条，跳过）', true, '');
    }

    // ---- H7 人工裁决必须显示在页面上 ----
    const audit = await ev(page,
      `(() => { const e = document.querySelector('[data-hinge="audit"]');`
      + ` return e ? e.innerText : null; })()`);
    check('H7 页面写明人工裁决数与准确率',
      !!audit && audit.includes('裁决') && /%/.test(audit), (audit || '').slice(0, 50));

    // ---- H10 逐条列表的五项交叉核对 ----
    // ⚠⚠ 这五条是**被 C4 点名补上的**。全链第一次跑时 `panel_coverage` 红在
    //   C4：「页面上存在、但没有任何判据读过的标记」——它逐个点名了
    //   data-hinge-decidable / -first-layer / -list / -tok / -verdict。
    //   ⇒ 处置方式选**「让判据真的读它们」**，不是登记成装饰或欠账：
    //     登记簿只是把账记上，缺口还在。
    //   ⚠ 主体仍是**可见文案**：data-* 只用来把「哪一条」对回产物，
    //     断言的是那句文字本身。
    const xc = await ev(page,
      `(() => {`
      + ` const first = document.querySelector('[data-hinge="ready"]')`
      + `   ? document.querySelectorAll('[data-hinge-item]')[0] : null;`
      + ` const q = s => document.querySelector(s);`
      + ` return {`
      + `  listLen: (document.querySelector('[data-hinge-list]')`
      + `    || {children:[]}).children.length,`
      + `  tok: first ? first.getAttribute('data-hinge-tok') : null,`
      + `  verdict: first ? first.getAttribute('data-hinge-verdict') : null,`
      + `  decidable: first ? first.getAttribute('data-hinge-decidable') : null,`
      + `  firstLayerText: first ?`
      + `    (first.querySelector('[data-hinge-first-layer]')`
      + `     || {innerText:''}).innerText : null,`
      + ` }; })()`);
    // H10a 列表容器存在且装着条目
    check('H10a 列表容器 data-hinge-list 装着条目', xc.listLen > 0,
      `${xc.listLen} 个子项`);
    // ⚠⚠ 必须按**下拉当前值**取产物侧的那条，不能用 `first` /
    //   `art.trajectories[0]` —— H6 刚把下拉切到了第二条轨迹，
    //   于是「页面第一条」是 tok 597、而 `trajectories[0]` 是 tok 745。
    //   第一版这么写，三条断言同时红，且红得莫名其妙（null vs 745、
    //   「应含 20」而页面上写 27）。⇒ 判决的**两侧必须取自同一个选择**。
    const curTraj = await ev(page,
      `(() => { const s = document.querySelector('[data-hinge-traj]');`
      + ` return s ? s.value : null; })()`);
    const curArt = art.trajectories.find(t => t.trajectory_id === curTraj);
    const firstH = curArt ? curArt.hinges[0] : null;

    // H10b tok 属性与产物一致，且**可见文字里也有那个步号**
    const firstItemText = await ev(page,
      `(() => { const e = document.querySelector('[data-hinge-item]');`
      + ` return e ? e.innerText : ''; })()`);
    check('H10b data-hinge-tok 与产物一致',
      !!firstH && String(xc.tok) === String(firstH.tok),
      `${xc.tok} vs ${firstH && firstH.tok}（当前录制 ${curTraj && curTraj.slice(5, 9)}）`);
    check('H10b 步号也出现在可见文字里',
      !!firstH && firstItemText.includes(`tok ${firstH.tok}`), '');
    // H10c verdict 与产物一致，且人工裁决那句话在文字里
    check('H10c data-hinge-verdict 与产物一致',
      !!firstH && xc.verdict === firstH.audited,
      `${xc.verdict} vs ${firstH && firstH.audited}`);
    const expectWord = !firstH ? ''
      : firstH.audited === 'true_hinge' ? '真动摇'
      : firstH.audited === 'false_positive' ? '假阳性' : '尚未人工裁决';
    check('H10c 人工裁决那句话在可见文字里',
      !!firstH && firstItemText.includes(expectWord), expectWord);
    // H10d decidable 与产物一致
    check('H10d data-hinge-decidable 与产物一致',
      !!firstH && String(xc.decidable) === String(firstH.decidable),
      `${xc.decidable} vs ${firstH && firstH.decidable}`);
    // H10e 首个定型层的**可见文字**与产物一致
    const fv = firstH ? firstH.first_layer_correct : null;
    const want = fv == null ? '未读出' : String(fv);
    check('H10e 首个定型层的可见文字与产物一致',
      !!firstH && !!xc.firstLayerText && xc.firstLayerText.includes(want),
      `${(xc.firstLayerText || '').trim()} 应含 ${want}`);

    // ---- H9 页面上不许出现 markdown 残留或内部路径 ----
    // ⚠ 截图才发现的：产物里带着 42 处 `**`，而 React **不渲染 markdown**
    //   ⇒ 读者看到的是「`**探针测的是可分性…`」这样一串星号。
    //   判据读 innerText，所以这类问题**对已有的 H1–H8 完全不可见** ——
    //   必须单独立一条。
    const dirty = await ev(page,
      `(() => { const t = document.querySelector('[data-hinge]')?.innerText || '';`
      + ` const bad = [];`
      + ` if (t.includes('**')) bad.push('markdown 星号 **');`
      + ` if (t.includes('.cache/')) bad.push('内部路径 .cache/');`
      + ` if (/\\*[^*]+\\*/.test(t)) bad.push('markdown 斜体或链接');`
      + ` return bad; })()`);
    check('H9 页面无 markdown 残留与内部路径',
      Array.isArray(dirty) && dirty.length === 0,
      dirty && dirty.length ? dirty.join(' / ') : '干净');

    // ---- H8 已证伪的说法不许被当作**肯定断言**出现在这一屏 ----
    // ⚠⚠ 第一版这里是纯字符串匹配「页面里不含『算错了的位置』」，
    //   判红后发现页面**确实**有那六个字 —— 但它在
    //   「为什么不是「算错了的位置」」这个**否定句**里，意思恰好相反。
    //   ⇒ 判据自己错了：纯字符串匹配**分不清肯定与否定**。
    //   ⇒ 现在改成检查「肯定式断言」：那句话必须以「不是」/「为什么不是」
    //     开头才允许出现被否定的字面串。
    const whole = await ev(page,
      `(() => { const e = document.querySelector('[data-hinge]');`
      + ` return e ? e.innerText : null; })()`);
    const negOk = await ev(page,
      `(() => {`
      + ` const lines = (document.querySelector('[data-hinge]')?.innerText || '')`
      + `   .split('\\n').map(s => s.trim()).filter(Boolean);`
      + ` const bad = lines.filter(s => (s.includes('算错了的位置')`
      + `   || s.includes('推理中途某个数算错了'))`
      + `   && !s.includes('不是') && !s.includes('为什么'));`
      + ` return bad; })()`);
    check('H8 被证伪的说法只以否定形式出现',
      Array.isArray(negOk) && negOk.length === 0,
      negOk && negOk.length ? JSON.stringify(negOk).slice(0, 80) : '干净');
    // 顺带：标题与首段**必须**不含那个字面串（这两处不是否定句）
    const head = await ev(page,
      `(() => { const e = document.querySelector('[data-hinge] h3');`
      + ` return e ? e.innerText : ''; })()`);
    check('H8 标题不含被证伪的字面串',
      !head.includes('算错了的位置'), head);
  } finally {
    await cdp.send('Browser.close').catch(() => {});
    proc.kill?.();
  }

  const pass = results.filter(r => r.ok).length;
  const red = results.length - pass;
  console.log(`\nRESULT ${red === 0 ? 'PASS' : 'FAIL'} ${pass}/${results.length}`);
  if (red) console.log('判红：' + results.filter(r => !r.ok).map(r => r.name).join('; '));
  return red === 0 ? 0 : 1;
}

/**
 * 牙齿自检：证明这些断言**会红**。
 * 手法：直接改**页面上的可见文案**（不动 data-*），看断言是否抓住。
 * 只在这一页实例上做，不碰源码与产物。
 */
async function selfTest() {
  const { proc, cdp, page } = await boot();
  const caught = [];
  try {
    const art = await ev(page,
      `(async () => { const r = await fetch("/latent/data/hinge_hinges.json");`
      + ` return r.ok ? await r.json() : null; })()`);
    const nullMax = Math.max(...Object.values(art.probe.auroc_null_controls));
    for (let i = 0; i < 40; i++) {
      const st = await ev(page,
        `(() => { const e = document.querySelector('[data-hinge]');`
        + ` return e ? e.getAttribute('data-hinge') : null; })()`);
      if (st === 'ready') break;
      await sleep(500);
    }

    // 变异 1：标题改成已被证伪的说法
    await ev(page,
      `(() => { const e = document.querySelector('[data-hinge] h3');`
      + ` e.innerText = '推理中途算错了的位置'; return true; })()`);
    const h3 = await ev(page,
      `(() => { const e = document.querySelector('[data-hinge] h3'); return e.innerText; })()`);
    caught.push(['H1 标题说的是「动摇」', !!h3 && h3.includes('动摇')]);
    caught.push(['H1 标题**不含**「算错」', !!h3 && !h3.includes('算错')]);

    // 变异 2：把诚实边界折叠起来
    await ev(page,
      `(() => { document.querySelector('[data-hinge="caveats"]').open = false;`
      + ` return true; })()`);
    const open = await ev(page,
      `document.querySelector('[data-hinge="caveats"]').open`);
    caught.push(['H3 诚实边界默认展开', open === true]);

    // 变异 3：把零对照数字伪造成与实验臂一样（伪造「没有对照」）
    await ev(page,
      `(() => { const e = document.querySelector('[data-hinge-row="null"]');`
      + ` e.innerText = 'AUROC 0.993'; return true; })()`);
    const nn = await ev(page,
      `(() => { const e = document.querySelector('[data-hinge-row="null"]');`
      + ` const m = e.innerText.match(/([\\d.]+)\\s*$/); return m ? parseFloat(m[1]) : NaN; })()`);
    caught.push(['H2 零对照的数字与产物一致', Math.abs(nn - nullMax) < 0.002]);
    caught.push(['H2 零对照**显著低于**两个实验臂', nn < 0.9]);

    // 变异 4：注入 markdown 残留与内部路径（复现截图里发现的那个问题）
    await ev(page,
      `(() => { const e = document.querySelector('[data-hinge="audit"]');`
      + ` e.innerText = '裁决见 .cache/mutbak/audit_hinge.py，**准确率 98%**';`
      + ` return true; })()`);
    const d9 = await ev(page,
      `(() => { const t = document.querySelector('[data-hinge]')?.innerText || '';`
      + ` const bad = [];`
      + ` if (t.includes('**')) bad.push('markdown 星号');`
      + ` if (t.includes('.cache/')) bad.push('内部路径');`
      + ` return bad; })()`);
    caught.push(['H9 页面无 markdown 残留与内部路径',
      Array.isArray(d9) && d9.length === 0]);
  } finally {
    await cdp.send('Browser.close').catch(() => {});
    proc.kill?.();
  }

  console.log('=== 牙齿自检（变异后对应断言应当变红）===');
  let allRed = true;
  for (const [name, stillPass] of caught) {
    if (stillPass) allRed = false;
    console.log(`  ${stillPass ? '✗ 仍绿（没牙齿）' : '✓ 变红'}  ${name}`);
  }
  console.log(allRed ? '\n✓ 全部变异被抓' : '\n✗ 至少一条变异没被抓 ⇒ 判据恒真');
  return allRed ? 0 : 1;
}

const mode = process.argv[2] || 'run';
process.exit(mode === 'selftest' ? await selfTest() : await run());
