#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mut_fixed_dose_audit —— `fixed_dose_audit.py` 的**变异台**（修订 244.66）

⚠⚠⚖ **本台架问什么**

  244.66 交的是**固定剂量 / 分层剂量批次的分析管线**（⛔ 不跑批；替身跑通）。
  它的价值全在**判据能红**：口径一旦被改坏、检验被换成别的、区间被换成错的、
  留白被删掉、预算表被掏空 ⇒ 必须**立刻红**。

  ⇒ 台架必须保证：那 12 条判据（F1–F12）**每一条**都**抓得住**对应的实现写错。

⚖⚠⚖⚖⚖ **本轮最要紧的五个错**（台架要能抓住）：

  ① **口径被写死**（代码里不再从预登记读）⇒ 预登记改了也没人知道
  ② **区间被换成错的那个**（两个 CI 相减 / CP95 冒充 Wilson95）
  ③ **检验被换成粗口径**（MC 带去掉 +1 修正 ⇒ p 看着更"确定"）
  ④ **块级被换成轨迹级**（前提独立性未量到 ⇒ 两种口径必须并报）
  ⑤ **留白被删**（没量到的被说成「无差异」）

⚖⚠⚖⚖⚖⚖ **台架怎么跑（与别处一致）**

  1. **基线必须绿**：未变异的源码 ⇒ 真实数据全绿 **且** 自检全绿。
  2. 每条变异**只改一处代码点**；⛔ 不改注释/散文。
  3. 每条变异**必须先证明自己有效**：落点串**确实被替换**（命中恰好 1 处）。
  4. **崩 ≠ 抓到**：被测代码抛异常单列（`[CRASH]`），⛔ 不算抓到。
  5. **两条路都查**（真实数据路 + 自检的畸形夹具路）
  6. ⚖ **自检路的 id 用完整 token**（`T13` 与 `T1` 分得开）

⚖⚠⚖⚖⚖⚖⚖ **244.66 的一个结构性发现**（本台架的设计依据）

  ⚖⚠⚠ **「口径来自预登记」这件事，判据 F2 抓不住**：
     F2 比的是「生效口径 vs 预登记文件」⇒ 如果代码把 `n_bands` 写死成 **4**
     而预登记里恰好也是 4 ⇒ **两边一样 ⇒ F2 照样绿** ⇒ **恒绿**。
  ⚖⇒ 真正抓得住的是**自检的「活体变异」**（T13/T14/T15）：
     ① 复制一份预登记 ⇒ 把 `n_bands` 改成 3 ⇒ 管线必须产出 3 档
     ② 把 `zero_span` 改成 drop ⇒ 格数必须变
     ③ 把 `alpha` 改成 0.01 ⇒ 生效 α 必须变
  ⚖⚠ **判别式**：**「A 等于 B」型判据在「A、B 都写死」时是恒绿的**
     ⇒ 必须有一条**「改了输入就必须变输出」**的**活体**判据。
  ⚖⚠⚠ 同理：判据 F8 里的「MC 带可复算」**不可**调本文件自己的 `mc_band_p`
     （那是从被检对象派生 ⇒ 带算错时一起错 ⇒ 恒绿）
     ⇒ 改成**用外部机械 `interval_audit.wilson_bounds` 内联重算**
     ⇒ 并由自检 T3（已知答案：`ge=0 ⇒ 带下端 = 1/(n+1)`）钉住变换的语义。

⚖⚠⚖⚖⚖⚖ **必须能红**的变异（18 条）

  M1  档边界被写死成 `alt`（预登记说 prod）           ⇒ F2
  M2  档数被写死成 4（不再从预登记读）              ⇒ T13
  M3  预登记机器块缺键被**兜底**（不许抛）           ⇒ T16
  M4  Fisher 的 `d` 传错（`nr-kr` → `nr`）          ⇒ F7
  M5  比例区间 Wilson95 → CP95                      ⇒ F6
  M6  差区间 Newcombe95 → 两个 CI 相减              ⇒ F6
  M7  配对置换被短路（p 恒 1.0）                    ⇒ F8
  M8  MC 带去掉 +1 修正（回到 244.64 的粗口径）       ⇒ F8
  M9  p 的比较符号写死（恒「≥」）                    ⇒ F8
  M10 `zero_fn` 不传（零格数丢失）                   ⇒ F5
  M11 K6b 规则被换成主口径                          ⇒ F5
  M12 改判矩阵被写死                                ⇒ F12
  M13 块级规则被换（全部为正 → 多数为正）             ⇒ F9
  M14 块级那一行被删                                ⇒ F9
  M15 功效预算表被掏空                              ⇒ F10
  M16 留白被删一条                                   ⇒ F11
  M17 分档调用被写死（忽略预登记的 boundary/quantile/n_bands） ⇒ T13
  M18 分位点算法被写死成 `nearest_rank`              ⇒ F3

跑法：
    python3 mut_fixed_dose_audit.py
    python3 mut_fixed_dose_audit.py --selftest
退出码：0 = 全部被抓住；1 = 有变异存活 / 基线不绿。
"""

import argparse
import contextlib
import io
import os
import re
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "fixed_dose_audit.py")

# ⚖ (编号, 落点旧串, 落点新串, 期望红的那条判据/自检 token, 它踩的是哪一支)
MUTATIONS = [
    ("M1",
     '        self.boundary = raw["boundary"]',
     '        self.boundary = "alt"',
     "F2", "档边界被**写死**成 alt（预登记说 prod）"),
    ("M2",
     '        self.n_bands = int(raw["n_bands"])',
     '        self.n_bands = 4',
     "T13", "档数被**写死**成 4（不再从预登记读 ⇒ 预登记改了也没人知道）"),
    ("M3",
     '    missing = [k for k in PREREG_KEYS if k not in raw]\n'
     '    if missing:\n'
     '        raise HardFail("预登记机器块缺键：%s（⛔ 不许用默认值兜底）"\n'
     '                       % ", ".join(missing))',
     '    missing = []',
     "T16", "预登记机器块**缺键被兜底**（⛔ 不许抛）"),
    ("M4",
     "        pf, _po = armv().fisher_exact_two_sided(kw, nw - kw, kr, nr - kr)",
     "        pf, _po = armv().fisher_exact_two_sided(kw, nw - kw, kr, nr)",
     "F7", "Fisher 的 `d` 传错（`nr-kr` 写成 `nr`）"),
    ("M5",
     "        wlw, wuw = iaud().wilson_bounds(kw, nw)\n"
     "        wlr, wur = iaud().wilson_bounds(kr, nr)",
     "        wlw, wuw = iaud().cp95(kw, nw)\n"
     "        wlr, wur = iaud().cp95(kr, nr)",
     "F6", "比例区间 Wilson95 → CP95（K12 写死 Wilson95）"),
    ("M6",
     "        nc = iaud().newcombe_diff(kw, nw, kr, nr)",
     "        nc = iaud().naive_diff(kw, nw, kr, nr)",
     "F6", "差区间 Newcombe95 → **两个 CI 相减**（统计上是错的）"),
    ("M7",
     "        p_perm, obs, ge, n_perm = (DL.paired_perm_geom(diffs, N_PERM, MC_SEED)\n"
     "                                   if paired else (1.0, 0, 0, N_PERM))",
     "        p_perm, obs, ge, n_perm = (1.0, 0, 0, N_PERM)",
     "F8", "配对置换被**短路**（p 恒 1.0）"),
    ("M8",
     "    return ((lo * n_perm + 1.0) / d, (hi * n_perm + 1.0) / d)",
     "    return (lo, hi)",
     "F8", "MC 带去掉 **+1 修正**（回到 244.64 的粗口径 ⇒ p 看着更「确定」）"),
    ("M9",
     '    return "<" if p < alpha else "≥"',
     '    return "≥"',
     "F8", "p 的**比较符号写死**（244.65 的坑：印出「p=0.0500 ≥ 0.05」）"),
    ("M10",
     "            v_main = DL.layer_verdicts(cells_by_tid, DL.cell_sign_p9, DL.cell_zero_p9)",
     "            v_main = DL.layer_verdicts(cells_by_tid, DL.cell_sign_p9, None)",
     "F5", "`zero_fn` 不传 ⇒ 零格数丢失（零格恒 False 的信息没了）"),
    ("M11",
     "            v_alt = VS.p9delta_per_tid(cells)",
     "            v_alt = v_main",
     "F5", "K6b（另一条多数规则）被换成主口径 ⇒ 两条规则不再并报"),
    ("M12",
     '            mat["%s%s" % ("T" if a else "F", "T" if b else "F")] += 1',
     '            mat["FF"] += 1',
     "F12", "改判矩阵被写死"),
    ("M13",
     "        out.append((blk, cpre().block_is_pos(blk, signs)))",
     "        out.append((blk, any(signs[t] > 0 for t in blk)))",
     "F9", "块级规则被换（「全部为正」→ 「任一为正」⇒ 块级口径变了）"),
    ("M14",
     '        RP.append("      · 块级（K13，%d 块中 %d 块可评）：w %d/%d ｜ rand %d/%d"\n',
     '        RP.append("      · 块级xx（K13，%d 块中 %d 块可评）：w %d/%d ｜ rand %d/%d"\n',
     "F9", "块级那一行的**标记**被改（K13 要求块级与轨迹级**并报**）"),
    ("M15",
     '    for ln in A["budget"]["lines"]:\n        RP.append(ln)\n',
     "",
     "F10", "功效预算表被掏空"),
    ("M16",
     '    ("【B7】**远端 tokenizer 快照的内容指纹** / **`pos_frac` 只在 0.5 取过值**",\n'
     '     "未量到"),\n',
     "",
     "F11", "留白被删一条（没量到的被说成「无差异」）"),
    ("M17",
     "        qs, bands = DC.dose_bands_v(ks, fr, boundary=cfg.boundary,\n"
     "                                    quantile=cfg.quantile, n_bands=cfg.n_bands)",
     '        qs, bands = DC.dose_bands_v(ks, fr, boundary="prod",\n'
     '                                    quantile="inclusive", n_bands=4)',
     "T13", "分档调用被**写死**（预登记的 boundary/quantile/n_bands 全被忽略）"),
    ("M18",
     "        qs, bands = DC.dose_bands_v(ks, fr, boundary=cfg.boundary,\n"
     "                                    quantile=cfg.quantile, n_bands=cfg.n_bands)",
     "        qs, bands = DC.dose_bands_v(ks, fr, boundary=cfg.boundary,\n"
     "                                    quantile=\"nearest_rank\", n_bands=cfg.n_bands)",
     "F3", "分位点算法被写死成 `nearest_rank`（预登记说 inclusive）"),
]


def _load(path, src=None):
    mod = types.ModuleType("fda_mut")
    mod.__file__ = os.path.abspath(path)
    exec(compile(src if src is not None
                 else io.open(path, encoding="utf-8").read(), path, "exec"),
         mod.__dict__)
    return mod


def run_audit(mod):
    """⚖ 真实数据路：跑完整的「读预登记 → 建管线 → 出报告」。"""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            raw = mod.read_prereg(mod.PREREG)
            krows = mod.prereg_k_rows(mod.PREREG)
            cfg = mod.Cfg(raw)
            A = mod.build_all(cfg)
            _RP, R = mod.build_report(A, cfg, raw, krows)
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, e)
    return R, None


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=TARGET)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    src = io.open(args.target, encoding="utf-8").read()

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
    for mid, old, new, want, why in MUTATIONS:
        n_hit = src.count(old)
        if n_hit != 1:
            invalid.append((mid, "落点串命中 %d 处（必须恰好 1 处）" % n_hit))
            print("[SKIP] %s 落点串命中 %d 处 ⇒ 变异**无效**（%s）" % (mid, n_hit, why))
            continue
        msrc = src.replace(old, new, 1)
        # ⚖⚠⚖⚠ **变异必须先证明自己有效**：切完后源码**还要能解析**
        #   （切坏语法 ⇒ 模块加载即崩 ⇒ 这不是「抓到」，是变异**无效**）
        #   ⛔ 崩 ≠ 抓到：加载失败**不许**算进 caught。
        try:
            mod = _load(args.target, msrc)
        except SyntaxError as e:
            invalid.append((mid, "切完后语法错（%s）⇒ 变异**无效**" % e))
            print("[SKIP] %s 切完后语法错 ⇒ 变异**无效**（%s）" % (mid, e))
            continue
        R, err = run_audit(mod)
        sf, serr = run_selftest_fails(mod)
        if err or serr:
            crashed.append((mid, err or serr))
            print("[CRASH] %s 崩了：%s（⚠ 崩 ≠ 抓到）" % (mid, err or serr))
            continue
        red = set(c for c, v in R.items() if not v)
        by = []
        if want in red:
            by.append("真实数据路")
        if want in sf:
            by.append("自检路（活体变异/畸形夹具）")
        # ⚖⚠⚠⚠⚠ **顺序要紧**：先判「什么都没变」⇒ 那是**无效**变异（no-op），
        #   **不是**「存活」⇒ 否则台架会把「等价变异」记成「判据抓不住」（冤枉判据）
        if not red and not sf:
            invalid.append((mid, "真实路与自检都没变 ⇒ 变异**无效**（等价变异）"))
            print("[SKIP] %s 真实路与自检均未变化 ⇒ 变异**无效**（等价变异）" % mid)
            continue
        if not by:
            survived.append((mid, want, "真实路红=%s；自检失败=%s"
                             % (",".join(sorted(red)) or "无",
                                ",".join(sorted(sf)) or "无")))
            print("[SURVIVED] %s 期望 %s 红，实际 真实路=%s 自检=%s ⇒ **变异存活**"
                  % (mid, want, ",".join(sorted(red)) or "无",
                     ",".join(sorted(sf)) or "无"))
            continue
        caught.append(mid)
        print("[CAUGHT] %s ⇒ %s 红（%s；经 %s）"
              % (mid, want, why, "、".join(by)))

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
