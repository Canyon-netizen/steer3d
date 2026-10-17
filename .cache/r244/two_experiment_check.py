#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""two_experiment_check —— 「这两份日志真的是两个实验吗」

## 这条在量什么

跨臂判决（Fisher / 符号检验）要成立，前提是**两臂真的是两次不同的实验**。
⚠⚠⚠ 修订 244.25 的实测发现：这个前提此前**从未被单独验过** ——
它只是**隐含**在「两臂 p 值不同」里，而「p 值不同」也可以来自别的原因
（格数不同 / 少了几格 / 配对错位）。

⚖⚠ 更要命的一种失效：把**同一份日志**当成两臂传进去。
⇒ 逐位相同 ⇒ 判决是恒等式 ⇒ 所有 p 都是 0/0 那种无意义的东西，
⚖ 而报告看上去和正常情况**一模一样**。
⚖ 这正是账本反复记的「两条名义上不同的配置给出逐位相同的读数 ⇒ 它们是同一个实验」。

## ⚠⚠⁴ 一个必须避开的陷阱：臂名本身就是载荷的一部分

每条读数 JSON 里都带 `"arm": "w"` / `"arm": "rand"`。
⇒ **直接比原始行，两臂必然「不同」，而这个不同可能完全由臂名解释**，
⚖⚗ 对「读数有没有变」零信息量。
⇒ 本工具**先剥掉 `arm` 字段再比**。这是本工具存在的第一个理由。

## 判据（都能红）

1. ⛔ 格数不等 ⇒ 拒读（不是「取交集」，那会让分母偷偷变小）
2. ⛔ tid 逐格不等 ⇒ 拒读（错位会把上一格读成这一格）
3. ⛔ `MUST_MATCH` 字段逐格不等 ⇒ 拒读（那就不是单变量对照）
4. ⛔ 剥 arm 后载荷 md5 **相同** ⇒ 硬失败「这是同一个实验」
5. ⛔ 承重字段（`p9_lo_meas`）逐格**全**同 ⇒ 硬失败（同上，只是形式不同）
6. ⚖ 部分相同的格**不是**失败，但必须**印出来**并点名是哪几格

跑法：
    python3 two_experiment_check.py A.log B.log
    python3 two_experiment_check.py --selftest
退出码：0 = 两臂确是两个实验；1 = 判定失败；3 = 台架/定位问题。
"""

import argparse
import hashlib
import json
import os
import re
import sys

# ⚖ 判定「单变量对照」时必须逐位相同的字段（244.23.2 实测两臂全同）
MUST_MATCH = ("tid", "k", "scope", "P", "t", "n_gen", "pos_frac", "n_steps",
              "gap", "inject_scope", "inject_n_sites", "inject_nested")

# ⚖ 判决吃的那一个量（闸 5/7 的 Δ 就是它算出来的）
LOAD_BEARING = "p9_lo_meas"

# ⚖⚠⚠ 「按设计就与臂无关」的字段，附**理由与生产者行号**。
# ⚖⚗ 为什么必须逐个写理由：把 0/137 全同的字段**笼统**印在一起，
# ⚖   读的人无法区分「正向对照通过」与「该红的缺陷」—— 而这两件事的修法相反。
# ⚖⚠ 这张表**只能增不能减**：少了谁，谁就会掉进「⛔ 按设计应变却没变」那一桶，
# ⚖ 于是有人必须为它写理由。⇒ 它本身是可核的，不是免责名单。
INVARIANT_BY_DESIGN = {
    "b_mark": "无注入基线的前向 logit（r204_noise_probe.py:436/480）"
              "⇒ 结构上与注入向量无关，跨臂相同是**正向对照通过**",
    "b_ctl": "无注入基线的 control logit（同上 :437/481）⇒ 同上",
    "rep_n_lo": "实测 137/137 恒为 **1**（:98）⇒ **每格只测一次，格内无重复**",
    "rep_n_hi": "同上 ⇒ 每格只测一次",
    "rep_std_lo": "n==1 ⇒ 刻意给 **None**（:99-100「没量到，不是 0.0」）⇒ 恒为 null",
    "rep_std_hi": "同上 ⇒ 恒为 null",
    "rep_spread_lo": "n==1 ⇒ max(v)−min(v) 恰为 0（:102）⇒ 恒为 0.0",
    "rep_spread_hi": "同上 ⇒ 恒为 0.0",
    "rep_exact_lo": "n==1 ⇒ max(v)==min(v) **恒真**（:104）⇒ ⚠ 它长得像"
                    "「确定性证据」但结构上不可能为 False，⛔ 不得当作证据引用",
    "rep_exact_hi": "同上 ⇒ 恒真，不得当作确定性证据引用",
}

READ_MARKERS = ("p9_lo_meas", "p9_hi_meas")


class HardFail(Exception):
    pass


def extract_readings(path):
    """按顺序抽出每格的读数 JSON。⛔ 一格多于一条 ⇒ 拒读（不知道该信哪条）。"""
    out = []
    with open(path, "rb") as fh:
        for raw in fh:
            t = raw.decode("utf-8", "replace").strip()
            if not t.startswith("{"):
                continue
            if not all(m in t for m in READ_MARKERS):
                continue
            out.append(json.loads(t))
    return out


def normalize(reading):
    """⚖⚠ 剥掉 `arm` —— 它是**标签**不是载荷。留着它，「两臂不同」就是废话。"""
    r = dict(reading)
    r.pop("arm", None)
    return r


def payload_md5(cells):
    """规范化后的载荷 md5。⚖ 逐格拼接 ⇒ 格序变了 md5 也变（那是另一个错误）。"""
    h = hashlib.md5()
    for c in cells:
        h.update(json.dumps(normalize(c), sort_keys=True,
                            separators=(",", ":")).encode("utf-8"))
    return h.hexdigest()[:12]


def field_diff_counts(cells_a, cells_b):
    keys = sorted(set(k for c in cells_a for k in c)
                  | set(k for c in cells_b for k in c))
    counts = {}
    for k in keys:
        n = 0
        for a, b in zip(cells_a, cells_b):
            if a.get(k) != b.get(k):
                n += 1
        counts[k] = n
    return counts


def check(path_a, path_b, label_a="A", label_b="B", verbose=True):
    L = []
    ca = extract_readings(path_a)
    cb = extract_readings(path_b)
    n = len(ca)

    # ---- 闸 1：格数 ----
    if len(cb) != n:
        raise HardFail("格数不等：%s %d 格 vs %s %d 格 —— ⛔ 不取交集"
                       "（那会让分母偷偷变小），拒读" % (label_a, n, label_b, len(cb)))

    # ---- 闸 2：tid 逐格 ----
    for i, (a, b) in enumerate(zip(ca, cb)):
        if a.get("tid") != b.get("tid"):
            raise HardFail("第 %d 格 tid 对不上：%r vs %r（错位会把上一格读成这一格）"
                           % (i + 1, a.get("tid"), b.get("tid")))

    # ---- 闸 3：MUST_MATCH ----
    bad = []
    for i, (a, b) in enumerate(zip(ca, cb)):
        for k in MUST_MATCH:
            if a.get(k) != b.get(k):
                bad.append("第%d格 %s: %r vs %r" % (i + 1, k, a.get(k), b.get(k)))
    if bad:
        raise HardFail("两臂不是单变量对照（%d 处不符）：%s%s"
                       % (len(bad), "；".join(bad[:3]),
                          " …" if len(bad) > 3 else ""))

    ma, mb = payload_md5(ca), payload_md5(cb)

    L.append("=" * 74)
    L.append("两臂是否真是两个实验（%s vs %s，各 %d 格）" % (label_a, label_b, n))
    L.append("=" * 74)
    L.append("  格数 %d / %d   tid 逐格一致   MUST_MATCH(%d 项) 逐格一致"
             % (len(ca), len(cb), len(MUST_MATCH)))
    L.append("  ⚖ 载荷 md5（**已剥掉 arm 字段**）  %s=%s  %s=%s"
             % (label_a, ma, label_b, mb))
    L.append("  ⚖⚠ 剥 arm 这一步是全部要害：不剥的话，两臂必然「不同」，"
             "而那个不同可能只由臂名解释 ⇒ 对读数零信息量。")

    # ---- 闸 4：剥 arm 后载荷相同 ⇒ 同一个实验 ----
    if ma == mb:
        raise HardFail("剥掉 arm 字段后两臂载荷 md5 **逐位相同**（%s）⇒ "
                       "它们是**同一个实验**，跨臂判决是恒等式，⛔ 所有 p 无意义"
                       % ma)

    counts = field_diff_counts(ca, cb)
    lb = counts.get(LOAD_BEARING, 0)

    L.append("\n  逐字段「有多少格不同」/ %d：" % n)
    inv = [k for k, v in counts.items() if v == 0]
    part = sorted((k for k, v in counts.items() if 0 < v < n),
                  key=lambda k: counts[k])
    full = sorted(k for k, counts_ in counts.items() if counts_ == n)
    # ⚖⚠ 格数一律从 `n` 出，⛔ 不许把 137 写进文案 —— 那会让夹具（小格数）
    # 印出「137/137 全不同」这种不可能的数，而报告看上去完全正常。
    L.append("    %d/%d 全不同（%d 个）：%s"
             % (n, n, len(full), " ".join(full[:14])))
    L.append("    部分不同（%d 个）：%s"
             % (len(part), " ".join("%s=%d" % (k, counts[k]) for k in part[:14])))
    # ⚖⚠⚠ 把「0/%d 全同」**分成两桶**并各带理由。不分桶的话，读的人分不清
    # ⚖ 「正向对照通过」与「该红的缺陷」—— 两者修法相反。
    inv_ok = [k for k in inv if k in INVARIANT_BY_DESIGN]
    # ⚖⚠ MUST_MATCH 那几个**本来就该不变**（闸 3 已逐格核对过它们相等）。
    # ⚖⚗ 把它们塞进「⛔ 按设计应变却没变」那一桶是**误导** —— 那等于说
    # ⚖ 「pos_frac / n_steps 本该随臂变却没变」。⇒ 单独一桶，注明已核对。
    inv_mm = [k for k in inv if k in MUST_MATCH]
    inv_bad = [k for k in inv
               if k not in INVARIANT_BY_DESIGN and k not in MUST_MATCH]
    L.append("    ✅ 闸 3 不变量（MUST_MATCH %d 个，已逐格核对相等）：%s"
             % (len(inv_mm), " ".join(sorted(inv_mm))))
    L.append("    ✅ 按设计不变（不变清单 %d 个，逐个有理由）：" % len(inv_ok))
    for k in sorted(inv_ok):
        L.append("        %-14s %s" % (k, INVARIANT_BY_DESIGN[k]))
    if inv_bad:
        L.append("    ⛔ 按设计**应变**却 0/%d 全同（%d 个）：%s"
                 % (n, len(inv_bad), " ".join(sorted(inv_bad))))
        L.append("       ⇒ 这些既不在 MUST_MATCH、也不在不变清单里。"
                 "要么它们本该随臂变（= 干预没生效，⛔ 判决是恒等式），")
        L.append("          要么它们的理由该补进 INVARIANT_BY_DESIGN（⛔ 不许默默放过）。")
    else:
        L.append("    ✅ 无「按设计应变却没变」的字段")

    # ---- 闸 5：承重字段全同 ⇒ 同样是同一个实验 ----
    if lb == 0:
        raise HardFail("承重字段 %s 逐格**全同**（0/%d 不同）⇒ 判决吃的量"
                       "在两臂之间一动没动 ⛔ 跨臂判决是恒等式"
                       % (LOAD_BEARING, n))
    if lb < n:
        same = [ca[i].get("tid") for i in range(n)
                if ca[i].get(LOAD_BEARING) == cb[i].get(LOAD_BEARING)]
        L.append("\n  ⚠⚠ %s 只有 %d/%d 格不同 ⇒ 有 %d 格**两臂完全一样**："
                 % (LOAD_BEARING, lb, n, len(same)))
        for t in same[:8]:
            L.append("      · %s" % t)
        L.append("  ⚖ 「%d/%d 不同」与「全同」是**两个不同强度的结论**：前者还留尾巴，"
                 "后者什么都不剩。" % (lb, n))

    L.append("\n  ✅ 判定：两臂确是**两个不同的实验**（载荷 md5 不同、承重字段 %d/%d 不同）"
             % (lb, n))
    L.append("  ⚖ 本检查**只**回答「是不是两个实验」。它不回答哪个对、"
             "剂量曲线对不对、阶梯排对了没有。")
    return "\n".join(L)


# ---------------------------------------------------------------- 自检
def _fixture(n_arm_a="w", n_arm_b="rand", shift=0.5, n=6):
    """造两份日志。shift=0 ⇒ 两臂读数**逐位相同**（= 同一个实验的形态）。"""
    log_a, log_b = [], []
    for i in range(n):
        tid = "p%02d__think" % i
        common = {"tid": tid, "k": 10 ** (i % 3), "inject_scope": "k",
                  "inject_n_sites": 10 ** (i % 3), "inject_nested": True,
                  "pos_frac": 0.5, "n_steps": 60, "gap": 113.47440338134766,
                  "P": 108, "t": 1000 + i, "n_gen": 2000 + 2 * i,
                  "p9_hi_meas": -0.5 + 0.1 * i}
        r = dict(common, arm=n_arm_a, p9_lo_meas=round(-0.2 + 0.1 * i + shift, 6))
        log_a.append(json.dumps(r))
        r2 = dict(common, arm=n_arm_b, p9_lo_meas=round(-0.2 + 0.1 * i, 6))
        log_b.append(json.dumps(r2))
    return ("\n".join(log_a) + "\n", "\n".join(log_b) + "\n")


def selftest():
    T = []

    def ck(name, fn):
        try:
            fn()
            T.append((name, "PASS", ""))
        except AssertionError as e:
            T.append((name, "FAIL", str(e) or "断言失败"))
        except Exception as e:
            T.append((name, "FAIL", "%s: %s" % (type(e).__name__, e)))

    def _write(tmp, a, b):
        pa, pb = os.path.join(tmp, "a.log"), os.path.join(tmp, "b.log")
        with open(pa, "w", encoding="utf-8") as f:
            f.write(a)
        with open(pb, "w", encoding="utf-8") as f:
            f.write(b)
        return pa, pb

    import tempfile

    def with_fixture(fn, shift=0.5, **kw):
        tmp = tempfile.mkdtemp()
        a, b = _fixture(shift=shift, **kw)
        fn(*_write(tmp, a, b))

    # T1 绿：真的是两个实验
    def t1():
        out = []

        def run(pa, pb):
            out.append(check(pa, pb))
        with_fixture(run)
        assert "两个不同的实验" in out[0], out[0][-300:]
        assert "已剥掉 arm 字段" in out[0], out[0]
    ck("T1 绿：载荷不同 ⇒ 判两个实验；页眉写明「已剥掉 arm」", t1)

    # T2 红：两臂读数逐位相同 ⇒ 必须硬失败「同一个实验」
    # ⚖ 这是本工具存在的头号理由：把同一份日志当两臂传，判决会变成恒等式。
    def t2():
        def run(pa, pb):
            try:
                check(pa, pb)
            except HardFail as e:
                assert "同一个实验" in str(e), str(e)
                return
            raise AssertionError("两臂逐位相同竟然判通过了")
        with_fixture(run, shift=0.0)
    ck("T2 红：两臂读数逐位相同 ⇒ 硬失败「同一个实验」", t2)

    # T3 红：**只**改臂名不算数 —— 剥 arm 后必须仍判「同一个实验」
    # ⚖⚠ 这是臂名陷阱的反向测试：若实现漏了归一化，这个夹具会被误判成
    # ⚖ 「两个不同的实验」⇒ 而实际上读数一动没动。
    def t3():
        a, b = _fixture(shift=0.0)

        def run(pa, pb):
            try:
                check(pa, pb)
            except HardFail as e:
                assert "同一个实验" in str(e), str(e)
                return
            raise AssertionError("只改臂名竟判成两个不同实验 ⇒ 没剥 arm")
        import tempfile
        tmp = tempfile.mkdtemp()
        run(*_write(tmp, a, b))
    ck("T3 红：只改臂名（读数不动）⇒ 仍须判「同一个实验」", t3)

    # T4 红：格数不等 ⇒ 拒读，且**不许**取交集
    def t4():
        import tempfile
        tmp = tempfile.mkdtemp()
        a, b = _fixture()
        b = "\n".join(b.split("\n")[:4]) + "\n"

        def run(pa, pb):
            try:
                check(pa, pb)
            except HardFail as e:
                assert "格数不等" in str(e), str(e)
                assert "不取交集" in str(e), str(e)
                return
            raise AssertionError("格数不等竟然读过去了")
        run(*_write(tmp, a, b))
    ck("T4 红：格数不等 ⇒ 拒读「不取交集」（分母不许偷偷变小）", t4)

    # T5 红：tid 错位 ⇒ 拒读
    def t5():
        import tempfile
        tmp = tempfile.mkdtemp()
        a, b = _fixture()
        lines = b.split("\n")
        lines[0], lines[1] = lines[1], lines[0]

        def run(pa, pb):
            try:
                check(pa, pb)
            except HardFail as e:
                assert "tid 对不上" in str(e), str(e)
                return
            raise AssertionError("tid 错位竟然读过去了")
        run(*_write(tmp, a, "\n".join(lines)))
    ck("T5 红：tid 错位一格 ⇒ 拒读", t5)

    # T6 红：MUST_MATCH 字段被改 ⇒ 不是单变量对照 ⇒ 拒读
    def t6():
        import tempfile
        tmp = tempfile.mkdtemp()
        a, b = _fixture()
        rows = [json.loads(x) for x in b.split("\n") if x.strip()]
        rows[0]["n_steps"] = 61
        b2 = "\n".join(json.dumps(r) for r in rows) + "\n"

        def run(pa, pb):
            try:
                check(pa, pb)
            except HardFail as e:
                assert "不是单变量对照" in str(e), str(e)
                return
            raise AssertionError("改了 n_steps 竟然判成单变量对照")
        run(*_write(tmp, a, b2))
    ck("T6 红：MUST_MATCH 字段被改 ⇒ 拒读「不是单变量对照」", t6)

    # T7 报告口径：部分相同的格必须被点名，且不得说成「全同」
    def t7():
        out = []

        def run(pa, pb):
            out.append(check(pa, pb))
        import tempfile
        tmp = tempfile.mkdtemp()
        a, b = _fixture(shift=0.5)
        rows = [json.loads(x) for x in b.split("\n") if x.strip()]
        rows[0]["p9_lo_meas"] = rows[0]["p9_lo_meas"] + 0.5
        b2 = "\n".join(json.dumps(r) for r in rows) + "\n"
        run(*_write(tmp, a, b2))
        assert "只有 5/6 格不同" in out[0], out[0]
        assert "p00__think" in out[0], out[0]
        assert "两个不同强度的结论" in out[0], out[0]
        # ⚖ 夹具只有 6 格 ⇒ 报告里不许出现「137/137」这种写死的数
        assert "137" not in out[0], "报告里出现了写死的 137"
    ck("T7 红：部分相同的格须被点名，「5/6 不同」不得说成「全同」", t7)

    # T8 红：0/N 全同的字段必须**分桶** —— 「按设计不变」与
    # 「按设计应变却没变」不能笼统印成一句，否则读的人分不清
    # 「正向对照通过」与「该红的缺陷」。
    def t8():
        out = []

        def run(pa, pb):
            out.append(check(pa, pb))
        import tempfile
        tmp = tempfile.mkdtemp()
        a, b = _fixture(shift=0.5)
        rows = [json.loads(x) for x in b.split("\n") if x.strip()]
        # 造两个「0/N 全同但不在不变清单里」的字段
        for r in rows:
            r["mystery_field"] = 7
        b2 = "\n".join(json.dumps(r) for r in rows) + "\n"
        run(*_write(tmp, a, b2))
        assert "按设计不变" in out[0], out[0]
        assert "mystery_field" in out[0], out[0]
        assert "按设计**应变**却没变" in out[0] or "按设计**应变**却 0/" in out[0], out[0]
    ck("T8 红：0/N 全同的字段须分桶；不在清单里的必须被点名", t8)

    # T9 红：**承重字段全同**而别的字段不同 ⇒ 闸 4（md5）会放过，
    # ⚖ 必须由闸 5 抓住。
    # ⚖⚠ 这条夹具是分开两个闸的关键：不造它的话，闸 5 永远被闸 4 遮蔽，
    # ⚖   于是「删掉闸 5」这个变异会「存活」—— 而那正是恒绿判据的形态。
    def t9():
        import tempfile
        tmp = tempfile.mkdtemp()
        a, b = _fixture(shift=0.0)          # 承重字段两边相同
        rows = [json.loads(x) for x in b.split("\n") if x.strip()]
        for r in rows:                       # 但别的字段变了 ⇒ 载荷 md5 不同
            r["p9_hi_meas"] = r["p9_hi_meas"] + 0.25
        b2 = "\n".join(json.dumps(r) for r in rows) + "\n"

        def run(pa, pb):
            try:
                check(pa, pb)
            except HardFail as e:
                assert "承重字段" in str(e), str(e)
                return
            raise AssertionError("承重字段逐格全同竟然判通过了")
        run(*_write(tmp, a, b2))
    ck("T9 红：承重字段全同但载荷 md5 不同 ⇒ 闸 4 放过、闸 5 必须抓住", t9)

    npass = sum(1 for _, s, _ in T if s == "PASS")
    for name, s, msg in T:
        print("[%s] %s%s" % (s, name, ("  ← " + msg) if msg else ""))
    print("two_experiment_check --selftest: %d/%d" % (npass, len(T)))
    return 0 if npass == len(T) else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log_a", nargs="?")
    ap.add_argument("log_b", nargs="?")
    ap.add_argument("--label-a", default="A")
    ap.add_argument("--label-b", default="B")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if not (args.log_a and args.log_b):
        ap.error("需要两个日志，或 --selftest")
    try:
        print(check(args.log_a, args.log_b, args.label_a, args.label_b))
    except HardFail as e:
        print("⛔ %s" % e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
