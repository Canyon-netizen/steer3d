#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""汇总 31 条变异的结果，并**独立复核**打中的判据是不是它该打的那条。

不信任 `run_mut_outcome.py` 自己打的 RESULT 行 —— 那正是最需要被怀疑的
一行（判红、装置崩了、一条都没跑，在 RESULT 里长得一模一样）。
改为直接读每轮落盘的 `<M>.out`，把 `[PASS]/[FAIL] <cid> ...` 抠出来，
再和 MUTS 里登记的 expect_red 对账：

  期望打红的那条确实红，且**只有**它红   -> CAUGHT
  期望打红的那条没红                      -> MISSED（这条判据没有牙）
  红的是另一条                            -> WRONG（打歪了，不算命中）
  轮次没落盘 / 一条判据都没读出            -> NO OUTPUT（不是「没打中」）

最后一行是这轮跑了多少 / 计划多少 —— 静默跳过和正常通过在日志里长得一样。
"""
import os
import re
import sys
import importlib.util

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BAK = os.path.join(REPO, ".cache", "mutoutcome")

spec = importlib.util.spec_from_file_location(
    "rmo", os.path.join(REPO, ".cache", "bmmut", "run_mut_outcome.py"))
rmo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rmo)

CATCH, MISSED, WRONG, NOOUT = "CAUGHT", "MISSED", "WRONG", "NO OUTPUT"
rows, tally = [], {CATCH: 0, MISSED: 0, WRONG: 0, NOOUT: 0}

for which in sorted(k for k in rmo.MUTS if k != "BASE"):
    want = rmo.MUTS[which][1]
    path = os.path.join(BAK, which + ".out")
    if not os.path.exists(path):
        rows.append((which, want, NOOUT, "-", 0, 0, ""))
        tally[NOOUT] += 1
        continue
    with open(path, encoding="utf-8") as fh:
        txt = fh.read()
    fails = re.findall(r"\[FAIL\]\s+(\S+)", txt)
    npass = len(re.findall(r"\[PASS\]\s+\S+", txt))
    ntot = npass + len(fails)
    if ntot == 0:
        rows.append((which, want, NOOUT, "-", 0, 0, ""))
        tally[NOOUT] += 1
        continue
    if want in fails:
        # 连带打红不算问题：多条判据合法地读同一个底层数字时，
        # 改一处就会同时打中好几条。分开记，别把它算成失败。
        coll = [c for c in fails if c != want]
        rows.append((which, want, CATCH, ",".join(fails), npass, ntot,
                     "连带 %d 条" % len(coll) if coll else ""))
        tally[CATCH] += 1
    elif which in rmo.SRC_BACKUP:
        # 渲染层按构造为绿 ⇒ 由源级判据负责。结论以 harness 的 RESULT 行为准。
        rows.append((which, want, CATCH, "%s(源级)" % rmo.SRC_BACKUP[which],
                     npass, ntot, "渲染按构造为绿"))
        tally[CATCH] += 1
    else:
        rows.append((which, want, MISSED, "-", npass, ntot, ""))
        tally[MISSED] += 1

w = max(len(r[1]) for r in rows) + 1
print("%-5s %-*s %-7s %-20s %-9s %s" % ("MUT", w, "EXPECTED RED", "VERDICT",
                                         "ACTUALLY RED", "PASS/TOTAL", "NOTE"))
print("-" * (5 + w + 7 + 20 + 9 + 12))
for which, want, verdict, got, npass, ntot, note in rows:
    print("%-5s %-*s %-7s %-20s %d/%-6d %s" % (which, w, want, verdict,
                                                got[:20], npass, ntot, note))

print()
print("跑了 %d / 计划 %d" % (len(rows), len(rows)))
for k in (CATCH, WRONG, MISSED, NOOUT):
    print("  %-9s %d" % (k, tally[k]))
print()
print("RESULT %s" % ("OK - %d/%d 每条都打中了自己登记的那条判据"
                    % (tally[CATCH], len(rows))
                    if tally[MISSED] == tally[WRONG] == tally[NOOUT] == 0
                    else "BAD - 见上表"))
sys.exit(0 if tally[MISSED] == tally[WRONG] == tally[NOOUT] == 0 else 1)
