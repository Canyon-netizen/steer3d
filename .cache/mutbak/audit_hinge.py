#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把动摇点**摊开**供人工复核，并给出可复核的准确率。

⚠ P0 的教训：H-1/2/3 三支自检曾**全绿**，而真实语料的 14 条「错」
  逐条读后**全是假阳性**。所以判决全绿**不等于**标注正确。

本脚本分两步：
  （默认）把每个动摇点的原句 + 前后文印出来，人工读；
  （--audit）按 VERDICTS 给出真实语料的准确率。

⚠ VERDICTS 里的每一条都必须对应**实际读过的那一行**。
  第一版我手抄了若干 (traj, start) 键，其中几条是我**没读**过的行
  （凭印象填的），会凭空造出裁决。已作废重写为下方这份，
  它由 `hinge.json` 的前 104 行导出，与打印输出逐行对应。
"""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NPZ_DIR = os.path.join(ROOT, "datasets", "aime_qwen3_1p7b_16k_fp16", "aime")
HINGE = os.path.join(ROOT, ".cache", "xcheck", "hinge.json")

# --------------------------------------------------------------------------
# 人工裁决。key = (trajectory_id, start)。
# verdict ∈ {"true_hinge","false_positive"}
# ⚠ 只覆盖**实际读过**的前 104 行；其余未读，跑 --audit 会单列出来。
# --------------------------------------------------------------------------
_T = "true_hinge"
_F = "false_positive"
VERDICTS = {
    ("aime__1983__1983_I_1__think", 2066): (_T, "But let me check if I did everything correctly ⇒ 回头全链重算"),
    ("aime__1983__1983_I_1__think", 2115): (_T, "Let me verify each step again ⇒ 同一轮自查的延续"),
    ("aime__1984__1984_I_1__think", 1653): (_F, "But maybe I don't need to worry about … ⇒ 是「不必管这个」的**免除**，不是动摇"),
    ("aime__1985__1985_I_1__think", 1562): (_T, "Hmm, okay ⇒ 停下来消化已得结论"),
    ("aime__1986__1986_I_1__think", 1213): (_T, "Wait, let me check that ⇒ 回头验刚写的化简"),
    ("aime__1986__1986_I_1__think", 1923): (_T, "But hold on, let me check if x=3 satisfies … ⇒ 代回原式验证"),
    ("aime__1986__1986_I_1__think", 2228): (_T, "But maybe I made a mistake here? ⇒ 自疑最强的一类"),
    ("aime__1986__1986_I_1__think", 2261): (_T, "Let me check again ⇒ 紧接上句的自查延续"),
    ("aime__1986__1986_I_1__think", 2547): (_T, "Wait, let me think again ⇒ 回头重想"),
    ("aime__1987__1987_I_1__think", 1833): (_F, "Wait, but maybe I can use the principle … ⇒ 想到新方法的**推进**，不是回头"),
    ("aime__1987__1987_I_1__think", 3864): (_F, "But maybe I need to handle m=0 separately ⇒ 想到要补的**边界情况**，是推进"),
    ("aime__1987__1987_I_1__think", 5214): (_T, "Wait, no ⇒ 明确否掉刚说的假设"),
    ("aime__1987__1987_I_1__think", 5568): (_T, "So maybe my assumption is wrong ⇒ 自疑假设"),
    ("aime__1988__1988_I_1__think", 2036): (_T, "So maybe I made a mistake? ⇒ 自疑"),
    ("aime__1988__1988_I_1__think", 2061): (_T, "Wait, let me check again ⇒ 回核算术"),
    ("aime__1988__1988_I_1__think", 2430): (_T, "Wait, maybe I miscalculated 1988 mod 625? ⇒ 自疑算术，下一句确实重算"),
    ("aime__1988__1988_I_1__think", 2466): (_T, "Let me check again ⇒ 重算 mod"),
    ("aime__1988__1988_I_1__think", 2846): (_T, "Let me check ⇒ 回看"),
    ("aime__1988__1988_I_1__think", 3385): (_T, "Wait, maybe I miscalculated 1988 mod 5? ⇒ 自疑算术"),
    ("aime__1989__1989_I_1__think", 2517): (_T, "Let me verify the steps again ⇒ 回核算术"),
    ("aime__1990__1990_I_1__think", 1986): (_T, "Let me think again ⇒ 回头重想"),
    ("aime__1990__1990_I_1__think", 2383): (_T, "Wait, no ⇒ 否掉刚说的方案"),
    ("aime__1990__1990_I_1__think", 2884): (_T, "Wait, no ⇒ 同上"),
    ("aime__1990__1990_I_1__think", 5488): (_T, "Let me think again ⇒ 回头重想"),
    ("aime__1990__1990_I_1__think", 7758): (_T, "So, maybe my assumption is wrong ⇒ 自疑"),
    ("aime__1991__1991_I_1__think", 281): (_T, "Hmm, okay ⇒ 停下来消化"),
    ("aime__1991__1991_I_1__think", 1133): (_T, "Wait, no ⇒ 否掉上一句"),
    ("aime__1991__1991_I_1__think", 2243): (_T, "Wait, no ⇒ 否掉上一句"),
    ("aime__1991__1991_I_1__think", 2501): (_T, "Wait, no ⇒ 否掉上一句"),
    ("aime__1991__1991_I_1__think", 2864): (_T, "Let me think again ⇒ 回头重想"),
    ("aime__1991__1991_I_1__think", 3596): (_T, "Wait, no ⇒ 否掉上一句"),
    ("aime__1994__1994_I_1__think", 3388): (_T, "Hmm, okay ⇒ 停下来消化"),
    ("aime__1994__1994_I_1__think", 4827): (_T, "Hmm ⇒ 停下来"),
    ("aime__2000__2000_I_1__think", 3496): (_T, "Wait, no ⇒ 否掉上一句"),
    ("aime__2000__2000_I_1__think", 4562): (_T, "Let me check ⇒ 回头"),
    ("aime__2002__2002_I_1__think", 3030): (_T, "But let me check if I did the multiplication correctly ⇒ 回核算术"),
    ("aime__2002__2002_I_1__think", 3807): (_T, "But let me check if there's any other constraints ⇒ 回头补漏条件"),
    ("aime__2002__2002_I_1__think", 4170): (_T, "But let me think again ⇒ 回头重想"),
    ("aime__2002__2002_I_1__think", 5056): (_T, "But let me check with another approach ⇒ 换方法验同一结论"),
    ("aime__2002__2002_I_1__think", 5420): (_T, "maybe I can check if my answer is correct ⇒ 自查答案"),
    ("aime__2004__2004_I_1__think", 1313): (_T, "Wait, no ⇒ 否掉上一句"),
    ("aime__2004__2004_I_1__think", 1479): (_T, "Wait, no ⇒ 否掉上一句"),
    ("aime__2004__2004_I_1__think", 4589): (_T, "Wait, no ⇒ 否掉上一句"),
    ("aime__2004__2004_I_1__think", 5126): (_T, "Wait, no ⇒ 否掉上一句"),
    ("aime__2004__2004_I_1__think", 6995): (_T, "Wait, no ⇒ 否掉上一句"),
    ("aime__2004__2004_I_1__think", 8694): (_T, "Wait, no ⇒ 否掉上一句"),
    ("aime__2010__2010_I_1__think", 1132): (_T, "Wait, but let me check if that's correct ⇒ 回核算术"),
    ("aime__2010__2010_I_1__think", 1357): (_F, "But hold on, the problem says … ⇒ 在**重读题目**，不是自查（§1 已排除，但本实现漏了这句）"),
    ("aime__2010__2010_I_1__think", 1485): (_T, "But let me check if there's any other constraints ⇒ 回头补漏"),
    ("aime__2010__2010_I_1__think", 2363): (_T, "But let me check once again ⇒ 回核算术"),
    ("aime__2010__2010_I_1__think", 2743): (_T, "Let me check ⇒ 回头"),
    ("aime__2010__2010_I_1__think", 3079): (_T, "But let me check if there's any other possible interpretation ⇒ 回头查歧义"),
    ("aime__2012__2012_I_1__think", 1264): (_T, "Let me check again ⇒ 回头"),
    ("aime__2012__2012_I_1__think", 1474): (_T, "Hmm ⇒ 停下来"),
    ("aime__2012__2012_I_1__think", 1896): (_T, "But let me think again ⇒ 回头重想"),
    ("aime__2012__2012_I_1__think", 2975): (_T, "Let me check ⇒ 回头"),
    ("aime__2012__2012_I_1__think", 3179): (_T, "maybe I need to check if there's a different interpretation ⇒ 回头查歧义"),
    ("aime__2012__2012_I_1__think", 3552): (_T, "But let me think again ⇒ 回头重想"),
    ("aime__2014__2014_I_1__think", 724): (_T, "Wait, no ⇒ 否掉上一句"),
    ("aime__2014__2014_I_1__think", 984): (_T, "Wait, no ⇒ 否掉上一句"),
    ("aime__2014__2014_I_1__think", 2961): (_T, "Wait, no ⇒ 否掉上一句"),
    ("aime__2014__2014_I_1__think", 3494): (_T, "Wait, no ⇒ 否掉上一句"),
    ("aime__2014__2014_I_1__think", 3927): (_T, "Wait, no ⇒ 否掉上一句"),
    ("aime__2014__2014_I_1__think", 4341): (_T, "Wait, no ⇒ 否掉上一句"),
    ("aime__2016__2016_I_1__think", 1368): (_T, "Let me check ⇒ 回头"),
    ("aime__2016__2016_I_1__think", 2331): (_T, "Wait, maybe I made a mistake here ⇒ 自疑"),
    ("aime__2016__2016_I_1__think", 3520): (_T, "Wait, let me check again ⇒ 回头"),
    ("aime__2016__2016_I_1__think", 5661): (_T, "Let me verify that again ⇒ 回验"),
    ("aime__2016__2016_I_1__think", 5968): (_T, "Hmm ⇒ 停下来"),
    ("aime__2020__2020_I_1__think", 1248): (_T, "Let me check ⇒ 回头"),
    ("aime__2020__2020_I_1__think", 1765): (_T, "Wait, but hold on ⇒ 停下来回头"),
    ("aime__2020__2020_I_1__think", 2770): (_T, "But let me think again ⇒ 回头重想"),
    ("aime__2020__2020_I_1__think", 3898): (_T, "maybe I need to check if there's a mistake ⇒ 自疑"),
    ("aime__2020__2020_I_1__think", 4376): (_T, "But let me check with another approach ⇒ 换方法验"),
    ("aime__2020__2020_I_1__think", 5399): (_T, "But let me check if there is a possible mistake ⇒ 自疑"),
    ("aime__2021__2021_I_1__think", 1476): (_T, "Let me check ⇒ 回头"),
    ("aime__2021__2021_I_1__think", 2983): (_T, "Let me check that ⇒ 回头"),
    ("aime__2021__2021_I_1__think", 3135): (_T, "Let me check that ⇒ 回头"),
    ("aime__2021__2021_I_1__think", 3243): (_T, "Wait, no ⇒ 否掉上一句"),
    ("aime__2021__2021_I_1__think", 3389): (_T, "Let me check that ⇒ 回头"),
    ("aime__2021__2021_I_1__think", 3639): (_T, "Wait, no ⇒ 否掉上一句"),
    ("aime__2022__2022_I_1__think", 2284): (_T, "maybe I need to check if there are other possibilities ⇒ 回头补漏"),
    ("aime__2022__2022_I_1__think", 2429): (_T, "Let me think again ⇒ 回头重想"),
    ("aime__2022__2022_I_1__think", 2646): (_T, "But let me check if there are any other solutions ⇒ 回头补漏解"),
    ("aime__2022__2022_I_1__think", 3801): (_T, "But let me check with another approach ⇒ 换方法验"),
    ("aime__2022__2022_I_1__think", 4246): (_T, "Let me check ⇒ 回头"),
    ("aime__2022__2022_I_1__think", 5251): (_T, "Let me check again ⇒ 回头"),
    ("aime__2023__2023_I_1__think", 1268): (_T, "But hold on, if all three sides are equal ⇒ 回头重新审视"),
    ("aime__2023__2023_I_1__think", 1470): (_T, "maybe I need to check if that's the case? ⇒ 回头查"),
    ("aime__2023__2023_I_1__think", 1523): (_T, "Wait, maybe I misread the problem ⇒ 自疑读题"),
    ("aime__2023__2023_I_1__think", 1552): (_T, "Let me check again ⇒ 回读题"),
    ("aime__2023__2023_I_1__think", 2311): (_T, "Wait, maybe I misread the problem ⇒ 自疑读题"),
    ("aime__2023__2023_I_1__think", 2340): (_T, "Let me check again ⇒ 回读题"),
    ("aime__2024__2024_I_1__think", 1236): (_F, "But maybe it's better to think in terms of … ⇒ 换**更好的思考方式**，是推进"),
    ("aime__2024__2024_I_1__think", 4549): (_T, "Wait, no ⇒ 否掉上一句"),
    ("aime__2024__2024_I_1__think", 4728): (_T, "Wait, no ⇒ 否掉上一句"),
    ("aime__2024__2024_I_1__think", 5053): (_T, "Wait, no ⇒ 否掉上一句"),
    ("aime__2024__2024_I_1__think", 5312): (_T, "Wait, no ⇒ 否掉上一句"),
    ("aime__2025__2025_I_1__think", 656): (_F, "但 since the side length here is 4 … ⇒ maybe 后面接的是**往前推**，不是回头"),
    ("aime__2025__2025_I_1__think", 977): (_T, "Let me think again ⇒ 回头重想"),
    ("aime__2025__2025_I_1__think", 1133): (_T, "Wait, no ⇒ 否掉上一句"),
    ("aime__2025__2025_I_1__think", 2100): (_T, "Let me think again ⇒ 回头重想"),
    ("aime__2025__2025_I_1__think", 3489): (_T, "Wait, no ⇒ 否掉上一句"),
    ("aime__2025__2025_I_1__think", 4816): (_T, "Wait, maybe my coordinate system is wrong ⇒ 自疑坐标系"),

    # --- 补读：规则修好后的第二轮 32 个 ---
    ("aime__1986__1986_I_1__think", 2232): (_T, "But maybe I made a mistake here? ⇒ 自疑"),
    ("aime__1987__1987_I_1__think", 5574): (_T, "So maybe my assumption is wrong ⇒ 自疑假设"),
    ("aime__1988__1988_I_1__think", 2735): (_T, "So maybe there's a mistake in my reasoning? ⇒ 自疑推理"),
    ("aime__1988__1988_I_1__think", 3419): (_T, "Let me check again ⇒ 紧接着自疑后的重算"),
    ("aime__1988__1988_I_1__think", 3758): (_F, "Hmm. 然后是 Alternatively, maybe I need to check… ⇒ 停下来但随即往前推进，不是回头自查"),
    ("aime__1988__1988_I_1__think", 4850): (_T, "maybe I miscalculated 1988 mod 625? ⇒ 自疑算术，下一句确实重算"),
    ("aime__1988__1988_I_1__think", 4886): (_T, "Let me check again ⇒ 重算"),
    ("aime__1990__1990_I_1__think", 7764): (_T, "So, maybe my assumption is wrong ⇒ 自疑"),
    ("aime__1991__1991_I_1__think", 7776): (_T, "Wait, no ⇒ 否掉上一句"),
    ("aime__2010__2010_I_1__think", 3531): (_T, "But let me check if there's a trick here ⇒ 回头查漏"),
    ("aime__2010__2010_I_1__think", 3974): (_T, "But let me check once again ⇒ 回核算术"),
    ("aime__2010__2010_I_1__think", 4382): (_T, "But let me check if there's a possibility that … ⇒ 回头查另一种可能"),
    ("aime__2014__2014_I_1__think", 4490): (_T, "Wait, no ⇒ 否掉上一句"),
    ("aime__2014__2014_I_1__think", 4991): (_T, "Wait, no ⇒ 否掉上一句"),
    ("aime__2014__2014_I_1__think", 5341): (_T, "Wait, no ⇒ 否掉上一句"),
    ("aime__2014__2014_I_1__think", 7824): (_T, "Wait, no ⇒ 否掉上一句"),
    ("aime__2016__2016_I_1__think", 5489): (_T, "unless there's a mistake in my calculation ⇒ 自疑算术"),
    ("aime__2021__2021_I_1__think", 3649): (_T, "Wait, no ⇒ 否掉上一句"),
    ("aime__2021__2021_I_1__think", 3826): (_T, "Let me check that ⇒ 回验"),
    ("aime__2021__2021_I_1__think", 4977): (_T, "maybe I made a mistake here ⇒ 自疑"),
    ("aime__2021__2021_I_1__think", 5007): (_T, "Let me check again ⇒ 紧接自疑后的重算"),
    ("aime__2021__2021_I_1__think", 5332): (_T, "But maybe I made a mistake here ⇒ 自疑"),
    ("aime__2021__2021_I_1__think", 5378): (_T, "But maybe my reasoning is wrong ⇒ 自疑推理"),
    ("aime__2022__2022_I_1__think", 5608): (_T, "But wait, let me check with another approach ⇒ 换方法验"),
    ("aime__2023__2023_I_1__think", 3583): (_F, "Wait, no. The problem says … ⇒ 引述题面被 `Wait, no` 触发"),
    ("aime__2023__2023_I_1__think", 4499): (_T, "Wait, no ⇒ 否掉上一句"),
    ("aime__2023__2023_I_1__think", 5216): (_T, "Wait, let me check again ⇒ 回读题"),
    ("aime__2023__2023_I_1__think", 5660): (_T, "Wait, no ⇒ 否掉上一句"),
    ("aime__2023__2023_I_1__think", 6595): (_T, "Let me check again ⇒ 回读题"),
    ("aime__2025__2025_I_1__think", 5089): (_T, "Wait, no ⇒ 否掉上一句"),
    ("aime__2025__2025_I_1__think", 6055): (_T, "Let me think again ⇒ 回头重想"),
    ("aime__2025__2025_I_1__think", 7012): (_T, "Let me think again ⇒ 回头重想"),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", action="store_true", help="按 VERDICTS 出准确率")
    ap.add_argument("--per", type=int, default=6, help="每条轨迹读几个")
    a = ap.parse_args()

    d = json.load(open(HINGE, encoding="utf-8"))
    rows = d["rows"]

    if a.audit:
        tot = tp = fp = 0
        unread = []
        detail = []
        for r in rows:
            for h in r["hinges"]:
                tot += 1
                v = VERDICTS.get((r["trajectory_id"], h["start"]))
                if not v:
                    unread.append((r["trajectory_id"], h["start"], h["sentence"][:50]))
                    continue
                vd = v[0]
                tp += vd == _T
                fp += vd == _F
                detail.append({"traj": r["trajectory_id"], "start": h["start"],
                               "tok": h.get("tok"), "cls": h["cls"],
                               "sentence": h["sentence"], "verdict": vd, "note": v[1]})
        judged = tp + fp
        print(f"动摇点共 {tot} 个")
        print(f"  已人工读 {judged} 个：真 {tp} · 假 {fp}")
        print(f"  准确率 {tp/judged*100:.1f}%" if judged else "  还没读")
        print(f"  **未读** {len(unread)} 个（占 {len(unread)/tot*100:.1f}%）")
        print("\n⚠ 准确率只覆盖已读的 %d 个，不是全量 %d 个的准确率。"
              % (judged, tot))
        cls_stat = Counter()
        for it in detail:
            cls_stat[(it["cls"], it["verdict"])] += 1
        print("\n=== 按类别的真/假 ===")
        for c in ("A", "B"):
            t = cls_stat[(c, _T)]
            f = cls_stat[(c, _F)]
            if t + f:
                print(f"  类{c}: 真 {t} · 假 {f}  （准确率 {t/(t+f)*100:.0f}%）")
        if unread:
            print("\n=== 未读的前 10 个（供继续读）===")
            for u in unread[:10]:
                print(f"  {u[0][5:9]} [{u[1]}] {u[2]}")
        json.dump(detail, open(os.path.join(ROOT, ".cache", "mutbak",
                                           "hinge_audit.json"), "w",
                              encoding="utf-8"), ensure_ascii=False, indent=1)
        return 0

    texts = {}
    n = 0
    cls_cnt = Counter()
    for r in rows:
        t = r["trajectory_id"]
        if t not in texts:
            texts[t] = json.load(
                open(os.path.join(NPZ_DIR, t + ".json"), encoding="utf-8")
            )["generated_text"]
        text = texts[t]
        for h in r["hinges"][:a.per]:
            n += 1
            cls_cnt[h["cls"]] += 1
            ctx = text[max(0, h["start"] - 55):h["end"] + 55]
            ctx = " ".join(ctx.split())
            mark = "✓" if (t, h["start"]) in VERDICTS else " "
            print(f"{mark}{n:3d}. [{t[5:9]}] tok{str(h.get('tok')):>5} 类{h['cls']} "
                  f"[{h['start']}:{h['end']}]")
            print(f"     …{ctx}…")
    print(f"\n共 {d['n_hinges']} 个（本次每条轨迹印前 {a.per} 个），"
          f"类别分布 {dict(cls_cnt)}")
    print(f"轨迹分布：{d['n_traces_with_hinge']}/{d['n_traces']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())