// 就绪等待 + **自报**（从 probe_panels.mjs 抽出来，好在没有浏览器的机器上测）。
//
// ⚠⚠⚴ 抽出来的理由：原循环内联在探针主流程里，等不到时**照样往下走**，
// ⚠⚠⚴ 而产物里**没有任何字段**能区分「等到了」与「空等 24 秒」——
// ⚠⚠⚴ 读产物的人会把两件事当成同一件。本模块把这件事变成返回值里的三个字段。
//
// ⚠ 这里刻意不引入任何依赖：探针必须能在没有 node_modules 的机器上跑。

/**
 * 等就绪信号，直到 `isReady(observed)` 为真或预算耗尽。
 *
 * @param {() => Promise<any>} readOne 读一次当前状态（返回字符串或布尔）
 * @param {(v:any) => boolean} isReady  判定就绪
 * @param {object} opt
 * @returns {Promise<{ok:boolean, last:any, waitedMs:number, polls:number}>}
 */
export async function waitReady(readOne, isReady, opt = {}) {
  const maxMs = opt.maxMs ?? 24000;
  const pollMs = opt.pollMs ?? 1200;
  const sleep = opt.sleep ?? (ms => new Promise(r => setTimeout(r, ms)));
  const now = opt.now ?? (() => Date.now());
  const t0 = now();
  let last = null, polls = 0;
  for (;;) {
    const s = await readOne();
    polls++;
    last = s;
    if (isReady(s)) return { ok: true, last, waitedMs: now() - t0, polls };
    const elapsed = now() - t0;
    if (elapsed + pollMs > maxMs) {
      return { ok: false, last, waitedMs: elapsed, polls };
    }
    await sleep(pollMs);
  }
}

/** `data-outcome="ready"` 形态：读到字符串，读到 'ready' 就算。 */
export const readyWhenAttr = name => s => s === 'ready';

/** 「选择器存在」形态：读到 true 就算。 */
export const readyWhenPresent = s => !!s;
