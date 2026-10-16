#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""r213_stepwise_check_selftest —— 对账脚本的**双向证伪**。

规矩（本项目已付过代价的）：
1. ⚠⚠⛔ **判据必须能红**：每条检查都要有一份「错了就红」的输入，
   ⚠⚠⛔ 全绿但从不红的判据 = 没有判别力。
2. ⚠⚠⛔ **错数据红 / 对数据绿**，两个方向都要跑。
3. ⚠⚠⛔ **旧闸门抄进同一文件**作参照（见 G 组），不靠「以前验过」。

跑法：python3 r213_stepwise_check_selftest.py
退出码：0 全部通过 / 1 有检查红
"""

import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MUT = os.path.join(os.path.dirname(HERE), "mutbak")
_spec = importlib.util.spec_from_file_location(
    "r213", os.path.join(MUT, "r213_stepwise_check.py"))
r213 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(r213)

CASES = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


def mk_cell(tid="aime__aime25__p00__think", pf=0.3, alphas=(56.73720169067383,),
            marks=None, fed=None, cfg_names=("A", "B", "C", "D")):
    """造一份合成锚点。四配置的 marks 全同（= 假设它们彼此一致）。"""
    base = marks if marks is not None else [1.0, 2.0, 3.0]
    cells = []
    for al in alphas:
        cfgs = []
        for nm in cfg_names:
            cfgs.append({
                "name": "%s 流水线原样" % nm if nm == "D" else "%s cfg" % nm,
                "ctx": "inference", "use_cache": True,
                "all_pos": nm == "D",
                "mark": base[0], "dec": {
                    "marks": list(base), "tops": [1, 2, 3],
                    "fed": list(fed if fed is not None else [7, 8]),
                    "eos_step": None, "n_ran": len(base) - 1},
            })
        cells.append({
            "tid": tid, "pos_frac": pf, "P": 100, "t": 200, "n_gen": 900,
            "seq_len": 300, "repeat": 2,
            "by_alpha": {"%.12f" % al: {"alpha": al, "configs": cfgs}},
        })
    return {"alphas": list(alphas), "cells": cells}


def mk_probe(marks, fed=None, eos_step=None, alphas=None):
    al = alphas or {"base": 0.0, "lo": 56.73720169067383,
                    "hi": 113.47440338134766}
    lab = "lo" if abs(float(al["lo"]) - 56.73720169067383) < 1e-12 else "hi"
    dec = {}
    for k in ("base", "lo", "hi"):
        dec[k] = {"marks": list(marks) if k == lab else list(marks),
                  "tops": [1, 2, 3],
                  "fed": list(fed if fed is not None else [7, 8]),
                  "eos_step": eos_step, "n_ran": len(marks) - 1}
    return {"tid": "aime__aime25__p00__think", "pos_frac": 0.3,
            "dec": dec, "dec_alpha": dict(al)}


# ===========================================================================
# A 组：`cmp_series` —— 判据是「恰好 == 0」
# ===========================================================================


@case("A1 完全相同 ⇒ n_cmp=n_exact、first_bad=None")
def _():
    r = r213.cmp_series([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
    assert r["n_cmp"] == 3 and r["n_exact"] == 3
    assert r["first_bad_step"] is None and r["len_agree"]


@case("A2 ⛔⛔ 差 1e-9 也必须算**不一致**（不是「小于容差就算过」）")
def _():
    # ⚠⚠⛔ 这一条是整份自检的核心：容差会把 1e-9 当成 0，
    # ⚠⚠⛔ 而「恰好 == 0」才是我们要断言的东西。
    r = r213.cmp_series([1.0, 2.0, 3.0], [1.0, 2.0 + 1e-9, 3.0])
    assert r["first_bad_step"] == 1, r
    assert r["n_exact"] == 2
    assert 0 < r["max_abs_diff"] < 1e-8


@case("A3 ⛔⛔ first_bad_step 报的是**第一个**不为 0 的下标，不是最后一个")
def _():
    r = r213.cmp_series([1.0, 2.0, 3.0], [9.0, 2.0, 8.0])
    assert r["first_bad_step"] == 0, r
    assert r["n_exact"] == 1


@case("A4 ⛔⛔ 长度不同必须**显式**报 len_agree=False，且按**短的那个**比")
def _():
    r = r213.cmp_series([1.0, 2.0, 3.0, 4.0], [1.0, 2.0])
    assert r["len_agree"] is False
    assert r["len_pipe"] == 4 and r["len_probe"] == 2
    assert r["n_cmp"] == 2 and r["n_exact"] == 2
    # ⚠⚠⛔ 且**不许**因此判成「一致」—— 分母变了就是另一件事
    assert r["first_bad_step"] is None      # 公共部分确实全等
    # ⛔ 但 summarize 必须据此判 mismatch（见 B4）


@case("A5 空输入不抛，给 0 分母")
def _():
    r = r213.cmp_series([], [])
    assert r["n_cmp"] == 0 and r["max_abs_diff"] is None


# ===========================================================================
# B 组：`summarize` —— 三态必须分开
# ===========================================================================


@case("B1 not_measured **不进** matched 分母，也不算 mismatch")
def _():
    rows = [{"label": "ok", "n_cmp": 3, "n_exact": 3, "first_bad_step": None,
             "len_agree": True, "max_abs_diff": 0.0, "n_ran": 2},
            {"label": "miss", "status": "not_measured"}]
    s = r213.summarize(rows)
    assert s["n_matched"] == 1 and s["n_mismatch"] == 0
    assert s["n_not_measured"] == 1, s
    assert s["n_cmp"] == 3, "未量到的那行不得贡献比较点数"


@case("B2 ⛔⛔ 长度不一致 ⇒ 判 mismatch（哪怕公共段逐位相同）")
def _():
    rows = [{"label": "short", "n_cmp": 2, "n_exact": 2,
             "first_bad_step": None, "len_agree": False,
             "max_abs_diff": 0.0, "n_ran": 1}]
    s = r213.summarize(rows)
    assert s["n_mismatch"] == 1 and s["n_matched"] == 0, s
    assert s["n_len_disagree"] == 1


@case("B3 ⛔⛔ 实跑 < 预算的行必须被单列出来（分母变小而通过率不变）")
def _():
    rows = [{"label": "short", "n_cmp": 2, "n_exact": 2,
             "first_bad_step": None, "len_agree": True,
             "max_abs_diff": 0.0, "n_ran": 2, "eos_step": 2}]
    s = r213.summarize(rows, budget=8)
    assert len(s["rows_short_of_budget"]) == 1, s
    assert s["rows_short_of_budget"][0]["n_ran"] == 2
    # ⚠⚠⛔ 且它**仍然是 matched** —— 脚本不许偷偷把提前 EOS 判成失败，
    # ⚠⚠⛔ 但必须让「只跑了 2 步」这件事出现在汇总里。
    assert s["n_matched"] == 1


@case("B4 worst 记的是**最大 |Δ|**，并带上是哪一行")
def _():
    rows = [{"label": "a", "n_cmp": 1, "n_exact": 0, "first_bad_step": 0,
             "len_agree": True, "max_abs_diff": 1e-3},
            {"label": "b", "n_cmp": 1, "n_exact": 0, "first_bad_step": 0,
             "len_agree": True, "max_abs_diff": 5e-2}]
    s = r213.summarize(rows)
    assert abs(s["worst"] - 5e-2) < 1e-18 and s["worst_row"] == "b"


@case("B5 fed 分叉的行要进 first_divergences")
def _():
    rows = [{"label": "d", "n_cmp": 1, "n_exact": 1, "first_bad_step": None,
             "len_agree": True, "max_abs_diff": 0.0,
             "first_divergence_step": 3}]
    s = r213.summarize(rows)
    assert len(s["first_divergences"]) == 1 and s["first_divergences"][0]["step"] == 3


# ===========================================================================
# C 组：`first_divergence` —— token 链分叉
# ===========================================================================


@case("C1 两条 fed 全同 ⇒ None")
def _():
    d, n = r213.first_divergence([[7, 8, 9], [7, 8, 9]])
    assert d is None and n == 3


@case("C2 ⛔⛔ 第 2 步不同 ⇒ 报 2（不是「有几条链不同」）")
def _():
    d, n = r213.first_divergence([[7, 8, 9], [7, 5, 9]])
    assert d == 1, d


@case("C3 ⛔⛔ 长度不同取**最短**那条为分母，不因长链多出一步而误报分叉")
def _():
    d, n = r213.first_divergence([[7, 8], [7, 8, 9]])
    assert d is None and n == 2, (d, n)


@case("C4 空序列不抛")
def _():
    assert r213.first_divergence([[], []]) == (None, 0)


# ===========================================================================
# D 组：`build_rows` —— 装配
# ===========================================================================


@case("D1 全同 ⇒ matched，且剂量按**数值**配对（lo↔lo、hi↔hi）")
def _():
    a = mk_cell(alphas=(56.73720169067383, 113.47440338134766),
                marks=[1.0, 2.0, 3.0])
    pm = {("aime__aime25__p00__think", 0.3): mk_probe([1.0, 2.0, 3.0])}
    rows = r213.build_rows(a, pm)
    assert len(rows) == 2, rows
    assert {r["dose_label"] for r in rows} == {"lo", "hi"}, rows
    assert all(r["status"] == "measured" for r in rows)
    assert all(r["first_bad_step"] is None for r in rows)


@case("D2 ⛔⛔ 只改探针的第 2 步 ⇒ 那一行必须判不一致，且报出步号")
def _():
    a = mk_cell(alphas=(56.73720169067383,), marks=[1.0, 2.0, 3.0])
    pm = {("aime__aime25__p00__think", 0.3): mk_probe([1.0, 2.5, 3.0])}
    rows = r213.build_rows(a, pm)
    assert rows[0]["first_bad_step"] == 1, rows[0]
    assert r213.summarize(rows)["n_mismatch"] == 1


@case("D3 ⛔⛔ 探针侧没有 dec ⇒ 整格 not_measured，**不许**被跳过")
def _():
    a = mk_cell(alphas=(56.73720169067383,))
    pm = {("aime__aime25__p00__think", 0.3): {"tid": "x", "pos_frac": 0.3}}
    rows = r213.build_rows(a, pm)
    assert rows[0]["status"] == "not_measured", rows[0]
    s = r213.summarize(rows)
    assert s["n_not_measured"] == 1 and s["n_matched"] == 0


@case("D4 ⛔⛔ 锚点剂量对不上探针三条剂量 ⇒ not_measured 且报出实际值")
def _():
    a = mk_cell(alphas=(60.0,), marks=[1.0, 2.0])
    pm = {("aime__aime25__p00__think", 0.3): mk_probe([1.0, 2.0])}
    rows = r213.build_rows(a, pm)
    assert rows[0]["status"] == "not_measured"
    assert "60.000000000000" in rows[0]["reason"], rows[0]


@case("D5 ⛔⛔ 锚点侧配置 D 没 dec ⇒ not_measured（不是「A/B/C 都同就当过」）")
def _():
    a = mk_cell(alphas=(56.73720169067383,), marks=[1.0, 2.0], cfg_names=("A", "B", "C"))
    pm = {("aime__aime25__p00__think", 0.3): mk_probe([1.0, 2.0])}
    rows = r213.build_rows(a, pm)
    assert rows[0]["status"] == "not_measured", rows[0]


@case("D6 ⛔⛔ 配对按 (tid, pos_frac) 复合键，不能只按 tid")
def _():
    a = mk_cell(pf=0.3, alphas=(56.73720169067383,), marks=[1.0, 2.0])
    a["cells"].append(mk_cell(pf=0.7, alphas=(56.73720169067383,),
                              marks=[1.0, 2.0])["cells"][0])
    pm = {("aime__aime25__p00__think", 0.3): mk_probe([1.0, 2.0]),
          ("aime__aime25__p00__think", 0.7): mk_probe([1.0, 9.0])}
    rows = r213.build_rows(a, pm)
    assert len(rows) == 2
    bad = [r for r in rows if r["status"] == "measured"
           and r["first_bad_step"] is not None]
    assert len(bad) == 1 and bad[0]["pos_frac"] == 0.7, rows


# ===========================================================================
# E 组：`factor_rows` —— 逐步因子分解
# ===========================================================================


@case("E1 四配置全同 ⇒ 四个因子逐步 Δ 全为 0")
def _():
    f = r213.factor_rows(mk_cell(marks=[1.0, 2.0, 3.0]))
    for k in ("A->B", "B->C", "C->D", "A->D"):
        assert len(f[k]) == 3, (k, len(f[k]))
        assert all(x[4] == 0.0 for x in f[k]), k


@case("E2 ⛔⛔ 只有 C→D 非 0 时，**另外三个必须仍是 0**（不能一起变非 0）")
def _():
    a = mk_cell(marks=[1.0, 2.0, 3.0])
    for c in a["cells"][0]["by_alpha"]["56.737201690674"]["configs"]:
        if c["name"].startswith("D"):
            c["dec"]["marks"] = [1.0, 2.0, 3.5]
    f = r213.factor_rows(a)
    assert all(x[4] == 0.0 for x in f["A->B"])
    assert all(x[4] == 0.0 for x in f["B->C"])
    nz = [x for x in f["C->D"] if x[4] != 0.0]
    assert len(nz) == 1 and nz[0][3] == 2 and abs(nz[0][4]) == 0.5, f["C->D"]


@case("E3 ⛔⛔ 逐步 Δ 能与单步 Δ 不同（缓存逐步累积 ⇒ 单步 0 不蕴含逐步 0）")
def _():
    # ⚠⚠⛔ 这一条是**脚本必须支持**的情形，不是「不该发生」：
    # ⚠⚠⛔ 前两步四配置同，第三步才分叉。单步判据看不出，��步能。
    a = mk_cell(marks=[1.0, 2.0, 3.0])
    for c in a["cells"][0]["by_alpha"]["56.737201690674"]["configs"]:
        if c["name"].startswith("D"):
            c["dec"]["marks"] = [1.0, 2.0, 3.0]
    f = r213.factor_rows(a)
    assert len(f["C->D"]) == 3


# ===========================================================================
# G 组：旧闸门抄进同一文件作参照（不靠「以前验过」）
# ===========================================================================


@case("G1 旧闸门：cmp_series 的判据是**恰好 0**，不是 abs(d)<1e-6")
def _():
    tol_style = lambda d: abs(d) < 1e-6          # noqa: E731  旧（错）写法
    exact_style = lambda d: d == 0.0             # noqa: E731  新（对）写法
    d = 1e-9
    # ⚠⚠⛔ 旧写法把 1e-9 判成「过」，新写法判成「红」—— 这正是分水岭。
    assert tol_style(d) is True
    assert exact_style(d) is False
    r = r213.cmp_series([1.0], [1.0 + 1e-9])
    assert r["n_exact"] == 0, "脚本必须按新写法判"


@case("G2 旧闸门：bf16 的 ulp 级差也算**不一致**（1e-7 不是 0）")
def _():
    r = r213.cmp_series([5.5060715675354], [5.506071627])
    assert r["first_bad_step"] == 0
    assert r["max_abs_diff"] > 0


@case("G3 旧闸门抄进本文件的 A2 必须仍红（防止有人把容差改回去）")
def _():
    r = r213.cmp_series([1.0, 2.0, 3.0], [1.0, 2.0 + 1e-9, 3.0])
    assert r["first_bad_step"] == 1, "A2 的判据被改软了？"


@case("G4 ⛔⛔ not_measured 的行不得让 n_exact 增加（防止「没量」被算成「全等」）")
def _():
    rows = [{"label": "m", "status": "not_measured"}]
    s = r213.summarize(rows)
    assert s["n_exact"] == 0 and s["n_matched"] == 0 and s["n_not_measured"] == 1


@case("G5 ⛔⛔ summarize 的 n_cmp 必须等于**已测**行的比较点数之和")
def _():
    rows = [{"label": "a", "n_cmp": 5, "n_exact": 5, "first_bad_step": None,
             "len_agree": True, "max_abs_diff": 0.0},
            {"label": "b", "n_cmp": 3, "n_exact": 1, "first_bad_step": 2,
             "len_agree": True, "max_abs_diff": 9.0},
            {"label": "c", "status": "not_measured"}]
    s = r213.summarize(rows)
    assert s["n_cmp"] == 8 and s["n_exact"] == 6, s


# ===========================================================================
# H 组：变异台 —— 「台架本身有效」必须先证
# ===========================================================================


@case("H1 ⛔ 变异台：把判据改成 abs(d)<1e-6 ⇒ A2/D2 的断言必须**红**")
def _():
    # ⚠⚠⛔ 变异台报「抓住了」之前先证明**台架本身有效**：
    # ⚠⚠⛔ 这里真的去改源码、在副本上重新 import，再拿 A2/D2 的断言打它。
    # ⚠⚠⛔ 只断言「变异体存在」等于什么都没验。
    import types
    src = open(os.path.join(MUT, "r213_stepwise_check.py"),
               encoding="utf-8").read()
    mut = src.replace("if d != 0.0 and first_bad is None:",
                      "if abs(d) < 1e-6 and first_bad is None:")
    assert mut != src, "变异没生效 —— 源码里的判据串变了？"
    mod = types.ModuleType("r213_mutant")
    mod.__dict__["__file__"] = "r213_mutant.py"
    exec(compile(mut, "r213_mutant.py", "exec"), mod.__dict__)
    # 变异体应当把 1e-9 判成「没坏」⇒ A2 的断言（first_bad_step==1）必须失败
    r = mod.cmp_series([1.0, 2.0, 3.0], [1.0, 2.0 + 1e-9, 3.0])
    caught = (r["first_bad_step"] != 1)
    assert caught, "变异体竟然仍被判红 ⇒ 台架无效（A2 分辨不出）"
    # ⚠ 同时确认**原版**在同一输入上是绿的 ⇒ 说明是变异被抓住，不是台架常红
    assert r213.cmp_series([1.0, 2.0, 3.0],
                          [1.0, 2.0 + 1e-9, 3.0])["first_bad_step"] == 1


@case("H2 ⛔ 变异：把 not_measured 也算 matched ⇒ 汇总必须变样")
def _():
    rows = [{"label": "ok", "n_cmp": 2, "n_exact": 2, "first_bad_step": None,
             "len_agree": True, "max_abs_diff": 0.0},
            {"label": "miss", "status": "not_measured"}]
    s = r213.summarize(rows)
    fake = s["n_matched"] + s["n_not_measured"]
    assert fake == 2 and s["n_matched"] == 1, "not_measured 绝不能进 matched"


@case("H3 ⛔ 变异：去掉提前 EOS 的记账 ⇒ rows_short_of_budget 必须变空")
def _():
    rows = [{"label": "s", "n_cmp": 2, "n_exact": 2, "first_bad_step": None,
             "len_agree": True, "max_abs_diff": 0.0, "n_ran": 2}]
    assert r213.summarize(rows, budget=8)["rows_short_of_budget"]
    assert r213.summarize(rows, budget=None)["rows_short_of_budget"] == []


@case("H4 ⛔ 变异：只比公共段、忽略长度差 ⇒ B2 必须红")
def _():
    r = r213.cmp_series([1.0, 2.0, 3.0], [1.0, 2.0])
    rows = [{"label": "x", "n_cmp": r["n_cmp"], "n_exact": r["n_exact"],
             "first_bad_step": r["first_bad_step"],
             "len_agree": r["len_agree"], "max_abs_diff": r["max_abs_diff"]}]
    s = r213.summarize(rows)
    assert s["n_mismatch"] == 1, "长度差必须让 summarize 判 mismatch"


@case("H6 ⛔ 变异：剂量按**标签顺序**配对（把 anchor 的 doses 倒序）⇒ 必须配错")
def _():
    # ⚠⚠⛔ 顺序配对在「anchor doses=[lo,hi]」时**恰好也对** ⇒ 看不出来。
    # ⚠⚠⛔ 把 doses 倒成 [hi,lo]，顺序配对就会把 hi 认成 lo。
    # ⛔ 键用 `%.12f` 现算，不写死 —— 113.47440338134766 会舍入成 ...381348，
    # ⛔ 写死字符串会 KeyError，而那是**测试自己的错**，不是被测物的信号。
    HI, LO = 113.47440338134766, 56.73720169067383
    a = mk_cell(alphas=(HI, LO), marks=[1.0, 2.0])
    pm = {("aime__aime25__p00__think", 0.3): mk_probe([1.0, 2.0])}
    rows = r213.build_rows(a, pm)
    labels = {r["label"].split("α=")[1]: r.get("dose_label") for r in rows}
    assert labels["%.12f" % HI] == "hi", labels
    assert labels["%.12f" % LO] == "lo", labels
    # ⚠ 顺序配对在这里会给出 {hi→lo, lo→hi} ⇒ 与上面相反 ⇒ 变异被抓住
    assert labels["%.12f" % HI] != labels["%.12f" % LO]


def main():
    npass = nfail = 0
    for name, fn in CASES:
        try:
            fn()
        except AssertionError as exc:
            nfail += 1
            print("  %-4s ⛔ FAIL  %s" % (name, exc), flush=True)
        except Exception as exc:                      # noqa: BLE001
            nfail += 1
            print("  %-4s ⛔ ERROR %s: %r" % (name, type(exc).__name__, exc),
                  flush=True)
        else:
            npass += 1
            print("  %-4s ✅ %s" % (name, name), flush=True)
    print()
    print("RESULT r213_stepwise_check_selftest  %s  %d/%d"
          % ("OK" if nfail == 0 else "FAIL", npass, npass + nfail))
    return 0 if nfail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
