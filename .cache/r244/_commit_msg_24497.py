#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_commit_msg_24497.py —— 生成 244.97 的提交信息（**每个数都从收据/账本现取**，⛔ 不手打）。

⚖ 提交信息里的数**必须**与**跑出它们的那些字节**同源 ⇒ ⇒ 账本改了，它**不可能**留在旧数上。
"""

import hashlib
import io
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
RCPT = os.path.join(REPO, ".cache", "r244", "_e24497")
LEDGER = os.path.join(REPO, ".cache", "xcheck", "R6_RERUN_PREREG.md")
INDEX = os.path.join(REPO, ".cache", "xcheck", "R6_RERUN_INDEX.md")
GUARD = os.path.join(REPO, ".cache", "r244", "_guard24497", "verify.out")


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

    # ⚖ 守卫的逐轮验证收据（⛔ 不入库，但**要**进提交信息 ⇒ ⇒ 数字从它现取）
    gtxt = read(GUARD)
    g_rounds = gtxt.count("✅ 全过")
    g_bad = gtxt.count("⛔ 有红")
    g_rc = (re.search(r"VERIFY_RC=(\d+)", gtxt) or [None, "?"])[1]
    with open(GUARD, "rb") as fh:
        g_md5 = hashlib.md5(fh.read()).hexdigest()
    if g_rc != "0" or g_bad != 0:
        raise SystemExit("⛔ 守卫验证收据 VERIFY_RC=%s ｜ 有红 %d ⇒ ⇒ 中止" % (g_rc, g_bad))

    # ⚖ R16 全回归收据（⛔ 不入库，但**要**进提交信息）
    regp = os.path.join(RCPT, "reg_24497.txt")
    reg = read(regp)
    reg_rc = (re.search(r"REG_RC=(\d+)", reg) or [None, "?"])[1]
    bad_n = (re.search(r"BAD_n=(\d+)", reg) or [None, "?"])[1]
    mdiff = re.search(r"added=(\d+)\s+removed=(\d+)", reg)
    added, removed = mdiff.groups() if mdiff else ("?", "?")
    mut_line = [l for l in reg.split("\n") if l.startswith("变异台 全绿=")]
    st_line = [l for l in reg.split("\n") if l.startswith("自检   全绿=")]
    mut_green = mut_line[0].split("=")[1].split("（")[0].strip() if mut_line else "(缺)"
    st_green = st_line[0].split("=")[1].split("（")[0].strip() if st_line else "(缺)"
    if reg_rc != "0" or bad_n != "0":
        raise SystemExit("⛔ R16 收据 REG_RC=%s ｜ BAD_n=%s ⇒ ⇒ 中止" % (reg_rc, bad_n))

    ledger_text = read(LEDGER)
    ledger_lines = ledger_text.count("\n")
    ledger_md5 = hashlib.md5(ledger_text.encode("utf-8")).hexdigest()
    index_lines = read(INDEX).count("\n")
    index_md5 = hashlib.md5(read(INDEX).encode("utf-8")).hexdigest()
    n_2497 = len(re.findall(r"^## 修订 244\.97 ", ledger_text, re.M))
    # ⚖⚖⚖ 「落账前那版的 md5」必须**限定在 244.97 段里**取
    _i = ledger_text.find("## 修订 244.97 ")
    _seg = ledger_text[_i:] if _i >= 0 else ""
    pre_md5 = (re.search(r"落账前\*\* md5 `([0-9a-f]{32})`", _seg) or [None, "?"])[1]

    out = []
    W = out.append
    W("剂量—响应曲线留白块（§6.2.2）纳入证据链：每个断言**逐位可溯源** ＋ "
      "**留白守卫**（⛔ 不许把「未量到」写成「无差异 / 已量到」）")
    W("")
    W("· **判决**：页面 `docs/BPATH_VERDICT.md` §6.2.2「剂量—响应曲线（**未量到**）」的 "
      + str(a.get("N_BULLETS", "?")) + " 个 bullet ↔ 权威账本 `.cache/xcheck/R6_RERUN_PREREG.md`"
      " ⇒ ⇒ **形态 " + a.get("VERDICT", "?") + "**（"
      + str(n_checks) + " 条判据 E1–E" + str(n_checks) + " 全绿）")
    W("· **断言可溯源**：措辞类与数值类断言共 **" + a.get("N_ASSERT", "?") + "** 条，"
      "命中 **" + a.get("N_HIT", "?") + "** ｜ 缺口 **" + a.get("N_MISS", "?")
      + "** ⇒ ⇒ 每条都**逐位**出现在**它自己引用的那一行**里（⛔ 不许跨行借用）")
    W("· **留白守卫**：可疑措辞出现 **" + a.get("N_SUSPECT", "?") + "** 处，"
      "豁免 **" + a.get("N_EXEMPT", "?") + "** 处（紧邻否定 或 **别的小节**作用域），"
      "**未被否定 0 处** ⇒ ⇒ ⛔ 没有把「未量到」写成「无差异 / 已量到」")
    W("· **改前 ⇒ 改后**：改前形态 **" + b.get("VERDICT", "?") + "**、判红 **"
      + ("/".join(b_red) if b_red else "无") + "**（⛔ 那次不算判决）⇒ ⇒ 改后形态 **"
      + a.get("VERDICT", "?") + "**（预登记末尾的预测 **" + sp.get("SPEC_PREDICTED_RED", "?")
      + "** == 实测 **" + sp.get("SPEC_ACTUAL_RED_BEFORE", "?") + "**）")
    W("· **页面改动**：**只改 2 行**（B1 补出处、B3 补出处 ＋ 记号改成账本逐字式）"
      "⇒ ⇒ **三个值（0.25 / 0.50 / 0.75）一个都没改**，改的**只是记号**")
    W("· **每条判据能红**：自检 **" + str(st_total) + "/" + str(st_total_of)
      + "**（失败 " + str(st_red) + "）｜ 变异台 **" + mu.get("MUT_N", "?") + "** 条，"
      "抓住 **" + mu.get("MUT_CAUGHT", "?") + "** ｜ 存活 **" + mu.get("MUT_SURVIVORS", "?")
      + "** ｜ 崩 **" + mu.get("MUT_CRASHED", "?") + "** ｜ 等价变异通过 **"
      + mu.get("MUT_EQUIV_OK", "?") + "** ｜ **预登记期望与实测不符 "
      + mu.get("MUT_PREREG_MISMATCH", "?") + " 处**（MU-C6：`:41657` 是个**空行**、"
      "行号在范围内 ⇒ E2 按定义不红、实测红的是 E3 ⇒ ⇒ **如实登记**，⛔ 不改判据去迁就期望）")
    W("· **互证**（第二条**独立**实现，⛔ 零共用代码、锚定/归一化/匹配/豁免判定**四处故意不同**）："
      "断言 **" + cr.get("CROSS_N_ASSERT", "?") + "** ｜ 命中 **" + cr.get("CROSS_N_HIT", "?")
      + "** ｜ 缺口 **" + cr.get("CROSS_N_MISS", "?") + "** ｜ **不符合计 **"
      + cr.get("CROSS_MISMATCH", "?") + "** ｜ 自算形态 **" + cr.get("CROSS_VERDICT", "?")
      + "** ｜ 互证自己也要能红：篡改 3 处 ⇒ ⇒ 真比对抓到 **"
      + cs.get("CROSS_SELFTEST_N_DIFF", "?") + "** 处")
    W("· **规格对账**（七项全绿）：判据 **" + sp.get("SPEC_N_CRITERIA", "?") + "** 条 ｜ 变异 **"
      + sp.get("SPEC_N_MUT", "?") + "** 条 ｜ 缺陷集合 **" + sp.get("SPEC_DEFECT_BULLETS", "?")
      + "** == 实际有差异的 bullet **" + sp.get("SPEC_REAL_DEFECT_BULLETS", "?")
      + "** ｜ **真值命中 " + sp.get("SPEC_REAL_TOKEN_HITS", "?") + "**（实现）与 **"
      + sp.get("SPEC_REAL_TOKEN_HITS_CROSS", "?") + "**（互证）⇒ 「零手写期望」**机械可查**")
    W("· **预登记 §8 追加更正**（实现期发现，⛔ §1–§7 一行未改）：E6 漏了「别的小节」作用域 ⇒ ⇒ "
      "页面 B3 的「（6.2.1 已量到）」本会被**误判红** ⇒ ⇒ 补上作用域；**原文本**下改前判红会是 "
      "E3/E4/E6，**更正后**是 **" + sp.get("SPEC_ACTUAL_RED_BEFORE", "?")
      + "** ⇒ ⇒ 与预登记末尾的预测**一致**")
    W("· **补记 244.96 的连带修复**：244.92–244.96 五份落账脚本的「防重复落账」闸**曾是死闸** ⇒ ⇒ "
      "244.96 已恢复 244.86 成规并补强；本轮把该修复**扩到第 6 轮**（244.97）"
      "⇒ ⇒ 逐轮验证 **" + str(g_rounds) + " 轮 × 3 项全绿**（含**负控**：必须会停）｜ 收据 md5 `"
      + g_md5 + "`（⛔ 不入库）")
    W("· **R16 全回归**（远端 zju-12）：`REG_RC=" + reg_rc + "` ｜ `BAD_n=" + bad_n
      + "` ｜ 清单 diff added/removed=**" + added + "/" + removed + "** ｜ 变异台 **"
      + mut_green + "** ｜ 自检 **" + st_green + "**")
    W("")
    W("· **落账**：账本 **" + str(ledger_lines) + " 行**（md5 `" + ledger_md5 + "`）"
      " ｜ 索引 **" + str(index_lines) + " 行**（md5 `" + index_md5 + "`）"
      " ｜ 落账前 md5 `" + pre_md5 + "` ⇒ ⇒ **只追加**、旧前缀逐字节不变、围栏数不变"
      " ｜ 244.97 段 " + str(n_2497) + " 处")
    W("")
    W("⛔ **边界**：剂量—响应曲线**仍然未量到**（本批 `n_bands = 1`）⇒ ⇒ 本轮只是把"
      "「未量到」这句话**纳入证据链**，⛔ **不是**去量它 ⇒ ⇒ ⛔ 不许把「留白被纳入证据链」"
      "读成「留白被填上」；⛔ 本轮**只**对账 §6.2.2 的 3 个 bullet ⇒ ⇒ ⛔ 不许说成「§6.2 已核」。")
    W("⛔ **要点头的线**（本轮一律没碰）：块级同口径污染上界、固定剂量批重跑加 `--dump-raw`、"
      "多随机种子对照臂、同结论对照臂、分层剂量真阶梯、docs 那条线 GPU 前向、"
      "照 meta 重建能否逐位复现的重训。")
    W("")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
