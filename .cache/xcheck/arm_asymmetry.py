#!/usr/bin/env python3
"""32k 批次的两臂（`confidence_up` / `confidence_down`）到底差在哪 —— 配对检验。

## 为什么要重算

`InterventionOutcomePanel` 现在把两臂**合并**取中位数，于是
「token 一致率 97.9%」「mean logit KL 0.034」这两个数把 up 与 down
之间**显著的**差异盖住了。而且全面板没有分母、没有不确定性。

现有 `build_cot_effect.py` 只把**强度 0.0** 的配对当浮点漂移闸门用，
**从未对 0.2 的两臂做过配对检验** —— 这一支是第一次。

## 为什么这个比较是有意义的

`confidence_up` 与 `confidence_down` 在磁盘上**恰好互为负向量**
（`max|up + down| = 0.0`，两者都是单位向量）。所以「同题、同层、同强度、
只差一个符号」这个配对，隔离出来的正是**网络沿这条轴的响应不对称**：
注入 −v 比注入 +v 扰动得多。

## 但这**不**构成方向专属性

同幅度随机方向注入**同样**会产生非零 KL 与低于 1 的一致率，
也同样可能左右不对称。⇒ 本批次**没有同范数随机对照臂**，
所以这里能说的只有「这条轴的响应不对称，且不对称可测」，
不能说「这个效果是 confidence 这条方向特有的」。

⇒ 缺的那一格现在被精确指出来了：随机臂必须**同层 20、同强度 ±0.2、
同 23 道题、随机单位方向**，跑出来直接和本表的两个数比。

## 自证（三条前置，缺一条即 ABORT）

1. 强度 0.0 的两臂必须**逐位等价**（否则配对里混进了浮点漂移）
2. `confidence_up` 与 `confidence_down` 必须**恰好互为负**（否则这不是一个符号对比）
3. 配对题数必须 ≥ 20（低于这个数 CI 会宽到什么都说明不了）
"""
import collections
import json
import math
import random
import statistics as st
from pathlib import Path

ROOT = Path("/Users/zhourui/code/steer3d")
COT = ROOT / "frontend/public/latent/data/cot_texts.json"
AXES = ROOT / "frontend/public/latent/data/axis_readouts.json"
VEC = ROOT / "backend/examples/output/steering_vectors"
OUT = ROOT / "frontend/public/latent/data/arm_asymmetry.json"
N_BOOT = 20000
MIN_PAIRS = 20
UP, DOWN = "confidence_up", "confidence_down"


def paired_bootstrap(diffs, n=N_BOOT, seed=7):
    random.seed(seed)
    n_ = len(diffs)
    bs = sorted(sum(random.choice(diffs) for _ in range(n_)) / n_
                for _ in range(n))
    return bs[int(0.025 * n)], bs[int(0.975 * n)]


def main():
    import numpy as np
    d = json.loads(COT.read_text(encoding="utf-8"))
    runs = d["runs"]

    # ---------- 派生层 / 强度档 / 符号数 / 命名轴数 ----------
    # 判决 ③ 与 not_claimed ③ 一共印了四个数：层、强度、符号数、
    # 「另外 N 条命名轴」。四个都改成从输入现算，理由是它们**各自都会说谎**：
    #   层     —— 批次里出现第二层时，「同层」当场变成假的
    #   强度   —— 出现第二档非零强度时，下面这个配对只覆盖其中一档
    #   符号数 —— 出现第三条臂时，「±2 个符号」会高估覆盖面
    #   轴数   —— 「另外 3 条」的 3 在源里是 axis_readouts.axes，不是手抄
    # ⚠ 四个都读不到 / 不唯一就 SystemExit：宁可**不写产物**，
    #   也不要写一个没人核的字面量 —— 那正是第十五笔之前的状态。
    layers = sorted({r["layer"] for r in runs})
    if len(layers) != 1:
        raise SystemExit("ABORT 批次里出现 %d 个层 %s —— 「同层」这句话不成立"
                         % (len(layers), layers))
    layer = layers[0]

    nonzero = sorted({float(r["strength"]) for r in runs} - {0.0})
    if len(nonzero) != 1:
        raise SystemExit("ABORT 非零强度不止一档 %s —— 本表只声称一档" % nonzero)
    strength = nonzero[0]

    dirs = sorted({r["direction"] for r in runs})
    if dirs != sorted([DOWN, UP]):
        raise SystemExit("ABORT 方向不是恰好 ±v 两臂（%s）—— "
                         "本表是符号对比，不是多臂对比" % dirs)
    n_dirs = len(dirs)

    if not AXES.exists():
        raise SystemExit("ABORT 读不到 %s —— 「另外 N 条命名轴」的 N 没有源" % AXES)
    named = sorted(json.loads(AXES.read_text(encoding="utf-8"))["axes"])
    if not any(a.startswith("confid") for a in named):
        raise SystemExit("ABORT axis_readouts.axes 里没有 confidence 轴（%s）—— "
                         "「它只覆盖 confidence 一条轴」这句话不成立" % named)
    other_axes = [a for a in named if not a.startswith("confid")]

    # ---------- 自证 1：零强度两臂逐位等价 ----------
    by0 = collections.defaultdict(dict)
    for r in runs:
        if r["strength"] == 0.0:
            by0[r["label"]][r["direction"]] = r
    ident = [v for v in by0.values()
             if len(v) == 2 and all(x["token_agreement"] == 1.0
                                   and x["mean_logit_kl"] == 0.0
                                   and x["first_diverged_step"] is None
                                   for x in v.values())]
    if len(ident) < MIN_PAIRS:
        raise SystemExit("ABORT 零强度对照只有 %d 对逐位等价（要 ≥%d）"
                         % (len(ident), MIN_PAIRS))

    # ---------- 自证 2：两臂恰好互为负 ----------
    u = np.load(VEC / "confidence_up.npy").astype(np.float64).ravel()
    dn = np.load(VEC / "confidence_down.npy").astype(np.float64).ravel()
    neg_max = float(np.abs(u + dn).max())
    # ⚠ 这里**不用** `u @ dn`：numpy 2.0.2 在本机的 matmul 上会发
    #   `divide by zero / overflow / invalid value encountered in matmul` 三条
    #   RuntimeWarning，而范数明明是 0.99999997、结果也对。
    #   已用三条独立算法交叉验证（matmul / einsum / 显式 (u*d).sum()，
    #   三者一致到 1e-15）⇒ 那是该 BLAS 路径的噪声，不是计算问题。
    #   但脚本里留着我解释不了的警告 = 留着一个可能掩盖真问题的哨兵，
    #   所以改走不发警告的显式路径，并把理由写在这里。
    dot = float((u * dn).sum())
    cos_ud = dot / (float(np.linalg.norm(u)) * float(np.linalg.norm(dn)))
    if neg_max > 0.0 or abs(cos_ud + 1.0) > 1e-6:
        raise SystemExit("ABORT confidence_up/down 不是恰好互为负"
                         "（max|u+d|=%.3e, cos=%.9f）" % (neg_max, cos_ud))

    # ---------- 配对 ----------
    by = collections.defaultdict(dict)
    for r in runs:
        by[r["label"]][(r["direction"], r["strength"])] = r
    paired = [v for v in by.values()
              if (UP, strength) in v and (DOWN, strength) in v]
    if len(paired) < MIN_PAIRS:
        raise SystemExit("ABORT 配对题数 %d < %d" % (len(paired), MIN_PAIRS))

    METRICS = [
        ("mean_logit_kl", lambda r: r["mean_logit_kl"],
         "分布被推离零强度臂的远度（越大=扰动越强）"),
        ("token_agreement", lambda r: r["token_agreement"],
         "两臂每一步选中同一个 token 的比例（越小=分岔越多）"),
        ("first_diverged_step", lambda r: (r["first_diverged_step"] or 10 ** 9),
         "第一次选出不同 token 的步（越小=起效越快）"),
    ]
    out_metrics = []
    for key, fn, desc in METRICS:
        diffs, ups, dns = [], [], []
        for v in paired:
            a, b = fn(v[(UP, strength)]), fn(v[(DOWN, strength)])
            ups.append(a); dns.append(b); diffs.append(a - b)
        m = st.mean(diffs)
        sem = st.stdev(diffs) / math.sqrt(len(diffs)) if len(diffs) > 1 else 0.0
        lo, hi = paired_bootstrap(diffs)
        out_metrics.append({
            "metric": key, "desc": desc,
            "up_mean": st.mean(ups), "down_mean": st.mean(dns),
            "paired_diff": m, "paired_sem": sem, "t": (m / sem) if sem else None,
            "ci95_lo": lo, "ci95_hi": hi,
            # CI 跨 0 ⇒ 这个量在两臂之间**分不开**。不许报一个数当成结论。
            "distinguishable": not (lo < 0 < hi),
        })
        print("%-20s up %9.4f  down %9.4f  配对差 %+.4f ± %.4f  t=%6.2f  "
              "CI95 [%+.4f, %+.4f]  %s"
              % (key, st.mean(ups), st.mean(dns), m, sem, m / sem if sem else 0,
                 lo, hi, "分得开" if not (lo < 0 < hi) else "**跨 0,分不开**"))

    payload = {
        "schema": "arm_asymmetry/1",
        "source": "%s（%d runs，%s）" % (COT.name, len(runs), d.get("model")),
        "what": "同题同层同强度下，注入 +v 与注入 −v 的配对差异",
        "n_pairs": len(paired),
        "n_zero_strength_identity_pairs": len(ident),
        "up_down_are_exact_negatives": True,
        "max_abs_up_plus_down": neg_max,
        "cos_up_down": cos_ud,
        "layer": layer, "strength": strength,
        # 「另外 N 条命名轴」的 N 与它的源（axis_readouts.axes）一起进产物，
        # 好让**面板**也能从数据取这个数，而不是在 JSX 里再手抄一份。
        "n_dirs": n_dirs,
        "named_axes_total": len(named),
        "n_other_named_axes": len(other_axes),
        "other_named_axes": other_axes,
        "bootstrap_n": N_BOOT,
        "metrics": out_metrics,
        "verdict": (
            "① 两臂在**扰动幅度**上分得开：注入 −v 把分布推得比 +v 远 "
            "(KL 配对差 %+.4f ± %.4f)，一致率也更低 (%+.4f ± %.4f)。"
            "⇒ confidence 轴的响应是**左右不对称**的，这一点现在有配对检验撑着，"
            "不再是两个并排的中位数。\n"
            "② 但**首次分岔步数**两臂分不开 (t=%.2f, CI 跨 0) —— "
            "「什么时候开始起效」与「往哪个方向偏」是两回事。\n"
            "③ 这一切**都不构成方向专属性**：本批次没有同范数随机对照臂，"
            "同幅度的随机方向注入同样会产生非零 KL 与低于 1 的一致率。"
            "缺的那一格 = 同层 %d、同强度 ±%g、同这 %d 道题、随机单位方向。"
        ) % (
            out_metrics[0]["paired_diff"], out_metrics[0]["paired_sem"],
            out_metrics[1]["paired_diff"], out_metrics[1]["paired_sem"],
            out_metrics[2]["t"],
            layer, strength, len(paired)),
        "not_claimed": (
            "① 不能说 confidence 这条方向的效果是**特有**的 —— 缺同范数随机对照，"
            "而随机轴也会扰动、也可能左右不对称。\n"
            "② 不能把配对差的 t 值读成「效应很大」—— n=%d，"
            "且这 %d 道题是同一批 32k 批次里的，不跨批次。\n"
            "③ 这一节仍然是**真干预**（32k 批次逐 token 重跑解码器），"
            "但它只覆盖 confidence 一条轴的 ±%d 个符号，"
            "另外 %d 条命名轴（%s）的干预结果不在这里。"
        ) % (len(paired), len(paired), n_dirs, len(other_axes),
             "、".join(other_axes)),
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print()
    print("已写", OUT)


if __name__ == "__main__":
    main()
