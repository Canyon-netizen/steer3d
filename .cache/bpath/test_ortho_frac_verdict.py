"""ortho_frac_verdict.py 的本地先验（假数据，不碰任何真产物）。

每个用例对应预登记 §24.1 的一个分支或一条守卫。
跑法：PYTHONPATH=.cache/pylibs python3 .cache/bpath/test_ortho_frac_verdict.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ortho_frac_verdict as V   # noqa: E402

TMP = tempfile.mkdtemp(prefix="fracverdict_")
PREREG = V.PREREG

# 一份可用的预登记：§24.2 存在且有 blockquote
assert os.path.exists(PREREG), PREREG
REAL_242 = V.read_sec242(PREREG)
assert "未能在有足够高对齐位点的样本上检验" in REAL_242, REAL_242[:200]

# 一份缺 §24.2 的预登记（守卫 5）
BAD_PREREG = os.path.join(TMP, "no_242.md")
open(BAD_PREREG, "w", encoding="utf-8").write("# x\n## 24.1\n占位\n")


def rows(fracs):
    return [{"traj": f"aime__aime25__p{i:02d}__think", "n_hi": 0,
             "n_sites": 100, "frac": f} for i, f in enumerate(fracs)]


def expect_raise(fn, needle):
    try:
        fn()
    except SystemExit as e:
        msg = str(e)
        assert needle in msg, f"拒绝理由不含 {needle!r}: {msg}"
        return msg
    raise AssertionError(f"本该拒绝但没拒绝：{needle}")


# ---- 用例 1：M1 过 + M2 不过（修订 24 的预期落点）----
f = [0.40, 0.30, 0.22, 0.18, 0.12, 0.11, 0.10, 0.09, 0.08, 0.07] * 5 + [0.02] * 8
assert len(f) == V.N_EXPECT, len(f)
v = V.verdict(rows(f), PREREG)
assert v["M1"]["pass"] is True, v["M1"]
assert v["M2"]["pass"] is False and v["M2"]["rank"] > 3, v["M2"]
assert v["M3"]["action"] == "revise_rev23_again", v["M3"]
assert v["M3"]["new_wording_sec242"] == REAL_242
assert abs(v["median_std"] - v["median_upper_mid"]) < 1e-12   # 全同值时两者相同
print("用例1 PASS  M1过/M2不过 -> 再更正一次")

# ---- 用例 2：M1 过 + M2 过（p01 独占前 3）----
# 恰好两条高于 p01 ⇒ 名次 3 =「前 3 条之内」的边界
f = [0.50, 0.40] + [0.10] * (V.N_EXPECT - 2)
v = V.verdict(rows(f), PREREG)
assert v["M1"]["pass"] is True and v["M2"]["pass"] is True, (v["M1"], v["M2"])
assert v["M2"]["rank"] == 3, v["M2"]                     # 边界：恰好第 3 也算过
assert v["M3"]["new_wording_sec242"] is not None
print("用例2 PASS  M1过/M2过（p01 恰排第3，边界）")

# ---- 用例 3：M1 不过 => 维持修订 23，且不输出措辞 ----
f = [0.30, 0.20, 0.10] + [0.01] * (V.N_EXPECT - 3)     # 中位 0.01 < 0.05
v = V.verdict(rows(f), PREREG)
assert v["M1"]["pass"] is False, v["M1"]
assert v["M3"]["action"] == "keep_rev23", v["M3"]
assert v["M3"]["new_wording_sec242"] is None, "不过时不得吐措辞"
print("用例3 PASS  M1不过 -> 维持修订23")

# ---- 用例 4：轨迹数不对 => 拒绝（守卫 1）----
expect_raise(lambda: V.verdict(rows([0.2] * 57), PREREG), "拒绝出结论")
expect_raise(lambda: V.verdict(rows([0.2] * 60), PREREG), "拒绝出结论")
print("用例4 PASS  轨迹数 57/60 均被拒")

# ---- 用例 5：两种中位数定义判定相反 => 拒绝挑一个（守卫 2）----
# 升序后下标 28 = 0.001、下标 29 = 0.06 ⇒ 标准中位 (0.001+0.06)/2 = 0.0305 不过，
# 上中位 fr[29] = 0.06 过 ⇒ 两个定义给出相反判定，必须拒绝而不是挑一个。
f = [0.001] * 29 + [0.06] + [0.9] * 28
assert len(f) == V.N_EXPECT, len(f)
import statistics as _st
_s = sorted(f)
assert (_st.median(_s) < V.M1_MIN_MEDIAN) and (_s[len(_s) // 2] >= V.M1_MIN_MEDIAN), \
    "反例构造错了：两个定义没真正打架"
expect_raise(lambda: V.verdict(rows(f), PREREG), "拒绝挑一个出结论")
print("用例5 PASS  两种中位数相反 -> 拒绝")

# ---- 用例 6：§24.2 缺失 => 拒绝（守卫 3）----
expect_raise(lambda: V.read_sec242(BAD_PREREG), "找不到 §24.2")
open(BAD_PREREG, "w", encoding="utf-8").write("# x\n## 24.2\n没有引文\n")
expect_raise(lambda: V.read_sec242(BAD_PREREG), "没有 blockquote 措辞")
print("用例6 PASS  §24.2 缺/无引文 -> 拒绝")

# ---- 用例 7：判据常量没被偷改（守卫 4）----
assert (V.N_EXPECT, V.M1_MIN_MEDIAN, V.M2_MAX_RANK, V.P01_FRAC) \
    == (58, 0.05, 3, 0.1577), "判据常量被改动"
print("用例7 PASS  判据常量与预登记一致")

# ---- 用例 8：p01 常量转写错误的敏感性（守卫 5）----
# 预登记字面值 0.1577 vs 实测 21/133 = 0.157894736...，差在小数第 4 位。
# 只要没有轨迹落在 (0.1577, 0.157895] 这个窗口里，名次就与实测值一致。
assert abs(V.P01_FRAC_TRUE - V.P01_FRAC) < 1e-3, "两值本应同在第 3 位"
assert V.P01_FRAC != V.P01_FRAC_TRUE, "字面值与实测值竟完全相同？"
# 8a：窗口里没有轨迹 => 正常出结论，且标记判定不变
f = [0.50, 0.40] + [0.10] * (V.N_EXPECT - 2)
v = V.verdict(rows(f), PREREG)
assert v["M2"]["rank"] == v["M2"]["rank_under_true_value"] == 3, v["M2"]
assert v["M2"]["verdict_invariant"] is True, v["M2"]
# 8b：窗口里恰好有 3 条（0.1578）⇒ 按字面值名次 4 不过、按实测值名次 1 过，
# 转写错误会翻转结论，必须拒绝出结论而不是替判据挑一个
f = [0.1578] * 3 + [0.10] * (V.N_EXPECT - 3)
assert 0.1577 < 0.1578 <= V.P01_FRAC_TRUE, "窗口构造错了"
_r_lit = 1 + sum(1 for v in f if v > V.P01_FRAC)
_r_true = 1 + sum(1 for v in f if v > V.P01_FRAC_TRUE)
assert (_r_lit <= V.M2_MAX_RANK) != (_r_true <= V.M2_MAX_RANK), \
    f"窗口构造没造成翻转：{_r_lit} vs {_r_true}"
expect_raise(lambda: V.verdict(rows(f), PREREG), "必须单独立修订后才出结论")
print("用例8 PASS  p01 常量敏感性：无轨迹落窗内则不变，有则拒绝出结论")

print("\n全部先验通过：8 组用例 / 7 条拒绝路径")