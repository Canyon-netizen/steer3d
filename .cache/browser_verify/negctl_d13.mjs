// 负控制：证明 verify_real_replay.mjs 里 D13 的比对器**不是恒真**。
//
// 为什么要单独做：D13 断言「注入期间 token 与无注入基线逐字相同」。
// 如果比对器写错了（比如 map 键取错、比较写成了恒真），它会**照样报绿**，
// 而页面上的谎话就跟着过了门禁。这和「全 PASS 的判据等于没有判据」同族。
//
// 手法：拿**故意错位**的基线去跑同一段比对逻辑。
//   · 真基线   → 应当 0 处差异（这才是 D13 正常时的样子）
//   · 错一位基线（step+1）→ 应当大量差异
// 两者都跑一遍：若错位基线也报 0 差异，说明比对器恒真，D13 是假绿。
//
// 用法: T3D_PORT=9503 T3D_URL=http://127.0.0.1:22233/ node .cache/browser_verify/negctl_d13.mjs
import { launch, Page, CDP } from './cdp_client.mjs';

const BACKEND = process.env.T3D_PORT || '9503';
const URL = process.env.T3D_URL || 'http://127.0.0.1:22233/';
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_negctl_'
  + process.pid;
const sleep = ms => new Promise(r => setTimeout(r, ms));

const { proc, version } = await launch({
  port: 9487, userDataDir: PROFILE, windowSize: '1500,950', url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);

try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  await sleep(3000);

  // 采两批帧：无注入 / 有注入。用的是 D13 里同一段协议。
  const collect = inject => page.eval(`(async () => {
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
            ${inject ? `ws.send(JSON.stringify({ kind: 'inject_steering', payload: {
                direction: 'reasoning_deep', strength: 0.5, layer: 14 } }));
              await sleep(400);` : ''}
            ws.send(JSON.stringify({ kind: 'start', payload: {
              prompt: 'aime__1983__1983_I_1__no_think', layer: 14 } }));
          } else if (m.kind === 'frame') {
            out.push({ step: m.step_id, token: m.token, steer: !!m.steer_active });
            if (out.length >= 8) { clearTimeout(t); ws.close();
              res({ ok: true, frames: out }); }
          }
        } catch (e) {}
      };
      ws.onerror = () => { clearTimeout(t); res({ ok: false, why: 'ws error' }); };
    });
  })()`);

  const base = await collect(false);
  const inj = await collect(true);
  if (!base.ok || !inj.ok) {
    console.log(`装置故障：采帧失败 base=${base.ok} inj=${inj.ok} `
      + `${base.why || ''}${inj.why || ''}`);
    process.exit(2);
  }

  const steered = inj.frames.filter(f => f.steer);
  if (!steered.length) {
    console.log('装置故障：没有 steer_active 的帧 ⇒ 比对器无从验起');
    process.exit(2);
  }

  // 与 D13 完全相同的比较逻辑，只是基线的取法不同。
  const cmpWith = (get) => {
    const map = new Map(base.frames.map(f => [f.step, f.token]));
    const rows = steered.map(f => ({ step: f.step, b: get(map, f.step), i: f.token }));
    return { rows, diff: rows.filter(r => r.b != null && r.b !== r.i) };
  };
  const trueBase = cmpWith((m, s) => m.get(s));              // 真基线
  const shiftBase = cmpWith((m, s) => m.get(s + 1));          // 故意错一位

  console.log(`\n注入生效帧数 = ${steered.length}`);
  console.log(`[真基线 ] 差异 ${trueBase.diff.length}/${trueBase.rows.length} `
    + `  （D13 正常时应为 0）`);
  console.log(`[错一位 ] 差异 ${shiftBase.diff.length}/${shiftBase.rows.length} `
    + `  （负控制：必须 > 0）`);
  if (shiftBase.diff.length) {
    const d = shiftBase.diff[0];
    console.log(`         例：step ${d.step} 错位基线="${d.b}" 实际="${d.i}"`);
  }

  const ok = trueBase.diff.length === 0 && shiftBase.diff.length > 0;
  console.log(ok
    ? '\nRESULT PASS 比对器有牙齿：真基线 0 差异、错位基线报出差异'
    : '\nRESULT FAIL 比对器恒真或恒假 —— D13 是假绿/恒红，必须先修比对逻辑');
  process.exit(ok ? 0 : 1);
} catch (e) {
  console.log('脚本崩了:', String(e && e.stack || e).slice(0, 300));
  process.exit(2);
} finally {
  cdp.close(); proc.kill('SIGKILL');
}
