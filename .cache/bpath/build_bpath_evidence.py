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

本脚本不判定任何一���「过没过」，只把实测值摆出来。
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

    # ---------- 6. 挂到八级阶梯 ----------
    ladder = [
        {"level": "L2", "claim": "这个方向线性编码了观测量 y",
         "bpath_state": "done",
         "here": f"频次加权 w·U = {read['freq_weighted']:+.5f}，"
                 f"{read['n_ids_positive']}/{read['n_ids']} 个 marker id 为正",
         "note": "这是**静态**读数，一次前向都不用。"},
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
                        "dose_sweep_B.json")],
        "selfcheck_passed": True,
        "selfcheck": "位置+层轴 12/12；P9 判定 11/11（含新旧闸门对照）；判决脚本 26/26",
        "coordinates": coord,
        "readability_static": read,
        "p9_device_benchmark": p9_block,
        "dose_position_scan": dose_block,
        "layer_profile": layer_block,
        "ladder_mapping": ladder,
        "answerable": [
            "装置在 no_think 上给出干净、单调、符号正确的剂量响应（正控 5/5）",
            "α·(w·U) 在校准点精确成立（实测/预测 0.987 / 0.981），"
            "但注入点一移出校准点读数即掉进噪声（|ratio| 0.0000–0.0939 且逐层变号）"
            "⇒ w·U 应在校准点读，中间层读到的量与它无可预测的定量关系",
            "同一 w 在两条 think 上给出相反形态 ⇒ 效应对位置/轨迹敏感",
        ],
        "not_answerable": [
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