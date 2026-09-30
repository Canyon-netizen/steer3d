"""Distil the collected trajectories into a small problem index.

The sidecar JSON next to each trajectory holds a full per-token record
list — enough to reconstruct every activation — and runs to tens of
megabytes per file. Reading those off a network filesystem just to get
the *problem text* is slow and pointless, so this writes a few kilobytes
containing only what an intervention run needs:

    { "<problem_id>": {"id", "prompt", "answer", "correct"}, ... }

Pass the result to `run_intervention.py --problems-file`. Duplicates
between the `think` and `no_think` variants of a problem are collapsed
on problem id, so the sample stays independent rather than doubled.

Usage:
    python3 backend/examples/make_problem_index.py \
        --data-root datasets/aime_qwen3_1p7b_16k_fp16/aime \
        --out /tmp/problem_index.json
"""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path


def build(data_roots, out_path: Path) -> dict:
    problems: dict = {}
    n_files = 0
    for root in data_roots:
        pattern = str(Path(root) / "*.json")
        for j in sorted(glob.glob(pattern)):
            n_files += 1
            try:
                meta = json.loads(Path(j).read_text())
            except Exception:
                continue
            pid = meta.get("problem_id")
            prompt = meta.get("prompt")
            if not pid or not prompt or pid in problems:
                continue
            problems[pid] = {
                "id": pid,
                "prompt": prompt,
                "answer": meta.get("ground_truth", ""),
                "correct": bool(meta.get("is_correct")),
            }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(problems, indent=1, ensure_ascii=False))

    solved = [k for k, v in problems.items() if v["correct"]]
    print(f"read {n_files} sidecar(s) → {len(problems)} unique problems")
    print(f"  {len(solved)} the model originally solved: {sorted(solved)}")
    print(f"  wrote {out_path} ({out_path.stat().st_size / 1024:.1f} KB)")
    return problems


def main(args) -> int:
    roots = args.data_root or [
        "datasets/aime_qwen3_1p7b_16k_fp16/aime",
        "datasets/aime_qwen3_1p7b_32k_fp32/aime",
    ]
    build(roots, Path(args.out))
    return 0


def cli():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--data-root", type=str, nargs="*", default=None)
    ap.add_argument("--out", type=str, default="backend/examples/output/problem_index.json")
    return main(ap.parse_args())


if __name__ == "__main__":
    raise SystemExit(cli())
