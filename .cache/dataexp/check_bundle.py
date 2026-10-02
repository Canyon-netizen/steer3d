"""Self-check for the 24-trajectory latent bundle.

Proves four things, each printed as ok/FAIL and the script exits non-zero on
any failure:

  1. manifest.json has exactly 24 trajectories with unique ids;
  2. the 24 problem_ids are exactly the id set of core.aime_loader._BUILTIN,
     read through the real loader rather than a hand-copied constant;
  3. every hs_XX.bin byte count matches the shape the manifest declares
     (n_layers x d_model x 2 bytes x n_tokens_shipped);
  4. three randomly chosen trajectories have their hs_XX.bin read back and
     compared element-by-element against the source npz hidden_states, so a
     silent reordering or off-by-one window cannot pass.

Run:  python3 .cache/dataexp/check_bundle.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "frontend/public/latent/data"
DATASET = REPO / "datasets/aime_qwen3_1p7b_16k_fp16"
EXPECTED_N = 24
N_SPOTCHECK = 3

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"[{'ok' if ok else 'FAIL'}] {label}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(label)


manifest = json.loads((DATA / "manifest.json").read_text())
trajs = manifest["trajectories"]
print(f"manifest variant={manifest['variant']} "
      f"n_layers={manifest['n_layers']} d_model={manifest['d_model']}\n")

# --- 1. count and id uniqueness -------------------------------------------
ids = [t["id"] for t in trajs]
check(f"manifest has exactly {EXPECTED_N} trajectories",
      len(trajs) == EXPECTED_N, f"got {len(trajs)}")
check("trajectory ids are unique",
      len(set(ids)) == len(ids),
      f"{len(set(ids))} unique of {len(ids)}")

# --- 2. problem coverage against the real loader ---------------------------
sys.path.insert(0, str(REPO / "backend"))
from core.aime_loader import load_aime  # noqa: E402

builtin_ids = {p["id"] for p in load_aime()}
bundle_ids = {t["problem_id"] for t in trajs}
check("problem_id set == aime_loader._BUILTIN id set",
      bundle_ids == builtin_ids,
      f"bundle {len(bundle_ids)}, builtin {len(builtin_ids)}"
      + (f", missing={sorted(builtin_ids - bundle_ids)}" if builtin_ids - bundle_ids else "")
      + (f", extra={sorted(bundle_ids - builtin_ids)}" if bundle_ids - builtin_ids else ""))

# --- 3. hs_XX.bin size matches the declared shape --------------------------
print()
size_ok = True
for t in trajs:
    p = DATA / t["hs"]
    if not p.exists():
        check(f"{t['hs']} exists", False)
        size_ok = False
        continue
    want = t["n_layers"] * t["d_model"] * 2 * t["n_tokens_shipped"]
    got = p.stat().st_size
    if got != want:
        print(f"[FAIL] {t['hs']} is {got} bytes, manifest shape "
              f"({t['n_layers']}x{t['d_model']}x2x{t['n_tokens_shipped']}) "
              f"requires {want}")
        size_ok = False
check(f"all {len(trajs)} hs_XX.bin sizes match manifest shape", size_ok)

# --- 4. element-wise read-back against the source npz ----------------------
print()
rng = np.random.default_rng(20261002)
picks = sorted(rng.choice(len(trajs), size=N_SPOTCHECK, replace=False).tolist())
for i in picks:
    t = trajs[i]
    n = t["n_tokens_shipped"]
    npz = DATASET / "aime" / f"{t['id']}.npz"
    with np.load(npz) as d:
        src = d["hidden_states"][:n]          # (n, L, D) float16
    got = np.frombuffer((DATA / t["hs"]).read_bytes(), dtype="<f2")
    got = got.reshape(src.shape)
    same_shape = got.shape == src.shape
    if not same_shape:
        check(f"{t['id']} read-back shape", False,
              f"{got.shape} != {src.shape}")
        continue
    exact = np.array_equal(got, src)
    n_diff = int((got != src).sum())
    # A slice shifted by one token still looks like a plausible vector, so
    # also prove the window is not accidentally off by one.
    check(f"{t['id']} [{i}] read-back is element-wise identical to npz "
          f"hidden_states[:{n}] ({src.size} values)",
          exact, "" if exact else f"{n_diff} differing values")
    with np.load(npz) as d:
        full = d["hidden_states"]
    shifted_differs = not np.array_equal(got, full[1:1 + n])
    check(f"{t['id']} [{i}] is not off-by-one (differs from window[1:])",
          shifted_differs)

print()
if failures:
    print(f"FAILED {len(failures)} check(s): " + "; ".join(failures))
    raise SystemExit(1)
print("ALL CHECKS PASSED")
