#!/usr/bin/env python3
"""单条变异施加器 + 编排器（轨迹选择器）。

用法: python3 run_mut_picker.py M1

单独成 Python 文件而不是 shell：
前两版都用 bash 写，被两个问题反复咬到 ——
  1. echo 里的全角括号 `（` 被 bash 当成命令替换的一部分，
     于是 "$PORT）" 报 unbound variable。中文注释在 shell 里是陷阱。
  2. sed 改端口列表时转义层层叠加，最后 invalid command code f。

端口探测、启动、还原、判据、汇总全在 Python 里做，没有转义层。
"""
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.request

REPO = "/Users/zhourui/code/steer3d"
BAK = os.path.join(REPO, ".cache/mutpick")
PY = os.path.join(REPO, ".cache/venv3d/bin/python")
TRASH = "/Users/zhourui/.minimax/bin/mavis-trash"

SERVER = os.path.join(REPO, "backend/server.py")
RUNNER = os.path.join(REPO, "backend/core/replay_runner.py")
PANEL = os.path.join(REPO, "frontend/components/ControlPanel.tsx")
WSEND = os.path.join(REPO, "frontend/lib/ws-endpoint.ts")
PROTOCOL = os.path.join(REPO, "backend/core/protocol.py")

# mutation -> (desc, criteria that must go red, expected trajectory count)
# "BASE" is not a mutation: it runs the criteria against pristine source and
# requires everything to pass. Without a baseline, "all green under mutation"
# is indistinguishable from "all green because the criteria are dead".
MUTS = {
    "BASE": ("pristine source, everything must pass", "", 48),
    "M1": ("backend stops reporting trajectories", "E1", 0),
    "M2": ("UI forces the text box", "E1", 48),
    "M3": ("Start sends a hardcoded wrong recording", "E9", 48),
    "M4": ("only half the trajectories are reported", "E2", 24),
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


def probe_trajectories(port):
    """Ask the server how many trajectories it reports.

    Every mutation is checked through this before the criteria run. A
    mutation that never reached the process under test makes every
    criterion pass for the wrong reason, and 'all green' then reads as
    'the criterion has teeth' when it has none.
    """
    code = (
        "import asyncio, json, websockets\n"
        "async def m():\n"
        "    try:\n"
        "        async with websockets.connect('ws://127.0.0.1:%d/ws',"
        " open_timeout=6) as w:\n"
        "            p = json.loads(await asyncio.wait_for(w.recv(), timeout=6))"
        "['payload']\n"
        "            print(len(p.get('trajectories', [])))\n"
        "    except Exception as e:\n"
        "        print('ERR:' + type(e).__name__)\n"
        "asyncio.run(m())\n" % port
    )
    r = subprocess.run([PY, "-c", code], capture_output=True, text=True, timeout=40)
    return r.stdout.strip()


def backup():
    os.makedirs(BAK, exist_ok=True)
    for src in (SERVER, RUNNER, PANEL, WSEND):
        shutil.copy(src, os.path.join(BAK, os.path.basename(src) + ".pristine"))


def restore():
    for src in (SERVER, RUNNER, PANEL, WSEND):
        dst = os.path.join(BAK, os.path.basename(src) + ".pristine")
        if os.path.exists(dst):
            shutil.copy(dst, src)
    for d in ("backend/core/__pycache__", "backend/__pycache__"):
        p = os.path.join(REPO, d)
        if os.path.isdir(p):
            subprocess.run([TRASH, "--", p], capture_output=True)


def apply(which):
    if which == "M1":
        edit(SERVER,
             "            trajectories=list(\n"
             "                (getattr(state.runner, \"describe\", None) or (lambda: []))()\n"
             "            ),",
             "            trajectories=[],  # MUT_NO_TRAJECTORIES", "M1")
    elif which == "M2":
        edit(PANEL,
             "  const pickList = trajectories.length > 0;",
             "  const pickList = false && trajectories.length > 0;"
             "  // MUT_FORCE_TEXTAREA", "M2")
    elif which == "M3":
        # Start ignores the picker and always replays the FIRST recording.
        #
        # The previous version of this mutation replaced `effectivePrompt`
        # with `localPrompt`, and that was an **equivalent mutation**:
        # ControlPanel's onChange writes BOTH setLocalPrompt and setPrompt,
        # so after any user interaction the two are the same string. The
        # backend's _pick() also falls back to records[0] for anything it
        # does not recognise, so the two paths picked the same record. It
        # was untestable by construction -- not a weak criterion, a
        # mutation that broke nothing.
        #
        # Pinning the prompt to a fixed id makes the picker decorative:
        # whatever the user selects, the same recording plays. That is
        # observable, and E9 catches it by comparing the replayed tokens
        # against the npz ground truth for the *selected* id.
        edit(PANEL,
             "      payload: { prompt: effectivePrompt, layer },",
             "      payload: { prompt: trajectories[0].id, layer },"
             "  // MUT_HARDCODED_RECORD", "M3")
    elif which == "M4":
        # `return out` appears three times in this file (discover_records,
        # _load_vocab's caller, describe). The naive replace hit the first
        # one, which describe() never calls, so the mutation was invisible
        # and the probe correctly aborted instead of letting a false green
        # through. Anchor on describe()'s own return.
        s = read(RUNNER)
        i = s.index("    def describe(")
        j = s.index("        return out", i)
        write(RUNNER, s[:j] + "        return out[:24]  # MUT_HALF_TRAJECTORIES"
              + s[j + len("        return out"):])
    else:
        raise SystemExit("unknown mutation " + which)


def build_frontend():
    r = subprocess.run(["npx", "next", "build"], cwd=os.path.join(REPO, "frontend"),
                       capture_output=True, text=True, timeout=600)
    return "Compiled successfully" in (r.stdout + r.stderr)


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "M1"
    if which not in MUTS:
        raise SystemExit("unknown mutation " + which)
    desc, expect_red, expect_traj = MUTS[which]

    print("=== %s: %s" % (which, desc))
    if expect_red:
        print("    expect %s to go red, trajectories should be %d"
              % (expect_red, expect_traj))
    else:
        print("    no mutation applied -- every criterion must pass")

    backup()
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

    # Bytecode cache would hide the edit.
    for d in ("backend/core/__pycache__", "backend/__pycache__"):
        p = os.path.join(REPO, d)
        if os.path.isdir(p):
            subprocess.run([TRASH, "--", p], capture_output=True)

    bport = free_port(9800, 9880)
    log = open(os.path.join(BAK, "srv_%d.log" % bport), "w")
    subprocess.Popen([PY, "-m", "uvicorn", "server:app", "--host", "127.0.0.1",
                      "--port", str(bport)],
                     cwd=os.path.join(REPO, "backend"),
                     stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    if not wait_http("http://127.0.0.1:%d/health" % bport):
        print("    ABORT mutated backend never came up")
        restore()
        return 3

    act = probe_trajectories(bport)
    print("    backend %d reports trajectories=%s (expect %d)" % (bport, act, expect_traj))
    if act != str(expect_traj):
        print("    ABORT mutated backend does not carry the expected state")
        restore()
        return 3

    # The candidate port list is compiled into the bundle, and a running
    # `next start` keeps serving the old one. So the list has to be changed
    # BEFORE the build, and the frontend has to be restarted after it.
    # Skipping either step is how the first M1 run came out 10/10 green
    # while measuring a completely different backend.
    write(WSEND, re.sub(r"export const DEFAULT_WS_PORT_CANDIDATES = \[.*?\];",
                        "export const DEFAULT_WS_PORT_CANDIDATES = [%d];" % bport,
                        read(WSEND), count=1))
    if not build_frontend():
        print("    ABORT frontend build failed")
        restore()
        return 3

    # Prove the bundle really points at the mutated backend.
    # Match the minified form: the const keeps whatever name the minifier
    # picked (`o=[9803]`), so searching for the source identifier finds
    # nothing and every mutation aborts for the wrong reason.
    chunks = os.path.join(REPO, "frontend/.next/static/chunks/app")
    found = False
    for f in os.listdir(chunks):
        if not (f.startswith("page-") and f.endswith(".js")):
            continue
        if re.search(r"=\[%d\]" % bport, read(os.path.join(chunks, f))):
            found = True
            break
    if not found:
        print("    ABORT bundle does not point at port %d" % bport)
        restore()
        return 3
    print("    bundle confirmed pointing at %d" % bport)

    fport = free_port(9880, 9960)
    subprocess.Popen(["npx", "next", "start", "-p", str(fport)],
                     cwd=os.path.join(REPO, "frontend"),
                     stdout=open(os.path.join(BAK, "fe.log"), "w"),
                     stderr=subprocess.STDOUT, start_new_session=True)
    if not wait_http("http://127.0.0.1:%d/" % fport):
        print("    ABORT frontend never came up")
        restore()
        return 3
    print("    frontend %d" % fport)

    env = dict(os.environ, T3D_PORT=str(bport),
               T3D_URL="http://127.0.0.1:%d/" % fport,
               T3D_PROFILE=os.path.join(BAK, "prof_" + which))
    # The criteria now replay two full recordings (reset -> pick -> start ->
    # wait for tokens -> compare against npz), so 280s was not enough and
    # the timeout used to kill the run, discarding the output AND the
    # restore step. 600s covers the worst case; the runner is always
    # launched with nohup so a timeout cannot lose the log.
    try:
        r = subprocess.run(["node", os.path.join(REPO,
                            ".cache/browser_verify/verify_picker.mjs")],
                           capture_output=True, text=True, timeout=600, env=env)
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        with open(os.path.join(BAK, which + ".out"), "w") as fh:
            fh.write(out + "\nTIMEOUT after 600s\n")
        print("    TIMEOUT after 600s")
        restore()
        return 3
    with open(os.path.join(BAK, which + ".out"), "w") as fh:
        fh.write(r.stdout + r.stderr)
    for line in (r.stdout + r.stderr).splitlines():
        if line.startswith("[PASS]") or line.startswith("[FAIL]") or line.startswith("==="):
            print("    " + line)
    restore()
    print("    source restored")

    if not expect_red:
        # Baseline: anything red here is a broken criterion, not a caught
        # mutation. Reporting it as "OK" would be reading a red light as
        # a green one.
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
