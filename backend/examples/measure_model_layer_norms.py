"""Measure per-layer hidden-state norms for any model, directly from a forward pass.

Finding 10 injects a vector sized as a fraction of the layer's own state, and
its whole claim is a claim about *depth* — "the useful band is 43–64% of the
stack". Repeating that on another model requires knowing that model's
residual-stream scale, and `layer_profiles.json` only describes Qwen3-1.7B
(d_model 2048, measured from its own collected trajectories). Feeding a 1.7B
profile to an 8B model would make "20% of the state" wrong by whatever
factor separates the two, silently.

So this measures it from the model in front of us: run the actual prompts
through a real forward pass, take the mean norm of each layer's residual
stream over generated positions, and write the same JSON shape
`measure_layers.py` uses. No .npz required, so it works for any model that
loads.

Two things are measured, and they are not the same number:

  * `mean_norm` — mean of ‖h‖ over positions. This is what the steering
    registry scales against, and it is the conservative choice: a norm
    distribution is right-skewed, so the mean sits above the typical token
    and a vector sized at "20% of the mean" is a slightly larger push than
    "20% of a typical token".

  * `median_norm` — the median. Reported next to it so the skew is visible
    rather than assumed away.

Usage:
    python3 backend/examples/measure_model_layer_norms.py \
        --model-path /data/model/Qwen3-8B \
        --problem-file problem_index.json \
        --out backend/examples/output/layer_profiles_qwen3_8b.json
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Dict, List


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-path", required=True)
    ap.add_argument("--problem-file", required=True)
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--prefill", type=int, default=32,
                    help="teacher-forced tokens per problem to measure at")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--dtype", default="float32",
                    help="float32: this reads a residual stream through no "
                         "unembedding, but norms are cheap and a bf16 sum "
                         "over 4096 dims loses precision")
    ap.add_argument("--chat-template", type=int, default=1)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    td = {"bfloat16": torch.bfloat16, "float16": torch.float16,
          "float32": torch.float32}[args.dtype]
    tok = AutoTokenizer.from_pretrained(args.model_path)
    model = AutoModelForCausalLM.from_pretrained(
        args.model_path, dtype=td, device_map={"": args.device})
    model.eval()

    raw = json.loads(Path(args.problem_file).read_text())
    if isinstance(raw, dict):
        if "problems" in raw:
            problems = raw["problems"]
        else:
            problems = [dict(v, label=v.get("id", k)) if isinstance(v, dict)
                        else {"label": k, "prompt": str(v)}
                        for k, v in raw.items()]
    problems = problems[: args.limit]

    n_layers = model.config.num_hidden_layers
    per_layer: Dict[int, List[float]] = {L: [] for L in range(n_layers + 1)}

    with torch.inference_mode():
        for pi, prob in enumerate(problems):
            text = prob.get("prompt") or prob.get("text") or ""
            if not text:
                continue
            if args.chat_template and getattr(tok, "chat_template", None):
                try:
                    text = tok.apply_chat_template(
                        [{"role": "user", "content": text}],
                        tokenize=False, add_generation_prompt=True)
                except Exception as exc:
                    print(f"  (chat template unavailable: {exc})")
            ids = tok(text, return_tensors="pt",
                      add_special_tokens=False).input_ids.to(model.device)
            if ids.shape[1] < 8:
                continue
            # Prefill a bounded window: norms grow with position, and the
            # steering calibration should reflect the region the vectors are
            # actually injected into rather than the whole prompt.
            ids = ids[:, -args.prefill:]
            out = model(input_ids=ids, output_hidden_states=True,
                        use_cache=False, return_dict=True)
            for L, h in enumerate(out.hidden_states):
                # Mean over positions, per sequence, then across sequences:
                # averaging positions first would let one long prompt
                # dominate every layer.
                per_layer[L].append(float(h[0].float().norm(dim=-1).mean()))
            print(f"[{pi+1}/{len(problems)}] {prob.get('label','?')} "
                  f"({ids.shape[1]} tokens)")

    rows = []
    for L in range(n_layers + 1):
        vals = per_layer[L]
        if not vals:
            continue
        rows.append({
            "layer": L,
            "n_positions": len(vals),
            "mean_norm": round(statistics.fmean(vals), 4),
            "median_norm": round(statistics.median(vals), 4),
        })

    out = {
        "d_model": model.config.hidden_size,
        "n_trajectories": len(problems),
        "source": (f"measured from {args.model_path} via forward pass, "
                   f"{args.prefill}-token prefill"),
        "note": ("mean_norm is what the steering registry scales against; "
                 "median_norm is reported because the norm distribution is "
                 "right-skewed and the two differ"),
        "layers": rows,
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2))

    print(f"\n{'layer':>6}{'mean':>12}{'median':>12}{'median/mean':>14}")
    for r in rows:
        print(f"{r['layer']:>6}{r['mean_norm']:>12.2f}"
              f"{r['median_norm']:>12.2f}"
              f"{r['median_norm']/r['mean_norm']:>14.3f}")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
