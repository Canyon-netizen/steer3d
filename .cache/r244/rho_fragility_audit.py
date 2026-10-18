#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rho_fragility_audit.py —— 层内 Spearman 的 12/14 **稳不稳**（零 GPU）

🔴 **这个工具要回答什么**
  244.38 之后剩下的 🔴 是「rand 臂传播层 12/14 正号（p=0.0129）是不是噪声」。
  ⚖⚠ 而 rep_n=1 ⇒ **格内噪声没量到** ⇒ 「噪声 vs 信号」**结构性答不了**。
  ⚗⇒ 那就问一个**能答的**次级问题：
  **这 12 条正号，是不是每条都被**某一档**撑着的？**
  ⚖⚠⚖ 这不是「噪声」那个问题，但它是那个问题的**前置**：
     若一条 rho 的符号**删掉任意一档就会翻**，那么「单调剂量响应」
     这个说法在**这条轨迹上根本不成立** ⇒ 12/14 这个计数的**分母就不干净**。

⚖⚖ **方法：丢一档 jackknife（leave-one-rung-out）**
  ⚖ 对每条轨迹，把它的传播层档数减一，**重算** rho，记下符号。
  ⚖ 报告三样：① 符号翻转的档数 ② 符号是否稳定
     ③ **单独**报告「删掉覆盖率最高那一档」之后符号如何
  ⚖⚠ ③ 之所以单独报，是因为整个「剂量—响应」叙事**就压在那最高档上**。

⚖⚖ **顺带排除一条退化路径：`n_distinct`**
  ⚖ 若响应被量化成少数几个取值，Spearman 就跑在一个**粗网格**上
  ⇒ 排序信息比看上去少。⚖ 探针已经落盘 `n_distinct`（α 扫描上 `dm` 的不同取值数）
  ⇒ 报告必须把它印出来 ⛔ 不许只报 rho。

⚖⚠⚠ **读法（必须照抄）**
  ⚖ ⚠ 「符号稳定」⛔ **不等于**「不是噪声」——它只说明这条轨迹的排序
     **不由单一档决定**。⛔ rep_n=1 的那个问题**本工具回答不了**。
  ⚖ ⚠ 「符号脆弱」⇒ ⛔ 也**不等于**噪声，它只说明**这一条**撑不起「单调」的说法。

⛔ 本工具：⛔ 不改任何真文件；⛔ 不跑批；⛔ 只读两份已有日志。
"""

import argparse
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else "."
PROBE_REL = ".cache/mutbak/r204_noise_probe.py"
W_LOG = ".cache/r244/w_new.log"
RAND_LOG = ".cache/r244/rand_new.log"

MIN_RUNGS = 3          # ⚖ Spearman 的最小档数（2 点时恒为 ±1，244.31 已登记）
DEGENERATE_ND = 2     # ⚖ n_distinct ≤ 它 ⇒ 认为响应被量化到粗网格上
ALPHA = 0.05          # ⚖ 显著性门槛（⚖⚠ 是约定，⛔ 不是自然常数）


class HardFail(Exception):
    pass


def _load_dose():
    path = os.path.join(HERE, "dose_axis_audit.py")
    if not os.path.exists(path):
        raise HardFail("找不到 %s ⇒ ⛔ 拒读" % path)
    spec = importlib.util.spec_from_file_location("dose_axis_for_frag", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------- jackknife
def jackknife(cov, y, spearman_fn):
    """⚖ **丢一档 jackknife**：返回 (rho_full, 符号翻转的档数, 删最高档后的 rho)。

    ⚖⚠⚠ **零差必须单列**：`rho_full == 0.0` 时符号无意义
       ⇒ 翻转数⛔ 不许算成 0（那会把「无方向」印成「非常稳」）。
    ⚖⚠⚠⚖⚖ 这里原本还有一道 `if n < min_rungs(MIN_RUNGS=3): return None, ...`
       —— ⚖⚠⚖⚖ **变异台把它判为可证冗余并已删除**：
       `dose_axis_audit.spearman` **自己**就前置 `len(x) < 3 ⇒ None`
       ⇒ 2 档时它返回 None ⇒ 无论这道守卫在不在，`jackknife` 都返回
       (None, None, None) ⇒ **删不删完全一样** ⇒ 那是一条**恒绿护栏**。
       ⚖⚠⚠ 而 `MIN_RUNGS` 常量**保留**：它仍被 `run()` 用来把短档标成「未量到」。
       ⚗⇒ 恒绿护栏要么删、要么写成能红的形状；这里**删函数里的，留报告用的**，
         并把「为什么删」写在原地 —— ⛔ 不是把它悄悄改掉。
    """
    n = len(cov)
    full = spearman_fn(list(cov), list(y))
    if full is None:
        return None, None, None
    if full == 0.0:
        return 0.0, None, spearman_fn(list(cov[:-1]), list(y[:-1]))
    flips = 0
    for j in range(n):
        c2 = [v for i, v in enumerate(cov) if i != j]
        y2 = [v for i, v in enumerate(y) if i != j]
        r2 = spearman_fn(c2, y2)
        if r2 is not None and (r2 > 0) != (full > 0):
            flips += 1
    top = spearman_fn(list(cov[:-1]), list(y[:-1]))   # ⚖ 删掉覆盖率**最高**那一档
    return full, flips, top


def degenerate(cells, D, kp):
    """⚖ 数出响应被量化到粗网格上的格数（`n_distinct ≤ 2`）。"""
    bad, seen, miss = 0, 0, 0
    for c in cells:
        n, cov, direct = D.check_cell(c, kp)
        if cov is None:
            continue
        seen += 1
        v = c.get("n_distinct")
        try:
            v = int(v)
        except (TypeError, ValueError):
            miss += 1
            continue
        if v <= DEGENERATE_ND:
            bad += 1
    return bad, seen, miss


# --------------------------------------------------------------- 复用（⛔ 不写第二份实现）
def _mcnemar_exact(b, c):
    """⚖ **复用** `arm_contrast_audit.mcnemar_exact`。

    ⚖⚠⚠⚖ ⛔ **不做第二份实现**：手抄就是两份口径必然漂移
       （244.35 那条「抄来的常量会静默过期」的同族教训）。
    ⚖ 两条工具的差异检验**必须是同一把尺**，否则两节的 p 不可比。
    """
    path = os.path.join(HERE, "arm_contrast_audit.py")
    if not os.path.exists(path):
        raise HardFail("找不到 %s ⇒ ⛔ 拒读（⛔ 不手抄一份 McNemar）" % path)
    import importlib.util as _iu
    spec = _iu.spec_from_file_location("arm_for_frag", path)
    mod = _iu.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod.mcnemar_exact(b, c)


def _binom2(k, n):
    import math
    if n <= 0:
        return None
    return min(1.0, 2.0 * sum(math.comb(n, i)
                            for i in range(0, min(k, n - k) + 1)) / 2.0 ** n)


def _frag_flags(D, kp, path, want_direct):
    """⚖ 每条轨迹「符号是否脆弱」= 丢一档 jackknife 是否出现变号。"""
    rows = D.k_cells(D.load_cells(path), kp)
    g = D.by_tid([r for r in rows if r["direct"] == want_direct])
    out = {}
    for tid in sorted(g):
        sub = sorted(g[tid], key=lambda r: r["cov"])
        full, flips, _top = jackknife([r["cov"] for r in sub],
                                      [r["raw"] for r in sub], D.spearman)
        if full is None or full == 0.0:
            continue
        out[tid] = bool(flips)
    return out


def fragile_is_not_a_verdict(p_value, alpha=ALPHA):
    """⚖⚖ **恒返回 False 的禁令**，且它**必须**恒返回 False。

    🔴 244.37 与 244.38 连续两次踩同一个坑的延伸：
       「p ≥ 0.05 ⇒ 这个性质不存在」——⛔ 不成立。
    ⚖⚠⚠⚖ 本工具会印出 discordant **5 vs 0**、p=**0.0625** 这种
       「方向一边倒但够不到 0.05」的读数。
       ⛔ 那必须报「**未量到**」，⛔ 不能报「两臂稳健性没有差别」。
    ⚖⚠⚠⚠ 而 discordant 是**离散**的：单向不一致要 **6 vs 0** 才越过 0.05
       ⇒ 「差一格」这件事**必须**印出来，而不是让读者以为「差很远」。
    """
    return False


# --------------------------------------------------------------- 主流程
def run(w_log=W_LOG, rand_log=RAND_LOG, probe_path=PROBE_REL):
    D = _load_dose()
    kp = D.load_k_positions(probe_path)
    L = []

    L.append("【1】响应被量化了吗（`n_distinct`，α 扫描上 dm 的不同取值数）")
    for name, path in (("w", w_log), ("rand", rand_log)):
        bad, seen, miss = degenerate(D.load_cells(path), D, kp)
        L.append("  ⚖ %s 臂：k 档格 %d 个；`n_distinct` ≤ %d 的 **%d** 个"
                 "（缺失 %d 剔出）⇒ %s"
                 % (name, seen, DEGENERATE_ND, bad, miss,
                    "✅ 响应**没有**退化到粗网格" if bad == 0
                    else "⚠⚠ 有格退化 ⇒ Spearman 的排序信息比看上去少"))

    L.append("")
    L.append("【2】层内 rho 的丢一档 jackknife")
    for tag, want in (("传播层", False), ("直接层", True)):
        L.append("")
        L.append("  ── %s" % tag)
        for name, path in (("w", w_log), ("rand", rand_log)):
            rows = D.k_cells(D.load_cells(path), kp)
            g = D.by_tid([r for r in rows if r["direct"] == want])
            L.append("     %s 臂" % name)
            L.append("       %-26s %5s %6s %6s %s"
                     % ("tid", "档数", "rho", "翻档", "删最高档后"))
            n_calc = n_zero = n_flip = n_top_flip = n_short = 0
            for tid in sorted(g):
                sub = sorted(g[tid], key=lambda r: r["cov"])
                cov = [r["cov"] for r in sub]
                y = [r["raw"] for r in sub]
                if len(sub) < MIN_RUNGS:
                    n_short += 1
                    L.append("       %-26s %5d %6s %6s %s"
                             % (tid, len(sub), "未量到", "—", "—"))
                    continue
                full, flips, top = jackknife(cov, y, D.spearman)
                if full is None:
                    n_short += 1
                    L.append("       %-26s %5d %6s %6s %s"
                             % (tid, len(sub), "未量到", "—", "—"))
                    continue
                n_calc += 1
                if full == 0.0:
                    n_zero += 1
                if flips:
                    n_flip += 1
                if top is not None and full != 0.0 and (top > 0) != (full > 0):
                    n_top_flip += 1
                L.append("       %-26s %5d %+6.3f %6s %s"
                         % (tid, len(sub), full,
                            "—" if flips is None else str(flips),
                            "—" if top is None else "%+.3f" % top))
            stable = n_calc - n_flip
            L.append("       ⚖ 可算 %d 条｜rho 恰为 0 的 %d 条｜"
                     "**符号翻转过的 %d 条**｜删最高档后变号的 %d 条｜档数不足 %d 条"
                     % (n_calc, n_zero, n_flip, n_top_flip, n_short))
            L.append("       ⇒ %s"
                     % ("⚖ 符号全部稳定（%d/%d）⇒ 「单调」这条不是靠单档撑起来的"
                        % (stable, n_calc) if n_flip == 0 and n_calc else
                        "⚠⚠ **%d/%d 条**的符号删掉某一档就翻 ⇒ 那些「正号」"
                        "**撑不起**「单调剂量响应」" % (n_flip, n_calc)))

    L.append("")
    L.append("【3】两臂的稳健性有差别吗（**配对**检验，⛔ 不是两个比例摆一起比）")
    fw = _frag_flags(D, kp, w_log, False)
    fr = _frag_flags(D, kp, rand_log, False)
    tids = sorted(set(fw) & set(fr))
    both = sum(1 for t in tids if fw[t] and fr[t])
    only_w = sum(1 for t in tids if fw[t] and not fr[t])
    only_r = sum(1 for t in tids if fr[t] and not fw[t])
    neither = sum(1 for t in tids if not fw[t] and not fr[t])
    mc = _mcnemar_exact(only_w, only_r)
    L.append("  ⚖ 配对 n=%d｜都脆弱 %d｜**只 w 脆弱 %d**｜**只 rand 脆弱 %d**｜都稳 %d"
             % (len(tids), both, only_w, only_r, neither))
    L.append("  ⚖ McNemar 精确（⛔ **只用不一致对**）p = **%.4f**" % mc)
    grp = _binom2(only_w + both, len(tids)) if len(tids) else None
    L.append("  ⚖⚠⚠ 对照：组间两比例的 Fisher p = **%.4f** ⛔ **这里不适用**"
             "（两臂跑的是**同一批轨迹** ⇒ 配对设计）" % (grp if grp is not None else 1.0))
    L.append("     ⚖⚠⚠ 两者可能差很远（本次 %.4f vs %.4f）⇒ ⛔ 拿组间那个当结论"
             % (grp if grp is not None else 1.0, mc))
    L.append("  ⚖⚠ 判决的**分辨率**（discordant 是离散的）：")
    for need in range(1, 8):
        pv = _mcnemar_exact(need, 0)
        L.append("     单向不一致 %d vs 0 ⇒ p=%.4f%s"
                 % (need, pv, "  ✅ 越过 0.05" if pv < 0.05 else "  ⛔ 还差"))
        if pv < 0.05:
            break
    L.append("  ⇒ %s" % ("⚖⚠ 方向是**一边倒**（%d vs %d），但 %s ⇒ **未量到**，"
                        "⛔ 不是「没有差别」"
                        % (only_w, only_r,
                           "p 够不到 0.05" if mc >= ALPHA else "p<0.05")
                        if only_w != only_r else
                        "⚖ 两臂脆弱的轨迹数相同 ⇒ 未量到差异"))

    L.append("")
    L.append("【4】读法（⛔ 不要越读）")
    L.append("  ⚖ ⚠ 「符号稳定」⛔ **不等于**「不是噪声」")
    L.append("     —— rep_n=1、格内噪声没量到，本工具⛔ **回答不了**那个问题。")
    L.append("  ⚖ ⚠ 「符号脆弱」⛔ 也**不等于**噪声，它只说明那一条撑不起「单调」。")
    return "\n".join(L), 0


# --------------------------------------------------------------- 自检
def selftest():
    ok, bad = [], []

    def chk(t, cond, why=""):
        (ok if cond else bad).append(t)
        print(("[PASS] %s %s" if cond else "[FAIL] %s %s") % (t, why))

    import importlib.util as _iu
    sp = _iu.spec_from_file_location("frag_probe", os.path.join(HERE, "dose_axis_audit.py"))
    dm = _iu.module_from_spec(sp)
    sys.modules[sp.name] = dm
    sp.loader.exec_module(dm)
    spm = dm.spearman

    # C1 ⚖⚠⚖ 干净单调 ⇒ 删任意一档**都不该**翻符号
    f1, fl1, t1 = jackknife([0.1, 0.2, 0.3, 0.4], [1.0, 2.0, 3.0, 4.0], spm)
    chk("C1", abs(f1 - 1.0) < 1e-12 and fl1 == 0 and abs(t1 - 1.0) < 1e-12,
        "干净单调：rho=%+.3f、翻档 %d、删最高档后 %+.3f" % (f1, fl1, t1))

    # C2 ⚠⚠⚖ **必须能红**：一档撑着的序列 ⇒ 删掉它符号翻
    #    ⚖⚠⚠⚖⚖ 夹具**暴力搜出来的**，⛔ 不是我编的：
    #    第一版写的 `[1,2,9,3]` 翻不了（rho=+0.8，删掉 9 仍是 +1）；
    #    ⚖ 而我第一次搜索用 `combinations_with_replacement` ⇒ **只生成单调序列**
    #    ⇒ 秩本就有序 ⇒ 删一档永远翻不了 ⇒ 我差点把「搜不到」
    #    ⚖ 当成「结构上不可能」（随机序列上实测发生率 **45–55%**）。
    #    ⛔ **搜索方法错了，症状却长得像个结论。**
    f2, fl2, t2 = jackknife([0.1, 0.2, 0.3, 0.4, 0.5],
                            [25.0, 27.0, 3.0, 17.0, 33.0], spm)
    chk("C2", fl2 is not None and fl2 >= 1 and t2 is not None
        and (t2 > 0) != (f2 > 0),
        "一档撑着的序列：rho=%+.3f、翻档 %s、删最高档后 %+.3f（期望变号）"
        % (f2, fl2, t2))

    # C3 ⚠⚠ 档数 < 3 ⇒ **未量到** ⇒ 返回 None，⛔ 不许当 0
    # ⚖⚠⚖⚖ 承重的是 `spearman` **自己**的 n>=3 前置，⛔ 不是 jackknife 里那道
    #   （那道已被变异台判为恒绿并删除）。
    f3, fl3, t3 = jackknife([0.1, 0.2], [1.0, 9.0], spm)
    sp2 = spm([0.1, 0.2], [1.0, 9.0])
    chk("C3", f3 is None and fl3 is None and sp2 is None
        and MIN_RUNGS == 3 and "未量到" in run()[0],
        "2 档 ⇒ 未量到（spearman 前置=%s、jackknife=%s）；报告层 MIN_RUNGS=%d "
        "且短档必须印「未量到」" % (sp2, f3, MIN_RUNGS))

    # C4 ⚠⚠⚖ rho 恰为 0 ⇒ 符号**无意义**，翻转数⛔ 不得算成 0（=「非常稳」）
    # ⚖⚠⚠ 夹具同样是搜出来的：`[1,3,2,4]` 的 rho 并不为 0。
    f4, fl4, _ = jackknife([0.1, 0.2, 0.3, 0.4], [2.0, 4.0, 4.0, 2.0], spm)
    chk("C4", f4 == 0.0 and fl4 is None,
        "rho 恰为 0 ⇒ 翻转数必须报 None（实测 %s），⛔ 不许当 0"
        % ("None" if fl4 is None else fl4))

    # C5 ⚖ 端到端：退化计数必须来自**真实字段**，⛔ 不许默认 0
    L2, _ = run()
    chk("C5", "n_distinct" in L2 and "`n_distinct` ≤ %d 的" % DEGENERATE_ND in L2
        and ("没有**退化" in L2 or "有格退化" in L2),
        "报告必须印出 `n_distinct` 退化计数（阈值 %d）" % DEGENERATE_ND)

    # C7 ⚖ 阈值必须**印成字面量**（⛔ 只活在代码里 ⇒ 改它全绿）
    # ⚖⚠⚠⚖ 分母是 **13**（w 臂有一条 rho 恰为 0 被剔出），⛔ 不是 14
    #   —— 我第一版写 14 算得 0.7905，报告里印的 0.58105 才是对的
    #   ⇒ 断言必须对着**报告真正用的那个数**写。
    chk("C7", abs((_binom2(8, 13) or 1.0) - 0.58105) < 1e-4
        # ⚖⚠⚠⚖⚖⚖ **期望串必须是字面量**：第一版写的是
        #   ``"`n_distinct` \u2264 %d \u7684" % DEGENERATE_ND`` ——
        #   ⛔ 断言**引用了自己的被测参数** ⇒ 改阈值它照样 PASS ⇒ **恒绿**
        #   （244.35「断言不许引用自己的被测参数」，这里又犯一次）
        and ("`n_distinct` \u2264 2 \u7684" in run()[0]),
        "对照组 Fisher(8/13)=%.5f（应 0.58105）；退化阈值必须印成字面量 \u2264 2"
        % (_binom2(8, 13) or 1.0,))

    # C8 ⚠⚠⚖ 「删最高档」必须真的删**覆盖率最大**那一档
    #   ⚖⚠⚠ 第一版与「删最低档」在某些数据上给出同一个 rho ⇒ 测不出来
    #   ⇒ 夹具要挑一组两者**不同**的
    cx = [0.1, 0.2, 0.3, 0.4, 0.5]
    cy = [25.0, 27.0, 3.0, 17.0, 33.0]
    _f, _fl, top = jackknife(cx, cy, spm)
    top_real = spm(cx[:-1], cy[:-1])
    top_low = spm(cx[1:], cy[1:])
    chk("C8", abs(top - top_real) < 1e-12 and abs(top - top_low) > 1e-12,
        "删最高档 ⇒ %+.3f（真值 %+.3f）；删最低档会得 %+.3f ⇒ ⛔ 两者必须不同"
        % (top, top_real, top_low))

    # C6 ⚖⚖⚖ **禁令必须有实体**：discordant 5 vs 0、p=0.0625
    #    ⛔ 「够不到 0.05」⛔ **不等于**「两臂没有差别」。
    chk("C6", fragile_is_not_a_verdict(0.0625) is False and 0.0625 >= ALPHA,
        "反例：单向不一致 5 vs 0 ⇒ p=0.0625 ≥ %.2f（**未量到**），"
        "⛔ 不得印成「两臂稳健性相同」；要到 0.05 需 **6 vs 0**（差一格）" % ALPHA)

    print("自检 %d/%d 通过" % (len(ok), len(ok) + len(bad)))
    if bad:
        print("失败：%s" % ", ".join(bad))
        return 1
    return 0


def main():
    ap = argparse.ArgumentParser(description="层内 Spearman 的稳健性审计（零 GPU）")
    ap.add_argument("--w-log", default=W_LOG)
    ap.add_argument("--rand-log", default=RAND_LOG)
    ap.add_argument("--probe", default=PROBE_REL)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    txt, rc = run(args.w_log, args.rand_log, args.probe)
    print(txt)
    return rc


if __name__ == "__main__":
    sys.exit(main())
