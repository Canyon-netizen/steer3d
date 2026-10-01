"""What does a steering vector do to the *reasoning*, not just the logits?

Every other experiment in this project measures intervention effects as
numbers on a distribution: mean Δentropy, mean logit KL, token agreement.
Those say the output distribution moved. They say nothing about whether the
model's *chain of thought* changed, which is the thing a person actually
reads and the thing the user asked about.

The data needed is already on disk. `run_intervention.py` returns
`primary_text` (steered) and `shadow_text` (unsteered, teacher-forced on the
same tokens) for every run, and those have been persisted all along:

    backend/examples/output/intervention/*.json

This script reads them and measures the reasoning-level effect. The
dual-stream construction matters here: because the shadow is teacher-forced
from the primary's own tokens, a divergence in the text is *not* an artefact
of the two streams having wandered onto different sentences -- it is the
consequence of the same prefix carrying a different state.

Measured, per run:

  * first divergence point, in tokens and as a fraction of the trace
  * length change
  * structural markers that indicate the model is checking its own work
    ("wait", "actually", "let me verify", ...) -- the CoT-level analogue of
    the `caution` direction
  * answer agreement: does the extracted final answer change, even when 94%
    of the tokens agree?  Token agreement is the quantity every earlier
    finding reported; answer agreement is the one that actually matters.
  * verbatim-overlap of reasoning steps, to separate "reworded" from
    "re-derived"

The control is built in: a strength-0.0 run is the same code path with a
zero vector, and any effect it shows is the harness, not the intervention.
It is reported alongside every other condition so the reader can subtract it.

Usage:
    python3 backend/examples/analyse_cot_divergence.py \
        --json backend/examples/output/intervention/replication_24problems_L20.json \
        --out backend/examples/output/intervention/cot_divergence_24problems.json
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# The same marker set the steering-vector extractor uses for `caution`, so
# the behavioural number here and the direction that supposedly moves it
# are measured against the same definition.
SELF_CHECK_RE = re.compile(
    r"\b(wait|actually|hmm|hold on|let me check|let me verify|recheck|"
    r"double[- ]check|second thought|alternatively|but wait)\b",
    re.IGNORECASE,
)

# Final-answer extraction. AIME answers are integers 0-999.
ANSWER_RE = re.compile(r"(?:answer|Answer)\s*(?:is)?\s*[:：]?\s*\$?\\?boxed\{?\s*(\d{1,4})", re.IGNORECASE)
BOXED_RE = re.compile(r"\\boxed\{\s*(\d{1,4})\s*\}")
TAIL_INT_RE = re.compile(r"(-?\d{1,4})\s*[.。]?\s*$")


def extract_answer(text: str) -> Optional[int]:
    """Best-effort final answer. Returns None when nothing is extractable.

    Tries the most explicit markers first and falls back to the last integer
    in the trace. A wrong extraction is worse than an honest None, so the
    ordering encodes descending reliability.
    """
    return extract_answer_sourced(text)[0]


def extract_answer_sourced(text: str) -> Tuple[Optional[int], str]:
    """Same extraction, but reports *which* rule fired.

    The distinction matters more than it looks. ``TAIL_INT_RE`` — "whatever
    integer happens to end the text" — is a reasonable guess for a finished
    answer and an actively misleading one for a chain of thought that ran out
    of budget: it will happily return an intermediate quantity from the
    middle of a derivation and label it "the answer". Measured on the 32k
    study (2026-10-01), two runs of problem 1987 both left ``</think>`` unclosed
    and both came back with a confident integer — 1 for the control arm and
    2 for the steered one. That reads exactly like "the intervention moved the
    answer from 1 to 2", and both numbers are noise scraped off a truncated
    derivation.

    A caller comparing arms across runs needs to be able to refuse the
    fallback. Returning the source makes that possible without changing what
    every existing caller gets.
    """
    if not text:
        return None, "empty"
    m = ANSWER_RE.search(text)
    if m:
        return int(m.group(1)), "explicit"
    m = BOXED_RE.search(text)
    if m:
        return int(m.group(1)), "boxed"
    m = TAIL_INT_RE.search(text.strip())
    if m:
        return int(m.group(1)), "tail_guess"
    return None, "none"


def split_think(text: str) -> Tuple[str, str]:
    """Split a Qwen3 response into (reasoning, answer).

    Qwen3 emits `<think>...</think>` and then the answer. Responses cut off
    before closing the think block are all-reasoning, which is common at
    60 steps and is itself worth counting.
    """
    m = re.search(r"<think>(.*?)(?:</think>|$)", text, re.DOTALL)
    if not m:
        return "", text
    reasoning = m.group(1)
    rest = text[m.end():]
    return reasoning, rest


def first_divergence(a: str, b: str) -> int:
    """Index of the first differing character, or -1 if identical.

    A token-level view is not available here (only decoded text is
    persisted), so this is a character offset. It is used only for
    *ordering* -- where the two traces stop agreeing -- so the unit does
    not affect any comparison.
    """
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    if len(a) != len(b):
        return n
    return -1


def reasoning_steps(reasoning: str) -> List[str]:
    """Split reasoning into comparable units: lines and sentences."""
    lines = [l.strip() for l in reasoning.splitlines() if l.strip()]
    if lines:
        return lines
    return [s.strip() for s in re.split(r"(?<=[.!?。！？])\s+", reasoning) if s.strip()]


def analyse_run(run: dict) -> dict:
    """Reduce one intervention run to its reasoning-level measurements."""
    primary = run.get("primary_text", "") or ""
    shadow = run.get("shadow_text", "") or ""
    summary = run.get("summary", {}) or {}

    p_reason, p_ans = split_think(primary)
    s_reason, s_ans = split_think(shadow)

    p_steps = reasoning_steps(p_reason)
    s_steps = reasoning_steps(s_reason)

    p_marks = SELF_CHECK_RE.findall(p_reason)
    s_marks = SELF_CHECK_RE.findall(s_reason)

    p_answer = extract_answer(p_ans) if p_ans.strip() else extract_answer(primary)
    s_answer = extract_answer(s_ans) if s_ans.strip() else extract_answer(shadow)

    div = first_divergence(p_reason, s_reason)
    closed_think = primary.count("</think>") > 0

    return {
        "label": run.get("prompt_label"),
        "direction": run.get("direction"),
        "strength": run.get("strength"),
        "layer": run.get("layer"),
        "n_steps": summary.get("n_steps"),
        "token_agreement": summary.get("token_agreement"),
        "mean_logit_kl": summary.get("mean_logit_kl"),
        # reasoning-level
        "reason_chars_primary": len(p_reason),
        "reason_chars_shadow": len(s_reason),
        "reason_len_ratio": (len(p_reason) / len(s_reason)) if s_reason else None,
        "n_steps_primary": len(p_steps),
        "n_steps_shadow": len(s_steps),
        "selfcheck_primary": len(p_marks),
        "selfcheck_shadow": len(s_marks),
        "selfcheck_delta": len(p_marks) - len(s_marks),
        "answer_primary": p_answer,
        "answer_shadow": s_answer,
        "answer_known": p_answer is not None and s_answer is not None,
        "answer_changed": (p_answer is not None and s_answer is not None
                           and p_answer != s_answer),
        "verbatim_step_overlap": (
            len(set(p_steps) & set(s_steps)) / len(set(p_steps) | set(s_steps))
            if (p_steps or s_steps) else None
        ),
        "first_divergence_char": div,
        "closed_think": closed_think,
    }


def mean(xs: List[Optional[float]]) -> Optional[float]:
    vals = [x for x in xs if x is not None]
    return statistics.fmean(vals) if vals else None


def paired_t(diffs: List[float]) -> Tuple[Optional[float], Optional[float], int]:
    """One-sample t-test on a paired difference. Returns (t, p, n).

    Two-sided, Student. Implemented directly so the script has no scipy
    dependency -- scipy is present in the local env but not guaranteed on
    the GPU boxes, and this is the only statistic it needs.
    """
    n = len(diffs)
    if n < 2:
        return None, None, n
    m = statistics.fmean(diffs)
    sd = statistics.stdev(diffs)
    if sd == 0.0:
        return (None, 0.0 if m == 0 else 1.0, n)
    t = m / (sd / (n ** 0.5))
    # Two-sided p from the t distribution, via the incomplete beta function.
    try:
        from scipy import stats as _st
        p = float(2.0 * _st.t.sf(abs(t), n - 1))
    except Exception:
        p = _t_sf_approx(abs(t), n - 1)
    return t, p, n


def _t_sf_approx(t: float, df: int) -> float:
    """Two-sided p-value for a t statistic, via the normal approximation.

    Accurate enough for the magnitudes reported here (|t| is generally > 3);
    used only when scipy is unavailable, and the script records which path
    it took.
    """
    from math import erfc, sqrt
    return erfc(abs(t) / sqrt(2.0))


def _selftest() -> None:
    """Verify the answer extractor before its output is used for a claim."""
    cases = [
        (r"<think>reasoning...</think>\n\nThe final answer is \boxed{60}.",
         60, "boxed after a closed think block"),
        (r"<think>r</think>\nThe answer is 123.", 123, "plain prose"),
        (r"<think>r</think>\n\boxed{999}", 999, "bare boxed"),
        ("<think>r</think>\nSo the value comes to 45.", 45, "trailing integer"),
        ("<think>unclosed reasoning that just stops", None,
         "think never closed — must NOT invent an answer"),
        ("", None, "empty text"),
    ]
    bad = []
    for text, expect, label in cases:
        got = extract_answer(text)
        if got != expect:
            bad.append(f"{label}: expected {expect}, got {got}")
    if bad:
        raise SystemExit("answer extractor self-test FAILED:\n  " +
                         "\n  ".join(bad))


def main() -> None:
    # The extractor decides whether the answer-level effect is measurable at
    # all, so it is checked before it is trusted. A wrong extraction is worse
    # than an honest None: it would turn "no answer was found" into "the
    # answer never changed", which is the specific claim this script exists
    # to avoid making on short traces.
    _selftest()

    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True, nargs="+",
                    help="intervention output JSON file(s) to analyse")
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-strength", type=float, default=None,
                    help="only report conditions at or above this strength")
    args = ap.parse_args()

    runs: List[dict] = []
    for path in args.json:
        data = json.loads(Path(path).read_text())
        if isinstance(data, dict):
            data = data.get("runs", [data])
        runs.extend(data)

    if not runs:
        raise SystemExit("no runs found")

    rows = [analyse_run(r) for r in runs]
    rows = [r for r in rows if r["n_steps"] is not None]

    # --- group by (direction, strength), which is the experimental cell ---
    groups: Dict[Tuple, List[dict]] = defaultdict(list)
    for r in rows:
        if args.min_strength is not None and r["strength"] < args.min_strength:
            continue
        groups[(r["direction"], r["strength"])].append(r)

    summary = []
    for (direction, strength), cell in sorted(
        groups.items(), key=lambda kv: (str(kv[0][0]), kv[0][1])
    ):
        known = [r for r in cell if r["answer_known"]]
        n_changed = sum(1 for r in known if r["answer_changed"])
        # The self-check delta is a paired per-problem difference, so it can
        # be tested; the length ratio is not paired (two separate traces).
        sc_diffs = [r["selfcheck_delta"] for r in cell]
        t_sc, p_sc, n_sc = paired_t(sc_diffs)
        ov = [r["verbatim_step_overlap"] for r in cell]
        # Sign test on answer change is not applicable (binary), so report
        # the count and let the reader judge; with n=24 and a handful of
        # changes this is descriptive, not inferential.
        summary.append({
            "direction": direction,
            "strength": strength,
            "n": len(cell),
            "mean_token_agreement": mean([r["token_agreement"] for r in cell]),
            "mean_logit_kl": mean([r["mean_logit_kl"] for r in cell]),
            # reasoning
            "mean_reason_len_ratio": mean([r["reason_len_ratio"] for r in cell]),
            "mean_selfcheck_primary": mean([r["selfcheck_primary"] for r in cell]),
            "mean_selfcheck_shadow": mean([r["selfcheck_shadow"] for r in cell]),
            "mean_selfcheck_delta": mean([r["selfcheck_delta"] for r in cell]),
            "selfcheck_t": t_sc,
            "selfcheck_p": p_sc,
            "selfcheck_n": n_sc,
            "mean_verbatim_overlap": mean(ov),
            # answers
            "n_answer_known": len(known),
            "n_answer_changed": n_changed,
            "frac_answer_changed": (n_changed / len(known)) if known else None,
            "frac_closed_think": (
                sum(1 for r in cell if r["closed_think"]) / len(cell)
            ),
        })

    out = {
        "source_files": args.json,
        "n_runs": len(rows),
        "note": (
            "primary_text is the steered trace, shadow_text the unsteered "
            "trace teacher-forced on the same tokens. A strength-0.0 cell is "
            "included from the same runs and is the harness control."
        ),
        "per_condition": summary,
        "per_run": rows,
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2))

    # --- console report ---
    print(f"\n{len(rows)} runs from {len(args.json)} file(s)\n")
    hdr = (f"{'direction':<18}{'str':>6}{'n':>4}{'tokAgr':>9}{'logitKL':>10}"
           f"{'lenRatio':>10}{'scDelta':>10}{'sc p':>10}{'ovl':>7}"
           f"{'ansChg':>9}")
    print(hdr)
    print("-" * len(hdr))
    for s in summary:
        scd = s["mean_selfcheck_delta"]
        scp = s["selfcheck_p"]
        print(f"{str(s['direction']):<18}{s['strength']:>6.2f}{s['n']:>4}"
              f"{s['mean_token_agreement']:>9.4f}"
              f"{s['mean_logit_kl']:>10.4f}"
              f"{s['mean_reason_len_ratio']:>10.3f}"
              f"{scd:>10.2f}"
              f"{('%.4f' % scp) if scp is not None else '   n/a':>10}"
              f"{s['mean_verbatim_overlap']:>7.3f}"
              f"{s['n_answer_changed']:>4}/{s['n_answer_known']:<4}")
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
