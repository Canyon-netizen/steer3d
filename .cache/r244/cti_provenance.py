#!/usr/bin/env python
"""What exactly does recomp_p.py's 60/60 agreement prove?  Bound the claim.

recomp_p.py compares  sidecar extra.prompt_tokens  against
len(tokenizer(sidecar chat_template_input)).

Both sides consume the SAME stored string.  So a match proves the sidecar's
count is the correct encoding *of that string*.  It does NOT by itself prove
the string is the correctly templated prompt for the intended conversation.

This script separates the two:

  A. Does cti literally contain the system_prompt and the prompt text?
  B. Does cti equal tokenizer.apply_chat_template() on the obvious
     reconstruction from system_prompt + prompt?
  C. How do the token counts compare: cti vs prompt-only vs system-only?

Result shape decides the wording of the claim:
  - B matches          -> P is verified end to end for those sidecars
  - A holds, B differs -> P is verified only as "encoding of the stored
                          string"; the string itself is unverified
  - A fails            -> the stored string may not even be this
                          conversation; the claim is even weaker

Exit: 0 ran to completion (read the printed verdicts; this is a probe, not a
gate), 2 precondition failure.
"""
import json
import os
import sys
from glob import glob

MODEL = "/home/zhourui/.cache/huggingface/models/Qwen--Qwen3-1.7B/snapshots/master"
SIDECAR = "/home/zhourui/steer3d_bpath/gen_b2_max32768/aime"


def main():
    if not os.path.isdir(MODEL) or not os.path.isdir(SIDECAR):
        print("PRECOND_FAIL: model or sidecar dir missing")
        return 2

    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL)

    files = sorted(glob(os.path.join(SIDECAR, "*.json")))
    if not files:
        print("PRECOND_FAIL: no sidecar json")
        return 2

    n = len(files)
    c_contains_sys = 0
    c_contains_prompt = 0
    b_match = 0
    b_diff = 0
    b_detail = []

    for f in files:
        j = json.load(open(f, encoding="utf-8"))
        tid = j.get("trajectory_id") or os.path.basename(f)[:-5]
        cti = j.get("chat_template_input") or ""
        sysp = j.get("system_prompt") or ""
        pr = j.get("prompt") or ""

        has_sys = bool(sysp) and sysp in cti
        has_pr = bool(pr) and pr in cti
        c_contains_sys += int(has_sys)
        c_contains_prompt += int(has_pr)

        # B: rebuild the obvious conversation and apply the template.
        msgs = []
        if sysp:
            msgs.append({"role": "system", "content": sysp})
        if pr:
            msgs.append({"role": "user", "content": pr})
        try:
            rebuilt = tok.apply_chat_template(
                msgs, tokenize=False, add_generation_prompt=True)
        except Exception as exc:  # noqa: BLE001 - probe reports, does not raise
            b_detail.append("%s\tAPPLY_FAIL\t%s" % (tid, type(exc).__name__))
            b_diff += 1
            continue

        same = (rebuilt == cti)
        if same:
            b_match += 1
        else:
            b_diff += 1
            n_tok_cti = len(tok(cti, add_special_tokens=False).input_ids)
            n_tok_rb = len(tok(rebuilt, add_special_tokens=False).input_ids)
            b_detail.append("%s\tDIFF\tcti_tok=%d\trebuilt_tok=%d\tsame_prefix=%s"
                            % (tid, n_tok_cti, n_tok_rb,
                               str(cti.startswith(rebuilt[:80]))))

    print("sidecars=%d" % n)
    print("A_contains_system_prompt=%d/%d" % (c_contains_sys, n))
    print("A_contains_prompt=%d/%d" % (c_contains_prompt, n))
    print("B_apply_chat_template_identical=%d" % b_match)
    print("B_apply_chat_template_differs=%d" % b_diff)
    print("--- B details (first 8) ---")
    for s in b_detail[:8]:
        print(s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
