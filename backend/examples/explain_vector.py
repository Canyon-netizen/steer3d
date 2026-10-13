"""Explain any .npy steering direction from recorded states or actual model responses.

Run with --help, or see backend/README.md for the two instruments and their limits.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.vector_explanation import explain_observations, explain_response, unit_direction


REVISION_TOKEN = re.compile(r"\b(wait|actually|hmm|recheck|alternatively)\b", re.I)
NUMBER_TOKEN = re.compile(r"[0-9]")
OPERATOR_TOKEN = re.compile(r"[+*/=−×÷]|^\s*-\s*$")


def load_records(data_root: Path, hidden_index: int, dimension: int, limit: int = 0):
    """Strictly join generated-state rows to sidecar tokens and NPZ token ids.

    Prompt arrays are separate in the standard format. n_prompt_tokens must
    NEVER be subtracted from this generated-only hidden_states array.
    """
    paths = sorted(data_root.glob("*.npz"))
    if limit:
        paths = paths[:limit]
    if not paths:
        raise ValueError(f"no trajectory NPZ files in {data_root}")
    records, models = [], set()
    for path in paths:
        sidecar = json.loads(path.with_suffix(".json").read_text())
        tokens = sidecar["tokens"]
        with np.load(path, allow_pickle=False) as z:
            hs = z["hidden_states"]
            if hs.ndim != 3 or not 0 <= hidden_index < hs.shape[1] or hs.shape[2] != dimension:
                raise ValueError(f"{path.name}: hidden shape/index incompatible with vector")
            if len(tokens) != hs.shape[0] or not np.array_equal(z["token_ids"], [t["token_id"] for t in tokens]):
                raise ValueError(f"{path.name}: generated state/token alignment failed")
            if "attention_mask" in z and not np.all(z["attention_mask"] == 1):
                raise ValueError(f"{path.name}: padded rows require explicit filtering before analysis")
            hidden = hs[:, hidden_index, :].astype(np.float32)
        text = [t["token"] for t in tokens]
        def values(key):
            return np.array([np.nan if t.get(key) is None else t[key] for t in tokens], dtype=float)
        # This is a lexical marker label, not a mental state or creativity score.
        obs = {
            "next_token_entropy": values("entropy"),
            "next_token_top1_probability": values("top1_prob"),
            "revision_marker_token": np.array([bool(REVISION_TOKEN.search(t)) for t in text], dtype=float),
            "number_token": np.array([bool(NUMBER_TOKEN.search(t)) for t in text], dtype=float),
            "operator_token": np.array([bool(OPERATOR_TOKEN.search(t)) for t in text], dtype=float),
            "in_think_block": values("is_in_think_block"),
            "generation_position": np.arange(len(tokens), dtype=float) / max(len(tokens)-1, 1),
        }
        records.append({"trajectory_id": sidecar["trajectory_id"],
                        "problem_id": f"{sidecar.get('dataset', '')}/{sidecar.get('split', '')}/{sidecar['problem_id']}",
                        "hidden": hidden, "observables": obs, "texts": text,
                        "source": str(path.resolve())})
        models.add(sidecar["config"]["model"])
        print(f"loaded {len(records)}/{len(paths)}: {path.stem}, {len(tokens)} generated rows", flush=True)
    if len(models) != 1:
        raise ValueError("cannot combine hidden states from different models")
    return records, next(iter(models))


def vector_provenance(path: Path) -> dict:
    meta_path = path.parent / "steering_vectors.json"
    meta = json.loads(meta_path.read_text()).get(path.stem, {}) if meta_path.exists() else {}
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "metadata": meta, "model_identity_verified": False}


def recorded_prefix(path: Path, step: int):
    """Recover the exact token prefix predicting stored generation row `step`."""
    side = json.loads(path.with_suffix(".json").read_text())
    with np.load(path, allow_pickle=False) as z:
        prompt_ids = z["prompt_token_ids"]
        generated_ids = z["token_ids"]
        if prompt_ids.ndim != 1 or not prompt_ids.size or generated_ids.ndim != 1:
            raise ValueError("recorded prefix requires separate 1-D prompt_token_ids and token_ids")
        if not np.array_equal(generated_ids, [t["token_id"] for t in side["tokens"]]):
            raise ValueError("recorded prefix/token sidecar alignment failed")
        if not 0 <= step < len(generated_ids):
            raise ValueError("step must index a recorded generated token")
        prefix = np.concatenate([prompt_ids, generated_ids[:step]]).astype(np.int64)
        expected = int(generated_ids[step])
    return prefix, {"trajectory": str(path.resolve()), "step": step,
                    "stored_next_token_id": expected, "source_model": side["config"]["model"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="instrument", required=True)
    for name in ("observe", "respond"):
        p = sub.add_parser(name)
        p.add_argument("--vector", type=Path, required=True)
        p.add_argument("--out", type=Path, required=True)
        p.add_argument("--seed", type=int, default=0)
        p.add_argument("--random-directions", type=int, default=64 if name == "observe" else 16)
    observe = sub.choices["observe"]
    observe.add_argument("--data-root", type=Path, required=True)
    observe.add_argument("--hidden-index", type=int, required=True,
                         help="stored NPZ hidden_states axis index; this is NOT an injection block number")
    observe.add_argument("--limit", type=int, default=0, help="0 = all; otherwise first N sorted files")
    observe.add_argument("--lag", type=int, default=0, help="project h[t] against label[t+lag]")
    observe.add_argument("--evaluation-split", choices=["unknown", "independent", "overlap"], default="unknown")
    respond = sub.choices["respond"]
    respond.add_argument("--model-path", type=Path, required=True)
    prefix_group = respond.add_mutually_exclusive_group(required=True)
    prefix_group.add_argument("--prompt", help="user message, rendered with the model chat template")
    prefix_group.add_argument("--trajectory", type=Path, help="standard NPZ with prompt_token_ids and generated token_ids")
    respond.add_argument("--step", type=int, default=0, help="generation row to predict when using --trajectory")
    respond.add_argument("--layer", type=int, required=True, help="zero-based transformer block INPUT")
    respond.add_argument("--device", default="cpu")
    respond.add_argument("--strengths", type=float, nargs="+", default=[-0.1, -0.05, 0.05, 0.1])
    respond.add_argument("--epsilon", type=float, default=0.001)
    respond.add_argument("--target-ids", type=Path, help='JSON object: {"name": [token_ids]}')
    respond.add_argument("--target-token", action="append", default=[], help="name=text; text must encode to one token")
    respond.add_argument("--think", action="store_true", help="enable thinking in the model chat template")
    args = ap.parse_args(argv)
    vector = np.load(args.vector, allow_pickle=False)
    unit_direction(vector)
    if args.instrument == "observe":
        if args.limit < 0:
            raise ValueError("limit must be nonnegative")
        records, model_name = load_records(args.data_root, args.hidden_index, vector.size, args.limit)
        report = explain_observations(records, vector, n_random=args.random_directions,
                                      seed=args.seed, lag=args.lag, evaluation_split=args.evaluation_split)
        report.update({"model": model_name, "hidden_index": args.hidden_index,
                       "hidden_index_convention": "NPZ storage axis; consult collector for block input/output and final norm convention",
                       "trajectories": [{"id": r["trajectory_id"], "source": r["source"]} for r in records],
                       "observable_definitions": {
                           "revision_marker_token": "per-token regex: wait/actually/hmm/recheck/alternatively; multi-token phrases can be missed",
                           "number_token": "decoded token contains an ASCII digit",
                           "operator_token": "decoded token contains a listed arithmetic symbol",
                           "in_think_block": "sidecar flag; often constant throughout a trajectory",
                           "generation_position": "t/(T-1); a positional control, not reasoning depth",
                       }})
        for name, row in report["associations"].items():
            print(f"{name}: {row}")
    else:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        torch.set_num_threads(min(8, torch.get_num_threads()))
        tokenizer = AutoTokenizer.from_pretrained(str(args.model_path), local_files_only=True)
        prefix_info = {}
        if args.trajectory:
            prefix_ids, prefix_info = recorded_prefix(args.trajectory, args.step)
            inputs = {"input_ids": torch.tensor(prefix_ids[None, :], device=args.device)}
            prompt = tokenizer.decode(prefix_ids.tolist())
        else:
            if args.step != 0:
                raise ValueError("--step applies only with --trajectory")
            prompt = tokenizer.apply_chat_template([{"role": "user", "content": args.prompt}],
                                                   tokenize=False, add_generation_prompt=True, enable_thinking=args.think)
            inputs = tokenizer(prompt, return_tensors="pt").to(args.device)
        model = AutoModelForCausalLM.from_pretrained(str(args.model_path), local_files_only=True,
                                                   torch_dtype=torch.float32, attn_implementation="eager").to(args.device)
        targets = json.loads(args.target_ids.read_text()) if args.target_ids else {}
        for spec in args.target_token:
            name, text = spec.split("=", 1)
            ids = tokenizer.encode(text, add_special_tokens=False)
            if len(ids) != 1:
                raise ValueError(f"{name}: text encodes to {len(ids)} tokens; use single tokens or --target-ids")
            if name in targets:
                raise ValueError(f"duplicate target name: {name}")
            targets[name] = ids
        report = explain_response(model, dict(inputs), vector, args.layer,
                                  strengths=args.strengths, epsilon=args.epsilon,
                                  n_random=args.random_directions, seed=args.seed, targets=targets,
                                  decode=lambda i: tokenizer.decode([i]))
        if prefix_info:
            prefix_info["baseline_matches_stored_token"] = report["arms"][0]["next_token_base"] == prefix_info["stored_next_token_id"]
        report.update({"model": str(args.model_path.resolve()), "prompt": args.prompt,
                       "rendered_prefix": prompt, "recorded_prefix": prefix_info,
                       "thinking_enabled": args.think if not args.trajectory else None,
                       "dtype": "float32", "device": args.device})
        for arm in report["arms"]:
            print(f"strength {arm['strength']:+.3f}: KL={arm['kl_base_to_arm']:.6g}, "
                  f"delta_entropy={arm['delta_entropy']:+.6g}, targets={arm['target_probability_delta']}")
    report.update({"schema": "steer3d.vector_explanation/1", "vector": vector_provenance(args.vector),
                   "generated_by": "backend/examples/explain_vector.py"})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
