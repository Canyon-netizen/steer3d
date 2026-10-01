// Zero-dependency CDP client.
// Node 22 ships a global WebSocket, so Chrome DevTools Protocol can be driven
// with no npm install at all -- this repo has no playwright/puppeteer package,
// and /tmp is not writable, so everything lives under .cache/browser_verify/.
//
// Exists because the session's mcp_browser was unusable: clicks landed one
// control to the left and screenshots came back as stale frames. Here the click
// coordinates are read from the page itself (getBoundingClientRect) and every
// claim is backed by a value read back out of the live DOM, not by a picture.

import { spawn } from 'node:child_process';
import { writeFileSync, mkdirSync } from 'node:fs';
import { dirname } from 'node:path';

// Two environment facts forced this choice of binary, both found by trying:
//  1. The full "Google Chrome for Testing" app aborts before DevTools comes up
//     here: process_singleton_posix.cc "Failed to create socket directory" plus
//     a crashpad mkdir with an EMPTY path. That is the session sandbox refusing
//     the unix socket, not a bad flag or a bad profile dir.
//  2. chrome-headless-shell gets one step further and then dies with
//     FATAL mach_port_rendezvous_mac.cc "bootstrap_check_in ... Permission
//     denied (1100)" -- the sandbox blocks Mach bootstrap registration for
//     Chromium's child-process launcher.
// --single-process removes the child-process launcher entirely, and
// chrome-headless-shell has no ProcessSingleton, so both blockers disappear
// and DevTools comes up normally. Verified: HeadlessChrome/148.0.7778.96.
export const CHROME = process.env.BV_CHROME
  || '/Users/zhourui/Library/Caches/ms-playwright/chromium_headless_shell-1223/'
     + 'chrome-headless-shell-mac-arm64/chrome-headless-shell';

const sleep = ms => new Promise(r => setTimeout(r, ms));

/* ------------------------------------------------------------------ CDP core */

export class CDP {
  constructor(ws) {
    this.ws = ws;
    this._id = 0;
    this._pending = new Map();
    this._handlers = [];
    ws.addEventListener('message', ev => {
      const msg = JSON.parse(ev.data);
      if (msg.id !== undefined) {
        const p = this._pending.get(msg.id);
        if (!p) return;
        this._pending.delete(msg.id);
        msg.error ? p.reject(new Error(msg.method + ' ' + JSON.stringify(msg.error)))
                  : p.resolve(msg.result);
      } else {
        for (const h of this._handlers) h(msg);
      }
    });
  }

  static async connect(url) {
    const ws = new WebSocket(url);
    await new Promise((res, rej) => {
      ws.addEventListener('open', res, { once: true });
      ws.addEventListener('error', () => rej(new Error('ws fail ' + url)), { once: true });
    });
    return new CDP(ws);
  }

  send(method, params = {}, sessionId) {
    const id = ++this._id;
    const payload = { id, method, params };
    if (sessionId) payload.sessionId = sessionId;
    this.ws.send(JSON.stringify(payload));
    return new Promise((resolve, reject) => {
      this._pending.set(id, { resolve, reject });
      setTimeout(() => {
        if (this._pending.has(id)) {
          this._pending.delete(id);
          reject(new Error('CDP timeout ' + method));
        }
      }, 120000);
    });
  }

  on(fn) { this._handlers.push(fn); }
  close() { try { this.ws.close(); } catch {} }
}

/* ------------------------------------------------------------------ launch */

export async function launch(opts = {}) {
  const {
    port = 9333,
    userDataDir,
    windowSize = '1600,1000',
    url = 'about:blank',
  } = opts;
  // Chromium aborts at startup if the --user-data-dir parent is missing
  // ("Failed to create socket directory"), and there is no writable TMPDIR in
  // this environment, so the profile is created eagerly inside the repo.
  mkdirSync(userDataDir, { recursive: true });
  const args = [
    '--single-process',
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${userDataDir}`,
    `--window-size=${windowSize}`,
    '--force-device-scale-factor=1',
    '--no-first-run', '--no-default-browser-check', '--disable-sync',
    '--disable-crash-reporter', '--hide-scrollbars', '--mute-audio',
    // Keep timers/rendering at full speed: a throttled renderer would look
    // exactly like a stalled page and is the other classic false negative.
    '--disable-background-timer-throttling',
    '--disable-renderer-backgrounding',
    '--disable-backgrounding-occluded-windows',
    '--disable-features=Translate,BackForwardCache',
    url,
  ];
  const proc = spawn(CHROME, args, { stdio: ['ignore', 'pipe', 'pipe'] });
  let stderr = '';
  proc.stderr.on('data', d => { stderr += d.toString(); });
  proc.stdout.on('data', () => {});
  let version = null;
  for (let i = 0; i < 100; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${port}/json/version`);
      if (r.ok) { version = await r.json(); break; }
    } catch {}
    await sleep(100);
  }
  if (!version) {
    proc.kill('SIGKILL');
    throw new Error('chromium devtools never came up. stderr:\n' + stderr.slice(-2000));
  }
  return { proc, version, port, stderrRef: () => stderr };
}

/* --------------------------------------------------------------- page scope */

export class Page {
  constructor(cdp, sessionId) {
    this.cdp = cdp;
    this.sid = sessionId;
    this.events = [];
  }

  static async create(cdp) {
    const { targetId } = await cdp.send('Target.createTarget', { url: 'about:blank' });
    const { sessionId } = await cdp.send('Target.attachToTarget', { targetId, flatten: true });
    const page = new Page(cdp, sessionId);
    cdp.on(msg => {
      if (msg.sessionId === sessionId) page.events.push({ method: msg.method, params: msg.params, t: Date.now() });
      if (page._waiters) {
        // Iterate entries, not the Map itself: for...of over a Map yields
        // [key, value] pairs, which silently never match a method name.
        for (const [key, w] of [...page._waiters]) {
          if (key === msg.method) { page._waiters.delete(key); w.resolve(msg.params); }
        }
      }
    });
    await page.send('Page.enable');
    await page.send('Runtime.enable');
    return page;
  }

  send(method, params) { return this.cdp.send(method, params, this.sid); }

  waitForEvent(method, timeout = 30000) {
    return new Promise((resolve, reject) => {
      if (!this._waiters) this._waiters = new Map();
      this._waiters.set(method, { resolve, reject });
      setTimeout(() => {
        if (this._waiters && this._waiters.has(method)) {
          this._waiters.delete(method);
          reject(new Error('event timeout ' + method));
        }
      }, timeout);
    });
  }

  /* Evaluate in page. Returns the value by value; throws on page-side error. */
  async eval(fnOrExpr, { awaitPromise = true } = {}) {
    const expr = typeof fnOrExpr === 'function' ? `(${fnOrExpr})()` : fnOrExpr;
    const r = await this.send('Runtime.evaluate', {
      expression: expr, returnByValue: true, awaitPromise,
      userGesture: true,
    });
    if (r.exceptionDetails) {
      const d = r.exceptionDetails;
      throw new Error('PAGE EXCEPTION: ' + (d.exception?.description || d.text));
    }
    return r.result.value;
  }

  async screenshot(path, { fullPage = false } = {}) {
    const r = await this.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: fullPage });
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, Buffer.from(r.data, 'base64'));
    return path;
  }

  /* ---- real pointer input. Coordinates always come from the page. ---- */

  async rect(sel) {
    return this.eval(`(()=>{const e=document.querySelector(${JSON.stringify(sel)});
      if(!e) return null; const r=e.getBoundingClientRect();
      return {x:r.left,y:r.top,w:r.width,h:r.height,cx:r.left+r.width/2,cy:r.top+r.height/2};})()`);
  }

  async mouse(type, x, y, extra = {}) {
    await this.send('Input.dispatchMouseEvent', {
      type, x, y, button: 'left', buttons: type === 'mouseMoved' ? 1 : 1,
      clickCount: type === 'mouseMoved' ? 0 : 1, ...extra,
    });
  }

  async click(sel, { dx = 0, dy = 0 } = {}) {
    const r = await this.rect(sel);
    if (!r) throw new Error('no element ' + sel);
    const x = r.cx + dx, y = r.cy + dy;
    await this.mouse('mouseMoved', x, y, { buttons: 0 });
    await this.mouse('mousePressed', x, y);
    await this.mouse('mouseReleased', x, y);
    return { sel, x, y };
  }

  // Genuine press-move-release drag across a range input, with intermediate
  // moves, so the page sees a real input event sequence rather than a synthetic
  // value assignment.
  async dragRange(sel, fromValue, toValue) {
    const info = await this.eval(`(()=>{const e=document.querySelector(${JSON.stringify(sel)});
      const r=e.getBoundingClientRect();
      return {min:+e.min,max:+e.max,w:r.width,h:r.height,top:r.top,left:r.left,val:+e.value,
              thumb:15};})()`);
    const { min, max, w, top, left, thumb } = info;
    const xFor = v => left + thumb / 2 + (v - min) / (max - min) * (w - thumb);
    const y = top + info.h / 2;
    await this.mouse('mouseMoved', xFor(fromValue), y, { buttons: 0 });
    await this.mouse('mousePressed', xFor(fromValue), y);
    const steps = 8;
    for (let i = 1; i <= steps; i++) {
      const v = fromValue + (toValue - fromValue) * (i / steps);
      await this.mouse('mouseMoved', xFor(v), y);
      await sleep(25);
    }
    await this.mouse('mouseReleased', xFor(toValue), y);
    await sleep(120);
    return info;
  }

  // Navigating and then polling the page is the primary path: waiting on
  // loadEventFired alone is not trustworthy here, and readiness is decided by
  // the page's own loading overlay anyway.
  async nav(url, { waitLoadMs = 20000 } = {}) {
    const load = this.waitForEvent('Page.loadEventFired', waitLoadMs).catch(() => null);
    const r = await this.send('Page.navigate', { url });
    const ev = await load;
    return { navigated: r, loadEventFired: !!ev };
  }

  async close() { try { await this.cdp.send('Target.closeTarget', {}); } catch {} }
}
