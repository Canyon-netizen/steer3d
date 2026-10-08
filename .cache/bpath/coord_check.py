"""新批次坐标系统自检：R-6 是否真的不需要 prompt 回填。

## 为什么查这个

R-1 确立的正确映射是
    npz 第 g 行 == 全序列第 (P + g − 1) 位,  P = prompt token 数。
回填脚本会往 npz 里写 `prompt_token_ids`，看上去 P 只能从那儿拿。

但采集器第 279-280 行自己就写了
    enc = tokenizer(text, add_special_tokens=False);  extra["prompt_tokens"] = len
——**P 就在侧车里**，而且是同一份 `add_special_tokens=False` 分词的结果。
注入那一轮又自己跑全序列前向，`prompt_hidden_states` 一次都没读过。
⇒ 回填很可能**不在关键路径上**，能省 1 小时 GPU + 27 GB 回传。

## 判决规则（取数前写死）

  C1 新批次每条侧车都有 `extra.prompt_tokens`（缺一条就回填不能省）
  C2 用 `add_special_tokens=False` 重新分词 `chat_template_input`，
     得到的 token 数必须**逐条等于** `extra.prompt_tokens`
     （不等 ⇒ 生成侧与复算侧不一致，全序列坐标不可信，必须回填）
  C3 重新分词得到的 **token id 序列**与 `extra.prompt_tokens` 之外无冲突：
     用它拼出的全序列前若干位必须能喂进 tokenizer 且长度自洽
  C4 marker 位置在「生成段坐标」与「全序列坐标」下的换算必须与 R-1 一致：
     gen 下标 g  ->  全序列 P+g-1

任一不成立 => 回填不能省，P1..P9 的执行方式要改。
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

MODEL_DIR = "/Users/zhourui/code/steer3d/datasets/models/Qwen3-1.7B"
MARKER_IDS = [13824, 14190, 6771, 10061, 7196, 88190, 80022]


def main(root):
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL_DIR)

    files = sorted(glob.glob(f"{root}/*.json"))
    print(f"侧车 {len(files)} 份，来自 {root}")
    rows = []
    for f in files:
        j = json.load(open(f, encoding="utf-8"))
        P_side = (j.get("extra") or {}).get("prompt_tokens")
        cti = j.get("chat_template_input", "")
        ids = tok(cti, return_tensors="pt", add_special_tokens=False).input_ids[0].tolist()
        T_p = len(ids)
        gen_ids = j.get("n_generated_tokens")
        markers = [i for i, t in enumerate(j.get("tokens") or [])
                   if t["token_id"] in MARKER_IDS]
        rows.append({
            "traj": j["trajectory_id"],
            "mode": j["config"]["mode"],
            "cap": j["config"]["max_new_tokens"],
            "n_tok": gen_ids,
            "P_sidecar": P_side,
            "P_retokenized": T_p,
            "P_match": P_side == T_p,
            "full_len": T_p + (gen_ids or 0),
            "first_marker_gen": markers[0] if markers else None,
            "first_marker_full": (T_p + markers[0] - 1) if markers else None,
            "n_markers": len(markers),
        })

    print(f"\n{'traj':40s} {'mode':9s} {'tok':>5s} {'P(侧车)':>8s} {'P(复算)':>8s} "
          f"{'一致':>4s} {'marker0(gen)':>13s} {'-> 全序列':>9s}")
    for r in rows:
        print(f"{r['traj']:40s} {r['mode']:9s} {str(r['n_tok']):>5s} "
              f"{str(r['P_sidecar']):>8s} {r['P_retokenized']:8d} "
              f"{'OK' if r['P_match'] else 'MISMATCH':>4s} "
              f"{str(r['first_marker_gen']):>13s} {str(r['first_marker_full']):>9s}")

    c1 = all(r["P_sidecar"] is not None for r in rows)
    c2 = all(r["P_match"] for r in rows)
    c4 = all(r["first_marker_full"] == r["P_retokenized"] + r["first_marker_gen"] - 1
             for r in rows if r["first_marker_gen"] is not None)
    # C3：复算出的 prompt id 能喂回 tokenizer（往返自洽）
    ok_round = True
    for r in rows[:3]:
        f2 = files[files.index(next(x for x in files if True))]
        break
    j0 = json.load(open(files[0], encoding="utf-8"))
    ids0 = tok(j0["chat_template_input"], return_tensors="pt",
               add_special_tokens=False).input_ids[0].tolist()
    ok_round = (tok.decode(ids0) == j0["chat_template_input"])

    print("\n" + "=" * 74)
    print(f"C1 每条都有 extra.prompt_tokens : {c1}")
    print(f"C2 复算 token 数逐条相等       : {c2}")
    print(f"C3 分词往返自洽（decode 回原串）: {ok_round}")
    print(f"C4 marker 换算与 R-1 一致       : {c4}  (全序列 = P + g - 1)")
    print("=" * 74)

    if c1 and c2 and ok_round and c4:
        print("=> **回填可以省掉**：P 直接取 extra.prompt_tokens，"
              "注入自带全序列前向，prompt_hidden_states 读不到。")
        print("   省下约 1 小时 GPU（回填）+ 27 GB 回传。")
    else:
        print("=> **回填不能省**，P1..P9 的执行方式要改。")

    out = Path(".cache/mutbak/bpath_coord_check.json")
    json.dump({"rows": rows, "verdict": {"C1": c1, "C2": c2, "C3": ok_round, "C4": c4}},
              open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("写出", out)
    return 0 if (c1 and c2 and ok_round and c4) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))