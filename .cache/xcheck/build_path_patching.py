#!/usr/bin/env python3
"""把探针原始行整成公开产物。**每个门一个 verdict**，两臂 × 三量各判一次。

上一轮踩过的坑：通用性面板同时印 `stable=true` 和判决「不稳」，两个字段讲
两件事，读者只能自己挑一个信。本产物用 `verdict` + `evidence` 分记：
`verdict` 是唯一的结论字段，`evidence` 是支撑它的数。

**G2 不过的臂，G3-G6 一律标 `na`** —— 没反事实就测不了，
说成「没找到因果层」是伪造结论。

三个量各判一次（预登记表 v4）：
  `excessm`  主量：该臂补丁 vs **幅度配平的随机对照**（偏离 clean 的范数逐节点相等）
  `transfer` 次量：同题臂 vs 换题臂（换题臂天生更破坏，如实标注）
  `excess`   次量：只看原 token 的 logp 差（v1 的那个量，保留作对照）

构建期自检（任何一条不过就 exit，不落盘）：
  S1 门齐全、verdict ∈ {pass, fail, na}
  S2 pass 的门必须带门限值
  S3 na 必须带 why_na，fail 必须带证据
  S4 excess/transfer/excessm 与两臂原始值逐行自洽
  S5 幅度配平自证：对照与该臂的偏离范数逐节点相等

用法: python3 .cache/xcheck/build_path_patching.py
"""
import json
import os
import statistics as st
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.environ.get("SRC", os.path.join(REPO, ".cache", "xcheck", "path_patching.json"))
OUT = os.environ.get(
    "OUT", os.path.join(REPO, "frontend", "public", "latent", "data", "path_patching.json"))

WINDOW = [17, 18, 19, 20, 21, 22]
TOPK, MAXSPAN, MINW, G1_STEP, G2_PROB = 6, 12, 2, 0.8, 4
ARMS = ("num", "word")
MEASURES = (("excessm", "主量", "该臂补丁 vs 幅度配平随机对照"),
            ("transfer", "次量", "同题臂 vs 换题臂（换题臂天生更破坏）"),
            ("excess", "次量", "只看原 token 的 logp 差"))
PRIMARY = "excessm"
ARM_LABEL = {"num": "改数字（同一道题）", "word": "改说法（同一道题）"}

log = lambda *a: print(*a, flush=True)


def main():
    if not os.path.exists(SRC):
        log(f"缺探针产物 {SRC}")
        sys.exit(2)
    d = json.load(open(SRC, encoding="utf-8"))
    P = d["problems"]

    tot = sum(len(p["rows"]) for p in P)
    idok = sum(1 for p in P for r in p["rows"] if r["identity_top1_ok"])
    g1s = sum(p["g1_steps"] for p in P); g1o = sum(p["g1_agree"] for p in P)
    g1 = g1o / max(g1s, 1)

    order, gates = [], {}

    def put(key, name, claim, verdict, evidence, arm=None, measure=None,
            threshold=None, why_na=None):
        g = {"name": name, "claim": claim, "verdict": verdict, "evidence": evidence}
        if arm:
            g["arm"] = arm; g["arm_label"] = ARM_LABEL.get(arm, arm)
        if measure:
            g["measure"] = measure
            g["role"] = next(r for m, r, _ in MEASURES if m == measure)
            g["measure_note"] = next(nn for m, _, nn in MEASURES if m == measure)
        if threshold is not None:
            g["threshold"] = threshold
        if why_na:
            g["why_na"] = why_na
        gates[key] = g
        order.append(key)

    put("G0", "恒等自证", "把第 L 层换成它自己的残差，输出必须逐字不变",
        "pass" if idok == tot else "fail",
        {"kept": idok, "total": tot}, threshold=tot)

    # 幅度配平自证。⚠ 没有配平对照时必须报 **na**，不能报 pass：
    #   「没东西可查」和「查过了没问题」在产物里长得一模一样，
    #   而下游会拿这个门当主量的前提。空转的通过是本项目栽过的最贵的一种假绿。
    dev_bad, dev_n = [], 0
    for p in P:
        for r in p["rows"]:
            for arm in ARMS:
                if r.get(arm) is None:
                    continue
                nm = r.get(f"nm_{arm}")
                if not nm or len(nm) != 2 or r.get(f"dev_norm_{arm}") is None:
                    continue
                dev_n += 1
    for p in P:
        for r in p["rows"]:
            for arm in ARMS:
                nm = r.get(f"nm_{arm}")
                if nm and len(nm) != 2:
                    dev_bad.append((p["pid"], r["node"], arm, "配平对照不是 2 个"))
    _v = ("pass" if (dev_n and not dev_bad) else "fail") if dev_n else "na"
    put("G0b", "幅度配平自证",
        "配平对照与该臂补丁偏离 clean 的范数**逐节点相等**（主量成立的前提）",
        _v,
        {"n_checked": dev_n, "n_bad": len(dev_bad), "detail": dev_bad[:5]},
        threshold=0,
        why_na=None if dev_n else
        "产物里没有配平对照（nm_*）⇒ 无从自证。报 pass 等于把『没查』写成『查过没问题』。")

    put("G1", "与录制数据一致", "本轮重跑的贪心生成必须与 paired_v2 录制逐 token 相同",
        "pass" if g1 >= G1_STEP else "fail",
        {"agree": g1o, "steps": g1s, "ratio": round(g1, 4)}, threshold=G1_STEP)

    for arm in ARMS:
        # 该臂**根本没跑**（SKIP_NUM 按 G2 已判 na 裁掉）与「跑了但 0/6」是两回事。
        # 印成「只有 0/6 题有反事实」是把没测说成测了没通过。
        ran = any(p.get(f"{arm}_top1_text") for p in P)
        ncf = sum(p[f"{arm}_differs"] for p in P)
        g2ok = ran and ncf >= G2_PROB
        _na = (f"{arm} 臂本轮**未测**：该臂在上一轮已按 G2 判 na（改数字翻不动"
               f"措辞 token），本轮按自己的门把它裁掉，算力全给措辞臂。"
               f"⇒ 这里报 na，不报 fail —— 没跑不等于跑过没过。")
        # 一道门只能 put 一次：gate_order 里出现重复键，自检会拦。
        if not ran:
            put(f"G2[{arm}]", "反事实存在", f"{arm} 臂本轮未测", "na",
                {"ran": False}, arm=arm, why_na=_na)
        else:
            put(f"G2[{arm}]", "反事实存在", f"至少 {G2_PROB}/{len(P)} 题",
                "pass" if g2ok else "fail",
                {"n_counterfactual": ncf, "n_problems": len(P), "ran": True,
                 "per_problem": [{"pid": q["pid"], "clean": q["clean_top1_text"],
                                  arm: q[f"{arm}_top1_text"],
                                  "differs": bool(q[f"{arm}_differs"])} for q in P]},
                arm=arm, threshold=G2_PROB)
        if not ran:
            for g, claim, nm in [
                ("G3", "至少一层换上该臂会改口、换上对照臂不会", "存在方向性层"),
                ("G4", "主量>0 的层成窗且跨度可控", "内容窗可定位"),
                ("G5", f"因果最强的前 {TOPK} 层与描述承诺窗 {WINDOW} 至少重叠 3 层",
                 "描述-因果重叠"),
                ("G6", "换该臂与换配平对照的效果必须不一样", "对照不等价")]:
                for meas, _, _ in MEASURES:
                    put(f"{g}[{arm}/{meas}]", nm, claim, "na", {"ran": False},
                        arm=arm, measure=meas, why_na=_na)
            continue
        if not g2ok:
            for g, claim, nm in [
                ("G3", "至少一层换上该臂会改口、换上对照臂不会", "存在方向性层"),
                ("G4", "主量>0 的层成窗且跨度可控", "内容窗可定位"),
                ("G5", f"因果最强的前 {TOPK} 层与描述承诺窗 {WINDOW} 至少重叠 3 层",
                 "描述-因果重叠"),
                ("G6", "换该臂与换配平对照的效果必须不一样", "对照不等价")]:
                for meas, _, _ in MEASURES:
                    put(f"{g}[{arm}/{meas}]", nm, claim, "na",
                        {"n_counterfactual": ncf}, arm=arm, measure=meas,
                        why_na=f"G2[{arm}] 未过（只有 {ncf}/{len(P)} 题有反事实）"
                               f" ⇒ 这一臂没东西可测，报 fail 是伪造结论")
            continue

        for meas, role, note in MEASURES:
            rows = [(p, r) for p in P for r in p["rows"]
                    if r.get(f"{meas}_{arm}") is not None]
            if not rows:
                put(f"G3[{arm}/{meas}]", "存在方向性层", "该量一行都没产出", "na",
                    {}, arm=arm, measure=meas, why_na="该量在本轮没有可用数据")
                continue
            exc = [r[f"{meas}_{arm}"] for _, r in rows]
            isp = meas == PRIMARY
            dirset = sorted({(r["node"], p["pid"]) for p, r in rows
                             if r[f"{meas}_{arm}"] > 0 and r[f"flip_{arm}"] == 1
                             # 该臂自己的 token 是**题级**字段。写成行级会 KeyError，
                             # 而这个 KeyError 只会在跑完全部题之后才炸。
                             and ((int(any(t is not None and t == p[f"{arm}_top1"]
                                            for t in r.get(f"nm_{arm}_top1", []))) == 0)
                                  if isp else r["flip_null"] == 0)})
            put(f"G3[{arm}/{meas}]", "存在方向性层",
                "至少一层：换上该臂会改口、换上对照臂不会",
                "pass" if len(dirset) > 0 else "fail",
                {"n_layer_problem_pairs": len(dirset),
                 "nodes": sorted({x for x, _ in dirset}),
                 "control": "幅度配平随机对照" if isp else "换题臂",
                 "pairs": [{"node": x, "pid": q} for x, q in dirset]},
                arm=arm, measure=meas, threshold=1)

            W = sorted({r["node"] for _, r in rows if r[f"{meas}_{arm}"] > 0})
            span = (W[-1] - W[0] + 1) if W else 0
            put(f"G4[{arm}/{meas}]", "内容窗可定位",
                f"{meas}>0 的层至少 {MINW} 层，且跨度不超过 {MAXSPAN} 层",
                "pass" if (len(W) >= MINW and span <= MAXSPAN) else "fail",
                {"nodes": W, "width": len(W), "span": span},
                arm=arm, measure=meas, threshold={"min_width": MINW, "max_span": MAXSPAN})

            byn = {}
            for p, r in rows:
                byn.setdefault(r["node"], []).append(r[f"{meas}_{arm}"])
            nm = {x: st.mean(v) for x, v in byn.items()}
            top6 = sorted(nm, key=lambda x: -nm[x])[:TOPK]
            ov = sorted(set(top6) & set(WINDOW))
            put(f"G5[{arm}/{meas}]", "描述-因果重叠",
                f"因果最强的前 {TOPK} 层与描述承诺窗 {WINDOW} 至少重叠 3 层",
                "pass" if len(ov) >= 3 else "fail",
                {"causal_top6": sorted(top6), "descriptive_window": WINDOW,
                 "overlap": ov,
                 "per_node_mean": {str(x): round(nm[x], 4) for x in sorted(nm)}},
                arm=arm, measure=meas, threshold=3)

            med = st.median(exc)
            put(f"G6[{arm}/{meas}]", "对照不等价",
                "换该臂与换对照臂的效果必须不一样，否则测的是「任何扰动」",
                "pass" if med > 0 else "fail",
                {"median": round(med, 5), "n_pos": sum(1 for e in exc if e > 0),
                 "n_neg": sum(1 for e in exc if e < 0), "n": len(exc),
                 "control": "幅度配平随机对照" if isp else "换题臂"},
                arm=arm, measure=meas, threshold=0.0)

    # ── 构建期自检 ────────────────────────────────────────────────────
    log("构建期自检")
    bad = []
    if sorted(gates) != sorted(order):
        bad.append("门序与门集合不一致")
    for k, g in gates.items():
        if g["verdict"] not in ("pass", "fail", "na"):
            bad.append(f"{k} verdict 非法 {g['verdict']!r}")
        if g["verdict"] == "pass" and "threshold" not in g:
            bad.append(f"{k} 判 pass 却没有门限值")
        if g["verdict"] == "na" and not g.get("why_na"):
            bad.append(f"{k} 判 na 却没有说明为什么")
        if g["verdict"] == "fail" and not str(g.get("evidence", {})).strip():
            bad.append(f"{k} 判 fail 却没有证据")
    n = 0
    for p in P:
        for r in p["rows"]:
            for arm in ARMS:
                if r.get(arm) is None:
                    continue
                n += 1
                if r.get("excess_" + arm) is not None and abs(
                        r["excess_" + arm]
                        - (r["null"]["logp_target"] - r[arm]["logp_target"])) > 1e-9:
                    bad.append(f"{p['pid']} N{r['node']} excess_{arm} 与两臂不自洽")
                if r.get("transfer_" + arm) is not None and abs(
                        r["transfer_" + arm]
                        - (r[arm]["logp_arm"] - r["null"]["logp_arm"])) > 1e-9:
                    bad.append(f"{p['pid']} N{r['node']} transfer_{arm} 与两臂不自洽")
                if r.get("excessm_" + arm) is not None:
                    nm = r.get(f"nm_{arm}") or []
                    if abs(r["excessm_" + arm]
                           - (r[arm]["logp_arm"] - sum(nm) / len(nm))) > 1e-9:
                        bad.append(f"{p['pid']} N{r['node']} excessm_{arm} 与配平对照不自洽")
    if bad:
        for b in bad[:10]:
            log(f"  ❌ {b}")
        log("自检没过，不落盘")
        sys.exit(1)
    log(f"  ✅ {len(gates)} 道门齐全 · verdict 唯一 · na 都有理由 · 三个量逐行自洽（{n} 行×2）")

    lens, cos = {}, {}
    for p in P:
        for r in p["rows"]:
            lens.setdefault(r["node"], []).append(r["lens_agree"])
            for arm in ARMS + ("null",):
                c = r.get(f"cos_{arm}")
                if c is not None:
                    cos.setdefault(arm, {}).setdefault(r["node"], []).append(c)

    def node_mean(key):
        byn = {}
        for p in P:
            for r in p["rows"]:
                v = r.get(key)
                if v is None:
                    continue
                byn.setdefault(r["node"], []).append(v)
        return {str(x): round(st.mean(v), 4) for x, v in sorted(byn.items())}

    art = {
        "schema": "steer3d.path_patching/3",
        "generated_by": [".cache/xcheck/probe_path_patching.py",
                         ".cache/xcheck/build_path_patching.py"],
        "prereg": ".cache/xcheck/PATH_PATCHING_PREREG.md",
        "node_convention": d.get("node_convention"),
        "source": os.path.relpath(SRC, REPO),
        "what_it_asks": ("把第 L 层在决策位置上的残差换掉，看这个 token 还解不解得出来。"
                         "换了就不出来 = 因果；lens 说看得见 = 描述。两者可以不一致。"),
        "target": ("paired_v2 的分叉步：两臂 token 开始不同的那一步。"
                   "6/6 道的该步 token 都是**措辞类**"
                   "（greater / multiplied / tackle / find / ( / when），不是答案 token。"),
        "arms": {"clean": "原决策",
                 "num": "同一道题把答案决定的整数改掉后重新生成的残差",
                 "word": "同一道题改说法（人写同义改写表）后重新生成的残差",
                 "nm1/nm2": "幅度配平随机对照：clean + ‖臂残差−clean‖·随机单位向量，"
                            "与该臂补丁偏离 clean 的范数逐节点相等",
                 "null": "另一道题在同一步序号上的残差（陌生度失配，只作次要报告）"},
        "measures": {m: {"role": r, "note": nn} for m, r, nn in MEASURES},
        "primary_measure": PRIMARY,
        "honest_limits": [
            "只补决策位置那一个 token，「信息从哪个位置流过来」没测",
            "幅度配平仍有限：随机方向落在 2048 维里几乎在数据流形之外，"
            "而该臂的偏离是在流形上的 ⇒ 方向内/外之别混在里面，消不掉",
            "两个随机对照取均值（种子固定）；第三个对照在 CPU 上不划算",
            "content 臂重新生成过，臂间差异里混着「推理路线不同」",
            "靶子是措辞 token 不是答案 token。paired_v2 的 128 步窗口里没有答案 token，"
            "测「为什么写出那个数字」要重生成 700 步 CoT（CPU 约 40 分钟/题），本轮没测",
            "措辞改写表是人写的，有拟合风险；6 题统计功效很低，不报 p 值",
        ],
        "gate_order": order,
        "gates": gates,
        "node_lens_agree": {str(x): round(st.mean(v), 4) for x, v in sorted(lens.items())},
        "cosine_by_arm": {arm: {str(x): round(st.mean(v), 4) for x, v in sorted(nd.items())}
                          for arm, nd in cos.items()},
        "problems": [{
            "pid": p["pid"], "k": p["k"],
            "token_explained": p["token_explained"], "token_text": p["token_text"],
            "clean_top1_text": p["clean_top1_text"],
            "num_top1_text": p["num_top1_text"], "num_differs": bool(p["num_differs"]),
            "num_edit": p["num_edit"],
            "word_top1_text": p["word_top1_text"], "word_differs": bool(p["word_differs"]),
            "word_edit": p["word_edit"],
            "null_pid": p["null_pid"], "null_top1_text": p["null_top1_text"],
            "clean_logp_target": p["clean_logp_target"],
            "nodes": [{
                "node": r["node"],
                "lens_agree": r["lens_agree"],
                "logp_target_num": r["num"]["logp_target"] if r.get("num") else None,
                "logp_target_word": r["word"]["logp_target"] if r.get("word") else None,
                "logp_target_null": r["null"]["logp_target"],
                "excess_num": r.get("excess_num"), "excess_word": r.get("excess_word"),
                "transfer_num": r.get("transfer_num"), "transfer_word": r.get("transfer_word"),
                "excessm_num": r.get("excessm_num"), "excessm_word": r.get("excessm_word"),
                "flip_num": r.get("flip_num"), "flip_word": r.get("flip_word"),
                "flip_null": r.get("flip_null"),
            } for r in p["rows"]],
        } for p in P],
    }
    for m, _, _ in MEASURES:
        for arm in ARMS:
            art[f"node_{m}_{arm}"] = node_mean(f"{m}_{arm}")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(art, open(OUT, "w"), ensure_ascii=False, indent=2)
    log(f"\n产物 → {OUT}  ({os.path.getsize(OUT)/1024:.1f} KB)")

    log("\n门")
    for k in order:
        g = gates[k]
        log(f"  {k:<20} {g['verdict'].upper():<5} {g['name']}")
    log("\n统计：" + "  ".join(
        f"{v.upper()}={sum(1 for o in gates.values() if o['verdict'] == v)}"
        for v in ("pass", "fail", "na")))
    log("**没过的那几道必须原样上页面。**")


if __name__ == "__main__":
    main()