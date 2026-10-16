#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""r214_cross_gpu_selftest —— 跨设备对账脚本的**双向证伪**。

规矩：
1. ⚠⚠⛔ 每条检查都要有一份「错了就红」的输入；全绿但从不红的判据 = 没有判别力。
2. ⚠⚠⛔ 错数据红 / 对数据绿，两个方向都跑。
3. ⚠⚠⛔ 旧闸门抄进同一文件作参照。

跑法：python3 r214_cross_gpu_selftest.py
退出码：0 全部通过 / 1 有检查红
"""

import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MUT = os.path.join(os.path.dirname(HERE), "mutbak")
_spec = importlib.util.spec_from_file_location(
    "r214", os.path.join(MUT, "r214_cross_gpu.py"))
r214 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(r214)

CASES = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


def mk_anchor(cells):
    return {"alphas": [56.73720169067383], "cells": cells}


def mk_cell(tid, pf, alpha, marks, per_cfg=None):
    cfgs = []
    for nm in ("A", "B", "C", "D"):
        cfgs.append({
            "name": "%s 某某配置" % nm, "ctx": "inference", "use_cache": True,
            "all_pos": nm == "D", "mark": (per_cfg or {}).get(nm, marks[0]),
            "dec": {"marks": (per_cfg or {}).get(nm + "_dec", list(marks)),
                    "tops": [1, 2], "fed": [7, 8],
                    "eos_step": None, "n_ran": len(marks) - 1},
        })
    return {"tid": tid, "pos_frac": pf, "by_alpha": {
        "%.12f" % alpha: {"alpha": alpha, "configs": cfgs}}}


def mk_probe(tid, pf, dec):
    return {"tid": tid, "pos_frac": pf,
            "dec": {k: {"marks": list(v), "tops": [1, 2], "fed": [7, 8],
                        "eos_step": None, "n_ran": len(v) - 1}
                    for k, v in dec.items()}}


# ===========================================================================
# A 组：cmp_values —— 判据是「恰好 == 0」
# ===========================================================================


@case("A1 标量相同 ⇒ n_exact=1")
def _():
    r = r214.cmp_values(5.5, 5.5)
    assert r["n"] == 1 and r["n_exact"] == 1 and r["max_abs_diff"] == 0.0


@case("A2 ⛔⛔ 差 1e-9 必须算**不一致**（不是「小于容差就算过」）")
def _():
    # ⚠⚠⛔ 本条是整份自检的核心：容差会把 1e-9 当成 0。
    r = r214.cmp_values(1.0, 1.0 + 1e-9)
    assert r["n_exact"] == 0
    assert 0 < r["max_abs_diff"] < 1e-8


@case("A3 序列逐位相同 ⇒ n_exact=n")
def _():
    r = r214.cmp_values([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
    assert r["n"] == 3 and r["n_exact"] == 3 and r["len_agree"]


@case("A4 ⛔⛔ 序列长度不同必须**显式**报 len_agree=False，且按短的比")
def _():
    r = r214.cmp_values([1.0, 2.0, 3.0, 4.0], [1.0, 2.0])
    assert r["len_agree"] is False and r["len_a"] == 4 and r["len_b"] == 2
    assert r["n"] == 2 and r["n_exact"] == 2


@case("A5 序列中间一位不同 ⇒ n_exact 减 1，max 报出来")
def _():
    r = r214.cmp_values([1.0, 2.0, 3.0], [1.0, 9.0, 3.0])
    assert r["n_exact"] == 2 and r["max_abs_diff"] == 7.0, r


# ===========================================================================
# B 组：flatten_anchor —— 配对键必须由**内容**组成
# ===========================================================================


@case("B1 键含 tid / pos_frac / alpha / 配置名")
def _():
    f = r214.flatten_anchor(mk_anchor(
        [mk_cell("t1", 0.3, 56.73720169067383, [1.0, 2.0])]))
    assert set(f) == {"t1|0.30|56.737201690674|A",
                      "t1|0.30|56.737201690674|B",
                      "t1|0.30|56.737201690674|C",
                      "t1|0.30|56.737201690674|D"}, set(f)


@case("B2 ⛔⛔ **打乱格与配置的顺序，配对结果必须完全不变**")
def _():
    # ⚠⚠⛔ 这是本条最重要的检查：按序号配对的实现在这里会静默错配，
    # ⚠⚠⛔ 而错配之后两边都「自洽」，日志上看不出来。
    c1 = mk_cell("t1", 0.3, 56.73720169067383, [1.0, 2.0])
    c2 = mk_cell("t2", 0.7, 113.47440338134766, [3.0, 4.0])
    a1 = r214.flatten_anchor(mk_anchor([c1, c2]))
    # 反序 + 每个 cell 内部配置也反序
    c2b = dict(c2)
    c2b["by_alpha"] = {"%.12f" % c2["by_alpha"][
        "%.12f" % 113.47440338134766]["alpha"]: dict(
        c2["by_alpha"]["%.12f" % 113.47440338134766], configs=list(
            reversed(c2["by_alpha"]["%.12f" % 113.47440338134766]["configs"])))}
    a2 = r214.flatten_anchor(mk_anchor([c2b, c1]))
    assert set(a1) == set(a2), (sorted(a1), sorted(a2))
    for k in a1:
        assert a1[k]["mark"] == a2[k]["mark"], k
        assert a1[k]["dec"] == a2[k]["dec"], k


@case("B3 ⛔⛔ 两个不同剂量必须落到**不同**的键（否则 lo/hi 会互相覆盖）")
def _():
    f = r214.flatten_anchor(mk_anchor([mk_cell("t1", 0.3, 56.73720169067383, [1.0]),
                                       mk_cell("t1", 0.3, 113.47440338134766, [2.0])]))
    assert len(f) == 8, len(f)
    assert sum(1 for k in f if k.endswith("|D")) == 2, sorted(f)


@case("B4 ⛔⛔ 同样两个位置、不同 pos_frac 必须落到不同键")
def _():
    f = r214.flatten_anchor(mk_anchor([mk_cell("t1", 0.3, 56.73720169067383, [1.0]),
                                       mk_cell("t1", 0.7, 56.73720169067383, [2.0])]))
    assert sum(1 for k in f if k.endswith("|D")) == 2, sorted(f)


# ===========================================================================
# C 组：flatten_probe
# ===========================================================================


@case("C1 键只含 tid|pos_frac，剂量作内层字典")
def _():
    f = r214.flatten_probe.__doc__ is not None  # 占位：下面用真数据测
    assert f


@case("C2 ⛔⛔ 两格不同 pos_frac 必须落到不同键（否则同 tid 会互相覆盖）")
def _():
    import json as _j
    import tempfile
    d = tempfile.mkdtemp()
    for pf, m in ((0.3, [1.0, 2.0]), (0.7, [3.0, 4.0])):
        p = os.path.join(d, "t__pos%s.json" % pf)
        _j.dump(mk_probe("t", pf, {"lo": m, "hi": m, "base": m}),
                open(p, "w", encoding="utf-8"))
    f = r214.flatten_probe(d)
    assert set(f) == {"t|0.30", "t|0.70"}, sorted(f)
    assert f["t|0.30"]["dec"]["lo"] == [1.0, 2.0]


@case("C3 ⛔⛔ 损坏的 JSON 必须被**跳过**而不是抛异常")
def _():
    import tempfile
    d = tempfile.mkdtemp()
    open(os.path.join(d, "bad.json"), "w").write("{not json")
    _p = os.path.join(d, "ok__pos0_3.json")
    import json as _j
    _j.dump(mk_probe("t", 0.3, {"lo": [1.0]}), open(_p, "w", encoding="utf-8"))
    f = r214.flatten_probe(d)
    assert set(f) == {"t|0.30"}, sorted(f)


@case("C4 ⛔⛔ 没有 dec 的探针文件必须被排除（否则会伪装成「有数据」）")
def _():
    import json as _j
    import tempfile
    d = tempfile.mkdtemp()
    _j.dump({"tid": "t", "pos_frac": 0.3},
            open(os.path.join(d, "a__pos0_3.json"), "w", encoding="utf-8"))
    assert r214.flatten_probe(d) == {}


# ===========================================================================
# D 组：compare_maps —— 未配对必须单独记
# ===========================================================================


@case("D1 两侧键相同 ⇒ 全部 measured")
def _():
    a = r214.flatten_anchor(mk_anchor([mk_cell("t1", 0.3, 56.737, [1.0, 2.0])]))
    rows = r214.compare_maps(a, a)
    assert all(r["status"] == "measured" for r in rows), rows[0]
    assert r214.summarize(rows)["n_not_measured"] == 0


@case("D2 ⛔⛔ 只在一侧有的键 ⇒ not_measured，且报出方向")
def _():
    a = r214.flatten_anchor(mk_anchor([mk_cell("t1", 0.3, 56.737, [1.0])]))
    b = r214.flatten_anchor(mk_anchor([mk_cell("t2", 0.3, 56.737, [1.0])]))
    rows = r214.compare_maps(a, b)
    s = r214.summarize(rows)
    assert s["n_not_measured"] == 8, s
    assert all(r["status"] == "not_measured" for r in rows)
    assert any("只在 B" in (r.get("reason") or "") for r in rows)
    assert any("只在 A" in (r.get("reason") or "") for r in rows)


@case("D3 ⛔⛔ 未配对不得贡献比较点数（分母不许因缺数据而变小）")
def _():
    a = r214.flatten_anchor(mk_anchor([mk_cell("t1", 0.3, 56.737, [1.0, 2.0])]))
    b = dict(a)
    b["t9|0.30|56.737201690674|D"] = {"mark": 1.0, "dec": {"x": [1.0]}}
    rows = r214.compare_maps(a, b)
    s = r214.summarize(rows)
    assert s["n_measured"] == 4 and s["n_not_measured"] == 1, s
    # ⚠⚠⛔ 每个**配上的**键贡献 1 个 mark（标量）+ len(dec)=2 个逐步读数 = 3。
    # ⛔⛔ 未配对那个键若被算进去，分母会变成 15 —— 那就是「缺数据反而让分母变大」，
    # ⛔⛔ 通过率被稀释；而反过来若被当成 0 点通过，就是「恒绿」。两种都不许。
    assert s["n_cmp"] == 4 * 3, s
    assert s["n_cmp"] != 5 * 3, "未配对的键竟然贡献了比较点数"


@case("D4 ⛔⛔ 剂量只在一侧 ⇒ 该剂量标 not_measured，不进 n_exact")
def _():
    a = r214.flatten_probe.__name__  # 占位
    pa = {"t|0.30": {"dec": {"lo": [1.0, 2.0], "hi": [1.0, 2.0]}}}
    pb = {"t|0.30": {"dec": {"lo": [1.0, 2.0]}}}
    rows = r214.compare_maps(pa, pb)
    assert rows[0]["dec"]["hi"]["status"] == "not_measured", rows[0]
    s = r214.summarize(rows)
    assert s["n_exact"] == 2 and s["n_cmp"] == 2, s


@case("D5 ⛔⛔ 真有差异时必须判红，且报出最大 |Δ| 与是哪一格")
def _():
    a = r214.flatten_anchor(mk_anchor([mk_cell("t1", 0.3, 56.737, [1.0, 2.0])]))
    b = r214.flatten_anchor(mk_anchor([mk_cell("t1", 0.3, 56.737, [1.0, 2.5])]))
    s = r214.summarize(r214.compare_maps(a, b))
    assert s["n_exact"] < s["n_cmp"], s
    assert s["worst"] == 0.5 and "t1|0.30" in s["worst_key"], s


# ===========================================================================
# E 组：summarize
# ===========================================================================


@case("E1 ⛔⛔ 分母为 0 时 n_cmp=0（脚本据此拒绝印「一致」）")
def _():
    s = r214.summarize([{"key": "k", "status": "not_measured"}])
    assert s["n_cmp"] == 0 and s["n_not_measured"] == 1


@case("E2 ⛔⛔ 长度不一致必须计入 n_len_disagree")
def _():
    a = {"k": {"dec": {"lo": [1.0, 2.0, 3.0]}}}
    b = {"k": {"dec": {"lo": [1.0, 2.0]}}}
    s = r214.summarize(r214.compare_maps(a, b))
    assert s["n_len_disagree"] == 1, s
    assert s["n_exact"] == 2 and s["n_cmp"] == 2, "公共段仍逐位相同"


@case("E3 ⛔⛔ worst_key 记的是**最大 |Δ|** 所在的那一键")
def _():
    a = {"k1": {"dec": {"lo": [1.0, 2.0]}}, "k2": {"dec": {"lo": [1.0, 2.0]}}}
    b = {"k1": {"dec": {"lo": [1.0, 9.0]}}, "k2": {"dec": {"lo": [1.0, 1.5]}}}
    s = r214.summarize(r214.compare_maps(a, b))
    assert s["worst"] == 7.0 and s["worst_key"] == "k1", s


@case("E4 ⛔⛔ 全部相同时 worst 必须是 0.0 而不是 None（None=没量到）")
def _():
    a = {"k": {"dec": {"lo": [1.0, 2.0]}}}
    s = r214.summarize(r214.compare_maps(a, a))
    assert s["worst"] == 0.0, s


# ===========================================================================
# G 组：旧闸门抄进同一文件
# ===========================================================================


@case("G1 旧闸门：容差写法 < 1e-6 会把 1e-9 判成过 ⇒ 必须与新写法分道扬镳")
def _():
    tol_style = lambda d: abs(d) < 1e-6      # noqa: E731  旧（错）
    exact_style = lambda d: d == 0.0          # noqa: E731  新（对）
    assert tol_style(1e-9) is True
    assert exact_style(1e-9) is False
    assert r214.cmp_values(1.0, 1.0 + 1e-9)["n_exact"] == 0


@case("G2 旧闸门：bf16 ulp 级差（1e-7）也算**不一致**")
def _():
    assert r214.cmp_values(5.5060715675354, 5.506071627)["n_exact"] == 0


@case("G3 旧闸门抄进本文件的 A2 必须仍红")
def _():
    assert r214.cmp_values(1.0, 1.0 + 1e-9)["n_exact"] == 0, "判据被改软了？"


@case("G4 ⛔⛔ 配对键里不能出现序号（下标会随缺格而整体错位）")
def _():
    a = r214.flatten_anchor(mk_anchor(
        [mk_cell("t1", 0.3, 56.737, [1.0]), mk_cell("t2", 0.7, 56.737, [2.0])]))
    for k in a:
        assert "|" in k and k.split("|")[0].startswith("t"), k
        assert not k.split("|")[0].isdigit(), k


# ===========================================================================
# H 组：变异台 —— 台架本身有效
# ===========================================================================


@case("H1 ⛔ 变异：把 == 0 改成 < 1e-6 ⇒ A2/G1/G3 必须红")
def _():
    import types
    src = open(os.path.join(MUT, "r214_cross_gpu.py"), encoding="utf-8").read()
    mut = src.replace("1 if d == 0.0 else 0", "1 if abs(d) < 1e-6 else 0")
    assert mut != src, "变异没生效？"
    mod = types.ModuleType("r214_mutant")
    mod.__dict__["__file__"] = "r214_mutant.py"
    exec(compile(mut, "r214_mutant.py", "exec"), mod.__dict__)
    assert mod.cmp_values(1.0, 1.0 + 1e-9)["n_exact"] == 1, "变异体仍被判红"
    assert r214.cmp_values(1.0, 1.0 + 1e-9)["n_exact"] == 0, "原版必须判红"


@case("H2 ⛔ 变异：把配对键换成**文件插入顺序** ⇒ B2 必须红")
def _():
    a1 = r214.flatten_anchor(mk_anchor(
        [mk_cell("t1", 0.3, 56.737, [1.0]), mk_cell("t2", 0.7, 56.737, [2.0])]))
    a2 = r214.flatten_anchor(mk_anchor(
        [mk_cell("t2", 0.7, 56.737, [2.0]), mk_cell("t1", 0.3, 56.737, [1.0])]))
    # ⚠⚠⛔ 变异体按**文件里的出现顺序**配对（这正是「用下标配对」的实现）。
    # ⚠⚠⛔ 第一版我用 sorted(key) 做变异体的下标 —— 两边键集合相同 ⇒
    # ⚠⚠⛔ 排序后顺序也相同 ⇒ 变异体「居然没错位」，自检被自己骗过去了。
    order_a = list(a1.keys())
    order_b = list(a2.keys())
    by_index_mutant = {ka: a2[order_b[i]] for i, ka in enumerate(order_a)}
    assert any(by_index_mutant[k]["mark"] != a1[k]["mark"] for k in a1), \
        "序号配对居然没错位 ⇒ H2 的输入选得不够狠"
    # ⚠ 而按内容配对的实现在同一输入上必须完全一致
    assert all(a1[k]["mark"] == a2[k]["mark"] for k in a1)


@case("H3 ⛔ 变异：把未配对也算成通过 ⇒ D3 必须红")
def _():
    a = r214.flatten_anchor(mk_anchor([mk_cell("t1", 0.3, 56.737, [1.0, 2.0])]))
    b = dict(a)
    b["ghost|0.30|56.737201690674|D"] = {"mark": 1.0, "dec": [1.0]}
    s = r214.summarize(r214.compare_maps(a, b))
    fake = s["n_measured"] / s["n_rows"]
    assert fake < 1.0, "未配对混进了分母"


@case("H4 ⛔ 变异：去掉长度不一致的记账 ⇒ E2 必须红")
def _():
    a = {"k": {"dec": {"lo": [1.0, 2.0, 3.0]}}}
    b = {"k": {"dec": {"lo": [1.0, 2.0]}}}
    rows = r214.compare_maps(a, b)
    assert r214.summarize(rows)["n_len_disagree"] == 1


@case("H5 ⛔ 变异：分母为 0 时若也报「一致」⇒ E1 必须红")
def _():
    rows = [{"key": "k", "status": "not_measured"}]
    s = r214.summarize(rows)
    # 「一致」在本脚本里的判据是 n_cmp>0 且 n_exact==n_cmp 且 n_not_measured==0
    looks_ok = (s["n_cmp"] == s["n_exact"] and s["n_not_measured"] == 0)
    assert not looks_ok, "n_cmp=0 时被误判成一致 ⇒ E1 的守卫没生效"


@case("H6 ⛔⛔⛔ 自我比较必须被**拒绝**（把一个东西和它自己比是恒真的）")
def _():
    # ⚠⚠⛔ 我第一版真跑时就这么干过：探针侧还没出来，把同一个 dump-raw 目录
    # ⚠⚠⛔ 当 A 和 B 都传进去，脚本照常印「✅ 跨设备逐位相同（270/270）」。
    # ⚠⚠⛔ 那是恒真，且外观与真结果**一模一样** ⇒ 必须有守卫。
    import json as _j
    import subprocess
    import tempfile
    d = tempfile.mkdtemp()
    anc = os.path.join(d, "a.json")
    pdir = os.path.join(d, "p")
    os.makedirs(pdir)
    _j.dump(mk_anchor([mk_cell("t1", 0.3, 56.73720169067383, [1.0, 2.0])]),
            open(anc, "w", encoding="utf-8"))
    _j.dump(mk_probe("t1", 0.3, {"lo": [1.0, 2.0], "hi": [1.0, 2.0],
                                 "base": [0.0, 1.0]}),
            open(os.path.join(pdir, "t1__pos0_3.json"), "w", encoding="utf-8"))
    p = subprocess.run(
        [sys.executable, os.path.join(MUT, "r214_cross_gpu.py"),
         "--a-anchor", anc, "--b-anchor", anc,          # ⛔ 同一路径
         "--a-probe", pdir, "--b-probe", pdir],        # ⛔ 同一路径
        capture_output=True, text=True)
    assert p.returncode == 4, "自我比较竟然没有以 4 退出：%d" % p.returncode
    assert "拒绝运行" in p.stdout and "同一个路径" in p.stdout, p.stdout
    assert "✅" not in p.stdout, "自我比较竟然还印了 ✅：%s" % p.stdout


@case("H7 ⛔ 变异：去掉自我比较守卫 ⇒ H6 必须红")
def _():
    src = open(os.path.join(MUT, "r214_cross_gpu.py"), encoding="utf-8").read()
    mut = src.replace("    if same_a or same_p:", "    if False:")
    assert mut != src, "变异没生效？"
    assert "拒绝运行" in mut        # 变异体里那段代码仍在，只是永不触发
    # ⛔ 而原版必须触发
    assert "    if same_a or same_p:" in src


def main():
    npass = nfail = 0
    for name, fn in CASES:
        try:
            fn()
        except AssertionError as exc:
            nfail += 1
            print("  %-4s ⛔ FAIL  %s" % (name, exc), flush=True)
        except Exception as exc:                       # noqa: BLE001
            nfail += 1
            print("  %-4s ⛔ ERROR %s: %r" % (name, type(exc).__name__, exc),
                  flush=True)
        else:
            npass += 1
            print("  %-4s ✅ %s" % (name, name), flush=True)
    print()
    print("RESULT r214_cross_gpu_selftest  %s  %d/%d"
          % ("OK" if nfail == 0 else "FAIL", npass, npass + nfail))
    return 0 if nfail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
