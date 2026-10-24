#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""mut_alignment_distribution_audit.py —— **对照臂方向污染类级判读**的变异台（244.84）。

⚖⚖⚖⚖⚖ **这个台架要回答的问题**
   「`alignment_distribution_audit.py` 的每条判据**是不是恒绿的**？」
   ⇒ ⇒ 必须证明它们**能红**：
     · **实现被改**（阈值 / 种子区间 / 参考分布构造 / 余弦口径 / 置换方式 / …）
       ⇒ ⇒ 对应判据必须由 PASS 变 FAIL；
     · **数据被改**（向量副本 / sidecar 副本）⇒ ⇒ 对应判据必须红。

⚖⚖⚖⚖⚖ **纪律（从 244.66–244.83 的台架继承，一条都不许放松）**

   ① 每条变异只改**一处**（⛔ 改多处 ⇒ 抓到了也不知道是哪一处抓的）
   ② 每条变异必须**恰好命中 1 处**（⛔ 命中 0 ⇒ 这条变异**无效** ⇒ 必须报出来；
      ⛔ **等价变异（什么都没变）记「无效」，⛔ 不是「存活」**）
   ③ ⛔ **「崩」≠「抓到」** ⇒ 崩了单独报 ⇒ 崩的条数必须压到 **0**
   ④ **阳性对照先过**：不改任何东西时，目标必须**全绿** ⇒ ⇒
      否则「全红」什么也证明不了 ⇒ ⇒ 直接退出
   ⑤ 期望的「哪条该红」是**手写**的 ⇒ ⇒ **不许从被检对象派生**
   ⑥ ⛔ 本台架**不改**目标实现、⛔ 不改预登记、⛔ 不改原始产物
      ⇒ ⇒ 数据变异只发生在**临时目录里的副本**上
   ⑦ ⛔ 缺前置/远端产物 ⇒ 报 **`PRECOND_FAIL`**（⛔ 这样回归器才判「跑不动」，
      ⛔ **不是**「本轮引入的红」⇒ ⇒ 冤枉）
   ⑧ ⚖ **「把容差改紧 ⇒ 判据变红」也算一种合法变异**
      ⇒ ⇒ 它证明的是「这条判据**不是恒绿**」⇒ ⇒ 与「放宽容差」方向相反，但同样必要。

⚖⚖⚖⚖⚖ **244.84 特有的一条纪律（本台架的来历）**
   本轮 Phase-0 闸门**当场抓到**了一个真统计缺陷：**零分布「自包含」**
   ⇒ ⇒ 构造成分种子落在参考种子区间里 ⇒ ⇒ 参考分布被系统性抬高（实测 sd 相对理论 0.41–0.43）
   ⇒ ⇒ 因此本台架**必须**有一条变异把参考种子区间改回自包含的形态
   ⇒ ⇒ 并且**必须**由 **H13**（自包含闸）抓住
   ⇒ ⇒ ⚠ 否则「H13 是恒绿的」这件事没人知道。
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
TARGET = "alignment_distribution_audit.py"
PY = os.environ.get("R244_PY", "/home/zhourui/miniconda3/envs/easysteer/bin/python")

# ⚖ 判据 id（真数据路径印的是这些）
CRIT_RE = re.compile(r"^\[(PASS|FAIL)\]\s+(\S+)", re.M)
GATE_RE = re.compile(r"^\[(PASS|FAIL)\]\s+(G0-\d)", re.M)
CRASH_RE = re.compile(r"^(Traceback \(most recent call last\)|\w*(?:Error|Exception)\b)", re.M)

# ⚖ (编号, 类别, 模式, 落点串, 替换串, 期望红的判据 id（列表）, 说明)
#    模式 "self" = 跑 `--selftest`（⛔ 不依赖远端产物）；"data" = 跑真数据路径
#    类别 "impl" = 改**实现源码副本**；"data" = 改**产物副本**
MUTATIONS = [
    # ---------------- 实现被改：Phase-0 闸门（self）----------------
    ("PM1", "impl", "self", '"z_threshold": 2.0,', '"z_threshold": -99.0,',
     ["G0-1"],
     "⚖⚖⚖ **判决阈值被改成 −99** ⇒ ⇒ 连「无结构」的夹具也会被判成 E-B "
     "⇒ ⇒ G0-1 必须红 ⇒ ⇒ 证明「E-A 那一支」不是恒绿"),
    ("PM2", "impl", "self", "common_frac=0.8", "common_frac=0.0",
     ["G0-2"],
     "⚖⚖⚖ **G0-2 的公共分量被去掉**（0.8 ⇒ 0.0）⇒ ⇒ 结构夹具不再有结构 "
     "⇒ ⇒ G0-2 必须红 ⇒ ⇒ 证明「E-B 那一支」不是恒绿"),
    ("PM3", "impl", "self", "Ts[:half] = [x * 3.0 for x in Ts[:half]]",
     "Ts[:half] = [x * 1.0 for x in Ts[:half]]",
     ["G0-3"],
     "⚖⚖⚖ **G0-3 的「人为污染」被取消**（×3 ⇒ ×1）⇒ ⇒ 参考分布不再偏离理论 "
     "⇒ ⇒ G0-3 必须红 ⇒ ⇒ 证明「参考没校准 ⇒ E-C」这条闸门有牙齿"),

    # ---------------- 实现被改：零分布自包含（本轮的来历）----------------
    ("PM4", "impl", "data", '"ref_class_seed_lo": 100001,', '"ref_class_seed_lo": 1,',
     ["H13-SELFINCLUDE"],
     "⚖⚖⚖⚖⚖ **类级零分布的种子区间被改回「含构造种子 42」的形态**（100001 ⇒ 1）"
     "⇒ ⇒ 零分布**自包含** ⇒ ⇒ H13 的「交集 = ∅」必须红 "
     "⇒ ⇒ **这一条是本轮最重要的变异**（它证明 H13 不是恒绿的）"),

    # ---------------- 实现被改：阈值 / 容差（data）----------------
    ("PM5", "impl", "data", '"negctl_z_max": 2.0,', '"negctl_z_max": 0.001,',
     ["H11-NEGCONTROL"],
     "⚖⚖⚖ **负控的 |z| 上限被改到 0.001** ⇒ ⇒ 负控必须红 "
     "⇒ ⇒ 证明「负控真的在检查负控」"),
    ("PM6", "impl", "data", '"fpr_max": 0.05,', '"fpr_max": 0.0001,',
     ["H12-FPR"],
     "⚖⚖⚖ **规则假阳性率上限被改到 0.0001** ⇒ ⇒ H12 必须红 "
     "⇒ ⇒ 证明「判别力判据真的在判别力」"),
    ("PM7", "impl", "data", '"ref_sd_rel_tol": 0.05,', '"ref_sd_rel_tol": 1e-9,',
     ["H6-CROSSROUND"],
     "⚖⚖⚖ **单向量参考 sd 的容差被改紧 7 个量级**（0.05 ⇒ 1e-9）"
     "⇒ ⇒ 实测相对差 0.016 > 1e-9 ⇒ ⇒ H6 必须红 ⇒ ⇒ 证明它**不是恒绿**"),
    ("PM8", "impl", "data", '"cross_rel_tol": 1e-12,', '"cross_rel_tol": 1e-18,',
     ["H5-CLASSCOS"],
     "⚖⚖⚖ **跨轮对账容差被改到 1e-18** ⇒ ⇒ 244.83 两条路线的尾数差 6e-17 会超限 "
     "⇒ ⇒ H5 必须红 ⇒ ⇒ 证明「跨轮对账不是恒绿」"),

    # ---------------- 实现被改：参考分布与余弦口径（data）----------------
    ("PM9", "impl", "data", "def shuffle_indep(v, seed):",
     "def shuffle_indep(v, seed, _cache={}):\n"
     "    # ⚠⚖ **变异体**：6 把**共用同一个**置换（⇒ 正交变换 ⇒ 保内积 ⇒ 共享结构没被破坏）\n"
     "    v = np.asarray(v, dtype=np.float64).ravel()\n"
     "    g = np.random.default_rng(int(seed))\n"
     "    if 'p' not in _cache:\n"
     "        _cache['p'] = g.permutation(v.shape[0])\n"
     "    return v[_cache['p']]",
     ["H11-NEGCONTROL"],
     "⚖⚖⚖⚖⚖ **独立坐标置换被改成「6 把共用同一个置换」** ⇒ ⇒ 那是**正交变换** "
     "⇒ ⇒ 两两余弦原封不动 ⇒ ⇒ 共享结构**没被破坏** ⇒ ⇒ H11 的「置换后两两余弦上限」必须红 "
     "⇒ ⇒ 证明这条守得住"),
    ("PM10", "impl", "data", "rank1 = sum(1 for x in ref1 if x < cos_w_p2a) / float(len(ref1))",
     "rank1 = sum(1 for x in ref1 if x < cos_w_p2a) / float(len(ref1) - 1)",
     ["H6-CROSSROUND"],
     "⚖⚖⚖ **经验秩的分母被改错**（len(ref1) ⇒ len(ref1)−1）⇒ ⇒ 秩从 1994/2000 = 0.997 变成 "
     "1994/1999 ⇒ ⇒ 与账本登记的 0.997 不符 ⇒ ⇒ H6 必须红 "
     "（⚠ 试过改「<」为「≤」**不成立**：参考值不可能与被观测值**精确相等** ⇒ ⇒ 秩根本不变 ⇒ ⇒ "
     "那条变异是**无效**的，⛔ 不是「存活」）"),
    ("PM11", "impl", "data", "    for k in range(1, int(K) + 1):",
     "    for k in range(0, int(K) + 1):",
     ["H6-CROSSROUND"],
     "⚖⚖⚖ **单向量参考的种子起点从 1 改成 0**（把**被观测的**那个种子也放进参考集）"
     "⇒ ⇒ 秩/z 必然变 ⇒ ⇒ H6 必须红 ⇒ ⇒ 证明「种子 1..K、排除 0」这条口径被守住了"),
    ("PM12", "impl", "data",
     "    w = (w / np.linalg.norm(w)) * float(np.linalg.norm(w0))",
     "    w = (w / np.linalg.norm(w)) * float(np.linalg.norm(w0.astype(np.float64)))",
     ["H5-CLASSCOS"],
     "⚖⚖⚖⚖⚖ **rand 向量的缩放因子从 float32 口径改回 float64 口径**"
     "（⛔ 这正是 244.83 当场抓到的那个真 bug）⇒ ⇒ r₀ 与探针实际行为差 6.4e-10 "
     "⇒ ⇒ H5 的跨轮对账相对差 6.4e-10 > 1e-12 ⇒ ⇒ H5 必须红"),
    ("PM13", "impl", "data", "    g = np.random.default_rng(int(seed))\n    w = g.standard_normal(w0.shape)",
     "    g = np.random.default_rng(int(seed) + 1)\n    w = g.standard_normal(w0.shape)",
     ["H5-CLASSCOS"],
     "⚖⚖⚖ **rand 臂的种子被 +1**（探针写死 0 ⇒ 实际用的应该是 0）"
     "⇒ ⇒ r₀ 换了一把 ⇒ ⇒ H5 的跨轮对账必须红"),

    # ---------------- 实现被改：身份 / 出处（data）----------------
    ("PM14", "impl", "data", '"train_seed": 42,', '"train_seed": 43,',
     ["H2-PROVENANCE"],
     "⚖⚖⚖ **训练种子被改成 43** ⇒ ⇒ 6 把 sidecar 的 seed=42 与之不符 "
     "⇒ ⇒ H2 必须红"),
    ("PM15", "impl", "data", '"dose_w": "w_p2a",', '"dose_w": "w_old",',
     ["H1-IDENT"],
     "⚖⚖⚖ **「剂量批用的那把 w」被换成 w_old** ⇒ ⇒ class_gap=319.89 ≠ 113.474 "
     "⇒ ⇒ H1 必须红 ⇒ ⇒ 证明「身份链」被守住了"),
    ("PM16", "impl", "data", '"layer": 20,', '"layer": 19,',
     ["H2-PROVENANCE"],
     "⚖⚖⚖ **注入层被改成 19** ⇒ ⇒ sidecar layer=20 与之不符 ⇒ ⇒ H2 必须红"),

    # ---------------- 实现被改：H6′ 的打印精度口径（data）----------------
    ("PM17", "impl", "data", '"sd_print_decimals": 6,', '"sd_print_decimals": 12,',
     ["H6-CROSSROUND"],
     "⚖⚖⚖⚖⚖ **账本那个参考 sd 的「打印小数位」被改成 12** ⇒ ⇒ 容差由 5e-7 收紧到 5e-13 "
     "⇒ ⇒ 实测绝对差 4.56e-7 **超限** ⇒ ⇒ 且「印到 12 位小数逐位相同」那条**也不再成立** "
     "⇒ ⇒ H6 必须红 ⇒ ⇒ 证明 H6′ **不是恒绿**"),

    # ---------------- 数据被改（data）----------------
    ("PD1", "data", "data", None, None,
     ["H1-IDENT"],
     "⚖⚖⚖ **w_p2a.npy 的副本被篡改一个字节** ⇒ ⇒ 实测 md5 与账本登记不符 "
     "⇒ ⇒ H1 的 md5 对账必须红 ⇒ ⇒ 证明「产物 md5 对账」不是恒绿的"),
    ("PD2", "data", "data", None, None,
     ["H2-PROVENANCE"],
     "⚖⚖⚖ **w_real 的 sidecar 副本的 seed 被改成 7** ⇒ ⇒ 6 把种子不再一致 "
     "⇒ ⇒ H2 必须红"),
]

# ⚖⚖⚖⚖⚖ **判决形态的期望**（⛔ 早先的变异台**只断言「哪些判据变红」**，⛔ **不看判决形态**
#   ⇒ ⇒ 那个「H12 红 ⇒ 只能是 E-C」的承诺（预登记 §3.1）**没有任何变异体在守**
#   ⇒ ⇒ 被检实现把 H12 红一律判成 FAIL 也**照样全绿过**（⇒ ⇒ 死分支不被抓）
#   ⇒ ⇒ 现在把**判决形态**也纳入断言：PM6 逼出 **E-C**、PM15/PD1 逼出 **FAIL**）
EXPECT_VERDICT = {
    "PM6":  "E-C",    # H12（判别力）红 ⇒ ⇒ 形态只能是 E-C（「判别力不足 ⇒ 未量到」）
    "PM15": "FAIL",   # H1（身份）红 ⇒ ⇒ 前提被推翻 ⇒ ⇒ 形态 FAIL（⛔ 不是 E-C、不是「没量到」）
    "PD1":  "FAIL",   # 同上（**从数据侧**篡改 ⇒ 身份对账红 ⇒ 形态 FAIL）
}


def _run(cmd, env=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    p = subprocess.run(cmd, capture_output=True, text=True, env=e)
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
    # 训练脚本（只读，用于 H2 的跨来源那一半）
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
        tmp0 = tempfile.mkdtemp(prefix="mut84_pos_", dir="/dev/shm")
        bpc, err = _bpath_copy(tmp0)
        if bpc is None:
            print("PRECOND_FAIL: %s" % err)
            return 2
        rc, out, err = _run([PY, os.path.join(HERE, TARGET), "--data",
                             "--bpath", bpc, "--ledger", LEDGER])
        if rc != 0 or "DATA_RC=0" not in out:
            print("⛔ 阳性对照（--data）没过 ⇒ 中止")
            print(out[-3000:])
            print(err[-3000:])
            return 4
        print("[阳性对照] --data 全绿 ✅")
    if tmp0 is not None:
        shutil.rmtree(tmp0, ignore_errors=True)

    caught, missed, invalid, crashed = [], [], [], []
    for mid, cat, mode, pat, rep, expect, note in MUTATIONS:
        if self_only and mode != "self":
            continue
        tmp = tempfile.mkdtemp(prefix="mut84_%s_" % mid, dir="/dev/shm")
        try:
            tgt = os.path.join(tmp, TARGET)
            shutil.copy2(os.path.join(HERE, TARGET), tgt)
            bpc = None
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
            # ⚖⚠ **凡是走数据路径的变异都要一份 bpath 副本**
            #   （⚠ 「改实现」那类变异**也要**：它们跑的是真数据路径 ⇒ ⇒ 必须指到一个可读的 bpath；
            #    ⛔ 但**副本** ⇒ ⇒ 任何情况下都不碰真 bpath）
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
                    #   `.npy` 的头部占前 128 字节（magic + header + 64 字节对齐填充）
                    #   ⇒ ⇒ 改头部会让 `np.load` 直接抛 ValueError ⇒ ⇒ 那是**崩**，
                    #   ⛔ **崩 ≠ 抓到** ⇒ ⇒ 改第 200 字节（落在 float32 数据区 128..8320 内）
                    assert len(b) >= 8320, "⛔ w_p2a.npy 比预期短 ⇒ 偏移量要重算"
                    assert 128 < 200 < len(b), "⛔ 偏移 200 落在文件头或越界 ⇒ 重算"
                    b[200] = (b[200] + 1) % 256
                    open(p, "wb").write(bytes(b))
                elif mid == "PD2":
                    p = os.path.join(bpc, "w_real.npy.json")
                    t = open(p, encoding="utf-8").read().replace('"seed": 42', '"seed": 7', 1)
                    open(p, "w", encoding="utf-8").write(t)

            cmd = [PY, tgt]
            env = {}
            if mode == "self":
                cmd.append("--selftest")
            else:
                cmd += ["--data", "--bpath", bpc, "--ledger", LEDGER]
            rc, out, err = _run(cmd, env)
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
                print("[没抓到] %s  期望红 %s ｜ 实得红 %s%s"
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
