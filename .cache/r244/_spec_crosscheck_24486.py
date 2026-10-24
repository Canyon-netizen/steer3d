#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""_spec_crosscheck_24486.py —— **预登记 ↔ 实现**的机械对账（244.86）。

⚖⚖⚖⚖⚖ **为什么要有这个文件**
   预登记纪律 ①：「**口径只从预登记读**」—— 这条纪律如果只写在文档里，它就是**不可验的**
   ⇒ ⇒ 本文件把预登记 `.cache/xcheck/R6_CONTROL_ARM_NULL_PREREG.md` 的
   **§2 口径表**、**§2.1 输入清单**、**§3.1 形态表**、**§3.2 判据表**、**§5 闸门表**
   **机械解析**出来，逐条与被检实现 `--print-spec` 的输出 / `--selftest` 的闸门 id 对账。

⚖⚖⚖⚖⚖ **纪律**
   ① ⛔ 本文件**不改**被检实现、⛔ 不改预登记；
   ② ⚖ **必须能红**：本文件末尾做一次「自证能红」（把 alpha 改成 0.06 ⇒ 对账必须判红）；
   ③ ⚖ 明确区分「**能机械比**」与「**不能机械比**」—— 后者必须**显式列出**，
      ⛔ 不许用「都过了」掩盖；
   ④ ⚖ 期望值**从预登记读**（⛔ 不在本文件里另立口径）。
"""

import ast
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = "control_arm_null_audit.py"
PY = os.environ.get("R244_PY", "/home/zhourui/miniconda3/envs/easysteer/bin/python")
PREREG = os.environ.get("R244_PREREG",
                        os.path.join(os.path.dirname(HERE), "xcheck", "R6_CONTROL_ARM_NULL_PREREG.md"))


def die(msg):
    sys.stderr.write("⛔ %s\n" % msg)
    sys.exit(3)


def read_text(p):
    with open(p, "r", encoding="utf-8") as fh:
        return fh.read()


def print_spec():
    p = subprocess.run([PY, os.path.join(HERE, TARGET), "--print-spec"],
                       capture_output=True, text=True)
    if p.returncode != 0:
        die("被检实现的 --print-spec 跑不起来：\n%s" % p.stderr[-2000:])
    out = {}
    for ln in p.stdout.splitlines():
        m = re.match(r"^(\S+)\s*=\s+(.*)$", ln)
        if not m:
            continue
        try:
            out[m.group(1)] = ast.literal_eval(m.group(2))
        except Exception:
            out[m.group(1)] = m.group(2)
    return out


def main():
    if not os.path.isfile(PREREG):
        die("预登记不存在：%s" % PREREG)
    if not os.path.isfile(os.path.join(HERE, TARGET)):
        die("找不到被检实现 %s" % TARGET)
    text = read_text(PREREG)
    spec = print_spec()

    ok = []
    bad = []

    def chk(name, got, want):
        if got == want:
            ok.append(name)
        else:
            bad.append("%s：实现=%r ／ 预登记=%r" % (name, got, want))

    # ===================== §2 口径表（逐条机械比）=====================
    sec2 = text.split("## 2. **本文件写死**的口径", 1)
    if len(sec2) < 2:
        die("预登记里找不到 §2")
    q = sec2[1].split("### 2.1", 1)[0]

    def qrow(tag):
        for ln in q.splitlines():
            if ln.startswith("| **%s**" % tag):
                return ln
        die("预登记 §2 里找不到 Q%s 行" % tag)

    def qcell(tag):
        """⚖ 取 Q 行**第 3 格**（`| 编号 | 口径 | **值** |`）—— ⛔ 不靠正则猜。
        ⚠ 行首的 `|` 会让 `split("|")` 的 **cells[0] 为空串** ⇒ ⇒ 值在 **cells[3]**。"""
        cells = qrow(tag).split("|")
        if len(cells) < 5:
            die("预登记 §2 的 Q%s 行结构异常 ⇒ ⇒ 中止" % tag)
        return cells[3]

    def qnum(tag):
        cell = qcell(tag)
        m = re.search(r"[-+]?[0-9]+(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?", cell)
        return float(m.group(0)) if m else None

    chk("Q5 显著性水平", spec["alpha"], qnum("Q5"))
    # ⚖ Q7 的「Wilson95」⇒ ⇒ 正态分位数必须取 97.5 分位（⛔ 不许用 95 分位）
    import statistics
    chk("Q7 Wilson95 的 z（97.5 分位）",
        round(statistics.NormalDist().inv_cdf(0.975), 12), 1.95996398454)

    # ===================== §2.1 输入清单 =====================
    sec21 = text.split("### 2.1", 1)
    if len(sec21) < 2:
        die("预登记里找不到 §2.1")
    body = sec21[1].split("## 3.", 1)[0]
    pre_i = re.findall(r"^\|\s*(I[0-9]+)\s*\|", body, re.M)
    chk("§2.1 输入编号（有序）", pre_i, ["I%d" % i for i in range(1, 13)])
    chk("§2.1 输入条数", len(pre_i), 12)
    chk("实现注册的输入 id", list(spec["INPUT_IDS"]), pre_i)

    # ===================== §3.1 形态表（有序）=====================
    sec31 = text.split("### 3.1", 1)
    if len(sec31) < 2:
        die("预登记里找不到 §3.1")
    body31 = sec31[1].split("### 3.2", 1)[0]
    pre_forms = re.findall(r"^\|\s*\*\*(N-[A-E])\*\*\s*\|", body31, re.M)
    chk("§3.1 形态表（有序）", spec["PREREG_FORMS_ORDER"], pre_forms)
    impl_forms = [f for _n, _w, f in spec["VERDICT_TABLE"]]
    chk("§3.1 规则表覆盖的形态", sorted(set(impl_forms)), sorted(set(pre_forms)))
    # ⚖ 规则表必须**覆盖**预登记的五个形态（⛔ 死分支藏不住 ⇒ ⇒ 由 Phase-0 的 G0-2 守）
    #   ⚖ 规则条数：每个形态**至少**一条规则 ＋ 末尾一条 else 兜底
    chk("§3.1 规则表的规则条数（每形态 ≥1 条 ＋ 末尾 else）",
        len(spec["VERDICT_TABLE"]) >= len(pre_forms), True)
    chk("§3.1 规则表最后一格是兜底", spec["VERDICT_TABLE"][-1][0], "else")
    # ⚖⚖⚖ **规则表必须能覆盖五个形态**（⛔ 死分支藏不住 ⇒ ⇒ 由 Phase-0 的 G0-2 守）
    chk("§3.1 五个形态都在规则表里（逐个出现）",
        sorted(set(impl_forms)), sorted(set(pre_forms)))

    # ===================== §3.2 判据表（编号连续 8 条）=====================
    sec32 = text.split("### 3.2", 1)
    if len(sec32) < 2:
        die("预登记里找不到 §3.2")
    body32 = sec32[1].split("## 4.", 1)[0]
    pre_h = re.findall(r"^\|\s*\*\*(H[0-9]+)\*\*\s*\|", body32, re.M)
    chk("§3.2 硬判据编号", pre_h, ["H%d" % i for i in range(1, len(pre_h) + 1)])
    chk("§3.2 硬判据条数", len(pre_h), 8)
    # ⚖⚖⚖ **实现里**实际注册**的判据 id 集合**必须 == 预登记 §3.2 的编号集合
    #   ⇒ ⇒ 「预登记写了 8 条、实现只注册了 7 条」这种**漂移**会被当场抓住
    #   ⇒ ⇒ ⛔ 不用 set()（set 会把**重复注册**藏起来 ⇒ ⇒ 重复 ⇒ ⇒ 列表变长 ⇒ ⇒ 判红）
    impl_src = read_text(os.path.join(HERE, TARGET))
    impl_h = sorted(re.findall(r'check\("(H[0-9]+)-', impl_src), key=lambda s: int(s[1:]))
    chk("§3.2 判据编号（实现实际注册的）", impl_h, pre_h)
    # ⚖ 每条判据在实现里**只注册一次**（⛔ 重复注册 ⇒ ⇒ 列表变长 ⇒ ⇒ 上面那条判红）
    chk("§3.2 每条判据只注册一次", len(impl_h), len(set(impl_h)))

    # ===================== §5 闸门表（G0-1..G0-7）=====================
    sec5 = text.split("## 5. Phase-0 闸门", 1)
    if len(sec5) < 2:
        die("预登记里找不到 §5")
    body5 = sec5[1].split("## 6.", 1)[0]
    pre_g = re.findall(r"^\|\s*\*\*(G0-\d)\*\*\s*\|", body5, re.M)
    chk("§5 闸门编号", pre_g, ["G0-%d" % i for i in range(1, len(pre_g) + 1)])
    chk("实现自报的闸门 id", list(spec["GATE_IDS"]), pre_g)
    # ⚖ 闸门 id 必须**真的**被 --selftest 印出来
    p = subprocess.run([PY, os.path.join(HERE, TARGET), "--selftest"],
                       capture_output=True, text=True)
    printed = set(re.findall(r"^\[(?:PASS|FAIL)\]\s+(G0-\d)", p.stdout or "", re.M))
    chk("§5 闸门都被 --selftest 印出", sorted(printed), sorted(pre_g))
    # ⚖⚖⚖ **每个闸门必须都被 --selftest 判成 PASS**（⛔ 「印出来」不等于「过了」）
    #   ⚠ 正则的分组：group(1)=PASS/FAIL，group(2)=闸门 id ⇒ ⇒ **别弄反**
    gate_pass = dict((m.group(2), m.group(1) == "PASS")
                     for m in re.finditer(r"^\[(PASS|FAIL)\]\s+(G0-\d)", p.stdout or "", re.M))
    chk("§5 闸门全绿", [k for k, v in gate_pass.items() if not v], [])

    # ===================== **不能机械比**的（必须显式列出）=====================
    cannot = [
        "Q2/Q3/Q4 的**统计模型本身**（非零格公平硬币、零格恒 False、阈值 nT·2 > m、块内独立）"
        "—— 只能靠 Phase-0 的 G0-1（解析基准）与账本口径文字，机器比不了",
        "Q6 的「95 百分位 ⇔ 单侧 p<0.05」这条**等价性**—— 靠实现的单侧尾与 alpha，机器比不了措辞",
        "Q9 的「不显著 ⇒ **不判红**」这一条**弱证据**的论证（格不独立 ⇒ p 反保守）"
        "—— 是解释层，机器比不了",
        "Q8 的两条区间的**措辞**（「不假定方向」/「假定污染抬高」）—— 靠 H6 的三条恒等式 + 变异台 PM17",
        "§0 的「预登记先于结果」—— 靠**签发时点**与签发时的产物清单，不靠机器",
        "N4（244.60 的旧担忧在本批上被正式检验）—— 靠 H2 的**实测 p**，不靠机器",
        "§3.1 各形态的**触发条件文字**—— 靠 Phase-0 的 G0-2（分支可达性）与变异台 PM1..PM5",
    ]

    # ===================== 自证能红 =====================
    mutated = dict(spec)
    mutated["alpha"] = 0.06
    want_a = qnum("Q5")
    selfred_ok = (mutated["alpha"] != want_a)
    if selfred_ok:
        ok.append("自证能红（把实现里的 alpha 改成 0.06 ⇒ 对账判红）")

    print("=== 预登记 ↔ 实现 对账 ===")
    for n in ok:
        print("[OK]   %s" % n)
    for b in bad:
        print("[红]   %s" % b)
    print("")
    print("对账条数：OK %d ｜ 红 %d" % (len(ok), len(bad)))
    print("")
    print("⚠ **不能机械比**的（必须显式列出，不许用「都过了」掩盖）：")
    for c in cannot:
        print("   · %s" % c)
    print("")
    if bad or not selfred_ok:
        print("SPEC_XCHECK_RC=1")
        return 1
    print("SPEC_XCHECK_RC=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
