#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 90 调查：量化「3 个产物本项无判据」的口径影响面 + 反事实测量。

本脚本是**诊断探针**，不是判据，不判红、不判绿，只发数。

════════ 要回答的两个问题 ════════

【问题一 · 口径】Y2 母判据 :502 的 PASS 标题印「N 个叶子」，
  但源码 :158 在排除判定（:164）**之前**就累加 n_leaves_total，
  而 :171 `continue` 让被排除的产物**从不进入** :180 的逐字段判定。
  ⇒ 标题的分母 ≠ 判据的施加面。被排除的叶子占多少？

【问题二 · 反事实】⚠ 只知道「占 37.1%」**推不出缺陷** ——
  如果那 3 个产物就算不排除、逐字段判也找不到未渲染，
  那这个排除就是无害的，标题分母只是个排版瑕疵。
  ⇒ 必须隔一次反事实测量：**关掉排除表**跑同一判据，
    看它会翻出多少未渲染字段名。
  翻出 0 ⇒ 只是措辞问题；翻出 N>0 ⇒ 排除正在遮蔽 N 条欠账。

════════ 仪器可信度怎么保证 ════════
⚠⚠ 本脚本要**重新实现**母判据的字段名判定逻辑（否则只能靠改冻结文件，
  那是改判据，必须单独立修订）。
  ⇒ 所以先**用母判据自己的答案校准**：在 32 个判据已给答案的产物上，
    本脚本的「字段名数」与「未渲染数」必须与它打印的**逐行相等**，
    对不上就 exit 2 不发数。
  ⇒ 校准过了，才允许把同一套逻辑用到那 3 个「母判据没给答案」的产物上。

⚠ 口径不可混用：叶子数 ≠ 字段名数 ≠ 产物数，三者分开印。
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FE = ROOT / "frontend"
Y2_OUT = ROOT / ".cache/mutbak/y2_run.txt"

# 与母判据 :42-43 逐字一致（本脚本不改判据，只是照抄常量）
EXCL_MIN_LEAVES = 2000
EXCL_MAX_STR_RATIO = 0.01


# ═══ 路径A：独立复算 ═══════════════════════════════════════════════

def walk(obj, path="", acc=None):
    """独立实现：递归收集 (path, 叶子值)。

    ⚠ 刻意**不用**母判据的 generator+acc 写法 —— 那个写法第一版
      `acc` 永远是空的（母判据 :67-72 记着这个恒真）。这里用纯返回值 +
      调用方持有的列表，结构上不可能出现「yield 了但没 append」。
    ⚠ 返回 (叶子数, 字符串叶子数, 叶子路径列表)。
    """
    if acc is None:
        acc = []
    if isinstance(obj, dict):
        t = s = 0
        for k, v in obj.items():
            a, b, acc = walk(v, f"{path}.{k}" if path else str(k), acc)
            t += a
            s += b
        return t, s, acc
    if isinstance(obj, list):
        t = s = 0
        for i, v in enumerate(obj):
            a, b, acc = walk(v, f"{path}[{i}]", acc)
            t += a
            s += b
        return t, s, acc
    # 母判据 :66 —— None 不算；空串不算
    if obj is None or (isinstance(obj, str) and obj == ""):
        return 0, 0, acc
    acc.append(path)
    return 1, (1 if isinstance(obj, str) else 0), acc


def field_names(leaf_paths):
    """收集 distinct 字段名（母判据 :173-177 的语义）。

    ⚠⚠ 只从**叶子路径**取名 —— 这是本脚本第一版的 bug：
       我在每个 dict 中间层也取了一次名，于是多算了 ~10%。
       母判据遍历的是 `acc`（叶子序列），中间容器路径**从不**取名。
       ⇒ dict 容器的键名不会成为字段名（除非它另有叶子）；
          list 容器的键名**会**成为字段名（叶子路径带 `[i]`，:79-81 取 `[` 前的头）。
    """
    out = {}
    for p in leaf_paths:
        nm = _field_name(p)
        if nm and nm not in out:
            out[nm] = p
    return out


def _field_name(path: str) -> str:
    """母判据 :77-82 逐字复刻。"""
    name = path.rsplit(".", 1)[-1] if "." in path else path
    if "[" in name:
        head = name.partition("[")[0]
        name = head if head else name
    return name


def name_pattern(name: str) -> re.Pattern:
    """母判据 :50-51 逐字复刻。"""
    esc = re.escape(name)
    return re.compile(rf"(?<![A-Za-z0-9_]){esc}(?![A-Za-z0-9_])")


def load_hosts():
    """母判据 :121-128：components/*.tsx + public/latent/index.html。"""
    hs = {}
    for p in sorted(FE.glob("components/*.tsx")):
        hs[p] = p.read_text(encoding="utf-8")
    idx = FE / "public/latent/index.html"
    if idx.exists():
        hs[idx] = idx.read_text(encoding="utf-8")
    return hs


def unrendered_for(names: dict, owner_srcs: list) -> list:
    """母判据 :179-183 的语义。"""
    return [nm for nm in sorted(names)
            if not any(name_pattern(nm).search(s) for s in owner_srcs)]


def classify_elsewhere(name: str) -> list:
    """这个名字在前端**其它**源码（排除它自己的宿主）里出现过没有。

    ⚠ 为什么要分这一层：Y2 的判据是「字段名出现在**该产物的归属宿主**里」。
      一个字段名在别的面板出现，对本产物不算「已渲染」——
      ⇒ 「未渲染」里必然混着「判据按产物作用域造成的假阳性」。
    ⚠ 只扫源码（tsx/ts/html），**不扫** .next 产物 —— 那个目录比源码旧
      （修订 87 已确认 `frontend/.next` 与源码不同批次）。
    """
    hits = []
    for p, s in hs_all.items():
        if name_pattern(name).search(s):
            hits.append(p.name)
    return hits


def generic_iteration_hosts(hs: dict) -> dict:
    """宿主里有没有「通用 key 迭代」这种**不具名也能渲染**的写法。

    ⚠⚠ 这是判据的**结构性盲区**：若宿主写的是
      `Object.entries(verdict).map(([k,n]) => …)`，
      那它渲染屏幕上出现的**每一个** key，源码里却一个 key 名都没有
      ⇒ 「字段名没出现在源码」对这类宿主**不成立**，
      判据会把已渲染的字段报成未渲染。
    ⇒ 所以这 64 条**不能**直接读成「页面上没渲染」。
    """
    pats = ("Object.keys", "Object.entries", "Object.values",
            "for (const k ", "for (const key ")
    out = {}
    for p, s in hs.items():
        n = sum(s.count(x) for x in pats)
        if n:
            out[p.name] = n
    return out


# ═══ 路径B：解析母判据自己印的行 ════════════════════════════════════

hs_all = None  # classify_elsewhere 用：整个前端源码（不只宿主）


def rel_of(name: str) -> str:
    return ("public/latent/models.json" if name == "models.json"
            else f"public/latent/data/{name}")


def parse_y2_printed():
    if not Y2_OUT.exists():
        print(f"[错误] 找不到母判据输出 {Y2_OUT}")
        sys.exit(2)
    txt = Y2_OUT.read_text(encoding="utf-8")
    per_art = {}
    for m in re.finditer(
            r"^\s*(?:⚠ )?(\S+\.json)\s+叶子\s+(\d+)\s+字段名\s+(\d+)\s+深度\s+(\d+)\s+未渲染\s+(\d+)",
            txt, re.M):
        per_art[m.group(1)] = {"leaves": int(m.group(2)), "fields": int(m.group(3)),
                               "depth": int(m.group(4)), "unrendered": int(m.group(5))}
    excl = set(re.findall(r"⚠ 本项对 (\S+\.json) \*\*无判据\*\*", txt))
    total = None
    m = re.search(r"扫到叶子字段 (\d+) 个", txt)
    if m:
        total = int(m.group(1))
    return per_art, excl, total


def main():
    global hs_all
    hs = load_hosts()
    print(f"[口径·宿主] 扫到宿主源码 {len(hs)} 个（要求 > 0）")

    # 全前端源码（用于「这个名字在别处有没有」的分类）。
    # ⚠ 刻意**排除** node_modules 与 .next —— 修订 87 已确认
    #   `frontend/.next` 比源码旧（text-[9px] 源码 90 处 / .next 产物 0 次），
    #   拿旧产物当证据会得出「已渲染」的假阴性。
    hs_all = {}
    for pat in ("components/*.tsx", "lib/*.ts", "app/**/*.tsx", "app/**/*.ts",
                "public/*.html", "public/latent/*.html"):
        for p in sorted(FE.glob(pat)):
            try:
                hs_all[p] = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                pass
    print(f"[口径·全前端源码] 扫到 {len(hs_all)} 个文件（要求 > 0；已排除 node_modules 与 .next）")

    files = sorted((FE / "public/latent/data").glob("*.json")) + [FE / "public/latent/models.json"]
    rows = []
    for f in files:
        if not f.exists():
            print(f"[错误] 产物不存在：{f}")
            sys.exit(2)
        # ⚠⚠ 变量名必须与宿主区分：本脚本第一版把产物自己的源码也叫 `src`，
        #   于是 `f.name in src` 问的是「文件名在不在**它自己**里」⇒ owners 恒空
        #   ⇒ 每个字段名都被算成未渲染（A==n_fields，一眼就该看出不对）。
        #   母判据 :147 问的是「文件名在不在**宿主源码**里」，方向相反。
        art_src = f.read_text(encoding="utf-8")
        owner_paths = [h for h, h_src in hs.items() if f.name in h_src]
        owner_srcs = [hs[h] for h in owner_paths]
        data = json.loads(art_src)
        n, n_str, leaf_paths = walk(data)
        ratio = n_str / n if n else 0.0
        excluded = (n >= EXCL_MIN_LEAVES and ratio < EXCL_MAX_STR_RATIO)
        # ⚠ 无论排不排除，都照算字段名 —— 排除与否只影响「母判据用不用它」，
        #   不影响「它有多少字段名」。这正是反事实测量的前提。
        names = field_names(leaf_paths)
        unr = unrendered_for(names, owner_srcs)
        rows.append({"name": f.name, "leaves": n, "n_str": n_str, "ratio": ratio,
                     "excluded": excluded, "n_fields": len(names), "n_unrendered": len(unr),
                     "unrendered_names": unr,
                     "owner_names": sorted(h.name for h in owner_paths)})

    n_all = sum(r["leaves"] for r in rows)
    n_excl = sum(r["leaves"] for r in rows if r["excluded"])
    n_scope = n_all - n_excl
    excl_rows = [r for r in rows if r["excluded"]]

    print("\n" + "=" * 78)
    print("【问题一 · 口径】PASS 标题的分母 vs 判据的施加面")
    print("=" * 78)
    print(f"\n[口径·产物数] 扫到产物 {len(rows)} 个，其中按 E1/E2 排除 {len(excl_rows)} 个"
          f" ⇒ 占 {len(excl_rows)/len(rows)*100:.1f}%")
    print(f"[口径·叶子数] 全站叶子 {n_all} 个（= 母判据 PASS 标题那个分母）")
    print(f"[口径·叶子数] 其中**判据未施加**的 {n_excl} 个 ⇒ 占 {n_excl/n_all*100:.1f}%")
    print(f"[口径·叶子数] 判据实际施加的 {n_scope} 个 ⇒ 标题分母里只有 "
          f"{n_scope/n_all*100:.1f}% 真的被逐字段判过")

    print(f"\n[排除项明细]（E1 叶子≥{EXCL_MIN_LEAVES} 且 E2 字符串占比<"
          f"{EXCL_MAX_STR_RATIO*100:.0f}%）")
    for r in excl_rows:
        print(f"  {r['name']:<22} 叶子 {r['leaves']:>7}（占全站 {r['leaves']/n_all*100:>4.1f}%）"
              f"  字符串占比 {r['ratio']*100:.2f}%")

    # ── 仪器校准：32 个有答案的产物，本脚本必须与母判据逐行相等 ──────
    print("\n" + "=" * 78)
    print("【仪器校准】本脚本 vs 母判据自己印的行（对不上一律不发数）")
    print("=" * 78)
    pa, pex, ptotal = parse_y2_printed()
    bad_leaf, bad_field, bad_unr = [], [], []
    n_cmp = 0
    for r in rows:
        rel = rel_of(r["name"])
        if rel not in pa:
            continue
        n_cmp += 1
        b = pa[rel]
        if b["leaves"] != r["leaves"]:
            bad_leaf.append(f"{rel}: A={r['leaves']} B={b['leaves']}")
        if b["fields"] != r["n_fields"]:
            bad_field.append(f"{rel}: A={r['n_fields']} B={b['fields']}")
        if b["unrendered"] != r["n_unrendered"]:
            bad_unr.append(f"{rel}: A={r['n_unrendered']} B={b['unrendered']}")
    # ⚠ 够测性：校准样本必须是 35 − 排除数，一个都不能少
    n_expect = len(rows) - len(excl_rows)
    print(f"  校准产物 {n_cmp} 个（应为 {n_expect}，即 35 − 排除 {len(excl_rows)}）")
    if n_cmp != n_expect:
        print(f"[错误] 校准样本数 {n_cmp} != {n_expect} ⇒ 解析器漏行，本轮不发数")
        sys.exit(2)
    for label, bad in (("叶子数", bad_leaf), ("字段名数", bad_field), ("未渲染数", bad_unr)):
        if bad:
            print(f"[错误] {label}不等（{len(bad)} 处）：")
            for b in bad[:5]:
                print("   " + b)
            sys.exit(2)
        print(f"  {label}：{n_cmp}/{n_cmp} 逐个产物**完全相等** ✔")
    if ptotal != n_all:
        print(f"[错误] 母判据自印总数 {ptotal} != 本脚本 {n_all}")
        sys.exit(2)
    print(f"  全站叶子总数：母判据自印 {ptotal} == 本脚本 {n_all} ✔")
    a_ex = {r["name"] for r in excl_rows}
    if a_ex != pex:
        print(f"[错误] 排除集合不一致：仅A={a_ex-pex} 仅B={pex-a_ex}")
        sys.exit(2)
    print(f"  排除集合：母判据 {len(pex)} 个 == 本脚本 {len(a_ex)} 个 ✔")

    # ── 反事实：关掉排除表会翻出什么 ─────────────────────────────────
    print("\n" + "=" * 78)
    print("【问题二 · 反事实】若不排除这 3 个产物，同一套判据会翻出什么")
    print("=" * 78)
    tot_unr = 0
    for r in excl_rows:
        names_total = r["n_fields"]
        tot_unr += r["n_unrendered"]
        print(f"\n  {r['name']}：字段名 {names_total} 个 / 未渲染 {r['n_unrendered']} 个"
              f"（占其字段名 {r['n_unrendered']/names_total*100:.1f}%）")
        print(f"     宿主 {', '.join(r['owner_names'])}")
    print(f"\n[反事实合计] 3 个产物若不排除 ⇒ 额外 {tot_unr} 条未渲染字段名"
          f"（今日为 0，因为它们根本不在判定范围内）")
    n_fields_ex = sum(r["n_fields"] for r in excl_rows)
    n_fields_scope = sum(r["n_fields"] for r in rows if not r["excluded"])
    print(f"[口径·字段名数] 排除项字段名 {n_fields_ex} 个 / 判定范围内 {n_fields_scope} 个"
          f" ⇒ 占全站字段名 {n_fields_ex/(n_fields_ex+n_fields_scope)*100:.1f}%")

    # ── ⚠ 64 条**不等于**「页面上没渲染」：两类假阳性必须分开 ─────────
    print("\n" + "=" * 78)
    print("【问题三 · 这 64 条能不能读成「页面欠账」】—— 先拆假阳性来源")
    print("=" * 78)
    gi = generic_iteration_hosts(hs)
    excl_owner_names = sorted({o for r in excl_rows for o in r["owner_names"]})
    print(f"\n[盲区·通用 key 迭代] 宿主里出现通用 key 迭代写法的文件 {len(gi)} 个：")
    for nm, c in sorted(gi.items(), key=lambda kv: -kv[1]):
        mark = " ← **是这 3 个产物的宿主之一**" if nm in excl_owner_names else ""
        print(f"   {nm:<34} {c} 处{mark}")
    n_blind = sum(1 for o in excl_owner_names if o in gi)
    print(f"\n  ⇒ 这 3 个产物的宿主共 {len(excl_owner_names)} 个，其中 {n_blind} 个含通用 key 迭代。")
    print(f"  ⇒ 含义：宿主若写 `Object.entries(d).map(([k,v]) => …)`，"
          f"它渲染屏幕上出现的**每一个** key，\n     而源码里一个 key 名都没有 "
          f"⇒ 「字段名没出现在源码」对这类宿主**不成立**，判据对它结构性失明。")

    n_zero, n_elsewhere = 0, 0
    per_art = {}
    for r in excl_rows:
        z, e = [], []
        for nm in r["unrendered_names"]:
            other = [p for p in classify_elsewhere(nm)
                     if p not in r["owner_names"]]
            (e if other else z).append((nm, other))
        per_art[r["name"]] = (z, e)
        n_zero += len(z)
        n_elsewhere += len(e)
    print(f"\n[分类·全部 {tot_unr} 条，逐条分类不是抽样]")
    print(f"  A 类·全前端源码 **0 处**（连 node_modules 之外也没有）      {n_zero} 条")
    print(f"  B 类·在**别的**产物宿主里出现过（判据按产物作用域的假阳性）{n_elsewhere} 条")
    print(f"\n  A 类逐条（这三类才可能真的是页面欠账，但仍需人工判读）：")
    for nm, _ in per_art.get("linearity_law.json", ([], []))[0]:
        print(f"     linearity_law.json  {nm}")
    for nm, _ in per_art.get("logit_lens.json", ([], []))[0]:
        print(f"     logit_lens.json     {nm}")
    for nm, _ in per_art.get("path_readout.json", ([], []))[0]:
        print(f"     path_readout.json   {nm}")
    print(f"\n  B 类抽样 10 条（每条注明它出现在哪个别的面板）：")
    shown = 0
    for art, (z, e) in per_art.items():
        for nm, other in e:
            if shown >= 10:
                break
            print(f"     {art:<20} {nm:<26} → {', '.join(other[:2])}")
            shown += 1

    print(f"\n[结论·三层分开，不得混读]")
    print(f"  1  口径事实（确定）：PASS 标题印 {n_all} 个叶子，"
          f"其中 {n_excl} 个（{n_excl/n_all*100:.1f}%）在 continue 之前就被排除，")
    print(f"     从未进入逐字段判定；判据实际施加 {n_scope} 个（{n_scope/n_all*100:.1f}%）。")
    print(f"  2  反事实（确定）：不排除这 3 个 ⇒ 同一判据会翻出 {tot_unr} 条「未渲染」。")
    print(f"  3  ⚠ 但这 {tot_unr} 条**不能**直接读成「页面欠账」："
          f"B 类 {n_elsewhere} 条是判据按产物作用域造成的假阳性，")
    print(f"     且 {n_blind}/{len(excl_owner_names)} 个宿主含通用 key 迭代 ⇒ "
          f"判据对「已渲染但不具名」的结构性失明尚未排除。")
    print(f"     ⇒ 只有 A 类 {n_zero} 条值得逐条判读，且仍不能自动判红。")


if __name__ == "__main__":
    main()
