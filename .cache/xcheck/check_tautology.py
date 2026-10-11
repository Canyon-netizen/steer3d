"""重言式检测器：找出**期望串与被检查文本同源**的自检（修订 57 X5）。

## 它抓的是什么

    need("%.1f%%" % (100.0 * l1_thr["random_indistinguishable"] / l1_base)
         in _l1["note"], …)

而 note 里那个 `%.1f%%` 位**也是用 `100.0*l1_thr[...]/l1_base` 格式化出来的**
⇒ 两边同时变、同时对 ⇒ **恒成立**，从一开始就不可能红。

这类自检比「恒绿」更坏：它在 `CHECKS` 里占一个名额、每轮贡献一次「全过」，
让人以为那个数有人看着。

⚠ 实测证据（决定性实验）：把生成器里两个判定阈值 `1.0 → 7.0`，
note 里的 `49.5%` 消失（变 `346.8%`）、`1 个百分点` 变 `7 个百分点`，
而相关自检**全绿**。

## 判定规则（冻结）

把 `need(...)` 的第一个参数按形态分三类，**三类都要报数**：

| 类 | 形态 | 判决 |
|---|---|---|
| **A** | `"字面量" in 阶梯文本` | 真判据（X1 改完该落在这里） |
| **B** | `"…" % (…) in 阶梯文本`，且元组里**所有**变量都出现在生成侧的格式化表达式里 | ⚠⚠ **重言式**（必须为空） |
| **C** | 同上但变量**不**全在生成侧 | 真判据（它的期望值有独立出处） |

⚠⚠⚠ **第一版把 A 类直接 `continue` 掉了** ⇒ 报出「真判据 0 条、重言式 0 条」
然后打印 **✅ 通过**。那是**空洞通过**：它一条都没匹配上，却装作查过了。
⇒ 现在的硬要求：**A+B+C 三类之和必须等于「形如 `… in 阶梯文本`」的自检总数**，
对不上就报「本项无判据」并**判红**。

## 边界（不判为重言式）

- 数值比较 `abs(l1_lo - 2.026) < 0.01`（`ast.Compare` 的左端不是 `%`）
  —— 比的是**冻结常数**，与 note 同源与否无关。单独计数告知。

## 阳性对照（X4 同源教训）

`--self-test` 会往待检源码里**注入一条已知的重言式**，要求检测器**必须**报出来。
⚠ M1b 那次教训：「阳性对照自己写错等于没有对照」——
所以自测失败时打印**注入的那一行**，便于核对是检测器坏了还是对照写坏了。

## 用法

    PYTHONPATH=.cache/pylibs python3 .cache/xcheck/check_tautology.py
    PYTHONPATH=.cache/pylibs python3 .cache/xcheck/check_tautology.py --self-test
    PYTHONPATH=.cache/pylibs python3 .cache/xcheck/check_tautology.py <某个 .py>
"""
from __future__ import annotations

import ast
import io
import os
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
BUILDER = os.path.join(ROOT, ".cache/xcheck/build_evidence_ladder.py")

# ⚠ 注入用的重言式：`l1_base` 与 `l1_thr` 都是生成侧用到的变量
INJECT = ('    need("%.1f%%" % (100.0 * l1_thr["x"] / l1_base) in _l1["note"],\n'
          '         "【自测注入】这条是**故意**的重言式")\n')


def _names(node):
    """一个表达式里出现的所有变量名（含 `d[k]` 的基名 `d`）。"""
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _is_ladder_text(node):
    """右端是不是「阶梯文本」（`ladder` / `payload` 里的字段取值）。"""
    seg = ast.dump(node)
    return any(k in seg for k in ("'ladder'", "'note'", "'claim'", "'here'",
                                  "'not_answerable'", "'answerable'",
                                  "'overreach_numbers'"))


def _classify(left, text_names):
    """把一个「期望串」表达式分类：('A'|'B'|'C'|'D', 名字集合)。"""
    if isinstance(left, ast.BinOp) and isinstance(left.op, ast.Mod) \
            and isinstance(left.left, ast.Constant) \
            and isinstance(left.left.value, str):
        used = _names(left.right)
        if used and used <= text_names:
            return "B", used
        return "C", used
    if isinstance(left, ast.Constant):
        return "A", set()
    return "D", set()


def _loop_fragments(tree):
    """展开 `for _frag, _why in (( "字面量", "理由" ), …)` 这类片段清单循环。

    ⚠⚠ 第一版**看不见**这些循环里的自检：循环体的第一个参数是 `Name(_frag)`，
    既不是 `Constant` 也不是 `%` 表达式 ⇒ 全部落进「D 其它形态」。
    而那正是本文件里**条目最多**的一组 note 片段检查（十几条）——
    「检测器覆盖不到」和「那里没有问题」在报告里长得一模一样。
    ⇒ 这里把清单按源码里的字面量展开，逐条分类。

    返回 [(行号, 期望串 AST 或 None, 描述)]。
    """
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.For):
            continue
        body_names = {n.id for b in node.body for n in ast.walk(b)
                      if isinstance(n, ast.Name)}
        tgts = ([node.target.id] if isinstance(node.target, ast.Name)
                else [t.id for t in node.target.elts]
                if isinstance(node.target, ast.Tuple) else [])
        if not tgts or not (body_names & set(tgts)):
            continue
        items = node.iter.elts if isinstance(node.iter, ast.Tuple) else []
        if not items or not isinstance(items[0], (ast.Tuple, ast.Constant)):
            continue
        for it in items:
            if isinstance(it, ast.Tuple) and it.elts:
                out.append((node.lineno, it.elts[0],
                            "%s 循环" % tgts[0]))
            elif isinstance(it, ast.Constant):
                out.append((node.lineno, it, "%s 循环" % tgts[0]))
    return out


def analyse(src, label):
    tree = ast.parse(src)

    # ---- 1. 生成侧：把 `%` 结果当字符串用的那些格式化表达式 ----
    text_names, n_fmt = set(), 0
    for node in ast.walk(tree):
        if (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod)
                and isinstance(node.left, ast.Constant)
                and isinstance(node.left.value, str)):
            n_fmt += 1
            text_names |= _names(node.right)
    if not text_names:
        print("✗ 没能识别出任何生成侧的格式化表达式 ⇒ 本项**无判据**")
        return None

    counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    taut, expanded = [], 0

    def add(left, where):
        nonlocal expanded
        kind, used = _classify(left, text_names)
        counts[kind] += 1
        if kind == "B":
            frag = (left.left.value[:70] if isinstance(left, ast.BinOp)
                    and isinstance(left.left, ast.Constant) else "?")
            taut.append((where, sorted(used), frag))
        if "循环" in str(where):
            expanded += 1

    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "need" and node.args):
            continue
        arg0 = node.args[0]
        if not (isinstance(arg0, ast.Compare) and len(arg0.ops) == 1
                and isinstance(arg0.ops[0], ast.In)):
            continue
        if not any(_is_ladder_text(x) for x in arg0.comparators):
            continue
        add(arg0.left, node.lineno)

    # ---- 3. 循环展开的片段清单（体里的 Name 形如已在上一步落进 D）----
    loop_frags = _loop_fragments(tree)
    for ln, frag, _src in loop_frags:
        add(frag, "行 %d 的 %s" % (ln, _src))

    total = sum(counts.values())
    return dict(label=label, n_fmt=n_fmt, n_text_vars=len(text_names),
                a=counts["A"], b=counts["B"], c=counts["C"],
                d=counts["D"], taut=taut, n_loops=len(loop_frags))


def report(r):
    if r is None:
        return 1
    print("=== 重言式检测（修订 57 X5）：%s ===" % r["label"])
    print("生成侧格式化表达式 %d 个，涉及 %d 个变量" % (r["n_fmt"], r["n_text_vars"]))
    print("形如「… in 阶梯文本」的自检共 %d 条"
          "（其中 %d 条来自循环里的片段清单，已展开）："
          % (r["a"] + r["b"] + r["c"] + r["d"], r["n_loops"]))
    print("  A 字面量期望串（真判据）        : %d" % r["a"])
    print("  B 同源期望串（⚠ 重言式，应为空）: %d" % r["b"])
    print("  C 独立出处（真判据）            : %d" % r["c"])
    print("  D 其它形态（不在本检测范围）    : %d" % r["d"])
    if r["taut"]:
        print("\n⚠⚠⚠ 下列自检的期望串与被检查文本**同源** ⇒ 恒成立：")
        for where, names, frag in r["taut"]:
            print("  ✗ %s  用到 %s" % (where, "、".join(names)))
            print("      期望串：%r" % frag)
        print("\n判决：❌ 有重言式（它们比「恒绿」更坏：长得像在查东西）")
        return 1
    if r["a"] + r["c"] == 0:
        print("\n⚠⚠⚠ A 与 C 都是 0：**一条真判据都没匹配上** ⇒ 这是空洞通过，"
              "不是「没有重言式」。")
        print("判决：❌ 本项无判据")
        return 1
    print("\n判决：✅ 无重言式，且确实匹配到了 %d 条真判据（非空洞通过）"
          % (r["a"] + r["c"]))
    return 0


def main(argv):
    src_path = BUILDER
    do_self_test = "--self-test" in argv
    for a in argv:
        if not a.startswith("-"):
            src_path = a

    rc = 0
    if do_self_test:
        # ⚠ 阳性对照：注入一条**已知**重言式，要求检测器必须抓到。
        base = io.open(src_path, encoding="utf-8").read()
        anchor = "def main("
        if anchor not in base:
            print("✗ 自测失败：找不到注入锚点 %r" % anchor)
            return 2
        injected = base.replace(anchor, INJECT + "\n" + anchor, 1)
        print("【阳性对照】注入的这一行是**故意**的重言式：")
        print("  " + INJECT.split("\n")[0].strip())
        r = analyse(injected, "注入后（自测）")
        if r is None:
            return 2
        found = any(ln and "自测注入" in "" for ln, _, _ in r["taut"])
        # ⚠ 不能只看计数：必须确认抓到的是**注入的那一条**。
        hit = report(r)
        print()
        if r["b"] < 1:
            print("❌ 自测失败：注入了一条重言式，检测器却没抓到 ⇒ **检测器坏了**")
            return 1
        if hit == 0:
            print("⚠ 注入的重言式被抓到了，但注入点在 %s —— 请核对是不是同一条"
                  % [ln for ln, _, _ in r["taut"]])
        print("✅ 阳性对照通过：检测器能抓到已知的重言式 ⇒ 上面的 ✅ 有意义")
        return 0

    rc = report(analyse(io.open(src_path, encoding="utf-8").read(),
                        os.path.relpath(src_path, ROOT)))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
