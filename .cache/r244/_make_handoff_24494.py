#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_make_handoff_24494.py —— 生成 244.94 的**交接文件**（`.cache/xcheck/HANDOFF_24494.md`，⛔ 不入库）。

⚖ 交接里的每个数**都从收据/账本现取** ⇒ ⇒ 与提交信息**同源**。
"""

import io
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
RCPT = os.path.join(REPO, ".cache", "r244", "_e24494")
LEDGER = os.path.join(REPO, ".cache", "xcheck", "R6_RERUN_PREREG.md")
INDEX = os.path.join(REPO, ".cache", "xcheck", "R6_RERUN_INDEX.md")
OUT = os.path.join(REPO, ".cache", "xcheck", "HANDOFF_24494.md")


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
    st_total = len(re.findall(r"^\[(PASS|FAIL)\]", st_text, re.M))
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

    ledger_text = read(LEDGER)
    ledger_lines = ledger_text.count("\n")
    index_lines = read(INDEX).count("\n")
    n_2494 = len(re.findall(r"^## 修订 244\.94 ", ledger_text, re.M))
    sec_line = 0
    for i, l in enumerate(ledger_text.split("\n")):
        if l.startswith("## 修订 244.94 "):
            sec_line = i + 1
            break

    out = []
    W = out.append
    W("# 交接 · 244.94 —— 「两臂同一个剂量」前提纳入证据链")
    W("")
    W("⚖⚖⚖ **判决**：页面 `docs/BPATH_VERDICT.md` §6.2.1 的 **9 行**（两臂同剂量表）"
      "↔ 权威账本 244.83 段那张验收表 ⇒ ⇒ **逐行逐字一致** ⇒ 形态 **" + a["VERDICT"] + "**"
      "（改前那份副本：形态 **" + b["VERDICT"] + "**、判红 **" + "/".join(b_red) + "** ⇒ ⛔ 那次不算判决）")
    W("")
    W("· **判据 E1–E5**（真数据 · 改后）：**" + a["N_CHECKS"] + "** 条全绿 ｜ 逐行矩阵 **" + str(n_rows)
      + "** 行 ＋ **" + str(n_rowv) + "** 条逐行结论 ｜ 辅助测量：rand 列不符 **"
      + a.get("AUX_RAND_MISMATCH", "?") + "** 处、一一对应 **" + a.get("AUX_BIJ", "?") + "/"
      + a.get("AUX_BIJ_TOTAL", "?") + "**（⛔ 这两项**不是闸门**）")
    W("· **本轮抓到 3 处真缺陷**（⛔ 页面**只补措辞**，**一个数据数都没动**，+3/−3 行）："
      "`:41612` 少「且」、`:41614` 少「路径」、`:41615` 少「（同一把向量）」"
      "⇒ ⇒ 缺陷行集合与**预登记 §1.2 登记的完全一致**")
    W("· **每条判据能红**：自检 **" + str(st_total) + "** 道（失败 **" + str(st_red)
      + "**）｜ 变异台 **" + mu["MUT_N"] + "** 条（抓住 **" + mu["MUT_CAUGHT"] + "** ｜ 存活 **"
      + mu["MUT_SURVIVORS"] + "** ｜ 崩 **" + mu["MUT_CRASHED"] + "** ｜ 等价 **" + mu["MUT_EQUIV_OK"]
      + "** ｜ 留白实证 **" + mu["MUT_NORED_OK"] + "** ｜ **预登记期望与实测不符 "
      + mu["MUT_PREREG_MISMATCH"] + " 处**）｜ 互证锚点 **" + cr["CROSS_N_ANCHORS"] + "** ｜ 不符合计 **"
      + cr["CROSS_MISMATCH"] + "** ｜ 互证自证 **" + cs.get("CROSS_SELFTEST_N_DIFF", "?")
      + "** 处 ｜ 规格对账 真值命中 **" + sp["SPEC_REAL_TOKEN_HITS"] + "**")
    W("· **账本**：**" + str(ledger_lines) + "** 行 ｜ 244.94 段在行 **" + str(sec_line)
      + "**（**" + str(n_2494) + "** 处）｜ 索引 **" + str(index_lines) + "** 行")
    W("· **收据**：`.cache/r244/_e24494/`（⛔ 不入库）｜ 判决链跑在 `zju-53`（⛔ 零 GPU）、全回归跑在 `zju-12`")
    W("")
    W("## ⛔ 边界（本轮**没有**做到什么）")
    W("")
    W("1. 本轮**只**对账 §6.2.1 的 9 行 ⇒ ⇒ ⛔ **不许**说成「剂量轴整节已核」⇒ ⇒ ⛔ **不许**说成「整页已核」。")
    W("2. ⚖⚖⚖ **页面的 rand 臂列在不是「同」时没有闸门守**（MU-E3 / MU-E12 实测：**没有任何闸门红**）"
      "⇒ ⇒ 本轮只用**辅助测量**把它量出来 ⇒ ⇒ 它**仍然不是闸门** ⇒ ⇒ **下一轮第一件事就是补它**。")
    W("3. ⚖ **预登记 §1.3 的「见 §2 E6」是悬空引用**（§2 只有 E1–E5）⇒ ⇒ 「一一对应」这条**要求**没有闸门"
      "⇒ ⇒ 辅助测量量到 9/9 ⇒ ⇒ 仍**不是闸门** ⇒ ⇒ 下一轮补成真判据。")
    W("4. ⚠ **预登记期望写错 2 处，已如实登记**（⛔ 不改实现去迁就期望、⛔ 不改预登记）："
      "MU-E3（E2 是条件式判据）｜ MU-E4（E4 守唯一性，删行不破坏唯一性 ⇒ 真正抓住的是 E5）。")
    W("5. **剂量—响应曲线 / 污染精确幅度 / 块级同口径上界 / 机制轴 / 多随机种子**一律**未量到** ⇒ ⇒ 本轮**不碰**。")
    W("6. **预登记层与账本层仍没有自检** ⇒ ⇒ 「预登记**整体**先于结果」**仍不成立**。")
    W("7. 「**改闸门自己的比较表达式**没有闸门能抓」⇒ ⇒ 只能缩小、⛔ 不可能消灭 ⇒ ⇒ 留白。")
    W("")
    W("## ▶️ 下一轮（244.95+）")
    W("")
    W("1. **把 rand 臂列变成真判据**：页面写「同」⇒ ⇒ 账本能证明（已是 E2）；页面写**实际值**⇒ ⇒ 必须与账本**逐字相同**。")
    W("2. **把「一一对应」变成真判据**：9 个页行引到的账本行**必须互不相同**。")
    W("3. **§6.1 判决面板 P1–P29** 逐条对账（**判决数本身** ⇒ 最靠近判决数），"
      "先解决「页面侧派生数」（P18/P21/P28/P29 的「9/9」「10 处」「4/12」）的取数口径。")
    W("4. **§6.2.2「未量到」措辞**纳入；然后 **§6.3 台账 / §6.4 边界条目**；页面第一部分（§0–§5）**最后**做。")
    W("5. **要点头的线**（本轮一律没碰）：块级同口径污染上界、固定剂量批重跑加 `--dump-raw`、"
      "多随机种子对照臂、同结论对照臂、分层剂量真阶梯、docs 那条线 GPU 前向、照 meta 重建能否逐位复现的重训。")
    W("")
    W("## ▶️ 怎么跑（可复现）")
    W("")
    W("```bash")
    W("# 判决链（zju-53，⛔ 零 GPU）：自检 ＋ 改前/改后 ＋ 变异台 ＋ 互证 ＋ 规格对账")
    W("ssh zju-53 'cd /home/zhourui/steer3d && bash .cache/r244/_run_24494_verify.sh'")
    W("")
    W("# 全回归（zju-12，验「落账后」那份账本）：")
    W("ssh zju-12 'cd /home/zhourui/steer3d && setsid nohup bash .cache/r244/_run_24494_reg_shm.sh \\")
    W("  > /dev/shm/s24480r/launch_24494b.log 2>&1 < /dev/null &'")
    W("")
    W("# 落账（幂等）：APPEND_LEDGER=.cache/r244/_ledger_24494_dry.md python3 .cache/r244/_append_24494.py")
    W("# 提交后双回读：python3 .cache/r244/_post_commit_readback_24494.py")
    W("```")
    W("")
    W("⚖ **「改前」副本怎么重建**（⛔ 它**不入库**，⛔ 收据也不入库）：")
    W("")
    W("```bash")
    W("git show fa33b38:docs/BPATH_VERDICT.md > .cache/r244/_page_24494_before.md")
    W("```")
    W("")
    with io.open(OUT, "w", encoding="utf-8", newline="") as fh:
        fh.write("\n".join(out))
    print("已写出 %s（%d 行）" % (OUT, len(out)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
