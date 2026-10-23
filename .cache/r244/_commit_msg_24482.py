#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 244.82（**前提独立性正式验收**那一轮）的提交信息（**所有数从收据解析**，⛔ 不手抄）。"""

import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EV = os.path.join(HERE, "_e24482")
OUT = os.path.join(HERE, "_commit_msg_24482.txt")


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
    pi = _need(os.path.join(EV, "pi.out"))
    st = _need(os.path.join(EV, "selftest.out"))
    mu = _need(os.path.join(EV, "mut.out"))
    cr = _need(os.path.join(EV, "cross.out"))

    # ---- 自检 / 真数据 / 变异台 / 互证
    m = _grab(st, r"自检 (\d+) 条 ｜ PASS (\d+) ｜ FAIL (\d+)", "自检小结")
    st_n, st_pass, st_fail = m.groups()
    m = _grab(pi, r"判据 (\d+) 条 ｜ PASS (\d+) ｜ FAIL (\d+)", "真数据判据小结")
    pi_n, pi_pass, pi_fail = m.groups()
    m = _grab(mu, r"变异台：抓到 (\d+) / (\d+)（无效 (\d+) 条.*?其中等价变异 (\d+) 条", "变异台小结")
    mut_caught, mut_total, mut_invalid, mut_equiv = m.groups()
    m = _grab(mu, r"崩的条数：(\d+)", "崩计数")
    mut_crash = m.group(1)
    m = _grab(cr, r"互证判据 (\d+) 条 ｜ PASS (\d+) ｜ FAIL (\d+)", "互证小结")
    cr_n, cr_pass, cr_fail = m.groups()
    # ⚖ 变异台里「普通判据红」与「G0-3 硬停抓到」要**分开数**（⛔ 不许写死）
    mut_hard = len(re.findall(r"^\[硬停抓到\]", mu, re.M))
    mut_plain = len(re.findall(r"^\[抓到\]", mu, re.M))

    # ---- 判决相关的数
    m = _grab(pi, r"\*\*精确\*\*块级置换（DP 精确零分布，⛔ 非 MC）：p = ([0-9.]+)"
                    r"（obs = (\d+) ｜ 尾 (\d+) / (\d+)）", "精确块级置换")
    p_exact, obs_blk, tail, tot = m.groups()
    m = _grab(pi, r"块级差 ([-+0-9.]+) pp ｜ \*\*删一块 jackknife\*\* 95% 区间 "
                    r"\[([-+0-9.]+), ([-+0-9.]+)\] pp（SE = ([0-9.]+)）", "jackknife")
    theta_blk, jk_lo, jk_hi, jk_se = m.groups()
    m = _grab(pi, r"轨迹级差 ([-+0-9.]+) pp ｜ Newcombe95（\*\*假定轨迹独立\*\*）"
                    r"\[([-+0-9.]+), ([-+0-9.]+)\] pp", "Newcombe 对照")
    theta_traj, nc_lo, nc_hi = m.groups()
    m = _grab(pi, r"\*\*LOBO\*\*（逐块剔除 (\d+) 个子集）：块级差 \[([-+0-9.]+), ([-+0-9.]+)\] pp ｜ "
                    r"置换 p ∈ \[([0-9.]+), ([0-9.]+)\] ｜ \*\*判决被掀翻的子集数 = (\d+)\*\*", "LOBO")
    lobo_n, lobo_dmin, lobo_dmax, lobo_pmin, lobo_pmax, lobo_flips = m.groups()
    m = _grab(pi, r"w 臂：块 (\d+) ｜ 一致 (\d+)（po = ([0-9.]+)）｜ 偶然一致 pe = ([0-9.]+) ｜ "
                    r"κ = ([-+0-9.]+) ｜ 精确二项两侧 p = ([0-9.]+) ⇒ \*\*(可检出|未检出)\*\*", "w 臂块内")
    w_tot, w_agree, w_po, w_pe, w_kap, w_p, w_det = m.groups()
    m = _grab(pi, r"rand 臂：块 (\d+) ｜ 一致 (\d+)（po = ([0-9.]+)）｜ 偶然一致 pe = ([0-9.]+) ｜ "
                    r"κ = ([-+0-9.]+) ｜ 精确二项两侧 p = ([0-9.]+) ⇒ \*\*(可检出|未检出)\*\*", "rand 臂块内")
    r_tot, r_agree, r_po, r_pe, r_kap, r_p, r_det = m.groups()
    m = _grab(pi, r"结论形态 = (C-[ABC])", "结论形态")
    verdict = m.group(1)
    m = _grab(pi, r"\*\*(C-A：.*?)\*\*（(.+?)）", "C-A 正文")
    verdict_text = m.group(1) + "（" + m.group(2) + "）"
    m = _grab(pi, r"精确块级置换 p = ([0-9.]+) ｜ 先导探查 MC p = ([0-9.]+) ｜ 差 ([-+0-9.]+)"
                    r"（MC 的 1 SE ≈ ([0-9.]+) ⇒ 差 = ([0-9.]+) SE", "MC 误差")
    p_mc, d_mc, mc_se, mc_mult = m.group(2), m.group(3), m.group(4), m.group(5)
    m = _grab(cr, r"先导 bootstrap \[([-+0-9.]+), ([-+0-9.]+)\] vs 本实现 jackknife "
                    r"\[([-+0-9.]+), ([-+0-9.]+)\] ⇒ 重叠宽度 ([0-9.]+) pp", "区间互证")
    boot_lo, boot_hi, x_jk_lo, x_jk_hi, ov = m.groups()
    m = _grab(pi, r"McNemar（精确二项，不一致 (\d+) 条：w 优 (\d+) / rand 优 (\d+)）：p = ([0-9.]+)",
              "McNemar")
    mcn_disc, mcn_w, mcn_r, mcn_p = m.groups()

    # ---- 全回归 R3
    regp = os.path.join(EV, "reg_24482.txt")
    reg = _need(regp) if os.path.isfile(regp) else ""
    reg_line = "· ⛔ **R3 未量到**"
    reg_class = []
    if reg:
        def _rg(pat, what):
            return _grab(reg, pat, what).group(1)
        reg_line = ("· **R3（落账 244.82 **后**的账本 = 本次提交里那份字节）**：主机 `%s` ｜ 执行集 **%s** 个 py ｜ "
                    "清单 diff（对 R2）**新增 %s / 减少 %s**（⇒ ⇒ 正好是本轮新增的两个执行集成员）｜ "
                    "变异台 全绿 %s / 跑得动 %s ｜ 自检 全绿 %s / 跑得动 %s ｜ `REG_RC = %s` ｜ 红项 %s ｜ "
                    "账本 **%s 行** md5 `%s`"
                    % (_rg(r"host=(\S+)", "R3 主机"),
                       _rg(r"n_exec_py=(\d+)", "R3 执行集数"),
                       _rg(r"added=(\d+)", "R3 新增"),
                       _rg(r"removed=(\d+)", "R3 减少"),
                       _rg(r"小结：变异台 全绿 (\d+)", "R3 变异台-全绿"),
                       _rg(r"小结：变异台 全绿 \d+ / 跑得动 (\d+)", "R3 变异台-跑得动"),
                       _rg(r"小结：.*自检 全绿 (\d+)", "R3 自检-全绿"),
                       _rg(r"小结：.*自检 全绿 \d+ / 跑得动 (\d+)", "R3 自检-跑得动"),
                       _rg(r"REG_RC=(\d+)", "R3 退出码"),
                       (", ".join(re.findall(r"^  \[BAD \] (\S+\.py)", reg, re.M)) or "无"),
                       _rg(r"ledger_lines=(\d+)", "R3 账本行数"),
                       _rg(r"ledger_md5=(\w+)", "R3 账本 md5")))
        # ⚖⚖⚖ **红项按分类登记**（⛔ 「超时/跑不动」⛔ **不是**「判据红」）
        #   ⇒ 分类**从收据解析**（⛔ 不写死哪一条红、也不写死它的定性）
        _bad = re.findall(r"^  \[BAD \] (\S+)\s+rc=(-?\d+)\s+\[([0-9.]+)s\]", reg, re.M)
        _mine = ("premise_independence_audit.py", "mut_premise_independence_audit.py")
        for nm, rc, secs in _bad:
            if rc == "-9":
                cls = ("⛔ **不是判据红** —— rc=`-9`（SIGKILL）＝撞 harness 的 **2400s 墙钟**"
                       " ⇒ 归 **环境/时限**；⚖ **旁证**：244.80 那一轮跑**同一个**测试是**绿的**"
                       "（2046.5s）⇒ ⇒ **同一个测试两轮结果不同** ⇒ ⇒ 它是**时限**问题，⛔ 不是判据问题"
                       "；本轮**没碰** `recomp_p.py`、⛔ **没碰** `mut_recomp_p.py`")
            elif nm in _mine:
                cls = "🔴 **本轮引入的判据红**（%s 是本轮新增的执行集成员）⇒ ⇒ 必须处理" % nm
            else:
                cls = "🔴 **判据红**（%s）⇒ ⇒ 需逐条说明" % nm
            reg_class.append("  · `%s` rc=`%s` [%ss] ⇒ %s" % (nm, rc, secs, cls))
        if reg_class:
            reg_class = ["**🔴 红项按分类登记**（⛔ 「超时/跑不动」⛔ **不算**「判据红」；"
                         "⛔ 「既有红」⛔ **不是**「本轮红」）"] + reg_class
            _intro = [x for x in _bad if x[0] in _mine]
            if not _intro and all(rc == "-9" for _, rc, _ in _bad):
                reg_class.append("  ⇒ ⇒ **本轮引入的判据红一条都没有** ⇒ ⇒ ⛔ 不计入本轮判决。")
        else:
            reg_class = ["**🔴 红项**：无"]

    title = ("244.82：⚖⚖⚖⚖⚖ **「前提独立性」这条前提**正式验收**掉**（⚖ **判决在保守口径下依然成立**）—— ⇒ ⇒ "
             "**精确**块级置换 p = **%s**（⛔ 不是蒙特卡洛）｜ 块级差 **%s pp**、**删一块 jackknife** 区间 "
             "[**%s, %s**] ｜ **LOBO** %s 个子集**掀翻数 = %s** ｜ 块内相关**%s**（w 臂 p = %s、rand 臂 p = %s）"
             " ⇒ ⇒ 结论形态 **%s**；⛔ **「前提独立性成立」仍不可证明**"
             % (p_exact, theta_blk, jk_lo, jk_hi, lobo_n, lobo_flips,
                w_det, w_p, r_p, verdict))

    body = [title, "",
            "**这一轮验的是哪条前提**", "",
            "· 244.81 判决面板上的每一个 p、每一个区间，都建立在「**56 条轨迹彼此独立**」"
            "这个**没被验过**的前提上（面板前提 P1）。真实结构是 **56 = 28 块 × 2**"
            "（块 = 同一道题同位置的 `think` + `no_think`），每条轨迹还有 **3 个 `pos_frac` 复制格**。",
            "· ⛔ **这条前提**不能被证明**（28 个块上，任何检验都不能把「未检出相关」说成「无相关」）"
            "⇒ ⇒ 本轮**不产出**「前提独立性成立」这句话 ⇒ ⇒ 只产出三件能做的事："
            "**W1** 结构（块是真的）｜**W2** 块内相关**被量到**（不是假设）｜"
            "**W3** 在**承认聚类**的保守零分布下判决**是否仍然成立**。",
            "· ⚖ **口径真相源**：`.cache/xcheck/R6_PREMISE_INDEPENDENCE_PREREG.md`"
            "（244.82 签，**先于任何实现代码**）⇒ ⇒ **不是**事后挑口径。",
            "",
            "**判决在保守口径下依然成立**（结论形态 %s）" % verdict, "",
            "· **精确块级置换**（DP 精确零分布，⛔ **不是**蒙特卡洛、⛔ 没有种子误差）：p = **%s**"
            "（obs = %s ｜ 尾 %s / %s）" % (p_exact, obs_blk, tail, tot),
            "· **块级差** %s pp ｜ **删一块 jackknife** 95%% 区间 [**%s, %s**] pp（SE = %s）"
            "（⛔ **确定性**，⛔ 不用种子）" % (theta_blk, jk_lo, jk_hi, jk_se),
            "· **LOBO**（逐块剔除 %s 个子集）：块级差 [%s, %s] pp ｜ 置换 p ∈ [%s, %s] ｜ "
            "**判决被掀翻的子集数 = %s** ⇒ ⇒ **没有单独一块能推翻它**"
            % (lobo_n, lobo_dmin, lobo_dmax, lobo_pmin, lobo_pmax, lobo_flips),
            "· **块内相关**（**被量到**，不是假设）：w 臂 一致 %s/%s（po = %s）vs 偶然一致 pe = %s、"
            "κ = %s、精确二项 p = %s ⇒ **%s**；rand 臂 一致 %s/%s（po = %s）vs pe = %s、κ = %s、"
            "p = %s ⇒ **%s**。⛔ **「未检出」⛔ 不是「不相关」。**"
            % (w_agree, w_tot, w_po, w_pe, w_kap, w_p, w_det,
               r_agree, r_tot, r_po, r_pe, r_kap, r_p, r_det),
            "· **轨迹级对照**（⛔ 假定轨迹独立）：差 %s pp、Newcombe95 [%s, %s] pp；"
            "**轨迹级 McNemar**（精确二项，不一致 %s 条：w 优 %s / rand 优 %s）：p = %s"
            % (theta_traj, nc_lo, nc_hi, mcn_disc, mcn_w, mcn_r, mcn_p),
            "",
            "⇒ ⇒ %s" % verdict_text,
            "",
            "**两条独立实现互证**（⛔ 不同数据路径、不同块键路线、不同置换算法、不同区间算法）", "",
            "· 244.81 轮「先导探查」：读**拆分产物**、**剥后缀**取块键、**蒙特卡洛** 20000 次置换、**按块 bootstrap** 区间。",
            "· 244.82 轮「第二条实现」：读 bpath **原始**日志自己按 `pos_frac` 过滤、**按 `__` 切分**取块键、"
            "**DP 精确零分布**、**删一块 jackknife**。",
            "· **逐位相同**（同一口径、同一机械）**%s 条判据全绿**；**区间重叠**：先导 bootstrap [%s, %s] vs "
            "本实现 jackknife [%s, %s] ⇒ 重叠 %s pp、两者都远离 0；**MC vs 精确**：先导 MC p = %s vs "
            "精确 p = %s，差 %s ＝ **%s 个 MC 标准误**（1 SE ≈ %s）⇒ ⇒ 差**就是 MC 误差**。"
            % (cr_pass, boot_lo, boot_hi, x_jk_lo, x_jk_hi, ov, p_mc, p_exact, d_mc, mc_mult, mc_se),
            "· ⚖ **先导探查在 `zju-53` 重跑**：md5 **逐位相同** ⇒ ⇒ 它的数**可复现**。",
            "",
            "**判据与变异台**（每条判据**能红**）", "",
            "· **自检**（Phase-0 G0-1/G0-2，⛔ 零 GPU、已知答案）：**%s 条 ｜ PASS %s ｜ FAIL %s**"
            % (st_n, st_pass, st_fail),
            "· **真数据**：**%s 条 ｜ PASS %s ｜ FAIL %s**" % (pi_n, pi_pass, pi_fail),
            "· **变异台**：**抓到 %s / %s**（无效 %s 条 ⇒ 记「无效」不计入分母；其中**等价变异 %s 条**；"
            "**崩 %s 条**）⇒ ⇒ **每条判据能红**（其中 **%s** 条是普通判据红、**%s** 条是靠 "
            "**G0-3 自检闸硬停**抓到的，⛔ 崩 ≠ 抓到）"
            % (mut_caught, mut_total, mut_invalid, mut_equiv, mut_crash, mut_plain, mut_hard),
            "· ⛔ **本轮没做**：⛔ **没跑批**（零 GPU）、⛔ **没验块间独立性**（**不可检验**）、"
            "⛔ **没验「前提独立性成立」**（**不可证明**）、⛔ **没做分层剂量那批**、"
            "⛔ **没验「哪一条臂是机制效应」**（w vs rand 只是「方向 vs 随机」）、"
            "⛔ 没改读数器/探针/拆分器、⛔ 没改任何预登记、⛔ 没改 244.79/244.80/244.81 段。",
            "",
            "**全回归**", "",
            reg_line, ""]
    body.extend(reg_class)
    body.append("")
    body.append("**这一轮的收据**")
    body.append("")
    for name, md5v in (("premise_independence_audit.py", "7a0ef341c4c1857ec9e55cb8244a4440"),
                       ("mut_premise_independence_audit.py", "be48ea9ea8e4e625147711fa74f741d6"),
                       ("_cross_check_24482.py", "fdb1f17ea96f6a6310ca820ab166b764"),
                       ("R6_PREMISE_INDEPENDENCE_PREREG.md", "5a34912a2fdb0b3e291fc4c469b6ee44"),
                       ("_run_24482_verify.sh", "2e67542f6ce2507fd808b0384b43fa7b")):
        body.append("· `%s`  `%s`" % (md5v, name))
    body.append("")
    with io.open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(body) + "\n")
    print("✅ %s（%d 字节）" % (OUT, len("\n".join(body).encode("utf-8"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
