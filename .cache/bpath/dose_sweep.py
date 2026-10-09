"""剂量扫描：分清「方向不匹配」与「量太大进了非线性区」。

## 为什么要扫

P9 装置符号基准 FAIL：+w 在 think 轨迹上不单调升，而 −w 全域一致单调降。
两种可能，处理方式完全相反：

- **A 方向问题**：小剂量下 +w 也抬不起 marker logit ⇒ w 不是个「token 方向」，
  是「位置判别方向」，训练目标与注入读数不是一回事 ⇒ 要改目标或改读数。
- **B 量纲问题**：小剂量下 +w 正常，大剂量下翻转 ⇒ 进了非线性/饱和区 ⇒ 剂量要缩。

只看重跑的 P9 无法区分这两者——它只测 rel∈{0.5,1.0} 两个点。

## 判据（取数前写死，跑之前先写在这）

  D1 若存在剂量 d* 使 +w 在 think 上单调升 ⇒ B（量纲问题），报 d*
  D2 若在 d→0 处 +w 仍不升 ⇒ A（方向问题）
  D3 −w 在所有剂量都应单调降；若某剂量下失效，说明连线性都不成立，先查装置
  D4 扫描必须覆盖两条 no_think 作正控：no_think 上的 +w 应当全程单调升

正控缺失时不得解读 think 的结果（判据/变异/环境先怀疑）。
"""
from __future__ import annotations

import argparse
import json
import os
import statistics as st
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
MODEL = "/home/zhourui/.cache/huggingface/models/Qwen--Qwen3-1.7B/snapshots/master"
DOSE = [0.02, 0.05, 0.1, 0.25, 0.5, 1.0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--npz-dir", required=True)
    ap.add_argument("--sidecar-dir", required=True)
    ap.add_argument("--w-out", default=None, help="现训的 w 存到哪")
    ap.add_argument("--w", default=None,
                help="外部 w(.npy)；不给则用 r6_rerun.train_direction 在本批 think 上重训")
    ap.add_argument("--out", required=True)
    ap.add_argument("--gap", type=float, default=302.456,
                    help="注入尺度基准（= w_real 的类间间距）")
    ap.add_argument("--tids", default="",
                    help="逗号分隔的轨迹 id；不给则自动挑 think 2 条 + no_think 2 条")
    ap.add_argument("--n-pos", type=int, default=3)
    ap.add_argument("--layer", type=int, default=20)
    ap.add_argument("--gpu-uuid", default=None)
    a = ap.parse_args()

    # ⚠ CVD 必须在 import torch **之前**设好，否则对当前进程无效
    if a.gpu_uuid:
        os.environ["CUDA_VISIBLE_DEVICES"] = f"GPU-{a.gpu_uuid}"
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    MARKER_IDS = [13824, 14190, 6771, 10061, 7196, 88190, 80022]
    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL, dtype=torch.bfloat16).to("cuda:0").eval()

    # ---- 收集轨迹元信息 ----
    metas = {}
    for f in sorted(Path(a.sidecar_dir).glob("*.json")):
        j = json.load(open(f, encoding="utf-8"))
        mk = [i for i, t in enumerate(j.get("tokens") or [])
              if t["token_id"] in MARKER_IDS]
        if not mk:
            continue
        metas[j["trajectory_id"]] = {
            "mode": j["config"]["mode"], "P": (j.get("extra") or {}).get("prompt_tokens"),
            "n_tok": j["n_generated_tokens"], "markers": mk}

    # ---- 取 w：外部给的，或用与 r6_rerun **完全相同**的代码路径现训 ----
    if a.w:
        W = np.load(a.w).astype(np.float32)
        gap = a.gap
        print(f"[方向] 用外部 w: {a.w}  |w|={np.linalg.norm(W):.4f}")
    else:
        import importlib.util
        sp = importlib.util.spec_from_file_location(
            "r6r", str(Path(__file__).resolve().parent / "r6_rerun.py"))
        RR = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(RR)          # r6_rerun 的 main 在 __main__ 守卫里，安全
        train_tids = {t: metas[t]["markers"] for t in metas
                      if metas[t]["mode"] == "think" and len(metas[t]["markers"]) >= 3}
        tmap = {t: metas[t]["n_tok"] for t in metas}
        print(f"[方向] 在 {len(train_tids)} 条 think 轨迹上重训（与 r6_rerun 同路径）…")
        W, sgn, X, y, _ = RR.train_direction(a.npz_dir, train_tids, tmap)
        gap = RR.class_gap(W, X, y)
        del X, y
        print(f"[方向] |w|={np.linalg.norm(W):.4f}  正负打分差={sgn:.3f}  类间间距={gap:.3f}")
        if a.w_out:
            np.save(a.w_out, W)
            print("[方向] 已存", a.w_out)
    a.gap = gap

    LAYER = a.layer

    def lse(v):
        if hasattr(v, "detach"):
            v = v.detach().float().cpu().numpy()
        v = np.asarray(v, dtype=np.float64)
        m = float(v.max())
        return m + float(np.log(np.exp(v - m).sum()))

    def make_forward():
        blk = model.model.layers[LAYER]

        def logits_at(ids, vec, alpha):
            inj = len(ids) - 1

            def pre(mod, inp):
                h = inp[0]
                if alpha != 0.0:
                    v = torch.as_tensor(vec, dtype=h.dtype, device=h.device)
                    h = h.clone()
                    h[:, inj, :] = h[:, inj, :] + alpha * v
                    return (h,) + inp[1:]
                return None

            hd = blk.register_forward_pre_hook(pre)
            try:
                with torch.no_grad():
                    o = model(input_ids=ids.unsqueeze(0), use_cache=False,
                              return_dict=True)
            finally:
                hd.remove()
            return o.logits[0, -1].float()

        return logits_at

    fwd = make_forward()

    # ---- 选轨迹 ----
    def decile(g, n):
        return min(9, int(g / max(n, 1) * 10))

    def sample(mk, n):
        b = defaultdict(list)
        for g in mk:
            b[decile(g, n)].append(g)
        ks = sorted(b)
        if len(ks) > 6:
            idx = sorted({round(i * (len(ks) - 1) / 5) for i in range(6)})
            ks = [ks[j] for j in idx]
        return [sorted(b[k])[len(b[k]) // 2] for k in ks]

    if a.tids:
        tids = [t.strip() for t in a.tids.split(",") if t.strip()]
    else:
        th = [t for t in sorted(metas) if metas[t]["mode"] == "think"][:2]
        nt = [t for t in sorted(metas) if metas[t]["mode"] == "no_think"][:2]
        tids = th + nt

    print(f"[扫描] {len(tids)} 条轨迹，剂量 {DOSE}，尺度基准 gap={a.gap}")
    out = {"dose": DOSE, "gap": a.gap, "layer": LAYER, "traj": {}}
    for tid in tids:
        m = metas[tid]
        pos = sample(m["markers"], m["n_tok"])[: a.n_pos]
        z = np.load(os.path.join(a.npz_dir, tid + ".npz"))
        gen = z["token_ids"].tolist(); z.close()
        cti = json.load(open(Path(a.sidecar_dir) / f"{tid}.json", encoding="utf-8"))
        pid = tok(cti["chat_template_input"], return_tensors="pt",
                  add_special_tokens=False).input_ids[0].tolist()
        ids = torch.tensor(pid + gen, dtype=torch.long, device="cuda:0")
        rec = {"mode": m["mode"], "n_tok": m["n_tok"], "pos": pos, "curve": {}}
        for t in pos:
            up = ids[: m["P"] + t]
            base = fwd(up, up, None, 0.0)
            mk_t = torch.tensor(MARKER_IDS, device=base.device)
            b_lse = lse(base[mk_t])
            for sgn, nm in ((1.0, "w+"), (-1.0, "w-")):
                for d in DOSE:
                    lg = fwd(up, up, W * sgn, d * a.gap)
                    dl = lse(lg[mk_t]) - b_lse
                    rec["curve"].setdefault(f"{nm}@{d}", []).append(round(dl, 4))
        out["traj"][tid] = rec
        print(f"  {tid[:34]:34s} {m['mode']}")
        for k in sorted(rec["curve"], key=lambda z: (z[:2], float(z.split("@")[1]))):
            v = rec["curve"][k]
            print(f"     {k:10s} 中位 {st.median(v):9.4f}   逐位置 {v}")

    # ---- 判据 ----
    print()
    print("=" * 74)
    print("D1-D4 判决")
    print("=" * 74)
    fails = []

    def mono_up(vals):
        return all(b >= a_ for a_, b in zip(vals, vals[1:]))

    for tid, rec in out["traj"].items():
        for nm in ("w+", "w-"):
            med = [st.median(rec["curve"][f"{nm}@{d}"]) for d in DOSE]
            ok = mono_up(med) if nm == "w+" else mono_up([-x for x in med])
            if not ok:
                fails.append(f"{tid[:26]} {nm} 非单调")

    pos_ok = [t for t, r in out["traj"].items()
              if all(mono_up([st.median(r["curve"][f"w+@{d}"]) for d in DOSE])
                     for _ in [0])]
    print(f"D3 -w 全剂量单调降: {'PASS' if not [f for f in fails if 'w-' in f] else 'FAIL'}")
    print(f"D4 no_think +w 全剂量单调升（正控）: "
          f"{'PASS' if all(mono_up([st.median(out['traj'][t]['curve'][f'w+@{d}']) for d in DOSE]) for t in pos_ok) else 'FAIL'}")
    for tid, rec in out["traj"].items():
        med = [st.median(rec["curve"][f"w+@{d}"]) for d in DOSE]
        good = [DOSE[i] for i in range(len(DOSE) - 1) if med[i + 1] >= med[i]]
        print(f"  {tid[:34]:34s} {rec['mode']:9s} +w 各剂量单调升的邻段 {len(good)}/{len(DOSE)-1}"
              f"  小剂量端(0.02) 中位 {med[0]:+.4f}")

    if fails:
        print("\n=> 存在非单调：", fails[:6])
    json.dump(out, open(a.out, "w"), ensure_ascii=False, indent=1)
    print("\n写出", a.out)


if __name__ == "__main__":
    main()