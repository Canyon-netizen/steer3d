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
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
SRC = os.path.join(ROOT, "backend", "examples", "output", "intervention")
DEST = os.path.join(ROOT, "frontend", "public", "latent", "data", "cot_effect.json")

# The problem bank, read from the one place it is defined. A second hand-typed
# list of labels or answers would be a second copy of a fact that changes when
# the bank changes, and nothing would notice -- the same failure as the two
# copies of the verifier prompt. Importing is not copying.
from backend.core.aime_loader import _BUILTIN  # noqa: E402

# id -> reference answer, as a string. The bank stores strings and the
# extractors return floats, so a direct comparison would score every baseline
# wrong. Normalise once, here.
REF = {p["id"]: str(p["answer"]).strip() for p in _BUILTIN}


def _as_answer_str(x):
    """The extractors return floats; the bank returns digit strings.

    40.0 and '40' are the same answer and must compare equal, or every
    baseline reads as wrong and the accuracy counts below are all zeroes.
    """
    if x is None:
        return None
    if float(x) == int(float(x)):
        return str(int(float(x)))
    return str(x)

SOURCE = "cot_divergence_summary.json"
MODEL = "Qwen3-1.7B"
MODEL_PROVENANCE = ("replication_24problems_L20.log 记录 model loaded: /tmp/qwen3/master；"
                    "run_intervention.py 的数据集默认值为 aime_qwen3_1p7b_16k_fp16")

# Planned size of the batch, 0 when unknown. See --planned-runs.
PLANNED_RUNS = 0

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
    global SRC, DEST, SOURCE, MODEL, MODEL_PROVENANCE, PLANNED_RUNS
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
        # How many runs this batch was *planned* to produce, as distinct from
        # how many have landed. The 32k family is a live batch: 24 problems x 4
        # directions = 96, and the payload gets rebuilt as shards finish. A
        # page that says "72 runs" without this invites the reader to treat a
        # partial count as a final one -- and the conclusion it carries is a
        # *negative* one ("the answers did not change"), which is exactly the
        # kind of claim a later batch can overturn. 0 means "not stated".
        ap.add_argument("--planned-runs", type=int, default=0)
        a = ap.parse_args()
        SRC, DEST, SOURCE = a.src, a.dest, a.source
        MODEL, MODEL_PROVENANCE = a.model, a.model_provenance
        STEPS_PER_RUN, TRUNCATED = a.steps_per_run, a.truncated
        PLANNED_RUNS = a.planned_runs

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

    # --- 归因闸门：同题两个零向量运行必须逐字相同 --------------------------
    # The answer-shift measurement below compares a free run with the vector
    # against a free run with a zero vector. Those two differ by the vector and
    # by nothing else -- unless the forward pass is not reproducible, in which
    # case a 32k-token generation's worth of accumulated float drift could
    # flip a token somewhere and the whole comparison is measuring the GPU.
    #
    # The check is free: at strength 0.0 the injected vector is multiplied by
    # zero, so `confidence_up@0.0` and `confidence_down@0.0` of the SAME problem
    # are the same computation under two labels, and the harness runs them
    # back to back in one process. Measured on the current batch, 21/21 such
    # pairs are character-for-character identical, including the three that ran
    # the full 32000 steps. A non-zero count here would invalidate the
    # comparison outright, so it is a gate and not a statistic.
    det = []
    bylabel = {}
    for r in runs:
        if r["strength"] == 0.0:
            bylabel.setdefault(r["label"], {})[r["direction"]] = r
    for label, m in sorted(bylabel.items()):
        if "confidence_up" in m and "confidence_down" in m:
            a, b = m["confidence_up"], m["confidence_down"]
            det.append({"label": label,
                        "identical": a["reason_text_digest"] == b["reason_text_digest"],
                        "steps": a["n_steps"]})
    # How much generation separates the two runs. The loop in
    # run_intervention.py is `for direction: for strength:`, so the two
    # zero-vector runs of one problem are NOT adjacent -- a full generation of
    # the other direction sits between them. That distance is what makes this
    # a real bound on accumulated float drift rather than a restatement of
    # "the same call twice"; it is measured per problem, not assumed.
    # The intervening run is `confidence_up @ 0.2`, which is NOT in `bylabel`
    # -- that dict holds the strength-0.0 runs only. Reading the zero-vector
    # run's own length instead reported a median of 7818 where the truth is
    # 32000, i.e. the separation was understated by four-fold.
    steps_all = {(r["label"], r["direction"], r["strength"]): r.get("n_steps")
                 for r in runs}
    for label in list(bylabel):
        # NOT `d` -- that name is the loaded payload two scopes up, and
        # shadowing it made every later `d["per_condition"]` a KeyError.
        rec = next((x for x in det if x["label"] == label), None)
        if rec is None:
            continue
        rec["intervening_steps"] = steps_all.get((label, "confidence_up", 0.2))
    seps = sorted((d.get("intervening_steps") or 0) for d in det)
    n_same = sum(1 for d in det if d["identical"])
    print("归因闸门：同题两个零向量运行逐字相同 %d/%d" % (n_same, len(det)))
    if len(det) < 5:
        raise SystemExit("零向量同题配对只有 %d 对，不足以支撑任何跨运行的归因。" % len(det))
    if n_same != len(det):
        bad = [d["label"] for d in det if not d["identical"]]
        raise SystemExit(
            "FATAL：同题两个零向量运行正文不同：%s。前向不可复现，"
            "「加向量 vs 零向量」的差异不能归给向量，answer_shift_free_run 不可用。" % bad)

    # --- 答案有没有变：自由生成 vs 零向量对照 -------------------------------
    # The per-row `answer_changed` counts primary-vs-shadow INSIDE one run, and
    # the shadow is teacher-forced on the primary's own tokens. That is the
    # right comparison for "at this step, what would it have picked" and it is
    # almost always a tie, because by construction the two arms agree on every
    # step that matters for the final token. It is NOT the comparison a reader
    # means by "did the vector change the answer", which is:
    #
    #     the freely generated answer with the vector
    #   vs
    #     the freely generated answer with a zero vector, same question
    #
    # Both are greedy decodes, so the only thing that differs is the injected
    # vector -- and the identity gate above already proved the forward pass is
    # reproducible (42/42 zero-vector runs reproduce their own texts exactly,
    # which is two independent forward passes agreeing token for token over
    # ~32k steps). This is therefore a real, attributable comparison, and it
    # does not agree with the within-run one.
    # STRICT answers only. The cascade's tail-integer fallback invents an
    # answer out of an unfinished trace, and pairing one invented answer with
    # one real one reports a change that did not happen -- which is exactly the
    # failure this measurement exists to detect, so contaminating it with a
    # known-bad extractor would be self-defeating.
    # --- Gate 2: no duplicated (problem, direction, strength) cell ---------
    # `ans_by.setdefault(...)[strength] = ...` overwrites, and `n_runs` counts
    # every record, so a shard that re-ran one problem would both double-weight
    # that problem in the change rate and report a run count that no single
    # experiment produced. Nothing downstream would notice. The current batch is
    # clean (84 records, 84 distinct cells, 42 problem-direction pairs each with
    # exactly the two swept strengths); this is here so the next shard cannot
    # make it dirty silently.
    seen = collections.Counter((r["label"], r["direction"], r["strength"])
                               for r in runs)
    dupes = {k: v for k, v in seen.items() if v > 1}
    per_cell = collections.Counter((r["label"], r["direction"]) for r in runs)
    # The expected count per (problem, direction) is the MODE, not the minimum.
    # Taking `sorted(...)[0]` made a batch with 41 pairs at 2 runs and 1 pair at
    # 1 run declare the expected value to be 1, so the message named all 41
    # normal pairs as anomalous and never mentioned the one that was actually
    # missing an arm. The gate still refused, but it refused while pointing at
    # the wrong thing, which is the same as not refusing.
    if per_cell:
        want, want_n = per_cell.most_common(1)[0]
    else:
        want, want_n = None, 0
    print("重复检查  %d 次运行 / %d 个唯一单元%s；每 (题,方向) 应有 %s 次"
          % (len(runs), len(seen),
             "（无重复）" if not dupes else "，重复 %d 个" % len(dupes),
             want_n))
    if dupes:
        raise SystemExit(
            "同一 (题, 方向, 强度) 出现多次，例如 %s。"
            "某个 shard 重跑过题目；继续会把那一题双计，且 n_runs 会报出一个"
            "没有哪一次实验产生过的数字。" % list(dupes)[:3])
    if per_cell and any(v != want_n for v in per_cell.values()):
        # Report the odd ones, not the whole table. Dumping all 42 pairs made
        # the one line that matters -- the pair with a single run -- the
        # hardest thing in the message to find.
        odd = sorted(k for k, v in per_cell.items() if v != want_n)
        # k is a (label, direction) pair, so it fills TWO of the three slots in
        # the per-item format. A "%s/%s=%d" % k raises TypeError at format time
        # -- which is exactly why this gate gets exercised on purpose rather
        # than trusted to work.
        sample = ", ".join("%s/%s=%d" % (k[0], k[1], per_cell[k]) for k in odd[:4])
        raise SystemExit(
            "有 %d 个 (题, 方向) 的运行数不是 %d，例如 %s。"
            "有一道题少跑了某个强度，答案位移的比较会因为缺配对而少算一组，"
            "而 n_runs 仍会把缺的那次算进去。"
            % (len(odd), want_n, sample + (" ..." if len(odd) > 4 else "")))

    ans_by = {}
    for r in runs:
        if r.get("answer_primary_strict") is None:
            continue
        ans_by.setdefault((r["label"], r["direction"]), {})[r["strength"]] = {
            "answer": r["answer_primary_strict"], "closed": r["closed_think"],
            "in_domain": r.get("answer_primary_in_domain")}
    shift = {}
    for (label, direction), m in ans_by.items():
        if 0.0 not in m or 0.2 not in m:
            continue
        ref = REF.get(label)
        shift.setdefault(direction, []).append({
            "label": label,
            "zero": m[0.0]["answer"],
            "steered": m[0.2]["answer"],
            "both_closed": bool(m[0.0]["closed"] and m[0.2]["closed"]),
            "both_in_domain": bool(m[0.0]["in_domain"] and m[0.2]["in_domain"]),
            # "The answer changed" is not a finding on its own. A flip that
            # breaks a correct answer and a flip that fixes a wrong one are
            # opposite findings, and a reader who only sees 8/18 has no way to
            # tell which of the 8 they are looking at. The reference answer
            # comes from the problem bank, so the classification cannot drift
            # away from the questions that were actually asked.
            "ref": _as_answer_str(float(ref)) if ref is not None else None,
            "steps_zero": None, "steps_steered": None,
        })
        x = shift[direction][-1]
        for arm, st in (("zero", 0.0), ("steered", 0.2)):
            r = next((q for q in runs if q["label"] == label
                      and q["direction"] == direction and q.get("strength") == st), None)
            x["steps_" + arm] = (r or {}).get("n_steps")

    def _verdict(x):
        """right->wrong / wrong->right / right->right / wrong->wrong, or
        unknown when the bank has no reference for this label."""
        if x["ref"] is None:
            return "unknown"
        z_ok = _as_answer_str(x["zero"]) == x["ref"]
        s_ok = _as_answer_str(x["steered"]) == x["ref"]
        return ("right->right" if z_ok and s_ok else
                "right->wrong" if z_ok else
                "wrong->right" if s_ok else "wrong->wrong")

    answer_shift = {}
    for direction, g in shift.items():
        for x in g:
            x["verdict"] = _verdict(x)
        closed_g = [x for x in g if x["both_closed"]]
        verdicts = collections.Counter(x["verdict"] for x in closed_g)
        known = [x for x in closed_g if x["verdict"] != "unknown"]
        correct_zero = sum(1 for x in known if x["verdict"].split("->")[0] == "right")
        correct_steered = sum(1 for x in known if x["verdict"].split("->")[1] == "right")
        v = {k: verdicts.get(k, 0) for k in
             ("right->right", "right->wrong", "wrong->right", "wrong->wrong", "unknown")}
        # The same histogram restricted to the pairs whose answer actually
        # moved. The page needs this one: "wrong->wrong" above counts every
        # question both arms got wrong, including the ones both arms got wrong
        # the SAME way, so 6 changed-the-wrong-way cannot be recovered from it
        # by subtraction without also knowing how many stayed put.
        ch = collections.Counter(x["verdict"] for x in closed_g
                                 if x["zero"] != x["steered"])
        v_changed = {k: ch.get(k, 0) for k in v}
        # The two correctness counts are the same fact as the verdict
        # histogram, and a first version of this block got them wrong by
        # indexing the verdict STRING: "right->wrong"[-1] is 'g', not 'w' and
        # not a direction at all, so every steered answer scored as incorrect
        # and the page would have reported 4 -> 0. Nothing caught it because
        # the numbers were plausible. These two identities are what catch it.
        assert correct_zero == v["right->right"] + v["right->wrong"], (
            "%s: correct_zero disagrees with the verdict histogram" % direction)
        assert correct_steered == v["right->right"] + v["wrong->right"], (
            "%s: correct_steered disagrees with the verdict histogram" % direction)
        # And the changed-only histogram must account for exactly the changes.
        n_changed_closed = sum(1 for x in closed_g if x["zero"] != x["steered"])
        assert sum(v_changed.values()) == n_changed_closed, (
            "%s: changed-verdict histogram does not add up" % direction)
        answer_shift[direction] = {
            "comparable": len(g),
            "changed": sum(1 for x in g if x["zero"] != x["steered"]),
            "comparable_both_closed": len(closed_g),
            "changed_both_closed": sum(1 for x in closed_g if x["zero"] != x["steered"]),
            # Restricted to answers that are even in range: a run that boxed
            # 11,232,000 for an AIME question has left the domain entirely, and
            # counting it as "the vector changed the answer" measures the
            # derailment, not the vector.
            "comparable_in_domain": sum(1 for x in g if x["both_in_domain"]),
            "changed_in_domain": sum(1 for x in g
                                     if x["both_in_domain"] and x["zero"] != x["steered"]),
            "examples": [x for x in g if x["zero"] != x["steered"]][:6],
            # The other half of the question. A change rate on its own invites
            # the reader to score the intervention by how often it moved the
            # answer; these two numbers say what the moves were worth.
            "accuracy": {
                "n": len(known),
                "n_unknown": len(closed_g) - len(known),
                "correct_zero": correct_zero,
                "correct_steered": correct_steered,
                "verdicts": v,
                "verdicts_changed": v_changed,
            },
        }
        a = answer_shift[direction]
        a["accuracy"]["delta"] = (a["accuracy"]["correct_steered"]
                                  - a["accuracy"]["correct_zero"])
    for direction, a in answer_shift.items():
        print("自由生成答案  %-18s 可比 %2d 组，不同 %2d 组；两臂都写完的 %2d 组里 "
              "答对 %d -> %d（净 %+d）"
              % (direction, a["comparable"], a["changed"],
                 a["comparable_both_closed"], a["accuracy"]["correct_zero"],
                 a["accuracy"]["correct_steered"], a["accuracy"]["delta"]))

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
        # Planned total for this batch, or 0 when the caller does not state
        # one. The page turns this into "this is N of M, still growing".
        "planned_runs": PLANNED_RUNS,
        "planned_problems": PLANNED_RUNS // 4 if PLANNED_RUNS else 0,
        "batch_complete": bool(PLANNED_RUNS) and len(runs) >= PLANNED_RUNS,
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
        "determinism_gate": {
            "what": "同题 confidence_up@0.0 与 confidence_down@0.0 是同一个计算"
                    "（零向量乘任何方向仍是零），在同一次进程里先后完整生成，"
                    "正文必须逐字相同。",
            "pairs": len(det),
            "identical": n_same,
            "max_steps_compared": max((d["steps"] or 0) for d in det) if det else 0,
            "intervening_steps_median": seps[len(seps)//2] if seps else 0,
            "intervening_steps_max": seps[-1] if seps else 0,
            "pairs_separated_by_full_run": sum(1 for x in seps if x >= 32000),
            "loop_order_dependency":
                "这个论断依赖 run_intervention.py 的循环顺序是 "
                "`for direction: for strength:`，也就是同题执行顺序为 "
                "up@0.0 -> up@0.2 -> down@0.0 -> down@0.2，两个零向量运行之间"
                "隔着一次完整生成。改了循环顺序这句话就不成立了，"
                "verify_cot32k.mjs 会去 grep 那一行。",
            "why_it_matters": "它给出「一次完整生成的浮点累积会不会改变 token」"
                              "的答案。0 差异 ⇒ 自由生成答案位移不可能是 GPU 噪声。",
        },
        "answer_shift_free_run": {
            "what": ("自由生成：加向量的答案 vs 同题零向量对照的答案。"
                     "与 per-row 的 answer_changed 是**两个不同的比较**——"
                     "后者比的是同一次运行内 teacher-forced 的两臂，"
                     "按构造几乎总是打平；前者才是「加了这个向量，模型答得一样吗」。"),
            "why_trustworthy": (
                "两臂都是贪心解码，唯一差别是注入的向量；且 strength=0.0 的运行里"
                "两臂正文逐字完全相同（42/42），说明前向本身可复现，"
                "跨运行的差异不能归给随机性。"),
            "caveat": ("可比组只统计两臂都能解析出最终答案的那些题；"
                       "另外有一部分题两臂都没闭合 </think>，这些没有可比答案。"),
            "by_direction": answer_shift,
        },
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
