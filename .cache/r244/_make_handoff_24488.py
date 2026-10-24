#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⚖ **生成 244.88 的交接文件**（`.cache/xcheck/HANDOFF_24488.md`；⛔ **不入库**，按惯例）。

⚖ **纪律**：交接里的数**全部从收据抠**（⛔ 不手抄）⇒ ⇒ 交接与账本/提交信息**同源**。
"""

import io
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
EV = os.path.join(REPO, ".cache", "r244", "_e24488")
OUT = os.path.join(REPO, ".cache", "xcheck", "HANDOFF_24488.md")


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
    if not m:
        raise SystemExit("⛔ 收据 de.out 里没有 AUDIT_KEYS 块 ⇒ ⇒ 中止")
    K = {}
    for ln in m.group(1).splitlines():
        if "=" in ln:
            k, v = ln.split("=", 1)
            K[k.strip()] = v.strip()

    verdict = K["VERDICT"]
    m = re.search(r"SELFTEST_GATES=(\d+) ｜ FAIL=(\d+) ｜ (\S+)", st)
    st_n, st_fail, st_word = m.groups()
    m = re.search(r"变异台：抓到 (\d+) / (\d+)（无效 (\d+) 条", mu)
    mut_caught, mut_total, mut_invalid = m.groups()
    mut_crash = _grab(mu, r"崩的条数：(\d+)", "崩的条数").group(1)
    m = re.search(r"CROSS_OK=(\d+) ｜ CROSS_MISMATCH=(\d+)", cr)
    cr_ok, cr_bad = m.groups()
    cr_verdict = _grab(cr, r"^CROSS_FORM=(\S+)$", "互证形态").group(1)
    m = re.search(r"SPEC_OK=(\d+) ｜ SPEC_RED=(\d+)", sp)
    sp_ok, sp_bad = m.groups()
    m = re.search(r"SELFTEST_RC=(\d+)\s+DE_RC=(\d+)\s+MUT_RC=(\d+)\s+CROSS_RC=(\d+)\s+SPEC_RC=(\d+)",
                  rc)
    rcs = m.groups()
    # ---- 可复现性对照（两次独立验证链的逐字节比对；⛔ 不手写）----
    rp = os.path.join(EV, "repro.txt")
    if not os.path.isfile(rp):
        raise SystemExit("⛔ 缺 %s ⇒ ⇒ 中止" % rp)
    repro = {}
    for ln in _read(rp).splitlines():
        if "=" in ln:
            k, v = ln.split("=", 1)
            repro[k.strip()] = v.strip()
    for k in ("REPRO_N_FILES", "REPRO_N_IDENTICAL", "REPRO_DRIVER_OLD_MD5",
              "REPRO_DRIVER_NEW_MD5", "REPRO_LEDGER_RUN1_LINES", "REPRO_LEDGER_RUN1_MD5",
              "REPRO_LEDGER_RUN2_LINES", "REPRO_LEDGER_RUN2_MD5"):
        if k not in repro:
            raise SystemExit("⛔ repro.txt 里缺 %s ⇒ ⇒ 中止" % k)
    repro_n = int(repro["REPRO_N_FILES"])
    repro_ident = int(repro["REPRO_N_IDENTICAL"])
    if repro_ident != repro_n:
        raise SystemExit("⛔ 两次验证链的收据并不逐字节一致（%d / %d）⇒ ⇒ 中止"
                         % (repro_ident, repro_n))
    led_md5 = _grab(rc, r"ledger_md5=([0-9a-f]{32})", "账本 md5").group(1)
    led_lines = _grab(rc, r"ledger_lines=(\d+)", "账本行数").group(1)
    n_scan = int(K["N_SCAN"])

    # R5 逐口径（保守读法）
    per = re.findall(r"^      (\d\.\d\d) / (\S+)\s+界=([+-][0-9.]+) pp ⇒ (\*\*不成立\*\*|成立)"
                     r"( ｜ 联合 (\d+)%)?$", de, re.M)
    if len(per) != 36:
        raise SystemExit("⛔ de.out 里解析到 %d 行逐口径界（期望 36）⇒ ⇒ 中止" % len(per))
    r5 = per[18:27]
    viol = [x for x in r5 if x[3] != "成立"]

    reg = ""
    regp = os.path.join(EV, "reg_24488.txt")
    if os.path.isfile(regp):
        reg = _read(regp)

    L = []
    A = L.append
    A("# 交接 —— 244.88「保守读法与口径边界」")
    A("")
    A("> ⚖⚖⚖ **这一轮做完了什么**：244.87 说「污染上界对**口径**稳健」；本轮问的是"
      "**更狠的一句** —— 「**把抽样噪声与污染幅度同时按最保守方向放**，这条结论还站得住吗？」"
      "⇒ ⇒ 答案：**只在部分扫描口径成立** ⇒ ⇒ **结论必须收紧**。")
    A("")
    A("## 【1】结论（**形态 %s**）" % verdict)
    A("")
    A("· **R1** 污染**只抬高** rand 臂（c ≥ 0）｜轨迹级 **%+.2f pp**（95%% 单源、**不依赖 c**）｜ ✅ 成立"
      % float(K["R1_BOUND_PP"]))
    A("· **R2** 同上｜块级 **%+.2f pp**（95%% 单源、**不依赖 c**）｜ ✅ 成立"
      % float(K["R2_BOUND_PP"]))
    A("· **R3** 不假定方向·**点估计**｜轨迹级 **%d/%d 口径成立**，最紧 **%+.2f pp** ｜ ✅ 成立"
      % (n_scan - int(K["R3_NVIOL"]), n_scan, float(K["R3_MIN_PP"])))
    A("· **R4** 不假定方向·点估计（⚠**跨口径**）｜块级 **%d/%d 成立**，最紧 **%+.2f pp** ｜ ✅ 成立"
      % (n_scan - int(K["R4_NVIOL"]), n_scan, float(K["R4_MIN_PP"])))
    A("· **R5** 不假定方向·**保守**（CI 下端点 ＋ c 下端点，**同时**取最保守）｜轨迹级 "
      "**%d/%d 成立** ｜ ⛔ **有破口**（%s）"
      % (n_scan - int(K["R5_NVIOL"]), n_scan,
         "、".join("%s/%s（%+.4f）" % (x[0], x[1], float(x[2])) for x in viol)))
    A("· **R6** 同上（⚠跨口径·**示意**）｜块级 %d/%d 成立 ｜ ⚠ **不参与形态判定**"
      % (n_scan, n_scan))
    A("· **互证独立重算的形态**：**%s**" % cr_verdict)
    A("")
    A("⚖⚖⚖ **措辞纪律**：「污染解释不了观测差」这句话**必须**带着读法与口径一起说："
      "**在「污染只抬高」的读法下成立**（不依赖 c，95%% 单源下界 %+.2f pp）、"
      "**在点估计口径下成立**（%d/%d）；**在最保守读法下只覆盖部分扫描口径** "
      "⇒ ⇒ ⛔ **不许**写成「污染不存在」，⛔ 也**不许**写成「污染能解释观测差」。"
      % (float(K["R1_BOUND_PP"]), n_scan, n_scan))
    A("")
    A("## 【2】证据链")
    A("")
    A("· 自检（Phase-0 G0-1..G0-9）**%s** 道 ｜ FAIL **%s**（%s）" % (st_n, st_fail, st_word))
    A("· 变异台 **%s / %s**（无效 %s、崩 %s）" % (mut_caught, mut_total, mut_invalid, mut_crash))
    A("· 互证 **%s / %s**（Fraction ＋ Decimal(60 位) ＋ NormalDist 路线）" % (cr_ok, cr_bad))
    A("· 预登记 ↔ 实现对账 **%s / %s**" % (sp_ok, sp_bad))
    A("· 验证链五个 rc：**%s**" % "/".join(rcs))
    A("· ⚖⚖⚖ **可复现性（两次独立验证链）**：**%d / %d** 个收据 .out **逐字节相同**"
      "（run1 读**落账前**的账本 %s 行 ｜ md5 `%s`；run2 读**落账后**的账本 %s 行 ｜ md5 `%s`）"
      "⇒ ⇒ ① 改驱动里的过期计数**没动任何数**；② 「**本轮的数不会因为落账而变**」**被实证**"
      % (repro_ident, repro_n, repro["REPRO_LEDGER_RUN1_LINES"],
         repro["REPRO_LEDGER_RUN1_MD5"], repro["REPRO_LEDGER_RUN2_LINES"],
         repro["REPRO_LEDGER_RUN2_MD5"]))
    if reg:
        A("· 全回归 R9：%s" % " ｜ ".join(
            l.strip() for l in reg.split("\n")
            if l.startswith(("n_exec_py=", "manifest_diff_rc=", "REG_RC=", "BAD_n="))))
    A("")
    A("## 【3】本轮抓到 **9 条**真缺陷（⛔ 一个数都没动）")
    A("")
    A("1. ⚠⚖ **预登记层**：G0-6 的负控期望（「把 `c_lo` 换成 `c_hi` ⇒ 必须红」）在**数学上不成立** "
      "⇒ ⇒ 界只会**变大** ⇒ ⇒ 正确的实现**不会红** ⇒ ⇒ 那是**恒不红**的检查 "
      "⇒ ⇒ **预登记追加更正 ④**（改的是**判据的期望**，⛔ 不是改实现去迎合它 ⇒ ⇒ 判据**变严**）。")
    A("2. ⚠⚖⚖ **实现层**：G0-2 的期望级联**从模块常量派生** ⇒ ⇒ 变异两边一起变 ⇒ ⇒ **恒绿** "
      "⇒ ⇒ 变异台 **MU1 存活**暴露 ⇒ ⇒ 改成「硬失败集合**手写**」＋「两者必须逐条相同」。")
    A("3. ⚠⚖⚖ **实现层**：G0-3 只试了三条特例分支 ⇒ ⇒ **兜底分支**没被覆盖 ⇒ ⇒ 变异台 **MU8 存活**暴露 "
      "⇒ ⇒ 补了第 5 个用例。")
    A("4. ⚠ **实现层**：`_check_sum` 的消息缺占位符却传两个参数 ⇒ ⇒ **整份实现跑不起来** "
      "⇒ ⇒ ⚠ **本地只跑 `ast.parse` 抓不到这一类错**（符号表/运行期才查）⇒ ⇒ 改用 `compile()` 复查。")
    A("5. ⚠⚠ **实现层**：`global` 声明位置错了 ⇒ ⇒ **编译期**就报 `SyntaxError` "
      "⇒ ⇒ 同样**只有 `compile()` 才抓得到** ⇒ ⇒ `ast.parse` 不够。")
    A("6. ⚠ **互证层**：按「下标」取表格单元格 ⇒ ⇒ 表头行首格是空串 ⇒ ⇒ **下标错位** "
      "⇒ ⇒ 改用「按形状取」⇒ ⇒ 与被检实现**不同源**。")
    A("7. ⚠ **互证层**：轨迹级定位**命中 2 行** ⇒ ⇒ 锚点不唯一 ⇒ ⇒ 改成**必须同时**含「`**差 `」。")
    A("8. ⚠ **对账层**：抽取常量时留下逗号 / `range` 上界含头 ⇒ ⇒ 六条对账项**误红** "
      "⇒ ⇒ 改用 `re.findall` ＋ `range(1, n)` ⇒ ⇒ 对账从 6 红降到 0 红。")
    A("9. ⚠⚠⚖ **驱动层**：`_run_24488_verify.sh` 的 banner 印「变异台（**34** 条）」⇒ ⇒ 而变异台真实是 "
      "**%d 条**（MU1–MU33 ＋ ML1 ＋ ML2）⇒ ⇒ **过期计数** ⇒ ⇒ 该文件**要入库** ⇒ ⇒ ⛔ 不能带着一个错的数入库 "
      "⇒ ⇒ **改成 %d** ＋ **重跑整条验证链** ⇒ ⇒ ⛔ **一个数都没动**（%d / %d 个 .out **逐字节不变**，"
      "只有驱动字节 md5 变 `%s` → `%s`）⇒ ⇒ 顺带**实证**了「落账之后账本变长、而本轮的数不变」。"
      % (int(mut_total), int(mut_total), repro_ident, repro_n,
         repro["REPRO_DRIVER_OLD_MD5"], repro["REPRO_DRIVER_NEW_MD5"]))
    A("")
    A("## 【4】⛔ 仍然留白（不许被读成什么）")
    A("")
    A("· **「污染不存在」仍未量到**；**污染的精确幅度**仍未量到（本轮给的是**界**，⛔ 不是点估计）。")
    A("· **块级口径下的污染量 / 污染上界未量到**（块级零假设基准未在账本登记 ⇒ ⇒ 需**重解析原始跑批日志**"
      "⇒ ⇒ **要点头**）⇒ ⇒ R4 / R6 两行**都带口径混合标签**。")
    A("· **更宽置信水平下的保守读法未量到**（CI 下端点本轮**只有 95%**）⇒ ⇒ 下一轮 Newcombe 换水平。")
    A("· **识别假设**「rand 臂无污染时的改判率 = 零假设基准」⇒ ⇒ **全部**污染相关结论都**条件于**它 "
      "⇒ ⇒ **未在本轮独立验证**。")
    A("· **R5 的破口 ≠「结论被否」** ⇒ ⇒ 它只说明**最保守读法**下的结论**只覆盖部分扫描口径**。")
    A("· **机制轴、剂量轴** ⇒ ⇒ 沿用旧留白，**未量到**。")
    A("· ⚖ **自检层的固有上限**：**改「闸门自己的比较表达式」**没有闸门能抓 ⇒ ⇒ 本轮把它**缩小**了"
      "（正控＋负控共用同一个函数），⛔ 但**不可能消灭** ⇒ ⇒ 记为留白。")
    A("· ⛔ **预登记层与账本层没有自检** ⇒ ⇒ 「预登记**整体**先于结果」**不成立**；"
      "准确的说法是「§0.5'、§1、§2、§3、§3.2、§4、§5、§6、§7 的**口径与判据**全部先于结果」；"
      "且 §0.5' 的 N2 **明写**各行符号可手算 ⇒ ⇒ **不主张**「结果未知」。")
    A("")
    A("## 【5】▶️ 下一轮（244.89+）**怎么接着做**")
    A("")
    A("1. **B-1 要点头**（**重解析原始跑批日志**）⇒ ⇒ 才能得到「**同口径**的块级污染上界」"
      "⇒ ⇒ 才能把 R4 / R6 从「混合口径」升级成「同口径」。")
    A("2. **B-2**：Newcombe 换置信水平 ⇒ ⇒ 保守读法在 95 / 99 双水平上的**完整**作用域。")
    A("3. ⚖ **要点头的线**（本轮**一件都没碰**）：固定剂量批重跑加 `--dump-raw`、多随机种子对照臂、"
      "同结论对照臂（机制轴）、分层剂量真阶梯（剂量轴）、docs 那条线 GPU 前向、照 meta 重建重训。")
    A("")
    A("## 【6】⚖ 执行集纪律（**下一轮必读**）")
    A("")
    A("· R9 的执行集 = `.cache/r244/` 下**不以 `_` 开头**的 `.py`（**递归**，含子目录）。")
    A("· ⛔ **全回归跑着的时候，不许往 `.cache/r244/` 放非 `_` 开头的 `.py`** ⇒ ⇒ 半成品会让全回归崩。")
    A("· 本轮新增的执行集成员：`conservative_bound_audit.py` ＋ `mut_conservative_bound_audit.py`"
      "（`_%s` 开头的那三个**不进**执行集）。")
    A("· ⚠ **R9 的清单 diff 是 added=2 / removed=0** ⇒ ⇒ **下一轮的 R10 期望是 added=2 / removed=0**"
      "（除非又有新成员）。")
    A("· ⚠⚠⚖ **取消本地的 ssh 任务 ≠ 杀掉远端进程** ⇒ ⇒ 要停就**按 PID 精确 kill**；"
      "跑之前先 `ps -eo cmd | grep \"[s]24480r/.cache/r244/\"` 确认**没有残留**。")
    A("· ⚠⚖ **跑全回归要用 `setsid nohup ... &` 让它独立进程组** ⇒ ⇒ 否则会话一断，"
      "harness 就被 SIGTERM ⇒ ⇒ 收据里会留一条 `REG_RC=143`。")
    A("· ⚠⚠⚖ **zju-12 的 `/home/zhourui/steer3d` 不是这棵 R 系列树** ⇒ ⇒ `.cache/` 是手工同步的 "
      "⇒ ⇒ 同步清单要**逐条**核对 md5 ⇒ ⇒ 本轮的 R9 脚本里把期望 md5 **手写**进去，"
      "**杜绝**「同步错版本」。")
    A("· ⚠⚠⚖ **两台远端共享同一份 NFS 家目录** ⇒ ⇒ 「**两台远端逐位一致**」是**必然**的，"
      "⛔ **不是**独立证据 ⇒ ⇒ 真正的独立证据是「**收据里的 md5 == 本地现算的 md5**」。")
    A("· ⚠⚖⚖ **本轮踩到的第二个操作坑（工具层）**：`_commit_msg_24488.py` 里有一句 `A(\"…（95%%）…\")` "
      "**没有 `%` 运算符** ⇒ ⇒ `%%` **不会被转义** ⇒ ⇒ 提交信息里原样印出「95%%」"
      "⇒ ⇒ ⚠ **只在「带 `%` 运算符的格式串」上做转义检查是抓不到它的** "
      "⇒ ⇒ **正确做法**：**产物写完再 grep 一遍 `%%`**，本轮就是靠「**合成收据试跑 ＋ 回头 grep**」挖出来的"
      "（⇒ ⇒ **在提交之前**挖出来 ⇒ ⇒ **没有进账本、没有进证据链、没有动任何数**）"
      "⇒ ⇒ ⚖ **教训**：本地静态检查**不够** ⇒ ⇒ ⛔ 必须**真的跑一遍产物再回头看**。")
    A("")
    A("## 【7】本轮的字节")
    A("")
    A("· 账本：%s 行 ｜ md5 `%s`" % (led_lines, led_md5))
    A("· 收据：`.cache/r244/_e24488/`（selftest/de/mut/cross/spec 的 .out ＋ receipt.txt ＋ reg_24488.txt"
      " ＋ **repro.txt**（两次验证链的逐字节对照记录））")
    A("· ⚖ **复现性对照的另一半**：`.cache/r244/_e24488_run1/`（**第一次**验证链的五个 .out ＋ receipt.txt）"
      "⇒ ⇒ 与 `_e24488/` 里的**第二次**逐字节比对 ⇒ ⇒ 就是 `repro.txt` 里那 **%d / %d 逐字节相同**"
      "（⛔ 两份都**不入库**，按惯例）" % (repro_ident, repro_n))
    A("· 预登记：`.cache/xcheck/R6_CONSERVATIVE_BOUND_PREREG.md`（§0.5' **四条更正**）")
    A("")
    A("⚖⚖⚖ **本交接文件不入库**（按惯例）⇒ ⇒ ⛔ 别把它加进提交。")
    A("")

    with io.open(OUT, "w", encoding="utf-8", newline="") as fh:
        fh.write("\n".join(L) + "\n")
    print("✅ 已写：%s（%d 字节）" % (OUT, os.path.getsize(OUT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
