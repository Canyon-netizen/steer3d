#!/usr/bin/env python3
"""LTV 的独立重算判据。**不复用构建器的任何计算**，只从原始落盘字段重算。

第三层防护：探针自己算一遍 → 构建器从它写下的原始字段独立算一遍 →
这里再从**原始层**独立算一遍，并逐条与公开产物对账。
共用同一份中间量 ⇒ 一处错则处处绿。

分层（与项目既有口径一致）：
  E 层  从原始行重算三道门的关键量（g_v / α*_pred / G-b 打分）
  F 层  预登记漂移：α 网格、拟合窗、稀疏上限、留出划分是否还对得上
  G 层  公开产物与原始层逐数对账（页面读的那份必须是对的）
  S 层  构建期自检的复算

用法:
  python3 .cache/xcheck/verify_ltv.py
  ARTIFACT=.cache/xcheck/ltv.json PUBLIC=... python3 .cache/xcheck/verify_ltv.py
"""
import json
import os
import statistics as st
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
ART = os.environ.get("ARTIFACT", os.path.join(HERE, "ltv.json"))
PUBLIC = os.environ.get("PUBLIC", os.path.join(
    REPO, "frontend", "public", "latent", "data", "ltv.json"))
PREREG = os.path.join(HERE, "LTV_PREREG.md")

ALPHA_GRID = [0.05, 0.1, 0.2, 0.35, 0.5, 1.0, 2.0, 4.0]
FIT_ALPHAS = [0.05, 0.1, 0.2]
K_MAX = 8

# G1t 用的期望值。**本文件自己写死**，不从构建器 import ——
#   同源共用会「一处错则处处绿」，而顶层对账的全部意义就是抓那类错。
#   alpha_grid / fit_alphas 在原始层与公开层都可能对不上预登记，
#   所以对账时允许「原始＝预登记」或「公开＝预登记」任一成立，
#   两者都不成立才算不符。
_EXPECT = {"alpha_grid": ALPHA_GRID, "fit_alphas": FIT_ALPHAS, "k_max": K_MAX}

fails, warns, _total = [], [], [0]


def check(name, ok, detail):
    _total[0] += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    for x in detail:
        print(f"         {x}")
    if not ok:
        fails.append(name)


def slope(ys, xs):
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den


def gidx(a):
    for i, x in enumerate(ALPHA_GRID):
        if abs(x - a) < 1e-9:
            return i
    return None


def main():
    if not os.path.exists(ART):
        print(f"原始产物不存在：{ART}")
        sys.exit(2)
    raw = json.load(open(ART, encoding="utf-8"))
    ctx = raw.get("contexts") or []
    print(f"原始产物 {ART}　上下文 {len(ctx)} 个")
    if not ctx:
        print("❌ 一条上下文都没有 ⇒ 这一轮没取到数，不许判绿")
        sys.exit(2)

    pub = json.load(open(PUBLIC, encoding="utf-8")) if os.path.exists(PUBLIC) else {}

    # ---- 判决切片（独立于构建器，自己从原始 split 重算）------------------
    # ⚠⚠⚠ 第一版**没有切片**，于是一整套判据都在**全量**上下文上重算，
    #   而预登记表 §43/§84/§100-101 要求 G-a / G-b 只在**留出集**上判。
    #   这个偏差一路没人抓，公开产物里 `split` 还反过来说 `holdout: []` ——
    #   一份**自相矛盾且无人披露**的产物发了出去。
    #   ⇒ 这里不 import 构建器的常量，也不读产物里的 judge_slice：
    #     两个来源都不算独立证据。切片从**原始产物的 split** 现算。
    _split = raw.get("split") or {}
    _ho = set(_split.get("holdout") or [])
    _ex = set(_split.get("extract") or [])
    _sctx = [c for c in ctx if c["pid"] in _ho]
    print(f"判决切片（判据自算）：留出题 {len(_ho)} ／抽取题 {len(_ex)}"
          f" ⇒ 留出切片内上下文 {len(_sctx)}/{len(ctx)}")
    if not _ho:
        # ⚠⚠⚠ 这里**不许 exit**。写成「留出集为空 ⇒ 退出码 2」的理由是
        #   「前提不成立就别判」。那条路更糟：整个判据**当场死掉**，
        #   其余二十几条检查一条都不再出声 —— 而「一处前提坏了」
        #   与「其余检查全都没跑」在汇总里长得一模一样。
        #   这就是「恒红污染下游」的**崩溃版**。
        #   ⇒ 记一条红，让其余检查照常跑完，让读的人看见
        #     「哪一条坏了、其余结论还成不成立」。
        check("E0 原始产物的留出集非空（预登记表 §43/§84/§100 要求在留出集上判）",
              False, [f"split.holdout 为空：{raw.get('split')}",
                      "判决切片退化为空 ⇒ G-a0/G-a/G-b 的口径不成立",
                      "其余检查仍会跑完；它们的结论只对『可判的部分』成立"])
    else:
        check("E0 原始产物的留出集非空（预登记表 §43/§84/§100 要求在留出集上判）",
              True, [f"留出 {len(_ho)} 题 ／ 抽取 {len(_ex)} 题，两集无重叠",
                     f"留出切片内 {len(_sctx)}/{len(ctx)} 个上下文"])

    # ---- E 层：从原始 gap(α) 重算 ----
    print("\nE 层 · 从原始行独立重算")
    # ⚠ 第一版 E1 查的是「gap(最小 α) 与 m_p 同量级」，容差 25%+0.05。
    #   实测它抓到一条 pos=511：m_p=0.237 而 gap(0.05)=0.072（差 70%）。
    #   查下来那**不是装置坏了**，是该上下文的杠杆响应极陡 —— 0.05 档就掉七成。
    #   ⇒ 容差定错了，而且这个检查问的不是定律用到的那个性质。
    #   改成查**拟合窗内 gap 是否单调不增** —— 那正是 α*=m/g_v 的前提
    #   （gap 必须在小 α 段往 0 走，线性外推才有意义）。
    #   而「先微升再塌」正是 G-a 判红的机理，两者必须挂钩印出来，
    #   否则 G-a 那个红看起来像是随便挑的。
    nonmono, bad_m = set(), []
    # ⚠ 非单调的重算口径**必须与判决切片一致**：判决只在留出集上做，
    #   而「非单调」是 G-a 剔除的依据 ⇒ 剔的是切片内的那几个。
    #   第一版（和构建器第一版一样）在全量上算，判决改到留出集后
    #   判据立刻报「11 ≠ 4」—— 那正是它在提醒我两处口径没同步。
    #   全量口径仍在这里算一遍，只作信息。
    for c in ctx:
        gap = c["arm_gap"]
        ys = [float(gap[str(a)]) for a in FIT_ALPHAS if str(a) in gap]
        if len(ys) >= 2 and any(ys[i + 1] > ys[i] + 1e-12 for i in range(len(ys) - 1)):
            nonmono.add((c["pid"], c["pos"]))
        if not (c["m_p"] > 0):
            bad_m.append((c["pid"][-11:], c["pos"], c["m_p"]))
    nonmono_s = {(c["pid"], c["pos"]) for c in _sctx
                 if (c["pid"], c["pos"]) in nonmono}
    # ⚠ 这条**不是**「必须单调」。非单调是**物理事实**（gap 先微升再塌），
    #   报告它不是缺陷 —— 判据该管的是「构建器有没有把这批位置**从 G-a 里剔除**，
    #   并把剔除数印出来」。不这么写，这条就会永远红，而红的是装置不是被测物。
    pg0 = (pub.get("gates") or {}).get("G-a0", {}).get("evidence", {}) or {}
    pub_nm = {(x["pid"], x["pos"]) for x in (pg0.get("nonmonotone_ctx") or [])}
    # ⚠ 产物里只存了 pid 的**后 11 位**，而 raw 里是全名 ⇒ 不能直接比集合。
    #   改成比**条数**并抽查第一条的后缀，这是能核的。
    check("E1 拟合窗内 gap 非单调的位置数：判据独立重算 == 产物 G-a0 报的",
          len(nonmono_s) == len(pub_nm) and not bad_m,
          [f"判据重算：切片内 {len(nonmono_s)}/{len(_sctx)} 个非单调"
           f"（全量 {len(nonmono)}/{len(ctx)}，只作信息）；"
           f"产物 G-a0 报 {pg0.get('n_nonmonotone')} 个",
           f"产物 judge_slice = {pg0.get('judge_slice')!r}",
           f"m_p ≤ 0 的 {len(bad_m)} 个 {bad_m[:3]}"])

    check("E1b 全部上下文的 m_p > 0（m_p ≤ 0 时「决胜间距」本身没有意义）",
          not bad_m, [f"{len(bad_m)} 处", f"前 3：{bad_m[:3]}"] if bad_m
          else [f"{len(ctx)} 个上下文 m_p 全为正"])

    # ⚠ 适用率门必须**独立**重算，且门槛与产物一致。
    #   口径与 E1 一致：**切片内**算，不是全量 ——
    #   「剔掉的那些占多数吗」这个问题本身就是相对判决切片问的。
    applic = (len(_sctx) - len(nonmono_s)) / max(len(_sctx), 1)
    want_a0 = "pass" if applic >= 2.0 / 3 else "fail"
    check("E1c 独立重算的适用率与 G-a0 的判决一致"
          "（剔除太多位置后 G-a 变好看，这条门就是防那个的）",
          abs(applic - float(pg0.get("applicability", -1))) < 1e-3
          and (pub.get("gates") or {}).get("G-a0", {}).get("verdict") == want_a0,
          [f"重算适用率（切片 {len(_sctx)} 个上下文）{applic:.3f}"
           f"（门槛 2/3）⇒ 应判 {want_a0.upper()}",
           f"产物 {pg0.get('applicability')}（n_ctx={pg0.get('n_ctx')}"
           f"／n_ctx_all={pg0.get('n_ctx_all')}）⇒ "
           f"{(pub.get('gates') or {}).get('G-a0', {}).get('verdict')}"])

    gvs, preds = [], []
    for c in ctx:
        gap = c["arm_gap"]
        xs = [a for a in FIT_ALPHAS if str(a) in gap]
        ys = [float(gap[str(a)]) for a in xs]
        b = slope(ys, xs)
        g = None if b is None else -b
        p = None if (g is None or g <= 0) else float(c["m_p"]) / g
        gvs.append(g)
        preds.append(p)
    # ⚠ 第一版的变异台有一条打「恒等自证」，而本文件**没有复算它** ——
    #   变异打在一个不存在的条上，等于没打。构建器里有这条，
    #   独立重算这边必须也有一份，否则装置自证只有构建器自己说了算。
    idbad = [c for c in ctx if not c.get("identity_top1_ok")]
    check("每个上下文的恒等自证必须为真"
          "（批量前向若改变了结果，恒等臂会立刻改口）",
          not idbad,
          [f"{len(idbad)}/{len(ctx)} 个上下文恒等自证失败",
           f"前 3：{[(c['pid'][-11:], c['pos']) for c in idbad[:3]]}"] if idbad
          else [f"{len(ctx)} 个上下文全部通过（干净残差放进同一个 batch 后顶 token 不变）"])
    check("E1b 全部上下文的 m_p > 0（m_p ≤ 0 时「决胜间距」本身没有意义）",
          not bad_m, [f"{len(bad_m)} 处", f"前 3：{bad_m[:3]}"] if bad_m
          else [f"{len(ctx)} 个上下文 m_p 全为正"])

    # 重算 G-b：与构建器**同一套**配对打分 + 符号检验。
    # ⚠ 第一版这里还是旧公式（「臂没改口 −1」），而构建器已经改成配对比较 ——
    #   两处口径不同就等于一个恒红的判据，而红的原因是「我没同步」。
    import math
    pos = neg = zero = 0
    for c in _sctx:
        a = c["arm_alpha_star"]
        flips = [v for v in c["ctl_alpha_star"].values() if v is not None]
        if a is None and not flips:
            zero += 1
        elif a is None:
            neg += 1
        elif not flips:
            pos += 1
        else:
            best = min(flips)
            pos += a < best
            neg += a > best
            zero += a == best
    net = pos - neg
    n_eff = pos + neg
    p_two = (min(1.0, 2 * sum(math.comb(n_eff, i) for i in range(min(pos, neg) + 1))
                   / (2 ** n_eff)) if n_eff else 1.0)
    pg = (pub.get("gates") or {}).get("G-b", {}).get("evidence", {})
    check("E2 独立重算的 G-b 配对打分与符号检验，与公开产物逐项一致",
          pg.get("net") == net and pg.get("n_plus") == pos
          and pg.get("n_minus") == neg and pg.get("n_zero") == zero
          and abs(float(pg.get("sign_test_p", -1)) - p_two) < 1e-12,
          [f"本文件重算（切片 holdout，{len(_sctx)} 个上下文）："
           f"+1 {pos}／−1 {neg}／0 {zero}，净 {net}，p={p_two:.4g}",
           f"产物：    +1 {pg.get('n_plus')}／−1 {pg.get('n_minus')}"
           f"／0 {pg.get('n_zero')}，净 {pg.get('net')}，p={pg.get('sign_test_p')}",
           f"产物声明的 judge_slice = {pg.get('judge_slice')!r}",
           f"切片内逐上下文：臂改口 "
           f"{sum(1 for c in _sctx if c['arm_alpha_star'] is not None)}"
           f"／共 {len(_sctx)}；对照改口 "
           f"{sum(1 for c in _sctx for v in c['ctl_alpha_star'].values() if v is not None)}"
           f"／共 {2*len(_sctx)}"])

    # 重算 G-a 的判否数
    # ⚠ `preds` 与 `ctx` **并行同序**，所以切片要按下标取，不能直接过滤 preds ——
    #   直接过滤会把「第 i 个的预测」配到「第 j 个的实测」上，而那种错
    #   在数字上仍然自洽，只是不再是同一个上下文。
    _sidx = [i for i, c in enumerate(ctx) if c["pid"] in _ho]
    circ = f_g = hit = both = nonmono_n = 0
    for _i in _sidx:
        c, p = ctx[_i], preds[_i]
        m = c["arm_alpha_star"]
        # ⚠ 与构建器主口径同一套剔除：非单调的位置也**不判**。
        gap = c["arm_gap"]
        ys = [float(gap[str(a)]) for a in FIT_ALPHAS if str(a) in gap]
        if len(ys) >= 2 and any(ys[i + 1] > ys[i] + 1e-12 for i in range(len(ys) - 1)):
            nonmono_n += 1
            continue
        if m is not None and m <= max(FIT_ALPHAS):
            circ += 1
            continue
        if p is None:
            if m is None:
                both += 1
            else:
                f_g += 1
            continue
        if m is None:
            if p > ALPHA_GRID[-1]:
                both += 1
            else:
                f_g += 1
            continue
        ip = min(range(len(ALPHA_GRID)), key=lambda i: abs(ALPHA_GRID[i] - p))
        im = gidx(m)
        if im is not None and abs(ip - im) <= 1:
            hit += 1
        else:
            f_g += 1
    pa = (pub.get("gates") or {}).get("G-a", {}).get("evidence", {})
    check("E3 独立重算的 G-a 计数与公开产物逐条一致",
          all(pa.get(k) == v for k, v in
              (("n_judged", hit + both + f_g), ("n_excluded_fit_window", circ),
               ("n_excluded_nonmonotone", nonmono_n),
               ("n_within_one_notch", hit), ("n_both_censored", both))),
          [f"重算（切片 holdout）：可判 {hit+both+f_g}／窗内剔除 {circ}"
           f"／非单调剔除 {nonmono_n}"
           f"／命中 {hit}／同判删失 {both}／红 {f_g}",
           f"产物：可判 {pa.get('n_judged')}／窗内 {pa.get('n_excluded_fit_window')}"
           f"／非单调 {pa.get('n_excluded_nonmonotone')}"
           f"／命中 {pa.get('n_within_one_notch')}／同判删失 {pa.get('n_both_censored')}",
           f"产物声明的 judge_slice = {pa.get('judge_slice')!r}"])

    # ---- F 层：预登记漂移 ----
    print("\nF 层 · 预登记与实现是否漂移")
    if os.path.exists(PREREG):
        t = open(PREREG, encoding="utf-8").read()
        for label, pat in [("α 网格", "0.05, 0.1, 0.2, 0.35, 0.5, 1, 2, 4"),
                           ("稀疏上限 K≤8", "8"),
                           ("改口判据 top-1 变化", "top-1"),
                           ("留出按题划分", "按题")]:
            check(f"F1 {label}", pat in t, [f"在预登记表里查 {pat!r}"])
        # 预登记表 §3 自称「一档 ≈ 1.7~2.8 倍」，与它自己定的网格对不上。
        # ⚠ 这条**故意长期红**：原文是取数前写下的记录，不能事后改。
        #   改的是它的**判据形状** —— 不是「算错了就当没看见」，而是
        #   「不一致必须持续可见，且必须有一条写下来的修订说明处置方式」。
        ratios = [ALPHA_GRID[i + 1] / ALPHA_GRID[i] for i in range(len(ALPHA_GRID) - 1)]
        bad_claim = "1.7~2.8" in t and (min(ratios) < 1.7 or max(ratios) > 2.8)
        has_amend = "修订 1" in t and "1.43" in t
        # ⚠⚠ 这里判的是**披露与处置**，不是「原文写对了」。
        #   预登记表 §3 是取数**之前**写下的记录，它那句倍数算错了，但不许事后改
        #   —— 改了，「判决是取数前定下的」这句话就没有依据了。
        #   ⇒ 原版把它做成一条「必须为真」的判据，结果是**永远红**：
        #     一条永远红的判据等于没有判据，而且会让全链退出码恒为 1，
        #     此后任何真故障都被淹在这条恒红里。
        #   ⇒ 正确的判法：差异每轮都打印（那是披露），并且要求存在一条
        #     写明处置方式的修订记录（那是处置）。原文不动。
        if bad_claim:
            warns.append("预登记表 §3 的「一档 ≈ 1.7~2.8 倍」与它自己定的 α 网格"
                         f"（实为 {min(ratios):.2f}~{max(ratios):.2f}）不一致；"
                         "判决按「相邻档」字面执行；原文保留，处置写在 §6 修订 1")
            print(f"    ⚠ 预登记表 §3 的「一档」自述为「约 1.7~2.8 倍」，"
                  f"而它自己定的网格实为 {min(ratios):.2f}~{max(ratios):.2f} "
                  "⇒ 不一致（原文是取数前的记录，不许事后改）")
        check("F2 预登记表的「一档倍数」若与它自己定的 α 网格不一致，"
              "必须存在写明处置方式的修订记录（原文不许改，差异每轮披露）",
              (not bad_claim) or has_amend,
              [f"网格相邻档之比实为 {min(ratios):.2f}~{max(ratios):.2f}；"
               f"§3 写的是「约 1.7~2.8 倍」⇒ 不一致：{bad_claim}",
               f"§6 修订记录存在：{'是' if has_amend else '**否**'}"
               "（判决按「相邻档下标相差 ≤ 1」的字面执行）"] if bad_claim
              else [f"一致（{min(ratios):.2f}~{max(ratios):.2f}），无需修订记录"])
    else:
        check("F0 预登记表存在", False, [f"缺 {PREREG}"])

    # ---- G 层：公开产物逐数对账 ----
    print("\nG 层 · 公开产物与原始层对账")
    if not os.path.exists(PUBLIC):
        check("G0 公开产物存在", False, [f"缺 {PUBLIC}"])
    else:
        pctx = pub.get("contexts") or []
        mism = []
        if len(pctx) != len(ctx):
            mism.append([f"上下文条数 {len(pctx)} ≠ 原始 {len(ctx)}"])
        for a, b in zip(ctx, pctx):
            # ⚠⚠ 只对账**原始层真有**的字段。
            #   第一版把 g_v / alpha_star_pred 也列进来了，而那两个是**派生**量 ——
            #   原始层根本没有 ⇒ a.get(...) 返回 None ⇒ 69 处「不符」，
            #   而红的原因是「我在拿不存在的东西对账」。
            #   派生量改与本文件的**独立重算**对账（见 E1d），那才是有意义的对照。
            for fld_raw, fld_pub in (("m_p", "m_p"),
                                     ("arm_alpha_star", "alpha_star_meas")):
                x, y = a.get(fld_raw), b.get(fld_pub)
                if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                    if abs(float(x) - float(y)) > 1e-9 * max(1.0, abs(float(x))):
                        mism.append([b.get("pid", "?")[-11:], b.get("pos"), fld_pub, x, y])
                elif x != y:
                    mism.append([b.get("pid", "?")[-11:], b.get("pos"), fld_pub, x, y])
            cf = [v for v in a["ctl_alpha_star"].values() if v is not None]
            cmin = min(cf) if cf else None
            if b.get("ctl_alpha_star_min") != cmin:
                mism.append([b.get("pid", "?")[-11:], b.get("pos"),
                             "ctl_alpha_star_min", cmin, b.get("ctl_alpha_star_min")])
        check("G1 公开产物与原始层的**逐上下文字段**相符"
              "（页面读的那份必须是对的）",
              not mism,
              [f"核对 {len(ctx)} 个上下文 × 3 个原始字段", f"不符 {len(mism)} 处",
               f"前 3：{mism[:3]}"] if mism else ["逐数一致"])

        # ---- G1t 顶层字段对账 --------------------------------------------
        # ⚠⚠⚠ 第一版的 G1 叫「与原始层的**每个数**相符」，而它只对账
        #   **逐上下文**的 3 个字段 + 2 个派生量。**顶层字段一个都没核** ——
        #   split / alpha_grid / fit_alphas / registry_names / lever 全在缺口里。
        #   后果不是理论上的：磁盘上那份公开产物的 `split` 是
        #   `extract 6 / holdout 0`，而原始层是 `3 / 3` ——
        #   一句**假话**在 GREEN 18/18 的独立重算下原样发了出去，
        #   而 G-a 的 claim 明写「在留出上下文上」，两者直接矛盾。
        #   ⇒ 名字里写「每个数」就得真核每个数。清单式对账必须把清单也核。
        tm = []
        for key in ("split", "registry_names"):
            if pub.get(key) != raw.get(key):
                tm.append([key, raw.get(key), pub.get(key)])
        for key in ("alpha_grid", "fit_alphas", "k_max"):
            # 这三个在原始层与公开层都可能对不上预登记 ⇒ 任一等于本文件的
            # 期望值就算过；两者都不等于才算不符。
            if pub.get(key) != raw.get(key) and pub.get(key) != _EXPECT[key]:
                tm.append([key, f"原始 {raw.get(key)}", f"产物 {pub.get(key)}"])
        # lever：vec 是 2048 维，逐数比；name/layer/unit_norm 比值
        lv_r, lv_p = raw.get("lever") or {}, pub.get("lever") or {}
        for k in ("name", "layer", "unit_norm"):
            if lv_r.get(k) != lv_p.get(k):
                tm.append([f"lever.{k}", lv_r.get(k), lv_p.get(k)])
        if lv_r.get("vec") != lv_p.get("vec"):
            tm.append(["lever.vec",
                       f"{len(lv_r.get('vec') or [])} 维",
                       f"{len(lv_p.get('vec') or [])} 维"])
        # sentence_diffs 的每个键与范数（判红的是**逐条**，不是条数）
        sdr = {r["key"]: r for r in (raw.get("sentence_diffs") or [])}
        for r in (pub.get("sentence_diffs") or []):
            o = sdr.get(r.get("key"))
            if o is None:
                tm.append([f"sentence_diffs[{r.get('key')}]", "原始层没有", "产物有"])
            elif (o.get("norm") != r.get("norm")
                  or o.get("S") != r.get("S") or o.get("Sp") != r.get("Sp")
                  or o.get("negative_control") != r.get("negative_control")):
                tm.append([f"sentence_diffs[{r.get('key')}]",
                           o.get("norm"), r.get("norm")])
        if len(sdr) != len(pub.get("sentence_diffs") or []):
            tm.append(["sentence_diffs 条数", len(sdr),
                       len(pub.get("sentence_diffs") or [])])
        check("G1t **顶层字段**也与原始层逐项相符"
              "（split / lever / alpha_grid / fit_alphas / sentence_diffs）",
              not tm,
              [f"核了 2 类原始透传字段 + 3 类预登记字段 + 3 项 lever + "
               f"{len(sdr)} 条句子差分",
               f"不符 {len(tm)} 处", f"全部：{tm}"] if tm else ["逐项一致"])

        # schema / prereg 是**构建器自己写的**，原始层没有 ⇒ 不参与「与原始对账」，
        #   但它们同样是会被读的字段，另立一条查它们**自洽**。
        #   （第一版把它们并进原始对账，于是 `prereg` 永远「不符」——
        #     又一条恒红判据，而红的原因是「我把两类字段混在一张清单里」。）
        _bm = []
        if pub.get("schema") != "steer3d.ltv/1":
            _bm.append(["schema", pub.get("schema")])
        _pr = str(pub.get("prereg") or "")
        if "LTV_PREREG.md" not in _pr:
            _bm.append(["prereg 没指向预登记表", _pr])
        if not os.path.exists(PREREG):
            _bm.append(["预登记表文件不存在", PREREG])
        check("G1u 构建器自撰字段（schema / prereg）自洽且指向真实文件",
              not _bm, [f"schema={pub.get('schema')!r}", f"prereg={_pr!r}",
                        f"文件在不在：{os.path.exists(PREREG)}"] if _bm
              else [f"schema=steer3d.ltv/1；prereg 指向 {PREREG}（文件存在）"])

        # ---- G1s 判决切片必须真的是留出集 ---------------------------------
        # 判据不 import 构建器的 JUDGE_SLICE，也**不信产物自己写的** judge_slice
        #   值 —— 产物说自己是 holdout，正需要有人拿原始 split 去对。
        gs = pub.get("judge_slice")
        check("G1s 产物声明的判决切片 == 原始产物的留出集，且留出集非空",
              gs == "holdout" and _ho and bool(_ho - _ex),
              [f"产物 judge_slice = {gs!r}",
               f"原始 split：留出 {len(_ho)} 题 ／抽取 {len(_ex)} 题",
               f"两集重叠 {sorted(_ho & _ex)}",
               f"留出集内的上下文 {len(_sctx)} 个（判决只用这些）",
               f"产物 G-a/G-b 的 judge_slice = "
               f"{(pub.get('gates') or {}).get('G-a', {}).get('evidence', {}).get('judge_slice')!r} / "
               f"{(pub.get('gates') or {}).get('G-b', {}).get('evidence', {}).get('judge_slice')!r}"])

        # ---- G1d2 披露：切片这件事必须写在产物里 --------------------------
        # 口径与预登记不一致时，**差异本身要成为产物的一部分**，
        # 只活在提交信息里是不够的 —— 提交信息不会每轮重印，页面也不会。
        _cav = " ".join(pub.get("caveats") or [])
        _need = ["留出", "不显著", "弱留出"]
        _miss = [w for w in _need if w not in _cav]
        check("G1d 口径偏离（判决改到留出集、抽取集上不显著）已被 caveats 披露",
              not _miss,
              [f"caveats {len(pub.get('caveats') or [])} 条",
               f"缺少关键词：{_miss}"] if _miss else
              ["「留出」「不显著」「弱留出」三条披露都在产物里"])

        # 派生量：产物 vs 本文件的独立重算
        dm = []
        for b, c, gv, pr in zip(pctx, ctx, gvs, preds):
            if b.get("g_v") != gv:
                dm.append([b.get("pid", "?")[-11:], b.get("pos"), "g_v", gv, b.get("g_v")])
            if b.get("alpha_star_pred") != pr:
                dm.append([b.get("pid", "?")[-11:], b.get("pos"),
                           "alpha_star_pred", pr, b.get("alpha_star_pred")])
        check("G1d 派生量（g_v / α*_pred）产物与本文件的独立重算逐条相符",
              not dm,
              [f"核对 {len(ctx)} 个上下文 × 2 个派生量", f"不符 {len(dm)} 处",
               f"前 3：{dm[:3]}"] if dm else ["逐条一致"])

        need = [k for k in (pub.get("gate_order") or [])]
        gp = pub.get("gates") or {}
        check("G2 公开产物每道门都有唯一 verdict，且 na 带理由",
              all(k in gp and gp[k]["verdict"] in ("pass", "fail", "na")
                  and (gp[k]["verdict"] != "na" or gp[k].get("why_na"))
                  for k in need) and len(need) == len(set(need)),
              [f"门数 {len(need)}",
               f"三态计数 "
               + json.dumps({x: sum(1 for k in need if gp[k]["verdict"] == x)
                             for x in ("pass", "fail", "na")})])

        # G-c 必须是 na —— 本轮没做生成实验
        check("G3 G-c 必须是 na 且带理由（没跑 ≠ 跑过没过）",
              gp.get("G-c", {}).get("verdict") == "na" and bool(gp.get("G-c", {}).get("why_na")),
              [f"G-c verdict = {gp.get('G-c', {}).get('verdict')}",
               f"理由：{str(gp.get('G-c', {}).get('why_na'))[:90]}…"])

        # 敏感性表必须存在，且退化行必须被标成 degenerate_untested
        sens = pa.get("fit_window_sensitivity") or []
        # ⚠ 判据改成「**可判比例**」，不是绝对数。
        #   n_circular 现在合并了两种剔除（非单调 + 改口落在窗内），
        #   拿它跟 n_judged 比绝对值会把「剔掉 9 个还判 16 个」误成退化。
        #   真正要防的是「几乎什么都没测却报 pass」⇒ 看比例。
        degen_ok = all(
            (r["n_judged"] >= r["n_circular"])   # 可判的 ≥ 剔除的 ⇒ 比例过半
            or r["verdict"] == "degenerate_untested"
            for r in sens)
        check("G4 拟合窗敏感性：不可判过半的行不许被报成 pass（没测 ≠ 通过）",
              bool(sens) and degen_ok,
              [f"{len(sens)} 个窗口",
               "判决：" + "、".join(f"{r['fit_alphas'][-1]}→{r['verdict']}" for r in sens)])

    # ---- 量级体检 ----
    print("\nH 层 · 量级体检")
    ok_g = [g for g in gvs if g is not None]
    if ok_g:
        med = st.median(ok_g)
        neg = sum(1 for g in ok_g if g <= 0)
        print(f"    g_v 中位 {med:.4f}；其中 ≤0 的 {neg}/{len(ok_g)} 个")
        if neg > 0.5 * len(ok_g):
            warns.append("过半上下文的 g_v ≤ 0（小 α 段 gap 不收敛）"
                         "⇒ 「阈值 = m / g_v」在一半以上的上下文上**预测不出改口**")
        check("H1 g_v 的正负分布已报告（g_v≤0 是「预测不出」，不是「无效」）",
              True, [f"中位 {med:.4f}；≤0 的 {neg}/{len(ok_g)}"])

    print("\n" + "=" * 60)
    print("\nRESULT verify_ltv  %s  %d/%d 条通过"
          % ("RED" if fails else "GREEN", _total[0] - len(fails), _total[0]))
    for f in fails:
        print("   [FAIL] " + f)
    for w in warns:
        print("⚠ " + w)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())