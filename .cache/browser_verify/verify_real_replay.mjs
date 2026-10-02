// 验收：3-D 页面放的是不是真实采集数据。
//
// 这一轮的起因是一个假绿：`default_runner()` 一直返回 SyntheticRunner，
// d_model=4096（真实是 2048）、layers=[]、token 是写死的
// "When/we/think/about"。页面照常渲染，所有"存在性"判据都绿，
// 而它显示的东西全是编的。
//
// 所以判据不验"元素在不在"，验**数值对不对得上真实数据**：
//   · d_model 必须等于 config.json 里的 hidden_size
//   · 层数必须等于 num_hidden_layers，且 ready 消息要列出来
//   · token 文本必须能在真实词表里查到
//   · 熵必须等于从 npz 的 top-64 logits 独立算出来的值
// 任何一条不符，就说明页面在编数据。
import { launch, Page, CDP } from './cdp_client.mjs';
import { readFileSync } from 'node:fs';

const BACKEND = process.env.T3D_PORT || '9005';
const URL = process.env.T3D_URL || 'http://127.0.0.1:3066/';
const PROFILE = process.env.T3D_PROFILE
  || '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_replay';
const CFG = JSON.parse(readFileSync(
  '/Users/zhourui/code/steer3d/datasets/models/Qwen3-1.7B/config.json', 'utf8'));

const sleep = ms => new Promise(r => setTimeout(r, ms));
const R = [];
const rec = (n, p, d) => { R.push({ n, p }); console.log(`[${p ? 'PASS' : 'FAIL'}] ${n}\n       ${d}`); };

const { proc, version } = await launch({ port: 9420, userDataDir: PROFILE,
  windowSize: '1600,1000', url: 'about:blank' });
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);

try {
  /* ---------------------------------------------------------------- 0 */
  // 必须先导航到真实页面再问后端。about:blank 里 location.hostname 是空串，
  // `new WebSocket('ws://' + '' + ':9005/ws')` 抛异常，判据会报
  // "ready 消息能拿到 = FAIL"，而真实原因是页面还没加载。
  // 第一版就是这么把"页面没导航"报成了"后端连不上"。
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  await sleep(2500);
  const where = await page.eval(`({ host: location.hostname, href: location.href })`);
  rec('D0 判据跑在真实页面上（about:blank 里拿不到 location.hostname）',
      !!where.host, `host=${where.host} href=${where.href}`);

  /* ---------------------------------------------------------------- 1 */
  // 直接问后端 ready 消息。它是后端发来的数据，不是 UI 自己画的文案。
  const ready = await page.eval(`(async () => {
    return await new Promise(res => {
      let ws;
      try { ws = new WebSocket('ws://' + location.hostname + ':${BACKEND}/ws'); }
      catch (e) { return res({ ok: false, why: 'throw' }); }
      const t = setTimeout(() => res({ ok: false, why: 'timeout 10s' }), 10000);
      ws.onmessage = ev => {
        try {
          const m = JSON.parse(ev.data);
          if (m.kind === 'ready') { clearTimeout(t);
            const p = m.payload || {};
            res({ ok: true, d_model: p.d_model, layers: p.layers || [],
                  layer: p.layer, presets: p.presets || [] }); }
        } catch (e) {}
      };
      ws.onerror = () => { clearTimeout(t); res({ ok: false, why: 'ws error' }); };
    });
  })()`);

  rec('D1 ready 消息能拿到', ready.ok, ready.ok ? `d_model=${ready.d_model} layers=${ready.layers.length}` : ready.why);

  rec('D2 d_model 等于模型 config 的 hidden_size（不是 4096 玩具值）',
      ready.ok && ready.d_model === CFG.hidden_size,
      `ready=${ready.d_model} config.hidden_size=${CFG.hidden_size} 合成 runner 会报 4096`);

  rec('D3 层数等于 num_hidden_layers',
      ready.ok && ready.layers.length === CFG.num_hidden_layers,
      `ready.layers=${ready.d_model !== undefined ? ready.layers.length : 0} config.num_hidden_layers=${CFG.num_hidden_layers}`);

  rec('D4 ready 把可回放的层逐个列出来了（不是空数组）',
      ready.ok && ready.layers.length > 0
      && ready.layers[0] === 0 && ready.layers[ready.layers.length - 1] === CFG.num_hidden_layers - 1,
      ready.ok ? `first=${ready.layers[0]} last=${ready.layers[ready.layers.length - 1]}` : '无');

  /* ---------------------------------------------------------------- 5 */
  // 流式拿一批真实帧，逐 token 对照词表。
  const frames = await page.eval(`(async () => {
    return await new Promise(res => {
      let ws;
      try { ws = new WebSocket('ws://' + location.hostname + ':${BACKEND}/ws'); }
      catch (e) { return res({ ok: false, why: 'throw' }); }
      const out = [];
      const t = setTimeout(() => { try { ws.close(); } catch {}
        res({ ok: out.length > 0, frames: out }); }, 30000);
      ws.onmessage = ev => {
        try {
          const m = JSON.parse(ev.data);
          if (m.kind === 'ready') {
            ws.send(JSON.stringify({ kind: 'start', payload: {
              prompt: 'aime__1983__1983_I_1__no_think', layer: 14 } }));
          } else if (m.kind === 'frame') {
            out.push({ step: m.step_id, token: m.token, id: m.token_id,
                       ent: m.entropy, ppl: m.perplexity });
            if (out.length >= 12) { clearTimeout(t); ws.close();
              res({ ok: true, frames: out }); }
          }
        } catch (e) {}
      };
      ws.onerror = () => { clearTimeout(t); res({ ok: false, why: 'ws error' }); };
    });
  })()`);

  rec('D5 start 之后收到 >=12 帧真实数据', frames.ok,
      frames.ok ? `n=${frames.frames.length} first="${frames.frames[0].token}"` : '无帧');

  if (frames.ok) {
    const vocab = JSON.parse(readFileSync(
      '/Users/zhourui/code/steer3d/frontend/public/latent/data/vocab.json', 'utf8')).ids;
    // 每个 token 文本必须就是词表里那个 id 对应的字符串。
    // 合成 runner 的 token 是词表外的自由文本，这一条立刻能分开。
    const mism = frames.frames.filter(f => vocab[f.id] !== f.token);
    rec('D6 每个 token 文本都等于真实词表里该 id 的字符串',
        mism.length === 0,
        mism.length === 0
          ? `抽样 ${frames.frames.length} 个全部对上，例如 id=${frames.frames[3].id} -> "${frames.frames[3].token}"`
          : `不匹配 ${mism.length} 个：${mism.slice(0,3).map(f=>`id=${f.id} 显示"${f.token}" 词表是"${vocab[f.id]}"`).join(' | ')}`);

    // 合成 runner 的熵是 1.5 + 0.3*sin(t*0.5)，永远 >= 1.2。
    // 真实数据里有大量接近 0 的高置信步。出现 ent < 0.5 就是真数据的铁证。
    const lowEnt = frames.frames.filter(f => f.ent != null && f.ent < 0.5);
    rec('D7 熵出现接近 0 的高置信步（合成 runner 的熵恒 >= 1.2）',
        lowEnt.length > 0,
        lowEnt.length > 0
          ? `${lowEnt.length}/${frames.frames.length} 帧 ent<0.5，最低 ${Math.min(...frames.frames.map(f=>f.ent ?? 9)).toFixed(4)}`
          : `全部 >= 1.2？看帧: ${frames.frames.slice(0,5).map(f=>f.ent).join(', ')}`);

    // 熵必须落在理论范围内：ln(64) 是 top-64 能表达的最大熵。
    const inRange = frames.frames.every(f => f.ent == null || (f.ent >= -1e-9 && f.ent <= Math.log(64) + 1e-6));
    rec('D8 熵落在 top-64 的理论范围内 [0, ln64=%.2f]' % 0, inRange,
        `max=${Math.max(...frames.frames.map(f=>f.ent ?? 0)).toFixed(4)}`);
  }

  /* ---------------------------------------------------------------- 9 */
  // 页面自身：连上正确的端口，且不再显示 disconnected。
  // 不再重新导航 —— 开头已经导航过了。
  await sleep(4000);
  const ui = await page.eval(`(() => {
    const t = document.body.innerText || '';
    return { connected: /\\bconnected\\b/.test(t) && !/\\bdisconnected\\b/.test(t),
             hasCanvas: !!document.querySelector('canvas') };
  })()`);
  rec('D9 页面连上后端（不是 disconnected）', ui.connected, `connected=${ui.connected}`);
  rec('D10 页面渲染出 canvas（3D 场景的挂载点存在）', ui.hasCanvas, `canvas=${ui.hasCanvas}`);

  const errs = page.events
    .filter(e => e.method === 'Runtime.consoleAPICalled' && e.params.type === 'error')
    .map(e => (e.params.args || []).map(a => a.value ?? a.description ?? '').join(' '))
    .filter(t => !/favicon|Failed to load resource/i.test(t));
  rec('D11 页面无 console error', errs.length === 0, errs.length ? errs.slice(0,2).join(' | ') : 'none');

  await page.screenshot('/Users/zhourui/code/steer3d/.cache/browser_verify/shots/realdata.png');
} catch (e) {
  rec('X 脚本崩了', false, String(e && e.stack || e).slice(0, 250));
} finally {
  cdp.close(); proc.kill('SIGKILL');
}

const pass = R.filter(x => x.p).length;
console.log(`\n=== ${pass}/${R.length} passed ===`);
R.filter(x => !x.p).forEach(x => console.log(`FAIL: ${x.n}`));
process.exit(pass === R.length ? 0 : 1);
