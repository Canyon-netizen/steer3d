#!/usr/bin/env python3
"""变异施加器 + 编排器（3D「强度定律」面板）。

用法: python3 run_mut_law.py BASE / W1 W2 ...

这一块面板的特殊性：它讲的是一条**定律**，所以「把它说错」和「把它画错」
后果一样严重。W1 就是本轮真实踩到的那个 bug —— ½a² 少乘 100，曲线被压在
底边，读者看到的是"解析曲线就是贴着 0 的一条平线"，而判据第一版只查
宽度，全绿。W1 把它钉住。
"""
import os
import re
import subprocess
import sys
import time
import urllib.request

REPO = "/Users/zhourui/code/steer3d"
BAK = os.path.join(REPO, ".cache/mutlaw")
PANEL = os.path.join(REPO, "frontend/components/StrengthLawPanel.tsx")
WSEND = os.path.join(REPO, "frontend/lib/ws-endpoint.ts")

MUTS = {
    "BASE": ("pristine source, everything must pass", ""),
    # ½a² 少乘 100：曲线被压平成贴在底边的一条线。本轮真实发生过的 bug。
    "W1": ("drops the x100 so the analytic curve is drawn flat at zero", "L6"),
    # 所有实测点画在同一行
    "W2": ("draws every measured point on one horizontal line", "L4"),
    # 删掉失效区（文字里还留着，但图上没了）
    "W3": ("hides the out-of-depth region", "L8"),
    # 把"不是反例"改写成"定律处处成立"
    "W4": ("claims the law holds everywhere", "L7"),
    # 把反证写成支持
    "W5": ("rewrites the negative as support for the naming", "L9"),
    # 两个数写死。**不能**写 0.037 —— 那恰是真值 0.036816… 的 toFixed(3)，
    # 变异撞上巧合值时判据必然保持绿，测不出任何东西（O7 教训，第二次）。
    "W6": ("hardcodes the random-vs-named gap to a non-coinciding value", "L3"),
    # 随机区间画成固定高度
    "W7": ("draws the random span as a fixed height", "L5"),
    # 删掉装置自检
    "W8": ("drops the device self-check line", "L10"),
}

PRISTINE_MARKERS = [
    "data-law=\"ready\"",
    "data-outofdepth-from",
    "data-curve=\"analytic\"",
    "carries no information",
    "not counterexamples",
    "toy input",
    "data-gap={safe.max_real_vs_random_gap_pp}",
    "100 * 0.5 * a * a",
]


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


def wait_http(url, seconds=30):
    for _ in range(seconds):
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status < 500:
                    return True
        except Exception:
            time.sleep(1)
    return False


def verify_source_untouched():
    s = read(PANEL)
    missing = [m for m in PRISTINE_MARKERS if m not in s]
    if missing:
        raise SystemExit("ABORT panel source is not pristine; missing: %s"
                         % "; ".join(repr(m)[:48] for m in missing))


def backup():
    if os.path.isdir(BAK):
        for f in os.listdir(BAK):
            if f.endswith(".pristine") or f.endswith(".out"):
                os.remove(os.path.join(BAK, f))
    os.makedirs(BAK, exist_ok=True)
    verify_source_untouched()
    for src in (PANEL, WSEND):
        with open(os.path.join(BAK, os.path.basename(src) + ".pristine"), "w",
                  encoding="utf-8") as fh:
            fh.write(read(src))


def restore():
    for src in (PANEL, WSEND):
        dst = os.path.join(BAK, os.path.basename(src) + ".pristine")
        if os.path.exists(dst):
            with open(dst, encoding="utf-8") as fh:
                write(src, fh.read())


def apply(which):
    if which == "W1":
        edit(PANEL, "            const p = 100 * 0.5 * a * a;",
                    "            const p = 0.5 * a * a;  // MUT_NO_X100", "W1")
    elif which == "W2":
        edit(PANEL, "            cx={sx(r.a_mean)} cy={sy(r.real_dev_mean)} r={2.6}",
                    "            cx={sx(r.a_mean)} cy={sy(rows[0].real_dev_mean)} r={2.6}  // MUT_FLAT",
             "W2")
    elif which == "W3":
        edit(PANEL, "          data-outofdepth-from={aAtSafe}",
                    "          data-outofdepth-from={0}  // MUT_BAND_GONE", "W3")
    elif which == "W4":
        edit(PANEL,
             "        . Those points are not counterexamples — the quadratic term is simply\n"
             "        no longer the whole story there.",
             "        . Those points are just noise, and the law holds everywhere.", "W4")
    elif which == "W5":
        edit(PANEL,
             "        <b>So a random vector costs exactly as much geometry as the one called\n"
             "        &ldquo;confidence&rdquo;.</b> The cost is set by how hard you push, and\n"
             "        it carries no information about whether the direction means anything.",
             "        <b>The cost is set purely by the injected magnitude, which\n"
             "        confirms that these directions encode a specific, repeatable\n"
             "        property of the model rather than an arbitrary choice.</b>", "W5")
    elif which == "W6":
        edit(PANEL,
             "          {safe.max_real_vs_random_gap_pp.toFixed(3)} pp",
             "          0.900 pp  // MUT_HARDCODED_GAP", "W6")
    elif which == "W7":
        edit(PANEL, "            y1={sy(r.random_dev_max)} y2={sy(r.random_dev_min)}",
                    "            y1={sy(r.random_dev_max)} y2={sy(r.random_dev_max - 1)}  // MUT_FLAT_SPAN",
                    "W7")
    elif which == "W8":
        edit(PANEL,
             "        The measurement device was checked against a toy input with a closed-form\n"
             "        answer ({law.toy_selfcheck}) before being pointed at the recordings.",
             "        The measurement device is sound.", "W8")
    else:
        raise SystemExit("unknown mutation " + which)


def build_frontend():
    """横幅 + BUILD_ID 双条件。

    Next 先打 "Compiled successfully" 再跑类型检查，所以只认横幅会把
    编译失败判成成功，接着 `next start` 报 "Could not find a production
    build"，编排器只能给一条没有原因的 ABORT。
    """
    build_id = os.path.join(REPO, "frontend/.next/BUILD_ID")
    if os.path.exists(build_id):
        os.remove(build_id)
    r = subprocess.run(["npx", "next", "build"], cwd=os.path.join(REPO, "frontend"),
                       capture_output=True, text=True, timeout=900)
    out = r.stdout + r.stderr
    if "Compiled successfully" not in out:
        print("    build failed (no banner)")
        for ln in out.splitlines():
            if "error" in ln.lower():
                print("      " + ln[:170])
        return False
    if not os.path.exists(build_id):
        print("    banner printed but no BUILD_ID (type-check or page generation failed)")
        for ln in out.splitlines():
            if "error" in ln.lower() or "Type error" in ln:
                print("      " + ln[:200])
        return False
    return True


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

    bport = int(os.environ.get("MUT_BACKEND", "9503"))
    r = None
    try:
        write(WSEND, re.sub(r"export const DEFAULT_WS_PORT_CANDIDATES = \[.*?\];",
                            "export const DEFAULT_WS_PORT_CANDIDATES = [%d];" % bport,
                            read(WSEND), count=1))
        if not build_frontend():
            return 3
        fport = free_port(10200, 10400)
        subprocess.Popen(["npx", "next", "start", "-p", str(fport)],
                         cwd=os.path.join(REPO, "frontend"),
                         stdout=open(os.path.join(BAK, "fe.log"), "w"),
                         stderr=subprocess.STDOUT, start_new_session=True)
        if not wait_http("http://127.0.0.1:%d/" % fport):
            print("    ABORT frontend never came up on %d" % fport)
            try:
                with open(os.path.join(BAK, "fe.log"), encoding="utf-8") as fh:
                    print("    fe.log: " + " / ".join(
                        t.strip() for t in fh.read().splitlines()[-12:])[:400])
            except Exception as e:
                print("    fe.log 读不到: %s" % e)
            return 3
        # chunk 必须取得到 200：200 才说明服务的是**这一轮**的产物
        with urllib.request.urlopen("http://127.0.0.1:%d/" % fport, timeout=10) as rr:
            html = rr.read().decode("utf-8", "replace")
        m = re.search(r"/_next/static/chunks/app/page-[a-z0-9]+\.js", html)
        if not m:
            print("    ABORT 首页里找不到 page chunk，服务可能不是本轮的产物")
            return 3
        with urllib.request.urlopen("http://127.0.0.1:%d%s" % (fport, m.group(0)),
                                    timeout=10) as cr:
            ccode = cr.status
        if ccode != 200:
            print("    ABORT page chunk 返回 %d —— 服务的是旧 .next 产物" % ccode)
            return 3
        print("    frontend %d -> backend %d (chunk %d 200)" % (fport, bport, ccode))

        env = dict(os.environ, T3D_PORT=str(bport),
                   T3D_URL="http://127.0.0.1:%d/" % fport,
                   T3D_PROFILE=os.path.join(BAK, "prof_" + which))
        r = subprocess.run(["node", os.path.join(REPO,
                            ".cache/browser_verify/verify_law.mjs")],
                           capture_output=True, text=True, timeout=420, env=env)
        with open(os.path.join(BAK, which + ".out"), "w") as fh:
            fh.write(r.stdout + r.stderr)
        for line in (r.stdout + r.stderr).splitlines():
            if line.startswith("[PASS]") or line.startswith("[FAIL]") or line.startswith("==="):
                print("    " + line)
    finally:
        restore()
        print("    source restored")
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
