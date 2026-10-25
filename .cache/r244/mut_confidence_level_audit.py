#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""mut_confidence_level_audit.py —— **保守读法换置信水平**的变异台（244.89）。

⚖⚖⚖⚖⚖ **这个台架要回答的问题**
   「`confidence_level_audit.py` 的每条判据**是不是恒绿的**？」
   ⇒ ⇒ 必须证明它们**能红**：
     · **实现被改**（形态级联 / 判据的比较方向 / 加法公式 / 量纲护栏 / 容差 /
       决策区成员 / Newcombe 公式 / Wilson 公式 / 基准算法 …）
       ⇒ ⇒ 对应判据（或对应 Phase-0 闸门）必须由 PASS 变 FAIL；
     · **账本被改** ⇒ ⇒ 必须判红或**硬失败**
       （⛔ 不是判红、⛔ 不是「跳过」⇒ ⇒ 这条纪律单独有变异体守着）。

⚖⚖⚖⚖⚖ **纪律（从 244.66–244.88 的台架继承，一条都不许放松）**
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

⚖⚖⚖⚖⚖ **244.89 特有的三条纪律**
   · 变异台**同时断言判决形态**（`EXPECT_VERDICT`）
     ⇒ ⇒ 「改级联 ⇒ 形态错」这条承诺才不是空话；
   · **决策区的成员表是「手写」的**（实现里的 `EXPECTED_DECISION_ALLOCATIONS`）
     ⇒ ⇒ MU21 那条「把联合置信改成浮点比较」的变异**必须**被 H2 抓住
     ⇒ ⇒ （二元浮点里 `0.95+0.95-1.0 = 0.8999999999999999 < 0.9`
     ⇒ ⇒ ⇒ 那个 (95,95) 的 **3** 格（3 个基准变体）会被**静默踢出**决策区
     ⇒ ⇒ ⇒ 主表会悄悄从 12 格变成 9 格 ⇒ ⇒ 这是本轮最阴的一条变异）；
   · **量纲护栏的「调用点」也要测**（MU14）⇒ ⇒ 「护栏函数还在、但加法不再调用它」
     这种削弱**没人知道** ⇒ ⇒ 护栏自证必须从**真正的加法路径**喂一次未登记配对。
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.environ.get("R244_LEDGER", "/home/zhourui/steer3d/.cache/xcheck/R6_RERUN_PREREG.md")
TARGET = "confidence_level_audit.py"
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
MUTATIONS = [
    # ---------------- 实现被改：形态的落态级联（self ⇒ G0-2 穷举必须红）----------------
    ("MU1", "impl", "self",
     'HARD_FAIL_IDS = ("H1", "H2", "H7", "H8", "H9")',
     'HARD_FAIL_IDS = ("H1", "H2", "H7", "H8")',
     ["G0-2"], None,
     "⚖⚖⚖⚖⚖ **硬失败集合里被拿掉 H9** ⇒ ⇒ 「H9 红」不再落 E″ ⇒ ⇒ G0-2 的穷举必须红 "
     "⇒ ⇒ 证明「H9 红 ⇒ 形态 E″」这条归属**被钉住**了"),
    ("MU2", "impl", "self",
     '    if not flags.get("H5", True) or not flags.get("H6", True):\n        return FORM_B',
     '    if False:\n        return FORM_B',
     ["G0-2"], None,
     "⚖⚖⚖⚖⚖ **级联里的 B″ 那一支被改成不可达** ⇒ ⇒ G0-2 必须红 ⇒ ⇒ **B″ 不是死代码**"),
    ("MU3", "impl", "self",
     '    if not flags.get("H3", True):\n        return FORM_D',
     '    if False:\n        return FORM_D',
     ["G0-2"], None,
     "⚖⚖⚖⚖⚖ **级联里的 D″ 那一支被改成不可达** ⇒ ⇒ G0-2 必须红 ⇒ ⇒ **D″ 不是死代码**"),
    ("MU4", "impl", "self",
     '    if not flags.get("H4", True):\n        return FORM_C',
     '    if False:\n        return FORM_C',
     ["G0-2"], None,
     "⚖⚖⚖⚖⚖ **级联里的 C″ 那一支被改成不可达** ⇒ ⇒ G0-2 必须红 ⇒ ⇒ **C″ 不是死代码**"),

    # ---------------- 实现被改：量纲护栏（self ⇒ G0-3 必须红）----------------
    ("MU5", "impl", "self",
     "    if pair == {K_DELTA_CI_LO, K_C_UPPER}:",
     "    if False:",
     ["G0-3"], None,
     "⚖⚖⚖⚖⚖ **加法护栏的「拒绝 delta_ci_lo + c_upper」那条分支被删掉** ⇒ ⇒ G0-3 必须红 "
     "⇒ ⇒ **「把差值区间下端点与污染上界相加」这条假警报就没人拦了**"),
    ("MU6", "impl", "self",
     "    if pair == {K_DELTA_CI_LO, K_DELTA_OBS}:",
     "    if False:",
     ["G0-3"], None,
     "⚖⚖⚖⚖⚖ **加法护栏的「拒绝 delta_ci_lo + delta_obs」那条分支被删掉** ⇒ ⇒ G0-3 必须红 "
     "⇒ ⇒ 护栏**不是只挡一种错法**"),
    ("MU7", "impl", "self",
     "    if pair == {K_C_UPPER, K_C_LOWER}:",
     "    if False:",
     ["G0-3"], None,
     "⚖⚖⚖⚖⚖ **加法护栏的「拒绝 c_upper + c_lower」那条分支被删掉** ⇒ ⇒ G0-3 必须红"),
    ("MU8", "impl", "self",
     "    if K_SUM in pair:",
     "    if False:",
     ["G0-3"], None,
     "⚖⚖⚖⚖⚖ **加法护栏的「拒绝把界本身再参与运算」那条分支被删掉** ⇒ ⇒ G0-3 必须红"),
    ("MU9", "impl", "self",
     "    if (kind_a, kind_b) not in ALLOWED_SUMS:",
     "    if False:",
     ["G0-3"], None,
     "⚖⚖⚖⚖⚖ **加法护栏的兜底那条（只允许登记的加法对）被删掉** ⇒ ⇒ G0-3 必须红"),
    ("MU10", "impl", "self",
     "        if kind_a == K_C_UPPER:\n            die(\"H7-KIND-CMP-CILO-CUPPER",
     "        if False:\n            die(\"H7-KIND-CMP-CILO-CUPPER",
     ["G0-3"], None,
     "⚖⚖⚖⚖⚖ **比较护栏里「拿污染上界去比 0」那条专属分支被删掉** ⇒ ⇒ 分支代号对不上 "
     "⇒ ⇒ G0-3 必须红 ⇒ ⇒ 证明「分支可区分」这条承诺**能红**"),
    ("MU14", "impl", "self",
     '    guard_add(a["kind"], b["kind"])',
     '    pass',
     ["G0-3"], None,
     "⚖⚖⚖⚖⚖ **加法路径**不再调用量纲护栏**（护栏函数本身还在）** ⇒ ⇒ 护栏自证必须从"
     "**真正的加法路径**喂一次未登记配对 ⇒ ⇒ G0-3 必须红 ⇒ ⇒ 证明「护栏被削弱」**察觉得到**"),
    ("MU15", "impl", "self",
     '    m = re.search(r"H7-KIND-[A-Z\\-]+", msg or "")',
     '    m = None',
     ["G0-3"], None,
     "⚖⚖⚖⚖⚖ **护栏的分支代号取不到** ⇒ ⇒ 护栏自证必须发现「分支对不上」⇒ ⇒ G0-3 必须红"),

    # ---------------- 实现被改：容差 / 只读 / c 的两端（self ⇒ G0-4 / G0-6 / G0-7）----------------
    ("MU11", "impl", "self",
     "    return 0.5 * (10.0 ** (-dec))",
     "    return 0.005",
     ["G0-4"], None,
     "⚖⚖⚖⚖⚖ **容差被写死成 0.005**（⛔ 不再由打印精度推导）⇒ ⇒ G0-4 必须红 "
     "⇒ ⇒ 证明「容差由账本打印精度推导」这条承诺**能红**"),
    ("MU12", "impl", "self",
     "    return md5_file(path) == before_md5",
     "    return True",
     ["G0-7"], None,
     "⚖⚖⚖⚖⚖ **「这个文件没被改过」的判断被改成恒真**（H8 与 G0-7 **共用**它）"
     "⇒ ⇒ G0-7 的 **md5 负控**失效 ⇒ ⇒ G0-7 必须红 ⇒ ⇒ 证明「只读」这条闸门**钉得住实现**"),
    ("MU13", "impl", "self",
     "    return (lo - base * 100.0, hi - base * 100.0)",
     "    return (hi - base * 100.0, lo - base * 100.0)",
     ["G0-6"], None,
     "⚖⚖⚖⚖⚖ **c 的区间上下端被写反** ⇒ ⇒ `c_lo` 拿到的是上界 ⇒ ⇒ G0-6 的负控②"
     "（「每行必须 c_lo < c_hi」）失效 ⇒ ⇒ G0-6 必须红 ⇒ ⇒ 证明「护栏真的在看 `c_lo` 那一端」"),

    # ---------------- 实现被改：判据被改成恒绿（self ⇒ G0-9 必须红）----------------
    ("MU16", "impl", "self",
     'checks.append(make_check("H5", "保守读法·决策区（联合 ≥ 90%·运算③）", not dec_bad,',
     'checks.append(make_check("H5", "保守读法·决策区（联合 ≥ 90%·运算③）", True,',
     ["G0-9"], None,
     "⚖⚖⚖⚖⚖ **H5（保守读法·决策区）被改成恒绿** ⇒ ⇒ 在真数据上它本来就绿 ⇒ ⇒ "
     "只能靠 Phase-0 的合成夹具逼红 ⇒ ⇒ G0-9 必须红"),
    ("MU17", "impl", "self",
     'checks.append(make_check("H6", "保守读法·全 27 格（运算③）", not all_bad,',
     'checks.append(make_check("H6", "保守读法·全 27 格（运算③）", True,',
     ["G0-9"], None,
     "⚖⚖⚖⚖⚖ **H6（保守读法·全 27 格）被改成恒绿** ⇒ ⇒ G0-9 必须红"),
    ("MU18", "impl", "self",
     "        ok = abs(calc - printed) <= tol",
     "        ok = True",
     ["G0-9"], None,
     "⚖⚖⚖⚖⚖ **H1 的「算出来的 vs 账本印的」比较被改成恒真** ⇒ ⇒ G0-9 必须红"),
    ("MU19", "impl", "self",
     "            if abs(resid) > RESID_TOL or not same_flag:",
     "            if False:",
     ["G0-9"], None,
     "⚖⚖⚖⚖⚖ **H9 的「残差必须被完全归因」被放宽成恒真** ⇒ ⇒ G0-9 必须红"),
    ("MU20", "impl", "self",
     "    h8_ok = md5_ok and (not out_of_range) and (not missing)",
     "    h8_ok = md5_ok",
     ["G0-9"], None,
     "⚖⚖⚖⚖⚖ **H8 的「重建串必须逐字符在段内」被删掉** ⇒ ⇒ G0-9 必须红"),

    # ---------------- 实现被改：网格与决策区（data ⇒ H2 必须红）----------------
    ("MU21", "impl", "data",
     "    return int(round(lv_ci * 100)) + int(round(lv_c * 100)) - 100",
     "    return int((lv_ci + lv_c - 1.0) * 100)",
     ["H2"], "E'",
     "⚖⚖⚖⚖⚖⚖⚖ **联合置信的整数百分点被换成「浮点乘完截断」** ⇒ ⇒ 二元浮点里 "
     "`0.95+0.95-1.0 = 0.8999999999999999` ⇒ ⇒ `int(89.99999999999999)` = **89** "
     "⇒ ⇒ **(95,95) 那 3 格（3 个基准变体）被静默踢出决策区**（主表 12 → 9）"
     "⇒ ⇒ H2 的**手写**决策区成员表必须抓住它"),
    ("MU22", "impl", "data",
     "JOINT_FLOOR = 0.90",
     "JOINT_FLOOR = 0.80",
     ["H2"], "E'",
     "⚖⚖⚖⚖⚖ **决策区的门槛从 90% 放宽到 80%** ⇒ ⇒ 决策区成员表必须对不上 ⇒ ⇒ H2 必须红"),
    ("MU23", "impl", "data",
     "CI_LEVELS = (0.90, 0.95, 0.99)",
     "CI_LEVELS = (0.90, 0.95)",
     ["H2"], "E'",
     "⚖⚖⚖⚖⚖ **CI 水平少了 99% 一档** ⇒ ⇒ 27 格变 18 格 ⇒ ⇒ H2 必须红"),
    ("MU24", "impl", "data",
     "C_LEVELS = (0.90, 0.95, 0.99)",
     "C_LEVELS = (0.90, 0.95)",
     ["H2"], "E'",
     "⚖⚖⚖⚖⚖ **污染水平少了 99% 一档** ⇒ ⇒ H2 必须红"),
    ("MU25", "impl", "data",
     'BASE_VARIANTS = ("main", "zero_as_half", "zero_as_zero")',
     'BASE_VARIANTS = ("main", "zero_as_half")',
     ["H2"], "E'",
     "⚖⚖⚖⚖⚖ **基准变体少了 zero_as_zero** ⇒ ⇒ H2 必须红"),

    # ---------------- 实现被改：口径公式（data ⇒ H1 必须红）----------------
    ("MU26", "impl", "data",
     "    lo = diff - math.sqrt((pw - lw) ** 2 + (ur - pr) ** 2)",
     "    lo = diff + math.sqrt((uw - pw) ** 2 + (pr - lr) ** 2)",
     ["H1"], "E'",
     "⚖⚖⚖⚖⚖ **Newcombe 的 lower 公式被换成 upper 公式** ⇒ ⇒ 现算值对不上账本印的 "
     "+13.01 ⇒ ⇒ H1 必须红 ⇒ ⇒ 形态必须是 **E″**"),
    ("MU27", "impl", "data",
     "    lo = diff - math.sqrt((pw - lw) ** 2 + (ur - pr) ** 2)",
     "    lo = diff - ((pw - lw) + (ur - pr))",
     ["H1"], "E'",
     "⚖⚖⚖⚖⚖ **Newcombe 的 √(a²+b²) 被换成 a+b** ⇒ ⇒ H1 必须红"),
    ("MU28", "impl", "data",
     "    half = (z / den) * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n))",
     "    half = (z / den) * math.sqrt(p * (1.0 - p) / n)",
     ["H1"], "E'",
     "⚖⚖⚖⚖⚖ **Wilson 的 z²/(4n²) 那一项被删掉** ⇒ ⇒ Wilson95 对不上账本印的 "
     "[+39.01, +64.33] ⇒ ⇒ H1 必须红"),
    ("MU29", "impl", "data",
     "p * (1.0 - p) / n + z * z / (4.0 * n * n))",
     "p * (1.0 - p) / (n - 1) + z * z / (4.0 * n * n))",
     ["H1"], "E'",
     "⚖⚖⚖⚖⚖ **Wilson 的 p(1−p)/n 被换成 p(1−p)/(n−1)** ⇒ ⇒ H1 必须红"),
    ("MU30", "impl", "data",
     '    if variant == "main":\n        b_zero = BASE_ZERO_MAIN',
     '    if variant == "main":\n        b_zero = 0.5',
     ["H1"], "E'",
     "⚖⚖⚖⚖⚖ **零格轨迹在 main 变体下的 base 从 0.25 被改成 0.5** ⇒ ⇒ 现算基准对不上账本印的 "
     "0.4911 ⇒ ⇒ H1 必须红"),

    # ---------------- 账本被改（data）----------------
    ("ML1", "ledger", "data",
     "| 0.95 | main | **+2.9132** | 90% |",
     "| 0.95 | main | **+9.9132** | 90% |",
     ["H9"], "E'",
     "⚖⚖⚖⚖⚖ **账本里 244.88 段印的 R5 那一格被从 +2.9132 改成 +9.9132** ⇒ ⇒ 本轮算出的那格"
     "与它对不上 ⇒ ⇒ H9 必须红 ⇒ ⇒ 判决形态必须是 **E″**"),
    ("ML2", "ledger", "data",
     "| 改判（主口径：逐轨迹**严格多数**，`nT·2 > m`） | **46/56** | **29/56** |",
     "",
     [], None,
     "⚖⚖⚖⚖⚖ **账本里 244.81 段的改判行被整行删掉** ⇒ ⇒ 输入读不到 ⇒ ⇒ 必须 **硬失败**"
     "（⛔ 不是判红、⛔ 不是「跳过」、⛔ 不是静默降级）⇒ ⇒ 这条纪律单独有变异体守着"),
    ("ML3", "ledger", "data",
     "差区间（Newcombe95）[+13.01, +45.36]",
     "差区间（Newcombe95）[+23.01, +45.36]",
     ["H1"], "E'",
     "⚖⚖⚖⚖⚖ **账本里 244.81 段印的 Newcombe95 下端点被从 +13.01 改成 +23.01** ⇒ ⇒ "
     "本轮**自己算**的 Newcombe95 对不上 ⇒ ⇒ H1 必须红 ⇒ ⇒ 判决形态必须是 **E″**"),
    ("ML4", "ledger", "data",
     "| 零假设基准（逐轨迹平均） | 0.4955 | 0.4911 |",
     "| 零假设基准（逐轨迹平均） | 0.4955 | 0.4999 |",
     ["H1"], "E'",
     "⚖⚖⚖⚖⚖ **账本里 244.81 段印的 rand 臂基准被从 0.4911 改成 0.4999** ⇒ ⇒ 由分布现算的"
     "基准对不上 ⇒ ⇒ H1 必须红 ⇒ ⇒ 判决形态必须是 **E″**"),
]

# ⚖ 期望的判决形态（None = 不要求）
EXPECT_VERDICT = {}
for _mid, _cat, _mode, _p, _r, _exp, _v, _n in MUTATIONS:
    if _v:
        EXPECT_VERDICT[_mid] = _v
# ⚖ ML2 期望的是「硬失败」，不是「某个判据变红」
EXPECT_HARDFAIL = {"ML2"}


def _run(cmd, env=None):
    p = subprocess.run(cmd, capture_output=True, text=True, env=env)
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
            return tempfile.mkdtemp(prefix="mut89_", dir=cand)
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
        print((out or "")[-3000:])
        print((err or "")[-3000:])
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
                with open(tgt, encoding="utf-8") as fh:
                    txt = fh.read()
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
                with open(tgt, "w", encoding="utf-8") as fh:
                    fh.write(txt)
            else:
                led = os.path.join(tmp, "ledger_copy.md")
                with open(LEDGER, encoding="utf-8") as fh:
                    txt = fh.read()
                n = txt.count(pat)
                if n != 1:
                    print("[无效] %s 落点命中 %d 处（⛔ 必须是 1 处）⇒ 记「无效」⇒ 不计入分母"
                          % (mid, n))
                    invalid.append(mid)
                    continue
                txt = txt.replace(pat, rep, 1)
                with open(led, "w", encoding="utf-8") as fh:
                    fh.write(txt)

            env = dict(os.environ)
            env["R24489_TMPDIR"] = os.path.join(tmp, "selftmp")
            cmd = [PY, tgt]
            if mode == "self":
                cmd.append("--selftest")
            else:
                cmd += ["--data", "--ledger", led]
            rc, out, err = _run(cmd, env=env)
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
                    print("[没抓到] %s 期望硬失败（HardFail）｜ 实得：%s" % (mid, (out or "")[-600:]))
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
