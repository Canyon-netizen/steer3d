"""修订 42 的本地先验：文档/预登记表格里的数字必须与产物**逐位**一致。

跑法：PYTHONPATH=.cache/pylibs python3 .cache/bpath/test_docs_token_tables.py

## 这些用例在钉什么

§4.3（修订 37）、§4.3b（修订 39）、§37.3 的表格数字**全部只以手写散文存在**，
产物一个也没有；构建器里 `position_check` 与 `n_tracks` 也都是硬编码。
改了产物而忘了改散文 ⇒ 逐字节复算照样通过、页面照样渲染，
**只有读者会在同一屏看到两个打架的数**。

所以这里钉的是：**文档里的每个数字都能追到产物的一个字段**。

## ⚠ 为什么末尾一定要有变异台架

一份「数字对得上」的检查，若所有变异都测不出它红，那就是**恒绿**，
即没有判据。本文件末尾对**每一个**判据都注入一次变异，
要求它变红，并且要求红的原因是**对的那一条**。

⚠ 变异**只改产物**（内存里的 dict），**不改文档文件** ——
这样不需要备份/回滚，也不会出现「跑到一半去读被测文档读到中间态」。
反向（改文档）另有一组变异。
"""
from __future__ import annotations

import copy
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
MUTBAK = os.path.join(ROOT, ".cache/mutbak")
DOC = os.path.join(ROOT, "docs/BPATH_MARKER_STEERING.md")
PREREG = os.path.join(ROOT, ".cache/xcheck/R6_RERUN_PREREG.md")
BUILT = os.path.join(ROOT, "frontend/public/latent/data/"
                            "bpath_marker_steering.json")

FAILS = []


def ok(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name
          + ("" if cond else f"  ← {detail}"))
    if not cond:
        FAILS.append(name)


# ---------------------------------------------------------------- 取文本
def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def section(text, header, nxt):
    i = text.find(header)
    if i < 0:
        raise SystemExit(f"找不到章节 {header!r}")
    j = text.find(nxt, i + len(header))
    return text[i:] if j < 0 else text[i:j]


def rows(seg):
    """抽出表格行 ⇒ [[cell, ...], ...]（跳过表头与分隔行）。"""
    out = []
    for line in seg.splitlines():
        s = line.strip()
        if not s.startswith("|") or not s.endswith("|"):
            continue
        cells = [c.strip() for c in s[1:-1].split("|")]
        if all(set(c) <= set("-: ") for c in cells):
            continue
        if cells and cells[0] in ("marker id", "位置层", ""):
            continue
        out.append(cells)
    return out


def bare(cell):
    """去掉加粗与空白，只留内容。"""
    return cell.replace("**", "").strip()


def cell_expect(neg, n, frac, footnote):
    """文档里那一格应当是什么：`k/n = x.xxx`，小样本再跟一个 `ᵃ`。"""
    s = f"{neg}/{n} = {frac:.3f}"
    return s + (" ᵃ" if footnote else "")


def pct_list(comp):
    """`M1.composition` ⇒ 各分位的 dom 百分比文本。"""
    return " → ".join(f"{a / (a + b):.0%}" for a, b in comp)


def near(lines, target, within=3):
    """返回 `target` 出现处 ±within 邻域内的**行内容**集合。

    ⚠ 这里必须返回**内容**而不是行号：早先返回行号集合再拿字符串去 `in`，
      恒为 False ⇒ 守卫报了两条**假红**（理由是假的，不是文档错了）。
      凡是「恒假」的判据，先怀疑判据。
    """
    idx = [i for i, l in enumerate(lines) if target in l]
    return {lines[j] for i in idx
            for j in range(max(0, i - within), min(len(lines), i + within + 1))}


# ---------------------------------------------------------------- 判据
def verify(doc, prereg, built, t1, t2, ps, mx, n_tracks):
    """跑完全部断言，返回**失败条目的名字**（空列表 = 全过）。

    ⚠ 返回失败名而不是就地打印，是为了让变异台架能复用同一段逻辑：
      真数据与变异数据走**完全相同**的代码路径。
    """
    bad = []

    def need(cond, name):
        if not cond:
            bad.append(name)

    doc43 = section(doc, "### 4.3 ", "### 4.3b ")
    doc43b = section(doc, "### 4.3b ", "### 4.3c ")
    pre373 = section(prereg, "### 37.3 ", "### 37.4 ")
    pre36 = section(prereg, "### 36.4", "### 37.1")

    # ---- §4.3 表格：逐 token 的 `k/n = x.xxx` + 脚注双向 ----
    r43 = {re.sub(r"\D", "", c[0]): c for c in rows(doc43) if c[0].strip("*").isdigit()}
    need(set(r43) == set(t1["per_token"]) | set(t2["per_token"]),
         f"§4.3 表的 marker 行 = 两批 per_token 的并集"
         f"（表 {sorted(r43)} vs 产物 {sorted(set(t1['per_token']) | set(t2['per_token']))}）")
    for tid, c in r43.items():
        for idx, (ver, tag) in enumerate(((t1, "E"), (t2, "hi"))):
            if tid not in ver["per_token"]:
                need(bare(c[idx + 2]) == "—",
                     f"§4.3 {tid} 在 {tag} 批应为「—」")
                continue
            pt = ver["per_token"][tid]
            want = cell_expect(pt["neg"], pt["n"], pt["neg_frac"],
                               not pt["reportable"])
            need(bare(c[idx + 2]) == want,
                 f"§4.3 {tid}@{tag} 单元格 = {want!r}"
                 f"（文档 {bare(c[idx + 2])!r}）")
            # ⚠ 脚注**双向**：漏标与多标都要红（修订 41 的规则，机器化）
            need(("ᵃ" in c[idx + 2]) == (not pt["reportable"]),
                 f"§4.3 {tid}@{tag} 脚注 ⇔ reportable==false")

    # ---- §4.3 表头：轨迹数与位点数 ----
    for ver, tag, nt in ((t1, "E", n_tracks[0]), (t2, "hi", n_tracks[1])):
        h = f"（{nt} 条 / {ver['n_sites']} 位点）"
        need(h in doc43, f"§4.3 表头 {tag} 批 = {h!r}")

    # ---- §4.3 散文：分层 CMH 的 χ² / p / 层数 ----
    for ver, tag in ((t1, "E"), (t2, "hi")):
        T1 = ver["T1"]
        c = format(T1["chi2_mh"], ".2f")
        need(f"χ² = {c}" in doc43, f"§4.3 {tag} 批 χ² = {c}")
        need(f"{T1['n_strata_used']} 层" in doc43,
             f"§4.3 {tag} 批层数 = {T1['n_strata_used']}")
        # ⚠ p = 0.0 时读者要看到「≈ 0」，不能去 format 一个 0
        ptxt = ("≈ 0" if T1["p_two_sided"] == 0.0
                else format(T1["p_two_sided"], ".1e"))
        need(f"p = {ptxt}" in doc43 or f"p {ptxt}" in doc43,
             f"§4.3 {tag} 批 p = {ptxt}")

    # ---- §37.3 位置分层：切点 + 逐层格子 + χ²（§4.3 也引了同一组率）----
    lo, hi = ps["cutpoints"]
    need(f"{lo}" in pre373 and f"{hi}" in pre373,
         f"§37.3 切点 = {lo} / {hi}")
    r37 = [c for c in rows(pre373) if "t" in c[0]]
    need(len(r37) == len(ps["strata"]),
         f"§37.3 表行数 = {len(ps['strata'])}")
    for c, s in zip(r37, ps["strata"]):
        for col, (neg, n, frac) in enumerate(
                ((s["dom_neg"], s["dom_n"], s["dom_neg_frac"]),
                 (s["rest_neg"], s["rest_n"], s["rest_neg_frac"])), start=1):
            want = cell_expect(neg, n, frac, False)
            need(bare(c[col]) == want,
                 f"§37.3 {s['label']} 第 {col} 列 = {want!r}"
                 f"（文档 {bare(c[col])!r}）")
    pc = format(ps["chi2_mh"], ".2f")
    need(f"**{pc}**" in pre373 or f"χ² = {pc}" in pre373,
         f"§37.3 χ² = {pc}")
    need(ps["cutpoint_def"] == "rank_third",
         f"切点定义仍是 rank_third（实际 {ps['cutpoint_def']!r}）")
    # ⚠ 另一个切法必须仍然给出不同的格子数，否则「定义会改答案」这句话就是假的
    alt = ps["cutpoint_sensitivity"]["other_strata"][1]
    need(alt["rest_n"] != ps["strata"][1]["rest_n"],
         "切点敏感性：np.percentile 下中间层 rest_n 必须与 rank_third 不同")

    # ---- §4.3 正文引用的三个位置分层率 ----
    rates = " / ".join(format(s["dom_neg_frac"], ".3f") for s in ps["strata"])
    need(rates in doc43, f"§4.3 位置分层三率 = {rates!r}")

    # ---- §4.3b 表格：整体 / 7196 / 其余 × Q1–Q4 + 极差 ----
    p_, s_ = mx["primary"], mx["secondary"]
    r43b = {bare(c[0]): c for c in rows(doc43b)}
    for key, blk in (("整体同号率", p_["overall"]), ("7196 组", p_["dom"]),
                     ("其余组", p_["rest"])):
        c = r43b.get(key)
        need(c is not None, f"§4.3b 表有 {key!r} 行")
        if c is None:
            continue
        for i in range(4):
            need(bare(c[i + 1]) == f"{blk['rates'][i]:.3f}",
                 f"§4.3b {key} Q{i + 1} = {blk['rates'][i]:.3f}"
                 f"（文档 {bare(c[i + 1])!r}）")
        need(bare(c[5]) == f"{blk['range']:.3f}",
             f"§4.3b {key} 极差 = {blk['range']:.3f}")

    # ---- §4.3b 的 M1 / M2 / M3（**主口径**）----
    need(f"χ² = {format(p_['M1']['chi2'], '.2f')}" in doc43b,
         f"§4.3b 主口径 M1 χ² = {format(p_['M1']['chi2'], '.2f')}")
    need(format(p_["M1"]["p"], ".1e") in doc43b,
         f"§4.3b 主口径 M1 p = {format(p_['M1']['p'], '.1e')}")
    for r, tag in ((p_["M2"]["dom_range"], "7196"), (p_["M2"]["rest_range"], "其余")):
        need(f"{r:.3f}" in doc43b, f"§4.3b M2 {tag} 极差 = {r:.3f}")
    need(f"{format(p_['M3']['gain'], '.3f')}" in doc43b,
         f"§4.3b M3 增益 = {format(p_['M3']['gain'], '.3f')}")
    need(f"{format(s_['M3']['gain'], '.3f')}" in doc43b,
         f"§4.3b 次要口径增益 = {format(s_['M3']['gain'], '.3f')}")
    need(format(s_["M1"]["p"], ".1e") in doc43b,
         f"§4.3b 次要口径 M1 p = {format(s_['M1']['p'], '.1e')}")

    # ---- §4 第 12 条：同一 bullet 里的数字必须同一口径 ----
    L = doc43b.splitlines()
    a_pri = pct_list(p_["M1"]["composition"])     # 主口径 76% → 43% …
    a_sec = pct_list(s_["M1"]["composition"])     # 次要口径 78% → 57% …
    need(a_pri in doc43b, f"§4.3b 主口径构成 = {a_pri!r}")
    need(a_sec in doc43b, f"§4.3b 次要口径构成 = {a_sec!r}")
    for arrow, chi, tag in ((a_pri, format(p_["M1"]["chi2"], ".2f"), "主"),
                            (a_sec, format(s_["M1"]["p"], ".1e"), "次")):
        # ⚠ 必须 `any(... in line)`：**集合成员是整行**，`arrow in 集合`
        #   是**精确相等**而不是子串包含 —— 那样恒假。
        need(any(arrow in l for l in near(L, chi)),
             f"§4.3b {tag}口径：构成与它的统计量在同一条 bullet")
    # ⚠ 反向：主口径的构成不许出现在次要口径那条附近
    need(not any(a_pri in l
                 for l in near(L, format(s_["M1"]["p"], ".1e"), within=2)),
         f"§4.3b 次要口径那条附近**没有**主口径构成（否则又是口径错配）")
    need("主口径" in doc43b, "§4.3b 把口径写出来了")

    # ---- 构建器：数字必须由产物拼出，不能硬编码 ----
    t37 = built.get("orthogonality", {}).get("token_id37", {})
    need("position_strat" in t37, "交付 JSON 带 position_strat 块")
    if "position_strat" in t37:
        slim = {k: v for k, v in ps.items() if k not in ("probe", "map")}
        need(t37["position_strat"] == slim,
             "交付 JSON 的 position_strat = 产物（剥掉本机路径）")
        need("probe" not in t37["position_strat"] and "map" not in t37["position_strat"],
             "交付 JSON 里没有本机路径")
    pc_txt = t37.get("position_check", "")
    need(rates in pc_txt, f"position_check 的三率跟随产物（{rates}）")
    need(f"χ² = {pc}" in pc_txt, f"position_check 的 χ² 跟随产物（{pc}）")
    need(ps["cutpoint_def"] in pc_txt, "position_check 写出切点定义")
    for b, nt in zip(t37.get("batches", []), n_tracks):
        need(b.get("n_tracks") == nt,
             f"交付 JSON 的 n_tracks = {nt}（面板会渲染它）")
    return bad


# ---------------------------------------------------------------- 主流程
print("== 1. 读真实产物与文档 ==")


def jread(name):
    return json.loads(read(os.path.join(MUTBAK, name)))


t1 = jread("token_id_verdict.json")
t2 = jread("token_id_verdict_hi.json")
ps = jread("pos_strat.json")
mx = jread("mixture_verdict.json")
built = json.loads(read(BUILT))
for nm in ("token_id_verdict.json", "token_id_verdict_hi.json",
           "pos_strat.json", "mixture_verdict.json"):
    ok(f"产物存在：{nm}", os.path.exists(os.path.join(MUTBAK, nm)))
doc = read(DOC)
prereg = read(PREREG)
def _traj_count(verdict):
    """从判决产物**点名的那份探针**里数轨迹（与构建器 `_n_tracks` 同一条链）。"""
    p = verdict["probe"]
    p = p if os.path.isabs(p) else os.path.join(ROOT, p)
    return len({r["traj"] for r in json.loads(read(p))["rows"]})


n_tracks = [_traj_count(t1), _traj_count(t2)]
ok("文档/预登记 0 坏字", doc.count("\ufffd") == 0 and prereg.count("\ufffd") == 0)

print("\n== 2. 真数据必须全过 ==")
bad = verify(doc, prereg, built, t1, t2, ps, mx, n_tracks)
ok(f"真数据 {len(bad)} 条判据全过", not bad, str(bad[:6]))

print("\n== 3. 变异自证：每条判据都得有牙齿 ==")
# ⚠ 逐个变异，每个都必须让 verify 变红；全绿 = 没有判据。
#   变异**只改产物**（内存 dict），不动任何文档文件。
MUTS = [
    ("§4.3 某格的负向数改了", "per_token", "neg"),
    ("§4.3 某格的分母改了", "per_token", "n"),
    ("§4.3 某格的 reportable 被翻", "reportable", None),
    ("§4.3 表头的位点数改了", "n_sites", None),
    ("§4.3 散文的 χ² 改了", "T1_chi2", None),
    ("§37.3 切点改了", "cutpoints", None),
    ("§37.3 某层格子改了", "strata", None),
    ("§37.3 的 χ² 改了", "ps_chi2", None),
    ("§37.3 切点定义被换掉", "cutpoint_def", None),
    ("§4.3b 某格的分位率改了", "rates", None),
    ("§4.3b 的 M1 p 改了", "m1p", None),
    ("§4.3b 的 M3 增益改了", "m3gain", None),
    ("§4.3b 构成被换成另一口径", "caliber_swap", None),
    ("构建器的 position_strat 不跟产物", "built_posstrat", None),
    ("构建器的 n_tracks 被写死成别的数", "built_ntracks", None),
]


def mutate(kind, key):
    a, b, c, d, e = (copy.deepcopy(t1), copy.deepcopy(t2),
                     copy.deepcopy(ps), copy.deepcopy(mx),
                     copy.deepcopy(built))
    if kind == "per_token":
        a["per_token"]["7196"]["neg"] += 3
    elif kind == "n":
        a["per_token"]["7196"]["n"] -= 2
    elif kind == "reportable":
        a["per_token"]["13824"]["reportable"] = True     # 脚注应随之消失
    elif kind == "n_sites":
        a["n_sites"] = 180
    elif kind == "T1_chi2":
        a["T1"]["chi2_mh"] = round(a["T1"]["chi2_mh"] + 1.0, 4)
    elif kind == "cutpoints":
        c["cutpoints"] = [2938, 5106]
    elif kind == "strata":
        c["strata"][1]["rest_n"] = 13
    elif kind == "ps_chi2":
        c["chi2_mh"] = round(c["chi2_mh"] / 33.0, 4)     # 忘了平方分子的那个值
    elif kind == "cutpoint_def":
        c["cutpoint_def"] = "np.percentile"
    elif kind == "rates":
        # ⚠ 必须改到**显示精度之外**才测得到：`0.7061` 的 `.3f` 仍是 `0.706`，
        #   改了产物而显示值不变 ⇒ 文档确实还是对的，守卫理应不红。
        #   这个边界由下面 `pre_display_precision` 单独钉住。
        d["primary"]["overall"]["rates"][2] = 0.7201
    elif kind == "m1p":
        d["primary"]["M1"]["p"] = 9.9e-05
    elif kind == "m3gain":
        d["primary"]["M3"]["gain"] = 0.4401
    elif kind == "caliber_swap":
        # ⚠ 最要紧的一支：把主口径的构成换成次要口径的（修订 42 抓到的原缺陷）
        d["primary"]["M1"]["composition"] = \
            copy.deepcopy(d["secondary"]["M1"]["composition"])
    elif kind == "built_posstrat":
        e["orthogonality"]["token_id37"]["position_strat"]["chi2_mh"] = 1.0
    elif kind == "built_ntracks":
        e["orthogonality"]["token_id37"]["batches"][0]["n_tracks"] = 25
    return a, b, c, d, e


for name, kind, key in MUTS:
    a, b, c, d, e = mutate(kind, key)
    got = verify(doc, prereg, e, a, b, c, d, n_tracks)
    ok(f"变异「{name}」能让守卫变红", bool(got),
       "verify 仍然全绿 ⇒ 这条判据没有牙齿")

print("\n== 4. 反向变异：改文档/预登记也必须红 ==")
for name, which, old, new in [
    ("§4.3 某格的比率改了", "doc", "121/125 = 0.968", "121/125 = 0.969"),
    # ⚠ `144.86` 的判据在**预登记** §37.3 里（doc §4.3 只是引用它）。
    #   第一版这条变异只改 doc ⇒ 守卫当然不红 ⇒ 测了个寂寞。
    ("§37.3 的 χ² 改了", "prereg", "144.86", "144.87"),
    ("§37.3 某层的分母改了", "prereg", "45/46 = 0.978", "45/47 = 0.978"),
    ("§4.3b 某格的分位率改了", "doc", "0.706", "0.707"),
]:
    base = doc if which == "doc" else prereg
    ok(f"{which} 变异「{name}」已生效", old in base and new not in base,
       f"{which} 里找不到待替换的原文，变异没生效 ⇒ 这条测不到东西")
    if which == "doc":
        bad2 = verify(doc.replace(old, new, 1), prereg, built,
                      t1, t2, ps, mx, n_tracks)
    else:
        bad2 = verify(doc, prereg.replace(old, new, 1), built,
                      t1, t2, ps, mx, n_tracks)
    ok(f"{which} 变异「{name}」能让守卫变红", bool(bad2),
       "verify 仍然全绿 ⇒ 这条判据没有牙齿")

print("\n== 4b. 精度边界：显示精度以下的变动**故意**抓不到 ==")
# ⚠ 本守卫比的是**格式化后的显示值**（文档里就是显示值）。
#   所以产物在显示精度以下的变动**抓不到** —— 这不是缺陷，
#   但必须写下来，否则以后会有人以为守卫漏了。
_e = copy.deepcopy(mx)
_e["primary"]["overall"]["rates"][2] = 0.7061        # .3f 仍是 0.706
_g = copy.deepcopy(mx)
_g["primary"]["M3"]["gain"] = 0.4321                  # .3f 仍是 0.432
ok("显示精度以下的产物变动不会被当成缺陷（rate 0.7061）",
   not verify(doc, prereg, built, t1, t2, ps, _e, n_tracks))
ok("显示精度以下的产物变动不会被当成缺陷（gain 0.4321）",
   not verify(doc, prereg, built, t1, t2, ps, _g, n_tracks))
# ⚠ 反过来：精度**不够**就会出事（修订 40 的 enrich 教训）⇒ 断言产物留足位数
ok("产物留住足够显示位数（M1.p 未被四舍五入成 0.0）",
   format(mx["primary"]["M1"]["p"], ".1e") != "0.0e+00",
   f"p = {mx['primary']['M1']['p']!r}")

print("\n== 5. 关键反例：文档数字真的对得上吗（人工可读）==")
print(f"  §4.3  E 7196 = {cell_expect(t1['per_token']['7196']['neg'], t1['per_token']['7196']['n'], t1['per_token']['7196']['neg_frac'], False)}")
print(f"  §37.3 切点 = {ps['cutpoints']}（{ps['cutpoint_def']}）"
      f" ⇒ χ² = {format(ps['chi2_mh'], '.2f')}")
print(f"  §4.3b 主口径构成 = {pct_list(mx['primary']['M1']['composition'])}"
      f" / 次要 = {pct_list(mx['secondary']['M1']['composition'])}")

print()
if FAILS:
    print(f"**先验失败 {len(FAILS)} 项**：{FAILS}")
    sys.exit(1)
print("先验全过")