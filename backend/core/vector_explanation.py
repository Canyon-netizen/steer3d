"""Context-dependent explanations of arbitrary residual-stream directions.

Observation measures association on recorded states. Response runs the actual
model at a fixed prefix, so downstream blocks and normalization are included.
Neither instrument identifies a reasoning algorithm or causal necessity.
"""
from __future__ import annotations

from typing import Callable, Mapping, Optional, Sequence

import numpy as np


def unit_direction(vector: np.ndarray) -> np.ndarray:
    v = np.asarray(vector, dtype=np.float64)
    if v.ndim != 1 or not v.size or not np.isfinite(v).all():
        raise ValueError("vector must be a finite, nonempty 1-D array")
    norm = float(np.linalg.norm(v))
    if not np.isfinite(norm) or norm == 0:
        raise ValueError("vector must have a finite, positive norm")
    return v / norm


def _correlations(scores: np.ndarray, values: np.ndarray) -> np.ndarray:
    """Columnwise Spearman; constants/missing denominators remain NaN."""
    from scipy.stats import rankdata

    valid = np.isfinite(values)
    if valid.sum() < 4 or np.ptp(values[valid]) == 0:
        return np.full(scores.shape[1], np.nan)
    x = rankdata(scores[valid], axis=0)
    y = rankdata(values[valid])
    x -= x.mean(axis=0)
    y -= y.mean()
    den = np.linalg.norm(x, axis=0) * np.linalg.norm(y)
    return np.divide(np.einsum("td,t->d", x, y), den,
                     out=np.full(scores.shape[1], np.nan), where=den > 0)


def explain_observations(
    records: Sequence[dict], vector: np.ndarray, *, n_random: int = 64,
    seed: int = 0, lag: int = 0, bootstrap_reps: int = 2000,
    evaluation_split: str = "unknown",
) -> dict:
    """Project states onto v and report problem-weighted associations.

    Each record supplies hidden (T,D), observables {name: (T,)}, problem_id,
    trajectory_id and optional texts. Random controls share the same states,
    masks and grouping. The null is isotropic directions, not label shuffling.
    All searched observables enter a maximum-statistic correction.
    """
    u = unit_direction(vector)
    if not records or n_random < 1 or lag < 0 or bootstrap_reps < 1:
        raise ValueError("need records, random controls, bootstrap reps and lag >= 0")
    if evaluation_split not in {"unknown", "independent", "overlap"}:
        raise ValueError("invalid evaluation_split")
    rng = np.random.default_rng(seed)
    random = rng.standard_normal((n_random, u.size))
    random /= np.linalg.norm(random, axis=1, keepdims=True)
    directions = np.vstack([u, random])
    names = sorted({name for r in records for name in r["observables"]})
    cells = {name: [] for name in names}
    examples = []
    total_tokens = 0
    ids = set()
    for rec in records:
        tid = rec["trajectory_id"]
        if tid in ids:
            raise ValueError(f"duplicate trajectory: {tid}")
        ids.add(tid)
        h = np.asarray(rec["hidden"], dtype=np.float64)
        if h.ndim != 2 or h.shape[1] != u.size or not np.isfinite(h).all():
            raise ValueError(f"invalid hidden states for {tid}")
        norm = np.linalg.norm(h, axis=1)
        if not h.shape[0] or np.any(norm == 0) or not np.isfinite(norm).all():
            raise ValueError(f"empty/zero or invalid hidden-state norms for {tid}")
        raw = np.einsum("td,kd->tk", h, directions, optimize=True)
        cosine = raw / norm[:, None]
        total_tokens += h.shape[0]
        stop = h.shape[0] - lag
        for name in names:
            if name not in rec["observables"]:
                continue
            y = np.asarray(rec["observables"][name], dtype=np.float64)
            if y.shape != (h.shape[0],):
                raise ValueError(f"{tid}/{name}: observable rows do not match hidden states")
            rho = _correlations(cosine[:max(stop, 0)], y[lag:])
            raw_rho = _correlations(raw[:max(stop, 0), :1], y[lag:])[0]
            if np.isfinite(rho[0]):
                if not np.isfinite(rho[1:]).all():
                    raise ValueError(f"{tid}/{name}: a random control has undefined correlation")
                cells[name].append((str(rec["problem_id"]), rho, raw_rho))
        texts = rec.get("texts", [])
        if texts and len(texts) != h.shape[0]:
            raise ValueError(f"{tid}: text rows do not match hidden states")
        if texts:
            for polarity, step in [("positive", int(cosine[:, 0].argmax())),
                                   ("negative", int(cosine[:, 0].argmin()))]:
                examples.append({"trajectory_id": tid, "step": step,
                                 "polarity": polarity, "cosine": float(cosine[step, 0]),
                                 "text": "".join(texts[max(0, step-12):step+13])})
    result = {}
    nulls = []
    for name, rows in cells.items():
        groups = sorted({pid for pid, _, _ in rows})
        if not groups:
            result[name] = {"status": "unmeasured", "n_problems": 0,
                            "n_variable_trajectories": 0,
                            "reason": "fewer than four valid rows, or constant within every trajectory"}
            continue
        # Think/no_think traces of the same problem do not become two units.
        grouped = np.stack([np.mean([r for p, r, _ in rows if p == pid], axis=0)
                            for pid in groups])
        raw_groups = [[r for p, _, r in rows if p == pid and np.isfinite(r)] for pid in groups]
        raw_grouped = [float(np.mean(values)) for values in raw_groups if values]
        mean = grouped.mean(axis=0)
        nulls.append(np.abs(mean[1:]))
        ci = None
        if len(groups) >= 2:
            draws = rng.integers(len(groups), size=(bootstrap_reps, len(groups)))
            ci = np.quantile(grouped[draws, 0].mean(axis=1), [0.025, 0.975]).tolist()
        result[name] = {
            "status": "association_only", "rho_cosine": float(mean[0]),
            "rho_raw_projection": float(np.mean(raw_grouped)) if raw_grouped else None,
            "n_raw_projection_problems": len(raw_grouped),
            "problem_bootstrap_ci95": ci, "n_problems": len(groups),
            "n_variable_trajectories": len(rows),
            "random_abs_rho_q95": float(np.quantile(np.abs(mean[1:]), 0.95)),
        }
    if nulls:
        max_null = np.max(nulls, axis=0)
        for row in result.values():
            if row["status"] == "association_only":
                row["random_max_stat_p"] = float(
                    (1 + np.count_nonzero(max_null >= abs(row["rho_cosine"]))) / (n_random + 1))
    positive = sorted((e for e in examples if e["polarity"] == "positive"),
                      key=lambda e: -e["cosine"])[:5]
    negative = sorted((e for e in examples if e["polarity"] == "negative"),
                      key=lambda e: e["cosine"])[:5]
    return {
        "kind": "observational", "evaluation_split": evaluation_split,
        "evidence_status": "association_only" if evaluation_split == "independent"
                           else "exploratory_possible_extraction_overlap",
        "n_trajectories": len(records), "n_tokens": total_tokens,
        "n_problems": len({str(r["problem_id"]) for r in records}),
        "lag": lag, "n_random": n_random, "seed": seed,
        "method": "within-trajectory Spearman, average traces within problem, equal problem weights",
        "null": "isotropic unit directions, max absolute mean rho across measured observables; (b+1)/(R+1)",
        "associations": result, "contexts": {"positive": positive, "negative": negative},
        "limits": ["Associations do not establish causal effects or necessity.",
                   "Constant within-trajectory labels cannot identify a within-trajectory function.",
                   "Random-direction p measures geometric specificity, not a label-permutation null.",
                   "Evaluation independence is caller-declared; extraction provenance needs separate verification."],
    }


def _log_probs(logits: np.ndarray) -> np.ndarray:
    from scipy.special import logsumexp
    return logits - logsumexp(logits)


def _effect(base: dict, arm: dict, targets: Mapping[str, Sequence[int]]) -> dict:
    b, a = _log_probs(base["logits"]), _log_probs(arm["logits"])
    pb, pa = np.exp(b), np.exp(a)
    layers = []
    for name, hb in base["states"].items():
        delta = arm["states"][name] - hb
        dn = float(np.linalg.norm(delta))
        layers.append({"site": name, "relative_shift": dn / max(float(np.linalg.norm(hb)), 1e-30),
                       "delta_cosine_with_vector": float(np.einsum("d,d->", delta, arm["unit"]) / dn) if dn > 0 else None})
    return {
        "delta_entropy": float(np.sum(-pa * a + pb * b)),
        "kl_base_to_arm": max(0.0, float(np.sum(pb * (b - a)))),
        "next_token_base": int(np.argmax(b)), "next_token_arm": int(np.argmax(a)),
        "target_probability_delta": {name: float(pa[list(ids)].sum() - pb[list(ids)].sum())
                                     for name, ids in targets.items()},
        "layers": layers,
    }


def explain_response(
    model, inputs: dict, vector: np.ndarray, layer: int, *,
    strengths: Sequence[float] = (-0.1, -0.05, 0.05, 0.1),
    epsilon: float = 0.001, n_random: int = 16, seed: int = 0,
    targets: Optional[Mapping[str, Sequence[int]]] = None,
    decode: Optional[Callable[[int], str]] = None, top_k: int = 10,
) -> dict:
    """Exact local interventions plus a central finite-difference response.

    L is a zero-based transformer block INPUT. Perturb ONLY the final input
    position, with no KV cache; every arm starts from identical input_ids.
    strengths scale the measured baseline input norm at that position.
    Llama-style .model.layers and .model.norm are required. Torch is optional
    until this instrument is used. Hooks and the model training flag restore.
    """
    import torch

    u = unit_direction(vector)
    layers = model.model.layers
    if not 0 <= layer < len(layers) or u.size != model.config.hidden_size:
        raise ValueError("layer/vector do not match model")
    ids = inputs.get("input_ids")
    if ids is None or ids.ndim != 2 or ids.shape[0] != 1 or ids.shape[1] < 1:
        raise ValueError("need exactly one nonempty token prefix")
    if "past_key_values" in inputs or "inputs_embeds" in inputs:
        raise ValueError("response requires an explicit prefix without a KV cache")
    if len(strengths) == 0 or not np.isfinite(strengths).all() or epsilon <= 0 or not np.isfinite(epsilon):
        raise ValueError("need finite strengths and a positive finite epsilon")
    if "attention_mask" in inputs and not bool(torch.all(inputs["attention_mask"] == 1)):
        raise ValueError("response requires an unpadded prefix")
    if n_random < 1 or top_k < 1:
        raise ValueError("need random controls and top_k >= 1")
    targets = {name: list(v) for name, v in (targets or {}).items()}
    vocab_size = int(model.config.vocab_size)
    for name, token_ids in targets.items():
        if (not token_ids or len(set(token_ids)) != len(token_ids) or
                any(not isinstance(t, (int, np.integer)) or not 0 <= t < vocab_size for t in token_ids)):
            raise ValueError(f"invalid/duplicate target token ids for {name}")
    was_training = model.training
    model.eval()

    def run(direction, alpha):
        handles, states, norm = [], {}, []

        def add(module, args, kwargs):
            x = args[0] if args else kwargs["hidden_states"]
            norm.append(float(torch.linalg.vector_norm(x[0, -1].float())))
            new_x = x.clone()
            v = torch.as_tensor(direction, device=x.device, dtype=x.dtype)
            new_x[:, -1, :] += float(alpha) * v
            if args:
                return (new_x,) + args[1:], kwargs
            return args, {**kwargs, "hidden_states": new_x}

        def capture(name):
            def hook(module, args, output):
                x = output[0] if isinstance(output, tuple) else output
                states[name] = x[0, -1].detach().float().cpu().numpy().astype(np.float64)
            return hook

        try:
            handles.append(layers[layer].register_forward_pre_hook(add, with_kwargs=True))
            for idx, block in enumerate(layers):
                handles.append(block.register_forward_hook(capture(f"block_{idx}_output")))
            handles.append(model.model.norm.register_forward_hook(capture("final_post_norm")))
            with torch.inference_mode():
                out = model(**{**inputs, "use_cache": False, "return_dict": True})
            logits = out.logits[0, -1].detach().float().cpu().numpy().astype(np.float64)
            if len(norm) != 1 or not np.isfinite(logits).all() or not np.isfinite(norm[0]) or norm[0] <= 0:
                raise ValueError("invalid forward response or injection site")
            if any(not np.isfinite(h).all() for h in states.values()):
                raise ValueError("nonfinite captured states")
            return {"logits": logits, "states": states, "norm": norm[0], "unit": direction}
        finally:
            for handle in handles:
                handle.remove()

    try:
        base = run(u, 0.0)
        zero = run(u, 0.0)
        zero_error = float(np.max(np.abs(base["logits"] - zero["logits"])))
        state_zero_error = max(float(np.max(np.abs(h - zero["states"][k])))
                               for k, h in base["states"].items())
        if zero_error != 0 or state_zero_error != 0:
            raise ValueError("zero control is not exact; deterministic local attribution is unavailable")
        scale = base["norm"]
        pos, neg = run(u, epsilon * scale), run(u, -epsilon * scale)
        derivative = (_log_probs(pos["logits"]) - _log_probs(neg["logits"])) / (2 * epsilon * scale)
        if not np.any(derivative):
            raise ValueError("finite difference vanished; increase epsilon or use float32")
        half_pos, half_neg = run(u, epsilon * scale / 2), run(u, -epsilon * scale / 2)
        half_derivative = (_log_probs(half_pos["logits"]) - _log_probs(half_neg["logits"])) / (epsilon * scale)
        derivative_disagreement = float(np.linalg.norm(half_derivative - derivative) / np.linalg.norm(derivative))
        base_lp = _log_probs(base["logits"])
        base_p = np.exp(base_lp)
        arms = []
        for s in strengths:
            arm = run(u, float(s) * scale)
            arm_lp = _log_probs(arm["logits"])
            arm_p = np.exp(arm_lp)
            delta = arm_lp - base_lp
            effect = _effect(base, arm, targets)
            effect.update({"strength": float(s), "alpha": float(s) * scale,
                           "linear_prediction_relative_error": float(np.linalg.norm(delta - s * scale * derivative) /
                                                                     max(np.linalg.norm(delta), 1e-30))})
            def entries(order, sign):
                return [{"token_id": int(i), "token": decode(int(i)) if decode else str(i),
                         "base_probability": float(base_p[i]),
                         "arm_probability": float(arm_p[i]),
                         "delta_log_probability": float(delta[i])} for i in order if sign * delta[i] > 0]
            effect["promoted_tokens"] = entries(np.argsort(-delta)[:top_k], 1)
            effect["suppressed_tokens"] = entries(np.argsort(delta)[:top_k], -1)
            probability_delta = arm_p - base_p
            effect["largest_probability_changes"] = [
                {"token_id": int(i), "token": decode(int(i)) if decode else str(i),
                 "base_probability": float(base_p[i]), "arm_probability": float(arm_p[i]),
                 "delta_probability": float(probability_delta[i]), "delta_log_probability": float(delta[i])}
                for i in np.argsort(-np.abs(probability_delta))[:top_k] if probability_delta[i] != 0
            ]
            arms.append(effect)
        rng = np.random.default_rng(seed)
        control_strength = float(max(abs(float(s)) for s in strengths))
        controls = []
        for _ in range(n_random):
            direction = unit_direction(rng.standard_normal(u.size))
            controls.append(_effect(base, run(direction, control_strength * scale), targets))
        # Compare like doses only. Multiple target groups use a max statistic.
        null = np.array([max([abs(v) for v in c["target_probability_delta"].values()], default=0)
                         for c in controls])
        for arm in arms:
            if abs(arm["strength"]) == control_strength:
                arm["target_random_max_stat_p"] = {
                    name: float((1 + np.count_nonzero(null >= abs(value))) / (n_random + 1))
                    for name, value in arm["target_probability_delta"].items()}
        return {
            "kind": "local_causal_response", "layer": layer, "site": "block_input",
            "position": int(ids.shape[1] - 1), "prefix_token_ids": ids[0].detach().cpu().tolist(),
            "baseline_site_norm": scale, "zero_control_max_logit_error": zero_error,
            "zero_control_max_state_error": state_zero_error,
            "epsilon_relative": epsilon, "n_random": n_random, "seed": seed,
            "finite_difference_relative_disagreement_at_half_epsilon": derivative_disagreement,
            "target_probability_derivative": {name: float(np.sum(base_p[list(token_ids)] * derivative[list(token_ids)]))
                                               for name, token_ids in targets.items()},
            "derivative_method": "central finite difference of full-model log probabilities per unit residual norm",
            "targets": targets, "arms": arms,
            "random_control": {"strength": control_strength, "kl_base_to_arm": [c["kl_base_to_arm"] for c in controls],
                               "target_probability_delta": [c["target_probability_delta"] for c in controls]},
            "limits": ["Local single-position response only; no claim about full generations, accuracy or reasoning strategy.",
                       "Target token groups are operational definitions, not proof of semantic concepts.",
                       "Finite differences depend on epsilon and numerical precision; inspect linearity error.",
                       "Random controls are isotropic and matched in norm; they do not establish causal necessity."],
        }
    finally:
        model.train(was_training)
