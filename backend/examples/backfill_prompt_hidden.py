"""Backfill prompt hidden states into existing trajectories.

For each ``<tid>.json`` + ``<tid>.npz`` pair under ``--root`` that does not
yet contain ``prompt_hidden_states``, this script:

  1. Loads the HF model + tokenizer (matching the model that produced
     the trajectory — verify with ``--verify``).
  2. Re-tokenizes ``meta.chat_template_input`` with
     ``add_special_tokens=False`` (the exact setting used by the
     collectors) and concatenates with the saved gen ``token_ids``.
  3. Runs ONE forward pass over the concatenation with
     ``output_hidden_states=True``.
  4. Slices the prompt portion [:n_prompt] off the per-layer hidden
     states, converts to the on-disk dtype (float32 / float16) and
     writes them back as ``prompt_hidden_states`` /
     ``prompt_last_hidden`` / ``prompt_token_ids`` in the NPZ.
  5. Updates the JSON sidecar: ``n_prompt_tokens`` promoted to
     top-level, ``schema_version`` bumped to v1.1, ``extra.prompt_backfilled``
     set to True.

This is a one-shot tool — re-running it with ``--overwrite`` recomputes.

Usage::

    /home/zhourui/miniconda3/envs/steer3d/bin/python \\
        backend/examples/backfill_prompt_hidden.py \\
        --root datasets/aime_qwen3_1p7b_32k_fp32/aime \\
        --model-path /home/zhourui/.cache/huggingface/models/Qwen--Qwen3-1.7B/snapshots/master \\
        --dtype float32 --verify --limit 5      # sanity check first

    # then without --limit for full backfill

GPU: pin to nvidia-smi index 7 (CUDA_VISIBLE_DEVICES=7) before launch.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# IMPORTANT: same GPU pin as the collector.
os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
os.environ["CUDA_VISIBLE_DEVICES"] = "7"

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from core.standard import TrajectoryDataset, SCHEMA_VERSION  # noqa: E402


# Alignment-gate threshold for --verify.
#
# Measured on 6 pilot trajectories (aime25/aime26, both modes, bfloat16,
# HF-collector data re-forwarded by this script):
#   aligned    0.0226 - 0.0461
#   misaligned 1.0935 - 1.3025
# 0.10 sits ~2x above the worst observed aligned value and ~10x below the
# misalignment signature, so it separates the two populations with room on
# both sides. It is NOT the 5e-2 the --help text used to quote: that number
# predates this alignment fix and is below the legitimate bf16 incremental-
# vs-full-forward spread.
VERIFY_MAX_REL = 0.10


def get_dtype(name: str) -> torch.dtype:
    return {"bfloat16": torch.bfloat16,
            "float16": torch.float16,
            "float32": torch.float32}[name]


def load_model(model_path: str, dtype: torch.dtype, device: torch.device):
    from transformers import AutoModelForCausalLM, AutoTokenizer
    print(f"[backfill] loading tokenizer from {model_path}", flush=True)
    tok = AutoTokenizer.from_pretrained(model_path)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    print(f"[backfill] loading HF model (dtype={dtype})", flush=True)
    mdl = AutoModelForCausalLM.from_pretrained(model_path, dtype=dtype)
    mdl = mdl.to(device).eval()
    print(f"[backfill] ready: d_model={mdl.config.hidden_size}, "
          f"n_layers={mdl.config.num_hidden_layers}", flush=True)
    return mdl, tok


def backfill_one(json_path: Path, npz_path: Path, model, tokenizer,
                 device: torch.device, dtype: torch.dtype,
                 verify: bool = False, overwrite: bool = False,
                 ) -> tuple[str, int, int]:
    """Backfill a single trajectory. Returns ('ok'|'skip'|'err', T_p, T_g)."""
    with open(json_path) as f:
        meta = json.load(f)

    chat_input = meta.get("chat_template_input", "")
    if not chat_input:
        return ("skip", 0, 0)

    # Read existing npz arrays (don't keep file handle open during forward)
    with np.load(npz_path) as data:
        existing_files = list(data.files)
        existing_arrays = {k: data[k] for k in data.files}
        gen_token_ids = data["token_ids"]
        gen_hidden_states = data["hidden_states"]   # for verify
    stored_dtype = meta.get("extra", {}).get("stored_dtype", "float32")
    target_np_dtype = np.float16 if stored_dtype == "float16" else np.float32

    if "prompt_hidden_states" in existing_files and not overwrite:
        return ("skip", 0, 0)

    T_g = len(gen_token_ids)
    prompt_ids = tokenizer(chat_input, return_tensors="pt",
                           add_special_tokens=False).input_ids[0].tolist()
    T_p = len(prompt_ids)
    full_ids = prompt_ids + list(gen_token_ids)

    input_ids = torch.tensor([full_ids], dtype=torch.long, device=device)
    with torch.no_grad():
        out = model(input_ids=input_ids,
                    attention_mask=torch.ones_like(input_ids),
                    output_hidden_states=True, return_dict=True, use_cache=False)

    hs_tuple = out.hidden_states   # (L+1) x (1, T_full, D)
    L = len(hs_tuple) - 1
    D = hs_tuple[1].shape[-1]

    p_hs = np.zeros((T_p, L, D), dtype=np.float32)
    for li in range(1, len(hs_tuple)):
        p_hs[:, li - 1, :] = hs_tuple[li][0, :T_p, :].to(torch.float32).cpu().numpy()
    p_lh = p_hs[:, -1, :].copy()
    p_ti = np.asarray(prompt_ids, dtype=np.int32)

    # Alignment gate.
    #
    # The collector decodes one token at a time with a KV cache and stores the
    # residual stream **before** consuming that token, so stored row g is the
    # state at full-sequence position P+g-1 (this is the R-1 offset: a full
    # forward's row T_p+g is the state *after* consuming it).
    # Comparing the two directly is off by one position, which reads as a ~100%
    # relative difference on every trajectory — measured 1.09-1.30 across 6
    # pilot traces — and says nothing about the prompt block we are writing.
    #
    # We therefore compare the ALIGNED slice. Measured on the same 6 traces:
    #   aligned    0.0226 - 0.0461
    #   misaligned 1.0935 - 1.3025
    # The two are separated by ~30x, so the threshold below sits in the gap.
    # --verify now REJECTS the write instead of only reporting, which is what
    # its --help text always claimed; see the "Don't fail" note that used to
    # be here. A rejection means the prompt block would be untrustworthy.
    if verify:
        final = hs_tuple[L][0].to(torch.float32).cpu().numpy()
        stored_lh = existing_arrays["last_hidden"]
        if stored_lh.dtype != np.float32:
            stored_lh = stored_lh.astype(np.float32)

        aligned = final[T_p - 1:T_p - 1 + T_g, :]
        misaligned = final[T_p:T_p + T_g, :]
        rel_aligned = float(np.abs(aligned - stored_lh).max()) / (
            float(np.abs(stored_lh).max()) + 1e-9)
        rel_misaligned = float(np.abs(misaligned - stored_lh).max()) / (
            float(np.abs(stored_lh).max()) + 1e-9)
        print(f"      verify: aligned={rel_aligned:.4e} "
              f"(misaligned={rel_misaligned:.4e}, reported for diagnosis only)",
              flush=True)
        if rel_aligned > VERIFY_MAX_REL:
            print(f"      verify: REJECT — aligned relative diff {rel_aligned:.4e} "
                  f"> {VERIFY_MAX_REL:.2e}; prompt block NOT written", flush=True)
            return ("reject", T_p, T_g)

    # Write back
    existing_arrays["prompt_hidden_states"] = p_hs.astype(target_np_dtype, copy=False)
    existing_arrays["prompt_last_hidden"]   = p_lh.astype(target_np_dtype, copy=False)
    existing_arrays["prompt_token_ids"]     = p_ti
    np.savez(npz_path, **existing_arrays)

    # JSON update
    meta["n_prompt_tokens"] = T_p
    meta["n_tokens"] = T_p + T_g
    meta["schema_version"] = SCHEMA_VERSION
    meta.setdefault("extra", {})
    meta["extra"]["prompt_backfilled"] = True
    meta["extra"]["prompt_backfill_unix_s"] = time.time()
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    del out, hs_tuple, input_ids
    return ("ok", T_p, T_g)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True,
                    help="Directory of <tid>.json + <tid>.npz trajectory pairs")
    ap.add_argument("--model-path", required=True,
                    help="HF model path (must match the one in trajectory meta)")
    ap.add_argument("--device", default="cuda:0")
    ap.add_argument("--dtype", default="bfloat16",
                    choices=["bfloat16", "float16", "float32"],
                    help="Compute dtype for the forward pass; on-disk dtype "
                         "follows the trajectory's stored_dtype (float32 or float16).")
    ap.add_argument("--overwrite", action="store_true",
                    help="Recompute even if prompt_hidden_states already exists")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--verify", action="store_true",
                    help="Alignment gate: re-forward the trajectory and compare "
                         "the ALIGNED gen-position last-layer residual "
                         "(position T_p-1, i.e. before the token is consumed) "
                         "against stored last_hidden. If the relative max "
                         f"difference exceeds {VERIFY_MAX_REL:g}, the prompt "
                         "block is NOT written and the trajectory is counted "
                         "as rejected. Measured aligned spread on 6 pilot "
                         "trajectories is 0.0226-0.0461; the off-by-one "
                         "(misaligned) comparison reads ~1.1-1.3.")
    args = ap.parse_args()

    root = Path(args.root)
    if not root.is_dir():
        raise NotADirectoryError(root)
    device = torch.device(args.device)
    dtype = get_dtype(args.dtype)
    model, tokenizer = load_model(args.model_path, dtype, device)

    ds = TrajectoryDataset(root)
    ids = ds.ids()
    if args.limit:
        ids = ids[:args.limit]
    print(f"[backfill] {len(ids)} trajectories in {root}", flush=True)

    n_ok = n_skip = n_err = n_reject = 0
    t_start = time.time()
    for tid in ids:
        json_path = ds._index[tid]
        npz_path = json_path.with_suffix(".npz")
        try:
            status, T_p, T_g = backfill_one(
                json_path, npz_path, model, tokenizer, device, dtype,
                verify=args.verify, overwrite=args.overwrite,
            )
        except Exception as e:
            print(f"  · {tid}: ERROR {type(e).__name__}: {e}", file=sys.stderr,
                  flush=True)
            n_err += 1
            continue
        if status == "ok":
            n_ok += 1
            print(f"  · {tid}: OK (T_p={T_p}, T_g={T_g})", flush=True)
        elif status == "skip":
            n_skip += 1
            print(f"  · {tid}: SKIP", flush=True)
        else:
            n_reject += 1
            print(f"  · {tid}: **REJECTED by the alignment gate — prompt block "
                  f"not written**", flush=True)
    dt = time.time() - t_start
    print(f"\n[backfill] ok={n_ok} skip={n_skip} reject={n_reject} err={n_err}  "
          f"in {dt/60:.1f} min. root={root}", flush=True)
    if n_reject:
        print("[backfill] WARNING: rejections mean --verify found the recomputed "
              "gen block does not line up with the stored one. Do not ship this "
              "root until the cause is understood.", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()