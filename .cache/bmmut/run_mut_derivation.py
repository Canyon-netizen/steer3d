#!/usr/bin/env python3
"""变异施加器 + 编排器（3D 逐层推导链面板）。

用法: python3 run_mut_derivation.py D1

每条变异都配了一条「它该打红哪条判据」。判据在健康代码上全绿只是
起点 —— 这里的判据是逐值比对 p_final，理论上很容易写出一条恒绿的
判据（比如只查 rect 有没有 28 根）。所以每条变异都必须真的让
对应那条转红，否则记为「没抓住」。
"""
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request

REPO = "/Users/zhourui/code/steer3d"
BAK = os.path.join(REPO, ".cache/mutderiv")
PY = os.path.join(REPO, ".cache/venv3d/bin/python")
TRASH = "/Users/zhourui/.minimax/bin/mavis-trash"

PANEL = os.path.join(REPO, "frontend/components/LayerDerivationPanel.tsx")
STORE = os.path.join(REPO, "frontend/lib/store.ts")
WSEND = os.path.join(REPO, "frontend/lib/ws-endpoint.ts")

# mutation -> (desc, criterion that must go red)
MUTS = {
    "BASE": ("pristine source, everything must pass", ""),
    # 柱高改成常数：F5 逐值比对必须抓到
    "D1": ("bar height ignores p_final", "F5"),
    # 绿柱条件写成 p_final > 0.5：F6 首个说对层会变
    "D2": ("green-bar rule is a p_final threshold, not correct[]", "F6b"),
    # 换记录时不跟着换：链画的是上一条记录
    "D3": ("currentTrajectory never updates on picker change", "F9"),
    # 窗口外的诚实提示改成"画一条空链"
    "D4": ("out-of-window draws a chain instead of saying so", "F3"),
    # 步滑块失效：锁死在窗口第一步
    "D5": ("step slider pinned to window start", "F3c"),
    # 读错轨迹（按索引取而不是按 id）
    "D6": ("looks the trajectory up by index, not by id", "F9"),
    "D8": ("clears even a pick that is valid in the new record", "F12"),
    "D9": ("never clears the previous record's pick", "F11"),
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
    """Snapshot the three source files -- but only if they are clean.

    The first version wrote unconditionally. That silently turned every
    ABORT into a permanent problem: the run aborts before `restore()`, the
    mutated file stays on disk, and the *next* run's `backup()` copies that
    mutated file over the pristine one. Two runs later `restore()` restores
    a mutation, and the working tree carries `MUT_` markers into whatever
    gets committed next.

    The check is the one this repo has used all along: a marker left by a
    mutation. If it is there, the snapshot is not trustworthy.
    """
    os.makedirs(BAK, exist_ok=True)
    for src in (PANEL, STORE, WSEND):
        with open(src, encoding="utf-8") as fh:
            if "MUT_" in fh.read():
                raise SystemExit(
                    "ABORT %s still carries a mutation marker -- a previous "
                    "run aborted before restore(). Restore it by hand before "
                    "trusting any snapshot: %s" % (os.path.basename(src), src))
    for src in (PANEL, STORE, WSEND):
        shutil.copy(src, os.path.join(BAK, os.path.basename(src) + ".pristine"))


def restore():
    for src in (PANEL, STORE, WSEND):
        dst = os.path.join(BAK, os.path.basename(src) + ".pristine")
        if os.path.exists(dst):
            shutil.copy(dst, src)


def apply(which):
    if which == "D1":
        # Height stops being p_final. The 28 bars still render, the panel
        # still says "ready" -- only the numbers are wrong, which is
        # exactly what an existence check cannot see.
        edit(PANEL,
             "const hgt = Math.max(1.5, Math.min(p, 1) * plotH);",
             "const hgt = plotH * 0.5;  // MUT_CONST_HEIGHT", "D1")
    elif which == "D2":
        edit(PANEL,
             "const ok = pl.correct[l];",
             "const ok = p > 0.5;  // MUT_PFINAL_THRESHOLD", "D2")
    elif which == "D3":
        # The picker no longer publishes which recording is on screen, so
        # the chain keeps rendering the previous recording's data.
        edit(STORE,
             "  setCurrentTrajectory: (id) => set(() => ({ currentTrajectory: id })),",
             "  setCurrentTrajectory: (_id) => set(() => ({ currentTrajectory: null })),"
             "  // MUT_NEVER_UPDATES", "D3")
    elif which == "D4":
        # Out of the window, claim to be ready.
        #
        # No `//` comment in the replacement: this is a JSX *attribute*,
        # where `//` is not a comment. The first version wrote
        # `data-derivation="ready"  // MUT_FAKE_READY` and the build died
        # with a bare "Syntax Error" from webpack -- it never reached the
        # screen, so it proved nothing about the criterion. A mutation
        # that cannot compile is not a weak mutation, it is a no-op one.
        edit(PANEL,
             'data-derivation="out-of-window"',
             'data-derivation="ready"', "D4")
    elif which == "D5":
        edit(PANEL,
             "          value={stepId != null && stepId >= win[0] && stepId < win[1] ? stepId : win[0]}\n"
             "          onChange={(e) => setFocusedStep(parseInt(e.target.value, 10))}",
             "          value={win[0]}\n"
             "          readOnly  // MUT_PINNED_SLIDER", "D5")
    elif which == "D6":
        # Look the recording up by position instead of by id. With 48
        # entries and the reader switching between them, this renders a
        # plausible-looking chain from the wrong recording.
        edit(PANEL,
             "    return lens.trajectories.find((t) => t.id === currentTrajectory) ?? null;",
             "    const i = lens.trajectories.findIndex((t) => t.id === currentTrajectory);\n"
             "    return lens.trajectories[(i + 1) % lens.trajectories.length] ?? null;"
             "    // MUT_INDEX_LOOKUP", "D6")
    elif which == "D9":
        # 彻底删掉轨迹切换的清理逻辑。F11 走的是"只 dispatch change、
        # 不点 reset"的路径，reset 帮不上忙，所以这条变异是 F11 真正的牙齿。
        edit(PANEL,
             "      const w = traj?.window ?? null;\n"
             "      const s = focusedStep;               // \u540c\u4e00\u6b21\u6e32\u67d3\u91cc\u7684\u503c\uff0c\u5207\u6362\u90a3\u4e00\u523b\u7684 pick\n"
             "      if (s != null && (!w || s < w[0] || s >= w[1])) setFocusedStep(null);",
             "      // MUT_NEVER_CLEAR_STALE_PICK\n"
             "      void traj; void focusedStep;", "D9")
    elif which == "D8":
        # 去掉「新窗口内就保留 pick」的判断，退回无条件清。
        # 这不是等价变异：它会清掉**新记录里也有效**的 pick，于是「切记录 +
        # 立刻选步」这条正常路径被打断 —— 表现为 F9 间歇性转红。
        # 与 D7 的区别：D7 是稳定复现的卡死，D8 是竞态。
        edit(PANEL,
             "      const w = traj?.window ?? null;\n"
             "      const s = focusedStep;               // \u540c\u4e00\u6b21\u6e32\u67d3\u91cc\u7684\u503c\uff0c\u5207\u6362\u90a3\u4e00\u523b\u7684 pick\n"
             "      if (s != null && (!w || s < w[0] || s >= w[1])) setFocusedStep(null);",
             "      setFocusedStep(null);  // MUT_CLEAR_EVERYTHING", "D8")
    # D7 被删掉了，不是漏掉，是它**编不出来**：
    #   * 把整个 effect 块删掉 ⇒ 根节点的 data-traj={trajId} 引用未定义
    #     变量 ⇒ TS 编译失败 ⇒ 变异从未进到页面上（与 V6 同一类）。
    #   * 只删 effect 而留下"清陈旧 pick"这件事 ⇒ 那就是 D9。
    # 另外还试过"去掉滑块的 win[0] clamp"，那是**等价变异**：range input
    # 的 min/max 由浏览器强制执行，React 里少一层 clamp 肉眼无差别，
    # 换任何判据都抓不到。
    else:
        raise SystemExit("unknown mutation " + which)


def build_frontend():
    """Banner alone is not enough: Next prints "Compiled successfully"
    *before* linting and type-checking, so a TypeScript error still emits
    it and the build then dies without writing BUILD_ID. `next start` then
    answers "Could not find a production build", which the orchestrator can
    only report as a bare ABORT."""
    build_id = os.path.join(REPO, "frontend/.next/BUILD_ID")
    if os.path.exists(build_id):
        os.remove(build_id)
    r = subprocess.run(["npx", "next", "build"], cwd=os.path.join(REPO, "frontend"),
                       capture_output=True, text=True, timeout=900)
    out = r.stdout + r.stderr
    return ("Compiled successfully" in out) and os.path.exists(build_id)


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "BASE"
    if which not in MUTS:
        raise SystemExit("unknown mutation " + which)
    desc, expect_red = MUTS[which]
    print("=== %s: %s" % (which, desc))

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

    bport = int(os.environ.get("MUT_BACKEND", "9501"))

    # Everything from here on can raise -- `free_port` raises SystemExit
    # when the port range is exhausted, and that is the single most likely
    # failure. Without a finally, that path skips `restore()` and leaves the
    # mutated source on disk, which the next run's `backup()` would then
    # snapshot as "pristine". The whole chain was observed doing exactly
    # that. Wrap it so every exit path restores.
    try:
        return _run(which, expect_red, bport)
    finally:
        restore()
        print("    source restored")


def _run(which, expect_red, bport):
    # The candidate port list is compiled into the bundle, so it has to be
    # rewritten BEFORE the build and the frontend restarted after it.
    write(WSEND, re.sub(r"export const DEFAULT_WS_PORT_CANDIDATES = \[.*?\];",
                        "export const DEFAULT_WS_PORT_CANDIDATES = [%d];" % bport,
                        read(WSEND), count=1))
    if not build_frontend():
        print("    ABORT frontend build failed")
        return 3

    # Port range. Wide on purpose: every run leaves a `next start` behind
    # and the sandbox forbids signals, so those cannot be killed. After a
    # few runs the original [9976, 9990) is exhausted and every mutation
    # ABORTs on "no free port" -- which looks exactly like a criterion
    # problem and is not one. 120 slots is far more than this file will
    # ever consume; when they do run out, the run is genuinely done and
    # the leftover processes should be restarted from outside.
    fport = free_port(9976, 10096)
    subprocess.Popen(["npx", "next", "start", "-p", str(fport)],
                     cwd=os.path.join(REPO, "frontend"),
                     stdout=open(os.path.join(BAK, "fe.log"), "w"),
                     stderr=subprocess.STDOUT, start_new_session=True)
    if not wait_http("http://127.0.0.1:%d/" % fport):
        print("    ABORT frontend never came up")
        restore()
        return 3
    print("    frontend %d -> backend %d" % (fport, bport))

    env = dict(os.environ, T3D_PORT=str(bport),
               T3D_URL="http://127.0.0.1:%d/" % fport,
               T3D_PROFILE=os.path.join(BAK, "prof_" + which))
    try:
        r = subprocess.run(["node", os.path.join(REPO,
                            ".cache/browser_verify/verify_derivation.mjs")],
                           capture_output=True, text=True, timeout=420, env=env)
    except subprocess.TimeoutExpired:
        with open(os.path.join(BAK, which + ".out"), "w") as fh:
            fh.write("TIMEOUT after 420s\n")
        print("    TIMEOUT after 420s")
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
