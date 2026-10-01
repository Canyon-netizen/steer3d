"""Independent numpy reference for the delta view's arithmetic.

The browser check (.cache/delta_check.mjs) can only tell whether the page and
this file agree. It cannot tell whether both are wrong the same way, so the
numbers here are produced by plain numpy from the shipped .bin files, with no
code shared with the viewer.

The point of storing specific tokens is that the identity
    proj(h + delta) - proj(h) == proj(delta)
is only true because the per-layer mean cancels in the difference. If the
viewer ever subtracts the mean from the delta as well, the two stop agreeing
and this file is what catches it.
"""
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path("/Users/zhourui/code/steer3d")
DATA = REPO / "frontend/public/latent/data"
OUT = REPO / ".cache/analysis/delta_ref.json"

mf = json.loads((DATA / "pairs/pairs.json").read_text())
D = int(mf["d_model"])
n_layers = np.fromfile(DATA / "pca_00.bin", dtype=np.float32).size // (D * 2)
pca = np.fromfile(DATA / "pca_00.bin", dtype=np.float32).reshape(n_layers, D, 2)
mean = np.fromfile(DATA / "mean_00.bin", dtype=np.float32).reshape(n_layers, D)

# Probe tokens spread across the sequence rather than clustered at the start,
# where adjacent states are most similar and a transpose-type error is least
# likely to show up.
PROBE = [0, 1, 3, 7, 11, 16]

out = {"d_model": D, "note": "computed by numpy from the shipped bins",
       "layers": {}}
for p in mf["pairs"]:
    for L in p["layers"]:
        a = p["arms"][str(L)]
        if "control" not in a:
            continue
        C = np.fromfile(DATA / "pairs" / a["control"]["file"],
                        dtype=np.float16).reshape(-1, D).astype(np.float32)
        probe = [k for k in PROBE if k < C.shape[0]]
        rec = {"probe": probe,
               "ctl": [[float((C[k] - mean[L]) @ pca[L][:, 0]),
                        float((C[k] - mean[L]) @ pca[L][:, 1])] for k in probe]}
        if "delta" in a:
            Dl = np.fromfile(DATA / "pairs" / a["delta"]["file"],
                             dtype=np.float16).reshape(-1, D).astype(np.float32)
            rec["delta"] = [
                [float(Dl[k] @ pca[L][:, 0]), float(Dl[k] @ pca[L][:, 1])]
                for k in probe if k < Dl.shape[0]]
            rec["delta_probe"] = [k for k in probe if k < Dl.shape[0]]
            # The identity, evaluated in float32 here too — a numpy that
            # disagreed with the browser by more than rounding would be a
            # third, independent symptom worth knowing about.
            k = rec["delta_probe"][0] if rec["delta_probe"] else None
            if k is not None:
                lhs = ((C[k] + Dl[k] - mean[L]) - (C[k] - mean[L])) @ pca[L]
                rhs = Dl[k] @ pca[L]
                rec["identity_err"] = float(np.abs(lhs - rhs).max())
        # Every layer of every pair, not just the first one that parses: a
        # reference that covers only the layer the viewer happens to open on
        # is a reference that would miss a per-layer storage mistake.
        out["layers"][f"{p['id']}:{L}"] = rec

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(out))
print(f"wrote {OUT}  {len(out['layers'])} layer-entries")
for _k, v in out["layers"].items():
    L = _k.split(":")[-1]
    if "identity_err" in v:
        print(f"  L{L}: probe={v['probe']}  identity_err={v['identity_err']:.3e}")
    else:
        print(f"  L{L}: probe={v['probe']}  (no delta)")
