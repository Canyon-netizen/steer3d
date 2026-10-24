#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⚖ **244.84 落账**（只追加；⛔ 追加段里不许有围栏；⛔ 所有数都从收据抠，⛔ 不手抄）。

**这一段记什么**：把 244.83 结论形态 D-A 唯一那个留白口——

    「N=1 ⇒ 巧合还是结构**未量到**、对改判率影响**未量到**」

——里的**第一个**问号做成可判读的三态（E-A / E-B / E-C）。

⚖ **口径真相源**：`.cache/xcheck/R6_ALIGNMENT_DISTRIBUTION_PREREG.md`（244.84 签，**先于实现**）
⚖ **数据**：bpath 的 6 把 w 向量 ＋ 各自 sidecar ＋ 探针 ＋ 跑批器 ＋ 两臂日志
   （⛔ 只读、⛔ 零 GPU、远端 `zju-53`）
⚖ **收据**：`.cache/r244/_e24484/{selftest,de,mut,cross}.out`
"""

import hashlib
import io
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
LEDGER = os.path.join(REPO, ".cache", "xcheck", "R6_RERUN_PREREG.md")
EV = os.path.join(REPO, ".cache", "r244", "_e24484")
DEV = os.path.join(REPO, ".cache", "r244")
XCH = os.path.join(REPO, ".cache", "xcheck")
TITLE = "## 修订 244.84 —— "

# ⚖⚖⚖ **这一轮的字节清单**（本地路径，⛔ md5 **由文件本身算出**）
ROUND_FILES = [
    ("alignment_distribution_audit.py", os.path.join(DEV, "alignment_distribution_audit.py")),
    ("mut_alignment_distribution_audit.py", os.path.join(DEV, "mut_alignment_distribution_audit.py")),
    ("_cross_check_24484.py", os.path.join(DEV, "_cross_check_24484.py")),
    ("_run_24484_verify.sh", os.path.join(DEV, "_run_24484_verify.sh")),
    ("R6_ALIGNMENT_DISTRIBUTION_PREREG.md",
     os.path.join(XCH, "R6_ALIGNMENT_DISTRIBUTION_PREREG.md")),
]


def _md5_file(path):
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


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
    """⚖ 全部数**从收据抠**（⛔ 不手抄）。"""
    st = _need(os.path.join(EV, "selftest.out"))
    de = _need(os.path.join(EV, "de.out"))
    mu = _need(os.path.join(EV, "mut.out"))
    cr = _need(os.path.join(EV, "cross.out"))
    rc = _need(os.path.join(EV, "receipt.txt"))

    N = {}

    # ---- 自检（Phase-0）----
    m = _grab(st, r"自检（Phase-0 G0-1/G0-2/G0-3）：(\d+) 条 ｜ FAIL (\d+) 条", "自检小结")
    N["st_n"], N["st_fail"] = m.groups()
    N["st_gates"] = re.findall(r"^\[(PASS|FAIL)\]\s+(G0-\d)", st, re.M)

    # ---- 真数据：判决形态 ----
    m = _grab(de, r"^VERDICT=([EABC]-[ABC]|E-C|FAIL)$", "判决形态")
    N["verdict"] = m.group(1)
    m = _grab(de, r"^判决形态：(.+)$", "判决形态说明")
    N["verdict_why"] = m.group(1).strip()
    # ⚖ 剥出「E-B（…）」里的正文，并去掉它自带的 ** ⇒ ⇒ 免得 markdown 加粗嵌套破掉
    _b = N["verdict_why"]
    _mm = re.match(r"^[A-Z]-[A-Z]（(.*)）$", _b)
    N["verdict_why_body"] = (_mm.group(1) if _mm else _b).replace("**", "")
    m = _grab(de, r"^判据汇总：(\d+) 条 ｜ PASS (\d+) ｜ FAIL (\d+)$", "真数据判据小结")
    N["de_n"], N["de_pass"], N["de_fail"] = m.groups()
    N["de_ids"] = re.findall(r"^\[PASS\] (\S+)", de, re.M)

    # ---- 真数据：账本期望值与跨轮对账 ----
    m = _grab(de, r"^账本期望值（244\.83 段）：cos0=([-+0-9.eE]+) ｜ 秩=([-+0-9.eE]+) ｜ "
                   r"z=([-+0-9.eE]+) ｜ 参考 sd=([-+0-9.eE]+) ｜ w 能量占比=([-+0-9.eE]+)$",
             "账本期望值")
    N["exp_cos0"], N["exp_rank"], N["exp_z"], N["exp_sd"], N["exp_wfrac"] = m.groups()
    m = _grab(de, r"^账本 244\.78 段登记的 w_p2a\.npy md5 候选：(.+)$", "md5 候选")
    N["md5_cand"] = m.group(1).strip()

    # ---- H5：类级余弦 + 跨轮对账 ----
    m = _grab(de, r"^\[PASS\] H5-CLASSCOS\s+6 把对 r₀ 的余弦：(.+?) ｜ w_p2a 那一条 = ([-+0-9.eE]+) ｜ "
                   r"账本 244\.83 登记 = ([-+0-9.eE]+) ｜ 相对差 ([-+0-9.eE]+)（上限 ([-+0-9.eE]+)）",
             "H5")
    N["h5_cos_list"] = m.group(1)
    N["h5_cos"], N["h5_exp"], N["h5_rel"], N["h5_tol"] = m.group(2), m.group(3), m.group(4), m.group(5)

    # ---- H6：244.83 对账 ----
    m = _grab(de, r"^\[PASS\] H6-CROSSROUND\s+K=(\d+) 单向量参考（与 244\.83 逐字同构）：秩=([-+0-9.eE]+) "
                   r"vs 账本 ([-+0-9.eE]+) ⇒ 逐位相同 ｜ z=([-+0-9.eE]+) vs ([-+0-9.eE]+)"
                   r"（相对差 ([-+0-9.eE]+)）｜ 参考 sd=([-+0-9.eE]+) vs ([-+0-9.eE]+)"
                   r".*?sd vs 理论 1/√d 相对差 ([-+0-9.eE]+)（上限 ([-+0-9.eE]+)）", "H6")
    (N["h6_K"], N["h6_rank"], N["h6_rank_exp"], N["h6_z"], N["h6_z_exp"], N["h6_zrel"],
     N["h6_sd"], N["h6_sd_exp"], N["h6_theo_rel"], N["h6_tol"]) = m.groups()
    m = _grab(de, r"（\*\*绝对差 ([-+0-9.eE]+)\*\*，上限 ([-+0-9.eE]+) ", "H6 绝对差")
    N["h6_absdiff"], N["h6_abstol"] = m.groups()

    # ---- H10：类级主统计量 ----
    m = _grab(de, r"^\[PASS\] H10-CLASSSTAT\s+主统计量 T=[^=]*=([-+0-9.eE]+) ｜ "
                   r"参考 K=(\d+)：mean=([-+0-9.eE]+) sd=([-+0-9.eE]+) ｜ "
                   r"理论 sd=[^=]*=([-+0-9.eE]+)（相对差 ([-+0-9.eE]+)，上限 ([-+0-9.eE]+)）｜ "
                   r"z_T=([-+0-9.eE]+) ｜ 秩=([-+0-9.eE]+) ｜ 共同分量投影 U₀=([-+0-9.eE]+) z_U=([-+0-9.eE]+)",
             "H10")
    (N["T0"], N["K"], N["Tmean"], N["Tsd"], N["Theo"], N["Tsdrel"], N["Ttol"],
     N["zT"], N["rankT"], N["U0"], N["zU"]) = m.groups()

    # ---- H9：分层稳健性 ----
    m = _grab(de, r"^\[PASS\] H9-STRATUM\s+分层 A（(\d+) 把同 npz）单独重算：T=([-+0-9.eE]+) "
                   r"z_T=([-+0-9.eE]+)（判 ([A-Z]-[A-Z])）｜ 全 (\d+) 把：z_T=([-+0-9.eE]+)（判 ([A-Z]-[A-Z])）",
             "H9")
    (N["h9_n"], N["h9_T"], N["h9_z"], N["h9_v"], N["h9_tot"], N["h9_zall"], N["h9_vall"]) = m.groups()

    # ---- H11：负控 ----
    m = _grab(de, r"^\[PASS\] H11-NEGCONTROL\s+6 把各自独立坐标置换（种子 (\d+)\+i）后：z_T=([-+0-9.eE]+)"
                   r"（\|z\| 上限 ([-+0-9.eE]+)）｜ 置换后两两余弦 max=([-+0-9.eE]+)（上限 ([-+0-9.eE]+)",
             "H11")
    (N["h11_seed"], N["h11_z"], N["h11_zmax"], N["h11_pwmax"], N["h11_pwmax_lim"]) = m.groups()

    # ---- H12：判别力 ----
    m = _grab(de, r"^\[PASS\] H12-FPR\s+判决规则「z_T ≥ ([-+0-9.eE]+)」在 K=(\d+) 个参考种子下的"
                   r"\*\*经验假阳性率\*\* = ([-+0-9.eE]+)（上限 ([-+0-9.eE]+)）", "H12")
    N["h12_thr"], N["h12_K"], N["h12_fpr"], N["h12_max"] = m.groups()

    # ---- H13：自包含闸 ----
    m = _grab(de, r"^\[PASS\] H13-SELFINCLUDE\s+构造种子（6 把 sidecar 读出）= (.+?) ｜ "
                   r"类级参考种子区间 (\d+)\.\.(\d+) ⇒ 交集 = (.+?) ⇒ (.+?) ｜ "
                   r"含构造种子的参考集（(\d+)\.\.(\d+)）算出的 z_T=([-+0-9.eE]+)（判 ([A-Z]-[A-Z])）"
                   r"vs 不含的 z_T=([-+0-9.eE]+)（判 ([A-Z]-[A-Z])）", "H13")
    (N["h13_ctor"], N["h13_lo"], N["h13_hi"], N["h13_inter"], N["h13_inter_txt"],
     N["h13_alt_lo"], N["h13_alt_hi"], N["h13_z_alt"], N["h13_v_alt"], N["h13_z"], N["h13_v"]) = m.groups()

    # ---- H1：身份 ----
    m = _grab(de, r"^\[PASS\] H1-IDENT\s+sidecar class_gap=([-+0-9.eE]+) == 批 --gap ([-+0-9.eE]+)", "H1")
    N["h1_gap"], N["h1_batchgap"] = m.groups()
    m = _grab(de, r"实测 md5=([0-9a-f]{32}) ∈ 账本候选", "H1 md5")
    N["h1_md5"] = m.group(1)

    # ---- H2：出处 ----
    m = _grab(de, r"^\[PASS\] H2-PROVENANCE\s+6 把 sidecar：layer=(\d+) seed=(\d+) marker_ids（(\d+) 个逐个相同）"
                   r"w_norm=1\.0", "H2")
    N["h2_layer"], N["h2_seed"], N["h2_nmark"] = m.groups()

    # ---- H3 / H4 ----
    m = _grab(de, r"^\[PASS\] H3-RANDRULE\s+探针源码：`default_rng\((\d+)\)`", "H3")
    N["h3_seed"] = m.group(1)
    m = _grab(de, r"^\[PASS\] H4-NOSHAREDSTREAM\s+default_rng\((\d+)\) 与 default_rng\((\d+)\) 的前 (\d+) 个输出："
                   r"逐位不同 (\d+)/\d+ 个、最大绝对差 ([-+0-9.eE]+)", "H4")
    N["h4_a"], N["h4_b"], N["h4_d"], N["h4_ndiff"], N["h4_maxdiff"] = m.groups()

    # ---- 6 把逐条余弦 + 正号计数 ----
    m = _grab(de, r"^=== 类级余弦（6 把 × 同一个 r₀）===\n((?:  .*\n)+)", "类级余弦块")
    N["cos_block"] = m.group(1).rstrip("\n")
    N["cos_each"] = re.findall(r"^  (\S+)\s+cos\(v, r₀\) = ([-+0-9.eE]+)$", N["cos_block"], re.M)
    if not N["cos_each"]:
        raise SystemExit("⛔ 从收据里抠不到「6 把逐条余弦」⇒ ⇒ 那一段会是空的 ⇒ 中止")
    m = _grab(de, r"正号计数 = (\d+) / (\d+)（单侧 P\(全正\) = 2\^-(\d+) = ([-+0-9.eE]+)）", "正号计数")
    N["npos"], N["ntot"], N["nexp"], N["p_allpos"] = m.groups()

    # ---- 描述量 D1 / D2 ----
    m = _grab(de, r"^  D1 污染量级：cos=([-+0-9.eE]+) ⇒ rand 方向含 w 能量 ([-+0-9.eE]+)% ｜ "
                   r"w 等效剂量 = ([-+0-9.eE]+) × ([-+0-9.eE]+) = ([-+0-9.eE]+)$", "D1")
    (N["d1_cos"], N["d1_pct"], N["d1_c"], N["d1_gap"], N["d1_equiv"]) = m.groups()
    m = _grab(de, r"^  D2 换个 r（seed (\d+)）：(.+?) ｜ 正号 (\d+)/(\d+)$", "D2")
    N["d2_seed"], N["d2_list"], N["d2_pos"], N["d2_tot"] = m.groups()

    # ---- 变异台 ----
    m = _grab(mu, r"变异台：抓到 (\d+) / (\d+)（无效 (\d+) 条", "变异台小结")
    N["mut_caught"], N["mut_total"], N["mut_invalid"] = m.groups()
    m = _grab(mu, r"崩的条数：(\d+)", "崩计数")
    N["mut_crash"] = m.group(1)
    N["mut_ids"] = re.findall(r"^\[(?:抓到|硬停抓到)\] (\S+)", mu, re.M)
    N["mut_missed"] = re.findall(r"^\[没抓到\] (\S+)", mu, re.M)

    # ---- 收据：字节 md5（被检 / 口径与驱动 / bpath / 收据文件）----
    N["rc_host"] = _grab(rc, r"^host=(\S+)\s+date=", "收据主机").group(1)
    N["rc_rcs"] = _grab(rc, r"^SELFTEST_RC=(\d+)\s+DE_RC=(\d+)\s+MUT_RC=(\d+)\s+CROSS_RC=(\d+)$",
                        "收据退出码").groups()
    N["rc_md5"] = dict((v, k) for k, v in re.findall(r"^([0-9a-f]{32})\s+(\S+)$", rc, re.M))
    if not N["rc_md5"]:
        raise SystemExit("⛔ 收据里核不到任何字节 md5 ⇒ 字节清单无出处 ⇒ 中止")
    N["rc_md5_base"] = dict((os.path.basename(k), v) for k, v in N["rc_md5"].items())
    m = _grab(rc, r"^--- bpath 产物 md5 ---\n((?:[0-9a-f]{32}\s+\S+\n)+)", "bpath 字节块")
    N["rc_bpath"] = re.findall(r"^([0-9a-f]{32})\s+(\S+)$", m.group(1), re.M)
    m = _grab(rc, r"^--- 收据文件 md5 ---\n((?:[0-9a-f]{32}\s+\S+\n)+)", "收据文件字节块")
    N["rc_out"] = re.findall(r"^([0-9a-f]{32})\s+(\S+)$", m.group(1), re.M)

    # ---- 互证 ----
    m = _grab(cr, r"^互证：(.*)$", "互证小结")
    N["cr_summary"] = m.group(1).strip()
    N["cr_cos0"] = _grab(cr, r"^CROSS\|cos0=([-+0-9.eE]+)$", "互证 cos0").group(1)
    N["cr_z"] = _grab(cr, r"^CROSS\|cos_z=([-+0-9.eE]+)$", "互证 z").group(1)
    N["cr_rank"] = _grab(cr, r"^CROSS\|cos_rank=([-+0-9.eE]+)$", "互证秩").group(1)
    N["cr_class_z"] = _grab(cr, r"^CROSS\|class_z=([-+0-9.eE]+)$", "互证类级 z").group(1)
    N["cr_class_T"] = _grab(cr, r"^CROSS\|class_T0=([-+0-9.eE]+)$", "互证类级 T").group(1)
    N["cr_fpr"] = _grab(cr, r"^CROSS\|class_fpr=([-+0-9.eE]+)$", "互证 FPR").group(1)
    N["cr_verdict"] = _grab(cr, r"^CROSS\|verdict=(\S+)$", "互证判决形态").group(1)
    N["cr_ledger_cos_rel"] = _grab(cr, r"^CROSS\|ledger_cos_rel=([-+0-9.eE]+)$", "互证 cos 相对差").group(1)
    N["cr_ledger_z_rel"] = _grab(cr, r"^CROSS\|ledger_z_rel=([-+0-9.eE]+)$", "互证 z 相对差").group(1)
    N["cr_ledger_rank_same"] = _grab(cr, r"^CROSS\|ledger_rank_same=(\d+)$", "互证秩一致").group(1)
    m = _grab(cr, r"^互证：(\d+) 项 ｜ OK (\d+) ｜ MISMATCH (\d+)", "互证计数")
    N["cr_n"], N["cr_ok"], N["cr_bad"] = m.groups()
    return N


def build(N):
    """⚖ 组装追加段（⛔ **不许有围栏**、⛔ **不许有反斜杠**）。"""
    L = []
    A = L.append
    A(TITLE + "⚖⚖⚖⚖⚖ **「rand 臂那把固定随机方向为什么会带着 w 的 %.2f%% 能量」** "
      "—— ⇒ ⇒ **N=1 变成 N=6**（同一套 recipe 的 6 个解）⇒ ⇒ 判「**巧合 vs 结构**」"
      "⇒ ⇒ 判决形态 **%s**" % (float(N["exp_wfrac"]) * 100.0, N["verdict"]))
    A("")
    A("⚖ **口径真相源**：`.cache/xcheck/R6_ALIGNMENT_DISTRIBUTION_PREREG.md`（244.84 签，**先于实现**）")
    A("⚖ **数据**：bpath 的 6 把 w 向量 ＋ 各自 sidecar ＋ `r241_probe.py` ＋ `r244_warm_sweep.sh`"
      " ＋ 两臂原始日志（⛔ 只读、⛔ 零 GPU、远端 `zju-53`）")
    A("⚖ **接的是 244.83 的哪一句**：244.83 实测 `cos(w_p2a, rand_seed0) = %s`（K=2000 参考：秩 %s、z %s）"
      "⇒ ⇒ rand 臂那把随机方向**带着 w 的 %.3f%% 能量**（比值 %s）⇒ ⇒ 244.83 自己写下的留白："
      "「**N=1** ⇒ 巧合还是结构**未量到**」。"
      % (N["exp_cos0"], N["exp_rank"], N["exp_z"],
         float(N["exp_wfrac"]) * 100.0, N["exp_wfrac"]))
    A("")
    A("### 【1】⚖⚖⚖ **一句话**")
    A("")
    A("> **判决形态 %s** —— ⇒ ⇒ 「这个 2.7σ 是**单把 w 撞上单把随机向量**的巧合，还是"
      "『训练出来的 steering 向量与任意固定随机方向存在**系统性重叠**』的结构？」"
      "⇒ ⇒ **本轮把它判成 %s**（%s）。"
      % (N["verdict"], N["verdict"], N["verdict_why_body"]))
    A("")
    A("⚖⚖⚖ **手法（把 N=1 变成 N=6）**：**换掉 w，不换 r**。rand 臂那把 `r = rand_seed0` 是"
      "**探针里写死的**（`np.random.default_rng(0)`），实验已经用它跑完了 168 格 ⇒ ⇒ **它不能换**；"
      "能换的是 **w** ⇒ ⇒ 对 **6 把同层同 marker 同训练种子的 steering 向量**各算一次 `cos(v_i, r)`。")
    A("")
    A("### 【2】📊 **判决面板（类级）**")
    A("")
    A("| 量 | 值 | 判据 |")
    A("|---|---|---|")
    A("| **类级主统计量** `T = mean_i cos(v_i, r₀)` | **%s** | 6 把 w 对同一把 r₀ |" % N["T0"])
    A("| **z_T**（对参考种子分布） | **%s** | 判决阈值 2.0 ⇒ ⇒ %s |"
      % (N["zT"], "**离群 ⇒ 结构（E-B）**" if float(N["zT"]) >= 2.0 else "**未离群 ⇒ 巧合（E-A）**"))
    A("| 经验秩 / 参考 sd / 理论 sd=‖m‖/√d | %s / %s / %s | sd 相对差 %s（上限 %s）⇒ 零分布**被校准** |"
      % (N["rankT"], N["Tsd"], N["Theo"], N["Tsdrel"], N["Ttol"]))
    A("| **判别力**（判决规则的经验假阳性率） | **%s**（上限 %s） | H12 ⇒ ⇒ 规则%s |"
      % (N["h12_fpr"], N["h12_max"], "**可用**"))
    A("| **分层稳健性**（同 npz 的 %s 把单独重算） | z_T=%s（判 %s）vs 全 %s 把 z_T=%s（判 %s） | H9 ⇒ ⇒ 结论%s |"
      % (N["h9_n"], N["h9_z"], N["h9_v"], N["h9_tot"], N["h9_zall"], N["h9_vall"],
         "**不随纳入范围而变**" if N["h9_v"] == N["h9_vall"] else "⛔**随纳入范围而变**"))
    A("| **自包含闸**（构造种子 %s vs 类级参考区间 %s..%s） | 交集 %s ｜ 含它的参考集 z_T=%s（判 %s）vs 不含 %s（判 %s） | H13 ⇒ ⇒ %s |"
      % (N["h13_ctor"], N["h13_lo"], N["h13_hi"], N["h13_inter"], N["h13_z_alt"], N["h13_v_alt"],
         N["h13_z"], N["h13_v"], "自包含**没有影响判决**"))
    A("| **负控**（6 把各自独立坐标置换） | z_T=%s（z 的绝对值上限 %s）｜ 置换后两两余弦 max=%s（上限 %s） | H11 ⇒ ⇒ %s |"
      % (N["h11_z"], N["h11_zmax"], N["h11_pwmax"], N["h11_pwmax_lim"],
         "负控通过（无结构时**不该**触发）"))
    A("")
    A("### 【3】🔍 **6 把 w 对同一把 r₀ 的余弦（逐条）**")
    A("")
    for nm, c in N["cos_each"]:
        A("- `%s` → **%s**" % (nm, c))
    A("")
    A("- 正号计数 **%s / %s**（单侧 `P(全正) = 2^-%s = %s`）"
      % (N["npos"], N["ntot"], N["nexp"], N["p_allpos"]))
    A("")
    A("### 【4】✅ **判据与变异台（每条判据能红）**")
    A("")
    A("- **自检**（Phase-0 G0-1/G0-2/G0-3，合成夹具、零 bpath、零 GPU）：判据 %s 条 ｜ FAIL %s 条"
      % (N["st_n"], N["st_fail"]))
    A("- **变异台**：抓到 **%s / %s**（无效 %s 条 ⇒ 记「无效」⇒ 不计入分母）｜ 崩的条数 **%s**（⛔ 必须是 0）"
      % (N["mut_caught"], N["mut_total"], N["mut_invalid"], N["mut_crash"]))
    A("- **互证**（第二条独立实现，纯 Python 路线 vs numpy 路线）：%s 项 ｜ OK **%s** ｜ MISMATCH **%s**"
      % (N["cr_n"], N["cr_ok"], N["cr_bad"]))
    A("- **真数据判据**：%s 条 ｜ PASS **%s** ｜ FAIL **%s**" % (N["de_n"], N["de_pass"], N["de_fail"]))
    A("- 互证逐位：cos0 `%s` ｜ 秩 `%s` ｜ z `%s` ｜ 类级 T `%s` ｜ 类级 z `%s` ｜ FPR `%s`"
      % (N["cr_cos0"], N["cr_rank"], N["cr_z"], N["cr_class_T"], N["cr_class_z"], N["cr_fpr"]))
    A("- **跨轮对账**（纯 Python 路线 vs 账本里 244.83 的登记）：cos 相对差 `%s`、z 相对差 `%s`、"
      "秩**逐位相同**=%s ⇒ ⇒ 244.83 那个 0.0602 被**独立重算**出来了"
      % (N["cr_ledger_cos_rel"], N["cr_ledger_z_rel"], N["cr_ledger_rank_same"]))
    A("- 变异台逐条：%s" % "、".join(N["mut_ids"]))
    A("")
    A("### 【5】⚠⚠⚠ **六条更正 ＋ 两条增补（撤回并更正，⛔ 不改数凑好看）**")
    A("")
    A("⚖ **这八条全部写在预登记 §0.5 里**（含「发生时机」与「有没有改动实测数」）"
      " ⇒ ⇒ **口径真相源 = 预登记**，不是实现。")
    A("")
    A("1. **更正 ①：「逐位相同」这个说法本身是错的** —— 244.83 自己的**两条实现路线**"
      "（纯 Python vs numpy）算出的 `cos0` 就已经不一样（`0.060171700088156616` vs "
      "`0.06017170008815668`，尾数差 6e-17）⇒ ⇒ **跨实现口径下「逐位」在数学上不成立** "
      "⇒ ⇒ 改成**相对差 ≤ 1e-12**，并把**实际差值**印出来。")
    A("2. **更正 ②：⚠⚠⚠ 零分布「自包含」** —— 本轮的 **Phase-0 闸门当场抓到的真统计缺陷**："
      "参考集若与**构造向量所用的随机种子**重叠，零分布里就含着构造它的那批随机量 "
      "⇒ ⇒ 统计量被**系统性抬高**（实测：构造成分种子 ∈ 1..2000 × 参考 1..2000 ⇒ "
      "**参考 sd 相对理论偏 0.41–0.43**；种子 ∈ 900k+ × 参考 1..2000 ⇒ **0.0002–0.027**）"
      "⇒ ⇒ 真数据同样中招（6 把 w 都由 `default_rng(42)` 参与构造，而 **42 就落在参考区间 1..2000 里**）"
      "⇒ ⇒ 修正：**类级**零分布的种子区间改成 **%s..%s**（与构造种子不相交）"
      "⇒ ⇒ 并新增 **H13 自包含闸**（含/不含构造种子的两种参考集，**判决形态必须相同**）。"
      % (N["h13_lo"], N["h13_hi"]))
    A("3. **更正 ③：H9 的通过条件此前没写死** ⇒ ⇒ 改成「**分层 A 单独重算的判决形态必须与主判决相同**」"
      "⇒ ⇒ 避免出现一个**通过条件随结果漂移**的判据。")
    A("4. **更正 ④：H6 的参考 sd 容差** —— ⛔ 拿 1e-12 的相对容差去比账本里**只印到 6 位小数**的数 "
      "⇒ ⇒ **数学上不可能通过** ⇒ ⇒ 改成「**绝对差 ≤ 5e-7**（＝末位打印精度 1e-6 的一半，"
      "⛔ **由打印精度推导**，⛔ 不是从实测值倒推）」**＋** 一条**更强**的：「把本轮的值印到 6 位小数，"
      "必须与账本那个数**逐位相同**」⇒ ⇒ 实测：绝对差 %s（上限 %s）、印到 6 位小数 = %s ⇒ ⇒ **逐位相同**。"
      % (N["h6_absdiff"], N["h6_abstol"], N["h6_sd_exp"]))
    A("5. **更正 ⑤：⚠⚠⚠ 实现把 H11 的 |z| 上限单方面放宽成 3.0**（预登记 §3.2 H11 写的是 **2**）"
      "⇒ ⇒ **护栏变松 ⇒ 判据的牙齿变少**，且**没有外部依据** ⇒ ⇒ **撤回，改回 2.0**；"
      "实测负控 `z_T = %s` ⇒ ⇒ **2.0 与 3.0 都通过** ⇒ ⇒ **判决形态不变**（仍是 E-B）"
      "⇒ ⇒ 改的是**口径、不是数** ⇒ ⇒ ⛔ **没有动任何实测数**。"
      "⚖ **连带必改**：变异台 `PM5` 的搜索串原本写死 `3.0` ⇒ ⇒ 实现一改它就找不到落点 ⇒ ⇒ "
      "该变异体会退化成「**无效**」⇒ ⇒ 已同步改成 `2.0` ⇒ ⇒ **「每条判据能红」没有因为这次回落而失效**。"
      % N["h11_z"])
    A("6. **增补 Ⅵ：H11 半 B 的可验阈值** —— 预登记原来只说「置换种子固定并登记」，"
      "**没写死**「怎么判断置换**真的**破坏了共享结构」的数值判据 ⇒ ⇒ 实现里多了一个 "
      "`negctl_paircos_max = 0.15` ⇒ ⇒ **原先没有出处** ⇒ ⇒ 现补上**外部依据**："
      "零假设下两把独立各向同性单位向量的余弦 `sd ≈ 1/√d = 0.022097`（d=2048）"
      "⇒ ⇒ 上界取 **6.79 × (1/√d) = 0.15** ⇒ ⇒ 单对超过它的概率 ≈ **1.2e-11**、15 对取最大 ≈ **1.9e-10** "
      "⇒ ⇒ 它是「结构**确实被破坏**」的**存在性**判据，⛔ 不是分布形状判据 ⇒ ⇒ "
      "变异台 `PM9` 证明它**能红**（只把 `shuffle_indep` 改成不破共享 ⇒ ⇒ H11 必须红）。")
    A("7. **增补 §3.3：D5 簇分解 与 D6 簇的出处**（**描述判据**，⛔ 不改变判决形态）"
      "⇒ ⇒ 两两余弦 > 0.5 连通分簇 ⇒ ⇒ 簇 A（w_L19_m1+w_t1+w_p2a）平均余弦 +0.051822、z=+2.393；"
      "簇 B（w_L19_m0+w_real+w_old）+0.001517、z=+0.046 ⇒ ⇒ **偏高只集中在 w_p2a 所属的那个簇**。")
    A("8. **更正 ⑥：⚠⚠⚠ 两条「判决形态」层面的缺陷**（**落账之后、R5 跑到一半**时做"
      "「预登记 ↔ 实现 ↔ 变异台」三方对账才发现 ⇒ ⇒ ⛔ **不享受**「先于实现」的豁免）："
      "① **被检实现里「E-C」那一支是死代码** —— 判决逻辑把「`failed_ids()` 非空 ⇒ FAIL」写在前、"
      "「`not h12_ok` ⇒ E-C」写在后 ⇒ ⇒ **H12 红时它已经进了 `failed_ids`** ⇒ ⇒ 第一个分支先命中 "
      "⇒ ⇒ **E-C 永远走不到** ⇒ ⇒ 预登记承诺的「H12 红 ⇒ 只能是 E-C」在实现里**不成立** "
      "⇒ ⇒ **「判别力不足（没量到）」与「前提被推翻」被混成一类** ⇒ ⇒ 已改成："
      "**非 H12** 的硬判据红 ⇒ **FAIL**（前提被推翻）、**只有 H12** 红 ⇒ **E-C**（判别力不足）"
      "⇒ ⇒ 并把**第四种形态 FAIL** 写进预登记 §3.1（连同「三种『不是结论』必须分开」那段）；"
      "② **预登记 §3.1 / §6 漏改** —— 更正 ② 新增的 **H13** 是硬判据，但形态表与里程碑仍写「H1–H12 全绿」"
      "⇒ ⇒ **比实现松** ⇒ ⇒ 已改成 H1–H13。"
      "⚖ **为什么变异台此前没抓到 ①**：变异台**只断言「哪些判据变红」**、⛔ **不看判决形态** "
      "⇒ ⇒ 实现把 H12 红一律判成 FAIL 也照样全绿过 ⇒ ⇒ 现在把**判决形态**纳入断言："
      "**PM6 逼出 E-C**、**PM15/PD1 逼出 FAIL** ⇒ ⇒ 那条死分支**再也藏不住**。"
      "⚖ **有没有改动实测数**：⛔ **没有，一个都没有**（z_T / 秩 / sd / FPR / 6 条余弦 / 簇分解全不变）"
      "⇒ ⇒ 形态**仍是 E-B**（H12 绿、其余 11 条全绿 ⇒ ⇒ 走的是 E-B 那一支，⛔ 不经过 E-C/FAIL）"
      "⇒ ⇒ **判决不变、结论不变**；⚖ **代价**：预登记 md5 变了 ⇒ ⇒ 字节清单重出 ⇒ ⇒ 账本重落 "
      "⇒ ⇒ **R5 重跑** ⇒ ⇒ 这是如实记账的代价。")
    A("")
    A("### 【5.1】🔧 **本轮顺带修掉的、上一轮留下的「验证工具」缺陷**（⛔ **不涉及任何实测数**）")
    A("")
    A("- **244.83 的提交后回读脚本，两处断言写错了**（本轮做「实现 ↔ 预登记」逐条对账时顺带发现）"
      "⇒ ⇒ ① **D 断言**假设「每个修订号在账本里只有一段」，但 **244.74 有 2 段、244.75 有 3 段**"
      "（那是「第二机旁证 / 补记」这类**按设计复用同一修订号的追加段**，⛔ 不是重复条目）"
      "⇒ ⇒ ② **E 断言**用子串「修订 244.1」去找索引条目 ⇒ ⇒ 把「修订 244.10」…「修订 244.19」"
      "**以及兄弟修订「修订 244.1b」「修订 244.2b」**一起匹上 ⇒ ⇒ 两处都判红 "
      "⇒ ⇒ 已改成「**登记该修订的全部段行号**」＋「**带 token 边界的正则**」"
      "⇒ ⇒ 并新增一条**能红自证**（把索引里某条**多段**修订的条目**删掉一条** ⇒ ⇒ E 必须判红）"
      "⇒ ⇒ **账本与索引本身没有错，错的是断言** ⇒ ⇒ 已 amend 进 244.83 的提交，**实测数一个字没动**。")
    A("- **落账脚本的「防重复落账」闸**原来只做「拒绝」⇒ ⇒ 提交链**不可重跑**"
      "⇒ ⇒ 改成「**已落 ⇒ 必须与收据算出来的那段逐字节相同**，相同则不重写，不同则停下」"
      "⇒ ⇒ 幂等且**自证**。")
    A("")
    A("### 【6】⛔ **边界清单（本轮哪些仍未量到）**")
    A("")
    A("- ⛔ **「污染对改判率的影响」仍然未量到** —— 固定剂量批**没落盘 alpha 轨迹**"
      "（跑批器调探针时**没传 `--dump-raw`**）⇒ ⇒ 离线**算不出**「污染最多能翻多少格」；"
      "且 w 臂在 **w 剂量 %s** 处的响应**未量到**、单调性**未量到** ⇒ ⇒ "
      "本轮只登记**条件命题**：污染在 rand 臂最大剂量处等效于一次 **w 剂量 %s** 的注入，"
      "⛔ 两条前提未实测 ⇒ ⇒ **不进判决**。" % (N["d1_equiv"], N["d1_equiv"]))
    A("- ⛔ **「6 把 w 代表全部 steering 向量」的外推** ⇒ ⇒ **未量到**（6 把是**同一套 recipe** 的"
      "6 个解：同 marker 集、同训练种子 %s、同层 ⇒ ⇒ 结论的外推范围仅限「同一 recipe 的解」。"
      % N["h2_seed"])
    A("- ⛔ **「多随机种子的对照臂」** ⇒ ⇒ 仍然**未量到**（实验用的还是**一个**种子 ⇒ 本轮只是"
      "把「w 的这一侧」从 N=1 变成 N=6，**r 那一侧仍是 N=1**）⇒ ⇒ 要 K 臂跑批。")
    A("- ⛔ **「哪一条臂是机制效应」** ⇒ ⇒ 沿用旧留白，**未量到**（要「同结论对照臂」）。")
    A("- ⛔ 远端 tokenizer 快照的内容指纹、**照 meta 重建能否逐位复现** ⇒ ⇒ 沿用旧留白，**未量到**。")
    A("")
    A("### 【7】▶️ **下一轮（244.85+）**")
    A("")
    A("1. **多随机种子的对照臂**（把 **r 那一侧**也从 N=1 变成 N=K）⇒ ⇒ 这是把「对照臂对齐度」"
      "从 N=1 变成**分布**的正解（本轮只做了 w 那一侧）。")
    A("2. **固定剂量批重跑并加 `--dump-raw`** ⇒ ⇒ 拿到 60 点全曲线 ⇒ ⇒ 离线把 w 臂曲线缩放到 "
      "**%s** 剂量 ⇒ ⇒ 直接算「污染最多能翻多少格」⇒ ⇒ 把 D3 的条件命题变成实测。" % N["d1_equiv"])
    A("3. **同结论对照臂**（机制轴）：同结论、同末值、只有检查有效性不同。")
    A("4. **分层剂量的真阶梯**（剂量轴）：⛔ 不能靠事后分位分档 ⇒ ⇒ 要跑批 ⇒ ⇒ 要点头。")
    A("")
    A("### 【8】⚖ **这一轮的字节**")
    A("")
    A("⚖⚖⚖ 下面每个 md5 都是**由文件本身算出来的**，且与**收据登记的那份逐位对上**"
      " ⇒ ⇒ 「入库的字节 ＝ 跑出这些数的字节」。")
    A("")
    A("- **被检 / 口径 / 驱动（%d 件）**：" % len(ROUND_FILES))
    for name, path in ROUND_FILES:
        m = _md5_file(path)
        rcv = N["rc_md5_base"].get(name)
        if rcv is None:
            raise SystemExit("⛔ 收据里没有登记 `%s` 的 md5 ⇒ 字节清单无出处 ⇒ 中止" % name)
        if rcv != m:
            raise SystemExit("⛔ `%s` 的本地 md5 = %s 与收据登记的 %s **不一致** ⇒ ⇒ 停下"
                             "（⛔ 不许入库与收据不是同一份的字节）" % (name, m, rcv))
        A("  - `%s`  `%s`" % (m, name))
    A("- **bpath 产物（%d 件，⛔ 只读、零 GPU）**：" % len(N["rc_bpath"]))
    for md5v, nm in N["rc_bpath"]:
        A("  - `%s`  `%s`" % (md5v, os.path.basename(nm)))
    A("- **收据文件（%d 件）**：" % len(N["rc_out"]))
    for md5v, nm in N["rc_out"]:
        A("  - `%s`  `%s`" % (md5v, os.path.basename(nm)))
    A("")
    A("⚖ **远端**：`zju-53` ｜ ⛔ **零 GPU**、⛔ 没跑批、⛔ 没改读数器/探针/拆分器、"
      "⛔ 没改 244.79–244.83 段。")
    A("")
    return "\n".join(L) + "\n"


def main():
    dry = "--dry" in sys.argv
    N = collect()
    sec = build(N)
    fences = [l for l in sec.split("\n") if l.strip().startswith("```")]
    assert not fences, "⛔ 追加段里有围栏 ⇒ 不许"
    assert "\\" not in sec, "⛔ 追加段里有反斜杠 ⇒ 不许"
    full = _read(LEDGER)
    # ⚖⚖⚖ **防重复落账**（幂等闸）：已落 ⇒ 必须**逐字节等于**收据算出来的那段，否则停下
    _h = TITLE
    n_have = full.count(_h)
    if n_have > 1:
        raise SystemExit("⛔ 账本里有 %d 处「%s」⇒ ⇒ 停下" % (n_have, _h))
    if n_have == 1:
        tail = full[full.index(_h):]
        if tail == sec or tail.rstrip() == sec.rstrip():
            print("✅ 幂等：账本里已有的 244.84 段与**收据算出来的那段逐字节相同**"
                  " ⇒ ⇒ 不重复写（本次落账无需再动）")
            return 0
        raise SystemExit("⛔ 账本里已有 244.84 段，但它与收据算出来的**不一致** ⇒ ⇒ 停下"
                         "（⛔ 不许覆盖、⛔ 不许改数凑好看）")
    n_before = sum(1 for l in full.split("\n") if l.strip().startswith("```"))
    old_len = len(full.encode("utf-8"))
    old_lines = full.count("\n")
    print("账本现状：%d 行 / %d 字节 ｜ 围栏 %d 个" % (old_lines, old_len, n_before))
    if dry:
        print("")
        print(sec)
        print("（--dry：只看不写）")
        return 0
    with io.open(LEDGER, "a", encoding="utf-8") as f:
        f.write(sec)
    after = _read(LEDGER)
    n_after = sum(1 for l in after.split("\n") if l.strip().startswith("```"))
    assert n_after == n_before, "⛔ 落账后围栏数变了 ⇒ 停下"
    assert after.encode("utf-8")[:old_len] == full.encode("utf-8"), "⛔ 旧前缀变了 ⇒ 停下"
    print("")
    print("✅ 已追加：%d → %d 字节（行 %d → %d）｜ 围栏仍 %d 个 ｜ 旧前缀逐字节不变"
          % (old_len, len(after.encode("utf-8")), old_lines, after.count("\n"), n_after))
    return 0


if __name__ == "__main__":
    sys.exit(main())
