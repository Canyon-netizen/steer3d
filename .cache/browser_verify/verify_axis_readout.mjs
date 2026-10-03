import { readFileSync } from 'node:fs';
import { launch, Page, CDP } from './cdp_client.mjs';

/**
 * 判据：轴→观测量面板。
 *
 * 判据主体是**页面上读者看到的那段文字**；`data-*` 属性只用来交叉核对
 * 「属性说的」与「印出来的」。外部真值取磁盘上的 axis_readouts.json ——
 * 不取页面自己报的值。
 *
 * 特别要守住的一条：这块面板的全部价值在于**并排显示位置对照**。
 * 所以 C 组判据专门查对照栏在不在、印的数对不对。
 * 如果哪天有人把对照那一栏删掉（页面照样渲染、看起来完全正常），
 * C1–C3 会红。
 */
const URL = process.env.BV_URL || 'http://127.0.0.1:10340/';
const PROFILE = '/Users/zhourui/code/steer3d/.cache/browser_verify/profile_axis_' + process.pid;
const sleep = ms => new Promise(r => setTimeout(r, ms));

const truth = JSON.parse(readFileSync(
  '/Users/zhourui/code/steer3d/frontend/public/latent/data/axis_readouts.json', 'utf8'));
const AXES = ['confidence', 'caution', 'creativity', 'reasoning'];

const results = [];
const check = (name, ok, detail) => {
  results.push({ name, ok: !!ok });
  console.log(`[${ok ? 'PASS' : 'FAIL'}] ${name}: ${detail}`);
};

const { proc, version } = await launch({
  port: 9484, userDataDir: PROFILE, windowSize: '1700,1100', url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
try {
  await page.send('Page.navigate', { url: URL });
  await page.waitForEvent('Page.loadEventFired', 40000).catch(() => {});
  await sleep(12000);

  const root = await page.eval(`(() => {
    const el = document.querySelector('[data-axis]');
    if (!el) return JSON.stringify({present:false});
    const r = el.getBoundingClientRect();
    return JSON.stringify({
      present: true, state: el.getAttribute('data-axis'),
      w: Math.round(r.width), h: Math.round(r.height),
      text: (el.innerText||'').replace(/\\s+/g,' ').trim(),
      measured: el.getAttribute('data-measured'),
      taut: el.getAttribute('data-tautological'),
      shared: el.getAttribute('data-shared-readout'),
      posAxis: el.getAttribute('data-position-axis'),
      notMeasured: el.getAttribute('data-not-measured'),
      retraction: (el.querySelector('[data-retraction]')?.innerText || '')
        .replace(/\s+/g, ' ').trim(),
    });
  })()`);
  const P = JSON.parse(root);

  check('A1 面板已就绪且有非零包围盒',
    P.present && P.state === 'ready' && P.w > 0 && P.h > 0,
    `state=${P.state} ${P.w}x${P.h}px`);

  if (P.present && P.state === 'ready') {
    // A2 四条轴都在，行上的状态标记与产物一致
    for (const ax of AXES) {
      const got = await page.eval(`(() => {
        const el = document.querySelector('[data-axis-row="${ax}"]');
        if (!el) return JSON.stringify({missing:true});
        const v = el.querySelector('[data-verdict]');
        return JSON.stringify({
          status: el.getAttribute('data-status'),
          beating: el.getAttribute('data-beating'),
          layers: el.getAttribute('data-layers'),
          statusLabel: el.querySelector('[data-status-label]')?.textContent?.trim(),
          verdictText: v ? (v.innerText||'').replace(/\\s+/g,' ').trim() : '',
        });
      })()`);
      const g = JSON.parse(got);
      const want = truth.axes[ax].status;
      check(`A2 ${ax} 状态与产物一致`, g.status === want,
        `页面 ${g.status} / 产物 ${want}；标签「${g.statusLabel}」`);

      // A4 徽章文案本身也必须与产物一致。
      // 这一条是被变异 M2 逼出来的：M2 把徽章硬编码成「已测到读出方向」，
      // 而 A2 读的是 data-status 属性、A3 读的是判定句 —— **两者都不受徽章影响**，
      // 于是判据全绿。也就是「页面可以给四行都印『已测』而判据通过」。
      const LABEL_OF = { measured: '已测到读出方向', not_measured: '测不出',
                         position_axis: '判定为轨迹位置轴',
                         tautological: '已测，但目标是定义式',
                         shared_readout: '非循环，但不专属' };
      check(`A4 ${ax} 徽章文案与产物状态一致`,
        g.statusLabel === LABEL_OF[want],
        `页面「${g.statusLabel}」/ 期望「${LABEL_OF[want]}」`);

      // A3 印出来的判定句必须真的包含对应的词。
      // 2026-10-03：confidence/caution 降级后，判定句各要印自己的新结论 ——
      // 「都印 token 局部」不再够用，因为那正是被撤回的那句话。
      const need = want === 'tautological' ? ['token 局部', '构造恒等式']
        : want === 'shared_readout' ? ['分不开归属', '共用']
        : want === 'measured' ? ['token 局部']
        : want === 'position_axis' ? ['轨迹位置轴']
        : ['测不出'];
      check(`A3 ${ax} 判定句包含关键结论`,
        need.every(k => g.verdictText.includes(k)),
        `「${g.verdictText.slice(0, 70)}」`);

      // B 组：cos 与对照都要真的印出来，且与产物一致
      for (const L of ['12', '14', '20']) {
        const c = truth.axes[ax].at_delta0.per_layer[L];
        const cell = await page.eval(`(() => {
          const el = document.querySelector('[data-cell="${ax}-${L}"]');
          if (!el) return JSON.stringify({missing:true});
          const r = el.getBoundingClientRect();
          return JSON.stringify({
            cos: el.querySelector('[data-cos]')?.getAttribute('data-cos'),
            ctl: el.querySelector('[data-control-cos]')?.getAttribute('data-control-cos'),
            text: (el.innerText||'').replace(/\\s+/g,' ').trim(),
            w: Math.round(r.width), h: Math.round(r.height),
          });
        })()`);
        const cc = JSON.parse(cell);
        if (cc.missing) { check(`B1 ${ax}/L${L} 格子存在`, false, 'missing'); continue; }
        const okCos = Math.abs(Number(cc.cos) - c.cos) < 5e-3;
        const okCtl = Math.abs(Number(cc.ctl) - c.control_cos) < 5e-3;
        const inText = cc.text.includes(c.cos.toFixed(3))
          && cc.text.includes(c.control_cos.toFixed(3));
        check(`B1 ${ax}/L${L} cos 与对照都印出且与产物一致`,
          okCos && okCtl && inText && cc.w > 0 && cc.h > 0,
          `页面 cos=${cc.cos} 对照=${cc.ctl} | 产物 cos=${c.cos} 对照=${c.control_cos} | 文字「${cc.text}」`);
      }
    }

    // C 组：对照这件事必须在页面上被说清楚
    const saysControl = P.text.includes('对照') && P.text.includes('step_frac');
    check('C1 页面解释了对照是什么', saysControl,
      P.text.includes('step_frac') ? '提到 step_frac 对照' : '未提到');
    const saysSearch = P.text.includes('搜索') || P.text.includes('付过钱');
    check('C2 页面声明了多重比较的代价', saysSearch,
      saysSearch ? '已声明 p 为搜索付过钱' : '未声明');
    const saysVocab = P.text.includes('四条独立轴') || P.text.includes('4 条独立轴');
    check('C3 页面提醒 6 个标签 = 4 条轴', saysVocab,
      saysVocab ? '已提醒' : '未提醒');

    // D 组：顶层汇总与产物一致
    check('D1 五组状态与产物一致（measured / tautological / shared / position / not-measured）',
      P.measured === truth.headline.measured.join(',')
      && P.taut === (truth.headline.tautological || []).join(',')
      && P.shared === (truth.headline.shared_readout || []).join(',')
      && P.posAxis === truth.headline.position_axis.join(',')
      && P.notMeasured === truth.headline.not_measured.join(','),
      `页面 [${P.measured}] [${P.taut}] [${P.shared}] [${P.posAxis}] [${P.notMeasured}]`);

    // D2 反向守卫：位置轴那一行必须**不**出现「token 局部」
    const posText = await page.eval(`(() => {
      const el = document.querySelector('[data-axis-row="reasoning"]');
      const v = el && el.querySelector('[data-verdict]');
      return v ? (v.innerText||'') : '';
    })()`);
    check('D2 位置轴那一行不得声称 token 局部',
      !posText.includes('token 局部'),
      posText.includes('token 局部') ? '错误地出现了「token 局部」' : '正确');

    // D3 只剩 confidence 一条成立，所以只有它必须出现 token 局部。
    // 2026-10-03：原来 D3 对 confidence/caution 都要求「token 局部」，
    // 那是把「caution 已测」当成了前提。现在前提没了，判据跟着改。
    const confText = await page.eval(`(() => {
      const el = document.querySelector('[data-axis-row="confidence"]');
      const v = el && el.querySelector('[data-verdict]');
      return v ? (v.innerText||'') : '';
    })()`);
    check('D3 confidence 那行必须出现「token 局部」', confText.includes('token 局部'),
      confText.slice(0, 60));

    // D4 **替换**掉原来那条对 caution 的要求，而且更强：
    // 归属检验的四个余弦必须真的印出来、且逐个与产物一致，
    // 并且「最高的那一列」必须真的高于报告行所属的那一列 ——
    // 也就是把「caution 降级」这个结论本身变成可执行的判据。
    for (const ax of ['confidence', 'caution']) {
      const sp = truth.axes[ax].specificity;
      const got = JSON.parse(await page.eval(`(() => {
        const cells = {};
        document.querySelectorAll('[data-specificity="${ax}"] [data-spec-cell]')
          .forEach(e => {
            const k = e.getAttribute('data-spec-cell').split('-').pop();
            cells[k] = { cos: e.getAttribute('data-spec-cos'),
                         role: e.getAttribute('data-spec-role'),
                         text: (e.innerText||'').replace(/\\s+/g,' ').trim() };
          });
        return JSON.stringify(cells);
      })()`));
      const keys = Object.keys(sp.cos_per_axis);
      const allMatch = keys.every(k =>
        got[k] && Math.abs(Number(got[k].cos) - sp.cos_per_axis[k]) < 1e-6);
      check(`D4 ${ax} 归属检验的 ${keys.length} 个余弦都印出且与产物一致`, allMatch,
        keys.map(k => `${k}=${got[k] ? got[k].cos : '缺'}`).join(' '));
      // D4 的第二条路径：**属性对了不等于读者看到的对了。**
      // M2 那次教训（徽章/属性/判定句三条独立渲染路径）的同族 ——
      // 这里 data-spec-cos 是属性，格子里的数字是文案，必须分别查。
      const textOk = keys.every(k => {
        if (!got[k]) return false;
        const want = Number(sp.cos_per_axis[k]).toFixed(3);
        return got[k].text.includes(want);
      });
      check(`D4 ${ax} 归属检验的可见文案与产物一致（不只看 data 属性）`, textOk,
        keys.map(k => `${k}印「${got[k] ? got[k].text : '缺'}」`).join(' '));
      const strongest = keys.reduce((a, b) =>
        sp.cos_per_axis[b] > sp.cos_per_axis[a] ? b : a);
      const marked = got[strongest] && got[strongest].role === 'strongest';
      check(`D4 ${ax} 最高的一列（${strongest} ${sp.cos_per_axis[strongest]}）被标成 strongest`,
        marked, `页面角色 ${got[strongest] ? got[strongest].role : '缺'}；`
        + `报告行所属 ${sp.axis_of_report_row}=${sp.row_axis_cos}`);
    }

    // D5 撤回声明必须印在页面上，且必须真的提到被撤回的那个说法。
    check('D5 页面印出了撤回声明',
      P.retraction.includes('已撤回') && P.retraction.includes('0.3341')
      && P.retraction.includes('0.3077'),
      P.retraction.slice(0, 90) || '（页面没有 data-retraction 区块）');
  }
} catch (e) {
  check('装置', false, String(e && e.message ? e.message : e));
} finally {
  try { await page.close(); } catch {}
  cdp.close();
  proc.kill('SIGKILL');
}

const pass = results.filter(r => r.ok).length;
console.log(`\nRESULT ${pass === results.length ? 'PASS' : 'FAIL'}  ${pass}/${results.length}`);
process.exit(pass === results.length ? 0 : 1);
