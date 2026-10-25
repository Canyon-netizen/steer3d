#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⚖ **生成 244.89 的提交信息**（⛔ 所有数都从收据抠，⛔ 不手抄）。

⚖⚖⚖ **同源纪律**：本脚本**直接复用落账脚本 `_append_24489.py` 的解析器**
   ⇒ ⇒ 提交信息里的数与**账本里那段**用的是**同一套解析** ⇒ ⇒ 二者**不可能打架**。

用法：python3 .cache/r244/_commit_msg_24489.py  ⇒ ⇒ 写 `.cache/r244/_commit_msg_24489.txt`
"""

import io
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DEV = os.path.join(REPO, ".cache", "r244")
EV = os.path.join(DEV, "_e24489b")
OUT = os.path.join(DEV, "_commit_msg_24489.txt")

sys.path.insert(0, DEV)
import _append_24489 as AP              # noqa: E402  （⛔ 只复用**解析**，不 import 被检实现）


def _read(p):
    with io.open(p, encoding="utf-8", newline="") as fh:
        return fh.read()


def _need(p):
    if not os.path.isfile(p):
        raise SystemExit("⛔ 缺收据：%s" % p)
    return _read(p)


def _final_ledger_md5():
    """⚖ **最终版账本的 md5**：从**落账后现算**的 FACTS 里抠（⛔ 不写死）。"""
    p = os.path.join(DEV, "_post_commit_readback_24489.py")
    if not os.path.isfile(p):
        raise SystemExit("⛔ 缺 %s ⇒ ⇒ 先跑 `_gen_readback_24489.py`" % p)
    txt = _read(p)
    m = re.search(r'^FULL_MD5 = "([0-9a-f]{32})"$', txt, re.M)
    if not m:
        raise SystemExit("⛔ FACTS 里没有 FULL_MD5 ⇒ ⇒ 先跑 `_gen_readback_24489.py`")
    return m.group(1)


def _reg_facts():
    """⚖ **R10 全回归收据**（⛔ 必须有 ⇒ ⇒ 提交信息**一定**带全回归证据）。"""
    p = os.path.join(EV, "reg_24489.txt")
    if not os.path.isfile(p):
        raise SystemExit("⛔ 缺 R10 全回归收据：%s ⇒ ⇒ **不许**在没跑全回归的情况下提交" % p)
    txt = _read(p)
    out = {}
    m = re.search(r"ledger_lines=(\d+)\s+ledger_md5=(\w+)", txt)
    out["ledger_lines"] = m.group(1) if m else "(缺)"
    out["ledger_md5"] = m.group(2) if m else "(缺)"
    m = re.search(r"index_lines=(\d+)\s+index_md5=(\w+)", txt)
    out["index_lines"] = m.group(1) if m else "(缺)"
    out["index_md5"] = m.group(2) if m else "(缺)"
    m = re.search(r"added=(\d+)\s+removed=(\d+)", txt)
    out["added"], out["removed"] = m.groups() if m else ("?", "?")
    m = re.search(r"n_exec_py=(\d+)", txt)
    out["n_exec"] = m.group(1) if m else "(缺)"
    m = re.search(r"REG_RC=(\d+)", txt)
    out["reg_rc"] = m.group(1) if m else "(缺)"
    m = re.search(r"BAD_n=(\d+)", txt)
    out["bad_n"] = m.group(1) if m else "(缺)"
    m = re.search(r"小结：变异台.*", txt)
    out["summary"] = m.group(0) if m else "(缺)"
    m = re.search(r"GATE_RC=(\d+)", txt)
    out["gate_rc"] = m.group(1) if m else "(缺)"
    return out


def main():
    N = AP.collect()
    K = N["K"]
    R = _reg_facts()
    led_md5 = _final_ledger_md5()

    L = []
    A = L.append
    A("244.89：保守读法换置信水平 —— 「污染解释不了观测差」在**更宽置信水平**下**不再全域成立**（判成 %s）"
      % N["verdict"])
    A("")
    A("**一句话**：244.88 判成形态 %s，但它只用了 **95%% 一档**的 CI 下端点（它**读**账本印好的 "
      "Newcombe95 区间、**自己没有算过 Newcombe**）⇒ ⇒ 「**更宽置信水平下的保守读法**」"
      "**完全没量到**（244.88 边界清单的 B-2）⇒ ⇒ 本轮①**把 Newcombe 自己实现出来**（方法 10）"
      "并在 **90 / 95 / 99** 三档各算一遍；② 把保守读法放到完整的 "
      "**(CI 水平 × 污染水平 × 基准变体) = %d 格**上，并抽出**决策区**（联合置信 ≥ 90%%）作主表 "
      "⇒ ⇒ **结论再收紧一档**。" % (N["verdict"], N["n_cells"]))
    A("")
    A("**判决面板**（全部数从账本 244.81 / 244.88 段**逐行解析**，⛔ 代码里不写死任何一个数；"
      "连**容差**都由账本自己的打印精度推导）：")
    A("· **判决形态**：**%s**" % N["verdict"])
    A("· **理由（原文）**：%s" % N["reason"])
    A("")
    A("· ⚖ **三个 Newcombe 下端点（本轮自己算的）**：CI_lo(traj) 90%% = **%s** ｜ 95%% = **%s** ｜ "
      "99%% = **%s**；CI_lo(block) 90%% = **%s** ｜ 95%% = **%s** ｜ 99%% = **%s**"
      % (K["CI_LO_TRAJ_90"], K["CI_LO_TRAJ_95"], K["CI_LO_TRAJ_99"],
         K["CI_LO_BLK_90"], K["CI_LO_BLK_95"], K["CI_LO_BLK_99"]))
    A("· ⚖ **c 的下界（Wilson；随水平变宽，main 基准）**：90%% ⇒ **%s** ｜ 95%% ⇒ **%s** ｜ 99%% ⇒ **%s**"
      % (K["CLO_90_MAIN"], K["CLO_95_MAIN"], K["CLO_99_MAIN"]))
    A("· **单源读法（污染只抬高 rand 臂；不依赖 c）跨 %d 个水平**：轨迹级 "
      % len(N["s1"])
      + " ｜ ".join("%s ⇒ **%+.4f pp**" % (lv, float(bd)) for lv, bd, _ok in N["s1"])
      + " ｜ 块级 "
      + " ｜ ".join("%s ⇒ **%+.4f pp**" % (lv, float(bd)) for lv, bd, _ok in N["s2"])
      + " ⇒ ⇒ **三个水平全部 > 0**")
    A("· **点估计读法**：轨迹级 **%s/%s** 成立 ｜ 块级 **%s/%s** 成立"
      % (N["h4_traj"][0], N["h4_traj"][1], N["h4_blk"][0], N["h4_blk"][1]))
    A("· ⚖⚖⚖ **保守读法（决策区 = 联合置信 ≥ 90%%）**：**%d 格里只有 %d 格成立** ⇒ ⇒ "
      "**结论必须收紧**：这条读法**只在部分水平/基准组合成立**"
      % (N["n_dec"], N["n_dec_hold"]))
    A("· **全表 %d 格**（完整作用域）：**%d 格成立** ｜ 破口 %d 个"
      % (N["n_cells"], N["n_all_hold"], N["n_cells"] - N["n_all_hold"]))
    A("")
    A("**决策区逐格**（联合置信 ≥ 90%% 的 %d 种分配 × %d 个基准 = %d 格）："
      % (N["n_alloc"], N["n_var"], N["n_dec"]))
    for c in N["dec_cells"]:
        A("· CI%.0f / 污染%.0f / %s ｜ 界 **%+.4f pp** ｜ 联合 %d%% ｜ %s"
          % (c["ci"] * 100, c["c"] * 100, c["var"], c["bound"], c["conf"],
             "✅ 成立" if c["ok"] else "⛔ **不成立**"))
    A("")
    A("**九条判据（真数据）**：")
    for st_, cid, name, detail in N["crits"]:
        A("- [%s] **%s** %s" % (st_, cid, name.strip()))
    A("")
    A("**每条判据能红**：自检 **%s** 道 / FAIL **%s** ｜ 变异台抓到 **%s / %s**（无效 %s 条、崩 %s 条）"
      "｜ 互证 OK **%s** / MISMATCH **%s**（独立重算的形态 **%s**）｜ 预登记↔实现对账 OK **%s** / 红 **%s** "
      "｜ 验证链五个 rc **%s / %s / %s / %s / %s**"
      % (N["st_n"], N["st_fail"], N["mut_caught"], N["mut_total"], N["mut_invalid"], N["mut_crash"],
         N["cr_ok"], N["cr_bad"], N["cr_form"], N["sp_ok"], N["sp_bad"], *N["rcs"]))
    A("")
    A("**全回归 R10**（zju-12，零 GPU）：清单 diff added/removed = **%s/%s** ｜ 执行集 %s 个 ｜ "
      "REG_RC=%s ｜ BAD_n=%s ｜ 硬门 GATE_RC=%s ｜ %s"
      % (R["added"], R["removed"], R["n_exec"], R["reg_rc"], R["bad_n"], R["gate_rc"], R["summary"]))
    A("")
    A("**本轮抓到的真缺陷（⛔ 一个实测数都没动）**：")
    A("① ⚠⚖⚖ **实现层（自检层）**：G0-2 的期望级联**从模块常量派生** ⇒ ⇒ 变异两边一起变 ⇒ ⇒ "
      "**恒绿** ⇒ ⇒ 变异台 **MU1 存活**暴露 ⇒ ⇒ 改成「硬失败集合**手写**」⇒ ⇒ 判据**变严**"
      "（⚖ **244.88 第 ② 条缺陷的同型复发**）｜")
    A("② ⚠⚖ **实现层（护栏层）**：量纲护栏的**兜底分支**没被覆盖 ⇒ ⇒ 变异 **MU9 存活**暴露 "
      "⇒ ⇒ 补用例 ⇒ ⇒ 判据**变严**（⚖ **244.88 第 ③ 条缺陷的同型复发**）｜")
    A("③ ⚠ **实现层（护栏层）**：护栏的**调用点**没被测 ⇒ ⇒ 补「从**真正的加法路径**喂一次未登记配对」"
      "⇒ ⇒ 变异 MU14 抓住｜")
    A("④ ⚠ **实现层**：允许加法表**只登记了一个方向** ⇒ ⇒ 补齐两种顺序 ⇒ ⇒ 判据**变严**｜")
    A("⑤ ⚠⚖ **工具层（合成夹具）**：夹具里的 `\"95% 单源\"` **没转义** ⇒ ⇒ 整份自检跑不起来 "
      "⇒ ⇒ ⚠ **本地 `compile()` 抓不到** ⇒ ⇒ 抓到它的办法是「**真的跑一遍**」⇒ ⇒ 另加静态检查｜")
    A("⑥ ⚠ **工具层（互证）**：按单元格切抠分布失败 ⇒ ⇒ 改正则｜")
    A("⑦ ⚠⚖⚖ **工具层（互证）**：互证的 **Newcombe 混了单位** ⇒ ⇒ 量级 1e4 ⇒ ⇒ ⛔ **不是**被检实现发现的 "
      "⇒ ⇒ 是**互证自己的数值对账**抓到的 ⇒ ⇒ 这正是「第二条独立实现」的价值｜")
    A("⑧ ⚠ **工具层（互证）**：`Decimal(Fraction)` 抛 TypeError ⇒ ⇒ 改成「分子/分母」｜")
    A("⑨ ⚠⚖ **工具层（对账）**：对账脚本有 **8 处抽取失配** ⇒ ⇒ 11 条里红 11 条（⚠ **全是「对账脚本自己」的问题**）"
      "⇒ ⇒ 逐条改 ⇒ ⇒ 改到 **%s OK / %s 红** ⇒ ⇒ 教训：「全红」的第一反应必须是「**谁的抽取坏了**」"
      % (N["sp_ok"], N["sp_bad"]))
    A("⑩ ⚖⚖ **驱动层（结构性改进）**：banner 的变异条数改成**从台架源码现算** ⇒ ⇒ "
      "**结构上**堵死「过期计数」这一类缺陷｜")
    A("⑪ ⚖ **等价变异（记「无效」，⛔ 不是「存活」）**：MU21 的初版**逐条结果完全相同** ⇒ ⇒ 记「无效」"
      "⇒ ⇒ 改成真正会触发浮点陷阱的那条 ⇒ ⇒ 抓到了 ✓｜")
    A("⑫ ⚠⚖⚖ **预登记层（起草层算术）**：预登记 §0.5' 更正 ④ 写「(95,95) 那 **9** 格」「主表会悄悄**少掉 9 格**」"
      "⇒ ⇒ **与预登记自己的「决策区 = %d 格」矛盾**（每种分配只覆盖 **%d** 个基准变体）⇒ ⇒ "
      "⇒ ⇒ **只改描述、⛔ 一个实测数都没动** ⇒ ⇒ 已按预登记自己的机制**追加**「更正 ⑧」"
      "⇒ ⇒ ⚠ **如实标注**：更正 ⑧ 是**落账时**（**已看到结果之后**）才发现的，但它是**纯算术**、"
      "与实测结果无关 ⇒ ⇒ **不改动任何判据/门槛/护栏/形态定义** ⇒ ⇒ 不构成「结果驱动的改判据」"
      % (N["n_dec"], N["n_var"]))
    A("")
    A("⚖⚖⚖ **「只改描述」不是声明，是比对结果**：本轮**跑了两遍验证链**"
      "（更正 ⑧ **之前** ＋ **之后**）⇒ ⇒ 两遍的 `selftest / de / mut / cross / spec` "
      "**逐字节 IDENTICAL** ⇒ ⇒ 落账脚本里有一条**硬闸**：这五个文件只要有一个不同 ⇒ ⇒ **不许**落账。")
    A("")
    A("**预登记** `.cache/xcheck/R6_CONFIDENCE_LEVEL_PREREG.md`（**先于实现**签；"
      "§0.5' 含 **%d 条更正**——① 联合置信的算术、② H9② 的残差容差、③ H9③ 的 R6 切片、"
      "④ H2 加「手写」决策区成员表、⑤ G0-3 加「调用点」用例、⑥ G0-7 改成间隙负控＋函数级正负控、"
      "⑦ 补读法 id 表、⑧ 更正 ④ 的一处算术表述）"
      "（⚠ 本轮的量**全部已在账本登记** ⇒ ⇒ **手算即可**得出各格符号 ⇒ ⇒ "
      "**不主张**「结果未知」；准确的说法是「预登记的**口径与判据**全部先于结果」）" % N["n_corr"])
    A("")
    A("**账本** `.cache/xcheck/R6_RERUN_PREREG.md`（**只追加**：旧前缀逐字节不变、围栏数不变；"
      "现 **%s 行 / md5 `%s`**）｜ **索引** `.cache/xcheck/R6_RERUN_INDEX.md`（**%s 行 / md5 `%s`**）"
      "｜ **收据** `.cache/r244/_e24489b/`"
      % (R["ledger_lines"], led_md5, R["index_lines"], R["index_md5"]))
    A("")
    A("⚖ **一条查实的事实**：`zju-53` 与 `zju-12` 是**两台共享同一份 NFS 家目录**的机器"
      "⇒ ⇒ 「**两台远端逐位一致**」是**必然**的，⛔ **不是**独立证据 "
      "⇒ ⇒ 真正的独立证据是「**收据里的 md5 == 本地现算的 md5**」⇒ ⇒ 以后**不许**拿"
      "「两台一致」当成交叉验证。")

    msg = "\n".join(L) + "\n"
    with io.open(OUT, "w", encoding="utf-8", newline="") as fh:
        fh.write(msg)
    print("✅ 已写：%s（%d 字节）" % (OUT, len(msg.encode("utf-8"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
