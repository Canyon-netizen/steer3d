#!/usr/bin/env python3
"""独立重算校验 path_readout.json —— **不复用生成器的任何函数**。

⚠ 为什么必须另写一份
   生成器算完的数再由生成器自己核对，等于没核。这份脚本只依赖
   `numpy` + `json`，把关键量从 npz **重新实现一遍**，再和落盘 JSON 逐位比。
   两份实现写岔了才会红；只有一份时，红的唯一来源是生成器自己崩。

⚠ 它验什么（每条都有可变的红侧）
   C1 逐题 k 与已发货 divergence_readout 一致
   C2 每题 steps 长度 == k+1，且 t 是 0..k 连续无洞
   C3 逐步 m_c / m_s / jaccard / same_top1 独立重算后逐位吻合
   C4 交叉名次 s1_in_c_rank / c1_in_s_rank 独立重算后吻合
   C5 prefix_tail 独立拼接后逐字吻合
   C6 三条判决规则 R1/R2/R5 独立重跑，计数吻合
   C7 汇总口径：top1_same_steps 与 n_prefix_steps 独立累加后吻合
   C8 身份检查：落盘 pure_rank_swap 与重算逐题一致（**与 C6 的数量检查分开**）
   C9 R6 名次互换 + 分叉步两词位移 + 净间距，独立重算
   C10 prefix_effect 七项独立重算（含"无一为零"这条 —— 它是最容易被悄悄改成 0 的）
   C8 负控：把落盘 JSON 的 m_c 全改成 0，必须**判红**（证明 C3 真会变红）

⚠ 变异台（--mutate）：每条检查都要能自己变红，红不了就当它没在工作
   跑法：`python3 independent_recompute_path.py --mutate <字段>`
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
NPZ = ROOT / ".cache" / "analysis" / "paired_v2"
PATH_JSON = ROOT / "frontend" / "public" / "latent" / "data" / "path_readout.json"
DIVERGENCE = ROOT / "frontend" / "public" / "latent" / "data" / "divergence_readout.json"
VOCAB = ROOT / "frontend" / "public" / "latent" / "data" / "vocab.json"

N_CAND = 8
TOL = 1e-3

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))


def load_json(p: pathlib.Path):
    return json.loads(p.read_text())


def main() -> int:
    mutate = None
    for a in sys.argv[1:]:
        if a.startswith("--mutate="):
            mutate = a.split("=", 1)[1]

    prod = load_json(PATH_JSON)
    dv = load_json(DIVERGENCE)
    vocab = load_json(VOCAB)["ids"]

    # --- 变异：污染落盘产物，让检查自己变红 -------------------------------
    if mutate == "m_c_zero":
        for p in prod["problems"].values():
            for st in p["steps"]:
                st["m_c"] = 0.0
    elif mutate == "jaccard_one":
        for p in prod["problems"].values():
            for st in p["steps"]:
                st["jaccard"] = 1.0
    elif mutate == "rank_wrong":
        prod["problems"]["1983_I_1"]["summary"]["s1_in_c_rank"] = 7
    elif mutate == "tail_wrong":
        prod["problems"]["1983_I_1"]["prefix_tail"] = "WRONG"
    elif mutate == "drop_step":
        prod["problems"]["1983_I_1"]["steps"].pop(5)
    elif mutate == "k_wrong":
        prod["problems"]["1983_I_1"]["k"] = 999
    elif mutate == "id_swap":
        prod["problems"]["1983_I_1"]["steps"][27]["c"]["ids"][0] = 12345
    elif mutate == "gates_inflated":
        prod["gates"]["R5_pure_swap"] = 6
    elif mutate == "mech_wrong":
        prod["problems"]["1983_I_1"]["mechanism"]["gap_widened"] = 0.0
    elif mutate == "swap_flag":
        prod["problems"]["1983_I_1"]["summary"]["rank_swapped"] = False
    elif mutate == "prefix_nonzero":
        prod["prefix_effect"]["n_zero"] = 133
    elif mutate == "prefix_ratio":
        prod["prefix_effect"]["ratio_median"] = 0.9
    elif mutate == "r6_inflated":
        prod["gates"]["R6_rank_swapped"] = 6
        prod["gates"]["winner_pushed_down"] = 6
    elif mutate is not None:
        print(f"未知变异 {mutate}", file=sys.stderr)
        return 2

    probs = prod["problems"]
    check("C0 题数", set(probs) == set(dv["problems"]),
          f"产物 {sorted(probs)} vs 已发货 {sorted(dv['problems'])}")

    agg = {"R1": 0, "R2": 0, "R5": 0, "R6": 0, "down": 0, "flat": 0}
    tot_same = tot_den = 0
    all_shift, all_margin = [], []

    for pid in sorted(probs):
        p = probs[pid]
        q = dv["problems"][pid]
        z = np.load(NPZ / f"pair_{pid}.npz", allow_pickle=True)
        ci_all, si_all = z["control_ids"], z["steered_ids"]
        cti, sti = z["control_top_ids"], z["steered_top_ids"]
        ctl, stl = z["control_top_logits"], z["steered_top_logits"]

        # C1
        k = len([1 for t in range(len(ci_all)) if ci_all[t] != si_all[t]]) or len(ci_all)
        first_diff = int(np.argmax(ci_all != si_all)) if (ci_all != si_all).any() else -1
        k_true = first_diff
        check(f"C1 k {pid}", p["k"] == q["k"] == k_true,
              f"产物 {p['k']} 已发货 {q['k']} 重算 {k_true}")

        steps = p["steps"]
        # C2
        check(f"C2 步数 {pid}", len(steps) == k_true + 1 and
              [s["t"] for s in steps] == list(range(k_true + 1)),
              f"len {len(steps)} 应 {k_true + 1}")

        # C3
        bad = []
        for t in range(min(k_true, len(steps) - 1) + 1):
            s = steps[t]
            c_ids = [int(x) for x in cti[t][:N_CAND]]
            s_ids = [int(x) for x in sti[t][:N_CAND]]
            c_g = [float(x) for x in ctl[t][:N_CAND]]
            s_g = [float(x) for x in stl[t][:N_CAND]]
            if s["c"]["ids"] != c_ids or s["s"]["ids"] != s_ids:
                bad.append(f"t{t}:ids")
            if max(abs(a - b) for a, b in zip(s["c"]["g"], c_g)) > TOL or \
               max(abs(a - b) for a, b in zip(s["s"]["g"], s_g)) > TOL:
                bad.append(f"t{t}:g")
            if abs(s["m_c"] - (c_g[0] - c_g[1])) > TOL or abs(s["m_s"] - (s_g[0] - s_g[1])) > TOL:
                bad.append(f"t{t}:margin")
            jac = len(set(c_ids) & set(s_ids)) / len(set(c_ids) | set(s_ids))
            if abs(s["jaccard"] - jac) > TOL:
                bad.append(f"t{t}:jaccard")
            if s["same_top1"] != (c_ids[0] == s_ids[0]):
                bad.append(f"t{t}:same1")
        check(f"C3 逐步量 {pid}", not bad, f"不符 {bad[:6]}")

        # C4
        cl = [int(x) for x in cti[k_true][:N_CAND]]
        sl = [int(x) for x in sti[k_true][:N_CAND]]
        r_sc = cl.index(sl[0]) + 1 if sl[0] in cl else None
        r_cs = sl.index(cl[0]) + 1 if cl[0] in sl else None
        sm = p["summary"]
        check(f"C4 交叉名次 {pid}",
              sm["s1_in_c_rank"] == r_sc and sm["c1_in_s_rank"] == r_cs,
              f"产物 {sm['s1_in_c_rank']}/{sm['c1_in_s_rank']} 重算 {r_sc}/{r_cs}")

        # C5
        tail = "".join(vocab[int(x)] for x in ci_all[max(0, k_true - 24):k_true])
        check(f"C5 前缀尾巴 {pid}", p["prefix_tail"] == tail,
              f"产物 {p['prefix_tail']!r} 重算 {tail!r}")

        # C6
        # R5 重算。⚠ 这里量的是「**重算后确实是纯名次互换的题数**」，
        # 不是「落盘标志与重算一致的题数」—— 后者恒等于题数（本轮 6），
        # 拿它去比 gates.R5_pure_swap（纯互换题数，本轮 5）是在比两个不同的量。
        # 这个错已经犯过一次：判据先报「R5 5 vs 6」红，查下来是**判据错、产物对**。
        # 身份一致性单列为 C8，不混进数量检查。
        recomputed_pure = (r_sc is not None and r_cs is not None
                           and r_sc <= 2 and r_cs <= 2)
        agg["R1"] += int(np.array_equal(ci_all[:k_true], si_all[:k_true]))
        agg["R2"] += int(int(cti[k_true][0]) == int(q["c_id"]) and
                         int(sti[k_true][0]) == int(q["s_id"]))
        agg["R5"] += int(recomputed_pure)
        check(f"C8 pure 标志 {pid}", sm["pure_rank_swap"] == bool(recomputed_pure),
              f"落盘 {sm['pure_rank_swap']} 重算 {bool(recomputed_pure)}")

        # C9 R6 名次互换 + 分叉步两词位移
        rec_swapped = ((cl.index(cl[0]) < cl.index(sl[0])) !=
                       (sl.index(cl[0]) < sl.index(sl[0])))
        agg["R6"] += int(rec_swapped)
        cgl = [float(x) for x in ctl[k_true][:N_CAND]]
        sgl = [float(x) for x in stl[k_true][:N_CAND]]
        r_dn = sgl[sl.index(cl[0])] - cgl[cl.index(cl[0])]
        r_up = sgl[sl.index(sl[0])] - cgl[cl.index(sl[0])]
        mech = p["mechanism"]
        check(f"C9 机制量 {pid}",
              sm["rank_swapped"] == bool(rec_swapped)
              and abs(mech["winner_shift"] - r_dn) < TOL
              and abs(mech["loser_shift"] - r_up) < TOL
              and abs(mech["gap_widened"] - (r_up - r_dn)) < TOL
              and mech["winner_fell_gt_1pt"] == bool(r_dn < -1.0),
              f"落盘 swap={sm['rank_swapped']} down={mech['winner_shift']} up={mech['loser_shift']}"
              f" ｜ 重算 swap={rec_swapped} down={r_dn:.3f} up={r_up:.3f}")
        agg["down"] += int(r_dn < -1.0)
        agg["flat"] += int(not (r_dn < -1.0))

        for t in range(k_true):
            ci_t = [int(x) for x in cti[t][:N_CAND]]
            si_t = [int(x) for x in sti[t][:N_CAND]]
            cg_t = [float(x) for x in ctl[t][:N_CAND]]
            sg_t = [float(x) for x in stl[t][:N_CAND]]
            if ci_t[0] == si_t[0]:
                all_shift.append(sg_t[0] - cg_t[0])
                all_margin.append(cg_t[0] - cg_t[1])

        # C7
        same = sum(1 for t in range(k_true)
                   if int(cti[t][0]) == int(sti[t][0]))
        tot_same += same
        tot_den += k_true
        check(f"C7 汇总 {pid}",
              sm["top1_same_steps"] == same and sm["top1_same_denom"] == k_true,
              f"产物 {sm['top1_same_steps']}/{sm['top1_same_denom']} 重算 {same}/{k_true}")

    g = prod["gates"]
    check("C6 判决规则 R1", g["R1_prefix_shared"] == agg["R1"], f"{g['R1_prefix_shared']} vs {agg['R1']}")
    check("C6 判决规则 R2", g["R2_id_aligned"] == agg["R2"], f"{g['R2_id_aligned']} vs {agg['R2']}")
    check("C6 判决规则 R5", g["R5_pure_swap"] == agg["R5"], f"{g['R5_pure_swap']} vs {agg['R5']}")
    check("C6 判决规则 R6", g["R6_rank_swapped"] == agg["R6"], f"{g['R6_rank_swapped']} vs {agg['R6']}")
    check("C9 赢家被压计数", g["winner_pushed_down"] == agg["down"],
          f"{g['winner_pushed_down']} vs {agg['down']}")
    check("C9 赢家没动计数", g["winner_about_flat"] == agg["flat"],
          f"{g['winner_about_flat']} vs {agg['flat']}")
    check("C7 全局 top1 相同步", f"{tot_same}/{tot_den}" in prod["alignment_gate"],
          f"alignment_gate={prod['alignment_gate']!r} 重算 {tot_same}/{tot_den}")

    # C10 prefix_effect 独立重算
    pe = prod["prefix_effect"]
    sh = np.asarray(all_shift, dtype=np.float64)
    mg = np.asarray(all_margin, dtype=np.float64)
    rt = np.abs(sh) / mg
    exp = {
        "n": int(sh.size),
        "shift_median": round(float(np.median(sh)), 4),
        "shift_abs_mean": round(float(np.abs(sh).mean()), 4),
        "n_pos": int((sh > 0).sum()),
        "n_neg": int((sh < 0).sum()),
        "n_zero": int((sh == 0).sum()),
        "margin_median": round(float(np.median(mg)), 4),
        "ratio_median": round(float(np.median(rt)), 4),
        "ratio_below_quarter": int((rt < 0.25).sum()),
    }
    for key, want in exp.items():
        got = pe[key]
        ok = got == want if isinstance(want, int) else abs(float(got) - float(want)) < TOL
        check(f"C10 prefix.{key}", ok, f"落盘 {got} 重算 {want}")

    red = [r for r in results if not r[1]]
    for name, ok, detail in results:
        if not ok:
            print(f"RED  {name}  {detail}")
    print(f"\n检查 {len(results)} 条：PASS {len(results) - len(red)} / RED {len(red)}"
          + (f"   [变异 {mutate}]" if mutate else ""))
    if not mutate and red:
        return 1
    if mutate and not red:
        print(f"装置故障：变异 {mutate} 没有让任何检查变红 —— 这些检查不会自证")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
