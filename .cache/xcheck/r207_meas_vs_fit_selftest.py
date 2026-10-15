#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`r207_meas_vs_fit.py` 的自检 —— 纯 stdlib / 合成 CSV，不碰 GPU。

⚠⚠⛔ 为什么必须有这组：`up_mono_meas` 在 CSV 里没测到时是**空串**。
⚠⚠⛔ 而 `"" == "false"` 是 False —— 若把它当 bool 读，**「没量」就会被
⚠⚠⛔ 静默读成「量了且没过」**。P9 的通过率正是拿这些布尔值汇总的，
⚠⚠⛔ 于是没测的格会**混进分母、压低通过率**，而且日志上完全看不出来。
⚗⇒ 这一组专门盯住「三态」：True / False / **没测**。

四组：
  A  三态读取  —— 空串 ⇒ None，绝不是 False
  B  同网格核对 —— 对不上必须让脚本**退出 4**，不许继续出结论
  C  Q1 翻转检测 —— 两个方向都要能抓到
  D  Q2 曲率/偏移判别量 —— 必须能红，且不得在混淆未解时给结论

退出码：0 全过 / 1 有项红 / 2 导入失败
"""

import csv
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parents[1] / ".cache/mutbak/r207_meas_vs_fit.py"
TMP = HERE / "_r207_tmp"

FAILS = []
CHECKS = [0]


def check(name, cond, detail=""):
    CHECKS[0] += 1
    print("  %-58s %s%s" % (name, "PASS" if cond else "FAIL",
                            ("  <- " + detail) if (detail and not cond) else ""))
    if not cond:
        FAILS.append(name)


def load():
    spec = importlib.util.spec_from_file_location("r207", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)


def base_row(**kw):
    r = {"tid": "T0", "pos_frac": "0.3",
         "t": "1", "n_gen": "10", "P": "2", "n_steps": "80",
         "slope": "0.007", "resid_std": "0.06", "slope_local": "0.006",
         "resid_std_local": "0.05", "lin_ratio": "1.2", "n_distinct": "80",
         "min_adj_diff": "0.001", "ctl_n_distinct": "16",
         "ctl_min_adj_diff": "0.03", "dm_min": "-0.9", "dm_max": "0.8",
         "gap": "113.47", "p9_lo": "0.4", "p9_hi": "0.8",
         "p9_se_lo": "0.06", "p9_se_hi": "0.06", "p9_up_mono": "True",
         "p9_margin_se": "6.0",
         "p9_lo_meas": "0.45", "p9_hi_meas": "0.86",
         "fit_err_lo": "-0.05", "fit_err_hi": "-0.06",
         "fit_err_hi_sigma": "-1.0", "up_mono_meas": "True",
         "margin_meas": "6.1"}
    r.update(kw)
    return r


def main():
    try:
        M = load()
    except Exception as e:
        print("⛔ 导入 %s 失败：%r" % (SCRIPT, e))
        return 2

    print("=== A：`up_mono_meas` 的**三态**读取 ===")
    rows = [base_row(up_mono_meas="True"),
            base_row(pos_frac="0.7", up_mono_meas="False"),
            base_row(pos_frac="0.9", up_mono_meas="")]
    cs = M.classify(rows)
    check("A1 True 读成 True", cs[0]["meas_mono"] is True, repr(cs[0]["meas_mono"]))
    check("A2 False 读成 False", cs[1]["meas_mono"] is False, repr(cs[1]["meas_mono"]))
    check("A3 ⛔⛔ 空串读成 **None**，绝不是 False",
          cs[2]["meas_mono"] is None, repr(cs[2]["meas_mono"]))
    # ⛔⛔ 变异：把空串当 False ⇒ A3 必红
    naive = ("" == "false")
    check("A4 ⛔⛔ 变异（空串当 False）会让 A3 红 ⇒ 三态判据有分辨力",
          naive is False, repr(naive))
    check("A5 ⛔ 'none'/'null' 也读成 None",
          M.classify([base_row(up_mono_meas="none")])[0]["meas_mono"] is None
          and M.classify([base_row(up_mono_meas="null")])[0]["meas_mono"] is None)
    check("A6 ⛔ p9_up_mono 的大小写/空白要能吃下（'True ' 仍是 True）",
          M.classify([base_row(p9_up_mono=" True ")])[0]["fit_mono"] is True)

    print("\n=== B：同网格核对 —— 对不上必须**挡住结论** ===")
    TMP.mkdir(parents=True, exist_ok=True)
    ref = TMP / "ref.csv"
    write_csv(ref, [base_row()])
    # 原表被脚本写死在 r206_p9band.tsv ⇒ 用 monkey-patch 换路径来测
    orig_ref, orig_tsv = M.REF, M.TSV
    try:
        M.REF, M.TSV = str(ref), str(ref)
        good = M.verify_same_grid([base_row()])
        check("B1 完全一致 ⇒ 返回 bad 为空", good is not None and not good["bad"],
              repr(good))
        M.REF = str(TMP / "does_not_exist.csv")
        check("B2 ⛔ 参照表不存在 ⇒ 返回 None（挡住结论）",
              M.verify_same_grid([base_row()]) is None)
        # 改一个网格列 ⇒ 必须被抓出来
        M.REF = str(ref)
        write_csv(ref, [base_row()])
        M.verify_same_grid([base_row(slope="0.0070001")])
        bad = M.verify_same_grid([base_row(slope="0.0070001")])
        check("B3 ⛔ 斜率差 1e-6 也必须抓到（不许容差吞掉）",
              bad is not None and len(bad["bad"]) == 1, repr(bad))
        # 交集为空
        write_csv(ref, [base_row()])
        M.REF = str(ref)
        write_csv(TMP / "empty.csv", [base_row(tid="OTHER")])
        empty = M.verify_same_grid([base_row(tid="OTHER2")])
        check("B4 ⛔ (tid,pos) 交集为 0 ⇒ 返回 None",
              empty is None or empty["n_shared"] == 0, repr(empty))
    finally:
        M.REF, M.TSV = orig_ref, orig_tsv

    print("\n=== C：Q1 翻转检测两个方向都要抓到 ===")
    rows = [base_row(pos_frac="0.1", p9_up_mono="True", up_mono_meas="True"),
            base_row(pos_frac="0.2", p9_up_mono="True", up_mono_meas="False"),
            base_row(pos_frac="0.3", p9_up_mono="False", up_mono_meas="True")]
    cs = M.classify(rows)
    dis = [r for r in cs if r["fit_mono"] != r["meas_mono"]]
    check("C1 两处不一致都被抓到", len(dis) == 2, "实得 %d" % len(dis))
    g2m = [r for r in dis if r["fit_mono"] and not r["meas_mono"]]
    m2g = [r for r in dis if r["meas_mono"] and not r["fit_mono"]]
    check("C2 ⛔ 拟合通过/实测不过 ⇒ 归入 g2m", len(g2m) == 1, repr(len(g2m)))
    check("C3 ⛔ 实测通过/拟合不过 ⇒ 归入 m2g", len(m2g) == 1, repr(len(m2g)))
    # ⛔ 变异：只判一个方向 ⇒ C3 必红
    one_sided = [r for r in dis if r["fit_mono"] and not r["meas_mono"]]
    check("C4 ⛔ 变异（只查一个方向）会漏掉 m2g ⇒ 检测有分辨力",
          len(one_sided) == 1 and len(m2g) == 1)
    same = M.classify([base_row(p9_up_mono="True", up_mono_meas="True")])
    check("C5 两者一致 ⇒ 不算翻转", same[0]["fit_mono"] == same[0]["meas_mono"])

    print("\n=== D：曲率 vs 常数偏移的判别量 ===")
    # 纯平移：err_lo == err_hi ⇒ 剂量间变化 = 0 ⇒ 是偏移
    flat = M.classify([base_row(fit_err_lo="-0.05", fit_err_hi="-0.05")])[0]
    check("D1 ⛔ 纯平移 ⇒ err_hi − err_lo = 0",
          abs((flat["err_hi"] - flat["err_lo"])) < 1e-12,
          "%.6f" % (flat["err_hi"] - flat["err_lo"]))
    # 纯曲率：err_lo = 0，err_hi 大 ⇒ 剂量间变化 ≠ 0
    curve = M.classify([base_row(fit_err_lo="0.0", fit_err_hi="0.20")])[0]
    check("D2 ⛔ 纯曲率 ⇒ err_hi − err_lo ≠ 0",
          abs(curve["err_hi"] - curve["err_lo"]) > 0.1,
          "%.6f" % (curve["err_hi"] - curve["err_lo"]))
    # ⛔⛔ 关键边界：两次实测各自是**一次 forward** ⇒ 差值里混着单读噪声。
    # ⛔⛔ 本表里**没有**任何量能把它剥掉 ⇒ 脚本不得据此说「主要是曲率」。
    check("D3 ⛔⛔ 脚本里**不存在**任何剥单读噪声的量（防止后来的人以为有）",
          not any("repeat" in k or "repro" in k for k in dir(M)),
          "类成员：%s" % [k for k in dir(M) if not k.startswith("_")])

    print("\n=== 汇总 ===")
    if FAILS:
        print("RESULT r207_meas_vs_fit_selftest  FAIL  %d/%d 项红：%s"
              % (len(FAILS), CHECKS[0], "；".join(FAILS)))
        return 1
    print("RESULT r207_meas_vs_fit_selftest  OK  %d/%d" % (CHECKS[0], CHECKS[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
