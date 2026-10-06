// 根页 LayerDerivationPanel 到底停在哪个态，以及「可选的录制列表」存不存在。
import { launch, CDP, Page } from './cdp_client.mjs';
import { mkdirSync } from 'node:fs';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_ltp';
mkdirSync(PROFILE, { recursive: true });
const { proc, version } = await launch({ port: 9473, userDataDir: PROFILE, windowSize: '1600,1000', url: 'about:blank' });
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
await page.send('Runtime.enable'); await page.send('Page.enable');
await page.send('Page.navigate', { url: process.env.T3D_URL || 'http://127.0.0.1:22226/' });
await page.waitForEvent('Page.loadEventFired', 60000).catch(()=>{});
await sleep(6000);
console.log(await page.eval(`JSON.stringify({
  derivation: (document.querySelector('[data-derivation]')||{}).getAttribute
      ? document.querySelector('[data-derivation]').getAttribute('data-derivation') : 'ABSENT',
  derivText: (document.querySelector('[data-derivation]')||{}).innerText || 'ABSENT',
  // 面板叫人「Pick a recording」—— 那选择器在哪？
  pickers: [...document.querySelectorAll('select')].map(s => ({
    id: s.id || '(no-id)', opts: s.options.length,
    label: (s.closest('div')||{}).innerText ? (s.closest('div').innerText||'').slice(0,30) : '' })),
  selIds: [...document.querySelectorAll('select')].map(s=>s.id),
  ready: document.querySelector('[data-derivation]')?.getAttribute('data-derivation'),
  traj: document.querySelector('[data-derivation]')?.getAttribute('data-traj'),
  stepId: document.querySelector('[data-derivation]')?.getAttribute('data-step-id'),
  nLayers: document.querySelector('[data-derivation]')?.getAttribute('data-n-layers'),
  hasStepSlider: !!document.querySelector('[data-deriv-step]'),
  bars: document.querySelectorAll('[data-derivation="ready"] rect').length,
  defaultNote: (document.querySelector('[data-deriv-default]')||{}).innerText || 'ABSENT',
  // 后端不在时，那颗状态点必须说 disconnected
  connDot: (()=>{const t=document.body.innerText||'';
    const m=t.match(/\b(connected|disconnected)\b/); return m?m[1]:'ABSENT';})(),
}, null, 1)`));
// logit_lens.json 本身有没有记录可选
const lens = await page.eval(`(async()=>{const r=await fetch('/latent/data/logit_lens.json');
  const j=await r.json(); return JSON.stringify({n:(j.trajectories||[]).length,
    first3:(j.trajectories||[]).slice(0,3).map(t=>t.id)});})()`);
console.log('logit_lens.json：', lens);
try { proc.kill('SIGKILL'); } catch(e) {}
process.exit(0);
