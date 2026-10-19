#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""layer_row_audit.py —— 判决清单里那 **4 行「层内 rho 正号」**的重算与对账（修订 244.56，零 GPU）

🔴🔴 **本工具问什么**

  244.55 把判决数的**来源链**钉死之后，`headroom_audit.py` 的判决清单十行里
  **还有 4 行是「层内 rho 正号」的抄写**，而 244.55 的 C8 明确把它们标成
  「**未量到**」（那个工具⛔ 不重算它们）：

      传播层 w（244.37）      9/14
      传播层 rand（244.37）  12/14
      传播层 w 直接层         6/7
      传播层 rand 直接层      5/7

  ⚖⚠⚠⚠ **这 4 行和 244.55 刚撤回的那一行是同一类风险**（手抄、无人独立重算）
  ⇒ 本工具把它们**从日志重算**出来，再与那份表**逐行对账**。

⚖⚖⚖ **重算走的是既有生产机械（⛔ 不另写一套）**

      `dose_axis_audit.load_k_positions`  ← 真探针里的 `_k_positions`（AST 抽出）
      `dose_axis_audit.load_cells` / `k_cells`
      `dose_axis_audit.within_mech`       ← 层内 rho（机制固定、只变剂量）
      `arm_contrast_audit.contrast`       ← 配对 + 符号计数 + 各臂 vs 零
      `arm_verdict.fisher_exact_two_sided` ← 跨臂 Fisher
      `verdict_source_audit.derive_arm`   ← 预登记主统计量的分子/分母（244.55 的工具）

  ⚖⚠⚠⚠ **本工具不复用任何「手抄的期望」**：期望值一律**从读数/日志算出来**再互相比。

⚖⚖⚖ **顺带重算一个从没被独立算过的数**：**预登记主统计量的跨臂 Fisher
  = 0.0460717**（244.23.3 / 244.30 的「合计」行）⇒ 本工具从 2×2 表
  `[[12, 2], [6, 8]]` 重算 ⇒ 必须逐位对上。

⚖⚠⚖⚖ **本工具⛔ 不发批**、⛔ 不改探针、⛔ 不连远端、⛔ 不写/删任何数据文件。
⚖⚠⚖ 每条判据都必须**能红**：自检用畸形夹具证明「红得了」，
  变异台（`mut_layer_row_audit.py`）在**源码层**证明「红得了」。

跑法：
    python3 layer_row_audit.py
    python3 layer_row_audit.py --selftest
退出码：0 = 全部判据通过；1 = 有判据红；2 = 前置/读数问题。
"""

import argparse
import collections
import importlib.util
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))

W_LOG = os.path.join(REPO, ".cache", "r244", "w_new.log")
RAND_LOG = os.path.join(REPO, ".cache", "r244", "rand_new.log")
PROBE_REL = os.path.join(REPO, ".cache", "mutbak", "r204_noise_probe.py")
JSONL_W = os.path.join(REPO, ".cache", "r244", "_an.txt")
JSONL_RAND = os.path.join(REPO, ".cache", "r244", "_ra.txt")

# ⚖ 判决清单里那 4 行（**表里的抄写**，由 AST 从 headroom_audit.py 抽出）
LAYER_ROWS = ("传播层 w（244.37）", "传播层 rand（244.37）",
              "传播层 w 直接层", "传播层 rand 直接层")

# ⚖ 244.32 §③ 记的**层内 rho 正号**的 p —— 账本**印到 3 位小数**，
#   这里存**精确值**（由重算得到），账本印的那一版只用来对账展示
LAYER_P = {
    "传播层 w（244.37）": 0.4239501953125,
    "传播层 rand（244.37）": 0.012939453125,
    "传播层 w 直接层": 0.125,
    "传播层 rand 直接层": 0.453125,
}
# ⚖ 账本 244.32 §③ 印出来的样子（3 位小数）
LAYER_P_LEDGER = {
    "传播层 w（244.37）": "0.424",
    "传播层 rand（244.37）": "0.0129",
    "传播层 w 直接层": "0.125",
    "传播层 rand 直接层": "0.453",
}

# ⚖ 预登记主统计量的跨臂 Fisher（244.23.3 / 244.30 的「合计」行）
PREREG_FISHER = 0.0460717

# ⚖⚠⚠ **仍未量到**（⛔ 不许写成「无差异」）
#   ⚖ 用 **list**（⛔ 不是 tuple）：自检要能临时少印一条 ⇒ 夹具必须能改它
BLANKS = [
    ("层内 rho 的**重复性**",
     "rep_n=1 ⇒ 层内读数 ~1σ ⇒ 「rand 臂 12/14 是不是噪声」**仍未解释**（244.37）"),
    ("「层内」这个分层本身的机制含义",
     "「直接层 / 传播层」按**读出位点是否被注入**分，⛔ 不是按「机制」分 ⇒ "
     "「层内 = 机制固定」这个说法**未量到**"),
    ("这 4 行对应的**剂量跨度**",
     "层内 rho 跨**不同 k 档** ⇒ 与 244.48/244.50 的「跨剂量多数」是同一个坑 ⇒ "
     "**固定/分层剂量前仍不可分辨**"),
]
BLANKS_REQUIRED = ("层内 rho 的**重复性**",
                   "「层内」这个分层本身的机制含义",
                   "这 4 行对应的**剂量跨度**")

_MODS = {}


def _load(path, name):
    if not os.path.isfile(path):
        raise SystemExit("PRECOND_FAIL: 找不到 %s" % path)
    if name in _MODS:
        return _MODS[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _MODS[name] = mod
    return mod


def dose_axis():
    return _load(os.path.join(HERE, "dose_axis_audit.py"), "dose_axis_audit")


def arm_contrast():
    return _load(os.path.join(HERE, "arm_contrast_audit.py"), "arm_contrast_audit")


def arm_verdict():
    return _load(os.path.join(HERE, "arm_verdict.py"), "arm_verdict_mod")


def verdict_source():
    return _load(os.path.join(HERE, "verdict_source_audit.py"), "verdict_source_audit")


# ---------------------------------------------------------------- 计算


def derive_layers(pw_prop, pw_direct, pr_prop, pr_direct):
    """⚖ 从 `within_mech` 的返回（`{tid: (rho, 档数)}`）算出**四行**。
    ⚖ **复用** `arm_contrast_audit.contrast`（⛔ 不另写一套符号计数）。"""
    AC = arm_contrast()
    out = collections.OrderedDict()
    for tag, want, pw_raw, pr_raw in (
            ("传播层 w（244.37）", False, pw_prop, pr_prop),
            ("传播层 rand（244.37）", False, pw_prop, pr_prop),
            ("传播层 w 直接层", True, pw_direct, pr_direct),
            ("传播层 rand 直接层", True, pw_direct, pr_direct)):
        s = AC.contrast(pw_raw, pr_raw, "w 臂 / %s" % tag, "rand 臂 / %s" % tag)
        if tag.startswith("传播层 w"):
            out[tag] = {"k": s["w_pos"], "n": s["n_paired"],
                        "p": s["w_sign_p"], "zero": s["w_zero"],
                        "neg": s["w_neg"], "dropped": s["dropped"],
                        "per_tid": s["per_tid"]}
        else:
            # ⚠⚠⚠ `contrast()` **只返回 `w_zero`** ⇒ rand 的零号数必须**自己数**
            #   （244.56 实测：rand 直接层有 **1 条** rho=0 ⇒ 漏掉它，
            #   ⚖   「正+负+零 == n」这条判据就会**误报红**）
            r_zero = s["n_paired"] - s["r_pos"] - s["r_neg"]
            out[tag] = {"k": s["r_pos"], "n": s["n_paired"],
                        "p": s["r_sign_p"], "zero": r_zero,
                        "neg": s["r_neg"], "dropped": s["dropped"],
                        "per_tid": s["per_tid"]}
    return out


def derive_from_logs():
    """⚖ 生产路径：日志 → dose_axis_audit → arm_contrast_audit → 四行"""
    D = dose_axis()
    AC = arm_contrast()
    kp = D.load_k_positions(PROBE_REL)
    cw = D.load_cells(W_LOG)
    cr = D.load_cells(RAND_LOG)
    rw = D.k_cells(cw, kp)
    rr = D.k_cells(cr, kp)
    pw_prop = D.within_mech(rw, False)
    pr_prop = D.within_mech(rr, False)
    pw_dir = D.within_mech(rw, True)
    pr_dir = D.within_mech(rr, True)
    # ⚖ 两臂必须是**同一批轨迹**（J4 已钉过）⇒ 这里再钉一次
    if sorted(pw_prop) != sorted(pr_prop):
        raise SystemExit("PRECOND_FAIL: 两臂轨迹集合不一致 ⇒ 不是配对，拒读")
    return derive_layers(pw_prop, pw_dir, pr_prop, pr_dir), \
        {"prop": (pw_prop, pr_prop), "direct": (pw_dir, pr_dir)}


def derive_prereg_fisher():
    """⚖ 从**读数**重算预登记主统计量，再算它的跨臂 Fisher"""
    VS = verdict_source()
    dw = VS.derive_arm(VS.load_rows(JSONL_W), "w")
    dr = VS.derive_arm(VS.load_rows(JSONL_RAND), "rand")
    w_pos = dw["prereg"][0]
    w_n = dw["prereg"][1]
    r_pos = dr["prereg"][0]
    r_n = dr["prereg"][1]
    p, _ = arm_verdict().fisher_exact_two_sided(
        w_pos, w_n - w_pos, r_pos, r_n - r_pos)
    return {"w": (w_pos, w_n), "rand": (r_pos, r_n), "fisher": p}


# ---------------------------------------------------------------- 判据


def audit(layers, table_rows, prereg, tol=1e-6):
    """⚖ 判据（C1–C6）。返回 (results, lines)"""
    L = []
    R = collections.OrderedDict()

    def put(cid, ok, detail):
        R[cid] = bool(ok)
        L.append("  [%s] %s：%s" % ("PASS" if ok else "FAIL", cid, detail))

    tmap = dict((n, (k, nn)) for n, k, nn, _t in table_rows)

    # ---- C1 四行的 k/n 逐行对账 ------------------------------------
    mism = []
    for name in LAYER_ROWS:
        got = layers[name]
        tab = tmap.get(name)
        if tab is None:
            mism.append((name, None, (got["k"], got["n"])))
        elif tab != (got["k"], got["n"]):
            mism.append((name, tab, (got["k"], got["n"])))
    L.append("  ℹ 判决清单里那 4 行的对账（**从日志重算** vs **表里的抄写**）")
    for name in LAYER_ROWS:
        got = layers[name]
        tab = tmap.get(name)
        mark = "✅" if tab == (got["k"], got["n"]) else "⛔⛔⛔ 不一致"
        L.append("      %-22s 重算 %d/%d ｜ 表里 %s  %s"
                 % (name, got["k"], got["n"],
                    ("%d/%d" % tab) if tab else "（缺）", mark))
    put("C1", not mism,
        "4 行的 k/n 必须与重算值**逐位相等**；不一致 %d 行%s"
        % (len(mism),
           ("：" + "；".join("%s 表里 %s vs 重算 %d/%d"
                             % (n, ("%d/%d" % a) if a else "缺", b[0], b[1])
                             for n, a, b in mism)) if mism else ""))

    # ---- C2 四行的 p 对账 ------------------------------------------
    bad_p = []
    for name in LAYER_ROWS:
        got = layers[name]
        exp = LAYER_P.get(name)
        if exp is None or abs(got["p"] - exp) > 1e-9:
            bad_p.append((name, got["p"], exp))
    put("C2", not bad_p,
        "4 行的**各臂 vs 零**的 p 必须与重算值**逐位相等**"
        "（账本 244.32 §③ 印的是 %s）；不一致 %d 行%s"
        % ("、".join("%s %s" % (n, LAYER_P_LEDGER.get(n, "?"))
                    for n in LAYER_ROWS),
           len(bad_p),
           ("：" + "；".join("%s 重算 %.7g vs 期望 %.7g"
                             % (n, p, e) for n, p, e in bad_p)) if bad_p else ""))

    # ---- C3 分母口径：每一层的 14 条**全部有交代** ------------------
    prop = layers["传播层 w（244.37）"]
    dire = layers["传播层 w 直接层"]
    cov_prop = prop["n"] + len(prop["dropped"])
    cov_dir = dire["n"] + len(dire["dropped"])
    ok3 = (cov_prop == 14 and cov_dir == 14
           and prop["n"] == 14 and dire["n"] == 7
           and len(dire["dropped"]) == 7)
    put("C3", ok3,
        "分母口径：传播层可算 %d、剔 %d ⇒ 合计 %d 条；直接层可算 %d、剔 %d ⇒ 合计 %d 条"
        "⇒ 每一层都必须**把那 14 条全部有交代**（可算 + 被剔）"
        % (prop["n"], len(prop["dropped"]), cov_prop,
           dire["n"], len(dire["dropped"]), cov_dir))

    # ---- C4 第三态（rho=0）必须留在分母里 ---------------------------
    zs = [(name, layers[name]["zero"], layers[name]["k"],
           layers[name]["neg"], layers[name]["n"]) for name in LAYER_ROWS]
    ok4 = all(k + ng + z == n for _nm, z, k, ng, n in zs)
    put("C4", ok4,
        "rho=0 的轨迹**既不进分子、也不能从分母里丢掉**；逐行 (正+负+零) vs n：%s"
        % "；".join("%s %d+%d+%d=%d vs n=%d %s"
                    % (nm, k, ng, z, k + ng + z, n,
                       "✅" if k + ng + z == n else "⛔")
                    for nm, z, k, ng, n in zs))

    # ---- C5 预登记主统计量的跨臂 Fisher ----------------------------
    ok5 = (abs(prereg["fisher"] - PREREG_FISHER) <= 1e-6)
    put("C5", ok5,
        "预登记主统计量的跨臂 Fisher：重算 %.7g（2×2 表 [[%d,%d],[%d,%d]]，"
        "期望 %.7g）"
        % (prereg["fisher"], prereg["w"][0], prereg["w"][1] - prereg["w"][0],
           prereg["rand"][0], prereg["rand"][1] - prereg["rand"][0],
           PREREG_FISHER))

    # ---- C6 留白 ----------------------------------------------------
    for t, why in BLANKS:
        L.append("  · %s —— **未量到**（%s）" % (t, why))
    missing = [t for t in BLANKS_REQUIRED
               if not any(("· %s ——" % t) in x for x in L)]
    put("C6", not missing,
        "三条未量到项必须逐条印出（⛔ 不许写成「无差异」）；缺 %s"
        % ("无" if not missing else "、".join(missing)))

    return R, L


def build_report(layers, table_rows, prereg, raw=None):
    L = []
    L.append("【1】那 4 行「层内 rho 正号」的**重算来源**（⛔ 全部走既有生产机械）")
    L.append("  ⚖ `dose_axis_audit.load_k_positions`（真探针的 `_k_positions`，AST 抽出）")
    L.append("  ⚖ `dose_axis_audit.load_cells` / `k_cells` / `within_mech`")
    L.append("  ⚖ `arm_contrast_audit.contrast`（配对 + 符号计数 + 各臂 vs 零）")
    L.append("  ⚖ `arm_verdict.fisher_exact_two_sided`（跨臂 Fisher）")
    L.append("  ⚖ `verdict_source_audit.derive_arm`（预登记主统计量的分子/分母）")
    L.append("")
    L.append("【2】逐轨迹明细（层内 rho；⛔ rho=0 的是**第三态**，不是「负」）")
    if raw:
        for tag, key in (("传播层", "prop"), ("直接层", "direct")):
            pw, pr = raw[key]
            L.append("  ── %s" % tag)
            L.append("      %-38s %-14s %-14s" % ("tid", "w rho", "rand rho"))
            for t in sorted(pw):
                L.append("      %-38s %-14s %-14s"
                         % (t, _rho(pw[t]), _rho(pr.get(t))))
            L.append("")
    else:
        L.append("  ⚠ 本次没有原始层内读数（夹具路）⇒ 逐轨迹明细**未量到**")
        L.append("")
    L.append("【3】判据")
    R, L3 = audit(layers, table_rows, prereg)
    L.extend(L3)
    return L, R


def _rho(v):
    if v is None:
        return "未量到"
    if isinstance(v, tuple):
        v = v[0]
        if v is None:
            return "未量到"
    if v == 0:
        return "0（第三态）"
    return "%+.4f" % v


def run():
    VS = verdict_source()
    layers, raw = derive_from_logs()
    table_rows = VS.extract_verdicts(os.path.join(HERE, "headroom_audit.py"))
    prereg = derive_prereg_fisher()
    L, R = build_report(layers, table_rows, prereg, raw)
    return L, (0 if all(R.values()) else 1), R


# ---------------------------------------------------------------- 自检夹具

# ⚖ 合成夹具：层内 rho 的**逐轨迹**取值（⛔ 从规格推，不抄生产数据）
# ⚖⚠⚠ **两臂的 tid 集合必须逐条相同**（配对设计）⇒ 两条都用 t00… 与 d00…
FX_PROP_W = ([1.0] * 9 + [-1.0] * 4 + [0.0])          # 9 正 / 4 负 / 1 零 ⇒ n=14
FX_PROP_R = ([1.0] * 12 + [-1.0] * 2)                 # 12 正 / 2 负 ⇒ n=14
FX_DIR_W = ([1.0] * 6 + [-1.0] * 1)                   # 6 正 / 1 负 ⇒ n=7
FX_DIR_R = ([1.0] * 5 + [-1.0] * 1 + [0.0])          # 5 正 / 1 负 / 1 零 ⇒ n=7


def fx_mech(vals, dropped=0):
    """⚖ 造 `{tid: (rho, 档数)}`（生产形状）"""
    out = collections.OrderedDict()
    for i, v in enumerate(vals):
        out["t%02d" % i] = (v, 5)
    for i in range(dropped):
        out["d%02d" % i] = (None, 1)
    return out


def fx_layers():
    """⚖ 夹具：传播层 14 条全可算；直接层 7 条可算 + 7 条「档数不足」被剔"""
    pw_prop = fx_mech(FX_PROP_W)
    pr_prop = fx_mech(FX_PROP_R)
    pw_dir = fx_mech(FX_DIR_W, dropped=7)
    pr_dir = fx_mech(FX_DIR_R, dropped=7)
    return derive_layers(pw_prop, pw_dir, pr_prop, pr_dir)


def fx_table_rows():
    """⚖ 夹具的「表」：故意用**正确**的那 4 行（⇒ 干净夹具必须全绿）"""
    return [("传播层 w（244.37）", 9, 14, "事后·层内"),
            ("传播层 rand（244.37）", 12, 14, "事后·层内"),
            ("传播层 w 直接层", 6, 7, "事后·层内"),
            ("传播层 rand 直接层", 5, 7, "事后·层内")]


def fx_prereg():
    return {"w": (12, 14), "rand": (6, 14), "fisher": PREREG_FISHER}


def selftest():
    ok, bad = [], []

    def chk(t, cond, why=""):
        (ok if cond else bad).append(t)
        print(("[PASS] %s %s" if cond else "[FAIL] %s %s") % (t, why))

    layers = fx_layers()
    R, L = audit(layers, fx_table_rows(), fx_prereg())
    chk("C0", all(R.values()),
        "干净夹具全绿（红的有 %s）"
        % (",".join(k for k, v in R.items() if not v) or "无"))

    # ---- C1：表里某一行被抄错 ⇒ 必须红 ----------------------------
    t1 = list(fx_table_rows())
    t1[0] = ("传播层 w（244.37）", 8, 14, "事后·层内")
    R1, L1 = audit(layers, t1, fx_prereg())
    chk("C1x", not R1.get("C1"),
        "表里「传播层 w」被抄成 8/14 ⇒ C1 必须红")

    # ---- C2：p 的期望被改 ⇒ 必须红 --------------------------------
    old = dict(LAYER_P)
    LAYER_P["传播层 w（244.37）"] = 0.9
    try:
        R2, L2 = audit(layers, fx_table_rows(), fx_prereg())
    finally:
        LAYER_P.clear()
        LAYER_P.update(old)
    chk("C2x", not R2.get("C2"),
        "层内 p 的期望被改 ⇒ C2 必须红")

    # ---- C3：直接层的分母被改 ⇒ 必须红 ----------------------------
    lay3 = dict(layers)
    lay3["传播层 w 直接层"] = dict(layers["传播层 w 直接层"])
    lay3["传播层 w 直接层"]["n"] = 14
    lay3["传播层 w 直接层"]["dropped"] = []
    R3, L3 = audit(lay3, fx_table_rows(), fx_prereg())
    chk("C3x", not R3.get("C3"),
        "直接层分母被改成 14（且不剔任何）⇒ C3 必须红")

    # ---- C3y：只破坏**覆盖率**那一支 ⇒ C3 必须红 ---------------------
    #   ⚠⚠⚠ 244.56 踩到的：**一条判据拆成两支，两支各要一条夹具单独踩到**。
    #   ⚖ 上面那条 C3x 破坏的是「n/剔的条数」那一支 ⇒ 覆盖率那一支**走不到**
    #   ⇒ 变异台 M9（把覆盖率检查焊成恒真）在夹具上**看不出来** ⇒ 变异存活。
    #   ⇒ 这里造一条**只**多塞一个「被剔」tid 的夹具 ⇒ 覆盖率 15 ≠ 14
    #   ⇒ 而 n 与「剔的条数」都还是原样 ⇒ **只有覆盖率那一支会红**。
    lay3y = dict(layers)
    lay3y["传播层 w（244.37）"] = dict(layers["传播层 w（244.37）"])
    lay3y["传播层 w（244.37）"]["dropped"] = ["x"]
    R3y, L3y = audit(lay3y, fx_table_rows(), fx_prereg())
    chk("C3y", not R3y.get("C3"),
        "多塞一个「被剔」tid（覆盖率 15≠14，其余不变）⇒ C3 必须红")

    # ---- C4：零号被从分母里丢掉 ⇒ 必须红 --------------------------
    lay4 = dict(layers)
    lay4["传播层 w（244.37）"] = dict(layers["传播层 w（244.37）"])
    lay4["传播层 w（244.37）"]["n"] = 13     # ⛔ 把那条 rho=0 的从分母里悄悄丢掉
    R4, L4 = audit(lay4, fx_table_rows(), fx_prereg())
    chk("C4x", not R4.get("C4"),
        "rho=0 的那条被从分母里丢掉 ⇒ C4 必须红")

    # ---- C5：预登记 Fisher 被改 ⇒ 必须红 --------------------------
    pr5 = dict(fx_prereg())
    pr5["fisher"] = 0.0460717 + 0.001
    R5, L5 = audit(layers, fx_table_rows(), pr5)
    chk("C5x", not R5.get("C5"),
        "预登记 Fisher 被改 ⇒ C5 必须红")

    # ---- C6：少印一条留白 ⇒ 必须红 --------------------------------
    old_blanks = BLANKS[:]
    try:
        del BLANKS[1]
        R6, L6 = audit(layers, fx_table_rows(), fx_prereg())
    finally:
        BLANKS[:] = old_blanks
    chk("C6x", not R6.get("C6"),
        "少印一条留白 ⇒ C6 必须红")

    print("自检 %d/%d 通过" % (len(ok), len(ok) + len(bad)))
    if bad:
        print("失败：%s" % ", ".join(bad))
        return 1
    return 0


def main():
    ap = argparse.ArgumentParser(description="判决清单那 4 行的重算与对账（零 GPU）")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    try:
        L, rc, R = run()
    except SystemExit as e:
        print(str(e), file=sys.stderr)
        return 2
    print("\n".join(L))
    print("")
    print("判据：%d/%d 通过" % (sum(1 for v in R.values() if v), len(R)))
    return rc


if __name__ == "__main__":
    sys.exit(main())
