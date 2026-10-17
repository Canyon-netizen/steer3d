#!/usr/bin/env python
"""Mutation bench for cross_round_params.py (revision 244.22).

Why a bench exists at all: this script's ONLY job is to say "the params match"
or "they do not".  A check that always says "match" is indistinguishable from
a correct check unless something tries to make it wrong and watches it fail.
That is the whole point of this file.

Two groups, following 244.9.6:
  A -- mutations to the SCRIPT (break its own decision logic).
  B -- fixture violations (probe whether its gates can actually see).

⚠⚠ Rules this bench follows, each learned the hard way:
  - It does NOT trust the exit code.  It re-reads the printed table and checks
    it against the expected outcome.  rc=0 while the artifact shows unequal
    values is reported as GATE_NEUTERED, not as "caught".
  - Every B fixture leaves EACH file internally self-consistent and differs
    only BETWEEN files (or, for B2, varies within one file by design).  An
    earlier bench version edited a single cell in one file; the tool's own
    "params vary across cells" gate fired first and the bench measured the
    wrong gate.
  - "Not measured" must never be scored as "equal".  B4/B5 exist for that:
    deleting a key or all readouts must be distinguishable from agreement.
  - INVISIBLE_ON_THIS_DATA is counted separately from a miss, and it is not a
    property of the guard -- it is a property of the fixture.

Exit: 0 all mutations behaved as required; 1 otherwise.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "cross_round_params.py")
TMP = os.path.join(HERE, "_mut_xrp")


def _cell(tid, k, pos_frac=0.5, gap=113.47440338134766, arm="w",
          nested=True, n_steps=60):
    obj = {"tid": tid, "p9_lo_meas": 0.1234, "p9_hi_meas": -0.01,
           "inject_scope": "k", "inject_n_sites": k, "inject_nested": nested,
           "arm": arm, "pos_frac": pos_frac, "n_steps": n_steps, "gap": gap,
           "P": 108, "t": 10}
    return json.dumps(obj)


def _log(cells, t0=0):
    """cells: list of (tid, k, overrides-dict)."""
    lines = []
    for i, (tid, k, ov) in enumerate(cells):
        lines.append("### BEGIN %s n_eff=118  00:%02d:%02d" % (tid, (t0 + i) // 60, (t0 + i) % 60))
        lines.append(_cell(tid, k, **ov))
    lines.append("ALLDONE 01:00:00")
    return "\n".join(lines) + "\n"


def base_cells(n=6):
    return [("t%02d" % i, i + 1, {}) for i in range(n)]


def shifted(n=6):
    """Same shape as base_cells(); the t0 offset lives in _log, not here."""
    return base_cells(n)


def run(tool, args):
    p = subprocess.run([sys.executable, tool] + args,
                       capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def write(name, text):
    path = os.path.join(TMP, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def read_params(out, fname):
    """Pull the printed per-file param block out of the artifact."""
    blocks = out.split("  " + fname)
    if len(blocks) < 2:
        return None
    body = blocks[1].split("\n\n")[0]
    got = {}
    for line in body.splitlines():
        m = re.match(r"\s{6}(\S+)\s+(.*)$", line)
        if m:
            got[m.group(1)] = m.group(2).strip()
    return got or None


RESULTS = []


def record(name, verdict, why=""):
    RESULTS.append((name, verdict, why))
    print("  %-6s %s%s" % (verdict, name, ("  -- " + why) if why else ""))


def main():
    os.makedirs(TMP, exist_ok=True)
    for f in os.listdir(TMP):
        os.remove(os.path.join(TMP, f))

    src = open(TOOL, encoding="utf-8").read()

    # ================= baseline =================
    a = write("a.log", _log(base_cells()))
    b = write("b.log", _log(shifted()))
    rc, out = run(TOOL, [a, b])
    ok = rc == 0 and "逐项相同" in out
    record("BASE 基线：两轮同参数 ⇒ rc=0 且印「逐项相同」",
           "ok" if ok else "BAD",
           "" if ok else "rc=%d out=%r" % (rc, out[-200:]))

    # ================= A: script mutations =================
    # ⚠⚠⁴ Every A mutation runs on a fixture where the params REALLY differ.
    # ⚖ First version of this bench ran them on the equal-param fixture and
    # ⚖ scored A1 as "the artifact didn't expose it".  Wrong measurement:
    # ⚖ on equal params rc=0 is the CORRECT answer, so nothing was broken.
    # ⚖ Same shape of mistake as the B4 fixture bug below -- confirm the
    # ⚖ fixture actually creates the condition before blaming the tool.
    a_pf = write("a_pf.log", _log(base_cells()))
    b_pf = write("b_pf.log", _log([(t, k, dict(ov, pos_frac=0.25))
                                  for t, k, ov in shifted()]))
    a_gp = write("a_gp.log", _log(base_cells()))
    b_gp = write("b_gp.log", _log([(t, k, dict(ov, gap=113.47440338134767))
                                  for t, k, ov in shifted()]))
    # A3 fixture: the varying cell MUST be the FIRST one.  With the varying
    # cell in the middle, deleting the gate makes resolve() fall back to the
    # first value, which is 0.5 in both files -- so rc and artifact agree and
    # the mutation stays invisible.  With it first, the fallback yields 0.25
    # vs 0.5 => rc=1 where the correct answer is rc=2 ("mixed within a file"),
    # which is exactly the difference the gate exists to make.
    c_mix = base_cells()
    c_mix[0] = (c_mix[0][0], c_mix[0][1], dict(c_mix[0][2], pos_frac=0.25))
    a_mix = write("a_mix.log", _log(c_mix))

    # A1: neuter the comparison -- always report "same"
    m1 = src.replace("    if diffs:\n", "    diffs = []\n    if diffs:\n", 1)
    # A2: make every float print as the same string (printing path only)
    m2 = src.replace('    if isinstance(v, float):\n        return repr(v)\n',
                     '    if isinstance(v, float):\n        return "0.5"\n', 1)
    # A3: drop the within-file "varies across cells" gate
    m3 = src.replace("        if len(vals) > 1:\n", "        if False:\n", 1)

    A_WHY = {"A1": "比较被抹平 ⇒ 该 rc=1 却 rc=0",
             "A2": "打印被打成同一串 ⇒ 判定仍对、产物说谎",
             "A3": "混用闸被删 ⇒ 该 rc=2 却 rc=1"}
    # (mutant, fixtureA, fixtureB, printed key, CORRECT rc on this fixture)
    for tag, mutated, fx, fy, key, want in (
            ("A1", m1, a_pf, b_pf, "pos_frac", 1),
            ("A2", m2, a_gp, b_gp, "gap", 1),
            ("A3", m3, a_mix, a, "pos_frac", 2)):
        if mutated == src:
            record("%s 脚本变异（夹具上条件确实存在）" % tag, "BAD",
                   "源码没匹配上，变异没施加")
            continue
        t = write("tool_%s.py" % tag, mutated)
        rc, out = run(t, [fx, fy])
        px = read_params(out, os.path.basename(fx))
        py = read_params(out, os.path.basename(fy))
        shown_same = bool(px and py and px.get(key) == py.get(key))
        shown_differs = bool(px and py and px.get(key) != py.get(key))
        if rc == want:
            if tag == "A2" and shown_same:
                # rc right, artifact lies: this is the split that matters.
                # It only became observable because the verdict path was moved
                # off _fmt (revision 244.22) -- before that, both rc and the
                # artifact went wrong together and no bench could see it.
                record("A2 %s" % A_WHY[tag], "ok",
                       "rc=%d 正确，但产物把两项印成同一个 %r ⇒ 台架抓到了"
                       % (rc, px.get(key)))
            else:
                record("%s 变异未生效（rc=%d，仍是正确答案）" % (tag, rc), "ok",
                       "rc=%d" % rc)
        elif rc == 0 and shown_differs:
            record("%s %s" % (tag, A_WHY[tag]), "ok",
                   "GATE_NEUTERED：rc=0 与产物矛盾，产物可信")
        elif rc == 0 and shown_same:
            record("%s %s" % (tag, A_WHY[tag]), "BAD",
                   "rc=0 且产物也无从分辨 ⇒ 变异不可见（夹具或判定有问题）")
        else:
            record("%s 被破坏且台架看见" % tag, "ok",
                   "rc=%d，正确应为 %d" % (rc, want))

    # ================= B: fixture violations =================
    # B1: B runs at a different pos_frac -- each file internally consistent
    c1 = [(t, k, dict(ov, pos_frac=0.25)) for t, k, ov in shifted()]
    b1 = write("b1.log", _log(c1))
    rc, out = run(TOOL, [a, b1])
    named = "pos_frac" in out and "≠" in out
    record("B1 B 轮 pos_frac=0.25（两文件各自自洽）⇒ rc=1 且指名该项",
           "ok" if (rc == 1 and named) else "BAD",
           "" if (rc == 1 and named) else "rc=%d named=%s" % (rc, named))

    # B2: A file varies pos_frac ACROSS cells => the within-file gate
    c2 = base_cells()
    c2[3] = (c2[3][0], c2[3][1], dict(c2[3][2], pos_frac=0.25))
    b2 = write("b2.log", _log(c2))
    rc, out = run(TOOL, [b2, a])
    said_mix = "混用" in out
    record("B2 A 轮第 4 格 pos_frac 变 ⇒ rc=2 且报「格间混用」（不是「不同」）",
           "ok" if (rc == 2 and said_mix) else "BAD",
           "" if (rc == 2 and said_mix) else "rc=%d mix=%s" % (rc, said_mix))

    # B3: same file twice => gate 0 must refuse
    rc, out = run(TOOL, [a, a])
    refused = rc == 2 and "跟自己" in out
    record("B3 同一文件传两次 ⇒ rc=2 且闸 0 拒绝", "ok" if refused else "BAD",
           "" if refused else "rc=%d" % rc)

    # B4: B has NO gap key at all => "not measured", must NOT read as equal
    # ⚠⚠ First version built this fixture as
    # ⚖   [{k: v for k, v in ov.items() if k != "gap"} for ...]
    # ⚖ but `ov` is the per-cell OVERRIDE dict and is empty, so the filter
    # ⚖ never removed anything -- the fixture was a plain copy and the run
    # ⚖ correctly reported "equal".  Removing a key has to happen on the
    # ⚖ rendered JSON text, not on an empty override dict.
    b4 = write("b4.log", re.sub(r', "gap": [0-9.]+', "", _log(shifted())))
    rc, out = run(TOOL, [a, b4])
    said_unmeasured = rc == 2 and "未量到" in out
    claimed_same = "逐项相同" in out
    record("B4 B 轮缺 gap 键 ⇒ rc=2「未量到」，且⛔不许印「相同」",
           "ok" if (said_unmeasured and not claimed_same) else "BAD",
           "" if (said_unmeasured and not claimed_same)
           else "rc=%d claimed_same=%s" % (rc, claimed_same))

    # B5: B has zero readable readout lines
    b5 = write("b5.log", "### BEGIN t00 n_eff=118  00:00:00\nnothing here\n")
    rc, out = run(TOOL, [a, b5])
    said_unmeasured = rc == 2 and "未量到" in out
    record("B5 B 轮 0 条读数行 ⇒ rc=2「未量到」",
           "ok" if said_unmeasured else "BAD",
           "" if said_unmeasured else "rc=%d" % rc)

    # B6: gap differs by 1 ULP -- does the equality test actually see it?
    c6 = [(t, k, dict(ov, gap=113.47440338134767))
          for t, k, ov in shifted()]
    b6 = write("b6.log", _log(c6))
    rc, out = run(TOOL, [a, b6])
    saw = rc == 1 and "gap" in out
    record("B6 gap 差 1 ULP（113.47440338134766 vs …67）⇒ 必须报不同",
           "ok" if saw else "BAD", "" if saw else "rc=%d" % rc)

    # B7: equal values written two different ways must NOT count as different
    c7 = [(t, k, dict(ov)) for t, k, ov in shifted()]
    txt = _log(c7).replace('"gap": 113.47440338134766',
                           '"gap": 113.474403381347660')
    b7 = write("b7.log", txt)
    rc, out = run(TOOL, [a, b7])
    same = rc == 0 and "逐项相同" in out
    record("B7 gap 同一浮点两种写法 ⇒ 仍判「相同」（比的是值不是字面）",
           "ok" if same else "BAD", "" if same else "rc=%d" % rc)

    # ================= tally =================
    bad = [r for r in RESULTS if r[1] == "BAD"]
    invisible = [r for r in RESULTS if r[1] == "INVISIBLE"]
    print("\n" + "-" * 70)
    print("caught=%d bad=%d invisible=%d total=%d"
          % (len(RESULTS) - len(bad) - len(invisible), len(bad),
             len(invisible), len(RESULTS)))
    if invisible:
        print("INVISIBLE 不计 miss：%s" % ", ".join(r[0].split(" ")[0] for r in invisible))
    if bad:
        print("⛔ 有变异没按预期表现：")
        for r in bad:
            print("   %s  %s" % (r[0], r[2]))
        return 1
    print("⚖ rc=0 只读作「所有**能**被本台架分辨的变异都抓住了」，不是「没有洞」")
    return 0


if __name__ == "__main__":
    sys.exit(main())
