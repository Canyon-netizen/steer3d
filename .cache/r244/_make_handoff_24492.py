#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_make_handoff_24492.py —— 生成 `.cache/xcheck/HANDOFF_24492.md`（**不入库**）。

⚖ **数同源**：复用 `_append_24492.py` 的同一套解析 ⇒ ⇒ 交接里的数与账本**不可能打架**。
"""

import importlib.util
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
RCPT = os.path.join(REPO, ".cache", "r244", "_e24492")
OUT = os.path.join(REPO, ".cache", "xcheck", "HANDOFF_24492.md")

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
    b_verdict = (ap.re.search(r"^VERDICT=(.*)$", bf, ap.re.M) or [None, "?"])[1]
    b_a_red = ap.re.findall(r"^\[FAIL\] (A\d) ", bf, ap.re.M)
    led = ap.read(ap.LEDGER)
    led_md5 = ap.md5b(led.encode("utf-8"))
    led_lines = led.count("\n")
    # ⚖⚖⚖ 面板数**现取**（账本 244.89 段 ＋ AUDIT_KEYS）⇒ ⇒ 交接里的数与账本**不可能打架**
    ci, c_lo = ap.ci_and_c_from_ledger(led.split("\n"))
    st_total = len(ap.re.findall(r"^\[(PASS|FAIL)\]", ap.read(os.path.join(RCPT, "selftest.out")), ap.re.M))
    red = ap.parse_red_r11()
    r10_g, r10_t = ap.parse_r10_lpa()
    grn = ap.parse_green_r11()
    idx = ap.read(os.path.join(REPO, ".cache", "xcheck", "R6_RERUN_INDEX.md"))
    idx_md5 = ap.md5b(idx.encode("utf-8"))
    page_md5 = ap.md5f(os.path.join(REPO, "docs", "BPATH_VERDICT.md"))
    reg = ""
    regp = os.path.join(RCPT, "reg_24492.txt")
    if os.path.isfile(regp):
        reg = ap.read(regp)

    L = []
    A = L.append
    A("# 交接 · 244.92（对外口径页纳入证据链）")
    A("")
    A("## 上手三步")
    A("")
    A("1. **先读账本尾部**：`/Users/zhourui/code/steer3d/.cache/xcheck/R6_RERUN_PREREG.md`"
      "（唯一权威历史；本轮之后 " + str(led_lines) + " 行 ｜ md5 `" + led_md5 + "`）")
    A("2. **再读本文件**（全文）")
    A("3. `git log --oneline -10` ＋ `git status --porcelain`"
      "（工作区有同事的改动与未跟踪文件，⛔ **不碰、不提交**）")
    A("")
    A("## 本轮一句话")
    A("")
    A("> 把**对外口径页** `docs/BPATH_VERDICT.md` 纳入证据链：它的对外断言**逐条**与**账本 244.89 段**对账"
      "⇒ ⇒ 交付标准 = 「页面 ↔ 账本**逐条一致**」⇒ ⇒ 本轮形态 **" + ak["VERDICT"] + "**。")
    A("> ⛔ **不跑批、零 GPU、不重解析原始跑批日志** ⇒ ⇒ **一个实测数都没改**。")
    A("")
    A("## 判决与口径")
    A("")
    A("| 项 | 值 |")
    A("|---|---|")
    A("| 判决形态 | **" + ak["VERDICT"] + "**（页面与账本逐条一致） |")
    A("| 保守读法 · 决策区 | **" + ak["N_DEC_HOLD"] + "/" + ak["N_DEC"] + "** 成立（联合置信 ≥ 90% 的 "
      + ak["N_DEC"] + " 格） |")
    A("| 保守读法 · 全表 | **" + ak["N_ALL_HOLD"] + "/" + ak["N_CELLS"] + "** 成立 |")
    A("| 破口 | 全表 **" + ak["N_ALL_BREAKS"] + " 处**，决策区内 **" + ak["N_DEC_BREAKS"] + " 处** |")
    A("| CI_lo(traj) | 90% = **" + ci[("traj", "90")] + "** ｜ 95% = **" + ci[("traj", "95")]
      + "** ｜ 99% = **" + ci[("traj", "99")] + "** |")
    A("| CI_lo(block) | 90% = **" + ci[("block", "90")] + "** ｜ 95% = **" + ci[("block", "95")]
      + "** ｜ 99% = **" + ci[("block", "99")] + "** |")
    A("| c 的下界 | 90% ⇒ **" + c_lo["90"] + "** ｜ 95% ⇒ **" + c_lo["95"] + "** ｜ 99% ⇒ **"
      + c_lo["99"] + "** |")
    A("| 逐字引用句 | 预登记 §3.2 模板 ＋ 账本填空，**逐字**对上 |")
    A("")
    A("## 证据链（每条判据能红）")
    A("")
    A("| 项 | 结果 |")
    A("|---|---|")
    A("| 自检（合成夹具，零账本零页面零 GPU） | 共 **" + str(st_total) + "** 道用例 ⇒ ⇒ **失败 "
      + sk["SELFTEST_RED"] + " 道**（⚖ 这是「**没通过**」的条数，⛔ **不是**「判红」的条数）｜ `FIX_A1`…`FIX_A9` 全 PASS |")
    A("| 变异台 | 抓到 **" + mu["MUT_CAUGHT"] + " / " + mu["MUT_TOTAL"] + "**（无效 " + mu["MUT_INVALID"]
      + " ⇒ 不计入分母）｜ 存活 **" + mu["MUT_SURVIVED"] + "** ｜ 崩 **" + mu["MUT_CRASHED"] + "** |")
    A("| 互证（第二条独立实现 ＋ 三方对账） | OK **" + cr["CROSS_OK"] + "** ｜ MISMATCH **" + cr["CROSS_MISMATCH"] + "** |")
    A("| 预登记 ↔ 实现 对账 | OK **" + sp["SPEC_OK"] + "** ｜ 红 **" + sp["SPEC_RED"] + "** |")
    A("| **全回归 R11**（zju-12，零 GPU） | `REG_RC=" + grn["reg_rc"] + "`｜`GATE_RC=" + grn["gate_rc"]
      + "`｜变异台 **" + grn["mut_g"] + "/" + grn["mut_r"] + "**｜自检 **" + grn["st_g"] + "/" + grn["st_r"] + "** |")
    A("| 改前 ⇒ 改后 | 改前形态 **" + b_verdict + "**（检查项判红 **" + "/".join(b_a_red)
      + "**）⇒ ⇒ 改后形态 **" + ak["VERDICT"] + "** |")
    A("")
    A("⚖⚖⚖ **本轮自己引入、又被抓回来的一处缺陷（值得下一轮记住）**：244.92 段标题里两个粗体"
      "（`**244.89 段**` 与 `**逐条一致**`）**贴在了一起** ⇒ ⇒ 原始行里出现**字面** `****` ⇒ ⇒ 被**既有**护栏 "
      "`ledger_placeholder_audit.py` 的 **C8** 判红 ⇒ ⇒ **R11 第一次跑是红的**（`REG_RC=" + red["reg_rc"]
      + "`｜变异台 **" + red["mut_g"] + "/" + red["mut_r"] + "**｜自检 **" + red["st_g"] + "/" + red["st_r"]
      + "**）⇒ ⇒ **处置**：⛔ **不扩 C8 的登记表** ⇒ ⇒ **改自己的标题** ⇒ ⇒ 重跑 R11。")
    A("⚖ **这条恰好证明 C8 不是恒绿的**（**R10 时同一脚本 " + r10_g + "/" + r10_t
      + " 全绿** ⇒ ⇒ 红是**本轮引入**的，不是历史遗留）；⚖ 改完后该脚本自检 **" + grn["lpa_st_g"] + "/"
      + grn["lpa_st_t"] + "**、其变异台 **" + grn["lpa_mut_caught"] + "/" + grn["lpa_mut_total"] + "** 全抓住。")
    A("⚖ **红的那份收据也留着**：`.cache/r244/_e24492/reg_24492_R11a_red.txt`（⛔ 不入库）；"
      "R10 对照收据 `reg_24489_R10.txt`；绿的那份 `reg_24492.txt`。")
    A("")
    A("⚖ **页面改了什么**（⛔ 只改**与账本不一致的对外断言**，同事的措辞与结构**一字未动**）："
      "标题「截至修订 244.88」→ **244.89**｜§6.0 作用域句 ｜§6.1 加 **P25–P29**｜§6.3 加 **244.89 台账行**"
      "＋ 改 244.88 行的「R9 未做」｜§6.4.1 **B-14** 改「已量到」＋ 加 **B-21**｜§6.4.4 逐字句换 244.89 那句"
      "（244.88 那句**逐字保留**、标为历史）｜§6.5 加 **RC-8a/8b/8c**｜§6.6 改掉「入库收尾未完成」｜**新增 §6.7 可对账块**。")
    A("")
    A("## 边界清单（⛔ 这些**仍未量到**，不许被页面读成已量到）")
    A("")
    A("- ✅ **B-14 关闭**：「更宽置信水平下的保守读法」**已量到**（27 格全表 ＋ 决策区 12 格）"
      "⇒ ⇒ 但量到的是**界与作用域**，⛔ **不是**「污染的精确幅度」。")
    A("- ✅ **新增 B-21**：「**换个区间方法**（承认聚类 vs score 型区间）在保守读法上的影响」**未量到**。")
    A("- ⛔ 页面**第一部分**（静态读数）**不在本轮口径内** ⇒ ⇒ ⛔ **不许**被说成「整页已核」。")
    A("- ⛔ 文档层（预登记 ＋ 账本）的**整体自检**仍未建立 ⇒ ⇒ 旧留白 **B-20 仍成立**（只被**缩小**）。")
    A("- ⛔ 「**污染不存在**」/ 污染的**精确幅度** / **块级**同口径污染上界 / **剂量—响应** / **机制轴** / "
      "**多随机种子** ⇒ ⇒ 一律**未量到**。")
    A("- ⚖ **留白**：改「**闸门自己的比较表达式**」这件事**没有闸门能抓** ⇒ ⇒ 只能用「正控 ＋ 负控共用同一函数」"
      "把它**缩小**，⛔ **不可能**消灭。")
    A("")
    A("## 下一轮（244.93+）")
    A("")
    A("1. **B-1 要点头**（**重解析原始跑批日志**）⇒ ⇒ 才能得到「**同口径**的块级污染上界」。")
    A("2. **换区间方法**（承认聚类 vs score 型）在保守读法上的影响 ⇒ ⇒ **要点头**。")
    A("3. **剂量轴 / 机制轴 / 多随机种子** ⇒ ⇒ **要点头**（跑批）。")
    A("4. **页面 ↔ 账本的一致性检查已进执行集** ⇒ ⇒ 以后每轮落账后**都要重跑它**"
      "（页面若忘了更新 ⇒ ⇒ **红**）⇒ ⇒ 这就是「**现状表有人盯着**」那一条的机器版。")
    A("")
    A("## 字节")
    A("")
    A("| 件 | md5 |")
    A("|---|---|")
    A("| 账本 `.cache/xcheck/R6_RERUN_PREREG.md` | `" + led_md5 + "`（" + str(led_lines) + " 行） |")
    A("| 索引 `.cache/xcheck/R6_RERUN_INDEX.md` | `" + idx_md5 + "` |")
    A("| 页面 `docs/BPATH_VERDICT.md` | `" + page_md5 + "` |")
    if reg:
        for m in ap.re.finditer(r"^([0-9a-f]{32})\s+(\S+)$", reg, ap.re.M):
            A("| " + m.group(2) + " | `" + m.group(1) + "` |")
    A("")
    A("⚖ **远端**：`zju-53`（验证链，零 GPU）＋ `zju-12`（全回归 R11）｜"
      "收据在 `.cache/r244/_e24492/`（⛔ **不入库**）")
    A("")

    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        fh.write("\n".join(L))
    print("已写出 %s（%d 字节）" % (OUT, os.path.getsize(OUT)))
    print("HANDOFF_RC=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
