#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 244.84 的交接文件（**所有数从收据解析**，⛔ 不手抄）。

⚖ 口径真相源：`.cache/xcheck/R6_ALIGNMENT_DISTRIBUTION_PREREG.md`
⚖ 收据：`.cache/r244/_e24484/{selftest,de,mut,cross}.out` ＋ `receipt.txt` ＋ `reg_24484.txt`
"""

import datetime
import io
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
EV = os.path.join(HERE, "_e24484")
OUT = os.path.join(REPO, ".cache", "xcheck", "HANDOFF_24484.md")


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


def _git(*a):
    return subprocess.run(["git"] + list(a), cwd=REPO, capture_output=True,
                          text=True).stdout.strip()


def main():
    de = _need(os.path.join(EV, "de.out"))
    st = _need(os.path.join(EV, "selftest.out"))
    mu = _need(os.path.join(EV, "mut.out"))
    cr = _need(os.path.join(EV, "cross.out"))
    rc = _need(os.path.join(EV, "receipt.txt"))
    regp = os.path.join(EV, "reg_24484.txt")
    reg = _read(regp) if os.path.isfile(regp) else ""

    N = {}

    # ---- 判决形态 ----
    N["verdict"] = _grab(de, r"^VERDICT=([EABC]-[ABC])$", "判决形态").group(1)
    m = _grab(de, r"^判决形态：(.+)$", "判决形态说明")
    N["why"] = m.group(1).strip().replace("**", "")

    # ---- 主统计量 ----
    m = _grab(de, r"^\[PASS\] H10-CLASSSTAT\s+主统计量 T=[^=]*=([-+0-9.eE]+) ｜ "
                   r"参考 K=(\d+)：mean=([-+0-9.eE]+) sd=([-+0-9.eE]+) ｜ "
                   r"理论 sd=[^=]*=([-+0-9.eE]+)（相对差 ([-+0-9.eE]+)，上限 ([-+0-9.eE]+)）｜ "
                   r"z_T=([-+0-9.eE]+) ｜ 秩=([-+0-9.eE]+) ｜ 共同分量投影 U₀=([-+0-9.eE]+) z_U=([-+0-9.eE]+)",
             "H10")
    (N["T0"], N["K"], N["Tmean"], N["Tsd"], N["Theo"], N["Tsdrel"], N["Ttol"],
     N["zT"], N["rankT"], N["U0"], N["zU"]) = m.groups()

    m = _grab(de, r"^\[PASS\] H12-FPR\s+判决规则「z_T ≥ ([-+0-9.eE]+)」在 K=(\d+) 个参考种子下的"
                   r"\*\*经验假阳性率\*\* = ([-+0-9.eE]+)（上限 ([-+0-9.eE]+)）", "H12")
    N["h12_thr"], N["h12_K"], N["h12_fpr"], N["h12_max"] = m.groups()

    m = _grab(de, r"^\[PASS\] H9-STRATUM\s+分层 A（(\d+) 把同 npz）单独重算：T=([-+0-9.eE]+) "
                   r"z_T=([-+0-9.eE]+)（判 ([A-Z]-[A-Z])）｜ 全 (\d+) 把：z_T=([-+0-9.eE]+)（判 ([A-Z]-[A-Z])）",
             "H9")
    (N["h9_n"], N["h9_T"], N["h9_z"], N["h9_v"], N["h9_tot"], N["h9_zall"], N["h9_vall"]) = m.groups()

    m = _grab(de, r"^\[PASS\] H13-SELFINCLUDE\s+构造种子（6 把 sidecar 读出）= (.+?) ｜ "
                   r"类级参考种子区间 (\d+)\.\.(\d+) ⇒ 交集 = (.+?) ⇒ (.+?) ｜ "
                   r"含构造种子的参考集（(\d+)\.\.(\d+)）算出的 z_T=([-+0-9.eE]+)（判 ([A-Z]-[A-Z])）"
                   r"vs 不含的 z_T=([-+0-9.eE]+)（判 ([A-Z]-[A-Z])）", "H13")
    (N["h13_ctor"], N["h13_lo"], N["h13_hi"], N["h13_inter"], N["h13_inter_txt"],
     N["h13_alt_lo"], N["h13_alt_hi"], N["h13_z_alt"], N["h13_v_alt"], N["h13_z"], N["h13_v"]) = m.groups()

    m = _grab(de, r"^\[PASS\] H11-NEGCONTROL\s+6 把各自独立坐标置换（种子 (\d+)\+i）后：z_T=([-+0-9.eE]+)"
                   r"（\|z\| 上限 ([-+0-9.eE]+)）｜ 置换后两两余弦 max=([-+0-9.eE]+)（上限 ([-+0-9.eE]+)",
             "H11")
    N["h11_seed"], N["h11_z"], N["h11_zmax"], N["h11_pwmax"], N["h11_pwmax_lim"] = m.groups()

    m = _grab(de, r"^  D1 污染量级：cos=([-+0-9.eE]+) ⇒ rand 方向含 w 能量 ([-+0-9.eE]+)% ｜ "
                   r"w 等效剂量 = ([-+0-9.eE]+) × ([-+0-9.eE]+) = ([-+0-9.eE]+)$", "D1")
    (N["d1_cos"], N["d1_pct"], N["d1_c"], N["d1_gap"], N["d1_equiv"]) = m.groups()

    m = _grab(de, r"^  D2 换个 r（seed (\d+)）：(.+?) ｜ 正号 (\d+)/(\d+)$", "D2")
    N["d2_seed"], N["d2_list"], N["d2_pos"], N["d2_tot"] = m.groups()

    # ---- 簇分解（描述）----
    m = _grab(de, r"^   簇（3 把）(\S+?)\s*：对 r₀ 的平均余弦 = ([-+0-9.eE]+) ｜ z = ([-+0-9.eE]+)$", "簇 A")
    N["clA_members"], N["clA_cos"], N["clA_z"] = m.groups()
    m = _grab(de, r"^   簇（3 把）(\S+?)\s*：对 r₀ 的平均余弦 = ([-+0-9.eE]+) ｜ z = ([-+0-9.eE]+)$"
               .replace("^   簇（3 把）", "^   簇（3 把）"), "簇 B")
    # 第二个簇用「全部匹配」拿第二条
    _cs = re.findall(r"^   簇（3 把）(\S+?)\s*：对 r₀ 的平均余弦 = ([-+0-9.eE]+) ｜ z = ([-+0-9.eE]+)$",
                      de, re.M)
    if len(_cs) < 2:
        raise SystemExit("⛔ 簇分解抠不到两条 ⇒ 中止")
    N["clB_members"], N["clB_cos"], N["clB_z"] = _cs[1]
    N["clA_members"], N["clA_cos"], N["clA_z"] = _cs[0]

    # ---- 6 把逐条余弦 ----
    m = _grab(de, r"^=== 类级余弦（6 把 × 同一个 r₀）===\n((?:  .*\n)+)", "类级余弦块")
    N["cos_each"] = re.findall(r"^  (\S+)\s+cos\(v, r₀\) = ([-+0-9.eE]+)$", m.group(1), re.M)
    if not N["cos_each"]:
        raise SystemExit("⛔ 6 把逐条余弦抠不到 ⇒ 中止")
    m = _grab(de, r"正号计数 = (\d+) / (\d+)（单侧 P\(全正\) = 2\^-(\d+) = ([-+0-9.eE]+)）", "正号计数")
    N["npos"], N["ntot"], N["nexp"], N["p_allpos"] = m.groups()

    # ---- 跨轮对账 ----
    m = _grab(de, r"^\[PASS\] H5-CLASSCOS\s+6 把对 r₀ 的余弦：(.+?) ｜ w_p2a 那一条 = ([-+0-9.eE]+) ｜ "
                   r"账本 244\.83 登记 = ([-+0-9.eE]+) ｜ 相对差 ([-+0-9.eE]+)（上限 ([-+0-9.eE]+)）",
             "H5")
    N["h5_cos"], N["h5_exp"], N["h5_rel"], N["h5_tol"] = m.group(2), m.group(3), m.group(4), m.group(5)
    m = _grab(de, r"（\*\*绝对差 ([-+0-9.eE]+)\*\*，上限 ([-+0-9.eE]+) ", "H6 绝对差")
    N["h6_absdiff"], N["h6_abstol"] = m.groups()

    # ---- 自检 / 变异台 / 互证 / 真数据判据 ----
    m = _grab(st, r"自检（Phase-0 G0-1/G0-2/G0-3）：(\d+) 条 ｜ FAIL (\d+) 条", "自检小结")
    N["st_n"], N["st_fail"] = m.groups()
    m = _grab(mu, r"变异台：抓到 (\d+) / (\d+)（无效 (\d+) 条", "变异台小结")
    N["mut_caught"], N["mut_total"], N["mut_invalid"] = m.groups()
    N["mut_crash"] = _grab(mu, r"崩的条数：(\d+)", "崩计数").group(1)
    N["mut_ids"] = re.findall(r"^\[(?:抓到|硬停抓到)\] (\S+)", mu, re.M)
    m = _grab(cr, r"^互证：(\d+) 项 ｜ OK (\d+) ｜ MISMATCH (\d+)", "互证计数")
    N["cr_n"], N["cr_ok"], N["cr_bad"] = m.groups()
    m = _grab(de, r"^判据汇总：(\d+) 条 ｜ PASS (\d+) ｜ FAIL (\d+)$", "真数据判据小结")
    N["de_n"], N["de_pass"], N["de_fail"] = m.groups()

    # ---- 收据：主机 / 退出码 / 字节 ----
    N["rc_host"] = _grab(rc, r"^host=(\S+)\s+date=", "收据主机").group(1)
    N["rc_rcs"] = _grab(rc, r"^SELFTEST_RC=(\d+)\s+DE_RC=(\d+)\s+MUT_RC=(\d+)\s+CROSS_RC=(\d+)$",
                         "收据退出码").groups()
    N["rc_md5"] = dict((v, k) for k, v in
                        re.findall(r"^([0-9a-f]{32})\s+(\S+)$", rc, re.M))
    N["rc_md5_base"] = dict((os.path.basename(k), v) for k, v in N["rc_md5"].items())

    # ---- 全回归 R5 ----
    reg_line = "⛔ **R5 收据未取回**"
    ledger_lines = "?"
    if reg:
        def _rg(pat, what):
            return _grab(reg, pat, what).group(1)
        reg_line = ("`%s` ｜ 执行集 **%s** 个 py ｜ 清单 diff 对 R4 added **%s** / removed **%s** ｜ "
                    "变异台 全绿 %s / 跑得动 %s ｜ 自检 全绿 %s / 跑得动 %s ｜ `REG_RC = %s` ｜ "
                    "账本 %s 行 md5 `%s`"
                    % (_rg(r"host=(\S+)", "R5 主机"),
                       _rg(r"n_exec_py=(\d+)", "R5 执行集数"),
                       _rg(r"added=(\d+)", "R5 新增"), _rg(r"removed=(\d+)", "R5 减少"),
                       _rg(r"小结：变异台 全绿 (\d+)", "R5 变异台-全绿"),
                       _rg(r"小结：变异台 全绿 \d+ / 跑得动 (\d+)", "R5 变异台-跑得动"),
                       _rg(r"小结：.*自检 全绿 (\d+)", "R5 自检-全绿"),
                       _rg(r"小结：.*自检 全绿 \d+ / 跑得动 (\d+)", "R5 自检-跑得动"),
                       _rg(r"REG_RC=(\d+)", "R5 退出码"),
                       _rg(r"ledger_lines=(\d+)", "R5 账本行数"),
                       _rg(r"ledger_md5=(\w+)", "R5 账本 md5")))
        ledger_lines = _rg(r"ledger_lines=(\d+)", "R5 账本行数")
        # ⚖⚖⚖ **红项按分类登记**（⛔ 只报两个数 ⇒ ⇒ 会把红项藏起来）
        # ⚖⚖⚖ **只把「harness 的逐条结果行」当红项**（⛔ 收据**头行**不是红项 ⇒ ⇒ 早先一版误报）
        reg_red = []
        for _l in reg.split("\n"):
            _s = _l.strip()
            if not _s or not _s.startswith("["):
                continue
            if _s.startswith("[OK") or _s.startswith("[SKIP"):
                continue
            reg_red.append(_s)
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
            reg_line += " ｜ ⚠ **红项 %d 条**（逐条见提交信息）" % len(reg_red)
        else:
            reg_line += " ｜ ✅ **红项登记：零红项**"

    head = _git("log", "--oneline", "-1")

    L = []
    A = L.append
    A("# 交接 —— 244.84「对照臂方向污染的类级判读」（%s）"
      % datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
    A("")
    A("⚖⚖⚖ **一句话**")
    A("")
    A("**244.83 那个「N=1 ⇒ 巧合还是结构未量到」的留白，本轮被做成可判读的三态，判成 %s。**"
      % N["verdict"])
    A("手法是**换掉 w、不换 r**：rand 臂那把 `r = rand_seed0` 是探针里写死的（`default_rng(0)`），"
      "实验已经用它跑完 168 格 ⇒ ⇒ 它不能换；能换的是 **w** ⇒ ⇒ 对 **6 把同层同 marker 同训练种子的 "
      "steering 向量**各算一次 `cos(v_i, r)`。")
    A("类级主统计量 `T = mean_i cos(v_i, r₀)` = **%s**，z_T = **%s**（阈值 2.0）⇒ ⇒ 离群。"
      % (N["T0"], N["zT"]))
    A("")
    A("⚖⚠⚠⚠ **E-B 的准确含义必须收紧**（⛔ 不许读成「所有 steering 向量都偏高」）：")
    A("偏高**只集中在 `w_p2a` 所属的那个簇**（簇 `%s` z=**%s**）⇒ ⇒ 另一簇 `%s` 的 z=**%s**（≈ 0）"
      "⇒ ⇒ 且**换个种子（r_42）就不偏高**（正号 %s/%s）"
      "⇒ ⇒ 准确表述是「**这次实验用的那把固定随机方向 r_seed0，恰好落在 w_p2a 所属 steering 簇的"
      "公共方向附近**」⇒ ⇒ **rand 臂对这一簇不是干净的零假设**。"
      % (N["clA_members"], N["clA_z"], N["clB_members"], N["clB_z"], N["d2_pos"], N["d2_tot"]))
    A("")
    A("## 1. 📊 判决面板（类级）")
    A("")
    A("| 量 | 值 | 判据 |")
    A("|---|---|---|")
    A("| **类级主统计量** `T = mean_i cos(v_i, r₀)` | **%s** | 6 把 w 对同一把 r₀ |" % N["T0"])
    A("| **z_T** | **%s** | 阈值 %s ⇒ ⇒ **离群 ⇒ 结构（%s）** |"
      % (N["zT"], N["h12_thr"], N["verdict"]))
    A("| 经验秩 / 参考 sd / 理论 sd=‖m‖/√d | %s / %s / %s | sd 相对差 %s（上限 %s）⇒ 零分布**被校准** |"
      % (N["rankT"], N["Tsd"], N["Theo"], N["Tsdrel"], N["Ttol"]))
    A("| 共同分量投影 U₀ / z_U | %s / %s | 描述量 |" % (N["U0"], N["zU"]))
    A("| **判别力**（判决规则的经验假阳性率） | **%s**（上限 %s） | H12 ⇒ ⇒ 规则**可用** |"
      % (N["h12_fpr"], N["h12_max"]))
    A("| **分层稳健性**（同 npz 的 %s 把单独重算） | z_T=%s（判 %s）vs 全 %s 把 z_T=%s（判 %s） | H9 ⇒ ⇒ 结论**不随纳入范围而变** |"
      % (N["h9_n"], N["h9_z"], N["h9_v"], N["h9_tot"], N["h9_zall"], N["h9_vall"]))
    A("| **自包含闸**（构造种子 %s vs 类级参考区间 %s..%s） | 交集 %s ｜ 含它的参考集 z_T=%s（判 %s）vs 不含 %s（判 %s） | H13 ⇒ ⇒ 自包含**没有影响判决** |"
      % (N["h13_ctor"], N["h13_lo"], N["h13_hi"], N["h13_inter"], N["h13_z_alt"], N["h13_v_alt"],
         N["h13_z"], N["h13_v"]))
    A("| **负控**（6 把各自独立坐标置换） | z_T=%s（z 的绝对值上限 %s）｜ 置换后两两余弦 max=%s（上限 %s） | H11 ⇒ ⇒ 负控通过 |"
      % (N["h11_z"], N["h11_zmax"], N["h11_pwmax"], N["h11_pwmax_lim"]))
    A("")
    A("## 2. 🔍 6 把 w 对同一把 r₀ 的余弦（逐条）")
    A("")
    for nm, c in N["cos_each"]:
        A("- `%s` → **%s**" % (nm, c))
    A("- 正号计数 **%s / %s**（单侧 `P(全正) = 2^-%s = %s`）"
      % (N["npos"], N["ntot"], N["nexp"], N["p_allpos"]))
    A("")
    A("## 3. 📚 跨轮对账（244.83 的数被独立重算出来）")
    A("")
    A("- `w_p2a` 那一条 = `%s` vs 账本 `%s`（相对差 %s，上限 %s）"
      % (N["h5_cos"], N["h5_exp"], N["h5_rel"], N["h5_tol"]))
    A("- H6 参考 sd：绝对差 **%s**（上限 %s —— ⛔ 账本里那个数只印到 6 位小数 ⇒ ⇒ 容差由**打印精度**推导）"
      % (N["h6_absdiff"], N["h6_abstol"]))
    A("- 互证：%s 项 ｜ OK **%s** ｜ MISMATCH **%s**" % (N["cr_n"], N["cr_ok"], N["cr_bad"]))
    A("")
    A("## 4. ✅ 每条判据能红")
    A("")
    A("- 自检（Phase-0 G0-1/G0-2/G0-3，合成夹具、零 bpath、零 GPU）：判据 **%s** 条 ｜ FAIL **%s** 条"
      % (N["st_n"], N["st_fail"]))
    A("- 变异台：抓到 **%s / %s**（无效 %s ⇒ 记「无效」不计入分母）｜ 崩 **%s**（⛔ 必须是 0）"
      % (N["mut_caught"], N["mut_total"], N["mut_invalid"], N["mut_crash"]))
    A("- 真数据判据：%s 条 ｜ PASS **%s** ｜ FAIL **%s**" % (N["de_n"], N["de_pass"], N["de_fail"]))
    A("- 变异台逐条：%s" % "、".join(N["mut_ids"]))
    A("")
    A("## 5. ⚠⚠⚠ 六条更正 ＋ 两条增补（撤回并更正，⛔ 不改数凑好看）")
    A("")
    A("1. **更正 ①**：「逐位相同」在跨实现口径下**数学上不成立**（244.83 两条路线差 6e-17）⇒ ⇒ 改成相对差 ≤ 1e-12。")
    A("2. **更正 ②：⚠⚠⚠ 零分布「自包含」** —— Phase-0 闸门当场抓到的真统计缺陷（参考集与构造种子重叠 ⇒ "
      "参考 sd 相对理论**偏 0.41–0.43**）⇒ ⇒ 类级参考种子区间改成 %s..%s ＋ 新增 **H13 自包含闸**。"
      % (N["h13_lo"], N["h13_hi"]))
    A("3. **更正 ③**：H9 的通过条件此前没写死 ⇒ ⇒ 改成「分层 A 单独重算的判决形态必须与主判决相同」。")
    A("4. **更正 ④**：H6 的参考 sd 容差 —— ⛔ 拿 1e-12 去比只印到 6 位小数的数**数学上不可能通过** "
      "⇒ ⇒ 改成绝对差 ≤ %s ＋「印到 6 位小数必须逐位相同」。" % N["h6_abstol"])
    A("5. **更正 ⑤：⚠⚠⚠ 实现把 H11 的 |z| 上限单方面放宽成 3.0**（预登记写的是 2）⇒ ⇒ **撤回，改回 2.0**；"
      "实测负控 z_T=%s ⇒ ⇒ **2.0 与 3.0 都通过** ⇒ ⇒ 判决形态不变 ⇒ ⇒ **改的是口径、不是数**。"
      % N["h11_z"])
    A("6. **增补 Ⅵ**：H11 半 B 的可验阈值（置换后两两余弦 max ≤ 0.15 ＝ 6.79/√d）补上**外部依据**。")
    A("7. **增补 §3.3**：D5 簇分解 与 D6 簇的出处（描述判据，⛔ 不改变判决形态）。")
    A("8. **更正 ⑥：⚠⚠⚠ 两条「判决形态」层面的缺陷**（落账之后、R5 跑到一半时做三方对账才发现）"
      "⇒ ⇒ ① **被检实现里「E-C」那一支是死代码** ⇒ ⇒ 「判别力不足（没量到）」与「前提被推翻」被混成一类 "
      "⇒ ⇒ 已改成：非 H12 的硬判据红 ⇒ **FAIL**、只有 H12 红 ⇒ **E-C**；"
      "② **预登记 §3.1 / §6 漏改**（H13 是硬判据，形态表仍写「H1–H12 全绿」）⇒ ⇒ 改成 H1–H13。"
      "⚖ **变异台为何此前抓不到 ①**：它**只断言「哪些判据变红」**、⛔ 不看判决形态 "
      "⇒ ⇒ 现在把**判决形态**纳入断言（PM6 ⇒ E-C、PM15/PD1 ⇒ FAIL）。"
      "⚖ **有没有改动实测数**：⛔ **没有** ⇒ ⇒ 形态**仍是 E-B**（走 E-B 那一支）⇒ ⇒ **判决不变**。")
    A("")
    A("⚖ **顺带修掉的、244.83 留下的「验证工具」缺陷**（⛔ **不涉及任何实测数**）：244.83 的提交后回读脚本"
      "两处断言写错（D 假设每个修订号只有一段；E 用子串匹上 244.10/244.1b）⇒ ⇒ **账本与索引本身没错，"
      "错的是断言** ⇒ ⇒ 已修并 amend 进 244.83 的提交。")
    A("")
    A("## 6. 📚 证据链台账")
    A("")
    A("- 权威账本：`.cache/xcheck/R6_RERUN_PREREG.md`（**只追加**，`## 修订 244.84` 段；共 %s 行）" % ledger_lines)
    A("- 索引：`.cache/xcheck/R6_RERUN_INDEX.md`（每条修订一行）")
    A("- 预登记：`.cache/xcheck/R6_ALIGNMENT_DISTRIBUTION_PREREG.md`（**先于实现**签；§0.5 含"
      "**六条更正 ＋ 两条增补**，逐条写明发生时机与有没有改动实测数）")
    A("- 收据：`.cache/r244/_e24484/{selftest,de,mut,cross}.out` ＋ `receipt.txt` ＋ `reg_24484.txt`")
    A("- 「实现 SPEC ↔ 预登记 §2」机器对账：`.cache/r244/_spec_crosscheck_24484.py`"
      "（12 条机械比 + 3 条明确「不能机械比」＋ 自证能红）")
    A("- 验证链：`%s` ｜ SELFTEST_RC=%s DE_RC=%s MUT_RC=%s CROSS_RC=%s"
      % (N["rc_host"], N["rc_rcs"][0], N["rc_rcs"][1], N["rc_rcs"][2], N["rc_rcs"][3]))
    A("- 全回归 R5：%s" % reg_line)
    A("")
    A("## 7. ⛔ 边界清单")
    A("")
    A("- ⛔ **「污染对改判率的影响」仍未量到** —— 固定剂量批**没落盘 alpha 轨迹**（跑批器调探针时没传 "
      "`--dump-raw`）⇒ ⇒ 离线算不出；且 w 臂在 **w 剂量 %s** 处的响应未量到、单调性未量到 "
      "⇒ ⇒ 本轮只登记**条件命题**，⛔ 不进判决。" % N["d1_equiv"])
    A("- ⛔ **「6 把 w 代表全部 steering 向量」的外推** ⇒ ⇒ **未量到**（6 把是**同一套 recipe** 的 6 个解："
      "同 marker 集、同训练种子 42、同层）⇒ ⇒ 外推范围仅限「同一 recipe 的解」。")
    A("- ⛔ **「r 那一侧」仍是 N=1** —— 本轮只把 **w 那一侧**从 N=1 变成 N=6 ⇒ ⇒ **多随机种子的对照臂**仍要跑批。")
    A("- ⛔ **「哪一条臂是机制效应」** ⇒ ⇒ 沿用旧留白，**未量到**（要「同结论对照臂」）。")
    A("- ⛔ **剂量—响应曲线** ⇒ ⇒ **未量到**（本轮只看对齐度，⛔ 一个读数都不看）。")
    A("- ⛔ 远端 tokenizer 快照的内容指纹、**照 meta 重建能否逐位复现** ⇒ ⇒ 沿用旧留白，**未量到**。")
    A("")
    A("## 8. ▶️ 如何做（下一步）")
    A("")
    A("1. **先读**账本尾部 `/Users/zhourui/code/steer3d/.cache/xcheck/R6_RERUN_PREREG.md`"
      "（**唯一权威历史**）→ ② 再读本文件 → ③ `git log --oneline -10` + `git status --porcelain`"
      "（工作区有同事的未跟踪文件，⛔ 不碰）→ ④ 照下面接着做。")
    A("2. **下一轮 244.85（按性价比排序）**：")
    A("   - **多随机种子的对照臂**（把 **r 那一侧**也从 N=1 变成 N=K）⇒ ⇒ 这是把「对照臂对齐度」"
      "从 N=1 变成**分布**的正解 ⇒ ⇒ ⛔ **要跑批 ⇒ 要用户点头**。")
    A("   - **固定剂量批重跑并加 `--dump-raw`**（w 臂 + rand 臂）⇒ ⇒ 拿到 60 点全曲线 ⇒ ⇒ 离线把 w 臂曲线"
      "缩放到 **%s** 剂量 ⇒ ⇒ 直接算「污染最多能翻多少格」⇒ ⇒ 把 D3 的条件命题变成实测。" % N["d1_equiv"])
    A("   - **同结论对照臂**（机制轴）：同结论、同末值、只有检查有效性不同 ⇒ ⇒ 回答「哪一条臂是机制效应」。")
    A("   - **分层剂量的真阶梯**（剂量轴）：⛔ 不能事后分位分档 ⇒ ⇒ 要跑批 ⇒ ⇒ 要点头。")
    A("3. ⛔ 别把 E-B 读成「所有 steering 向量都与随机方向系统性重叠」—— 证据只支持「**这把固定的 r "
      "恰好落在 w_p2a 所属簇的公共方向附近**」。")
    A("4. ⛔ 在「对齐越高 ⇒ w 样行为越强」这条**未实测**的单调性假设下，244.81 的 **+30.36pp 偏保守"
      "（下界）**，**幅度未量到**。")
    A("")
    A("⚖ 最近一次提交：`%s`" % head)
    A("")

    with io.open(OUT, "w", encoding="utf-8", newline="") as fh:
        fh.write("\n".join(L) + "\n")
    print("已写出：%s（%d 字节）" % (OUT, os.path.getsize(OUT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
