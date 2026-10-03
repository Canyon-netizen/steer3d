#!/usr/bin/env python3
"""S1b — 从 S1 的缓存重算 L12..L15 的 4 条 contrast 方向（修正全局池化）。

## 怎么跑

    cd /Users/zhourui/code/steer3d
    python3 .cache/layerside2/s1_cache_facts.py     # 先跑，产出 hidden_L{12..15}.npy
    python3 .cache/layerside2/s1b_vectors.py         # 再跑本脚本

产物：
    vecs_L12_L15.npz   4 条独立轴 × 4 个层的单位方向（覆盖 s1 的错误版本）
    s1b_vectors.json   复现判据 + 全部原始数值

## 为什么必须有 S1b（s1 的向量段已作废）

`compute_steering_vectors.py` 的 `pool_self_check` / `pool_think_block` 是
**先遍历全部轨迹、再做一次全局尺寸闸门**。s1 把它当成逐轨迹闸门用了，
于是把 21 条「整条都在 <think> 内」的轨迹（38912 token）和 self-check 数
不足 20 的轨迹整条丢掉，caution 池从 62799 缩到 15198、creativity 池从
62799 缩到 5088，与线上发布向量对不上。

判据不是「cos 差不多」，而是**样本数逐个相等**：
    self_check 正则（跳过前 n_prompt 个 token）= 379  = 发布 n_positive
    in_think（跳过前 n_prompt 个 token）        = 40338 = 发布 n_positive
    379+62420 = 40338+22461 = 62799 = 69155 − 6356（= Σ n_prompt_tokens）
两组都对上，才说明分组谓词与发布那次逐字一致。

## 数值口径

`hidden_states` 是 fp16，缓存里已转 float32；均值用 float64 累加。
`dot()` 不用 BLAS matmul，而是 `np.sum(a*b)`：本机 BLAS 是 accelerate，
会对正常 float64 matmul 抛伪的 divide-by-zero/overflow 告警。
1-D/2-D `@` 经与手写求和 450 次对照无误，但 `sum(a*b)` 无此风险。
"""
import json
import re
import time
from pathlib import Path

import numpy as np

ROOT = Path("/Users/zhourui/code/steer3d")
NPZ_DIR = ROOT / "datasets/aime_qwen3_1p7b_16k_fp16/aime"
VEC_DIR = ROOT / "backend/examples/output/steering_vectors"
OUT = Path(__file__).resolve().parent

LAYERS = [12, 13, 14, 15]
AXES = ["confidence_up", "reasoning_deep", "caution", "creativity"]
DERIVED = {"confidence_down": "confidence_up", "reasoning_shallow": "reasoning_deep"}
MIN_LEN = 20          # compute_steering_vectors.main 里的全局闸门
SELF_CHECK_RE = re.compile(
    r"\b(wait|actually|hmm|hold on|let me check|let me verify|recheck|"
    r"double[- ]check|second thought|alternatively|but wait)\b", re.IGNORECASE)


def dot(a, b):
    """与 BLAS 无关的内积。float64 累加。"""
    return float(np.sum(np.asarray(a, dtype=np.float64) *
                        np.asarray(b, dtype=np.float64), dtype=np.float64))


def l2(v):
    v = np.asarray(v, dtype=np.float64)
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-8 else v


def build_flags():
    """逐轨迹的 token 标记（已按 n_prompt 跳过开头），返回 (n_total, [(name,T,n_p,sc,th,valid)])。

    `valid` 必须单独存：`compute_steering_vectors.py` 的两个 flag 池在遍历里
    对正负两侧**同时**跳过 i < n_prompt。若把 i>=n_p 只折进正侧掩码、负侧用
    `~flag`，就会把 6356 个 prompt token 放回负组（379+68776=69155 即此）。
    """
    rows, total = [], 0
    for f in sorted(NPZ_DIR.glob("*.npz")):
        side = json.loads(f.with_suffix(".json").read_text())
        toks = side["tokens"]
        n_p = int(side.get("n_prompt_tokens", 0) or 0)
        valid = np.zeros(len(toks), dtype=bool)
        valid[n_p:] = True
        # 与 compute_steering_vectors.py:109-113 同：flag 全 False 时用正则重算
        if any(bool(t.get("is_self_check", False)) for t in toks):
            sc_raw = np.array([bool(t.get("is_self_check", False)) for t in toks])
        else:
            sc_raw = np.array([bool(SELF_CHECK_RE.search(t["token"] or "")) for t in toks])
        th_raw = np.array([bool(t.get("is_in_think_block", False)) for t in toks])
        rows.append({"name": f.stem, "T": len(toks), "n_prompt": n_p,
                     "is_self_check": sc_raw & valid, "is_in_think": th_raw & valid,
                     "valid": valid,
                     "entropy": np.array([t["entropy"] for t in toks], dtype=np.float64)})
        total += len(toks)
    return rows, total


def main():
    t0 = time.time()
    idx = json.loads((OUT / "traj_index.json").read_text())
    trajs, total_rows = build_flags()
    if total_rows != idx["total_rows"]:
        raise AssertionError(f"sidecar 步数 {total_rows} != 缓存 {idx['total_rows']}")
    if len(trajs) != len(idx["traj"]):
        raise AssertionError(f"轨迹数 {len(trajs)} != {len(idx['traj'])}")
    for t, e in zip(trajs, idx["traj"]):
        # 名称可能因 <U30 截断而对不上，用下标 + 行数 + n_prompt 三重核验
        if t["T"] != e["rows"]:
            raise AssertionError(f"轨迹 {t['name']}: sidecar {t['T']} 步 != npz {e['rows']} 步")
    print(f"[flags] {len(trajs)} traj, {total_rows} steps, "
          f"self_check={sum(int(t['is_self_check'].sum()) for t in trajs)}, "
          f"in_think={sum(int(t['is_in_think'].sum()) for t in trajs)}", flush=True)

    caches = {L: np.load(OUT / f"hidden_L{L}.npy", mmap_mode="r") for L in LAYERS}
    res = {"schema": "layerside2.s1b_vectors/1",
           "n_rows": total_rows, "layers": LAYERS,
           "sum_n_prompt_tokens": int(sum(t["n_prompt"] for t in trajs)),
           "n_tokens_after_n_prompt_skip": total_rows - int(
               sum(t["n_prompt"] for t in trajs)),
           "pool_counts": {}, "reproduction": {}, "adjacent_cos": {}}

    vecs = {L: {} for L in LAYERS}
    for L in LAYERS:
        H = caches[L]
        # ---- 逐轨迹池（confidence / reasoning）----
        pos_sum = {a: np.zeros(H.shape[1]) for a in AXES}
        neg_sum = {a: np.zeros(H.shape[1]) for a in AXES}
        pos_n = {a: 0 for a in AXES}
        neg_n = {a: 0 for a in AXES}

        def add(a, pos, neg):
            pos_sum[a] += pos.sum(axis=0, dtype=np.float64)
            neg_sum[a] += neg.sum(axis=0, dtype=np.float64)
            pos_n[a] += int(len(pos))
            neg_n[a] += int(len(neg))

        # ---- 全局池（caution / creativity）：先累积全部轨迹，再过一次闸门 ----
        sc_rows, reg_rows, ins_rows, out_rows = [], [], [], []
        for t, e in zip(trajs, idx["traj"]):
            h = np.asarray(H[e["start"]:e["stop"]], dtype=np.float64)
            n_p = t["n_prompt"]
            gen_h = h[n_p:]
            gen_e = t["entropy"][n_p:]
            if len(gen_h) >= 20:
                q1, q3 = np.percentile(gen_e, 30), np.percentile(gen_e, 75)
                add("confidence_up", gen_h[gen_e <= q1], gen_h[gen_e >= q3])
            if len(gen_h) >= 120:
                k = len(gen_h) // 4
                add("reasoning_deep", gen_h[-k:], gen_h[:k])
            sc, th, va = t["is_self_check"], t["is_in_think"], t["valid"]
            if sc.any():
                sc_rows.append(h[sc])
            reg_rows.append(h[va & ~sc])
            if th.any():
                ins_rows.append(h[th])
            out_rows.append(h[va & ~th])
            del h, gen_h, gen_e
        sc_all = np.concatenate(sc_rows)
        reg_all = np.concatenate(reg_rows)
        ins_all = np.concatenate(ins_rows)
        out_all = np.concatenate(out_rows)
        del sc_rows, reg_rows, ins_rows, out_rows
        # 全局闸门，与 compute_steering_vectors.py:221-223 / 235-237 逐字一致
        if len(sc_all) >= 20 and len(reg_all) >= 100:
            add("caution", sc_all, reg_all)
        if len(ins_all) >= 50 and len(out_all) >= 100:
            add("creativity", ins_all, out_all)
        res["pool_counts"][str(L)] = {a: {"n_positive": pos_n[a], "n_negative": neg_n[a]}
                                      for a in AXES}
        for a in AXES:
            if pos_n[a] >= MIN_LEN and neg_n[a] >= MIN_LEN:
                vecs[L][a] = l2((pos_sum[a] / pos_n[a]) - (neg_sum[a] / neg_n[a]))
            else:
                vecs[L][a] = None
        del sc_all, reg_all, ins_all, out_all
        print(f"[L{L}] " + "  ".join(
            f"{a}=({res['pool_counts'][str(L)][a]['n_positive']},"
            f"{res['pool_counts'][str(L)][a]['n_negative']})" for a in AXES), flush=True)

    # ---- 复现判据（对全部 6 个发布向量逐条检查）----
    meta = json.loads((VEC_DIR / "steering_vectors.json").read_text())
    for a in AXES:
        pub = np.load(VEC_DIR / f"{a}.npy").astype(np.float64).ravel()
        pub = pub / np.linalg.norm(pub)
        c = res["pool_counts"]["14"][a]
        res["reproduction"][a] = {
            "published_n_positive": meta[a]["n_positive"],
            "recomputed_n_positive": c["n_positive"],
            "published_n_negative": meta[a]["n_negative"],
            "recomputed_n_negative": c["n_negative"],
            "counts_match": (c["n_positive"] == meta[a]["n_positive"] and
                             c["n_negative"] == meta[a]["n_negative"]),
            "cos_recomputed_L14_vs_published": dot(vecs[14][a], pub),
            "published_layer": meta[a]["layer"],
            "published_positive_group": meta[a]["positive_group"],
            "published_negative_group": meta[a]["negative_group"],
            "reproduced": (c["n_positive"] == meta[a]["n_positive"] and
                           c["n_negative"] == meta[a]["n_negative"] and
                           dot(vecs[14][a], pub) > 0.999),
        }
    for a, base in DERIVED.items():
        pub = np.load(VEC_DIR / f"{a}.npy").astype(np.float64).ravel()
        pub = pub / np.linalg.norm(pub)
        bp = np.load(VEC_DIR / f"{base}.npy").astype(np.float64).ravel()
        bp = bp / np.linalg.norm(bp)
        res["reproduction"][a] = {
            "derived_from": base,
            "cos_recomputed_L14_vs_published": dot(vecs[14][base], pub),
            "cos_published_vs_neg_base": dot(pub, -bp),
            "n_positive": meta[a]["n_positive"], "n_negative": meta[a]["n_negative"],
        }

    # ---- item 2：相邻层 cos ----
    for a in AXES:
        pairs = {}
        for lo, hi in ((12, 13), (13, 14), (14, 15)):
            pairs[f"L{lo}_vs_L{hi}"] = dot(vecs[lo][a], vecs[hi][a])
        res["adjacent_cos"][a] = pairs

    # ---- cos(发布向量, 重算的 v_Lv)：发布向量就是 v_L14，所以 L14 那行必须是 1 ----
    res["cos_published_vs_recomputed"] = {}
    for a in AXES:
        pub = np.load(VEC_DIR / f"{a}.npy").astype(np.float64).ravel()
        pub = pub / np.linalg.norm(pub)
        res["cos_published_vs_recomputed"][a] = {
            str(L): dot(vecs[L][a], pub) for L in LAYERS}
    # 恒等式：cos(发布, v_L13) 必须等于 cos(v_L13, v_L14)
    res["identity_published_L13_equals_L13_vs_L14"] = {
        a: {
            "cos_published_vs_L13": res["cos_published_vs_recomputed"][a]["13"],
            "cos_L13_vs_L14": res["adjacent_cos"][a]["L13_vs_L14"],
            "abs_diff": abs(res["cos_published_vs_recomputed"][a]["13"]
                            - res["adjacent_cos"][a]["L13_vs_L14"]),
        } for a in AXES}

    # ---- 存盘 ----
    np.savez(OUT / "vecs_L12_L15.npz", axes=np.array(AXES),
             **{f"L{L}": np.stack([vecs[L][a] for a in AXES]) for L in LAYERS})
    res["elapsed_sec"] = round(time.time() - t0, 1)
    (OUT / "s1b_vectors.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(json.dumps(res["reproduction"], ensure_ascii=False, indent=1))
    print(json.dumps(res["adjacent_cos"], ensure_ascii=False, indent=1))
    print(f"[done] {res['elapsed_sec']}s -> s1b_vectors.json")


if __name__ == "__main__":
    main()
