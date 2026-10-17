#!/usr/bin/env python
"""Mutation bench for recomp_p.py (revision 244.7, rewritten after run 1).

Why this bench was rewritten:
  Run 1 reported caught=2 missed=2.  Both misses had to be classified before
  anything could be concluded, and neither was a defect in the check:

    M1 add_special_tokens  False -> True  stayed green.
      Classified INVALID MUTATION, not a check defect: Qwen2Tokenizer adds no
      special tokens to plain text, so the two calls encode identically.  The
      mutant is behaviour-preserving, so no bench can catch it.  Useful
      corollary: the add_special_tokens=False in recomp_p.py is inert for
      these 60 strings and carries no information either way.

    M4 hardcode flag="OK"  stayed green.
      Classified BENCH-TARGET ERROR: the mutation hit a display column, and
      the gate reads the counter, not the column.  The fix is in the script,
      not the bench: recomp_p.py now cross-checks the printed column against
      the counter and exits 3 on disagreement, so a lying column is a hard
      failure.  M4 is retained and must now be caught.

Verdicts this bench can issue:
  caught        data-changing mutation -> rc != 0 and artifact shows mismatch
  GATE_NEUTERED rc lies (0) but artifact shows mismatch > 0 -> bench reports
                the gate was neutered instead of trusting rc
  UNPROVABLE    mutant emits an artifact identical to a genuine pass, so the
                bench is blind to it by construction.  Reported, not counted
                as a miss, because the remedy is a static check, not a
                mutation.
  INVALID       mutant is behaviour-preserving; cannot be caught

The static check is the actual anti-tautology evidence: a mutation bench on an
output-comparison check cannot prove the check is not a tautology, because a
tautological reimplementation and a genuine check emit the same bytes.  So the
bench also asserts statically that the recompute expression never reads the
field under test.

Exit: 0 if no mutation was missed and the static check passed, else 1.
"""
import os
import re
import subprocess
import sys

SRC = "/home/zhourui/steer3d_bpath/recomp_p.py"
WORK = "/home/zhourui/steer3d_bpath/mut_recomp_p"
PY = "/home/zhourui/miniconda3/envs/easysteer/bin/python"

# (name, [(needle, replacement), ...], kind)
#   kind "data"      : expected to change token counts -> must go red
#   kind "gate"      : expected to neuter the verdict  -> must be exposed
#   kind "tau"       : expected to be bench-blind      -> UNPROVABLE
#   kind "cosmetic"  : display only, cross-checked     -> must go red (rc 3)
#   kind "paired"    : data mutation + gate mutation; the pairing is what
#                      gives the gate mutation any discriminating power
MUTATIONS = [
    ("M1_truncate_cti",
     [("recomp = len(tok(cti, add_special_tokens=False).input_ids)",
       "recomp = len(tok(cti[:len(cti) // 2], add_special_tokens=False).input_ids)")],
     "data"),
    ("M2_wrong_field",
     [('sp = r["sidecar_P"]', 'sp = r["top_level_n_prompt_tokens"]')],
     "data"),
    ("M3_off_by_one",
     [("recomp = len(tok(cti, add_special_tokens=False).input_ids)",
       "recomp = len(tok(cti, add_special_tokens=False).input_ids) + 1")],
     "data"),
    ("M4_flag_always_ok",
     [('flag = "OK" if d == 0 else "MISMATCH"', 'flag = "OK"')],
     "unguarded"),
    ("M5_neuter_exit",
     [("return 0 if n_mismatch == 0 else 1", "return 0")],
     "unguarded"),
    ("M6_tau_sidecar_from_recomp",
     [('sp = r["sidecar_P"]', 'sp = r["recomp_P"]')],
     "tau"),
    # Paired: the real dataset has zero mismatches, so a gate mutation alone is
    # invisible on it (run 2 proved that: M4 and M5 both stayed green).  Pair
    # each gate mutation with a data mutation so mismatches exist and the gate
    # mutation has something to fail on.
    ("P1_data_plus_flag_always_ok",
     [("recomp = len(tok(cti, add_special_tokens=False).input_ids)",
       "recomp = len(tok(cti, add_special_tokens=False).input_ids) + 1"),
      ('flag = "OK" if d == 0 else "MISMATCH"', 'flag = "OK"')],
     "paired"),
    ("P2_data_plus_neuter_exit",
     [("recomp = len(tok(cti, add_special_tokens=False).input_ids)",
       "recomp = len(tok(cti, add_special_tokens=False).input_ids) + 1"),
      ("return 0 if n_mismatch == 0 else 1", "return 0")],
     "paired"),
]

RECOMPUTE_RE = re.compile(r"^\s*recomp\s*=", re.M)
FORBIDDEN = ("prompt_tokens", "sidecar_P", "n_prompt_tokens")


def static_independence(src_text):
    """The recompute side must not read the quantity under test."""
    body = []
    for line in src_text.splitlines():
        if RECOMPUTE_RE.match(line):
            body.append(line)
    if not body:
        return False, "no recomp= assignment found"
    blob = "\n".join(body)
    hits = [f for f in FORBIDDEN if f in blob]
    if hits:
        return False, "recompute reads field(s) under test: %s" % ",".join(hits)
    return True, "recompute reads only cti + tokenizer (%d line(s))" % len(body)


def parse_total(body):
    for s in body.splitlines():
        if s.startswith("total="):
            parts = dict(p.split("=", 1) for p in s.split() if "=" in p)
            try:
                return int(parts.get("mismatch", "0"))
            except ValueError:
                return -1
    return -1


def run(path):
    out = path + ".out"
    err = path + ".err"
    with open(out, "wb") as fo, open(err, "wb") as fe:
        proc = subprocess.run([PY, path], stdout=fo, stderr=fe)
    return proc.returncode, os.path.getsize(out), open(
        out, encoding="utf-8", errors="replace").read()


def main():
    if not os.path.isfile(SRC):
        print("PRECOND_FAIL: %s missing" % SRC)
        return 2
    src_text = open(SRC, encoding="utf-8").read()
    src_lines = src_text.splitlines(keepends=True)
    os.makedirs(WORK, exist_ok=True)

    ok_static, static_msg = static_independence(src_text)
    print("STATIC_INDEPENDENCE: %s -- %s" % ("ok" if ok_static else "FAIL",
                                             static_msg))
    print("")

    rc0, nbytes0, body0 = run(SRC)
    base_ok = (rc0 == 0 and nbytes0 > 0 and "INTEGRITY: counted_all=True"
               in body0)
    print("BASELINE\t%s\trc=%d\tbytes=%d\tINTEGRITY_ok=%s"
          % ("green" if base_ok else "NOT_GREEN", rc0, nbytes0,
             "INTEGRITY: counted_all=True" in body0))
    print("")

    rows = []
    n_caught = 0
    n_neutered = 0
    n_unprovable = 0
    n_invisible = 0
    n_bad = 0

    for name, subs, kind in MUTATIONS:
        mutated = list(src_lines)
        bad_anchor = None
        for needle, repl in subs:
            hits = [i for i, s in enumerate(mutated) if needle in s]
            if len(hits) != 1:
                bad_anchor = "%s hits=%d" % (needle[:40], len(hits))
                break
            mutated[hits[0]] = mutated[hits[0]].replace(needle, repl)
        if bad_anchor:
            rows.append("%s\tANCHOR_BAD\tn/a\t%s" % (name, bad_anchor))
            n_bad += 1
            continue
        mpath = os.path.join(WORK, "%s.py" % name)
        with open(mpath, "w", encoding="utf-8") as fh:
            fh.writelines(mutated)

        rc, nbytes, body = run(mpath)
        mism = parse_total(body)
        if nbytes == 0 or mism < 0:
            rows.append("%s\tCRASHED\trc=%d\tbytes=%d\tno_total_line" % (
                name, rc, nbytes))
            n_bad += 1
            continue

        if kind == "tau":
            # Blind by construction: artifact matches a genuine pass.
            rows.append("%s\tUNPROVABLE\trc=%d\tmismatch=%d\tbench cannot "
                        "distinguish this from a real pass" % (name, rc, mism))
            n_unprovable += 1
            continue

        if kind == "unguarded":
            # Isolated gate mutation on a dataset with zero mismatches.  It is
            # indistinguishable from an honest pass here, so NOT being caught
            # is the expected result and says nothing about the check.  Its
            # guarded counterpart (paired with a data mutation) is the real
            # test; see P1 / P2.  Counting these as misses would blame the
            # check for the bench's choice of dataset.
            if rc == 0 and mism == 0:
                rows.append("%s\tINVISIBLE_ON_THIS_DATA\trc=%d\tmismatch=%d\t"
                            "zero-mismatch data cannot expose a gate-only "
                            "mutation; see its P* counterpart" % (
                                name, rc, mism))
                n_invisible += 1
            else:
                rows.append("%s\tUNEXPECTED\trc=%d\tmismatch=%d\tan isolated "
                            "gate mutation changed the verdict on "
                            "zero-mismatch data" % (name, rc, mism))
                n_bad += 1
            continue

        if rc != 0 and mism > 0:
            rows.append("%s\tcaught\trc=%d\tmismatch=%d" % (name, rc, mism))
            n_caught += 1
        elif rc == 0 and mism > 0:
            rows.append("%s\tGATE_NEUTERED\trc=%d\tmismatch=%d\texit code "
                        "lies; artifact shows real mismatches" % (
                            name, rc, mism))
            n_neutered += 1
        else:
            rows.append("%s\tMISSED\trc=%d\tmismatch=%d" % (name, rc, mism))
            n_bad += 1

    for r in rows:
        print(r)
    print("")
    ok = base_ok and ok_static and n_bad == 0
    print("RESULT: caught=%d gate_neutered=%d unprovable=%d "
          "invisible_on_this_data=%d bad=%d baseline_green=%s static_ok=%s"
          % (n_caught, n_neutered, n_unprovable, n_invisible, n_bad,
             base_ok, ok_static))
    if n_neutered:
        print("NOTE: a neutered gate is a bench success only in the sense "
              "that the bench SAW it; the mutant script itself is defective.")
    with open(os.path.join(WORK, "results.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(rows) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
