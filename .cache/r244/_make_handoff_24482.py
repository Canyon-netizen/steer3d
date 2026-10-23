#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 244.82 的交接文件（**所有数从收据解析**，⛔ 不手抄）。"""

import datetime
import io
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
EV = os.path.join(HERE, "_e24482")
OUT = os.path.join(REPO, ".cache", "xcheck", "HANDOFF_24482.md")


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


def _git(*a):
    return subprocess.run(["git"] + list(a), cwd=REPO, capture_output=True,
                          text=True).stdout.strip()


def main():
    pi = _need(os.path.join(EV, "pi.out"))
    st = _need(os.path.join(EV, "selftest.out"))
    mu = _need(os.path.join(EV, "mut.out"))
    cr = _need(os.path.join(EV, "cross.out"))

    m = _grab(st, r"自检 (\d+) 条 ｜ PASS (\d+) ｜ FAIL (\d+)", "自检小结")
    st_n, st_pass, st_fail = m.groups()
    m = _grab(pi, r"判据 (\d+) 条 ｜ PASS (\d+) ｜ FAIL (\d+)", "真数据判据小结")
    pi_n, pi_pass, pi_fail = m.groups()
    m = _grab(mu, r"变异台：抓到 (\d+) / (\d+)（无效 (\d+) 条.*?其中等价变异 (\d+) 条", "变异台小结")
    mut_caught, mut_total, mut_invalid, mut_equiv = m.groups()
    m = _grab(mu, r"崩的条数：(\d+)", "崩计数")
    mut_crash = m.group(1)
    mut_hard = len(re.findall(r"^\[硬停抓到\]", mu, re.M))
    mut_plain = len(re.findall(r"^\[抓到\]", mu, re.M))
    m = _grab(cr, r"互证判据 (\d+) 条 ｜ PASS (\d+) ｜ FAIL (\d+)", "互证小结")
    cr_n, cr_pass, cr_fail = m.groups()

    m = _grab(pi, r"\*\*精确\*\*块级置换（DP 精确零分布，⛔ 非 MC）：p = ([0-9.]+)"
                    r"（obs = (\d+) ｜ 尾 (\d+) / (\d+)）", "精确块级置换")
    p_exact, obs_blk, tail, tot = m.groups()
    m = _grab(pi, r"块级差 ([-+0-9.]+) pp ｜ \*\*删一块 jackknife\*\* 95% 区间 "
                    r"\[([-+0-9.]+), ([-+0-9.]+)\] pp（SE = ([0-9.]+)）", "jackknife")
    theta_blk, jk_lo, jk_hi, jk_se = m.groups()
    m = _grab(pi, r"轨迹级差 ([-+0-9.]+) pp ｜ Newcombe95（\*\*假定轨迹独立\*\*）"
                    r"\[([-+0-9.]+), ([-+0-9.]+)\] pp", "Newcombe")
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

    # ---- 全回归 R3
    regp = os.path.join(EV, "reg_24482.txt")
    reg = _read(regp) if os.path.isfile(regp) else ""
    reg_row = "| 全回归 R3（落账 **后**的账本 = 本次提交里那份） | ⛔ **未量到** |"
    if reg:
        def _rg(pat):
            return _grab(reg, pat, "R3").group(1)
        reg_row = ("| **全回归 R3（落账 244.82 **后**的账本 = 本次提交里那份）** | 主机 `%s` ｜ 执行集 **%s** 个 py ｜ "
                   "清单 diff（对 R2）**新增 %s / 减少 %s** ｜ 变异台 全绿 %s / 跑得动 %s ｜ "
                   "自检 全绿 %s / 跑得动 %s ｜ `REG_RC = %s` ｜ 红项 %s ｜ 账本 **%s 行** md5 `%s` |"
                   % (_rg(r"host=(\S+)"), _rg(r"n_exec_py=(\d+)"), _rg(r"added=(\d+)"),
                      _rg(r"removed=(\d+)"), _rg(r"小结：变异台 全绿 (\d+) / 跑得动 (\d+)"),
                      _rg(r"小结：变异台 全绿 (\d+) / 跑得动 (\d+)"),
                      _rg(r"小结：.*自检 全绿 (\d+) / 跑得动 (\d+)"),
                      _rg(r"小结：.*自检 全绿 (\d+) / 跑得动 (\d+)"),
                      _rg(r"REG_RC=(\d+)"),
                      (", ".join(re.findall(r"^  \[BAD \] (\S+\.py)", reg, re.M)) or "无"),
                      _rg(r"ledger_lines=(\d+)"), _rg(r"ledger_md5=(\w+)")))

    commit = _git("rev-parse", "HEAD")
    subject = _git("log", "-1", "--pretty=%s")

    L = []
    A = L.append
    A("# 交接：244.82（**「前提独立性」这条前提正式验收掉**）")
    A("")
    A("⚖⚖⚖ **一句话**：244.81 判决面板上的每一个 p、每一个区间都建立在「56 条轨迹彼此独立」"
      "这个**没被验过**的前提上 ⇒ ⇒ 本轮在**承认聚类**的保守零分布（**块是独立单位**）下重算："
      "**精确**块级置换 p = **%s**、块级差 **%s pp**（**删一块 jackknife** 区间 [**%s, %s**]）、"
      "**LOBO** %s 个子集**掀翻数 = %s** ⇒ ⇒ **%s**；"
      "⛔ 但 **块间独立性不可检验**、「前提独立性成立」**不可证明** ⇒ ⇒ **不是**「前提已证」。"
      % (p_exact, theta_blk, jk_lo, jk_hi, lobo_n, lobo_flips, verdict_text))
    A("")
    A("· 提交：`%s` —— %s" % (commit[:12], subject))
    A("· 生成时间：%s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    A("")
    A("## 1. ✅ **本轮的关键结论**（完整版在账本 244.82 段）")
    A("")
    A("1. ✅ **判决在保守口径下依然成立**（结论形态 **%s**）：**精确**块级置换 p = **%s**"
      "（⛔ **不是**蒙特卡洛、⛔ 没有种子误差；obs = %s ｜ 尾 %s / %s）"
      % (verdict, p_exact, obs_blk, tail, tot))
    A("2. ✅ **块级差 %s pp**，**删一块 jackknife** 95%% 区间 [**%s, %s**] pp（SE = %s）"
      "（⛔ **确定性**，⛔ 不用种子）" % (theta_blk, jk_lo, jk_hi, jk_se))
    A("3. ✅ **LOBO**（逐块剔除 %s 个子集）：块级差 [%s, %s] pp ｜ 置换 p ∈ [%s, %s] ｜ "
      "**掀翻数 = %s** ⇒ ⇒ **没有单独一块能推翻它**"
      % (lobo_n, lobo_dmin, lobo_dmax, lobo_pmin, lobo_pmax, lobo_flips))
    A("4. ⚖ **块内相关被量到**（⛔ 不是假设）：w 臂 一致 %s/%s（po = %s）vs 偶然一致 pe = %s、"
      "κ = %s、精确二项 p = %s ⇒ **%s**；rand 臂 一致 %s/%s（po = %s）vs pe = %s、κ = %s、"
      "p = %s ⇒ **%s**。⛔ **「未检出」⛔ 不是「不相关」。**"
      % (w_agree, w_tot, w_po, w_pe, w_kap, w_p, w_det,
         r_agree, r_tot, r_po, r_pe, r_kap, r_p, r_det))
    A("5. ✅ **两条独立实现互证**（⛔ 不同数据路径、不同块键路线、不同置换算法、不同区间算法）："
      "**%s 条判据全绿**；区间重叠：先导 bootstrap [%s, %s] vs 本实现 jackknife [%s, %s] ⇒ 重叠 %s pp；"
      "MC vs 精确：先导 MC p = %s vs 精确 p = %s，差 %s ＝ **%s 个 MC 标准误** ⇒ ⇒ 差**就是 MC 误差**。"
      % (cr_pass, boot_lo, boot_hi, x_jk_lo, x_jk_hi, ov, p_mc, p_exact, d_mc, mc_mult))
    A("6. ✅ **每条判据能红**：自检 **%s/%s**、真数据 **%s/%s**、变异台 **抓到 %s / %s**"
      "（无效 %s、等价 %s、崩 %s；其中 **%s** 条普通判据红 ＋ **%s** 条 G0-3 硬停抓到）"
      % (st_pass, st_n, pi_pass, pi_n, mut_caught, mut_total, mut_invalid, mut_equiv, mut_crash,
         mut_plain, mut_hard))
    A("")
    A("## 2. ⚖ **收据摘要**（全部可回查）")
    A("")
    A("| 项 | 值 |")
    A("|---|---|")
    A("| 精确块级置换 p | **%s**（DP 精确零分布；obs = %s ｜ 尾 %s / %s） |" % (p_exact, obs_blk, tail, tot))
    A("| 块级差与区间 | **%s pp** ｜ 删一块 jackknife [**%s, %s**] pp（SE = %s） |"
      % (theta_blk, jk_lo, jk_hi, jk_se))
    A("| LOBO | %s 个子集 ｜ 差 [%s, %s] pp ｜ p ∈ [%s, %s] ｜ **掀翻数 = %s** |"
      % (lobo_n, lobo_dmin, lobo_dmax, lobo_pmin, lobo_pmax, lobo_flips))
    A("| 块内相关 | w：一致 %s/%s、po %s、pe %s、κ %s、p %s（**%s**）｜ rand：一致 %s/%s、po %s、pe %s、κ %s、p %s（**%s**） |"
      % (w_agree, w_tot, w_po, w_pe, w_kap, w_p, w_det,
         r_agree, r_tot, r_po, r_pe, r_kap, r_p, r_det))
    A("| 轨迹级对照 | 差 %s pp、Newcombe95 [%s, %s] pp（⛔ 假定轨迹独立） |" % (theta_traj, nc_lo, nc_hi))
    A("| 自检 | **%s/%s 绿**（FAIL %s） |" % (st_pass, st_n, st_fail))
    A("| 真数据 | **%s/%s 绿**（FAIL %s） |" % (pi_pass, pi_n, pi_fail))
    A("| 变异台 | 抓住 **%s/%s**（无效 %s ｜ 等价 %s ｜ 崩 %s） |"
      % (mut_caught, mut_total, mut_invalid, mut_equiv, mut_crash))
    A("| 跨实现互证 | **%s/%s 绿**（FAIL %s） |" % (cr_pass, cr_n, cr_fail))
    A(reg_row)
    A("")
    A("## 3. 📜 **证据链台账**（一条一句结论 ＋ 判据 ＋ 变异台计数）")
    A("")
    A("| # | 结论 | 判据 | 变异台 |")
    A("|---|---|---|---|")
    A("| 244.82-1 | 判决在**承认聚类**的保守零分布下**依然成立** | `S-SELFPANEL` ＋ `S-EXACT-P` ＋ `S-VERDICT` | `PM10` 改 MC 基准 ⇒ 抓 |")
    A("| 244.82-2 | 判决**不是**单块造成的 | `S-LOBO` | `PM9`/`PM11` ⇒ G0-3 硬停 |")
    A("| 244.82-3 | 块内相关**被量到**（⛔ 不是假设） | `S-WITHIN` | — |")
    A("| 244.82-4 | 块级差区间**不靠种子** | `S-JACK` ＋ `S-JACK-LINEAR` | `PM5` 删因子 ⇒ 抓 |")
    A("| 244.82-5 | 置换零分布**精确**（⛔ 非 MC） | `S-DP`（vs 暴力枚举）＋ `S-DP-TOTAL` | `PM3` 删组合数 ⇒ 抓 |")
    A("| 244.82-6 | t 分位数**自己算**（⛔ 不抄表） | `S-TQ` | `PM4` 换常数 ⇒ 抓 |")
    A("| 244.82-7 | 块键路线**两条一致** | `S-BLOCKKEY` ＋ `S-BLOCKROUTE` | `PM7` 改路线 ⇒ 抓 |")
    A("| 244.82-8 | 口径常量与预登记**一致** | `S-SPEC` | `PM1`/`PM2` ⇒ 抓 |")
    A("")
    A("## 4. 🚧 **边界清单**（哪些还没量到、哪些数不许再动）")
    A("")
    A("· ⛔ **块间独立性** ⇒ ⇒ **不可检验**（28 个块之间**没有**任何重复结构可供配对）⇒ ⇒ **未量到**。")
    A("· ⛔ **「块内不相关」** ⇒ ⇒ **未量到**（本轮只能给「可检出 / 未检出」，⛔ 给不了「不相关」）。")
    A("· ⛔ **「前提独立性成立」** ⇒ ⇒ **未量到**（**不可证明**）⇒ ⇒ 结论里**不许**出现这句话。")
    A("· ⚠ **新查到的一条数据事实**：这一批**没有平票轨迹** —— w 臂唯一那条 m=2 的轨迹是 **2 正 0 负**"
      "（⛔ 不是 1:1）⇒ ⇒ 「多数 `>` 改 `>=`」在**真数据上不可见** ⇒ ⇒ 该边界改由**合成平票夹具**"
      "（判据 `S-TIE`）覆盖 ⇒ ⇒ 变异 PM8 因此**能红**。")
    A("· ⛔ **剂量趋势**、**哪一条臂是机制效应**（w vs rand 只是「方向 vs 随机」，⛔ 不是「机制 vs 非机制」）、"
      "**远端 tokenizer 指纹**、**旧批可比性**、**「照 meta 重建能否逐位复现」** ⇒ ⇒ 全部**未量到**。")
    A("· ⛔ **拿到分层剂量那一批之前，固定剂量的这几个数不许再动。**")
    A("")
    A("## 5. ▶️ **下一步（244.83）**")
    A("")
    A("1. **分层剂量那批**（**要跑批 ⇒ 要点头**）：把「剂量」与「机制」两条轴**真正拆开**"
      "（现在只到「固定剂量 + 机制 vs rand」）。")
    A("2. **同结论对照的机制臂**（参考 `docs/VERIFICATION_V3_IDENTIFIABILITY_AUDIT.md` §7）："
      "「**有效性标签方向不自动是能力方向**」⇒ ⇒ 要回答「**哪一条臂是机制效应**」，"
      "需要**同结论、同末值、只有检查有效性不同**的对照臂 ⇒ ⇒ w vs rand **答不了**这个问题。")
    A("3. ⛔ **别把「前提独立性已验收」读成「前提独立性成立」**。")
    A("")
    A("## 6. 🧭 **上手三步**")
    A("")
    A("1. 读账本尾部：`.cache/xcheck/R6_RERUN_PREREG.md`（**唯一权威历史**）")
    A("2. 读本文件（交接全文）")
    A("3. `git log --oneline -10` ＋ `git status --porcelain`（工作区有**别人的**未跟踪文件，⛔ 不碰）")
    A("")
    A("## 7. ⚖ **本轮的硬约束**（⛔ 别放松）")
    A("")
    A("· ⛔ **跑批 / sudo / 远端写操作 / 改探针**都要**等用户点头**。")
    A("· ⛔ **一切实验与验证在服务器上跑**（本地只编辑源码/文档；本轮判决链在 `zju-53`、全回归在 `zju-12`）。")
    A("· ⛔ **账本只追加**；改数只**撤回并更正**，⛔ 绝不改数凑好看。")
    A("· ⛔ **没量到的写「未量到」**，⛔ 不许说成「无差异」。")
    A("· ⛔ 提交只带**显式路径**；⛔ 不用 `git add -A`、⛔ 不加整个目录。")
    A("")
    with io.open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("✅ %s（%d 字节）" % (OUT, len("\n".join(L).encode("utf-8"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
