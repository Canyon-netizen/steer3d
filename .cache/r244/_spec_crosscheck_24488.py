#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""_spec_crosscheck_24488.py —— **预登记 ↔ 实现 的机械对账**（244.88）。

⚖⚖⚖⚖⚖ **这一条要回答的问题**
   「实现的判据集合、形态、级联、允许配对表、闸门清单、读法清单，是不是**逐条**对上
   预登记写死的东西？」⇒ ⇒ 任何一处**实现自己改了**（或预登记改了但实现没跟上）
   ⇒ ⇒ 必须在这里红。

⚖⚖⚖⚖⚖ **对账方式（⛔ 零共用代码）**
   · 预登记那边：**从 markdown 正文里正则抠出** id / 形态 / 加法对 / 禁止代号；
   · 实现那边：**从源码文本里正则抠出**常量（⛔ **不 import 被检实现** ——
     import 进来就等于让被检对象自己解释自己 ⇒ ⇒ 那样对账没有意义）。
   ⇒ ⇒ 两条来源**互不相干**。

⚖⚖⚖⚖⚖ **必须红的十一类**
   ① 判据 id 集合（H1..H9）② 形态集合（E′/D′/C′/B′/A′）③ 硬失败集合（{H1,H2,H8,H9}）
   ④ 闸门清单（G0-1..G0-9）⑤ 读法清单（R1..R6）⑥ 允许的加法对（预登记 §1 ＋ 更正①）
   ⑦ 禁止配对的**分支代号**（三条）⑧ 扫描维度（3 档 Wilson × 3 种基准）
   ⑨ 级联的**优先级顺序**（E′ → D′ → C′ → B′ → A′）
   ⑩ 联合置信的**逐口径**取值（90% / 85% / 94%）
   ⑪ 实现**不得**出现预登记之外的读法/判据/形态 id
"""

import os
import re
import sys

REPO = os.environ.get("R244_REPO", "/home/zhourui/steer3d")
PREREG = os.environ.get("R244_PREREG", os.path.join(REPO, ".cache", "xcheck",
                                                    "R6_CONSERVATIVE_BOUND_PREREG.md"))
IMPL = os.environ.get("R244_IMPL", os.path.join(REPO, ".cache", "r244",
                                                "conservative_bound_audit.py"))

TOL = 5e-3          # = 账本印两位小数的半个单位（用于联合置信的核对）


def _read(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def _die(msg):
    print("SPEC_FAIL: %s" % msg)
    raise SystemExit(1)


def _grab(text, pattern, what, flags=re.M):
    hits = re.findall(pattern, text, flags)
    if not hits:
        _die("抠不到「%s」" % what)
    return hits


def main():
    if not os.path.isfile(PREREG):
        print("SPEC_FAIL: 预登记不存在：%s" % PREREG)
        return 2
    if not os.path.isfile(IMPL):
        print("SPEC_FAIL: 实现不存在：%s" % IMPL)
        return 2

    pre = _read(PREREG)
    imp = _read(IMPL)

    ok = 0
    red = 0

    def chk(name, got, want):
        nonlocal ok, red
        g = sorted(got) if isinstance(got, (list, tuple, set)) else got
        w = sorted(want) if isinstance(want, (list, tuple, set)) else want
        if g == w:
            ok += 1
            print("[OK ] %s  实现=%s ｜ 预登记=%s" % (name, g, w))
        else:
            red += 1
            print("[RED] %s  实现=%s ｜ 预登记=%s" % (name, g, w))

    # ---- ① 判据 id 集合 ----
    pre_h = set(re.findall(r"\*\*(H[1-9])\*\*", pre))
    imp_h = set(re.findall(r"H[1-9]", re.findall(r'CRIT_IDS = \(([^)]*)\)', imp)[0]))
    chk("判据 id 集合", imp_h, pre_h)

    # ---- ② 形态集合 ----
    # ⚖ 预登记用**全角撇号**（′），实现用 ASCII（'）⇒ ⇒ 归一化后再比
    pre_forms = set(x.replace("′", "'") for x in
                    re.findall(r"\*\*(A′|B′|C′|D′|E′)[^*]*\*\*", pre))
    imp_forms = set(re.findall(r'FORM_\w+ = "(\w[\w\']*)"', imp))
    chk("形态集合", imp_forms, pre_forms)

    # ---- ③ 硬失败集合 ----
    pre_hard_raw = re.findall(r"E′（硬失败）[^=]*=\s*\{([^}]*)\}", pre)
    if not pre_hard_raw:
        _die("预登记里找不到「E′（硬失败）= {…}」这一行")
    pre_hard = set(re.findall(r"H[1-9]", pre_hard_raw[0]))
    imp_hard = set(re.findall(r"H[1-9]", re.findall(r'HARD_FAIL_IDS = \(([^)]*)\)', imp)[0]))
    chk("硬失败集合", imp_hard, pre_hard)

    # ---- ④ 闸门清单 ----
    pre_g = set("G0-" + d for d in re.findall(r"G0-(\d)", pre))
    graw = re.findall(r'GATE_IDS = tuple\("G0-%d" % i for i in range\(1,\s*(\d+)\)\)', imp)
    if not graw:
        _die("实现里找不到 GATE_IDS 的定义")
    # ⚖ Python 的 `range(1, n)` **上界不含** ⇒ ⇒ 闸门是 G0-1 .. G0-(n-1)
    imp_g = set("G0-%d" % i for i in range(1, int(graw[0])))
    chk("闸门清单（G0-1..G0-9）", imp_g, pre_g)

    # ---- ⑤ 读法清单 ----
    pre_r = set(re.findall(r"\*\*(R[1-6])\*\*", pre))
    imp_r = set(re.findall(r"R[1-6]", re.findall(r'READINGS = \(([^)]*)\)', imp)[0]))
    chk("读法清单", imp_r, pre_r)

    # ---- ⑥ 允许的加法对（⛔ **只**取 ALLOWED_SUMS 那个块 ⇒ ⇒ 别把 ALLOWED_PAIRS 也算进来）----
    # ⚖ 预登记那边：⛔ **不能**用「全文找 `x + y`」⇒ ⇒ 那会把 §1 的**禁止清单**里的
    #   「`c_upper + c_lower`」也算进来 ⇒ ⇒ 只认**登记行**（更正 ① 的 ①②③ 三条）。
    pre_sums = set()
    pre_pairs = set()
    reg = re.findall(r"^\s*[①②③]\s+`([a-z_]+)\s*([+↔])\s*([a-z_]+)`", pre, re.M)
    if not reg:
        _die("预登记里抠不到登记行（①/②/③ + `x + y`）")
    for a, op, b in reg:
        if op == "+":
            pre_sums.add((a, b))
            pre_sums.add((b, a))
        else:
            pre_pairs.add((a, b))
            pre_pairs.add((b, a))
    blk = imp[imp.index("ALLOWED_SUMS = frozenset(["):]
    blk = blk[:blk.index("])")]
    kind_map = {"C_UPPER": "c_upper", "C_LOWER": "c_lower",
                "DELTA_OBS": "delta_obs", "DELTA_CI_LO": "delta_ci_lo"}

    def _norm(pairs):
        out = set()
        for a, b in pairs:
            a = kind_map.get(a.replace("KIND_", ""), a.replace("KIND_", "").lower())
            b = kind_map.get(b.replace("KIND_", ""), b.replace("KIND_", "").lower())
            out.add((a, b))
        return out

    imp_sums = _norm(re.findall(r"\((KIND_\w+), KIND_(\w+)\)", blk))
    chk("允许的加法对（§1 ＋ 更正①）", imp_sums, pre_sums)
    pblk = imp[imp.index("ALLOWED_PAIRS = frozenset(["):]
    pblk = pblk[:pblk.index("])")]
    imp_pairs = _norm(re.findall(r"\((KIND_\w+), KIND_(\w+)\)", pblk))
    chk("允许的比较对（加法①）", imp_pairs, pre_pairs)

    # ---- ⑦ 禁止配对的分支代号（⚖ 预登记只点名**必须存在**的三条 ⇒ ⇒ 判「⊇」，
    #         实现里的**兜底代号**（PAIR / SUM-UNKNOWN）不算「预登记之外」）----
    pre_codes = set(re.findall(r"`(H8-KIND-[A-Z\-]+)`", pre))
    imp_codes = set(re.findall(r'"(H8-KIND-[A-Z\-]+):', imp))
    if pre_codes and pre_codes <= imp_codes:
        ok += 1
        print("[OK ] 禁止配对的分支代号 预登记要求的 %s 都在实现里 ｜ 实现另有兜底代号 %s"
              % (sorted(pre_codes), sorted(imp_codes - pre_codes) or "无"))
    else:
        red += 1
        print("[RED] 禁止配对的分支代号 预登记要求 %s ｜ 实现 %s（缺 %s）"
              % (sorted(pre_codes), sorted(imp_codes), sorted(pre_codes - imp_codes) or "无"))

    # ---- ⑧ 扫描维度 ----
    imp_lv = re.findall(r"WILSON_LEVELS = \(([^)]*)\)", imp)[0]
    chk("Wilson 档数", len([x for x in imp_lv.split(",") if x.strip()]), 3)
    imp_bv = re.findall(r'BASE_VARIANTS = \(([^)]*)\)', imp)[0]
    chk("基准变体数", len(re.findall(r'"([a-z_]+)"', imp_bv)), 3)

    # ---- ⑨ 级联的优先级顺序 ----
    pre_order = re.findall(r"级联顺序固定为 ([^）]+)", pre)
    pre_seq = re.findall(r"([A-E]′)", pre_order[0]) if pre_order else []
    body = imp[imp.index("def classify("):]
    body = body[:body.index("def judge(")]
    impl_seq = re.findall(r"return (FORM_\w+)", body)
    impl_seq = [s.replace("FORM_", "").replace("Ap", "A′").replace("Bp", "B′")
                .replace("Cp", "C′").replace("Dp", "D′").replace("Ep", "E′") for s in impl_seq]
    chk("级联顺序", impl_seq, pre_seq)

    # ---- ⑩ 联合置信（逐口径）· **真的把实现的公式拿出来算**（⛔ 不是恒真断言）----
    m = re.search(r"return (1\.0 - ALPHA_CI - \(1\.0 - level\))", imp)
    ma = re.search(r"ALPHA_CI = ([0-9.]+)", imp)
    if not m or not ma:
        red += 1
        print("[RED] 联合置信的实现公式 / ALPHA_CI 找不到")
    else:
        expr = m.group(1)
        alpha = float(ma.group(1))
        want = {95: 0.90, 90: 0.85, 99: 0.94}
        bad = []
        for lv, conf in want.items():
            got = eval(expr, {"ALPHA_CI": alpha, "level": lv / 100.0})  # noqa: S307
            if abs(got - conf) > TOL:
                bad.append("%d→%.4f（期望 %.4f）" % (lv, got, conf))
        if bad:
            red += 1
            print("[RED] 联合置信逐口径取值对不上：%s" % "；".join(bad))
        else:
            ok += 1
            print("[OK ] 联合置信逐口径取值（用实现自己的公式算）95→90%% ｜ 90→85%% ｜ 99→94%%")

    # ---- ⑪ 实现不得出现预登记之外的 id ----
    pre_ids = pre_h | pre_forms | pre_r | pre_g | pre_codes
    impl_ids = set(re.findall(r'"(H[0-9]+|G0-[0-9]+|R[0-9]+)"', imp))
    extra = {i for i in impl_ids if i not in pre_ids and i not in ("H0",)}
    chk("实现里没有预登记之外的 id", extra, set())

    print("")
    print("SPEC_OK=%d ｜ SPEC_RED=%d" % (ok, red))
    return 0 if red == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
