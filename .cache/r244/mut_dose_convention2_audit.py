#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mut_dose_convention2_audit —— `dose_convention2_audit.py` 的**变异台**（修订 244.64）

⚠⚠⚖ **本台架问什么**

  244.64 问的是：**剂量轴口径的「其余维度」**（分位点算法 / 档数 / 格集合过滤）
  会不会动摇 244.62–244.63 的结论
  ⇒ 实测：**w 臂跨全部 36 个组合都稳健**（p ≤ 0.0006）；
  **rand 臂有 7/36 个组合检出** ⇒ 「rand 的剂量—响应在 α 上未量到」**再加一条独立理由**
  ⇒ 台架必须保证：244.64 的那 **18 条判据****每一条**都**抓得住**对应的实现写错。

⚖⚖⚖⚖ **本台架的分工（三个被测目标）**

  · **目标①**：`dose_convention2_audit.py`（本轮的新工具）⇒ 工具自己的逻辑
  · **目标②**：`dose_confound_audit.py` 的**分档器**（244.64 新增了 `n_bands` 参数
    ＋ `nearest_rank` 分位算法分支）
  · **目标③**：`dose_layer_audit.py` 的**剂量趋势 MC**（244.64 新增了 `n_layer` 参数
    ＋ 权重中心通用化）
  ⚖⚠⚠ **后两个目标的分支是 244.64 的全新代码** ⇒ 既有台架（`mut_dose_convention_audit`、
  `mut_dose_confound_audit`）**一条都没测到** ⇒ 必须补。
  ⚖⚠⚖⚖ **目标②③ 用「临时副本 + 重定向 `DCONF` / `DLAYER`」实现**：
    ⛔ **绝不改工作区里的文件**（只读工作区；变异副本写在系统临时目录），
    ⛔ 绝不在工作区留下任何变异体。
    ⚖ 临时目录里**软链**本目录的全部文件 ⇒ 被测模块的 `HERE` 仍能找齐它的同伴。

⚖⚖⚖⚖⚖ **台架怎么跑（与别处一致）**

  1. **基线必须绿**：未变异的源码 ⇒ 真实数据全绿 **且** 自检全绿。
  2. 每条变异**只改一处代码点**；⛔ 不改注释/散文。
  3. 每条变异**必须先证明自己有效**：落点串**确实被替换**（命中恰好 1 处）。
  4. **崩 ≠ 抓到**：被测代码抛异常单列（`[CRASH]`），⛔ 不算抓到；
     **切坏语法的变异判「无效」**，⛔ 也不许算抓到。
  5. **两条路都查**（真实数据路 + 自检的畸形夹具路）
  6. ⚖⚠⚖⚖ **期望标签必须存在**（244.62 自己踩过：判据改名后期望标签还写着旧号
     ⇒ 期望**指向了不存在的判据** ⇒ 变异明明让真判据红了，台架却报「存活」
     ⇒ 现在是守卫：**期望标签不在基线判据集合里 ⇒ 判「无效」**（⛔ 不许报存活））

⚖⚖⚖⚖⚖ **必须能红**的变异（26 条）

  M1  分位算法没传下去（写死 inclusive）   ⇒ C17
  M2  档数没传下去（写死 4 档）             ⇒ C2
  M3  档边界没传下去（写死 prod）           ⇒ C17
  M4  零跨度策略没传下去（写死 keep）        ⇒ C17
  M5  层数少算一档                          ⇒ C17
  M6  预登记的 α 被改小（0.05 → 0.01）      ⇒ C0
  M7  判决被写死成恒真                     ⇒ C4
  M8  分位算法的两个取值被写成同一个          ⇒ C17
  M9  档数的取值集合被改小                    ⇒ C1
  M10 组合数被写成 8                        ⇒ C1
  M11 rand 检出数被写错                     ⇒ C6
  M12 rand 带跨 α 数被写错                  ⇒ C7
  M13 本机能用的 method 集合被改坏           ⇒ C8
  M14 端点档的缺位点数被写错                ⇒ C9
  M15 「inclusive ≡ exclusive」数被写错     ⇒ C11
  M16 「nearest-rank 改了档表」数被写错      ⇒ C11
  M17 「⚠⚠ **翻转**」这个标记被改掉          ⇒ C4
  M18 结论字段那行被改掉                    ⇒ C15
  M19 留白字段被写成「无影响」               ⇒ C15
  M20 前提标签 【P5】 被改掉                ⇒ C16
  M21 【分档器】生产口径默认档数被改成 5      ⇒ C0
  M22 【分档器】最近秩切点位置算错           ⇒ C17
  M23 【分档器】prod 中间档的左边界写错       ⇒ C17
  M24 【分档器】alt 中间档的右边界写错        ⇒ C17
  M25 【分档器】drop 零跨度格被改成空操作     ⇒ C17
  M26 【趋势 MC】权重中心被写死 1.5          ⇒ C3

⚖⚠⚖⚖⚖⚖⚖ **台架第一版的实测（19/26 ⇒ 如实记在案）**：

  ⚖⚠⚠⚖ **两条存活**：
  · **M6**（α 0.05 → 0.01）：基准那两个 p（0.0002 / 0.0878）在 α=0.01 下**状态不变**
    ⇒ 「只比期望表」的 C0 **抓不到** ⇒ ⇒ 处置：C0 里**显式**断言 `ALPHA == BASE_ALPHA`
    ⇒ 变异改成期望 **C0**。
  · **M21**（分档器默认档数 4 → 5）：本工具**显式**传 `n_bands` ⇒ **看不见默认值被改**
    ⇒ ⇒ 处置：C0 里**单独**比对「生产薄包装 `dose_bands`」与「基准组合」
    ⇒ 变异改成期望 **C0**。
  ⚖⚠⚠⚖ **五条崩**（⛔ 崩 ≠ 抓到 ⇒ 台架**学不到东西**）：
  · **M2 / M5 / M8 / M22** ⇒ ⇒ 处置：工具改成**不崩、只记不一致**
    （档数用**实际**返回的档数算；枚举缺组合时用 `.get()`；期望表缺键时**报告**而不是抛）
  · **M18** ⇒ ⇒ 处置：变异的替换串自己**别带 `%`**（`"..." % concl` 在没有 `%s` 时会抛 TypeError）
    ⇒ ⇒ 纪律：**变异必须让判据变红**，⛔ 不许只让它崩

⚠⚠⚖⚖⚖ **期望标签必须 ∈ 基线判据集合**（244.62 的教训）—— 本台架自己就是守卫。

跑法：
    python3 mut_dose_convention2_audit.py
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
TARGET = os.path.join(HERE, "dose_convention2_audit.py")
BANDER = os.path.join(HERE, "dose_confound_audit.py")
LAYER = os.path.join(HERE, "dose_layer_audit.py")

# ⚖ 工具里两个路径常量的定位串（变异台用它把分档器 / 趋势 MC **重定向**到临时副本）
DCONF_LINE = 'DCONF = os.path.join(HERE, "dose_confound_audit.py")'
DLAYER_LINE = 'DLAYER = os.path.join(HERE, "dose_layer_audit.py")'

# ⚖ (编号, 目标, 落点旧串, 落点新串, 期望红的那条判据, 它踩的是哪一支)
MUTATIONS = [
    ("M1", "tool",
     "quantile=quantile,", "quantile=\"inclusive\",",
     "C17", "分位算法变体没传下去 ⇒ nearest_rank 的组合退化成 inclusive"),
    ("M2", "tool",
     "n_bands=n_bands)", "n_bands=4)",
     "C2", "档数变体没传下去 ⇒ 3/5 档的组合退化成 4 档（声明档数 ≠ 实际档数）"),
    ("M3", "tool",
     "boundary=boundary,", "boundary=\"prod\",",
     "C17", "档边界变体没传下去 ⇒ alt 组合退化成 prod"),
    ("M4", "tool",
     "DC.dose_cells(recs, zero_span=zero_span)",
     "DC.dose_cells(recs, zero_span=\"keep\")",
     "C17", "零跨度格策略没传下去 ⇒ drop 组合退化成 keep"),
    ("M5", "tool",
     "n_mc=N_MC, seed=MC_SEED, n_layer=n_eff)",
     "n_mc=N_MC, seed=MC_SEED, n_layer=n_eff - 1)",
     "C17", "层数少算一档 ⇒ 趋势统计量只用前 n−1 档（权重中心也跟着错）"),
    ("M6", "tool",
     "\nALPHA = 0.05\n", "\nALPHA = 0.01\n",
     "C0", "预登记的 α 被改小（0.05 → 0.01）"),
    ("M7", "tool",
     "    return dfrag().verdict_of(sc)", "    return True",
     "C4", "判决被写死成恒真（印出的 p 与「成立」自相矛盾）"),
    ("M8", "tool",
     "QUANTILES = (\"inclusive\", \"exclusive\", \"nearest_rank\")",
     "QUANTILES = (\"inclusive\", \"inclusive\", \"nearest_rank\")",
     "C1", "分位算法的两个取值被写成同一个 ⇒ 枚举空间塌成 24 个组合"),
    ("M9", "tool",
     "BAND_COUNTS = (3, 4, 5)", "BAND_COUNTS = (3, 4)",
     "C1", "档数的取值集合被改小 ⇒ 枚举空间塌成 24 个组合"),
    ("M10", "tool",
     "N_COMBO = 36", "N_COMBO = 8",
     "C1", "组合数被写成 8"),
    ("M11", "tool",
     "RAND_DETECT_N = 7", "RAND_DETECT_N = 6",
     "C6", "rand 检出数被写错"),
    ("M12", "tool",
     "RAND_BORDER_N = 7", "RAND_BORDER_N = 6",
     "C7", "rand MC 带跨 α 的组合数被写错"),
    ("M13", "tool",
     "WORKING_METHODS = (\"inclusive\", \"exclusive\")",
     "WORKING_METHODS = (\"inclusive\",)",
     "C8", "本机能用的 method 集合被改坏（少认一个）"),
    ("M14", "tool",
     "ENDPOINT_NO_NSITES_N = 28", "ENDPOINT_NO_NSITES_N = 27",
     "C9", "端点档的缺位点数被写错"),
    ("M15", "tool",
     "INC_EQ_EXC_N = 12", "INC_EQ_EXC_N = 11",
     "C11", "「inclusive ≡ exclusive」的设置数被写错"),
    ("M16", "tool",
     "NEAREST_DIFF_N = 9", "NEAREST_DIFF_N = 8",
     "C11", "「nearest-rank 改了档表」的组合数被写错"),
    ("M17", "tool",
     "\"  ⚠⚠ **翻转**\" if s[\"flip\"] else \"\"",
     "\"  ⚠⚠ **flipped**\" if s[\"flip\"] else \"\"",
     "C4", "「⚠⚠ **翻转**」这个标记被改掉"),
    ("M18", "tool",
     "\"  ⚖ rand 臂的剂量—响应结论（α 上）= **%s**\" % concl",
     "\"  ⚖ rand 臂的剂量—响应结论（α 上）= \" + concl",
     "C15", "结论字段那行被改掉（结构化字段消失）"),
    ("M19", "tool",
     "\"  ⚖ 格集合过滤（端点档进轴 / 缺读数格进轴）= **未量到**\"",
     "\"  ⚖ 格集合过滤（端点档进轴 / 缺读数格进轴）= **无影响**\"",
     "C15", "留白字段被写成「无影响」（⛔ 「未量到」被渲染成「无影响」）"),
    ("M20", "tool",
     "\"【P5】⚖⚠⚖⚖ **档数 = 层数", "\"【PX】⚖⚠⚖⚖ **档数 = 层数",
     "C16", "前提标签 【P5】 被改掉"),
    ("M21", "bander",
     "def dose_bands_v(ks, fr, boundary=\"prod\", quantile=\"inclusive\", n_bands=4):",
     "def dose_bands_v(ks, fr, boundary=\"prod\", quantile=\"inclusive\", n_bands=5):",
     "C0", "【分档器】生产口径的**默认档数**被改成 5（⇒ 生产剂量轴整个变了）"),
    ("M22", "bander",
     "r = int(math.ceil(n * (i / float(n_bands))))",
     "r = int(math.ceil(n * (i / float(n_bands + 1))))",
     "C17", "【分档器】最近秩分位点的**切点位置**算错（分位点整体右移）"),
    ("M23", "bander",
     "[r for r, f2 in zip(ks, fr) if qs[i] < f2 <= qs[i + 1]]",
     "[r for r, f2 in zip(ks, fr) if qs[i] <= f2 <= qs[i + 1]]",
     "C17", "【分档器】prod 中间档的左边界 `<` 改 `<=` ⇒ 切点上的格分配变了"),
    ("M24", "bander",
     "[r for r, f2 in zip(ks, fr) if qs[i] <= f2 < qs[i + 1]]",
     "[r for r, f2 in zip(ks, fr) if qs[i] <= f2 <= qs[i + 1]]",
     "C17", "【分档器】alt 中间档的右边界 `<` 改 `<=` ⇒ 切点上的格分配变了"),
    ("M25", "bander",
     "ks = [r for r in ks if d_of(r) != 0.0]",
     "ks = list(ks)",
     "C17", "【分档器】drop 零跨度格被改成空操作"),
    ("M26", "layer",
     "w_off = (n_layer - 1) / 2.0", "w_off = 1.5",
     "C3", "【趋势 MC】权重中心被写死 1.5（3/5 档的权重就错了）"),
]


def _load(path, src=None):
    mod = types.ModuleType("dc2_mut")
    mod.__file__ = os.path.abspath(path)
    exec(compile(src if src is not None
                 else io.open(path, encoding="utf-8").read(), path, "exec"),
         mod.__dict__)
    return mod


def _mirror_dir(skip_name):
    """⚖ 建一个临时目录，把本目录的**全部**文件**软链**进去（跳过被改的那个）。

    ⚖⚠⚖⚖ **为什么要软链**：被测模块用 `os.path.dirname(__file__)` 找同伴
    ⇒ 变异副本单独放一个空目录 ⇒ 它的同伴全找不到 ⇒ **崩**（不是「抓到」）。
    ⇒ 软链 ⇒ `HERE` 仍然对 ⇒ 同伴找得到。
    """
    d = tempfile.mkdtemp(prefix="dc2_mut_")
    for name in os.listdir(HERE):
        src = os.path.join(HERE, name)
        if not os.path.isfile(src) or name == skip_name:
            continue
        try:
            os.symlink(src, os.path.join(d, name))
        except OSError:
            pass
    return d


def _load_with_redirect(tool_src, line, new_path):
    """⚖ 把工具里的某个路径常量指向一份**临时**的副本。

    ⚖⚠⚠⚖ **⛔ 绝不改工作区里的文件** —— 只读工作区，变异副本写在系统临时目录。
    """
    n = tool_src.count(line)
    if n != 1:
        raise AssertionError("定位串命中 %d 处（必须恰好 1 处）：%s" % (n, line))
    s2 = tool_src.replace(line, "%s = %r" % (line.split(" = ")[0], new_path))
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
        raise AssertionError("落点串命中 %d 处（必须恰好 1 处）：%s" % (n, old[:60]))
    return src.replace(old, new, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=TARGET)
    ap.add_argument("--bander", default=BANDER)
    ap.add_argument("--layer", default=LAYER)
    args = ap.parse_args()

    src = io.open(args.target, encoding="utf-8").read()
    bsrc = io.open(args.bander, encoding="utf-8").read()
    lsrc = io.open(args.layer, encoding="utf-8").read()

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
                tmpdir = _mirror_dir("dose_confound_audit.py")
                bpath = os.path.join(tmpdir, "dose_confound_audit.py")
                io.open(bpath, "w", encoding="utf-8").write(bmut)
                mod = _load_with_redirect(src, DCONF_LINE, bpath)
            elif target == "layer":
                lmut = _apply(lsrc, old, new)
                tmpdir = _mirror_dir("dose_layer_audit.py")
                lpath = os.path.join(tmpdir, "dose_layer_audit.py")
                io.open(lpath, "w", encoding="utf-8").write(lmut)
                mod = _load_with_redirect(src, DLAYER_LINE, lpath)
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
            # ⚖⚠⚖⚖ **删临时目录必须在跑完之后**（⛔ 早删 ⇒ 工具加载时找不到同伴 ⇒ 崩）
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
