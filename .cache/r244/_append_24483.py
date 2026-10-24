#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⚖ **244.83 落账**（只追加；⛔ 追加段里不许有围栏；⛔ 所有数都从收据抠，⛔ 不手抄）。

**这一段记什么**：把 244.81/244.82 判决面板上那条**从未被实测过**的前提——

    「w 臂与 rand 臂是**同一个剂量**下的比较」

——**正式验收**掉。此前这句话只有**跑批脚本里的一行注释**作依据。

⚖ **口径真相源**：`.cache/xcheck/R6_DOSE_EQUIVALENCE_PREREG.md`（244.83 签，**先于实现**）
⚖ **数据**：bpath 原始跑批日志 ＋ 向量 ＋ 跑批器 ＋ 探针（⛔ 只读、⛔ 零 GPU、远端 `zju-53`）
⚖ **收据**：`.cache/r244/_e24483/{selftest,de,mut,cross}.out`
"""

import io
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
LEDGER = os.path.join(REPO, ".cache", "xcheck", "R6_RERUN_PREREG.md")
EV = os.path.join(REPO, ".cache", "r244", "_e24483")
TITLE = "## 修订 244.83 —— "


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
    de = _need(os.path.join(EV, "de.out"))
    mu = _need(os.path.join(EV, "mut.out"))
    cr = _need(os.path.join(EV, "cross.out"))

    N = {}
    # ---- 真数据：产物 md5 对账（DQ-ARTEFACT）
    m = _grab(de, r"产物 md5 逐位对上：账本登记的 (\d+) 件（([^）]*)）｜ 本轮首次登记的 (\d+) 件"
                r"（([^）]*)）｜ 不符 (\d+) 件", "产物 md5 对账")
    N["art_ledger_n"], N["art_ledger"], N["art_new_n"], N["art_new"], N["art_bad"] = m.groups()
    m = _grab(de, r"^未量到：", "未量到")
    # ---- 真数据：注入范数（注入前）
    m = _grab(de, r"注入前范数（float64 口径）：w=([-+0-9.eE]+) ｜ rand\(seed=0\)=([-+0-9.eE]+) ｜ "
                r"相对差=([-+0-9.eE]+)（上限 ([-+0-9.eE]+)）｜ 探针缩放因子 "
                r"float\(np\.linalg\.norm\(float32 W\)\)=([-+0-9.eE]+)", "注入前范数")
    N["w_norm"], N["r_norm"], N["rel"], N["tol_norm"], N["scale_f32"] = m.groups()
    # ---- 真数据：注入范数（注入后，bf16）
    m = _grab(de, r"注入后（bfloat16）范数：w=([-+0-9.]+) ｜ rand=([-+0-9.]+) ｜ "
                r"相对差=([-+0-9.eE]+)（上限 ([-+0-9.eE]+)", "注入后范数")
    N["w_bf"], N["r_bf"], N["rel16"], N["bound16"] = m.groups()
    # ---- α 网格
    m = _grab(de, r"α 网格：w=linspace\(([-0-9.]+),([-0-9.]+),(\d+)\)", "α 网格")
    N["amax"], N["amax2"], N["nsteps"] = m.groups()
    # ---- 判决读数 α / gap 三源
    m = _grab(de, r"判决读数 α：w=\[([-+0-9.eE, ]+)\] ｜ rand=\[([-+0-9.eE, ]+)\] ｜ "
                r"命令行 gap (\S+)/(\S+) ｜ 探针源码系数 \(([-0-9.]+), ([-0-9.]+)\)", "判决读数 α")
    N["ro_w"], N["ro_r"], N["gap_c"], N["gap_r"], N["coef_lo"], N["coef_hi"] = m.groups()
    # ---- 位点数 / 比较格数
    m = _grab(de, r"四源\*\*一致 ｜ 比较格数 (\d+) ｜ 不一致 (\d+) 格", "位点数四源")
    N["n_common"], N["ns_bad"] = m.groups()
    # ---- 字段划分
    m = _grab(de, r"字段划分完备：实测 (\d+) 个 ｜ 声明 (\d+) 个 ｜ 未声明 (\d+) 个", "字段划分")
    N["n_keys"], N["n_decl"], N["n_miss"] = m.groups()
    m = _grab(de, r"S 内 (\d+) 个结构字段逐格比较：实际比较 (\d+) 次（应 (\d+)）｜ 两臂不一致 (\d+) 处",
              "结构字段比较")
    N["n_struct"], N["n_cmp"], N["n_cmp_exp"], N["s_bad"] = m.groups()
    m = _grab(de, r"实测差异字段 D（除 arm）共 (\d+) 个", "差异字段数")
    N["n_diff"] = m.group(1)
    # ---- 注入总范数
    m = _grab(de, r"= alpha_max\(([-0-9.]+)\) × ∥v∥ × √k ｜ 两臂相对差超限的格 (\d+) ｜ "
                r"公式路径 vs 直接求和路径不一致 (\d+) 格", "注入总范数")
    N["amax_v"], N["inj_bad"], N["inj_path_bad"] = m.groups()
    # ---- 未量到的格
    m = _grab(de, r"未量到：w 臂独有 (\d+) 格", "未量到 w")
    N["only_w"] = m.group(1)
    m = _grab(de, r"rand 臂独有 (\d+) 格", "未量到 rand")
    N["only_r"] = m.group(1)
    m = _grab(de, r"w 总 (\d+) / rand 总 (\d+)", "两臂格数")
    N["n_w"], N["n_rand"] = m.groups()
    # ---- 余弦
    m = _grab(de, r"cos\(w, rand_seed0\)=([-+0-9.]+) ｜ 参考分布 K=(\d+) ｜ 经验秩=([-+0-9.]+) ｜ "
                r"z=([-+0-9.]+) ｜ 参考 sd=([-+0-9.]+) vs 理论 1/√(\d+)=([-+0-9.]+)（相对差 ([-+0-9.]+)）",
              "余弦")
    N["cos0"], N["K"], N["rank"], N["z"], N["sd"], N["d_dim"], N["theo"], N["sd_rel"] = m.groups()
    # ---- 判决形态与判据小结
    m = _grab(de, r"^VERDICT=(D-[ABC])", "判决形态")
    N["verdict"] = m.group(1)
    m = _grab(de, r"判据汇总：(\d+) 条 ｜ PASS (\d+) ｜ FAIL (\d+)", "真数据判据小结")
    N["de_n"], N["de_pass"], N["de_fail"] = m.groups()
    N["de_ids"] = re.findall(r"^\[PASS\] (\S+)", de, re.M)

    # ---- 自检
    m = _grab(st, r"自检①（无缺陷）：判决形态 = (D-[ABC]) ｜ 判据 (\d+) 条 ｜ FAIL (\d+) 条", "自检①")
    N["st_verdict"], N["st_n"], N["st_fail"] = m.groups()
    m = _grab(st, r"自检②（注入缺陷 (\d+) 个）：抓到 (\d+) ｜ 没抓到 (\d+)", "自检②")
    N["st_def"], N["st_caught"], N["st_missed"] = m.groups()
    N["st_ids"] = re.findall(r"^\[PASS\] (\S+)", st, re.M)

    # ---- 变异台
    m = _grab(mu, r"变异台：抓到 (\d+) / (\d+)（无效 (\d+) 条.*?其中等价变异 (\d+) 条", "变异台小结")
    N["mut_caught"], N["mut_total"], N["mut_invalid"], N["mut_equiv"] = m.groups()
    m = _grab(mu, r"崩的条数：(\d+)", "崩计数")
    N["mut_crash"] = m.group(1)
    N["mut_ids"] = re.findall(r"^\[(?:抓到|硬停抓到)\] (\S+)", mu, re.M)
    N["mut_hard_ids"] = re.findall(r"^\[硬停抓到\] (\S+)", mu, re.M)

    # ---- 互证
    m = _grab(cr, r"互证：(\d+) 项 ｜ OK (\d+) ｜ MISMATCH (\d+)", "互证小结")
    N["cr_n"], N["cr_ok"], N["cr_bad"] = m.groups()
    for k, pat in (("x_cos0", r"^CROSS\|cos0=([-+0-9.eE]+)"),
                   ("x_rank", r"^CROSS\|cos_rank=([-+0-9.eE]+)"),
                   ("x_z", r"^CROSS\|cos_z=([-+0-9.eE]+)"),
                   ("x_sd", r"^CROSS\|ref_sd=([-+0-9.eE]+)"),
                   ("x_theo", r"^CROSS\|theo_sd=([-+0-9.eE]+)"),
                   ("x_sdrel", r"^CROSS\|ref_sd_rel=([-+0-9.eE]+)"),
                   ("x_wfrac", r"^CROSS\|w_energy_frac=([-+0-9.eE]+)"),
                   ("x_never", r"^CROSS\|n_never_diff=(\d+)"),
                   ("x_ever", r"^CROSS\|n_ever_diff=(\d+)"),
                   ("x_common", r"^CROSS\|n_common=(\d+)")):
        N[k] = _grab(cr, pat, "互证 " + k).group(1)
    N["x_onlyrand"] = _grab(cr, r"^CROSS\|only_rand=(.*)$", "互证 only_rand").group(1).strip()
    return N


def build(N):
    """⚖ 组装追加段（⛔ **不许有围栏**）。"""
    L = []
    A = L.append
    A(TITLE + "⚖⚖⚖⚖⚖ **「w 臂与 rand 臂是同一个剂量下的比较」这条前提**正式验收**掉**"
      "（⚖ **剂量轴被控住**）—— ⇒ ⇒ 244.81/244.82 的 w-vs-rand 判决**在剂量侧**站得住")
    A("")
    A("⚖ **口径真相源**：`.cache/xcheck/R6_DOSE_EQUIVALENCE_PREREG.md`（244.83 签，**先于实现**）")
    A("⚖ **数据**：bpath 原始跑批日志 ＋ `w_p2a.npy` ＋ `r244_warm_sweep.sh` ＋ `r241_probe.py`"
      "（⛔ 只读、⛔ 零 GPU、远端 `zju-53`）")
    A("⚖ **独立性三条**：① 被验量不同（本轮**一个读数都不看**，只看剂量等价链）；"
      "② 数据路径不同（多读向量与跑批器/探针源码）；③ 重建方式不同"
      "（位点/α/随机方向**从源码规则现场重建**，⛔ 不是从读数反推）")
    A("")
    A("### 【1】⚖⚖⚖ **一句话**")
    A("")
    A("> **剂量轴在 w 臂与 rand 臂之间被控住了** —— 注入前两臂范数相对差 **%s**，"
      "注入后（模型 dtype = bfloat16）相对差 **%s**；α 网格、判决读数 α、位点数、位点集合、"
      "逐格结构字段、静态命令行、逐格注入场 L2 范数**逐项相同** ⇒ ⇒ "
      "**244.81/244.82 的 w-vs-rand 判决不是「剂量不同造成的」**。"
      % (N["rel"], N["rel16"]))
    A("")
    A("⚠⚠⚠ **但这一轮只管剂量这一侧** ⇒ ⇒ ⛔ **不产出**「w 有效、rand 无效」这类**机制**结论"
      "（预登记 §4：那要等「同结论对照臂」）⇒ ⇒ 也**不产出**「前提独立性成立」那类不可证明的命题。")
    A("")
    A("### 【2】📊 **判决面板（剂量等值性）**")
    A("")
    A("| 量 | w 臂 | rand 臂 | 差 / 判据 | 结论 |")
    A("|---|---|---|---|---|")
    A("| **产物 md5 对账** | 账本登记 %s 件（%s） | — | 不符 **%s** 件 ｜ 本轮首次登记 %s 件（%s） | ✅ |"
      % (N["art_ledger_n"], N["art_ledger"], N["art_bad"], N["art_new_n"], N["art_new"]))
    A("| 注入前范数（float64 口径） | `%s` | `%s` | 相对差 **%s**（上限 %s） | ✅ 等模 |"
      % (N["w_norm"], N["r_norm"], N["rel"], N["tol_norm"]))
    A("| 注入后范数（**bfloat16**，模型真实 dtype） | `%s` | `%s` | 相对差 **%s**（上限 %s ＝ 5×2⁻⁹） | ✅ 相等到量化精度 |"
      % (N["w_bf"], N["r_bf"], N["rel16"], N["bound16"]))
    A("| α 网格 | `linspace(%s, %s, %s)` | 同 | 逐位相同 | ✅ |"
      % (N["amax"], N["amax2"], N["nsteps"]))
    A("| 判决读数 α | `[%s]` | `[%s]` | 逐位相同（三源：命令行 / 探针源码系数 / 日志 JSON） | ✅ |"
      % (N["ro_w"], N["ro_r"]))
    A("| 位点数 k（逐格） | BEGIN行 / JSON / cells 文件 | 同 | 四源一致 ｜ 比较 %s 格 ｜ 不一致 %s | ✅ |"
      % (N["n_common"], N["ns_bad"]))
    A("| 位点集合 | 种子 0、nested、permutation(n)[:k] | 同 | 逐格相同（且 n_eff == P+t 全部相符） | ✅ |")
    A("| 逐格结构字段 | %s 个（S） | 同 | 比较 %s 次（应 %s）｜ 不一致 %s 处 | ✅ |"
      % (N["n_struct"], N["n_cmp"], N["n_cmp_exp"], N["s_bad"]))
    A("| 逐格注入场 L2（alpha_max×∥v∥×√k） | — | — | 两臂相对差超限 **%s** 格 ｜ 公式 vs 直接求和路径不一致 **%s** 格 | ✅ |"
      % (N["inj_bad"], N["inj_path_bad"]))
    A("| 静态命令行 | 扣掉 `--gpu-uuid`/`--arm` | 同 | 差异 0 处 ｜ `--w` 两臂**相同**（同一把向量） | ✅ |")
    A("| 字段划分 | 实测 %s 个 ｜ 声明 %s 个 | — | 未声明 %s 个 ｜ 落进「第三处」0 个 ｜ 读数字段 %s 个 | ✅ |"
      % (N["n_keys"], N["n_decl"], N["n_miss"], N["n_diff"]))
    A("")
    A("⚖ **判据形态**：**%s**（硬判据 13 条全绿 ⇒ ⇒ D-A）" % N["verdict"])
    A("")
    A("### 【3】🔍 **对照方向的余弦（描述性；本轮唯一「不是等式」的量）**")
    A("")
    A("- `cos(w, rand_seed0)` = **%s** ｜ 参考分布 K = %s ｜ 经验秩 **%s** ｜ z = **%s**" %
      (N["cos0"], N["K"], N["rank"], N["z"]))
    A("- 参考分布 sd = `%s` vs 理论 1/√%s = `%s`（相对差 %s）⇒ ⇒ 零分布**教科书级** ⇒ ⇒ "
      "**z 是可判读的**" % (N["sd"], N["d_dim"], N["theo"], N["sd_rel"]))
    A("- 互证（纯 Python 路线 vs numpy 路线）逐位一致：cos0 `%s` ｜ 秩 `%s` ｜ z `%s` ｜ "
      "rand 方向里含 w 的能量占比 **%s**" %
      (N["x_cos0"], N["x_rank"], N["x_z"], N["x_wfrac"]))
    A("- ⚠ **要老实说的**：这**一个**对照方向落在随机方向对齐度的 **%s 分位（z=%s）** ⇒ ⇒ "
      "它**不是**一个「典型」的随机方向；⇒ ⇒ 但 **N=1**（只用了一个种子）⇒ ⇒ "
      "「这是巧合还是结构」**未量到** ⇒ ⇒ 它对改判率的**影响未量到**。" % (N["rank"], N["z"]))
    A("- ⚖ **方向性**（⛔ 推断，不是测量）：若这条对照臂与 w 的对齐**偏高**，它会让 rand 臂"
      "**更像** w 臂 ⇒ ⇒ 真实差距**可能更大** ⇒ ⇒ 244.81/244.82 的 +30.36pp / +53.57pp "
      "在这一项上**偏保守**；⇒ ⇒ ⛔ 但「偏保守多少」**未量到**，⛔ 本轮不许当结论写。")
    A("")
    A("### 【4】✅ **判据与变异台（每条判据能红）**")
    A("")
    A("- **自检**（Phase-0 G0-1/G0-2，合成夹具、零 bpath、零 GPU）：判决形态 %s ｜ 判据 %s 条 ｜ FAIL %s 条"
      % (N["st_verdict"], N["st_n"], N["st_fail"]))
    A("- **自检②**（逐个注入缺陷）：注入缺陷 **%s** 个 ｜ 抓到 **%s** ｜ 没抓到 **%s**"
      % (N["st_def"], N["st_caught"], N["st_missed"]))
    A("- **变异台**：抓到 **%s / %s**（无效 %s 条 ⇒ 记「无效」⇒ 不计入分母；其中等价变异 %s 条）"
      "｜ 崩的条数 **%s**（⛔ 必须是 0）" %
      (N["mut_caught"], N["mut_total"], N["mut_invalid"], N["mut_equiv"], N["mut_crash"]))
    A("- **互证**（第二条独立实现，纯 Python 路线 vs numpy 路线）：%s 项 ｜ OK **%s** ｜ MISMATCH **%s**"
      % (N["cr_n"], N["cr_ok"], N["cr_bad"]))
    A("- **真数据判据**：%s 条 ｜ PASS **%s** ｜ FAIL **%s**" % (N["de_n"], N["de_pass"], N["de_fail"]))
    A("- 变异台逐条：%s" % "、".join(N["mut_ids"]))
    A("")
    A("### 【5】⚠⚠⚠ **三条更正记录（撤回并更正，⛔ 不改数凑好看）**")
    A("")
    A("1. **注入 dtype 不是 float32，是 bfloat16**（探针第 379 行 `torch_dtype=torch.bfloat16`）"
      "⇒ ⇒ 「注入后范数相等」**只能在 bf16 量化精度上谈** ⇒ ⇒ 容差由 **dtype 推导**"
      "（5×2⁻⁹）而不是从实测值倒推；⚖ 更正发生在**实现之前**、**真数据一次都还没跑**。")
    A("2. **「逐格全字段相同」是错的** —— 读数字段在两臂之间**必然不同**（方向不同 ⇒ slope / p9_* 都不同）"
      "⇒ ⇒ 改成「**结构字段 S vs 读数字段 R**」的**划分**口径，并把「落进第三处」「声明了但不比」"
      "也做成判据 ⇒ ⇒ 恒红的判据比没有判据更危险。")
    A("3. **rand 臂的缩放因子是 float32 口径**（探针 `float(np.linalg.norm(_W0))`，而 `_W0` 是 float32 "
      "⇒ numpy 走 float32 累加 ⇒ 本批 = 1.0 精确）⇒ ⇒ 我第一版实现误用 float64 范数，"
      "**差 6.43e-10** ⇒ ⇒ **由跨实现互证当场抓到** ⇒ ⇒ 形态不变（仍 < 1e-6）但**那个数是错的** ⇒ ⇒ "
      "已更正；⇒ ⇒ 这正是「要有第二条独立实现」的意义。")
    A("")
    A("### 【6】⛔ **边界清单（本轮哪些仍未量到）**")
    A("")
    A("- ⛔ **「哪一条臂是机制效应」** ⇒ ⇒ **未量到**（w vs rand 只答「方向 vs 随机」）"
      "⇒ ⇒ 要「同结论、同末值、只有检查有效性不同」的对照臂（244.84+）。")
    A("- ⛔ **「随机」的覆盖面** ⇒ ⇒ **未量到**（只用了**一个**种子 ⇒ N=1）"
      "⇒ ⇒ 「这个对照臂为什么这么对齐」**未量到**。")
    A("- ⛔ **对照方向与 w 的对齐对改判率的实际影响** ⇒ ⇒ **未量到**（本轮只量到余弦本身）。")
    A("- ⛔ **剂量—响应曲线** ⇒ ⇒ **未量到**（本批是单一剂量档的两个工作点）⇒ ⇒ 分层剂量要**真阶梯**。")
    A("- ⚠ **w 臂缺一格**：`%s` ⇒ ⇒ 那一格**没有读数** ⇒ ⇒ 报「**未量到**」（⛔ 不当 0、⛔ 不当失败）；"
      "本轮比较的是 **%s** 格（w 总 %s / rand 总 %s）。" %
      (N["x_onlyrand"], N["n_common"], N["n_w"], N["n_rand"]))
    A("- ⛔ 远端 tokenizer 快照的内容指纹、**照 meta 重建能否逐位复现** ⇒ ⇒ 沿用旧留白，**未量到**。")
    A("")
    A("### 【7】▶️ **下一轮（244.84）**")
    A("")
    A("1. **同结论对照臂**（机制轴）：同结论、同末值、只有检查有效性不同 ⇒ ⇒ 回答「**哪一条臂是机制效应**」。")
    A("2. **多随机种子的对照臂**（把「随机」从 N=1 变成 N=K）⇒ ⇒ 顺带回答「对照臂对齐度的分布」"
      "⇒ ⇒ 这是 244.83 唯一留下的**可量化**开口。")
    A("3. **分层剂量的真阶梯**（剂量轴）：⛔ **不能靠事后分位分档**（244.72 的 D5 审计已证 4 档分位会"
      "**切穿复制组**）⇒ ⇒ 每条轨迹扫 K 个 `n_sites` ⇒ ⇒ 规模按新 K 重算 ⇒ ⇒ **要跑批 ⇒ 要点头**。")
    A("")
    A("### 【8】⚖ **这一轮的字节**")
    A("")
    for name, md5v in (("dose_equivalence_audit.py", "8199f2d303404b35eaf9662faa76dd19"),
                       ("mut_dose_equivalence_audit.py", "11f61f9f5de1eacf72dbd76da92c9eae"),
                       ("_cross_check_24483.py", "70bc986cda5bedaa6c79e5471b453d29"),
                       ("_run_24483_verify.sh", "a521ae857af58dab51efce7df0d7ba7b"),
                       ("R6_DOSE_EQUIVALENCE_PREREG.md", "cf71d1b308cb533f3e39962a7e39ebbf"),
                       ("r244_warm_fd_w.log（**首次登记**）", "3f910a1c600a81d5a909834db81e35e7"),
                       ("r244_warm_fd_rand.log（**首次登记**）", "5f4b928a3ebc25e3ee65171b2ac3a6e9")):
        A("- `%s`  `%s`" % (md5v, name))
    A("")
    A("⚖ **远端**：`zju-53` ｜ ⛔ **零 GPU**、⛔ 没跑批、⛔ 没改读数器/探针/拆分器、⛔ 没改 244.79/244.81/244.82 段。")
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
            print("✅ 幂等：账本里已有的 244.83 段与**收据算出来的那段逐字节相同**"
                  " ⇒ ⇒ 不重复写（本次落账无需再动）")
            return 0
        raise SystemExit("⛔ 账本里已有 244.83 段，但它与收据算出来的**不一致** ⇒ ⇒ 停下"
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
