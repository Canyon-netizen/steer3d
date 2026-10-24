#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""mut_cmax_robustness_audit.py —— **c_max 口径稳健性**的变异台（244.87）。

⚖⚖⚖⚖⚖ **这个台架要回答的问题**
   「`cmax_robustness_audit.py` 的每条判据**是不是恒绿的**？」
   ⇒ ⇒ 必须证明它们**能红**：
     · **实现被改**（形态级联 / 判据的比较方向 / 公式 / 容差 / 锚点唯一性 / …）
       ⇒ ⇒ 对应判据（或对应 Phase-0 闸门）必须由 PASS 变 FAIL；
     · **账本被改**（把某个输入删掉 / 改掉）⇒ ⇒ 必须判红或**硬失败**
       （⛔ 不是判红、⛔ 不是「跳过」⇒ ⇒ 这条纪律单独有变异体守着）。

⚖⚖⚖⚖⚖ **纪律（从 244.66–244.86 的台架继承，一条都不许放松）**
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

⚖⚖⚖⚖⚖ **244.87 特有的一条纪律**
   变异台**同时断言判决形态**（`EXPECT_VERDICT`）
   ⇒ ⇒ 「改级联 ⇒ 形态错」这条承诺才不是空话
   ⇒ ⇒ 四个形态（A / B / C / D）的**可达性**由 Phase-0 的 G0-1 守。

⚖⚖⚖ **为什么有些变异走 "self"（--selftest）而不是 "data"（--data）**
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
TARGET = "cmax_robustness_audit.py"
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
    # ---------------- 实现被改：形态的落态级联（self）----------------
    ("MU1", "impl", "self", "        form = FORM_B", "        form = FORM_A",
     ["G0-1"], None,
     "⚖⚖⚖⚖⚖ **落态级联里的 B 被改成 A** ⇒ ⇒ 「扫描出现违例 ⇒ B」这条承诺被破坏 "
     "⇒ ⇒ G0-1 必须红 ⇒ ⇒ **B 这一支不是死代码**"),
    ("MU2", "impl", "self", "        form = FORM_D", "        form = FORM_A",
     ["G0-1"], None,
     "⚖⚖⚖⚖⚖ **落态级联里的 D 被改成 A** ⇒ ⇒ G0-1 必须红 ⇒ ⇒ **D 这一支不是死代码**"),
    ("MU3", "impl", "self", "        form = FORM_C", "        form = FORM_A",
     ["G0-1"], None,
     "⚖⚖⚖⚖⚖ **落态级联里的 C 被改成 A** ⇒ ⇒ G0-1 必须红 ⇒ ⇒ **C 这一支不是死代码**"),
    ("MU4", "impl", "self",
     'HARD_FAIL_IDS = ("H1", "H2", "H6", "H7", "H8")',
     'HARD_FAIL_IDS = ("H1", "H2", "H6", "H7")',
     ["G0-1"], None,
     "⚖⚖⚖⚖⚖ **硬失败集合里被拿掉 H8** ⇒ ⇒ 「H8 红」不再落 C ⇒ ⇒ G0-1 的 E 夹具必须红 "
     "⇒ ⇒ 证明「H8 红 ⇒ 形态 C」这条归属**被钉住**了（⛔ 这条夹具就是为它加的）"),

    # ---------------- 实现被改：判据被改成**恒绿**（self ⇒ Phase-0 必须抓）----------------
    ("MU5", "impl", "self", "ref is not None and abs(c_main - ref) <= 5e-3,",
     "ref is not None and abs(c_main - ref) <= 5e9,",
     ["G0-2"], None,
     "⚖⚖⚖⚖⚖ **H1 的容差被放到 5e9** ⇒ ⇒ H1 恒绿 ⇒ ⇒ G0-2 必须红 ⇒ ⇒ 证明 H1 **能红**"),
    ("MU6", "impl", "self", "got_seq == expect_seq,", "True,",
     ["G0-2"], None,
     "⚖⚖⚖⚖⚖ **H2 的「顺序固定」检查被改成恒真** ⇒ ⇒ H2 恒绿 ⇒ ⇒ G0-2 必须红"),
    ("MU7", "impl", "self", 'return bool(cmax < dq["value"])',
     'return bool(cmax > dq["value"])',
     ["G0-1", "G0-2"], None,
     "⚖⚖⚖⚖⚖ **主判据的比较方向被写反**（< ⇒ >）⇒ ⇒ H3 恒红 ⇒ ⇒ A 夹具的形态不再是 A "
     "⇒ ⇒ G0-1 必须红（且 G0-2 的 H3 夹具也必须红）"),
    ("MU8", "impl", "self",
     "if kind_a == KIND_DELTA_CI_LO or kind_b == KIND_DELTA_CI_LO:",
     "if False:",
     ["G0-1", "G0-4"], None,
     "⚖⚖⚖⚖⚖ **量纲护栏的第一条（拒 delta_ci_lo）被删掉** ⇒ ⇒ H5 的自证必须红 ⇒ ⇒ G0-4 必须红 "
     "⇒ ⇒ **「把 Newcombe 下端点误当 Δ_obs」这条假警报就没人拦了**"),
    ("MU9", "impl", "self", 'miss = [k for k, s in rebuilds if s not in I["_sec"]]',
     "miss = []",
     ["G0-2"], None,
     "⚖⚖⚖⚖⚖ **H6 的「重建串必须命中期内」被改成恒绿** ⇒ ⇒ H6 恒绿 ⇒ ⇒ G0-2 必须红 "
     "⇒ ⇒ 证明「改账本任一个数 ⇒ 红」这条承诺**不是空话**"),
    ("MU10", "impl", "self",
     '_md5_unchanged(ledger_path, I["_raw_md5"]) and not out_of_range,',
     "True,",
     ["G0-2"], None,
     "⚖⚖⚖⚖⚖ **H7 的「md5 不变 + 行号在段内」被改成恒真** ⇒ ⇒ H7 恒绿 ⇒ ⇒ G0-2 必须红"),
    ("MU11", "impl", "self", "abs(calc_delta - delta_obs_printed) <= 0.005",
     "abs(calc_delta - delta_obs_printed) <= 1e9",
     ["G0-2"], None,
     "⚖⚖⚖ **H8 的 Δ_obs 交叉校验容差被放到 1e9** ⇒ ⇒ H8 恒绿 ⇒ ⇒ G0-2 必须红"),
    ("MU12", "impl", "self",
     'BASE_VARIANTS = ("main", "zero_as_half", "zero_as_zero")',
     'BASE_VARIANTS = ("main", "zero_as_half")',
     ["G0-3"], None,
     "⚖⚖⚖⚖⚖ **基准变体从 3 个减成 2 个** ⇒ ⇒ 扫描不再 3×3=9 ⇒ ⇒ G0-3 必须红 "
     "⇒ ⇒ 证明「扫描完备性」这条闸门**钉得住实现**"),
    ("MU13", "impl", "self", "return (lo - base * 100.0, hi - base * 100.0)",
     "return (lo - base * 10.0, hi - base * 10.0)",
     ["G0-2", "G0-5"], None,
     "⚖⚖⚖⚖⚖ **c 的区间换算把 ×100 写成 ×10** ⇒ ⇒ c_max 的量纲错 ⇒ ⇒ G0-5（独立复算）必须红"),
    ("MU14", "impl", "self",
     'if len(hits) != 1:\n        _die("段内「%s」按模式命中',
     'if len(hits) < 1:\n        _die("段内「%s」按模式命中',
     ["G0-6"], None,
     "⚖⚖⚖⚖⚖ **锚点「命中数 ≠ 1 ⇒ 硬失败」被放宽成「命中 0 才硬失败」** ⇒ ⇒ 锚点不唯一时"
     "**静默取第一个** ⇒ ⇒ G0-6 必须红 ⇒ ⇒ 证明「锚点不唯一必须硬失败」这条纪律**能红**"),
    ("MU15", "impl", "self", "    return _md5_file(path) == before_md5", "    return True",
     ["G0-2", "G0-7"], None,
     "⚖⚖⚖⚖⚖ **「文件没被改过」这个判断被改成恒真**（H7 与 G0-7 **共用**它）"
     "⇒ ⇒ H7 恒绿 ⇒ G0-2 必须红 ｜ G0-7 的**负控**（碰一下必须被检出）失效 ⇒ G0-7 必须红 "
     "⇒ ⇒ 证明「只读」这条闸门**钉得住实现**"),
    ("MU16", "impl", "self",
     "if (kind_a, kind_b) not in ALLOWED_KIND_PAIRS:",
     "if False:",
     ["G0-4"], None,
     "⚖⚖⚖⚖⚖ **量纲护栏的第二条（只允许 c_upper ↔ delta_obs）被删掉** ⇒ ⇒ 未知 kind 的比较"
     "不再被拒 ⇒ ⇒ G0-4 必须红 ⇒ ⇒ 证明护栏**不是只挡一种错法**"),
    ("MU17", "impl", "self",
     "abs(calc_delta_blk - I[\"i8_delta_obs_blk\"]) <= 0.005",
     "True",
     ["G0-2"], None,
     "⚖⚖⚖ **H8 的「块级 Δ_obs 交叉校验」被删掉** ⇒ ⇒ H8 少了一条腿 ⇒ ⇒ G0-2 的块级夹具必须红"),

    # ---------------- 实现被改：真数据下判据红 / 形态错（data）----------------
    ("MU18", "impl", "data", "MAIN_LEVEL = 0.95                     # 主口径：Wilson95",
     "MAIN_LEVEL = 0.90",
     ["H1"], "C",
     "⚖⚖⚖⚖⚖ **主口径从 Wilson95 改成 Wilson90** ⇒ ⇒ c_max 变成 +13.32 pp ≠ 账本印的 +15.22 pp "
     "⇒ ⇒ H1 必须红 ⇒ ⇒ 判决形态必须是 **C**（硬失败：复算门槛没过）"),
    ("MU19", "impl", "data", "        b_zero = 0.25", "        b_zero = 0.5",
     ["H1"], "C",
     "⚖⚖⚖⚖⚖ **主口径基准的「零格轨迹 base」从 0.25 改成 0.5** ⇒ ⇒ 基准变 ⇒ ⇒ H1 必须红 "
     "⇒ ⇒ 判决形态必须是 **C**"),
    ("MU20", "impl", "data",
     "return (max(0.0, c - h) * 100.0, min(1.0, c + h) * 100.0)",
     "return (min(1.0, c + h) * 100.0, max(0.0, c - h) * 100.0)",
     ["H1"], "C",
     "⚖⚖⚖⚖⚖ **Wilson 的上下界被写反** ⇒ ⇒ c_max 取成了下界 ⇒ ⇒ H1 必须红 ⇒ ⇒ 形态必须是 **C**"),
    ("MU21", "impl", "data", 'return bool(cmax < dq["value"])',
     'return bool(cmax > dq["value"])',
     ["H3", "H4"], "B",
     "⚖⚖⚖⚖⚖ **主判据的比较方向被写反** ⇒ ⇒ 每个口径都成「违例」⇒ ⇒ H3/H4 必须红 "
     "⇒ ⇒ 判决形态必须是 **B**"),
    ("MU22", "impl", "self",
     '        def _wrong_kind(I, path):\n            I["delta_qty"] = qty(I["i7_newcombe_lo"], KIND_DELTA_CI_LO, "newcombe_lo")',
     '        def _wrong_kind(I, path):\n            pass',
     ["G0-1"], None,
     "⚖⚖⚖⚖⚖ **Phase-0 的 D 夹具被掏空**（不再把 Newcombe 下端点接到 Δ_obs 槽位）"
     "⇒ ⇒ D 夹具不再是 D ⇒ ⇒ G0-1 必须红 ⇒ ⇒ 证明「形态 D **可达**」这条承诺**不是空话**"
     "（⛔ 否则「D 那一支是死代码」没人知道）"),
    ("MU23", "impl", "data", 'miss = [k for k, s in rebuilds if s not in I["_sec"]]',
     'miss = [k for k, s in rebuilds if s in I["_sec"]]',
     ["H6"], "C",
     "⚖⚖⚖⚖⚖ **H6 的「缺失」判定被写反** ⇒ ⇒ 正常时全部算缺失 ⇒ ⇒ H6 必须红 ⇒ ⇒ 形态必须是 **C**"),
    ("MU24", "impl", "data",
     '_md5_unchanged(ledger_path, I["_raw_md5"])',
     '_md5_unchanged(__file__, I["_raw_md5"])',
     ["H7"], "C",
     "⚖⚖⚖⚖⚖ **H7 的「运行后账本 md5」取错了文件**（取成实现自己 —— ⛔ 真实的「取错对象」bug）"
     "⇒ ⇒ 前后 md5 不等 ⇒ ⇒ H7 必须红 ⇒ ⇒ 判决形态必须是 **C**"),
    ("MU25", "impl", "data",
     'calc_delta = (I["i1_w_num"] / I["i1_w_den"] - I["i2_r_num"] / I["i2_r_den"]) * 100.0',
     'calc_delta = (I["i1_w_num"] / I["i1_w_den"] + I["i2_r_num"] / I["i2_r_den"]) * 100.0',
     ["H8"], "C",
     "⚖⚖⚖⚖⚖ **H8 的「观测差」交叉校验公式被改**（减 ⇒ 加）⇒ ⇒ 算出的差与账本印的 +30.36 pp "
     "对不上 ⇒ ⇒ H8 必须红 ⇒ ⇒ 判决形态必须是 **C**"),
    ("MU26", "impl", "data", "(cmp_cmax(c_main) is True),", "(cmp_cmax(c_main) is False),",
     ["H4"], "B",
     "⚖⚖⚖ **H4（最紧组合）的判定被写反** ⇒ ⇒ H4 恒红 ⇒ ⇒ 判决形态必须是 **B**"),

    # ---------------- 账本被改（data）----------------
    ("ML1", "ledger", "data", "**46/56** | **29/56**", "**45/56** | **29/56**",
     ["H6", "H8"], "C",
     "⚖⚖⚖⚖⚖ **账本里 w 臂的改判数被从 46/56 改成 45/56** ⇒ ⇒ Δ_obs 算出来对不上印的 "
     "⇒ ⇒ H8 必须红、且 H6 的重建串命不中 ⇒ ⇒ 判决形态必须是 **C**"),
    ("ML2", "ledger", "data",
     "| 比例区间（Wilson95） | [+70.16, +90.00] | [+39.01, +64.33] |", "",
     [], None,
     "⚖⚖⚖⚖⚖ **账本里 Wilson95 区间那整行被删掉** ⇒ ⇒ 输入读不到 ⇒ ⇒ 必须 **硬失败**"
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
            return tempfile.mkdtemp(prefix="mut87_", dir=cand)
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
