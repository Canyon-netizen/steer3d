#!/usr/bin/env python3
"""独立复现 vector_roles.json 的 `heldout_non_circular` —— 项目里唯一的
非循环证据，也是主张四（方向指哪）唯一的指望。

上一轮的角色扮演报告说「需要第二遍重拟合+重打分」，一直没做。现在做。

**为什么这块特别值得复现**：它前面的 `in_sample_circular` 是循环论证 ——
向量就是用这批 token 的两组均值差定义的，再拿回同一批 token 与定义它的
标签求相关，通过与否是恒等式。只有两折交叉（在一半轨迹上重新拟合
contrast，在另一半打分）不是恒等式。而 `unmeasured` 里又明说
`heldout_non_circular` 只覆盖 L14。

**独立性怎么保证**：统计量、分折逻辑、投影、打分全部自己写。
只有*分组谓词*（熵的 30/70 分位、self_check 正则、think 块、轨迹首尾 25%）
刻意与 analyse_vector_roles.py 保持一致 —— 谓词一漂，测的就不是同一个概念
了，那比数字对不上更糟。脚本里对此写了断言。

装置自检：先用一个小玩具折（4 条合成轨迹、已知的均值差方向）跑通，
确认 rho 和 AUC 都算得出来，再上真数据。
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
from scipy import stats

ROOT = Path("/Users/zhourui/code/steer3d")
NPZ_DIR = ROOT / "datasets/aime_qwen3_1p7b_16k_fp16/aime"
SHIPPED = ROOT / "frontend/public/latent/data/vector_roles.json"
OUT = ROOT / ".cache/rolesverify/heldout_recheck.json"
LAYER = 14

# 与 analyse_vector_roles.py 保持一致（谓词漂移 = 测的不是同一个概念）
SELF_CHECK_RE = re.compile(
    r"\b(wait|actually|hmm|hold on|let me check|let me verify|recheck|"
    r"double[- ]check|second thought|alternatively|but wait)\b",
    re.IGNORECASE,
)
CONTRASTS = {
    "confidence_up": ("entropy_lo", "entropy_hi"),
    "confidence_down": ("entropy_hi", "entropy_lo"),
    "caution": ("self_check_yes", "self_check_no"),
    "creativity": ("think_yes", "think_no"),
    "reasoning_deep": ("late", "early"),
    "reasoning_shallow": ("early", "late"),
}
CLAIMS = {
    "confidence_up": ("entropy", -1),
    "confidence_down": ("entropy", +1),
    "caution": ("self_check", +1),
    "creativity": ("in_think", +1),
    "reasoning_deep": ("step_frac", +1),
    "reasoning_shallow": ("step_frac", -1),
}
BINARY = ("self_check", "in_think", "top1_switch")


# ---------------------------------------------------------------- 统计量
def rho_rank(xs, ys):
    """Spearman rho。两侧有常量时返回 nan（rho 无定义）。"""
    if len(xs) < 4:
        return float("nan")
    r = stats.spearmanr(xs, ys).statistic
    return float(r) if r == r else float("nan")


def auc_rankwise(pos, neg):
    """P(随机正样本投影 > 随机负样本投影)，Mann-Whitney U 归一化。"""
    n1, n2 = len(pos), len(neg)
    if n1 == 0 or n2 == 0:
        return float("nan")
    ranks = stats.rankdata(np.concatenate([pos, neg]))
    return float((ranks[:n1].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n2))


def floor_traj(n):
    """1/sqrt(n-3)：抽样噪声的量级。**分母用轨迹数**，不用步数 ——
    相邻解码步强自相关，按步数算会低估两个数量级。"""
    return float(1.0 / np.sqrt(n - 3)) if n >= 4 else float("nan")


def floor_auc(n1, n2):
    """Mann-Whitney 零假设 SE，刻意当**下界**而不是校准过的门槛。"""
    if n1 == 0 or n2 == 0:
        return float("nan")
    return float(np.sqrt((n1 + n2 + 1) / (12.0 * n1 * n2)))


# ---------------------------------------------------------------- 谓词
def read_side(p: Path, T: int):
    """从 npz 的 sidecar .json 读逐步可观测量。"""
    meta = json.loads(p.read_text())
    toks = meta.get("tokens", [])
    if len(toks) != T:
        return None
    ent = np.asarray([t["entropy"] for t in toks], np.float32)
    think = np.asarray([bool(t.get("is_in_think_block", False)) for t in toks], np.float32)
    sc = np.asarray([bool(SELF_CHECK_RE.search(t.get("token") or "")) for t in toks], np.float32)
    frac = np.arange(T, dtype=np.float32) / max(T - 1, 1)
    q30, q75 = float(np.quantile(ent, 0.30)), float(np.quantile(ent, 0.75))
    masks = {
        "entropy_lo": ent <= q30, "entropy_hi": ent >= q75,
        "self_check_yes": sc > 0.5, "self_check_no": sc < 0.5,
        "think_yes": think > 0.5, "think_no": think < 0.5,
        "late": frac >= 0.75, "early": frac <= 0.25,
    }
    return {"traj": meta.get("trajectory_id", p.stem), "T": T,
            "entropy": ent, "self_check": sc, "in_think": think,
            "step_frac": frac, "masks": masks}


# ---------------------------------------------------------------- 自检
def toy_check():
    """玩具折：造 4 条轨迹，正组恒在 +x₀ 方向上。

    两个观测量各查各的，**不能用同一个阈值**：

      * 连续标签 → rho 应接近 1
      * 二元标签 → AUC 应接近 1，而 rho **到不了** 1

    第二条是本项目的核心统计陷阱：对 0/1 结果，Spearman 退化成点二列相关，
    其上限是 d·sqrt(p(1−p))。基率 0.3、几乎完美分离时也只有 0.76 左右 ——
    所以拿 1/sqrt(n−3) 当门槛去卡它，量的其实是基率而不是方向。
    这也是产物里二元观测量改用 AUC 门槛的原因。
    第一版把阈值写成 rho>0.9，被自己的玩具输入判红 —— 错的是阈值。
    """
    rs = np.random.default_rng(7)
    xs, yc, yb = [], [], []
    for _ in range(4):
        h = rs.standard_normal((400, 16)).astype(np.float32)
        lab = rs.random(400) < 0.3
        h[lab, 0] += 3.0
        v = np.zeros(16, np.float32); v[0] = 1.0
        p = h @ v
        xs.append(p)
        # 真正**连续**且与投影单调等价的标签：Spearman 对它必须 ≈ 1。
        # 第二版误写成 lab + 0.2·噪声 —— 那是二元结构加抖动，rho 照样被
        # 基率卡在 0.59，是我的期望值不对，不是装置不对。
        yc.append(p + rs.standard_normal(400) * 0.01)
        yb.append(lab.astype(np.float32))
    px, pyc, pyb = np.concatenate(xs), np.concatenate(yc), np.concatenate(yb)
    r_cont = rho_rank(px, pyc)
    r_bin = rho_rank(px, pyb)
    a = auc_rankwise(px[pyb > 0.5], px[pyb < 0.5])
    ok = r_cont > 0.95 and a > 0.95 and 0.3 < r_bin < 0.95
    print(f"[自检] 连续标签 rho={r_cont:.4f}（应≈1）  "
          f"二元标签 AUC={a:.4f}（应≈1）  "
          f"二元 rho={r_bin:.4f}（受基率限制，达不到 1）-> {'OK' if ok else '装置有问题'}")
    if not ok:
        raise SystemExit("ABORT 玩具输入都不对，后面的数字没有意义")
    return ok


def main():
    toy_check()
    files = sorted(p for p in NPZ_DIR.glob("*.npz") if p.with_suffix(".json").exists())
    print(f"records with sidecar: {len(files)}")

    # 分折**按题目**，不按文件位置。文件是 ..._no_think / ..._think 交替排的，
    # 按位置切会把所有 no_think 放进一折、所有 think 放进另一折 ——
    # 于是 creativity 那个 contrast 变成在测「运行模式」而不是在测 think 块。
    probs = {}
    for p in files:
        probs.setdefault(p.stem.rsplit("__", 1)[0], []).append(p)
    order = sorted(probs)
    fold_of = {p.stem: (i % 2) for i, base in enumerate(order) for p in probs[base]}
    n_fold = {f: sum(1 for v in fold_of.values() if v == f) for f in (0, 1)}
    print(f"problems={len(order)}  fold sizes={n_fold}")

    # pass A：按折累计两组的均值向量
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
        print(f"  pass A {p.stem} T={T}", file=sys.stderr)

    def fit(f, pos, neg):
        a, b = sums.get((f, pos)), sums.get((f, neg))
        na, nb = cnts.get((f, pos), 0), cnts.get((f, neg), 0)
        if a is None or b is None or na < 30 or nb < 30:
            return None, na, nb
        u = (a / na) - (b / nb)
        return (u / (np.linalg.norm(u) + 1e-8)).astype(np.float32), na, nb

    # pass B：在另一折上打分
    proj = {0: {}, 1: {}}
    for f in (0, 1):
        for rec in meta[f]:
            with np.load(path_of[rec["traj"]]) as z:
                h = z["hidden_states"][:, LAYER, :].astype(np.float32)
            proj[f][rec["traj"]] = h
    print("  pass B: projections materialised", file=sys.stderr)

    res = {"schema": "rolesverify.heldout_recheck/1", "layer": LAYER,
           "n_fold": n_fold, "toy_selfcheck": "passed", "folds": {}}
    for name, (pos, neg) in CONTRASTS.items():
        obs, sign = CLAIMS[name]
        entry = {"observable": obs, "expected_sign": sign, "scores": {}}
        for ff in (0, 1):
            v, na, nb = fit(ff, pos, neg)
            if v is None:
                entry["scores"][f"fit{ff}"] = {"status": "too_few_tokens",
                                              "n_pos": na, "n_neg": nb}
                continue
            sf = 1 - ff
            xs = [proj[sf][r["traj"]] @ v for r in meta[sf]]
            ys = [r[obs] for r in meta[sf]]
            px, py = np.concatenate(xs), np.concatenate(ys)
            n_steps = len(px)
            rho = rho_rank(px, py)
            s = {"n_pos_tokens_in_fit": int(na), "n_neg_tokens_in_fit": int(nb),
                 "n_traj_scored": len(xs), "n_steps_scored": int(n_steps),
                 "rho": rho, "null_floor_by_traj": floor_traj(len(xs)),
                 "passes_gate": bool(sign * rho > floor_traj(len(xs)))}
            if obs in BINARY:
                n1 = int((py > 0.5).sum()); n2 = n_steps - n1
                # 轨迹内去均值：与 in-sample 门槛用同一个统计量，两块才可比
                xcw = np.concatenate([a - a.mean() for a in xs])
                a_w = auc_rankwise(xcw[py > 0.5], xcw[py < 0.5])
                s.update(base_rate=n1 / n_steps, n_positive_steps=n1,
                         n_negative_steps=n2, auc_within_traj=a_w,
                         auc_pooled=auc_rankwise(px[py > 0.5], px[py < 0.5]),
                         auc_null_floor_naive=floor_auc(n1, n2),
                         gate_statistic="auc_within_traj",
                         passes_gate=bool(a_w - 0.5 > floor_auc(n1, n2)))
            entry["scores"][f"fit{ff}_score{sf}"] = s
            print(f"{name:20s} fit{ff}->score{sf}  rho={rho:+.4f} "
                  f"floor={s['null_floor_by_traj']:.4f} pass={s['passes_gate']}"
                  + (f"  auc_w={s.get('auc_within_traj', float('nan')):.4f}"
                     if obs in BINARY else ""), file=sys.stderr)
        res["folds"][name] = entry

    # ---- 与产物逐值比对 ----
    ship = json.loads(SHIPPED.read_text())["necessity"]["heldout_non_circular"]
    cmp_rows, worst = [], 0.0
    for name in CONTRASTS:
        for key, s in res["folds"][name]["scores"].items():
            if "rho" not in s:
                continue
            ref = ship["folds"].get(name, {}).get("scores", {}).get(key)
            if ref is None:
                cmp_rows.append({"name": name, "key": key, "status": "MISSING_IN_ARTIFACT"})
                continue
            d_rho = abs(s["rho"] - ref["rho"])
            d_auc = (abs(s["auc_within_traj"] - ref["auc_within_traj"])
                     if "auc_within_traj" in s else 0.0)
            d_n = abs(s["n_steps_scored"] - ref["n_steps_scored"])
            d_gate = s["passes_gate"] != ref["passes_gate"]
            worst = max(worst, d_rho, d_auc)
            cmp_rows.append({"name": name, "key": key,
                             "rho_mine": s["rho"], "rho_ref": ref["rho"],
                             "d_rho": d_rho,
                             "auc_mine": s.get("auc_within_traj"),
                             "auc_ref": ref.get("auc_within_traj"),
                             "d_auc": d_auc,
                             "d_n_steps": d_n,
                             "gate_mine": s["passes_gate"], "gate_ref": ref["passes_gate"],
                             "gate_disagrees": d_gate})
    res["comparison"] = {
        "rows": cmp_rows,
        "max_abs_rho_diff": max((r.get("d_rho", 0.0) for r in cmp_rows), default=None),
        "max_abs_auc_diff": max((r.get("d_auc", 0.0) for r in cmp_rows), default=None),
        "max_abs_n_steps_diff": max((r.get("d_n_steps", 0) for r in cmp_rows), default=None),
        "n_gate_disagreements": sum(1 for r in cmp_rows if r.get("gate_disagrees")),
        "n_rows": len(cmp_rows),
    }
    c = res["comparison"]
    print()
    print(f"比对 {c['n_rows']} 行：max|Δrho|={c['max_abs_rho_diff']}  "
          f"max|Δauc|={c['max_abs_auc_diff']}  max|Δn|={c['max_abs_n_steps_diff']}  "
          f"门槛判定分歧 {c['n_gate_disagreements']}")

    # ------------------------------------------------------------------
    # 随机方向对照 —— 产物里没有，而它正是判据能不能定案的关键。
    #
    # `passes_gate` 对二元观测量用的是 Mann-Whitney 零假设 SE，脚本自己
    # 注明"steps 自相关，所以只当下界，不是校准过的门槛"。复现出的
    # `creativity` AUC = 0.5206/0.5226 就是这么过的：门槛小到
    # 任何非零偏移都算过。0.52 到底是效应还是噪声，光看门槛回答不了。
    #
    # 办法：同一条流水线（同样在一折上拟合、在另一折上打分、同样去均值
    # 算轨迹内 AUC）灌 200 个定长随机方向，看真实方向在这个分布里排第几。
    # 这与 subspace_frac 那边用的是同一套方法。
    K = 200
    rs = np.random.default_rng(20261003)
    rand = rs.standard_normal((K, 2048))
    rand /= np.linalg.norm(rand, axis=1, keepdims=True)
    null = {}
    for name, (pos, neg) in CONTRASTS.items():
        obs, sign = CLAIMS[name]
        null[name] = {}
        for ff in (0, 1):
            sf = 1 - ff
            ys = [r[obs] for r in meta[sf]]
            py = np.concatenate(ys)
            # 轨迹内去均值，与产物里 auc_within_traj / rho 的口径一致。
            # 流式累加，不 np.stack —— (24, 2048, 2048) 的 float32 是 400MB，
            # 再乘一份拷贝就危险了，而这里完全不需要那么写。
            pc = [proj[sf][r["traj"]] - proj[sf][r["traj"]].mean(axis=0, keepdims=True)
                  for r in meta[sf]]
            Xc = np.concatenate(pc, axis=0)                 # (sum T, d)
            if obs in BINARY:
                a = np.empty(K)
                for k in range(K):
                    pj = Xc @ rand[k]
                    a[k] = auc_rankwise(pj[py > 0.5], pj[py < 0.5])
                got = res["folds"][name]["scores"][f"fit{ff}_score{sf}"].get("auc_within_traj")
                null[name][f"fit{ff}_score{sf}"] = {
                    "statistic": "auc_within_traj",
                    "real": got,
                    "null_mean": float(a.mean()), "null_sd": float(a.std()),
                    "null_p95": float(np.percentile(a, 95)),
                    "null_max": float(a.max()),
                    "p_gt": float((a > got).mean()),
                }
            else:
                rhos = np.empty(K)
                for k in range(K):
                    rhos[k] = rho_rank(Xc @ rand[k], py)
                got = res["folds"][name]["scores"][f"fit{ff}_score{sf}"]["rho"]
                null[name][f"fit{ff}_score{sf}"] = {
                    "statistic": "rho",
                    "real": got,
                    "null_mean": float(rhos.mean()), "null_sd": float(rhos.std()),
                    "null_p95_abs": float(np.percentile(np.abs(rhos), 95)),
                    "null_max_abs": float(np.abs(rhos).max()),
                    "p_abs_gt": float((np.abs(rhos) >= abs(got)).mean()),
                }
            n = null[name][f"fit{ff}_score{sf}"]
            p = n.get("p_gt", n.get("p_abs_gt"))
            print(f"  null {name:20s} fit{ff}->sf{sf}  real={n['real']:+.4f}  "
                  f"零假设 {n['null_mean']:+.4f}±{n['null_sd']:.4f}  p={p:.4f}")
            del Xc, pc
    res["random_direction_control"] = {"n_random": K, "seed": 20261003,
                                       "note": "同一条流水线灌定长随机方向；"
                                               "产物本身没有这一项",
                                       "per_fold": null}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print("wrote " + str(OUT))


if __name__ == "__main__":
    main()
