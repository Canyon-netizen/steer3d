#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""mut_dose_equivalence_audit.py —— **剂量等值性核查**的变异台（244.83）。

⚖⚖⚖⚖⚖ **这个台架要回答的问题**
   「`dose_equivalence_audit.py` 的每条判据**是不是恒绿的**？」
   ⇒ ⇒ 必须证明它们**能红**：
     · **实现被改**（容差 / 公式 / 字段划分 / 读数系数 / 位点种子 / 允许差异集 / …）
       ⇒ ⇒ 对应判据必须由 PASS 变 FAIL；
     · **数据被改**（日志副本 / 探针副本 / 向量副本）⇒ ⇒ 对应判据必须红。

⚖⚖⚖⚖⚖ **纪律（从 244.66–244.82 的台架继承，一条都不许放松）**

   ① 每条变异只改**一处**（⛔ 改多处 ⇒ 抓到了也不知道是哪一处抓的）
   ② 每条变异必须**恰好命中 1 处**（⛔ 命中 0 ⇒ 这条变异**无效** ⇒ 必须报出来；
      ⛔ **等价变异（什么都没变）记「无效」，⛔ 不是「存活」**）
   ③ ⛔ **「崩」≠「抓到」** ⇒ 崩了单独报 ⇒ 崩的条数必须压到 **0**
      （⚠ 例外：**G0-3 硬停**是**被闸门拦下**，⛔ **不是**崩 ⇒ 单独归类为「硬停抓到」）
   ④ **阳性对照先过**：不改任何东西时，目标必须**全绿** ⇒ ⇒
      否则「全红」什么也证明不了 ⇒ ⇒ 直接退出
   ⑤ 期望的「哪条该红」是**手写**的 ⇒ ⇒ **不许从被检对象派生**
   ⑥ ⛔ 本台架**不改**目标实现、⛔ 不改预登记、⛔ 不改原始日志
      ⇒ ⇒ 数据变异只发生在**临时目录里的副本**上
   ⑦ ⛔ 缺前置/远端产物 ⇒ 报 **`PRECOND_FAIL`**（⛔ 这样回归器才判「跑不动」，
      ⛔ **不是**「本轮引入的红」⇒ ⇒ 冤枉）
   ⑧ ⚖ **「把容差改紧 ⇒ 判据变红」也算一种合法变异**
      ⇒ ⇒ 它证明的是「这条判据**不是恒绿**」⇒ ⇒ 与「放宽容差」方向相反，但同样必要。
"""

import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BPATH = os.environ.get("R244_BPATH", "/home/zhourui/steer3d_bpath")
TARGET = "dose_equivalence_audit.py"
W_LOG = os.path.join(BPATH, "r244_warm_fd_w.log")
R_LOG = os.path.join(BPATH, "r244_warm_fd_rand.log")
RUNNER = os.path.join(BPATH, "r244_warm_sweep.sh")
PROBE = os.path.join(BPATH, "r241_probe.py")
W_NPY = os.path.join(BPATH, "w_p2a.npy")
CELLS = os.path.join(BPATH, "warm_cells_fixed_dose.tsv")

CRASH_RE = re.compile(r"^(Traceback \(most recent call last\)|\w*(?:Error|Exception)\b)", re.M)
HARDSTOP_RE = re.compile(r"^G0_3_HARDSTOP:", re.M)

# ⚖ (编号, 类别, 模式, 落点串, 替换串, 期望红的判据 id（列表）, 说明)
#    模式 "self" = 跑 `--selftest`（⛔ 不依赖远端产物）；"data" = 跑真数据路径
#    类别 "impl" = 改**实现源码副本**；"data" = 改**产物副本**
MUTATIONS = [
    # ---------------- 实现被改：口径常量 / 公式 / 规则 ----------------
    ("PM1", "impl", "self", '"norm_rel_tol": 1e-6,', '"norm_rel_tol": 1e-18,',
     ["DQ-NORM"],
     "⚖⚖⚖ **注入前范数容差被改紧 8 个量级**（1e-6 → 1e-18）⇒ ⇒ 实测相对差 1.11e-16 > 1e-18 "
     "⇒ ⇒ 必须红 ⇒ ⇒ 证明 DQ-NORM **不是恒绿**"),
    ("PM2", "impl", "self", '"bf16_rel_bound": 1e-2,', '"bf16_rel_bound": 1e-8,',
     ["DQ-NORM16"],
     "⚖⚖⚖ **注入后（bf16）容差被改紧 6 个量级**（1e-2 → 1e-8）⇒ ⇒ 实测相对差 5.17e-05 > 1e-8 "
     "⇒ ⇒ 必须红 ⇒ ⇒ 证明 DQ-NORM16 **不是恒绿**"),
    ("PM3", "impl", "self",
     "    return float(alpha_max) * float(vnorm) * math.sqrt(float(k))",
     "    return float(alpha_max) * float(vnorm) * float(k)",
     ["DQ-INJECT"],
     "⚖⚖⚖ **注入场 L2 范数漏掉 √k**（√k ⇒ k）⇒ ⇒ 「公式路径」与「直接路径」必然对不上 "
     "⇒ ⇒ 必须红"),
    ("PM4", "impl", "self",
     '    "n_gen", "n_steps", "pos_frac", "rep_n_hi", "rep_n_lo", "t", "tid",',
     '    "n_gen", "n_steps", "rep_n_hi", "rep_n_lo", "t", "tid",',
     ["DQ-FIELDS-CLS"],
     "⚖⚖⚖ **结构字段集里拿掉 pos_frac** ⇒ ⇒ 该字段落进「第三处」（既不是结构、也不是读数、"
     "也不是退化）⇒ ⇒ 必须红 ⇒ ⇒ 证明「不许藏」这条守得住"),
    ("PM5", "impl", "self", "READOUT_COEF = (0.5, 1.0)", "READOUT_COEF = (0.25, 2.0)",
     ["DQ-GAP"],
     "⚖⚖⚖ **判决读数 α 的系数被改**（0.5/1.0 ⇒ 0.25/2.0）⇒ ⇒ 与探针源码里那行对不上 "
     "⇒ ⇒ 必须红"),
    ("PM6", "impl", "data", 'allowed = ("--gpu-uuid", "--arm")', 'allowed = ()',
     ["DQ-CMD"],
     "⚖⚖⚖ **命令行「允许不同的集合」被清空** ⇒ ⇒ 连 gpu-uuid 都算成不同 ⇒ ⇒ 必须红 "
     "⇒ ⇒ 证明 DQ-CMD 真的在比命令行（⚠ **必须真数据模式**：合成夹具两臂 GPU 相同 ⇒ "
     "清空允许集**看不出**差别）"),
    ("PM7", "impl", "self", '"k_seed": 0,', '"k_seed": 1,',
     ["DQ-KPOS"],
     "⚖⚖⚖ **位点种子被改**（0 → 1）⇒ ⇒ 与探针源码 `seed=0` 对不上 ⇒ ⇒ 必须红"),
    ("PM8", "impl", "self",
     "    y = [float(start) + step * i for i in range(num)]",
     "    y = [0.0 + step * i for i in range(num)]",
     ["DQ-ALPHA"],
     "⚖⚖⚖ **α 网格的起点被改**（`-alpha_max` → 0）⇒ ⇒ 与探针源码的构造式对不上 ⇒ ⇒ 必须红"),
    ("PM9", "impl", "self", '"model_dtype": "bfloat16",', '"model_dtype": "float32",',
     ["DQ-DTYPE"],
     "⚖⚖⚖ **登记的模型 dtype 被改**（bfloat16 → float32）⇒ ⇒ 与源码读出的对不上 ⇒ ⇒ 必须红"),
    ("PM10", "impl", "self",
     "        ref.append(float(np.dot(w64.ravel(), rr.ravel()) / w_norm))",
     "        ref.append(float(cos0))",
     ["DQ-COS"],
     "⚖⚖⚖ **余弦参考分布被换成常数** ⇒ ⇒ sd = 0 ⇒ 与理论值 1/√d 对不上 ⇒ ⇒ 必须红"),
    ("PM11", "impl", "self",
     '    ("④", "**未正交化**：`cos(w, rand) ≠ 0`（实测见下）⇒ rand 臂里含 w 成分的"\n'
     '          "**影响未量到**"),\n',
     "",
     ["DQ-REMIX"],
     "⚖⚖⚖ **残余混淆第 ④ 条被删掉** ⇒ ⇒ 必须红 ⇒ ⇒ 证明「残余混淆必须逐条在案」守得住"),
    ("PM12", "impl", "self",
     "    w = (w / np.linalg.norm(w)) * float(np.linalg.norm(w0))",
     "    w = w  # 缺陷：rand 臂不归一",
     ["DQ-NORM"],
     "⚖⚖⚖ **rand 臂不再归一到 ∥W_0∥** ⇒ ⇒ 注入前两臂范数不再相等 ⇒ ⇒ 必须红"),

    # ---------------- 数据被改（产物副本，真数据模式）----------------
    ("DM1", "data", "data", "__W_PATH_RAND__", "", ["DQ-CMD"],
     "⚖⚖⚖ **rand 臂的 `--w` 指向另一把向量** ⇒ ⇒ 两臂命令行出现第二处不同 ⇒ ⇒ 必须红"),
    ("DM2", "data", "data", "__NSITES_W__", "", ["DQ-NSITES"],
     "⚖⚖⚖ **w 臂日志副本里改掉一格的 inject_n_sites** ⇒ ⇒ 四源不再一致 ⇒ ⇒ 必须红"),
    ("DM3", "data", "data", "__PROBE_NO_LINSPACE__", "", ["DQ-SRC"],
     "⚖⚖⚖ **探针副本里去掉 `linspace` 那行** ⇒ ⇒ 源码七条事实缺一条 ⇒ ⇒ 必须红"),
    ("DM4", "data", "data", "__PROBE_F32__", "", ["DQ-DTYPE"],
     "⚖⚖⚖ **探针副本里 dtype 改成 float32** ⇒ ⇒ 与登记的 bfloat16 对不上 ⇒ ⇒ 必须红"),
    ("DM5", "data", "data", "__MOD_RAND__", "", ["DQ-COS"],
     "⚖⚖⚖ **rand 臂日志里探针印的 mod 改成 1.5** ⇒ ⇒ 与重算的 ∥W_rand‖ 跨来源对不上 ⇒ ⇒ 必须红"),
    ("DM6", "data", "data", "__VEC_SCALE__", "", ["DQ-COS", "DQ-ARTEFACT"],
     "⚖⚖⚖ **w 向量副本整体乘 1.5** ⇒ ⇒ 两臂**同时**放大 ⇒ ⇒ 剂量等值性本身**不受影响** "
     "（这是**该有的性质**）⇒ ⇒ 但探针日志印的 mod=1.0 与重算对不上 ⇒ ⇒ 跨来源检查必须红 "
     "⇒ ⇒ 证明「跨来源」那一半真的在起作用"),
]

# ⚖⚖⚖ 等价变异**为什么**在这批数据上不可见（⚖ 手写，⛔ 不从被检对象派生）
EQUIV_WHY = {
}


def run_target(script, mode, workdir, paths):
    """⚖ 跑一次目标实现 ⇒ 返回 `(rc, stdout+stderr)`。"""
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if mode == "self":
        cmd = [sys.executable, script, "--selftest"]
    else:
        cmd = [sys.executable, script,
               "--w-log", paths["w_log"], "--rand-log", paths["rand_log"],
               "--runner", paths["runner"], "--probe", paths["probe"],
               "--w-npy", paths["w_npy"], "--cells", paths["cells"]]
    try:
        r = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True,
                           timeout=1800, env=env)
        return r.returncode, (r.stdout + r.stderr)
    except subprocess.TimeoutExpired:
        return -9, "TIMEOUT"


def _red_ids(out):
    """⚖ 抠出 FAIL 的判据 id（⛔ 期望集是手写的，不许从被检对象派生）。"""
    return set(re.findall(r"^\[FAIL\] (\S+)", out, re.M))


def _my_numbers(out):
    """⚖ 抠出输出里所有 `= <数>` 的数 ⇒ 用来判「等价变异」。"""
    vals = []
    for ln in out.split("\n"):
        if ln.startswith("CROSS|"):
            vals.append(ln.strip())
            continue
        m = re.search(r"= ([-+0-9.eE]+)", ln)
        if m:
            vals.append(m.group(1))
    return vals


def _same_numbers(out, base_out):
    """⚖⚖ **等价变异的判别**：源码改了，但算出来的数**逐条相同** ⇒ ⇒ 记「无效」。"""
    a, b = _my_numbers(out), _my_numbers(base_out)
    return bool(a) and a == b


def _apply_data_mut(out, tag):
    """⚖ 对产物副本施加数据变异（⛔ 原件不动）。"""
    if tag == "__W_PATH_RAND__":
        p = out["rand_log"]
        t = io.open(p, encoding="utf-8", errors="replace").read()
        t = t.replace("W_PATH=%s/w_p2a.npy" % BPATH, "W_PATH=%s/w_other.npy" % BPATH)
        io.open(p, "w", encoding="utf-8", newline="").write(t)
    elif tag == "__NSITES_W__":
        p = out["w_log"]
        t = io.open(p, encoding="utf-8", errors="replace").read()
        t = t.replace("--inject-n-sites 75 ", "--inject-n-sites 76 ", 1)
        t = t.replace('"inject_n_sites": 75', '"inject_n_sites": 76', 1)
        io.open(p, "w", encoding="utf-8", newline="").write(t)
    elif tag == "__PROBE_NO_LINSPACE__":
        p = out["probe"]
        t = io.open(p, encoding="utf-8", errors="replace").read()
        t = t.replace("alphas = np.linspace(-a.alpha_max, a.alpha_max, a.n_steps)",
                      "alphas = np.arange(a.n_steps)")
        io.open(p, "w", encoding="utf-8", newline="").write(t)
    elif tag == "__PROBE_F32__":
        p = out["probe"]
        t = io.open(p, encoding="utf-8", errors="replace").read()
        t = t.replace("torch_dtype=torch.bfloat16", "torch_dtype=torch.float32")
        io.open(p, "w", encoding="utf-8", newline="").write(t)
    elif tag == "__MOD_RAND__":
        p = out["rand_log"]
        t = io.open(p, encoding="utf-8", errors="replace").read()
        t = t.replace("mod=1.0000", "mod=1.5000")
        io.open(p, "w", encoding="utf-8", newline="").write(t)
    elif tag == "__VEC_SCALE__":
        import numpy as np
        p = out["w_npy"]
        a = np.load(p).astype(np.float64) * 1.5
        # ⚠ 用文件句柄写：⛔ `np.save(path, ...)` 会**自动补 `.npy` 后缀** ⇒ ⇒ 原文件没被改
        with open(p, "wb") as fh:
            np.save(fh, a.astype(np.float32))
    else:
        raise SystemExit("⛔ 未知的数据变异：%s" % tag)


def main():
    work = tempfile.mkdtemp(prefix="_mut_de_")
    try:
        base_paths = {"w_log": W_LOG, "rand_log": R_LOG, "runner": RUNNER,
                      "probe": PROBE, "w_npy": W_NPY, "cells": CELLS}
        for k, p in base_paths.items():
            if not os.path.isfile(p):
                print("PRECOND_FAIL: 缺远端产物：%s ⇒ 这一轮**跑不动** ⇒ ⛔ **不是「判据红」**" % p)
                return 2
        with io.open(os.path.join(HERE, TARGET), encoding="utf-8") as fh:
            src_txt = fh.read()

        # ---- ④ 阳性对照：什么都没改 ⇒ 必须全绿（自检模式 + 真数据模式各一次）
        for mode, tag in (("self", "自检模式"), ("data", "真数据模式")):
            rc, out = run_target(os.path.join(HERE, TARGET), mode, work, base_paths)
            if rc != 0:
                print("⛔ **阳性对照没过**（未改任何东西时目标不是全绿，%s）⇒ ⇒ 台架自己瞎了 ⇒ 退出" % tag)
                print(out[-4000:])
                return 3
            print("阳性对照（%s）：过 ⇒ 阳性对照通过（台架能判红）" % tag)
        base_self = run_target(os.path.join(HERE, TARGET), "self", work, base_paths)[1]
        base_data = run_target(os.path.join(HERE, TARGET), "data", work, base_paths)[1]

        caught, invalid, crashed, equivalent, hardstop = [], [], [], [], []
        for mid, kind, mode, find, repl, expect_red, desc in MUTATIONS:
            if kind == "impl":
                n = src_txt.count(find)
                if n != 1:
                    invalid.append((mid, "落点命中 %d 处（期望 1）⇒ **落点无效**（台架瞎了）" % n))
                    continue
                script = os.path.join(work, "target_%s.py" % mid)
                with io.open(script, "w", encoding="utf-8", newline="") as fh:
                    fh.write(src_txt.replace(find, repl))
                paths = base_paths
            else:
                script = os.path.join(HERE, TARGET)
                d2 = tempfile.mkdtemp(prefix="_mut_de_d_", dir=work)
                paths = {"__dir__": d2}
                for k, src in base_paths.items():
                    dst = os.path.join(d2, k)
                    shutil.copyfile(src, dst)
                    paths[k] = dst
                _apply_data_mut(paths, find)

            rc, out = run_target(script, mode, work, paths)
            if rc == -9:
                crashed.append((mid, "超时"))
                continue
            red = _red_ids(out)
            hard = bool(HARDSTOP_RE.search(out))
            if hard:
                hardstop.append((mid, sorted(red)))
                print("[硬停抓到] %-4s ⇒ G0-3 自检闸把它拦下了（红的判据：%s）"
                      % (mid, ",".join(sorted(red))))
                continue
            if _looks_like_crash(out):
                crashed.append((mid, "崩了（⛔ 崩 ≠ 抓到）"))
                print("[崩] %-4s ⇒ 崩了（⛔ 崩 ≠ 抓到）")
                continue
            hit = [e for e in expect_red if e in red]
            if expect_red and rc != 0 and hit:
                caught.append((mid, hit, sorted(red)))
                print("[抓到] %-4s ⇒ 红：%s（同时红了：%s）" % (mid, ",".join(hit),
                                                               ",".join(sorted(red))))
            elif not expect_red and _same_numbers(out, base_data if mode == "data" else base_self):
                why = EQUIV_WHY.get(mid, "⚖ 源码改了但结果逐条相同 ⇒ 等价变异"
                                           "（**原因未登记** ⇒ 记进账本待查，⛔ 不许编理由）")
                equivalent.append((mid, why))
                print("[无效/等价] %-4s ⇒ 源码改了但**这批数据上结果逐条相同** ⇒ 记「无效」：%s"
                      % (mid, why))
            else:
                invalid.append((mid, "❌ 没抓到（rc=%s，红的判据：%s）⇒ **台架瞎了**" % (rc, sorted(red))))

        print("")
        print("变异台：抓到 %d / %d（无效 %d 条 ⇒ 记「无效」⇒ 不计入分母；"
              "其中等价变异 %d 条 ⇒ 有效分母 = %d）"
              % (len(caught) + len(hardstop), len(MUTATIONS),
                 len(invalid) + len(equivalent), len(equivalent),
                 len(caught) + len(hardstop) + len(equivalent)))
        for mid, why in invalid:
            print("  [无效] %-4s %s" % (mid, why))
        for mid, why in equivalent:
            print("  [无效/等价] %-4s %s" % (mid, why))
        print("崩的条数：%d（⛔ 必须是 0）" % len(crashed))
        for mid, why in crashed:
            print("  [崩] %-4s %s" % (mid, why))
        rc = 0 if (not invalid and not crashed
                   and len(caught) + len(hardstop) + len(equivalent) == len(MUTATIONS)) else 1
        print("MUT_RC=%d" % rc)
        return rc
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _looks_like_crash(out):
    return bool(CRASH_RE.search(out))


if __name__ == "__main__":
    sys.exit(main())
