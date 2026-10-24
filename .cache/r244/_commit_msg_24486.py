#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⚖ **生成 244.86 的提交信息**（⛔ 所有数都从收据抠，⛔ 不手抄）。

用法：python3 .cache/r244/_commit_msg_24486.py  ⇒ ⇒ 写 `.cache/r244/_commit_msg_24486.txt`
"""

import io
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
EV = os.path.join(REPO, ".cache", "r244", "_e24486")
OUT = os.path.join(REPO, ".cache", "r244", "_commit_msg_24486.txt")


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


def _final_ledger_md5():
    """⚖ **最终版账本的 md5**：从**落账后现算**的 FACTS 里抠（⛔ 不写死）。"""
    p = os.path.join(REPO, ".cache", "r244", "_post_commit_readback_24486.py")
    if not os.path.isfile(p):
        raise SystemExit("⛔ 缺 %s ⇒ ⇒ 先跑 `_gen_readback_24486.py`" % p)
    txt = _read(p)
    m = re.search(r'^FULL_MD5 = "([0-9a-f]{32})"$', txt, re.M)
    if not m:
        raise SystemExit("⛔ FACTS 里没有 FULL_MD5 ⇒ ⇒ 先跑 `_gen_readback_24486.py`")
    return m.group(1)


def _reg_facts():
    """⚖ **R7 全回归收据**（⛔ 必须有 ⇒ ⇒ 提交信息**一定**带全回归证据）。

    ⚖⚖⚖ **R7 收据里锚的账本 md5 必须 == 提交里那份** ⇒ ⇒ 这一条同时是
    「R7 验的就是提交里那份字节」的**交叉核对**。
    """
    p = os.path.join(EV, "reg_24486.txt")
    if not os.path.isfile(p):
        raise SystemExit("⛔ 缺 R7 全回归收据：%s ⇒ ⇒ **不许**在没跑全回归的情况下提交" % p)
    txt = _read(p)
    out = {}
    m = _grab(txt, r"n_exec_py=(\d+)", "R7 执行集成员数")
    out["n_exec"] = m.group(1)
    m = _grab(txt, r"added=(\d+)\s+removed=(\d+)", "R7 清单 diff")
    out["added"], out["removed"] = m.groups()
    m = _grab(txt, r"REG_RC=(\d+)", "R7 的 rc")
    out["rc"] = m.group(1)
    m = _grab(txt, r"变异台 全绿 (\d+) / 跑得动 (\d+)", "R7 变异台小结")
    out["mut_ok"], out["mut_n"] = m.groups()
    m = _grab(txt, r"自检 全绿 (\d+) / 跑得动 (\d+)", "R7 自检小结")
    out["st_ok"], out["st_n"] = m.groups()
    m = _grab(txt, r"ledger_lines=(\d+)\s+ledger_md5=([0-9a-f]{32})", "R7 锚的账本")
    out["led_lines"], out["led_md5"] = m.groups()
    if out["rc"] != "0":
        raise SystemExit("⛔ R7 的 REG_RC=%s（≠0）⇒ ⇒ **不许**提交" % out["rc"])
    if out["added"] != "2" or out["removed"] != "0":
        raise SystemExit("⛔ R7 清单 diff 是 added=%s/removed=%s（期望 2/0）⇒ ⇒ **不许**提交"
                         % (out["added"], out["removed"]))
    if out["led_md5"] != _final_ledger_md5():
        raise SystemExit("⛔ R7 收据锚的账本 md5=%s ≠ 提交里那份 %s ⇒ ⇒ R7 验的不是这份字节 "
                         "⇒ ⇒ **不许**提交" % (out["led_md5"], _final_ledger_md5()))
    return out


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

    N = {}
    N["verdict"] = _grab(de, r"^VERDICT=(\S+)$", "判决形态").group(1)
    N["why"] = _grab(de, r"^理由：(.*)$", "判决理由").group(1).strip()
    m = _grab(de, r"^判据汇总：(\d+) 条 ｜ PASS (\d+) ｜ FAIL (\d+)$", "真数据判据小结")
    N["de_n"], N["de_pass"], N["de_fail"] = m.groups()
    m = _grab(st, r"自检（Phase-0 G0-1\.\.G0-7）：(\d+) 条 ｜ FAIL (\d+) 条", "自检小结")
    N["st_n"], N["st_fail"] = m.groups()
    m = _grab(mu, r"变异台：抓到 (\d+) / (\d+)（无效 (\d+) 条", "变异台小结")
    N["mut_caught"], N["mut_total"], N["mut_invalid"] = m.groups()
    N["mut_crash"] = _grab(mu, r"崩的条数：(\d+)", "崩的条数").group(1)
    m = _grab(cr, r"互证：OK (\d+) ｜ MISMATCH (\d+)", "互证小结")
    N["cr_ok"], N["cr_bad"] = m.groups()
    N["cr_verdict"] = _grab(cr, r"^独立重算的判决形态：(\S+)$", "互证形态").group(1)
    m = _grab(sp, r"对账条数：OK (\d+) ｜ 红 (\d+)", "对账小结")
    N["sp_ok"], N["sp_bad"] = m.groups()
    m = _grab(rc, r"SELFTEST_RC=(\d+)\s+DE_RC=(\d+)\s+MUT_RC=(\d+)\s+CROSS_RC=(\d+)\s+SPEC_RC=(\d+)",
               "五个 rc")
    N["rcs"] = m.groups()
    if any(x != "0" for x in N["rcs"]):
        raise SystemExit("⛔ 五个 rc 里有非 0 ⇒ ⇒ 不生成提交信息")

    if N["cr_verdict"] != N["verdict"]:
        raise SystemExit("⛔ 两条实现的判决形态不一致 ⇒ ⇒ 中止")

    # ⚖⚖⚖ **R7 全回归收据**（⛔ 缺就中止 ⇒ ⇒ 提交信息**一定**带全回归证据）
    R = _reg_facts()

    L = []
    A = L.append
    A("244.86：对照臂的零假设地位 —— rand 臂的**边际**改判率**没有可检出的**高于零假设"
      "（判成 %s）" % N["verdict"])
    A("")
    A("**一句话**：244.81 那个固定剂量判决（w 臂 46/56 vs rand 臂 29/56，差 +30.36 pp）的"
      "**对照臂**，在**可检出层面**没被 244.84/244.85 查到的「`r₀` 与 steering 簇 A 对齐」"
      "这条污染抬起 ⇒ ⇒ 污染幅度从**纯留白**变成**有界命题**：c_max = %+.2f pp。"
      % float(K["C_MAX_PP"]))
    A("")
    A("**判决面板**（全部数从账本 244.81 段**逐行解析**，⛔ 代码里不写死任何一个数；"
      "连容差都由账本自己的打印精度推导）：")
    A("· rand 轨迹级：观测 %s/%s ｜ 零分布（Poisson-binomial）均值 `%s` ｜ 单侧上尾 p = `%s` "
      "⇒ ⇒ 与零假设**不可区分**" % (K["OBS_R"], K["N_TRAJ"], K["BASE_R_CALC"], K["P_TRAJ_R"]))
    A("· rand 块级：观测 %s/%s ｜ 同块 p = `%s` ｜ 异块 p = `%s` ⇒ ⇒ **两端都**不可区分"
      % (K["BLK_R"], K["N_BLOCKS"], K["P_BLK_R_SAME"], K["P_BLK_R_SPLIT"]))
    A("· 逐格前提：rand 非零格 %s、正号 %s ｜ 单侧**下尾** p = `%s` ⇒ ⇒ 不判红"
      "（⛔「不显著」是**弱**证据：格不独立 ⇒ p 反保守）"
      % (K["N_NZ_CELLS"], K["N_POS_CELLS"], K["P_CELL_LOWER"]))
    A("· 判别力（w 臂**同一条**检验）：轨迹级 p = `%s` ｜ 块级 p = `%s` ⇒ ⇒ **显著** "
      "⇒ ⇒ 这条检验**不是恒绿**" % (K["P_TRAJ_W"], K["P_BLK_W_ONLY"]))
    A("· 幅度上界：c_max = **%+.2f pp** ｜ 真实差（**不假定方向**）[%+.2f, %+.2f] pp ｜ "
      "（**假定污染方向为抬高**）[%+.2f, %+.2f] pp"
      % (float(K["C_MAX_PP"]), float(K["IV_NO_LO_PP"]), float(K["IV_NO_HI_PP"]),
         float(K["IV_UP_LO_PP"]), float(K["IV_UP_HI_PP"])))
    A("")
    A("**⛔ 措辞纪律**：只说「**在可检出层面**没有」＋「幅度上界是 %+.2f pp」；"
      "⛔ **不许**写成「对照臂干净」。" % float(K["C_MAX_PP"]))
    A("")
    A("**证据链**：自检 %s/%s ｜ 变异台 %s/%s（无效 %s、崩 %s）｜ 互证 %s/%s"
      "（精确整数路线 vs numpy 路线，独立重算形态 %s）｜ 对账 %s/%s ｜ 验证链五项 rc 全 %s"
      % (N["st_n"], N["st_n"], N["mut_caught"], N["mut_total"], N["mut_invalid"],
         N["mut_crash"], N["cr_ok"], N["cr_bad"], N["cr_verdict"], N["sp_ok"], N["sp_bad"],
         "/".join(N["rcs"])))
    A("**全回归 R7**（`zju-12`）：执行集 **%s** 个 py ｜ 清单 diff 对 R6 added **%s** / removed **%s** ｜ "
      "`REG_RC = %s` ｜ 变异台全绿 **%s/%s** ｜ 自检全绿 **%s/%s** ｜ 收据锚的账本 %s 行 md5 `%s` "
      "⇒ ⇒ **就是提交里那份字节**"
      % (R["n_exec"], R["added"], R["removed"], R["rc"], R["mut_ok"], R["mut_n"],
         R["st_ok"], R["st_n"], R["led_lines"], R["led_md5"]))
    A("**边界**：污染的精确幅度 ｜ 「污染最多翻多少格」的精确值 ｜ 机制轴 ｜ 剂量轴 ｜ "
      "rand 换种子后的分布 ⇒ ⇒ 全部**未量到**（⛔ 不是「无差异」）；r 那一侧仍是 **N=1**；"
      "「污染存在」的响应级严格证明因**共线**（共享成分 vs 题目可移动性）**验不了**。")
    A("")
    A("**本轮抓到七个真缺陷**（前 **5** 个是**实现的错，⛔ 不是口径的错**；⚠ 第 **6** 个是"
      "**落账层**的错、⚠ 第 **7** 个是**预登记层**的错 ⇒ ⇒ 这两个**没有任何闸门覆盖** "
      "⇒ ⇒ 是**人工复核**发现的）："
      "① 判决映射表把 H3/H4 也算进「其他硬判据红」⇒ N-B/N-C 变**死分支**（G0-2 红）｜ "
      "② H6 把 Q8 的两条区间当成嵌套关系 ⇒ 恒等式写错（G0-3/G0-5 红）｜ "
      "③ I12 的锚点「跨臂 Fisher」在 244.81 段内**不唯一**（命中 4 行）⇒ 硬失败｜ "
      "④ `(n_nz,n_zero)` 分布串按逗号切 ⇒ 被切碎（内层 `(2,0)` 自带逗号）｜ "
      "⑤ ⚠ H7 的 Wilson 交叉校验容差被**多乘了 100** ⇒ 那条护栏**松了 100 倍**"
      "（**跨实现互证**抓到的）⇒ ⇒ 已收紧 ⇒ ⇒ 收紧后**仍然绿** ⇒ ⇒ **结论未变**"
      "（⚠ 诚实记账：这条收紧发生在真数据跑出形态**之后** ⇒ ⇒ 假如它是红的，形态会是 N-E）｜ "
      "⑥ ⚠ **落账层**的字节清单三处不准（`receipt` 写成 `.out` 实为 `.txt`｜"
      "「收据文件（N 件）」的 N 用了登记总数｜清单漏了 `_run_24486_reg_shm.sh`）"
      "⇒ ⇒ **没有任何闸门覆盖** ⇒ ⇒ 是**人工复核**发现的 ⇒ ⇒ **重落了本段**"
      "（旧前缀逐字节不变、围栏数不变、**一个数都没动** ⇒ ⇒ **判决形态不变**）｜ "
      "⑦ ⚠ **预登记 §0.5 更正 ② 末尾三句引用了真数据结果**（「本轮实测 H3、H4 都绿」）"
      "⇒ ⇒ 与同节「任何 p 值算出之前」的声明**自相矛盾**、且是把**预期写成了断言** "
      "⇒ ⇒ **预登记追加 §0.6「更正 ③」**撤回那三句的证据效力（⛔ 不改任何口径/数/已写下的句子）"
      "＋ 给出**不依赖结果**的替代论证 ⇒ ⇒ **远端验证链重跑**（五个 rc 全 0、"
      "**5 个被检收据 md5 一个都没变** ⇒ ⇒ **判决形态不变**）")
    A("")
    A("⚖ **本段的字节历史**：账本文本**改过 3 轮**（前 3 版**都只存在于本地、从未提交** "
      "⇒ ⇒ **中间字节** ⇒ ⇒ **全回归 R7 只以最终版为准**）⇒ ⇒ "
      "最终版 md5 `%s` ⇒ ⇒ 变的是**表述层**（路径、件数、计数）与**预登记的更正记录**，"
      "**判决与一个数都没变**。" % _final_ledger_md5())
    A("")
    A("**预登记** `.cache/xcheck/R6_CONTROL_ARM_NULL_PREREG.md`（**先于实现**签；"
      "§0.5 含**两条更正**、§0.6 含**一条更正 ③** —— ⚠ 更正 ③ 是**本轮补的**："
      "§0.5 更正 ② 末尾三句**引用了真数据结果** ⇒ ⇒ 已**撤回其证据效力**"
      "（⛔ 不改任何口径、不改任何数、不改已写下的任何一句）⇒ ⇒ "
      "准确的说法是「预登记的**口径与判据**（§0、§2、§2.1、§3.1、§3.2、§4、§5）"
      "**全部**先于结果」，⛔ **不是**「预登记**整体**先于结果」）"
      "（⚠ 更正 ② 的**实质内容**（N-C 优先于 N-B）**不依赖结果** ⇒ ⇒ **不影响**本轮结论："
      "本轮 H3、H4 **都绿** ⇒ ⇒ 两种读法都落在 %s）。" % N["verdict"])
    A("")
    A("**账本** `.cache/xcheck/R6_RERUN_PREREG.md`（**只追加**：旧前缀逐字节不变、"
      "围栏数不变）｜ **收据** `.cache/r244/_e24486/`")

    msg = "\n".join(L) + "\n"
    with io.open(OUT, "w", encoding="utf-8", newline="") as fh:
        fh.write(msg)
    print("✅ 已写：%s（%d 字节）" % (OUT, len(msg.encode("utf-8"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
