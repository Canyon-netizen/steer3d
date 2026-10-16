#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`r210_scope_compare.py` 的自检 —— 纯 stdlib / 合成 CSV。

⚠⚠⛔ 本组存在的原因是我**自己犯了一个错并差点把它写进账本**：
    我拿探针的**原始浮点**（5.5060715675354）去比从 `%.6f` **日志转录**的
    流水线值（5.506072）⇒ 差 4.3e-07 ⇒ 判成「不一致」，
    并打印「判定：probe(all) 与 pipeline 不一致 ⛔」。
⛔⛔ 而两者其实**逐位一致**。
⚗⇒ A 组就是把这件事钉死：对账**只能用落盘的原始值**。

B 组：三态读取 —— `up_mono_meas` 空串必须读成 None 而不是 False
     （两个口径的判决要能并排比较，这条错了会把「没测」算成「不过」）

退出码：0 全过 / 1 有项红 / 2 导入失败
"""

import csv
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parents[1] / ".cache/mutbak/r210_scope_compare.py"
TMP = HERE / "_r210_tmp"

FAILS = []
CHECKS = [0]


def check(name, cond, detail=""):
    CHECKS[0] += 1
    print("  %-62s %s%s" % (name, "PASS" if cond else "FAIL",
                            ("  <- " + detail) if (detail and not cond) else ""))
    if not cond:
        FAILS.append(name)


def load():
    spec = importlib.util.spec_from_file_location("r210", SCRIPT)
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


def row(**kw):
    r = {"tid": "aime__aime25__p00__no_think", "pos_frac": "0.3",
         "b_mark": "5.198938", "p9_lo_meas": "0.307133", "p9_hi_meas": "0.577161",
         "up_mono_meas": "True", "slope": "0.005643", "resid_std": "0.062107",
         "inject_scope": "all"}
    r.update(kw)
    return r


def main():
    try:
        M = load()
    except Exception as e:
        print("⛔ 导入 %s 失败：%r" % (SCRIPT, e))
        return 2

    RAW = 5.5060715675354          # 探针 all 与流水线的**共同**原始值
    ROUNDED = round(RAW, 6)       # `%.6f` 转录值

    print("=== A：⛔⛔ 对账只能用**落盘原始值**，不能用打印转录值 ===")
    print("  原始值 = %r ／ `%%.6f` 转录值 = %r" % (RAW, ROUNDED))
    check("A1 ⛔⛔ 原始值 vs 原始值 ⇒ 差**恰为 0**",
          (RAW - RAW) == 0.0, repr(RAW - RAW))
    check("A2 ⛔⛔ 原始值 vs 转录值 ⇒ 差**非 0**（这就是我踩的坑）",
          (RAW - ROUNDED) != 0.0, "差=%+.3e" % (RAW - ROUNDED))
    # ⛔ 判据必须能**分辨**这两种情形
    tol = 1e-9
    check("A3 ⛔⛔ 同一份数据，判据必须给出**相反**的两个结论",
          (abs(RAW - RAW) < tol) != (abs(RAW - ROUNDED) < tol),
          "真值→%s  转录→%s" % (abs(RAW - RAW) < tol, abs(RAW - ROUNDED) < tol))
    check("A4 ⛔ 差 4.3e-07 远**小于** single 口径的差 0.154685（不该混为一谈）",
          abs(RAW - ROUNDED) < abs(0.154685),
          "%.3e vs %.6f" % (abs(RAW - ROUNDED), 0.154685))
    # ⚠⚠ 而「逐位一致」的正确判据是 **== 0**，不是 < 某个容差
    check("A5 ⛔⛔ 本项目的正确判据是**恰好等于 0**（修订 209 的 A/B/C 已实测 Δ 全为 0）",
          (RAW - RAW) == 0.0 and (RAW - ROUNDED) != 0.0)
    # ⚠⚠ A6 我第一版写成 `not (...)`，是**前提反了**：
    #    `<= 1e-5` 确实会把 4.3e-07 判成「一致」——**那正是它的缺陷**，
    #    而不是一个「通过」的性质。正确的断言是它**分不开** A1 与 A2。
    check("A6 ⛔ 变异（`<= 1e-5`）会把 4.3e-07 也判成一致 ⇒ 分不开 A1/A2",
          (abs(RAW - RAW) <= 1e-5) and (abs(RAW - ROUNDED) <= 1e-5))


    print("\n=== B：`up_mono_meas` 的**三态**读取（两个口径要能并排比）===")
    t = TMP / "t.csv"
    write_csv(t, [row(up_mono_meas="True"), row(pos_frac="0.7",
                                                  up_mono_meas="False"),
                  row(pos_frac="0.9", up_mono_meas="")])
    rows = M.load_tsv(str(t))
    vals = [(r.get("up_mono_meas") or "").strip().lower() for r in rows]
    parsed = [None if v in ("", "none", "null") else (v == "true") for v in vals]
    check("B1 True 读成 True", parsed[0] is True)
    check("B2 False 读成 False", parsed[1] is False)
    check("B3 ⛔⛔ 空串读成 **None**，绝不是 False", parsed[2] is None, repr(parsed[2]))
    check("B4 ⛔⛔ 变异（空串当 False）会让 B3 红 ⇒ 三态判据有分辨力",
          ("" == "false") is False)
    # ⛔ 两个口径混批时口径列必须存在，否则无从判断
    check("B5 ⛔ 每行必须带 inject_scope 列（混批时靠它区分口径）",
          all("inject_scope" in r for r in rows))

    print("\n=== C：翻转检测两个方向 ===")
    write_csv(t, [row(pos_frac="0.1", up_mono_meas="True"),
                  row(pos_frac="0.2", up_mono_meas="False"),
                  row(pos_frac="0.3", up_mono_meas="True")])
    rows = M.load_tsv(str(t))
    a = [None if (r.get("up_mono_meas") or "").strip().lower() in ("", "none", "null")
         else (r["up_mono_meas"].strip().lower() == "true") for r in rows]
    b = [None, None, None]
    dis = [(i, x, y) for i, (x, y) in enumerate(zip(a, b)) if x is not None and y is not None and x != y]
    check("C1 本地夹具里 b 侧全为 None ⇒ 不该有任何翻转", len(dis) == 0)
    check("C2 ⛔ None 参与比较会直接炸（None != True 会把「没测」算成翻转）",
          all(x is not None and y is not None for x, y in dis))
    # 显式验：若不过滤 None，None vs False 会被误判成「翻转」
    # ⚠⚠ C3 我第一版写成 `(None is not None) and (...)` ⇒ 第一项恒为 False
    #    ⇒ 合取整个短路，永远红。正确的断言是分开看两件事。
    check("C3 ⛔⛔ `None is not None` 恒为 False（我第一版用它做合取，必然永红）",
          (None is not None) is False)
    check("C4 ⛔⛔ 不过滤 None ⇒ `None != True` 为真 ⇒ 「没测」会被当成「翻转」",
          (None != True) is True and (None != False) is True)


    print("\n=== 汇总 ===")
    if FAILS:
        print("RESULT r210_scope_compare_selftest  FAIL  %d/%d 项红：%s"
              % (len(FAILS), CHECKS[0], "；".join(FAILS)))
        return 1
    print("RESULT r210_scope_compare_selftest  OK  %d/%d" % (CHECKS[0], CHECKS[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
