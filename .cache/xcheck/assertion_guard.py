#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""§8.3 十条断言的引用守卫：**文档里印的每个数字都必须能从产物现算出来。**

## 为什么需要它

§8.3 那十条是本项目「通用可解释性理论」的骨架，也是**最容易被无声改坏**的部分 ——
它们是散落在长文里的散数，没有产物与之绑定。任何一次重算产物，只要没同步改文档，
理论就会开始印着**已经不成立**的数字，而没有任何判据会红。

## 方向是单向的

期望值**从产物现算**，不是写死在脚本里。然后要求文档逐字包含它。
⇒ 产物变了，文档被迫跟着变；反过来改文档数字，守卫立刻判红。

## 三条纪律（都是被本项目坑出来的）

1. **区间必须连聚合方式一起印。** 断言① 的 2.026%–2.245% 是「每层 4 方向均值」
   在 4 层之间的极值；16 个**逐点**值的区间是 1.989%–2.280%。
   只印数字不印聚合方式，读者按逐点去核必然核不上。⇒ G1/G2 两个判据分别盯这两个。
2. **p 值有两条，选错一条不会报错。** 产物里同时有 `fisher_p_plus_vs_zero`
   与 `fisher_p_plus_vs_minus`。文档表格标题写「vs 共享对照」，
   所以必须取 `p_plus_vs_zero`；取错了照样是个 p，只是比错了对象。⇒ G11 显式核对。
3. **断言不是判据。** 这份守卫只证明「文档与产物一致」，
   **不证明断言为真**。十条断言的对错由各自的实验负责。守卫红了先怀疑同步，不是怀疑结论。
"""
import io
import math
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# 变异台会把**副本**传进来。守卫绝不能靠「改完再还原真文档」来工作 ——
# 中途崩一次就等于把 §8.3 留在坏状态，而这个仓库没有别的校验会立刻发现。
DOC = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs/STEERING_INTERPRETABILITY_FRAMEWORK.md"
DATA = ROOT / "frontend/public/latent/data"


def load(name):
    return json.load(io.open(str(DATA / name), encoding="utf-8"))


def section_83(text):
    """只取 §8.3 那一节 —— 不许因为别处也印了同一个数就算过。"""
    a = text.index("### 8.3 十条可迁移的断言")
    b = text.index("### 8.4", a)
    return text[a:b]


MARKS = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩"]


def assertion_block(s83, mark):
    """只取 §8.3 里**某一条断言自己**的那一段。

    ⚠ 为什么要切块：判据若在整节里做子串匹配，就会被**别的断言**的同号数字喂饱。
      实测：⑦ 印「18/23 撞上限」，⑧ 也印「18/23 没跑完」——
      把 ⑦ 的那个改成 17/23，G4 仍然绿，因为它匹配到了 ⑧ 那一份。
      这是「判据每一项都成立，只是没有一项在问该问的问题」的又一例。
    ⇒ 每条判据只在自己的断言块里找数。
    """
    start = s83.index("**%s " % mark)
    nxt = [s83.find("**%s " % m, start + 1) for m in MARKS]
    nxt = [i for i in nxt if i > start]
    return s83[start:min(nxt)] if nxt else s83[start:]


results = []


def check(name, ok, detail):
    results.append({"name": name, "ok": bool(ok)})
    print("[%s] %s\n       %s" % ("PASS" if ok else "FAIL", name, detail))


def main():
    doc = io.open(str(DOC), encoding="utf-8").read()
    s83 = section_83(doc)
    a1, a7, a8, a10 = (assertion_block(s83, m) for m in ("①", "⑦", "⑧", "⑩"))
    lin = load("linearity_law.json")
    dirs = load("steer_directions.json")
    rep = load("steer_repetition.json")

    # ---------- 断言① 强度定律 ----------
    smax = lin["conclusions"]["safe_regime"]["strength_max"]
    rows20 = [r for r in lin["rows"] if abs(r["strength"] - smax) < 1e-9]
    # 组内均值（每层 4 个方向先平均）
    means = [sum(o["dev_pct"] for o in r["real"].values()) / len(r["real"])
             for r in rows20]
    # 逐点（16 个）
    pts = [o["dev_pct"] for r in rows20 for o in r["real"].values()]

    # ⚠ `dev_pct` 字段**已经是百分数**，不是分数。
    #   我第一版又 ×100，于是算出 202.6%–224.5%，判文档的 2.026%–2.245% 是错的。
    #   判红先怀疑判据 —— 查下来是这个。旁证：s 每翻一倍 ×4.0
    #   （0.1238 → 0.4991 → 1.9892），正是二次近似该有的形状。
    lo_m, hi_m = min(means), max(means)
    lo_p, hi_p = min(pts), max(pts)
    check("G1 断言① 印的区间必须等于**组内均值**的极值",
          ("%.3f%%–%.3f%%" % (lo_m, hi_m)) in a1,
          "组内均值 %.3f%%–%.3f%% → 期望文档含「%.3f%%–%.3f%%」"
          % (lo_m, hi_m, lo_m, hi_m))

    check("G2 断言① 必须**同时**印出逐点区间（否则读者会按 16 个点去核）",
          ("%.3f%%–%.3f%%" % (lo_p, hi_p)) in a1 and "逐点" in a1
          and "聚合" in a1,
          "逐点 %.3f%%–%.3f%%，且文档须出现「逐点」「聚合」两词"
          % (lo_p, hi_p))
    # 两个区间真的不同 —— 否则 G1/G2 是同一个判据的两次抄写
    check("G2b 组内均值区间与逐点区间必须真的不同（否则 G2 是装饰）",
          abs(hi_p - lo_p) > 1e-6 and abs(hi_m - lo_m) > 1e-6
          and abs((lo_p - lo_m)) > 1e-6 or abs((hi_p - hi_m)) > 1e-6,
          "均值 %.3f–%.3f  逐点 %.3f–%.3f  两者确有差异"
          % (lo_m, hi_m, lo_p, hi_p))

    sp = lin["conclusions"]["safe_regime"]["max_direction_spread_pp"]
    sp5 = lin["conclusions"]["beyond_safe_regime"]["max_direction_spread_pp"]
    check("G3 断言① 跨方向极差（层内）必须等于产物",
          ("%.2fpp" % sp) in a1 and ("%.2fpp" % sp5) in a1,
          "s<=0.2 → %.4fpp（印 %.2fpp）  s=0.5 → %.4fpp（印 %.2fpp）"
          % (sp, sp, sp5, sp5))

    # ---------- 断言⑦ / ⑧ 方向对照 ----------
    n = dirs["n_problems"]
    up, dn = dirs["per_direction"]["up"], dirs["per_direction"]["down"]
    check("G4 断言⑦ +v 撞上限必须是 %d/%d" % (up["arms_at_token_cap"], n),
          ("%d/%d" % (up["arms_at_token_cap"], n)) in a7,
          "产物 up.arms_at_token_cap=%d / n_problems=%d" % (up["arms_at_token_cap"], n))
    check("G5 断言⑦ −v 撞上限必须是 %d/%d" % (dn["arms_at_token_cap"], n),
          ("%d/%d" % (dn["arms_at_token_cap"], n)) in a7,
          "产物 down.arms_at_token_cap=%d / n=%d" % (dn["arms_at_token_cap"], n))
    check("G6 断言⑧ +v 闭合题数与未闭合题数",
          ("闭合的 %d 题" % up["n_complete"]) in a8
          and ("%d/%d" % (up["n_incomplete"], n)) in a8,
          "n_complete=%d  n_incomplete=%d / %d" % (up["n_complete"],
                                                   up["n_incomplete"], n))

    # ⚠ 真路径是 `blew_up.mcnemar_exact_p`，是**嵌套**的。
    #   我连着两版都按顶层找（先是 `mcnemar.exact_two_sided_p`，再是顶层同名键），
    #   两次都拿到 None、两次都判红 —— 同一处连续判错的根源都是
    #   **没打开产物看真实结构就写键名**。
    mc = dirs["blew_up"]["mcnemar_exact_p"]
    # ⚠ 指数是 floor(log10(p))，**不是** round(-log10(p))。
    #   我第一版写 round(-log10(6.1e-5)) = round(4.214) = 4 ⇒ 拼出「6.1×10⁻4」，
    #   与文档的「6.1×10⁻⁵」差一级。尾数 6.1 落在 [1,10) ⇒ 指数必须取 floor。
    #   （这与 §8.6 的 `next` 字段整体错位一级是同一类：指数/下标算错一级。）
    SUP = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")

    def sci_notation(x):
        e = math.floor(math.log10(abs(x)))
        m = x / (10.0 ** e)
        return ("%.1f×10" % m) + str(e).translate(SUP)

    sci = sci_notation(mc)
    check("G7 断言⑦ McNemar 精确 p（文档用「6.1×10⁻⁵」形式，不是 e 记法）",
          sci in a7,
          "产物 mcnemar_exact_p=%s → 期望文档含「%s」" % (mc, sci))

    ku = dirs["kl_contrast"]["mean_logit_kl_up"]
    kd = dirs["kl_contrast"]["mean_logit_kl_down"]
    # §8.3 只引了 −v 那一个（0.0686），用来支撑「KL 更大的方向反而更稳」。
    # 我第一版要求两个都印 ⇒ 判红，查下来是判据越权：**没印不等于印错**。
    check("G8 断言⑦ §8.3 引用的 KL 必须与产物一致，且方向不得反",
          ("%.4f" % kd) in a7 and kd > ku
          and ("%.4f" % ku) not in a7,
          "文档引 down=%.4f（产物 %.4f，且 up=%.4f 确实更小 ⇒ 方向对）"
          "；§8.3 未引 up，判据不要求它出现" % (kd, kd, ku))

    # ⚠ 长度比 2.21 / 1.20 与符号检验 p=0.093 属于 §4.16，不属于 §8.3。
    #   我第一版把它们列进本守卫，直接判红 —— 那是判据在替文档要求它没承诺的东西。
    #   ⇒ 这两个数归 §4.16 的 J5 管，不在这里管。

    # ---------- 断言⑩ 切点扫描 ----------
    by_w = {c["words"]: c for c in rep["cut_sweep"]}
    c800, c3200 = by_w[800], by_w[3200]
    check("G10 断言⑩ 800 词档：三臂同题入选数与 Fisher p（+v vs 共享对照）",
          ("%d/%d/%d" % (c800["zero"]["n_eligible"], c800["minus_v"]["n_eligible"],
                        c800["plus_v"]["n_eligible"])) in a10
          and ("%.4f" % c800["fisher_p_plus_vs_zero"])[1:] in a10
          and c800["same_problem_set"] is True,
          "入选 %d/%d/%d  p=%.6f（文档印 %.4f）  same_problem_set=%s"
          % (c800["zero"]["n_eligible"], c800["minus_v"]["n_eligible"],
             c800["plus_v"]["n_eligible"], c800["fisher_p_plus_vs_zero"],
             c800["fisher_p_plus_vs_zero"], c800["same_problem_set"]))

    check("G11 断言⑩ 3200 词档必须印「不可引用」且入选数与产物一致",
          ("%d/%d/%d" % (c3200["zero"]["n_eligible"], c3200["minus_v"]["n_eligible"],
                        c3200["plus_v"]["n_eligible"])) in a10
          and "不可引用" in a10 and c3200["same_problem_set"] is False,
          "入选 %d/%d/%d  same_problem_set=%s（必须 False，文档须写「不可引用」）"
          % (c3200["zero"]["n_eligible"], c3200["minus_v"]["n_eligible"],
             c3200["plus_v"]["n_eligible"], c3200["same_problem_set"]))

    # ⚠ 产物里同时有两个 p：vs_zero 与 vs_minus。表格标题写的是「vs 共享对照」，
    #   所以只准用 vs_zero。若文档印了 vs_minus 的数，这一条判红。
    pm3200 = c3200["fisher_p_plus_vs_minus"]
    check("G12 必须用 vs_共享对照 的 p，不能用 vs_−v 的（两者不等，印错不报错）",
          ("%.4f" % pm3200)[1:] not in a10.replace("**", ""),
          "vs_minus 的 %.4f 不许出现在 §8.3" % pm3200)

    smax_rep = max(rep["summary"], key=lambda s: s["rep_k_max"])
    zero_rep = [s for s in rep["summary"] if s["arm"] == "zero"][0]
    check("G13 断言⑩ 重复次数极值（+v %d vs 对照 %d）"
          % (smax_rep["rep_k_max"], zero_rep["rep_k_max"]),
          ("重复 %d 次" % smax_rep["rep_k_max"]) in a10
          and ("对照 %d 次" % zero_rep["rep_k_max"]) in a10,
          "plus_v rep_k_max=%d  zero rep_k_max=%d"
          % (smax_rep["rep_k_max"], zero_rep["rep_k_max"]))

    # ---------- 汇总：逐条失败必须进判定 ----------
    failed = [r for r in results if not r["ok"]]
    print("\nRESULT assertion_guard  %s  %d/%d 条通过"
          % ("RED" if failed else "GREEN", len(results) - len(failed), len(results)))
    for f in failed:
        print("   [FAIL] " + f["name"])
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
