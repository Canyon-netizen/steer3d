"""前置可行性检查：新批次的 think 轨迹里有多少动摇标记词？

## 为什么现在查

B 路全量还要 3 小时多。若新批次的 CoT 里几乎没有 Wait/Hmm/Let/maybe，
R-6 重跑（correct vs incorrect 对照）的**位置来源**就没了，
整套设计要改。现在查几分钟；等 3 小时后才发现，代价是整轮生成白跑。

## 用什么查

轨迹侧车里有逐步的 `tokens` 列表（`step_id` / `token_id` / `token`），
不必下 npz、不必加载 tokenizer 就能数。marker id 取自
CAUSAL_PREREG 的预登记集合（写死的 7 个），不在这里重新挑。

## 判决规则（取数前写死）

  M1 每条 think 轨迹的 marker 位置数 >= 3 才算「可用于取样」。
     低于 3 条的位置无法做配对比较。
  M2 pilot 3 条 think 轨迹里，**至少 2 条**满足 M1
     —— 否则说明这个 cap 下 CoT 形态变了，需要改设计。
  M3 marker 的相对密度（每千 token 的 marker 数）与旧批次
     （cap 2048，24 条 think）比，不得低于旧批次的一半。
     若显著更低，说明 marker 变少了，抽出来的位置可能系统性偏易。

⚠ **修订 M3（原 M3 是错的可观测量，见本轮披露）**：M3 用的是「每千 token 的
   密度」，但新旧批次的 trace 长度差很多（旧中位 2048 token，新 3300-4000），
   分母一变密度就跟着动，**这个量分不清「marker 变少」和「trace 变长」**。
   取样是**按轨迹**做的，真正决定「每条轨迹能抽几个位置」的是**绝对 marker 数**。
   补 M3' = 每条轨迹 marker **绝对数**中位数之比，这才是要解除的约束。

M2/M3'/任一不达标 => 不要等全量跑完，先停下来改设计。
"""
from __future__ import annotations

import glob
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

# CAUSAL_PREREG 预登记写死的 7 个 marker token id
MARKER_IDS = [13824, 14190, 6771, 10061, 7196, 88190, 80022]
MIN_PER_TRAJ = 3
MIN_TRAJS_OK = 2
DENSITY_FLOOR = 0.5


def scan(path):
    j = json.load(open(path, encoding="utf-8"))
    toks = j.get("tokens") or []
    ids = [t["token_id"] for t in toks]
    n_tok = j.get("n_generated_tokens") or len(ids)
    pos, which = [], []
    for i, tid in enumerate(ids):
        if tid in MARKER_IDS:
            pos.append(i)
            which.append(toks[i].get("token", "?"))
    return {
        "traj": j["trajectory_id"],
        "mode": j["config"]["mode"],
        "n_tok": n_tok,
        "n_marker": len(pos),
        "per_1k": len(pos) / max(n_tok, 1) * 1000,
        "which": Counter(which),
        "marker_texts": sorted({t.get("token", "?") for t in toks
                                if t["token_id"] in MARKER_IDS}),
    }


def report(rows, title):
    print(f"\n{'='*72}\n{title}\n{'='*72}")
    print(f"{'traj':40s} {'mode':9s} {'tok':>6s} {'marker':>7s} {'每千tok':>8s}  出现的标记词")
    for r in rows:
        print(f"{r['traj']:40s} {r['mode']:9s} {r['n_tok']:6d} {r['n_marker']:7d} "
              f"{r['per_1k']:8.2f}  {sorted(r['which'])}")
    th = [r for r in rows if r["mode"] == "think"]
    if th:
        d = [r["per_1k"] for r in th]
        a = [r["n_marker"] for r in th]
        print(f"\nthink 每千 token 密度: min={min(d):.2f} 中位={statistics.median(d):.2f} max={max(d):.2f}")
        print(f"think 每条轨迹绝对 marker 数: min={min(a)} 中位={statistics.median(a):.0f} max={max(a)}"
              f"   <- 这才是「每条能抽几个位置」")
        ok = [r for r in th if r["n_marker"] >= MIN_PER_TRAJ]
        print(f"M1 满足 (marker>={MIN_PER_TRAJ}) 的 think 轨迹: {len(ok)}/{len(th)}")
        return th, statistics.median(d), len(ok), statistics.median(a)
    return [], 0.0, 0, 0.0


def main():
    # 新批次：cap 8192 的 pilot（本地侧车）
    new = [scan(p) for p in sorted(glob.glob(".cache/bpath/pilot/*.json"))]
    th_new, dens_new, ok_new, abs_new = report(new, "A) 新批次 pilot（cap 8192）")

    # 旧批次：cap 2048 的 24 条 think（对照）
    old = [scan(p) for p in sorted(
        glob.glob("datasets/aime_qwen3_1p7b_16k_fp16/aime/*__think.json"))]
    th_old, dens_old, ok_old, abs_old = report(old, "B) 旧批次（cap 2048）对照")

    print("\n" + "=" * 72)
    print("判决")
    print("=" * 72)
    m1 = ok_new >= MIN_TRAJS_OK
    print(f"M2 pilot 里满足 M1 的 think 轨迹 >= {MIN_TRAJS_OK} : 实测 {ok_new}/{len(th_new)}"
          f"  -> {'PASS' if m1 else 'FAIL'}")
    if th_old:
        ratio = dens_new / dens_old if dens_old else float("inf")
        m3 = ratio >= DENSITY_FLOOR
        print(f"M3 每千token密度比 >= {DENSITY_FLOOR}        : 实测 {dens_new:.2f}/{dens_old:.2f}"
              f" = {ratio:.2f}x  -> {'PASS' if m3 else 'FAIL'}"
              f"   （该量受 trace 长度影响，仅作参考）")
        ratio_abs = abs_new / abs_old if abs_old else float("inf")
        m3p = ratio_abs >= DENSITY_FLOOR
        print(f"M3' 每条轨迹绝对 marker 数之比 >= {DENSITY_FLOOR}: 实测 {abs_new:.0f}/{abs_old:.0f}"
              f" = {ratio_abs:.2f}x  -> {'PASS' if m3p else 'FAIL'}"
              f"   <- **这条才是要解除的约束**")
    else:
        m3 = m3p = False
        print("M3/M3' 无旧批次可比 -> FAIL")

    print()
    verdict_ok = m1 and m3p
    if verdict_ok:
        print("=> 新批次每条 think 轨迹的 marker 数与旧批次相当，"
              "可以照原设计重跑 R-6（位置来源不受阻）。")
    else:
        print("=> **不要等全量跑完**：先停下来改 R-6 的位置来源设计。")

    out = Path(".cache/mutbak/bpath_marker_feasibility.json")
    json.dump({
        "marker_ids": MARKER_IDS,
        "rules": {"min_per_traj": MIN_PER_TRAJ, "min_trajs_ok": MIN_TRAJS_OK,
                  "floor": DENSITY_FLOOR},
        "m3_note": "M3 用每千 token 密度，受 trace 长度影响；M3' 用绝对数，才是取样相关的量。",
        "new_batch": {"rows": new, "density_median": dens_new, "abs_median": abs_new,
                      "trajs_ok": ok_new},
        "old_batch": {"rows": old, "density_median": dens_old, "abs_median": abs_old,
                      "trajs_ok": ok_old},
        "verdict": {"M2": m1, "M3_density_reference_only": m3, "M3_prime": m3p},
    }, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("写出", out)
    return 0 if verdict_ok else 1


if __name__ == "__main__":
    sys.exit(main())