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

chk(exceptions.length === 0, '两个模型都没有未捕获异常', exceptions.slice(0, 2).join(' | '));
console.log(fails.length ? `\n✗ ${fails.length} 条未过` : '\n✓ 双模型验收全部通过');
proc.kill('SIGKILL');
process.exit(fails.length ? 1 : 0);
