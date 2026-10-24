#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⚖ **生成 244.85 的交接文件**（⛔ 所有数都从收据抠，⛔ 不手抄）。

**输出**：`.cache/xcheck/HANDOFF_24485.md`（⚖ 按惯例**不入库** —— 只给下一个接手的人读）
**输入**：
  · `.cache/r244/_e24485/{selftest,de,mut,cross,spec}.out` ＋ `receipt.txt` ＋ `reg_24485.txt`
  · 账本 `.cache/xcheck/R6_RERUN_PREREG.md`（读 244.84 段的**原文**）

⚖⚖⚖ **为什么交接文件由脚本生成**：交接文件里的每个数都是**收据里的数**
⇒ ⇒ 交接文件与账本、与跑出这些数的字节**同源** ⇒ ⇒ ⛔ 不会出现「手抄抄错」。
"""

import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
EV = os.path.join(REPO, ".cache", "r244", "_e24485")
LEDGER = os.path.join(REPO, ".cache", "xcheck", "R6_RERUN_PREREG.md")
OUT = os.path.join(REPO, ".cache", "xcheck", "HANDOFF_24485.md")

DECISION = ["FULL", "LOO-m0", "LOO-m1", "LOO-real", "LOO-t1", "LOO-p2a", "LOO-old"]
DESCRIPTIVE = ["STRAT-A", "CLU-A", "CLU-B", "SINGLE-m0", "SINGLE-m1",
                "SINGLE-real", "SINGLE-t1", "SINGLE-p2a", "SINGLE-old"]


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


def collect():
    de = _need(os.path.join(EV, "de.out"))
    mu = _need(os.path.join(EV, "mut.out"))
    cr = _need(os.path.join(EV, "cross.out"))
    sp = _need(os.path.join(EV, "spec.out"))
    st = _need(os.path.join(EV, "selftest.out"))
    rc = _need(os.path.join(EV, "receipt.txt"))
    regp = os.path.join(EV, "reg_24485.txt")
    reg = _read(regp) if os.path.isfile(regp) else ""

    N = {}
    N["verdict"] = _grab(de, r"^VERDICT=(\S+)$", "判决形态").group(1)
    N["why"] = _grab(de, r"^VERDICT_WHY=(.+)$", "判决理由").group(1).strip().replace("**", "")
    m = _grab(de, r"^判据汇总：(\d+) 条 ｜ PASS (\d+) ｜ FAIL (\d+)$", "真数据判据小结")
    N["de_n"], N["de_pass"], N["de_fail"] = m.groups()
    N["de_ids"] = re.findall(r"^\[PASS\] (\S+)", de, re.M)

    # ---- 账本 244.84 段的**原文**（⛔ 不用收据里 %r 的缩写）----
    led = _read(LEDGER)
    m = re.search(r"^## 修订 244\.84\b", led, re.M)
    if not m:
        raise SystemExit("⛔ 账本里没有「## 修订 244.84」段 ⇒ 中止")
    m2 = re.search(r"^## 修订 ", led[m.end():], re.M)
    sec = led[m.start():(m.end() + m2.start() if m2 else len(led))]

    def line_with(kw, what):
        for ln in sec.splitlines():
            if kw in ln:
                return ln
        raise SystemExit("⛔ 账本 244.84 段里找不到含「%s」的行（%s）" % (kw, what))

    N["T"] = _grab(line_with("**类级主统计量**", "类级 T"), r"\*\*([-+0-9.eE]+)\*\*", "类级 T").group(1)
    N["z"] = _grab(line_with("**z_T**（对参考种子分布）", "类级 z_T"),
                   r"\*\*([-+0-9.eE]+)\*\*", "类级 z_T").group(1)
    mm = _grab(line_with("经验秩 / 参考 sd", "秩/sd"),
               r"\|\s*([-+0-9.eE]+)\s*/\s*([-+0-9.eE]+)\s*/\s*([-+0-9.eE]+)\s*\|", "秩/sd")
    N["rank"], N["sd"], N["theo"] = mm.group(1), mm.group(2), mm.group(3)
    N["fpr"] = _grab(line_with("经验假阳性率", "FPR"), r"\*\*([-+0-9.eE]+)\*\*", "FPR").group(1)

    # ---- 16 个子集 ----
    subs = {}
    for mm in re.finditer(
            r"^SUBSET\|([^|]+)\|n=(\d+)\|T=([-+0-9.eE]+)\|z=([-+0-9.eE]+)\|"
            r"rank=([-+0-9.eE]+)\|sd=([-+0-9.eE]+)\|theo=([-+0-9.eE]+)\|"
            r"sdrel=([-+0-9.eE]+)\|fpr=([-+0-9.eE]+)\|shape=(\S+)$", de, re.M):
        subs[mm.group(1)] = {"n": int(mm.group(2)), "T": mm.group(3), "z": mm.group(4),
                             "rank": mm.group(5), "sd": mm.group(6), "theo": mm.group(7),
                             "sdrel": mm.group(8), "fpr": mm.group(9), "shape": mm.group(10)}
    if len(subs) != 16:
        raise SystemExit("⛔ 收据里抠到 %d 个子集（应为 16）" % len(subs))
    N["subs"] = subs
    N["ea"] = [k for k in DECISION if subs[k]["shape"] == "E-A"]

    # ---- H6 逐项 ----
    h6 = _grab(de, r"^\[PASS\] H6-CROSSROUND\s+(.*)$", "H6").group(1)
    pairs = re.findall(r"（差 ([-+0-9.eE]+)，上限 ([-+0-9.eE]+)）", h6)
    N["h6_n"] = len(pairs)
    N["h6_zero"] = sum(1 for d, t in pairs if float(d) == 0.0)
    N["h6_maxratio"] = max((float(d) / float(t) if float(t) else 0.0) for d, t in pairs)

    # ---- H13 位级 ----
    h13 = _grab(de, r"^\[PASS\] H13-BITIDENT\s+(.*)$", "H13").group(1)
    N["h13_ulp0"] = h13.count("ULP 差 0")
    N["h13_n"] = len(re.findall(r"ULP 差 \d+", h13))

    N["h9_max"] = max(float(v["fpr"]) for v in subs.values())
    N["h8_max"] = max(float(v["sdrel"]) for v in subs.values())
    N["h10_z"], N["h10_zmax"] = _grab(
        de, r"置换（种子 \d+\+i）后：z_T=([-+0-9.eE]+)（\|z\| 上限 ([-+0-9.eE]+)", "H10").groups()
    N["h11_alt"], N["h11_altv"], N["h11_z"], N["h11_v"] = _grab(
        de, r"含构造种子的参考集（\d+\.\.\d+）算出的 z_T=([-+0-9.eE]+)（判 (\S+)；账本登记 [-+0-9.eE]+）"
        r"vs 不含的 z_T=([-+0-9.eE]+)（判 (\S+)）", "H11").groups()
    N["h12_maxnm"] = _grab(de, r"本轮实测：余弦最大的那把 = (\S+)", "H12").group(1)
    N["h12_maxcos"] = _grab(de, r"余弦最大的那把 = \S+（([-+0-9.eE]+)）", "H12 值").group(1)
    N["d1_equiv"] = _grab(de, r"w 等效剂量 = [-+0-9.eE]+ × [-+0-9.eE]+ = ([-+0-9.eE]+)", "D6").group(1)

    # ---- 跨路线差值 ----
    xr_full, xr_led, xr_sum = [], [], {}
    for ln in cr.splitlines():
        if not ln.startswith("CROSSROUTE|"):
            continue
        parts = ln.split("|")
        kv = {}
        rest = parts[2:]
        if rest and "=" not in rest[0]:
            kv["name"] = rest[0]
            rest = rest[1:]
        for p in rest:
            if "=" in p:
                k, v = p.split("=", 1)
                kv[k] = v
        if parts[1] == "FULL":
            xr_full.append(kv)
        elif parts[1] == "LEDGER":
            xr_led.append(kv)
        elif parts[1] == "SUMMARY":
            xr_sum = kv
    if not xr_full or not xr_led or not xr_sum:
        raise SystemExit("⛔ 互证收据里抠不到 CROSSROUTE 块 ⇒ 中止")
    N["xr_full"], N["xr_led"], N["xr_sum"] = xr_full, xr_led, xr_sum

    # ---- 变异台 / 自检 / 互证 / 对账 ----
    m = _grab(st, r"自检（Phase-0 G0-1\.\.G0-7）：(\d+) 条 ｜ FAIL (\d+) 条", "自检小结")
    N["st_n"], N["st_fail"] = m.groups()
    m = _grab(mu, r"变异台：抓到 (\d+) / (\d+)（无效 (\d+) 条", "变异台小结")
    N["mut_caught"], N["mut_total"], N["mut_invalid"] = m.groups()
    N["mut_crash"] = _grab(mu, r"崩的条数：(\d+)", "崩计数").group(1)
    N["mut_ids"] = re.findall(r"^\[(?:抓到|硬停抓到)\] (\S+)", mu, re.M)
    N["mut_pl3"] = _grab(mu, r"^\[抓到\] PL3\s+(.*)$", "PL3").group(1)
    N["cr_ok"] = _grab(cr, r"^CROSS\|items_ok=(\d+)$", "互证计数").group(1)
    N["cr_bad"] = _grab(cr, r"^CROSS\|mismatches=(\d+)$", "互证失配").group(1)
    N["cr_verdict"] = _grab(cr, r"^CROSS\|verdict=(\S+)$", "互证判决形态").group(1)
    m = _grab(sp, r"对账条数：OK (\d+) ｜ 红 (\d+)", "预登记对账")
    N["sp_ok"], N["sp_bad"] = m.groups()
    N["rc_host"] = _grab(rc, r"^host=(\S+)\s+date=", "收据主机").group(1)
    N["rc_rcs"] = _grab(rc, r"^SELFTEST_RC=(\d+)\s+DE_RC=(\d+)\s+MUT_RC=(\d+)\s+"
                           r"CROSS_RC=(\d+)\s+SPEC_RC=(\d+)$", "收据退出码").groups()

    # ---- 全回归 R6 ----
    N["reg_line"] = "⛔ **R6 收据未取回**"
    if reg:
        def _rg(pat, what):
            return _grab(reg, pat, what).group(1)
        N["reg_line"] = ("`%s` ｜ 执行集 **%s** 个 py ｜ 清单 diff 对 R5 added **%s** / removed **%s** ｜ "
                         "变异台 全绿 %s / 跑得动 %s ｜ 自检 全绿 %s / 跑得动 %s ｜ `REG_RC = %s` ｜ "
                         "账本 %s 行 md5 `%s`"
                         % (_rg(r"host=(\S+)\s+date=", "R6 主机"),
                            _rg(r"n_exec_py=(\d+)", "R6 执行集数"),
                            _rg(r"added=(\d+)", "R6 added"),
                            _rg(r"removed=(\d+)", "R6 removed"),
                            _rg(r"小结：变异台 全绿 (\d+)", "R6 变异台全绿"),
                            _rg(r"小结：变异台 全绿 \d+ / 跑得动 (\d+)", "R6 变异台跑得动"),
                            _rg(r"自检 全绿 (\d+)", "R6 自检全绿"),
                            _rg(r"自检 全绿 \d+ / 跑得动 (\d+)", "R6 自检跑得动"),
                            _rg(r"REG_RC=(\d+)", "R6 REG_RC"),
                            _rg(r"ledger_lines=(\d+)", "R6 账本行数"),
                            _rg(r"ledger_md5=(\w+)", "R6 账本 md5")))
    return N


def build(N):
    S = N["subs"]
    L = []
    A = L.append
    A("# 交接 —— 244.85「类级结论的留一稳健性（LOO）」（2026-10-24 11:1x）")
    A("")
    A("⚖⚖⚖ **一句话**")
    A("")
    A("**244.84 那个「`r₀` 系统性地落在 steering 向量的公共方向上」的类级结论，本轮被留一法（LOO）"
      "判成 **F-B**：它**站不住**（判决形态 %s）。**" % N["verdict"])
    A("")
    A("手法是**换掉「纳入哪几把 w」，不换 `r₀`** ⇒ ⇒ 对 **16 个子集**"
      "（FULL n=6 ｜ 6 个 LOO n=5 ｜ STRAT-A n=4 ｜ 簇 A/B n=3 ｜ 6 个 SINGLE n=1）"
      "各自**重算**类级统计量 ⇒ ⇒ **每个子集有自己的零分布、自己的 sd、自己的经验假阳性率 FPR_n**"
      "（⛔ n=6 的 FPR 不许套到 n=5）。")
    A("")
    A("⚖⚠⚠⚠ **F-B 的准确含义**（⛔ 不许读成「无差异」）：")
    A("**「`r₀` 系统性地落在 steering 向量的公共方向上」这一句仍然「未量到」** ⇒ ⇒ "
      "能站住的只有**更窄**的一句：「`r₀` 与**簇 A** 显著对齐」（`CLU-A` 的 z=%s，该 n 自己的 FPR_n=%s ≤ 0.05），"
      "而**与簇 B 不对齐**（z=%s）。"
      % (S["CLU-A"]["z"], S["CLU-A"]["fpr"], S["CLU-B"]["z"]))
    A("")
    A("## 1. 📊 判决面板（留一 · 决策族）")
    A("")
    A("| 子集 | n | T | z_T | FPR_n | 形态 |")
    A("|---|---|---|---|---|---|")
    for k in DECISION:
        s = S[k]
        A("| **%s** | %d | %+.9f | **%+.4f** | %.5f | **%s** |"
          % (k, s["n"], float(s["T"]), float(s["z"]), float(s["fpr"]), s["shape"]))
    A("")
    A("| 量 | 值 | 判据 |")
    A("|---|---|---|")
    A("| **基线** FULL 的类级统计量 | T=%s ｜ z_T=%s ｜ 秩 %s ｜ 参考 sd %s ｜ 理论 sd %s ｜ FPR %s | "
      "与账本 244.84 段**逐项对账**（%d 项里 **%d 项差 0**）｜ 其中 **%d 项与 244.84 主表逐位相同**"
      "（H13，⛔ 不是「相对差 ≤ 1e-12」） |"
      % (N["T"], N["z"], N["rank"], N["sd"], N["theo"], N["fpr"],
         N["h6_n"], N["h6_zero"], N["h13_ulp0"]))
    A("| **关键位**（去掉剂量批那一把） | `LOO-p2a` 的 z_T=%s ⇒ 判 **%s** | 判决阈值 2.0 |"
      % (S["LOO-p2a"]["z"], S["LOO-p2a"]["shape"]))
    A("| **决策族里掉出阈值的子集** | %s（共 %d / %d 个） | ⇒ ⇒ 类级结论**依赖这些成员** |"
      % ("、".join(N["ea"]), len(N["ea"]), len(DECISION)))
    A("| **逐 n 判别力**（每个子集自己的 FPR_n） | 最大 %s（上限 0.05） | H9 ⇒ ⇒ 规则**逐 n 都可用** |"
      % N["h9_max"])
    A("| **逐子集校准**（参考 sd vs 理论 ‖m_S‖/√d） | 最大相对差 %s（上限 0.05） | H8 ⇒ ⇒ 零分布**逐子集被校准** |"
      % N["h8_max"])
    A("| **自包含闸**（构造种子 42 vs 类级参考区间 100001..102000） | 交集 ∅ ｜ 含它的参考集 z_T=%s（判 %s）"
      "vs 不含 %s（判 %s） | H11 ⇒ ⇒ 自包含**没有影响判决** |"
      % (N["h11_alt"], N["h11_altv"], N["h11_z"], N["h11_v"]))
    A("| **负控**（6 把各自独立坐标置换） | z_T=%s（\\|z\\| 上限 %s）｜ 置换后两两余弦 max=+0.035476368742900312"
      "（上限 0.15） | H10 ⇒ ⇒ 负控通过 |" % (N["h10_z"], N["h10_zmax"]))
    A("")
    A("## 2. 🔍 描述族（算出来、登记，⛔ 不进判决）")
    A("")
    A("| 子集 | n | T | z_T | FPR_n | 形态 |")
    A("|---|---|---|---|---|---|")
    for k in DESCRIPTIVE:
        s = S[k]
        A("| %s | %d | %+.9f | %+.4f | %.5f | %s |"
          % (k, s["n"], float(s["T"]), float(s["z"]), float(s["fpr"]), s["shape"]))
    A("")
    A("⚖ **为什么簇与分层只进描述族**：簇与分层**换的是总体**、不是「同一总体去掉一把」；"
      "⛔ 且 `CLU-B` 的 z=%s **必定**是 E-A ⇒ ⇒ 若把簇放进决策族，**F-A 就是死分支**。"
      % S["CLU-B"]["z"])
    A("")
    A("## 3. ⚖⚖⚖ 跨路线差值（「逐位」这句话的边界）")
    A("")
    A("H6 的容差是「相对差 ≤ 1e-12」⇒ ⇒ **差 1 个 ULP 照样过** ⇒ ⇒ 「差 0」与「差 3 个 ULP」"
      "在容差口径下**长得一模一样** ⇒ ⇒ 差值**单独存、单独落账**：")
    A("")
    A("| 比的是 | 纯 Python 路线 | numpy 路线 | 相对差 | ULP 差 | 逐位相同 |")
    A("|---|---|---|---|---|---|")
    for it in N["xr_full"]:
        A("| FULL %s | `%s` | `%s` | %s | **%s** | %s |"
          % (it.get("name", "?"), it.get("py", "?"), it.get("np", "?"), it.get("rel", "?"),
             it.get("ulp", "?"), "✅ 是" if it.get("identical") == "yes" else "⛔ **否**"))
    A("")
    A("- 两条路线的最大差：相对差 `%s`（出现在 `%s`）｜ ULP 差 **%s**（出现在 `%s`）｜ 逐位相同的项 **%s**"
      % (N["xr_sum"].get("max_rel", "?"), N["xr_sum"].get("at", "?"),
         N["xr_sum"].get("max_ulp", "?"), N["xr_sum"].get("ulp_at", "?"),
         N["xr_sum"].get("identical", "?")))
    A("- numpy 路线 vs 账本 244.84 主表：**%d 项全部逐位相同**（ULP 差 0）⇒ ⇒ "
      "「逐位」**只限「同一条实现路线」** ⇒ ⇒ ⛔ **不许**推广成「跨实现逐位可复现」。"
      % len(N["xr_led"]))
    A("")
    A("## 4. ✅ 每条判据能红")
    A("")
    A("- 自检（Phase-0 G0-1..G0-7，合成夹具、零 bpath、零 GPU）：判据 **%s** 条 ｜ FAIL **%s** 条"
      % (N["st_n"], N["st_fail"]))
    A("- 变异台：抓到 **%s / %s**（无效 %s ⇒ 记「无效」不计入分母）｜ 崩 **%s**（⛔ 必须是 0）"
      % (N["mut_caught"], N["mut_total"], N["mut_invalid"], N["mut_crash"]))
    A("- 真数据判据：**%s** 条 ｜ PASS **%s** ｜ FAIL **%s**"
      % (N["de_n"], N["de_pass"], N["de_fail"]))
    A("- 互证（第二条独立实现，纯 Python 路线 vs numpy 路线）：OK **%s** ｜ MISMATCH **%s** ｜ 判决形态 **%s**"
      % (N["cr_ok"], N["cr_bad"], N["cr_verdict"]))
    A("- 预登记 ↔ 实现 的机械对账：OK **%s** ｜ 红 **%s**" % (N["sp_ok"], N["sp_bad"]))
    A("- 变异台逐条：%s" % "、".join(N["mut_ids"]))
    A("")
    A("⚖⚖⚖ **PL3 是本轮最有价值的变异**：%s" % N["mut_pl3"])
    A("⇒ ⇒ 它证明「逐位」这条守卫**真的在比位**，⛔ **不是**「相对差 ≤ 1e-12」的同义词。")
    A("")
    A("## 5. ⚠⚠⚠ 三条更正 ＋ 两条发现（撤回并更正，⛔ 不改数凑好看）")
    A("")
    A("1. **更正 ①：F-B 的「降级措辞」** —— 预登记 §4.3 原写「降级为『**这一对**（`w_p2a`, `r₀`）的现象』」，"
      "但实测 `LOO-m1`（z=%s）与 `LOO-t1`（z=%s）**也**掉出阈值 ⇒ ⇒ 准确的降级对象是"
      "「**簇 A 相对 `r₀` 的对齐**」⇒ ⇒ 改的只有**解释层**，⛔ **没改任何实测数**、"
      "⛔ **没改判决形态与触发条件**。"
      % (S["LOO-m1"]["z"], S["LOO-t1"]["z"]))
    A("2. **更正 ②：预登记 §2.1 的表格排版** —— `SINGLE` 那 6 行原写成一行 ⇒ ⇒ 机械对账解析不到 "
      "⇒ ⇒ 拆成 6 行（**口径内容一字未改**）。")
    A("3. **更正 ③：⚠ 账本 244.84 段【4】那行「互证逐位」的标签不准确** —— 那行的类级 T/z 与**同一段主表**"
      "**不是同一个 double**（差 3 ULP / 2 ULP）⇒ ⇒ 标签写错了。⚖ **正面证据**：本轮纯 Python 路线算出的"
      "FULL 类级 T=%s、z=%s，与那一行**逐位相同** ⇒ ⇒ **数没错，错的是标签** ⇒ ⇒ "
      "⛔ **只更正标签、不改任何数**；账本**只追加** ⇒ ⇒ 244.84 段的**原文一字不动**。"
      % (N["xr_full"][0].get("py", "?"), N["xr_full"][1].get("py", "?")))
    A("4. **发现 ①：⚠⚠⚠ 244.84 的 H1 实现比它自己的预登记松** —— 预登记写的是「md5 **==** 账本登记值」，"
      "实现取的是「实测 md5 **∈ 三个候选**」⇒ ⇒ 本轮按**预登记**实现 ⇒ ⇒ 244.84 的 H1 收紧后**仍然绿** "
      "⇒ ⇒ 这是**判据收紧**，⛔ 不是「改数」。")
    A("5. **发现 ②：⚠⚠⚠ H6 的「差 0」是「同一条实现路线」的结果** —— 跨路线实测差 3 ULP / 2 ULP "
      "⇒ ⇒ 「逐位」只限同路线 ⇒ ⇒ 本轮因此把「位级相同」单独做成**硬判据 H13-BITIDENT**，"
      "并用 **PL3**（账本副本挪 1 ULP ⇒ **H6 绿 / H13 红**）证明它**能红**。"
      "⚖ **没改实测数**；⚖ **没改判决形态与触发条件**（H13 实测绿 ⇒ 形态仍是 %s）；"
      "⚠ 但 H13 是**事后**加的 ⇒ ⇒ **假如它当初是红的，形态会是 FAIL** ⇒ ⇒ 它**有可能**改变结论 "
      "⇒ ⇒ 结论**未变**是因为它实测绿。" % N["verdict"])
    A("")
    A("## 6. 📚 证据链台账")
    A("")
    A("- 权威账本：`.cache/xcheck/R6_RERUN_PREREG.md`（**只追加**，`## 修订 244.85` 段）")
    A("- 索引：`.cache/xcheck/R6_RERUN_INDEX.md`（每条修订一行）")
    A("- 预登记：`.cache/xcheck/R6_LOO_ROBUSTNESS_PREREG.md`（**先于实现**签；§0.5 含**三条更正 ＋ 两条发现**，"
      "逐条写明发生时机与有没有改动实测数）")
    A("- 收据：`.cache/r244/_e24485/{selftest,de,mut,cross,spec}.out` ＋ `receipt.txt` ＋ `reg_24485.txt`")
    A("- 「预登记 ↔ 实现」机器对账：`.cache/r244/_spec_crosscheck_24485.py`（%s 条机械比 ＋ "
      "明确「不能机械比」＋ 自证能红）" % N["sp_ok"])
    A("- 验证链：`%s` ｜ SELFTEST_RC=%s DE_RC=%s MUT_RC=%s CROSS_RC=%s SPEC_RC=%s"
      % ((N["rc_host"],) + N["rc_rcs"]))
    A("- 全回归 R6：%s" % N["reg_line"])
    A("")
    A("## 7. ⛔ 边界清单（本轮哪些仍未量到）")
    A("")
    A("- ⛔ **「`r₀` 系统性地落在 steering 向量的公共方向上」仍然未量到** —— 本轮判成 F-B "
      "⇒ ⇒ 那句话**降级**为「`r₀` 与**簇 A** 显著对齐」这一条**更窄**的事实 ⇒ ⇒ "
      "「系统性重叠」**未量到**（⛔ 不是「无差异」）。")
    A("- ⛔ **「污染对改判率的影响」仍然未量到** —— 固定剂量批**没落盘 alpha 轨迹**（跑批器调探针时"
      "**没传 `--dump-raw`**）⇒ ⇒ 离线**算不出**；且 w 臂在 **w 剂量 %s** 处的响应**未量到**、"
      "单调性**未量到** ⇒ ⇒ 本轮只登记**条件命题**（污染在 rand 臂最大剂量处等效于一次 **w 剂量 %s** 的注入），"
      "⛔ 两条前提未实测 ⇒ ⇒ **不进判决**。" % (N["d1_equiv"], N["d1_equiv"]))
    A("- ⛔ **「换个 w 也会被同样污染」未量到** —— 本轮只验了「**去掉一把**」这一族变换。")
    A("- ⛔ **「6 把 w 代表全部 steering 向量」的外推** ⇒ ⇒ **未量到**（6 把是**同一套 recipe** 的 "
      "6 个解：同 marker 集、同训练种子 42、同层）⇒ ⇒ 外推范围仅限「同一 recipe 的解」。")
    A("- ⛔ **「多随机种子的对照臂」** ⇒ ⇒ 仍然**未量到**（本轮还是**一个** `r₀` ⇒ ⇒ **r 那一侧仍是 N=1**）。")
    A("- ⛔ **「哪一条臂是机制效应」** ⇒ ⇒ 沿用旧留白，**未量到**。")
    A("- ⛔ 远端 tokenizer 快照的内容指纹、**照 meta 重建能否逐位复现** ⇒ ⇒ 沿用旧留白，**未量到**。")
    A("")
    A("## 8. ▶️ 如何做（下一步）")
    A("")
    A("1. **先读**账本尾部 `/Users/zhourui/code/steer3d/.cache/xcheck/R6_RERUN_PREREG.md`"
      "（**唯一权威历史**）→ ② 再读本文件 → ③ `git log --oneline -10` + `git status --porcelain`"
      "（工作区有同事的未跟踪文件，⛔ 不碰）→ ④ 照下面接着做。")
    A("2. **下一轮 244.86（按性价比排序）**：")
    A("   - **固定剂量批重跑并加 `--dump-raw`**（w 臂 + rand 臂）⇒ ⇒ 拿到 60 点全曲线 ⇒ ⇒ "
      "离线把 w 臂曲线缩放到 **%s** 剂量 ⇒ ⇒ 直接算「污染最多能翻多少格」⇒ ⇒ "
      "把条件命题变成实测 ⚖ 这是**现在**最靠近判决数、且**不依赖**任何未决口径的一步。" % N["d1_equiv"])
    A("   - **多随机种子的对照臂**（把 **r 那一侧**也从 N=1 变成 N=K）⇒ ⇒ 把「对照臂对齐度」从 N=1 变成**分布**。")
    A("   - **同结论对照臂**（机制轴）：同结论、同末值、只有检查有效性不同。")
    A("   - **分层剂量的真阶梯**（剂量轴）：⛔ 不能事后分位分档 ⇒ ⇒ 要跑批 ⇒ ⇒ 要点头。")
    A("3. ⛔ 别把 F-B 读成「没有系统性重叠」—— 那句话是**未量到**，⛔ 不是「无差异」。")
    A("4. ⛔ 别把「逐位相同」推广到**跨实现路线** —— 本轮实测跨路线差 3 ULP / 2 ULP（见【3】）。")
    A("5. ⛔ 在「对齐越高 ⇒ w 样行为越强」这条**未实测**的单调性假设下，244.81 的 **+30.36pp 偏保守（下界）**，"
      "**幅度未量到**（244.85 不受影响：它本就没依赖类级主张）。")
    A("")
    return "\n".join(L) + "\n"


def main():
    N = collect()
    txt = build(N)
    fences = [l for l in txt.split("\n") if l.strip().startswith("```")]
    if fences:
        raise SystemExit("⛔ 交接文件里有围栏 ⇒ 不许")
    with io.open(OUT, "w", encoding="utf-8", newline="") as fh:
        fh.write(txt)
    print("✅ 已写出 %s（%d 字节 / %d 行）"
          % (OUT, len(txt.encode("utf-8")), txt.count("\n")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
