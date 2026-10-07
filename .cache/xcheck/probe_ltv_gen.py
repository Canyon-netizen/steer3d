#!/usr/bin/env python3
"""LTV 的 G-c 探针：**注入后自由生成**，落全文。只采数，不下判决。

判决的唯一权威仍是 `.cache/xcheck/build_ltv.py`；本文件把生成出来的正文
交给 `.cache/xcheck/ltv_behavior.py` 与 build 链去判。

## 它为什么现在才做

G-c 要求「$S_k$ 指向的行为出现在**注入后的可读输出**里」，而前几轮的
`probe_ltv.py` 只做了**教师强制**下的改口测量 —— 两种不同实验。
`build_ltv.py` 一直把它报成 `na` 并写明原因。

## 测量程序已预先写死

`LTV_PREREG.md` **修订 4** 在取任何生成文本**之前**就把词表、三臂、判决规则、
样本量与不可判情形全部写死了。本文件只负责按那份文件跑，
**不许在这里挑 α、不许改词表、不许只跑看起来好看的那一档。**

## 注入点：实测是同一个

`.cache/probe_hook_equiv.py` 实测：`probe_ltv.py` 的
「forward hook on `layers[LAYER-1]`、替换单点」与 `ResidualSteerer` 的
「pre-hook on `layers[LAYER]`、加到整段」打在**同一个残差流位置**
（作用域对齐后 logits 逐位相同）。所以这里直接复用 `ResidualSteerer`。

⚠ **σ 必须照抄 `probe_ltv.py` 的定标**：`hidden_states[LAYER][0].float().std()`
  （整段前缀在该层的 std）。**不要用 `reg.scaled`** —— 那是
  `strength × layer_rms(layer)`，与前者不是同一个统计量，混用会让 α 偏一个量级。
  （`ResidualSteerer` 只负责把给它的向量加上去，定标在调用方，这里就写死。）

## 三臂

arm（`α·σ·v̂`）／ rand（`α·σ·û`，同范数随机方向）／ zero（不注入）。
rand 是牙齿：只比 zero 的话，「任何扰动都会让文本变形」也会被判成通过。

用法:
    PYTHONPATH=.cache/pylibs python3 .cache/xcheck/probe_ltv_gen.py
    N_TOKENS=128 python3 .cache/xcheck/probe_ltv_gen.py     # 最小可跑探针
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "backend", "examples"))

OUT = os.environ.get("OUT", os.path.join(HERE, "ltv_gen.json"))
RAW = os.environ.get("ARTIFACT", os.path.join(HERE, "ltv.json"))
MODEL_DIR = os.environ.get("PROBE_MODEL",
                           os.path.join(REPO, "datasets", "models", "Qwen3-1.7B"))
COT = os.path.join(REPO, "datasets", "aime_qwen3_1p7b_16k_fp16", "aime")

# ---- 全部来自 LTV_PREREG.md 修订 4，一个都不许在这里改 --------------------
LAYER = 14
ALPHAS = [0.35, 1.0, 4.0]        # 修订 4 ①：低于/接近/高于 α* 中位 1.0
N_TOKENS = int(os.environ.get("N_TOKENS", "256"))
SEED = 20261007                   # 与 probe_ltv.py 同一个种子，便于复现
ARMS = ("arm", "rand", "zero")
# ----------------------------------------------------------------------------


def log(*a):
    print(*a, flush=True)


def main():
    if not os.path.exists(MODEL_DIR):
        log(f"缺模型 {MODEL_DIR}")
        return 2
    import numpy as np
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from run_intervention import run_dual_stream

    # 留出题**从原始产物的 split 读**，不自己挑题 —— 预登记 §3/§5 写死了
    # 「不在抽取用的那批上下文上报 G-c」，挑题规则不许在探针里另发明。
    raw = json.load(open(RAW, encoding="utf-8"))
    holdout = list((raw.get("split") or {}).get("holdout") or [])
    if not holdout:
        log("原始产物 split.holdout 为空 ⇒ 预登记 §5 的前提不成立，不许跑")
        return 2
    log(f"留出题 {holdout}")

    tok = AutoTokenizer.from_pretrained(MODEL_DIR)
    model = AutoModelForCausalLM.from_pretrained(MODEL_DIR, torch_dtype=torch.float32)
    model.eval()

    # 杠杆方向。**只取方向**（单位化），强度在下面按 probe_ltv 的 σ 另算。
    sys.path.insert(0, os.path.join(REPO, "backend"))
    from core.steering import get_registry
    reg = get_registry()
    v = reg.scaled("confidence_up", 1.0, LAYER)
    if v is None:
        log("registry 里没有 confidence_up")
        return 2
    vhat = np.asarray(v, dtype=np.float32)
    vhat = vhat / np.linalg.norm(vhat)

    rng = np.random.default_rng(SEED)

    result = {
        "schema": "steer3d.ltv_gen/1",
        "source": "probe_ltv_gen.py",
        "prereg": "LTV_PREREG.md 修订 4（在取任何生成文本之前写死）",
        "layer": LAYER,
        "alphas": ALPHAS,
        "arms": list(ARMS),
        "n_tokens": N_TOKENS,
        "seed": SEED,
        "prompt_field": "chat_template_input（原始 CoT 用的同一份模板化输入）",
        "sigma_rule": "hidden_states[%d][0].float().std()，照抄 probe_ltv.py" % LAYER,
        "holdout": holdout,
        "runs": [],
        "problems": [],
    }

    for pid in holdout:
        p = os.path.join(COT, pid + ".json")
        if not os.path.exists(p):
            log(f"⚠ 缺 {pid}.json，跳过")
            continue
        cot = json.load(open(p, encoding="utf-8"))
        prompt = cot["chat_template_input"]

        # σ：照抄 probe_ltv.py 的定标，且**只算一次**（同一 prompt 三臂共用）
        enc = tok(prompt, return_tensors="pt", add_special_tokens=False)
        with torch.no_grad():
            out = model(**enc, output_hidden_states=True)
        sigma = float(out.hidden_states[LAYER][0].float().std())
        log(f"\n=== {pid}　prompt {enc['input_ids'].shape[1]} tok　σ={sigma:.4f}")

        # 同范数随机方向，种子写死；每题每档重抽（修订 4 没有写死重抽规则，
        # 这里**固定为每题一个**，与 alpha 无关 —— 这样「同一题的 rand」在各档
        # 之间是可比的，而不同题的 rand 之间不可比。）
        u = rng.standard_normal(vhat.shape).astype(np.float32)
        u = u / np.linalg.norm(u)

        result["problems"].append(
            {"pid": pid, "n_prompt_tokens": int(enc["input_ids"].shape[1]),
             "sigma": sigma, "ground_truth": cot.get("ground_truth")})

        for alpha in ALPHAS:
            for arm in ARMS:
                t0 = time.time()
                if arm == "arm":
                    vec = (alpha * sigma * vhat).astype(np.float32)
                elif arm == "rand":
                    vec = (alpha * sigma * u).astype(np.float32)
                else:
                    vec = None
                r = run_dual_stream(model, tok, prompt, vec, LAYER,
                                    max_new_tokens=N_TOKENS,
                                    track_shadow=False)
                txt = r["primary_text"]
                result["runs"].append({
                    "pid": pid, "alpha": alpha, "arm": arm,
                    "n_steps": r["n_steps"],
                    "norm": (float(np.linalg.norm(vec)) if vec is not None else 0.0),
                    "text": txt,
                    "text_sha_1": __import__("hashlib").sha1(
                        txt.encode("utf-8")).hexdigest(),
                    "wallclock_s": round(time.time() - t0, 1),
                })
                log(f"   α={alpha:<5} {arm:<5} steps={r['n_steps']:<5}"
                    f" ‖v‖={result['runs'][-1]['norm']:.3f}"
                    f"  {result['runs'][-1]['wallclock_s']:.0f}s")
            json.dump(result, open(OUT, "w"), ensure_ascii=False, indent=1)

    json.dump(result, open(OUT, "w"), ensure_ascii=False, indent=1)
    log(f"\n已写出 {OUT}　{len(result['runs'])} 次生成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())