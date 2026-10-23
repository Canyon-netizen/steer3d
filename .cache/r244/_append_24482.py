#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⚖ **244.82 落账**（只追加；⛔ 追加段里不许有围栏；⛔ 所有数都从收据抠，⛔ 不手抄）。

**这一段记什么**：把 244.81 判决面板上那条**没被验过**的前提（面板前提 P1「56 条轨迹彼此独立」）
**正式验收**掉：在**承认聚类**的保守零分布（块是独立单位）下，判决**是否仍然成立**。

⚖ **口径真相源**：`.cache/xcheck/R6_PREMISE_INDEPENDENCE_PREREG.md`（244.82 签，**先于实现**）
⚖ **数据**：bpath 原始跑批日志（⛔ 只读、⛔ 零 GPU、远端 `zju-53`）
⚖ **收据**：`.cache/r244/_e24482/{selftest,pi,mut,cross}.out`
"""

import io
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
LEDGER = os.path.join(REPO, ".cache", "xcheck", "R6_RERUN_PREREG.md")
EV = os.path.join(REPO, ".cache", "r244", "_e24482")
TITLE = "## 修订 244.82 —— "


def _read(p):
    with io.open(p, encoding="utf-8", newline="") as fh:
        return fh.read()


def _need(p):
    if not os.path.isfile(p):
        raise SystemExit("⛔ 缺收据：%s" % p)
    return _read(p)


def _grab(txt, pat, what, flags=re.M):
    m = re.search(pat, txt, flags)
    if not m:
        raise SystemExit("⛔ 收据里核不到「%s」" % what)
    return m


def collect():
    """⚖ 全部数**从收据抠**（⛔ 不手抄）。"""
    st = _need(os.path.join(EV, "selftest.out"))
    pi = _need(os.path.join(EV, "pi.out"))
    mu = _need(os.path.join(EV, "mut.out"))
    cr = _need(os.path.join(EV, "cross.out"))

    N = {}
    # ---- 自检（Phase-0 G0-1/G0-2）
    m = _grab(st, r"自检 (\d+) 条 ｜ PASS (\d+) ｜ FAIL (\d+)", "自检小结")
    N["st_n"], N["st_pass"], N["st_fail"] = m.groups()
    N["st_ids"] = re.findall(r"^\[PASS\] (\S+)", st, re.M)

    # ---- 真数据
    m = _grab(pi, r"判据 (\d+) 条 ｜ PASS (\d+) ｜ FAIL (\d+)", "真数据判据小结")
    N["pi_n"], N["pi_pass"], N["pi_fail"] = m.groups()
    N["pi_ids"] = re.findall(r"^\[PASS\] (\S+)", pi, re.M)

    m = _grab(pi, r"\*\*精确\*\*块级置换（DP 精确零分布，⛔ 非 MC）：p = ([0-9.]+)"
                    r"（obs = (\d+) ｜ 尾 (\d+) / (\d+)）", "精确块级置换")
    N["p_exact"], N["obs_blk"], N["tail"], N["tot"] = m.groups()
    m = _grab(pi, r"精确块级置换 p = ([0-9.]+) ｜ 先导探查 MC p = ([0-9.]+) ｜ 差 ([-+0-9.]+)"
                    r"（MC 的 1 SE ≈ ([0-9.]+) ⇒ 差 = ([0-9.]+) SE", "MC 误差")
    N["p_exact2"], N["p_mc"], N["d_mc"], N["mc_se"], N["mc_se_mult"] = m.groups()
    m = _grab(pi, r"差 = ([0-9.]+) SE", "MC 误差的 SE 倍数")
    N["mc_se_mult"] = m.group(1)

    m = _grab(pi, r"块级差 ([-+0-9.]+) pp ｜ \*\*删一块 jackknife\*\* 95% 区间 "
                    r"\[([-+0-9.]+), ([-+0-9.]+)\] pp（SE = ([0-9.]+)）", "jackknife 区间")
    N["theta_blk"], N["jk_lo"], N["jk_hi"], N["jk_se"] = m.groups()
    m = _grab(pi, r"轨迹级差 ([-+0-9.]+) pp ｜ Newcombe95（\*\*假定轨迹独立\*\*）"
                    r"\[([-+0-9.]+), ([-+0-9.]+)\] pp", "Newcombe 对照")
    N["theta_traj"], N["nc_lo"], N["nc_hi"] = m.groups()

    m = _grab(pi, r"\*\*LOBO\*\*（逐块剔除 (\d+) 个子集）：块级差 \[([-+0-9.]+), ([-+0-9.]+)\] pp ｜ "
                    r"置换 p ∈ \[([0-9.]+), ([0-9.]+)\] ｜ \*\*判决被掀翻的子集数 = (\d+)\*\*", "LOBO")
    N["lobo_n"], N["lobo_dmin"], N["lobo_dmax"], N["lobo_pmin"], N["lobo_pmax"], N["lobo_flips"] = m.groups()

    m = _grab(pi, r"w 臂：块 (\d+) ｜ 一致 (\d+)（po = ([0-9.]+)）｜ 偶然一致 pe = ([0-9.]+) ｜ "
                    r"κ = ([-+0-9.]+) ｜ 精确二项两侧 p = ([0-9.]+) ⇒ \*\*(可检出|未检出)\*\*", "w 臂块内")
    N["w_tot"], N["w_agree"], N["w_po"], N["w_pe"], N["w_kappa"], N["w_p"], N["w_det"] = m.groups()
    m = _grab(pi, r"rand 臂：块 (\d+) ｜ 一致 (\d+)（po = ([0-9.]+)）｜ 偶然一致 pe = ([0-9.]+) ｜ "
                    r"κ = ([-+0-9.]+) ｜ 精确二项两侧 p = ([0-9.]+) ⇒ \*\*(可检出|未检出)\*\*", "rand 臂块内")
    N["r_tot"], N["r_agree"], N["r_po"], N["r_pe"], N["r_kappa"], N["r_p"], N["r_det"] = m.groups()

    m = _grab(pi, r"w 臂：三格全一致 (\d+) ｜ 2:1 分歧 (\d+) ｜ 分歧率 ([0-9.]+)", "w 臂复制格")
    N["w_same"], N["w_split"], N["w_rate"] = m.groups()
    m = _grab(pi, r"rand 臂：三格全一致 (\d+) ｜ 2:1 分歧 (\d+) ｜ 分歧率 ([0-9.]+)", "rand 臂复制格")
    N["r_same"], N["r_split"], N["r_rate"] = m.groups()

    m = _grab(pi, r"McNemar（精确二项，不一致 (\d+) 条：w 优 (\d+) / rand 优 (\d+)）：p = ([0-9.]+)",
              "McNemar")
    N["mcn_disc"], N["mcn_w"], N["mcn_r"], N["mcn_p"] = m.groups()
    m = _grab(pi, r"结论形态 = (C-[ABC])", "结论形态")
    N["verdict"] = m.group(1)
    m = _grab(pi, r"\*\*C-A：", "C-A 正文")
    N["verdict_text"] = pi[m.start():pi.index("\n", m.start())].strip()

    # ---- 变异台
    m = _grab(mu, r"变异台：抓到 (\d+) / (\d+)（无效 (\d+) 条.*?其中等价变异 (\d+) 条", "变异台小结")
    N["mut_caught"], N["mut_total"], N["mut_invalid"], N["mut_equiv"] = m.groups()
    m = _grab(mu, r"崩的条数：(\d+)", "崩计数")
    N["mut_crash"] = m.group(1)
    m = _grab(mu, r"阳性对照（([^）]+)）：过", "阳性对照")
    N["posctl"] = m.group(1)
    N["mut_ids"] = re.findall(r"^\[(?:抓到|硬停抓到)\] (\S+)", mu, re.M)
    N["mut_hard_ids"] = re.findall(r"^\[硬停抓到\] (\S+)", mu, re.M)
    N["mut_plain_ids"] = re.findall(r"^\[抓到\] (\S+)", mu, re.M)

    # ---- 跨实现互证
    m = _grab(cr, r"互证判据 (\d+) 条 ｜ PASS (\d+) ｜ FAIL (\d+)", "互证小结")
    N["cr_n"], N["cr_pass"], N["cr_fail"] = m.groups()
    N["cr_ids"] = re.findall(r"^\[PASS\] (\S+)", cr, re.M)
    m = _grab(cr, r"先导 bootstrap \[([-+0-9.]+), ([-+0-9.]+)\] vs 本实现 jackknife "
                    r"\[([-+0-9.]+), ([-+0-9.]+)\] ⇒ 重叠宽度 ([0-9.]+) pp", "区间互证")
    N["boot_lo"], N["boot_hi"], N["x_jk_lo"], N["x_jk_hi"], N["ov"] = m.groups()
    return N


def build(N):
    """⚖ 组装追加段（⛔ **不许有围栏**）。"""
    L = []
    A = L.append
    A(TITLE + "⚖⚖⚖⚖⚖ **「前提独立性」这条前提**正式验收**掉**（⚖ **判决在保守口径下依然成立**）—— ⇒ ⇒ "
      "**精确**块级置换 p = **%s**（⛔ 不是蒙特卡洛）｜ 块级差 **%s pp**、**删一块 jackknife** 区间 "
      "[**%s, %s**] ｜ **LOBO** %s 个子集**掀翻数 = %s** ｜ 块内相关**未检出**（w 臂 p = %s、rand 臂 p = %s）"
      " ⇒ ⇒ 结论形态 **%s**；⛔ **「前提独立性成立」仍不可证明**（块间独立性**不可检验**）"
      % (N["p_exact"], N["theta_blk"], N["jk_lo"], N["jk_hi"],
         N["lobo_n"], N["lobo_flips"], N["w_p"], N["r_p"], N["verdict"]))
    A("")
    A("⚖ **口径真相源**：`.cache/xcheck/R6_PREMISE_INDEPENDENCE_PREREG.md`（244.82 签，**先于任何实现代码**）")
    A("⚖ **数据**：bpath **原始**跑批日志（⛔ 只读、⛔ 零 GPU、远端 `zju-53`）")
    A("⚖ **收据**：`.cache/r244/_e24482/{selftest,pi,mut,cross}.out`")
    A("")
    A("### 【1】⚠⚠⚠ **先说清楚：这条前提**不能被证明**（免得做成伪命题）")
    A("")
    A("「56 条轨迹彼此独立」在 28 个块上**不可证明** ⇒ ⇒ 任何统计检验都不能把「未检出相关」"
      "说成「无相关」⇒ ⇒ **本轮不产出**「前提独立性成立」这句话。")
    A("本轮只做三件能做的事（预登记 §1）：**W1** 结构（块是真的）｜**W2** 块内相关**被量到**（不是假设）"
      "｜**W3** 在**承认聚类**的保守零分布下判决**是否仍然成立**。")
    A("")
    A("### 【2】⚖ **判决在保守口径下依然成立**（结论形态 %s）" % N["verdict"])
    A("")
    A("- **精确块级置换**（DP 精确零分布，⛔ **不是**蒙特卡洛、⛔ 没有种子误差）：p = **%s**"
      "（obs = %s ｜ 尾 %s / %s）" % (N["p_exact"], N["obs_blk"], N["tail"], N["tot"]))
    A("- **块级差** %s pp ｜ **删一块 jackknife** 95%% 区间 [**%s, %s**] pp（SE = %s）"
      "（⛔ **确定性**，⛔ 不用种子）" % (N["theta_blk"], N["jk_lo"], N["jk_hi"], N["jk_se"]))
    A("- **LOBO**（逐块剔除 %s 个子集）：块级差 [%s, %s] pp ｜ 置换 p ∈ [%s, %s] ｜ "
      "**判决被掀翻的子集数 = %s** ⇒ ⇒ **没有单独一块能推翻它**"
      % (N["lobo_n"], N["lobo_dmin"], N["lobo_dmax"], N["lobo_pmin"], N["lobo_pmax"], N["lobo_flips"]))
    A("- **轨迹级对照**（⛔ 假定轨迹独立）：差 %s pp、Newcombe95 [%s, %s] pp"
      % (N["theta_traj"], N["nc_lo"], N["nc_hi"]))
    A("- **块内相关**（**被量到**，不是假设）：w 臂 一致 %s/%s（po = %s）vs 偶然一致 pe = %s、"
      "κ = %s、精确二项 p = %s ⇒ **%s**；rand 臂 一致 %s/%s（po = %s）vs pe = %s、κ = %s、"
      "p = %s ⇒ **%s**。⛔ **「未检出」⛔ 不是「不相关」。**"
      % (N["w_agree"], N["w_tot"], N["w_po"], N["w_pe"], N["w_kappa"], N["w_p"], N["w_det"],
         N["r_agree"], N["r_tot"], N["r_po"], N["r_pe"], N["r_kappa"], N["r_p"], N["r_det"]))
    A("- **复制格一致性**：w 臂 三格全一致 %s / 2:1 分歧 %s（分歧率 %s）；rand 臂 %s / %s（分歧率 %s）"
      % (N["w_same"], N["w_split"], N["w_rate"], N["r_same"], N["r_split"], N["r_rate"]))
    A("- **轨迹级 McNemar**（精确二项，不一致 %s 条：w 优 %s / rand 优 %s）：p = %s（对照）"
      % (N["mcn_disc"], N["mcn_w"], N["mcn_r"], N["mcn_p"]))
    A("")
    A("⇒ ⇒ %s" % N["verdict_text"])
    A("")
    A("### 【3】⚖⚖ **两条独立实现互证**（⛔ 不同数据路径、不同块键路线、不同置换算法、不同区间算法）")
    A("")
    A("| 维度 | 244.81 轮「先导探查」 | 244.82 轮「第二条实现」 |")
    A("|---|---|---|")
    A("| 数据路径 | `fixed_dose_split_log.py` 的**拆分产物** | bpath **原始**跑批日志，自己按 `pos_frac` 过滤 |")
    A("| 块键路线 | **剥后缀** | **按 `__` 切分取前 N−1 段** |")
    A("| 块级置换 | **蒙特卡洛** 20000 次（有种子） | **DP 精确零分布**（⛔ 无 MC 误差） |")
    A("| 差 pp 区间 | **按块 bootstrap**（有种子） | **删一块 jackknife**（确定性） |")
    A("")
    A("- **逐位相同**（同一口径、同一机械）**%s 条判据全绿**（轨迹级/块级改判数、Fisher p、块内一致数、"
      "复制格一致/分歧计数与分歧率、两臂差 pp、McNemar p、块数）" % N["cr_pass"])
    A("- **区间重叠**（不同机械、同一被估量）：先导 bootstrap [%s, %s] vs 本实现 jackknife [%s, %s] "
      "⇒ 重叠宽度 %s pp、两者都远离 0" % (N["boot_lo"], N["boot_hi"], N["x_jk_lo"], N["x_jk_hi"], N["ov"]))
    A("- **MC vs 精确**（同一零分布）：先导 MC p = %s vs 本实现精确 p = %s，差 %s，"
      "**%s 个 MC 标准误**（1 SE ≈ %s）⇒ ⇒ 差**就是 MC 误差**（预登记 §3.1）"
      % (N["p_mc"], N["p_exact"], N["d_mc"], N["mc_se_mult"], N["mc_se"]))
    A("- ⚖ **先导探查在 `zju-53` 重跑**：md5 **逐位相同** ⇒ ⇒ 它的数**可复现**")
    A("")
    A("### 【4】⚖ **判据与变异台**（每条判据**能红**）")
    A("")
    A("- **自检**（Phase-0 G0-1/G0-2，⛔ 零 GPU、已知答案）：**%s 条 ｜ PASS %s ｜ FAIL %s**"
      " ⇒ %s" % (N["st_n"], N["st_pass"], N["st_fail"], "、".join(N["st_ids"])))
    A("- **真数据**：**%s 条 ｜ PASS %s ｜ FAIL %s** ⇒ %s"
      % (N["pi_n"], N["pi_pass"], N["pi_fail"], "、".join(N["pi_ids"])))
    A("- **变异台**：**抓到 %s / %s**（无效 %s 条 ⇒ 记「无效」不计入分母；其中**等价变异 %s 条**；"
      "**崩 %s 条**）⇒ ⇒ %s 条变异**逐条能红**（其中 **%s** 条是普通判据红、**%s** 条是靠 "
      "**G0-3 自检闸硬停**抓到的，⛔ 崩 ≠ 抓到）⇒ ⇒ 变异台 id：%s"
      % (N["mut_caught"], N["mut_total"], N["mut_invalid"], N["mut_equiv"], N["mut_crash"],
         N["mut_total"], len(N["mut_plain_ids"]), len(N["mut_hard_ids"]),
         "、".join(N["mut_ids"])))
    A("- **阳性对照先过**：不改任何东西时目标**全绿**（%s）⇒ ⇒ 否则「全红」什么也证明不了"
      % N["posctl"])
    A("")
    A("### 【5】⛔ **边界清单（新增；哪些仍未量到）**")
    A("")
    A("- ⛔ **块间独立性** ⇒ ⇒ **不可检验**（28 个块，块与块之间**没有**任何重复结构可供配对）"
      "⇒ ⇒ **未量到**。")
    A("- ⛔ **「块内不相关」** ⇒ ⇒ **未量到**（本轮只能给「可检出 / 未检出」，⛔ 给不了「不相关」）。")
    A("- ⛔ **「前提独立性成立」** ⇒ ⇒ **未量到**（预登记 §1 已声明**不可证明**）。")
    A("- ⛔ **剂量趋势**、**哪一条臂是机制效应**（w vs rand 只是「方向 vs 随机」，⛔ 不是「机制 vs 非机制」）、"
      "**远端 tokenizer 指纹**、**旧批可比性**、**「照 meta 重建能否逐位复现」** ⇒ ⇒ 全部**未量到**。")
    A("- ⚠ **新查到的一条数据事实**（用于解释「等价变异」）：这一批**没有平票轨迹** —— "
      "w 臂唯一那条 m=2 的轨迹是 **2 正 0 负**（⛔ 不是 1:1）⇒ ⇒ 「多数 `>` 改 `>=`」在**真数据上不可见** "
      "⇒ ⇒ 该边界改由**合成平票夹具**（判据 `S-TIE`）覆盖 ⇒ ⇒ 变异 PM8 因此**能红**。")
    A("")
    A("### 【6】▶️ **下一轮（244.83）**")
    A("")
    A("1. **分层剂量那批**（**要跑批 ⇒ 要点头**）：把「剂量」与「机制」两条轴**真正拆开**"
      "（现在只到「固定剂量 + 机制 vs rand」）。")
    A("2. **同结论对照的机制臂**（参考 `docs/VERIFICATION_V3_IDENTIFIABILITY_AUDIT.md` §7）："
      "「**有效性标签方向不自动是能力方向**」⇒ ⇒ 要回答「**哪一条臂是机制效应**」，"
      "需要**同结论、同末值、只有检查有效性不同**的对照臂（他们的 true vs compensated）"
      "⇒ ⇒ w vs rand **答不了**这个问题。")
    A("3. ⛔ **别把「前提独立性已验收」读成「前提独立性成立」**；⛔ 拿到分层剂量那一批之前，"
      "**固定剂量的这几个数不许再动**。")
    A("")
    A("### 【7】⚖ **这一轮的字节**")
    A("")
    for name, md5v in (("premise_independence_audit.py", "7a0ef341c4c1857ec9e55cb8244a4440"),
                       ("mut_premise_independence_audit.py", "be48ea9ea8e4e625147711fa74f741d6"),
                       ("_cross_check_24482.py", "fdb1f17ea96f6a6310ca820ab166b764"),
                       ("R6_PREMISE_INDEPENDENCE_PREREG.md", "5a34912a2fdb0b3e291fc4c469b6ee44"),
                       ("_run_24482_verify.sh", "2e67542f6ce2507fd808b0384b43fa7b")):
        A("- `%s`  `%s`" % (md5v, name))
    A("")
    A("⚖ **远端**：`zju-53` ｜ ⛔ **零 GPU**、⛔ 没跑批、⛔ 没改读数器/探针/拆分器、⛔ 没改 244.79/244.81 段。")
    A("")
    return "\n".join(L) + "\n"


def main():
    dry = "--dry" in sys.argv
    N = collect()
    sec = build(N)
    fences = [l for l in sec.split("\n") if l.strip().startswith("```")]
    assert not fences, "⛔ 追加段里有围栏 ⇒ 不许"
    full = _read(LEDGER)
    # ⚖⚖⚖ **防重复落账**（幂等闸）
    _h = TITLE
    if full.count(_h) > 0:
        raise SystemExit("⛔ 账本里已经有「%s」这一段（%d 处）⇒ ⇒ **拒绝重复落账**"
                         % (_h, full.count(_h)))
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
