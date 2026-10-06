#!/usr/bin/env python3
"""逐步推理路径：t=0..k 每一步，两条流各自的 top-8 候选词与分差。

⚠ 这份产物补的是什么
   已发货的 `divergence_readout.json` 只在**分叉那一步**给候选词（5 个读出层 ×
   top-8），前面 k 步只给了一条 sparkline 用的 margin 标量。读者能看见"差距变小"，
   却**核不了是哪一步、也不看不见每步的两条流各自在考虑哪几个词**。
   而「模型到底按什么路径推理」这个问题，缺的正是这个逐步视图。

⚠⚠ 数据从哪来：不是重跑模型
   `.cache/analysis/paired_v2/pair_*.npz` 里已经存了两条臂的
   `*_top_ids (128,8)` / `*_top_logits (128,8)` —— 每一步、每臂、top-8。
   三份 `paired_*`（`paired_v2` / `paired_fp32` / `paired_l28`）的 `control_ids`
   前 10 项逐位相同 ⇒ 同一次运行，只有 v2 存了 top-8。**零模型、零 GPU。**

   选它而不是重跑的理由是可核：已发货产物的 `c_id/s_id` 必须与本产物
   `steps[k].c.ids[0] / steps[k].s.ids[0]` 逐位相同。这条不成立就整份作废。

⚠⚠⚠ 判决规则（取数前写死，不许事后改）
   R1 前缀共享：`control_ids[:k] == steered_ids[:k]` 必须 6/6 成立。
      不成立 ⇒ 两条流在第 k 步之前就分过，"分叉步"这个词整个是假的。
   R2 身份对齐：`steps[k].c.ids[0] == divergence_readout.problems[pid].c_id`
      （s 同）。必须 6/6。R1 过了但 R2 没过 ⇒ 索引口径错位，不是模型行为。
   R3 候选宽度：每步每臂必须恰好 8 个候选。少一个就 assert 崩，
      **不许**用不足 8 个的列表算 Jaccard —— 宽度不同 Jaccard 不可比。
   R4 交叉排名：分叉步上"对方臂的第一名"在本臂 top-8 里的名次（1 起）。
      找不到就写 `null` 并把该题计入"未交叉"，**不许**当成 0 或当成 8。
   R5 判决「纯名次互换」：该题 R4 两边都 ≤ 2 且都非 null。
      只有满足这条才能说"干预没有创造新词"。

   ⚠⚠ R5 和「名次互换」**不是同一件事**，别混用：
      R5 = 对方第一名在本臂排 ≤2（本轮 5/6，1984 排第 3）。
      R6 名次互换 = 两词在两臂里的**相对先后**反了（本轮 6/6，1984 是 2↔3 互换）。
      1984 两边都真、都为真，但 R5 判它 False。已发货页面只能说 R5 那个口径。

⚠ 一个必须印出来的口径：Jaccard 是在 **top-8** 上算的
   页面另一处（`renderDivergenceReadout`）只显示 top-5，那是**显示宽度**不是
   计算宽度。两个数不能混。本产物 `n_cand` 字段与每个 jaccard 一起落盘。

⚠⚠⚠ 前缀那 133 步的位移**不能**说成"持续推向一个方向"
   实测：中位 −0.559，80 步为负 / 53 步为正，**133/133 步无一为零**。
   方向有涨有落，但每一步都真的改了打分（|位移| 均值 2.003）。
   而同一步自身的决胜间距中位 14.728 —— 位移只有它的 12%。
   ⇒ 唯一站得住的说法是「每一步都被改动，但改动始终没跨过决胜线」，
     不是「持续推」也不是「最后一步才生效」。后者是另一个误读。
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
NPZ_DIR = ROOT / ".cache" / "analysis" / "paired_v2"
DIVERGENCE = ROOT / "frontend" / "public" / "latent" / "data" / "divergence_readout.json"
VOCAB = ROOT / "frontend" / "public" / "latent" / "data" / "vocab.json"
OUT = ROOT / "frontend" / "public" / "latent" / "data" / "path_readout.json"

N_CAND = 8          # R3：存全宽，页面按需 slice
PREFIX_TAIL = 24    # 共享前缀的可读尾巴，只为让读者看到"是从哪句话里分出去的"


def r4(x, nd=4):
    """numpy 标量 -> 原生 float。JSON 不认 numpy 类型，硬写会 TypeError。"""
    return None if x is None else round(float(x), nd)


def main() -> int:
    dv = json.loads(DIVERGENCE.read_text())
    voc = json.loads(VOCAB.read_text())
    vocab = voc["ids"] if isinstance(voc, dict) and "ids" in voc else voc

    problems, gates = {}, {"R1_prefix_shared": 0, "R2_id_aligned": 0,
                           "R3_width": 0, "R5_pure_swap": 0, "R6_rank_swapped": 0,
                           "winner_pushed_down": 0, "winner_about_flat": 0}
    total_prefix_steps = 0
    top1_same_steps = 0
    missed = []
    prefix_shift, prefix_margin = [], []

    for pid, q in sorted(dv["problems"].items()):
        npz_path = NPZ_DIR / f"pair_{pid}.npz"
        if not npz_path.exists():
            print(f"FATAL 缺 npz: {npz_path}", file=sys.stderr)
            return 2
        z = np.load(npz_path, allow_pickle=True)
        for key in ("control_ids", "steered_ids", "control_top_ids",
                    "control_top_logits", "steered_top_ids", "steered_top_logits"):
            if key not in z.files:
                print(f"FATAL {pid} 缺键 {key}", file=sys.stderr)
                return 2

        c_ids, s_ids = z["control_ids"], z["steered_ids"]
        c_ti, s_ti = z["control_top_ids"], z["steered_top_ids"]
        c_tl, s_tl = z["control_top_logits"], z["steered_top_logits"]
        k = int(q["k"])

        # R3 宽度闸：宽度不齐就崩，不许拿不等宽的列表继续算
        for arr, name in ((c_ti, "control_top_ids"), (s_ti, "steered_top_ids"),
                          (c_tl, "control_top_logits"), (s_tl, "steered_top_logits")):
            if arr.shape[0] <= k or arr.shape[1] != N_CAND:
                print(f"FATAL {pid} {name} 形状 {arr.shape} 与 (>{k}, {N_CAND}) 不符",
                      file=sys.stderr)
                return 2
        gates["R3_width"] += 1

        # R1 前缀共享
        if not np.array_equal(c_ids[:k], s_ids[:k]):
            print(f"FAIL R1 {pid}: control_ids[:{k}] != steered_ids[:{k}]", file=sys.stderr)
            return 3
        gates["R1_prefix_shared"] += 1

        # R2 身份对齐（拿已发货产物当外部参照，不拿自己当参照）
        if int(c_ti[k][0]) != int(q["c_id"]) or int(s_ti[k][0]) != int(q["s_id"]):
            print(f"FAIL R2 {pid}: npz 头名 {int(c_ti[k][0])}/{int(s_ti[k][0])} "
                  f"vs 已发货 {q['c_id']}/{q['s_id']}", file=sys.stderr)
            return 3
        gates["R2_id_aligned"] += 1

        steps, jac_all, same_n = [], [], 0
        for t in range(k + 1):
            ci = [int(x) for x in c_ti[t][:N_CAND]]
            si = [int(x) for x in s_ti[t][:N_CAND]]
            cg = [r4(x) for x in c_tl[t][:N_CAND]]
            sg = [r4(x) for x in s_tl[t][:N_CAND]]
            cs, ss = set(ci), set(si)
            jac = len(cs & ss) / len(cs | ss)
            same1 = ci[0] == si[0]
            if t < k and same1:
                same_n += 1
            jac_all.append(jac)
            steps.append({
                "t": t,
                "same_top1": bool(same1),
                "jaccard": round(jac, 4),
                "m_c": r4(cg[0] - cg[1]),      # 对照臂 top1 减 top2
                "m_s": r4(sg[0] - sg[1]),
                "c": {"ids": ci, "g": cg},
                "s": {"ids": si, "g": sg},
            })
            if t < k and same1:
                # t<k 时 ci[0]==si[0]，共享词就在两臂各自第 1 位；
                # 它的位移 = 干预臂打分 − 对照臂打分。
                # ⚠ 别写成 cg[list(ci).index(si[0])] - cg[0] —— 那样索引恒为 0，位移恒为 0。
                prefix_shift.append(sg[0] - cg[0])
                prefix_margin.append(cg[0] - cg[1])
        total_prefix_steps += k
        top1_same_steps += same_n

        # R4 交叉排名：找不到写 null，不写 0
        c_list = [int(x) for x in c_ti[k][:N_CAND]]
        s_list = [int(x) for x in s_ti[k][:N_CAND]]
        s1_in_c = c_list.index(int(s_ti[k][0])) + 1 if int(s_ti[k][0]) in c_list else None
        c1_in_s = s_list.index(int(c_ti[k][0])) + 1 if int(c_ti[k][0]) in s_list else None
        if s1_in_c is None or c1_in_s is None:
            missed.append(pid)
        # R5
        pure = s1_in_c is not None and c1_in_s is not None and s1_in_c <= 2 and c1_in_s <= 2
        if pure:
            gates["R5_pure_swap"] += 1

        # R6 名次互换（比 R5 宽：只看两词相对先后有没有反）
        swapped = (
            (c_list.index(int(c_ti[k][0])) < c_list.index(int(s_ti[k][0])))
            != (s_list.index(int(c_ti[k][0])) < s_list.index(int(s_ti[k][0])))
        )
        if swapped:
            gates["R6_rank_swapped"] += 1

        # 分叉步的机制量：两个竞争词各自被推了多少。
        # ⚠⚠ 这里**只报两个位移 + 一个净间距，不做三型分类**。
        #    6 个点分三型，统计撑不住，阈值挪 0.1 就有题跨界（1987 的 |d_down|=0.85
        #    恰好卡在 1.0 边上）。硬分型会把一个真实但脆的观察包装成结论。
        #    站得住的只有一条：两词的**净间距**被拉开了多少（d_up − d_down，恒正）。
        c_g_full = [float(x) for x in c_tl[k][:N_CAND]]
        s_g_full = [float(x) for x in s_tl[k][:N_CAND]]
        d_down = r4(s_g_full[s_list.index(int(c_ti[k][0]))] - c_g_full[c_list.index(int(c_ti[k][0]))])
        d_up = r4(s_g_full[0] - c_g_full[c_list.index(int(s_ti[k][0]))])
        gap_widened = r4(d_up - d_down)
        # 二值描述，阈值写死 1.0 分，并把它和 counts 一起落盘，读者能自己重切。
        winner_fell = bool(d_down < -1.0)
        if winner_fell:
            gates["winner_pushed_down"] += 1
        else:
            gates["winner_about_flat"] += 1

        tail_ids = [int(x) for x in c_ids[max(0, k - PREFIX_TAIL):k]]
        problems[pid] = {
            "k": k,
            "n_prefix_steps": k,
            "c_id": int(q["c_id"]),
            "s_id": int(q["s_id"]),
            # 词形不落盘：页面用自己的 vocab 解，跟 divergence_readout 同口径，
            # 免得这里手抄一份、页面再手抄一份，两份漂移没人发现。
            "prefix_tail": "".join(vocab[i] for i in tail_ids),
            "summary": {
                "top1_same_steps": same_n,
                "top1_same_denom": k,
                "jaccard_prefix_mean": round(sum(jac_all[:-1]) / max(1, k), 4) if k else None,
                "jaccard_at_k": round(jac_all[-1], 4),
                "jaccard_min": round(min(jac_all), 4),
                "jaccard_max": round(max(jac_all), 4),
                "s1_in_c_rank": s1_in_c,
                "c1_in_s_rank": c1_in_s,
                "pure_rank_swap": bool(pure),
                "rank_swapped": bool(swapped),
                "decisive_margin_c": r4(c_g_full[0] - c_g_full[1]),
            },
            "mechanism": {
                "winner_shift": d_down,   # 对照臂原本选中的词，被抬/压了多少
                "loser_shift": d_up,     # 干预臂选中的词，被抬/压了多少
                "gap_widened": gap_widened,   # 恒为正时：干预把两词的净间距拉开了多少
                "winner_fell_gt_1pt": winner_fell,
            },
            "steps": steps,
        }

    n = len(problems)
    shift = np.asarray(prefix_shift, dtype=np.float64)
    margin = np.asarray(prefix_margin, dtype=np.float64)
    ratio = np.abs(shift) / margin if margin.size else np.asarray([0.0])
    gaps = [pr["mechanism"]["gap_widened"] for pr in problems.values()]

    print(f"题数 {n}")
    print(f"R1 前缀共享      {gates['R1_prefix_shared']}/{n}")
    print(f"R2 身份对齐      {gates['R2_id_aligned']}/{n}  (对拍已发货 divergence_readout)")
    print(f"R3 候选宽度      {gates['R3_width']}/{n}  (每臂每步 {N_CAND})")
    print(f"R5 纯名次互换    {gates['R5_pure_swap']}/{n}   ← 对方第一名在本臂 ≤2（窄）")
    print(f"R6 名次互换      {gates['R6_rank_swapped']}/{n}   ← 两词相对先后反转（宽）")
    print(f"  其中 赢家被压>1分  {gates['winner_pushed_down']}/{n}   赢家基本没动 {gates['winner_about_flat']}/{n}")
    print(f"前缀 t<k top1 相同步  {top1_same_steps}/{total_prefix_steps}")
    print(f"分叉步净间距拉开      中位 {np.median(gaps):.3f}  范围 {min(gaps):.2f}~{max(gaps):.2f}  全正={all(g > 0 for g in gaps)}")
    print(f"前缀位移          n={shift.size}  中位 {np.median(shift):+.3f}  "
          f"|均值| {np.abs(shift).mean():.3f}  为正 {(shift > 0).sum()} 为负 {(shift < 0).sum()} 为零 {(shift == 0).sum()}")
    print(f"前缀决胜间距      中位 {np.median(margin):.3f}   位移/间距 中位 {np.median(ratio):.4f}  "
          f"<0.25 的步 {(ratio < 0.25).sum()}/{ratio.size}")
    if missed:
        print(f"未交叉（R4 判 null）: {missed}")

    out = {
        "schema": "steer3d.path_readout/1",
        "source": {
            "build": ".cache/xcheck/build_path_readout.py",
            "npz_dir": ".cache/analysis/paired_v2",
            "npz_keys": ["control_ids", "steered_ids", "control_top_ids",
                         "control_top_logits", "steered_top_ids", "steered_top_logits"],
            "cross_checked_against": "frontend/public/latent/data/divergence_readout.json",
            "no_model_run": True,
        },
        "note": ("t=0..k 每一步两条流各自的 top-8 候选词（id）与原始打分。"
                 "i 是 vocab id，页面用自己的 vocab 解词形。"
                 "jaccard 在 top-8 上算，与页面只显示 top-5 那个宽度无关，别混用。"),
        "n_cand": N_CAND,
        "jaccard_caliber": f"top-{N_CAND} 交集/并集，逐 t 计算后再取均值",
        "gates": gates,
        "mechanism_note": ("不把 6 个点分三型：阈值挪 0.1 就有题跨界（1987 的 winner_shift=-0.85 "
                           "恰好卡在 1.0 边上）。只报两个位移与净间距 gap_widened，"
                           "阈值 1.0 写在 winner_fell_gt_1pt 里，读者可自己重切。"),
        "prefix_effect": {
            "n": int(shift.size),
            "shift_median": r4(np.median(shift)),
            "shift_abs_mean": r4(np.abs(shift).mean()),
            "n_pos": int((shift > 0).sum()),
            "n_neg": int((shift < 0).sum()),
            "n_zero": int((shift == 0).sum()),
            "margin_median": r4(np.median(margin)),
            "ratio_median": r4(np.median(ratio)),
            "ratio_below_quarter": int((ratio < 0.25).sum()),
            "reading": ("前缀上注入每一步都真的改了打分（无一为零），但方向有涨有落、"
                        "幅度中位只有该步决胜间距的约 12%。⇒ 能说的只有「每步都被改动，"
                        "但没跨过决胜线」；说成「持续推向一个方向」或「最后一步才生效」都不成立。"),
        },
        "alignment_gate": (f"{gates['R1_prefix_shared']}/{n} prefixes byte-identical up to k; "
                           f"{gates['R2_id_aligned']}/{n} match shipped c_id/s_id; "
                           f"{top1_same_steps}/{total_prefix_steps} shared steps with identical top-1"),
        "cross_rank_missing": missed,
        "problems": problems,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False) + "\n")
    print(f"写出 {OUT.relative_to(ROOT)}  {OUT.stat().st_size/1024:.1f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
