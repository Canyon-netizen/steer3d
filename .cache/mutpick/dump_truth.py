#!/usr/bin/env python3
"""从 npz 直读每条记录的前 N 个真实 token，作为判据的外部真值。

为什么要独立取一遍：判据要在浏览器里断言「页面显示的 token 属于
用户选的那条记录」。若判据自己也是从后端拿的，后端选错记录时两边
一起错，判据就恒绿。npz 是采集下来的原始数据，与页面、与后端的
选择逻辑都无关，所以它是唯一可信的对照。

写文件而不是直接 print：verify_picker.mjs 要读它。
"""
import json
import os
import sys

import numpy as np

REPO = "/Users/zhourui/code/steer3d"
sys.path.insert(0, REPO)

from backend.core.replay_runner import NpzReplayRunner  # noqa: E402

N_STEPS = 12
OUT = os.path.join(REPO, ".cache/mutpick/ground_tokens.json")


def main() -> None:
    runner = NpzReplayRunner()
    vocab = runner._vocab
    if not vocab:
        raise SystemExit("vocab.json missing -- cannot decode tokens honestly")
    out = {}
    for rec in runner.records:
        with np.load(rec["npz"], mmap_mode="r") as z:
            # Read the SAME field the runner reads. _Decoder.text() takes
            # tok_ids (z["token_ids"]), not the top-k argmax -- using
            # topk_indices[:, 0] instead is a different source and the
            # criterion would be comparing against a number the page never
            # had a chance to display.
            ids = z["token_ids"][:N_STEPS]
        out[rec["id"]] = [vocab[int(i)] for i in ids]
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False)
    print("wrote %d records -> %s" % (len(out), OUT))
    for rid in list(out)[:1] + [k for k in out if k.endswith("__think")][:1]:
        print("  %s -> %r" % (rid, "".join(out[rid])[:80]))


if __name__ == "__main__":
    main()
