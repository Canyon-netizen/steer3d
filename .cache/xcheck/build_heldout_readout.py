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
