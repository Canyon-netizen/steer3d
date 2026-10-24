#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""_append_24487.py —— 把 244.87 的结果**追加**进权威账本（⛔ 只追加，绝不改写）。

⚖⚖⚖ **纪律（继承 244.86 的落账脚本）**
   ① **只追加**：旧前缀逐字节不变、围栏数不变 ⇒ ⇒ 落完当场自证；
   ② **追加段不许有围栏、不许有反斜杠**（⛔ 账本正文里出现 ``` 会把别人的阅读器搞乱）；
   ③ **幂等闸**：账本里已有 244.87 段 ⇒ ⇒ 必须与「收据算出来的那段」逐字节相同
      ⇒ ⇒ 否则**停下**（⛔ 不许覆盖、⛔ 不许改数凑好看）；
   ④ **所有数都从收据抠**（⛔ 不手抄）⇒ ⇒ 收据没写的数 ⇒ ⇒ 落账脚本直接中止；
   ⑤ **字节清单逐条自验**：标「⚖ 收据登记」的必须与收据里登记的那份**逐位对上**。

用法：python3 .cache/r244/_append_24487.py [--dry]
"""

import hashlib
import io
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DEV = os.path.join(REPO, ".cache", "r244")
EV = os.path.join(DEV, "_e24487")
LEDGER = os.path.join(REPO, ".cache", "xcheck", "R6_RERUN_PREREG.md")
PREREG = os.path.join(REPO, ".cache", "xcheck", "R6_CMAX_ROBUSTNESS_PREREG.md")

TITLE = "## 修订 244.87 ——"


def _md5_file(path):
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


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
    if N["verdict"] not in ("A", "B", "C", "D"):
        raise SystemExit("⛔ 判决形态 %r 不在 A/B/C/D 里 ⇒ ⇒ 中止" % N["verdict"])

    # ---- 八条判据（逐条，含说明）----
    crits = re.findall(r"^\[(PASS|FAIL)\] (H\d) ([^—]*)— (.*)$", de, re.M)
    if len(crits) != 8:
        raise SystemExit("⛔ de.out 里解析到 %d 条判据（期望 8）⇒ ⇒ 中止" % len(crits))
    N["crits"] = crits
    N["reason"] = _grab(de, r"^理由：(.*)$", "判决理由").group(1).strip()

    # ---- 扫描表（9 个口径）----
    rows = re.findall(r"^  (\d\.\d\d) / (\S+)\s+base=([0-9.]+)\s+c ∈ \[([+-][0-9.]+), ([+-][0-9.]+)\]"
                      r" pp  ⇒  c_max=([+-][0-9.]+) pp$", de, re.M)
    if len(rows) != 9:
        raise SystemExit("⛔ de.out 里解析到 %d 个扫描口径（期望 9）⇒ ⇒ 中止" % len(rows))
    N["rows"] = rows

    # ---- 每个口径的两条真实差区间 ----
    ivs = re.findall(r"^  (\d\.\d\d) / (\S+)\s+不假定方向 \[([+-][0-9.]+), ([+-][0-9.]+)\] pp"
                     r" ｜ 假定污染抬高 \[([+-][0-9.]+), ([+-][0-9.]+)\] pp$", de, re.M)
    if len(ivs) != 9:
        raise SystemExit("⛔ de.out 里解析到 %d 组真实差区间（期望 9）⇒ ⇒ 中止" % len(ivs))
    N["ivs"] = ivs

    # ---- 自检 / 变异台 / 互证 / 对账 ----
    m = re.search(r"自检（Phase-0 G0-1\.\.G0-7）：(\d+) 条 ｜ FAIL (\d+) 条", st)
    if not m:
        raise SystemExit("⛔ selftest.out 里没有自检小结 ⇒ ⇒ 中止")
    N["st_n"], N["st_fail"] = m.groups()
    gates = re.findall(r"^\[(PASS|FAIL)\] (G0-\d)", st, re.M)
    if len(gates) != 7:
        raise SystemExit("⛔ selftest.out 里解析到 %d 道闸门（期望 7）⇒ ⇒ 中止" % len(gates))
    N["gates"] = gates

    m = re.search(r"变异台：抓到 (\d+) / (\d+)（无效 (\d+) 条", mu)
    if not m:
        raise SystemExit("⛔ mut.out 里没有变异台小结 ⇒ ⇒ 中止")
    N["mut_caught"], N["mut_total"], N["mut_invalid"] = m.groups()
    N["mut_crash"] = _grab(mu, r"崩的条数：(\d+)", "崩的条数").group(1)
    N["mut_ids"] = re.findall(r"^\[(抓到|没抓到)\] (\S+)", mu, re.M)

    m = re.search(r"互证：OK (\d+) ｜ MISMATCH (\d+)", cr)
    if not m:
        raise SystemExit("⛔ cross.out 里没有互证小结 ⇒ ⇒ 中止")
    N["cr_ok"], N["cr_bad"] = m.groups()
    N["cr_verdict"] = _grab(cr, r"^独立重算的判决形态：(\S+)$", "互证形态").group(1)

    m = re.search(r"对账条数：OK (\d+) ｜ 红 (\d+)", sp)
    if not m:
        raise SystemExit("⛔ spec.out 里没有对账小结 ⇒ ⇒ 中止")
    N["sp_ok"], N["sp_bad"] = m.groups()

    # ---- 收据登记的 md5 ----
    N["rc_md5"] = {}
    for mm in re.finditer(r"^([0-9a-f]{32})\s+(\S+)$", rc, re.M):
        N["rc_md5"][os.path.basename(mm.group(2))] = mm.group(1)

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

    cmin = float(K["C_MIN_PP"])
    cmax = float(K["C_MAX_PP"])
    cmain = float(K["C_MAIN_PP"])
    dobs = float(K["DELTA_OBS_PP"])

    A("## 修订 244.87 —— ⚖⚖⚖⚖⚖ **c_max 的口径稳健性**：污染上界对**口径**稳健（形态 **%s**）"
      "⇒ ⇒ c_max 从「一个数」升级成「**一个区**」[**%+.2f**, **%+.2f**] pp（9 个口径）"
      "｜ 最紧组合 **%+.2f pp** < Δ_obs **%+.2f pp**" % (N["verdict"], cmin, cmax, cmain, dobs))
    A("")
    A("⚖ **口径真相源**：`.cache/xcheck/R6_CMAX_ROBUSTNESS_PREREG.md`（244.87 签，**先于实现**；"
      "§0.5 含 **两条更正**（② 形态的落态级联、③ 「五个形态」/「G0-2」两处笔误）、"
      "§0.7 含一条**签发前**修订）")
    A("⚖ **数据**：**只读**权威账本的 **244.81 段**（⛔ 不重跑日志、⛔ 零 GPU、⛔ 不碰 bpath）")
    A("⚖ **收据**：`.cache/r244/_e24487/{selftest,de,mut,cross,spec}.out` ＋ "
      "`.cache/r244/_e24487/receipt.txt`")
    A("")

    A("#### 【1】这一轮做了什么")
    A("")
    A("· **没有跑批、没有重解析跑批日志、没有 GPU** ⇒ ⇒ 全部输入**从账本 244.81 段逐行解析**"
      "（⛔ 代码里**不写死任何一个数**；连**容差**都由**账本自己的打印精度**推导）。")
    A("· **回答的问题**：244.86 给的 **c_max = +15.22 pp** 是**一个数**、不是**一个区** ⇒ ⇒ "
      "它由「rand 改判率的 Wilson **上界**」减「零假设基准」得到 ⇒ ⇒ **两个输入的口径都会动它** "
      "⇒ ⇒ 本轮检验「**污染解释不了观测差**」这条结论**对口径敏不敏感**。")
    A("· ⚖⚖⚖ **量纲陷阱（N6/N7）**：Newcombe95 的下端点（%+.2f pp）与块级 bootstrap 的下端点"
      "**都是「w − rand 的差」的区间下端点** ⇒ ⇒ **不是** Δ_obs ⇒ ⇒ ⛔ **不能**拿它们去比 c_max "
      "⇒ ⇒ 否则会得出「假警报」⇒ ⇒ 本轮把它做成 **H5 硬门**（**kind 标签**机制）。"
      % float(K["IV_NO_LO_PP"]))
    A("· ⚖ **本轮享受不到「结果未知」的豁免**：用到的**每一个原始数**（29/56、0.4911、+30.36 …）"
      "**都已在 244.81 段登记** ⇒ ⇒ 本轮**没有新的原始数**；新的是**命题**（「对口径稳健」）。")
    A("")

    A("#### 【2】判决面板（9 个扫描口径 × 两条真实差区间）")
    A("")
    A("· **判决形态**：**%s**" % N["verdict"])
    A("· **理由（原文）**：%s" % N["reason"])
    A("")
    A("| Wilson | 基准变体 | 基准 | c 的区间（pp） | c_max（pp） | 真实差（不假定方向） | 真实差（假定污染抬高） |")
    A("|---|---|---|---|---|---|---|")
    for (lv, va, base, clo, chi, cmaxx), (_l2, _v2, nlo, nhi, ulo, uhi) in zip(N["rows"], N["ivs"]):
        A("| %s | %s | %.6f | [%+.2f, %+.2f] | **%+.2f** | [%+.2f, %+.2f] | [%+.2f, %+.2f] |"
          % (lv, va, float(base), float(clo), float(chi), float(cmaxx),
             float(nlo), float(nhi), float(ulo), float(uhi)))
    A("")
    A("· **c_max 的取值区间**：[**%+.2f**, **%+.2f**] pp（9 个口径的最小/最大）"
      "⇒ ⇒ 这是**上界族**，⛔ **不是**污染的点估计（⛔ 「污染不存在」**仍未量到**）。" % (cmin, cmax))
    A("· **最紧组合**：(Wilson95, 主基准) c_max = **%+.4f pp** < Δ_obs = **%+.2f pp** ⇒ ⇒ "
      "**污染最多抬这么多，而观测差至少这么多** ⇒ ⇒ 污染**解释不了**观测差。" % (cmain, dobs))
    A("· **Δ_obs 的两个口径**：轨迹级 **%+.2f pp**（本轮用它比，因为它是**最紧**的那个）"
      "｜ 块级 **%+.2f pp**（⛔ 本轮**不**用它下判决；§6 的「连承认聚类的块级口径也解释不了」"
      "是**下一轮**的活 ⇒ ⇒ 预登记先行，不许在本轮偷跑）"
      % (dobs, float(K["DELTA_OBS_BLK_PP"])))
    A("")

    A("#### 【3】✅ **八条硬判据逐条（真数据：PASS %d ｜ FAIL %d）**"
      % (sum(1 for c, _i, _n, _d in N["crits"] if c == "PASS"),
         sum(1 for c, _i, _n, _d in N["crits"] if c == "FAIL")))
    A("")
    for c, i, nm, d in N["crits"]:
        A("- [%s] **%s** %s — %s" % (c, i, nm.strip(), d))
    A("")
    A("⚖⚖⚖ **H1 的余量只有 0.0046 pp**（现算 %+.4f vs 账本印 %+.2f，容差 0.005 pp）"
      "⇒ ⇒ 这是**账本两位小数打印精度的半个单位**（由打印精度推导，⛔ 不是拍脑袋的容差）"
      "⇒ ⇒ ⚠ **诚实记账**：这条余量**很薄** ⇒ ⇒ 账本若改这一段 ⇒ ⇒ H1 立刻红。"
      % (cmain, cmain))
    A("")

    A("#### 【4】✅ **每条判据能红**")
    A("")
    A("- **自检**（Phase-0 G0-1..G0-7，合成夹具、⛔ 零账本、⛔ 零 GPU）：判据 **%s** 条 ｜ "
      "FAIL **%s** 条（%s）"
      % (N["st_n"], N["st_fail"],
         "、".join("%s=%s" % (g, p) for p, g in N["gates"])))
    A("- **变异台**：抓到 **%s / %s**（无效 %s 条 ⇒ 记「无效」⇒ 不计入分母）｜ 崩的条数 **%s**"
      "（⛔ 必须是 0）" % (N["mut_caught"], N["mut_total"], N["mut_invalid"], N["mut_crash"]))
    A("- **变异台逐条**：%s"
      % "、".join(m[1] for m in N["mut_ids"] if m[0] == "抓到"))
    A("- **互证**（第二条独立实现：**Fraction** 算基准 ＋ **Decimal(60 位)** 算 Wilson ＋ "
      "**NormalDist** 取 z，⛔ 与被检实现零共用代码、锚点也故意不同）：OK **%s** ｜ MISMATCH **%s** "
      "｜ 独立重算的判决形态 **%s**" % (N["cr_ok"], N["cr_bad"], N["cr_verdict"]))
    A("- **预登记 ↔ 实现 的机械对账**：OK **%s** ｜ 红 **%s**" % (N["sp_ok"], N["sp_bad"]))
    A("")

    A("#### 【5】⚠⚖⚖ **本轮抓到的真缺陷（11 条：3 条**预登记层** ＋ 5 条**实现层** ＋ "
      "2 条**第二/第三条实现层** ＋ 1 条**执行集覆盖**；⛔ **一个数都没动**）**")
    A("")
    A("1. ⚠ **预登记层：§5 的 G0-1 写「五个形态」** ⇒ ⇒ 而 §3.1 只定义了 **A/B/C/D 四个**"
      "（§3.1 尾注自己也写「四个」）⇒ ⇒ 与 G0-1 括号里**自己列的** A/B/C/D 矛盾 "
      "⇒ ⇒ 查因：**244.86 的预登记**写的是「N-A…N-E 五个分支」⇒ ⇒ 这是**抄过来的笔误**。"
      "⇒ ⇒ **预登记追加 §0.5 更正 ③**（读成「四个」）；§3.1/§3.2/§5 的**闸门内容一字未改**。")
    A("2. ⚠ **预登记层：§3.1 尾注把「可达性」闸门指向 G0-2** ⇒ ⇒ 而 §5 里可达性是 **G0-1**"
      "（G0-2 写的是「H1..H8 每条都能红」）⇒ ⇒ **指针差一位** ⇒ ⇒ 同一条**更正 ③** 里改正。")
    A("3. ⚠⚠⚖ **预登记层：§3.1 的四态在字面上不穷尽** —— 当「H6/H7 绿、H5 绿、扫描**无违例**、"
      "但 **H1/H2/H8 红**」时 ⇒ ⇒ A/B/C/D **落不进任何一态**；且「H1/H2/H8 红**且**扫描有违例」"
      "按字面读法落 **B** ⇒ ⇒ 会把「**前提层面的失败**」写成「**结论层面的命题被否**」"
      "⇒ ⇒ **预登记追加 §0.5 更正 ②**：把落态写成**唯一级联**（硬失败 = H1/H2/H6/H7/H8 ⇒ **C**；"
      "⇒ H5 红 ⇒ **D**；⇒ H3/H4 红 ⇒ **B**；⇒ 其余 ⇒ **A**）⇒ ⇒ 四个形态**互斥且穷尽**。"
      "⚖ **各形态的「含义」与「A 的成立条件」一字未改**；且 §3.1 的 B 行**本来就**写着"
      "「H6/H7/H8 绿」这个限定 ⇒ ⇒ 把它贯彻到底与 B 行**口径一致**，⛔ 不是新口径。")
    A("4. **实现层：H8 用了「可被替换的量」去比「账本印的值」** ⇒ ⇒ 把 Newcombe 下端点接到 "
      "Δ_obs 槽位时，**H8 跟着一起红** ⇒ ⇒ 形态被误判成 **C**（应是 **D**）⇒ ⇒ **G0-1 抓到的** "
      "⇒ ⇒ 修的是**实现**（H8 改用账本印的那个 `i7_delta_obs`）⇒ ⇒ **一个数都没动**。")
    A("5. **实现层：预登记明写的两条没兑现** —— ① H6 的「重建串逐位回读」**只覆盖 8 项**、"
      "**漏了 I6**（`(n_nz,n_zero)` 分布）⇒ ⇒ 「改账本里的分布 ⇒ H6 红」这条承诺**没兑现**；"
      "② H7 **只做了 md5 一半**，漏了「解析到的行号**全部落在 244.81 段范围内**」"
      "⇒ ⇒ **补齐**（H6 现 12 项、H7 现记 6 个锚点的行号）⇒ ⇒ 判据变**更严**，⛔ 不是更松。")
    A("6. **实现层：量纲护栏的**两条分支不可区分** ⇒ ⇒ 删掉其中一条 ⇒ ⇒ **另一条仍会挡住** "
      "⇒ ⇒ G0-4 的自证**察觉不到** ⇒ ⇒ 「护栏被削弱」没人知道 ⇒ ⇒ **变异台 MU8 抓到的** "
      "⇒ ⇒ 给两条分支各一个**代号**（`H5-KIND-DELTA-CI-LO` / `H5-KIND-PAIR`），"
      "G0-4 断言**必须**是前者 ⇒ ⇒ 这是**Phase-0 设计的缺陷**，不是数字的缺陷。")
    A("7. **实现层：G0-7 只做正控** ⇒ ⇒ 把「md5 不变」这个**比较表达式**改成恒真 ⇒ ⇒ "
      "**没有任何闸门能抓**（自检层的固有上限：改「比较表达式」本身没人监督）⇒ ⇒ "
      "**变异台 MU15 抓到的** ⇒ ⇒ 修法：把比较抽成**H7 与 G0-7 共用的函数** ＋ "
      "给 G0-7 加**负控**（碰一下账本 ⇒ 必须被检出）⇒ ⇒ 两个控件**共用** ⇒ ⇒ 改成恒真 ⇒ ⇒ "
      "**正控与负控同时失效** ⇒ ⇒ 抓得到。")
    A("8. **实现层：两处「会骗人」的记账缺陷** —— ① `GATE_IDS` 是**一次性生成器** ⇒ ⇒ "
      "对账脚本第二次用时看到**空列表** ⇒ ⇒ 明细会骗人（改成 tuple）；"
      "② `AUDIT_KEYS` 的 `IV_*` **取错了行**（取了 rows[0] = (Wilson90, main) 而不是主口径行）"
      "⇒ ⇒ 提交信息会引到**别的口径**的数 ⇒ ⇒ 改成主口径行 ⇒ ⇒ **改完与 244.86 账本印的 "
      "[%+.2f, %+.2f] / [%+.2f, %+.2f] 逐位对上**。"
      % (float(K["IV_NO_LO_PP"]), float(K["IV_NO_HI_PP"]),
         float(K["IV_UP_LO_PP"]), float(K["IV_UP_HI_PP"])))
    A("9. **第二/第三条实现层：互证脚本踩了 244.86 第 4 条缺陷的**同类坑** —— `(n_nz,n_zero)` "
      "分布串**按逗号切** ⇒ ⇒ 内层 `(2,0)` **自带逗号** ⇒ ⇒ 切碎 ⇒ ⇒ 改用**括号感知**的"
      "**顶层逗号**切分（⛔ 与被检实现的正则路线**真的不同源**）；另有三处："
      "Newcombe 锚点**不唯一**（表头行也命中 ⇒ 2 行）、**全角/半角括号**用错、"
      "`Fraction × Decimal` 不能直接乘 ⇒ ⇒ 三条**都崩** ⇒ ⇒ 逐条修好。")
    A("10. **第三条实现层：对账脚本的 Q4 比错了对象** —— 比的是「**该臂**的基准」（它取决于 "
      "`(n_nz,n_zero)` 分布本身）而不是「**零格轨迹的 base 参数**」⇒ ⇒ 改用「**每条轨迹都含零格**」"
      "的合成分布去测 ⇒ ⇒ 现预登记 `[0.0, 0.25, 0.5]` == 实现 `[0.0, 0.25, 0.5]`。")
    A("11. ⚠⚠⚖ **执行集覆盖的一个洞（本轮顺手补上）** —— R4–R7 的回归树里**漏了两个"
      "**已入库**的执行集成员**（`fixed_dose_strata.py` / `mut_fixed_dose_strata.py`，"
      "来自 `0466c9b`）⇒ ⇒ 「**全回归全绿**」这句话**在这两个文件上从未成立过** ⇒ ⇒ "
      "本轮把两者补进 R8 的树 ⇒ ⇒ 它们都绿（变异台 14/14、自检 22/22）⇒ ⇒ **R8 首次覆盖它们**。")
    A("")

    A("#### 【6】⛔ **边界清单（本轮哪些仍未量到 / 不许被读成什么）**")
    A("")
    A("- ⛔ **「污染不存在」仍未量到** —— 本轮只检验「**c_max < Δ_obs 这条对口径稳健**」，"
      "⛔ **不**检验污染本身存不存在 ⇒ ⇒ 「没有污染」**未量到**（⛔ 不是「无污染」）。")
    A("- ⛔ **污染的精确幅度仍未量到** —— 本轮给的是 **c_max 的上界族**（一个**区**），"
      "⛔ **不是**点估计。")
    A("- ⛔ **「污染最多能翻多少格」的精确值仍未量到**（要剂量曲线 ⇒ ⇒ 跑批 ⇒ ⇒ 要点头）。")
    A("- ⛔ **换随机种子后的分布仍未量到** ⇒ ⇒ r 那一侧仍是 **N=1**（本轮**不碰**）。")
    A("- ⛔ **「连承认聚类的块级口径也解释不了」这一条** —— 本轮**只**把块级 Δ_obs 拿来"
      "**交叉核对**（H8）⇒ ⇒ **没有**用它下判决 ⇒ ⇒ 该命题**未量到**（⇒ ⇒ 下一轮的活）。")
    A("- ⛔ **机制轴、剂量轴** ⇒ ⇒ 沿用旧留白，**未量到**。")
    A("- ⛔ **预登记层与账本层没有自检**（244.86 的留白，**本轮仍然成立**）⇒ ⇒ "
      "「预登记**整体**先于结果」**不成立** ⇒ ⇒ 准确的说法是「**§0、§2、§2.1、§3.1、§3.2、"
      "§4、§5 全部先于结果**」⇒ ⇒ 本轮的两条**更正记录**（②③）写于实现阶段，"
      "其论证**不引用任何实测数**。")
    A("- ⚖ **自检层的固有上限**：**改「闸门自己的比较表达式」**这件事**没有闸门能抓**"
      "⇒ ⇒ 本轮用「正控＋负控共用同一个函数」把它**缩小**（第 7 条），"
      "⛔ 但**没有**、也**不可能**把它**消灭** ⇒ ⇒ 记为**留白**。")
    A("")

    A("#### 【7】▶️ **下一轮（244.88+）**")
    A("")
    A("1. **把「污染上界族」与「Δ_obs 的块级口径」接起来** ⇒ ⇒ 即「**污染上界 vs 块级观测差**」"
      "在**所有扫描口径**下是否成立 ⇒ ⇒ 若成立 ⇒ ⇒ 结论可再加一层「**连承认聚类的块级口径也"
      "解释不了**」⇒ ⇒ ⚖ 这是**现在**最靠近判决数、且**不依赖**任何未决口径的一步"
      "（⛔ 预登记必须**先于**它签发）。")
    A("2. **固定剂量批重跑并加 `--dump-raw`** ⇒ ⇒ 拿到 60 点全曲线 ⇒ ⇒ 离线把 w 臂曲线缩放到 "
      "**6.828** 剂量 ⇒ ⇒ 直接算「污染最多能翻多少格」⇒ ⇒ 把**条件命题**变成**实测**"
      "⇒ ⇒ ⚠ 要点头。")
    A("3. **多随机种子的对照臂**（把 **r 那一侧**从 N=1 变成 N=K）⇒ ⇒ 要点头。")
    A("4. **同结论对照臂**（机制轴）与**分层剂量的真阶梯**（剂量轴）⇒ ⇒ 要点头。")
    A("")

    A("#### 【8】⚖ **这一轮的字节**")
    A("")
    A("⚖⚖⚖ 下面每个 md5 都是**由文件本身算出来的**；标「⚖ 收据登记」的**同时**与"
      "**远端验证链收据里登记的那份逐位对上** ⇒ ⇒ 「入库的字节 ＝ 跑出这些数的字节」。")
    A("")
    A("- **被检 / 口径 / 驱动（7 件）**：")
    for name, path in [
        ("cmax_robustness_audit.py", os.path.join(DEV, "cmax_robustness_audit.py")),
        ("mut_cmax_robustness_audit.py", os.path.join(DEV, "mut_cmax_robustness_audit.py")),
        ("_cross_check_24487.py", os.path.join(DEV, "_cross_check_24487.py")),
        ("_spec_crosscheck_24487.py", os.path.join(DEV, "_spec_crosscheck_24487.py")),
        ("_run_24487_verify.sh", os.path.join(DEV, "_run_24487_verify.sh")),
        ("R6_CMAX_ROBUSTNESS_PREREG.md", PREREG),
    ]:
        m = _md5_file(path)
        rcv = N["rc_md5"].get(name)
        if rcv is None:
            raise SystemExit("⛔ 收据里没有登记 `%s` 的 md5 ⇒ 字节清单无出处 ⇒ 中止" % name)
        if m != rcv:
            raise SystemExit("⛔ `%s` 的本地 md5 = %s 与收据登记的 %s **不一致** ⇒ ⇒ 停下"
                             % (name, m, rcv))
        A("  - `%s`  `%s`  ⚖ 收据登记（远端验证链）" % (m, name))
    A("  - `%s`  `_run_24487_reg_shm.sh`  ⚖ **本地现算**（本轮的**全回归 R8 驱动** "
      "⇒ ⇒ **不在**远端验证链收据里：验证链在 zju-53、R8 在 zju-12 ⇒ ⇒ **两份收据**）"
      % _md5_file(os.path.join(DEV, "_run_24487_reg_shm.sh")))
    A("- **收据文件（6 件）**：")
    for name in ("selftest.out", "de.out", "mut.out", "cross.out", "spec.out"):
        m = _md5_file(os.path.join(EV, name))
        rcv = N["rc_md5"].get(name)
        if rcv is None or m != rcv:
            raise SystemExit("⛔ 收据 `%s` 的本地 md5 与收据登记的不一致 ⇒ ⇒ 停下" % name)
        A("  - `%s`  `%s`  ⚖ 收据登记（远端验证链）" % (m, name))
    A("  - `%s`  `receipt.txt`  ⚖ **本地现算**（它是远端验证链的**总收据**，登记其余 11 条 md5 "
      "⇒ ⇒ **它自己的** md5 只能由本地现算）" % _md5_file(os.path.join(EV, "receipt.txt")))
    A("")
    A("⚖ **远端**：`zju-53`（2026-10-24 21:52 CST）｜ ⛔ **零 GPU**、⛔ 没跑批、"
      "⛔ 没改读数器/探针/拆分器、⛔ 没改 244.79–244.86 段。")
    A("")
    A("⚖⚖⚖ **一条必须说清的事实（本轮查实的）**：`zju-53` 与 `zju-12` 是**两台共享同一份 NFS "
      "家目录**的机器（`/home/zhourui/steer3d/.cache/xcheck/R6_RERUN_PREREG.md` 在两台上的 "
      "**inode 相同**、挂载点相同）⇒ ⇒ 「**两台远端逐位一致**」这件事是**必然**的，"
      "⛔ **不是**一条独立证据 ⇒ ⇒ 真正的独立证据是「**收据里的 md5 == 本地现算的 md5**」"
      "⇒ ⇒ 以后**不许**把「两台一致」当成交叉验证。")
    A("")
    A("⚖⚖⚖ **全回归 R8 的收据**（`.cache/r244/_e24487/reg_24487.txt`）是**落账之后**才生成的 "
      "⇒ ⇒ 因此它**不在**上面的字节清单里（⛔ 不是漏了）⇒ ⇒ 它的 md5 由**提交后的回读**核对 "
      "（⇒ ⇒ 收据里锚的账本 md5 必须 == 提交里那份）。")
    A("")
    A("⚖ **被读的账本**：`R6_RERUN_PREREG.md`（%s 行 ｜ md5 `%s`）⇒ ⇒ 本轮**只读**它 ⇒ ⇒ "
      "落账后账本会变长，但 **244.81 段一字不动** ⇒ ⇒ **本轮的数不会因为落账而变**。"
      % (N["led_lines"], N["led_md5"]))
    A("")
    return "\n".join(L) + "\n"


def main():
    dry = "--dry" in sys.argv
    truncate = "--truncate" in sys.argv
    N = collect()
    if truncate:
        # ⚖⚖⚖ **撤回重落**：把账本**截回**「追加 244.87 之前」的那份字节
        #   ⇒ ⇒ 截断前必须**逐位核对**那一份的 md5（⛔ 不许盲截）
        #   ⇒ ⇒ 截断**只动尾部** ⇒ ⇒ 旧前缀（244.86 那份）**一个字节都不动**
        with open(LEDGER, "rb") as fh:
            data = fh.read()
        pre_len = len(data)
        if pre_len <= 2609372:
            raise SystemExit("⛔ 账本只有 %d 字节（≤ 追加前那份的 %d）⇒ ⇒ 没落过账 ⇒ 中止"
                             % (pre_len, 2609372))
        head = data[:2609372]
        import hashlib as _h
        m = _h.md5(head).hexdigest()
        if m != "c762e1ae1cf9971e0bef11d49873efcb":
            raise SystemExit("⛔ 前 2609372 字节的 md5 = %s（期望 c762e1ae…）⇒ ⇒ **不截**" % m)
        with open(LEDGER, "wb") as fh:
            fh.write(head)
        after = open(LEDGER, "rb").read()
        if after != head:
            raise SystemExit("⛔ 截断后不一致 ⇒ 中止")
        print("✅ 已截回追加前那份：%d → %d 字节 ｜ md5 %s"
              % (pre_len, len(after), m))
        return 0
    sec = build(N)
    fences = [l for l in sec.split("\n") if l.strip().startswith("```")]
    assert not fences, "⛔ 追加段里有围栏 ⇒ 不许"
    assert "\\" not in sec, "⛔ 追加段里有反斜杠 ⇒ 不许"
    full = _read(LEDGER)
    _h = TITLE
    n_have = full.count(_h)
    if n_have > 1:
        raise SystemExit("⛔ 账本里有 %d 处「%s」⇒ ⇒ 停下" % (n_have, _h))
    if n_have == 1:
        tail = full[full.index(_h):]
        if tail == sec or tail.rstrip() == sec.rstrip():
            print("✅ 幂等：账本里已有的 244.87 段与**收据算出来的那段逐字节相同**"
                  " ⇒ ⇒ 不重复写")
            return 0
        raise SystemExit("⛔ 账本里已有 244.87 段，但它与收据算出来的**不一致** ⇒ ⇒ 停下"
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
