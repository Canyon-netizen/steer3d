#!/usr/bin/env python3
"""打破标签循环：在**未来**的步上打分。

`heldout_recheck.py` 复现出来的那份证据，循环性只去掉了「样本」这一半：
contrast 仍然是 mean(A) − mean(B)，而打分的可观测量就是 A/B 的划分谓词。
换轨迹没换标签 —— 所以它测的是「contrast 跨轨迹稳不稳」，
不是「这个方向在绝对意义上就是 self-check 的实现」。

这里换一个**时间**上的切分来去掉标签这一半：

    向量/contrast 的定义只用了第 t 步的观测量
    打分改用第 t+Δ 步的观测量 —— 它没有进过定义

于是「方向能预测 t 步的量」与「方向能预测 t+Δ 步的量」是两个不同的命题。
后者不是恒等式。

**必须配随机方向对照**：轨迹内观测量强自相关，所以哪怕方向完全随机，
p_t 与 obs_{t+Δ} 也会相关。真实方向与随机方向吃的是同一份自相关，
两者的差才是信号。曲线随 Δ 的衰减形状本身也是结论：

    Δ 小   ⇒ 只有可能是 token 局部效应
    Δ 大   ⇒ 方向编码的是一个持续的状态

装置自检与上一支脚本同源（连续标签 rho≈1、二元标签 AUC≈1）。
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
from scipy import stats

ROOT = Path("/Users/zhourui/code/steer3d")
NPZ_DIR = ROOT / "datasets/aime_qwen3_1p7b_16k_fp16/aime"
OUT = ROOT / ".cache/rolesverify/heldout_lag.json"
LAYER = 14
LAGS = [0, 1, 5, 20, 100, 400]
N_RANDOM = 200
SEED = 20261003

SELF_CHECK_RE = re.compile(
    r"\b(wait|actually|hmm|hold on|let me check|let me verify|recheck|"
    r"double[- ]check|second thought|alternatively|but wait)\b", re.IGNORECASE)
CONTRASTS = {
    "confidence_up": ("entropy_lo", "entropy_hi"),
    "caution": ("self_check_yes", "self_check_no"),
    "creativity": ("think_yes", "think_no"),
    "reasoning_deep": ("late", "early"),
}
CLAIMS = {
    "confidence_up": ("entropy", -1),
    "caution": ("self_check", +1),
    "creativity": ("in_think", +1),
    "reasoning_deep": ("step_frac", +1),
}
BINARY = ("self_check", "in_think", "top1_switch")


def rho_rank(x, y):
    if len(x) < 8:
        return float("nan")
    r = stats.spearmanr(x, y).statistic
    return float(r) if r == r else float("nan")


def auc_rankwise(pos, neg):
    n1, n2 = len(pos), len(neg)
    if n1 == 0 or n2 == 0:
        return float("nan")
    ranks = stats.rankdata(np.concatenate([pos, neg]))
    return float((ranks[:n1].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n2))


def read_side(p: Path, T: int):
    meta = json.loads(p.read_text())
    toks = meta.get("tokens", [])
    if len(toks) != T:
        return None
    ent = np.asarray([t["entropy"] for t in toks], np.float32)
    think = np.asarray([bool(t.get("is_in_think_block", False)) for t in toks], np.float32)
    sc = np.asarray([bool(SELF_CHECK_RE.search(t.get("token") or "")) for t in toks], np.float32)
    frac = np.arange(T, dtype=np.float32) / max(T - 1, 1)
    q30, q75 = float(np.quantile(ent, 0.30)), float(np.quantile(ent, 0.75))
    return {"traj": meta.get("trajectory_id", p.stem), "T": T,
            "entropy": ent, "self_check": sc, "in_think": think, "step_frac": frac,
            "masks": {"entropy_lo": ent <= q30, "entropy_hi": ent >= q75,
                      "self_check_yes": sc > 0.5, "self_check_no": sc < 0.5,
                      "think_yes": think > 0.5, "think_no": think < 0.5,
                      "late": frac >= 0.75, "early": frac <= 0.25}}


def toy_check():
    rs = np.random.default_rng(11)
    p, yc, yb = [], [], []
    for _ in range(4):
        h = rs.standard_normal((400, 16)).astype(np.float32)
        lab = rs.random(400) < 0.3
        h[lab, 0] += 3.0
        v = np.zeros(16, np.float32); v[0] = 1.0
        q = h @ v
        p.append(q)
        yc.append(q + rs.standard_normal(400) * 0.01)
        yb.append(lab.astype(np.float32))
    r = rho_rank(np.concatenate(p), np.concatenate(yc))
    a = auc_rankwise(np.concatenate(p)[np.concatenate(yb) > 0.5],
                     np.concatenate(p)[np.concatenate(yb) < 0.5])
    ok = r > 0.95 and a > 0.95
    print(f"[自检] 连续 rho={r:.4f}  二元 AUC={a:.4f} -> {'OK' if ok else '装置有问题'}")
    if not ok:
        raise SystemExit("ABORT 玩具输入不对")


def main():
    toy_check()
    files = sorted(p for p in NPZ_DIR.glob("*.npz") if p.with_suffix(".json").exists())
    probs = {}
    for p in files:
        probs.setdefault(p.stem.rsplit("__", 1)[0], []).append(p)
    order = sorted(probs)
    fold_of = {p.stem: (i % 2) for i, base in enumerate(order) for p in probs[base]}

    sums, cnts, meta, path_of = {}, {}, {0: [], 1: []}, {}
    for p in files:
        with np.load(p) as z:
            T = int(z["hidden_states"].shape[0])
            rec = read_side(p.with_suffix(".json"), T)
            if rec is None:
                continue
            f = fold_of[p.stem]
            meta[f].append(rec)
            path_of[rec["traj"]] = p
            h = z["hidden_states"][:, LAYER, :].astype(np.float32)
            for g, m in rec["masks"].items():
                if m.sum() < 2:
                    continue
                k = (f, g)
                sums[k] = sums.get(k, 0.0) + h[m].sum(axis=0)
                cnts[k] = cnts.get(k, 0) + int(m.sum())
            del h

    H = {0: {}, 1: {}}
    for f in (0, 1):
        for rec in meta[f]:
            with np.load(path_of[rec["traj"]]) as z:
                H[f][rec["traj"]] = z["hidden_states"][:, LAYER, :].astype(np.float32)
    print(f"records={len(files)} problems={len(order)} materialised", file=sys.stderr)

    rs = np.random.default_rng(SEED)
    rand = rs.standard_normal((N_RANDOM, 2048))
    rand /= np.linalg.norm(rand, axis=1, keepdims=True)

    def fit(f, pos, neg):
        a, b = sums.get((f, pos)), sums.get((f, neg))
        na, nb = cnts.get((f, pos), 0), cnts.get((f, neg), 0)
        if a is None or b is None or na < 30 or nb < 30:
            return None
        u = (a / na) - (b / nb)
        return (u / (np.linalg.norm(u) + 1e-8)).astype(np.float32)

    res = {"schema": "rolesverify.heldout_lag/1", "layer": LAYER, "lags": LAGS,
           "n_random": N_RANDOM, "seed": SEED,
           "note": "contrast 在一折上拟合，在另一折上按 Δ 步错位打分；"
                   "Δ=0 即 heldout_non_circular 的同折版本，Δ>0 的量没进过定义",
           "toy_selfcheck": "passed", "folds": {}}

    for name, (pos, neg) in CONTRASTS.items():
        obs, sign = CLAIMS[name]
        entry = {"observable": obs, "expected_sign": sign, "folds": {}}
        for ff in (0, 1):
            v = fit(ff, pos, neg)
            if v is None:
                continue
            sf = 1 - ff
            recs = meta[sf]
            # 投影：一次算好，真实方向和 200 个随机方向共用
            P_real = {r["traj"]: H[sf][r["traj"]] @ v for r in recs}
            P_rnd = {}
            for r in recs:
                hm = H[sf][r["traj"]] - H[sf][r["traj"]].mean(axis=0, keepdims=True)
                P_rnd[r["traj"]] = hm @ rand.T          # (T, K)
            per_lag = {}
            for lag in LAGS:
                xs, ys = [], []
                for r in recs:
                    T = r["T"]
                    if T - lag < 8:
                        continue
                    xs.append(P_real[r["traj"]][:T - lag])
                    ys.append(r[obs][lag:])
                if not xs:
                    continue
                x = np.concatenate(xs); y = np.concatenate(ys)
                rx = rho_rank(x, y)
                # 随机方向：同样错位、同样轨迹内去均值
                rxs, rys = [], []
                for r in recs:
                    T = r["T"]
                    if T - lag < 8:
                        continue
                    rxs.append(P_rnd[r["traj"]][:T - lag, :])
                    rys.append(r[obs][lag:])
                if not rxs:
                    continue
                RX = np.concatenate(rxs, axis=0); RY = np.concatenate(rys)
                null = np.array([rho_rank(RX[:, k], RY) for k in range(N_RANDOM)])
                null = null[~np.isnan(null)]
                per_lag[str(lag)] = {
                    "n_pairs": int(len(x)),
                    "rho": rx,
                    "null_mean": float(null.mean()), "null_sd": float(null.std()),
                    "null_p95_abs": float(np.percentile(np.abs(null), 95)),
                    "null_max_abs": float(np.abs(null).max()),
                    "p_abs_gt": float((np.abs(null) >= abs(rx)).mean()),
                    "excess_over_null": rx - float(null.mean()),
                }
                q = per_lag[str(lag)]
                line = (f"  {name:16s} fit{ff}->sf{sf} Δ={lag:<4d} "
                        f"rho={rx:+.4f}  零假设 {q['null_mean']:+.4f}±{q['null_sd']:.4f}  "
                        f"超出 {q['excess_over_null']:+.4f}  p={q['p_abs_gt']:.4f}")
                # 二元观测量上 rho 是退化的（上限 d·sqrt(p(1-p))），
                # 延迟版必须同时给 AUC，否则这一行读不出任何东西。
                if obs in BINARY:
                    m = y > 0.5
                    if m.sum() > 8 and (~m).sum() > 8:
                        a_real = auc_rankwise(x[m], x[~m])
                        # 轨迹内去均值要在**错位后的切片**上做，与产物里
                        # auc_within_traj 的口径一致。第一版写成
                        # `for r in hmc` —— 迭代的是字典的键（字符串），
                        # 而且对已经去过均值的 P_rnd 又去了一次。
                        lagx = {}
                        for r in recs:
                            T = r["T"]
                            if T - lag >= 8:
                                lagx[r["traj"]] = P_rnd[r["traj"]][:T - lag, :]
                        a_null = []
                        for k in range(N_RANDOM):
                            pj = np.concatenate([lagx[r["traj"]][:, k] for r in recs
                                                 if r["traj"] in lagx])
                            pj = pj - pj.mean()
                            a_null.append(auc_rankwise(pj[m], pj[~m]))
                        a_null = np.asarray([a for a in a_null if a == a])
                        q["auc"] = a_real
                        q["auc_null_mean"] = float(a_null.mean())
                        q["auc_null_sd"] = float(a_null.std())
                        q["auc_p_gt"] = float((a_null > a_real).mean())
                        line += (f"  | AUC={a_real:.4f} 零假设 "
                                 f"{a_null.mean():.4f}±{a_null.std():.4f} "
                                 f"p={q['auc_p_gt']:.4f}")
                        del lagx
                print(line, file=sys.stderr)
                del RX, RY, rxs, rys
            entry["folds"][f"fit{ff}_score{sf}"] = per_lag
            del P_real, P_rnd
        res["folds"][name] = entry

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print("wrote " + str(OUT))


if __name__ == "__main__":
    main()
