#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修订 67 · Z1 / Z2 守卫
=====================

**Z1** 诊断串不许把 payload 截掉
--------------------------------
`selfcheck` 一行串里每个 unavailable 项的 reason，必须与
`selfcheck_unavailable[i].reason` **逐字相同**。

⚠ 这是「不许截断」的**机械化表述**。原因：`one_line()` 里原来写的是
`x["reason"][:110]`，紧挨着的注释断言「取到 110，让
`/home/…/w_L19_m0.npy` 这种路径能露出来」——
实测 reason 全文 **117** 字符，110 **正好停在文件名中间**
（印出 `w_L19_m`，丢掉 `0.npy'）`）。**那个断言是假的。**
⇒ 判据不看注释、不看「截断长度是多少」，只看**两个字段是否逐字相同**：
谁再写 `[:N]` 立刻对不上并判红。

**Z2** 带 `**` 的产物字符串必须经 `<Em>` 渲染
-----------------------------------------------
扫每个组件的**裸 JSX 插值**（`{d.a.b}` / `{x}` / `{v.field}`）指向的产物字段；
若该字段在产物里的**值含 `**`** ⇒ 判红。

⚠ 这条**不依赖「值对不对」**，只依赖「含 markdown 标记的字段有没有走 `Em`」
⇒ 结构上就能抓到 D3（`selfcheck` 里的 `⚠**本项无判据**` 被裸插值渲染，
星号在页面上原样显示）。

⚠ 作用域与 Y1 同：**先只扫 B 路这一对产物 × 三个面板**。
⚠ 判据在跑之前已写死在预登记 §67.1。**本文件不得先改判据再跑。**

⚠ Z3（实页 outerHTML 不许出现 `**`）**不在本文件里** ——
   页面是客户端渲染，静态守卫拿不到 ⇒ Z3 由实点执行，结果记进预登记。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SCOPE: list[tuple[str, list[tuple[str, str]]]] = [
    ("frontend/public/latent/data/bpath_marker_steering.json",
     [("frontend/components/BPathPanel.tsx", "d")]),
    ("frontend/public/latent/data/heldout_readability.json",
     [("frontend/components/HeldoutPanel.tsx", "d")]),
    ("frontend/public/latent/data/evidence_ladder.json",
     [("frontend/components/EvidenceLadderPanel.tsx", "d")]),
]

# ⚠⚠ payload 变量名必须**声明**，不许猜。
#   第一版用「查不到就把首段剥掉再查」这个启发式 ⇒
#   `{r.verdict}` / `{sd.verdict}` / `{rc.verdict}` 剥掉首段后撞上**顶层**
#   `verdict`，报出 4 条**假阳性**（`r`/`sd`/`rc` 是局部变量，不是 payload）。
#   ⚠ 判据的「分类依据不能是代理指标」：剥首段是代理，
#   「它是不是 payload 变量」才是真正要问的。
#   ⇒ 三个面板的 payload 变量统一是 `d`（已逐个核对绑定行）。
#   ⚠ 若将来某个面板换了变量名，**这里会漏扫** ⇒ 报告里印出各面板的
#   payload 变量名，让人能一眼看出它对不对。
PAYLOAD_VARS = {c: v for _, hosts in SCOPE for c, v in hosts}

# ⚠ 派生局部变量 → 它在产物里的基路径。**声明式**，逐条对照源码绑定行。
#   HeldoutPanel.tsx:226  `const sd = d.selfdup;`
#   HeldoutPanel.tsx:227  `const rc = d.recipe;`
# ⚠⚠ 不声明它们的后果：那 71 处跳过的裸插值里就包含 `{rc.verdict}` 与
#   `{sd.verdict}`，而它们与 `{d.verdict}` **是同一类**（值里带 `**`）。
#   ⇒ 「跳过」必须收窄到确实无判据的那些，不能把同类一起放过。
# ⚠ `r`（`rows.map(r => …)` 的循环变量）**不在此表** ——
#   它的路径依赖 map 的宿主，`{r.verdict}` 等只能靠 Z3 实页兜底。
#   这一条必须显式自曝，不许假装扫过了。
DERIVED_VARS = {
    "sd": "selfdup",
    "rc": "recipe",
}


def jload(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def dig(obj, dotted: str):
    """按 `a.b[0].c` 取值；取不到返回哨兵（不是 None —— None 是合法值）。"""
    cur = obj
    for part in re.findall(r"[^.\[\]]+", dotted):
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return _MISS
        elif isinstance(cur, dict):
            if part not in cur:
                return _MISS
            cur = cur[part]
        else:
            return _MISS
    return cur


class _Miss:
    def __repr__(self):
        return "<MISSING>"


_MISS = _Miss()


# 裸 JSX 插值：`{expr}`，且 expr 不是以 `<` 开头（那是 JSX 元素）、
# 不是注释、不是模板字面量里的花括号噪声。
# ⚠ 只取**简单的**成员访问链（`d.a.b` / `v.field` / `sd.what`）——
# 复杂表达式（函数调用、`?.`、三元）不做静态推断，那种要靠 Z3 的实页兜底。
JSX_BARE = re.compile(
    r"\{([A-Za-z_$][\w$]*(?:\??\.[A-Za-z_$][\w$]*)+)\}")

# 含 markdown 标记 ⇒ 必须走 Em
MD_MARK = "**"


def z1() -> dict:
    d = jload(ROOT / "frontend/public/latent/data/bpath_marker_steering.json")
    line = d.get("selfcheck", "")
    unav = d.get("selfcheck_unavailable", []) or []

    rows = []
    bad = []
    for i, u in enumerate(unav):
        reason = u.get("reason", "")
        # ⚠ 逐字比较：只要 selfcheck 里那一段不是完整 reason，就判红。
        #   用「reason 是否作为子串出现」而不是「切出来比」——
        #   后者需要复刻拼接逻辑，而拼接逻辑正是可能出错的那一环。
        present = reason in line
        rows.append({"i": i, "name": u.get("name"),
                     "len_reason": len(reason),
                     "present_verbatim": present})
        if not present:
            bad.append(rows[-1])
    return {"selfcheck_len": len(line), "n_unavail": len(unav),
            "rows": rows, "bad": bad,
            "trunc_markers": _scan_slices(_one_line_src())}


def _scan_slices(src: str) -> list[str]:
    """
    只扫**代码**，不看注释 —— ⚠⚠ 第一版直接对整个文件 `re.findall(r"\[:\d+\]")`，
    结果匹配到了我**自己新写的注释**里那句「`[:110]`」⇒ 守卫在扫自己的文档。

    ⇒ 先按行剔除纯注释行（`#` 开头，缩进后），再找切片表达式。
    这条与「注释说的和代码做的不一样」是同一个坑的两面：
    **注释里提到某个模式，不代表代码里有那个模式。**
    """
    out = []
    for ln in src.splitlines():
        code = ln.lstrip()
        if code.startswith("#"):
            continue
        out.extend(re.findall(r"\[:\d+\]", code))
    return out


def _one_line_src() -> str:
    p = ROOT / ".cache/bpath/bpath_selfcheck_recompute.py"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _resolve(data, expr: str, payload_var: str):
    """
    把 JSX 表达式解析成产物里的字段路径。

    ⚠⚠⚠ 第一版直接把 `expr` 整体当路径查 —— `{d.selfcheck}` 被当成
    `d.selfcheck`，而产物里**没有 `d` 这个键**（`d` 是 payload 变量名）
    ⇒ 每次都 MISS ⇒ **Z2 恒真**。
    ⚠ 这个恒真是**阳性对照抓出来的**，不是我看出来的：
    对照把 `<Em s={d.selfcheck} />` 改回 `{d.selfcheck}`，判据毫无反应。

    ⚠⚠ 第二版用「剥掉首段再查」修恒真 ⇒ 又造出 4 条**假阳性**
    （`{r.verdict}` / `{sd.verdict}` / `{rc.verdict}` / `{d.verdict}`
    剥首段后全撞上顶层 `verdict`）。启发式是**代理指标**。

    ⇒ 第三版：只认**声明过的**变量。`d` 直接查；`sd`/`rc` 按 DERIVED_VARS
      加上基路径再查；其余（`r` 等循环变量）**跳过并计数** ——
      跳过的那部分对 Z2 是「本项无判据」，不是「查过了没问题」。
    """
    head, _, rest = expr.partition(".")
    if head == payload_var:
        return dig(data, rest), rest
    base = DERIVED_VARS.get(head)
    if base is not None:
        path = f"{base}.{rest}" if rest else base
        return dig(data, path), path
    return _MISS, expr


def z2() -> dict:
    hits = []
    n_scanned = 0
    n_resolved = 0
    n_skipped = 0
    skip_kinds: dict[str, int] = {}
    n_fields_with_md = 0
    for rel, hosts in SCOPE:
        data = jload(ROOT / rel)
        for h, pvar in hosts:
            src = _strip_nonrendered((ROOT / h).read_text(encoding="utf-8"))
            for m in JSX_BARE.finditer(src):
                expr = m.group(1)
                n_scanned += 1
                head = expr.split(".")[0]
                val, path = _resolve(data, expr, pvar)
                if val is _MISS:
                    n_skipped += 1
                    skip_kinds[head] = skip_kinds.get(head, 0) + 1
                    continue
                if not isinstance(val, str):
                    continue
                n_resolved += 1
                if MD_MARK in val:
                    n_fields_with_md += 1
                    hits.append({"artifact": rel.split("/")[-1],
                                 "component": h.split("/")[-1],
                                 "expr": expr, "path": path,
                                 "snippet": val[:70]})
    return {"n_scanned": n_scanned, "n_resolved": n_resolved,
            "n_skipped": n_skipped, "skip_kinds": skip_kinds,
            "n_fields_with_md": n_fields_with_md, "hits": hits}


def _strip_nonrendered(src: str) -> str:
    """
    剔掉三样**不作为可见文案渲染**的东西，否则判据会把自己的
    文档和数据属性当成缺陷：

    1. `{/* … */}` JSX 注释 —— ⚠⚠ 第一版匹配到了我**自己写的注释**里那句
       `{d.selfcheck}`，于是修好的地方继续被判红（与 Z1 扫到自己注释里的
       `[:110]` 是同一个坑）。
    2. `//` 行注释。
    3. `data-*={…}` 属性值 —— 它们只作**交叉核对**，按本项目规矩
       **不是判据主体**；`{r.verdict}` / `{sd.verdict}` 都在这里。
    """
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    src = re.sub(r"^\s*//.*$", " ", src, flags=re.M)
    src = re.sub(r"\bdata-[A-Za-z0-9-]+\s*=\s*\{[^}]*\}", " ", src)
    # 已经走过 Em 的字段是**正确的**，不能让判据把它判红
    src = re.sub(r"<Em\b[^>]*?/>", " ", src, flags=re.S)
    return src


def positive_controls() -> dict:
    """
    ⚠⚠ 必须**另报 ok_inj**（注入是否真的发生），否则对照的 FAIL
    会被误读成判据的 FAIL —— 对照崩了不是「对照失败」，是「对照没跑」。
    """
    out = {}
    # PC1（Z1）：在 selfcheck 里插一个截断版 reason ⇒ 必须判红
    p = ROOT / "frontend/public/latent/data/bpath_marker_steering.json"
    orig = p.read_bytes()
    try:
        d = json.loads(orig.decode("utf-8"))
        if d.get("selfcheck_unavailable"):
            u = d["selfcheck_unavailable"][0]
            trunc = u["reason"][:20]
            ok_inj = trunc != u["reason"]
            d["selfcheck"] = d["selfcheck"].replace(u["reason"], trunc)
            p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            out["Z1"] = {"ok_inj": ok_inj, "caught": bool(z1()["bad"])}
    finally:
        p.write_bytes(orig)
    # PC2（Z2）：把一个含 ** 的字段改成裸插值语境 ⇒ 必须判红
    h = ROOT / "frontend/components/BPathPanel.tsx"
    hsrc = h.read_text(encoding="utf-8")
    try:
        # 把走 Em 的那处改回裸插值（这正是 D3 的原始写法）
        h.write_text(hsrc.replace("<Em s={d.selfcheck} />", "{d.selfcheck}"),
                     encoding="utf-8")
        # ⚠ ok_inj 必须真的验证：替换后源码里应当**不存在** <Em s={d.selfcheck}
        ok = "<Em s={d.selfcheck} />" not in h.read_text(encoding="utf-8")
        out["Z2"] = {"ok_inj": ok,
                     "caught": any(h["expr"].endswith("selfcheck")
                                   for h in z2()["hits"])}
    finally:
        h.write_text(hsrc, encoding="utf-8")
    return out


def main() -> int:
    print("=" * 78)
    print("修订 67 · Z1 诊断串不许截 payload / Z2 带 ** 的字段必须走 Em")
    print("=" * 78)

    r1 = z1()
    print(f"\n[Z1] selfcheck 串长 {r1['selfcheck_len']} 字符；"
          f"unavailable {r1['n_unavail']} 项")
    for row in r1["rows"]:
        mark = "✓" if row["present_verbatim"] else "✗"
        print(f"   {mark} [{row['i']}] {row['name']}："
              f"reason {row['len_reason']} 字符，"
              f"{'逐字出现' if row['present_verbatim'] else '**未逐字出现**'}")
    print(f"   源码里的切片表达式 {r1['trunc_markers'] or '（无）'}"
          f"　⚠ 出现即判红：Z1 判的是逐字相同，不是「截得合不合适」")

    r2 = z2()
    print(f"\n[Z2] 扫到裸 JSX 插值 {r2['n_scanned']} 处；"
          f"解析到产物字符串 {r2['n_resolved']} 处；"
          f"跳过（非 payload 变量）{r2['n_skipped']} 处；"
          f"含 `**` 的 {r2['n_fields_with_md']} 处")
    print(f"   payload 变量（声明值，非推断）："
          f"{sorted(set(PAYLOAD_VARS.values()))}；"
          f"派生变量：{DERIVED_VARS}")
    print(f"   ⚠ 跳过的 {r2['n_skipped']} 处按变量分：{r2['skip_kinds']}")
    print(f"     ⚠ 其中 `r` 是 rows.map 的**循环变量**，路径依赖宿主，"
          f"本项对它**无判据** —— 只能靠 Z3 实页兜底。")
    print(f"   ⚠ 两个防空通过闸：`n_resolved` 为 0 ⇒ 恒真（第一版就是这样："
          f"把 `d.selfcheck` 当路径查、产物里没有 `d` 键）；"
          f"`n_skipped` 是**本项对这些插值无判据**，不许当「查过了」。")
    for h in r2["hits"]:
        print(f"   ✗ {h['component']} 的 {{{h['expr']}}}（路径 {h['path']}）"
              f" ⇒ {h['snippet']}")

    print()
    pc = positive_controls()
    for k, v in pc.items():
        print(f"[阳性对照 {k}] ok_inj={v['ok_inj']}  caught={v['caught']}")

    fails = []
    if r1["trunc_markers"]:
        fails.append(f"one_line() 里仍有切片 {r1['trunc_markers']}")
    if r1["bad"]:
        fails.append(f"{len(r1['bad'])} 项 reason 未在 selfcheck 里逐字出现")
    if r2["n_resolved"] == 0:
        fails.append("Z2 一个字段都没解析到 ⇒ 本项无判据（不得报 PASS）")
    if r2["hits"]:
        fails.append(f"{len(r2['hits'])} 处含 `**` 的字段被裸插值渲染")
    for k, v in pc.items():
        if not v["ok_inj"]:
            fails.append(f"{k} 阳性对照注入失败 ⇒ 对照没跑，不是判据通过")
        elif not v["caught"]:
            fails.append(f"{k} 阳性对照注入成功但判据没抓到 ⇒ 判据恒真")

    print()
    if fails:
        print("FAIL 修订 67：")
        for f in fails:
            print(f"  ✗ {f}")
        return 1

    print(f"PASS Z1/Z2：{r1['n_unavail']} 项 reason 逐字一致、无切片；"
          f"{r2['n_scanned']} 处裸插值里 0 处含 `**`；两条阳性对照均被抓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
