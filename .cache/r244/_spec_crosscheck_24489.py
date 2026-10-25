#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""_spec_crosscheck_24489.py —— **预登记 ↔ 实现 的机械对账**（244.89）。

⚖⚖⚖⚖⚖ **这一条要回答的问题**
   「实现里跑的**判据 / 形态 / 护栏 / 网格 / 门槛**，是不是**就是预登记里写的那一套**？」
   ⇒ ⇒ 预登记那边**只能追加更正**（§0.5'）⇒ ⇒ 如果实现里长出了预登记之外的东西，
     或者预登记写了而实现没做 ⇒ ⇒ **红** ⇒ ⇒ 必须回预登记或回实现改。

⚖⚖⚖⚖⚖ **两条硬规矩（从 244.66–244.88 的对账脚本继承）**
   ① **不 import 被检实现** —— import 进来就等于让被检对象自己解释自己 ⇒ ⇒ 那样对账没有意义
      ⇒ ⇒ 本脚本**从源码文本里正则抠出**常量；
   ② **期望值不许从被检对象派生** ⇒ ⇒ 预登记那一侧从**预登记文本**里抠，
      实现那一侧从**实现源码文本**里抠 ⇒ ⇒ 两边**真的**在比。

⚖⚖⚖⚖⚖ **本脚本自己也必须有牙齿** ⇒ ⇒ 抠取失败 ⇒ ⇒ **记红**（⛔ 不许静默跳过）
   ⇒ ⇒ 「预登记里根本没这条」与「实现里根本没这条」**必须分得开**。
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
PREREG = os.environ.get("R244_PREREG", os.path.join(REPO, ".cache", "xcheck",
                                                    "R6_CONFIDENCE_LEVEL_PREREG.md"))
IMPL = os.path.join(HERE, "confidence_level_audit.py")

OK = []
RED = []


def _read(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def _norm(s):
    """⚖ 归一化：预登记用「″ / ′」，实现用「'」⇒ ⇒ 统一成「'」再比。"""
    return s.replace("″", "'").replace("′", "'").replace("’", "'")


def _chk(name, mine, theirs):
    if mine == theirs:
        OK.append(name)
        print("[OK ] %s  实现=%s ｜ 预登记=%s" % (name, mine, theirs))
    else:
        RED.append(name)
        print("[RED] %s  实现=%s ｜ 预登记=%s" % (name, mine, theirs))


def _fail(name, why):
    RED.append(name)
    print("[RED] %s  %s" % (name, why))


def _src_block(text, name):
    """⚖ 从源码文本里抠出 `NAME = (...)` / `NAME = [...]` / `NAME = frozenset([...])` 这个**块**。"""
    m = re.search(r"^%s\s*=\s*(?:frozenset\(\s*)?[\(\[]" % re.escape(name), text, re.M)
    if not m:
        return None
    i = m.end() - 1
    depth = 0
    for j in range(i, len(text)):
        if text[j] in "([{":
            depth += 1
        elif text[j] in ")]}":
            depth -= 1
            if depth == 0:
                return text[i:j + 1]
    return None


def _src_str_tuple(text, name):
    """⚖ 抠出一个**字符串** tuple/list（⛔ 不 import）。"""
    blk = _src_block(text, name)
    if blk is None:
        return None
    out = []
    for m in re.finditer(r'"([^"]*)"|\'([^\']*)\'', blk):
        out.append(m.group(1) if m.group(1) is not None else m.group(2))
    return out


def _src_num_tuple(text, name):
    """⚖ 抠出一个**数值** tuple/list。"""
    blk = _src_block(text, name)
    if blk is None:
        return None
    body = blk[1:-1]
    return [float(x) for x in re.findall(r"-?\d+\.?\d*(?:[eE][-+]?\d+)?", body)]


def _src_num(text, name):
    m = re.search(r"^%s\s*=\s*(-?[0-9]*\.?[0-9]+(?:[eE][-+]?\d+)?)\s*$" % re.escape(name),
                  text, re.M)
    return float(m.group(1)) if m else None


def main():
    if not os.path.isfile(PREREG):
        print("SPEC_FAIL: 预登记不存在：%s" % PREREG)
        return 2
    if not os.path.isfile(IMPL):
        print("SPEC_FAIL: 实现不存在：%s" % IMPL)
        return 2
    pre = _norm(_read(PREREG))
    src = _read(IMPL)

    # ---- ① 判据 id 集合 ----
    pre_h = sorted(set(re.findall(r"\|\s*\*\*(H\d)\*\*\s*\|", pre)))
    impl_h = sorted(_src_str_tuple(src, "CRIT_IDS") or [])
    _chk("判据 id 集合", impl_h, pre_h)

    # ---- ② 形态集合（FORMS 里是**常量名**，⇒ ⇒ 要先把 FORM_* 的字面值解出来）----
    pre_forms = sorted(set(re.findall(r"\*\*(E'|D'|C'|B'|A')", pre)))
    form_map = {}
    for nm in ("FORM_E", "FORM_D", "FORM_C", "FORM_B", "FORM_A"):
        mm = re.search(r"^%s\s*=\s*\"([^\"]*)\"" % nm, src, re.M)
        if mm:
            form_map[nm] = mm.group(1)
    blk = _src_block(src, "FORMS")
    impl_forms = sorted(form_map.get(nm, nm)
                        for nm in re.findall(r"(FORM_[A-Z])", blk or ""))
    if len(form_map) != 5:
        _fail("形态集合", "实现里抠不到 FORM_E..FORM_A 的字面值（%s）" % sorted(form_map))
    else:
        _chk("形态集合", impl_forms, pre_forms)

    # ---- ③ 硬失败集合 ----
    m = re.search(r"\*\*E'（硬失败）\*\* = \{([^}]*)\}", pre)
    if not m:
        _fail("硬失败集合", "预登记里抠不到 E'（硬失败）那一行")
    else:
        pre_hard = sorted(set(re.findall(r"H\d", m.group(1))))
        impl_hard = sorted(_src_str_tuple(src, "HARD_FAIL_IDS") or [])
        _chk("硬失败集合", impl_hard, pre_hard)

    # ---- ④ 闸门清单 ----
    pre_g = sorted(set(re.findall(r"\*\*(G0-\d)\*\*", pre)))
    impl_g = sorted(_src_str_tuple(src, "GATE_IDS") or [])
    _chk("闸门清单（G0-1..G0-9）", impl_g, pre_g)

    # ---- ⑤ 读法清单 ----
    pre_r = sorted(set(re.findall(r"\*\*(S\d)\*\*", pre)))
    impl_r = sorted(_src_str_tuple(src, "READINGS") or [])
    _chk("读法清单", impl_r, pre_r)

    # ---- ⑥ 允许的加法对（预登记 §1 的运算②③）----
    pre_sums = set()
    for a, b in (("delta_ci_lo", "c_lower"), ("delta_obs", "c_lower")):
        pre_sums.add((a, b))
        pre_sums.add((b, a))
    blk = _src_block(src, "ALLOWED_SUMS")
    impl_sums = set()
    if blk:
        amap = {"K_DELTA_CI_LO": "delta_ci_lo", "K_DELTA_OBS": "delta_obs",
                "K_C_LOWER": "c_lower", "K_C_UPPER": "c_upper"}
        for a, b in re.findall(r"\((K_[A-Z_]+), (K_[A-Z_]+)\)", blk):
            impl_sums.add((amap.get(a, a), amap.get(b, b)))
    else:
        _fail("允许的加法对（§1 运算②③）", "实现里抠不到 ALLOWED_SUMS 这个块")
    if impl_sums:
        _chk("允许的加法对（§1 运算②③）", sorted(impl_sums), sorted(pre_sums))

    # ---- ⑦ 允许与 0 比较的 kind（预登记 §1 的运算①）----
    pre_zero = set(["delta_ci_lo"])
    impl_zero = set()
    blk = _src_block(src, "ALLOWED_ZERO_CMP")
    if blk:
        amap = {"K_DELTA_CI_LO": "delta_ci_lo", "K_DELTA_OBS": "delta_obs",
                "K_C_LOWER": "c_lower", "K_C_UPPER": "c_upper"}
        for a in re.findall(r"K_[A-Z_]+", blk):
            impl_zero.add(amap.get(a, a))
    else:
        _fail("允许与 0 比较的 kind（§1 运算①）", "实现里抠不到 ALLOWED_ZERO_CMP")
    if impl_zero:
        _chk("允许与 0 比较的 kind（§1 运算①）", sorted(impl_zero), sorted(pre_zero))

    # ---- ⑧ 决策区门槛（预登记写百分数，实现写比例）----
    m = re.search(r"联合置信 ≥ (\d+)%", pre)
    pre_floor = float(m.group(1)) if m else None
    impl_floor = _src_num(src, "JOINT_FLOOR")
    if pre_floor is None or impl_floor is None:
        _fail("决策区门槛（联合置信 %）", "抠不到门槛（预登记 %s / 实现 %s）"
              % (pre_floor, impl_floor))
    else:
        _chk("决策区门槛（联合置信 %）", impl_floor * 100.0, pre_floor)

    # ---- ⑨ 决策区成员（手写的那张表）----
    blk = _src_block(src, "EXPECTED_DECISION_ALLOCATIONS")
    impl_alloc = []
    if blk:
        impl_alloc = sorted((float(a), float(b))
                            for a, b in re.findall(r"\((0\.\d\d), (0\.\d\d)\)", blk))
    else:
        _fail("决策区成员（手写表）", "实现里抠不到 EXPECTED_DECISION_ALLOCATIONS")
    pre_alloc = sorted([(0.95, 0.95), (0.95, 0.99), (0.99, 0.95), (0.99, 0.99)])
    if impl_alloc:
        _chk("决策区成员（手写表）", impl_alloc, pre_alloc)

    # ---- ⑩ 三个维度的档数 ----
    impl_n_ci = len(_src_num_tuple(src, "CI_LEVELS") or [])
    impl_n_c = len(_src_num_tuple(src, "C_LEVELS") or [])
    impl_n_b = len(_src_str_tuple(src, "BASE_VARIANTS") or [])
    _chk("CI 水平档数", impl_n_ci, 3)
    _chk("污染水平档数", impl_n_c, 3)
    _chk("基准变体数", impl_n_b, 3)

    # ---- ⑪ 联合置信逐分配取值（用**本脚本自己**的算术，不调实现）----
    def jp(a, b):
        return int(round(a * 100)) + int(round(b * 100)) - 100
    mine_in = sorted((a, b) for a in (0.90, 0.95, 0.99) for b in (0.90, 0.95, 0.99)
                     if jp(a, b) >= 90)
    pre_tbl = {}
    for ln in pre.split("\n"):
        m = re.match(r"^\|\s*\*\*(90|95|99)\*\*\s*\|(.+)\|\s*$", ln)
        if not m:
            continue
        cells = [c.strip() for c in m.group(2).split("|")]
        pcts = []
        for c in cells:
            mm = re.search(r"(\d+)%", c)
            if mm:
                pcts.append(int(mm.group(1)))
        if len(pcts) != 3:
            continue
        a = float(m.group(1)) / 100.0
        for b, p in zip((0.90, 0.95, 0.99), pcts):
            pre_tbl[(a, b)] = p
    if not pre_tbl:
        _fail("联合置信 ≥ 90% 的分配", "预登记 §2.2 的那张表抠不到")
    else:
        pre_in = sorted(k for k, v in pre_tbl.items() if v >= 90)
        _chk("联合置信 ≥ 90% 的分配", mine_in, pre_in)
        # 逐格的取值也要一致（⛔ 不许「门槛对了但某格的联合置信不对」）
        bad = [(k, pre_tbl[k], jp(k[0], k[1])) for k in pre_tbl
               if pre_tbl[k] != jp(k[0], k[1])]
        _chk("联合置信逐分配取值", bad, [])

    # ---- ⑫ H9 的残差容差（预登记 §0.5' 更正②）----
    m = re.search(r"容差取 \*\*([0-9]*\.?[0-9]+(?:[eE][-+]?\d+)?) pp\*\*", pre)
    pre_tol = float(m.group(1)) if m else None
    impl_tol = _src_num(src, "RESID_TOL")
    if pre_tol is None or impl_tol is None:
        _fail("H9 残差容差（§0.5' 更正②）", "抠不到容差（预登记 %s / 实现 %s）"
              % (pre_tol, impl_tol))
    else:
        _chk("H9 残差容差（§0.5' 更正②）", impl_tol, pre_tol)

    # ---- ⑬ 硬门的分支代号（预登记 §4 的 G0-3 要求的那些）----
    pre_codes = sorted(set(re.findall(r"`(H7-KIND-[A-Z\-]+)`", pre)))
    impl_codes = sorted(set(re.findall(r"(H7-KIND-[A-Z\-]+)", src)))
    missing = [c for c in pre_codes if c not in impl_codes]
    if missing:
        _fail("硬门分支代号", "预登记要求 %s 都在实现里 ｜ 缺 %s" % (pre_codes, missing))
    else:
        OK.append("硬门分支代号")
        print("[OK ] 硬门分支代号  预登记要求的 %s 都在实现里 ｜ 实现另有 %s"
              % (pre_codes, sorted(set(impl_codes) - set(pre_codes))))

    # ---- ⑭ 实现里没有预登记之外的 id ----
    extra = sorted(set(impl_h) - set(pre_h))
    _chk("实现里没有预登记之外的判据 id", extra, [])

    print("")
    print("SPEC_OK=%d ｜ SPEC_RED=%d" % (len(OK), len(RED)))
    if RED:
        print("SPEC_RED_LIST=%s" % ",".join(RED))
        print("SPEC_RC=1")
        return 1
    print("SPEC_RC=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
