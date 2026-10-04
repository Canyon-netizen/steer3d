# -*- coding: utf-8 -*-
"""随机同范数方向对照臂的**纯 CPU 预检**（不需要 GPU、不需要模型权重）。

## 它证明什么

§4.13 记下一个硬缺口：32k 批次那 92 个 run **没有随机同范数方向对照臂**，
所以「这条轴之所以有效是因为它编码了『推高自信』，而不是因为
『在第 20 层往残差流里推任何同范数向量都会这样』」这句话至今没被排除。

我一直把它当成「需要另外造一套装置」。**读完源码之后发现不是**：

    backend/core/steering.py  load()
        v = np.load(npy)...;  self._vectors[name] = v / (‖v‖ + 1e-8)
        ⇒ **任何**从磁盘载入的向量都被归一化到单位范数
    backend/core/steering.py  scaled(name, strength, layer)
        return v * (strength * layer_rms(layer)
        ⇒ 强度是「该层残差流 RMS 范数的倍数」，不是原始尺度

⇒ 所以**同范数是结构性保证的**，不是要记得做的事：
放一个标准正态随机向量进向量目录，它会被 `load()` 归一化到与 6 个命名方向
**完全相同**的范数 1.0，再乘上**同一个** `0.2 × layer_rms(20)`。
⇒ 随机臂不需要改注入机制的任何一行代码。

## 它同时证明一个会「静默不跑」的坑

`load()` 的第一个循环遍历的是 **`steering_vectors.json` 的条目**；
那段「没有 JSON 就捡散落的 .npy」的兜底逻辑只在 **`found == 0`** 时才跑。

⇒ 已经加载了 6 个命名向量之后，**单独丢一个 `rand_a.npy` 而不写进 JSON，
  它永远不会被加载** ⇒ `registry.scaled('rand_a', ...)` 返回 `None`
  ⇒ `run_32k_study.py` 打印一行 `!! no vector for rand_a @ L20` 然后
  **`continue`** ⇒ 整次 run 正常结束、对照臂一次都没跑。

⇒ 这是本项目最危险的一类失败：**装置自己报成功，而它测的东西从没发生。**
⇒ 所以本预检把「这些向量确实会被加载」做成**可执行断言**，
  而不是留成一段说明。

## 用法

    python3 .cache/xcheck/verify_random_arm_preflight.py

## 它**不**证明什么

它只证明「对照臂在装置层面是同范数的、且会被真的跑到」。
它**不能**替代真跑：没有 GPU 与 Qwen3-1.7B 权重时，
`has_rms(20)` 只是从 `layer_profiles.json` 读来的数，
而那份 profile 本身是另一次实测的产物。
"""
import json
import os
import shutil
import sys
import tempfile

import numpy as np

ROOT = "/Users/zhourui/code/steer3d"
sys.path.insert(0, os.path.join(ROOT, "backend"))
from core.steering import SteeringRegistry   # noqa: E402

VEC_DIR = os.path.join(ROOT, "backend/examples/output/steering_vectors")
LAYER = 20
STRENGTH = 0.2
D_MODEL = 2048          # 6 个命名向量都是 2048 维（实测）
N_RANDOM = 3            # 预检用 3 个；真跑建议 5–16 个
SEEDS = (11, 22, 33)

results = []


def rec(name, ok, detail):
    results.append((name, ok, detail))
    print("%s %s\n     %s" % ("[PASS]" if ok else "[FAIL]", name, detail))


def main():
    rng = np.random.default_rng(20261004)
    reg = SteeringRegistry(VEC_DIR)
    ok = reg.load()
    named = [n for n in reg.names]
    rec("P0 命名方向能从磁盘载入", ok and len(named) >= 6,
        "载入 %d 个：%s" % (len(named), "、".join(sorted(named))))

    # ---- P1：载入后每个方向都是单位范数 --------------------------------
    norms = {n: float(np.linalg.norm(reg._vectors[n])) for n in named}
    off = {n: v for n, v in norms.items() if abs(v - 1.0) > 1e-5}
    rec("P1 载入的每个方向范数都是 1.0（`load()` 归一化的效果）",
        not off, "实测 %s%s" % (
            {n: round(v, 6) for n, v in sorted(norms.items())},
            "" if not off else "　⚠ 偏离 1.0 的：%s" % off))

    # ---- P2：第 20 层的 RMS 标定必须在位 --------------------------------
    n_cal = reg.load_layer_scales()
    rec("P2 第 %d 层的 RMS 标定在位（否则 0.2 会被静默当成 1.0 倍）" % LAYER,
        reg.has_rms(LAYER),
        "标定了 %d 层；L%d 的 mean_norm = %s"
        % (n_cal, LAYER, reg._rms.get(LAYER, "无 —— ⚠ strength 会退回 1.0 倍")))

    # ---- P3：随机方向放进「临时副本」后确实会被加载 ---------------------
    tmp = tempfile.mkdtemp(prefix="randarm_")
    try:
        tdir = os.path.join(tmp, "steering_vectors")
        shutil.copytree(VEC_DIR, tdir)
        # ⚠⚠ 必须把 layer_profiles.json 也搬过来。
        #   `load_layer_scales()` 在没给路径时找的是
        #   `self.vector_dir.parent / "layer_profiles.json"` —— 也就是 tmp 根目录。
        #   不搬 ⇒ 它返回 0 ⇒ `layer_rms(20)` 退回 **1.0** ⇒
        #   `scaled(v, 0.2, 20)` 的范数变成 0.2 而不是 173.15。
        #   ⇒ P4 会拿 0.2 和 0.2 比，**照样绿，而它验的是一个退化的装置**。
        #   这是本项目最熟的一类假绿：检查器自己没坏，它只是在一个假世界上运行。
        prof_src = os.path.join(ROOT, "backend/examples/output/layer_profiles.json")
        if os.path.exists(prof_src):
            shutil.copy(prof_src, os.path.join(tmp, "layer_profiles.json"))
        meta_path = os.path.join(tdir, "steering_vectors.json")
        meta = json.load(open(meta_path, encoding="utf-8"))

        # 陷阱复现：**只放 .npy、不写 JSON**
        stray = rng.standard_normal(D_MODEL).astype(np.float32)
        np.save(os.path.join(tdir, "rand_stray.npy"), stray)
        reg_stray = SteeringRegistry(tdir)
        reg_stray.load()
        stray_loaded = "rand_stray" in reg_stray.names
        rec("P3a 陷阱复现：只丢 .npy、**不写进 JSON** ⇒ 该方向不会被加载",
            (not stray_loaded) and len(reg_stray.names) == len(named),
            "放下 rand_stray.npy 后仍只载入 %d 个（%s）"
            % (len(reg_stray.names), "它确实没进来" if not stray_loaded
               else "⚠ 它进来了 ⇒ 本条的结论要重写"))

        # 正规做法：写进 JSON
        for s in SEEDS:
            v = rng.standard_normal(D_MODEL).astype(np.float32)
            name = "rand_s%d" % s
            np.save(os.path.join(tdir, name + ".npy"), v)
            meta[name] = {
                "description": "random same-norm control arm, seed=%d" % s,
                "layer": LAYER, "d_model": D_MODEL, "method": "standard_normal",
                "seed": s, "norm": 1.0,
            }
        json.dump(meta, open(meta_path, "w", encoding="utf-8"))

        reg2 = SteeringRegistry(tdir)
        reg2.load()
        n_cal2 = reg2.load_layer_scales()
        want = ["rand_s%d" % s for s in SEEDS]
        got = [n for n in want if n in reg2.names]
        rec("P3b 写进 `steering_vectors.json` 之后，这 %d 个随机方向全部被加载" % N_RANDOM,
            len(got) == N_RANDOM,
            "命名 %d + 随机 %d = %d 个；随机方向：%s"
            % (len(reg2.names) - len(got), len(got), len(reg2.names), "、".join(got)))

        # P3c：临时副本里的 RMS 标定必须**同样**在位，否则下面 P4 验的是退化装置
        rec("P3c 临时副本里第 %d 层的 RMS 标定也在位（P4 的前提）" % LAYER,
            reg2.has_rms(LAYER),
            "标定了 %d 层；L%d mean_norm = %s（若为 1.0 就是退回了默认值，"
            "P4 会变成拿 0.2 比 0.2 的假绿）"
            % (n_cal2, LAYER, reg2._rms.get(LAYER, "无")))

        # ---- P4：同范数 —— 这是整个对照臂成立的前提 -------------------
        cells = {}
        for n in list(named) + got:
            cells[n] = reg2.scaled(n, STRENGTH, LAYER)
        nn = {n: float(np.linalg.norm(v)) for n, v in cells.items() if v is not None}
        rand_ns = [nn[n] for n in got]
        named_ns = [nn[n] for n in named]
        max_dev = (max(abs(x - named_ns[0]) for x in rand_ns + named_ns)
                   if rand_ns and named_ns else float("inf"))
        rec("P4 **同范数**：随机方向与命名方向经 `scaled(%s, %s, %d)` 之后范数相同"
            % (STRENGTH, STRENGTH, LAYER),
            max_dev <= 1e-3,
            "命名 %s ｜ 随机 %s（单位：残差流 ‖h‖ 的倍数，层 RMS=%.2f）　最大偏差 %.2e"
            % ([round(x, 4) for x in sorted(named_ns)],
               [round(x, 4) for x in sorted(rand_ns)],
               float(reg2._rms.get(LAYER, 0.0)), max_dev))

        # ---- P5：维度必须与模型一致，否则 hook 会炸或错位 ---------------
        dims = {n: int(cells[n].size) for n in cells if cells[n] is not None}
        bad = {n: d for n, d in dims.items() if d != D_MODEL}
        rec("P5 所有方向维度都是 %d（0.6B 是 1024，**混用会错位**）" % D_MODEL,
            not bad, "实测维度 %s" % sorted(set(dims.values())))

        # ---- P6：注入向量与命名方向不共线（否则就不是「随机」） ---------
        import itertools
        ref = cells[named[0]]
        dots = []
        for r in got:
            c = np.dot(cells[r], ref) / (np.linalg.norm(cells[r]) * np.linalg.norm(ref))
            dots.append(abs(float(c)))
        rec("P6 随机方向与命名方向**近似正交**（|cos| 远小于 1 ⇒ 它确实随机）",
            max(dots) < 0.1,
            "与 %s 的 |cos| = %s" % (named[0], [round(d, 5) for d in dots]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    npass = sum(1 for _, k, _ in results if k)
    print("\n=== %d/%d 条通过 ===" % (npass, len(results)))
    print("⚠ 本预检只覆盖**装置层面**。真跑仍需 CUDA + transformers + Qwen3-1.7B 权重。")
    for n, k, _ in results:
        if not k:
            print("[FAIL] " + n)
    return 0 if npass == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
