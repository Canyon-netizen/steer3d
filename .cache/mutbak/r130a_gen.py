#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""r130a_gen.py —— 从已提交的 verify_patch.mjs 派生一份「判决表被摘掉」的副本。

⚠⚠⚴ 纪律：**不改已提交的判据文件**，只生成派生副本。
   派生副本与原文件**只差一个注入块**，本脚本在写盘前逐条断言：
     ① 锚点唯一（切 tabPatch 那一段在原文件里只出现一次）
     ② 除注入块外，两文件逐行相同（用去掉注入块后的逆变换比对）
     ③ import 相对路径已改写成绝对路径（副本不在同一目录）

⚠ 为什么值得做：逐条扰动能证明「某条判据靠某个词活着」，
   但答不出「**这一族里到底有几条是虚的**」。
   把判决表整张摘掉再跑一遍真实判据，一次就能列全。
"""
import difflib
import sys
from pathlib import Path

SRC = Path('/Users/zhourui/code/steer3d/.cache/browser_verify/verify_patch.mjs')
DST = Path('/Users/zhourui/code/steer3d/.cache/mutbak/r130a_patch_notable.mjs')
CDP = '/Users/zhourui/code/steer3d/.cache/browser_verify/cdp_client.mjs'

ANCHOR = """    b.click();
  })()`);
  await sleep(2500);
"""

INJECT = """    b.click();
  })()`);
  await sleep(2500);

  // ===== r130a 注入：把判决表整张摘掉，再让原判据原样跑 =====
  // ⚠ 注入块只做一件事；**不在这里做任何判定**，
  //   所有结论都由下面未改动的原判据给出 ⇒ 谓词零漂移。
  const __r130a = JSON.parse(await page.eval(`JSON.stringify((() => {
    const wrap = document.getElementById('patchWrap');
    const g = document.querySelector('#patchWrap [data-gate]');
    const t = g ? g.closest('table') : null;
    if (!t) return { landed:false, why:'找不到 [data-gate] 的祖先 table' };
    const rowsBefore = t.querySelectorAll('tr').length;
    const wrapBefore = (wrap ? wrap.innerText : '').length;
    const innerBefore = (t.innerText || '').length;
    t.remove();
    const wrapAfter = (wrap ? wrap.innerText : '').length;
    const left = document.querySelectorAll('#patchWrap [data-gate]').length;
    return { landed:true, rowsBefore, wrapBefore, innerBefore, wrapAfter, gatesLeft:left };
  })())`));
  // ⚠⚠⚴ **落地核验**：摘掉之后 [data-gate] 必须真的一个都不剩。
  //   没剩 ⇒ 扰动没生效 ⇒ 这一轮**不算判据结论**，直接 exit 2。
  if (!(__r130a.landed && __r130a.gatesLeft === 0)) {
    console.log('[扰动未落地] ' + JSON.stringify(__r130a));
    process.exit(2);
  }
  console.log('[扰动已落地] 判决表整张摘掉：tr ' + __r130a.rowsBefore + ' 行、自身 innerText '
    + __r130a.innerBefore + ' 字；#patchWrap.innerText ' + __r130a.wrapBefore + ' → '
    + __r130a.wrapAfter + ' 字（−' + (__r130a.wrapBefore - __r130a.wrapAfter)
    + '）；残留 [data-gate] ' + __r130a.gatesLeft + ' 个');
"""


def main() -> int:
    src = SRC.read_text(encoding='utf-8')

    # ① 锚点唯一
    n = src.count(ANCHOR)
    if n != 1:
        print(f'[失败] 锚点在 verify_patch.mjs 里出现 {n} 次（要求恰好 1）⇒ 判据文件结构变了，拒绝生成')
        return 2

    # ③ import 相对路径改绝对
    if "from './cdp_client.mjs'" not in src:
        print("[失败] 找不到 import './cdp_client.mjs' ⇒ 判据文件结构变了，拒绝生成")
        return 2
    patched = src.replace("from './cdp_client.mjs'", f"from '{CDP}'")

    out = patched.replace(ANCHOR, INJECT)

    # ② 除注入块外逐行相同（把注入块从产物里摘掉，应逐行还原成 patched）
    back = out.replace(INJECT, ANCHOR)
    if back != patched:
        print('[失败] 去掉注入块后与派生源不一致 ⇒ 改动了不该改的地方，拒绝写盘')
        for l in list(difflib.unified_diff(patched.splitlines(), back.splitlines(), lineterm=''))[:20]:
            print('   ' + l)
        return 2

    dl = [l for l in difflib.unified_diff(patched.splitlines(), out.splitlines(), lineterm='')
          if l[:1] in '+-' and l[:3] not in ('---', '+++')]
    if out.count('\ufffd') or patched.count('\ufffd'):
        print('[失败] 含 U+FFFD，拒绝写盘')
        return 2

    DST.write_text(out, encoding='utf-8')
    print(f'[已生成] {DST}')
    print(f'  原文件 {len(src.splitlines())} 行 → 副本 {len(out.splitlines())} 行（+{len(out.splitlines()) - len(src.splitlines())}）')
    print(f'  差异行 {len(dl)} 条（应全是注入块）· U+FFFD {out.count(chr(0xfffd))} · 以\\n结尾 {out.endswith(chr(10))}')
    print(f'  锚点 1 处 ✓ · 除注入块外与原文件逐行相同 ✓ · import 已改绝对路径 ✓')
    return 0


if __name__ == '__main__':
    sys.exit(main())