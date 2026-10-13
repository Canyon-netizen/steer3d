#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""r133_gen.py —— 把遮挡层**提前**到取数之前，验 A2/A3 有没有牙齿。

⚠⚠⚴⚠ **为什么要做这个**：`verify_path.mjs` 自带变异台 `--mutate=hide_intro`，
实跑印 `变异 hide_intro：已生效 (covered-by:__mutOverlay)`，
⚠⚠⚴⚠ **可是 `RESULT OK 36/36` —— A2「容器可见且未被遮挡」、A3「内容块可见且未被遮挡」照样绿。**

行号给出的解释（**本节唯一的依据，不靠印象**）：

    :86   await page.eval(`document.querySelector('#tabPath').click(); true`);
    :96   const d = JSON.parse(await page.eval(`(() => { …`        ← 取数
    :103      visWrap: window.__vp(q('#pathWrap')),                ← __vp 在这里被调用
    :120  check('A2 容器可见且未被遮挡', d.visWrap.ok, …);          ← 当场判决
    :121  check('A3 内容块可见且未被遮挡', d.visBlk.ok, …);         ← 当场判决
    :257      d.id='__mutOverlay'; …                               ← 遮挡层，晚了 136 行
    :265  check('M1 加一层遮挡后，可见性检查必须判「被别的元素盖住」', covered, …);

⇒ ⚠⚠⚴⚠ **A2/A3 在遮挡层存在之前就已经判完了** ⇒ 该变异对它们**零影响**。
⇒ ⚠⚠⚴⚠⚠ M1 测的是 **`window.__vp` 这个辅助函数**，**不是用它的判据**。
⚠⚠⚴ 而那一轮仍印出 `RESULT OK 36/36`，读起来像「判据扛住了扰动」——
⚠⚠⚴⚠ **这正是「恒绿」的样子：扰动发生了，只是它碰不到判据。**

⚠ 本脚本把遮挡层**挪到 `:86` 之后、`:96` 取数之前**，让 A2/A3 真的被遮住。

⚠ 纪律：不改已提交的判据文件，只生成派生副本；
   注入块**不做任何判定**（结论由未改动的原判据给出），
   且写盘前用**逆变换逐行比对**断言「除注入块外与原文件相同」。
"""
import difflib
import sys
from pathlib import Path

SRC = Path('/Users/zhourui/code/steer3d/.cache/browser_verify/verify_path.mjs')
DST = Path('/Users/zhourui/code/steer3d/.cache/mutbak/r133a_path_earlyoverlay.mjs')
CDP = '/Users/zhourui/code/steer3d/.cache/browser_verify/cdp_client.mjs'

# ⚠⚠⚴ 锚点**必须带行首**：只写语句本身的话，`:246` 那处（带 2 空格缩进）
#   也会被**子串**计数命中 ⇒ 计数 2 ⇒ 守卫当场拦下（本轮实际发生过一次）。
ANCHOR = "\nawait page.eval(`document.querySelector('#tabPath').click(); true`);\nlet state = '';"

HEAD = "await page.eval(`document.querySelector('#tabPath').click(); true`);\n"
TAIL = "\nlet state = '';"

INJECT = r"""
// ===== r133a 注入：遮挡层提前到**取数之前** =====
// ⚠ 原脚本在 :257（取数之后 136 行）才加遮挡 ⇒ A2/A3 早已判完，变异碰不到它们。
// ⚠ 这里提前到取数之前，让 A2/A3 真的被遮住。
await sleep(1200);
const __r133a = JSON.parse(await page.eval(`JSON.stringify((() => {
  const ov = document.createElement('div');
  ov.id = '__earlyOverlay';
  ov.style.cssText = 'position:fixed;inset:0;background:#000;z-index:99999';
  document.body.appendChild(ov);
  const blk = document.querySelector('[data-pathblock]');
  const w = document.getElementById('pathWrap');
  const vp = el => { if(!el) return {ok:false, why:'no-el'};
    const r = el.getBoundingClientRect();
    if(r.height<=0) return {ok:false, why:'zero-height'};
    const x = Math.round(r.left + Math.min(r.width/2, 40));
    const y = Math.round(r.top + Math.min(r.height/2, 12));
    if (x<0||y<0||x>innerWidth||y>innerHeight) return {ok:false, why:'offscreen'};
    const hit = document.elementFromPoint(x,y);
    if(!hit) return {ok:false, why:'no-hit'};
    return { ok: !!(hit===el||el.contains(hit)||hit.contains(el)),
             why: (hit===el||el.contains(hit)||hit.contains(el)) ? '' : 'covered-by:'+(hit.id||hit.tagName) };
  };
  const a = vp(w), b = vp(blk);
  return { overlayAdded: !!document.getElementById('__earlyOverlay'),
           wrap: a, blk: b,
           // ⚠⚠⚴ 落地判据：遮挡层必须**真的**盖住了这两个容器。
           //   只是「元素加进去了」不算 —— 必须 __vp 自己判出 covered-by。
           landed: !a.ok && !b.ok && /covered-by/.test((a.why||'')+(b.why||'')) };
})())`));
// ⚠⚠⚴ **落地核验**：注入块自己不做判定，但**落地与否必须在这里核**，
//   否则「没遮住」会被读成「判据扛住了扰动」。
if (!__r133a.landed) {
  console.log('[扰动未落地] ' + JSON.stringify(__r133a));
  process.exit(2);
}
console.log('[扰动已落地] 遮挡层提前注入：#pathWrap ' + JSON.stringify(__r133a.wrap)
  + ' / [data-pathblock] ' + JSON.stringify(__r133a.blk));
"""


def main() -> int:
    src = SRC.read_text(encoding='utf-8')
    n = src.count(ANCHOR)
    if n != 1:
        print(f'[失败] 锚点出现 {n} 次（要求恰好 1）⇒ 判据文件结构变了，拒绝生成')
        return 2
    if "from './cdp_client.mjs'" not in src:
        print("[失败] 找不到 import './cdp_client.mjs' ⇒ 判据文件结构变了，拒绝生成")
        return 2
    if 'RESULT ${st}' not in src:
        print("[失败] 找不到汇总行 ⇒ 判据文件结构变了，拒绝生成")
        return 2
    # ⚠⚠⚴ 断言三件事实的顺序如文档所述 —— 本轮的结论建立在这些行号上
    i_cap = src.index('visWrap: window.__vp')
    i_a2 = src.index("check('A2 ")
    i_ov = src.index("d.id='__mutOverlay'")
    if not (i_cap < i_a2 < i_ov):
        print('[失败] 取数(:visWrap) → A2 判决 → 遮挡层 的顺序与文档不符，拒绝生成')
        return 2

    patched = src.replace("from './cdp_client.mjs'", f"from '{CDP}'")
    inj = HEAD + INJECT + TAIL
    out = patched.replace(ANCHOR, inj)
    back = out.replace(inj, ANCHOR)
    if back != patched:
        print('[失败] 去掉注入块后与派生源不一致，拒绝写盘')
        for l in list(difflib.unified_diff(patched.splitlines(), back.splitlines(), lineterm=''))[:20]:
            print('   ' + l)
        return 2
    if out.count('\ufffd'):
        print('[失败] 含 U+FFFD，拒绝写盘')
        return 2

    DST.write_text(out, encoding='utf-8')
    print(f'[已生成] {DST}')
    print(f'  原 {len(src.splitlines())} 行 → 副本 {len(out.splitlines())} 行')
    print('  锚点唯一（带行首）✓ · 取数→A2→遮挡层 顺序断言 ✓ · 除注入块外逐行相同 ✓')
    print('  ⚠ 注入块只加遮挡层，不做任何判定；结论由未改动的原判据给出')
    return 0


if __name__ == '__main__':
    sys.exit(main())