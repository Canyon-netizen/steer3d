"""片段唯一性守卫：note 必须含的每个片段，在 note 里**恰好出现一次**（修订 60 R1）。

## 它抓的是什么

判据写成 `need("是错的" in note, …)`，而 note 里 `是错误的` 出现在**两个**地方
⇒ 删掉其中任意一个，判据照样绿 ⇒ **判据与意图脱钩**（修订 59 那一条的族）。

反过来，片段**缺失**（count == 0）说明判据已经失效。

⇒ 把「逐条手工核」变成**可枚举、会变红**的常规检查。

## 三条不能省的

1. ⚠⚠ **本体空洞通过**：一条都没匹配上却报 ✅（§57.5.4）。
   ⇒ 匹配到的判据数必须 **> 0**，否则报「本项无判据」并**判红**。
2. ⚠⚠ **结构特征不唯一**：第一版用「`ast.For` + `ast.Tuple`」找片段清单，
   而阈值读取循环 `for _key, _var in (("direction_independent","sp"), …)`
   形状**完全一样** ⇒ 混进 3 条根本不是判据的字符串。
   ⇒ 判据：**循环体里必须真的有 `need(变量 in <阶梯文本>)`**。
3. ⚠⚠ **阳性对照**：`--self-test` 往源码里注入一条**故意**不唯一的判据
   （片段取自 note 里实测出现 ≥2 次的一段），要求脚本**必须**报出来。
   ⚠ M1b 教训：阳性对照自己写错等于没有对照 —— 所以对照的片段是
   **动态找出来的**，不是手写一个可能已经变成唯一的那句。

## 读的是**交付产物**里的 note（读者看到的文本），不是源码里的模板

## 用法

    PYTHONPATH=.cache/pylibs python3 .cache/xcheck/check_fragment_uniqueness.py
    PYTHONPATH=.cache/pylibs python3 .cache/xcheck/check_fragment_uniqueness.py --self-test
"""
from __future__ import annotations

import ast
import io
import json
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
BUILDER = os.path.join(ROOT, ".cache/xcheck/build_evidence_ladder.py")
ARTIFACT = os.path.join(ROOT, "frontend/public/latent/data/evidence_ladder.json")
LEVEL = "L1"
MIN_FRAGS = 15        # ⚠ 少报比多报更难发现 ⇒ 设下限，低于它判「覆盖不足」
DUP_K = 10          # 自测注入的片段长度


def _is_ladder_text(node):
    seg = ast.dump(node)
    return any(k in seg for k in ("'ladder'", "'note'", "'claim'", "'here'",
                                  "'not_answerable'", "'answerable'",
                                  "'overreach_numbers'"))


def _frag_loop(n, varmap):
    """这个 `for` 是不是「片段清单」循环？

    ⚠ 判据：**循环体里必须真的有 `need(变量 in <阶梯文本>)`**。
    只看「For + Tuple」会把阈值读取循环混进来（形状一模一样）。
    """
    if not (isinstance(n, ast.For) and isinstance(n.iter, ast.Tuple)):
        return None
    tgts = ([n.target.id] if isinstance(n.target, ast.Name)
            else [t.id for t in n.target.elts]
            if isinstance(n.target, ast.Tuple) else [])
    if not tgts:
        return None
    for b in n.body:
        for c in ast.walk(b):
            if (isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
                    and c.func.id == "need" and c.args
                    and isinstance(c.args[0], ast.Compare)
                    and len(c.args[0].ops) == 1
                    and isinstance(c.args[0].ops[0], ast.In)
                    and isinstance(c.args[0].left, ast.Name)
                    and c.args[0].left.id in tgts):
                for cmp_ in c.args[0].comparators:
                    # ⚠⚠⚠ 必须返回 **AST 节点**，不能返回已解出的元组 ——
                    #   第一版返回了 `("__field__", "note")`，而 `collect_frags`
                    #   拿它再解一次 ⇒ 解不出 ⇒ **11 条片段判据全丢**，
                    #   报告里只剩 6 条独立判据，而且**没有报警**。
                    #   「两级解析混用」的后果是**静默少报**。
                    if _resolve(cmp_, varmap):
                        return cmp_
    return None


def _var_levels(tree):
    """`_l1 = next(x for x in ladder if x["level"] == "L1")` ⇒ {"_l1": "L1"}。"""
    m = {}
    for n in ast.walk(tree):
        if (isinstance(n, ast.Assign) and len(n.targets) == 1
                and isinstance(n.targets[0], ast.Name)
                and isinstance(n.value, ast.Call)):
            for c in ast.walk(n.value):
                if (isinstance(c, ast.Compare) and len(c.ops) == 1
                        and isinstance(c.ops[0], ast.Eq)
                        and isinstance(c.left, ast.Subscript)
                        and isinstance(c.left.slice, ast.Constant)
                        and c.left.slice.value == "level"
                        and isinstance(c.comparators[0], ast.Constant)):
                    m[n.targets[0].id] = c.comparators[0].value
    return m


def _target_of(node):
    """从 `x["field"]` 这个比较端点解出它指的是**哪一级、哪个字段**。

    ⚠⚠⚠ 第一版没有这一步，只判断「是不是阶梯文本」，于是
    **claim 的片段**（`任何 a>0 都…`）与 **L6 的 `here`**（`92 个真 run`）
    都被拿去 **L1 的 note** 里数 —— **三个不同的量混在一起比**。
    实测报出 3 条假阳性。⇒ 守卫必须知道每条判据钉的是哪个字段。
    """
    if isinstance(node, ast.Subscript):
        if not (isinstance(node.slice, ast.Constant)
                and isinstance(node.slice.value, str)):
            return None
        return ("__field__", node.slice.value)
    if isinstance(node, ast.Name) and node.id in ("_l1",):
        return None
    return None


def _resolve(node, varmap):
    """解出 (级别, 字段)；级别为 None 表示 payload 级字段。"""
    tgt = _target_of(node)
    if not tgt:
        return None
    field = tgt[1]
    payload_level = {"not_answerable", "answerable", "overreach_numbers",
                     "most_common_overreach", "max_level_claimed"}
    if field in payload_level:
        return (None, field)
    # 比较端点常常是 `_l1["note"]` 或 `_l6["here"]`
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
        return (varmap.get(node.value.id), field)
    return None


def _text_of(payload, level, field):
    if level is None:
        return json.dumps(payload.get(field), ensure_ascii=False)
    for x in payload.get("ladder", []):
        if x.get("level") == level:
            return str(x.get(field, ""))
    return ""


def collect_frags(src):
    """抽出全部「阶梯文本必须含某片段」的判据。

    返回 [(片段, 来源, 级别, 字段)]。
    ⚠⚠⚠ **级别与字段必须解出来** —— 否则会把 claim 的片段、L6 的 `here`
    拿去 **L1 的 note** 里数（第一版就是这么报出 3 条假阳性的）。
    """
    tree = ast.parse(src)
    varmap = _var_levels(tree)
    out, seen = [], set()

    def add(frag, where, cmp_node):
        r = _resolve(cmp_node, varmap)
        if not r:
            return
        key = (frag, r)
        if key in seen:
            return
        seen.add(key)
        out.append((frag, where, r[0], r[1]))

    for n in ast.walk(tree):
        tgt = _frag_loop(n, varmap)
        if not tgt:
            continue
        for it in n.iter.elts:
            if (isinstance(it, ast.Tuple) and it.elts
                    and isinstance(it.elts[0], ast.Constant)
                    and isinstance(it.elts[0].value, str)):
                add(it.elts[0].value, "片段清单循环", tgt)
    for n in ast.walk(tree):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "need" and n.args
                and isinstance(n.args[0], ast.Compare)
                and len(n.args[0].ops) == 1
                and isinstance(n.args[0].ops[0], ast.In)
                and isinstance(n.args[0].left, ast.Constant)
                and isinstance(n.args[0].left.value, str)):
            for cmp_ in n.args[0].comparators:
                add(n.args[0].left.value, "独立字面量判据", cmp_)
    return out


def _find_dup(note, k=DUP_K):
    """在 note 里找一段**实测出现 ≥2 次**的子串（给自测注入用）。"""
    for i in range(0, max(len(note) - k, 1)):
        w = note[i:i + k]
        if w.strip() and note.count(w) >= 2:
            return w
    return None


def report(frags, payload, label):
    print("=== 片段唯一性（修订 60 R1）：%s ===" % label)
    print("文本取自**交付产物** `%s`（判据钉的是哪一级、哪个字段，就数那一处）"
          % os.path.basename(ARTIFACT))
    print("识别到「阶梯文本必须含片段」判据：**%d 条**" % len(frags))
    if not frags:
        print("\n⚠⚠⚠ 一条都没匹配上 ⇒ 这是**空洞通过**，不是「全部唯一」。")
        print("判决：❌ 本项无判据")
        return 1
    # ⚠⚠ 反向也要查：匹配到的条数**太少**同样是覆盖不足。
    #   实测踩过：解析出「已解好的元组」再解一次 ⇒ 11 条片段判据全丢，
    #   报告里只剩 6 条，却**没有任何报警** —— 少报比多报更难发现。
    if len(frags) < MIN_FRAGS:
        print("\n⚠⚠⚠ 只识别到 %d 条（门槛 %d）⇒ 解析**静默漏掉了**一部分判据。"
              % (len(frags), MIN_FRAGS))
        print("   「少报」比「多报」更难发现：上面每一条都 ✅，看着像全过。")
        print("判决：❌ 覆盖不足")
        return 1
    bad = []
    for f, where, level, field in frags:
        text = _text_of(payload, level, field)
        c = text.count(f)
        mark = "✅ 恰好 1 次" if c == 1 else ("⚠ 缺失（判据已失效）" if c == 0
                                            else "⚠⚠ 出现 %d 次（与意图脱钩）" % c)
        print("  %-34s %-16s %-4s.%-5s %s"
              % (f[:32], where[:14], level or "payload", field[:5], mark))
        if c != 1:
            bad.append((f, c, where, level, field))
    if bad:
        print("\n⚠⚠⚠ %d 条片段**不唯一或已缺失** ⇒ 删掉其中一处判据照样绿：" % len(bad))
        for f, c, where, level, field in bad:
            print("  ✗ %r 在 %s.%s 里出现 %d 次"
                  % (f, level or "payload", field, c))
            print("     ⇒ 要么同一件事说了两遍（该去重），要么片段选得太短（该改判据）")
        print("\n判决：❌ 不通过")
        return 1
    print("\n判决：✅ %d 条片段在它们各自钉的字段里都**恰好出现一次**"
          "（删任何一处都会红）" % len(frags))
    return 0


def main(argv):
    src = io.open(BUILDER, encoding="utf-8").read()
    payload = json.loads(io.open(ARTIFACT, encoding="utf-8").read())
    # 自测注入的片段从 **L1 的 note** 里找（那儿最长、最容易找到重复子串）
    note = _text_of(payload, LEVEL, "note")

    if "--self-test" in argv:
        dup = _find_dup(note)
        if dup is None:
            print("✗ 自测失败：在 note 里找不到任何出现 ≥2 次的 %d 字子串" % DUP_K)
            return 2
        print("【阳性对照】注入的片段是**从 note 里动态找出来的**"
              "（实测出现 %d 次）：" % note.count(dup))
        print("  %r" % dup)
        anchor = "def main("
        if anchor not in src:
            print("✗ 自测失败：找不到注入锚点 %r" % anchor)
            return 2
        inject = ('    _frag_self_test = %r\n\n' % dup)
        injected = src.replace(anchor, inject + anchor, 1)
        r = report(collect_frags(injected)
                   + [(dup, "【自测注入】", LEVEL, "note")],
                   payload, "注入后（自测）")
        if r == 0:
            print("\n❌ 自测失败：注入了一条**不唯一**的判据，脚本却报通过"
                  " ⇒ **守卫坏了**")
            return 1
        print("\n✅ 阳性对照通过：守卫能抓到已知的非唯一片段 ⇒ 上面的 ✅ 有意义")
        return 0

    return report(collect_frags(src), payload, os.path.relpath(BUILDER, ROOT))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))