#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修订 66 · Y1：渲染覆盖守卫
================================

**要问的问题**：产物 JSON 里的每个叶子字段，页面真的读它吗？

为什么需要它：修订 64 落地（`658595b`）把「两条路径及其 sem」写进了
`heldout_readability.json`，commit message 承诺「两条路径都报」——
但那笔提交没碰过 `HeldoutPanel.tsx`，实页 outerHTML 里也没有任何 path sem。
`path_to_threshold` 的每个数都完美可溯源、通过了全部七条判据，
**然后没有人看得到它**。X1–X5 全在查「数字是不是可溯源」，没有一条问
「这个字段到底有没有被渲染」。

⚠ 判据在跑之前就已写死在预登记 §66.1。**本文件不得先改判据再跑。**

判红条件（§66.1 Y1）
------------------
1. 某个叶子字段的**字段名**在其宿主组件源码里一次都没出现；
2. `n_components_checked == 0`（没检查到任何组件）
   或 `n_leaves_total == 0`（没抽出任何叶子字段）。

⚠ 空通过防护：条件 2 是为了让「0 个未渲染」与「什么都没检查」
在输出里长得不一样。**报「0 个违规 · PASS」而 `n_leaves_total == 0`
是本守卫明令禁止的输出。**

⚠ 作用域收窄（§66.1）：只扫 B 路这一对产物 × 三个面板。
先让这一条有牙齿，再谈扩面。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# ── 作用域（§66.1：收窄）────────────────────────────────────────────────
SCOPE: list[tuple[str, list[str]]] = [
    ("frontend/public/latent/data/heldout_readability.json",
     ["frontend/components/HeldoutPanel.tsx"]),
    ("frontend/public/latent/data/bpath_marker_steering.json",
     ["frontend/components/BPathPanel.tsx"]),
    ("frontend/public/latent/data/evidence_ladder.json",
     ["frontend/components/EvidenceLadderPanel.tsx"]),
]

# ── 豁免表（§66.1：列明，每次报出大小与条目）─────────────────────────────
# ⚠⚠⚠ 这张表是**人列的** ⇒ 属「本项对这些字段无判据」的一角，
# 守卫每次运行都会把**大小与条目原样打出来**。
# 判据写死时本表是**空的**；下面每一条都是看到实跑输出后逐条判定的。
#
# ⚠⚠⚠ **这张表最大的自曝**：Y1 按**字段名**判「有没有被页面读到」，但页面
# 可以合法地把一个字段的**值**经由**派生散文串**渲染出来 ——
# 按名字判就会把「值在页面上」误报成「没渲染」。
# 本仓真实存在这一类（见 `VALUES_VIA_PROSE`），本判据**看不见**。
# ⇒ 值级核对由 §66.1 的 Y2（浏览器实点）承担，不靠这张表。
EXEMPT: dict[str, str] = {
    # ── A 类：值经由构建器生成的派生散文串渲染（Y1 按名字看不见）──────
    "pred_marker_lse": "A类·值已渲染：由构建器生成 layer_profile.calibration 散文"
                       "（实测页显示 预测 +41.8022 / 实测 +41.2500 / ratio 0.9868）",
    "calibration_ratio": "A类·值已渲染：同上（ratio 0.9868 / 0.9808）",
    "-1": "A类·层号键：by_layer 的 '-1' 校准点档，页面经 by_layer 容器画火花图",

    # ── B 类：schema / 元数据，页面按约定不展示 ──────────────────────
    "schema": "B类·产物 schema 名，按约定不上页面",

    # ── C 类：中间量或低价值统计，页面当前不展示 ──────────────────────
    "alpha": "C类·layer_profile.rows 的中间量，页面只用 by_layer 画火花图",
    "rel_perturbation": "C类·同上",
    "w_dot_hhat": "C类·同上",
    "n_missing": "C类·标签覆盖统计，页面不展示",
    "floor_from": "C类·地板来源文件名，页面只印地板值",
    "non_circular": "C类·产物来源文件名，页面不展示",
    "to": "C类·margin_gain_attribution 的目标档名，页面用 VLABEL 印人话",
    "n_used_lag1": "C类·selfdup 逐轨迹 lag1 有效数，页面只印均值与轨迹数",
    "d_rand": "C类·校准批次单点对照值，页面只印地板",
    "above_p01": "C类·sampling_defect27 M2 的计数，页面只印判定",
    "rank_under_true_value": "C类·同上",
    "verdict_invariant": "C类·同上",
    "rule": "C类·M1/M2 的判据文本，判据全文在预登记不在页面",
    "reportable_why": "C类·逐 token 不单独判决的理由，页面不逐 token 展开",
    "role": "C类·position_strat 的自我定位说明",
    "dom_id": "C类·position_strat 的 dominator token id",
    "label": "C类·分层标签，页面不逐层展开",
    "dom_n": "C类·分层计数",
    "dom_pos": "C类·分层计数",
    "rest_n": "C类·分层计数",
    "rest_pos": "C类·分层计数",
    "n_strata_skipped": "C类·分层跳过数（值恒为 0）",
    "other_def": "C类·切点敏感性说明",

    # ⚠⚠⚠ 这里**故意留空**：`path_to_threshold` 的 10 个叶子，
    # 以及 `max_level_with_data` / `why_two_numbers` / `max_level_claimed`
    # / `selfdup.what`，**一律不进豁免表**。
    #
    # 我第一版把它们标成「D类·待渲染」放进了表里 —— 那守卫会在缺陷
    # **还在**的时候报 PASS。这正是本项目反复吃过的「假绿」：
    # 一张列了「待办」的豁免表 = 把待办伪装成已完成。
    # ⇒ 待落地的字段必须**留在判红侧**，渲染出来之后它们自己会变绿。
    # （本表 D 类条目已于此删除，改由预登记 §66.4 记录待渲染清单。）
}

# 叶子节点里不参与「是否被页面读到」判定的形态：
#   - 空字符串：页面上不渲染它，判它等于判噪声
#   - dict/list：容器，会被展开成叶子，容器本身不判
_SKIP_TYPES = (dict, list)

# 下钻上限：命中就 raise，而不是静默截断。
# ⚠ 静默截断 = 某一片整块没进检查，而计数照样非零（正是本文件踩过的坑）。
MAX_DEPTH = 12

# Y1a：下钻到这个深度才算扫到了预期的那几层嵌套。
# ⚠ 这个数是**全局下限**，不是逐产物的目标深度 —— 逐产物判会把
# `evidence_ladder.json` 这种本来就只有两层的平表误判成「整片没扫」。
MIN_DEPTH_EXPECTED = 3


def leaves(obj, path: str = "", depth: int = 0):
    """
    递归产出所有叶子字段的 (点分路径, 字段名, 值)。

    ⚠⚠⚠ 第一版在这里放过 list（`return` 直接返回）。后果是
    `recipe.variants[i]` 里的**全部字段一个都没扫** ——
    包含本守卫唯一要抓的 `path_to_threshold`。
    而 `n_leaves_total` 仍然是 435（非零）⇒ 空通过防护也没拦住。

    ⇒ **判据写的是「所有非容器节点」，第一版的实现没做到。**
    这是实现没实现判据，不是判据错了，所以改实现、不改判据。
    教训与「`n_seen == 0` 要判红」同源，只是这次反过来：
    **`n_leaves_total` 非零也可能只数到了**某一部分**容器。**
    ⇒ 追加 Y1a（见下）：报告必须报**下钻到的最大深度**，
    深度恒等于 1 ⇒ 某个分支整片没进检查。
    """
    if depth > MAX_DEPTH:
        raise RuntimeError(
            f"下钻超过 MAX_DEPTH={MAX_DEPTH}，数据结构与判据预期不符")

    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from leaves(v, f"{path}.{k}" if path else str(k), depth + 1)
    elif isinstance(obj, list):
        # ⚠ 不再跳过 list。同名字段在 list 里会重复很多次，
        # 但判定单位是**字段名**（§66.1），报告层会去重。
        for i, v in enumerate(obj):
            yield from leaves(v, f"{path}[{i}]", depth + 1)
    else:
        if obj is None or (isinstance(obj, str) and obj == ""):
            return
        name = path.rsplit(".", 1)[-1] if "." in path else path
        # [0] 之类的下标后缀要在点分路径里剥掉：variants[1].margin 的
        # 字段名是 margin，不是 "1].margin"
        if "[" in name:
            head, _, rest = name.partition("[")
            name = rest.split("]", 1)[-1] if "]" in rest else head
        yield path, name, obj


def name_pattern(name: str) -> re.Pattern:
    """
    字段名匹配必须带标识符边界。

    ⚠⚠ 踩过的坑：`margin` 是 `specificity_margin` / `best_margin` 的子串；
    `mean` 是 `group_mean` 的子串。不加边界，`margin` 会「因为
    specificity_margin 被读了」而假通过 —— 而页面上那个数根本不是 margin。
    ⇒ 两侧都不许相邻 [A-Za-z0-9_]。
    """
    esc = re.escape(name)
    return re.compile(rf"(?<![A-Za-z0-9_]){esc}(?![A-Za-z0-9_])")


def check() -> dict:
    report: dict = {
        "artifacts": [],
        "n_components_checked": 0,
        "n_leaves_total": 0,
        "max_depth_seen": 0,
        "unrendered": [],
        "exempt_used": [],
        "exempt_table_size": len(EXEMPT),
        "errors": [],
    }

    for rel, hosts in SCOPE:
        apath = ROOT / rel
        if not apath.exists():
            report["errors"].append(f"产物不存在：{rel}")
            continue

        src = ""
        host_ok = []
        for h in hosts:
            hp = ROOT / h
            if not hp.exists():
                report["errors"].append(f"组件不存在：{h}")
                continue
            src += "\n" + hp.read_text(encoding="utf-8")
            host_ok.append(h)
        report["n_components_checked"] += len(host_ok)

        data = json.loads(apath.read_text(encoding="utf-8"))
        got = list(leaves(data))
        report["n_leaves_total"] += len(got)

        # ── Y1a：报下钻到的最大深度 ──────────────────────────────────
        # ⚠⚠ 第一版 `n_leaves_total` = 435（非零）却整片没扫 variants[]，
        # 空通过防护因此失效。现在额外报最大深度，并在深度过浅时判红。
        depth_here = max((p.count(".") + p.count("[") for p, _, _ in got),
                         default=0)
        report["max_depth_seen"] = max(report["max_depth_seen"], depth_here)

        art = {
            "artifact": rel,
            "hosts": host_ok,
            "n_leaves": len(got),
            "depth": depth_here,
            "unrendered": [],
            "n_unrendered": 0,
            "n_exempt": 0,
            "exempt_hits": [],
        }
        # 判定单位是**字段名**（§66.1）：同一字段名在 list 里出现几十次，
        # 只报一次并记下它出现过几次，免得「未渲染清单」被一个名字淹没。
        seen_names: dict[str, dict] = {}
        n_exempt_names = 0
        # ⚠⚠ 修订 72（W6）：本守卫判的是**字段名**，不是路径。
        #   「字段名在源码里出现过」**不等于**「这个字段被渲染了」——
        #   同名的字段可能挂在完全不同的路径下。
        #   这里把「名字命中但父路径在源码里没有对应形态」的叶子**单独记下来**，
        #   它们仍然算「已覆盖」（不改变 Y1 的判红条件），
        #   但必须被**报出来**，否则「未渲染 0」会被读成「都渲染了」。
        weak: list[dict] = []
        n_name_hit = 0
        n_empty_name = 0
        for lpath, lname, val in got:
            # ⚠⚠ 字段名为**空串**的叶子（标量直接躺在 list 里，如 `built_from[0]`）
            #   会被编译成 `(?<![A-Za-z0-9_])(?![A-Za-z0-9_])` ——
            #   只要源码**不以 ASCII 字母/数字/下划线开头**就匹配。
            #   真实的 .tsx 都不以它开头 ⇒ 这些叶子**全部自动判为「已覆盖」**，
            #   而它根本没有名字可供匹配。
            #   这是弱覆盖里**唯一可证**的子集，单独计数、单独报出。
            if not lname:
                n_empty_name += 1
            if name_pattern(lname).search(src):
                n_name_hit += 1
                # ⚠ `lpath` 是**点分字符串**（`a.b[0].c`），不是元组 ——
                #   第一版写 `"/".join(lpath)`，把路径拆成了逐字符输出。
                # 父形态 = 路径的最后两段（`b.c`），它在源码里出现，
                # 才说明宿主是**沿着这个路径**取到值的。
                segs = lpath.rsplit(".", 2)
                parent = ".".join(segs[-2:]) if len(segs) >= 2 else lpath
                if not name_pattern(parent).search(src):
                    weak.append({"field": lname, "path": lpath,
                                 "parent_form_absent": parent,
                                 "sample": repr(val)[:60]})
                continue
            reason = EXEMPT.get(lname)
            if reason is not None:
                n_exempt_names += 1
                continue
            e = seen_names.get(lname)
            if e is None:
                seen_names[lname] = {
                    "field": lname, "path": lpath, "sample": repr(val)[:60],
                    "n_occurrences": 1}
            else:
                e["n_occurrences"] += 1

        for lname, e in seen_names.items():
            art["unrendered"].append(e)
            report["unrendered"].append({"artifact": rel, **e})
        art["n_unrendered"] = len(art["unrendered"])
        art["n_exempt"] = n_exempt_names
        # ⚠⚠ 豁免条目按 (产物, 字段) 记账，而不是按字段名 ——
        #   同一个名字（如 `label` / `rule`）在多个产物里都出现，
        #   第一版按名字累加，输出过「表大小 27 / 用掉 30」这种
        #   **用得比表还多**的自相矛盾数字。
        #   「表大小」是**去重后的表长**，「用掉」是**本次实际命中的条目数**，
        #   两者单位不同，不许互相比较 ⇒ 报告里分开印，别放在同一句里。
        for lname in sorted({ln for ln, _, _ in got if ln in EXEMPT}):
            art["exempt_hits"].append(lname)
            report["exempt_used"].append(
                {"artifact": rel, "field": lname, "reason": EXEMPT[lname]})
        art["n_name_hit"] = n_name_hit
        art["n_empty_name"] = n_empty_name
        art["n_weak"] = len(weak)
        art["weak_sample"] = weak[:12]
        report["artifacts"].append(art)

    # ⚠ 修订 72（W6-5）：叶子总数为 0 必须判红。
    #   否则「弱覆盖 0 个」会从一个**空扫描**里漂亮地报出来。
    #   `n_leaves_total` 在上面已按产物累加，这里只汇总新增的两项。
    report["n_weak_total"] = sum(a.get("n_weak", 0) for a in report["artifacts"])
    report["n_name_hit_total"] = sum(a.get("n_name_hit", 0)
                                     for a in report["artifacts"])
    report["n_empty_name_total"] = sum(a.get("n_empty_name", 0)
                                       for a in report["artifacts"])

    # 去重：同一 (产物, 字段) 只记一次
    seen_pairs = set()
    deduped = []
    for e in report["exempt_used"]:
        k = (e["artifact"], e["field"])
        if k in seen_pairs:
            continue
        seen_pairs.add(k)
        deduped.append(e)
    report["exempt_used"] = deduped
    return report


# ── 阳性对照（§「判据上线前必须做扰动测试」）─────────────────────────────
def positive_control() -> dict:
    """
    注入一个宿主组件里**不可能出现**的字段名，确认判据仍判红。

    ⚠⚠ 对照自己坏过 5 次的教训：必须**另报 ok_inj**（注入是否真的发生）。
    否则对照的 PASS 会被误读成判据的 PASS。
    """
    fake = "zzz_rev66_should_never_appear"
    injected = False
    # 真正把假字段名塞进一份产物副本里再跑一遍 check()
    apath = ROOT / "frontend/public/latent/data/heldout_readability.json"
    orig = apath.read_bytes()
    try:
        d = json.loads(orig.decode("utf-8"))
        d["recipe"][fake] = 12345
        apath.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        injected = True

        # 组件源码里当然没有这个字段名 ⇒ 它必须落进 unrendered
        found = any(u["field"] == fake for u in check()["unrendered"])
    finally:
        apath.write_bytes(orig)

    return {"ok_inj": injected, "caught": bool(found), "field": fake}


def main() -> int:
    rep = check()

    print("=" * 78)
    print("修订 66 · Y1 渲染覆盖（产物里的叶子字段有没有真的被页面读到）")
    print("=" * 78)

    # ── 空通过防护：先报「扫了几个」，再报「抓到几个」────────────────────
    print(f"\n[计数] 扫到组件 {rep['n_components_checked']} 个"
          f"（要求 > 0）")
    print(f"[计数] 扫到叶子字段 {rep['n_leaves_total']} 个"
          f"（要求 > 0）")
    print(f"[深度] 下钻到 {rep['max_depth_seen']} 层"
          f"（下限 {MIN_DEPTH_EXPECTED}，上限 {MAX_DEPTH}）"
          f"{'  ⚠ 偏浅 ⇒ 可能整片容器没进检查' if rep['max_depth_seen'] < MIN_DEPTH_EXPECTED else ''}")
    print(f"[豁免] 表里列了 {rep['exempt_table_size']} 个字段名"
          f"；本轮实际命中 {len(rep['exempt_used'])} 个 (产物, 字段) 条目"
          f"　⚠ 两个数单位不同，不可互相比较")
    for e in rep["exempt_used"]:
        print(f"        - {e['artifact'].split('/')[-1]}:{e['field']}"
              f" → {e['reason']}")
    if rep["exempt_table_size"] == 0:
        print("        ⚠ 豁免表为空 —— 本项对该类字段**无判据**")

    for err in rep["errors"]:
        print(f"[错误] {err}")

    print()
    for art in rep["artifacts"]:
        print(f"── {art['artifact']}")
        print(f"   宿主组件 {len(art['hosts'])} 个：{', '.join(art['hosts'])}")
        print(f"   叶子字段 {art['n_leaves']} 个（深度 {art['depth']}）"
              f" / 豁免 {art['n_exempt']} / **未渲染 {art['n_unrendered']}**")
        for u in art["unrendered"]:
            extra = (f" ×{u['n_occurrences']}"
                     if u["n_occurrences"] > 1 else "")
            print(f"      ✗ {u['field']}{extra}  首见 {u['path']}"
                  f"  = {u['sample']}")

    # ── 判定 ────────────────────────────────────────────────────────────
    print()
    pc = positive_control()
    print(f"[阳性对照] ok_inj={pc['ok_inj']}  caught={pc['caught']}"
          f"  field={pc['field']}")

    fails: list[str] = []
    if rep["n_components_checked"] == 0:
        fails.append("没检查到任何组件 ⇒ 本项无判据（不得报 PASS）")
    if rep["n_leaves_total"] == 0:
        fails.append("没抽出任何叶子字段 ⇒ 本项无判据（不得报 PASS）")
    if rep["max_depth_seen"] < MIN_DEPTH_EXPECTED:
        fails.append(
            f"全局下钻深度只有 {rep['max_depth_seen']}，"
            f"< {MIN_DEPTH_EXPECTED} ⇒ 很可能整片容器没进检查")
    if rep["errors"]:
        fails.extend(rep["errors"])
    if not pc["ok_inj"]:
        fails.append("阳性对照注入失败 ⇒ 对照没跑，不是判据通过")
    if pc["ok_inj"] and not pc["caught"]:
        fails.append("阳性对照注入成功但判据没抓到 ⇒ 判据恒真")
    if rep["unrendered"]:
        fails.append(f"{len(rep['unrendered'])} 个叶子字段从未被页面读到")

    print()
    if fails:
        print("FAIL 修订 66 Y1 渲染覆盖：")
        for f in fails:
            print(f"  ✗ {f}")
        return 1

    # ⚠⚠ 修订 72（W6）：把「弱覆盖」印出来。
    #   本守卫判的是**字段名**，不是路径 —— 「字段名在源码里出现过」
    #   **不等于**「这个字段被渲染了」（同名字段可能挂在不同路径下）。
    #   ⇒ 这一行不许被读成「都渲染了」。
    weak_tot = rep["n_weak_total"]
    hit_tot = rep["n_name_hit_total"]
    leaf_tot = rep["n_leaves_total"]
    pct = (100.0 * weak_tot / hit_tot) if hit_tot else 0.0
    print(f"PASS Y1 渲染覆盖：扫 {leaf_tot} 个叶子字段 / "
          f"{rep['n_components_checked']} 个组件，未渲染 0 个"
          f"（豁免 {len(rep['exempt_used'])}/{rep['exempt_table_size']}）")
    print(f"  ⚠⚠ 其中 {weak_tot} 个是**弱覆盖**（字段名命中、"
          f"父路径在源码里无对应形态），占名字命中的 {pct:.1f}%"
          f" —— **这些不能读成「已渲染」**：本守卫判的是字段名，不是路径。")
    emp = rep["n_empty_name_total"]
    print(f"  ⚠⚠ 其中 {emp} 个叶子的**字段名是空串**"
          f"（标量直接躺在 list 里，如 built_from[0]）—— 空正则只要源码不以 "
          f"ASCII 字母开头就匹配 ⇒ 它们**全部自动判为「已覆盖」**，"
          f"而它根本没有名字可供匹配。这是弱覆盖里**唯一可证**的子集。")
    # ⚠ 修订 73：把上面的弱覆盖**拆成三级**，否则「弱覆盖 1062」会被读成
    #   「1062 个没渲染」——它只是「名字命中但路径对不上」。
    try:
        tier = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parent
                                 / "check_render_tiers.py")],
            capture_output=True, text=True, timeout=300)
        for line in tier.stdout.splitlines():
            if ("A 强" in line or "B 循环" in line or "C 弱" in line):
                print(f"  [修订 73 分级] {line.strip()}")
    except Exception as exc:                      # noqa: BLE001
        print(f"  ⚠ 三级分级没跑成（{type(exc).__name__}: {exc}）"
              f" ⇒ 本项对「弱覆盖里有多少真没渲染」**无判据**，"
              f"别把 {weak_tot} 读成「有 {weak_tot} 个没渲染」")
    for a in rep["artifacts"]:
        if not a.get("n_weak"):
            continue
        print(f"    {a['artifact']}：{a['n_weak']} / {a['n_leaves']}")
        for w in a["weak_sample"]:
            print(f"       · {w['path']}  (父形态 `{w['parent_form_absent']}` 缺席)")
    return 0


if __name__ == "__main__":
    sys.exit(main())