"""扫描**注入层**：把「下游 8 层 block 把方向改了」和「w 本身指错方向」分开。

## 为什么要做这个

已确立的事实：

- 装置几何**是对的**：`logits_at` 注入在 `inj = len(ids)-1`，即绝对位置
  `P+t-1`（预测 marker 的那个位置），读 `logits[-1]`，正是同一位置。
- `w·U[marker] > 0`（`w_real` 7/7 marker 全正，均值 +0.1855；随机基线 0.0264，7×）。
- 但实测注入 `+w` 之后，marker 的 logsumexp **反而下降**（think 上 −0.25 → −1.25）。

这两条同时为真，只有一个解释候选：`w·U` **假设 layer 20 到 unembedding 是恒等映射**，
而中间还隔着 Qwen3-1.7B 的 block 21–28。真实的效应是
`Δlogit ≈ α·wᵀ·G·U`，`G` 是那 8 层在扰动点处的雅可比；测得的 `w·U` 只是 `G=I` 的特例。

## 判据（取数前写死，**不改**）

  L1 **校准点**：在最后一层 `model.norm` **之后、lm_head 之前**注入（LAYER=-1），
     下游无任何变换，此时一阶预测 `Δlogit = α·(w·W_eff)` 应当**精确成立**
     （`W_eff` = `lm_head.weight * model.norm.weight`，因为 RMSNorm 的 γ 乘在通道上）。
     量级对不上 ⇒ 是 unembedding 数学或 γ 没算对，**先修这个**，别的都别谈。
  L2 层阶梯：对每个注入层报 `Δ = lse(lg[marker]) - lse(base[marker])`，
     以及单个 marker token 的 logit 差。
  L3 若 L=20 的符号与 L=−1 相反 ⇒ 方向是**被下游 block 翻掉的**，
     不是 w 指错；这与「位置判别方向 ≠ token 方向」是**不同**的结论。
  L4 报 `w·ĥ`、`cos(w,ĥ)`、`||h||`（注入点在 layer 20 的残差流），
     用来判断 RMSNorm 归一化项 `−(Δrms/rms)·(h·W_eff)` 能不能吃掉整个效应。
  L5 **本脚本只测量，不判决通过与否**；不调 α、不调剂量求绿。

## 为什么 L=−1 是干净的

Qwen3 的前向末尾是 `lm_head(model.norm(h_final))`。
把 forward pre-hook 挂在 `model.norm` 上、在它的**输出**上加 `α·w`，
则该向量原封不动进 lm_head，于是 `logit_j = (h+αw)·W_eff_j`，
一阶（其实是精确线性）预测成立。中间没有任何 block。
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

# 与 r6_rerun.py 同源；本脚本 import 它的常量，避免复制漂移
import importlib.util

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("r6run", _HERE / "r6_rerun.py")
R6 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R6)
MARKER_IDS = R6.MARKER_IDS
CONTROL_ID = R6.CONTROL_ID

LAYER_LADDER = [-1, 0, 4, 8, 12, 16, 20, 24, 26, 27]


def lse(v):
    v = v.detach().float().cpu().numpy()
    v = np.asarray(v, dtype=np.float64)
    m = float(v.max())
    return m + float(np.log(np.exp(v - m).sum()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--npz-dir", required=True)
    ap.add_argument("--sidecar-dir", required=True)
    ap.add_argument("--w", required=True)
    ap.add_argument("--w-meta", default=None, help="w 的 .json（取 class_gap）")
    ap.add_argument("--sites", nargs="+", required=True,
                    help="tid:t 形式，取该轨迹的第一个被抽样 marker")
    ap.add_argument("--rel", type=float, default=1.0, help="相对 class_gap 的倍数")
    ap.add_argument("--out", required=True)
    ap.add_argument("--gpu-uuid", default=None)
    a = ap.parse_args()

    if a.gpu_uuid:
        os.environ["CUDA_VISIBLE_DEVICES"] = f"GPU-{a.gpu_uuid}"
    # 必须在 import torch 之后、模型加载之前设 —— 上面的 import 已经发生，
    # 所以这里只做提示，真跑请用外部 export CUDA_VISIBLE_DEVICES。
    torch.set_grad_enabled(False)

    model = AutoModelForCausalLM.from_pretrained(
        a.model, dtype=torch.bfloat16).to("cuda:0").eval()
    tok = AutoTokenizer.from_pretrained(a.model)
    n_layer = model.config.num_hidden_layers
    print(f"层数 {n_layer}  hidden {model.config.hidden_size}")

    W = np.load(a.w).astype(np.float32)
    wn = float(np.linalg.norm(W))
    W = W / (wn + 1e-12)

    gap = 375.0
    if a.w_meta and os.path.exists(a.w_meta):
        gap = float(json.load(open(a.w_meta, encoding="utf-8")).get("class_gap") or gap)
    alpha = a.rel * gap
    print(f"|w| 原值 {wn:.4f}（已归一）  class_gap {gap:.3f}  rel {a.rel}  => alpha {alpha:.3f}")

    # 在 L=-1 注入时，向量落在**过了最终 RMSNorm** 的空间里，
    # 下游只剩 lm_head，而 Qwen3-1.7B 的 lm_head 与 embed_tokens **逐位相同**（tied）。
    # ⇒ 有效 unembedding 就是 `lm_head.weight` 本身，**不乘 γ**。
    # （这一点是实测的，不是推的：j2_formula_probe.py 试了四个组合，
    #   `h@lm` 中位误差 0.0216，凡经过 RMSNorm 的组合差 10~270。
    #   原因：HF 的 all_hidden_states **末项已经是 norm 之后**的值，
    #   而 npz 把它当成了「最后一层残差」。)
    U = model.lm_head.weight.detach().float()
    tied = bool(torch.equal(model.lm_head.weight,
                            model.get_input_embeddings().weight))
    print(f"lm_head 与 embed_tokens 逐位相同 = {tied}")
    W_eff = U.cpu().numpy().astype(np.float64)      # (V, H)，**不乘 γ**
    pred_marker = float(W @ W_eff[MARKER_IDS].mean(axis=0))
    pred_ctl = float(W @ W_eff[CONTROL_ID])
    print(f"L1 一阶预测 α·(w·lm_head[marker均值]) = {alpha*pred_marker:+.4f}"
          f"   （w·lm_head = {pred_marker:+.6f}）")
    print(f"    α·(w·lm_head[' the ']) = {alpha*pred_ctl:+.4f}")

    mk = torch.tensor(MARKER_IDS, device="cuda:0")
    ctl = torch.tensor([CONTROL_ID], device="cuda:0")

    def fwd(ids, vec, alpha_, layer):
        """在 layer 注入。layer=-1 表示**最后一层 RMSNorm 之后、lm_head 之前**。

        ⚠ 这两种 hook 完全不同，踩过：
        - `register_forward_pre_hook` 收到的是模块的**输入**（norm 之前的残差），
          那跟 layer 27 所在的 hs 是**同一个空间**，根本不是「之后」；
        - 要改 norm 的**输出**，必须用 `register_forward_hook`（签名
          `(module, inputs, output)`），在 output 上加。
        少了这一步，校准点就不在校准点上，整条阶梯的解读全部作废。
        """
        inj = ids.shape[0] - 1

        def add(h):
            v = torch.as_tensor(vec, dtype=h.dtype, device=h.device)
            h = h.clone()
            h[:, inj, :] = h[:, inj, :] + alpha_ * v
            return h

        if layer == -1:
            def post_hook(mod, inp, out):      # 改 norm 的**输出**
                return add(out)
            hd = model.model.norm.register_forward_hook(post_hook)
        else:
            def pre_hook(mod, inp):            # 改 block 的**输入**
                return (add(inp[0]),) + tuple(inp[1:])
            hd = model.model.layers[layer].register_forward_pre_hook(pre_hook)
        try:
            o = model(input_ids=ids.view(1, -1), use_cache=False, return_dict=True)
        finally:
            hd.remove()
        return o.logits[0, -1].float()

    rows = []
    for spec in a.sites:
        tid, t = spec.rsplit(":", 1)
        t = int(t)
        z = np.load(os.path.join(a.npz_dir, tid + ".npz"))
        gen = z["token_ids"].tolist()
        if "hidden_states" in z:
            # 用 NPZ_LAYER（= LAYER-1），不是 LAYER：npz[k] == hs[k+1]，
            # 而注入动的是 hs[LAYER]。写成 LAYER 会读到 block LAYER 的**输出**，
            # 也就是注入点的下一层 —— 那正是 r6_rerun.py 修掉的那个错。
            h20 = z["hidden_states"][R6.NPZ_LAYER][t - 1].astype(np.float64)
            rec_hs_layer = R6.NPZ_LAYER
        else:
            h20, rec_hs_layer = None, None
        z.close()
        cti = json.load(open(Path(a.sidecar_dir) / f"{tid}.json", encoding="utf-8"))
        pid = tok(cti["chat_template_input"], return_tensors="pt",
                  add_special_tokens=False).input_ids[0].tolist()
        P = (cti.get("extra") or {}).get("prompt_tokens")
        ids = torch.tensor(pid + gen, dtype=torch.long, device="cuda:0")
        up = ids[: P + t]
        mode = cti["config"]["mode"]
        real_tok = gen[t] if t < len(gen) else 0

        print(f"\n=== {tid}  mode={mode}  t={t}  n_tok={cti['n_generated_tokens']} ===")
        rec = {"traj": tid, "mode": mode, "t": t, "n_tok": cti["n_generated_tokens"],
               "alpha": alpha, "rel": a.rel, "class_gap": gap,
               "npz_layer_read": rec_hs_layer, "inject_hs_index": R6.LAYER,
               "pred_marker_lse": None, "layers": {}}

        base = fwd(up, W, 0.0, R6.LAYER)
        b_mark, b_ctl = lse(base[mk]), lse(base[ctl])
        b_real = float(base[real_tok])

        if h20 is not None:
            # L4 只是**描述性诊断**，不是预测。
            # 原先这里估过一个「RMSNorm 归一化项」把效应吃掉多少，那个式子
            # 把 layer 20 的残差当成了最终 norm 的输入 —— 两件事。
            # 注入之后还要过 block 21–28 与 model.norm，任何单点线性估计都不成立；
            # 真正的量就是下面那条逐层实测曲线。
            hn = float(np.linalg.norm(h20))
            rec["h20_norm"] = round(hn, 3)
            rec["w_dot_hhat"] = round(float(W @ (h20 / hn)), 6)
            rec["w_dot_h"] = round(float(W @ h20), 3)
            rec["rel_perturbation"] = round(alpha / hn, 4)   # ||Δh|| / ||h||
            h1 = h20 + alpha * W.astype(np.float64)
            rec["rms_ratio"] = round(
                float(np.linalg.norm(h1)) / hn, 5)
            print(f"L4 ||hs[{R6.LAYER}]||={rec['h20_norm']}  "
                  f"w·ĥ={rec['w_dot_hhat']:+.6f}  w·h={rec['w_dot_h']:+.3f}")
            print(f"    ||Δh||/||h|| = {rec['rel_perturbation']:.4f}"
                  f"   范数比 {rec['rms_ratio']}")
            if abs(rec["w_dot_hhat"]) < 0.05:
                print(f"    ⚠ w 与该处激活近乎正交（|w·ĥ|<0.05）："
                      f"注入方向几乎不改变残差的方向，只改范数。")

        for L in LAYER_LADDER:
            if L != -1 and L >= n_layer:
                continue
            lg = fwd(up, W, alpha, L)
            d_lse = lse(lg[mk]) - b_mark
            d_real = float(lg[real_tok]) - b_real
            d_ctl = lse(lg[ctl]) - b_ctl
            rec["layers"][str(L)] = {
                "d_marker_lse": round(d_lse, 4),
                "d_real_token": round(d_real, 4),
                "d_control": round(d_ctl, 4)}
            tag = "norm后/lm_head前" if L == -1 else f"block{L}"
            print(f"  L={L:3d} {tag:18s} Δmarker_lse={d_lse:+8.4f}"
                  f"  Δ真实token={d_real:+8.4f}  Δ' the '={d_ctl:+8.4f}")

        cal = rec["layers"].get("-1", {}).get("d_marker_lse")
        rec["pred_marker_lse"] = round(alpha * pred_marker, 4)
        if cal is not None:
            rec["calibration_ratio"] = round(cal / (alpha * pred_marker), 4) \
                if abs(alpha * pred_marker) > 1e-9 else None
            print(f"  L1 校准：实测 {cal:+.4f}  预测 {rec['pred_marker_lse']:+.4f}"
                  f"  比值 {rec['calibration_ratio']}")
        rows.append(rec)

    json.dump({"alpha": alpha, "rel": a.rel, "class_gap": gap,
               "w_norm_raw": wn, "n_layer": n_layer,
               "layer_ladder": LAYER_LADDER,
               "pred_w_dot_Weff_marker": pred_marker,
               "rows": rows},
              open(a.out, "w"), ensure_ascii=False, indent=1)
    print("\n写出", a.out, "（L5 只测量，不判决）")


if __name__ == "__main__":
    main()
