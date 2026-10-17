#!/usr/bin/env python
"""Field-by-field diff between the two arms' readout lines (revision 244.23).

Why: the w and rand rounds differ only in --arm.  That makes them a clean
single-variable pair, and it lets us say something strong and cheap:

  fields that MUST be identical (P, t, n_gen, tid, k, scope, pos_frac,
  n_steps, gap)  -> if any differ, the two rounds are NOT a single-variable
                     pair and the cross-arm verdict is void.

  fields that MAY differ (anything the instrument computes from the injected
  direction: p9_lo_meas, p9_hi_meas, slope, residuals, up_mono_*) -> those
  are the effect being measured.

⚠ This does NOT decide which arm is right.  It decides whether the comparison
is the comparison we think it is.
"""
import json
import sys

MUST_MATCH = ("tid", "P", "t", "n_gen", "pos_frac", "n_steps", "gap",
              "inject_scope", "inject_n_sites", "inject_nested", "arm")


def load(path):
    out = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if '"p9_lo_meas"' not in line:
                continue
            try:
                out.append(json.loads(line[line.index("{"):]))
            except Exception as e:
                raise SystemExit("BAD_JSON %s: %s" % (path, e))
    return out


def main():
    a = load(sys.argv[1])
    b = load(sys.argv[2])
    if len(a) != len(b):
        print("PRECOND_FAIL 格数不同 %d vs %d" % (len(a), len(b)))
        return 2
    bad_order = [(i, x.get("tid"), y.get("tid")) for i, (x, y) in enumerate(zip(a, b))
                 if x.get("tid") != y.get("tid")]
    must_bad = {}
    may_diff = set()
    for x, y in zip(a, b):
        for k in MUST_MATCH:
            if k == "arm":
                continue
            if x.get(k) != y.get(k):
                must_bad.setdefault(k, 0)
                must_bad[k] += 1
        for k in set(x) | set(y):
            if k == "arm":
                continue
            if x.get(k) != y.get(k):
                may_diff.add(k)

    print("格数 %d / %d" % (len(a), len(b)))
    if bad_order:
        print("⛔ 逐格 tid 顺序不一致，前 3：%r" % bad_order[:3])
        return 2
    print("✅ 逐格 tid 顺序一致")
    print("arm: A=%r  B=%r" % (a[0].get("arm"), b[0].get("arm")))
    if a[0].get("arm") == b[0].get("arm"):
        print("⛔ 两臂 arm 名相同 ⇒ 不是两臂对照")
        return 2

    print("\n【必须相同】与臂无关的字段")
    if must_bad:
        for k, n in sorted(must_bad.items(), key=lambda kv: -kv[1]):
            print("  ⛔ %-16s 不一致 %d/%d 格" % (k, n, len(a)))
        print("\n⇒ ⛔ **两轮不是单变量对照**，跨臂判决作废（闸失败）")
        return 1
    print("  ✅ %s 全部逐位相同" % ", ".join(MUST_MATCH[:-1]))

    print("\n【允许不同】随臂改变的字段（这就是被测的效应）")
    for k in sorted(may_diff):
        xs = [x.get(k) for x in a]
        ys = [y.get(k) for y in b]
        nd = sum(1 for u, v in zip(xs, ys) if u != v)
        nx = [v for v in xs if isinstance(v, (int, float))]
        ny = [v for v in ys if isinstance(v, (int, float))]
        rng = ("范围 %.6g..%.6g" % (min(nx), max(nx)) if nx else "")
        rny = ("范围 %.6g..%.6g" % (min(ny), max(ny)) if ny else "")
        print("  · %-22s 不同 %3d/%d 格   A %s   B %s" % (k, nd, len(a), rng, rny))
    print("\n⚖ 上面这些字段的差异**不判断谁对**；它只确认两轮确实只差 --arm。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
