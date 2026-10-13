#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""r131a_gen.py —— 派生一份「把每条 check 的 detail 都印出来」的 verify_path 副本。

⚠ 为什么需要：`verify_path.mjs:283-284` 只在**判红**时打 `RED <name> <detail>`，
   全绿运行时**一条 detail 都不印**（实测 36/36 只输出 `RESULT OK 36/36`）。
   ⇒ 想量 C5–C9 的 needle 命中次数，只能先让判据**把自己的 needle 说出来**。

⚠⚠⚴ 纪律：**不改已提交的判据文件**，只生成派生副本；
   注入块**只加一行 console.log，不碰任何谓词**，
   且写盘前用**逆变换逐行比对**断言「除注入块外与原文件相同」。

⚠ 这样拿到的 needle 是**判据自己算的**，不是我重算的 ⇒ 零漂移。
"""
import difflib
import sys
from pathlib import Path

SRC = Path('/Users/zhourui/code/steer3d/.cache/browser_verify/verify_path.mjs')
DST = Path('/Users/zhourui/code/steer3d/.cache/mutbak/r131a_path_echo.mjs')
CDP = '/Users/zhourui/code/steer3d/.cache/browser_verify/cdp_client.mjs'

ANCHOR = "const check = (name, ok, detail = '') => { checks.push({ name, ok: !!ok, detail }); };"
REPLACE = ("const check = (name, ok, detail = '') => { checks.push({ name, ok: !!ok, detail });\n"
           "  // ===== r131a 注入：只加一行日志，**不改任何谓词** =====\n"
           "  console.log(`CHECK\\t${ok?'OK':'RED'}\\t${name}\\t${String(detail).replace(/\\n/g,' ⏎ ')}`);\n"
           "};")


def main() -> int:
    src = SRC.read_text(encoding='utf-8')
    n = src.count(ANCHOR)
    if n != 1:
        print(f'[失败] check 定义出现 {n} 次（要求恰好 1）⇒ 判据文件结构变了，拒绝生成')
        return 2
    if "from './cdp_client.mjs'" not in src:
        print("[失败] 找不到 import './cdp_client.mjs' ⇒ 判据文件结构变了，拒绝生成")
        return 2
    if 'RESULT ${st}' not in src:
        print("[失败] 找不到汇总行 ⇒ 判据文件结构变了，拒绝生成")
        return 2

    patched = src.replace("from './cdp_client.mjs'", f"from '{CDP}'")
    out = patched.replace(ANCHOR, REPLACE)
    back = out.replace(REPLACE, ANCHOR)
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
    print(f'  原 {len(src.splitlines())} 行 → 副本 {len(out.splitlines())} 行（+{len(out.splitlines()) - len(src.splitlines())}）')
    print('  check 定义唯一 ✓ · 除注入块外逐行相同 ✓ · import 已改绝对路径 ✓')
    print('  ⚠ 注入块只有一行 console.log，未触碰任何谓词')
    return 0


if __name__ == '__main__':
    sys.exit(main())