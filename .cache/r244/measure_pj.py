#!/usr/bin/env python
"""Measure the marker's actual p_j at the calibration point (revision 244.19).

Closes the one item 244.13.5 left open. The chain so far:
  244.12  d_L20's input (dot_marker_mean) measured; constant not stale
  244.12.3  but d_L20 uses an UNWEIGHTED mean while the instrument reads
            lse(lg[MARKER_IDS]), whose first-order form is SUM_j p_j*(w.U[j])
            => hard interval [-0.0797, +0.4923] (straddles zero)
  244.13  a corpus-level FREQUENCY proxy gives +0.04519 (+4.7% vs the mean)
          -> but frequency is not probability, and the 4.7% is two opposing
             effects cancelling, not a convergence

What is still missing is p_j itself, at the exact position the probe reads.

Why it is cheap:
  r204_noise_probe.py:433-436  base = forward(W, 0.0); b_mark = lse_t(base[mk])
  and `forward` returns  o.logits[0, -1]  -- the LAST position of ids, where
  ids = (pid + gen)[:P+t], i.e. exactly the injection point `inj`.
  With alpha = 0.0 the residual hook injects zero, so ONE plain forward pass
  gives every p_j. No dose sweep, no injection, one trajectory.

⚠⚠ What this does NOT establish:
  - p_j here is the DISTRIBUTION AT ONE POSITION OF ONE TRAJECTORY. It is not
    the corpus average, and the seven markers' total mass may be tiny.
  - That is exactly why the script also reports the markers' TOTAL PROBABILITY
    MASS. If they carry ~0 of the mass, then no injection can move lse much and
    the whole instrument is bounded by that, whatever d_L20 says.
  - It does not validate pos_frac, the ladder, or the 244 verdict.

Exit: 0 printed; 2 precondition failure.
"""
import argparse
import json
import os
import sys

import numpy as np

MODEL = "/home/zhourui/.cache/huggingface/models/Qwen--Qwen3-1.7B/snapshots/master"
DATA = "/home/zhourui/steer3d_bpath/gen_b2_max32768/aime"
W_NPY = "/tmp/w_p2a.npy"
W_META = "/tmp/w_p2a.npy.json"
MARKER_IDS = [13824, 14190, 6771, 10061, 7196, 88190, 80022]
CONTROL_ID = 279
ATTENUATION = 40.0
# numbers already in the ledger, for side-by-side reporting
MEAN_BASED_DL20 = 0.1225
FREQ_BASED_DL20 = 0.1282
INTERVAL = (-0.0797, 0.4923)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tid", required=True)
    ap.add_argument("--pos-frac", type=float, default=0.5,
                    help="must match the sweep's --pos-frac exactly")
    ap.add_argument("--gpu-uuid", default="",
                    help="informational only; CUDA_VISIBLE_DEVICES is set outside")
    args = ap.parse_args()

    side = os.path.join(DATA, args.tid + ".json")
    npz = os.path.join(DATA, args.tid + ".npz")
    for p in (MODEL, W_NPY, side, npz):
        if not os.path.exists(p):
            print("PRECOND_FAIL: %s missing" % p)
            return 2

    import torch
    from safetensors import safe_open
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(MODEL)
    j = json.load(open(side, encoding="utf-8"))
    cti = j["chat_template_input"]
    pid = tok(cti, add_special_tokens=False).input_ids
    z = np.load(npz)
    gen = z["token_ids"].tolist()
    z.close()

    P = (j.get("extra") or {}).get("prompt_tokens") or len(pid)
    n = len(gen)
    t = max(1, int(n * args.pos_frac))
    ids = (list(pid) + list(gen))[: P + t]
    print("tid=%s  P=%d  n_gen=%d  t=%d  ids_len=%d  inj=%d"
          % (args.tid, P, n, t, len(ids), len(ids) - 1))

    w = np.load(W_NPY).astype(np.float32)
    gap = 1.0
    if os.path.isfile(W_META):
        gap = float(json.load(open(W_META, encoding="utf-8"))["class_gap"])

    model = AutoModelForCausalLM.from_pretrained(
        MODEL, torch_dtype=torch.bfloat16).cuda().eval()
    with torch.no_grad():
        out = model(input_ids=torch.tensor([ids], device="cuda:0"),
                    use_cache=False, return_dict=True)
    logits = out.logits[0, -1].float()          # same position the probe reads
    probs = torch.softmax(logits, dim=-1)

    p_mark = probs[torch.tensor(MARKER_IDS, device=probs.device)].cpu().numpy()
    p_ctl = float(probs[CONTROL_ID])
    mass = float(p_mark.sum())

    shard = os.path.join(MODEL, "model.safetensors.index.json")
    wm = json.load(open(shard, encoding="utf-8"))["weight_map"]
    key = "lm_head.weight" if "lm_head.weight" in wm else "model.embed_tokens.weight"
    with safe_open(os.path.join(MODEL, wm[key]), framework="pt") as f:
        U = f.get_tensor(key).float().cpu().numpy()
    dots = U[MARKER_IDS] @ w.astype(np.float64)
    del U

    weighted = float((p_mark * dots).sum())
    scale = gap / ATTENUATION

    print("")
    print("marker  id      p_j            w.U        p_j*(w.U)")
    for mid, pj, dt in zip(MARKER_IDS, p_mark, dots):
        print("      %6d  %.6e   %+.6f   %+.3e" % (mid, pj, dt, pj * dt))
    print("")
    print("七个 marker 的总概率质量 = %.6e   control(' the ') p = %.6e"
          % (mass, p_ctl))
    print("频次代理给的加权值（244.13）= +0.04519  <- 语料级，不是 p_j")
    print("")
    print("Σ_j p_j·(w·U[j]) = %+.6f" % weighted)
    print("⇒ 这一格上的 d_L20 = (class_gap/40)·Σ p_j(w.U[j]) = %+.4f"
          % (scale * weighted))
    print("")
    print("对照（账本里已有的三个数）:")
    print("  算术均值版        %+.4f" % MEAN_BASED_DL20)
    print("  频次代理版        %+.4f" % FREQ_BASED_DL20)
    print("  硬区间            [%+.4f, %+.4f]" % INTERVAL)
    print("")
    inside = (INTERVAL[0] <= scale * weighted <= INTERVAL[1])
    print("落在硬区间内：%s" % ("是" if inside else "否 ⇒ 有别的地方要查"))
    if mass < 1e-3:
        print("⚠⚠ 七个 marker 的总概率质量只有 %.2e —— 即便注入完美，"
              % mass)
        print("   lse 的位移也上界在这个量级附近。⚠ d_L20 若比它大，"
              "两件事不可能同时为真。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
