#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""r220_scope_delta_selftest —— 口径差对账脚本的**双向证伪**。

## 这条在守什么

`r220_scope_delta.py` 是修订 219 铺的那条路的**读数器**：P6 三选一
（`single` / `all` / 两套都跑报差）要靠它把口径差变成一个数。
⚠⚠⛔ 读数器本身报出一个**安静的错误数字**，比没有读数器更糟 ——
⚗ 因为它会把「没量到」印成「一致」。

所以本文件守三件最容易悄悄坏掉的事：

1. ⛔⛔⛔ **分母为 0 时不许印「一致」**。0 个比较点不是「一致」，是「没量到」。
2. ⛔⛔ **方向必须用符号构成报告**，不能只报 |Δ| ——
   ⚠ 「整体偏低」和「随机抖」在 |Δ| 上完全一样。
3. ⛔⛔ **一次对照只改一个变量**：除口径外还有字段不同 ⇒ 拒绝把差归给口径。

跑法：python3 r220_scope_delta_selftest.py
退出码：0 全部通过 / 1 有检查红
"""

import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), "mutbak", "r220_scope_delta.py")

CASES = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


def _load():
    import importlib.util
    spec = importlib.util.spec_from_file_location("r220", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


r220 = _load()


def _load_mutant(old, new):
    src = open(SRC, encoding="utf-8").read()
    assert old in src, "变异锚点不在源码里：%r" % (old,)
    mut = src.replace(old, new)
    assert mut != src, "变异没生效"
    mod = types.ModuleType("r220_mutant")
    mod.__dict__["__file__"] = "r220_mutant.py"
    exec(compile(mut, "r220_mutant.py", "exec"), mod.__dict__)
    return mod


# ⚠ 真产物里 label_coverage.n_traj = **60**（数据集轨迹数），不是 bench 的格数。
# ⚠⚠⁴ 第一版这里写成了 len(bench)，于是 E6 里 3 条 vs 10 条轨迹被伪装成
# ⚠⚠⁴ 「label_coverage 变了」⇒ 单变量守卫拒绝归因，读数器**判得对**、夹具**写错了**。
# ⚖ 这条记在这里，因为它是个容易再犯的错：把「覆盖面」和「读数」塞进同一个数。
N_TRAJ_DATASET = 60


# ⚠⚠⁴ 夹具必须**像真产物**：`r6_rerun.py` 顶层**总会**写 `dose_source`
# ⚖（`w_meta` / `retrained` / `FALLBACK_375` 三者之一）。
# ⚖⚗ 第一版夹具**不写**它 ⇒ C1「只有口径不同」其实还共享一个**没记的差别**，
# ⚖ 而按本项目的纪律「没记」**不**等于「一样」⇒ 那三个「应当放行」的用例
# ⚖ 当时是靠**漏字段**放行的，不是靠「确认过只有口径不同」。
# ⚖⇒ 给了真实默认值，⛔ 想测「缺字段」必须显式传 `dose=None`（E9④ 那样做）。
DOSE_FIXTURE = "w_meta"


def _payload(bench, scope="single", ok=True, extra=None, dose=DOSE_FIXTURE):
    p = {"bench": bench, "bench_v": {t: {"ok": ok} for t in bench},
         "pos_ok": ok, "device_validated": ok,
         "label_coverage": {"n_traj": N_TRAJ_DATASET, "n_missing": 0, "frac": 1.0}}
    if scope is not None:
        p["inject_scope"] = scope
    if dose is not None:
        p["dose_source"] = dose
    if extra:
        p.update(extra)
    return p


B1 = {"t1": {"w+@0.5": 0.5, "w+@1.0": 0.25, "w-@0.5": -0.25, "rand@0.5": 0.25},
      "t2": {"w+@0.5": 0.0, "w+@1.0": 0.75, "w-@0.5": -0.5, "rand@0.5": 0.0}}


# ===========================================================================
# A 组：分母守卫（本条最重要 —— 「没量到」不许印成「一致」）
# ===========================================================================


@case("A1 ⛔⛔⛔ bench 为空时判决必须是「没量到」，绝不能是「一致」")
def _():
    r = r220.analyze(_payload({}, scope="single"), _payload({}, scope="all"))
    assert r["bench"]["n_compared"] == 0, r["bench"]
    # ⚠ 判决串本身含「一致」二字（"不是「一致」"），所以只能判**开头**，
    # ⚠ 用 `"一致" not in verdict` 会把自己写的说明文字当成违规。
    assert r["verdict"].startswith("没量到"), r["verdict"]
    assert not r["verdict"].startswith("逐位相同"), \
        "⛔⛔⛔ 0 个比较点却印了「逐位相同」"


@case("A2 ⛔ 分母为 0 时 frac_exact 必须是 None，不是 1.0")
def _():
    r = r220.analyze(_payload({}, "single"), _payload({}, "all"))
    assert r["bench"]["frac_exact"] is None, \
        "⛔ frac_exact=%r ⇒ 0/0 被算成了 1.0" % (r["bench"]["frac_exact"],)


@case("A3 ⛔ 两边 bench 的键集不同 ⇒ 只在 A / 只在 B 必须被列出来")
def _():
    a = _payload({"t1": {"w+@0.5": 0.5}, "t9": {"w+@0.5": 1.0}}, "single")
    b = _payload({"t1": {"w+@0.5": 0.5}, "t8": {"w+@0.5": 1.0}}, "all")
    r = r220.analyze(a, b)
    assert r["bench"]["only_in_a"] == [("t9", "w+@0.5")], r["bench"]["only_in_a"]
    assert r["bench"]["only_in_b"] == [("t8", "w+@0.5")], r["bench"]["only_in_b"]


# ===========================================================================
# B 组：逐位相同 / 不相同
# ===========================================================================


@case("B1 两份完全相同 ⇒ 逐位相同，且符号检验无方向")
def _():
    r = r220.analyze(_payload(B1, "single"), _payload(B1, "single"))
    assert r["verdict"].startswith("逐位相同"), r["verdict"]
    assert r["bench"]["n_exact"] == r["bench"]["n_compared"] == 8
    assert r["bench"]["sign_z"] is None, "全为 0 却报出方向"


@case("B2 一格 +0.5 ⇒ 必须报不逐位相同，且符号为正")
def _():
    b2 = {"t1": dict(B1["t1"]), "t2": dict(B1["t2"])}
    b2["t1"]["w+@0.5"] = B1["t1"]["w+@0.5"] + 0.5
    r = r220.analyze(_payload(B1, "single"), _payload(b2, "all"))
    assert r["bench"]["n_exact"] == 7 and r["bench"]["n_compared"] == 8
    assert r["bench"]["n_pos"] == 1 and r["bench"]["n_neg"] == 0, r["bench"]


@case("B3 一格 -0.5 ⇒ 符号必须为负（不能被绝对值吃掉）")
def _():
    b2 = {"t1": dict(B1["t1"]), "t2": dict(B1["t2"])}
    b2["t2"]["w-@0.5"] = B1["t2"]["w-@0.5"] - 0.5
    r = r220.analyze(_payload(B1, "single"), _payload(b2, "all"))
    assert r["bench"]["n_neg"] == 1 and r["bench"]["n_pos"] == 0, r["bench"]
    assert r["bench"]["sign_z"] < 0, r["bench"]["sign_z"]


@case("B4 ⛔ 非数值格必须被跳过并计数，不许当成「相同」")
def _():
    a = _payload({"t1": {"w+@0.5": 0.5, "w+@1.0": None}}, "single")
    b = _payload({"t1": {"w+@0.5": 0.5, "w+@1.0": 1.0}}, "all")
    r = r220.analyze(a, b)
    assert r["bench"]["n_skipped"] == 1, r["bench"]
    assert r["bench"]["n_compared"] == 1, r["bench"]
    assert "跳过" in r["verdict"], r["verdict"]


# ===========================================================================
# C 组：一次对照只改一个变量
# ===========================================================================


@case("C1 只有口径不同 ⇒ 允许把差归给口径")
def _():
    a = _payload(B1, "single")
    b = _payload(B1, "all")
    r = r220.analyze(a, b)
    assert r["single_variable_ok"], r["single_variable_reasons"]
    assert r["scope_a"] == "single" and r["scope_b"] == "all"


@case("C2 ⛔⛔ 另有字段不同 ⇒ 必须拒绝归因")
def _():
    a = _payload(B1, "single", extra={"rows": [{"t": 1}]})
    b = _payload(B1, "all", extra={"rows": [{"t": 2}]})
    r = r220.analyze(a, b)
    assert not r["single_variable_ok"], "⛔ 两个变量都变了却仍然放行"
    assert any("rows" in x for x in r["single_variable_reasons"])


@case("C3 ⛔ 旧产物没有 inject_scope 字段 ⇒ 必须如实报「未记录」")
def _():
    a = _payload(B1, None)              # 改之前的 r6_rerun.py 就是这样
    b = _payload(B1, "all")
    r = r220.analyze(a, b)
    assert r["scope_a"] == "（未记录）", r["scope_a"]
    assert "未记录" in r220.report(r), "报告里看不到 A 没记口径这件事"


# ===========================================================================
# D 组：P9 判决翻转
# ===========================================================================


@case("D1 ok 翻转必须被数出来")
def _():
    a = _payload(B1, "single", ok=True)
    b = _payload(B1, "all", ok=False)
    r = r220.analyze(a, b)
    assert r["verdicts"]["n_flipped"] == 2, r["verdicts"]
    assert sorted(r["verdicts"]["flipped"]) == ["t1", "t2"]


@case("D2 幅度逐位相同但判决翻转是可能的 ⇒ 两者必须分别报")
def _():
    # ⚠ 这一组就是「幅度小 ≠ 判决不变」的最小反例：读数全同，ok 却不同。
    a = _payload(B1, "single", ok=True)
    b = dict(_payload(B1, "all", ok=False))
    r = r220.analyze(a, b)
    assert r["verdict"].startswith("逐位相同"), r["verdict"]
    assert r["verdicts"]["n_flipped"] == 2, "⛔ 判决翻转被幅度掩盖了"


# ===========================================================================
# E 组：报告与「涨 N%」纪律
# ===========================================================================


@case("E1 报告必须同时给出「中位数之比」与「逐格比值的中位数」")
def _():
    txt = r220.report(r220.analyze(_payload(B1, "single"), _payload(B1, "all")))
    assert "中位数之比" in txt and "逐格比值的中位数" in txt, txt[:400]
    assert "是**不同的量**" in txt, "⚠ 两者的区别必须在报告里点破，否则读者会混用"


@case("E2 ⛔ 报告必须带符号构成与符号检验")
def _():
    txt = r220.report(r220.analyze(_payload(B1, "single"), _payload(B1, "all")))
    assert "符号构成" in txt and "符号检验" in txt, txt[:400]
    assert "正 0 ｜ 负 0" in txt, "符号构成没被印出来"


@case("E3 ⛔⛔ 报告必须带覆盖面与「没验的范围」")
def _():
    txt = r220.report(r220.analyze(_payload(B1, "single"), _payload(B1, "all")))
    assert "【1】覆盖面" in txt, txt[:400]
    assert "⛔ 不含全量 rows" in txt, "没验的范围必须写在报告里"


# ===========================================================================
# F 组：变异台 —— 判据本身必须能红
# ===========================================================================


@case("F1 ⛔ 变异：去掉分母守卫 ⇒ A1 必须红（「0/0」会被印成「一致」）")
def _():
    mod = _load_mutant('if bench["n_compared"] == 0:', "if False:")
    r = mod.analyze(_payload({}, "single"), _payload({}, "all"))
    # 双向：原版必须说「没量到」
    ok = r220.analyze(_payload({}, "single"), _payload({}, "all"))
    assert ok["verdict"].startswith("没量到"), \
        "原版没把 0/0 判成「没量到」 ⇒ 台架无效"
    # 变异体必须把它印成「一致」⇒ 否则这个变异证明不了 A1 有分辨力
    assert r["verdict"].startswith("逐位相同"), \
        "变异体没让 0/0 变成「逐位相同」 ⇒ 台架无效"


@case("F2 ⛔ 变异：符号检验恒返回 None ⇒ E2 的方向段必须失效")
def _():
    mod = _load_mutant("    if n == 0:\n        return None, None",
                       "    return None, None")
    b2 = {"t1": dict(B1["t1"]), "t2": dict(B1["t2"])}
    b2["t1"]["w+@0.5"] = B1["t1"]["w+@0.5"] + 0.5
    r = mod.analyze(_payload(B1, "single"), _payload(b2, "all"))
    # ⛔ 有 1 正 0 负的差异，变异体却报「无非零差异」
    assert r["bench"]["n_pos"] == 1
    assert r["bench"]["sign_z"] is None, "变异没生效"
    txt = mod.report(r)
    assert "无非零差异" in txt, "⛔ 变异体应当把有方向的情况印成「无方向」"


@case("F3 ⛔ 变异：把 bench 也当出处字段排除 ⇒ C2 必须红")
def _():
    # ⚗⚠ 锚点随 PROVENANCE_KEYS 的改写一起换了（修订 239 把 dose_source 拿出去），
    # ⚖ 旧锚点 `'"device_validated", "dose_source",'` 已不存在。
    # ⚖ ⚗ **变异锚点必须随实现一起改** —— 锚点失效时报的是「锚点不在源码里」，
    # ⚖ ⛔ 而不是静默放过。
    mod = _load_mutant('"inject_scope", "pos_ok", "device_validated",',
                       '"inject_scope", "pos_ok", "device_validated", '
                       '"bench", "bench_v",')
    a = _payload(B1, "single", extra={"rows": [{"t": 1}]})
    b = _payload(B1, "all", extra={"rows": [{"t": 2}]})
    r = mod.analyze(a, b)
    assert not r["single_variable_ok"], "原版就应该拒绝归因"
    ok = _payload(B1, "single", extra={"rows": [{"t": 2}]})
    rb = mod.analyze(ok, _payload(B1, "all", extra={"rows": [{"t": 2}]}))
    assert rb["single_variable_ok"], \
        "变异体放行了 rows 不同的对照 ⇒ C2 的变异没生效"


@case("E4 ⛔⛔ 读数中心在 0（差值型）时，比值必须被判为「没有意义」")
def _():
    # ⚠ 这是真机上 p6 bench 的实际形状：读数是 logit **差**，中心就在 0。
    # ⚠⚠⁴ 若照印「中位数之比」，读者会拿一个拿 0 去除出来的数当结论用。
    z = {"t1": {"w+@0.5": 0.0, "w+@1.0": 0.0, "w-@0.5": -0.0}}
    r = r220.analyze(_payload(z, "single"), _payload(z, "all"))
    assert r["bench"]["level_is_above_noise"] is False, \
        "⛔ 中心在 0 的读数被判成「水平高于噪声」⇒ 守卫失效"
    txt = r220.report(r)
    assert "比值没有意义" in txt, txt[-600:]
    assert "别引用" in txt


@case("E5 水平明显高于噪声时，比值照常给出（不能把守卫写成一律不给）")
def _():
    z = {"t1": {"w+@0.5": 10.0, "w+@1.0": 20.0, "w-@0.5": -30.0}}
    r = r220.analyze(_payload(z, "single"), _payload(z, "all"))
    assert r["bench"]["level_is_above_noise"] is True, \
        "⛔ 水平远大于噪声，却被判成「没有意义」⇒ 守卫过宽"
    txt = r220.report(r)
    assert "中位数之比" in txt and "别引用" not in txt


@case("E6 ⛔ smoke_traj 是覆盖面出处：不同不该被当成「口径差」，也不该被静默")
def _():
    # ⚠ 两批读数比的是 3 条 vs 10 条轨迹 ⇒ 覆盖面不同。
    # ⚖ 它们**不是**读数差异（⇒ 不该让单变量守卫拒绝归因），
    # ⚖ 但**必须**被看见（⇒ 格数不同要报出来，不能悄悄只比交集）。
    a = _payload(B1, "single", extra={"smoke_traj": 3, "smoke_traj_arg": 3})
    big = {"t%d" % i: {"w+@0.5": 0.5, "w+@1.0": 0.25} for i in range(1, 11)}
    b = _payload(big, "all", extra={"smoke_traj": 10, "smoke_traj_arg": 10})
    r = r220.analyze(a, b)
    assert r["single_variable_ok"], "⛔ 覆盖面差异被误判成「不止一个变量变了」"
    assert r["bench"]["n_bench_rows"] == 2 and r["bench"]["n_compared"] == 4, \
        "⛔ 比较点数算错：交集应是 2 条 × 2 点 = 4"
    assert len(r["bench"]["only_in_b"]) == 16, \
        "⛔ 只在 B 的格数不对（8 条 × 2 点）"
    txt = r220.report(r)
    assert "比较点 4 个（2 条轨迹）" in txt, "⛔ 覆盖面没印出来"


@case("E7 ⛔⛔ 只在 B 出现的新格必须被看见，不能只比交集就宣布「逐位相同」")
def _():
    a = _payload(B1, "single")
    b = dict(_payload(B1, "single"))
    b["bench"] = dict(b["bench"])
    b["bench"]["t9"] = {"w+@0.5": 0.5, "w+@1.0": 0.25}
    r = r220.analyze(a, b)
    assert r["bench"]["n_exact"] == r["bench"]["n_compared"] == 8
    # ⚠⚠ 交集全同，但两边格数不同 ⇒ 「逐位相同」这句话必须带上「只在 B」这个事实
    assert r["bench"]["only_in_b"] == [("t9", "w+@0.5"), ("t9", "w+@1.0")], \
        r["bench"]["only_in_b"]
    txt = r220.report(r)
    assert "只在 B 2" in txt, txt[:400]


@case("E8 ⚠⚠ 符号检验必须是**精确**二项：n=4 全同向的 p 是 0.125，"
      "不是正态近似的 0.0455")
def _():
    import math
    z, p = r220._sign_test(0, 4)
    lb = 2.0 ** (1 - 4)
    assert abs(p - 0.125) < 1e-12, \
        "n=4 全同向的精确 p 应为 0.125，实得 %r" % p
    assert p >= lb, "p=%r 低于理论下界 %r —— 那是伪影" % (p, lb)
    # ⚖ 把正态近似也算出来，记住它有多离谱（这就是本条存在的理由）
    approx = math.erfc(abs(z) / math.sqrt(2.0))
    assert abs(approx - 0.0455) < 1e-3, approx
    assert approx < lb, \
        "本条的前提是「正态近似低于下界」；若哪天不成立请重写本条"
    # ⚖ 其它 n：全同向时 p 恒等于下界
    for n in (5, 8, 13):
        _, pn = r220._sign_test(n, 0)
        assert abs(pn - 2.0 ** (1 - n)) < 1e-15, (n, pn)
    assert r220._sign_test(0, 0) == (None, None)


@case("E9 ⚠⚠⚠⛔ 方向向量来源（dose_source）不同 ⇒ **不是一次对照**；"
      "且必须印在报告头上")
def _():
    # ⚖① 两边来源相同 ⇒ 正常放行
    a = _payload(B1, "single", extra={"dose_source": "w_meta"})
    b = _payload(B1, "all", extra={"dose_source": "w_meta"})
    r = r220.analyze(a, b)
    assert r["dose_state"] == "same", r["dose_state"]
    assert r["dose_same"] is True, r["dose_same"]
    assert r["single_variable_ok"], r["single_variable_reasons"]
    # ⚖⚠② **FALLBACK_375 vs w_meta** ⇒ 必须拒绝归因
    # ⚖    （⚠⚠ 这是「仪器静默回落」那条路径，最危险）
    b2 = _payload(B1, "all", extra={"dose_source": "FALLBACK_375"})
    r2 = r220.analyze(a, b2)
    assert r2["dose_state"] == "different", r2["dose_state"]
    assert r2["dose_same"] is False, r2["dose_same"]
    assert not r2["single_variable_ok"], \
        "⛔⛔ 兜底向量 vs 正常向量竟然判成「一次对照」"
    txt = r220.report(r2)
    assert "不是同一个方向向量" in txt, txt[:500]
    assert "方向向量来源不同" in txt, txt[:800]
    # ⚖⚠ ③ 报告头**必须**印出两边的来源（以前一个字都没印）
    assert "dose_source" in txt, txt[:400]
    assert "FALLBACK_375" in txt, txt[:400]
    # ⚖⚠⚠ ④ **两边都没记** ⇒ 「没量到」**不许**判成「一样」（修订 239.1 实测）
    # ⚖⚗ 第一版实现这里是**红的**：`None == None` 成立 ⇒ `dose_same=True`、
    # ⚖   `reasons=[]`、守卫照样签发「✅ 除口径外逐字段相同 ⇒ 差可以归给口径」。
    # ⚖⚠ 而本条的注释**一直**写着「缺字段时也要说，不能默默当『一样』」
    # ⚖ ⚗ 实现做的恰好是它禁止的事 —— 注释对、代码错，才是最难发现的一种。
    a3 = _payload(B1, "single", dose=None)
    b3 = _payload(B1, "all", dose=None)
    r3 = r220.analyze(a3, b3)
    assert r3["dose_state"] == "unknown", r3["dose_state"]
    assert r3["dose_same"] is False, \
        "⛔⛔ 两边都没记 dose_source 却判成「同一个向量」"
    assert not r3["single_variable_ok"], \
        "⛔⛔ 无法确认两臂同向量，却仍然放行归因"
    assert any("未记录" in x for x in r3["single_variable_reasons"]), \
        r3["single_variable_reasons"]
    assert r3["dose_a"] == "（未记录）", r3["dose_a"]
    txt3 = r220.report(r3)
    assert "（未记录）" in txt3, txt3[:400]
    assert "无法确认" in txt3, txt3[:400]
    # ⚖⚠ ⑤ **只缺一边** ⇒ 同样不许放行（比「都缺」更容易被当成「一样」）
    for tag, (pa_, pb_) in [("A缺", (a3, _payload(B1, "all"))),
                           ("B缺", (_payload(B1, "single"), b3))]:
        rr = r220.analyze(pa_, pb_)
        assert rr["dose_state"] == "unknown", (tag, rr["dose_state"])
        assert not rr["single_variable_ok"], \
            "⛔ 只缺一边（%s）却放行了归因" % tag


@case("F4 ⚠⚠⚠⛔ 变异：复原旧行为（跳过 + 无检查 + 报告不印，**三处**）⇒ E9 必须红")
def _():
    # ⚠⚠⚠ 变异**不是假想**：dose_source 真的**一直在** PROVENANCE_KEYS 里被跳过，
    # ⚖ 而 report **一个字都没印过**它 ⇒ 兜底向量 vs 正常向量会静默通过。
    # ⚖⚠⚠ **三处**，不是两处 —— 这正是第一版 F4 红着的原因。
    # ⚖   ① PROVENANCE_KEYS 把它当「出处」跳过
    # ⚖   ② check_single_variable 里那条专门检查
    # ⚖   ③ report 头那一行 `_dose_head(a, r)`
    # ⚖ ⚗ 只复原 ①② 时：`single_variable_ok` 确实变回 True（第一道断言过），
    # ⚖⚠⚠ 但报告**仍然印着**「两边不是同一个方向向量」（第二道断言红）。
    # ⚖⚖⇒ 那一版变异体是**半复原的 chimeric**：既不是旧代码也不是新代码，
    # ⚖ ⚗ 谁也说不清它到底在测哪个分支 —— 这是台架自己的缺陷，不是被测代码的。
    # ⚖ ⇒ 与 F3 同源：**变异必须真的把被测行为破坏掉**。
    # ⚖⚖ 另外①②合起来只是「第二层防护」：`dose_source` 移出 PROVENANCE_KEYS
    # ⚖ 之后，通用字段循环**也会**比它 ⇒ 只改一处会被另一层挡住。
    src = open(SRC, encoding="utf-8").read()
    m1 = src.replace('"inject_scope", "pos_ok", "device_validated",\n'
                     '                   "smoke_traj", "smoke_traj_arg")',
                     '"inject_scope", "pos_ok", "device_validated", "dose_source",\n'
                     '                   "smoke_traj", "smoke_traj_arg")')
    m2 = m1.replace("    if dst != DOSE_STATE_SAME:", "    if False:")
    m3 = m2.replace("    _dose_head(a, r)",
                    "    pass  # 变异：复原旧行为 —— report 根本不印 dose_source")
    assert m1 != src, "第一处（PROVENANCE_KEYS）没生效"
    assert m2 != m1, "第二处（专门检查）没生效"
    assert m3 != m2, "第三处（报告头）没生效"
    mod = types.ModuleType("r220_mutant")
    mod.__dict__["__file__"] = "r220_mutant.py"
    exec(compile(m3, "r220_mutant.py", "exec"), mod.__dict__)
    a = _payload(B1, "single", extra={"dose_source": "w_meta"})
    b = _payload(B1, "all", extra={"dose_source": "FALLBACK_375"})
    r = mod.analyze(a, b)
    assert r["single_variable_ok"], "变异没生效：旧行为没复原"
    txt = mod.report(r)
    assert "不是同一个方向向量" not in txt, \
        "变异体不该再报「不是同一个方向向量」：%s" % txt[:400]
    assert "dose_source" not in txt, \
        "变异体不该再印 dose_source 那一行：%s" % txt[:400]
    # ⚖⚠ 变异体也必须复原「两边没记 ⇒ 放行」那条旧行为（第一版红的一半）
    r3 = mod.analyze(_payload(B1, "single", dose=None),
                     _payload(B1, "all", dose=None))
    assert r3["single_variable_ok"], \
        "变异没生效：旧实现把「两边没记」判成「同向量」并放行"


@case("F5 ⚠⚠⛔ 变异：**只**拿掉报告头那一行 ⇒ 守卫仍对，但 E9③/④ 的显示断言必须红")
def _():
    # ⚖⚠ 为什么要有这一条：F4 是**三处一起**改的 ⇒ E9②（守卫）和 E9③④（显示）
    # ⚖ **同时**变红。⚖⇒ 报告头哪天被改坏时，**分不清**是哪条断言抓住的。
    # ⚖ ⇒ 补一条**只动显示**的单点变异，把两类断言的牙**分开**验。
    # ⚖ ⚗ 单点变异如果也把守卫改坏 ⇒ 这条测的就不是显示，而是另一条路径。
    mod = _load_mutant("    _dose_head(a, r)",
                       "    pass  # 变异：只拿掉显示，守卫保持不动")
    a = _payload(B1, "single", extra={"dose_source": "w_meta"})
    b = _payload(B1, "all", extra={"dose_source": "FALLBACK_375"})
    r = mod.analyze(a, b)
    # ⚖⚗ **守卫必须仍然工作** —— 这是本条的前提，先证明夹具造出了目标形状
    assert not r["single_variable_ok"], \
        "变异把守卫也改坏了 ⇒ 本条测到的不是显示，而是另一条路径"
    txt = mod.report(r)
    # ⚖⚠⚠ **只量报告头那一块**（两条 `=` 横线之间）。
    # ⚖⚗ 第一版量的是**整篇** `"dose_source" not in txt` ⇒ 红。
    # ⚖ ⚗ 查下来是**断言量错了东西，不是变异没生效**：
    # ⚖   报告头那行确实没了（实测第 3 行已是收尾横线），
    # ⚖⚠ 但【0】段回显 reasons 时**合法地**又印了一次 `dose_source`。
    # ⚖ ⇒ 判据必须量**它声称在量的那一处**；量得太宽会把对的实现判成错的。
    sep = "=" * 78
    head = txt.split(sep)[1] if txt.count(sep) >= 2 else ""
    assert "dose_source" not in head, "报告头那一行还在：变异没生效"
    assert "不是同一个方向向量" not in head, \
        "报告头那一行还在：变异没生效"
    # ⚖ 而守卫的措辞仍在文本里 ⇒ 说明**只有显示**被拿掉（单点变异成立）
    assert "方向向量来源不同" in txt, \
        "⛔ 守卫的措辞也没了 ⇒ 这不是单点变异，是把整条检查删了"


def main():
    npass = nfail = 0
    for name, fn in CASES:
        try:
            fn()
        except AssertionError as exc:
            nfail += 1
            print("  %-4s ⛔ FAIL  %s" % (name, exc), flush=True)
        except Exception as exc:                        # noqa: BLE001
            nfail += 1
            print("  %-4s ⛔ ERROR %s: %r" % (name, type(exc).__name__, exc),
                  flush=True)
        else:
            npass += 1
            print("  %-4s ✅ %s" % (name, name), flush=True)
    print()
    print("RESULT r220_scope_delta_selftest  %s  %d/%d"
          % ("OK" if nfail == 0 else "FAIL", npass, npass + nfail))
    return 0 if nfail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
