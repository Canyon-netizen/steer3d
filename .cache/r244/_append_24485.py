#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⚖ **244.85 落账**（只追加；⛔ 追加段里不许有围栏；⛔ 所有数都从收据抠，⛔ 不手抄）。

**这一段记什么**：244.84 结论形态 E-B（类级）唯一那个**结构性留白口** ——
「244.84 的『r₀ 系统性地落在 steering 向量的公共方向上』这一句，
是不是被**剂量批用的那一把** `w_p2a` 撑起来的？」
⇒ ⇒ 用**留一法（LOO）**把它做成可判读的五态（F-A / F-B / F-C / F-E / FAIL）。

⚖ **口径真相源**：`.cache/xcheck/R6_LOO_ROBUSTNESS_PREREG.md`（244.85 签，**先于实现**）
⚖ **数据**：bpath 的 6 把 w 向量 ＋ 各自 sidecar ＋ 探针 ＋ 跑批器 ＋ 两臂日志
   （⛔ 只读、⛔ 零 GPU、远端 `zju-53`）
⚖ **收据**：`.cache/r244/_e24485/{selftest,de,mut,cross,spec,receipt}.out`
"""

import hashlib
import io
import os
import re
import struct
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
LEDGER = os.path.join(REPO, ".cache", "xcheck", "R6_RERUN_PREREG.md")
EV = os.path.join(REPO, ".cache", "r244", "_e24485")
DEV = os.path.join(REPO, ".cache", "r244")
XCH = os.path.join(REPO, ".cache", "xcheck")
TITLE = "## 修订 244.85 —— "

# ⚖⚖⚖ **这一轮的字节清单**（本地路径，⛔ md5 **由文件本身算出**）
ROUND_FILES = [
    ("loo_robustness_audit.py", os.path.join(DEV, "loo_robustness_audit.py")),
    ("mut_loo_robustness_audit.py", os.path.join(DEV, "mut_loo_robustness_audit.py")),
    ("_cross_check_24485.py", os.path.join(DEV, "_cross_check_24485.py")),
    ("_spec_crosscheck_24485.py", os.path.join(DEV, "_spec_crosscheck_24485.py")),
    ("_run_24485_verify.sh", os.path.join(DEV, "_run_24485_verify.sh")),
    ("R6_LOO_ROBUSTNESS_PREREG.md",
     os.path.join(XCH, "R6_LOO_ROBUSTNESS_PREREG.md")),
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


def ledger_24484_raw(ledger_text):
    """⚖⚖⚖ **账本 244.84 段里的**原文**（⛔ 不是收据里 `%r` 的缩写）。

    ⚖ **为什么必须用原文**：
    收据里那行是 `print("...%r..." % ...)` ⇒ ⇒ Python 的**最短 repr**
    ⇒ ⇒ 账本写的 `+0.026669793515452608` 被印成 `0.02666979351545261`
    ⇒ ⇒ **同一个 double、两串字** ⇒ ⇒ 读者拿 244.85 的基线行去对 244.84 的表
    **对不上字** ⇒ ⇒ 会误以为数值不一致。
    ⇒ ⇒ 所以落账引**账本自己的写法**，并在本地断言它与收据实测**逐位相同**。
    """
    m = re.search(r"^## 修订 244\.84\b", ledger_text, re.M)
    if not m:
        raise SystemExit("⛔ 账本里没有「## 修订 244.84」段 ⇒ ⇒ 基线原文无处可读 ⇒ 中止")
    m2 = re.search(r"^## 修订 ", ledger_text[m.end():], re.M)
    sec = ledger_text[m.start():(m.end() + m2.start() if m2 else len(ledger_text))]

    def line_with(kw, what):
        for ln in sec.splitlines():
            if kw in ln:
                return ln
        raise SystemExit("⛔ 账本 244.84 段里找不到含「%s」的行（%s）" % (kw, what))

    def one(pat, what, s, grp=1):
        mm = re.search(pat, s)
        if not mm:
            raise SystemExit("⛔ 账本 244.84 段里读不到「%s」" % what)
        return mm.group(grp)

    raw = {}
    ln = line_with("**类级主统计量**", "类级 T")
    raw["T"] = one(r"\*\*([-+0-9.eE]+)\*\*", "类级 T", ln)
    ln = line_with("**z_T**（对参考种子分布）", "类级 z_T")
    raw["z"] = one(r"\*\*([-+0-9.eE]+)\*\*", "类级 z_T", ln)
    ln = line_with("经验秩 / 参考 sd", "秩/sd")
    mm = re.search(r"\|\s*([-+0-9.eE]+)\s*/\s*([-+0-9.eE]+)\s*/\s*([-+0-9.eE]+)\s*\|", ln)
    if not mm:
        raise SystemExit("⛔ 账本 244.84 段里读不到「经验秩 / 参考 sd / 理论 sd」三个数")
    raw["rank"], raw["sd"], raw["theo"] = mm.group(1), mm.group(2), mm.group(3)
    ln = line_with("经验假阳性率", "FPR")
    raw["fpr"] = one(r"\*\*([-+0-9.eE]+)\*\*", "FPR", ln)
    return raw


def _bits(x):
    """⚖ double 的**位模式**（⇒ 「逐位相同」必须比这个，⛔ 不是比字符串、也不是比容差）。"""
    return struct.pack(">d", float(x))


def collect():
    """⚖ 全部数**从收据抠**（⛔ 不手抄）。"""
    st = _need(os.path.join(EV, "selftest.out"))
    de = _need(os.path.join(EV, "de.out"))
    mu = _need(os.path.join(EV, "mut.out"))
    cr = _need(os.path.join(EV, "cross.out"))
    sp = _need(os.path.join(EV, "spec.out"))
    rc = _need(os.path.join(EV, "receipt.txt"))

    N = {}

    # ---- 自检（Phase-0 G0-1..G0-7）----
    m = _grab(st, r"自检（Phase-0 G0-1\.\.G0-7）：(\d+) 条 ｜ FAIL (\d+) 条", "自检小结")
    N["st_n"], N["st_fail"] = m.groups()
    N["st_gates"] = re.findall(r"^\[(PASS|FAIL)\]\s+(G0-\d)", st, re.M)

    # ---- 真数据：判决形态 ----
    N["verdict"] = _grab(de, r"^VERDICT=(\S+)$", "判决形态").group(1)
    N["verdict_why"] = _grab(de, r"^VERDICT_WHY=(.+)$", "判决形态说明").group(1).strip()
    N["verdict_why_body"] = N["verdict_why"].replace("**", "")
    m = _grab(de, r"^判据汇总：(\d+) 条 ｜ PASS (\d+) ｜ FAIL (\d+)$", "真数据判据小结")
    N["de_n"], N["de_pass"], N["de_fail"] = m.groups()
    N["de_ids"] = re.findall(r"^\[PASS\] (\S+)", de, re.M)

    # ---- 账本期望值 ----
    # ⚖⚠⚠⚠ **落账用**账本里的**原文**（⛔ 不用收据里 `%r` 的缩写）
    #   ⇒ 收据那行是 `print("...%r...")` ⇒ ⇒ 账本写的 `+0.026669793515452608`
    #     被印成 `0.02666979351545261` ⇒ ⇒ **同一个 double、两串字**
    #   ⇒ ⇒ 读者拿 244.85 的基线行去对 244.84 的表**对不上字** ⇒ ⇒ 会误以为数值不一致。
    m = _grab(de, r"^账本期望值（244\.84 段）：T=([-+0-9.eE]+) ｜ z=([-+0-9.eE]+) ｜ "
                   r"秩=([-+0-9.eE]+) ｜ 参考 sd=([-+0-9.eE]+) ｜ 理论 sd=([-+0-9.eE]+) ｜ "
                   r"FPR=([-+0-9.eE]+) ｜ 判决形态=(\S+)$", "账本期望值")
    (N["rc_T"], N["rc_z"], N["rc_rank"], N["rc_sd"], N["rc_theo"],
     N["rc_fpr"], N["exp_verdict"]) = m.groups()
    # ⚖⚖⚖ **账本原文**（244.84 段逐字读）⇒ ⇒ 落账引的就是**账本自己那一串**
    raw = ledger_24484_raw(_read(LEDGER))
    N["exp_T"], N["exp_z"], N["exp_rank"] = raw["T"], raw["z"], raw["rank"]
    N["exp_sd"], N["exp_theo"], N["exp_fpr"] = raw["sd"], raw["theo"], raw["fpr"]
    N["exp_md5"] = _grab(de, r"^账本 244\.78 段登记的 w_p2a\.npy md5：([0-9a-f]{32})",
                          "账本登记 md5").group(1)

    # ---- 16 个子集 ----
    subs = {}
    for m in re.finditer(
            r"^SUBSET\|([^|]+)\|n=(\d+)\|T=([-+0-9.eE]+)\|z=([-+0-9.eE]+)\|"
            r"rank=([-+0-9.eE]+)\|sd=([-+0-9.eE]+)\|theo=([-+0-9.eE]+)\|"
            r"sdrel=([-+0-9.eE]+)\|fpr=([-+0-9.eE]+)\|shape=(\S+)$", de, re.M):
        subs[m.group(1)] = {
            "n": int(m.group(2)), "T": float(m.group(3)), "z": float(m.group(4)),
            "rank": float(m.group(5)), "sd": float(m.group(6)), "theo": float(m.group(7)),
            "sdrel": float(m.group(8)), "fpr": float(m.group(9)), "shape": m.group(10),
            "z_s": m.group(4), "fpr_s": m.group(9), "sdrel_s": m.group(8),
            "T_s": m.group(3), "shape_s": m.group(10),
        }
    if len(subs) != 16:
        raise SystemExit("⛔ 从收据里抠到 %d 个子集（应为 16）⇒ ⇒ 那一段会是空的 ⇒ 中止" % len(subs))
    N["subs"] = subs
    N["decision"] = ["FULL", "LOO-m0", "LOO-m1", "LOO-real", "LOO-t1", "LOO-p2a", "LOO-old"]
    N["descriptive"] = ["STRAT-A", "CLU-A", "CLU-B", "SINGLE-m0", "SINGLE-m1",
                        "SINGLE-real", "SINGLE-t1", "SINGLE-p2a", "SINGLE-old"]
    for k in N["decision"] + N["descriptive"]:
        if k not in subs:
            raise SystemExit("⛔ 收据里缺子集 %s ⇒ ⇒ 中止" % k)
    N["ea_decision"] = [k for k in N["decision"] if subs[k]["shape"] == "E-A"]
    N["eb_decision"] = [k for k in N["decision"] if subs[k]["shape"] == "E-B"]

    # ---- H6：跨轮对账（取每一项的「差 / 上限」，算最大占用比）----
    h6 = _grab(de, r"^\[PASS\] H6-CROSSROUND\s+(.*)$", "H6").group(1)
    pairs = re.findall(r"（差 ([-+0-9.eE]+)，上限 ([-+0-9.eE]+)）", h6)
    if not pairs:
        raise SystemExit("⛔ H6 行里抠不到「（差 …，上限 …）」⇒ ⇒ 中止")
    N["h6_pairs"] = pairs
    N["h6_max_ratio"] = max((float(d) / float(t) if float(t) else 0.0) for d, t in pairs)
    N["h6_zero"] = sum(1 for d, t in pairs if float(d) == 0.0)
    N["h6_n"] = len(pairs)
    # ⚖⚖⚖ **逐项的「实测 / 账本」两串字**（⛔ H6 只印了差值与上限 ⇒ ⇒ 这里补上出处）
    h6_items = {}
    for mm in re.finditer(r"([^：｜]+)：实测 ([-+0-9.eE]+) vs 账本 ([-+0-9.eE]+)"
                          r"（差 ([-+0-9.eE]+)，上限 ([-+0-9.eE]+)）", h6):
        h6_items[mm.group(1).strip()] = (mm.group(2), mm.group(3), mm.group(4), mm.group(5))
    N["h6_items"] = h6_items
    # ⚖⚖⚖⚖⚖ **位级闸**：H6 说「差 0」的那几项，**实测与账本必须是同一个 double**
    #   ⇒ ⇒ 这是「基线逐位相同」这句话的**机械出处**（⛔ 不是「相对差 ≤ 1e-12」的推论）
    #   ⇒ ⇒ H13-BITIDENT 就是这条的**判据化**（在实现里跑）
    for label, key in (("类级 T", "T"), ("类级 z_T", "z"), ("类级秩", "rank"),
                       ("类级参考 sd", "sd"), ("类级理论 sd", "theo"), ("类级 FPR", "fpr")):
        if label not in h6_items:
            raise SystemExit("⛔ H6 行里抠不到「%s」这一项 ⇒ ⇒ 位级闸无从下手 ⇒ 中止" % label)
        meas, led, diff, _tol = h6_items[label]
        if float(diff) != 0.0:
            raise SystemExit("⛔ H6 的「%s」差值不是 0（%s）⇒ ⇒ 基线不是逐位复现 ⇒ 中止"
                             % (label, diff))
        if _bits(meas) != _bits(N["exp_%s" % key]):
            raise SystemExit("⛔ H6 实测（%s）与账本原文（%s）**不是同一个 double** ⇒ ⇒ 中止"
                             % (meas, N["exp_%s" % key]))
        if _bits(meas) != _bits(N["rc_%s" % key]):
            raise SystemExit("⛔ H6 实测（%s）与收据「账本期望值」那行（%s）**不是同一个 double**"
                             " ⇒ ⇒ 中止" % (meas, N["rc_%s" % key]))
    N["h6_bitident"] = 6

    # ---- H7 / H8 / H9 / H10 / H11 / H12 ----
    N["h7"] = _grab(de, r"^\[PASS\] H7-FULLFORM\s+(.*)$", "H7").group(1)
    N["h8_max"] = max(v["sdrel"] for v in subs.values())
    N["h9_max"] = max(v["fpr"] for v in subs.values())
    N["h8_txt"] = _grab(de, r"^\[PASS\] H8-CALIB\s+(.*)$", "H8").group(1)
    N["h9_txt"] = _grab(de, r"^\[PASS\] H9-DISC\s+(.*)$", "H9").group(1)
    N["h10"] = _grab(de, r"^\[PASS\] H10-NEGCTL\s+(.*)$", "H10").group(1)
    N["h10_z"] = _grab(de, r"置换（种子 (\d+)\+i）后：z_T=([-+0-9.eE]+)", "H10 z").groups()
    N["h10_pc"] = _grab(de, r"置换后两两余弦 max=([-+0-9.eE]+)（上限 ([-+0-9.eE]+)", "H10 pc").groups()
    N["h11"] = _grab(de, r"^\[PASS\] H11-SELFINCLUDE\s+(.*)$", "H11").group(1)
    N["h11_alt"] = _grab(de, r"含构造种子的参考集（(\d+)\.\.(\d+)）算出的 z_T=([-+0-9.eE]+)"
                          r"（判 (\S+)；账本登记 ([-+0-9.eE]+)）vs 不含的 z_T=([-+0-9.eE]+)（判 (\S+)）",
                          "H11 数字").groups()
    N["h12"] = _grab(de, r"^\[PASS\] H12-MAXCOS\s+(.*)$", "H12").group(1)
    N["h12_maxnm"] = _grab(de, r"本轮实测：余弦最大的那把 = (\S+)", "H12 最大").group(1)
    N["h12_maxcos"] = _grab(de, r"余弦最大的那把 = \S+（([-+0-9.eE]+)）", "H12 值").group(1)

    # ---- H1 / H2 / H4 ----
    N["h1"] = _grab(de, r"^\[PASS\] H1-IDENT\s+(.*)$", "H1").group(1)
    N["h1_md5"] = _grab(de, r"实测 md5=([0-9a-f]{32}) == 账本登记 ([0-9a-f]{32})", "H1 md5").groups()
    N["h2"] = _grab(de, r"^\[PASS\] H2-PROVENANCE\s+(.*)$", "H2").group(1)
    N["h2_layer"], N["h2_seed"], N["h2_nmark"] = _grab(
        de, r"6 把 sidecar：layer=(\d+) seed=(\d+) marker_ids（(\d+) 个逐个相同）", "H2 数字").groups()
    N["h4"] = _grab(de, r"^\[PASS\] H4-NOSHAREDSTREAM\s+(.*)$", "H4").group(1)
    N["h5"] = _grab(de, r"^\[PASS\] H5-FAMILY\s+(.*)$", "H5").group(1)

    # ---- 描述量 D1..D7 ----
    N["d1"] = _grab(de, r"^  D6 污染量级（244\.84 登记，本轮复算）：(.*)$", "D6").group(1)
    N["d1_cos"], N["d1_pct"], N["d1_c"], N["d1_gap"], N["d1_equiv"] = _grab(
        de, r"cos\(w_p2a, r₀\)=([-+0-9.eE]+) ⇒ w 能量占比 ([-+0-9.eE]+)% ｜ "
        r"w 等效剂量 = ([-+0-9.eE]+) × ([-+0-9.eE]+) = ([-+0-9.eE]+)", "D6 数字").groups()
    N["d5"] = _grab(de, r"^  D5 两两余弦：(.*)$", "D5").group(1)
    N["d4"] = _grab(de, r"^  D4 单向量族（.*$", "D4").group(0)
    N["d3"] = _grab(de, r"^  D3 FPR_n 随 n：(.*)$", "D3").group(1)

    # ---- 变异台 ----
    m = _grab(mu, r"变异台：抓到 (\d+) / (\d+)（无效 (\d+) 条", "变异台小结")
    N["mut_caught"], N["mut_total"], N["mut_invalid"] = m.groups()
    N["mut_crash"] = _grab(mu, r"崩的条数：(\d+)", "崩计数").group(1)
    N["mut_ids"] = re.findall(r"^\[(?:抓到|硬停抓到)\] (\S+)", mu, re.M)
    N["mut_missed"] = re.findall(r"^\[没抓到\] (\S+)", mu, re.M)

    # ---- 互证 ----
    N["cr_items_ok"] = _grab(cr, r"^CROSS\|items_ok=(\d+)$", "互证计数").group(1)
    N["cr_mismatch"] = _grab(cr, r"^CROSS\|mismatches=(\d+)$", "互证 MISMATCH").group(1)
    N["cr_verdict"] = _grab(cr, r"^CROSS\|verdict=(\S+)$", "互证判决形态").group(1)
    N["cr_subsets"] = _grab(cr, r"^CROSS\|subsets=(\d+)$", "互证子集数").group(1)

    # ---- 跨路线差值（⚖ **差值要单独存**：⛔ 不能只说「在容差内」）----
    xr = {}
    for ln in cr.splitlines():
        if not ln.startswith("CROSSROUTE|"):
            continue
        parts = ln.split("|")
        kv = {}
        rest = parts[2:]
        # ⚖⚠ `CROSSROUTE|FULL|类级 T|py=…` 的**第 3 格是位置标签**（不带 `=`）
        #   ⇒ ⇒ 而 `CROSSROUTE|SUMMARY|max_rel=…` 的第 3 格**就是** kv
        #   ⇒ ⇒ 按「有没有 =」区分，⛔ 不许一律当 kv（那会把标签丢掉）
        if rest and "=" not in rest[0]:
            kv["name"] = rest[0]
            rest = rest[1:]
        for p in rest:
            if "=" in p:
                k, v = p.split("=", 1)
                kv[k] = v
        xr.setdefault(parts[1], []).append(kv)
    for t in ("SUMMARY", "FULL", "LEDGER"):
        if t not in xr:
            raise SystemExit("⛔ 互证收据里抠不到 CROSSROUTE|%s 块 ⇒ ⇒ 跨路线差值没被单独存 ⇒ 中止" % t)
    N["xr_sum"] = xr["SUMMARY"][0]
    N["xr_full"] = xr["FULL"]
    N["xr_ledger"] = xr["LEDGER"]
    # ⚖⚖⚖ **正面核对**：FULL 的 6 项（numpy 路线 vs 账本主表）必须**逐位**相同
    #   ⇒ ⇒ 这是「基线逐位相同」这句话在**收据层**的出处（实现层由 H13 守）
    for it in N["xr_ledger"]:
        if it.get("identical") != "yes":
            raise SystemExit("⛔ 互证的 CROSSROUTE|LEDGER|%s 不是逐位相同（%s）⇒ ⇒ 中止"
                             % (it.get("name", "?"), it))
    N["xr_ledger_n"] = len(N["xr_ledger"])

    # ---- 预登记 ↔ 实现 对账 ----
    m = _grab(sp, r"对账条数：OK (\d+) ｜ 红 (\d+)", "对账计数")
    N["sp_ok"], N["sp_bad"] = m.groups()
    N["sp_cannot"] = re.findall(r"^   · (.+)$", sp, re.M)

    # ---- 收据：字节 md5 ----
    N["rc_host"] = _grab(rc, r"^host=(\S+)\s+date=", "收据主机").group(1)
    N["rc_rcs"] = _grab(rc, r"^SELFTEST_RC=(\d+)\s+DE_RC=(\d+)\s+MUT_RC=(\d+)\s+"
                           r"CROSS_RC=(\d+)\s+SPEC_RC=(\d+)$", "收据退出码").groups()
    N["rc_md5"] = dict((v, k) for k, v in re.findall(r"^([0-9a-f]{32})\s+(\S+)$", rc, re.M))
    if not N["rc_md5"]:
        raise SystemExit("⛔ 收据里核不到任何字节 md5 ⇒ 字节清单无出处 ⇒ 中止")
    N["rc_md5_base"] = dict((os.path.basename(k), v) for k, v in N["rc_md5"].items())
    m = _grab(rc, r"^--- bpath 产物 md5 ---\n((?:[0-9a-f]{32}\s+\S+\n)+)", "bpath 字节块")
    N["rc_bpath"] = re.findall(r"^([0-9a-f]{32})\s+(\S+)$", m.group(1), re.M)
    m = _grab(rc, r"^--- 收据文件 md5 ---\n((?:[0-9a-f]{32}\s+\S+\n)+)", "收据文件字节块")
    N["rc_out"] = re.findall(r"^([0-9a-f]{32})\s+(\S+)$", m.group(1), re.M)
    return N


def build(N):
    """⚖ 组装追加段（⛔ **不许有围栏**、⛔ **不许有反斜杠**）。"""
    L = []
    A = L.append
    S = N["subs"]
    A(TITLE + "⚖⚖⚖⚖⚖ **「244.84 的『类级结构』是不是被**剂量批那一把** `w_p2a` 撑起来的？**」"
      "—— ⇒ ⇒ **留一法（LOO）**把 N=6 的类级结论拆成 16 个子集各自重算"
      "⇒ ⇒ 判决形态 **%s**" % N["verdict"])
    A("")
    A("⚖ **口径真相源**：`.cache/xcheck/R6_LOO_ROBUSTNESS_PREREG.md`（244.85 签，**先于实现**、"
      "**先于 6 个 LOO 与 6 个 SINGLE 的结果**）")
    A("⚖ **数据**：bpath 的 6 把 w 向量 ＋ 各自 sidecar ＋ `r241_probe.py` ＋ `r244_warm_sweep.sh`"
      " ＋ 两臂原始日志（⛔ 只读、⛔ 零 GPU、远端 `zju-53`）")
    A("⚖ **接的是 244.84 的哪一句**：244.84 判「**结构**」（类级 `z_T = %s`）⇒ ⇒ "
      "但它自己登记的事实里，**剂量批用的那把 `w_p2a` 恰好是对齐最高的那把**"
      "（余弦 %s，6 把里最大）⇒ ⇒ 那一簇（簇 A）的 z=%s、另一簇（簇 B）的 z=%s "
      "⇒ ⇒ 「类级结构」这句话**可能是被那一把撑起来的** ⇒ ⇒ **本轮判这个**。"
      % (N["exp_z"], N["h12_maxcos"], N["subs"]["CLU-A"]["z_s"], N["subs"]["CLU-B"]["z_s"]))
    A("")
    A("### 【1】⚖⚖⚖ **一句话**")
    A("")
    A("> **判决形态 %s** —— ⇒ ⇒ 「244.84 的『`r₀` **系统性地**落在 steering 向量的公共方向上』"
      "这一句，对**纳入哪几把 w** 敏不敏感？」⇒ ⇒ **本轮把它判成 %s**（%s）。"
      % (N["verdict"], N["verdict"], N["verdict_why_body"]))
    A("")
    A("⚖⚖⚖ **手法**：**换掉「纳入哪几把」，不换 `r₀`** ⇒ ⇒ 对 **16 个子集**"
      "（FULL n=6 ｜ 6 个 LOO n=5 ｜ STRAT-A n=4 ｜ 簇 A/B n=3 ｜ 6 个 SINGLE n=1）"
      "各自**重算**类级统计量 ⇒ ⇒ **每个子集有自己的零分布、自己的 sd、自己的经验假阳性率 FPR_n**"
      "（⛔ n=6 的 FPR 不许套到 n=5）。")
    A("")
    A("### 【2】📊 **判决面板（留一 · 决策族）**")
    A("")
    A("| 子集 | n | T | z_T | FPR_n | 形态 |")
    A("|---|---|---|---|---|---|")
    for k in N["decision"]:
        s = S[k]
        A("| **%s** | %d | %+.9f | **%+.4f** | %.5f | **%s** |"
          % (k, s["n"], s["T"], s["z"], s["fpr"], s["shape"]))
    A("")
    A("| 量 | 值 | 判据 |")
    A("|---|---|---|")
    A("| **基线** FULL 的类级统计量 | T=%s ｜ z_T=%s ｜ 秩 %s ｜ 参考 sd %s ｜ 理论 sd %s ｜ FPR %s | "
      "与账本 244.84 段**逐项对账**（%d 项里 **%d 项差 0**，其余都在容差内；最大「差/上限」= %.3g）"
      "⇒ ⇒ **基线可复现**；⚖ 其中 **%d 项（类级 T / z_T / 秩 / 参考 sd / 理论 sd / FPR）"
      "与 244.84 主表是**同一个 double**（H13 位级对账，⛔ 不是「相对差 ≤ 1e-12」） |"
      % (N["exp_T"], N["exp_z"], N["exp_rank"], N["exp_sd"], N["exp_theo"], N["exp_fpr"],
         N["h6_n"], N["h6_zero"], N["h6_max_ratio"], N["h6_bitident"]))
    A("| **关键位**（去掉剂量批那一把） | `LOO-p2a` 的 z_T=**%s** ⇒ 判 **%s** | 判决阈值 2.0 |"
      % (S["LOO-p2a"]["z_s"], S["LOO-p2a"]["shape"]))
    A("| **决策族里掉出阈值的子集** | %s（共 %d / %d 个） | ⇒ ⇒ 类级结论**依赖这些成员** |"
      % ("、".join(N["ea_decision"]), len(N["ea_decision"]), len(N["decision"])))
    A("| **逐 n 判别力**（每个子集自己的 FPR_n） | 最大 %.5f（上限 0.05） | H9 ⇒ ⇒ 规则**逐 n 都可用** |"
      % N["h9_max"])
    A("| **逐子集校准**（参考 sd vs 理论 ‖m_S‖/√d） | 最大相对差 %.6f（上限 0.05） | H8 ⇒ ⇒ 零分布**逐子集被校准** |"
      % N["h8_max"])
    A("| **自包含闸**（构造种子 42 vs 类级参考区间 100001..102000） | 交集 ∅ ｜ 含它的参考集 z_T=%s（判 %s）vs 不含 %s（判 %s） | H11 ⇒ ⇒ 自包含**没有影响判决** |"
      % (N["h11_alt"][2], N["h11_alt"][3], N["h11_alt"][5], N["h11_alt"][6]))
    A("| **负控**（6 把各自独立坐标置换） | z_T=%s（z 的绝对值上限 2.0）｜ 置换后两两余弦 max=%s（上限 %s） | H10 ⇒ ⇒ 负控通过（无结构时**不该**触发） |"
      % (N["h10_z"][1], N["h10_pc"][0], N["h10_pc"][1]))
    A("")
    A("### 【3】🔍 **16 个子集逐条（描述族也一并登记，⛔ 不进判决）**")
    A("")
    A("| 子集 | n | T | z_T | 秩 | 参考 sd | 理论 sd | sd 相对差 | FPR_n | 形态 |")
    A("|---|---|---|---|---|---|---|---|---|---|")
    for k in sorted(S.keys(), key=lambda x: (S[x]["n"], x)):
        s = S[k]
        A("| %s | %d | %+.9f | %+.4f | %.5f | %.9f | %.9f | %.6f | %.5f | %s |"
          % (k, s["n"], s["T"], s["z"], s["rank"], s["sd"], s["theo"], s["sdrel"],
             s["fpr"], s["shape"]))
    A("")
    A("⚖ **决策族 vs 描述族**（预登记 §2.2 的理由）：决策族 = FULL ＋ 6 个 LOO；"
      "描述族 = STRAT-A / 簇 A / 簇 B / 6 个 SINGLE（**算出来、登记，不决定形态**）"
      "⇒ ⇒ 理由：簇与分层**换的是总体**、不是「同一总体去掉一把」；"
      "⛔ 且 `CLU-B` 的 z=%s **必定**是 E-A ⇒ ⇒ 若把簇放进决策族，**F-A 就是死分支** ⇒ ⇒ 只放描述族。"
      % S["CLU-B"]["z_s"])
    A("")
    A("### 【3-B】⚖⚖⚖ **跨路线差值（单独存）—— 「逐位」这句话的边界**")
    A("")
    A("⚖ **为什么单列这一段**：H6 的容差是「相对差 ≤ 1e-12」⇒ ⇒ **差 1 个 ULP（约 1.3e-16 相对）"
      "照样过** ⇒ ⇒ 「差 0」与「差 3 个 ULP」在容差口径下**长得一模一样** ⇒ ⇒ "
      "「本轮与账本 244.84 **逐位相同**」这句话**能不能说**取决于差值本身 ⇒ ⇒ "
      "所以差值**单独算、单独印、单独落账**（互证脚本的 `CROSSROUTE|...` 块）。")
    A("")
    A("| 比的是 | 纯 Python 路线 | numpy 路线 | 相对差 | ULP 差 | 逐位相同 |")
    A("|---|---|---|---|---|---|")
    for it in N["xr_full"]:
        A("| FULL %s | `%s` | `%s` | %s | **%s** | %s |"
          % (it.get("name", "?"), it.get("py", "?"), it.get("np", "?"),
             it.get("rel", "?"), it.get("ulp", "?"),
             "✅ 是" if it.get("identical") == "yes" else "⛔ **否**"))
    A("")
    A("- **两条路线的最大差**：相对差 `%s`（出现在 `%s`）｜ ULP 差 **%s**（出现在 `%s`）｜ "
      "逐位相同的项 **%s**（分母 %s）"
      % (N["xr_sum"].get("max_rel", "?"), N["xr_sum"].get("at", "?"),
         N["xr_sum"].get("max_ulp", "?"), N["xr_sum"].get("ulp_at", "?"),
         N["xr_sum"].get("identical", "?"),
         (N["xr_sum"].get("identical", "0").split("/")[1]
          if "/" in N["xr_sum"].get("identical", "") else "?")))
    A("- **numpy 路线 vs 账本 244.84 主表**：**%d 项全部逐位相同**（ULP 差 0）⇒ ⇒ "
      "「逐位」这句话**只限「同一条实现路线」** ⇒ ⇒ ⛔ **不许**推广成「跨实现逐位可复现」。"
      % N["xr_ledger_n"])
    A("")
    A("### 【4】✅ **判据与变异台（每条判据能红）**")
    A("")
    A("- **自检**（Phase-0 G0-1..G0-7，合成夹具、零 bpath、零 GPU）：判据 %s 条 ｜ FAIL %s 条"
      % (N["st_n"], N["st_fail"]))
    A("- **变异台**：抓到 **%s / %s**（无效 %s 条 ⇒ 记「无效」⇒ 不计入分母）｜ 崩的条数 **%s**（⛔ 必须是 0）"
      % (N["mut_caught"], N["mut_total"], N["mut_invalid"], N["mut_crash"]))
    A("- **互证**（第二条独立实现，纯 Python 路线 vs numpy 路线）：%s 个子集 ｜ OK **%s** ｜ MISMATCH **%s** ｜ "
      "判决形态 **%s**" % (N["cr_subsets"], N["cr_items_ok"], N["cr_mismatch"], N["cr_verdict"]))
    A("- **预登记 ↔ 实现 的机械对账**：OK **%s** ｜ 红 **%s**" % (N["sp_ok"], N["sp_bad"]))
    A("- **真数据判据**：%s 条 ｜ PASS **%s** ｜ FAIL **%s**"
      % (N["de_n"], N["de_pass"], N["de_fail"]))
    A("- 真数据判据逐条：%s" % "、".join(N["de_ids"]))
    A("- 变异台逐条：%s" % "、".join(N["mut_ids"]))
    A("")
    A("### 【5】⚠⚠⚠ **三条更正 ＋ 两条发现（撤回并更正，⛔ 不改数凑好看）**")
    A("")
    A("⚖ **这四条全部写在预登记 §0.5 里**（含「发生时机」与「有没有改动实测数」）"
      " ⇒ ⇒ **口径真相源 = 预登记**，不是实现。")
    A("")
    A("1. **更正 ①：F-B 的「降级措辞」** —— 预登记 §4.3 的 F-B 行原写「『类级结构』降级为"
      "『**这一对**（`w_p2a`, `r₀`）的现象』」⇒ ⇒ 但实测 **`LOO-m1`（z=%s）** 与 "
      "**`LOO-t1`（z=%s）** 也**掉出阈值** ⇒ ⇒ 去掉**簇 A 的任意一把**都会让类级结论掉出阈值 "
      "⇒ ⇒ 准确的降级对象是「**簇 A 相对 `r₀` 的对齐**」，⛔ 不是「`w_p2a` 与 `r₀` 这一对」。"
      "⚖ **有没有改动实测数**：⛔ **没有，一个都没有**。"
      "⚖ **有没有改动判决形态与触发条件**：⛔ **没有**（§3.1 的 F-B 触发条件"
      "「`LOO-p2a`=E-A」**一字未改**，实测满足 ⇒ ⇒ **形态仍是 F-B**）⇒ ⇒ 改的只有**解释层**。"
      "⚖ **代价**：预登记 md5 变了 ⇒ ⇒ 字节清单重出、收据重出、验证链**重跑** ⇒ ⇒ 这是如实记账的代价。"
      % (S["LOO-m1"]["z_s"], S["LOO-t1"]["z_s"]))
    A("2. **发现 ①：⚠⚠⚠ 244.84 的 H1 实现比它自己的预登记松** —— 244.84 的预登记写的是"
      "「`.npy` 的 md5 **==** 账本登记值」，而 244.84 的实现取的是「实测 md5 **∈ 三个候选**」"
      "（账本那一行**同时**登记了 `w_p2a.npy` / `w_p2a.npy.json` / `train_p2a.log` 三个 md5）"
      "⇒ ⇒ 本轮按**预登记**实现（取「`w_p2a.npy` 之后出现的第一个 md5」＝向量自己的那一个）"
      "⇒ ⇒ 244.84 的 H1 在收紧后**仍然绿**（实测 md5 = `%s`）⇒ ⇒ 这是**判据收紧**，⛔ 不是「改数」。"
      % N["h1_md5"][0])
    A("3. **更正 ③：⚠ 账本 244.84 段【4】那行「互证逐位」的标签不准确** —— "
      "那行里的类级 T `%s` 与类级 z `%s`，与**同一段主表**的 `%s` / `%s` "
      "**不是同一个 double**（差 3 ULP / 2 ULP）⇒ ⇒ 「**逐位**」这个标签**写错了**。"
      "⚖ **正面证据（那行的数本身没错）**：本轮**纯 Python 路线**算出的 FULL 类级 "
      "T=`%s`、z=`%s`，与那一行**逐位相同** ⇒ ⇒ 那行的数**来自 244.84 自己的纯 Python 互证路线** "
      "⇒ ⇒ **数没错，错的是标签**（与 244.84 自己预登记的更正 ①「跨实现口径下『逐位相同』不成立」一致）。"
      "⚖ **改法**：⛔ **只更正标签**（「互证逐位」→「互证（纯 Python 路线）」）、⛔ **不改任何数**；"
      "账本**只追加** ⇒ ⇒ 244.84 段的**原文一字不动**，本条作为更正登记在这里。"
      "⚖ **有没有改动实测数**：⛔ **没有，一个都没有**。"
      % (N["xr_full"][0].get("py", "?"), N["xr_full"][1].get("py", "?"),
         N["exp_T"], N["exp_z"],
         N["xr_full"][0].get("py", "?"), N["xr_full"][1].get("py", "?")))
    A("4. **发现 ②：⚠⚠⚠ H6 的「差 0」是「同一条实现路线」的结果** —— 本轮**同一份数据、同一套种子区间**，"
      "两条实现路线对 FULL 的类级统计量给出**两个不同的 double**：numpy 路线 `%s` / `%s`，"
      "纯 Python 路线 `%s` / `%s` ⇒ ⇒ **差 3 ULP / 2 ULP** ⇒ ⇒ "
      "**H6 绿（相对差 ≤ 1e-12）推不出「与账本是同一个 double」** ⇒ ⇒ "
      "「逐位」这句话**只限同一条实现路线内**成立（跨路线差值已**单独存**在【3-B】）。"
      "⚖ **处置**：本轮因此把「位级相同」单独做成**硬判据 H13-BITIDENT**（比 H6 严一档），"
      "并用变异台 **PL3**（把**账本副本**里 244.84 的类级 T **挪 1 个 ULP**）证明它**能红**、"
      "**而 H6 照样绿** ⇒ ⇒ 证明「逐位」这条守卫**真的在比位**、⛔ 不是容差的同义词。"
      "⚖ **有没有改动实测数**：⛔ **没有**。⚖ **有没有改动判决形态与触发条件**：⛔ **没有**"
      "（F-B 的触发条件「`LOO-p2a`=E-A」一字未改；H13 实测**绿** ⇒ ⇒ 形态仍是 F-B）；"
      "⚠ 但**要说清楚**：H13 是**事后**加的（真数据首跑之后）⇒ ⇒ **假如它当初是红的，形态会是 FAIL** "
      "⇒ ⇒ 加它**有可能**改变结论 ⇒ ⇒ 但它实测是绿的 ⇒ ⇒ **结论未变**。"
      % (N["xr_full"][0].get("np", "?"), N["xr_full"][1].get("np", "?"),
         N["xr_full"][0].get("py", "?"), N["xr_full"][1].get("py", "?")))
    A("")
    A("⚖⚖⚖ **顺带确认（不是更正，只是把实测写清楚）**：更窄的那一句站得住 —— "
      "「`r₀` 与**簇 A** 显著对齐」（`CLU-A` 的 z=%s，该 n 自己的 FPR_n=%.5f ≤ 0.05），"
      "而**与簇 B 不对齐**（`CLU-B` 的 z=%s）。⚖ 但这**不是本轮的发现** —— "
      "`CLU-A` 的 z=+2.393 是 **244.84 已登记**的事实 ⇒ ⇒ 它是**复算**，⛔ 不是挑出来的。"
      "⚠⚠⚠ **代价要说清楚**：本轮扫了 **16 个子集** ⇒ ⇒ 单点 FPR 在**族内**不再是那个数 "
      "⇒ ⇒ 只能写成「**在 244.84 预先登记的簇 A 上复现了离群**」，⛔ **不许**写成"
      "「16 个子集里唯一显著的那个」（那正是多重比较的错）。"
      % (S["CLU-A"]["z_s"], S["CLU-A"]["fpr"], S["CLU-B"]["z_s"]))
    A("")
    A("### 【6】⛔ **边界清单（本轮哪些仍未量到）**")
    A("")
    A("- ⛔ **「`r₀` 系统性地落在 steering 向量的公共方向上」仍然未量到** —— 本轮把它判成 F-B "
      "⇒ ⇒ 那句话**降级**为「`r₀` 与**簇 A** 显著对齐」这一条**更窄**的事实 "
      "⇒ ⇒ 「系统性重叠」**未量到**（⛔ 不是「无差异」）。")
    A("- ⛔ **「污染对改判率的影响」仍然未量到** —— 固定剂量批**没落盘 alpha 轨迹**"
      "（跑批器调探针时**没传 `--dump-raw`**）⇒ ⇒ 离线**算不出**「污染最多能翻多少格」；"
      "且 w 臂在 **w 剂量 %s** 处的响应**未量到**、单调性**未量到** ⇒ ⇒ "
      "本轮只登记**条件命题**：污染在 rand 臂最大剂量处等效于一次 **w 剂量 %s** 的注入，"
      "⛔ 两条前提未实测 ⇒ ⇒ **不进判决**。" % (N["d1_equiv"], N["d1_equiv"]))
    A("- ⛔ **「换个 w 也会被同样污染」未量到** —— 本轮只验了「**去掉一把**」这一族变换 ⇒ ⇒ "
      "「**换一批完全不同的 w**」的稳健性**未量到**。")
    A("- ⛔ **「6 把 w 代表全部 steering 向量」的外推** ⇒ ⇒ **未量到**（6 把是**同一套 recipe** 的 "
      "6 个解：同 marker 集、同训练种子 %s、同层 ⇒ ⇒ 结论的外推范围仅限「同一 recipe 的解」。"
      % N["h2_seed"])
    A("- ⛔ **「多随机种子的对照臂」** ⇒ ⇒ 仍然**未量到**（本轮还是**一个** `r₀` ⇒ ⇒ "
      "**r 那一侧仍是 N=1**）⇒ ⇒ 要 K 臂跑批。")
    A("- ⛔ **「哪一条臂是机制效应」** ⇒ ⇒ 沿用旧留白，**未量到**（要「同结论对照臂」）。")
    A("- ⛔ 远端 tokenizer 快照的内容指纹、**照 meta 重建能否逐位复现** ⇒ ⇒ 沿用旧留白，**未量到**。")
    A("")
    A("### 【7】▶️ **下一轮（244.86+）**")
    A("")
    A("1. **固定剂量批重跑并加 `--dump-raw`** ⇒ ⇒ 拿到 60 点全曲线 ⇒ ⇒ 离线把 w 臂曲线缩放到 "
      "**%s** 剂量 ⇒ ⇒ 直接算「污染最多能翻多少格」⇒ ⇒ 把条件命题变成实测。"
      "⚖ 这是**现在**最靠近判决数、且**不依赖**任何未决口径的一步。" % N["d1_equiv"])
    A("2. **多随机种子的对照臂**（把 **r 那一侧**也从 N=1 变成 N=K）⇒ ⇒ "
      "这是把「对照臂对齐度」从 N=1 变成**分布**的正解。")
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
    A("⚖ **远端**：`%s` ｜ ⛔ **零 GPU**、⛔ 没跑批、⛔ 没改读数器/探针/拆分器、"
      "⛔ 没改 244.79–244.84 段。" % N["rc_host"])
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
            print("✅ 幂等：账本里已有的 244.85 段与**收据算出来的那段逐字节相同**"
                  " ⇒ ⇒ 不重复写（本次落账无需再动）")
            return 0
        raise SystemExit("⛔ 账本里已有 244.85 段，但它与收据算出来的**不一致** ⇒ ⇒ 停下"
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
