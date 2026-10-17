#!/usr/bin/env python
"""Measure dot_marker_mean on CPU, from the shipped w vector (revision 244.12).

Why:
  d_L20 = alpha * dot_marker_mean / attenuation has been carried through
  revisions 197/200/201/206 as a first-order PREDICTION, and it is the assumed
  observand in every SNR figure quoted for this project (SNR 2.07, 3.81 ...).
  The value in use is a HARD-CODED constant in p6_resolvability.py:

      "new_p2a": {"dot_marker_mean": 0.043172, "class_gap": 113.474}

  ⛔ Nobody re-measured it against the vector that actually ships
  (/tmp/w_p2a.npy).  That is the same defect class as the n_eff backfill in
  244.5: a number carried forward whose provenance was never checked against
  the current artifact.

This measures it for real, on CPU, no GPU needed:
  dot_marker_mean = mean over MARKER_IDS of ( w . U[marker] )
  U = lm_head.weight, read lazily with safetensors.safe_open so only that one
  tensor is loaded (not the whole ~3.4 GB checkpoint).

⚠⚠ Two precisions are reported, deliberately.
  The original measurement loaded the model with torch_dtype=bfloat16, so U was
  bf16 and the dot product carried bf16 rounding.  dot_marker_mean ~ 0.043 is
  exactly the magnitude where bf16 (~3 significant decimal digits) can move the
  result by a few percent -- and every SNR in the ledger is quoted to 2-3
  significant figures off this constant.  Reporting only one precision would
  hide that; reporting both makes the size of the rounding explicit.

⚠ What this does NOT establish:
  - that 0.5 (pos_frac) selects the right position
  - that d_L20 is the true group-level effect; it remains a first-order
    prediction at one calibration point
  - agreement with the hardcoded constant proves the constant is not stale,
    NOT that it is right in some deeper sense

Exit: 0 measured and compared; 2 precondition failure.
"""
import json
import os
import sys

import numpy as np

MODEL_DIR = "/home/zhourui/.cache/huggingface/models/Qwen--Qwen3-1.7B/snapshots/master"
W_NPY = "/tmp/w_p2a.npy"
W_META = "/tmp/w_p2a.npy.json"
HARDCODED = 0.043172          # as found in p6_resolvability.py
HARDCODED_CLASS_GAP = 113.474
MARKER_IDS = [13824, 14190, 6771, 10061, 7196, 88190, 80022]
CONTROL_ID = 279
ATTENUATION = 40.0             # d_L20 = d_calib / 40


def find_tensor_dir():
    """Locate the safetensors shard holding lm_head.weight, and the index."""
    idx_path = os.path.join(MODEL_DIR, "model.safetensors.index.json")
    shards = []
    if os.path.isfile(idx_path):
        wm = json.load(open(idx_path, encoding="utf-8")).get("weight_map", {})
        if "lm_head.weight" in wm:
            shards.append(wm["lm_head.weight"])
        else:
            # tied embeddings: fall back to the embedding tensor
            for k in ("model.embed_tokens.weight",):
                if k in wm:
                    shards.append(wm[k])
        if not shards:
            shards = sorted({v for v in wm.values()})
    if not shards:
        single = os.path.join(MODEL_DIR, "model.safetensors")
        if os.path.isfile(single):
            shards = [single]
    if not shards:
        raise SystemExit("PRECOND_FAIL: 找不到 safetensors 分片")
    return [os.path.join(MODEL_DIR, s) for s in shards]


def main():
    if not os.path.isfile(W_NPY):
        print("PRECOND_FAIL: %s 不存在" % W_NPY)
        return 2
    shards = find_tensor_dir()
    for s in shards:
        if not os.path.isfile(s):
            print("PRECOND_FAIL: 分片不存在 %s" % s)
            return 2

    import torch
    from safetensors import safe_open

    w = np.load(W_NPY).astype(np.float64)
    print("w: shape=%s norm=%.6f" % (w.shape, np.linalg.norm(w)))
    if os.path.isfile(W_META):
        meta = json.load(open(W_META, encoding="utf-8"))
        print("w meta: class_gap=%r w_norm=%r layer=%r"
              % (meta.get("class_gap"), meta.get("w_norm"), meta.get("layer")))

    results = {}
    for path in shards:
        with safe_open(path, framework="pt") as f:
            keys = list(f.keys())
            key = ("lm_head.weight" if "lm_head.weight" in keys
                   else "model.embed_tokens.weight")
            if key not in keys:
                print("PRECOND_FAIL: 分片里既无 lm_head.weight 亦无 "
                      "model.embed_tokens.weight；keys 头部 %r" % keys[:5])
                return 2
            for dt_name, dt in (("fp32", torch.float32),
                                ("bf16", torch.bfloat16)):
                if dt is torch.bfloat16 and key != "lm_head.weight":
                    # embedding may be stored fp32; converting to bf16 is what
                    # the original did anyway, so keep the comparison honest.
                    pass
                U = f.get_tensor(key).to(dt)
                rows = U[[CONTROL_ID] + MARKER_IDS].double().numpy()
                dots = rows @ w
                marker = dots[1:]
                results[dt_name] = {
                    "mean": float(marker.mean()),
                    "min": float(marker.min()),
                    "all": [float(x) for x in marker],
                    "control": float(dots[0]),
                    "n_pos": int((marker > 0).sum()),
                }
                del U, rows, dots

    for dt_name in ("fp32", "bf16"):
        r = results[dt_name]
        gap = HARDCODED_CLASS_GAP
        d_calib = 1.0 * gap * r["mean"]
        d_l20 = d_calib / ATTENUATION
        print("")
        print("[%s]" % dt_name)
        print("  w.U[control=' the '] = %+.6f" % r["control"])
        print("  w.U[marker] 逐 id   = "
              + ", ".join("%+.5f" % x for x in r["all"]))
        print("  dot_marker_mean      = %+.6f   (min %+.6f, 为正 %d/%d)"
              % (r["mean"], r["min"], r["n_pos"], len(MARKER_IDS)))
        print("  => d_calib = alpha*mean = %+.4f" % d_calib)
        print("  => d_L20   = d_calib/40 = %+.4f" % d_l20)

    fp32_mean = results["fp32"]["mean"]
    bf16_mean = results["bf16"]["mean"]
    rel = (bf16_mean - fp32_mean) / fp32_mean if fp32_mean else float("nan")
    print("")
    print("与写死常量 %.6f 的对比：" % HARDCODED)
    print("  fp32 实测 %+.6f   相对差 %+.2f%%"
          % (fp32_mean, (fp32_mean - HARDCODED) / HARDCODED * 100.0))
    print("  bf16 实测 %+.6f   相对差 %+.2f%%"
          % (bf16_mean, (bf16_mean - HARDCODED) / HARDCODED * 100.0))
    print("  bf16 与 fp32 相差 %+.2f%%  => 精度选择本身带来的偏移" % (rel * 100.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
