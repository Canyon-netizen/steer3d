// 验收：回放模式下 UI 只能选真实存在的轨迹。
//
// 这一轮发现的缺陷：ControlPanel 是个自由文本框，而回放 runner 拿 prompt
// 去匹配记录 id，匹配不上就回退到第 0 条。实测：
//
//     prompt='Why is the sky blue?'  -> ['We',' are',' given',' the']   ← 1983_I_1
//     prompt='1983_I_1'              -> 同一批 token
//
// 用户输入了一句不相干的话，页面上跑的是另一道题，而输入框仍显示着他那句。
// 看起来完全正常。判据要盯的是「UI 不允许构造出一个不存在的选择」。
import { launch, Page, CDP } from './cdp_client.mjs';

const BACKEND = process.env.T3D_PORT || '9500';
const URL = process.env.T3D_URL || 'http://127.0.0.1:9401/';
const PROFILE = process.env.T3D_PROFILE
  || '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_picker';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const R = [];
const rec = (n, p, d) => { R.push({ n, p }); console.log(`[${p ? 'PASS' : 'FAIL'}] ${n}\n       ${d}`); };

const { proc, version } = await launch({ port: 9425, userDataDir: PROFILE,
  windowSize: '1600,1000', url: 'about:blank' });
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);

try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  // 等 ready 落地：选择器要等 trajectories 到了才渲染。
  //
  // 等待条件必须是「**轨迹选择器**出现了」，不能是「有 select」。
  // 页面里本来就有层选择器和速度选择器，所以 `!!querySelector('select')`
  // 在 trajectories 到达之前就成立 —— 判据于是读到一个选项为空的
  // 选择器，报 E1/E2/E3 全红，而页面其实是对的。第一版就是这么误报的。
  let ok = false;
  for (let i = 0; i < 12; i++) {
    ok = await page.eval(`(() => {
      const s = [...document.querySelectorAll('select')].find(x =>
        [...x.options].some(o => /^aime__/.test(o.value)));
      return !!s;
    })()`);
    if (ok) break;
    await sleep(1200);
  }
  rec('E0 轨迹选择器已渲染（等待条件是它本身，不是「有 select」）', ok,
      ok ? 'ready 落地' : '等了 14s 仍未出现');

  /* ---------------------------------------------------------------- 1 */
  const ui = await page.eval(`(() => {
    const sels = [...document.querySelectorAll('select')];
    const rec = sels.find(s => [...s.options].some(o => /^aime__/.test(o.value)));
    return {
      selCount: sels.length,
      hasRecPicker: !!rec,
      options: rec ? rec.options.length : 0,
      values: rec ? [...rec.options].slice(0, 4).map(o => o.value) : [],
      textareas: document.querySelectorAll('textarea').length,
      labels: [...document.querySelectorAll('label')].map(l => l.textContent.trim()),
      bodyHasSky: /Why is the sky blue/.test(document.body.innerText || ''),
      saysReplaying: /Replaying a recorded/.test(document.body.innerText || ''),
    };
  })()`);

  rec('E1 页面有轨迹选择器（不是自由文本框）', ui.hasRecPicker,
      `selects=${ui.selCount} textareas=${ui.textareas} labels=${JSON.stringify(ui.labels)}`);
  rec('E2 选择器选项数 == 后端上报的轨迹数（48）', ui.options === 48, `options=${ui.options}`);
  rec('E3 选项值是真实记录 id', ui.values.length > 0 && ui.values.every(v => v.startsWith('aime__')),
      `sample=${JSON.stringify(ui.values)}`);
  rec('E4 「Why is the sky blue?」这个不存在的 prompt 不再出现在页面上',
      !ui.bodyHasSky, `bodyHasSky=${ui.bodyHasSky}`);
  rec('E5 页面说明这是回放而非生成', ui.saysReplaying, `saysReplaying=${ui.saysReplaying}`);

  /* ---------------------------------------------------------------- 6 */
  // 换一条轨迹，token 流必须真的变。
  const before = await page.eval(`(() => {
    const s=[...document.querySelectorAll('select')].find(s=>
      [...s.options].some(o=>/^aime__/.test(o.value)));
    return s ? s.value : null;
  })()`);
  const after = await page.eval(`(async () => {
    const s=[...document.querySelectorAll('select')].find(s=>
      [...s.options].some(o=>/^aime__/.test(o.value)));
    if(!s) return null;
    // 选一条 id 与当前不同的
    const opt=[...s.options].find(o=>o.value!==s.value && /__think$/.test(o.value));
    if(!opt) return null;
    s.value=opt.value;
    s.dispatchEvent(new Event('change',{bubbles:true}));
    return opt.value;
  })()`);
  await sleep(1200);
  rec('E6 换选项后选中的 id 真的变了', !!(before && after && before !== after),
      `${before} -> ${after}`);

  /* ---------------------------------------------------------------- 7 */
  // 从这里开始，判据不再问「有没有 token 在动」，而是问
  // **页面上显示的每一个 token，是不是都属于用户选的那条记录**。
  //
  // 上一版（E7b 看 N tokens 增长 + E9 在整页 grep '<think>'）是两条
  // 假绿，实测两条都抓不住把 prompt 换掉的变异：
  //
  //  1. `start` 不清 frames。store 的 ingestFrame 是追加，只有 reset
  //     才清（store.ts:90 / :123）。所以换记录后，页面上仍留着
  //     **上一条**记录的 token。E9 在整页 innerText 里 grep
  //     '<think>'，命中的是 E6 步骤就已经播出来的 think 记录的残留，
  //     不是它选的那条 —— 于是无论 Start 发的是哪个 id 都通过。
  //  2. 真正的信息在**逐字比对**：npz 里有每条记录的真实 token
  //     （token_ids，与 _Decoder.text 读的是同一个字段），比对它
  //     才谈得上"页面显示的是不是这条记录"。
  //
  // 所以顺序固定为：reset（清空）→ 选记录 → Start → 读前 N 个
  // token → 与 npz 真值逐字比对。
  //
  // 真值由 .cache/mutpick/dump_truth.py 从 npz 直读导出。它必须是
  // 独立来源：若判据自己也是从后端拿的，后端选错记录时两边一起错，
  // 判据恒绿。
  const TRUTH = JSON.parse(
    await (await import('node:fs/promises')).readFile(
      '/Users/zhourui/code/steer3d/.cache/mutpick/ground_tokens.json', 'utf8'));

  // 页面上当前显示的 token 列表。
  //
  // 必须**锚在 "Reasoning Trace" 这个标题上**，再取它所在行的
  // nextElementSibling —— 那才是 TokenStreamPanel 的滚动盒。
  //
  // 上一版写的是「找任意含 Reasoning Trace 文本且含 span 的 div，
  // 再找它里面第一个 className 带 overflow-y-auto 的 div」。错在
  // 两处：(1) querySelectorAll 返回文档序，祖先在子孙之前，所以
  // 第一个命中的是包住整个面板网格的大容器；(2) 于是
  // `[...大容器.querySelectorAll('div')].find(overflow-y-auto)` 抓到
  // 的是页面上更靠前的另一个可滚动面板（TopTokensPanel 也有
  // overflow-y-auto），它里面没有 span。读回来是空数组，E8/E9 于是
  // 报 "no tokens on page" —— 判据自己坏了，看起来像页面坏了。
  //
  // TokenStreamPanel 的结构（frontend/components/TokenStreamPanel.tsx）：
  //   div.panel
  //     div.row  <-- h2 "Reasoning Trace" + span "N tokens"
  //     div.box  <-- overflow-y-auto，每个 token 一个 span
  const pageTokens = () => page.eval(`(() => {
    const hdr = [...document.querySelectorAll('*')].find(e =>
      e.children.length === 0
      && (e.textContent || '').trim() === 'Reasoning Trace');
    if (!hdr || !hdr.parentElement) return null;
    const box = hdr.parentElement.nextElementSibling;
    if (!box) return null;
    return [...box.querySelectorAll('span')]
      .map(s => s.textContent || '')
      // frames 为空时盒子里是一个占位 span，不是 token
      .filter(t => !/awaiting first frame/.test(t));
  })()`);

  const nTok = () => page.eval(`(() => {
    const m = (document.body.innerText || '').match(/(\\d+)\\s*tokens/);
    return m ? parseInt(m[1], 10) : 0;
  })()`);

  const clickBtn = (re) => page.eval(`(() => {
    const b = [...document.querySelectorAll('button')]
      .find(x => ${re}.test(x.textContent || ''));
    if (!b) return false;
    b.click();
    return true;
  })()`);

  // 选一条记录并 Start，等到页面上 token 数稳定在 >= 4。
  // 返回 {id, toks} —— toks 是 reset 之后新流出来的那些。
  const playRecord = async (pickRe) => {
    const id = await page.eval(`(() => {
      const s = [...document.querySelectorAll('select')].find(x =>
        [...x.options].some(o => /^aime__/.test(o.value)));
      if (!s) return null;
      const opt = [...s.options].find(o => ${pickRe});
      if (!opt) return null;
      s.value = opt.value;
      s.dispatchEvent(new Event('change', { bubbles: true }));
      return opt.value;
    })()`);
    if (!id) return { id: null, toks: [] };
    // 先清空，否则读到的是上一条记录的 token —— 这一步就是
    // 上一版 E9 假绿的直接原因。
    await clickBtn('/reset/i');
    await sleep(1200);
    const afterReset = await pageTokens();
    await clickBtn('/start|play|run/i');
    let toks = [];
    for (let i = 0; i < 20; i++) {
      await sleep(1000);
      toks = await pageTokens();
      if (toks.length >= 4) break;
    }
    return { id, toks, residue: afterReset };
  };

  // 逐字比对：页面前 k 个 token 与 npz 真值的前 k 个必须完全相同。
  const matchTruth = (id, toks) => {
    const want = TRUTH[id] || [];
    const k = Math.min(toks.length, want.length, 6);
    if (k === 0) return { ok: false, why: 'no tokens on page' };
    const gotA = toks.slice(0, k).join('');
    const wantA = want.slice(0, k).join('');
    return { ok: gotA === wantA, k, gotA, wantA };
  };

  const r1 = await playRecord('/__no_think$/.test(o.value)');
  const m1 = r1.id ? matchTruth(r1.id, r1.toks) : { ok: false, why: 'no no_think option' };
  rec('E7 reset 之后页面上确实没有残留 token',
      (r1.residue || []).length === 0,
      `after reset the panel still had ${(r1.residue || []).length} token(s): ${JSON.stringify((r1.residue||[]).slice(0,4))}`);
  rec('E8 所选记录的 token 与 npz 真值逐字相同',
      m1.ok,
      m1.ok ? `id=${r1.id} k=${m1.k} ${JSON.stringify(m1.gotA.slice(0,60))}`
            : `id=${r1.id} want=${JSON.stringify(String(m1.wantA).slice(0,60))} got=${JSON.stringify(String(m1.gotA).slice(0,60))} (${m1.why||'mismatch'})`);

  /* ---------------------------------------------------------------- 9 */
  // 换一条记录，播的必须是新选的那条 —— 靠真值比对，不靠 '<think>'
  // 这种"页面上碰巧有过的字符串"。
  const r2 = await playRecord('/__think$/.test(o.value)');
  const m2 = r2.id ? matchTruth(r2.id, r2.toks) : { ok: false, why: 'no think option' };
  // 额外确认它和上一条不是同一条：两条真值首 token 必须不同，
  // 否则这条判据在"两条记录恰好一样"时会白送通过。
  const distinct = r1.id && r2.id && r1.id !== r2.id
    && (TRUTH[r1.id] || [])[0] !== (TRUTH[r2.id] || [])[0];
  rec('E9 换记录后播的是新选的那条（与 npz 真值逐字比对）',
      m2.ok && distinct,
      m2.ok ? `id=${r2.id} k=${m2.k} first=${JSON.stringify((m2.gotA||'').slice(0,30))} distinct=${distinct}`
            : `id=${r2.id} want=${JSON.stringify(String(m2.wantA).slice(0,60))} got=${JSON.stringify(String(m2.gotA).slice(0,60))} (${m2.why||'mismatch'}) distinct=${distinct}`);

  const nEnd = await nTok();
  rec('E10 页面在流动（N tokens 计数 > 0）', nEnd > 0, `n_tokens=${nEnd}`);

  const errs = page.events
    .filter(e => e.method === 'Runtime.consoleAPICalled' && e.params.type === 'error')
    .map(e => (e.params.args || []).map(a => a.value ?? a.description ?? '').join(' '))
    .filter(t => !/favicon|Failed to load resource/i.test(t));
  rec('E11 页面无 console error', errs.length === 0, errs.length ? errs.slice(0,2).join(' | ') : 'none');
} catch (e) {
  rec('X 脚本崩了', false, String(e && e.stack || e).slice(0, 250));
} finally {
  cdp.close(); proc.kill('SIGKILL');
}

const pass = R.filter(x => x.p).length;
console.log(`\n=== ${pass}/${R.length} passed ===`);
R.filter(x => !x.p).forEach(x => console.log(`FAIL: ${x.n}`));
process.exit(pass === R.length ? 0 : 1);
