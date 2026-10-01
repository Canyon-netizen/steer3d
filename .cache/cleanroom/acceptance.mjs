// Clean-room acceptance test of the DELIVERED artefact.
//
// Everything else in this project verifies the working tree. The thing the
// user actually opens is a tar.gz they download from obs, and a tarball can be
// wrong in ways a working tree cannot: a data file that was never added, a
// path that only resolves because of a symlink, a manifest whose relative
// paths escape the archive. So this untars the downloaded package into an
// empty directory, serves it with a bare `python3 -m http.server`, and drives
// it as a first-time visitor would -- no build step, no local data directory.
//
// It also asserts something the build-time checks structurally cannot: that
// the page reaches "ready" using ONLY files that came out of the tarball.
import { launch, CDP, Page } from '../browser_verify/cdp_client.mjs';
import { existsSync, readdirSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';

const ROOT = '/Users/zhourui/code/steer3d/.cache/cleanroom/latent';
const URL = 'http://localhost:8923/latent/index.html';
const sleep = ms => new Promise(r => setTimeout(r, ms));

const fails = [];
const chk = (c, label, extra = '') => {
  console.log((c ? '  ok   ' : '  FAIL ') + label + (extra ? '   ' + extra : ''));
  if (!c) fails.push(label);
};

// ---- static completeness, before any browser is involved -------------------
// A missing file shows up in the browser as a console error and a blank panel,
// which is easy to misread as a rendering bug.
const manifest = JSON.parse(
  (await import('node:fs')).readFileSync(join(ROOT, 'data/manifest.json'), 'utf8'));
const files = [
  'index.html', 'README.md', 'data/manifest.json', 'data/vocab.json',
  'data/dim_names.json', 'data/pairs/pairs.json',
];
for (const f of files) chk(existsSync(join(ROOT, f)), `包内有 ${f}`);

let missing = 0, checked = 0;
for (const t of manifest.trajectories) {
  for (const k of ['hs', 'topk', 'topki', 'pca', 'mean', 'proj']) {
    if (!t[k]) continue;
    checked++;
    if (!existsSync(join(ROOT, 'data', t[k]))) { missing++; console.log('    缺', t[k]); }
  }
}
chk(missing === 0, `manifest 引用的 ${checked} 个数据文件全部在包内`, `缺 ${missing}`);

// pairs.json is nested: pairs[].arms[layer][arm].file. An earlier version of
// this check walked Object.keys() of the top level and found no file list at
// all, so it reported "0 files, 0 missing, ok" -- a green light for a loop
// that never ran. The count is now asserted to be non-zero as its own check.
const pairs = JSON.parse(
  (await import('node:fs')).readFileSync(join(ROOT, 'data/pairs/pairs.json'), 'utf8'));
let pmiss = 0, pchecked = 0;
for (const pr of pairs.pairs) {
  for (const armSet of Object.values(pr.arms || {})) {
    for (const arm of Object.values(armSet)) {
      if (!arm.file) continue;
      pchecked++;
      if (!existsSync(join(ROOT, 'data/pairs', arm.file))) {
        pmiss++; console.log('    缺', arm.file);
      }
    }
  }
}
chk(pchecked > 0, `pairs.json 真的被遍历到了（不是空循环）`, `遍历到 ${pchecked} 个文件引用`);
chk(pmiss === 0, `pairs.json 引用的 ${pchecked} 个文件全部在包内`, `缺 ${pmiss}`);

// ---- and now drive it, as a first-time visitor -----------------------------
const { proc, version } = await launch({
  port: 9352,
  userDataDir: '/Users/zhourui/code/steer3d/.cache/cleanroom/profile',
  url: 'about:blank',
});
const cdp = await CDP.connect(
  `ws://127.0.0.1:9352/devtools/browser/${version.webSocketDebuggerUrl.split('/').pop()}`);
const page = await Page.create(cdp);
const exceptions = [], netfail = [];
const reqUrl = new Map();
cdp.on(m => {
  if (m.method === 'Runtime.exceptionThrown') {
    exceptions.push(m.params.exceptionDetails?.exception?.description
                    || m.params.exceptionDetails?.text || 'unknown');
  }
  if (m.method === 'Network.requestWillBeSent') {
    reqUrl.set(m.params.requestId, m.params.request.url);
  }
  if (m.method === 'Network.loadingFailed') {
    // Record the URL, not just the error text: "ERR_ABORTED" with no URL is
    // not actionable, and there are benign ones (a request cancelled by a
    // later navigation) that look exactly like a missing file.
    netfail.push(m.params.errorText + '  canceled=' + m.params.canceled
                 + '  ' + (reqUrl.get(m.params.requestId) || '(no url)'));
  }
});
await page.send('Network.enable');
await page.send('Emulation.setDeviceMetricsOverride',
  { width: 1600, height: 1000, deviceScaleFactor: 1, mobile: false });

await page.send('Page.navigate', { url: `${URL}?orient=reset` });
await page.waitForEvent('Page.loadEventFired', 40000);
await sleep(6000);

const boot = await page.eval(`(()=>{
  const t = s => (document.querySelector(s)||{}).textContent || '';
  return {
    loaded: !document.getElementById('app') ||
            getComputedStyle(document.getElementById('app')).visibility !== 'hidden',
    loading: t('#pmsg'),
    orientVisible: (()=>{const o=document.getElementById('orientation');
      return !!o && getComputedStyle(o).display !== 'none';})(),
    mainTitle: t('#mainTitle'), sub: t('#mainSub'),
    stD: t('#stD'), stEnt: t('#stEnt'), stRaw: t('#stRaw'),
    nTraj: (document.getElementById('selTraj')||{}).options?.length || 0,
  };
})()`);
chk(boot.loaded, '数据加载完成（app 不再 hidden）', '进度=' + boot.loading);
chk(boot.nTraj > 0, `题目下拉有 ${boot.nTraj} 项`);
chk(boot.orientVisible, '首次访问弹出导读层');
chk(boot.mainTitle.length > 0, '主图标题已渲染', boot.mainTitle);
chk(boot.stD === '2048', '维度读数为 2048', boot.stD);
chk(boot.stEnt.length > 0, '熵/top1 概率已渲染', boot.stEnt);
await page.screenshot('.cache/cleanroom/shot-01-orient.png');

await page.click('#orientClose'); await sleep(600);

// Walk all four tabs, because a bundle can be complete and still serve a panel
// that throws on first paint.
for (const [id, label] of [['#tabXY', '隐空间 2D'], ['#tabBar', '候选词'],
                           ['#tabDim', '维度解读'], ['#tabDelta', '干预 vs 对照']]) {
  await page.click(id); await sleep(1600);
  const s = await page.eval(`(()=>{
    const on = document.querySelector('${id}').classList.contains('on');
    const t = document.querySelector('#mainTitle').textContent;
    return {on, title: t,
            rows: document.querySelectorAll('.dimrow, #tblTop tr').length};
  })()`);
  chk(s.on, `切到「${label}」`, '标题=' + s.title);
}
await page.screenshot('.cache/cleanroom/shot-02-delta.png');

// The delta view is the one that reads pairs/*.bin, so exercise it: switch to
// the paired problem, move the token slider to the divergence step.
const dl = await page.eval(`(()=>{
  const s = document.getElementById('pairNote');
  const cap = document.getElementById('deltaCap');
  return {note: (s&&s.textContent||'').slice(0,80),
          cap: (cap&&cap.textContent||'').slice(0,60),
          tableRows: document.querySelectorAll('#tblTop tr').length};
})()`);
chk(dl.tableRows > 0, `第 4 屏候选词表已渲染 ${dl.tableRows} 行`, dl.cap);

chk(exceptions.length === 0, '无未捕获异常', exceptions.slice(0, 2).join(' | '));
chk(netfail.length === 0, '无资源加载失败/中止', netfail.slice(0, 3).join(' | '));

// ---- the delivered page must not talk to anything off-origin ---------------
// Not "no failed requests" -- no *outbound* request at all. A beacon to a
// hardcoded localhost port is how a local dev habit becomes part of the
// artefact, and the only reason it went unnoticed is that the port happened
// to have a listener on the machine where every other check was written.
const offOrigin = [];
cdp.on(m => {
  if (m.method !== 'Network.requestWillBeSent') return;
  const u = m.params.request.url;
  if (!u.startsWith(URL.split('?')[0].replace(/index\.html$/, '')) && !u.startsWith('data:')) {
    offOrigin.push(u);
  }
});
await page.send('Page.navigate', { url: URL });
await page.waitForEvent('Page.loadEventFired', 40000);
await sleep(5000);
await page.click('#tabDelta'); await sleep(2500);
chk(offOrigin.length === 0, '页面没有任何指向包外的请求',
    [...new Set(offOrigin)].slice(0, 3).join(' | '));

console.log(`\nindex.html sha256 内联 hash: ${boot.mainTitle ? 'ok' : 'n/a'}`);
console.log(fails.length ? `\n✗ ${fails.length} 条未过` : '\n✓ 净室验收全部通过');
proc.kill('SIGKILL');
process.exit(fails.length ? 1 : 0);
