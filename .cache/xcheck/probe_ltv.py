#!/usr/bin/env python3
"""LTV（阈值可读向量）探针。**只采数，不下判决。**

判决的唯一权威是 `build_ltv.py`，它从本文件落下的原始字段独立算一遍。
探针自己也算一部分（用于增量落盘与自检），但那份不作为结论。

预登记表：`LTV_PREREG.md`（写于取数之前，里面把 α 网格、稀疏上限、
留出划分、判定口径全都写死了）。

用法:
  PYTHONPATH=.cache/pylibs python3 .cache/xcheck/probe_ltv.py
  PART=decomp   python3 .cache/xcheck/probe_ltv.py     # 只跑①，便宜
  PART=thresh   python3 .cache/xcheck/probe_ltv.py     # 只跑②，贵
  N_PROB=4 N_CTX=6 python3 .cache/xcheck/probe_ltv.py
"""
import json
import os
import statistics as st
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ltv_sentences import SENTENCE_PAIRS, NEGATIVE_CONTROL_KEYS, TARGET_LAYERS

REPO = os.path.dirname(os.path.dirname(HERE))
OUT = os.environ.get("OUT", os.path.join(HERE, "ltv.json"))
MODEL_DIR = os.environ.get("PROBE_MODEL", os.path.join(REPO, "datasets", "models", "Qwen3-1.7B"))
COT = os.path.join(REPO, "datasets", "aime_qwen3_1p7b_16k_fp16", "aime")

# ---- 预登记表 §3 写死的量，一个都不许在这里改 -------------------------------
ALPHA_GRID = [0.05, 0.1, 0.2, 0.35, 0.5, 1.0, 2.0, 4.0]   # 按该层残差 std 定标
FIT_ALPHAS = [0.05, 0.1, 0.2]        # g_v 只在**最小的三档**上拟合
K_MAX = 8
N_PROB = int(os.environ.get("N_PROB", "4"))
N_CTX = int(os.environ.get("N_CTX", "6"))
LAYER = int(os.environ.get("LAYER", "14"))
N_CONTROL = 2                         # 每个上下文两个随机对照（种子写死）
SEED = 20261007                       # 预登记表里 AMBIG 的地方固定下来，见下
# ---------------------------------------------------------------------------

PROMPT_TMPL = ("{s}\n\nPlease reason step by step, and put your final answer "
               "within \\boxed{{}}.")


def log(*a):
    print(*a, flush=True)


def pick_problems():
    """按**题**划分留出集（预登记表 §3：同一道 AIME 题的句子不得跨集）。"""
    pids = sorted(f[:-5] for f in os.listdir(COT) if f.endswith(".json"))
    return pids[:N_PROB]


def main():
    part = os.environ.get("PART", "all")
    if not os.path.exists(MODEL_DIR):
        log(f"缺模型 {MODEL_DIR}")
        return 2
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL_DIR)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_DIR, torch_dtype=torch.float32)
    model.eval()
    nlayer = model.config.num_hidden_layers
    log(f"模型 {nlayer} 层 × {model.config.hidden_size}")

    def as_enc(text):
        return tok(text, return_tensors="pt")

    def resid_at_last(text, layer):
        """句子的**时间平均残差**（预登记表 §3：不含 padding，逐层各算一个）。"""
        enc = as_enc(text)
        with torch.no_grad():
            out = model(**enc, output_hidden_states=True)
        # hidden_states[k] 是第 k 层的输出；layer 是 1-based 约定
        h = out.hidden_states[layer][0].float()
        am = enc["attention_mask"][0].bool()
        return h[am].mean(0)

    result = {"schema": "steer3d.ltv/1", "alpha_grid": ALPHA_GRID,
              "fit_alphas": FIT_ALPHAS, "layer": LAYER, "k_max": K_MAX,
              "n_control": N_CONTROL, "seed": SEED,
              "n_prob": N_PROB, "n_ctx": N_CTX,
              "problem_ids": pick_problems(),
              "note": "本文件是原始采数，判决在 build_ltv.py",
              }

    # ================= ① 句子锚定的稀疏分解 =================
    if part in ("all", "decomp"):
        log("\n① 句子锚定：算每层的 r̄(S) − r̄(S')")
        t0 = time.time()
        rows = []
        for i, (key, s, sp) in enumerate(SENTENCE_PAIRS):
            # 每条句子塞在**同一段提示**里，避免提示本身的差异混进来
            a = resid_at_last(PROMPT_TMPL.format(s=s), LAYER)
            b = resid_at_last(PROMPT_TMPL.format(s=sp), LAYER)
            d = (a - b).float()
            rows.append({"key": key, "S": s, "Sp": sp,
                         "negative_control": key in NEGATIVE_CONTROL_KEYS,
                         "vec": [float(x) for x in d],
                         "norm": float(d.norm())})
            log(f"   [{i+1}/{len(SENTENCE_PAIRS)}] {key:<14} ‖d‖={rows[-1]['norm']:.3f}")
        result["sentence_diffs"] = rows
        result["decomp_seconds"] = round(time.time() - t0, 1)
        log(f"   ① 用掉 {result['decomp_seconds']}s")

    # ================= ② 阈值表（贵）=================
    if part in ("all", "thresh"):
        log("\n② 阈值表：在**留出题**的上下文上扫 α 网格")
        pids = result["problem_ids"]
        # 留出划分：前一半题抽句子，后一半题**只用来验**（G-a/G-c 都在留出集上判）
        split = max(1, len(pids) // 2)
        result["split"] = {"extract": pids[:split], "holdout": pids[split:]}
        log(f"   抽取题 {result['split']['extract']} ／ 留出题 {result['split']['holdout']}")

        # ⚠⚠⚠ 杠杆必须是项目**真实的 steering 向量**，不能拿句子差分当杠杆。
        #   第一版拿 v_conf（句子差分）当 v，冒烟测试跑出来的结果是
        #   「m_p=0.24~1.19，而 α* 全是 None，连 α=4 都翻不动」。
        #   原因不是定标错了，是**向量不对**：句子差分是在另一段上下文上算的，
        #   对该位置的 logit 头来说基本是噪声；而 steering 向量是对着 logit 头
        #   提出来的方向。⇒ LTV 讲的是「**一个杠杆**的说明书」，
        #   杠杆必须是真能当杠杆用的那个。
        #   这也正是预登记表 §0③「方向 ≠ 杠杆」的意思。
        sys.path.insert(0, os.path.join(REPO, "backend"))
        from core.steering import get_registry
        reg = get_registry()
        if not reg.names:
            log("装置故障：steering registry 里没有方向，无从验起")
            return 2
        result["registry_names"] = list(reg.names)
        VNAME = os.environ.get("LTV_DIR", "confidence_up")
        v_raw = reg.scaled(VNAME, 1.0, LAYER)
        if v_raw is None:
            log(f"装置故障：registry 给不出 {VNAME}@L{LAYER}")
            return 2
        v = torch.tensor(v_raw, dtype=torch.float32).ravel()
        v = v / (v.norm() + 1e-9)
        result["lever"] = {"name": VNAME, "layer": LAYER,
                           "unit_norm": float(v.norm()),
                           "vec": [float(x) for x in v]}
        log(f"   杠杆 {VNAME}@L{LAYER}，‖v‖={float(v.norm()):.6f}")
        v_conf = v      # 供①分解用的就是它（v = Σ c_k d_k）

        g = torch.Generator().manual_seed(SEED)
        ctx_rows = []
        t0 = time.time()
        for pid in pids:
            cpath = os.path.join(COT, f"{pid}.json")
            if not os.path.exists(cpath):
                continue
            cj = json.load(open(cpath, encoding="utf-8"))
            toks = cj.get("tokens") or []
            if len(toks) < N_CTX * 3:
                continue
            # 上下文取**生成段中部**，避开开头（还没进入推理）与结尾（答案已写完）
            lo, hi = len(toks) // 3, 2 * len(toks) // 3
            idxs = [lo + (hi - lo) * i // max(N_CTX, 1) for i in range(N_CTX)]
            for p in idxs:
                ctx_rows.append({"pid": pid, "pos": p,
                                 "tok": toks[p].get("token") if p < len(toks) else None})
                if len(ctx_rows) >= N_CTX * len(pids):
                    break
            if len(ctx_rows) >= N_CTX * len(pids):
                break
        log(f"   选了 {len(ctx_rows)} 个上下文（按题留出）")

        # 逐上下文：clean 前向 → 扫 α（臂 + 配平随机对照）→ 量 gap(α)
        out_rows = []
        for ci, c in enumerate(ctx_rows):
            cj = json.load(open(os.path.join(COT, f"{c['pid']}.json"), encoding="utf-8"))
            toks = cj.get("tokens") or []
            ids = [t["token_id"] for t in toks[: c["pos"]] if "token_id" in t]
            if len(ids) < 8:
                continue
            enc = as_enc(PROMPT_TMPL.format(
                s="Consider the reasoning so far."))
            inp = torch.tensor([ids + [enc["input_ids"][0, -1].item()]])
            pos = len(ids)

            def splice_hooks(vecs):
                """一次前向同时打 N 个补丁（batch=N），与 probe_path_patching 同一套。"""
                n = len(vecs)
                ids_b = inp.repeat(n, 1)
                V = torch.stack([v.to(torch.float32) for v in vecs])

                def hook(_m, _i, outp):
                    hs = outp[0] if isinstance(outp, tuple) else outp
                    hs = hs.clone()
                    for b in range(n):
                        hs[b, pos, :] = V[b].to(hs.dtype)
                    return ((hs,) + tuple(outp[1:])) if isinstance(outp, tuple) else hs
                layers = model.model.layers
                h = layers[LAYER - 1].register_forward_hook(hook)
                try:
                    with torch.no_grad():
                        lg = model(ids_b).logits[:, pos, :].float()
                    return [lg[b] for b in range(n)]
                finally:
                    h.remove()

            with torch.no_grad():
                _o = model(inp, output_hidden_states=True)
            clean_res = _o.hidden_states[LAYER][0, pos].float()
            clean_lg = splice_hooks([clean_res])[0]
            order = torch.argsort(clean_lg, descending=True)
            top1, top2 = int(order[0]), int(order[1])
            m_p = float(clean_lg[top1] - clean_lg[top2])
            # ⚠⚠ 定标必须与**已通过预登记**的 `probe_threshold_law.py` 逐字一致：
            #   那边是 `float(hs.float().std())`，hs 是**整个前缀**在该层的隐状态张量。
            #   第一版这里用的是**单个位置**残差的 std（`clean_res.std()`），
            #   两者不是同一个统计量，于是 α 的含义整体偏了一个量级 ——
            #   而预登记表的阈值区间（0.2~2.0×）是按**前一个**定标测出来的。
            #   ⇒ 用错定标 = 拿旧表配新尺子。
            sigma = float(_o.hidden_states[LAYER][0].float().std())

            # 臂：clean + α·σ·v̂（v̂ = 单位方向）
            vhat = v_conf / v_conf.norm()
            us = [torch.randn(model.config.hidden_size, generator=g)
                  for _ in range(N_CONTROL)]
            us = [u / u.norm() for u in us]

            slots, vecs = [], []
            for a in ALPHA_GRID:
                vecs.append(clean_res + a * sigma * vhat); slots.append(("arm", a))
            for a in ALPHA_GRID:
                for k, u in enumerate(us):
                    vecs.append(clean_res + a * sigma * u)
                    slots.append((f"nm{k}", a))
            # ⚠ 恒等自证：把干净残差也放进同一个 batch。
            #   批量化会轻微改变浮点，若引入偏差，这一条立刻会红。
            vecs.append(clean_res); slots.append(("id", 0.0))
            lgs = dict()
            for (k, a), lg in zip(slots, splice_hooks(vecs)):
                lgs[(k, a)] = lg

            def gap_of(lg):
                """gap(α) = logit[clean_top1] − logit[clean_top2]"""
                return float(lg[top1] - lg[top2])

            arm_gap = {a: gap_of(lgs[("arm", a)]) for a in ALPHA_GRID}
            ctl_gap = {f"nm{k}": {a: gap_of(lgs[(f"nm{k}", a)]) for a in ALPHA_GRID}
                      for k in range(N_CONTROL)}
            id_ok = int(torch.argmax(lgs[("id", 0.0)])) == top1

            # 首次 top-1 改变的 α（预登记表：**top-1 发生变化**，不是「接近」）。
            # ⚠ 判定必须用**各自的** logits —— 拿臂的 α* 去套对照是拿错对象。
            def first_flip_for(keyfn):
                for a in ALPHA_GRID:
                    if int(torch.argmax(keyfn(a))) != top1:
                        return a
                return None
            arm_flip = first_flip_for(lambda a: lgs[("arm", a)])
            ctl_flip = {f"nm{k}": first_flip_for(lambda a, k=k: lgs[(f"nm{k}", a)])
                        for k in range(N_CONTROL)}

            out_rows.append({
                "pid": c["pid"], "pos": c["pos"], "tok": c["tok"],
                "layer": LAYER, "sigma": sigma,
                "clean_top1": top1, "clean_top2": top2, "m_p": m_p,
                "identity_top1_ok": id_ok,
                "arm_gap": {str(a): arm_gap[a] for a in ALPHA_GRID},
                "ctl_gap": {k: {str(a): v for a, v in m.items()} for k, m in ctl_gap.items()},
                "arm_alpha_star": arm_flip,
                "ctl_alpha_star": ctl_flip,
                # g_v 只在最小三档上拟合；后面五档是**预测区**。
                "fit_alphas": FIT_ALPHAS,
            })
            log(f"   [{ci+1}/{len(ctx_rows)}] {c['pid'][-11:]} pos={c['pos']:4d} "
                f"m_p={m_p:8.4f} arm α*={arm_flip} ctl α*={ctl_flip} "
                f"恒等={id_ok}")
            result["contexts"] = out_rows
            _dump(result)

        result["thresh_seconds"] = round(time.time() - t0, 1)
        log(f"   ② 用掉 {result['thresh_seconds']}s")
        _dump(result)

    _dump(result)
    return 0


def _dump(r):
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False)
    os.replace(tmp, OUT)


if __name__ == "__main__":
    sys.exit(main())