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
    # ---- I 组：「净变化 0」到底是什么（§4.15，v2）----
    # 这一组的数字本来就全对，错的是**这个 0 允许被读成什么**。
    # 除 O22 外，每条变异都不改 data-* 属性（那样 I0 立刻红，太便宜），
    # 改的是**可见文案**。J3 是这一族里第四条「判据只读属性」的翻版。
    # O12 把「欠功效」的读法换回零效应读法 —— 数字一个没动。
    "O12": ("restores the zero-effect reading of net change 0", "I2"),
    # O13 删掉「要 p<0.05 需要 6 个同向翻转」那条算术。
    "O13": ("drops the flips-needed arithmetic", "I3"),
    # O14 把印出来的破坏率 CI 压窄（属性仍诚实，文字假装功效够）。
    "O14": ("narrows the printed break-rate CI while attributes stay honest", "I4"),
    # O15 把完整配对数说成 10 —— 正是 v1 那个被 §4.15 查实为错的分母。
    "O15": ("reverts to the wrong denominator (10 instead of 20)", "I6"),
    # O16 删掉不变性定理。读者最该怀疑的就是「这个 0 会不会是筛出来的」。
    "O16": ("drops the invariance theorem", "I7"),
    # O17 删掉「答案变了 ≠ 概念变了」—— 50% 改变率最容易被读错的地方。
    "O17": ("drops the changed-vs-semantic distinction", "I8"),
    # O18 删掉「未知那几题是撞 token 上限跑飞的」这半句。
    "O18": ("drops the token-cap link for the unknown problems", "I9"),
    # O19 删掉域外答案那条。
    "O19": ("drops the out-of-domain answer caveat", "I10"),
    # O20 删掉「不能说准确率没有下降」—— net 0 恰好最容易读成这句。
    "O20": ("drops the no-accuracy-drop restriction", "I5"),
    # O21 把印出来的基线答对数写死成 10（data-* 仍诚实）。
    "O21": ("hardcodes the printed baseline-correct count", "I1"),
    # O22 唯一一条改 data-* 的：把完整配对数写死成 10。
    "O22": ("hardcodes the complete-pair count in the data attribute", "I0"),
    # O23 把 markdown 强调记号抄回 JSX。判据 I0b 就是为它加的 ——
    # 而 I0b 本身是**看截图看出来的**：I0–I10 全绿时页面上赫然印着
    # `**不是数据碰巧**`。「文字在」判据查得出，「渲染对了没有」查不出。
    "O23": ("copies markdown emphasis into plain JSX", "I0b"),

    # ---- J 组：同一根轴换符号（§4.16）----
    # 这一组盯的是**反直觉**的那条：+v 把分布推得更近却让 18/23 的题跑不完，
    # −v 推得更远却只让 1 题跑不完。数字都对，难的是不把它们压成一个
    # 「强度越大后果越大」的故事。
    # J1 把「共享对照」说成两次独立运行。
    "J1": ("breaks the shared-control pairing claim", "J1"),
    # J2 把 +v 的闭合率淡化（只说「略有下降」）。
    "J2": ("softens the +v closure collapse into a mild dip", "J2"),
    # J3 把 McNemar 的 p 写死成一个不够小的值。
    "J3": ("inflates the McNemar p-value", "J3"),
    # J4 删掉「与注入幅度相反」那一条 —— 最容易被抹掉的一个事实。
    "J4": ("drops the amplitude-vs-instability inversion", "J4"),
    # J5 把没到 0.05 的长度差印成结论。**这一条是本组最容易犯的错。**
    "J5": ("presents the under-powered length gap as a conclusion", "J5"),
    # J6 删掉「破坏从『答错』变成了『答不出来』」的陷阱说明。
    "J6": ("drops the unclosed-illusion warning", "J6"),
    # J7 删掉「只有一个强度点」与「缺随机方向臂」两条限制。
    "J7": ("drops the single-strength and missing-random-arm limits", "J7"),
    # J8 唯一一条改 data-* 的：把 upOnly 写死成 1（与 −v 一样）。
    "J8": ("hardcodes the up-only blow-up count in the data attribute", "J0"),
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
        "data-power-item=\"invariance\"",
        "data-power-item=\"semantic\"",
        "data-power-item=\"domain\"",
        "data-power-item=\"unknown\"",
        "data-power-item=\"power\"",
        "flips_needed_for_p05",
        "max_possible_flips",
        "changed_but_still_wrong_magnitude",
        "欠功效",
        "不等于「概念变了」",
        "贡献恒为 0",
        # §4.16 方向对照块
        "data-direction-compare",
        "data-dir-item=\"mcnemar\"",
        "data-dir-item=\"kl\"",
        "data-dir-item=\"length\"",
        "data-dir-trap",
        "零强度臂逐字相同",
        "没到 0.05",
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
    elif which == "J1":
        edit(PANEL,
             '            {" "}上面整块只看了 <code>−v</code>。disk 上还有同 '
             '{sd.n_problems} 道题的{" "}\n'
             '            <code>+v</code> 臂，而两个方向的<b>零强度臂逐字相同</b>（\n'
             '            {sd.shared_control.n_identical_zero_arms}/{sd.n_problems}）⇒\n'
             '            它们共享同一份对照，配对里没有「两次运行」的噪声源，\n'
             '            只差注入向量这一个变量。',
             "            上面整块只看了 <code>−v</code>。下面这组是 <code>+v</code> 臂的同样口径。",
             "J1")
    elif which == "J2":
        edit(PANEL,
             '            <Stat label="注入 +v 后" v={`${sd.closed_counts.up_plus_v}/${sd.n_problems}`}\n'
             '                  sub="大面积跑飞" />',
             '            <Stat label="注入 +v 后" v={`${sd.closed_counts.up_plus_v}/${sd.n_problems}`}\n'
             '                  sub="略有下降" />',
             "J2")
    elif which == "J3":
        edit(PANEL,
             "                {sd.blew_up.mcnemar_exact_p.toExponential(2)}\n",
             "                {0.42.toFixed(2)}  // MUT_J3\n",
             "J3")
    elif which == "J4":
        edit(PANEL,
             '            <li data-dir-item="kl">\n'
             '              <b>而且这与注入幅度相反。</b>同一层同一强度下，\n',
             '            <li data-dir-item="kl">\n'
             '              <b>这与注入幅度一致。</b>同一层同一强度下，\n',
             "J4a")
        edit(PANEL,
             "              ⇒ 「把分布推得远」和「把生成推入不收敛」是两件事，\n"
             "              本项目这条轴上两者的方向<b>相反</b>。\n",
             "",
             "J4b")
    elif which == "J5":
        # 把没到 0.05 的长度差印成结论。
        edit(PANEL,
             "              <b className=\"text-amber-300\">没到 0.05</b>。\n"
             "              ⇒ <b>长度是弱证据</b>，能站住的是上面的闭合率。\n",
             "              <b>说明 +v 让模型明显更啰嗦。</b>\n",
             "J5")
    elif which == "J6":
        edit(PANEL,
             "            那是 <b>{sd.per_direction.up.n_incomplete}/{sd.n_problems}</b>{\" \"}\n"
             "            未闭合制造出来的假象：<b>破坏没有消失</b>，\n"
             "            它从「答错」变成了「答不出来」，而按 verdict 计数<b>看不见</b>。\n",
             "            那只是这批题恰好偏难。\n",
             "J6")
    elif which == "J7":
        edit(PANEL,
             "            <b>不能说的</b>：本项目只有 s = {sd.strength} <b>一个强度点</b>，\n"
             "            所以「某个阈值之上 +v 会跑飞」是<b>假设</b>，既不能证实也不能证伪；\n"
             "            也不能把这个符号不对称说成 confidence 这个<b>概念</b>的性质 ——\n"
             "            <b>缺同范数随机方向臂</b>，排除不了「±v 各自靠近某个不稳定吸引域」\n"
             "            这种更平凡的解释。\n",
             "",
             "J7")
    elif which == "J8":
        edit(PANEL,
             "             data-up-only={sd.blew_up.table_on_shared_zero_control.up_only_blew_up}\n",
             "             data-up-only={1}  // MUT_J8\n",
             "J8")
    elif which == "O12":
        # 数字一个都不动：净变化仍从 answer_power.json 读、data-* 仍诚实。
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
             '            <li data-power-item="power">\n'
             '              <b>功效仍然不够。</b>正确性翻转{" "}\n'
             '              <b className="font-mono text-gray-200">{pw.flips}</b> 次\n'
             '              （{pw.flips_up} 正 / {pw.flips_down} 反），\n'
             '              符号检验双侧精确 p ={" "}\n'
             '              <span className="font-mono text-gray-200">\n'
             '                {pw.two_sided_sign_p_if_all_same_direction}\n'
             '              </span>\n',
             '            <li data-power-item="power">\n'
             '              <b>功效仍然不够。</b>正确性翻转{" "}\n'
             '              <b className="font-mono text-gray-200">{pw.flips}</b> 次\n'
             '              （{pw.flips_up} 正 / {pw.flips_down} 反）。  // MUT_O13\n',
             "O13")
    elif which == "O14":
        # 属性照旧（data-* 仍读产物），只有印出来的区间被压窄。
        edit(PANEL,
             "                [{pw.break_rate_ci95[0].toFixed(3)},"
             " {pw.break_rate_ci95[1].toFixed(3)}]\n",
             "                [{pw.break_rate_ci95[0].toFixed(3)},"
             " {0.2.toFixed(3)}]  // MUT_O14\n",
             "O14a")
    elif which == "O15":
        # 把 v2 查实的分母改回 v1 那个错的 10。
        edit(PANEL,
             "            <b>{pw.n_complete_pairs} 题</b>两臂都跑完、构成可比的配对，\n"
             "            这 {pw.n_complete_pairs} 题的 verdict 全表是 ——",
             "            <b>10 题</b>两臂都跑完、构成可比的配对，\n"
             "            这 10 题的 verdict 全表是 ——",
             "O15")
    elif which == "O16":
        edit(PANEL,
             '            <li data-power-item="invariance">\n'
             '              <b>先回答最容易被怀疑的那一条：这个 0 会不会是筛出来的？</b>\n'
             '              {" "}不会，而且这<b>不是数据碰巧</b>，是定理 ——\n'
             '              上面那张表只入表了 {pw.n_shipped} 题（规则含「两臂答案不同」），\n'
             '              被剔除的 {pw.n_complete_pairs - pw.n_shipped} 题<b>答案都相同</b>，\n'
             '              答案相同 ⇒ 两臂对错必然一致 ⇒ verdict 恒为 X-&gt;X ⇒{" "}\n'
             '              <b>对净变化的贡献恒为 0</b>。\n'
             '              实测印证：入表 {pw.n_shipped} 题净{" "}\n'
             '              <span className="font-mono text-gray-200">\n'
             '                {pw.net_change_invariance.net_over_shipped_10}\n'
             '              </span>{" "}\n'
             '              = 完整 {pw.n_complete_pairs} 题净{" "}\n'
             '              <span className="font-mono text-gray-200">\n'
             '                {pw.net_change_invariance.net_over_complete_20}\n'
             '              </span>。\n'
             '            </li>\n',
             "", "O16")
    elif which == "O17":
        edit(PANEL,
             '            <li data-power-item="semantic">\n'
             '              <b>但「答案变了」不等于「概念变了」。</b>\n',
             '            <li data-power-item="semantic">\n'
             '              <b>答案改变率如下。</b>\n',
             "O17")
    elif which == "O18":
        edit(PANEL,
             "              条撞了 <b>{pw.token_cap}</b> token 上限\n"
             "              ⇒ 未知的那几题恰恰是<b>跑飞了</b>的题，\n"
             "              也就是干预影响最大的那批。这才是这批数据真正的选择效应。\n",
             "              条没有跑完。\n",
             "O18")
    elif which == "O19":
        edit(PANEL,
             '            <li data-power-item="domain">\n'
             '              上面那 {pw.changed_but_still_wrong_magnitude.n} 次里还有{" "}\n'
             '              <b>{pw.changed_but_still_wrong_magnitude.out_of_domain_labels.length}</b>{" "}\n'
             '              次两臂答案都落在 AIME 答案域之外（\n'
             '              {pw.changed_but_still_wrong_magnitude.out_of_domain_labels.join("、")}\n'
             '              ），它们的「错」是<b>域外判定</b>，对净变化没有贡献。\n'
             '            </li>\n',
             "", "O19")
    elif which == "O20":
        edit(PANEL,
             "            <b>不能说</b>「干预对答案正确性无影响」，也<b>不能说</b>「准确率没有下降」——\n"
             "            净变化 0 只是「1 修 1 破」相抵，两边区间都极宽。\n",
             "            <b>不能说</b>「干预对答案正确性无影响」。\n",
             "O20")
    elif which == "O21":
        # 属性照旧（data-base-right 仍读产物），只有可见数字写死。
        edit(PANEL,
             '            基线答对 <b className="font-mono text-gray-200">{pw.baseline_correct}</b>\n',
             '            基线答对 <b className="font-mono text-gray-200">10</b>  // MUT_O21\n',
             "O21")
    elif which == "O22":
        # 唯一一条改 data-* 的。
        edit(PANEL,
             "             data-n-complete={pw.n_complete_pairs}\n",
             "             data-n-complete={10}  // MUT_O22\n",
             "O22")
    elif which == "O23":
        edit(PANEL,
             '              {" "}不会，而且这<b>不是数据碰巧</b>，是定理 ——',
             '              {" "}不会，而且这**不是数据碰巧**，是定理 ——',
             "O23")
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


def check_table_consistency():
    """MUTS 与 apply() 的分支必须一一对应，缺一个就当场 ABORT。

    ⚠ 这条守卫是被一次真实事故逼出来的：我用「按行号切片拼接」的方式
    插入 J 组变异，结果把 I 组的 MUTS 条目**和** apply 分支各吃掉一段。
    症状非常隐蔽 —— apply() 里的 `raise SystemExit("unknown mutation ...")`
    发生在 main() 的**任何输出之前**，所以那一轮跑出来
    O23 那一节**一行 RESULT 都没有**，看起来像「没跑」，
    而实际上前面 11 条已经跑过、后面还没跑。
    ⇒ 少一条分支 = 少一条回归，而它自己不会吭声。
    """
    import re
    branches = set(re.findall(r'(?:if|elif) which == "([A-Z0-9]+)"', read(__file__)))
    missing = sorted(set(MUTS) - branches - {"BASE"})
    extra = sorted(branches - set(MUTS))
    if missing:
        raise SystemExit(
            "ABORT MUTS 里有 %d 条变异在 apply() 里没有分支：%s\n"
            "    ⇒ 变异台自己坏着，不是变异没打中。补分支再跑。"
            % (len(missing), ", ".join(missing)))
    if extra:
        raise SystemExit("ABORT apply() 里有 %d 条 MUTS 没登记的分支：%s"
                         % (len(extra), ", ".join(extra)))


# --- 源级判据：渲染里根本看不见的那一类 ------------------------------
#
# O7 把 `<Stat label="first changed step" v={stats.fdMed != null ? `~${stats.fdMed}` : "—"}`
# 换成字面量 v="~13"。而产物里的 `med()` 取的是**上中位数**
# （xs[Math.floor(n/2)]，不是均值 —— 46 个非空值里 xs[23] 正好是 13），
# 于是**页面渲染逐字相同**。
#
# ⇒ G3 那类「读可见文案、和产物逐值比对」的判据，在**构造上**就抓不到它：
#    字面量一旦等于真值，读者看到的、data-* 里的、全部都一样。
#    这类变异一旦「绿」，很容易被读成「这条判据没牙」，而真相是
#    **它在渲染这一层无解**。
#
# ⇒ 「这个数字是从产物读的，还是写死的」这个问题，只能在源码里问。
#    下面 SRC_BACKUP 登记的变异在渲染上按构造为绿，由源级判据负责。
SRC_BACKUP = {
    "O7": "S1",   # 硬编码 ~13；真值也是 13 ⇒ 渲染零差异
}


def src_criteria():
    """源级判据：只读源码，不读渲染。返回 {cid: (是否被违反, 说明)}。

    S1 盯「<Stat> 的值是字面量」这一整类，而不是只盯 O7 那一个 13。
    当前源码里 6 个 <Stat> 的值全部来自产物/状态，字面量 0 个。
    判据写的是**类**，所以下一次有人写死任何一个 Stat 都会红。
    """
    lits = re.findall(r'<Stat[^>]*\bv="[^"]*"', read(PANEL))
    return {"S1": (len(lits) > 0,
                   "面板里有 %d 个 <Stat> 的值写成了字面量（应为 0）：%s"
                   % (len(lits), "; ".join(l[:60] for l in lits[:3]))
                   if lits else "6 个 <Stat> 的值全部来自产物/状态，0 个字面量")}


def main():
    check_table_consistency()
    which = sys.argv[1] if len(sys.argv) > 1 else "BASE"
    if which not in MUTS:
        raise SystemExit("unknown mutation " + which)
    desc, expect_red = MUTS[which]
    print("=== %s: %s" % (which, desc))

    backup()
    verify_source_untouched()
    # ⚠ 源级判据必须在这里取快照，**不能**等到 main() 末尾。
    #   末尾已经过了 finally: restore()，源码早就还原成干净版了 ——
    #   于是 O7 明明写着字面量，S1 却报「0 个字面量」。
    #   这就是「验证读的不是被验证的那份东西」：它读的是还原后的源码，
    #   于是永远绿，绿得毫无意义。
    src_state = dict(src_criteria())
    for cid, (hit, why) in src_state.items():
        print("    [src] %s %s" % (cid, "RED  " + why if hit else "green " + why))
    if expect_red:
        try:
            apply(which)
        except SystemExit as e:
            print("    " + str(e))
            restore()
            return 3
        print("    mutation written")
        # 施加之后**立刻**重取：上面的快照是施加前的
        src_state = dict(src_criteria())
        for cid, (hit, why) in src_state.items():
            print("    [src:mutated] %s %s"
                  % (cid, "RED  " + why if hit else "green " + why))
    else:
        print("    pristine source, nothing to write")

    bport = int(os.environ.get("MUT_BACKEND", "9503"))
    try:
        write(WSEND, re.sub(r"export const DEFAULT_WS_PORT_CANDIDATES = \[.*?\];",
                            "export const DEFAULT_WS_PORT_CANDIDATES = [%d];" % bport,
                            read(WSEND), count=1))
        if not build_frontend():
            return 3
        # ⚠ 沙箱禁所有信号 ⇒ 每一轮 next start 都永久占着它的端口。
        #   我用 10100-10160 跑了十来轮之后整段被占满，free_port 直接
        #   ABORT，而 run_all_outcome.sh 把 ABORT 之后的输出全冲掉了
        #   ——症状是「跑着跑着就停了，没有任何报错」。
        #   ⇒ 端口段必须放在一个每轮都会变的高位，且 ABORT 要自己喊出来。
        fport = free_port(21000, 22000)
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
        if r.returncode == 0 and "[FAIL]" not in r.stdout and not any(
                h for h, _ in src_state.values()):
            print("    RESULT BASE OK - all render criteria pass, "
                  "and the source-level criteria are clean too")
            return 0
        print("    RESULT BASE BAD - criteria are red on pristine source")
        return 1
    if ("[FAIL] " + expect_red) in r.stdout:
        print("    RESULT %s OK - %s went red" % (which, expect_red))
        return 0
    # 渲染层没红。这**不等于**「这条判据没牙」—— 先问这条是不是按构造
    # 就不可能在渲染上变红（值一旦写死成真值，页面逐字相同）。
    if which in SRC_BACKUP:
        cid = SRC_BACKUP[which]
        hit, why = src_state[cid]
        if hit:
            print("    RESULT %s OK - %s stayed green **by construction** "
                  "(the literal equals the true value, so the render is "
                  "byte-identical), but source-level %s is red: %s"
                  % (which, expect_red, cid, why))
            return 0
        print("    RESULT %s BAD - %s stayed green and %s is clean too: %s"
              % (which, expect_red, cid, why))
        return 1
    print("    RESULT %s BAD - %s stayed green, so that criterion has no teeth"
          % (which, expect_red))
    return 1


if __name__ == "__main__":
    sys.exit(main())
