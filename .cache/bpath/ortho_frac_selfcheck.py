"""修订 25 · 占比扫描的**方法自检**：扫描脚本能不能复现探针量到的数？

## 为什么需要它

M1/M2 要拿 `ortho_frac_scan.py` 算出的 58 条轨迹占比，
去比 `p01_think` 的 **0.1577**（那个数是 `orthogonality_probe.py` 量的）。
⚠ 但这是**两套独立代码**算的同一个量。
「读代码看着定义一样」不是证据 —— 必须实跑比对。

本脚本对 `p00_think` / `p01_think` 跑**与扫描脚本逐字相同**的取数路径，
再和缓存产物 `orthogonality.json` 里的逐位点 `w_dot_hhat` 重新聚合，
断言两边的 (n_hi, n_sites) **完全相等**。

- 相等 ⇒ 58 条的占比与 p01 的参考值**同口径**，M1/M2 的比较成立。
- 不等 ⇒ M1/M2 **不得出结论**（比较的是两个不同的量）。

## 只读

不改任何产物；只打印 + 断言。纯静态，不跑模型、不用 GPU。
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys

import numpy as np

MK = {13824, 14190, 6771, 10061, 7196, 88190, 80022}
NPZ = 19

# 探针实测（.cache/mutbak/orthogonality.json，逐位点重聚合得到）
REF = {("aime__aime25__p00__think", "think"): (3, 33),
       ("aime__aime25__p01__think", "think"): (21, 133)}


def scan_like(path, tid):
    """与 ortho_frac_scan.py **逐字相同**的取数路径（改一处即失效）。"""
    j = json.load(open(path, encoding="utf-8"))
    ts = [i for i, t in enumerate(j.get("tokens") or [])
          if t.get("token_id") in MK]
    z = np.load(path[:-5] + ".npz")
    hs = np.asarray(z["hidden_states"])   # 取一次，之后在 numpy 侧切片
    z.close()
    vals = []
    for i in ts:
        h = hs[i - 1, NPZ, :].astype(np.float64)
        vals.append(float(W @ (h / np.linalg.norm(h))))
    del hs
    return ts, vals


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/home/zhourui/steer3d_bpath")
    ap.add_argument("--ref", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "mutbak",
        "orthogonality.json"))
    a = ap.parse_args()

    global W
    W = np.load(os.path.join(a.root, "w_L19_m0.npy")).astype(np.float32)
    W = W / (float(np.linalg.norm(W)) + 1e-12)

    # 探针侧的参考值：从缓存产物**重新聚合**，不写死数字
    ref_rows = json.load(open(a.ref, encoding="utf-8"))["rows"]
    ref = collections.defaultdict(list)
    for r in ref_rows:
        ref[(r["traj"], r["mode"])].append(r["w_dot_hhat"])
    ref_agg = {k: (sum(1 for v in vs if v > 0.1), len(vs)) for k, vs in ref.items()}

    print(f"{'轨迹':<32}{'扫描路径':>12}{'探针路径':>12}   一致?")
    ok = True
    for (tid, mode), expect in sorted(ref_agg.items()):
        if mode != "think" or tid.endswith("no_think"):
            continue
        path = os.path.join(a.root, "gen_b2/aime", f"{tid}.json")
        ts, vals = scan_like(path, tid)
        got = (sum(1 for v in vals if v > 0.1), len(vals))
        same = got == expect
        ok &= same
        print(f"{tid:<32}{str(got):>12}{str(expect):>12}   {'一致' if same else '**不一致**'}")
        if not same:
            print(f"   扫描取到的位点数 {len(ts)}，探针聚合 {expect[1]}")

    # 硬编码的 REF 只作为「预登记里写的数」的对照，不作判定依据
    for k, v in REF.items():
        print(f"[预登记写的数] {k[0]:<28} {v[0]}/{v[1]} = {v[0]/v[1]:.6f}"
              f"  （探针重聚合 {ref_agg.get(k)}）")

    if not ok:
        print("\n**方法不同口径** ⇒ M1/M2 不得出结论", file=sys.stderr)
        return 1
    print("\n两套代码同口径 ⇒ M1/M2 的比较（58 条 vs p01）成立")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())