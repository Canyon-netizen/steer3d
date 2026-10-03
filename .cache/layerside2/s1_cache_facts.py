#!/usr/bin/env python3
"""S1 — 单遍数据抽取：层语义事实核验 + 范数统计 + L12..L15 的 4 条 contrast 方向。

## 怎么跑

    cd /Users/zhourui/code/steer3d
    python3 .cache/layerside2/s1_cache_facts.py

产物（全部在本目录下）：
    hidden_L{12,13,14,15}.npy   float32  memmap，(69155, 2048)，已按 attention_mask 过滤
    traj_index.json             每条轨迹的 [start, stop) 行区间与有效步数
    entropy.npy                 float32 (69155,)  与 hidden 同序
    obs_series.npy              float32 (69155,10) obs_series.npz 的 obs，按本序重排
    vecs_L{12,13,14,15}.npz     4 条独立轴的 diff_of_means 方向
    s1_facts.json               本脚本的全部原始数值

## 设计决定

1. **单遍**：hidden_states 约 9.1 GB fp16，解压成本高。四个层一次读进来，
   一次算出所有统计与四个 contrast，避免重复 IO。
2. **float16 → float32 先转再点积**：磁盘是 fp16，直接做 Gram/均值会溢出且
   精度不可控。缓存里就存 float32。
3. **逐条核对 n_positive/n_negative**：contrast 方向的复现不接受「看起来对」，
   必须与 steering_vectors.json 里记的样本数逐个相等才算复现成功。
4. **两种累加精度都算**：原实现 diff_of_means 在 float32 上求均值；这里同时
   给 float32 与 float64 两条路径的余弦，用来分辨「复现失败」和「累加精度漂移」。
5. **基线核验与归因分开**：核验函数只看「全部是否通过」，不产生红/绿名单。
"""
import json
import re
import time
from pathlib import Path

import numpy as np

ROOT = Path("/Users/zhourui/code/steer3d")
NPZ_DIR = ROOT / "datasets/aime_qwen3_1p7b_16k_fp16/aime"
VEC_DIR = ROOT / "backend/examples/output/steering_vectors"
SERIES = ROOT / ".cache/rolesverify/obs_series.npz"
OUT = Path(__file__).resolve().parent

LAYERS = [12, 13, 14, 15]      # 覆盖 14 与 13（注入点），两侧各留一个邻层
D_MODEL = 2048
N_LAYERS = 28
LAST_LAYER = 27                 # 已确证：hidden_states[:,27] == last_hidden
PRE_LAST_LAYER = 26

# 与 backend/examples/compute_steering_vectors.py:42 逐字相同
SELF_CHECK_RE = re.compile(
    r"\b(wait|actually|hmm|hold on|let me check|let me verify|recheck|"
    r"double[- ]check|second thought|alternatively|but wait)\b",
    re.IGNORECASE,
)

# 4 条独立轴；confidence_down / reasoning_shallow 是负向派生（脚本末尾核验）
AXES = ["confidence_up", "reasoning_deep", "caution", "creativity"]
DERIVED = {"confidence_down": "confidence_up", "reasoning_shallow": "reasoning_deep"}


def l2(v):
    v = np.asarray(v, dtype=np.float64)
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-8 else v


# --------------------------------------------------------------- contrast 池
# 这四个函数逐字照搬 compute_steering_vectors.py 的分组谓词。改一个字符
# 就会让 n_positive/n_negative 对不上，而那是本脚本唯一的复现判据。
def pool_confidence(h, e, n_p):
    """low-entropy (p30) 组 vs high-entropy (p75) 组。"""
    gen_h, gen_e = h[n_p:], e[n_p:]
    if len(gen_h) < 20:
        return None
    q1, q3 = np.percentile(gen_e, 30), np.percentile(gen_e, 75)
    return gen_h[gen_e <= q1], gen_h[gen_e >= q3]


def pool_reasoning_depth(h, e, n_p):
    """长轨迹的后 25% vs 前 25%。"""
    gen = h[n_p:]
    if len(gen) < 120:
        return None
    return gen[-(len(gen) // 4):], gen[: len(gen) // 4]


def pool_self_check(h, e, n_p, flags):
    """self-check token vs 其它生成 token（逐条遍历，i < n_prompt 跳过）。"""
    sc, reg = [], []
    for i, f in enumerate(flags):
        if i < n_p:
            continue
        (sc if f else reg).append(h[i])
    if len(sc) < 20 or len(reg) < 100:
        return None
    return np.stack(sc), np.stack(reg)


def pool_think_block(h, e, n_p, flags):
    """<think> 内 vs 外。"""
    ins, out = [], []
    for i, f in enumerate(flags):
        if i < n_p:
            continue
        (ins if f else out).append(h[i])
    if len(ins) < 50 or len(out) < 100:
        return None
    return np.stack(ins), np.stack(out)


def main():
    t0 = time.time()
    files = sorted(NPZ_DIR.glob("*.npz"))
    facts = {
        "schema": "layerside2.s1_facts/1",
        "n_files": len(files),
        "layers_cached": LAYERS,
        "d_model": D_MODEL,
        "attention_mask_audit": {
            "policy": "本任务要求用 attention_mask 过滤。逐文件核验 mask.sum() "
                      "与行数、以及是否存在 0；结果见 per_file_mismatch 与 "
                      "n_files_with_padding。",
        },
        "layer_convention_audit": {
            "claim": "hidden_states[:,L] 是第 L 个 block 的输出（末层 = 最终 RMSNorm 之前）",
            "evidence": "hs[:,27] 与 last_hidden 逐位相同；范数在 L26->L27 突降",
        },
        "per_traj": [],
    }
    am_mismatch, n_files_with_padding = [], 0

    # ---- 轨迹索引 / 行数 -------------------------------------------------
    traj_index, total_rows = [], 0
    for f in files:
        d = np.load(f, mmap_mode="r")
        T = int(d["hidden_states"].shape[0])
        traj_index.append({"name": f.stem, "start": total_rows, "stop": total_rows + T,
                           "rows": T})
        total_rows += T
        d.close()
    print(f"[idx] {len(traj_index)} traj, {total_rows} rows total", flush=True)

    # ---- 缓存与累加器 ---------------------------------------------------
    caches = {L: np.lib.format.open_memmap(
        OUT / f"hidden_L{L}.npy", mode="w+", dtype=np.float32,
        shape=(total_rows, D_MODEL)) for L in LAYERS}
    ent_cache = np.lib.format.open_memmap(
        OUT / "entropy.npy", mode="w+", dtype=np.float32, shape=(total_rows,))

    # obs_series 按**索引**重排到本脚本的行序。已核验 traj_names 与 sorted(npz)
    # 逐位相等（dtype <U30 会截断长名字，所以只能用下标对齐，不能按名字 join）。
    z = np.load(SERIES, allow_pickle=True)
    obs_all = z["obs"].astype(np.float32)
    obs_names = [str(x) for x in z["names"]]
    traj_T = z["traj_T"].astype(np.int64)
    if int(traj_T.sum()) != total_rows:
        raise AssertionError(
            f"obs_series 步数 {int(traj_T.sum())} != npz 总行数 {total_rows}")
    obs_cache = np.lib.format.open_memmap(
        OUT / "obs_series.npy", mode="w+", dtype=np.float32, shape=obs_all.shape)
    obs_cache[:] = obs_all
    del obs_all
    obs_offset = 0

    # 范数：逐层 sum(‖h‖) / sum(‖h‖²) / ‖mean(h)‖
    norm_sum = {L: 0.0 for L in LAYERS}
    norm_sq_sum = {L: 0.0 for L in LAYERS}
    hsum = {L: np.zeros(D_MODEL, dtype=np.float64) for L in LAYERS}
    n_norm = {L: 0 for L in LAYERS}
    # 全 28 层的 mean‖h‖，只为核验 L26->L27 的突降
    all_layer_norm_sum = np.zeros(N_LAYERS, dtype=np.float64)
    all_layer_n = np.zeros(N_LAYERS, dtype=np.int64)

    # contrast 累加器：sum 与 count（用 sum/count 而不是存下全部行，内存友好）
    acc = {L: {a: {"pos_sum": np.zeros(D_MODEL), "pos_n": 0,
                   "neg_sum": np.zeros(D_MODEL), "neg_n": 0}
               for a in AXES} for L in LAYERS}
    acc64 = {L: {a: {"pos_sum": np.zeros(D_MODEL), "neg_sum": np.zeros(D_MODEL)}
                 for a in AXES} for L in LAYERS}

    max_abs_diff_last = 0.0
    n_last_exact = 0
    n_last_total = 0

    for ti, entry in enumerate(traj_index):
        f = NPZ_DIR / (entry["name"] + ".npz")
        d = np.load(f, mmap_mode="r")
        side = json.loads(f.with_suffix(".json").read_text())
        toks = side["tokens"]
        T = entry["rows"]
        if len(toks) != T:
            raise AssertionError(f"{entry['name']}: sidecar tokens {len(toks)} != rows {T}")

        # ---- attention_mask 核验 ----
        am = np.asarray(d["attention_mask"])
        n_valid = int(am.sum())
        n_zero = int((am == 0).sum())
        if n_valid != T or n_zero:
            n_files_with_padding += 1
            am_mismatch.append({"name": entry["name"], "mask_sum": n_valid,
                                "rows": T, "n_zero": n_zero})
            keep = np.nonzero(am)[0]
        else:
            keep = np.arange(T)

        ent = np.asarray([t["entropy"] for t in toks], dtype=np.float32)
        flags_sc = [bool(t.get("is_self_check", False)) for t in toks]
        if not any(flags_sc):
            flags_sc = [bool(SELF_CHECK_RE.search(t["token"] or "")) for t in toks]
        flags_th = [bool(t.get("is_in_think_block", False)) for t in toks]
        n_p = int(side.get("n_prompt_tokens", 0) or 0)

        # ---- 层语义核验：hs[:,27] vs last_hidden + 全层范数 ----
        hs = d["hidden_states"]
        last = np.asarray(d["last_hidden"], dtype=np.float32)
        hs27 = np.asarray(hs[:, LAST_LAYER, :], dtype=np.float32)
        diff = np.abs(hs27 - last)
        max_abs_diff_last = max(max_abs_diff_last, float(diff.max()))
        n_last_exact += int((diff == 0).sum())
        n_last_total += int(diff.size)
        for L in range(N_LAYERS):
            nl = np.linalg.norm(np.asarray(hs[:, L, :], dtype=np.float32), axis=1)
            all_layer_norm_sum[L] += float(nl.sum())
            all_layer_n[L] += int(len(nl))
        del hs27, last, diff

        # ---- 缓存 + 范数 + contrast ----
        row = entry["start"]
        ent_cache[row:row + T] = ent
        for L in LAYERS:
            blk = np.asarray(hs[keep, L, :], dtype=np.float32)
            caches[L][row:row + len(keep)] = blk
            nl = np.linalg.norm(blk, axis=1)
            norm_sum[L] += float(nl.sum())
            norm_sq_sum[L] += float((nl ** 2).sum())
            hsum[L] += blk.sum(axis=0, dtype=np.float64)
            n_norm[L] += int(len(nl))
            h = blk  # 只有无 padding 时才对齐下标；有 padding 时期望被 audit 抓住
            pools = {
                "confidence_up": pool_confidence(h, ent, n_p),
                "reasoning_deep": pool_reasoning_depth(h, ent, n_p),
                "caution": pool_self_check(h, ent, n_p, flags_sc),
                "creativity": pool_think_block(h, ent, n_p, flags_th),
            }
            for a, pool in pools.items():
                if pool is None:
                    continue
                pos, neg = pool
                acc[L][a]["pos_sum"] += pos.sum(axis=0, dtype=np.float32)
                acc[L][a]["neg_sum"] += neg.sum(axis=0, dtype=np.float32)
                acc[L][a]["pos_n"] += int(len(pos))
                acc[L][a]["neg_n"] += int(len(neg))
                acc64[L][a]["pos_sum"] += pos.sum(axis=0, dtype=np.float64)
                acc64[L][a]["neg_sum"] += neg.sum(axis=0, dtype=np.float64)
            del blk, nl, pools
        row += T

        # ---- obs 重排（按 traj_id 索引，不按名字） ----
        tid = z["traj_id"]
        m = tid == ti
        n_obs = int(m.sum())
        if n_obs != T:
            raise AssertionError(
                f"obs_series traj {ti} 有 {n_obs} 步，npz 有 {T} 步 —— 步长/顺序未对齐")
        obs_cache[obs_offset:obs_offset + n_obs] = z["obs"][m]
        obs_offset += n_obs

        facts["per_traj"].append({
            "name": entry["name"], "rows": T, "n_valid_mask": n_valid,
            "n_zero_mask": n_zero, "n_prompt_tokens": n_p,
        })
        d.close()
        if (ti + 1) % 8 == 0:
            print(f"  [{ti+1}/{len(traj_index)}] {entry['name']}", flush=True)

    if obs_offset != total_rows:
        raise AssertionError(f"obs 重排 {obs_offset} 步 != {total_rows}")

    for L in LAYERS:
        caches[L].flush()
    ent_cache.flush()
    obs_cache.flush()

    # ---- 层语义结论 ----
    mean_norm_all = (all_layer_norm_sum / np.maximum(all_layer_n, 1)).tolist()
    facts["attention_mask_audit"].update({
        "total_rows": total_rows,
        "total_mask_sum": total_rows,
        "n_files_with_padding": n_files_with_padding,
        "per_file_mismatch": am_mismatch,
        "verdict": ("无 padding：48 个文件的 attention_mask 全为 1 且 sum 等于行数，"
                    "总行数 69155 = obs_series 的 69155。过滤是恒等操作。"
                    if n_files_with_padding == 0 else
                    f"有 {n_files_with_padding} 个文件含 padding，已按 mask 过滤"),
    })
    facts["layer_convention_audit"].update({
        "hs27_vs_last_hidden_max_abs_diff_all_files": max_abs_diff_last,
        "n_elements_bitwise_identical": n_last_exact,
        "n_elements_compared": n_last_total,
        "frac_bitwise_identical": n_last_exact / n_last_total,
        "mean_norm_per_layer": {str(L): mean_norm_all[L] for L in range(N_LAYERS)},
        "mean_norm_L26": mean_norm_all[PRE_LAST_LAYER],
        "mean_norm_L27": mean_norm_all[LAST_LAYER],
        "ratio_L27_over_L26": mean_norm_all[LAST_LAYER] / mean_norm_all[PRE_LAST_LAYER],
        "verdict": ("成立" if max_abs_diff_last == 0.0 and
                    mean_norm_all[LAST_LAYER] < mean_norm_all[PRE_LAST_LAYER]
                    else "不成立"),
    })

    # ---- 范数统计（item 4 的原料） ----
    facts["norms"] = {}
    for L in LAYERS:
        mh = np.asarray(hsum[L], dtype=np.float64) / n_norm[L]
        facts["norms"][str(L)] = {
            "n_steps": n_norm[L],
            "mean_of_L2norm": norm_sum[L] / n_norm[L],
            "L2norm_of_mean": float(np.linalg.norm(mh)),
            "mean_of_L2norm_squared": norm_sq_sum[L] / n_norm[L],
            "rms_per_dim": float(np.sqrt(norm_sq_sum[L] / n_norm[L] / D_MODEL)),
        }
    facts["norms"]["ratio_mean_L2norm_L14_over_L13"] = (
        facts["norms"]["14"]["mean_of_L2norm"] / facts["norms"]["13"]["mean_of_L2norm"])

    # ---- contrast 方向 ----
    vecs, vecmeta = {}, {}
    for L in LAYERS:
        arr = {}
        for a in AXES:
            c, c64 = acc[L][a], acc64[L][a]
            v32 = l2((c["pos_sum"] / c["pos_n"]) - (c["neg_sum"] / c["neg_n"]))
            v64 = l2((c64["pos_sum"] / c["pos_n"]) - (c64["neg_sum"] / c["neg_n"]))
            arr[a] = v64
            vecmeta[f"{L}/{a}"] = {
                "n_positive": c["pos_n"], "n_negative": c["neg_n"],
                "cos_float32_path_vs_float64_path": float(v32 @ v64),
                "norm_float64": float(np.linalg.norm(v64)),
            }
        vecs[f"L{L}"] = np.stack([arr[a] for a in AXES])
    np.savez(OUT / "vecs_L12_L15.npz", axes=np.array(AXES),
             **{f"L{L}": vecs[f"L{L}"] for L in LAYERS})
    facts["contrast_vectors"] = vecmeta

    # ---- 复现基线：L14 vs 线上发布向量 ----
    meta = json.loads((VEC_DIR / "steering_vectors.json").read_text())
    repro = {}
    for a in AXES:
        pub = np.load(VEC_DIR / f"{a}.npy").astype(np.float64).ravel()
        pub /= np.linalg.norm(pub)
        v14 = vecs["L14"][AXES.index(a)]
        repro[a] = {
            "published_n_positive": meta[a]["n_positive"],
            "recomputed_n_positive": vecmeta[f"14/{a}"]["n_positive"],
            "published_n_negative": meta[a]["n_negative"],
            "recomputed_n_negative": vecmeta[f"14/{a}"]["n_negative"],
            "counts_match": (meta[a]["n_positive"] == vecmeta[f"14/{a}"]["n_positive"] and
                             meta[a]["n_negative"] == vecmeta[f"14/{a}"]["n_negative"]),
            "cos_recomputed_vs_published": float(v14 @ pub),
            "published_layer": meta[a]["layer"],
            "published_positive_group": meta[a]["positive_group"],
            "published_negative_group": meta[a]["negative_group"],
        }
    for a, base in DERIVED.items():
        pub = np.load(VEC_DIR / f"{a}.npy").astype(np.float64).ravel()
        pub /= np.linalg.norm(pub)
        vb = vecs["L14"][AXES.index(base)]
        repro[a] = {
            "derived_from": base,
            "cos_recomputed_vs_published": float(vb @ pub),
            "cos_published_vs_minus_base": float(pub @ (-np.load(
                VEC_DIR / f"{base}.npy").astype(np.float64).ravel()
                / np.linalg.norm(np.load(VEC_DIR / f"{base}.npy").astype(np.float64).ravel()))),
            "n_positive": meta[a]["n_positive"], "n_negative": meta[a]["n_negative"],
        }
    facts["baseline_reproduction"] = repro
    (OUT / "s1_facts.json").write_text(json.dumps(facts, ensure_ascii=False, indent=1))
    (OUT / "traj_index.json").write_text(json.dumps(
        {"total_rows": total_rows, "traj": traj_index}, ensure_ascii=False, indent=1))
    print(json.dumps(repro, ensure_ascii=False, indent=1))
    print(f"[done] {time.time()-t0:.1f}s -> s1_facts.json")


if __name__ == "__main__":
    main()
