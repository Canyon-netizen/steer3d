#!/usr/bin/env python
"""Phase-0 rehearsal for the n_eff-bearing BEGIN line (revision 244.8).

The question this answers before any GPU time is spent:
  If the sweep had emitted `n_eff=` computed by precompute_n_eff.py, would the
  reader's cross-check have stayed green on cells we already ran?

That check (r227_kcurve.py:214, b["n_eff"] != pt_sum) has never been able to
fire -- 244.5 proved it is structurally unfireable today.  After this change
it becomes a real prediction: BEGIN's independently computed n_eff versus the
probe's own self-reported P + t.

This script is that prediction, tested against the 137 already-collected w-arm
cells instead of against fresh ones.  Block-wise pairing, by BEGIN order --
NOT by tid, because tid is not unique across the 137 cells (244.4 measured
only 14 distinct tids, each repeated 9-11 times).

What this does and does not prove:
  - matching  : the two routes agree on every cell, so the new BEGIN line will
                not turn a passing batch red
  - mismatching: either pos_frac, the data dir, or the npz/tokens source is
                wrong -- do NOT launch
  It does NOT prove the agreement is non-tautological: precompute reads the
  same npz for t that the probe reads.  That limitation is stated in the
  ledger, not hidden here.

Exit: 0 all cells agree; 1 any mismatch; 2 precondition failure.
"""
import argparse
import json
import os
import re
import sys

BEGIN_RE = re.compile(r"^###\s+BEGIN\s+(?P<tid>\S+)(?P<rest>.*?)\s\s+"
                      r"(?P<time>\d\d:\d\d:\d\d)\s*$")
NUM_RE = {
    "P": re.compile(r'"P"\s*:\s*(\d+)'),
    "t": re.compile(r'"t"\s*:\s*(\d+)'),
    "n_gen": re.compile(r'"n_gen"\s*:\s*(\d+)'),
}


def load_map(path):
    out = {}
    with open(path, encoding="utf-8") as fh:
        head = fh.readline()
        if not head.startswith("tid\t"):
            print("PRECOND_FAIL: map header unexpected: %r" % head[:40])
            return None
        cols = head.rstrip("\n").split("\t")
        if "n_eff" not in cols:
            print("PRECOND_FAIL: map has no n_eff column: %r" % cols)
            return None
        idx = {name: cols.index(name) for name in cols}
        for line in fh:
            f = line.rstrip("\n").split("\t")
            if len(f) < len(cols):
                continue
            out[f[0]] = {
                "P": int(f[idx["P"]]),
                "n_gen_sidecar": int(f[idx["n_gen_sidecar"]]),
                "n_gen_npz": int(f[idx["n_gen_npz"]]),
                "t": int(f[idx["t"]]),
                "n_eff": int(f[idx["n_eff"]]),
            }
    if not out:
        print("PRECOND_FAIL: map empty")
        return None
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True)
    ap.add_argument("--map", required=True)
    ap.add_argument("--expect-cells", type=int, default=137)
    args = ap.parse_args()

    if not os.path.isfile(args.log):
        print("PRECOND_FAIL: no log %s" % args.log)
        return 2
    mp = load_map(args.map)
    if mp is None:
        return 2

    with open(args.log, encoding="utf-8", errors="replace") as fh:
        lines = fh.read().split("\n")

    blocks = []
    cur = None
    for line in lines:
        m = BEGIN_RE.match(line)
        if m:
            if cur is not None:
                blocks.append(cur)
            cur = {"tid": m.group("tid"), "rest": m.group("rest"),
                   "begin_n_eff": None, "body": []}
            ne = re.search(r"n_eff=(\d+)", m.group("rest"))
            if ne:
                cur["begin_n_eff"] = int(ne.group(1))
        elif cur is not None:
            cur["body"].append(line)
    if cur is not None:
        blocks.append(cur)

    if len(blocks) != args.expect_cells:
        print("PRECOND_FAIL: parsed %d blocks, expected %d"
              % (len(blocks), args.expect_cells))
        return 2

    n_ok = 0
    bad = []
    n_already_carried = 0
    for i, b in enumerate(blocks, 1):
        if b["begin_n_eff"] is not None:
            n_already_carried += 1
        body = "\n".join(b["body"])
        got = {}
        for k, rx in NUM_RE.items():
            mm = rx.search(body)
            got[k] = int(mm.group(1)) if mm else None
        if got["P"] is None or got["t"] is None:
            bad.append((i, b["tid"], "P/t not parsed", got))
            continue
        ref = mp.get(b["tid"])
        if ref is None:
            bad.append((i, b["tid"], "tid absent from map", got))
            continue
        pt_sum = got["P"] + got["t"]
        row = [i, b["tid"], pt_sum, ref["n_eff"], pt_sum - ref["n_eff"],
               got["P"], ref["P"], got["t"], ref["t"],
               got["n_gen"], ref["n_gen_npz"], ref["n_gen_sidecar"]]
        if pt_sum == ref["n_eff"]:
            n_ok += 1
        else:
            bad.append(tuple(row))

    print("cells=%d agree=%d disagree=%d" % (len(blocks), n_ok, len(bad)))
    print("log_cells_already_carrying_n_eff=%d" % n_already_carried)
    # The t half is only falsifiable if its two artifacts agree on the
    # generated length.  Report it rather than assume it: if sidecar and npz
    # disagree, BEGIN's t and the probe's t are computed from different numbers
    # and the reader's check would fire for a reason that is not a real fault.
    n_gen_split = sum(1 for v in mp.values()
                      if v["n_gen_sidecar"] != v["n_gen_npz"])
    print("map_tids=%d  map_n_gen_sidecar_vs_npz_disagree=%d"
          % (len(mp), n_gen_split))
    print("--- header ---")
    print("idx\ttid\tpt_sum\tmap_n_eff\tdelta\tP_probe\tP_map\tt_probe\t"
          "t_map\tn_gen_probe\tn_gen_npz\tn_gen_sidecar")
    print("--- disagree / unparsed (up to 10) ---")
    for r in bad[:10]:
        print("\t".join(str(x) for x in r))
    if bad:
        print("---")
        print("VERDICT: DO_NOT_LAUNCH  (%d cell(s) disagree)" % len(bad))
        return 1
    print("---")
    print("VERDICT: rehearsal OK  (%d/%d cells agree)" % (n_ok, len(blocks)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
