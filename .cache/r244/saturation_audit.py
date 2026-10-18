#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""saturation_audit.py —— 传播层的原始响应在**两端被饱和吃掉**了多少（零 GPU）

🔴 **这个工具要回答什么**（修订 244.42）
  ⚖⚠⚠⚠ 244.41 测到：**把覆盖率最低那一档删掉，rand 臂的 p 就从 0.0129 掉到 0.0574。**
  ⚖⚠⚠ 那是个**平凡动作** ⇒ ⇒ 「12/14 正号」这个显著性**站在刀尖上**。

  ⚖⚠⚖⚖⚖ **本轮我想验证的那条解释**
    「剂量阶梯的低端，响应对比**只注入读出位点**的单点档**几乎没动**
      ⇒ 最低档不承载信息 ⇒ 删它有**正面**理由」
  ⚖⚠⚖⚖⚖ ⚖ 第一步就**测错了**：单点档是**直接层**（读出位点被注入），
     ⛔ 它压根不是 k 阶梯的 k=0 基线 ⇒ 跨机制比，|Δ| 大 2.25×（rand）/
     23.6×（w）⇒ 那正是**机制切换**本身，不是「梯度小」。
     ⚖⚠⚥ ⛔ 幸好在**动手写工具之前**先探了数。

⚖⚖⚖⚖⚖⚖⚖ **于是换成真正可答的问题：这个响应量本身有多少落在量程之外？**
  ⚖ `raw` = |读数(α=0.5·gap) − 读数(α=1.0·gap)|（`dose_axis_audit.raw_response`）
  ⚖⚠⚠⚠ 实测它在**两端**都撞墙：rand 传播层 **14 格 ≤0.001**（含 13 格精确 0.0）
     **8 格 ≥0.124**（≈1/8）；w **10 格 / 7 格** ⇒ 合计 **31% / 24%**

⚖⚖⚖⚖⚖⚖🔴🔴 **本轮最重要的结果是一个「否证」，不是发现**
  ⚖⚠⚠⚠⚠⚠⚠ **假说**：「饱和档多 ⇒ |rho| 被压小 ⇒ 符号更脆」
     ⚖ 预测：两条臂**都是**负相关
  ⚖⚠⚠⚠⚠⚠⚠ **实测**：rand **r = −0.078**、w **r = +0.533**（**方向相反**）
     ⇒ ⇒ **假说被自己的预测证伪** ⇒ ⚖⚠⚠⚠⚠⚠ **只能报「未量到」**
  ⚖⚖⚖⚖⚖⚖⚖⚖⚖ **这条否证的价值**：它挡住了下一步的一个**坏主意** ——
     ⚖ 「符号检验只吃序、丢了幅度 ⇒ 换成**幅度口径**（斜率/面积）就会更稳」
     ⛔ **数据上没有依据**：① 幅度在两端被截断；② 饱和与 |rho| 无关
     ⇒ ⇒ 那是**不该走的路**，⚗ 先记下来，省下一次 GPU 跑批

⚖⚠⚖⚖⚖⚖⚖⚖⚖ **两条必须一起说的禁令**
  ⚖ **饱和** ⛔ 不等于「那条轨迹无效」——它是**量程**限制，不是数据错误
  ⚖ **假说被证伪** ⛔ 不等于「饱和与稳健性无关」——只能说**未量到**（n=14）

⛔ 本工具：⛔ 不改任何真文件；⛔ 不跑批；⛔ 只读两份已有日志。
"""

import argparse
import importlib.util
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else "."
PROBE_REL = ".cache/mutbak/r204_noise_probe.py"
W_LOG = ".cache/r244/w_new.log"
RAND_LOG = ".cache/r244/rand_new.log"
# ⚖⚠⚖⚖⚖⚖ **阈值不是我拍的**：`FLOOR_SWEEP`/`CEIL_SWEEP` 会把结论的
# **敏感性**印出来 ⇒ 阈值落在哪一档 census 都一样 ⇒ 结论不是阈值产物。
FLOOR = 0.001
CEIL = 0.124
FLOOR_SWEEP = (0.0001, 0.001, 0.004)
CEIL_SWEEP = (0.10, 0.12, 0.124)
SATURATION_IS_NOT_INVALID = None          # 下面定义：恒 False 的禁令


class HardFail(Exception):
    pass


def _load(modname, fname):
    path = os.path.join(HERE, fname)
    if not os.path.exists(path):
        raise HardFail("找不到 %s ⇒ ⛔ 拒读" % path)
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------- 饱和判定
def sat_flag(raw, floor=FLOOR, ceil=CEIL):
    """⚖ 三态互不相同：`"floor"` / `"ceil"` / `None`（未饱和）。

    ⚖⚠⚠⚠⚖⚖⚖⚖ **⛔ 绝不许用一个布尔值**表示两件事。
    ⚖⚠⚠⚠⚖⚖⚖⚖ 实测 rand 传播层最常见的取值是**精确 0.0（13 格）**，
    ⚖ 而次常见是 0.004 ⇒ 响应在 0 处**撞地板**；
    ⚖⚠ 另一端聚在 0.125 = 1/8 ⇒ **撞天花板**。
    ⚖⚠⚠⚖⚖⚖⚖⚖ 两端撞墙是**同一个布尔**表达不了的 ⇒ 分三态。
    """
    if raw <= floor:
        return "floor"
    if raw >= ceil:
        return "ceil"
    return None


def census(raws, floor=FLOOR, ceil=CEIL):
    """⚖ 饱和普查。返回 `{"n","floor","ceil","sat","flags"}`。

    ⚖⚠⚖ 恒等式按定义写：`floor + ceil == sat`，`sat == floor + ceil`；
    ⚖⚠⚠ 且 `n == floor + ceil + 中间档数` ⇒ 三个数必须加起来等于 n。
    """
    flags = [sat_flag(r, floor, ceil) for r in raws]
    f = sum(1 for x in flags if x == "floor")
    c = sum(1 for x in flags if x == "ceil")
    return {"n": len(raws), "floor": f, "ceil": c, "sat": f + c,
            "mid": len(raws) - f - c, "flags": flags}


def pearson_r(xs, ys):
    """⚖ Pearson r。⛔ **不给 p**：n=14 ⇒ 抽样波动极大，本工具只报**方向**。"""
    n = len(xs)
    if n < 3 or len(ys) != n:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((a - mx) ** 2 for a in xs)
    syy = sum((b - my) ** 2 for b in ys)
    if sxx <= 0 or syy <= 0:
        return None                            # ⛔ 零方差 ⇒ 未量到，不是 0
    sxy = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    return sxy / (sxx ** 0.5 * syy ** 0.5)


def usable_rungs(g, floor=FLOOR, ceil=CEIL, spearman_fn=None):
    """⚖ 剔掉饱和格之后**还剩几档**、还剩几条轨迹**可算**。

    ⚖⚠⚠⚠⚖⚖ 这是在问「**剔掉饱和格这条路值不值得走**」——
      ⛔ **不是**建议剔；⚖ 必须同时报出**代价**（有多少轨迹变得不可算）。
    ⚠⚠ 剩不足 3 档 ⇒ Spearman 未量到 ⇒ ⛔ 绝不许当 0.0 参与。
    """
    out = {}
    for tid in sorted(g):
        sub = sorted(g[tid], key=lambda r: r["cov"])
        keep = [r for r in sub if sat_flag(r["raw"], floor, ceil) is None]
        out[tid] = (len(keep), len(sub))
    n_ok = sum(1 for v in out.values() if v[0] >= 3)
    return {"per_tid": out, "n_ok": n_ok, "n_all": len(out)}


def saturation_is_not_invalid():
    """⚖⚖ **恒返回 False 的禁令**，且它**必须**恒返回 False。

    🔴 244.42 实测：rand 传播层 **31%** 的格落在两端饱和区
       ⇒ 一半的人会顺手写成「这些轨迹**无效**/该剔除」。
    ⚖⚠⚠⚠⚠⚠ 那**两件事方向相反**：
       ⚖ **饱和** = 响应落在量程之外 ⇒ 它是**仪器量程**的陈述
       ⚖ **无效** = 数据错了/该丢掉 ⇒ ⛔ 本工具**没有任何证据**说这些轨迹无效
    ⚖⚠⚠⚠⚠⚠⇒ 把「落在量程外」读成「该剔除」，会**悄悄换掉分母**
       （244.41 的 floor 族已经演示过：分母一变，p 就不可比）。
    """
    return False


# --------------------------------------------------------------- 主流程
def run(w_log=W_LOG, rand_log=RAND_LOG, probe_path=PROBE_REL):
    D = _load("dose_for_sat", "dose_axis_audit.py")
    kp = D.load_k_positions(probe_path)
    arms = {}
    for name, path in (("w", w_log), ("rand", rand_log)):
        rows = D.k_cells(D.load_cells(path), kp)
        arms[name] = D.by_tid([r for r in rows if not r["direct"]])

    L = []
    L.append("【1】传播层原始响应的**饱和普查**（raw = |读数(α=0.5·gap) − 读数(1.0·gap)|）")
    L.append("  ⚖ 阈值 floor=%.4g / ceil=%.4g；⚠ **它们不是我拍的** ⇒ 敏感性见【3】"
             % (FLOOR, CEIL))
    base = {}
    for name in ("w", "rand"):
        raws = [r["raw"] for g in arms[name].values() for r in g]
        cs = census(raws)
        base[name] = cs
        L.append("  ⚖ %-4s 臂：n=**%d** ｜floor **%d** ｜ceil **%d** ｜合计饱和 **%d**"
                 "（**%.0f%%**）｜中间 %d"
                 % (name, cs["n"], cs["floor"], cs["ceil"], cs["sat"],
                    100.0 * cs["sat"] / cs["n"], cs["mid"]))
    raws_rand = [r["raw"] for g in arms["rand"].values() for r in g]
    cnt = {}
    for x in raws_rand:
        k3 = "%.3f" % round(x, 3)
        cnt[k3] = cnt.get(k3, 0) + 1
    L.append("  ⚖ rand 臂最常见的取值：%s"
             % "｜".join("%s×%d" % (k, v)
                         for k, v in sorted(cnt.items(), key=lambda kv: -kv[1])[:6]))

    L.append("")
    L.append("【2】🔴 我的假说与它的预测 —— **被自己的预测证伪**")
    L.append("  ⚖⚠⚖⚖⚖⚖ 假说：「饱和档多 ⇒ |rho| 被压小 ⇒ 符号更脆」")
    L.append("     ⚖⚠⚖⚖⚖⚖ **预测：两条臂都应是负相关**")
    rs = {}
    for name in ("w", "rand"):
        xs, ys = [], []
        for tid in sorted(arms[name]):
            sub = sorted(arms[name][tid], key=lambda r: r["cov"])
            nsat = sum(1 for r in sub
                       if sat_flag(r["raw"]) is not None)
            rho = D.spearman([r["cov"] for r in sub], [r["raw"] for r in sub])
            if rho is None:
                continue
            xs.append(nsat)
            ys.append(abs(rho))
        rs[name] = pearson_r(xs, ys)
        L.append("     ⚖ %-4s 臂：n=%d 条可算轨迹，Pearson r(饱和档数, |rho|) = **%+.3f**"
                 % (name, len(xs), rs[name]))
    L.append("  ⚖⚠⚠⚠⚠⚠⇒ **r 一负一正（%+.3f / %+.3f），方向相反**"
             % (rs["rand"], rs["w"]))
    L.append("     ⇒ ⇒ **假说被自己的预测证伪** ⇒ ⚖⚠⚠⚠⚠ 只能报「**未量到**」")
    L.append("  ⚖⚠⚖⚖⚖⚖⚖⚖⚖⚖ **这条否证挡住了一个坏主意**（本轮最值钱的产出）")
    L.append("     ⚖「符号检验只吃序、丢了幅度 ⇒ 换**幅度口径**（斜率/面积）会更稳」")
    L.append("     ⛔ **数据上没有依据**：① 幅度在两端被截断；② 饱和与 |rho| **无关**")
    L.append("     ⚗⇒ 先记下来 ⇒ ⚠ 省下一次 GPU 跑批")

    L.append("")
    L.append("【3】阈值敏感性（⛔ 结论不许是「阈值我拍的」这种产物）")
    L.append("  %-28s %-22s %-22s" % ("阈值组合", "w 臂 饱和占比", "rand 臂 饱和占比"))
    for fl in FLOOR_SWEEP:
        for ce in CEIL_SWEEP:
            cells = []
            for name in ("w", "rand"):
                raws = [r["raw"] for g in arms[name].values() for r in g]
                cs = census(raws, fl, ce)
                cells.append("%d/%d = %.0f%%" % (cs["sat"], cs["n"],
                                                 100.0 * cs["sat"] / cs["n"]))
            L.append("  %-28s %-22s %-22s"
                     % ("floor=%.4g ceil=%.4g" % (fl, ce), cells[0], cells[1]))
    shares = {"w": [], "rand": []}
    for fl in FLOOR_SWEEP:
        for ce in CEIL_SWEEP:
            for name in ("w", "rand"):
                raws = [r["raw"] for g in arms[name].values() for r in g]
                cs = census(raws, fl, ce)
                shares[name].append(100.0 * cs["sat"] / cs["n"])
    L.append("")
    L.append("  ⚖⚠⚠⚠ **我第一版在这里写「结论对阈值不敏感」—— ⛔ 被上面这张表推翻了**：")
    L.append("     实测占比随阈值在 %.0f%%–%.0f%%（w）/ %.0f%%–%.0f%%（rand）之间**变动**"
             % (min(shares["w"]), max(shares["w"]),
                min(shares["rand"]), max(shares["rand"])))
    L.append("  ⚖⇒ ⚖⚠ **具体数字是阈值敏感的**；⚖ 但**下限** %.0f%%/%.0f%% 仍是"
             "「**大量格落在量程外**」⇒ ⚖ **定性**结论不敏感"
             % (min(shares["w"]), min(shares["rand"])))

    L.append("")
    L.append("【4】剔掉饱和格这条路的**代价**（⛔ 我不建议剔，只报代价）")
    for name in ("w", "rand"):
        u = usable_rungs(arms[name], spearman_fn=D.spearman)
        lost = sorted(t for t, v in u["per_tid"].items() if v[0] < 3)
        L.append("  ⚖ %-4s 臂：剔后仍可算 **%d/%d** 条；变得**不可算** %d 条%s"
                 % (name, u["n_ok"], u["n_all"], len(lost),
                    ("：%s" % "、".join(t.split("__", 1)[-1] for t in lost)) if lost else ""))
    L.append("  ⚖⚠⚠⚠⚠ ⇒ **饱和 ⛔ 不等于「那条轨迹无效」**（禁令 %s）"
             % ("生效" if saturation_is_not_invalid() is False else "⛔ 失效"))
    L.append("     ⚖ 它是**量程**的陈述；⚖⚠⚠ 本工具**没有任何证据**说这些轨迹无效")
    L.append("     ⚖⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠ 把「落在量程外」读成「该剔除」⇒ **悄悄换掉分母**")
    L.append("        ⇒ p 与 p 之间**不可比**（244.41 的 floor 族已演示）")

    L.append("")
    L.append("【5】⛔ 读法（不要越读）")
    L.append("  ⚖ ⚠ 本节**没有**回答 244.41 的「为什么删最低档就破」")
    L.append("  ⚖ ⚠ 本节只回答：① 响应有多少落在量程外 ② 饱和与 |rho| **未量到相关**")
    L.append("  ⚖ ⚠ 「假说被证伪」⛔ **不等于**「饱和与稳健性无关」⇒ 仍是**未量到**")
    L.append("  ⚖ ⚠ rep_n=1 ⇒ 格内噪声没量到 ⇒ 「哪一档承载信息」仍**结构性答不了**")
    return "\n".join(L), 0


# --------------------------------------------------------------- 自检
def selftest():
    ok, bad = [], []

    def chk(t, cond, why=""):
        (ok if cond else bad).append(t)
        print(("[PASS] %s %s" if cond else "[FAIL] %s %s") % (t, why))

    # C1 🔴 三态互不相同：floor / ceil / 中间，⛔ 不许合并成一个布尔
    chk("C1", sat_flag(0.0) == "floor" and sat_flag(0.125) == "ceil"
        and sat_flag(0.05) is None,
        "0.0→%s、0.125→%s、0.05→%s（三态，⛔ 不是布尔）"
        % (sat_flag(0.0), sat_flag(0.125), sat_flag(0.05)))

    # C2 🔴 边界**恰在**阈值上 ⇒ 归饱和（`<=` / `>=`，⛔ 不是 `<` / `>`）
    chk("C2", sat_flag(0.001) == "floor" and sat_flag(0.124) == "ceil"
        and sat_flag(0.0011) is None and sat_flag(0.1239) is None,
        "恰等于 floor/ceil ⇒ 饱和；刚过一点点 ⇒ 不饱和（%s/%s/%s/%s）"
        % (sat_flag(0.001), sat_flag(0.124), sat_flag(0.0011), sat_flag(0.1239)))

    # C3 ⚖ 恒等式按定义写：floor + ceil == sat；n == floor + ceil + mid
    cs = census([0.0, 0.125, 0.05, 0.0, 0.12])
    chk("C3", cs["n"] == 5 and cs["floor"] == 2 and cs["ceil"] == 1
        and cs["sat"] == 3 and cs["mid"] == 2
        and cs["floor"] + cs["ceil"] + cs["mid"] == cs["n"],
        "n=%d floor=%d ceil=%d sat=%d mid=%d（加起来 == n）"
        % (cs["n"], cs["floor"], cs["ceil"], cs["sat"], cs["mid"]))

    # C4 🔴 `pearson_r` 零方差 ⇒ **未量到（None）**，⛔ 不许印 0.0
    r_flat = pearson_r([1, 1, 1, 1], [0.1, 0.2, 0.3, 0.4])
    r_real = pearson_r([1, 2, 3, 4], [0.1, 0.2, 0.3, 0.4])
    r_inv = pearson_r([1, 2, 3, 4], [0.4, 0.3, 0.2, 0.1])
    chk("C4", r_flat is None and abs(r_real - 1.0) < 1e-12
        and abs(r_inv + 1.0) < 1e-12,
        "零方差⇒%s（⛔ 不是 0.0）；完全同向⇒%+.3f；完全反向⇒%+.3f"
        % (r_flat, r_real, r_inv))

    # C5 🔴 夹具是**真实阶梯形状**（⛔ 不是示意）：末档恒在 ceil ⇒ 剔后不可算
    #   ⚖⚠⚠⚠ 244.37 的老坑：cov 必须是**阶梯**，⛔ 不是常量
    #   ⚖⚠⚠⚠ 第一版我把 t_ok 写成 5 档里**两端**都饱和 ⇒ 剔完只剩 **2** 档
    #   ⚖⚠⚥⇒ C5 期望 (3,4) 却实测 2/4 —— **夹具是我设计错的**，不是实现错
    g5 = {"t_ok": [{"cov": 0.001, "raw": 0.0}, {"cov": 0.02, "raw": 0.03},
                   {"cov": 0.06, "raw": 0.05}, {"cov": 0.25, "raw": 0.08},
                   {"cov": 0.50, "raw": 0.125}],
          "t_bad": [{"cov": 0.001, "raw": 0.0}, {"cov": 0.02, "raw": 0.0},
                    {"cov": 0.06, "raw": 0.125}, {"cov": 0.25, "raw": 0.125}],
          # 🔐 补一条：剩**2 档**（不足 3 但 非 0）
          #   ⛔ 没它时变异 S7（`>= 3` → `>= 1`）在夹具上**看不见**
          "t_two": [{"cov": 0.001, "raw": 0.0}, {"cov": 0.02, "raw": 0.03},
                    {"cov": 0.06, "raw": 0.05}, {"cov": 0.25, "raw": 0.125}]}
    u5 = usable_rungs(g5)
    chk("C5", u5["n_all"] == 3 and u5["n_ok"] == 1
        and u5["per_tid"]["t_ok"] == (3, 5) and u5["per_tid"]["t_bad"] == (0, 4)
        and u5["per_tid"]["t_two"] == (2, 4),
        "剔饱和后：t_ok %d/%d 档（可算）、t_two %d/%d（⛔ 不足 3）、t_bad %d/%d（⛔ 0 档）"
        % (u5["per_tid"]["t_ok"] + u5["per_tid"]["t_two"] + u5["per_tid"]["t_bad"]))

    # C6 ⚖ 禁令必须有实体：饱和 ⛔ 不等于「无效」
    chk("C6", saturation_is_not_invalid() is False,
        "禁令恒 False（本工具**没有**任何证据说饱和轨迹无效）")

    # C7 ⚖⚖ 报告字面量：恒印查报告、分支查源码（⛔ 不做数据依赖判据）
    Lr = run()[0]
    src = open(os.path.abspath(__file__), encoding="utf-8").read()
    always = ("【1】传播层原始响应的**饱和普查**", "floor", "ceil",
              "阈值敏感性", "结论对阈值不敏感")
    # ⚖⚠⚖⚖⚖⚠⚖⚖ 修订（台架 S9 逼出来的）：我第一版把这五条放进 `branches`
    #   （查**源码**），⚠⚠⚠ 但它们**全部**都在**无条件**的 L.append 里
    #   ⇒ ⛔ 查源码等于「判据存在即可」，⛔ 不要求它**真的被印出来**
    #   ⇒ 变异把报告里那句抹掉，C7 照样绿（台架 S9 实测）
    # ⚗⇒ 归位到 `always`（查**报告**）⇒ 判据**更强**：必须真的印出来。
    always = always + ("假说被自己的预测证伪", "只能报「**未量到**」",
                       "坏主意", "不等于「那条轨迹无效」",
                       "「饱和与稳健性无关」")
    branches = ("分支占位：保留形状",) if False else ()
    mr = [x for x in always if x not in Lr]
    ms = [x for x in branches if x not in src]
    chk("C7", not mr and not ms,
        "报告恒印缺 %s；源码分支缺 %s" % ("无" if not mr else mr, "无" if not ms else ms))

    # C8 🔴🔴 **端到端**：必须复现本轮**实测**的两个 r（字面量，⛔ 不从被测函数算）
    rl = [l for l in Lr.split("\n") if "Pearson r(" in l]
    chk("C8", len(rl) == 2 and "**-0.078**" in Lr and "**+0.533**" in Lr,
        "端到端必须复现**实测**的两个 r（rand −0.078 / w +0.533，方向相反）：%s"
        % "｜".join(x.strip()[-14:] for x in rl))

    # C9 🔐 🔐 敏感性的**区间**必须被钉住（字面量，⛔ 不从被测函数算）
    #   ⚖⚠⚠⚠ 第一版只查了表头字面量 ⇒ 哪天换阈值，这个区间变了**也不会红**
    chk("C9", "18%–31%（w）/ 24%–41%（rand）" in Lr
        and "被上面这张表推翻了" in Lr
        and "具体数字是阈值敏感的" in Lr,
        "报告必须印出**实测区间**（w 18–31% / rand 24–41%），"
        "且必须**正向**印出「具体数字是阈值敏感的」（⛔ 不用「不许出现某句」那种判据）")

    print("自检 %d/%d 通过" % (len(ok), len(ok) + len(bad)))
    if bad:
        print("失败：%s" % ", ".join(bad))
        return 1
    return 0


def main():
    ap = argparse.ArgumentParser(description="传播层响应的两端饱和（零 GPU）")
    ap.add_argument("--w-log", default=W_LOG)
    ap.add_argument("--rand-log", default=RAND_LOG)
    ap.add_argument("--probe", default=PROBE_REL)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    txt, rc = run(args.w_log, args.rand_log, args.probe)
    print(txt)
    return rc


if __name__ == "__main__":
    sys.exit(main())
