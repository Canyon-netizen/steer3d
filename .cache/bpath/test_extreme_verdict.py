"""extreme_verdict.py 的本地先验（假数据，不碰真产物）。

判据写死在预登记 §30.3.1，本文件只验**实现**对不对。

跑法：PYTHONPATH=.cache/pylibs python3 .cache/bpath/test_extreme_verdict.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extreme_verdict as V   # noqa: E402

TMP = tempfile.mkdtemp(prefix="extverdict_")
SGN = True          # wU_marker > 0：Δ>0 记为同号


def site(traj, t, aw, d, dr):
    return {"traj": traj, "mode": "think", "t": t, "n_tok": 8192,
            "npz_layer_read": 19, "inject_hs_index": 20, "h_norm": 700.0,
            "w_dot_hhat": aw if aw > 0 else -aw, "w_dot_h": 0.0,
            "points": [{"rel": rel, "alpha": rel * 231.978, "d_marker": x,
                        "d_rand": dr, "effective_dose": 0.0}
                       for rel, x in ((0.1, d / 3), (0.3, d / 3), (1.0, d))]}


def run(rows, expect=None, all_sites=None):
    J = {"schema": "orthogonality_probe/1", "wU_marker": 0.180199,
         "traj": sorted({r["traj"] for r in rows}), "rows": rows}
    ip, op = os.path.join(TMP, "p.json"), os.path.join(TMP, "v.json")
    json.dump(J, open(ip, "w", encoding="utf-8"), ensure_ascii=False)
    argv = sys.argv
    sys.argv = ["x", "--probe", ip, "--out", op]
    if expect is not None:
        sys.argv += ["--expect-sites", str(expect)]
    if all_sites is not None:
        ap = os.path.join(TMP, "all.json")
        json.dump({"rows": all_sites}, open(ap, "w", encoding="utf-8"))
        sys.argv += ["--all-sites", ap]
    try:
        V.main()
    finally:
        sys.argv = argv
    return json.load(open(op, encoding="utf-8"))


def expect_raise(rows, needle):
    try:
        run(rows, expect=999)
    except SystemExit as e:
        assert needle in str(e), f"拒绝理由不含 {needle!r}: {e}"
        return
    raise AssertionError(f"本该拒绝但没拒绝：{needle}")


# ---- 用例 1：全负 ⇒ E1/E2 通过 ----
rows = []
for j in range(3):
    for i in range(12):
        rows.append(site(f"t{j}", i, 0.40 + 0.001 * i, d=-2.0, dr=0.5))
v = run(rows, expect=36)
assert v["E1"]["frac"] == 0.0 and v["E1"]["pass"] is True, v["E1"]
assert v["E2"]["n_judge"] == 3 and v["E2"]["pass"] is True, v["E2"]
print(f"用例1 PASS  全负 ⇒ E1 同号率 0.0、p={v['E1']['fisher_two_sided_p']:.3g}；E2 三条全过")

# ---- 用例 2：全正 ⇒ E1 不过（方向反了就该不过）----
rows = [site("t0", i, 0.40 + 0.001 * i, d=2.0, dr=0.5) for i in range(36)]
v = run(rows, expect=36)
assert v["E1"]["frac"] == 1.0 and v["E1"]["pass"] is False, v["E1"]
print("用例2 PASS  全正 ⇒ E1 不过（方向写死）")

# ---- 用例 3：同号率够低但**样本量不够** ⇒ 报「无法判定」，不报 FAIL ----
rows = [site("t0", i, 0.40 + 0.001 * i, d=-2.0, dr=0.5) for i in range(12)]
v = run(rows, expect=12)
assert v["final"] == "无法判定", v
assert "E1" not in v, "样本量不足时不该给出 E1 判决"
print(f"用例3 PASS  12 个位点 ⇒ 报「{v['final']}」且不出 E1 判决")

# ---- 用例 4：E2 允许至多 1 条例外 ----
def two(n_bad):
    rows = []
    for j in range(3):
        for i in range(12):
            d = 2.0 if j >= (3 - n_bad) else -2.0      # 前 n_bad 条整条为正
            rows.append(site(f"t{j}", i, 0.40 + 0.001 * i, d=d, dr=0.5))
    return run(rows, expect=36)


assert two(1)["E2"]["pass"] is True, "1 条例外应仍通过"
assert two(2)["E2"]["pass"] is False, "2 条例外应不通过"
assert two(2)["E2"]["verdict"] == "不具轨迹间一致性"
print("用例4 PASS  E2：1 条例外仍过，2 条即不具轨迹间一致性")

# ---- 用例 4b（修订 33 §33.7）：n_judge 太小 ⇒ 判据无牙齿 ----
# ⚠ 夹具必须**先过 MIN_TOTAL=20**，否则会先被总样本量守卫拦下、
#    根本走不到 E2（第一版就踩了这个：9 个位点 ⇒ 产物里压根没有 E2 键）。
# 构造：1 条 12 位点的主轨迹 + 8 条各 1 位点的填充轨迹 = 20 个超地板位点，
# 但只有主轨迹够「≥8 位点」⇒ n_judge = 1。
def solo_track(d_main):
    rows = [site("solo", i, 0.40, d=d_main, dr=0.5) for i in range(12)]
    rows += [site(f"f{j}", 0, 0.35, d=-2.0, dr=0.5) for j in range(8)]
    return rows


for d, tag in ((-2.0, "主轨迹全负"), (2.0, "主轨迹全正")):
    v = run(solo_track(d), expect=20)
    assert v["E2"]["n_judge"] == 1, f"{tag}：{v['E2']['n_judge']}"
    assert v["E2"]["teeth_ok"] is False, f"{tag}：n_judge=1 应标记无牙齿"
    assert v["E2"]["verdict"] == "无法判定", \
        f"{tag}：n_judge=1 必须报无法判定，实得 {v['E2']['verdict']}"
    assert v["E2"]["pass"] is False, f"{tag}：n_judge=1 不得报 PASS"
# 关键：两种**相反**的数据得到**同一个**「无法判定」⇒ 判据没在区分它们，
# 这正是「无牙齿」的证据。若这里任何一侧报 PASS，就是回归。
print("用例4b PASS  n_judge=1 时主轨迹全负/全正**都**判「无法判定」⇒ 无牙齿，不可判")

# 反向对照 1：n_judge=2 同样无牙齿（2 条都全正 ⇒ 2 条例外 > 1，才 FAIL）
two = [site("s0", i, 0.40, d=-2.0, dr=0.5) for i in range(8)] + \
      [site("s1", i, 0.40, d=2.0, dr=0.5) for i in range(8)] + \
      [site(f"g{j}", 0, 0.35, d=-2.0, dr=0.5) for j in range(4)]
v2 = run(two, expect=20)
assert v2["E2"]["n_judge"] == 2, v2["E2"]["n_judge"]
assert v2["E2"]["teeth_ok"] is False, "n_judge=2 仍应标记无牙齿"
assert v2["E2"]["verdict"] == "无法判定", v2["E2"]["verdict"]

# 反向对照 2：n_judge=3 时同一构造**能**判出 2 条例外 ⇒ 守卫没有过度拦截
three = two + [site("s2", i, 0.40, d=2.0, dr=0.5) for i in range(8)]
v3 = run(three, expect=28)
assert v3["E2"]["n_judge"] == 3, v3["E2"]["n_judge"]
assert v3["E2"]["teeth_ok"] is True, "n_judge=3 应标记有牙齿"
assert v3["E2"]["pass"] is False and v3["E2"]["verdict"] == "不具轨迹间一致性", v3["E2"]
print("用例4c PASS  n_judge=2 判无法判定、n_judge=3 能判「不具轨迹间一致性」⇒ 守卫不过度拦截")

# ---- 用例 5：E3′ 两条子判据各自能不过 ----
# 基准：全体 36 个位点，对照臂 |Δrand| 恒为 0.1 ⇒ p95 = 0.1
rest = [site("r0", i, 0.20, d=-2.0, dr=0.1) for i in range(36)]
# 5a：极对齐带比基准安静 ⇒ (a)(b) 都过
ext_ok = [site("e0", i, 0.40, d=-2.0, dr=0.05) for i in range(36)]
v = run(ext_ok, expect=36, all_sites=rest)
assert v["E3"]["a_ok"] is True and v["E3"]["noisy_ratio_ok"] is True
assert v["E3"]["pass"] is True, v["E3"]
# 5b：极对齐带的对照臂**更吵** ⇒ (b) 不过（这才是 E3′ 有牙齿的地方）
ext_noisy = [site("e0", i, 0.40, d=-2.0, dr=0.9) for i in range(36)]
v2 = run(ext_noisy, expect=36, all_sites=rest)
assert v2["E3"]["noisy_ratio_ok"] is False, \
    "极对齐带 |Δrand| p95 高出基准 1.5 倍以上却判过 ⇒ E3′ 没有牙齿"
assert v2["E3"]["pass"] is False, v2["E3"]
print("用例5 PASS  E3′：安静带过、噪声带（p95 超 1.5 倍）不过")

# ---- 用例 6：地板同档（§28.3）+ 全部落在地板下 ⇒ 「无法判定」----
# 构造：对照臂 |Δrand| 恒为 3.0 ⇒ 地板 3.0；测试臂 |Δ| 只有 0.5 ⇒ 全部在地板下
rows = [site("t0", i, 0.40, d=0.5, dr=3.0) for i in range(36)]
v = run(rows, expect=36)
assert v["floor_same_slice"] == 3.0, v["floor_same_slice"]
assert v["n_above"] == 0, v["n_above"]
assert v["final"] == "无法判定", v["final"]
assert "E1" not in v, "全在地板下时不该出 E1 判决"
print("用例6 PASS  地板只取同档（=3.0）；全在地板下 ⇒ 「无法判定」且不出判决")

# ---- 用例 7：拒绝路径 ----
expect_raise(rows, "拒绝判定")           # 位点数对不上
bad = [site("t0", 0, 0.4, d=-2.0, dr=0.5)]
bad[0]["points"][-1]["d_marker"] = None
try:
    run(bad, expect=1)
    raise AssertionError("本该拒绝但没拒绝")
except SystemExit as e:
    assert "非数值读数" in str(e), e
print("用例7 PASS  位点数不符 / 非数值读数 均拒绝")

# ---- 用例 8：判据常量没被偷改（修订 31 改了 E3，见下）----
assert (V.E1_MAX_AGREE, V.E1_MAX_P, V.E2_MIN_PER_TRACK, V.E2_MIN_NEG,
        V.E2_MAX_EXC, V.MIN_TOTAL) == (0.25, 0.05, 8, 0.75, 1, 20), "判据常量被改动"
# ⚠ E3 的两个常量在修订 31 §31.2 被改过（原本几乎恒过）：
#   E3_MAX_CTRL 0.25 → 0.05（名义率），并新增 E3_NOISY_RATIO = 1.5。
#   这里断言的就是**修订后**的值 —— 改动本身有预登记依据，不是偷改。
assert (V.E3_MAX_CTRL, V.E3_NOISY_RATIO) == (0.05, 1.5), "E3 常量与修订 31 不符"
print("用例8 PASS  判据常量与 §30.3.1 / §31.2 一致")

print("\n全部先验通过：8 组用例 / 2 条拒绝路径")
