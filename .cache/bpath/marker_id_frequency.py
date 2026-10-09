"""marker 七个 id 的**实际出现频次** × `w·U` 逐条对照。

## 为什么必须有这个

`w_unembed_align.py` 报的是 `w·U[marker]` 的**七个 id 的均值**。
本轮实测发现这个量**会把符号分裂掩盖掉**：

    w_t1 (H[t-1]) 的逐 id 点积
      13824 −0.01321   14190 −0.03890   6771 +0.02454
      10061 −0.00657   7196 +0.15583   88190 +0.05960   80022 +0.04083
    均值 = +0.03173（看着是正的）

可实测注入 `+w` 之后，**实际生成的那个 marker token 的 logit 是 −1.00**
（校准点 `L=-1` 上无下游变换，`Δlogit = α·(w·lm_head[real_tok])` 是**精确**的，
反解得 `w·U[real_tok] = −0.0058`，正落在上面那几个弱负的 id 里）。

原因：P9 读的是 `lse(lg[MARKER_IDS])`，即**七个 id 的 logsumexp**。
它的一阶变化近似是 `Σ_j p_j · α·(w·U[j])`，
**起决定作用的是当前概率最高的那一个**，不是七个的算术均值。

⇒ 「对 marker 类平均为正」**不等于**「对实际出现的 marker 为正」。
本脚本把频次和点积摆在一起，让这条差异看得见。

## 判据（只报，不判决）

  F1 七个 id 各自的语料频次
  F2 每个 id 的 `w·U`
  F3 **频次加权**的 `w·U`（按频次加权，不是算术均值）
  F4 高频 id（累计占比 ≥ 80%）里**有没有负的**——有就要点名
  F5 只测量，不判决通过与否
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np

MARKER_IDS = [13824, 14190, 6771, 10061, 7196, 88190, 80022]


def read_marker_freq(sidecar_dir):
    """统计七个 marker id 在全语料（只数生成段）里各出现多少次。"""
    cnt = Counter()
    n_traj = 0
    for f in sorted(Path(sidecar_dir).glob("*.json")):
        j = json.load(open(f, encoding="utf-8"))
        toks = j.get("tokens") or []
        # `tokens` 是生成段；与 npz 的 n_generated_tokens 一致（coord_triple_check 24/24）
        if len(toks) != j.get("n_generated_tokens"):
            continue
        n_traj += 1
        for t in toks:
            if t["token_id"] in MARKER_IDS:
                cnt[t["token_id"]] += 1
    return cnt, n_traj


def _load_unembedding(model_dir):
    """只按切片读 lm_head.weight，不实例化整个 1.7B。

    ⚠ 必须用 framework="pt"：numpy 后端读不了 bfloat16（TypeError）。
    ⚠ **不乘 RMSNorm 的 γ**。npz 的最后一层已经是 norm 之后的值
       （j2_formula_probe.py 四组合实测：`h@lm` 中位误差 0.0216，
        凡经过 RMSNorm 的组合都差 10~270）。这里要的是同一套口径。
    """
    import torch
    from safetensors import safe_open
    w = None
    for c in sorted(Path(model_dir).glob("*.safetensors")):
        with safe_open(str(c), framework="pt") as f:
            for k in list(f.keys()):
                if k.endswith("lm_head.weight"):
                    w = f.get_tensor(k).to(torch.float32).numpy()
        if w is not None:
            break
    if w is None:
        raise SystemExit("**没找到 lm_head.weight**")
    return w.astype(np.float64)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True,
                    help="模型目录（按切片从 safetensors 读 lm_head，不实例化 1.7B）")
    ap.add_argument("--sidecar-dir", required=True)
    ap.add_argument("--w-json", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--top-share", type=float, default=0.8,
                    help="F4 里「高频」的累计占比阈值")
    a = ap.parse_args()

    U = _load_unembedding(a.model)
    print(f"unembedding {U.shape}")

    cnt, n_traj = read_marker_freq(a.sidecar_dir)
    total = sum(cnt.values())
    print(f"语料 {n_traj} 条轨迹，marker 总出现 {total} 次")
    if total == 0:
        print("**一个 marker 都没找到，频次诊断用不了**"); sys.exit(2)

    # 按频次降序
    order = sorted(MARKER_IDS, key=lambda i: -cnt.get(i, 0))
    ws = json.load(open(a.w_json, encoding="utf-8"))
    print("\n频次降序：" + "  ".join(f"{i}:{cnt.get(i,0)}" for i in order))

    rows = {}
    for name, path in ws.items():
        w = np.load(path).astype(np.float32)
        w = w / (np.linalg.norm(w) + 1e-12)
        dots = {int(i): float(w @ U[i]) for i in MARKER_IDS}
        freq = {int(i): int(cnt.get(i, 0)) for i in MARKER_IDS}
        fmean = sum(dots[i] * freq[i] for i in MARKER_IDS) / total
        # 高频集合：累计占比 >= top-share
        acc, hot = 0, []
        for i in order:
            hot.append(i)
            acc += freq[i]
            if acc / total >= a.top_share:
                break
        hot_share = sum(freq[i] for i in hot) / total
        neg_hot = [i for i in hot if dots[i] < 0]
        rows[name] = {"dots": dots, "freq": freq, "freq_weighted_dot": fmean,
                      "hot_ids": hot, "hot_share": round(hot_share, 4),
                      "neg_in_hot": neg_hot}
        print(f"\n  [{name}]")
        for i in order:
            flag = ""
            if i in neg_hot:
                flag = "  <-- 高频且**负**"
            print(f"    id {i:6d}  频次 {freq[i]:5d} ({freq[i]/total:5.1%})"
                  f"  w·U {dots[i]:+9.5f}{flag}")
        print(f"    算术均值   {sum(dots.values())/7:+9.5f}"
              f"   （w_unembed_align 报的就是这个）")
        print(f"    频次加权   {fmean:+9.5f}   <-- 才是 logsumexp 的一阶权重")
        print(f"    高频集合（累计 {hot_share:.1%}）里为负的 id："
              f"{neg_hot if neg_hot else '无'}")

    json.dump({"n_traj": n_traj, "total_markers": total,
               "top_share": a.top_share, "rows": rows},
              open(a.out, "w"), ensure_ascii=False, indent=1)
    print("\n写出", a.out, "（F5 只测量，不判决）")


if __name__ == "__main__":
    import sys
    sys.exit(main())