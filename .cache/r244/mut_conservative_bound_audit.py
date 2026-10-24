#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""mut_conservative_bound_audit.py —— **保守读法与口径边界**的变异台（244.88）。

⚖⚖⚖⚖⚖ **这个台架要回答的问题**
   「`conservative_bound_audit.py` 的每条判据**是不是恒绿的**？」
   ⇒ ⇒ 必须证明它们**能红**：
     · **实现被改**（形态级联 / 判据的比较方向 / 加法公式 / 量纲护栏 / 容差 / 锚点唯一性 / …）
       ⇒ ⇒ 对应判据（或对应 Phase-0 闸门）必须由 PASS 变 FAIL；
     · **账本被改**（把某个输入删掉 / 改掉）⇒ ⇒ 必须判红或**硬失败**
       （⛔ 不是判红、⛔ 不是「跳过」⇒ ⇒ 这条纪律单独有变异体守着）。

⚖⚖⚖⚖⚖ **纪律（从 244.66–244.87 的台架继承，一条都不许放松）**
   ① 每条变异只改**一处**（⛔ 改多处 ⇒ 抓到了也不知道是哪一处抓的）；
   ② 每条变异必须**恰好命中 1 处**（⛔ 命中 0 ⇒ 这条变异**无效** ⇒ 必须报出来；
      ⛔ **等价变异（什么都没变）记「无效」，⛔ 不是「存活」**）；
   ③ ⛔ **「崩」≠「抓到」** ⇒ 崩了单独报 ⇒ 崩的条数必须压到 **0**；
   ④ **阳性对照先过**：不改任何东西时，目标必须**跑出判决形态** ⇒ ⇒
      否则「全红」什么也证明不了 ⇒ ⇒ 直接退出；
   ⑤ 期望的「哪条该红」是**手写**的 ⇒ ⇒ **不许从被检对象派生**；
   ⑥ ⛔ 本台架**不改**目标实现、⛔ 不改预登记、⛔ 不改原始账本
      ⇒ ⇒ 账本变异只发生在**临时目录里的副本**上；
   ⑦ ⛔ 缺前置 ⇒ 报 **`PRECOND_FAIL`**（⛔ 这样回归器才判「跑不动」，
      ⛔ **不是**「本轮引入的红」⇒ ⇒ 冤枉）；
   ⑧ ⚖ **「把容差改紧 ⇒ 判据变红」也算一种合法变异**。

⚖⚖⚖⚖⚖ **244.88 特有的一条纪律**
   变异台**同时断言判决形态**（`EXPECT_VERDICT`）
   ⇒ ⇒ 「改级联 ⇒ 形态错」这条承诺才不是空话
   ⇒ ⇒ 五个形态（A′ / B′ / C′ / D′ / E′）的**可达性**由 Phase-0 的 G0-2（穷举）守。

⚖⚖⚖⚖⚖ **为什么有些变异走 "self"（--selftest）而不是 "data"（--data）**
   ⇒ ⇒ 「把一条判据改成**恒绿**」这种变异，在真数据上**看不出来**（真数据本来就是绿的）
   ⇒ ⇒ 只能靠 **Phase-0 的合成夹具**把它逼红 ⇒ ⇒ 那些变异走 "self"
   ⇒ ⇒ ⛔ 而「把一条判据改成**恒红**」的变异，在真数据上会**改变判决形态** ⇒ ⇒ 走 "data"。
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.environ.get("R244_LEDGER", "/home/zhourui/steer3d/.cache/xcheck/R6_RERUN_PREREG.md")
TARGET = "conservative_bound_audit.py"
PY = os.environ.get("R244_PY", "/home/zhourui/miniconda3/envs/easysteer/bin/python")

# ⚖ 判据 id（真数据路径印的是这些）
CRIT_RE = re.compile(r"^\[(PASS|FAIL)\]\s+(\S+)", re.M)
GATE_RE = re.compile(r"^\[(PASS|FAIL)\]\s+(G0-\d)", re.M)
CRASH_RE = re.compile(r"^(Traceback \(most recent call last\)|\w*(?:Error|Exception)\b)", re.M)
VERDICT_RE = re.compile(r"^VERDICT=(\S+)$", re.M)
HARDFAIL_RE = re.compile(r"HARD_FAIL:")

# ⚖ (编号, 类别, 模式, 落点串, 替换串, 期望红的 id, 期望的判决形态, 说明)
#    模式 "self" = 跑 `--selftest`（⛔ 不依赖账本）；"data" = 跑真数据路径
#    类别 "impl" = 改**实现源码副本**；"ledger" = 改**账本副本**
#    期望形态 None = 不要求（但**打出来**）
MUTATIONS = [
    # ---------------- 实现被改：形态的落态级联（self ⇒ G0-2 穷举必须红）----------------
    ("MU1", "impl", "self", 'HARD_FAIL_IDS = ("H1", "H2", "H8", "H9")',
     'HARD_FAIL_IDS = ("H1", "H2", "H8")',
     ["G0-2"], None,
     "⚖⚖⚖⚖⚖ **硬失败集合里被拿掉 H9** ⇒ ⇒ 「H9 红」不再落 E′ ⇒ ⇒ G0-2 的穷举必须红 "
     "⇒ ⇒ 证明「H9 红 ⇒ 形态 E′」这条归属**被钉住**了"),
    ("MU2", "impl", "self", '    if not flags.get("H7", True):\n        return FORM_Bp',
     '    if False:\n        return FORM_Bp',
     ["G0-2"], None,
     "⚖⚖⚖⚖⚖ **级联里的 B′ 那一支被改成不可达** ⇒ ⇒ G0-2 必须红 ⇒ ⇒ **B′ 不是死代码**"),
    ("MU3", "impl", "self", '    if not flags.get("H5", True) or not flags.get("H6", True):\n        return FORM_Cp',
     '    if False:\n        return FORM_Cp',
     ["G0-2"], None,
     "⚖⚖⚖⚖⚖ **级联里的 C′ 那一支被改成不可达** ⇒ ⇒ G0-2 必须红 ⇒ ⇒ **C′ 不是死代码**"),
    ("MU4", "impl", "self", '    if not flags.get("H3", True) or not flags.get("H4", True):\n        return FORM_Dp',
     '    if False:\n        return FORM_Dp',
     ["G0-2"], None,
     "⚖⚖⚖⚖⚖ **级联里的 D′ 那一支被改成不可达** ⇒ ⇒ G0-2 必须红 ⇒ ⇒ **D′ 不是死代码**"),

    # ---------------- 实现被改：量纲护栏（self ⇒ G0-3 必须红）----------------
    ("MU5", "impl", "self", "    if {kind_a, kind_b} == {KIND_DELTA_CI_LO, KIND_C_UPPER}:",
     "    if False:",
     ["G0-3"], None,
     "⚖⚖⚖⚖⚖ **加法② 的「拒绝 delta_ci_lo + c_upper」那条分支被删掉** ⇒ ⇒ G0-3 必须红 "
     "⇒ ⇒ **「把差值区间下端点与污染上界相加」这条假警报就没人拦了**"),
    ("MU6", "impl", "self", "    if {kind_a, kind_b} == {KIND_DELTA_CI_LO, KIND_DELTA_OBS}:",
     "    if False:",
     ["G0-3"], None,
     "⚖⚖⚖⚖⚖ **加法② 的「拒绝 delta_ci_lo + delta_obs」那条分支被删掉** ⇒ ⇒ G0-3 必须红 "
     "⇒ ⇒ 护栏**不是只挡一种错法**"),
    ("MU7", "impl", "self", "    if {kind_a, kind_b} == {KIND_C_UPPER, KIND_C_LOWER}:",
     "    if False:",
     ["G0-3"], None,
     "⚖⚖⚖⚖⚖ **加法② 的「拒绝 c_upper + c_lower」那条分支被删掉** ⇒ ⇒ G0-3 必须红"),
    ("MU8", "impl", "self", "    if (kind_a, kind_b) not in ALLOWED_SUMS:",
     "    if False:",
     ["G0-3"], None,
     "⚖⚖⚖⚖⚖ **加法② 的「只允许登记的加法对」被删掉** ⇒ ⇒ 任何 kind 都能相加 ⇒ ⇒ G0-3 必须红"),

    # ---------------- 实现被改：容差 / 只读（self ⇒ G0-4 / G0-7 必须红）----------------
    ("MU9", "impl", "self", "    return 0.5 * (10.0 ** (-dec))",
     "    return 0.005",
     ["G0-4"], None,
     "⚖⚖⚖⚖⚖ **容差被写死成 0.005**（⛔ 不再由打印精度推导）⇒ ⇒ G0-4 必须红 "
     "⇒ ⇒ 证明「容差由账本打印精度推导」这条承诺**能红**"),
    ("MU10", "impl", "self", "    return _md5_file(path) == before_md5",
     "    return True",
     ["G0-7", "G0-9"], None,
     "⚖⚖⚖⚖⚖ **「这个文件没被改过」的判断被改成恒真**（H9 与 G0-7 **共用**它）"
     "⇒ ⇒ H9 恒绿 ⇒ G0-9 必须红 ｜ G0-7 的**负控**（碰一下必须被检出）失效 ⇒ G0-7 必须红 "
     "⇒ ⇒ 证明「只读」这条闸门**钉得住实现**"),

    # ---------------- 实现被改：c 的两端（self ⇒ G0-6 / G0-9 必须红）----------------
    ("MU11", "impl", "self", "    return (lo - base * 100.0, hi - base * 100.0)",
     "    return (hi - base * 100.0, lo - base * 100.0)",
     ["G0-6"], None,
     "⚖⚖⚖⚖⚖ **c 的区间上下端被写反** ⇒ ⇒ `c_lo` 拿到的是上界 ⇒ ⇒ G0-6 的负控失效 "
     "⇒ ⇒ G0-6 必须红 ⇒ ⇒ 证明「护栏真的在看 `c_lo` 那一端」"),
    ("MU12", "impl", "self", '        viol = [it for it in t["items"] if not it["ok"]]',
     '        viol = []',
     ["G0-9"], None,
     "⚖⚖⚖⚖⚖ **H5/H6/H7 的「违例清单」被改成恒空** ⇒ ⇒ 三条判据恒绿 ⇒ ⇒ G0-9 必须红 "
     "⇒ ⇒ 证明「这三条能红」**不是空话**"),
    ("MU13", "impl", "self",
     'res.append(_chk("H3", "读法 R1（污染只抬高·轨迹级·单源 95%）", r1["bound"] > 0,',
     'res.append(_chk("H3", "读法 R1（污染只抬高·轨迹级·单源 95%）", r1["bound"] > -1e9,',
     ["G0-9"], None,
     "⚖⚖⚖⚖⚖ **H3 被改成恒绿** ⇒ ⇒ G0-9 必须红 ⇒ ⇒ 证明 H3 **能红**"),
    ("MU14", "impl", "self",
     'res.append(_chk("H4", "读法 R2（污染只抬高·块级·单源 95%）", r2["bound"] > 0,',
     'res.append(_chk("H4", "读法 R2（污染只抬高·块级·单源 95%）", r2["bound"] > -1e9,',
     ["G0-9"], None,
     "⚖⚖⚖⚖⚖ **H4 被改成恒绿** ⇒ ⇒ G0-9 必须红 ⇒ ⇒ 证明 H4 **能红**"),
    ("MU15", "impl", "self",
     '    d_ok = abs(delta_calc - I["i7_delta_obs"]) <= tol_d',
     '    d_ok = True',
     ["G0-9"], None,
     "⚖⚖⚥ **H1 的「轨迹级改判数复算」那一半被改成恒真** ⇒ ⇒ G0-9 必须红 "
     "⇒ ⇒ 证明「改判数复算」这一半**有牙齿**"),
    ("MU16", "impl", "self",
     '    b_ok = abs(delta_blk_calc - I["i8_delta_obs_blk"]) <= tol_b',
     '    b_ok = True',
     ["G0-9"], None,
     "⚖⚖⚥ **H1 的「块级改判数复算」那一半被改成恒真** ⇒ ⇒ G0-9 必须红 "
     "⇒ ⇒ 证明「块级那一半」**有牙齿**"),
    ("MU17", "impl", "self",
     '        ok = d_ok and b_ok and (abs(calc_main - float(printed_lo)) <= tol)',
     '        ok = d_ok and b_ok',
     ["G0-9"], None,
     "⚖⚖⚥ **H1 的「现算 vs 244.86 段印的参照」那一半被删掉** ⇒ ⇒ G0-9 必须红"),
    ("MU18", "impl", "self", "        tol = _tol_from_printed(printed_lo)",
     "        tol = 1e9",
     ["G0-9"], None,
     "⚖⚖⚥ **H1 的容差被放到 1e9** ⇒ ⇒ H1 恒绿 ⇒ ⇒ G0-9 必须红"),
    ("MU19", "impl", "self",
     '    ok2 = (got == want) and len(rows) == 9 and n_cells == 18',
     '    ok2 = True',
     ["G0-9"], None,
     "⚖⚖⚖⚖⚖ **H2（扫描完备性）被改成恒真** ⇒ ⇒ H2 恒绿 ⇒ ⇒ G0-9 必须红"),
    ("MU20", "impl", "self",
     '    out_of_range = sorted(k for k, v in I["_lines"].items() if not (sec_lo <= v <= sec_hi))',
     '    out_of_range = []',
     ["G0-9"], None,
     "⚖⚖⚖⚖⚖ **H9 的「行号必须落在段内」被改成恒真** ⇒ ⇒ G0-9 必须红"),

    # ---------------- 实现被改：作用域表的公式（self ⇒ G0-5 / G0-9 必须红）----------------
    ("MU21", "impl", "self",
     '        b = _sum_bound(ct, qty(r["c_lo"], KIND_C_LOWER, "c_lo"))',
     '        b = _sum_bound(dt, qty(r["c_lo"], KIND_C_LOWER, "c_lo"))',
     ["G0-5"], None,
     "⚖⚖⚖⚖⚖ **R5（保守读法）把 CI 下端点换成了 Δ_obs 点估计** ⇒ ⇒ R5 与 R3 同形 "
     "⇒ ⇒ G0-5 的手算核对必须红 ⇒ ⇒ 证明「R5 用的是**保守**那一读」这条承诺**能红**"),
    ("MU22", "impl", "self",
     '        b = _sum_bound(db, qty(r["c_lo"], KIND_C_LOWER, "c_lo"))',
     '        b = _sum_bound(dt, qty(r["c_lo"], KIND_C_LOWER, "c_lo"))',
     ["G0-5"], None,
     "⚖⚖⚖⚖⚖ **R4（块级）把块级 Δ_obs 换成了轨迹级 Δ_obs** ⇒ ⇒ **跨口径串** ⇒ ⇒ G0-5 必须红"),
    ("MU23", "impl", "self",
     '        b = _sum_bound(ct, qty(r["c_lo"], KIND_C_LOWER, "c_lo"))',
     '        b = _sum_bound(ct, qty(abs(r["c_lo"]), KIND_C_LOWER, "c_lo"))',
     ["G0-9"], None,
     "⚖⚖⚖⚖⚖ **R5 把 `c_lo` 取了绝对值**（⇒ ⇒ 最不利的那一端被翻成最有利）⇒ ⇒ G0-9 必须红"),
    ("MU24", "impl", "self", "    return 1.0 - ALPHA_CI - (1.0 - level)",
     "    return (1.0 - ALPHA_CI) * level",
     ["G0-5"], None,
     "⚖⚖⚥ **Bonferroni 的联合置信被写成乘法**（1−α）·level ⇒ ⇒ G0-5 必须红 "
     "⇒ ⇒ 证明「联合置信是减法」这条承诺**能红**"),
    ("MU25", "impl", "self", "ALPHA_CI = 0.05", "ALPHA_CI = 0.5",
     ["G0-5"], None,
     "⚖⚖⚥ **差区间的 alpha 被改成 0.5** ⇒ ⇒ 联合置信全错 ⇒ ⇒ G0-5 必须红"),

    # ---------------- 实现被改：真数据下判据红 / 形态错（data）----------------
    ("MU26", "impl", "data",
     '    out["i7_nc_lo"] = float(m.group(2))',
     '    out["i7_nc_lo"] = float(m.group(3))',
     ["H9"], "E'",
     "⚖⚖⚖⚖⚖ **轨迹级 CI 的**下端点被解析成**上端点** ⇒ ⇒ H9 的「整段区间重建」命不中 "
     "⇒ ⇒ H9 必须红 ⇒ ⇒ 判决形态必须是 **E′**"),
    ("MU27", "impl", "data",
     '    out["i8_delta_obs_blk"] = float(m.group(5))',
     '    out["i8_delta_obs_blk"] = float(m.group(5)) + 1.0',
     ["H1"], "E'",
     "⚖⚖⚖⚖⚖ **块级 Δ_obs 被加了 1.0 pp** ⇒ ⇒ H1 的「块级改判数复算」那一半红 "
     "⇒ ⇒ 判决形态必须是 **E′**"),
    ("MU28", "impl", "data", "MAIN_LEVEL = 0.95                        # 主口径：Wilson95",
     "MAIN_LEVEL = 0.90",
     ["H1"], "E'",
     "⚖⚖⚖⚖⚖ **主口径从 Wilson95 改成 Wilson90** ⇒ ⇒ c_lo 变了 ⇒ ⇒ H1 必须红 ⇒ ⇒ 形态必须是 **E′**"),
    ("MU29", "impl", "data", "        b_zero = 0.25", "        b_zero = 0.5",
     ["H1"], "E'",
     "⚖⚖⚖⚖⚖ **主口径基准的「零格轨迹 base」从 0.25 改成 0.5** ⇒ ⇒ 基准变 ⇒ ⇒ H1 必须红 "
     "⇒ ⇒ 形态必须是 **E′**"),
    ("MU30", "impl", "data",
     "    return (max(0.0, c - h) * 100.0, min(1.0, c + h) * 100.0)",
     "    return (min(1.0, c + h) * 100.0, max(0.0, c - h) * 100.0)",
     ["H1"], "E'",
     "⚖⚖⚖⚖⚖ **Wilson 的上下界被写反** ⇒ ⇒ `c_lo` 取成了上界 ⇒ ⇒ H1 必须红 ⇒ ⇒ 形态必须是 **E′**"),
    ("MU31", "impl", "data",
     'BASE_VARIANTS = ("main", "zero_as_half", "zero_as_zero")',
     'BASE_VARIANTS = ("main", "zero_as_half")',
     ["H2"], "E'",
     "⚖⚖⚖⚖⚖ **基准变体从 3 个减成 2 个** ⇒ ⇒ 扫描不再 3×3=9 ⇒ ⇒ H2 必须红 ⇒ ⇒ 形态必须是 **E′**"),
    ("MU32", "impl", "data",
     '        viol = [it for it in t["items"] if not it["ok"]]',
     '        viol = [it for it in t["items"] if it["ok"]]',
     ["H5", "H6", "H7"], "C'",
     "⚖⚖⚖⚖⚖ **H5/H6/H7 的「违例清单」被写反** ⇒ ⇒ 正常的口径全成违例 ⇒ ⇒ 三条必须红 "
     "⇒ ⇒ 判决形态必须是 **C′**（点估计口径被否）"),

    # ---------------- 账本被改（data）----------------
    ("MU33", "impl", "self",
     "    g_ok, g_msg, _code = _guard_selftest()",
     "    g_ok, g_msg, _code = (True, \"假装护栏在位\", None)",
     ["G0-9"], None,
     "⚖⚖⚖⚖⚖ **H8 被改成恒绿**（不再看护栏的自证结果）⇒ ⇒ G0-9 的「护栏失守 ⇒ H8 必须红」"
     "这一步就抓不到 ⇒ ⇒ G0-9 必须红 ⇒ ⇒ 证明 H8 **有牙齿**"),
    ("ML1", "ledger", "data",
     "| 真实差（Q8 ①） | **不假定方向** | **[+20.26, +45.58] pp**",
     "| 真实差（Q8 ①） | **不假定方向** | **[+21.26, +45.58] pp**",
     ["H1"], "E'",
     "⚖⚖⚖⚖⚖ **账本里 244.86 段印的「真实差（不假定方向）」下端点被从 +20.26 改成 +21.26** "
     "⇒ ⇒ 现算值对不上 ⇒ ⇒ H1 必须红 ⇒ ⇒ 判决形态必须是 **E′**"),
    ("ML2", "ledger", "data",
     "| 改判（主口径：逐轨迹**严格多数**，`nT·2 > m`） | **46/56** | **29/56** |",
     "",
     [], None,
     "⚖⚖⚖⚖⚖ **账本里 244.81 段的改判行被整行删掉** ⇒ ⇒ 输入读不到 ⇒ ⇒ 必须 **硬失败**"
     "（⛔ 不是判红、⛔ 不是「跳过」、⛔ 不是静默降级）⇒ ⇒ 这条纪律单独有变异体守着"),
]

# ⚖ 期望的判决形态（None = 不要求）
EXPECT_VERDICT = {}
for _mid, _cat, _mode, _p, _r, _exp, _v, _n in MUTATIONS:
    if _v:
        EXPECT_VERDICT[_mid] = _v
# ⚖ ML2 期望的是「硬失败」，不是「某个判据变红」
EXPECT_HARDFAIL = {"ML2"}


def _run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, p.stdout or "", p.stderr or ""


def _parse_ids(out):
    ids = {}
    for m in CRIT_RE.finditer(out or ""):
        ids[m.group(2)] = (m.group(1) == "PASS")
    return ids


def _parse_gates(out):
    ids = {}
    for m in GATE_RE.finditer(out or ""):
        ids[m.group(2)] = (m.group(1) == "PASS")
    return ids


def _tmpdir():
    for cand in ("/dev/shm", None):
        try:
            return tempfile.mkdtemp(prefix="mut88_", dir=cand)
        except Exception:
            continue
    print("PRECOND_FAIL: 建不了临时目录")
    raise SystemExit(2)


def main():
    self_only = "--self-only" in sys.argv
    if not os.path.isfile(LEDGER):
        print("PRECOND_FAIL: 账本不存在：%s" % LEDGER)
        return 2
    if not os.path.isfile(os.path.join(HERE, TARGET)):
        print("PRECOND_FAIL: 找不到被检实现 %s" % TARGET)
        return 2

    # ---- 阳性对照（self）----
    rc, out, err = _run([PY, os.path.join(HERE, TARGET), "--selftest"])
    if rc != 0:
        print("⛔ 阳性对照（--selftest）没过 ⇒ 「全红」什么也证明不了 ⇒ 中止")
        print((out or "")[-2000:])
        print((err or "")[-2000:])
        return 4
    print("[阳性对照] --selftest 全绿 ✅（rc=0）")

    # ---- 阳性对照（data）----
    if self_only:
        print("[阳性对照] --data **跳过**（--self-only）")
    else:
        rc, out, err = _run([PY, os.path.join(HERE, TARGET), "--data", "--ledger", LEDGER])
        mv = VERDICT_RE.search(out or "")
        if not mv:
            print("⛔ 阳性对照（--data）没跑出判决形态 ⇒ 中止")
            print((out or "")[-3000:])
            print((err or "")[-3000:])
            return 4
        print("[阳性对照] --data 跑出判决形态 %s ✅（rc=%d）" % (mv.group(1), rc))

    caught, missed, invalid, crashed = [], [], [], []
    for mid, cat, mode, pat, rep, expect, want_v, note in MUTATIONS:
        if self_only and mode != "self":
            continue
        tmp = _tmpdir()
        try:
            tgt = os.path.join(tmp, TARGET)
            shutil.copy2(os.path.join(HERE, TARGET), tgt)
            led = LEDGER
            if cat == "impl":
                txt = open(tgt, encoding="utf-8").read()
                n = txt.count(pat)
                if n != 1:
                    print("[无效] %s 落点命中 %d 处（⛔ 必须是 1 处）⇒ 记「无效」⇒ 不计入分母"
                          % (mid, n))
                    invalid.append(mid)
                    continue
                if pat == rep:
                    print("[无效] %s 替换串等于锚点 ⇒ 文件逐字节不变 ⇒ 必须记成「无效」"
                          "（⛔ 不是「存活」）" % mid)
                    invalid.append(mid)
                    continue
                txt = txt.replace(pat, rep, 1)
                open(tgt, "w", encoding="utf-8").write(txt)
            if cat == "ledger":
                led = os.path.join(tmp, "ledger_copy.md")
                txt = open(LEDGER, encoding="utf-8").read()
                n = txt.count(pat)
                if n != 1:
                    print("[无效] %s 落点命中 %d 处（⛔ 必须是 1 处）⇒ 记「无效」⇒ 不计入分母"
                          % (mid, n))
                    invalid.append(mid)
                    continue
                txt = txt.replace(pat, rep, 1)
                open(led, "w", encoding="utf-8").write(txt)

            cmd = [PY, tgt]
            if mode == "self":
                cmd.append("--selftest")
            else:
                cmd += ["--data", "--ledger", led]
            rc, out, err = _run(cmd)
            if CRASH_RE.search(err or "") or "Traceback" in (out or ""):
                print("[崩] %s  ⇒ 崩的条数必须压到 0" % mid)
                print((err or out)[-1200:])
                crashed.append(mid)
                continue
            if mid in EXPECT_HARDFAIL:
                got_hf = (bool(HARDFAIL_RE.search(out or ""))
                          or bool(HARDFAIL_RE.search(err or "")))
                if got_hf:
                    print("[抓到] %s  硬失败（期望：读不到 ⇒ 必须 HardFail）" % mid)
                    caught.append(mid)
                else:
                    print("[没抓到] %s 期望硬失败（HardFail）｜ 实得：%s"
                          % (mid, (out or "")[-600:]))
                    print("    %s" % note)
                    missed.append(mid)
                continue
            ids = _parse_gates(out) if mode == "self" else _parse_ids(out)
            red = sorted([k for k, v in ids.items() if not v])
            hit = [e for e in expect if e in red]
            want_v = EXPECT_VERDICT.get(mid)
            got_v = None
            mv = VERDICT_RE.search(out or "")
            if mv:
                got_v = mv.group(1)
            v_ok = (want_v is None) or (got_v == want_v)
            if hit and v_ok:
                print("[抓到] %s  %s ⇒ 红：%s%s"
                      % (mid, ",".join(hit), red,
                         ("" if want_v is None else " ｜ 判决形态 %s（期望 %s）" % (got_v, want_v))))
                caught.append(mid)
            else:
                print("[没抓到] %s 期望红 %s ｜ 实得红 %s%s"
                      % (mid, expect, red,
                         ("" if want_v is None else " ｜ 判决形态 %s（期望 %s）" % (got_v, want_v))))
                print("    %s" % note)
                missed.append(mid)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    total = len(caught) + len(missed) + len(crashed)
    print("")
    print("变异台：抓到 %d / %d（无效 %d 条 ⇒ 记「无效」⇒ 不计入分母）"
          % (len(caught), total, len(invalid)))
    print("崩的条数：%d%s" % (len(crashed), ("：%s" % crashed) if crashed else ""))
    if missed:
        print("没抓到的：%s" % missed)
    if invalid:
        print("无效的：%s" % invalid)
    if missed or crashed or invalid:
        print("MUT_RC=1")
        return 1
    print("MUT_RC=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
