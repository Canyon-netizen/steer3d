"""Does the intervention change the model's final answer?

This is the cross-run question: for the same problem, does the strength-0.2
run land on a different final answer than the strength-0.0 run? That is a
different comparison from `analyse_cot_divergence.py`, which compares the two
arms *inside* one run (primary vs shadow on the same tokens). Both are worth
knowing; only this one answers "did steering change the answer".

Reuses `analyse_run` from analyse_cot_divergence so answer extraction and the
think-block split stay in exactly one place.

Three rules this file follows on purpose:

1. **The control arm gates everything.** If any strength-0.0 run is not
   bit-identical, the 0.2 differences cannot be attributed to the injection
   and the script exits non-zero instead of reporting a number.
2. **Every rate carries its denominator.** A "the answer never changed" claim
   over 2 parseable runs out of 24 is not the same claim as over 24, and the
   summary prints both counts, never a bare percentage.
3. **A problem whose baseline answer will not parse is counted separately**,
   not silently dropped -- otherwise the denominator drifts upward and the
   rate looks better than it is.
4. **"The answer changed" is not interpretable without knowing whether the
   baseline was right.** A flip that breaks a correct answer and a flip that
   fixes a wrong one are opposite findings, so each change is classified as
   correct->wrong / wrong->correct / wrong->other-wrong, against the reference
   answer in the problem bank.
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from analyse_cot_divergence import analyse_run  # noqa: E402
from backend.core.aime_loader import _BUILTIN  # noqa: E402

# The extractors in analyse_cot_divergence cap at \d{1,4}. A problem whose
# reference answer has more digits can therefore never be scored, and it would
# otherwise be indistinguishable from a model that failed to answer.
REF = {p["id"]: p["answer"] for p in _BUILTIN}
UNSCORABLE = {pid: a for pid, a in REF.items() if not a.isdigit() or len(a) > 4}

# The bank stores answers as strings; the extractor returns ints. Comparing
# them directly makes every baseline look wrong, so normalise once here.
def _as_int(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None

REF_INT = {pid: _as_int(a) for pid, a in REF.items()}


def classify(ref, base, got):
    if base is None or got is None or ref is None:
        return "unparseable"
    b_ok, g_ok = base == ref, got == ref
    if b_ok and g_ok:
        return "still_correct"
    if b_ok and not g_ok:
        return "correct_to_wrong"
    if not b_ok and g_ok:
        return "wrong_to_correct"
    return "wrong_to_other_wrong"


def load_jsonl(paths):
    runs = []
    for p in paths:
        text = Path(p).read_text()
        if p.endswith(".jsonl"):
            for line in text.splitlines():
                line = line.strip()
                if line:
                    runs.append(json.loads(line))
        else:
            data = json.loads(text)
            if isinstance(data, dict):
                data = data.get("runs", [data])
            runs.extend(data)
    return runs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    runs = load_jsonl(args.json)
    if not runs:
        raise SystemExit("no runs found")

    # A duplicated (problem, direction, strength) cell means a shard re-ran
    # something; that would silently weight one problem twice.
    seen = defaultdict(int)
    for r in runs:
        seen[(r["prompt_label"], r["direction"], r["strength"])] += 1
    dupes = {k: v for k, v in seen.items() if v > 1}
    if dupes:
        print(f"WARNING: {len(dupes)} duplicated cells, e.g. {list(dupes)[:3]}")

    rows = []
    for raw in runs:
        a = analyse_run(raw)
        # analyse_run does not expose text identity, and the control gate is
        # exactly a statement about it, so take it from the raw run.
        a["texts_identical"] = (raw.get("primary_text") == raw.get("shadow_text"))
        a["problem"] = a.get("label")
        rows.append(a)

    # ---- Gate 1: the control arm must be exactly identical -------------
    ctrl = [r for r in rows if float(r["strength"]) == 0.0]
    bad = [r for r in ctrl
           if not (r["texts_identical"]
                   and r["token_agreement"] == 1.0
                   and r["mean_logit_kl"] == 0.0)]
    gate = {
        "n_control_runs": len(ctrl),
        "n_control_identical": len(ctrl) - len(bad),
        "control_all_identical": not bad,
        "offending_control_runs": [
            {"problem": r["problem"], "token_agreement": r["token_agreement"],
             "logit_kl": r["mean_logit_kl"]}
            for r in bad
        ],
    }

    # ---- Per-problem baseline vs treatment ----------------------------
    by_problem = defaultdict(dict)
    for r in rows:
        by_problem[r["problem"]][(r["direction"], float(r["strength"]))] = r

    per_problem = []
    for pid in sorted(by_problem):
        cells = by_problem[pid]
        base = cells.get(("confidence_up", 0.0))
        ref = REF_INT.get(pid)
        entry = {
            "problem": pid,
            "reference_answer": ref,
            # A 7-digit reference answer can never be extracted by the
            # \d{1,4} extractors; flag it rather than let it look like a
            # model that failed to produce an answer.
            "unscorable_by_extractor": pid in UNSCORABLE,
            "baseline_answer": base["answer_primary"] if base else None,
            "baseline_correct": (
                None if (base is None or base["answer_primary"] is None or ref is None)
                else base["answer_primary"] == ref
            ),
            "baseline_closed_think": base["closed_think"] if base else None,
            "baseline_n_steps": base["n_steps"] if base else None,
            "treatments": {},
        }
        for (d, s), r in sorted(cells.items(), key=lambda kv: kv[0][1]):
            if (d, s) == ("confidence_up", 0.0):
                continue
            entry["treatments"][f"{d}@{s}"] = {
                "answer": r["answer_primary"],
                "closed_think": r["closed_think"],
                "n_steps": r["n_steps"],
                "token_agreement": r["token_agreement"],
                "mean_logit_kl": r["mean_logit_kl"],
                "reason_len_ratio": r["reason_len_ratio"],
                "shadow_answer": r["answer_shadow"],
                # same-problem, same-direction: did the answer move at all?
                "answer_differs_from_baseline": (
                    None if (entry["baseline_answer"] is None
                             or r["answer_primary"] is None)
                    else r["answer_primary"] != entry["baseline_answer"]
                ),
                "transition": classify(ref, entry["baseline_answer"],
                                       r["answer_primary"]) if ref else None,
            }
        per_problem.append(entry)

    # ---- Aggregate with explicit denominators -------------------------
    treatments = [
        (e["problem"], key, tv)
        for e in per_problem
        for key, tv in e["treatments"].items()
    ]
    per_cell = {}
    for key in sorted({k for _, k, _ in treatments}):
        cell = [(pid, tv) for pid, k, tv in treatments if k == key]
        closed = sum(1 for _, tv in cell if tv["closed_think"])
        base_known = sum(1 for _, tv in cell if tv["answer_differs_from_baseline"] is not None)
        changed = sum(1 for _, tv in cell if tv["answer_differs_from_baseline"] is True)
        lens = [tv["reason_len_ratio"] for _, tv in cell if tv["reason_len_ratio"] is not None]
        agrees = [tv["token_agreement"] for _, tv in cell if tv["token_agreement"] is not None]
        trans = defaultdict(int)
        for _, tv in cell:
            if tv["transition"]:
                trans[tv["transition"]] += 1
        per_cell[key] = {
            "n_runs": len(cell),
            "n_closed_think": closed,
            "frac_closed_think": closed / len(cell) if cell else None,
            "n_answer_comparable": base_known,
            "n_answer_changed": changed,
            "frac_answer_changed": (changed / base_known) if base_known else None,
            "transitions": dict(trans),
            "mean_reason_len_ratio": sum(lens) / len(lens) if lens else None,
            "mean_token_agreement": sum(agrees) / len(agrees) if agrees else None,
        }

    out = {
        "n_runs": len(rows),
        "n_problems": len(per_problem),
        "gate": gate,
        "unscorable_problems": UNSCORABLE,
        "n_baseline_correct": sum(1 for e in per_problem if e["baseline_correct"] is True),
        "n_baseline_comparable": sum(1 for e in per_problem if e["baseline_correct"] is not None),
        "per_cell": per_cell,
        "per_problem": per_problem,
        "note": (
            "answer_differs_from_baseline compares the strength-0.2 run's own "
            "primary answer against the same problem's strength-0.0 run. It is "
            "a separate question from analyse_cot_divergence.py, which compares "
            "the two arms inside one run. Denominators are reported next to "
            "every rate; a rate over a small denominator is not evidence. "
            "'transition' classifies each change against the reference answer, "
            "because correct->wrong and wrong->correct are opposite findings."
        ),
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1))

    print(f"runs={len(rows)}  problems={len(per_problem)}")
    print(f"CONTROL: {gate['n_control_identical']}/{gate['n_control_runs']} identical"
          f"  -> gate {'PASS' if gate['control_all_identical'] else 'FAIL'}")
    print(f"BASELINE: {out['n_baseline_correct']}/{out['n_baseline_comparable']} correct"
          f"  (unscorable by extractor: {sorted(UNSCORABLE)})")
    for k, v in per_cell.items():
        print(f"  {k:<24} closed {v['n_closed_think']}/{v['n_runs']}"
              f"   changed {v['n_answer_changed']}/{v['n_answer_comparable']}"
              f"   tok_agree {v['mean_token_agreement']}")
        if v["transitions"]:
            print(f"      transitions: {v['transitions']}")
    print(f"wrote {args.out}")

    if not gate["control_all_identical"]:
        print("GATE FAILED: control arm is not identical; any 0.2 difference is "
              "unattributable and the per-cell rates above must not be quoted.")
        sys.exit(2)


if __name__ == "__main__":
    main()
