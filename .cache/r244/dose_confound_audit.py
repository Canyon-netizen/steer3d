#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dose_confound_audit.py —— 那个 k/n 符号判决是不是**被剂量轴混淆**了（零 GPU）

🔴🔴 **本工具问什么**
  账本的判决是「逐轨迹取 `up_mono_meas` **多数**」。可 244.47 说：
  **R 再大也不改变那个 p**，且能答问题的是**幅度**口径。
  ⚖⚠⚠⚠ 但在走幅度之前必须先问一件更基本的事：
  **那些「格」之间到底是不是同一个东西？**

⚖⚠⚠⚖⚖⚠ **实测结论（本工具算出来的，不是推的）**

  那 137 格里 —— `inject_scope=k` 的 109 格是**注入位点数扫描**，
  位点数从 **1 一直到 4655**；外加 `scope=single` 14 格与 `scope=all` 14 格。
  ⚖⚠⚠⚠ **它们⛔ 不是同一条件下的重复测量，而是不同剂量。**

  ⇒ 逐轨迹的「多数为真」= **跨不同剂量的多数**
  ⇒ **符号翻转与剂量效应在 w 臂上完全混淆** ⇒ ⛔ 在固定剂量之前，
     「12/14 是不是噪声」**原理上不可分辨**。

⚖⚠ **w 臂上剂量效应是实测到的（Spearman +0.622）**：

      位点分档        格数   d 中位     为正
      ≤ n/4           87    +0.0301    53/87   ← 接近抛硬币
      n/4 – n/2       11    +0.1679    10/11
      n/2 – 3n/4       8    +0.9521     8/8
      > 3n/4           3    +1.2495     3/3

  ⚖⇒ 那个 12/14 的大部分**来自高位点数那几档**；最低档 53/87 与抛硬币无异。
⚖ **rand 臂没有剂量趋势**（Spearman −0.038）⇒ 它的 6/14 **不是**剂量驱动的。

⚠⚠⚠ **本节的限制（写在这里以免被当成全绿）**
  · 分档用的 `n` 是**该臂位点数最大值**的代理，⛔ 不是逐格的真实 n_eff
    （真实值在 `n_eff_map.tsv`，本工具⛔ 没读它）⇒ 分档边界是粗的。
  · 只用了每臂**一个**结果文件；跨文件一致性由「多数计数必须复现账本的
    12/14 / 6/14」这条判据把关。
  · `inject_scope` 的三类（single / k / all）**混在一起**参与多数，
    ⛔ 而它们注入的量根本不同。

⚠⚠⚠ 本工具⛔ **不发批**、⛔ 不改探针、⛔ 不写数据文件。
⚖⚠⚠⚖ 每条判据都必须**能红**：变异台改的是喂进来的**数据形状**。
"""

import argparse
import ast
import io
import json
import math
import os
import statistics as _st
import sys

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else "."
# ⚖ 两个**已入库**的结果文件（.cache/ 被 ignore ⇒ 只作默认，不入库）
DEFAULT_FILES = {"w": ".cache/r244/_an.txt", "rand": ".cache/r244/_ra.txt"}
# ⚖⚠ 账本 244.43 记的计数：**判据必须复现它**，否则说明读的不是那一批
LEDGER_COUNT = {"w": 12, "rand": 6}
N_TRAJ = 14


class HardFail(Exception):
    pass


# --------------------------------------------------------------- 小工具
def load_jsonl(path):
    """⚖ 逐行读 JSON。⚖⚠⚠⚠ 缺失/坏行必须**报错**，⛔ 不许静默跳过 ——
    静默跳过会让「读到了 137 条」看起来像「全部都在」。"""
    out, bad = [], 0
    for i, line in enumerate(io.open(path, encoding="utf-8", errors="replace"), 1):
        t = line.strip()
        if not t.startswith("{"):
            continue
        try:
            out.append(json.loads(t))
        except Exception:
            bad += 1
    if bad:
        raise HardFail("文件 %s 有 %d 行 JSON 解析失败 ⇒ ⛔ 拒读（不许跳过后当全量）"
                       % (path, bad))
    if not out:
        raise HardFail("文件 %s 一条记录都没有 ⇒ ⛔ 拒读" % path)
    return out


def rank(v):
    s = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and v[s[j + 1]] == v[s[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1
        for k in range(i, j + 1):
            r[s[k]] = avg
        i = j + 1
    return r


def spearman(xs, ys):
    """⚖ Spearman 秩相关。⚖⚠⚠⚠ **必须逐条秩**（并列取平均秩），
    ⛔ 不许用 numpy 的默认名次（并列会给不同名次 ⇒ 静默错一个值）。"""
    if len(xs) != len(ys) or len(xs) < 3:
        raise HardFail("Spearman 需要成对且 n≥3（得到 %d,%d）" % (len(xs), len(ys)))
    rx, ry = rank(xs), rank(ys)
    n = len(rx)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx)
                    * sum((b - my) ** 2 for b in ry))
    return num / den if den else float("nan")


def d_of(rec):
    """⚖ 一格的 lo→hi 实测差。⚖⚠⚠⚠ 缺 `p9_lo_meas` 必须**拒读**，
    ⛔ 不许当成 0（那是「没量到」被渲染成 0 的老坑）。"""
    lo, hi = rec.get("p9_lo_meas"), rec.get("p9_hi_meas")
    if lo is None or hi is None:
        raise HardFail("记录 %r 缺 p9_lo_meas/p9_hi_meas ⇒ **未量到**，⛔ 不许当 0"
                       % (rec.get("tid"),))
    return float(hi) - float(lo)


def majority_count(recs):
    """⚖ 账本口径：逐轨迹取 `d > 0` 的多数（平票算 False ⇒ 不算真）。"""
    g = {}
    for r in recs:
        g.setdefault(r.get("tid"), []).append(d_of(r) > 0)
    return sum(1 for v in g.values() if sum(v) * 2 > len(v)), len(g)


# --------------------------------------------------------------- 判据
def audit(arm, path):
    L = ["【臂】%s ｜ 文件 %s" % (arm, path)]
    recs = load_jsonl(path)
    meas = [r for r in recs if r.get("p9_lo_meas") is not None]
    L.append("  ⚖ 记录 %d 条 ｜ 有实测读数的 %d 条" % (len(recs), len(meas)))

    ok = True
    # C1 必须复现账本的逐轨迹多数计数
    k, n_traj = majority_count(recs)
    want = LEDGER_COUNT.get(arm)
    good = (want is not None and k == want and n_traj == N_TRAJ)
    L.append("  C1 逐轨迹「多数为真」= %d/%d（账本记 %s）⇒ %s"
             % (k, n_traj, want, "✅ 复现" if good else "⛔ 没复现 ⇒ 读的不是那一批"))
    ok &= good

    # C2 格的构成：必须是**混合剂量**，否则「混淆」这条判据恒红
    ks = [r for r in meas if r["inject_scope"] == "k" and r.get("inject_n_sites")]
    scopes = {}
    for r in meas:
        scopes[r["inject_scope"]] = scopes.get(r["inject_scope"], 0) + 1
    L.append("  C2 inject_scope 分布 %s ｜ scope=k 里位点数 %d..%d（%d 格）"
             % (scopes, min(r["inject_n_sites"] for r in ks),
                max(r["inject_n_sites"] for r in ks), len(ks)))
    mixed = (len(scopes) > 1 and len({r["inject_n_sites"] for r in ks}) > 1)
    L.append("     ⇒ %s" % ("✅ 剂量与 scope 都是混合的 ⇒ 跨格多数**不是**同条件多数"
                             if mixed else "⛔ 剂量是齐的 ⇒ 这批不能支持「混淆」这条结论"))
    ok &= mixed

    # C3 剂量相关性
    ns = [float(r["inject_n_sites"]) for r in ks]
    dd = [d_of(r) for r in ks]
    rho = spearman(ns, dd)
    L.append("  C3 d 与位点数的 Spearman = %+.3f（%d 格）" % (rho, len(ks)))

    # C4 分档表（四档都必须印出来，且中位数单调与否要**报出来**）
    hi = max(ns)
    bands = [("位点<=n/4", [r for r in ks if r["inject_n_sites"] <= hi / 4]),
             ("n/4..n/2", [r for r in ks if hi / 4 < r["inject_n_sites"] <= hi / 2]),
             ("n/2..3n/4", [r for r in ks if hi / 2 < r["inject_n_sites"] <= 3 * hi / 4]),
             ("位点>3n/4", [r for r in ks if r["inject_n_sites"] > 3 * hi / 4])]
    L.append("  C4 按位点数分档（n 用**该臂最大值**代理，⚠ 边界是粗的）")
    meds = []
    for lab, sub in bands:
        if not sub:
            L.append("     %-11s 0 格" % lab)
            continue
        v = [d_of(r) for r in sub]
        meds.append(_st.median(v))
        L.append("     %-11s %3d 格  d 中位 %+.4f  为正 %2d/%d"
                 % (lab, len(v), meds[-1], sum(1 for x in v if x > 0), len(v)))
    mono = all(meds[i] <= meds[i + 1] for i in range(len(meds) - 1))
    L.append("     ⇒ 各档中位%s单调递增 ⇒ %s"
             % ("" if mono else "**不**", "✅ 剂量效应实测存在" if mono
                else "⚠ 不单调 ⇒ 该臂看不出剂量效应（≠「剂量不存在」）"))

    # C5 结论
    L.append("")
    if good and mixed and abs(rho) > 0.3:
        L.append("  ⚖⚠⚠⚖ **结论**：逐轨迹的「多数」是**跨不同注入位点数**的多数")
        L.append("     ⇒ 符号翻转与剂量效应**混淆** ⇒ ⛔ 在固定/分层剂量之前，")
        L.append("     「%d/%d 是不是噪声」**原理上不可分辨**" % (k, n_traj))
    else:
        L.append("  ⚠ 本臂**不支持**「剂量混淆」这条结论（复现=%s，混合=%s，rho=%+.3f）"
                 % (good, mixed, rho))
    L.append("")
    L.append("【⛔】本工具没验的：真实 n_eff（未读 n_eff_map.tsv）、"
             "single/all 与 k 三类的**跨类**可比性、逐文件一致性（只读了一个文件）")
    return L, (0 if ok else 1)


# --------------------------------------------------------------- 自检
def selftest(files=None):
    ok, bad = [], []

    def chk(t, cond, why=""):
        (ok if cond else bad).append(t)
        print(("[PASS] %s %s" if cond else "[FAIL] %s %s") % (t, why))

    # 合成数据：构造一个**必然**复现 12/14 且剂量单调的批
    syn = []
    for tid in range(N_TRAJ):
        pos_majority = tid < 12
        for ns in (1, 10, 100, 1000, 4000):
            base = 0.01 * ns if pos_majority else -0.01 * ns
            if (base > 0) != pos_majority:      # 强制该轨迹的多数方向
                base = -base if base != 0 else 0.5
            syn.append({"tid": "t%02d" % tid, "inject_scope": "k",
                        "inject_n_sites": ns, "p9_lo_meas": 0.0,
                        "p9_hi_meas": base})
        # ⚖⚠⚠⚠ 必须同时有 scope=single / all ⇒ 否则 C2「剂量混合」判据**恒红**
        #   （合成夹具少一维 ⇒ 判据看起来红，其实是夹具不全）
        for sc in ("single", "all"):
            syn.append({"tid": "t%02d" % tid, "inject_scope": sc,
                        "inject_n_sites": None, "p9_lo_meas": 0.0,
                        "p9_hi_meas": 0.5 if pos_majority else -0.5})
    import tempfile
    fd, p = tempfile.mkstemp(suffix=".jsonl"); os.close(fd)
    io.open(p, "w", encoding="utf-8").write(
        "\n".join(json.dumps(r) for r in syn) + "\n")

    # C0 Spearman：构造已知秩相关
    chk("C0", abs(spearman([1, 2, 3, 4], [10, 20, 30, 40]) - 1.0) < 1e-12,
        "完全同序 ⇒ rho=%.6f" % spearman([1, 2, 3, 4], [10, 20, 30, 40]))
    chk("C0b", abs(spearman([1, 2, 3, 4], [40, 30, 20, 10]) + 1.0) < 1e-12,
        "完全逆序 ⇒ rho=%.6f" % spearman([1, 2, 3, 4], [40, 30, 20, 10]))
    # ⚖⚠⚠ 并列必须取**平均秩**（numpy 默认会给出不同名次 ⇒ 静默错一个值）
    # ⚖⚠⚠⚠ 这一条第一版写成 `spearman([1,1,2],[5,5,9]) == 1.0`
    #   ⇒ **两种名次都给 1.0** ⇒ 用例**区分不了** ⇒ 台架 P6 存活。
    #   ⚖⚠⚠⚠ 用例必须选「并列处理不同 ⇒ rho 不同」的那一组。
    _a, _b = [1, 1, 2, 3], [1, 2, 2, 3]
    chk("C0c", abs(spearman(_a, _b) - 0.8333333333333333) < 1e-12,
        "并列处理不同会改 rho ⇒ rho=%.6f（平均秩 0.833333 / 顺序名次 0.838870）"
        % spearman(_a, _b))

    # C1 多数口径：平票算 False
    rows = [{"tid": "a", "p9_lo_meas": 0.0, "p9_hi_meas": 1.0},
            {"tid": "a", "p9_lo_meas": 0.0, "p9_hi_meas": -1.0},
            {"tid": "b", "p9_lo_meas": 0.0, "p9_hi_meas": 1.0}]
    chk("C1", majority_count(rows) == (1, 2), "平票不算真 ⇒ %s" % (majority_count(rows),))

    # C2 缺读数必须拒读
    # ⚖⚠⚠⚠ 这里必须接 **Exception** 再断言类型，⛔ 不能只接 HardFail ——
    #   否则把守卫拆掉之后 `float(None)` 抛 TypeError ⇒ 直接逃出 selftest
    #   ⇒ 台架按「崩」记 ⇒ 而**崩 ⛔ 不等于按判据转红**（变异 P3 当场撞到）。
    try:
        d_of({"tid": "z", "p9_lo_meas": None, "p9_hi_meas": 1.0})
        chk("C2", False, "缺 p9_lo_meas 却**没有**拒读")
    except HardFail as e:
        chk("C2", "未量到" in str(e), "拒读理由是「未量到」：%s" % str(e)[:40])
    except Exception as e:
        chk("C2", False, "拒读时抛的是 %s 而不是 HardFail ⇒ 崩 ⛔ 不算按判据转红"
            % type(e).__name__)

    # C3 坏 JSON 必须拒读，不许静默跳过
    badp = p + ".bad"
    io.open(badp, "w", encoding="utf-8").write('{"tid":"a","p9_lo_meas":0,'
                                               '"p9_hi_meas":1}\n{oops\n')
    try:
        load_jsonl(badp)
        chk("C3", False, "有坏行却**没有**拒读")
    except HardFail as e:
        chk("C3", "解析失败" in str(e), "拒读理由正确：%s" % str(e)[:40])
    except Exception as e:
        chk("C3", False, "拒读时抛的是 %s 而不是 HardFail" % type(e).__name__)

    # C4 合成批上跑一遍：多数必须复现 12/14
    L, rc = audit("w", p)
    chk("C4", rc == 0, "合成批审计 rc=%d" % rc)
    chk("C5", any("= 12/14（账本记 12）⇒ ✅ 复现" in x for x in L),
        "C1 行必须印出复现成功")

    for f in (p, badp):
        try:
            os.unlink(f)
        except OSError:
            pass

    print("自检 %d/%d 通过" % (len(ok), len(ok) + len(bad)))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description="符号判决的剂量混淆审计（零 GPU）")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--arm", choices=sorted(DEFAULT_FILES), default=None)
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    arms = [args.arm] if args.arm else sorted(DEFAULT_FILES)
    rc = 0
    for arm in arms:
        path = DEFAULT_FILES[arm]
        if not os.path.exists(path):
            print("【臂】%s ｜ ⛔ 文件不存在：%s" % (arm, path))
            rc = 1
            continue
        L, r = audit(arm, path)
        print("\n".join(L)); print()
        rc |= r
    return rc


if __name__ == "__main__":
    sys.exit(main())
