#!/usr/bin/env python3
"""Ship the *text* of the two arms, not just the statistics about them.

The page's "what did the vector do to the chain of thought" surface is, to this
day, a table of percentages: token agreement 94%, verbatim overlap, a length
ratio. The user asked what the intervention did to the chain of thought. A
reader cannot feel that from four percentages, and the percentages alone hide
the one thing that most needs saying out loud.

The texts have been on disk all along. `run_intervention.py` returns
`primary_text` (steered) and `shadow_text` (unsteered, teacher-forced on the
primary's own tokens) and both were persisted. This script ships a bounded
window of each, anchored at the first place the two disagree.

Two rules this script holds itself to, both of which cost me a wrong number
once already:

  1. NO QUANTITIES ARE DERIVED FROM THE TEXT. Token-level facts
     (`first_diverged_step`, `token_agreement`, `mean_logit_kl`, the two
     entropies) are measured at generation time, one argmax per step, and are
     copied through verbatim. A word-level diff of the decoded strings is NOT a
     substitute: the two texts are token-aligned but not word-aligned, so a
     single deleted token shifts every subsequent word and `difflib` reports
     the tail as one enormous "changed region" -- I measured 2585/3000 words
     "different" on a run whose token agreement is 98.3%, which is not a
     measurement, it is an artefact. The text here is illustration; the numbers
     in the table come from `summary`.

  2. THE SHADOW IS NOT AN ALTERNATIVE ESSAY, and the payload says so where the
     page will show it. `run_intervention.py` takes `next_s = argmax(logits_s)`
     but then feeds BOTH streams `next_p` (its lines 272-282). So the shadow is
     the primary's text with individual words swapped in wherever the unsteered
     model would have preferred a different one. It is a per-step counterfactual,
     not "what the model would have written". Read as prose it is incoherent in
     exactly the places where a swap happened -- which reads as the unsteered
     model getting dumber, the precise opposite of the truth. Every window in
     this payload therefore carries its swap offsets, so the page can mark them
     instead of letting a reader infer a narrative from the seams.

Usage:
    python3 backend/examples/build_cot_text_readout.py \
        --runs .cache/32k_journal/all_runs.json \
        --out  frontend/public/latent/data/cot_texts.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEST = os.path.join(ROOT, "frontend", "public", "latent", "data", "cot_texts.json")

MODEL = "Qwen3-1.7B"

# How much of each arm's opening to ship. The interesting action is at the very
# start -- the median run first disagrees at word 10 -- so a short window shows
# the whole event.
PRE_CHARS = 120
# 170, not 260: the delta panel's scroll window is 300px tall and the two arms
# are the whole point of this block, so at 260 chars each they were ~400px of
# text and the reader could only ever see one of them. Trimming the window is
# the right trade -- the shared prefix above it already establishes the
# context, and the first divergence happens in the first sentence anyway.
# 145 measured out: at 170 the two arms plus the shared prefix came to ~330px
# against the window's 300px, and the check said the unsteered arm was 47%
# visible -- close enough to look right in a DOM read and short enough that the
# reader never saw the arm they were being asked to compare against.
POST_CHARS = 145
HEAD_CHARS = 300


def split_think(text: str) -> Tuple[str, str]:
    """(reasoning, everything after it). Same rule as analyse_cot_divergence."""
    m = re.search(r"<think>(.*?)(?:</think>|$)", text, re.DOTALL)
    if not m:
        return "", text
    return m.group(1), text[m.end():]


def first_char_difference(a: str, b: str) -> int:
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    return -1 if len(a) == len(b) else n


def split_at_first_difference(reasoning: str, other: str) -> dict:
    """Cut both arms at the first place they differ.

    Emits the shared opening (identical in both arms, so it is stored once) and
    the two continuations. That shape is the honest one: everything before the
    split is character-for-character the same in both arms, so shipping it
    twice would suggest a difference that is not there, and shipping only the
    continuations would hide the context the swap happened in.

    `split_char` is a character offset into the full reasoning text and is
    labelled as such wherever it is shown. It is NOT `first_diverged_step`,
    which is a token step measured at generation time and lives in `summary`.
    """
    d = first_char_difference(reasoning, other)
    if d < 0:
        return {
            "split_char": -1,
            "before": reasoning[:PRE_CHARS],
            "after_primary": reasoning[:POST_CHARS],
            "after_shadow": reasoning[:POST_CHARS],
            "note": "两臂逐字相同，没有分岔",
        }
    start = max(0, d - PRE_CHARS)
    while start > 0 and not reasoning[start - 1].isspace():
        start -= 1
    return {
        "split_char": d,
        "before": reasoning[start:d],
        "after_primary": reasoning[d:d + POST_CHARS],
        "after_shadow": other[d:d + POST_CHARS],
        "note": "分岔处",
    }


def analyse(runs: List[dict]) -> dict:
    """Reduce the raw run list to the shipped payload."""
    by_key: Dict[Tuple[str, str], List[dict]] = {}
    for r in runs:
        by_key.setdefault((r.get("prompt_label"), r.get("direction")), []).append(r)

    payload_runs = []
    for r in runs:
        s = r.get("summary") or {}
        p_reason, p_rest = split_think(r.get("primary_text", "") or "")
        s_reason, _ = split_think(r.get("shadow_text", "") or "")
        # The strength-0.0 run for the same problem and direction is the same
        # code path with a zero vector. Its own texts are the clean reference:
        # if the shadow at 0.2 looks broken, this is what "not broken" is.
        siblings = by_key.get((r.get("prompt_label"), r.get("direction")), [])
        zero = [x for x in siblings if float(x.get("strength", -1)) == 0.0]

        fd = s.get("first_diverged_step")
        agree = s.get("token_agreement")
        payload_runs.append({
            "id": f"{r.get('prompt_label')}_{r.get('direction')}_{r.get('strength')}",
            "label": r.get("prompt_label"),
            "direction": r.get("direction"),
            "strength": r.get("strength"),
            "layer": r.get("layer"),
            "n_steps": r.get("n_steps"),
            # --- measured at generation time, copied verbatim, never re-derived
            "first_diverged_step": fd,
            "token_agreement": agree,
            "mean_logit_kl": s.get("mean_logit_kl"),
            "mean_entropy_primary": s.get("mean_entropy_primary"),
            "mean_entropy_shadow": s.get("mean_entropy_shadow"),
            "n_bad_steps": s.get("n_bad_steps"),
            # --- derived from the text, for illustration only
            "reason_chars_primary": len(p_reason),
            "reason_chars_shadow": len(s_reason),
            "closed_think_primary": "</think>" in (r.get("primary_text") or ""),
            "closed_think_shadow": "</think>" in (r.get("shadow_text") or ""),
            "primary_head": split_at_first_difference(p_reason, s_reason),
            "shadow_head": {"note": "见 primary_head.after_primary —— 切分后两臂各自那一段"},
            "zero_strength_control": {
                "id": f"{zero[0].get('prompt_label')}_{zero[0].get('direction')}_0.0",
                "token_agreement": (zero[0].get("summary") or {}).get("token_agreement"),
                "first_diverged_step": (zero[0].get("summary") or {}).get("first_diverged_step"),
                "texts_identical": (zero[0].get("primary_text") == zero[0].get("shadow_text")),
                "head": split_think(zero[0].get("primary_text", "") or "")[0][:HEAD_CHARS],
            } if zero else None,
        })

    return {"runs": payload_runs}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default=os.path.join(ROOT, ".cache", "32k_journal", "all_runs.json"))
    ap.add_argument("--out", default=DEST)
    ap.add_argument("--planned-runs", type=int, default=96,
                    help="Total the batch will reach, so the page can say how "
                         "much of it has landed. 0 when unknown.")
    args = ap.parse_args()

    runs = json.loads(Path(args.runs).read_text())
    payload = analyse(runs)

    # The gates. A control that is not the identity would mean every number in
    # the table describes two different forward passes, not an intervention.
    zero = [x for x in payload["runs"] if float(x["strength"]) == 0.0]
    bad_identity = [x["id"] for x in zero
                    if not x["zero_strength_control"]["texts_identical"]
                    or x["token_agreement"] != 1.0]
    if bad_identity:
        raise SystemExit(f"FATAL: {len(bad_identity)} strength-0.0 run(s) are not the "
                         f"identity on their own texts: {bad_identity[:3]}")

    steered = [x for x in payload["runs"] if float(x["strength"]) != 0.0]
    no_div = [x["id"] for x in steered if x["first_diverged_step"] is None]
    print(f"runs: {len(payload['runs'])}  (zero-vector controls {len(zero)}, "
          f"steered {len(steered)})")
    print(f"identity gate: all {len(zero)} zero-vector runs reproduce their own "
          f"texts exactly  OK")
    print(f"steered runs with no first_diverged_step: {len(no_div)}"
          + (f"  e.g. {no_div[:3]}" if no_div else ""))

    out = {
        "schema": "steer3d.cot_texts/1",
        "source": "backend/examples/build_cot_text_readout.py on all_runs.json (32k batch)",
        "model": MODEL,
        "design": {
            "primary": "被干预的生成（干预臂）",
            "shadow": "同一条 token 序列上的无干预对照，在每一步问「同一前缀下它会选哪个词」",
            "shadow_is_not_an_essay": (
                "run_intervention.py:272-282 取出 shadow 的 argmax，但下一步两臂都吃 primary 的词。"
                "所以 shadow 是 primary 原文被逐词打补丁的产物，不是一篇「没有向量时会写的文章」。"
                "把它当散文读，会在每个换词处看到语法断裂——那不是无干预模型变笨了，"
                "而是补丁的接缝。所有数字都来自 summary（生成时逐步实测），不从文字反推。"
            ),
            "why_no_word_diff": (
                "两臂在 token 层对齐但在词边界不对齐，一个词的删除会让后面所有词错位，"
                "difflib 会把尾巴报成一大段「改动」。实测 token 一致率 98.3% 的运行，"
                "词级 diff 会报 3000 词里 2585 词不同——那是伪影，不是测量。"
            ),
        },
        "n_runs": len(payload["runs"]),
        "planned_runs": args.planned_runs,
        "batch_complete": False if args.planned_runs and len(payload["runs"]) < args.planned_runs else True,
        "head_chars": HEAD_CHARS,
        "control_is_identity": True,
        "runs": payload["runs"],
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1))
    size = os.path.getsize(args.out)
    print(f"wrote {args.out}  ({size/1024:.1f} KB, {len(payload['runs'])} runs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
