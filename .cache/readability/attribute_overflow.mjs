// 归因：某个容器在 1280x800 溢出 3–4px，是我的改动带来的，还是页面本来就这样？
// 两个来源（HEAD 静态根 :8944 / 现行 :8917）× 两个 token 状态，各量一遍。
import { launch, CDP, Page } from '../browser_verify/cdp_client.mjs';
import * as P from './probe_lib.mjs';

const ROOT = '/Users/zhourui/code/steer3d';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const SRC = [
  { tag: 'HEAD', url: 'http://127.0.0.1:8944/latent/index.html', port: 9391, dir: 'ph_head' },
  { tag: 'NEW',  url: 'http://127.0.0.1:8917/latent/index.html?orient=off', port: 9392, dir: 'ph_new' },
];

for (const S of SRC) {
  for (const size of [{ w: 1600, h: 1000 }, { w: 1280, h: 800 }]) {
    const { proc, version } = await launch({
      port: S.port, userDataDir: `${ROOT}/.cache/readability/${S.dir}_${size.w}`,
      windowSize: `${size.w},${size.h}`, url: 'about:blank',
    });
    const cdp = await CDP.connect(
      `ws://127.0.0.1:${S.port}/devtools/browser/${version.webSocketDebuggerUrl.split('/').pop()}`);
    const page = await Page.create(cdp);
    await page.send('Storage.clearDataForOrigin',
      { origin: 'http://localhost:8917', storageTypes: 'local_storage' });
    await page.nav(S.url);
    for (let i = 0; i < 160; i++) {
      const st = await page.eval(`(()=>({l:getComputedStyle(document.getElementById('loading')).display,
        a:getComputedStyle(document.getElementById('app')).visibility,
        r:document.querySelectorAll('#tblTop tr').length}))()`);
      if (st.l === 'none' && st.a === 'visible' && st.r > 0) break;
      await sleep(250);
    }
    await sleep(1500);
    for (const tok of [0, 5]) {
      if (tok) {
        await page.eval(`(()=>{const e=document.getElementById('rngTok');e.value=${tok};
          e.dispatchEvent(new Event('input',{bubbles:true}));return 1;})()`);
        await sleep(600);
      }
      const po = await page.eval(P.pageOverflow);
      const lo = await page.eval(`(()=>{const f=${P.layoutOverflow.toString()};
        return f('.wrap,.panel,.col');})()`);
      const over = lo.filter(x => x.vOver > 0)
        .map(x => `${x.sel}:${x.vOver}(h=${x.h})`);
      const bleed = (await page.eval(P.horizontalBleed)).length;
      console.log(JSON.stringify({
        src: S.tag, size: size.w + 'x' + size.h, tok,
        pageVOver: po.vOver, bleed, over: over.length ? over : 'none',
      }));
    }
    page.close(); cdp.close(); proc.kill('SIGKILL');
  }
}
