"""KV-cache 共享加速的等价性判决。

## 为什么验这个

R6_RERUN_PREREG §2 计划：注入在 t−1、读取在 t，而 t−1 之前的状态与剂量无关
⇒ prefix[0:t−1] 的 KV cache 按案例算一次，各变体只重跑 2 个位置。
照搬旧设计要 ~1800 次长前缀全量前向，跑不完。

但「数学上等价」不等于「数值上等价」。bf16 的 attention 累加顺序、
chunk 形状都会影响末位。所以必须实测。

## 判决规则（取数前写死）

  E1 快慢两条路径读出的 marker token 的 Δlogit，
     逐变体最大绝对差 <= 5e-3（预登记 §2 写死的门槛）
  E2 两条路径读出的 **argmax token id** 完全一致
  E3 快路径的耗时显著低于慢路径（否则加速没意义，加速本身要否掉）
  E4 用「hook 空挂（α=0）」做零对照：装 hook 本身不得改变读数，
     差 > 1e-3 判红 —— 这是旧实验已有的约定，本轮继续守

E1/E2 任一不达标 => 放弃加速，按慢路径跑完（本轮宁可慢也不引入未验证的变换）。
"""
from __future__ import annotations

import copy
import json
import os
import sys
import time

os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
# ⚠ 卡的选择必须按 **UUID**，且必须在 import torch **之前**设定。
#   两个坑都踩过：
#   1. CVD 编号依赖 CUDA_DEVICE_ORDER：FASTEST_FIRST 与 PCI_BUS_ID 给出
#      **不同**的 卡号<->卡 对应。曾因此把测试脚本放到生成任务正在用的那张卡上。
#   2. torch.cuda.device_count() 一调用就初始化 CUDA，之后再改
#      CUDA_VISIBLE_DEVICES 对当前进程**无效**。
#   CUDA 支持直接写 `CUDA_VISIBLE_DEVICES=GPU-<uuid>`，绕开以上全部歧义。
os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
_uuid = sys.argv[2] if len(sys.argv) > 2 else None
if _uuid:
    os.environ["CUDA_VISIBLE_DEVICES"] = f"GPU-{_uuid}"
    print(f"[卡] CUDA_VISIBLE_DEVICES=GPU-{_uuid}（按 UUID 指定，不猜编号）")
else:
    print("[卡] 未指定 UUID，沿用环境中的 CUDA_VISIBLE_DEVICES")

import numpy as np
import torch

MODEL = "/home/zhourui/.cache/huggingface/models/Qwen--Qwen3-1.7B/snapshots/master"
ROOT = "/home/zhourui/steer3d_bpath/pilot8192/aime"
LAYER = 20
MARKER_IDS = [13824, 14190, 6771, 10061, 7196, 88190, 80022]
ALPHAS = [0.0, 0.25, 0.5, 1.0]
TOL_LOGIT = 5e-3
TOL_HOOK0 = 1e-3


def logit_at(ids, t, vec, alpha, model):
    """慢路径：全量前向 [0..t]，在绝对位置 t-1 注入，返回 t 处 marker 的 logit。"""
    x = ids[: t + 1].unsqueeze(0)
    blk = model.model.layers[LAYER]
    inj_at = t - 1

    def pre_hook(mod, inp):
        h = inp[0]
        if h.shape[1] > inj_at and alpha != 0.0:
            h = h.clone()
            h[:, inj_at, :] = h[:, inj_at, :] + alpha * vec.to(h.dtype)
            return (h,) + inp[1:]
        return None

    hd = blk.register_forward_pre_hook(pre_hook)
    try:
        with torch.no_grad():
            out = model(input_ids=x, use_cache=True, return_dict=True)
    finally:
        hd.remove()
    return out.logits[0, t].float()


def logit_at_fast(ids, t, vec, alpha, model, prefix_cache, explicit_pos=True):
    """快路径：用共享的 prefix cache，只重跑位置 t-1 与 t。

    两个必须显式处理的点（第一版两处都踩了，E4 零对照当场把它抓出来）：

      1. **cache 会被原地增长**。HF 的 forward 把新 key/value 追加进
         传入的 DynamicCache。同一份 cache 连用几个变体后，里面已经是
         [0..t] 了，第二个变体等于把 [t-1, t] 又拼了一遍 ⇒ 必须每个变体
         各自持有一份（deepcopy 或 crop）。
      2. **position_ids / RoPE**。cached 调用若让模型自己推断位置，
         可能从 0 重新数起 ⇒ RoPE 相位错，注意力结果就不一样了。
         显式给出 [t-1, t]。
    """
    blk = model.model.layers[LAYER]

    def pre_hook(mod, inp):
        h = inp[0]
        if h.shape[1] > 0 and alpha != 0.0:
            h = h.clone()
            h[:, 0, :] = h[:, 0, :] + alpha * vec.to(h.dtype)
            return (h,) + inp[1:]
        return None

    cache = copy.deepcopy(prefix_cache)
    hd = blk.register_forward_pre_hook(pre_hook)
    kw = {}
    if explicit_pos:
        kw["position_ids"] = torch.tensor([[t - 1, t]], dtype=torch.long, device=ids.device)
    try:
        with torch.no_grad():
            out = model(input_ids=ids[t - 1: t + 1].unsqueeze(0),
                        past_key_values=cache, use_cache=True, return_dict=True, **kw)
    finally:
        hd.remove()
    return out.logits[0, -1].float()


def main():
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL)
    DT = torch.float32 if (len(sys.argv) > 3 and sys.argv[3] == "fp32") else torch.bfloat16
    print(f"[dtype] {DT}")
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=DT).to("cuda:0").eval()

    name = "aime__aime25__p00__think"
    meta = json.load(open(f"{ROOT}/{name}.json"))
    z = np.load(f"{ROOT}/{name}.npz", allow_pickle=True)
    gen_ids = z["token_ids"].tolist()
    prompt_ids = tok(meta["chat_template_input"], return_tensors="pt",
                     add_special_tokens=False).input_ids[0].tolist()
    ids = torch.tensor(prompt_ids + gen_ids, dtype=torch.long, device="cuda:0")
    marker_pos = [i for i, tid in enumerate(gen_ids)
                  if tid in MARKER_IDS]
    marker_abs = [len(prompt_ids) + i for i in marker_pos]
    print(f"轨迹 {name}: T_p={len(prompt_ids)} T_g={len(gen_ids)} marker 数={len(marker_abs)}")

    rng = np.random.default_rng(42)
    vec = torch.tensor(rng.standard_normal(2048).astype(np.float32))
    vec = (vec / vec.norm()).to("cuda:0")
    marker_id = MARKER_IDS[0]

    rows = []
    for t in marker_abs[len(marker_abs) // 2: len(marker_abs) // 2 + 2]:
        # 共享前缀 cache：[0, t-1]
        tp0 = time.time()
        with torch.no_grad():
            pre = model(input_ids=ids[: t - 1].unsqueeze(0), use_cache=True, return_dict=True)
        t_pre = time.time() - tp0
        cache = pre.past_key_values
        for a in ALPHAS:
            t0 = time.time()
            slow = logit_at(ids, t, vec, a, model)
            t1 = time.time()
            fast = logit_at_fast(ids, t, vec, a, model, cache)
            t2 = time.time()
            rows.append({
                "t": t, "alpha": a,
                "logit_slow": float(slow[marker_id].item()),
                "logit_fast": float(fast[marker_id].item()),
                "abs_diff": float((slow - fast).abs().max().item()),
                "argmax_same": int(slow.argmax()) == int(fast.argmax()),
                "slow_s": t1 - t0, "fast_s": t2 - t1, "prefix_s": t_pre,
                "fast_amort_s": (t2 - t1) + t_pre / len(ALPHAS),
            })
            print(f"  t={t} alpha={a:<5} marker_logit slow={rows[-1]['logit_slow']:+.4f} "
                  f"fast={rows[-1]['logit_fast']:+.4f} 全logit最大差={rows[-1]['abs_diff']:.3e} "
                  f"argmax同={rows[-1]['argmax_same']} "
                  f"慢={rows[-1]['slow_s']:.2f}s 快={rows[-1]['fast_s']:.2f}s 摊薄后={rows[-1]['fast_amort_s']:.2f}s")

    dmax = max(r["abs_diff"] for r in rows)
    arg_ok = all(r["argmax_same"] for r in rows)
    # E4：alpha=0 时慢快两路必须逐位一致（hook 空挂不改变结果）
    a0 = [r for r in rows if r["alpha"] == 0.0]
    e4 = max(r["abs_diff"] for r in a0) if a0 else 0.0
    t_slow = sum(r["slow_s"] for r in rows)
    t_fast = sum(r["fast_s"] for r in rows)
    t_amort = sum(r["fast_amort_s"] for r in rows)

    print("\n" + "=" * 72)
    e1 = dmax <= TOL_LOGIT
    e2 = arg_ok
    e3 = t_amort < t_slow
    print(f"E1 快慢最大 logit 差 <= {TOL_LOGIT} : {dmax:.3e}  -> {'PASS' if e1 else 'FAIL'}")
    print(f"E2 argmax 逐变体一致            : {arg_ok}  -> {'PASS' if e2 else 'FAIL'}")
    print(f"E3 快路径更快(摊薄前缀后)      : 慢 {t_slow:.1f}s vs 快 {t_amort:.1f}s"
          f" ({t_slow/max(t_amort,1e-9):.1f}x)  -> {'PASS' if e3 else 'FAIL'}")
    print(f"E4 alpha=0 空挂不改变读数 <= {TOL_HOOK0} : {e4:.3e}  -> {'PASS' if e4<=TOL_HOOK0 else 'FAIL'}")
    print("=" * 72)

    out = ("/home/zhourui/steer3d_bpath/kv_share_verdict_fp32.json"
           if DT == torch.float32 else "/home/zhourui/steer3d_bpath/kv_share_verdict.json")
    json.dump({"rows": rows, "dmax": dmax, "argmax_all_same": arg_ok,
               "t_slow_s": t_slow, "t_fast_s": t_fast, "t_fast_amort_s": t_amort, "hook0_diff": e4,
               "tolerances": {"logit": TOL_LOGIT, "hook0": TOL_HOOK0},
               "verdict": {"E1": e1, "E2": e2, "E3": e3, "E4": e4 <= TOL_HOOK0}},
              open(out, "w"), indent=1)
    print("写出", out)
    print("\n=> " + ("加速可用，按快路径跑。" if (e1 and e2 and e3) else
                     "**加速不成立**，按慢路径跑完或另想办法。"))
    return 0 if (e1 and e2 and e3 and e4 <= TOL_HOOK0) else 1


if __name__ == "__main__":
    sys.exit(main())