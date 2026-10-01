"""Run a *long* chain-of-thought generation and measure what the steer did
to the **answer**, not just to the representation.

Why this file exists
--------------------
The 1024-token study (Finding 9/10) established two things and ran into a
third:

  * an intervention rewrites the chain of thought early — by ~50 chars;
  * but the measured effect size collapses as the generation gets longer
    (60 tokens: agreement 0.940 / KL 0.136; 1024 tokens: 0.995 / 0.0005);
  * and the **answer-level** effect was *structurally unmeasurable*, because
    `</think>` never closed inside 1024 tokens. 0/96 runs reached an answer.

That third point is not a finding about steering. It is a statement about the
budget we happened to give the model. This file is the one that reopens it at
32k, where the chain of thought has room to actually finish.

Two phases, and the order matters
---------------------------------
``calibrate``
    Unsteered, single stream, 32k budget. Answers exactly one question:
    *how many tokens does this model need before it closes `</think>`?*
    Nothing downstream can be sized without it, and guessing wrong costs
    either a truncated run (the same structural failure as before, now at
    5x the price) or a 30x oversized one.

``measure``
    Dual stream (steered + counterfactual shadow), budget taken from the
    calibration. This is where `closed_think`, answer extraction and
    answer-level change become measurable.

Design note — the thing that breaks at 32k
-----------------------------------------
`core/shadow.py` stores one `StepShadow` per step, each holding one
`LayerShift` dataclass per layer. At 32 768 steps x 29 layers that is
~950 000 dataclass instances: gigabytes of allocator churn, and a
`layer_curve()` that walks all of them at the end. Meanwhile the cheap
statistics we actually need an *exact* value for — token agreement, mean
KL, first divergence step — only need running sums.

So this file splits them deliberately:

  * ``_LongAccumulator`` keeps **full-coverage** running sums for
    agreement / KL / entropy / first-diverged. Every step is counted.
  * per-layer cosine & rel-shift are accumulated on a **stride**
    (``--track-stride``, default 64). Those curves describe the *shape* of
    the divergence, not an exact total, and 512 samples is already dense
    relative to the noise floor.

Reporting a subsampled curve as if it were full-coverage is the failure
mode this split exists to prevent, so ``n_tracked`` and ``n_steps`` are
always both reported and a reader can see the ratio.

Answers are extracted with the *same* ``extract_answer`` /
``split_think`` the earlier analysis used, imported from
``analyse_cot_divergence``. Re-implementing them here would risk the two
studies silently disagreeing about what "the answer" is — a bug that is
invisible in every single run and fatal when the numbers are compared.

Usage
-----
    # Phase 1 — how long does Qwen3 need?
    python3 backend/examples/run_long_cot.py \
        --model-path /models/Qwen3-0.6B \
        --problems-file backend/examples/output/problem_index.json \
        --limit 2 --mode calibrate --max-new-tokens 32768 \
        --out backend/examples/output/longcal_06b.json

    # Phase 2 — with the calibrated budget
    python3 backend/examples/run_long_cot.py \
        --model-path /models/Qwen3-0.6B \
        --problems-file backend/examples/output/problem_index.json \
        --limit 8 --mode measure --directions confidence_up \
        --layer 20 --sweep 0.2 --max-new-tokens <from phase 1> \
        --out backend/examples/output/long_06b_L20.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

# Reuse the tested extractors rather than re-deriving them. If these ever
# disagree with the 1024-token study, that must be a deliberate edit to one
# implementation, not an accident of copy-paste.
from analyse_cot_divergence import (  # noqa: E402
    extract_answer,
    extract_answer_sourced,
    split_think,
    _selftest as _extractor_selftest,
)

from core.shadow import (  # noqa: E402
    _entropy,
    _kl,
    _log_softmax,
)
from core.steering import SteeringRegistry  # noqa: E402
from run_intervention import (  # noqa: E402
    AIME_SYSTEM,
    ResidualSteerer,
    load_model,
)


# ---------------------------------------------------------------------------
# Cheap-vs-expensive split
# ---------------------------------------------------------------------------


class _LongAccumulator:
    """Full-coverage running stats plus a strided per-layer curve.

    ``self.steps`` keeps one dict per *tracked* step only. Everything in
    ``summary()`` under "full coverage" counts every generated step.
    """

    def __init__(self, n_layers: int, stride: int, unit: np.ndarray):
        self.n_layers = n_layers
        self.stride = max(1, stride)
        self.unit = unit

        # --- full coverage ---
        self.n_steps = 0
        self.n_match = 0
        self.sum_kl = 0.0
        self.sum_ent_p = 0.0
        self.sum_ent_s = 0.0
        self.n_bad = 0
        self.first_diverged: Optional[int] = None
        self.kl_series: List[float] = []
        self.match_series: List[int] = []

        # --- strided, per-layer ---
        self.n_seen = 0
        self.n_tracked = 0
        self._cos = np.zeros(n_layers + 1, dtype=np.float64)
        self._rel = np.zeros(n_layers + 1, dtype=np.float64)
        self.track: List[dict] = []

    def cheap_step(self, step: int, logits_p, logits_s) -> None:
        """One primary-vs-shadow logits comparison. Runs every step."""
        pl = np.asarray(logits_p, dtype=np.float64).reshape(-1)
        sl = np.asarray(logits_s, dtype=np.float64).reshape(-1)

        self.n_steps += 1
        lp, ls = _log_softmax(pl), _log_softmax(sl)
        if not (np.all(np.isfinite(lp)) and np.all(np.isfinite(ls))):
            self.n_bad += 1
            return

        kl = _kl(sl, pl)
        ent_p, ent_s = _entropy(pl), _entropy(ls)
        if not (np.isfinite(kl) and np.isfinite(ent_p) and np.isfinite(ent_s)):
            self.n_bad += 1
            return

        match = int(np.argmax(pl)) == int(np.argmax(sl))
        self.sum_kl += kl
        self.sum_ent_p += ent_p
        self.sum_ent_s += ent_s
        self.n_match += int(match)
        self.kl_series.append(kl)
        self.match_series.append(int(match))
        if not match and self.first_diverged is None:
            self.first_diverged = step

    def layer_step(self, step: int, token: str, get_p, get_s) -> None:
        """The expensive per-layer diff. Called every step, records on the
        stride.

        ``get_p`` / ``get_s`` are *callables* producing the per-layer states,
        not the states themselves. That is deliberate: pulling 29 hidden
        states off the GPU costs a real device sync, so the caller has to be
        able to skip it — and a caller-side ``if step % stride`` guard would
        be a second, independent copy of the sampling rule. Two copies of a
        rule can disagree, and the symptom is a curve that looks completely
        normal but sits on no defined grid. One predicate, evaluated once.
        """
        if self.n_seen % self.stride != 0:
            self.n_seen += 1
            return
        self.n_seen += 1
        self.n_tracked += 1
        idx = self.n_seen - 1
        hs_p, hs_s = get_p(), get_s()

        cos_row, rel_row, shift_row = [], [], []
        for p, s in zip(hs_p, hs_s):
            p = np.asarray(p, dtype=np.float32).reshape(-1)
            s = np.asarray(s, dtype=np.float32).reshape(-1)
            sn = float(np.linalg.norm(s))
            d = float(np.linalg.norm(p - s))
            cos_row.append(float(np.clip(
                np.dot(p, s) / (np.linalg.norm(p) * sn + 1e-8), -1.0, 1.0)))
            rel_row.append(d / (sn + 1e-8))
            shift_row.append(d)
        self._cos += np.asarray(cos_row)
        self._rel += np.asarray(rel_row)
        self.track.append({
            "step": idx, "token": token,
            "cosine": cos_row, "rel_shift": rel_row, "shift": shift_row,
        })

    def layer_curve(self) -> dict:
        if self.n_tracked == 0:
            return {}
        return {
            "layer": list(range(-1, self.n_layers)),
            "mean_cosine": (self._cos / self.n_tracked).tolist(),
            "mean_rel_shift": (self._rel / self.n_tracked).tolist(),
        }

    def summary(self) -> dict:
        good = max(1, self.n_steps - self.n_bad)
        return {
            "n_steps": self.n_steps,
            # Renamed from "n_bad_steps", which read like "steps where the two
            # streams disagreed" and is not that. It counts steps whose KL or
            # entropy came out non-finite — a numerical-garbage counter, and
            # the two arms disagreeing is `token_agreement` and
            # `first_diverged_step`. The old name invited reading 0 as "the
            # arms never diverged" on a run where they diverged on 8% of steps.
            "n_bad_numeric_steps": self.n_bad,
            "n_bad_meaning": ("steps where KL/entropy was non-finite; this is "
                              "NOT the number of steps the two arms disagreed"),
            "n_tracked": self.n_tracked,
            "track_stride": self.stride,
            "full_coverage_note": (
                "agreement / KL / entropy count EVERY generated step; "
                "layer curves are strided by "
                f"{self.stride} ({self.n_tracked}/{self.n_steps} sampled)"
            ),
            "token_agreement": self.n_match / good if self.n_bad < self.n_steps
            else None,
            "first_diverged_step": self.first_diverged,
            "mean_logit_kl": self.sum_kl / good,
            "mean_entropy_primary": self.sum_ent_p / good,
            "mean_entropy_shadow": self.sum_ent_s / good,
            # The per-step match bits are what distinguish "the perturbation
            # compounds into a different derivation" from "it flips a few
            # tokens early and the chains re-synchronise". A single mean
            # cannot tell those apart — 0.94 over 6500 steps is consistent with
            # both. 6507 bits is 814 bytes, so there was no reason to drop it.
            "match_bits_b64": self._match_bits_b64(),
            "layer_curve": self.layer_curve(),
        }

    def _match_bits_b64(self) -> Optional[str]:
        if not self.match_series:
            return None
        import base64
        bits = np.packbits(np.asarray(self.match_series, dtype=np.uint8))
        return base64.b64encode(bits.tobytes()).decode("ascii")


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

_THINK_CLOSE = "</think>"
_THINK_OPEN = "<think>"


def generate(model, tokenizer, prompt_text: str, max_new_tokens: int,
             steer_vec: Optional[np.ndarray] = None, layer: int = 20,
             track_stride: int = 0,
             progress_every: int = 2048) -> dict:
    """Greedy decode, optionally with a steered primary + unsteered shadow.

    ``track_stride == 0`` means calibration mode: no shadow, no hidden
    states, one forward per step. That is ~4x cheaper and is all phase 1
    needs.
    """
    import torch

    device = model.device
    n_layers = model.config.num_hidden_layers
    measure = track_stride > 0 and steer_vec is not None

    enc = tokenizer(prompt_text, return_tensors="pt", add_special_tokens=False)
    input_ids = enc.input_ids.to(device)
    attn = torch.ones_like(input_ids)

    steerer = ResidualSteerer(model, layer)
    if steer_vec is not None:
        steerer.set_vector(steer_vec)

    def to_numpy(out):
        # One device sync per stream per step instead of n_layers+1 of them.
        stacked = torch.stack([h[0, -1, :] for h in out.hidden_states])
        return stacked.float().cpu().numpy()

    with steerer, torch.inference_mode():
        out_p = model(input_ids=input_ids, attention_mask=attn,
                      output_hidden_states=measure, use_cache=True, return_dict=True)
    past_p, logits_p = out_p.past_key_values, out_p.logits[0, -1, :].float()

    acc = None
    past_s = logits_s = None
    if measure:
        v = np.asarray(steer_vec, dtype=np.float32).reshape(-1)
        acc = _LongAccumulator(n_layers, track_stride, v / max(1e-8, np.linalg.norm(v)))
        steerer.clear()
        with steerer, torch.inference_mode():
            out_s = model(input_ids=input_ids, attention_mask=attn,
                          output_hidden_states=True, use_cache=True, return_dict=True)
        past_s, logits_s = out_s.past_key_values, out_s.logits[0, -1, :].float()
        steerer.set_vector(steer_vec)
        acc.layer_step(0, "<prompt>", lambda: to_numpy(out_p), lambda: to_numpy(out_s))
        acc.cheap_step(-1, logits_p.cpu().numpy(), logits_s.cpu().numpy())

    primary_ids: List[int] = []
    shadow_ids: List[int] = []
    open_step: Optional[int] = None
    close_step: Optional[int] = None
    hit_eos = False
    t0 = time.time()

    eos = tokenizer.eos_token_id
    with torch.inference_mode():
        for step in range(max_new_tokens):
            next_p = int(torch.argmax(logits_p))
            next_s = int(torch.argmax(logits_s)) if measure else next_p

            if next_p == eos:
                hit_eos = True
                break

            tok_str = tokenizer.decode([next_p])
            primary_ids.append(next_p)
            shadow_ids.append(next_s)
            if open_step is None and _THINK_OPEN in tok_str:
                open_step = len(primary_ids) - 1
            if close_step is None and _THINK_CLOSE in tok_str:
                close_step = len(primary_ids) - 1

            if progress_every and (len(primary_ids) % progress_every == 0):
                rate = len(primary_ids) / max(1e-9, time.time() - t0)
                print(f"    step {len(primary_ids):>6}  "
                      f"({rate:.1f} tok/s  eta "
                      f"{(max_new_tokens - len(primary_ids)) / rate / 60:.1f} min)",
                      flush=True)

            step_input = torch.tensor([[next_p]], device=device)
            attn = torch.cat(
                [attn, torch.ones((1, 1), device=device, dtype=attn.dtype)], dim=1
            )

            with steerer:
                out_p = model(input_ids=step_input, attention_mask=attn,
                              past_key_values=past_p,
                              output_hidden_states=measure,
                              use_cache=True, return_dict=True)
            past_p, logits_p = out_p.past_key_values, out_p.logits[0, -1, :].float()

            if measure:
                steerer.clear()
                with steerer:
                    out_s = model(input_ids=step_input, attention_mask=attn,
                                  past_key_values=past_s, output_hidden_states=True,
                                  use_cache=True, return_dict=True)
                past_s, logits_s = out_s.past_key_values, out_s.logits[0, -1, :].float()
                steerer.set_vector(steer_vec)

                lp = logits_p.cpu().numpy()
                ls = logits_s.cpu().numpy()
                acc.cheap_step(len(primary_ids) - 1, lp, ls)
                # Bound, not late-closing: `out_p` is reassigned on the next
                # loop iteration, so a bare lambda would read whatever the
                # variable holds *then* if this were ever deferred.
                acc.layer_step(
                    len(primary_ids) - 1, tok_str,
                    lambda o=out_p: to_numpy(o), lambda o=out_s: to_numpy(o),
                )

    p_text = tokenizer.decode(primary_ids, skip_special_tokens=True)
    s_text = (tokenizer.decode(shadow_ids, skip_special_tokens=True)
              if measure else "")

    p_reason, p_ans = split_think(p_text)
    s_reason, s_ans = split_think(s_text) if measure else ("", "")
    return {
        "primary_text": p_text,
        "shadow_text": s_text,
        "primary_ids": primary_ids,
        "shadow_ids": shadow_ids,
        "n_steps": len(primary_ids),
        "hit_eos": hit_eos,
        "budget": max_new_tokens,
        "wallclock_s": time.time() - t0,
        "think_open_step": open_step,
        "think_close_step": close_step,
        "closed_think": close_step is not None,
        "n_reason_chars": len(p_reason),
        "n_answer_chars": len(p_ans),
        "answer": _answer_of(p_ans, p_text),
        "answer_source": _answer_source(p_ans, p_text, _answer_of(p_ans, p_text)),
        "answer_guessed": not p_ans.strip() and close_step is None,
        # The shadow gets the *same* fallback chain as the primary. Getting
        # this wrong is silent: an unclosed shadow chain would fall back to
        # the reasoning segment here and report a number that is really
        # "last integer mentioned anywhere in the CoT".
        "shadow_answer": _answer_of(s_ans, s_text) if measure else None,
        "shadow_answer_source": (
            _answer_source(s_ans, s_text, _answer_of(s_ans, s_text))
            if measure else None),
        "shadow_answer_guessed": bool(
            measure and not s_ans.strip() and _THINK_CLOSE not in s_text),
        "shadow_closed_think": bool(measure and _THINK_CLOSE in s_text),
        "acc": acc,
    }


def _answer_of(answer_part: str, full_text: str,
               strict: bool = False) -> Optional[int]:
    """Answer from the post-`</think>` segment, optionally refusing to guess.

    An unclosed chain leaves that segment empty, so the default behaviour
    falls back to scanning the whole response. That fallback is the right
    default for a viewer and the wrong one for a *comparison*: see
    ``extract_answer_sourced`` — on an unclosed chain it returns the last
    integer in a truncated derivation, which is not an answer at all.

    ``strict=True`` reads only the post-`</think>` segment and reports
    ``None`` when it is empty. The 32k study uses strict, because "the
    intervention changed the answer" is a claim that has to survive a
    reader noticing that the chains never closed.
    """
    if answer_part.strip():
        a = extract_answer(answer_part)
        if a is not None:
            return a
    if strict:
        return None
    return extract_answer(full_text)


def _answer_source(answer_part: str, full_text: str,
                   value: Optional[int]) -> str:
    """Which extraction rule produced ``value`` — for the record, not for
    branching. ``unclosed`` means the guess came from a chain of thought
    that never emitted an answer segment."""
    if value is None:
        return "unknown"
    src = extract_answer_sourced(answer_part)[1] if answer_part.strip() else "none"
    if src in ("explicit", "boxed"):
        return src
    return "unclosed_guess" if not answer_part.strip() else src


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


def build_prompt(tok, problem: str) -> str:
    msgs = [{"role": "system", "content": AIME_SYSTEM},
            {"role": "user", "content": problem}]
    # Thinking mode must be explicit. The Qwen3 template's default has
    # changed between point releases, and a silent flip to no-think would
    # make every number here about a different model behaviour.
    try:
        return tok.apply_chat_template(
            msgs, tokenize=False, add_generation_prompt=True, enable_thinking=True
        )
    except TypeError:
        print("  (template rejected enable_thinking; using its default)")
        return tok.apply_chat_template(
            msgs, tokenize=False, add_generation_prompt=True
        )


def load_problems(path: Optional[str], limit: Optional[int]) -> List[dict]:
    if not path:
        return [{"id": "demo", "prompt": "What is 17 * 23?", "correct": None}]
    data = json.loads(Path(path).read_text())
    probs = list(data.values()) if isinstance(data, dict) else list(data)
    if limit:
        probs = probs[:limit]
    return probs


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _accumulator_selftest() -> None:
    """Round-trip the per-step match bits through the encoder.

    A packbits/base64 codec is easy to write in a way that silently loses the
    last partial byte or transposes the order, and the symptom is a plausible
    curve rather than an error. So this checks the decoded length and a few
    specific positions against the input, rather than comparing a copy of the
    encoder written next to it.
    """
    import base64

    acc = _LongAccumulator(n_layers=4, stride=64,
                           unit=np.zeros(8, dtype=np.float32))
    pattern = [1] * 300 + [0] * 5 + [1, 0, 1, 1, 0, 0, 0]   # 312 steps
    fake_p = np.zeros(16)
    fake_s = np.zeros(16)
    for i, m in enumerate(pattern):
        # argmax equal when m == 1; make the shadow pick a different index else
        fake_p[:] = 0.0
        fake_s[:] = 0.0
        fake_p[1] = 1.0
        fake_s[1 if m else 2] = 1.0
        acc.cheap_step(i, fake_p, fake_s)

    s = acc.summary()
    assert s["n_steps"] == len(pattern), s["n_steps"]
    assert s["n_bad_numeric_steps"] == 0, s["n_bad_numeric_steps"]
    assert abs(s["token_agreement"] - sum(pattern) / len(pattern)) < 1e-12, \
        s["token_agreement"]
    assert s["first_diverged_step"] == 300, s["first_diverged_step"]

    raw = base64.b64decode(s["match_bits_b64"])
    bits = np.unpackbits(np.frombuffer(raw, dtype=np.uint8))[:len(pattern)]
    assert bits.tolist() == pattern, "match bits did not round-trip"
    assert len(bits) == len(pattern), (len(bits), len(pattern))
    print(f"accumulator self-test OK ({len(pattern)} steps, "
          f"{len(s['match_bits_b64'])} b64 chars, "
          f"first_div={s['first_diverged_step']})")


def main(args) -> int:
    if args.self_test:
        _extractor_selftest()
        _accumulator_selftest()
        print("self-test OK")
        return 0

    if not args.model_path:
        print("ERROR: --model-path is required unless --self-test")
        return 2

    if not args.stride_ok:
        print("refusing: --track-stride 0 with --mode measure silently "
              "degrades the run to calibration (no shadow, no answer "
              "comparison). Use --mode calibrate for that.")
        return 2

    model, tok = load_model(args.model_path, args.device, args.dtype)
    print(f"model: {args.model_path}  layers={model.config.num_hidden_layers} "
          f"d={model.config.hidden_size} maxpos={model.config.max_position_embeddings}")
    if args.max_new_tokens > model.config.max_position_embeddings - 256:
        print(f"  WARNING: budget {args.max_new_tokens} + prompt approaches the "
              f"position limit {model.config.max_position_embeddings}")
    print(f"budget: {args.max_new_tokens} new tokens   mode: {args.mode}")
    print()

    registry = None
    vectors: Dict[str, np.ndarray] = {}
    if args.mode == "measure":
        registry = SteeringRegistry(Path(args.vector_dir) if args.vector_dir else None)
        if not registry.load():
            print(f"ERROR: {registry.load_error}")
            return 1
        n_cal = registry.load_layer_scales(
            Path(args.layer_profiles) if args.layer_profiles else None)
        if n_cal and registry.has_rms(args.layer):
            rms, src = registry.layer_rms(args.layer), f"layer_profiles.json ({n_cal})"
        else:
            rms, src = 1.0, "FALLBACK 1.0 (uncalibrated)"
        registry.set_layer_rms(args.layer, rms)
        print(f"layer L{args.layer} ‖h‖ reference: {rms:.2f}  [{src}]")
        for d in args.directions:
            for s in args.sweep:
                v = registry.scaled(d, s, args.layer)
                if v is None:
                    print(f"  !! no vector for {d} @ L{args.layer}")
                    continue
                vectors[f"{d}@{s}"] = v
        print(f"vectors: {', '.join(vectors)}")
        print()

    problems = load_problems(args.problems_file, args.limit)
    print(f"{len(problems)} problem(s)")
    print()

    records = []
    for pi, prob in enumerate(problems):
        prompt = build_prompt(tok, prob["prompt"])
        if args.mode == "calibrate":
            cells = [("calibrate", None)]
        else:
            cells = list(vectors.items())
            if args.include_control:
                # A zero vector must be passed as zeros, NOT as None: None
                # turns the shadow off, which makes the control run produce
                # no comparison at all instead of an exactly-zero one.
                cells.insert(0, ("control_zero", np.zeros(model.config.hidden_size,
                                                           dtype=np.float32)))
        for name, vec in cells:
            print(f"[{pi + 1}/{len(problems)}] {prob['id']}  ·  {name}")
            res = generate(
                model, tok, prompt, args.max_new_tokens,
                steer_vec=vec, layer=args.layer,
                track_stride=args.track_stride,
            )
            rec = {
                "label": prob["id"],
                "cell": name,
                "n_steps": res["n_steps"],
                "budget": res["budget"],
                "hit_eos": res["hit_eos"],
                "truncated": not res["hit_eos"] and res["n_steps"] >= res["budget"],
                "closed_think": res["closed_think"],
                "think_open_step": res["think_open_step"],
                "think_close_step": res["think_close_step"],
                "n_reason_chars": res["n_reason_chars"],
                "n_answer_chars": res["n_answer_chars"],
                "answer": res["answer"],
                "answer_source": res["answer_source"],
                "shadow_answer": res["shadow_answer"],
                "shadow_answer_source": res["shadow_answer_source"],
                "shadow_closed_think": res["shadow_closed_think"],
                # Strict: an unclosed chain reports the answer as unknown.
                # The non-strict fallback returns the last integer in a
                # truncated derivation, which for problem 1987 produced a
                # confident 1 vs 2 across the two arms — a difference that
                # reads like a result and is not one.
                "answer_known": (res["answer"] is not None
                                 and not res["answer_guessed"]),
                "answer_guessed": res["answer_guessed"],
                "answer_changed": (
                    None if not res["answer_known"] or res["shadow_answer"] is None
                    or res["shadow_answer_guessed"]
                    else res["answer"] != res["shadow_answer"]
                ),
                "wallclock_s": res["wallclock_s"],
                "injected_norm": (
                    float(np.linalg.norm(vec)) if vec is not None else None
                ),
                "summary": res["acc"].summary() if res["acc"] else None,
            }
            records.append(rec)

            close = res["think_close_step"]
            print(f"  steps {res['n_steps']}"
                  f"{'  [TRUNCATED at budget]' if rec['truncated'] else ''}")
            print(f"  </think> at step {close if close is not None else 'NEVER'}"
                  f"   eos={res['hit_eos']}")
            print(f"  reason {res['n_reason_chars']} chars, "
                  f"answer {res['n_answer_chars']} chars, "
                  f"answer={res['answer']} (shadow={res['shadow_answer']})")
            if res["acc"]:
                s = rec["summary"]
                print(f"  agreement {s['token_agreement']}, "
                      f"KL {s['mean_logit_kl']:.5f}, "
                      f"first_div {s['first_diverged_step']}, "
                      f"tracked {s['n_tracked']}/{s['n_steps']}")
            print(f"  {res['wallclock_s'] / 60:.1f} min")
            print()

            if args.save_text:
                base = Path(args.out).with_suffix("")
                base.parent.mkdir(parents=True, exist_ok=True)
                base.with_name(
                    f"{base.name}_{pi:02d}_{name}_primary.txt"
                ).write_text(res["primary_text"])
                if res["shadow_text"]:
                    base.with_name(
                        f"{base.name}_{pi:02d}_{name}_shadow.txt"
                    ).write_text(res["shadow_text"])

    payload = {
        "model_path": args.model_path,
        "mode": args.mode,
        "layer": args.layer if args.mode == "measure" else None,
        "directions": args.directions if args.mode == "measure" else [],
        "sweep": args.sweep if args.mode == "measure" else [],
        "max_new_tokens": args.max_new_tokens,
        "track_stride": args.track_stride,
        "n_problems": len(problems),
        "records": records,
    }
    if args.out:
        p = Path(args.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        print(f"wrote {len(records)} record(s) → {p}")

    # Headline roll-up, because a 32k run is too long to read record by record.
    n = len(records)
    closed = sum(1 for r in records if r["closed_think"])
    known = sum(1 for r in records if r["answer_known"])
    trunc = sum(1 for r in records if r["truncated"])
    print()
    print("=" * 68)
    print(f"  closed </think> : {closed}/{n}")
    print(f"  answer extracted: {known}/{n}")
    print(f"  truncated       : {trunc}/{n}")
    lens = [r["think_close_step"] for r in records
            if r["think_close_step"] is not None]
    if lens:
        print(f"  close step      : min {min(lens)}  median "
              f"{int(np.median(lens))}  max {max(lens)}")
    print("=" * 68)
    return 0


def cli() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--model-path", default=None,
                    help="Omitted only for --self-test, which must be able "
                         "to run before any model is downloaded")
    ap.add_argument("--device", default="cuda:0")
    ap.add_argument("--dtype", default="bfloat16")
    ap.add_argument("--problems-file", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--mode", choices=["calibrate", "measure"], default="calibrate")
    ap.add_argument("--directions", nargs="+", default=["confidence_up"])
    ap.add_argument("--sweep", nargs="+", type=float, default=[0.2])
    ap.add_argument("--layer", type=int, default=20)
    ap.add_argument("--vector-dir", default=None)
    ap.add_argument("--layer-profiles", default=None)
    ap.add_argument("--max-new-tokens", type=int, default=32768)
    ap.add_argument("--track-stride", type=int, default=64,
                    help="Record per-layer divergence every Nth step. "
                         "Agreement/KL always count every step.")
    ap.add_argument("--include-control", action="store_true",
                    help="Prepend an exactly-zero vector run as the control")
    ap.add_argument("--save-text", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--self-test", action="store_true",
                    help="Run the answer-extractor self-test and exit")
    args = ap.parse_args()
    # A zero stride in measure mode is the silent-degradation trap described
    # in the module docstring; make it a hard refusal rather than a warning.
    args.stride_ok = not (args.mode == "measure" and args.track_stride <= 0)
    return main(args)


if __name__ == "__main__":
    raise SystemExit(cli())
