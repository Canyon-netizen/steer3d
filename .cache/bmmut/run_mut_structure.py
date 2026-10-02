#!/usr/bin/env python3
"""变异施加器 + 编排器（3D「方向是不是随机的」面板）。

用法: python3 run_mut_structure.py BASE / V1 V2 ...

判据 14 条全绿只是起点。这里的每条变异对应"它该打红哪条判据"，
重点是那些**只有读者看得见**的性质：柱子的实际宽度、随机上限线的实际
位置、页面对"几对反向向量"的说法。只读 data-* 属性的判据抓不住这些。

一条故意不写成变异的：
  「把峰值层写死成 L14」—— 六个方向的峰值**确实**都是 L14，所以这条
  变异行为等价，判据必然全绿。它不是"判据没牙齿"，是"什么都没破坏"，
  换了任何判据都抓不到。要测 S9 有没有牙齿，用 V6（写死成注入层 L20）。
"""
import os
import re
import subprocess
import sys
import time
import urllib.request

REPO = "/Users/zhourui/code/steer3d"
BAK = os.path.join(REPO, ".cache/mutstruct")
PANEL = os.path.join(REPO, "frontend/components/VectorStructurePanel.tsx")
WSEND = os.path.join(REPO, "frontend/lib/ws-endpoint.ts")

MUTS = {
    "BASE": ("pristine source, everything must pass", ""),
    # 柱子宽度改成常数：页面上是一排等长柱，读者一眼看穿，
    # 但只断言 data-frac 的判据会全绿。
    "V1": ("bar width becomes a constant", "S3"),
    # 随机上限线画成满宽：看起来像"所有方向都只刚过随机线"，
    # 与事实相反（真实方向是它的 5-7 倍）。
    "V2": ("random ceiling line drawn full-width again", "S5"),
    # 把"两对"改回"三对"——这正是页面曾经写错、也被 worker 复述错的
    # 那个数。注册表里 derived_from 只有 2 条。
    "V3": ("claims three opposite pairs instead of two", "S6"),
    # top-3 方差占比写死成 0.19（就是它当前的真实值附近），
    # 断掉与产物的连接。
    "V4": ("hardcodes the top-3 variance share", "S10"),
    # 去掉符号翻转标记：两根等长柱不再被说明，成因不明。
    "V5": ("drops the sign-flip marker", "S8"),
    # 峰值层写死成注入层 L20（一个看起来很合理的猜法）。
    "V6": ("assumes the structural peak sits at the injection layer L20", "S9"),
    # 比值用 random_mean 而不是 random_max 当分母。
    "V7": ("divides by the random mean instead of the max", "S11"),
    # 删掉"这不能证明结构就是 confidence 的含义"这句。
    "V9": ("drops the not-what-this-says caveat", "S12"),
}

# 判据会去找的关键文案。备份时查这些，而不是查 MUT_ 标记 ——
# V3 把散文换成散文，不留任何标记。
PRISTINE_MARKERS = [
    "Two of the six are sign flips",
    "The six labels are four vectors",
    "What this does <b>not</b> say",
    "data-top3var={v3}",
    "data-drawn={w}",
    "x1={rndX} x2={rndX}",
    "SIGN_FLIP[n]",
    "best_over_random_max",
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
        raise SystemExit(
            "ABORT panel source is not pristine; missing: %s"
            % "; ".join(repr(m)[:46] for m in missing))


def backup():
    # 每次运行前清备份目录：上一轮 ABORT 留下的 .pristine 可能是变异态。
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
    if which == "V1":
        edit(PANEL,
             "          const w = ((v / top) * BAR_W).toFixed(1);",
             "          const w = 120;", "V1")
    elif which == "V2":
        edit(PANEL,
             "          x1={rndX} x2={rndX}\n"
             "          y1={-4} y2={names.length * rowH}",
             "          x1={BAR_X} x2={BAR_X + BAR_W}\n"
             "          y1={-4} y2={names.length * rowH}", "V2")
    elif which == "V3":
        edit(PANEL, "Two of the six are sign flips of another",
                    "Three of the six are sign flips of another", "V3")
    elif which == "V3b":
        edit(PANEL, "The six labels are four vectors.",
                    "The six labels are three vectors.", "V3b")
    elif which == "V4":
        edit(PANEL,
             "  const v3 = scan.top3_variance_frac?.[INJECT_LAYER] ?? NaN;",
             "  const v3 = 0.19;", "V4")
    elif which == "V5":
        edit(PANEL,
             "          const flip = SIGN_FLIP[n];",
             "          const flip = undefined;", "V5")
    elif which == "V6":
        # 必须显式写成 `: string`。`const INJECT_LAYER = "20"` 会让 TS 推断
        # 出字面量类型 "20"，于是下面 `peakL === "14"` 直接报
        # "no overlap" 而**编译失败** —— 变异根本没进到页面上，
        # 编排器只看到一条哑掉的 ABORT。类型标注把字面量拓宽回 string。
        edit(PANEL,
             "          const peakL = LAYERS[vals.indexOf(Math.max(...vals))];",
             '          const peakL: string = INJECT_LAYER;', "V6")
    elif which == "V7":
        edit(PANEL,
             "  const rnd = at.random_max;",
             "  const rnd = at.random_max;\n"
             "  const RND = at.random_mean;", "V7")
        edit(PANEL,
             "        <span className=\"font-mono text-gray-400\" data-ratio={at.best_over_random_max}>\n"
             "          {at.best_over_random_max.toFixed(1)}×\n"
             "        </span>{\" \"}",
             "        <span className=\"font-mono text-gray-400\" data-ratio={at.best_real / RND}>\n"
             "          {(at.best_real / RND).toFixed(1)}×\n"
             "        </span>{\" \"}", "V7")
    elif which == "V9":
        edit(PANEL,
             "        What this does <b>not</b> say: that the structure means",
             "        This also shows that the structure means", "V9")
    else:
        raise SystemExit("unknown mutation " + which)


def build_frontend():
    """Build and confirm a *usable* production build.

    Checking stdout for "Compiled successfully" is not enough. Next prints
    that line **before** it lints and type-checks, so a TypeScript error
    still produces it and the build then dies without writing BUILD_ID.
    The symptom was V6: build "succeeded", `next start` answered
    "Could not find a production build in the '.next' directory", and the
    orchestrator reported only a bare ABORT.

    So: require both the banner *and* a real BUILD_ID on disk.
    """
    build_id = os.path.join(REPO, "frontend/.next/BUILD_ID")
    if os.path.exists(build_id):
        os.remove(build_id)          # 下次 build 若失败，这行就不会回来
    r = subprocess.run(["npx", "next", "build"], cwd=os.path.join(REPO, "frontend"),
                       capture_output=True, text=True, timeout=900)
    out = r.stdout + r.stderr
    if "Compiled successfully" not in out:
        print("    build failed (no banner)")
        for ln in out.splitlines():
            if "error" in ln.lower() or "Failed" in ln:
                print("      " + ln[:170])
        return False
    if not os.path.exists(build_id):
        # 横幅打了但产物没落地 = 类型检查/页面生成阶段炸了。
        print("    build printed the banner but wrote no BUILD_ID "
              "(type-check or page generation failed)")
        bad = [ln for ln in out.splitlines()
               if "error" in ln.lower() or "Type error" in ln]
        for ln in bad[:6]:
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
        fport = free_port(9990, 10200)
        # 顺序要紧：先 build 再 start。反过来会让 next start 拿着上一轮
        # 的 .next 起来，服务的是旧 chunk —— 页面停在 SSR 骨架上永远
        # 不 hydrate，看上去像"面板加载不出来"。
        subprocess.Popen(["npx", "next", "start", "-p", str(fport)],
                         cwd=os.path.join(REPO, "frontend"),
                         stdout=open(os.path.join(BAK, "fe.log"), "w"),
                         stderr=subprocess.STDOUT, start_new_session=True)
        if not wait_http("http://127.0.0.1:%d/" % fport):
            print("    ABORT frontend never came up on %d" % fport)
            # 端口扫到了但服务没起来 —— 打印前端的日志，否则只能猜。
            # 上一轮 V6 就是这么哑掉的：ABORT 了但没说为什么。
            try:
                with open(os.path.join(BAK, "fe.log"), encoding="utf-8") as fh:
                    tail = fh.read().splitlines()[-12:]
                print("    fe.log: " + " / ".join(t.strip() for t in tail)[:400])
            except Exception as e:
                print("    fe.log 读不到: %s" % e)
            return 3
        print("    frontend %d -> backend %d" % (fport, bport))

        env = dict(os.environ, T3D_PORT=str(bport),
                   T3D_URL="http://127.0.0.1:%d/" % fport,
                   T3D_PROFILE=os.path.join(BAK, "prof_" + which))
        r = subprocess.run(["node", os.path.join(REPO,
                            ".cache/browser_verify/verify_structure.mjs")],
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
            # 还原源码 ≠ bundle 干净。必须重建，否则下一轮的 next start
            # 服务的是变异产物，而 BASE 会报出一堆"文案明明在屏幕上"的红。
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
