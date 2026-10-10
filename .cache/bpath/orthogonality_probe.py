"""正交度测量：检验「有效剂量 = α·(w·ĥ)/‖h‖」这个假设（预登记修订 15 §15.1）。

## 为什么测这个

修订 14 确立了「注入点处精确成立，移出注入点即掉进噪声」，
但没解释**为什么**。层扫描打印了一个诊断量 `w·ĥ`，
两条轨迹恰好是「|w·ĥ| 大的那条剂量单调、小的那条不单调」——
⚠ 两条样本是巧合的可能性远大于机制，所以它只是**待检验假设**。

## 假设 H（预登记 §15.1，取数前写死）

真正进入「方向改变」的那部分正比于 `w·ĥ`，与 `‖h‖` 无关：

    有效剂量 ≈ α · (w·ĥ) / ‖h‖      （而不是 α）

## 本脚本测什么

对每条轨迹的**每一个 marker 位置**（不抽样，全量）：
1. 静态读 `w·ĥ`、`‖h‖`、`α·(w·ĥ)/‖h‖`（numpy，不跑模型）
2. 真跑模型读 `Δmarker`（注入在 block 20 的**输入** = `hs[20]` = npz 第 19 层）
3. 同时跑一个**同范数随机方向**作对照（修订 8 起 P9 就在用这个噪声地板）

## 取数前写死的设置（§15.3 第 4 条：跑之前不许改）

- 轨迹：think `aime__aime25__p00`、`p01__think` + no_think 同两条
  ⇒ **四条全测**，think/no_think 各两条，避免「恰好那条单调」
- 位置：每条轨迹的**全部 marker 位置**，不抽样、不挑
- 剂量：`REL = [0.1, 0.3, 1.0]`（三个点，取数前定死）
- 注入：`layer=20`，`rel` 相对 class_gap，`w` 取臂 B
- 随机方向：**每个 (轨迹, 位置, 剂量) 配一个**，同范数、由该轨迹的 seed 决定

⚠⚠ 坐标系（踩过三次，别再改）：
- `npz[k] == HF 的 hs[k+1]`（采集端 `for li in range(1, len(hs))` 丢了 embedding 那层）
- 注入挂在 `layers[LAYER]` 的 **forward pre**-hook，动的是 block LAYER 的**输入**
  = `hs[LAYER]` = **npz 第 `LAYER-1` 层** ⇒ 读 `NPZ_LAYER`，不是 `LAYER`
- 数组是 `(T, L, D)`，下标是 `[t-1, NPZ_LAYER, :]`，**不是** `[NPZ_LAYER][t-1]`
- `ids[:P+t]` 的最后一位 = 生成段内 `t-1`（npz 只含生成段）
- `npz` 最后一层已过最终 RMSNorm（HF `all_hidden_states` 末项就是 norm 之后的值）

## 判据（§15.2，取数前写死；本脚本只**测**，判定在 verdict 里）

- Q1 `|w·ĥ|` 最大 1/3 位点 vs 最小 1/3 位点，「Δmarker 与 w·U 同号」的比例
  Fisher 精确检验 `p < 0.01`
- Q2 `Δmarker` 与 `α·(w·ĥ)/‖h‖` 的秩相关 vs 与 `α` 的秩相关，后者必须显著更低
- Q3 `no_think` 上 Q1/Q2 同样成立（否则是与 mode 混淆，不受理 H）
- Q4 `p01__think` 的反例必须一并报告（§15.1 已指出的不利证据）
"""
from __future__ import annotations

import argparse
import json
import os
import statistics as st
import zlib
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
import r6_rerun as R6  # noqa: E402

MARKER_IDS = R6.MARKER_IDS          # 从被测模块 import，**不复制**
CONTROL_ID = R6.CONTROL_ID
MODEL = "/home/zhourui/.cache/huggingface/models/Qwen--Qwen3-1.7B/snapshots/master"

# ⚠ 取数前定死（§15.3 第 4 条）
REL = [0.1, 0.3, 1.0]
TRAJ = [
    "aime__aime25__p00__think",
    "aime__aime25__p01__think",
    "aime__aime25__p00__no_think",
    "aime__aime25__p01__no_think",
]
# ⚠⚠ 修订 17：Q3 补测用的 no_think 子集。
# **由机械规则选出，不许人工挑选**（§17.2）：按 marker 位点数降序取前 N。
# 第 15 版把 no_think 写死成 2 条，导致 Q3 只有 3 个超地板位点 ——
# 那是**样本选择**造成的缺陷，不是数据缺陷（该批实际有 59 条 / 652 个位点）。
NO_THINK_TOP_N = int(os.environ.get("ORTHO_NO_THINK_TOP_N", "0") or 0)
# ⚠⚠ 修订 22：think 侧的**独立轨迹复核**。
# 排除已测过的 p00/p01，按 **trajectory_id 字典序**取前 N 条
# —— 字典序是**无信息**规则，不可能挑到对结论有利的轨迹
# （若改成「位点最多的 N 条」，就会偏向长轨迹，等于把 p01 的效应再放大一遍）。
# 位点用**等距分位**取 8 个，不抽样到「看起来好」的位置。
THINK_FRESH_N = int(os.environ.get("ORTHO_THINK_FRESH_N", "0") or 0)
THINK_FRESH_SITES = int(os.environ.get("ORTHO_THINK_FRESH_SITES", "8") or 8)
THINK_ALREADY = {"aime__aime25__p00__think", "aime__aime25__p01__think"}
# ⚠ 冒烟开关（§15.3 第 4 条：正式跑不许用）
SMOKE = int(os.environ.get("ORTHO_SMOKE_SITES", "0")) or None


def pick_think_fresh(sidecar_dir, n, n_sites):
    """按字典序取前 n 条**未测过**的 think 轨迹（修订 22 §22.1）。

    ⚠ 三条规则都是取数前写死的，这里由代码保证：
      1. 排除 `THINK_ALREADY`（已测过的 p00/p01）；
      2. 按 `trajectory_id` **字典序**排序（无信息规则）；
      3. 位点按**等距分位**取 `n_sites` 个（`floor(i*(k-1)/(n_sites-1))`）。
    打印完整候选表与排序结果，便于事后核对「确实没挑」。
    """
    import glob
    cands = []
    for f in sorted(glob.glob(str(Path(sidecar_dir) / "*.json"))):
        try:
            j = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if (j.get("config") or {}).get("mode") != "think":
            continue
        tid = j["trajectory_id"]
        if tid in THINK_ALREADY:
            continue
        k = sum(1 for t in (j.get("tokens") or [])
                if t.get("token_id") in MARKER_IDS)
        if k:
            # ⚠⚠ 必须把该轨迹自己的 tokens 一起带上。
            # 第一版只存了 (tid, k, n_tok)，循环里再用**残留的上一条 `j`**
            # 去数 marker 位点 ⇒ 断言 `k == len(ts)` 拿两条不同轨迹的数在比，
            # 第一条就崩。**断言本身是对的，错的是它比的对象。**
            cands.append((tid, k, j.get("n_generated_tokens"),
                          [i for i, t in enumerate(j.get("tokens") or [])
                           if t.get("token_id") in MARKER_IDS]))
    cands.sort(key=lambda r: r[0])                # ← 字典序（只按 tid）
    print(f"\n[修订 22] 未测过的 think 轨迹共 {len(cands)} 条，"
          f"按字典序取前 {n} 条：")
    chosen = []
    for tid, k, nt, ts in cands[:n]:
        assert k == len(ts), f"{tid} 的 marker 位点数在两次读之间变了"
        # 等距分位（去重后按实有数）
        idx = sorted({int(i * (k - 1) / max(1, n_sites - 1)) for i in range(n_sites)})
        sites = [ts[i] for i in idx]
        print(f"   {tid:<32} marker位点={k:<4} n_tok={nt:<6} 取 {len(sites)} 个：{sites}")
        chosen.append((tid, sites))
    print(f"（已排除：{sorted(THINK_ALREADY)}）")
    return chosen


def pick_no_think_top(sidecar_dir, n):
    """按 marker 位点数降序取前 n 条 no_think 轨迹（§17.2 的机械规则）。

    ⚠ **不允许人工挑**：只按位点数排序，排序键与阈值都在判据里写死。
    打印完整排序表，便于事后核对「确实没挑」。
    """
    import glob
    rows = []
    for f in sorted(glob.glob(str(Path(sidecar_dir) / "*.json"))):
        try:
            j = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        mode = (j.get("config") or {}).get("mode")
        if mode != "no_think":
            continue
        k = sum(1 for t in (j.get("tokens") or [])
                if t.get("token_id") in MARKER_IDS)
        if k:
            rows.append((k, j["trajectory_id"], j.get("n_generated_tokens")))
    rows.sort(key=lambda r: (-r[0], r[1]))       # 位点降序，同数按 id 升序（确定性）
    print(f"\n[修订 17] no_think 按 marker 位点数降序，前 {n} 条：")
    for k, tid, nt in rows[:n]:
        print(f"   位点={k:<4} n_tok={nt:<6} {tid}")
    print(f"（该 mode 共有 {len(rows)} 条带 marker 的轨迹，"
          f"合计 {sum(r[0] for r in rows)} 个位点）")
    return [r[1] for r in rows[:n]]
SEED = 42


def lse(v):
    v = np.asarray(v, dtype=np.float64)
    m = float(v.max())
    return m + float(np.log(np.exp(v - m).sum()))


def spearman(xs, ys):
    """秩相关。样本量小时用它而不是 Pearson：判定关心的是**排序**。"""
    def rank(a):
        order = sorted(range(len(a)), key=lambda i: a[i])
        r = [0.0] * len(a)
        for pos, i in enumerate(order):
            r[i] = float(pos + 1)
        return r
    rx, ry = rank(xs), rank(ys)
    mx, my = st.mean(rx), st.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return (num / den) if den > 1e-12 else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--npz-dir", required=True)
    ap.add_argument("--sidecar-dir", required=True)
    ap.add_argument("--w", required=True)
    ap.add_argument("--w-meta", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--gpu-uuid", default=None)
    # 修订 28：高对齐位点批次。选材由 `pick_hi_sites.py` 预先算好，
    # 探针**只按那份清单跑**，不在这里重新挑（挑的地方必须唯一、可单测）。
    ap.add_argument("--pick", default=None,
                    help="hi_sites_pick.json：{tracks:[{traj,n_hi,...}]}")
    ap.add_argument("--orth-threshold", type=float, default=0.1,
                    help="--pick 模式下只跑 w·ĥ 大于这个值的位点")
    a = ap.parse_args()

    if a.gpu_uuid:
        os.environ["CUDA_VISIBLE_DEVICES"] = f"GPU-{a.gpu_uuid}"
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL, dtype=torch.bfloat16).to("cuda:0").eval()
    torch.set_grad_enabled(False)

    W = np.load(a.w).astype(np.float32)
    W = W / (float(np.linalg.norm(W)) + 1e-12)
    wmeta = json.load(open(a.w_meta, encoding="utf-8"))
    gap = float(wmeta["class_gap"])
    print(f"臂 {a.w_meta}  class_gap {gap:.3f}  "
          f"pos_offset {wmeta['pos_offset']}  npz_layer {wmeta['npz_layer']}")
    assert wmeta["npz_layer"] == R6.NPZ_LAYER, \
        f"w 的 npz_layer({wmeta['npz_layer']}) 与 R6.NPZ_LAYER({R6.NPZ_LAYER}) 不一致"

    U = model.lm_head.weight.detach().float().cpu().numpy().astype(np.float64)
    tied = bool(torch.equal(model.lm_head.weight,
                            model.get_input_embeddings().weight))
    print(f"lm_head 与 embed_tokens 逐位相同 = {tied}")
    wU_marker = float(W @ U[MARKER_IDS].mean(axis=0))
    print(f"w·U[marker均值] = {wU_marker:+.6f}")
    assert wU_marker > 0, \
        "w 对 marker 的对齐为负，Q1 的「同号」判据无意义，先查 w"

    mk = torch.tensor(MARKER_IDS, device="cuda:0")

    def fwd(ids, vec, alpha_, seed):
        inj = ids.shape[0] - 1

        def add(h):
            v = torch.as_tensor(vec, dtype=h.dtype, device=h.device)
            h = h.clone()
            h[:, inj, :] = h[:, inj, :] + alpha_ * v
            return h

        def pre_hook(mod, inp):
            return (add(inp[0]),) + tuple(inp[1:])
        hd = model.model.layers[R6.LAYER].register_forward_pre_hook(pre_hook)
        try:
            o = model(input_ids=ids.view(1, -1), use_cache=False, return_dict=True)
        finally:
            hd.remove()
        return o.logits[0, -1].float()

    rows = []
    # 修订 17：用机械规则（位点数降序前 N）挑 no_think 补测子集
    traj_list = list(TRAJ)
    site_override = None                    # {traj: [位点]}，修订 22 用
    pick_nhi = None                         # {traj: n_hi}，修订 28 用
    if a.pick:
        _pk = json.load(open(a.pick, encoding="utf-8"))
        pick_nhi = {t["traj"]: int(t["n_hi"]) for t in _pk["tracks"]}
        traj_list = sorted(pick_nhi)        # 字典序，与选材器一致
        print(f"\n修订 28 选材：{len(traj_list)} 条轨迹，"
              f"声明位点合计 {sum(pick_nhi.values())}，"
              f"正交边界 w·ĥ > {a.orth_threshold}")
    if THINK_FRESH_N:
        fresh = pick_think_fresh(a.sidecar_dir, THINK_FRESH_N,
                                 THINK_FRESH_SITES)
        traj_list = [tid for tid, _ in fresh]
        site_override = {tid: sites for tid, sites in fresh}
    if NO_THINK_TOP_N:
        extra = pick_no_think_top(a.sidecar_dir, NO_THINK_TOP_N)
        traj_list = traj_list + extra      # ⚠ 不覆盖 think 侧（修订 22 与 17 互斥使用）
    print(f"\n本轮轨迹 {len(traj_list)} 条：{traj_list}")

    for tid in traj_list:
        cti = json.load(
            open(Path(a.sidecar_dir) / f"{tid}.json", encoding="utf-8"))
        sites = [i for i, tk in enumerate(cti.get("tokens") or [])
                 if tk["token_id"] in MARKER_IDS]
        # 修订 22：若该轨迹有**指定位点**（等距分位选的），用它而不是全量
        if site_override and tid in site_override:
            want = site_override[tid]
            assert set(want) <= set(sites), \
                f"{tid} 的指定位点不在 marker 位点集里"
            sites = want
        mode = cti["config"]["mode"]
        print(f"\n=== {tid} mode={mode} n_gen={cti['n_generated_tokens']} "
              f"marker 位点 {len(sites)} 个：{sites[:12]}")
        assert sites, "这条轨迹没有 marker 位点，H 测不了"
        # ⚠ pick 模式下**先筛后截断**：SMOKE 若在筛选前截断，条数守卫
        # 会拿「截断后的数」去比选材清单，冒烟测试永远过不了。
        if SMOKE and pick_nhi is None:
            sites = sites[:SMOKE]
        # ⚠⚠ 取 hidden_states 的正确姿势，踩了两次才对：
        #
        # v1（循环里逐点 `z["hidden_states"][t-1, ...]`）：
        #    第 2 次访问就 AttributeError —— NpzFile 的惰性解压句柄是一次性的。
        # v2（循环前逐点取、立刻 close）：不崩了，但**慢到不可用** ——
        #    NpzFile.__getitem__ 每次都把**整个数组重新解压一遍**，
        #    33 个位点 = 33 × 4.7 GB 的解压量，跑十几分钟一个位点都没打印。
        # v3（本次）：**只取一次** `zs["hidden_states"]` 拿整个数组，
        #    然后在 numpy 侧切片。
        #
        # ⚠ 「大数组不许整块读」是**本机**的约束（`/tmp` 不可写、本机内存紧），
        # **远端有 503 GB / 135 GB 可用** ⇒ 在远端整块读是对的。
        # 规矩要跟着环境走，不是无条件的。
        zs = np.load(Path(a.npz_dir) / f"{tid}.npz")
        gen = zs["token_ids"].tolist()
        hs_all = zs["hidden_states"]              # 只解压这一次
        hs_all = np.asarray(hs_all)              # 独立数组，后续切片不再碰 zip
        zs.close()
        print(f"    hidden_states shape={hs_all.shape} "
              f"({hs_all.nbytes/2**30:.2f} GiB)")
        # 坐标系（踩过三次）：读 npz 第 NPZ_LAYER 层，不是 LAYER
        h_at = {t: hs_all[t - 1, R6.NPZ_LAYER, :].astype(np.float64)
                for t in sites}

        # ---- 修订 28：按 w·ĥ 阈值筛位点（选材的第二段，纯 numpy，不前向）----
        # ⚠ 筛选**只用到 w·ĥ**（预测量），不看任何 Δ ⇒ 不可能偏向结果。
        if pick_nhi is not None:
            w_at = {t: float(W @ (h_at[t] / np.linalg.norm(h_at[t])))
                    for t in sites}
            keep = [t for t in sites if w_at[t] > a.orth_threshold]
            want = pick_nhi.get(tid)
            # ⚠ 与静态扫描逐条对齐：选材清单说这条有 n_hi 个高对齐位点，
            # 探针按同一阈值数出来必须**完全一样**。不一样 ⇒ 两套口径分家了，
            # 此时继续跑就是拿一个说不清的样本去判 G1–G4 ⇒ 拒跑。
            if want is None:
                raise SystemExit(f"{tid} 不在选材清单里，拒绝跑")
            if len(keep) != want and not SMOKE:
                raise SystemExit(
                    f"{tid}：选材清单说 {want} 个 w·ĥ>{a.orth_threshold} 的位点，"
                    f"探针按同一阈值数出 {len(keep)} 个 ⇒ 口径不一致，拒绝跑")
            print(f"    修订28 筛选：{len(sites)} 个 marker 位点 → "
                  f"{len(keep)} 个高对齐位点"
                  f"{'（清单一致）' if len(keep) == want else '（SMOKE 模式，跳过条数比对）'}")
            sites = keep
            if SMOKE:
                sites = sites[:SMOKE]
            del w_at
            h_at = {t: h_at[t] for t in sites}
        del hs_all

        pid = tok(cti["chat_template_input"], return_tensors="pt",
                  add_special_tokens=False).input_ids[0].tolist()
        P = (cti.get("extra") or {}).get("prompt_tokens")

        for t in sites:
            ids = torch.tensor(pid + gen, dtype=torch.long, device="cuda:0")
            up = ids[: P + t]
            h = h_at[t]
            hn = float(np.linalg.norm(h))
            w_dot_hhat = float(W @ (h / hn))

            rec = {
                "traj": tid, "mode": mode, "t": t, "n_tok": cti["n_generated_tokens"],
                "npz_layer_read": R6.NPZ_LAYER, "inject_hs_index": R6.LAYER,
                "h_norm": round(hn, 3),
                "w_dot_hhat": round(w_dot_hhat, 6),
                "w_dot_h": round(float(W @ h), 3),
                "points": [],
            }
            base = fwd(up, W, 0.0, 0)
            b_lse = lse(base[mk].cpu().numpy())
            # 同范数随机方向：每个点一个，由 seed 决定（可复算）
            # ⚠ 种子必须**把轨迹也编进去**：第一版用 `SEED*1000003 + t`，
            # 于是不同轨迹的同 `t` 拿到**同一个随机方向** ——
            # 对照臂与轨迹绑定，就分不清「效应来自 w」还是「来自这条轨迹」。
            # 且**不能用内置 `hash()`**：它对 str 受 PYTHONHASHSEED 影响，
            # 换个进程种子就换一个方向 ⇒ 产物不可复算。用 zlib.crc32（确定性）。
            h_seed = zlib.crc32(f"{tid}|{t}".encode("utf-8")) % (2 ** 31)
            rnd = np.random.RandomState(h_seed).randn(W.shape[0]).astype(np.float32)
            rnd = rnd / (float(np.linalg.norm(rnd)) + 1e-12)

            for rel in REL:
                alpha = rel * gap
                d = fwd(up, W, alpha, 0)
                dr = fwd(up, rnd, alpha, 0)
                eff = alpha * w_dot_hhat / hn          # H 预测的有效剂量
                rec["points"].append({
                    "rel": rel, "alpha": round(alpha, 4),
                    "d_marker": round(lse(d[mk].cpu().numpy()) - b_lse, 4),
                    "d_rand": round(lse(dr[mk].cpu().numpy()) - b_lse, 4),
                    "effective_dose": round(eff, 4),
                })
            rows.append(rec)
            ps = "  ".join(f"{p['rel']}:{p['d_marker']:+.3f}" for p in rec["points"])
            print(f"  t={t:<5} w·ĥ={w_dot_hhat:+.5f}  ||h||={hn:7.1f}  Δmarker {ps}")

    out = {
        "schema": "orthogonality_probe/1",
        "prereg": "R6_RERUN_PREREG.md 修订 15",
        "arm": wmeta.get("pos_offset"),
        "w_meta": {k: wmeta.get(k) for k in
                   ("class_gap", "pos_offset", "npz_layer", "sign_gap")},
        "rel_ladder": REL,
        "traj": traj_list,
        "no_think_top_n": NO_THINK_TOP_N,
        "think_fresh_n": THINK_FRESH_N,
        "think_fresh_sites": THINK_FRESH_SITES,
        "think_already_excluded": sorted(THINK_ALREADY),
        "seed": SEED,
        "rand_seed_rule": "zlib.crc32(f'{traj}|{t}') —— 确定性，不受 PYTHONHASHSEED 影响",
        "wU_marker": round(wU_marker, 6),
        "npz_layer_read": R6.NPZ_LAYER,
        "inject_hs_index": R6.LAYER,
        "rows": rows,
    }
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1),
                            encoding="utf-8")
    print(f"\n写出 {a.out}（{len(rows)} 个位点 × {len(REL)} 个剂量）")


if __name__ == "__main__":
    main()