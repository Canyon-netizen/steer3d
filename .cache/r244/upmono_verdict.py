#!/usr/bin/env python
"""The pre-registered primary statistic from revision 244.14, in code.

Frozen BEFORE the new 274-cell run produces data.  Writing the statistic down
in prose is a promise; freezing the code that computes it is the promise being
enforceable.  If this file changes after the new data lands, git history shows
it, and that is the point.

The pre-registration (ledger 244.14.5):
  PRIMARY  trajectory-level `up_mono_meas` "majority true" rate, compared
           across arms with Fisher exact two-sided.  n = 14 per arm.
  SECOND   cell-level same quantity.  MUST be co-reported, and MUST be
           labelled anti-conservative: 137 cells come from only 14 distinct
           tids (9-11 cells each), so treating them as independent inflates
           significance.  Measured inflation on old data: ~30x.
  THIRD    `fit_err_hi_sigma` distribution per arm, reported separately from
           monotonicity -- it measures prediction quality, not dose response.
  ALSO     failure counts at both levels, and the p value.  Never the p alone.

Why `up_mono_meas` and not the k-curve sign flip: it is the SPEC's own
per-cell criterion (w+@1.0 >= w+@0.5, judged on measured readings), so it needs
no derivation and no fitted line.  The k-curve comparison is a dose-ladder
statistic and remains the 244 verdict; this is a separate, pre-registered one.

Division of labour: block/status parsing and the per-cell reading dict come
from r227_kcurve (imported, never re-implemented -- two parsers are two truths).

Exit: 0 printed; 2 precondition/contract failure (no statistic).
"""
import argparse
import importlib.util
import json
import os
import statistics
import sys
from math import comb


def load_reader(path):
    if not os.path.isfile(path):
        raise SystemExit("PRECOND_FAIL: reader not found: %s" % path)
    spec = importlib.util.spec_from_file_location("r227_kcurve", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fisher_two_sided(a, b, c, d):
    n = a + b + c + d
    if n == 0:
        return None
    r1, r2, c1 = a + b, c + d, a + c
    lo = max(0, c1 - r2)
    hi = min(r1, c1)
    probs = lambda x: (comb(r1, x) * comb(r2, c1 - x)) / float(comb(n, c1))
    p_obs = probs(a)
    p = sum(probs(x) for x in range(lo, hi + 1) if probs(x) <= p_obs * (1 + 1e-12))
    return min(1.0, p)


def read_arm(rc, log, status, expect_cells, label):
    with open(log, encoding="utf-8", errors="replace") as fh:
        log_text = fh.read()
    with open(status, encoding="utf-8", errors="replace") as fh:
        st_text = fh.read()
    blocks = rc.parse_blocks(log_text)
    rows, alldone = rc.parse_status(st_text)
    if alldone is None:
        raise SystemExit("PRECOND_FAIL: %s 无 ALLDONE ⇒ 该轮可能没跑完" % status)
    if expect_cells is not None and len(blocks) != expect_cells:
        raise SystemExit("PRECOND_FAIL: %s 有 %d 块，期望 %d"
                         % (log, len(blocks), expect_cells))
    if len(blocks) != len(rows):
        raise SystemExit("PRECOND_FAIL: %s 块数 %d ≠ 状态行数 %d"
                         % (log, len(blocks), len(rows)))

    cells = []
    for i, (b, row) in enumerate(zip(blocks, rows), 1):
        if b["tid"] != row["tid"]:
            raise SystemExit("PRECOND_FAIL: %s 第 %d 格 tid %r ≠ 状态 %r"
                             % (log, i, b["tid"], row["tid"]))
        reading, err = rc._extract_reading(b["lines"])
        if reading is None:
            raise SystemExit("PRECOND_FAIL: %s 第 %d 格无读数（%s）"
                             % (log, i, err))
        if reading.get("arm") is None:
            raise SystemExit("PRECOND_FAIL: %s 第 %d 格臂名未量到" % (log, i))
        cells.append({"tid": b["tid"], "up": reading.get("up_mono_meas"),
                      "fit_sig": reading.get("fit_err_hi_sigma"),
                      "arm": reading.get("arm")})
    arms = sorted({c["arm"] for c in cells})
    if len(arms) != 1:
        raise SystemExit("PRECOND_FAIL: %s 臂名混了 %r" % (log, arms))
    n_alldone = sum(1 for ln in st_text.split("\n") if ln.strip().startswith("ALLDONE"))
    print("[%s] arm=%s  cells=%d  ALLDONE_last=%s" % (label, arms[0], len(cells),
                                                     alldone))
    # ⚠⚠ 修订 244.16.4：多轮并集的产物里 ALLDONE 有多个，每一个都不能描述整体。
    # ⛔ 印成「这一臂跑完了的时刻」会继承「拿某一轮的戳当整体」的错基准。
    if n_alldone > 1:
        print("     ⛔ ALLDONE_count=%d ⇒ 这是最后一轮的戳，不描述该臂的时间跨度"
              % n_alldone)
    return cells, arms[0]


def aggregate(cells):
    """-> (cell_true, cell_n, per-tid majority map, all_true map)"""
    known = [c for c in cells if c["up"] is not None]
    per = {}
    for c in cells:
        per.setdefault(c["tid"], []).append(bool(c["up"]))
    return per


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reader", required=True)
    ap.add_argument("--w-log", required=True)
    ap.add_argument("--w-status", required=True)
    ap.add_argument("--rand-log", required=True)
    ap.add_argument("--rand-status", required=True)
    ap.add_argument("--expect-cells", type=int, default=137)
    args = ap.parse_args()

    rc = load_reader(args.reader)
    w_cells, w_arm = read_arm(rc, args.w_log, args.w_status,
                              args.expect_cells, "w")
    r_cells, r_arm = read_arm(rc, args.rand_log, args.rand_status,
                              args.expect_cells, "rand")
    if w_arm == r_arm:
        raise SystemExit("PRECOND_FAIL: 两臂 --arm 相同（%r）⇒ 不是对照" % w_arm)

    print("")
    per_w = aggregate(w_cells)
    per_r = aggregate(r_cells)
    print("轨迹数：w=%d rand=%d" % (len(per_w), len(per_r)))

    w_cell_t = sum(1 for c in w_cells if c["up"])
    w_cell_f = sum(1 for c in w_cells if c["up"] is False)
    r_cell_t = sum(1 for c in r_cells if c["up"])
    r_cell_f = sum(1 for c in r_cells if c["up"] is False)

    w_maj = sum(1 for v in per_w.values() if sum(v) * 2 > len(v))
    r_maj = sum(1 for v in per_r.values() if sum(v) * 2 > len(v))
    w_all = sum(1 for v in per_w.values() if all(v))
    r_all = sum(1 for v in per_r.values() if all(v))

    print("")
    print("=== 第二量（必须同报）：格级 ===")
    print("  w    True=%d False=%d (未量到 %d)  率=%.4f"
          % (w_cell_t, w_cell_f, len(w_cells) - w_cell_t - w_cell_f,
             w_cell_t / max(1, w_cell_t + w_cell_f)))
    print("  rand True=%d False=%d (未量到 %d)  率=%.4f"
          % (r_cell_t, r_cell_f, len(r_cells) - r_cell_t - r_cell_f,
             r_cell_t / max(1, r_cell_t + r_cell_f)))
    p_cell = fisher_two_sided(w_cell_t, w_cell_f, r_cell_t, r_cell_f)
    print("  Fisher 双尾 p=%.6g   ⛔ 反保守：137 格只来自 %d 个 tid，"
          "格不独立" % (p_cell, len(per_w)))

    print("")
    print("=== 主统计量：轨迹级「多数为真」 ===")
    print("  w    %d/%d = %.4f    （全格为真 %d/%d）"
          % (w_maj, len(per_w), w_maj / max(1, len(per_w)),
             w_all, len(per_w)))
    print("  rand %d/%d = %.4f    （全格为真 %d/%d）"
          % (r_maj, len(per_r), r_maj / max(1, len(per_r)),
             r_all, len(per_r)))
    p_traj = fisher_two_sided(w_maj, len(per_w) - w_maj,
                              r_maj, len(per_r) - r_maj)
    diff = (w_maj / max(1, len(per_w)) - r_maj / max(1, len(per_r))) * 100
    print("  差 = %+.1f 个百分点" % diff)
    print("  Fisher 双尾 p=%.6g   （每臂 n=%d）" % (p_traj, len(per_w)))
    if p_cell and p_traj and p_cell > 0:
        # ⚠⚠ 方向：轨迹级 p 是格级 p 的多少倍。旧数据上 ≈30 倍。
        # ⚖ 印「格级比轨迹级小几倍」会用 %.0f 把 0.03 印成 0，读起来像「没差」。
        print("  ⛔ 轨迹级 p 是格级 p 的 %.1f 倍 ⇒ 那正是「把格当独立样本」的代价"
              % (p_traj / p_cell))

    print("")
    print("=== 第三量：拟合直线在工作剂量上的误差（预测质量，与单调性分开看） ===")
    for label, cells in (("w", w_cells), ("rand", r_cells)):
        sig = [c["fit_sig"] for c in cells
               if c["fit_sig"] is not None and c["fit_sig"] == c["fit_sig"]]
        if not sig:
            print("  %-4s 未量到" % label)
            continue
        print("  %-4s n=%d  中位=%+.3f  |中位|=%.3f  max|.|=%.3f"
              % (label, len(sig), statistics.median(sig),
                 statistics.median([abs(x) for x in sig]),
                 max(abs(x) for x in sig)))

    print("")
    print("=== 判决（只读上面三段，不要只读 p） ===")
    print("  轨迹级 p=%.6g  格级 p=%.6g（反保守）" % (p_traj, p_cell))
    print("  失败条数 格级 w=%d rand=%d ｜ 轨迹级 w=%d rand=%d"
          % (w_cell_f, r_cell_f, len(per_w) - w_maj, len(per_r) - r_maj))
    print("  ⚠ 本统计量只说「两臂的规格单调性通过率不同或不可分辨」。")
    print("  ⚠ 它不说明：剂量响应是对的 / 阶梯排对了 / 算力条件两臂可比。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
