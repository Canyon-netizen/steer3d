#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⚖ **生成 244.87 的交接文件**（`.cache/xcheck/HANDOFF_24487.md`；⛔ **不入库**，按惯例）。

⚖ **纪律**：交接里的数**全部从收据抠**（⛔ 不手抄）⇒ ⇒ 交接与账本/提交信息**同源**。
"""

import io
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
EV = os.path.join(REPO, ".cache", "r244", "_e24487")
OUT = os.path.join(REPO, ".cache", "xcheck", "HANDOFF_24487.md")


def _read(p):
    with io.open(p, encoding="utf-8", newline="") as fh:
        return fh.read()


def _need(p):
    if not os.path.isfile(p):
        raise SystemExit("⛔ 缺收据：%s" % p)
    return _read(p)


def _grab(txt, pat, what, flags=re.M):
    m = re.search(pat, txt, flags)
    if not m:
        raise SystemExit("⛔ 收据里核不到「%s」（模式 %s）" % (what, pat))
    return m


def main():
    st = _need(os.path.join(EV, "selftest.out"))
    de = _need(os.path.join(EV, "de.out"))
    mu = _need(os.path.join(EV, "mut.out"))
    cr = _need(os.path.join(EV, "cross.out"))
    sp = _need(os.path.join(EV, "spec.out"))
    rc = _need(os.path.join(EV, "receipt.txt"))

    m = re.search(r"===== AUDIT_KEYS =====\n(.*?)\n===== END_AUDIT_KEYS =====", de, re.S)
    K = {}
    for ln in m.group(1).splitlines():
        if "=" in ln:
            k, v = ln.split("=", 1)
            K[k.strip()] = v.strip()

    verdict = K["VERDICT"]
    m = re.search(r"自检（Phase-0 G0-1\.\.G0-7）：(\d+) 条 ｜ FAIL (\d+) 条", st)
    st_n, st_fail = m.groups()
    m = re.search(r"变异台：抓到 (\d+) / (\d+)（无效 (\d+) 条", mu)
    mut_caught, mut_total, mut_invalid = m.groups()
    mut_crash = _grab(mu, r"崩的条数：(\d+)", "崩的条数").group(1)
    m = re.search(r"互证：OK (\d+) ｜ MISMATCH (\d+)", cr)
    cr_ok, cr_bad = m.groups()
    cr_verdict = _grab(cr, r"^独立重算的判决形态：(\S+)$", "互证形态").group(1)
    m = re.search(r"对账条数：OK (\d+) ｜ 红 (\d+)", sp)
    sp_ok, sp_bad = m.groups()
    m = re.search(r"SELFTEST_RC=(\d+)\s+DE_RC=(\d+)\s+MUT_RC=(\d+)\s+CROSS_RC=(\d+)\s+SPEC_RC=(\d+)",
                  rc)
    rcs = m.groups()
    led_md5 = _grab(rc, r"ledger_md5=([0-9a-f]{32})", "账本 md5").group(1)
    led_lines = _grab(rc, r"ledger_lines=(\d+)", "账本行数").group(1)

    reg = ""
    regp = os.path.join(EV, "reg_24487.txt")
    if os.path.isfile(regp):
        reg = _read(regp)

    L = []
    A = L.append
    A("# 交接 —— 244.87「c_max 的口径稳健性」")
    A("")
    A("> ⚖⚖⚖ **这一轮做完了什么**：244.86 给的 **c_max = %+.2f pp** 是**一个数**；"
      "本轮把它变成**一个区**。" % float(K["C_MAIN_PP"]))
    A("")
    A("## 【1】结论（**形态 %s**）" % verdict)
    A("")
    A("· **9 个扫描口径**（Wilson {90,95,99} × 基准变体 {main, zero_as_half, zero_as_zero}）"
      "的 c_max ∈ **[%+.2f, %+.2f] pp** ⇒ ⇒ **全部**小于 Δ_obs（轨迹级）**%+.2f pp**"
      % (float(K["C_MIN_PP"]), float(K["C_MAX_PP"]), float(K["DELTA_OBS_PP"])))
    A("· **最紧组合** (Wilson95, main)：c_max = **%+.4f pp** < Δ_obs = **%+.2f pp**"
      % (float(K["C_MAIN_PP"]), float(K["DELTA_OBS_PP"])))
    A("· **真实差区间**（主口径）：不假定方向 [%+.2f, %+.2f] pp ｜ 假定污染抬高 "
      "[%+.2f, %+.2f] pp ⇒ ⇒ 与 244.86 账本印的**逐位相同**"
      % (float(K["IV_NO_LO_PP"]), float(K["IV_NO_HI_PP"]),
         float(K["IV_UP_LO_PP"]), float(K["IV_UP_HI_PP"])))
    A("· **互证独立重算的形态**：**%s**" % cr_verdict)
    A("")
    A("⚖⚖⚖ **措辞纪律**：只说「**污染上界对口径稳健**」＋「c_max ∈ [%+.2f, %+.2f] pp」"
      "⇒ ⇒ ⛔ **不许**写成「污染不存在」（那是**未量到**，不是「无污染」）。"
      % (float(K["C_MIN_PP"]), float(K["C_MAX_PP"])))
    A("")
    A("## 【2】证据链")
    A("")
    A("· 自检（Phase-0 G0-1..G0-7）**%s** 条 ｜ FAIL **%s**" % (st_n, st_fail))
    A("· 变异台 **%s / %s**（无效 %s、崩 %s）" % (mut_caught, mut_total, mut_invalid, mut_crash))
    A("· 互证 **%s / %s**（Fraction ＋ Decimal(60 位) ＋ NormalDist 路线）" % (cr_ok, cr_bad))
    A("· 预登记 ↔ 实现对账 **%s / %s**" % (sp_ok, sp_bad))
    A("· 验证链五个 rc：**%s**" % "/".join(rcs))
    if reg:
        A("· 全回归 R8：%s" % " ｜ ".join(
            l.strip() for l in reg.split("\n")
            if l.startswith(("n_exec_py=", "manifest_diff_rc=", "REG_RC="))))
    A("")
    A("## 【3】本轮抓到 **11 条**真缺陷（⛔ 一个数都没动）")
    A("")
    A("1. **预登记层**：§5 的 G0-1 写「**五个**形态」而 §3.1 只定义四个 ⇒ ⇒ 从 244.86 抄过来的笔误。")
    A("2. **预登记层**：§3.1 尾注把「可达性」闸门指向 **G0-2**（实际是 G0-1）⇒ ⇒ 指针差一位。")
    A("3. ⚠⚠ **预登记层**：§3.1 的四态**字面上不穷尽** ⇒ ⇒ **预登记追加 §0.5 更正 ②**"
      "（落态 = 唯一级联：硬失败 H1/H2/H6/H7/H8 ⇒ C；H5 红 ⇒ D；H3/H4 红 ⇒ B；其余 ⇒ A）。")
    A("4. **实现层**：H8 用了「可被替换的量」去比「账本印的值」⇒ ⇒ 形态被误判成 C（应是 D）。")
    A("5. **实现层**：预登记明写的两条没兑现（H6 漏 I6；H7 漏「行号落在段内」）⇒ ⇒ 补齐。")
    A("6. **实现层**：量纲护栏两条分支不可区分 ⇒ ⇒ 删一条察觉不到 ⇒ ⇒ 给分支代号。")
    A("7. **实现层**：G0-7 只做正控 ⇒ ⇒ 「改成恒真」抓不到 ⇒ ⇒ 抽成共用函数 ＋ 加负控。")
    A("8. **实现层**：两处会骗人的记账缺陷（`GATE_IDS` 一次性生成器、`AUDIT_KEYS` 的 `IV_*` 取错行）。")
    A("9. **互证层**：踩了 244.86 第 4 条缺陷的**同类坑**（分布串按逗号切）＋ 锚点不唯一 ＋ 全角括号 ＋ "
      "`Fraction × Decimal` ⇒ ⇒ 四条都崩 ⇒ ⇒ 逐条修好。")
    A("10. **对账层**：Q4 比错了对象（比「该臂的基准」而不是「零格 base 参数」）。")
    A("11. ⚠⚖⚖ **执行集覆盖的一个洞**：R4–R7 的树里**漏了两个已入库的执行集成员**"
      "（`fixed_dose_strata.py` / `mut_fixed_dose_strata.py`）⇒ ⇒ 「全回归全绿」在这两个文件上"
      "**从未成立过** ⇒ ⇒ 本轮补进 R8 的树 ⇒ ⇒ **R8 首次覆盖它们**。")
    A("")
    A("## 【4】⛔ 仍然留白（不许被读成什么）")
    A("")
    A("· **「污染不存在」仍未量到**（本轮只说「**上界**对口径稳健」）。")
    A("· **污染的精确幅度仍未量到**（给的是**上界族**，不是一个点估计）。")
    A("· **「连承认聚类的块级口径也解释不了」未量到** ⇒ ⇒ 本轮**只**把块级 Δ_obs 拿来做交叉核对。")
    A("· **换随机种子后的分布仍未量到** ⇒ ⇒ r 那一侧仍是 **N=1**。")
    A("· **「污染最多能翻多少格」的精确值仍未量到**（要剂量曲线 ⇒ ⇒ 跑批 ⇒ ⇒ 要点头）。")
    A("· **机制轴、剂量轴** ⇒ ⇒ 沿用旧留白，**未量到**。")
    A("· **预登记层与账本层没有自检**（244.86 的留白，**本轮仍然成立**）⇒ ⇒ 「预登记**整体**先于结果」"
      "**不成立**；准确的说法是「§0、§2、§2.1、§3.1、§3.2、§4、§5 **全部**先于结果」。")
    A("· ⚖ **自检层的固有上限**：**改「闸门自己的比较表达式」**没有闸门能抓 ⇒ ⇒ 本轮把它**缩小**了"
      "（正控＋负控共用同一个函数），⛔ 但**不可能消灭** ⇒ ⇒ 记为留白。")
    A("")
    A("## 【5】▶️ 下一轮（244.88）**怎么接着做**")
    A("")
    A("1. **预登记先行**：把「污染上界 vs **块级** Δ_obs」写成一份**新的**口径预登记"
      "（⛔ 本轮**没有**偷跑这一条：块级 Δ_obs 只进了 H8 的交叉核对，**没有**进判决）。")
    A("2. 预登记签发 ⇒ ⇒ 实现 ⇒ ⇒ Phase-0/变异台/互证/对账 ⇒ ⇒ 落账 ⇒ ⇒ R9 ⇒ ⇒ 提交。")
    A("3. ⚖ **要点头的线**（本轮**一件都没碰**）：固定剂量批重跑加 `--dump-raw`（⇒ 60 点曲线 ⇒ ⇒ "
      "「污染最多能翻多少格」）、多随机种子对照臂（r 侧 N=1 ⇒ N=K）、同结论对照臂（机制轴）、"
      "分层剂量真阶梯（剂量轴）。")
    A("")
    A("## 【6】⚖ 执行集纪律（**下一轮必读**）")
    A("")
    A("· R7/R8 的执行集 = `.cache/r244/` 下**不以 `_` 开头**的 `.py`（**递归**，含子目录）。")
    A("· ⛔ **全回归跑着的时候，不许往 `.cache/r244/` 放非 `_` 开头的 `.py`** ⇒ ⇒ 半成品会让全回归崩。")
    A("· 本轮新增的执行集成员：`cmax_robustness_audit.py` ＋ `mut_cmax_robustness_audit.py`"
      "（两者**都在** `.cache/r244/` ⇒ ⇒ 进执行集 ⇒ ⇒ R8 跑过）。")
    A("· ⚠ **R8 的清单 diff 是 added=4 / removed=0**：2 个是本轮的 ＋ 2 个是**补进来的旧成员**"
      "（`fixed_dose_strata.py` / `mut_fixed_dose_strata.py`）⇒ ⇒ **下一轮的 R9 期望是 added=2 / removed=0**"
      "（除非又有新成员）。")
    A("· ⚠⚠⚖ **一条本轮真踩到的操作坑（务必记住）**：**取消本地的 ssh 任务 ≠ 杀掉远端进程** "
      "⇒ ⇒ 本轮取消过一次 R8 ⇒ ⇒ 远端的 harness **还在跑** ⇒ ⇒ 于是**两个 harness 同写一份收据** "
      "⇒ ⇒ 收据被**交错污染** ⇒ ⇒ 那份收据**作废**、必须重跑 "
      "⇒ ⇒ **正确做法**：跑之前先 `ps -eo cmd | grep \"[s]24480r/.cache/r244/\"` 确认**没有残留**；"
      "要停就**按 PID 精确 kill**（含它刚拉起的孤儿台架），⛔ 别只 kill 本地任务句柄。")
    A("· ⚠⚖ **跑全回归要用 `setsid nohup ... &` 让它独立进程组**（⛔ 别挂在 ssh 会话上）"
      "⇒ ⇒ 否则会话一断，harness 就被 SIGTERM ⇒ ⇒ 收据里会留一条 `REG_RC=143` ⇒ ⇒ 本轮踩过一次。"
      "⇒ ⇒ 跑完**必须**验：`REG_RC=0` ＋ 收据里**零** `[BAD]` ＋ 条目数与执行集规模对得上。")
    A("· ⚠ **zju-12 的 `/home/zhourui/steer3d` 不是这棵 R 系列树**（它自己的 HEAD 是另一个项目）"
      "⇒ ⇒ `.cache/` 是手工同步的 ⇒ ⇒ 同步清单要**逐条**核对 md5。")
    A("· ⚠⚠⚖ **本轮查实**：`zju-53` 与 `zju-12` 是**两台共享同一份 NFS 家目录**的机器"
      "（`R6_RERUN_PREREG.md` 在两台上的 **inode 相同**）⇒ ⇒ 「**两台远端逐位一致**」是"
      "**必然**的，⛔ **不是**独立证据 ⇒ ⇒ 以后**不许**拿它当成交叉验证 ⇒ ⇒ 真正的独立证据是"
      "「**收据里的 md5 == 本地现算的 md5**」。")
    A("")
    A("## 【7】本轮的字节")
    A("")
    A("· 账本：%s 行 ｜ md5 `%s`" % (led_lines, led_md5))
    A("· 收据：`.cache/r244/_e24487/`（selftest/de/mut/cross/spec 的 .out ＋ receipt.txt ＋ reg_24487.txt）")
    A("· 预登记：`.cache/xcheck/R6_CMAX_ROBUSTNESS_PREREG.md`（§0.5 两条更正 ＋ §0.7 一条签发前修订）")
    A("")
    A("⚖⚖⚖ **本交接文件不入库**（按惯例）⇒ ⇒ ⛔ 别把它加进提交。")
    A("")

    with io.open(OUT, "w", encoding="utf-8", newline="") as fh:
        fh.write("\n".join(L) + "\n")
    print("✅ 已写：%s（%d 字节）" % (OUT, os.path.getsize(OUT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
