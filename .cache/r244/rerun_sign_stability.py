#!/usr/bin/env python
"""Cross-round reproducibility of the dose-response SIGN (revision 244.22).

Division of labour, deliberately narrow:
  Every reading comes from r227_kcurve (imported, never reimplemented) and
  every sweep-param comparison comes from cross_round_params (imported).
  ⛔ Two parsers are two truths; this file adds no third.

Why this exists:
  The 244.14.5 pre-registered headline statistic (trajectory-level
  up_mono_meas, cross-arm Fisher) assumes each arm's readings are worth
  comparing.  That assumption has never been tested: no one has asked whether
  the SAME arm, re-run, gives the same signs.  If signs are not stable across
  reruns, then "w differs from rand" could be rerun-to-rerun churn, and the
  whole verdict rests on sand.  This is a precondition, not a nicety.

⚠⚠⁴ THE STATISTIC IS FIXED HERE, BEFORE ANY SIGN COMPARISON WAS LOOKED AT.
  ⛔ It may not be changed after seeing the data.  Frozen:
    PRIMARY  n_flip = trajectories whose dose drift (k_hi->all) has
              OPPOSITE sign in the two rounds.  Exact two-sided binomial
              under H0: P(flip) = 0.5, on the n trajectories that are
              non-zero in BOTH rounds.
    The count of same-sign trajectories is NOT the headline -- it is the
    complement of n_flip, and reporting it alone is the forbidden half.
  ⛔ Zero-drift trajectories are excluded from n and COUNTED OUT LOUD, never
     silently dropped (a dropped denominator is how a small n gets to look
     significant).

What must be reported alongside any sign verdict:
  - each round's own exact sign test, at trajectory AND problem level
  - each round's below-floor count (|drift| < same-curve jitter), because a
    sign you cannot resolve is not a sign you may cite
  - the trajectories that are below floor in BOTH rounds: their agreement is
    agreement about noise.  A secondary agreement rate restricted to the
    resolvable trajectories is printed next to the primary one.
  - per-trajectory deltas from both rounds and their difference, both rulers
    (max and med), per the standing rule that max is not comparable across
    different ladder lengths.

⚠⚠ What this cannot settle:
  - It does NOT establish that either round is correct.
  - Equal sweep params remove one confound only.  Model, w vector, data
    files and machine load are NOT checked here.
  - If the two rounds ran under different load, a sign flip is uninterpretable
    as reproducibility failure until compute_conditions.py has run.
  - n=14 is small: the exact binomial's lower bound is reported next to it,
    never the p alone.

Exit: 0 comparison printed; 2 precondition failure (no verdict);
     1 a real finding (at least one sign flipped) -- a finding, not an error.
"""
import argparse
import importlib.util
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, path):
    if not os.path.isfile(path):
        raise SystemExit("PRECOND_FAIL: %s not found: %s" % (name, path))
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def flip_test(n, f):
    """Exact two-sided binomial, H0 P(flip)=0.5.  Returns (p, lower_bound, z).

    ⛔ No normal approximation: at small n it reports p values SMALLER than
    the theoretical floor 2/2^n, i.e. a significance the design cannot reach.
    """
    if n == 0:
        return None, None, None
    k = min(f, n - f)
    obs = _comb(n, k)
    probs = [_comb(n, j) for j in range(n + 1)]
    p = sum(c for c in probs if c <= obs) / float(2 ** n)
    return p, 2.0 ** (1 - n), (n - 2 * f) / float(n) ** 0.5


def _comb(n, k):
    import math
    return math.comb(n, k)


def _sgn(x):
    if x is None:
        return None
    return (x > 0) - (x < 0)


def log_facts(path):
    """Independence facts about a log, read from the log itself.

    ⚠⚠⁴ "The two rounds are independent" is the ROOT of this whole check.
    ⚖ If they are not, a sign agreement is a tautology.  So it must be read
    ⚖ back from the artifacts, not assumed:
      md5        whole-file digest; two rounds with the SAME md5 are the same
                 file and the check is void
      gpu        the PINNED GPU UUID from the sweep header
      span       first/last BEGIN timestamps (the round's own clock span)
      nload      "Loading weights" progress lines == cells actually loaded
                 ⚠ if this is short, we cannot claim every cell was recomputed
    """
    import hashlib
    raw = open(path, "rb").read()
    text = raw.decode("utf-8", errors="replace")
    lines = text.split("\n")
    gpu = None
    for line in lines:
        if line.startswith("PINNED "):
            m = re.search(r"GPU=(\S+)", line)
            if m:
                gpu = m.group(1)
            break
    begin = [ln for ln in lines if ln.startswith("### BEGIN ")]
    bts = [re.search(r"(\d\d:\d\d:\d\d)\s*$", ln).group(1) for ln in begin
           if re.search(r"(\d\d:\d\d:\d\d)\s*$", ln)]
    # ⚠⚠ Count LINES, not substring occurrences.  transformers' progress bar
    # ⚖ redraws with \r, so one physical line holds TWO "Loading weights"
    # ⚖ fragments (0% then 100%).  text.count() therefore returns 2 per cell
    # ⚖ and this gate fired "nload 274 != nbegin 137" -- the GUARD WAS
    # ⚖ REPORTING MY OWN COUNTING BUG, not a data problem.  Read that shape
    # ⚖ of warning as "the criterion is wrong" before touching the data.
    nload_lines = sum(1 for ln in lines if "Loading weights" in ln)
    nload_done = sum(1 for ln in lines if "Loading weights: 100%" in ln)
    return {
        "md5": hashlib.md5(raw).hexdigest(),
        "gpu": gpu,
        "span": (bts[0], bts[-1]) if bts else (None, None),
        "nload": nload_lines,
        "nload_done": nload_done,
        "nbegin": len(begin),
    }


def reading_md5(path):
    """md5 over the instrument's readout lines, untouched (no normalisation).

    ⛔ Deliberately NOT stripping timestamps: the readout JSON lines carry no
    timestamp, so there is nothing to strip, and any normalisation step is a
    place where a real difference could be silently discarded.
    """
    import hashlib
    h = hashlib.md5()
    n = 0
    for line in open(path, encoding="utf-8", errors="replace"):
        if '"p9_lo_meas"' in line:
            h.update(line.encode("utf-8", "replace"))
            n += 1
    return h.hexdigest(), n


def read_round(R, log, status):
    blocks = R.parse_blocks(open(log, encoding="utf-8", errors="replace").read())
    rows, alldone = R.parse_status(open(status, encoding="utf-8",
                                       errors="replace").read())
    cells = R.join(blocks, rows)
    return R.analyze(cells), alldone, len(cells), len(rows)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--reader", default=os.path.join(os.path.dirname(HERE),
                                                      "mutbak", "r227_kcurve.py"))
    ap.add_argument("--xrp", default=os.path.join(HERE, "cross_round_params.py"))
    ap.add_argument("--a-label", required=True)
    ap.add_argument("--a-log", required=True)
    ap.add_argument("--a-status", required=True)
    ap.add_argument("--b-label", required=True)
    ap.add_argument("--b-log", required=True)
    ap.add_argument("--b-status", required=True)
    args = ap.parse_args(argv)

    R = _load("r227_kcurve", args.reader)
    X = _load("cross_round_params", args.xrp)

    # ---- 闸 0：比较的必须是同一臂的重跑，不是两臂 ---------------------
    ra, ald_a, na, _ = read_round(R, args.a_log, args.a_status)
    rb, ald_b, nb, _ = read_round(R, args.b_log, args.b_status)
    if ra["arm"] is None or rb["arm"] is None:
        raise SystemExit("PRECOND_FAIL: 至少一轮没读出 arm 名 ⇒ 未量到")
    if ra["arm"] != rb["arm"]:
        raise SystemExit("PRECOND_FAIL: 两轮 arm 不同（%r vs %r）—— 那是跨臂比较，"
                         "用 arm_verdict.py，不是本脚本" % (ra["arm"], rb["arm"]))

    # ---- 闸 1：扫描参数必须逐项相同（复用 cross_round_params 的解析）----
    pa = X.resolve(args.a_log, X.scan_params(args.a_log)[0])
    pb = X.resolve(args.b_log, X.scan_params(args.b_log)[0])
    diffs = [(k, pa[k], pb[k]) for k in X.SCAN_PARAMS if repr(pa[k]) != repr(pb[k])]
    if diffs:
        raise SystemExit("PRECOND_FAIL: 扫描参数不同 ⇒ 跨轮判决不可比：%s"
                         % "; ".join("%s %r≠%r" % d for d in diffs))

    # ---- 闸 2：轨迹集合必须完全对齐 -------------------------------------
    ta, tb = list(ra["tids"]), list(rb["tids"])
    if set(ta) != set(tb):
        raise SystemExit("PRECOND_FAIL: 轨迹集合不同：只在 A %s / 只在 B %s"
                         % (sorted(set(ta) - set(tb)), sorted(set(tb) - set(ta))))
    if ra["arm"] == "w" and rb["arm"] == "w" and len(ta) != 14:
        print("⚠ 轨迹数 %d ≠ 14" % len(ta))

    # ---- 闸 3：两轮必须是两次独立跑批（不是同一份文件）------------------
    fa = log_facts(args.a_log)
    fb = log_facts(args.b_log)
    if fa["md5"] == fb["md5"]:
        raise SystemExit("PRECOND_FAIL: 两份日志 md5 相同 ⇒ **同一份文件**，"
                         "「两轮一致」是恒等式，不读")
    # ⚖ 直接证据是「读数行数 == 格数」；`Loading weights: 100%` 只证明
    # ⚖ 模型被加载过，不证明前向跑完 —— 两样都报，不合并成一个数。
    md5_a, cnt_a = reading_md5(args.a_log)
    md5_b, cnt_b = reading_md5(args.b_log)
    readings_identical = (md5_a == md5_b) and cnt_a == cnt_b and cnt_a > 0
    for lab, f, cnt in ((args.a_label, fa, cnt_a), (args.b_label, fb, cnt_b)):
        if cnt != f["nbegin"]:
            print("⚠⚠ %s：BEGIN %d 格但读数行 %d 条 ⇒ **未量到**「每格都出读数」"
                  % (lab, f["nbegin"], cnt))
        if f["nload_done"] != f["nbegin"]:
            print("⚠⚠ %s：BEGIN %d 格但 `Loading weights: 100%%` %d 次 ⇒ "
                  "**未量到**「每格都加载到完成」"
                  % (lab, f["nbegin"], f["nload_done"]))

    # 逐轨迹 Δ 是否**逐位**相同（不是四舍五入后相同）
    exact_same = sum(
        1 for t in ta
        if ra["per"][t].get("drift_khi_all") is not None
        and rb["per"][t].get("drift_khi_all") is not None
        and ra["per"][t]["drift_khi_all"] == rb["per"][t]["drift_khi_all"])

    # ---- 主统计量：符号翻转（已冻结，见文件头）------------------------
    n_nonzero = n_flip = n_same = 0
    n_zero = n_missing = 0
    rows_out = []
    for t in ta:
        da = ra["per"][t].get("drift_khi_all")
        db = rb["per"][t].get("drift_khi_all")
        sa, sb = _sgn(da), _sgn(db)
        ja = ra["per"][t].get("jitter")
        jb = rb["per"][t].get("jitter")
        jma = ra["per"][t].get("jitter_med")
        jmb = rb["per"][t].get("jitter_med")
        below_a = None if (da is None or ja is None) else abs(da) < ja
        below_b = None if (db is None or jb is None) else abs(db) < jb
        if sa is None or sb is None:
            n_missing += 1
            rows_out.append((t, da, db, None, below_a, below_b, "未量到"))
            continue
        if sa == 0 or sb == 0:
            n_zero += 1
            rows_out.append((t, da, db, 0, below_a, below_b, "含零（已剔出 n）"))
            continue
        n_nonzero += 1
        flip = (sa != sb)
        if flip:
            n_flip += 1
        else:
            n_same += 1
        rows_out.append((t, da, db, -1 if flip else 1, below_a, below_b,
                         "符号相反" if flip else "同号"))

    p_flip, lb_flip, z_flip = flip_test(n_nonzero, n_flip)

    # ---- 可分辨性：两轮都低于地板的轨迹，「一致」只是一致在噪声里 -------
    both_below = [r for r in rows_out
                  if r[4] is True and r[5] is True]
    resolvable = [r for r in rows_out
                  if r[4] is False and r[5] is False and r[3] is not None]
    n_res = len(resolvable)
    n_res_same = sum(1 for r in resolvable if r[3] == 1)

    # ---- 报告 ---------------------------------------------------------
    print("=" * 78)
    print("同臂重跑的剂量符号可重现性（臂 = %s）" % ra["arm"])
    print("  A = %s   格 %d   ALLDONE %s" % (args.a_label, na, ald_a))
    print("  B = %s   格 %d   ALLDONE %s" % (args.b_label, nb, ald_b))
    print("=" * 78)
    print("\n【闸】两轮扫描参数逐项相同：%s"
          % ", ".join("%s=%r" % (k, pa[k]) for k in X.SCAN_PARAMS))
    print("  ⚠ 只消掉这一个混淆；模型 / w 向量 / 数据文件 / 机器负载本脚本**没查**。")

    print("\n【闸 3】两轮是两次独立跑批（不是同一份文件）")
    nread = {args.a_label: cnt_a, args.b_label: cnt_b}
    for lab, f in ((args.a_label, fa), (args.b_label, fb)):
        print("  %-6s md5=%s  GPU=%s  BEGIN %d 格 / 读数 %d 行 / 加载完成 %d 次"
              "  钟面 %s→%s"
              % (lab, f["md5"][:12], f["gpu"], f["nbegin"], nread[lab],
                 f["nload_done"], f["span"][0], f["span"][1]))
    # ⚖ All three branches print the SAME leading phrase on purpose, so that
    # ⚖ "where did these rounds run" has exactly one answer line to read and
    # ⚖ a bench can find the verdict without keyword-guessing the prose.
    if fa["gpu"] is None or fb["gpu"] is None:
        print("  ⚖ 两轮 GPU **未量到**（缺 PINNED 行）—— ⛔ 未量到 ≠ 同一张卡，"
              "也 ≠ 不同卡")
    elif fa["gpu"] == fb["gpu"]:
        print("  ⚖ 两轮 GPU **相同**（同一张卡跑两遍，仍算两次独立跑批）")
    else:
        print("  ⚖ 两轮 GPU **不同**（不同物理卡，同一型号）")

    print("\n【判别】读数本身是否**逐位**相同 —— 这一段决定上面那个 p 怎么解释")
    print("  读数行 md5  A=%s (%d 条)" % (md5_a[:12], cnt_a))
    print("  读数行 md5  B=%s (%d 条)" % (md5_b[:12], cnt_b))
    print("  逐轨迹 Δ 逐位相同：%d/%d" % (exact_same, len(ta)))
    if readings_identical and exact_same == len(ta):
        print("  ⚖⚖⚖ **全部读数逐位相同** ⇒ 这个测量在本仪器与本输入下是")
        print("     **确定性**的（无采样、无随机数聚合）。")
        print("  ⚠⚠⚠ **因此上面那个符号翻转 p 是恒绿的**：确定性测量下重跑必然同号，")
        print("     ⛔ 它**不构成**「稳健 / 可重现」的证据，只构成「确定」的证据。")
        print("     把它读成稳健性，是**用恒绿的检查给结论背书**。")
    elif n_flip == 0:
        print("  ✅ 读数**不是**逐位相同，但符号全部一致 ⇒ 这才是稳健性证据。")
    else:
        print("  ⛔ 既有符号翻转，读数是否逐位相同不影响结论：存在真实差异。")

    print("\n【主统计量（冻结）】符号翻转的精确二项，H0: P(翻转)=0.5")
    print("  纳入 n = %d（两轮都非零）" % n_nonzero)
    print("  符号相反 %d / 同号 %d" % (n_flip, n_same))
    print("  剔除并计数：含零 %d 条、未量到 %d 条（⛔ 不许缩小分母）"
          % (n_zero, n_missing))
    if p_flip is not None:
        print("  p = %.6g（精确双尾）   功效下界 2/2^n = %.6g" % (p_flip, lb_flip))
    print("  ⚖ 同号 %d/%d 是上式的补集，⛔ **不许只报这一半**。" % (n_same, n_nonzero))

    print("\n【必报 1】两轮各自的符号检验（读数器算的，不是本脚本）")
    for lab, r in ((args.a_label, ra), (args.b_label, rb)):
        t = r["traj"]
        p = r["prob"]
        print("  %-10s 轨迹级 正%d/负%d/零%d p=%.6g（下界 %.6g）"
              "  低于地板 %d/14" % (lab, t[1], t[2], t[3], t[0], t[4], r["n_below"]))
        print("  %-10s 问题级 正%d/负%d/零%d p=%.6g（下界 %.6g）"
              % ("", p[1], p[2], p[3], p[0], p[4]))

    print("\n【必报 2】两轮都低于地板的 %d 条 ⇒ 它们的「一致」是一致在噪声里" % len(both_below))
    for r in both_below:
        print("     %-30s AΔ=%+.4f  BΔ=%+.4f" % (r[0], r[1], r[2]))
    print("  只在「两轮都可分辨」的 %d 条上算一致率：%d/%d"
          % (n_res, n_res_same, n_res))
    print("  ⚖ 这是**次要**口径。分母从 %d 缩到 %d 是有代价的："
          % (n_nonzero, n_res))
    print("     丢掉的那些不是「随机」的，是**按可分辨性筛过的**。")

    print("\n【必报 3】逐轨迹 Δ（max 尺只在档数相同处可比）")
    print("  %-30s %10s %10s %10s   %-8s %-8s %s"
          % ("tid", "AΔ", "BΔ", "B−A", "A<地板", "B<地板", "符号"))
    for t, da, db, sg, ba, bb, why in rows_out:
        diff = (db - da) if (da is not None and db is not None) else None
        print("  %-30s %10s %10s %10s   %-8s %-8s %s"
              % (t,
                 "%+.4f" % da if da is not None else "—",
                 "%+.4f" % db if db is not None else "—",
                 "%+.4f" % diff if diff is not None else "—",
                 "是" if ba else ("否" if ba is False else "—"),
                 "是" if bb else ("否" if bb is False else "—"),
                 why))

    print("\n" + "-" * 78)
    print("⚖ 这个比较**不能**说明哪一轮对，也不能说明剂量曲线本身正确。")
    if n_flip:
        print("⚖ 有 %d 条符号相反 ⇒ 在算力条件（compute_conditions.py）跑过之前，"
              % n_flip)
        print("   这些翻转**不可**解释成「重现性失败」—— 也可能是机器负载不同。")
        return 1
    print("✅ 无符号翻转（但读上面「两轮都低于地板」那一节再决定这意味着什么）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
