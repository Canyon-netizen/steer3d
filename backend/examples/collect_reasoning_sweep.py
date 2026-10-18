#!/usr/bin/env python3
"""Small dose / anchor sweep for the reasoning-path intervention.

For each source, inject at offsets relative to the marker anchor:
  offsets = [-16, -8, 0]
  doses   = [0.02, 0.05, 0.1, 0.2]
  arms    = mean_g / w / random

Measure the marker logp at the fixed target position and the layer-21 hidden
state in a window around that target.  Teacher-forced, same suffix.
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
    p.add_argument("--offsets", default="-16,-8,0")
    p.add_argument("--doses", default="0.02,0.05,0.1,0.2")
    p.add_argument("--arms", default="mean_g,w,random")
    p.add_argument("--window-before", type=int, default=8)
    p.add_argument("--window-after", type=int, default=24)
    p.add_argument("--gpu", default="2")
    args = p.parse_args()

    import torch
    from transformers import AutoModelForCausalLM

    torch.cuda.set_device(int(args.gpu))
    model = AutoModelForCausalLM.from_pretrained(
        str(args.model), local_files_only=True, dtype=torch.float32, attn_implementation="eager")
    model = model.to("cuda").eval()
    offsets = [int(item) for item in args.offsets.split(",") if item.strip()]
    doses = [float(item) for item in args.doses.split(",") if item.strip()]
    arms = [item.strip() for item in args.arms.split(",") if item.strip()]
    data = load_json(args.sources)
    records = []
    archive = {}

    for source in data["sources"]:
        source_id = source["id"]
        prompt = np.asarray(source["prompt_ids"], dtype=np.int64)
        generated = np.asarray(source["ids"], dtype=np.int64)
        full = np.concatenate([prompt, generated])
        target = int(len(prompt) + int(source["anchor_t"]))
        marker = int(full[target + 1])
        start = max(0, target - args.window_before)
        end = min(len(full), target + 1 + args.window_after)
        ids = torch.tensor(full[:end].reshape(1, -1), dtype=torch.long, device="cuda")
        with torch.inference_mode():
            out = model(input_ids=ids, use_cache=False, output_hidden_states=True, return_dict=True)
        base_logits = out.logits[0, target].float().cpu().numpy()
        base_logp = float(base_logits[marker] - np.logaddexp.reduce(base_logits))
        base_state = out.hidden_states[21][0, start:end].detach().float().cpu().numpy()
        base_h20 = {offset: out.hidden_states[20][0, max(0, target + offset)].detach().float().cpu().numpy()
                    for offset in offsets}
        archive["%s__baseline__L21" % source_id] = base_state
        rows = []
        for offset in offsets:
            anchor = target + offset
            if not 0 <= anchor < len(full) - 1:
                continue
            norm = float(np.linalg.norm(base_h20[offset]))
            for arm in arms:
                vector = np.load(args.vectors / ("%d_%s.npy" % (marker, arm))).astype(np.float32)
                vector = vector / max(float(np.linalg.norm(vector)), 1e-12)
                for dose in doses:
                    def inject(module, inputs):
                        hidden = inputs[0]
                        if hidden.shape[1] <= anchor:
                            return None
                        changed = hidden.clone()
                        changed[0, anchor, :] += torch.as_tensor(dose * norm * vector, dtype=hidden.dtype, device=hidden.device)
                        return (changed,) + inputs[1:]
                    handle = model.model.layers[20].register_forward_pre_hook(inject)
                    try:
                        with torch.inference_mode():
                            steered = model(input_ids=ids, use_cache=False, output_hidden_states=True, return_dict=True)
                    finally:
                        handle.remove()
                    logits = steered.logits[0, target].float().cpu().numpy()
                    logp = float(logits[marker] - np.logaddexp.reduce(logits))
                    state = steered.hidden_states[21][0, start:end].detach().float().cpu().numpy()
                    key = "%s__o%d__d%s__%s__L21" % (source_id, offset, str(dose).replace(".", "p"), arm)
                    archive[key] = state
                    rows.append({"offset": offset, "anchor": anchor, "arm": arm, "dose": dose,
                                 "logp": logp, "delta": logp - base_logp,
                                 "displacement": float(np.linalg.norm(state - base_state, axis=1).mean())})
        records.append({"id": source_id, "marker": marker, "target": target, "base_logp": base_logp,
                        "start": int(start), "end": int(end), "rows": rows})
        print("SWEEP", source_id, "rows", len(rows), flush=True)

    payload = {
        "schema": "steer3d.reasoning_sweep/1",
        "complete": True,
        "scope": "teacher-forced dose/anchor sweep at the target marker; same suffix",
        "model": str(args.model),
        "offsets": offsets,
        "doses": doses,
        "arms": arms,
        "window_before": args.window_before,
        "window_after": args.window_after,
        "records": records,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.out / "reasoning_sweep_states.npz", **archive)
    (args.out / "reasoning_sweep.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print("OK", args.out / "reasoning_sweep.json", "arrays", len(archive))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

