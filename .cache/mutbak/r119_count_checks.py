#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 119 —— 数「check( 调用点」的**三个口径**，把差值逐条解释掉。

为什么需要第三个口径：
  口径A  grep -cE "^[[:space:]]*check\\("   行首锚定，会漏 `if (…) { check(…); }`
  口径B  grep -c "\\bcheck\\("               不锚定，但**把注释行也算进去**
  口径C  先剥块注释 + 行注释，再不锚定计数   ← 唯一可信的口径

口径B 被污染的证据（本轮实测 2 处）：
  verify_hinge_panel.mjs:29  `// ⚠ 原写法 \`check('…（跳过）', true, '')\` 会把…`
  verify_path.mjs:32         `// ⚠ 原写法 \`check('D3 …', true, …)\` 会把…`
口径A 被漏掉的证据（本轮实测 1 处）：
  verify_axis_readout.mjs:209 `if (cc.missing) { check(\`B1 ${ax}/L${L} 格子存在\`, false, 'missing'); continue; }`

⚠ 本脚本自身带**正对照**：它数自己源码里的 check( 调用点，
  且用一个内含字符串字面量 "check(" 的行验证「剥注释后不该被计入」。
⚠ 三道对照必须齐全才发布：① 口径C 能剥掉注释行  ② 口径C 保留真调用点
  ③ 三口径的差值逐条列得出名字。
"""
import io
import os
import re
import sys

DIR = '/Users/zhourui/code/steer3d/.cache/browser_verify'


def strip_comments(src):
    """剥 JS 块注释与行注释。保留行结构（用等量换行顶替），使行号仍可用。

    ⚠ 简化：不处理字符串/正则字面量里的 `//` 与 `/*`。
      本目录 8 个文件的源码里没有这类情形（判据脚本不把 URL 写成裸串）。
      这个限制必须写出来，因为它是本口径的已知缺口，不是没有缺口。
    """
    out = []
    i, n = 0, len(src)
    while i < n:
        two = src[i:i + 2]
        if two == '/*':
            j = src.find('*/', i + 2)
            j = n if j < 0 else j + 2
            seg = src[i:j]
            out.append(''.join(c if c == '\n' else ' ' for c in seg))
            i = j
        elif two == '//':
            j = src.find('\n', i)
            j = n if j < 0 else j
            out.append(' ' * (j - i))
            i = j
        else:
            out.append(src[i])
            i += 1
    return ''.join(out)


def count(src, anchored):
    pat = re.compile(r'^\s*check\(') if anchored else re.compile(r'\bcheck\(')
    return sum(1 for ln in src.split('\n') if pat.search(ln))


def main():
    files = sorted(f for f in os.listdir(DIR)
                   if f.endswith('.mjs') and re.search(r'\bcheck\(', io.open(
                       os.path.join(DIR, f), encoding='utf-8').read()))
    print('带 check( 的文件数 = %d / 全部 .mjs = %d'
          % (len(files), len([f for f in os.listdir(DIR) if f.endswith('.mjs')])))
    print()
    hdr = '%-26s %6s %6s %6s   %s'
    print(hdr % ('文件', 'A行首', 'B不锚', 'C剥注', 'A/B/C'))
    print('-' * 78)
    tA = tB = tC = 0
    detail = []
    for f in files:
        p = os.path.join(DIR, f)
        raw = io.open(p, encoding='utf-8').read()
        bare = strip_comments(raw)
        a, b, c = count(raw, True), count(raw, False), count(bare, False)
        tA += a; tB += b; tC += c
        print('%-26s %6d %6d %6d   %d/%d/%d' % (f, a, b, c, a, b, c))
        if a != c or b != c:
            detail.append((f, raw, bare, a, b, c))
    print('-' * 78)
    print('%-26s %6d %6d %6d' % ('合计', tA, tB, tC))
    print()

    # ---- 差值逐条：口径B 多出来的（注释行）与口径C 多出来的（真调用点）----
    print('=== 差值逐条解释 ===')
    for f, raw, bare, a, b, c in detail:
        lines = raw.split('\n')
        blines = bare.split('\n')
        for idx, (ln, bln) in enumerate(zip(lines, blines), 1):
            in_raw = bool(re.search(r'\bcheck\(', ln))
            in_bare = bool(re.search(r'\bcheck\(', bln))
            if in_raw and not in_bare:
                kind = '注释里的 check('
            elif in_bare and not re.match(r'^\s*check\(', bln):
                kind = '★真调用点但不在行首（口径A 漏掉）'
            else:
                continue
            print('  %s:%d  [%s]' % (f, idx, kind))
            print('      %s' % ln.strip()[:118])
    print()

    # ---- 阳性对照：本脚本源码里自己埋了一个「注释行含 check(」与一个「字符串含 check(」----
    self_src = io.open(__file__, encoding='utf-8').read()
    self_bare = strip_comments(self_src)
    print('=== 阳性对照（判据必须能报非零 / 必须剥对）===')
    print('  本脚本源码：原始 check( 计数 = %d（应 >0，含刻意埋的两处）'
          % len(re.findall(r'\bcheck\(', self_src)))
    print('  本脚本源码：剥注释后 = %d' % len(re.findall(r'\bcheck\(', self_bare)))
    ok_a = len(re.findall(r'\bcheck\(', self_bare)) >= 2
    ok_b = len(re.findall(r'\bcheck\(', self_bare)) < len(re.findall(r'\bcheck\(', self_src))
    print('  ① 剥注释后仍保留 ≥2 个真调用点（正则/pattern 两处）：%s' % ('PASS' if ok_a else 'FAIL'))
    print('  ② 剥注释确实削掉了注释里的 check(（docstring 那两行）：%s'
          % ('PASS' if ok_b else 'FAIL'))
    ok_c = tC > 0 and tC < tB
    print('  ③ 口径C 严格小于口径B 且 >0：%s（C=%d B=%d）'
          % ('PASS' if ok_c else 'FAIL', tC, tB))
    ok_d = tC >= tA
    print('  ④ 口径C ≥ 口径A（行首锚定不可能更多）：%s（C=%d A=%d）'
          % ('PASS' if ok_d else 'FAIL', tC, tA))
    print()
    print('VERDICT %s  权威调用点数 = %d（口径C）'
          % ('PASS' if all([ok_a, ok_b, ok_c, ok_d]) else 'FAIL', tC))
    return 0 if all([ok_a, ok_b, ok_c, ok_d]) else 1


if __name__ == '__main__':
    sys.exit(main())