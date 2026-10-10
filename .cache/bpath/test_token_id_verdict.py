"""token_id_verdict.py 的本地先验（假数据，不碰真产物）。

跑法：PYTHONPATH=.cache/pylibs python3 .cache/bpath/test_token_id_verdict.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FAILS = []


def ok(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f" {detail}"))
    if not cond:
        FAILS.append(name)


def make(tmp, per_traj_dom, per_traj_rest, n_traj, dom_neg, rest_neg,
         dom_id=7196, dup_map=False, drop_map=False):
    """造一对假产物：probe（179 行结构）+ map。"""
    rows, mp = [], []
    for j in range(n_traj):
        traj = f"t{j:02d}"
        # ⚠ 每组**各自**从 0 数 —— 第一版用同一个 k，于是 rest 组的
        #    「前 k 个为负」拿已经 ≥6 的 k 去比，「全负」静默变成「全正」。
        for k in range(per_traj_dom):
            neg = False if dom_neg is None else (k < dom_neg)
            d = -2.0 if neg else 2.0
            rows.append({"traj": traj, "t": 100 + k, "mode": "think",
                         "w_dot_hhat": 0.3, "w_dot_h": 200.0,
                         "h_norm": 700.0, "npz_layer_read": 19,
                         "inject_hs_index": 20, "n_tok": 8192,
                         "points": [{"rel": 1.0, "alpha": 23.2,
                                     "d_marker": d, "d_rand": 0.1,
                                     "effective_dose": 0.004}]})
            mp.append({"traj": traj, "t": 100 + k, "token_id": dom_id})
        for k in range(per_traj_rest):
            neg = (k % 2 == 1) if rest_neg is None else (k < rest_neg)
            d = -2.0 if neg else 2.0
            rows.append({"traj": traj, "t": 1000 + k, "mode": "think",
                         "w_dot_hhat": 0.3, "w_dot_h": 200.0,
                         "h_norm": 700.0, "npz_layer_read": 19,
                         "inject_hs_index": 20, "n_tok": 8192,
                         "points": [{"rel": 1.0, "alpha": 23.2,
                                     "d_marker": d, "d_rand": 0.1,
                                     "effective_dose": 0.004}]})
            mp.append({"traj": traj, "t": 1000 + k, "token_id": 10061})
    if drop_map:
        mp = mp[:-1]
    if dup_map:
        mp = mp + [dict(mp[0])]
    P = os.path.join(tmp, "probe.json")
    M = os.path.join(tmp, "map.json")
    O = os.path.join(tmp, "out.json")
    with open(P, "w", encoding="utf-8") as f:
        json.dump({"schema": "orthogonality_probe/1", "wU_marker": 0.18,
                   "rows": rows}, f)
    with open(M, "w", encoding="utf-8") as f:
        json.dump(mp, f, ensure_ascii=False)
    return P, M, O


def run(P, M, O):
    r = subprocess.run(
        [sys.executable, os.path.join(HERE, "token_id_verdict.py"),
         "--probe", P, "--map", M, "--out", O],
        capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": os.path.join(
            HERE, "..", "pylibs")})
    out = json.load(open(O, encoding="utf-8")) if os.path.exists(O) else None
    return r, out


print("\n=== 1. 自校验真的跑了，而且不匹配会拒绝 ===")
with tempfile.TemporaryDirectory() as tmp:
    P, M, O = make(tmp, 6, 3, 10, 3, 3)     # 60/30 位点、10 条共享轨迹
    r, v = run(P, M, O)
    ok("自校验在 stdout 里报通过", "自校验通过" in r.stdout, r.stdout[-200:])
    ok("退出码 0", r.returncode == 0, r.stderr[-300:])
    ok("产物带 selfcheck 字段",
       v and "selfcheck" in v and "已跑" in v["selfcheck"], v)

print("\n=== 2. 强关联 ⇒ T1 通过 ===")
with tempfile.TemporaryDirectory() as tmp:
    P, M, O = make(tmp, 6, 3, 10, 0, 3)     # 7196 全正、其余全负
    r, v = run(P, M, O)
    ok("T1 pass", v["T1"]["pass"] is True, v["T1"])
    ok("T2 pass", v["T2"]["pass"] is True, v["T2"])
    ok("判词是「两组符号分布不同」",
       v["final"] == "两组符号分布不同", v["final"])
    ok("负向占比 0.000 vs 1.000",
       v["dom_neg_frac"] == 0.0 and v["rest_neg_frac"] == 1.0,
       (v["dom_neg_frac"], v["rest_neg_frac"]))
    ok("作用域警示在产物里", "不可分离" in v.get("scope_warning", ""),
       v.get("scope_warning", "")[:60])

print("\n=== 3. 零关联 ⇒ T1 不通过 ===")
# ⚠ 第一版用 `dom_neg=None, rest_neg=None`（交替），结果 dom 负向 3/6 = 0.5、
#    rest 1/3 = 0.333 —— **那不是零关联**，CMH 当然判出差异。
#    真正的零关联是**两组比例完全一样**：都 3/6。
with tempfile.TemporaryDirectory() as tmp:
    P, M, O = make(tmp, 6, 6, 10, 3, 3)     # 两组各 3/6 为负
    r, v = run(P, M, O)
    ok("两组比例真的相等",
       v["dom_neg_frac"] == v["rest_neg_frac"] == 0.5,
       (v["dom_neg_frac"], v["rest_neg_frac"]))
    ok("T1 不通过", v["T1"]["pass"] is False, v["T1"])
    ok("判词是「无差异」", v["final"] == "两组符号分布无差异", v["final"])

print("\n=== 3b. 差异存在但只在轨迹之间（分层应当把它消掉）===")
# 每条轨迹内两组比例**完全一样**，但轨迹之间差异很大
# ⇒ 不分层会显著，分层后应当不显著 —— 这正是选 CMH 的理由。
with tempfile.TemporaryDirectory() as tmp:
    P, M, O = make(tmp, 6, 6, 10, None, None)
    # 手工把 dom 组改成：前 5 条全正、后 5 条全负（rest 两组都 3/6）
    import json as _j
    pr = _j.load(open(P, encoding="utf-8"))
    for rrow in pr["rows"]:
        if rrow["t"] < 1000:                 # dom 组
            traj = rrow["traj"]
            rrow["points"][0]["d_marker"] = (-2.0 if traj >= "t05" else 2.0)
    _j.dump(pr, open(P, "w", encoding="utf-8"))
    r, v = run(P, M, O)
    orr, p3 = v["T3"]["or"], v["T3"]["p_two_sided"]
    ok("不分层 Fisher 看不出差异（被轨迹混淆抹平）",
       p3 > 0.05, (orr, p3))
    ok("分层 CMH 仍判无差异（同向）",
       v["T1"]["pass"] is False, v["T1"])

print("\n=== 4. T2 守卫：共享轨迹不足 ⇒ 无法判定，不报 PASS ===")
with tempfile.TemporaryDirectory() as tmp:
    P, M, O = make(tmp, 6, 3, 5, 0, 3)      # 只有 5 条共享轨迹 < 8
    r, v = run(P, M, O)
    ok("final = 无法判定", v["final"] == "无法判定", v.get("final"))
    ok("T2 pass = False", v["T2"]["pass"] is False, v["T2"])
    ok("说清了缺哪一项", "共享轨迹" in v["why"], v.get("why"))
    ok("T2 不过时**不出** T1 判决", "T1" not in v, list(v))
    ok("T2 不过时**不出** T3 对照", "T3" not in v, list(v))

print("\n=== 5. T2 守卫：其余组太小 ⇒ 无法判定 ===")
with tempfile.TemporaryDirectory() as tmp:
    P, M, O = make(tmp, 1, 2, 30, 0, 2)     # 其余组 60 >=20，但共享 30
    r, v = run(P, M, O)
    # 这个用例其余组够大，共享轨迹 30 条 ⇒ 应该能判；改成测位点不足：
with tempfile.TemporaryDirectory() as tmp:
    P, M, O = make(tmp, 6, 0, 10, 0, None)   # 其余组 0 个
    r, v = run(P, M, O)
    ok("其余组为 0 ⇒ 无法判定", v["final"] == "无法判定", v.get("final"))
    ok("且是被守卫拦下的，不是崩了", r.returncode == 0, r.stderr[-200:])

print("\n=== 6. 映射守卫 ===")
with tempfile.TemporaryDirectory() as tmp:
    P, M, O = make(tmp, 6, 3, 10, 0, 3, dup_map=True)
    r, v = run(P, M, O)
    ok("重复 (traj,t) 被拒", r.returncode != 0 and "重复" in r.stderr,
       r.stderr.strip()[-120:])
    ok("被拒时不落盘", not os.path.exists(O))
with tempfile.TemporaryDirectory() as tmp:
    P, M, O = make(tmp, 6, 3, 10, 0, 3, drop_map=True)
    r, v = run(P, M, O)
    ok("缺映射被拒", r.returncode != 0 and "没有 token 映射" in r.stderr,
       r.stderr.strip()[-120:])

print("\n=== 7. 阈值没被偷改 ===")
sys.path.insert(0, HERE)
import token_id_verdict as T  # noqa: E402
ok("T1_MAX_P = 0.01", T.T1_MAX_P == 0.01, T.T1_MAX_P)
ok("MIN_DOM = 50", T.MIN_DOM == 50, T.MIN_DOM)
ok("MIN_REST = 20", T.MIN_REST == 20, T.MIN_REST)
ok("MIN_STRATA = 8", T.MIN_STRATA == 8, T.MIN_STRATA)
ok("DOM = 7196", T.DOM == 7196, T.DOM)

print()
if FAILS:
    print(f"✗ {len(FAILS)} 条不过：{FAILS}")
    sys.exit(1)
print("✓ token_id_verdict.py 全部先验通过")
