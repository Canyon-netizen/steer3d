"""判决：backfill 的 verify 报 110% 相对差，是因为它**比对错开了一格的位置**吗？

## 背景

`backfill_prompt_hidden.py` 的 `--verify` 打印
  max|computed - stored| last_layer，相对差 ~1.10，然后照常写入。
两件事要分清：

  Q1 verify 比对的位置对不对？
     采集器逐 token 用 KV cache 生成，存的是**消费该 token 之前**的残差流；
     R-1 已实测 `npz 第 g 行 == 全序列第 (P+g-1) 位`。
     回填取 `hs_tuple[L][0, T_p:, :]` = 全序列第 P+g 位（**消费之后**）。
     ⇒ 两者差一格。若如此，把 computed 往前挪一格，差应当塌掉。

  Q2 prompt 块本身对不对？
     `p_hs[:, li-1, :] = hs_tuple[li][0, :T_p, :]` 取的是全序列 0..T_p-1，
     与存储无关，**本来就该对**。若 Q1 成立，prompt 块不需要动。

判决规则（取数前写死）：
  V1 若 shift=1 的相对差比 shift=0 小一个数量级以上 ⇒ 确认是错位，不是数值漂移
  V2 若 shift=1 仍然很大 ⇒ 另有原因，不能靠错位解释
  V3 两种情况下 prompt 块（位置 0..T_p-1）都单独报一个对照数
"""
from __future__ import annotations

import json
import os
import sys

os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
os.environ["CUDA_VISIBLE_DEVICES"] = "7"

import numpy as np
import torch

MODEL = "/home/zhourui/.cache/huggingface/models/Qwen--Qwen3-1.7B/snapshots/master"


def rel(a, b):
    return float(np.abs(a - b).max()) / (float(np.abs(b).max()) + 1e-9)


def main(root):
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16).to("cuda:0").eval()

    for jf in sorted(__import__("glob").glob(f"{root}/*.json")):
        meta = json.load(open(jf))
        npz = jf[:-5] + ".npz"
        with np.load(npz) as d:
            files = list(d.files)
            gen_ids = d["token_ids"]
            stored_lh = d["last_hidden"].astype(np.float32)
            stored_hs = d["hidden_states"]
            p_hs_exist = "prompt_hidden_states" in files

        chat = meta["chat_template_input"]
        prompt_ids = tok(chat, return_tensors="pt", add_special_tokens=False).input_ids[0].tolist()
        T_p, T_g = len(prompt_ids), len(gen_ids)
        full = torch.tensor([prompt_ids + list(gen_ids)], dtype=torch.long, device="cuda:0")
        with torch.no_grad():
            out = model(input_ids=full, attention_mask=torch.ones_like(full),
                        output_hidden_states=True, use_cache=False, return_dict=True)
        L = len(out.hidden_states) - 1
        final = out.hidden_states[L][0].to(torch.float32).cpu().numpy()   # (T_p+T_g, D)

        gen_post = final[T_p:]          # 消费之后  -> 全序列 P..P+T_g-1
        gen_pre = final[T_p - 1:T_p - 1 + T_g]   # 消费之前 -> 全序列 P-1..P+T_g-2

        print(f"\n=== {meta['trajectory_id']} ===")
        print(f"  T_p={T_p}  T_g={T_g}  stored_dtype={meta['extra'].get('stored_dtype')}")
        print(f"  collector extra.prompt_tokens = {meta['extra'].get('prompt_tokens')}"
              f"   回填重算 T_p = {T_p}"
              f"   -> {'一致' if meta['extra'].get('prompt_tokens') == T_p else '不一致 !!'}")
        r0, r1 = rel(gen_post, stored_lh), rel(gen_pre, stored_lh)
        print(f"  verify 现在的口径 (shift=0，消费后 vs 存储):  相对差 {r0:.4e}")
        print(f"  假设的错位口径 (shift=1，消费前 vs 存储):      相对差 {r1:.4e}")
        ratio = r0 / max(r1, 1e-30)
        v1 = ratio >= 10.0
        v2 = not v1
        print(f"  V1 差一个数量级以上？ {ratio:.1f}x -> {'PASS 确认是错位' if v1 else 'FAIL'}")
        print(f"  V2 仍很大？          -> {'是，另有原因' if v2 else '否'}")

        # V3：prompt 块自己的对照（位置 0..T_p-1），若已回填则与已存值比
        if p_hs_exist:
            with np.load(npz) as d:
                p_hs = d["prompt_hidden_states"]
            cur = final[:T_p]
            got = p_hs[:, -1, :].astype(np.float32)
            print(f"  V3 prompt 块 (末层) 与全序列 0..T_p-1 的相对差: {rel(cur, got):.4e}"
                  f"  shape {got.shape} dtype {p_hs.dtype}")
        else:
            print(f"  V3 prompt 块尚未回填")

        # 顺带：存储 hidden_states 的末层是否就是 last_hidden
        print(f"  旁证: stored last_hidden vs stored hidden_states[:,-1,:] 相对差 "
              f"{rel(stored_lh, stored_hs[:, -1, :].astype(np.float32)):.4e}")


if __name__ == "__main__":
    main(sys.argv[1])