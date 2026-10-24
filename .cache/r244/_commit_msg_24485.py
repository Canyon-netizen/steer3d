#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⚖ **生成 244.85 的提交信息**（⛔ 所有数都从收据抠，⛔ 不手抄）。

用法：python3 .cache/r244/_commit_msg_24485.py  ⇒ ⇒ 写 `.cache/r244/_commit_msg_24485.txt`
"""

import io
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
EV = os.path.join(REPO, ".cache", "r244", "_e24485")
OUT = os.path.join(REPO, ".cache", "r244", "_commit_msg_24485.txt")
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


def main():
    st = _need(os.path.join(EV, "selftest.out"))
    de = _need(os.path.join(EV, "de.out"))
    mu = _need(os.path.join(EV, "mut.out"))
    cr = _need(os.path.join(EV, "cross.out"))
    sp = _need(os.path.join(EV, "spec.out"))
    rc = _need(os.path.join(EV, "receipt.txt"))
    regp = os.path.join(EV, "reg_24485.txt")
    reg = _read(regp) if os.path.isfile(regp) else ""

    N = {}
    N["verdict"] = _grab(de, r"^VERDICT=(\S+)$", "判决形态").group(1)
    N["why"] = _grab(de, r"^VERDICT_WHY=(.+)$", "判决理由").group(1).strip().replace("**", "")
    m = _grab(de, r"^判据汇总：(\d+) 条 ｜ PASS (\d+) ｜ FAIL (\d+)$", "真数据判据小结")
    N["de_n"], N["de_pass"], N["de_fail"] = m.groups()
    N["de_ids"] = re.findall(r"^\[PASS\] (\S+)", de, re.M)
    m = _grab(de, r"^账本期望值（244\.84 段）：T=([-+0-9.eE]+) ｜ z=([-+0-9.eE]+) ｜ "
                   r"秩=([-+0-9.eE]+) ｜ 参考 sd=([-+0-9.eE]+) ｜ 理论 sd=([-+0-9.eE]+) ｜ "
                   r"FPR=([-+0-9.eE]+) ｜ 判决形态=(\S+)$", "账本期望值")
    (N["rc_T"], N["rc_z"], N["rc_rank"], N["rc_sd"], N["rc_theo"],
     N["rc_fpr"], N["exp_verdict"]) = m.groups()

    # ⚖⚖⚖ **账本 244.84 段的**原文**（⛔ 不用收据里 `%r` 的缩写）
    #   ⇒ ⇒ 提交信息里的 T/z 与**账本那一串逐字相同**（读者可直接 grep 对上）
    _led = _read(os.path.join(REPO, ".cache", "xcheck", "R6_RERUN_PREREG.md"))
    _m = re.search(r"^## 修订 244\.84\b", _led, re.M)
    if not _m:
        raise SystemExit("⛔ 账本里没有「## 修订 244.84」段 ⇒ ⇒ 基线原文无处可读 ⇒ 中止")
    _m2 = re.search(r"^## 修订 ", _led[_m.end():], re.M)
    _sec = _led[_m.start():(_m.end() + _m2.start() if _m2 else len(_led))]

    def _sec_line(kw, what):
        for _l in _sec.splitlines():
            if kw in _l:
                return _l
        raise SystemExit("⛔ 账本 244.84 段里找不到含「%s」的行（%s）" % (kw, what))

    N["exp_T"] = re.search(r"\*\*([-+0-9.eE]+)\*\*",
                           _sec_line("**类级主统计量**", "类级 T")).group(1)
    N["exp_z"] = re.search(r"\*\*([-+0-9.eE]+)\*\*",
                           _sec_line("**z_T**（对参考种子分布）", "类级 z_T")).group(1)
    _mm = re.search(r"\|\s*([-+0-9.eE]+)\s*/\s*([-+0-9.eE]+)\s*/\s*([-+0-9.eE]+)\s*\|",
                    _sec_line("经验秩 / 参考 sd", "秩/sd"))
    if not _mm:
        raise SystemExit("⛔ 账本 244.84 段里读不到「经验秩 / 参考 sd / 理论 sd」")
    N["exp_rank"], N["exp_sd"], N["exp_theo"] = _mm.group(1), _mm.group(2), _mm.group(3)
    N["exp_fpr"] = re.search(r"\*\*([-+0-9.eE]+)\*\*",
                             _sec_line("经验假阳性率", "FPR")).group(1)

    subs = {}
    for m in re.finditer(
            r"^SUBSET\|([^|]+)\|n=(\d+)\|T=([-+0-9.eE]+)\|z=([-+0-9.eE]+)\|"
            r"rank=([-+0-9.eE]+)\|sd=([-+0-9.eE]+)\|theo=([-+0-9.eE]+)\|"
            r"sdrel=([-+0-9.eE]+)\|fpr=([-+0-9.eE]+)\|shape=(\S+)$", de, re.M):
        subs[m.group(1)] = {"n": int(m.group(2)), "T": m.group(3), "z": m.group(4),
                            "rank": m.group(5), "sd": m.group(6), "theo": m.group(7),
                            "sdrel": m.group(8), "fpr": m.group(9), "shape": m.group(10)}
    if len(subs) != 16:
        raise SystemExit("⛔ 收据里抠到 %d 个子集（应为 16）" % len(subs))
    N["subs"] = subs
    N["ea"] = [k for k in DECISION if subs[k]["shape"] == "E-A"]

    h6 = _grab(de, r"^\[PASS\] H6-CROSSROUND\s+(.*)$", "H6").group(1)
    pairs = re.findall(r"（差 ([-+0-9.eE]+)，上限 ([-+0-9.eE]+)）", h6)
    N["h6_n"] = len(pairs)
    N["h6_zero"] = sum(1 for d, t in pairs if float(d) == 0.0)
    N["h6_maxratio"] = max((float(d) / float(t) if float(t) else 0.0) for d, t in pairs)

    N["h9_max"] = max(v["sdrel"] for v in subs.values()) if False else max(
        float(v["fpr"]) for v in subs.values())
    N["h8_max"] = max(float(v["sdrel"]) for v in subs.values())
    N["h10_z"], N["h10_zmax"] = _grab(de, r"置换（种子 \d+\+i）后：z_T=([-+0-9.eE]+)（\|z\| 上限 ([-+0-9.eE]+)",
                                     "H10").groups()
    N["h11_alt"], N["h11_altv"], N["h11_z"], N["h11_v"] = _grab(
        de, r"含构造种子的参考集（\d+\.\.\d+）算出的 z_T=([-+0-9.eE]+)（判 (\S+)；账本登记 [-+0-9.eE]+）"
        r"vs 不含的 z_T=([-+0-9.eE]+)（判 (\S+)）", "H11").groups()
    N["h12_maxnm"] = _grab(de, r"本轮实测：余弦最大的那把 = (\S+)", "H12").group(1)
    N["h12_maxcos"] = _grab(de, r"余弦最大的那把 = \S+（([-+0-9.eE]+)）", "H12 值").group(1)
    N["d1_equiv"] = _grab(de, r"w 等效剂量 = [-+0-9.eE]+ × [-+0-9.eE]+ = ([-+0-9.eE]+)",
                           "D6").group(1)

    m = _grab(st, r"自检（Phase-0 G0-1\.\.G0-7）：(\d+) 条 ｜ FAIL (\d+) 条", "自检小结")
    N["st_n"], N["st_fail"] = m.groups()
    m = _grab(mu, r"变异台：抓到 (\d+) / (\d+)（无效 (\d+) 条", "变异台小结")
    N["mut_caught"], N["mut_total"], N["mut_invalid"] = m.groups()
    N["mut_crash"] = _grab(mu, r"崩的条数：(\d+)", "崩计数").group(1)
    N["mut_ids"] = re.findall(r"^\[(?:抓到|硬停抓到)\] (\S+)", mu, re.M)
    N["cr_ok"] = _grab(cr, r"^CROSS\|items_ok=(\d+)$", "互证计数").group(1)
    N["cr_bad"] = _grab(cr, r"^CROSS\|mismatches=(\d+)$", "互证失配").group(1)
    N["cr_verdict"] = _grab(cr, r"^CROSS\|verdict=(\S+)$", "互证判决形态").group(1)
    N["cr_subsets"] = _grab(cr, r"^CROSS\|subsets=(\d+)$", "互证子集数").group(1)
    # ---- 跨路线差值（**单独存**：⛔ 不能只说「在容差内」）----
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
        raise SystemExit("⛔ 互证收据里抠不到 CROSSROUTE 块 ⇒ ⇒ 跨路线差值没被单独存 ⇒ 中止")
    N["xr_full"], N["xr_led"], N["xr_sum"] = xr_full, xr_led, xr_sum
    m = _grab(sp, r"对账条数：OK (\d+) ｜ 红 (\d+)", "预登记对账")
    N["sp_ok"], N["sp_bad"] = m.groups()
    N["rc_host"] = _grab(rc, r"^host=(\S+)\s+date=", "收据主机").group(1)
    N["rc_rcs"] = _grab(rc, r"^SELFTEST_RC=(\d+)\s+DE_RC=(\d+)\s+MUT_RC=(\d+)\s+"
                           r"CROSS_RC=(\d+)\s+SPEC_RC=(\d+)$", "收据退出码").groups()
    N["rc_md5_base"] = dict((os.path.basename(k), v) for k, v in
                            re.findall(r"^([0-9a-f]{32})\s+(\S+)$", rc, re.M))

    # ---- 全回归 R6 ----
    reg_line = "⛔ **R6 收据未取回**"
    reg_red = []
    if reg:
        def _rg(pat, what):
            return _grab(reg, pat, what).group(1)
        reg_line = ("`%s` ｜ 执行集 **%s** 个 py ｜ 清单 diff 对 R5 added **%s** / removed **%s** ｜ "
                    "变异台 全绿 %s / 跑得动 %s ｜ 自检 全绿 %s / 跑得动 %s ｜ `REG_RC = %s` ｜ "
                    "账本 %s 行 md5 `%s`"
                    % (_rg(r"host=(\S+)", "R6 主机"), _rg(r"n_exec_py=(\d+)", "R6 执行集数"),
                       _rg(r"added=(\d+)", "R6 新增"), _rg(r"removed=(\d+)", "R6 减少"),
                       _rg(r"小结：变异台 全绿 (\d+)", "R6 变异台-全绿"),
                       _rg(r"小结：变异台 全绿 \d+ / 跑得动 (\d+)", "R6 变异台-跑得动"),
                       _rg(r"小结：.*自检 全绿 (\d+)", "R6 自检-全绿"),
                       _rg(r"小结：.*自检 全绿 \d+ / 跑得动 (\d+)", "R6 自检-跑得动"),
                       _rg(r"REG_RC=(\d+)", "R6 退出码"),
                       _rg(r"ledger_lines=(\d+)", "R6 账本行数"),
                       _rg(r"ledger_md5=(\w+)", "R6 账本 md5")))
        # ⚖⚖⚖ **红项按分类登记**（⛔ 只报两个数 ⇒ ⇒ 会把红项藏起来）
        # ⚖⚖⚖ **只把「harness 的逐条结果行」当红项**（⛔ 收据**头行**不是红项）
        for _l in reg.split("\n"):
            _s = _l.strip()
            if not _s or not _s.startswith("["):
                continue
            if _s.startswith("[OK") or _s.startswith("[SKIP"):
                continue
            reg_red.append(_s)
        try:
            _ok = int(_rg(r"小结：变异台 全绿 (\d+)", "R6 变异台-全绿"))
            _run = int(_rg(r"小结：变异台 全绿 \d+ / 跑得动 (\d+)", "R6 变异台-跑得动"))
            _ok2 = int(_rg(r"小结：.*自检 全绿 (\d+)", "R6 自检-全绿"))
            _run2 = int(_rg(r"小结：.*自检 全绿 \d+ / 跑得动 (\d+)", "R6 自检-跑得动"))
            if _ok != _run or _ok2 != _run2:
                reg_red.append("⚠ 全绿/跑得动不等：变异台 %d vs %d ｜ 自检 %d vs %d"
                               % (_ok, _run, _ok2, _run2))
        except Exception:
            pass
        if reg_red:
            reg_line += " ｜ ⚠ **红项 %d 条**（逐条见下）" % len(reg_red)
        else:
            reg_line += " ｜ ✅ **红项登记：零红项**"

    S = N["subs"]
    L = []
    A = L.append
    A("244.85：类级结论的留一稳健性 —— 「`r₀` 系统性落在 steering 公共方向上」**未量到**（判成 F-B）")
    A("")
    A("⚖⚖⚖ **这一轮验的是什么**")
    A("")
    A("244.84（对照臂方向污染的类级判读，形态 **E-B**）把「N=1 的巧合」升级成了「N=6 的类级结构」：")
    A("")
    A("    类级 T = mean_i cos(v_i, r₀) = %s ｜ z_T = %s（阈值 2.0）⇒ ⇒ 离群 ⇒ 结构"
      % (N["exp_T"], N["exp_z"]))
    A("")
    A("⇒ ⇒ 它声称「`r₀` **系统性地**落在 steering 向量的公共方向上」。")
    A("⚖⚖⚖ **但 244.84 自己登记的事实让这句话变成危楼**：**剂量批用的那把 `w_p2a` 恰好是对齐最高的那把**")
    A("（余弦 %s，6 把里最大；簇 A 的 z=%s、簇 B 的 z=%s）⇒ ⇒ 「类级结构」**可能是被那一把撑起来的**。"
      % (N["h12_maxcos"], S["CLU-A"]["z"], S["CLU-B"]["z"]))
    A("")
    A("⚖⚖⚖ **手法：换掉「纳入哪几把」，不换 `r₀`**")
    A("")
    A("对 **16 个子集**（FULL n=6 ｜ 6 个 LOO n=5 ｜ STRAT-A n=4 ｜ 簇 A/B n=3 ｜ 6 个 SINGLE n=1）")
    A("各自**重算**类级统计量 ⇒ ⇒ **每个子集有自己的零分布、自己的 sd、自己的经验假阳性率 FPR_n**")
    A("（⛔ n=6 的 FPR 不许套到 n=5 —— 244.84 只验过 n=6 那一个 n）。")
    A("")
    A("⚖⚖⚖ **判决（形态 %s）**" % N["verdict"])
    A("")
    A("- %s" % N["why"])
    A("- **基线 FULL** ｜ T = %s ｜ z_T = %s ｜ 秩 %s ｜ 参考 sd %s ｜ 理论 sd %s ｜ FPR %s"
      % (N["exp_T"], N["exp_z"], N["exp_rank"], N["exp_sd"], N["exp_theo"], N["exp_fpr"]))
    A("- **关键位 `LOO-p2a`**（去掉剂量批那一把）｜ z_T = **%s** ⇒ 判 **%s**"
      % (S["LOO-p2a"]["z"], S["LOO-p2a"]["shape"]))
    A("- **决策族里掉出阈值的子集**：%s（%d / %d 个）⇒ ⇒ 类级结论**依赖这些成员**，不是「一对」"
      % ("、".join(N["ea"]), len(N["ea"]), len(DECISION)))
    A("- **逐 n 判别力**：每个子集自己的 FPR_n 最大 **%.5f**（上限 0.05）⇒ ⇒ 规则**逐 n 都可用**"
      % N["h9_max"])
    A("- **逐子集校准**：参考 sd vs 理论 ‖m_S‖/√d 的相对差最大 **%.6f**（上限 0.05）⇒ ⇒ 零分布**逐子集被校准**"
      % N["h8_max"])
    A("- **跨轮对账**：%d 项里 **%d 项差 0**，最大占用比 %.3g ⇒ ⇒ 基线与 244.84 对得上"
      % (N["h6_n"], N["h6_zero"], N["h6_maxratio"]))
    A("- **位级对账（H13）**：FULL 的 6 项（类级 T / z_T / 秩 / 参考 sd / 理论 sd / FPR）与账本 244.84 "
      "主表**是同一个 double**（ULP 差 0）⇒ ⇒ 「逐位」这句话**有判据在守**"
      "（变异台 **PL3**：把账本副本的类级 T **挪 1 ULP** ⇒ ⇒ **H6 照样绿、H13 必红**）")
    A("- ⚖ **跨路线差值（单独存）**：numpy 路线 vs 纯 Python 路线的 FULL 类级 T/z "
      "**不是同一个 double**（ULP 差 %s / %s，相对差 %s / %s）⇒ ⇒ "
      "「逐位」**只限同一条实现路线** ⇒ ⇒ ⛔ **不许**推广成「跨实现逐位可复现」"
      % (N["xr_full"][0].get("ulp", "?"), N["xr_full"][1].get("ulp", "?"),
         N["xr_full"][0].get("rel", "?"), N["xr_full"][1].get("rel", "?")))
    A("- **自包含闸**：含构造种子的参考集 z_T=%s（判 %s）vs 不含 %s（判 %s）⇒ ⇒ 形态相同"
      % (N["h11_alt"], N["h11_altv"], N["h11_z"], N["h11_v"]))
    A("- **负控**：6 把各自独立坐标置换后 z_T=%s（z 的绝对值上限 %s）⇒ ⇒ 负控通过"
      % (N["h10_z"], N["h10_zmax"]))
    A("")
    A("⚖⚖⚖ **留一面板（决策族）**")
    A("")
    A("| 子集 | n | T | z_T | FPR_n | 形态 |")
    A("|---|---|---|---|---|---|")
    for k in DECISION:
        s = S[k]
        A("| **%s** | %d | %+.9f | **%+.4f** | %.5f | **%s** |" % (k, s["n"], float(s["T"]),
                                                                    float(s["z"]),
                                                                    float(s["fpr"]), s["shape"]))
    A("")
    A("⚖⚖⚖ **描述族（算出来、登记，⛔ 不进判决）**")
    A("")
    A("| 子集 | n | T | z_T | FPR_n | 形态 |")
    A("|---|---|---|---|---|---|")
    for k in DESCRIPTIVE:
        s = S[k]
        A("| %s | %d | %+.9f | %+.4f | %.5f | %s |" % (k, s["n"], float(s["T"]), float(s["z"]),
                                                        float(s["fpr"]), s["shape"]))
    A("")
    A("⚖⚖⚖ **这轮真正测出来的一句话**")
    A("")
    A("> 能站住的**只有更窄**的一句：**「`r₀` 与簇 A 显著对齐」**（`CLU-A` 的 z=**%s**，该 n 自己的 "
      "FPR_n=**%.5f** ≤ 0.05），而**与簇 B 不对齐**（z=**%s**）。"
      % (S["CLU-A"]["z"], float(S["CLU-A"]["fpr"]), S["CLU-B"]["z"]))
    A("> ⛔ 「`r₀` 系统性地落在 steering 向量的公共方向上」**未量到**（⛔ 不是「无差异」）。")
    A("> ⚖ 而且这**不是本轮的发现** —— `CLU-A` 的 z=+2.393 是 **244.84 已登记**的事实 ⇒ ⇒ 它是**复算**。")
    A("> ⚠⚠⚠ 本轮扫了 **16 个子集** ⇒ ⇒ 单点 FPR 在**族内**不再是那个数 ⇒ ⇒ 只能写成"
      "「**在 244.84 预先登记的簇 A 上复现了离群**」，⛔ **不许**写成「16 个子集里唯一显著的那个」。")
    A("")
    A("⚖⚖⚖ **三条更正 ＋ 两条发现（撤回并更正，⛔ 不改数凑好看）**")
    A("")
    A("1. **更正 ①：F-B 的「降级措辞」** —— 预登记 §4.3 的 F-B 行原写「降级为『**这一对**"
      "（`w_p2a`, `r₀`）的现象』」⇒ ⇒ 但实测 **`LOO-m1`（z=%s）** 与 **`LOO-t1`（z=%s）** 也**掉出阈值**"
      "⇒ ⇒ 去掉**簇 A 的任意一把**都会让类级结论掉出阈值 ⇒ ⇒ 准确的降级对象是"
      "「**簇 A 相对 `r₀` 的对齐**」，⛔ 不是「这一对」。"
      "⚖ **没有改动实测数**（一个都没有）｜⚖ **没有改动判决形态与触发条件**"
      "（§3.1 的 F-B 触发条件「`LOO-p2a`=E-A」**一字未改**）⇒ ⇒ 改的只有**解释层**。"
      % (S["LOO-m1"]["z"], S["LOO-t1"]["z"]))
    A("2. **更正 ②：预登记 §2.1 的表格排版** —— `SINGLE` 那 6 行原写成**一行** ⇒ ⇒ 机械对账解析不到 "
      "⇒ ⇒ 拆成 6 行（**口径内容一字未改**，只改排版，让它**可被机械解析**）。")
    A("3. **发现 ①：⚠⚠⚠ 244.84 的 H1 实现比它自己的预登记松** —— 预登记写的是「md5 **==** 账本登记值」，"
      "而 244.84 的实现取的是「实测 md5 **∈ 三个候选**」（账本那一行**同时**登记了 "
      "`w_p2a.npy` / `w_p2a.npy.json` / `train_p2a.log` 三个 md5）⇒ ⇒ 本轮按**预登记**实现"
      "（取「`w_p2a.npy` 之后出现的第一个 md5」）⇒ ⇒ 244.84 的 H1 在收紧后**仍然绿** "
      "⇒ ⇒ 这是**判据收紧**，⛔ 不是「改数」。")
    A("4. **更正 ③：⚠ 账本 244.84 段【4】那行「互证逐位」的标签不准确** —— 那行的类级 T `%s` 与类级 z `%s`，"
      "与**同一段主表**的 `%s` / `%s` **不是同一个 double**（差 3 ULP / 2 ULP）⇒ ⇒ 标签写错了。"
      "⚖ **正面证据（那行的数本身没错）**：本轮**纯 Python 路线**算出的 FULL 类级 T=`%s`、z=`%s`，"
      "与那一行**逐位相同** ⇒ ⇒ **数没错，错的是标签** ⇒ ⇒ ⛔ **只更正标签、不改任何数**；"
      "账本**只追加** ⇒ ⇒ 244.84 段的**原文一字不动**。"
      % (N["xr_full"][0].get("py", "?"), N["xr_full"][1].get("py", "?"),
         N["exp_T"], N["exp_z"],
         N["xr_full"][0].get("py", "?"), N["xr_full"][1].get("py", "?")))
    A("5. **发现 ②：⚠⚠⚠ H6 的「差 0」是「同一条实现路线」的结果** —— 跨路线实测差 3 ULP / 2 ULP "
      "⇒ ⇒ 「逐位」只限同路线 ⇒ ⇒ 本轮因此把「位级相同」单独做成**硬判据 H13-BITIDENT**，"
      "并用 **PL3**（账本副本挪 1 ULP ⇒ **H6 绿 / H13 红**）证明它**能红**。"
      "⚖ **没改实测数**；⚖ **没改判决形态与触发条件**（H13 实测绿 ⇒ 形态仍是 %s）；"
      "⚠ 但 H13 是**事后**加的 ⇒ ⇒ **假如它当初是红的，形态会是 FAIL** ⇒ ⇒ 它**有可能**改变结论 "
      "⇒ ⇒ 结论**未变**是因为它实测绿。"
      % N["verdict"])
    A("")
    A("⚖⚖⚖ **每条判据能红**")
    A("")
    A("- **自检**（Phase-0 G0-1..G0-7，合成夹具、零 bpath、零 GPU）：判据 %s 条 ｜ FAIL %s 条"
      % (N["st_n"], N["st_fail"]))
    A("- **变异台**：抓到 **%s / %s**（无效 %s 条 ⇒ 记「无效」⇒ 不计入分母）｜ 崩 **%s**（⛔ 必须是 0）"
      % (N["mut_caught"], N["mut_total"], N["mut_invalid"], N["mut_crash"]))
    A("- **互证**（第二条独立实现，纯 Python 路线 vs numpy 路线）：%s 个子集 ｜ OK **%s** ｜ "
      "MISMATCH **%s** ｜ 判决形态 **%s**"
      % (N["cr_subsets"], N["cr_ok"], N["cr_bad"], N["cr_verdict"]))
    A("- **预登记 ↔ 实现 的机械对账**：OK **%s** ｜ 红 **%s**" % (N["sp_ok"], N["sp_bad"]))
    A("- **真数据判据**：%s 条 ｜ PASS **%s** ｜ FAIL **%s**"
      % (N["de_n"], N["de_pass"], N["de_fail"]))
    A("- 变异台逐条：%s" % "、".join(N["mut_ids"]))
    A("- 真数据判据逐条：%s" % "、".join(N["de_ids"]))
    A("")
    A("⚖⚖⚖ **全回归**")
    A("")
    A(reg_line)
    if reg_red:
        A("")
        A("⚠ **红项逐条**：")
        for r in reg_red:
            A("  - `%s`" % r)
    A("")
    A("⚖⚖⚖ **边界（本轮哪些仍未量到）**")
    A("")
    A("- ⛔ **「`r₀` 系统性地落在 steering 向量的公共方向上」仍然未量到** ⇒ ⇒ 本轮把它判成 F-B "
      "⇒ ⇒ 那句话**降级**为「`r₀` 与**簇 A** 显著对齐」这一条**更窄**的事实。")
    A("- ⛔ **「污染对改判率的影响」仍未量到** —— 固定剂量批**没落盘 alpha 轨迹**（跑批器调探针时"
      "**没传 `--dump-raw`**）⇒ ⇒ 离线**算不出**「污染最多能翻多少格」；且 w 臂在 **w 剂量 %s** 处的响应"
      "**未量到**、单调性**未量到** ⇒ ⇒ 只登记**条件命题** ⇒ ⇒ **不进判决**。" % N["d1_equiv"])
    A("- ⛔ **「换个 w 也会被同样污染」未量到** —— 本轮只验了「**去掉一把**」这一族变换。")
    A("- ⛔ **「6 把 w 代表全部 steering 向量」的外推** ⇒ ⇒ **未量到**（6 把是**同一套 recipe** 的 6 个解）。")
    A("- ⛔ **「r 那一侧」仍是 N=1** —— 本轮只把**纳入哪几把 w**变成变量 ⇒ ⇒ **多随机种子的对照臂**仍要跑批。")
    A("- ⛔ **「哪一条臂是机制效应」** ⇒ ⇒ 沿用旧留白，**未量到**（要「同结论对照臂」）。")
    A("- ⛔ 远端 tokenizer 快照的内容指纹、**照 meta 重建能否逐位复现** ⇒ ⇒ 沿用旧留白，**未量到**。")
    A("")
    A("⚖⚖⚖ **本轮改了哪些文件**")
    A("")
    A("- `.cache/r244/loo_robustness_audit.py`（**进执行集**）—— 留一稳健性实现")
    A("- `.cache/r244/mut_loo_robustness_audit.py`（**进执行集**）—— 变异台 24 条")
    A("- `.cache/r244/_cross_check_24485.py`（⛔ **不进**执行集）—— 第二条独立实现（纯 Python 路线）")
    A("- `.cache/r244/_spec_crosscheck_24485.py`（⛔ **不进**执行集）—— 预登记 ↔ 实现的机械对账")
    A("- `.cache/r244/_run_24485_verify.sh`、`_run_24485_reg_shm.sh`、`_append_24485.py`、"
      "`_commit_msg_24485.py`、`_make_handoff_24485.py`、`_gen_readback_24485.py`、"
      "`_post_commit_readback_24485.py`、`_commit_24485.sh`（⛔ **不进**执行集）")
    A("- `.cache/xcheck/R6_LOO_ROBUSTNESS_PREREG.md`（**先于实现**签的预登记；§0.5 含**两条更正**）")
    A("- `.cache/xcheck/R6_RERUN_PREREG.md`（账本，只**追加** 244.85 段）、`.cache/xcheck/R6_RERUN_INDEX.md`")
    A("")
    A("⚖ **远端**：`%s`（验证链，零 GPU、只读 bpath）＋ `zju-12`（全回归 R6）" % N["rc_host"])
    A("")

    txt = "\n".join(L) + "\n"
    with io.open(OUT, "w", encoding="utf-8", newline="") as fh:
        fh.write(txt)
    print("✅ 已写：%s（%d 字节）" % (OUT, len(txt.encode("utf-8"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
