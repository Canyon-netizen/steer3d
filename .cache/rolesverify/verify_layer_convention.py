#!/usr/bin/env python3
"""层口径守卫：把 §2.1 那处一个 block 的错位钉成可复跑的检查。

## 为什么要有这个

这处错位极其难被发现，因为它「看起来差不多」：

    相邻层的 contrast 方向  cos(L13, L14) = 0.9565

0.9565 读起来像是「同一件事的两种说法」，于是没人会去问标量。
而标量那边差 **1.1797 倍** —— 在标称 s=0.2 下真实相对幅度是 0.236，
几何代价比标称暗示的高 24%。

## 设计：不变�� vs 状态

* **不变量**（必须恒过，挂了就是有人改坏了）：
  I1 `hidden_states[:,27]` 与 `last_hidden` 逐位相同
  I2 范数在 L26→L27 突降（最终 RMSNorm 的签名）
  I3 磁盘上的 `confidence_up` 就是 L14 那一版的 diff-of-means
  I4 向量提取脚本读的确实是 `hs[:, layer, :]`
  这四条合起来唯一确定「下标 L = 第 L 个 block 的输出」。

* **状态**（只报，不过不挂）：
  S1 注入钩子是 pre 还是 post ⇒ 扰动 `hidden_states[:,L]` 还是 `[L−1]`
  S2 若不对齐，打出真实放大倍数
  理由：现在的不对齐是一个**待用户决定的待办**，不是 bug；
  但它必须每次跑都可见，否则就会被静默修掉或者被静默当成已修。

`python3 .cache/rolesverify/verify_layer_convention.py`
退出码 0 = 不变量全过（不管状态是否对齐）。
"""
import glob
import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path("/Users/zhourui/code/steer3d")
NPZ = sorted((ROOT / "datasets/aime_qwen3_1p7b_16k_fp16/aime").glob("*.npz"))
VEC = ROOT / "backend/examples/output/steering_vectors/confidence_up.npy"
EXTRACT = ROOT / "backend/examples/compute_steering_vectors.py"
INJECT = [
    ROOT / "backend/core/model_runner.py",
    ROOT / "backend/core/activation.py",
    ROOT / "backend/examples/run_intervention.py",
]
_ERR = dict(all="ignore")
D = 2048


def check(name, ok, detail):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return bool(ok)


def main():
    print("不变量（挂了就是有人改坏了）")
    inv = []

    d0 = np.load(NPZ[0])
    hs0, lh0 = d0["hidden_states"], d0["last_hidden"]
    with np.errstate(**_ERR):
        diff = float(np.abs(hs0[:, 27, :].astype(np.float64)
                            - lh0.astype(np.float64)).max())
        same = bool(np.array_equal(hs0[:, 27, :], lh0))
    inv.append(check("I1 hidden_states[:,27] == last_hidden 逐位相同",
                     diff == 0.0 and same, f"max|diff|={diff:g}  bitwise={same}"))

    with np.errstate(**_ERR):
        n = [float(np.linalg.norm(hs0[:, L, :].astype(np.float64), axis=1).mean())
             for L in (25, 26, 27)]
    ratio = n[2] / n[1]
    inv.append(check("I2 范数在 L26→L27 突降（最终 RMSNorm 签名）",
                     ratio < 0.2, f"L25={n[0]:.2f} L26={n[1]:.2f} L27={n[2]:.2f} "
                                 f"ratio={ratio:.4f}"))

    # I3：用熵 p30/p75 分组重算 diff_of_means，与磁盘向量比
    pos = np.zeros(D, np.float64)
    neg = np.zeros(D, np.float64)
    np_ = nn = 0
    for f in NPZ:
        z = np.load(f)
        side = json.loads(f.with_suffix(".json").read_text())
        ent = np.asarray([t["entropy"] for t in side["tokens"]], np.float64)
        lo, hi = np.percentile(ent, [30, 75])
        h = np.asarray(z["hidden_states"][:, 14, :], np.float64)
        pos += h[ent <= lo].sum(axis=0)
        np_ += int((ent <= lo).sum())
        neg += h[ent >= hi].sum(axis=0)
        nn += int((ent >= hi).sum())
    v = pos / np_ - neg / nn
    v = v / np.linalg.norm(v)
    stored = np.load(VEC).astype(np.float64).ravel()
    stored = stored / np.linalg.norm(stored)
    c14 = float(stored @ v)
    inv.append(check("I3 磁盘 confidence_up == L14 的 diff-of-means",
                     c14 > 0.99, f"cos={c14:.5f}  n_pos={np_} n_neg={nn}"))

    src = EXTRACT.read_text()
    m = re.search(r"hs\[:,\s*layer\s*,\s*:\]", src)
    inv.append(check("I4 向量提取读的是 hs[:, layer, :]", bool(m),
                     f"{EXTRACT.name} 命中 {bool(m)}"))

    print()
    print("状态（只报，不挂；不对齐是一个待用户决定的待办）")
    # 注意：**不能**用「文件里有没有 pre_hook」来判。
    # model_runner.py / activation.py 里还有 capture 用的 post_hook
    # （model_runner.py:304/378 是抓残差，不是注入），会把结论带偏。
    # 只认**真正把向量加到 x 上**的那个钩子：向前 14 行内必须出现对
    # inputs[0] / x 的向量加法。
    inj = []
    for p in INJECT:
        lines = p.read_text().splitlines()
        for i, ln in enumerate(lines):
            m = re.search(r"register_forward_(pre_)?hook", ln)
            if not m:
                continue
            ctx = "\n".join(lines[max(0, i - 14):i + 1])
            # 形如 `return (x + v,) + inputs[1:]` —— 元组里的逗号要允许
            adds = re.search(r"return\s+\(\s*[\w.]+\s*\+\s*[\w.]+\s*,?\s*\)", ctx) or \
                re.search(r"\(\s*inputs\[0\]\s*\+\s*[\w.]+\s*,?", ctx)
            if not adds:
                continue
            inj.append((p, i + 1, bool(m.group(1))))
    pre = sum(1 for _, _, is_pre in inj if is_pre)
    post = len(inj) - pre
    for p, ln, is_pre in inj:
        print(f"    注入钩子 {p.relative_to(ROOT)}:{ln}  "
              f"{'pre_hook（改 block 输入 ⇒ hidden_states[:,L-1]）' if is_pre else 'post_hook（改 block 输出 ⇒ hidden_states[:,L]）'}")
    if not inj:
        print("    [警告] 没有定位到任何注入钩子，状态判不出来")
    elif post and not pre:
        print("  S1 注入侧 = 提取侧（post_hook）→ 已对齐，标称 s 就是真实相对幅度")
    elif pre:
        print("  S1 注入侧 = pre_hook ⇒ 扰动 hidden_states[:,L-1]，而向量取自 [:,L]")
        # 量化放大倍数
        acc = {13: 0.0, 14: 0.0}
        cnt = {13: 0, 14: 0}
        with np.errstate(**_ERR):
            for f in NPZ:
                z = np.load(f)
                side = json.loads(f.with_suffix(".json").read_text())
                T = len(side["tokens"])
                for L in (13, 14):
                    h = np.asarray(z["hidden_states"][:, L, :], np.float64)
                    acc[L] += float(np.linalg.norm(h, axis=1).sum())
                    cnt[L] += T
        rms = {L: acc[L] / cnt[L] for L in (13, 14)}
        amp = rms[14] / rms[13]
        print(f"     mean‖h‖@L13={rms[13]:.3f}  @L14={rms[14]:.3f}  "
              f"放大倍数={amp:.4f}x")
        print(f"     ⇒ 标称 s 的真实相对幅度 = {amp:.4f}·s；"
              f"s=0.2 → {0.2*amp:.4f}，几何代价 ½({0.2*amp:.4f})²="
              f"{0.5*(0.2*amp)**2*100:.2f}%")

    ok = all(inv)
    print()
    print(f"RESULT {'PASS' if ok else 'FAIL'}  不变量 {sum(inv)}/{len(inv)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
