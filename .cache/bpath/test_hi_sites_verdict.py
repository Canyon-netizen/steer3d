"""hi_sites_verdict.py 的本地先验（假数据，不碰任何真产物）。

判据写死在预登记 §28.3/§28.4，本文件只验**判定器实现**对不对：
方向、正交门��、打平的处理、样本不足报「不判」、以及各条拒绝路径。

跑法：PYTHONPATH=.cache/pylibs python3 .cache/bpath/test_hi_sites_verdict.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hi_sites_verdict as V   # noqa: E402

TMP = tempfile.mkdtemp(prefix="hiverdict_")


def run(rows, traj=None, expect=None):
    """造一个探针产物文件并跑 main()，返回写出的判决。"""
    J = {"schema": "orthogonality_probe/1", "wU_marker": 0.180199,
         "traj": sorted({r["traj"] for r in rows}), "rows": rows}
    inp = os.path.join(TMP, "probe.json")
    out = os.path.join(TMP, "v.json")
    json.dump(J, open(inp, "w", encoding="utf-8"), ensure_ascii=False)
    argv = sys.argv
    sys.argv = ["x", "--probe", inp, "--out", out]
    if expect is not None:
        sys.argv += ["--expect-sites", str(expect)]
    try:
        V.main()
    finally:
        sys.argv = argv
    return json.load(open(out, encoding="utf-8"))


def site(traj, t, w, d, dr=None, eff=None, ds=None):
    return {"traj": traj, "mode": "think", "t": t, "n_tok": 8192,
            "npz_layer_read": 19, "inject_hs_index": 20, "h_norm": 700.0,
            "w_dot_hhat": w,
            "w_dot_h": round(w * 700.0, 3),
            "points": [{"rel": rel, "alpha": rel * 231.978,
                        "d_marker": x, "d_rand": dr if dr is not None else 0.1,
                        "effective_dose": eff if eff is not None else 0.0}
                       for rel, x in zip((0.1, 0.3, 1.0),
                                         ds or (d / 3, d / 3, d))]}


def expect_raise(args, needle):
    try:
        run(*args)
    except SystemExit as e:
        assert needle in str(e), f"拒绝理由不含 {needle!r}: {e}"
        return
    raise AssertionError(f"本该拒绝但没拒绝：{needle}")


# ---- 用例 1：地板只取同一档（修订 26 F1 的修正确实生效）----
# 构造：低剂量档的对照臂很大，若混进来会把地板压低；同档则地板由 rel=1.0 决定。
rows = []
for i in range(30):
    w = 0.11 + 0.001 * i
    rows.append(site(f"t{i:02d}", i, w, d=-2.0, dr=1.0, eff=w))
v = run(rows, expect=30)
assert v["floor_same_slice"] == 1.0, v["floor_same_slice"]
assert v["floor_n"] == 30, f"同档只应有 30 个对照读数，实际 {v['floor_n']}"
assert "rel=1.0" in v["floor_note"], v["floor_note"]
print("用例1 PASS  地板只取 rel=1.0 那一档（floor_n == 位点数，不是 3×）")

# ---- 用例 2：G1 方向为反且显著 ⇒ 通过 ----
# ⚠ 方向：同号 = Δ 与 w·U 同号（wU_marker>0 ⇒ Δ>0）。「反」= 高对齐那组
# **同号更少**：低对齐组 Δ>0（多数同号），高对齐组 Δ<0（多数不同号）。
rows = [site(f"t{i:02d}", i, 0.11 + 0.01 * i,
             d=(3.0 if i < 15 else -3.0), dr=1.0, eff=0.11 + 0.01 * i)
        for i in range(30)]
v = run(rows, expect=30)
assert v["G1"]["direction"] == "反", v["G1"]
assert v["G1"]["pass"] is True, v["G1"]
print(f"用例2 PASS  G1 方向反、p={v['G1']['fisher_p']:.3g} ⇒ 通过")

# ---- 用例 3：G1 方向为正（= H 的预测）⇒ 不通过 ----
# 这一条必须在**方向为正**时报不过，哪怕 p 很小 ——
# 判据 §28.3 写的是「大 1/3 同号率**低于**小 1/3」，方向是判据的一部分。
rows = [site(f"t{i:02d}", i, 0.11 + 0.01 * i,
             d=(-3.0 if i < 15 else 3.0), dr=1.0, eff=0.11 + 0.01 * i)
        for i in range(30)]
v = run(rows, expect=30)
assert v["G1"]["direction"] == "正", v["G1"]
assert v["G1"]["pass"] is False, "方向为正却判通过 —— 方向没写死"
print("用例3 PASS  G1 方向为正即不通过（p 再小也不放过）")

# ---- 用例 4：G2 样本不足报「不判」，且不算「不同向」----
rows = [site("t0", i, 0.11 + 0.01 * i, d=3.0, dr=1.0) for i in range(5)]
v = run(rows, expect=5)
assert v["G2"]["n_judge"] == 0 and v["G2"]["n_skip"] == 1, v["G2"]
assert v["G2"]["verdict"] == "无法判定", v["G2"]["verdict"]
print("用例4 PASS  可判轨迹为 0 ⇒ 报「无法判定」，不报 FAIL")

# ---- 用例 5：G2 允许至多 1 条不同向，≥2 条即报不具一致性 ----
def two_track(n_bad):
    """n_bad 条轨迹内部方向为「正」（H 预测），其余为「反」。

    ⚠ 每条轨迹**内部**必须有梯度：低 w 位点与高 w 位点的 Δ 必须异号，
    否则 9 个位点同号 ⇒ 该轨迹的 hi/lo 两组计数相同 ⇒ 恒「打平」。
    """
    rows = []
    for j, tj in enumerate(["ta", "tb", "tc"]):
        bad = j >= (3 - n_bad)
        for i in range(9):
            w = 0.11 + 0.01 * i
            # 反 = 高 w 组 Δ<0（不同号）、低 w 组 Δ>0（多数同号）
            hi_neg = (i >= 5) if not bad else (i < 5)
            rows.append(site(tj, i, w, d=(-2.0 if hi_neg else 2.0), dr=1.0))
    return run(rows, expect=27)


v = two_track(1)
assert v["G2"]["n_diff"] == 1, v["G2"]
assert v["G2"]["verdict"] == "通过", v["G2"]["verdict"]
v = two_track(2)
assert v["G2"]["n_diff"] == 2, v["G2"]
assert v["G2"]["verdict"] == "不具轨迹间一致性", v["G2"]["verdict"]
print("用例5 PASS  G2：1 条不同向仍过，2 条即报不具轨迹间一致性")

# ---- 用例 6：G4 单调降按**逐档严格递减**计数 ----
rows = [site("t0", 0, 0.2, d=0, dr=0.1, ds=(3.0, 2.0, 1.0)),      # 严格降 ⇒ 计
        site("t0", 1, 0.2, d=0, dr=0.1, ds=(3.0, 2.0, 2.0)),      # 有持平 ⇒ 不计
        site("t0", 2, 0.2, d=0, dr=0.1, ds=(1.0, 2.0, 3.0))]      # 递增 ⇒ 不计
v = run(rows, expect=3)
assert v["G4"]["mono_down"] == 1, v["G4"]
print(f"用例6 PASS  G4 严格单调降计 1/3（持平不算）= {v['G4']['frac']:.2f}")

# ---- 用例 7：位点数与预登记不符 ⇒ 拒绝出结论 ----
expect_raise((rows, None, 999), "拒绝判定")
print("用例7 PASS  位点数对不上预登记即拒绝")

# ---- 用例 8：非数值读数 ⇒ 拒绝（别让 None 混进排序）----
bad = [site("t0", 0, 0.2, d=1.0, dr=0.1)]
bad[0]["points"][-1]["d_marker"] = None
expect_raise((bad, None, None), "非数值读数")
print("用例8 PASS  非数值读数即拒绝")

# ---- 用例 9：判据常量没被偷改 ----
assert (V.P_THRESHOLD, V.MIN_PER_TRACK, V.RHO_OLD, V.MONO_MIN,
        V.MAX_DIFF_TRACKS) == (0.01, 8, 0.4177, 0.20, 1), "判据常量被改动"
print("用例9 PASS  判据常量与 §28.3 一致")

print("\n全部先验通过：9 组用例 / 2 条拒绝路径")
