#!/usr/bin/env python3
"""决定性实测：往第 L 层残差里注入一个向量，模型预测的 token 到底变不变。

为什么单独写这个脚本：回放路径已经证明「注入不改 token」（verify_real_replay
的 D13）。但那是因为回放根本不跑推理。要回答「干预下模型行为如何变化」，
必须有一次**真前向传播**：同一段前缀、同一组权重、只把注入开关翻一下，
看下一步的分布怎么动。

这不是 benchmark，是**可行性闸门**。它只回答一个问题：这条路通不通。
通了才值得把它接进后端；不通就省下接线的功夫。

用法:
  PYTHONPATH=.cache/pylibs python3 .cache/xcheck/probe_live_inject.py
  PROMPT="..."  LAYER=14  NORM=2.0  STEPS=8
"""
import json
import os
import sys
import time

# 本文件在 <repo>/.cache/xcheck/ 下，要上溯三级才到仓库根。
# 少一级会让 REPO 变成 <repo>/.cache，下面拼出来的路径全错。
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL = os.environ.get(
    "PROBE_MODEL", os.path.join(REPO, "datasets", "models", "Qwen3-1.7B")
)
LAYER = int(os.environ.get("LAYER", "14"))
NORM = float(os.environ.get("NORM", "2.0"))
STEPS = int(os.environ.get("STEPS", "8"))
PROMPT = os.environ.get(
    "PROMPT",
    "Two skaters are on a frozen lake. One is 5 kg, the other 7 kg. "
    "They push off and the heavier one moves at 1.2 m/s. "
    "How fast does the lighter one move? Answer with a number only.",
)
VEC_PATH = os.environ.get("PROBE_VEC", "")
# 用不用 chat 模板。这不是装饰开关：
# 不套模板时 Qwen3 把 AIME 题干当**纯文本续写**，实测生成的是
# " | Study.com\nScience Physics" —— 它根本没在答题。
# 那样测到的阈值是**离分布上下文**下的阈值，不能当成「模型解题时的行为阈值」。
USE_CHAT = os.environ.get("USE_CHAT", "1") == "1"

log = lambda *a: print(*a, flush=True)


def fail(msg, code=2):
    log(f"装置故障：{msg}")
    sys.exit(code)


def main():
    import numpy as np
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    t0 = time.time()
    log(f"模型：{MODEL}")
    if not os.path.isdir(MODEL):
        fail(f"模型目录不存在 {MODEL}")
    wsum = sum(
        os.path.getsize(os.path.join(MODEL, f)) for f in os.listdir(MODEL)
        if f.endswith(".safetensors")
    )
    log(f"权重 {wsum/1e9:.2f} GB")

    tok = AutoTokenizer.from_pretrained(MODEL)
    # 套 chat 模板，并把它**冻结**成一段普通文本前缀。
    # 之后每一步都只在这段前缀后面追加 token 字符串，所以上下文分布
    # 始终是「模型自己会说的话」——与它是否在解题无关，但至少在分布内。
    # 用独立的 PFX 而不是改写模块级的 PROMPT：在 main() 里给 PROMPT 赋值
    # 会让它整体变成局部变量，模板分支一旦没走到，后面读它就 UnboundLocalError。
    PFX = PROMPT
    if USE_CHAT and getattr(tok, "chat_template", None):
        PFX = tok.apply_chat_template(
            [{"role": "user", "content": PROMPT}],
            tokenize=False, add_generation_prompt=True,
        )
        log("已套 chat 模板（否则模型会把题干当纯文本续写，不在分布内）")
    else:
        log("⚠ 未套 chat 模板：阈值是在**离分布**上下文下测的，不能当行为阈值用")
    try:
        model = AutoModelForCausalLM.from_pretrained(
            MODEL, torch_dtype=torch.bfloat16, low_cpu_mem_usage=True
        )
    except TypeError:
        # 老版 transformers 没有 low_cpu_mem_usage
        model = AutoModelForCausalLM.from_pretrained(MODEL, torch_dtype=torch.bfloat16)
    model.eval()
    log(f"载入完成 {time.time()-t0:.1f}s  "
        f"d_model={model.config.hidden_size} layers={model.config.num_hidden_layers}")

    n_layers = model.config.num_hidden_layers
    if not (0 <= LAYER < n_layers):
        fail(f"LAYER={LAYER} 越界（模型只有 {n_layers} 层）")

    # ── 干预向量从哪来 ──────────────────────────────────────────────
    # 用 registry.scaled() —— 那是**页面上真正注进去的那个向量**
    # （强度按该层残差 RMS 定标）。读不到才退化，且退化时必须说明退化。
    # 绝不用随机向量：随机方向测的是噪声，不是「干预有没有用」。
    unit = None
    src = ""
    direction = os.environ.get("DIRECTION", "reasoning_deep")
    if VEC_PATH:
        arr = json.load(open(VEC_PATH))
        unit = arr.get("unit") if isinstance(arr, dict) else arr
        src = f"显式文件 {VEC_PATH}"
    if unit is None:
        try:
            sys.path.insert(0, os.path.join(REPO, "backend"))
            from core.steering import get_registry
            reg = get_registry()
            if reg.names:
                direction = direction if direction in reg.names else reg.names[0]
                v = reg.scaled(direction, 1.0, LAYER)   # 1.0 强度拿单位向量
                if v is not None:
                    unit = np.asarray(v, dtype="float32").reshape(-1).tolist()
                    src = (f"steering registry 的「{direction}」经 scaled() "
                           f"（与页面同一个来源）")
            else:
                log("registry 里没有方向")
        except Exception as e:
            log(f"registry 不可用（{type(e).__name__}: {e}），退化到 PCA 方向")
    if unit is None:
        ids = tok(PFX, return_tensors="pt")
        with torch.no_grad():
            hs = model(**ids, output_hidden_states=True).hidden_states[LAYER][0]
        u = torch.linalg.svd(hs.float(), full_matrices=False).Vh[0]
        unit = u.tolist()
        src = f"第 {LAYER} 层残差的第一主成分（**退化方向，不是解释性方向**）"
    log(f"干预向量来源：{src}")

    u = torch.tensor(np.asarray(unit, dtype="float32"))
    if u.shape[0] != model.config.hidden_size:
        fail(f"向量维度 {u.shape[0]} != d_model {model.config.hidden_size}")
    # 注入量按「该层残差自身的尺度」定标，否则同一个 ‖v‖ 在不同层意义完全不同
    ids = tok(PFX, return_tensors="pt")
    with torch.no_grad():
        base_hs = model(**ids, output_hidden_states=True).hidden_states[LAYER][0]
    resid_scale = float(base_hs.float().std())
    udir = u / (u.norm() + 1e-9)
    log(f"残差尺度 std={resid_scale:.3f}   方向：{src}")

    # ── 两段式：先无注入生成，再在**同一前缀**上比两遍分布 ─────────
    #
    # 为什么不直接比两次自由生成：一旦 token 分叉，两边的上下文就不同了，
    # 后面每一步的 logit 都不可比，测到的会是「上下文不同」而不是「注入不同」。
    # 教师强制把两臂钉在同一条前缀上，每一步的差就只归因于注入。
    decoder_layers = model.model.layers

    def hook_fn(delta):
        def hook(_m, _i, outp):
            hs = outp[0] if isinstance(outp, tuple) else outp
            hs = hs.clone()
            hs[:, -1, :] = hs[:, -1, :] + delta.to(hs.dtype)
            return ((hs,) + tuple(outp[1:])) if isinstance(outp, tuple) else hs
        return hook

    def next_logits(cur: str, delta):
        handle = (decoder_layers[LAYER].register_forward_hook(hook_fn(delta))
                  if delta is not None else None)
        assert (handle is not None) == (delta is not None), "hook 装配与 delta 不一致"
        try:
            enc = tok(cur, return_tensors="pt")
            with torch.no_grad():
                return model(**enc).logits[0, -1].float()
        finally:
            if handle is not None:
                handle.remove()

    # 第一段：无注入，自由生成 STEPS 步，得到所有强度共用的前缀
    t0 = time.time()
    prefix, ctrl_toks = PFX, []
    for i in range(STEPS):
        lg = next_logits(prefix, None)
        ctrl_toks.append(tok.decode([int(torch.argmax(lg))]))
        prefix = prefix + ctrl_toks[-1]
    log(f"对照生成 {STEPS} 步 {time.time()-t0:.1f}s  → {''.join(ctrl_toks)!r}")

    # 第二段：在同一前缀上，扫若干强度逐步比两条分布
    def measure(mult: float):
        delta = udir * (mult * resid_scale)
        rows = []
        pre = PFX
        for i, want in enumerate(ctrl_toks):
            a = next_logits(pre, None)
            b = next_logits(pre, delta)
            da, db = torch.log_softmax(a, -1), torch.log_softmax(b, -1)
            kl = float((da.exp() * (da - db)).sum())
            # 决胜间距印 4 位小数：0.001 级的间距在 :.3f 下会印成 0.000，
            # 于是「几乎翻盘」和「差得很远」在纸面上长得一模一样。
            ta, tb = torch.topk(a, 2), torch.topk(b, 2)
            rows.append({
                "step": i,
                "token_ctrl": tok.decode([int(ta.indices[0])]),
                "token_inj": tok.decode([int(tb.indices[0])]),
                "flipped": int(ta.indices[0]) != int(tb.indices[0]),
                "max_abs_dlogit": float((b - a).abs().max()),
                "kl": kl,
                "margin_ctrl": float(ta.values[0] - ta.values[1]),
                "margin_inj": float(tb.values[0] - tb.values[1]),
                "inj_top5": [[tok.decode([int(j)]), round(float(v), 3)]
                             for v, j in zip(tb.values, tb.indices)],
            })
            pre = pre + want
        return rows, float(delta.norm())

    strengths = [float(x) for x in
                 os.environ.get("SWEEP", str(NORM)).split(",")]
    log(f"\n扫 {len(strengths)} 个强度 × {STEPS} 步 × 2 次前向")
    scans = []
    t0 = time.time()
    for m in strengths:
        rows, dn = measure(m)
        scans.append({"mult": m, "injected_norm": dn, "rows": rows})
        log(f"  {m:>5}x  ‖δ‖={dn:>7.2f}  翻盘 "
            f"{sum(r['flipped'] for r in rows)}/{len(rows)}  "
            f"最大Δlogit={max(r['max_abs_dlogit'] for r in rows):>7.3f}  "
            f"最大KL={max(r['kl'] for r in rows):>7.4f}  "
            f"最小注入后间距={min(r['margin_inj'] for r in rows):>7.4f}")
    log(f"  扫描共 {time.time()-t0:.1f}s")

    # ── 判决 ──────────────────────────────────────────────────────
    all_rows = [r for s in scans for r in s["rows"]]
    moved = [r for r in all_rows if r["max_abs_dlogit"] > 1e-6]
    any_flip = [r for r in all_rows if r["flipped"]]

    # ── 逐步阈值**夹逼**，不是「最小翻盘强度」 ──────────────────────
    #
    # 上一版印「最小翻盘强度 = 0.5x」，读起来像「阈值就是 0.5x」。但如果
    # 0.5x 恰好是网格里最低的一档，那么真实阈值只是被**从上面**框住了
    # （≤0.5x），根本没被定位。印一个没有下界的数当阈值，是把
    # 「没测到」说成「测到了」——和把样本不够报成值是 0 同一族。
    # 所以这里逐步报**区间**：该步在网格上第一次翻盘的那一档，和它下面一档。
    grid = sorted(s["mult"] for s in scans)
    log("")
    log("逐步阈值夹逼（区间 = [不翻盘的最高档, 翻盘的最低档]）")
    log(f"  步  区间(×残差std)            对照 token      注入后 token     对照间距")
    per_step = []
    for i in range(STEPS):
        flip_at = next((m for m in grid
                        if next(r for r in scans if r["mult"] == m)["rows"][i]["flipped"]),
                       None)
        r0 = next(r for r in scans if r["mult"] == grid[0])["rows"][i]
        if flip_at is None:
            lo_txt = f"(>{grid[-1]} 全部不翻)"
            per_step.append({"step": i, "flips_at": None,
                             "lo": grid[-1], "hi": None})
        else:
            k = grid.index(flip_at)
            lo = grid[k - 1] if k > 0 else 0.0
            lo_txt = f"({lo}, {flip_at}]" if k > 0 else f"(0, {flip_at}]"
            per_step.append({"step": i, "flips_at": flip_at,
                             "lo": lo, "hi": flip_at})
        log(f"  {i:>2}  {lo_txt:<24} {r0['token_ctrl']!r:<14} "
            f"{r0['token_inj']!r:<15} {r0['margin_ctrl']:>8.3f}")
    unbracketed = [p for p in per_step if p["hi"] is None]
    at_lowest = [p for p in per_step if p["lo"] == 0.0]

    # ── 机制断言：阈值随决胜间距单调 ──────────────────────────────
    #
    # 「存在一个阈值」只是一句观察；「阈值由模型当时离改口有多近决定」才是机制。
    # 判据：**间距大的那一步，阈值下界不许更小**。任何一对违反就是反例，
    # 直接报红。这一条是能变红的：把注入点换到别的层、或换另一个方向，
    # 排序很可能就乱了，那时它会拦住我。
    #
    # 比较用**下界**而不是中点：下界只依赖「在多少倍以下确定不翻」这一事实，
    # 对右删失（到网格上限仍不翻）也成立；中点会假装我们知道删失点在哪。
    lows = {}
    for p in per_step:
        lows[p["step"]] = p["lo"] if p["lo"] > 0 else grid[0] * 0.5
    margins = {r["step"]: r["margin_ctrl"] for r in scans[0]["rows"]}
    violations = []
    steps_sorted = sorted(margins, key=lambda s: margins[s])
    for a, b in zip(steps_sorted, steps_sorted[1:]):
        if lows[b] < lows[a] - 1e-12:
            violations.append((a, b))
    monotonic = not violations
    log("")
    log("机制断言：阈值下界是否随决胜间距单调不减")
    for s in steps_sorted:
        log(f"  步{s}  间距={margins[s]:>7.3f}  阈值下界={lows[s]:>6.3f}")
    log(f"  ⇒ {'单调，断言成立' if monotonic else '**有反例，断言被推翻**'}")
    for a, b in violations:
        log(f"     反例：步{a}(间距{margins[a]:.3f}) 阈值下界 {lows[a]:.3f} "
            f"却 > 步{b}(间距{margins[b]:.3f}) 的 {lows[b]:.3f}？"
            f"间距大的反而阈值更小")

    log("")
    if at_lowest:
        log(f"  ⚠ {len(at_lowest)}/{STEPS} 步在**网格最低档就翻盘**"
            f"（步 {[p['step'] for p in at_lowest]}）")
        log(f"    ⇒ 它们的阈值**没有下界**，本轮只框到 ≤{grid[0]}；"
            f"要定位就得把网格往下延。")
    if unbracketed:
        log(f"  ⚠ {len(unbracketed)}/{STEPS} 步到 {grid[-1]}× 仍不翻"
            f"（步 {[p['step'] for p in unbracketed]}）⇒ 只框到 >{grid[-1]}")

    report = {
        "model": MODEL, "layer": LAYER, "steps": STEPS, "direction": direction,
        "vec_source": src, "resid_scale": resid_scale, "use_chat": USE_CHAT,
        "ctrl_generation": "".join(ctrl_toks), "scans": scans,
        "grid": grid, "per_step_threshold_bracket": per_step,
        "mechanism_monotonic": monotonic,
        "mechanism_violations": violations,
        "n_steps": STEPS, "n_flips": len(any_flip),
        "max_abs_dlogit": max((r["max_abs_dlogit"] for r in all_rows), default=0.0),
        "max_kl": max((r["kl"] for r in all_rows), default=0.0),
    }
    outp = os.path.join(REPO, ".cache", "probe_live_inject.json")
    os.makedirs(os.path.dirname(outp), exist_ok=True)
    json.dump(report, open(outp, "w"), ensure_ascii=False, indent=2)

    log("")
    log(f"向量来源：{src}")
    log(f"注入 = 强度 × 第 {LAYER} 层残差 std({resid_scale:.2f})   chat模板={USE_CHAT}")
    log("")
    if not moved:
        log("RESULT ① 全部强度下 logit 一步都没动 ⇒ hook 没生效，**装置故障**不是结论")
        sys.exit(1)
    if any_flip:
        log(f"RESULT ③ 真前向注入**会改模型行为**：{len(any_flip)}/{len(all_rows)} "
            f"步翻盘，最大 Δlogit {report['max_abs_dlogit']:.2f}，"
            f"最大 KL {report['max_kl']:.3f}")
        log("        剂量-反应成立：干预不是「有效/无效」，"
            "而是**强度够不够跨过决胜线**。")
        if at_lowest:
            log(f"        但本轮网格最低档 {grid[0]}× 就翻 ⇒ "
                f"阈值只框到 ≤{grid[0]}，**未定位**（见上面的夹逼表）")
            sys.exit(4)   # 结论成立但阈值没夹住，退出码要说清
        log("        逐步阈值已夹在 [不翻/翻] 区间里（见上表）")
        sys.exit(0)
    log(f"RESULT ② logit 每步都动了（最大 {report['max_abs_dlogit']:.3f}，"
        f"最大 KL {report['max_kl']:.4f}），但**所有强度下 0 步翻盘**")
    log(f"        ⇒ 干预是真的，但连最强的 {grid[-1]}× 也没跨过决胜线。")
    log(f"（明细已写 {outp}）")
    sys.exit(3)


if __name__ == "__main__":
    main()
