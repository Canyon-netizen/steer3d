// Does the page actually answer "why this token and not that one"?
//
// Before this panel the divergence point on screen 4 was two bare labels
// ("control said X, steered said Y"). That answers "what changed". The data to
// answer "why" already existed (analyse_divergence_logits.py +
// analyse_common_prefix.py) and was never shipped, so it lived only in
// docs/INTERPRETABILITY.md.
//
// The check is therefore not "is the panel present". It is: for every problem
// of both models, does the *rendered* candidate list, the margin sentence and
// the emitted-token markers agree, token for token and number for number, with
// the shipped JSON. A panel that renders plausible-looking candidates from the
// wrong run passes every "does it look right" test.
//
// Three negative controls, because a check that cannot go red proves nothing:
//   N1  layer chips have teeth -- L4 must render L4's logits, not L28's. A page
//       that ignored the selection and always drew the final layer would still
//       pass a presence check.
//   N2  cross-model -- 0.6B's panel must not contain 1.7B's tokens. Both models
//       reuse problem ids 1983..1988, so an id-keyed mistake is invisible in the
//       ids and only shows in the words.
//   N3  the readout is wired to the *displayed* pair: switching the problem
//       selector must change the panel. A panel frozen on problem 1 under
//       problem 5's title is the stale-panel failure mode already paid for
//       three times in this page.
import { launch, CDP, Page } from '../browser_verify/cdp_client.mjs';
import { readFileSync, mkdirSync } from 'node:fs';

const URL = 'http://localhost:8917/latent/index.html';
const ROOT = '/Users/zhourui/code/steer3d';
const SHOTS = ROOT + '/.cache/divergence_shots';
const sleep = ms => new Promise(r => setTimeout(r, ms));
mkdirSync(SHOTS, { recursive: true });

const fails = [];
const chk = (c, label, extra = '') => {
  console.log((c ? '  ok   ' : '  FAIL ') + label + (extra ? '   ' + extra : ''));
  if (!c) fails.push(label);
};

const reg = await (await fetch('http://localhost:8917/latent/models.json')).json();
const reads = {};
for (const m of reg.models) {
  reads[m.id] = {
    meta: await (await fetch(`http://localhost:8917/latent/${m.base}divergence_readout.json`)).json(),
    vocab: (await (await fetch(`http://localhost:8917/latent/${m.base}vocab.json`)).json()).ids,
    pairs: (await (await fetch(`http://localhost:8917/latent/${m.base}pairs/pairs.json`)).json()).pairs,
  };
}
const txt = (vocab, id) => vocab[id] != null ? vocab[id] : '#' + id;

// What the page should be showing, derived independently from the shipped data
// rather than by re-running the page's own formatting code.
const NCAND = 5;   // matches the panel; the JSON ships 8
function expect(model, pid, layer) {
  const R = reads[model], q = R.meta.problems[pid], L = q.layers[String(layer)];
  const rows = arm => L[arm].slice(0, NCAND).map(t => ({ text: txt(R.vocab, t.i), g: t.g }));
  return {
    k: q.k,
    cEmitted: txt(R.vocab, q.c_id),
    sEmitted: txt(R.vocab, q.s_id),
    c: rows('c'), s: rows('s'),
    kl: L.kl,
    margin: (L.c[0].g - L.c[1].g).toFixed(2),
    marginS: (L.s[0].g - L.s[1].g).toFixed(2),
    nCand: NCAND,
    nMargin: q.margin.length,
  };
}

const { proc, version } = await launch({
  port: 9354,
  userDataDir: ROOT + '/.cache/divergence_shots/profile',
  url: 'about:blank',
});
const cdp = await CDP.connect(
  `ws://127.0.0.1:9354/devtools/browser/${version.webSocketDebuggerUrl.split('/').pop()}`);
const page = await Page.create(cdp);
const exceptions = [];
cdp.on(m => {
  if (m.method === 'Runtime.exceptionThrown') {
    exceptions.push(m.params.exceptionDetails?.exception?.description
                    || m.params.exceptionDetails?.text || 'unknown');
  }
});
await page.send('Emulation.setDeviceMetricsOverride',
  { width: 1600, height: 1000, deviceScaleFactor: 1, mobile: false });

// Read the rendered panel straight out of the DOM: every candidate row is
// [rank, token, logit], plus the margin sentence and the caveat text.
const READ = `(() => {
  const b = document.querySelector('[data-dvblock]');
  if (!b) return null;
  const rows = [];
  b.querySelectorAll('div[style*="flex"]').forEach(div => {
    const sp = div.querySelectorAll(':scope > span');
    if (sp.length < 4) return;
    rows.push({ n: sp[0].textContent.trim(), tok: sp[2].textContent.replace(/\\s*←$/, ''),
                emitted: /←/.test(sp[2].textContent), g: sp[3].textContent.trim() });
  });
  return {
    text: b.innerText,
    chips: [...b.querySelectorAll('[data-dvl]')].map(x => ({
      L: x.dataset.dvl, on: x.className.includes('on'), txt: x.textContent.trim() })),
    rows,
  };
})()`;

for (const m of reg.models) {
  console.log(`\n===== ${m.label} (d=${m.d_model}) =====`);
  const R = reads[m.id];
  const finalL = R.meta.final_layer;

  await page.send('Page.navigate', { url: `${URL}?orient=reset&m=${m.id}` });
  await page.waitForEvent('Page.loadEventFired', 40000);
  await sleep(6500);
  // The orientation layer is display:flex over the whole page, so a click on
  // #tabDelta lands on the overlay and nothing happens -- the page looks fine
  // and the check reads zero. Dismiss it the way a reader does first.
  if (await page.eval(
      `(()=>{const o=document.getElementById('orientation');
        return !!(o && getComputedStyle(o).display!=='none');})()`)) {
    await page.click('#orientClose');
    await sleep(900);
  }
  await page.click('#tabDelta');
  await sleep(2500);

  const npair = R.pairs.length;
  chk(npair > 0, `${npair} 个配对题目`);
  chk(Object.keys(R.meta.problems).length === npair,
      '读出数据覆盖全部配对题目',
      `${Object.keys(R.meta.problems).length}/${npair}`);

  const ownChips = [];
  const other = reg.models.find(x => x.id !== m.id);
  // N2, done so it can actually go red.
  //
  // The first version of this check collected every token from the other model
  // and asserted none appeared. That is invalid by construction: both models
  // answer the same six maths problems, so their top-8 lists legitimately
  // overlap (measured: 1984 shares 6/8, 1988 shares 7/8, and ordinary words
  // like "the" / "when" / "multiplied" belong to both). It fired on correct
  // pages, which is worse than having no check.
  //
  // The signal that does separate the runs is the *score*. For every problem
  // and both models the top-1 logits differ (e.g. 1984: 45.505 vs 33.027), and
  // for 4 of 6 even the token id differs. So: the rendered score list must be
  // this model's, and must not be the other model's. Token-based exclusion is
  // kept only for tokens the other model has and this one does not -- and the
  // run reports how many problems that left with any power, instead of
  // pretending a vacuous check is a pass.
  let nPowerful = 0, nVacuous = 0;

  for (let i = 0; i < npair; i++) {
    const pid = R.pairs[i].id;
    if (i > 0) {
      await page.eval(`(()=>{const s=document.getElementById('selPair');s.value='${i}';
        s.dispatchEvent(new Event('change'));return s.value;})()`);
      await sleep(1600);
    }
    const want = expect(m.id, pid, finalL);
    const got = await page.eval(READ);

    if (!got) { chk(false, `${pid} 读出面板存在`); continue; }
    chk(got.rows.length === want.c.length * 2,
        `${pid} 渲染了 ${want.c.length * 2} 行候选词`, String(got.rows.length));
    chk(got.chips.length === R.meta.layers.length,
        `${pid} 层按钮 ${R.meta.layers.length} 个`,
        got.chips.map(c => c.L).join('/'));

    const cRows = got.rows.slice(0, want.c.length);
    const sRows = got.rows.slice(want.c.length);
    const same = (a, b) => a.length === b.length
      && a.every((r, j) => r.tok === b[j].text && r.g === b[j].g.toFixed(2));
    chk(same(cRows, want.c), `${pid} 对照臂候选词逐行逐分一致`);
    chk(same(sRows, want.s), `${pid} 干预臂候选词逐行逐分一致`);

    const cMark = cRows.filter(r => r.emitted).map(r => r.tok);
    const sMark = sRows.filter(r => r.emitted).map(r => r.tok);
    chk(cMark.length === 1 && cMark[0] === want.cEmitted,
        `${pid} 对照臂标出的就是它吐出的词`, JSON.stringify(cMark));
    chk(sMark.length === 1 && sMark[0] === want.sEmitted,
        `${pid} 干预臂标出的就是它吐出的词`, JSON.stringify(sMark));

    chk(got.text.includes(`第 ${want.k} 步`), `${pid} 写明分叉步 = ${want.k}`);
    chk(got.text.includes(want.margin), `${pid} 对照臂领先 ${want.margin} 分出现在面板上`);
    chk(got.text.includes(want.marginS), `${pid} 干预臂领先 ${want.marginS} 分出现在面板上`);
    ownChips.push(...got.chips.map(c => c.txt));

    if (other) {
      const RO = reads[other.id];
      const oq = RO.meta.problems[pid];
      const oL = oq && oq.layers[String(finalL)];
      if (oL) {
        const mine = want.c.map(x => x.g.toFixed(2)).join(',');
        // Same slice on both sides. Comparing this model's top-5 against the
        // other's top-8 makes the two strings differ by length no matter which
        // model is showing, so the check passes on a swapped bundle -- it was
        // 12 failures before NCAND was introduced and 0 after, which is the
        // signature of a check that quietly stopped being able to fail.
        const theirs = oL.c.slice(0, NCAND).map(t => t.g.toFixed(2)).join(',');
        chk(mine !== theirs,
            `${pid} 分数不是 ${other.label} 的（同题同层）`,
            `${mine.slice(0, 22)} vs ${theirs.slice(0, 22)}`);
        // Tokens the other model ranks and this one does not.
        // Compare against the rendered *rows*, not against the block's innerText:
        // a substring test flags "when" inside the rendered token " when", which
        // is this model's own emitted word. Space-sensitive BPE tokens cannot
        // be searched with `includes`.
        const renderedToks = new Set(got.rows.map(r => r.tok));
        const mineIds = new Set(want.c.map(x => x.text).concat(want.s.map(x => x.text)));
        const exclusive = [...new Set([...oL.c, ...oL.s].map(t => txt(RO.vocab, t.i)))]
          .filter(w => w.length > 2 && !mineIds.has(w));
        const hit = exclusive.filter(w => renderedToks.has(w));
        if (exclusive.length) {
          nPowerful++;
          chk(hit.length === 0, `${pid} 没出现 ${other.label} 独有的 ${exclusive.length} 个词`,
              hit.slice(0, 3).join(' '));
        } else {
          nVacuous++;
          console.log(`  note ${pid}: 与 ${other.label} 词表完全重合，本题的词级检查无判别力`);
        }
      }
    }
  }
  if (other) console.log(`  负控 N2 统计：有判别力 ${nPowerful} 题 / 空转 ${nVacuous} 题`);

  // ---- N1: the layer chips actually change what is drawn ----
  console.log(`  -- ${m.label} 负控 N1：层切换`);
  await page.eval(`(()=>{const s=document.getElementById('selPair');s.value='0';
    s.dispatchEvent(new Event('change'));return s.value;})()`);
  await sleep(1500);
  const at = async L => {
    await page.eval(`(()=>{const b=document.querySelector('[data-dvblock]');
      const c=b.querySelector('[data-dvl="${L}"]'); if(c) c.click(); return !!c;})()`);
    await sleep(900);
    return page.eval(READ);
  };
  const g28 = await at(finalL);
  const w28 = expect(m.id, R.pairs[0].id, finalL);
  chk(g28 && g28.rows[0].g === w28.c[0].g.toFixed(2),
      `L${finalL} 画的是 L${finalL} 的分数`, g28 && g28.rows[0].g);
  chk(g28 && g28.chips.find(c => c.L === String(finalL)).on, `L${finalL} 按钮高亮`);
  chk(g28 && g28.chips.find(c => c.L === String(finalL)).txt.includes('最终'),
      `L${finalL} 按钮标注「最终」`);
  chk(g28 && g28.chips.filter(c => c.on).length === 1,
      `L${finalL} 只有一个按钮高亮`,
      String(g28 && g28.chips.filter(c => c.on).length));

  // V1: the answer must be visible without scrolling *inside* the panel.
  // The panel's scroller is 460px against ~1780px of content, so a block parked
  // at the bottom shows its heading and nothing else -- the reader never learns
  // the answer is there. Measured in viewport coordinates, because that is what
  // the eye gets.
  const vis = await page.eval(`(()=>{
    const b=document.querySelector('[data-dvblock]');
    const sc=b.closest('div[style*="overflow-y"]');
    const band=sc.getBoundingClientRect();
    const rows=[...b.querySelectorAll('div')].filter(d=>d.querySelectorAll(':scope > span').length>=4);
    // A raw DOMRect has no own enumerable properties, so CDP serialises it
    // to {} and every field reads NaN. That is a broken probe, not a
    // broken page -- copy the two numbers out explicitly.
    const r=i=>{const q=rows[i].getBoundingClientRect();
              return {top:q.top,bottom:q.bottom};};
    return { bandTop:Math.round(band.top), bandBot:Math.round(band.bottom),
             bandH:Math.round(band.height),
             firstCtl:r(0), firstSte:r(${NCAND}), blockTop:Math.round(b.getBoundingClientRect().top) };
  })()`);
  const inBand = q => q.bottom <= vis.bandBot + 1 && q.top >= vis.bandTop - 1;
  chk(inBand(vis.firstCtl),
      `${m.label} 不滚动就能看到对照臂第一候选`,
      `band ${vis.bandTop}-${vis.bandBot}, row@${Math.round(vis.firstCtl.top)}-${Math.round(vis.firstCtl.bottom)}`);
  chk(inBand(vis.firstSte),
      `${m.label} 不滚动就能看到干预臂第一候选`,
      `row@${Math.round(vis.firstSte.top)}-${Math.round(vis.firstSte.bottom)}`);

  const shallow = R.meta.layers.find(L => L !== finalL && R.meta.layers.indexOf(L) === 0);
  const gSh = await at(shallow);
  const wSh = expect(m.id, R.pairs[0].id, shallow);
  chk(gSh && gSh.rows[0].g === wSh.c[0].g.toFixed(2),
      `L${shallow} 画的是 L${shallow} 的分数`, gSh && gSh.rows[0].g);
  chk(gSh && gSh.rows[0].g !== g28.rows[0].g,
      `L${shallow} 与 L${finalL} 分数确实不同（否则「切换」没意义）`,
      `${gSh && gSh.rows[0].g} vs ${g28.rows[0].g}`);
  chk(gSh && gSh.chips.find(c => c.L === String(shallow)).on, `L${shallow} 按钮高亮`);
  chk(gSh && gSh.text.includes(wSh.kl.toFixed(1)),
      `L${shallow} 的 KL=${wSh.kl.toFixed(1)} 告诫出现`,
      `期望 ${wSh.kl.toFixed(1)}`);
  chk(g28 && !g28.text.includes(`相差 ${wSh.kl.toFixed(1)}`),
      `L${finalL} 不再显示浅层的 KL 告诫`);

  await page.screenshot(SHOTS + `/panel_${m.id}_L${shallow}.png`, { fullPage: false });
  await at(finalL);
  await page.screenshot(SHOTS + `/panel_${m.id}_L${finalL}.png`, { fullPage: false });

  // N3: switching problems must change the panel, not freeze it.
  if (R.pairs.length > 1) {
    await page.eval(`(()=>{const s=document.getElementById('selPair');s.value='0';
      s.dispatchEvent(new Event('change'));return 1;})()`);
    await sleep(1400);
    const a0 = await page.eval(READ);
    await page.eval(`(()=>{const s=document.getElementById('selPair');s.value='1';
      s.dispatchEvent(new Event('change'));return 1;})()`);
    await sleep(1400);
    const a1 = await page.eval(READ);
    chk(a0 && a1 && a0.text !== a1.text,
        `负控 N3：切题后面板内容跟着变（${R.pairs[0].id} → ${R.pairs[1].id}）`);
  }
}

chk(exceptions.length === 0, '全程无 JS 异常',
    exceptions.slice(0, 2).join(' | ').slice(0, 200));

console.log(`\n失败 ${fails.length} 条`);
fails.forEach(f => console.log('  - ' + f));
try { await page.close(); } catch {}
try { proc.kill(); } catch {}
process.exit(fails.length ? 1 : 0);
