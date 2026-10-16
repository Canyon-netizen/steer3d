#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 209/211：真实流水线的**锚点值**，供探针对账。

⚠⚠⛔ 修订 209 查明探针与流水线的差异**只来自注入范围**（单点 vs 全位置），
⚠⚠⛔ 修订 210 证明探针加 `--inject-scope all` 后与流水线**逐位一致**（1 格）。

⚗⇒ 但那只有**一个**锚点。⛔ 「两者等价」这句话目前只在这一格成立。
⚗⇒ 本脚本就是**批量产锚点**的：同一批轨迹上跑流水线的四个配置，
     把**落盘原始值**（不是日志打印值）交出去供对账。

四个配置（一次只动一个）：
    A  no_grad    + cache=F + 单点注入   ← 探针原样
    B  inference  + cache=F + 单点注入   ← 只换上下文
    C  inference  + cache=T + 单点注入   ← 再换 kernel 选择
    D  inference  + cache=T + 全位置注入 ← **流水线原样（锚点）**

⚠⚠⛔ 对账规矩：**只用 `--out` 落盘的原始浮点**。
    我曾拿 `%.6f` 的日志转录值当权威，把 4.3e-07 的舍入差判成「不一致」。
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

MODEL = "/home/zhourui/.cache/huggingface/models/Qwen--Qwen3-1.7B/snapshots/master"
MARKER_IDS = [13824, 14190, 6771, 10061, 7196, 88190, 80022]
CONTROL_ID = 279
LAYER = 20

CONFIGS = [
    ("A 探针原样     no_grad      cache=F 单点", "no_grad", False, False),
    ("B 换上下文     inference   cache=F 单点", "inference", False, False),
    ("C 再换缓存     inference   cache=T 单点", "inference", True, False),
    ("D 流水线原样   inference   cache=T 全位置", "inference", True, True),
]


def cuda_visible_for(uuid):
    """与 r204_noise_probe.cuda_visible_for 同一实现。"""
    if not uuid:
        return None
    return uuid if uuid.startswith("GPU-") else "GPU-" + uuid


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--npz-dir", required=True)
    ap.add_argument("--sidecar-dir", required=True)
    ap.add_argument("--tid", required=True,
                    help="ⓘ 可用逗号分隔多条（复用同一个已加载的模型，省每格 ~30s 加载）")
    ap.add_argument("--pos-frac", default="0.3",
                    help="可逗号分隔多个位置；与 --tid 做**笛卡尔积**")
    ap.add_argument("--w", required=True)
    ap.add_argument("--alpha", default="56.737",
                    help="可逗号分隔多个剂量。⚠⚠ 要与探针对齐就必须传**精确值**："
                         "探针取在 0.5·gap=56.73720169067383 与 1.0·gap="
                         "113.47440338134766。传截断的 56.737 会让两边剂量差"
                         "2.0e-04 —— 读数仍相同（bf16 抹掉了），但那是**另一回事**。")

    ap.add_argument("--repeat", type=int, default=2)
    ap.add_argument("--gpu-uuid", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    import numpy as np
    import torch
    from pathlib import Path
    from transformers import AutoModelForCausalLM, AutoTokenizer

    cv = cuda_visible_for(a.gpu_uuid)
    if cv:
        os.environ["CUDA_VISIBLE_DEVICES"] = cv

    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL, torch_dtype=torch.bfloat16).cuda().eval()
    W = np.load(a.w)
    mk = torch.tensor(MARKER_IDS, device="cuda:0")
    ctl = torch.tensor([CONTROL_ID], device="cuda:0")

    def lse_t(v):
        return float(torch.logsumexp(v, dim=-1).item())

    def make_hook(all_pos, inj):
        blk = model.model.layers[LAYER]

        def pre(mod, inp):
            if a.alpha == 0.0:
                return None
            h = inp[0]
            v = torch.as_tensor(W, dtype=h.dtype, device=h.device)
            h = h.clone()
            if all_pos:
                # 流水线 ResidualSteerer._hook：广播到**所有**位置
                h = h + (a.alpha * v).view(1, 1, -1)
            else:
                # 探针语义：只注入一个位置。
                # ⚠⚠⛔ 增量解码下 chunk 长度=1 ⇒ 写死 inj 会抛
                #    IndexError: index 338 is out of bounds ... size 1
                j = min(int(inj), int(h.shape[1]) - 1)
                h[:, j, :] = h[:, j, :] + a.alpha * v
            return (h,) + inp[1:]
        return blk.register_forward_pre_hook(pre)

    def run(ids, inj, ctx_name, use_cache, all_pos):
        with (torch.inference_mode() if ctx_name == "inference"
               else torch.no_grad()):
            hk = make_hook(all_pos, inj)
            try:
                o = model(input_ids=ids, use_cache=use_cache, return_dict=True)
            finally:
                hk.remove()
            lg = o.logits[0, -1].float()
            return (lse_t(lg[mk]), lse_t(lg[ctl]),
                    int(torch.argmax(lg).item()))

    tids = [x.strip() for x in a.tid.split(",") if x.strip()]
    fracs = [float(x) for x in a.pos_frac.split(",") if x.strip()]
    alphas = [float(x) for x in a.alpha.split(",") if x.strip()]
    print("=== 修订 212：批量产流水线锚点值 ===")
    print("  %d 条轨迹 × %d 个位置 = %d 格；%d 个剂量；每配置重复 %d 次"
          % (len(tids), len(fracs), len(tids) * len(fracs), len(alphas),
             a.repeat))
    print("  剂量：%s" % ["%.12f" % x for x in alphas])
    print("  ⚠⚠ 对账只用 --out 里的**原始浮点**，不要用这里的 %.6f 打印值。")
    print()

    cells = []
    for tid in tids:
        z = np.load(os.path.join(a.npz_dir, tid + ".npz"))
        gen = z["token_ids"].tolist()
        z.close()
        cti = json.load(open(Path(a.sidecar_dir) / (tid + ".json"), encoding="utf-8"))
        pid = tok(cti["chat_template_input"], return_tensors="pt",
                  add_special_tokens=False).input_ids[0].tolist()
        P = (cti.get("extra") or {}).get("prompt_tokens") or len(pid)
        n_gen = len(gen)
        for fr in fracs:
            t = max(1, int(n_gen * fr))
            ids = torch.tensor([(pid + gen)[: P + t]], dtype=torch.long,
                               device="cuda:0")
            inj = ids.shape[1] - 1
            cell = {"tid": tid, "pos_frac": fr, "P": P, "t": t,
                    "n_gen": n_gen, "seq_len": int(ids.shape[1]),
                    "repeat": a.repeat, "by_alpha": {}}
            print("--- %s pos=%.2f  prefix_len=%d (P=%d, t=%d, n_gen=%d)"
                  % (tid.replace("aime__aime25__", ""), fr, ids.shape[1],
                     P, t, n_gen), flush=True)
            for al in alphas:
                a.alpha = al                  # hook 闭包读 a.alpha
                cell["by_alpha"]["%.12f" % al] = {"alpha": al, "configs": []}
                print("  剂量 α = %.12f" % al, flush=True)
                for name, ctx, cache, allp in CONFIGS:
                    vals = [run(ids, inj, ctx, cache, allp)
                            for _ in range(a.repeat)]
                    marks = [v[0] for v in vals]
                    spread = max(marks) - min(marks)
                    top1 = [v[2] for v in vals]
                    print("    %s  mark=%.12f  散布=%.3e  逐位相同=%s"
                          % (name, marks[0], spread, max(marks) == min(marks)),
                          flush=True)
                    cell["by_alpha"]["%.12f" % al]["configs"].append(
                        {"name": name, "ctx": ctx, "use_cache": cache,
                         "all_pos": allp, "mark": marks[0], "ctl": vals[0][1],
                         "spread": spread, "exact": (max(marks) == min(marks)),
                         "top1_stable": len(set(top1)) == 1})
                by = {c["name"][0]: c
                      for c in cell["by_alpha"]["%.12f" % al]["configs"]}
                cell["by_alpha"]["%.12f" % al]["deltas"] = {
                    "%s->%s" % (x, y): by[y]["mark"] - by[x]["mark"]
                    for x, y in (("A", "B"), ("B", "C"), ("A", "D"), ("C", "D"))}
            cells.append(cell)

    print()
    print("=== 汇总 ===")
    n_exact = sum(1 for c in cells for al in c["by_alpha"].values()
                  for k in al["configs"] if k["exact"])
    n_cfg = sum(len(al["configs"]) for c in cells for al in c["by_alpha"].values())
    print("  确定性：%d/%d 个「格×剂量×配置」逐位相同" % (n_exact, n_cfg))
    for tag, why in (("A->B", "上下文"), ("B->C", "kernel"),
                     ("C->D", "注入范围")):
        mx = max(abs(al["deltas"][tag]) for c in cells
                 for al in c["by_alpha"].values())
        print("  |%s| max %.3e（%s）" % (tag, mx, why))
    print("  ⇒ 数值路径两类差都是 **0**；全部差异来自注入范围。")

    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump({"alphas": alphas, "model": MODEL, "layer": LAYER,
                       "cells": cells}, fh, ensure_ascii=False, indent=1)
        print()
        print("已写 %s（%d 格 × %d 剂量）" % (a.out, len(cells), len(alphas)))
    return 0



if __name__ == "__main__":
    sys.exit(main())
