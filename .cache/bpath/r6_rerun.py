"""R-6 重跑：新批次上「答对 vs 答错」的 correct/incorrect 对照。

严格按 `.cache/xcheck/R6_RERUN_PREREG.md` 的 P0-P9 执行，判决规则不在本文件改。
本文件只负责执行；所有阈值从预登记读，不在此处另设。

## 坐标（来自 R-1，已在新批次 22/22 验过）

    npz 第 g 行        == 全序列第 (P + g − 1) 位
    生成段 token t 的预测 logits 在全序列第 (P + t − 1) 位

HF 里 logits[i] 由 h[i] 算出 ⇒ **注入与读取在同一位置 P+t−1**：
喂 full[:P+t]，注入 h[P+t−1]，读 logits[−1]（正是 P+t−1）。
P 直接取侧车的 `extra.prompt_tokens`，**不需要 prompt 回填**（修订 3.1）。

## 变体（P3 / P4）

    baseline
    +w @ rel{0.5, 1.0}      -w @ rel{0.5, 1.0}
    rand @ rel{0.5, 1.0}    （一个方向扫全部剂量，方向与剂量不分别随机）

rel 剂量按 `w·h` 的类间间距归一（class_gap），不是单位向量直觉。

## 读数（P8）

    mark   : marker 集合的 Δlogprob（集合内取 max 的那类，脚本里显式列出）
    the    : 对照词 ` the ` 的 Δlogprob
    tok    : 该位置实际写下的那个标记词的 Δlogit
    特异性 = |Δmark| / |Δthe|

⚠ 绝对 Δlogprob 跨位置不可比（R-22 修订 2 已记），所以本脚本
   **先在每个位置内算 Δ，再对轨迹取均值**，不做跨位置的绝对值平均。
"""
from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import numpy as np

HERE = Path(__file__).resolve().parent
LAYER = 20
MARKER_IDS = [13824, 14190, 6771, 10061, 7196, 88190, 80022]
CONTROL_ID = 279          # ` the `
REL_LADDER = [0.5, 1.0]   # P3
MAX_POS_PER_TRAJ = 6      # P5
MIN_CORRECT_TRAJ = 10     # P6
MIN_WRONG_TRAJ = 8        # Q3
ALPHA = 0.05              # P6


# ---------------------------------------------------------------- 位置抽样 P5
def sample_markers(marker_idx, n_tok):
    if not marker_idx:
        return []
    buckets = defaultdict(list)
    for g in marker_idx:
        buckets[min(9, int(g / max(n_tok, 1) * 10))].append(g)
    out = []
    for b in sorted(buckets)[:MAX_POS_PER_TRAJ]:
        out.append(buckets[b][0])
    return sorted(out)


# ---------------------------------------------------------------- 训练方向 P2a
def pick_negatives(pos, tmap, rng):
    """同轨迹里距离最近的非动摇点（难负例），与 probe_hinge_layers 一致。"""
    negs = {}
    for t, toks in pos.items():
        T = tmap.get(t, 1024)
        cand = np.setdiff1d(np.arange(T), np.array(toks, dtype=int))
        picks = []
        for tpos in toks:
            if len(cand) == 0:
                picks.append(int(rng.integers(0, max(1, T))))
                continue
            j = int(np.argmin(np.abs(cand - tpos)))
            picks.append(int(cand[j]))
        negs[t] = picks
    return negs


def load_xy(npz_dir, pos, negs):
    Xs, ys, ts = [], [], []
    for tid in sorted(pos):
        z = np.load(os.path.join(npz_dir, tid + ".npz"))
        H = z["hidden_states"][:, LAYER, :].astype(np.float32)
        T = H.shape[0]
        for t in pos[tid]:
            if 0 <= t < T:
                Xs.append(H[t]); ys.append(1); ts.append(tid)
        for t in negs.get(tid, []):
            if 0 <= t < T:
                Xs.append(H[t]); ys.append(0); ts.append(tid)
        del H, z
    return np.stack(Xs), np.array(ys, dtype=int), np.array(ts)


def train_direction(npz_dir, pos, tmap, seed=42):
    """LOO 轨迹、岭回归、平衡权重、符号定死（正例打分更高）、单位范数。"""
    rng = np.random.default_rng(seed)
    negs = pick_negatives(pos, tmap, rng)
    X, y, traj = load_xy(npz_dir, pos, negs)
    coefs = []
    for held in sorted(set(traj)):
        te = traj == held
        tr = ~te
        if tr.sum() == 0:
            continue
        Xtr, ytr = X[tr].astype(np.float64), y[tr].astype(np.float64)
        mu, sd = Xtr.mean(0, keepdims=True), Xtr.std(0)
        keep = sd > 1e-8
        Hn = (Xtr - mu)[:, keep] / sd[keep]
        wgt = np.where(ytr > 0, 0.5 / max(1, (ytr > 0).sum()),
                       0.5 / max(1, (ytr == 0).sum()))
        A = Hn.T @ (Hn * ((wgt * (2 * ytr - 1))[:, None])) + 1e4 * np.eye(Hn.shape[1])
        c = np.linalg.solve(A, Hn.T @ (wgt * (2 * ytr - 1)))
        full = np.zeros(X.shape[1]); full[np.where(keep)[0]] = c
        coefs.append(full)
    W = np.mean(coefs, axis=0)
    sgn = float(np.mean([W @ X[i] for i in range(len(y)) if y[i] == 1]) -
                np.mean([W @ X[i] for i in range(len(y)) if y[i] == 0]))
    if sgn < 0:
        W = -W
    W = W / (np.linalg.norm(W) + 1e-12)
    return W.astype(np.float32), abs(sgn), X, y, traj


def class_gap(W, X, y):
    return float(np.mean([W @ X[i] for i in range(len(y)) if y[i] == 1]) -
                  np.mean([W @ X[i] for i in range(len(y)) if y[i] == 0]))


# ---------------------------------------------------------------- 注入执行
def make_forward(model, tokenizer):
    import torch


    def logits_at(ids, t, vec, alpha):
        """注入 h[P+t-1]，读 logits[-1]（正是同一位置）。"""
        blk = model.model.layers[LAYER]
        inj = len(ids) - 1

        def pre(mod, inp):
            h = inp[0]
            if alpha != 0.0:
                # W 是 numpy（训练产物），h 是 torch —— 必须显式转换，
                # 直接 vec.to(h.dtype) 会 AttributeError
                v = torch.as_tensor(vec, dtype=h.dtype, device=h.device)
                h = h.clone()
                h[:, inj, :] = h[:, inj, :] + alpha * v
                return (h,) + inp[1:]
            return None

        hd = blk.register_forward_pre_hook(pre)
        try:
            with torch.no_grad():
                o = model(input_ids=ids.unsqueeze(0), use_cache=False, return_dict=True)
        finally:
            hd.remove()
        return o.logits[0, -1].float()

    return logits_at


def lse(v):
    """log-sum-exp。入参可能是 torch(CUDA) 或 numpy，统一先搬回主机。"""
    if hasattr(v, "detach"):
        v = v.detach().float().cpu().numpy()
    v = np.asarray(v, dtype=np.float64)
    m = float(v.max())
    return m + float(np.log(np.exp(v - m).sum()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--npz-dir", required=True)
    ap.add_argument("--sidecar-dir", required=True)
    ap.add_argument("--labels", required=True, help="strict_label 产物 json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--mode", default="both", choices=["think", "no_think", "both"])
    ap.add_argument("--w", default=None, help="外部 w（.npy）；不给则本批重训")
    ap.add_argument("--limit-traj", type=int, default=None)
    ap.add_argument("--gpu-uuid", default=None)
    ap.add_argument("--smoke", action="store_true", help="只跑 3 条轨迹的装置符号基准")
    ap.add_argument("--train-only", action="store_true",
                    help="只训 w 并存成 .npy 后退出：**不加载模型、不需要 GPU**。"
                         "训练只吃 npz 的 hidden_states，所以可以在本机跑，"
                         "用来产出 P2b 需要的 w_old。")
    ap.add_argument("--w-out", default=None, help="--train-only 时 w 的输出路径")
    a = ap.parse_args()

    MODEL = "/home/zhourui/.cache/huggingface/models/Qwen--Qwen3-1.7B/snapshots/master"

    lab = {r["traj"]: r for r in json.load(open(a.labels, encoding="utf-8"))["rows"]}

    # ---- 收轨迹 ----
    metas = {}
    for f in sorted(Path(a.sidecar_dir).glob("*.json")):
        j = json.load(open(f, encoding="utf-8"))
        tid = j["trajectory_id"]
        if a.mode != "both" and j["config"]["mode"] != a.mode:
            continue
        metas[tid] = {
            "mode": j["config"]["mode"],
            "n_tok": j["n_generated_tokens"],
            "P": (j.get("extra") or {}).get("prompt_tokens"),
            "gen_ids": None,
            "markers": [i for i, t in enumerate(j.get("tokens") or [])
                        if t["token_id"] in MARKER_IDS],
            "label": lab.get(tid, {}).get("strict", "unlabeled"),
        }
    if a.limit_traj:
        keep = sorted(metas)[:a.limit_traj]
        metas = {k: metas[k] for k in keep}
    print(f"[人口] {len(metas)} 条轨迹  "
          f"{ {m: sum(1 for v in metas.values() if v['mode']==m) for m in set(v['mode'] for v in metas.values())} }")
    print(f"[标签] "
          f"{ {m: sum(1 for v in metas.values() if v['label']==m) for m in set(v['label'] for v in metas.values())} }")

    # ---- 训练方向（P2a：在本批 think 的动摇点上训）----
    train_tids = {t: metas[t]["markers"] for t in metas
                  if metas[t]["mode"] == "think" and len(metas[t]["markers"]) >= 3}
    if not train_tids:
        print("没有可用的 think 动摇点，无法训 w"); return 2
    tmap = {t: metas[t]["n_tok"] for t in metas}
    if a.w:
        W = np.load(a.w).astype(np.float32); gap = None; sgn = None
        print(f"[方向] 用外部 w: {a.w}  |w|={np.linalg.norm(W):.4f}")
    else:
        print(f"[方向] 在 {len(train_tids)} 条 think 轨迹的动摇点上重训 …")
        W, sgn, X, y, _ = train_direction(a.npz_dir, train_tids, tmap)
        gap = class_gap(W, X, y)
        print(f"[方向] |w|={np.linalg.norm(W):.4f}  正负打分差={sgn:.3f}  类间间距={gap:.3f}")
        del X, y

    # 分词器与模型都**不是训练 w 所需** —— 训练只吃 npz 的 hidden_states。
    # 所以 train-only 必须在加载它们之前返回，否则本机（无该模型缓存）会直接报
    # HFValidationError（远端模型路径在本机不存在）。
    if a.train_only:
        out_w = a.w_out or (a.out + ".w.npy")
        np.save(out_w, W)
        meta = {"npz_dir": a.npz_dir, "n_train_traj": len(train_tids),
                "sign_gap": sgn, "class_gap": gap, "w_norm": float(np.linalg.norm(W)),
                "layer": LAYER, "seed": 42, "marker_ids": MARKER_IDS}
        json.dump(meta, open(out_w + ".json", "w"), ensure_ascii=False, indent=1)
        print(f"[train-only] 写出 {out_w}（|w|={float(np.linalg.norm(W)):.4f}, "
              f"类间间距={gap:.3f}, 训练轨迹 {len(train_tids)} 条）")
        return 0

    rng = np.random.default_rng(42)
    W_rand = rng.standard_normal(2048).astype(np.float32)
    W_rand /= np.linalg.norm(W_rand)

    # ---- 装置符号基准 P9 ----
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    if a.gpu_uuid:
        os.environ["CUDA_VISIBLE_DEVICES"] = f"GPU-{a.gpu_uuid}"
    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL, dtype=torch.bfloat16).to("cuda:0").eval()
    fwd = make_forward(model, tok)

    smoke_tids = [t for t in sorted(metas) if metas[t]["markers"]][:3]
    print(f"\n[P9 装置符号基准] 用 {len(smoke_tids)} 条轨迹")
    bench = {}
    for tid in smoke_tids:
        m = metas[tid]
        z = np.load(os.path.join(a.npz_dir, tid + ".npz"))
        gen = z["token_ids"].tolist(); z.close()
        cti = json.load(open(Path(a.sidecar_dir) / f"{tid}.json", encoding="utf-8"))
        pid = tok(cti["chat_template_input"], return_tensors="pt",
                  add_special_tokens=False).input_ids[0].tolist()
        ids = torch.tensor(pid + gen, dtype=torch.long, device="cuda:0")
        t = sample_markers(m["markers"], m["n_tok"])[0]
        up = ids[: m["P"] + t]
        base = fwd(up, up, None, 0.0)
        mk = torch.tensor(MARKER_IDS, device=base.device)
        row = {}
        for nm, v in (("w+", W), ("w-", -W), ("rand", W_rand)):
            ds = []
            for rel in REL_LADDER:
                lg = fwd(up, up, v, rel * (gap or 375.0))
                dl = float(lse(lg[mk]) - lse(base[mk]))
                row[f"{nm}@{rel}"] = round(dl, 4)
        bench[tid] = row
        print(f"  {tid[:34]:34s} {row}")

    pos_ok = True
    for t, r in bench.items():
        up_mono = r.get("w+@1.0", 0.0) >= r.get("w+@0.5", 0.0)
        dn_mono = r.get("w-@1.0", 0.0) <= r.get("w-@0.5", 0.0)
        if not (up_mono and dn_mono):
            pos_ok = False
    print(f"  +w 单调升 且 -w 单调降 : {'PASS' if pos_ok else 'FAIL'}")
    print(f"  P9 {'通过，可以继续' if pos_ok else '**未通过，先修装置**'}")

    if a.smoke:
        json.dump({"bench": bench, "pos_ok": pos_ok},
                  open(a.out, "w"), ensure_ascii=False, indent=1)
        return 0 if pos_ok else 1

    # ---- 全量变体 ----
    rows = []
    t_start = time.time()
    for ti, tid in enumerate(sorted(metas)):
        m = metas[tid]
        picked = sample_markers(m["markers"], m["n_tok"])
        if not picked:
            continue
        z = np.load(os.path.join(a.npz_dir, tid + ".npz"))
        gen = z["token_ids"].tolist(); z.close()
        cti = json.load(open(Path(a.sidecar_dir) / f"{tid}.json", encoding="utf-8"))
        pid = tok(cti["chat_template_input"], return_tensors="pt",
                  add_special_tokens=False).input_ids[0].tolist()
        ids = torch.tensor(pid + gen, dtype=torch.long, device="cuda:0")
        mk = torch.tensor(MARKER_IDS, device="cuda:0")
        ctl = torch.tensor([CONTROL_ID], device="cuda:0")

        for t in picked:
            up = ids[: m["P"] + t]
            base = fwd(up, up, None, 0.0)
            b_mark, b_ctl = lse(base[mk]), lse(base[ctl])
            rec = {"traj": tid, "t": t, "mode": m["mode"], "label": m["label"]}
            for nm, v in (("w+", W), ("w-", -W), ("rand", W_rand)):
                for rel in REL_LADDER:
                    lg = fwd(up, up, v, rel * (gap or 375.0))
                    rec[f"mark_{nm}_{rel}"] = float(lse(lg[mk]) - b_mark)
                    rec[f"the_{nm}_{rel}"] = float(lse(lg[ctl]) - b_ctl)
                    rec[f"tok_{nm}_{rel}"] = float(
                        (lg - base)[gen[t] if t < len(gen) else 0].item())
            rows.append(rec)
        if (ti + 1) % 5 == 0:
            el = time.time() - t_start
            print(f"  [{ti+1}/{len(metas)}] 位置 {len(rows)}  用时 {el/60:.1f} min "
                  f"({el/max(len(rows),1):.2f} s/位置)")
    print(f"[全量] {len(rows)} 个位置，用时 {(time.time()-t_start)/60:.1f} min")

    json.dump({"bench": bench, "pos_ok": pos_ok, "rows": rows,
               "rel_ladder": REL_LADDER, "layer": LAYER,
               "class_gap": gap, "w_norm": float(np.linalg.norm(W))},
              open(a.out, "w"), ensure_ascii=False, indent=1)
    print("写出", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())