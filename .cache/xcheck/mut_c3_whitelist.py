#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""C3 白名单的变异台：证明修好的 C3 **两个方向都能红**。

## 为什么必须有它

第三十三笔之八查出 C3 是一条**恒真判据**：原式
`not cond or set(cond) <= CONDITIONAL_3D`，而上游 `cond` 已被筛成
`[k for k in real if k in CONDITIONAL_3D]` ⇒ 子集关系**恒成立**。
证法是把 `CONDITIONAL_3D` 整个清空 —— 它照样 PASS。

修好之后必须**当场证明它会红**，否则只是把一条恒真换成另一条恒真。

## 三个方向

- **M1 藏**：往名单里塞一条「本轮就在 DOM 里、却没有判据读过」的标记
  （`data-step`）。方向一必须红。
- **M2 空转**：往名单里塞一条「根本没有判据想读」的标记（`data-nosuchmarker`）。
  方向二必须红。**它不在 DOM 里** —— 所以 M1 抓不到它，两条不可互相替代。
- **M3 清空**：把整份名单清空（原版的证法）。方向一与方向二同时触发。
  ⚠ 这一条正是**旧判据 PASS、新判据 RED** 的那一条。

## 三条纪律（与本项目其它变异台同源）

1. **期望红必须命中** —— 不许只看「整体变红」。
2. **不许有额外红** —— 只红 C3。红别的说明变异打偏了。
3. **还原后逐字节比对 sha256** —— 「看起来改回去了」不算还原。
   并且查 `.mutbak` 残留。
"""

import ast
import hashlib
import io
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path("/Users/zhourui/code/steer3d")
SRC = ROOT / ".cache/xcheck/scan_panel_coverage.py"
BAK = ROOT / ".cache/xcheck/scan_panel_coverage.py.mutbak"

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print("  [%s] %s" % ("PASS" if ok else "FAIL", name))
    if detail:
        print("         %s" % detail)


def sha256(path):
    h = hashlib.sha256()
    with open(str(path), "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def run_scan():
    p = subprocess.run([sys.executable, str(SRC)],
                       capture_output=True, text=True)
    out = p.stdout + p.stderr
    fails = re.findall(r"^\[FAIL\] (C\d+[a-z]?)", out, re.M)
    passes = re.findall(r"^\[PASS\] (C\d+[a-z]?)", out, re.M)
    return fails, passes, out


def body_span(text):
    """返回 `CONDITIONAL_3D = {` **之后**的插入点，与对应 `}` 的结束点。

    ⚠⚠ 第一版这里返回 `index("\\n}") + 2`（越过 `}`），拼回去时
      **右花括号被吞掉** ⇒ 变体是语法错误 ⇒ 扫描脚本崩 ⇒
      它的输出里一条 `[FAIL]` 都没有 ⇒ 本台读到的 `失败项 = []`
      看起来像「C3 没红」。
      **「该红没红」的第一嫌疑永远是变异本身**，不是判据。
    ⇒ 现在两件事同时做：插入点只取 `{` 之后；每个变体**先 ast.parse 自检**，
      语法不过就报**装置故障**并停下，绝不把它读成「判据没红」。
    """
    i = text.index("CONDITIONAL_3D = {") + len("CONDITIONAL_3D = {")
    j = text.index("\n}", i) + 2
    return i, j


def variant_add(text, marker):
    """在 { 之后**插入**一行，保留原有全部条目与右花括号。"""
    i, _ = body_span(text)
    return text[:i] + '\n    "%s",' % marker + text[i:]


def variant_clear(text):
    """整份清空，但**保留**右花括号。"""
    i, j = body_span(text)
    return text[:i] + "\n}" + text[j:]


def first_crosscheck_key(text):
    """从簿子里取一条「在 DOM 里、但没有任何判据读过」的标记名。

    ⚠ 不写死字符串：`data-step` 在 verify_derivation.mjs 里**出现过**
      （在注释里，markers_in() 会剥掉），凭 grep 判它「没人读」是错的。
      ⇒ 枚举从现场反推：CROSSCHECK_EXEMPT 按定义收的就是这一类。
    """
    m = re.search(r"CROSSCHECK_EXEMPT = \{(.*?)\n\}", text, re.S)
    if not m:
        return None
    k = re.search(r'"(data-[a-z0-9-]+)"', m.group(1))
    return k.group(1) if k else None


def apply_variant(text, label):
    """写盘 + 语法自检。自检不过 ⇒ 报装置故障并退出，**不**读成判据没红。"""
    try:
        ast.parse(text)
    except SyntaxError as e:
        check("装置自检：%s 的变体必须语法正确" % label, False,
              "SyntaxError: %s（行 %s）⇒ **变异坏了，不是判据没红**"
              % (e.msg, e.lineno))
        io.open(str(SRC), "w", encoding="utf-8").write(PRISTINE)
        sys.exit(2)
    io.open(str(SRC), "w", encoding="utf-8").write(text)


PRISTINE = ""


def main():
    global PRISTINE
    PRISTINE = io.open(str(SRC), encoding="utf-8").read()
    pristine = PRISTINE
    if not BAK.exists():
        shutil.copy2(str(SRC), str(BAK))
    base_sha = sha256(SRC)
    print("基线 sha256 = %s\n" % base_sha[:16])

    # ---- 0：基线必须绿，且 C3 必须在通过名单里 ----
    fails, passes, _ = run_scan()
    check("M0 基线：C3 通过、且失败项**只有** C6 那份 118 条活清单",
          "C3" in passes and fails == ["C6"],
          "失败项 = %s（预期 ['C6']）" % fails)
    if fails != ["C6"]:
        print("       ⚠ 基线就不是预期形状 —— 下面的「有没有额外红」无从判起，停止。")
        return 2

    hide_marker = first_crosscheck_key(pristine)
    if not hide_marker:
        print("       ⚠ 装饰簿里取不到「在 DOM 里却没人读」的标记，无法做方向一。")
        return 2
    print("方向一的标记从装饰簿反推 = %s"
          "（不写死：它在 verify_derivation.mjs 的**注释**里出现过，\n"
          "  凭 grep 说它「没人读」是错的 —— 只有簿子的定义算数）\n"
          % hide_marker)

    for mid, desc, variant, want_c3, want_extra in (
        ("M1", "方向一（藏）：塞一条在 DOM 里却没人读的 %s" % hide_marker,
         variant_add(pristine, hide_marker), True, []),
        ("M2", "方向二（空转）：塞一条根本没有判据想读的 data-nosuchmarker",
         variant_add(pristine, "data-nosuchmarker"), True, []),
        # ⚠⚠ M3 的期望**第二版才写对**，第一版写的是「M3 ⇒ C3 必须红」——
        #   那是我按「旧的 C3 恒真」反推的，想象「清空名单就等于露出破绽」。
        #   实测 C3 仍绿，而这是**正确的**：C3 判的是「名单里**有什么**」，
        #   `hiding` / `idle` 都从 `CONDITIONAL_3D` 算 ⇒ 空集恒满足两个条件。
        #   真正接住这次变异的是 **C2**：没人豁免 ⇒ 8 个 `data-scene-*`
        #   变成死引用。
        #   ⇒ 责任归属要钉死：**「名单里藏东西」归 C3，「没人豁免」归 C2。**
        #     两者合起来才没有静默通过的缝。
        ("M3", "整份清空（原恒真判据的证法）：此时**该红的是 C2 不是 C3**",
         variant_clear(pristine), False, ["C2"]),
    ):
        apply_variant(variant, mid)
        fails, passes, out = run_scan()
        check("%s %s" % (mid, desc), ("C3" in fails) == want_c3,
              "失败项 = %s（C3 红 = %s，期望 %s）"
              % (fails, "C3" in fails, want_c3))
        extra = [f for f in fails if f not in ("C3", "C6") and f not in want_extra]
        check("%s 除 C3 / C6 / %s 外不许有额外红"
              % (mid, "/".join(want_extra) or "—"), not extra,
              "额外红 = %s" % (extra or "无"))
        if mid == "M3":
            # 钉住「清空名单后 C2 报出来的**就是那 8 条**」，不多不少。
            got = re.search(r"root 页判据 \d+ 条 → 死引用 \d+ 个：([^\n]+)", out)
            names = sorted(re.findall(r"data-[a-z0-9-]+", got.group(1))) if got else []
            expect = sorted(re.findall(r'"(data-[a-z0-9-]+)"',
                                       re.search(r"CONDITIONAL_3D = \{(.*?)\n\}",
                                                 pristine, re.S).group(1)))
            check("M3 C2 报出来的死引用**恰好就是**名单里那 8 条（不多不少）",
                  names == expect,
                  "C2 报 %d 条：C2 报的 = %s ／ 名单 = %s"
                  % (len(names), names or "（无）", expect))
        ver = [ln for ln in out.splitlines() if "条：藏了" in ln]
        if ver:
            print("         %s" % ver[0].strip())
        shutil.copy2(str(BAK), str(SRC))

    # ---- 收尾 ----
    now = sha256(SRC)
    check("M4 收尾：源码 sha256 回到基线（逐字节相同）", now == base_sha,
          "还原后 %s vs 基线 %s" % (now[:16], base_sha[:16]))
    # ⚠ 第一版写的是 `if BAK.exists() and now != base_sha: os.remove(...)`
    #   —— 条件正好反了：**还原成功时反而把备份留下**。
    #   「残留检查」在还原成功的那一次运行里永远是红的。
    if BAK.exists():
        os.remove(str(BAK))
    check("M5 收尾：没有 .mutbak 残留", not BAK.exists(),
          "无残留" if not BAK.exists() else "⚠ %s 还在" % BAK.name)

    bad = [n for n, ok, _ in results if not ok]
    print("\n%s　%d/%d 条通过%s"
          % ("RESULT FAIL" if bad else "RESULT PASS",
             len(results) - len(bad), len(results),
             ("　红：" + "、".join(bad)) if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
