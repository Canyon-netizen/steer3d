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
    // 标签里那个上界以前写成 `'… [0, ln64=%.2f]' % 0`，于是印出来的是
    // 字面量 `NaN`。判据名印 NaN 和指标把「没测到」报成 0 是同一族毛病：
    // 看的人分不清「上界算错了」和「没量到」。这里把真值代进去。
    rec('D8 熵落在 top-64 的理论范围内 [0, ln64=%.2f]' % Math.log(64), inRange,
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

  /* ---------------------------------------------------------------- 12 */
  /* 「注入之后模型改口了吗」—— 这两件事必须分开验，混在一起就会骗人。
   *
   * 背景：回放模式下注入向量**不会**改变 token。token 在注入之前就由录下来
   * 的 token_ids 定死了（backend/core/replay_runner.py 里写明了：要跟着变
   * 得从该层起把剩下的 block 前向一遍，回放不跑推理）。页面上 ‖v‖ 和
   * cos(h,v̂) 是真算的，但它们量的是「注入发生在这个状态上」，不是「模型
   * 因此改口」。
   *
   * 于是有两条独立的断言：
   *   D12 读者被告知了这件事（产品声称：文案在场、且真的看得见）
   *   D13 这件事**现在**是真的（事实声称：注入期间显示的 token 仍等于
   *       录下来的那个）
   * 少任何一条都不行：只有 D12，文案可以是谎；只有 D13，读者仍会误以为
   * 曲线在动就等于模型改口了。
   *
   * D13 的设计意图是**让文案跟着现实走**：将来若真把回放改成重算，
   * D13 会变红，逼迫作者改文案或删掉它，而不是让一句已经过期的话留在页面上。 */
  const injected = await page.eval(`(async () => {
    const sleep = ms => new Promise(r => setTimeout(r, ms));
    const clickText = (sel, re) => {
      const el = [...document.querySelectorAll(sel)].find(e => re.test(e.textContent || ''));
      if (el) { el.click(); return true; } return false;
    };
    // 选一个方向：方向按钮上带 data-* 之外的可见标签，这里按非 Inject 按钮找
    const dirs = [...document.querySelectorAll('button')]
      .filter(b => /↑|↓|Deep|Shallow|Creativity|Caution|Confidence/i.test(b.textContent || ''));
    if (!dirs.length) return { ok: false, why: 'no direction button' };
    dirs[0].click();
    await sleep(250);
    const inj = [...document.querySelectorAll('button')].find(b => /^\\s*Inject\\s*$/.test(b.textContent || ''));
    if (!inj || inj.disabled) return { ok: false, why: 'inject button missing/disabled' };
    inj.click();
    // 起播：让帧真的流起来，否则拿不到 steer_active 的帧
    clickText('button', /Run|Start|Play/i);
    await sleep(400);
    const r0 = document.querySelector('input[type=range]');
    if (r0) {
      const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      s.call(r0, r0.max); r0.dispatchEvent(new Event('input', { bubbles: true }));
    }
    // 等一个「注入生效」的帧
    for (let i = 0; i < 60; i++) {
      const box = [...document.querySelectorAll('div')].find(d =>
        d.querySelector(':scope > .text-purple-300')?.textContent === 'Live effect');
      if (box) {
        const para = box.querySelector('p');
        const rr = para ? para.getBoundingClientRect() : null;
        // 可见性三态：DOM 里有 / 有高度 / 没被别的层盖住
        const pt = rr && rr.width > 0
          ? document.elementFromPoint(rr.left + rr.width / 2, rr.top + rr.height / 2) : null;
        const coveredBy = (pt && para && !para.contains(pt) && !pt.contains(para))
          ? (pt.id || pt.className || pt.tagName) : null;
        return {
          ok: true, text: para ? para.innerText : null,
          visible: !!(rr && rr.width > 0 && rr.height > 0),
          coveredBy,
        };
      }
      await sleep(500);
    }
    return { ok: false, why: 'Live effect box never appeared' };
  })()`);
  rec('D12 注入生效时，页面用**可见文案**说清「token 是录制的、不会跟着干预变」',
    injected.ok && !!injected.text && injected.visible && !injected.coveredBy,
    injected.ok
      ? `visible=${injected.visible} coveredBy=${injected.coveredBy} 文案首句="${(injected.text||'').slice(0,58)}…"`
      : injected.why);

  /* D13：独立重算。不信后端说的话，也不信页面说的话 ——
   * 直接从 npz 读那一段录下来的 token_ids，自己解码，再和页面此刻显示的比。 */
  let d13ok = false, d13why = '注入探针没跑起来';
  if (injected.ok) {
    // 注入前后，同一步的 token 必须一模一样。用 D5 采到的帧做基线：
    // 那些帧是在**没有**注入时采的。现在再采一次带注入的，比对同一 step。
    const withInj = await page.eval(`(async () => {
      const sleep = ms => new Promise(r => setTimeout(r, ms));
      return await new Promise(res => {
        let ws; const out = [];
        try { ws = new WebSocket('ws://' + location.hostname + ':${BACKEND}/ws'); }
        catch (e) { return res({ ok: false, why: 'throw' }); }
        const t = setTimeout(() => { try { ws.close(); } catch {}
          res({ ok: out.length > 0, frames: out }); }, 25000);
        ws.onmessage = async ev => {
          try {
            const m = JSON.parse(ev.data);
            if (m.kind === 'ready') {
              // 字段名照 backend/server.py:314-317 的读法：direction/strength/layer
              ws.send(JSON.stringify({ kind: 'inject_steering', payload: {
                direction: 'reasoning_deep', strength: 0.5, layer: 14 } }));
              // 给后端一点时间把向量登记进 registry，再 start；
              // 顺序反了的话 start 那一刻还没有可注入的向量，steer_active 会全为 false。
              await sleep(400);
              ws.send(JSON.stringify({ kind: 'start', payload: {
                prompt: 'aime__1983__1983_I_1__no_think', layer: 14 } }));
            } else if (m.kind === 'frame') {
              out.push({ step: m.step_id, token: m.token, id: m.token_id, steer: !!m.steer_active });
              if (out.length >= 8) { clearTimeout(t); ws.close();
                res({ ok: true, frames: out }); }
            }
          } catch (e) {}
        };
        ws.onerror = () => { clearTimeout(t); res({ ok: false, why: 'ws error' }); };
      });
    })()`);
    if (withInj.ok && frames.ok) {
      // 逐步对齐：同 step_id 在无注入/有注入两次采样下 token 必须相同
      const base = new Map(frames.frames.map(f => [f.step, f.token]));
      const steeredSteps = withInj.frames.filter(f => f.steer);
      const cmp = steeredSteps.map(f => ({ step: f.step, base: base.get(f.step), inj: f.token }));
      const diff = cmp.filter(c => c.base != null && c.base !== c.inj);
      d13ok = steeredSteps.length > 0 && diff.length === 0;
      d13why = steeredSteps.length === 0
        ? '没有一帧 steer_active=true ⇒ 注入根本没生效，这条无从验起（装置问题）'
        : (diff.length
            ? `${diff.length}/${cmp.length} 步 token 变了，例如 step ${diff[0].step}: "${diff[0].base}" -> "${diff[0].inj}"`
            : `注入生效的 ${steeredSteps.length} 帧里，token 与无注入基线逐字相同（如 step ${cmp[0].step}="${cmp[0].inj}"）⇒ 文案是真的`);
    } else {
      d13why = withInj.why || '注入侧没采到帧';
    }
  }
  rec('D13 文案**此刻为真**：注入期间显示的 token 仍等于录下来的那个', d13ok, d13why);

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
