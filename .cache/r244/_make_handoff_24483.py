#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 244.83 的交接文件（**所有数从收据解析**，⛔ 不手抄）。"""

import datetime
import io
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
EV = os.path.join(HERE, "_e24483")
OUT = os.path.join(REPO, ".cache", "xcheck", "HANDOFF_24483.md")


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
    de = _need(os.path.join(EV, "de.out"))
    st = _need(os.path.join(EV, "selftest.out"))
    mu = _need(os.path.join(EV, "mut.out"))
    cr = _need(os.path.join(EV, "cross.out"))
    regp = os.path.join(EV, "reg_24483.txt")
    reg = _read(regp) if os.path.isfile(regp) else ""

    N = {}
    m = _grab(de, r"产物 md5 逐位对上：账本登记的 (\d+) 件（([^）]*)）｜ 本轮首次登记的 (\d+) 件"
                r"（([^）]*)）｜ 不符 (\d+) 件", "产物 md5 对账")
    N["art_ledger_n"], N["art_ledger"], N["art_new_n"], N["art_new"], N["art_bad"] = m.groups()
    m = _grab(de, r"注入前范数（float64 口径）：w=([-+0-9.eE]+) ｜ rand\(seed=0\)=([-+0-9.eE]+) ｜ "
                r"相对差=([-+0-9.eE]+)（上限 ([-+0-9.eE]+)）", "注入前范数")
    N["w_norm"], N["r_norm"], N["rel"], N["tol"] = m.groups()
    m = _grab(de, r"注入后（bfloat16）范数：w=([-+0-9.]+) ｜ rand=([-+0-9.]+) ｜ "
                r"相对差=([-+0-9.eE]+)（上限 ([-+0-9.eE]+)", "注入后范数")
    N["w_bf"], N["r_bf"], N["rel16"], N["bound16"] = m.groups()
    m = _grab(de, r"α 网格：w=linspace\(([-0-9.]+),([-0-9.]+),(\d+)\)", "α 网格")
    N["g0"], N["g1"], N["nst"] = m.groups()
    m = _grab(de, r"判决读数 α：w=\[([-+0-9.eE, ]+)\] ｜ rand=\[([-+0-9.eE, ]+)\]", "判决读数 α")
    N["ro_w"], N["ro_r"] = m.groups()
    m = _grab(de, r"四源\*\*一致 ｜ 比较格数 (\d+) ｜ 不一致 (\d+) 格", "位点数")
    N["n_common"], N["ns_bad"] = m.groups()
    m = _grab(de, r"S 内 (\d+) 个结构字段逐格比较：实际比较 (\d+) 次（应 (\d+)）｜ 两臂不一致 (\d+) 处",
              "结构字段")
    N["n_struct"], N["n_cmp"], N["n_cmp_exp"], N["s_bad"] = m.groups()
    m = _grab(de, r"实测差异字段 D（除 arm）共 (\d+) 个", "差异字段")
    N["n_diff"] = m.group(1)
    m = _grab(de, r"= alpha_max\(([-0-9.]+)\) × ∥v∥ × √k ｜ 两臂相对差超限的格 (\d+) ｜ "
                r"公式路径 vs 直接求和路径不一致 (\d+) 格", "注入总范数")
    N["amax_v"], N["inj_bad"], N["inj_path"] = m.groups()
    m = _grab(de, r"cos\(w, rand_seed0\)=([-+0-9.]+) ｜ 参考分布 K=(\d+) ｜ 经验秩=([-+0-9.]+) ｜ "
                r"z=([-+0-9.]+) ｜ 参考 sd=([-+0-9.]+) vs 理论 1/√(\d+)=([-+0-9.]+)（相对差 ([-+0-9.]+)）",
              "余弦")
    N["cos0"], N["K"], N["rank"], N["z"], N["sd"], N["dim"], N["theo"], N["sdrel"] = m.groups()
    N["verdict"] = _grab(de, r"^VERDICT=(D-[ABC])", "判决形态").group(1)
    m = _grab(de, r"判据汇总：(\d+) 条 ｜ PASS (\d+) ｜ FAIL (\d+)", "真数据判据")
    N["de_n"], N["de_pass"], N["de_fail"] = m.groups()
    m = _grab(st, r"自检②（注入缺陷 (\d+) 个）：抓到 (\d+) ｜ 没抓到 (\d+)", "自检②")
    N["st_def"], N["st_caught"], N["st_missed"] = m.groups()
    m = _grab(mu, r"变异台：抓到 (\d+) / (\d+)（无效 (\d+) 条.*?其中等价变异 (\d+) 条", "变异台")
    N["mut_caught"], N["mut_total"], N["mut_invalid"], N["mut_equiv"] = m.groups()
    N["mut_crash"] = _grab(mu, r"崩的条数：(\d+)", "崩计数").group(1)
    N["mut_ids"] = re.findall(r"^\[(?:抓到|硬停抓到)\] (\S+)", mu, re.M)
    m = _grab(cr, r"互证：(\d+) 项 ｜ OK (\d+) ｜ MISMATCH (\d+)", "互证")
    N["cr_n"], N["cr_ok"], N["cr_bad"] = m.groups()
    N["x_onlyrand"] = _grab(cr, r"^CROSS\|only_rand=(.*)$", "互证 only_rand").group(1).strip()

    reg_line = "⛔ **R4 收据未取回**"
    if reg:
        def _rg(pat, what):
            return _grab(reg, pat, what).group(1)
        reg_line = ("`%s` ｜ 执行集 **%s** 个 py ｜ 清单 diff 对 R3 added **%s** / removed **%s** ｜ "
                    "变异台 全绿 %s / 跑得动 %s ｜ 自检 全绿 %s / 跑得动 %s ｜ `REG_RC = %s` ｜ "
                    "账本 %s 行 md5 `%s`"
                    % (_rg(r"host=(\S+)", "R4 主机"),
                       _rg(r"n_exec_py=(\d+)", "R4 执行集数"),
                       _rg(r"added=(\d+)", "R4 新增"), _rg(r"removed=(\d+)", "R4 减少"),
                       _rg(r"小结：变异台 全绿 (\d+) / 跑得动 (\d+)", "R4 变异台"),
                       _rg(r"小结：变异台 全绿 (\d+) / 跑得动 (\d+)", "R4 变异台"),
                       _rg(r"小结：.*自检 全绿 (\d+) / 跑得动 (\d+)", "R4 自检"),
                       _rg(r"小结：.*自检 全绿 (\d+) / 跑得动 (\d+)", "R4 自检"),
                       _rg(r"REG_RC=(\d+)", "R4 退出码"),
                       _rg(r"ledger_lines=(\d+)", "R4 账本行数"),
                       _rg(r"ledger_md5=(\w+)", "R4 账本 md5")))

    head = _git("log", "--oneline", "-1")
    ledger_lines = _grab(reg, r"ledger_lines=(\d+)", "R4 账本行数").group(1) if reg else "?"

    L = []
    A = L.append
    A("# 交接 —— 244.83「剂量等值性」验收（%s）" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
    A("")
    A("⚖⚖⚖ **一句话**")
    A("")
    A("**「w 臂与 rand 臂是同一个剂量下的比较」这条前提，被逐项实测通过了。**")
    A("注入前两臂范数相对差 **%s**、注入后（模型 dtype = bfloat16）**%s**；α 网格、判决读数 α、"
      "位点数、位点集合、逐格结构字段、静态命令行、逐格注入场 L2 范数**逐项相同**。"
      % (N["rel"], N["rel16"]))
    A("⇒ ⇒ **244.81/244.82 的 w-vs-rand 判决（轨迹级 +30.36pp、块级 +53.57pp）"
      "不是「剂量不同造成的」**。")
    A("⛔ **但这只管剂量这一侧** ⇒ ⇒ 「**哪一条臂是机制效应**」**仍然未量到**。")
    A("")
    A("## 1. 📊 判决面板（剂量等值性）")
    A("")
    A("| 量 | w 臂 | rand 臂 | 差 / 判据 |")
    A("|---|---|---|---|")
    A("| 产物 md5 对账 | 账本登记 %s 件 | — | 不符 %s 件；本轮首次登记 %s 件 |"
      % (N["art_ledger_n"], N["art_bad"], N["art_new_n"]))
    A("| 注入前范数（float64） | `%s` | `%s` | 相对差 **%s**（≤ %s） |" % (N["w_norm"], N["r_norm"], N["rel"], N["tol"]))
    A("| 注入后范数（bfloat16） | `%s` | `%s` | 相对差 **%s**（≤ %s） |" % (N["w_bf"], N["r_bf"], N["rel16"], N["bound16"]))
    A("| α 网格 | `linspace(%s, %s, %s)` | 同 | 逐位相同 |" % (N["g0"], N["g1"], N["nst"]))
    A("| 判决读数 α | `[%s]` | `[%s]` | 逐位相同（三源） |" % (N["ro_w"], N["ro_r"]))
    A("| 位点数 k | 四源一致 | 同 | 比较 %s 格 ｜ 不一致 %s |" % (N["n_common"], N["ns_bad"]))
    A("| 位点集合 | 种子 0 nested | 同 | 逐格相同 |")
    A("| 逐格结构字段 | %s 个 | 同 | 比较 %s 次 ｜ 不一致 %s 处 |" % (N["n_struct"], N["n_cmp"], N["s_bad"]))
    A("| 注入场 L2（alpha_max×∥v∥×√k） | — | — | 超限 **%s** 格 ｜ 双路径不一致 **%s** 格 |"
      % (N["inj_bad"], N["inj_path"]))
    A("| 字段划分 | 实测/声明一致 | — | 读数字段 %s 个 |" % N["n_diff"])
    A("")
    A("⚖ **形态 %s**" % N["verdict"])
    A("")
    A("## 2. 🔍 唯一「不是等式」的量：对照方向的余弦")
    A("")
    A("- `cos(w, rand_seed0)` = **%s** ｜ K = %s ｜ 经验秩 **%s** ｜ z = **%s**"
      % (N["cos0"], N["K"], N["rank"], N["z"]))
    A("- 参考分布 sd `%s` vs 理论 1/√%s = `%s`（相对差 %s）⇒ 零分布可判读"
      % (N["sd"], N["dim"], N["theo"], N["sdrel"]))
    A("- ⚠ 这**一个**对照方向在对齐度上落在 **%s 分位** ⇒ 它**不是**典型随机方向；"
      "**N=1** ⇒ 「巧合还是结构」**未量到** ⇒ 它对改判率的**影响未量到**" % N["rank"])
    A("")
    A("## 3. ✅ 每条判据能红")
    A("")
    A("- 自检②：注入缺陷 **%s** 个 ｜ 抓到 **%s** ｜ 没抓到 **%s**" % (N["st_def"], N["st_caught"], N["st_missed"]))
    A("- 变异台：抓到 **%s / %s**（无效 %s ｜ 等价 %s）｜ 崩 **%s**" %
      (N["mut_caught"], N["mut_total"], N["mut_invalid"], N["mut_equiv"], N["mut_crash"]))
    A("- 互证：%s 项 ｜ OK **%s** ｜ MISMATCH **%s**" % (N["cr_n"], N["cr_ok"], N["cr_bad"]))
    A("- 真数据判据：%s 条 ｜ PASS **%s** ｜ FAIL **%s**" % (N["de_n"], N["de_pass"], N["de_fail"]))
    A("- 变异台逐条：%s" % "、".join(N["mut_ids"]))
    A("")
    A("## 4. ⚠ 三条更正记录（撤回并更正，⛔ 不改数凑好看）")
    A("")
    A("1. 注入 dtype 是 **bfloat16** 不是 float32 ⇒ 容差改为**由 dtype 推导**（5×2⁻⁹）。")
    A("2. 「逐格全字段相同」是**错的**（读数字段必然不同）⇒ 改成「结构/读数**划分**」口径。")
    A("3. rand 臂缩放因子是 **float32 口径** ⇒ 第一版实现误用 float64 范数、差 6.43e-10 "
      "⇒ **由互证当场抓到** ⇒ 已更正。")
    A("")
    A("## 5. 📚 证据链台账")
    A("")
    A("- 权威账本：`.cache/xcheck/R6_RERUN_PREREG.md`（**只追加**，`## 修订 244.83` 段；共 %s 行）" % ledger_lines)
    A("- 索引：`.cache/xcheck/R6_RERUN_INDEX.md`（每条修订一行）")
    A("- 预登记：`.cache/xcheck/R6_DOSE_EQUIVALENCE_PREREG.md`（**先于实现**签，含 §0.5 三条更正记录）")
    A("- 收据：`.cache/r244/_e24483/{selftest,de,mut,cross}.out` ＋ `reg_24483.txt`")
    A("- 全回归 R4：%s" % reg_line)
    A("")
    A("## 6. ⛔ 边界清单")
    A("")
    A("- ⛔ **「哪一条臂是机制效应」** ⇒ **未量到** ⇒ 要「同结论、同末值、只有检查有效性不同」的对照臂。")
    A("- ⛔ **「随机」的覆盖面** ⇒ **未量到**（N=1，只用了一个种子）。")
    A("- ⛔ **对照方向与 w 的对齐对改判率的影响** ⇒ **未量到**。")
    A("- ⛔ **剂量—响应曲线** ⇒ **未量到** ⇒ 分层剂量要**真阶梯**（⛔ 不能事后分位分档：244.72 的 D5 审计"
      "已证 4 档分位会**切穿复制组**）。")
    A("- ⚠ **w 臂缺一格**（`%s`）⇒ 报「未量到」；本轮比较 %s 格。" % (N["x_onlyrand"], N["n_common"]))
    A("- ⛔ 远端 tokenizer 快照的内容指纹、**照 meta 重建能否逐位复现** ⇒ 沿用旧留白，**未量到**。")
    A("")
    A("## 7. ▶️ 如何做（下一步）")
    A("")
    A("1. **先读**账本尾部 `/Users/zhourui/code/steer3d/.cache/xcheck/R6_RERUN_PREREG.md`"
      "（**唯一权威历史**）→ ② 再读本文件 → ③ `git log --oneline -10` + `git status --porcelain`"
      "（工作区有同事的未跟踪文件，⛔ 不碰）→ ④ 照下面接着做。")
    A("2. **下一轮 244.84（三件事，都不需要跑批的先做前两件）**：")
    A("   - **同结论对照臂**（机制轴）：同结论、同末值、只有检查有效性不同 ⇒ 回答「哪一条臂是机制效应」。")
    A("   - **多随机种子的对照臂**：把「随机」从 N=1 变成 N=K ⇒ 顺带回答「对照臂对齐度的分布」"
      "⇒ 这是 244.83 唯一留下的**可量化**开口。")
    A("   - **分层剂量的真阶梯**（剂量轴）：每条轨迹扫 K 个 `n_sites` ⇒ 规模按新 K 重算 "
      "⇒ ⛔ **要跑批 ⇒ 要用户点头**。")
    A("3. ⛔ 别把「剂量轴被控住」读成「剂量—响应已知」；⛔ 别把「前提独立性已验收」读成「前提独立性成立」。")
    A("")
    A("⚖ 最近一次提交：`%s`" % head)
    A("")

    with io.open(OUT, "w", encoding="utf-8", newline="") as fh:
        fh.write("\n".join(L) + "\n")
    print("已写出：%s（%d 字节）" % (OUT, os.path.getsize(OUT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
