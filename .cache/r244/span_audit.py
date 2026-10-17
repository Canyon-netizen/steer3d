#!/usr/bin/env python
"""Separating "monotone = False" from "monotone = not measurable" (revision 244.23).

The instrument reports up_mono_meas (did the dose response increase from the
k_hi rung to the full-injection rung).  A False there is currently read as
"monotonicity failed".  But there is a second, very different way to get
False: if the injected direction barely moves the marker logit between the two
rungs, the comparison is between two nearly identical numbers, and the test is
measuring noise rather than monotonicity.

⚠ That distinction decides whether "w beats rand on up_mono_meas" means
anything.  If rand's failures are mostly "the dose had no measurable effect",
then the statistic is reporting the absence of an effect, not a failure of
monotonicity, and the cross-arm verdict would be built on that.

Evidence used here, per trajectory:
  span      marker_raw_hi - marker_raw_lo  (the dose span actually realised)
  margin    margin_meas                    (the reader's own margin field)
  zero      span is exactly 0              -> the two rungs are the same number
  and how many of each arm's 137 cells fall in each bucket.

⚠ This script does NOT say which arm is better.  It says how much of each
arm's signal is measurable at all, and flags trajectories whose up_mono_meas
verdict rests on an unmeasurable span.

Exit: 0 report printed; 2 precondition failure.
"""
import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
READER = os.path.join(os.path.dirname(HERE), "mutbak", "r227_kcurve.py")

EXACT_ZERO_EPS = 0.0   # span == 0 means the two rungs are bit-identical


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_cells(path):
    R = _load("r227_kcurve", READER)
    spath = path.replace(".log", "_status.txt")
    if not os.path.isfile(spath):
        raise SystemExit("PRECOND_FAIL: 找不到 %s 的 status" % path)
    log = open(path, encoding="utf-8", errors="replace").read()
    sttxt = open(spath, encoding="utf-8", errors="replace").read()
    cells = R.join(R.parse_blocks(log), R.parse_status(sttxt)[0])
    return R, cells


def readout_objs(path):
    out = []
    for line in open(path, encoding="utf-8", errors="replace"):
        if '"p9_lo_meas"' in line:
            out.append(json.loads(line[line.index("{"):]))
    return out


def main(argv):
    if len(argv) < 3:
        raise SystemExit("用法: span_audit.py <logA> <labelA> <logB> <labelB>")
    a, la = argv[0], argv[1]
    b, lb = argv[2], argv[3]
    spec = [
        ("tid", "inject_scope", "inject_n_sites", "marker_raw_lo",
         "marker_raw_hi", "margin_meas", "p9_lo_meas", "p9_hi_meas",
         "up_mono_meas"),
    ]
    print("=" * 78)
    print("剂量跨度审计：「单调性失败」vs「剂量量不到」")
    print("=" * 78)

    per_arm = {}
    for path, label in ((a, la), (b, lb)):
        objs = readout_objs(path)
        # only k-scope rungs have a dose pair
        ksc = [o for o in objs if o.get("inject_scope") == "k"]
        spans = [o["marker_raw_hi"] - o["marker_raw_lo"] for o in ksc
                 if o.get("marker_raw_lo") is not None
                 and o.get("marker_raw_hi") is not None]
        n_zero = sum(1 for s in spans if s == EXACT_ZERO_EPS)
        margins = [o["margin_meas"] for o in objs
                   if o.get("margin_meas") is not None]
        n_mzero = sum(1 for m in margins if m == 0)
        kspans = [spans[i] for i, o in enumerate(ksc)
                  if i < len(spans)]
        neg = sum(1 for s in spans if s < 0)
        print("\n【%s】%s" % (label, os.path.basename(path)))
        print("  k 档 %d 个：剂量跨度(hi−lo) 最小 %.6g / 中位 %.6g / 最大 %.6g"
              % (len(spans), min(spans), sorted(spans)[len(spans) // 2],
                 max(spans)))
        print("  ⛔ 跨度**恰好为 0**（lo 与 hi 是同一个数）：%d 个 k 档" % n_zero)
        print("  ⚠ 跨度为负：%d 个" % neg)
        print("  margin_meas 恰为 0：%d / %d 格" % (n_mzero, len(margins)))
        per_arm[label] = {"ksc": ksc, "spans": kspans, "objs": objs}

    # ---- per trajectory: does up_mono_meas rest on a zero span? ----------
    # ⚠⚠ `an["per"][tid]` holds TRAJECTORY aggregates; the per-cell fields
    # ⚖ (marker_raw_lo/hi, margin_meas) live on the cell's reading dict.
    # ⚖ Reading them off `per` returns None for everything, which would have
    # ⚖ printed "未量到" for every row -- a silently useless table.
    print("\n" + "-" * 78)
    print("逐轨迹：k_hi 与 all 两档的实测跨度、以及 up_mono_meas 的归属")
    for path, label in ((a, la), (b, lb)):
        R, cells = read_cells(path)
        an = R.analyze(cells)
        # index readings by (tid, scope); up_mono_meas is PER CELL, not per
        # trajectory -- reading it off `per` gives None for every row.
        idx, mono = {}, {}
        for c in cells:
            rd = c.get("reading") or {}
            idx[(c["tid"], rd.get("inject_scope"))] = rd
            if rd.get("inject_scope") == "k" and "up_mono_meas" in rd:
                mono.setdefault(c["tid"], []).append(bool(rd["up_mono_meas"]))
        print("\n  【%s】" % label)
        print("    %-30s %9s %9s %6s %6s  %-9s %s"
              % ("tid", "k_hi跨度", "all:mk_lo", "T", "F", "多数为真", "判定依据"))
        for t in an["tids"]:
            per = an["per"][t]
            j = per.get("jitter")
            d = per.get("drift_khi_all")
            flags = mono.get(t, [])
            nT, nF = sum(1 for v in flags if v), sum(1 for v in flags if not v)
            maj = None if not flags else (nT > nF)
            rk = idx.get((t, "k"))
            ra = idx.get((t, "all"))
            span = mg = lo = None
            if rk is not None and ra is not None:
                lo = rk.get("marker_raw_lo")
                hi = rk.get("marker_raw_hi")
                if lo is not None and hi is not None:
                    span = hi - lo
                mg = ra.get("margin_meas")
            if span is None:
                basis = "未量到"
            elif span == 0.0:
                basis = "⛔ 跨度=0 ⇒ 单调性**量不到**"
            elif span < 0:
                basis = "⛔ 跨度<0 ⇒ 剂量把 marker **压下去**"
            elif mg is not None and mg == 0:
                basis = "⛔ margin=0 ⇒ 量不到"
            elif d is not None and j is not None and abs(d) < j:
                basis = "⚠ |Δ| < 地板 ⇒ 噪声主导"
            else:
                basis = "可分辨"
            print("    %-30s %9s %9s %6d %6d  %-9s %s"
                  % (t,
                     "%.4g" % span if span is not None else "—",
                     "%.4g" % lo if lo is not None else "—",
                     nT, nF, str(maj), basis))

    print("\n" + "-" * 78)
    print("⚖ 「跨度=0 / margin=0」的格，其 up_mono_meas **不可**读成「单调性失败」：")
    print("  那是剂量效应本身为 0，两个档是同一个数，比较无从发生。")
    print("⚖ 本脚本不判断哪一臂更好；它只报每一臂有多少信号**根本没有被量到**。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
