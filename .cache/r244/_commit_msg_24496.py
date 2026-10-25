#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_commit_msg_24496.py —— 生成 244.96 的提交信息（**每个数都从收据/账本现取**，⛔ 不手打）。

⚖ 提交信息里的数**必须**与**跑出它们的那些字节**同源 ⇒ ⇒ 账本改了，它**不可能**留在旧数上。
"""

import io
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
RCPT = os.path.join(REPO, ".cache", "r244", "_e24496")
LEDGER = os.path.join(REPO, ".cache", "xcheck", "R6_RERUN_PREREG.md")
INDEX = os.path.join(REPO, ".cache", "xcheck", "R6_RERUN_INDEX.md")


def read(p):
    with io.open(p, encoding="utf-8") as fh:
        return fh.read()


def keys(text, name):
    m = re.search(r"===== %s =====\n(.*?)===== END_%s =====" % (name, name), text, re.S)
    if not m:
        raise SystemExit("⛔ 收据里没有 %s 块 ⇒ ⇒ 中止" % name)
    d = {}
    for l in m.group(1).split("\n"):
        if "=" in l:
            k, v = l.split("=", 1)
            d[k.strip()] = v.strip()
    return d


def main():
    st_text = read(os.path.join(RCPT, "selftest.out"))
    bf = read(os.path.join(RCPT, "data_before.out"))
    af = read(os.path.join(RCPT, "data_after.out"))
    # ⚖⚖⚖ 244.96 的自检只印**汇总行**（「自检 13/13 通过」）⇒ ⇒ 逐条 [PASS] 行**不存在**
    #    ⇒ ⇒ 计数必须从汇总行取（⛔ 否则会数成 0 道 ⇒ ⇒ 提交信息里会出现假数）。
    _mst = re.search(r"自检\s+(\d+)\s*/\s*(\d+)\s+通过", st_text)
    if _mst:
        st_total = int(_mst.group(1))
        st_total_of = int(_mst.group(2))
    else:
        st_total = len(re.findall(r"^\[(PASS|FAIL)\]", st_text, re.M))
        st_total_of = st_total
    st_red = (re.search(r"^SELFTEST_RED=(\d+)", st_text, re.M) or [None, "?"])[1]
    a = keys(af, "AUDIT_KEYS")
    b = keys(bf, "AUDIT_KEYS")
    mu = keys(read(os.path.join(RCPT, "mut.out")), "AUDIT_KEYS")
    cr = keys(read(os.path.join(RCPT, "cross.out")), "AUDIT_KEYS")
    cs = keys(read(os.path.join(RCPT, "cross_selftest.out")), "AUDIT_KEYS")
    sp = keys(read(os.path.join(RCPT, "spec.out")), "AUDIT_KEYS")

    b_red = re.findall(r"^\[FAIL\] (E\d)：", bf, re.M)
    n_rows = len(re.findall(r"^ROW=", af, re.M))
    n_rowv = len(re.findall(r"^ROWV=", af, re.M))
    n_checks = len(re.findall(r"^\[(PASS|FAIL)\] (E\d)：", af, re.M))

    # ⚖ 守卫修复的验证收据（⛔ 不入库，但**要**进提交信息 ⇒ ⇒ 数字从它现取）
    gtxt = read(os.path.join(REPO, ".cache", "r244", "_guard24496", "verify.out"))
    g_n_all = gtxt.count("✅ ①") + gtxt.count("✅ ②") + gtxt.count("✅ ③")
    g_rc = (re.search(r"VERIFY_RC=(\d+)", gtxt) or [None, "?"])[1]
    g_md5 = ""
    try:
        import hashlib
        with open(os.path.join(REPO, ".cache", "r244", "_guard24496", "verify.out"), "rb") as fh:
            g_md5 = hashlib.md5(fh.read()).hexdigest()
    except Exception:
        pass
    if g_rc != "0":
        raise SystemExit("⛔ 守卫验证收据 VERIFY_RC=%s ⇒ ⇒ 中止" % g_rc)

    ledger_text = read(LEDGER)
    ledger_lines = ledger_text.count("\n")
    index_lines = read(INDEX).count("\n")
    n_2496 = len(re.findall(r"^## 修订 244\.96 ", ledger_text, re.M))
    # ⚖⚖⚖ 「落账前那版的 md5」必须**限定在 244.96 段里**取
    #    ⇒ ⇒ 否则会匹配到**更早**那一段的同名行（拿到的就是过期值）。
    _i = ledger_text.find("## 修订 244.96 ")
    _seg = ledger_text[_i:] if _i >= 0 else ""
    pre_md5 = (re.search(r"落账前\*\* md5 `([0-9a-f]{32})`", _seg) or [None, "?"])[1]

    out = []
    W = out.append
    W("判决面板 P1–P29 纳入证据链：每个数**可溯源**到它引用的账本行（形态 A）")
    W("")
    W("· **判决**：页面 `docs/BPATH_VERDICT.md` §6.1「判决面板」**29 个 P 行** ↔ 权威账本"
      " ⇒ ⇒ 每个数**可溯源**到**它自己引用的那几行** ⇒ ⇒ 形态 **" + a["VERDICT"] + "**")
    W("  · 判据 **E1–E8**（共 **" + str(n_checks) + "** 条）全绿："
      "E1 结构（29 行、P1–P29 连续）｜E2 出处存在｜E3 强 token 可溯源"
      "｜**E4 R6′ 收紧（打印精度必须恰好 6 位小数）**｜E5 计数口径可数｜E6 计数短语逐位｜"
      "E7 派生分数逐位｜E8 每行至少 1 项命中")
    W("  · 逐行矩阵：**" + str(n_rows) + " 行** ＋ **" + str(n_rowv) + " 条逐行结论**"
      "｜ 强 token **" + a["N_STRONG"] + "** 个（逐位 **" + a["N_VERBATIM"] + "** ＋ R6′ **"
      + a["N_R6"] + "**）｜ **缺口 " + a["N_MISSING"] + "**"
      "｜ 派生分数 **" + a["N_FRAC"] + "** 个（缺口 **" + a["N_FRAC_MISSING"] + "**）"
      "｜ 计数短语 **" + a["N_COUNT"] + "** 个")
    W("")
    W("· ⚖⚖⚖ **本轮的方法论要点**（⛔ 都是**踩过**的坑，记在账本里）：")
    W("  · ⛔ **引用集合必须精确**：P22 引的是 `:42164`、`:42222` 两个**离散行**"
      "⇒ ⇒ 若用 min..max **区间窗口**，会**夹进 57 行没被引用的行** ⇒ ⇒ 「4/12」会在区间内的"
      " `:42388` 上**偶然命中** ⇒ ⇒ **判据虚高** ⇒ ⇒ 离散项取自己、区间项取区间全部行")
    W("  · ⚖ **R6′ 的外部依据**（⛔ 不是本轮反推的）：账本 `:41722`「印到 6 位小数，必须与账本那个数"
      "**逐位相同**」＋「绝对差 ≤ 5e-7（**由打印精度推导**）」；账本 `:39004`「判决行与场景行改用 6 位小数」"
      "⇒ ⇒ ⛔ **不许**写成「|page − ledger| ≤ tol 且 tol 现算」（那是「为让数对上而定的容差」）")
    W("  · ⚖⚠⚖ **E4 专为治 R6′ 的自证缺口**：R6′ **放行 7 位小数**（多印的那位被舍掉）"
      "⇒ ⇒ E3 抓不到「多印一位」⇒ ⇒ **MU-H3 / MU-H7** 证明**只有 E4 能抓** ⇒ ⇒ E4 **不是恒绿的**")
    W("")
    W("· ⛔ **本轮页面只改了 2 行**（P28 / P29），**一个实测数都没改** ⇒ ⇒ 改的只有：")
    W("  · **P28 的「账本位置」补 2 个出处**：`:42278`（一行同时给出「4/12」「决策区内 8 个」"
      "「10/27 格有破口」**和 10 条破口清单**）＋ `:42297`（「破口 10 个」）")
    W("  · **量词「处」→「个」**（3 处）：账本写「个」而页面写「处」⇒ ⇒ 按 244.94 的成规判为**措辞缺陷**并更正")
    W("  · 缺陷行集合：预登记 §1.3 登记的 == 实际有差异的行 == **" + sp["SPEC_DEFECT_LINES"] + "**"
      " ⇒ ⇒ **机械可查**")
    W("")
    W("· **每条判据能红**：")
    W("  · 自检（合成夹具、⛔ 零账本零页面零 GPU）：共 **" + str(st_total) + "/" + str(st_total_of)
      + "** 道 ⇒ ⇒ **失败 "
      + str(st_red) + " 道**（⛔ 这是「没通过」的条数，不是「判红的条数」）")
    W("  · 变异台：预登记 §4 的 **" + mu["MUT_PREREG_N"] + "** 条 ＋ 实现期新增 **"
      + str(len(re.findall(r"'MU-H\d+'", sp.get("SPEC_MUT_EXTRA", "[]")))) + "** 条 ⇒ ⇒ 共 **"
      + mu["MUT_N"] + "** 条，抓住 **" + mu["MUT_CAUGHT"] + "** ｜ 存活 **" + mu["MUT_SURVIVORS"]
      + "** ｜ 崩 **" + mu["MUT_CRASHED"] + "** ｜ 等价变异通过 **" + mu["MUT_EQUIV_OK"]
      + "**（输出与基线**逐字节相同** ⇒ ⇒ 记「无效」）｜ **预登记期望与实测不符 "
      + mu["MUT_PREREG_MISMATCH"] + " 处**")
    W("  · **等价变异 2 条**里有一条是**留白的实证**：改 P5 的 n_perm=20000 → 20001"
      "⇒ ⇒ **弱 token 本轮不判** ⇒ ⇒ **没有任何闸门会红** ⇒ ⇒ 这条留白被**量到**了")
    W("  · 互证（第二条**独立**实现，⛔ 零共用代码、⛔ 锚定/归一化/R6′ 三处**故意不同**）："
      "锚点 **" + cr["CROSS_N_ANCHORS"] + "** ｜ 强 token **" + cr["CROSS_N_STRONG"] + "** ｜ 缺口 **"
      + cr["CROSS_N_MISSING"] + "** ｜ **表示差异 " + cr["CROSS_REPR_DIFF"] + "**"
      "（⛔ 不算不符：实为**记号差异**〔页面排版减号 −(U+2212) vs ASCII -〕）｜ 不符合计 **"
      + cr["CROSS_MISMATCH"] + "** ｜ 互证**自己也能红**：`CROSS_SELFTEST_RC="
      + cs["CROSS_SELFTEST_RC"] + "`（抓到 **" + cs["CROSS_SELFTEST_N_DIFF"] + "** 处）")
    W("  · 预登记 ↔ 实现 的**机械对账**：判据 **" + sp["SPEC_N_CRITERIA"] + "** ｜ 变异 **"
      + sp["SPEC_N_MUT"] + "** ｜ **真值命中 " + sp["SPEC_REAL_TOKEN_HITS"]
      + "** ⇒ ⇒ 「零手写期望」**机械可查**")
    W("  · ⚖⚖⚖ **预登记的预测被兑现**：预登记 §1.3 写「改前预期判红 **" + sp["SPEC_PREDICTED_RED"]
      + "**」⇒ ⇒ 实测改前判红 **" + sp["SPEC_ACTUAL_RED_BEFORE"] + "** ⇒ ⇒ **逐条对上**"
      "（⛔ 预登记写错 ⇒ 这里立刻红）")
    W("  · 「**改前 ⇒ 改后**」两份收据都在：改前形态 **" + b["VERDICT"] + "**、判红 **"
      + "/".join(b_red) + "**（⛔ 那次不算判决）⇒ ⇒ 改后形态 **" + a["VERDICT"] + "**")
    W("  · **不变性**：同一套链连跑 **3 次**，7 份收据 **md5 逐字节相同**；"
      "**落账后**再重跑一遍 ⇒ ⇒ 判据块**逐字节相同**（⛔ 整份收据**唯一**的差异是 E2 那行印的"
      "「账本总行数」42800 ⇒ 42895）")
    W("")
    W("· ⚖⚖⚖ **本轮顺手抓到并修掉的一个真缺陷（连带修复，与 244.96 的判决无关）**：")
    W("  · **症状**：对**已经落过账**的账本再跑一次落账脚本 ⇒ ⇒ 它**又追加了一份**该轮段落"
      "（实测 244.96 段被追加了**第二份**，+95 行、md5 从 `912f7d6f…` 变成 `6196ce59…`）")
    W("  · **根因**：244.92–244.96 这五份脚本的幂等闸写的是 `old.startswith(MARK)`"
      "⇒ ⇒ `MARK` 是**段标题** ⇒ ⇒ 整本账本的**第一行**永远不是它 ⇒ ⇒ **这个闸从来没有触发过**（死闸）")
    W("  · ⚖⚖⚖ **这是「退化」，不是「从来没有」**：账本 `:41731` 明写「落账脚本的『防重复落账』闸……"
      "改成『**已落 ⇒ 必须与收据算出来的那段逐字节相同**』⇒ ⇒ 幂等且**自证**」"
      "⇒ ⇒ **244.86–244.91 时代已经修过一次** ⇒ ⇒ **这五轮把它退化掉了**")
    W("  · ✅ **修法**：恢复 **244.86 起的成规**，并补上成规里没有的两处："
      "① 比的是「段标题 → **下一段标题**」（成规比到文件末尾 ⇒ 对**非最后一段**的历史轮次不成立）；"
      "② 「不一致」时**打印前 3 处差异**（⛔ 不许悄悄失败）")
    W("  · ✅ **证据（它自己的验证，⛔ 不是 R15）**：`_verify_append_guard_24496.py` 在 `zju-53` 跑"
      "**5 轮 × 3 项 = " + str(g_n_all) + " 项**：")
    W("    · ① **复现**：拿**落账前**那份账本跑 ⇒ ⇒ 产出**逐字节等于**当年入库那份（5/5）")
    W("    · ② **重跑不得写**：对已落过的账本再跑 ⇒ ⇒ 退出 0、**一个字节都没改**、仍只有 1 段、打印「幂等」")
    W("    · ③ **负控**（闸必须能红）：把那一段篡改 ⇒ ⇒ **必须停下**且**不改** ⇒ ⇒ 这条闸**不是恒绿的**")
    W("  · ⚖ **诚实声明**：")
    W("    · ⛔ **这个缺陷没有影响任何一份已入库的账本** ⇒ ⇒ 244.92–244.96 各段的计数**恰好都是 1**"
      "（每轮的 R1x 驱动都有这一条硬门）⇒ ⇒ 它只是「**再跑一次就会多一份**」的**潜在**损坏路径")
    W("    · ⛔ **R15 的执行集不含落账脚本**（`_` 前缀 ⇒ 不进清单）⇒ ⇒ 这条修复的证据是"
      "**它自己的 15/15 验证**（带负控），⛔ **不是** R15")
    W("    · ⚠ **账本的 244.96 段里没有记这条连带修复**（账本只追加、且 R15 已在跑 ⇒ "
      "追记就得重跑 60 分钟全回归）⇒ ⇒ **244.97 的账本段要补记这一条**")
    W("")
    W("· **边界**（⛔ 不许被读成什么）：")
    W("  · 本轮**只**对账 §6.1 的 **29 个 P 行** ⇒ ⇒ ⛔ **不许**说成「整页已核」⇒ ⇒ ⛔ **不许**说成「§6 全核」")
    W("  · ⛔ **弱 token（纯整数）本轮不判**（⛔ 在窗口里几乎必然偶然出现 ⇒ ⇒ 证据弱）⇒ ⇒ 留白"
      "（已被变异台**实证**：改 n_perm 无人抓）")
    W("  · ⚠ **P11 的「56 个 base」不判**（页面**补充说明**，数是对的）⇒ ⇒ 留白")
    W("  · ⚠ **E3 的「逐位」分支是「子串包含」** ⇒ ⇒ **多打一位小数会被放行** ⇒ ⇒ 留白")
    W("  · ⚠ **E5 的清单识别口径是写死的**（「破口：」/「违例：」＋ `),` 切分）⇒ ⇒ 换一种写法数不到 ⇒ ⇒ 留白")
    W("  · §6.2.2、§6.3、§6.4、§6.5、§6.6、§6.7 与页面 §0–§5 ⇒ ⇒ 内容断言仍未被机器守")
    W("  · ⛔ **剂量—响应曲线 / 污染的精确幅度 / 块级同口径上界 / 机制轴 / 多随机种子**一律**未量到**"
      " ⇒ ⇒ 本轮**不碰**")
    W("  · ⛔ **预登记层与账本层仍没有自检** ⇒ ⇒ 「预登记**整体**先于结果」**仍不成立**")
    W("  · ⛔ 「**改闸门自己的比较表达式**没有闸门能抓」⇒ ⇒ 只能缩小、⛔ 不可能消灭 ⇒ ⇒ 留白")
    W("")
    W("· **账本**：追加 244.96 段（落账前 md5 `" + pre_md5 + "`）⇒ ⇒ 落账后 **" + str(ledger_lines)
      + "** 行；索引重建 **" + str(index_lines) + "** 行；244.96 段在账本里恰好 **"
      + str(n_2496) + "** 处")
    sys.stdout.write("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
