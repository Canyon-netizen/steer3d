#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_cross_check_24492.py —— 互证：**第二条独立实现**重新抠页面、重新算期望值、逐条比。

⚖⚖⚖ **零共用代码**：⛔ **不 import** 被检实现；⛔ 解析口径**故意不同**
   （被检实现用「全文正则一次性匹配」，本脚本用「**逐行 startswith ＋ 手工切字段 ＋ findall**」）；
   ⛔ 填空用 **str.replace**（被检实现用 **re.sub**）。
⚖ **三方对账**：**收据 `de.out` 的 AUDIT_KEYS** ↔ **账本 244.89 段** ↔ **页面 `docs/BPATH_VERDICT.md`**
   ⇒ ⇒ 「页面上那个数」不可能与「跑出它的字节」脱节。

⚖ **用法**：
   R244_LEDGER=… R244_PREREG=… R244_PAGE=… R244_RECEIPT=… python3 _cross_check_24492.py
"""

import io
import os
import re
import sys

LEDGER = os.environ.get("R244_LEDGER", ".cache/xcheck/R6_RERUN_PREREG.md")
PREREG = os.environ.get("R244_PREREG", ".cache/xcheck/R6_CONFIDENCE_LEVEL_PREREG.md")
PAGE = os.environ.get("R244_PAGE", "docs/BPATH_VERDICT.md")
RECEIPT = os.environ.get("R244_RECEIPT", ".cache/r244/_e24489b/de.out")


def read(path):
    with io.open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def ledger_section(path):
    """⚖ 抠出 244.89 段（**逐行扫**，⛔ 不用被检实现的 section_of）。"""
    lines = read(path).split("\n")
    start = end = None
    for i, l in enumerate(lines):
        if start is None and l.startswith("## 修订 244.89 "):
            start = i
        elif start is not None and l.startswith("## 修订 "):
            end = i
            break
    if start is None:
        return None, None, None
    if end is None:
        end = len(lines)
    return start + 1, end, lines[start:end]


def ledger_bits(sec):
    """⚖ 逐行取字段（⛔ 与被检实现**不同**的取法）。"""
    b = {}
    for l in sec:
        if l.startswith("· **判决形态**：") and "verdict" not in b:
            b["verdict"] = l.split("：", 1)[1].strip().strip("*")
        elif l.startswith("· **主表 = 决策区**"):
            b["dec_n"] = l.split("**", 3)[3].split(" 格")[0]
            b["dec_hold"] = l.split("其中 **")[1].split(" 格")[0]
        elif l.startswith("· **副表 = 全"):
            b["all_n"] = l.split("全 ", 1)[1].split(" 格")[0]
            b["all_hold"] = l.split("：**", 1)[1].split(" 格")[0]
            b["all_break"] = l.split("破口 ", 1)[1].split(" 个")[0]
        elif l.startswith("· ⚖ **三个 Newcombe 下端点"):
            t = l.split("：", 1)[1]
            traj = t.split("CI_lo(traj)")[1].split("；")[0]
            blk = t.split("CI_lo(block)")[1]
            b["ci_traj"] = re.findall(r"=\s*\*\*([+-][0-9.]+)\*\*", traj)
            b["ci_blk"] = re.findall(r"=\s*\*\*([+-][0-9.]+)\*\*", blk)
        elif l.startswith("· ⚖ **c 的下界"):
            b["c_lo"] = re.findall(r"⇒\s*\*\*([+-][0-9.]+)\*\*", l.split("：", 1)[1])
        elif l.startswith("· **理由（原文）**："):
            r = l.split("：", 1)[1]
            b["reason"] = r
            m = re.search(r"跨水平 (\d+)/(\d+)，最紧 ([+-][0-9.]+) pp", r)
            b["sr"] = m.groups() if m else None
            m = re.search(r"点估计\*\*口径下成立（(\d+)/(\d+)，最紧 ([+-][0-9.]+) pp）", r)
            b["pt"] = m.groups() if m else None
            b["viol_all"] = r.split("破口：", 1)[1].strip()
        elif l.startswith("- [FAIL] **H5**"):
            b["viol_dec"] = l.split("**违例**：", 1)[1].strip()
    return b


def ledger_cells(sec):
    """⚖ 抠副表逐格（⛔ 逐行切字段）。"""
    cells = []
    started = False
    for l in sec:
        if l.startswith("· **副表 = 全"):
            started = True
            continue
        if not started:
            continue
        if not l.startswith("|"):
            if cells:
                break
            continue
        p = [x.strip() for x in l.strip().strip("|").split("|")]
        if len(p) < 7 or p[0] in ("CI 水平",) or set(p[0]) <= set("-: "):
            continue
        cells.append({"ci": p[0], "c": p[1], "var": p[2], "bound": p[3].strip("*"),
                      "conf": p[4], "dec": p[5], "ok": "不成立" not in p[6]})
    return cells


def page_block(path):
    """⚖ 抠页面 §6.7 块（⛔ 逐行扫 + 遇到下一个 '## ' 停）。"""
    lines = read(path).split("\n")
    start = None
    for i, l in enumerate(lines):
        if l.startswith("## 6.7 "):
            start = i
            break
    if start is None:
        return []
    out = []
    for l in lines[start + 1:]:
        if l.startswith("## "):
            break
        out.append(l)
    return out


def receipt_keys(path):
    """⚖ 抠收据里的 AUDIT_KEYS（⛔ 244.89 的收据**没有 END 标记** ⇒ ⇒ 读到下一个 '=====' 为止）。"""
    out = {}
    inside = False
    for l in read(path).split("\n"):
        if l.strip().startswith("===== AUDIT_KEYS"):
            inside = True
            continue
        if inside:
            if l.strip().startswith("====="):
                break
            if "=" in l:
                k, v = l.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def main():
    lo, hi, sec = ledger_section(LEDGER)
    if sec is None:
        print("⛔ 账本里没有 244.89 段")
        print("CROSS_RC=2")
        return 2
    b = ledger_bits(sec)
    cells = ledger_cells(sec)
    blk = page_block(PAGE)
    rec = receipt_keys(RECEIPT) if os.path.exists(RECEIPT) else {}

    ok = 0
    bad = []

    def cmp(name, got, want):
        nonlocal ok
        if got == want:
            ok += 1
        else:
            bad.append("%s：得到 %r，期望 %r" % (name, got, want))

    # ---- 期望的 7 个锚点行（**独立**构造：用 f-string，被检实现用字符串拼接）----
    want_lines = [
        f"· **判决形态**：**{b['verdict']}**",
        f"· **保守读法**：决策区 **{b['dec_hold']}/{b['dec_n']}** 成立，全表 **{b['all_hold']}/{b['all_n']}** 成立",
        f"· **全表破口**：**{b['all_break']} 处**",
        f"· **决策区破口（{len([c for c in cells if c['dec'] == '是' and not c['ok']])} 格）**：{b['viol_dec']}",
        f"· **CI_lo(traj)**：90% = **{b['ci_traj'][0]}** ｜ 95% = **{b['ci_traj'][1]}** ｜ 99% = **{b['ci_traj'][2]}**",
        f"· **CI_lo(block)**：90% = **{b['ci_blk'][0]}** ｜ 95% = **{b['ci_blk'][1]}** ｜ 99% = **{b['ci_blk'][2]}**",
        f"· **c 的下界**：90% ⇒ **{b['c_lo'][0]}** ｜ 95% ⇒ **{b['c_lo'][1]}** ｜ 99% ⇒ **{b['c_lo'][2]}**",
    ]
    names = ["L_verdict", "L_counts", "L_allbrk", "L_decbrk", "L_ci_traj", "L_ci_blk", "L_c_lo"]
    for nm, want in zip(names, want_lines):
        cmp("页面行 " + nm, blk.count(want), 1)

    # ---- 逐字引用句（**str.replace** 填空，⛔ 不用 re.sub）----
    pre = read(PREREG)
    tmpl = [l for l in pre.split("\n") if l.startswith("> 「『污染解释不了观测差』")]
    if not tmpl:
        bad.append("预登记里核不到 §3.2 模板")
    else:
        t = tmpl[0]
        t = t.replace("在 CI 水平 __ 上", "在 CI 水平 99 上")
        t = t.replace("下界 +__ pp", "下界 %s pp" % b["ci_traj"][2].lstrip("+"))
        t = t.replace("跨水平 __/3 成立", "跨水平 %s/%s 成立" % (b["sr"][0], b["sr"][1]))
        t = t.replace("（__/__ 口径成立", "（%s/%s 口径成立" % (b["pt"][0], b["pt"][1]))
        t = t.replace("最紧 +__ pp", "最紧 %s pp" % b["pt"][2].lstrip("+"))
        t = t.replace("）内 __/__ 格成立", "）内 %s/%s 格成立" % (b["dec_hold"], b["dec_n"]))
        t = t.replace("全表 __/27 格成立", "全表 %s/%s 格成立" % (b["all_hold"], b["all_n"]))
        t = t.replace("违例：__）。", "违例：%s）。" % b["viol_all"])
        quotes = [l for l in read(PAGE).split("\n") if l.startswith("> 「『污染解释不了观测差』")]
        cmp("逐字引用句", quotes[0] if quotes else "", t)

    # ---- 三方对账：收据 ↔ 账本 ----
    if not rec:
        bad.append("收据 %s 不存在或没有 AUDIT_KEYS" % RECEIPT)
    else:
        cmp("收据↔账本 VERDICT", rec.get("VERDICT"), b["verdict"])
        cmp("收据↔账本 N_DECISION", rec.get("N_DECISION"), b["dec_n"])
        cmp("收据↔账本 N_DECISION_HOLD", rec.get("N_DECISION_HOLD"), b["dec_hold"])
        cmp("收据↔账本 N_CELLS", rec.get("N_CELLS"), b["all_n"])
        cmp("收据↔账本 N_ALL_HOLD", rec.get("N_ALL_HOLD"), b["all_hold"])
        for i, lv in enumerate((90, 95, 99)):
            cmp("收据↔账本 CI_LO_TRAJ_%d" % lv, rec.get("CI_LO_TRAJ_%d" % lv), b["ci_traj"][i])
            cmp("收据↔账本 CI_LO_BLK_%d" % lv, rec.get("CI_LO_BLK_%d" % lv), b["ci_blk"][i])
            cmp("收据↔账本 CLO_%d_MAIN" % lv, rec.get("CLO_%d_MAIN" % lv), b["c_lo"][i])

        def tag(c):
            return "CI%s/c%s/%s" % (int(round(float(c["ci"]) * 100)),
                                    int(round(float(c["c"]) * 100)), c["var"])

        holds = ",".join(tag(c) for c in cells if c["dec"] == "是" and c["ok"])
        breaks = ",".join(tag(c) for c in cells if not c["ok"])
        cmp("收据↔账本 DECISION_HOLDS", rec.get("DECISION_HOLDS"), holds)
        cmp("收据↔账本 ALL_BREAKS", rec.get("ALL_BREAKS"), breaks)
        # ---- 三方对账：账本 ↔ 页面（破口清单的**内容**，不只是数）----
        cmp("页面 L_decbrk 的破口条数", b["viol_dec"].count("CI"), len([c for c in cells if c["dec"] == "是" and not c["ok"]]))
        cmp("理由行的全表破口条数", b["viol_all"].count("CI"), len([c for c in cells if not c["ok"]]))

    print("──── 互证逐条 ────")
    for x in bad:
        print("[MISMATCH] %s" % x)
    print("互证：OK %d ｜ MISMATCH %d" % (ok, len(bad)))
    print("独立重算的判决形态：%s" % b["verdict"])
    print("===== CROSS_KEYS =====")
    print("CROSS_OK=%d" % ok)
    print("CROSS_MISMATCH=%d" % len(bad))
    print("CROSS_FORM=%s" % b["verdict"])
    print("CROSS_RC=%d" % (0 if not bad else 1))
    print("===== END_CROSS_KEYS =====")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
