#!/usr/bin/env python3
"""干预实验（真模型）：沿一个方向注入，量输出怎么变 —— **本项目唯一还缺的因果证据**。

## 为什么这个脚本现在跑不了

本机（macOS 沙箱）实测：torch 2.8.0 在，但
* `transformers` 装不了（无外网）
* MPS `is_available()=False`、`torch.cuda.is_available()=False`
* 本地没有 Qwen3-1.7B 权重

⇒ 所以这个脚本**当前状态是「写好但未执行」**。它做的是两件事：
① 把前置条件逐条查清楚，缺什么就报什么，**不猜、不降级**；
② 前置条件齐了就能直接跑，不需要再改代码。

## 跑之前必须先过装置自证

`--selftest-only` 或每次开跑都会先执行 `selftest.py`。
**自证不过就不许碰真模型**：坏装置跑出来的空结果和有意义的空结果
长得一模一样（§4.4 已经吃过一次这个亏）。

## 实验设计

teacher-forced 前向：我们已经有每条轨迹的**确切 token 序列**，
所以不用重新生成，只需要在第 L 层往残差流里加 `α·mean‖h‖·v̂`，然后读：

1. **读出方向投影** ρ(v̂·h, y) —— 内部状态有没有沿声称的方向走
2. **下一 token 分布**：KL(base ‖ pert) 与目标类别概率质量的变化
3. **同范数随机方向对照**（N ≥ 200，§6 第 1 步的纪律）——
   植入方向必须打赢**最坏**那一条随机方向，否则结论只关于幅度
4. **位置轴对照**（`reasoning_deep`，§4.6 判定它是轨迹位置轴）——
   把「语义改变」和「沿位置移动」分开

### 成本（1.7B / 48 条 × 均 1441 token）

    基线            48 次
    植入 6 档 α     48 × 6 = 288 次
    随机对照        8 条轨迹 × 6 档 × 201 = 9648 次
    合计            ≈ 10⁴ 次前向；GPU 上分钟级，CPU 上不可能

⇒ 随机对照只在**子样本轨迹**上跑，随机性由 §4.8 的做法承担；
代价是这个数必须写进报告，不能当成全 48 条的结论。

## 用法

    python3 .cache/intervene/intervene_qwen.py --model /path/to/Qwen3-1.7B
    python3 .cache/intervene/intervene_qwen.py --preflight-only
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

LAYER = 14
ALPHAS = [-4.0, -2.0, -1.0, 1.0, 2.0, 4.0]
N_RANDOM = 200
N_RANDOM_TRACES = 8
SEED = 20261003
AXES = ["confidence_up", "caution", "creativity", "reasoning_deep"]


# --------------------------------------------------------------------------
# 前置条件：缺什么报什么，不猜、不降级
# --------------------------------------------------------------------------
def preflight(model_path: str | None):
    missing, notes = [], []

    try:
        import torch
        notes.append("torch %s" % torch.__version__)
        if torch.cuda.is_available():
            notes.append("CUDA 可用: %s" % torch.cuda.get_device_name(0))
        else:
            mps = getattr(torch.backends, "mps", None)
            ok = bool(mps and mps.is_available())
            notes.append("CUDA 不可用；MPS 可用=%s" % ok)
            if not ok:
                missing.append("可用算力（CUDA / MPS 都没有；CPU 上 ~10⁴ 次前向不现实）")
    except Exception as e:
        missing.append("torch（%s）" % e)
        torch = None  # noqa

    try:
        import transformers  # noqa: F401
        notes.append("transformers %s" % transformers.__version__)
    except Exception as e:
        missing.append("transformers（%s；本机无外网装不了）" % type(e).__name__)

    if not model_path:
        missing.append("模型路径（--model；本机没有 Qwen3-1.7B 权重）")
    elif not Path(model_path).exists():
        missing.append("模型路径不存在：%s" % model_path)
    else:
        notes.append("模型路径 %s" % model_path)

    return missing, notes


def run_selftest():
    """装置自证。不过就不许碰真模型。"""
    r = subprocess.run([sys.executable, str(HERE / "selftest.py")],
                       capture_output=True, text=True)
    tail = [ln for ln in r.stdout.splitlines()
            if ln.startswith("RESULT selftest")]
    print("装置自证: " + (tail[-1] if tail else "（没有 RESULT 行 —— 装置没跑完）"))
    if not tail or "GREEN" not in tail[-1]:
        print(r.stdout[-1200:])
        print("ABORT 装置自证没全绿 —— 空结果只会是装置的错，不许继续")
        return False
    return True


# --------------------------------------------------------------------------
# 真实验收
# --------------------------------------------------------------------------
def run_experiment(model_path: str, out_path: Path, n_traces: int):
    import numpy as np
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    from harness import Measurement, ResidualInjector, attach, random_directions

    data_dir = ROOT / "datasets/aime_qwen3_1p7b_16k_fp16/aime"
    files = sorted(data_dir.glob("*.npz"))
    if not files:
        raise SystemExit("ABORT 找不到轨迹数据：%s" % data_dir)

    tok = AutoTokenizer.from_pretrained(model_path)
    model = AutoModelForCausalLM.from_pretrained(
        model_path, torch_dtype=torch.float16).eval().cuda()
    layers = model.model.layers          # Qwen3：embed_tokens 独立于 decoder layers
    print("层数 %d，注入层 %d" % (len(layers), LAYER))

    axis_dir = ROOT / "backend/examples/output/steering_vectors"
    axes = {}
    for a in AXES:
        p = axis_dir / ("%s.npy" % a)
        if p.exists():
            axes[a] = torch.from_numpy(np.load(p).astype(np.float32)).cuda()
        else:
            print("  跳过 %s（磁盘上没有 %s）" % (a, p.name))

    results = {"layer": LAYER, "alphas": ALPHAS, "n_random": N_RANDOM,
               "random_traces": N_RANDOM_TRACES, "axes": {}, "notes": []}
    sub = list(range(0, min(n_traces, len(files))))
    rnd_sub = sub[:N_RANDOM_TRACES]

    for k in sub:
        meta = json.loads((files[k].with_suffix(".json")).read_text())
        toks = [t["token"] for t in meta["tokens"]]
        ids = torch.tensor([tok.convert_tokens_to_ids(t) for t in toks],
                           device="cuda").unsqueeze(0)
        n_prompt = int(meta.get("n_prompt_tokens", 0) or 0)

        def fwd(injector):
            hd = []
            if injector is not None:
                hd.append(attach(model, layers, LAYER, injector))
            box = {}

            def rec(mod, _i, out):
                box["h"] = (out[0] if isinstance(out, tuple) else out).detach()
            hd.append(layers[LAYER].register_forward_hook(rec))
            with torch.no_grad():
                out = model(ids, output_hidden_states=True)
            for d in hd:
                d.remove()
            # logits[:, :-1] 预测 ids[:, 1:]；只算生成段
            return Measurement(logits=out.logits[0, n_prompt:-1].float(),
                               h_layer=box["h"][0, n_prompt:].float())

        base = fwd(None)
        for aname, v in axes.items():
            rec = {"base": None, "planted": [], "random": []}
            z = fwd(ResidualInjector(v, 0.0))
            rec["base"] = float((z.logits - base.logits).abs().max())
            for a in ALPHAS:
                m = fwd(ResidualInjector(v, a))
                rec["planted"].append({"alpha": a,
                                       "kl": float(torch.nn.functional.kl_div(
                                           m.logits.log_softmax(-1),
                                           base.logits.log_softmax(-1),
                                           log_target=True, reduction="mean"))})
            if k in rnd_sub:
                for i, r in enumerate(random_directions(
                        N_RANDOM, v.numel(), SEED + i)):
                    m = fwd(ResidualInjector(r, ALPHAS[-1]))
                    rec["random"].append(float(torch.nn.functional.kl_div(
                        m.logits.log_softmax(-1), base.logits.log_softmax(-1),
                        log_target=True, reduction="mean")))
            results["axes"].setdefault(aname, []).append(rec)
        print("轨迹 %d/%d 完成" % (k + 1, len(sub)))

    results["notes"].append(
        "α 是以该层 mean‖h‖ 为单位的无量纲倍数；跨方向可比。"
        "随机对照只在 %d 条子样本轨迹上跑，N=%d。"
        % (N_RANDOM_TRACES, N_RANDOM))
    results["notes"].append(
        "本实验只测**前向**的因果性（教师强制），不等于自由生成下行为改变。")
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=1))
    print("已写", out_path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None, help="Qwen3-1.7B 权重目录")
    ap.add_argument("--out", default=str(HERE / "intervention_qwen.json"))
    ap.add_argument("--traces", type=int, default=48)
    ap.add_argument("--preflight-only", action="store_true")
    a = ap.parse_args()

    missing, notes = preflight(a.model)
    print("== 前置条件 ==")
    for n in notes:
        print("  有 " + n)
    for m in missing:
        print("  缺 " + m)
    if missing:
        print("\nABORT 缺 %d 项前置条件。这个脚本**没有降级路径** —— "
              "缺算力就是不能跑，不许用 CPU 硬扛出一个假结果。" % len(missing))
        return 2
    if a.preflight_only:
        print("\n前置条件齐了。去掉 --preflight-only 即可开跑。")
        return 0

    print()
    if not run_selftest():
        return 3
    run_experiment(a.model, Path(a.out), a.traces)
    return 0


if __name__ == "__main__":
    sys.exit(main())
