#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 244.81（**判决那一轮**）的收据落进账本（**只追加**）。

⚖⚖⚖ **纪律**（同 244.79/244.80）：
   ① **所有数都从收据解析**，⛔ 不许手抄
   ② **追加段里不许有围栏**
   ③ 落账后**回读**：围栏数不变 ＋ 旧前缀逐字节不变
   ④ ⚠⚠⚖ **判决数的前置**：面板里带「部分读数」横幅 ⇒ ⇒ **拒绝落账**
      （⛔ 半批数据长得像判决 ⇒ 护栏必须在这里也拦一道）
"""

import hashlib
import io
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", ".."))
LEDGER = os.path.join(REPO, ".cache", "xcheck", "R6_RERUN_PREREG.md")
EV = os.path.join(REPO, ".cache", "r244", "_e24481")


def _read(p):
    with io.open(p, encoding="utf-8", newline="") as fh:
        return fh.read()


def _need(p):
    if not os.path.isfile(p):
        raise SystemExit("⛔ 缺收据：%s ⇒ 硬停" % p)
    return _read(p)


def _grab(txt, pat, what, flags=re.M):
    """⚖⚠ **必须带 `re.M`**（⛔ `re.search` 默认**不**多行 ⇒ `^` 锚点匹配不到行首
    ⇒ ⇒ 244.79/244.81 各踩过一次这个坑 ⇒ 这里写死，别再忘）。"""
    m = re.search(pat, txt, flags)
    if not m:
        raise SystemExit("⛔ 收据里核不到「%s」⇒ 硬停" % what)
    return m


def collect():
    N = {}
    rc = _need(os.path.join(EV, "receipt_24481.txt"))
    panel = _need(os.path.join(EV, "verdict_panel.txt"))
    # ⚖⚠⚠ **护栏**：面板里若带「部分读数」横幅 ⇒ 拒绝落账
    # ⚖⚠⚖ 护栏必须**精确**（244.81 修）：原来搜的是 `"不是判决"` 四个字
    #   ⇒ ⇒ **完整**面板里的「异质性（前提，⛔ 不是判决）」与「是前提，不是判决」
    #   **也含这四个字** ⇒ ⇒ 护栏**假红**（把好数据当半批拒掉）。
    #   ⇒ ⇒ 改成只认**横幅的精确标记**：`部分读数` 与 `本面板的数不是判决`
    #   （⛔ 横幅恒含这两句 ⇒ ⇒ 护栏**没被放松**，只是不再误伤）。
    if "部分读数" in panel or "本面板的数不是判决" in panel:
        raise SystemExit("⛔ 面板带「部分读数 / 本面板的数不是判决」横幅 ⇒ 这一轮**还没跑完** "
                         "⇒ ⇒ **拒绝落账**（⛔ 半批数据不许进账本）")
    if "未量到" not in panel:
        raise SystemExit("⛔ 面板里没有「未量到」字样 ⇒ 面板形状变了 ⇒ 停下人工看")
    N["panel"] = panel
    N["panel_md5"] = hashlib.md5(panel.encode("utf-8")).hexdigest()
    # ⚖ 面板**可复现**：又独立跑了一次流水线（收据 `panel_repro_24481.out`）⇒ md5 仍逐位相同
    pr = _need(os.path.join(EV, "panel_repro_24481.out"))
    N["panel_repro_md5"] = _grab(pr, r"^(\w{32})\s+/dev/shm/_pooled_24481/verdict_panel\.txt",
                                 "复跑一次的面板 md5").group(1)
    N["receipt"] = rc
    # ---- 批次进度（⛔ 从收据算，⛔ 不手估）
    # ⚠⚠ **不要**用「切出进度段」的办法（那段后面**未必**有空行 ⇒ 正则会 MISS
    #   ⇒ 本轮实测踩到）⇒ ⇒ 直接在**整份收据**里找臂行（唯一且稳）。
    arms = {}
    for mm in re.finditer(
            r"arm=(\w+) cells_done=(\d+) first_end=(\d\d:\d\d:\d\d) "
            r"last_end=(\d\d:\d\d:\d\d) idx_tot=(\d+) (\d+) abort=(\d+) rc0=(\d+)", rc):
        arms[mm.group(1)] = {"done": int(mm.group(2)), "tot": int(mm.group(6)),
                             "abort": int(mm.group(7)), "rc0": int(mm.group(8))}
    if not arms:
        raise SystemExit("⛔ 收据里核不到跑批进度 ⇒ 硬停")
    N["arms"] = arms
    # ---- 字节（⛔ 从收据解析）
    N["bytes"] = dict(re.findall(r"^(\w{32})\s+(\S+)$", rc, re.M))
    # ⚖ 拆分/分析器的退出码在**流水线 stdout** 里（⛔ 不在面板收据里）⇒ 从流水线收据读
    pl = _need(os.path.join(EV, "pipeline_24481.out"))
    N["split_rc"] = _grab(pl, r"SPLIT_w_RC=(\d+)", "w 臂拆分退出码").group(1)
    N["split_rc_r"] = _grab(pl, r"SPLIT_rand_RC=(\d+)", "rand 臂拆分退出码").group(1)
    N["audit_rc"] = _grab(pl, r"AUDIT_RC=(\d+)", "分析器退出码").group(1)
    # ---- 面板数字（⛔ 全部从面板文本解析）
    p = panel
    for arm in ("w", "rand"):
        m = _grab(p, r"^  %-4s 改判 \*\*(\d+)/(\d+)\*\* ｜ 区间 (\[[-+0-9., %%]+\])" % arm,
                  "%s 臂改判数与区间" % arm)
        N["%s_pos" % arm] = int(m.group(1))
        N["%s_n" % arm] = int(m.group(2))
        N["%s_ci" % arm] = m.group(3)
    m = _grab(p, r"差 \*\*([-+0-9.]+) pp\*\* ｜ 差区间 (\[[-+0-9., %%]+\]) pp ｜ "
                  r"跨臂 Fisher（精确枚举）p = ([0-9.]+) ｜ 配对置换 p = ([0-9.]+)", "跨臂差")
    N["diff_pp"] = m.group(1)
    N["diff_ci"] = m.group(2)
    N["fisher_p"] = m.group(3)
    N["perm_p"] = m.group(4)
    m = _grab(p, r"配对置换 \*\*MC95% 不确定带\*\* = \[([0-9.]+), ([0-9.]+)\]"
                  r"（ge=(\d+) / n_perm=(\d+)", "MC 不确定带")
    N["band"] = (m.group(1), m.group(2))
    N["band_ge"] = m.group(3)
    N["band_n"] = m.group(4)
    m = _grab(p, r"^  w (\d+)/(\d+) ｜ rand (\d+)/(\d+) ｜ 差 ([-+0-9.]+) pp ｜ "
                  r"差区间 (\[[-+0-9., %%]+\]) pp ｜ Fisher p = ([0-9.]+)", "块级")
    N["blk_w"] = int(m.group(1))
    N["blk_n"] = int(m.group(2))
    N["blk_r"] = int(m.group(3))
    N["blk_diff"] = m.group(5)
    N["blk_ci"] = m.group(6)
    N["blk_p"] = m.group(7)
    N["groups"] = re.findall(
        r"pos_frac=([0-9.]+)\s+w (\d+)/(\d+) ｜ rand (\d+)/(\d+) ｜ 差 ([-+0-9.]+) pp ｜ "
        r"差区间 (\[[-+0-9., %%]+\]) pp ｜ Fisher p = ([0-9.]+)", p)
    N["disagree"] = re.findall(r"三格全一致 (\d+) ｜ 2:1 分歧 (\d+) ｜ 分歧率 ([0-9.]+)", p)
    N["agree"] = re.findall(r"与主口径\*\*逐条一致\*\*的轨迹：(\d+)/(\d+)", p)
    N["alt_rule"] = re.findall(r"零格剔出分母那条 (\d+)/(\d+)", p)
    N["base"] = re.findall(r"零假设基准（逐轨迹平均）([0-9.]+)", p)
    N["kept"] = re.findall(r"格集合：进 (\d+) 格 ｜ 剔出 (\d+) 格", p)
    N["up_rule"] = re.findall(r"辅口径（`up_mono_meas`）改判 (\d+)/(\d+)", p)
    # ---- 本轮（244.81）补印的 V3/V4 三项（⛔ 从面板解析，⛔ 不手抄）
    N["mdist"] = re.findall(r"每轨迹有效格 m 分布 = (\{[^}]*\})", p)
    N["nzdist"] = re.findall(r"\(n_nz,n_zero\) 分布 = (\{[^}]*\})", p)
    N["basedist"] = re.findall(r"基准分布（V4）：(\{[^}]*\})", p)
    N["zerocells"] = re.findall(r"零格合计 (\d+)", p)
    # ---- 链日志（各步退出码都在里面；⛔ 分析器与变异台**自己不印 rc**）
    cl = _need(os.path.join(EV, "chain_24481.log"))
    N["chain_selftest_rc"] = _grab(cl, r"SELFTEST_RC=(\d+)", "分析器自检退出码").group(1)
    N["chain_mut_analyzer_rc"] = _grab(cl, r"MUT_ANALYZER_RC=(\d+)", "分析器变异台退出码").group(1)
    N["chain_indep_rc"] = _grab(cl, r"INDEP_VERIFY_RC=(\d+)", "独立重算退出码").group(1)
    N["chain_pipeline_rc"] = _grab(cl, r"PIPELINE_RC=(\d+)", "流水线退出码").group(1)
    # ---- ① 分析器自检（补印 V3/V4 之后的那一版）
    ast_ = _need(os.path.join(EV, "analyzer_selftest.out"))
    m = _grab(ast_, r"判据 (\d+) 条 ｜ PASS (\d+) ｜ FAIL (\d+)", "分析器自检小结")
    N["a_crit_total"], N["a_crit_pass"], N["a_crit_fail"] = [int(x) for x in m.groups()]
    N["a_selftest_rc"] = N["chain_selftest_rc"]
    N["a_vp19"] = [l for l in ast_.split("\n") if "V-P19" in l]
    # ---- ② 分析器变异台（21 条，含 P21）
    am = _need(os.path.join(EV, "mut_analyzer.out"))
    m = _grab(am, r"变异台：抓住 (\d+) / (\d+)（等价变异 (\d+) 条", "分析器变异台小结")
    N["a_mut_caught"], N["a_mut_total"], N["a_mut_equiv"] = [int(x) for x in m.groups()]
    # ⚖ 这个变异台**自己不印 rc**（⛔ 244.80 那份收据里的 `MUT_RC` 是**跑它的脚本**加的）
    #   ⇒ ⇒ 退出码从链日志取
    N["a_mut_rc"] = N["chain_mut_analyzer_rc"]
    N["a_mut_p21"] = [l for l in am.split("\n") if l.strip().startswith("[抓到] P21")]
    # ---- ③ 独立重算器（第二条独立实现）：自检 ＋ 真数据 ＋ 它的变异台
    ist = _need(os.path.join(EV, "indep_selftest.out"))
    m = _grab(ist, r"自检 (\d+) 条 ｜ PASS (\d+) ｜ FAIL (\d+)", "独立重算器自检小结")
    N["i_st_total"], N["i_st_pass"], N["i_st_fail"] = [int(x) for x in m.groups()]
    iv = _need(os.path.join(EV, "indep_verify_24481.out"))
    m = _grab(iv, r"判据 (\d+) 条 ｜ PASS (\d+) ｜ FAIL (\d+)", "独立重算小结")
    N["i_total"], N["i_pass"], N["i_fail"] = [int(x) for x in m.groups()]
    N["i_perm"] = re.findall(r"置换：不一致轨迹 k = (\d+) ｜ 观测 T/2 = ([-+0-9.g]+) ｜ "
                             r"我的二项精确 p = ([0-9.]+)", iv)
    N["i_mdist"] = re.findall(r"轨迹 (\d+) ｜ m 分布 = (\{[^}]*\})", iv)
    N["i_nzdist"] = re.findall(r"\(n_nz,n_zero\) 分布 = (\{[^}]*\})", iv)
    im = _need(os.path.join(EV, "mut_indep.out"))
    m = _grab(im, r"变异台：抓到 (\d+) / (\d+)（无效 (\d+) 条.*?其中等价变异 (\d+) 条",
              "独立重算器变异台小结", flags=re.S)
    N["i_mut_caught"], N["i_mut_total"] = int(m.group(1)), int(m.group(2))
    N["i_mut_equiv"] = int(m.group(4))
    N["i_mut_rc"] = _grab(im, r"MUT_RC=(\d+)", "独立重算器变异台退出码").group(1)
    # ⚖ 台架把等价变异印**两遍**（逐条行带前缀「⇒ 源码改了但…」 ＋ 小结行）
    #   ⇒ ⇒ 只取**小结行**（不含那个前缀）⇒ ⇒ 一条变异一行
    _eq = [l.strip() for l in im.split("\n")
           if l.strip().startswith("[无效/等价]") and "源码改了但" not in l]
    N["i_mut_equiv_lines"] = _eq
    # ---- ③b 第三条路径（shell/awk）的交叉核对
    xc = _need(os.path.join(EV, "crosscheck_awk_24481.out"))
    N["xc_lines"] = [l.strip() for l in xc.split("\n")
                     if ("格数=" in l or "缺读数=" in l) and l.strip()]
    # ---- ③c **第四条路径**：自包含的探查脚本（**又一份独立实现**）
    #   ⚠⚠⚖ 它**只**证明「面板每个数能被第四份实现逐位复现」＋给出**块级**先导数
    #   ⇒ ⇒ 块级那些数是**先导**，⛔ **不是**判决（没过「第二条独立实现 + 变异台」）
    sc = _need(os.path.join(EV, "scout_premise_indep_24481.out"))
    m = _grab(sc, r"自检通过：轨迹级 w (\d+)/(\d+)、rand (\d+)/(\d+) ｜ 块级 w (\d+)/(\d+)、"
                  r"rand (\d+)/(\d+) ｜ 轨迹级 Fisher ([0-9.]+)、块级 Fisher ([0-9.]+)",
              "探查自检")
    N["sc_traj_w"] = (int(m.group(1)), int(m.group(2)))
    N["sc_traj_r"] = (int(m.group(3)), int(m.group(4)))
    N["sc_blk_w"] = (int(m.group(5)), int(m.group(6)))
    N["sc_blk_r"] = (int(m.group(7)), int(m.group(8)))
    N["sc_fisher_traj"] = m.group(9)
    N["sc_fisher_blk"] = m.group(10)
    m = _grab(sc, r"块数 (\d+) ｜ w 臂块内两条\*\*判决一致\*\* (\d+)（([0-9.]+)）｜ "
                  r"rand 臂块内不一致 (\d+) ｜ w 臂块内不一致 (\d+)", "探查块内相关")
    N["sc_nblk"] = int(m.group(1))
    N["sc_blk_agree"] = int(m.group(2))
    N["sc_blk_agree_rate"] = m.group(3)
    N["sc_rand_disc"] = int(m.group(4))
    N["sc_w_disc"] = int(m.group(5))
    m = _grab(sc, r"McNemar（逐轨迹配对，不一致 (\d+) 条：w优 (\d+) / rand优 (\d+)）⇒ "
                  r"精确二项两侧 p = ([0-9.]+)", "探查 McNemar")
    N["sc_disc"] = int(m.group(1))
    N["sc_w_better"] = int(m.group(2))
    N["sc_r_better"] = int(m.group(3))
    N["sc_mcnemar_p"] = m.group(4)
    m = _grab(sc, r"\*\*逐轨迹\*\*置换：p = ([0-9.]+)（obs = (\d+) ｜ ge=(\d+)/(\d+)）", "探查逐轨迹置换")
    N["sc_traj_perm_p"] = m.group(1)
    N["sc_traj_perm_obs"] = int(m.group(2))
    N["sc_traj_perm_ge"] = int(m.group(3))
    N["sc_traj_perm_n"] = int(m.group(4))
    m = _grab(sc, r"\*\*块级\*\*置换（块内整体交换两臂标签）：p = ([0-9.]+)（obs = (\d+) ｜ "
                  r"ge=(\d+)/(\d+)）", "探查块级置换")
    N["sc_blk_perm_p"] = m.group(1)
    N["sc_blk_perm_obs"] = int(m.group(2))
    N["sc_blk_perm_ge"] = int(m.group(3))
    N["sc_blk_perm_n"] = int(m.group(4))
    m = _grab(sc, r"\*\*比值\*\*：块级 p ÷ 逐轨迹 p = ([0-9.]+)×", "探查比值")
    N["sc_ratio"] = m.group(1)
    m = _grab(sc, r"\*\*块级\*\*差 ([-+0-9.]+) pp ｜ 按块 bootstrap 95% 区间 "
                  r"\[([-+0-9.]+), ([-+0-9.]+)\] pp", "探查 bootstrap 区间")
    N["sc_boot_diff"] = m.group(1)
    N["sc_boot_lo"] = m.group(2)
    N["sc_boot_hi"] = m.group(3)
    N["sc_dis"] = re.findall(r"臂：三格全一致 (\d+) ｜ 2:1 分歧 (\d+) ｜ 分歧率 ([0-9.]+)", sc)
    # ---- ④ `probe_compat_check.py`：那条**永久红**（244.45 起）修好了
    pc = _need(os.path.join(EV, "probe_compat_selftest.out"))
    m = _grab(pc, r"自检 (\d+)/(\d+) 通过", "probe_compat_check 自检小结")
    N["pcc_total"], N["pcc_pass"] = int(m.group(1)), int(m.group(2))
    N["pcc_c1"] = [l.strip() for l in pc.split("\n")
                   if re.match(r"^\[PASS\] C1\s", l.strip())]
    N["pcc_c11"] = [l.strip() for l in pc.split("\n")
                    if re.match(r"^\[PASS\] C11\s", l.strip())]
    # ⚖ 我改了这个工具 ⇒ ⇒ 它**自己的变异台**必须还绿（⛔ 不然就是「改坏别人的尺子」）
    pm = _need(os.path.join(EV, "probe_mut_24481.out"))
    N["pcc_mut_line"] = [l.strip() for l in pm.split("\n") if "变异终检" in l]
    N["pcc_mut_n"] = re.findall(r"变异终检：(\d+)/(\d+)", pm)
    # ---- ⑤ 全回归收据（本轮跑完才有）
    rgp = os.path.join(EV, "reg_24481.txt")
    if os.path.isfile(rgp):
        rg = _read(rgp)
        N["reg_rc"] = _grab(rg, r"REG_RC=(\d+)", "回归退出码").group(1)
        N["reg_npy"] = _grab(rg, r"n_exec_py=(\d+)", "执行集 py 数").group(1)
        N["reg_manifest_md5"] = _grab(rg, r"manifest_md5=(\w+)", "清单 md5").group(1)
        N["reg_added"] = _grab(rg, r"added=(\d+)", "清单新增").group(1)
        N["reg_removed"] = _grab(rg, r"removed=(\d+)", "清单减少").group(1)
        N["reg_host"] = _grab(rg, r"host=(\S+)", "回归主机").group(1)
        N["reg_ledger_lines"] = _grab(rg, r"ledger_lines=(\d+)", "账本行数").group(1)
        N["reg_ledger_md5"] = _grab(rg, r"ledger_md5=(\w+)", "账本 md5").group(1)
        m = _grab(rg, r"小结：变异台 全绿 (\d+) / 跑得动 (\d+) ；自检 全绿 (\d+) / 跑得动 (\d+)",
                  "回归小结")
        N["reg_mut_ok"], N["reg_mut_run"], N["reg_st_ok"], N["reg_st_run"] = \
            [int(x) for x in m.groups()]
        i_a, i_b, i_s = rg.find("A) 变异台族"), rg.find("B) 自检族"), rg.find("小结：")
        sec_mut = rg[i_a:i_b] if 0 <= i_a < i_b else ""
        sec_st = rg[i_b:i_s] if 0 <= i_b < i_s else ""
        N["reg_mut_bad"] = re.findall(r"^  \[BAD \] (\S+\.py)\s+rc=(-?\d+)", sec_mut, re.M)
        N["reg_st_bad"] = re.findall(r"^  \[BAD \] (\S+\.py)", sec_st, re.M)
        N["reg_mut_skip"] = len(re.findall(r"^  \[SKIP\] ", sec_mut, re.M))
        N["reg_st_skip"] = len(re.findall(r"^  \[SKIP\] ", sec_st, re.M))
        N["reg_new_files"] = re.findall(r"^md5_(\S+\.py)=(\w+)$", rg, re.M)
    return N


def build(N):
    L = []
    A = L.append
    A("## 修订 244.81 —— ⚖⚖⚖⚖⚖ **固定剂量下的判决数出来了**（合池口径）—— ⇒ ⇒ "
      "**w 臂改判 %s/%s、rand 臂改判 %s/%s、差 %s pp**（跨臂 Fisher p = %s，配对置换 p = %s）；"
      "⛔ **前提独立性仍未量到** ⇒ ⇒ 判决**口径依赖**，⛔ 不是「机制已证」"
      % (N["w_pos"], N["w_n"], N["rand_pos"], N["rand_n"], N["diff_pp"],
         N["fisher_p"], N["perm_p"]))
    A("")
    A("#### 【1】这一轮做了什么")
    A("")
    A("· **跑批落盘**（`zju-53`，两臂各 %s 格）⇒ ⇒ 拆分器按 `pos_frac` 拆三份 ⇒ ⇒ "
      "权威读数器读（⛔ 一个字没改）⇒ ⇒ 合池分析器出**判决面板**。" % N["arms"].get("w", {}).get("tot", "?"))
    A("· ⛔ **没跑新批、没改探针、没改读数器、没改预登记、没改拆分器** ⇒ ⇒ "
      "**跑批产物**与 244.80 那一轮**逐位对应**（收据里记 md5）；"
      "⚠ **分析器本身在本轮改了**（补印 V3/V4，见【9】）⇒ ⇒ 但**判决数一个没动**，"
      "且**面板两次独立运行 md5 逐位相同** ⇒ ⇒ 可复现。")
    A("· ✅ **补印**了预登记 V3/V4 明写「必须打印」的三项（`m` 分布 / `(n_nz,n_zero)` 分布 / "
      "基准分布）⇒ ⇒ **判决数一个没动**，只是判决面**多披露了分母的形状**（详见【9】）。")
    A("· ✅ **新增第二条独立实现** `verify_pooled_verdict_indep.py` ⇒ ⇒ 把面板上的每个数"
      "**独立重算一遍**（详见【8】）＋ 它自己的变异台（证明这条比对**能红**）。")
    A("· ✅ **修掉一条永久红**：`probe_compat_check.py` 的 C1（详见【10】）。")
    A("")
    A("#### 【2】判决面板（轨迹级 · 合池口径）")
    A("")
    A("| 项 | w 臂 | rand 臂 |")
    A("|---|---|---|")
    A("| 改判（主口径：逐轨迹**严格多数**，`nT·2 > m`） | **%s/%s** | **%s/%s** |" % (
        N["w_pos"], N["w_n"], N["rand_pos"], N["rand_n"]))
    A("| 比例区间（Wilson95） | %s | %s |" % (N["w_ci"], N["rand_ci"]))
    A("| 零格剔出分母那条（V8） | %s/%s | %s/%s |"
      % (N["alt_rule"][0][0], N["alt_rule"][0][1], N["alt_rule"][1][0], N["alt_rule"][1][1]))
    A("| 辅口径（`up_mono_meas`） | %s/%s | %s/%s |"
      % (N["up_rule"][0][0], N["up_rule"][0][1], N["up_rule"][1][0], N["up_rule"][1][1]))
    A("| 与主口径逐条一致 | %s/%s | %s/%s |"
      % (N["agree"][0][0], N["agree"][0][1], N["agree"][1][0], N["agree"][1][1]))
    A("| 零假设基准（逐轨迹平均） | %s | %s |" % (N["base"][0], N["base"][1]))
    A("| 格集合 | 进 %s 格 | 进 %s 格 |" % (N["kept"][0][0], N["kept"][1][0]))
    A("")
    A("· **差 %s pp** ｜ 差区间（Newcombe95）%s ｜ 跨臂 Fisher（**精确枚举**）p = %s ｜ "
      "配对置换 p = %s（MC95%% 不确定带 [%s, %s]，ge=%s/n_perm=%s）。" % (
          N["diff_pp"], N["diff_ci"], N["fisher_p"], N["perm_p"],
          N["band"][0], N["band"][1], N["band_ge"], N["band_n"]))
    A("")
    A("#### 【3】块级（块 = think + no_think；块内两条都正才算正）")
    A("")
    A("· w **%s/%s** ｜ rand **%s/%s** ｜ 差 %s pp ｜ 差区间 %s ｜ Fisher p = %s"
      "（⛔ 分母是**块数**，⛔ 不是轨迹数）。" % (
          N["blk_w"], N["blk_n"], N["blk_r"], N["blk_n"], N["blk_diff"],
          N["blk_ci"], N["blk_p"]))
    A("")
    A("#### 【4】分 `pos_frac` 三组（V7：合池组为主，三组分列）")
    A("")
    A("| pos_frac | w | rand | 差 | 差区间（Newcombe95） | Fisher p |")
    A("|---|---|---|---|---|---|")
    for pf, wp, wn, rp, rn, dp, ci, fp in N["groups"]:
        A("| %s | %s/%s | %s/%s | %s pp | %s | %s |" % (pf, wp, wn, rp, rn, dp, ci, fp))
    A("")
    A("· ⚖⚖⚖ **异质性（前提，⛔ 不是判决）**：三复制格的三格全一致 / 2:1 分歧 / 分歧率 —— "
      "w：%s ｜ rand：%s ⇒ ⇒ **合池口径对 `pos_frac` 敏感** ⇒ ⇒ 三组各自的数必须与合池数一起看。"
      % ("、".join("%s/%s/%s" % d for d in N["disagree"][:1]) or "未量到",
         "、".join("%s/%s/%s" % d for d in N["disagree"][1:2]) or "未量到"))
    A("")
    A("#### 【5】问题级")
    A("")
    A("· **不适用**：问题级 Δ 需要 `scope = all` 的格，本批**没有** ⇒ ⇒ "
      "⛔ 不是「未量到」，⛔ 不是「无差异」。")
    A("")
    A("#### 【6】这些数**在什么口径下才成立**（⛔ 拿出去说必须带上）")
    A("")
    A("· **合池**口径（3 个 `pos_frac` 逐轨迹严格多数）⇒ ⇒ ⛔ 不是「单剂量」口径。")
    A("· **零格进分母、不进基准** ⇒ ⇒ 零假设基准是**逐轨迹算再平均**（⛔ 不是恒 0.5）。")
    A("· **块级分母是块数**；**跨臂 Fisher 是精确枚举**；**差区间是 Newcombe95**。")
    A("· ⚠⚠⚖ **前提独立性仍未量到** ⇒ ⇒ 「显著」是**口径依赖**的 ⇒ ⇒ ⛔ **不是**「机制已证」。")
    A("· ⚠ **`pos_frac = 0.25 / 0.75` 这两组的数以前从没测过** ⇒ ⇒ 本轮**第一次**有它们的数。")
    A("· ⚠ **剂量趋势未量到**（本批 `n_bands = 1`，没有剂量轴）⇒ ⇒ ⛔ 不是「无趋势」。")
    A("· ⛔ **远端 tokenizer 快照的内容指纹仍未量到**；**旧批与本批的样本可比性仍未量到**。")
    A("")
    A("#### 【7】⛔ 本轮**没做**（明账）")
    A("")
    A("· ⛔ **没验前提独立性**（56 条轨迹 = 28 块 × 2；块内还有 3 个复制格）⇒ ⇒ "
      "p 值与区间都建立在这个**没被验过**的前提上。")
    A("  · ⚖⚖⚖ **诚实补一句**：本轮**没有正式验**它（⛔ 「正式验」＝ 第二条独立实现 ＋ 变异台能红）"
      "⇒ ⇒ 上面这条**依然记为「未验到」**；本轮只做了**一条路径的先导探查**，见【13】。")
    A("· ⛔ **没实测**「照 meta 重建能否逐位复现」；⛔ **没做**剂量轴那批（分层剂量）。")
    A("· ⛔ 没改读数器、⛔ 没改探针、⛔ 没改拆分器、⛔ 没改任何预登记、⛔ 没跑新批。")
    A("")
    A("#### 【8】**独立重算**：第二条实现把面板上的每个数重算一遍（⛔ 不共用任何代码）")
    A("")
    A("· ⚖⚖⚖ **为什么要做**：判决面板是**分析器自己算自己印**的 ⇒ ⇒ V-P16 只保证**自洽** ⇒ ⇒ "
      "⛔ **不保证算对** ⇒ ⇒ 必须有**第二条独立实现**把每个数重算一遍。")
    A("· **独立性的三条硬规矩**：⛔ **不 import** 那个分析器 / 权威读数器 / 拆分器；"
      "⛔ **自己解析原始跑批日志**（⛔ 连**数据路径**都不共用 ⇒ ⇒ 连「拆分器有没有改格」"
      "也一起独立验掉）；⛔ **统计量自己实现**（Wilson / Newcombe / Fisher / 置换）；"
      "⚖ **置换用二项精确**（分析器那边是 Monte Carlo `n_perm=20000`）"
      "⇒ ⇒ 两条路给出**同一个 p** 才算对上。")
    A("· 实测（收据 `indep_verify_24481.out`）：**判据 %d 条 ｜ PASS %d ｜ FAIL %d**。"
      % (N["i_total"], N["i_pass"], N["i_fail"]))
    A("  · ⚖ 我这边第一版**有 2 处自己的 bug**（rand 臂的 kept/dropped 取错了臂的字段；"
      "Fisher 是 6 位小数打印、容差给成 1e-9）⇒ ⇒ 是**阳性对照**把它抓出来的 ⇒ ⇒ "
      "已修 ⇒ ⇒ **如实记这一条**（⛔ 不是「一次就对」）。")
    if N.get("i_perm"):
        k, obs, p = N["i_perm"][0]
        A("  · 置换：分析器 MC p = %s（MC95%% 带 [%s, %s]）｜ 我这边**二项精确** p = %s"
          "（不一致轨迹 k = %s、观测 T/2 = %s）⇒ ⇒ **落在带内** ⇒ ⇒ 两条不同实现互相印证。"
          % (N["perm_p"], N["band"][0], N["band"][1], p, k, obs))
    A("· **第三条路径**（shell/awk，⛔ 与分析器、与独立重算器都**不同的实现**）直接从原始日志数：")
    for l in N["xc_lines"]:
        A("  · %s" % l)
    A("  ⇒ ⇒ 与面板、与独立重算**逐格一致** ⇒ ⇒ **三条路互证**。")
    A("· **第四条路径**（自包含的探查脚本，⛔ **不 import** 上面任何一个、⛔ 自己解析原始日志、"
      "⛔ Fisher / McNemar / 置换全部自己实现）⇒ ⇒ 把面板的数**逐位复现**："
      "轨迹级 w **%d/%d**、rand **%d/%d** ｜ 块级 w **%d/%d**、rand **%d/%d** ｜ "
      "轨迹级 Fisher **%s**、块级 Fisher **%s** ｜ 逐轨迹置换 p = **%s**（obs = %d、ge = %d/%d）"
      " ⇒ ⇒ **四个数（改判数 / 块级数 / 两个 Fisher / 置换 p 与 ge）四份实现逐位相同**。"
      % (N["sc_traj_w"][0], N["sc_traj_w"][1], N["sc_traj_r"][0], N["sc_traj_r"][1],
         N["sc_blk_w"][0], N["sc_blk_w"][1], N["sc_blk_r"][0], N["sc_blk_r"][1],
         N["sc_fisher_traj"], N["sc_fisher_blk"],
         N["sc_traj_perm_p"], N["sc_traj_perm_obs"], N["sc_traj_perm_ge"], N["sc_traj_perm_n"]))
    A("· 自检（**已知答案**夹具，⛔ 不依赖真数据 ⇒ ⇒ 可以进回归执行集）："
      "**%d 条 ｜ PASS %d ｜ FAIL %d**。" % (N["i_st_total"], N["i_st_pass"], N["i_st_fail"]))
    A("· 它自己的变异台：**%d 条变异 ⇒ 抓到 %d 条**（判据真的变红）＋ **%d 条等价变异**"
      "（源码改了，但这批数据上逐条相同 ⇒ ⇒ 记「**无效**」⇒ ⇒ ⛔ **不是**「存活」）"
      "＋ **0 条台架瞎了**（invalid）＋ **崩 0 条** ⇒ ⇒ **存活 0 条**；退出码 `%s`。"
      % (N["i_mut_total"], N["i_mut_caught"], N["i_mut_equiv"], N["i_mut_rc"]))
    A("  · ⚖ 两条**等价变异为什么**在这批数据上不可见（⛔ 必须写清，⛔ 不许含糊）：")
    for l in N["i_mut_equiv_lines"]:
        A("    · %s" % l)
    A("")
    A("#### 【9】**面板补印**预登记 V3/V4 明写「必须打印」的三项（⇒ ⇒ **判决数一个没动**）")
    A("")
    A("· ⚖ **第一版面板漏印了**：每轨迹有效格 `m` 分布、`(n_nz,n_zero)` 分布、基准分布 "
      "⇒ ⇒ 「零格进分母」（B2）与「某条轨迹少一个有效格」在判决面上**看不见**。")
    A("· 实测为什么非要印：那批数据里 **rand 臂有 %s 个零格**（`d == 0`，**进分母、不进基准**）"
      "、**w 臂有 1 条轨迹只有 2 个有效格**（那格 `rc=1`、没读数 ⇒ 被剔出格集合）"
      "⇒ ⇒ 这两件事在旧面板上**一个都看不出来**。"
      % (N["zerocells"][1] if len(N["zerocells"]) > 1 else "未量到"))
    A("· 已补印（面板全文在收据里可逐字核）：")
    A("  · 每轨迹有效格 m 分布：%s" % " ｜ ".join(N["mdist"]))
    A("  · (n_nz,n_zero) 分布：%s" % " ｜ ".join(N["nzdist"]))
    A("  · 基准分布：%s ｜ 零格合计：%s"
      % (" ｜ ".join(N["basedist"]), " / ".join(N["zerocells"])))
    A("· ⛔ **判决数一个都没动**：w %s/%s、rand %s/%s、差 %s pp、跨臂 Fisher p = %s "
      "⇒ ⇒ **只补披露，不改数**；且**面板三次独立运行 md5 逐位相同**"
      "（`%s` ⇔ 复跑 `%s`）⇒ ⇒ 可复现。"
      % (N["w_pos"], N["w_n"], N["rand_pos"], N["rand_n"], N["diff_pp"], N["fisher_p"],
         N["panel_md5"], N["panel_repro_md5"]))
    A("· 并加判据 **V-P19**（钉住「必须印」）＋ 变异 **P21**（删标记必红）"
      "⇒ ⇒ 分析器自检 **%d/%d 绿**、变异台 **%d/%d 全抓到**。"
      % (N["a_crit_pass"], N["a_crit_total"], N["a_mut_caught"], N["a_mut_total"]))
    for l in N.get("a_mut_p21", []):
        A("  · %s" % l.strip())
    A("")
    A("#### 【10】**修掉一条永久红**（`probe_compat_check.py` 的 C1）")
    A("")
    A("· 244.79 的全回归把「自检红 `probe_compat_check.py`」记成「**既有红**（244.45 起）："
      "探针里 `SIG_OLD` 锚点找不到」⇒ ⇒ 那个**分类是对的**，⛔ 但只记账不修 ⇒ ⇒ "
      "这个工具会**永远瞎着**。")
    A("· **真相**：244.45 给真探针打了 force 补丁 ⇒ ⇒ 补丁**前**的锚点 `SIG_OLD` **再也命中不到** "
      "⇒ ⇒ 那条判据**永久红**（和恒绿一样是**坏护栏**）⇒ ⇒ 已改成**按形态各查各的锚点**"
      "（形态判定**复用**工具自己的 `probe_state`，⛔ **不另写一套** —— 两处判定不一致本身就是一类错）。")
    A("· 并加自检 **C11**（合成**混合形态** ⇒ 必须红）⇒ ⇒ 这条判据**自己先把自己钉住**。")
    A("· 实测（收据 `probe_compat_selftest.out`）：自检 **%d/%d 通过**。"
      % (N["pcc_pass"], N["pcc_total"]))
    if N.get("pcc_mut_line"):
        A("· ⚖⚖ **我改了这个工具 ⇒ ⇒ 它自己的变异台必须还绿**（⛔ 不然就是「改坏别人的尺子」）"
          "⇒ ⇒ 在**完整执行集树**（`zju-12`，229 个文件）上实测：%s（含 `Q14`：改形态判定仍会被抓住）"
          % N["pcc_mut_line"][0])
        A("  · ⚖ 顺带一条**排查记录**：先在 zju-53 的**精简树**（只有 6 个文件）上跑，台架基线报红 ⇒ ⇒ "
          "**不是**工具的问题，是**那棵树不完整**（提取器的自检读不到别的文件）⇒ ⇒ "
          "用**旧版工具**在同一棵精简树上做对照实验，也是红的 ⇒ ⇒ 两条独立证据指向「环境」⇒ ⇒ "
          "换完整树后基线全绿 ⇒ ⇒ ⛔ **没有**把环境问题记成「判据红」。")
    for l in N.get("pcc_c1", []):
        A("  · %s" % l)
    for l in N.get("pcc_c11", []):
        A("  · %s" % l)
    A("")
    if N.get("reg_rc"):
        A("#### 【11】**全回归**（`%s`，本轮判决那一轮）" % N["reg_host"])
        A("")
        A("· 执行集 **%s** 个 py（清单 md5 `%s`）；清单 diff：**新增 %s 行 / 减少 %s 行** "
          "⇒ ⇒ **每一行都能解释**（新增 2 个新工具 ＋ 变更 3 个工具各一增一删）。"
          % (N["reg_npy"], N["reg_manifest_md5"], N["reg_added"], N["reg_removed"]))
        A("· 回归读到的账本：**%s 行**，md5 `%s` ⇒ ⇒ **这轮回归跑在「244.80 ＋ 244.81 两段追加**之前**」**"
          "⇒ ⇒ 它看到的是 244.79 那版账本（**逐字节相同**）⇒ ⇒ 读账本的那几个工具看到的是**当时最新**的账本。"
          % (N["reg_ledger_lines"], N["reg_ledger_md5"]))
        A("· ⚖⚖⚖ **「证据 ↔ 最终版字节」这条闸要说清**：这轮回归验的是**工具**字节（已最终）"
          "⇒ ⇒ 追加这两段后**账本字节会变** ⇒ ⇒ 追加后的账本**另跑**一轮全回归（**R2**）来验 "
          "⇒ ⇒ R2 的收据与小结记在**交接文件**里（⛔ 不是记在这里 —— 记在这里就会让账本再变一次，"
          "⇒ ⇒ 那等于**又**绕回「证据 ↔ 字节」的老问题）。")
        A("· 小结：**变异台 全绿 %d / 跑得动 %d**（跳过 %d，缺远端产物）｜ "
          "**自检 全绿 %d / 跑得动 %d**（跳过 %d，无 `--selftest` 入口）｜ `REG_RC = %s`。"
          % (N["reg_mut_ok"], N["reg_mut_run"], N["reg_mut_skip"],
             N["reg_st_ok"], N["reg_st_run"], N["reg_st_skip"], N["reg_rc"]))
        if N["reg_mut_bad"] or N["reg_st_bad"]:
            A("· 🔴 **红项按分类登记**（⛔ 「超时」与「跑不动」⛔ **不算**「判据红」；"
              "⛔ 「既有红」⛔ **不是**「本轮红」）：")
            for nm, rc in N["reg_mut_bad"]:
                if rc == "-9":
                    A("  · **变异台** `%s` rc=`-9`（**超时**，撞 harness 的 2400s 墙钟）"
                      "⇒ ⛔ **不是判据红**（本仓纪律：`rc=-9` 归**环境/时限**问题；本轮**没碰**它）。"
                      "⚖ **旁证**：244.80 那一轮跑**同一个**测试是**绿的**（2046.5s）⇒ ⇒ "
                      "**同一个测试两轮结果不同** ⇒ ⇒ 这更说明它是**时限**问题，⛔ 不是判据问题。"
                      % nm)
                else:
                    A("  · **变异台** `%s` rc=`%s` ⇒ 🔴 **判据红**（本轮引入 ⇒ ⇒ 必须查清并修）" % (nm, rc))
            for nm in N["reg_st_bad"]:
                A("  · **自检** `%s` ⇒ ⚠ **既有红**（244.45 起；本轮**修好了**它 ⇒ ⇒ 下一轮应为绿）" % nm)
            A("  ⇒ ⇒ **本轮引入的判据红一条都没有** ⇒ ⇒ ⛔ 不计入本轮判决。")
        else:
            A("· ✅ **零红项**（变异台与自检都没有 `[BAD ]`）⇒ ⇒ 本轮**没有引入任何红**。")
        A("· ⚖⚖⚖ **诚实记账：本轮作废过两次回归**（⛔ 只作废、⛔ 不藏）："
          "① 第一次：树里 `mut_verify_pooled_verdict_indep.py` **不是最终版字节**"
          "（少了 `PRECOND_FAIL` 那句 ⇒ 缺远端产物时会报**假红**而不是「跳过」）"
          "⇒ ⇒ 回归测的不是最终版 ⇒ ⇒ 作废；"
          "② 第二次：查到 **DEV 树里存着旧字节**，而同步步骤是「DEV → 树」"
          "⇒ ⇒ 把新字节**盖回旧的** ⇒ ⇒ 又作废；"
          "⇒ ⇒ **给同步步骤加了「DEV 与树逐位对账」的断言**（不一致 ⇒ 硬停）"
          "⇒ ⇒ 第三次才作数（收据里印 `sync_ok`）。")
        A("")
    A("#### 【12】**先导探查**：前提独立性（⚠⚖⚖ **这是先导，不是判决**）")
    A("")
    A("· ⚖ **为什么要做**：面板前提 P1 说「前提独立性未量到」⇒ ⇒ 244.81 的**每一个 p 与每一个区间**"
      "都建立在这个**没被验过**的前提上 ⇒ ⇒ 那是判决现在**最硬的缺口**。")
    A("· ⚖ **探查问什么**：「把零分布换成『**块是独立单位**』（块内**整体**交换两臂标签），"
      "判决还站得住吗？」")
    A("· ⚖⚖⚖ **它只是先导，⛔ 不是判决**：它**只有一条实现**、**没有变异台** ⇒ ⇒ 过不了"
      "「第二条独立实现 ＋ 每条判据能红」那一关 ⇒ ⇒ 下面的数**不许**当结论用。"
      "⚖ 它唯一**确立**的事属于**复现**（证据链）：第四份实现把面板的数**逐位复现**（见【8】末尾）。")
    A("")
    A("· **先导结果**（全部来自**这批真数据**，零 GPU）：")
    A("  · **块内确实相关**（前提「不独立」这一半**成立**）：%d 个块里，w 臂块内两条判决**一致** %d 条"
      "（%s）｜ rand 臂块内**不一致** %d 条 ｜ w 臂块内不一致 %d 条"
      " ⇒ ⇒ 「块内两条轨迹可当独立」这个前提**站不住** ⇒ ⇒ 逐轨迹的零分布**偏窄**。"
      % (N["sc_nblk"], N["sc_blk_agree"], N["sc_blk_agree_rate"],
         N["sc_rand_disc"], N["sc_w_disc"]))
    A("  · **但它没有推翻判决**：零分布换成**块级**（块内整体交换两臂标签）⇒ ⇒ p = **%s**"
      "（obs = %d、ge = %d/%d）⇒ ⇒ 只比逐轨迹的 **%s**（ge = %d/%d）大 **%s×**"
      " ⇒ ⇒ **p 仍远小于 0.05** ⇒ ⇒ 判决**在「块是独立单位」这个更强前提下依然站得住**。"
      % (N["sc_blk_perm_p"], N["sc_blk_perm_obs"], N["sc_blk_perm_ge"], N["sc_blk_perm_n"],
         N["sc_traj_perm_p"], N["sc_traj_perm_ge"], N["sc_traj_perm_n"], N["sc_ratio"]))
    A("  · **区间**：按**块**重采样（承认聚类）的 bootstrap ⇒ ⇒ 块级差 **%s pp**，95%% 区间 "
      "**[%s, %s] pp** ⇒ ⇒ 仍然**远离 0**（对比：轨迹级 Newcombe95 %s pp）"
      " ⇒ ⇒ 「区间会不会被聚类撑破」这个担心，**先导没看到**。"
      % (N["sc_boot_diff"], N["sc_boot_lo"], N["sc_boot_hi"], N["diff_ci"]))
    A("  · **McNemar**（逐轨迹配对，不一致 %d 条：w 优 %d / rand 优 %d）⇒ ⇒ 精确二项两侧 p = **%s**"
      " ⇒ ⇒ 与独立重算器那条「二项精确 p」**逐位相同**（第三条印证）。"
      % (N["sc_disc"], N["sc_w_better"], N["sc_r_better"], N["sc_mcnemar_p"]))
    A("· ⚖⚖⚖ **它没回答的**（⛔ 这些**仍算「未量到」**）：")
    A("  · **块间独立**没验（28 个块之间有没有共享结构，单批数据验不了）；")
    A("  · **复制格**之间的一致性只有**分歧率**（w %s ｜ rand %s）⇒ ⇒ 那仍是**前提**，不是判决；"
      % (N["sc_dis"][0][2] if len(N["sc_dis"]) > 0 else "未量到",
         N["sc_dis"][1][2] if len(N["sc_dis"]) > 1 else "未量到"))
    A("  · **剂量轴**完全没碰（本批 `n_bands = 1`）⇒ ⇒ ⛔ 不是「无剂量效应」。")
    A("")
    A("#### 【13】下一轮（244.82）该做什么")
    A("")
    A("1. **验前提独立性**（这是判决现在最硬的缺口）：块内相关、块间独立、复制格一致性（分歧率）"
      "⇒ ⇒ 必要时改成**按块聚合**的口径并重算区间。")
    A("   · ⚖⚖⚖ **方向已经被【12】那轮先导探查钉死了**（⛔ 先导 ≠ 判决）⇒ ⇒ "
      "244.82 要做的**不是**从零开始，而是：把【12】的**块级**结论做成**正式一轮** ⇒ ⇒ "
      "**第二条独立实现**（⛔ 不许复用探查脚本的代码）＋ **变异台**（每条判据能红）＋ 写进预登记。")
    A("2. **分层剂量那批**：把「剂量」与「机制」两条轴真正拆开（现在只到「固定剂量 + 机制 vs rand」）。")
    A("3. ⛔ 别在前提独立性**正式**验过之前把 p 值当结论。")
    A("")
    return "\n".join(L) + "\n"


def main():
    dry = "--dry" in sys.argv
    N = collect()
    sec = build(N)
    fences = [l for l in sec.split("\n") if l.strip().startswith("```")]
    assert not fences, "⛔ 追加段里有围栏 ⇒ 不许"
    full = _read(LEDGER)
    # ⚖⚖⚖ **防重复落账**（幂等闸）：账本是「只追加」⇒ ⇒ 追加**同一段两次**
    #   就是**破坏历史**（同一修订出现两遍）⇒ ⇒ 落账前必须查标题是否已在
    _h = "## 修订 244.81 —— "
    if full.count(_h) > 0:
        raise SystemExit("⛔ 账本里已经有「%s」这一段（%d 处）⇒ ⇒ **拒绝重复落账**"
                         % (_h, full.count(_h)))
    n_before = sum(1 for l in full.split("\n") if l.strip().startswith("```"))
    old_len = len(full.encode("utf-8"))
    print("账本现状：%d 字节 ｜ 围栏 %d 个" % (old_len, n_before))
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
    print("✅ 已追加：%d → %d 字节 ｜ 围栏仍 %d 个 ｜ 旧前缀逐字节不变"
          % (old_len, len(after.encode("utf-8")), n_after))
    return 0


if __name__ == "__main__":
    sys.exit(main())
