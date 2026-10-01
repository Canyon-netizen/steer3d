// Final-hash re-verification of the last three UI fixes.
//
// The earlier pass (report.md) endorsed hash 225487af and separately confirmed
// the #layerStory fix on 15b5b5b6. Three fixes landed after both:
//   commit 2373fb6 — pointer names an existing layer; unsteered panel hidden in
//                    screen 4; #pairRow label no longer wraps one glyph per line
// plus the dimension rows moved to flex in d435305.
//
// This script re-runs only what those touches could have broken, against the
// hash that actually ships, and says so in its output. It deliberately does not
// re-run the full 10-item sweep: that is already recorded, and a re-run that
// gets reported as "10/10 again" would blur which version it speaks for.

import { launch, CDP, Page } from '../browser_verify/cdp_client.mjs';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { createHash } from 'node:crypto';

const URL = 'http://localhost:8917/latent/index.html';
const OUT = '.cache/browser_verify3/shots';
const sleep = ms => new Promise(r => setTimeout(r, ms));
mkdirSync(OUT, { recursive: true });

const indexBytes = readFileSync('frontend/public/latent/index.html');
const HASH = createHash('sha256').update(indexBytes).digest('hex');
console.log('index.html sha256:', HASH.slice(0, 16), `(${indexBytes.length} bytes)`);

const fails = [];
const say = (...a) => console.log(a.join(' '));
const chk = (c, label, extra = '') => {
  if (c) say('  ok   ' + label + (extra ? '   ' + extra : ''));
  else { say('  FAIL ' + label + (extra ? '   ' + extra : '')); fails.push(label); }
};

const { proc, version } = await launch({
  port: 9350,
  userDataDir: '/Users/zhourui/code/steer3d/.cache/browser_verify3/profile_final',
  url: 'about:blank',
});
say('chromium:', version.Browser, 'port 9350');
const cdp = await CDP.connect(`ws://127.0.0.1:9350/devtools/browser/${version.webSocketDebuggerUrl.split('/').pop()}`);
const page = await Page.create(cdp);
const exceptions = [];
cdp.on(m => {
  if (m.method === 'Runtime.exceptionThrown') {
    exceptions.push(m.params.exceptionDetails?.exception?.description
                    || m.params.exceptionDetails?.text || 'unknown');
  }
});

await page.nav(URL);
await sleep(4500);

// Enter screen 4 by clicking the real tab, coordinates read from the page.
await page.click('#tabDelta');
await sleep(2500);
const ready = await page.eval(`(()=>{const S=window.__latentState||null; return {
  view: document.querySelector('#tabDelta') ? 'ok' : 'no-tab',
  mainTitle: document.querySelector('#mainTitle')?.textContent,
  sub: document.querySelector('#mainSub')?.textContent,
  selLayer: document.querySelector('#valLayer')?.textContent,
  pairOpts: [...document.querySelectorAll('#selPair option')].map(o=>o.textContent),
};})()`);
say('\n[enter] ' + ready.mainTitle);
chk(/L26/.test(ready.mainTitle || ''), '默认层是 L26（注入点之上第一层）', ready.mainTitle);
chk((ready.pairOpts || []).length === 6, `下拉列出 6 个配对`, (ready.pairOpts || []).length + '');

// ---- Fix 1: the pointer must name a layer that exists --------------------
const avail = JSON.parse(readFileSync('frontend/public/latent/data/pairs/pairs.json', 'utf8'))
  .pairs[0].layers;
const injected = JSON.parse(readFileSync('frontend/public/latent/data/pairs/pairs.json', 'utf8'))
  .pairs[0].inject_layer;
say('\n[fix 1] 注入块指路（可用层 ' + avail.join('/') + '，注入点 L' + injected + '）');

await page.eval(`(()=>{const S=window.__latent; return 0;})()`).catch(() => {});
await page.click('#rngLayer', { dx: 0, dy: 0 }).catch(() => {});

// Move the layer slider with a real drag to the injection layer.
const dragTo = async (target) => {
  const info = await page.eval(`(()=>{const e=document.querySelector('#rngLayer');
    const r=e.getBoundingClientRect(); return {min:+e.min,max:+e.max,w:r.width,h:r.height,
      top:r.top,left:r.left,val:+e.value,thumb:15};})()`);
  const xFor = v => info.left + info.thumb/2 + (v-info.min)/(info.max-info.min)*(info.w-info.thumb);
  const y = info.top + info.h/2;
  await page.mouse('mouseMoved', xFor(info.val), y, { buttons: 0 });
  await page.mouse('mousePressed', xFor(info.val), y);
  for (let i = 1; i <= 6; i++) {
    const v = info.val + (target - info.val) * (i/6);
    await page.mouse('mouseMoved', xFor(v), y);
    await sleep(30);
  }
  await page.mouse('mouseReleased', xFor(target), y);
  await sleep(600);
};
await dragTo(injected);

const inj = await page.eval(`(()=>{
  const side = document.querySelector('#tblTop')?.innerHTML || '';
  const sub  = document.querySelector('#mainSub')?.textContent || '';
  return { sideText: side.replace(/<[^>]+>/g,' ').replace(/\\s+/g,' ').trim().slice(0,400),
           sub, layer: document.querySelector('#valLayer')?.textContent,
           pushed: (side.match(/被推了<\\/td><td class="tok"><b[^>]*>([\\d.]+)%/)||[])[1] || null };
})()`);
say('  侧栏: ' + inj.sideText.slice(0, 200));
const layersNamed = [...(inj.sideText + ' ' + inj.sub).matchAll(/L(\d+)/g)].map(m => +m[1]);
const bogus = layersNamed.filter(L => !avail.includes(L));
chk(bogus.length === 0, '注入块的指路指向真实存在的层',
    bogus.length ? '指向了 L' + bogus.join(',L') : '提到 ' + [...new Set(layersNamed)].join('/'));
chk(!/L21/.test(inj.sideText + inj.sub), '不再出现不存在的 L21');
chk(inj.pushed === '0.00' || inj.pushed === '0.0' || inj.pushed === '0',
    '注入块读数仍精确为 0%', inj.pushed);
chk(/没有任何维度被推动/.test(inj.sideText), '注入块明说没有维度被推动');

// ---- Fix 2: only one problem visible in screen 4 -------------------------
say('\n[fix 2] 第 4 屏不该同时摆两道题');
const twoProbs = await page.eval(`(()=>{
  const tp = document.querySelector('#trajPanel');
  const pp = document.querySelector('#pairRow');
  return { trajPanelDisplay: tp ? getComputedStyle(tp).display : 'missing',
           trajVisible: tp ? tp.getBoundingClientRect().height > 0 : false,
           pairVisible: pp ? pp.getBoundingClientRect().height > 0 : false,
           selPair: document.querySelector('#selPair')?.value,
           selPairText: document.querySelector('#selPair')?.selectedOptions?.[0]?.textContent };
})()`);
chk(twoProbs.trajPanelDisplay === 'none' || !twoProbs.trajVisible,
    '无干预的「题目」面板在第 4 屏已隐藏', 'display=' + twoProbs.trajPanelDisplay);
chk(twoProbs.pairVisible, '配对面板可见', twoProbs.selPairText || '');

// And it must come back on the other screens.
await page.click('#tabXY');
await sleep(1200);
const backOnXY = await page.eval(`(()=>{const tp=document.querySelector('#trajPanel');
  return {display: tp?getComputedStyle(tp).display:'missing',
          visible: tp?tp.getBoundingClientRect().height>0:false,
          opts: document.querySelector('#selTraj')?.options?.length||0};})()`);
chk(backOnXY.visible && backOnXY.opts > 0,
    '切回「隐空间 2D」后无干预题目面板恢复且可选',
    `display=${backOnXY.display} 可选 ${backOnXY.opts} 项`);
await page.click('#tabDelta');
await sleep(1200);

// ---- Fix 3: label no longer one glyph per line ---------------------------
say('\n[fix 3] 「配对题目」标签不应竖排');
const label = await page.eval(`(()=>{const l=document.querySelector('#pairRow label');
  if(!l) return null; const r=l.getBoundingClientRect();
  const cs=getComputedStyle(l);
  return {text:l.textContent.trim(), w:r.width, h:r.height,
          sameRow: (()=>{const s=document.querySelector('#selPair');
            if(!s) return null; const sr=s.getBoundingClientRect();
            return Math.abs(sr.top - r.top) < sr.height*0.6;})()};})()`);
chk(label && label.text === '配对题目', '标签文本完整', label && label.text);
chk(label && label.h < 34, '标签高度 < 34px（不是每字一行）',
    label ? `${label.w.toFixed(0)}×${label.h.toFixed(0)}px` : 'null');
chk(label && label.sameRow, '标签与下拉框同一行');

// ---- Regression spot-checks ----------------------------------------------
say('\n[回归抽查]');
await dragTo(26);
const l26 = await page.eval(`(()=>{const side=document.querySelector('#tblTop')?.innerHTML||'';
  return {pushed:(side.match(/被推了<\\/td><td class="tok"><b[^>]*>([\\d.]+)%/)||[])[1]||null,
          dimrows:document.querySelectorAll('.dimrow').length,
          names:[...document.querySelectorAll('.dimname')].map(e=>e.textContent.trim()),
          bars:[...document.querySelectorAll('.dimbar > i')].map(e=>parseFloat(e.style.width)),
          story:document.querySelector('#layerStory')?.textContent?.trim().slice(0,80)};})()`);
chk(l26.dimrows === 10, 'L26 有 10 行维度', l26.dimrows + ' 行');
chk(l26.bars.every(w => w >= 0 && w <= 100), '条宽全部落在 0–100%',
    l26.bars.length ? Math.min(...l26.bars).toFixed(1) + '–' + Math.max(...l26.bars).toFixed(1) + '%' : '');
chk(new Set(l26.bars.map(b => b.toFixed(0))).size > 1, '条长有区分',
    [...new Set(l26.bars.map(b => b.toFixed(0)))].join(','));
chk(l26.names.every(n => n.length >= 4), '词名不是 1–2 字符残片',
    l26.names.slice(0, 3).map(n => n.slice(0, 18)).join(' / '));
chk(!/L(?!26)\d/.test(l26.story || '') && /不适用|配对/.test(l26.story || ''),
    '「这一层在做什么」跟随当前层', l26.story);

// Out-of-range token slider must still refuse to show a per-step number.
const tokInfo = await page.dragRange('#rngTok', 0, 30);
const oor = await page.eval(`(()=>{const side=document.querySelector('#tblTop')?.innerHTML||'';
  return {text: side.replace(/<[^>]+>/g,' ').replace(/\\s+/g,' ').trim().slice(0,260),
          hasPct: /被推了<\\/td><td class="tok"><b/.test(side)};})()`);
chk(/无对照可比/.test(oor.text), '越界时说明没有可比的对照', oor.text.slice(0, 90));
chk(oor.hasPct === false, '越界时不显示该步的百分数');

await page.screenshot(`${OUT}/final-01-L26-dims.png`);
say('  shot -> final-01-L26-dims.png');
await dragTo(injected);
await page.screenshot(`${OUT}/final-02-L20-inject.png`);
say('  shot -> final-02-L20-inject.png');
await dragTo(26);
await page.click('#tabXY');
await sleep(900);
await page.click('#tabDelta');
await sleep(1200);
await page.screenshot(`${OUT}/final-03-screen4-top.png`);
say('  shot -> final-03-screen4-top.png');

chk(exceptions.length === 0, '无未捕获异常', exceptions.slice(0, 2).join(' | '));

const summary = { hash: HASH, browser: version.Browser, fails, checkedAt: new Date().toISOString() };
writeFileSync('.cache/browser_verify3/result_final.json', JSON.stringify(summary, null, 2));
say('\nhash ' + HASH.slice(0, 16) + ' | ' + (fails.length ? fails.length + ' 项失败: ' + fails.join(' | ') : '全部通过'));
page.close(); cdp.close(); proc.kill('SIGKILL');
process.exit(fails.length ? 1 : 0);
