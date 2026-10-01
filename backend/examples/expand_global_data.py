"""Project every Qwen3-1.7B .npz trajectory in the dataset through one
global PCA PER LAYER, and write a unified `qwen3_global.json` that the
token-terrain player can consume.

This replaces the single-layer `qwen3_global.json` produced by the
older run_global.py with one that covers all 28 residual-stream layers
for every trajectory on disk (both `16k_fp16` and `32k_fp32` configs),
so the player can switch layers at runtime.

JSON structure (one record per trajectory):

    {
      "trajectory_id": "...",
      "prompt": "...",
      "correct": true/false/null,
      "config": "16k_fp16"/"32k_fp32",
      "n_tokens": N,
      "tokens": [   # SHARED across layers — token-level metadata
        {"tok": "...", "ppl": ..., "ent": ..., "sc": bool,
         "rv": bool, "step_id": int},
        ...
      ],
      "layers": {   # PER-LAYER projected (x,y,z)
        "0":  {"xyz": [x0,y0,z0, x1,y1,z1, ...]},  # Float32-packed
        "1":  {"xyz": [...]},
        ...
        "27": {"xyz": [...]}
      }
    }

Run:
    python backend/examples/expand_global_data.py
→ writes backend/examples/output/qwen3_global.json
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
DATA_ROOT = HERE.parent.parent / "datasets"   # .../steer3d/datasets
N_LAYERS = 28

# Self-check heuristics
SELF_CHECK_PATTERNS = [
    r"\bwait\b", r"\bactually\b", r"\bbut\b", r"\bhmm\b", r"\breconsider",
    r"let me (?:check|reconsider|verify|re-?examine)",
    r"on (?:second )?thought",
    r"that'?s (?:not )?(?:right|correct)",
]


# ---------------------------------------------------------------------------
# Configs to harvest
# ---------------------------------------------------------------------------
CONFIGS = [
    DATA_ROOT / "aime_qwen3_1p7b_16k_fp16",
    DATA_ROOT / "aime_qwen3_1p7b_32k_fp32",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def softmax_entropy(topk_logits: np.ndarray) -> tuple[float, float]:
    tl = np.asarray(topk_logits, dtype=np.float64)
    if not np.isfinite(tl).all() or tl.size == 0:
        return 1.0, 0.0
    m = tl.max()
    log_z = m + np.log(np.exp(tl - m).sum())
    log_p = tl - log_z
    log_p_clamped = np.maximum(log_p, -50.0)
    p = np.exp(log_p_clamped)
    H = float(-(p * log_p_clamped).sum())
    if not np.isfinite(H) or H < 0:
        return 1.0, 0.0
    return float(np.exp(min(H, 50.0))), H


def detect_self_check(token_text: str) -> bool:
    if not token_text:
        return False
    t = token_text.lower().strip()
    for pat in SELF_CHECK_PATTERNS:
        if re.search(pat, t):
            return True
    if t in {"wait", "hmm", "but", "actually"}:
        return True
    return False


def detect_revisit(token_text: str, seen: set[str]) -> bool:
    if not token_text or len(token_text) < 3:
        return False
    t = token_text.strip()
    if t in seen:
        return True
    seen.add(t)
    return False


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main():
    # 1) Discover all .npz files + their .json sidecars
    npz_files: list[tuple[Path, Path]] = []
    for cfg in CONFIGS:
        aime_dir = cfg / "aime"
        if not aime_dir.exists():
            print(f"  skip (no aime/): {cfg}")
            continue
        for npz in sorted(aime_dir.glob("*.npz")):
            j = npz.with_suffix(".json")
            if j.exists():
                npz_files.append((npz, j))
    print(f"found {len(npz_files)} trajectories on disk")

    # 2) For each trajectory, discover shape + finite-mask per layer
    print("loading trajectory metadata…")
    traj_meta = []   # [{'npz': Path, 'json': Path, 'n_tok': int, 'n_layer': int, 'finite_masks': [array per layer]}]
    for npz, j in npz_files:
        try:
            d = np.load(npz, allow_pickle=True)
        except Exception as e:
            print(f"  ! {npz.name}: {e}")
            continue
        if "hidden_states" not in d.files:
            print(f"  ! {npz.name}: no hidden_states")
            continue
        hs = d["hidden_states"]
        n_tok, n_layer, _ = hs.shape
        finite_masks = []
        for li in range(n_layer):
            l_all = hs[:, li, :].astype(np.float32)
            finite_masks.append(np.isfinite(l_all).all(axis=1))
        traj_meta.append({"npz": npz, "json": j, "n_tok": int(n_tok),
                          "n_layer": int(n_layer), "finite_masks": finite_masks})

    if not traj_meta:
        raise SystemExit("no usable trajectories found")

    # 3) For each layer, fit a global PCA + project every trajectory through it
    print(f"computing per-layer global PCA + projection ({N_LAYERS} layers)…")
    layer_data = {}   # layer_idx -> {tid: [x,y,z] array per token}
    for li in range(N_LAYERS):
        # 3a) Pool clean rows from every trajectory that has this layer
        pooled = []
        valid_tids = []
        for meta in traj_meta:
            if meta["n_layer"] <= li:
                continue
            try:
                d = np.load(meta["npz"], allow_pickle=True)
            except Exception:
                continue
            hs = d["hidden_states"]
            l_all = hs[:, li, :].astype(np.float32)
            finite_mask = meta["finite_masks"][li]
            l_clean = l_all[finite_mask]
            if l_clean.shape[0] < 16:
                continue
            idx = np.linspace(0, l_clean.shape[0] - 1, min(80, l_clean.shape[0])).astype(int)
            pooled.append(l_clean[idx])
            valid_tids.append(meta["npz"].stem)
        if len(pooled) < 3:
            print(f"  layer {li}: skipped (only {len(pooled)} trajectories)")
            continue
        arr = np.concatenate(pooled, axis=0)
        # 3b) Fit PCA(3) via SVD
        mean = arr.mean(axis=0)
        X = (arr - mean).astype(np.float64)
        X += 1e-5 * np.random.standard_normal(X.shape)
        _, _, Vt = np.linalg.svd(X, full_matrices=False)
        components = Vt[:3].T
        # 3c) Project every trajectory's layer-li hidden states
        layer_data[li] = {"mean": mean, "components": components, "projs": {}}
        for meta in traj_meta:
            if meta["n_layer"] <= li:
                continue
            try:
                d = np.load(meta["npz"], allow_pickle=True)
            except Exception:
                continue
            hs = d["hidden_states"][:, li, :].astype(np.float64)
            bad_rows = ~meta["finite_masks"][li]
            if bad_rows.any():
                hs[bad_rows] = mean.astype(np.float64)
            proj = (hs - mean) @ components  # (N, 3)
            layer_data[li]["projs"][meta["npz"].stem] = proj.astype(np.float32)
        print(f"  layer {li:2d}: PCA on {arr.shape[0]} rows; "
              f"projected {len(layer_data[li]['projs'])} trajectories")

    # 4) Build the JSON: per-run record with shared tokens + per-layer xyz
    # Layer 14 stays in the JSON (so the page can render immediately without
    # a second fetch); the other 27 layers are written as separate binary
    # files under output/layer_xyz/<run_id>__l<N>.bin for lazy loading.
    print("writing JSON + per-layer binary files…")
    XY_DIR = OUT / "layer_xyz"
    XY_DIR.mkdir(exist_ok=True)
    runs_out = []
    for meta in traj_meta:
        npz, j = meta["npz"], meta["json"]
        tid = npz.stem
        sidecar = json.loads(j.read_text())
        d = np.load(npz, allow_pickle=True)
        N = meta["n_tok"]
        n_prompt = int(sidecar.get("n_prompt_tokens", 0))

        # Shared token-level metadata (this is the only thing in the main JSON)
        token_texts = _decode_tokens(d, sidecar, N)
        ppl = np.ones(N, dtype=np.float32)
        ent = np.zeros(N, dtype=np.float32)
        if "topk_logits" in d.files and d["topk_logits"].shape[0] >= N:
            for i in range(N):
                p, h = softmax_entropy(d["topk_logits"][i])
                ppl[i] = p
                ent[i] = h

        seen: set[str] = set()
        token_records = []
        for i in range(N):
            t = token_texts[i]
            sc = (i >= n_prompt) and detect_self_check(t)
            rv = (i >= n_prompt) and detect_revisit(t, seen)
            token_records.append({
                "tok":      t,
                "ppl":      float(ppl[i]),
                "ent":      float(ent[i]),
                "sc":       bool(sc),
                "rv":       bool(rv),
                "step_id":  int(i - n_prompt),
            })

        cfg_name = npz.parts[-3]
        kind = "math" if sidecar.get("dataset") == "aime" else "unknown"
        tag = "16k" if "16k" in cfg_name else "32k"

        # Per-layer xyz: layer 14 inlined in JSON, others to binary files
        layers_in_json = {}
        layers_to_bin = {}
        for li in range(N_LAYERS):
            if li not in layer_data:
                continue
            projs = layer_data[li]["projs"]
            if tid not in projs:
                continue
            xyz = projs[tid]                    # (N, 3) float32
            if li == 14:
                layers_in_json[str(li)] = {"xyz": xyz.flatten().tolist()}
            else:
                layers_to_bin[li] = xyz

        # Write per-layer binary files
        for li, xyz in layers_to_bin.items():
            (XY_DIR / f"{tid}__l{li}.bin").write_bytes(
                xyz.astype(np.float16).tobytes()
            )

        runs_out.append({
            "prompt":          sidecar.get("prompt", ""),
            "expected":        sidecar.get("ground_truth", ""),
            "generated_text":  (sidecar.get("generated_text") or "")[:400],
            "tag":             tag,
            "kind":            kind,
            "correct":         sidecar.get("is_correct"),
            "wallclock_s":     0.0,
            "n_tokens":        N - n_prompt,
            "config":          cfg_name,
            "problem_id":      sidecar.get("problem_id", ""),
            "trajectory_id":   tid,
            "tokens":          token_records,
            "layers":          layers_in_json,
        })

    out_path = OUT / "qwen3_global.json"
    out_path.write_text(json.dumps(runs_out, ensure_ascii=False))
    size_mb = out_path.stat().st_size / 1024 / 1024
    n_bin = len(list(XY_DIR.glob("*.bin")))
    print(f"\nwrote {out_path}  ({size_mb:.1f} MB, {len(runs_out)} runs, "
          f"layer 14 inlined)")
    print(f"wrote {XY_DIR}/  ({n_bin} .bin files; "
          f"{sum(p.stat().st_size for p in XY_DIR.glob('*.bin')) / 1024 / 1024:.1f} MB)")


def _decode_tokens(d: np.ndarray, sidecar: dict, N: int) -> list[str]:
    """Try sidecar.tokens[] first, then fall back to Qwen3 tokenizer."""
    side_tokens = sidecar.get("tokens", [])
    if side_tokens and isinstance(side_tokens[0], dict) and "token" in side_tokens[0]:
        out = [str(t.get("token", "")) for t in side_tokens]
    else:
        try:
            from transformers import AutoTokenizer
            tok = getattr(_decode_tokens, "_tok", None)
            if tok is None:
                tok = AutoTokenizer.from_pretrained(
                    "Qwen/Qwen3-1.7B", trust_remote_code=True
                )
                _decode_tokens._tok = tok
            ids = d["token_ids"][:N]
            out = tok.convert_ids_to_tokens(ids.tolist())
        except Exception as e:
            print(f"  ! token decode failed: {e}")
            out = [""] * N
    if len(out) < N:
        out = out + [""] * (N - len(out))
    return out[:N]


if __name__ == "__main__":
    main()
