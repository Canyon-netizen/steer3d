// 验收：候选词读出这一块（divergence_readout.json）在真实页面里。
//
// 为什么有这一组（§8.9 第二十三笔）：
//   第二十三笔做了一次「已发布产物的消费方普查」，发现
//   divergence_readout.json 是**只有页面读、没有任何判据读**的那两份之一。
//   ⇒ 另一只鞋：这一块渲染着，而它上面的数没有人核。
//
// 这一组要盯的东西：
//   1. 块真的渲染出来了。⚠ 这一块嵌在 drawDeltaSide() 里，需要一个被选中的
//      配对；而页面有全局错误兜底 —— 一个抛异常的 render 函数会让整块
//      **静默消失而页面照常**。所以「块不在」与「块崩了」要分开看。
//   2. 「同范数的 N 个随机方向」里的 N **不许是写死的**。
//      它原来是 JSX 里的字面量 128；改成读产物字段之后，
//      这一条就变成「页面上的 N = 产物里现算的 N」。
//   3. 层选择器的高亮真的是亮的。源码注释里记着一个修过的 bug：
//      `layers` 是字符串列表而 `final_layer` 是数字，
//      `x === S.dvLayer` 拿 "28" === 28 比，永不命中 ——
//      状态对了、而显示它的控件不对，读者看不出自己在看哪一层。
import { launch, Page, CDP } from './cdp_client.mjs';
import { readFileSync } from 'node:fs';

const URL = process.env.LAT_URL || 'http://127.0.0.1:22113/latent/index.html';
const DATA = '/Users/zhourui/code/steer3d/frontend/public/latent/data';
const PROFILE = process.env.LAT_PROFILE
  || '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_dv';

const sleep = ms => new Promise(r => setTimeout(r, ms));
const R = [];
function rec(name, pass, detail) {
  R.push({ name, pass });
  console.log(`[${pass ? 'PASS' : 'FAIL'}] ${name}\n       ${detail}`);
}

// ---- V0 可达性前置：连不上是装置事故，不是被测物判红 ----
let reach = null;
try {
  const resp = await fetch(URL, { method: 'GET' });
  reach = { ok: resp.ok, status: resp.status };
} catch (e) {
  reach = { ok: false, status: String(e && e.message || e) };
}
if (!reach.ok) {
  console.log('[FAIL] V0 页面不可达 ⇒ **装置事故，不是被测物判红**');
  console.log(`       URL = ${URL}  状态 = ${reach.status}`);
  console.log('       下面 6 条一条都没执行 ⇒ **不报 N/M**（报 0/6 会让「没跑」'
    + '看起来像「跑了而且全红」）。');
  console.log(`\n=== unreached (LAT_URL=${URL}) ===`);
  process.exit(4);
}
console.log(`[PASS] V0 页面可达\n       ${URL} → ${reach.status}`);
R.push({ name: 'V0 页面可达', pass: true });

const DV = JSON.parse(readFileSync(DATA + '/divergence_readout.json', 'utf8'));
const nProb = Object.keys(DV.problems || {}).length;

const { proc, version } = await launch({
  port: 9412, userDataDir: PROFILE, windowSize: '1600,1000', url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);

try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});

  // 等块出现，而不是等固定秒数：固定等待在慢机器上假阴性、快机器上白等。
  let waited = 0, st = null;
  while (waited < 45000) {
    st = await page.eval(`(() => {
      const r = document.querySelector('[data-dvblock]');
      if(!r) return { has: false };
      const g = s => { const e = document.querySelector(s);
                        return e ? (e.textContent || '').trim() : null; };
      const chips = [...r.querySelectorAll('[data-dvl]')].map(b => ({
        l: b.getAttribute('data-dvl'), on: b.className.indexOf('on') >= 0,
      }));
      return { has: true, len: r.innerHTML.length, chips,
               dirs: g('[data-dvdirs]'), hits: g('[data-dvhits]'),
               dlgat: g('[data-dvdlgat]'),
               text: (r.innerText || '').replace(/\\s+/g, ' ').slice(0, 600) };
    })()`);
    if (st.has && st.len > 300) break;
    await sleep(1200);
    waited += 1200;
  }
  rec('V1 候选词读出块渲染出来了（不是空串，也不是被兜底吞掉）',
      !!(st && st.has && st.len > 300),
      st && st.has ? `len=${st.len} waited=${waited}ms 层按钮 ${st.chips.length} 个`
                   : `等了 ${waited}ms 仍无 [data-dvblock]`
                     + '（要么数据没到，要么 render 抛了异常被全局兜底吃掉 —— '
                     + '两者要靠 V6 的 console 区分）');

  const pageSrc = readFileSync('/Users/zhourui/code/steer3d/frontend/public/latent/'
    + 'index.html', 'utf8');
  const hasLit = /同范数的 128 个随机方向/.test(pageSrc);
  // V2/V3 只核**已提交产物里就有的**字段（c4_random_hits 与 problems 的键）。
  //
  // ⚠ 为什么不要求 c4_random_dirs_per_problem：
  //   `frontend/public/latent/data/` 在 .gitignore 里，那三个新字段进不了提交
  //   ⇒ 页面若依赖它们，别人 checkout 之后会渲染成「undefined 个随机方向」。
  //   ⇒ 判据也不许依赖它们，否则它会为一版别人拿不到的数据背书。
  //   产物里那三个字段留作**额外**交叉核对（V4 同时验两路）。
  const hitM = /^\s*(\d+)\s*\/\s*(\d+)\s*$/.exec(String(DV.c4_random_hits || ''));
  rec('V2 「同范数的 N 个随机方向」由已提交的 c4_random_hits 现算，页面不许有字面量 128',
      st && st.dirs !== null && st.dirs !== undefined
      && hitM && nProb > 0 && Number(st.dirs) === Number(hitM[2]) / nProb
      && !/同范数的 128 个随机方向/.test(pageSrc),
      `页面印 ${st && st.dirs}；现算 c4_random_hits「${DV.c4_random_hits}」`
      + `分母 ${hitM && hitM[2]} ÷ 题数 ${nProb}`
      + `${hitM && nProb > 0 && Number(hitM[2]) % nProb === 0 ? '' : '（除不尽 ⇒ 页面不该印整数）'}`
      + `；页面源码含字面量「同范数的 128 个随机方向」=${hasLit}`
      + `（产物新字段 c4_random_dirs_per_problem=${DV.c4_random_dirs_per_problem}`
      + `在本地存在但未入库，所以判据不依赖它）`);

  rec('V3 命中率必须与产物同字符串，且分子/分母字段自洽',
      st && st.hits === DV.c4_random_hits && hitM
      && Number(hitM[1]) <= Number(hitM[2]),
      `页面「${st && st.hits}」= 产物 c4_random_hits「${DV.c4_random_hits}」；`
      + `拆开 ${hitM && hitM[1]}/${hitM && hitM[2]}`
      + (DV.c4_random_hits_n !== undefined
         ? `；产物新字段 ${DV.c4_random_hits_n}/${DV.c4_random_hits_denom}`
           + `与字符串一致=${DV.c4_random_hits_n === Number(hitM[1])
              && DV.c4_random_hits_denom === Number(hitM[2])}` : ''));

  // V4 核的是**推导本身**，且走两路互相对照：
  //   路 1：页面印的 N × 题数 = 从 c4_random_hits 字符串解析出的分母（已提交）
  //   路 2：产物新字段 c4_random_dirs_per_problem × 题数 = 同一分母（未提交，额外核对）
  rec('V4 印出的 N × 题数 = 分母，且与产物新字段一致（这个数是推出来的，必须能推回去）',
      st && nProb > 0 && hitM
      && Number(st.dirs) * nProb === Number(hitM[2])
      && (DV.c4_random_dirs_per_problem === undefined
          || DV.c4_random_dirs_per_problem * nProb === Number(hitM[2])),
      `页面 ${st && st.dirs} × ${nProb} 题 = `
      + `${st && Number(st.dirs) * nProb}，分母 = ${hitM && hitM[2]}；`
      + `产物新字段 ${DV.c4_random_dirs_per_problem} × ${nProb} = `
      + `${DV.c4_random_dirs_per_problem * nProb}`
      + `（两路互相对照；新字段未入库，所以它只是额外核对，不是前提）`);

  // V5 是这一组最该有的一条：源码注释里记着一个**修过的** bug，
  // 「状态对了而显示它的控件不对」—— 只核数据核不到它，必须核高亮。
  const sel = (st && st.chips || []).filter(c => c.on);
  const finL = String(DV.final_layer);
  rec('V5 层选择器：默认层必须真的高亮，且必须是产物声明的最终层',
      sel.length === 1 && sel[0].l === finL
      && (st.chips || []).some(c => c.l === finL),
      `高亮 ${JSON.stringify(sel)}；产物 final_layer=${finL}（${typeof DV.final_layer}）；`
      + `层列表 ${JSON.stringify((st.chips || []).map(c => c.l))}`
      + `（源码注释记着：layers 是字符串而 final_layer 是数字，`
      + `"${finL}" === ${finL} 恒为假 ⇒ 高亮永不触发）`);

  // V6 第一版是「块内没有破折号」，判红了 4 个。查下去是**判据错**：
  //   `innerText` 会把中文破折号「——」（两个 U+2014）规范化，字符形态上
  //   与 nfmt(undefined) 的占位「—」分不开 —— verify_backmap 的 B12 早就
  //   记过这个坑（它上一版就是被中文破折号误报的）。
  // ⇒ 改成**结构性**判据：占位符是「一个孤立的 <b> 里只有破折号」，
  //   真正的中文破折号在 </b> 之外。
  //   同时把「无 console 异常」真的查一遍 —— 上一版那条判据名里写了
  //   「无 console 级异常痕迹」但代码里根本没查，那是个**自己会显得成立**的名字。
  const errs = page.events
    .filter(e => e.method === 'Runtime.consoleAPICalled' && e.params.type === 'error')
    .map(e => (e.params.args || []).map(a => a.value ?? a.description ?? '').join(' '))
    .filter(t => !/favicon|Failed to load resource/i.test(t));
  const dashes = await page.eval(`(() => {
    const r = document.querySelector('[data-dvblock]');
    if(!r) return null;
    const out = [];
    for(const b of r.querySelectorAll('b')){
      const t = (b.textContent || '').trim();
      if(t === '—' || t === '-' || t === '') out.push(
        '<b>' + t + '</b> 紧邻：'
        + (b.previousSibling ? (b.previousSibling.textContent || '').slice(-14) : '?'));
    }
    return out;
  })()`);
  rec('V6 块内无 console error，且「实测值」位置没有占位破折号（结构性判据）',
      errs.length === 0 && dashes !== null && dashes.length === 0,
      `console error ${errs.length} 条${errs.length ? '：' + errs.slice(0, 2).join(' | ') : ''}；`
      + `孤立破折号 ${dashes === null ? '块不在' : dashes.length} 个`
      + `${dashes && dashes.length ? '：' + dashes.join(' | ') : ''}`
      + `（按字符形态数会把中文「——」数进来，所以只数 <b> 里只有破折号的）`);
} catch (e) {
  rec('V 脚本自身没跑完', false, String(e && e.stack || e).slice(0, 300));
} finally {
  cdp.close(); proc.kill('SIGKILL');
}

const pass = R.filter(r => r.pass).length;
console.log(`\n=== ${pass}/${R.length} passed ===`);
R.filter(r => !r.pass).forEach(r => console.log('FAIL: ' + r.name));
process.exit(pass === R.length ? 0 : 1);
