#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""r130b_gen.py —— 派生「篡改 [data-patch-fails] 块」的两臂副本，证伪 P4。

⚠⚠⚴⚠ 为什么怀疑 P4 空洞（纯读代码即可推出，本脚本用实验钉死）：

    verify_patch.mjs:145-150
      rec('P4 「N/M 道门没有通过」那一块**可见且把判否/没测都点了名**',
        vis.fails.ok && (fails.length + nas.length === 0
          ? /没有通过/.test(vis.failsTxt)
          : fails.length + nas.length === 0 || new RegExp('没测').test(vis.failsTxt)), ...)

    实测 fails=7、nas=13 ⇒ 和为 20 ≠ 0 ⇒ **走 else 分支**
      ⇒ P4 ≡  vis.ok && /没测/.test(vis.failsTxt)

    ⚠ 判据名承诺「把**判否/没测都点了名**」，
      实现**只查块里有没有「没测」这两个字** ——
      不核 `20 / 29` 这个数，不核任何一个门名。

⚠⚠⚴ 两臂缺一不可：
  A（攻击臂）：数字改成 99/99、名单整段删掉，**只留「没测」二字**
      ⇒ 若 P4 仍绿 ⇒ P4 既不核数字也不核名单
  B（负对照）：与 A 完全相同，**连「没测」也去掉**
      ⇒ 若 P4 转红 ⇒ 说明 A 的绿确实来自那两个字，实验有区分力
      ⇒ 若 B 仍绿 ⇒ P4 连「没测」都不核，病更重

⚠ `data-patch-fails` 在判据文件里**只出现 1 次**（:125）⇒ 只有 P4 读它
  ⇒ 扰动只影响 P4，归因干净。

⚠ 纪律：不改已提交的判据文件，只生成派生副本；注入块只改页面状态，
  **所有判定仍由未改动的原判据给出** ⇒ 谓词零漂移。
"""
import difflib
import json
import sys
from pathlib import Path

SRC = Path('/Users/zhourui/code/steer3d/.cache/browser_verify/verify_patch.mjs')
DST = Path('/Users/zhourui/code/steer3d/.cache/mutbak/r130b_patch_fails.mjs')
CDP = '/Users/zhourui/code/steer3d/.cache/browser_verify/cdp_client.mjs'

ANCHOR = """    b.click();
  })()`);
  await sleep(2500);
"""

# ⚠ 两臂文本：A 留「没测」，B 不留。其余部分**逐字相同** —— 这是 B 作为负对照的前提。
ARM_A = "99 / 99 道门没有通过｜不成立：［名单已整段删除］｜没测"
ARM_B = "99 / 99 道门没有通过｜不成立：［名单已整段删除］｜本页未覆盖"

INJECT = """    b.click();
  })()`);
  await sleep(2500);

  // ===== r130b 注入：篡改 [data-patch-fails] 块，让下面**未改动**的原判据原样判 =====
  // ⚠ 注入块只改页面状态，不做任何判定 ⇒ 结论全由原判据给出。
  const __arm = (process.env.R130B_ARM || 'A').toUpperCase();
  const __TEXT = __arm === 'B' ? %(ARM_B)s : %(ARM_A)s;
  const __r130b = JSON.parse(await page.eval(`JSON.stringify((() => {
    const f = document.querySelector('[data-patch-fails]');
    if (!f) return { landed:false, why:'找不到 [data-patch-fails]' };
    const before = (f.innerText || '').trim();
    const boxBefore = f.getBoundingClientRect();
    f.innerText = ${JSON.stringify(__TEXT)};
    const after = (f.innerText || '').trim();
    const box2 = f.getBoundingClientRect();
    return { landed: after === ${JSON.stringify(__TEXT)},
             beforeLen: before.length, after: after,
             w0: boxBefore.width, h0: boxBefore.height,
             w: box2.width, h: box2.height };
  })())`));

  // ⚠⚠⚴ **落地核验**：回读的块文本必须与要写进去的**逐字相同**，否则不算落地。
  //   ⚠ 这道守卫在本轮**当场拦下过一次坏扰动**（拼接写错，落地文本成了 "undefined"）
  //   ⇒ 它不是装饰，是这一族实验能不能算数的前提。
  if (!__r130b.landed) {
    console.log('[扰动未落地] ' + JSON.stringify(__r130b));
    process.exit(2);
  }
  console.log('[扰动已落地] 臂 ' + __arm + '：块原文 ' + __r130b.beforeLen
    + ' 字（' + __r130b.w0 + '×' + __r130b.h0 + '）→ 改写为 '
    + JSON.stringify(__r130b.after) + '（' + __r130b.after.length
    + ' 字，' + __r130b.w + '×' + __r130b.h + '）');
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
    if src.count('data-patch-fails') != 1:
        print(f"[失败] data-patch-fails 在源文件出现 {src.count('data-patch-fails')} 次（要求 1）"
              "⇒ 它不再只被 P4 读，扰动会污染别的判据，拒绝生成")
        return 2

    patched = src.replace("from './cdp_client.mjs'", f"from '{CDP}'")
    inj = INJECT % {'ARM_A': json.dumps(ARM_A, ensure_ascii=False),
                    'ARM_B': json.dumps(ARM_B, ensure_ascii=False)}
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
    print(f'  锚点唯一 ✓ · data-patch-fails 源文件中恰好 1 处 ✓ · 除注入块外逐行相同 ✓')
    print(f'  臂 A 文本 = {ARM_A!r}')
    print(f'  臂 B 文本 = {ARM_B!r}')
    print(f'  ⚠ 两臂除「没测/本页未覆盖」外逐字相同 = {ARM_A.replace("没测", "§") == ARM_B.replace("本页未覆盖", "§")}')
    return 0


if __name__ == '__main__':
    sys.exit(main())