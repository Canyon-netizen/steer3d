"""基线 marker 读数：每条轨迹跑**一次**无注入前向，取该轨迹全部位点的基线。

## 为什么这么便宜（修订 19 §19.1）

基线 `marker logsumexp` 只依赖 `(轨迹, 位置)`，**与 `w` 和剂量都无关**。
494 个位点分布在 10 条轨迹上 ⇒ **10 次前向**即可，
不需要重跑 494 × 3 × 2 次注入前向。

## 它要回答什么

修订 16 观察到「think 上 `w·ĥ>0` 的位点 20/20 全负」，
但没区分这是**天花板效应**（该处本来就快写出 marker 了）
还是**符号错误**（注入真的把模型推离 marker）。
基线读数把这两者分开：S1 判相关、S2 判分组、S3 判哪个量解释力更强。

## 坐标系（踩过三次，照抄不改）

- `ids = pid + gen`，注入/读数的位置是 `P + t - 1`（`t` 是生成段内的 0-based 下标）
- ⚠ **基线只读 logits，不注入**，所以这里**不涉及层坐标**，
  但仍要用 sidecar 的 `prompt_tokens` 算对位置 —— 错一格就全错。
- marker 位点取 `MARKER_IDS`（从 `r6_rerun` import，**不复制常量**）

## 判据在修订 19 §19.2，取数前已写死；本脚本只测不判。
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
import r6_rerun as R6  # noqa: E402

MARKER_IDS = R6.MARKER_IDS
CONTROL_ID = R6.CONTROL_ID
MODEL = "/home/zhourui/.cache/huggingface/models/Qwen--Qwen3-1.7B/snapshots/master"


def lse(v):
    v = np.asarray(v, dtype=np.float64)
    m = float(v.max())
    return m + float(np.log(np.exp(v - m).sum()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sidecar-dir", required=True)
    ap.add_argument("--traj-json", required=True,
                    help="orthogonality_nt8.json —— 取它跑过的那些轨迹与位点")
    ap.add_argument("--out", required=True)
    ap.add_argument("--gpu-uuid", default=None)
    a = ap.parse_args()

    if a.gpu_uuid:
        os.environ["CUDA_VISIBLE_DEVICES"] = f"GPU-{a.gpu_uuid}"
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL, dtype=torch.bfloat16).to("cuda:0").eval()
    torch.set_grad_enabled(False)

    src = json.loads(Path(a.traj_json).read_text(encoding="utf-8"))
    # ⚠ 位点必须用**被测产物里的那批**，不能自己重新挑
    want = {}
    for r in src["rows"]:
        want.setdefault(r["traj"], []).append(r["t"])
    order = src["traj"]
    print(f"待测 {len(order)} 条轨迹，{sum(len(v) for v in want.values())} 个位点"
          f"（位点来自 {a.traj_json}，**不重新挑**）")

    mk = torch.tensor(MARKER_IDS, device="cuda:0")
    ctl = torch.tensor([CONTROL_ID], device="cuda:0")

    rows = []
    for tid in order:
        cti = json.load(open(
            Path(a.sidecar_dir) / f"{tid}.json", encoding="utf-8"))
        toks = cti.get("tokens") or []
        assert toks, f"{tid} 侧车没有 tokens，坐标系无法确定"
        gen = [t["token_id"] for t in toks]
        pid = tok(cti["chat_template_input"], return_tensors="pt",
                  add_special_tokens=False).input_ids[0].tolist()
        P = (cti.get("extra") or {}).get("prompt_tokens")
        ids = torch.tensor(pid + gen, dtype=torch.long, device="cuda:0")
        # ⚠ 一次前向拿全部位置的 logits（不用 cache，逐位置取）
        out = model(input_ids=ids.view(1, -1), use_cache=False, return_dict=True)
        logits = out.logits[0].float().cpu().numpy()
        mode = cti["config"]["mode"]

        for t in want[tid]:
            # ⚠ 位置必须是 `P + t - 1`：生成段内第 t 个 token（0-based）的前一位
            pos = P + t - 1
            assert 0 <= pos < logits.shape[0], (tid, t, pos, logits.shape)
            lg = logits[pos]
            real = gen[t]
            rows.append({
                "traj": tid, "mode": mode, "t": t,
                "pos": pos,
                "real_tok": real,
                "base_marker_lse": round(lse(lg[MARKER_IDS]), 4),
                "base_real_logit": round(float(lg[real]), 4),
                "base_marker_max": round(float(lg[MARKER_IDS].max()), 4),
                "base_control_lse": round(lse(lg[CONTROL_ID]), 4),
                "top1_tok": int(lg.argmax()),
                "real_is_top1": bool(int(lg.argmax()) == real),
            })
        print(f"  {tid:<32} mode={mode:<9} 位点 {len(want[tid]):>3} 个，已读基线")

    out = {"schema": "baseline_marker_probe/1",
           "prereg": "R6_RERUN_PREREG.md 修订 19",
           "src": a.traj_json, "traj": order,
           "marker_ids": MARKER_IDS, "control_id": CONTROL_ID,
           "rows": rows}
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1),
                           encoding="utf-8")
    print(f"写出 {a.out}（{len(rows)} 个位点的基线读数）")


if __name__ == "__main__":
    main()