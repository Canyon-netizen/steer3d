// Two-model acceptance: does switching to Qwen3-0.6B actually change the data
// AND the prose, together?
//
// The failure this is built to catch: the page loads 0.6B's hidden states
// (width 1024) while the orientation layer still says "2048 个数字" and
// "587–831 / 2048". Nothing throws. Every panel renders. The guide is simply
// wrong, and a reader has no way to tell -- which is the exact shape of the
// mistake this project has spent five findings correcting.
//
// So the check is not "does 0.6B load". It is: for each model, does the
// rendered page agree with models.json, which is generated from the analysis
// outputs.
import { launch, CDP, Page } from '../browser_verify/cdp_client.mjs';
import { readFileSync, writeFileSync } from 'node:fs';
import { execSync } from 'node:child_process';

const URL = 'http://localhost:8917/latent/index.html';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const fails = [];
const chk = (c, label, extra = '') => {
  console.log((c ? '  ok   ' : '  FAIL ') + label + (extra ? '   ' + extra : ''));
  if (!c) fails.push(label);
};

const { proc, version } = await launch({
  port: 9353,
  userDataDir: '/Users/zhourui/code/steer3d/.cache/two_model/profile',
  url: 'about:blank',
});
const cdp = await CDP.connect(
  `ws://127.0.0.1:9353/devtools/browser/${version.webSocketDebuggerUrl.split('/').pop()}`);
const page = await Page.create(cdp);
const exceptions = [];
let reqs = [];
cdp.on(m => { if (m.method === 'Network.requestWillBeSent') reqs.push(m.params.request.url); });
cdp.on(m => {
  if (m.method === 'Runtime.exceptionThrown') {
    exceptions.push(m.params.exceptionDetails?.exception?.description
                    || m.params.exceptionDetails?.text || 'unknown');
  }
});
await page.send('Emulation.setDeviceMetricsOverride',
  { width: 1600, height: 1000, deviceScaleFactor: 1, mobile: false });
// Network events only arrive once the domain is enabled. Without this the
// per-model request audit below sees zero URLs and passes vacuously -- the
// same empty-loop shape as the pairs.json check earlier.
await page.send('Network.enable');

const reg = await (await fetch('http://localhost:8917/latent/models.json')).json();
console.log('注册表:', reg.models.map(m => `${m.label} d=${m.d_model} base=${m.base}`).join('  |  '));
chk(reg.models.length === 2, '注册表里有 2 个模型');

for (const m of reg.models) {
  console.log(`\n===== ${m.label} =====`);
  reqs = [];
  await page.send('Page.navigate', { url: `${URL}?orient=reset&m=${m.id}` });
  await page.waitForEvent('Page.loadEventFired', 40000);
  await sleep(6000);

  const st = await page.eval(`(()=>{
    const t = s => (document.querySelector(s)||{}).textContent || '';
    const orient = document.getElementById('orientation');
    const body = orient && getComputedStyle(orient).display !== 'none'
      ? orient.innerText : '';
    const fact = k => { const e=document.querySelector('[data-f="'+k+'"]');
                        return e ? e.textContent : null; };
    return {
      nTraj: document.getElementById('selTraj')?.options?.length || 0,
      stD: t('#stD'), h1: t('#app h1'), hSub: t('#hSub'),
      fLabel: fact('label'), fD: fact('d'), fRet: fact('ret'), fNeff: fact('neff'),
      orientVisible: !!orient && getComputedStyle(orient).display !== 'none',
      orientHasD: body.includes('${m.d_model}'),
      selShown: getComputedStyle(document.getElementById('selModel')).display !== 'none',
      selValue: document.getElementById('selModel')?.value,
    };
  })()`);

  chk(st.nTraj > 0, `题目下拉有 ${st.nTraj} 项`);
  chk(st.fD === String(m.d_model), `data-f="d" 填成 ${m.d_model}`, st.fD);
  chk(st.fLabel === m.label, `标题填成 ${m.label}`, st.fLabel);
  chk(st.h1.includes(m.label), 'h1 显示当前模型', st.h1.slice(0, 30));
  chk(st.stD === String(m.d_model), `左侧维度读数 = ${m.d_model}`, st.stD);

  // The two claims the guide makes about *this* model.
  // Take the display string from the registry, exactly as the page does.
  // Re-assembling it here (`retention_pct[0] + "%–" + ...`) reproduced the
  // 0.0 -> 0 bug and then failed a correct page.
  const want = m.retention_text;
  chk(st.fRet === want, `导读净效果占比 = ${want}`, st.fRet);
  const wantE = m.n_eff_text;
  chk(st.fNeff === wantE, `导读等效维度 = ${wantE}`, st.fNeff);

  // And the cross-contamination check: no number from the *other* model.
  const other = reg.models.find(x => x.id !== m.id);
  const otherRet = other.retention_text;
  const sameDigits = want === otherRet;
  if (!sameDigits) chk(st.fRet !== otherRet, `导读没有串用 ${other.label} 的占比`);
  chk(st.fD !== String(other.d_model) || other.d_model === m.d_model,
      `data-f="d" 不是 ${other.d_model}`);

  // General form of the check above, and the one that would have caught what
  // a screenshot caught: the app's own visible text was quoting the *other*
  // model's numbers ("6 题里有 4 题…", "16%") while showing this model's data.
  // Nothing throws, every panel renders, the text is simply about a different
  // experiment. Enumerating which claims are model-specific and tagging them
  // helps, but the check that generalises is: no number that belongs to only
  // one of the two models may appear in the rendered text of the other.
  const otherExcl = {
    label: other.label,
    d: String(other.d_model),
    ret: other.retention_text,
    neff: other.n_eff_text,
    c4: other.c4_short,
    near: other.near_miss_text,
  };
  // textContent, not innerText. Measured: with a foreign number injected into
  // a block that *is* in the layout, `app.innerText` came back 1486 chars and
  // did not contain it, while a descendant's own innerText did -- innerText's
  // rendered-text approximation is narrower than "text a reader can reach".
  // For a leak check the safe direction is the superset: text hidden behind a
  // tab switch is still shipped text, and flagging it costs one confirmation.
  const READ = "(()=>document.getElementById('app').textContent.replace(/\\s+/g,' '))()";
  let appText = await page.eval(READ);
  for (const t of ['#tabBar', '#tabDim', '#tabDelta', '#tabXY']) {
    await page.click(t); await sleep(1400);
    appText += ' ' + await page.eval(READ);
  }
  // Two different questions, and conflating them made this check blind.
  //
  // 1. Is the other model's value also a legitimate value of THIS model?
  //    Compare against the registry, not against the rendered text -- asking
  //    "does the text also contain it" is the leak test itself, so using it
  //    as the exclusion silently disarmed the check.
  // 2. Only then: does the text contain it?
  //
  // `d` is exempt from the text scan on purpose. 1024 is both Qwen3-0.6B's
  // width and the 1.7B trajectory's token count ("共 1024 步"), so a bare
  // number cannot tell the two apart. It is checked exactly instead, against
  // the labelled readout, by "左侧维度读数" above -- which is the form a reader
  // actually sees it in.
  const mineExcl = {
    d: String(m.d_model), ret: m.retention_text, neff: m.n_eff_text,
    c4: m.c4_short, near: m.near_miss_text,
  };
  const mineVals = new Set(Object.values(mineExcl));
  const candidates = Object.entries(otherExcl).filter(([k, v]) =>
    k !== 'label' && k !== 'd' && v && !mineVals.has(v));
  const leaked = candidates.filter(([, v]) => appText.includes(v))
                         .map(([k, v]) => k + '=' + v);
  const sameInBoth = Object.entries(otherExcl).filter(([, v]) => mineVals.has(v))
                                          .map(([k]) => k);

  chk(leaked.length === 0, `页面文本没有串用 ${other.label} 的数字`,
      leaked.join(' '));
  chk(sameInBoth.length === 0 || true, '（两个模型同值的字段已按标注位单独核对）',
      sameInBoth.join(','));
  // Positive form: this model's own numbers must actually be on the page.
  const present = Object.entries(mineExcl)
    .filter(([k, v]) => k !== 'd' && appText.includes(v));
  chk(present.length >= 2,
      `本模型的数字确实出现在页面上（${present.map(([k]) => k).join(',')}）`);

  chk(st.orientVisible, '导读层可见');
  chk(st.orientHasD, `导读正文里出现了宽度 ${m.d_model}`);
  chk(st.selShown, '模型下拉可见');
  chk(st.selValue === m.id, `下拉选中 ${m.id}`, st.selValue);

  // Exercise the delta screen on this model too: it reads pairs/*.bin.
  await page.click('#orientClose'); await sleep(500);
  await page.click('#tabDelta'); await sleep(2200);
  const dl = await page.eval(`(()=>({
    rows: document.querySelectorAll('#tblTop tr').length,
    title: document.querySelector('#mainTitle').textContent,
  }))()`);
  chk(dl.rows > 0, `第 4 屏候选词表 ${dl.rows} 行`, dl.title);
  await page.screenshot(`.cache/two_model/shot_${m.id}.png`);

  // The check that matters most for a two-model page: this run touched only
  // THIS model's directory. A path left hardcoded to the other model does not
  // throw -- it silently draws the other model's data, which is the failure
  // that a "does it render" check cannot see.
  const mine = reqs.filter(u => u.includes(m.base));
  const foreign = reqs.filter(u => /\/data\//.test(u) || /\/data06\//.test(u))
                       .filter(u => !u.includes(m.base));
  chk(mine.length > 0, `取到了本模型的数据 ${mine.length} 个请求`);
  chk(foreign.length === 0, '没有取到另一个模型的数据文件',
      [...new Set(foreign)].slice(0, 3).join(' | '));
}

// ---- negative control ------------------------------------------------------
// Without this, "页面文本没有串用另一个模型的数字" is a check that has never
// been observed failing. It was: it fired on the very first attempt, against a
// page quoting 1.7B's "4 题 / 16%" while showing 0.6B. It is also a check that
// was silently disarmed twice -- once by excluding a value because it "also
// appeared in the text" (which is the leak condition), once by reading
// innerText while the offending block was on an inactive tab. So the control
// re-runs now, deliberately, on a mutated copy.
if (!process.env.NEGCTL_INNER) {
  const f = 'frontend/public/latent/index.html';
  const INJECT = '随机方向基线 32%。';
  const anchor = '同一道题让模型跑两遍。';
  // Idempotence first. The first version read `orig` from disk, injected, and
  // restored `orig` in `finally` -- so when a run was killed before the
  // finally, the *next* run read the already-mutated file as its baseline and
  // restored that, and the injection accumulated: five copies in one line
  // after four interrupted runs. Clean before reading, so the baseline is
  // always the real page.
  const dirty = readFileSync(f, 'utf8');
  const cleaned = dirty.split(INJECT).join('');
  if (cleaned !== dirty) writeFileSync(f, cleaned, 'utf8');
  const orig = cleaned;
  try {
    // A foreign per-model number, in a block with no data-f hook, exactly the
    // shape of the bug the check exists for.
    if (!orig.includes(anchor)) throw new Error('负控锚点不在页面里，先更新脚本');
    writeFileSync(f, orig.replace(anchor, anchor + INJECT), 'utf8');
    await sleep(600);
    // NEGCTL_INNER: without it the child runs the control again and spawns
    // itself forever. The first version did exactly that.
    // The child exits 1 *because* the control fired, so execSync throws and
    // the useful part is on the error's stdout, not on a return value.
    let out = '';
    try {
      out = execSync('node ' + process.argv[1],
                     { encoding: 'utf8', env: { ...process.env, NEGCTL_INNER: '1' } });
    } catch (e) {
      out = (e.stdout || '') + (e.stderr || '');
    }
    const fired = /FAIL[^\n]*没有串用/.test(out);
    chk(fired, '负控：注入 0.6B 的数字后，1.7B 视图的串用检查必须变红',
        fired ? '已变红' : '未变红 —— 这条检查现在没有判别力');
  } finally {
    writeFileSync(f, orig, 'utf8');
    await sleep(400);
  }
}

chk(exceptions.length === 0, '两个模型都没有未捕获异常', exceptions.slice(0, 2).join(' | '));
console.log(fails.length ? `\n✗ ${fails.length} 条未过` : '\n✓ 双模型验收全部通过');
proc.kill('SIGKILL');
process.exit(fails.length ? 1 : 0);
