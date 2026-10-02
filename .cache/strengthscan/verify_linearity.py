#!/usr/bin/env python3
"""独立复算强度扫描的线性度结论（不 import worker 的任何代码）。

worker 声称：strength ≤ 0.1 时 ‖h+v‖ 偏离一阶线性 < 1%，strength=0.2
时约 2%，且偏离量与解析二阶项 ½(s·rms/‖h‖)² 吻合。

这条如果成立，含义很实在：现有的 steering 产物全都测在 strength=0.2，
也就是**刚刚开始进入非线性**的位置，它们的"强度"还能按线性读。

推导（一阶 + 二阶）：
  ‖h + a v‖ = ‖h‖·sqrt(1 + 2a·c + a²)  其中 a = s·rms/‖h‖, c = cos(h,v)
  一阶：  ‖h‖(1 + a·c)
  二阶份额 ≈ ½a²(1 − c²)
所以偏离百分比 ≈ ½·(s·rms/‖h‖)²·(1 − c²)。

注意 worker 用的是 ½a²（漏了 (1−c²)），而 c 通常远离 0，所以两者
差别不小。这里两边都算，看哪个对得上实测。
"""
import sys

import numpy as np

sys.path.insert(0, "/Users/zhourui/code/steer3d")
from backend.core.replay_runner import NpzReplayRunner  # noqa: E402
from backend.core.steering import get_registry  # noqa: E402

LAYERS = [12, 14, 20, 27]
STRENGTHS = [0.05, 0.1, 0.2, 0.5]
N_REC = 6
N_STEPS = 12


def main():
    runner = NpzReplayRunner()
    reg = get_registry()
    # 六个方向里有两对是精确取反，投影长度与方向无关；取一个代表即可，
    # 再用第二个非共线方向确认结论不是某一个方向的巧合。
    DIRS = ["caution", "confidence_up", "creativity", "reasoning_deep"]

    print(f"{'dir':16s}{'L':>4s}{'s':>7s}{'hn':>10s}"
          f"{'dev%':>9s}{'0.5a^2%':>9s}{'0.5a^2(1-c^2)%':>14s}{'winner':>10s}")
    rows = []
    for dname in DIRS:
        for L in LAYERS:
            rms = float(reg.layer_rms(L))
            for s in STRENGTHS:
                devs, q1, q2 = [], [], []
                for r in runner.records[:N_REC]:
                    z = np.load(r["npz"], mmap_mode="r")
                    T = z["hidden_states"].shape[0]
                    idx = np.linspace(int(T * 0.35), T - 1, N_STEPS).round().astype(int)
                    H = np.asarray(z["hidden_states"][idx, L, :], dtype=np.float64)
                    u = np.asarray(reg._vectors[dname], dtype=np.float64)
                    un = u / np.linalg.norm(u)
                    hn = np.linalg.norm(H, axis=1)                    # (n,)
                    c = (H @ un) / hn                                 # cos(h, v)
                    a = s * rms / hn                                 # 注入的相对幅度
                    # 注意加进去的必须是**绝对量** s·rms·u，不是相对量 a·u。
                    # 第一版这里写成了 a，两者在 s·rms ≈ ‖h‖ 时才碰巧接近，
                    # 于是实测偏离比解析值小了一个 ‖h‖ 倍（0.58% vs 14%）。
                    inj = np.full(len(H), s * rms)                    # (n,)
                    actual = np.linalg.norm(H + inj[:, None] * un[None, :], axis=1)
                    lin = hn * (1 + a * c)
                    dev = (actual / lin - 1.0) * 100.0
                    devs.append(dev)
                    q1.append(0.5 * a ** 2 * 100.0)
                    q2.append(0.5 * (a ** 2) * (1 - c ** 2) * 100.0)
                dev, m1, m2 = np.concatenate(devs), np.concatenate(q1), np.concatenate(q2)
                w = "0.5a^2(1-c^2)" if abs(dev.mean() - m2.mean()) < abs(dev.mean() - m1.mean()) else "0.5a^2"
                rows.append((dname, L, s, hn.mean(), dev.mean(), m1.mean(), m2.mean(), w))
                print(f"{dname:16s}{L:4d}{s:7.2f}{hn.mean():10.2f}"
                      f"{dev.mean():9.3f}{m1.mean():9.3f}{m2.mean():14.3f}{w:>14s}")

    print()
    print("=== 阈值：偏离 >1% 的最小 strength（逐方向逐层取最大）===")
    for dname in DIRS:
        worst = max(r[4] for r in rows if r[0] == dname and r[3] > 100)
        first = min((r[2] for r in rows if r[0] == dname and r[4] > 1.0), default=None)
        print(f"  {dname:18s} 最大偏离 {worst:6.2f}%  首个 >1% 的 strength: {first}")

    print()
    print("=== worker 声称 vs 本次实测（strength=0.2）===")
    for dname in DIRS:
        got = [r for r in rows if r[0] == dname and r[2] == 0.2]
        print(f"  {dname:18s} " + "  ".join(f"L{r[1]}:{r[4]:.2f}%" for r in got))


if __name__ == "__main__":
    main()
