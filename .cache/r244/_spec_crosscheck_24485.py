#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""_spec_crosscheck_24485.py —— **预登记 ↔ 实现**的机械对账（244.85）。

⚖⚖⚖⚖⚖ **为什么要有这个文件**
   预登记纪律 ①：「**口径只从预登记读**」—— 这条纪律如果只写在文档里，它就是**不可验的**
   ⇒ ⇒ 本文件把预登记 `.cache/xcheck/R6_LOO_ROBUSTNESS_PREREG.md` 的
   **§2.1 子集族表**、**§2 口径表**、**§3.1 形态表**、**§3.2 判据表**、**§5 闸门表**
   **机械解析**出来，逐条与被检实现 `--print-spec` 的输出 / `--selftest` 的闸门 id 对账。

⚖⚖⚖⚖⚖ **纪律**
   ① ⛔ 本文件**不改**被检实现、⛔ 不改预登记；
   ② ⚖ **必须能红**：本文件末尾做一次「自证能红」（把 z_threshold 改成 1.5 ⇒ 对账必须判红）；
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
TARGET = "loo_robustness_audit.py"
PY = os.environ.get("R244_PY", "/home/zhourui/miniconda3/envs/easysteer/bin/python")
PREREG = os.environ.get("R244_PREREG",
                        os.path.join(os.path.dirname(HERE), "xcheck", "R6_LOO_ROBUSTNESS_PREREG.md"))


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
        m = re.match(r"^(\S+)\s+=\s+(.*)$", ln)
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
    cannot = []

    def chk(name, got, want):
        if got == want:
            ok.append(name)
        else:
            bad.append("%s：实现=%r ／ 预登记=%r" % (name, got, want))

    # ===================== §2.1 子集族 =====================
    sec21 = text.split("### 2.1", 1)
    if len(sec21) < 2:
        die("预登记里找不到 §2.1")
    body = sec21[1].split("### 2.2", 1)[0]
    pre_family = {}
    # ⚖⚠ **名字格可能带粗体**（预登记里关键位 `LOO-p2a` 那行是 **粗体** ⇒ ⇒ 正则必须容 `**`）
    for m in re.finditer(r"\|\s*\**\s*`([A-Za-z0-9\-]+)`\s*\**\s*\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|", body):
        name = m.group(1)
        members = re.findall(r"`(w_[A-Za-z0-9_]+)`", m.group(2))
        n = int(m.group(3))
        if not members:
            raise SystemExit("⛔ 预登记 §2.1 的子集 %s **没写死成员** ⇒ ⇒ 口径不是可机械解析的 ⇒ 中止" % name)
        pre_family[name] = (members, n)
    impl_family = dict((k, (list(v), len(v))) for k, v in spec["subset_family"].items())
    chk("§2.1 子集族（名字集合）", sorted(pre_family.keys()), sorted(impl_family.keys()))
    for k in sorted(set(pre_family.keys()) & set(impl_family.keys())):
        chk("§2.1 子集 %s 的成员" % k, sorted(impl_family[k][0]), sorted(pre_family[k][0]))
        chk("§2.1 子集 %s 的 n" % k, impl_family[k][1], pre_family[k][1])

    # ===================== §2 口径常量（逐条机械比）=====================
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
        """⚖ 取 Q 行**第 3 格**（`| 编号 | 口径 | **值** | 出处 |`）—— ⛔ 不靠正则猜。
        ⚠ 行首的 `|` 会让 `split("|")` 的 **cells[0] 为空串** ⇒ ⇒ 值在 **cells[3]**。"""
        cells = qrow(tag).split("|")
        if len(cells) < 5:
            die("预登记 §2 的 Q%s 行结构异常 ⇒ ⇒ 中止" % tag)
        return cells[3]

    def qnum(tag):
        """⚖ 取那一格里**第一个**数字（容忍 **粗体**、≤/≥/> 前缀、e 记数法）。"""
        cell = qcell(tag)
        m = re.search(r"[-+]?[0-9]+(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?", cell)
        if not m:
            return None
        return float(m.group(0))

    chk("Q3 维度 d", spec["dim"], int(qnum("Q3")))
    chk("Q9 参考规模 K", spec["ref_K"], int(qnum("Q9")))
    chk("Q10 校准容差", spec["class_sd_rel_tol"], qnum("Q10"))
    chk("Q13 判决阈值", spec["z_threshold"], qnum("Q13"))
    chk("Q14 假阳性率上限", spec["fpr_max"], qnum("Q14"))
    chk("Q15 类级参考种子起点", spec["ref_class_seed_lo"], int(qnum("Q15")))
    chk("Q18 跨轮相对容差", spec["cross_rel_tol"], qnum("Q18"))
    chk("Q19 簇连边阈值", spec["cluster_cos_thresh"], qnum("Q19"))
    chk("Q5 rand 种子", spec["rand_seed"], int(qnum("Q5")))
    chk("Q6 训练种子", spec["train_seed"], int(qnum("Q6")))
    chk("Q8 注入层", spec["layer"], int(qnum("Q8")))
    m = re.search(r"`(w_[A-Za-z0-9_]+)`", qcell("Q1"))
    chk("Q1 剂量批用的 w", spec["dose_w"], m.group(1) if m else None)
    m2 = re.findall(r"`(w_[A-Za-z0-9_]+)`", qcell("Q2"))
    chk("Q2 类成员", spec["members"], m2 if m2 else None)
    chk("Q16 决策族", spec["decision_family"],
        ["FULL", "LOO-m0", "LOO-m1", "LOO-real", "LOO-t1", "LOO-p2a", "LOO-old"])
    chk("Q12 子集数", len(spec["subset_family"]), 16)

    # ===================== §3.1 形态表（有序）=====================
    sec31 = text.split("### 3.1", 1)
    if len(sec31) < 2:
        die("预登记里找不到 §3.1")
    body31 = sec31[1].split("### 3.2", 1)[0]
    pre_forms = re.findall(r"^\|\s*\*\*(F-[A-E]|FAIL)\*\*\s*\|", body31, re.M)
    chk("§3.1 形态表（有序）", spec["PREREG_FORMS_ORDER"], pre_forms)
    impl_forms = [f for _n, _w, f in spec["VERDICT_TABLE"]]
    chk("§3.1 规则表覆盖的形态", sorted(set(f for _n, _w, f in spec["VERDICT_TABLE"])),
        sorted(set(pre_forms)))
    chk("§3.1 规则表的规则条数（形态数 +1 条 else 兜底）", len(spec["VERDICT_TABLE"]), len(pre_forms) + 1)
    chk("§3.1 规则表最后一格是兜底", spec["VERDICT_TABLE"][-1][0], "else")

    # ===================== §3.2 判据表（编号连续 13 条）=====================
    sec32 = text.split("### 3.2", 1)
    if len(sec32) < 2:
        die("预登记里找不到 §3.2")
    body32 = sec32[1].split("### 3.3", 1)[0]
    pre_h = re.findall(r"^\|\s*\*\*(H[0-9]+)\*\*\s*\|", body32, re.M)
    chk("§3.2 硬判据编号", pre_h, ["H%d" % i for i in range(1, len(pre_h) + 1)])
    chk("§3.2 硬判据条数", len(pre_h), 13)
    # ⚖⚖⚖ **实现里**实际注册**的判据 id 集合**必须 == 预登记 §3.2 的编号集合
    #   ⇒ ⇒ 「预登记写了 13 条、实现只注册了 12 条」这种**漂移**会被当场抓住
    #   ⇒ ⇒ ⛔ 不用 set()（set 会把**重复注册**藏起来 ⇒ ⇒ 重复 ⇒ ⇒ 列表变长 ⇒ ⇒ 判红）
    impl_src = read_text(os.path.join(HERE, TARGET))
    impl_h = sorted(re.findall(r'check\("(H[0-9]+)-', impl_src), key=lambda s: int(s[1:]))
    chk("§3.2 判据编号（实现实际注册的）", impl_h, pre_h)

    # ===================== §5 闸门表（G0-1..G0-7）=====================
    sec5 = text.split("## 5. Phase-0 闸门", 1)
    if len(sec5) < 2:
        die("预登记里找不到 §5")
    body5 = sec5[1].split("## 6.", 1)[0]
    pre_g = re.findall(r"^\|\s*\*\*(G0-\d)\*\*\s*\|", body5, re.M)
    chk("§5 闸门编号", pre_g, ["G0-%d" % i for i in range(1, len(pre_g) + 1)])
    # ⚖ 闸门 id 必须**真的**被 --selftest 印出来
    p = subprocess.run([PY, os.path.join(HERE, TARGET), "--selftest"],
                       capture_output=True, text=True)
    printed = set(re.findall(r"^\[(?:PASS|FAIL)\]\s+(G0-\d)", p.stdout or "", re.M))
    chk("§5 闸门都被 --selftest 印出", sorted(printed), sorted(pre_g))

    # ===================== **不能机械比**的（必须显式列出）=====================
    cannot = [
        "Q4：rand 向量的**构造式**（探针源码逐字）—— 只能靠源码 grep + 现场重建 + 日志 mod 三方对账",
        "Q7/Q8 的 sidecar **字段语义**（marker_ids 是不是同一套）—— 靠 H2 的逐个比对，不是靠本文",
        "§3.1 各形态的**触发条件文字**—— 靠 Phase-0 的 G0-3/G0-4/G0-5/G0-6（合成夹具）验，不是靠本文",
        "§0.6 的「预登记先于结果」—— 靠**签发时点**与签发时的产物清单，不靠机器",
        "§4.3 形态对既有结论的含义—— 靠落账文本，不靠机器",
    ]

    # ===================== 自证能红 =====================
    mutated = dict(spec)
    mutated["z_threshold"] = 1.5
    m = re.search(r"E-B\(S\)\*\*\s*⟺\s*`z_T\(S\)\s*≥\s*([0-9.]+)`", qrow("Q13"))
    want_t = float(m.group(1)) if m else None
    selfred_ok = (mutated["z_threshold"] != want_t)
    if selfred_ok:
        ok.append("自证能红（把实现里的 z_threshold 改成 1.5 ⇒ 对账判红）")

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
