#!/usr/bin/env python3
"""通用性检验：行为阈值在 RMS 归一化单位下，跨方向 / 跨层稳不稳定？

为什么问这个
------------
`probe_live_inject.py` 已经测到一件事：注入强度按「该层残差自身的 std」归一化后，
行为翻转有一个可测的阈值。这个说法本身就有意思 —— 因为残差流的**绝对尺度**
逐层差好几个数量级（深层可达数百），只有归一化之后，不同层/不同模型的数字
才可比。也就是说：效应的度量单位是 (方向, 层, 强度/该层RMS)，不是向量的绝对范数。

但「在一层一个方向上成立」不等于「通用」。要成为一条**可迁移的规律**，
它得在两个维度上稳：
  · 跨方向：6 个方向是不是都落在同一量级？
  · 跨层：14 层和 22 层是不是也同一量级？
两者若都稳 ⇒ 「按 RMS 归一化的强度阈值」是一条候选通则；
任一不稳 ⇒ 规律必须写成 (方向, 层) 的函数，那就不该拿它当通则讲。

判决规则在取数**之前**写死（不许看着结果再定标准）：
  · 「稳」= 各格的中位阈值落在彼此的 2 倍以内（max/min ≤ 2）
  · 「不稳」= 超过 2 倍，就照实说它是 (方向,层) 依赖的
  · 某格「未夹住」（最低档就翻 / 最高档还不翻）单独计，不混进稳不稳

用法:
  PYTHONPATH=.cache/pylibs python3 .cache/xcheck/probe_threshold_law.py
  GRID=0.1,0.25,0.6,1.5 STEPS=4 LAYERS=6,14,22 DIRECTIONS=reasoning_deep,confidence_up
"""
import json
import os
import statistics
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL = os.environ.get("PROBE_MODEL", os.path.join(REPO, "datasets", "models", "Qwen3-1.7B"))
LAYERS = [int(x) for x in os.environ.get("LAYERS", "6,14,22").split(",")]
DIRS = os.environ.get("DIRECTIONS", "reasoning_deep,confidence_up,creativity").split(",")
GRID = [float(x) for x in os.environ.get("GRID", "0.1,0.25,0.6,1.5").split(",")]
STEPS = int(os.environ.get("STEPS", "4"))
PROMPT = os.environ.get(
    "PROMPT",
    "Two skaters are on a frozen lake. One is 5 kg, the other 7 kg. "
    "They push off and the heavier one moves at 1.2 m/s. "
    "How fast does the lighter one move? Answer with a number only.",
)
# 判决阈值：格与格之间中位阈值超过 2 倍差就算「不稳」。取数前定死。
STABLE_RATIO = float(os.environ.get("STABLE_RATIO", "2.0"))

log = lambda *a: print(*a, flush=True)


def main():
    import numpy as np
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    sys.path.insert(0, os.path.join(REPO, "backend"))
    from core.steering import get_registry
    reg = get_registry()
    if not reg.names:
        log("装置故障：steering registry 里没有方向，本脚本无从验起")
        return 2
    log(f"registry 方向：{reg.names}")
    dirs = [d for d in DIRS if d in reg.names] or reg.names[:2]
    log(f"要测的方向：{dirs}   层：{LAYERS}   网格：{GRID}   步数：{STEPS}")

    tok = AutoTokenizer.from_pretrained(MODEL)
    pfx = tok.apply_chat_template(
        [{"role": "user", "content": PROMPT}],
        tokenize=False, add_generation_prompt=True)
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16)
    model.eval()
    layers_mod = model.model.layers

    def next_logits(cur, delta, layer):
        h = None
        if delta is not None:
            def hook(_m, _i, outp):
                hs = (outp[0] if isinstance(outp, tuple) else outp).clone()
                hs[:, -1, :] = hs[:, -1, :] + delta.to(hs.dtype)
                return ((hs,) + tuple(outp[1:])) if isinstance(outp, tuple) else hs
            h = layers_mod[layer].register_forward_hook(hook)
        try:
            with torch.no_grad():
                return model(**tok(cur, return_tensors="pt")).logits[0, -1].float()
        finally:
            if h is not None:
                h.remove()

    cells, t_all = [], time.time()
    for dname in dirs:
        for layer in LAYERS:
            if not (0 <= layer < model.config.num_hidden_layers):
                log(f"  跳过 {dname}@L{layer}：层越界")
                continue
            v = reg.scaled(dname, 1.0, layer)
            if v is None:
                log(f"  跳过 {dname}@L{layer}：registry 给不出向量")
                continue
            u = torch.tensor(np.asarray(v, dtype="float32"))
            u = u / (u.norm() + 1e-9)

            # 该层在该前缀上的残差尺度
            with torch.no_grad():
                hs = model(**tok(pfx, return_tensors="pt"),
                           output_hidden_states=True).hidden_states[layer][0]
            scale = float(hs.float().std())

            # 对照前缀。**同时把每步的对照 token id 存下来** ——
            # 后面每个强度档都要跟它比，而它与强度无关。
            # 早先的版本在每个强度档里重新前向一遍去取对照，等于白做 N 倍的功；
            # 更糟的是那让「对照」在不同档上变成 N 次独立计算，数值噪声会被
            # 误当成强度效应。存 id 之后对照是**同一个**数，跨档严格可比。
            pre, toks, toks_ids = pfx, [], []
            for _ in range(STEPS):
                lg = next_logits(pre, None, layer)
                nid = int(torch.argmax(lg))
                toks_ids.append(nid)
                toks.append(tok.decode([nid]))
                pre = pre + toks[-1]

            flip_at = {}
            for m in GRID:
                pre = pfx
                for i, want in enumerate(toks):
                    b = next_logits(pre, u * (m * scale), layer)
                    if int(torch.argmax(b)) != toks_ids[i] and i not in flip_at:
                        flip_at[i] = m
                    pre = pre + want
            unbracketed = [i for i in range(STEPS) if i not in flip_at]
            got = sorted(flip_at.values())
            cell = {
                "direction": dname, "layer": layer, "resid_scale": scale,
                "median_threshold": statistics.median(got) if got else None,
                "per_step_first_flip": flip_at,
                "n_flipped_steps": len(flip_at), "n_steps": STEPS,
                "unbracketed_steps": unbracketed,
                "bracketed_low": (got[0] == GRID[0]) if got else None,
            }
            cells.append(cell)
            log(f"  {dname:<18} L{layer:<3} 中位阈值="
                f"{('%.3f' % cell['median_threshold']) if cell['median_threshold'] else '—':>7}"
                f"  翻 {len(flip_at)}/{STEPS} 步  未夹住={unbracketed or '无'}")

    med = [c["median_threshold"] for c in cells if c["median_threshold"]]
    n_unb = sum(len(c["unbracketed_steps"]) for c in cells)
    log("")
    if len(med) >= 2:
        ratio = max(med) / min(med)
        stable = ratio <= STABLE_RATIO
        log(f"各格中位阈值：min={min(med):.3f} max={max(med):.3f} "
            f"比值={ratio:.2f}（判「稳」的门是 ≤{STABLE_RATIO}）")
    else:
        stable, ratio = False, None
        log(f"只有 {len(med)} 个格夹住了阈值，样本不足以判稳不稳")
    log(f"未夹住的 (格,步) 组合：{n_unb}")
    log("")
    if ratio is not None and stable and n_unb == 0:
        log("RESULT 稳 ⇒ 「按该层残差 RMS 归一化的强度阈值」可当候选通则")
    else:
        log("RESULT 不稳 ⇒ 阈值是 (方向,层) 依赖的，"
            "**不能**当成通则讲；只能作为该模型该层该方向的实测参数")
    log(f"      （未夹住 {n_unb} 处已单列，没有混进上面那个判断）")

    outp = os.path.join(REPO, ".cache", "probe_threshold_law.json")
    json.dump({"cells": cells, "grid": GRID, "stable": stable,
               "ratio": ratio, "stable_gate": STABLE_RATIO,
               "n_unbracketed": n_unb, "layers": LAYERS, "directions": dirs},
              open(outp, "w"), ensure_ascii=False, indent=2)
    log(f"（明细已写 {outp}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
