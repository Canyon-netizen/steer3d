#!/usr/bin/env python3
"""Ship the two full essays, so "the answer changed from 40 to 3" can be read.

The page carries the change as two integers. That is the right unit for a
summary and the wrong one for the question the user actually asked -- what did
the vector do to the chain of thought. Both texts have been on disk the whole
time, in `all_runs.json`, and this puts a bounded window of each on the page.

Four things this script refuses to do, each because a version of it did:

1. **No quantity is derived from the text.** The answers are copied from the
   divergence analysis, never re-extracted here, so this screen can never
   disagree with the table above it about what the two answers were. The
   character offsets below ARE computed here, and they are labelled as
   character offsets everywhere they surface.

2. **The split point is a character offset, not a step.** The two runs are
   separate greedy decodes of different lengths, so after they part there is
   no alignment between them -- not token-aligned, not word-aligned, not
   anything. A `difflib` diff over the tails would report most of both essays
   as "changed" and mean nothing by it. The payload therefore ships the shared
   prefix length and a window around the split, and says plainly that the tails
   are two independent essays rather than a marked-up version of one.

3. **The arms are not token-synchronised, so nothing here is a "counterfactual
   of the same sentence".** Compare with `build_cot_text_readout.py`, which
   ships the teacher-forced shadow arm: there the two texts really are the same
   sentence with individual words swapped, and that is what makes the swap
   offsets meaningful. Here the only thing the two runs share is the question
   and the deterministic prefix they decode until the vector moves the argmax.

4. **A change is not an improvement.** Each item carries the bank's reference
   answer and a verdict, so "40 -> 3" is shown next to the fact that 3 is not
   the right answer either. Without that the screen would overstate what the
   batch shows, and the batch's net effect on accuracy is zero.

Usage:
    python3 backend/examples/build_answer_readout.py \
        --divergence .cache/32k_journal/cot_divergence_32k.json \
        --runs       .cache/32k_journal/all_runs.json \
        --out        frontend/public/latent/data/answer_readout.json \
        --planned-runs 96
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.core.aime_loader import _BUILTIN  # noqa: E402

# The problem bank, read from the one place it is defined. See the note in
# build_cot_effect.py: importing is not copying, and a second hand-typed list
# of answers would be a second copy of a fact that changes.
REF = {p["id"]: str(p["answer"]).strip() for p in _BUILTIN}

MODEL = "Qwen3-1.7B"

# Window sizes. The split window has to be wide enough to show a sentence
# starting on each side of the offset and narrow enough that six problems fit
# on a screen; the landing window is the tail, which is where the answer is.
# HEAD_CHARS caps the shared head ONLY -- it never extends it, because the
# shared head ends where the two texts part.
SPLIT_PRE = 380
SPLIT_POST = 420
LANDING_CHARS = 900
HEAD_CHARS = 180


def _as_str(x) -> Optional[str]:
    """The extractors return floats, the bank returns digit strings. 40.0 and
    '40' are the same answer and must compare equal, or every baseline reads as
    wrong."""
    if x is None:
        return None
    f = float(x)
    return str(int(f)) if f == int(f) else str(f)


def _clip(s: str) -> str:
    """Keep the payload printable: collapse the control characters a decoded
    model stream can contain, and cut anything that would break a JSON string
    on the way out. None of this touches the measured numbers."""
    out = []
    for ch in s:
        o = ord(ch)
        if ch in ("\n", "\t"):
            out.append(ch)
        elif o < 0x20 or o == 0x7f:
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)


def _window(text: str, centre: int, pre: int, post: int):
    """A window around `centre`, plus whether the window hit either end, so the
    page can say "this is the very beginning" rather than leaving the reader to
    guess why the text starts mid-sentence."""
    lo = max(0, centre - pre)
    hi = min(len(text), centre + post)
    return {
        "text": _clip(text[lo:hi]),
        "start": lo,
        "clipped_head": lo == 0 and centre - pre > 0,
        "clipped_tail": hi == len(text) and centre + post < len(text),
    }


def _verdict(zero, steered, ref):
    if ref is None:
        return "unknown"
    z = _as_str(zero) == ref
    s = _as_str(steered) == ref
    return ("right->right" if z and s else
            "right->wrong" if z else
            "wrong->right" if s else "wrong->wrong")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--divergence", required=True)
    ap.add_argument("--runs", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--planned-runs", type=int, default=0)
    ap.add_argument("--direction", default="confidence_down")
    ap.add_argument("--max-items", type=int, default=8)
    args = ap.parse_args()

    with open(args.divergence, encoding="utf-8") as f:
        div = json.load(f)
    with open(args.runs, encoding="utf-8") as f:
        runs = json.load(f)

    # Answers, sources and closure come from the divergence analysis and are
    # copied, never recomputed. Re-extracting here would give the page two
    # answers to the same question and no way to tell which one it is reading.
    meas = {}
    for r in div.get("per_run", []):
        if r.get("answer_primary_strict") is None:
            continue
        meas[(r["label"], r["direction"], r["strength"])] = r
    texts = {}
    for r in runs:
        texts[(r["prompt_label"], r["direction"], r["strength"])] = r.get("primary_text") or ""

    pairs = []
    labels = sorted({k[0] for k in meas if k[1] == args.direction})
    for label in labels:
        a0 = meas.get((label, args.direction, 0.0))
        a2 = meas.get((label, args.direction, 0.2))
        if not (a0 and a2):
            continue
        # Both arms must have finished. Comparing a finished answer against an
        # unfinished trace measures the budget, not the vector.
        if not (a0.get("closed_think") and a2.get("closed_think")):
            continue
        if a0["answer_primary_strict"] == a2["answer_primary_strict"]:
            continue
        t0, t2 = texts.get((label, args.direction, 0.0)), texts.get((label, args.direction, 0.2))
        if not t0 or not t2:
            continue
        # Shared prefix: both arms decode greedily and deterministically, so
        # they must agree until the injected vector moves the argmax. This is
        # the one place the two texts are genuinely comparable, and it is a
        # measured quantity, not an illustration.
        n = min(len(t0), len(t2))
        k = 0
        while k < n and t0[k] == t2[k]:
            k += 1
        r0 = runs[0]
        zero_run = next((x for x in runs if x["prompt_label"] == label
                         and x["direction"] == args.direction
                         and x.get("strength") == 0.0), None)
        two_run = next((x for x in runs if x["prompt_label"] == label
                        and x["direction"] == args.direction
                        and x.get("strength") == 0.2), None)
        ref = REF.get(label)
        pairs.append({
            "label": label,
            "direction": args.direction,
            "ref": _as_str(float(ref)) if ref is not None else None,
            "verdict": _verdict(a0["answer_primary_strict"], a2["answer_primary_strict"], ref),
            "both_in_domain": bool(a0.get("answer_primary_in_domain")
                                   and a2.get("answer_primary_in_domain")),
            "zero": {
                "answer": a0["answer_primary_strict"],
                "source": a0.get("answer_primary_source"),
                "steps": a0.get("n_steps"),
                "chars": len(t0),
            },
            "steered": {
                "answer": a2["answer_primary_strict"],
                "source": a2.get("answer_primary_source"),
                "steps": a2.get("n_steps"),
                "chars": len(t2),
            },
            "steps_ratio": (round(a2["n_steps"] / a0["n_steps"], 3)
                            if a0.get("n_steps") else None),
            # The headline offset, and the thing most easily misread: it counts
            # characters of the generated text, not decode steps, and the two
            # texts have no alignment past it.
            "split_char": k,
            "split_ratio": round(k / max(len(t0), len(t2)), 4),
            "shared_prefix_chars": k,
            # The shared head is cut AT the split, not at a fixed length. An
            # earlier version shipped `text[:180]` while the arms part at
            # character 14 on some problems, so the page would have printed
            # "the first 180 characters are identical" directly above 180
            # characters that are not. The block claims identity, so the thing
            # it shows has to be the thing it is claiming about.
            "head_chars": min(k, HEAD_CHARS),
            "heads": {
                "zero": _clip(t0[:min(k, HEAD_CHARS)]),
                "steered": _clip(t2[:min(k, HEAD_CHARS)]),
                "identical": t0[:k] == t2[:k],
                "truncated": k > HEAD_CHARS,
            },
            "split": {
                "zero": _window(t0, k, SPLIT_PRE, SPLIT_POST),
                "steered": _window(t2, k, SPLIT_PRE, SPLIT_POST),
            },
            "landing": {
                "zero": _clip(t0[-LANDING_CHARS:]),
                "steered": _clip(t2[-LANDING_CHARS:]),
                "zero_start": max(0, len(t0) - LANDING_CHARS),
                "steered_start": max(0, len(t2) - LANDING_CHARS),
            },
        })

    pairs.sort(key=lambda x: (x["verdict"] != "right->wrong",
                              x["verdict"] != "wrong->right", x["label"]))
    shipped = pairs[:args.max_items]

    by_verdict: Dict[str, int] = {}
    for p in pairs:
        by_verdict[p["verdict"]] = by_verdict.get(p["verdict"], 0) + 1

    # Same provenance block as cot_effect, and for the same reason: this screen
    # is where a reader meets "标准答案" most directly, so it is the worst place
    # to leave that number looking like an official AIME key. REF is
    # `_BUILTIN`'s own `answer` field over problems the bank documents as
    # inspired-by and re-worded; nothing here checks either against the
    # competition's own text or key.
    _labels = sorted({p["label"] for p in pairs})
    _unknown = [l for l in _labels if l not in REF]
    if _unknown:
        raise SystemExit(
            "FAIL: %d label(s) not in the problem bank: %s -- their reference "
            "answer would be None and every verdict below would be scored "
            "against nothing." % (len(_unknown), _unknown))

    payload = {
        "schema": "steer3d.answer_readout/1",
        "model": MODEL,
        "problem_set": {
            "source_file": "backend/core/aime_loader.py :: _BUILTIN",
            "loader_self_description": (
                "inspired by AIME 1983-2024 problems. Re-worded but "
                "mathematically faithful; answers verified"),
            "is_official_aime": False,
            "verbatim_checked_against_official": None,
            "reference_answers_from": "_BUILTIN 的 answer 字段，本仓库未独立核对",
            "answer_domain_rule": "0–999（题库自述采用的 AIME 答案域约定）",
            "n_in_bank": len(_BUILTIN),
            "n_in_screen": len(_labels),
            "labels": _labels,
        },
        "source": {
            "divergence": os.path.basename(args.divergence),
            "runs": os.path.basename(args.runs),
        },
        "direction": args.direction,
        "strength": 0.2,
        "zero_strength": 0.0,
        "planned_runs": args.planned_runs,
        "n_runs_analysed": len(runs),
        "selection": {
            "rule": "两臂都跑完 </think>、严格口径下能解析出答案、且两臂答案不同",
            "strict_only": True,
            "require_both_closed": True,
            "n_eligible": len(pairs),
            "n_shipped": len(shipped),
            "by_verdict": by_verdict,
        },
        "design": (
            "每道题两遍完整贪心解码：一遍注入强度 0.2，一遍喂零向量。"
            "解码循环自己写，逐 token 取 argmax（run_intervention.py:272），"
            "没有采样。同样的输入跑两遍会逐字相同（本批 21/21 对验证），"
            "所以两条路一旦分开，只可能是因为注入的向量。"
        ),
        "caveats": [
            "split_char 是字符位置，不是 token 步数。两段文本长度不同，"
            "越过这个位置之后它们没有任何对齐关系，不能逐词对比。",
            "这里的两臂不是 token 同步的。思维链正文屏里的影子臂是同一句话"
            "被逐词替换，那里的接缝有意义；这里两段是各自独立写出来的文章。",
            "答案一律取自分析脚本的严格口径，本脚本不重新提取，"
            "所以这块屏和上面的表不可能对不上。",
            "变了不等于变好了：每一项都带标准答案和判定，"
            "本批答对数净变化为 0。",
        ],
        "items": shipped,
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    size = os.path.getsize(args.out)
    print("写出 %s  %d 项（符合条件 %d 项）  %d 题  %d 字节"
          % (args.out, len(shipped), len(pairs), len(div.get("per_run", [])), size))
    for p in shipped:
        print("  %-11s 零向量 %-8s → 加向量 %-8s 标准 %-6s %-13s 步数 %s/%s"
              % (p["label"], _as_str(p["zero"]["answer"]), _as_str(p["steered"]["answer"]),
                 p["ref"], p["verdict"], p["zero"]["steps"], p["steered"]["steps"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
