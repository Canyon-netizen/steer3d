#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修订 69 · Y2 整站渲染覆盖
=========================

Y1 的作用域一直限死在「B 路这一对产物 × 三个面板」。本判据扩到整站。

**产物有两类宿主，不是一类**（§69.0）：

- `frontend/components/*.tsx`（Next 组件）
- `frontend/public/latent/index.html`（**318 KB 单文件独立站**）

只扫 tsx ⇒ 将近一半产物永远无判据，而「无判据」在报告里
和「都覆盖到了」长得一模一样。

判红：叶子字段的**字段名**在其归属宿主源码里一次都没出现。
⚠ 字段名只要在**至少一个**归属宿主里出现就不算未渲染
（§69.1 第 3 条的更正，提交 `aa3b5d2`）——
本判据问的是「读者能不能看到」，任一宿主渲染了读者就看得到。

⚠⚠ **排除表用机械定义**（§69.1.1），不是「看着像表就排除」：
  E1 叶子总数 ≥ 2000 **且** E2 字符串叶子占比 < 1%。
  每条排除都必须列出实测的两个数。**排除 ≠ 通过**：
  排除表里的产物单独成行、标注「本项对它无判据」，
  不许混进「未渲染 0 个」那个总数里。

⚠ 判据在跑之前已写死在预登记 §69.1。**本文件不得先改判据再跑。**
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FE = ROOT / "frontend"

# ── §69.1.1 排除表的机械定义 ────────────────────────────────────────────
EXCL_MIN_LEAVES = 2000
EXCL_MAX_STR_RATIO = 0.01

MAX_DEPTH = 14
MIN_DEPTH_EXPECTED = 3


def name_pattern(name: str) -> re.Pattern:
    esc = re.escape(name)
    return re.compile(rf"(?<![A-Za-z0-9_]){esc}(?![A-Za-z0-9_])")


def leaves(obj, path: str = "", depth: int = 0, acc=None):
    if acc is None:
        acc = []
    if depth > MAX_DEPTH:
        raise RuntimeError(f"下钻超过 MAX_DEPTH={MAX_DEPTH}（{path[:60]}）")
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from leaves(v, f"{path}.{k}" if path else str(k),
                              depth + 1, acc)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from leaves(v, f"{path}[{i}]", depth + 1, acc)
    elif obj is not None and not (isinstance(obj, str) and obj == ""):
        # ⚠⚠ 第一版**只 yield 没 append** ⇒ `acc` 永远是空的
        #   ⇒ 35 个产物全报「叶子 0」，而 `n_leaves_total` 也是 0。
        #   ⚠ 这个恒真被**阳性对照**当场崩出来（它去读
        #   `a["field"]`，而 `a` 是产物字典、没有这个键）。
        #   ⚠ 若没有阳性对照，空通过防护也会拦下（n_leaves_total==0），
        #   但**报错的位置**离病根很远 —— 对照崩在守卫内部才更好定位。
        acc.append((path, obj))
        yield path, obj


def field_name(path: str) -> str:
    name = path.rsplit(".", 1)[-1] if "." in path else path
    if "[" in name:
        head = name.partition("[")[0]
        name = head if head else name
    return name


# ── §69.5 挂账台账 ─────────────────────────────────────────────────────
# ⚠⚠ 这张台账里的条目**是欠账，不是通过**。它每次运行都被打印出来，
#    且**不计入**「未渲染 0 个」那个数字。
# ⚠ 台账**不许自动增长**：新出现的未渲染字段一律判红，
#    要么改代码渲染它，要么显式加进来并写理由。
#    默默让台账变大 = 把判据调松。
DEBT_PATH = Path(__file__).with_suffix("").with_name(
    "check_render_coverage_sitewide.debt.json")

# data-key：AIME 题号（1983_I_1）与纯数字层号 —— 这些是**数据键**，
#   宿主是遍历它们而不是按名字引用它们，按「字段名」判没有意义。
DATA_KEY = re.compile(r"^(\d{4}_[A-Z]_\d+|\d+)$")

# meta：列明的产物元数据名（§69.4）
META_NAMES = {"schema", "design", "generated_by", "built_from",
              "model_provenance", "how", "convention", "sources",
              "note_batch"}


def categorize(field: str) -> str:
    if DATA_KEY.match(field):
        return "data-key"
    if field in META_NAMES:
        return "meta"
    return "unclassified"


def load_debt() -> dict:
    if not DEBT_PATH.exists():
        return {"entries": {}, "note": "台账文件不存在 —— 首跑，全部判红"}
    d = json.loads(DEBT_PATH.read_text(encoding="utf-8"))
    return {"entries": {e["artifact"] + "|" + e["field"]: e
                        for e in d.get("debt", [])},
            "note": d.get("note", ""), "raw": d}


def hosts() -> dict[Path, str]:
    out: dict[Path, str] = {}
    for p in sorted(FE.glob("components/*.tsx")):
        out[p] = p.read_text(encoding="utf-8")
    idx = FE / "public/latent/index.html"
    if idx.exists():
        out[idx] = idx.read_text(encoding="utf-8")
    return out


def artifacts() -> list[Path]:
    return sorted((FE / "public/latent/data").glob("*.json")) + \
        [FE / "public/latent/models.json"]


def scan() -> dict:
    hs = hosts()
    rep = {"artifacts": [], "n_leaves_total": 0, "max_depth_seen": 0,
           "n_artifacts_checked": 0, "n_artifacts_with_host": 0,
           "excluded": [], "errors": []}

    for f in artifacts():
        if not f.exists():
            rep["errors"].append(f"产物不存在：{f}")
            continue
        rel = str(f.relative_to(FE))
        owners = [h for h, src in hs.items() if f.name in src]

        data = json.loads(f.read_text(encoding="utf-8"))
        acc = []
        list(leaves(data, acc=acc))
        n = len(acc)
        n_str = sum(1 for _, v in acc if isinstance(v, str))
        ratio = n_str / n if n else 0.0
        depth = max((p.count(".") + p.count("[") for p, _ in acc), default=0)

        rep["n_artifacts_checked"] += 1
        rep["n_leaves_total"] += n
        rep["max_depth_seen"] = max(rep["max_depth_seen"], depth)
        if owners:
            rep["n_artifacts_with_host"] += 1

        # ── 排除表：机械判定，且必须列出实测两个数 ────────────────────
        if n >= EXCL_MIN_LEAVES and ratio < EXCL_MAX_STR_RATIO:
            rep["excluded"].append(
                {"artifact": f.name, "n_leaves": n, "str_ratio": ratio,
                 "owners": [o.name for o in owners],
                 "why": f"E1 叶子 {n} ≥ {EXCL_MIN_LEAVES} 且 "
                        f"E2 字符串占比 {ratio*100:.2f}% < "
                        f"{EXCL_MAX_STR_RATIO*100:.0f}%"})
            continue

        names: dict[str, str] = {}
        for p, _v in acc:
            nm = field_name(p)
            if nm and nm not in names:
                names[nm] = p

        unrendered = []
        for nm, first in sorted(names.items()):
            if any(name_pattern(nm).search(hs[o]) for o in owners):
                continue
            unrendered.append({"field": nm, "first": first})

        rep["artifacts"].append({
            "artifact": rel, "owners": [o.name for o in owners],
            "n_leaves": n, "str_ratio": ratio, "depth": depth,
            "n_fields": len(names), "unrendered": unrendered})

    return rep


def positive_control() -> dict:
    """
    注入一个**任何宿主源码里不可能出现**的字段名，确认判据仍判红。

    ⚠⚠ 必须另报 ok_inj（注入是否真的发生）：对照崩了是「对照没跑」，
    不是「判据通过」。
    """
    fake = "zzz_rev69_never_in_any_host"
    target = FE / "public/latent/data/arm_asymmetry.json"
    orig = target.read_bytes()
    ok_inj = False
    try:
        d = json.loads(orig.decode("utf-8"))
        d[fake] = 1
        target.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        ok_inj = True
        rep = scan()
        caught = any(u["field"] == fake
                     for a in rep["artifacts"] for u in a["unrendered"])
        # ⚠⚠ 只证「扫到了」不够 —— 还要证它**会被判红**。
        #   挂账模式下「判红」的条件是「不在台账里」，
        #   所以必须另查它确实不在台账；否则对照可能证明的是
        #   一条**恒绿**的判定路径（扫到了，但被判成「已挂账」就放过）。
        not_in_ledger = not any(
            u["field"] == fake
            for a in rep["artifacts"] for u in a["unrendered"]
            if a["artifact"] + "|" + u["field"] in load_debt()["entries"])
    finally:
        target.write_bytes(orig)
    return {"ok_inj": ok_inj, "caught": bool(caught),
            "would_red": bool(caught and not_in_ledger), "field": fake}


def main() -> int:
    rep = scan()

    print("=" * 78)
    print("修订 69 · Y2 整站渲染覆盖（产物里的叶子字段有没有真的被页面读到）")
    print("=" * 78)

    print(f"\n[计数] 扫到产物 {rep['n_artifacts_checked']} 个（要求 > 0）")
    print(f"[计数] 其中**有宿主**的 {rep['n_artifacts_with_host']} 个"
          f"（要求 > 0，否则「产物清单没配上宿主」）")
    print(f"[计数] 扫到叶子字段 {rep['n_leaves_total']} 个（要求 > 0）")
    print(f"[深度] 全局下钻 {rep['max_depth_seen']} 层"
          f"（下限 {MIN_DEPTH_EXPECTED}，上限 {MAX_DEPTH}）")
    for e in rep["errors"]:
        print(f"[错误] {e}")

    # ── 排除表：单独成行，标注「无判据」，不混进总数 ────────────────────
    print(f"\n[排除表] {len(rep['excluded'])} 个产物按机械定义排除"
          f"（E1 叶子≥{EXCL_MIN_LEAVES} 且 E2 字符串占比<"
          f"{EXCL_MAX_STR_RATIO*100:.0f}%）")
    for e in rep["excluded"]:
        print(f"   ⚠ 本项对 {e['artifact']} **无判据**")
        print(f"      {e['why']}；宿主 {', '.join(e['owners'])}")

    print()
    tot_un = 0
    for a in rep["artifacts"]:
        n_un = len(a["unrendered"])
        tot_un += n_un
        mark = "  " if n_un == 0 else "⚠ "
        print(f"{mark}{a['artifact']:<52} 叶子 {a['n_leaves']:>7}"
              f" 字段名 {a['n_fields']:>4} 深度 {a['depth']}"
              f" 未渲染 {n_un}")
        if a["unrendered"]:
            print(f"      宿主 {', '.join(a['owners']) or '⚠ 无'}")
            for u in a["unrendered"][:12]:
                print(f"        ✗ {u['field']}   首见 {u['first']}")
            if len(a["unrendered"]) > 12:
                print(f"        … 另有 {len(a['unrendered'])-12} 个")

    print(f"\n[合计] 已检查产物中未渲染字段 {tot_un} 个"
          f"（排除表的 {len(rep['excluded'])} 个产物**不计入**）")

    # ── §69.5 台账比对：判红只对**新增** ─────────────────────────────
    debt = load_debt()
    new_hits, old_hits = [], []
    cats: dict[str, int] = {}
    for a in rep["artifacts"]:
        for u in a["unrendered"]:
            key = a["artifact"] + "|" + u["field"]
            e = debt["entries"].get(key)
            if e is None:
                new_hits.append({"artifact": a["artifact"], **u})
            else:
                old_hits.append(e)
                cats[e.get("category", "?")] = \
                    cats.get(e.get("category", "?"), 0) + 1

    print(f"\n[台账] 已在册欠账 {len(old_hits)} 条"
          f"　⚠ **这是欠账，不是通过**；不计入下面的「未渲染 0 个」")
    for k, v in sorted(cats.items(), key=lambda kv: -kv[1]):
        extra = ("（含未判读，**未逐条复核**）" if k == "unclassified" else "")
        print(f"        {k:<18} {v}{extra}")
    print(f"[台账] 台账文件条目 {len(debt['entries'])} 条；"
          f"本次实到 {len(old_hits)} 条"
          f"{'　⚠ 有条目已不在实跑结果里（可能被修复，也可能台账过时）' if len(debt['entries']) != len(old_hits) else ''}")
    if new_hits:
        print(f"\n[新增] **不在台账里**的未渲染字段 {len(new_hits)} 条"
              f"　⚠ 台账不许自动增长，这些是回归：")
        for h in new_hits[:20]:
            print(f"      ✗ {h['artifact'].split('/')[-1]}:{h['field']}"
                  f"   首见 {h['first']}")
        if len(new_hits) > 20:
            print(f"      … 另有 {len(new_hits)-20} 条")

    print()
    pc = positive_control()
    print(f"[阳性对照] ok_inj={pc['ok_inj']}  caught={pc['caught']}  "
          f"would_red={pc['would_red']}  field={pc['field']}")
    print(f"           ⚠ caught 只证明「扫到了」；would_red 才证明「会被判红」"
          f"（挂账模式下判红 = 不在台账里）")

    fails: list[str] = []
    if rep["n_artifacts_checked"] == 0:
        fails.append("没检查任何产物 ⇒ 本项无判据")
    if rep["n_artifacts_with_host"] == 0:
        fails.append("没有产物配上宿主 ⇒ 本项无判据（不得报 PASS）")
    if rep["n_leaves_total"] == 0:
        fails.append("没抽出任何叶子字段 ⇒ 本项无判据")
    if rep["max_depth_seen"] < MIN_DEPTH_EXPECTED:
        fails.append(f"全局下钻只有 {rep['max_depth_seen']} 层 < "
                     f"{MIN_DEPTH_EXPECTED} ⇒ 可能整片容器没进检查")
    if rep["errors"]:
        fails.extend(rep["errors"])
    if not pc["ok_inj"]:
        fails.append("阳性对照注入失败 ⇒ 对照没跑，不是判据通过")
    if pc["ok_inj"] and not pc["caught"]:
        fails.append("阳性对照注入成功但判据没抓到 ⇒ 判据恒真")
    if pc["ok_inj"] and pc["caught"] and not pc["would_red"]:
        fails.append("阳性对照被扫到了却不会被判红 ⇒ 判定路径恒绿")
    if new_hits:
        fails.append(f"{len(new_hits)} 个新出现的未渲染字段不在台账里"
                     f"（台账不许自动增长）")
    if tot_un and not new_hits:
        print(f"⚠ 注意：当前 {tot_un} 条未渲染**全部在台账内** ⇒ "
              f"没有新回归，但**欠账一条都没还**。")

    print()
    if fails:
        print("FAIL 修订 69 Y2：")
        for f in fails:
            print(f"  ✗ {f}")
        return 1

    print(f"PASS Y2（无新回归）：{rep['n_artifacts_checked']} 个产物 / "
          f"{rep['n_leaves_total']} 个叶子 / 新增未渲染 0 个；"
          f"\n     ⚠⚠ 在册欠账 {len(old_hits)} 条未清、"
          f"{len(rep['excluded'])} 个产物**本项无判据** —— "
          f"**这不是「整站都渲染了」**")
    return 0


if __name__ == "__main__":
    sys.exit(main())
