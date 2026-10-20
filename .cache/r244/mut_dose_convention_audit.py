#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mut_dose_convention_audit —— `dose_convention_audit.py` 的**变异台**（修订 244.63）

⚠⚠⚖ **本台架问什么**

  244.63 问的是：**剂量轴的「口径」会不会动摇 244.62 的结论**
  ⇒ 实测：**会** —— 8 个口径组合里翻了 **4 个**（rand 臂在「档边界换约定」下
  **确实检出**了剂量趋势，p=0.0418 / 0.0304，MC 带**不跨** α）
  ⇒ 台架必须保证：244.63 的那 **16 条判据****每一条**都**抓得住**对应的实现写错。

⚖⚖⚖⚖ **本台架的分工（两个被测目标）**

  · **目标①**：`dose_convention_audit.py`（本轮的新工具）⇒ 工具自己的逻辑
  · **目标②**：`dose_confound_audit.py` 的**分档器**（244.63 参数化后新增了
    `alt` 档边界分支、`exclusive` 四分位分支、`drop` 零跨度策略）
    ⚖⚠⚠ **这三个分支是 244.63 的全新代码** ⇒ 既有台架（`mut_dose_confound_audit`）
    **一条都没测到**（它的 13 条变异全在分母公式/拒读闸上）⇒ 必须补。
  ⚖⚠⚠⚖ **目标② 用「临时副本 + 重定向 `DCONF`」实现**：
    ⛔ **绝不改工作区里的文件**（只读工作区；变异副本写在系统临时目录），
    ⛔ 绝不在工作区留下任何变异体。

⚖⚖⚖⚖⚖ **台架怎么跑（与别处一致）**

  1. **基线必须绿**：未变异的源码 ⇒ 真实数据全绿 **且** 自检全绿。
  2. 每条变异**只改一处代码点**；⛔ 不改注释/散文。
  3. 每条变异**必须先证明自己有效**：落点串**确实被替换**（命中恰好 1 处）。
  4. **崩 ≠ 抓到**：被测代码抛异常单列（`__crash__`），⛔ 不算抓到；
     **切坏语法的变异判「无效」**，⛔ 也不许算抓到。
  5. **两条路都查**（真实数据路 + 自检的畸形夹具路）
  6. ⚖⚠⚖⚖ **期望标签必须存在**（244.62 自己踩过：判据改名后期望标签还写着旧号
     ⇒ 期望**指向了不存在的判据** ⇒ 变异明明让真判据红了，台架却报「存活」
     ⇒ 现在是守卫：**期望标签不在基线判据集合里 ⇒ 判「无效」**（⛔ 不许报存活））

⚖⚖⚖⚖⚖ **必须能红**的变异（20 条）

  M1  档边界变体没传下去（写死 prod）      ⇒ C11
  M2  零跨度格策略没传下去（写死 keep）    ⇒ C11
  M3  四分位维度的两个取值被写成同一个      ⇒ C1
  M4  判决被写死成恒真                     ⇒ C4
  M5  预登记的 α 被改小（0.05 → 0.01）     ⇒ C0
  M6  层内基准被换成 0.5                   ⇒ C3
  M7  「⚠⚠ **翻转**」这个标记被改掉        ⇒ C5
  M8  「MC95%带」这个标记被改掉            ⇒ C10
  M9  「剂量轴口径多数」这个标记被改掉      ⇒ C8
  M10 p_exact 被写死成 0                   ⇒ C9
  M11 口径空间少枚举一维（8 → 4）           ⇒ C1
  M12 少印一个口径组合                     ⇒ C4
  M13 结论字段被写成「无差异」              ⇒ C13
  M14 检出状态词被写死（「未检出」）         ⇒ C11
  M15 前提标签 【P5】 被改掉                ⇒ C15
  M16 「空转：」这个标记被改掉              ⇒ C2
  M17 「跨臂配对：」这个标记被改掉          ⇒ C7
  M18 【分档器】alt 第一档的边界 `<` 改 `<=` ⇒ C11
  M19 【分档器】drop 零跨度格被改成空操作   ⇒ C11
  M20 【分档器】alt 第二档的边界 `<=` 改 `<` ⇒ C11

⚖⚠⚖⚖⚖⚖ **为什么 M3 与 M20 是「枚举空间」与「边界分支」，⛔ 不是「四分位算法的取值」**
  （244.63 台架第一版的实测 ⇒ 改了两轮，**如实记下来**）：

  ⚖⚠⚖⚠⚠ 第一版的 M3 是「`quantile` 参数被写死成 `inclusive`」⇒ **变异存活**。
  ⚖⚠⚠ **原因不是判据弱，而是**这一维在这批数据上**完全空转**：
  实测 **inclusive 与 exclusive 的分档表逐位相同**（27/28/30/24 两边一样）
  ⇒ 改那个**取值**的错误在真数据上**不可分辨**
  ⇒ 这正是 244.50 的 **P7 同族**：「真数据在某维度上全同值 ⇒ 该维度上的错**在真数据里恒绿**」。
  ⚖⇒ 处置：① 工具里把「哪些维度**完全空转**」**算出来并印出来**（判据 C2 盯它）
  ② 账本 244.63 登记「**四分位算法这一维的口径不确定性未量到**」
  ③ 台架改测**枚举空间**（M3）与**边界分支**（M20）—— 那两处**改得动**。

⚖⚠⚖⚖⚖⚖ **台架自己踩到的两个坑（第一版 ⇒ 已修，记录在案）**
  ① **临时目录删早了**：变异副本在 `finally` 里删 ⇒ 工具**加载时**找不到分档器
     ⇒ 三条分档器级变异全**崩**（⛔ 崩 ≠ 抓到）⇒ 改成**跑完再删**。
  ② **自检里的硬编码下标**：`scenarios[4]` 在枚举被改成 4 个组合时**越界** ⇒ 自检**崩**
     ⇒ 改成负下标 ⇒ 枚举怎么变都不会越界。

跑法：
    python3 mut_dose_convention_audit.py
退出码：0 = 全部被抓住；1 = 有变异存活 / 基线不绿。
"""

import argparse
import contextlib
import io
import os
import re
import shutil
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "dose_convention_audit.py")
BANDER = os.path.join(HERE, "dose_confound_audit.py")

# ⚖ 工具里 `DCONF` 的定位串（变异台用它把分档器**重定向**到临时副本）
DCONF_LINE = 'DCONF = os.path.join(HERE, "dose_confound_audit.py")'

# ⚖ (编号, 目标, 落点旧串, 落点新串, 期望红的那条判据, 它踩的是哪一支)
MUTATIONS = [
    ("M1", "tool",
     "boundary=boundary, quantile=quantile)",
     "boundary=\"prod\", quantile=quantile)",
     "C11", "档边界变体没传下去（写死 prod）⇒ alt 组合退化成 prod"),
    ("M2", "tool",
     "DC.dose_cells(recs, zero_span=zero_span)",
     "DC.dose_cells(recs, zero_span=\"keep\")",
     "C11", "零跨度格策略没传下去（写死 keep）⇒ drop 组合退化成 keep"),
    ("M3", "tool",
     "QUANTILES = (\"inclusive\", \"exclusive\")",
     "QUANTILES = (\"inclusive\", \"inclusive\")",
     "C1", "四分位维度的两个取值被写成同一个 ⇒ 枚举空间塌成 4 个组合"),
    ("M4", "tool",
     "return dfrag().verdict_of(sc)",
     "return True",
     "C4", "判决被写死成恒真（印出的 p=0.0418 与「成立」自相矛盾）"),
    ("M5", "tool",
     "ALPHA = 0.05\n# ⚖ **预登记的 α**",
     "ALPHA = 0.01\n# ⚖ **预登记的 α**",
     "C0", "预登记的 α 被改小（0.05 → 0.01）"),
    ("M6", "tool",
     "bases = [DL.majority_base_p(nz) for nz in row[\"nzs\"]]",
     "bases = [0.5 for nz in row[\"nzs\"]]",
     "C3", "层内基准被换成 0.5（⛔ 244.60 的核心陷阱）"),
    ("M7", "tool",
     "\"  ⚠⚠ **翻转**\" if s[\"flip\"] else \"\")",
     "\"  ⚠⚠ ✗✗\" if s[\"flip\"] else \"\")",
     "C5", "「⚠⚠ **翻转**」这个**标记**被改掉 ⇒ 「必须印出」型判据红"),
    ("M8", "tool",
     "MC95%%带 [%.4f, %.4f]%s",
     "MCband [%.4f, %.4f]%s",
     "C10", "「MC95%带」这个**标记**被改掉 ⇒ 不确定带没被印出"),
    ("M9", "tool",
     "\" ｜ 剂量轴口径多数 %d/%d ｜ 检出状态=%s\"",
     "\" ｜ 轴口径多数 %d/%d ｜ 检出状态=%s\"",
     "C8", "「剂量轴口径多数」这个**标记**被改掉"),
    ("M10", "tool",
     "p_exact = RD.sign_test([float(d) for d in nz])[0] if nz else None",
     "p_exact = 0.0 if nz else None",
     "C9", "配对置换 p 的对照（精确符号检验）被写死成 0"),
    ("M11", "tool",
     "combos = list(itertools.product(BOUNDARIES, QUANTILES, ZERO_SPANS))",
     "combos = list(itertools.product(BOUNDARIES, QUANTILES, (\"keep\",)))",
     "C1", "口径空间少枚举一维（8 个组合 ⇒ 4 个）"),
    ("M12", "tool",
     "    for s in allr[\"scenarios\"]:\n        is_base = (s[\"combo\"] == BASE_COMBO)",
     "    for s in allr[\"scenarios\"][:7]:\n        is_base = (s[\"combo\"] == BASE_COMBO)",
     "C4", "少印一个口径组合 ⇒ 判决行数对不上"),
    ("M13", "tool",
     "concl = \"未量到\" if len(r_states) > 1 else r_states[0]",
     "concl = \"无差异\" if len(r_states) > 1 else r_states[0]",
     "C13", "结论字段被写成「无差异」⇒ 措辞与实算状态不一致"),
    ("M14", "tool",
     "return ST_YES if p < ALPHA else ST_NO",
     "return ST_NO",
     "C11", "检出状态词被写死成「未检出」⇒ 与独立写死的期望表不符"),
    ("M15", "tool",
     "\"【P5】⚖⚠⚖⚖ **MC p",
     "\"【P5x】⚖⚠⚖⚖ **MC p",
     "C15", "前提标签 【P5】 被改掉 ⇒ 「必须印出」型判据红"),
    ("M16", "tool",
     "    · 空转：%s ｜ w=%s rand=%s ｜ 完全空转=%s",
     "    · 空转表：%s ｜ w=%s rand=%s ｜ 完全空转=%s",
     "C2", "「空转：」这个**标记**被改掉 ⇒ 空转标记对不上账"),
    ("M17", "tool",
     "    · 跨臂配对：%s ｜ %s",
     "    · 跨对配：%s ｜ %s",
     "C7", "「跨臂配对：」这个**标记**被改掉 ⇒ 配对前提没被印出"),
    # ---- 目标②：分档器（244.63 新增的三个分支）----
    ("M18", "bander",
     # ⚖⚠⚠⚖ **244.64 改过落点串**（理由写在原地）：
     #   244.64 把分档器从「写死 4 档」改成**通用 n 档循环**（`dose_bands_v(..., n_bands=)`）
     #   ⇒ 原来的落点串 `"if f2 < qs[0]]),"` / `"if qs[0] <= f2 < qs[1]]),"` **在源码里消失了**
     #   ⇒ 台架把这两条判成「**无效变异**」并跳过 ⇒ ⚠⚠ **台架仍报绿，却静默少了 2 条牙**
     #   ⇒ ⇒ 落点串跟着新写法走（**切的是同一处边界，语义不变**）：
     #     · alt 第一档：`f2 < qs[0]` ⇒ `f2 <= qs[0]`
     #     · alt 内档：`qs[i] <= f2 < qs[i+1]` ⇒ `qs[i] < f2 < qs[i+1]`
     "if f2 < qs[0]])]",
     "if f2 <= qs[0]])]",
     "C11", "【分档器】alt 第一档的边界 `<` 改 `<=` ⇒ 切点上的格分配变了"),
    ("M19", "bander",
     "        ks = [r for r in ks if d_of(r) != 0.0]",
     "        ks = [r for r in ks if True]",
     "C11", "【分档器】drop 零跨度格被改成空操作 ⇒ drop 组合退化成 keep"),
    ("M20", "bander",
     # ⚖ 同上：244.64 通用化之后，内档边界是**循环写法** ⇒ 落点串跟着走
     "if qs[i] <= f2 < qs[i + 1]]))",
     "if qs[i] < f2 < qs[i + 1]]))",
     "C11", "【分档器】alt 第二档的边界 `<=` 改 `<` ⇒ 切点上的格分配变了"),
]


def _load(path, src=None):
    mod = types.ModuleType("dca_mut")
    mod.__file__ = os.path.abspath(path)
    exec(compile(src if src is not None
                 else io.open(path, encoding="utf-8").read(), path, "exec"),
         mod.__dict__)
    return mod


def _load_with_bander(tool_src, bander_path):
    """⚖ 把工具里的 `DCONF` 指向一份**临时**的分档器副本。

    ⚖⚠⚠⚖ **⛔ 绝不改工作区里的文件** —— 只读工作区，变异副本写在系统临时目录。
    """
    n = tool_src.count(DCONF_LINE)
    if n != 1:
        raise AssertionError("DCONF 定位串命中 %d 处（必须恰好 1 处）" % n)
    s2 = tool_src.replace(DCONF_LINE, "DCONF = %r" % bander_path)
    return _load(TARGET, s2)


def run_audit(mod):
    """⚖ 真实数据路：返回 {判据号: 是否通过}。"""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            _RP, res, _allr = mod.run()
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, e)
    return {c: o for c, o, _d in res}, None


def run_selftest_fails(mod):
    """⚖ 自检路：返回失败的**完整 token** 集合。"""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            mod.selftest()
    except Exception as e:
        return set(), "%s: %s" % (type(e).__name__, e)
    fails = set()
    for line in buf.getvalue().split("\n"):
        if line.startswith("[FAIL]"):
            m = re.match(r"\[FAIL\]\s+(\S+)", line)
            if m:
                fails.add(m.group(1))
    return fails, None


def _apply(src, old, new):
    n = src.count(old)
    if n != 1:
        raise AssertionError("落点串命中 %d 处（必须恰好 1 处）" % n)
    return src.replace(old, new, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=TARGET)
    ap.add_argument("--bander", default=BANDER)
    args = ap.parse_args()

    src = io.open(args.target, encoding="utf-8").read()
    bsrc = io.open(args.bander, encoding="utf-8").read()

    base = _load(args.target, src)
    R0, err0 = run_audit(base)
    if err0:
        print("⛔ 基线崩了：%s" % err0)
        return 1
    red0 = set(c for c, v in R0.items() if not v)
    sf0, serr0 = run_selftest_fails(base)
    print("基线（真实数据）：%d/%d 通过%s"
          % (sum(1 for v in R0.values() if v), len(R0),
             ("（红：%s）" % ",".join(sorted(red0))) if red0 else ""))
    print("基线（自检）：失败集合 %s" % (",".join(sorted(sf0)) or "空"))
    if red0 or sf0 or serr0:
        print("⛔ 基线不绿 ⇒ 先修基线，台架不许跑（%s%s）"
              % (err0 or "", ",".join(sorted(sf0))))
        return 1

    caught, survived, invalid, crashed = [], [], [], []
    # ⚖⚠⚖⚖⚖ **期望标签必须存在**（244.62 自己踩过 ⇒ 现在是守卫）
    known = set(R0.keys())
    for mid, target, old, new, want, why in MUTATIONS:
        if want not in known:
            invalid.append((mid, "期望标签 %s 不在基线判据集合里（%s）⇒ 标签过期"
                            % (want, ",".join(sorted(known)))))
            print("[SKIP] %s 期望标签 %s **不存在** ⇒ 期望**过期**（⛔ 不许报存活）"
                  % (mid, want))
            continue
        tmpdir = None
        try:
            if target == "tool":
                msrc = _apply(src, old, new)
                mod = _load(args.target, msrc)
            elif target == "bander":
                bmut = _apply(bsrc, old, new)
                tmpdir = tempfile.mkdtemp(prefix="dca_mut_")
                bpath = os.path.join(tmpdir, "dose_confound_audit.py")
                io.open(bpath, "w", encoding="utf-8").write(bmut)
                mod = _load_with_bander(src, bpath)
            else:
                raise AssertionError("未知目标 %r" % target)
        except SyntaxError as e:
            invalid.append((mid, "切完后语法错（%s）⇒ 变异**无效**" % e))
            print("[SKIP] %s 切完后语法错 ⇒ 变异**无效**（%s）" % (mid, e))
            continue
        except AssertionError as e:
            invalid.append((mid, str(e)))
            print("[SKIP] %s 变异**无效**（%s）" % (mid, e))
            continue
        try:
            R, err = run_audit(mod)
            sf, serr = run_selftest_fails(mod)
        finally:
            # ⚖⚠⚠⚠ **删临时目录必须在跑完之后**（⛔ 早删 ⇒ 工具加载时找不到分档器 ⇒ 崩）
            if tmpdir:
                shutil.rmtree(tmpdir, ignore_errors=True)
        if err or serr:
            crashed.append((mid, err or serr))
            print("[CRASH] %s 崩了：%s（⚠ 崩 ≠ 抓到）" % (mid, err or serr))
            continue
        red = set(c for c, v in R.items() if not v)
        by = []
        if want in red:
            by.append("真实数据路")
        if want in sf:
            by.append("自检路（畸形夹具）")
        if not by:
            survived.append((mid, want, "真实路红=%s；自检失败=%s"
                             % (",".join(sorted(red)) or "无",
                                ",".join(sorted(sf)) or "无")))
            print("[SURVIVED] %s 期望 %s 红，实际 真实路=%s 自检=%s ⇒ **变异存活**"
                  % (mid, want, ",".join(sorted(red)) or "无",
                     ",".join(sorted(sf)) or "无"))
            continue
        if not red and not sf:
            invalid.append((mid, "真实路与自检都没变 ⇒ 变异**无效**"))
            print("[SKIP] %s 真实路与自检均未变化 ⇒ 变异**无效**" % mid)
            continue
        caught.append(mid)
        print("[CAUGHT] %s ⇒ %s 红（%s；经 %s）" % (mid, want, why, "、".join(by)))

    print("")
    print("变异台：抓住 %d / %d" % (len(caught), len(MUTATIONS)))
    if survived:
        print("⛔ 存活 %d 条：%s" % (len(survived),
                                "；".join("%s（期望 %s）" % (m, w) for m, w, _ in survived)))
    if invalid:
        print("⚠ 无效变异 %d 条：%s" % (len(invalid),
                                   "；".join("%s（%s）" % (m, why) for m, why in invalid)))
    if crashed:
        print("⚠ 崩了 %d 条：%s" % (len(crashed),
                                   "；".join("%s（%s）" % (m, e) for m, e in crashed)))
    if survived:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
