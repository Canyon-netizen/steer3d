"""P9 装置符号基准判定的自检：既要能判红，也要**证明新判据比旧判据严**。

## 背景（这轮修的是什么）

旧 P9 只判两条剂量单调：`+w@1.0 >= +w@0.5` 且 `-w@1.0 <= -w@0.5`。
问题在于这条断言**饱和**：`0.0 >= 0.0` 成立。于是实测到的

    aime__aime25__p00__no_think
      w+@0.5=0.0  w+@1.0=0.0  w-@0.5=-0.0  w-@1.0=-0.0  rand@1.0=-0.25

在旧闸门下判 **PASS** —— 装置在这条轨迹上**一点没动**（效应 0.0），
却因为「0 不小于 0」而通过了符号基准。这正是本项目反复栽的同一族：
**饱和的断言对任何常量偏移都不敏感。**

修法：加一条「同剂量下 |w±| 必须超过 |rand|」。随机方向对照本来就跑在基准里，
所以这不是新加的魔数。剂量阶梯（P3 的 rel{0.5,1.0}）一个字没动。

## 两条纪律

1. **新旧对照写在同一个文件里**。只测新闸门的话，「它比旧的严」这句话没人验。
   T0 直接断言：同一份读数，旧闸门 PASS、新闸门 FAIL。
2. **既测判红也测判绿**。一个永远红的闸门和一个永远绿的闸门一样没用，
   所以 T1 必须造一份干净的正控，要求新闸门判 PASS。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("r6run", HERE / "r6_rerun.py")
R6 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R6)

FAILS = []
TOTAL = 0


def chk(name, cond, extra=""):
    global TOTAL
    TOTAL += 1
    print(f"  {'PASS' if cond else 'FAIL'}  {name}  {extra}")
    if not cond:
        FAILS.append(name)


def old_p9(bench):
    """旧 P9 判定，原样搬来当参照。**只用于对照，不参与判决。**"""
    for r in bench.values():
        up_mono = r.get("w+@1.0", 0.0) >= r.get("w+@0.5", 0.0)
        dn_mono = r.get("w-@1.0", 0.0) <= r.get("w-@0.5", 0.0)
        if not (up_mono and dn_mono):
            return False
    return True


def mk(**kw):
    """造一条基准读数。"""
    return kw


def judge(bench, mode="no_think"):
    modes = {t: mode for t in bench}
    bv, ok = R6.p9_verdict(bench, modes)
    return bv, ok


print("=" * 74)
print("P9 装置符号基准：饱和漏洞 + 正控 + 判红")
print("=" * 74)

# ---- T0 牙齿：零响应在旧闸门下 PASS、在新闸门下 FAIL ----
# 这份读数是 r6_smoke_t1.json 里 p00_no_think 的**实测值**，不是我编的。
DEAD = {"aime__aime25__p00__no_think":
        mk(**{"w+@0.5": 0.0, "w+@1.0": 0.0, "w-@0.5": -0.0, "w-@1.0": -0.0,
             "rand@0.5": -0.0, "rand@1.0": -0.25})}
bv, ok = judge(DEAD)
chk("T0a 零响应在新闸门下判 FAIL", ok is False, f"pos_ok={ok}")
chk("T0b T0 这份数据在**旧**闸门下是 PASS（否则这条判据没有牙齿）",
    old_p9(DEAD) is True, f"old_p9={old_p9(DEAD)}")
v = bv["aime__aime25__p00__no_think"]
chk("T0c 失败原因点明「未超过随机方向」",
    not v["w+_beats_rand"] and not v["w-_beats_rand"] and v["why"],
    f"why={v['why']}")
chk("T0d 饱和自查：这份读数里 w+ 的剂量差确实为 0（否则就不是饱和反例）",
    DEAD["aime__aime25__p00__no_think"]["w+@1.0"]
    - DEAD["aime__aime25__p00__no_think"]["w+@0.5"] == 0.0)

# ---- T1 正控：干净的正效应必须 PASS（闸门不能永远红）----
CLEAN = {"t1": mk(**{"w+@0.5": 0.5, "w+@1.0": 1.0,
                    "w-@0.5": -0.5, "w-@1.0": -1.0,
                    "rand@0.5": 0.0, "rand@1.0": 0.25})}
bv, ok = judge(CLEAN)
chk("T1a 干净正效应判 PASS（闸门可满足，不是永远红）", ok is True,
    f"pos_ok={ok} why={bv['t1']['why']}")
chk("T1b PASS 时不得给出失败原因", bv["t1"]["why"] == [])

# ---- T2 非单调判红 ----
NONMONO = {"t2": mk(**{"w+@0.5": 0.5, "w+@1.0": 0.25,
                      "w-@0.5": -0.5, "w-@1.0": -1.0,
                      "rand@0.5": 0.0, "rand@1.0": 0.0})}
bv, ok = judge(NONMONO)
chk("T2 +w 非单调升判 FAIL", ok is False and not bv["t2"]["up_mono"],
    f"why={bv['t2']['why']}")

# ---- T3 符号翻转判红（实测 p00_think / p01_no_think 就是这个形态）----
FLIP = {"t3": mk(**{"w+@0.5": 0.0, "w+@1.0": -1.25,
                   "w-@0.5": -0.25, "w-@1.0": -0.75,
                   "rand@0.5": 0.25, "rand@1.0": -0.0})}
bv, ok = judge(FLIP)
chk("T3 +w 剂量越大越负判 FAIL（符号翻转）", ok is False and not bv["t3"]["up_mono"],
    f"why={bv['t3']['why']}")

# ---- T4 效应与随机方向同量级 => 判 FAIL ----
NOISE = {"t4": mk(**{"w+@0.5": 0.25, "w+@1.0": 0.75,
                     "w-@0.5": -0.25, "w-@1.0": -0.75,
                     "rand@0.5": -0.25, "rand@1.0": 0.75})}
bv, ok = judge(NOISE)
chk("T4 效应不超过随机方向判 FAIL（与噪声不可区分）", ok is False,
    f"why={bv['t4']['why']}")

# ---- T5 全部通过才 pos_ok；一条红就整体红 ----
MIX = dict(CLEAN); MIX["t2"] = NONMONO["t2"]
bv, ok = judge(MIX)
chk("T5 三条里一条红则整体 pos_ok=False", ok is False and len(bv) == 2,
    f"pos_ok={ok} n={len(bv)}")

# ---- T6 剂量阶梯没被动过（防止有人为了求绿改 rel）----
chk("T6 剂量阶梯仍是 P3 预登记的 rel{0.5,1.0}",
    R6.REL_LADDER == [0.5, 1.0], f"REL_LADDER={R6.REL_LADDER}")

print()
print("=" * 74)
print(f"总计 {TOTAL} 项，失败 {len(FAILS)}")
if FAILS:
    print("失败项:", FAILS)
print("=" * 74)
print("=> " + ("P9 判定可用。" if not FAILS else "**P9 判定有问题，先修。**"))
sys.exit(0 if not FAILS else 1)
