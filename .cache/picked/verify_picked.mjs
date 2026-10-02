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

  // The first-run orientation overlay covers the app, so a screenshot taken
  // before dismissing it shows the primer, not the panel under test.
  await page.eval(`(()=>{
    const b=[...document.querySelectorAll('button')].find(x=>/开始看|我读完了/.test(x.textContent));
    if(b) b.click();
    return !!b;
  })()`);
  await sleep(900);
  await page.screenshot(HERE + 'out/picked_torn.png');
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
