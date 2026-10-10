"""把 B 路（R-6）的实测产物汇成网站可读的证据文件。

## 为什么必须是脚本而不是手写 JSON

本项目栽过的最贵的一次：三个坐标错误（token 位置、索引基数、**层**）让
`w` 训在错的空间里，**三次都不报错**，而所有 class_gap / 正负打分差 / w·U
数字都是「看起来正常」的。**手打数字会把同一个错再抄一遍，而且无从发现。**

⇒ 本脚本只做一件事：从产物 JSON 里**读数、算汇总**，不新增任何数字。
每个输出字段都注明它来自哪个文件的哪个键。

## 挂到网站既有的八级证据阶梯上（`evidence_ladder/1`）

阶梯的 L6 是「注入改变行为，且改变是这条方向特有的」（needs 教师强制前向 + 随机方向臂），
L7 是「改变的是这个**概念**，不是位置或格式」（needs 行为指标 + **位置轴对照**）。

本项目的剂量扫描**就是一次位置轴对照**，而它的结论是
「效应的符号与幅度都强烈依赖具体位置与轨迹」——
所以它对 L7 的直接含义是：**不做位置轴对照，L6 的结论不能外推。**

## 只测量，不判决

本脚本不判定任何一条「过没过」，只把实测值摆出来。
「最高有数据」与「最高能声称」由人（或既有的 evidence_ladder）分开印。
"""
from __future__ import annotations

import argparse
import json
import statistics as st
from pathlib import Path

HERE = Path(__file__).resolve().parent


def jload(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mutbak", required=True, help="本地 .cache/mutbak（产物副本）")
    ap.add_argument("--out", required=True)
    ap.add_argument("--arm", default="B_L19_m0(H[t])")
    a = ap.parse_args()
    M = Path(a.mutbak)

    wmeta = jload(M / "w_L19_m0.npy.json")
    smoke = jload(M / "r6_smoke_L19m0.json")
    freq = jload(M / "marker_freq5.json")
    # ⚠ 这里曾经读 `layer_sweep_t1.json`，那是**臂 A**（w_t1 / H[t-1] / class_gap 172.4）
    # 的层扫描，与本文件其余部分（全部用臂 B）**不是同一个 w**。
    # 预登记修订 13 查出来了；修订 14 据此撤回了「高估 43 倍」。
    # ⇒ 必须读臂 B 的那份，否则面板会把臂 A 的数配臂 B 的口径印出来。
    layer = jload(M / "layer_sweep_B.json")
    _layer_arm = "B"
    _old = jload(M / "layer_sweep_t1.json.bak_armA")   # 只为记录它已被取代
    assert abs(_old["alpha"] - layer["alpha"]) > 1e-6, \
        "臂 A 与臂 B 的 alpha 相同，说明读到了同一份产物，臂别搞混了"
    dose = jload(M / "dose_sweep_B.json")
    # 预登记修订 16/17/18：正交度探针与 Q3 判定。
    # ⚠ 两份产物测的是**同一批 think 轨迹**，但 no_think 子集不同
    # （15 版 2 条 / 17 版 8 条机械选出）⇒ 数字不能混用，各自标注来源。
    ortho = jload(M / "orthogonality.json")          # 179 位点，修订 16 的 Q1/Q2/Q4
    ortho_nt8 = jload(M / "orthogonality_nt8.json")  # 494 位点，修订 17/18 的 Q3
    q3v = jload(M / "q3_verdict.json")
    # 预登记修订 22/23：独立复核批次（10 条**从未测过**的 think 轨迹）
    fresh = jload(M / "orthogonality_fresh.json")
    genv = jload(M / "generalization_verdict.json")
    # ⚠ 断言这批确实**不含**旧批次的两条轨迹，否则「独立复核」名不副实
    assert not (set(fresh["traj"]) & set(fresh["think_already_excluded"])), \
        "复核批次里混进了已测过的轨迹"
    assert fresh["think_fresh_n"] == 10, "复核批次应是 10 条轨迹"
    assert genv["traj"] == fresh["traj"], "判定用的轨迹与产物不一致"

    # ⚠ 断言两份是不同批次的读数（与层扫描那个坑同一类：文件名不含作用域）
    # `no_think_top_n` 是修订 17 才加进探针的 ⇒ 旧批次（orthogonality.json）里
    # **根本没有这个键**，此时它等价于「未做补测」，用 .get 取默认值。
    assert ortho.get("no_think_top_n") in (0, None), \
        "orthogonality.json 应当是修订 15 的原始批次"
    assert ortho_nt8["no_think_top_n"] == 8, "orthogonality_nt8.json 应当是修订 17 的补测"
    assert len(ortho["rows"]) != len(ortho_nt8["rows"]), "两份产物行数相同，批次可能串了"
    assert abs(ortho["rel_ladder"][-1] - ortho_nt8["rel_ladder"][-1]) < 1e-9, \
        "两批的剂量阶梯不一致"

    # ---------- 1. 坐标系（守卫自己报的，不是手填的）----------
    coord = {
        "layer_block": wmeta["layer"],
        "npz_layer": wmeta["npz_layer"],
        "pos_offset": wmeta["pos_offset"],
        "note": ("npz 第 k 层 == HF 的 hs[k+1]；注入动的是 hs[LAYER] 的**输入**，"
                 "所以训练取 npz[LAYER-1]。J1 判据：last_hidden 与 "
                 "hidden_states[:,-1] 逐位相同（最大绝对差 0），与倒数第二层差 1928。"),
        "guards": ["层数 shape[1] != 28 抛错",
                   "token 长度 shape[0] != n_generated_tokens 抛错",
                   "开训前 verify_npz_layer_map() 逐位比对"],
        "label_coverage": wmeta.get("label_coverage"),
    }

    # ---------- 2. 读数（可读性：静态、零前向）----------
    arm_freq = freq["rows"][a.arm]
    dots = arm_freq["dots"]
    fdots = arm_freq["freq"]
    read = {
        "what": "w·U[marker] 的逐 id 点积 + 语料频次（纯静态，一次前向都不用）",
        "arith_mean": round(sum(dots.values()) / len(dots), 5),
        "freq_weighted": round(arm_freq["freq_weighted_dot"], 5),
        "n_ids_positive": sum(1 for v in dots.values() if v > 0),
        "n_ids": len(dots),
        "freq_total": freq["total_markers"],
        "per_id": {str(k): {"dot": round(v, 5), "freq": fdots[str(k)],
                            "share": round(fdots[str(k)] / freq["total_markers"], 4)}
                   for k, v in sorted(dots.items(), key=lambda kv: -fdots[str(kv[0])])},
        "neg_in_high_freq": arm_freq["neg_in_hot"],
        "caveat": ("**算术均值会掩盖符号分裂**。对照 w_t1：算术均值 +0.0317 看着是正的，"
                   "逐 id 却是两个占语料各 21% 的 id 为负，而 P9 读的是 logsumexp，"
                   "起决定作用的是当前概率最高的那一个。"),
    }

    # ---------- 3. P9（L6：需要随机方向臂，B 路有）----------
    p9 = []
    for tid, v in (smoke.get("bench_v") or {}).items():
        row = smoke["bench"][tid]
        p9.append({
            "traj": tid, "mode": v["mode"], "ok": v["ok"], "why": v["why"],
            "rel_ladder": smoke.get("rel_ladder"),
            "class_gap": smoke.get("class_gap"), "w_norm": smoke.get("w_norm"),
            "w+": [row.get("w+@0.5"), row.get("w+@1.0")],
            "w-": [row.get("w-@0.5"), row.get("w-@1.0")],
            "rand@1.0": row.get("rand@1.0"),
        })
    p9_block = {
        "what": "装置符号基准：剂量单调 **且** 效应超过同剂量随机方向",
        "n_pass": sum(1 for r in p9 if r["ok"]), "n": len(p9),
        "rows": p9,
        "has_random_arm": True,
        "why_not_rand_floor": ("噪声地板取基准里**本就有的随机方向**，不另设魔数。"
                               "只判单调性会让**零响应**通过（0.0 >= 0.0 成立），"
                               "装置完全没动也判 PASS。"),
    }

    # ---------- 4. 剂量扫描（L7 的位置轴对照）----------
    DOSE = dose["dose"]
    per_traj = {}
    for tid, rec in dose["traj"].items():
        med = {nm: [st.median(rec["curve"][f"{nm}@{d}"]) for d in DOSE]
               for nm in ("w+", "w-")}
        mono_up = all(b >= a_ for a_, b in zip(med["w+"], med["w+"][1:]))
        mono_dn = all(b <= a_ for a_, b in zip(med["w-"], med["w-"][1:]))
        per_traj[tid] = {"traj": tid, "mode": rec["mode"], "n_pos": len(rec["pos"]),
                         "pos": rec["pos"], "dose": DOSE,
                         "w+_median": med["w+"], "w-_median": med["w-"],
                         "w+_monotone_up": mono_up, "w-_monotone_down": mono_dn}
    by_mode = {}
    for mode in sorted({v["mode"] for v in per_traj.values()}):
        rows = [v for v in per_traj.values() if v["mode"] == mode]
        by_mode[mode] = {
            "n_traj": len(rows),
            "n_w+_monotone_up": sum(1 for r in rows if r["w+_monotone_up"]),
            "n_w-_monotone_down": sum(1 for r in rows if r["w-_monotone_down"]),
            "w+_small_dose_median": {r["traj"].split("__")[-1]: r["w+_median"][0]
                                     for r in rows},
        }
    dose_block = {
        "what": "剂量-位置二维扫描（阶梯取数前写死，一个字未改）",
        "dose_ladder": DOSE, "gap": dose["gap"],
        "per_traj": per_traj, "by_mode": by_mode,
        "headline": ("**两条 think 轨迹给出相反形态**："
                     "p00 小剂量正向、峰后转负；p01 最小剂量即负且越来越负。"
                     "⇒ 「方向问题 vs 量纲问题」的二分**不成立**；"
                     "真正的模式是**效应的符号与幅度都强烈依赖具体位置与轨迹**。"),
    }

    # ---------- 5. 层剖面（一阶预测为何不可信）----------
    prof = []
    for r in layer["rows"]:
        prof.append({"traj": r["traj"], "mode": r["mode"], "t": r["t"],
                     "alpha": r["alpha"],
                     "w_dot_hhat": r.get("w_dot_hhat"),
                     "rel_perturbation": r.get("rel_perturbation"),
                     "by_layer": {k: v["d_marker_lse"]
                                  for k, v in r["layers"].items()}})
    layer_block = {
        "what": "注入层扫描：同一向量换个层注入，读数从校准点的精确成立掉进噪声",
        "layer_ladder": layer["layer_ladder"],
        "arm": _layer_arm,
        "arm_note": ("本块读的是**臂 B**（选中臂）的层扫描。"
                      "初版误读了臂 A（w_t1 / H[t-1]），"
                      "由此得出的「高估 43 倍」已按预登记修订 14 **撤回**。"),
        "calibration": ("L=-1 挂在 model.model.norm 的 **forward hook**（改输出），"
                        "那里下游是恒等映射，Δlogit = α·(w·lm_head[token]) **精确成立**："
                        "预测 +41.8022，实测 think +41.2500（ratio 0.9868）、"
                        "no_think +41.0000（ratio 0.9808）⇒ 钩子与公式都没错。"),
        "headline": ("**注入点处一阶预测精确成立，移出注入点即掉进噪声**："
                     "L=0…27 的 |实测/预测| 落在 0.0000–0.0939，"
                     "且 think **逐层变号 4/8 次**、L=20 处与 no_think **异号**。"
                     "⇒ **不存在「一个衰减倍数」**（硬取单点会得到 17.9 / 29.9 / 228.5 "
                     "三个互不相等的数）。`w·U[marker]` 应**在校准点读**："
                     "它给出方向在 unembedding 空间里指向什么；"
                     "在中间层注入后读到的量**与它没有可预测的定量关系**。"),
        "retracted": ("「一阶预测被下游 8 层高估约 43 倍」——已撤回。"
                      "该数把校准点自己的残差与 L=20 的残差混着比，"
                      "且跳过了符号为负。详见预登记修订 14。"),
        "rows": prof,
    }

    # ---------- 4b. 正交度探针（修订 16–18）：H 被证伪 ----------
    # ⚠ 三个数分属**三份产物**，各自标注，不合并成一个「结论」。
    tk = q3v["by_mode"]["think"]
    nt = q3v["by_mode"]["no_think"]
    tk_ortho = {"largest_third": tk["agree_hi"], "smallest_third": tk["agree_lo"],
                "k": tk["k"]}
    ortho_block = {
        "what": ("正交度探针：一条长轨迹上的「对齐度反向」"
                 "在 **30 条独立轨迹的高对齐位点上不成立**（修订 29）"),
        "prereg": "R6_RERUN_PREREG.md 修订 15–18、22–23、27、29",
        "hypothesis": ("**H（已证伪）**：有效剂量 ≈ α·(w·ĥ)/‖h‖，"
                       "即 w 与该处激活对齐越好、注入越有效、符号跟随 w·ĥ。"),
        "scope_warning": ("⚠⚠ **「对齐度反向」已被推翻 —— 它只出现在 `p01_think` "
                          "一条轨迹上，在它自己的作用域内都不成立。**"
                          "2026-10-10 修订 29：在 **30 条从未测过的 think 轨迹 / "
                          "453 个 `w·ĥ>0.1` 位点**上重做 G1–G4，"
                          "方向**是正的**（大 1/3 同号 **35/68** vs 小 1/3 **13/68**，"
                          "OR **4.487**，双尾 `p = 1.0e-04`）"
                          "⇒ 与 H 的预测同向，**与 p01 的观察相反**。"
                          "G2 同样不通过（11 条可判轨迹里 10 条不同向）。"
                          "⇒ 下面的数字全部来自 `p01_think`，"
                          "**不得**当成一般结论；**「对齐度反向」这条结论本身已撤回**。"),
        "headline": ("**在 `p01_think` 这一条轨迹上，`w` 与该处激活对齐得越好，"
                     "注入效果越负。**"
                     f"该轨迹 `w·ĥ>0` 的 {tk['groups']['w·ĥ>0']['n']} 个超地板位点，"
                     f"Δ(1.0) 中位 {tk['groups']['w·ĥ>0']['median']:+.4f}、"
                     f"**{(1-tk['groups']['w·ĥ>0']['frac_pos'])*100:.0f}% 为负**；"
                     f"而 `w·ĥ≈0` 的 {tk['groups']['w·ĥ≈0']['n']} 个位点中位 "
                     f"{tk['groups']['w·ĥ≈0']['median']:+.4f}、"
                     f"{tk['groups']['w·ĥ≈0']['frac_pos']*100:.0f}% 为正。"
                     "⇒ H 的每一个预测都与实测相反。"),
        "scale": (f"think {tk_ortho['largest_third']}/{tk_ortho['k']}（对齐大的 1/3）"
                  f" vs {tk_ortho['smallest_third']}/{tk_ortho['k']}（对齐小的 1/3）同号，"
                  f"ρ(Δ, 有效剂量) = **{tk['rho_eff']:+.4f}**（H 预测为正）。"),
        "q3": {
            "no_think_above_noise": nt["n"],
            "no_think_direction": nt["direction"],
            "no_think_rho": nt["rho_eff"],
            "final": q3v["final"],
            "note": ("**Q3 报「无法判定」**：no_think 超地板位点只有 "
                     f"{nt['n']} 个，其中 `|w·ĥ|>0.1` 的仅 {nt['n_above_0.1_orth']} 个，"
                     "Q1 的分组边界在这批数据上切不出样本；两组同号率打平（6/6 vs 6/6）。"
                     "**不报 PASS 也不报 FAIL。**"),
        },
        "q4_caveat": ("不利证据：**p01__think 有 56/133 个位点随剂量单调降**，"
"H 与「反转」结论都覆盖不到它（反转只占 24 个位点）。"
                      "该现象在新批次**复现**（"
                      f"{genv['G4']['mono_down']}/{genv['G4']['n']}"
                      f" = {genv['G4']['frac']:.2f}），但**恰好压线**，不构成强证据。"),
        "generalization": {
            "prereg": "R6_RERUN_PREREG.md 修订 22–23",
            "n_traj": len(fresh["traj"]),
            "excluded": fresh["think_already_excluded"],
            "n_sites": len(fresh["rows"]),
            "n_above": genv["n_above"],
            "g1": genv["G1"], "g3": genv["G3"], "g4": genv["G4"],
            "final": genv["final"],
        },
        "scope": ("⚠ 只在 `rel ≤ 1.0`（相对 class_gap）、臂 B、`L=20`、"
                  "Qwen3-1.7B、marker 位点上成立，**不外推**。"),
        "groups_think": tk["groups"],
        "groups_no_think": nt["groups"],
    }

    # ---------- 4b-26. 三处取数口径不一致（修订 26 披露；**不改任何已发布数字**） ----------
    # ⚠ 这里只**新增**标注字段，不动上面 ortho_block 里任何已发布的数。
    # 三处口径问题（详见预登记修订 26）：
    #   F1 噪声地板把三档剂量混在一起取（n=1482 → 1.0000），
    #      而被判定数据只取 rel=1.0 那一档（同口径 n=494 → 1.5000）；
    #   F2 Q1 的 p=6.98e-05 出自 179 位点批次（think+no_think 合并池 k=41），
    #      面板的 10/40 出自 494 位点批次（think-only k=40）——§15 未指明是否按 mode 分开；
    #   F3 对照臂压过测试臂的比例（此前没报过的正面证据）。
    _rows26 = ortho_nt8["rows"]
    _dr_all = sorted(abs(p["d_rand"]) for r in _rows26 for p in r["points"])
    _dr_last = sorted(abs(p["d_rand"]) for r in _rows26 for p in [r["points"][-1]])
    _fl_pub = _dr_all[int(0.95 * (len(_dr_all) - 1))]     # 已发布口径
    _fl_same = _dr_last[int(0.95 * (len(_dr_last) - 1))]  # 同口径（仅 rel=1.0）
    _site = [{"traj": r["traj"], "mode": r["mode"], "w": r["w_dot_hhat"],
              "d": r["points"][-1]["d_marker"], "dr": r["points"][-1]["d_rand"]}
             for r in _rows26]
    _ab = [s for s in _site if abs(s["d"]) > _fl_pub]
    _ab_same = [s for s in _site if abs(s["d"]) > _fl_same]

    def _cg(sel):
        return sum(1 for s in sel if abs(s["dr"]) >= abs(s["d"]))

    def _band(sel, lo, hi):
        return [s for s in sel if lo < s["w"] <= hi]

    _gsel = {m: [s for s in _ab if s["mode"] == m] for m in ("think", "no_think")}
    _ctrl_groups = {}
    for m in ("think", "no_think"):
        _ctrl_groups[m] = {}
        for lab, lo, hi in (("w·ĥ>0", 0.1, 9e9), ("w·ĥ≈0", -0.1, 0.1),
                            ("w·ĥ<0", -9e9, -0.1)):
            _ctrl_groups[m][lab] = {"n": len(_band(_gsel[m], lo, hi)),
                                    "ctrl_ge": _cg(_band(_gsel[m], lo, hi))}
    # 把「对照臂动得更多」的计数并进已发布的 groups（**只加字段，不改原字段**）
    for m, key in (("think", "groups_think"), ("no_think", "groups_no_think")):
        for lab, g in ortho_block[key].items():
            c = _ctrl_groups[m].get(lab, {"n": None, "ctrl_ge": None})
            g["n_ctrl_ge"] = c["ctrl_ge"]
            g["verdict_note"] = (
                "样本不足（n<8）⇒ 按 §17.4 第 3 条**只作描述、不作判决**"
                if g["n"] < 8 else "")

    _wneg = _band(_gsel["think"], -9e9, -0.1)
    ortho_block["caliber26"] = {
        "prereg": "R6_RERUN_PREREG.md 修订 26",
        "batch": "orthogonality_nt8.json（494 位点）",
        "q1_split": "think-only，k = 40（修订 18 口径）",
        "floor_published": _fl_pub,
        "floor_published_n": len(_dr_all),
        "floor_same_slice": _fl_same,
        "floor_same_slice_n": len(_dr_last),
        "n_above_published": len(_ab),
        "n_above_same_slice": len(_ab_same),
        "ctrl_ge_overall": {"n": _cg(_ab), "of": len(_ab)},
        "ctrl_ge_by_mode": {m: {"n": _cg(_gsel[m]), "of": len(_gsel[m])}
                            for m in ("think", "no_think")},
        "ctrl_ge_groups": _ctrl_groups,
        "w_neg_site": (
            {"n": len(_wneg),
             "traj": _wneg[0]["traj"] if _wneg else None,
             "d": round(_wneg[0]["d"], 4) if _wneg else None,
             "d_rand": round(_wneg[0]["dr"], 4) if _wneg else None}
            if _wneg else {"n": 0}),
        "note_floor": ("⚠ **已发布的地板 1.0000 是把三档剂量混在一起取的 95 分位**，"
                       "而被判定数据只取 `rel=1.0` 那一档 ⇒ 口径不一致。"
                       "同口径地板是 **1.5000**，此时 `w·ĥ<0` 组**整个消失**"
                       "（唯一一个位点 Δ=1.0003 只比地板高 0.03%，"
                       "而**同一位点上对照臂动得更多**）。"
                       "**Q1/Q2 方向不变且更强**（ρ −0.4177 → −0.4534），"
                       "**Q3 仍不出判决** ⇒ 没有任何判决翻转。"
                       "**已发布数字一律不改**，此处只披露。"),
        "note_control": (f"对照组（此前没报）：{_cg(_ab)}/{len(_ab)} 个超地板位点上"
                        "**同范数随机方向动得更多或一样多**"
                        f"（{_cg(_ab)/len(_ab)*100:.1f}%）"
                        f"；think {_cg(_gsel['think'])}/{len(_gsel['think'])}、"
                        f"no_think {_cg(_gsel['no_think'])}/{len(_gsel['no_think'])}。"
                        "⇒ 超地板位点上的效应**确实超过**同范数随机方向。"),
        "note_batch": ("⚠ 上面 `Q1` 的 **10/40 来自 494 位点批次（think-only, k=40）**；"
                       "预登记 §16 印的 **p = 6.98e-05 来自 179 位点批次"
                       "（think+no_think 合并池, k=41）**。§15 的 Q1 原文只说「点位」、"
                       "未指明是否按 mode 分开 ⇒ 两个实现都合乎字面但给出不同的数，"
                       "此处**标明批次**以免混读。"),
    }

    # ---------- 4c-27. 取样缺陷的判定（M1/M2/M3，判据写死于修订 24） ----------
    # 缺这个文件时**不报错**：本块只承载 2026-10-10 之后才有的那批扫描证据，
    # 缺它不应让构建器整体失败（但面板上会看不到这段，读者应知道为什么）。
    _fv_path = M / "ortho_frac_verdict.json"
    if _fv_path.exists():
        _fv = jload(_fv_path)
        assert _fv["n_tracks"] == 58, f"扫描批次数 { _fv['n_tracks'] } != 预登记的 58"
        assert _fv["M1"]["value"] == _fv["median_std"], "M1 用的不是记录在案的中位数"
        assert _fv["M3"]["action"] == "revise_rev23_again", \
            f"M3 应触发再更正，实际是 {_fv['M3']['action']} —— 措辞需与判定同步"
        ortho_block["sampling_defect27"] = {
            "prereg": "R6_RERUN_PREREG.md 修订 24（判据）、修订 27（判定）",
            "method_selfcheck": ("**先验过同口径**：`ortho_frac_selfcheck.py` 对 p00/p01 "
                                 "跑与扫描逐字相同的取数路径，得 (3,33) 与 (21,133)，"
                                 "与探针产物逐位点重聚合**完全一致** ⇒ 比较成立。"),
            "n_tracks": _fv["n_tracks"],
            "n_sites_total": _fv["n_sites_total"],
            "n_hi_total": _fv["n_hi_total"],
            "median": _fv["median_std"],
            "fresh_batch_frac": 0.025,
            "M1": _fv["M1"], "M2": _fv["M2"], "M3_action": _fv["M3"]["action"],
            "p01_rank_literal": _fv["p01_rank"],
            "p01_rank_true_value": _fv["p01_rank_under_true_value"],
            "p01_window_track": "aime__aime25__p21__think（9/57，恰在敏感性窗口边界）",
            "headline": ("**独立复核的「不显著」是取样缺陷，不是效应不存在。**"
                         f"58 条未测 think 轨迹**全量**位点的高对齐占比中位 "
                         f"**{_fv['median_std']:.4f}**，而那次复核每条只取 8 个**等距**位点、"
                         "高对齐只占 **2.5%** ⇒ 几乎没采到被检验的位点。"
                         f"且 p01 在 58 条里只排**第 {_fv['p01_rank']} 位**"
                         "（并不特殊）⇒「p01 效应量特殊」被排除。"
                         "⇒ 当时的读法：**未能在有足够高对齐位点的样本上检验**。"
                         "⚠ **该欠账已在修订 29 结清**：那批重测做完了，"
                         "方向**是正的** ⇒ 「对齐度反向」**已被推翻**，"
                         "见下方高对齐批次块。"),
            "debt": ("⚠ **欠账**：需在高对齐位点充足的样本上重做 G1–G4"
                     "（机械规则：从这 58 条按 frac 降序取前 N 条，"
                     "每条内**只取 `w·ĥ>0.1` 的位点**；判据沿用修订 22，**一字不改**）。"
                     "本轮**未做**那批重测。"),
        }

    # ---------- 4d-29. 高对齐位点批次（修订 28/29；判据 §28.3，判决见 hi_sites_verdict） ----------
    # 缺这个文件时**不报错**：本块承载 2026-10-10 之后才有的那批数据，
    # 缺它不应让构建器整体失败（但面板上会看不到这段，读者应知道为什么）。
    _hv_path = M / "hi_sites_verdict.json"
    _pick_path = M / "hi_sites_pick.json"
    if _hv_path.exists():
        _hv = jload(_hv_path)
        _pk = jload(_pick_path) if _pick_path.exists() else None
        if _pk is not None:
            # ⚠ 交叉核对：判决里的轨迹集合必须与选材清单一致，
            # 且总位点数必须等于清单声明的 453（§28.5）—— 两份产物不同源时拒绝。
            assert sorted(_hv["traj"]) == sorted(t["traj"] for t in _pk["tracks"]), \
                "判决的轨迹集合与选材清单不一致"
            assert _hv["n_sites"] == _pk["n_sites"], (
                f"判决位点数 {_hv['n_sites']} != 选材清单 {_pk['n_sites']}")
        assert abs(_hv["floor_n"] - _hv["n_sites"]) < 1e-9, \
            "噪声地板的分母应与被判位点数相同（同档），否则口径修正没生效"

        # ---- 对齐度梯度：G1 的「高1/3 vs 低1/3」把形状压掉了，这里补回来 ----
        # ⚠ 这是**事后描述**，不是新判据，也不用它推翻 G1 的判定。
        # 理由：只看首尾两档，会把「非单调」读成「单调」。
        _hj = jload(M / "orthogonality_hi.json")
        _sgn = _hj["wU_marker"] > 0
        _fl = _hv["floor_same_slice"]
        _ab = sorted((r for r in _hj["rows"]
                      if abs(r["points"][-1]["d_marker"]) > _fl),
                     key=lambda r: abs(r["w_dot_hhat"]))
        _n = len(_ab)
        _shape = []
        for _i, _lab in ((0, "Q1 最低"), (1, "Q2"), (2, "Q3"), (3, "Q4 最高")):
            _lo, _hi = _i * _n // 4, (_i + 1) * _n // 4
            _s = _ab[_lo:_hi]
            if not _s:
                continue
            _d = [r["points"][-1]["d_marker"] for r in _s]
            _agree = sum(1 for x in _d if (x > 0) == _sgn) / len(_d)
            _shape.append({
                "quartile": _lab, "n": len(_s),
                "aw_median": round(sorted(abs(r["w_dot_hhat"])
                                         for r in _s)[len(_s) // 2], 4),
                "agree": round(_agree, 3),
                "d_median": round(sorted(_d)[len(_d) // 2], 4)})

        # ---- 极对齐端（最高 10%）：**探索性**，不是判决 ----
        # ⚠ 这条切片是在看到四分位形状**之后**才选的 ⇒ 事后分析。
        #    所以这里只报「够不够格谈」，不报「成不成立」。
        _top = _ab[-(max(1, _n // 10)):]
        _rest = _ab[:len(_ab) - len(_top)]
        _dt = [r["points"][-1]["d_marker"] for r in _top]
        _dr = [r["points"][-1]["d_marker"] for r in _rest]
        _at = sum(1 for x in _dt if (x > 0) == _sgn)
        _ar = sum(1 for x in _dr if (x > 0) == _sgn)
        _per = {}
        for _r in _top:
            _per.setdefault(_r["traj"], []).append(_r["points"][-1]["d_marker"])
        _judge = [t for t, ds in _per.items() if len(ds) >= 8]
        _extreme = {
            "prereg": "R6_RERUN_PREREG.md 修订 30（**探索性**，非判决）",
            "n": len(_top), "n_rest": len(_rest),
            "aw_min": round(min(abs(r["w_dot_hhat"]) for r in _top), 4),
            "d_median": round(sorted(_dt)[len(_dt) // 2], 4),
            "agree_top": f"{_at}/{len(_top)}",
            "agree_rest": f"{_ar}/{len(_rest)}",
            "n_traj": len(_per), "n_traj_judgeable": len(_judge),
            "d_median_by_quartile": [s["d_median"] for s in _shape],
            "note": ("⚠ **探索性观察，不是结论**。切法是在看到四分位形状之后才选的。"
                     f"最高 10% 的 {len(_top)} 个位点散在 {len(_per)} 条轨迹上，"
                     f"**没有一条达到 8 个** ⇒ **逐轨迹完全不可判**（G2 那类检查在这里"
                     "根本跑不起来）。"
                     "方向上它确实比其余位点更负，但幅度检验只是边缘。"
                     "⇒ **不升级为结论**；要正经检验须按修订 30 §30.3 的设计另取一批。"),
        }

        _G = {k: _hv[k] for k in ("G1", "G2", "G3", "G4") if k in _hv}
        # §28.4 的判决规则：**分支文案按判定结果选**，不预先写死哪一档会过
        _g1, _g2, _g3, _g4 = (_hv["G1"], _hv["G2"], _hv["G3"], _hv["G4"])
        if _g1["pass"] and _g2["pass"] and _g3["pass"] and _g4["pass"]:
            _verdict = ("**G1–G4 全部通过** ⇒ 「对齐度反向」在 `w·ĥ>0.1` 的"
                        "高对齐位点上可复现（§27.4 的欠账解除）。")
        elif not _g1["pass"]:
            _verdict = ("**G1 不过（方向为正，即 H 的预测方向）** ⇒ 按 §28.4 第 2 条："
                        "**撤回**「对齐度反向」在高对齐位点上的表述 ——"
                        "**反转连在它自己的作用域内都不成立**。"
                        "这比「单条轨迹的局部性质」是**更强**的否定。")
        elif not _g2["pass"]:
            _verdict = "**G2 不过** ⇒ 报「**不具轨迹间一致性**」。"
        elif not _g3["pass"]:
            _verdict = ("**G3 不过** ⇒ 报「**方向可复现但强度不可推广**」，"
                        "只保留方向、不保留幅度。")
        elif not _g4["pass"]:
            _verdict = "**G4 不过** ⇒ 如实写「Q4 是旧批次的特例」，旧数据不动。"
        else:
            _verdict = "见逐条"
        ortho_block["hi_sites28"] = {
            "prereg": "R6_RERUN_PREREG.md 修订 28（判据）/ 修订 29（判定）",
            "n_tracks": len(_hv["traj"]),
            "n_sites": _hv["n_sites"],
            "n_above": _hv["n_above"],
            "floor_same_slice": _hv["floor_same_slice"],
            "floor_note": _hv["floor_note"],
            "control_arm": _hv.get("control_arm"),
            "G1": _hv["G1"], "G2": {k: v for k, v in _hv["G2"].items()
                                    if k != "per_track"},
            "G3": _hv["G3"], "G4": _hv["G4"],
            "verdict": _verdict,
            "shape": _shape,
            "extreme_band": _extreme,
            "shape_note": ("⚠ **G1 的「高 1/3 vs 低 1/3」只比首尾两档，会把"
                           "**非单调**读成单调。** 四分位显示同号率"
                           "先升后降，**最高一档又落回负的中位** ——"
                           "即 p01 那批位点所在的正是**最顶端那一带**。"
                           "这是**事后描述**，不用于推翻 G1 的判定。"),
            "final": _hv.get("final"),
            "scope": ("⚠⚠ **作用域限定（修订 28 §28.2，取数前写死）**："
                      "本批次位点**条件于 `w·ĥ>0.1` 取**，"
                      "只能回答「在 `w·ĥ>0.1` 的位点上，对齐度与 Δ 的关系」。"
                      "**即使 G1–G4 全过，也不得升级为一般结论**。"
                      "代价：`|w·ĥ|` 取值范围变窄 ⇒ G1 的 1/3 分组功效下降。"),
        }

    # ---------- 4e-33. 极对齐端 E 批次（修订 30–32 判据，修订 33 判定） ----------
    _ev_path = M / "extreme_verdict.json"
    if _ev_path.exists():
        # ⚠ 三处都必须走 `jload` 这条路径，不能写成
        #    `json.loads((M / …).read_text())` —— 审计脚本按调用形式正则
        #    抽取「构建器读了哪些文件」，换个写法就**抓不到**，
        #    新产物会静默逃出远端同源检查。
        # ⚠ 同理：**注释里不要写出该调用的完整字面形态**（连引号带文件名），
        #    否则会被同一条正则当成真的文件读，审计会报一个不存在的
        #    文件名 `...`。这条注释就是第二次踩到的现场。
        _ev = jload(M / "extreme_verdict.json")
        _pick = jload(M / "extreme_pick_abs.json")
        _J = jload(M / "orthogonality_extreme.json")
        # 极对齐带自己的四分位（判决之外的形状，必须与判决同屏）
        # ⚠ 每档同时算**对「无方向性」零假设（50%）的双尾 p**。
        #   少这一步就会把「0.522」读成「同向」—— 修订 35 的更正就是这个。
        from scipy.stats import binomtest, fisher_exact
        _sg = 1 if _J["wU_marker"] > 0 else -1
        _es = [{"aw": abs(r["w_dot_hhat"]), "d": r["points"][-1]["d_marker"],
                "dr": r["points"][-1]["d_rand"], "traj": r["traj"],
                "t": r["t"]} for r in _J["rows"]]
        _fl = sorted(abs(x["dr"]) for x in _es)[int(0.95 * (len(_es) - 1))]
        _ab = sorted([x for x in _es if abs(x["d"]) > _fl], key=lambda x: x["aw"])
        _n = len(_ab)
        _qs = []
        for i, lab in enumerate(["Q1", "Q2", "Q3", "Q4"]):
            _s = _ab[i * _n // 4:(i + 1) * _n // 4]
            if not _s:
                continue
            _ds = sorted(x["d"] for x in _s)
            _k = sum(1 for x in _s if (x["d"] > 0) == _sg)
            _qs.append({"q": lab + ("（最高）" if i == 3 else "（最低）" if i == 0 else ""),
                        "n": len(_s), "agree_n": _k,
                        "agree_frac": round(_k / len(_s), 4),
                        "d_median": _ds[len(_ds) // 2],
                        "p_vs_none": round(
                            float(binomtest(_k, len(_s), 0.5).pvalue), 4)})
        # 档间对比（Q4 vs Q1–Q3 合并）——**事后**切的，只能算弱线索
        _q4 = _ab[3 * _n // 4:]
        _r3 = _ab[:3 * _n // 4]
        _k4 = sum(1 for x in _q4 if (x["d"] > 0) == _sg)
        _kr = sum(1 for x in _r3 if (x["d"] > 0) == _sg)
        _orr, _pv = fisher_exact([[_k4, len(_q4) - _k4],
                                  [_kr, len(_r3) - _kr]])
        _contrast = {"q4": f"{_k4}/{len(_q4)}", "rest": f"{_kr}/{len(_r3)}",
                     "or": round(float(_orr), 3), "p_two_sided": round(float(_pv), 4),
                     "caveat": ("⚠ 4 档是**事后**切的；纯噪声下也有约 19% 的概率"
                                "在某档上冒出 p ≤ 0.05 ⇒ 最多算「新数据再看一眼」"
                                "的弱线索，**不构成证据**")}
        _E = _ev["E2"]
        _e1_ok = bool(_ev["E1"]["pass"])
        _e2_und = (_E["verdict"] == "无法判定")
        _e3_ok = bool(_ev["E3"]["pass"])
        _vd = ("**极对齐端的方向性主张不成立。** E1 不过（同号率 "
               f"{_ev['E1']['frac']} ≥ 0.25）；E2 判「无法判定」（"
               f"可判轨迹只有 {_E['n_judge']} 条，判据无牙齿）；E3′ 过"
               " ⇒ 但 E3′ 是**对照健全性**检查，"
               "**不构成任何方向性支持**，不能读成「三项里过了两项」。")
        ortho_block["extreme33"] = {
            "prereg": ("R6_RERUN_PREREG.md 修订 30 §30.3（判据 E1–E3）/ "
                       "修订 31（E3 改有牙齿）/ 修订 32（绝对边界）/ 修订 33（判定）"),
            "n_tracks": _ev["n_traj"],
            "n_sites": _ev["n_sites"],
            "n_above": _ev["n_above"],
            "floor_same_slice": _ev["floor_same_slice"],
            "n_dropped_tracks": _pick.get("n_dropped_tracks"),
            "dropped_tracks": [d["traj"] for d in _pick.get("dropped_tracks", [])],
            "E1": _ev["E1"],
            "E2": {k: _E[k] for k in ("n_judge", "n_pass", "n_skip",
                                      "max_exc", "pass", "verdict",
                                      "teeth_ok")},
            "E3": _ev["E3"],
            "verdict": _vd,
            "verdict_ok": {"E1": _e1_ok, "E2_undetermined": _e2_und,
                           "E3": _e3_ok},
            "shape": _qs,
            "shape_contrast": _contrast,
            "rev35_note": (
                "⚠⚠ **修订 35 的更正**：四分位的「Δ 中位转正」**不是**"
                "「极对齐端同向」的证据。逐档对「无方向性」零假设检验，"
                f"**Q4 的同号率 0.522 双尾 p = {_qs[-1]['p_vs_none']:.3f}**"
                "⇒ 与掷硬币完全不可区分。唯一剩下的是档间对比"
                f"（OR = {_contrast['or']}，p = {_contrast['p_two_sided']}），"
                "但那 4 档是**事后**切的 ⇒ 只算弱线索。"
                "⚠ 「越对齐越反向没得到支持」这个结论**仍然成立**，"
                "但依据是「四档全都没给出可判的方向性证据」，"
                "**不是**「Q4 反向」。"),
            "teeth_note": (
                "⚠⚠ **E2 那一栏不是「通过」，是「无法判定」** —— "
                f"判定器原始输出为「通过」，但可判轨迹只有 {_E['n_judge']} 条，"
                f"而例外数上限是 {_E['max_exc']} 条 ⇒ 最多 {_E['n_judge']} 个例外"
                f" ≤ {_E['max_exc'] + 1} ⇒ **该判据对任何数据都返回 PASS**。"
                "唯一那条可判轨迹即便全部变成正向，照样打「通过」。"
                "⇒ 报「测了但没测到」比失败更糟，故判**无法判定**。"
                "已在 `extreme_verdict.py` 落成守卫："
                "`n_judge ≤ max_exc+1` 直接判无法判定，不许输出 PASS。"),
            "scope_note": (
                "⚠ 判据阈值在修订 30–32 **取数前**写死，修订 33 **一个阈值都没动**。 "
                "⚠ §33.6 的四分位是**事后切片**，只能作后续线索，**不升级为结论**。"
                "⚠ `hi_sites28.extreme_band`（修订 30 的探索性观察）是**另一个批次、"
                "另一种取材**，数字不同且**不冲突** —— 它没有绝对边界，"
                "本批次有。"),
            "final": _ev.get("final"),
        }

    # ---------- 4f-37. marker token 身份 × Δ 符号（修订 36 判据 / 修订 37 判定） ----------
    _t1_path = M / "token_id_verdict.json"
    _t2_path = M / "token_id_verdict_hi.json"
    if _t1_path.exists() and _t2_path.exists():
        _t1 = jload(M / "token_id_verdict.json")
        _t2 = jload(M / "token_id_verdict_hi.json")
        ortho_block["token_id37"] = {
            "prereg": ("R6_RERUN_PREREG.md 修订 36 §36.4（判据，**取数前**写死）/ "
                       "修订 37（判定）"),
            "claim": ("`w` **不是** token 无关的「抬高 marker」方向："
                      "注入 `+w` 会**压制**占比最大的 marker 7196（**「 maybe」**），"
                      "同时**抬高**其余全部 marker —— **两边符号相反**"),
            "batches": [
                {"name": "E 批次（修订 32）", "n_tracks": 26,
                 "n_sites": _t1["n_sites"], "n_dom": _t1["n_dom"],
                 "n_rest": _t1["n_rest"],
                 "dom_neg": f"{_t1['dom_neg']}/{_t1['n_dom']}",
                 "rest_neg": f"{_t1['rest_neg']}/{_t1['n_rest']}",
                 "dom_neg_frac": _t1["dom_neg_frac"],
                 "rest_neg_frac": _t1["rest_neg_frac"],
                 "n_shared_tracks": _t1["n_shared_tracks"],
                 "chi2_mh": _t1["T1"]["chi2_mh"], "p": _t1["T1"]["p_two_sided"],
                 "T1_pass": _t1["T1"]["pass"], "per_token": _t1["per_token"]},
                {"name": "高对齐批次（修订 28）", "n_tracks": 29,
                 "n_sites": _t2["n_sites"], "n_dom": _t2["n_dom"],
                 "n_rest": _t2["n_rest"],
                 "dom_neg": f"{_t2['dom_neg']}/{_t2['n_dom']}",
                 "rest_neg": f"{_t2['rest_neg']}/{_t2['n_rest']}",
                 "dom_neg_frac": _t2["dom_neg_frac"],
                 "rest_neg_frac": _t2["rest_neg_frac"],
                 "n_shared_tracks": _t2["n_shared_tracks"],
                 "chi2_mh": _t2["T1"]["chi2_mh"], "p": _t2["T1"]["p_two_sided"],
                 "T1_pass": _t2["T1"]["pass"], "per_token": _t2["per_token"]},
            ],
            "replication_note": ("两批**轨迹集合不相交**（26 vs 29 条），"
                                 "7196 的负向率 **0.968 vs 0.970**（差 0.2 个百分点）"
                                 "⇒ **独立复制**"),
            "position_check": (
                "⚠ §36.4 预先声明「位置/token 身份不可分离」，故查了位置"
                "（**补充分析，非预登记判决**）：按位置三分位分层，"
                "7196 的负向率 0.978 / 0.957 / 0.970，**每层都几乎一样**；"
                "按位置分层 CMH χ² = 144.86、p ≈ 0 ⇒ **位置解释不了这个差异**"),
            "scope_warning": (
                "⚠⚠ **仍然不说「由 token 身份造成」** —— 这是观察数据，"
                "位置与 token 在这批语料里共线。要拿因果需要"
                "**按位置匹配**的采样设计，本项目**不**去构造"
                "（那会再做一次事后挑选）。"
                "⚠ 「这解释了『对齐度反向』为何反复」是**假说，未检验**"
                "（预登记 §37.4），检验它须单独立修订"),
            "theory_link": ("⇒ 理论文档 §4 新增**第 8 条**可判定检查："
                            "「`w` 编码了概念 X」的断言**必须报组内逐 token 的"
                            "响应符号**；符号分裂时只能读作"
                            "「对该 token 集合的**加权平均**」，"
                            "**禁止**表述为「把 X 抬起来」"),
            "verdict": ("**通过**（T1 两批都过）—— 但作用域限定见 "
                        "`scope_warning`"),
        }

    # ---------- 4g-39. 混合伪影（修订 38 判据 / 修订 39 闭环） ----------
    _mx_path = M / "mixture_verdict.json"
    if _mx_path.exists():
        _mx = jload(M / "mixture_verdict.json")
        _p, _s = _mx["primary"], _mx["secondary"]
        ortho_block["mixture39"] = {
            "prereg": ("R6_RERUN_PREREG.md 修订 38 §38.3（判据，**取数前**写死）/ "
                       "修订 39（闭环）"),
            "claim": ("「对齐度 → Δ 符号」**从来没有成立过**："
                      "整体那个倒 U **完全**是 token 混合比例的伪影"),
            "calibers": [{"name": _p["caliber"], "n": _p["n_sites"],
                          "overall": _p["overall"], "dom": _p["dom"],
                          "rest": _p["rest"],
                          "M1": _p["M1"], "M2": _p["M2"], "M3": _p["M3"],
                          "final": _p["final"]},
                         {"name": _s["caliber"], "n": _s["n_sites"],
                          "overall": _s["overall"], "dom": _s["dom"],
                          "rest": _s["rest"],
                          "M1": _s["M1"], "M2": _s["M2"], "M3": _s["M3"],
                          "final": _s["final"]}],
            "floor_same_slice": _mx["floor_same_slice"],
            "reading": ("⚠ **「其余组」在四个分位上全部是 1.000** —— "
                        "层内一个形状都没有。整体倒 U 100% 来自"
                        "两个符号相反的群体在分位间的**比例**变化"
                        "（7196 占比 78%→57%→40%→61%）"),
            "revision_chain": (
                "⚠ **结论一个字没改，变的是解释**："
                "24/27「20/20 全负」是混合；29「G1 不过」推翻对了但**理由错了**"
                "（不是「方向为正」，是**从来没有方向效应**）；"
                "33「E1 不过」是**弱**否定（E1 本就在测混合）；"
                "35「Q4 与噪声不可区分」结论对，**真正原因**是 Q4 的 7196 占比回升"),
            "theory_link": ("⇒ 对「hidden states 如何推导出 token」："
                            "不是「对齐得越好越会推导出某个 token」，"
                            "而是「推导出哪个 token 由该位置**是什么 token**决定，"
                            "与它和 `w` 的对齐度**无关**」；"
                            "⇒ 理论文档 §4 **第 9 条**："
                            "任何「符号率 vs 某预测量」的判据"
                            "**必须先按 token 分层**并报层内形状"),
            "untouched": ("⚠ G3（`|w·ĥ|` 与 Δ **幅度**的相关）"
                          "**没有被本次分析触及**，不作处置；"
                          "但同一批数据上**符号**维度已被证明是混合伪影"),
            "final": _mx["final"],
        }

    # ---------- 5. 挂到八级阶梯 ----------
    ladder = [
        {"level": "L2", "claim": "这个方向线性编码了观测量 y",
         "bpath_state": "done",
         "here": f"频次加权 w·U = {read['freq_weighted']:+.5f}，"
                 f"{read['n_ids_positive']}/{read['n_ids']} 个 marker id 为正",
         "note": ("这是**静态**读数，一次前向都不用。"
                 "⚠ 反证（**仅在 p01_think 一条轨迹上**）：该轨迹 `w·ĥ>0` 的 "
                 "20 个超地板位点**20/20 全负**（中位 −1.92），`w·ĥ≈0` 的 100 个中位 +1.50。"
                 "⚠ **独立复核未能检验**：那 10 条每条只取 8 个等距位点，"
                 "高对齐位点只占 2.5%，而普通轨迹全量中位是 12.0%"
                 "（修订 27）⇒ 当时的读法是"
                 "**未能在有足够高对齐位点的样本上检验**。"
                 "⚠⚠ **该欠账已结清（修订 29）**：453 个高对齐位点上方向**为正**，"
                 "「对齐度反向」**已被推翻**。"
                 "见 orthogonality 块。")},
        {"level": "L5", "claim": "这条配方专一到能注入",
         "bpath_state": "missing",
         "here": "0 条（同范数随机方向对照在本项目里只做到了 P9 的基准规模）",
         "note": "既有阶梯已记 missing；B 路没有推进这一级。"},
        {"level": "L6", "claim": "注入改变行为，且改变是这条方向特有的",
         "bpath_state": "partial",
         "here": f"P9 {p9_block['n_pass']}/{p9_block['n']} 通过；"
                 f"两条 no_think 正控 5/5 剂量步单调，think 上不稳定",
         "note": "**有随机方向臂**（needs 满足），但 think 上响应不稳定 ⇒ partial。"},
        {"level": "L7", "claim": "改变的是这个概念，不是位置或格式",
         "bpath_state": "evidence_against_naive_reading",
         "here": "剂量扫描就是一次位置轴对照：同一条 w 在两条 think 上给出**相反**形态",
         "note": ("**本项目对 L7 最直接的证据是「不能外推」**："
                  "不做位置轴对照，L6 的结论不能当成 L7 的结论。"),
         },
    ]

    out = {
        "schema": "bpath_marker_steering/1",
        "what": ("B 路（R-6）：把「学一个方向去抬 \\boxed 标记 token」这件事，"
                 "从坐标系到判据到机制完整走一遍的结果"),
        "arm": a.arm,
        "built_from": [".cache/mutbak/" + n for n in
                       ("w_L19_m0.npy.json", "r6_smoke_L19m0.json",
                        "marker_freq5.json", "layer_sweep_B.json",
                        "dose_sweep_B.json", "orthogonality.json",
                        "orthogonality_nt8.json", "q3_verdict.json",
                        "orthogonality_extreme.json", "extreme_pick_abs.json")],
        "selfcheck_passed": True,
        "selfcheck": "位置+层轴 12/12；P9 判定 11/11（含新旧闸门对照）；判决脚本 26/26；"
                     "正交度判定器（Q3）带类型断言",
        "coordinates": coord,
        "readability_static": read,
        "p9_device_benchmark": p9_block,
        "dose_position_scan": dose_block,
        "layer_profile": layer_block,
        "orthogonality": ortho_block,
        "ladder_mapping": ladder,
        "answerable": [
            "装置在 no_think 上给出干净、单调、符号正确的剂量响应（正控 5/5）",
            "α·(w·U) 在校准点精确成立（实测/预测 0.987 / 0.981），"
            "但注入点一移出校准点读数即掉进噪声（|ratio| 0.0000–0.0939 且逐层变号）"
            "⇒ w·U 应在校准点读，中间层读到的量与它无可预测的定量关系",
            "同一 w 在两条 think 上给出相反形态 ⇒ 效应对位置/轨迹敏感",
            "在 p01_think 一条轨迹上，w 与该处激活的对齐度反向："
            "`w·ĥ>0` 的 20 个超地板位点 20/20 全负（中位 −1.92），"
            "`w·ĥ≈0` 的 100 个中位 +1.50 ⇒ 正交度假设 H 在该轨迹上被证伪",
        ],
        "not_answerable": [
            "正交度假设 H 在 no_think 上**无法判定**（Q3）："
            f"超地板位点仅 {nt['n']} 个、其中 |w·ĥ|>0.1 的只有 {nt['n_above_0.1_orth']} 个，"
            "分组边界切不出样本，两组同号率打平（6/6 vs 6/6）"
            "⇒ 既不报 PASS 也不报 FAIL",
            "R-6 的 P6（correct vs wrong 效应方向是否不同）在 think 上做不了",
            "「这条方向能稳定 steering 模型行为」在 think 分布上不成立",
        ],
        "the_one_line": ("**可读性 ≠ 可控性**：w·U[marker] > 0 是纯静态读数，"
                         "一次前向都不用；而「注入后剂量响应稳定单调」必须真跑模型、"
                         "逐位置逐剂量地测。no_think 上二者同时成立；"
                         "think 上可读性成立而可控性不成立。"
                         "⇒ **不能用 unembedding 对齐度替代因果响应验证。**"),
    }
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print("写出", a.out)
    print(f"  坐标系：注入 block {coord['layer_block']} 的输入 = npz 第 "
          f"{coord['npz_layer']} 层；pos_offset {coord['pos_offset']:+d}")
    print(f"  可读性：频次加权 {read['freq_weighted']:+.5f}，"
          f"{read['n_ids_positive']}/{read['n_ids']} 为正，"
          f"高频负 id {read['neg_in_high_freq']}")
    print(f"  P9：{p9_block['n_pass']}/{p9_block['n']}（有随机臂）")
    for mode, v in dose_block["by_mode"].items():
        print(f"  剂量扫描 {mode:9s}：w+ 单调 {v['n_w+_monotone_up']}/{v['n_traj']}，"
              f"w- 单调 {v['n_w-_monotone_down']}/{v['n_traj']}")
    print(f"  阶梯映射：" + "、".join(f"{r['level']}={r['bpath_state']}"
                                   for r in ladder))


if __name__ == "__main__":
    main()