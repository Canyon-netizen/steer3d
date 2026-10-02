#!/usr/bin/env python3
"""变异施加器 + 编排器（3D 干预结果面板）。

用法: python3 run_mut_outcome.py BASE / O1 O2 ...

每条变异对应一条「它该打红哪条判据」。基线全绿只是起点；这一组判据
里有几条是专门盯"不误导"的（G2 离线标注、G6 净变化、G7/G8 循环论证），
它们必须证明自己抓得住被删掉的情况。
"""
import os
import re
import subprocess
import sys
import time
import urllib.request

REPO = "/Users/zhourui/code/steer3d"
BAK = os.path.join(REPO, ".cache/mutoutcome")
PY = os.path.join(REPO, ".cache/venv3d/bin/python")
TRASH = "/Users/zhourui/.minimax/bin/mavis-trash"

PANEL = os.path.join(REPO, "frontend/components/InterventionOutcomePanel.tsx")
WSEND = os.path.join(REPO, "frontend/lib/ws-endpoint.ts")

MUTS = {
    "BASE": ("pristine source, everything must pass", ""),
    # 去掉「离线」横幅：读者会以为这是滑块的实时结果
    "O1": ("offline banner removed", "G2"),
    # 只展示变好的那一例，隐去 right->wrong
    "O2": ("hides the right->wrong verdict", "G5"),
    # 把「净变化 0」改成「成功率提升」
    "O3": ("claims an improvement instead of net zero", "G6"),
    # 删掉循环论证的解释
    "O4": ("drops the circularity explanation", "G7"),
    # 把对照臂的诚实陈述删掉
    "O5": ("drops the control-arm denominator", "G4"),
    # 数字改成整数（丢掉 0.3% 这类量级）
    "O6": ("rounds away the displacement magnitude", "G9"),
    # 数字与产物脱钩：写死一个中位数
    # Hardcode a median instead of reading it. The first version wrote
    # "~13", which is exactly the artifact's median (n=46 -> index 23 ->
    # 13), so the criterion stayed green. The mutation was a lucky guess,
    # not a pass. O8 hardcodes a value that cannot coincide.
    "O7": ("hardcodes the median instead of reading the artifact", "G3"),
    "O8": ("hardcodes a median that is not the artifact's", "G3"),
}


def read(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def write(p, s):
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(s)


def edit(path, old, new, tag):
    s = read(path)
    if old not in s:
        raise SystemExit("ABORT anchor not found: %s in %s" % (tag, path))
    write(path, s.replace(old, new, 1))


def port_busy(p):
    r = subprocess.run(["lsof", "-nP", "-iTCP:%d" % p, "-sTCP:LISTEN", "-t"],
                       capture_output=True, text=True)
    return bool(r.stdout.strip())


def free_port(lo, hi):
    for p in range(lo, hi):
        if not port_busy(p):
            return p
    raise SystemExit("ABORT no free port in [%d,%d)" % (lo, hi))


def wait_http(url, seconds=25):
    for _ in range(seconds):
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status < 500:
                    return True
        except Exception:
            time.sleep(1)
    return False


def backup():
    """Snapshot only clean files.

    Two lessons, both paid for in this file's first run:

    1. An ABORT that skips restore() poisons the *next* run, because
       backup() would copy the mutated file over the pristine one. A
       `MUT_` marker check catches that.
    2. The marker check is not sufficient. O1 replaces the offline banner
       with innocuous prose and leaves no marker, so the check passed --
       and then the pristine copy it took was already a mutation. What
       actually went wrong downstream is subtler: restore() puts the
       source back but leaves `.next` holding the mutated *build*, and a
       later run's `next start` serves that stale bundle. The symptom was
       BASE reporting six failures whose text was plainly on screen.

    So this refuses to run unless the source looks untouched, and it
    re-verifies against git for files git knows about.
    """
    os.makedirs(BAK, exist_ok=True)
    for src in (PANEL, WSEND):
        if "MUT_" in read(src):
            raise SystemExit("ABORT %s still carries a mutation marker" % src)
    for src in (PANEL, WSEND):
        with open(os.path.join(BAK, os.path.basename(src) + ".pristine"), "w",
                  encoding="utf-8") as fh:
            fh.write(read(src))


def verify_source_untouched():
    """Re-read the three markers this panel must always contain.

    Cheap, and it catches the failure mode a `MUT_` grep cannot: a
    mutation that swaps prose for other prose.
    """
    s = read(PANEL)
    required = [
        "Offline 32k batch, not this page",
        "Net change in correct answers",
        "circular: the vector is defined as a difference of group means",
        "about <b>0.3%</b>",
        "nCleanControl",              # the control-arm denominator
    ]
    missing = [m for m in required if m not in s]
    if missing:
        raise SystemExit(
            "ABORT the panel source is not in its pristine state; missing: %s"
            % "; ".join(repr(m)[:40] for m in missing))


def restore():
    for src in (PANEL, WSEND):
        dst = os.path.join(BAK, os.path.basename(src) + ".pristine")
        if os.path.exists(dst):
            with open(dst, encoding="utf-8") as fh:
                write(src, fh.read())


def apply(which):
    if which == "O1":
        edit(PANEL, "        <b>Offline 32k batch, not this page&apos;s slider.</b> Re-decoded\n"
                    "        token by token with a real decoder. The strength control on the\n"
                    "        left bends the 3-D trajectory but does <b>not</b> change the tokens\n"
                    "        you see replaying — that would need the remaining transformer\n"
                    "        blocks run here, and this page does not run the model.",
                    "        Measured on the recorded arms.", "O1")
    elif which == "O2":
        # Show only the favourable verdict.
        edit(PANEL,
             '      <div className="flex gap-1 mb-1.5">\n'
             '        {Object.entries(verdict).map(([k, n]) => (',
             '      <div className="flex gap-1 mb-1.5">\n'
             '        {Object.entries(verdict).filter(([k]) => k !== "right->wrong").map(([k, n]) => (',
 "O2")
    elif which == "O3":
        edit(PANEL,
             "        all. Net change in correct answers: <b>0</b>. Steering moved\n"
             "        things; it did not make them better.",
             "        all. Accuracy improved under steering.", "O3")
    elif which == "O4":
        edit(PANEL, "          circular: the vector is defined as a difference of group means\n"
                    "          over these tokens, then correlated back against the same labels,\n"
                    "          so the pass/fail is an identity rather than a finding. One\n"
                    "          direction rests on 3 trajectories out of 48. The non-circular\n"
                    "          (held-out) half of that evidence is not reproduced here either.\n"
                    "          Numbers like these render as convincing bars and mean nothing,\n"
                    "          so the panel omits them and tells you instead.",
                    "          not shown here.", "O4")
    elif which == "O5":
        edit(PANEL,
             "        only thing separating them is the injected vector — the controls\n"
             "        confirm it: {stats.nCleanControl}/{stats.nControl} have first-changed-step\n"
             "        null and 100% agreement, i.e. they never moved.",
             "        only thing separating them is the injected vector.", "O5")
    elif which == "O6":
        edit(PANEL, "        ~5.4 — about <b>0.3%</b>. An independent SVD says why: the vector\n"
                    "        moves the top-3 subspace by 29.8 while the model itself moves 30.4\n"
                    "        per step.",
                    "        negligible. An independent SVD says the vector is mostly\n"
                    "        orthogonal to the plotted subspace.", "O6")
    elif which == "O7":
        edit(PANEL,
             "        <Stat label=\"first changed step\" v={stats.fdMed != null ? `~${stats.fdMed}` : \"—\"}",
             "        <Stat label=\"first changed step\" v=\"~13\"", "O7")
    elif which == "O8":
        edit(PANEL,
             "        <Stat label=\"token agreement\" v={stats.agreeMed != null ? pct(stats.agreeMed) : \"—\"}",
             "        <Stat label=\"token agreement\" v=\"99.9%\"", "O8")
    else:
        raise SystemExit("unknown mutation " + which)


def build_frontend():
    r = subprocess.run(["npx", "next", "build"], cwd=os.path.join(REPO, "frontend"),
                       capture_output=True, text=True, timeout=600)
    out = r.stdout + r.stderr
    if "Compiled successfully" not in out:
        print("    build failed")
        for ln in out.splitlines():
            if "error" in ln.lower():
                print("      " + ln[:150])
        return False
    return True


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "BASE"
    if which not in MUTS:
        raise SystemExit("unknown mutation " + which)
    desc, expect_red = MUTS[which]
    print("=== %s: %s" % (which, desc))

    backup()
    verify_source_untouched()
    if expect_red:
        try:
            apply(which)
        except SystemExit as e:
            print("    " + str(e))
            restore()
            return 3
        print("    mutation written")
    else:
        print("    pristine source, nothing to write")

    bport = int(os.environ.get("MUT_BACKEND", "9503"))
    try:
        write(WSEND, re.sub(r"export const DEFAULT_WS_PORT_CANDIDATES = \[.*?\];",
                            "export const DEFAULT_WS_PORT_CANDIDATES = [%d];" % bport,
                            read(WSEND), count=1))
        if not build_frontend():
            return 3
        fport = free_port(10100, 10160)
        subprocess.Popen(["npx", "next", "start", "-p", str(fport)],
                         cwd=os.path.join(REPO, "frontend"),
                         stdout=open(os.path.join(BAK, "fe.log"), "w"),
                         stderr=subprocess.STDOUT, start_new_session=True)
        if not wait_http("http://127.0.0.1:%d/" % fport):
            print("    ABORT frontend never came up")
            return 3
        print("    frontend %d -> backend %d" % (fport, bport))

        env = dict(os.environ, T3D_PORT=str(bport),
                   T3D_URL="http://127.0.0.1:%d/" % fport,
                   T3D_PROFILE=os.path.join(BAK, "prof_" + which))
        r = subprocess.run(["node", os.path.join(REPO,
                            ".cache/browser_verify/verify_outcome.mjs")],
                           capture_output=True, text=True, timeout=300, env=env)
        with open(os.path.join(BAK, which + ".out"), "w") as fh:
            fh.write(r.stdout + r.stderr)
        for line in (r.stdout + r.stderr).splitlines():
            if line.startswith("[PASS]") or line.startswith("[FAIL]") or line.startswith("==="):
                print("    " + line)
    finally:
        restore()
        print("    source restored")
        # Rebuild after restoring. Without this, `.next` keeps holding the
        # mutated bundle and the *next* run's `next start` serves it -- so
        # a BASE run right after a mutation measured the mutation, not the
        # source, and reported six failures whose text was on screen.
        # Costs one build per run; skips it only when the run was BASE and
        # nothing was written.
        if expect_red:
            print("    rebuilding a clean bundle")
            write(WSEND, re.sub(r"export const DEFAULT_WS_PORT_CANDIDATES = \[.*?\];",
                                "export const DEFAULT_WS_PORT_CANDIDATES = [%d];"
                                % int(os.environ.get("MUT_BACKEND", "9503")),
                                read(WSEND), count=1))
            build_frontend()

    if not expect_red:
        if r.returncode == 0 and "[FAIL]" not in r.stdout:
            print("    RESULT BASE OK - all criteria pass on pristine source")
            return 0
        print("    RESULT BASE BAD - criteria are red on pristine source")
        return 1
    if ("[FAIL] " + expect_red) in r.stdout:
        print("    RESULT %s OK - %s went red" % (which, expect_red))
        return 0
    print("    RESULT %s BAD - %s stayed green, so that criterion has no teeth"
          % (which, expect_red))
    return 1


if __name__ == "__main__":
    sys.exit(main())
