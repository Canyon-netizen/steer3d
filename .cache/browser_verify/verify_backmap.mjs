// 验收：token 反向映射这一块在真实页面里。
//
// 判据要钉住的东西（都是这一轮真踩到的坑）：
//   1. 块真的渲染出来了，且**不是**被 catch 吞掉的空串。
//      页面有全局错误兜底，一个抛异常的 render 函数会让整块消失而页面照常。
//   2. 负面结果真的印在页面上：「零空间是空的」这件事如果不显示，
//      读者只会记住「我们把 token 映回去了」——那正是被推翻的说法。
//   3. 两种 regime 分开显示，且各带分母。合并成一个平均数会同时
//      稀释厚锥（2.20×）和夸大小锥的可移动性。
//   4. 实测网格的点数来自产物，不是插值出来的固定值。
//   5. 点了步按钮之后，网格必须真的换掉（DOM 判据不覆盖交互）。
import { launch, Page, CDP } from './cdp_client.mjs';

const URL = process.env.LAT_URL || 'http://127.0.0.1:8917/latent/index.html';
const PROFILE = process.env.LAT_PROFILE
  || '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_bm';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const R = [];

function rec(name, pass, detail) {
  R.push({ name, pass });
  console.log(`[${pass ? 'PASS' : 'FAIL'}] ${name}\n       ${detail}`);
}

const { proc, version } = await launch({
  port: 9411, userDataDir: PROFILE, windowSize: '1600,1000', url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);

try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  // 数据是 fetch 进来的，等它落地。这里等 block 出现，而不是等固定秒数——
  // 固定等待在慢机器上会假阴性，在快机器上白等。
  let waited = 0;
  let st = null;
  while (waited < 45000) {
    st = await page.eval(`(() => {
      const r = document.querySelector('[data-bmroot]');
      return r ? { has: true, len: r.innerHTML.length,
                   text: (r.innerText || '').slice(0, 4000) } : { has: false };
    })()`);
    if (st.has && st.len > 400) break;
    await sleep(1200);
    waited += 1200;
  }
  rec('B1 块渲染出来了（不是空串）', !!(st && st.has && st.len > 400),
      st && st.has ? `len=${st.len} waited=${waited}ms` : 'data-bmroot 不存在');

  const txt = (st && st.text) || '';

  /* ---------------------------------------------------- 负面结果必须显示 */
  rec('B2 页面上写了「零空间是空的」',
      /零空间/.test(txt) && /(空|不存在)/.test(txt),
      (txt.match(/.{0,40}零空间.{0,60}/) || ['<未找到>'])[0].replace(/\s+/g, ' '));

  rec('B3 印出了最小奇异值与条件数（可核对的数）',
      // 上一版只查 /4\.4/，而 4.4217 是 σ_min 的值：即使我把字段名写成
      // rk.condition（实际叫 rk.cond），σ_min 照样渲染出来，正则照样匹配，
      // 判据报 PASS 而页面上「条件数只有 —」。这里必须让条件数自己
      // 出现一个像样的数值（32.999… → 33.0），且秩的分母也必须在。
      /最小奇异值/.test(txt) && /条件数/.test(txt)
      && /最小奇异值\s*4\.42/.test(txt)
      && /条件数只有\s*3[0-9](\.[0-9])?/.test(txt)
      && /秩\s*2048\/2048/.test(txt),
      (txt.match(/最小奇异值[^。]{0,80}/) || ['<未找到>'])[0].replace(/\s+/g, ' '));

  /* ---------------------------------------------------- 两种 regime 分开 */
  const regimes = await page.eval(`(() => {
    const r = document.querySelector('[data-bmroot]');
    if(!r) return null;
    const rows = [...r.querySelectorAll('tr')].map(tr => tr.innerText.replace(/\\s+/g,' ').trim());
    return rows;
  })()`);
  const hasThick = regimes && regimes.some(r => /读出已指向该词/.test(r));
  const hasThin = regimes && regimes.some(r => /靠微调才指向该词/.test(r));
  rec('B4 厚锥/薄锥两行都在，且没有合并成一行平均',
      !!(hasThick && hasThin),
      (regimes || []).filter(r => /指向该词/.test(r)).join(' || ') || '<无>');

  rec('B5 两行都带分母（步数 + >1× 次数/总次数）',
      !!(hasThick && hasThin
         && /\d+\/\d+/.test(regimes.find(r => /读出已指向该词/.test(r)) || '')
         && /\d+\/\d+/.test(regimes.find(r => /靠微调才指向该词/.test(r)) || '')),
      (regimes || []).filter(r => /指向该词/.test(r)).join(' || '));

  /* ---------------------------------------------------- 实测网格 */
  const grid = await page.eval(`(() => {
    const r = document.querySelector('[data-bmroot]');
    if(!r) return null;
    const svg = r.querySelector('[data-bmgrid]');
    const n = r.querySelector('[data-bmgridn]');
    const rects = svg ? svg.querySelectorAll('rect').length : 0;
    return { hasSvg: !!svg, rects, declared: n ? n.textContent : null,
             w: svg ? svg.getBoundingClientRect().width : 0,
             h: svg ? svg.getBoundingClientRect().height : 0 };
  })()`);
  rec('B6 实测网格画出来了，且 rect 数 = 声明的采样点数',
      !!(grid && grid.hasSvg && grid.rects > 4
         && String(grid.rects) === String(grid.declared)),
      grid ? `rects=${grid.rects} declared=${grid.declared} size=${grid.w.toFixed(0)}x${grid.h.toFixed(0)}`
           : '无 svg');

  rec('B7 网格有实际像素高度（不是 0 高的隐形元素）',
      !!(grid && grid.h >= 30 && grid.w >= 150),
      grid ? `${grid.w.toFixed(0)}x${grid.h.toFixed(0)}` : '无');

  /* ---------------------------------------------------- 交互：点按钮要换图 */
  const before = await page.eval(`(() => {
    const s=document.querySelector('[data-bmgridn]');
    const r=document.querySelector('[data-bmroot]');
    return { n: s?s.textContent:null,
             step: (r.innerText.match(/第 (\\d+) 步/)||[])[1] || null };
  })()`);
  const clicked = await page.eval(`(() => {
    const bs=[...document.querySelectorAll('[data-bmstep]')];
    if(bs.length<2) return { n: bs.length };
    // 点一个黄区（需要 delta 的步），序号靠后
    bs[bs.length-1].click();
    return { n: bs.length, clicked: bs[bs.length-1].textContent };
  })()`);
  await sleep(1200);
  const after = await page.eval(`(() => {
    const s=document.querySelector('[data-bmgridn]');
    const r=document.querySelector('[data-bmroot]');
    // 读完整 innerText。上一版只取前 600 字符，而"并列"两个字落在
    // 步信息之后、网格之前 —— 600 字符窗口刚好把它切掉，判据于是
    // 报"页面没说并列"，实际页面说了。判据自己少读了字段，
    // 却报成产品缺陷。
    return { n: s?s.textContent:null,
             step: (r.innerText.match(/第 (\\d+) 步/)||[])[1] || null,
             txt: r.innerText };
  })()`);
  rec('B8 点步按钮后选中步真的变了',
      !!(before && after && after.step && before.step !== after.step),
      `before step=${before && before.step} -> after step=${after && after.step} (clicked ${clicked.clicked})`);

  /* ---------------------------------------------------- 边界必须如实说 */
  rec('B9 边界写明是「并列」而不是翻转',
      /并列/.test(after.txt || '') || /恰好为 0/.test(after.txt || ''),
      ((after.txt || '').match(/.{0,30}(并列|恰好为 0).{0,50}/) || ['<未找到>'])[0].replace(/\s+/g, ' '));

  rec('B10 说明了「词没变 ≠ logits 没变」',
      /logits 相对变化/.test(txt) || /读出没变/.test(txt),
      (txt.match(/.{0,25}logits 相对变化.{0,60}/) || ['<未找到>'])[0].replace(/\s+/g, ' '));

  /* ---------------------------------------------------- 无 console error */
  const errs = page.events
    .filter(e => e.method === 'Runtime.consoleAPICalled' && e.params.type === 'error')
    .map(e => (e.params.args || []).map(a => a.value ?? a.description ?? '').join(' '))
    .filter(t => !/favicon|Failed to load resource/i.test(t));
  rec('B11 页面无 console error', errs.length === 0,
      errs.length ? errs.slice(0, 2).join(' | ') : 'none');

  /* ---------------------------------------------------- 没有未替换的占位 */
  // 字段名写错时 nfmt(undefined) 返回 "—"，整块照常渲染、所有存在性
  // 判据都绿，只有数字是破折号。专门盯这个：任何「实测值」位置出现
  // —，都意味着取错了 key 而不是"这项没测到"。
  const dashes = await page.eval(`(() => {
    const r = document.querySelector('[data-bmroot]');
    if(!r) return null;
    const out = [];
    // 不按字符形态找破折号：innerText 会把 "——"（两个 U+2014）规范化成
    // "—" + 零宽字符，按正则区分"占位符"和"中文破折号"因此不可靠——
    // 上一版就是这么把 "0.20 倍——" 报成 nfmt 占位符的。
    //
    // 改成结构性判据：nfmt(undefined) 的输出是一个**孤立的 <b> 里只有破折号**，
    // 也就是"这一格该有数字却只有破折号"。真正的中文破折号在 </b> 之外。
    for(const b of r.querySelectorAll('b')){
      const t = (b.textContent || '').trim();
      if(t === '—' || t === '-' || t === '') out.push('<b>' + t + '</b> 紧邻：'
        + (b.previousSibling ? b.previousSibling.textContent.slice(-12) : '?'));
    }
    return out;
  })()`);
  rec('B12 实测值位置没有「—」（字段名取错会在这里露出来）',
      dashes !== null && dashes.length === 0,
      dashes && dashes.length ? dashes.join(' | ') : 'none');

  const shot = await page.screenshot(
    '/Users/zhourui/code/steer3d/.cache/browser_verify/shots/backmap.png',
    { fullPage: true });
  console.log('\nscreenshot ->', shot);
} catch (e) {
  rec('X 脚本自身没跑完', false, String(e && e.stack || e).slice(0, 300));
} finally {
  cdp.close(); proc.kill('SIGKILL');
}

const pass = R.filter(r => r.pass).length;
console.log(`\n=== ${pass}/${R.length} passed ===`);
R.filter(r => !r.pass).forEach(r => console.log(`FAIL: ${r.name}`));
process.exit(pass === R.length ? 0 : 1);
