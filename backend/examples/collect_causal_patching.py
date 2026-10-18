#!/usr/bin/env python3
"""Causal patching of top MLP / head components at the reasoning anchor.

For each source and arm:
  * run baseline and steered;
  * patch baseline MLP/head writes into the steered run (necessity test);
  * patch steered writes into the baseline run (sufficiency test);
  * report how much of the target logp effect survives.

This is a local single-position patching experiment, not a full edge graph.
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
    p.add_argument("--attribution", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--layers", default="20,21")
    p.add_argument("--arms", default="mean_g,w")
    p.add_argument("--top-heads", type=int, default=4)
    p.add_argument("--dose", type=float, default=0.1)
    p.add_argument("--gpu", default="2")
    args = p.parse_args()

    import torch
    from transformers import AutoModelForCausalLM

    torch.cuda.set_device(int(args.gpu))
    model = AutoModelForCausalLM.from_pretrained(
        str(args.model), local_files_only=True, dtype=torch.float32, attn_implementation="eager")
    model = model.to("cuda").eval()
    layers = [int(item) for item in args.layers.split(",") if item.strip()]
    arms = [item.strip() for item in args.arms.split(",") if item.strip()]
    head_dim = int(getattr(model.config, "head_dim", model.config.hidden_size // model.config.num_attention_heads))
    data = load_json(args.sources)
    attribution = load_json(args.attribution)
    attr_by_id = {row["id"]: row for row in attribution["records"]}

    def top_heads(source_id, arm, layer):
        row = attr_by_id[source_id]
        heads = sorted(row["layers"][str(layer)]["heads"], key=lambda item: -abs(item[arm]["delta"]))
        return [int(item["head"]) for item in heads[: args.top_heads]]

    def make_capture(captures, layer, anchor):
        def attn_hook(module, inputs):
            captures.setdefault(layer, {})["attn"] = inputs[0][0, anchor].detach().float().clone()
        def mlp_hook(module, inputs, output):
            captures.setdefault(layer, {})["mlp"] = output[0, anchor].detach().float().clone()
        return attn_hook, mlp_hook

    def make_patches(patches, anchor):
        handles = []
        for spec in patches:
            if spec["kind"] == "mlp":
                layer, donor = spec["layer"], spec["donor"]
                def hook(module, inputs, output, layer=layer, donor=donor):
                    out = output.clone()
                    out[0, anchor, :] = donor.to(out.dtype)
                    return out
                handles.append(model.model.layers[layer].mlp.down_proj.register_forward_hook(hook))
            else:
                layer, heads, donor = spec["layer"], spec["heads"], spec["donor"]
                def hook(module, inputs, layer=layer, heads=heads, donor=donor):
                    hidden = inputs[0].clone()
                    for head in heads:
                        block = slice(head * head_dim, (head + 1) * head_dim)
                        hidden[0, anchor, block] = donor[block].to(hidden.dtype)
                    return (hidden,) + inputs[1:]
                handles.append(model.model.layers[layer].self_attn.o_proj.register_forward_pre_hook(hook))
        return handles

    records = []
    for source in data["sources"]:
        source_id = source["id"]
        prompt = np.asarray(source["prompt_ids"], dtype=np.int64)
        generated = np.asarray(source["ids"], dtype=np.int64)
        full = np.concatenate([prompt, generated])
        anchor = int(len(prompt) + int(source["anchor_t"]))
        marker = int(full[anchor + 1])
        ids = torch.tensor(full[: anchor + 1].reshape(1, -1), dtype=torch.long, device="cuda")

        def run(vector=None, patches=None, collect=False):
            handles = []
            captures = {}
            if collect:
                for layer in layers:
                    a, m = make_capture(captures, layer, anchor)
                    handles.append(model.model.layers[layer].self_attn.o_proj.register_forward_pre_hook(a))
                    handles.append(model.model.layers[layer].mlp.down_proj.register_forward_hook(m))
            if patches:
                handles.extend(make_patches(patches, anchor))
            if vector is not None:
                def inject(module, inputs):
                    hidden = inputs[0]
                    if hidden.shape[1] <= anchor:
                        return None
                    changed = hidden.clone()
                    changed[0, anchor, :] += torch.as_tensor(vector, dtype=hidden.dtype, device=hidden.device)
                    return (changed,) + inputs[1:]
                handles.append(model.model.layers[20].register_forward_pre_hook(inject))
            try:
                with torch.inference_mode():
                    out = model(input_ids=ids, use_cache=False, return_dict=True)
            finally:
                for handle in handles:
                    handle.remove()
            logits = out.logits[0, anchor].float().cpu().numpy()
            return {"logp": float(logits[marker] - np.logaddexp.reduce(logits)), "captures": captures}

        # h20 norm for dose
        h_norm = [None]
        def norm_hook(module, inputs):
            h_norm[0] = float(inputs[0][0, anchor].float().norm().item())
        handle = model.model.layers[20].register_forward_pre_hook(norm_hook)
        baseline = run(collect=True)
        handle.remove()
        alpha = args.dose * float(h_norm[0])
        base_caps = baseline["captures"]
        row = {"id": source_id, "marker": marker, "anchor_t": int(source["anchor_t"]), "alpha": alpha, "arms": {}}
        for arm in arms:
            vector = np.load(args.vectors / ("%d_%s.npy" % (marker, arm))).astype(np.float32)
            vector = vector / max(float(np.linalg.norm(vector)), 1e-12)
            steered = run(vector * alpha, collect=True)
            steer_caps = steered["captures"]
            base_logp = baseline["logp"]
            steer_logp = steered["logp"]
            delta = steer_logp - base_logp
            components = {
                "mlp20": [{"kind": "mlp", "layer": 20, "donor": base_caps[20]["mlp"]}],
                "mlp21": [{"kind": "mlp", "layer": 21, "donor": base_caps[21]["mlp"]}],
                "heads20": [{"kind": "heads", "layer": 20, "heads": top_heads(source_id, arm, 20), "donor": base_caps[20]["attn"]}],
                "heads21": [{"kind": "heads", "layer": 21, "heads": top_heads(source_id, arm, 21), "donor": base_caps[21]["attn"]}],
                "mlp_both": [
                    {"kind": "mlp", "layer": 20, "donor": base_caps[20]["mlp"]},
                    {"kind": "mlp", "layer": 21, "donor": base_caps[21]["mlp"]},
                ],
                "heads_both": [
                    {"kind": "heads", "layer": 20, "heads": top_heads(source_id, arm, 20), "donor": base_caps[20]["attn"]},
                    {"kind": "heads", "layer": 21, "heads": top_heads(source_id, arm, 21), "donor": base_caps[21]["attn"]},
                ],
            }
            items = {}
            for name, specs in components.items():
                # necessity: baseline component into steered
                patched_steer = run(vector * alpha, patches=specs)["logp"]
                # sufficiency: steered component into baseline
                steer_specs = []
                for spec in specs:
                    copy = dict(spec)
                    if spec["kind"] == "mlp":
                        copy["donor"] = steer_caps[spec["layer"]]["mlp"]
                    else:
                        copy["donor"] = steer_caps[spec["layer"]]["attn"]
                    steer_specs.append(copy)
                patched_base = run(None, patches=steer_specs)["logp"]
                necessity = (patched_steer - base_logp) / delta if abs(delta) > 1e-9 else None
                sufficiency = (patched_base - base_logp) / delta if abs(delta) > 1e-9 else None
                items[name] = {
                    "patched_steer_logp": float(patched_steer),
                    "patched_base_logp": float(patched_base),
                    "necessity_fraction": None if necessity is None else float(necessity),
                    "sufficiency_fraction": None if sufficiency is None else float(sufficiency),
                }
            row["arms"][arm] = {"base_logp": float(base_logp), "steer_logp": float(steer_logp), "delta": float(delta), "components": items}
            print("PATCH", source_id, arm, "delta", round(delta, 3), "mlp20 necessity", round(items["mlp20"]["necessity_fraction"] or 0, 3), flush=True)
        records.append(row)

    payload = {
        "schema": "steer3d.causal_patching/1",
        "complete": True,
        "scope": "single-position component patching at the anchor; necessity = baseline component into steered, sufficiency = steered component into baseline",
        "layers": layers,
        "arms": arms,
        "top_heads": args.top_heads,
        "records": records,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "causal_patching.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print("OK", args.out / "causal_patching.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

