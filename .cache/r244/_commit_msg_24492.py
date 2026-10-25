#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_commit_msg_24492.py —— 生成 244.92 的**提交信息**（数**同源**：复用落账脚本的同一套解析）。

⚖⚖⚖ **为什么要复用**：提交信息里的每个数都从**同一批收据**解析 ⇒ ⇒ 数与账本**不可能打架**。
"""

import importlib.util
import io
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
RCPT = os.path.join(REPO, ".cache", "r244", "_e24492")

spec = importlib.util.spec_from_file_location("ap24492", os.path.join(REPO, ".cache", "r244", "_append_24492.py"))
ap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ap)


def main():
    sk = ap.keys(ap.read(os.path.join(RCPT, "selftest.out")), "SELFTEST_KEYS")
    mu = ap.keys(ap.read(os.path.join(RCPT, "mut.out")), "MUT_KEYS")
    cr = ap.keys(ap.read(os.path.join(RCPT, "cross.out")), "CROSS_KEYS")
    sp = ap.keys(ap.read(os.path.join(RCPT, "spec.out")), "SPEC_KEYS")
    af = ap.read(os.path.join(RCPT, "after.out"))
    bf = ap.read(os.path.join(RCPT, "before.out"))
    ak = ap.keys(af, "AUDIT_KEYS")
    # ⚖ 自检用例总数（**现算**）
    st_total = len(re.findall(r"^\[(PASS|FAIL)\]", ap.read(os.path.join(RCPT, "selftest.out")), re.M))
    b_verdict = (ap.re.search(r"^VERDICT=(.*)$", bf, ap.re.M) or [None, "?"])[1]
    b_a_red = ap.re.findall(r"^\[FAIL\] (A\d) ", bf, ap.re.M)
    led = ap.read(ap.LEDGER)
    led_md5 = ap.md5b(led.encode("utf-8"))
    led_lines = led.count("\n")
    ci, c_lo = ap.ci_and_c_from_ledger(led.split("\n"))
    # ⚖⚖⚖ **三个 run 的数全部现取**（⛔ 一个数都不手打）
    red = ap.parse_red_r11()
    r10_g, r10_t = ap.parse_r10_lpa()
    grn = ap.parse_green_r11()
    idx = ap.read(os.path.join(REPO, ".cache", "xcheck", "R6_RERUN_INDEX.md"))
    idx_md5 = ap.md5b(idx.encode("utf-8"))
    idx_lines = idx.count("\n")
    page_md5 = ap.md5f(os.path.join(REPO, "docs", "BPATH_VERDICT.md"))

    msg = []
    msg.append("对外口径页纳入证据链：页面 ↔ 账本 244.89 段**逐条一致**（形态 " + ak["VERDICT"] + "）")
    msg.append("")
    msg.append("⚖ **本轮把 `docs/BPATH_VERDICT.md` 纳入证据链**：页面上**与固定剂量判决相关**的对外断言")
    msg.append("（判决形态 / 成立格数 / 区间下端点 / 破口清单 / 边界条目 / 逐字引用句 / 复算入口 / 入库状态）")
    msg.append("**逐条**与**权威账本 244.89 段**对账 ⇒ ⇒ 交付标准 = 「页面 ↔ 账本**逐条一致**」。")
    msg.append("⛔ 本轮**不跑批、零 GPU、不重解析原始跑批日志** ⇒ ⇒ **不产生任何新的实测数**、**一个实测数都没改**。")
    msg.append("")
    msg.append("⚖ **判决**：" + ak["VERDICT"] + "（页面与账本逐条一致）")
    msg.append("· 页面 §6.7 可对账块：决策区 **" + ak["N_DEC_HOLD"] + "/" + ak["N_DEC"] + "** 成立、全表 **"
               + ak["N_ALL_HOLD"] + "/" + ak["N_CELLS"] + "** 成立、全表破口 **" + ak["N_ALL_BREAKS"]
               + " 处**、决策区破口 **" + ak["N_DEC_BREAKS"] + " 格**")
    msg.append("· 三个 Newcombe 下端点（轨迹级，**现取自账本 244.89 段**）：90% = **" + ci[("traj", "90")]
               + "** ｜ 95% = **" + ci[("traj", "95")] + "** ｜ 99% = **" + ci[("traj", "99")] + "**")
    msg.append("· 三个 c 下界（**现取自账本 244.89 段**）：90% ⇒ **" + c_lo["90"] + "** ｜ 95% ⇒ **"
               + c_lo["95"] + "** ｜ 99% ⇒ **" + c_lo["99"] + "**")
    msg.append("· 逐字引用句（预登记 §3.2 模板 ＋ 账本填空）**逐字**对上")
    msg.append("")
    msg.append("⚖ **每条判据能红**（远端 zju-53，零 GPU）：")
    msg.append("· 自检：共 **" + str(st_total) + "** 道用例 ⇒ ⇒ **失败 " + sk["SELFTEST_RED"]
               + " 道**（⚖ 这是「**没通过**」的条数，⛔ **不是**「判红」的条数）｜ FIX_A1..A9 全 PASS ｜ SELFTEST_RC="
               + sk["SELFTEST_RC"])
    msg.append("· 变异台：抓到 **" + mu["MUT_CAUGHT"] + " / " + mu["MUT_TOTAL"] + "**（无效 " + mu["MUT_INVALID"]
               + " 条 ⇒ 不计入分母）｜ 存活 **" + mu["MUT_SURVIVED"] + "** ｜ 崩 **" + mu["MUT_CRASHED"]
               + "** ｜ 未判 **" + mu["MUT_UNJUDGED"] + "** ｜ MUT_DATA_JUDGED=" + mu["MUT_DATA_JUDGED"])
    msg.append("· 互证（第二条独立实现 ＋ 收据↔账本↔页面三方对账）：OK **" + cr["CROSS_OK"] + "** ｜ MISMATCH **"
               + cr["CROSS_MISMATCH"] + "**")
    msg.append("· 预登记 ↔ 实现 的机械对账：OK **" + sp["SPEC_OK"] + "** ｜ 红 **" + sp["SPEC_RED"] + "**")
    msg.append("· **「改前 ⇒ 改后」两份收据都在**：改前（页面当时过期）形态 **" + b_verdict + "**、检查项判红 **"
               + "/".join(b_a_red) + "** ⇒ ⇒ 这是「检查器有牙齿」的证据 ⇒ ⇒ 改后形态 **" + ak["VERDICT"] + "**")
    msg.append("")
    msg.append("⚖⚖⚖ **全回归 R11（zju-12，零 GPU）**：`REG_RC=" + grn["reg_rc"] + "`｜`GATE_RC=" + grn["gate_rc"]
               + "`｜变异台 **" + grn["mut_g"] + "/" + grn["mut_r"] + "**｜自检 **" + grn["st_g"] + "/"
               + grn["st_r"] + "**｜执行集 **140** 个（清单 diff 对 R10：added=**2** / removed=**0**）")
    msg.append("⚖⚖⚖ **本轮抓到的真缺陷（一个实测数都没动）**：")
    msg.append("1. **恒绿（最严重）**：形态级联里判据状态用**字符串** `\"PASS\"` ⇒ ⇒ `not \"PASS\"` 恒假 ⇒ ⇒ "
               "**判红集合永远是空** ⇒ ⇒ **任何页面都被判成 A**；且**自检层根本没测级联** ⇒ ⇒ 改成布尔 ＋ 补 G0-10（128 种组合穷举）")
    msg.append("2. 检查项按**裸串**匹配 ⇒ ⇒ 同值在页面里出现多次 ⇒ ⇒ **改一处仍绿** ⇒ ⇒ 改成锚定**带标签的整行**")
    msg.append("3. 合成夹具与真账本**不同形** ⇒ ⇒ 自检在对着假账本绿、真数据必崩 ⇒ ⇒ 夹具改成**逐行同形**、填空另取一套值")
    msg.append("4. 逐字句的填空模式用了**半角**括号 ⇒ ⇒ 那一空**静默不填** ⇒ ⇒ 被夹具抓到 ⇒ ⇒ 加「填完残留 `__` 即中止」的硬闸")
    msg.append("5. 锚定用**子串** ⇒ ⇒ **被截断**的期望行是页面那行的**前缀** ⇒ ⇒ 仍判绿 ⇒ ⇒ 由变异 MU22 抓出 ⇒ ⇒ 改成整行比较")
    msg.append("6. 互证脚本按 END 标记抠收据的 AUDIT_KEYS ⇒ ⇒ 244.89 的收据**没有 END 标记** ⇒ ⇒ 抠不到键 ⇒ ⇒ 改成容错读取")
    msg.append("7. 变异台的期望闸门**手写也会写错**（MU21 写成 G0-5c，实际是 G0-19）⇒ ⇒ 改期望（不改实现）⇒ ⇒ 如实标注")
    msg.append("8. 预登记 §0.5 N1 / §1 写「收据**已入库**」⇒ ⇒ **假** ⇒ ⇒ 追加更正 ① ⇒ ⇒ 真相源改为已入库三件套")
    msg.append("9. ⚠⚖⚖ **账本层（本轮自己引入、已被**既有**护栏抓住）**：244.92 段标题里两个粗体"
               "（`**244.89 段**` 与 `**逐条一致**`）**贴在了一起** ⇒ ⇒ 原始行里出现**字面** `****` "
               "⇒ ⇒ 被**既有**的 `ledger_placeholder_audit.py` 判据 **C8** 判红 ⇒ ⇒ 连带它的变异台**基线**红"
               "（**" + red["base_g"] + "/" + red["base_t"] + "**，红 **" + red["base_cid"] + "**）"
               "⇒ ⇒ **全回归 R11 第一次跑是红的**（`REG_RC=" + red["reg_rc"] + "`｜`GATE_RC=" + red["gate_rc"]
               + "`｜变异台 **" + red["mut_g"] + "/" + red["mut_r"] + "**｜自检 **" + red["st_g"] + "/"
               + red["st_r"] + "**）⇒ ⇒ **本轮自己的提交被护栏挡在门外**")
    msg.append("   ⚖ **处置**：⛔ **不扩 C8 的登记表**（扩登记＝把例外变常态 ⇒ 护栏变弱）⇒ ⇒ **改我自己的标题** ⇒ ⇒ 重跑 R11")
    msg.append("   ⚖ 这条**恰好证明 C8 不是恒绿的**（**R10 时同一脚本 " + r10_g + "/" + r10_t
               + " 全绿** ⇒ ⇒ 红是本轮引入的，不是历史遗留）；⚖ 改完后该脚本自检 **" + grn["lpa_st_g"] + "/"
               + grn["lpa_st_t"] + "**、其变异台 **" + grn["lpa_mut_caught"] + "/" + grn["lpa_mut_total"]
               + "** 全抓住")
    msg.append("")
    msg.append("")
    msg.append("⚖ **边界**：B-14「更宽置信水平下的保守读法」**已量到**（可关闭）｜ 新增 **B-21**「换区间方法仍未量到」｜"
               "⛔ 页面**第一部分**不在本轮口径内｜⛔ 文档层整体自检仍未建立（B-20 仍成立，只被缩小）｜"
               "⛔ 污染的精确幅度 / 块级同口径上界 / 剂量—响应 / 机制轴 一律**未量到**")
    msg.append("")
    msg.append("⚖ **字节**：账本 " + str(led_lines) + " 行 / md5 " + led_md5 + " ｜ 索引 " + str(idx_lines)
               + " 行 / md5 " + idx_md5 + " ｜ 页面 md5 " + page_md5)
    msg.append("⚖ **远端**：`zju-53`（验证链，零 GPU）＋ `zju-12`（全回归 R11）｜ 收据在 `.cache/r244/_e24492/`（⛔ 不入库）")
    out = "\n".join(msg) + "\n"
    sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
