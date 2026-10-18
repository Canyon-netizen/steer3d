#!/usr/bin/env python3
"""Free-running steered generation from a reasoning anchor.

Modes:
  oneshot   inject once into the prefill anchor, then decode normally;
  per_token inject at every decoding step (same vector, same dose).

Records generated tokens, per-step logp/entropy, and layer-21 hidden states.
This is a small behavioural check, not a full evaluation.
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
    p.add_argument("--arms", default="mean_g,w,random")
    p.add_argument("--tokens", type=int, default=24)
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
    data = load_json(args.sources)
    arms = [item.strip() for item in args.arms.split(",") if item.strip()]
    records = []
    archive = {}

    for source in data["sources"]:
        source_id = source["id"]
        prompt = np.asarray(source["prompt_ids"], dtype=np.int64)
        generated = np.asarray(source["ids"], dtype=np.int64)
        anchor_t = int(source["anchor_t"])
        prefix = np.concatenate([prompt, generated[: anchor_t + 1]])
        marker = int(generated[anchor_t + 1]) if anchor_t + 1 < len(generated) else None
        ids = list(int(x) for x in prefix)
        with torch.inference_mode():
            probe = model(input_ids=torch.tensor(prefix.reshape(1, -1), dtype=torch.long, device="cuda"),
                          use_cache=False, output_hidden_states=True, return_dict=True)
        h20_norm = float(probe.hidden_states[20][0, -1].float().norm().item())
        alpha = args.dose * h20_norm

        def generate(vector=None, per_token=False):
            context = list(ids)
            out_tokens = []
            logps = []
            entropies = []
            hidden = []
            for step in range(args.tokens):
                tensor = torch.tensor(context, dtype=torch.long, device="cuda").reshape(1, -1)
                handle = None
                if vector is not None and (per_token or step == 0):
                    def inject(module, inputs):
                        hidden_in = inputs[0]
                        changed = hidden_in.clone()
                        changed[0, -1, :] += torch.as_tensor(vector * alpha, dtype=hidden_in.dtype, device=hidden_in.device)
                        return (changed,) + inputs[1:]
                    handle = model.model.layers[20].register_forward_pre_hook(inject)
                try:
                    with torch.inference_mode():
                        out = model(input_ids=tensor, use_cache=False, output_hidden_states=True, return_dict=True)
                finally:
                    if handle is not None:
                        handle.remove()
                logits = out.logits[0, -1].float().cpu().numpy()
                log_z = np.logaddexp.reduce(logits)
                probs = np.exp(logits - log_z)
                token = int(np.argmax(logits))
                out_tokens.append(token)
                logps.append(float(logits[token] - log_z))
                entropies.append(float(-(probs * np.log(np.clip(probs, 1e-30, 1.0))).sum()))
                hidden.append(out.hidden_states[21][0, -1].detach().float().cpu().numpy())
                context.append(token)
            return {"tokens": out_tokens, "logp": logps, "entropy": entropies, "hidden": np.stack(hidden, axis=0)}

        baseline = generate()
        record = {"id": source_id, "marker": marker, "anchor_t": anchor_t, "prefix_len": len(prefix), "alpha": alpha,
                  "baseline_tokens": baseline["tokens"], "baseline_text": tokenizer.decode(baseline["tokens"]),
                  "arms": {}}
        archive["%s__baseline__L21" % source_id] = baseline["hidden"]
        for arm in arms:
            vector = np.load(args.vectors / ("%d_%s.npy" % (int(source["marker"]), arm))).astype(np.float32)
            vector = vector / max(float(np.linalg.norm(vector)), 1e-12)
            for mode, per_token in (("oneshot", False), ("per_token", True)):
                if mode == "per_token" and arm not in ("mean_g",):
                    continue
                run = generate(vector, per_token=per_token)
                key = "%s__%s__%s__L21" % (source_id, arm, mode)
                archive[key] = run["hidden"]
                diff = next((index for index, (a, b) in enumerate(zip(baseline["tokens"], run["tokens"])) if a != b), len(run["tokens"]))
                record["arms"][arm + ":" + mode] = {
                    "tokens": run["tokens"], "text": tokenizer.decode(run["tokens"]),
                    "first_divergence": int(diff),
                    "first_token_changed": diff == 0,
                    "mean_logp": float(np.mean(run["logp"])),
                    "mean_entropy": float(np.mean(run["entropy"])),
                    "hidden_displacement": float(np.linalg.norm(run["hidden"] - baseline["hidden"], axis=1).mean()),
                }
                print("FREE", source_id, arm, mode, "first_diff", diff, "disp", round(record["arms"][arm + ":" + mode]["hidden_displacement"], 2), flush=True)
        records.append(record)

    payload = {
        "schema": "steer3d.free_running/1",
        "complete": True,
        "scope": "free-running greedy generation from the anchor; small behavioural check",
        "model": str(args.model),
        "tokens": args.tokens,
        "dose": args.dose,
        "arms": arms,
        "records": records,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.out / "free_running_states.npz", **archive)
    (args.out / "free_running.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print("OK", args.out / "free_running.json", "arrays", len(archive))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

