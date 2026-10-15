#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""r204 —— ⛔ 多点重复测「残差 std」的**分布**（解修订 201 §201.5 的单点限制）。

## 为什么有这个

修订 201 的定点扫描只用**一条轨迹的一个位置**，得出

    Δ(marker) 残差 std = 0.059052   SNR = 0.1225/0.059 ≈ 2.07

并明写：「上面所有数都来自**一条轨迹的一个位置**。⚠⚠⚴ 噪声 std 会不会随
位置/轨迹变，**没量过**。⛔ **不得**据此宣布「P6 可跑」」。

⚠⚠⚴ 本脚本量的就是那个「没量过」：在 **多条轨迹 × 多个位置**上重复同一道测量，
⚠⚠⚴ 报出残差 std 的**分布**，而不是它的单点值。

## 两条纪律（都来自本项目已付过代价的坑）

1. ⚠⚠⚴ **噪声底必须跨进程量。**
   同进程里重复跑 N 次是测不出非确定性的 —— 那些重复只证明「进程没动」。
   本脚本 `--driver` 为**每一格**拉起**独立子进程**。

2. ⚠⚠⚴ **一格一次只改一个变量。**
   每格只带 (traj, pos_frac)，其余（模型、层、marker 集合、w、α 网格）全同。

## 每格报三样

| 量 | 作用 |
|---|---|
| `resid_std` | 扣掉线性趋势后的残差标准差（= 噪声底） |
| `n_distinct` | Δ(marker) 的**不同取值个数** —— 量化是否随位置/轨迹变 |
| `min_adj_diff` | 最小相邻差 —— 是否有取整台阶，台阶是多少 |

⚠ 本脚本**只做测量**，不判「P6 能不能跑」。
⚠ 判定要等分布出来之后，由人按修订 201 §201.5 的口径来做。

用法：
    # 最小可跑样（先过这个，别直接跑全）
    python3 r204_noise_probe.py --cell --tid <TID> --pos-frac 0.5 --n-steps 20 …

    # 驱动：跨进程逐格测量
    python3 r204_noise_probe.py --driver --n-traj 5 --pos-fracs 0.25,0.5,0.75 \
        --n-steps 60 --out /tmp/r204.tsv …

退出码：0 成功 / 2 参数错 / 3 读不到轨迹 / 4 该格测量失败
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

MODEL = "/home/zhourui/.cache/huggingface/models/Qwen--Qwen3-1.7B/snapshots/master"
MARKER_IDS = [13824, 14190, 6771, 10061, 7196, 88190, 80022]
CONTROL_ID = 279          # ' the '
LAYER = 20


def cuda_visible_for(uuid):
    """把 `--gpu-uuid` 的值转成 `CUDA_VISIBLE_DEVICES` 该有的样子。

    ⚠⚠⚴ **`CUDA_VISIBLE_DEVICES` 要的是带 `GPU-` 前缀的完整 UUID。**
    ⚠⚠⚴ 我移植 r201 时**只抄了注释没抄逻辑**（注释写着「脚本自己拼 GPU-」，
    ⚠⚠⚴ 代码却是裸赋值）⇒ 每一格都 `RuntimeError: No CUDA GPUs are
    ⚠⚠⚴ available`，整轮 10/10 全废且只有一行 stderr。
    ⚗⇒ 抽出来单测：前缀缺失、前缀重复、None 三态都要验。
    """
    if not uuid:
        return None
    return uuid if uuid.startswith("GPU-") else "GPU-" + uuid


def analyze(alphas, dm, dc, gap=None, band=60.0):
    """把一条 α 扫描折成 {slope, resid_std, n_distinct, min_adj_diff, …}。

    ⚠⚠⚴ 抽出来是为了**能在无 GPU 的合成数据上自检** ——
    ⚠⚠⚴ 「残差 std 算得对不对」这件事本身此前从未被验过，
    ⚠⚠⚴ 而它是修订 201 §201.5 要测的那个量的**定义**。
    ⚗⇒ 见 `r204_noise_selftest.py`（四组：已知噪声 / 无噪声 / 量化台阶 / 斜率复原）。

    ⚠⚠⚴ `gap` 给了之后额外报 **P9 相关量**：
    ⚠⚠⚴ P9 的剂量是 `α = rel × class_gap`，rel ∈ {0.5, 1.0}。gap≈113 ⇒
    ⚠⚠⚴ **α=113.5 那一档落在第一遍的扫域（±60）之外**，
    ⚠⚠⚴ 那个域里量到的斜率**不能**替 P9 说话。⚗ 本函数因此显式报：
      p9_lo / p9_hi   线性拟合在 α=0.5·gap 与 α=1.0·gap 处的**预测**读数
      p9_se_hi        该预测的**标准误**（含残差与外推距离两项）
      p9_up_mono      预测是否满足 P9 的「+w 随剂量升」
      p9_margin_se    两档预测差 / 标准误（≳1 才谈得上「压得住噪声」）
    """
    import numpy as np
    alphas = np.asarray(alphas, dtype=float)
    dm = np.asarray(dm, dtype=float)
    dc = np.asarray(dc, dtype=float)
    A = np.vstack([alphas, np.ones_like(alphas)]).T
    coef, *_ = np.linalg.lstsq(A, dm, rcond=None)
    resid = dm - A.dot(coef)
    ad = np.abs(np.diff(dm))
    ad = ad[ad != 0.0]
    ac = np.abs(np.diff(dc))
    ac = ac[ac != 0.0]
    # ---- 两段拟合：局部(±band) vs 全域 ⇒ 线性还成不成立 ----
    # ⚠⚠⚴ 只报一个 resid_std 不够：若扫域比 P9 的工作区间大，
    # ⚠⚠⚴ 那个残差里混着「噪声」与「非线性」两样东西，分不开。
    # ⚗⇒ 同时做两段：局部带残差 ≈ 纯噪声；全域残差 ÷ 局部残差
    # ⚗   ≈ 1 ⇒ 线性成立；显著 >1 ⇒ 大剂量处弯了。
    m = np.abs(alphas) <= band
    if int(m.sum()) >= 5 and float(alphas[m].std()) > 0:
        cl, *_ = np.linalg.lstsq(A[m], dm[m], rcond=None)
        rl = dm[m] - A[m].dot(cl)
        rstd_local = float(rl.std(ddof=1))
        slope_local = float(cl[0])
    else:
        rstd_local, slope_local = float("nan"), float("nan")
    out = {
        "slope": float(coef[0]),
        "resid_std": float(resid.std(ddof=1)),
        "slope_local": slope_local,
        "resid_std_local": rstd_local,
        "lin_ratio": (float(resid.std(ddof=1)) / rstd_local)
                     if rstd_local == rstd_local and rstd_local > 0 else float("nan"),
        "n_distinct": int(len({round(float(x), 9) for x in dm})),
        "min_adj_diff": float(ad.min()) if ad.size else 0.0,
        "ctl_n_distinct": int(len({round(float(x), 9) for x in dc})),
        "ctl_min_adj_diff": float(ac.min()) if ac.size else 0.0,
        "dm_min": float(dm.min()),
        "dm_max": float(dm.max()),
    }
    if gap:
        n = alphas.size
        xbar = float(alphas.mean())
        sxx = float(((alphas - xbar) ** 2).sum())
        rstd_ = out["resid_std"]
        a_lo, a_hi = 0.5 * gap, 1.0 * gap
        f = lambda x: float(coef[0] * x + coef[1])
        se = lambda x: rstd_ * float(np.sqrt(1.0 + 1.0 / n + (x - xbar) ** 2 / sxx))
        out.update({
            "gap": float(gap),
            "p9_lo": f(a_lo), "p9_hi": f(a_hi),
            "p9_se_lo": se(a_lo), "p9_se_hi": se(a_hi),
            "p9_up_mono": bool(f(a_hi) >= f(a_lo)),
            "p9_margin_se": abs(f(a_hi) - f(a_lo)) / se(a_hi) if se(a_hi) > 0 else float("inf"),
        })
    return out


def run_cell(a):
    """量一格：扫 α，拟直线，回报残差 std / 不同值个数 / 最小相邻差。"""
    import numpy as np
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    _cv = cuda_visible_for(a.gpu_uuid)
    if _cv:
        os.environ["CUDA_VISIBLE_DEVICES"] = _cv

    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL, torch_dtype=torch.bfloat16).cuda().eval()

    z = np.load(os.path.join(a.npz_dir, a.tid + ".npz"))
    gen = z["token_ids"].tolist()
    z.close()
    cti = json.load(open(Path(a.sidecar_dir) / (a.tid + ".json"), encoding="utf-8"))
    pid = tok(cti["chat_template_input"], return_tensors="pt",
              add_special_tokens=False).input_ids[0].tolist()
    P = (cti.get("extra") or {}).get("prompt_tokens") or len(pid)
    n = len(gen)
    t = max(1, int(n * a.pos_frac))
    ids = torch.tensor([(pid + gen)[: P + t]], dtype=torch.long, device="cuda:0")
    inj = ids.shape[1] - 1

    W = np.load(a.w)
    mk = torch.tensor(MARKER_IDS, device="cuda:0")
    ctl = torch.tensor([CONTROL_ID], device="cuda:0")

    def lse_t(v):
        return float(torch.logsumexp(v, dim=-1).item())

    def forward(vec, alpha):
        blk = model.model.layers[LAYER]

        def pre(mod, inp):
            if alpha == 0.0:
                return None
            h = inp[0]
            v = torch.as_tensor(vec, dtype=h.dtype, device=h.device)
            h = h.clone()
            h[:, inj, :] = h[:, inj, :] + alpha * v
            return (h,) + inp[1:]

        hk = blk.register_forward_pre_hook(pre)
        try:
            with torch.no_grad():
                o = model(input_ids=ids, use_cache=False, return_dict=True)
        finally:
            hk.remove()
        return o.logits[0, -1].float()

    base = forward(W, 0.0)
    b_mark = lse_t(base[mk])
    b_ctl = lse_t(base[ctl])

    alphas = np.linspace(-a.alpha_max, a.alpha_max, a.n_steps)
    dm, dc = [], []
    for al in alphas:
        lg = forward(W, float(al))
        dm.append(lse_t(lg[mk]) - b_mark)
        dc.append(lse_t(lg[ctl]) - b_ctl)

    st = analyze(alphas, dm, dc, gap=a.gap, band=a.band)
    out = {"tid": a.tid, "pos_frac": a.pos_frac, "t": t, "n_gen": n, "P": P,
           "n_steps": int(a.n_steps)}
    out.update(st)
    # ⚠⚠⚴ flush：⛔ 不加的话，重定向到日志文件时 print 被**块缓冲**，
    # ⚠⚠⚴ 进度要等进程退出才刷出来 —— 于是「跑到第几格」这件事**看不见**。
    # ⚗ 与浏览器探针那个「等不到看不见」是同一类毛病（修订 205 之外那笔）。
    print("RESULT r204_cell  %s pos=%.2f  resid_std=%.6f  n_distinct=%d/%d  "
          "min_adj=%.6f  slope=%.6f"
          % (a.tid, a.pos_frac, st["resid_std"], st["n_distinct"], a.n_steps,
             st["min_adj_diff"], st["slope"]), flush=True)
    print(json.dumps(out, ensure_ascii=False))
    return out


def pick_tids(a):
    """从标注里挑 n_traj 条**有 marker** 的轨迹。"""
    rows = json.load(open(a.labels, encoding="utf-8"))
    rows = rows["rows"] if isinstance(rows, dict) and "rows" in rows else rows
    out = []
    for r in rows:
        tid = r.get("traj")
        if not tid:
            continue
        if not (Path(a.npz_dir) / (tid + ".npz")).exists():
            continue
        if not (Path(a.sidecar_dir) / (tid + ".json")).exists():
            continue
        out.append(tid)
        if len(out) >= a.n_traj:
            break
    return out


def run_driver(a):
    """⚠⚠ 每一格一个**独立子进程** —— 噪声底必须跨进程量。"""
    tids = pick_tids(a)
    if not tids:
        print("[错误] 找不到可用的轨迹（npz/sidecar 缺失）")
        return 3
    fracs = [float(x) for x in a.pos_fracs.split(",") if x.strip()]
    print("=== 驱动：%d 条轨迹 × %d 个位置 = %d 格，每格独立进程 ==="
          % (len(tids), len(fracs), len(tids) * len(fracs)))
    print("    每格 α 网格 %d 点，α ∈ [−%.1f, +%.1f]"
          % (a.n_steps, a.alpha_max, a.alpha_max))

    rows = []
    for tid in tids:
        for fr in fracs:
            cmd = [sys.executable, os.path.abspath(__file__), "--cell",
                   "--npz-dir", a.npz_dir, "--sidecar-dir", a.sidecar_dir,
                   "--labels", a.labels, "--w", a.w, "--tid", tid,
                   "--pos-frac", str(fr), "--n-steps", str(a.n_steps),
                   "--alpha-max", str(a.alpha_max)]
            cmd += ["--band", str(a.band)]
            if a.gap is not None:
                cmd += ["--gap", str(a.gap)]
            if a.gpu_uuid:
                cmd += ["--gpu-uuid", a.gpu_uuid]
            p = subprocess.run(cmd, capture_output=True, text=True)
            line = [l for l in p.stdout.splitlines() if l.startswith("{")]
            if p.returncode != 0 or not line:
                print("  ⛔ %s pos=%.2f 失败 rc=%d: %s"
                      % (tid, fr, p.returncode, (p.stderr or p.stdout)[-300:]))
                continue
            rows.append(json.loads(line[-1]))
            r = rows[-1]
            extra = ""
            if "p9_up_mono" in r:
                extra = ("  p9: lo=%+.4f±%.4f hi=%+.4f±%.4f mono=%s margin=%.2fSE"
                         % (r["p9_lo"], r["p9_se_lo"], r["p9_hi"], r["p9_se_hi"],
                            r["p9_up_mono"], r["p9_margin_se"]))
            print("  [%d/%d] %s pos=%.2f  resid=%.6f  slope=%+.6f%s"
                  % (len(rows), len(tids) * len(fracs), tid, fr,
                     r["resid_std"], r["slope"], extra), flush=True)

    # ⚠⚠⚴ 0 格成功时原来直接 `rows[0]` ⇒ **IndexError**，而真正的错误
    # ⚠⚠⚴ （10 格各自的 stderr）在上面 10 行里。⇒ 必须自己先说清楚。
    if not rows:
        print("⛔⛔ **0/%d 格成功** —— 产物没写。"
              % (len(tids) * len(fracs)))
        print("   ⚠ 各格失败原因见上面 ⛔ 行（**第一处通常是根因**）。")
        return 4
    if a.out:
        with open(a.out, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            for r in rows:
                w.writerow(r)
        print("已写 %s（%d 行）" % (a.out, len(rows)))

    # ---- 分布，不是单点 ----
    if rows:
        import statistics
        rs = sorted(r["resid_std"] for r in rows)
        nd = sorted(r["n_distinct"] for r in rows)
        print()
        print("=== 残差 std 的**分布**（%d 格）===" % len(rs))
        print("  min=%.6f  中位=%.6f  max=%.6f  极差=%.6f"
              % (rs[0], statistics.median(rs), rs[-1], rs[-1] - rs[0]))
        print("  ⚠ 修订 201 的单点值是 **0.059052**；")
        print("  ⚠ 若本分布的极差远大于 0 ⇒ 单点值不能代表全局。")
        print("  不同取值个数 n_distinct：min=%d 中位=%d max=%d（上限 %d 点）"
              % (nd[0], statistics.median(nd), nd[-1], rows[0]["n_steps"]))


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--npz-dir", required=True)
    ap.add_argument("--sidecar-dir", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--w", required=True)
    ap.add_argument("--gpu-uuid", default=None, help="**裸 UUID**（不带 GPU- 前缀）")
    ap.add_argument("--cell", action="store_true", help="只量一格")
    ap.add_argument("--driver", action="store_true", help="驱动多格（每格独立进程）")
    ap.add_argument("--tid", default=None)
    ap.add_argument("--pos-frac", type=float, default=0.5)
    ap.add_argument("--pos-fracs", default="0.25,0.5,0.75")
    ap.add_argument("--n-traj", type=int, default=5)
    ap.add_argument("--n-steps", type=int, default=60)
    ap.add_argument("--alpha-max", type=float, default=120.0,
                    help="⚠ 必覆盖 P9 的最高剂量 α=1.0×class_gap（≈113.5）")
    ap.add_argument("--band", type=float, default=60.0,
                    help="局部拟合带（±band）；band < alpha-max 才能分辨非线性")
    ap.add_argument("--gap", type=float, default=None,
                    help="w 的 class_gap（取自 w*.npy.json）。给了就额外报 P9 量")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    if a.cell:
        if not a.tid:
            print("[错误] --cell 需要 --tid")
            return 2
        run_cell(a)
        return 0
    if a.driver:
        return run_driver(a)
    print("[错误] 要么 --cell，要么 --driver")
    return 2


if __name__ == "__main__":
    sys.exit(main())
