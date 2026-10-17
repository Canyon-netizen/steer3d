#!/usr/bin/env python
"""Independently recompute prompt token count P for sidecars.

Why this script exists (revision 244.5 -> 244.7):
  The reader's P half of n_eff = P + t was judged same-source self-proof,
  because probe line 390 reads cti["extra"]["prompt_tokens"] -- the sidecar's
  own report.  A reader-side cross-check that compares the sidecar against the
  sidecar proves nothing.

What this does instead:
  Fresh process.  Fresh tokenizer load.  Re-encode chat_template_input with
  the same tokenizer + add_special_tokens=False the probe uses, and compare
  that independent length against the sidecar's self-reported value.

This is a genuinely separate code path:
  - sidecar value was produced by the data-generation pipeline
  - here it is recomputed by loading the tokenizer again from disk
  If they agree, that is evidence about P.  If they disagree, the script must
  say so -- it does not filter, average, or fall back.

Exit codes:
  0 = every sidecar matched
  1 = at least one mismatch (details printed)
  2 = crash / precondition failure (missing model, missing sidecar dir)
"""
import json
import os
import sys
from glob import glob

MODEL = "/home/zhourui/.cache/huggingface/models/Qwen--Qwen3-1.7B/snapshots/master"
SIDECAR = "/home/zhourui/steer3d_bpath/gen_b2_max32768/aime"


def main():
    if not os.path.isdir(MODEL):
        print("PRECOND_FAIL: model dir missing: %s" % MODEL)
        return 2
    if not os.path.isdir(SIDECAR):
        print("PRECOND_FAIL: sidecar dir missing: %s" % SIDECAR)
        return 2

    from transformers import AutoTokenizer

    # Same load call the probe makes, but in this process, not its.
    tok = AutoTokenizer.from_pretrained(MODEL)
    print("tokenizer_class_loaded: %s" % type(tok).__name__)

    files = sorted(glob(os.path.join(SIDECAR, "*.json")))
    if not files:
        print("PRECOND_FAIL: no sidecar json in %s" % SIDECAR)
        return 2

    rows = []
    for f in files:
        j = json.load(open(f, encoding="utf-8"))
        tid = j.get("trajectory_id") or os.path.basename(f)[:-5]
        cti = j.get("chat_template_input")
        extra = j.get("extra") or {}

        # Independent re-encode. This is the quantity under test.
        recomp = len(tok(cti, add_special_tokens=False).input_ids)

        rows.append({
            "tid": tid,
            "sidecar_P": extra.get("prompt_tokens"),
            "recomp_P": recomp,
            "top_level_n_prompt_tokens": j.get("n_prompt_tokens"),
            "cti_type": type(cti).__name__,
            "cti_len_chars": len(cti) if isinstance(cti, str) else -1,
        })

    hdr = "tid\tsidecar_P\trecomp_P\tdelta\tratio\ttop_level_n_pt\tcti_type\tcti_chars"
    print(hdr)
    n_match = 0
    n_mismatch = 0
    n_flag_mismatch = 0
    for r in rows:
        sp = r["sidecar_P"]
        rp = r["recomp_P"]
        if sp is None:
            print("%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s" % (
                r["tid"], "NONE", rp, "NA", "NA",
                r["top_level_n_prompt_tokens"], r["cti_type"], r["cti_len_chars"]))
            n_mismatch += 1
            continue
        d = rp - sp
        ratio = (rp / sp) if sp else float("nan")
        flag = "OK" if d == 0 else "MISMATCH"
        if d == 0:
            n_match += 1
        else:
            n_mismatch += 1
        if flag == "MISMATCH":
            n_flag_mismatch += 1
        print("%s\t%d\t%d\t%+d\t%.6f\t%s\t%s\t%s\t%s" % (
            r["tid"], sp, rp, d, ratio,
            r["top_level_n_prompt_tokens"], r["cti_type"], r["cti_len_chars"], flag))

    print("---")
    print("total=%d match=%d mismatch=%d" % (len(rows), n_match, n_mismatch))
    # Integrity invariant (added 244.7).  The per-row flag column is display
    # only, so nothing downstream depended on it -- which is exactly why a
    # mutation that hardcodes flag="OK" stayed green in the first bench run.
    # Cross-check the printed column against the counter, and make a lying
    # column a hard failure instead of a silent one.
    counted_all = (n_match + n_mismatch == len(rows))
    flag_agrees = (n_flag_mismatch == n_mismatch)
    integrity_ok = counted_all and flag_agrees
    print("INTEGRITY: counted_all=%s flag_matches_counter=%s"
          % (counted_all, flag_agrees))
    if not integrity_ok:
        return 3
    return 0 if n_mismatch == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
