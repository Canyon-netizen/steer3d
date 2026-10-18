#!/usr/bin/env python3
"""Capture a baseline reasoning route and vector-steered continuations.

This is a small, targeted GPU capture:
  * one anchor per source (the token before a marker),
  * teacher-forced continuation on the SAME tokens,
  * arms: baseline / w / mean_g / sparse_g / random,
  * hidden states at selected layers and behaviour summaries for a window.

It is not a free-running rollout.  The goal is to see where a single injection
moves the hidden-state route, not to claim a new generated answer.
"""
from __future__ import annotations

import argparse
import json
import sys
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
    p.add_argument("--layers", default="10,20,27")
    p.add_argument("--inject-layer", type=int, default=20)
    p.add_argument("--window-before", type=int, default=8)
    p.add_argument("--window-after", type=int, default=64)
    p.add_argument("--dose", type=float, default=0.1)
    p.add_argument("--gpu", default="0")
    args = p.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch.set_num_threads(4)
    torch.cuda.set_device(int(args.gpu))
    tokenizer = AutoTokenizer.from_pretrained(str(args.model), local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        str(args.model), local_files_only=True, dtype=torch.float32, attn_implementation="eager")
    model = model.to("cuda").eval()
    layers = [int(item) for item in args.layers.split(",") if item.strip()]
    data = load_json(args.sources)
    sources = data["sources"]
    arms = data.get("arms", ["w", "mean_g", "sparse_g", "random"])
    records = []
    archive = {}

    for index, source in enumerate(sources):
        source_id = source["id"]
        prompt = np.asarray(source["prompt_ids"], dtype=np.int64)
        generated = np.asarray(source["ids"], dtype=np.int64)
        full = np.concatenate([prompt, generated])
        anchor_t = int(source["anchor_t"])
        anchor_pos = int(len(prompt) + anchor_t)
        start = max(0, anchor_pos - args.window_before)
        end = min(len(full), anchor_pos + 1 + args.window_after)
        if not 0 <= anchor_pos < len(full) - 1:
            raise ValueError("bad anchor for " + source_id)
        ids = torch.tensor(full[:end].reshape(1, -1), dtype=torch.long, device="cuda")

        def run(arm: str, vector=None):
            hook = None
            alpha = 0.0
            if vector is not None:
                baseline = run("baseline")
                anchor_norm = float(np.linalg.norm(baseline["anchors"][str(args.inject_layer)]))
                alpha = args.dose * anchor_norm
                def inject(module, inputs):
                    hidden = inputs[0]
                    if hidden.shape[1] <= anchor_pos:
                        return None
                    changed = hidden.clone()
                    changed[:, anchor_pos, :] += alpha * torch.as_tensor(
                        vector, dtype=hidden.dtype, device=hidden.device)
                    return (changed,) + inputs[1:]
                hook = model.model.layers[args.inject_layer].register_forward_pre_hook(inject)
            try:
                with torch.inference_mode():
                    out = model(input_ids=ids, use_cache=False, output_hidden_states=True, return_dict=True)
            finally:
                if hook is not None:
                    hook.remove()
            hidden = {str(layer): out.hidden_states[layer][0, start:end].detach().float().cpu().numpy()
                      for layer in layers}
            logits = out.logits[0, start:end].float().cpu().numpy()
            top1 = np.argmax(logits, axis=-1)
            log_z = np.logaddexp.reduce(logits, axis=-1)
            probs = np.exp(logits - log_z[:, None])
            entropy = -(probs * np.log(np.clip(probs, 1e-30, 1.0))).sum(axis=-1)
            next_ids = full[start + 1:end + 1]
            next_logp = []
            for row in range(len(next_ids)):
                next_logp.append(float(logits[row, int(next_ids[row])] - log_z[row]))
            anchors = {str(layer): out.hidden_states[layer][0, anchor_pos].detach().float().cpu().numpy()
                       for layer in layers}
            return {"hidden": hidden, "top1": top1, "entropy": entropy, "next_logp": np.asarray(next_logp),
                    "anchors": anchors, "alpha": alpha}

        baseline = run("baseline")
        captures = {"baseline": baseline}
        for arm in arms:
            path = args.vectors / ("%d_%s.npy" % (int(source["marker"]), arm))
            if not path.exists():
                raise FileNotFoundError(str(path))
            vector = np.load(path).astype(np.float32)
            vector = vector / max(float(np.linalg.norm(vector)), 1e-12)
            captures[arm] = run(arm, vector)
            print("CAPTURE", source_id, "arm", arm, "alpha", captures[arm]["alpha"], flush=True)

        record = {
            "id": source_id,
            "marker": int(source["marker"]),
            "anchor_t": anchor_t,
            "anchor_pos": anchor_pos,
            "start": int(start),
            "end": int(end),
            "dose": args.dose,
            "token_ids": [int(item) for item in full[start:end]],
            "tokens": [tokenizer.decode([int(item)]) for item in full[start:end]],
            "behavior": {},
        }
        for arm, cap in captures.items():
            record["behavior"][arm] = {
                "top1": [int(item) for item in cap["top1"]],
                "entropy": [float(item) for item in cap["entropy"]],
                "next_logp": [float(item) for item in cap["next_logp"]],
                "anchor_norm": {layer: float(np.linalg.norm(cap["anchors"][layer])) for layer in cap["anchors"]},
            }
            for layer in layers:
                archive["%s__%s__L%d" % (source_id, arm, layer)] = cap["hidden"][str(layer)]
        records.append(record)
        print("DONE", source_id, "records", len(records), flush=True)

    args.out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.out / "reasoning_path_states.npz", **archive)
    payload = {
        "schema": "steer3d.reasoning_path/1",
        "complete": True,
        "scope": "targeted anchor injection, teacher-forced continuation; not free-running",
        "model": str(args.model),
        "layers": layers,
        "inject_layer": args.inject_layer,
        "window_before": args.window_before,
        "window_after": args.window_after,
        "dose": args.dose,
        "arms": arms,
        "sources": records,
    }
    (args.out / "reasoning_path.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print("OK", args.out / "reasoning_path.json", "arrays", len(archive))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

