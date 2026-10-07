#!/usr/bin/env python3
"""LTV 的 G-c 行为判定器：**只按词表数特征**，不下最终判决。

## 它为什么长这样（而不是「让模型来判断」）

`LTV_PREREG.md` 修订 4 已经在**取任何生成文本之前**把下面四样全部写死了：
① 注入点与强度定标、② 三臂、③ 11 个特征的词表、④ 判决规则。
本文件是那份文件的**实现**，逐条照抄，不许在这里挑 α、不许改词表、
不许在事后把某个词从一个轴挪到另一个轴。

⚠ 不用 LLM 当裁判：本项目已经吃过「换题臂混着陌生度失配」的亏，
  证据在 `PATH_PATCHING_PREREG.md` 的修订记录里。判定只用这张词表。

## 词表的来源

`ltv_sentences.py` 里每个轴的 S 与 S′。每条只收「**S 相对 S′ 多出来的
那个语言特征**」，不收 S′ 独有的。所以这份表**照着定义写**，
不是照着生成结果写 —— 后者就是事后编指标。

⚠ 已知重叠：`perhaps` 同时出现在 `exploratory` 与 `hesitant`
  （`hesitant` 的 S 是「I think … might」，`exploratory` 的 S 是
  「Perhaps a different approach」）。**照实保留**，事后不许挪轴。

## 归一化

三臂的正文长度不同，不归一就是在比长度。计数一律 **按 1000 个词**。

用法:
    python3 .cache/xcheck/ltv_behavior.py .cache/xcheck/ltv_gen.json
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# ---- 词表：逐条照抄 LTV_PREREG.md 修订 4 ③，顺序与大小写都不改 --------------
#   每条写成「小写化的词边界正则」。`person_ctrl` 用第一人称单数的边界匹配。
FEATURES = {
    "confident": [r"so we can", r"build on", r"therefore", r"thus", r"clearly",
                  r"obviously", r"definitely", r"must be", r"that gives"],
    "hesitant":  [r"i think", r"\bmight\b", r"\bmaybe\b", r"perhaps",
                  r"not sure", r"could be", r"seems"],
    "deliberate":[r"carefully", r"before moving on", r"methodically"],
    "brisk":     [r"moving on", r"\bnext,", r"let's proceed"],
    "early_setup": [r"\bfirst,", r"let's set up", r"we set up", r"start with"],
    "late_chain": [r"combining", r"in total", r"altogether", r"as a whole"],
    "exploratory": [r"perhaps", r"another approach", r"alternative", r"what if",
                    r"could also"],
    "verify_mode": [r"double-check", r"double check", r"verify", r"make sure",
                    r"check again"],
    # ↓ 以下三条是**负对照**：与 steering 无关，只是写法不同（修订 4 ④G-c.3）
    "len_control":  [r"considering the", r"with respect to", r"in terms of",
                     r"that having been said"],
    "person_ctrl":  [r"\bi\b", r"\bi'm\b", r"\bi'll\b", r"\bi've\b"],
    "register_ct":  [r"\bjust\b", r"basically", r"kinda", r"gonna", r"\bstuff\b",
                     r"no big deal"],
}
NEGATIVE_KEYS = ("len_control", "person_ctrl", "register_ct")
PRIMARY_KEY = "confident"
# -----------------------------------------------------------------------------

# 分词：修订 4 ③「按 \b[A-Za-z']+\b 切，先把文本小写化」
_WORD = re.compile(r"[A-Za-z']+")
_COMPILED = {k: [re.compile(p) for p in v] for k, v in FEATURES.items()}


def n_words(text):
    return max(1, len(_WORD.findall(text)))


def rate(text, key):
    """该特征在正文里的**每千词出现次数**。"""
    low = text.lower()
    hits = sum(len(p.findall(low)) for p in _COMPILED[key])
    return 1000.0 * hits / n_words(text)


def per_run(runs):
    """逐次生成算 11 个特征的率。"""
    out = []
    for r in runs:
        row = {"pid": r["pid"], "alpha": r["alpha"], "arm": r["arm"],
               "n_words": n_words(r["text"]),
               "sha1": (r.get("text_sha_1") or "")[:12]}
        for k in FEATURES:
            row[k] = rate(r["text"], k)
        out.append(row)
    return out


def pooled(rows, pid=None):
    """按**词数**加权池化，而不是按次数的算术平均。

    ⚠ 加权是有理由的：三次生成的长度不同，算术平均会让短的那次权重过大。
      这里用 Σ命中 / Σ词数 ×1000，也就是把三段文本拼起来数。
    """
    sel = [r for r in rows if pid is None or r["pid"] == pid]
    res = {"n_runs": len(sel), "n_words": sum(r["n_words"] for r in sel)}
    for k in FEATURES:
        hits = 0.0
        for r in sel:
            # 由 rate 与 n_words 反推命中数，浮点误差远小于计数粒度
            hits += r[k] * r["n_words"] / 1000.0
        res[k] = 1000.0 * hits / res["n_words"] if res["n_words"] else 0.0
    return res


def pooled_where(rows, **eq):
    """按任意字段等值过滤后，**词数加权**池化。

    与 `pooled` 同一份数学（Σ命中 / Σ词数 ×1000），只是过滤条件不写死成 pid。
    判决要「固定一档 α、跨三题池化」，若在 build 侧另写一份池化，
    两处数学一旦漂移，判决读数就对不上 `ltv_behavior.json` 印出来的那份。
    ⇒ 共用这一处实现。
    """
    sel = [r for r in rows if all(r.get(k) == v for k, v in eq.items())]
    res = {"n_runs": len(sel), "n_words": sum(r["n_words"] for r in sel)}
    if not sel:
        return None
    for k in FEATURES:
        hits = 0.0
        for r in sel:
            hits += r[k] * r["n_words"] / 1000.0
        res[k] = 1000.0 * hits / res["n_words"] if res["n_words"] else 0.0
    return res


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "ltv_gen.json")
    g = json.load(open(src, encoding="utf-8"))
    rows = per_run(g["runs"])

    # 装置自检：三臂的文本**必须**真的有差别。
    #   否则下面所有比较都是恒真（arm == rand == zero 时，
    #   `arm > rand` 会因为浮点噪声偶然成立或偶然不成立，没有信息量）。
    sig = {}
    for pid in g["holdout"]:
        for alpha in g["alphas"]:
            texts = {r["arm"]: r.get("sha1") for r in rows
                     if r["pid"] == pid and r["alpha"] == alpha}
            sig[(pid, alpha)] = len(set(texts.values()))
    n_same = sum(1 for v in sig.values() if v == 1)
    print(f"装置自检：{len(sig)} 个 (题,α) 组合里，三臂文本完全相同的 "
          f"{n_same} 个（应为 0 或少数极小 α）")
    for (pid, alpha), n in sorted(sig.items()):
        if n == 1:
            print(f"  ⚠ {pid[-16:]} α={alpha}: 三臂文本**逐字相同** ⇒ 这一格没有信息量")

    out = {"schema": "steer3d.ltv_behavior/1",
           "prereg": "LTV_PREREG.md 修订 4",
           "source": os.path.basename(src),
           "n_runs": len(rows),
           "primary_key": PRIMARY_KEY,
           "negative_keys": list(NEGATIVE_KEYS),
           "note": "本文件只出数与装置自检，判决在 build_ltv.py",
           "per_run": rows,
           "pooled_all": pooled(rows)}
    out["pooled_by_problem"] = {
        pid: {str(a): pooled(rows, pid) for a in g["alphas"]} for pid in g["holdout"]}
    dst = os.environ.get("OUT", os.path.join(HERE, "ltv_behavior.json"))
    json.dump(out, open(dst, "w"), ensure_ascii=False, indent=1)
    print(f"已写出 {dst}")

    # 摘要：三臂在主特征上的率
    print(f"\n{'题':<18}{'α':<7}{'arm':>10}{'rand':>10}{'zero':>10}")
    for pid in g["holdout"]:
        for a in g["alphas"]:
            sel = [r for r in rows if r["pid"] == pid and r["alpha"] == a]
            by = {r["arm"]: r[PRIMARY_KEY] for r in sel}
            print(f"{pid[-16:]:<18}{a:<7}{by.get('arm',0):>10.3f}"
                  f"{by.get('rand',0):>10.3f}{by.get('zero',0):>10.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())