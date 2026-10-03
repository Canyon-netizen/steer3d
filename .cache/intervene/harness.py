"""干预装置：沿一个方向往残差流里加东西，然后量它改变了什么。

这份代码是**唯一**的注入实现，被两处共用：

  1. `selftest.py`   —— 合成模型上跑，植入已知方向
  2. `intervene_qwen.py` —— 真 Qwen3-1.7B 上跑

共用是硬要求。自证如果验的是另一份注入代码，它证明不了真实验收用的那份。

## 三个容易被忽略、且都曾经坑过我的地方

**① α 必须以 mean‖h‖ 为单位，不能是绝对幅度。**
不同方向 ‖v‖ 差 2 倍以上（实测 41.2 / 49.9 / 58.5），同样 α 在不同方向上
根本不是同样的扰动。§4.6 已经因为注入层错位和在线 `1.18s` 口径踩过一次。
⇒ `alpha` 一律传**无量纲倍数**，实际注入量 = `alpha * mean_norm(h) * v̂`。

**② 必须在 α=0 上验证装置是恒等映射。**
hook 写错（挂错层、挂两次、忘了归一化）时，α=0 就会悄悄改变输出，
而所有"α 越大效果越强"的曲线照样漂亮。
⇒ 每次实验的第一格永远是 α=0，且断言它逐位复现基线。

**③ 没有同范数随机对照的干预实验一律不算数。**
本项目已经被这一条判死过一次：§4.4 的两条方向在换成同范数随机方向后
效果一样好，所以那些"漂亮"结果全是幅度效应。
⇒ `sweep()` 强制同时跑 `n_random` 条随机方向，**它们是输出的一部分，不是可选项**。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import torch


# --------------------------------------------------------------------------
# 注入 hook
# --------------------------------------------------------------------------
class ResidualInjector:
    """在某一层的残差流输出上加 `alpha * scale * v̂`。

    `scale` 是该层未扰动残差流各 token 的平均范数，这样 `alpha` 是无量纲的，
    跨方向、跨轨迹可比（见模块 docstring ①）。
    """

    def __init__(self, v: torch.Tensor, alpha: float):
        self.v = v / v.norm()
        self.alpha = float(alpha)
        self.active = self.alpha != 0.0
        self.scale: float | None = None   # 施加时用未扰动的 ‖h‖ 现算

    def __call__(self, h: torch.Tensor) -> torch.Tensor:
        if not self.active:
            return h
        # 现算 scale：必须用**未扰动**的范数，否则 α 会随扰动自己缩放
        if self.scale is None:
            self.scale = float(h.reshape(-1, h.shape[-1]).norm(dim=-1).mean())
        v = self.v.to(h.dtype).to(h.device)
        return h + (self.alpha * self.scale) * v


def attach(model, layers, layer: int, injector: ResidualInjector):
    """把 injector 挂到 `layers[layer]` 的输出上，返回一个 detach 函数。

    传一个**列表**而不是单个模块：Qwen 的 decoder layer 在不同版本里
    可能是 `model.model.layers` 或 `model.model.model.layers`，
    层级探测失败时宁可显式报错，也不要默默挂到错的地方。
    """
    if not layers:
        raise SystemExit("ABORT 没有拿到 layer 列表 —— 层级探测失败，不许猜")
    if not (0 <= layer < len(layers)):
        raise SystemExit("ABORT 注入层 %d 越界（只有 %d 层）" % (layer, len(layers)))
    blk = layers[layer]
    h = injector

    def hook(_mod, _inp, out):
        t = out[0] if isinstance(out, tuple) else out
        return (h(t),) + tuple(out[1:]) if isinstance(out, tuple) else h(t)

    return blk.register_forward_hook(hook)


# --------------------------------------------------------------------------
# 读出
# --------------------------------------------------------------------------
@dataclass
class Measurement:
    """一次前向里量到的东西。所有字段都是**对照**用的，不是结论。"""
    logits: torch.Tensor | None = None      # [T, V] 下一 token 的 logits
    h_layer: torch.Tensor | None = None     # [T, D] 注入层的残差流
    kl: float | None = None                 # vs 基线的 KL(base ‖ pert)
    cos_base_pert: float | None = None      # cos(base ‖ pert)，纯幅度
    logit_max_shift: float | None = None    # 变化最大的那个 logit 位移


def measure_against_base(base: Measurement, pert: Measurement) -> Measurement:
    """把一次扰动前向的结果折算成「相对基线变了多少」。

    ⚠ **cos 与 KL 都要报**。只看 KL 会被幅度骗：一个纯放大的扰动
    就能把 KL 顶上去，但它不改变任何语义。只看 cos 又会漏掉重排。
    真正想看的是「在 KL 涨的同时，读出方向上的投影有没有**专一**地涨」。
    """
    m = Measurement(logits=pert.logits, h_layer=pert.h_layer)
    if base.logits is None or pert.logits is None:
        return m
    lb = torch.log_softmax(base.logits.float(), dim=-1)
    lp = torch.log_softmax(pert.logits.float(), dim=-1)
    pb, pp = lb.exp(), lp.exp()
    m.kl = float((pb * (lb - lp)).sum(-1).mean())
    m.logit_max_shift = float((pert.logits.float() - base.logits.float()).abs().max())
    if base.h_layer is not None and pert.h_layer is not None:
        a = base.h_layer.reshape(-1, base.h_layer.shape[-1])
        b = pert.h_layer.reshape(-1, pert.h_layer.shape[-1])
        m.cos_base_pert = float(torch.nn.functional.cosine_similarity(
            a[0:1], b[0:1], dim=-1).item()) if a.shape == b.shape else None
    return m


# --------------------------------------------------------------------------
# 随机对照
# --------------------------------------------------------------------------
def random_directions(n: int, dim: int, seed: int) -> list[torch.Tensor]:
    """同范数随机方向。范数在 `sweep` 里被归一化掉，所以这里只管方向。

    ⚠ 必须**每个实验重新固定 seed**：跨条件复用同一组随机方向，
    才能把「方向之间的差」与「随机抽样的噪声」分开。
    """
    g = torch.Generator().manual_seed(seed)
    out = []
    for _ in range(n):
        x = torch.randn(dim, generator=g)
        out.append(x / x.norm())
    return out


# --------------------------------------------------------------------------
# 扫描
# --------------------------------------------------------------------------
@dataclass
class SweepPoint:
    alpha: float
    which: str            # "planted" / "random_0" / ...
    kl: float
    rho: float | None     # 在读出方向上的投影均值（越大越"沿这条方向走了"）
    logit_max_shift: float
    extra: dict = field(default_factory=dict)


def rho_on_direction(h: torch.Tensor, y: torch.Tensor, w: torch.Tensor) -> float:
    """把残差流投到方向 `w` 上，与 y 算相关。

    读出与 §4.6/§4.10 完全同一套口径（`corr(h·ŵ, y)`），
    这样注入实验的数字可以和前面的可读性数字**放在一张表里比**。
    """
    import numpy as np
    proj = (h.float() @ (w / w.norm()).float()).cpu().numpy()
    yv = y.float().cpu().numpy()
    if proj.size < 3 or yv.std() == 0 or proj.std() == 0:
        return float("nan")
    return float(np.corrcoef(proj, yv)[0, 1])


def run_sweep(forward_fn, alphas, v, n_random, readout_w, seed,
              y_fn=None) -> list[SweepPoint]:
    """跑一整条 α 曲线，**强制带上** n_random 条同范数随机方向。

    `forward_fn(injector, label) -> Measurement`，把注入器交给调用方去挂。
    `readout_w` 是读出方向（用来算 rho）；`y_fn(k) -> 目标标签序列` 可为 None。
    """
    pts: list[SweepPoint] = []
    base = forward_fn(None, "base")
    # ① α=0 必须恒等：这是装置自检，不是结果
    zero = forward_fn(ResidualInjector(v, 0.0), "alpha0")
    zk = measure_against_base(base, zero)
    pts.append(SweepPoint(0.0, "planted", zk.kl or 0.0, None, zk.logit_max_shift or 0.0,
                          extra={"identity_max_abs_diff":
                                 float((zero.logits - base.logits).abs().max())}))
    for a in alphas:
        inj = ResidualInjector(v, a)
        m = forward_fn(inj, f"alpha={a}")
        mm = measure_against_base(base, m)
        rho = None
        if readout_w is not None and m.h_layer is not None and y_fn is not None:
            rho = rho_on_direction(m.h_layer, y_fn(), readout_w)
        pts.append(SweepPoint(a, "planted", mm.kl or 0.0, rho,
                              mm.logit_max_shift or 0.0))
    # ② 同范数随机对照。**这是与"方向"有关的一切结论的基准线。**
    for i, r in enumerate(random_directions(n_random, v.numel(), seed + i)):
        for a in alphas:
            inj = ResidualInjector(r, a)
            m = forward_fn(inj, f"random{i}={a}")
            mm = measure_against_base(base, m)
            rho = None
            if readout_w is not None and m.h_layer is not None and y_fn is not None:
                rho = rho_on_direction(m.h_layer, y_fn(), readout_w)
            pts.append(SweepPoint(a, f"random_{i}", mm.kl or 0.0, rho,
                                  mm.logit_max_shift or 0.0))
    return pts
