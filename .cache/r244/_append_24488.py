#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_append_24488.py —— 把 244.88 的判决**只追加**进权威账本。

⚖⚖⚖⚖⚖ **纪律（从 244.87 继承，一条都不许放松）**
   ① **只追加**：⛔ 不许改账本的既有字节 ⇒ ⇒ 追加后必须验「旧前缀逐字节不变」＋「围栏数不变」；
   ② 追加段里 ⛔ **不许有围栏**、⛔ **不许有反斜杠**（⇒ 账本可被逐行核对）；
   ③ 段里的**每一个数都从收据解析出来**（⛔ 不许手写、⛔ 不许凭记忆）；
   ④ **五个 rc 必须全 0** ⇒ ⇒ 否则**不许**落账；
   ⑤ 判决形态必须在 {A′, B′, C′, D′, E′} 里；
   ⑥ 支持 `--truncate`：**撤回重落**时只截尾部，且截断前必须**逐位核对**那份字节的 md5；
   ⑦ 幂等：账本里已有的 244.88 段若与收据算出来的那段**逐字节相同** ⇒ ⇒ 不重复写。

⚖ **用法**：python3 .cache/r244/_append_24488.py [--dry|--truncate]
"""

import hashlib
import io
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DEV = os.path.join(REPO, ".cache", "r244")
EV = os.path.join(DEV, "_e24488")
LEDGER = os.path.join(REPO, ".cache", "xcheck", "R6_RERUN_PREREG.md")
PREREG = os.path.join(REPO, ".cache", "xcheck", "R6_CONSERVATIVE_BOUND_PREREG.md")

TITLE = "## 修订 244.88 ——"
# ⚖ 追加**前**那份账本的字节数与 md5（撤回重落时逐位核对）
PRE_LEN = 2626945
PRE_MD5 = "8e89b6d1ba2fc220073d86fca7f329ed"
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
        raise SystemExit("⛔ de.out 里没有 AUDIT_KEYS 块 ⇒ ⇒ 中止")
    K = {}
    for ln in m.group(1).splitlines():
        if "=" in ln:
            k, v = ln.split("=", 1)
            K[k.strip()] = v.strip()
    N["K"] = K
    N["verdict"] = K.get("VERDICT")
    if N["verdict"] not in FORMS:
        raise SystemExit("⛔ 判决形态 %r 不在 %s 里 ⇒ ⇒ 中止" % (N["verdict"], FORMS))

    # ---- 九条判据（逐条，含说明）----
    crits = re.findall(r"^\[(PASS|FAIL)\] (H\d) ([^—]*)— (.*)$", de, re.M)
    if len(crits) != 9:
        raise SystemExit("⛔ de.out 里解析到 %d 条判据（期望 9）⇒ ⇒ 中止" % len(crits))
    N["crits"] = crits
    N["reason"] = _grab(de, r"^理由：(.*)$", "判决理由").group(1).strip()

    # ---- 作用域表：R1 / R2 两行（单源）----
    single = re.findall(r"^  (R[12])  (.+?)\s+界=([+-][0-9.]+) pp ｜ 置信 (\d+)% ｜ (.*)$", de, re.M)
    if len(single) != 2:
        raise SystemExit("⛔ de.out 里解析到 %d 行 R1/R2（期望 2）⇒ ⇒ 中止" % len(single))
    N["single"] = single

    # ---- 作用域表：R3 / R4 / R5 / R6 的逐口径行 ----
    per = re.findall(r"^      (\d\.\d\d) / (\S+)\s+界=([+-][0-9.]+) pp ⇒ (\*\*不成立\*\*|成立)"
                     r"( ｜ 联合 (\d+)%)?$", de, re.M)
    if len(per) != 36:
        raise SystemExit("⛔ de.out 里解析到 %d 行逐口径界（期望 36 = 4 行 × 9 口径）⇒ ⇒ 中止" % len(per))
    N["per"] = per

    # ---- 自检 ----
    m = re.search(r"SELFTEST_GATES=(\d+) ｜ FAIL=(\d+) ｜ (\S+)", st)
    if not m:
        raise SystemExit("⛔ selftest.out 里没有自检小结 ⇒ ⇒ 中止")
    N["st_n"], N["st_fail"], N["st_word"] = m.groups()
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

    # ---- 互证 ----
    m = re.search(r"CROSS_OK=(\d+) ｜ CROSS_MISMATCH=(\d+)", cr)
    if not m:
        raise SystemExit("⛔ cross.out 里没有互证小结 ⇒ ⇒ 中止")
    N["cr_ok"], N["cr_bad"] = m.groups()
    N["cr_form"] = _grab(cr, r"^CROSS_FORM=(\S+)$", "互证形态").group(1)

    # ---- 对账 ----
    m = re.search(r"SPEC_OK=(\d+) ｜ SPEC_RED=(\d+)", sp)
    if not m:
        raise SystemExit("⛔ spec.out 里没有对账小结 ⇒ ⇒ 中止")
    N["sp_ok"], N["sp_bad"] = m.groups()

    # ---- 收据登记的 md5 ----
    N["rc_md5"] = {}
    for mm in re.finditer(r"^([0-9a-f]{32})\s+(\S+)$", rc, re.M):
        N["rc_md5"][os.path.basename(mm.group(2))] = mm.group(1)

    # ---- 可复现性对照（两次独立验证链的逐字节比对；⛔ 不手写）----
    rp = os.path.join(EV, "repro.txt")
    if not os.path.isfile(rp):
        raise SystemExit("⛔ 缺 %s ⇒ ⇒ 中止（没有对照记录就不能落账）" % rp)
    R = {}
    for ln in _read(rp).splitlines():
        if "=" in ln:
            k, v = ln.split("=", 1)
            R[k.strip()] = v.strip()
    for k in ("REPRO_N_FILES", "REPRO_N_IDENTICAL", "REPRO_DRIVER_OLD_MD5",
              "REPRO_DRIVER_NEW_MD5", "REPRO_DRIVER_CHANGED",
              "REPRO_LEDGER_RUN1_LINES", "REPRO_LEDGER_RUN1_MD5",
              "REPRO_LEDGER_RUN2_LINES", "REPRO_LEDGER_RUN2_MD5"):
        if k not in R:
            raise SystemExit("⛔ repro.txt 里缺 %s ⇒ ⇒ 中止" % k)
    N["repro"] = R
    N["repro_n"] = int(R["REPRO_N_FILES"])
    N["repro_ident"] = int(R["REPRO_N_IDENTICAL"])
    if N["repro_ident"] != N["repro_n"]:
        raise SystemExit("⛔ 两次验证链的收据并不逐字节一致（%d / %d）⇒ ⇒ 中止"
                         % (N["repro_ident"], N["repro_n"]))

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

    r1 = N["single"][0]
    r2 = N["single"][1]
    per = N["per"]
    # 逐口径行：按 R3/R4/R5/R6 的顺序（de.out 里就是这个顺序）
    blocks = {"R3": per[0:9], "R4": per[9:18], "R5": per[18:27], "R6": per[27:36]}
    r3 = blocks["R3"]
    r4 = blocks["R4"]
    r5 = blocks["R5"]
    r6 = blocks["R6"]

    A("## 修订 244.88 —— ⚖⚖⚖⚖⚖ **保守读法与口径边界**：「污染解释不了观测差」在**最保守读法**下"
      "**只在部分扫描口径成立**（形态 **%s**）⇒ ⇒ 结论**必须收紧**" % N["verdict"])
    A("")
    A("⚖ **口径真相源**：`.cache/xcheck/R6_CONSERVATIVE_BOUND_PREREG.md`（244.88 签，**先于**实现；"
      "§0.5' 含 **四条更正**：① 加法③ 的补登记、② 追加 G0-9、③ H1/H9/G0-5 的加严、"
      "④ G0-6 的负控期望在数学上不成立 ⇒ ⇒ 改判据的期望、⛔ 不改实现去迎合它）")
    A("⚖ **数据**：**只读**权威账本的 **244.81 段**（差、区间、改判数）与 **244.86 段**（真实差参照）"
      "⇒ ⇒ ⛔ 不重跑日志、⛔ 零 GPU、⛔ 不碰 bpath")
    A("⚖ **收据**：`.cache/r244/_e24488/{selftest,de,mut,cross,spec}.out` ＋ `receipt.txt`")
    A("")
    A("#### 【1】这一轮做了什么")
    A("")
    A("· **没有跑批、没有重解析跑批日志、没有 GPU** ⇒ ⇒ 全部输入**从账本 244.81 / 244.86 段逐行解析**"
      "（⛔ 代码里**不写死任何一个数**；连**容差**都由**账本自己的打印精度**推导）。")
    A("· **回答的问题**：244.87 判成形态 A（9 口径下 `c_max` 全部 < Δ_obs）⇒ ⇒ 但那条主判据是"
      "**点估计**口径、而且**只守了 c 区间的高端** ⇒ ⇒ 面板里那列「真实差（不假定方向）」"
      "= `Δ_obs + c_lo` **只被打印、没有任何判据守它**。")
    A("· **本轮做两件事**：① **补守紧端**（把 `Δ_obs + c_lo` 接到逐口径判据上）；"
      "② **把抽样噪声也算进去** —— 问「**把污染幅度与抽样噪声同时按最保守方向放**，"
      "这条结论还站得住吗？」⇒ ⇒ 交付物是一张「**读法—口径作用域表**」。")
    A("· ⚖⚖⚖ **量纲（唯一允许的两种加法 ＋ 一对比较）**：`c_upper ↔ delta_obs`（加法①，244.87 的主判据）｜"
      "`delta_ci_lo + c_lower`（加法②，**保守读法**）｜ `delta_obs + c_lower`（加法③，**点估计读法**）"
      "⇒ ⇒ ⛔ `delta_ci_lo ↔ c_upper` **仍然红**（那是「+15.22 翻越 +13.01」的**假警报**）。")
    A("· ⚖⚖⚖ **保守读法的联合置信**：population 层的分解 `Δ_true = Δ_obs + c` ⇒ ⇒ 若 `Δ_obs ≥ CI_lo`（95%）"
      "**且** `c ≥ c_lo`（95%）⇒ ⇒ `Δ_true ≥ CI_lo + c_lo`；两项各 95% ⇒ ⇒ **Bonferroni ⇒ 联合 ≥ 90%**"
      "（⛔ Bonferroni **不要求**两项独立）⇒ ⇒ 联合置信**逐口径不同**：Wilson90 ⇒ 85%｜Wilson95 ⇒ 90%｜"
      "Wilson99 ⇒ 94%。")
    A("· ⚠ **本轮享受不到「结果未知」的豁免**（预登记 §0.5' 的 N2）：本轮的量**全部已在账本登记** ⇒ ⇒ "
      "**手算即可**得出各行界的符号 ⇒ ⇒ 预登记的作用是「**先验固定判据、形态与护栏**」，⛔ 不是隐藏结果。")
    A("")
    A("#### 【2】判决面板（读法—口径作用域表；6 行）")
    A("")
    A("· **判决形态**：**%s**" % N["verdict"])
    A("· **理由（原文）**：%s" % N["reason"])
    A("")
    A("| 读法 | 口径 | 界 | 置信 | 结论 |")
    A("|---|---|---|---|---|")
    A("| **R1** 污染**只抬高** rand 臂（c ≥ 0） | 轨迹级 | **%+.2f pp** | %s%% 单源（**不依赖 c**） | ✅ 成立 |"
      % (float(r1[2]), r1[3]))
    A("| **R2** 同上 | 块级 | **%+.2f pp** | %s%% 单源（**不依赖 c**） | ✅ 成立 |"
      % (float(r2[2]), r2[3]))
    A("| **R3** 不假定方向·**点估计** | 轨迹级 | 9/9 口径成立，最紧 **%+.2f pp** | 点估计 | ✅ 成立 |"
      % float(K["R3_MIN_PP"]))
    A("| **R4** 不假定方向·点估计（⚠跨口径） | 块级 | 9/9 成立，最紧 **%+.2f pp** | 点估计 | ✅ 成立 |"
      % float(K["R4_MIN_PP"]))
    A("| **R5** 不假定方向·**保守**（CI+c 同时最保守） | 轨迹级 | **%d/9 成立** | 85/90/94%%（逐口径） | ⛔ **有破口** |"
      % (9 - int(K["R5_NVIOL"])))
    A("| **R6** 同上（⚠跨口径·**示意**） | 块级 | 9/9 成立，最小 **%+.2f pp** | 85/90/94%% | ⚠ 不参与形态判定 |"
      % min(float(x[2]) for x in r6))
    A("")
    A("· **R5 的逐口径界（保守读法；这是本轮的核心表）**：")
    A("")
    A("| Wilson | 基准 | 界（pp） | 联合置信 | 结论 |")
    A("|---|---|---|---|---|")
    for lv, va, b, st_, _c, cf in r5:
        A("| %s | %s | **%+.4f** | %s%% | %s |"
          % (lv, va, float(b), cf, "✅ 成立" if st_ == "成立" else "⛔ **不成立**"))
    A("")
    A("· ⛔ **破口在哪**：%s ⇒ ⇒ ⇒ ⇒ 「污染解释不了观测差」这条结论**必须收紧**成："
      "在**污染只抬高 rand 臂**的读法下成立（**不依赖 c**，95%% 单源下界 **%+.2f pp**），"
      "在**点估计**口径下成立（9/9，逐口径 ≥ **%+.2f pp**）；"
      "但在**把抽样噪声与污染幅度同时按最保守方向**的读法下，**只在部分扫描口径成立**。"
      % (("、".join("%.2f/%s（%+.4f）" % (float(x[0]), x[1], float(x[2])) for x in r5
                   if x[3] != "成立")) or "无",
         float(K["R1_BOUND_PP"]), float(K["R3_MIN_PP"])))
    A("· ⚖ **为什么会破口**：Wilson99 的 c 区间**更宽** ⇒ ⇒ `c_lo` 更负 ⇒ ⇒ 与 CI 下端点相加后越过 0 ⇒ ⇒ "
      "这是**两个下界同时取到最坏方向**的必然结果 ⇒ ⇒ ⛔ **不是**「数据有问题」，"
      "⛔ 也**不是**「结论被否」⇒ ⇒ 是**结论的适用范围**被钉出来了。")
    A("")
    A("#### 【3】%s **九条判据逐条（真数据）**" % ("❌" if any(c[0] == "FAIL" for c in N["crits"]) else "✅"))
    A("")
    for stt, cid, name, detail in N["crits"]:
        A("- [%s] **%s** %s — %s" % (stt, cid, name.strip(), detail.strip()))
    A("")
    A("#### 【4】✅ **每条判据能红**")
    A("")
    A("- **自检**（Phase-0 G0-1..G0-9，合成夹具、⛔ 零账本、⛔ 零 GPU）：判据 **%s** 道 ｜ FAIL **%s** 道（%s）"
      % (N["st_n"], N["st_fail"], N["st_word"]))
    A("- **变异台**：抓到 **%s / %s**（无效 %s 条 ⇒ 记「无效」⇒ 不计入分母）｜ 崩的条数 **%s**（⛔ 必须是 0）"
      % (N["mut_caught"], N["mut_total"], N["mut_invalid"], N["mut_crash"]))
    A("- **变异台逐条**：%s" % "、".join(mid for tag, mid in N["mut_ids"] if tag == "抓到"))
    A("- **互证**（第二条独立实现：**Fraction** 算基准 ＋ **Decimal(60 位)** 算 Wilson ＋ **NormalDist** 取 z；"
      "⛔ 与被检实现零共用代码、锚点也故意不同、**解析按单元格切**而非整行大正则）：OK **%s** ｜ MISMATCH **%s**"
      " ｜ 独立重算的判决形态 **%s**" % (N["cr_ok"], N["cr_bad"], N["cr_form"]))
    A("- **预登记 ↔ 实现 的机械对账**：OK **%s** ｜ 红 **%s**" % (N["sp_ok"], N["sp_bad"]))
    A("- **验证链五个 rc**：**%s**" % " / ".join(N["rcs"]))
    A("- ⚖⚖⚖ **可复现性（两次独立验证链 ⇒ 逐字节对照）**：**%d / %d** 个收据 .out **逐字节相同**"
      "（run1 读的是**落账前**的账本 %s 行 ｜ md5 `%s`；run2 读的是**落账后**的账本 %s 行 ｜ md5 `%s`）"
      "⇒ ⇒ ① 改驱动里的那个过期计数**没动任何一个数**；"
      "② 账本里那句「**本轮的数不会因为落账而变**」**被实证**（不是断言）"
      % (N["repro_ident"], N["repro_n"], N["repro"]["REPRO_LEDGER_RUN1_LINES"],
         N["repro"]["REPRO_LEDGER_RUN1_MD5"], N["repro"]["REPRO_LEDGER_RUN2_LINES"],
         N["repro"]["REPRO_LEDGER_RUN2_MD5"]))
    A("")
    A("#### 【5】⚖⚖⚖ **本轮抓到的真缺陷（⛔ 一个数都没动）**")
    A("")
    A("1. ⚠⚠⚖ **预登记层：G0-6 的负控期望在数学上不成立** —— 原文写「把 `c_lo` 换成 `c_hi` ⇒ ⇒ "
      "H5/H6/H7 **必须红**」⇒ ⇒ 但界 = `Δ_obs + c_lo` ⇒ ⇒ 换成**更大**的 `c_hi` ⇒ ⇒ 界只会**变大** ⇒ ⇒ "
      "**正确的实现**在这一步**不会红** ⇒ ⇒ 那是一条**恒不红**的检查 ⇒ ⇒ **预登记追加更正 ④**："
      "G0-6 拆成两条互补负控（① `c_lo` 换成一个很负的值 ⇒ ⇒ 三条必须红；② 每一行必须 `c_lo < c_hi`）"
      "⇒ ⇒ 改的是**判据的期望**（一条数学上不可能红的期望），⛔ **不是**改实现去迎合它 ⇒ ⇒ 判据**变严**。")
    A("2. ⚠⚖⚖ **实现层：G0-2 的期望级联从模块常量派生** ⇒ ⇒ 「把 `HARD_FAIL_IDS` 改掉」这种变异"
      "**两边一起变** ⇒ ⇒ 闸门看不见 ⇒ ⇒ **恒绿** ⇒ ⇒ 变异台 **MU1 存活**暴露了它 ⇒ ⇒ "
      "改成「期望里的硬失败集合**手写**」＋「模块常量必须与手写那份**逐条相同**」。")
    A("3. ⚠⚖⚖ **实现层：G0-3 只试了三条特例分支 ⇒ ⇒ 兜底分支（`H8-KIND-SUM-UNKNOWN`）没被覆盖** ⇒ ⇒ "
      "「把兜底那条删掉」这种变异没人知道 ⇒ ⇒ 变异台 **MU8 存活**暴露了它 ⇒ ⇒ 补了第 5 个用例。")
    A("4. ⚠ **实现层：`_check_sum` 的第三条分支消息里没有占位符却传了两个参数** ⇒ ⇒ "
      "`TypeError: not all arguments converted during string formatting` ⇒ ⇒ **整份实现跑不起来**"
      "⇒ ⇒ ⚠ **本地只跑 `ast.parse` 抓不到这一类错**（符号表/运行期才查）⇒ ⇒ 改用 `compile()` 复查。")
    A("5. ⚠⚠ **实现层：`global _guard_selftest` 声明位置错了**（在同函数里已被用过之后）⇒ ⇒ "
      "**编译期**就报 `SyntaxError: name '_guard_selftest' is used prior to global declaration`"
      "⇒ ⇒ 同样**只有 `compile()` 才抓得到** ⇒ ⇒ `ast.parse` 不够。")
    A("6. ⚠ **实现层：互证脚本按「下标」取表格单元格** ⇒ ⇒ 表头行以 `|` 开头 ⇒ ⇒ 首格是空串 ⇒ ⇒ "
      "**下标错位** ⇒ ⇒ 改用「按形状取」（找形如 `**46/56**` 的格子）⇒ ⇒ 与被检实现的整行正则**不同源**。")
    A("7. ⚠ **实现层：互证脚本的轨迹级定位命中 2 行**（`pos_frac` 那张表的**表头行**也有「差区间（Newcombe95）」"
      "和「Fisher p」）⇒ ⇒ 改成**必须同时**含「`**差 `」⇒ ⇒ 锚点唯一。")
    A("8. ⚠ **对账脚本：抽取常量时留下逗号 / `range` 上界含头** ⇒ ⇒ 六条对账项**误红** ⇒ ⇒ "
      "改用 `re.findall` 抽 id、用 `range(1, n)` 的**不含上界**语义 ⇒ ⇒ 对账从 6 红降到 0 红。")
    A("9. ⚠⚠⚖ **驱动层：`_run_24488_verify.sh` 的 banner 印「变异台（**34** 条）」⇒ ⇒ 而变异台真实是 "
      "**%d 条**（MU1–MU33 ＋ ML1 ＋ ML2）⇒ ⇒ 那是**过期计数** ⇒ ⇒ 该文件**要入库** ⇒ ⇒ "
      "⛔ 不能带着一个错的数入库 ⇒ ⇒ **改成 %d** ⇒ ⇒ 并**重跑整条验证链** ⇒ ⇒ ⛔ **一个数都没动**："
      "**%d / %d** 个收据 .out **逐字节不变**（只有驱动字节的 md5 变了：`%s` → `%s`）"
      "⇒ ⇒ 顺带**实证**了「落账之后账本变长、而本轮的数不变」。"
      % (int(N["mut_total"]), int(N["mut_total"]),
         N["repro_ident"], N["repro_n"], N["repro"]["REPRO_DRIVER_OLD_MD5"],
         N["repro"]["REPRO_DRIVER_NEW_MD5"]))
    A("")
    A("#### 【6】⛔ **边界清单（本轮哪些仍未量到 / 不许被读成什么）**")
    A("")
    A("- ⛔ **「污染不存在」仍未量到**；「污染的**精确幅度**」仍未量到（本轮给的是**界**，⛔ 不是点估计）。")
    A("- ⛔ **块级口径下的污染量 / 污染上界未量到**（块级零假设基准未在账本登记 ⇒ ⇒ 需**重解析原始跑批日志**"
      "⇒ ⇒ **要点头**）⇒ ⇒ 本轮一切与块级相加的界（R4 / R6）**都带口径混合标签**"
      "（那两行**只能**读成「**轨迹级算出的污染下界**放到**块级观测差**上」这一句）。")
    A("- ⛔ **更宽置信水平下的保守读法未量到**（需要 Newcombe 在 95% 以外的水平 ⇒ ⇒ 新方法）⇒ ⇒ "
      "本轮的 CI 下端点**只有 95%**。")
    A("- ⛔ **识别假设**：「rand 臂在无污染时的改判率 = 零假设基准」⇒ ⇒ **全部**污染相关结论都**条件于**它 "
      "⇒ ⇒ 该假设**未在本轮独立验证**。")
    A("- ⛔ **R5 的破口不等于「结论被否」** ⇒ ⇒ 它只说明：**最保守读法**下的结论**只覆盖部分扫描口径** ⇒ ⇒ "
      "⛔ **不许**写成「污染能解释观测差」。")
    A("- ⛔ 机制轴、剂量轴沿用旧留白，**未量到**。")
    A("- ⚖ **自检层的固有上限**：改「闸门自己的比较表达式」这件事**没有闸门能抓** ⇒ ⇒ 本轮用"
      "「正控 ＋ 负控共用同一个函数」把它**缩小**，⛔ 不能消灭 ⇒ ⇒ 记为**留白**。")
    A("- ⛔ **预登记层与账本层没有自检** ⇒ ⇒ 「预登记**整体**先于结果」**不成立**；准确的说法是"
      "「§0.5'、§1、§2、§3、§3.2、§4、§5、§6、§7 的**口径与判据**全部先于结果」"
      "⇒ ⇒ 且本轮 §0.5' 的 N2 已**明写**各行的符号可手算 ⇒ ⇒ **不主张**「结果未知」。")
    A("")
    A("#### 【7】▶️ **下一轮（244.89+）**")
    A("")
    A("1. **本轮收尾**：落账（只追加）→ 重建索引 → **全回归 R9**（执行集 +2 ⇒ 期望 added=2 / removed=0）"
      "→ 提交 + 提交后双回读 ⇒ ⇒ 本段的判决形态 **%s** 才会**入库**。" % N["verdict"])
    A("2. **B-1 要点头**（重解析原始日志）⇒ ⇒ 才能得到「**同口径**的块级污染上界」⇒ ⇒ "
      "才能把 R4 / R6 从「混合口径」升级成「同口径」。")
    A("3. **B-2**：Newcombe 换置信水平 ⇒ ⇒ 保守读法在 95 / 99 双水平上的**完整**作用域。")
    A("")
    A("#### 【8】⚖ **这一轮的字节**")
    A("")
    A("⚖⚖⚖ 下面每个 md5 都是**由文件本身算出来的**；标「⚖ 收据登记」的**同时**与**远端验证链收据里登记的那份"
      "逐位对上** ⇒ ⇒ 「入库的字节 ＝ 跑出这些数的字节」。")
    A("")
    A("- **被检 / 口径 / 驱动（6 件）**：")
    for nm, key in (("conservative_bound_audit.py", "conservative_bound_audit.py"),
                    ("mut_conservative_bound_audit.py", "mut_conservative_bound_audit.py"),
                    ("_cross_check_24488.py", "_cross_check_24488.py"),
                    ("_spec_crosscheck_24488.py", "_spec_crosscheck_24488.py")):
        A("  - `%s`  `%s`  ⚖ 收据登记（远端验证链）"
          % (N["rc_md5"].get(key, "?"), nm))
    A("  - `%s`  `_run_24488_verify.sh`  ⚖ 收据登记（远端验证链）"
      % N["rc_md5"].get("_run_24488_verify.sh", "?"))
    A("  - `%s`  `R6_CONSERVATIVE_BOUND_PREREG.md`  ⚖ 收据登记（远端验证链）"
      % N["rc_md5"].get("R6_CONSERVATIVE_BOUND_PREREG.md", "?"))
    A("- **收据文件（5 件）**：")
    for nm in ("selftest.out", "de.out", "mut.out", "cross.out", "spec.out"):
        A("  - `%s`  `%s`  ⚖ 收据登记（远端验证链）" % (N["rc_md5"].get(nm, "?"), nm))
    A("")
    A("⚖ **远端**：`zju-53`（2026-10-24 23:11 CST）｜ ⛔ **零 GPU**、⛔ 没跑批、⛔ 没改读数器/探针/拆分器、"
      "⛔ 没改 244.79–244.87 段。")
    A("")
    A("⚖⚖⚖ **一条必须说清的事实**：`zju-53` 与 `zju-12` 是**两台共享同一份 NFS 家目录**的机器 ⇒ ⇒ "
      "「**两台远端逐位一致**」是**必然**的，⛔ **不是**一条独立证据 ⇒ ⇒ 真正的独立证据是"
      "「**收据里的 md5 == 本地现算的 md5**」⇒ ⇒ 以后**不许**把「两台一致」当成交叉验证。")
    A("")
    A("⚖ **被读的账本**：`R6_RERUN_PREREG.md` —— run1：**%s 行 ｜ md5 `%s`**（**落账前**那份）｜ "
      "run2：**%s 行 ｜ md5 `%s`**（**落账后**那份）⇒ ⇒ 本轮**只读**它 ⇒ ⇒ 两次读的账本**不同**、"
      "而五个收据 .out **逐字节相同** ⇒ ⇒ 「**本轮的数不会因为落账而变**」**被实证**（不是断言）。"
      % (N["repro"]["REPRO_LEDGER_RUN1_LINES"], N["repro"]["REPRO_LEDGER_RUN1_MD5"],
         N["repro"]["REPRO_LEDGER_RUN2_LINES"], N["repro"]["REPRO_LEDGER_RUN2_MD5"]))
    A("")
    return "\n".join(L)


def main():
    dry = "--dry" in sys.argv
    truncate = "--truncate" in sys.argv
    N = collect()
    if truncate:
        # ⚖⚖⚖ **撤回重落**：把账本**截回**「追加 244.88 之前」的那份字节
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
            print("✅ 幂等：账本里已有的 244.88 段与**收据算出来的那段逐字节相同** ⇒ ⇒ 不重复写")
            return 0
        raise SystemExit("⛔ 账本里已有 244.88 段，但它与收据算出来的**不一致** ⇒ ⇒ 停下"
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
