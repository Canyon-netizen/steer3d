#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 38 案例的读数拆成两套口径，因为样本里混了**两类不同的位置**。

## 触发

R-5 的 A 组跑出五桶，其中「其他」(+4.699) 是其余各组的 4 倍。
`group_recheck.py` 查出那 8 个位置写的是：

    ' But' ×1   'But' ×4   ' my' ×1   ' there' ×1

而 `CAUSAL_PREREG.md` §3.1 **明写**「`But` / `but` / `my` **不算** marker」——
它们比 marker 更常见，算进去会被普通连接词的概率上升顶账。
所以这 8 个位置**根本不是 marker 位置**，却混在样本里，
而且贡献了最大的 Δ（`' my'` 单点 **+18.38**）。

⚠ 更要紧的是：**绝对 Δlogprob 跨位置不可比**。
`logprob = logit − logsumexp`；一个基线本来就在 −20 的
「几乎不可能的集合」，被扰动后可以涨 +18，而一个基线 −0.3 的
集合涨不到 +1。⇒ 大 Δ 既可能来自「效应更强」，
也可能只来自「基线更低」。

## 本脚本算什么

同一份读数，两套口径并列，**不做取舍**：

- **口径 A（全样本 38）**：PREREG 取数时定的样本，原样。
- **口径 B（marker 位置 30）**：只留实际写的 token **落在 7 个
  marker id 里**的位置。

⚠ 口径 B 是**事后限制**，不是新的主结果 —— 只能在口径 A 之后
并列呈现，不能拿它替换 A，也不能用它去重判任何一条判决。
它的用途只有一个：**说明口径 A 的均值被哪一类位置拉动。**
"""
from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, ".cache", "mutbak", "causal_rel44.json")
NOISE = 4.339e-05
K1, K0 = "w|rel+1.00", "w|rel+0.00"


def spearman(x, y):
    x = [float(v) for v in x]
    y = [float(v) for v in y]
    rx = [sorted(range(len(x)), key=lambda i: x[i]).index(i)
          for i in range(len(x))]
    ry = [sorted(range(len(y)), key=lambda i: y[i]).index(i)
          for i in range(len(y))]
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    rx = [v - mx for v in rx]
    ry = [v - my for v in ry]
    d = (sum(v * v for v in rx) * sum(v * v for v in ry)) ** 0.5
    return sum(a * b for a, b in zip(rx, ry)) / d if d else 0.0


def traj_mean(rows, key):
    """按轨迹聚合：组内先对轨迹取均值，再对轨迹取均值。"""
    by = {}
    for r in rows:
        by.setdefault(r["traj"], []).append(r["d"][key]["mark"] - r["d"][K0]["mark"])
    per = {t: sum(v) / len(v) for t, v in by.items()}
    return sum(per.values()) / len(per), per


def report(tag, rows):
    n = len(rows)
    nt = len(set(r["traj"] for r in rows))
    m_all, per = traj_mean(rows, K1)
    ctl = traj_mean(rows, "w|rel+1.00")[0]     # 同函数，这里替换成 ctl 字段
    # ctl 要单独算（field 不同）
    def tm(field):
        by = {}
        for r in rows:
            by.setdefault(r["traj"], []).append(
                r["d"][K1][field] - r["d"][K0][field])
        per = {t: sum(v) / len(v) for t, v in by.items()}
        return sum(per.values()) / len(per)
    d_ctl = tm("ctl")
    d_cur = tm("cur")
    d_rnd = tm("mark") if False else None
    by = {}
    for r in rows:
        by.setdefault(r["traj"], []).append(
            r["d"]["rand|rel+1.00"]["mark"] - r["d"]["rand|rel+0.00"]["mark"])
    per_r = {t: sum(v) / len(v) for t, v in by.items()}
    d_rand = sum(per_r.values()) / len(per_r)
    ok = sum(1 for r in rows if r["is_correct"])
    ntk = len(set(r["traj"] for r in rows if r["is_correct"]))

    print(f"\n{'=' * 66}\n### 口径 {tag}：{n} 个位置 / {nt} 条轨迹"
          f"（答对轨迹 {ntk}）\n{'=' * 66}")
    print(f"  Δmarker            {m_all:+.4f}")
    print(f"  Δ' the '          {d_ctl:+.4f}")
    print(f"  Δ标记词本身        {d_cur:+.4f}")
    print(f"  随机方向 Δmarker   {d_rand:+.4f}")
    print(f"  |Δw| / |Δ随机|     {abs(m_all) / max(1e-9, abs(d_rand)):.1f}×")
    print(f"  特异性比 |Δmarker|/|Δ'the'|  {abs(m_all) / max(1e-9, abs(d_ctl)):.3f}")
    # 单调性（只在 marker 位置口径下有意义，因为 negative 档也在）
    ladder = ["w|rel+0.00", "w|rel+0.25", "w|rel+0.50", "w|rel+1.00"]
    vals = []
    for k in ladder:
        bb = {}
        for r in rows:
            bb.setdefault(r["traj"], []).append(
                r["d"][k]["mark"] - r["d"][K0]["mark"])
        pp = {t: sum(v) / len(v) for t, v in bb.items()}
        vals.append(sum(pp.values()) / len(pp))
    print(f"  正向剂量曲线 ρ     {spearman(vals, [0, 1, 2, 3]):+.3f}"
          f"   ({' '.join(f'{v:+.3f}' for v in vals)})")
    return {"n": n, "d_marker": m_all, "d_ctl": d_ctl, "d_cur": d_cur,
            "d_rand": d_rand, "ratio_rand": abs(m_all) / max(1e-9, abs(d_rand)),
            "spec": abs(m_all) / max(1e-9, abs(d_ctl)), "curve": vals}


def main() -> int:
    d = json.load(open(SRC, encoding="utf-8"))
    rows = d["rows"]
    mids = set(d["marker_ids"])
    in_set = [r for r in rows if r["marker_id"] in mids]
    out_set = [r for r in rows if r["marker_id"] not in mids]

    print(f"全样本 {len(rows)} 个位置，其中**实际写的 token 在 marker 集合内**的 "
          f"{len(in_set)} 个，不在的 {len(out_set)} 个")
    print(f"噪声底 {NOISE:.2e}")
    a = report("A（全样本，PREREG 取数时定的）", rows)
    b = report("B（仅 marker 位置，事后限制）", in_set)

    print(f"\n{'=' * 66}\n### 口径 A 的均值被谁拉动\n{'=' * 66}")
    print(f"  全部 38 位置            Δ {a['d_marker']:+.4f}")
    print(f"  marker 位置 {len(in_set):2d} 个      Δ {b['d_marker']:+.4f}")
    by = {}
    for r in out_set:
        by.setdefault(r["traj"], []).append(
            r["d"][K1]["mark"] - r["d"][K0]["mark"])
    pp = {t: sum(v) / len(v) for t, v in by.items()}
    c = sum(pp.values()) / len(pp)
    print(f"  非 marker 位置 {len(out_set):2d} 个    Δ {c:+.4f}"
          f"   ← 是其余的 {c / max(1e-9, abs(b['d_marker'])):.1f} 倍")

    print("\n### 两条口径下判决是否翻转")
    for name, v in (("A", a), ("B", b)):
        print(f"  口径 {name}：方向可区分 {v['ratio_rand']:.1f}× "
              f"{'✅' if v['ratio_rand'] >= 10 else '❌'}   "
              f"特异性比 {v['spec']:.3f} "
              f"{'✅' if v['spec'] >= 1.2 else '❌'}")

    print("\n⚠ 口径 B 是**事后限制**，只能并列呈现，不能替换口径 A。")
    print("  它唯一的作用是回答：口径 A 的 +1.27 是被哪一类位置拉起来的。")
    json.dump({"A": a, "B": b, "n_marker_pos": len(in_set),
               "n_nonmarker_pos": len(out_set)},
              open(os.path.join(ROOT, ".cache", "mutbak",
                                "causal_rel44_calibers.json"),
                  "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\nwrote .cache/mutbak/causal_rel44_calibers.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())