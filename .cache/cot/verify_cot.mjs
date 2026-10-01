// Does the page state, in plain words, what the vector did to the reasoning?
//
// The measurement existed the whole time (analyse_cot_divergence.py over
// run_intervention.py's primary/shadow pairs) and the page showed none of it --
// just two texts side by side. That is the goal's explicit "思维链到底有什么
// 影响" sitting unanswered on the same screen as the data for it.
//
// The result is a null result, and null results are where a page is most likely
// to overclaim. So the checks are not only "are the numbers right", they are:
//
//   L1-L3  the three limitations are printed next to the conclusion. Each maps
//          to a specific way this table could be misread as stronger evidence
//          than it is: the harness control, the p-value, and the answer column
//          being 7-of-168 with zero closed traces.
//   N1     0.6B must show "no data", not 1.7B's numbers. Only the 1.7B bundle
//          ships cot_effect.json, and 1.7B/0.6B reuse nothing here -- but the
//          fallback path (silently reusing the other model) is exactly the bug
//          this project has already paid for once on the retention figures.
//   N2     every row's control must still be the identity in the shipped file.
//          build_cot_effect.py refuses to emit a file that fails this, so
//          asserting it on the delivered JSON catches a hand-edited payload.
import { launch, CDP, Page } from '../browser_verify/cdp_client.mjs';
import { mkdirSync } from 'node:fs';

const URL = 'http://localhost:8917/latent/index.html';
const OUT = '/Users/zhourui/code/steer3d/.cache/divergence_shots';
mkdirSync(OUT, { recursive: true });
const sleep = ms => new Promise(r => setTimeout(r, ms));

const fails = [];
const chk = (c, label, extra = '') => {
  console.log((c ? '  ok   ' : '  FAIL ') + label + (extra ? '   ' + extra : ''));
  if (!c) fails.push(label);
};

const reg = await (await fetch('http://localhost:8917/latent/models.json')).json();
const big = reg.models.find(m => m.d_model === 2048);
const small = reg.models.find(m => m.d_model === 1024);
const cot = await (await fetch(`http://localhost:8917/latent/${big.base}cot_effect.json`)).json();

// The other model's bundle must genuinely not have the file, or "0.6B shows no
// data" would be a fact about the server rather than about the page.
const smallHas = await fetch(`http://localhost:8917/latent/${small.base}cot_effect.json`);
chk(!smallHas.ok, `包内 ${small.base} 确实没有 cot_effect.json（这是"没有数据"的前提）`,
    'HTTP ' + smallHas.status);

chk(cot.control_is_identity === true, '产物自带「对照臂恒等」标记');
for (const r of cot.rows) {
  chk(r.control.token_agreement === 1 && r.control.reason_len_ratio === 1
      && r.control.selfcheck_delta === 0 && r.control.verbatim_overlap === 1,
      `${r.direction}@${r.strength} 的对照臂逐项恒等`,
      JSON.stringify(r.control));
}

const { proc, version } = await launch({
  port: 9365, userDataDir: '/Users/zhourui/code/steer3d/.cache/divergence/cot_profile',
  url: 'about:blank' });
const cdp = await CDP.connect(
  `ws://127.0.0.1:9365/devtools/browser/${version.webSocketDebuggerUrl.split('/').pop()}`);
const page = await Page.create(cdp);
await page.send('Network.enable');
await page.send('Network.setCacheDisabled', { cacheDisabled: true });
await page.send('Emulation.setDeviceMetricsOverride',
  { width: 1600, height: 1100, deviceScaleFactor: 1, mobile: false });
const exceptions = [];
cdp.on(m => { if (m.method === 'Runtime.exceptionThrown')
  exceptions.push(m.params.exceptionDetails?.exception?.description
                  || m.params.exceptionDetails?.text || 'unknown'); });

const READ = `(()=>{
  const b=document.querySelector('[data-cotblock]');
  const none=document.querySelector('[data-dvblock]');
  // The "no data" branch renders inside the same wrapper as the readout, so
  // look for its wording when the cot block itself is absent.
  const wrap=b?b:null;
  const tbl=document.getElementById('tblTop');
  return { has: !!b, text: wrap?wrap.innerText:'',
           dirBtns: wrap?[...wrap.querySelectorAll('[data-cotdir]')].map(x=>x.dataset.cotdir):[],
           on: wrap?[...wrap.querySelectorAll('[data-cotdir]')]
                     .filter(x=>x.className.includes('on')).map(x=>x.dataset.cotdir):[],
           tblText: tbl?tbl.innerText:'' };
})()`;

async function open(m) {
  await page.send('Page.navigate', { url: `${URL}?orient=reset&m=${m.id}` });
  await page.waitForEvent('Page.loadEventFired', 40000);
  await sleep(6000);
  if (await page.eval(`(()=>{const o=document.getElementById('orientation');
      return !!(o&&getComputedStyle(o).display!=='none');})()`)) {
    await page.click('#orientClose'); await sleep(800);
  }
  await page.click('#tabDelta'); await sleep(2400);
  return page.eval(READ);
}

console.log(`\n===== ${big.label}：面板应完整呈现 =====`);
let g = await open(big);
chk(g.has, '思维链面板渲染出来了');
chk(g.dirBtns.length === cot.directions.length,
    `${cot.directions.length} 个方向按钮`, g.dirBtns.join('/'));
chk(g.on.length === 1, `默认高亮一个方向`, JSON.stringify(g.on));

// Numbers, against the shipped rows for the selected direction.
const sel = g.on[0];
for (const r of cot.rows.filter(x => x.direction === sel)) {
  const pct = (r.token_agreement * 100).toFixed(1);
  chk(g.text.includes(pct), `${r.direction}@${r.strength} token 一致率 ${pct}% 在面板上`);
  chk(g.text.includes((r.verbatim_overlap * 100).toFixed(0) + '%'),
      `${r.direction}@${r.strength} 逐字重合 ${(r.verbatim_overlap*100).toFixed(0)}% 在面板上`);
  chk(g.text.includes(r.reason_len_ratio.toFixed(3)),
      `${r.direction}@${r.strength} 长度比 ${r.reason_len_ratio.toFixed(3)} 在面板上`);
  chk(g.text.includes('p = ' + r.selfcheck_p.toFixed(2)),
      `${r.direction}@${r.strength} 自我检查 p 值 ${r.selfcheck_p.toFixed(2)} 在面板上`);
}
chk(/向量把思维链改/.test(g.text), '面板自带标题（不是只有上方的 sideTitle 顶着）');
chk(/这是另一组实验/.test(g.text), '标明这是与配对流不同的一组实验');
chk(/^\s*\S/.test(g.text) && g.text.trim().length > 0, '面板文本非空');
chk(g.text.includes(cot.model), `写明是哪个模型的实验（${cot.model}）`);
chk(g.text.includes('喂零向量') || g.text.includes('零向量'), '说明对照组是零向量');

// --- the three limitations -------------------------------------------------
console.log('\n--- 三条限制必须与结论同屏 ---');
chk(/测不出差别|不等于没有差别/.test(g.text), 'L2 自我检查：说明"测不出差别≠没有差别"');
chk(/没测到/.test(g.text), 'L3 答案那一维标为"没测到"');
chk(g.text.includes(String(cot.coverage.answer_known))
    && g.text.includes(String(cot.coverage.runs)),
    `L3 给出答案覆盖率 ${cot.coverage.answer_known}/${cot.coverage.runs}`);
chk(/没有.*跑完|一次都没有跑完/.test(g.text), 'L3 点明没有一次跑完 </think>');
chk(cot.coverage.closed_think === 0 && /没有|一次都没有/.test(g.text),
    'L3 与产物的 closed_think=0 一致');
// The dangerous phrasing is an ASSERTION that the answer did not change. The
// first version of this check was a bare regex, and it fired on the page's own
// disclaimer -- "别拿它证明「答案不受影响」" contains the banned words. A
// check that cannot tell a claim from the warning against it is not checking
// the thing. So each occurrence is judged by its surrounding clause: it passes
// only if what precedes it is a disclaimer.
const claims = await page.eval(`(()=>{
  const b=document.querySelector('[data-cotblock]');
  if(!b) return null;
  const t=b.innerText;
  const re=/答案[^。！？\\n]{0,10}(没变|不变|不受影响)/g;
  const hits=[]; let m;
  while((m=re.exec(t))!==null){
    hits.push({hit:m[0], before:t.slice(Math.max(0,m.index-24), m.index)});
  }
  return hits;})()`);
const disclaim = /别|不是|没测到|不要|≠|没有.*结论|劝/;
const asserted = (claims || []).filter(c => !disclaim.test(c.before));
chk(asserted.length === 0,
    '页面没有把"答案"写成阴性结论（劝阻语不算断言）',
    asserted.map(c => `…${c.before}[${c.hit}]`).join(' | ').slice(0, 120));
console.log(`       （命中 ${(claims || []).length} 处，其中劝阻 ${(claims || []).length - asserted.length} 处）`);

// Direction switching must actually re-render.
const other = cot.directions.find(d => d !== sel);
await page.eval(`(()=>{const b=document.querySelector('[data-cotblock]');
  const c=b.querySelector('[data-cotdir="${other}"]'); if(c) c.click(); return !!c;})()`);
await sleep(900);
const g2 = await page.eval(READ);
chk(g2.has && g2.on.length === 1 && g2.on[0] === other,
    `切到「${other}」后高亮跟着换`, JSON.stringify(g2.on));
chk(g2.text !== g.text, '切方向后面板内容确实变了');

await page.eval(`(()=>{document.querySelector('[data-cotblock]')
  .scrollIntoView({block:'center'});return 1;})()`);
await sleep(700);
const r = await page.rect('[data-cotblock]');
await page.screenshot(`${OUT}/cot_${big.id}.png`, { clip: {
  x: Math.max(0, r.x - 14), y: Math.max(0, r.y - 8),
  width: Math.min(1600 - Math.max(0, r.x - 14), r.w + 28),
  height: Math.min(1100 - Math.max(0, r.y - 8), r.h + 16) } });

console.log(`\n===== ${small.label}：必须说"没有数据"，不得串用 =====`);
const s = await open(small);
chk(!s.has, `${small.label} 不渲染思维链面板`);
chk(/这一块没有数据|没做过思维链层面的实验/.test(s.tblText),
    `${small.label} 明说这一维缺失`,
    (s.tblText.match(/这一块没有数据[^\n]*/) || [''])[0].slice(0, 40));
// No number from the 1.7B table may appear anywhere in the 0.6B panel.
const foreign = new Set();
for (const row of cot.rows) {
  foreign.add((row.token_agreement * 100).toFixed(1));
  foreign.add((row.reason_len_ratio).toFixed(3));
}
foreign.add(String(cot.n_runs));
foreign.add(cot.model);
const leak = [...foreign].filter(t => t.length > 3 && s.tblText.includes(t));
chk(leak.length === 0, `${small.label} 没有出现 1.7B 思维链表的任何数字/模型名`,
    leak.join(' '));

chk(exceptions.length === 0, '全程无 JS 异常',
    exceptions.slice(0, 2).join(' | ').slice(0, 160));

console.log(`\n失败 ${fails.length} 条`);
fails.forEach(f => console.log('  - ' + f));
try { await page.close(); } catch {} try { proc.kill(); } catch {}
process.exit(fails.length ? 1 : 0);
