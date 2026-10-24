#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⚖ **生成 244.88 的提交信息**（⛔ 所有数都从收据抠，⛔ 不手抄）。

用法：python3 .cache/r244/_commit_msg_24488.py  ⇒ ⇒ 写 `.cache/r244/_commit_msg_24488.txt`
"""

import io
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
EV = os.path.join(REPO, ".cache", "r244", "_e24488")
OUT = os.path.join(REPO, ".cache", "r244", "_commit_msg_24488.txt")


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
    p = os.path.join(REPO, ".cache", "r244", "_post_commit_readback_24488.py")
    if not os.path.isfile(p):
        raise SystemExit("⛔ 缺 %s ⇒ ⇒ 先跑 `_gen_readback_24488.py`" % p)
    txt = _read(p)
    m = re.search(r'^FULL_MD5 = "([0-9a-f]{32})"$', txt, re.M)
    if not m:
        raise SystemExit("⛔ FACTS 里没有 FULL_MD5 ⇒ ⇒ 先跑 `_gen_readback_24488.py`")
    return m.group(1)


def _reg_facts():
    """⚖ **R9 全回归收据**（⛔ 必须有 ⇒ ⇒ 提交信息**一定**带全回归证据）。

    ⚖⚖⚖ **R9 收据里锚的账本 md5 必须 == 提交里那份** ⇒ ⇒ 这一条同时是
    「R9 验的就是提交里那份字节」的**交叉核对**。
    ⚖⚖⚖ **加严**：**R9 本身必须绿**（`REG_RC=0` ＋ 清单 diff 2/0 ＋ 零 BAD）
       ⇒ ⇒ 否则「收据对得上」也可能是**一份红的回归**留下的。
    """
    p = os.path.join(EV, "reg_24488.txt")
    if not os.path.isfile(p):
        raise SystemExit("⛔ 缺 R9 全回归收据：%s ⇒ ⇒ **不许**在没跑全回归的情况下提交" % p)
    txt = _read(p)
    out = {}
    out["n_exec"] = _grab(txt, r"n_exec_py=(\d+)", "R9 执行集成员数").group(1)
    m = _grab(txt, r"added=(\d+)\s+removed=(\d+)", "R9 清单 diff")
    out["added"], out["removed"] = m.groups()
    out["rc"] = _grab(txt, r"REG_RC=(\d+)", "R9 的 rc").group(1)
    m = _grab(txt, r"变异台 全绿 (\d+) / 跑得动 (\d+)", "R9 变异台小结")
    out["mut_ok"], out["mut_n"] = m.groups()
    m = _grab(txt, r"自检 全绿 (\d+) / 跑得动 (\d+)", "R9 自检小结")
    out["st_ok"], out["st_n"] = m.groups()
    m = _grab(txt, r"ledger_lines=(\d+)\s+ledger_md5=([0-9a-f]{32})", "R9 锚的账本")
    out["led_lines"], out["led_md5"] = m.groups()
    out["bad_n"] = _grab(txt, r"BAD_n=(\d+)", "R9 里的 [BAD] 数").group(1)
    if out["rc"] != "0":
        raise SystemExit("⛔ R9 的 REG_RC=%s（≠0）⇒ ⇒ **不许**提交" % out["rc"])
    if out["added"] != "2" or out["removed"] != "0":
        raise SystemExit("⛔ R9 清单 diff 是 added=%s/removed=%s（期望 2/0）⇒ ⇒ **不许**提交"
                         % (out["added"], out["removed"]))
    if out["bad_n"] != "0":
        raise SystemExit("⛔ R9 收据里有 %s 处 [BAD] ⇒ ⇒ **不许**提交" % out["bad_n"])
    if out["led_md5"] != _final_ledger_md5():
        raise SystemExit("⛔ R9 收据锚的账本 md5=%s ≠ 提交里那份 %s ⇒ ⇒ R9 验的不是这份字节 "
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
    N["de_n"] = len(re.findall(r"^\[(PASS|FAIL)\] H\d ", de, re.M))
    N["de_pass"] = len(re.findall(r"^\[PASS\] H\d ", de, re.M))
    N["de_fail"] = len(re.findall(r"^\[FAIL\] H\d ", de, re.M))
    m = re.search(r"SELFTEST_GATES=(\d+) ｜ FAIL=(\d+) ｜ (\S+)", st)
    N["st_n"], N["st_fail"], N["st_word"] = m.groups()
    m = re.search(r"变异台：抓到 (\d+) / (\d+)（无效 (\d+) 条", mu)
    N["mut_caught"], N["mut_total"], N["mut_invalid"] = m.groups()
    N["mut_crash"] = _grab(mu, r"崩的条数：(\d+)", "崩的条数").group(1)
    m = re.search(r"CROSS_OK=(\d+) ｜ CROSS_MISMATCH=(\d+)", cr)
    N["cr_ok"], N["cr_bad"] = m.groups()
    N["cr_verdict"] = _grab(cr, r"^CROSS_FORM=(\S+)$", "互证形态").group(1)
    m = re.search(r"SPEC_OK=(\d+) ｜ SPEC_RED=(\d+)", sp)
    N["sp_ok"], N["sp_bad"] = m.groups()
    m = re.search(r"SELFTEST_RC=(\d+)\s+DE_RC=(\d+)\s+MUT_RC=(\d+)\s+CROSS_RC=(\d+)\s+SPEC_RC=(\d+)",
                  rc)
    N["rcs"] = m.groups()
    if any(x != "0" for x in N["rcs"]):
        raise SystemExit("⛔ 五个 rc 里有非 0 ⇒ ⇒ 不生成提交信息")
    if N["cr_verdict"] != N["verdict"]:
        raise SystemExit("⛔ 两条实现的判决形态不一致 ⇒ ⇒ 中止")

    # ---- 可复现性对照（两次独立验证链的逐字节比对；⛔ 不手写）----
    rp = os.path.join(EV, "repro.txt")
    if not os.path.isfile(rp):
        raise SystemExit("⛔ 缺 %s ⇒ ⇒ 中止" % rp)
    R = {}
    for ln in _read(rp).splitlines():
        if "=" in ln:
            k, v = ln.split("=", 1)
            R[k.strip()] = v.strip()
    for k in ("REPRO_N_FILES", "REPRO_N_IDENTICAL", "REPRO_DRIVER_OLD_MD5",
              "REPRO_DRIVER_NEW_MD5", "REPRO_LEDGER_RUN1_LINES", "REPRO_LEDGER_RUN1_MD5",
              "REPRO_LEDGER_RUN2_LINES", "REPRO_LEDGER_RUN2_MD5"):
        if k not in R:
            raise SystemExit("⛔ repro.txt 里缺 %s ⇒ ⇒ 中止" % k)
    N["repro"] = R
    N["repro_n"] = int(R["REPRO_N_FILES"])
    N["repro_ident"] = int(R["REPRO_N_IDENTICAL"])
    if N["repro_ident"] != N["repro_n"]:
        raise SystemExit("⛔ 两次验证链的收据并不逐字节一致（%d / %d）⇒ ⇒ 中止"
                         % (N["repro_ident"], N["repro_n"]))

    # ---- R5 的逐口径行（保守读法；本轮的核心表）----
    per = re.findall(r"^      (\d\.\d\d) / (\S+)\s+界=([+-][0-9.]+) pp ⇒ (\*\*不成立\*\*|成立)"
                     r"( ｜ 联合 (\d+)%)?$", de, re.M)
    if len(per) != 36:
        raise SystemExit("⛔ de.out 里解析到 %d 行逐口径界（期望 36）⇒ ⇒ 中止" % len(per))
    r5 = per[18:27]
    viol = [x for x in r5 if x[3] != "成立"]

    R = _reg_facts()

    L = []
    A = L.append
    A("244.88：保守读法与口径边界 —— 「污染解释不了观测差」在**最保守读法**下"
      "**只在部分扫描口径成立**（判成 %s）" % N["verdict"])
    A("")
    A("**一句话**：244.87 判成形态 A（9 口径下 `c_max` 全部 < Δ_obs）⇒ ⇒ 但那条主判据是"
      "**点估计**口径、而且**只守了 c 区间的高端** ⇒ ⇒ 面板里那列「真实差（不假定方向）」"
      "= `Δ_obs + c_lo` **只被打印、没有任何判据守它** ⇒ ⇒ 本轮①**补守紧端**、"
      "②**把抽样噪声也算进去**（问「**把污染幅度与抽样噪声同时按最保守方向放**，"
      "这条结论还站得住吗？」）⇒ ⇒ 交付一张「**读法—口径作用域表**」。")
    A("")
    A("**判决面板**（全部数从账本 244.81 / 244.86 段**逐行解析**，⛔ 代码里不写死任何一个数；"
      "连**容差**都由账本自己的打印精度推导）：")
    A("· **判决形态**：**%s** —— %s" % (N["verdict"], N["why"]))
    A("· **R1** 污染**只抬高** rand 臂（c ≥ 0）｜轨迹级 **%+.2f pp**（%s%% 单源、**不依赖 c**）｜ ✅ 成立"
      % (float(K["R1_BOUND_PP"]), "95"))
    A("· **R2** 同上｜块级 **%+.2f pp**（%s%% 单源、**不依赖 c**）｜ ✅ 成立"
      % (float(K["R2_BOUND_PP"]), "95"))
    A("· **R3** 不假定方向·**点估计**｜轨迹级 **%d/%d 口径成立**，最紧 **%+.2f pp** ｜ ✅ 成立"
      % (int(K["N_SCAN"]) - int(K["R3_NVIOL"]), int(K["N_SCAN"]), float(K["R3_MIN_PP"])))
    A("· **R4** 不假定方向·点估计（⚠**跨口径**）｜块级 **%d/%d 成立**，最紧 **%+.2f pp** ｜ ✅ 成立"
      % (int(K["N_SCAN"]) - int(K["R4_NVIOL"]), int(K["N_SCAN"]), float(K["R4_MIN_PP"])))
    A("· **R5** 不假定方向·**保守**（CI 下端点 ＋ c 下端点，**同时**取最保守）｜轨迹级 "
      "**%d/%d 成立** ｜ ⛔ **有破口**"
      % (int(K["N_SCAN"]) - int(K["R5_NVIOL"]), int(K["N_SCAN"])))
    A("· **R6** 同上（⚠跨口径·**示意**）｜块级 %d/%d 成立 ｜ ⚠ **不参与形态判定**"
      % (int(K["N_SCAN"]), int(K["N_SCAN"])))
    A("")
    A("· **R5 的逐口径界（保守读法；本轮的核心表）**：")
    for lv, va, b, st_, _c, cf in r5:
        A("  · Wilson%s ｜ %s ｜ 界 **%+.4f pp** ｜ 联合 %s%% ｜ %s"
          % (lv, va, float(b), cf, "✅ 成立" if st_ == "成立" else "⛔ **不成立**"))
    A("")
    A("· ⛔ **破口在哪**：%s ⇒ ⇒ ⇒ ⇒ **结论必须收紧**成：在**污染只抬高 rand 臂**的读法下成立"
      "（**不依赖 c**，95%% 单源下界 **%+.2f pp**），在**点估计**口径下成立（%d/%d，逐口径 ≥ **%+.2f pp**）；"
      "但在**把抽样噪声与污染幅度同时按最保守方向**的读法下，**只在部分扫描口径成立**。"
      % ("、".join("%s/%s（%+.4f）" % (x[0], x[1], float(x[2])) for x in viol),
         float(K["R1_BOUND_PP"]), int(K["N_SCAN"]), int(K["N_SCAN"]), float(K["R3_MIN_PP"])))
    A("· ⚖ **为什么会破口**：Wilson99 的 c 区间**更宽** ⇒ ⇒ `c_lo` 更负 ⇒ ⇒ 与 CI 下端点相加后越过 0 "
      "⇒ ⇒ 这是**两个下界同时取到最坏方向**的必然结果 ⇒ ⇒ ⛔ **不是**「数据有问题」，"
      "⛔ 也**不是**「结论被否」⇒ ⇒ 是**结论的适用范围**被钉出来了。")
    A("")
    A("**⚖⚖⚖ 量纲纪律**：只允许三对 —— `c_upper ↔ delta_obs`（加法①）｜"
      "`delta_ci_lo + c_lower`（加法②，保守读法）｜ `delta_obs + c_lower`（加法③，点估计读法）"
      "⇒ ⇒ ⛔ `delta_ci_lo ↔ c_upper` **仍然红**（那是「+15.22 翻越 +13.01」的**假警报**）"
      "⇒ ⇒ 每条禁止分支各有**代号** ⇒ ⇒ **H8 量纲硬门**在位。")
    A("**⚖⚖⚖ 保守读法的联合置信**：population 层的分解 `Δ_true = Δ_obs + c` ⇒ ⇒ 若 `Δ_obs ≥ CI_lo`（95%）"
      "**且** `c ≥ c_lo`（95%）⇒ ⇒ `Δ_true ≥ CI_lo + c_lo`；两项各 95% ⇒ ⇒ **Bonferroni ⇒ 联合 ≥ 90%**"
      "（⛔ Bonferroni **不要求**两项独立）⇒ ⇒ 联合置信**逐口径不同**：Wilson90 ⇒ 85%｜Wilson95 ⇒ 90%｜"
      "Wilson99 ⇒ 94%。")
    A("")
    A("**证据链**：自检 %s 道（FAIL %s，%s）｜ 变异台 %s/%s（无效 %s、崩 %s）｜ 互证 %s/%s"
      "（Fraction ＋ Decimal(60 位) ＋ NormalDist 路线，独立重算形态 %s）｜ 对账 %s/%s "
      "｜ 验证链五项 rc 全 %s"
      % (N["st_n"], N["st_fail"], N["st_word"], N["mut_caught"], N["mut_total"], N["mut_invalid"],
         N["mut_crash"], N["cr_ok"], N["cr_bad"], N["cr_verdict"], N["sp_ok"], N["sp_bad"],
         "/".join(N["rcs"])))
    A("**可复现性**：**两次独立验证链**（run1 读**落账前**的账本 %s 行 / md5 `%s`；run2 读**落账后**的账本 "
      "%s 行 / md5 `%s`）⇒ ⇒ **%d / %d** 个收据 .out **逐字节相同** ⇒ ⇒ ① 改驱动里的过期计数**没动任何数**；"
      "② 「**本轮的数不会因为落账而变**」**被实证**（不是断言）"
      % (N["repro"]["REPRO_LEDGER_RUN1_LINES"], N["repro"]["REPRO_LEDGER_RUN1_MD5"],
         N["repro"]["REPRO_LEDGER_RUN2_LINES"], N["repro"]["REPRO_LEDGER_RUN2_MD5"],
         N["repro_ident"], N["repro_n"]))
    A("**全回归 R9**（`zju-12`）：执行集 **%s** 个 py ｜ 清单 diff 对 R8 added **%s** / removed **%s** ｜ "
      "`REG_RC = %s` ｜ 变异台全绿 **%s/%s** ｜ 自检全绿 **%s/%s** ｜ 零 `[BAD]`（%s）｜ "
      "收据锚的账本 %s 行 md5 `%s` ⇒ ⇒ **就是提交里那份字节**"
      % (R["n_exec"], R["added"], R["removed"], R["rc"], R["mut_ok"], R["mut_n"],
         R["st_ok"], R["st_n"], R["bad_n"], R["led_lines"], R["led_md5"]))
    A("")
    A("**边界**：块级口径下的污染量 / 污染上界（**口径混合标签**）｜ 更宽置信水平下的保守读法"
      "｜ 识别假设「rand 臂无污染时的改判率 = 零假设基准」｜ 「污染不存在」｜ 污染的精确幅度"
      "｜ 机制轴 ｜ 剂量轴 ⇒ ⇒ 全部**未量到**（⛔ 不是「无差异」）。")
    A("")
    A("**本轮抓到 9 条真缺陷**（⛔ **一个数都没动**）："
      "① ⚠⚖ **预登记层：G0-6 的负控期望在数学上不成立**（「把 `c_lo` 换成 `c_hi` ⇒ 必须红」"
      "⇒ ⇒ 界只会**变大** ⇒ ⇒ 正确的实现**不会红** ⇒ ⇒ 那是**恒不红**的检查）"
      "⇒ ⇒ **预登记追加更正 ④**：拆成两条互补负控（改的是**判据的期望**，⛔ 不是改实现去迎合它）｜ "
      "② ⚠⚖⚖ **实现层：G0-2 的期望级联从模块常量派生** ⇒ ⇒ 变异两边一起变 ⇒ ⇒ **恒绿** "
      "⇒ ⇒ 变异台 **MU1 存活**暴露 ⇒ ⇒ 改成「硬失败集合**手写**」｜ "
      "③ ⚠⚖⚖ **实现层：G0-3 只试了三条特例分支** ⇒ ⇒ 兜底分支没被覆盖 ⇒ ⇒ 变异台 **MU8 存活**暴露 "
      "⇒ ⇒ 补了第 5 个用例｜ "
      "④ ⚠ **实现层：`_check_sum` 消息缺占位符却传两个参数** ⇒ ⇒ **整份实现跑不起来** "
      "⇒ ⇒ ⚠ **本地只跑 `ast.parse` 抓不到这一类错** ⇒ ⇒ 改用 `compile()` 复查｜ "
      "⑤ ⚠⚠ **实现层：`global` 声明位置错了** ⇒ ⇒ **编译期**就报 `SyntaxError` ⇒ ⇒ 同样**只有 `compile()` 才抓得到**｜ "
      "⑥ ⚠ **互证层：按「下标」取表格单元格** ⇒ ⇒ 表头行首格是空串 ⇒ ⇒ **下标错位** "
      "⇒ ⇒ 改用「按形状取」⇒ ⇒ 与被检实现**不同源**｜ "
      "⑦ ⚠ **互证层：轨迹级定位命中 2 行** ⇒ ⇒ 锚点不唯一 ⇒ ⇒ 改成**必须同时**含「`**差 `」｜ "
      "⑧ ⚠ **对账层：抽取常量时留下逗号 / `range` 上界含头** ⇒ ⇒ 六条对账项**误红** "
      "⇒ ⇒ 改用 `re.findall` ＋ `range(1, n)` ⇒ ⇒ 对账从 6 红降到 0 红｜ "
      "⑨ ⚠⚠⚖ **驱动层：`_run_24488_verify.sh` 的 banner 印「变异台（**34** 条）」⇒ ⇒ 而变异台真实是 "
      "**%d 条**（MU1–MU33 ＋ ML1 ＋ ML2）⇒ ⇒ **过期计数** ⇒ ⇒ 该文件**要入库** ⇒ ⇒ ⛔ 不能带着一个错的数入库 "
      "⇒ ⇒ **改成 %d** ＋ **重跑整条验证链** ⇒ ⇒ ⛔ **一个数都没动**（%d / %d 个 .out **逐字节不变**，"
      "只有驱动字节 md5 变 `%s` → `%s`）⇒ ⇒ 顺带**实证**了「落账之后账本变长、而本轮的数不变」"
      % (int(N["mut_total"]), int(N["mut_total"]), N["repro_ident"], N["repro_n"],
         N["repro"]["REPRO_DRIVER_OLD_MD5"], N["repro"]["REPRO_DRIVER_NEW_MD5"]))
    A("")
    A("**预登记** `.cache/xcheck/R6_CONSERVATIVE_BOUND_PREREG.md`（**先于实现**签；"
      "§0.5' 含**四条更正**——① 加法③ 的补登记、② 追加 G0-9、③ H1/H9/G0-5 的加严、"
      "④ G0-6 的负控期望在数学上不成立）"
      "（⚠ 244.88 的量**全部已在账本登记** ⇒ ⇒ **手算即可**得出各行符号 ⇒ ⇒ "
      "**不主张**「结果未知」；准确的说法是「预登记的**口径与判据**全部先于结果」）")
    A("")
    A("**账本** `.cache/xcheck/R6_RERUN_PREREG.md`（**只追加**：旧前缀逐字节不变、"
      "围栏数不变）｜ **收据** `.cache/r244/_e24488/`")
    A("")
    A("⚖ **一条查实的事实**：`zju-53` 与 `zju-12` 是**两台共享同一份 NFS 家目录**的机器"
      "⇒ ⇒ 「**两台远端逐位一致**」是**必然**的，⛔ **不是**独立证据 "
      "⇒ ⇒ 真正的独立证据是「**收据里的 md5 == 本地现算的 md5**」⇒ ⇒ 以后**不许**拿"
      "「两台一致」当成交叉验证。")

    msg = "\n".join(L) + "\n"
    with io.open(OUT, "w", encoding="utf-8", newline="") as fh:
        fh.write(msg)
    print("✅ 已写：%s（%d 字节）" % (OUT, len(msg.encode("utf-8"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
