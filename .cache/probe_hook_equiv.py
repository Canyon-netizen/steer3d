#!/usr/bin/env python3
"""证明两套注入机制打在**同一个点**（层栈上）—— 结论：EQUIV。

## 它回答什么问题

LTV 的阈值表由 `.cache/xcheck/probe_ltv.py` 测出，它这样注入：

    layers[LAYER-1].register_forward_hook(hook)   # forward hook
    hook 里 hs[b, pos, :] = clean_res[b] + 扰动     # 替换**单点**

而生成侧 `backend/examples/run_intervention.py` 的 `ResidualSteerer` 这样注入：

    blocks[layer].register_forward_pre_hook(...)   # **pre** hook
    hook 里 x + vector                              # 加到**整段**

光看下标 `LAYER-1` 与 `layer` 像差一层。这直接决定「LTV 已测的 alpha* 阈值
能不能搬到生成侧」，也就是 G-c（注入后生成，测名字是否预测行为）能不能做。
**所以不能靠推理下结论，必须跑出来。**

## 三条判据，缺一条整份结果作废

1. **装置有效性**：扰动必须真的改变了 logits。
   否则 `A == B` 恒真（两边都等于基线），结论毫无意义。
   第一版把权重清零想让痕迹「一目了然」，结果每层输出恒为 0 ——
   恰恰因为什么都没发生，两种机制「相等」。**退化的装置会报出正确答案。**
2. **作用域对齐后再比**：A 只扰动 POS，B 注入整段。**作用域不同就不是同一个
   操作**，直接比全张量必然不等价。⇒ 把 B 的向量也限制成只在 POS 非零。
   仍不等价的话才是真的不等价。
3. **阴性对照**：pre-hook 打在 `layers[LAYER-1]`（真少一层）必须与 A 不同。
   若它也等于 A，说明这套装置分不出层号，是无效的。

## 实测结论（transformers 4.57.6 / torch 2.8.0，随机初始化 4 层 Qwen3）

    A（forward hook layers[LAYER-1]）与 B（pre-hook layers[LAYER]）
      在只扰动 POS 时：logits 逐位相同（最大差 0.0），
      output_hidden_states **逐层全等**；
      且与 clean 的 logits 最大差 0.012（扰动确实生效）。
    阴性对照（pre-hook layers[LAYER-1]）：与 A 不同（最大差 1.02e-04）。

⇒ **同一个点**。`LAYER-1` 与 `layer` 看起来差一层，是把 forward hook 的
「改输出」与 pre-hook 的「改输入」当成同一种下标比较造成的。

## 但 alpha 的**单位**不通用（务必读这一段）

同点 ≠ 同尺度。两条路对 α 的定标不同：

- `probe_ltv.py`：`sigma = hidden_states[LAYER][0].float().std()`
  （**整段前缀**在该层的 std），注入 `clean_res + α·sigma·v̂`。
- `reg.scaled(name, strength, layer)`：`strength × layer_rms(layer)`
  （registry 自己实测的**该层** RMS）。

两者不是同一个统计量。⇒ **LTV 的 α 值不能直接喂给 `reg.scaled`。**
G-c 若要沿用 LTV 的 α，必须**照抄 probe_ltv 的 σ 定义**，绕开 `scaled`。

用法:
    PYTHONPATH=.cache/pylibs python3 .cache/probe_hook_equiv.py
"""
import torch
from transformers import Qwen3Config, Qwen3ForCausalLM

LAYER = 2
POS = 3
T = 6
HID = 64
N_LAYERS = 4


def build():
    torch.manual_seed(1234)
    cfg = Qwen3Config(
        vocab_size=97, hidden_size=HID, intermediate_size=128,
        num_hidden_layers=N_LAYERS, num_attention_heads=4, num_key_value_heads=2,
        head_dim=16, max_position_embeddings=64, tie_word_embeddings=False,
    )
    m = Qwen3ForCausalLM(cfg).eval().to(torch.float32)
    for p in m.parameters():
        torch.nn.init.normal_(p, std=0.02)   # ⚠ 不清零，见「装置有效性」
    return m


def _fwd(m, ids):
    with torch.no_grad():
        o = m(ids, output_hidden_states=True)
        return o.logits, o.hidden_states


def splice_hook(m, ids, d):
    """probe_ltv.py 的机制。注意替换成的是 **clean + d**（它算的是
    `V[b] = clean_res + a * sigma * vhat`），不是裸 d。"""
    def hook(_m, _i, o):
        hs = (o[0] if isinstance(o, tuple) else o).clone()
        hs[0, POS, :] = hs[0, POS, :] + d
        return ((hs,) + tuple(o[1:])) if isinstance(o, tuple) else hs
    h = m.model.layers[LAYER - 1].register_forward_hook(hook)
    try:
        return _fwd(m, ids)
    finally:
        h.remove()


def residual_pre_hook(m, ids, vec, layer):
    """ResidualSteerer 的机制。`vec` 的形状 (T, HID)，作用域由它决定。"""
    def hook(_mo, inp):
        return ((inp[0] + vec,) + tuple(inp[1:]))
    h = m.model.layers[layer].register_forward_pre_hook(hook)
    try:
        return _fwd(m, ids)
    finally:
        h.remove()


def main():
    m = build()
    ids = torch.randint(0, 97, (1, T))
    base_lg, _ = _fwd(m, ids)
    torch.manual_seed(7)
    d = torch.randn(HID)

    d_pos = torch.zeros(T, HID)          # 只在 POS 上非零 ⇒ 作用域与 A 对齐
    d_pos[POS] = d

    a_lg, a_hs = splice_hook(m, ids, d)
    b_lg, b_hs = residual_pre_hook(m, ids, d_pos, LAYER)       # 同点
    c_lg, _ = residual_pre_hook(m, ids, d_pos, LAYER - 1)      # 阴性对照

    signal = float((a_lg - base_lg).abs().max())
    print(f"LAYER={LAYER} POS={POS} hidden_size={HID} layers={N_LAYERS}")
    print(f"  扰动 ‖d‖ = {float(d.norm()):.6f}")

    # ① 装置有效性
    a_trace = signal > 0
    print(f"  ① 扰动确实改变了 logits：A 与 clean 最大差 = {signal:.6g}"
          f" ⇒ 装置{'有效' if a_trace else '**退化**（下面所有比较都是恒真）'}")
    if not a_trace:
        print("RESULT DEGENERATE")
        return 1

    # ② 作用域对齐后，A 与 B 是否逐位相同
    same_lg = torch.equal(a_lg, b_lg)
    diff_hs = [k for k in range(len(a_hs))
               if not torch.equal(a_hs[k], b_hs[k])]
    print(f"  ② 作用域对齐后 A 与 B 的 logits 逐位相同: {same_lg}"
          f"（最大差 {float((a_lg - b_lg).abs().max()):.3e}）")
    print(f"     output_hidden_states 逐层全等: {not diff_hs}"
          + (f"；不等的下标 {diff_hs}" if diff_hs else ""))

    # ③ 阴性对照
    c_diff = not torch.equal(a_lg, c_lg)
    c_margin = float((a_lg - c_lg).abs().max())
    print(f"  ③ 阴性对照（pre-hook 在 layers[{LAYER-1}]）与 A 不同: {c_diff}"
          f"（最大差 {c_margin:.3e}；信号 {signal:.3e}）")

    ok = a_trace and same_lg and (not diff_hs) and c_diff
    if ok:
        print("  ⇒ **同一个点**。`LAYER-1` 与 `layer` 看起来差一层，"
              "是把 forward hook 的「改输出」与 pre-hook 的「改输入」"
              "当成同一种下标比出来的错觉。")
        print("  ⇒ G-c 的「差一层」阻塞点不成立。")
    else:
        print("  ⇒ 不等价或装置不足以下结论；G-c 必须先统一注入点的约定。")
    print("⚠ 同点 ≠ 同尺度：alpha 的单位两路不同（见本文件 docstring）。")
    print("RESULT %s" % ("EQUIV" if ok else "NOT_EQUIV"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())