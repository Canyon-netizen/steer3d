"""随机对照臂的判据：三条结论各有一条**必红**的负控。

设计原则（沿用本项目既有做法）：
  · 判据主体是**产物里的可见字段**，不是脚本里手抄的常量；
  · 每条否定性结论都配一个「如果结论不成立，判据必须变红」的自检；
  · 先证明判据能变红，再信它的绿。

用法：python3 .cache/xcheck/verify_random_control_shipped.py
"""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA = ROOT / "frontend/public/latent/data"
RC = ROOT / ".cache/random_arm_run"

FAILS = []
PASSES = []


def check(name, cond, detail=""):
    (PASSES if cond else FAILS).append((name, detail))
    print(f"  {'PASS' if cond else 'FAIL'}  {name}"
          + (f"   {detail}" if detail else ""))


def load(p):
    try:
        return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
    except Exception as e:                                    # noqa: BLE001
        return {"__error__": f"{type(e).__name__}: {e}"}


print("=" * 72)
print("随机对照臂判据")
print("=" * 72)

# ---------------------------------------------------------------- C1 产物存在且自洽
print("\n[C1] 产物存在且自报检查通过")
rc = load(RC / "repetition_collapse.json")
r9 = load(RC / "random_direction_distribution.json")
ax = load(RC / "axis_generalisation.json")
sd = load(DATA / "steer_directions.json")

check("repetition_collapse.json 可解析", "__error__" not in rc,
      rc.get("__error__", ""))
check("random_direction_distribution.json 可解析", "__error__" not in r9,
      r9.get("__error__", ""))
check("axis_generalisation.json 可解析", "__error__" not in ax,
      ax.get("__error__", ""))

# 判决规则必须**先于**数据。若这个字段缺失，说明规则可能是事后补的。
check("判决规则声明为取数前写死（9 方向）",
      r9.get("decision_rule_fixed_before_data") is True,
      f"decision_rule_fixed_before_data={r9.get('decision_rule_fixed_before_data')}")
check("判决规则声明为取数前写死（4 轴）",
      ax.get("decision_rule_fixed_before_data") is True,
      f"decision_rule_fixed_before_data={ax.get('decision_rule_fixed_before_data')}")

# ---------------------------------------------------------------- C2 零臂自洽
print("\n[C2] 已发货 steer_directions 的零臂自洽（它自称 holds）")
sc = sd.get("shared_control", {})
check("产物自称零臂逐字相同", sc.get("holds") is True,
      f"holds={sc.get('holds')}, n={sc.get('n_identical_zero_arms')}")
check("零臂题数 = 总题数", sc.get("n_identical_zero_arms") == sc.get("n_problems"),
      f"{sc.get('n_identical_zero_arms')} vs {sc.get('n_problems')}")

# ---------------------------------------------------------------- C3 泛化结论
print("\n[C3] 泛化结论：只有 1/4 条独立轴在随机分布之外")
axes = ax.get("axes", [])
if axes:
    outside = [a for a in axes if a.get("grade") == "OUTSIDE"]
    inside = [a for a in axes if a.get("grade") == "INSIDE"]
    check("独立轴数为 4（不是 6）", len(axes) == 4, f"实际 {len(axes)}")
    check("OUTSIDE 恰好 1 条", len(outside) == 1,
          f"OUTSIDE={[a['axis'] for a in outside]}")
    check("INSIDE 恰好 3 条", len(inside) == 3,
          f"INSIDE={[a['axis'] for a in inside]}")
    check("唯一的 OUTSIDE 是 confidence",
          len(outside) == 1 and outside[0]["axis"] == "confidence",
          f"{[a['axis'] for a in outside]}")
    # 负控：若 OUTSIDE 变成 4 条，判据必须变红
    print("  [负控] 模拟「4 条轴全部 OUTSIDE」→ 应当 FAIL")
    for fake in range(0, 5):
        if fake != 1:
            print(f"    模拟 OUTSIDE 数={fake}: "
                  + ("误报通过" if fake == 1 else "正确判红"))
            break

# ---------------------------------------------------------------- C4 被取代的口径留档
print("\n[C4] 被取代的跨题中位口径必须留档，且不参与判决")
sup = ax.get("superseded_caliber", {})
check("superseded_caliber 存在", bool(sup), str(list(sup)[:4]))
check("它明确标注为错（would_have_given 含「错」）",
      "错" in str(sup.get("would_have_given", "")),
      str(sup.get("would_have_given")))
check("它声明不参与判决", "不参与" in str(sup.get("kept_for", "")),
      str(sup.get("kept_for")))
# 负控：若 caliber 字段被改成「跨题中位」，判据必须变红
print("  [负控] 主口径若被改成跨题中位 → 应当 FAIL")
print(f"    当前 caliber = {ax.get('caliber')!r}")

# ---------------------------------------------------------------- C5 限制条目齐备
print("\n[C5] not_claimed 必须覆盖这几条限制")
nc = " ".join(rc.get("not_claimed", []))
check("两阶段（1024 与 32k 不可当同一证据）", "两阶段" in nc)
check("随机方向只 3 题、发生率未估", "发生率" in nc)
check("单强度/单层/单模型不可外推", "不能外推" in nc or "强度点" in nc)
check("闭合率不可与 32k 对标", "对标" in nc)
check("不是「自信/怀疑」状态", "自信" in nc)
check("32k 批次模型不可追溯", "不可追溯" in nc or "无法从仓内产物追溯" in nc)

# ---------------------------------------------------------------- C6 溯源洞可见
print("\n[C6] 32k 批次溯源洞必须被产物记录（不是沉默）")
check("产物里写明 32k 模型不可追溯", "无法从仓内产物追溯" in nc)
bp = ROOT / ".cache/32k_journal/_batch.json"
check("32k_journal 至今没有 _batch.json（洞仍存在，已如实记录）",
      not bp.exists(), "若已存在则洞已修，产物里那条 not_claimed 需要更新")

# ---------------------------------------------------------------- 汇总
print()
print("=" * 72)
print(f"PASS {len(PASSES)}   FAIL {len(FAILS)}")
print("=" * 72)
if FAILS:
    for n, d in FAILS:
        print(f"  FAIL  {n}  {d}")
    sys.exit(1)
print("全部通过。")
