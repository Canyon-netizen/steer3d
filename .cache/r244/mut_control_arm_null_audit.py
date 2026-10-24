#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""mut_control_arm_null_audit.py —— **对照臂零假设地位**的变异台（244.86）。

⚖⚖⚖⚖⚖ **这个台架要回答的问题**
   「`control_arm_null_audit.py` 的每条判据**是不是恒绿的**？」
   ⇒ ⇒ 必须证明它们**能红**：
     · **实现被改**（口径 / 判决映射表 / 判据的比较方向 / 公式 / 容差 / 段尾算法 / …）
       ⇒ ⇒ 对应判据必须由 PASS 变 FAIL；
     · **账本被改**（把某个输入删掉）⇒ ⇒ 必须 **HardFail**
       （⛔ 不是判红、⛔ 不是「跳过」⇒ ⇒ 这条纪律单独有变异体守着）。

⚖⚖⚖⚖⚖ **纪律（从 244.66–244.85 的台架继承，一条都不许放松）**
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

⚖⚖⚖⚖⚖ **244.86 特有的一条纪律**
   变异台**同时断言判决形态**（`EXPECT_VERDICT`）
   ⇒ ⇒ 「改映射表 ⇒ 形态错」这条承诺才不是空话
   ⇒ ⇒ 五个形态（N-A / N-B / N-C / N-D / N-E）的**可达性**由 Phase-0 的 G0-2 守。
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.environ.get("R244_LEDGER", "/home/zhourui/steer3d/.cache/xcheck/R6_RERUN_PREREG.md")
TARGET = "control_arm_null_audit.py"
PY = os.environ.get("R244_PY", "/home/zhourui/miniconda3/envs/easysteer/bin/python")

# ⚖ 判据 id（真数据路径印的是这些）
CRIT_RE = re.compile(r"^\[(PASS|FAIL)\]\s+(\S+)", re.M)
GATE_RE = re.compile(r"^\[(PASS|FAIL)\]\s+(G0-\d)", re.M)
CRASH_RE = re.compile(r"^(Traceback \(most recent call last\)|\w*(?:Error|Exception)\b)", re.M)

# ⚖ (编号, 类别, 模式, 落点串, 替换串, 期望红的判据 id, 期望的判决形态, 说明)
#    模式 "self" = 跑 `--selftest`（⛔ 不依赖账本）；"data" = 跑真数据路径
#    类别 "impl" = 改**实现源码副本**；"ledger" = 改**账本副本**
#    期望形态 None = 不要求（但**打出来**）
MUTATIONS = [
    # ---------------- 实现被改：判决映射表（self）----------------
    ("PM1", "impl", "self", '("else", None, "N-A"),', '("else", None, "N-C"),',
     ["G0-2"], None,
     "⚖⚖⚖⚖⚖ **判决映射表里的 N-A 被改成 N-C** ⇒ ⇒ 「rand 与零假设不可区分 ⇒ N-A」这条承诺被破坏 "
     "⇒ ⇒ G0-2 必须红 ⇒ ⇒ **N-A 这一支不是死代码**"),
    ("PM2", "impl", "self", '("both_sig", True, "N-B"),', '("both_sig", True, "N-A"),',
     ["G0-2"], None,
     "⚖⚖⚖⚖⚖ **判决映射表里的 N-B 被改成 N-A** ⇒ ⇒ G0-2 必须红 ⇒ ⇒ **N-B 这一支不是死代码**"),
    ("PM3", "impl", "self", '("base_ok", False, "N-D"),', '("base_ok", False, "N-A"),',
     ["G0-2"], None,
     "⚖⚖⚖⚖⚖ **判决映射表里的 N-D 被改成 N-A** ⇒ ⇒ G0-2 必须红 ⇒ ⇒ **N-D 这一支不是死代码**"),
    ("PM4", "impl", "self", '("other_hard_ok", False, "N-E"),', '("other_hard_ok", False, "N-A"),',
     ["G0-2"], None,
     "⚖⚖⚖⚖⚖ **判决映射表里的 N-E 被改成 N-A** ⇒ ⇒ G0-2 必须红 ⇒ ⇒ **N-E 这一支不是死代码**"),
    ("PM5", "impl", "self", '"mixed_sig": bool(traj_sig != block_sig),',
     '"mixed_sig": bool(traj_sig == block_sig),',
     ["G0-2"], None,
     "⚖⚖⚖⚖⚖ **「方向不一致」这个条件的比较被写反**（!= ⇒ ==）⇒ ⇒ 「一显著一不显著 ⇒ N-C」被破坏 "
     "⇒ ⇒ G0-2 必须红 ⇒ ⇒ **N-C 这一支不是死代码**"),

    # ---------------- 实现被改：Phase-0 夹具（self）----------------
    ("PM6", "impl", "self", "obs_r=44, obs_w=46, blk_r=22, blk_w=21,",
     "obs_r=29, obs_w=46, blk_r=22, blk_w=21,",
     ["G0-3"], None,
     "⚖⚖⚖ **G0-3 夹具的 rand 观测数被改成「不可区分」**（44 ⇒ 29）⇒ ⇒ 合成里不再显著 "
     "⇒ ⇒ G0-3 必须红 ⇒ ⇒ 证明「rand 显著 ⇒ N-B」这条端到端构造有效"),
    ("PM7", "impl", "self", "obs_r=40, obs_w=46, blk_r=8, blk_w=21,",
     "obs_r=40, obs_w=46, blk_r=22, blk_w=21,",
     ["G0-5"], None,
     "⚖⚖⚖ **G0-5 夹具的块级观测被改成与轨迹级同向**（8 ⇒ 22）⇒ ⇒ 「方向不一致」不再成立 "
     "⇒ ⇒ G0-5 必须红 ⇒ ⇒ 证明 N-C 的**端到端**构造有效"),
    ("PM8", "impl", "self", "cells_pos=40)", "cells_pos=85)",
     ["G0-6"], None,
     "⚖⚖⚖ **G0-6 夹具的正号数被改成「不显著」**（40 ⇒ 85）⇒ ⇒ 基准不再「不可用」 "
     "⇒ ⇒ G0-6 必须红 ⇒ ⇒ 证明 N-D 的**端到端**构造有效"),
    ("PM9", "impl", "self", "obs_r=29, obs_w=46, blk_r=6, blk_w=21,\n                           cells_pos=85)",
     "obs_r=44, obs_w=46, blk_r=6, blk_w=21,\n                           cells_pos=85)",
     ["G0-4"], None,
     "⚖⚖⚖ **G0-4 夹具的 rand 观测数被改成「显著」**（29 ⇒ 44）⇒ ⇒ 合成里不再不可区分 "
     "⇒ ⇒ G0-4 必须红 ⇒ ⇒ 证明 N-A 的**端到端**构造有效"),
    ("PM10", "impl", "self",
     '        raise HardFail("244.81 段里找不到含 %s 的行（%s）⇒ ⇒ 拒绝兜底" % (list(keys), what))',
     '        return (0, "（静默兜底：读不到就给一行假数据）")',
     ["G0-7"], None,
     "⚖⚖⚖⚖⚖ **单点查找器的「读不到 ⇒ HardFail」被改成静默兜底** ⇒ ⇒ G0-7 的 (a) 子检查必须红 "
     "⇒ ⇒ 证明「读不到必须硬失败」这条纪律**能红**（⛔ 不是判红、⛔ 不是「跳过」）"),
    ("PM11", "impl", "self", "Fraction(math.comb(10, k), 2 ** 10) for k in range(11)",
     "Fraction(math.comb(10, k), 2 ** 11) for k in range(11)",
     ["G0-1"], None,
     "⚖⚖⚖ **G0-1 的「已知答案」被写错**（分母 2**10 ⇒ 2**11）⇒ ⇒ 卷积不再复现 Binomial(10,0.5) "
     "⇒ ⇒ G0-1 必须红 ⇒ ⇒ 证明「解析基准」这条闸门**钉得住实现**"),

    # ---------------- 实现被改：口径 / 判据（data）----------------
    ("PM12", "impl", "data", "        if 2 * k > m:", "        if 2 * k >= m:",
     ["H1-BASECALC"], "N-D",
     "⚖⚖⚖⚖⚖ **多数规则的阈值被从 `nT·2 > m` 改成 `nT·2 >= m`** ⇒ ⇒ base(2,0) 从 1/4 变 3/4 "
     "⇒ ⇒ 现算基准 ≠ 账本印的 ⇒ ⇒ H1 必须红 ⇒ ⇒ 判决形态必须是 **N-D**（基准本身不可用）"),
    ("PM13", "impl", "data", "    ok2 = not (float(p_cell) < alpha)",
     "    ok2 = not (float(p_cell) > alpha)",
     ["H2-CELLBASE"], "N-D",
     "⚖⚖⚖ **H2 的「只判『明显偏低』红」的比较方向被写反**（< ⇒ >）⇒ ⇒ p=0.65 > 0.05 ⇒ 判红 "
     "⇒ ⇒ H2 必须红 ⇒ ⇒ 判决形态必须是 **N-D**"),
    ("PM14", "impl", "data", '    p_traj_r = tail_p(pmf_r, st["obs_r"])',
     '    p_traj_r = tail_p(pmf_r, st["obs_w"])',
     ["H3-TRAJNULL"], "N-C",
     "⚖⚖⚖⚖⚖ **rand 的轨迹级观测数被换成 w 的**（两臂取反 —— ⛔ 244.81 的独立重算器**当场踩过**这个坑类）"
     "⇒ ⇒ rand 变成「显著高于零假设」⇒ ⇒ H3 必须红 ⇒ ⇒ 判决形态必须是 **N-C**（轨迹显著、块不显著）"),
    ("PM15", "impl", "data", "        p = tail_p(pm, st[\"blk_r\"])",
     "        p = tail_p(pm, st[\"blk_w\"])",
     ["H4-BLOCKNULL"], "N-C",
     "⚖⚖⚖⚖⚖ **rand 的块级观测数被换成 w 的** ⇒ ⇒ 块级变成「显著」⇒ ⇒ H4 必须红 "
     "⇒ ⇒ 判决形态必须是 **N-C**"),
    ("PM16", "impl", "data", "    ok5 = (p_traj_w < alpha) and all(p < alpha for _n, p in p_blk_w)",
     "    ok5 = (p_traj_w > alpha) and all(p > alpha for _n, p in p_blk_w)",
     ["H5-POWER"], "N-E",
     "⚖⚖⚖⚖⚖ **H5（判别力）的比较方向被写反** ⇒ ⇒ w 臂 p≈4e-7 不满足「> 0.05」⇒ ⇒ H5 必须红 "
     "⇒ ⇒ 判决形态必须是 **N-E**（⛔ FAIL：⛔ **不是**「没量到」）"),
    ("PM17", "impl", "data", "    iv_up_lo, iv_up_hi = d_obs, d_obs + c_hi",
     "    iv_up_lo, iv_up_hi = d_obs + c_lo, d_obs + c_hi",
     ["H6-MAGNITUDE"], "N-E",
     "⚖⚖⚖ **「假定污染抬高」那条区间的下端点被改用 c_lo**（Q8 的公式被改）⇒ ⇒ H6 必须红 "
     "⇒ ⇒ 判决形态必须是 **N-E**"),
    ("PM18", "impl", "data",
     "    d_calc = 100.0 * (st[\"obs_w\"] / float(st[\"n_w\"]) - st[\"obs_r\"] / float(st[\"n_r\"]))",
     "    d_calc = 100.0 * (st[\"obs_w\"] / float(st[\"n_w\"]) + st[\"obs_r\"] / float(st[\"n_r\"]))",
     ["H7-PROVENANCE"], "N-E",
     "⚖⚖⚖⚖⚖ **H7 的「观测差」交叉校验公式被改**（减 ⇒ 加）⇒ ⇒ 算出的差与账本印的 +30.36 pp 对不上 "
     "⇒ ⇒ H7 必须红 ⇒ ⇒ 判决形态必须是 **N-E**"),
    ("PM19", "impl", "data", "    tol_w = tol_from(raw[\"I11\"])",
     "    tol_w = 1e-9",
     ["H7-PROVENANCE"], "N-E",
     "⚖⚖⚖ **H7 的 Wilson 交叉校验容差被改紧 7 个量级**（0.005 pp ⇒ 1e-9 pp）⇒ ⇒ 现算与印出的差被抓住 "
     "⇒ ⇒ H7 必须红 ⇒ ⇒ 判决形态必须是 **N-E**"),
    ("PM20", "impl", "data", "    md5_after_parse = md5_of(ledger_path)",
     "    md5_after_parse = md5_of(__file__)",
     ["H8-READONLY"], "N-E",
     "⚖⚖⚖⚖⚖ **H8 的「运行后账本 md5」取错了文件**（取成实现自己 —— ⛔ 真实的「取错对象」bug）"
     "⇒ ⇒ 前后 md5 不等 ⇒ ⇒ H8 必须红 ⇒ ⇒ 判决形态必须是 **N-E**"),
    ("PM21", "impl", "data", "            return j          # 0-based ⇒ 1-based 的「下一段标题行 − 1」＝ 段尾",
     "            return j + 1",
     ["H8-READONLY"], "N-E",
     "⚖⚖⚖ **H8 的「第二种段尾算法」被挪了一行**（正则法 vs 字符串法不再一致）⇒ ⇒ H8 必须红 "
     "⇒ ⇒ 判决形态必须是 **N-E**"),
    ("PM22", "impl", "data", '    "alpha": 0.05,', '    "alpha": 0.999,',
     ["H2-CELLBASE"], "N-D",
     "⚖⚖⚖ **显著性水平被改到 0.999** ⇒ ⇒ 「明显偏低」这条判据被放大成「几乎都偏低」⇒ ⇒ H2 必须红 "
     "⇒ ⇒ 判决形态必须是 **N-D**"),

    # ---------------- 账本被改（data）----------------
    ("PL1", "ledger", "data", "  · pos_frac=0.25  格数=56  正=25  负=29  零=2\n", "",
     [], None,
     "⚖⚖⚖⚖⚖ **账本里 rand 臂的一行逐格统计被整行删掉** ⇒ ⇒ 输入读不到 ⇒ ⇒ 必须 **HardFail**"
     "（⛔ 不是判红、⛔ 不是「跳过」、⛔ 不是静默降级）⇒ ⇒ 这条纪律单独有变异体守着"),
]

# ⚖ 期望的判决形态（None = 不要求）
EXPECT_VERDICT = {}
for _mid, _cat, _mode, _p, _r, _exp, _v, _n in MUTATIONS:
    if _v:
        EXPECT_VERDICT[_mid] = _v
# ⚖ PL1 期望的是「硬失败」，不是「某个判据变红」
EXPECT_HARDFAIL = {"PL1"}


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
    if rc != 0 or "SELFTEST_RC=0" not in out:
        print("⛔ 阳性对照（--selftest）没过 ⇒ 「全红」什么也证明不了 ⇒ 中止")
        print(out[-2000:])
        print(err[-2000:])
        return 4
    print("[阳性对照] --selftest 全绿 ✅")

    # ---- 阳性对照（data）----
    if self_only:
        print("[阳性对照] --data **跳过**（--self-only）")
    else:
        rc, out, err = _run([PY, os.path.join(HERE, TARGET), "--data", "--ledger", LEDGER])
        if "VERDICT=" not in out:
            print("⛔ 阳性对照（--data）没跑出判决形态 ⇒ 中止")
            print(out[-3000:])
            print(err[-3000:])
            return 4
        _mv = re.search(r"^VERDICT=(\S+)$", out or "", re.M)
        print("[阳性对照] --data 跑出判决形态 %s ✅（rc=%d）"
              % (_mv.group(1) if _mv else "?", rc))

    caught, missed, invalid, crashed = [], [], [], []
    for mid, cat, mode, pat, rep, expect, want_v, note in MUTATIONS:
        if self_only and mode != "self":
            continue
        tmp = tempfile.mkdtemp(prefix="mut86_%s_" % mid, dir="/dev/shm")
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
                got_hf = "HARD_FAIL:" in (out or "")
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
            if want_v:
                _mv = re.search(r"^VERDICT=(\S+)$", out or "", re.M)
                got_v = _mv.group(1) if _mv else "(没印)"
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
