"""Run a steered generation against a counterfactual shadow stream.

This is the experiment that answers "what did my intervention actually
do to the model's internals?". For each generated token it runs two
forward passes over the same KV-cache prefix — one with the steering
vector added at layer L, one without — and records how far apart the
two residual streams are at every layer, plus how much the output
distribution moved.

Teacher-forcing note: the shadow consumes the *primary's* chosen
token, not its own. That keeps the two runs on identical inputs, so
every difference you measure is a representational effect of the
intervention rather than a downstream consequence of a different
token. The first step where the two argmaxes disagree is reported
separately as `first_diverged_step` — that is where behaviour starts
to diverge, and it is worth looking at on its own.

Usage:
    # single prompt, one direction
    python3 backend/examples/run_intervention.py \
        --prompt "What is 17 * 23?" \
        --direction confidence_up --strength 0.15 --layer 14

    # sweep strengths to find the behavioural threshold
    python3 backend/examples/run_intervention.py \
        --prompt "What is 17 * 23?" \
        --direction confidence_up --sweep 0.0 0.05 0.1 0.2 0.4

    # AIME problem from the builtin loader
    python3 backend/examples/run_intervention.py \
        --aime-split 2024 --limit 3 \
        --direction caution --strength 0.1 \
        --model-path /path/to/Qwen3-1.7B
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from core.shadow import ShadowTracker  # noqa: E402
from core.steering import SteeringRegistry  # noqa: E402


AIME_SYSTEM = (
    "You are an expert mathematician competing in the AIME. Solve the "
    "given problem step by step. Show all reasoning clearly. Your final "
    "answer must be a non-negative integer between 0 and 999. Present it "
    "inside \\boxed{} on its own line at the very end."
)


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------


def load_model(model_path: str, device: str, dtype: str = "bfloat16"):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    td = {"bfloat16": torch.bfloat16, "float16": torch.float16,
          "float32": torch.float32}[dtype]
    tok = AutoTokenizer.from_pretrained(model_path)
    model = AutoModelForCausalLM.from_pretrained(
        model_path, dtype=td, device_map={"": device}
    )
    model.eval()
    return model, tok


# ---------------------------------------------------------------------------
# Residual-stream surgery
# ---------------------------------------------------------------------------


class ResidualSteerer:
    """Adds a fixed vector to the residual stream entering `layer`.

    Installed as a forward-pre-hook so the vector lands on the *input*
    of the chosen block, which is the convention every steering paper
    uses (and the one ``compute_steering_vectors.py`` matched, since it
    reads ``hidden_states[layer]`` = the block's *output*... see
    ``--inject-at`` below for the two conventions).
    """

    def __init__(self, model, layer: int):
        self.model = model
        self.layer = layer
        self.vector: Optional["torch.Tensor"] = None
        self._handle = None

    def _blocks(self):
        return self.model.model.layers

    def set_vector(self, vec: np.ndarray) -> None:
        import torch

        block = self._blocks()[self.layer]
        p = next(block.parameters())
        t = torch.as_tensor(np.asarray(vec, dtype=np.float32),
                            dtype=p.dtype, device=p.device)
        self.vector = t.view(1, 1, -1)

    def clear(self) -> None:
        self.vector = None

    def _hook(self, module, inputs):
        if self.vector is None:
            return None
        x = inputs[0]
        return (x + self.vector,) + tuple(inputs[1:])

    def __enter__(self):
        if self.vector is not None and self._handle is None:
            self._handle = self._blocks()[self.layer].register_forward_pre_hook(
                self._hook
            )
        return self

    def __exit__(self, *exc):
        if self._handle is not None:
            self._handle.remove()
            self._handle = None
        return False


# ---------------------------------------------------------------------------
# The dual-stream decode loop
# ---------------------------------------------------------------------------


def run_dual_stream(
    model,
    tokenizer,
    prompt_text: str,
    steer_vec: Optional[np.ndarray],
    layer: int,
    max_new_tokens: int = 256,
    track_shadow: bool = True,
    max_track_steps: Optional[int] = None,
) -> dict:
    """Generate greedily, running a shadow stream in parallel.

    Returns a dict with the primary text, the shadow text, per-step
    shadow records, and a summary.
    """
    import torch

    device = model.device
    n_layers = model.config.num_hidden_layers
    d_model = model.config.hidden_size

    enc = tokenizer(prompt_text, return_tensors="pt", add_special_tokens=False)
    input_ids = enc.input_ids.to(device)
    attn = torch.ones_like(input_ids)

    steerer = ResidualSteerer(model, layer)
    if steer_vec is not None:
        steerer.set_vector(steer_vec)

    tracker = ShadowTracker(steer_vec, n_layers,
                            enabled=track_shadow,
                            max_steps=max_track_steps)

    def to_numpy(out):
        """Pull per-layer last-token states off the GPU in ONE transfer.

        Naively doing `h[0,-1,:].cpu().numpy()` per layer issues 29
        separate device syncs per stream per step; stacking first turns
        that into one. On a shared-filesystem box that difference is
        the whole runtime.
        """
        stacked = torch.stack([h[0, -1, :] for h in out.hidden_states])
        return stacked.float().cpu().numpy()

    # --- prime the primary stream ---
    with steerer, torch.inference_mode():
        out_p = model(input_ids=input_ids, attention_mask=attn,
                      output_hidden_states=True, use_cache=True, return_dict=True)
    past_p = out_p.past_key_values
    logits_p = out_p.logits[0, -1, :].float()
    hs_p = to_numpy(out_p)

    shadow_ok = track_shadow and steer_vec is not None
    if shadow_ok:
        # --- prime the shadow stream (identical but unsteered) ---
        steerer.clear()
        with steerer, torch.inference_mode():
            out_s = model(input_ids=input_ids, attention_mask=attn,
                          output_hidden_states=True, use_cache=True,
                          return_dict=True)
        past_s = out_s.past_key_values
        logits_s = out_s.logits[0, -1, :].float()
        hs_s = to_numpy(out_s)
        # Re-arm the steerer for subsequent steps.
        steerer.set_vector(steer_vec)
        tracker.compare(-1, "<prompt>", hs_p, hs_s,
                        logits_p.cpu().numpy(), logits_s.cpu().numpy())

    primary_ids: List[int] = []
    shadow_ids: List[int] = []
    tokens: List[str] = []

    eos = tokenizer.eos_token_id
    with torch.inference_mode():
        for step in range(max_new_tokens):
            next_p = int(torch.argmax(logits_p))
            next_s = int(torch.argmax(logits_s)) if shadow_ok else next_p

            if next_p == eos:
                break
            primary_ids.append(next_p)
            shadow_ids.append(next_s)
            tokens.append(tokenizer.decode([next_p]))

            # Teacher-force: both streams consume the primary's token.
            step_input = torch.tensor([[next_p]], device=device)
            attn = torch.cat(
                [attn, torch.ones((1, 1), device=device, dtype=attn.dtype)], dim=1
            )

            with steerer:
                out_p = model(input_ids=step_input, attention_mask=attn,
                              past_key_values=past_p, output_hidden_states=True,
                              use_cache=True, return_dict=True)
            past_p = out_p.past_key_values
            logits_p = out_p.logits[0, -1, :].float()
            hs_p = to_numpy(out_p)

            if shadow_ok:
                steerer.clear()
                with steerer:
                    out_s = model(input_ids=step_input, attention_mask=attn,
                                  past_key_values=past_s, output_hidden_states=True,
                                  use_cache=True, return_dict=True)
                past_s = out_s.past_key_values
                logits_s = out_s.logits[0, -1, :].float()
                hs_s = to_numpy(out_s)
                steerer.set_vector(steer_vec)

                tracker.compare(step, tokens[-1], hs_p, hs_s,
                                logits_p.cpu().numpy(), logits_s.cpu().numpy())

    return {
        "primary_text": tokenizer.decode(primary_ids, skip_special_tokens=True),
        "shadow_text": tokenizer.decode(shadow_ids, skip_special_tokens=True),
        "primary_ids": primary_ids,
        "shadow_ids": shadow_ids,
        "tokens": tokens,
        "n_steps": len(primary_ids),
        "shadow": tracker,
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def format_result(res: dict, direction: str, strength: float, layer: int,
                  steer_norm: float, verbose: bool = True) -> str:
    tracker: ShadowTracker = res["shadow"]
    summ = tracker.summary()
    lines = []
    lines.append("=" * 68)
    lines.append(f"  {direction}  ·  strength {strength:.3f}  ·  layer L{layer}")
    lines.append("=" * 68)
    lines.append(f"  injected ‖v‖        : {steer_norm:.4f}")
    lines.append(f"  steps generated      : {res['n_steps']}")
    if summ.get("n_steps", 0) == 0:
        lines.append("  (no shadow tracking — was the vector None?)")
        return "\n".join(lines)

    lines.append(f"  token agreement      : {summ['token_agreement']:.1%}")
    fd = summ.get("first_diverged_step")
    lines.append(f"  first token diverged : "
                 f"{'step ' + str(fd) if fd is not None else 'never'}")
    lines.append(f"  mean logit KL        : {summ['mean_logit_kl']:.4f} nats")
    lines.append(f"  entropy  steered     : {summ['mean_entropy_primary']:.4f}")
    lines.append(f"  entropy  unsteered   : {summ['mean_entropy_shadow']:.4f}")
    lines.append(f"  Δentropy             : "
                 f"{summ['mean_entropy_primary'] - summ['mean_entropy_shadow']:+.4f}")
    lines.append(f"  max divergence       : {summ['max_divergence']:.4f}")
    lines.append(f"  mean divergence      : {summ['mean_divergence']:.4f}")

    curve = summ.get("layer_curve") or {}
    if curve:
        lines.append("")
        lines.append("  Divergence by depth (1.0 = identical, 0.0 = orthogonal):")
        layers = curve["layer"]
        coss = curve["mean_cosine"]
        rels = curve["mean_rel_shift"]
        # Print every 3rd layer to keep it readable.
        for i in range(0, len(layers), 3):
            bar_n = int(round(max(0.0, 1.0 - coss[i]) * 40))
            bar = "█" * bar_n
            lines.append(
                f"    L{layers[i]:>2}  cos={coss[i]:.3f}  "
                f"relΔ={rels[i]:.3f}  {bar}"
            )
        inject_idx = layer + 1  # +1 for the embedding slot at index 0
        if 0 <= inject_idx < len(layers):
            lines.append(f"    ↑ injected at L{layer} "
                         f"(cos={coss[inject_idx]:.3f})")

    if verbose:
        lines.append("")
        lines.append("  steered output:")
        lines.append("    " + res["primary_text"][:400].replace("\n", "\n    "))
        if summ.get("token_agreement", 1.0) < 1.0:
            lines.append("  unsteered output:")
            lines.append("    " + res["shadow_text"][:400].replace("\n", "\n    "))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(args) -> int:
    registry = SteeringRegistry(Path(args.vector_dir) if args.vector_dir else None)
    if not registry.load():
        print(f"ERROR: {registry.load_error}")
        print("Run: python3 backend/examples/compute_steering_vectors.py")
        return 1

    print(f"registry: {len(registry.names)} vectors from {registry.vector_dir}")
    print(f"         {', '.join(registry.names)}")
    print()

    if not registry.has(args.direction):
        print(f"ERROR: unknown direction '{args.direction}'")
        return 1

    # Scale reference: how big the hidden state actually is at the
    # target layer. Without this, "strength" means wildly different
    # things at different layers.
    #
    # Prefer the already-measured profile (layer_profiles.json). It is
    # both the authoritative source and cheap — re-deriving it by
    # re-reading the .npz files takes minutes on a network filesystem,
    # which previously stalled the run before it started.
    layer_rms = args.layer_rms
    source = "--layer-rms"
    if layer_rms is None:
        n_cal = registry.load_layer_scales(
            Path(args.layer_profiles) if args.layer_profiles else None
        )
        if n_cal and registry.has_rms(args.layer):
            layer_rms = registry.layer_rms(args.layer)
            source = f"layer_profiles.json ({n_cal} layers)"
        else:
            layer_rms = _measure_layer_rms(args, layer=args.layer)
            source = "re-measured from .npz"
            if layer_rms is None:
                layer_rms = 1.0
                source = "FALLBACK 1.0 (uncalibrated — treat strength as arbitrary)"
    registry.set_layer_rms(args.layer, layer_rms)
    print(f"layer L{args.layer} ‖h‖ reference: {layer_rms:.2f}  [{source}]")
    if source.startswith("FALLBACK"):
        print("  ⚠ no measured scale for this layer; results are not "
              "comparable across layers or against the web UI.")
    print()

    prompts = _gather_prompts(args)
    if not prompts:
        print("ERROR: no prompts")
        return 1

    model, tok = load_model(args.model_path, args.device, args.dtype)
    print(f"model loaded: {args.model_path} on {args.device}")
    print()

    all_summaries = []
    for pi, (label, prompt_text) in enumerate(prompts):
        for strength in args.sweep:
            vec = registry.scaled(args.direction, strength, args.layer)
            if vec is None:
                print(f"  could not build vector for {args.direction}")
                continue
            t0 = time.time()
            res = run_dual_stream(
                model, tok, prompt_text, vec, args.layer,
                max_new_tokens=args.max_new_tokens,
                track_shadow=not args.no_shadow,
                max_track_steps=args.max_track_steps,
            )
            dt = time.time() - t0
            # Report the norm actually injected, not a re-derivation of
            # it — if the scaling ever changes, the printed number would
            # otherwise quietly stop matching what the model received.
            print(format_result(res, args.direction, strength, args.layer,
                                float(np.linalg.norm(vec)),
                                verbose=args.verbose))
            print(f"  wallclock: {dt:.1f}s")
            print()

            all_summaries.append({
                "prompt_label": label,
                "direction": args.direction,
                "strength": strength,
                "layer": args.layer,
                "n_steps": res["n_steps"],
                "primary_text": res["primary_text"],
                "shadow_text": res["shadow_text"],
                "summary": res["shadow"].summary(),
            })

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(all_summaries, indent=2, ensure_ascii=False))
        print(f"wrote {len(all_summaries)} result(s) → {out}")
    return 0


def _gather_prompts(args) -> List[Tuple[str, str]]:
    if args.prompt:
        msgs = [{"role": "system", "content": AIME_SYSTEM},
                {"role": "user", "content": args.prompt}]
        return [("prompt", _apply_template(args, msgs))]
    if args.aime_split:
        from core.aime_loader import load_aime
        problems = load_aime(args.aime_split)
        if args.limit:
            problems = problems[: args.limit]
        out = []
        for p in problems:
            msgs = [{"role": "system", "content": AIME_SYSTEM},
                    {"role": "user", "content": p["problem"]}]
            out.append((p["id"], _apply_template(args, msgs)))
        return out
    msgs = [{"role": "system", "content": AIME_SYSTEM},
            {"role": "user", "content": "What is 17 * 23?"}]
    return [("demo", _apply_template(args, msgs))]


def _apply_template(args, msgs) -> str:
    from transformers import AutoTokenizer
    tok = getattr(args, "_tok", None)
    if tok is None:
        tok = AutoTokenizer.from_pretrained(args.model_path)
        args._tok = tok
    return tok.apply_chat_template(
        msgs, tokenize=False, add_generation_prompt=True
    )


def _measure_layer_rms(args, layer: int) -> Optional[float]:
    """Measure ‖h‖/√d at `layer` from the collected dataset, if present."""
    root = Path(args.data_root)
    if not root.is_dir():
        return None
    files = sorted(root.glob("*.npz"))[: args.rms_sample]
    if not files:
        return None
    acc, n = 0.0, 0
    for f in files:
        try:
            d = np.load(f, allow_pickle=True)
            if "hidden_states" not in d.files:
                continue
            hs = d["hidden_states"]
            if hs.ndim != 3 or layer >= hs.shape[1]:
                continue
            sl = hs[:: max(1, hs.shape[0] // 64), layer, :].astype(np.float32)
            acc += float((sl ** 2).sum(axis=1).mean())
            n += sl.shape[0]
        except Exception:
            continue
    if n == 0:
        return None
    return float(np.sqrt(acc / n))


def cli():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--prompt", type=str, help="A single prompt")
    ap.add_argument("--aime-split", type=str, help="Run a builtin AIME split")
    ap.add_argument("--limit", type=int, default=3, help="Cap #problems")
    ap.add_argument("--direction", type=str, default="confidence_up")
    ap.add_argument("--sweep", type=float, nargs="+", default=None,
                    help="Multiple strengths to try (overrides --strength)")
    ap.add_argument("--strength", type=float, default=0.1)
    ap.add_argument("--layer", type=int, default=14)
    ap.add_argument("--layer-rms", type=float, default=None,
                    help="Override the measured state-norm scale reference")
    ap.add_argument("--layer-profiles", type=str, default=None,
                    help="layer_profiles.json to read the scale from "
                         "(default: alongside the steering vectors)")
    ap.add_argument("--max-new-tokens", type=int, default=256)
    ap.add_argument("--max-track-steps", type=int, default=None)
    ap.add_argument("--no-shadow", action="store_true",
                    help="Skip the counterfactual stream (halves the cost)")
    ap.add_argument("--model-path", type=str,
                    default=os.environ.get(
                        "QWEN3_MODEL_PATH",
                        "/home/zhourui/.cache/huggingface/models/"
                        "Qwen--Qwen3-1.7B/snapshots/master"))
    ap.add_argument("--device", type=str, default="cuda:0")
    ap.add_argument("--dtype", default="bfloat16",
                    choices=["bfloat16", "float16", "float32"])
    ap.add_argument("--vector-dir", type=str, default=None)
    ap.add_argument("--data-root", type=str,
                    default="datasets/aime_qwen3_1p7b_16k_fp16/aime",
                    help="Used only to measure the layer RMS scale")
    ap.add_argument("--rms-sample", type=int, default=8)
    ap.add_argument("--out", type=str, default=None, help="Write JSON here")
    ap.add_argument("--verbose", action="store_true", default=True)
    args = ap.parse_args()
    if args.sweep is None:
        args.sweep = [args.strength]
    return main(args)


if __name__ == "__main__":
    raise SystemExit(cli())
