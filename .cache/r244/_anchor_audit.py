#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""_anchor_audit.py —— **变异台落点（锚点）审计**，**只查本轮改过的文件**（244.74 加）。

🔴🔴 **为什么要有这个**（244.74 自己踩的）：
   我改 `fixed_dose_feasible` 的 F1 时，把
       `ok1 = cpt >= float(need_cells)`   →   `ok1 = (cpt >= float(need_cells))`
   ⇒ ⇒ 多了一对括号 ⇒ ⇒ **变异台的落点串命中 0 次**
   ⇒ ⇒ 那条变异会被台架记成「落点命中 0 次 ⇒ 这条变异**无效**」
   ⇒ ⇒ ⛔ 而台架的 `rc` 变成 1 ⇒ ⇒ **那一轮白废**；更糟的是它看起来像「台架坏了」
   ⇒ ⇒ 所以：**改任何被变异台锚着的源码之后，必须重跑这个审计**。

⚖⚖⚖⚖⚖ **范围（关键）**：**只查「本轮改过的文件」**
   ⇒ ⇒ 因为台架的锚点**五花八门**（短到 `return False\n` 的都有 ⇒ 全目录扫会淹掉）
   ⇒ ⇒ 而**本轮改过的文件**才是我**有能力改坏**的那些
   ⇒ ⇒ 别的台架锚在**别的文件**上 ⇒ ⇒ 那不归我管（⛔ 不越界）

⚖⚖⚖⚖⚖ **判据**：
   ① 对**目标文件落在本轮改动集里**的台架 ⇒ 落点必须**恰好命中 1 次**
      （0 次 ⇒ 我把它改没了 ⇒ 那条变异**无效**；>1 次 ⇒ 落点不唯一 ⇒ 抓到了也不知道是哪处）
   ② 目标文件**不在**改动集里的台架 ⇒ **跳过**（⛔ 不越界、⛔ 不静默：只报一个计数）
   ③ 6 元组里第 2 项可能是**给人看的标签**（"tool" / "bander" / "layer"）
      ⇒ ⇒ 判据：**该目录下真的存在这个文件吗**

⚖ 用法：`python _anchor_audit.py <改动文件1> <改动文件2> ...`
   （不给参数 ⇒ 用 `.cache/r244` 里**本轮清单**——见 `FILES_24474`）
"""

import importlib.util
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# ⚖ 244.74 本轮改过 / 新增的文件（⛔ 只查这些）
FILES_24474 = (
    "dose_confound_audit.py",
    "dose_layer_audit.py",
    "fixed_dose_audit.py",
    "fixed_dose_density_audit.py",
    "mut_fixed_dose_density_audit.py",
    "fixed_dose_feasible.py",
    "mut_fixed_dose_feasible.py",
    "fixed_dose_dispatch.py",
    "pooled_mode_audit.py",
    "mut_pooled_mode_audit.py",
)


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _row_shape(row):
    """⚖ 返回 (anchor, repl, expect, 显式目标或 None)。"""
    if len(row) == 4:
        return row[1], row[2], None, None
    if len(row) == 5:
        return row[1], row[2], row[3], None
    if len(row) == 6:
        return row[2], row[3], row[4], row[1]
    return None, None, None, None


def main():
    d = os.path.dirname(os.path.abspath(__file__))
    args = sys.argv[1:]
    if args and os.path.isdir(args[0]):
        # ⚖ 给的是**目录** ⇒ 就用它当根 ⇒ 改动集取 `FILES_24474`（相对于它）
        d = os.path.abspath(args[0])
        args = []
    changed = args or list(FILES_24474)
    changed = [c if os.path.isabs(c) else os.path.join(d, c) for c in changed]
    texts = {}
    for c in changed:
        if os.path.isfile(c):
            texts[os.path.basename(c)] = io.open(c, encoding="utf-8").read()
    if not texts:
        print("⛔ 本轮改动集**一个文件都没读到** ⇒ 审计无效")
        return 2
    benches = sorted(f for f in os.listdir(d)
                     if f.startswith("mut_") and f.endswith(".py")
                     and not f.startswith("mut__"))
    checked = 0
    skipped = 0
    dead = []
    ambiguous = []
    for b in benches:
        try:
            mod = _load(os.path.join(d, b), "anch_" + b[:-3])
        except Exception as e:
            print("⚠ 台架 %s **读不进来**：%s" % (b, str(e)[:100]))
            continue
        rows = getattr(mod, "MUTATIONS", None)
        if rows is None:
            continue
        for row in rows:
            if not isinstance(row, (tuple, list)):
                continue
            anchor, repl, expect, explicit = _row_shape(row)
            if anchor is None:
                continue
            target = None
            if explicit and os.path.exists(os.path.join(d, explicit)):
                target = explicit
            else:
                cand = b[len("mut_"):]
                if cand in texts:
                    target = cand
            if target is None or target not in texts:
                skipped += 1
                continue
            checked += 1
            n = texts[target].count(anchor)
            if n == 0:
                dead.append((row[0], b, target))
            elif n > 1:
                ambiguous.append((row[0], b, target, n))
    print("落点审计：改动集 %d 个文件 ｜ 台架 %d 个 ｜ **查了 %d 条落点**（跳过 %d 条："
          "锚在**别的**文件上，⛔ 不越界）" % (len(texts), len(benches), checked, skipped))
    if dead:
        print("⛔ **落点失效 %d 条**（⇒ 我把这个落点改没了 ⇒ 那条变异**无效**）：" % len(dead))
        for mid, b, t in dead:
            print("    %s（台架 %s ｜ 文件 %s）" % (mid, b, t))
    if ambiguous:
        print("⚠ **落点不唯一 %d 条**（⇒ 当场人工看）：" % len(ambiguous))
        for mid, b, t, n in ambiguous:
            print("    %s（台架 %s ｜ 文件 %s ｜ 命中 %d 次）" % (mid, b, t, n))
    print("落点审计：%s" % ("✅ 全过" if (not dead and not ambiguous) else "⛔ 不过"))
    return 0 if (not dead and not ambiguous) else 1


if __name__ == "__main__":
    sys.exit(main())
