/**
 * Where does the 3-D backend live?
 *
 * This used to be a hard-coded `ws://<hostname>:8000/ws` in page.tsx. That
 * silently broke whenever 8000 was already taken by something else — which is
 * exactly what happened: a stray `python http.server` directory listing owned
 * 8000, so the socket never opened and the page sat at "disconnected" with an
 * empty canvas and no error worth reading.
 *
 * Two things changed as a result:
 *
 *  1. The port is no longer baked in. `NEXT_PUBLIC_WS_URL` wins if set; then a
 *     list of same-host ports is probed in order and the first one that
 *     actually answers a WebSocket handshake wins.
 *  2. Probing is done by *attempting the handshake* and waiting for `open`,
 *     not by guessing or by polling `/health`. This mattered: on this machine
 *     port 8010 answers `GET /health` with `{"ok":true}` and port 8100 answers
 *     it with `{"status":"ok",...}` — both look like a healthy backend — yet
 *     both reject the WebSocket upgrade with HTTP 404. Only 8200 actually
 *     completed the handshake. A health check cannot tell you whether the
 *     `/ws` route exists.
 *
 * The candidate list is the same host the page was served from, so this also
 * works when you reach the frontend through a LAN IP or a tunnel.
 */

export const DEFAULT_WS_PORT_CANDIDATES = [8200, 8000, 8001, 8300, 8400];

/** ms to wait for a candidate socket to open before giving up on it. */
const PROBE_TIMEOUT_MS = 1200;

function envUrl(): string | null {
  const raw = process.env.NEXT_PUBLIC_WS_URL;
  return raw && raw.trim() ? raw.trim() : null;
}

function candidatesFor(host: string): string[] {
  const out: string[] = [];
  const explicit = envUrl();
  if (explicit) out.push(explicit);
  for (const port of DEFAULT_WS_PORT_CANDIDATES) {
    out.push(`ws://${host}:${port}/ws`);
  }
  return out;
}

/**
 * Resolve a single WebSocket URL by racing handshake attempts in order.
 *
 * Order matters: earlier candidates win, so `NEXT_PUBLIC_WS_URL` still takes
 * priority and a multi-backend deployment stays predictable.
 */
export async function resolveWsUrl(
  host: string,
  timeoutMs: number = PROBE_TIMEOUT_MS
): Promise<string> {
  const list = candidatesFor(host);

  for (const url of list) {
    const ok = await probe(url, timeoutMs);
    if (ok) return url;
  }
  // Nothing answered. Return the first candidate anyway so the page still
  // renders and shows "disconnected" with a URL the user can act on, instead
  // of throwing during render.
  return list[0];
}

function probe(url: string, timeoutMs: number): Promise<boolean> {
  return new Promise((resolve) => {
    let settled = false;
    let ws: WebSocket | null = null;
    const done = (v: boolean) => {
      if (settled) return;
      settled = true;
      if (ws) {
        ws.onopen = null;
        ws.onerror = null;
        ws.onclose = null;
        // Close a socket that *did* open; leave a failed one alone.
        if (ws.readyState === WebSocket.OPEN) ws.close();
      }
      resolve(v);
    };

    try {
      ws = new WebSocket(url);
    } catch (err) {
      resolve(false);
      return;
    }
    const timer = setTimeout(() => done(false), timeoutMs);
    ws.onopen = () => {
      clearTimeout(timer);
      done(true);
    };
    ws.onerror = () => {
      clearTimeout(timer);
      done(false);
    };
    ws.onclose = () => {
      clearTimeout(timer);
      done(false);
    };
  });
}
