#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 85 Y1b：**空字段名的叶子不得计入「已覆盖」，必须改按「所属 list 的名字」判定**。

判据原文：预登记 §85.1（形态侦察）+ §85.2（Y1b-a/b/c/d）+ §85.3（5 条对照）+ §85.5（判据更正）。

⚠⚠⚴ 两条实现纪律：
  1. **复用而不复算**：直接 import `check_render_coverage.py`，用**它自己的**
     `leaves()` / `name_pattern()` / `SCOPE`。
     ⚠⚠ 否则 Y1b 的红可能来自「两把尺子对同一棵树给出不同的叶子集」，
     ⚠ 而那正是本项目反复栽的坑（§82.8 / §83 的下标与 helper 键空间）。
  2. **不碰冻结判据**：`check_render_coverage.py` 是冻结判据（有豁免表与阳性对照），
     ⚠ 本脚本**只读**它的函数与常量，一个字都不改（§85.2 Y1b-d）。

⚠⚠⚴ 判红的措辞必须是「**无法判定**」而不是「未渲染」——
「list 名在源码里没出现」**推不出**「这个 list 没被渲染」（它完全可能经由变量遍历）。
⚠ **标签不得比它的证据强**。
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent

_idx = re.compile(r"\[\d+\]")


def load_y1():
    spec = importlib.util.spec_from_file_location("y1", HERE / "check_render_coverage.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


Y1 = load_y1()


def list_name_of(path: str) -> str:
    """空名叶子的「所属 list 的名字」：剥掉路径尾部所有 `[i]` 后的最后一段。"""
    p = _idx.sub("", path)
    return p.rsplit(".", 1)[-1] if "." in p else p


def judge(pairs: list[tuple[str, object, str]], label: str) -> dict:
    """pairs = [(产物标签, 产物对象, 宿主组件源码拼接)] —— 真实扫描与 5 条对照共用它。"""
    reds: list[str] = []
    n_leaves_named = n_leaves_unnamed = n_leaves_exempt = 0
    lists_regrouped: set[str] = set()
    lists_not_found: dict[str, dict] = {}

    for art_label, data, src in pairs:
        for lpath, lname, _val in Y1.leaves(data, "", 0):
            if lname:
                n_leaves_named += 1
                # ⚠⚠⚴⚠ **必须复用 Y1 的 `EXEMPT` 表**（第一版漏了，报出 27 条假红）。
                #   ⚠⚠ Y1 自己会跳过这 27 个「人列的」字段名（理由多为「页面不展示」），
                #   ⚠ 而我第一版**复现了判断、却没复用豁免表** ⇒ 把豁免项全报成「未渲染」。
                #   ⚠⚠⚴ 这是「独立复算的实现本身可能才是坏的东西」第三次复发：
                #   ⚠ 复用了 `leaves()`/`name_pattern()` 并不等于复用了**判定语义**。
                if lname in Y1.EXEMPT:
                    n_leaves_exempt += 1
                    continue
                # ⚠ 正向通道：有名叶子但名字在源码里找不到 ⇒ 真「未渲染」。
                #   ⚠ 今天真实数据里这一条应为 0（Y1 报「未渲染 0」），它是对照 3 的通道。
                if not Y1.name_pattern(lname).search(src):
                    reds.append(f"⚠ 未渲染（有名叶子）：{art_label} :: {lpath}"
                                 f"  字段名 `{lname}` 在宿主源码里没出现")
            else:
                n_leaves_unnamed += 1
                nm = list_name_of(lpath)
                key = f"{art_label}::{nm}"
                lists_regrouped.add(key)
                if not Y1.name_pattern(nm).search(src):
                    lists_not_found.setdefault(key, {
                        "artifact": art_label, "list_name": nm, "n_leaves": 0, "sample": None})
                    lists_not_found[key]["n_leaves"] += 1
                    if lists_not_found[key]["sample"] is None:
                        lists_not_found[key]["sample"] = lpath

    # ⚠ 空名通道：**无法判定**（不是「未渲染」）
    for key, info in sorted(lists_not_found.items()):
        reds.append(
            f"⚠ **无法判定**（空字段名叶子）：{info['artifact']} :: {info['sample']} …\n"
            f"    所属 list 名 `{info['list_name']}` 在宿主源码里**找不到**\n"
            f"    该 list 下有 **{info['n_leaves']}** 个空字段名叶子"
            f"（原被 Y1 的空正则自动判为「已覆盖」）\n"
            f"    ⚠ **这不是「未渲染」的证据** —— 它只说明「按 list 名这一层**判不了**」，"
            f"该 list 完全可能经由变量被遍历。")

    # ⚠ Y1b-c（§85.5 更正后）：只留 `n_leaves_unnamed == 0`；
    #   ⚠ `n_lists_regrouped == 0` 与它**逻辑等价**，是死条件，已删。
    if n_leaves_unnamed == 0:
        reds.append(f"⚠ Y1b-c：{label} 的空字段名叶子 = **0** ⇒ 「按 list 名归并」这条通道"
                    f"在本产物上从未被行使 ⇒ 判红")
    # ⚠ §85.5 换上的**独立**通道：空扫描防护
    if len(pairs) == 0:
        reds.append(f"⚠ §85.5：{label} 的 scope 是**空的**（0 个产物）⇒ "
                    f"Y1b 会从一个空扫描里漂亮地报绿 ⇒ 判红")

    return {
        "label": label, "n_artifacts": len(pairs),
        "n_leaves_named": n_leaves_named, "n_leaves_unnamed": n_leaves_unnamed,
        "n_leaves_exempt": n_leaves_exempt,
        "exempt_table_size": len(Y1.EXEMPT),
        "n_lists_regrouped": len(lists_regrouped),
        "n_lists_not_found": len(lists_not_found),
        "n_leaves_unjudgeable": sum(i["n_leaves"] for i in lists_not_found.values()),
        "lists_not_found": lists_not_found,
        "reds": reds, "green": not reds,
    }


# ---------------------------------------------------------------- 对照

def _yn(b: bool) -> str:
    return "是" if b else "否"


def run_controls() -> tuple[bool, list[str]]:
    lines: list[str] = []
    ok = True

    # 对照 1：空名叶子，其 list 名**在**宿主源码里 ⇒ 绿
    d1 = {"dose_ladder": [1, 2, 3]}
    r1 = judge([("ctl1", d1, "const rows = Object.entries(d.dose_ladder);")], "对照1")
    ok1 = r1["green"] and r1["n_leaves_unnamed"] == 3
    lines.append("对照1 空名叶子 + list 名在源码里   : 判绿=%s 空名叶子=%d（期望 绿 / 3）%s"
                 % (_yn(r1["green"]), r1["n_leaves_unnamed"], "✅" if ok1 else "✗")); ok &= ok1

    # 对照 2：空名叶子，其 list 名**不在**宿主源码里 ⇒ 红（且印出五要素）
    # ⚠⚠⚴ 第一版我把这行写成 `// 故意不出现 dose_ladder` ——
    #   ⚠ **注释里自己出现了那个名字** ⇒ name_pattern 命中 ⇒ 对照 2 假绿。
    #   ⚠ 「用来证明『不含』的样本，自己绝不能含」——这是合成对照的第一条纪律。
    d2 = {"dose_ladder": [1, 2, 3]}
    r2 = judge([("ctl2", d2, "const unrelated = 1;")], "对照2")
    has5 = ("ctl2" in r2["reds"][0] and "dose_ladder[0]" in r2["reds"][0]
            and "3" in r2["reds"][0] and "无法判定" in r2["reds"][0]) if r2["reds"] else False
    ok2 = (not r2["green"]) and r2["n_lists_not_found"] == 1 \
        and r2["n_leaves_unjudgeable"] == 3 and has5
    lines.append("对照2 空名叶子 + list 名**不在**源码: 判绿=%s 找不到的list=%d 无法判定叶子=%d"
                 " 五要素齐=%s（期望 否 / 1 / 3 / 是）%s"
                 % (_yn(r2["green"]), r2["n_lists_not_found"],
                    r2["n_leaves_unjudgeable"], _yn(has5), "✅" if ok2 else "✗")); ok &= ok2

    # 对照 3（**正向对照**）：**有名**叶子，名字不在源码里 ⇒ 红
    d3 = {"missing_field": 1, "present_field": 2}
    r3 = judge([("ctl3", d3, "const present_field = 1;")], "对照3")
    ok3 = (not r3["green"]) and r3["n_leaves_named"] == 2 and r3["n_leaves_unnamed"] == 0
    lines.append("对照3 **有名**叶子但名字不在源码  : 判绿=%s 有名=%d 空名=%d（期望 否 / 2 / 0）%s"
                 % (_yn(r3["green"]), r3["n_leaves_named"],
                    r3["n_leaves_unnamed"], "✅" if ok3 else "✗")); ok &= ok3

    # 对照 4：产物里没有任何空名叶子 ⇒ 红（Y1b-c）
    d4 = {"only_named": {"inner": 1}}
    r4 = judge([("ctl4", d4, "const only_named = 1; const inner = 2;")], "对照4")
    ok4 = (not r4["green"]) and r4["n_leaves_unnamed"] == 0
    lines.append("对照4 产物里没有空名叶子        : 判绿=%s 空名=%d（期望 否 / 0）%s"
                 % (_yn(r4["green"]), r4["n_leaves_unnamed"], "✅" if ok4 else "✗")); ok &= ok4

    # 对照 5（§85.5 换上的**独立**通道）：scope 为空 ⇒ 红
    r5 = judge([], "对照5")
    ok5 = (not r5["green"]) and r5["n_artifacts"] == 0
    lines.append("对照5 scope 为空（0 个产物）   : 判绿=%s n_artifacts=%d（期望 否 / 0）%s"
                 % (_yn(r5["green"]), r5["n_artifacts"], "✅" if ok5 else "✗")); ok &= ok5

    return ok, lines


# ---------------------------------------------------------------- main

def main() -> int:
    print("=== 修订 85 Y1b：空字段名叶子改按「所属 list 的名字」判定 ===\n")
    print("---- 对照（先跑；不过就不发数）----")
    try:
        ok, lines = run_controls()
    except SystemExit:
        raise
    except Exception as e:
        print(f"⚠⚠⚠ 对照**崩了**（不是「对照失败」）：{type(e).__name__}: {e}")
        return 2
    for l in lines:
        print("  " + l)
    print(f"\n对照 {'全部符合期望' if ok else '⚠⚠ 有对照不符合期望'}")
    if not ok:
        print("⚠⚠⚠ 对照没过 ⇒ 本脚本不可信，**不发数**")
        return 1

    print("\n---- 真实扫描 ----")
    print(f"⚠ 复用 Y1 的 scope（不另立映射）：{len(Y1.SCOPE)} 个产物\n")
    pairs = []
    for rel, hosts in Y1.SCOPE:
        apath = ROOT / rel
        if not apath.exists():
            print(f"⚠⚠⚠ 产物不存在：{rel} ⇒ **这是没测成，不是「没有」**")
            return 2
        src = ""
        for h in hosts:
            hp = ROOT / h
            if not hp.exists():
                print(f"⚠⚠⚠ 宿主组件不存在：{h} ⇒ **这是没测成**")
                return 2
            src += "\n" + hp.read_text(encoding="utf-8")
        pairs.append((f"{rel}（宿主 {', '.join(hosts)}）",
                      json.loads(apath.read_text(encoding="utf-8")), src))

    res = judge(pairs, "真实扫描")

    print(f"产物数                          : {res['n_artifacts']}")
    print(f"⚠ **有名**叶子（可按字段名判定）  : {res['n_leaves_named']}")
    print(f"⚠ **空字段名**叶子（Y1b 的主体）  : {res['n_leaves_unnamed']}")
    print(f"    ↳ 其中 **{res['n_leaves_exempt']}** 个名字在 Y1 的 EXEMPT 表里"
          f"（表 {res['exempt_table_size']} 条，人列的）⇒ 本守卫也不判它们"
          f"（⚠ 这是**有名**叶子里的豁免，⚠ **不是**上面 213 里的）")
    print()
    print(f"对账：有名 {res['n_leaves_named']} + 空名 {res['n_leaves_unnamed']} = "
          f"{res['n_leaves_named'] + res['n_leaves_unnamed']}"
          f"（⚠ 必须等于 Y1 的 n_leaves_total = 1319，否则说明两把尺子的叶子集不一致）")
    print(f"  ⇐ Y1 旧口径把 {res['n_leaves_unnamed']} 个空名叶子也算进「已覆盖」⇒ 分母虚增")
    print(f"归并出的不同 list 名             : {res['n_lists_regrouped']}")
    print(f"⚠ 宿主源码里**找不到**的 list 名  : {res['n_lists_not_found']}")
    print(f"⚠ **无法判定**的叶子            : {res['n_leaves_unjudgeable']}")
    print()
    for key, info in sorted(res["lists_not_found"].items()):
        print(f"  {info['artifact']}")
        print(f"    list 名 `{info['list_name']}`（{info['n_leaves']} 个空名叶子，例：{info['sample']}）")

    print()
    if res["reds"]:
        print("⚠⚠⚴ 判红：")
        for r in res["reds"]:
            print("  " + r)
        print()
        print("⚠⚠⚴ 读法提醒：这些是「**无法判定**」，**不是「未渲染」**。")
        print("   「list 名在宿主源码里没出现」推不出「这个 list 没被渲染」——")
        print("   它完全可能经由一个变量被遍历。⚠ 「该不该把它们补到页面上」是**设计问题**，")
        print("   判据不替人决定（承修订 78 `neg_ids` 的先例：先问，不先做）。")
        return 1
    print("✅ Y1b 判绿：空字段名叶子按所属 list 名全部可判定，且无未渲染的有名字段。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
