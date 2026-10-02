#!/usr/bin/env python3
"""Build the "what did the vector do to the chain of thought" payload.

The goal asked specifically about the effect of intervention on the chain of
thought, not just on hidden states. That measurement exists -- run_intervention.py
persists `primary_text` (steered) and `shadow_text` (unsteered, teacher-forced on
the same tokens), and analyse_cot_divergence.py reduces it -- but none of it
reached the page. The page's entire CoT surface was a raw text panel: here is the
reasoning, side by side, unremarked upon.

Why the shadow matters: because it is teacher-forced from the primary's own
tokens, a textual difference is not an artefact of the two streams having
wandered onto different sentences. It is the same prefix carrying a different
state.

Two things this deliberately refuses to claim:

  * "The answer never changed." True, and worthless as stated. Only a handful of
    runs produce a parseable final answer, and NONE of the 264 runs in the source
    families ever closed `</think>`. Every trace was truncated by the step budget
    -- 61 steps in one family, 1025 in the other -- so this dimension is mostly
    unmeasured, not measured-null. The payload carries the denominators so the
    page can say so out loud.
  * Self-check markers. Delta is near zero but the p-values are 0.16-0.33, which
    is "not distinguishable from zero at n=24", not "no effect". The page shows
    the p-value for exactly this reason.

Model attribution: only runs whose model is provable are shipped.
`replication_24problems_L20.log` records `model loaded: /tmp/qwen3/master` and
run_intervention.py's dataset default is `aime_qwen3_1p7b_16k_fp16`, so that
family is Qwen3-1.7B. The 1025-step family has no log and no model field, so it
is left in the repo and out of the bundle -- shipping it under a model label
nobody can check is the same mistake as a 0.6B view quoting 1.7B's numbers.

The control is built in and gated: every strength-0.0 cell must be the identity
on all five measured quantities. A zero vector through the same code path is the
harness; if it moved anything, every other number in the table is suspect.
"""

import collections
import json
import os
import sys
from statistics import median

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "backend", "examples", "output", "intervention")
DEST = os.path.join(ROOT, "frontend", "public", "latent", "data", "cot_effect.json")

SOURCE = "cot_divergence_summary.json"
MODEL = "Qwen3-1.7B"
MODEL_PROVENANCE = ("replication_24problems_L20.log 记录 model loaded: /tmp/qwen3/master；"
                    "run_intervention.py 的数据集默认值为 aime_qwen3_1p7b_16k_fp16")

# The five quantities the control must reproduce exactly. `token_agreement` and
# `verbatim_step_overlap` are fractions of 1 when the two texts are the same
# text; `reason_len_ratio` is 1; the self-check delta is 0; the answer is
# unchanged. `mean_logit_kl` is included because a non-zero KL at strength 0
# would mean the two runs are not the same forward pass at all.
IDENTITY = {
    "mean_token_agreement": 1.0,
    "mean_logit_kl": 0.0,
    "mean_reason_len_ratio": 1.0,
    "mean_selfcheck_delta": 0.0,
    "mean_verbatim_overlap": 1.0,
}


def r4(x, nd=4):
    return None if x is None else round(float(x), nd)


def main():
    # CLI overrides so the same reducer can build more than one experiment.
    # The shipped cot_effect.json is the 60-step family; the 32k-budget family
    # is a *different* experiment and must not overwrite it — it lands in its
    # own file and the page shows it as a separate block.
    global SRC, DEST, SOURCE, MODEL, MODEL_PROVENANCE
    if len(sys.argv) > 1:
        import argparse
        ap = argparse.ArgumentParser(description="Build the CoT-effect payload.")
        ap.add_argument("--src", default=SRC, help="directory holding the divergence summary")
        ap.add_argument("--source", default=SOURCE, help="summary filename")
        ap.add_argument("--dest", default=DEST, help="output payload path")
        ap.add_argument("--model", default=MODEL)
        ap.add_argument("--model-provenance", default=MODEL_PROVENANCE)
        ap.add_argument("--steps-per-run", type=int, default=1025)
        ap.add_argument("--truncated", type=int, default=1)
        a = ap.parse_args()
        SRC, DEST, SOURCE = a.src, a.dest, a.source
        MODEL, MODEL_PROVENANCE = a.model, a.model_provenance
        STEPS_PER_RUN, TRUNCATED = a.steps_per_run, a.truncated

    src_path = os.path.join(SRC, SOURCE)
    if not os.path.exists(src_path):
        raise SystemExit("缺 %s" % src_path)
    d = json.load(open(src_path))
    runs = d["per_run"]

    # --- the control gate ---------------------------------------------------
    ctrl = [c for c in d["per_condition"] if c["strength"] == 0.0]
    if not ctrl:
        raise SystemExit("没有 strength=0.0 的对照臂，整张表无法解读")
    for c in ctrl:
        for k, want in IDENTITY.items():
            got = c.get(k)
            if got is None or abs(float(got) - want) > 1e-9:
                raise SystemExit(
                    "对照臂 %s@%s 的 %s = %r，不是 %r。零向量不该产生任何效应，"
                    "说明采集链路本身有偏，表里其它数字全部不可信。"
                    % (c["direction"], c["strength"], k, got, want))
    print("对照臂 %d 个条件全部逐项恒等（零向量无效应）" % len(ctrl))

    # --- free-run length ratio ---------------------------------------------
    # primary length vs the strength-0.0 arm of the SAME problem and
    # direction. `reason_len_ratio` compares against the teacher-forced
    # shadow, which is pinned to the primary's token sequence and is
    # therefore ~1 no matter what the intervention does — it cannot
    # detect rambling. These are the numbers that can.
    ctrl_chars = {}
    for r in runs:
        if r["strength"] == 0.0:
            ctrl_chars[(r["label"], r["direction"])] = r["reason_chars_primary"]
    fr, fr_closed = {}, {}
    for i, r in enumerate(runs):
        base = ctrl_chars.get((r["label"], r["direction"]))
        if r["strength"] == 0.0 or not base:
            continue
        ratio = r["reason_chars_primary"] / float(base)
        fr[i] = ratio
        fr_closed.setdefault(r["closed_think"], []).append(ratio)

    # --- per-condition rows -------------------------------------------------
    rows = []
    for c in d["per_condition"]:
        if c["strength"] == 0.0:
            continue
        sub = [r for r in runs
               if r["direction"] == c["direction"] and r["strength"] == c["strength"]]
        idx = [i for i, r in enumerate(runs)
               if r["direction"] == c["direction"] and r["strength"] == c["strength"]]
        # The denominators that decide which claims are allowed.
        n_known = sum(1 for r in sub if r["answer_known"])
        n_closed = sum(1 for r in sub if r["closed_think"])
        ctrl_row = next(x for x in ctrl if x["direction"] == c["direction"])
        rows.append({
            "direction": c["direction"],
            "strength": c["strength"],
            "n": c["n"],
            "n_runs_scanned": len(sub),
            "token_agreement": r4(c["mean_token_agreement"]),
            "logit_kl": c["mean_logit_kl"],
            "reason_len_ratio": r4(c["mean_reason_len_ratio"]),
            "selfcheck_delta": r4(c["mean_selfcheck_delta"], 3),
            "selfcheck_p": r4(c["selfcheck_p"], 3),
            "selfcheck_n": c["selfcheck_n"],
            "verbatim_overlap": r4(c["mean_verbatim_overlap"], 3),
            "answer_known": n_known,
            "answer_changed": sum(1 for r in sub if r["answer_changed"]),
            "closed_think": n_closed,
            "steps": sub[0]["n_steps"] if sub else None,
            # `reason_len_ratio` above is primary-vs-SHADOW. The shadow is
            # teacher-forced on the primary's own tokens, so that ratio is ~1
            # by construction and says nothing about rambling. The free-run
            # ratio below is primary-vs-the-zero-vector-arm-of-the-same
            # problem: both are free generations, so it is the only length
            # comparison on this page that can move.
            "free_len_ratio_median": r4(median([fr[i] for i in idx if i in fr]), 3),
            "free_len_ratio_min": r4(min([fr[i] for i in idx if i in fr]), 3) if any(i in fr for i in idx) else None,
            "free_len_ratio_max": r4(max([fr[i] for i in idx if i in fr]), 3) if any(i in fr for i in idx) else None,
            "control": {
                "token_agreement": r4(ctrl_row["mean_token_agreement"]),
                "reason_len_ratio": r4(ctrl_row["mean_reason_len_ratio"]),
                "selfcheck_delta": r4(ctrl_row["mean_selfcheck_delta"], 3),
                "verbatim_overlap": r4(ctrl_row["mean_verbatim_overlap"], 3),
            },
        })
    rows.sort(key=lambda x: (x["direction"], x["strength"]))

    tot_known = sum(r["answer_known"] for r in runs)
    tot_closed = sum(1 for r in runs if r["closed_think"])
    out = {
        "schema": "steer3d.cot_effect/1",
        "source": "backend/examples/analyse_cot_divergence.py on " + SOURCE,
        "model": MODEL,
        "model_provenance": MODEL_PROVENANCE,
        "design": ("primary = 被干预的生成；shadow = 同一条 token 序列上的无干预对照"
                   "（teacher-forced），因此两段文字的差异来自同一个前缀带着不同的状态，"
                   "而不是两条流走到了不同句子。strength=0.0 是同一条代码路径喂零向量，"
                   "它给出的一切都算在采集头上。"),
        "n_runs": len(runs),
        "n_problems": len(set(r["label"] for r in runs)),
        "layer": sorted(set(r["layer"] for r in runs))[0],
        # Steps actually taken vary run to run once the budget stops binding,
        # so report the distribution rather than sorted(set(...))[0] — on the
        # 32k family that would have printed the *shortest* run (1406) as if
        # it were the budget every run got.
        "steps_per_run": sorted(set(r["n_steps"] for r in runs))[0],
        "steps_median": sorted(r["n_steps"] for r in runs)[len(runs) // 2],
        "steps_max": max(r["n_steps"] for r in runs),
        "runs_at_budget": sum(1 for r in runs if r["n_steps"] >= max(r["n_steps"] for r in runs) - 100),
        "truncated": tot_closed == 0,
        "coverage": {
            "runs": len(runs),
            "answer_known": tot_known,
            "answer_known_frac": r4(tot_known / float(len(runs)), 3),
            "closed_think": tot_closed,
            "closed_think_frac": r4(tot_closed / float(len(runs)), 3),
        },
        "control_is_identity": True,
        "directions": sorted(set(r["direction"] for r in rows)),
        # 按「跑没跑完 </think>」把自由生成长度比分开。合在一起看中位数会
        # 把两种相反的行为平均掉：confidence_up@0.2 在闭合的 5 次里比对照臂
        # 短（0.78×），在没闭合的 13 次里长 2.89×，合起来看不出任何东西。
        "free_run_len_by_closure": {
            ("closed" if k else "open"): {
                "n": len(v),
                "median": r4(median(v), 3),
                "min": r4(min(v), 3),
                "max": r4(max(v), 3),
            } for k, v in sorted(fr_closed.items(), key=lambda kv: str(kv[0]))
        },
        "rows": rows,
    }
    with open(DEST, "w") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print("写出 %s  %d 条条件  %d 次运行  答案可解析 %d/%d  跑完</think> %d"
          % (os.path.relpath(DEST, ROOT), len(rows), len(runs), tot_known, len(runs), tot_closed))
    for r in rows:
        print("  %-18s s=%-5s n=%-3d tok=%.4f 逐字=%.3f 长度比=%.4f 自我检查Δ=%+.3f(p=%.3f) 答案 %d/%d"
              % (r["direction"], r["strength"], r["n"], r["token_agreement"],
                 r["verbatim_overlap"], r["reason_len_ratio"], r["selfcheck_delta"],
                 r["selfcheck_p"], r["answer_changed"], r["answer_known"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
