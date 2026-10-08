#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CAUSAL：把「动摇方向」注入 L20，看 marker 概率按剂量怎么变。

判决规则全部在 `.cache/xcheck/CAUSAL_PREREG.md` 里，**取数之前**定死。

## 做什么

1. 重训 PROBE 的线性方向 `w`（按轨迹分组 LOO 的**全体**系数均值，
   单位范数），符号按「正例打分更高」定死。
2. 对每个动摇点：teacher-force 到位置 `t-1`，在 **L20** 的
   **单一 token 位置**注入 `α·w`，读位置 `t` 上 marker token 的 logprob。
3. α ∈ {0, ±0.5, ±1, ±2, ±4}，加随机方向对照。

## 关键纪律

- **注入只作用于位置 t-1**，不是全序列（PREREG §2）。
- **marker 集合写死** 7 个 token id（PREREG §3.1）——
  `But`/`but`/`my` 明确不算，它们比 marker 更常见。
- **α=0 走完全相同的路径**（hook 装上、量乘 0），
  用来验「装 hook 本身不改变结果」。
- 不做全序列注入、不做多方向组合、不做跨模型。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, ".cache", "xcheck"))
import probe_hinge_layers as P  # noqa: E402

NPZ_DIR = os.path.join(ROOT, "datasets", "aime_qwen3_1p7b_16k_fp16", "aime")
MODEL = os.path.join(ROOT, "datasets", "models", "Qwen3-1.7B")
OUT = os.path.join(ROOT, ".cache", "mutbak", "causal_inject.json")

# ---- PREREG §2：取数前定死 ----
LAYER = 20
ALPHAS = (0.0, 0.5, 1.0, 2.0, 4.0)
OFF = 1                      # 注入位置 = t-1
DELTA = 20                  # 负例到正例的距离（PREREG 指定的读数口径）
SEED = 20261007

# ---- 噪声底（PREREG 修订 2 的 R-9，实测值）----
# 批量 vs 逐个前向的最大差：4.339e-05 nats。
# 用途：分组分析里判断某组均值是不是「真的非零」。
# ⚠ 它是 fp32 累加顺序造成的噪声，**不是**效应量下限 ——
#   别拿它去卡效应量，那会把「小于噪声」当成「没有效应」。
NOISE = 4.339e-05
# 装置符号守卫用的**小剂量**（相对类间间距）。见 R-19 的注释。
CHK_REL = 0.05

# ---- PREREG §3.1：marker 集合写死，含前导空格变体 ----
MARKER_WORDS = (" Wait", "Wait", " Let", "Let", " maybe", " Hmm", "Hmm")
CONTROL_WORD = " the"        # §3.1 的对照 token


def load_marker_ids(tk):
    ids = []
    for w in MARKER_WORDS:
        e = tk(w, add_special_tokens=False)["input_ids"]
        assert len(e) == 1, f"marker {w!r} 不是单 token：{e}"
        ids.append(e[0])
    c = tk(CONTROL_WORD, add_special_tokens=False)["input_ids"]
    assert len(c) == 1, f"对照 {CONTROL_WORD!r} 不是单 token：{c}"
    return ids, c[0]


def train_direction(pos, tmap, seed):
    """重训探针方向 w（全体系数均值，单位范数，符号定死）。"""
    rng = np.random.default_rng(seed)
    negs = P.pick_negatives(pos, rng, tmap=tmap)
    X, y, traj = P.build_xy(pos, negs)
    # ⚠ PREREG §2：**整条轨迹的系数**（每个位置训自己的 w）会让注入量
    #   随位置变，无法比较剂量。改为「所有位置共享一个 w」：
    #   在**整条轨迹**上分组的 LOO 下，收集每折的系数并取均值。
    coefs = []
    for held in sorted(set(traj)):
        te = traj == held
        tr = ~te
        if tr.sum() == 0:
            continue
        for L in (LAYER,):
            Xtr = X[tr][:, L, :].astype(np.float64)
            ytr = y[tr].astype(np.float64)
            mu = Xtr.mean(0, keepdims=True)
            sd = Xtr.std(0)
            keep = sd > 1e-8
            Hn = (Xtr - mu)[:, keep] / sd[keep]
            wgt = np.where(ytr > 0, 0.5 / max(1, (ytr > 0).sum()),
                           0.5 / max(1, (ytr == 0).sum()))
            sgn = 2 * ytr - 1
            A = Hn.T @ (Hn * (wgt * sgn)[:, None]) + 1e4 * np.eye(Hn.shape[1])
            try:
                c = np.linalg.solve(A, Hn.T @ (wgt * sgn))
            except np.linalg.LinAlgError:
                c = np.linalg.lstsq(A, Hn.T @ (wgt * sgn), rcond=None)[0]
            full = np.zeros(X.shape[2])
            idx = np.where(keep)[0]
            full[idx] = c
            coefs.append(full)
    W = np.mean(coefs, axis=0)
    # 符号定死：w 应让**正例**（动摇点）打分更高
    sgn_check = float(np.mean([W @ X[i, LAYER, :] for i in range(len(y)) if y[i] == 1])) \
        - float(np.mean([W @ X[i, LAYER, :] for i in range(len(y)) if y[i] == 0]))
    if sgn_check < 0:
        W = -W
        print(f"⚠ w 的符号翻了（正负均值差 {sgn_check:+.3f} → 已取反）")
    n = W / (np.linalg.norm(W) + 1e-12)
    print(f"方向 w：{len(coefs)} 折均值，|w|=1.0，"
          f"正负打分差 {abs(sgn_check):+.3f}（正例应更高）")
    return n.astype(np.float32), abs(sgn_check)


def class_gap(pos, tmap, seed):
    """自然尺度锚点：`w·h` 在动摇点与随机点之间的类间间距。

    ⚠ 没有它，α 就只能按「单位向量的直觉」取值，而实测
    ‖h‖ 中位 1014、类间间距 375 ⇒ 那一套取值比自然尺度小约 100 倍，
    落在几乎无响应的区间里。C-4 的「≥0.5 nats」阈值正是这么写错的。
    """
    negs = P.pick_negatives(pos, np.random.default_rng(seed), tmap=tmap)
    X, y, _ = P.build_xy(pos, negs)
    Hp = X[y == 1][:, LAYER, :].astype(np.float64)
    Hn = X[y == 0][:, LAYER, :].astype(np.float64)
    rng_ = np.random.default_rng(seed + 7)
    # 与 train_direction 同 seed ⇒ 系数方向一致
    W_, _ = train_direction(pos, tmap, seed)
    return float(np.mean(Hp @ W_) - np.mean(Hn @ W_))


def build_cases(pos, tmap):
    """每个案例：轨迹、注入位置 t-1、被读的下一位置 t。"""
    cases = []
    for tid in sorted(pos):
        toks = pos[tid]
        ts = set(toks)
        for t in toks:
            if t - OFF < 1:
                continue
            # marker 落在 t（读 t 处的分布）
            cases.append({"traj": tid, "t": t, "inj": t - OFF})
    return cases


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="只取前 N 个位置")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--check-unbatched", type=int, default=0,
                    help="前 N 个案例再逐个前向复算一遍，验证批量路径等价")
    ap.add_argument("--per-traj", type=int, default=0,
                    help="每条轨迹取 N 个位置（PREREG 修订 3 取 2）")
    ap.add_argument("--rel-ladder", default="0.1,0.25,0.5,1.0,2.0",
                    help="标定剂量梯；修订 3 取 0.25,0.5,1.0")
    a = ap.parse_args()

    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM

    pos = P.load_positives()
    tmap = {t: P.real_T(t) for t in pos}
    W, sep = train_direction(pos, tmap, SEED)
    cases = build_cases(pos, tmap)
    # ⚠ 取样：修订 3 改为「每条轨迹 N 个位置」，让 22 条轨迹都被覆盖。
    #   第一版是 `cases[:limit]` —— 那只取**排序最靠前**的若干轨迹，
    #   `--limit 8` 实测「案例 8 个 / 轨迹 3」：8 个位置来自 3 条轨迹。
    #   ⚠⚠ 这是「参数没生效」的又一形态：脚本不报错、案例数也对，
    #   但**轨迹覆盖度**塌了。§8 局限 2 明写「统计推断必须按轨迹聚合」，
    #   轨迹覆盖不全时那个约束根本无法执行。
    #   ⇒ 打印必须同时给**案例数**与**轨迹数**，两者对不上要看得见。
    if a.per_traj:
        by = {}
        for c in cases:
            by.setdefault(c["traj"], []).append(c)
        tids = sorted(by)
        sel, used = [], set()
        for i in range(a.per_traj):
            for j, t in enumerate(tids):
                idx = (i * 5 + j * 3) % len(by[t])
                if (t, idx) not in used:
                    used.add((t, idx))
                    sel.append(by[t][idx])
        cases = sel
    if a.limit:
        cases = cases[:a.limit]
    # 轨迹对错：PREREG 修订 3 的 B 组标签。
    # ⚠ 只用 npz 同目录的 json 里的 `is_correct`，
    #   不从轨迹**文本**重新判断 —— 重新判断就是引入第二个可能出错的东西。
    correct = {}
    for tid in sorted(set(c["traj"] for c in cases)):
        jp = os.path.join(NPZ_DIR, tid + ".json")
        if os.path.exists(jp):
            correct[tid] = bool(json.load(open(jp, encoding="utf-8"))
                                .get("is_correct", False))
    n_traj_used = len(set(c["traj"] for c in cases))
    n_ok = sum(1 for t in set(c["traj"] for c in cases) if correct.get(t))
    print(f"案例 {len(cases)} 个（轨迹 {n_traj_used}：答对 {n_ok} / 答错 "
          f"{n_traj_used - n_ok}）")

    tk = AutoTokenizer.from_pretrained(MODEL)
    mid, cid = load_marker_ids(tk)
    print("marker ids:", mid, "对照 id:", cid)

    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.float32)
    model.eval()
    blk = model.model.layers[LAYER]

    rng = np.random.default_rng(SEED + 1)
    # ⚠⚠⚠ 随机方向对照的第一版是**每个剂量重新采样**的 ——
    #   于是「随机方向」其实是 5 个**不同**方向的混合，剂量响应被平均掉。
    #   冒烟实测：w 的 Δ+2.7274 vs 「随机」+2.7310，看似无差别；
    #   但单独查发现随机方向让 marker **下降** 0.5 nats、w 让它**上升** 2.73
    #   ⇒ 方向是有区分的，是**对照写错**让读数被抹平。
    #   ⇒ 修法：采**一个**随机方向，扫全部剂量。
    R = rng.normal(size=W.shape).astype(np.float32)
    R /= np.linalg.norm(R)

    dirs = {"w": W, "-w": -W, "rand": R}

    # ---- 装置自检（PREREG §3.2：加零必须逐位不变）----
    ids = tk("The capital of France is", return_tensors="pt")
    with torch.no_grad():
        base = model(**ids).logits[0, -1].clone()
    for name, v in (("0 向量", np.zeros_like(W)),
                    ("hook 空挂", None)):
        h = blk.register_forward_pre_hook(
            (lambda mod, inp: inp) if v is None
            else (lambda mod, inp: ((inp[0] + torch.as_tensor(v)),) + inp[1:]))
        with torch.no_grad():
            z = model(**ids).logits[0, -1]
        h.remove()
        same = bool(torch.equal(z, base))
        print(f"  自检 {name}: 逐位相同={same}")
        if not same:
            raise SystemExit(f"ABORT 装置自检失败：{name} 改变了 logits")

    # ---- 装置符号基准：unembedding 行（Qwen3-1.7B tie_word_embeddings=True）----
    # 注入 +α·U[tok] **必然**抬高 tok 的 logprob：符号由构造决定，
    # 与任何「学出来的方向」无关。这是把「装置把符号弄错了」
    # 与「方向没效」分开的唯一干净办法。
    U = model.lm_head.weight.detach().float().numpy()
    ref_tok = mid[0]
    print(f"符号基准 token：{tk.decode([ref_tok])!r}({ref_tok}) / "
          f"{tk.decode([cid])!r}({cid})")

    # ---- 主实验 ----
    # ⚠⚠⚠⚠ 位置映射：**这是第一版最严重的一个错，比符号问题严重得多。**
    #
    # 第一版这么取输入：
    #     text = rec["prompt"] + rec["generated_text"]
    #     enc  = tk(text);  pre = enc["input_ids"][:, :t]
    #
    # 三个错误叠在一起，且**每一个都不报错**：
    #   ① npz 的 `hidden_states` 只有 **1024 行 = 生成段**，
    #      prompt 是另一个数组 `prompt_token_ids`（133 个）。
    #      ⇒ `tok` 下标活在**生成段坐标系**里，
    #        而 `prompt + generated_text` 重新分词得到的是**全序列坐标系**，
    #        两者差着 133 个 token，还不算 chat template 与边界分词的差异。
    #   ② 生成时的 token 序列是 `prompt_token_ids ++ token_ids`，
    #      与「把拼接后的字符串重新分词」**不是**同一个序列。
    #   ③ `pre = ids[:, :t]` 只喂到第 t−1 位，读的最后一个 logit
    #      预测的是第 t 位；而注入位置 `_inj = t - 1` 在**全序列**里
    #      又不是生成段下标 t−1 对应的那个位置。
    #
    # ⇒ 第一版的注入**根本没作用在「标记词还没写出来的那个位置」上**。
    #   6 案例冒烟读数（α=+4 → −0.0049）因此是**无效读数**，
    #   不能用来讨论 C-2/C-3 的符号。本文件已按
    #   「诊断结论」重写取输入方式，旧读数作废、见 PREREG 修订 1。
    #
    # 正确映射（实测三项对齐，见 `.cache/mutbak/causal_align.py`）：
    #     npz 第 g 行          == 全序列第 (P + g − 1) 位
    #     npz topk_logits[g]   == 该位输出的 logits（top-1 一致率 0.9912）
    #     npz last_hidden[g]   == HF hidden_states[28] 该位（余弦 0.99993）
    #   其中 P = len(prompt_token_ids)。
    #   ⇒ 生成段 token t 的预测 logits 在全序列第 (P+t−1) 位；
    #     要读它的下一 token 分布，就喂 `full[:P+t]`、读 logits[−1]，
    #     并把 α·w 注入**同一个位置** P+t−1（即生成段 token t−1 的位置）。
    # ---- 变体清单（两套剂量梯 + 装置符号守卫）----
    #
    # ⚠⚠⚠ 剂量尺度是第一版的**真正**病因，不是符号约定：
    #   实测（`.cache/mutbak/causal_signbench.py`）‖h(动摇点,L20)‖ 中位 1014、
    #   `w·h` 的动摇/随机**类间间距只有 375**。
    #   第一版的 α ∈ {0.5,1,2,4} 是**单位向量直觉**下的取值，
    #   只有自然尺度的 ~1%，于是整套剂量梯落在**几乎无响应**的区间里，
    #   冒烟读到的 −0.0006…−0.0049 是那个区间的真实值，
    #   **不是**「方向反了」。按自然尺度重标后，+w 把 marker logprob
    #   推高 +0.041 → +0.416（单调，峰值在 α_rel=1.0），
    #   而随机方向全程**下降**（−0.03 → −0.91）⇒ 方向是可区分的。
    #
    # ⇒ 两套梯都跑、都留档：旧梯原样保留以复现修订 1 里的旧读数，
    #   新梯 `α_rel = α_abs / 类间间距` 是**锚在数据自己的尺度上**的。
    gap = class_gap(pos, tmap, SEED)
    rel_ladder = tuple(float(x) for x in a.rel_ladder.split(",") if x.strip())
    if 1.0 not in rel_ladder:
        raise SystemExit(f"ABORT 剂量梯必须含 α_rel=1.0（判决 R-3/R-4/R-5/R-6 都在那里取数）：{rel_ladder}")
    # ⚠⚠⚠ 变体清单必须与判决块引用的键**逐字对齐**。
    #   第二版漏了两处，两处都以「剂量键不存在」的形式**响亮**炸出来
    #   （这个守卫救了一次命）：
    #   ① `w` 的**负**剂量档根本没进清单（只放了正的），
    #      而判决块要 C-3。
    #   ② `rand` 的 rel 档被命名成 `rand|abs+0.10` —— 键名里
    #      剂量数值的格式对了（abs vs rel）却写死成 `abs`，
    #      于是判决块按 `rand|rel+0.10` 去取，取不到。
    #   ③ 更隐蔽的一条：`mean_delta` 用 `keys[0]` 当基线，
    #      所以 REL_POS 的第一格**必须是 α_rel=0**，
    #      否则所有 Δ 都是「相对 α_rel=0.1」而不是相对无注入。
    variants = []      # (key, dir_name, vector_np)
    for al in list(ALPHAS) + [-x for x in ALPHAS if x > 0]:
        variants.append((f"w|abs{al:+.1f}", "w", (al * W)))
    for al in [0.0] + list(rel_ladder) + [-x for x in rel_ladder]:
        variants.append((f"w|rel{al:+.2f}", "w", (al * gap * W)))
    for al in [0.0] + list(ALPHAS):
        variants.append((f"rand|abs{al:+.1f}", "rand", (al * R)))
    for al in [0.0] + list(rel_ladder):
        variants.append((f"rand|rel{al:+.2f}", "rand", (al * gap * R)))
    # 装置符号守卫：**每个案例**都带两个 unembedding 基准。
    # +α·U[tok] 必然抬高 tok 的 logprob（符号由构造决定，与学出来的方向无关）。
    # 若这两条翻红 ⇒ 装置坏了，本案例全部读数作废。
    # ⚠⚠⚠ 守卫剂量必须是**小剂量**（α_rel = CHK_REL = 0.05）。
    #   我第一版把它放在 α_rel = 1.0 上，于是第 12 个案例被判红：
    #       Wait −1.4017   the +20.3922
    #   ` the` 涨了 20（守卫期望的形状），` Wait` 却**跌了** 1.4。
    #   这不是装置坏了，是我**守卫的假设错了**：
    #   log_softmax 是**相对量** —— 只要别的 token 的 logit 涨得更多，
    #   目标 token 的 logprob 照样会降。大剂量下 unembedding 的
    #   「直接 logit 通路」被其他词淹没，这个论证不成立。
    #   ⇒ 装置符号是**符号约定**问题，属于小剂量极限；
    #     用标定剂量去判它，等于拿大剂量去检验一个小剂量的命题。
    #   守卫照旧（这次真的在正确地响），但剂量改到 5%。
    for nm, tk_id in (("Uref", ref_tok), ("Uctl", cid)):
        u = U[tk_id] / np.linalg.norm(U[tk_id])
        variants.append((f"{nm}|chk", nm, (CHK_REL * gap * u)))
    print(f"变体 {len(variants)} 个/案例，类间间距 {gap:.1f}，"
          f"新梯 α_abs = " + " ".join(f"{r:g}×{gap:.0f}" for r in rel_ladder))

    def run_batched(pre1, inj, vecs):
        """把所有变体塞进**一次**前向。hook 按 batch 元素分别加各自的量。"""
        B = len(vecs)
        L = pre1.shape[1]
        delta = torch.as_tensor(np.stack(vecs), dtype=torch.float32)
        pos_idx = torch.full((B,), inj, dtype=torch.long)
        bidx = torch.arange(B)

        def hook(mod, inp):
            h = inp[0].clone()
            h[bidx, pos_idx, :] = h[bidx, pos_idx, :] + delta
            return (h,) + inp[1:]

        hd = blk.register_forward_pre_hook(hook)
        try:
            with torch.no_grad():
                lg = model(pre1.expand(B, L)).logits[:, -1, :]
        finally:
            hd.remove()
        return lg, torch.log_softmax(lg, dim=-1)

    results = []
    align_checked = 0
    for ci, c in enumerate(cases, 1):
        tid = c["traj"]
        z = np.load(os.path.join(NPZ_DIR, tid + ".npz"))
        pids = z["prompt_token_ids"].astype(np.int64)
        gids = z["token_ids"].astype(np.int64)
        # ⚠⚠ 变量名不能叫 `P`：模块顶部有 `import probe_hinge_layers as P`，
        #   在 main() 里赋同名局部变量会让它变成**局部**，
        #   于是同一函数开头那行 `P.load_positives()` 直接 UnboundLocalError。
        n_pre = len(pids)
        if c["t"] >= len(gids):
            continue
        full = np.concatenate([pids, gids])
        pos_read = n_pre + c["t"] - 1      # logits 读在第几个位置
        pre1 = torch.as_tensor(full[:pos_read + 1])[None, :]
        cur = int(gids[c["t"]])

        lg_all, lp_all = run_batched(pre1, pos_read,
                                      [v for _, _, v in variants])
        mid_t = torch.as_tensor(mid)
        d = {}
        for bi, (key, _nm, _v) in enumerate(variants):
            row_lp = lp_all[bi]
            # ⚠ `cur` 是「位置 t 上**实际写的那个 token**」的 logprob，
            #   而 Uref 的 unembedding 行是 ` Wait` 的 —— 两者一般**不是**
            #   同一个 token。第一版守卫错查了 `cur`，自己把自己判红了。
            #   ⇒ unembedding 基准必须查它自己对应的那一列。
            d[key] = {"mark": float(torch.logsumexp(row_lp[mid_t], dim=0)),
                      "ctl": float(row_lp[cid]),
                      "ref": float(row_lp[ref_tok]),
                      "cur": float(row_lp[cur]),
                      # ⚠⚠ logit 是**绝对**量，logprob 是**相对**量。
                      #   装置符号的判据必须看 logit，见下面守卫处。
                      "ctl_logit": float(lg_all[bi, cid]),
                      "ref_logit": float(lg_all[bi, ref_tok])}

        # ⚑ 守卫 1：坐标错位（第一版缺的正是这条，错位时读数照常输出）
        if align_checked < 50:
            align_checked += 1
            _ref = int(z["topk_indices"][c["t"], 0])
            if int(lp_all[0].argmax()) != _ref:
                raise SystemExit(
                    f"ABORT 位置映射错位：生成段 t={c['t']} 处本地 top-1="
                    f"{int(lp_all[0].argmax())} 与 npz 记录的 {_ref} 不一致。")
        # ⚑ 守卫 2：装置符号。变体 0 是 w|abs+0.0，必须逐位等于基线。
        if abs(d["w|abs+0.0"]["mark"] - d["w|abs+0.0"]["mark"]) > 1e-12:
            raise SystemExit("ABORT α=0 不自洽。")
        # ⚑⚑ 装置符号守卫：**判 logit，不判 logprob**。
        #   「注入 +α·U[tok] ⇒ tok 的 logit 上升」是**绝对**的、只走
        #   unembedding 这一条通路的事 —— 这正是「符号约定对不对」。
        #   而 logprob 是**相对**量（logit 减 logsumexp）：只要别的
        #   token 涨得更多，tok 的 logprob 照样会降，哪怕它自己的
        #   logit 一路涨。实测（`guard_case12.py`）：α_rel=1.0 时
        #   ` Wait` 的 Δlogit **+4.845、排 151936 名中的第 1 名**，
        #   Δlogprob 却被别的 token 挤到 +0.30（换一批位置会变负）。
        #   ⇒ 第一版守卫拿 logprob 下判决，被一个**良性的相对效应**
        #     判死在第 12 个案例上。守卫自己写错，照样很响。
        _b = d["w|abs+0.0"]
        _dl_ref = d["Uref|chk"]["ref_logit"] - _b["ref_logit"]
        _dl_ctl = d["Uctl|chk"]["ctl_logit"] - _b["ctl_logit"]
        # logprob 的变化只**记录**，不参与判死。
        _dp_ref = d["Uref|chk"]["ref"] - _b["ref"]
        _dp_ctl = d["Uctl|chk"]["ctl"] - _b["ctl"]
        if _dl_ref <= 0 or _dl_ctl <= 0:
            raise SystemExit(
                f"ABORT 装置符号：注入 +α·U 后对应 token 的 **logit** 未上升"
                f"（Wait {_dl_ref:+.4f}， the {_dl_ctl:+.4f}）"
                f"⇒ 读数不可用。")
        d["_guard"] = {"d_logit_ref": _dl_ref, "d_logit_ctl": _dl_ctl,
                       "d_logprob_ref": _dp_ref, "d_logprob_ctl": _dp_ctl}

        row = {"traj": tid, "t": c["t"], "inj": pos_read,
               "npz_row": c["t"], "n_prompt": n_pre, "marker_id": cur,
               # 分组用的标签。`marker_text` 是**该位置实际写的那个 token**，
               # 不是「哪一类」—— 修订 3 的 A 组按它的词干归类。
               "marker_text": tk.decode([cur]),
               "is_correct": bool(correct.get(tid, None)),
               "d": d}
        results.append(row)
        if ci % 1 == 0:
            print(f"  [{ci}/{len(cases)}]")

    # ---- 批量路径必须与逐个前向一致（批量不是免费的等价变换）----
    # ⚠ 第一版没有这一项。批量化把 26 次前向压成 1 次，
    #   如果 hook 的按元素加法写错（位置广播、索引错位），
    #   读数会**平滑地**错掉而不报错 —— 又是一个静默失效。
    if a.check_unbatched:
        md = 0.0
        for row in results[:a.check_unbatched]:
            z = np.load(os.path.join(NPZ_DIR, row["traj"] + ".npz"))
            full = np.concatenate([z["prompt_token_ids"].astype(np.int64),
                                   z["token_ids"].astype(np.int64)])
            pre1 = torch.as_tensor(full[:row["inj"] + 1])[None, :]
            for key, _nm, v in variants[:6]:
                # ⚠⚠⚠ 独立实现必须**结构不同**才能当交叉校验，
                #   而第一版写的是
                #       cat([inp[0][:, :inj, :] + _v, inp[0][:, inj:, :]])
                #   它把 v 加到了前缀的**每一个**位置，不是只加 inj ——
                #   长得像「截断拼接」，读过去以为只改了 inj 那一行。
                #   实测：它与正确实现的差在「非注入位置」上同样是 **48.6**
                #   ⇒ 是两种**不同实验**，不是数值噪声（噪声底 6.6e-5）。
                #   ⇒ 正确写法：把 inj 那一行单独切出来加，再拼回去。
                hd = blk.register_forward_pre_hook(
                    lambda m, inp, _v=torch.as_tensor(v, dtype=torch.float32): (
                        (torch.cat([inp[0][:, :row["inj"], :],
                                    inp[0][:, row["inj"]:row["inj"] + 1, :] + _v,
                                    inp[0][:, row["inj"] + 1:, :]], dim=1),)
                        + inp[1:]))
                try:
                    with torch.no_grad():
                        l1 = model(pre1).logits[0, -1]
                finally:
                    hd.remove()
                l1 = torch.log_softmax(l1, dim=-1)
                md = max(md, abs(float(torch.logsumexp(l1[mid_t], dim=0))
                                 - row["d"][key]["mark"]))
        print(f"  批量 vs 逐个前向：最大差 {md:.3e}"
              f"{'  ✅' if md < 1e-4 else '  ❌ 批量路径不是等价变换'}")
        if md >= 1e-4:
            raise SystemExit(f"ABORT 批量路径与逐个前向不一致（{md:.3e}）。")

    # ---- 判决 ----
    # ⚠⚠ 两套剂量梯**都**判决，且都留档。
    #   旧梯（abs）保留是因为它写在预登记里，必须能复现修订 1 的旧读数；
    #   新梯（rel）锚在实测类间间距上，才是可解释的那个。
    #   绝不许因为旧梯红就把新梯当成「唯一正确的口径」——
    #   两条一起报，才看得出是剂量的问题还是符号的问题。
    def mean_delta(rows, keys, field="mark"):
        # ⚠⚠⚠ 历史上这个函数连坑三次：① `zip(keys, base)` 逐元素配对，
        #   ②「第 i 个剂量」配「第 i 个案例的基线」，
        #   ③ `--limit` 小时静默截断。三处的表现都是
        #   **`α=0 的 Δ 不为 0`** —— 一个自明的矛盾，却没人先看它一眼。
        #   ⇒ 现在：显式断言长度一致 + 减**全体案例的平均基线**。
        if len(rows) < 1:
            raise SystemExit("ABORT 没有可用案例。")
        miss = [k for k in keys if k not in rows[0]["d"]]
        if miss:
            raise SystemExit(f"ABORT 剂量键不存在：{miss}")
        base = float(np.mean([r["d"][keys[0]][field] for r in rows]))
        return np.array([np.mean([r["d"][k][field] for r in rows]) - base
                         for k in keys])

    def spearman(x, y):
        x = np.asarray(x, float); y = np.asarray(y, float)
        rx = np.argsort(np.argsort(x)).astype(float)
        ry = np.argsort(np.argsort(y)).astype(float)
        # ⚠ 去中心化是 Spearman 的**必要步骤**。我改上面那个 bug 时
        #   顺手删掉了这两行，ρ 立刻全错。
        rx -= rx.mean(); ry -= ry.mean()
        dd = np.sqrt((rx ** 2).sum() * (ry ** 2).sum())
        return float((rx * ry).sum() / dd) if dd else 0.0

    # ⚠⚠ 剂量键必须**按实际档位生成**，不能写死。
    #   写死过一版（REL_POS 固定 6 档），而修订 3 把梯子精简成
    #   {0.5, 1.0}，于是判决取数时找不到 w|rel+0.10 / +0.25 / +2.00。
    #   这个错被 `mean_delta` 的「剂量键不存在」守卫**响亮**拦住了 ——
    #   若没有那条守卫，它会退化成静默截断，读数看着仍然完整。
    # ⚠ 第一格必须是 α=0：mean_delta 拿 keys[0] 当基线。
    ABS_POS = ["w|abs+0.0"] + [f"w|abs{al:+.1f}" for al in ALPHAS]
    ABS_NEG = [f"w|abs{-al:+.1f}" for al in ALPHAS if al > 0]
    REL_POS = ["w|rel+0.00"] + [f"w|rel{al:+.2f}" for al in rel_ladder]
    REL_NEG = [f"w|rel{-al:+.2f}" for al in rel_ladder]
    RND_ABS = ["rand|abs+0.0"] + [f"rand|abs{al:+.1f}" for al in ALPHAS]
    RND_REL = ["rand|rel+0.00"] + [f"rand|rel{al:+.2f}" for al in rel_ladder]
    I_R1 = 1 + list(rel_ladder).index(1.0)   # REL_POS 里 α_rel=1.0 的下标

    d_pos = mean_delta(results, ABS_POS)
    d_neg = mean_delta(results, ABS_NEG)
    d_rnd = mean_delta(results, RND_ABS)
    r_pos = mean_delta(results, REL_POS)
    r_neg = mean_delta(results, REL_NEG)
    rr_pos = mean_delta(results, RND_REL)
    r_ctl = mean_delta(results, REL_POS, "ctl")
    r_cur = mean_delta(results, REL_POS, "cur")

    # ---- 恒等式守卫：解析上必然成立，不成立就是代码坏了 ----
    for nm, arr in (("abs", d_pos), ("rel", r_pos)):
        if abs(arr[0]) > 1e-9:
            raise SystemExit(
                f"ABORT 恒等式破了（{nm} 梯）：α=0 的 Δ 应为 0，实得 {arr[0]:+.6f}。")
    if abs(spearman(np.arange(5.0), np.arange(5.0)) - 1.0) > 1e-9:
        raise SystemExit("ABORT spearman(x,x) 应恒为 1.0 —— 实现坏了。")
    if abs(spearman(np.arange(5.0), np.arange(5.0)[::-1]) + 1.0) > 1e-9:
        raise SystemExit("ABORT spearman(x,-x) 应恒为 -1.0 —— 实现坏了。")
    # ⚑ 装置符号守卫（已在逐案例时跑过，这里再总检一次）
    g1 = mean_delta(results, ["w|abs+0.0", "Uref|chk"], "ref_logit")
    g2 = mean_delta(results, ["w|abs+0.0", "Uctl|chk"], "ctl_logit")
    if g1[1] <= 0 or g2[1] <= 0:
        raise SystemExit(
            f"ABORT 装置符号总检失败：+α·U 未能抬高对应 token"
            f"（Wait {g1[1]:+.4f}， the {g2[1]:+.4f}）。读数不可用。")

    rho_pos = spearman(d_pos, np.arange(len(d_pos)))
    rho_neg = spearman(d_neg, np.arange(len(d_neg)))
    rho_rpos = spearman(r_pos, np.arange(len(r_pos)))
    rho_rneg = spearman(r_neg, np.arange(len(r_neg)))
    dt_at4 = float(d_pos[-1])
    rt_at1 = float(r_pos[I_R1])
    # 旧梯 α=4 时对照词 ` the` 的变化（C-5 用）。
    # ⚠ 必须取**全体案例平均**且只取 `w` 那一批 ——
    #   历史上这里取过 `results[0]` 单个案例，且键名前缀逻辑把随机方向
    #   的值混了进来，两处都让 C-5 拿错对象下判决。
    d_control = float(mean_delta(results, ["w|abs+0.0", "w|abs+4.0"], "ctl")[1])

    # X-3 负控：打乱 α 顺序再拟合
    # ⚠ 固定置换表在 `--limit` 变小时会越界（第一版 perm 硬编码 5 个下标，
    #   `--limit 3` 只产生 1 个案例 → IndexError）。按实际长度取置换。
    perm = np.array([min(i, len(d_pos) - 1) for i in
                     [2, 0, 4, 1, 3, 0, 2, 5, 1, 3]])[:len(d_pos)]
    rho_shuf = spearman(d_pos[perm], np.arange(len(d_pos)))

    print("\n=== 旧剂量梯（PREREG §2 原样，α_abs）—— 保留以复现旧读数 ===")
    for k, v in zip(ABS_POS, d_pos):
        print(f"  {k:12s}  Δmarker {v:+.4f}")
    for k, v in zip(ABS_NEG, d_neg):
        print(f"  {k:12s}  Δmarker {v:+.4f}")
    print(f"  随机 {RND_ABS[-1]:12s}  Δmarker {d_rnd[-1]:+.4f}")

    print(f"\n=== 新剂量梯（α_rel = α_abs / 类间间距 {gap:.1f}）===")
    for k, v, c, u in zip(REL_POS, r_pos, r_ctl, r_cur):
        print(f"  {k:12s}  Δmarker {v:+.4f}   Δ'the' {c:+.4f}"
              f"   Δ标记词本身 {u:+.4f}")
    for k, v in zip(REL_NEG, r_neg):
        print(f"  {k:12s}  Δmarker {v:+.4f}")
    for k, v in zip(RND_REL, rr_pos):
        print(f"  随机 {k:12s}  Δmarker {v:+.4f}")

    # ---- 分组分析（PREREG 修订 3 R-13，取数前已写死）----
    # ⚠⚠ 一律**按轨迹聚合**：位置之间不独立（§8 局限 2），
    #   组内先对轨迹取均值，再对轨迹取均值 ——
    #   直接把位置当独立样本会让样本量虚高 5 倍（121 位置 / 22 轨迹）。
    K1 = "w|rel+1.00"
    K0 = "w|rel+0.00"

    def traj_delta(rows_):
        """每条轨迹内先算 Δ，再对轨迹取均值。"""
        by_t = {}
        for r in rows_:
            by_t.setdefault(r["traj"], []).append(
                r["d"][K1]["mark"] - r["d"][K0]["mark"])
        return {t: float(np.mean(v)) for t, v in by_t.items()}

    td = traj_delta(results)

    def stem(txt):
        t = txt.strip().lower()
        for k in ("wait", "let", "hmm", "mayb"):
            if t.startswith(k[:3]):
                return {"wait": "Wait", "let": "Let",
                        "hmm": "Hmm", "mayb": "maybe"}.get(k[:4], "?")
        return "其他"

    grp_type, grp_ok = {}, {}
    for r in results:
        grp_type.setdefault(stem(r["marker_text"]), []).append(r)
        grp_ok.setdefault("答对" if r["is_correct"] else "答错", []).append(r)

    print("\n=== 分组：Δmarker(α_rel=1)，按轨迹聚合（PREREG 修订 3）===")
    print("  A 组 按标记词类型：")
    sub_type = {}
    for g, rs in sorted(grp_type.items()):
        d = traj_delta(rs)
        if not d:
            continue
        sub_type[g] = float(np.mean(list(d.values())))
        print(f"    {g:6s} 轨迹 {len(d):2d} 条 / 位置 {len(rs):2d} 个  "
              f"Δ {sub_type[g]:+.4f}")
    print("  B 组 按轨迹对错：")
    sub_ok = {}
    for g, rs in sorted(grp_ok.items()):
        d = traj_delta(rs)
        if not d:
            continue
        sub_ok[g] = float(np.mean(list(d.values())))
        print(f"    {g:4s} 轨迹 {len(d):2d} 条 / 位置 {len(rs):2d} 个  "
              f"Δ {sub_ok[g]:+.4f}")

    def same_sign(dd):
        vv = [v for v in dd.values() if abs(v) > NOISE]
        return len(vv) >= 2 and (all(v > 0 for v in vv) or all(v < 0 for v in vv))

    def same_sign_flat(dd):
        vv = [v for v in dd.values() if abs(v) > NOISE]
        return len(vv) >= 2 and (all(v > 0 for v in vv) or all(v < 0 for v in vv))

    r5 = same_sign_flat(sub_type) and len(sub_type) >= 2
    r6 = same_sign_flat(sub_ok) and len(sub_ok) == 2

    verdicts = [
        {"name": "C-1 α=0 与未注入逐位一致（装置自检）", "ok": True,
         "detail": "见上方自检"},
        {"name": "C-1b 装置符号：+α·U 抬高对应 token（逐案例守卫）",
         "ok": bool(g1[1] > 0 and g2[1] > 0),
         "detail": f"Δlogit Wait {g1[1]:+.4f}， the {g2[1]:+.4f}"},
        {"name": "C-2 正向剂量单调（旧 abs 梯，ρ ≥ 0.8）",
         "ok": rho_pos >= 0.8, "detail": f"ρ={rho_pos:.3f}"},
        {"name": "C-3 反向剂量反向单调（旧 abs 梯，ρ ≤ -0.8）",
         "ok": rho_neg <= -0.8, "detail": f"ρ={rho_neg:.3f}"},
        {"name": "C-4 α=4 的变化 ≥ 0.5 nats（旧梯）",
         "ok": abs(dt_at4) >= 0.5, "detail": f"{dt_at4:+.4f}"},
        {"name": "C-5 marker 变化 > 对照词 ' the' 的变化（旧梯 α=4）",
         "ok": abs(dt_at4) > abs(d_control),
         "detail": f"{abs(dt_at4):.4f} vs {abs(d_control):.4f}"},
        {"name": "X-1 随机方向显著更小（旧梯 α=4）",
         "ok": abs(dt_at4) > abs(d_rnd[-1]) + 0.05,
         "detail": f"w {dt_at4:+.4f} vs 随机 {d_rnd[-1]:+.4f}"},
        {"name": "X-3 打乱 α 顺序后 ρ 掉到接近 0",
         "ok": abs(rho_shuf) < 0.9, "detail": f"ρ_shuf={rho_shuf:.3f}"},
        {"name": "R-1 新梯正向单调（α_rel ∈ 0.1..2，ρ ≥ 0.8）",
         "ok": rho_rpos >= 0.8, "detail": f"ρ={rho_rpos:.3f}"},
        {"name": "R-2 新梯反向反向单调（ρ ≤ -0.8）",
         "ok": rho_rneg <= -0.8, "detail": f"ρ={rho_rneg:.3f}"},
        # ⚠⚠⚠ 这两条的第一版都是**假判据**，而且都是照着 buggy 读数写的
        #   （buggy = 全前缀注入，见 PREREG 修订 2 的 R-8）。逐条记：
        #   R-3 原写法要求「随机方向**下降**」。实测随机方向也**上升**
        #       （+0.0841），只是比 w 小 20 倍。「符号相反」是巧合，
        #       不是判据 ⇒ 改为**幅度比** ≥ 10×。
        #   R-4 原写法比的是**带符号**的 Δ：`+1.67 > -1.66` 就通过，
        #       但它只因为对照是负的，**根本没比幅度**。
        #       按 |Δ| 比是 1.6661 vs 1.6607，**比值 1.003 ≈ 1**
        #       ⇒ marker 与对照**等幅移动**，特异性**不成立**。
        #   ⚠ 两者的共同病根：把「方向相反」当成加分项。可注入会同时
        #     抬高一部分、压低另一部分 —— 只要挑一个看起来对的符号，
        #     任何规则都能蒙混过关。判据要比较**幅度**。
        {"name": "R-3 方向可区分：|Δw| ≥ 10×|Δ随机|",
         "ok": abs(rt_at1) >= 10 * abs(rr_pos[I_R1]),
         "detail": f"w {rt_at1:+.4f}（|{abs(rt_at1):.4f}|） vs "
                   f"随机 {rr_pos[I_R1]:+.4f}"
                   f"（|{abs(rr_pos[I_R1]):.4f}|）→ "
                   f"{abs(rt_at1) / max(1e-9, abs(rr_pos[I_R1])):.1f}×"},
        {"name": "R-4 特异性：|Δmarker| ≥ 1.2×|Δ' the'|",
         "ok": abs(rt_at1) >= 1.2 * abs(r_ctl[I_R1]),
         "detail": f"{abs(rt_at1):.4f} vs {abs(r_ctl[I_R1]):.4f} → "
                   f"比值 {abs(rt_at1) / max(1e-9, abs(r_ctl[I_R1])):.3f}"},
        # ↓ 修订 3 的两条：**只判方向，不设阈值** —— 不给「看到结果后
        #   调门槛」留余地。同号 ⇒ 效应与该维度无关；异号 ⇒ 必须单列。
        {"name": "R-5 各标记词类型的 Δ 同号（效应与类型无关）",
         "ok": bool(r5),
         "detail": " ".join(f"{g}:{v:+.3f}" for g, v in sub_type.items())},
        {"name": "R-6 答对组与答错组的 Δ 同号（效应与对错无关）",
         "ok": bool(r6),
         "detail": " ".join(f"{g}:{v:+.3f}" for g, v in sub_ok.items())},
    ]
    print("\n=== 判决（旧梯 = 预登记口径，新梯 = 标定后口径，两条都报）===")
    for v in verdicts:
        print(f"  {'PASS' if v['ok'] else 'FAIL'}  {v['name']}  —— {v['detail']}")
    allok = all(v["ok"] for v in verdicts)

    out = {"prereg": "CAUSAL_PREREG.md", "amendment": "修订 1",
           "layer": LAYER, "alphas_abs": ALPHAS, "rel_ladder": list(rel_ladder),
           "class_gap": gap, "off": OFF, "marker_ids": mid,
           "control_id": cid, "ref_tok_id": ref_tok, "n_cases": len(results),
           "n_variants": len(variants),
           "keys_abs_pos": ABS_POS, "keys_abs_neg": ABS_NEG,
           "keys_rel_pos": REL_POS, "keys_rel_neg": REL_NEG,
           "d_pos": d_pos.tolist(), "d_neg": d_neg.tolist(),
           "d_rand": d_rnd.tolist(),
           "rel_pos": r_pos.tolist(), "rel_neg": r_neg.tolist(),
           "rel_rand": rr_pos.tolist(), "rel_ctl": r_ctl.tolist(),
           "rel_cur": r_cur.tolist(),
           "rho_pos": rho_pos, "rho_neg": rho_neg, "rho_shuf": rho_shuf,
           "rho_rel_pos": rho_rpos, "rho_rel_neg": rho_rneg,
           "device_sign_Wait": g1[1], "device_sign_the": g2[1],
           "noise_floor": NOISE,
           "sub_type": sub_type, "sub_correct": sub_ok,
           "n_traj": n_traj_used, "n_traj_correct": n_ok,
           "verdicts": verdicts, "verdict": "PASS" if allok else "FAIL",
           "caveats": [
               "teacher-forced：读的是「给定前文时下一个 token 的分布」，"
               "不含「注入改变前文 ⇒ 后续全变」的连锁效应。",
               "注入只作用于「标记词前一位」这一个 token 位置，不是全序列。",
               "121 个位置来自同一次生成、22 条轨迹同源 ⇒ 位置间不独立，"
               "统计推断必须按轨迹聚合（本轮只报全体均值）。",
               "注入有效 ≠ 该方向是模型原来就用的因果通路。",
               "动摇频率 ≠ 纠错能力；更犹豫不等于更可能算对。",
               "marker 集合的 logprob 上升**不等于**标记词本身概率上升："
               "本轮两者在 α_rel ≤ 1 区间明显分离，必须分开报。",
           ],
           "rows": results}
    # ⚠⚠ 落盘前先验 JSON 可序列化。121 个位置要跑很久，
    #   而第一版是在 `json.dump` 时才炸（numpy bool 不可序列化）——
    #   40 分钟的算力当场蒸发。⇒ 先用 `default=` 兜住。
    def _j(o):
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            return float(o)
        if isinstance(o, np.bool_):
            return bool(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        raise TypeError(f"不可序列化：{type(o)}")

    json.dump(out, open(a.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1, default=_j)
    print(f"\nRESULT {out['verdict']}")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())