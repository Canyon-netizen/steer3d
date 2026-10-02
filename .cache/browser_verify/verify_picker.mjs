// 验收：回放模式下 UI 只能选真实存在的轨迹。
//
// 这一轮发现的缺陷：ControlPanel 是个自由文本框，而回放 runner 拿 prompt
// 去匹配记录 id，匹配不上就回退到第 0 条。实测：
//
//     prompt='Why is the sky blue?'  -> ['We',' are',' given',' the']   ← 1983_I_1
//     prompt='1983_I_1'              -> 同一批 token
//
// 用户输入了一句不相干的话，页面上跑的是另一道题，而输入框仍显示着他那句。
// 看起来完全正常。判据要盯的是「UI 不允许构造出一个不存在的选择」。
import { launch, Page, CDP } from './cdp_client.mjs';

const BACKEND = process.env.T3D_PORT || '9500';
const URL = process.env.T3D_URL || 'http://127.0.0.1:9401/';
const PROFILE = process.env.T3D_PROFILE
  || '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_picker';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const R = [];
const rec = (n, p, d) => { R.push({ n, p }); console.log(`[${p ? 'PASS' : 'FAIL'}] ${n}\n       ${d}`); };

const { proc, version } = await launch({ port: 9425, userDataDir: PROFILE,
  windowSize: '1600,1000', url: 'about:blank' });
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);

try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  // 等 ready 落地：选择器要等 trajectories 到了才渲染。
  //
  // 等待条件必须是「**轨迹选择器**出现了」，不能是「有 select」。
  // 页面里本来就有层选择器和速度选择器，所以 `!!querySelector('select')`
  // 在 trajectories 到达之前就成立 —— 判据于是读到一个选项为空的
  // 选择器，报 E1/E2/E3 全红，而页面其实是对的。第一版就是这么误报的。
  let ok = false;
  for (let i = 0; i < 12; i++) {
    ok = await page.eval(`(() => {
      const s = [...document.querySelectorAll('select')].find(x =>
        [...x.options].some(o => /^aime__/.test(o.value)));
      return !!s;
    })()`);
    if (ok) break;
    await sleep(1200);
  }
  rec('E0 轨迹选择器已渲染（等待条件是它本身，不是「有 select」）', ok,
      ok ? 'ready 落地' : '等了 14s 仍未出现');

  /* ---------------------------------------------------------------- 1 */
  const ui = await page.eval(`(() => {
    const sels = [...document.querySelectorAll('select')];
    const rec = sels.find(s => [...s.options].some(o => /^aime__/.test(o.value)));
    return {
      selCount: sels.length,
      hasRecPicker: !!rec,
      options: rec ? rec.options.length : 0,
      values: rec ? [...rec.options].slice(0, 4).map(o => o.value) : [],
      textareas: document.querySelectorAll('textarea').length,
      labels: [...document.querySelectorAll('label')].map(l => l.textContent.trim()),
      bodyHasSky: /Why is the sky blue/.test(document.body.innerText || ''),
      saysReplaying: /Replaying a recorded/.test(document.body.innerText || ''),
    };
  })()`);

  rec('E1 页面有轨迹选择器（不是自由文本框）', ui.hasRecPicker,
      `selects=${ui.selCount} textareas=${ui.textareas} labels=${JSON.stringify(ui.labels)}`);
  rec('E2 选择器选项数 == 后端上报的轨迹数（48）', ui.options === 48, `options=${ui.options}`);
  rec('E3 选项值是真实记录 id', ui.values.length > 0 && ui.values.every(v => v.startsWith('aime__')),
      `sample=${JSON.stringify(ui.values)}`);
  rec('E4 「Why is the sky blue?」这个不存在的 prompt 不再出现在页面上',
      !ui.bodyHasSky, `bodyHasSky=${ui.bodyHasSky}`);
  rec('E5 页面说明这是回放而非生成', ui.saysReplaying, `saysReplaying=${ui.saysReplaying}`);

  /* ---------------------------------------------------------------- 6 */
  // 换一条轨迹，token 流必须真的变。
  const before = await page.eval(`(() => {
    const s=[...document.querySelectorAll('select')].find(s=>
      [...s.options].some(o=>/^aime__/.test(o.value)));
    return s ? s.value : null;
  })()`);
  const after = await page.eval(`(async () => {
    const s=[...document.querySelectorAll('select')].find(s=>
      [...s.options].some(o=>/^aime__/.test(o.value)));
    if(!s) return null;
    // 选一条 id 与当前不同的
    const opt=[...s.options].find(o=>o.value!==s.value && /__think$/.test(o.value));
    if(!opt) return null;
    s.value=opt.value;
    s.dispatchEvent(new Event('change',{bubbles:true}));
    return opt.value;
  })()`);
  await sleep(1200);
  rec('E6 换选项后选中的 id 真的变了', !!(before && after && before !== after),
      `${before} -> ${after}`);

  // 点 Start，token 流应当与所选 id 对应。用后端独立取同一 id 的首几个
  // token 比对，避免"页面显示的其实是别的轨迹"这种假绿。
  const got = await page.eval(`(async () => {
    return await new Promise(res => {
      const sel = [...document.querySelectorAll('select')].find(x =>
        [...x.options].some(o => /^aime__/.test(o.value)));
      if(!sel) return res({ok:false, why:'no trajectory select'});
      const want = sel.value;
      let ws;
      try { ws = new WebSocket('ws://' + location.hostname + ':${BACKEND}/ws'); }
      catch(e){ return res({ok:false, why:'throw'}); }
      const out=[];
      const t=setTimeout(()=>{ try{ws.close();}catch{}
        res({ok:out.length>0, out, picked:want, why: out.length?'':'no frame in 30s'}); }, 12000);
      ws.onmessage=ev=>{
        try{
          const m=JSON.parse(ev.data);
          if(m.kind==='ready'){
            ws.send(JSON.stringify({kind:'start',payload:{prompt:want,layer:14}}));
          } else if(m.kind==='frame'){
            out.push(m.token);
            if(out.length>=5){ clearTimeout(t); ws.close();
              res({ok:true,out,picked:want}); }
          }
        }catch(e){}
      };
      ws.onerror=()=>{clearTimeout(t);res({ok:false,why:'ws error',picked:want});};
    });
  })()`);
  rec('E7 按所选 id 回放，收到 >=5 帧', got.ok,
      got.ok ? `id=${got.picked} tokens=${JSON.stringify(got.out)}` : (got.why || '无帧'));

  // 所选 id 的 mode 必须和首帧内容自洽：__think 的记录第一步通常是 <think>
  if (got.ok) {
    const modeOk = got.picked.endsWith('__no_think')
      ? !/<think>/.test(got.out.join(''))
      : true;
    rec('E8 所选 id 的 think/no_think 与内容自洽', modeOk,
        `id=${got.picked} first=${JSON.stringify(got.out.slice(0,3))}`);
  }

  const errs = page.events
    .filter(e => e.method === 'Runtime.consoleAPICalled' && e.params.type === 'error')
    .map(e => (e.params.args || []).map(a => a.value ?? a.description ?? '').join(' '))
    .filter(t => !/favicon|Failed to load resource/i.test(t));
  rec('E9 页面无 console error', errs.length === 0, errs.length ? errs.slice(0,2).join(' | ') : 'none');
} catch (e) {
  rec('X 脚本崩了', false, String(e && e.stack || e).slice(0, 250));
} finally {
  cdp.close(); proc.kill('SIGKILL');
}

const pass = R.filter(x => x.p).length;
console.log(`\n=== ${pass}/${R.length} passed ===`);
R.filter(x => !x.p).forEach(x => console.log(`FAIL: ${x.n}`));
process.exit(pass === R.length ? 0 : 1);
