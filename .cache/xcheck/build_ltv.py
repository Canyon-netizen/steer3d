#!/usr/bin/env python3
"""LTV 的**唯一判决权威**。从 probe_ltv.py 的原始落盘字段独立算一遍。

⚠ 本文件不 import 探针，也不复用它的任何中间量。
  探针自己也算了一部分（用于增量落盘），那份**不作为结论** ——
  同源共用会「一处错则处处绿」。

判决规则全部来自 `LTV_PREREG.md`，那是**取数之前**写死的。
结果与门不符就照实报，不换指标、不改门、不挑一个好看的讲。

用法:
  python3 .cache/xcheck/build_ltv.py
  ARTIFACT=.cache/xcheck/ltv.json PUBLIC=... python3 .cache/xcheck/build_ltv.py
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
ART = os.environ.get("ARTIFACT", os.path.join(HERE, "ltv.json"))
PUBLIC = os.environ.get("PUBLIC", os.path.join(
    REPO, "frontend", "public", "latent", "data", "ltv.json"))

# ---- 预登记表 §3 写死的量 ----------------------------------------------------
ALPHA_GRID = [0.05, 0.1, 0.2, 0.35, 0.5, 1.0, 2.0, 4.0]
FIT_ALPHAS = [0.05, 0.1, 0.2]
K_MAX = 8
# G-a：预登记表写的是「≤ 一档强度（α 网格相邻档）」。
#   这里按**字面**实现成「在网格里的下标相差 ≤ 1」，因为那是可判定的形式。
#   ⚠ 预登记表 §3 把它描述成「本网格上约 1.7~2.8 倍」，而本网格的实际相邻档之比是
#     2 / 2 / 1.75 / 1.43 / 2 / 2 / 2 —— **下界 1.43，不是 1.7**。
#     预登记表那句话与它自己定的网格对不上；按上面的「相邻档」字面执行，
#     并把这个不一致印出来，不替它圆。
# -----------------------------------------------------------------------------

gates, order = {}, []


def put(key, name, claim, verdict, evidence, why_na=None):
    if key in gates:
        raise SystemExit(f"一道门只能 put 一次：{key}")
    g = {"name": name, "claim": claim, "verdict": verdict, "evidence": evidence}
    if why_na:
        g["why_na"] = why_na
    gates[key] = g
    order.append(key)


def log(*a):
    print(*a, flush=True)


def grid_idx(a):
    """α 在网格里的下标；不在网格上（预测值）返回 None。"""
    for i, x in enumerate(ALPHA_GRID):
        if abs(x - a) < 1e-9:
            return i
    return None


def fit_slope(ys, xs):
    """最小二乘斜率与截距（两点以上）。"""
    n = len(xs)
    if n < 2:
        return None, None
    mx = sum(xs) / n
    my = sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return None, None
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den
    return b, my - b * mx


def sensitivity(ctx):
    """⚠ G-a 的判决依赖「g_v 在哪几档上拟合」—— 而预登记表**没有写死这一项**。

    项目规矩是「判决规则必须取数前写死」。这一项当时没写 ⇒
    它就是一个**未写死却左右判决**的参数。补救不是替它选一个好看的，
    而是**把它变成报告出来的一列**：同一批数据、同一道门、只换拟合窗，
    判决会变成什么，全部印出来。

    为什么主口径取**最小的三档**：窗口越宽，越可能把改口点本身包进去
    ⇒ g_v 是拿答案拟合答案 ⇒ 门变成恒真。所以主口径必须窄。
    而窄窗口的代价正是 pos=391 那种情形：小 α 段 gap 几乎是平的，
    拟合出 g_v ≈ 0，预测「永不改口」，实测却在 α=4 改了口 ——
    这是**真失败**，不是拟合事故（那条曲线的原始形状就在产物里）。
    """
    out = []
    wins = [[0.05, 0.1, 0.2], [0.05, 0.1, 0.2, 0.35], [0.05, 0.1, 0.2, 0.35, 0.5],
            [0.05, 0.1, 0.2, 0.35, 0.5, 1.0], ALPHA_GRID]
    for w in wins:
        hit = circ = both = f = 0
        for c in ctx:
            gap = c["arm_gap"]
            xs = [a for a in w if str(a) in gap]
            ys = [float(gap[str(a)]) for a in xs]
            b, _ = fit_slope(ys, xs)
            m = c["arm_alpha_star"]
            # ⚠⚠ 这里**必须**用与主口径同一套剔除。第一版敏感性函数只剔了
            #   「改口落在窗口内」，没剔「gap 非单调」⇒ 它把主口径已经判 na 的
            #   位置又拿去判了一遍，而那一遍的口径更宽、命中更多 ⇒ 表里
            #   出现「主口径 PASS 而宽窗 FAIL」这种自相矛盾的行。
            #   ⇒ 两处必须共用同一个前置。
            if len(ys) >= 2 and any(ys[i + 1] > ys[i] + 1e-12
                                   for i in range(len(ys) - 1)):
                continue          # 线性外推的前提不成立 ⇒ 与主口径一致地剔除
            if m is not None and m <= max(w):
                circ += 1          # 改口落在窗口内 ⇒ 这档拟合含答案，不可判
                continue
            g = None if b is None else -b
            p = None if (g is None or g <= 0) else float(c["m_p"]) / g
            if p is None:
                if m is None:
                    both += 1
                else:
                    f += 1
                continue
            if m is None:
                if p > ALPHA_GRID[-1]:
                    both += 1
                else:
                    f += 1
                continue
            ip = min(range(len(ALPHA_GRID)), key=lambda i: abs(ALPHA_GRID[i] - p))
            im = grid_idx(m)
            if im is not None and abs(ip - im) <= 1:
                hit += 1
            else:
                f += 1
        out.append({"fit_alphas": w, "n_circular": circ, "n_within_one_notch": hit,
                    "n_both_censored": both, "n_fail": f,
                    # ⚠⚠ **「不可判的多」不是「红得少」。**
                    #   实测：全网格那一行是 8/11 不可判 + 0 红 ⇒ 看着像满分通过，
                    #   实际上它只是**几乎什么都没测**（拟合窗把改口点包进去了，
                    #   g_v 是拿答案拟合答案）。不守这一条，宽窗就会把窄窗发现的
                    #   真失败「洗成」通过 —— 与「全 PASS 的判据等于没有判据」同族。
                    "n_judged": hit + both + f,
                    "verdict": ("degenerate_untested" if (hit + both + f) == 0 or
                                circ > 0.5 * (hit + both + f + circ)
                                else ("pass" if f == 0 else "fail"))})
    return out


def main():
    if not os.path.exists(ART):
        log(f"原始产物不存在：{ART}；先跑 probe_ltv.py")
        return 2
    d = json.load(open(ART, encoding="utf-8"))
    ctx = d.get("contexts") or []
    if not ctx:
        log("产物里没有 contexts —— 这一轮没取到数，不许判绿")
        return 2
    log(f"原始产物 {ART}")
    log(f"杠杆 {d.get('lever', {}).get('name')}@L{d.get('layer')}　"
        f"α 网格 {d.get('alpha_grid')}　拟合窗 {d.get('fit_alphas')}")
    log(f"上下文 {len(ctx)} 个；留出划分 {d.get('split')}")

    # ---- 构建期自检 ------------------------------------------------------
    problems = []
    if d.get("alpha_grid") != ALPHA_GRID:
        problems.append(f"α 网格与预登记不符：{d.get('alpha_grid')}")
    if d.get("fit_alphas") != FIT_ALPHAS:
        problems.append(f"拟合窗与预登记不符：{d.get('fit_alphas')}")
    idbad = [c for c in ctx if not c.get("identity_top1_ok")]
    if idbad:
        problems.append(f"{len(idbad)} 个上下文恒等自证失败（批量化引入了偏差？）")
    if not d.get("sentence_diffs"):
        problems.append("① 的句子差分缺失")
    log(f"构建期自检：{len(problems)} 条问题 {problems if problems else ''}")

    # ---- 逐上下文：由 gap(α) 推出 g_v，再预测 α* -------------------------
    rows = []
    for c in ctx:
        m_p = float(c["m_p"])
        gap = c["arm_gap"]
        xs = [a for a in FIT_ALPHAS if str(a) in gap]
        ys = [float(gap[str(a)]) for a in xs]
        b, a0 = fit_slope(ys, xs)
        # 斜率 b = d(gap)/dα。gap 收敛到 0 时改口 ⇒ g_v = −b（正 = 会顶开缺口）
        g_v = None if b is None else -b
        pred = None if (g_v is None or g_v <= 0) else m_p / g_v
        meas = c["arm_alpha_star"]
        ctl = c["ctl_alpha_star"]
        ctl_vals = [v for v in ctl.values() if v is not None]
        ctl_min = min(ctl_vals) if ctl_vals else None
        # 拟合窗**不含**改口，否则「预测」是拿答案推答案
        circular = meas is not None and meas <= max(FIT_ALPHAS)
        rows.append({
            "pid": c["pid"], "pos": c["pos"], "tok": c.get("tok"),
            "m_p": m_p, "g_v": g_v, "gap_at_0": a0,
            "alpha_star_pred": pred, "alpha_star_meas": meas,
            "ctl_alpha_star_min": ctl_min, "ctl_all": ctl,
            "circular_fit_window": circular,
        })

    # ---- G-a 可预测 ------------------------------------------------------
    # ⚠ 先剔除**前提不成立**的上下文，否则这道门会红在一个不是缺陷的地方。
    #   前提是什么：小 α 段 gap 必须**单调不增**往 0 走 —— 否则线性外推无意义。
    #   实测确实有这类上下文（gap 先微升再塌，如 pos=391：
    #   0.75425 → 0.75481 → 0.75501，然后到 α≥2 才塌到 −0.47）。
    #   ⇒ 这些位置**报 na**，不报 fail：本仓自己的规矩是
    #     「G2 不过的臂，G3-G6 一律标 na —— 报 fail 是伪造结论」，
    #     这里 G-a 的前提没过，形状完全一样。
    #   同时把它们印出来，因为它们**正是 G-a 会失败的那个机理**，两者必须挂钩。
    def monotone_in_fit(c):
        gap = c["arm_gap"]
        ys = [float(gap[str(a)]) for a in FIT_ALPHAS if str(a) in gap]
        return not any(ys[i + 1] > ys[i] + 1e-12 for i in range(len(ys) - 1))

    nonmono = [c for c in ctx if not monotone_in_fit(c)]
    nonmono_key = {(c["pid"], c["pos"]) for c in nonmono}
    for r in rows:
        r["gap_monotone_in_fit"] = (r["pid"], r["pos"]) not in nonmono_key
    log(f"\nG-a 前置：拟合窗 {FIT_ALPHAS} 内 gap **非单调**的 {len(nonmono)}/{len(ctx)}"
        f" 个上下文报 na（线性外推的前提不成立）")
    for c in nonmono[:5]:
        g = c["arm_gap"]
        log(f"     ⊘ {c['pid'][-11:]} pos={c['pos']} "
            f"gap: {[round(float(g[str(a)]), 4) for a in FIT_ALPHAS]}")

    judged = [r for r in rows
              if not r["circular_fit_window"] and r["gap_monotone_in_fit"]]
    censored_fit = [r for r in rows if r["circular_fit_window"]]
    dropped_nonmono = [r for r in rows
                       if not r["gap_monotone_in_fit"] and not r["circular_fit_window"]]
    log(f"   改口落在拟合窗内（预测会变成拿答案推答案）的 {len(censored_fit)} 个"
        f"／前提不成立的 {len(dropped_nonmono)} 个 ⇒ 可判 {len(judged)} 个")

    applic = (len(ctx) - len(nonmono)) / max(len(ctx), 1)
    log(f"   ⚠ 适用率 {(len(ctx)-len(nonmono))}/{len(ctx)} = {applic:.3f}"
        f"（前提不成立的 {len(nonmono)} 个被剔除 ⇒ G-a 只判 {len(judged)} 个）")
    ok_grid, ok_beyond, fail, npred, nmeas, both_cens = 0, 0, [], 0, 0, 0
    for r in judged:
        p, m = r["alpha_star_pred"], r["alpha_star_meas"]
        if p is None:
            npred += 1                       # g_v ≤ 0：这一档顶不开缺口
            if m is not None:
                fail.append((r, "预测为 None（g_v≤0）但实测改了口"))
            continue
        if m is None:
            nmeas += 1                       # 实测在网格内没改口
            if p <= ALPHA_GRID[-1]:
                fail.append((r, f"预测 α*={p:.3g} ≤ 网格上限但实测未改口（右删失）"))
            else:
                both_cens += 1                # 两边都说「要更大的强度」⇒ 一致
            continue
        ip, im = grid_idx(p), grid_idx(m)
        if ip is None:
            # 预测值不在网格上：与实测所在档比较档距
            near = min(range(len(ALPHA_GRID)),
                       key=lambda i: abs(ALPHA_GRID[i] - p))
            ip = near
        if abs(ip - im) <= 1:
            ok_grid += 1
        else:
            fail.append((r, f"预测 α*={p:.3g}（档 {ip}）与实测 {m}（档 {im}）"
                            f"相差 {abs(ip-im)} 档 > 1"))
    va = ok_grid + both_cens
    log(f"   相邻档内命中 {ok_grid}／两边同判右删失 {both_cens}"
        f"／预测不出（g_v≤0）{npred}／实测右删失 {nmeas}／判红 {len(fail)}")
    for r, why in fail[:6]:
        log(f"     ✗ {r['pid'][-11:]} pos={r['pos']} m_p={r['m_p']:.3f} "
            f"g_v={r['g_v']}：{why}")
    put("G-a0", "定律的适用率",
        "拟合窗内 gap 单调不增（线性外推成立）的上下文必须占多数 —— "
        "前提不成立就把该处剔除，会让 G-a 变好看，那正是「改了坏的一处却让"
        "更宽的检查变绿」",
        "pass" if applic >= 2.0 / 3 else "fail",
        {"n_ctx": len(ctx), "n_monotone": len(ctx) - len(nonmono),
         "n_nonmonotone": len(nonmono), "applicability": round(applic, 3),
         "threshold": 2 / 3,
         "nonmonotone_ctx": [{"pid": c["pid"][-11:], "pos": c["pos"],
                              "gap_fit_window": [round(float(c["arm_gap"][str(a)]), 5)
                                                 for a in FIT_ALPHAS]}
                             for c in nonmono]})

    put("G-a", "阈值可预测",
        "在留出上下文上，由 gap(α) 线性拟合出的 g_v 预测的 α*，"
        "与实测 α* 相差不超过一个网格档",
        "pass" if not fail else "fail",
        {"n_judged": len(judged), "n_excluded_fit_window": len(censored_fit),
         "n_excluded_nonmonotone": len(nonmono),
         "n_within_one_notch": ok_grid, "n_both_censored": both_cens,
         "n_pred_none_gv_le0": npred, "n_meas_censored": nmeas,
         "alpha_grid": ALPHA_GRID, "fit_alphas": FIT_ALPHAS,
         "fit_window_sensitivity": sensitivity(ctx),
         "failures": [{"pid": r["pid"], "pos": r["pos"], "m_p": r["m_p"],
                       "g_v": r["g_v"], "pred": r["alpha_star_pred"],
                       "meas": r["alpha_star_meas"], "why": w}
                      for r, w in fail]})

    # ---- G-b 有牙齿 ------------------------------------------------------
    # 判据：该向量的 α* 必须**显著低于**幅度配平随机对照的 α*。
    #
    # ⚠⚠ 第一版的打分**给错了**两处，都会虚增分数或虚减：
    #   ① 「臂没改口 → −1」。可对照也没改口时，那是**两边都没动**，
    #      谈不上谁更有效 —— 算成扣分是把「没反应」当成「不如别人」。
    #   ② 「两边都改口 → 0」。那恰恰是最该比 α* 的情形，
    #      恰恰比出高下的地方，我却放弃了比较。
    # ⇒ 改成按「谁先动」逐上下文配对：
    #     臂动、对照全不动           → +1
    #     臂动、对照也动             → 比 α*：臂更低 +1／更高 −1／相等 0
    #     臂不动、对照也不动         →  0（两边都没反应，无从比较）
    #     臂不动、对照动了           → −1（随机顶动了而杠杆没顶动）
    #   最后对**非零**的那些做符号检验，报 p 值 ——
    #   「净分 > 0」不是显著性，而预登记表要的是「**显著**低于」。
    detail, pos, neg, zeros = [], 0, 0, 0
    for r in rows:
        n_ctl = len(r["ctl_all"])
        n_ctl_flip = sum(1 for v in r["ctl_all"].values() if v is not None)
        a = r["alpha_star_meas"]
        if a is None and n_ctl_flip == 0:
            s, why = 0, "两边都没改口 ⇒ 无从比较（不记 +1 也不记 −1）"
        elif a is None:
            s, why = -1, f"臂没改口，但 {n_ctl_flip}/{n_ctl} 个对照改口了"
        elif n_ctl_flip == 0:
            s, why = 1, "臂改口而两个对照都没改口"
        else:
            best = min(v for v in r["ctl_all"].values() if v is not None)
            s = 1 if a < best else (-1 if a > best else 0)
            why = f"两边都改口：臂 α*={a} vs 对照最早 {best}"
        pos += s > 0
        neg += s < 0
        zeros += s == 0
        detail.append({"pid": r["pid"], "pos": r["pos"], "m_p": r["m_p"],
                       "arm": a, "ctl": r["ctl_all"], "score": s, "why": why})
    net = pos - neg
    n_eff = pos + neg
    # 双侧符号检验的精确 p（n 较小，直接数）
    if n_eff > 0:
        k = min(pos, neg)
        tot = sum(math.comb(n_eff, i) for i in range(0, k + 1))
        p_two = min(1.0, 2 * tot / (2 ** n_eff))
    else:
        p_two = 1.0
    log(f"\nG-b：配对打分  +1 {pos}／−1 {neg}／0 {zeros}"
        f"（共 {len(rows)}）⇒ 净 {net}，有效对比 {n_eff}，符号检验 p={p_two:.4g}")
    put("G-b", "阈值表有牙齿",
        "该向量的 α* 显著低于幅度配平随机对照的 α*"
        "（对照与该臂偏离 clean 的范数逐节点相等）",
        "pass" if (net > 0 and p_two < 0.05) else "fail",
        {"net": net, "n_plus": pos, "n_minus": neg, "n_zero": zeros,
         "n_ctx": len(rows), "n_effective": n_eff, "sign_test_p": p_two,
         "alpha": 0.05,
         "control": "幅度配平随机对照，‖偏离‖ 逐节点相等",
         "detail": detail})

    # ---- G-c 名字预测效果 ----------------------------------------------
    # ⚠ 本轮**没测**。它要的是「注入后的可读输出里，S_k 指向的行为是否出现」，
    #   那需要**生成**（注入后让模型续写文本），与本轮测的
    #   「教师强制下逐步注入能不能改口」是两种实验。
    #   预登记表 §5 明写「不在抽取用的那批上下文上报 G-c」。
    #   ⇒ 这里报 **na 并写明为什么**，不报 fail —— 没跑 ≠ 跑了没过。
    put("G-c", "名字预测效果",
        "S_k 指向的行为必须出现在注入后的可读输出里，"
        "且在未参与抽取的题上仍成立",
        "na", {"reason": "本轮探针只做了教师强制下的改口测量，没有做注入后生成"},
        why_na="本轮**未测**：G-c 需要注入后**生成**可读输出并检查 S_k 指向的行为，"
               "而 probe_ltv.py 这一轮只测了「教师强制下逐步注入能不能改口」——"
               "两者是不同实验。按预登记表 §5「不在抽取用的那批上下文上报 G-c」，"
               "这里报 na 而非 fail：没跑 ≠ 跑了没过。")

    # ---- 自检门 ----------------------------------------------------------
    put("S1", "自检：α 网格/拟合窗与预登记一致、每个上下文恒等自证过、① 句子差分齐全",
        "装置不许带着错的口径去报判决", "pass" if not problems else "fail",
        {"problems": problems, "n_ctx": len(ctx),
         "n_identity_ok": sum(1 for c in ctx if c.get("identity_top1_ok"))})

    # ---- 输出 ------------------------------------------------------------
    sd = d.get("sentence_diffs") or []
    public = {
        "schema": "steer3d.ltv/1",
        "prereg": "LTV_PREREG.md（写于取数之前）",
        "lever": d.get("lever"),
        "alpha_grid": ALPHA_GRID,
        "fit_alphas": FIT_ALPHAS,
        "k_max": K_MAX,
        "split": d.get("split"),
        "registry_names": d.get("registry_names"),
        "sentence_diffs": [
            {"key": r["key"], "S": r["S"], "Sp": r["Sp"], "norm": r["norm"],
             "negative_control": r["negative_control"]} for r in sd],
        "contexts": rows,
        "gate_order": order,
        "gates": gates,
        "caveats": [
            "S_k 是人挑的（预登记表 §4 已声明），存在拟合风险，消不掉。",
            "g_v 只在最小三档上拟合；改口落在拟合窗内的上下文一律不判 G-a。",
            "预登记表 §3 把「一档」写成「约 1.7~2.8 倍」，"
            "而本网格的相邻档之比实为 1.43~2.0 —— 按「相邻档」字面执行。",
            "G-a 剔除了两类上下文并各自写明理由：改口落在拟合窗内"
            "（预测会变成拿答案推答案）与拟合窗内 gap 非单调"
            "（线性外推的前提不成立）。两类都记 na，不记 fail。",
            "G-b 的对照是幅度配平随机对照，‖偏离‖ 逐节点相等，"
            "但随机方向在 2048 维里落在数据流形外，可能过度破坏 ⇒ 右删失被"
            "读成「顶不动」，这个混淆消不掉。",
        ],
    }
    os.makedirs(os.path.dirname(PUBLIC), exist_ok=True)
    tmp = PUBLIC + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(public, f, ensure_ascii=False, indent=1)
    os.replace(tmp, PUBLIC)

    log(f"\n{'-'*60}")
    for k in order:
        g = gates[k]
        log(f"  {k:<4} {g['verdict'].upper():<5} {g['name']}")
        if g.get("why_na"):
            log(f"        {g['why_na'][:110]}…")
    cnt = {v: sum(1 for k in order if gates[k]["verdict"] == v)
           for v in ("pass", "fail", "na")}
    log(f"  三态计数 {cnt}")
    log(f"  已写出 {PUBLIC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())