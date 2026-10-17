#!/usr/bin/env python
"""Mutation bench for arm_verdict.py (revision 244.9).

A script that computes p-values is exactly the kind of thing that can be
silently wrong: if it always prints a small p, nothing looks broken.  So the
bench must show each of its decisions can change.

Unlike the 244.7 bench on a tautology-shaped check, this one CAN discriminate,
because a wrong formula produces a *different number*, not the same artifact.

Mutations are chosen per guard:
  data / gate / arithmetic / tautology-reminder

Rules the bench follows (from 244.7 and 244.8):
  - assert the anchor is unique before running; a no-op mutant is INVALID, not
    a miss (that mistake already cost one round in 244.7)
  - do not trust rc alone: read the artifact and check it says what changed
  - a mutation is "caught" when the mutant's output DIFFERS from baseline in
    the specific way the guard is supposed to prevent

Exit: 0 if every mutation was caught; 1 otherwise.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "arm_verdict.py")
READER = os.path.join(HERE, "..", "mutbak", "r227_kcurve.py")
W_LOG = os.path.join(HERE, "r244_warm.norm.log")
W_ST = os.path.join(HERE, "r244_warm_status.txt")
R_LOG = os.path.join(HERE, "rand_sweep.log")
R_ST = os.path.join(HERE, "..", "r240", "r227_status.txt")

# ---- group A: script mutations on GOOD data (arithmetic / invariance) ----
# (name, needle, replacement, must_do)
#   no_change_expected: the invariant must survive the mutant
#   p_grows           : the mutant must move the reported p
SCRIPT_MUTATIONS = [
    ("A1_fisher_drop_slop",
     "if px <= p_obs * (1 + 1e-12):",
     "if px <= p_obs:",
     "no_change_expected"),
    ("A2_fisher_ignore_filter",
     "if px <= p_obs * (1 + 1e-12):",
     "if True:",
     "p_grows"),
    ("A3_swap_fisher_args",
     "fisher_exact_two_sided(wpos, wneg, rpos, rneg)",
     "fisher_exact_two_sided(rpos, rneg, wpos, wneg)",
     "no_change_expected"),
    ("A4_report_pos_as_neg",
     "% (wpos, wneg, wtie, wp, wlb, wz))",
     "% (wneg, wpos, wtie, wp, wlb, wz))",
     "swapped"),
]

# ---- group B: FIXTURE violations on the GOOD script (gate power) ----
# ⚖⚖ A guard can only be shown to fire on data that violates it.  Running a
# ⚖  guard-removing mutation against clean data is the same mistake as asking a
# ⚖  green gate to prove it can go red: 244.7 called it INVISIBLE_ON_THIS_DATA.
# ⚖⇒ So each guard gets a deliberately broken fixture instead.
# (name, how to break it, which guard must fire)
# ⚖⚖ 每条夹具都必须让**每一臂各自内部自洽**，只有两臂之间不同。
# ⚖ 理由：第一版夹具只改了 rand 的一格，于是被**读数器自己的**守卫先拦下
# ⚖   （「曲线里混了多个 pos_frac」/「混了多个臂」）—— 测到的是读数器，
# ⚖   不是本脚本的跨臂守卫。跨臂守卫只在「两臂各自自洽但彼此不同」时才有活可干。
FIXTURES = [
    ("B1_param_mismatch_between_arms", "param", "HARD_FAIL 扫描参数两臂不一致"),
    ("B2_status_no_alldone", "alldone", "无 ALLDONE 行"),
    ("B3_status_short", "short", ""),
    ("B4_arm_same_both_sides", "arm", "两臂的 --arm 相同"),
]


def run(script, out):
    with open(out, "wb") as fo, open(out + ".err", "wb") as fe:
        proc = subprocess.run(
            [sys.executable, script, "--reader", READER,
             "--w-log", W_LOG, "--w-status", W_ST,
             "--rand-log", R_LOG, "--rand-status", R_ST,
             "--expect-cells", "137"], stdout=fo, stderr=fe)
    nbytes = os.path.getsize(out)
    return proc.returncode, nbytes, open(out, encoding="utf-8",
                                         errors="replace").read()


def fisher_p(body):
    for line in body.splitlines():
        if line.startswith("  Fisher two-sided across arms:"):
            return line.split("p=")[1].strip()
    return None


def make_fixture(kind, tag):
    """Write a deliberately broken copy of a fixture.  Returns the path."""
    import re as _re
    # slot: which argument the fixture replaces
    slot = {"param": "log", "arm": "log", "alldone": "status",
            "short": "status", "same": "same"}[kind]
    src = R_ST if slot == "status" else R_LOG
    text = open(src, encoding="utf-8", errors="replace").read()
    if kind == "param":
        # EVERY cell, so the rand arm stays internally consistent and only the
        # cross-arm comparison can notice.
        text = text.replace('"pos_frac": 0.5', '"pos_frac": 0.25')
        print("  fixture param: pos_frac replacements = %d"
              % text.count('"pos_frac": 0.25'))
    elif kind == "arm":
        # relabel the whole rand arm as w: internally consistent, but then the
        # two inputs are no longer two arms.
        text = text.replace('"arm": "rand"', '"arm": "w"')
        print("  fixture arm: relabels = %d" % text.count('"arm": "w"'))
    elif kind == "alldone":
        text = _re.sub(r"^ALLDONE.*$", "", text, flags=_re.M)
    elif kind == "short":
        lines = text.split("\n")
        text = "\n".join(lines[:40])
    out = os.path.join(HERE, "fix_%s_%s" % (kind, tag))
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(text)
    return out, slot


def run_with(script, rand_log, rand_st, out):
    with open(out, "wb") as fo, open(out + ".err", "wb") as fe:
        proc = subprocess.run(
            [sys.executable, script, "--reader", READER,
             "--w-log", W_LOG, "--w-status", W_ST,
             "--rand-log", rand_log, "--rand-status", rand_st,
             "--expect-cells", "137"], stdout=fo, stderr=fe)
    combined = open(out, encoding="utf-8", errors="replace").read() + \
        open(out + ".err", encoding="utf-8", errors="replace").read()
    return proc.returncode, combined


def main():
    if not os.path.isfile(TARGET):
        print("PRECOND_FAIL: %s missing" % TARGET)
        return 2
    src = open(TARGET, encoding="utf-8").read()
    lines = src.splitlines(keepends=True)

    base_out = os.path.join(HERE, "verdict_baseline.out")
    rc0, body0 = run_with(TARGET, R_LOG, R_ST, base_out)
    if rc0 != 0 or len(body0) < 100:
        print("PRECOND_FAIL: baseline rc=%d len=%d" % (rc0, len(body0)))
        print("  a broken baseline makes every mutant meaningless")
        return 2
    base_fisher = fisher_p(body0)
    print("BASELINE rc=0 fisher=%s" % base_fisher)
    print("")
    print("--- A: script mutations on good data (arithmetic / invariance) ---")

    n_caught = 0
    n_invalid = 0
    n_missed = 0
    for name, needle, repl, must_do in SCRIPT_MUTATIONS:
        hits = [i for i, s in enumerate(lines) if needle in s]
        if len(hits) != 1:
            print("%s\tANCHOR_BAD\thits=%d" % (name, len(hits)))
            n_invalid += 1
            continue
        mut = list(lines)
        mut[hits[0]] = mut[hits[0]].replace(needle, repl)
        mpath = os.path.join(HERE, "mut_%s.py" % name)
        with open(mpath, "w", encoding="utf-8") as fh:
            fh.writelines(mut)
        rc, body = run_with(mpath, R_LOG, R_ST,
                            os.path.join(HERE, "mut_%s.out" % name))
        if must_do == "no_change_expected":
            same = (body == body0)
            ok = same
            note = "invariant preserved" if same else "INVARIANT BROKEN"
        elif must_do == "p_grows":
            p = fisher_p(body)
            ok = p is not None and base_fisher is not None and \
                float(p) > float(base_fisher)
            note = "fisher=%s base=%s" % (p, base_fisher)
        else:  # swapped
            wline = [x for x in body.splitlines() if x.startswith("  w    : pos=")]
            ok = bool(wline) and wline[0].split()[2].split("=")[1] == "1"
            note = wline[0] if wline else "no w line"
        print("%s\t%s\trc=%d\t%s" % (name, "caught" if ok else "MISSED",
                                        rc, note))
        if ok:
            n_caught += 1
        else:
            n_missed += 1

    print("")
    print("--- B: fixture violations on the good script (gate power) ---")
    for name, kind, expect_msg in FIXTURES:
        fixture, slot = make_fixture(kind, name)
        if slot == "status":
            rc, body = run_with(TARGET, R_LOG, fixture,
                                os.path.join(HERE, "fix_%s.out" % name))
        else:
            rc, body = run_with(TARGET, fixture, R_ST,
                                os.path.join(HERE, "fix_%s.out" % name))
        stopped = rc != 0 or "HARD_FAIL" in body or "PRECOND_FAIL" in body
        named = True if not expect_msg else (expect_msg in body)
        ok = stopped and named
        note = "rc=%d named=%s" % (rc, named)
        if expect_msg and not named:
            note += " expected_msg=%r" % expect_msg
        print("%s\t%s\t%s" % (name, "caught" if ok else "MISSED", note))
        if ok:
            n_caught += 1
        else:
            n_missed += 1

    print("")
    print("RESULT: caught=%d missed=%d invalid=%d" % (n_caught, n_missed,
                                                      n_invalid))
    return 0 if n_missed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
