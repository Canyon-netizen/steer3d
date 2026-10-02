// One-off: dump the colours that the ribbon-hue discriminator actually
// matches, so a count that refuses to drop can be explained instead of
// guessed at. Written because the mutated run still reported 21k "ribbon"
// pixels with 243 of 245 points off-screen, and the first hypothesis (the
// blue axis) turned out to be arithmetically impossible -- g - r along the
// axis blend never exceeds 3, so it cannot satisfy g < r - 8.

import { launch, CDP, Page } from '../browser_verify/cdp_client.mjs';

const sleep = ms => new Promise(r => setTimeout(r, ms));
const PORT = Number(process.env.BV_PORT || 9430);
const { proc, version } = await launch({
  port: PORT,
  userDataDir: new URL('./profile_' + PORT, import.meta.url).pathname,
  windowSize: '1600,1000',
  url: 'about:blank',
});
const cdp = await CDP.connect(version.webSocketDebuggerUrl);
const page = await Page.create(cdp);
try {
  await page.send('Network.enable');
  await page.send('Network.setCacheDisabled', { cacheDisabled: true });
  await page.send('Page.enable');
  await page.send('Runtime.enable');
  await page.send('Page.navigate', { url: (process.env.FRONTEND || 'http://127.0.0.1:3025/') + '?render=2d' });
  for (let i = 0; i < 25; i++) {
    await sleep(1000);
    const n = await page.eval(() => {
      const c = document.querySelector('[data-testid="scene3d-fallback"] canvas');
      return c ? Number(c.getAttribute('data-rendered-points') || 0) : 0;
    });
    if (n > 30) break;
  }
  const out = await page.eval(() => {
    const c = document.querySelector('[data-testid="scene3d-fallback"] canvas');
    const { data, width, height } = c.getContext('2d').getImageData(0, 0, c.width, c.height);
    const hist = {};
    let minX = 1e9, maxX = -1e9, minY = 1e9, maxY = -1e9, n = 0;
    // 8x8 spatial buckets, to show whether the match is a compact shape
    // (a trajectory) or scattered streaks (clipped off-screen segments).
    const GX = 8, GY = 8;
    const grid = Array.from({ length: GY }, () => new Array(GX).fill(0));
    for (let i = 0; i < data.length; i += 4) {
      const r = data[i], g = data[i + 1], b = data[i + 2];
      if (!(r > 30 && b > 40 && b > r + 25 && g > 25 && g < r - 8)) continue;
      const px = (i / 4) % width, py = Math.floor((i / 4) / width);
      n++;
      const k = `${r},${g},${b}`;
      hist[k] = (hist[k] || 0) + 1;
      if (px < minX) minX = px; if (px > maxX) maxX = px;
      if (py < minY) minY = py; if (py > maxY) maxY = py;
      grid[Math.min(GY - 1, Math.floor((py / height) * GY))][Math.min(GX - 1, Math.floor((px / width) * GX))]++;
    }
    return {
      distinct: Object.keys(hist).length,
      total: n,
      bbox: [minX, minY, maxX, maxY],
      canvas: [width, height],
      top: Object.entries(hist).sort((a, b) => b[1] - a[1]).slice(0, 4),
      grid,
    };
  });
  console.log('matching pixels: total=' + out.total + '  distinct colours=' + out.distinct);
  console.log('canvas ' + out.canvas.join('x') + '  bbox ' + out.bbox.join(',') +
    '  (bbox spanning the full canvas = streaks, not a shape)');
  console.log('top colours: ' + out.top.map(([k, v]) => `rgb(${k})x${v}`).join('  '));
  console.log('spatial distribution (8x8, each cell = matching pixels):');
  const cellW = Math.max(...out.grid.flat()).toString().length;
  for (const row of out.grid) {
    console.log('  ' + row.map(v => String(v).padStart(cellW)).join(' '));
  }
} finally {
  try { proc.kill('SIGKILL'); } catch {}
  cdp.ws.close();
}
