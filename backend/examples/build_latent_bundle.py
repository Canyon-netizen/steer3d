"""Build the data bundle for the interactive latent-space viewer.

Why this file exists
--------------------
The delivered page (`qwen3_hidden_space.html`) contained **no hidden state
vectors at all** — only per-layer scalars like `agreement[i]` and
`lens_kl[i]`, drawn as static SVG. Zero `<canvas>`, zero event listeners.
So there was nothing in it that *could* show a hidden state changing.

The raw data was on this machine the whole time and had never been wired
up:

    datasets/aime_qwen3_1p7b_16k_fp16/aime/*.npz
        hidden_states  (T, 28, 2048) float16     <- the actual vectors
        topk_logits    (T, 64)   float16
        topk_indices   (T, 64)   int32
        prompt_hidden_states (P, 28, 2048) float32

    datasets/aime_qwen3_1p7b_16k_fp16/viewer_cache/aime/*__layers.json
        layers[i].pca_mean        (2048)          <- projection centre
        layers[i].pca_components  (4096)          <- 2048 x 2 basis
        layers[i].proj_2d         (2T,)           <- dense 2-D coords
        layers[i].terrain                           <- 3-D scene

The `pca_components` are the reason this can be a *live* viewer rather than
a video: the page can take a raw 2048-d vector it loaded, subtract the
per-layer mean and project it with that layer's own basis, in the browser,
for any layer the user drags to. Nothing is pre-rendered, so switching the
visible layer recomputes every point from the original vectors.

What gets shipped
-----------------
Raw vectors are the expensive part (48 tokens x 28 layers x 2048 x fp16 =
5.5 MB per trajectory), so the token window is a parameter. The PCA basis
and the 2-D coordinates are cheap and cover the *whole* trajectory, so the
page has a dense cloud to fly around and exact raw vectors to inspect in
the window where it matters.

Float16 is kept for the vectors rather than float32: it halves the bundle
and the residual stream was produced in bf16, so the extra digits would be
noise being paid for with bandwidth.

Usage
-----
    python3 backend/examples/build_latent_bundle.py \
        --dataset datasets/aime_qwen3_1p7b_16k_fp16 \
        --variant think --problems 12 --tokens 48 \
        --out frontend/public/latent/data
"""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np


# ---------------------------------------------------------------------------
# float16 <-> bytes, without depending on torch being installed here
# ---------------------------------------------------------------------------


def f16_bytes(arr: np.ndarray) -> bytes:
    return np.ascontiguousarray(arr, dtype=np.float16).tobytes()


def _write_bin(path: Path, arr: np.ndarray) -> int:
    """Write a float32 .bin and return its byte size.

    Plain little-endian float32 rather than .npy: the browser reads it with
    a bare `new Float32Array(buf)` and knows the exact shape from a
    sidecar. A .npy header per file would be 128 bytes of parsing the page
    has to do anyway, for no benefit.
    """
    a = np.ascontiguousarray(arr, dtype="<f4")
    path.write_bytes(a.tobytes())
    return a.nbytes


def _write_f16_bin(path: Path, arr: np.ndarray) -> int:
    a = np.ascontiguousarray(arr, dtype="<f2")
    path.write_bytes(a.tobytes())
    return a.nbytes


def _write_i32_bin(path: Path, arr: np.ndarray) -> int:
    """int32 must NOT go through _write_bin.

    _write_bin casts everything to float32. Token ids written that way and
    read back as Int32 come out as their float bit patterns — 1209277632
    instead of 151667 — which looks like a plausible integer and silently
    destroys every label in the page.
    """
    a = np.ascontiguousarray(arr, dtype="<i4")
    path.write_bytes(a.tobytes())
    return a.nbytes


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_trajectory(npz_path: Path) -> dict:
    d = np.load(npz_path, allow_pickle=True)
    meta = json.loads(npz_path.with_suffix(".json").read_text())
    return {
        "npz": d,
        "meta": meta,
        "hidden": d["hidden_states"],          # (T, L, D) float16
        "token_ids": d["token_ids"],
        "topk_logits": d["topk_logits"],
        "topk_indices": d["topk_indices"],
        "n_layers": int(d["hidden_states"].shape[1]),
        "d_model": int(d["hidden_states"].shape[2]),
    }


def load_cache(cache_dir: Path, traj_id: str) -> Optional[dict]:
    p = cache_dir / f"{traj_id}__layers.json"
    if not p.exists():
        return None
    return json.loads(p.read_text())


# ---------------------------------------------------------------------------
# Bundle
# ---------------------------------------------------------------------------


def build(args) -> int:
    ds = Path(args.dataset)
    aime = ds / "aime"
    cache = ds / "viewer_cache" / "aime"
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    npz_files = sorted(p for p in aime.glob("*.npz")
                       if p.stem.endswith(f"__{args.variant}"))
    if not npz_files:
        print(f"ERROR: no *__{args.variant}.npz under {aime}")
        return 1
    if args.problems:
        npz_files = npz_files[: args.problems]
    print(f"{len(npz_files)} trajectory/trajectories, variant={args.variant}")

    index: List[dict] = []
    dim_names: Optional[np.ndarray] = None
    total = 0

    for i, npz_path in enumerate(npz_files):
        traj_id = npz_path.stem
        tr = load_trajectory(npz_path)
        T, L, D = tr["hidden"].shape
        n_tok = min(args.tokens, T)
        print(f"\n[{i+1}/{len(npz_files)}] {traj_id}")
        print(f"  T={T} L={L} D={D}  shipping first {n_tok} tokens")

        # --- raw vectors, the expensive payload -------------------------
        raw = tr["hidden"][:n_tok]                      # (n, L, D) fp16
        hs_bytes = _write_f16_bin(out / f"hs_{i:02d}.bin", raw)
        total += hs_bytes

        # --- candidate tokens at every shipped step ----------------------
        tl = tr["topk_logits"][:n_tok].astype(np.float32)
        ti = tr["topk_indices"][:n_tok].astype(np.int32)
        topk_bytes = _write_bin(out / f"topk_{i:02d}.bin", tl) \
            + _write_i32_bin(out / f"topki_{i:02d}.bin", ti)
        total += topk_bytes

        # --- per-layer PCA: this is what makes the page live -------------
        # All layers go into ONE file each, not L files. The page was
        # originally built with 28 layers x 3 files = 84 separate fetches
        # issued in parallel, which overruns a plain http.server's listen
        # backlog and leaves the page on the loading screen forever with no
        # error. Five files per trajectory also transfers and unzips
        # better than eighty-four, and the per-layer offsets are just
        # arithmetic.
        comps: List[np.ndarray] = []
        means: List[np.ndarray] = []
        projs: List[np.ndarray] = []
        layer_meta: List[dict] = []
        cache_entry = load_cache(cache, traj_id)
        if cache_entry is None:
            print(f"  !! no viewer_cache for {traj_id}; "
                  f"computing PCA here over the first {n_tok} tokens")
            pca_src = tr["hidden"][: min(1024, T)].astype(np.float32)
        else:
            pca_src = None

        for li in range(L):
            if cache_entry is not None:
                le = cache_entry["layers"][li]
                mean = np.asarray(le["pca_mean"], dtype=np.float32)
                # Stored component-major: row 0 is PC1 over all 2048 dims,
                # row 1 is PC2. Reshaping to (D, 2) instead gives a (D, 2)
                # matrix that is a *transpose*, which projects the cloud
                # into a rotated, differently-scaled space — it still
                # looks like a plausible scatter plot, so nothing about the
                # output would signal the mistake. Asserted below.
                comp = np.asarray(le["pca_components"],
                                  dtype=np.float32).reshape(2, -1).T.copy()
                dmean = np.asarray(le.get("ppl_mean", 0.0), dtype=np.float32)
                dmax = np.asarray(le.get("ppl_max", 0.0), dtype=np.float32)
            else:
                X = pca_src[:, li, :]
                mean = X.mean(axis=0)
                _, sv, Vt = np.linalg.svd(X - mean, full_matrices=False)
                comp = (Vt[:2].T * sv[:2]).astype(np.float32)
                dmean, dmax = 0.0, 0.0

            norms = np.linalg.norm(comp, axis=0)
            assert comp.shape == (D, 2), f"layer {li}: {comp.shape}"
            assert np.allclose(norms, 1.0, atol=0.05), (
                f"layer {li}: component norms {norms} are not ~1 — the "
                f"storage layout is probably not component-major")

            Xfull = tr["hidden"][:, li, :].astype(np.float32)
            proj = ((Xfull - mean) @ comp).reshape(-1)

            # The cached coordinates cover only a 1024-token prefix of a
            # 2048-token trajectory. Reusing them would give the page a
            # cloud that stops halfway with twice as many labels, so they
            # are recomputed here over every token — using the cached basis,
            # which is the part that has to be shared so the page can
            # project in the browser. When a cached coordinate does exist
            # the two must agree; if they do not, the basis is not what the
            # cache used and every point on the page would be in the wrong
            # place.
            if cache_entry is not None:
                ref = np.asarray(cache_entry["layers"][li]["proj_2d"],
                                 dtype=np.float32)
                k = min(ref.size // 2, T)
                ref_k = ref[:k * 2].reshape(k, 2)
                err = float(np.abs(proj[:k * 2].reshape(k, 2) - ref_k).max())
                # Relative, not absolute: the residual stream's norm grows
                # by two orders of magnitude with depth (L14 ~164, L20 ~866,
                # L24 ~1928 in layer_profiles.json), so a fixed epsilon
                # rejects the deep layers for being large rather than wrong.
                # A genuinely transposed basis misses by 10-50 absolute, so
                # 1% of the coordinate span still separates the two cases
                # by three orders of magnitude.
                span = float(np.abs(ref_k).max()) or 1.0
                rel = err / span
                assert rel < 1e-2, (
                    f"layer {li}: recomputed projection differs from the "
                    f"cached one by {err:.4g} ({rel:.2%} of span "
                    f"{span:.4g}) — basis orientation is probably wrong")

            comps.append(comp)
            means.append(mean)
            projs.append(proj)
            layer_meta.append({
                "layer": li,
                "ppl_mean": float(dmean), "ppl_max": float(dmax),
                "n_proj": int(proj.size // 2),
            })

        # (L, D, 2), (L, D), (L, 2T) — three files, not 3L.
        n1 = _write_bin(out / f"pca_{i:02d}.bin", np.stack(comps))
        n2 = _write_bin(out / f"mean_{i:02d}.bin", np.stack(means))
        n3 = _write_bin(out / f"proj_{i:02d}.bin", np.stack(projs))
        total += n1 + n2 + n3
        print(f"  {L} layers -> pca {n1/1e3:.0f}KB  mean {n2/1e3:.0f}KB  "
              f"proj {n3/1e3:.0f}KB")

        # --- per-token metadata for the whole trajectory ------------------
        toks = tr["meta"].get("tokens", [])
        n_meta = min(len(toks), T)
        all_tok = [{
            "i": t.get("step_id", k),
            "id": int(tr["token_ids"][k]),
            "s": t.get("token", ""),
            "ppl": t.get("perplexity", t.get("ppl")),
            "ent": t.get("entropy", t.get("ent")),
            "top1": t.get("top1_prob"),
            "think": bool(t.get("is_in_think_block", t.get("in_think", False))),
        } for k, t in enumerate(toks[:n_meta])]

        index.append({
            "id": traj_id,
            "problem_id": tr["meta"].get("problem_id"),
            "problem": tr["meta"].get("prompt", "")[:400],
            "answer": tr["meta"].get("generated_answer"),
            "ground_truth": tr["meta"].get("ground_truth"),
            "correct": tr["meta"].get("is_correct"),
            "n_tokens_total": int(T),
            "n_tokens_shipped": int(n_tok),
            "d_model": D,
            "n_layers": L,
            "hs": f"hs_{i:02d}.bin",
            "topk": f"topk_{i:02d}.bin",
            "topki": f"topki_{i:02d}.bin",
            "pca": f"pca_{i:02d}.bin",
            "mean": f"mean_{i:02d}.bin",
            "proj": f"proj_{i:02d}.bin",
            "n_layers": L,
            "d_model": D,
            "layers": layer_meta,
            "tokens": all_tok,
            "system_prompt": (tr["meta"].get("system_prompt") or "")[:400],
        })

    # --- dimension dictionary, if the server produced one ---------------
    dim_file = Path(args.dim_names)
    if dim_file.exists():
        dim_names = json.loads(dim_file.read_text())
        print(f"\ndimension dictionary: {dim_file} "
              f"({len(dim_names.get('dims', []))} dims)")
    else:
        print(f"\n!! no dimension dictionary at {dim_file} — the page will "
              f"show raw dimension indices without names")

    manifest = {
        "schema": "latent_bundle_v1",
        "dataset": str(ds),
        "variant": args.variant,
        "n_layers": index[0]["n_layers"],
        "d_model": index[0]["d_model"],
        "n_tok_shipped": index[0]["n_tokens_shipped"],
        "topk": 64,
        "trajectories": index,
        "dim_names": dim_names,
    }
    mf = out / "manifest.json"
    mf.write_text(json.dumps(manifest, ensure_ascii=False, separators=(",", ":")))
    total += mf.stat().st_size

    print(f"\n{'=' * 60}")
    print(f"  {len(index)} trajectories, {total/1e6:.1f} MB total")
    print(f"  manifest: {mf}")
    print(f"{'=' * 60}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", default="datasets/aime_qwen3_1p7b_16k_fp16")
    ap.add_argument("--variant", default="think", choices=["think", "no_think"])
    ap.add_argument("--problems", type=int, default=12)
    ap.add_argument("--tokens", type=int, default=48,
                    help="How many generated tokens of raw vectors to ship. "
                         "The PCA coordinates cover every token regardless.")
    ap.add_argument("--dim-names", default="frontend/public/latent/dim_names.json",
                    help="Per-dimension token dictionary produced on the server; "
                         "this is what makes the viewer interpretable rather "
                         "than just animated")
    ap.add_argument("--out", default="frontend/public/latent/data")
    args = ap.parse_args()
    return build(args)


if __name__ == "__main__":
    raise SystemExit(main())
