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
    """按 `a.b[0].c` 取值；取不到返回哨兵（不是 None —— None 是合法值）。

    ⚠⚠⚠ list **不认识字段名** ⇒ `layer_profile.rows.claim` 解不出来，
    而组件里写的是 `{r.claim}`（`r` 是 `rows.map` 的循环变量）。
    第一版这里只认整数下标，于是 133 处裸插值里只有 19 处解析得出，
    `.map` 宿主解析明明已经找到了宿主，却卡在最后一步。

    ⇒ 现在 list 也按**字段名**取：把该 list 的**所有元素**取这个字段，
    返回它们的集合（供 Z4 判断「是不是全都含 `**`」）。
    """
    cur = obj
    for part in re.findall(r"[^.\[\]]+", dotted):
        if isinstance(cur, list):
            if part.isdigit():
                try:
                    cur = cur[int(part)]
                    continue
                except IndexError:
                    return _MISS
            # 字段名 ⇒ 取所有元素的这个字段（都取不到才算 MISS）
            vals = []
            for el in cur:
                if isinstance(el, dict) and part in el:
                    vals.append(el[part])
            if not vals:
                return _MISS
            cur = vals
            continue
        if isinstance(cur, dict):
            if part not in cur:
                return _MISS
            cur = cur[part]
            continue
        return _MISS
    return cur


class _Miss:
    def __repr__(self):
        return "<MISSING>"


_MISS = _Miss()

# 下钻上限：命中就 raise，不静默截断（修订 66 §66.3.1 的教训）。
MAX_DEPTH = 12


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


# `HOST.map((VAR) => …` / `HOST.map(VAR => …`
# ⚠ 第一版 `\.map\(\s*\(?\s*…` 只允许**一个**左括号，
#   而源码写的是 `.map((r) => {` —— **两个** ⇒ 匹配 0 处，
#   宿主解析静默失效（`n_by_path` 停在 19，与 Z2 一样）。
#   ⚠ 这是「匹配不到」而不是「匹配错」，症状是「数字没变」——
#   而「数字没变」很容易被读成「本来就没有更多可解析的」。
#   ⇒ 所以下面这条每次运行都要把 `n_by_path` 印出来，让它能被看见。
MAP_BIND = re.compile(
    r"([A-Za-z_$][\w$]*(?:\??\.[A-Za-z_$][\w$]*)*)"
    r"\.map\(\s*\(?\s*([A-Za-z_$][\w$]*)?\s*\)?\s*=>")


def _host_for(src: str, pos: int, var: str):
    """
    往前找最近一次把 `var` 绑成循环变量的 `.map(`，取它的宿主。

    ⚠⚠ 这是让 Z4 从「按名字猜」升级到「按路径算」的关键：
    Z2 放弃的 69 处里绝大多数是 `.map(r => …)` 的循环变量，
    而**宿主**就写在同一行上方（`d.ladder_mapping.map((r) => {`）。
    ⇒ 找到宿主就能把 `r.claim` 解析成 `ladder_mapping.claim`，**不需要猜**。
    """
    best = None
    for m in MAP_BIND.finditer(src):
        if m.start() > pos:
            break
        if m.group(2) == var:
            best = m.group(1)
    return best


def _resolve_host(data, host: str, payload_var: str):
    """把宿主表达式（`d.ladder_mapping`）解析成产物路径。"""
    head, _, rest = host.partition(".")
    if head == payload_var:
        return rest if rest else None
    base = DERIVED_VARS.get(head)
    if base is not None:
        return f"{base}.{rest}" if rest else base
    return None


def z4() -> dict:
    """
    Z4（修订 68）：按**字段名**判，不按路径。

    ⚠⚠ Z2 放弃的那 69 处几乎全是 `.map(r => …)` 的循环变量，
    路径依赖宿主、静态解析不了。而 `{r.verdict}` 与已覆盖的
    `{d.verdict}` **是同一类** —— 都在渲染一个含 `**` 的产物字符串。
    一起跳过等于用「解析不了」当「没关系」。

    ⇒ 观察：Z2 真正要问的是「**含 `**` 的那个字段**有没有走 `<Em>`」。
    它**不需要**知道这个字段在产物 JSON 里的完整路径 ——
    「产物里哪些字段的值含 `**`」+「组件怎么渲染 `{x.字段名}`」
    两个信息就够。**路径解析是多余的一步，也正是它挡掉那 69 处的原因。**

    ⚠ 同名歧义必须每次报出来：若某字段名的值**有**含 `**` 也**有**不含的，
    按名字判会误判 ⇒ 该名字标为歧义，不许悄悄算作「已覆盖」。
    """
    md_names: set[str] = set()
    ambig: set[str] = set()
    for rel, _ in SCOPE:
        data = jload(ROOT / rel)
        by_name: dict[str, list[bool]] = {}
        for _p, name, val in _walk(data):
            if not isinstance(val, str):
                continue
            has = MD_MARK in val
            by_name.setdefault(name, []).append(has)
        for nm, flags in by_name.items():
            if any(flags):
                md_names.add(nm)
                if not all(flags):
                    ambig.add(nm)

    hits = []
    n_scanned = 0
    n_by_path = 0
    n_by_name = 0
    n_unresolved = 0
    for rel, hosts in SCOPE:
        data = jload(ROOT / rel)
        for h, pvar in hosts:
            raw = (ROOT / h).read_text(encoding="utf-8")
            # ⚠ 先标出「在 <Em> 内的插值」，再扫其余的。
            #   不能像 Z2 那样先把 <Em/> 整段删掉 —— 那样就分不出
            #   「走 Em 的」与「裸的」了。
            em_spans = [(m.start(), m.end()) for m in
                        re.finditer(r"<Em\b[^>]*?/>", raw, flags=re.S)]
            src = _strip_nonrendered(raw)
            for m in JSX_BARE.finditer(src):
                expr = m.group(1)
                n_scanned += 1
                in_em = any(a <= m.start() < b for a, b in em_spans)
                if in_em:
                    continue
                val, path, how = _resolve_full(data, expr, pvar, src, m.start())
                if val is not _MISS and isinstance(val, (str, list)):
                    n_by_path += 1
                    texts = [val] if isinstance(val, str) else \
                        [x for x in val if isinstance(x, str)]
                    if any(MD_MARK in t for t in texts):
                        hits.append({"component": h.split("/")[-1],
                                     "expr": expr, "path": path,
                                     "field": path.split(".")[-1],
                                     "how": how, "ambiguous": False})
                    continue
                # ⚠ 路径解不出来 ⇒ 退回按**字段名**判。
                #   只有名字**不在歧义集**里才能下结论；歧义名字必须
                #   单独列出来等人判，不许悄悄算作「已覆盖」。
                n_unresolved += 1
                last = expr.split(".")[-1]
                if last in ambig:
                    hits.append({"component": h.split("/")[-1],
                                 "expr": expr, "path": "<解析不出>",
                                 "field": last, "how": "name(歧义)",
                                 "ambiguous": True, "needs_human": True})
                elif last in md_names:
                    n_by_name += 1
                    hits.append({"component": h.split("/")[-1],
                                 "expr": expr, "path": "<解析不出>",
                                 "field": last, "how": "name",
                                 "ambiguous": False})
    return {"md_field_names": sorted(md_names), "ambiguous": sorted(ambig),
            "n_scanned": n_scanned, "n_by_path": n_by_path,
            "n_by_name": n_by_name, "n_unresolved": n_unresolved,
            "hits": hits}


def _resolve_full(data, expr: str, payload_var: str, src: str, pos: int):
    """三级解析：payload 变量 → 声明的派生变量 → `.map` 宿主。返回 (值, 路径, 方式)。"""
    val, path = _resolve(data, expr, payload_var)
    if val is not _MISS:
        return val, path, "payload/derived"
    host = _host_for(src, pos, expr.split(".")[0])
    if host:
        base = _resolve_host(data, host, payload_var)
        if base:
            rest = expr.partition(".")[2]
            full = f"{base}.{rest}" if rest else base
            return dig(data, full), full, "map-host"
    return _MISS, expr, "未解析"


def _walk(obj, path: str = "", depth: int = 0):
    """产出全部叶子 (路径, 字段名, 值) —— 含 list 内元素（Z4 要按名字覆盖它们）。"""
    if depth > MAX_DEPTH:
        raise RuntimeError(f"下钻超过 MAX_DEPTH={MAX_DEPTH}")
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk(v, f"{path}.{k}" if path else str(k), depth + 1)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{path}[{i}]", depth + 1)
    else:
        name = path.rsplit(".", 1)[-1] if "." in path else path
        if "[" in name:
            # ⚠ 第一版写的是 `rest.split("]",1)[-1]` —— 对 `note_batch[0]`
            #   算出的是**空串**，于是产物里凭空多出一个名为 "" 的字段。
            #   字段名是**中括号之前**那一段（`note_batch`）。
            head = name.partition("[")[0]
            name = head if head else name
        yield path, name, obj


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
    # PC3（Z4）：把一个走 Em 的、字段名含 ** 的插值改回裸的 ⇒ 必须判红。
    #   ⚠ 必须覆盖**循环变量**那种（Z2 放弃的正是它们），
    #   否则对照只证明「Z4 对 Z2 已经覆盖的那部分有效」。
    h = ROOT / "frontend/components/HeldoutPanel.tsx"
    src2 = h.read_text(encoding="utf-8")
    old = "<Em s={d.not_claimed} />"
    ok3 = old in src2
    try:
        if ok3:
            h.write_text(src2.replace(old, "{d.not_claimed}"),
                         encoding="utf-8")
            out["Z4"] = {"ok_inj": ok3,
                         "caught": any(x["field"] == "not_claimed"
                                       for x in z4()["hits"])}
    finally:
        h.write_text(src2, encoding="utf-8")
    # PC4（Z4 的 map 宿主路径）：
    #   ⚠ PC3 只改了 `{d.not_claimed}`，那是 **payload 变量**路径 ——
    #   它证明不了「`r.claim` 这种 `.map` 循环变量也能解析」。
    #   ⇒ 直接往产物的 `ladder_mapping[0].claim` 里注入一个 `**`，
    #     若宿主解析 + list 感知的 dig 真的工作，Z4 必须判红。
    ap = ROOT / "frontend/public/latent/data/bpath_marker_steering.json"
    aorig = ap.read_bytes()
    try:
        d3 = json.loads(aorig.decode("utf-8"))
        rows3 = d3.get("ladder_mapping") or []
        ok4 = bool(rows3)
        if ok4:
            rows3[0]["claim"] = rows3[0]["claim"] + " **注入**"
            ap.write_text(json.dumps(d3, ensure_ascii=False), encoding="utf-8")
            h4 = z4()["hits"]
            out["Z4-map"] = {
                "ok_inj": True,
                "caught": any(x["field"] == "claim" and x["how"] == "map-host"
                              for x in h4)}
    finally:
        ap.write_bytes(aorig)
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

    r4 = z4()
    print(f"\n[Z4] 产物里含 `**` 的字段名 {len(r4['md_field_names'])} 个："
          f"{r4['md_field_names']}")
    if r4["ambiguous"]:
        print(f"   ⚠⚠ 同名歧义（同名下有的含 `**` 有的不含，按名字判会误判）"
              f"：{r4['ambiguous']}")
    print(f"   扫到裸 JSX 插值 {r4['n_scanned']} 处；"
          f"按路径判 {r4['n_by_path']} 处 / 按名字判 {r4['n_by_name']} 处；"
          f"仍解析不出 {r4['n_unresolved']} 处；**裸渲染含 `**` {len(r4['hits'])} 处**")
    for h in r4["hits"]:
        if h.get("needs_human"):
            print(f"   ? {h['component']} 的 {{{h['expr']}}} ⇒ 字段名 "
                  f"`{h['field']}` 在不同产物里有的含 `**` 有的不含 —— "
                  f"**按名字判不了，需人工判定**")
        else:
            print(f"   ✗ {h['component']} 的 {{{h['expr']}}} ⇒ 路径 "
                  f"`{h['path']}`（{h['how']}）的值含 `**` 却是裸插值")

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
    if r4["n_by_path"] + r4["n_by_name"] == 0:
        fails.append("Z4 一个含 `**` 的字段都没判到 ⇒ 本项无判据")
    needs_human = [h for h in r4["hits"] if h.get("needs_human")]
    if needs_human:
        fails.append(f"{len(needs_human)} 处字段名歧义、按名字判不了，"
                     f"需人工判定（不得默认算作已覆盖）")
    if r4["hits"]:
        fails.append(f"{len(r4['hits'])} 处含 `**` 的字段被裸插值渲染（Z4）")
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

    print(f"\n⚠ 剩下 {r4['n_unresolved']} 处路径解析不出。**这不是静默放过** —— "
          f"它们的字段名若落在产物里那 {len(r4['md_field_names'])} 个含 `**` 的"
          f"字段名里，Z4 会按名字判红；既然 0 处命中，"
          f"说明这些名字**在任何一份产物里都没有含 `**` 的值** ⇒ "
          f"裸渲染它们不可能漏出星号。")
    print(f"PASS Z1/Z2/Z4：{r1['n_unavail']} 项 reason 逐字一致、无切片；"
          f"Z4 按路径判 {r4['n_by_path']} 处、0 处裸渲染含 `**`；"
          f"{len(pc)} 条阳性对照全被抓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
