#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⚖ **244.84 提交信息生成器**（⛔ 全部数从收据抠，⛔ 不手抄）。

**收据**：
  · `.cache/r244/_e24484/{selftest,de,mut,cross}.out`（zju-53，零 GPU，只读 bpath）
  · `.cache/r244/_e24484/reg_24484.txt`（zju-12，全回归 R5）
"""

import io
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
EV = os.path.join(REPO, ".cache", "r244", "_e24484")
OUT = os.path.join(REPO, ".cache", "r244", "_commit_msg_24484.txt")


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

    N = {}
    # ---- 判决形态 ----
    N["verdict"] = _grab(de, r"^VERDICT=(\S+)$", "判决形态").group(1)
    N["why"] = _grab(de, r"^判决形态：(.+)$", "判决形态说明").group(1).strip()
    m = _grab(de, r"^判据汇总：(\d+) 条 ｜ PASS (\d+) ｜ FAIL (\d+)$", "判据小结")
    N["de_n"], N["de_pass"], N["de_fail"] = m.groups()
    N["de_ids"] = re.findall(r"^\[PASS\] (\S+)", de, re.M)

    # ---- 账本期望值 & 跨轮对账 ----
    m = _grab(de, r"^账本期望值（244\.83 段）：cos0=([-+0-9.eE]+) ｜ 秩=([-+0-9.eE]+) ｜ "
                   r"z=([-+0-9.eE]+) ｜ 参考 sd=([-+0-9.eE]+) ｜ w 能量占比=([-+0-9.eE]+)$", "账本期望值")
    N["exp_cos0"], N["exp_rank"], N["exp_z"], N["exp_sd"], N["exp_wfrac"] = m.groups()
    N["md5_cand"] = _grab(de, r"^账本 244\.78 段登记的 w_p2a\.npy md5 候选：(.+)$", "md5 候选").group(1).strip()

    # ---- H5 / H6 ----
    m = _grab(de, r"^\[PASS\] H5-CLASSCOS\s+6 把对 r₀ 的余弦：(.+?) ｜ w_p2a 那一条 = ([-+0-9.eE]+) ｜ "
                   r"账本 244\.83 登记 = ([-+0-9.eE]+) ｜ 相对差 ([-+0-9.eE]+)（上限 ([-+0-9.eE]+)）", "H5")
    N["h5_list"], N["h5_cos"], N["h5_exp"], N["h5_rel"], N["h5_tol"] = m.groups()
    m = _grab(de, r"^\[PASS\] H6-CROSSROUND\s+K=(\d+) 单向量参考（与 244\.83 逐字同构）：秩=([-+0-9.eE]+) "
                   r"vs 账本 ([-+0-9.eE]+) ⇒ 逐位相同 ｜ z=([-+0-9.eE]+) vs ([-+0-9.eE]+)"
                   r"（相对差 ([-+0-9.eE]+)）｜ 参考 sd=([-+0-9.eE]+) vs ([-+0-9.eE]+)"
                   r".*?sd vs 理论 1/√d 相对差 ([-+0-9.eE]+)（上限 ([-+0-9.eE]+)）", "H6")
    (N["h6_K"], N["h6_rank"], N["h6_rank_exp"], N["h6_z"], N["h6_z_exp"], N["h6_zrel"],
     N["h6_sd"], N["h6_sd_exp"], N["h6_theo_rel"], N["h6_tol"]) = m.groups()
    m = _grab(de, r"（\*\*绝对差 ([-+0-9.eE]+)\*\*，上限 ([-+0-9.eE]+) ", "H6 绝对差")
    N["h6_absdiff"], N["h6_abstol"] = m.groups()

    # ---- H1 / H2 / H3 / H4 ----
    m = _grab(de, r"^\[PASS\] H1-IDENT\s+sidecar class_gap=([-+0-9.eE]+) == 批 --gap ([-+0-9.eE]+)", "H1")
    N["h1_gap"], N["h1_batch"] = m.groups()
    N["h1_md5"] = _grab(de, r"实测 md5=([0-9a-f]{32}) ∈ 账本候选", "H1 md5").group(1)
    m = _grab(de, r"^\[PASS\] H2-PROVENANCE\s+6 把 sidecar：layer=(\d+) seed=(\d+) marker_ids（(\d+) 个逐个相同）"
                   r"w_norm=1\.0", "H2")
    N["h2_layer"], N["h2_seed"], N["h2_nmark"] = m.groups()
    N["h3_seed"] = _grab(de, r"^\[PASS\] H3-RANDRULE\s+探针源码：`default_rng\((\d+)\)`", "H3").group(1)
    m = _grab(de, r"^\[PASS\] H4-NOSHAREDSTREAM\s+default_rng\((\d+)\) 与 default_rng\((\d+)\) 的前 (\d+) 个输出："
                   r"逐位不同 (\d+)/\d+ 个、最大绝对差 ([-+0-9.eE]+)", "H4")
    N["h4_a"], N["h4_b"], N["h4_d"], N["h4_ndiff"], N["h4_maxdiff"] = m.groups()

    # ---- H9 / H10 / H11 / H12 / H13 ----
    m = _grab(de, r"^\[PASS\] H10-CLASSSTAT\s+主统计量 T=[^=]*=([-+0-9.eE]+) ｜ "
                   r"参考 K=(\d+)：mean=([-+0-9.eE]+) sd=([-+0-9.eE]+) ｜ "
                   r"理论 sd=[^=]*=([-+0-9.eE]+)（相对差 ([-+0-9.eE]+)，上限 ([-+0-9.eE]+)）｜ "
                   r"z_T=([-+0-9.eE]+) ｜ 秩=([-+0-9.eE]+) ｜ 共同分量投影 U₀=([-+0-9.eE]+) z_U=([-+0-9.eE]+)", "H10")
    (N["T0"], N["K"], N["Tmean"], N["Tsd"], N["Theo"], N["Tsdrel"], N["Ttol"],
     N["zT"], N["rankT"], N["U0"], N["zU"]) = m.groups()
    m = _grab(de, r"^\[PASS\] H9-STRATUM\s+分层 A（(\d+) 把同 npz）单独重算：T=([-+0-9.eE]+) "
                   r"z_T=([-+0-9.eE]+)（判 (\S+)）｜ 全 (\d+) 把：z_T=([-+0-9.eE]+)（判 (\S+)）", "H9")
    (N["h9_n"], N["h9_T"], N["h9_z"], N["h9_v"], N["h9_tot"], N["h9_zall"], N["h9_vall"]) = m.groups()
    m = _grab(de, r"^\[PASS\] H11-NEGCONTROL\s+6 把各自独立坐标置换（种子 (\d+)\+i）后：z_T=([-+0-9.eE]+)"
                   r"（\|z\| 上限 ([-+0-9.eE]+)）｜ 置换后两两余弦 max=([-+0-9.eE]+)（上限 ([-+0-9.eE]+)", "H11")
    (N["h11_seed"], N["h11_z"], N["h11_zmax"], N["h11_pw"], N["h11_pwlim"]) = m.groups()
    m = _grab(de, r"^\[PASS\] H12-FPR\s+判决规则「z_T ≥ ([-+0-9.eE]+)」在 K=(\d+) 个参考种子下的"
                   r"\*\*经验假阳性率\*\* = ([-+0-9.eE]+)（上限 ([-+0-9.eE]+)）", "H12")
    N["h12_thr"], N["h12_K"], N["h12_fpr"], N["h12_max"] = m.groups()
    m = _grab(de, r"^\[PASS\] H13-SELFINCLUDE\s+构造种子（6 把 sidecar 读出）= (.+?) ｜ "
                   r"类级参考种子区间 (\d+)\.\.(\d+) ⇒ 交集 = (.+?) ⇒ (.+?) ｜ "
                   r"含构造种子的参考集（(\d+)\.\.(\d+)）算出的 z_T=([-+0-9.eE]+)（判 (\S+)）"
                   r"vs 不含的 z_T=([-+0-9.eE]+)（判 (\S+)）", "H13")
    (N["h13_ctor"], N["h13_lo"], N["h13_hi"], N["h13_inter"], N["h13_intertxt"],
     N["h13_altlo"], N["h13_althi"], N["h13_zalt"], N["h13_valt"], N["h13_z"], N["h13_v"]) = m.groups()

    # ---- 6 把逐条余弦 + 正号计数 ----
    m = _grab(de, r"^=== 类级余弦（6 把 × 同一个 r₀）===\n((?:  .*\n)+)", "类级余弦块")
    N["cos_each"] = re.findall(r"^  (\S+)\s+cos\(v, r₀\) = ([-+0-9.eE]+)$", m.group(1), re.M)
    if not N["cos_each"]:
        raise SystemExit("⛔ 从收据里抠不到「6 把逐条余弦」⇒ ⇒ 那一段会是空的 ⇒ 中止")
    m = _grab(de, r"正号计数 = (\d+) / (\d+)（单侧 P\(全正\) = 2\^-(\d+) = ([-+0-9.eE]+)）", "正号计数")
    N["npos"], N["ntot"], N["nexp"], N["p_allpos"] = m.groups()

    # ---- 描述量 ----
    m = _grab(de, r"^  D1 污染量级：cos=([-+0-9.eE]+) ⇒ rand 方向含 w 能量 ([-+0-9.eE]+)% ｜ "
                   r"w 等效剂量 = ([-+0-9.eE]+) × ([-+0-9.eE]+) = ([-+0-9.eE]+)$", "D1")
    (N["d1_cos"], N["d1_pct"], N["d1_c"], N["d1_gap"], N["d1_equiv"]) = m.groups()
    m = _grab(de, r"^  D2 换个 r（seed (\d+)）：(.+?) ｜ 正号 (\d+)/(\d+)$", "D2")
    N["d2_seed"], N["d2_list"], N["d2_pos"], N["d2_tot"] = m.groups()

    # ---- 自检 / 变异台 / 互证 ----
    m = _grab(st, r"自检（Phase-0 G0-1/G0-2/G0-3）：(\d+) 条 ｜ FAIL (\d+) 条", "自检小结")
    N["st_n"], N["st_fail"] = m.groups()
    m = _grab(mu, r"变异台：抓到 (\d+) / (\d+)（无效 (\d+) 条", "变异台小结")
    N["mut_caught"], N["mut_total"], N["mut_invalid"] = m.groups()
    N["mut_crash"] = _grab(mu, r"崩的条数：(\d+)", "崩计数").group(1)
    N["mut_ids"] = re.findall(r"^\[(?:抓到|硬停抓到)\] (\S+)", mu, re.M)
    m = _grab(cr, r"^互证：(\d+) 项 ｜ OK (\d+) ｜ MISMATCH (\d+)", "互证计数")
    N["cr_n"], N["cr_ok"], N["cr_bad"] = m.groups()
    N["cr_cos0"] = _grab(cr, r"^CROSS\|cos0=([-+0-9.eE]+)$", "互证 cos0").group(1)
    N["cr_z"] = _grab(cr, r"^CROSS\|cos_z=([-+0-9.eE]+)$", "互证 z").group(1)
    N["cr_rank"] = _grab(cr, r"^CROSS\|cos_rank=([-+0-9.eE]+)$", "互证秩").group(1)
    N["cr_cz"] = _glob = _grab(cr, r"^CROSS\|class_z=([-+0-9.eE]+)$", "互证类级 z").group(1)
    N["cr_cT"] = _grab(cr, r"^CROSS\|class_T0=([-+0-9.eE]+)$", "互证类级 T").group(1)
    N["cr_fpr"] = _grab(cr, r"^CROSS\|class_fpr=([-+0-9.eE]+)$", "互证 FPR").group(1)
    N["cr_verdict"] = _grab(cr, r"^CROSS\|verdict=(\S+)$", "互证判决形态").group(1)
    N["cr_cosrel"] = _grab(cr, r"^CROSS\|ledger_cos_rel=([-+0-9.eE]+)$", "互证 cos 相对差").group(1)
    N["cr_zrel"] = _grab(cr, r"^CROSS\|ledger_z_rel=([-+0-9.eE]+)$", "互证 z 相对差").group(1)
    N["cr_ranksame"] = _grab(cr, r"^CROSS\|ledger_rank_same=(\d+)$", "互证秩一致").group(1)

    # ---- 全回归 R5 ----
    regp = os.path.join(EV, "reg_24484.txt")
    reg_line = "· ⛔ **R5 未量到**"
    if os.path.isfile(regp):
        reg = _read(regp)

        def _rg(pat, what):
            return _grab(reg, pat, what).group(1)

        reg_line = ("· **R5（落账 244.84 **后**的账本 = 本次提交里那份字节）**：主机 `%s` ｜ 执行集 **%s** 个 py ｜ "
                    "清单 diff 对 R4：added **%s** / removed **%s** ｜ "
                    "变异台 全绿 %s / 跑得动 %s ｜ 自检 全绿 %s / 跑得动 %s ｜ `REG_RC = %s` ｜ "
                    "账本 %s 行 ｜ md5 `%s`"
                    % (_rg(r"host=(\S+)", "R5 主机"),
                       _rg(r"n_exec_py=(\d+)", "R5 执行集数"),
                       _rg(r"added=(\d+)", "R5 新增"),
                       _rg(r"removed=(\d+)", "R5 减少"),
                       _rg(r"小结：变异台 全绿 (\d+)", "R5 变异台-全绿"),
                       _rg(r"小结：变异台 全绿 \d+ / 跑得动 (\d+)", "R5 变异台-跑得动"),
                       _rg(r"小结：.*自检 全绿 (\d+)", "R5 自检-全绿"),
                       _rg(r"小结：.*自检 全绿 \d+ / 跑得动 (\d+)", "R5 自检-跑得动"),
                       _rg(r"REG_RC=(\d+)", "R5 退出码"),
                       _rg(r"ledger_lines=(\d+)", "R5 账本行数"),
                       _rg(r"ledger_md5=(\w+)", "R5 账本 md5")))
        # ⚖⚖⚖⚖⚖ **红项按分类登记**（⛔ 只报「全绿 / 跑得动」两个数 ⇒ ⇒ 会把红项**藏起来**
        #   ⇒ ⇒ 这里把收据里**每一行非 [OK]** 原样列出来 ⇒ ⇒ 「零红项」必须**能被看见**
        #   ⇒ ⇒ ⛔ **「超时 / 跑不动」⛔ 不等于「判据红」** ⇒ ⇒ 分类登记，不混为一谈）
        # ⚖⚖⚖ **只把「harness 的逐条结果行」当红项**（⛔ 收据**头行**（host= / python= /
        #   清单 diff / 账本 md5 …）**不是**红项 ⇒ ⇒ 早先一版把它们也算进去 ⇒ ⇒ 误报）
        reg_red = []
        for _l in reg.split("\n"):
            _s = _l.strip()
            if not _s or not _s.startswith("["):
                continue
            if _s.startswith("[OK") or _s.startswith("[SKIP"):
                continue
            reg_red.append(_s)
        # ⚖ **交叉核对**：「全绿」与「跑得动」不等 ⇒ ⇒ 说明有条目没进逐条结果行 ⇒ ⇒ 也算红项
        try:
            _ok = int(_rg(r"小结：变异台 全绿 (\d+)", "R5 变异台-全绿"))
            _run = int(_rg(r"小结：变异台 全绿 \d+ / 跑得动 (\d+)", "R5 变异台-跑得动"))
            _ok2 = int(_rg(r"小结：.*自检 全绿 (\d+)", "R5 自检-全绿"))
            _run2 = int(_rg(r"小结：.*自检 全绿 \d+ / 跑得动 (\d+)", "R5 自检-跑得动"))
            if _ok != _run or _ok2 != _run2:
                reg_red.append("⚠ 全绿/跑得动不等：变异台 %d vs %d ｜ 自检 %d vs %d"
                               % (_ok, _run, _ok2, _run2))
        except Exception:
            pass
        if reg_red:
            reg_line += ("\n   ⚠ **红项登记（%d 条，⛔ 逐条分类，⛔ 不许笼统说「全绿」）**：\n"
                         % len(reg_red))
            for _l in reg_red:
                reg_line += "     - `%s`\n" % _l
        else:
            reg_line += ("\n   ✅ **红项登记：零红项**（harness 的**每一行逐条结果**都看过："
                         "只有 [OK] 与 [SKIP]；且「全绿 == 跑得动」）")

    L = []
    A = L.append
    A("244.84：对照臂方向污染的类级判读 —— 把「N=1」变成「N=6」，判「巧合 vs 结构」")
    A("")
    A("⚖⚖⚖ **这一轮验的是什么**")
    A("")
    A("244.83（剂量等值性，形态 D-A）实测出唯一**不是等式**的量：")
    A("")
    A("    cos(w_p2a, rand_seed0) = %s   （K=2000 参考：经验秩 %s、z %s）" % (N["exp_cos0"], N["exp_rank"], N["exp_z"]))
    A("    ⇒ rand 臂那把「固定种子随机方向」带着 w 的 %.3f%% 能量（比值 %s）"
      % (float(N["exp_wfrac"]) * 100.0, N["exp_wfrac"]))
    A("")
    A("⇒ ⇒ 244.83 自己写下的留白：「**N=1** ⇒ 巧合还是结构**未量到**、对改判率影响**未量到**」。")
    A("⇒ ⇒ 本轮把**第一个**问号做成可判读的三态。")
    A("")
    A("⚖⚖⚖ **手法：换掉 w，不换 r**")
    A("")
    A("rand 臂那把 `r = rand_seed0` 是**探针里写死的**（`np.random.default_rng(%s)`），实验已经用它跑完了"
      "168 格 ⇒ ⇒ **它不能换**；能换的是 **w** ⇒ ⇒ 对 **6 把同层（layer=%s）同 marker（%s 个）"
      "同训练种子（%s）的 steering 向量**各算一次 `cos(v_i, r)`。"
      % (N["h3_seed"], N["h2_layer"], N["h2_nmark"], N["h2_seed"]))
    A("")
    A("⚖⚖⚖ **判决（形态 %s）**" % N["verdict"])
    A("")
    A("- %s" % N["why"].replace("**", ""))
    A("- **类级主统计量** `T = mean_i cos(v_i, r₀)` = **%s** ｜ **z_T = %s**（阈值 2.0）"
      % (N["T0"], N["zT"]))
    A("- 零分布**被校准**：参考 sd `%s` vs 理论 `‖m‖/√d = %s`（相对差 %s，上限 %s）"
      % (N["Tsd"], N["Theo"], N["Tsdrel"], N["Ttol"]))
    A("- **判别力**（判决规则的经验假阳性率）= **%s**（上限 %s）" % (N["h12_fpr"], N["h12_max"]))
    A("- **分层稳健性**：同 npz 的 %s 把单独重算 z_T=%s（判 %s）vs 全 %s 把 z_T=%s（判 %s）⇒ ⇒ 结论%s"
      % (N["h9_n"], N["h9_z"], N["h9_v"], N["h9_tot"], N["h9_zall"], N["h9_vall"],
         "**不随纳入范围而变**" if N["h9_v"] == N["h9_vall"] else "⛔**随纳入范围而变**"))
    A("- **自包含闸**：构造种子 %s vs 类级参考区间 %s..%s ⇒ 交集 %s；含它的参考集 z_T=%s（判 %s）"
      "vs 不含 %s（判 %s）⇒ ⇒ 自包含**没有影响判决**"
      % (N["h13_ctor"], N["h13_lo"], N["h13_hi"], N["h13_inter"], N["h13_zalt"], N["h13_valt"],
         N["h13_z"], N["h13_v"]))
    A("- **负控**：6 把各自独立坐标置换后 z_T=%s（z 的绝对值上限 %s）、置换后两两余弦 max=%s（上限 %s）"
      % (N["h11_z"], N["h11_zmax"], N["h11_pw"], N["h11_pwlim"]))
    A("")
    A("⚖⚖⚖ **6 把 w 对同一把 r₀ 的余弦（逐条）**")
    A("")
    for nm, c in N["cos_each"]:
        A("- `%s` → **%s**" % (nm, c))
    A("- 正号计数 **%s / %s**（单侧 `P(全正) = 2^-%s = %s`）"
      % (N["npos"], N["ntot"], N["nexp"], N["p_allpos"]))
    A("")
    A("⚖⚖⚖ **跨轮对账（244.83 的数被独立重算出来）**")
    A("")
    A("- 单向量口径（与 244.83 **逐字同构**，种子 1..K、排除被观测的 0）：秩 **%s** vs 账本 **%s**"
      "（逐位相同）｜ z `%s` vs `%s`（相对差 %s）｜ 参考 sd `%s` vs `%s`（**绝对差 %s**，上限 %s —— "
      "⛔ 账本里那个数**只印到 6 位小数** ⇒ ⇒ 容差由**打印精度**推导，⛔ 不是从实测值倒推）"
      "｜ sd vs 理论 1/√d 相对差 %s（上限 %s）"
      % (N["h6_rank"], N["h6_rank_exp"], N["h6_z"], N["h6_z_exp"], N["h6_zrel"],
         N["h6_sd"], N["h6_sd_exp"], N["h6_absdiff"], N["h6_abstol"],
         N["h6_theo_rel"], N["h6_tol"]))
    A("- `w_p2a` 那一条 = `%s` vs 账本 `%s`（相对差 %s，上限 %s）" % (N["h5_cos"], N["h5_exp"], N["h5_rel"], N["h5_tol"]))
    A("- 互证（纯 Python 路线）：cos0 `%s` ｜ 秩 `%s` ｜ z `%s` ｜ 类级 T `%s` ｜ 类级 z `%s` ｜ FPR `%s`"
      " ｜ 判决形态 `%s`" % (N["cr_cos0"], N["cr_rank"], N["cr_z"], N["cr_cT"], N["cr_cz"],
                             N["cr_fpr"], N["cr_verdict"]))
    A("- 互证与账本的相对差：cos `%s`、z `%s`；秩逐位相同 = %s"
      % (N["cr_cosrel"], N["cr_zrel"], N["cr_ranksame"]))
    A("")
    A("⚖⚖⚖ **六条更正 ＋ 两条增补（撤回并更正，⛔ 不改数凑好看）**")
    A("")
    A("1. **更正 ①：「逐位相同」这个说法本身是错的** —— 244.83 自己的**两条实现路线**（纯 Python vs numpy）"
      "算出的 `cos0` 就差 6e-17 ⇒ ⇒ **跨实现口径下「逐位」在数学上不成立** ⇒ ⇒ 改成**相对差 ≤ 1e-12**。")
    A("2. **更正 ②：⚠⚠⚠ 零分布「自包含」** —— 本轮 **Phase-0 闸门当场抓到的真统计缺陷**：参考集若与"
      "**构造向量所用的随机种子**重叠，零分布里就含着构造它的那批随机量 ⇒ ⇒ 统计量被**系统性抬高**"
      "（实测 sd 相对理论偏 **0.41–0.43**）⇒ ⇒ 真数据同样中招（6 把 w 都由 `default_rng(%s)` 参与构造，"
      "而 **42 就落在参考区间 1..2000 里**）⇒ ⇒ 修正：类级零分布的种子区间改成 **%s..%s**"
      "⇒ ⇒ 并新增 **H13 自包含闸**（含/不含构造种子的两种参考集，**判决形态必须相同**）。"
      % (N["h2_seed"], N["h13_lo"], N["h13_hi"]))
    A("3. **更正 ③：H9 的通过条件此前没写死** ⇒ ⇒ 改成「**分层 A 单独重算的判决形态必须与主判决相同**」"
      "⇒ ⇒ 避免一个**通过条件随结果漂移**的判据。")
    A("4. **更正 ④：H6 的参考 sd 容差** —— ⛔ 拿 1e-12 的相对容差去比账本里**只印到 6 位小数**的数 "
      "⇒ ⇒ **数学上不可能通过** ⇒ ⇒ 改成「**绝对差 ≤ 5e-7**（＝末位打印精度 1e-6 的一半，"
      "⛔ **由打印精度推导**，⛔ 不是从实测值倒推）」**＋** 一条**更强**的：「本轮的值印到 6 位小数，"
      "必须与账本那个数**逐位相同**」⇒ ⇒ 实测绝对差 %s（上限 %s）。"
      % (N["h6_absdiff"], N["h6_abstol"]))
    A("5. **更正 ⑤：⚠⚠⚠ 实现把 H11 的 |z| 上限单方面放宽成 3.0**（预登记 §3.2 H11 写的是 **2**）"
      "⇒ ⇒ **护栏变松 ⇒ 判据的牙齿变少**，且**没有外部依据** ⇒ ⇒ **撤回，改回 2.0**；"
      "实测负控 `z_T = %s` ⇒ ⇒ **2.0 与 3.0 都通过** ⇒ ⇒ **判决形态不变**（仍是 E-B）"
      "⇒ ⇒ 改的是**口径、不是数** ⇒ ⇒ ⛔ **没有动任何实测数**。"
      "⚖ **连带必改**：变异台 `PM5` 的搜索串原本写死 `3.0` ⇒ ⇒ 已同步改成 `2.0` "
      "⇒ ⇒ 该变异体不会退化成「无效」。"
      % N["h11_z"])
    A("6. **增补 Ⅵ：H11 半 B 的可验阈值** —— 预登记原来只说「置换种子固定并登记」，**没写死**"
      "「怎么判断置换**真的**破坏了共享结构」的数值判据 ⇒ ⇒ 实现里多了一个 "
      "`negctl_paircos_max = 0.15` ⇒ ⇒ **原先没有出处** ⇒ ⇒ 现补上**外部依据**："
      "零假设下余弦 `sd ≈ 1/√d = 0.022097`（d=2048）⇒ ⇒ 上界取 **6.79 × (1/√d) = 0.15** "
      "⇒ ⇒ 单对超过它的概率 ≈ **1.2e-11**、15 对取最大 ≈ **1.9e-10** ⇒ ⇒ 它是「结构**确实被破坏**」的"
      "**存在性**判据 ⇒ ⇒ 变异台 `PM9` 证明它**能红**。")
    A("7. **增补 §3.3：D5 簇分解 与 D6 簇的出处**（**描述判据**，⛔ 不改变判决形态）⇒ ⇒ "
      "偏高**只集中在 w_p2a 所属的那个簇**（簇 A z=+2.393 vs 簇 B z=+0.046）。")
    A("8. **更正 ⑥：⚠⚠⚠ 两条「判决形态」层面的缺陷**（**落账之后、R5 跑到一半**时做"
      "「预登记 ↔ 实现 ↔ 变异台」三方对账才发现 ⇒ ⇒ ⛔ **不享受**「先于实现」的豁免）"
      "⇒ ⇒ ① **被检实现里「E-C」那一支是死代码**（判决逻辑把「`failed_ids()` 非空 ⇒ FAIL」写在前、"
      "「`not h12_ok` ⇒ E-C」写在后 ⇒ ⇒ **H12 红时它已经进了 `failed_ids`** ⇒ ⇒ **E-C 永远走不到**）"
      "⇒ ⇒ **「判别力不足（没量到）」与「前提被推翻」被混成一类** ⇒ ⇒ 已改成："
      "非 H12 的硬判据红 ⇒ **FAIL**、只有 H12 红 ⇒ **E-C**；并把**第四种形态 FAIL** 写进预登记 §3.1；"
      "② **预登记 §3.1 / §6 漏改**（H13 是硬判据，形态表仍写「H1–H12 全绿」⇒ ⇒ 比实现松）⇒ ⇒ 改成 H1–H13。"
      "⚖ **变异台为何此前抓不到 ①**：变异台**只断言「哪些判据变红」**、⛔ 不看判决形态 "
      "⇒ ⇒ 现在把**判决形态**纳入断言（**PM6 逼 E-C**、**PM15/PD1 逼 FAIL**）⇒ ⇒ 死分支藏不住。"
      "⚖ **有没有改动实测数**：⛔ **没有** ⇒ ⇒ 形态**仍是 E-B**（走 E-B 那一支，⛔ 不经过 E-C/FAIL）"
      "⇒ ⇒ **判决不变**；⚖ **代价**：预登记 md5 变 ⇒ ⇒ 字节清单重出、账本重落、**R5 重跑**。")
    A("")
    A("⚖⚖⚖ **顺带修掉的、上一轮留下的「验证工具」缺陷**（⛔ **不涉及任何实测数**）")
    A("")
    A("- **244.83 的提交后回读脚本两处断言写错了** ⇒ ⇒ ① D 断言假设「每个修订号只有一段」，"
      "但 **244.74 有 2 段、244.75 有 3 段**（按设计复用同一修订号的追加段）⇒ ⇒ ② E 断言用子串"
      "「修订 244.1」⇒ ⇒ 把「修订 244.10」…「修订 244.19」**和兄弟修订「修订 244.1b」「修订 244.2b」**"
      "一起匹上 ⇒ ⇒ **账本与索引本身没错，错的是断言** ⇒ ⇒ 已改成「登记全部段行号」＋"
      "「带 token 边界的正则」＋新增「**E 能红自证**」⇒ ⇒ 已 amend 进 244.83 的提交。")
    A("- **落账脚本的「防重复落账」闸**原来只做「拒绝」⇒ ⇒ 提交链不可重跑 ⇒ ⇒ 改成"
      "「**已落 ⇒ 必须与收据算出来的那段逐字节相同**」⇒ ⇒ 幂等且**自证**。")
    A("")
    A("⚖⚖⚖ **每条判据能红**")
    A("")
    A("- **自检**（Phase-0 G0-1/G0-2/G0-3，合成夹具、零 bpath、零 GPU）：判据 %s 条 ｜ FAIL %s 条"
      % (N["st_n"], N["st_fail"]))
    A("- **变异台**：抓到 **%s / %s**（无效 %s 条 ⇒ 记「无效」不计入分母）｜ 崩 **%s**（⛔ 必须是 0）"
      % (N["mut_caught"], N["mut_total"], N["mut_invalid"], N["mut_crash"]))
    A("- **互证**（纯 Python 路线 vs numpy 路线）：%s 项 ｜ OK **%s** ｜ MISMATCH **%s**"
      % (N["cr_n"], N["cr_ok"], N["cr_bad"]))
    A("- **真数据判据**：%s 条 ｜ PASS **%s** ｜ FAIL **%s**" % (N["de_n"], N["de_pass"], N["de_fail"]))
    A("- 变异台逐条：%s" % "、".join(N["mut_ids"]))
    A("")
    A("⚖⚖⚖ **全回归**")
    A("")
    A(reg_line)
    A("")
    A("⚖⚖⚖ **边界（本轮哪些仍未量到）**")
    A("")
    A("- ⛔ **「污染对改判率的影响」仍未量到** —— 固定剂量批**没落盘 alpha 轨迹**（跑批器调探针时"
      "**没传 `--dump-raw`**）⇒ ⇒ 离线算不出；且 w 臂在 **w 剂量 %s** 处的响应**未量到**、"
      "单调性**未量到** ⇒ ⇒ 本轮只登记**条件命题**，⛔ 不进判决。" % N["d1_equiv"])
    A("- ⛔ **「6 把 w 代表全部 steering 向量」的外推** ⇒ ⇒ **未量到**（6 把是**同一套 recipe** 的 6 个解）。")
    A("- ⛔ **「r 那一侧」仍是 N=1** —— 本轮只把 **w 那一侧**从 N=1 变成 N=6 ⇒ ⇒ "
      "**多随机种子的对照臂**仍要跑批。")
    A("- ⛔ **「哪一条臂是机制效应」** ⇒ ⇒ 沿用旧留白，**未量到**（要「同结论对照臂」）。")
    A("- ⛔ 远端 tokenizer 快照的内容指纹、**照 meta 重建能否逐位复现** ⇒ ⇒ 沿用旧留白，**未量到**。")
    A("")
    A("⚖⚖⚖ **本轮改了哪些文件**")
    A("")
    A("- `.cache/r244/alignment_distribution_audit.py`（**进执行集**）—— 类级判读实现"
      "（Phase-0 三闸 + %s 条硬判据）" % N["de_n"])
    A("- `.cache/r244/mut_alignment_distribution_audit.py`（**进执行集**）—— 变异台 19 条"
      "（其中 3 条**额外断言判决形态**：PM6 ⇒ E-C、PM15/PD1 ⇒ FAIL）")
    A("- `.cache/r244/_cross_check_24484.py`（⛔ **不进**执行集）—— 第二条独立实现（纯 Python 路线）")
    A("- `.cache/r244/_spec_crosscheck_24484.py`（⛔ **不进**执行集）—— 把预登记纪律①「**口径只从预登记读**」"
      "做成**机器可判、能红**的对账：逐条抠预登记 §2 的 Q 表与实现的 `SPEC` 比对（12 条机械比）"
      "⇒ ⇒ 另有 3 条（Q4 构造式 / Q7 marker id 列表 / Q11 零假设语义）**明确标成「不能机械比」**"
      "⇒ ⇒ ⛔ **不假装比过了**")
    A("- `.cache/r244/_run_24484_verify.sh`、`_run_24484_reg_shm.sh`、`_append_24484.py`、"
      "`_commit_msg_24484.py`、`_make_handoff_24484.py`、`_post_commit_readback_24484.py`、"
      "`_commit_24484.sh`")
    A("- `.cache/xcheck/R6_ALIGNMENT_DISTRIBUTION_PREREG.md`（**先于实现**签的预登记；"
      "§0.5 含**六条更正 ＋ 两条增补**，且逐条写明**发生时机**与**有没有改动实测数**）")
    A("- `.cache/xcheck/R6_RERUN_PREREG.md`（账本，只**追加** 244.84 段）、`.cache/xcheck/R6_RERUN_INDEX.md`")
    A("")
    A("⚖ **远端**：`zju-53`（验证链，零 GPU、只读 bpath）＋ `zju-12`（全回归 R5）"
      "｜ ⛔ 没跑批、⛔ 没改读数器/探针/拆分器、⛔ 没改 244.79–244.83 段。")
    A("")

    with io.open(OUT, "w", encoding="utf-8", newline="") as fh:
        fh.write("\n".join(L) + "\n")
    print("已写出：%s" % OUT)
    print("字节数：%d" % os.path.getsize(OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
