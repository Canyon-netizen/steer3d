"""Collect **paired** hidden states: the same problem, run twice, once clean
and once steered, keeping the raw 2048-d residual stream for both.

Why this file exists
--------------------
Everything under ``output/intervention/`` records what the steer *did to the
text* — ``primary_text``, ``shadow_text``, and a ``summary`` of scalars.
None of it records what the steer did to the **representation**. That is
the gap this file fills: a viewer can be handed 96 runs' worth of token
strings and still be unable to draw a single point cloud of "the hidden
state moved".

Why two *independent* streams, not the dual-stream shadow
----------------------------------------------------------
``run_intervention.run_dual_stream`` already runs a counterfactual shadow, and
reusing it would have been cheaper. It is the wrong instrument here, for a
reason that is easy to miss:

    the shadow is **teacher-forced** — it consumes the primary's chosen
    token at every step.

So the shadow's hidden states answer the question *"given these tokens, how
would I represent them?"* — not *"if I were generating on my own, where
would I be?"*. The moment the two streams diverge (they do, around step
8-30 in practice) the shadow is describing a world that no longer exists.
Plotting a divergence map built from a teacher-forced stream would produce a
confident, plausible, and wrong picture — the same failure shape as every
other "looks fine, contents are wrong" bug in this project.

Two greedy streams on the same prompt, differing only in whether the residual
at one layer is offset, is the only version where "the hidden state moved"
means what a reader will assume it means.

What is stored
--------------
Only a handful of layers, but all of them, all steps, at full 2048-d
fidelity in fp16. Storing 28 layers x 1024 steps x 2048 x 2B is 112 KB per
token; a layer subset is what makes "keep the raw vectors" affordable.

    {4, 12, 20, 26} — deliberately straddling the injection layer 20, so the
    viewer can ask *did it move before the injection point, at the injection
    point, and how far did it propagate after it*. Those are three different
    questions and answering only one of them is how a steering demo turns
    into a steering assertion.

Everything else is derived, not stored: the per-step deltas, the alignment
of the delta with the steering vector itself, and the per-dimension breakdown
that ``build_dim_dictionary.py`` later turns into words.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from run_intervention import ResidualSteerer  # noqa: E402
from run_long_cot import (  # noqa: E402
    build_prompt,
    load_model,
    load_problems,
)
from run_long_cot import _answer_of  # noqa: E402
from analyse_cot_divergence import split_think  # noqa: E402

DEFAULT_LAYERS = (4, 12, 20, 26)


def run_one(model, tok, prompt: str, budget: int, layers: List[int],
            steer_vec: Optional[np.ndarray], layer: int,
            log_every: int = 256) -> dict:
    """Greedy decode, keeping the last-step residual at each layer in ``layers``.

    The steerer is entered even when ``steer_vec is None`` so the control arm
    walks *exactly* the same code path — same hooks installed, same context
    managers — and differs from the steered arm in one thing only: whether
    a vector was set. A control that skipped the hook machinery entirely
    would be a control that also tested "does having the hooks change
    anything", quietly.
    """
    steerer = ResidualSteerer(model, layer)
    if steer_vec is not None:
        steerer.set_vector(steer_vec)

    ids: List[int] = []
    # {layer: (steps, d)} preallocated; steps grows, d is fixed.
    store = {L: [] for L in layers}

    def last_residual(out) -> None:
        for L in layers:
            # hidden_states is a tuple of length n_layers+1, each (1, T, D).
            # [0] drops batch, [-1] takes the newest position only.
            store[L].append(out.hidden_states[L][0, -1, :].to(torch.float32).cpu().numpy())

    t0 = time.time()
    with steerer, torch.inference_mode():
        enc = tok(prompt, return_tensors="pt").to(model.device)
        out = model(**enc, output_hidden_states=True, use_cache=True, return_dict=True)
        past = out.past_key_values
        last_residual(out)
        nxt = int(torch.argmax(out.logits[0, -1, :]))
        for step in range(1, budget + 1):
            if step % log_every == 0 or step == budget:
                el = time.time() - t0
                print(f"    step {step:6d}  ({step / el:5.1f} tok/s  "
                      f"eta {(budget - step) / max(step / el, 1e-6) / 60:4.1f} min)",
                      flush=True)
            if nxt == tok.eos_token_id:
                break
            ids.append(nxt)
            out = model(input_ids=torch.tensor([[nxt]], device=model.device),
                        past_key_values=past, output_hidden_states=True,
                        use_cache=True, return_dict=True)
            past = out.past_key_values
            last_residual(out)
            nxt = int(torch.argmax(out.logits[0, -1, :]))

    text = tok.decode(ids, skip_special_tokens=True)
    # hs[i] is the residual at the position that *predicted* ids[i]; index 0 is
    # the prefill position, so the store is exactly one longer than the token
    # list. Trimming to len(ids) makes the two indexable by the same i, which
    # is the only way a viewer can put "the state" and "the token it chose"
    # next to each other without an off-by-one nobody notices.
    #
    # The empty case is real, not defensive padding: a stream whose very first
    # argmax is EOS produces zero tokens, and np.stack([]) raises. Shape (0, d)
    # keeps that trajectory representable instead of killing the run.
    d = int(model.config.hidden_size)
    hs = {L: (np.stack(store[L][:len(ids)]).astype(np.float16) if len(ids)
              else np.zeros((0, d), dtype=np.float16))
          for L in layers}
    return {
        "text": text,
        "ids": ids,
        "n_steps": len(ids),
        "hs": hs,
        "closed_think": "</think>" in text,
    }


def analyze(control: dict, steered: dict, layers: List[int],
            unit: Optional[np.ndarray]) -> dict:
    """Per-step and per-layer description of the difference between the arms.

    ``n_common`` is the number of leading steps at which the two arms emitted
    the *same* token. Beyond it the token sequences differ and "per-step
    delta" stops meaning a like-for-like comparison, so every per-step curve
    is reported over ``[:n_common]`` and the rest is labelled rather than
    silently averaged in.
    """
    c_ids, s_ids = control["ids"], steered["ids"]
    n_common = 0
    for a, b in zip(c_ids, s_ids):
        if a != b:
            break
        n_common += 1

    out: dict = {
        "n_steps_control": len(c_ids),
        "n_steps_steered": len(s_ids),
        "n_common_prefix": n_common,
        "diverged": n_common < min(len(c_ids), len(s_ids)),
        "per_layer": {},
    }
    m = min(n_common, control["n_steps"], steered["n_steps"])
    for L in layers:
        c = control["hs"][L][:m].astype(np.float32)
        s = steered["hs"][L][:m].astype(np.float32)
        d = s - c
        entry = {
            "n_compared": int(m),
            "rel_shift": [],      # ‖Δ‖ / ‖h_control‖
            "abs_shift": [],
            "cosine": [],
            "h_norm": [],
        }
        if unit is not None and m > 0:
            # How much of the move is *along the steering direction* rather
            # than incidental drift. 1.0 would mean "purely the steer".
            u = unit.astype(np.float32)
            u = u / max(float(np.linalg.norm(u)), 1e-8)
            proj = d @ u
            entry["proj_on_steer"] = proj.astype(np.float32).tolist()
            entry["proj_fraction"] = float(
                (proj ** 2).sum() / max((d ** 2).sum(), 1e-8))
        for i in range(m):
            hc = float(np.linalg.norm(c[i]))
            dd = float(np.linalg.norm(d[i]))
            entry["abs_shift"].append(dd)
            entry["rel_shift"].append(dd / max(hc, 1e-6))
            entry["h_norm"].append(hc)
            den = hc * float(np.linalg.norm(s[i]))
            entry["cosine"].append(float((c[i] @ s[i]) / den) if den > 1e-6 else 1.0)
        out["per_layer"][str(L)] = entry
    return out


def top_dims(delta_mean: np.ndarray, k: int = 24) -> List[dict]:
    """The 24 coordinates the steer moved most, by |signed| change.

    Signed, not absolute: "this dimension went *down*" is the part that tells
    a reader something, and sorting by magnitude alone throws the sign away.
    """
    order = np.argsort(-np.abs(delta_mean))[:k]
    return [{"dim": int(i), "delta": float(delta_mean[i])} for i in order]


def main(args) -> int:
    if not args.model_path:
        print("ERROR: --model-path is required")
        return 2

    model, tok = load_model(args.model_path, args.device, args.dtype)
    layers = sorted({int(x) for x in args.layers.split(",")})
    n_layers = model.config.num_hidden_layers
    bad = [L for L in layers if not (0 <= L < n_layers)]
    if bad:
        print(f"ERROR: layers {bad} outside 0..{n_layers - 1}")
        return 2
    print(f"model={args.model_path}  L={n_layers} d={model.config.hidden_size}")
    print(f"layers kept: {layers}   budget: {args.max_new_tokens}   "
          f"problems: {args.limit}")
    print()

    # ---- steering vector -------------------------------------------------
    unit: Optional[np.ndarray] = None
    vec: Optional[np.ndarray] = None
    if args.strength > 0:
        from core.steering import SteeringRegistry
        reg = SteeringRegistry(
            Path("output/steering_vectors")
            if Path("output/steering_vectors").is_dir() else None)
        if not reg.load():
            print(f"ERROR: {reg.load_error}")
            return 1
        n_cal = reg.load_layer_scales(Path("output/layer_profiles.json"))
        rms = reg.layer_rms(args.layer)
        print(f"direction={args.direction} strength={args.strength} "
              f"inject@L{args.layer}  ‖h‖(L{args.layer})={rms:.2f} "
              f"[{n_cal} calibrated layers]")
        if not reg.has_rms(args.layer):
            print(f"  WARNING no measured ‖h‖ for L{args.layer}; scaled() falls back "
                  f"to 1.0, so 'strength 0.2' is NOT 0.2x the residual norm here")
        unit = reg.unit_vector(args.direction)
        vec = reg.scaled(args.direction, args.strength, args.layer)
        if vec is None:
            print(f"ERROR: direction {args.direction!r} unavailable")
            return 1
        print(f"  ‖vec‖ = {np.linalg.norm(vec):.3f}  d={vec.size}")
    else:
        print("strength 0 -> running a single unsteered control only")

    problems = load_problems(args.problems, args.limit)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    for pi, prob in enumerate(problems, 1):
        pid = str(prob.get("id", pi))
        prompt = build_prompt(tok, prob["prompt"])
        print(f"\n[{pi}/{len(problems)}] problem {pid}")
        print(f"  {prob['prompt'][:90]}")

        print("  -- control (no injection)")
        ctl = run_one(model, tok, prompt, args.max_new_tokens, layers, None, args.layer)

        st: dict = {}
        if vec is not None:
            print("  -- steered")
            st = run_one(model, tok, prompt, args.max_new_tokens, layers, vec, args.layer)

        a_ans, a_think = _answer_of(split_think(ctl["text"])[1], ctl["text"])
        record = {
            "id": pid,
            "problem": prob["prompt"],
            "correct": prob.get("correct"),
            "layers": layers,
            "inject_layer": args.layer,
            "direction": args.direction,
            "strength": args.strength,
            "max_new_tokens": args.max_new_tokens,
            "n_steps": {"control": ctl["n_steps"]},
            "closed_think": {"control": ctl["closed_think"]},
            "answer": {"control": a_ans},
            "control": {"text": ctl["text"], "ids": ctl["ids"]},
        }
        if st:
            b_ans, _ = _answer_of(split_think(st["text"])[1], st["text"])
            record["n_steps"]["steered"] = st["n_steps"]
            record["closed_think"]["steered"] = st["closed_think"]
            record["answer"]["steered"] = b_ans
            record["steered"] = {"text": st["text"], "ids": st["ids"]}
            record["paired"] = analyze(ctl, st, layers, unit)
            mc = record["paired"]["n_common_prefix"]
            print(f"  common prefix: {mc} steps   "
                  f"diverged={record['paired']['diverged']}")
            for L in layers:
                e = record["paired"]["per_layer"][str(L)]
                if e["n_compared"]:
                    print(f"    L{L:<3d} rel_shift mean={np.mean(e['rel_shift']):.4f} "
                          f"max={np.max(e['rel_shift']):.4f}  "
                          f"cos min={np.min(e['cosine']):.4f}"
                          + (f"  proj_frac={e['proj_fraction']:.3f}"
                             if "proj_fraction" in e else ""))
                dm = (st["hs"][L][:e["n_compared"]].astype(np.float32)
                      - ctl["hs"][L][:e["n_compared"]].astype(np.float32)).mean(0)
                record.setdefault("top_dims", {})[str(L)] = top_dims(dm)

        np.savez_compressed(
            outdir / f"pair_{pid}.npz",
            **{f"control_L{L}": ctl["hs"][L] for L in layers},
            **({f"steered_L{L}": st["hs"][L] for L in layers} if st else {}),
            control_ids=np.asarray(ctl["ids"], dtype=np.int32),
            steered_ids=(np.asarray(st["ids"], dtype=np.int32) if st
                         else np.zeros(0, np.int32)),
            unit=(unit.astype(np.float32) if unit is not None
                  else np.zeros(1, np.float32)),
            layers=np.asarray(layers, dtype=np.int32),
        )
        record["hs_alignment"] = ("hs[i] is the residual at the position that "
                                  "predicted ids[i]; same i indexes both")
        (outdir / f"pair_{pid}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2))
        print(f"  wrote {outdir / f'pair_{pid}.npz'}")

    print(f"\ndone -> {outdir}")


def cli() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model-path", default="")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--dtype", default="bfloat16")
    ap.add_argument("--problems", default="")
    ap.add_argument("--limit", type=int, default=4)
    ap.add_argument("--max-new-tokens", type=int, default=1024)
    ap.add_argument("--layers", default=",".join(str(x) for x in DEFAULT_LAYERS))
    ap.add_argument("--direction", default="confidence_up")
    ap.add_argument("--strength", type=float, default=0.2)
    ap.add_argument("--layer", type=int, default=20, help="injection layer")
    ap.add_argument("--outdir", default="output/paired")
    a = ap.parse_args()
    return main(a)


if __name__ == "__main__":
    raise SystemExit(cli())
