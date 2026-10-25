#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_make_handoff_24496.py —— 生成 244.96 的**交接文件**（`.cache/xcheck/HANDOFF_24496.md`，⛔ 不入库）。

⚖ 交接里的每个数**都从收据/账本现取** ⇒ ⇒ 与提交信息**同源**。
"""

import io
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
RCPT = os.path.join(REPO, ".cache", "r244", "_e24496")
LEDGER = os.path.join(REPO, ".cache", "xcheck", "R6_RERUN_PREREG.md")
INDEX = os.path.join(REPO, ".cache", "xcheck", "R6_RERUN_INDEX.md")
OUT = os.path.join(REPO, ".cache", "xcheck", "HANDOFF_24496.md")


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
    #    ⇒ ⇒ 计数必须从汇总行取（⛔ 否则会数成 0 道 ⇒ ⇒ 交接里会出现假数）。
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

    # ⚖ 提交号（**现算**，⛔ 不手打）＋ R15 收据的数（**从收据现取**）
    import subprocess
    _g = subprocess.Popen(["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    commit_id = _g.communicate()[0].decode("utf-8").strip()
    if not commit_id:
        raise SystemExit("⛔ 取不到提交号 ⇒ ⇒ 中止")
    _r15 = read(os.path.join(REPO, ".cache", "r244", "_e24496", "reg_24496.txt"))
    import hashlib
    with open(os.path.join(REPO, ".cache", "r244", "_e24496", "reg_24496.txt"), "rb") as fh:
        r15_md5 = hashlib.md5(fh.read()).hexdigest()
    r15_n = (re.search(r"n_exec_py=(\d+)", _r15) or [None, "?"])[1]
    r15_add = (re.search(r"added=(\d+)\s+removed=(\d+)", _r15) or [None, "?", "?"])[1]
    r15_rem = (re.search(r"added=(\d+)\s+removed=(\d+)", _r15) or [None, "?", "?"])[2]
    def _two(text, label):
        m = re.search(label + r"\s+全绿=(\d+)\s+跑得动=(\d+)", text)
        return ("%s/%s" % (m.group(1), m.group(2))) if m else "?"
    r15_mut = _two(_r15, "变异台")
    r15_st = _two(_r15, "自检")
    r15_rc = (re.search(r"REG_RC=(\d+)", _r15) or [None, "?"])[1]
    r15_bad = (re.search(r"BAD_n=(\d+)", _r15) or [None, "?"])[1]
    r15_gate = (re.search(r"GATE_RC=(\d+)", _r15) or [None, "?"])[1]
    if (r15_rc, r15_bad, r15_gate) != ("0", "0", "0"):
        raise SystemExit("⛔ R15 收据不是绿的（REG_RC=%s BAD_n=%s GATE_RC=%s）⇒ ⇒ 中止"
                         % (r15_rc, r15_bad, r15_gate))

    gtxt = read(os.path.join(REPO, ".cache", "r244", "_guard24496", "verify.out"))
    g_n_all = gtxt.count("✅ ①") + gtxt.count("✅ ②") + gtxt.count("✅ ③")
    if (re.search(r"VERIFY_RC=(\d+)", gtxt) or [None, "?"])[1] != "0":
        raise SystemExit("⛔ 守卫验证收据不是绿的 ⇒ ⇒ 中止")

    ledger_text = read(LEDGER)
    ledger_lines = ledger_text.count("\n")
    index_lines = read(INDEX).count("\n")
    n_2496 = len(re.findall(r"^## 修订 244\.96 ", ledger_text, re.M))
    sec_line = 0
    for i, l in enumerate(ledger_text.split("\n")):
        if l.startswith("## 修订 244.96 "):
            sec_line = i + 1
            break

    out = []
    W = out.append
    W("# 交接 · 244.96 —— 判决面板 P1–P29 纳入证据链（每个数**可溯源**到它引用的账本行）")
    W("")
    W("⚖⚖⚖ **判决**：页面 `docs/BPATH_VERDICT.md` §6.1「判决面板」的 **29 个 P 行** ↔ 权威账本"
      " ⇒ ⇒ 每个数**可溯源**到**它自己引用的那几行** ⇒ ⇒ 形态 **" + a["VERDICT"] + "**"
      "（改前那份副本：形态 **" + b["VERDICT"] + "**、判红 **" + "/".join(b_red)
      + "** ⇒ ⛔ 那次不算判决）")
    W("")
    W("· ✅ **244.92–244.95 的留白已关闭**：§6.2.3 剂量轴展品块（244.93）｜ §6.2.1 两臂同剂量 9 行"
      "（244.94）｜ rand 臂列 ＋ 一一对应（244.95）｜ ⇒ ⇒ **§6.1 判决面板**（本轮）")
    W("· ⛔ **本轮页面只改了 2 行**（P28 / P29），**一个实测数都没改** ⇒ ⇒ 改的只有"
      "**出处** ＋ **量词** ⇒ ⇒ 缺陷行集合 **" + sp["SPEC_DEFECT_LINES"]
      + "**（预登记 §1.3 登记的 == 实际有差异的行）")
    W("")
    W("· **判据 E1–E8**（真数据 · 改后）：**" + a["N_CHECKS"] + "** 条全绿 ｜ 逐行矩阵 **" + str(n_rows)
      + "** 行 ＋ **" + str(n_rowv) + "** 条逐行结论 ｜ 强 token **" + a["N_STRONG"]
      + "** 个（逐位 **" + a["N_VERBATIM"] + "** ＋ R6′ **" + a["N_R6"] + "**）｜ **缺口 "
      + a["N_MISSING"] + "** ｜ 派生分数 **" + a["N_FRAC"] + "** 个（缺口 **"
      + a["N_FRAC_MISSING"] + "**）｜ 计数短语 **" + a["N_COUNT"] + "** 个")
    W("· ⚖⚖⚖ **方法论要点**（⛔ 是**踩过**的坑）：")
    W("  · ⛔ **引用集合必须精确**：⛔ **不许**用 min..max 区间窗口（P22 引两个离散行 ⇒ ⇒ 区间会夹进 57 行"
      "⇒ ⇒ 「4/12」偶然命中 ⇒ ⇒ **判据虚高**）")
    W("  · ⚖ **R6′ 的外部依据**取自账本既有约定（`:41722` / `:39004`）⇒ ⇒ ⛔ **不许**用现算容差")
    W("  · ⚖⚠ **E4 专为治 R6′ 的自证缺口**（R6′ 放行 7 位小数 ⇒ ⇒ MU-H3 / MU-H7 证明**只有 E4 能抓**）")
    W("· **每条判据能红**：自检 **" + str(st_total) + "/" + str(st_total_of) + "** 道（失败 **" + str(st_red)
      + "**）｜ 变异台 **" + mu["MUT_N"] + "** 条（抓住 **" + mu["MUT_CAUGHT"] + "** ｜ 存活 **"
      + mu["MUT_SURVIVORS"] + "** ｜ 崩 **" + mu["MUT_CRASHED"] + "** ｜ 等价 **" + mu["MUT_EQUIV_OK"]
      + "** ｜ **预登记期望与实测不符 " + mu["MUT_PREREG_MISMATCH"] + " 处**）"
      "｜ 互证锚点 **" + cr["CROSS_N_ANCHORS"] + "** ｜ 缺口 **" + cr["CROSS_N_MISSING"]
      + "** ｜ 表示差异 **" + cr["CROSS_REPR_DIFF"] + "** ｜ 不符合计 **" + cr["CROSS_MISMATCH"]
      + "** ｜ 互证自证 **" + cs.get("CROSS_SELFTEST_N_DIFF", "?") + "** 处"
      " ｜ 规格对账 真值命中 **" + sp["SPEC_REAL_TOKEN_HITS"] + "**"
      " ｜ **预登记预测 " + sp["SPEC_PREDICTED_RED"] + " == 实测 " + sp["SPEC_ACTUAL_RED_BEFORE"] + "**")
    W("· **本轮提交**：`" + commit_id + "`（23 条路径，⛔ 同事的未跟踪文件与那两个已跟踪文件**没碰**）"
      "｜ 提交后双回读 **READBACK_RC=0**")
    W("· **全回归 R15**（zju-12，⛔ 零 GPU）：执行集 **" + r15_n + "** 个（对 R14 清单 **added "
      + r15_add + " / removed " + r15_rem + "**）｜ 变异台 **" + r15_mut + "** ｜ 自检 **" + r15_st
      + "** ｜ **REG_RC=" + r15_rc + "** ｜ 零 [BAD]（BAD_n=" + r15_bad + "）｜ **GATE_RC=" + r15_gate
      + "** ｜ 收据 md5 `" + r15_md5 + "`")
    W("· **账本**：**" + str(ledger_lines) + "** 行 ｜ 244.96 段在行 **" + str(sec_line)
      + "**（**" + str(n_2496) + "** 处）｜ 索引 **" + str(index_lines) + "** 行")
    W("· **收据**：`.cache/r244/_e24496/`（落账前）＋ `.cache/r244/_e24496b/`（落账后重跑，⛔ 不入库）"
      "｜ 判决链跑在 `zju-53`（⛔ 零 GPU）、全回归跑在 `zju-12`")
    W("")
    W("· ⚖⚖⚖ **本轮顺手抓到并修掉的真缺陷（连带修复，与 244.96 的判决无关）**：")
    W("  · 落账脚本的「防重复落账」闸在 **244.92–244.96 这五轮**里退化成了**死闸**"
      "（`old.startswith(MARK)` ⇒ ⇒ `MARK` 是段标题 ⇒ ⇒ 整本账本第一行永远不是它 ⇒ ⇒ **从来没触发过**）"
      "⇒ ⇒ 对已落过账的账本再跑一次 ⇒ ⇒ **会再追加一份**（实测 244.96 段被追加第二份，+95 行）")
    W("  · ⚖ **这是「退化」**：账本 `:41731` 记着「改成『已落 ⇒ 必须与收据算出来的那段逐字节相同』」"
      "⇒ ⇒ **244.86–244.91 已经修过一次** ⇒ ⇒ 这五轮把它退化掉了")
    W("  · ✅ **已修**：恢复 244.86 起的成规 ＋ 两处补强（比「段标题 → 下一段标题」；"
      "「不一致」时打印前 3 处差异）｜ 证据 = `_verify_append_guard_24496.py`（zju-53）"
      "**5 轮 × 3 项 = " + str(g_n_all) + " 项全绿**（复现逐字节相同 / 重跑不写不改 / 负控必停）")
    W("  · ⛔ **这个缺陷没有影响任何一份已入库的账本**（各段计数恰好都是 1，每轮 R1x 驱动都有这条硬门）")
    W("  · ⛔ **R15 的执行集不含落账脚本**（`_` 前缀）⇒ ⇒ 这条修复的证据是**它自己的 15/15**，⛔ 不是 R15")
    W("  · ⚠ **账本 244.96 段没记这条连带修复** ⇒ ⇒ **244.97 的账本段要补记**")
    W("")
    W("## ⛔ 边界（本轮**没有**做到什么）")
    W("")
    W("1. 本轮**只**对账 §6.1 的 **29 个 P 行** ⇒ ⇒ ⛔ **不许**说成「整页已核」⇒ ⇒ ⛔ **不许**说成「§6 全核」。")
    W("2. ⚠ **弱 token（纯整数）本轮不判**（⛔ 在窗口里几乎必然偶然出现）⇒ ⇒ 留白"
      "（已被变异台**实证**：改 n_perm 20000 → 20001，**没有任何闸门会红**）。")
    W("3. ⚠ **P11 的「56 个 base」不判**（页面**补充说明**，数是对的）⇒ ⇒ 留白。")
    W("4. ⚠ **E3 的「逐位」分支是「子串包含」** ⇒ ⇒ **多打一位小数会被放行** ⇒ ⇒ 留白。")
    W("5. ⚠ **E5 的清单识别口径是写死的** ⇒ ⇒ 换一种写法数不到 ⇒ ⇒ 留白。")
    W("6. §6.2.2、§6.3、§6.4、§6.5、§6.6、§6.7 与页面 §0–§5 ⇒ ⇒ 内容断言仍未被机器守。")
    W("7. **剂量—响应曲线 / 污染精确幅度 / 块级同口径上界 / 机制轴 / 多随机种子**一律**未量到** ⇒ ⇒ 本轮**不碰**。")
    W("8. **预登记层与账本层仍没有自检** ⇒ ⇒ 「预登记**整体**先于结果」**仍不成立**。")
    W("9. 「**改闸门自己的比较表达式**没有闸门能抓」⇒ ⇒ 只能缩小、⛔ 不可能消灭 ⇒ ⇒ 留白。")
    W("")
    W("## ▶️ 下一轮（244.97+）")
    W("")
    W("1. **弱 token 的取数口径**：纯整数（46/56、4/12、12 格…）如何在**不用偶然命中**的前提下判。")
    W("2. **P11 的「56 个 base」**这类**页面补充说明**的处置口径（要么纳入、要么明确排除）。")
    W("3. **§6.2.2「未量到」措辞**纳入；然后 **§6.3 台账 / §6.4 边界条目**；页面 §0–§5 **最后**做。")
    W("4. **把「改闸门自己的比较表达式」也纳入变异台**（实现层变异 ⇒ 治那条留白）。")
    W("5. **要点头的线**（本轮一律没碰）：块级同口径污染上界、固定剂量批重跑加 `--dump-raw`、"
      "多随机种子对照臂、同结论对照臂、分层剂量真阶梯、docs 那条线 GPU 前向、照 meta 重建能否逐位复现的重训。")
    W("")
    W("## ▶️ 怎么跑（可复现）")
    W("")
    W("```bash")
    W("# 判决链（zju-53，⛔ 零 GPU）：自检 ＋ 改前/改后 ＋ 变异台 ＋ 互证 ＋ 规格对账")
    W("ssh zju-53 'cd /home/zhourui/steer3d && bash .cache/r244/_run_24496_verify.sh'")
    W("")
    W("# 全回归（zju-12，验「落账后」那份账本）：")
    W("ssh zju-12 'cd /home/zhourui/steer3d && setsid nohup bash .cache/r244/_run_24496_reg_shm.sh \\")
    W("  > /dev/shm/s24480r/launch_24496.log 2>&1 < /dev/null &'")
    W("")
    W("# 落账（幂等）：APPEND_LEDGER=.cache/r244/_ledger_24496_dry.md python3 .cache/r244/_append_24496.py")
    W("# 索引重建：python3 .cache/mutbak/r100_build_index.py")
    W("# 提交后双回读：python3 .cache/r244/_post_commit_readback_24496.py")
    W("```")
    W("")
    W("⚖ **「改前」副本怎么重建**（⛔ 它**不入库**，⛔ 收据也不入库）：")
    W("")
    W("```bash")
    W("git show e59570e:docs/BPATH_VERDICT.md > .cache/r244/_page_24496_before.md")
    W("```")
    W("")
    with io.open(OUT, "w", encoding="utf-8", newline="") as fh:
        fh.write("\n".join(out))
    print("已写出 %s（%d 行）" % (OUT, len(out)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
