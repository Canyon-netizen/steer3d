#!/usr/bin/env python
"""Cross-arm verdict for the 137x2 sweep (revision 244.9).

Division of labour, deliberately narrow:
  r227_kcurve.analyze() already does, per arm, the exact two-sided sign test
  at trajectory and problem level plus the below-floor count.  This script
  does NOT reimplement any of that.  It imports the reader and reuses:
    parse_blocks -> parse_status -> join -> analyze -> sign_test

Why that matters: two parsers are two truths.  If this script re-derived the
per-cell deltas itself, it could disagree with the reader for reasons nobody
could audit.  Reuse is the guard.

What it adds, and only this:
  1. HardFail unless the two arms ran with IDENTICAL sweep params
     (pos_frac / n_steps / gap).  242.2 requires the arms to differ only in
     --arm; if a scan param differs the comparison is void, so this must be a
     hard failure, not a warning.
  2. HardFail unless each arm parsed exactly the expected cell count.
  3. Fisher's exact two-sided test on the (pos, neg) contingency between arms,
     at both trajectory and problem level.  The per-arm sign tests say "this
     arm is lopsided"; Fisher says whether the two arms differ from each
     other, which is the actual claim ("w flips sign where rand does not").
  4. Co-reports everything the ledger demands alongside any sign verdict:
     below-floor counts, knife-edge count, both arms' cell counts.

⚠⚠ What this cannot settle, stated so it is not read as settled:
  - It compares two arms.  It does NOT establish that either arm's dose
    response is correct, nor that the ladder was placed correctly.
  - If the two arms ran under different machine load, a difference between
    them is confounded with co-tenancy.  Print the wall-clock spans.
  - Fisher on tiny n is weak by construction; the p is reported, and the
    lower bound is reported next to it, never the verdict alone.

Exit: 0 verdict printed; 2 precondition/contract failure (no verdict).
"""
import argparse
import importlib.util
import os
import sys
from math import comb


def load_reader(path):
    if not os.path.isfile(path):
        raise SystemExit("PRECOND_FAIL: reader not found: %s" % path)
    spec = importlib.util.spec_from_file_location("r227_kcurve", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fisher_exact_two_sided(a, b, c, d):
    """Exact two-sided p for [[a, b], [c, d]] by summing all tables no more
    likely than the observed one.  Uses the definition of "no more likely"
    rather than a doubled one-tail, so it does not overstate small-n evidence.
    """
    n = a + b + c + d
    r1, r2, c1 = a + b, c + d, a + c
    if n == 0:
        return None, None

    def prob(x):
        return (comb(r1, x) * comb(r2, c1 - x)) / float(comb(n, c1))

    lo = max(0, c1 - r2)
    hi = min(r1, c1)
    p_obs = prob(a)
    p = 0.0
    for x in range(lo, hi + 1):
        px = prob(x)
        # tolerate float slop rather than silently dropping a term
        if px <= p_obs * (1 + 1e-12):
            p += px
    return min(1.0, p), p_obs


def read_arm(rc, log, status, expect_cells):
    with open(log, encoding="utf-8", errors="replace") as fh:
        log_text = fh.read()
    with open(status, encoding="utf-8", errors="replace") as fh:
        st_text = fh.read()
    blocks = rc.parse_blocks(log_text)
    # ⚠⚠ parse_status 返回 **(rows, alldone)**，不是裸 rows。
    # ⚖ 第一版漏了这个解包，把元组当 rows 传下去，join() 于是拿 len(rows)==2
    # ⚖   去比块数，报出「状态行数 2」—— 一个看起来像数据坏了、其实是自己传错类型的错。
    # ⚖⇒ 两个返回值都要用：alldone 是「这批跑完了」的契约信号，
    # ⚖   截断的状态文件没有它，此时**不出判决**而不是出半个判决。
    rows, alldone = rc.parse_status(st_text)
    if alldone is None:
        raise SystemExit(
            "PRECOND_FAIL: %s 无 ALLDONE 行 ⇒ 该轮可能没跑完，不出判决"
            % status)
    cells = rc.join(blocks, rows)
    if cells is None:
        raise SystemExit("PRECOND_FAIL: join() returned nothing for %s" % log)
    got = len(cells)
    if expect_cells is not None and got != expect_cells:
        raise SystemExit("PRECOND_FAIL: %s parsed %d cells, expected %d"
                         % (log, got, expect_cells))
    res = rc.analyze(cells, verbose=False)
    return res, got, alldone


def params_signature(res):
    """Frozen per-arm scan params.  Any disagreement across cells shows up as
    a list value; that must be a hard failure, not a silent first-wins."""
    sig = {}
    for k, v in sorted(res["sweep_params"].items()):
        sig[k] = tuple(v) if isinstance(v, (list, tuple)) else (v,)
    return sig


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

    w_res, w_n, w_done = read_arm(rc, args.w_log, args.w_status, args.expect_cells)
    r_res, r_n, r_done = read_arm(rc, args.rand_log, args.rand_status, args.expect_cells)

    # ---- gate 0: the two inputs must actually be different arms ----
    # ⚠⚠⚠ 变异台查出来的洞：sweep_params 只有 gap/n_steps/pos_frac，**不含 arm**。
    # ⚖ 于是「把同一份日志当两臂传进来」会安静地报出「两臂不可分辨」(p=1)，
    # ⚖ 看上去像个正常结论。⇒ 臂必须单独查，且必须**不同**。
    # ⚖ 同样要拒「臂名未量到」——那不是「两臂相同」，是「没量到」。
    w_arm, r_arm = w_res.get("arm"), r_res.get("arm")
    if w_arm is None or r_arm is None:
        print("HARD_FAIL 臂名未量到（w=%r rand=%r）⇒ 无法确认这是两臂比较"
              % (w_arm, r_arm))
        return 2
    if w_arm == r_arm:
        print("HARD_FAIL 两臂的 --arm 相同（都是 %r）⇒ 不是对照，是同一份数据"
              " 读了两次" % w_arm)
        return 2
    print("arms: w=%s  rand=%s  (不同臂，对照成立)" % (w_arm, r_arm))

    # ---- gate 1: the two arms must be comparable at all ----
    w_sig, r_sig = params_signature(w_res), params_signature(r_res)
    if w_sig != r_sig:
        print("HARD_FAIL 扫描参数两臂不一致，比较作废")
        for k in sorted(set(w_sig) | set(r_sig)):
            if w_sig.get(k) != r_sig.get(k):
                print("  %s: w=%r rand=%r" % (k, w_sig.get(k), r_sig.get(k)))
        return 2
    mixed = {k: v for k, v in w_sig.items() if len(v) != 1}
    if mixed:
        print("HARD_FAIL 扫描参数在同臂内逐格不一致: %r" % mixed)
        return 2

    n_w = sum(1 for ln in open(args.w_status, encoding="utf-8",
                              errors="replace").read().split("\n")
              if ln.strip().startswith("ALLDONE"))
    n_r = sum(1 for ln in open(args.rand_status, encoding="utf-8",
                               errors="replace").read().split("\n")
              if ln.strip().startswith("ALLDONE"))
    print("ALLDONE_last stamps: w=%s  rand=%s" % (w_done, r_done))
    # ⚠⚠ 修订 244.16.4：轮数 >1 的臂，那个戳只代表最后一轮。
    if n_w > 1 or n_r > 1:
        print("  ⛔ ALLDONE_count: w=%d rand=%d ⇒ 多轮并集，"
              "该戳不描述该臂的时间跨度" % (n_w, n_r))
    print("")
    print("scan_params (identical across arms AND across cells):")
    for k, v in sorted(w_sig.items()):
        print("  %s = %s" % (k, v[0]))
    print("")
    print("arm\tw_cells\tw_ok\tw_bad\tw_below_floor\tw_knife\trand_cells\t"
          "rand_ok\trand_bad\trand_below_floor\trand_knife")
    print("w\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d" % (
        w_n, w_res["n_ok"], w_res["n_bad"], w_res["n_below"],
        w_res["n_knife"], r_n, r_res["n_ok"], r_res["n_bad"],
        r_res["n_below"], r_res["n_knife"]))
    print("")

    levels = [("trajectory", "traj", "prob"),
              ("problem", "prob", None)]
    out = {}
    for label, key, _ in levels:
        w = w_res[key]
        r = r_res[key]
        if w is None or r is None:
            print("%s: one arm has no deltas (未量到) -- not a zero" % label)
            out[label] = None
            continue
        wp, wpos, wneg, wtie, wlb, wz = w
        rp, rpos, rneg, rtie, rlb, rz = r
        p_fisher, _ = fisher_exact_two_sided(wpos, wneg, rpos, rneg)
        out[label] = {"w": w, "rand": r, "fisher": p_fisher}
        print("[%s level]  (exact two-sided sign test per arm; Fisher across arms)"
              % label)
        print("  w    : pos=%d neg=%d tie=%d  p=%.6g  p_lower_bound=%.6g  z=%+.4f"
              % (wpos, wneg, wtie, wp, wlb, wz))
        print("  rand : pos=%d neg=%d tie=%d  p=%.6g  p_lower_bound=%.6g  z=%+.4f"
              % (rpos, rneg, rtie, rp, rlb, rz))
        print("  Fisher two-sided across arms: p=%.6g" % p_fisher)
        print("  below-floor: w=%d rand=%d   knife-edge: w=%d rand=%d"
              % (w_res["n_below"], r_res["n_below"],
                 w_res["n_knife"], r_res["n_knife"]))
        print("")

    print("VERDICT")
    for label in ("trajectory", "problem"):
        d = out.get(label)
        if d is None:
            print("  %-10s 未量到" % label)
            continue
        wpos, wneg = d["w"][1], d["w"][2]
        rpos, rneg = d["rand"][1], d["rand"][2]
        w_lopsided = d["w"][0] is not None and d["w"][0] < 0.05
        r_lopsided = d["rand"][0] is not None and d["rand"][0] < 0.05
        if d["fisher"] is not None and d["fisher"] < 0.05:
            sep = "两臂可分辨"
        else:
            sep = "两臂差异未达 0.05（p=%.6g）" % (d["fisher"] or float("nan"))
        print("  %-10s w %s / rand %s ; %s"
              % (label,
                 "显著单侧化" if w_lopsided else "未显著",
                 "显著单侧化" if r_lopsided else "未显著",
                 sep))
    print("")
    print("⚠ 以上只说「两臂彼此不同或不可分辨」。")
    print("⚠ 它不证明：剂量响应是对的 / 阶梯排对了 / 算力条件两臂可比。")
    print("⚠ 判读任何一条前，先看两臂各自的 below-floor 与 knife-edge 计数。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
