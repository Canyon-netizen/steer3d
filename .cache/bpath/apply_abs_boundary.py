"""修订 32 的**绝对边界**过滤器：把极对齐选材清单收紧到 `|w·ĥ| > 0.10`。

## 为什么需要这一步

远端 `ortho_extreme_scan.py` 跑的是**修订 32 之前**的版本，只做了
「逐轨迹 `|w·ĥ|` 最高十分位」，没有绝对边界。本地版 `pick_top_decile()`
已经带了 `orth_min=0.10`，但**不能**重跑扫描（要远端 npz），所以在本地
对已有清单做**后置过滤**。

## 后置过滤与直接跑新版扫描严格等价

`pick_top_decile()` 的两段是：

    k   = max(1, int(len(pairs) * decile))          # ← 只看该轨迹 marker 总数
    top = [p for p in order[:k] if abs(p[1]) > orth_min]

十分位的**分母 `len(pairs)` 和名额 `k` 都在绝对边界之前决定**，
边界只作用在已经取好的 `top` 上。所以

    新版扫描(top_k) == 旧版清单(top_k) 后置过滤 aw > 0.10

逐位点相同。⚠ 顺序不能反 —— 先筛边界会改变 k，取到的就不是
「该轨迹的最高十分位」了。

## 顺带丢掉零位点轨迹

过完边界后有轨迹一个位点都不剩（整体低对齐的轨迹，它的最高十分位
整体都在 0.1 以下）。留着它们只会让探针白跑一趟轨迹加载，
所以丢弃，并**如实报出丢了哪几条**。

## 守卫

⚠ 全部用显式 `raise`，不用 `assert` ——
`python -O` 会把 `assert` 关掉，守卫就静默失效了
（本项目 `bpath` 工具链的既定纪律）。

只读输入，只写 `--out`。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ORTH_MIN = 0.10          # 与 ortho_extreme_scan.ORTH_MIN 同值


def apply_boundary(pick, orth_min=ORTH_MIN):
    """pick: extreme_pick.json 的内容 -> (新清单, 丢弃的空轨迹列表)"""
    kept_tracks, dropped = [], []
    for t in pick["tracks"]:
        sites = t["sites"]
        for s in sites:
            # ⚠ 每处字段访问都要断言命中：缺字段会 KeyError，
            # 但 aw 缺失时若写成 s.get("aw") 就会静默变成 None 而比较崩在别处。
            if "aw" not in s:
                raise KeyError(f"{t['traj']} 的位点 {s.get('t')} 没有 aw 字段")
            if not isinstance(s["aw"], (int, float)):
                raise TypeError(f"{t['traj']} t={s['t']} 的 aw 不是数值：{s['aw']!r}")
        keep = [s for s in sites if s["aw"] > orth_min]
        if not keep:
            dropped.append({"traj": t["traj"], "decile_n": len(sites),
                            "reason": f"最高十分位里没有一个位点 |w·ĥ| > {orth_min}"})
            continue
        kept_tracks.append({"traj": t["traj"], "n_sites": t["n_sites"],
                            "n_kept": len(keep), "sites": keep})
    return kept_tracks, dropped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inp", required=True, help="extreme_pick.json（旧版，无绝对边界）")
    ap.add_argument("--out", required=True)
    ap.add_argument("--expect-tracks", type=int, default=None,
                    help="输入清单的轨迹数，不符就拒绝")
    ap.add_argument("--expect-sites", type=int, default=None,
                    help="输入清单的位点总数，不符就拒绝")
    ap.add_argument("--expect-kept-sites", type=int, default=None,
                    help="过完边界后的位点总数，不符就拒绝")
    ap.add_argument("--expect-kept-tracks", type=int, default=None)
    a = ap.parse_args()

    pick = json.loads(Path(a.inp).read_text(encoding="utf-8"))
    if pick.get("schema") != "extreme_pick/1":
        raise SystemExit(f"输入 schema 不是 extreme_pick/1：{pick.get('schema')!r}")
    tracks = pick["tracks"]
    n_sites = sum(len(t["sites"]) for t in tracks)
    if a.expect_tracks is not None and len(tracks) != a.expect_tracks:
        raise SystemExit(f"轨迹数 {len(tracks)} != 预期 {a.expect_tracks}，拒绝过滤")
    if a.expect_sites is not None and n_sites != a.expect_sites:
        raise SystemExit(f"位点数 {n_sites} != 预期 {a.expect_sites}，拒绝过滤")

    kept, dropped = apply_boundary(pick)
    n_kept = sum(t["n_kept"] for t in kept)
    n_ge8 = sum(1 for t in kept if t["n_kept"] >= 8)

    if a.expect_kept_sites is not None and n_kept != a.expect_kept_sites:
        raise SystemExit(f"过边界后位点 {n_kept} != 预期 {a.expect_kept_sites}，拒绝写出")
    if a.expect_kept_tracks is not None and len(kept) != a.expect_kept_tracks:
        raise SystemExit(f"过边界后轨迹 {len(kept)} != 预期 {a.expect_kept_tracks}，拒绝写出")

    out = {
        "schema": "extreme_pick_abs/1",
        "prereg": "R6_RERUN_PREREG.md 修订 32（极对齐位点 ≡ 最高十分位 ∩ |w·ĥ| > 0.10）",
        "derived_from": a.inp,
        "rule": ("逐轨迹 |w·ĥ| 最高 10% 的 marker 位点（名额 k 由该轨迹 marker 总数决定，"
                 "**不受**绝对边界影响）**且** |w·ĥ| > 0.10；"
                 "先取十分位再过边界，反过来会改变分母"),
        "orth_min": ORTH_MIN,
        "decile": pick["decile"],
        "n_tracks_in": len(tracks),
        "n_sites_in": n_sites,
        "n_tracks": len(kept),
        "n_sites": n_kept,
        "n_tracks_ge8": n_ge8,
        "n_dropped_tracks": len(dropped),
        "dropped_tracks": dropped,
        "tracks": kept,
    }
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1),
                           encoding="utf-8")

    print(f"输入 {len(tracks)} 条 / {n_sites} 位点"
          f" ⇒ 过 |w·ĥ| > {ORTH_MIN} 后 {len(kept)} 条 / {n_kept} 位点")
    print(f"丢弃 {n_sites - n_kept} 个位点（{(n_sites - n_kept) / n_sites:.1%}）")
    print(f"≥8 位点（E2 可判）的轨迹：{n_ge8} 条")
    for d in dropped:
        print(f"  丢弃轨迹 {d['traj']}：十分位 {d['decile_n']} 个位点，{d['reason']}")
    print(f"前向估计 = {n_kept}×3×2 + {len(kept)} = {n_kept * 3 * 2 + len(kept)}")
    print(f"写出 {a.out}")


if __name__ == "__main__":
    main()
