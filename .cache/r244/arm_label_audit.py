#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""arm_label_audit.py —— 结果文件里的 `arm` 标签能不能用来分臂（零 GPU）

🔴🔴 **本工具问什么**

  盘 `.cache/r244/*.txt` 时发现：15 个结果文件里 `arm` 字段有**四种**取值 ——
  `'w'`（7 份）、`'rand'`（2 份）、**`'X'`（2 份）**、**缺失（2 份）**，
  而 `X`/缺失那几份的多数计数**一个是 6/14、一个是 12/14**。

  🔴 探针 `.cache/mutbak/r204_noise_probe.py:821` 写的是：

      ap.add_argument("--arm", default="w", choices=["w", "rand"])

  ⇒ ⛔ 探针**不可能**产出 `X` 或空。`:490` 是 `st["arm"] = a.arm` 原样落盘。
  ⇒ **这些标签是后处理打上去的**，⛔ 不是仪器写的。

⚖⚠⚠⚖ **实测结论（本工具算出来的）**

  按**内容指纹**（把 `arm` 字段排除后逐条 sha1）聚类，12 个完整结果文件
  落在**恰好两簇**：`w` 簇 8 份、`rand` 簇 4 份，每簇内部 **137/137 逐条重合**。

  ⚠⚠⚠⚠⚠ **`arm='X'` 那一组横跨两簇** ——
     `_wn.txt`(X) 与 `_an.txt` 全同（w 簇），
     `_rn2.txt`(X) 与 `_ra.txt` 全同（rand 簇）。
     ⚖⇒ **「X 臂」根本不是一个臂**：它是两个臂**共用同一个被打坏的标签**。

  ⚖ **后果**：任何**按 `arm` 字段分组**的汇总，都会把两个臂混进同一桶，
     那个桶的多数计数（6/14 与 12/14）**互相矛盾** ⇒ 那个数**没有意义**。

  ✅ **对既往结论的影响：零。** 本轮 244.48–244.51 用的
     `_an.txt` / `_ra.txt` 标签**正确**，且内容已验（C4）。

⚖⚠⚠⚖ **本工具问不了、也⛔ 不许假装答了的一条**
  ⚖ 这些标签是**谁、什么时候、为什么**打上去的 —— 本地**查不到**（无时间戳链、
  无写入脚本记录）。⚠ 只登记「是后处理的」，⛔ 不指认来源。

⚠⚠⚠ 本工具⛔ **不发批**、⛔ 不改探针、⛔ 不写数据文件、⛔ 不删任何文件。
⚖⚠⚠⚖ 每条判据都必须**能红**：变异台改的是喂进来的**数据形状**。
"""

import argparse
import ast
import glob
import hashlib
import io
import json
import os
import sys

PROBE = ".cache/mutbak/r204_noise_probe.py"
R244 = ".cache/r244"
# ⚖ 本轮判决实际引用的两个文件（C4 守住它们）
USED = {"w": "_an.txt", "rand": "_ra.txt"}
# ⚖ 账本 244.43 记的多数计数（C5 用它当交叉校验）
LEDGER_COUNT = {"w": 12, "rand": 6}
# ⚖ 244.48/244.50/244.51 引用的格数
N_CELLS = 137
N_TRAJ = 14


class HardFail(Exception):
    pass


# --------------------------------------------------------------- 小工具
def load_jsonl(path):
    out, bad = [], 0
    for line in io.open(path, encoding="utf-8", errors="replace"):
        t = line.strip()
        if not t.startswith("{"):
            continue
        try:
            out.append(json.loads(t))
        except Exception:
            bad += 1
    if bad:
        raise HardFail("文件 %s 有 %d 行解析失败 ⇒ ⛔ 拒读" % (path, bad))
    if not out:
        raise HardFail("文件 %s 一条记录都没有 ⇒ ⛔ 拒读" % path)
    return out


def probe_arm_choices(path=PROBE):
    """⚖⚖ **从探针源码**取 `--arm` 的合法取值（AST，⛔ 不正则）。

    ⚖ 为什么要结构取：`choices=["w", "rand"]` 写成别的形状也还是同一个意思，
    ⚠ 而正则会在「注释里也有这句话」时静默取错 ⇒ 244.46 禁令 **㊫**。"""
    tree = ast.parse(io.open(path, encoding="utf-8").read())
    found = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "add_argument"
                and node.args and getattr(node.args[0], "value", None) == "--arm"):
            for kw in node.keywords:
                if kw.arg == "choices" and isinstance(kw.value, ast.List):
                    found.append(tuple(e.value for e in kw.value.elts
                                       if isinstance(e, ast.Constant)))
    if not found:
        raise HardFail("探针源码里**找不到** `--arm` 的 choices ⇒ 形状变了 ⇒ ⛔ 拒读")
    if len(found) != 1:
        raise HardFail("探针里有 %d 处 `--arm` choices ⇒ 形状变了 ⇒ ⛔ 拒读" % len(found))
    return found[0]


def fingerprint(rec):
    """⚖ 内容指纹：⛔ **必须排除 `arm`** —— 它就是被质疑的那个字段。"""
    d = {k: v for k, v in rec.items() if k != "arm"}
    return hashlib.sha1(
        json.dumps(d, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]


def majority(rs):
    """⚖ 逐轨迹取 `d > 0` 的多数（平票算 False，与账本同口径）。"""
    g = {}
    for r in rs:
        lo, hi = r.get("p9_lo_meas"), r.get("p9_hi_meas")
        if lo is None or hi is None:
            raise HardFail("记录 %r 缺 p9_*_meas ⇒ **未量到**" % (r.get("tid"),))
        g.setdefault(r.get("tid"), []).append(float(hi) > float(lo))
    return sum(1 for v in g.values() if sum(v) * 2 > len(v)), len(g)


# --------------------------------------------------------------- 判据
def audit(probe=PROBE, rdir=R244, used=None):
    used = used or USED
    L = ["【臂标签审计】探针 %s ｜ 目录 %s" % (probe, rdir)]
    ok = True

    # ---- C1 探针的合法 arm 取值（结构取，不正则）------------------------
    choices = probe_arm_choices(probe)
    L.append("  C1 探针 `--arm` 的 choices = %s" % (list(choices),))
    L.append("     ⇒ 仪器**只可能**产出这些标签；其余的都是**后处理**打的")

    # ---- 收集文件 --------------------------------------------------------
    recs, meta = {}, {}
    for p in sorted(glob.glob(os.path.join(rdir, "*.txt"))):
        try:
            rs = load_jsonl(p)
        except HardFail:
            continue
        if not rs or "p9_lo_meas" not in rs[0]:
            continue
        recs[p] = rs
        meta[p] = {"arm": sorted({r.get("arm") for r in rs}, key=repr),
                   "n": len(rs), "maj": majority(rs)}
    full = {p: v for p, v in recs.items() if len(v) == N_CELLS}
    L.append("  ⚖ 可读结果文件 %d 份，其中 %d 格完整的 %d 份" %
             (len(recs), N_CELLS, len(full)))

    # ---- C2 内容指纹必须落在**恰好两簇**，且与两个干净标签文件全同 ------
    clusters = {}
    for p, rs in full.items():
        clusters.setdefault(frozenset(fingerprint(r) for r in rs), []).append(p)
    sizes = sorted((len(v), sorted(os.path.basename(x) for x in v))
                   for v in clusters.values())
    two = (len(clusters) == 2)
    L.append("  C2 按内容指纹（排除 arm）聚类 ⇒ **%d 簇**：" % len(clusters))
    for sz, names in sizes:
        L.append("     %d 份：%s" % (sz, ", ".join(names)))
    L.append("     ⇒ %s" % ("✅ 恰好两簇 ⇒ 仪器只跑过两个臂"
                             if two else "⛔ 簇数 %d ⛔ 不是 2 ⇒ 数据里有第三批或被打乱过"
                             % len(clusters)))
    ok &= two

    # ---- C3 `arm` 标签**不得横跨两簇**（横跨 ⇒ 那个标签会混臂）-----------
    label_span = {}
    for cl in clusters.values():
        for p in cl:
            for lab in meta[p]["arm"]:
                label_span.setdefault(lab, set()).add(
                    list(clusters).index(frozenset(
                        fingerprint(r) for r in full[p])))
    bad_lab = {lab: s for lab, s in label_span.items() if len(s) > 1}
    L.append("  C3 每个 arm 标签横跨的簇数：%s"
             % {lab: len(s) for lab, s in sorted(label_span.items(), key=repr)})
    if bad_lab:
        for lab in sorted(bad_lab, key=repr):
            L.append("     ⛔ 标签 %r 横跨 %d 簇 ⇒ **它不是一个臂**，按它分组会把两臂混进"
                     "同一个桶（该桶的多数计数互相矛盾）" % (lab, len(bad_lab[lab])))
    else:
        L.append("     ⇒ ✅ 没有标签横跨两簇")
    ok &= (not bad_lab)

    # ---- C4 本轮判决实际引用的两个文件，标签必须正确 --------------------
    for arm, fn in sorted(used.items()):
        p = os.path.join(rdir, fn)
        if p not in recs:
            L.append("  C4 ⛔ 引用的文件 %s 不存在/不可读 ⇒ 判决的数据底账没了" % fn)
            ok = False
            continue
        labs = meta[p]["arm"]
        good = (labs == [arm])
        L.append("  C4 引用 %-10s arm=%-8s 多数 %d/%d ⇒ %s"
                 % (fn, repr(arm), meta[p]["maj"][0], meta[p]["maj"][1],
                    "✅ 标签正确" if good else
                    "⛔ 标签是 %s，**与引用的臂名不符** ⇒ 该文件的判决作废" % (labs,)))
        ok &= good

    # ---- C5「按 arm 分组」与「按内容簇分组」两种口径必须给出同一个数 -----
    by_label, by_cluster = {}, {}
    for p, rs in full.items():
        k = meta[p]["maj"][0]
        for lab in meta[p]["arm"]:
            by_label.setdefault(lab, set()).add(k)
        cl = frozenset(fingerprint(r) for r in rs)
        by_cluster.setdefault(
            list(clusters).index(cl), set()).add(k)
    agree = all(len(v) == 1 for v in by_label.values())
    L.append("  C5 按**标签**分组 ⇒ 每组出现的多数计数：%s"
             % {repr(lab): sorted(v) for lab, v in sorted(by_label.items(), key=repr)})
    L.append("     按**内容簇**分组 ⇒ 每簇的多数计数：%s"
             % {i: sorted(v) for i, v in sorted(by_cluster.items())})
    L.append("     ⇒ %s" % ("✅ 两种口径一致 ⇒ 既往用标签分组的数没被污染"
                             if agree else
                             "⛔ 标签口径内部**自相矛盾**（同组出现两个多数计数）"
                             "⇒ 任何按标签汇总的数都不可用"))
    ok &= agree

    # ---- 附：本轮用的两个文件的多数必须复现账本 --------------------------
    for arm, fn in sorted(used.items()):
        p = os.path.join(rdir, fn)
        if p in recs:
            k, n = meta[p]["maj"]
            g = (k == LEDGER_COUNT.get(arm) and n == N_TRAJ)
            L.append("  ⚖ %s 多数 %d/%d（账本记 %s）⇒ %s"
                     % (fn, k, n, LEDGER_COUNT.get(arm),
                        "✅ 复现" if g else "⛔ 没复现 ⇒ 读的不是那一批"))
            ok &= g

    L.append("")
    L.append("【⛔】本工具**没有**查的：这些 `X`/缺失标签是**谁、什么时候、为什么**"
             "打上去的 ⇒ 本地无时间戳链、无写入脚本记录 ⇒ ⛔ 只登记「是后处理的」，"
             "⛔ 不指认来源。⚠ 也**没有**删改任何文件。")
    return L, (0 if ok else 1)


# --------------------------------------------------------------- 自检
def selftest(files=None):
    ok, bad = [], []

    def chk(t, cond, why=""):
        (ok if cond else bad).append(t)
        print(("[PASS] %s %s" if cond else "[FAIL] %s %s") % (t, why))

    chk("C0", probe_arm_choices(PROBE) == ("w", "rand"),
        "从探针源码结构取出 %s" % (list(probe_arm_choices(PROBE)),))

    # ⚖⚠⚠⚠ C0b 证明那个抽取**不是硬编码**：改一份探针副本的 choices，
    #   抽出来的值必须跟着变。⛔ 否则「结构取」只是嘴上说说。
    import tempfile as _tf
    _src = io.open(PROBE, encoding="utf-8").read()
    _fd, _pp = _tf.mkstemp(suffix=".py"); os.close(_fd)
    io.open(_pp, "w", encoding="utf-8").write(
        _src.replace('choices=["w", "rand"]', 'choices=["w", "rand", "X"]', 1))
    try:
        got3 = probe_arm_choices(_pp)
    finally:
        os.unlink(_pp)
    chk("C0b", got3 == ("w", "rand", "X"),
        "改副本的 choices 后必须抽出 %s（实际 %s）" % (("w", "rand", "X"), got3))

    import tempfile

    def mk(arms_per_file):
        """⚖ `arms_per_file` = [(文件名, arm 值, 内容种子)]，同种子 ⇒ 同一簇。"""
        d = tempfile.mkdtemp()
        paths = []
        for fn, arm, seed in arms_per_file:
            p = os.path.join(d, fn)
            with io.open(p, "w", encoding="utf-8") as f:
                for i in range(N_CELLS):
                    tid = "t%02d" % (i % N_TRAJ)
                    f.write(json.dumps(
                        {"tid": tid, "arm": arm, "seed": seed, "i": i,
                         "inject_scope": "k", "inject_n_sites": i + 1,
                         "pos_frac": 0.5, "P": 100, "n_gen": 400,
                         "p9_lo_meas": 0.0,
                         "p9_hi_meas": (1.0 if (i % N_TRAJ) < seed else -1.0)},
                        ensure_ascii=False) + "\n")
            paths.append((p, fn))
        return d, paths

    # ---- 干净夹具：w/rand 两簇、标签干净、两种口径一致 ⇒ 必须全绿 ----
    d1, f1 = mk([("_an.txt", "w", 12), ("_ra.txt", "rand", 6)])
    L1, rc1 = audit(rdir=d1, used={"w": "_an.txt", "rand": "_ra.txt"})
    chk("C1", rc1 == 0, "干净夹具 rc=%d" % rc1)
    chk("C2", any("恰好两簇" in x for x in L1), "C2 必须印出「恰好两簇」")
    chk("C3", any("没有标签横跨两簇" in x for x in L1), "C3 必须印出无横跨")
    chk("C5", any("两种口径一致" in x for x in L1), "C5 必须印出两种口径一致")

    # ---- 畸形夹具：`X` 横跨两簇 ⇒ C3/C5 必须转红 ------------------------
    d2, f2 = mk([("_an.txt", "w", 12), ("_ra.txt", "rand", 6),
                 ("_wn.txt", "X", 12), ("_rn2.txt", "X", 6)])
    L2, rc2 = audit(rdir=d2, used={"w": "_an.txt", "rand": "_ra.txt"})
    chk("C6", rc2 != 0 and any("横跨 2 簇" in x for x in L2),
        "X 横跨两簇 ⇒ C3 必须转红（rc=%d）" % rc2)
    chk("C7", any("自相矛盾" in x for x in L2), "C5 必须报「标签口径自相矛盾」")

    # ---- 畸形夹具：引用文件的标签错了 ⇒ C4 必须转红 ---------------------
    d3, f3 = mk([("_an.txt", "X", 12), ("_ra.txt", "rand", 6)])
    L3, rc3 = audit(rdir=d3, used={"w": "_an.txt", "rand": "_ra.txt"})
    chk("C8", rc3 != 0 and any("与引用的臂名不符" in x for x in L3),
        "引用文件的标签错了 ⇒ C4 必须转红（rc=%d）" % rc3)

    # ---- 指纹必须排除 arm：只改 arm 不该改变簇 --------------------------
    d4, f4 = mk([("_an.txt", "w", 12), ("_an2.txt", "rand", 12)])
    L4, rc4 = audit(rdir=d4, used={"w": "_an.txt"})
    # ⚖⚠⚠ 同内容、**只差 arm 字段** ⇒ 指纹必须把它们并成**一簇**。
    #   若指纹把 `arm` 算进去了 ⇒ 同一批测量会被拆成两个「臂」。
    chk("C9", any("**1 簇**" in x for x in L4) and any("不是 2" in x for x in L4),
        "只差 arm 字段 ⇒ 必须并成 1 簇，且 C2 必须报「不是 2」")

    # ---- C11：C2 的「⛔ 簇数 N 不是 2」那一支必须走得到 -----------------
    # ⚖⚠⚠⚠ 244.52 的台架在这里又踩了 **㊹（死变异）**：
    #   干净夹具上「恰好两簇」**恒为真** ⇒ 把打印选择器焊成 `True` 看不出来
    #   （M1 第一版就是这么活下来的）。⇒ 必须另造一个**走得到 ⛔ 那一支**的夹具。
    d5, f5 = mk([("_a.txt", "w", 12), ("_b.txt", "rand", 6), ("_c.txt", "w", 8)])
    L5, rc5 = audit(rdir=d5, used={"w": "_a.txt"})
    chk("C11", any("簇数 3" in x and "不是 2" in x for x in L5),
        "三簇夹具上 C2 必须印「⛔ 簇数 3 不是 2」（这一条才走得到 ⛔ 那一支）")

    for paths in (f1, f2, f3, f4, f5):
        for p, _fn in paths:
            try:
                os.unlink(p)
            except OSError:
                pass
    for dd in (d1, d2, d3, d4, d5):
        try:
            os.rmdir(dd)
        except OSError:
            pass

    print("自检 %d/%d 通过" % (len(ok), len(ok) + len(bad)))
    return 1 if bad else 0




def main():
    ap = argparse.ArgumentParser(description="结果文件的 arm 标签能不能用来分臂（零 GPU）")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--dir", default=R244)
    ap.add_argument("--probe", default=PROBE)
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    L, rc = audit(probe=args.probe, rdir=args.dir)
    print("\n".join(L))
    return rc


if __name__ == "__main__":
    sys.exit(main())
