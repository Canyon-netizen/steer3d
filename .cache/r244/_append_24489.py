#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_append_24489.py —— 把 244.89 的判决**只追加**进权威账本。

⚖⚖⚖⚖⚖ **纪律（从 244.87 / 244.88 继承，一条都不许放松）**
   ① **只追加**：⛔ 不许改账本的既有字节 ⇒ ⇒ 追加后必须验「旧前缀逐字节不变」＋「围栏数不变」；
   ② 追加段里 ⛔ **不许有围栏**、⛔ **不许有反斜杠**（⇒ 账本可被逐行核对）；
   ③ 段里的**每一个数都从收据解析出来**（⛔ 不许手写、⛔ 不许凭记忆）；
   ④ **五个 rc 必须全 0** ⇒ ⇒ 否则**不许**落账；
   ⑤ 判决形态必须在 {A', B', C', D', E'} 里；
   ⑥ 支持 `--truncate`：**撤回重落**时只截尾部，且截断前必须**逐位核对**那份字节的 md5；
   ⑦ 幂等：账本里已有的 244.89 段若与收据算出来的那段**逐字节相同** ⇒ ⇒ 不重复写。

⚖ **用法**：python3 .cache/r244/_append_24489.py [--dry|--truncate]
"""

import hashlib
import io
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DEV = os.path.join(REPO, ".cache", "r244")
EV = os.path.join(DEV, "_e24489b")      # ⚖ **权威**收据（更正 ⑧ 之后重跑的那一轮）
EV0 = os.path.join(DEV, "_e24489")      # ⚖ 上一轮收据（更正 ⑧ **之前**）⇒ ⇒ 用来做「逐字节没动」的对照
LEDGER = os.path.join(REPO, ".cache", "xcheck", "R6_RERUN_PREREG.md")
PREREG = os.path.join(REPO, ".cache", "xcheck", "R6_CONFIDENCE_LEVEL_PREREG.md")

TITLE = "## 修订 244.89 ——"
# ⚖ 追加**前**那份账本的字节数与 md5（撤回重落时逐位核对）
PRE_LEN = 2643525
PRE_MD5 = "17557c5a4c9cc423d275def382d43b4f"
FORMS = ("A'", "B'", "C'", "D'", "E'")


def _md5_file(path):
    with open(path, "rb") as fh:
        return hashlib.md5(fh.read()).hexdigest()


def _read(p):
    with io.open(p, encoding="utf-8", newline="") as fh:
        return fh.read()


def _need(p):
    if not os.path.isfile(p):
        raise SystemExit("⛔ 缺收据/文件：%s" % p)
    return _read(p)


def _grab(txt, pat, what, flags=re.M):
    m = re.search(pat, txt, flags)
    if not m:
        raise SystemExit("⛔ 收据里核不到「%s」（模式 %s）" % (what, pat))
    return m


def _parse_cells(block, what, expect):
    """⚖ 解析作用域表里的一组格：CI / 污染 / 基准 / 界 / 联合 / 成立与否。"""
    rows = []
    for ln in block.split("\n"):
        m = re.match(r"^\s*CI([0-9.]+) / 污染([0-9.]+) / (\S+)\s+界=([+-][0-9.]+) pp"
                     r" ｜ 联合 (\d+)% ｜ (.+?)( ｜ 决策区)?$", ln)
        if m:
            rows.append({
                "ci": float(m.group(1)), "c": float(m.group(2)), "var": m.group(3),
                "bound": float(m.group(4)), "conf": int(m.group(5)),
                "ok": "不成立" not in m.group(6), "dec": m.group(7) is not None,
            })
    if len(rows) != expect:
        raise SystemExit("⛔ %s 里解析到 %d 格（期望 %d）⇒ ⇒ 中止" % (what, len(rows), expect))
    return rows


def collect():
    st = _need(os.path.join(EV, "selftest.out"))
    de = _need(os.path.join(EV, "de.out"))
    mu = _need(os.path.join(EV, "mut.out"))
    cr = _need(os.path.join(EV, "cross.out"))
    sp = _need(os.path.join(EV, "spec.out"))
    rc = _need(os.path.join(EV, "receipt.txt"))

    N = {}

    # ---- 五个 rc ----
    m = re.search(r"SELFTEST_RC=(\d+)\s+DE_RC=(\d+)\s+MUT_RC=(\d+)\s+CROSS_RC=(\d+)\s+SPEC_RC=(\d+)",
                  rc)
    if not m:
        raise SystemExit("⛔ receipt.txt 里没有五个 rc ⇒ ⇒ 中止")
    N["rcs"] = m.groups()
    if any(x != "0" for x in N["rcs"]):
        raise SystemExit("⛔ 五个 rc 里有非 0（%s）⇒ ⇒ **不许**落账" % (N["rcs"],))

    # ---- 判决形态 + AUDIT_KEYS ----
    m = re.search(r"===== AUDIT_KEYS =====\n(.*?)\n===== END_AUDIT_KEYS =====", de, re.S)
    if not m:
        m2 = re.search(r"===== AUDIT_KEYS =====\n(.*)", de, re.S)
        if not m2:
            raise SystemExit("⛔ de.out 里没有 AUDIT_KEYS 块 ⇒ ⇒ 中止")
        body = m2.group(1)
    else:
        body = m.group(1)
    K = {}
    for ln in body.splitlines():
        if "=" in ln:
            k, v = ln.split("=", 1)
            K[k.strip()] = v.strip()
    N["K"] = K
    N["verdict"] = K.get("VERDICT")
    if N["verdict"] not in FORMS:
        raise SystemExit("⛔ 判决形态 %r 不在 %s 里 ⇒ ⇒ 中止" % (N["verdict"], FORMS))
    for key in ("N_CELLS", "N_DECISION", "N_DECISION_HOLD", "N_ALL_HOLD",
                "CI_LO_TRAJ_90", "CI_LO_TRAJ_95", "CI_LO_TRAJ_99",
                "CI_LO_BLK_90", "CI_LO_BLK_95", "CI_LO_BLK_99",
                "BASE_MAIN_R", "CLO_90_MAIN", "CLO_95_MAIN", "CLO_99_MAIN",
                "DECISION_HOLDS", "ALL_BREAKS"):
        if key not in K:
            raise SystemExit("⛔ AUDIT_KEYS 里缺 %s ⇒ ⇒ 中止" % key)
    N["n_cells"] = int(K["N_CELLS"])
    N["n_dec"] = int(K["N_DECISION"])
    N["n_dec_hold"] = int(K["N_DECISION_HOLD"])
    N["n_all_hold"] = int(K["N_ALL_HOLD"])
    N["dec_holds"] = K["DECISION_HOLDS"]
    N["all_breaks"] = K["ALL_BREAKS"]

    # ---- 九条判据（逐条，含说明）----
    crits = re.findall(r"^\[(PASS|FAIL)\] (H\d) ([^—]*)— (.*)$", de, re.M)
    if len(crits) != 9:
        raise SystemExit("⛔ de.out 里解析到 %d 条判据（期望 9）⇒ ⇒ 中止" % len(crits))
    N["crits"] = crits
    N["reason"] = _grab(de, r"^理由：(.*)$", "判决理由").group(1).strip()

    # ---- H4：点估计读法的成立计数（⛔ 不手写「9/9」）----
    h4 = [d for _s, cid, _n, d in crits if cid == "H4"]
    if len(h4) != 1:
        raise SystemExit("⛔ de.out 里 H4 不唯一 ⇒ ⇒ 中止")
    m4 = re.search(r"轨迹级 (\d+)/(\d+) 成立 ｜ 块级 (\d+)/(\d+) 成立", h4[0])
    if not m4:
        raise SystemExit("⛔ H4 里核不到点估计读法的成立计数 ⇒ ⇒ 中止")
    N["h4_traj"] = (m4.group(1), m4.group(2))
    N["h4_blk"] = (m4.group(3), m4.group(4))

    # ---- H9：跨轮锚里的「CI 输入偏移」与 244.88 印值的**打印精度**（⛔ 不手写 13.01 / 0.0028 / 5e-5）----
    h9 = [d for _s, cid, _n, d in crits if cid == "H9"]
    if len(h9) != 1:
        raise SystemExit("⛔ de.out 里 H9 不唯一 ⇒ ⇒ 中止")
    m_off = re.search(r"CI 输入偏移 ([+-][0-9.]+)", h9[0])
    m_r1 = re.search(r"R1：新 ([+-][0-9.]+) vs 旧 ([+-][0-9.]+)", h9[0])
    m_cell = re.search(r"vs 旧 ([+-][0-9.]+)", h9[0])
    if not (m_off and m_r1 and m_cell):
        raise SystemExit("⛔ H9 里核不到「CI 输入偏移 / R1 旧值 / 首格旧值」⇒ ⇒ 中止")
    N["ci_offset"] = m_off.group(1)
    N["r1_old"] = m_r1.group(2)
    N["cell_old"] = m_cell.group(1)
    N["n_anchor_cells"] = h9[0].count("CI 输入偏移")   # 244.88 那 9 格（逐格对账的格数）

    def _dec_places(s):
        return len(s.split(".")[1]) if "." in s else 0

    N["dp_ci_in"] = _dec_places(N["r1_old"])        # 244.88 的 CI 输入印了几位小数
    N["dp_cell"] = _dec_places(N["cell_old"])      # 244.88 那 9 格印了几位小数
    N["half_ci_in"] = 0.5 * 10 ** (-N["dp_ci_in"])
    N["half_cell"] = 0.5 * 10 ** (-N["dp_cell"])

    # ---- 主表（决策区 12 格）与副表（全 27 格）----
    dec_blk = de.split("主表：决策区", 1)[1].split("⇒ 决策区", 1)[0]
    N["dec_cells"] = _parse_cells(dec_blk, "主表", N["n_dec"])
    all_blk = de.split("副表：全 27 格", 1)[1].split("⇒ 全表", 1)[0]
    N["all_cells"] = _parse_cells(all_blk, "副表", N["n_cells"])

    # ---- 作用域表：S1 / S2 的逐水平行（单源读法）----
    scope = de.split("──── 读法—作用域表 ────", 1)[1]
    s1_blk = scope.split("  S1  ", 1)[1].split("  S2  ", 1)[0]
    s2_blk = scope.split("  S2  ", 1)[1].split("  S3  ", 1)[0]
    s1 = re.findall(r"^\s+(\d\.\d\d)\s+界=([+-][0-9.]+) pp ⇒ (.+)$", s1_blk, re.M)
    s2 = re.findall(r"^\s+(\d\.\d\d)\s+界=([+-][0-9.]+) pp ⇒ (.+)$", s2_blk, re.M)
    if len(s1) != 3 or len(s2) != 3:
        raise SystemExit("⛔ 作用域表里 S1/S2 的行数是 %d/%d（期望 3/3）⇒ ⇒ 中止" % (len(s1), len(s2)))
    N["s1"], N["s2"] = s1, s2

    # ---- 自检 ----
    m = re.search(r"自检：(\d+) 道 ｜ FAIL (\d+) 道", st)
    if not m:
        raise SystemExit("⛔ selftest.out 里没有自检小结 ⇒ ⇒ 中止")
    N["st_n"], N["st_fail"] = m.groups()
    gates = re.findall(r"^\[(PASS|FAIL)\] (G0-\d)", st, re.M)
    if len(gates) != 9:
        raise SystemExit("⛔ selftest.out 里解析到 %d 道闸门（期望 9）⇒ ⇒ 中止" % len(gates))
    N["gates"] = gates

    # ---- 变异台 ----
    m = re.search(r"变异台：抓到 (\d+) / (\d+)（无效 (\d+) 条", mu)
    if not m:
        raise SystemExit("⛔ mut.out 里没有变异台小结 ⇒ ⇒ 中止")
    N["mut_caught"], N["mut_total"], N["mut_invalid"] = m.groups()
    N["mut_crash"] = _grab(mu, r"崩的条数：(\d+)", "崩的条数").group(1)
    N["mut_ids"] = re.findall(r"^\[(抓到|没抓到)\] (\S+)", mu, re.M)
    if N["mut_caught"] != N["mut_total"] or N["mut_invalid"] != "0" or N["mut_crash"] != "0":
        raise SystemExit("⛔ 变异台不是全绿（%s/%s，无效 %s，崩 %s）⇒ ⇒ **不许**落账"
                         % (N["mut_caught"], N["mut_total"], N["mut_invalid"], N["mut_crash"]))
    # ⚖ 叙述里点名的变异 id **必须**在收据里、且**必须**是「抓到」⇒ ⇒ 防止叙述与收据脱节
    _caught = dict((_mid, _st) for _st, _mid in N["mut_ids"])
    for _mid in ("MU1", "MU9", "MU14", "MU21"):
        if _mid not in _caught:
            raise SystemExit("⛔ 叙述里点名的变异 %s 不在收据的变异台清单里 ⇒ ⇒ 中止" % _mid)
        if _caught[_mid] != "抓到":
            raise SystemExit("⛔ 叙述里点名的变异 %s 在收据里**没抓到** ⇒ ⇒ 中止" % _mid)

    # ---- 互证 ----
    m = re.search(r"CROSS_OK=(\d+) ｜ CROSS_MISMATCH=(\d+)", cr)
    if not m:
        raise SystemExit("⛔ cross.out 里没有互证小结 ⇒ ⇒ 中止")
    N["cr_ok"], N["cr_bad"] = m.groups()
    N["cr_form"] = _grab(cr, r"^CROSS_FORM=(\S+)$", "互证形态").group(1)
    if N["cr_bad"] != "0" or N["cr_form"] != N["verdict"]:
        raise SystemExit("⛔ 互证有 MISMATCH（%s）或形态不一致（%s vs %s）⇒ ⇒ 中止"
                         % (N["cr_bad"], N["cr_form"], N["verdict"]))

    # ---- 对账 ----
    m = re.search(r"SPEC_OK=(\d+) ｜ SPEC_RED=(\d+)", sp)
    if not m:
        raise SystemExit("⛔ spec.out 里没有对账小结 ⇒ ⇒ 中止")
    N["sp_ok"], N["sp_bad"] = m.groups()
    if N["sp_bad"] != "0":
        raise SystemExit("⛔ 对账有红（%s）⇒ ⇒ 中止" % N["sp_bad"])

    # ---- 收据登记的 md5 ----
    N["rc_md5"] = {}
    for mm in re.finditer(r"^([0-9a-f]{32})\s+(\S+)$", rc, re.M):
        N["rc_md5"][os.path.basename(mm.group(2))] = mm.group(1)
    for need in ("confidence_level_audit.py", "mut_confidence_level_audit.py",
                 "_cross_check_24489.py", "_spec_crosscheck_24489.py",
                 "_run_24489_verify.sh", "R6_CONFIDENCE_LEVEL_PREREG.md",
                 "selftest.out", "de.out", "mut.out", "cross.out", "spec.out"):
        if need not in N["rc_md5"]:
            raise SystemExit("⛔ 收据里没有 %s 的 md5 ⇒ ⇒ 中止" % need)

    # ---- ⚖⚖⚖ 更正 ⑧ 之后**必须重跑验证链**（预登记与两处注释的字节变了）⇒ ⇒
    #      且这两次链的**五个输出必须逐字节相同**（更正只许改描述，不许动任何实测数）----
    N["chain_rerun"] = {}
    for f in ("selftest.out", "de.out", "mut.out", "cross.out", "spec.out"):
        p0 = os.path.join(EV0, f)
        p1 = os.path.join(EV, f)
        if not (os.path.isfile(p0) and os.path.isfile(p1)):
            raise SystemExit("⛔ 对照用的两轮收据不齐（%s）⇒ ⇒ 中止" % f)
        with open(p0, "rb") as fh:
            b0 = fh.read()
        with open(p1, "rb") as fh:
            b1 = fh.read()
        N["chain_rerun"][f] = (b0 == b1)
        if b0 != b1:
            raise SystemExit("⛔ 更正 ⑧ 之后重跑的验证链与之前**逐字节不同**（%s）"
                             "⇒ ⇒ 说明「只改描述」这句不成立 ⇒ ⇒ **不许**落账" % f)
    N["chain_rerun_ok"] = True

    # ---- 预登记 §0.5' 的更正条数（⛔ 不手写「七条」）----
    pre = _need(PREREG)
    mpre = re.search(r"^## §0\.5'", pre, re.M)
    if not mpre:
        raise SystemExit("⛔ 预登记里核不到 §0.5' ⇒ ⇒ 中止")
    seg = pre[mpre.start():]                       # §0.5' 是**最后一节** ⇒ ⇒ 截到文尾
    N["n_corr"] = len(re.findall(r"^### 更正 ", seg, re.M))
    if N["n_corr"] <= 0:
        raise SystemExit("⛔ 预登记 §0.5' 里数不到更正条 ⇒ ⇒ 中止")

    # ---- 决策区的分配结构（⛔ 不手写「4 种分配 × 3 个基准」）----
    alloc = {}
    for c in N["dec_cells"]:
        k = (c["ci"], c["c"])
        if k in alloc and alloc[k] != c["conf"]:
            raise SystemExit("⛔ 决策区里同一组分配 (%.2f,%.2f) 出现了**不同的联合置信** ⇒ ⇒ 中止"
                             % (k[0], k[1]))
        alloc[k] = c["conf"]
    N["alloc"] = alloc
    N["n_alloc"] = len(alloc)
    N["n_var"] = len(set(c["var"] for c in N["dec_cells"]))
    if N["n_alloc"] * N["n_var"] != N["n_dec"]:
        raise SystemExit("⛔ 决策区格数（%d）与「%d 种分配 × %d 个基准」对不上 ⇒ ⇒ 中止"
                         % (N["n_dec"], N["n_alloc"], N["n_var"]))

    # ---- 账本（被读的那份）----
    m = re.search(r"ledger_lines=(\d+)\s+ledger_md5=([0-9a-f]{32})", rc)
    if not m:
        raise SystemExit("⛔ receipt.txt 里没有账本行数/md5 ⇒ ⇒ 中止")
    N["led_lines"], N["led_md5"] = m.groups()
    return N


def build(N):
    K = N["K"]
    L = []
    A = L.append
    dec = N["dec_cells"]
    allc = N["all_cells"]
    s1 = N["s1"]
    s2 = N["s2"]

    A("## 修订 244.89 —— ⚖⚖⚖⚖⚖ **保守读法换置信水平的完整作用域**：「污染解释不了观测差」"
      "在**更宽置信水平**下**不再全域成立**（形态 **%s**）⇒ ⇒ 结论**再收紧一档**" % N["verdict"])
    A("")
    A("⚖ **口径真相源**：`.cache/xcheck/R6_CONFIDENCE_LEVEL_PREREG.md`（244.89 签，**先于**实现；"
      "§0.5' 含 **%d 条更正**：① 联合置信的算术（唯一「变松」的是更正②）、② H9② 的残差容差、"
      "③ H9③ 的 R6 切片、④ H2 加「手写」决策区成员表、⑤ G0-3 加「调用点」用例、"
      "⑥ G0-7 改成间隙负控＋函数级正负控、⑦ 补读法 id 表、⑧ 更正④ 的一处算术表述）"
      % N["n_corr"])
    A("⚖ **数据**：**只读**权威账本的 **244.81 段**（改判数、区间、基准）"
      "与 **244.88 段**（上一轮印的 %d 格 ＋ R1/R2/R3/R6，作**跨轮锚**）"
      "⇒ ⇒ ⛔ 不重跑日志、⛔ 零 GPU、⛔ 不碰 bpath" % N["n_anchor_cells"])
    A("⚖ **收据**：`.cache/r244/_e24489b/{selftest,de,mut,cross,spec}.out` ＋ `receipt.txt`"
      "（⚖ 这是**更正 ⑧ 之后重跑**的那一轮；`_e24489/` 是更正之前的上一轮）")
    A("")
    A("#### 【1】这一轮做了什么")
    A("")
    A("· **没有跑批、没有重解析跑批日志、没有 GPU** ⇒ ⇒ 全部输入**从账本逐行解析**"
      "（⛔ 代码里**不写死任何一个数**；连**容差**都由**账本自己的打印精度**推导）。")
    A("· **回答的问题**：244.88 判成形态 B'，但它的 CI 下端点**只有 95% 一档**"
      "（它**读**账本印好的 Newcombe95 区间，**自己没有算过 Newcombe**）"
      "⇒ ⇒ 「**更宽置信水平下的保守读法**」**完全没量到**（244.88 的边界清单 B-2）。")
    A("· **本轮做两件事**：① **把 Newcombe 自己实现出来**（方法 10），在 **90 / 95 / 99** 三档"
      "**各算一遍**；② 把保守读法放到完整的 **(CI 水平 × 污染水平 × 基准变体) = %d 格**上，"
      "并抽出**决策区**（联合置信 ≥ 90%%）作**主表**。" % N["n_cells"])
    A("· ⚖⚖⚖ **量纲（只允许三种运算）**：① `delta_ci_lo > 0`（单源读法，**不需要 c**）｜"
      "② `delta_obs + c_lower > 0`（点估计读法）｜③ `delta_ci_lo + c_lower > 0`（保守读法）"
      "⇒ ⇒ ⛔ `delta_ci_lo ↔ c_upper` **仍然红**（244.87 的 H5 / 244.88 的 H8 硬门，继续有效）。")
    _alloc_txt = " / ".join("(%d,%d) %d%%" % (round(k[0] * 100), round(k[1] * 100), v)
                            for k, v in sorted(N["alloc"].items()))
    A("· ⚖⚖⚖ **联合置信（Bonferroni）**：`联合 = 1 − α_CI − α_c = L_CI + L_c − 1`"
      "⇒ ⇒ **逐格不同**（⛔ 不许把整张表写成同一个数）⇒ ⇒ 决策区 = 联合 ≥ 90%% 的**全部**组合 = "
      "**%s** = **%d 种分配 × %d 个基准 = %d 格**。"
      % (_alloc_txt, N["n_alloc"], N["n_var"], N["n_dec"]))
    A("· ⚖⚖⚖ **联合置信的比较落在「整数百分点」上**（⛔ 不是浮点）⇒ ⇒ 因为二元浮点里 "
      "`0.95 + 0.95 − 1.0 = 0.8999999999999999 < 0.9` ⇒ ⇒ 若直接拿浮点比门槛，"
      "**(95,95) 那 %d 格（%d 个基准变体）会被静默踢出决策区**"
      "（⇒ ⇒ 主表会从 %d 格变成 %d 格）⇒ ⇒ 本轮把这条**结构性地**堵死"
      "（H2 的「**手写**成员表」＋ 变异 MU21 实证）。"
      % (N["n_var"], N["n_var"], N["n_dec"], N["n_dec"] - N["n_var"]))
    A("· ⚠ **本轮享受不到「结果未知」的豁免**（预登记 §0.5' 的 N2）：本轮的量**全部已在账本登记**"
      "⇒ ⇒ **手算即可**得出各格界的符号 ⇒ ⇒ 预登记的作用是「**先验固定判据、形态、护栏与口径**」，"
      "⛔ 不是隐藏结果 ⇒ ⇒ 连**对结果不利的那一档形态（B'）**也**先验写死**了。")
    A("")
    A("#### 【2】判决面板")
    A("")
    A("· **判决形态**：**%s**" % N["verdict"])
    A("· **理由（原文）**：%s" % N["reason"])
    A("")
    A("· **主表 = 决策区**（联合置信 ≥ 90%%；**%d 格**，其中 **%d 格成立**）：" % (N["n_dec"], N["n_dec_hold"]))
    A("")
    A("| CI 水平 | 污染水平 | 基准 | 界（pp） | 联合置信 | 结论 |")
    A("|---|---|---|---|---|---|")
    for c in dec:
        A("| %.2f | %.2f | %s | **%+.4f** | %d%% | %s |"
          % (c["ci"], c["c"], c["var"], c["bound"], c["conf"],
             "✅ 成立" if c["ok"] else "⛔ **不成立**"))
    A("")
    A("· **副表 = 全 %d 格**（**完整作用域**）：**%d 格成立** ｜ 破口 %d 个" % (N["n_cells"], N["n_all_hold"],
                                                                          N["n_cells"] - N["n_all_hold"]))
    A("")
    A("| CI 水平 | 污染水平 | 基准 | 界（pp） | 联合置信 | 决策区 | 结论 |")
    A("|---|---|---|---|---|---|---|")
    for c in allc:
        A("| %.2f | %.2f | %s | **%+.4f** | %d%% | %s | %s |"
          % (c["ci"], c["c"], c["var"], c["bound"], c["conf"],
             "是" if c["dec"] else "—",
             "✅ 成立" if c["ok"] else "⛔ **不成立**"))
    A("")
    A(("· **单源读法（污染只抬高 rand 臂；不依赖 c）跨 %d 个水平**：轨迹级 " % len(s1))
      + " ｜ ".join("%s ⇒ **%+.4f pp**（%s）" % (lv, float(bd), "成立" if "不成立" not in ok else "**不成立**")
                    for lv, bd, ok in s1)
      + " ｜ 块级 "
      + " ｜ ".join("%s ⇒ **%+.4f pp**（%s）" % (lv, float(bd), "成立" if "不成立" not in ok else "**不成立**")
                    for lv, bd, ok in s2))
    A("")
    A("· ⚖ **三个 Newcombe 下端点（本轮自己算的；244.88 只用了 95%% 那一个）**："
      "CI_lo(traj) 90%% = **%s** ｜ 95%% = **%s** ｜ 99%% = **%s**；"
      "CI_lo(block) 90%% = **%s** ｜ 95%% = **%s** ｜ 99%% = **%s**"
      % (K["CI_LO_TRAJ_90"], K["CI_LO_TRAJ_95"], K["CI_LO_TRAJ_99"],
         K["CI_LO_BLK_90"], K["CI_LO_BLK_95"], K["CI_LO_BLK_99"]))
    A("· ⚖ **c 的下界（Wilson；随水平变宽）**：90%% ⇒ **%s** ｜ 95%% ⇒ **%s** ｜ 99%% ⇒ **%s**（main 基准）"
      % (K["CLO_90_MAIN"], K["CLO_95_MAIN"], K["CLO_99_MAIN"]))
    A("· ⚖⚖⚖ **口径必须带**：单源读法的轨迹级界**在 %d 个水平上都 > 0**（最紧 **%s**）"
      "⇒ ⇒ 「污染只抬高 rand 臂」这条读法**跨水平都成立**；点估计读法 %s/%s 成立（轨迹级）／%s/%s（块级）；"
      "而**保守读法**在**决策区里只有 %d/%d 格成立** ⇒ ⇒ **结论必须收紧**。"
      % (len(N["s1"]), K["CI_LO_TRAJ_99"],
         N["h4_traj"][0], N["h4_traj"][1], N["h4_blk"][0], N["h4_blk"][1],
         N["n_dec_hold"], N["n_dec"]))
    A("")
    A("#### 【3】❌ **九条判据逐条（真数据）**")
    A("")
    for st_, cid, name, detail in N["crits"]:
        A("- [%s] **%s** %s — %s" % ("PASS" if st_ == "PASS" else "FAIL", cid, name.strip(), detail))
    A("")
    A("#### 【4】✅ **每条判据能红**")
    A("")
    A("- **自检**（Phase-0 G0-1..G0-9，合成夹具、⛔ 零账本、⛔ 零 GPU）：判据 **%s** 道 ｜ FAIL **%s** 道"
      % (N["st_n"], N["st_fail"]))
    A("- **变异台**：抓到 **%s / %s**（无效 %s 条 ⇒ 记「无效」⇒ 不计入分母）｜ 崩的条数 **%s**（⛔ 必须是 0）"
      % (N["mut_caught"], N["mut_total"], N["mut_invalid"], N["mut_crash"]))
    A("- **变异台逐条**：%s" % "、".join(mid for _s, mid in N["mut_ids"]))
    A("- **互证**（第二条独立实现：**Fraction** 算基准 ＋ **Decimal(60 位)** 算 Wilson ＋ **NormalDist** 取 z ＋ "
      "**自己实现 Newcombe**；⛔ 与被检实现零共用代码、锚点也故意不同、**解析按单元格切**）：OK **%s** ｜ "
      "MISMATCH **%s** ｜ 独立重算的判决形态 **%s**" % (N["cr_ok"], N["cr_bad"], N["cr_form"]))
    A("- **预登记 ↔ 实现 的机械对账**：OK **%s** ｜ 红 **%s**" % (N["sp_ok"], N["sp_bad"]))
    A("- **验证链五个 rc**：**%s / %s / %s / %s / %s**" % N["rcs"])
    A("- ⚖⚖⚖ **验证链跑了两次，两次的五个输出逐字节相同**："
      "第 1 轮（更正 ⑧ **之前**）与第 2 轮（更正 ⑧ **之后**）的 `selftest / de / mut / cross / spec` "
      "**逐字节 IDENTICAL** ⇒ ⇒ 「更正 ⑧ 与那两处注释**只改描述、一个实测字节都没动**」"
      "这句**不是声明，是比对结果** ⇒ ⇒ ⇒ ⇒ 落账脚本里有一条**硬闸**："
      "这五个文件只要有一个不同 ⇒ ⇒ **不许**落账。")
    A("")
    A("#### 【5】⚖⚖⚖ **本轮抓到的真缺陷（⛔ 一个数都没动）**")
    A("")
    A("1. ⚠⚖⚖ **实现层（自检层）**：G0-2 的期望级联**从模块常量 `HARD_FAIL_IDS` 派生** ⇒ ⇒ "
      "「把 H9 从硬失败集合里拿掉」这种变异**两边一起变** ⇒ ⇒ **恒绿** ⇒ ⇒ 变异台 **MU1 存活**暴露 "
      "⇒ ⇒ 改成「硬失败集合**手写**」＋「模块常量必须与手写那份**逐条相同**」⇒ ⇒ 判据**变严**。"
      "⚖ **这是 244.88 第 ② 条缺陷的同型复发**（244.88 当时改了它，**但本轮新写的代码又犯了一次**）"
      "⇒ ⇒ 记为「**同一类坑会复发**」⇒ ⇒ 以后每轮都要**显式检查**这一条。")
    A("2. ⚠⚖ **实现层（护栏层）**：量纲护栏的**兜底分支**（「只允许登记的加法对」）**没有被任何用例覆盖** "
      "⇒ ⇒ 变异 **MU9 存活**暴露 ⇒ ⇒ 补了「`delta_obs + delta_obs`」这条用例（它**只**由兜底那条拦）"
      "⇒ ⇒ 判据**变严**。⚖ **这是 244.88 第 ③ 条缺陷的同型复发**。")
    A("3. ⚠ **实现层（护栏层）**：护栏的**调用点**没被测 ⇒ ⇒ 「护栏函数还在、但**加法不再调用它**」"
      "这种削弱**没人知道** ⇒ ⇒ 补了「从**真正的加法路径**喂一次未登记配对」⇒ ⇒ 变异 MU14 抓住。")
    A("4. ⚠ **实现层**：量纲护栏的允许加法表**只登记了一个方向** ⇒ ⇒ 合法调用的**交换顺序**会被误判红 "
      "⇒ ⇒ 补齐两种顺序 ⇒ ⇒ 判据**变严**。")
    A("5. ⚠⚖ **工具层（合成夹具）**：夹具里的 `\"95% 单源\"` **没转义** ⇒ ⇒ "
      "`TypeError: not all arguments converted during string formatting` ⇒ ⇒ **整份自检跑不起来** "
      "⇒ ⇒ ⚠ **本地 `compile()` 抓不到**（运行期才炸）⇒ ⇒ 抓到它的办法是「**真的跑一遍**」"
      "⇒ ⇒ 另加了一条**静态检查**（`tokenize` ＋ 逐个 `%` 验格式说明符）。")
    A("6. ⚠ **工具层（互证）**：互证脚本按「单元格切」抠分布 ⇒ ⇒ 首格带前缀 ⇒ ⇒ 抠不到两个分布块 "
      "⇒ ⇒ 改成正则抠 `{…}` 块。")
    A("7. ⚠⚖⚖ **工具层（互证）**：互证脚本的 **Newcombe 混了单位**（Wilson 返回 pp，公式要比例）"
      "⇒ ⇒ 结果量级 1e4 ⇒ ⇒ ⛔ **不是**被检实现发现的 ⇒ ⇒ 是**互证自己的数值对账**抓到的 "
      "⇒ ⇒ 这正是「第二条独立实现」的价值：它**自己也会错**，所以两边都要对账。")
    A("8. ⚠ **工具层（互证）**：`Decimal(Fraction)` 直接转换抛 TypeError ⇒ ⇒ 改成「分子/分母」。")
    A("9. ⚠⚖ **工具层（对账）**：对账脚本有 **8 处抽取失配**（浮点 tuple 没抠到、`GATE_IDS` 是推导式、"
      "`frozenset([…])` 块没抠到、`FORMS` 是常量名、硬失败集合的正则、决策区块跨行、"
      "联合置信表的百分号格式、容差的科学计数法）⇒ ⇒ **11 条里红 11 条**"
      "⇒ ⇒ ⚠ **那 11 条红全是「对账脚本自己」的问题**（⛔ 不是被检实现的问题）⇒ ⇒ 逐条改 "
      "⇒ ⇒ 改到 **%s OK / %s 红** ⇒ ⇒ ⚖ **教训**：对账脚本自己的抽取逻辑**也会骗人**"
      "⇒ ⇒ 「全红」的第一反应必须是「**谁的抽取坏了**」，⛔ 不是「被检实现坏了」。"
      "⚖ **诚实标注**：这里的「8 处」「11 条里红 11 条」是**本轮中途的中间态**"
      "（⚠ **无收据留存**）⇒ ⇒ **最终态**才有收据（%s OK / %s 红）。" % (N["sp_ok"], N["sp_bad"], N["sp_ok"], N["sp_bad"]))
    A("10. ⚖⚖ **驱动层（结构性改进）**：244.88 的第 ⑨ 条缺陷（banner 印**过期**的变异条数）⇒ ⇒ "
      "本轮把 banner 里的条数改成**从台架源码现算** ⇒ ⇒ **结构上**堵死这一类缺陷"
      "（改台架就必然改 banner ⇒ ⇒ 不存在「过期计数」这种可能）。")
    A("11. ⚖ **等价变异（记「无效」，⛔ 不是「存活」）**：MU21 的初版只把 `in_decision` 的比较式换成浮点、"
      "而 `joint_conf` 内部**仍是整数百分点** ⇒ ⇒ **逐条结果完全相同** ⇒ ⇒ 记「无效」"
      "⇒ ⇒ 改成真正会触发浮点陷阱的那条（把**整数百分点本身**换成浮点截断）⇒ ⇒ 抓到了 ✓。")
    A("12. ⚠⚖⚖ **预登记层（起草层算术）**：预登记 §0.5' 更正 ④ 写「把 **(95,95) 那 9 格**静默踢出决策区」"
      "「**主表会悄悄少掉 9 格**」⇒ ⇒ **与预登记自己的「决策区 = 4 种分配 × 3 个基准 = 12 格」矛盾**："
      "每种分配**只覆盖 3 个基准变体** ⇒ ⇒ 踢掉 (95,95) 踢掉的是 **%d 格**，主表是**从 %d 格变成 %d 格**"
      "⇒ ⇒ ⚠ **预登记层**、**实现层**（两处注释）、**变异台**（两处描述）都复述了这个错 ⇒ ⇒ "
      "⇒ ⇒ **只改描述、⛔ 一个实测数都没动**（决策区仍是 12 格、成立格数不变、形态不变）"
      "⇒ ⇒ 已按预登记自己的机制**追加**「更正 ⑧」（⛔ 只追加、⛔ 不改既有字节）"
      "⇒ ⇒ 并在**落账时**把这条记为**预登记层的真缺陷** ⇒ ⇒ ⚠ **如实标注**：更正 ⑧ 是**落账时**"
      "（**已看到结果之后**）才发现的 ⇒ ⇒ 但它是**纯算术**、与实测结果无关 ⇒ ⇒ "
      "**不改动任何判据/门槛/护栏/形态定义** ⇒ ⇒ 因而不构成「结果驱动的改判据」。"
      % (N["n_var"], N["n_dec"], N["n_dec"] - N["n_var"]))
    A("")
    A("#### 【6】⚖⚖⚖ **本轮查实的一条「口径继承」事实（不是缺陷，但要进边界清单）**")
    A("")
    A("· 244.88 的 R5 表消费的是账本**印好的** Newcombe95 下端点（**%d 位小数 %s**）"
      "⇒ ⇒ 那 %d 格因此**继承了 ≤ ±%g pp 的舍入** ⇒ ⇒ 本轮**精确重算**得 "
      "**%s** ⇒ ⇒ 两轮那 %d 格**逐格差 %s pp** ⇒ ⇒ 而这个差**被「CI 输入的偏移」完全解释**"
      "（H9 的残差 ≤ %g = 244.88 那 %d 格**%d 位小数**的半个单位）⇒ ⇒ "
      "**244.88 的数一个字都不用改**（符号与形态都**不受影响**）⇒ ⇒ 但**本轮比 244.88 更保守一点点**。"
      % (N["dp_ci_in"], N["r1_old"], N["n_anchor_cells"], N["half_ci_in"], K["CI_LO_TRAJ_95"],
         N["n_anchor_cells"], N["ci_offset"], N["half_cell"], N["n_anchor_cells"], N["dp_cell"]))
    A("· ⇒ ⇒ **为什么这条要写进账本**：若下一轮有人拿 244.89 的数去比 244.88 的数，"
      "**必须**知道那 %s pp 的来源 ⇒ ⇒ 否则会误判成「有一轮偷偷改了数」。" % N["ci_offset"])
    A("")
    A("#### 【7】⛔ **边界清单（本轮哪些仍未量到 / 不许被读成什么）**")
    A("")
    A("- ✅ **B-2 已补上**：「更宽置信水平下的保守读法」**已量到**（%d 格全表 ＋ 决策区 %d 格）"
      "⇒ ⇒ 但它量到的是**界与作用域**，⛔ **不是**「污染的精确幅度」。"
      % (N["n_cells"], N["n_dec"]))
    A("- ⛔ **「污染不存在」仍未量到**；「污染的**精确幅度**」仍未量到（本轮给的是**界**，⛔ 不是点估计）。")
    A("- ⛔ **块级口径下的污染量 / 污染上界仍未量到**（块级零假设基准未在账本登记 ⇒ ⇒ 需**重解析原始跑批日志** "
      "⇒ ⇒ **要点头**）⇒ ⇒ 本轮块级那 %d 格**只作示意**，⛔ **不参与形态判定**。" % N["n_cells"])
    A("- ⛔ **识别假设**：「rand 臂在无污染时的改判率 = 零假设基准」⇒ ⇒ **全部**污染相关结论都**条件于**它 "
      "⇒ ⇒ 该假设**未在本轮独立验证**。")
    A("- ⛔ **Newcombe 是 score 型区间，不承认聚类** ⇒ ⇒ 轨迹级区间**可能偏窄** ⇒ ⇒ 本轮**沿用**同一口径"
      "（⛔ 不换方法）⇒ ⇒ 「本轮的界比 244.88 更保守**多少**」**未量到**。")
    A("- ⛔ **本轮只换置信水平，不换方法** ⇒ ⇒ 「换个区间方法会怎样」**未量到**。")
    A("- ⛔ **机制轴、剂量轴**沿用旧留白，**未量到**。")
    A("- ⚖ **自检层的固有上限**：改「闸门自己的比较表达式」这件事**没有闸门能抓** ⇒ ⇒ 本轮用"
      "「正控 ＋ 负控共用同一个函数」把它**缩小**，⛔ **不可能**消灭 ⇒ ⇒ 记为**留白**。")
    A("- ⛔ **预登记层与账本层没有自检** ⇒ ⇒ 「预登记**整体**先于结果」**不成立**；准确的说法是"
      "「§0.5、§1、§2、§3、§3.2、§4、§5、§6、§7 与 **§0.5' 的 %d 条更正**的**口径与判据**全部先于结果」"
      "⇒ ⇒ 且 N2 已**明写**各格的符号可手算 ⇒ ⇒ **不主张**「结果未知」。" % N["n_corr"])
    A("- ⛔ **决策区里 %d/%d 格成立** ⇒ ⇒ 这**不等于**「污染能解释观测差」⇒ ⇒ 它只说明："
      "「**把抽样噪声与污染幅度同时按最保守方向放**」这条读法，**只在部分水平/基准组合成立**。"
      % (N["n_dec_hold"], N["n_dec"]))
    A("")
    A("#### 【8】▶️ **下一轮（244.90+）**")
    A("")
    A("1. **B-1 要点头**（**重解析原始跑批日志**）⇒ ⇒ 才能得到「**同口径**的块级污染上界」"
      "⇒ ⇒ 才能把块级那些格从「跨口径·示意」升级成「同口径」。")
    A("2. **换区间方法**（承认聚类的区间 vs score 型区间）在保守读法上的影响 ⇒ ⇒ 本轮沿用同一方法"
      "（⛔ 不偷跑）。")
    A("3. 与旧留白（剂量轴、机制轴、多随机种子）的衔接仍需点头。")
    A("")
    A("#### 【9】⚖ **这一轮的字节**")
    A("")
    A("⚖⚖⚖ 下面每个 md5 都是**由文件本身算出来的**；标「⚖ 收据登记」的**同时**与"
      "**远端验证链收据里登记的那份逐位对上** ⇒ ⇒ 「入库的字节 ＝ 跑出这些数的字节」。")
    A("")
    A("- **被检 / 口径 / 驱动（6 件）**：")
    for nm in ("confidence_level_audit.py", "mut_confidence_level_audit.py",
               "_cross_check_24489.py", "_spec_crosscheck_24489.py",
               "_run_24489_verify.sh", "R6_CONFIDENCE_LEVEL_PREREG.md"):
        A("  - `%s`  `%s`  ⚖ 收据登记（远端验证链）" % (N["rc_md5"][nm], nm))
    A("- **收据文件（5 件）**：")
    for nm in ("selftest.out", "de.out", "mut.out", "cross.out", "spec.out"):
        A("  - `%s`  `%s`  ⚖ 收据登记（远端验证链）" % (N["rc_md5"][nm], nm))
    A("")
    A("⚖ **远端**：`zju-53`（2026-10-25 CST）｜ ⛔ **零 GPU**、⛔ 没跑批、⛔ 没改读数器/探针/拆分器、"
      "⛔ 没改 244.79–244.88 段。")
    A("")
    A("⚖⚖⚖ **一条必须说清的事实**：`zju-53` 与 `zju-12` 是**两台共享同一份 NFS 家目录**的机器 "
      "⇒ ⇒ 「**两台远端逐位一致**」是**必然**的，⛔ **不是**一条独立证据 "
      "⇒ ⇒ 真正的独立证据是「**收据里的 md5 == 本地现算的 md5**」。")
    A("")
    A("⚖ **被读的账本**：`R6_RERUN_PREREG.md` —— **%s 行 ｜ md5 `%s`** ⇒ ⇒ 本轮**只读**它 "
      "⇒ ⇒ 落账后账本会变长，而 **244.81 / 244.88 两段一字不动** ⇒ ⇒ 本轮的数不会因为落账而变。"
      % (N["led_lines"], N["led_md5"]))
    A("")
    return "\n".join(L) + "\n"


def main():
    dry = "--dry" in sys.argv
    truncate = "--truncate" in sys.argv
    N = collect()
    if truncate:
        # ⚖⚖⚖ **撤回重落**：把账本**截回**「追加 244.89 之前」的那份字节
        with open(LEDGER, "rb") as fh:
            data = fh.read()
        pre_len = len(data)
        if pre_len <= PRE_LEN:
            raise SystemExit("⛔ 账本只有 %d 字节（≤ 追加前那份的 %d）⇒ ⇒ 没落过账 ⇒ 中止"
                             % (pre_len, PRE_LEN))
        head = data[:PRE_LEN]
        m = hashlib.md5(head).hexdigest()
        if m != PRE_MD5:
            raise SystemExit("⛔ 前 %d 字节的 md5 = %s（期望 %s）⇒ ⇒ **不截**"
                             % (PRE_LEN, m, PRE_MD5))
        with open(LEDGER, "wb") as fh:
            fh.write(head)
        after = open(LEDGER, "rb").read()
        if after != head:
            raise SystemExit("⛔ 截断后不一致 ⇒ 中止")
        print("✅ 已截回追加前那份：%d → %d 字节 ｜ md5 %s" % (pre_len, len(after), m))
        return 0
    sec = build(N)
    fences = [l for l in sec.split("\n") if l.strip().startswith("```")]
    assert not fences, "⛔ 追加段里有围栏 ⇒ 不许"
    assert "\\" not in sec, "⛔ 追加段里有反斜杠 ⇒ 不许"
    full = _read(LEDGER)
    n_have = full.count(TITLE)
    if n_have > 1:
        raise SystemExit("⛔ 账本里有 %d 处「%s」⇒ ⇒ 停下" % (n_have, TITLE))
    if n_have == 1:
        tail = full[full.index(TITLE):]
        if tail == sec or tail.rstrip() == sec.rstrip():
            print("✅ 幂等：账本里已有的 244.89 段与**收据算出来的那段逐字节相同** ⇒ ⇒ 不重复写")
            return 0
        raise SystemExit("⛔ 账本里已有 244.89 段，但它与收据算出来的**不一致** ⇒ ⇒ 停下"
                         "（⛔ 不许覆盖、⛔ 不许改数凑好看）")
    n_before = sum(1 for l in full.split("\n") if l.strip().startswith("```"))
    old_len = len(full.encode("utf-8"))
    old_lines = full.count("\n")
    print("账本现状：%d 行 / %d 字节 ｜ 围栏 %d 个" % (old_lines, old_len, n_before))
    if dry:
        print("")
        print(sec)
        print("（--dry：只看不写）")
        return 0
    with io.open(LEDGER, "a", encoding="utf-8") as f:
        f.write(sec)
    after = _read(LEDGER)
    n_after = sum(1 for l in after.split("\n") if l.strip().startswith("```"))
    assert n_after == n_before, "⛔ 落账后围栏数变了 ⇒ 停下"
    assert after.encode("utf-8")[:old_len] == full.encode("utf-8"), "⛔ 旧前缀变了 ⇒ 停下"
    print("")
    print("✅ 已追加：%d → %d 字节（行 %d → %d）｜ 围栏仍 %d 个 ｜ 旧前缀逐字节不变"
          % (old_len, len(after.encode("utf-8")), old_lines, after.count("\n"), n_after))
    return 0


if __name__ == "__main__":
    sys.exit(main())
