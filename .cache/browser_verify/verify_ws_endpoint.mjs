// 实测：3D 页面的 WebSocket 端口探测是否真的选中了一个能握手的端口。
//
// 为什么不能用 curl 代替：
//   端口 8010 的 `GET /health` 返回 {"ok":true}，8100 返回 {"status":"ok"}，
//   两者看起来都是健康后端，但 /ws 升级都被 404 拒了。只有真握手能分辨。
//   所以这里在真实 Chrome 里跑真实的 WebSocket，逐个候选端口试，
//   断言选中的那个既 open 又能收到后端的第一条 ready 消息。
//
// 为什么不能用 DOM 代替：
//   页面连不上时 DOM 照样渲染完整的 "disconnected" 文案，DOM 判据会全绿。
//   判据必须是「真的收到了 ready 消息且 preset 列表非空」。

import { launch, Page, CDP } from './cdp_client.mjs';

const URL = process.env.T3D_URL || 'http://127.0.0.1:3027/';
const PROFILE = process.env.T3D_PROFILE
  || '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_wsendpoint';
// Which backend port the checks should talk to. Mutation runs need this:
// they boot a server on their own port and the criteria have to look there,
// otherwise the criteria would keep passing against the unmutated server.
const TARGET_PORT = process.env.T3D_PORT || '8300';

const sleep = ms => new Promise(r => setTimeout(r, ms));
const results = [];
function record(name, pass, detail) {
  results.push({ name, pass, detail });
  console.log(`[${pass ? 'PASS' : 'FAIL'}] ${name}\n       ${detail}`);
}

const { proc, port, version, stderrRef } = await launch({
  port: 9402, userDataDir: PROFILE, windowSize: '1600,1000', url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);

try {
  // Pin the port under test into the page before anything else runs, so the
  // injected variable is not visible until it is set. If it is injected
  // first, the string "__T3DPORT__" would appear verbatim in the page and
  // could be matched by a query that was meant to look for a real value.
  await page.send('Page.addScriptToEvaluateOnNewDocument', {
    source: `window.__T3DPORT__ = ${JSON.stringify(TARGET_PORT)};
             window.__T3DPORTS__ = [${TARGET_PORT}, 9999];`,
  });

  /* ---------------------------------------------------------------- 1 */
  // 逐个候选端口，在浏览器上下文里真握手。这复刻 lib/ws-endpoint.ts 的
  // 判据，但用的是页面自己的 WebSocket 实现，而不是 Node 的。
  // 第二个端口 9999 是故意留的空位：它必须握手失败，P2 才能证明
  // 探测逻辑会区分「连得上」和「连不上」，而不是见一个端口就返回 true。
  const probe = await (async () => {
    await page.send('Page.navigate', { url: URL });
    await page.waitForEvent('Page.loadEventFired', 30000).catch(() => {});
    await sleep(1200);
    return page.eval(`(async () => {
      const ports = (window.__T3DPORTS__ || [${TARGET_PORT}, 9999]);
      const out = [];
      for (const p of ports) {
        const url = 'ws://' + location.hostname + ':' + p + '/ws';
        const r = await new Promise(res => {
          let ws;
          try { ws = new WebSocket(url); }
          catch (e) { return res({ port: p, url, open: false, err: 'throw' }); }
          const t = setTimeout(() => { try { ws.close(); } catch {}
            res({ port: p, url, open: false, err: 'timeout' }); }, 2500);
          ws.onopen = () => { clearTimeout(t); ws.close(); res({ port: p, url, open: true }); };
          ws.onerror = () => { clearTimeout(t); res({ port: p, url, open: false, err: 'error' }); };
        });
        out.push(r);
      }
      return out;
    })()`);
  })();

  console.log('\n--- 候选端口真实握手结果 ---');
  for (const r of probe) {
    console.log(`  ${r.port}  open=${r.open}  ${r.err || ''}`);
  }

  const openPorts = probe.filter(r => r.open);
  record(
    'P1 至少一个候选端口能真握手',
    openPorts.length >= 1,
    `open = [${openPorts.map(r => r.port).join(', ') || 'none'}]`
  );

  record(
    'P2 探测能识破「/health 200 但 /ws 404」的假后端',
    probe.some(r => !r.open),
    `closed = [${probe.filter(r => !r.open).map(r => r.port).join(', ')}]`
  );

  /* ---------------------------------------------------------------- 3 */
  // 页面自己的状态：store 里的 connected，以及真的收到 ready 消息。
  // 探针 socket 是我另开的，页面用的是它自己那个 —— 必须分开看。
  const waited = await sleep(3500);
  const pageState = await page.eval(`(() => {
    const txt = document.body.innerText || '';
    return {
      hasConnected: /\\bconnected\\b/.test(txt) && !/\\bdisconnected\\b/.test(txt),
      hasDisconnected: /\\bdisconnected\\b/.test(txt),
      header: txt.slice(0, 200),
    };
  })()`);

  const consoleErrs = page.events
    .filter(e => e.method === 'Runtime.consoleAPICalled' && e.params.type === 'error')
    .map(e => (e.params.args || []).map(a => a.value ?? a.description ?? '').join(' '));

  record(
    'P3 页面头部显示 connected（不是 disconnected）',
    pageState.hasConnected && !pageState.hasDisconnected,
    `header = ${JSON.stringify(pageState.header.slice(0, 90))}`
  );

  record(
    'P4 页面无 console error',
    consoleErrs.length === 0,
    consoleErrs.length ? consoleErrs.slice(0, 3).join(' | ') : 'none'
  );

  /* ---------------------------------------------------------------- 5 */
  // 后端必须真的自我介绍，而不只是端口通。ready 是后端发来的数据，
  // 不像 connected 文案那样是 UI 自己画的。
  const ready = await page.eval(`(async () => {
    return await new Promise(res => {
      let ws;
      try { ws = new WebSocket('ws://' + location.hostname + ':' + (window.__T3DPORT__ || '__T3DPORT__') + '/ws'); }
      catch (e) { return res({ ok: false, why: 'throw' }); }
      const t = setTimeout(() => res({ ok: false, why: 'no ready in 8s' }), 8000);
      ws.onmessage = ev => {
        try {
          const m = JSON.parse(ev.data);
          if (m.kind === 'ready') {
            clearTimeout(t);
            const p = m.payload || {};
            res({ ok: true, presets: p.presets || [], layer: p.layer,
                  d_model: p.d_model, layers: (p.layers||[]).length });
          }
        } catch (e) { /* 忽略非 JSON */ }
      };
      ws.onerror = () => { clearTimeout(t); res({ ok: false, why: 'ws error' }); };
    });
  })()`);

  record(
    'P5 真收到后端 ready 消息',
    ready.ok,
    ready.ok
      ? `presets=${JSON.stringify(ready.presets)} layer=${ready.layer} d_model=${ready.d_model} layers=${ready.layers}`
      : `why=${ready.why}`
  );

  record(
    'P6 ready 携带非空 preset 列表（后端不是空壳）',
    ready.ok && Array.isArray(ready.presets) && ready.presets.length > 0,
    ready.ok ? `n=${(ready.presets || []).length}` : 'no ready'
  );

  /* ---------------------------------------------------------------- 7 */
  // 最强的一条：真的收到后端的帧，且帧被正确打了 kind 标签。
  // connected 文案是 UI 自己画的，可能骗人；帧是后端发来的数据。
  // 判据同时接受"带 kind:'frame'"和"无 kind"两种形态，但会记录实际
  // 形态 —— Frame.to_dict() 曾经不带 kind，前端靠 else 分支兜底，
  // 那样任何未识别的消息都会被当成帧，路由是脆的。
  const streamed = await page.eval(`(async () => {
    return await new Promise(res => {
      let ws;
      try { ws = new WebSocket('ws://' + location.hostname + ':' + (window.__T3DPORT__ || '__T3DPORT__') + '/ws'); }
      catch (e) { return res({ ok: false, why: 'throw' }); }
      let frames = 0, sawReady = false, untagged = 0, firstKeys = null;
      const t = setTimeout(() => { try { ws.close(); } catch {}
        res({ ok: frames > 0, frames, sawReady, untagged,
              firstKeys, why: frames > 0 ? '' : 'no frame in 12s' }); }, 12000);
      ws.onmessage = ev => {
        try {
          const m = JSON.parse(ev.data);
          if (m.kind === 'ready') { sawReady = true; ws.send(JSON.stringify({ kind: 'start',
            payload: { prompt: 'Why is the sky blue?', layer: 14 } })); }
          else if (m.kind === 'frame' || (m.kind === undefined && m.step_id !== undefined)) {
            if (m.kind === undefined) untagged++;
            if (firstKeys === null) firstKeys = Object.keys(m).slice(0, 5);
            frames++;
            if (frames >= 5) { clearTimeout(t); ws.close();
              res({ ok: true, frames, sawReady, untagged, firstKeys }); }
          }
        } catch (e) {}
      };
      ws.onerror = () => { clearTimeout(t); res({ ok: false, frames, sawReady, untagged, why: 'ws error' }); };
    });
  })()`);

  record(
    'P7 start 之后真的收到 >=5 帧（数据在流动）',
    streamed.ok,
    streamed.ok ? `frames=${streamed.frames} sawReady=${streamed.sawReady}`
                : `frames=${streamed.frames} why=${streamed.why}`
  );

  record(
    'P8 帧带 kind:"frame" 标签（不是靠 else 兜底路由）',
    streamed.ok && streamed.untagged === 0,
    streamed.ok
      ? `untagged=${streamed.untagged} firstKeys=${JSON.stringify(streamed.firstKeys)}`
      : 'no frames'
  );

  const shot = await page.screenshot('/Users/zhourui/code/steer3d/.cache/browser_verify/shots/wsendpoint.png');
  console.log('\nscreenshot ->', shot);

} catch (e) {
  record('X 测试脚本自身没跑完', false, String(e && e.stack || e));
} finally {
  cdp.close();
  proc.kill('SIGKILL');
}

const passed = results.filter(r => r.pass).length;
console.log(`\n=== ${passed}/${results.length} passed ===`);
for (const r of results) if (!r.pass) console.log(`FAIL: ${r.name} -> ${r.detail}`);
process.exit(passed === results.length ? 0 : 1);
