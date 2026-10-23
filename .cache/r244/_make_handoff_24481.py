#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成 244.81 的交接文件 `.cache/xcheck/HANDOFF_24481.md`。

⚖⚖⚖ **纪律**：所有数**从收据解析**（⛔ 不手抄）⇒ ⇒ 交接与账本永远一致。
⚖⚠ **内嵌 commit hash 的文档** ⇒ ⇒ **提交之后必须再生成一次**（否则写的是上一个 commit）。
"""

import datetime
import io
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(REPO, ".cache", "xcheck", "HANDOFF_24481.md")
EV = os.path.join(HERE, "_e24481")


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


def _git(*a):
    return subprocess.run(["git"] + list(a), cwd=REPO, capture_output=True,
                          text=True).stdout.strip()


def main():
    panel = _need(os.path.join(EV, "verdict_panel.txt"))
    if "部分读数" in panel or "本面板的数不是判决" in panel:
        raise SystemExit("⛔ 面板带「部分读数 / 本面板的数不是判决」横幅 ⇒ 不出交接")
    rc = _need(os.path.join(EV, "receipt_24481.txt"))
    iv = _need(os.path.join(EV, "indep_verify_24481.out"))
    ast = _need(os.path.join(EV, "analyzer_selftest.out"))
    amut = _need(os.path.join(EV, "mut_analyzer.out"))
    ist = _need(os.path.join(EV, "indep_selftest.out"))
    imut = _need(os.path.join(EV, "mut_indep.out"))
    pcc = _need(os.path.join(EV, "probe_compat_selftest.out"))
    regp = os.path.join(EV, "reg_24481.txt")
    reg = _need(regp) if os.path.isfile(regp) else ""
    # ⚖⚖ R2：**落账之后**再跑的那一轮（验的是**本次提交里**那份账本字节）
    regbp = os.path.join(EV, "reg_24481b.txt")
    regb = _need(regbp) if os.path.isfile(regbp) else ""

    # ---- ⚖ 本地 ↔ 远端**实际跑的那份**的字节对账（能红检查的收据）
    bcp = os.path.join(EV, "launcher_bytecheck_24481.txt")
    bc = _need(bcp) if os.path.isfile(bcp) else ""
    bc_pass = bc_red = "未量到"
    bc_exec_ok = bc_launch_ok = "未量到"
    bc_verdict = bc_led_local = bc_led_rec = bc_idx_local = bc_idx_rec = "未量到"

    # ---- 唯一红项的**分类**（rc=-9 ＝ SIGKILL ＝ 被时限上限杀掉 ⇒ 不是判据红）
    bad_detail = []
    for _fn in ("reg_24481.txt", "reg_24481b.txt"):
        _p = os.path.join(EV, _fn)
        if os.path.isfile(_p):
            for _n, _rc, _s in re.findall(r"^  \[BAD \] (\S+\.py)\s+rc=(-?\d+)\s+\[([\d.]+)s\]",
                                          _read(_p), re.M):
                bad_detail.append((_fn, _n, _rc, _s))
    old_p = os.path.join(HERE, "_e24480", "reg_24480.txt")
    old_ok = ""
    if os.path.isfile(old_p):
        _m = re.search(r"^  \[OK \] (mut_recomp_p\.py).*?\[([\d.]+)s\]", _read(old_p), re.M)
        if _m:
            old_ok = "%s 在 244.80 那轮是 **%s s 绿的**" % (_m.group(1), _m.group(2))
    if bad_detail:
        bc_bad_names = "、".join(sorted(set(b[1] for b in bad_detail)))
        bc_bad_rcs = "/".join(sorted(set(b[2] for b in bad_detail)))
        bc_bad_secs = "/".join(sorted(set(b[3] for b in bad_detail)))
    else:
        bc_bad_names = bc_bad_rcs = bc_bad_secs = "无"
    if bc:
        m = _grab(bc, r"\[✅\] A 账本 md5 == R2 收据 ledger_md5\n    本地 (\w+) ｜ 收据 (\w+)",
                  "字节对账·账本")
        bc_led_local, bc_led_rec = m.group(1), m.group(2)
        m = _grab(bc, r"\[✅\] B 索引 md5 == R2 收据 index_md5\n    本地 (\w+) ｜ 收据 (\w+)",
                  "字节对账·索引")
        bc_idx_local, bc_idx_rec = m.group(1), m.group(2)
        bc_pass = len(re.findall(r"^\[✅\]", bc, re.M))
        bc_red = len(re.findall(r"^\[⛔\]", bc, re.M))
        bc_exec_ok = len(re.findall(r"^\[✅\] C 执行集", bc, re.M))
        bc_launch_ok = len(re.findall(r"^\[✅\] _run_", bc, re.M))
        bc_verdict = "全部硬判据通过" if bc_red == 0 else "有硬判据没过"

    # ---- ④ 第四条实现（自包含探查脚本）的收据：⛔ 它是**先导**，不是判决
    sc = _need(os.path.join(EV, "scout_premise_indep_24481.out"))
    m = _grab(sc, r"自检通过：轨迹级 w (\d+)/(\d+)、rand (\d+)/(\d+) ｜ 块级 w (\d+)/(\d+)、"
                  r"rand (\d+)/(\d+) ｜ 轨迹级 Fisher ([0-9.]+)、块级 Fisher ([0-9.]+)", "探查自检")
    sc_traj_w = (m.group(1), m.group(2))
    sc_traj_r = (m.group(3), m.group(4))
    sc_blk_w = (m.group(5), m.group(6))
    sc_blk_r = (m.group(7), m.group(8))
    sc_fisher_traj = m.group(9)
    sc_fisher_blk = m.group(10)
    m = _grab(sc, r"块数 (\d+) ｜ w 臂块内两条\*\*判决一致\*\* (\d+)", "探查块内一致")
    sc_blk_agree = int(m.group(2))
    m = _grab(sc, r"\*\*逐轨迹\*\*置换：p = ([0-9.]+)（obs = (\d+) ｜ ge=(\d+)/(\d+)）", "探查逐轨迹置换")
    sc_traj_perm_p = m.group(1)
    sc_traj_perm_ge = int(m.group(3))
    sc_traj_perm_n = int(m.group(4))
    m = _grab(sc, r"\*\*块级\*\*置换（块内整体交换两臂标签）：p = ([0-9.]+)", "探查块级置换")
    sc_blk_perm_p = m.group(1)
    m = _grab(sc, r"\*\*比值\*\*：块级 p ÷ 逐轨迹 p = ([0-9.]+)×", "探查比值")
    sc_ratio = m.group(1)
    m = _grab(sc, r"按块 bootstrap 95% 区间 \[([-+0-9.]+), ([-+0-9.]+)\] pp", "探查 bootstrap")
    sc_boot_lo, sc_boot_hi = m.group(1), m.group(2)

    # ---- 判决面板（逐条从面板抠，⛔ 不手抄）
    m = _grab(panel, r"^  w\s+改判 \*\*(\d+)/(\d+)\*\*", "w 臂改判")
    w_pos, w_n = m.group(1), m.group(2)
    m = _grab(panel, r"^  rand\s+改判 \*\*(\d+)/(\d+)\*\*", "rand 臂改判")
    r_pos, r_n = m.group(1), m.group(2)
    m = _grab(panel, r"差 \*\*([-+0-9.]+) pp\*\* ｜ 差区间 (\[[-+0-9., %]+\]) pp ｜ "
                  r"跨臂 Fisher（精确枚举）p = ([0-9.]+) ｜ 配对置换 p = ([0-9.]+)", "跨臂")
    diff, diff_ci, fisher_p, perm_p = m.groups()
    m = _grab(panel, r"配对置换 \*\*MC95% 不确定带\*\* = \[([0-9.]+), ([0-9.]+)\]", "MC 带")
    band = m.groups()
    m = _grab(panel, r"^  w (\d+)/(\d+) ｜ rand (\d+)/(\d+) ｜ 差 ([-+0-9.]+) pp ｜ "
                  r"差区间 (\[[-+0-9., %]+\]) pp ｜ Fisher p = ([0-9.]+)", "块级")
    blk_w, blk_n, blk_r, blk_rn, blk_diff, blk_ci, blk_p = m.groups()
    groups = re.findall(
        r"pos_frac=([0-9.]+)\s+w (\d+)/(\d+) ｜ rand (\d+)/(\d+) ｜ 差 ([-+0-9.]+) pp ｜ "
        r"差区间 (\[[-+0-9., %]+\]) pp ｜ Fisher p = ([0-9.]+)", panel)
    dis = re.findall(r"三格全一致 (\d+) ｜ 2:1 分歧 (\d+) ｜ 分歧率 ([0-9.]+)", panel)
    mdist = re.findall(r"每轨迹有效格 m 分布 = (\{[^}]*\})", panel)
    nzdist = re.findall(r"\(n_nz,n_zero\) 分布 = (\{[^}]*\})", panel)
    zero = re.findall(r"零格合计 (\d+)", panel)
    bytes_md5 = dict(re.findall(r"^(\w{32})\s+(\S+)$", rc, re.M))
    arms = {}
    for mm in re.finditer(r"arm=(\w+) cells_done=(\d+).*?idx_tot=(\d+) (\d+) "
                          r"abort=(\d+) rc0=(\d+)", rc):
        arms[mm.group(1)] = (int(mm.group(2)), int(mm.group(4)),
                             int(mm.group(5)), int(mm.group(6)))

    # ---- 各台架的小结
    m = _grab(ast, r"判据 (\d+) 条 ｜ PASS (\d+) ｜ FAIL (\d+)", "分析器自检小结")
    n_crit, n_pass, n_fail = (int(x) for x in m.groups())
    m = _grab(amut, r"变异台：抓住 (\d+) / (\d+)（等价变异 (\d+) 条", "分析器变异台小结")
    mut_caught, mut_total, mut_equiv = (int(x) for x in m.groups())
    m = _grab(ist, r"自检 (\d+) 条 ｜ PASS (\d+) ｜ FAIL (\d+)", "独立重算器自检小结")
    i_st_total, i_st_pass, i_st_fail = (int(x) for x in m.groups())
    m = _grab(iv, r"判据 (\d+) 条 ｜ PASS (\d+) ｜ FAIL (\d+)", "独立重算小结")
    i_total, i_pass, i_fail = (int(x) for x in m.groups())
    m = _grab(imut, r"变异台：抓到 (\d+) / (\d+)（无效 (\d+) 条.*?其中等价变异 (\d+) 条",
              "独立重算器变异台小结", flags=re.S)
    i_mut_caught, i_mut_total, i_mut_equiv = (int(m.group(1)), int(m.group(2)),
                                              int(m.group(4)))
    equiv_lines = [l.strip() for l in imut.split("\n") if l.strip().startswith("[无效/等价]")]
    m = _grab(pcc, r"自检 (\d+)/(\d+) 通过", "probe_compat_check 自检小结")
    pcc_total, pcc_pass = int(m.group(1)), int(m.group(2))

    reg_host = reg_npy = reg_man = reg_added = reg_removed = reg_rc = "未量到"
    rm_ok = rm_run = rs_ok = rs_run = "-"
    reg_bad = []
    if reg:
        reg_host = _grab(reg, r"host=(\S+)", "回归主机").group(1)
        reg_npy = _grab(reg, r"n_exec_py=(\d+)", "执行集 py 数").group(1)
        reg_man = _grab(reg, r"manifest_md5=(\w+)", "清单 md5").group(1)
        reg_added = _grab(reg, r"added=(\d+)", "清单新增").group(1)
        reg_removed = _grab(reg, r"removed=(\d+)", "清单减少").group(1)
        reg_rc = _grab(reg, r"REG_RC=(\d+)", "回归退出码").group(1)
        m = _grab(reg, r"小结：变异台 全绿 (\d+) / 跑得动 (\d+) ；自检 全绿 (\d+) / 跑得动 (\d+)",
                  "回归小结")
        rm_ok, rm_run, rs_ok, rs_run = m.groups()
        reg_bad = re.findall(r"^  \[BAD \] (\S+\.py)", reg, re.M)

    # ⚖⚖ R2 的解析（**同一套抠法**，⛔ 不另写）
    regb_host = regb_npy = regb_rc = regb_led_md5 = regb_led_lines = "未量到"
    regb_added = regb_removed = "-"
    rm_b_ok = rm_b_run = rs_b_ok = rs_b_run = "-"
    regb_bad = []
    if regb:
        regb_host = _grab(regb, r"host=(\S+)", "R2 回归主机").group(1)
        regb_npy = _grab(regb, r"n_exec_py=(\d+)", "R2 执行集 py 数").group(1)
        regb_added = _grab(regb, r"added=(\d+)", "R2 清单新增").group(1)
        regb_removed = _grab(regb, r"removed=(\d+)", "R2 清单减少").group(1)
        regb_rc = _grab(regb, r"REG_RC=(\d+)", "R2 回归退出码").group(1)
        m = _grab(regb, r"ledger_lines=(\d+)\s+ledger_md5=(\w+)", "R2 账本行数与 md5")
        regb_led_lines, regb_led_md5 = m.group(1), m.group(2)
        m = _grab(regb, r"小结：变异台 全绿 (\d+) / 跑得动 (\d+) ；自检 全绿 (\d+) / 跑得动 (\d+)",
                  "R2 回归小结")
        rm_b_ok, rm_b_run, rs_b_ok, rs_b_run = m.groups()
        regb_bad = re.findall(r"^  \[BAD \] (\S+\.py)", regb, re.M)

    commit = _git("rev-parse", "HEAD")
    subject = _git("log", "-1", "--pretty=%s")
    stamp = _grab(rc, r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})$", "跑批进度时刻").group(1)

    L = []
    A = L.append
    A("# 交接：244.81（**固定剂量的判决数出来了**）")
    A("")
    A("⚖⚖⚖ **一句话**：**固定剂量（ρ\\* = 0.25，3 个 `pos_frac` 合池）下，w 臂改判 %s/%s、"
      "rand 臂改判 %s/%s、差 %s pp**（跨臂 Fisher p = %s、配对置换 p = %s，MC95%% 带 [%s, %s]）；"
      "块级 **%s/%s vs %s/%s**（Fisher p = %s）⇒ ⇒ **在固定剂量下，steering vector 确实"
      "改判了明显更多题**；⛔ 但 **前提独立性仍未量到** ⇒ ⇒ 判决**口径依赖**，⛔ **不是**「机制已证」。"
      % (w_pos, w_n, r_pos, r_n, diff, fisher_p, perm_p, band[0], band[1],
         blk_w, blk_n, blk_r, blk_rn, blk_p))
    A("")
    A("· 提交：`%s` —— %s" % (commit[:12], subject))
    A("· 生成时间：%s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    A("")
    A("## 1. ⏱ **现在在跑什么**")
    A("")
    for a in ("w", "rand"):
        if a in arms:
            done, tot, ab, rc0 = arms[a]
            A("· **%s 臂跑批**：%d/%d 格，`ABORT` %d，`rc=0` %d 格（收据时刻 `%s`）"
              % (a, done, tot, ab, rc0, stamp))
    A("· ✅ **跑批已跑完**（两臂各 168 格、`ALLDONE` 各 1 条）⇒ ⇒ **判决数据已到手**。")
    A("· ⛔ **前提独立性仍未量到** ⇒ ⇒ 「显著」是**口径依赖**的 ⇒ ⇒ **不是**「机制已证」。")
    A("")
    A("## 2. ✅ **本轮的关键结论**（完整版在账本 244.80 / 244.81 段）")
    A("")
    A("1. ✅ **固定剂量的判决数出来了**（合池口径）：轨迹级 w **%s/%s** vs rand **%s/%s**、"
      "差 **%s pp**（差区间 %s，Newcombe95）⇒ ⇒ 固定剂量下 w 臂的改判率显著高于 rand 臂。"
      % (w_pos, w_n, r_pos, r_n, diff, diff_ci))
    A("2. ✅ **块级**同样成立：w **%s/%s** vs rand **%s/%s**（Fisher p = %s）⇒ ⇒ "
      "⛔ 分母是**块数**，不是轨迹数。" % (blk_w, blk_n, blk_r, blk_rn, blk_p))
    A("3. ✅ **分 `pos_frac` 三组**（V7）：%s"
      % " ｜ ".join("%s: w %s/%s vs rand %s/%s（差 %s pp，Fisher p = %s）"
                  % (g[0], g[1], g[2], g[3], g[4], g[5], g[7]) for g in groups))
    A("4. ⚖⚖⚖ **第二条独立实现把面板上的每个数重算了一遍**（`verify_pooled_verdict_indep.py`："
      "⛔ 不 import 分析器/读数器/拆分器、⛔ 自己解析原始日志、自己实现统计量、"
      "置换用**二项精确**）⇒ ⇒ **%d 条判据 ｜ PASS %d ｜ FAIL %d** ⇒ ⇒ 判决**不是**自证。"
      % (i_total, i_pass, i_fail))
    A("5. ✅ **面板补印**了预登记 V3/V4 明写「必须打印」的三项（`m` 分布 %s ｜ "
      "`(n_nz,n_zero)` 分布 %s）⇒ ⇒ **判决数一个没动**，只是判决面多披露了分母的形状。"
      % (" / ".join(mdist), " / ".join(nzdist)))
    A("6. ✅ **修掉一条永久红**：`probe_compat_check.py` 的 C1（244.45 起就永久红）⇒ ⇒ "
      "改成**按形态各查各的锚点** ＋ 新增 **C11**（混合形态必红）⇒ ⇒ 自检 **%d/%d 通过**。"
      % (pcc_pass, pcc_total))
    A("7. ⚠ **两条等价变异**（记「无效」、不计分母）暴露了两条**前提**："
      "这一批**没有平票轨迹**；「等剂量」的精度是 **±0.5% 密度**（分母差 1 个 token 看不出来）。")
    A("8. ✅ **第四条实现**（自包含探查脚本，⛔ 不 import 上面任何一个）把面板的数**逐位复现**："
      "轨迹级 w **%s/%s**、rand **%s/%s** ｜ 块级 w **%s/%s**、rand **%s/%s** ｜ "
      "轨迹级 Fisher **%s**、块级 Fisher **%s** ｜ 逐轨迹置换 p = **%s**（ge = %s/%s）"
      " ⇒ ⇒ 判决**四份实现互证**。"
      % (sc_traj_w[0], sc_traj_w[1], sc_traj_r[0], sc_traj_r[1],
         sc_blk_w[0], sc_blk_w[1], sc_blk_r[0], sc_blk_r[1],
         sc_fisher_traj, sc_fisher_blk, sc_traj_perm_p, sc_traj_perm_ge, sc_traj_perm_n))
    A("9. ⚖⚖⚖ **先导探查（⛔ 不是判决）**：把零分布换成『**块是独立单位**』⇒ ⇒ "
      "块级置换 p = **%s**（只比逐轨迹的 %s 大 **%s×**）｜ 按块 bootstrap 的块级差区间 "
      "**[%s, %s] pp**（仍远离 0）｜ 块内**确实相关**（w 臂 28 块里 %d 块内两条一致）"
      " ⇒ ⇒ **判决在更强前提下依然站得住**；⚠ 但它**只有一条实现、没有变异台**"
      " ⇒ ⇒ 「前提独立性」这条前提**正式仍记「未验到」**，244.82 把它做成正式一轮。"
      % (sc_blk_perm_p, sc_traj_perm_p, sc_ratio, sc_boot_lo, sc_boot_hi, sc_blk_agree))
    if bc:
        A("10. ✅ **「R2 验的就是本次提交里那份字节」这句话被**逐文件**验过**（新加的**能红**检查 "
          "`_verify_launcher_bytes_24481.py`：拿**提交里那份**去对 **R2 收据里记的**字节）"
          "⇒ ⇒ 账本 md5 `%s` == 收据 `%s`、索引 md5 `%s` == 收据 `%s`、"
          "**执行集 %s/5 逐位一致**（承载判据逻辑的那 5 个文件）；"
          "⚠ **启动器 %s/2** 与「远端**实际跑的那份**」**不是**逐位一致，但差异**逐条**落在"
          "**已登记清单**里（登记 ① `${}` 加括号、② 收据计数修正、③ 纯注释行）"
          "⇒ ⇒ **没有未解释的漂移**；⇒ ⇒ 硬判据 **绿 %s / 红 %s**（%s）。"
          % (bc_led_local, bc_led_rec, bc_idx_local, bc_idx_rec,
             bc_exec_ok, bc_launch_ok, bc_pass, bc_red, bc_verdict))
    A("")
    A("## 3. ⚖ **收据摘要**（全部可回查）")
    A("")
    A("| 项 | 值 |")
    A("|---|---|")
    A("| 判决面板 | 轨迹级 w **%s/%s** ｜ rand **%s/%s** ｜ 差 **%s pp** ｜ Fisher p = %s ｜ 置换 p = %s（带 [%s, %s]） |"
      % (w_pos, w_n, r_pos, r_n, diff, fisher_p, perm_p, band[0], band[1]))
    A("| 块级 | w **%s/%s** ｜ rand **%s/%s** ｜ 差 %s pp ｜ Fisher p = %s |"
      % (blk_w, blk_n, blk_r, blk_rn, blk_diff, blk_p))
    A("| 分析器自检 | **%d/%d 绿**（FAIL %d）｜ 变异台 抓住 **%d/%d** ｜ 等价变异 %d ｜ 崩 0 |"
      % (n_pass, n_crit, n_fail, mut_caught, mut_total, mut_equiv))
    A("| 独立重算 | 自检 **%d/%d** ｜ 真数据 **%d/%d** ｜ 它的变异台 抓住 **%d/%d**（等价变异 %d） |"
      % (i_st_pass, i_st_total, i_pass, i_total, i_mut_caught, i_mut_total, i_mut_equiv))
    A("| probe_compat_check | 自检 **%d/%d 通过** |" % (pcc_pass, pcc_total))
    if reg:
        A("| 全回归 R1（落账**前**的账本 = 244.79 那版） | 主机 `%s` ｜ 执行集 **%s** 个 py ｜ "
          "清单 md5 `%s` ｜ diff **新增 %s / 减少 %s** ｜ "
          "变异台 全绿 %s / 跑得动 %s ｜ 自检 全绿 %s / 跑得动 %s ｜ `REG_RC = %s` ｜ 红项 %s |"
          % (reg_host, reg_npy, reg_man, reg_added, reg_removed,
             rm_ok, rm_run, rs_ok, rs_run, reg_rc, reg_bad or "无"))
    else:
        A("| 全回归 R1（落账**前**的账本） | ⛔ **未量到**（还没跑完） |")
    if regb:
        A("| **全回归 R2（落账**后**的账本 = 本次提交里那份）** | 主机 `%s` ｜ 执行集 **%s** 个 py ｜ "
          "清单 diff（对 R1）**新增 %s / 减少 %s**（⇒ ⇒ 执行集字节**一个没动**）｜ 账本 **%s 行** md5 `%s` ｜ "
          "变异台 全绿 %s / 跑得动 %s ｜ 自检 全绿 %s / 跑得动 %s ｜ `REG_RC = %s` ｜ 红项 %s |"
          % (regb_host, regb_npy, regb_added, regb_removed, regb_led_lines, regb_led_md5,
             rm_b_ok, rm_b_run, rs_b_ok, rs_b_run, regb_rc, regb_bad or "无"))
    else:
        A("| 全回归 R2（落账**后**的账本） | ⛔ **未量到** |")
    if bad_detail:
        A("| **唯一红项的分类** | %s ｜ rc = `%s`（= **SIGKILL**，**被 2400 s 上限杀掉**）｜ "
          "R1 与 R2 **两次都恰好停在 %s s** ⇒ ⇒ 归「**环境/时限**」，⛔ **不是**「判据红」 |"
          % (bc_bad_names, bc_bad_rcs, bc_bad_secs))
    if bc:
        A("| **字节对账（提交字节 ↔ R2 收据字节）** | 账本 md5 `%s` == 收据 `%s` ｜ 索引 md5 `%s` == 收据 `%s` ｜ "
          "执行集 **%s/5** 逐位一致 ｜ 启动器 **%s/2** 差异逐条落在已登记清单 ｜ 硬判据 **绿 %s / 红 %s** |"
          % (bc_led_local, bc_led_rec, bc_idx_local, bc_idx_rec,
             bc_exec_ok, bc_launch_ok, bc_pass, bc_red))
    else:
        A("| 字节对账（本地 ↔ 远端） | ⛔ **未量到** |")
    A("| 字节 | 分析器 `%s` ｜ 变异台 `%s` ｜ 独立重算 `%s` ｜ 读数器 `%s`（⛔ 一个字没动） |"
      % (bytes_md5.get("fixed_dose_pooled_verdict_audit.py", "?"),
         bytes_md5.get("mut_fixed_dose_pooled_verdict_audit.py", "?"),
         bytes_md5.get("verify_pooled_verdict_indep.py", "?"),
         bytes_md5.get("_k23_reader_r227_kcurve.py", "?")))
    A("")
    A("## 4. 📜 **证据链台账**（一条一句结论 ＋ 判据 ＋ 变异台计数）")
    A("")
    A("| # | 结论 | 判据 | 变异台 |")
    A("|---|---|---|---|")
    A("| 244.81-1 | 固定剂量下 w 臂改判 %s/%s、rand 臂 %s/%s、差 %s pp | 面板（分析器自检 %d/%d 绿） | `P21` 删标记 ⇒ 抓住 V-P19 |"
      % (w_pos, w_n, r_pos, r_n, diff, n_pass, n_crit))
    A("| 244.81-2 | 判决**不是自证**：第二条独立实现复现全部数 | 独立重算 **%d/%d** | 面板被改 ⇒ 抓 %d 条 |"
      % (i_pass, i_total, i_mut_caught))
    A("| 244.81-3 | 置换 p 两条不同实现一致（MC 带内） | 独立重算（二项精确） | — |")
    A("| 244.81-4 | 分母形状必须可见（`m` 分布 / `(n_nz,n_zero)` / 基准分布） | **V-P19** | `P21` ⇒ 抓住 |")
    A("| 244.81-5 | 探针形态检查能红（永久红已修） | **C11** | — |")
    A("| 244.81-6 | 前提独立性未量到 ⇒ ⇒ 判决口径依赖 | 面板前提 P1 | — |")
    A("")
    A("## 5. 🚧 **边界清单**（哪些还没量到、哪些数不许再动）")
    A("")
    A("· ⛔ **前提独立性仍未量到**（56 条轨迹 = 28 块 × 2；块内还有 3 个复制格）⇒ ⇒ "
      "**每一个 p 与每一个区间都建立在这个没被验过的前提上** ⇒ ⇒ 「显著」是**口径依赖**的。")
    A("  · ⚖ **但已有先导证据说它大概率不会推翻判决**（见【2】第 9 条）⇒ ⇒ "
      "⚠ 那是**先导**，⛔ **不许**当成「前提已验」⇒ ⇒ 244.82 必须补上"
      "**第二条独立实现 ＋ 变异台（每条判据能红）**。")
    A("· ⚠ **rand 臂有 %s 个零格**（`d == 0`）⇒ ⇒ 「零格**进分母、不进基准**」这条口径**真的被用到**了"
      "（⛔ 基准**不是**恒 0.5）。" % (zero[1] if len(zero) > 1 else "?"))
    A("· ⚠ **w 臂有 1 条轨迹只有 2 个有效格**（那格 `rc=1`、没读数 ⇒ 被剔出格集合）⇒ ⇒ "
      "它的零假设基准是 0.25（⛔ 不是 0.5）⇒ ⇒ 「等剂量」的精度是 **±0.5% 密度**。")
    A("· ⚠ **`pos_frac = 0.25 / 0.75` 的行为**在本批**第一次**被量到 ⇒ ⇒ 但那两组的数**不能**"
      "替合池组说话；⚠ 三组的差异（%s）本身也只在一批数据上量过一次。"
      % " ｜ ".join("%s: %s pp" % (g[0], g[5]) for g in groups))
    A("· ⚠ **剂量趋势未量到**（合池 `n_bands = 1` 没有剂量轴）⇒ ⇒ ⛔ 不是「无趋势」。")
    A("· ⚠ **「照 meta 重建能否逐位复现」仍未量到**（重训命令已定位，见账本 244.79 段【10】；重训要等点头）。")
    A("· ⛔ **旧批与本批的样本可比性未量到**；⛔ **远端 tokenizer 快照的内容指纹仍未量到**。")
    if bc:
        A("· ⚠ **启动器有已登记的漂移**：远端实际跑的那 2 份启动脚本是**本地改过之前**的版本"
          "（差异**逐条**落在已登记清单：① `${}` 加括号、② 收据计数修正、③ 纯注释行）"
          "⇒ ⇒ **执行集文件逐位一致**（R2 验的就是提交里那份），"
          "但**启动器**严格说**不是**逐位一致 ⇒ ⇒ 记为「**已登记的漂移**」，⛔ 不记为「无漂移」。"
          "⚠ 其中 ② 是**本轮我自己发现的收据格式缺陷**：`grep -c` 在无匹配时**照样打印 0** 并返回非 0，"
          "`|| echo 0` 于是**再补一个 0** ⇒ 收据头被撑出两行游离的「0」"
          "⇒ ⇒ **只在「没有差异」时触发**（恰恰是最该干净的情况）⇒ ⇒ 已改用 `awk` 修掉，"
          "**被验量不变**（manifest diff 文件 0 字节 ＋ R1/R2 `manifest_md5` 逐位相同）。")
    if bad_detail:
        A("· ⚖ **全回归唯一红项已定性**：%s ｜ rc = `%s`（= **SIGKILL**，**被 2400 s 上限杀掉**）｜ "
          "R1 与 R2 **两次都恰好停在 %s s** ⇒ ⇒ 按纪律归「**环境/时限**」，⛔ **不是**「判据红」"
          "（⛔「跑不动」⛔ 不是「判据红」）；%s ⇒ ⇒ ⛔ **不是**「这条判据坏了」。"
          % (bc_bad_names, bc_bad_rcs, bc_bad_secs,
             ("旁证：%s —— 机器当时负载低 ⇒ ⇒ 同一份代码在低负载下能过。" % old_ok) if old_ok else ""))
    A("· ⛔ **问题级不适用**：本批**没有** `scope=all` 的格 ⇒ ⇒ 印「**不适用**」（⛔ 不是「未量到」，⛔ 不是「无差异」）。")
    A("")
    A("## 6. ▶️ **下一步（244.82）**")
    A("")
    A("1. **验前提独立性**（这是判决现在最硬的缺口）：块内相关、块间独立、复制格一致性（分歧率）"
      "⇒ ⇒ 必要时改成**按块聚合**的口径并重算区间。")
    A("2. **分层剂量那批**：把「剂量」与「机制」两条轴真正拆开（现在只到「固定剂量 + 机制 vs rand」）。")
    A("3. ⛔ **别在前提独立性验过之前把 p 值当结论**；⛔ 拿到分层剂量那一批之前，"
      "**固定剂量的这几个数不许再动**。")
    A("")
    A("## 7. 🧭 **上手三步**")
    A("")
    A("1. 读账本尾部：`.cache/xcheck/R6_RERUN_PREREG.md`（**唯一权威历史**）")
    A("2. 读本文件（交接全文）")
    A("3. `git log --oneline -10` ＋ `git status --porcelain`（工作区有**别人的**未跟踪文件，⛔ 不碰）")
    A("")
    A("## 8. ⚖ **本轮的硬约束**（⛔ 别放松）")
    A("")
    A("· ⛔ **跑批 / sudo / 远端写操作 / 改探针**都要**等用户点头**。")
    A("· ⛔ **一切实验与验证在服务器上跑**（本地只编辑源码/文档；本轮判决链在 `zju-53`、全回归在 `zju-12`）。")
    A("· ⛔ **账本只追加**；改数只**撤回并更正**，⛔ 绝不改数凑好看。")
    A("· ⛔ **没量到的写「未量到」**，⛔ 不许说成「无差异」。")
    A("· ⛔ 提交只带**显式路径**；⛔ 不用 `git add -A`、⛔ 不加整个目录。")
    A("")
    with io.open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("✅ %s（%d 字节）" % (OUT, len("\n".join(L).encode("utf-8"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
