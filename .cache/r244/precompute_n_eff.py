#!/usr/bin/env python
"""Precompute n_eff independently, BEFORE the probe runs (revision 244.8).

Why:
  Revisions 244.3 -> 244.7 established that the reader's cross-check
  `b["n_eff"] != pt_sum` never fires, and that the BEGIN-line `n_eff=` that
  r232 backfilled from a previous round's readings is the exact defect:
  self-proof twice, labelled "cross-verified".

  The fix is not to relax the reader.  It is to give the producer a genuinely
  independent source for n_eff, and to emit it before the probe runs so the
  reader's check becomes falsifiable.

Where the numbers come from, and why this is independent:
  P = len(tokenizer(chat_template_input).input_ids)
      -- re-encoded here, in a separate process, from the stored string.
         NOT read from the sidecar's extra.prompt_tokens, which is what the
         probe reports.  Revision 244.7 measured those two agree 60/60, but
         that agreement is now used as a falsifiable prediction instead of
         being assumed.
  t = max(1, int(len(npz token_ids) * pos_frac))
      -- the same formula and the same stored artifact the probe reads, but
         evaluated before the probe runs, from the npz rather than from the
         probe's own stdout.

Both quantities are known before any GPU work starts, so the sweep can print
n_eff= into its BEGIN line.  If the probe later disagrees, the reader goes
red -- which is the entire point.

Guard rails (a missing value must never become a silent fallback):
  - every cell's tid must appear in the map, else the caller HardFails
  - P must be > 0 and t must be > 0
  - the map records its own md5 and the caller stamps it into the log

Exit: 0 map written and complete; 1 incomplete/invalid map; 2 precondition.
"""
import argparse
import hashlib
import json
import os
import sys
from glob import glob

import numpy as np

MODEL = "/home/zhourui/.cache/huggingface/models/Qwen--Qwen3-1.7B/snapshots/master"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True,
                    help="dir holding <tid>.json sidecars and <tid>.npz")
    ap.add_argument("--out", required=True, help="output tsv")
    ap.add_argument("--pos-frac", type=float, required=True,
                    help="must equal the sweep's --pos-frac exactly")
    ap.add_argument("--cells", default="",
                    help="optional cell list; assert full coverage of its tids")
    ap.add_argument("--t-source", choices=["sidecar", "npz"], default="sidecar",
                    help="which artifact supplies the generated length for t; "
                         "default sidecar keeps the reader's t-half check "
                         "falsifiable (the probe reads the npz, not the sidecar)")
    args = ap.parse_args()

    if not os.path.isdir(args.data_dir):
        print("PRECOND_FAIL: no data dir %s" % args.data_dir)
        return 2
    if not os.path.isdir(MODEL):
        print("PRECOND_FAIL: no model dir %s" % MODEL)
        return 2
    if not (0.0 < args.pos_frac <= 1.0):
        print("PRECOND_FAIL: pos_frac out of range: %r" % args.pos_frac)
        return 2

    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL)

    sidecars = sorted(glob(os.path.join(args.data_dir, "*.json")))
    if not sidecars:
        print("PRECOND_FAIL: no sidecar json in %s" % args.data_dir)
        return 2

    rows = []
    problems = []
    n_gen_disagree = []
    for f in sidecars:
        tid = os.path.basename(f)[:-5]
        npz = os.path.join(args.data_dir, tid + ".npz")
        if not os.path.isfile(npz):
            problems.append("%s MISSING_NPZ" % tid)
            continue
        j = json.load(open(f, encoding="utf-8"))
        cti = j.get("chat_template_input")
        if not isinstance(cti, str) or not cti:
            problems.append("%s CTI_NOT_STR" % tid)
            continue
        P = len(tok(cti, add_special_tokens=False).input_ids)

        # Two artifacts report the generated length.  The probe reads the npz;
        # here t is computed from the sidecar's own report instead, so the
        # reader's check has two genuinely different sources for the t half.
        z = np.load(npz)
        try:
            n_npz = len(z["token_ids"])
        finally:
            z.close()
        n_side = j.get("n_generated_tokens")
        if n_side is None:
            problems.append("%s NO_SIDECAR_n_generated_tokens" % tid)
            continue
        n_side = int(n_side)
        if n_npz != n_side:
            n_gen_disagree.append((tid, n_side, n_npz))

        n_used = n_side if args.t_source == "sidecar" else n_npz
        t = max(1, int(n_used * args.pos_frac))
        if P <= 0 or t <= 0:
            problems.append("%s NONPOSITIVE P=%d t=%d" % (tid, P, t))
            continue
        rows.append((tid, P, n_side, n_npz, t, P + t))

    if problems:
        print("INCOMPLETE: %d problem(s)" % len(problems))
        for p in problems[:10]:
            print("  " + p)
        return 1

    if args.cells:
        want = set()
        with open(args.cells, encoding="utf-8") as fh:
            for line in fh:
                f0 = line.rstrip("\n").split("\t")
                if f0 and f0[0]:
                    want.add(f0[0])
        have = {r[0] for r in rows}
        miss = want - have
        if miss:
            print("COVERAGE_FAIL: %d cell tid(s) absent from map: %s"
                  % (len(miss), sorted(miss)[:5]))
            return 1

    lines = ["tid\tP\tn_gen_sidecar\tn_gen_npz\tt\tn_eff"]
    for r in rows:
        lines.append("%s\t%d\t%d\t%d\t%d\t%d" % r)
    blob = "\n".join(lines) + "\n"
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(blob)

    md5 = hashlib.md5(blob.encode("utf-8")).hexdigest()
    # r[-1] not r[4]: the row grew a column when the npz cross-check was
    # added, and r[4] silently became t.  Label said n_eff, measured t.
    eff = sorted(r[-1] for r in rows)
    print("rows=%d pos_frac=%r n_eff_min=%d n_eff_max=%d"
          % (len(rows), args.pos_frac, eff[0], eff[-1]))
    print("t_source=%s n_gen_sidecar_vs_npz_disagree=%d"
          % (args.t_source, len(n_gen_disagree)))
    for tid, a, b in n_gen_disagree[:5]:
        print("  N_GEN_DISAGREE %s sidecar=%d npz=%d" % (tid, a, b))
    print("map_md5=%s" % md5)
    print("out=%s" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
