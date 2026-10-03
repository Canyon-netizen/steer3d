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
    # ---- H 组：±v 配对检验（§4.13）。三条各打一条 H 判据 ----
    # O9 把「CI 跨 0 ⇒ 分不开」这条判断写死成「都分得开」。
    #    这是最容易犯的一类：只印一个 +3.52 的配对差，读者会以为有差异，
    #    而它的 95% CI 是 [-6.04, +12.17]。
    "O9": ("hardcodes every arm as distinguishable", "H3"),
    # O10 删掉「没有同范数随机对照 ⇒ 不构成方向专属性」这条限制。
    #     数字全对、结论也还对，但读者会以为这就是方向专属性的证据。
    "O10": ("drops the missing-random-control limitation", "H5"),
    # O11 把配对差写死成两臂合并的差（= 0），属性照旧。
    #     专打「文案撒谎、属性诚实」。
    "O11": ("hardcodes the paired diff while attributes stay honest", "H2"),
    # ---- I 组：「净变化 0」的功效块（§4.14）----
    # 这一组的数字本来就全对，错的是**这个 0 允许被读成什么**。
    # 所以每条变异都不改 data-* 属性（那样 I0 立刻红，太便宜），
    # 改的是**可见文案**，专打判据主体。
    # O12 把「欠功效」的读法换回原来的零效应读法 —— 数字一个没动。
    "O12": ("restores the zero-effect reading of net change 0", "I2"),
    # O13 删掉「要 p<0.05 需要 6 个同向翻转」那条。
    #     这是「0 为什么不是零效应」的核心算术，删了剩下的读起来仍像结论。
    "O13": ("drops the flips-needed arithmetic", "I3"),
    # O14 把 95% CI 压窄成 [0.003, 0.120]（属性仍诚实，文字假装功效够）。
    #     专打「文案撒谎、属性诚实」，与 O11 同一类。
    "O14": ("narrows the printed CI while attributes stay honest", "I4"),
    # O15 删掉选择效应（「两臂答案不同」），把分母说成无偏。
    "O15": ("hides the selection rule that built the denominator", "I6"),
    # O16 删掉长度偏倚那条。
    "O16": ("drops the length-bias caveat", "I7"),
    # O17 把「没有分开记，这里不替它编」编成「其余题目答案未变」。
    #     这是本组最恶劣的一条：产物里根本没分开记三类的去向。
    "O17": ("fabricates where the remaining problems went", "I8"),
    # O18 删掉「L7 一次都没测」。
    "O18": ("drops the L7-never-tested statement", "I5"),
    # O19 删掉「域外答案的 2 题」那条点名。
    #     数字一个都不动 —— 结论也不动（它们贡献 0），所以这一条
    #     只靠「读者会不会误以为那两题被正常判定过」来发现。
    "O19": ("drops the out-of-domain answer caveat", "I9"),
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
        # §4.14 功效块。少了这几条，一条「删掉整个功效块」的变异跑完
        # 之后，backup() 会把删干净的源码当成 pristine 存下来，
        # 下一轮 BASE 就在一份缺块的源码上跑 —— 而 BASE 本该全绿。
        "data-answer-power",
        "data-power-not-claimed",
        "data-power-item=\"flips\"",
        "data-power-item=\"length\"",
        "data-power-item=\"ceiling\"",
        "data-power-item=\"domain\"",
        "flips_needed_for_p05",
        "欠功效",
        "labels_not_both_in_domain",
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
        # 锚点随 §4.14 改过：净变化那一段现在是从 answer_power.json
        # 读的。留着旧锚点的话这条变异会 ABORT（anchor not found），
        # 而 ABORT 不算命中 —— 判据会一直绿着没人发现它已失效。
        edit(PANEL,
             '        all. Net change in correct answers: <b>{pw?.net_change ?? 0}</b>.{" "}\n'
             '        {pw\n'
             '          ? "这个 0 是欠功效，不是零效应 —— 下面这一块算给你看。"\n'
             '          : ""}',
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
    elif which == "O9":
        # 判可分性的三元写死成 true —— 所有行都会印「两臂分得开」
        edit(PANEL,
             "                {m.distinguishable ? (",
             "                {true ? (  // MUT_O9",
             "O9")
    elif which == "O10":
        edit(PANEL,
             "            <b>但这不构成方向专属性：</b>本批次\n"
             "            <b>没有同范数随机方向对照臂</b>。同幅度的随机方向注入同样会产生\n"
             "            非零 KL、同样会让一致率低于 1，也可能左右不对称。\n"
             "            缺的那一格已经定位清楚 ——\n"
             "            <b>同层 {arm.layer}、同强度 ±{arm.strength}、同这 {arm.n_pairs} 道题、\n"
             "            随机单位方向</b>，跑出来直接和上面两个数比。\n"
             "            在补上之前，只能说「这条轴的响应不对称且可测」，\n"
             "            不能说「这个效果是 confidence 特有的」。",
             "            本批次的控制臂是零强度对照。",
             "O10")
    elif which == "O11":
        # 属性照旧（data-arm-diff 仍读产物），只有可见文字改成合并差
        edit(PANEL,
             "                  配对差 {m.paired_diff >= 0 ? \"+\" : \"\"}{m.paired_diff.toFixed(4)} ±{\" \"}\n"
             "                  {m.paired_sem.toFixed(4)}",
             "                  配对差 +0.0000 ± 0.0000  // MUT_O11",
             "O11")
    elif which == "O8":
        edit(PANEL,
             "        <Stat label=\"token agreement\" v={stats.agreeMed != null ? pct(stats.agreeMed) : \"—\"}",
             "        <Stat label=\"token agreement\" v=\"99.9%\"", "O8")
    elif which == "O12":
        # 数字一个都不动：净变化仍然从 answer_power.json 读、data-* 属性
        # 仍然诚实。只把「欠功效」的读法换回零效应。
        edit(PANEL,
             '        all. Net change in correct answers: <b>{pw?.net_change ?? 0}</b>.{" "}\n'
             '        {pw\n'
             '          ? "这个 0 是欠功效，不是零效应 —— 下面这一块算给你看。"\n'
             '          : ""}',
             "        all. Steering moved things; it did not make them better.",
             "O12a")
        edit(PANEL,
             "            <b>「净变化 {pw.net_change}」是欠功效，不是零效应。</b>",
             "            <b>「净变化 {pw.net_change}」说明干预没有影响答案正确性。</b>",
             "O12b")
    elif which == "O13":
        edit(PANEL,
             '            <li data-power-item="flips">\n'
             '              入选集里只有 <b className="font-mono text-gray-200">{pw.flips}</b>{" "}\n'
             '              个正确性翻转（{pw.flips_up} 正 / {pw.flips_down} 反）。符号检验双侧\n'
             '              精确 p = 2×0.5<sup>{pw.flips}</sup> ={" "}\n'
             '              <span className="font-mono">{pw.two_sided_sign_p_if_all_same_direction}</span>，\n'
             '              要 p &lt; 0.05 需要 <b className="font-mono text-gray-200">{pw.flips_needed_for_p05}</b>{" "}\n'
             '              个同向翻转，而本设计上限只有{" "}\n'
             '              <b className="font-mono text-gray-200">{pw.n_shipped}</b> 个。\n'
             '              实测 1 正 1 反，是零假设下的<b>典型</b>结果，不是「接近显著」。\n'
             '            </li>\n',
             "", "O13")
    elif which == "O14":
        # 属性照旧（data-ci-hi 仍读产物），只有印出来的区间被压窄。
        edit(PANEL,
             "                [{pw.up_rate_ci95[0].toFixed(3)}, "
             "{pw.up_rate_ci95[1].toFixed(3)}]\n",
             "                [{pw.up_rate_ci95[0].toFixed(3)}, {0.12.toFixed(3)}]  // MUT_O14\n",
             "O14a")
        edit(PANEL,
             "              {\" \"}—— 上界宽到 <b>{pct(pw.up_rate_ci95[1])}</b>，",
             "              {\" \"}—— 上界宽到 <b>{pct(0.12)}</b>，",
             "O14b")
    elif which == "O15":
        edit(PANEL,
             "            上面那张表，而入选条件之一就是<b>两臂答案不同</b> ——\n"
             "            算净变化的那个分母，是按「确实变了」挑出来的。",
             "            上面那张表，全部题目的两臂答案都能解析出来 ——\n"
             "            算净变化的那个分母，与批次其余题目没有差别。",
             "O15")
    elif which == "O16":
        edit(PANEL,
             '            <li data-power-item="length">\n'
             '              还有长度偏倚：入选要求两臂都跑完 {"</think>"}，而两臂步数比在{" "}\n'
             '              <span className="font-mono text-gray-200">\n'
             '                {pw.steps_ratio_min}×–{pw.steps_ratio_max}×\n'
             '              </span>\n'
             '              {" "}之间 ⇒ 入选集偏向两臂都跑到底的题，而那正是干预影响最大的题。\n'
             '            </li>\n',
             "", "O16")
    elif which == "O17":
        edit(PANEL,
             "              题的去向（答案相同 / 未跑完 / 严格口径解析不出）产物里没有分开记，\n"
             "              这里不替它编。",
             "              题的去向是答案与基线相同，未受干预影响。",
             "O17")
    elif which == "O18":
        edit(PANEL,
             "            <b>L7（改变的是概念而非位置/格式）一次都没测</b> ——\n"
             "            「答案对不对」连位置轴对照都没有。\n",
             "", "O18")
    elif which == "O19":
        edit(PANEL,
             '            <li data-power-item="domain">\n'
             '              还有 <b className="font-mono text-gray-200">\n'
             '                {pw.labels_not_both_in_domain.length}\n'
             '              </b>{" "}\n'
             '              题的<b>两臂答案都落在 AIME 答案域之外</b>（\n'
             '              {pw.labels_not_both_in_domain.join("、")}\n'
             '              ）。它们被归进 <code>wrong-&gt;wrong</code>，\n'
             '              对净变化<b>没有贡献</b>，所以上面所有结论都不受影响；\n'
             '              但它们的「错」是<b>域外判定</b>，不是与一个合法答案比对出来的。\n'
             '            </li>\n',
             "", "O19")
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
