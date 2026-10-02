// Checks the "why this token" panel against an independent computation.
//
// The panel used to print raw logits (31.13, 19.25, ...) and size each bar by
// (logit - lo) / (best - lo) -- the gap between scores, which is not how likely
// the words were. The rewrite shows softmax probabilities, marks the token the
// model actually emitted, and states how truncated the top-64 view is.
//
// The load-bearing assertion is #6: the percentage the page prints is compared
// against a softmax computed here, in Node, straight from topk_00.bin. A panel
// that renders beautifully while showing the wrong number passes every
// DOM-level check, so the number has to be reconciled against the file it came
// from.
//
// Run: node verify_picked.mjs

import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { launch, CDP, Page } from '../browser_verify/cdp_client.mjs';

const sleep = ms => new Promise(r => setTimeout(r, ms));
const HERE = new URL('.', import.meta.url).pathname;
const DATA = '/Users/zhourui/code/steer3d/frontend/public/latent/data/';
const PAGE_URL = process.env.FRONTEND || 'http://127.0.0.1:8917/latent/index.html';
const CDP_PORT = Number(process.env.BV_PORT || 9460);

mkdirSync(HERE + 'out/', { recursive: true });
const results = [];
let failures = 0;
const check = (name, ok, detail) => {
  results.push({ name, ok: !!ok, detail });
  if (!ok) failures++;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? '  ' + detail : ''}`);
};

// ---- independent reference, computed here from the same file ------------
const manifest = JSON.parse(readFileSync(DATA + 'manifest.json', 'utf8'));
const TIDX = Number(process.env.TIDX || 0);
const STEP = Number(process.env.STEP || 2);
const traj = manifest.trajectories[TIDX];
const K = manifest.topk || 64;
const buf = readFileSync(DATA + traj.topk);
const idBuf = readFileSync(DATA + traj.topki);
const f32 = new Float32Array(buf.buffer, buf.byteOffset, buf.byteLength / 4);
const i32 = new Int32Array(idBuf.buffer, idBuf.byteOffset, idBuf.byteLength / 4);

const rows = [];
for (let k = 0; k < K; k++) rows.push({ logit: f32[STEP * K + k], id: i32[STEP * K + k] });
rows.sort((a, b) => b.logit - a.logit);
const mx = rows[0].logit;
let z = 0;
for (const r of rows) z += Math.exp(r.logit - mx);
const ref = rows.map(r => ({ ...r, p: Math.exp(r.logit - mx) / z }));
const vocab = JSON.parse(readFileSync(DATA + 'vocab.json', 'utf8'));
const ids = vocab.ids;
// Step 0's reference ranking, computed the same independent way. Step 0 is
// where the HTML-shaped candidates live; STEP is usually 2, where they do not.
const rows0 = [];
for (let k = 0; k < K; k++) rows0.push({ logit: f32[0 * K + k], id: i32[0 * K + k] });
rows0.sort((a, b) => b.logit - a.logit);
const ref0 = rows0;
const chosenId = traj.tokens[STEP].id;
console.log(`reference (computed in Node from ${traj.topk}, step ${STEP} of "${traj.problem_id}"):`);
console.log(`  chosen token ${JSON.stringify(ids[chosenId])} id=${chosenId}`);
ref.slice(0, 4).forEach((r, i) => console.log(
  `  #${i + 1} ${JSON.stringify(ids[r.id])}  logit=${r.logit.toFixed(3)}  p=${(r.p * 100).toFixed(2)}%`));
console.log('');

const { proc, version } = await launch({
  port: CDP_PORT,
  userDataDir: HERE + 'profile_' + CDP_PORT,
  windowSize: '1600,1000',
  url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);

try {
  const errors = [];
  page.cdp.on(m => {
    if (m.method === 'Runtime.exceptionThrown') {
      const d = m.params.exceptionDetails;
      errors.push(d.exception?.description || d.text);
    }
  });
  await page.send('Network.enable');
  await page.send('Network.setCacheDisabled', { cacheDisabled: true });
  await page.send('Page.enable');
  await page.send('Runtime.enable');
  await page.send('Page.navigate', { url: PAGE_URL });

  for (let i = 0; i < 30; i++) {
    await sleep(1000);
    const ready = await page.eval(`(()=>{try{return !!(window.S||S)&&S.m&&S.m.trajectories&&S.m.trajectories.length>0}catch(e){return false}})()`);
    if (ready) break;
  }

  check('the page loaded with no uncaught exception', errors.length === 0,
    errors.length ? errors[0].slice(0, 160) : 'clean');

  // Drive to the trajectory/step under test, then let it render.
  const set = await page.eval(`(()=>{
    S.ti = ${TIDX}; S.tok = ${STEP}; S.view = "BAR";
    if (typeof renderAll === "function") renderAll();
    else { drawBar(); renderTop(); }
    return { ti: S.ti, tok: S.tok, shipped: S.m.trajectories[S.ti].n_tokens_shipped };
  })()`);
  check('the page exposes its state and accepted the navigation',
    set.ti === TIDX && set.tok === STEP && set.shipped > STEP,
    JSON.stringify(set));
  await sleep(700);

  // -- 1. the plain-language block exists and states a probability --------
  const picked = await page.eval(`(()=>{
    const el = document.querySelector('#picked');
    return el ? { text: el.innerText.replace(/\\s+/g,' ').trim(), html: el.innerHTML.length } : null;
  })()`);
  check('a plain-language answer block is rendered', picked && picked.text.length > 20,
    picked ? picked.text.slice(0, 110) : 'missing');
  check('it states the chosen token in words',
    picked && picked.text.includes(ids[chosenId].trim()) || (picked && picked.text.includes('模型这一步选了')),
    picked ? 'ok' : 'missing');
  check('it states a probability with a % sign',
    picked && /%/.test(picked.text), picked ? (picked.text.match(/[\d.]+%/) || ['none'])[0] : 'n/a');

  // -- 2. the table shows probabilities, not raw logits -------------------
  // Read the last cell of each row rather than a fixed index. When the score
  // column is mutated to print logits it no longer matches /%/, and indexing
  // a column that is not there aborted the whole script -- which threw away
  // every assertion after this point, including the ones that would have
  // explained the failure. A check that crashes on the defect it is meant to
  // catch reports less than one that reports cleanly.
  const tbl = await page.eval(`(()=>{
    return [...document.querySelectorAll('#tblTop tr')].slice(1)
      .map(tr => [...tr.children].map(td => td.innerText.trim()));
  })()`);
  const scoreCol = (r) => (r && r.length ? r[r.length - 1] : '');
  const body = tbl.filter(r => /%/.test(scoreCol(r)));
  check('every candidate row shows a probability, not a raw score',
    body.length >= 8, `${body.length} rows with %`);
  check('no row still shows a raw 2-decimal logit in the score column',
    !tbl.some(r => /^\d+\.\d\d$/.test(scoreCol(r))),
    (tbl.find(r => /^\d+\.\d\d$/.test(scoreCol(r))) || ['none'])[0]);
  check('the top row is the highest probability',
    body.length >= 2 && parseFloat(scoreCol(body[0])) >= parseFloat(scoreCol(body[1])),
    body.length >= 2 ? `${scoreCol(body[0])} >= ${scoreCol(body[1])}` : 'n/a');

  // -- 3. the token the model actually emitted is marked ------------------
  const marked = await page.eval(`(()=>{
    const trs = [...document.querySelectorAll('#tblTop tr')];
    const i = trs.findIndex(tr => tr.innerText.includes('←选了'));
    return { index: i, text: i >= 0 ? trs[i].innerText.replace(/\\s+/g,' ').trim() : '' };
  })()`);
  // index 0 is the header row this rewrite added (#/候选词/概率/占比), so the
  // first data row is 1. Asserting 0 would have failed on a correct page.
  check('the row for the emitted token is marked, and it is the top row',
    marked.index === 1,
    `tr index ${marked.index} (1 = first data row, after the header): ${marked.text.slice(0, 70)}`);

  // -- 4. the truncation caveat is stated --------------------------------
  const notes = await page.eval(`(()=>[...document.querySelectorAll('#tblTop .note')].map(n=>n.innerText).join(' '))()`);
  check('the panel admits the top-64 truncation and gives a tail bound',
    /151,?872|之后还有/.test(notes) && /不超过/.test(notes),
    notes.replace(/\s+/g, ' ').slice(0, 120));

  // -- 5. probabilities are a distribution --------------------------------
  // Only sum cells that parsed as numbers. parseFloat('') is NaN, and a NaN
  // here made this check fail with "sum = NaN%", which reads like a rounding
  // problem rather than "this column is not a percentage at all".
  const nums = body.map(r => parseFloat(scoreCol(r))).filter(Number.isFinite);
  const sum = nums.reduce((a, v) => a + v, 0);
  check('the displayed probabilities do not exceed 100%',
    nums.length > 0 && sum <= 100.001 && sum > 0,
    nums.length ? `sum of ${nums.length} shown rows = ${sum.toFixed(2)}%` : 'no numeric score column');

  // -- 6. THE assertion: the number on screen matches the file -----------
  const shown = parseFloat(scoreCol(body[0]));
  const expect = ref[0].p * 100;
  check('the percentage on screen matches an independent softmax of topk_*.bin',
    Math.abs(shown - expect) < 0.011,
    `page=${shown}% reference=${expect.toFixed(2)}% (tolerance 0.01pp, which is just the 2-dp rounding)`);
  const shownAlt = parseFloat(scoreCol(body[1]));
  check('so does the runner-up',
    Math.abs(shownAlt - ref[1].p * 100) < 0.011,
    `page=${shownAlt}% reference=${(ref[1].p * 100).toFixed(4)}%`);

  // -- 6b. distinct tokens must not collapse to the same rendering -------
  // Checked at the torn step below, where the candidates actually contain
  // newlines. (First written here, where STEP=2 of trajectory 0 has the top
  // three as Okay / Alright / Yes -- no whitespace to reveal, so it could
  // only ever fail.)
  // At 1994 step 27 the top three are ' here', '.\n\n' and '.'. Rendered as
  // plain HTML the two dots are indistinguishable, so the panel said twice
  // that the runner-up was a bare full stop -- hiding that its second choice
  // was to end the sentence. Whitespace inside a token is content here.

  // -- 7. the bar widths encode probability, not score gap ---------------
  // The renderer floors a bar at 0.6% so a real-but-tiny probability is still
  // visible at all; below that it would be a fraction of a pixel. The number
  // in the 占比 column stays authoritative, so the floor is an affordance and
  // not a claim. The reference below therefore models the same floor --
  // comparing against a raw p*100 would report a diff of exactly 0.600 on
  // every sub-floor row and look like a rendering bug.
  const FLOOR = 0.6;
  const bars = await page.eval(`(()=>[...document.querySelectorAll('#tblTop .bar > div')].slice(0,6)
      .map(d=>parseFloat(d.style.width)))()`);
  const wRef = ref.slice(0, 6).map(r => Math.max(FLOOR, r.p * 100));
  const maxDiff = Math.max(...bars.map((w, i) => Math.abs(w - wRef[i])));
  check('bar widths are max(0.6%, p*100), so a confident step looks decisive',
    maxDiff < 0.5, `max width diff = ${maxDiff.toFixed(3)}pp`);

  // -- 8. the old logit-scaled chart would have told a different story ----
  // A regression note rather than a page check: under the old scaling step 0
  // drew #2 at 65% of #1. Report what the new chart says for the same step so
  // the difference is on the record.
  const contrast = await page.eval(`(()=>{
    S.tok = 0; S.view = "BAR"; drawBar(); renderTop();
    const rows = [...document.querySelectorAll('#tblTop tr')].slice(1,3)
      .map(tr => [...tr.children].map(td=>td.innerText.trim()));
    return rows;
  })()`);
  console.log(`\n  step 0 contrast: top=${contrast[0]?.[3]}  second=${contrast[1]?.[3]}` +
    `  (old logit scaling would have drawn the second at ~65% of the first)`);

  await page.screenshot(HERE + 'out/picked.png');
  // -- 9. the feature that makes the panel answer the question ------------
  // Trajectory 10 (1994_I_1) has the most torn step in the whole bundle:
  // step 27, p1 = 41.92%. A reader who wants "why this token and not that
  // one" wants that step, not the median 99.9999% one.
  //
  // Switching trajectory has to go through loadTraj(), not `S.ti = n`:
  // loadTraj is async and pulls that trajectory's proj/mean/pca buffers in.
  // An earlier version of this check assigned S.ti directly -- and silently
  // stayed on trajectory 0, because the first test happened to ask for
  // trajectory 0. It reported three failures against the wrong question.
  const jump = await page.eval(`(async()=>{
    await loadTraj(10);
    S.tok = 0; S.view = "BAR"; render();
    const link = document.querySelector("#jumpTorn");
    if(!link) return { noLink: true, tok: S.tok, ti: S.ti };
    link.click();
    return { noLink:false, tok: S.tok, ti: S.ti };
  })()`);
  check('the trajectory actually switched before the jump was tested',
    jump.ti === 10, `S.ti=${jump.ti} (assigning S.ti directly does NOT load the buffers)`);
  await sleep(500);
  const torn = await page.eval(`(()=>({
    tok: S.tok,
    picked: document.querySelector('#picked').innerText.replace(/\\s+/g,' ').trim(),
    runnerUp: (document.querySelectorAll('#tblTop tr')[2]?.innerText||'').replace(/\\s+/g,' ').trim(),
    topRow: (document.querySelectorAll('#tblTop tr')[1]?.innerText||'').replace(/\\s+/g,' ').trim(),
  }))()`);
  check('the "jump to the most uncertain step" link navigates to it',
    !jump.noLink && torn.tok === 27, `landed on step ${torn.tok} (expected 27)`);
  check('that step is described as a real decision point, in words',
    /真正在犹豫|分岔口|不确定/.test(torn.picked), torn.picked.slice(0, 130));
  // Read the whole block, not a .pickedCtx child: that element was merged
  // into .pickedAlt when the block was compacted to fit an 800px window, and
  // a check bound to a class name that no longer exists fails on a page that
  // is correct.
  check('the panel notes this is the most uncertain step of the problem',
    /最犹豫的一步/.test(torn.picked),
    (torn.picked.match(/[^。]*最犹豫的一步[^。]*/) || ['not found'])[0].slice(0, 80));
  const rUp = (torn.runnerUp.match(/([\d.]+)%/) || [])[1];
  const tUp = (torn.topRow.match(/([\d.]+)%/) || [])[1];
  if (tUp === undefined) { /* leave the two checks below to report it */ }
  check('the runner-up at a torn step is a real alternative, not 0.00%',
    rUp !== undefined && parseFloat(rUp) > 5, `top=${tUp}% runner-up=${rUp}%`);

  // Reference: independently confirm step 27 of trajectory 10.
  const lg27 = new Float32Array(
    readFileSync(DATA + manifest.trajectories[10].topk).buffer).slice(27 * K, 28 * K);
  const mx27 = Math.max(...lg27);
  const z27 = lg27.reduce((a, v) => a + Math.exp(v - mx27), 0);
  const p1ref = Math.exp(lg27[0] - mx27) / z27 * 100;
  check('the torn step on screen matches the file',
    Math.abs(parseFloat(tUp) - p1ref) < 0.011,
    `page=${tUp}% reference=${p1ref.toFixed(2)}%`);

  // The three genuinely different candidates at this step must stay three
  // different strings on screen.
  const cells = await page.eval(`(()=>[...document.querySelectorAll('#tblTop tr')]
      .slice(1,4).map(tr=>tr.children[1].innerText.trim()))()`);
  check('whitespace inside a token is made visible, not collapsed',
    new Set(cells).size === 3, `rendered as: ${JSON.stringify(cells)}`);
  check('the runner-up is revealed as period+newlines, i.e. "end the sentence"',
    /⏎/.test(cells[1]), `runner-up cell: ${JSON.stringify(cells[1])}`);
  check('and the plain-language line says the same thing',
    /\.⏎/.test(torn.picked) || /⏎/.test(torn.picked),
    (torn.picked.match(/第二可能是[^（]*/) || ['not found'])[0]);

  // ---------------------------------------------------------------------
  // Tokens that are valid HTML. The panel above checks step 2, where the top
  // candidate is the ordinary word "Okay". Step 0 of the same trajectory is
  // where the bug lived: its top-4 candidates are the literal strings
  // `<think>`, `</think>`, `<|im_start|>`, `<|im_end|>` and ranks 6/9 are
  // `<tool_response>` / `</tool_response>`. Written into innerHTML unescaped
  // those are parsed as tags, so four rows rendered EMPTY -- including the
  // cell under the headline "模型这一步选了 __". Every check in this file
  // still passed, because the rows existed and had probabilities.
  //
  // So this walks every shipped step of this trajectory, reads the expected
  // token straight out of vocab.json, and requires the rendered cell to show
  // exactly that. A blank cell for any token containing "<" is the signature.
  const htmlish = await page.eval(`(async()=>{
    const K=64, out=[];
    // Go through loadTraj(), NOT by assigning S.ti directly. S.ti and the
    // candidate-word buffers are set together inside loadTraj, and the
    // assertion block above deliberately left trajectory 10 loaded. Assigning
    // S.ti alone left S.topk holding 1994_I_1's top-64 while S.ti said 0, so
    // the table showed one problem's candidates under another problem's
    // tokens. Nothing caught it: every id in the loop came from the same
    // desynced pair, so the checks agreed with themselves. A comment twenty
    // lines above this one already said switching trajectory has to go
    // through loadTraj() -- written for a different assertion, and I read
    // straight past it. (No backticks in this comment: it lives inside a
    // template literal and a stray one closes the string.)
    await loadTraj(${TIDX});
    const nSteps = S.m.trajectories[S.ti].n_tokens_shipped;
    for(let k=0;k<nSteps;k++){
      // renderTop(), not render(). render() schedules its DOM writes, so
      // reading the table on the next line read the PREVIOUS step's rows --
      // and the first version of this check then reported a mismatch on
      // ranks 3..10 that was purely its own off-by-one. renderTop() assigns
      // tb.innerHTML synchronously, so the read that follows sees this step.
      S.tok=k; S.view="BAR"; renderTop();
      const cell=document.querySelector('.pickedTok b');
      const alt=document.querySelector('.pickedAlt b');
      const id=S.m.trajectories[S.ti].tokens[k].id;
      // The TABLE rows, not just the headline. The first version of this check
      // only compared .pickedTok b, and mutation M3 (which touches the table
      // cell and not the headline) sailed through 27/27 -- the defect was on
      // screen the whole time and the assertion was pointed at the other
      // element. Read all ten rows: the table has a header at
      // nth-child(1), so rank i is nth-child(i+2).
      const rows=[...document.querySelectorAll('#tblTop tr')].slice(1, 11)
        .map(tr=>{const c=tr.querySelector('td.tok'); return c?c.textContent:null;});
      out.push({k, id, shown: cell?cell.textContent:null,
                alt: alt?alt.textContent:null, rows});
    }
    return {rows: out, vocabLen: (S.vocab||[]).length};
  })()`);
  const cellFor = r => String(ids[r.id] || '');
  const blanks = htmlish.rows.filter(r => {
    const want = cellFor(r);
    return /[<>]/.test(want) && String(r.shown || '').trim() === '';
  });
  check('no step renders an empty cell for a token that contains "<" or ">"',
    blanks.length === 0,
    blanks.length
      ? `第 ${blanks.slice(0,4).map(b=>b.k+' 步应有 '+JSON.stringify(cellFor(b))).join('、')} 步渲染为空`
      : `扫了 ${htmlish.rows.length} 步`);
  // And the headline cell must agree with the payload, token for token --
  // not merely be non-empty.
  const mismatch = htmlish.rows.filter(r => {
    const want = cellFor(r);
    if (!want) return false;
    const got = String(r.shown || '').trim();
    // visTok maps a leading space to '·' and newlines to '⏎'.
    const norm = want.replace(/\\/g,'\\\\').replace(/\n/g,'⏎').replace(/\r/g,'␍')
                     .replace(/\t/g,'⇥').replace(/^ /,'·');
    return got !== norm;
  });
  check('每一步的「模型这一步选了 X」与 vocab.json 里的词逐字一致',
    mismatch.length === 0,
    mismatch.length
      ? `第 ${mismatch.slice(0,3).map(m=>m.k+' 步 期望 '+JSON.stringify(cellFor(m))+' 实得 '+JSON.stringify(String(m.shown))).join('；')}`
      : `${htmlish.rows.length} 步全部逐字一致`);
  // The runner-up line, which is the other half of "why not that one".
  const altBad = htmlish.rows.filter(r => /[<>]/.test(cellFor(r)) && String(r.alt||'').trim() === '');
  check('第二可能那一行同样没有吞掉 HTML 式 token', altBad.length === 0,
    altBad.length ? `${altBad.length} 步的第二可能是空的` : '');
  // The table itself: every visible row must print the word, and the word must
  // be the one the file says. An empty cell in a table that still has a rank
  // number and a probability is exactly what the HTML parsing produced.
  const emptyCells = [];
  for (const r of htmlish.rows) {
    (r.rows || []).forEach((cellTxt, i) => {
      if (String(cellTxt || '').trim() === '') emptyCells.push(`第 ${r.k} 步第 ${i+1} 名`);
    });
  }
  check('候选词表里没有一格是空的（表头之外十格逐格检查）',
    emptyCells.length === 0,
    emptyCells.length ? `${emptyCells.length} 格为空：${emptyCells.slice(0,5).join('、')}` : '');
  // One step, read the page's OWN candidate order and require the rendered
  // cell to print exactly the word that order names. The scope is deliberately
  // narrow: this asserts the escaping, not the softmax. The softmax is already
  // reconciled against an independent computation of topk_*.bin above, and an
  // earlier version of this check re-sorted the file in Node and compared
  // position by position -- which made it a second, weaker copy of that check
  // and, because it read the DOM after render() had been called for all 48
  // steps, compared step 0 against a stale table and reported nine phantom
  // mismatches. One step, page order, no re-sorting.
  const step0 = await page.eval(`(async()=>{
    await loadTraj(${TIDX}); S.tok = 0; S.view = "BAR"; renderTop();
    const rows = topProbs().slice(0, 10).map(r => S.vocab[r.id]);
    const cells = [...document.querySelectorAll('#tblTop tr')].slice(1, 11)
      .map(tr => { const c = tr.querySelector('td.tok');
                   return c ? c.textContent.replace(/\s*←选了\s*$/, '').trim() : null; });
    return { rows, cells, note: document.querySelector('#tblTop').innerText };
  })()`);
  const normTok = t => String(t).replace(/\\/g, '\\\\').replace(/\n/g, '⏎')
    .replace(/\r/g, '␍').replace(/\t/g, '⇥').replace(/^ /, '·');
  const d0 = step0.rows.map((w, i) => normTok(w) === step0.cells[i] ? null
    : `#${i+1} 期望 ${JSON.stringify(normTok(w))} 实得 ${JSON.stringify(step0.cells[i])}`)
    .filter(Boolean);
  check('第 0 步十格与页面自己的候选顺序逐格对上（含 <think> / <tool_response>）',
    d0.length === 0, d0.length ? d0.join('；') : '10/10');
  // Spell out the four that used to vanish, so a regression names the words.
  const html4 = ['<think>', '</think>', '<|im_start|>', '<|im_end|>',
                 '<tool_response>', '</tool_response>'];
  const found = step0.rows.filter(r => html4.includes(r));
  const shownN = found.filter(r => html4.some(h => normTok(h) === step0.cells[step0.rows.indexOf(r)]));
  check('这些 HTML 式词在页面上真的显示出来了（不是空格子）',
    found.length === shownN.length && found.length >= 4,
    `第 0 步里这类词有 ${found.length} 个，显示出来的 ${shownN.length} 个`);

  await page.eval(`(()=>{
    const b=[...document.querySelectorAll('button')].find(x=>/开始看|我读完了/.test(x.textContent));
    if(b) b.click();
    return !!b;
  })()`);
  await sleep(900);
  await page.screenshot(HERE + 'out/picked_torn.png');
  // The replacement character is not a rendering bug, and a beginner cannot
  // tell that from the table alone. When any of the top ten is a byte-level
  // fragment the panel has to say what it is.
  //
  // The expected count is computed here from the file, not read back out of
  // the page. A first version asked the page how many fragments it had and
  // compared the note against that answer -- which is circular, and it also
  // inherited whatever state the 48-step sweep above had left behind and
  // reported 1 where the page actually has 2.
  const FRAG = String.fromCharCode(0xFFFD);
  // From the FILE, not from step0.rows (which is the page's own list --
  // comparing the page's note against the page's count is circular and
  // agreed with itself no matter what was rendered).
  const wantFrag = ref0.slice(0, 10).map(r => ids[r.id]).filter(t => t === FRAG).length;
  check('第 0 步前十名里的字节碎片条数（从文件独立算出）', wantFrag >= 0,
    `前十里有 ${wantFrag} 个 \uFFFD`);
  if (wantFrag > 0) {
    // Same eval that already reconciles the ten cells, so this cannot be
    // thrown off by state the 48-step sweep left behind. A version that ran
    // its own eval to re-read the note got "1" where the page has 2, and the
    // honest file-derived count is what exposed it.
    check('面板解释了 \uFFFD 是什么（半个多字节字符，不是显示坏了）',
      new RegExp('这十名里有\\s*' + wantFrag + '\\s*个').test(step0.note || '')
      && /多字节字符被切开/.test(step0.note || '')
      && /不是页面把字显示坏了/.test(step0.note || ''),
      ((step0.note || '').match(/这十名里有[^\n]*/) || ['<表格里没有这行>'])[0]);
  }
  check('no uncaught exception during the whole run', errors.length === 0,
    errors.length ? errors[0].slice(0, 160) : 'clean');
} catch (e) {
  check('the script ran to completion', false, String(e).slice(0, 240));
  failures++;
} finally {
  writeFileSync(HERE + 'out/result_picked.json',
    JSON.stringify({ failures, results, reference: { step: STEP, traj: TIDX, p1: ref[0].p } }, null, 2));
  try { proc.kill('SIGKILL'); } catch {}
  cdp.ws.close();
}
console.log(`\n=== ${results.length - failures}/${results.length} passed, ${failures} failed ===`);
process.exit(failures ? 1 : 0);
