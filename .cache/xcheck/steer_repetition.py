#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""§4.17 +v 到底是怎么坏的：不是「没答完」，是逐字重复退化。

## 动机

§4.16 测到 +v 让 18/23 的臂撞 32000 token 上限，闭合率 5/23。
那个说法有个弱点：它只说**没跑完**，而「没跑完」可以对应完全不同的机制 ——
（a）模型变得啰嗦但仍在推进、（b）模型进入无意义啰嗦、
（c）模型进入**逐字重复的退化循环**。
三者的解释力差很远，而**只有 (c) 能说明注入在做什么**。

翻 all_runs.json 的部分文本，(c) 一眼可见：模型卡在同一句上无限重复。

## 这件事必须做长度受控，否则是自证的

⚠ 未闭合的臂按定义就是**长**的（撞 32000 上限），而闭合的臂是短的。
所以「长文本里重复更多」几乎不用测就成立 —— 这是 §8.3 ⑧ 的又一次实例：
**任何一个只看「有输出的样本」的统计量都被条件化过。**

⇒ 因此本脚本**不比全长**，只比**每条 run 开头固定长度的窗口**。
窗口一固定，长度这个混淆变量就恒定了，臂间差才是真的。

## 度量

对窗口内的词序列，算两个互补的量：

- `rep_k`：任意 k-gram（k=12 词）**不重叠**出现次数的最大值。
  不重叠是关键：重叠计数会让一句重复 N 次的文本报出 N+k-1，
  把「重复了 3 遍」和「重复了 30 遍」混成一个数。
- `rep_frac`：落在「至少出现 2 次的不重叠 k-gram」里的词占比。
  rep_k 看最坏的一处，rep_frac 看整体的弥散程度。

两个都算，是为了避免「只在开头重复一次」和「整篇都在重复」被混为一谈。

## 自证（不过就不产出文件）

1. 窗口固定 ⇒ 三臂进窗口的词数完全相同（否则长度没控住）
2. 注入一段**人工构造的重复文本**，rep_k 必须显著高于真实文本
3. 注入一段**人工构造的多样文本**（打乱的词序列），rep_k 必须低
4. `rep_k` 的不重叠性：构造「a a a ... a」共 N 次 ⇒ rep_k = N（不是 N+k-1）
5. 三臂的 `primary_text` 里，零臂两向逐字相同 ⇒ 共享对照的前提仍成立
"""
import json
import os
import re
import statistics
import sys
from collections import Counter

REPO = "/Users/zhourui/code/steer3d"
RUNS = os.path.join(REPO, ".cache/32k_journal/all_runs.json")
JOURNAL = os.path.join(REPO, ".cache/32k_journal/cot_divergence_32k.json")
OUT = os.path.join(REPO, "frontend/public/latent/data/steer_repetition.json")

K = 12              # n-gram 长度（词）
# ⚠ WINDOW 不能拍脑袋定 4000。实测最短的一条 run 全文只有 876 词 ——
#   窗口比它长时，「固定窗口」就悄悄退化成「全文」，
#   长度混淆又回来了（自证 1 抓到的就是这个）。
#   ⇒ 取一个**所有** run 都够得着的值，并让自证 1 守住这条下限。
WINDOW = 800        # 全部 92 条 run 的最短全文是 876 词，这里留 76 词余量
aborts = []


def ab(msg):
    aborts.append(msg)
    print("ABORT " + msg)


def toks(text):
    return re.findall(r"\S+", text or "")


def rep_k(words, k=K):
    """任意 k-gram 的最大**不重叠**出现次数。"""
    if len(words) < k:
        return 0
    c = Counter(tuple(words[i:i + k]) for i in range(len(words) - k + 1))
    # 只出现一次的 k-gram 最多值就是 1，走全量扫描纯属浪费
    # （不跳的话 92 条 × 4000 词 × 4000 个不同 gram = 十亿级 tuple 比较）。
    best = 1
    for gram, n in c.items():
        if n < 2:
            continue
        # 不重叠计数：沿文本走，命中一次就跳过 k 个词
        cnt, i, L = 0, 0, len(words) - k + 1
        while i < L:
            if tuple(words[i:i + k]) == gram:
                cnt += 1
                i += k
            else:
                i += 1
        if cnt > best:
            best = cnt
    return best


def rep_frac(words, k=K):
    """落在「至少出现 2 次的不重叠 k-gram」里的词占比。"""
    if len(words) < k:
        return 0.0
    c = Counter(tuple(words[i:i + k]) for i in range(len(words) - k + 1))
    rep = {g for g, n in c.items() if n >= 2}
    if not rep:
        return 0.0
    hit = set()
    for i in range(len(words) - k + 1):
        if tuple(words[i:i + k]) in rep:
            hit.update(range(i, i + k))
    return len(hit) / float(len(words))


def rep_onset(words, k=K, min_count=3):
    """第一次出现「同一 k-gram 不重叠地重复 >= min_count 次」时的起始词下标。

    用来回答「退化从多早就开始」——如果 +v 的重复在开头 800 词内就已经
    开始，那么受控窗口确实罩得住这个现象；如果它到几千词才出现，
    800 词的窗口就会把真差异一并切掉（那是**漏掉**发现，不是伪造）。
    没找到返回 None。
    """
    if len(words) < k * min_count:
        return None
    c = Counter(tuple(words[i:i + k]) for i in range(len(words) - k + 1))
    for gram, n in c.items():
        if n < min_count:
            continue
        cnt, i, L, first = 0, 0, len(words) - k + 1, None
        while i < L:
            if tuple(words[i:i + k]) == gram:
                if first is None:
                    first = i
                cnt += 1
                i += k
            else:
                i += 1
        if cnt >= min_count:
            return first
    return None


def measure(text):
    w = toks(text)[:WINDOW]
    return {"n_words_window": len(w), "rep_k": rep_k(w),
            "rep_frac": round(rep_frac(w), 4), "rep_onset": rep_onset(w)}


def fisher_2x2(a, b, c, d):
    """双侧 Fisher 精确检验（2x2）。自己算，免得依赖 scipy。

    a = 事件且属于 A 组, b = 非事件且属于 A 组
    c = 事件且属于 B 组, d = 非事件且属于 B 组
    """
    from math import comb

    n = a + b + c + d
    r1, c1 = a + b, a + c

    def p_of(x):
        return comb(r1, x) * comb(n - r1, c1 - x) / comb(n, c1)

    p0 = p_of(a)
    lo = max(0, c1 - (n - r1))
    hi = min(r1, c1)
    return sum(p_of(x) for x in range(lo, hi + 1) if p_of(x) <= p0 + 1e-12)


def rate_at(words, n_words, thresh=5):
    """在固定长度的前 n_words 词窗口里，强重复与否。

    全文不足 n_words 时返回 None —— 那一档长度**没有**控住，
    把它算进去等于偷偷比了全文。
    """
    if len(words) < n_words:
        return None
    return rep_k(words[:n_words]) >= thresh


# ---------------------------------------------------------------- 自证
print("=== 自证 ===")

# 4. 不重叠性。
# ⚠ 探针的单元长度**必须正好等于 k**。我第一版用了 11 词的句子配 k=12，
#   相位每 11 词才对齐一次，于是 100 份只报出 50 —— rep_k=50 才是对的，
#   错的是我的预期。第三版直接让脚本自己断言 len(unit) == K。
unit = ("the sum of phi is one thousand nine hundred seventy two exactly").split()
if len(unit) != K:
    ab("自证 4 前置：探针单元 %d 词，必须正好等于 K=%d，否则相位错位会让 "
       "rep_k 系统性偏低，门槛却看不出来" % (len(unit), K))
probe = unit * 100
if rep_k(probe) != 100:
    ab("自证 4 失败：同一句重复 100 次（%d 词），rep_k 报了 %r，应为 100"
       "（重叠计数会报 100+K-1=111）" % (len(probe), rep_k(probe)))
else:
    print("[PASS] 自证 4 不重叠性：重复 100 次 -> rep_k=100（重叠会报 111）")

# 4b. 探针长度下限：k=12 时给 84 个词（刚好 7 个）必须报 7，
#     而 83 个词最多只能报 6。这条防止以后有人把探针改短又看不懂失败。
if rep_k(unit * 7) != 7:
    ab("自证 4b 失败：84 词（刚好 7 个 12-gram）rep_k 报了 %r，应为 7"
       % rep_k(unit * 7))
elif rep_k(unit * 6 + ["x"] * 1) != 6:
    ab("自证 4b 失败：73 词最多 6 个不重叠 12-gram，rep_k 报了 %r"
       % rep_k(unit * 6 + ["x"]))
else:
    print("[PASS] 自证 4b 探针下限：84 词->7，73 词->6（长度不够时如实降级）")

# 2/3. 人工重复 vs 人工多样
loopy = " ".join(unit * 200)
# ⚠ 第一版写的是 `" ".join(unit) * 200` —— 那样两句之间**没有空格**，
#   `exactly` 会粘成 `exactlythe`，词边界被打乱，rep_k 从 66 掉到 36。
#   而它没有触发任何阈值告警：36 看着像个正常数字。
#   ⇒ 探针的构造方式本身就是判据的一部分，得让脚本自己查。
if "exactlythe" in loopy or loopy.split()[:K] != unit:
    ab("自证 2/3 前置：人工重复串的词边界不对（%r）" % loopy[:40])
# 「多样」必须用**逐词唯一**的序列。我第一版用 (i*7919)%1013，
# 那个序列周期 1013，4000 词里 12-gram 必然重复 3 次 ——
# 于是 rep_k=3 而我的门槛是 <=2，自证红了，但**指标是对的、门槛是错的**。
diverse = " ".join("uniq%d" % i for i in range(4000))
rk_loop, rk_div = rep_k(toks(loopy)[:WINDOW]), rep_k(toks(diverse)[:WINDOW])
if not (rk_loop >= 50 and rk_div == 1):
    ab("自证 2/3 失败：人工重复 rep_k=%r，人工多样 rep_k=%r（应 >=50 且 ==1）"
       % (rk_loop, rk_div))
else:
    print("[PASS] 自证 2/3 人工重复 rep_k=%d，人工逐词唯一 rep_k=%d"
          % (rk_loop, rk_div))

# 真实文本的基线（−v 闭合臂的量级，用来确认 50 这个门槛不是随便定的）
runs = json.load(open(RUNS, encoding="utf-8"))
if aborts:
    print("\nRESULT ABORT（%d 条自证未过）" % len(aborts))
    sys.exit(1)
print("\n=== 真实数据 ===")

# ---------------------------------------------------------------- 取数
# 三臂：零强度（两向共享）/ −v / +v，都限 L20 s=0.2 与零臂 s=0.0
arms = {"zero": [], "minus_v": [], "plus_v": []}
arm_words = {"zero": [], "minus_v": [], "plus_v": []}
seen_zero = set()
for r in runs:
    if r.get("layer") != 20:
        continue
    s, d = r.get("strength"), r.get("direction")
    pl = r.get("prompt_label") or r.get("label")
    if s == 0.0:
        key = "zero"
        # 零臂两向逐字相同 ⇒ 同一道题被存了两遍。23 vs 23 的比较里
        # 保留 46 条会让对照臂的分母翻倍，Fisher 检验直接失真。
        if pl in seen_zero:
            continue
        seen_zero.add(pl)
    elif s == 0.2 and d == "confidence_down":
        key = "minus_v"
    elif s == 0.2 and d == "confidence_up":
        key = "plus_v"
    else:
        continue
    txt = r.get("primary_text")
    m = measure(txt)
    m["prompt_label"] = pl
    m["closed_think"] = r.get("closed_think")
    m["full_n_words"] = len(toks(txt))
    arms[key].append(m)
    arm_words[key].append(toks(txt))

# 自证 1：窗口必须**真固定**。判据不是「三臂词数相同」，
#   而是「每一条 run 的窗口词数都等于 WINDOW」——少一条就说明有 run
#   全文比窗口还短，那条 arm 实际比的是全文，长度混淆就回来了。
short = {k: min(x["n_words_window"] for x in v) for k, v in arms.items() if v}
if not short or min(short.values()) < WINDOW:
    ab("自证 1 失败：有 run 的全文短于窗口 %d，最短 %r ⇒ 「固定窗口」退化成"
       "「全文」，长度又没控住" % (WINDOW, short))
else:
    print("[PASS] 自证 1 长度受控：全部 %d 条 run 的窗口词数都 = %d"
          % (sum(len(v) for v in arms.values()), WINDOW))

# 自证 5：零臂两向逐字相同 ⇒ 共享对照
zero_txt = {}
for r in runs:
    if r.get("layer") == 20 and r.get("strength") == 0.0:
        zero_txt[(r.get("direction"), r.get("prompt_label"))] = r.get("primary_text")
shared = 0
for pl in set(p for (_d, p) in zero_txt):
    a, b = zero_txt.get(("confidence_up", pl)), zero_txt.get(("confidence_down", pl))
    if a is not None and b is not None and a == b:
        shared += 1
if shared == 0:
    ab("自证 5 失败：零臂两向没有任何一道题逐字相同")
else:
    print("[PASS] 自证 5 零臂两向逐字相同 %d 题（共享对照前提仍成立）" % shared)

if aborts:
    print("\nRESULT ABORT（%d 条自证未过）" % len(aborts))
    sys.exit(1)


def summ(name, rows):
    rk = [x["rep_k"] for x in rows]
    rf = [x["rep_frac"] for x in rows]
    on = [x["rep_onset"] for x in rows if x["rep_onset"] is not None]
    return {"arm": name, "n": len(rows),
            "rep_k_median": statistics.median(rk), "rep_k_max": max(rk),
            "rep_k_mean": round(statistics.mean(rk), 2),
            "rep_frac_median": round(statistics.median(rf), 4),
            "rep_frac_max": round(max(rf), 4),
            "n_with_rep_ge5": sum(1 for v in rk if v >= 5),
            "n_with_rep_ge20": sum(1 for v in rk if v >= 20),
            "n_with_onset": len(on),
            "onset_median": statistics.median(on) if on else None}


summary = [summ(k, arms[k]) for k in ("zero", "minus_v", "plus_v")]
print()
for s in summary:
    print("  %-8s n=%-3d rep_k 中位 %-5g 最大 %-5g | rep_frac 中位 %-8g "
          "| rep_k>=5: %2d  >=20: %2d | 有重复的 %2d 条，onset 中位 %s"
          % (s["arm"], s["n"], s["rep_k_median"], s["rep_k_max"],
             s["rep_frac_median"], s["n_with_rep_ge5"], s["n_with_rep_ge20"],
             s["n_with_onset"], s["onset_median"]))

# ---------------------------------------------------------------- 切点扫描
# 为什么扫：只报一个窗口长度会掩盖两件相反的事。
#   窗口太短 -> 退化还没来得及发生，真差异被切掉（**漏掉**发现）；
#   窗口太长 -> 有 run 全文不够长，那一档其实比的是全文，长度混淆回来。
# 扫描能把这两件事都显出来：每一档都标出有多少 run 全文够长。
CUTS = (200, 400, 800, 1600, 3200)
THRESH = 5
sweep = []
print("\n=== 切点扫描（强重复 = 某 12-gram 不重叠出现 >= %d 次）===" % THRESH)
print("  %-6s %-14s %-10s %-10s %-10s %-9s %s"
      % ("词数", "入选 z/m/p", "zero", "minus_v", "plus_v", "p(+v/0)", "p(+v/-)"))
for c in CUTS:
    row = {"words": c}
    cnt, ok, elig = {}, {}, {}
    for a in ("zero", "minus_v", "plus_v"):
        use = [(w, x["prompt_label"]) for w, x in zip(arm_words[a], arms[a])
               if rate_at(w, c) is not None]
        elig[a] = [pl for _w, pl in use]
        cnt[a] = sum(1 for w, _pl in use if rate_at(w, c))
        ok[a] = len(use)
        row[a] = {"n_strong": cnt[a], "n_eligible": ok[a]}
    # ⚠ 这一档到底算不算长度受控？判据不是「三臂都有人入选」，
    #   而是「三臂入选的是**同一批题**」。窗口放大到超过某些 run 的全长时，
    #   入选题集按长度筛掉一些题 —— 而长度和未闭合相关、未闭合和 +v 相关，
    #   于是这一档的比较本身就在挑 +v 想赢的题。
    #   3200 词那档 p 最小（0.016），但入选题集是 16/19/18，**正是这个坑**。
    same = (set(elig["zero"]) == set(elig["minus_v"]) == set(elig["plus_v"]))
    row["same_problem_set"] = same
    row["verdict"] = "clean" if same else (
        "CONFOUNDED - 三臂入选题集不同，这一档的差可能是筛选造成的")

    a_, b_ = cnt["plus_v"], ok["plus_v"]
    c_, d_ = cnt["zero"], ok["zero"]
    m_ = cnt["minus_v"]
    if min(a_, b_, c_, d_) > 0:
        row["fisher_p_plus_vs_zero"] = round(fisher_2x2(a_, b_ - a_, c_, d_ - c_), 6)
        row["fisher_p_plus_vs_minus"] = round(
            fisher_2x2(a_, b_ - a_, m_, ok["minus_v"] - m_), 6)
    sweep.append(row)
    print("  %-6d %-14s %-10s %-10s %-10s %-9s %s"
          % (c, "%d/%d/%d" % (ok["zero"], ok["minus_v"], ok["plus_v"]),
             "%d/%d" % (cnt["zero"], ok["zero"]),
             "%d/%d" % (m_, ok["minus_v"]),
             "%d/%d" % (a_, b_),
             row.get("fisher_p_plus_vs_zero", "-"),
             row.get("fisher_p_plus_vs_minus", "-")))

clean = [r for r in sweep if r["same_problem_set"]]
print("\n  三臂入选同一批题（真长度受控）的档位: %s"
      % ", ".join("%d 词" % r["words"] for r in clean))
if clean:
    best = min(clean, key=lambda r: r.get("fisher_p_plus_vs_zero", 1))
    print("  \u21d2 最小 p 出现在 %d 词: p(+v vs 共享对照) = %s"
          % (best["words"], best.get("fisher_p_plus_vs_zero")))

payload = {
    "schema": "steer_repetition/1",
    "k_grams": K,
    "window_words": WINDOW,
    "strong_repeat_threshold": THRESH,
    "why_window": ("未闭合的臂按定义更长，比全长会把「长 ⇒ 重复多」"
                   "当成发现。只比开头固定词数，长度被控住。"),
    # ⚠ 这条说明会被**直接渲染**进页面，所以不许带 markdown 记号。
    #   我第一版写了「**不重叠**」，结果 markdown 星号漏到页面上，
    #   被渲染守卫 I0b 抓到 —— 那个守卫本来是给功效块写的。
    "nonoverlap_note": "rep_k 数的是不重叠出现次数，否则重复 N 遍会报成 N+K-1。",
    "dedup_note": "零臂两向逐字相同，按题去重成 23 条，否则对照臂分母翻倍。",
    "layer": 20,
    "strength": 0.2,
    "cut_sweep": sweep,
    "summary": summary,
    "per_run": {k: arms[k] for k in arms},
}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(payload, fh, ensure_ascii=False, indent=1)
print("\n写出 %s" % OUT)
print("RESULT OK - 五条自证全过")
