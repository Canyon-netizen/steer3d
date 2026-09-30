"""Compute REAL steering vectors from collected trajectory data.

This reads the raw hidden states saved by collect_qwen3_aime_vllm.py
(datasets/aime_qwen3_1p7b_*/aime/*.npz — each with hidden_states of
shape (n_tokens, 28, 2048)) and extracts semantic direction vectors
for steering.

The extraction uses difference-of-means (the standard "actAdd /
CAA" recipe), grouped by semantically meaningful token subsets:

  * confidence_up  : low-entropy  −  high-entropy   tokens
  * confidence_down: high-entropy −  low-entropy   tokens
  * reasoning_deep : late tokens  −  early tokens   (in long chains)
  * reasoning_shallow: early tokens − late tokens
  * caution        : self-check ("wait"/"actually"/…) − ordinary tokens
  * creativity     : in-think-block − post-think tokens

Usage:
    python3 backend/examples/compute_steering_vectors.py \
        --data-root datasets/aime_qwen3_1p7b_16k_fp16/aime \
        --layer 14 --out-dir backend/examples/output/steering_vectors

Output:
    output/steering_vectors/steering_vectors.json   (metadata)
    output/steering_vectors/<name>.npy              (d_model float32 unit vector)
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np


# The collector's `is_self_check` flag was never enabled in the 16k/32k
# runs (it is always False), so we re-detect it from the token text here.
# Word boundaries matter: "waiting" must not count as "wait".
SELF_CHECK_RE = re.compile(
    r"\b(wait|actually|hmm|hold on|let me check|let me verify|recheck|"
    r"double[- ]check|second thought|alternatively|but wait)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_trajectories(
    data_root: Path,
    layer: int,
    max_trajectories: Optional[int] = None,
    min_tokens: int = 40,
) -> List[dict]:
    """Load every ``*.npz`` under `data_root` and slice out `layer`.

    Each returned dict has:
        trajectory_id: str
        hidden:     (n_gen_tokens, d_model) float32
        entropy:    (n_gen_tokens,)      float32
        top1_prob:  (n_gen_tokens,)      float32
        token_text: list[str]
        is_self_check: list[bool]
        is_in_think: list[bool]
        n_prompt:   int
    """
    npz_files = sorted(data_root.glob("*.npz"))
    if max_trajectories:
        npz_files = npz_files[:max_trajectories]

    out: List[dict] = []
    for i, npz_path in enumerate(npz_files):
        try:
            d = np.load(npz_path, allow_pickle=True)
            if "hidden_states" not in d.files:
                continue
            hs = d["hidden_states"]                     # (T, L, D) fp16
            if hs.ndim != 3:
                continue
            n_tok, n_layers, d_model = hs.shape
            if layer >= n_layers:
                continue

            gen_hidden = hs[:, layer, :].astype(np.float32)

            # Read sidecar JSON for token metadata
            sidecar = npz_path.with_suffix(".json")
            if not sidecar.exists():
                continue
            meta = json.loads(sidecar.read_text())
            tokens = meta.get("tokens", [])
            if len(tokens) != n_tok:
                continue

            n_prompt = int(meta.get("n_prompt_tokens", 0) or 0)
            token_text = [t["token"] for t in tokens]
            entropy = np.array([t["entropy"] for t in tokens], dtype=np.float32)
            top1 = np.array([t["top1_prob"] for t in tokens], dtype=np.float32)
            is_self_check = [bool(t.get("is_self_check", False)) for t in tokens]
            is_in_think = [bool(t.get("is_in_think_block", False)) for t in tokens]

            # Recover the self-check flags from text when the collector
            # left them all False (the case for the 16k/32k runs).
            if not any(is_self_check):
                is_self_check = [
                    bool(SELF_CHECK_RE.search(t["token"] or ""))
                    for t in tokens
                ]

            out.append({
                "trajectory_id": npz_path.stem,
                "hidden": gen_hidden,
                "entropy": entropy,
                "top1_prob": top1,
                "token_text": token_text,
                "is_self_check": is_self_check,
                "is_in_think": is_in_think,
                "n_prompt": n_prompt,
                "n_tokens": n_tok,
                "d_model": d_model,
                "n_layers": n_layers,
            })
            if (i + 1) % 20 == 0:
                print(f"    loaded {i+1}/{len(npz_files)} …")
        except Exception as e:  # keep going on one bad file
            print(f"    skip {npz_path.name}: {e}")

    return out


# ---------------------------------------------------------------------------
# Vector extraction
# ---------------------------------------------------------------------------


def diff_of_means(pos: np.ndarray, neg: np.ndarray) -> np.ndarray:
    """Standard CAA / actAdd steering direction."""
    return (pos.mean(axis=0) - neg.mean(axis=0)).astype(np.float32)


def pca_separating_direction(
    pos: np.ndarray, neg: np.ndarray, max_components: int = 32
) -> np.ndarray:
    """Top PCA component that best separates the two groups."""
    d = diff_of_means(pos, neg)
    all_x = np.vstack([pos, neg]).astype(np.float32)
    all_x -= all_x.mean(axis=0, keepdims=True)
    try:
        _, _, Vt = np.linalg.svd(all_x, full_matrices=False)
    except np.linalg.LinAlgError:
        return d / (np.linalg.norm(d) + 1e-8)
    for i in range(min(max_components, Vt.shape[0])):
        v = Vt[i]
        sep = abs(float(v @ pos.mean(axis=0) - v @ neg.mean(axis=0)))
        if sep > 0:
            return (v * np.sign(float(v @ d))).astype(np.float32)
    return d / (np.linalg.norm(d) + 1e-8)


def l2(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    return (v / n).astype(np.float32) if n > 1e-8 else v.astype(np.float32)


# ---------------------------------------------------------------------------
# Direction builders — each returns (pos, neg) activation pools
# ---------------------------------------------------------------------------


def pool_confidence(trajs: List[dict]) -> Tuple[np.ndarray, np.ndarray]:
    """Low-entropy and high-entropy token activations across all trajectories."""
    lo, hi = [], []
    for t in trajs:
        h, e = t["hidden"], t["entropy"]
        n_p = t["n_prompt"]
        gen_h = h[n_p:]
        gen_e = e[n_p:]
        if len(gen_h) < 20:
            continue
        q1, q3 = np.percentile(gen_e, 30), np.percentile(gen_e, 75)
        lo.append(gen_h[gen_e <= q1])
        hi.append(gen_h[gen_e >= q3])
    if not lo or not hi:
        return np.zeros((0, 1), np.float32), np.zeros((0, 1), np.float32)
    return np.concatenate(lo), np.concatenate(hi)


def pool_reasoning_depth(trajs: List[dict], min_len: int = 120) -> Tuple[np.ndarray, np.ndarray]:
    """Late vs early tokens of *long* trajectories."""
    deep, shallow = [], []
    for t in trajs:
        h = t["hidden"]
        n_p = t["n_prompt"]
        gen = h[n_p:]
        if len(gen) < min_len:
            continue
        shallow.append(gen[: len(gen) // 4])
        deep.append(gen[-(len(gen) // 4):])
    if not deep or not shallow:
        return np.zeros((0, 1), np.float32), np.zeros((0, 1), np.float32)
    return np.concatenate(deep), np.concatenate(shallow)


def pool_self_check(trajs: List[dict]) -> Tuple[np.ndarray, np.ndarray]:
    sc, reg = [], []
    for t in trajs:
        h, flags = t["hidden"], t["is_self_check"]
        n_p = t["n_prompt"]
        for i, f in enumerate(flags):
            if i < n_p:
                continue
            if f:
                sc.append(h[i])
            else:
                reg.append(h[i])
    if len(sc) < 20 or len(reg) < 100:
        return np.zeros((0, 1), np.float32), np.zeros((0, 1), np.float32)
    return np.stack(sc), np.stack(reg)


def pool_think_block(trajs: List[dict]) -> Tuple[np.ndarray, np.ndarray]:
    inside, outside = [], []
    for t in trajs:
        h, flags = t["hidden"], t["is_in_think"]
        n_p = t["n_prompt"]
        for i, f in enumerate(flags):
            if i < n_p:
                continue
            (inside if f else outside).append(h[i])
    if len(inside) < 50 or len(outside) < 100:
        return np.zeros((0, 1), np.float32), np.zeros((0, 1), np.float32)
    return np.stack(inside), np.stack(outside)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate(v: np.ndarray, trajs: List[dict], layer: int) -> dict:
    """How well does `v` actually separate the concept it was built from?"""
    out = {"layer": layer, "norm": float(np.linalg.norm(v))}
    if not np.all(np.isfinite(v)):
        out["error"] = "non-finite entries in vector"
        return out
    lo, hi = pool_confidence(trajs)
    if len(lo) > 10 and len(hi) > 10:
        a = lo @ v
        b = hi @ v
        pooled = np.sqrt(((len(a)-1)*a.var() + (len(b)-1)*b.var()) /
                         max(len(a)+len(b)-2, 1))
        d = (a.mean() - b.mean()) / max(pooled, 1e-8)
        out["confidence_cohens_d"] = float(d)
        out["confidence_separation"] = float(a.mean() - b.mean())
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(args):
    data_root = Path(args.data_root)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 64)
    print("Steering vector extraction (real hidden states)")
    print("=" * 64)
    print(f"data root : {data_root}")
    print(f"layer     : L{args.layer}")
    print(f"method    : {args.method}")
    print(f"out dir   : {out_dir}")
    print()

    print("[1/3] loading trajectories …")
    trajs = load_trajectories(
        data_root, args.layer,
        max_trajectories=args.limit,
        min_tokens=args.min_tokens,
    )
    if not trajs:
        print("ERROR: no trajectories loaded. Check --data-root.")
        return 1
    total = sum(t["n_tokens"] for t in trajs)
    d_model = trajs[0]["d_model"]
    print(f"  {len(trajs)} trajectories, {total} tokens, d_model={d_model}")
    print(f"  mean length: {total/len(trajs):.0f} tokens")
    print()

    fn = diff_of_means if args.method == "diff_of_means" else pca_separating_direction

    specs: List[Tuple[str, Callable[[], Tuple[np.ndarray, np.ndarray]], str, str]] = [
        ("confidence_up",  lambda: pool_confidence(trajs),
         "low-entropy tokens (p30)", "high-entropy tokens (p75)"),
        ("reasoning_deep", lambda: pool_reasoning_depth(trajs),
         "last 25% of long trajectories", "first 25% of long trajectories"),
        ("caution",        lambda: pool_self_check(trajs),
         "self-check tokens (wait/actually/…)", "ordinary generated tokens"),
        ("creativity",     lambda: pool_think_block(trajs),
         "tokens inside <think>", "tokens outside <think>"),
    ]

    print("[2/3] extracting directions …")
    vectors: Dict[str, np.ndarray] = {}
    metadata: Dict[str, dict] = {}

    for name, pool_fn, pos_desc, neg_desc in specs:
        try:
            pos, neg = pool_fn()
            if len(pos) < 20 or len(neg) < 20:
                print(f"  {name:18s} SKIP — not enough samples "
                      f"(pos={len(pos)}, neg={len(neg)})")
                continue
            v = l2(fn(pos, neg))
            vectors[name] = v
            metadata[name] = {
                "description": DESCRIPTIONS[name],
                "layer": args.layer,
                "d_model": int(d_model),
                "method": args.method,
                "positive_group": pos_desc,
                "negative_group": neg_desc,
                "n_positive": int(len(pos)),
                "n_negative": int(len(neg)),
                "norm": float(np.linalg.norm(v)),
                "validation": validate(v, trajs, args.layer),
            }
            print(f"  {name:18s} n=({len(pos)},{len(neg)}) "
                  f"norm={np.linalg.norm(v):.3f} "
                  f"d={metadata[name]['validation'].get('confidence_cohens_d', float('nan')):+.2f}")
        except Exception as e:
            print(f"  {name:18s} ERROR — {e}")

    # Derived inverse directions.
    for base, inv in (("confidence_up", "confidence_down"),
                      ("reasoning_deep", "reasoning_shallow")):
        if base in vectors:
            vectors[inv] = (-vectors[base]).astype(np.float32)
            metadata[inv] = {
                **metadata[base],
                "description": DESCRIPTIONS[inv],
                "positive_group": metadata[base]["negative_group"],
                "negative_group": metadata[base]["positive_group"],
                "derived_from": base,
            }
            print(f"  {inv:18s} (derived as -{base})")

    if not vectors:
        print("ERROR: no vectors extracted.")
        return 1

    print()
    print("[3/3] saving …")
    for name, v in vectors.items():
        np.save(out_dir / f"{name}.npy", v)
    (out_dir / "steering_vectors.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False)
    )

    print(f"  wrote {len(vectors)} vectors to {out_dir}")
    for name in vectors:
        print(f"    {name}.npy")
    return 0


DESCRIPTIONS = {
    "confidence_up": "Raise confidence / lower entropy",
    "confidence_down": "Lower confidence / raise entropy (more exploration)",
    "reasoning_deep": "Push toward long-chain, late-stage reasoning states",
    "reasoning_shallow": "Push toward early, setup-stage states (short answers)",
    "caution": "Push toward the state the model is in when it verifies its work",
    "creativity": "Push toward the state inside the <think> scratchpad",
}


def cli():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-root", type=str,
                    default="datasets/aime_qwen3_1p7b_16k_fp16/aime")
    ap.add_argument("--out-dir", type=str,
                    default="backend/examples/output/steering_vectors")
    ap.add_argument("--layer", type=int, default=14)
    ap.add_argument("--method", choices=["diff_of_means", "pca"], default="diff_of_means")
    ap.add_argument("--limit", type=int, default=None,
                    help="Cap the number of .npz files (debugging)")
    ap.add_argument("--min-tokens", type=int, default=40)
    args = ap.parse_args()
    raise SystemExit(main(args))


if __name__ == "__main__":
    cli()
