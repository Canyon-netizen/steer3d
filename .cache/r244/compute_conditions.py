#!/usr/bin/env python
"""Per-cell compute conditions for the two arms (revision 244.10).

Why this exists:
  Limitation 4 says the w arm showed 4-21x compute fluctuation while the rand
  arm's fluctuation was "量不到" (not measurable) because its log has no END
  lines.  The cross-arm comparison therefore could never check whether the two
  arms ran under comparable machine conditions.  The new sweep writes END
  lines for both arms, so that comparison becomes possible for the first time.

What it reports, and what it refuses to report:
  - per-cell duration from BEGIN time to END time, paired by BLOCK ORDER
    (never by tid: 244.4 measured only 14 distinct tids across 137 cells)
  - median / max / max-over-median, overall and per trajectory
  - a cross-arm comparison ONLY when both arms are measurable
  - when an arm has no END lines, it prints 未量到 and the reason.  It does not
    substitute an estimate, does not reuse the other arm's numbers, and does
    not treat "unknown" as "comparable".

⚠⚠ Day-boundary handling is not optional here.  The new run starts ~20:28 and
the second arm ends past 00:00, so naive END-minus-BEGIN is NEGATIVE for every
cell after midnight.  That would silently invert the long-tail statistic.
Seconds past midnight are tracked with an explicit wrap counter and reported.

⚠⚠ What a large max/med does and does not mean.  244.2b found 8/14 w-arm
trajectories with max/med >= 4.  It did NOT establish that co-tenancy moved
the readings; the sign overlap there was Fisher p=0.4286.  So this tool
measures the compute condition and stops.  It never claims a direction of
effect on the readings.

Exit: 0 report printed; 2 precondition failure.
"""
import argparse
import os
import re
import statistics
import sys

# ⚠⚠⚠ 时刻**三个部分全部用命名组**。第一版把 ``rest`` 编成第 2 组，
# ⚖ 却用位置组 2/3 去取分钟和秒 ⇒ 取到的是 rest 片段，于是 int() 直接崩。
# ⚖ 这是「位置组与命名组混用」的第三次翻车（第一次记在 244：两个正则一个用
# ⚖ 位置组一个用命名组，下标对不上）。
# ⚖⇒ 判别式：**一条正则里只要出现了 rest 这类可长可短的捕获，就不许再用位置组。**
BEGIN_RE = re.compile(
    r"^###\s+BEGIN\s+(?P<tid>\S+)(?P<rest>.*?)\s\s+"
    r"(?P<h>\d\d):(?P<m>\d\d):(?P<s>\d\d)\s*$")
END_RE = re.compile(
    r"^###\s+END\s+\[\d+/\d+\]\s+(?P<tid>\S+)\s+rc=(?P<rc>-?\d+)\s\s+"
    r"(?P<h>\d\d):(?P<m>\d\d):(?P<s>\d\d)\s*$")


# A single cell longer than this is treated as a malformed pair, not a wrap.
# Chosen from the observed data: the longest w-arm cell was 541s, so 4h is a
# ~27x margin -- generous, but tight enough to reject a garbage pair.
MAX_PLAUSIBLE_SEC = 4 * 3600


def secs(h, m, s):
    return int(h) * 3600 + int(m) * 60 + int(s)


def parse(path):
    """-> (cells, n_begin, n_end).  cells: [{tid, dur|None, rc}]"""
    with open(path, encoding="utf-8", errors="replace") as fh:
        lines = fh.read().split("\n")
    blocks = []
    cur = None
    n_begin = n_end = 0
    for line in lines:
        mb = BEGIN_RE.match(line)
        if mb:
            n_begin += 1
            if cur is not None:
                blocks.append(cur)
            cur = {"tid": mb.group("tid"),
                   "start": secs(mb.group("h"), mb.group("m"),
                                 mb.group("s")), "end": None}
            continue
        me = END_RE.match(line)
        if me:
            n_end += 1
            if cur is not None:
                cur["end"] = secs(me.group("h"), me.group("m"),
                                  me.group("s"))
                cur["rc"] = int(me.group("rc"))
            continue
    if cur is not None:
        blocks.append(cur)

    n_wrap = 0
    cells = []
    for b in blocks:
        if b["end"] is None:
            cells.append({"tid": b["tid"], "dur": None, "rc": None})
            continue
        d = b["end"] - b["start"]
        if d < 0:
            # END before BEGIN.  Either the run crossed midnight (so add a day)
            # or the pair is malformed.  The test is on the POST-WRAP value:
            # it has to land in a plausible range.  First version tested the
            # wrong side of the inequality and silently DROPPED every
            # post-midnight cell -- which is exactly the second half of the
            # rand arm -- while reporting "no END lines".  Wrong diagnosis.
            d2 = d + 86400
            if 0 <= d2 < MAX_PLAUSIBLE_SEC:
                d = d2
                n_wrap += 1
            else:
                cells.append({"tid": b["tid"], "dur": None,
                              "rc": b.get("rc"),
                              "why": "END<BEGIN 且回绕后仍不合理"})
                continue
        cells.append({"tid": b["tid"], "dur": d, "rc": b.get("rc")})
    return cells, n_begin, n_wrap


def stats_for(label, cells):
    good = [c for c in cells if c["dur"] is not None]
    if not good:
        print("[%s] 未量到 —— 没有可配对的 END 行（%d 格无 END）"
              % (label, len(cells)))
        return None
    durs = [c["dur"] for c in good]
    med = statistics.median(durs)
    mx = max(durs)
    per_traj = {}
    for c in good:
        per_traj.setdefault(c["tid"], []).append(c["dur"])
    ratios = []
    for tid, ds in sorted(per_traj.items()):
        if len(ds) >= 2:
            m = statistics.median(ds)
            ratios.append((max(ds) / m if m else float("inf"), tid, len(ds)))
    n_ge4 = sum(1 for r, _, _ in ratios if r >= 4.0)
    print("[%s] 可量：%d/%d 格有 END" % (label, len(good), len(cells)))
    print("  耗时 中位数=%.0fs  max=%.0fs  max/中位=%.2f  总计=%.1f 分钟"
          % (med, mx, mx / med if med else float("nan"), sum(durs) / 60.0))
    print("  逐轨迹 max/中位 ≥4x 的条数 = %d / %d" % (n_ge4, len(ratios)))
    if ratios:
        ratios.sort(reverse=True)
        print("  最极端 3 条：" + "; ".join(
            "%s %.1fx (%d格)" % (t, r, k) for r, t, k in ratios[:3]))
    return {"median": med, "max": mx, "n_ge4": n_ge4, "n_traj": len(ratios),
            "total": sum(durs)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--w-log", required=True)
    ap.add_argument("--rand-log", required=True)
    args = ap.parse_args()
    for p in (args.w_log, args.rand_log):
        if not os.path.isfile(p):
            print("PRECOND_FAIL: %s missing" % p)
            return 2

    w_cells, w_nb, w_wrap = parse(args.w_log)
    r_cells, r_nb, r_wrap = parse(args.rand_log)
    print("BEGIN 行：w=%d rand=%d" % (w_nb, r_nb))
    print("日界回绕次数：w=%d rand=%d  （跑批跨零点时会 >0，不是 bug）"
          % (w_wrap, r_wrap))
    print("")
    w = stats_for("w", w_cells)
    r = stats_for("rand", r_cells)
    print("")
    if w is None or r is None:
        missing = "rand" if r is None else "w"
        print("VERDICT: 两臂算力条件**不可比** —— %s 臂的每格耗时未量到" % missing)
        print("⚠ 这是「没量到」，不是「无差异」。⛔ 不得读成两臂条件相同。")
        return 0
    print("两臂算力条件（同批串行、同一空卡）：")
    print("  w    总耗时=%.1f 分钟  中位=%.0fs  max/中位=%.2f  ≥4x 轨迹 %d/%d"
          % (w["total"] / 60.0, w["median"], w["max"] / w["median"],
             w["n_ge4"], w["n_traj"]))
    print("  rand 总耗时=%.1f 分钟  中位=%.0fs  max/中位=%.2f  ≥4x 轨迹 %d/%d"
          % (r["total"] / 60.0, r["median"], r["max"] / r["median"],
             r["n_ge4"], r["n_traj"]))
    print("")
    print("⚠ 以上只量了算力条件本身。⛔ 它不说明共卡是否改变了读数的符号或量级")
    print("  （244.2b：长尾轨迹与 w 臂正 Δ 的 8/8 重合，Fisher p=0.4286，不显著）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
