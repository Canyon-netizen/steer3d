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

    # --- per-condition rows -------------------------------------------------
    rows = []
    for c in d["per_condition"]:
        if c["strength"] == 0.0:
            continue
        sub = [r for r in runs
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
        "steps_per_run": sorted(set(r["n_steps"] for r in runs))[0],
        "truncated": tot_closed == 0,
        "coverage": {
            "runs": len(runs),
            "answer_known": tot_known,
            "answer_known_frac": r4(tot_known / float(len(runs)), 3),
            "closed_think": tot_closed,
        },
        "control_is_identity": True,
        "directions": sorted(set(r["direction"] for r in rows)),
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
