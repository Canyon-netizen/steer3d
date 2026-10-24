#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""mut_loo_robustness_audit.py —— **类级结论留一稳健性**的变异台（244.85）。

⚖⚖⚖⚖⚖ **这个台架要回答的问题**
   「`loo_robustness_audit.py` 的每条判据**是不是恒绿的**？」
   ⇒ ⇒ 必须证明它们**能红**：
     · **实现被改**（阈值 / 容差 / 子集族 / 参考种子区间 / 余弦口径 / 置换方式 / 判决映射表 / …）
       ⇒ ⇒ 对应判据必须由 PASS 变 FAIL；
     · **数据被改**（向量副本 / sidecar 副本）⇒ ⇒ 对应判据必须红；
     · **账本被改**（判决形态 / 逐条余弦的副本）⇒ ⇒ 对应判据必须红。

⚖⚖⚖⚖⚖ **纪律（从 244.66–244.84 的台架继承，一条都不许放松）**
   ① 每条变异只改**一处**（⛔ 改多处 ⇒ 抓到了也不知道是哪一处抓的）；
   ② 每条变异必须**恰好命中 1 处**（⛔ 命中 0 ⇒ 这条变异**无效** ⇒ 必须报出来；
      ⛔ **等价变异（什么都没变）记「无效」，⛔ 不是「存活」**）；
   ③ ⛔ **「崩」≠「抓到」** ⇒ 崩了单独报 ⇒ 崩的条数必须压到 **0**；
   ④ **阳性对照先过**：不改任何东西时，目标必须**跑出判决形态** ⇒ ⇒
      否则「全红」什么也证明不了 ⇒ ⇒ 直接退出；
   ⑤ 期望的「哪条该红」是**手写**的 ⇒ ⇒ **不许从被检对象派生**；
   ⑥ ⛔ 本台架**不改**目标实现、⛔ 不改预登记、⛔ 不改原始产物
      ⇒ ⇒ 数据/账本变异只发生在**临时目录里的副本**上；
   ⑦ ⛔ 缺前置/远端产物 ⇒ 报 **`PRECOND_FAIL`**（⛔ 这样回归器才判「跑不动」，
      ⛔ **不是**「本轮引入的红」⇒ ⇒ 冤枉）；
   ⑧ ⚖ **「把容差改紧 ⇒ 判据变红」也算一种合法变异**。

⚖⚖⚖⚖⚖ **244.85 特有的一条纪律**
   244.84 的教训：变异台**只断言「哪些判据变红」** ⇒ ⇒ 死分支藏不住
   ⇒ ⇒ 本台架**同时断言判决形态**（`EXPECT_VERDICT`）
   ⇒ ⇒ 且**判决映射表**本身也要有变异体守着（PM3/PM4/PM5）
   ⇒ ⇒ 五个形态（F-A / F-B / F-C / F-E / FAIL）的**可达性**由 Phase-0 的 G0-3/G0-4/G0-5/G0-6 守。
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BPATH = os.environ.get("R244_BPATH", "/home/zhourui/steer3d_bpath")
LEDGER = os.environ.get("R244_LEDGER", "/home/zhourui/steer3d/.cache/xcheck/R6_RERUN_PREREG.md")
TARGET = "loo_robustness_audit.py"
PY = os.environ.get("R244_PY", "/home/zhourui/miniconda3/envs/easysteer/bin/python")

# ⚖ 判据 id（真数据路径印的是这些）
CRIT_RE = re.compile(r"^\[(PASS|FAIL)\]\s+(\S+)", re.M)
GATE_RE = re.compile(r"^\[(PASS|FAIL)\]\s+(G0-\d)", re.M)
CRASH_RE = re.compile(r"^(Traceback \(most recent call last\)|\w*(?:Error|Exception)\b)", re.M)

# ⚖ (编号, 类别, 模式, 落点串, 替换串, 期望红的判据 id（列表）, 说明)
#    模式 "self" = 跑 `--selftest`（⛔ 不依赖远端产物）；"data" = 跑真数据路径
#    类别 "impl" = 改**实现源码副本**；"data" = 改**产物副本**；"ledger" = 改**账本副本**
MUTATIONS = [
    # ---------------- 实现被改：Phase-0 闸门（self）----------------
    ("PM1", "impl", "self", '"z_threshold": 2.0,', '"z_threshold": -99.0,',
     ["G0-1"],
     "⚖⚖⚖ **判决阈值被改成 −99** ⇒ ⇒ 连「无结构」的夹具也会被判成 E-B "
     "⇒ ⇒ G0-1 必须红 ⇒ ⇒ 证明「E-A 那一支」不是恒绿"),
    ("PM2", "impl", "self", "_fixture_shared(900201, d, frac=0.8)",
     "_fixture_shared(900201, d, frac=0.0)",
     ["G0-2"],
     "⚖⚖⚖ **G0-2 的公共分量被去掉**（0.8 ⇒ 0.0）⇒ ⇒ 结构夹具不再有结构 "
     "⇒ ⇒ G0-2 必须红 ⇒ ⇒ 证明「E-B 那一支」不是恒绿"),
    ("PM3", "impl", "self", '("dose_ea", True, "F-B"),', '("dose_ea", True, "F-C"),',
     ["G0-3"],
     "⚖⚖⚖⚖⚖ **判决映射表里的 F-B 被改成 F-C** ⇒ ⇒ 「去掉剂量那一把 ⇒ F-B」这条承诺被破坏 "
     "⇒ ⇒ G0-3 必须红 ⇒ ⇒ **F-B 这一支不是死代码**"),
    ("PM4", "impl", "self", '("other_loo_ea", True, "F-C"),', '("other_loo_ea", True, "F-B"),',
     ["G0-3"],
     "⚖⚖⚖⚖⚖ **判决映射表里的 F-C 被改成 F-B** ⇒ ⇒ G0-3 必须红 ⇒ ⇒ **F-C 这一支不是死代码**"),
    ("PM5", "impl", "self", 'if shapes.get(k) == "E-A":', 'if shapes.get(k) == "E-B":',
     ["G0-3"],
     "⚖⚖⚖⚖⚖ **「另有子集掉出阈值」这个条件的比较方向被写反**（E-A ⇒ E-B）"
     "⇒ ⇒ 「全部子集仍在 ⇒ F-A」被破坏 ⇒ ⇒ G0-3 必须红 ⇒ ⇒ **F-A 这一支不是死代码**"),
    ("PM6", "impl", "self", 'role5["w_t1"] = 0.35', 'role5["w_t1"] = 0.0',
     ["G0-5"],
     "⚖⚖⚖ **G0-5 夹具的「主贡献位」被抹成 0** ⇒ ⇒ 「去掉剂量位仍在、去掉主贡献位掉出」不再成立 "
     "⇒ ⇒ G0-5 必须红 ⇒ ⇒ 证明 F-C 的**端到端**构造有效"),
    ("PM7", "impl", "self", "Ts[:half] = [x * 3.0 for x in Ts[:half]]",
     "Ts[:half] = [x * 1.0 for x in Ts[:half]]",
     ["G0-7"],
     "⚖⚖⚖ **G0-7 的「人为污染」被取消**（×3 ⇒ ×1）⇒ ⇒ 参考分布不再偏离理论 "
     "⇒ ⇒ G0-7 必须红 ⇒ ⇒ 证明「校准判据（⇒ H8）有牙齿」"),

    # ---------------- 实现被改：阈值 / 容差（data）----------------
    ("PM8", "impl", "data", '"z_threshold": 2.0,', '"z_threshold": 3.0,',
     ["H7-FULLFORM"],
     "⚖⚖⚖⚖⚖ **判决阈值被改成 3.0** ⇒ ⇒ FULL 的形态从 E-B 变成 E-A（而 H9 的假阳性率**仍然合格**）"
     "⇒ ⇒ **只有 H7 能抓到它** ⇒ ⇒ H7 必须红 ⇒ ⇒ 证明「基线形态」这条判据**不是恒绿的**"),
    ("PM9", "impl", "data", '"fpr_max": 0.05,', '"fpr_max": 0.0001,',
     ["H9-DISC"],
     "⚖⚖⚖⚖⚖ **规则假阳性率上限被改到 0.0001** ⇒ ⇒ H9 必须红 "
     "⇒ ⇒ 判决形态必须是 **F-E**（判别力不足 ⇒ 未量到）⇒ ⇒ ⛔ **不是 FAIL**"),
    ("PM10", "impl", "data", '"class_sd_rel_tol": 0.05,', '"class_sd_rel_tol": 1e-9,',
     ["H8-CALIB"],
     "⚖⚖⚖ **逐子集校准容差被改紧 7 个量级**（0.05 ⇒ 1e-9）⇒ ⇒ 实测相对差 ~1e-3 > 1e-9 "
     "⇒ ⇒ H8 必须红 ⇒ ⇒ 证明「零分布逐子集被校准」这条判据**不是恒绿的**"),
    ("PM11", "impl", "data", '"ref_class_seed_lo": 100001,', '"ref_class_seed_lo": 1,',
     ["H11-SELFINCLUDE"],
     "⚖⚖⚖⚖⚖ **零分布的种子区间被改回「含构造种子 42」的形态**（100001 ⇒ 1）"
     "⇒ ⇒ 零分布**自包含** ⇒ ⇒ H11 的「交集 = ∅」必须红"),
    ("PM12", "impl", "data", '"negctl_z_max": 2.0,', '"negctl_z_max": 0.001,',
     ["H10-NEGCTL"],
     "⚖⚖⚖ **负控的 |z| 上限被改到 0.001** ⇒ ⇒ 负控必须红 ⇒ ⇒ 证明「负控真的在检查负控」"),

    # ---------------- 实现被改：口径 / 出处（data）----------------
    ("PM13", "impl", "data", "* float(np.linalg.norm(w0))",
     "* float(np.linalg.norm(w0.astype(np.float64)))",
     ["H6-CROSSROUND"],
     "⚖⚖⚖⚖⚖ **rand 向量的缩放因子从 float32 口径改回 float64 口径**"
     "（⛔ 这正是 244.83 当场抓到的那个真 bug）⇒ ⇒ 余弦差 6.4e-10（相对）"
     "⇒ ⇒ **只有 244.83 段的全精度 cos0 锚**抓得到 ⇒ ⇒ H6 必须红"),
    ("PM14", "impl", "data", "    m = m / n", "    m = m / (n + 1)",
     ["H6-CROSSROUND"],
     "⚖⚖⚖ **理论 sd 的 m 被算错**（均值除以 n ⇒ n+1）⇒ ⇒ 理论 sd 偏 ~14% "
     "⇒ ⇒ H6 的「理论 sd」对账与 H8 的校准都必须红"),
    ("PM15", "impl", "data",
     '"LOO-p2a": ["w_L19_m0", "w_L19_m1", "w_real", "w_t1", "w_old"],',
     '"LOO-p2a": ["w_L19_m0", "w_L19_m1", "w_real", "w_t1"],',
     ["H5-FAMILY"],
     "⚖⚖⚖⚖⚖ **关键位子集的成员被改**（5 把 ⇒ 4 把）⇒ ⇒ 与程序化构造的族不一致 "
     "⇒ ⇒ H5 必须红 ⇒ ⇒ 证明「子集族 = 预登记 §2.1」这条判据**不是恒绿的**"),
    ("PM16", "impl", "data", '"dose_w": "w_p2a",', '"dose_w": "w_old",',
     ["H1-IDENT"],
     "⚖⚖⚖ **「剂量批用的那把 w」被换成 w_old** ⇒ ⇒ class_gap=319.89 ≠ 113.474 "
     "⇒ ⇒ H1 必须红 ⇒ ⇒ 证明「身份链」被守住了"),
    ("PM17", "impl", "data", '"train_seed": 42,', '"train_seed": 43,',
     ["H2-PROVENANCE"],
     "⚖⚖⚖ **训练种子被改成 43** ⇒ ⇒ 6 把 sidecar 的 seed=42 与之不符 ⇒ ⇒ H2 必须红"),
    ("PM18", "impl", "data", '"layer": 20,', '"layer": 19,',
     ["H2-PROVENANCE"],
     "⚖⚖⚖ **注入层被改成 19** ⇒ ⇒ sidecar layer=20 与之不符 ⇒ ⇒ H2 必须红"),
    ("PM19", "impl", "data",
     'exp_max_nm = max(names, key=lambda nm: exp["cos_each"][nm])',
     'exp_max_nm = "w_real"',
     ["H12-MAXCOS"],
     "⚖⚖⚖ **「余弦最大的那把」被改成与别的成员比** ⇒ ⇒ H12 必须红 "
     "⇒ ⇒ 证明「关键位的依据」这条判据**真的被算**，⛔ 不是恒绿"),

    # ---------------- 数据被改（data）----------------
    ("PD1", "data", "data", None, None,
     ["H1-IDENT"],
     "⚖⚖⚖ **w_p2a.npy 的副本被篡改一个字节** ⇒ ⇒ 实测 md5 与账本登记不符 "
     "⇒ ⇒ H1 的 md5 对账必须红 ⇒ ⇒ 证明「产物 md5 对账」不是恒绿的"),
    ("PD2", "data", "data", None, None,
     ["H2-PROVENANCE"],
     "⚖⚖⚖ **w_real 的 sidecar 副本的 seed 被改成 7** ⇒ ⇒ 6 把种子不再一致 ⇒ ⇒ H2 必须红"),

    # ---------------- 账本被改（ledger）----------------
    ("PL1", "ledger", "data",
     "**判决形态 E-B**",
     "**判决形态 E-A**",
     ["H7-FULLFORM"],
     "⚖⚖⚖⚖⚖ **账本副本里 244.84 登记的判决形态被改成 E-A** ⇒ ⇒ 本轮重算的 FULL 仍是 E-B "
     "⇒ ⇒ H7 必须红 ⇒ ⇒ 证明「基线形态对账」这条判据**真的在读账本**"),
    ("PL2", "ledger", "data",
     "`w_t1` → **+0.049091939**",
     "`w_t1` → **+0.099091939**",
     ["H12-MAXCOS"],
     "⚖⚖⚖ **账本副本里 w_t1 的余弦被改成 6 把里最大** ⇒ ⇒ 「关键位 = 剂量那一把」的前提被推翻 "
     "⇒ ⇒ H12 必须红"),
    ("PL3", "ledger", "data",
     "| **类级主统计量** `T = mean_i cos(v_i, r₀)` | **+0.026669793515452608** | 6 把 w 对同一把 r₀ |",
     "| **类级主统计量** `T = mean_i cos(v_i, r₀)` | **+0.026669793515452612** | 6 把 w 对同一把 r₀ |",
     ["H13-BITIDENT"],
     "⚖⚖⚖⚖⚖ **账本副本里 244.84 的类级 T 被挪了 1 个 ULP**（`+0.026669793515452608` ⇒ "
     "`+0.026669793515452612`，相对差 **1.3e-16**）⇒ ⇒ **H6 的「相对差 ≤ 1e-12」照样绿** "
     "⇒ ⇒ **H13（位级对账）必须红** ⇒ ⇒ 证明「逐位」这条守卫**真的在比位**、"
     "⛔ **不是**「相对差 ≤ 1e-12」的同义词（⚠ 落点用**整行**锚 ⇒ ⇒ 落账前后都恰好命中 1 处）"),
]

# ⚖⚖⚖⚖⚖ **判决形态的期望**（⛔ 早先的变异台**只断言「哪些判据变红」**，⛔ **不看判决形态**
#   ⇒ ⇒ 死分支抓不到 ⇒ ⇒ 现在把**判决形态**也纳入断言）
EXPECT_VERDICT = {
    "PM9":  "F-E",     # H9（逐 n 判别力）红 ⇒ ⇒ 形态只能是 F-E（「判别力不足 ⇒ 未量到」）
    "PM8":  "FAIL",    # H7（基线形态）红 ⇒ ⇒ 前提被推翻 ⇒ ⇒ 形态 FAIL（⛔ 不是 F-E）
    "PM10": "FAIL",    # H8（校准）红 ⇒ ⇒ 前提被推翻
    "PM11": "FAIL",    # H11（自包含）红 ⇒ ⇒ 前提被推翻
    "PM12": "FAIL",    # H10（负控）红 ⇒ ⇒ 前提被推翻
    "PM13": "FAIL",    # H6（跨轮对账）红 ⇒ ⇒ 前提被推翻
    "PM15": "FAIL",    # H5（子集族）红 ⇒ ⇒ 前提被推翻
    "PM16": "FAIL",    # H1（身份）红 ⇒ ⇒ 前提被推翻
    "PM17": "FAIL",    # H2（出处）红 ⇒ ⇒ 前提被推翻
    "PM18": "FAIL",    # H2（出处）红 ⇒ ⇒ 前提被推翻
    "PM19": "FAIL",    # H12（关键位依据）红 ⇒ ⇒ 前提被推翻
    "PD1":  "FAIL",    # 同上（**从数据侧**篡改）
    "PD2":  "FAIL",    # 同上（从 sidecar 侧篡改）
    "PL1":  "FAIL",    # 同上（从**账本侧**篡改）
    "PL3":  "FAIL",    # 同上（账本侧挪 1 ULP ⇒ H6 绿 / **H13 红** ⇒ ⇒ 证明「逐位」这条有牙齿）
}


def _run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, p.stdout or "", p.stderr or ""


def _parse_ids(out):
    """⚖ 抽出印出来的判据 id 与它们的状态。"""
    ids = {}
    for m in CRIT_RE.finditer(out):
        ids[m.group(2)] = (m.group(1) == "PASS")
    return ids


def _parse_gates(out):
    ids = {}
    for m in GATE_RE.finditer(out):
        ids[m.group(2)] = (m.group(1) == "PASS")
    return ids


def _bpath_copy(tmp):
    """⚖ 把 bpath 里**本轮要读的**那些产物复制到临时目录（⛔ 不改原 bpath）。"""
    dst = os.path.join(tmp, "bpath")
    os.makedirs(dst, exist_ok=True)
    names = ["w_L19_m0.npy", "w_L19_m1.npy", "w_real.npy", "w_t1.npy", "w_p2a.npy",
             "w_old.npy", "w_L19_m0.npy.json", "w_L19_m1.npy.json", "w_real.npy.json",
             "w_t1.npy.json", "w_p2a.npy.json", "w_old.npy.json",
             "r241_probe.py", "r244_warm_sweep.sh", "r244_warm_fd_w.log",
             "r244_warm_fd_rand.log"]
    for n in names:
        src = os.path.join(BPATH, n)
        if not os.path.isfile(src):
            return None, "缺远端产物：%s" % src
        shutil.copy2(src, os.path.join(dst, n))
    for n in ("r6_221.py",):
        src = os.path.join(BPATH, n)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(dst, n))
    return dst, None


def main():
    self_only = "--self-only" in sys.argv
    if not os.path.isfile(os.path.join(HERE, TARGET)):
        print("PRECOND_FAIL: 找不到被检实现 %s" % TARGET)
        return 2
    if not os.path.isfile(LEDGER):
        print("PRECOND_FAIL: 账本不存在 %s" % LEDGER)
        return 2
    if not os.path.isdir(BPATH):
        print("PRECOND_FAIL: bpath 不存在 %s" % BPATH)
        return 2

    print("变异台：%s ｜ %d 条变异%s"
          % (TARGET, len(MUTATIONS), "（⛔ 只跑 self 模式）" if self_only else ""))

    # ---- 阳性对照（self）----
    rc, out, err = _run([PY, os.path.join(HERE, TARGET), "--selftest"])
    if rc != 0 or "SELFTEST_RC=0" not in out:
        print("⛔ 阳性对照（--selftest）没过 ⇒ 「全红」什么也证明不了 ⇒ 中止")
        print(out[-2000:])
        print(err[-2000:])
        return 4
    print("[阳性对照] --selftest 全绿 ✅")

    # ---- 阳性对照（data）----
    tmp0 = None
    if self_only:
        print("[阳性对照] --data **跳过**（--self-only）")
    else:
        tmp0 = tempfile.mkdtemp(prefix="mut85_pos_", dir="/dev/shm")
        bpc, err = _bpath_copy(tmp0)
        if bpc is None:
            print("PRECOND_FAIL: %s" % err)
            return 2
        rc, out, err = _run([PY, os.path.join(HERE, TARGET), "--data",
                             "--bpath", bpc, "--ledger", LEDGER])
        # ⚖⚖⚖ **阳性对照的通过条件**：跑出**判决形态**即可（⛔ 不要求 DATA_RC=0：
        #   若本轮真形态就是 FAIL/前提被推翻 ⇒ DATA_RC=1 是**正确的** ⇒ ⇒ 不能因此判阳性对照失败）
        if "VERDICT=" not in out:
            print("⛔ 阳性对照（--data）没跑出判决形态 ⇒ 中止")
            print(out[-3000:])
            print(err[-3000:])
            return 4
        _mv = re.search(r"^VERDICT=(\S+)$", out or "", re.M)
        print("[阳性对照] --data 跑出判决形态 %s ✅（rc=%d）"
              % (_mv.group(1) if _mv else "?", rc))
    if tmp0 is not None:
        shutil.rmtree(tmp0, ignore_errors=True)

    caught, missed, invalid, crashed = [], [], [], []
    for mid, cat, mode, pat, rep, expect, note in MUTATIONS:
        if self_only and mode != "self":
            continue
        tmp = tempfile.mkdtemp(prefix="mut85_%s_" % mid, dir="/dev/shm")
        try:
            tgt = os.path.join(tmp, TARGET)
            shutil.copy2(os.path.join(HERE, TARGET), tgt)
            bpc = None
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
            # ⚖⚠ **凡是走数据路径的变异都要一份 bpath 副本**
            if mode == "data":
                bpc, err = _bpath_copy(tmp)
                if bpc is None:
                    print("PRECOND_FAIL: %s" % err)
                    return 2
            if cat == "data":
                if mid == "PD1":
                    p = os.path.join(bpc, "w_p2a.npy")
                    b = bytearray(open(p, "rb").read())
                    # ⚠⚠⚠ **必须篡改「数据区」的字节，不能碰文件头** ——
                    #   `.npy` 的头部占前 128 字节 ⇒ ⇒ 改头部会让 `np.load` 直接抛 ValueError
                    #   ⇒ ⇒ 那是**崩** ⇒ ⛔ **崩 ≠ 抓到** ⇒ ⇒ 改第 200 字节（落在 float32 数据区内）
                    assert len(b) >= 8320, "⛔ w_p2a.npy 比预期短 ⇒ 偏移量要重算"
                    assert 128 < 200 < len(b), "⛔ 偏移 200 落在文件头或越界 ⇒ 重算"
                    b[200] = (b[200] + 1) % 256
                    open(p, "wb").write(bytes(b))
                elif mid == "PD2":
                    p = os.path.join(bpc, "w_real.npy.json")
                    t = open(p, encoding="utf-8").read().replace('"seed": 42', '"seed": 7', 1)
                    open(p, "w", encoding="utf-8").write(t)

            cmd = [PY, tgt]
            if mode == "self":
                cmd.append("--selftest")
            else:
                cmd += ["--data", "--bpath", bpc, "--ledger", led]
            rc, out, err = _run(cmd)
            if CRASH_RE.search(err or "") or "Traceback" in (out or ""):
                print("[崩] %s  ⇒ 崩的条数必须压到 0" % mid)
                print((err or out)[-1200:])
                crashed.append(mid)
                continue
            ids = _parse_gates(out) if mode == "self" else _parse_ids(out)
            red = sorted([k for k, v in ids.items() if not v])
            hit = [e for e in expect if e in red]
            # ⚖⚖⚖ **判决形态也要对**（⛔ 早先只看「哪些判据红」⇒ ⇒ 死分支抓不到）
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
