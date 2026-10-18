#!/usr/bin/env python3
"""Capture head/OV and MLP attribution for the reasoning-path anchor injection.

For each source and arm, run a short prefix through the anchor and record:
  * per-head OV residual write at layers 20/21,
  * per-head direct logit attribution to the marker token,
  * vector projection onto each head's OV subspace,
  * MLP direct logit attribution.

This is a local, single-position attribution, not a full edge graph.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def load_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sources", type=Path, required=True)
    p.add_argument("--model", type=Path, required=True)
    p.add_argument("--vectors", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--layers", default="20,21")
    p.add_argument("--dose", type=float, default=0.1)
    p.add_argument("--gpu", default="2")
    args = p.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch.cuda.set_device(int(args.gpu))
    tokenizer = AutoTokenizer.from_pretrained(str(args.model), local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        str(args.model), local_files_only=True, dtype=torch.float32, attn_implementation="eager")
    model = model.to("cuda").eval()
    layers = [int(item) for item in args.layers.split(",") if item.strip()]
    head_dim = int(getattr(model.config, "head_dim", model.config.hidden_size // model.config.num_attention_heads))
    n_heads = int(model.config.num_attention_heads)
    hidden = int(model.config.hidden_size)
    w_u = model.lm_head.weight.detach().float().cpu().numpy()
    w_o = {layer: model.model.layers[layer].self_attn.o_proj.weight.detach().float().cpu().numpy() for layer in layers}
    data = load_json(args.sources)
    arms = data.get("arms", ["w", "mean_g", "sparse_g", "random"])
    records = []

    for source in data["sources"]:
        source_id = source["id"]
        prompt = np.asarray(source["prompt_ids"], dtype=np.int64)
        generated = np.asarray(source["ids"], dtype=np.int64)
        full = np.concatenate([prompt, generated])
        anchor_pos = int(len(prompt) + int(source["anchor_t"]))
        marker = int(full[anchor_pos + 1])
        ids = torch.tensor(full[: anchor_pos + 1].reshape(1, -1), dtype=torch.long, device="cuda")
        captured = {layer: {} for layer in layers}
        hooks = []
        for layer in layers:
            def make_attn(layer):
                def hook(module, inputs):
                    captured[layer]["attn"] = inputs[0][0, anchor_pos].detach().float().cpu().numpy().copy()
                return hook
            def make_mlp(layer):
                def hook(module, inputs, output):
                    captured[layer]["mlp"] = output[0, anchor_pos].detach().float().cpu().numpy().copy()
                return hook
            hooks.append(model.model.layers[layer].self_attn.o_proj.register_forward_pre_hook(make_attn(layer)))
            hooks.append(model.model.layers[layer].mlp.down_proj.register_forward_hook(make_mlp(layer)))

        def norm_hook(module, inputs):
            captured["h20_norm"] = float(inputs[0][0, anchor_pos].float().norm().item())
        norm_handle = model.model.layers[20].register_forward_pre_hook(norm_hook)

        def run(vector=None, alpha=0.0):
            injection = None
            if vector is not None:
                def inject(module, inputs):
                    hidden = inputs[0]
                    if hidden.shape[1] <= anchor_pos:
                        return None
                    changed = hidden.clone()
                    changed[0, anchor_pos, :] += torch.as_tensor(vector, dtype=hidden.dtype, device=hidden.device)
                    return (changed,) + inputs[1:]
                injection = model.model.layers[20].register_forward_pre_hook(inject)
            try:
                with torch.inference_mode():
                    out = model(input_ids=ids, use_cache=False, return_dict=True)
            finally:
                if injection is not None:
                    injection.remove()
            logits = out.logits[0, anchor_pos].float().cpu().numpy()
            logp = float(logits[marker] - np.logaddexp.reduce(logits))
            return {"logp": logp, "h20_norm": captured.get("h20_norm"),
                    "captured": {layer: {key: value.copy() for key, value in captured[layer].items()} for layer in layers}}

        baseline = run()
        alpha = args.dose * float(baseline["h20_norm"])
        norm_handle.remove()
        arms_out = {"baseline": baseline}
        for arm in arms:
            vector = np.load(args.vectors / ("%d_%s.npy" % (marker, arm))).astype(np.float32)
            vector = vector / max(float(np.linalg.norm(vector)), 1e-12)
            arms_out[arm] = run(vector * alpha, alpha=alpha)
        d = w_u[marker].astype(np.float64)
        row = {"id": source_id, "marker": marker, "anchor_t": int(source["anchor_t"]), "alpha": alpha, "layers": {}}
        for layer in layers:
            w_o_layer = w_o[layer].astype(np.float64)
            head_rows = []
            for head in range(n_heads):
                block = slice(head * head_dim, (head + 1) * head_dim)
                projection = w_o_layer[:, block] @ (w_o_layer[:, block].T @ d)
                proj_cos = float(np.dot(projection, d) / max(np.linalg.norm(projection) * np.linalg.norm(d), 1e-12))
                head_vec = arms_out["baseline"]["captured"][layer].get("attn")
                if head_vec is None:
                    continue
                base_write = head_vec[block] @ w_o_layer[:, block].T
                base_dla = float(np.dot(base_write, d))
                head_row = {"head": head, "proj_cos": proj_cos,
                            "base_dla": base_dla, "write_norm": float(np.linalg.norm(base_write))}
                for arm in arms:
                    head_vec = arms_out[arm]["captured"][layer].get("attn")
                    if head_vec is None:
                        continue
                    write = head_vec[block] @ w_o_layer[:, block].T
                    head_row[arm] = {"dla": float(np.dot(write, d)), "delta": float(np.dot(write, d) - base_dla),
                                     "write_delta_norm": float(np.linalg.norm(write - base_write))}
                head_rows.append(head_row)
            mlp_row = {}
            base_mlp = arms_out["baseline"]["captured"][layer].get("mlp")
            if base_mlp is not None:
                base_dla = float(np.dot(base_mlp, d))
                mlp_row = {"base_dla": base_dla}
                for arm in arms:
                    mlp = arms_out[arm]["captured"][layer].get("mlp")
                    if mlp is not None:
                        mlp_row[arm] = {"dla": float(np.dot(mlp, d)), "delta": float(np.dot(mlp, d) - base_dla),
                                        "write_delta_norm": float(np.linalg.norm(mlp - base_mlp))}
            row["layers"][str(layer)] = {"heads": head_rows, "mlp": mlp_row,
                                         "logp": {arm: arms_out[arm]["logp"] for arm in ["baseline"] + arms}}
        records.append(row)
        print("ATTR", source_id, "marker", marker, "alpha", alpha, flush=True)

    payload = {
        "schema": "steer3d.vector_attribution/1",
        "complete": True,
        "scope": "single-position head/OV and MLP direct logit attribution at the anchor; not a full edge graph",
        "model": str(args.model),
        "layers": layers,
        "n_heads": n_heads,
        "head_dim": head_dim,
        "arms": arms,
        "records": records,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "vector_attribution.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print("OK", args.out / "vector_attribution.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

