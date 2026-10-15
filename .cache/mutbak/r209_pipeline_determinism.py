#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 209：在**真实流水线**的推理模式下，验修订 208 那条「确定性」。

⚠⚠⛔ 修订 208 证的是**探针**上读数确定。探针与真实流水线有**三处**不同，
⚠⚠⛔ 三处都可能是「确定性」的来源（context manager / kernel 选择 / 注入范围）：

    | 维度 | 探针 r204_noise_probe.py | 真实流水线 run_paired_steering.py |
    |---|---|---|
    | 上下文     | `torch.no_grad()`            | `torch.inference_mode()` |
    | KV cache   | `use_cache=False`（全量一次）| `use_cache=True`（增量解码）|
    | 注入范围   | 只注入 1 个位置 `h[:,inj,:]` | `x + v` 广播到**所有**位置 |

⚗⇒ 拆成一个因子实验，**一次只动一个**：

    A  no_grad      + use_cache=False + 单点注入   ← 探针原样
    B  inference    + use_cache=False + 单点注入   ← 只换上下文
    C  inference    + use_cache=True  + 单点注入   ← 再换 kernel 选择
    D  inference    + use_cache=True  + 全位置注入 ← 流水线原样

问三个问题
  Q1 每个配置**重复跑**是否逐位相同？⇒ 确定性在哪个配置下成立？
  Q2 A→B、B→C 各差多少？⇒ 「探针 vs 流水线」里有多少来自数值路径？
  Q3 A vs D 差多少？⇒ **注入范围**这一个语义差异有多大？
     ⛔ 若这个差 ≫ resid_std（≈0.06），那么探针量的量与流水线 P9 量的量
        **不是同一个**，前面修订 205–208 那些 P9 数字**不能**当流水线的证据。
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# 与 r204_noise_probe.py 同源（那边是这些量的定义处）
MODEL = "/home/zhourui/.cache/huggingface/models/Qwen--Qwen3-1.7B/snapshots/master"
MARKER_IDS = [13824, 14190, 6771, 10061, 7196, 88190, 80022]
CONTROL_ID = 279
LAYER = 20


def cuda_visible_for(uuid):
    """与 r204_noise_probe.cuda_visible_for 同一实现（同深度可复制）。"""
    if not uuid:
        return None
    return uuid if uuid.startswith("GPU-") else "GPU-" + uuid


def read_prefix(npz_dir, sidecar_dir, tid, pos_frac):
    """按探针同款方式取 (prompt_ids, gen_ids, P, t)。"""
    import numpy as np
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(MODEL)
    z = np.load(os.path.join(npz_dir, tid + ".npz"))
    gen = z["token_ids"].tolist()
    z.close()
    from pathlib import Path
    cti = json.load(open(Path(sidecar_dir) / (tid + ".json"), encoding="utf-8"))
    pid = tok(cti["chat_template_input"], return_tensors="pt",
              add_special_tokens=False).input_ids[0].tolist()
    P = (cti.get("extra") or {}).get("prompt_tokens") or len(pid)
    n = len(gen)
    t = max(1, int(n * pos_frac))
    return tok, (pid + gen)[: P + t], P, t, len(gen)


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--npz-dir", required=True)
    ap.add_argument("--sidecar-dir", required=True)
    ap.add_argument("--tid", required=True)
    ap.add_argument("--pos-frac", type=float, default=0.3)
    ap.add_argument("--w", required=True)
    ap.add_argument("--alpha", type=float, default=56.737)
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--gen-steps", type=int, default=0,
                    help=">0 时按流水线方式贪心解码这么多步，比较两条路径")
    ap.add_argument("--gpu-uuid", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    import numpy as np
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    cv = cuda_visible_for(a.gpu_uuid)
    if cv:
        os.environ["CUDA_VISIBLE_DEVICES"] = cv

    tok, ids_list, P, t, n_gen = read_prefix(a.npz_dir, a.sidecar_dir,
                                            a.tid, a.pos_frac)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL, torch_dtype=torch.bfloat16).cuda().eval()
    ids = torch.tensor([ids_list], dtype=torch.long, device="cuda:0")
    inj = ids.shape[1] - 1
    W = np.load(a.w)
    mk = torch.tensor(MARKER_IDS, device="cuda:0")
    ctl = torch.tensor([CONTROL_ID], device="cuda:0")

    def lse_t(v):
        return float(torch.logsumexp(v, dim=-1).item())

    def make_hook(all_pos):
        blk = model.model.layers[LAYER]

        def pre(mod, inp):
            if a.alpha == 0.0:
                return None
            h = inp[0]
            v = torch.as_tensor(W, dtype=h.dtype, device=h.device)
            h = h.clone()
            if all_pos:
                # 流水线 ResidualSteerer._hook 的语义：广播到所有位置
                h = h + (a.alpha * v).view(1, 1, -1)
            else:
                # 探针的语义：只注入**一个**位置。
                # ⚠⚠⛔ 原探针写死 `h[:, inj, :]`（inj = prefix 长度 − 1）。
                #    在 **增量解码**下当前 chunk 长度是 1 ⇒ `IndexError:
                #    index 338 is out of bounds for dimension 1 with size 1`。
                # ⚗⇒ 这条崩溃本身就是发现：**探针那种「单点注入」在结构上
                #    无法用于增量解码**，它只能作用在 prefill 的那一位。
                #    ⇒ 取 min(inj, 当前长度−1) 作语义推广：prefill 时恰是 inj，
                #      decode 时唯一那一位就是它。
                j = min(inj, h.shape[1] - 1)
                h[:, j, :] = h[:, j, :] + a.alpha * v
            return (h,) + inp[1:]
        return blk.register_forward_pre_hook(pre)


    def run(ctx_name, use_cache, all_pos):
        """返回 (marker_logsumexp, control_logsumexp, top1_id)。"""
        with (torch.inference_mode() if ctx_name == "inference"
               else torch.no_grad()):
            hk = make_hook(all_pos)
            try:
                o = model(input_ids=ids, use_cache=use_cache, return_dict=True)
            finally:
                hk.remove()
            lg = o.logits[0, -1].float()
            return (lse_t(lg[mk]), lse_t(lg[ctl]),
                    int(torch.argmax(lg).item()))

    def gen(ctx_name, all_pos, steps):
        """按流水线的方式贪心解码 `steps` 步，逐步记录 marker 的 logsumexp。

        ⚠⚠⛔ 为什么必须比「生成」而不只是比「第 0 步的读数」：
        两条路径在**读完 prefix 那一刻**就已经不同了（见配置 C/D 的 Δ）。
        而 prefix 一旦不同，**KV cache 就不同**，后续每一步都在不同的
        上下文里跑 ⇒ 差异会**累积**。只报第 0 步会**低估**后果。
        """
        seqs = []
        with (torch.inference_mode() if ctx_name == "inference"
               else torch.no_grad()):
            hk = make_hook(all_pos)
            try:
                out = model(input_ids=ids, use_cache=True, return_dict=True)
                past = out.past_key_values
                nxt = int(torch.argmax(out.logits[0, -1].float()).item())
                seqs.append((nxt, lse_t(out.logits[0, -1].float()[mk])))
                for _ in range(steps):
                    if nxt == tok.eos_token_id:
                        break
                    out = model(input_ids=torch.tensor([[nxt]], device="cuda:0"),
                                past_key_values=past, use_cache=True,
                                return_dict=True)
                    past = out.past_key_values
                    lg = out.logits[0, -1].float()
                    nxt = int(torch.argmax(lg).item())
                    seqs.append((nxt, lse_t(lg[mk])))
            finally:
                hk.remove()
        return seqs


    CONFIGS = [
        ("A 探针原样     no_grad      cache=F 单点", "no_grad", False, False),
        ("B 换上下文     inference   cache=F 单点", "inference", False, False),
        ("C 再换缓存     inference   cache=T 单点", "inference", True, False),
        ("D 流水线原样   inference   cache=T 全位置", "inference", True, True),
    ]

    res = {"tid": a.tid, "pos_frac": a.pos_frac, "P": P, "t": t, "n_gen": n_gen,
           "seq_len": ids.shape[1], "alpha": a.alpha, "repeat": a.repeat,
           "configs": []}

    print("=== 修订 209：真实流水线的推理模式下验确定性 ===")
    print("  tid=%s pos=%.2f  prefix_len=%d (P=%d, t=%d, n_gen=%d)  α=%.3f"
          % (a.tid, a.pos_frac, ids.shape[1], P, t, n_gen, a.alpha))
    print("  每个配置重复 %d 次；比对 marker 的 logsumexp 是否逐位相同。" % a.repeat)
    print()

    for name, ctx, cache, allp in CONFIGS:
        vals = [run(ctx, cache, allp) for _ in range(a.repeat)]
        marks = [v[0] for v in vals]
        exact = (max(marks) == min(marks))
        spread = max(marks) - min(marks)
        top1 = [v[2] for v in vals]
        print("  %s  mark=%+.6f  散布=%.3e  逐位相同=%s  top1=%s"
              % (name, marks[0], spread, exact,
                 top1[0] if len(set(top1)) == 1 else "⛔不一致%s" % top1))
        res["configs"].append({"name": name, "ctx": ctx, "use_cache": cache,
                               "all_pos": allp, "mark": marks[0],
                               "ctl": vals[0][1], "spread": spread,
                               "exact": exact,
                               "top1_stable": len(set(top1)) == 1})

    # ---- 两两差 ----
    print()
    print("=== 两两差（同一 prefix，只换一个变量）===")
    by = {c["name"][0]: c for c in res["configs"]}
    for x, y, why in (("A", "B", "上下文 no_grad → inference_mode"),
                      ("B", "C", "use_cache False → True（kernel 选择）"),
                      ("A", "D", "探针原样 → 流水线原样（全部三项）"),
                      ("C", "D", "注入范围 单点 → 全位置")):
        d = by[y]["mark"] - by[x]["mark"]
        print("  %s → %s  Δmark = %+.6f   （%s）" % (x, y, d, why))
    res["deltas"] = {}
    for x, y in (("A", "B"), ("B", "C"), ("A", "D"), ("C", "D")):
        res["deltas"]["%s->%s" % (x, y)] = by[y]["mark"] - by[x]["mark"]

    print()
    print("  ⛔ 判读门槛：把 Δ 与探针的 resid_std（0.05–0.10 量级）比。")
    print("     Δ ≫ 0.1 ⇒ 探针与流水线的**不是同一个量**。")

    # ---- 生成：两条路径在哪一步分叉 ----
    if a.gen_steps > 0:
        print()
        print("=== 生成 %d 步：两条路径的 marker 读数与 token 何时分叉 ===" % a.gen_steps)
        g_s = gen("inference", False, a.gen_steps)      # 单点注入
        g_a = gen("inference", True, a.gen_steps)       # 全位置注入（流水线）
        first_tok = next((i for i in range(min(len(g_s), len(g_a)))
                          if g_s[i][0] != g_a[i][0]), None)
        print("  步  %-26s %-26s %10s" % ("单点注入 mark", "全位置 mark", "Δ"))
        for i in range(min(len(g_s), len(g_a))):
            print("  %2d  %+26.6f %+26.6f %+10.6f"
                  % (i, g_s[i][1], g_a[i][1], g_a[i][1] - g_s[i][1]))
        print()
        print("  首个**token** 分叉的步：%s" % ("第 %d 步" % first_tok
                                                if first_tok is not None
                                                else "⛔ %d 步内未分叉" % a.gen_steps))
        print("  ⚠⚠ 两条路径的 prefix 从第 0 步就不同 ⇒ KV cache 不同 ⇒")
        print("     后续每一步都在不同上下文里跑，差异**累积**。")
        res["gen"] = {"n_sing": len(g_s), "n_all": len(g_a),
                      "first_tok_div": first_tok,
                      "mark_sing": [x[1] for x in g_s],
                      "mark_all": [x[1] for x in g_a],
                      "tok_sing": [x[0] for x in g_s],
                      "tok_all": [x[0] for x in g_a]}

    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(res, fh, ensure_ascii=False, indent=1)
        print()
        print("已写 %s" % a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
