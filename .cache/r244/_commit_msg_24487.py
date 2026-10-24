#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⚖ **生成 244.87 的提交信息**（⛔ 所有数都从收据抠，⛔ 不手抄）。

用法：python3 .cache/r244/_commit_msg_24487.py  ⇒ ⇒ 写 `.cache/r244/_commit_msg_24487.txt`
"""

import io
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
EV = os.path.join(REPO, ".cache", "r244", "_e24487")
OUT = os.path.join(REPO, ".cache", "r244", "_commit_msg_24487.txt")


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
    p = os.path.join(REPO, ".cache", "r244", "_post_commit_readback_24487.py")
    if not os.path.isfile(p):
        raise SystemExit("⛔ 缺 %s ⇒ ⇒ 先跑 `_gen_readback_24487.py`" % p)
    txt = _read(p)
    m = re.search(r'^FULL_MD5 = "([0-9a-f]{32})"$', txt, re.M)
    if not m:
        raise SystemExit("⛔ FACTS 里没有 FULL_MD5 ⇒ ⇒ 先跑 `_gen_readback_24487.py`")
    return m.group(1)


def _reg_facts():
    """⚖ **R8 全回归收据**（⛔ 必须有 ⇒ ⇒ 提交信息**一定**带全回归证据）。

    ⚖⚖⚖ **R8 收据里锚的账本 md5 必须 == 提交里那份** ⇒ ⇒ 这一条同时是
    「R8 验的就是提交里那份字节」的**交叉核对**。
    ⚖⚖⚖ **加严**（244.86 的教训）：**R8 本身必须绿**（`REG_RC=0` ＋ 清单 diff 4/0）
       ⇒ ⇒ 否则「收据对得上」也可能是**一份红的回归**留下的。
    """
    p = os.path.join(EV, "reg_24487.txt")
    if not os.path.isfile(p):
        raise SystemExit("⛔ 缺 R8 全回归收据：%s ⇒ ⇒ **不许**在没跑全回归的情况下提交" % p)
    txt = _read(p)
    out = {}
    out["n_exec"] = _grab(txt, r"n_exec_py=(\d+)", "R8 执行集成员数").group(1)
    m = _grab(txt, r"added=(\d+)\s+removed=(\d+)", "R8 清单 diff")
    out["added"], out["removed"] = m.groups()
    out["rc"] = _grab(txt, r"REG_RC=(\d+)", "R8 的 rc").group(1)
    m = _grab(txt, r"变异台 全绿 (\d+) / 跑得动 (\d+)", "R8 变异台小结")
    out["mut_ok"], out["mut_n"] = m.groups()
    m = _grab(txt, r"自检 全绿 (\d+) / 跑得动 (\d+)", "R8 自检小结")
    out["st_ok"], out["st_n"] = m.groups()
    m = _grab(txt, r"ledger_lines=(\d+)\s+ledger_md5=([0-9a-f]{32})", "R8 锚的账本")
    out["led_lines"], out["led_md5"] = m.groups()
    if out["rc"] != "0":
        raise SystemExit("⛔ R8 的 REG_RC=%s（≠0）⇒ ⇒ **不许**提交" % out["rc"])
    if out["added"] != "4" or out["removed"] != "0":
        raise SystemExit("⛔ R8 清单 diff 是 added=%s/removed=%s（期望 4/0）⇒ ⇒ **不许**提交"
                         % (out["added"], out["removed"]))
    if out["led_md5"] != _final_ledger_md5():
        raise SystemExit("⛔ R8 收据锚的账本 md5=%s ≠ 提交里那份 %s ⇒ ⇒ R8 验的不是这份字节 "
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
    m = re.search(r"^判据汇总：(\d+) 条 ｜ PASS (\d+) ｜ FAIL (\d+)$", de, re.M)
    N["de_n"] = len(re.findall(r"^\[(PASS|FAIL)\] H\d ", de, re.M))
    N["de_pass"] = len(re.findall(r"^\[PASS\] H\d ", de, re.M))
    N["de_fail"] = len(re.findall(r"^\[FAIL\] H\d ", de, re.M))
    m = re.search(r"自检（Phase-0 G0-1\.\.G0-7）：(\d+) 条 ｜ FAIL (\d+) 条", st)
    N["st_n"], N["st_fail"] = m.groups()
    m = re.search(r"变异台：抓到 (\d+) / (\d+)（无效 (\d+) 条", mu)
    N["mut_caught"], N["mut_total"], N["mut_invalid"] = m.groups()
    N["mut_crash"] = _grab(mu, r"崩的条数：(\d+)", "崩的条数").group(1)
    m = re.search(r"互证：OK (\d+) ｜ MISMATCH (\d+)", cr)
    N["cr_ok"], N["cr_bad"] = m.groups()
    N["cr_verdict"] = _grab(cr, r"^独立重算的判决形态：(\S+)$", "互证形态").group(1)
    m = re.search(r"对账条数：OK (\d+) ｜ 红 (\d+)", sp)
    N["sp_ok"], N["sp_bad"] = m.groups()
    m = re.search(r"SELFTEST_RC=(\d+)\s+DE_RC=(\d+)\s+MUT_RC=(\d+)\s+CROSS_RC=(\d+)\s+SPEC_RC=(\d+)",
                  rc)
    N["rcs"] = m.groups()
    if any(x != "0" for x in N["rcs"]):
        raise SystemExit("⛔ 五个 rc 里有非 0 ⇒ ⇒ 不生成提交信息")
    if N["cr_verdict"] != N["verdict"]:
        raise SystemExit("⛔ 两条实现的判决形态不一致 ⇒ ⇒ 中止")

    R = _reg_facts()

    L = []
    A = L.append
    A("244.87：c_max 的口径稳健性 —— 污染上界对**口径**稳健：c_max 从「一个数」升级成"
      "「**一个区**」（判成 %s）" % N["verdict"])
    A("")
    A("**一句话**：244.86 给的 **c_max = %+.2f pp**（污染最多能把 rand 臂抬高多少）是**一个数**、"
      "不是**一个区** ⇒ ⇒ 它由「rand 改判率的 Wilson **上界**」减「零假设基准」得到 ⇒ ⇒ "
      "**两个输入的口径都会动它** ⇒ ⇒ 本轮把 3 档 Wilson 置信水平 × 3 种基准变体**全部**扫了一遍 "
      "⇒ ⇒ **9 个口径下 c_max ∈ [%+.2f, %+.2f] pp，全部小于 Δ_obs = %+.2f pp** ⇒ ⇒ "
      "「**污染解释不了观测差**」这条结论**对口径稳健**。"
      % (float(K["C_MAIN_PP"]), float(K["C_MIN_PP"]), float(K["C_MAX_PP"]),
         float(K["DELTA_OBS_PP"])))
    A("")
    A("**判决面板**（全部数从账本 244.81 段**逐行解析**，⛔ 代码里不写死任何一个数；"
      "连**容差**都由账本自己的打印精度推导）：")
    A("· **判决形态**：**%s** —— %s" % (N["verdict"], N["why"]))
    A("· **9 个口径的 c_max**（pp）：")
    _lbl = {"MAIN": "主口径", "ZERO_AS_HALF": "零格 base=0.5", "ZERO_AS_ZERO": "零格 base=0"}
    for lv in ("90", "95", "99"):
        row = " ｜ ".join("%s %+.2f" % (_lbl[v], float(K["CMAX_%s_%s" % (lv, v)]))
                          for v in ("MAIN", "ZERO_AS_HALF", "ZERO_AS_ZERO"))
        A("  · Wilson%s：%s" % (lv, row))
    A("· **最紧组合**：(Wilson95, 主基准) c_max = **%+.4f pp** < Δ_obs = **%+.2f pp** "
      "⇒ ⇒ 「污染最多抬这么多，而观测差至少这么多」⇒ ⇒ 污染**解释不了**观测差"
      % (float(K["C_MAIN_PP"]), float(K["DELTA_OBS_PP"])))
    A("· **真实差区间**（Q7：两条都算，⛔ 不许只印对自己有利的那条）"
      "—— 主口径 (Wilson95, main)：**不假定方向** [%+.2f, %+.2f] pp ｜ "
      "**假定污染抬高** [%+.2f, %+.2f] pp（⇒ ⇒ 与 244.86 账本印的**逐位相同**）"
      % (float(K["IV_NO_LO_PP"]), float(K["IV_NO_HI_PP"]),
         float(K["IV_UP_LO_PP"]), float(K["IV_UP_HI_PP"])))
    A("· **Δ_obs 的两个口径**：轨迹级 **%+.2f pp**（本轮用它比，因为它是**最紧**的那个）｜ "
      "块级 **%+.2f pp**（⛔ 本轮**只**拿它做交叉核对，⛔ **不**用它下判决 ⇒ ⇒ "
      "「连承认聚类的块级口径也解释不了」**未量到** ⇒ ⇒ 是**下一轮**的活）"
      % (float(K["DELTA_OBS_PP"]), float(K["DELTA_OBS_BLK_PP"])))
    A("")
    A("**⚖⚖⚖ 量纲陷阱**：Newcombe95 的下端点（%+.2f pp）与块级 bootstrap 的下端点**都是"
      "「w − rand 的差」的区间下端点** ⇒ ⇒ **不是** Δ_obs ⇒ ⇒ ⛔ **不能**拿它们去比 c_max "
      "⇒ ⇒ 否则会得出「假警报」⇒ ⇒ 本轮把它做成 **H5 硬门**（**kind 标签**机制："
      "比较前必须核对两个量的 `kind`）" % float(K["IV_NO_LO_PP"]))
    A("")
    A("**证据链**：自检 %s/%s（FAIL %s）｜ 变异台 %s/%s（无效 %s、崩 %s）｜ 互证 %s/%s"
      "（Fraction ＋ Decimal(60 位) ＋ NormalDist 路线，独立重算形态 %s）｜ 对账 %s/%s "
      "｜ 验证链五项 rc 全 %s"
      % (N["st_n"], N["st_n"], N["st_fail"], N["mut_caught"], N["mut_total"], N["mut_invalid"],
         N["mut_crash"], N["cr_ok"], N["cr_bad"], N["cr_verdict"], N["sp_ok"], N["sp_bad"],
         "/".join(N["rcs"])))
    A("**全回归 R8**（`zju-12`）：执行集 **%s** 个 py ｜ 清单 diff 对 R7 added **%s** / removed **%s** ｜ "
      "`REG_RC = %s` ｜ 变异台全绿 **%s/%s** ｜ 自检全绿 **%s/%s** ｜ 收据锚的账本 %s 行 md5 `%s` "
      "⇒ ⇒ **就是提交里那份字节**"
      % (R["n_exec"], R["added"], R["removed"], R["rc"], R["mut_ok"], R["mut_n"],
         R["st_ok"], R["st_n"], R["led_lines"], R["led_md5"]))
    A("**边界**：污染的精确幅度 ｜ 「污染最多翻多少格」的精确值 ｜ 「连承认聚类的块级口径也解释不了」"
      "｜ 换随机种子后的分布 ｜ 机制轴 ｜ 剂量轴 ⇒ ⇒ 全部**未量到**（⛔ 不是「无差异」）；"
      "r 那一侧仍是 **N=1**；「污染存在」的响应级严格证明因**共线**（共享成分 vs 题目可移动性）"
      "**验不了**。")
    A("")
    A("**本轮抓到 11 条真缺陷**（**3 条预登记层** ＋ **5 条实现层** ＋ **2 条第二/第三条实现层** "
      "＋ **1 条执行集覆盖**；⛔ **一个数都没动**）："
      "① 预登记 §5 的 G0-1 写「**五个**形态」而 §3.1 只定义四个 ⇒ ⇒ 从 244.86 抄过来的**笔误**｜ "
      "② 预登记 §3.1 尾注把「可达性」闸门指向 **G0-2**（实际是 G0-1）⇒ ⇒ **指针差一位**｜ "
      "③ ⚠⚠ **预登记 §3.1 的四态在字面上不穷尽**（「H1/H2/H8 红且扫描无违例」⇒ ⇒ 落不进任何一态；"
      "「H1/H2/H8 红且有违例」⇒ ⇒ 会被说成「结论被否」）⇒ ⇒ **预登记追加 §0.5 更正 ②**："
      "落态写成**唯一级联**（硬失败 = H1/H2/H6/H7/H8 ⇒ C；H5 红 ⇒ D；H3/H4 红 ⇒ B；其余 ⇒ A）｜ "
      "④ **H8 用了「可被替换的量」去比「账本印的值」** ⇒ ⇒ 形态被误判成 C（应是 D）（**G0-1 抓到的**）｜ "
      "⑤ 预登记明写的两条没兑现：**H6 漏了 I6**、**H7 漏了「行号落在段内」** ⇒ ⇒ 补齐（12 项 / 6 个锚点）｜ "
      "⑥ **量纲护栏两条分支不可区分** ⇒ ⇒ 删一条另一条仍挡 ⇒ ⇒ 察觉不到 ⇒ ⇒ 给分支**代号**"
      "（**变异台 MU8 抓到的**）｜ "
      "⑦ ⚠ **G0-7 只做正控** ⇒ ⇒ 把「md5 不变」改成恒真 ⇒ ⇒ **没有任何闸门能抓** "
      "（**变异台 MU15 抓到的**）⇒ ⇒ 抽成**共用函数** ＋ 加**负控**｜ "
      "⑧ 两处**会骗人**的记账缺陷（`GATE_IDS` 是一次性生成器、`AUDIT_KEYS` 的 `IV_*` 取错行）｜ "
      "⑨ 互证脚本踩了 244.86 第 4 条缺陷的**同类坑**（分布串按逗号切 ⇒ 内层 `(2,0)` 自带逗号）"
      "＋ 锚点不唯一 ＋ 全角括号 ＋ `Fraction × Decimal` ⇒ ⇒ 四条**都崩**｜ "
      "⑩ 对账脚本的 Q4 **比错了对象**（比「该臂的基准」而不是「零格 base 参数」）｜ "
      "⑪ ⚠⚖⚖ **执行集覆盖的一个洞**：R4–R7 的树里**漏了两个已入库的执行集成员**"
      "（`fixed_dose_strata.py` / `mut_fixed_dose_strata.py`）⇒ ⇒ 「全回归全绿」在这两个文件上"
      "**从未成立过** ⇒ ⇒ 本轮补进 R8 的树 ⇒ ⇒ **R8 首次覆盖它们**（都绿）")
    A("")
    A("**预登记** `.cache/xcheck/R6_CMAX_ROBUSTNESS_PREREG.md`（**先于实现**签；"
      "§0.5 含**两条更正**——② 形态的落态级联、③ 两处笔误；§0.7 含一条**签发前**修订）"
      "（⚠ 两条更正的论证**都不引用任何实测数** ⇒ ⇒ 不破坏「先于结果」的性质；"
      "准确的说法是「预登记的**口径与判据**全部先于结果」，⛔ **不是**「预登记**整体**先于结果」）")
    A("")
    A("**账本** `.cache/xcheck/R6_RERUN_PREREG.md`（**只追加**：旧前缀逐字节不变、"
      "围栏数不变）｜ **收据** `.cache/r244/_e24487/`")
    A("")
    A("⚖ **一条查实的事实**：`zju-53` 与 `zju-12` 是**两台共享同一份 NFS 家目录**的机器"
      "（同一 inode、同一挂载点）⇒ ⇒ 「**两台远端逐位一致**」是**必然**的，⛔ **不是**独立证据 "
      "⇒ ⇒ 真正的独立证据是「**收据里的 md5 == 本地现算的 md5**」⇒ ⇒ 以后**不许**拿"
      "「两台一致」当成交叉验证。")

    msg = "\n".join(L) + "\n"
    with io.open(OUT, "w", encoding="utf-8", newline="") as fh:
        fh.write(msg)
    print("✅ 已写：%s（%d 字节）" % (OUT, len(msg.encode("utf-8"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
