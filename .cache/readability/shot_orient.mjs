// Screenshot the orientation layer on first load, at both viewports.
//
// This exists so the claim "导读层默认可见、且真的读得到" has a picture behind
// it. The verify script already asserts it geometrically; a picture is what
// catches the class of problem geometry cannot -- a layer that is technically
// in the viewport and technically unoccluded, and still unreadable.
//
// Reuses .cache/browser_verify/cdp_client.mjs, whose launch() wraps the
// --single-process flag. A hand-rolled launcher omits it and the screenshots
// come back stale.
import { launch, CDP, Page } from '../browser_verify/cdp_client.mjs';

const URL = 'http://localhost:8917/latent/index.html';
const OUT = '.cache/readability/shots';

const { proc, version } = await launch({
  port: 9351,
  userDataDir: '/Users/zhourui/code/steer3d/.cache/readability/profile_shot',
  url: 'about:blank',
});
console.log('chromium:', version.Browser);
const cdp = await CDP.connect(
  `ws://127.0.0.1:9351/devtools/browser/${version.webSocketDebuggerUrl.split('/').pop()}`);
try {
  for (const [w, h] of [[1600, 1000], [1280, 800]]) {
    const page = await Page.create(cdp);
    await page.send('Emulation.setDeviceMetricsOverride',
      { width: w, height: h, deviceScaleFactor: 1, mobile: false });
    // ?orient=reset clears the "I've read it" flag, so this always measures a
    // genuine first visit rather than whatever the last run left behind.
    await page.send('Page.navigate', { url: `${URL}?orient=reset` });
    await page.waitForEvent('Page.loadEventFired', 40000);
    await new Promise(r => setTimeout(r, 2500));

    const st = await page.eval(() => {
      const o = document.getElementById('orientation');
      if (!o) return { present: false };
      const r = o.getBoundingClientRect();
      const cs = getComputedStyle(o);
      const body = document.getElementById('orientBody');
      return {
        present: true,
        hidden: o.classList.contains('hide'),
        display: cs.display, opacity: cs.opacity,
        rect: { x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height) },
        inViewport: r.top < innerHeight && r.bottom > 0
                    && r.left < innerWidth && r.right > 0,
        // Measure the element that actually scrolls. `#orientBody` reports 0
        // overflow because the scrolling container is its parent
        // `#orientScroll` -- measuring the wrong node is how a script reports
        // "no overflow" for a panel that plainly has more content than height.
        scroll: (() => {
          const el = document.getElementById('orientScroll') || body;
          return el ? { id: el.id,
                        vOver: el.scrollHeight - el.clientHeight,
                        hOver: el.scrollWidth - el.clientWidth } : null;
        })(),
        firstLine: (body?.innerText || '').split('\n').find(x => x.trim()) || '',
      };
    });
    console.log(`\n${w}x${h}`);
    console.log('  浮层存在:', st.present, '| display:', st.display,
                '| opacity:', st.opacity, '| hide 类:', st.hidden);
    console.log('  几何:', JSON.stringify(st.rect), '| 在视口内:', st.inViewport);
    console.log('  滚动容器:', JSON.stringify(st.scroll));
    console.log('  首行:', st.firstLine.slice(0, 70));

    await page.screenshot(`${OUT}/orient_${w}x${h}.png`);
    // A 2x crop of the opening paragraph, because at 1x the type is too small
    // to judge -- and a previous "the text is clipped" reading in this project
    // came from looking at the wrong magnification.
    await page.screenshot(`${OUT}/orient_top_${w}x${h}.png`,
      { clip: { x: st.rect.x + 24, y: st.rect.y + 90,
                width: Math.min(760, st.rect.w - 60), height: 340, scale: 2 } });
  }
} finally {
  proc.kill('SIGKILL');
}
console.log('\n截图写入', OUT);
