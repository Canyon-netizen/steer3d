"""mixture_verdict.py 的本地先验（假数据，不碰真产物）。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mixture_verdict import M1_MAX_P, M2_MAX_RANGE, M3_MIN_GAIN, analyse  # noqa: E402

FAILS = []


def ok(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f" {detail}"))
    if not cond:
        FAILS.append(name)


print("\n=== 1. 阈值没被偷改 ===")
ok("M1_MAX_P = 0.01", M1_MAX_P == 0.01, M1_MAX_P)
ok("M2_MAX_RANGE = 0.15", M2_MAX_RANGE == 0.15, M2_MAX_RANGE)
ok("M3_MIN_GAIN = 0.10", M3_MIN_GAIN == 0.10, M3_MIN_GAIN)

print("\n=== 2. 纯混合：组内无形状、整体有形状 ⇒ 支持 ===")
# ⚠ 第一版在这里先调了一个 mkrows(...) 造「每档均匀」的夹具，
#    紧接着又用 rows = [] 整个覆盖掉它 —— 被覆盖的那次构造**没有任何作用**，
#    读代码的人会以为它参与了判定。⇒ 已删除。
rows = []
for q in range(4):
    nd = [60, 40, 30, 55][q]              # 构成：78/57/40/61 的形状
    nr = [25, 49, 68, 45][q]
    for grp, cnt, rate in ((True, nd, 0.03), (False, nr, 0.97)):
        n_ag = int(round(cnt * rate))
        for i in range(cnt):
            rows.append({"traj": f"t{(q * 10 + i) % 40:03d}",
                         "t": q * 100 + i, "aw": q * 100 + i + 0.5,
                         "dom": grp, "agree": i < n_ag,
                         "d": 2.0 if i < n_ag else -2.0, "dr": 0.1})
r = analyse(rows, "aw", "夹具")
print(f"  整体 {r['overall']['rates']} 极差 {r['overall']['range']:.3f}")
print(f"  7196 {r['dom']['rates']} 极差 {r['dom']['range']:.3f}")
print(f"  其余 {r['rest']['rates']} 极差 {r['rest']['range']:.3f}")
ok("M1 过（构成随分位变）", r["M1"]["pass"] is True, r["M1"])
ok("M2 过（组内无形状）", r["M2"]["pass"] is True, r["M2"])
ok("M3 过（整体>组内）", r["M3"]["pass"] is True, r["M3"])
ok("判定 = 支持", r["final"] == "支持：倒 U 主要来自混合", r["final"])

print("\n=== 3. 构成本身不变 ⇒ M1 不过 ⇒ 不支持 ===")
rows = []
for q in range(4):
    for grp, rate in ((True, 0.03), (False, 0.97)):
        for i in range(50):
            ag = i < int(round(50 * rate))
            rows.append({"traj": f"t{(q * 50 + i) % 40:03d}", "t": q * 50 + i,
                         "aw": q * 50 + i + 0.5, "dom": grp, "agree": ag,
                         "d": 2.0 if ag else -2.0, "dr": 0.1})
r = analyse(rows, "aw", "夹具2")
ok("M1 不过", r["M1"]["pass"] is False, r["M1"])
ok("M3 不过（没有混合可解释）", r["M3"]["pass"] is False, r["M3"])
ok("判定 = 不支持且点名 M1/M3",
   r["final"].startswith("不支持") and "M1" in r["final"], r["final"])

print("\n=== 4. 组内**有**形状 ⇒ M2 不过 ⇒ 不支持 ===")
rows = []
for q in range(4):
    nd, nr = [60, 40, 30, 55][q], [25, 49, 68, 45][q]
    for grp, cnt, rates in ((True, nd, [0.20, 0.60, 0.90, 0.30]),
                            (False, nr, [0.95, 0.80, 0.70, 0.98])):
        for i in range(cnt):
            rate = rates[q]
            ag = i < int(round(cnt * rate))
            rows.append({"traj": f"t{(q * 10 + i) % 40:03d}",
                         "t": q * 100 + i, "aw": q * 100 + i + 0.5,
                         "dom": grp, "agree": ag,
                         "d": 2.0 if ag else -2.0, "dr": 0.1})
r = analyse(rows, "aw", "夹具3")
ok("M2 不过（组内极差大）", r["M2"]["pass"] is False, r["M2"])
ok("判定 = 不支持且点名 M2", "M2" in r["final"], r["final"])

print("\n=== 5. 样本量守卫：某组某档不足 20 ⇒ 无法判定 ===")
rows = []
for q in range(4):
    for grp, cnt in ((True, 90), (False, 10)):   # rest 组每档仅 10
        rate = 0.03 if grp else 0.97
        for i in range(cnt):
            ag = i < int(round(cnt * rate))
            rows.append({"traj": f"t{(q * 10 + i) % 40:03d}",
                         "t": q * 100 + i, "aw": q * 100 + i + 0.5,
                         "dom": grp, "agree": ag,
                         "d": 2.0 if ag else -2.0, "dr": 0.1})
r = analyse(rows, "aw", "夹具4")
ok("guard_fail 非空", bool(r["guard_fail"]), r["guard_fail"])
ok("final = 无法判定", r["final"] == "无法判定", r["final"])

print("\n=== 6. CLI：位点数不符 ⇒ 拒；缺映射 ⇒ 拒 ===")
with tempfile.TemporaryDirectory() as tmp:
    rows = []
    mp = []
    for i in range(60):
        rows.append({"traj": "t0", "t": i, "mode": "think",
                     "w_dot_hhat": 0.3 + i / 1000, "w_dot_h": 1.0,
                     "h_norm": 1.0, "npz_layer_read": 19,
                     "inject_hs_index": 20, "n_tok": 8192,
                     "points": [{"rel": 1.0, "alpha": 1.0,
                                 "d_marker": 2.0 if i % 3 else -2.0,
                                 "d_rand": 0.1, "effective_dose": 0.0}]})
        mp.append({"traj": "t0", "t": i, "token_id": 7196 if i % 2 else 14190})
    P = os.path.join(tmp, "p.json")
    Mp = os.path.join(tmp, "m.json")
    O = os.path.join(tmp, "o.json")
    json.dump({"schema": "orthogonality_probe/1", "wU_marker": 0.18,
               "rows": rows}, open(P, "w", encoding="utf-8"))
    json.dump(mp, open(Mp, "w", encoding="utf-8"))

    def run(args):
        return subprocess.run(
            [sys.executable, os.path.join(HERE, "mixture_verdict.py")] + args,
            capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": os.path.join(HERE, "..", "pylibs")})

    rr = run(["--probe", P, "--map", Mp, "--out", O, "--expect-sites", "99"])
    ok("位点数不符 ⇒ 拒且不落盘",
       rr.returncode != 0 and not os.path.exists(O), rr.returncode)
    bad = mp[:-1]
    json.dump(bad, open(Mp, "w", encoding="utf-8"))
    rr = run(["--probe", P, "--map", Mp, "--out", O])
    ok("缺映射 ⇒ 拒", rr.returncode != 0 and "没有 token 映射" in rr.stderr,
       rr.stderr.strip()[-120:])

print()
if FAILS:
    print(f"✗ {len(FAILS)} 条不过：{FAILS}")
    sys.exit(1)
print("✓ mixture_verdict.py 全部先验通过")