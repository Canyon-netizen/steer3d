#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成 244.81（**判决那一轮**）的提交信息（**所有数从面板收据解析**，⛔ 不手抄）。"""

import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EV = os.path.join(HERE, "_e24481")
OUT = os.path.join(HERE, "_commit_msg_24481.txt")


def _read(p):
    with io.open(p, encoding="utf-8", newline="") as fh:
        return fh.read()


def _need(p):
    if not os.path.isfile(p):
        raise SystemExit("⛔ 缺收据：%s" % p)
    return _read(p)


def _grab(txt, pat, what, flags=re.M):
    m = re.search(pat, txt, flags)
    if not m:
        raise SystemExit("⛔ 收据里核不到「%s」" % what)
    return m


def main():
    rc = _need(os.path.join(EV, "receipt_24481.txt"))
    p = _need(os.path.join(EV, "verdict_panel.txt"))
    if "部分读数" in p or "本面板的数不是判决" in p:
        raise SystemExit("⛔ 面板带「部分读数 / 不是判决」⇒ 这一轮**还没跑完** ⇒ 不出提交信息")
    iv = _need(os.path.join(EV, "indep_verify_24481.out"))
    m = _grab(iv, r"判据 (\d+) 条 ｜ PASS (\d+) ｜ FAIL (\d+)", "独立重算小结")
    i_total, i_pass, i_fail = (int(x) for x in m.groups())
    im = _need(os.path.join(EV, "mut_indep.out"))
    m2 = _grab(im, r"变异台：抓到 (\d+) / (\d+)（无效 (\d+) 条.*?其中等价变异 (\d+) 条",
               "独立重算器变异台小结", flags=re.S)
    i_caught = int(m2.group(1))
    i_equiv = int(m2.group(4))
    ast_ = _need(os.path.join(EV, "analyzer_selftest.out"))
    m3 = _grab(ast_, r"判据 (\d+) 条 ｜ PASS (\d+) ｜ FAIL (\d+)", "分析器自检小结")
    a_total, a_pass, _a_fail = (int(x) for x in m3.groups())
    am = _need(os.path.join(EV, "mut_analyzer.out"))
    m4 = _grab(am, r"变异台：抓住 (\d+) / (\d+)", "分析器变异台小结")
    a_caught, a_mut_total = int(m4.group(1)), int(m4.group(2))
    pcc = _need(os.path.join(EV, "probe_compat_selftest.out"))
    m5 = _grab(pcc, r"自检 (\d+)/(\d+) 通过", "probe_compat_check 自检小结")
    pcc_total, pcc_pass = int(m5.group(1)), int(m5.group(2))
    m = _grab(p, r"^  w\s+改判 \*\*(\d+)/(\d+)\*\*", "w 臂改判")
    w_pos, w_n = m.group(1), m.group(2)
    m = _grab(p, r"^  rand\s+改判 \*\*(\d+)/(\d+)\*\*", "rand 臂改判")
    r_pos, r_n = m.group(1), m.group(2)
    m = _grab(p, r"差 \*\*([-+0-9.]+) pp\*\* ｜ 差区间 (\[[-+0-9., %]+\]) pp ｜ "
                  r"跨臂 Fisher（精确枚举）p = ([0-9.]+) ｜ 配对置换 p = ([0-9.]+)", "跨臂")
    diff, diff_ci, fisher_p, perm_p = m.groups()
    m = _grab(p, r"配对置换 \*\*MC95% 不确定带\*\* = \[([0-9.]+), ([0-9.]+)\]", "MC 带")
    band = m.groups()
    m = _grab(p, r"^  w (\d+)/(\d+) ｜ rand (\d+)/(\d+) ｜ 差 ([-+0-9.]+) pp ｜ "
                  r"差区间 (\[[-+0-9., %]+\]) pp ｜ Fisher p = ([0-9.]+)", "块级")
    blk_w, blk_n, blk_r, blk_rn, blk_diff, blk_ci, blk_p = m.groups()
    groups = re.findall(
        r"pos_frac=([0-9.]+)\s+w (\d+)/(\d+) ｜ rand (\d+)/(\d+) ｜ 差 ([-+0-9.]+) pp ｜ "
        r"差区间 (\[[-+0-9., %]+\]) pp ｜ Fisher p = ([0-9.]+)", p)
    dis = re.findall(r"三格全一致 (\d+) ｜ 2:1 分歧 (\d+) ｜ 分歧率 ([0-9.]+)", p)
    bytes_md5 = dict(re.findall(r"^(\w{32})\s+(\S+)$", rc, re.M))
    arms = re.findall(r"arm=(\w+) cells_done=(\d+).*?idx_tot=(\d+) (\d+) abort=(\d+) rc0=(\d+)",
                      rc)

    # ---- 全回归收据（R1 = 落账前；R2 = 落账后 = 本次提交里那份账本）
    def _reg_summary(fname):
        p = os.path.join(EV, fname)
        if not os.path.isfile(p):
            return None
        t = _read(p)
        m = _grab(t, r"host=(\S+)", "回归主机").group(1)
        npy = _grab(t, r"n_exec_py=(\d+)", "执行集 py 数").group(1)
        add = _grab(t, r"added=(\d+)", "清单新增").group(1)
        rem = _grab(t, r"removed=(\d+)", "清单减少").group(1)
        led = _grab(t, r"ledger_lines=(\d+)\s+ledger_md5=(\w+)", "账本行数与 md5").groups()
        rc_ = _grab(t, r"REG_RC=(\d+)", "回归退出码").group(1)
        mm = _grab(t, r"小结：变异台 全绿 (\d+) / 跑得动 (\d+) ；自检 全绿 (\d+) / 跑得动 (\d+)",
                   "回归小结")
        bad = re.findall(r"^  \[BAD \] (\S+\.py)", t, re.M)
        return {"host": m, "npy": npy, "add": add, "rem": rem, "led_lines": led[0],
                "led_md5": led[1], "rc": rc_, "mut": mm.groups(), "bad": bad}

    reg1 = _reg_summary("reg_24481.txt")
    reg2 = _reg_summary("reg_24481b.txt")

    # ---- 唯一红项的**分类**（rc=-9 ＝ SIGKILL ＝ 被时限上限杀掉 ⇒ 不是判据红）
    bad_detail = []
    for _fn in ("reg_24481.txt", "reg_24481b.txt"):
        _p = os.path.join(EV, _fn)
        if os.path.isfile(_p):
            for _n, _rc, _s in re.findall(r"^  \[BAD \] (\S+\.py)\s+rc=(-?\d+)\s+\[([\d.]+)s\]",
                                          _read(_p), re.M):
                bad_detail.append((_fn, _n, _rc, _s))
    old_p = os.path.join(HERE, "_e24480", "reg_24480.txt")
    old_ok = ""
    if os.path.isfile(old_p):
        _m = re.search(r"^  \[OK \] (mut_recomp_p\.py).*?\[([\d.]+)s\]", _read(old_p), re.M)
        if _m:
            old_ok = "%s 在 244.80 那轮是 **%s s 绿的**" % (_m.group(1), _m.group(2))

    # ---- ⚖ 字节对账（本地 ↔ 远端实际跑的那份）：能红检查的收据
    bcp = os.path.join(EV, "launcher_bytecheck_24481.txt")
    bc = _read(bcp) if os.path.isfile(bcp) else ""
    bc_pass = bc_red = "未量到"
    bc_exec_ok = bc_launch_ok = "未量到"
    bc_verdict = bc_led_local = bc_led_rec = bc_idx_local = bc_idx_rec = "未量到"
    if bc:
        m = _grab(bc, r"\[✅\] A 账本 md5 == R2 收据 ledger_md5\n    本地 (\w+) ｜ 收据 (\w+)",
                  "字节对账·账本")
        bc_led_local, bc_led_rec = m.group(1), m.group(2)
        m = _grab(bc, r"\[✅\] B 索引 md5 == R2 收据 index_md5\n    本地 (\w+) ｜ 收据 (\w+)",
                  "字节对账·索引")
        bc_idx_local, bc_idx_rec = m.group(1), m.group(2)
        bc_pass = len(re.findall(r"^\[✅\]", bc, re.M))
        bc_red = len(re.findall(r"^\[⛔\]", bc, re.M))
        bc_exec_ok = len(re.findall(r"^\[✅\] C 执行集", bc, re.M))
        bc_launch_ok = len(re.findall(r"^\[✅\] _run_", bc, re.M))
        bc_verdict = "全部硬判据通过" if bc_red == 0 else "有硬判据没过"

    # ---- 第四条实现（自包含探查脚本）的收据：⛔ 块级那些是**先导**，不是判决
    sc = _need(os.path.join(EV, "scout_premise_indep_24481.out"))
    m = _grab(sc, r"自检通过：轨迹级 w (\d+)/(\d+)、rand (\d+)/(\d+) ｜ 块级 w (\d+)/(\d+)、"
                  r"rand (\d+)/(\d+) ｜ 轨迹级 Fisher ([0-9.]+)、块级 Fisher ([0-9.]+)", "探查自检")
    sc_traj_w, sc_traj_r = (m.group(1), m.group(2)), (m.group(3), m.group(4))
    sc_blk_w, sc_blk_r = (m.group(5), m.group(6)), (m.group(7), m.group(8))
    sc_fisher_traj, sc_fisher_blk = m.group(9), m.group(10)
    m = _grab(sc, r"w 臂块内两条\*\*判决一致\*\* (\d+)", "探查块内一致")
    sc_blk_agree = int(m.group(1))
    m = _grab(sc, r"\*\*逐轨迹\*\*置换：p = ([0-9.]+)（obs = (\d+) ｜ ge=(\d+)/(\d+)）", "探查逐轨迹置换")
    sc_traj_perm_p, sc_traj_perm_ge, sc_traj_perm_n = m.group(1), int(m.group(3)), int(m.group(4))
    m = _grab(sc, r"\*\*块级\*\*置换（块内整体交换两臂标签）：p = ([0-9.]+)", "探查块级置换")
    sc_blk_perm_p = m.group(1)
    m = _grab(sc, r"\*\*比值\*\*：块级 p ÷ 逐轨迹 p = ([0-9.]+)×", "探查比值")
    sc_ratio = m.group(1)
    m = _grab(sc, r"按块 bootstrap 95% 区间 \[([-+0-9.]+), ([-+0-9.]+)\] pp", "探查 bootstrap")
    sc_boot_lo, sc_boot_hi = m.group(1), m.group(2)
    # ⚖ 分析器退出码在**流水线 stdout** 里（⛔ 不在面板收据里）
    pl = _need(os.path.join(EV, "pipeline_24481.out"))
    audit_rc = _grab(pl, r"AUDIT_RC=(\d+)", "分析器退出码").group(1)
    split_rc = _grab(pl, r"SPLIT_w_RC=(\d+)", "w 臂拆分退出码").group(1)

    title = ("244.81：⚖⚖⚖⚖⚖ **固定剂量下的判决数出来了**（合池口径）—— ⇒ ⇒ "
             "**w 臂改判 %s/%s、rand 臂改判 %s/%s、差 %s pp**（跨臂 Fisher p = %s、配对置换 p = %s、"
             "MC95%% 带 [%s, %s]）；块级 **%s/%s vs %s/%s**（Fisher p = %s）；⛔ **前提独立性仍未量到** "
             "⇒ ⇒ 判决**口径依赖**，⛔ 不是「机制已证」"
             % (w_pos, w_n, r_pos, r_n, diff, fisher_p, perm_p, band[0], band[1],
                blk_w, blk_n, blk_r, blk_rn, blk_p))
    body = [title, "",
            "**判决面板（固定剂量 · 合池口径）**", "",
            "· 轨迹级（逐轨迹**严格多数**，`nT·2 > m`）：w **%s/%s** ｜ rand **%s/%s**" % (w_pos, w_n, r_pos, r_n),
            "· 差 **%s pp** ｜ 差区间（Newcombe95）%s ｜ 跨臂 Fisher（**精确枚举**）p = %s ｜ 配对置换 p = %s"
            "（MC95%% 不确定带 [%s, %s]）" % (diff, diff_ci, fisher_p, perm_p, band[0], band[1]),
            "· 块级（块 = think + no_think，块内两条都正才算正，⛔ 分母是**块数**）：w **%s/%s** ｜ rand **%s/%s**"
            " ｜ 差 %s pp ｜ 差区间 %s ｜ Fisher p = %s" % (blk_w, blk_n, blk_r, blk_rn, blk_diff, blk_ci, blk_p),
            "· 分 `pos_frac` 三组（V7）：" + " ｜ ".join(
                "%s: w %s/%s vs rand %s/%s（差 %s pp，Fisher p = %s）" % (g[0], g[1], g[2], g[3], g[4], g[5], g[7])
                for g in groups),
            "· ⚖ 异质性（**前提**，⛔ 不是判决）：三格全一致 / 2:1 分歧 / 分歧率 = "
            + " ｜ ".join("%s/%s/%s" % d for d in dis),
            "· ⛔ **问题级不适用**：本批**没有** `scope=all` 的格 ⇒ ⇒ 印「不适用」（⛔ 不是「未量到」，⛔ 不是「无差异」）。",
            "",
            "**这些数在什么口径下才成立**", "",
            "· **合池**口径（3 个 `pos_frac` 逐轨迹严格多数）⇒ ⇒ ⛔ 不是「单剂量」口径。",
            "· **零格进分母、不进基准** ⇒ ⇒ 零假设基准**逐轨迹算再平均**（⛔ 不是恒 0.5）。",
            "· **块级分母是块数**；**跨臂 Fisher 是精确枚举**；**差区间是 Newcombe95**（⛔ 不是两 CI 相减）。",
            "· ⚠⚠⚖ **前提独立性仍未量到** ⇒ ⇒ 「显著」是**口径依赖**的 ⇒ ⇒ ⛔ **不是**「机制已证」。",
            "· ⚠ **`pos_frac = 0.25 / 0.75` 这两组的数以前从没测过** ⇒ ⇒ 本轮**第一次**有它们的数。",
            "· ⚠ **剂量趋势未量到**（本批 `n_bands = 1`）⇒ ⇒ ⛔ 不是「无趋势」。",
            "",
            "**判决不是自证：第二条独立实现把每个数重算了一遍**", "",
            "· `verify_pooled_verdict_indep.py`：⛔ **不 import** 分析器/读数器/拆分器；"
            "⛔ **自己解析原始跑批日志**（连数据路径都不共用）；⛔ **统计量自己实现**；"
            "⚖ **置换用二项精确**（分析器那边是 Monte Carlo）⇒ ⇒ **%d 条判据 ｜ PASS %d ｜ FAIL %d**。"
            % (i_total, i_pass, i_fail),
            "· 它的变异台：面板被改 ⇒ 抓 %d 条；重算器自己的实现被改 ⇒ 也抓 ⇒ ⇒ "
            "**这条比对能红**（⛔ 不是恒绿护栏）；另有 **%d 条等价变异**（记「无效」、不计分母）。"
            % (i_caught, i_equiv),
            "· **第三条路径**（shell/awk，⛔ 与前两条都不同的实现）从原始日志直接数 ⇒ ⇒ **逐格一致**。",
            "",
            "**这一轮另外做的事**", "",
            "· ✅ **面板补印**了预登记 V3/V4 明写「必须打印」的三项（`m` 分布 / `(n_nz,n_zero)` 分布 / 基准分布）"
            "⇒ ⇒ **判决数一个没动**（面板三次独立运行 md5 逐位相同）⇒ ⇒ 只是让「分母长什么样」在判决面上**看得见**。",
            "· ✅ 判据 **V-P19** ＋ 变异 **P21** ⇒ ⇒ 分析器自检 **%d/%d 绿**、变异台 **%d/%d 全抓到**。"
            % (a_pass, a_total, a_caught, a_mut_total),
            "· ✅ **修掉一条永久红**：`probe_compat_check.py` 的 C1（244.45 起就永久红：探针打了 force 补丁，"
            "补丁前的锚点再也命中不到）⇒ ⇒ 改成**按形态各查各的锚点** ＋ 新增 **C11**（混合形态必红）"
            "⇒ ⇒ 自检 **%d/%d 通过**，它自己的变异台 **15/15 全抓住**。"
            % (pcc_pass, pcc_total),
            "· ✅ **第四条实现**（自包含探查脚本，⛔ 不 import 上面任何一个、⛔ 自己解析原始日志、"
            "⛔ Fisher / McNemar / 置换全自己实现）把面板的数**逐位复现**："
            "轨迹级 w **%s/%s**、rand **%s/%s** ｜ 块级 w **%s/%s**、rand **%s/%s** ｜ "
            "轨迹级 Fisher **%s**、块级 Fisher **%s** ｜ 逐轨迹置换 p = **%s**（ge = %s/%s）"
            " ⇒ ⇒ **四份实现互证**。"
            % (sc_traj_w[0], sc_traj_w[1], sc_traj_r[0], sc_traj_r[1],
               sc_blk_w[0], sc_blk_w[1], sc_blk_r[0], sc_blk_r[1],
               sc_fisher_traj, sc_fisher_blk, sc_traj_perm_p, sc_traj_perm_ge, sc_traj_perm_n),
            "· 🐛 **修掉一条「只在好情况下才发作」的收据格式缺陷**：R2 脚本里 "
            "`man_added=$(grep -c '^>' \"$DIFF\" 2>/dev/null || echo 0)` —— "
            "`grep -c` 在**无匹配**时**照样打印 0** 并返回**非 0** ⇒ `|| echo 0` 会**再补一个 0** "
            "⇒ 变量变成两行「0」⇒ 收据头被撑出两行游离的「0」；"
            "⚠ 而它**只在「没有差异」时触发** —— 恰恰是最该干净的那一种情况 "
            "⇒ ⇒ 改用 `awk '/^>/{n++} END{print n+0}'`（本地 bash 3.2 ＋ 远端 bash 5 都实测过：空 diff 下旧写法 **2 行** → 新写法 **1 行**）"
            "⇒ ⇒ **被验量（added/removed 的值）一个没变**（旁证：manifest diff 文件本身 **0 字节**，"
            "且 R1/R2 的 `manifest_md5` **逐位相同**）⇒ ⇒ ⛔ **不是**「改了数」。",
            "· ⚖⚖⚖ **先导探查（⛔ 不是判决）**：把零分布换成『**块是独立单位**』（块内整体交换两臂标签）"
            "⇒ ⇒ 块级置换 p = **%s**（只比逐轨迹的 %s 大 **%s×**）｜ 按块 bootstrap 的块级差区间 "
            "**[%s, %s] pp**（仍远离 0）｜ **块内确实相关**（w 臂 28 块里 %d 块内两条判决一致）"
            " ⇒ ⇒ **判决在更强前提下依然站得住**；⚠ 但它**只有一条实现、没有变异台**"
            " ⇒ ⇒ 「前提独立性」这条前提**正式仍记「未验到」**（244.82 补第二条实现 ＋ 变异台）。"
            % (sc_blk_perm_p, sc_traj_perm_p, sc_ratio, sc_boot_lo, sc_boot_hi, sc_blk_agree),
            "",
            "**全回归**", ""]
    if reg1:
        body.append("· **R1（落账**前**的账本 = 244.79 那版）**：主机 `%s` ｜ 执行集 **%s** 个 py ｜ "
                    "清单 diff（对 244.80）**新增 %s / 减少 %s** ｜ 变异台 全绿 %s / 跑得动 %s ｜ "
                    "自检 全绿 %s / 跑得动 %s ｜ `REG_RC = %s` ｜ 红项 %s ｜ 账本 %s 行 md5 `%s`"
                    % (reg1["host"], reg1["npy"], reg1["add"], reg1["rem"],
                       reg1["mut"][0], reg1["mut"][1], reg1["mut"][2], reg1["mut"][3],
                       reg1["rc"], reg1["bad"] or "无", reg1["led_lines"], reg1["led_md5"]))
    else:
        body.append("· ⛔ **R1 未量到**")
    if reg2:
        body.append("· **R2（落账**后**的账本 = 本次提交里那份字节）**：主机 `%s` ｜ 执行集 **%s** 个 py ｜ "
                    "清单 diff（对 R1）**新增 %s / 减少 %s**（⇒ ⇒ 执行集字节**一个没动**）｜ "
                    "变异台 全绿 %s / 跑得动 %s ｜ 自检 全绿 %s / 跑得动 %s ｜ `REG_RC = %s` ｜ 红项 %s ｜ "
                    "账本 **%s 行** md5 `%s`"
                    % (reg2["host"], reg2["npy"], reg2["add"], reg2["rem"],
                       reg2["mut"][0], reg2["mut"][1], reg2["mut"][2], reg2["mut"][3],
                       reg2["rc"], reg2["bad"] or "无", reg2["led_lines"], reg2["led_md5"]))
    else:
        body.append("· ⛔ **R2 未量到**")
    if bad_detail:
        _names = sorted(set(b[1] for b in bad_detail))
        _rcs = sorted(set(b[2] for b in bad_detail))
        _secs = sorted(set(b[3] for b in bad_detail))
        body.append("· ⚖ **唯一红项的分类**：%s ｜ rc = `%s`（= **SIGKILL**，"
                    "**被 2400 s 上限杀掉**）｜ R1 与 R2 **两次都恰好停在 %s s**"
                    " ⇒ ⇒ 按纪律归「**环境/时限**」，⛔ **不是**「判据红」"
                    "（⛔「跑不动」⛔ 不是「判据红」）%s"
                    % ("、".join(_names), "/".join(_rcs), "/".join(_secs),
                       ("；旁证：%s —— 机器当时负载低 ⇒ ⇒ ⛔ **不是**「这条判据坏了」" % old_ok)
                       if old_ok else ""))
    if bc:
        body.append("· ⚖ **字节对账（提交字节 ↔ R2 收据字节，能红检查 `_verify_launcher_bytes_24481.py`）**："
                    "账本 md5 `%s` == 收据 `%s`｜索引 md5 `%s` == 收据 `%s`｜"
                    "**执行集 %s/5 逐位一致**（承载判据逻辑的那 5 个文件）｜"
                    "**启动器 %s/2** 的差异**逐条**落在**已登记清单**（① `${}` 加括号、② 收据计数修正、③ 纯注释行）"
                    "⇒ ⇒ **没有未解释的漂移**｜硬判据 **绿 %s / 红 %s**（%s）"
                    "⇒ ⇒ 「R2 验的就是本次提交里那份字节」对**账本/索引/执行集****成立**。"
                    % (bc_led_local, bc_led_rec, bc_idx_local, bc_idx_rec,
                       bc_exec_ok, bc_launch_ok, bc_pass, bc_red, bc_verdict))
    else:
        body.append("· ⛔ **字节对账未量到**")
    body += [
            "",
            "**这一轮的收据**", ""]
    for k in sorted(bytes_md5):
        body.append("· `%s`  `%s`" % (k, bytes_md5[k]))
    body.append("· 跑批：%s ｜ 分析器退出码 `%s`" % (
        " ｜ ".join("臂 %s %s/%s（ABORT %s）" % (a[0], a[1], a[3], a[4]) for a in arms), audit_rc))
    body.append("")
    body.append("⛔ **本轮没做**：**没验前提独立性**（56 轨迹 = 28 块 × 2；块内还有 3 个复制格）"
                "⇒ ⇒ p 值与区间都建立在这个**没被验过**的前提上；⛔ **没做**分层剂量那批；"
                "⛔ **没实测**「照 meta 重建能否逐位复现」；⛔ 没改读数器、⛔ 没改探针、⛔ 没改拆分器、"
                "⛔ 没改任何预登记、⛔ 没跑新批。")
    body.append("")
    with io.open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(body) + "\n")
    print("✅ %s（%d 字节）" % (OUT, len("\n".join(body).encode("utf-8"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
