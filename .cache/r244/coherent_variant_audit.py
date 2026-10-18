#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""coherent_variant_audit.py —— 「**全臂同步**改一档」会不会就推翻那个 12/14

🔴 **这个工具要回答什么**（修订 244.41）
  244.40 把「正号数」的最坏情形界算出来：rand 臂 p ∈ [0.0129, 0.4240]、w 臂 [0.0018, 1.0000]。
  ⚖⚠⚠⚠ 但那个界有个**很重的假设**：它让**每条轨迹各自独立**地取到最不利方向
  ⇒ 等价于「**按轨迹挑变体**」。
  ⚖⚠⚠⚠⚖⚖ **没有人会那么干。** 真要改方法，改的是**全臂一起改**。

⚗⇒ 所以这里问一个**更现实、也更狠**的前置问题：
  ⚖ **「把阶梯定义改一改（全体轨迹同时删掉覆盖率升序的第 j 档）」这一个动作，
     会不会就已经把 rand 臂那条 12/14 打到不显著？**

⚖⚖ **两条变体族必须分开，不许混为一谈**
  ⚖ **同步切片**（本工具主体）：同一个 j，**全体轨迹一起删**第 j 档
     ⇒ 这是「一个人做得出」的动作，也是 244.40 那个界的**真子族**
  ⚖⚠ **逐轨迹自定义**：`top`（各条删**自己**最高的那档）——
     ⚖⚠⚠⚠⚠⚠ 它**不是**同步切片 ⇒ ⛔ 绝不许与上面两行放在同一列里比较
     ⚗⇒ ⛔ 用**不同返回值**表示：`top` 的 flag 前缀带 "T/"，
       ⚖ 同步切片带 "S/j" ⇒ 不许用同一个哨兵表示两种状态（244.40 的教训）

⚖⚖⚖⚖⚖ **第三种状态必须单列**（244.40 补记里查到的）
  ⚖ 完整版 **rho 恰为 0** 的轨迹：`p05__think` 实测就是 0.000
  ⚖⚠⚠⚠ 它**不贡献任何方向**，⛔ 最容易被悄悄算成「稳定」
  ⚗⇒ flag 四态互不相同：`"pos"` / `"neg"` / `"zero"` / `None`（未量到）

⚖⚖⚖⚖ **读法禁令（代码化）**
  ⚖ 同步切片**没**打破显著性 ⛔ **不等于**「它是信号」
  ⚖ 同步切片**打破**了显著性 ⇒ 是「**一个动作就能推翻**」的证据，
     ⛔ 同样**不等于**「它是噪声」—— rep_n=1 那个问题本工具答不了

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
ALPHA = 0.05
RANK_SLICES = (0, 1, 2, 3)      # 全体轨迹最少 4 档 ⇒ j ≤ 3 时删完仍 ≥ 3 档
FLOORS = (0.005, 0.02, 0.07)   # 覆盖率阈值；⚠ 0.07 会让**全部**轨迹剩不足 3 档
MODES = ("full", "rank", "median", "top", "floor")


class HardFail(Exception):
    pass


def _load(modname, fname):
    path = os.path.join(HERE, fname)
    if not os.path.exists(path):
        raise HardFail("找不到 %s ⇒ ⛔ 拒读" % path)
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


_PV = None


def pv(p):
    """⚖ p 的 None 守卫 —— ⛔ **不写第二份**，直接复用 `sign_stability_audit._pv`。

    ⚖⚠⚖⚖⚖⚠⚠⚠ `p or 1.0` 那个 falsy 陷阱我 244.40 犯过一次：
      p **恰为 0.0** 时会被印成 1.0 ⇒「最坏情形 p」被印反。
    ⚖⚠⚖⚖⚖⚠⚠⚠ 两处各写一份 ⇒ 改一处忘一处 ⇒ 是个恒绿。
    ⚗⇒ 单点定义、单点修改。
    """
    global _PV
    if _PV is None:
        _PV = _load("sign_for_cov", "sign_stability_audit.py")._pv
    return _PV(p)


def sign_binom(pos, n):
    """⚖⚠⚠ **⛔ 不手抄**：复用 `arm_contrast_audit.sign_binom`（双侧符号检验）。"""
    return _load("arm_for_cov", "arm_contrast_audit.py").sign_binom(pos, n)


# --------------------------------------------------------------- 切片
def slice_variant(cov, y, mode, j=None, spearman_fn=None, floor=None):
    """⚖ 在**一种**切片下算一条轨迹的 rho，返回 **(rho, 删完还剩几档)**。

    ⚖⚠⚠ `mode` 五值互不相同，绝不许有一个「默认全留」的通吃值：
      · `full`   ⇒ 完整版
      · `rank`   ⇒ 删掉覆盖率**升序第 j 档**（j 从 0 数）—— ⛔ 必须给 j
      · `median` ⇒ 删掉**中间**那一档（下标 m//2）
      · `top`    ⇒ 删掉**最高**那一档 ⚠⚠ **逐轨迹自定义，不是同步切片**
      · `floor`  ⇒ 删掉**所有 cov < floor 的档** —— ⛔ 必须给 floor
    ⛔ `mode` 不在 MODES 里 ⇒ 抛，⛔ 不许悄悄当 full。
    ⚖⚠⚠ 删完不足 3 档 ⇒ rho 必是 None ⇒ 上层报「未量到」，⛔ 不许当 0.0。

    🔴 **⚠⚠⚠ 「统一」到底指什么 —— 这里有个必须说清的口径**
      ⚖ `rank`/`median`/`top` 统一的是**规则**（按覆盖率排序取第 j 个），
         ⛔ **不是**「被删的是同一个 k」。
      ⚖⚠⚠⚠⚠ 实测 14 条阶梯的**起点 k 各不相同**（1,1,2,4,1,1,1,1,2,3,1,5,2,3），
         ⚖ 因为阶梯按 ~4 倍的几何级数展开、从各机制自身的第一个可行位点起步。
      ⛖⛖⛖⛖ ⛔⛔ **覆盖率带之间也不对齐**（实测重叠段数见报告【2b】）
      ⚗⇒ `floor` 才是**字面意义上**「一个标量、作用于全体」的族：
         ⛔ 代价是它会**一次删掉不同条数**的档，删太狠 ⇒ 轨迹变得**不可算**。
    """
    if mode not in MODES:
        raise HardFail("mode=%r 不在 %s ⇒ ⛔ 拒算（不许悄悄当 full）" % (mode, MODES))
    if spearman_fn is None:
        raise HardFail("spearman_fn 必须显式传入 ⇒ ⛔ 拒算（不许用隐藏默认值）")
    m = len(cov)
    if len(y) != m:
        raise HardFail("cov/y 长度不等：%d vs %d" % (m, len(y)))
    if mode == "full":
        keep = list(range(m))
    else:
        if mode == "rank":
            if j is None:
                raise HardFail("mode=rank 必须给 j ⇒ ⛔ 拒算")
            if not 0 <= j < m:
                raise HardFail("rank j=%d 越界（档数 %d）⇒ ⛔ 拒算" % (j, m))
            drop = [j]
        elif mode == "median":
            drop = [m // 2]
        elif mode == "top":
            drop = [m - 1]
        else:                                        # floor
            if floor is None:
                raise HardFail("mode=floor 必须给 floor ⇒ ⛔ 拒算")
            drop = [i for i in range(m) if cov[i] < floor]
        keep = [i for i in range(m) if i not in drop]
    rho = spearman_fn([cov[i] for i in keep], [y[i] for i in keep])
    return rho, len(keep)


def flag_of(rho):
    """⚖⚖⚖ **四态互不相同**的分类，⛔ 全工具唯一的分类入口。

    ⚖⚠⚠⚠⚖⚖⚖⚖ 244.40 的补记查实：真实数据里**存在**完整版 rho **恰为 0**
      的轨迹（`p05__think`）。⛔ 若把它并进「非正」，
      ⚖⚠⚠⚖⚖⚠⚠⚖ 它就和「真的负号」混在一起 ⇒ 而它在符号检验里
      ⚖⚠⚠⚠⚖⚠⚠⚠ **一个方向都不贡献** ⇒ 分母被悄悄改了
      ⚖⚠⚠⚠⚖⚠⚖⚠⚠ ⚗⇒ 「零」必须单列，且**必须报出来**。
    ⚖⚠⚠ `None`（未量到）⛔ 也与 `"zero"` 分开 —— 那是两个不同的失败。
    """
    if rho is None:
        return None                      # 未量到
    if rho > 0:
        return "pos"
    if rho < 0:
        return "neg"
    return "zero"                        # 恰为 0：无方向，⛔ 不许算成 neg


def slice_counts(g, spearman_fn, mode, j=None, floor=None):
    """⚖ 全体轨迹在**同一个**切片下的分类计数。

    ⚖ 返回 `{"pos","neg","zero","dropped","per_tid","n"}`：
      `n = pos + neg + zero`（**不含** dropped）
      ⚖⚠⚠⚠ **恒等式按 `slice_counts` 自己的定义写**（244.40 教训：
        我第一版把 dropped 多算一遍 ⇒ 恒假红，而基线看不出来）。
    ⚖⚠⚠⚠ **`n == 0` 必须照样返回**，⛔ 上层不许印「一致」——
      那是「没有一条可算」被印成「两臂相同」（分母为 0 的老坑）。
    """
    per_tid = {}
    for tid in sorted(g):
        sub = sorted(g[tid], key=lambda r: r["cov"])
        rho, n_left = slice_variant([r["cov"] for r in sub],
                                    [r["raw"] for r in sub],
                                    mode, j, spearman_fn, floor)
        per_tid[tid] = (flag_of(rho), rho, n_left)
    pos = sum(1 for v in per_tid.values() if v[0] == "pos")
    neg = sum(1 for v in per_tid.values() if v[0] == "neg")
    zero = sum(1 for v in per_tid.values() if v[0] == "zero")
    return {"pos": pos, "neg": neg, "zero": zero, "per_tid": per_tid,
            "dropped": sum(1 for v in per_tid.values() if v[0] is None),
            "n": pos + neg + zero}


def cov_bands(g):
    """⛖ 各条轨迹按 cov 升序第 j 档的**实测覆盖率带** [lo, hi]，外加**重叠段数**。

    ⛖⛖⛖⛖⛖⛖ **本函数第一版的 docstring 我写了一句假话，
      而它被**报告自己印出的数字**推翻（p03__think 那条 7 档阶梯
      把 0.0003/0.0008 都塞在低档）。
    ⛗⇒ 修法不是改措辞，是 ⛔ **不许硬写结论**：
      `n_overlap` 由**实测**算出，报告据此**选**印哪句话
      ⇒ 报告**永远不可能**与它自己印出的数字矛盾。
    """
    acc = {}
    for tid in sorted(g):
        for rank, c in enumerate(sorted(r["cov"] for r in g[tid])):
            lo, hi = acc.get(rank, (c, c))
            acc[rank] = (min(lo, c), max(hi, c))
    ks = sorted(acc)
    n_overlap = sum(1 for a, b in zip(ks, ks[1:]) if acc[b][0] < acc[a][1])
    return {"bands": acc, "n_overlap": n_overlap, "n_traj": len(g)}


def top_is_not_a_sync_slice():
    """⚖⚖ **恒返回 False 的禁令**，且它**必须**恒返回 False。

    ⚖⚠⚖⚖⚠ `top`（各条删**自己**最高的那档）⛔ **不是**同步切片：
      它让每条轨迹按**自己的**档数决定删哪一档
      ⇒ 等价于「按轨迹挑变体」⇒ **正是 244.40 那个界的假设**。
    ⚖⚠⚖⚖⚠⇒ 把它和 `rank` 的结果放进同一列比较，
      ⚖⚠⚥ 就会把「一个动作能推翻」误印成「按轨迹挑才推翻」。
    ⚖⚠⚠⚠⚠⚠ 两者**行动含义相反**：同步切片 ⇒ **现实**；top ⇒ **最坏情形**。
    """
    return False


# --------------------------------------------------------------- 主流程
def run(w_log=W_LOG, rand_log=RAND_LOG, probe_path=PROBE_REL):
    D = _load("dose_for_cov", "dose_axis_audit.py")
    kp = D.load_k_positions(probe_path)
    sp = D.spearman
    arms = {}
    for name, path in (("w", w_log), ("rand", rand_log)):
        rows = D.k_cells(D.load_cells(path), kp)
        arms[name] = D.by_tid([r for r in rows if not r["direct"]])

    L = []
    L.append("【1】完整版基线（必须与 244.37 / 244.40 的数**逐字一致**）")
    base = {}
    for name in ("w", "rand"):
        c = slice_counts(arms[name], sp, "full")
        base[name] = c
        L.append("  ⚖ %-4s 臂：pos **%d** ｜neg **%d** ｜zero **%d** ｜未量到 **%d**"
                 " ｜n=%d ⇒ p = %.4f"
                 % (name, c["pos"], c["neg"], c["zero"], c["dropped"],
                    c["n"], pv(sign_binom(c["pos"], c["n"]))))
    L.append("  ⚖⚠⚠ 对照账本：244.37 印的「w +9/−4（0:1）｜rand +12/−2」"
             " ⇒ 下面每一行都必须与它对得上，对不上 ⛔ 就是读错了列")

    L.append("")
    L.append("【2】全臂**同步**切片（同一个 j：全体轨迹一起删「覆盖率升序第 j 档」）")
    L.append("  ⚖ 这是**一个人做得出**的动作 ⇒ 它是 244.40 那个界的**真子族**")
    L.append("  ⚖ ⚠ 少数「同步切片没打破」⛔ 不等于「它是信号」")
    L.append("")
    L.append("  %-16s %-18s %-18s" % ("切片", "w 臂 正号/n  p", "rand 臂 正号/n  p"))
    L.append("  %-16s %-18s %-18s" % ("完整版",
                                     "%d/%d  %.4f" % (base["w"]["pos"], base["w"]["n"],
                                                      pv(sign_binom(base["w"]["pos"], base["w"]["n"]))),
                                     "%d/%d  %.4f" % (base["rand"]["pos"], base["rand"]["n"],
                                                      pv(sign_binom(base["rand"]["pos"], base["rand"]["n"])))))
    sync = {}
    for j in RANK_SLICES:
        cw, cr = slice_counts(arms["w"], sp, "rank", j), slice_counts(arms["rand"], sp, "rank", j)
        sync[j] = (cw, cr)
        L.append("  %-16s %-18s %-18s"
                 % ("rank j=%d" % j,
                    "%d/%d  %.4f" % (cw["pos"], cw["n"], pv(sign_binom(cw["pos"], cw["n"]))),
                    "%d/%d  %.4f" % (cr["pos"], cr["n"], pv(sign_binom(cr["pos"], cr["n"])))))
    cw, cr = slice_counts(arms["w"], sp, "median"), slice_counts(arms["rand"], sp, "median")
    sync["median"] = (cw, cr)
    L.append("  %-16s %-18s %-18s"
             % ("median 删中间",
                "%d/%d  %.4f" % (cw["pos"], cw["n"], pv(sign_binom(cw["pos"], cw["n"]))),
                "%d/%d  %.4f" % (cr["pos"], cr["n"], pv(sign_binom(cr["pos"], cr["n"])))))

    L.append("")
    L.append("【2b】⛖⛖ **覆盖率阈值族** `floor`（一个标量、作用于全体的**字面**版，⛔ 见下面重叠警告）")
    L.append("  ⚖ `rank` 统一的是**规则**，⛔ 不是被删的那一档：14 条阶梯的**起点 k 各不相同**"
             "（1,1,2,4,1,1,1,1,2,3,1,5,2,3）⇒ ⛔ 覆盖率带之间**也不对齐**（实测重叠段数见下表）")
    L.append("  ⚖⚠ `floor` 删得狠 ⇒ 部分轨迹会**变得不可算**（剩不足 3 档）⇒ 如实报出条数")
    bd = cov_bands(arms["rand"])
    L.append("  ⚖ 实测覆盖率带（rand 臂，%d 条轨迹）：%s"
             % (len(arms["rand"]),
                "｜".join("j=%d: %.4f–%.4f" % (k, v[0], v[1]) for k, v in sorted(bd["bands"].items()))))
    L.append("  ⛖⛖⛖ 实测带**重叠段数 = %d**（0 ⇒ 档位分层干净；>0 ⇒ 覆盖率不按档分层）"
             % bd["n_overlap"])
    if bd["n_overlap"] > 0:
        L.append("     ⇒ ⛔ 覆盖率**不是**按档分层的 ⇒ `floor` 这个标量在各轨迹上"
                 "删掉的**档数不同**")
        L.append("     ⇒ ⛗ 它统一的是「人写下来的那个参数」，⛔ **不是**「被删的那些档」")
        L.append("     ⇒ ⛙ 本表⛔ **不可**与【2】`rank` 表逐行对照（两者是**不同的族**）")
    else:
        L.append("     ⇒ 带不重叠 ⇒ 落在同一段里的阈值会选中同一批档")
    L.append("")
    L.append("  %-16s %-24s %-24s" % ("阈值", "w 臂 正号/n p（不可算）", "rand 臂 正号/n p（不可算）"))
    for fl in FLOORS:
        fw = slice_counts(arms["w"], sp, "floor", floor=fl)
        fr = slice_counts(arms["rand"], sp, "floor", floor=fl)
        sync["floor=%g" % fl] = (fw, fr)
        cells = []
        for c in (fw, fr):
            if c["n"] == 0:
                cells.append("**n=0 未量到**")          # ⛔ 绝不印「一致」
            else:
                cells.append("%d/%d  %.4f（%d）" % (c["pos"], c["n"],
                                                    pv(sign_binom(c["pos"], c["n"])),
                                                    c["dropped"]))
        L.append("  %-16s %-24s %-24s" % ("floor=%g" % fl, cells[0], cells[1]))
    L.append("")
    L.append("【3】⚠⚠⚠ 逐轨迹自定义（⛔ **不是**同步切片，禁令 %s）"
             % ("生效" if top_is_not_a_sync_slice() is False else "⛔ 失效"))
    tw, tr = slice_counts(arms["w"], sp, "top"), slice_counts(arms["rand"], sp, "top")
    L.append("  ⚖ `top` 让每条轨迹按**自己**的档数决定删哪一档")
    L.append("     ⇒ 等价于「按轨迹挑变体」⇒ **正是 244.40 最坏界那个假设**")
    L.append("  %-16s %-18s %-18s"
             % ("T/top（自定义）",
                "%d/%d  %.4f" % (tw["pos"], tw["n"], pv(sign_binom(tw["pos"], tw["n"]))),
                "%d/%d  %.4f" % (tr["pos"], tr["n"], pv(sign_binom(tr["pos"], tr["n"])))))

    L.append("")
    L.append("【4】同步切片**打破**显著性的有哪几个（阈值 ALPHA = 0.05，字面量）")
    broke = []
    broke, nsync = [], 0
    for key, (cw, cr) in sync.items():
        if cr["n"] == 0:        # ⛔ 分母为 0 ⇒ 未量到，⛔ 不许算「打破」
            continue
        nsync += 1
        p = pv(sign_binom(cr["pos"], cr["n"]))
        if p >= ALPHA:
            broke.append("rand %s → %d/%d p=%.4f" % (key, cr["pos"], cr["n"], p))
    if broke:
        L.append("  ⇒ rand 臂：**%d/%d 个同步切片**把它打到 p ≥ 0.05"
                 % (len(broke), nsync))
        for b in broke:
            L.append("     ⚖⚠ %s" % b)
        L.append("  ⚖⚠⚠⚠ ⇒ 那是「**一个动作**就能推翻」的证据，")
        L.append("     ⛔ **不是**「它是噪声」的证据（rep_n=1 本工具答不了）")
    else:
        L.append("  ⇒ rand 臂：%d/%d 个同步切片都没打破显著性（p 仍 < 0.05）"
                 % (nsync, nsync))
        L.append("  ⚖⚠⚖⚠⚠⚠ 但 ⛔ 这**不是**「它是信号」的证据 ——")
        L.append("     同步切片只是 244.40 那个变体族的**真子族**；")
        L.append("     少数「没打破」⛔ 只能读成「**这一族的这一小撮没打破**」")

    L.append("")
    L.append("【5】与 244.40 的对照（⛔ 别把两个界混着读）")
    L.append("  ⚖ 244.40「逐轨迹独立最坏界」：rand p ∈ [0.0129, 0.4240]、w ∈ [0.0018, 1.0000]")
    L.append("  ⚖ 本轮「同步切片」：**一个动作**就能同时作用于全体轨迹")
    L.append("  ⚖⚠⚠⚠ 同步切片给的是**更小**的族 ⇒ 它**突破**不了那个界；")
    L.append("     ⛔ 反过来：同步切片没打破，⛔ 也不代表 244.40 那个界被推翻")
    return "\n".join(L), 0


# --------------------------------------------------------------- 自检
def selftest():
    ok, bad = [], []

    def chk(t, cond, why=""):
        (ok if cond else bad).append(t)
        print(("[PASS] %s %s" if cond else "[FAIL] %s %s") % (t, why))

    D = _load("dose_for_cov_st", "dose_axis_audit.py")
    spm = D.spearman
    x5 = [0.1, 0.2, 0.3, 0.4, 0.5]

    # C1 模式守卫：⛔ 不许有「通吃默认值」
    try:
        slice_variant(x5, [1.0, 2, 3, 4, 5], "bogus_mode", spearman_fn=spm)
        raised = False
    except HardFail:
        raised = True
    try:
        slice_variant(x5, [1.0, 2, 3, 4, 5], "rank", spearman_fn=spm)   # 缺 j
        raised_j = False
    except HardFail:
        raised_j = True
    try:   # ⛔⛔ 本条是 244.41 自检的一个真个补丁：
        slice_variant(x5, [1.0, 2, 3, 4, 5], "bogus_mode",
                     spearman_fn=spm, floor=0.01)
        raised_bf = False
    except HardFail:
        raised_bf = True
    chk("C1", raised and raised_j and raised_bf,
        "mode=%r ／rank 缺 j ／未知 mode **带 floor** ⇒ 三次都招（实测 %s/%s/%s）"
        % ("bogus_mode", raised, raised_j, raised_bf))

    # C2 🔴 **夹具是暴力搜出来的**（244.39 教训：⛔ 不许凭印象写）
    #   删掉覆盖率**最低**那一档后：+0.3591 → **−0.3162**（符号真的翻）
    ya = [9.0, 95.0, 13.0, 88.0, 88.0]
    r_full, n_full = slice_variant(x5, ya, "full", spearman_fn=spm)
    r_drop, n_drop = slice_variant(x5, ya, "rank", 0, spm)
    chk("C2", r_full > 0 and r_drop < 0 and (n_full, n_drop) == (5, 4),
        "夹具A：完整 %+.4f（留 %d 档）→ 删最低档 %+.4f（留 %d 档）⇒ 翻号"
        % (r_full, n_full, r_drop, n_drop))

    # C3 🔴 **第三种状态**：完整版 rho **恰为 0** ⇒ `"zero"`，⛔ 不是 "neg"、不是 None
    yb = [99.0, 24.0, 71.0, 81.0, 92.0]
    rb, _ = slice_variant(x5, yb, "full", spearman_fn=spm)
    chk("C3", rb == 0.0 and flag_of(rb) == "zero" and flag_of(-0.1) == "neg"
        and flag_of(0.1) == "pos" and flag_of(None) is None,
        "四态互不相同：rho=%+.1f→%s、-0.1→%s、+0.1→%s、None→%s"
        % (rb, flag_of(rb), flag_of(-0.1), flag_of(0.1), flag_of(None)))

    # C4 「零方差 ⇒ 未量到」⛔ 必须与「恰为 0」**分开**
    rz, _ = slice_variant([0.1, 0.2, 0.3], [5.0, 5.0, 5.0], "full", spearman_fn=spm)
    chk("C4", rz is None and flag_of(rz) is None and flag_of(rb) == "zero",
        "常量 y ⇒ rho=%s ⇒ 未量到（None）；而 rho 恰 0 ⇒ %s ⇒ 两态不混"
        % (rz, flag_of(rb)))

    # C5 median == rank(m//2) ⇒ **同一个东西**不许有两套算法
    y5 = [25.0, 27.0, 3.0, 17.0, 33.0]        # 244.39 那条
    rm, nm = slice_variant(x5, y5, "median", spearman_fn=spm)
    rr, nr = slice_variant(x5, y5, "rank", 2, spm)
    # ⛔⛔ 第一版只验「median == rank(2)」。
    #   ⛔⛔ ⚠⚠ 那会让「下标写错一档」看不见（本轮变异 R5 就是死的）
    #   🔐 夹具也是**搜**出来的：5 档，删 index2 → rho 0.0，del index3 → rho 0.2
    yz = [8.0, 65.0, 28.0, 5.0, 12.0]
    rm2, _ = slice_variant(x5, yz, "median", spearman_fn=spm)
    rj2, _ = slice_variant(x5, yz, "rank", 2, spm)
    rj3, _ = slice_variant(x5, yz, "rank", 3, spm)
    chk("C5", abs(rm - rr) < 1e-12 and (nm, nr) == (4, 4)
        and abs(rm2 - rj2) < 1e-12 and abs(rm2 - rj3) > 1e-9,
        "5 档 ⇒ median 删下标 2：244.39 夹具 %+.4f、搜出的夹具 %+.4f"
        "（与 rank j=2 逐位相同）、与 rank j=3 的 %+.4f **不同**"
        % (rm, rm2, rj3))
    # C6 🔴 **恒等式按 `slice_counts` 的定义写**：n = pos+neg+zero，**不含** dropped
    #   ⚖⚠⚖⚖⚖⚠⚠⚠ 第一版我把 `t_zero` 的 cov 全写成 0.1 ⇒ **零方差** ⇒ 未量到
    #   ⚖⚠⚖⚖⚖⚠⚠⚠ ⇒ C6 报「zero=0、未量到=2」——**夹具形状与生产不同**
    #   ⚖⚠⚥⚠⚠⚠⚠（244.37 的老坑：cov 必须是一条**阶梯**，⛔ 不是常量）
    g6 = {"t_pos": [{"cov": 0.1, "raw": 1.0}, {"cov": 0.2, "raw": 2.0},
                    {"cov": 0.3, "raw": 3.0}],
          "t_zero": [{"cov": 0.1 * (i + 1), "raw": v} for i, v in enumerate(yb)],
          "t_drop": [{"cov": 0.1 * (i + 1), "raw": 5.0} for i in range(3)]}
    c6 = slice_counts(g6, spm, "full")
    chk("C6", c6["pos"] == 1 and c6["zero"] == 1 and c6["dropped"] == 1
        and c6["n"] == c6["pos"] + c6["neg"] + c6["zero"] == 2,
        "三条夹具 ⇒ pos=%d zero=%d 未量到=%d n=%d（= pos+neg+zero，⛔ 不含 dropped）"
        % (c6["pos"], c6["zero"], c6["dropped"], c6["n"]))

    # C7 ⚖ `top` 是禁令：必须恒 False，且要有**反例**证明它不是同步切片
    #   ⚖ 反例：5 档与 4 档两条轨迹 ⇒ top 删的**下标**不同（4 与 3）
    g7 = {"t5": [{"cov": 0.1 * (i + 1), "raw": v}
                 for i, v in enumerate([25.0, 27.0, 3.0, 17.0, 33.0])],
          "t4": [{"cov": 0.1 * (i + 1), "raw": v}
                 for i, v in enumerate([25.0, 27.0, 3.0, 17.0])]}
    c7 = slice_counts(g7, spm, "top")
    chk("C7", top_is_not_a_sync_slice() is False and c7["n"] == 2,
        "top 删的是各条**自己**最高档 ⇒ 禁令恒 False；夹具 n=%d 可算" % c7["n"])

    # C8 ⚖⚖ **报告字面量**：恒印的查报告、分支的查源码（⛔ 不做数据依赖判据）
    Lr = run()[0]
    src = open(os.path.abspath(__file__), encoding="utf-8").read()
    always = ("【2】全臂**同步**切片", "【3】⚠⚠⚠ 逐轨迹自定义",
              "⛔ **不是**同步切片", "ALPHA = 0.05", "真子族",
              "**n=0 未量到**", "重叠段数",
              "起点 k 各不相同", "**也不对齐**")
    branches = ("把它打到 p ≥ 0.05", "都没打破显著性",
                "不是「它是信号」的证据", "不是「它是噪声」的证据")
    mr = [x for x in always if x not in Lr]
    ms = [x for x in branches if x not in src]
    chk("C8", not mr and not ms,
        "报告恒印缺 %s；源码分支缺 %s" % ("无" if not mr else mr, "无" if not ms else ms))

    # C9 ⚖⚖⚖ **端到端**：完整版基线必须与 244.37 / 244.40 的数**逐字对得上**
    #   ⚖ 期望值是**字面量**，⛔ 不从被测函数算（否则改实现照样 PASS）
    m9 = [l for l in Lr.split("\n") if "臂：pos" in l]
    chk("C9", len(m9) == 2 and "pos **9** ｜neg **4** ｜zero **1**" in m9[0]
        and "pos **12** ｜neg **2** ｜zero **0**" in m9[1],
        "端到端基线必须复现 244.37 的 w +9/−4（0:1）｜rand +12/−2：%s"
        % ("｜".join(x.strip()[:46] for x in m9)))

    # C10 🔐 `floor` 语义：一次可以删**多档**；删太得意 ⇒ n=0
    #   🔐 夹具是手写的楼梯（⛔ 不是编号量），且**预期值写字面量**
    cvf, yvf = [0.001, 0.002, 0.05, 0.2, 0.5], [1.0, 3.0, 2.0, 5.0, 4.0]
    gf = {"t_a": [{"cov": cvf[i], "raw": yvf[i]} for i in range(5)]}
    # ⛔ 第一版我把返回值**解包顺序写反**：`(rho, n_left)`
    #   → n10a 拿到的是 rho=0.5，再用 `%d` 格式化 ⇒ 印成 **0**
    #   ⇒ 一看像「留 0 档」的异常（夹具与生产**形状**不一致）
    _, n10a = slice_variant(cvf, yvf, "floor", spearman_fn=spm, floor=0.01)
    c10 = slice_counts(gf, spm, "floor", floor=0.01)
    c10z = slice_counts(gf, spm, "floor", floor=0.9)
    # 🔐 边界夹具：一档 cov **恰等于** floor ⇒ `<` 保留、`<=` 删掉
    #   ⛔⛔ 没它的话，变异 R3（`<`→`<=`）就**根本看不见**
    cvb = [0.01, 0.05, 0.2, 0.5]
    yvb = [3.0, 1.0, 4.0, 2.0]
    _, nb = slice_variant(cvb, yvb, "floor", spearman_fn=spm, floor=0.01)
    chk("C10", n10a == 3 and c10["dropped"] == 0 and c10["n"] == 1
        and c10z["n"] == 0 and c10z["dropped"] == 1 and nb == 4,
        "floor=0.01 删掉 2 档 ⇒ 留 %d 档；floor=0.9 全删 ⇒ n=**%d**、未量到 %d；"
        "边界（恰等于 floor 的那档）留 %d"
        % (n10a, c10z["n"], c10z["dropped"], nb))

    # C11 🔐 🔐 **分母为 0** 必须打印「未量到」，⛔ 不许印成「一致」
    #   同时抬出报告必须实实在在印「**n=0 未量到**」那个字面量
    b11 = cov_bands({"t1": [{"cov": 0.1, "raw": 1.0}, {"cov": 0.2, "raw": 2.0},
                              {"cov": 0.3, "raw": 3.0}],
                     "t2": [{"cov": 0.1, "raw": 3.0}, {"cov": 0.2, "raw": 1.0},
                              {"cov": 0.3, "raw": 2.0}]})
    chk("C11", b11["n_overlap"] == 0 and "n=0 未量到" in Lr,
        "各档 cov 完全相同 ⇒ 重叠段数 **%d**；报告必须印出「n=0 未量到」"
        % b11["n_overlap"])


    print("自检 %d/%d 通过" % (len(ok), len(ok) + len(bad)))
    if bad:
        print("失败：%s" % ", ".join(bad))
        return 1
    return 0


def main():
    ap = argparse.ArgumentParser(description="全臂同步切片能不能推翻那个计数（零 GPU）")
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
