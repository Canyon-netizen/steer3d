#!/usr/bin/env python3
"""装置自证：在**答案已知**的合成模型上跑同一份注入代码。

这一支不是为拿科研结论，是为了让「Qwen 上跑出来没效果」这句话**有意义**。
装置在这里都过不了的话，Qwen 上的空结果就只能是装置的错。

## 必须逐条对上的真值

| 编号 | 真值 | 过了说明 |
|---|---|---|
| S1 | α=0 逐位复现基线（max diff 恰为 0） | hook 没有偷偷改变前向 |
| S2 | 第 0 层注入 `+α·e₀` ⇒ 概念 logit 随 α 严格单调 | 注入真的进了残差流 |
| S2b | Δlogit 精确等于 `α × mean‖h₀‖ × 增益`，其中增益由 **autograd 独立算出** | 幅度口径正确、且可加 |
| S3 | 20 条同范数随机方向的效果远小于植入方向 | 效果来自**方向**不是幅度 |
| S4 | 同一 α 注入第 0 / 第 1 层，效果之比 = 该通路的增益比 | 层号真的生效，不是摆设 |
| S5 | 从残差流恢复的读出方向与 `e₀` 的相关 ≈ 1 | 读出口径与 §4.6/§4.10 一致 |
| S6 | 绕过 `mean‖h‖` 归一化会改变注入量 ⇒ 口径差异可被测出 | 相对幅度不是隐形的 |

**每条判据都必须能变红** —— 收尾会跑一遍「把装置改坏」的变异。
"""
import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).parent))
from harness import (Measurement, ResidualInjector, attach,  # noqa: E402
                     random_directions, rho_on_direction)
from synth_model import (CONCEPT_COORD, CONCEPT_LOGIT, D, GAIN,  # noqa: E402
                         Synth, make_batch)

ALPHAS = [-4.0, -2.0, -1.0, 1.0, 2.0, 4.0]
results = []


def check(name, ok, detail):
    results.append({"name": name, "ok": bool(ok)})
    print("[%s] %s: %s" % ("PASS" if ok else "FAIL", name, detail))


def main():
    torch.manual_seed(0)
    model = Synth()
    model.eval()
    x = make_batch()
    v = model.planted_direction

    def forward_fn(injector, label, inject_layer=0):
        """注入只走 hook 这一条路 —— 与 Qwen 完全同形。"""
        hd = []
        if injector is not None:
            hd.append(attach(model, model.layers, inject_layer, injector))
        with torch.no_grad():
            logits, h = model(x)
        for d in hd:
            d.remove()
        return Measurement(logits=logits, h_layer=h)

    base = forward_fn(None, "base")
    l0 = float(base.logits[:, CONCEPT_LOGIT].mean())

    # ---------------- S1 α=0 恒等 ----------------
    z = forward_fn(ResidualInjector(v, 0.0), "a0")
    d0 = float((z.logits - base.logits).abs().max())
    check("S1 α=0 逐位复现基线（hook 无副作用）", d0 == 0.0,
          "最大绝对差 %.3e" % d0)

    # ---------------- 注入层的 ‖h‖ ----------------
    # ⚠⚠ **必须独立算**。第一版是从注入器里把 `inj.scale` 读回来用的，
    # 而注入器自己就是待检验的对象 —— 那等于「拿我传给它的值断言它自己」：
    # 把 scale 固定成 1.0（变异 X4）时，断言跟着一起错，于是 S2b 照样绿。
    # 代价是多挂一个**只记录不修改**的 hook。值不值得？值得。

    def capture(layer):
        box = {}
        def f(mod, _i, out):
            box["h"] = (out[0] if isinstance(out, tuple) else out).detach()
        d = model.layers[layer].register_forward_hook(f)
        with torch.no_grad():
            model(x)
        d.remove()
        return float(box["h"].reshape(-1, D).norm(dim=-1).mean())

    scale0 = capture(0)
    scale1 = capture(1)

    # ---------------- autograd 独立算增益 ----------------
    # 不靠手推，直接问 autograd：在第 L 层的残差流 COORD 上加 eps，
    # logit[CONCEPT_LOGIT].mean() 变化多少。
    # ⚠ 口径：对 **eps** 求导就是「所有 token 一起加 eps」的总敏感度。
    #   改成对单个 token 的 h[t] 求导会差一个 T 倍 —— 这个坑第一版踩过。
    onehot = torch.zeros(D)
    onehot[CONCEPT_COORD] = 1.0
    for p in model.parameters():
        p.requires_grad_(False)
    gain = []
    for layer in (0, 1):
        eps = torch.zeros(1, requires_grad=True)
        h = model.emb(x)
        for i, blk in enumerate(model.layers):
            h = blk(h)
            if i == layer:
                h = h + eps * onehot
        lg = model.head(h)[:, CONCEPT_LOGIT].mean()
        gain.append(float(torch.autograd.grad(lg, eps)[0]))
    gain0, gain1 = gain
    for p in model.parameters():
        p.requires_grad_(True)

    # ---------------- S2 单调 + 严格成正比 ----------------
    # ⚠ 只查「单调」太弱：乘性注入 `h*(1+α)` 同样单调（变异 X6 就是），
    #   照样能骗过。加性注入的真正性质是 **Δ 严格正比于 α**（过原点）。
    obs = []
    for a in ALPHAS:
        m = forward_fn(ResidualInjector(v, a), "a%s" % a)
        obs.append(float(m.logits[:, CONCEPT_LOGIT].mean()) - l0)
    mono = all(obs[i] < obs[i + 1] for i in range(len(obs) - 1))
    prop = all(abs(obs[i] / ALPHAS[i] - obs[-1] / ALPHAS[-1]) < 1e-4
               for i in range(len(obs)))
    check("S2 第 0 层注入 +α·e₀ ⇒ 概念 logit 单调且严格正比于 α", mono and prop,
          "Δ= %s  （Δ/α= %s）"
          % (", ".join("%+.4f" % o for o in obs),
             ", ".join("%.4f" % (o / a) for o, a in zip(obs, ALPHAS))))

    # ---------------- S2b 幅度口径 ----------------
    pred = [a * scale0 * gain0 for a in ALPHAS]
    err = max(abs(o - p) / max(abs(p), 1e-12) for o, p in zip(obs, pred))
    check("S2b Δlogit 精确等于 α × mean‖h₀‖ × autograd 增益", err < 1e-5,
          "mean‖h₀‖=%.5f  gain₀=%.4f  最大相对误差 %.2e" % (scale0, gain0, err))

    # ---------------- S3 同范数随机对照 ----------------
    # N=200 走项目里「与 ≥200 个同长度随机方向比」那条纪律。
    # 判据用的是**最坏**那一条随机方向：植入方向必须打赢**全部** 200 条，
    # 只打赢中位数等于没打赢（这正是 §4.4 那次翻车的形状）。
    planted = abs(obs[-1]) - abs(obs[2])            # |α=4| − |α=1|
    eff = []
    for r in random_directions(200, D, seed=101):
        e = []
        for a in (1.0, 4.0):
            m = forward_fn(ResidualInjector(r, a), "r")
            e.append(abs(float(m.logits[:, CONCEPT_LOGIT].mean()) - l0))
        eff.append(abs(e[1] - e[0]))
    eff_sorted = sorted(eff)
    worst, med = eff_sorted[-1], eff_sorted[len(eff_sorted) // 2]
    check("S3 植入方向打赢 200 条同范数随机方向的**最坏一条**",
          worst < abs(planted),
          "植入 %.4f  随机中位 %.4f 随机最坏 %.4f  最坏/植入 = %.2f"
          % (planted, med, worst, worst / max(abs(planted), 1e-12)))

    # ---------------- S4 层号生效 ----------------
    eL0 = abs(float(forward_fn(ResidualInjector(v, 4.0), "L0").logits
                    [:, CONCEPT_LOGIT].mean()) - l0)
    eL1 = abs(float(forward_fn(ResidualInjector(v, 4.0), "L1",
                               inject_layer=1).logits
                    [:, CONCEPT_LOGIT].mean()) - l0)
    pred0, pred1 = 4.0 * scale0 * gain0, 4.0 * scale1 * gain1
    r0 = abs(eL0 - pred0) / pred0
    r1 = abs(eL1 - pred1) / pred1
    check("S4 两个层号各自命中 autograd 算出的增益（层号不是摆设）",
          r0 < 1e-5 and r1 < 1e-5,
          "L0 实测 %.5f / 解析 %.5f (rel %.1e)   L1 实测 %.5f / 解析 %.5f (rel %.1e)"
          % (eL0, pred0, r0, eL1, pred1, r1))
    # ⚠ 效果之比 = (gain0·scale0)/(gain1·scale1)，**不是** gain0/gain1。
    #   两层残差的 ‖h‖ 不同（实测 %.5f vs %.5f），漏掉 scale 就会对不上 ——
    #   我第一版就是漏了它，印出「实测比 1.37 / 增益比 2.0」这种自相矛盾的行。
    pred_ratio = (gain0 * scale0) / (gain1 * scale1)
    meas_ratio = eL0 / max(eL1, 1e-12)
    check("S4b L0/L1 效果之比 = (增益 × 该层 ‖h‖) 之比",
          abs(meas_ratio - pred_ratio) / pred_ratio < 1e-5,
          "实测比 %.6f  解析比 %.6f  (‖h₀‖=%.5f ‖h₁‖=%.5f gain %.2f/%.2f)"
          % (meas_ratio, pred_ratio, scale0, scale1, gain0, gain1))

    # ---------------- S5 读出方向可恢复 ----------------
    y = (x[:, 0] > 0.5).float()
    r = rho_on_direction(base.h_layer, y, v)
    check("S5 从残差流恢复的读出方向与 e₀ 的相关 ≈ 1", abs(r) > 0.99,
          "rho(h·e₀, y) = %.6f" % r)

    # ---------------- S6 绕过 ‖h‖ 归一化会改变注入量 ----------------
    # 真值不是「差好几倍」，而是**恰好差一个 mean‖h_layer‖ 倍**：
    #   相对幅度 α=1 ⇒ Δ = 1·scale0·gain0
    #   绝对幅度 α=1 ⇒ Δ = 1·1·gain0
    # 我第一版在这里写了个「> 3×」的拍脑袋阈值，实测只差 1.08 倍，
    # 于是判红 —— 判红的是阈值不是性质。正确判据是这个恒等式。
    class NoScale(ResidualInjector):
        def __call__(self, h):
            if not self.active:
                return h
            return h + self.alpha * (self.v.to(h.dtype).to(h.device))

    n1 = abs(float(forward_fn(NoScale(v, 1.0), "n1").logits
                [:, CONCEPT_LOGIT].mean()) - l0)
    p1 = abs(obs[ALPHAS.index(1.0)])
    ratio = p1 / max(n1, 1e-12)
    check("S6 相对幅度与绝对幅度之比恰为 mean‖h_layer‖（口径差异可被测出）",
          abs(ratio - scale0) / scale0 < 1e-5 and scale0 > 1.0,
          "相对 %.4f / 绝对 %.4f = %.6f   mean‖h₀‖ = %.6f"
          % (p1, n1, ratio, scale0))
    print("     注：合成模型刻意做小（mean‖h₀‖≈%.2f）；Qwen 残差流的范数是几十到上百，"
          "同一个 α 在两套口径下差得更远。\n     ⇒ 口径不统一时跨方向比较会完全错位，"
          "这正是 §4.6「注入层错位 + 在线 1.18s」踩过的坑。" % scale0)

    # ---------------- S7 扰动严格沿 v（横向分量必须为 0）----------------
    # ⚠ S2 的「正比于 α」**抓不住**乘性注入：在本模型里概念坐标在 off 段
    #   严格为 0，所以 `h*(1+α)` 的 Δ 也恰好正比于 α（实测 X6 下 S2 照样绿）。
    #   真正能分开两者的性质只有一个：**扰动严格沿 v，横向分量为零**。
    def h_with(injector, layer):
        box = {}

        def f(mod, _i, out):
            box["h"] = (out[0] if isinstance(out, tuple) else out).detach()
        pre = []
        if injector is not None:
            pre.append(attach(model, model.layers, layer, injector))
        d = model.layers[layer].register_forward_hook(f)   # 后注册 ⇒ 看到扰动后的值
        with torch.no_grad():
            model(x)
        d.remove()
        for hh in pre:
            hh.remove()
        return box["h"].clone()

    hb = h_with(None, 0)
    hp = h_with(ResidualInjector(v, 4.0), 0)
    delta = (hp - hb).reshape(-1, D)
    u = (v / v.norm())
    along = (delta @ u).unsqueeze(1) * u.unsqueeze(0)
    ortho = (delta - along).norm()
    ratio_ortho = float(ortho / max(delta.norm(), 1e-12))
    check("S7 扰动严格沿 v，横向分量为 0（乘性注入会立刻被抓）",
          ratio_ortho < 1e-6,
          "‖Δh‖=%.4f  ‖横向‖=%.3e  相对 %.2e" % (float(delta.norm()), float(ortho),
                                              ratio_ortho))

    failed = [r for r in results if not r["ok"]]
    print("\nRESULT selftest  %s  %d/%d 条通过"
          % ("RED" if failed else "GREEN", len(results) - len(failed), len(results)))
    for f in failed:
        print("   [FAIL] " + f["name"])
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
