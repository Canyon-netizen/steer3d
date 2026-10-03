"""把 2026-10-03 的专属性检验结果写进页面数据。

背景：`backtrack_topk` 那一格上，最优读出方向 w* 与 confidence 轴的余弦
（0.3341）高于与 caution 轴的（0.3077）⇒ 「回退标记是 caution 的读出方向」
不成立。同时 confidence 那一格虽然过了专属性，但它的目标 top1_prob_renorm
与 entropy 的 Pearson 是 0.96，而 confidence 的定义分组就是熵的 p30/p75 差
⇒ 构造恒等式，只能算装置阳性对照。

数值来源：`.cache/completeness/completeness.json` 的 `apparatus_repro`，
已由 `.cache/xcheck/verify_crosstalk.py` 独立复算（四个余弦对到 4 位小数）。
本脚本只做搬运与判决，不重新计算。
"""
import json
from pathlib import Path

ROOT = Path("/Users/zhourui/code/steer3d")
SRC = ROOT / ".cache/completeness/completeness.json"
DST = ROOT / "frontend/public/latent/data/axis_readouts.json"

COMP = json.loads(SRC.read_text())
PAY = json.loads(DST.read_text())

rows = COMP["apparatus_repro"]["rows"]
pair = COMP["named_span_S"].get("pairwise_abs_cos", {})
PAIR_CONF_CAUT = pair.get("confidence|caution")

AX_KEY = {"confidence": "confidence", "caution": "caution",
          "creativity": "creativity", "reasoning": "reasoning_deep"}


def block(ax_name):
    r = rows[ax_name]
    cpa = r["cos_per_axis_median"]
    return {
        "cell": r["target"],
        "axis_of_report_row": r["axis_of_report_row"],
        "cos_per_axis": {k: round(v, 4) for k, v in cpa.items()},
        "strongest_axis": r["strongest_other_axis_on_same_cell"] if r["cross_talk_flag"]
        else r["axis_of_report_row"],
        "row_axis_cos": round(cpa[r["axis_of_report_row"]], 4),
        "row_axis_is_strongest": not r["cross_talk_flag"],
    }


# confidence：过了专属性，但目标是构造恒等式
# ⚠ §8.9 第十四笔：0.96 原来也是字面量。真源在 completeness.json 的
#   redundancy_audit.pairs_pearson_exceeding = [["top1_prob_renorm","entropy",0.96005…]]
#   （第四个数是 Spearman 0.9915）。本脚本的 SRC 就是那份文件 ⇒ 现算。
# ⚠ 查的时候要**按 (观测对) 定位**，不能拿「找一个等于 0.96 的数」当证据 ——
#   那份文件里 0.96 前后的浮点数多得很，随便一个都能凑上（同族：容差 haystack 假绿）。
PAIR = None
for _a, _b, _p, _s in COMP.get("redundancy_audit", {}).get("pairs_pearson_exceeding", []):
    if {_a, _b} == {"top1_prob_renorm", "entropy"}:
        PAIR = (round(_p, 2), round(_s, 3))
if PAIR is None:
    raise SystemExit("completeness.json 里找不到 (top1_prob_renorm, entropy) 的 Pearson —— "
                     "confidentiality 那句 note 的 0.96 会变成无源的字面量，拒绝写。")

spec_conf = block("confidence")
spec_conf.update({
    "specific": True,
    "verdict": "tautological",
    "note": ("目标是 top1_prob_renorm，与 entropy 的 Pearson " + str(PAIR[0])
             + "（Spearman " + str(PAIR[1]) + "）；而 "
             "confidence 的定义分组就是熵 p30 vs p75 的差 ⇒ 这一格是构造恒等式，"
             "只能算装置阳性对照，不是独立于定义式的证据。"),
})
# caution：非循环，但不专属
spec_caut = block("caution")
_cpa = rows["caution"]["cos_per_axis_median"]
spec_caut.update({
    "specific": False,
    "verdict": "shared",
    "pair_cos_confidence_caution": PAIR_CONF_CAUT,
    "note": ("同一格上 confidence 轴的余弦 " + str(round(_cpa["confidence"], 4))
             + " 高于 caution 轴的 " + str(round(_cpa["caution"], 4)) + "；"
             "而 cos(confidence, caution) = " + str(round(PAIR_CONF_CAUT, 4)) + "，"
             "两条轴本身就高度重叠，"
             "靠这一个读出量分不开它们。"),
})
PAY["axes"]["confidence"]["specificity"] = spec_conf
PAY["axes"]["confidence"]["status"] = "tautological"
PAY["axes"]["caution"]["specificity"] = spec_caut
PAY["axes"]["caution"]["status"] = "shared_readout"

# 其余两条：证据不足以做归属检验，明确标出来而不是留空
# ⚠ §8.9 第十四笔：这两句原来写死 0.039 / 0.057 / 0.339 / 0.628，
#   而它们取的是 **L14** 那一层，句中却只说「Δ=0」——
#   产物**同时**发布了 at_delta0.median_cos / median_control_cos，
#   而 creativity 的中位数是 0.0907 > 0.0554（**是超过对照的**），
#   与这句「未超位置对照」直接矛盾。
#   ⇒ 「未超」只在 L14 成立。这不是数错，是**把一个层特定的事实说成了普遍事实**：
#     读者拿 median_cos 一对就会以为写错了，而写的人也知道 0.039 来自哪一层。
#   ⇒ 处置：数字从 per_layer["14"] 现算，**并把层号写进句子里**。
#     这样句子与它引用的字段一一对应，判据也能按「句中声明的层」去核。
PRIMARY_LAYER = "14"   # 本项目的读出主层（L14；见 readable_subspace.convention.layer）


def d0_layer(ax, key):
    return round(PAY["axes"][ax]["at_delta0"]["per_layer"][PRIMARY_LAYER][key], 4)


def no_readout_note(ax, tail):
    c = d0_layer(ax, "cos")
    k = d0_layer(ax, "control_cos")
    return ("Δ=0 最佳候选（L" + PRIMARY_LAYER + "）" + str(c)
            + " 未超位置对照（L" + PRIMARY_LAYER + "）" + str(k) + "，" + tail)


PAY["axes"]["creativity"]["specificity"] = {
    "cell": None, "cos_per_axis": None, "specific": None, "verdict": "no_readout",
    "note": no_readout_note("creativity", "没有可归属的读出方向。"),
}
PAY["axes"]["reasoning"]["specificity"] = {
    "cell": None, "cos_per_axis": None, "specific": None, "verdict": "position_only",
    "note": no_readout_note("reasoning", "读出方向本身就是轨迹位置。"),
}

PAY["headline"]["measured"] = []
PAY["headline"]["tautological"] = ["confidence"]
PAY["headline"]["shared_readout"] = ["caution"]
PAY["headline"]["retraction_note"] = (
    "2026-10-03：原表把 confidence 与 caution 都标为「已测」。补做专属性检验后"
    "——confidence 那一格虽然专属，但目标与定义式 Pearson " + str(PAIR[0]) + "，是构造恒等式；"
    "caution 那一格虽然非循环，但同格上 confidence 轴对齐更高（"
    + str(round(_cpa["confidence"], 4)) + " vs " + str(round(_cpa["caution"], 4)) + "）。"
    "⇒ 「两条轴都测到了读出方向」已撤回，当前是 0 条既非循环、又专属。"
)
PAY["headline"]["vocabulary_caveat"] = PAY["headline"]["vocabulary_caveat"]

DST.write_text(json.dumps(PAY, ensure_ascii=False, indent=1))
print("已写", DST)
for ax, v in PAY["axes"].items():
    sp = v.get("specificity") or {}
    print("  %-12s status=%-14s verdict=%-12s" % (ax, v["status"], sp.get("verdict")))
print("headline.measured =", PAY["headline"]["measured"])
print("headline.tautological =", PAY["headline"]["tautological"])
print("headline.shared_readout =", PAY["headline"]["shared_readout"])
