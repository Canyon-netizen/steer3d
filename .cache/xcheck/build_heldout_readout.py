"""把 §4.9 压成页面产物 heldout_readability.json。

**为什么不合并进 readable_subspace.json**：那个文件由
`build_subspace_readout.py` 生成，而那个脚本每次都会整体覆写。
把留出家族塞进去 ⇒ 谁先跑谁覆盖，最后一个跑的赢，且顺序错了没人报错。
⇒ 各自一个产物，脚本之间无依赖。

倍数（ratio）在这里算，不在手写。
上一轮 §4.9.1 的「倍数」列就是手算错的（128/113/110，实际 128.6/112.3/244.4），
根因就是把三条地板混着当分母。这里强制逐行取自己的地板，并打印出来供核对。
"""
import json
from pathlib import Path

ROOT = Path("/Users/zhourui/code/steer3d")
XC = ROOT / ".cache/xcheck"
OUT = ROOT / "frontend/public/latent/data/heldout_readability.json"

fam = json.loads((XC / "heldout_family.json").read_text())
spec = json.loads((XC / "heldout_specificity.json").read_text())
dup = json.loads((XC / "heldout_selfdup.json").read_text())
rec = json.loads((XC / "recipe_vs_readout.json").read_text())
var = json.loads((XC / "recipe_variants.json").read_text())

TR = fam["heldout_same_class_different_form"]
NF = fam["heldout_new_family"]

FORM = {
    "digit_top1": "top-1 是不是数字（二值，只看第 1 名）",
    "digit_frac_top64": "top-64 里数字的个数占比（不加权）",
    "digit_top8_presence": "top-8 里有没有数字（只看前 8）",
    "emitted_is_upper": "已发出 token 的首字母是否大写",
    "emitted_tok_len": "已发出 token 的字符长度",
    "emitted_has_digit": "已发出 token 是否含数字",
}
ORIGIN = {
    "digit_top1": "同底层分类，换函数形式",
    "digit_frac_top64": "同底层分类，换函数形式",
    "digit_top8_presence": "同底层分类，换函数形式",
    "emitted_is_upper": "新家族（已发出 token 的文本）",
    "emitted_tok_len": "新家族（已发出 token 的文本）",
    "emitted_has_digit": "新家族（已发出 token 的文本）",
}
NEW_CLEAN = 2.0   # 余量门槛：高于它才算「干净通过」

transfer = []
for k in ["digit_top1", "digit_frac_top64", "digit_top8_presence"]:
    rho, fl = TR[k], TR["floors"][k]
    transfer.append({
        "target": k,
        "form": FORM[k],
        "rho": rho,
        "floor": fl,
        # 分母逐行取自己的地板 —— 不共用一个常量
        "ratio": abs(rho) / abs(fl),
        "floor_from": "heldout_family.json / heldout_same_class_different_form",
    })

rows = []
for k in ["digit_top1", "digit_frac_top64", "digit_top8_presence",
          "emitted_has_digit", "emitted_is_upper", "emitted_tok_len"]:
    s = spec[k]
    margin = s["margin"]
    if k in NF and k in ("emitted_is_upper", "emitted_tok_len"):
        verdict = "new_clean" if margin >= NEW_CLEAN else "new_weak"
    else:
        verdict = "same_direction"
    r20 = NF.get(k, {}).get("rho_delta20")
    rows.append({
        "key": k,
        "label": k,
        "form": FORM[k],
        "origin": ORIGIN[k],
        "verdict": verdict,
        "rho_self": s["rho_self"],
        "floor": s["floor"],
        "worst_other": s["worst_other"],
        "worst_other_value": s["worst_other_value"],
        "margin": margin,
        "max_cos_named_axes": s["max_cos_named_axes"],
        "rho_delta20": r20,
        "decay_x20": (s["rho_self"] / abs(r20)) if (r20 not in (None, 0)) else None,
    })

ratios = [t["ratio"] for t in transfer]
n_same = sum(1 for r in rows if r["verdict"] == "same_direction")
n_clean = sum(1 for r in rows if r["verdict"] == "new_clean")
n_weak = sum(1 for r in rows if r["verdict"] == "new_weak")


def _variant_row(vname, m):
    """一个变体格子：余量 + **谁在约束** + 这个归属分不分得开。

    `tie` 的判据用 gap/sem < 2：两个竞争者差距不到 2 个标准误，
    `max` 选中谁是任意的，此时 margin 只应读成「并列里的下界」。
    """
    gap_sem = m.get("top2_gap_over_sem")
    return {
        "name": vname,
        "short": vname.replace("V1_", "").replace("V2_", "")
                     .replace("V3_", ""),
        "rho_own": m["rho_own"],
        "rho_own_sem": m.get("rho_own_sem"),
        "worst_name": m.get("worst_other_name"),
        "worst_rho": m.get("worst_other"),
        "runner_up_name": m.get("runner_up_name"),
        "runner_up_rho": (m["rho_others"].get(m["runner_up_name"])
                          if m.get("runner_up_name") else None),
        "gap_over_sem": gap_sem,
        # 归属不可判 ⇒ 这个 margin 不能当结论印
        "tie": (gap_sem is not None and gap_sem < 2.0),
        "margin": m["margin"],
        "n_positive": m.get("n_positive_total"),
    }


def _attribution(v1, v2):
    """余量涨了多少，其中自身涨 / 竞争者掉各占多少（对数分解，可加）。

    1.146× → 1.675× 看着像「配方变干净了」，但拆开常常是竞争者掉得多。
    不给这个分解，读者会把功劳记在配方结构上。
    """
    import math
    own1, own2 = v1["rho_own"], v2["rho_own"]
    w1, w2 = v1["worst_other"], v2["worst_other"]
    tot = math.log(v2["margin"] / v1["margin"])
    return {
        "from": "V1_naive", "to": "V2_banded",
        "margin_from": v1["margin"], "margin_to": v2["margin"],
        "own_from": own1, "own_to": own2,
        "own_change_pct": (own2 / own1 - 1.0) * 100.0,
        "worst_from": w1, "worst_to": w2,
        "worst_change_pct": (w2 / w1 - 1.0) * 100.0,
        "worst_name_from": v1["worst_other_name"],
        "worst_name_to": v2["worst_other_name"],
        "share_from_competitor": (-math.log(w2 / w1) / tot * 100.0) if tot else None,
    }

payload = {
    "schema": "heldout_readability/v1",
    "question": "换一批从头到尾没参与过调参的观测量，这套判据还找不找得到东西？",
    "convention": {
        "source_direction": "w*(digit_mass)，L14，K=256 PCA，stride=2",
        "floor": "把目标在轨迹内打乱后同一个方向还能预测多少（逐行独立估计）",
        "margin_rule": "余量 = 自己对角 ÷ 同表最高别人（绝对值）",
        "new_clean_threshold": NEW_CLEAN,
        "note": "两份产物的打乱地板来自两次独立运行，**不要跨表比小数位**。",
    },
    "headline": {
        "heldout_total": len(rows),
        "transfer_targets": len(transfer),
        "ratio_min": min(ratios),
        "ratio_max": max(ratios),
        "same_direction": n_same,
        "new_clean": n_clean,
        "new_weak": n_weak,
        "verdict_line": ("非循环证据 %d–%d 倍地板；但 %d 个留出量里只有 %d 个是新方向"
                         "（干净 %d、弱 %d）。"
                         % (round(min(ratios)), round(max(ratios)),
                            len(rows), n_clean + n_weak, n_clean, n_weak)),
    },
    "transfer": transfer,
    "rows": rows,
    "selfdup": dup,
    "recipe": {
        "target": "emitted_is_upper",
        "how": "diff_of_means(首字母大写组, 非大写组)，与现有 4 条命名轴同一套配方",
        "selfcheck_cos": rec["recipe_selfcheck"]["cos"],
        "loo_rho": rec["loo_rho"]["emitted_is_upper"]["mean"],
        "loo_floor": rec["loo_rho"]["emitted_is_upper"]["floor_mean"],
        "loo_folds": rec["loo_rho"]["emitted_is_upper"]["n_folds"],
        "loo_range": [rec["loo_rho"]["emitted_is_upper"]["min"],
                      rec["loo_rho"]["emitted_is_upper"]["max"]],
        "control_confidence_same_code": rec["loo_rho"]["confidence_same_code"]["mean"],
        "cos_recipe_vs_ridge": rec["cos_recipe_vs_ridge_wstar"],
        "cos_recipe_vs_caution_axis": rec["where_does_the_recipe_point"]["cos_recipe_vs_caution_axis"],
        "cos_recipe_vs_caution_readout": rec["where_does_the_recipe_point"]["cos_recipe_vs_caution_readout"],
        "recipe_loo_on_entropy": rec["where_does_the_recipe_point"]["recipe_loo_on_entropy"],
        "recipe_loo_on_selfcheck": rec["where_does_the_recipe_point"]["recipe_loo_on_self_check"],
        "specificity_margin": (rec["loo_rho"]["emitted_is_upper"]["mean"]
                               / rec["where_does_the_recipe_point"]["recipe_loo_on_entropy"]),
        "relative_amplitude": rec["scale"]["relative"],
        # §4.11：换配方结构（熵带内差）能把余量抬到多少。
        #
        # ⚠ 余量 = 自身 / max(竞争者)，而 **max 选中了谁必须一起报出来**：
        #   去混杂把熵压下去之后，最紧的约束方会换人。V2 上 entropy 0.2236 与
        #   self_check 0.2241 只差 0.03 sem —— `max` 选中谁是任意的，
        #   报出来的 1.675× 只是一个并列里的下界。
        # ⇒ 每条都带 worst/runner_up 身份 + gap_over_sem + tie 标记。
        #   不印这些，页面上的「1.68×」会被读成干净的结论。
        "variants": [_variant_row(v, m) for v, m in var["targets"]["emitted_is_upper"].items()],
        "control_self_check": [
            _variant_row(v, m) for v, m in var["targets"]["self_check"].items()],
        "closure_v1_selfcheck_vs_caution_axis": var["closure_v1_selfcheck_vs_caution_axis"],
        "best_margin": max(m["margin"] for m in
                           var["targets"]["emitted_is_upper"].values()
                           if m["margin"]),
        "clean_threshold": 2.0,
        # 涨幅归因：自身涨了多少 vs 竞争者掉了多少。1.15× → 1.68× 看着是「变干净了」，
        # 拆开看几乎全是竞争者下降 —— 这个数不给，读者会归因到配方本身。
        "margin_gain_attribution": _attribution(
            var["targets"]["emitted_is_upper"]["V1_naive"],
            var["targets"]["emitted_is_upper"]["V2_banded"]),
        # 约束方是否换过人。换了人就不能说「这条配方方向本来就是 X」。
        "control_binding_swapped": (
            var["targets"]["self_check"]["V1_naive"]["worst_other_name"]
            != var["targets"]["self_check"]["V2_banded"]["worst_other_name"]),
        "verdict": ("可读 ✓ / 有配方 ✓ / 可注入 ✗ —— 配方专一性余量只有 %.2f×"
                    "（读出方向是 %.2f×），预测熵几乎和预测自己目标一样强。"
                    % (rec["loo_rho"]["emitted_is_upper"]["mean"]
                       / rec["where_does_the_recipe_point"]["recipe_loo_on_entropy"],
                       [r for r in rows if r["key"] == "emitted_is_upper"][0]["margin"])),
    },
    "verdict": (
        "两件事必须分开说：① w*(digit_mass) 换到二值、不加权、只看前 8 都还成立，"
        "说明它是「数字内容」这个方向，不是「top-64 加权方式」的产物；"
        "② 但专属性把其中三个判成同一条方向的重新构造（余量 ≈ 1.0×），"
        "另两个才是新方向 —— 其中 emitted_is_upper 干净通过（余量 %.2f×，"
        "对 4 条命名轴只有 %.3f），emitted_tok_len 余量 %.2f× 只能算弱通过。"
        % (rows[4]["margin"], rows[4]["max_cos_named_axes"], rows[5]["margin"])
    ),
    "not_claimed": (
        "这里测的仍然只是**可读性**。「沿这条方向注入会不会改变行为」一次都没测过，"
        "所以不能说任何一条是可干预的。另外不能说「可读方向只有这几条」—— "
        "这一轮补进来 2 条真正的新方向（emitted_is_upper / emitted_tok_len），"
        "可读子空间的下界因此从 12 抬到 **14**（20 个候选、|cos|<0.5）。"
        "而 14 仍然是下界：它依赖候选观测量集合，也依赖那个 0.5 的分隔门槛"
        "（门槛 0.45 就退回 12 条）。详见 SubspacePanel 里的门槛敏感性。"
    ),
    "sources": {
        "non_circular": "xcheck/heldout_family.json",
        "specificity": "xcheck/heldout_specificity.json",
        "selfdup": "xcheck/heldout_selfdup.json",
    },
}

OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1))

print("=== 迁移（非循环）：w*(digit_mass) 预测换形式的量 ===")
for t in transfer:
    print("  %-22s rho %.4f  地板 %+.4f  倍数 %.1f×" % (t["target"], t["rho"], t["floor"], t["ratio"]))
print()
print("=== 专属性：6 个留出量是不是新方向 ===")
for r in rows:
    print("  %-22s %-13s 余量 %5.2f×  最高别人 %-20s %+.4f  Δ=20 %s"
          % (r["key"], r["verdict"], r["margin"], r["worst_other"],
             r["worst_other_value"],
             ("%+.4f" % r["rho_delta20"]) if r["rho_delta20"] is not None else "未测"))
print()
print("headline:", payload["headline"]["verdict_line"])
print("selfdup :", dup["verdict"], "| 同一步 %.4f 错开一步 %.4f"
      % (dup["pooled"]["same_step"], dup["pooled"]["lag1"]))
print("已写", OUT)
