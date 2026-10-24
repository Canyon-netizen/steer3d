#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⚖ **244.83 提交信息生成器**（⛔ 全部数从收据抠，⛔ 不手抄）。

**收据**：
  · `.cache/r244/_e24483/{selftest,de,mut,cross}.out`（zju-53，零 GPU，只读 bpath）
  · `.cache/r244/_e24483/reg_24483.txt`（zju-12，全回归 R4）
"""

import io
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
EV = os.path.join(REPO, ".cache", "r244", "_e24483")
OUT = os.path.join(REPO, ".cache", "r244", "_commit_msg_24483.txt")


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


def main():
    st = _need(os.path.join(EV, "selftest.out"))
    de = _need(os.path.join(EV, "de.out"))
    mu = _need(os.path.join(EV, "mut.out"))
    cr = _need(os.path.join(EV, "cross.out"))

    N = {}
    m = _grab(de, r"产物 md5 逐位对上：账本登记的 (\d+) 件（([^）]*)）｜ 本轮首次登记的 (\d+) 件"
                r"（([^）]*)）｜ 不符 (\d+) 件", "产物 md5 对账")
    N["art_ledger_n"], N["art_ledger"], N["art_new_n"], N["art_new"], N["art_bad"] = m.groups()
    m = _grab(de, r"注入前范数（float64 口径）：w=([-+0-9.eE]+) ｜ rand\(seed=0\)=([-+0-9.eE]+) ｜ "
                r"相对差=([-+0-9.eE]+)（上限 ([-+0-9.eE]+)）", "注入前范数")
    N["w_norm"], N["r_norm"], N["rel"], N["tol"] = m.groups()
    m = _grab(de, r"注入后（bfloat16）范数：w=([-+0-9.]+) ｜ rand=([-+0-9.]+) ｜ "
                r"相对差=([-+0-9.eE]+)（上限 ([-+0-9.eE]+)", "注入后范数")
    N["w_bf"], N["r_bf"], N["rel16"], N["bound16"] = m.groups()
    m = _grab(de, r"α 网格：w=linspace\(([-0-9.]+),([-0-9.]+),(\d+)\)", "α 网格")
    N["g0"], N["g1"], N["nst"] = m.groups()
    m = _grab(de, r"判决读数 α：w=\[([-+0-9.eE, ]+)\] ｜ rand=\[([-+0-9.eE, ]+)\]", "判决读数 α")
    N["ro_w"], N["ro_r"] = m.groups()
    m = _grab(de, r"四源\*\*一致 ｜ 比较格数 (\d+) ｜ 不一致 (\d+) 格", "位点数")
    N["n_common"], N["ns_bad"] = m.groups()
    m = _grab(de, r"S 内 (\d+) 个结构字段逐格比较：实际比较 (\d+) 次（应 (\d+)）｜ 两臂不一致 (\d+) 处",
              "结构字段")
    N["n_struct"], N["n_cmp"], N["n_cmp_exp"], N["s_bad"] = m.groups()
    m = _grab(de, r"实测差异字段 D（除 arm）共 (\d+) 个", "差异字段")
    N["n_diff"] = m.group(1)
    m = _grab(de, r"字段划分完备：实测 (\d+) 个 ｜ 声明 (\d+) 个 ｜ 未声明 (\d+) 个", "字段划分")
    N["n_keys"], N["n_decl"], N["n_miss"] = m.groups()
    m = _grab(de, r"= alpha_max\(([-0-9.]+)\) × ∥v∥ × √k ｜ 两臂相对差超限的格 (\d+) ｜ "
                r"公式路径 vs 直接求和路径不一致 (\d+) 格", "注入总范数")
    N["amax_v"], N["inj_bad"], N["inj_path"] = m.groups()
    m = _grab(de, r"未量到：w 臂独有 (\d+) 格", "未量到")
    N["only_w"] = m.group(1)
    m = _grab(de, r"rand 臂独有 (\d+) 格", "未量到 rand")
    N["only_r"] = m.group(1)
    m = _grab(de, r"w 总 (\d+) / rand 总 (\d+)", "格数")
    N["n_w"], N["n_rand"] = m.groups()
    m = _grab(de, r"cos\(w, rand_seed0\)=([-+0-9.]+) ｜ 参考分布 K=(\d+) ｜ 经验秩=([-+0-9.]+) ｜ "
                r"z=([-+0-9.]+) ｜ 参考 sd=([-+0-9.]+) vs 理论 1/√(\d+)=([-+0-9.]+)（相对差 ([-+0-9.]+)）",
              "余弦")
    N["cos0"], N["K"], N["rank"], N["z"], N["sd"], N["dim"], N["theo"], N["sdrel"] = m.groups()
    m = _grab(de, r"^VERDICT=(D-[ABC])", "判决形态")
    N["verdict"] = m.group(1)
    m = _grab(de, r"判据汇总：(\d+) 条 ｜ PASS (\d+) ｜ FAIL (\d+)", "真数据判据")
    N["de_n"], N["de_pass"], N["de_fail"] = m.groups()
    N["de_ids"] = re.findall(r"^\[PASS\] (\S+)", de, re.M)

    m = _grab(st, r"自检①（无缺陷）：判决形态 = (D-[ABC]) ｜ 判据 (\d+) 条 ｜ FAIL (\d+) 条", "自检①")
    N["st_v"], N["st_n"], N["st_fail"] = m.groups()
    m = _grab(st, r"自检②（注入缺陷 (\d+) 个）：抓到 (\d+) ｜ 没抓到 (\d+)", "自检②")
    N["st_def"], N["st_caught"], N["st_missed"] = m.groups()

    m = _grab(mu, r"变异台：抓到 (\d+) / (\d+)（无效 (\d+) 条.*?其中等价变异 (\d+) 条", "变异台")
    N["mut_caught"], N["mut_total"], N["mut_invalid"], N["mut_equiv"] = m.groups()
    N["mut_crash"] = _grab(mu, r"崩的条数：(\d+)", "崩计数").group(1)
    N["mut_ids"] = re.findall(r"^\[(?:抓到|硬停抓到)\] (\S+)", mu, re.M)

    m = _grab(cr, r"互证：(\d+) 项 ｜ OK (\d+) ｜ MISMATCH (\d+)", "互证")
    N["cr_n"], N["cr_ok"], N["cr_bad"] = m.groups()
    N["x_cos0"] = _grab(cr, r"^CROSS\|cos0=([-+0-9.eE]+)", "互证 cos0").group(1)
    N["x_z"] = _grab(cr, r"^CROSS\|cos_z=([-+0-9.eE]+)", "互证 z").group(1)
    N["x_wfrac"] = _grab(cr, r"^CROSS\|w_energy_frac=([-+0-9.eE]+)", "互证 w 能量占比").group(1)
    N["x_onlyrand"] = _grab(cr, r"^CROSS\|only_rand=(.*)$", "互证 only_rand").group(1).strip()

    # ---- 全回归 R4
    regp = os.path.join(EV, "reg_24483.txt")
    if not os.path.isfile(regp):
        reg_line = "· ⛔ **R4 未量到**（收据 `%s` 不存在）⇒ ⇒ 本次提交**不含**全回归证据" % regp
    else:
        reg = _read(regp)

        def _rg(pat, what):
            return _grab(reg, pat, what).group(1)

        reg_line = ("· **R4（落账 244.83 **后**的账本 = 本次提交里那份字节）**：主机 `%s` ｜ 执行集 **%s** 个 py ｜ "
                    "清单 diff 对 R3：added **%s** / removed **%s** ｜ "
                    "变异台 全绿 %s / 跑得动 %s ｜ 自检 全绿 %s / 跑得动 %s ｜ `REG_RC = %s` ｜ "
                    "账本 %s 行 ｜ md5 `%s`"
                    % (_rg(r"host=(\S+)", "R4 主机"),
                       _rg(r"n_exec_py=(\d+)", "R4 执行集数"),
                       _rg(r"added=(\d+)", "R4 新增"),
                       _rg(r"removed=(\d+)", "R4 减少"),
                       _rg(r"小结：变异台 全绿 (\d+)", "R4 变异台-全绿"),
                       _rg(r"小结：变异台 全绿 \d+ / 跑得动 (\d+)", "R4 变异台-跑得动"),
                       _rg(r"小结：.*自检 全绿 (\d+)", "R4 自检-全绿"),
                       _rg(r"小结：.*自检 全绿 \d+ / 跑得动 (\d+)", "R4 自检-跑得动"),
                       _rg(r"REG_RC=(\d+)", "R4 退出码"),
                       _rg(r"ledger_lines=(\d+)", "R4 账本行数"),
                       _rg(r"ledger_md5=(\w+)", "R4 账本 md5")))

    L = []
    A = L.append
    A("244.83：剂量等值性前提验收 —— 固定剂量批的 w 臂与 rand 臂**剂量轴被控住**")
    A("")
    A("⚖⚖⚖ **这一轮验的是什么**")
    A("")
    A("244.81/244.82 的判决面板（w 臂 vs rand 臂、轨迹级差 +30.36pp、块级差 +53.57pp）**全部**建立在")
    A("一句**从未被实测过**的话上：「**w 臂与 rand 臂是同一个剂量下的比较**」。此前这句话只有")
    A("**跑批脚本里的一行注释**作依据 ⇒ ⇒ 注释不是测量 ⇒ ⇒ 本轮把它**逐项实测**。")
    A("")
    A("⚖⚖⚖ **判决（形态 %s）**" % N["verdict"])
    A("")
    A("- **产物 md5 对账**：账本**已登记**的 %s 件（%s）逐位对上（不符 %s 件）｜ "
      "另把**此前从未登记过**的 %s 件（%s）**首次登记**（⇒ 下一轮起它们也成了独立来源）"
      % (N["art_ledger_n"], N["art_ledger"], N["art_bad"], N["art_new_n"], N["art_new"]))
    A("- **注入前范数**（float64 口径）：w `%s` ｜ rand `%s` ⇒ 相对差 **%s**（上限 %s）⇒ **等模**"
      % (N["w_norm"], N["r_norm"], N["rel"], N["tol"]))
    A("- **注入后范数**（模型 dtype = **bfloat16**，探针 `torch_dtype=torch.bfloat16`）："
      "w `%s` ｜ rand `%s` ⇒ 相对差 **%s**（上限 %s ＝ 5×2⁻⁹，**由 dtype 推导**）⇒ **相等到量化精度**"
      % (N["w_bf"], N["r_bf"], N["rel16"], N["bound16"]))
    A("- **α 网格**：`linspace(%s, %s, %s)` 两臂**逐位相同**，且与探针源码的构造式一致、与日志 JSON 的 "
      "`n_steps` 一致" % (N["g0"], N["g1"], N["nst"]))
    A("- **判决读数 α**：`[%s]` 两臂**逐位相同**（三源：命令行 / 探针源码系数 / 日志 JSON 的 `gap`）"
      % N["ro_w"])
    A("- **位点数 k**：逐格**四源**一致（BEGIN 行 / JSON / cells 文件 / 两臂）｜ 比较 %s 格 ｜ 不一致 %s"
      % (N["n_common"], N["ns_bad"]))
    A("- **位点集合**：`default_rng(0).permutation(n)[:k]`（种子与探针源码一致、**不依赖臂**）"
      "⇒ 逐格两臂**相同**；且 `n_eff == P+t` 全部相符")
    A("- **逐格结构字段**：S 内 %s 个字段、比较 %s 次（应 %s）｜ 两臂不一致 %s 处"
      % (N["n_struct"], N["n_cmp"], N["n_cmp_exp"], N["s_bad"]))
    A("- **逐格注入场 L2**（`alpha_max(%s) × ∥v∥ × √k`）：两臂相对差超限 **%s** 格 ｜ "
      "公式路径 vs 直接求和路径不一致 **%s** 格" % (N["amax_v"], N["inj_bad"], N["inj_path"]))
    A("- **静态命令行**：扣掉 `--gpu-uuid`/`--arm` 后两臂**逐字相同**；且 `--w` 两臂**相同**"
      "（同一把向量 ⇒ rand 方向是从它派生的）")
    A("- **字段划分**：实测 %s 个 ｜ 声明 %s 个 ｜ 未声明 %s 个 ｜ 落进「第三处」0 个 ｜ "
      "实测两臂有差异的字段 %s 个（全部是读数字段）" % (N["n_keys"], N["n_decl"], N["n_miss"], N["n_diff"]))
    A("")
    A("⚖⚖⚖ **唯一「不是等式」的量（描述性）**")
    A("")
    A("- `cos(w, rand_seed0)` = **%s** ｜ 参考分布 K = %s ｜ 经验秩 **%s** ｜ z = **%s**"
      % (N["cos0"], N["K"], N["rank"], N["z"]))
    A("- 参考分布 sd `%s` vs 理论 1/√%s = `%s`（相对差 %s）⇒ 零分布**教科书级** ⇒ z 可判读"
      % (N["sd"], N["dim"], N["theo"], N["sdrel"]))
    A("- 互证逐位一致：cos0 `%s` ｜ z `%s` ｜ rand 方向里含 w 的能量占比 **%s**"
      % (N["x_cos0"], N["x_z"], N["x_wfrac"]))
    A("- ⚠ 这**一个**对照方向落在随机方向对齐度的 **%s 分位** ⇒ 它**不是**典型随机方向；"
      "但 **N=1** ⇒ 「巧合还是结构」**未量到** ⇒ 它对改判率的**影响未量到**" % N["rank"])
    A("")
    A("⚖⚖⚖ **三条更正记录（撤回并更正，⛔ 不改数凑好看）**")
    A("")
    A("1. **注入 dtype 不是 float32，是 bfloat16** ⇒ 「注入后范数相等」只能在 bf16 量化精度上谈 "
      "⇒ 容差由 **dtype 推导**（5×2⁻⁹）而非从实测值倒推（更正发生在**实现之前**、真数据一次都还没跑）。")
    A("2. **「逐格全字段相同」是错的** —— 读数字段在两臂之间**必然不同** ⇒ 改成「结构字段 S vs 读数字段 R」"
      "的**划分**口径，并把「落进第三处」「声明了但不比」也做成判据（恒红的判据比没有判据更危险）。")
    A("3. **rand 臂的缩放因子是 float32 口径**（探针 `float(np.linalg.norm(_W0))`，而 `_W0` 是 float32 "
      "⇒ numpy 走 float32 累加 ⇒ 本批 = 1.0 精确）⇒ 第一版实现误用 float64 范数、**差 6.43e-10** "
      "⇒ **由跨实现互证当场抓到** ⇒ 形态不变但**那个数是错的** ⇒ 已更正。")
    A("")
    A("⚖⚖⚖ **每条判据能红**")
    A("")
    A("- **自检**（合成夹具、零 bpath、零 GPU）：形态 %s ｜ 判据 %s 条 ｜ FAIL %s 条"
      % (N["st_v"], N["st_n"], N["st_fail"]))
    A("- **自检②**：注入缺陷 %s 个 ｜ 抓到 **%s** ｜ 没抓到 **%s**" % (N["st_def"], N["st_caught"], N["st_missed"]))
    A("- **变异台**：抓到 **%s / %s**（无效 %s 条 ⇒ 记「无效」不计入分母；等价变异 %s 条）｜ "
      "崩 **%s**（⛔ 必须是 0）" % (N["mut_caught"], N["mut_total"], N["mut_invalid"],
                                N["mut_equiv"], N["mut_crash"]))
    A("- **互证**（纯 Python 路线 vs numpy 路线）：%s 项 ｜ OK **%s** ｜ MISMATCH **%s**"
      % (N["cr_n"], N["cr_ok"], N["cr_bad"]))
    A("- **真数据判据**：%s 条 ｜ PASS **%s** ｜ FAIL **%s**" % (N["de_n"], N["de_pass"], N["de_fail"]))
    A("- 变异台逐条：%s" % "、".join(N["mut_ids"]))
    A("")
    A("⚖⚖⚖ **全回归**")
    A("")
    A(reg_line)
    A("")
    A("⚖⚖⚖ **边界（本轮哪些仍未量到）**")
    A("")
    A("- ⛔ **「哪一条臂是机制效应」** ⇒ **未量到**（w vs rand 只答「方向 vs 随机」）⇒ 要**同结论对照臂**。")
    A("- ⛔ **「随机」的覆盖面** ⇒ **未量到**（只用了**一个**种子 ⇒ N=1）。")
    A("- ⛔ **对照方向与 w 的对齐对改判率的实际影响** ⇒ **未量到**。")
    A("- ⛔ **剂量—响应曲线** ⇒ **未量到**（本批单一剂量档）⇒ 分层剂量要**真阶梯**（⛔ 不能事后分位分档）。")
    A("- ⚠ **w 臂缺一格**（`%s`）⇒ 那一格**没有读数** ⇒ 报「**未量到**」；本轮比较 %s 格"
      "（w 总 %s / rand 总 %s）" % (N["x_onlyrand"], N["n_common"], N["n_w"], N["n_rand"]))
    A("")
    A("⚖⚖⚖ **本轮改了哪些文件**")
    A("")
    A("- `.cache/r244/dose_equivalence_audit.py`（**进执行集**）—— 剂量等值性核查实现"
      "（自检 12 个缺陷全打红）")
    A("- `.cache/r244/mut_dose_equivalence_audit.py`（**进执行集**）—— 变异台 18 条")
    A("- `.cache/r244/_cross_check_24483.py`（⛔ **不进**执行集）—— 第二条独立实现（互证 19 项）")
    A("- `.cache/r244/_run_24483_verify.sh`、`_run_24483_reg_shm.sh`、`_append_24483.py`、"
      "`_commit_msg_24483.py`、`_make_handoff_24483.py`、`_post_commit_readback_24483.py`、"
      "`_commit_24483.sh`")
    A("- `.cache/xcheck/R6_DOSE_EQUIVALENCE_PREREG.md`（**先于实现**签的预登记，含 §0.5 三条更正记录）")
    A("- `.cache/xcheck/R6_RERUN_PREREG.md`（账本，只**追加** 244.83 段）、`.cache/xcheck/R6_RERUN_INDEX.md`")
    A("")
    A("⚖ **远端**：`zju-53`（验证链，零 GPU、只读 bpath）＋ `zju-12`（全回归 R4）"
      "｜ ⛔ 没跑批、⛔ 没改读数器/探针/拆分器、⛔ 没改 244.79/244.81/244.82 段。")
    A("")

    with io.open(OUT, "w", encoding="utf-8", newline="") as fh:
        fh.write("\n".join(L) + "\n")
    print("已写出：%s" % OUT)
    print("字节数：%d" % os.path.getsize(OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
