"""判据覆盖守卫：两条守卫的**职责边界**必须是可枚举的分区（修订 61）。

## 它抓的是什么

`check_fragment_uniqueness.py` 管**字面量**片段，
`check_tautology.py` 管**同源表达式**片段。
⇒ 这个分工**只写在两份 docstring 里**，没有任何机制保证。

探底时发现三件事（预登记 §61.2）：

1. 「B 类为空」有两种完全不同的可能：「确实一条都没有」与「我没解析出来」。
   重言式守卫的防空转断言是 `a + c > 0`，而 `a` 被**字面量**撑着
   ⇒ **B 全空它照样报 ✅** ⇒ 它没有在管它自己那一族。
2. 两条守卫对**同一批**判据用了**不同口径**：一个报 `a=22`（循环展开不去重），
   一个报 `18`（去重）⇒ 连「它俩加起来该等于多少」都没有权威答案。
3. 重言式守卫的**实际覆盖面已被片段唯一性守卫完全包含**。

## 判定规则（冻结，§61.3）

- **S1 规范集合**：循环展开 + 按 `(片段, 目标级别, 目标字段)` 去重，**唯一**口径。
- **S2 分区完备**：A/B/C/D 四类之和 == 规范集合总数；
  落在 D 的逐条列出，有则**判红**。
- **S3 两条守卫的覆盖必须与规范集合一致**：
  片段唯一性 == A 类条数；重言式的 `b + c` == B + C 条数。
- **S4 B 类为空要可辩护**：`--self-test` 注入一条**同源**判据（须归 B 并判红）
  与一条**独立出处**判据（须归 C）。
- **S5 冗余显式披露**：覆盖面被完全包含时打印它唯一的独立价值（不判红）。

## 用法

    PYTHONPATH=.cache/pylibs python3 .cache/xcheck/check_judge_coverage.py
    PYTHONPATH=.cache/pylibs python3 .cache/xcheck/check_judge_coverage.py --self-test
"""
from __future__ import annotations

import ast
import importlib.util
import io
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
BUILDER = os.path.join(ROOT, ".cache/xcheck/build_evidence_ladder.py")
SIBLINGS = {
    "tautology": os.path.join(ROOT, ".cache/xcheck/check_tautology.py"),
    "uniqueness": os.path.join(ROOT, ".cache/xcheck/check_fragment_uniqueness.py"),
}


def _load(name, path):
    spec = importlib.util.spec_from_file_location("jj_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _is_ladder_text(node):
    seg = ast.dump(node)
    return any(k in seg for k in ("'ladder'", "'note'", "'claim'", "'here'",
                                  "'not_answerable'", "'answerable'",
                                  "'overreach_numbers'"))


def _NAMES(node):
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def partition(src):
    """按**唯一**口径把「`X in <阶梯文本>`」判据分成 A/B/C/D。

    返回 (规范集合, 各类去重后的条目, 无法分类的行号)
    规范条目 = (片段, 级别, 字段, 类别)
    """
    uniq = _load("uniqueness", SIBLINGS["uniqueness"])
    tree = ast.parse(src)
    varmap = uniq._var_levels(tree)
    gen_names = taut_text_names(src)

    canon, d_lines = {}, []
    seen_lineno = set()
    # ⚠⚠ 片段清单循环体里的 `need(_frag in …)` 会**同时**被
    #   「逐个 need 统计」和「循环展开」数一遍 ⇒ **重复计数**
    #   （第一版因此把行 801 误报成「落在 D、谁都不管」）。
    #   ⇒ 先算出循环体覆盖的行号，逐个统计时跳过它们。
    loop_lines = set()
    for _n in ast.walk(tree):
        if uniq._frag_loop(_n, varmap):
            for _b in _n.body:
                loop_lines |= {x.lineno for x in ast.walk(_b)
                               if isinstance(x, ast.Call)}

    def add(frag, level, field, kind):
        key = (frag, level, field)
        canon[key] = kind
        seen_lineno.add(kind)

    # A/B/C：字面量 与 格式化表达式（**逐个 need() 现场判**）
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "need" and n.args):
            continue
        a0 = n.args[0]
        if not (isinstance(a0, ast.Compare) and len(a0.ops) == 1
                and isinstance(a0.ops[0], ast.In)):
            continue
        cmp_ = next((c for c in a0.comparators if _is_ladder_text(c)), None)
        if cmp_ is None or n.lineno in loop_lines:
            continue
        r = uniq._resolve(cmp_, varmap)
        if not r:
            d_lines.append(n.lineno)
            continue
        L = a0.left
        if isinstance(L, ast.Constant):
            add(L.value, r[0], r[1], "A")
        elif isinstance(L, ast.BinOp) and isinstance(L.op, ast.Mod) \
                and isinstance(L.left, ast.Constant):
            used = _NAMES(L.right)
            add(L.left.value, r[0], r[1],
                "B" if (used and used <= gen_names) else "C")
        else:
            d_lines.append(n.lineno)

    # 片段清单循环：循环体里的 `need(_frag in …)` 属于**展开后**的 A/B/C
    for n in ast.walk(tree):
        tgt = uniq._frag_loop(n, varmap)
        if not tgt:
            continue
        r = uniq._resolve(tgt, varmap)
        if not r:
            continue
        for it in n.iter.elts:
            if not (isinstance(it, ast.Tuple) and it.elts
                    and isinstance(it.elts[0], ast.Constant)):
                continue
            # ⚠⚠ 第一版用「片段里含 `%` 或 `(`」猜它是不是格式化表达式
            #   ⇒ 把字面量 `49.5%` 误判成 C 类。**分类依据不能是代理指标**：
            #   循环里的每一项**就是源码里的字面量**，没有表达式可求值，
            #   所以一律是 A 类。
            add(it.elts[0].value, r[0], r[1], "A")
    return canon, sorted(set(d_lines)), varmap


def taut_text_names(src):
    """生成侧（把 `%` 结果当字符串用的那些格式化表达式）用到的变量名。"""
    mod = _load("taut", SIBLINGS["tautology"])
    names = set()
    for node in ast.walk(ast.parse(src)):
        if (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod)
                and isinstance(node.left, ast.Constant)
                and isinstance(node.left.value, str)):
            names |= mod._names(node.right)
    return names


def report(src, label):
    canon, d_lines, _ = partition(src)
    cnt = {"A": 0, "B": 0, "C": 0}
    for v in canon.values():
        cnt[v] += 1
    print("=== 判据覆盖分区（修订 61 S1/S2）：%s ===" % label)
    print("规范集合（循环展开 + 去重）：**%d 条**" % len(canon))
    print("  A 字面量（片段唯一性守卫）  : %d" % cnt["A"])
    print("  B 同源表达式（重言式守卫，须为空）: %d" % cnt["B"])
    print("  C 独立出处（重言式守卫）    : %d" % cnt["C"])
    print("  D 无法静态分类             : %d %s"
          % (len(d_lines), d_lines[:8] if d_lines else ""))
    bad = []
    if d_lines:
        print("\n⚠⚠⚠ 落在 D 的判据**谁都不管**：")
        for ln in d_lines:
            print("  ✗ 行 %d" % ln)
        bad.append("S2 分区不完备：%d 条判据无法归类" % len(d_lines))
    if cnt["A"] + cnt["B"] + cnt["C"] != len(canon):
        bad.append("S2 四类之和 != 规范集合总数")
    print("\n--- S3 两条既有守卫的覆盖必须与规范集合一致 ---")
    r_t = _load("taut", SIBLINGS["tautology"]).analyse(src, "校验")
    r_u = _load("uniq", SIBLINGS["uniqueness"])
    u_frags = r_u.collect_frags(src)
    print("  check_fragment_uniqueness 报 %d 条，规范集合 A 类 %d 条"
          % (len(u_frags), cnt["A"]))
    if len(u_frags) != cnt["A"]:
        bad.append("S3 片段唯一性守卫 %d ≠ A 类 %d" % (len(u_frags), cnt["A"]))
    print("  check_tautology 报 b=%d c=%d，规范集合 B+C = %d"
          % (r_t["b"], r_t["c"], cnt["B"] + cnt["C"]))
    if r_t["b"] + r_t["c"] != cnt["B"] + cnt["C"]:
        bad.append("S3 重言式守卫 b+c=%d ≠ B+C=%d"
                   % (r_t["b"] + r_t["c"], cnt["B"] + cnt["C"]))
    print("  ⚠ 口径披露：check_tautology 的 a=%d 是**循环展开不去重**的计数，"
          % r_t["a"])
    print("     规范集合是**去重后**的 ⇒ 两个数字本就不该相等，"
          "它们不是同一个量。")
    print("\n--- S5 冗余披露（不判红）---")
    if cnt["B"] == 0 and cnt["C"] == 0:
        print("  ⚠ B 与 C 都为空 ⇒ `check_tautology.py` 的**覆盖面已被**")
        print("    `check_fragment_uniqueness.py` **完全包含**。")
        print("    它当前唯一的独立价值是：**`--self-test` 阳性对照** 与"
              " **防空转断言**")
        print("    （`a + c > 0`）。⚠ 而 a 被字面量撑着 ⇒ "
              "**B 全空它照样报 ✅**")
        print("    ⇒ 「空」必须由 `--self-test` 证明是真的空，而不是没解析出来。")
    if bad:
        print("\n判决：❌ " + "；".join(bad))
        return 1
    print("\n判决：✅ 分区完备、两条守卫覆盖与规范集合一致")
    return 0


def self_test(src):
    """S4：注入一条**同源**判据与一条**独立出处**判据，必须分别落进 B 与 C。"""
    import copy
    mod = _load("taut", SIBLINGS["tautology"])
    names = mod._names
    base = taut_text_names(src)
    anchor = "def main("
    inject_b = ('    need("%.1f%%" % (100.0 * l1_base_d) in _l1["note"],\n'
                '         "【自测注入 B】故意同源")\n')
    # ⚠⚠⚠ 两条注入的**格式串必须不同**：规范集合的去重键是
    #   `(片段, 级别, 字段)`，**不含类别**。第一版两条都用 `%.1f%%`
    #   且都指向 L1.note ⇒ C 把 B **整个覆盖**掉 ⇒ 自测误报失败。
    #   ⚠ 这也说明去重键不含类别本身是个弱点（记在预登记里）。
    inject_c = ('    need("%.3f%%" % (1234.5678) in _l1["note"],\n'
                '         "【自测注入 C】故意独立出处")\n')
    if anchor not in src:
        print("✗ 自测失败：找不到注入锚点")
        return 2
    injected = src.replace(anchor, inject_b + inject_c + "\n" + anchor, 1)
    canon, d_lines, _ = partition(injected)
    b = [k for k, v in canon.items() if v == "B"]
    c = [k for k, v in canon.items() if v == "C"]
    print("=== S4 阳性对照：注入一条同源 + 一条独立出处 ===")
    print("注入 B：%r（用 l1_base_d ⇒ 属生成侧）；注入 C：%r（用字面量 ⇒ 无生成侧变量）"
          % ("%.1f%%", "%.3f%%"))
    print("  B 类实际条目：%d %s" % (len(b), [k[0] for k in b]))
    print("  C 类实际条目：%d %s" % (len(c), [k[0] for k in c]))
    okb = any("%" in k[0] for k in b)
    okc = any("%" in k[0] for k in c)
    if okb and okc:
        print("\n✅ 阳性对照通过：同源落进 B、独立出处落进 C ⇒ 「B=0」"
              "在真实运行里**区分得了**「真的没有」与「没解析出来」")
        return 0
    print("\n❌ 自测失败：B 命中=%s、C 命中=%s ⇒ 分区规则本身有问题" % (okb, okc))
    return 1


def main(argv):
    src = io.open(BUILDER, encoding="utf-8").read()
    if "--self-test" in argv:
        return self_test(src)
    return report(src, os.path.relpath(BUILDER, ROOT))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))