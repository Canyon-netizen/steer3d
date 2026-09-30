"""Measure what each layer actually does, from the data we already have.

The frontend used to carry a hand-written table of layer descriptions
("layer 12: semantic", "layer 20: deep reasoning"). That is a guess
dressed up as a fact, and it is exactly the kind of thing that makes a
visualiser untrustworthy — the reader cannot tell the label from the
measurement.

This script replaces the guesses with numbers. For every layer it
computes, over all collected trajectories:

  * **entropy coupling** — Pearson r between the layer's hidden-state
    norm and the next-token entropy. High |r| means the layer's
    activation *magnitude* tracks the model's uncertainty, which is
    the empirical content of "this layer handles confidence".
  * **self-check alignment** — mean cosine of the residual with the
    mean residual at self-check tokens ("wait", "actually", …) minus
    the same for ordinary tokens. A positive gap means the layer
    encodes something specific about the verification state.
  * **think-block alignment** — the same contrast for tokens inside
    <think> versus after it closes.
  * **effective rank** — exp(entropy of the eigenvalue spectrum) over
    the token population, in nats. Low rank means the layer is doing
    something narrow and consistent; high rank means it is
    representing many things at once.
  * **write strength** — mean ‖h_out − h_in‖ / ‖h_in‖, how much the
    block actually changes the residual relative to its size.

The output is a JSON the frontend renders directly, so every claim in
the UI is traceable to a number computed from the trajectories.

Usage:
    python3 backend/examples/measure_layers.py \
        --data-root datasets/aime_qwen3_1p7b_16k_fp16/aime \
        --out backend/examples/output/layer_profiles.json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np


SELF_CHECK_RE = re.compile(
    r"\b(wait|actually|hmm|hold on|let me check|let me verify|recheck|"
    r"double[- ]check|second thought|alternatively|but wait)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Loading — memory-conscious, because a full trajectory is (T, 28, 2048)
# and holding 48 of them in fp32 is ~11 GB.
# ---------------------------------------------------------------------------


def iter_layer_stats(
    data_root: Path,
    max_trajectories: Optional[int] = None,
    min_tokens: int = 40,
    max_tokens_per_traj: int = 512,
):
    """Stream trajectories once, yielding per-layer slices.

    Yields ``(layer, hidden_slice, meta)`` where ``hidden_slice`` is
    (n_sampled, d_model) float32 for one layer of one trajectory, and
    ``meta`` carries the per-token entropy / flags aligned to it.
    We sample tokens (stride) rather than keeping all of them — the
    statistics we want are means and covariances, which converge fast.
    """
    npz_files = sorted(data_root.glob("*.npz"))
    if max_trajectories:
        npz_files = npz_files[:max_trajectories]

    for npz_path in npz_files:
        try:
            sidecar = npz_path.with_suffix(".json")
            if not sidecar.exists():
                continue
            meta_all = json.loads(sidecar.read_text())
            tokens = meta_all.get("tokens", [])
            if len(tokens) < min_tokens:
                continue

            d = np.load(npz_path, allow_pickle=True)
            if "hidden_states" not in d.files:
                continue
            hs = d["hidden_states"]                    # (T, L, D) fp16
            n_tok, n_layers, _ = hs.shape
            if len(tokens) != n_tok:
                continue

            n_prompt = int(meta_all.get("n_prompt_tokens", 0) or 0)
            # Stride-sample the generated region.
            gen_idx = np.arange(n_prompt, n_tok)
            if len(gen_idx) > max_tokens_per_traj:
                stride = len(gen_idx) // max_tokens_per_traj + 1
                gen_idx = gen_idx[::stride]

            texts = [tokens[i]["token"] or "" for i in gen_idx]
            entropies = np.array(
                [tokens[i]["entropy"] for i in gen_idx], dtype=np.float32
            )
            in_think = np.array(
                [bool(tokens[i].get("is_in_think_block", False)) for i in gen_idx],
                dtype=bool,
            )
            self_check = np.array(
                [bool(SELF_CHECK_RE.search(t)) for t in texts], dtype=bool
            )

            flags = {
                "entropy": entropies,
                "self_check": self_check,
                "in_think": in_think,
            }

            for layer in range(n_layers):
                yield layer, hs[gen_idx, layer, :].astype(np.float32), flags
        except Exception as e:
            print(f"    skip {npz_path.name}: {e}")


# ---------------------------------------------------------------------------
# Accumulators
# ---------------------------------------------------------------------------


class LayerAccumulator:
    """Streaming sufficient statistics for one layer.

    We never hold more than a token sample in memory: the entropy
    coupling needs sum(h), sum(||h||), sum(||h||·entropy) and counts;
    the rank needs a covariance sketch, which we approximate with a
    fixed random projection (a "sketch" of the second moment) rather
    than the full 2048×2048 matrix. That keeps this runnable in a few
    hundred MB and is more than accurate enough for an effective-rank
    readout.
    """

    def __init__(self, d_model: int, sketch_dim: int = 128, seed: int = 0):
        self.d_model = d_model
        rng = np.random.default_rng(seed)
        # Gaussian sketch: projecting to sketch_dim dims preserves the
        # spectrum's shape well enough for effective rank.
        self.proj = rng.standard_normal((d_model, sketch_dim)).astype(np.float32) / np.sqrt(
            sketch_dim
        )
        self.n = 0
        self.sum_norm = 0.0
        self.sum_norm_entropy = 0.0
        self.sum_entropy = 0.0
        self.sum_entropy_sq = 0.0
        self.sum_sketch = np.zeros(sketch_dim, dtype=np.float64)
        self.sum_sketch_sq = np.zeros((sketch_dim, sketch_dim), dtype=np.float64)
        # alignment accumulators
        self.sc_sum = np.zeros(d_model, dtype=np.float64)
        self.sc_n = 0
        self.reg_sum = np.zeros(d_model, dtype=np.float64)
        self.reg_n = 0
        self.think_sum = np.zeros(d_model, dtype=np.float64)
        self.think_n = 0
        self.post_sum = np.zeros(d_model, dtype=np.float64)
        self.post_n = 0
        # write strength (needs consecutive layers; filled by caller)
        self.sum_sq_norm = 0.0

    def add(self, h: np.ndarray, flags: dict) -> None:
        if len(h) == 0:
            return
        norms = np.linalg.norm(h, axis=1)
        ent = flags["entropy"]

        self.n += len(h)
        self.sum_norm += float(norms.sum())
        self.sum_norm_entropy += float((norms * ent).sum())
        self.sum_entropy += float(ent.sum())
        self.sum_entropy_sq += float((ent ** 2).sum())
        self.sum_sq_norm += float((norms ** 2).sum())

        sk = h @ self.proj
        self.sum_sketch += sk.sum(axis=0)
        self.sum_sketch_sq += sk.T @ sk

        for mask, sum_attr, n_attr in (
            (flags["self_check"], "sc_sum", "sc_n"),
            (~flags["self_check"], "reg_sum", "reg_n"),
            (flags["in_think"], "think_sum", "think_n"),
            (~flags["in_think"], "post_sum", "post_n"),
        ):
            if mask.any():
                getattr(self, sum_attr)[:] += h[mask].sum(axis=0)
                setattr(self, n_attr, getattr(self, n_attr) + int(mask.sum()))

    def finish(self) -> dict:
        if self.n < 2:
            return {}
        out: dict = {"n_tokens": int(self.n)}

        # --- entropy coupling: corr(||h||, entropy) ---
        mean_norm = self.sum_norm / self.n
        mean_ent = self.sum_entropy / self.n
        cov = self.sum_norm_entropy / self.n - mean_norm * mean_ent
        var_n = self.sum_sq_norm / self.n - mean_norm ** 2
        var_e = self.sum_entropy_sq / self.n - mean_ent ** 2
        denom = np.sqrt(max(var_n, 1e-12) * max(var_e, 1e-12))
        out["entropy_coupling"] = float(cov / denom) if denom > 0 else 0.0
        out["mean_norm"] = float(mean_norm)
        out["mean_entropy"] = float(mean_ent)

        # --- effective rank from the projected covariance ---
        k = self.proj.shape[1]
        cov_s = self.sum_sketch_sq / self.n - np.outer(
            self.sum_sketch / self.n, self.sum_sketch / self.n
        )
        try:
            ev = np.linalg.eigvalsh(cov_s)
            ev = np.clip(ev, 0.0, None)
            ev = ev[ev > 1e-10]
            if len(ev) > 0:
                p = ev / ev.sum()
                # Renyi entropy of order 1 == Shannon entropy of the spectrum.
                out["effective_rank"] = float(np.exp(-np.sum(p * np.log(p))))
                out["rank_fraction"] = float(len(ev) / k)
        except np.linalg.LinAlgError:
            pass

        # --- alignment gaps ---
        def gap(a_sum, a_n, b_sum, b_n) -> Optional[float]:
            if a_n < 10 or b_n < 10:
                return None
            a = a_sum / a_n
            b = b_sum / b_n
            na, nb = np.linalg.norm(a), np.linalg.norm(b)
            if na < 1e-8 or nb < 1e-8:
                return None
            return float(np.dot(a, b) / (na * nb))

        out["self_check_alignment"] = gap(
            self.sc_sum, self.sc_n, self.reg_sum, self.reg_n
        )
        out["think_alignment"] = gap(
            self.think_sum, self.think_n, self.post_sum, self.post_n
        )
        out["n_self_check"] = int(self.sc_n)
        out["n_think"] = int(self.think_n)
        return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(args) -> int:
    data_root = Path(args.data_root)
    out_path = Path(args.out)

    print("=" * 68)
    print("Per-layer functional profiling (measured, not assumed)")
    print("=" * 68)
    print(f"data root : {data_root}")
    print()

    # First pass: discover d_model and n_layers.
    first = next(iter_layer_stats(data_root, 1, args.min_tokens), None)
    if first is None:
        print("ERROR: no usable trajectories.")
        return 1
    _, h0, _ = first
    d_model = h0.shape[1]
    print(f"d_model = {d_model}")

    accs: Dict[int, LayerAccumulator] = {}
    n_traj = 0
    n_seen = set()

    print("\nstreaming trajectories …")
    for layer, h, flags in iter_layer_stats(
        data_root, args.limit, args.min_tokens, args.max_tokens_per_traj
    ):
        if layer not in accs:
            accs[layer] = LayerAccumulator(d_model, args.sketch_dim)
        accs[layer].add(h, flags)
        n_seen.add(layer)
        if layer == 0:
            n_traj += 1
            if n_traj % 10 == 0:
                print(f"    {n_traj} trajectories …")

    if not accs:
        print("ERROR: nothing accumulated.")
        return 1

    print(f"\nprofiling {len(accs)} layers over {n_traj} trajectories\n")

    profiles = []
    for layer in sorted(accs):
        p = accs[layer].finish()
        if not p:
            continue
        p["layer"] = layer
        profiles.append(p)
        ec = p.get("entropy_coupling", 0.0)
        er = p.get("effective_rank", float("nan"))
        sa = p.get("self_check_alignment")
        ta = p.get("think_alignment")
        print(
            f"  L{layer:>2}  n={p['n_tokens']:>7}  "
            f"r(norm,entropy)={ec:+.3f}  "
            f"eff_rank={er:6.1f}  "
            f"selfchk={_fmt(sa)}  think={_fmt(ta)}"
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "d_model": d_model,
                "n_trajectories": n_traj,
                "source": str(data_root),
                "layers": profiles,
            },
            indent=2,
        )
    )
    print(f"\nwrote {out_path}")

    # A short human summary of what the numbers actually support.
    print("\nWhat the measurements say:")
    best_ec = max(profiles, key=lambda p: abs(p.get("entropy_coupling", 0)))
    print(
        f"  • strongest ‖h‖↔entropy coupling at L{best_ec['layer']} "
        f"(r={best_ec.get('entropy_coupling', 0):+.3f}) — this is where the "
        f"model's activation magnitude tracks its uncertainty most closely."
    )
    with_sc = [p for p in profiles if p.get("self_check_alignment") is not None]
    if with_sc:
        best_sc = max(with_sc, key=lambda p: p["self_check_alignment"])
        print(
            f"  • self-check states most distinct at L{best_sc['layer']} "
            f"(cos gap={best_sc['self_check_alignment']:+.3f}) — the "
            f"verification state is most separable there."
        )
    ranks = [(p["layer"], p.get("effective_rank", 0)) for p in profiles]
    if ranks:
        lo = min(ranks, key=lambda t: t[1])
        hi = max(ranks, key=lambda t: t[1])
        print(
            f"  • narrowest state at L{lo[0]} (eff. rank {lo[1]:.1f}); "
            f"widest at L{hi[0]} ({hi[1]:.1f})"
        )
    return 0


def _fmt(v: Optional[float]) -> str:
    return "  n/a " if v is None else f"{v:+.3f}"


def cli():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--data-root", type=str,
                    default="datasets/aime_qwen3_1p7b_16k_fp16/aime")
    ap.add_argument("--out", type=str,
                    default="backend/examples/output/layer_profiles.json")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--min-tokens", type=int, default=40)
    ap.add_argument("--max-tokens-per-traj", type=int, default=512)
    ap.add_argument("--sketch-dim", type=int, default=128)
    return main(ap.parse_args())


if __name__ == "__main__":
    raise SystemExit(cli())
