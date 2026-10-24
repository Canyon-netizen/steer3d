#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⚖ **244.86 落账**（只追加；⛔ 追加段里不许有围栏；⛔ 所有数都从收据抠，⛔ 不手抄）。

**这一段记什么**：244.81 那个固定剂量判决（w 臂 46/56 vs rand 臂 29/56，差 +30.36 pp）的
**对照臂**是不是被 244.84/244.85 查到的「`r₀` 与 steering 簇 A 对齐」这条**污染**给抬起来了
⇒ ⇒ 把「rand 臂的**边际**改判率 vs 它自己那层零假设」做成**可判读的五态**（N-A..N-E），
并把「污染最多能把 +30.36 pp 抬高到多少」从**纯留白**变成**有界命题**。

⚖ **口径真相源**：`.cache/xcheck/R6_CONTROL_ARM_NULL_PREREG.md`（244.86 签，**先于实现**；
§0.5 含 **两条更正**：H8 的机械形式、＋ N-B/N-C 的优先读法）
⚖ **数据**：**只读**权威账本的 244.81 段（⛔ 不重跑日志、⛔ 零 GPU、⛔ 不碰 bpath）
⚖ **收据**：`.cache/r244/_e24486/{selftest,de,mut,cross,spec}.out` ＋ `.cache/r244/_e24486/receipt.txt`
（⛔ **注意**：`receipt` 那份的后缀是 **`.txt`**、**不是** `.out` ⇒ ⇒ 别按 `.out` 去 cat）
"""

import hashlib
import io
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
LEDGER = os.path.join(REPO, ".cache", "xcheck", "R6_RERUN_PREREG.md")
EV = os.path.join(REPO, ".cache", "r244", "_e24486")
DEV = os.path.join(REPO, ".cache", "r244")
XCH = os.path.join(REPO, ".cache", "xcheck")
TITLE = "## 修订 244.86 —— "

# ⚖⚖⚖ **这一轮的字节清单**（本地路径，⛔ md5 **由文件本身算出**）
ROUND_FILES = [
    ("control_arm_null_audit.py", os.path.join(DEV, "control_arm_null_audit.py")),
    ("mut_control_arm_null_audit.py", os.path.join(DEV, "mut_control_arm_null_audit.py")),
    ("_cross_check_24486.py", os.path.join(DEV, "_cross_check_24486.py")),
    ("_spec_crosscheck_24486.py", os.path.join(DEV, "_spec_crosscheck_24486.py")),
    ("_run_24486_verify.sh", os.path.join(DEV, "_run_24486_verify.sh")),
    ("R6_CONTROL_ARM_NULL_PREREG.md",
     os.path.join(XCH, "R6_CONTROL_ARM_NULL_PREREG.md")),
]

# ⚖ **远端验证链的收据文件**（⛔ `receipt.txt` 那份的后缀是 **`.txt`**、**不是** `.out`
#   ⇒ ⇒ 它**不能**放进上面那个 `{...}.out` 的花括号简写里）
RECEIPT_FILES = ["selftest.out", "de.out", "mut.out", "cross.out", "spec.out"]

# ⚖⚖⚖ **本轮「撤回重落」过程中留下的中间字节指纹（历史事实，⛔ 不可复算）**
#   ⇒ ⇒ 这两个 md5 **不是**「跑出来的数」，而是**本段被改写过程中真实存在过的两版账本**
#   ⇒ ⇒ 前两版**都只存在于本地、从未提交** ⇒ ⇒ 全回归 R7 **只以最终版为准**
#   ⇒ ⇒ **自检**：当前账本的 md5 **必须不等于**这两个 ⇒ ⇒ 否则说明本段**又被重落**了
#   ⇒ ⇒        ⇒ ⇒ 那时【8】节的历史指纹列表**已经过期** ⇒ ⇒ 必须更新
SUPERSEDED_LEDGER_MD5 = [
    ("81f7e4ec403c0ae927a49f8c18e40b5f",
     "第 1 版：【8】节的字节清单三处不准（见【5】第 6 条）"),
    ("420b60384f8a60e2746648bc191bc218",
     "第 2 版：清单已修好，但【5】节仍写「五个真缺陷」"),
    ("4129538bf761f3e209765395d9e067f8",
     "第 3 版：清单与【5】已修好，但**预登记 §0.5 更正 ② 末尾三句引用了真数据结果**"
     "这件事未被发现（见【5】第 7 条）"),
]


def _md5_file(path):
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _read(p):
    with io.open(p, encoding="utf-8", newline="") as fh:
        return fh.read()


def _need(p):
    if not os.path.isfile(p):
        raise SystemExit("⛔ 缺收据：%s" % p)
    return _read(p)


def collect():
    """⚖ 全部数**从收据抠**（⛔ 不手抄）。"""
    st = _need(os.path.join(EV, "selftest.out"))
    de = _need(os.path.join(EV, "de.out"))
    mu = _need(os.path.join(EV, "mut.out"))
    cr = _need(os.path.join(EV, "cross.out"))
    sp = _need(os.path.join(EV, "spec.out"))
    rc = _need(os.path.join(EV, "receipt.txt"))

    N = {}

    # ---- 机器可读键值块（判决面板的数都在里面）----
    m = re.search(r"===== AUDIT_KEYS =====\n(.*?)\n===== END_AUDIT_KEYS =====", de, re.S)
    if not m:
        raise SystemExit("⛔ 收据 de.out 里没有 AUDIT_KEYS 块 ⇒ ⇒ 无数可抠 ⇒ 中止")
    K = {}
    for ln in m.group(1).splitlines():
        if "=" in ln:
            k, v = ln.split("=", 1)
            K[k.strip()] = v.strip()
    N["K"] = K

    def kv(key):
        if key not in K:
            raise SystemExit("⛔ AUDIT_KEYS 里没有 `%s` ⇒ ⇒ 中止" % key)
        return K[key]

    # ---- 判决形态 ----
    mv = re.search(r"^VERDICT=(\S+)$", de, re.M)
    if not mv:
        raise SystemExit("⛔ 收据 de.out 里没有 VERDICT= ⇒ ⇒ 中止")
    N["verdict"] = mv.group(1)
    if kv("VERDICT") != N["verdict"]:
        raise SystemExit("⛔ VERDICT 行与 AUDIT_KEYS 里的 VERDICT 不一致 ⇒ ⇒ 中止")

    # ---- 真数据判据逐条 ----
    N["de_rows"] = re.findall(r"^\[(PASS|FAIL)\]\s+(H[0-9]+-[A-Z]+)\s+(.*)$", de, re.M)
    if not N["de_rows"]:
        raise SystemExit("⛔ 收据 de.out 里没有真数据判据行 ⇒ ⇒ 中止")
    N["de_n"] = len(N["de_rows"])
    N["de_pass"] = sum(1 for r in N["de_rows"] if r[0] == "PASS")
    N["de_fail"] = N["de_n"] - N["de_pass"]
    N["de_ids"] = [r[1] for r in N["de_rows"]]
    msum = re.search(r"判据汇总：(\d+) 条 ｜ PASS (\d+) ｜ FAIL (\d+)", de)
    if not msum:
        raise SystemExit("⛔ 收据 de.out 里没有「判据汇总」⇒ ⇒ 中止")
    if (int(msum.group(1)), int(msum.group(2)), int(msum.group(3))) != \
            (N["de_n"], N["de_pass"], N["de_fail"]):
        raise SystemExit("⛔ 「判据汇总」与逐条数对不上 ⇒ ⇒ 中止")

    # ---- 理由句（判决面板印的那一句）----
    mwhy = re.search(r"^理由：(.*)$", de, re.M)
    if not mwhy:
        raise SystemExit("⛔ 收据 de.out 里没有「理由：」行 ⇒ ⇒ 中止")
    N["why"] = mwhy.group(1).strip()

    # ---- 自检（Phase-0）----
    mg = re.search(r"自检（Phase-0 G0-1\.\.G0-7）：(\d+) 条 ｜ FAIL (\d+) 条", st)
    if not mg:
        raise SystemExit("⛔ 收据 selftest.out 里没有自检汇总 ⇒ ⇒ 中止")
    N["st_n"], N["st_fail"] = int(mg.group(1)), int(mg.group(2))
    N["gates"] = re.findall(r"^\[(PASS|FAIL)\]\s+(G0-\d)", st, re.M)
    if len(N["gates"]) != N["st_n"]:
        raise SystemExit("⛔ 闸门行数与自检汇总对不上 ⇒ ⇒ 中止")
    if N["st_fail"] != 0:
        raise SystemExit("⛔ 自检有红项 ⇒ ⇒ 本轮不落账 ⇒ 中止")

    # ---- 变异台 ----
    mm = re.search(r"变异台：抓到 (\d+) / (\d+)（无效 (\d+) 条", mu)
    if not mm:
        raise SystemExit("⛔ 收据 mut.out 里没有变异台汇总 ⇒ ⇒ 中止")
    N["mut_caught"], N["mut_total"], N["mut_invalid"] = (int(mm.group(1)),
                                                         int(mm.group(2)),
                                                         int(mm.group(3)))
    mc = re.search(r"崩的条数：(\d+)", mu)
    if not mc:
        raise SystemExit("⛔ 收据 mut.out 里没有「崩的条数」⇒ ⇒ 中止")
    N["mut_crash"] = int(mc.group(1))
    N["mut_ids"] = re.findall(r"^\[抓到\] (\S+)", mu, re.M)
    if len(N["mut_ids"]) != N["mut_caught"]:
        raise SystemExit("⛔ 变异台逐条数与汇总对不上 ⇒ ⇒ 中止")

    # ---- 互证 ----
    mx = re.search(r"互证：OK (\d+) ｜ MISMATCH (\d+)", cr)
    if not mx:
        raise SystemExit("⛔ 收据 cross.out 里没有互证汇总 ⇒ ⇒ 中止")
    N["cr_ok"], N["cr_bad"] = int(mx.group(1)), int(mx.group(2))
    mv2 = re.search(r"^独立重算的判决形态：(\S+)$", cr, re.M)
    if not mv2:
        raise SystemExit("⛔ 收据 cross.out 里没有「独立重算的判决形态」⇒ ⇒ 中止")
    N["cr_verdict"] = mv2.group(1)
    if N["cr_verdict"] != N["verdict"]:
        raise SystemExit("⛔ 两条实现的判决形态不一致（%s vs %s）⇒ ⇒ 中止"
                         % (N["cr_verdict"], N["verdict"]))

    # ---- 预登记对账 ----
    ms = re.search(r"对账条数：OK (\d+) ｜ 红 (\d+)", sp)
    if not ms:
        raise SystemExit("⛔ 收据 spec.out 里没有对账汇总 ⇒ ⇒ 中止")
    N["sp_ok"], N["sp_bad"] = int(ms.group(1)), int(ms.group(2))

    # ---- 收据（host / 五个 rc / 字节清单）----
    mh = re.search(r"^host=(\S+)\s+date=(.*)$", rc, re.M)
    if not mh:
        raise SystemExit("⛔ 收据 receipt.txt 里没有 host/date ⇒ ⇒ 中止")
    N["rc_host"], N["rc_date"] = mh.group(1), mh.group(2).strip()
    mr = re.search(r"SELFTEST_RC=(\d+)\s+DE_RC=(\d+)\s+MUT_RC=(\d+)\s+CROSS_RC=(\d+)\s+SPEC_RC=(\d+)",
                   rc)
    if not mr:
        raise SystemExit("⛔ 收据 receipt.txt 里没有五个 rc ⇒ ⇒ 中止")
    N["rcs"] = [int(x) for x in mr.groups()]
    if any(x != 0 for x in N["rcs"]):
        raise SystemExit("⛔ 五个 rc 里有非 0 ⇒ ⇒ 本轮不落账 ⇒ 中止")
    N["rc_md5"] = {}
    for mm2 in re.finditer(r"^\s*([0-9a-f]{32})\s+(/\S+)$", rc, re.M):
        N["rc_md5"][os.path.basename(mm2.group(2))] = mm2.group(1)
    mled = re.search(r"ledger_lines=(\d+)\s+ledger_md5=([0-9a-f]{32})", rc)
    if not mled:
        raise SystemExit("⛔ 收据 receipt.txt 里没有账本行数/md5 ⇒ ⇒ 中止")
    N["led_lines"], N["led_md5"] = int(mled.group(1)), mled.group(2)
    return N


def build(N):
    """⚖ 拼出 244.86 段（⛔ 追加段里不许有围栏、不许有反斜杠）。"""
    # ⚖⚖⚖ **自证 ①**：当前账本的 md5 **必须不等于**任何一版「已作废的中间字节」
    #   ⇒ ⇒ 否则说明本段**又被重落**了 ⇒ ⇒ 【8】节的历史指纹列表**已经过期**
    #   ⇒ ⇒ ⇒ 必须更新 `SUPERSEDED_LEDGER_MD5` ⇒ ⇒ **不许**默默再落一版
    _cur = _md5_file(LEDGER)
    for _h, _why in SUPERSEDED_LEDGER_MD5:
        if _cur == _h:
            raise SystemExit("⛔ 当前账本 md5 == 已作废的中间版（%s）⇒ ⇒ 本段**又被重落**了 "
                             "⇒ ⇒ 【8】节的历史指纹列表已过期 ⇒ ⇒ 必须更新 "
                             "`SUPERSEDED_LEDGER_MD5`" % _why)
    K = N["K"]
    L = []

    def A(s=""):
        L.append(s)

    A("## 修订 244.86 —— ⚖⚖⚖⚖⚖ **对照臂的零假设地位**：rand 臂的**边际**改判率"
      "**没有可检出的**高于零假设（形态 **%s**）⇒ ⇒ 污染幅度**有上界**："
      "c_max = **+%.2f pp** ｜ 真实差（**不假定方向**）[**+%.2f**, **+%.2f**] pp ｜ "
      "（**假定污染方向为抬高**）[**+%.2f**, **+%.2f**] pp；⛔ **不是**「对照臂干净」"
      % (N["verdict"], float(K["C_MAX_PP"]), float(K["IV_NO_LO_PP"]), float(K["IV_NO_HI_PP"]),
         float(K["IV_UP_LO_PP"]), float(K["IV_UP_HI_PP"])))
    A("")
    A("⚖ **口径真相源**：`.cache/xcheck/R6_CONTROL_ARM_NULL_PREREG.md`"
      "（244.86 签，**先于实现**；§0.5 含 **两条更正**：H8 的机械形式、＋ N-B/N-C 的优先读法）")
    A("⚖ **数据**：**只读**权威账本的 **244.81 段**（⛔ 不重跑日志、⛔ 零 GPU、⛔ 不碰 bpath）")
    A("⚖ **收据**：`.cache/r244/_e24486/{selftest,de,mut,cross,spec}.out`"
      " ＋ `.cache/r244/_e24486/receipt.txt`（⛔ `receipt` 那份是 **`.txt`**、**不是** `.out`）")
    A("")
    A("#### 【1】这一轮做了什么")
    A("")
    A("· **没有跑批、没有重解析跑批日志、没有 GPU** ⇒ ⇒ 全部输入**从账本 244.81 段逐行解析**"
      "（⛔ 代码里**不写死任何一个数**；连**容差**都由**账本自己的打印精度**推导）。")
    A("· **回答的问题**：244.84/244.85 只测了**向量**（`r₀` 与 steering 簇 A 对齐），"
      "⛔ **没有测「它有没有改变 rand 臂的改判率」** ⇒ ⇒ 本轮补这一口。")
    A("· ⚖⚖⚖ **共线性必须说清**：**污染（共享 `w_p2a` 成分）与「问题本身容易被 steering 移动」"
      "是共线的** ⇒ ⇒ 两臂都注入 steering ⇒ ⇒ 「两臂改判相关」**不能**区分"
      "「共享成分」与「题目可移动性」⇒ ⇒ 本轮**只给边际结论**。")
    A("· ⚖ **本轮享受不到「结果未知」的豁免**：用到的**每一个原始数**（29/56、0.4911、6/28 …）"
      "**都已在 244.81 段登记** ⇒ ⇒ 本轮**不是「首次发现」**；新的是 N1–N5 那五条"
      "（见预登记 §0 的诚实边界）。")
    A("")
    A("#### 【2】判决面板（rand 臂 vs 它自己那层零假设）")
    A("")
    A("· **判决形态**：**%s**" % N["verdict"])
    A("· **理由（原文）**：%s" % N["why"])
    A("")
    A("| 项 | 口径 | 实测 |")
    A("|---|---|---|")
    A("| 零假设（Q2） | 非零格公平硬币、零格恒 False、阈值 `nT·2 > m`、零格进分母 | — |")
    A("| 零分布（Q3/Q4） | 轨迹级 = **Poisson-binomial**（%s 个 base：零格轨迹 base=0.25、"
      "其余 base=0.5）；块级 = `base_a × base_b` | 配对未知 ⇒ ⇒ 取**两个极端** |"
      % K["N_TRAJ"])
    A("| 基准（Q2/H1） | 由 `(n_nz,n_zero)` 分布**现算** | w = `%s` ｜ rand = `%s` "
      "⇒ ⇒ 账本印的 **0.4955 / 0.4911** **复算得出来**"
      % (K["BASE_W_CALC"], K["BASE_R_CALC"]))
    A("| rand 轨迹级（H3） | 观测 **%s/%s** ｜ 零分布均值 `%s` ｜ 单侧上尾 p = **`%s`**"
      " ⇒ ⇒ **与零假设不可区分**（p ≥ 0.05）"
      % (K["OBS_R"], K["N_TRAJ"], K["BASE_R_CALC"], K["P_TRAJ_R"]))
    A("| rand 块级（H4） | 观测 **%s/%s** ｜ 同块：均值 `%s`、p = **`%s`** ｜ "
      "异块：均值 `%s`、p = **`%s`** ⇒ ⇒ **两端都**不可区分"
      % (K["BLK_R"], K["N_BLOCKS"], K["Q_MEAN_R_SAME"], K["P_BLK_R_SAME"],
         K["Q_MEAN_R_SPLIT"], K["P_BLK_R_SPLIT"]))
    A("| 逐格前提（Q9/H2） | rand 非零格 **%s** 个、正号 **%s** ｜ 单侧**下尾** p = **`%s`**"
      " ⇒ ⇒ **不判红**（⛔「不显著」是**弱**证据：格不独立 ⇒ p 反保守）"
      % (K["N_NZ_CELLS"], K["N_POS_CELLS"], K["P_CELL_LOWER"]))
    A("| 判别力（H5） | **w 臂在同一条检验下必须显著** | 轨迹级 p = **`%s`** ｜ "
      "块级 p = **`%s`** ⇒ ⇒ **显著** ⇒ ⇒ 这套检验**有牙齿**（不是恒绿）"
      % (K["P_TRAJ_W"], K["P_BLK_W_ONLY"]))
    A("| 幅度上界（Q7/H6） | c_max = rand Wilson95 **上界** − 零假设基准 | **+%.2f pp**"
      "（c_lo = %+.2f pp、c_hi = %+.2f pp）"
      % (float(K["C_MAX_PP"]), float(K["C_LO_PP"]), float(K["C_HI_PP"])))
    A("| 真实差（Q8 ①） | **不假定方向** | **[%+.2f, %+.2f] pp**"
      % (float(K["IV_NO_LO_PP"]), float(K["IV_NO_HI_PP"])))
    A("| 真实差（Q8 ②） | **假定污染方向为抬高**（机制上应当如此，⛔ **没被证明**） | "
      "**[%+.2f, %+.2f] pp**" % (float(K["IV_UP_LO_PP"]), float(K["IV_UP_HI_PP"])))
    A("")
    A("⚖⚖⚖ **措辞纪律（⛔ 不许改口）**：本形态**只**说「rand 臂的**边际**改判率"
      "**没有可检出的**高于零假设」⇒ ⇒ ⛔ **不许**写成「对照臂干净」"
      "⇒ ⇒ 只准写「**在可检出层面**没有」＋「幅度上界是 %+.2f pp」。"
      % float(K["C_MAX_PP"]))
    A("")
    A("⚖ **Wilson 区间（账本印的 vs 现算的）**：rand **[%+.2f, %+.2f]**"
      "（现算 `%s` / `%s`）｜ w **[%+.2f, %+.2f]**（现算 `%s` / `%s`）"
      " ⇒ ⇒ 差都 ≤ 0.002 pp ⇒ ⇒ 账本那两个数**是对的**。"
      % (float(K["WIL_R_LO_PP"]), float(K["WIL_R_HI_PP"]),
         K["WIL_R_LO_PP_CALC"], K["WIL_R_HI_PP_CALC"],
         float(K["WIL_W_LO_PP"]), float(K["WIL_W_HI_PP"]),
         K["WIL_W_LO_PP_CALC"], K["WIL_W_HI_PP_CALC"]))
    A("")
    A("#### 【3】✅ **八条硬判据逐条（真数据：PASS %d ｜ FAIL %d）**"
      % (N["de_pass"], N["de_fail"]))
    A("")
    for st_, cid, detail in N["de_rows"]:
        A("- [%s] **%s** — %s" % (st_, cid, detail))
    A("")
    A("#### 【4】✅ **每条判据能红**")
    A("")
    A("- **自检**（Phase-0 G0-1..G0-7，合成夹具、⛔ 零账本、⛔ 零 GPU）：判据 **%d** 条 ｜ "
      "FAIL **%d** 条（%s）"
      % (N["st_n"], N["st_fail"],
         "、".join("%s=%s" % (g[1], g[0]) for g in N["gates"])))
    A("- **变异台**：抓到 **%d / %d**（无效 %d 条 ⇒ 记「无效」⇒ 不计入分母）｜ "
      "崩的条数 **%d**（⛔ 必须是 0）"
      % (N["mut_caught"], N["mut_total"], N["mut_invalid"], N["mut_crash"]))
    A("- **变异台逐条**：%s" % "、".join(N["mut_ids"]))
    A("- **互证**（第二条独立实现：**精确整数** Poisson-binomial ＋ **根式** Wilson，"
      "⛔ 与被检实现零共用代码、锚点也故意不同）：OK **%d** ｜ MISMATCH **%d** ｜ "
      "独立重算的判决形态 **%s**"
      % (N["cr_ok"], N["cr_bad"], N["cr_verdict"]))
    A("- **预登记 ↔ 实现 的机械对账**：OK **%d** ｜ 红 **%d**" % (N["sp_ok"], N["sp_bad"]))
    A("")
    A("#### 【5】⚠⚖⚖ **本轮抓到的七个真缺陷**（前 **5** 个是**实现的错**，⛔ 不是口径的错，"
      "⇒ ⇒ 每一条都被闸门/变异台当场抓住；⚠ 第 **6** 个是**落账层**的错、"
      "⚠ 第 **7** 个是**预登记层**的错 ⇒ ⇒ 这两个**没有任何闸门覆盖** ⇒ ⇒ "
      "是**人工复核**发现的）")
    A("")
    A("1. **判决映射表把 H3 / H4 也算进「其他硬判据红」** ⇒ ⇒ **N-B / N-C 变成死分支** "
      "⇒ ⇒ **Phase-0 的 G0-2（五个分支必须全部可达）当场判红** ⇒ ⇒ "
      "「其他硬判据」正解是 **H5/H6/H7/H8**（H3/H4 的红**就是信号**）。"
      "⚖ 修的是**实现**，⛔ **没改**预登记的形态集合与触发条件（见预登记 §0.5 更正 ②）。")
    A("2. **H6 把 Q8 的两条区间当成「嵌套」关系** ⇒ ⇒ 写出了一条**错的**恒等式"
      "（真实差两条是**两种不同假设**下的结果：①允许 c 为负、②假设 c≥0 ⇒ ⇒ "
      "⛔ **不一定有包含关系**）⇒ ⇒ **G0-3 / G0-5 当场判红** ⇒ ⇒ "
      "正确的恒等式是「**上端点相同 ＋ 两个下端点各合 Q8 的公式**」。")
    A("3. **I12 的锚点「跨臂 Fisher」在 244.81 段内不唯一**（命中 **4** 行：段标题行 / "
      "本行 / 口径行 / 补印行）⇒ ⇒ 实现**硬失败**（⛔ 不是静默降级）⇒ ⇒ "
      "锚点改成「配对置换 **且** Newcombe95」⇒ ⇒ 段内**唯一**。")
    A("4. **`(n_nz,n_zero)` 分布串按逗号切** ⇒ ⇒ `(2,0)` **自身就带逗号** ⇒ ⇒ 切碎 "
      "⇒ ⇒ 实现**硬失败** ⇒ ⇒ 改成正则抽取 ＋ **逐位回读必须原样拼回**。")
    A("5. **⚠⚠⚠ H7 的 Wilson 交叉校验容差被多乘了 100**（`tol_from(...) * 100.0`）"
      "⇒ ⇒ 那条护栏**松了 100 倍**（0.005 pp ⇒ 0.5 pp）⇒ ⇒ **是跨实现互证抓到的**"
      "（它比对的是「重算值 vs 账本印的两位小数」，容差必须按**账本的打印精度**取）"
      "⇒ ⇒ 已**收紧**（0.005 pp）⇒ ⇒ 收紧后实测**仍然绿**（差 ≤ 0.002 pp）"
      "⇒ ⇒ **结论未变**。⚠ **诚实记账**：这条收紧发生在**真数据跑出形态之后** "
      "⇒ ⇒ **假如它是红的，形态会是 N-E** ⇒ ⇒ 它**有可能**改变结论 "
      "⇒ ⇒ **结论未变是因为它实测绿**。")
    A("6. **⚠ 落账层的字节清单三处不准**（⛔ **不是实现的错**、⛔ 也不是口径的错）—— "
      "**人工复核**账本【8】节时发现：① 收据路径把 `receipt` 写成 `.out`（实际是 **`.txt`**）"
      "⇒ ⇒ 读者按它去 cat 会**找不到**；② 「收据文件（N 件）」的 N 用了**收据登记的总数**"
      "（6 个脚本 ＋ 5 个收据 ＝ 11）⇒ ⇒ 与下面**实际列出的 5 条**不符；"
      "③ 「被检 / 口径 / 驱动」漏了 `_run_24486_reg_shm.sh`（本轮的**全回归 R7 驱动**）"
      "⇒ ⇒ 清单**不完整**。⇒ ⇒ **改的是落账脚本** ＋ **重落**了本段 ⇒ ⇒ "
      "**旧前缀逐字节不变、围栏数不变、244.81 段一字未动、一个数都没动** ⇒ ⇒ "
      "**判决形态不变**。⚠ **诚实记账**：这三条**没有闸门/变异台覆盖** ⇒ ⇒ "
      "**账本层没有自检** ⇒ ⇒ 记为**留白**（见【6】）。")
    A("7. **⚠ 预登记层的「先于结果」被污染**（⛔ **不是实现的错**、⛔ 也不是口径的错）—— "
      "**人工复核**预登记 `.cache/xcheck/R6_CONTROL_ARM_NULL_PREREG.md` 时发现：§0.5「更正 ②」的"
      "**末尾三句**（自「**本轮结论不受这条澄清影响**：本轮实测 **H3、H4 都绿**」起）"
      "**引用了本轮的真数据结果** ⇒ ⇒ 而 §0.5 的标题声称「**任何 p 值算出之前**」、"
      "更正 ② 的「更正时点」也写着「**任何真数据判决被算出之前**」⇒ ⇒ "
      "**那三句与这两处声明自相矛盾** ⇒ ⇒ 更根本地：那三句写于**真数据判决算出之前**，"
      "却**按「已实测」的口气写** ⇒ ⇒ 它当时其实是**一个预期**、不是观测 ⇒ ⇒ "
      "**把预期写成断言**本身就是记账错误 ⇒ ⇒ 即使后来真数据**恰好**与它一致，"
      "也**不构成**「先于结果」的证据。"
      "⇒ ⇒ **更正**：预登记**追加** §0.6「更正 ③」⇒ ⇒ **撤回那三句的证据效力**"
      "（⛔ 不改任何口径、不改任何数、⛔ 不改 §0.5 已写下的任何一句）＋ 给出"
      "**不依赖结果**的替代论证（「更正 ② 只改『两态同时命中时谁优先』的**读法** ⇒ ⇒ "
      "**不可能**改变任何一态的归属 ⇒ ⇒ 与本轮实测落在哪一态**无关**」）⇒ ⇒ 并且把"
      "「本轮落在 N-A」这个**事实**移回**账本本段**（⛔ 不再写在预登记里）。"
      "⚖ **正面证据**：预登记对账脚本 `_spec_crosscheck_24486.py` **自己就写明**"
      "「§0 的『预登记先于结果』—— 靠**签发时点**与签发时的产物清单，**不靠机器**」"
      "⇒ ⇒ 它**本来就不覆盖**这一层 ⇒ ⇒ **没有闸门能抓**这个错 ⇒ ⇒ 与第 6 条一样"
      "**没有闸门覆盖** ⇒ ⇒ **人工复核**才发现。"
      "⚖ **代价**：预登记 md5 变 ⇒ ⇒ **远端验证链重跑**（五个 rc 全 0、"
      "**5 个被检收据的 md5 一个都没变** ⇒ ⇒ 追加 §0.6 **没有改变任何被检输出** "
      "⇒ ⇒ **判决形态不变**）。")
    A("")
    A("#### 【6】⛔ **边界清单（本轮哪些仍未量到 / 不许被读成什么）**")
    A("")
    A("- ⛔ **「对照臂干净」仍未量到** —— 本轮只说「rand 臂的**边际**改判率"
      "**没有可检出的**高于零假设」⇒ ⇒ 「没有污染」**未量到**（⛔ 不是「无污染」）。")
    A("- ⛔ **污染的**精确**幅度仍未量到** —— 本轮只给**上界** c_max = %+.2f pp。"
      % float(K["C_MAX_PP"]))
    A("- ⛔ **「污染最多能翻多少格」的精确值仍未量到**（要剂量曲线 ⇒ ⇒ 跑批）。")
    A("- ⛔ **「污染存在」的响应级严格证明仍未量到** —— **共享成分 vs 题目可移动性共线** "
      "⇒ ⇒ 本轮只给**边际**结论。")
    A("- ⛔ **rand 臂换随机种子后的分布仍未量到** ⇒ ⇒ **r 那一侧仍是 N=1**"
      "（本轮**不碰**）。")
    A("- ⛔ **机制轴、剂量轴** ⇒ ⇒ 沿用旧留白，**未量到**。")
    A("- ⛔ **H2 的「不显著」是弱证据**：格不独立 ⇒ ⇒ 这个 p **反保守** ⇒ ⇒ "
      "「基准 0.5 没被推翻」**不成立**，只成立「**没有发现明显偏低**」。")
    A("- ⛔ **文档层（预登记 ＋ 账本）没有自检** —— 【5】第 6、7 条那两处错"
      "**没有任何闸门/变异台覆盖** ⇒ ⇒ 都是**人工复核**发现的 ⇒ ⇒ "
      "「账本的字节清单**总是**对的」「预登记**整体**先于结果」这两句话**未量到**"
      "（⛔ 不是「它们是对的」）。⚖ **更准确的边界**：预登记的**口径与判据**"
      "（§0、§2、§2.1、§3.1、§3.2、§4、§5）**全部**先于结果 ✅；⛔ 但「**预登记整体**"
      "先于结果」**不成立**（§0.5 曾有一句引用结果、已被 §0.6 撤回其证据效力）。")
    A("- ⚖ **块级零分布的两个极端在 rand 臂上**穷尽**了所有配对**（低基准只有 2 条 ⇒ ⇒ "
      "只有「同块 / 异块」两种）；**w 臂只有 1 条低基准 ⇒ ⇒ 配对唯一**。")
    A("")
    A("#### 【7】▶️ **下一轮（244.87+）**")
    A("")
    A("1. **固定剂量批重跑并加 `--dump-raw`** ⇒ ⇒ 拿到 60 点全曲线 ⇒ ⇒ 离线把 w 臂曲线缩放到 "
      "**6.828** 剂量 ⇒ ⇒ 直接算「污染最多能翻多少格」⇒ ⇒ 把**条件命题**变成**实测**。"
      "⚖ 这是**现在**最靠近判决数、且**不依赖**任何未决口径的一步。")
    A("2. **多随机种子的对照臂**（把 **r 那一侧**从 N=1 变成 N=K）⇒ ⇒ "
      "本轮给的是「rand 臂这一把」的上界 ⇒ ⇒ 换个种子**上界会变** ⇒ ⇒ 要分布。")
    A("3. **同结论对照臂**（机制轴）：同结论、同末值、只有检查有效性不同。")
    A("4. **分层剂量的真阶梯**（剂量轴）：⛔ 不能靠事后分位分档 ⇒ ⇒ 要跑批 ⇒ ⇒ 要点头。")
    A("")
    A("#### 【8】⚖ **这一轮的字节**")
    A("")
    A("⚖⚖⚖ 下面每个 md5 都是**由文件本身算出来的**；标「⚖ 收据登记」的**同时**与"
      "**远端验证链收据里登记的那份逐位对上** ⇒ ⇒ 「入库的字节 ＝ 跑出这些数的字节」；"
      "标「⚖ 本地现算」的**只由文件本身算出**（它**不在**那份收据里 ⇒ ⇒ 单独标出）。")
    A("")
    A("- **被检 / 口径 / 驱动（%d 件）**：" % (len(ROUND_FILES) + 1))
    for name, path in ROUND_FILES:
        m = _md5_file(path)
        rcv = N["rc_md5"].get(name)
        if rcv is None:
            raise SystemExit("⛔ 收据里没有登记 `%s` 的 md5 ⇒ 字节清单无出处 ⇒ 中止" % name)
        if rcv != m:
            raise SystemExit("⛔ `%s` 的本地 md5 = %s 与收据登记的 %s **不一致** ⇒ ⇒ 停下"
                             "（⛔ 不许入库与收据不是同一份的字节）" % (name, m, rcv))
        A("  - `%s`  `%s`  ⚖ 收据登记（远端验证链）" % (m, name))
    A("  - `%s`  `_run_24486_reg_shm.sh`  ⚖ **本地现算**（本轮的**全回归 R7 驱动** ⇒ ⇒ "
      "**不在**远端验证链收据里：验证链在 zju-53、R7 在 zju-12 ⇒ ⇒ **两份收据**）"
      % _md5_file(os.path.join(DEV, "_run_24486_reg_shm.sh")))
    A("- **收据文件（%d 件）**：" % (len(RECEIPT_FILES) + 1))
    for name in RECEIPT_FILES:
        m = _md5_file(os.path.join(EV, name))
        rcv = N["rc_md5"].get(name)
        if rcv is None or rcv != m:
            raise SystemExit("⛔ 收据 `%s` 的本地 md5 与收据登记的不一致 ⇒ ⇒ 停下" % name)
        A("  - `%s`  `%s`  ⚖ 收据登记（远端验证链）" % (m, name))
    A("  - `%s`  `receipt.txt`  ⚖ **本地现算**（它是远端验证链的**总收据**，"
      "登记其余 %d 条 md5 ⇒ ⇒ **它自己的** md5 只能由本地现算）"
      % (_md5_file(os.path.join(EV, "receipt.txt")), len(N["rc_md5"])))
    A("")
    A("⚖ **远端**：`%s`（%s）｜ ⛔ **零 GPU**、⛔ 没跑批、⛔ 没改读数器/探针/拆分器、"
      "⛔ 没改 244.79–244.85 段。" % (N["rc_host"], N["rc_date"]))
    A("")
    _hist = "、".join("第 %d 版 md5 `%s`（%s）" % (i + 1, _h, _why)
                      for i, (_h, _why) in enumerate(SUPERSEDED_LEDGER_MD5))
    A("⚖⚖⚖ **本段的字节历史（诚实记账）**：本段的账本文本**改过 %d 轮** —— %s、**最终版** "
      "⇒ ⇒ 前 %d 版**都只存在于本地、从未提交** ⇒ ⇒ 它们是**中间字节** ⇒ ⇒ "
      "**全回归 R7 只以最终版为准**（收据里锚的 `ledger_md5` 就是最终版）。"
      "⚖ **为什么改**：第 1 版【8】节的字节清单**三处不准**（【5】第 6 条）⇒ ⇒ 第 2 版修好了清单，"
      "却仍把「本轮抓到的是**六个**」这件事**漏在账本外** ⇒ ⇒ 第 3 版把【5】节改成六个 ＋ "
      "把第 6 条写进去 ＋ 把「账本层没有自检」记成【6】的留白 ⇒ ⇒ 最终版再把"
      "「**预登记层引用了真数据结果**」（【5】第 7 条）补进去 ＋ 把留白扩成「**文档层**没有自检」"
      "＋ 把预登记 §0.6「更正 ③」的记账写进来。"
      "⚖ **代价**：**旧前缀（244.85 那份）逐字节不变**、**围栏数不变**、**244.81 段一字未动** "
      "⇒ ⇒ **本轮的判决与一个数都没变** ⇒ ⇒ 变的是**表述层**（路径、件数、计数）与**预登记的更正记录**。"
      % (len(SUPERSEDED_LEDGER_MD5), _hist, len(SUPERSEDED_LEDGER_MD5)))
    A("")
    A("⚖ **被读的账本**：`%s`（%d 行 ｜ md5 `%s`）⇒ ⇒ 本轮**只读**它 ⇒ ⇒ "
      "落账后账本会变长，但 **244.81 段一字不动** ⇒ ⇒ **本轮的数不会因为落账而变**。"
      % ("R6_RERUN_PREREG.md", N["led_lines"], N["led_md5"]))
    A("")
    return "\n".join(L) + "\n"


def main():
    dry = "--dry" in sys.argv
    N = collect()
    sec = build(N)
    fences = [l for l in sec.split("\n") if l.strip().startswith("```")]
    assert not fences, "⛔ 追加段里有围栏 ⇒ 不许"
    assert "\\" not in sec, "⛔ 追加段里有反斜杠 ⇒ 不许"
    full = _read(LEDGER)
    # ⚖⚖⚖ **防重复落账**（幂等闸）：已落 ⇒ 必须**逐字节等于**收据算出来的那段，否则停下
    _h = TITLE
    n_have = full.count(_h)
    if n_have > 1:
        raise SystemExit("⛔ 账本里有 %d 处「%s」⇒ ⇒ 停下" % (n_have, _h))
    if n_have == 1:
        tail = full[full.index(_h):]
        if tail == sec or tail.rstrip() == sec.rstrip():
            print("✅ 幂等：账本里已有的 244.86 段与**收据算出来的那段逐字节相同**"
                  " ⇒ ⇒ 不重复写（本次落账无需再动）")
            return 0
        raise SystemExit("⛔ 账本里已有 244.86 段，但它与收据算出来的**不一致** ⇒ ⇒ 停下"
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
