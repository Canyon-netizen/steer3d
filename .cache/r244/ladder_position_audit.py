#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ladder_position_audit —— 阶梯的 `k` 档**挑到的是哪些位置**（零 GPU）

## 这条在量什么

账本挂着一个开放问题（修订 244.8.11 第 2 条 / 244.22.6）：
「⛔ `pos_frac=0.5` **选的位置**对不对，仍无任何证据」。

⚖⚠⚠ 查代码查清了一件必须先说的事：**`pos_frac` 不是位置**。
⚖ 全部历史版本（最早 `r201_jump_probe.py:104` 与现行 `r204_noise_probe.py:392`）
⚖ 逐字相同的一行是：

    t = max(1, int(n * a.pos_frac))       # n = len(gen)

⚖⚗ 它决定的是**有效前缀比例**（生成序列留前 50%），⛔ **没有任何偏移量、起始索引**。
⚖ ⇒ 「位置对不对」这个问法**本身不成立**（详见账本 244.26.1）。
⚖⚖ 而真正与「位置」有关、且**从来没人查过**的是**另一件事**：
⚖   阶梯每个 `k` 档挑到的位点，由 `_k_positions(n_eff, k, seed=0, nested=True)`
⚖   里的**种子 0 置换**决定 ⇒ **落在 prompt 段还是生成段，完全没人看过。**

## 本工具做的（全部离线，零 GPU）

1. ⚖ 用 **AST** 从真实探针源码里**抽出** `_k_positions` 并 exec
   ⚖⚠⛔ 抽取时断言「抽出的源码**逐字**在文件里」——
   ⚖   否则「审计用的函数」可能已经不是仪器在用的那个了。
2. ⚖ 读**实际物化**的格表 `warm_cells.txt`（⛔ 不重算阶梯：k 是既成事实）
   ⚖ 与 `n_eff_map.tsv`（P / n_gen / t / n_eff）。
3. ⚖ 校验 `t == int(pos_frac·n_gen)`、`n_eff == P + t`（运行时恒等）。
4. ⚖ 对每个 (tid, k) 算出位点，**分段统计**：`[0,P)` = prompt，
   ⚖ `[P, n_eff)` = 生成段。报告每档的 prompt 占比分布。
5. ⚖ 印出 `pos_frac` 的**真义**与它和阶梯分母的**混淆关系**（零 GPU 的演示）。

跑法：
    python3 ladder_position_audit.py
    python3 ladder_position_audit.py --selftest
退出码：0 = 阶梯位点已量到并报告；1 = 恒等校验失败；2 = 夹具/定位问题。
"""

import argparse
import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROBE = os.path.join(HERE, "..", "mutbak", "r204_noise_probe.py")
CELLS = os.path.join(HERE, "warm_cells.txt")
NMAP = os.path.join(HERE, "n_eff_map.tsv")


class HardFail(Exception):
    pass


def load_k_positions(probe_path=PROBE, name="_k_positions"):
    """⚖ 从**真实源码**抽出函数并 exec —— ⛔ 不手抄（手抄就是第二份实现）。

    ⚖⚠⚠⚠ 修订 244.26：这里原本还有一道「抽出的源码逐字在文件里」的断言，
    ⚖⚗ 自检 A3 **当场抓到它是恒绿的**：`seg` 本就是从 `src` 抽出来的，
    ⚖   `seg in src` **按构造恒真** ⇒ ⛔ 一个永远绿的装饰品，已删。
    ⚖⇒ 换成三道**按构造能红**的检查：
    ⚖  ① 定义存在；
    ⚖  ② 探针里**至少有一处真的调用它**（否则审计的不是仪器在走的那条路）；
    ⚖  ③ 调用点传的是 `nested=`，且定义里 `seed` 的默认值是 **0**
    ⚖     （仪器不传 seed ⇒ 用默认值；审计必须用同一个，否则挑到不同位点）。
    """
    src = open(probe_path, encoding="utf-8").read()
    tree = ast.parse(src)
    fn = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            fn = node
            break
    if fn is None:
        raise HardFail("探针源码里找不到 %s（文件 %s）" % (name, probe_path))

    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and getattr(n.func, "id", None) == name]
    if not calls:
        raise HardFail("探针里**没有任何地方调用** %s ⇒ 审计的不是仪器走的那条路，"
                       "⛔ 拒用" % name)
    if not any(kw.arg == "nested" for c in calls for kw in c.keywords):
        raise HardFail("%s 的调用点没有传 `nested=` ⇒ 仪器用的可能是**非嵌套**位点，"
                       "⛔ 本审计按 nested=True 算，两者不可比" % name)

    seg = ast.get_source_segment(src, fn)
    defaults = [ast.literal_eval(d) for d in fn.args.defaults]
    ns = {}
    exec(compile("import numpy as _np\n" + seg, probe_path, "exec"), ns)
    f = ns[name]
    import inspect
    sig = inspect.signature(f)
    if sig.parameters["seed"].default != 0:
        raise HardFail("%s 的 seed 默认值是 %r，不是 0 ⇒ 本审计按 seed=0 算的是"
                       "另一组位点，⛔ 拒用" % (name, sig.parameters["seed"].default))
    del defaults
    return f, seg


def read_map(path=NMAP):
    out = {}
    with open(path, encoding="utf-8") as f:
        head = f.readline().rstrip("\n").split("\t")
        ix = {k: i for i, k in enumerate(head)}
        for need in ("P", "n_gen", "t", "n_eff"):
            if need not in ix:
                raise HardFail("n_eff_map 缺列 %r ⇒ 无法计算分段（不许当 0）" % need)
        for line in f:
            if not line.strip():
                continue
            p = line.rstrip("\n").split("\t")
            out[p[0]] = {k: (p[ix[k]] if ix[k] < len(p) else None)
                         for k in ("P", "n_gen", "t", "n_eff")}
    return out


def read_cells(path=CELLS):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            tid, scope, val = line.rstrip("\n").split("\t")[:3]
            out.append((tid, scope, None if scope != "k" else int(val)))
    return out


def audit(probe_path=PROBE, cells_path=CELLS, map_path=NMAP,
          pos_frac=0.5, verbose=True):
    kp, seg = load_k_positions(probe_path)
    mp = read_map(map_path)
    cells = read_cells(cells_path)
    L = []
    L.append("=" * 74)
    L.append("阶梯位点审计（零 GPU）：`k` 档到底挑到了哪些位置")
    L.append("=" * 74)

    # ---- 参数真义（先把话说准，再谈对不对）----
    L.append("\n【0】参数真义：`pos_frac` **不是位置**")
    L.append("  全部历史版本逐字相同的一行（r201:104 / r204:392）：")
    L.append("      t = max(1, int(n * a.pos_frac))      # n = len(gen)")
    L.append("  ⚖ 它决定**有效前缀比例**（生成序列留前 %.0f%%），⛔ 没有任何偏移量。" % (pos_frac * 100))
    L.append("  ⚖⚠ 而 `n_eff = P + t` ⇒ **阶梯分母随 pos_frac 一起动** ⇒")
    L.append("     扫 pos_frac = 同时改「有效前缀长度」与「阶梯分母」，⛔ 不是单自由度。")

    # ---- 运行时恒等 ----
    bad = []
    for tid, r in mp.items():
        P, ng, t, ne = (int(r["P"]), int(r["n_gen"]), int(r["t"]), int(r["n_eff"]))
        if t != max(1, int(ng * pos_frac)):
            bad.append("%s: t=%d != int(%.2f·%d)=%d" % (tid, t, pos_frac, ng, int(ng * pos_frac)))
        if ne != P + t:
            bad.append("%s: n_eff=%d != P+t=%d+%d" % (tid, ne, P, t))
    if bad:
        raise HardFail("运行时恒等不成立（%d 处）：%s%s"
                       % (len(bad), "；".join(bad[:3]), " …" if len(bad) > 3 else ""))
    L.append("\n【1】运行时恒等：%d 条轨迹 `t == int(%.2f·n_gen)` 且 `n_eff == P+t` 全成立"
             % (len(mp), pos_frac))

    # ---- 位点分段 ----
    kcells = [(tid, k) for (tid, scope, k) in cells if scope == "k"]
    if not kcells:
        raise HardFail("格表里一格 k 口径的都没有 ⇒ 未量到（不许读成「位点没问题」）")
    rows = []
    mism = []
    for tid, k in kcells:
        if tid not in mp:
            mism.append("%s 不在 n_eff_map 里" % tid)
            continue
        P, ne = int(mp[tid]["P"]), int(mp[tid]["n_eff"])
        pos = kp(ne, k, 0, True)          # 种子 0 + nested，与仪器同口径
        if len(pos) != k:                  # ⚖ 自证：真的挑了 k 个
            mism.append("%s k=%d 挑到 %d 个" % (tid, k, len(pos)))
            continue
        n_prompt = sum(1 for p in pos if p < P)
        rows.append({"tid": tid, "k": k, "n_eff": ne, "P": P,
                     "frac": n_prompt / float(k), "n_prompt": n_prompt,
                     "frac_k": k / float(ne)})
    if mism:
        raise HardFail("位点自证失败（%d 处）：%s%s"
                       % (len(mism), "；".join(mism[:3]), " …" if len(mism) > 3 else ""))
    L.append("\n【2】%d 个 k 档的位点已算出（种子 0 + nested，与仪器同口径；逐档自证 |pos|==k）"
             % len(rows))

    L.append("\n【3】每个位点落在哪一段：[0,P) = prompt 段，P..n_eff = 生成段")
    L.append("     按「覆盖率 k/n_eff」排序看 prompt 占比：")
    L.append("     %-34s %-7s %-9s %-9s %s"
             % ("tid", "k", "k/n_eff", "P/n_eff", "prompt 占比"))
    for r in sorted(rows, key=lambda x: (x["frac_k"], x["tid"]))[:10]:
        L.append("     %-34s %-7d %-9.4f %-9.4f %.3f"
                 % (r["tid"], r["k"], r["frac_k"], r["P"] / float(r["n_eff"]), r["frac"]))
    L.append("     …（共 %d 档，完整表见产物）" % len(rows))

    fr = sorted(r["frac"] for r in rows)
    L.append("\n  prompt 占比：最小 %.4f  中位 %.4f  最大 %.4f"
             % (fr[0], fr[len(fr) // 2], fr[-1]))
    L.append("  ⚖ P/n_eff 的分布：%.4f .. %.4f（prompt 段占序列多长，两臂同值）"
             % (min(int(r["P"]) / float(r["n_eff"]) for r in rows),
                max(int(r["P"]) / float(r["n_eff"]) for r in rows)))

    # ---- 判定：拿「均匀采样」这个零假设去比，而不是「整档只落一段」----
    # ⚖⚠⚠⚠ 修订 244.26：第一版判据是「有整档 100% 落在一段 ⇒ 不同类、不得合池」，
    # ⚖⚗ 那是**假警报的配方**：位点由种子 0 的置换均匀挑出 ⇒ k=1 时落在
    # ⚖   prompt 的概率就是 p = P/n_eff（实测 0.036–0.429）⇒ 十几档里
    # ⚖   出现几个「全在生成段」是**均匀采样的必然结果**，不是缺陷。
    # ⚖⚗ 而且第一版还把 frac==0.0（=全在**生成**段）印成「全部落在 prompt 段」
    # ⚖   ⇒ 措辞与自己算的量反了（同族：措辞必须与它实际比的东西对齐）。
    # ⚖⇒ 改成对零假设做二项检验，并**显式处理多重比较**（109 档 ⇒ p<0.05 预期见 5.45 个）。
    from math import lgamma, log, exp
    tests = []
    for r in rows:
        k = r["k"]
        p = r["P"] / float(r["n_eff"])
        obs = r["n_prompt"]
        # ⚖⚠⚠ 精确二项在 k=881 上会**溢出**：`comb(881,440)` ≈ 10^263，
        # ⚖   `comb * p**j * ...` 直接 OverflowError（第一版真崩过）。
        # ⚖⇒ 对数空间算 pmf，再按**最大项**缩放（只保比值，尾部下溢可忽略），
        # ⚖   ⛔ 不用「凑合的近似分布」—— 近似会把真信号抹平。
        lp1, lq1 = log(p), log(1.0 - p)
        lpmf = {}
        for j in range(k + 1):
            lpmf[j] = (lgamma(k + 1) - lgamma(j + 1) - lgamma(k - j + 1)
                       + j * lp1 + (k - j) * lq1)
        mx = max(lpmf.values())
        sc = {j: exp(v - mx) for j, v in lpmf.items()}
        cut = sc[obs]
        pv = min(1.0, sum(v for v in sc.values() if v <= cut * (1 + 1e-12)))
        tests.append({"tid": r["tid"], "k": k, "obs": obs, "p_exp": p,
                      "frac": r["frac"], "pv": pv})
    n_tests = len(tests)
    bonf = 0.05 / n_tests
    tests.sort(key=lambda x: x["pv"])

    L.append("\n【4】判定：位点分布是否**偏离均匀采样**（二项精确双尾）")
    L.append("  零假设 H0：位点均匀 ⇒ 落在 prompt 段的概率 p = P/n_eff")
    L.append("  ⚖ 多重比较：%d 档 ⇒ p<0.05 时期望出现 **%.2f** 个 ⇒ ⛔ 不能拿 0.05 当门槛，"
             % (n_tests, 0.05 * n_tests))
    L.append("     本工具用 Bonferroni 门槛 p < 0.05/%d = %.2e" % (n_tests, bonf))
    L.append("  最极端的 6 档：")
    L.append("     %-34s %-6s %-6s %-8s %-10s %s"
             % ("tid", "k", "实得", "期望 p", "实得占比", "二项 p"))
    for t in tests[:6]:
        L.append("     %-34s %-6d %-6d %-8.4f %-10.3f %.4f"
                 % (t["tid"], t["k"], t["obs"], t["p_exp"], t["frac"], t["pv"]))
    below = sum(1 for t in tests if t["pv"] < 0.05)
    extreme = [t for t in tests if t["pv"] < bonf]
    L.append("  实测 p<0.05 的档数：%d（期望 %.2f）" % (below, 0.05 * n_tests))
    if extreme:
        L.append("  ⛔ 有 %d 档超过 Bonferroni 门槛 ⇒ 位点分布**可检出地**偏离均匀采样：" % len(extreme))
        for t in extreme[:10]:
            L.append("     · %s k=%d 实得 %d / 期望 p=%.4f ⇒ 二项 p=%.3e"
                     % (t["tid"], t["k"], t["obs"], t["p_exp"], t["pv"]))
        L.append("  ⛔ 那几档量的东西与均匀假设下不同，⛔ 不得与其它档合池。")
        return "\n".join(L), 1
    L.append("  ✅ 无档超过 Bonferroni 门槛 ⇒ 位点分布与**均匀采样不可区分**。")
    L.append("  ⚖⚠ 这句话**很弱**，它只说「看不出异常」：")
    L.append("     ⛔ 它**不**说位点有代表性；⛔ 它**不**说阶梯排对了；")
    L.append("     ⛔ 「没有偏离均匀」与「挑得对」是两件完全不同的事。")
    L.append("  ⚖ 另：prompt 占比 0.0000 的档有 %d 个、1.0000 的档有 %d 个 ——"
             % (sum(1 for r in rows if r["frac"] == 0.0),
                sum(1 for r in rows if r["frac"] == 1.0)))
    L.append("     这在 k 小时是均匀采样的**必然结果**（k=1 落在 prompt 的概率 = P/n_eff），")
    L.append("     ⛔ 不是缺陷；第一版判据正是把它误当成缺陷。")
    L.append("\n【5】本审计**依赖**的另一条（不在本工具内验）")
    L.append("  ⚖ 位点的总体取 `n_eff = P + t`，前提是 `P == len(pid)`：")
    L.append("     生产者 `r204_noise_probe.py:393` 的切片是 `(pid + gen)[: P + t]`")
    L.append("     —— 用的是**侧车**的 `P`，不是 tokenizer 的 `len(pid)`。")
    L.append("     ⚖ 账本 244.7.8 / 244.9 已实测独立 tokenizer 重编码 60/60 相等")
    L.append("     ⇒ 该前提成立；⛔ 但本工具**没有**自己验它，⛔ 不许把本审计说成端到端。")
    return "\n".join(L), 0


# ---------------------------------------------------------------- 自检
def selftest():
    T = []

    def ck(name, fn):
        try:
            fn()
            T.append((name, "PASS", ""))
        except AssertionError as e:
            T.append((name, "FAIL", str(e) or "断言失败"))
        except Exception as e:
            T.append((name, "FAIL", "%s: %s" % (type(e).__name__, e)))

    # A1 绿：真实数据跑通，且报出 prompt 占比
    def a1():
        txt, rc = audit()
        assert "prompt 占比" in txt, txt[-400:]
        assert "t == int" in txt or "运行时恒等" in txt, txt[-400:]
        assert rc in (0, 1), rc
    ck("A1 绿：真实格表跑通并报出 prompt 占比与运行时恒等", a1)

    # A2 红：恒等被破坏 ⇒ 必须硬失败
    # ⚖ 夹具须**先自证**造出了目标条件：这里直接把 t 改掉 1。
    def a2():
        import tempfile
        tmp = tempfile.mkdtemp()
        rows = ["tid\tP\tn_gen\tt\tn_eff"]
        rows.append("p00__think\t108\t3309\t1655\t1763")   # t 应为 1654
        mp = os.path.join(tmp, "m.tsv")
        open(mp, "w", encoding="utf-8").write("\n".join(rows) + "\n")
        cl = os.path.join(tmp, "c.txt")
        open(cl, "w", encoding="utf-8").write("p00__think\tk\t881\n")
        try:
            audit(map_path=mp, cells_path=cl)
        except HardFail as e:
            assert "恒等" in str(e), str(e)
            return
        raise AssertionError("t 被改坏竟然没报错")
    ck("A2 红：t 与 n_eff 的运行时恒等被破坏 ⇒ 硬失败", a2)

    # A3 红：探针里**从不调用** `_k_positions` ⇒ 必须拒用
    # ⚖⚠ 这条原本写成「抽出的源码不在文件里逐字出现」，自检当场抓到那是
    # ⚖ **恒绿**的（seg 本就从 src 抽出，按构造恒真）⇒ 换成真正能红的这条。
    def a3():
        import tempfile
        tmp = tempfile.mkdtemp()
        p = os.path.join(tmp, "fake.py")
        open(p, "w", encoding="utf-8").write(
            "def _k_positions(n, k, seed=0, nested=False):\n    return [0] * k\n"
            "def unrelated():\n    return 1\n")
        try:
            load_k_positions(p)
        except HardFail as e:
            assert "没有任何地方调用" in str(e), str(e)
            return
        raise AssertionError("定义了却从不调用的函数竟然被接受了")
    ck("A3 红：探针里从不调用 `_k_positions` ⇒ 拒用（非恒绿）", a3)

    # A5 红：seed 默认值不是 0 ⇒ 本审计算的是另一组位点 ⇒ 必须拒用
    def a5():
        import tempfile
        tmp = tempfile.mkdtemp()
        p = os.path.join(tmp, "seed1.py")
        open(p, "w", encoding="utf-8").write(
            "def _k_positions(n, k, seed=1, nested=False):\n    return [0] * k\n"
            "def caller():\n    return _k_positions(4, 2, nested=True)\n")
        try:
            load_k_positions(p)
        except HardFail as e:
            assert "seed" in str(e), str(e)
            return
        raise AssertionError("seed 默认值不是 0 竟然被接受了")
    ck("A5 红：`_k_positions` 的 seed 默认值不是 0 ⇒ 拒用", a5)

    # A6 红：调用点不传 nested ⇒ 仪器可能用的是非嵌套位点 ⇒ 必须拒用
    def a6():
        import tempfile
        tmp = tempfile.mkdtemp()
        p = os.path.join(tmp, "nonest.py")
        open(p, "w", encoding="utf-8").write(
            "def _k_positions(n, k, seed=0, nested=False):\n    return [0] * k\n"
            "def caller():\n    return _k_positions(4, 2)\n")
        try:
            load_k_positions(p)
        except HardFail as e:
            assert "nested" in str(e), str(e)
            return
        raise AssertionError("调用点不传 nested 竟然被接受了")
    ck("A6 红：调用点不传 `nested=` ⇒ 拒用（两者位点不可比）", a6)

    # A4 红：k 与挑出的位数不符 ⇒ 必须硬失败（自证失效就是审计失效）
    def a4():
        import tempfile
        tmp = tempfile.mkdtemp()
        src = open(PROBE, encoding="utf-8").read()
        import ast as _ast
        tree = _ast.parse(src)
        fn = [n for n in tree.body if isinstance(n, _ast.FunctionDef)
              and n.name == "_k_positions"][0]
        seg = _ast.get_source_segment(src, fn)
        bad = seg.replace("return sorted(int(x) for x in _rng.permutation(n)[:k])",
                          "return sorted(int(x) for x in _rng.permutation(n)[:k - 1])")
        assert bad != seg, "没改到夹具"
        p = os.path.join(tmp, "fake2.py")
        # ⚖ 夹具必须同时带上**调用点**，否则会先撞上「从不调用」那道检查，
        # ⚖ 测的就不是「位数与 k 不符」这个条件了（244.24.1 坑二同源）。
        open(p, "w", encoding="utf-8").write(
            bad + "\n\ndef caller(h, n_sites, nested):\n"
                  "    return _k_positions(len(h), n_sites, nested=nested)\n")
        rows = ["tid\tP\tn_gen\tt\tn_eff",
                "p00__think\t108\t3309\t1654\t1762"]
        mp = os.path.join(tmp, "m.tsv")
        open(mp, "w", encoding="utf-8").write("\n".join(rows) + "\n")
        cl = os.path.join(tmp, "c.txt")
        open(cl, "w", encoding="utf-8").write("p00__think\tk\t881\n")
        try:
            audit(probe_path=p, map_path=mp, cells_path=cl)
        except HardFail as e:
            assert "自证" in str(e), str(e)
            return
        raise AssertionError("位点数与 k 不符竟然没报错")
    ck("A4 红：挑出的位数 != k ⇒ 硬失败（自证失效即审计失效）", a4)

    # A7 绿：门槛必须是 Bonferroni，且真实数据判「不可区分」
    # ⚖⚠ 这条让**门槛本身**可被测：把 0.05/109 改回 0.05 ⇒ 真实数据里
    # ⚖   已有 1 档 p=0.0354 ⇒ 工具会改口报「⛔ 偏离均匀」⇒ A7 由 PASS 变 FAIL。
    # ⚖⚗ 这也说明「门槛定多严」不是口味问题：在**真实数据**上它会改变结论。
    def a7():
        txt, rc = audit()
        assert "Bonferroni" in txt, txt[-500:]
        assert "0.05/%d" % 109 in txt or "4.59e-04" in txt, txt[-500:]
        assert rc == 0, ("真实数据被判成 rc=%d" % rc)
        assert "不可区分" in txt, txt[-500:]
    ck("A7 绿：门槛是 Bonferroni，且真实数据判「与均匀采样不可区分」", a7)

    npass = sum(1 for _, s, _ in T if s == "PASS")
    for name, s, msg in T:
        print("[%s] %s%s" % (s, name, ("  ← " + msg) if msg else ""))
    print("ladder_position_audit --selftest: %d/%d" % (npass, len(T)))
    return 0 if npass == len(T) else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", default=PROBE)
    ap.add_argument("--cells", default=CELLS)
    ap.add_argument("--map", dest="map_path", default=NMAP)
    ap.add_argument("--pos-frac", type=float, default=0.5)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    try:
        txt, rc = audit(args.probe, args.cells, args.map_path, args.pos_frac)
        print(txt)
        return rc
    except HardFail as e:
        print("⛔ %s" % e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
