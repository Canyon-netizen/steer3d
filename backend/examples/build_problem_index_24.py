"""Regenerate the 24-problem index from the built-in problem bank.

The original run read `/tmp/problem_index.json` on zju-53, which is gone. The
problem *ids* survive in the 168-run outputs, so the index is only trustworthy
if the rebuilt set matches those ids exactly -- verified below, not assumed.
The text comes from `aime_loader._BUILTIN` (the authoritative source), never
hand-copied.

Note for whoever reads the data later: these are AIME-*style* problems
inspired by AIME 1983-2024 and re-worded, not verbatim competition problems.
That provenance is unchanged from the existing 168-run dataset.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.core.aime_loader import _BUILTIN  # noqa: E402

# The exact id set that produced the existing 168-run dataset.
PRIOR_IDS = {
    "1983_I_1", "1984_I_1", "1985_I_1", "1986_I_1", "1987_I_1", "1988_I_1",
    "1989_I_1", "1990_I_1", "1991_I_1", "1992_I_1", "1994_I_1", "2000_I_1",
    "2002_I_1", "2004_I_1", "2010_I_1", "2012_I_1", "2014_I_1", "2016_I_1",
    "2020_I_1", "2021_I_1", "2022_I_1", "2023_I_1", "2024_I_1", "2025_I_1",
}

rows = []
for p in _BUILTIN:
    rows.append({
        "id": p["id"],
        "prompt": p["problem"],
        # `correct` is unused by run_intervention.py; kept for parity with the
        # 6-problem index so both files have the same shape.
        "correct": True,
    })

ids = [r["id"] for r in rows]
if len(set(ids)) != len(ids):
    raise SystemExit("FAIL: duplicate ids in rebuilt index")
missing = PRIOR_IDS - set(ids)
extra = set(ids) - PRIOR_IDS
if missing or extra:
    print("FAIL: id set does not match the 168-run dataset")
    print("  missing:", sorted(missing))
    print("  extra  :", sorted(extra))
    raise SystemExit(1)

out = Path(__file__).resolve().parents[2] / "data" / "problem_index_24.json"
out.write_text(json.dumps(rows, ensure_ascii=False, indent=1))
print(f"OK  wrote {len(rows)} problems to {out}")
print(f"    id set matches the 168-run dataset exactly")
print(f"    first id={ids[0]}  last id={ids[-1]}")
