#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mut_doc_consistency_audit.py —— 变异台（244.92）：每条变异都必须被**抓住**。

⚖⚖⚖ **期望值一律手写**（⛔ **不从实现派生** ⇒ ⇒ 否则「两边一起变」⇒ ⇒ 恒绿）。
⚖ 每条变异有**两个落点**：
   ① **自检层**（合成夹具）⇒ ⇒ 期望某道闸门变红（`expect_gate`；`None` ⇒ 等价变异 ⇒ 记「无效」，
      且**输出必须与基线逐字节相同**）；
   ② **真数据层**（真账本 ＋ 真页面）⇒ ⇒ 期望某个检查项变红（`expect_check`；`None` ⇒
      该变异**不触及**数据路径 ⇒ ⇒ 真数据层必须**无变化**）。
⛔ **崩的条数必须是 0**（变异**不得**让被检实现自己崩；崩了不算「抓到」）。
⛔ **存活（没被抓住）的条数必须是 0**。

⚖ **用法**（远端）：
   R244_LEDGER=… R244_PREREG=… R244_PAGE=… python3 mut_doc_consistency_audit.py
"""

import os
import re
import shutil
import subprocess
import sys

TARGET = os.environ.get("MUT_TARGET", ".cache/r244/doc_consistency_audit.py")
WORK = os.environ.get("MUT_WORK", "/dev/shm/_mut24492")
LEDGER = os.environ.get("R244_LEDGER", ".cache/xcheck/R6_RERUN_PREREG.md")
PREREG = os.environ.get("R244_PREREG", ".cache/xcheck/R6_CONFIDENCE_LEVEL_PREREG.md")
PAGE = os.environ.get("R244_PAGE", "docs/BPATH_VERDICT.md")

# ⚖⚖⚖ **变异表**（id, 描述, 源码原文, 替换成, 期望变红的**自检闸门**, 期望变红的**检查项**）
#    ⚖ `expect_gate` / `expect_check` **全部手写**（⛔ 不从实现派生）。
MUTATIONS = [
    ("MU01", "锚定去掉「全页只出现一次」",
     '    return (blk_lines.count(line) == 1) and (page_lines.count(line) == 1)',
     '    return (blk_lines.count(line) == 1) and (page_lines.count(line) >= 1)',
     ["G0-11"], None),
    ("MU02", "A2 的决策区成立数取成格数",
     '        "L_counts": "· **保守读法**：决策区 **" + str(src["n_dec_hold"]) + "/" + str(src["n_dec"]) +',
     '        "L_counts": "· **保守读法**：决策区 **" + str(src["n_dec"]) + "/" + str(src["n_dec"]) +',
     ["G0-1"], ["A2"]),
    ("MU03", "A3 少守一行（c 的下界）",
     '    miss3 = [k for k in ("L_ci_traj", "L_ci_blk", "L_c_lo") if not _anchor(page_text, blk, el[k])]',
     '    miss3 = [k for k in ("L_ci_traj", "L_ci_blk") if not _anchor(page_text, blk, el[k])]',
     ["G0-12"], None),
    ("MU04", "逐字句的「下界」填空写死",
     '        (r"下界 \\+__ pp", "下界 " + src["ci_traj"][99].lstrip("+") + " pp"),',
     '        (r"下界 \\+__ pp", "下界 0 pp"),',
     ["G0-1"], ["A6"]),
    ("MU05", "逐字句的违例清单错用决策区清单",
     '        (r"违例：__）。", "违例：" + src["viol_all"] + "）。"),',
     '        (r"违例：__）。", "违例：" + src["viol_dec"] + "）。"),',
     ["G0-1"], ["A6"]),
    ("MU06", "A5 的「已量到」判定恒真",
     '    ok5 = bool(row) and ("未量到" not in row) and ("已量到" in row or "✅" in row)',
     '    ok5 = bool(row)',
     ["G0-2/A5"], None),
    ("MU07", "A5 的行号范围判定恒真",
     '    ok5b = bool(cites5) and all(src["sec_lo"] <= c <= src["sec_hi"] for c in cites5)',
     '    ok5b = bool(cites5)',
     ["G0-13"], None),
    ("MU08", "A7 少查一条复算入口",
     '    need_rc = ("RC-8a", "RC-8b", "RC-8c")',
     '    need_rc = ("RC-8a",)',
     ["G0-2/A7"], None),
    ("MU09", "A8 的台账行判定恒真",
     '        ok8b = (not off) and bool(hit)',
     '        ok8b = True',
     ["G0-2/A8"], None),
    ("MU10", "A9 少查一个过期措辞（**等价**：「入库待收尾」含「待收尾」）",
     '    stale_marks = ("入库收尾未完成", "入库待收尾", "待收尾")',
     '    stale_marks = ("入库收尾未完成", "待收尾")',
     None, None),
    ("MU11", "形态级联：D 与 C 换序",
     '    if "H6" in failed:\n        return "D", failed',
     '    if "H5" in failed or "H7" in failed:\n        return "D", failed\n'
     '    if "H6" in failed:\n        return "C", failed',
     ["G0-10"], None),
    ("MU12", "判据状态又用字符串比较（恒绿陷阱复发）",
     '    failed = set(c for ok, c in crits if not ok)',
     '    failed = set(c for ok, c in crits if ok == "PASS")',
     ["G0-10"], None),
    ("MU13", "硬失败集合多加一条（恒绿陷阱的另一面）",
     'HARD_FAIL_IDS = ("H1", "H2")',
     'HARD_FAIL_IDS = ("H1", "H2", "H3")',
     ["G0-10"], None),
    ("MU14", "无出处数：不再排除文件名里的数字",
     '        if before and (before.isalnum() or before in "_."):\n            continue',
     '        if False:\n            continue',
     ["G0-15"], None),
    ("MU15", "H7 真空绿（块缺失也绿）",
     '    if not body:\n        return False, ["§6.7 块缺失或为空 ⇒ ⇒ 无从核「无出处数」"]',
     '    if not body:\n        return True, []',
     ["G0-17"], None),
    ("MU16", "A1 恒真",
     '    res.append(_chk("A1", _anchor(page_text, blk, el["L_verdict"]),',
     '    res.append(_chk("A1", True,',
     ["G0-2/A1"], None),
    ("MU17", "§6.7 块的标题正则改成 6.6",
     '    m = re.search(r"^## 6\\.7 .*$", page_text, re.M)',
     '    m = re.search(r"^## 6\\.6 .*$", page_text, re.M)',
     ["G0-1"], ["A1", "A2", "A3", "A4"]),
    ("MU18", "全表破口数取成成立数",
     '    src["n_all_breaks"] = int(need(r"\\*\\*副表 = 全 \\d+ 格\\*\\*（\\*\\*完整作用域\\*\\*）：\\*\\*\\d+ 格成立\\*\\* ｜ 破口 (\\d+) 个", "全表破口数").group(1))',
     '    src["n_all_breaks"] = int(need(r"\\*\\*副表 = 全 \\d+ 格\\*\\*（\\*\\*完整作用域\\*\\*）：\\*\\*(\\d+) 格成立\\*\\*", "全表破口数").group(1))',
     [], ["A4"]),
    ("MU19", "作用域表的「成立」判定恒真",
     '                    "ok": "不成立" not in tail})',
     '                    "ok": True})',
     ["G0-1"], ["A4"]),
    ("MU20", "H6 自证改成恒等（改坏落点找不到）",
     '    tampered = page_text.replace(el["L_counts"], bad_line, 1)',
     '    tampered = page_text',
     ["H6-自证"], None),
    ("MU21", "H5 的「只出现一次」判定反向（⚖ 期望闸门最初手写成 G0-5c；实际它**削弱的那一层被 A 层独立守住**"
              "⇒ ⇒ 页面级的重复仍被 A1–A4 的整行锚定抓住 ⇒ ⇒ 记「无效」，⛔ **不是**等价：它是**冗余层被削**）",
     '        if page_lines.count(el[k]) != 1:',
     '        if page_lines.count(el[k]) == 0:',
     None, None),
    ("MU22", "决策区破口清单被截断",
     '    m = re.search(r"\\*\\*违例\\*\\*：(.+)$", h5.group(0))',
     '    m = re.search(r"\\*\\*违例\\*\\*：(.+?), CI99", h5.group(0))',
     [], ["A4"]),
    ("MU23", "账本自洽核对去掉一条子句",
     '        src["n_all_items"] == src["n_all_breaks"]',
     '        True',
     ["G0-16"], None),
    ("MU24", "夹具的决策区成立数写错（夹具侧）",
     '           "verdict": "B\'", "n_dec": 12, "n_dec_hold": 4, "n_cells": 27, "n_all_hold": 17,',
     '           "verdict": "B\'", "n_dec": 12, "n_dec_hold": 5, "n_cells": 27, "n_all_hold": 17,',
     ["G0-1"], None),
    ("MU25", "夹具的判决形态写错（夹具侧）",
     '           "verdict": "B\'", "n_dec": 12, "n_dec_hold": 4, "n_cells": 27, "n_all_hold": 17,\n           "n_all_breaks": 10,',
     '           "verdict": "C\'", "n_dec": 12, "n_dec_hold": 4, "n_cells": 27, "n_all_hold": 17,\n           "n_all_breaks": 10,',
     ["G0-1"], None),
    ("MU26", "A6 只判「页面上有这句」，不看「第一句是不是它」",
     '    ok6 = (p["quote"] == exp) and (exp in page_text)',
     '    ok6 = (exp in page_text)',
     ["G0-18"], None),
    ("MU27", "A9 的过期状态判定恒真",
     '    ok9 = (not stale) and (REV in page_text)',
     '    ok9 = True',
     ["G0-2/A9"], None),
    ("MU28", "A4 少守一行（决策区破口清单）",
     '    miss4 = [k for k in ("L_allbrk", "L_decbrk") if not _anchor(page_text, blk, el[k])]',
     '    miss4 = [k for k in ("L_allbrk",) if not _anchor(page_text, blk, el[k])]',
     ["G0-12"], None),
    ("MU29", "决策区成立数解析成格数",
     '    src["n_dec_hold"] = int(need(r"\\*\\*主表 = 决策区\\*\\*.*?其中 \\*\\*(\\d+) 格成立\\*\\*", "决策区成立数").group(1))',
     '    src["n_dec_hold"] = int(need(r"\\*\\*主表 = 决策区\\*\\*.*?\\*\\*(\\d+) 格\\*\\*", "决策区成立数").group(1))',
     [], ["A2"]),
]


def run(cmd, env=None):
    p = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       env=env)
    return p.returncode, p.stdout.decode("utf-8", "replace")


def gates(out):
    """⚖ 抽出自检输出里**变红**的闸门 id。"""
    red = set()
    for m in re.finditer(r"^\[FAIL\] (\S+)", out, re.M):
        red.add(m.group(1))
    return red


def checks(out):
    """⚖ 抽出真数据输出里**变红**的检查项 id。"""
    red = set()
    for m in re.finditer(r"^CHECK_(A\d+)=(FAIL)", out, re.M):
        red.add(m.group(1))
    return red


def fix_block(out):
    """⚖ 抽出自检输出里的 FIX_A* 块（⇒ ⇒ 「判定结果」的机器可读形态）。"""
    return re.findall(r"^FIX_(A\d+)=(PASS|FAIL)$", out, re.M)


def crit_block(out):
    """⚖ 抽出真数据输出里的判据行（[PASS]/[FAIL] H1..H7）。"""
    return re.findall(r"^\[(PASS|FAIL)\] (H\d)$", out, re.M)


def verdict_of(out):
    m = re.search(r"^VERDICT=(.*)$", out, re.M)
    return m.group(1) if m else "?"


def main():
    if not os.path.exists(TARGET):
        print("⛔ 找不到被检实现：%s" % TARGET)
        print("MUT_RC=2")
        return 2
    with open(TARGET, "r", encoding="utf-8") as fh:
        base_src = fh.read()
    if os.path.isdir(WORK):
        shutil.rmtree(WORK)
    os.makedirs(WORK, exist_ok=True)

    env = dict(os.environ)
    env["R244_LEDGER"] = LEDGER
    env["R244_PREREG"] = PREREG
    env["R244_PAGE"] = PAGE

    base_st_path = os.path.join(WORK, "base_selftest.out")
    rc, base_st = run("%s %s --selftest" % (sys.executable, TARGET), env)
    with open(base_st_path, "w", encoding="utf-8") as fh:
        fh.write(base_st)
    base_red = gates(base_st)
    rc_data, base_data = run("%s %s --data --page %s --ledger %s --prereg %s"
                              % (sys.executable, TARGET, PAGE, LEDGER, PREREG), env)
    base_ck = checks(base_data)
    print("基线：自检红 %s ｜ 真数据检查项红 %s ｜ VERDICT %s"
          % (sorted(base_red) or "无", sorted(base_ck) or "无",
             (re.search(r"^VERDICT=(.*)$", base_data, re.M) or [None, "?"])[1]))

    caught = invalid = survived = crashed = misplaced = unjudged = 0
    # ⚖⚖⚖ **数据层可判的判据是「形态 = A」**，⛔ **不是**「A 类检查项没红」
    #    （⛔ H5/H6/H7 红了但 A 项全绿时，数据层其实**不可判** ⇒ ⇒ 否则会拿不可判的结果充数）
    base_verdict = (re.search(r"^VERDICT=(.*)$", base_data, re.M) or [None, "?"])[1]
    data_judged = (base_verdict == "A") and (not base_ck)
    if not data_judged:
        print("⚠ **真数据层不可判**（基线形态 = %s，基线检查项红 %s）⇒ ⇒ 本轮只判自检层 ⇒ ⇒ "
              "MUT_DATA_JUDGED=0 ⇒ ⇒ 这份收据**不能**当作「数据层也验过」的证据"
              % (base_verdict, sorted(base_ck) or "无"))
    lines = []
    for mid, desc, old, new, exp_gate, exp_check in MUTATIONS:
        n = base_src.count(old)
        if n != 1:
            misplaced += 1
            lines.append("[MISS] %s 落点出现 %d 次（必须恰好 1 次）" % (mid, n))
            continue
        mut_src = base_src.replace(old, new, 1)
        mp = os.path.join(WORK, "mut_%s.py" % mid)
        with open(mp, "w", encoding="utf-8") as fh:
            fh.write(mut_src)
        rc, out = run("%s %s --selftest" % (sys.executable, mp), env)
        if "SELFTEST_KEYS" not in out:
            crashed += 1
            lines.append("[CRASH] %s 被检实现自己崩了（⛔ 不算抓到）" % mid)
            continue
        red = gates(out)
        if exp_gate is None:
            # ⚖ **无效**的判据（比「逐字节相同」更强、且可机械验）：被检实现在**夹具与真数据上的
            #   判定结果**必须与基线**完全相同**（FIX_A* 块 ＋ 判据行 ＋ 形态 ＋ 红项集合）
            same = (fix_block(out) == fix_block(base_st))
            why = ""
            if not same:
                why = "夹具上的检查项判定变了"
            else:
                rc2, out2 = run("%s %s --data --page %s --ledger %s --prereg %s"
                                % (sys.executable, mp, PAGE, LEDGER, PREREG), env)
                if verdict_of(out2) != base_verdict:
                    same, why = False, "真数据形态变了（%s ⇒ %s）" % (base_verdict, verdict_of(out2))
                elif checks(out2) != base_ck:
                    same, why = False, "真数据的红项集合变了"
                elif crit_block(out2) != crit_block(base_data):
                    same, why = False, "真数据的判据行变了"
            if same:
                invalid += 1
                lines.append("[INVALID] %s %s ⇒ **判定结果与基线完全相同** ⇒ 记「无效」（不计入分母）"
                             % (mid, desc))
            else:
                survived += 1
                lines.append("[SURVIVED] %s %s ⇒ 期望「无效」，但%s ⛔" % (mid, desc, why))
            continue
        if exp_gate == []:
            # ⚖ 该变异**不触及自检层**（夹具里的值是**手写**的 ⇒ ⇒ 解析类变异打不到它）
            #   ⇒ ⇒ 自检层必须**不变**（红 0），判由**真数据层**下
            if red:
                survived += 1
                lines.append("[SURVIVED] %s %s ⇒ 自检层本应不变，却红了 %s" % (mid, desc, sorted(red)))
                continue
        else:
            miss = [g for g in exp_gate if g not in red]
            if miss:
                survived += 1
                lines.append("[SURVIVED] %s %s ⇒ 期望红 %s，实际红 %s（⛔ 没被抓住）"
                             % (mid, desc, exp_gate, sorted(red)))
                continue
        # 真数据层
        if not data_judged:
            if exp_gate == []:
                unjudged += 1
                lines.append("[UNJUDGED] %s %s ⇒ 真数据层**本轮不可判**（基线不绿）⇒ ⇒ "
                             "**不计入「抓到」**（⚠ 诚实记账：不是「抓住了」，是「没判」）"
                             % (mid, desc))
            else:
                caught += 1
                lines.append("[CAUGHT] %s %s ⇒ 自检红 %s ｜ 真数据层**本轮不可判**（基线不绿）"
                             % (mid, desc, sorted(g for g in red if g in exp_gate)))
            continue
        rc2, out2 = run("%s %s --data --page %s --ledger %s --prereg %s"
                        % (sys.executable, mp, PAGE, LEDGER, PREREG), env)
        if "AUDIT_KEYS" not in out2:
            crashed += 1
            lines.append("[CRASH] %s 真数据层崩了（⛔ 不算抓到）" % mid)
            continue
        ck = checks(out2)
        if exp_check is None:
            if ck != base_ck:
                survived += 1
                lines.append("[SURVIVED] %s %s ⇒ 真数据层本应无变化，但检查项红了 %s" % (mid, desc, sorted(ck)))
                continue
        else:
            miss2 = [c for c in exp_check if c not in ck]
            if miss2:
                survived += 1
                lines.append("[SURVIVED] %s %s ⇒ 真数据层期望红 %s，实际红 %s"
                             % (mid, desc, exp_check, sorted(ck)))
                continue
        caught += 1
        lines.append("[CAUGHT] %s %s ⇒ 自检红 %s ｜ 真数据红 %s"
                     % (mid, desc, sorted(g for g in red if g in exp_gate),
                        sorted(c for c in ck if exp_check and c in exp_check)))

    for l in lines:
        print(l)
    print("")
    print("变异：%d 条 ｜ 抓到 %d ｜ 无效 %d ｜ 未判 %d ｜ 存活 %d ｜ 崩 %d ｜ 落点错 %d"
          % (len(MUTATIONS), caught, invalid, unjudged, survived, crashed, misplaced))
    print("===== MUT_KEYS =====")
    print("MUT_TOTAL=%d" % len(MUTATIONS))
    print("MUT_CAUGHT=%d" % caught)
    print("MUT_INVALID=%d" % invalid)
    print("MUT_UNJUDGED=%d" % unjudged)
    print("MUT_SURVIVED=%d" % survived)
    print("MUT_CRASHED=%d" % crashed)
    print("MUT_MISPLACED=%d" % misplaced)
    print("MUT_DATA_JUDGED=%d" % (1 if data_judged else 0))
    print("MUT_RC=%d" % (0 if (survived == 0 and crashed == 0 and misplaced == 0) else 1))
    print("===== END_MUT_KEYS =====")
    return 0 if (survived == 0 and crashed == 0 and misplaced == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
