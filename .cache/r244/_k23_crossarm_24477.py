#!/usr/bin/env python
"""244.77 的 **K23 跨臂复核**（⛔ 一次性，不入库）。

修订 238 的 K23：**两臂的扫描参数必须逐字相同**（⛔ 只许 `--arm` 不同）。
⇒ 这份批里 `--pos-frac` 从「写死的单一常量」挪成了「按格从清单取」，
   所以 K23 **必须重新核**：挪位之后，两臂读的是**同一份清单** ⇒
   ⇒ 每个格子的 `--pos-frac` 两臂必然相同 ⇒ 但这要**从真实读数里**验，不是嘴上说。

本脚本做的是**逐字比对**，不是重跑：
  · 从两份日志里各抠出每格的读数 JSON
  · 逐字比对两臂的扫描参数：pos_frac / n_steps / gap / P / t /
    inject_scope / inject_n_sites / inject_nested
  · 再比 BEGIN 行的 n_eff（两臂必须取到**同一个**映射表值）
  · 并且**要求** `arm` 字段两臂**不同**（否则「两臂相同」可能是「压根没跑两臂」）

⛔ 期望集**不**从被检对象派生：扫描参数清单是写死的常量表，不是「读出来有什么就算什么」。
"""
import argparse
import json
import re
import sys

SCAN_KEYS = ("pos_frac", "n_steps", "gap", "P", "t",
             "inject_scope", "inject_n_sites", "inject_nested")
BEGIN_RE = re.compile(r"^### BEGIN (?P<tid>\S+) \[(?P<i>\d+)/(?P<n>\d+)\] "
                       r"n_eff=(?P<neff>\d+)")


def read_log(path):
    readings = {}
    begins = {}
    order = []
    with open(path, encoding="utf-8") as fh:
        for ln in fh:
            ln = ln.rstrip("\n")
            m = BEGIN_RE.match(ln)
            if m:
                begins[m.group("tid")] = int(m.group("neff"))
                continue
            s = ln.strip()
            if s.startswith("{") and '"tid"' in s:
                try:
                    d = json.loads(s)
                except Exception:
                    continue
                if "tid" in d:
                    readings[d["tid"]] = d
                    order.append(d["tid"])
    return readings, begins, order


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log-w", required=True)
    ap.add_argument("--log-rand", required=True)
    ap.add_argument("--expect-arm-w", default="w")
    ap.add_argument("--expect-arm-rand", default="rand")
    args = ap.parse_args()

    fails = []

    def chk(name, ok, detail=""):
        print("[%s] %-46s %s" % ("OK  " if ok else "FAIL", name, detail))
        if not ok:
            fails.append(name)

    rw, bw, ow = read_log(args.log_w)
    rr, br, orr = read_log(args.log_rand)

    chk("C0 两份日志都有读数", bool(rw) and bool(rr),
        "w=%d 格 rand=%d 格" % (len(rw), len(rr)))
    chk("C1 两臂的 tid 集合相同", set(rw) == set(rr),
        "w_only=%s rand_only=%s" % (sorted(set(rw) - set(rr))[:3],
                                    sorted(set(rr) - set(rw))[:3]))

    diffs = []
    for tid in sorted(set(rw) & set(rr)):
        a, b = rw[tid], rr[tid]
        for k in SCAN_KEYS:
            va, vb = a.get(k, "<缺>"), b.get(k, "<缺>")
            if va != vb:
                diffs.append("%s %s: w=%r rand=%r" % (tid, k, va, vb))
    chk("C2 扫描参数两臂逐字相同", not diffs,
        "; ".join(diffs[:4]) if diffs else "全部 %d 项 × %d 格相同"
        % (len(SCAN_KEYS), len(set(rw) & set(rr))))

    aw = sorted(set(rw[t]["arm"] for t in rw))
    ar = sorted(set(rr[t]["arm"] for t in rr))
    chk("C3 两臂的 arm 字段分别正确且不同",
        aw == [args.expect_arm_w] and ar == [args.expect_arm_rand],
        "w臂=%s rand臂=%s" % (aw, ar))

    nd = []
    for tid in sorted(set(bw) & set(br)):
        if bw[tid] != br[tid]:
            nd.append("%s w=%d rand=%d" % (tid, bw[tid], br[tid]))
    chk("C4 两臂 BEGIN 的 n_eff 相同（同一张表）", not nd,
        "; ".join(nd[:3]) if nd else "%d 格全同" % len(set(bw) & set(br)))

    # 每臂内部 pos_frac 单一（读者 K23 的前提：单份日志内不得混 pos_frac）
    for tag, rd in (("w", rw), ("rand", rr)):
        pf = sorted(set(rd[t].get("pos_frac") for t in rd))
        chk("C5 %s 臂内 pos_frac 单一" % tag, len(pf) == 1, str(pf))

    # n_eff 与读数 P+t 的独立互证（读者里那道能红的检查，这里手算一遍）
    bad = []
    for tid in sorted(set(rw) & set(bw)):
        for tag, rd in (("w", rw), ("rand", rr)):
            d = rd[tid]
            pt = int(d["P"]) + int(d["t"])
            if bw[tid] != pt:
                bad.append("%s/%s BEGIN=%d vs P+t=%d" % (tid, tag, bw[tid], pt))
    chk("C6 两臂的 n_eff 与读数 P+t 相等（独立互证）", not bad,
        "; ".join(bad[:3]) if bad else "全对")

    print("--- summary ---")
    print("checks_failed=%d  %s" % (len(fails), ",".join(fails) if fails else "ALL_GREEN"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
