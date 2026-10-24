#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⚖ **244.84 的「实现 SPEC ↔ 预登记 Q 表」逐条对账**（⛔ 零 GPU、零 bpath、纯文本）。

**为什么要有这个**：预登记开篇纪律 ① 写的是「**口径只从预登记读，⛔ 不在实现里另立口径**」。
⇒ ⇒ 但「有没有人偷偷在实现里另立口径」这件事，**光靠人读**是**验不到**的
⇒ ⇒ 本脚本把这条纪律做成**可判读、能红**的机器检查。

⚖ **它做什么**：
   ① 从 `.cache/xcheck/R6_ALIGNMENT_DISTRIBUTION_PREREG.md` 的 §2 表里**逐条抠** Q1–Q15 的值；
   ② 从 `alignment_distribution_audit.py` 的 `SPEC` 字典里抠**同名口径**的值；
   ③ **逐条比对** ⇒ ⇒ 任何一条对不上 ⇒ ⇒ 判红、退出码非 0；
   ④ **自证能红**：把 SPEC 里某个值改掉再比一次 ⇒ ⇒ 必须判红 ⇒ ⇒ 证明它**不是恒绿的**。

⚖ **它不做什么**（⛔ 边界）：
   · 它**不**重算任何统计量（那些是 `alignment_distribution_audit.py` 的活）；
   · 它**不**代替 H1–H13 的硬判据；
   · 它只回答一件事：**「实现里用的那个数，和预登记写死的那个数，是同一个吗？」**
"""

import ast
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
PREREG = os.path.join(REPO, ".cache", "xcheck", "R6_ALIGNMENT_DISTRIBUTION_PREREG.md")
IMPL = os.path.join(HERE, "alignment_distribution_audit.py")

# ⚖ Q 号 → (SPEC 键, 从预登记那一格里怎么取值, 说明)
#   取值函数签名：prereg_cell(str) -> python 值（抛异常表示「这条没法机械比」）
def _strip_code(s):
    """把 `xxx` 里的内容取出来（预登记的表格里值都用反引号包着）。"""
    s = s.strip()
    m = re.match(r"^`(.+)`$", s)
    return m.group(1) if m else s


def _clean(s):
    """去掉加粗标记与空白。"""
    return re.sub(r"\s+", " ", s.replace("**", "")).strip()


def _first_num(s):
    """格子里**第一个**数字（预登记的口径值总是写在最前面）。"""
    m = re.search(r"[-+]?[0-9]+(?:\.[0-9]+)?", _clean(s))
    if not m:
        raise ValueError("格子里没有数字：%r" % s)
    return float(m.group(0))


def _num_after_le(s):
    """「… ≤ 0.05」这种 ⇒ ⇒ 取 **≤ 之后**的那个数（⛔ 不能取第一个，"
    "「1/√d」里的 1 会串位）。"""
    c = _clean(s)
    i = c.find("≤")
    if i < 0:
        raise ValueError("格子里没有「≤」：%r" % s)
    m = re.search(r"[-+]?[0-9]+(?:\.[0-9]+)?", c[i:])
    if not m:
        raise ValueError("「≤」之后没有数字：%r" % s)
    return float(m.group(0))


def _backtick_num(s):
    """反引号里那个数（例：`` `z_T ≥ 2` ``）。"""
    m = re.search(r"`([^`]+)`", s)
    if not m:
        raise ValueError("格子里没有反引号：%r" % s)
    mm = re.search(r"[-+]?[0-9]+(?:\.[0-9]+)?", m.group(1))
    if not mm:
        raise ValueError("反引号里没有数字：%r" % s)
    return float(mm.group(0))


def _num(s):
    return _first_num(s)


def _int(s):
    return int(_first_num(s))


def _str(s):
    return _strip_code(s)


def _stem(s):
    """文件名：**去掉扩展名**再比（预登记写 `w_p2a.npy`，实现存的是 `w_p2a`）。"""
    v = _strip_code(s)
    return v[:-4] if v.endswith(".npy") else v


def _bool(s):
    t = _strip_code(s).lower()
    if t in ("true", "是", "对"):
        return True
    if t in ("false", "否", "错"):
        return False
    raise ValueError("不是布尔：%r" % s)


def _members(s):
    """Q2：`` `w_L19_m0` `w_L19_m1` ... ``（多个反引号项，空格分隔）。"""
    return re.findall(r"`([^`]+)`", s)


def _marker_ids(s):
    """Q7：`` `marker_ids`（7 个） `` ⇒ ⇒ 取预登记里**列出的那 7 个数字**。"""
    return [int(x) for x in re.findall(r"\b(\d{3,6})\b", s)]


def _stratum_A(s):
    """Q12：分层 A ＝ `w_L19_m0` `w_L19_m1` `w_real` `w_t1`（同 npz …）"""
    head = s.split("（")[0]
    return re.findall(r"`([^`]+)`", head)


# ⚖ 预登记 §2 的表头是：| **Q1** | 剂量批用的 w | `w_p2a.npy` | sidecar … |
#   ⇒ ⇒ 第 2 格是**口径名**、第 3 格是**值**、第 4 格是**出处**
Q_MAP = [
    ("Q1",  "dose_w",          _stem,      "剂量批用的 w"),
    ("Q2",  "members",         _members,   "类成员（6 把）"),
    ("Q3",  "dim",             _int,       "向量维度 d"),
    ("Q5",  "rand_seed",       _int,       "rand 臂种子"),
    ("Q6",  "train_seed",      _int,       "训练种子"),
    ("Q8",  "layer",           _int,       "注入层"),
    ("Q9",  "ref_K",           _int,       "参考分布规模 K"),
    ("Q10", "ref_sd_rel_tol",  _num_after_le, "参考分布 sd 校验上限"),
    ("Q12", "stratum_A",       _stratum_A, "分层 A"),
    ("Q13", "z_threshold",     _backtick_num, "判决规则 z 阈值"),
    ("Q14", "fpr_max",         _num,       "规则假阳性率上限"),
    ("Q15", "ref_class_seed_lo", _int,     "类级零分布种子区间起点"),
]

# ⚖ 那些**没法逐字机械比**的口径（要人工读）⇒ ⇒ 明确列出来，⛔ 不假装比过了
MANUAL = {
    "Q4": "rand 臂随机向量的**构造式**（default_rng(0) → standard_normal → 归一化 → ×‖w‖，float32 口径）"
          " ⇒ ⇒ 不是一个标量，由实现里 H3 的源码比对负责",
    "Q7": "7 个 marker 的**具体 id 列表** ⇒ ⇒ 预登记的 Q7 只写了「7 个 marker，6 把逐个相同」"
          "⇒ ⇒ ⛔ **预登记里根本没列那 7 个数** ⇒ ⇒ 真正的对照源是**探针源码**的 `MARKER_IDS`"
          "（由实现里 H2 的「跨来源那一半」逐个比）⇒ ⇒ 这里**不假装**比过了",
    "Q11": "零假设的**语义**（r 重抽、v 不动）⇒ ⇒ 不是一个标量",
}


def _read(p):
    with io.open(p, encoding="utf-8", newline="") as fh:
        return fh.read()


def _prereg_q(prereg_text):
    """抠出 Q1–Q15 的值（从 §2 那张表）。"""
    out = {}
    for line in prereg_text.split("\n"):
        m = re.match(r"^\|\s*\*\*(Q\d+)\*\*\s*\|(.*?)\|(.*?)\|(.*?)\|\s*$", line)
        if not m:
            continue
        q, _name, val, _src = m.group(1), m.group(2), m.group(3), m.group(4)
        out[q] = val
    return out


def _impl_spec(impl_text):
    """从实现里抠出 SPEC 字典（⛔ 用 ast，⛔ 不执行被测代码）。"""
    tree = ast.parse(impl_text, IMPL)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "SPEC":
                    return ast.literal_eval(node.value)
    raise SystemExit("⛔ 实现里抠不到 SPEC 字典 ⇒ 中止")


def _norm(v):
    """把两边都归一到可比的形态。"""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, (list, tuple)):
        return [_norm(x) for x in v]
    return v


def compare(prereg_text, impl_text):
    """⇒ ⇒ 返回 (结果列表, 是否全绿)"""
    qv = _prereg_q(prereg_text)
    spec = _impl_spec(impl_text)
    res = []
    ok = True
    for q, key, fn, desc in Q_MAP:
        if q not in qv:
            res.append((q, key, False, "⛔ 预登记里抠不到 %s 这一行" % q))
            ok = False
            continue
        if key not in spec:
            res.append((q, key, False, "⛔ 实现 SPEC 里没有 `%s`" % key))
            ok = False
            continue
        try:
            want = fn(qv[q])
        except Exception as e:  # noqa: BLE001
            res.append((q, key, False, "⛔ 取值失败：%s" % e))
            ok = False
            continue
        got = spec[key]
        same = (_norm(want) == _norm(got))
        if not same:
            ok = False
        res.append((q, key, same, "预登记 %r ｜ 实现 %r%s"
                    % (want, got, "" if same else "　⛔ **不一致**")))
    return res, ok


def main():
    prereg_text = _read(PREREG)
    impl_text = _read(IMPL)
    res, ok = compare(prereg_text, impl_text)

    print("──── 「实现 SPEC ↔ 预登记 §2」逐条对账 ────")
    for q, key, good, detail in res:
        print("  %s %-4s %-20s %s" % ("✅" if good else "⛔", q, key, detail))
    print("  ⚖ **不能机械比的**（⛔ 不假装比过了）：")
    for q, why in sorted(MANUAL.items()):
        print("     %-4s %s" % (q, why))

    if not ok:
        print()
        print("⛔ 实现里有口径与预登记**对不上** ⇒ ⇒ **不许**继续（⛔ 口径真相源是预登记）")
        return 1

    # ---- 自证：改掉一个值 ⇒ ⇒ 必须判红 ⇒ ⇒ 证明它**不是恒绿的**
    print()
    print("──── 自证：把 SPEC 的 `z_threshold` 改成 1.5 再比一次（必须判红）────")
    bad_impl = impl_text.replace('"z_threshold": 2.0,', '"z_threshold": 1.5,', 1)
    if bad_impl == impl_text:
        print("  ⛔ 改不动 `z_threshold` 这一行 ⇒ ⇒ 没法自证 ⇒ 中止")
        return 1
    _res2, ok2 = compare(prereg_text, bad_impl)
    print("  %s 篡改后判红 = %s ⇒ ⇒ %s"
          % ("✅" if (not ok2) else "⛔", (not ok2),
             "这条检查**不是恒绿的**（有牙齿）" if not ok2 else "⛔它居然还绿 ⇒ 不可用"))
    if ok2:
        return 1

    print()
    print("✅ 实现 SPEC 与预登记 §2 **逐条一致**（%d 条机械比 + %d 条人工）"
          % (len(Q_MAP), len(MANUAL)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
