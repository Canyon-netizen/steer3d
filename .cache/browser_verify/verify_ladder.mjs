// 判据：证据阶梯面板（EvidenceLadderPanel）。
//
// 这一块回答 goal 里那句「能不能提取出一套通用的可解释性理论」。
// 它危险的地方不是画错，而是**画得比事实乐观** ——
// 一个把 L5 画成「差一点就到了」的阶梯，比没有阶梯更坏。
//
// 所以判据盯三件事：
//  1. 每一级的状态标记与产物逐级一致（L1 done / L3 partial / L5 missing …）
//  2. 每一级印出来的数与产物逐字一致（不许写死）
//  3. 「不能回答」那半必须印出来，且 L5/L7 不许是 done
//
// 另外两条专门盯**跨产物漂移**：这个面板的数字来自 5 份产物，
// 如果其中一份变了而阶梯没跟着变，判据必须红。
import { launch, Page, CDP } from './cdp_client.mjs';
import { readFileSync } from 'node:fs';

const URL = process.env.T3D_URL || 'http://127.0.0.1:10100/';
const PROFILE = process.env.T3D_PROFILE
  || '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_ladder_' + process.pid;
const DATA = '/Users/zhourui/code/steer3d/frontend/public/latent/data';

const LAD = JSON.parse(readFileSync(DATA + '/evidence_ladder.json', 'utf8'));
const SUB = JSON.parse(readFileSync(DATA + '/readable_subspace.json', 'utf8'));
const HEL = JSON.parse(readFileSync(DATA + '/heldout_readability.json', 'utf8'));
const ARM = JSON.parse(readFileSync(DATA + '/arm_asymmetry.json', 'utf8'));
const COT = JSON.parse(readFileSync(DATA + '/cot_texts.json', 'utf8'));

const sleep = ms => new Promise(r => setTimeout(r, ms));
const R = [];
const rec = (n, p, d) => { R.push({ n, p }); console.log(`[${p ? 'PASS' : 'FAIL'}] ${n}\n       ${d}`); };

const { proc, version } = await launch({ port: 9533, userDataDir: PROFILE,
  windowSize: '1600,1200', url: 'about:blank' });
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);

try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});

  let st = null;
  for (let i = 0; i < 18; i++) {
    st = await page.eval(`(() => {
      const el = document.querySelector('[data-ladder]');
      if (!el) return { missing: true };
      return {
        state: el.getAttribute('data-ladder'),
        maxLevel: el.getAttribute('data-max-level'),
        selfcheck: el.getAttribute('data-selfcheck'),
        nRungs: el.getAttribute('data-rungs'),
        text: (el.innerText || '').replace(/\\s+/g, ' '),
        overreach: (() => { const o = el.querySelector('[data-overreach]');
          return o ? (o.innerText||'').replace(/\\s+/g,' ') : null; })(),
        answerable: (() => { const o = el.querySelector('[data-answerable]');
          return o ? (o.innerText||'').replace(/\\s+/g,' ') : null; })(),
        notAnswerable: (() => { const o = el.querySelector('[data-not-answerable]');
          return o ? (o.innerText||'').replace(/\\s+/g,' ') : null; })(),
        rungs: [...el.querySelectorAll('[data-rung]')].map(d => ({
          level: d.getAttribute('data-rung'),
          state: d.getAttribute('data-rung-state'),
          mark: (d.querySelector('[data-rung-mark]')||{}).textContent || '',
          text: (d.innerText||'').replace(/\\s+/g, ' '),
        })),
      };
    })()`);
    if (st && st.state === 'ready') break;
    await sleep(1200);
  }

  rec('L0 面板已加载且为 ready', st && st.state === 'ready',
      st ? `state=${st.state}` : '元素不存在');
  if (!st || st.state !== 'ready') throw new Error('面板没 ready，后续判据不跑');

  rec('L1 八级都在，构建自检标记为 true，最高只到 L4',
      st.nRungs === '8' && LAD.ladder.length === 8
      && st.selfcheck === 'true' && LAD.selfcheck_passed === true
      && st.maxLevel === 'L4' && LAD.max_level_reached === 'L4',
      `页面 ${st.nRungs} 级 / selfcheck=${st.selfcheck} / max=${st.maxLevel} | `
      + `产物 ${LAD.ladder.length} 级 / selfcheck=${LAD.selfcheck_passed} / max=${LAD.max_level_reached}`);

  // 「画圆」的**摘要入口**。data-max-level 直接决定读者对整张表的印象，
  // 把它写死成 L6 就是最典型的越级（项目其实一行都没走到 L5）。
  const firstDoneAbove = st.rungs
    .filter(x => ['L5', 'L6', 'L7'].includes(x.level) && x.state === 'done')
    .map(x => x.level);
  rec('L1b 摘要与逐级标记都不得把 L5 及以上说成已走到',
      st.maxLevel === 'L4' && firstDoneAbove.length === 0,
      `页面 max=${st.maxLevel}，L5+ 里标成 done 的：${firstDoneAbove.join(',') || '无'}`);

  // 逐级：状态标记 + 印出来的数，都必须与产物一致
  rec('L2 八级的状态标记与产物逐级一致',
      LAD.ladder.every(a => {
        const r = st.rungs.find(x => x.level === a.level);
        return r && r.state === a.state;
      }),
      st.rungs.map(r => `${r.level}:${r.state}`).join(' ')
      + ' | 产物 ' + LAD.ladder.map(a => `${a.level}:${a.state}`).join(' '));

  // ⚠ detail 里的正则写在**外层** JS 里，不是 eval 的模板字符串里 ——
  //   所以要写 `\s` 不是 `\\s`。第一版写成 `\\s`（字面反斜杠），
  //   结果 detail 恒印「?」：断言照样绿，但**判红时看不到任何线索**，
  //   那和装饰没区别。判据的 detail 必须真的能读。
  rec('L3 每一级印出来的数与产物逐字一致（不许写死）',
      LAD.ladder.every(a => {
        const r = st.rungs.find(x => x.level === a.level);
        return r && a.here && r.text.includes(a.here);
      }),
      st.rungs.map(r => {
        const m = r.text.match(/本项目：\s*(\S+)/);
        return `${r.level}→「${m ? m[1] : 'REGEX没匹配上'}」`;
      }).join(' '));

  // ⚠ 最关键：L5 / L7 绝不能被画成 done。
  //    阶梯的价值在留白；把它画圆就是在推销一个不存在的结论。
  //    「画圆」有**两个入口**：摘要行（data-max-level）和单行标记。
  //    下面 L1 堵摘要入口，这里堵单行入口 —— 两边都要有变异。
  const l5 = LAD.ladder.find(x => x.level === 'L5');
  const l7 = LAD.ladder.find(x => x.level === 'L7');
  const r5 = st.rungs.find(x => x.level === 'L5');
  const r7 = st.rungs.find(x => x.level === 'L7');
  rec('L4 L5 与 L7 必须是「没有」：状态、标记、**文字**三样都要对',
      l5.state === 'missing' && l7.state === 'missing'
      && r5.state === 'missing' && r7.state === 'missing'
      && r5.mark.trim().startsWith('—') && r7.mark.trim().startsWith('—')
      // ⚠ 只查状态和破折号不够：把 STATE_TXT.missing 从「没有」改成「有」
      //   不会动 data-rung-state，也不动 MARK —— 那样这一条会照样绿，
      //   而页面上明明已经把「没有」印成了「有」。**文字也要查。**
      && r5.text.includes('没有') && r7.text.includes('没有')
      && !r5.text.includes('有  ') && !/✓/.test(r5.text),
      `产物 L5=${l5.state} L7=${l7.state} | 页面 L5=${r5 && r5.state}「${r5 && r5.mark.trim()}」 `
      + `L7=${r7 && r7.state}「${r7 && r7.mark.trim()}」`);

  // ---- 跨产物漂移：阶梯上的 L2/L4/L6 必须等于各自产物的当前值 ----
  rec('L5 L2 的条数等于 readable_subspace.json 的当前下界',
      String(SUB.headline.readable_directions_lower_bound) === '14'
      && r2text(st).includes(String(SUB.headline.readable_directions_lower_bound)),
      `产物 ${SUB.headline.readable_directions_lower_bound} | 页面「${r2text(st)}」`);

  rec('L6 L4 的 82× 地板比值由 heldout_readability.json 现算得出',
      (() => {
        const ratio = HEL.recipe.loo_rho / Math.abs(HEL.recipe.loo_floor);
        return Math.abs(ratio - 82) < 1 && r4text(st).includes('82×');
      })(),
      `产物现算 ${(HEL.recipe.loo_rho / Math.abs(HEL.recipe.loo_floor)).toFixed(1)}× | `
      + `页面「${r4text(st)}」`);

  rec('L7 L6 的 run 数与配对题数等于 cot/arm_asymmetry 的当前值',
      r6text(st).includes(String(COT.n_runs))
      && r6text(st).includes(String(ARM.n_pairs)),
      `产物 runs=${COT.n_runs} pairs=${ARM.n_pairs} | 页面「${r6text(st)}」`);

  rec('L8 最常见的越级必须印出，且把「未测」与「实测为 0」分开',
      !!st.overreach
      && st.overreach.includes(String(LAD.overreach_numbers.readable_directions))
      && st.overreach.includes(String(LAD.overreach_numbers.usable_axes))
      && /未测/.test(st.overreach),
      String(st.overreach).slice(0, 170));

  rec('L9 「能回答 / 不能回答」两半都印出，且不能回答里含 L5 以上',
      !!st.answerable && !!st.notAnswerable
      && /能回答/.test(st.answerable) && /不能回答/.test(st.notAnswerable)
      && /L5/.test(st.notAnswerable),
      `能: ${String(st.answerable).slice(0, 70)} || 不能: ${String(st.notAnswerable).slice(0, 70)}`);

  // ---------- L12 「有数据」与「能声称」必须分开印，且必须是**那句话** ----------
  // ⚠ L9 只查了「能回答 / 不能回答 / L5」三个关键词，**恰恰漏掉 L6 那一句** ——
  //   而那一句是页面上唯一说明「L6 有数据但不能声称」的地方。
  //   删掉它或改个措辞，读者就看不出 L4(能声称) 与 L6(有数据) 的区别，
  //   而 L6 在阶梯上仍是 partial、还印着 92 个 run ⇒ 极容易被读成「我们到 L6 了」。
  //   这正是本项目吃过一次的亏（产物 bug #11）：
  //   「最高有数据」与「最高能声称」混成一个数，就会写出「L5 及以上一行都没有」
  //   这种自相矛盾的话。
  // ⇒ 判据主体是**那句渲染文本**本身，且必须与产物逐字对得上。
  const naList = Array.isArray(LAD.not_answerable) ? LAD.not_answerable
                                                    : [String(LAD.not_answerable)];
  const l6line = naList.find(s => /L6/.test(s)) || '';
  const need = [
    ['L6 有数据', /L6/.test(l6line)],
    ['说清「有数据」', /有数据/.test(l6line)],
    ['点名缺随机臂', /随机(方向)?臂/.test(l6line)],
    ['区分「改变了」与「特有地改变了」',
     /只能声称.*改变了/.test(l6line) && /特有地/.test(l6line)],
  ];
  const naMiss = need.filter(([, ok]) => !ok).map(([w]) => w);
  rec('L12 「有数据」与「能声称」必须分开印，且 L6 那句必须逐字在页面上',
      !!l6line && naMiss.length === 0 && st.notAnswerable.includes(l6line),
      naMiss.length ? '产物 L6 句缺：' + naMiss.join('、')
        : (st.notAnswerable.includes(l6line)
            ? '逐字命中'
            : '⚠ 产物里有这句，但页面上**没有**（属性与状态都照旧，读者会误读成 L6）')
        + `　L6 句：${l6line.slice(0, 96)}`);

  // 可见性：阶梯是竖排块，但每一行内不能被裁
  const vis = await page.eval(`(() => {
    const el = document.querySelector('[data-ladder]');
    const rs = [...el.querySelectorAll('[data-rung]')];
    return JSON.stringify({
      rowOver: Math.max(0, ...rs.map(d => d.scrollWidth - d.clientWidth)),
      panelOver: el.scrollWidth - el.clientWidth,
      h: el.getBoundingClientRect().height,
    });
  })()`);
  const V = JSON.parse(vis);
  rec('L10 阶梯块不横向溢出（每一级都不被裁）', V.rowOver <= 1 && V.panelOver <= 1,
      `行溢 ${V.rowOver} / 块溢 ${V.panelOver} / 高 ${Math.round(V.h)}px`);

  const errs = page.events
    .filter(e => e.method === 'Runtime.consoleAPICalled' && e.params.type === 'error')
    .map(e => (e.params.args || []).map(a => a.value ?? a.description ?? '').join(' '))
    .filter(t => !/favicon|Failed to load resource/i.test(t));
  rec('L11 页面无 console error', errs.length === 0,
      errs.length ? errs.slice(0, 2).join(' | ') : 'none');
} catch (e) {
  rec('X 脚本崩了', false, String((e && e.stack) || e).slice(0, 300));
} finally {
  cdp.close(); proc.kill('SIGKILL');
}

function r2text(st) { const r = st.rungs.find(x => x.level === 'L2'); return r ? r.text : ''; }
function r4text(st) { const r = st.rungs.find(x => x.level === 'L4'); return r ? r.text : ''; }
function r6text(st) { const r = st.rungs.find(x => x.level === 'L6'); return r ? r.text : ''; }

const pass = R.filter(x => x.p).length;
console.log(`\n=== ${pass}/${R.length} passed ===`);
R.filter(x => !x.p).forEach(x => console.log('FAIL: ' + x.n));
process.exit(pass === R.length ? 0 : 1);
