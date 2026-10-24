#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""_spec_crosscheck_24487.py —— **预登记 ↔ 实现**的机械对账（244.87）。

⚖⚖⚖⚖⚖ **口径真相源 = 预登记**（`.cache/xcheck/R6_CMAX_ROBUSTNESS_PREREG.md`）
   ⇒ ⇒ 实现里的每一个**口径参数**、每一**条判据**、每一个**形态**、
   **每一个闸门**、**每一项输入**都必须与预登记**对得上** ⇒ ⇒ 对不上 ⇒ ⇒ **红**。

⚖⚖⚖⚖⚖ **对账是「机械」的**：全部靠**正则从预登记的表格里抽**，⛔ **不许手抄**
   ⇒ ⇒ 预登记改了 ⇒ ⇒ 对账自动变红 ⇒ ⇒ 「预登记与实现对不上」这条**能红**。

⚖⚖⚖ **对账的内容**
   ① Q3 的 Wilson 置信水平（3 档）　② Q4 的基准变体（3 个 ＋ 各自的零格 base）
   ③ §3.2 的八条硬判据 id　　　④ §3.1 的四个形态 id
   ⑤ §5 的七道闸门 id　　　　　⑥ §2.1 的输入清单（I1–I8）＋ 实现多出的项（**必须报出来**）
   ⑦ §0.5 更正 ② 的**硬失败集合**　⑧ §5 的「五个形态」笔误**是否已被更正记录覆盖**

⚖ **正文字段的诚实边界**（沿用 244.86 的做法）：
   预登记「整体先于结果」这件事**靠签发时点**，⛔ **靠机器验不了** ⇒ ⇒
   本脚本只验「**口径与判据**对得上」，⛔ **不**声称验了「先于结果」。
"""

import importlib.util
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PREREG = os.environ.get("R244_PREREG",
                        "/home/zhourui/steer3d/.cache/xcheck/R6_CMAX_ROBUSTNESS_PREREG.md")
LEDGER = os.environ.get("R244_LEDGER",
                        "/home/zhourui/steer3d/.cache/xcheck/R6_RERUN_PREREG.md")
TARGET = os.environ.get("R244_TARGET", "cmax_robustness_audit.py")


def _read(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def _load_impl():
    path = os.path.join(HERE, TARGET)
    if not os.path.isfile(path):
        print("PRECOND_FAIL: 找不到被检实现 %s" % path)
        raise SystemExit(2)
    spec = importlib.util.spec_from_file_location("cmax_impl_24487", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _rows(text, pattern):
    """⚖ 从 markdown 表格里抽行（按行首模式）。"""
    return [l for l in text.split("\n") if re.match(pattern, l)]


def main():
    if not os.path.isfile(PREREG):
        print("PRECOND_FAIL: 预登记不存在：%s" % PREREG)
        return 2
    if not os.path.isfile(LEDGER):
        print("PRECOND_FAIL: 账本不存在：%s" % LEDGER)
        return 2

    P = _read(PREREG)
    M = _load_impl()

    ok = 0
    red = []

    def chk(name, cond, detail=""):
        nonlocal ok
        if cond:
            ok += 1
            print("  [OK ] %s%s" % (name, (" ｜ %s" % detail) if detail else ""))
        else:
            red.append(name)
            print("  [FAIL] %s%s" % (name, (" ｜ %s" % detail) if detail else ""))

    # ---- ① Q3：Wilson 置信水平 ----
    r3 = _rows(P, r"^\| \*\*Q3\*\*")
    if len(r3) != 1:
        chk("Q3 行唯一", False, "命中 %d 行" % len(r3))
    else:
        m = re.search(r"\{([0-9,\s]+)\}", r3[0])
        levels = tuple(int(x) for x in re.findall(r"\d+", m.group(1))) if m else ()
        chk("Q3 的 Wilson 置信水平 == 实现的 WILSON_LEVELS",
            levels == tuple(int(round(x * 100)) for x in M.WILSON_LEVELS),
            "预登记 %s vs 实现 %s" % (levels, M.WILSON_LEVELS))

    # ---- ② Q4：基准变体（3 个 ＋ 各自的零格 base）----
    #   ⚠⚠⚖ 比的是**「零格轨迹的 base 参数」**（0.25 / 0.5 / 0）⇒ ⇒ 必须用一个
    #   **每条轨迹都含零格**的合成分布去测 ⇒ ⇒ 否则算出来的是「该臂的基准」
    #   （它还取决于 (n_nz,n_zero) 分布本身 ⇒ ⇒ 比的不是同一件事）
    r4 = _rows(P, r"^\| \*\*Q4\*\*")
    if len(r4) != 1:
        chk("Q4 行唯一", False, "命中 %d 行" % len(r4))
    else:
        bases = sorted(set(float(x) for x in re.findall(r"base=([0-9.]+)", r4[0])))
        zero_only = {(2, 1): 2}          # ⚠ 每条轨迹都含零格 ⇒ ⇒ 基准 == 零格 base
        mine = sorted(set(round(M.base_from_dist(zero_only, v), 10)
                          for v in M.BASE_VARIANTS))
        chk("Q4 的基准变体数 == 3", len(M.BASE_VARIANTS) == 3,
            "实现 %d 个：%s" % (len(M.BASE_VARIANTS), M.BASE_VARIANTS))
        chk("Q4 的零格 base 取值集合 == 实现现算出的三个基准",
            bases == mine, "预登记 %s vs 实现 %s" % (bases, mine))
        chk("Q4 的三个基准都落在 [0,1]",
            all(0.0 <= b <= 1.0 for b in mine), "实现 %s" % mine)

    # ---- ③ §3.2 的八条硬判据 ----
    hs = [re.match(r"^\| \*\*(H\d+)\*\*", l).group(1)
          for l in _rows(P, r"^\| \*\*H\d+\*\*")]
    chk("§3.2 的硬判据 id == 实现的 CRIT_IDS",
        tuple(hs) == tuple(M.CRIT_IDS), "预登记 %s vs 实现 %s" % (hs, list(M.CRIT_IDS)))

    # ---- ④ §3.1 的四个形态 ----
    forms = [re.match(r"^\| \*\*([A-D])\*\*", l).group(1)
             for l in _rows(P, r"^\| \*\*[A-D]\*\*")]
    chk("§3.1 的形态 id == 实现的 FORMS",
        tuple(forms) == tuple(M.FORMS), "预登记 %s vs 实现 %s" % (forms, list(M.FORMS)))

    # ---- ⑤ §5 的七道闸门 ----
    gates = [re.match(r"^\| \*\*(G0-\d)\*\*", l).group(1)
             for l in _rows(P, r"^\| \*\*G0-\d\*\*")]
    chk("§5 的闸门 id == 实现的 GATE_IDS",
        tuple(gates) == tuple(M.GATE_IDS), "预登记 %s vs 实现 %s" % (gates, list(M.GATE_IDS)))

    # ---- ⑥ §2.1 的输入清单（I1–I8）＋ 实现多出的项 ----
    ids = [re.match(r"^\| \*\*(I\d+)\*\*", l).group(1)
           for l in _rows(P, r"^\| \*\*I\d+\*\*")]
    chk("§2.1 的输入清单条数 == 8", len(ids) == 8, "预登记 %s" % ids)
    I = M.parse_inputs(LEDGER)
    keymap = {
        "I1": ("i1_w_num", "i1_w_den"), "I2": ("i2_r_num", "i2_r_den"),
        "I3": ("i3_w_lo", "i3_w_hi"), "I4": ("i4_r_lo", "i4_r_hi"),
        "I5": ("i5_w", "i5_r"), "I6": ("i6_w", "i6_r"),
        "I7": ("i7_delta_obs", "i7_newcombe_lo", "i7_newcombe_hi"),
        "I8": ("i8_delta_obs_blk", "i8_boot_lo", "i8_boot_hi"),
    }
    missing = []
    for i in ids:
        for k in keymap.get(i, ()):
            if I.get(k) is None:
                missing.append("%s.%s" % (i, k))
    chk("§2.1 的每个输入都被实现解析出来", not missing, "缺 %s" % (missing or "无"))
    extra = []
    for i in ("I9",):
        if i not in ids:
            for k in ("i9_w_num", "i9_r_num"):
                if I.get(k) is not None:
                    extra.append("%s.%s（实现层加的：块级 Δ_obs 的交叉核对需要它）" % (i, k))
    print("  [INFO] 实现比预登记多出的输入项：%s" % (extra or "无"))

    # ---- ⑦ §0.5 更正 ② 的硬失败集合 ----
    m = re.search(r"硬失败集合 = \{([^}]*)\}", P)
    if not m:
        chk("§0.5 更正 ② 的硬失败集合写明", False, "没找到「硬失败集合 = {...}」")
    else:
        hard = tuple(re.findall(r"H\d+", m.group(1)))
        chk("§0.5 更正 ② 的硬失败集合 == 实现的 HARD_FAIL_IDS",
            hard == tuple(M.HARD_FAIL_IDS),
            "预登记 %s vs 实现 %s" % (hard, list(M.HARD_FAIL_IDS)))

    # ---- ⑧ §5 的「五个形态」笔误是否已被更正记录覆盖 ----
    g1 = _rows(P, r"^\| \*\*G0-1\*\*")
    if not g1:
        chk("§5 的 G0-1 行存在", False)
    else:
        five = ("五个" in g1[0])
        corrected = ("更正 ③" in P) and ("G0-1" in P)
        if five:
            chk("§5 G0-1 的「五个形态」已被 §0.5 更正 ③ 覆盖", corrected,
                "G0-1 行仍写着「五个」⇒ ⇒ 必须有更正记录把它读成「四个」⇒ ⇒ 更正 ③ %s"
                % ("在" if corrected else "**不在**"))
        else:
            chk("§5 G0-1 的形态个数写法", True, "写的是「四个」⇒ ⇒ 与 §3.1 一致")

    print("")
    print("对账条数：OK %d ｜ 红 %d" % (ok, len(red)))
    if red:
        print("红的条目：%s" % red)
        print("SPEC_RC=1")
        return 1
    print("SPEC_RC=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
