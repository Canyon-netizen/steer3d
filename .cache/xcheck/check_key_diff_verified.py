#!/usr/bin/env python3
"""修订 81 §81.2 的 **J2**：J1 报出的每一对「key 集合不同」都必须**有核实记录**。

⚠⚠⚴ 为什么用「核实记录」代替 AST 自动判「渲染方式」（§81.1）：
   1. 假红风险：`per_token` 那对差异**经人工核实是安全的**，一个写不准的
      AST 判据会把**写得比我设想更好的代码**判成缺陷 ⇒ 假欠账比漏报危险得多；
   2. 「两块是并排还是上下」是 **CSS 布局**问题，JSX 里根本没有这个信息；
   3. 「并集遍历」的 AST 形状不唯一，枚举必然不全。

⚠⚠⚴ **本脚本对核实清单只读，绝不自己往里加东西**（§81.2 第 3 条）。
⚠ 加条目必须由人写并附理由 ⇒ 挂账表不许自动增长。

⚠ 记录里必须写 `render` **本身**，不能只写「安全」两个字 ——
「已排除 ≠ 已验证」（承 §74 的 W8c 分类）。

用法：python3 .cache/xcheck/check_key_diff_verified.py [--selfcheck]
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DATA = ROOT / "frontend/public/latent/data"
VERIFIED = HERE / "j1_verified.json"
CTL = ROOT / ".cache/mutbak/j2ctl"


def load_j1():
    spec = importlib.util.spec_from_file_location(
        "j1", HERE / "check_record_key_sets.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def pair_key(artifact: str, field: str, a: str, b: str) -> str:
    """⚠ 配对是**无序**的：J1 按发现顺序给 (A,B)，清单里可能写反。"""
    return f"{artifact}|{field}|{'␟'.join(sorted([a, b]))}"


def check(diffs, verified: list) -> dict:
    vkeys = {pair_key(v.get("artifact", ""), v.get("field", ""),
                       *sorted(v.get("paths", []))) for v in verified}
    done, todo = [], []
    for label, a, b, _only_a, _only_b in diffs:
        art_field = label.split(" ", 1)
        artifact = art_field[0]
        field = art_field[1].strip("`") if len(art_field) > 1 else ""
        k = pair_key(artifact, field, a, b)
        (done if k in vkeys else todo).append((label, a, b, k))
    return {"n_diff": len(diffs), "n_done": len(done), "n_todo": len(todo),
            "done": done, "todo": todo}


def selfcheck() -> int:
    """§81.4 的四条阳性对照。⚠ 每条用**独立目录**（上一轮的教训）。"""
    print("=== 阳性对照 ===\n")
    j1 = load_j1()
    cases = [
        ("c1", {"a": {"per_id": {"1": {"x": 1}, "2": {"x": 2}}},
                "b": {"per_id": {"2": {"x": 2}, "1": {"x": 1}}}}, 0, "green",
         "0 对差异 ⇒ 绿，且必须印「本次 0 对」"),
        ("c2", {"a": {"per_id": {"1": {"x": 1}, "2": {"x": 2}}},
                "b": {"per_id": {"2": {"x": 2}, "3": {"x": 3}}}}, 1, "verified",
         "1 对差异 + 有核实记录 ⇒ 绿"),
        ("c3", {"a": {"per_id": {"1": {"x": 1}, "2": {"x": 2}}},
                "b": {"per_id": {"2": {"x": 2}, "3": {"x": 3}}}}, 1, "none",
         "⚠ 1 对差异 + **无**记录 ⇒ 判红"),
        ("c4", {"a": {"per_id": {"1": {"x": 1}, "2": {"x": 2}}},
                "b": {"per_id": {"2": {"x": 2}}},
                "c": {"per_id": {"9": {"x": 9}}}}, 3, "one_of_two",
         "⚠ 3 对差异（3 张同名表两两配对）只有 1 条记录 ⇒ 判红（未核实 2）"),
    ]
    n_ok = 0
    for tag, payload, n_diff, mode, why in cases:
        one = CTL / tag
        if one.exists():
            shutil.rmtree(one)
        one.mkdir(parents=True)
        try:
            (one / "case.json").write_text(json.dumps(payload, ensure_ascii=False),
                                           encoding="utf-8")
            r = j1.scan_dir(one, tag)
            verified = []
            if mode == "verified":
                # ⚠⚠ 第一版写 `sorted(x[1] for x in r["diffs"])` —— `r["diffs"]` 的
                #   元素是 (label, a, b, …)，`x[1]` 只有 **a** 一个路径
                #   ⇒ paths 长度 1 ⇒ `pair_key()` 缺参数 ⇒ 对照崩在 TypeError。
                #   ⚠ 崩溃被「没跑」分支正确捕获了，但**不能**把它当对照通过。
                if not r["diffs"]:
                    raise RuntimeError("对照 c2 本该有差异，却报 0 —— 先查对照数据")
                verified = [{"artifact": "case.json", "field": "per_id",
                             "paths": sorted([r["diffs"][0][1], r["diffs"][0][2]])}]
            elif mode == "one_of_two":
                a, b = r["diffs"][0][1], r["diffs"][0][2]
                verified = [{"artifact": "case.json", "field": "per_id",
                             "paths": sorted([a, b])}]
            res = check(r["diffs"], verified)
            red = res["n_todo"] > 0
            expect_red = (mode in ("none", "one_of_two"))
            ok = (res["n_diff"] == n_diff) and (red == expect_red)
            if ok:
                n_ok += 1
            print(f"  {'✓' if ok else '✗'} 对照 {tag}: 差异 {res['n_diff']}"
                  f"（期望 {n_diff}）已核实 {res['n_done']} 未核实 {res['n_todo']}"
                  f" ⇒ {'判红' if red else '判绿'}（期望{'判红' if expect_red else '判绿'}）"
                  f"  —— {why}")
        except Exception as e:
            print(f"  ⚠ 对照 {tag} **没跑**（不是「对照失败」）：{e}")
    print(f"\n对照 {n_ok}/{len(cases)}")
    if n_ok != len(cases):
        print("⚠⚠ 对照没过 ⇒ 本脚本不可信，**不发数**")
        return 1
    return 0


def main() -> int:
    if "--selfcheck" in sys.argv:
        return selfcheck()

    # ⚠⚠⚠⚠ **取数前强制跑对照，且在同一次调用里。**
    #   这条直接来自我自己在修订 80 §80.7 记下的失误：
    #   「守卫说『不发数』，我还是手工跑了取数命令」。
    #   ⇒ 若 `--selfcheck` 与正式取数是两个命令，我可以在两者之间插入任何东西，
    #     「对照没过 ⇒ 不发数」就只是**一句提醒**而不是**一道机制**。
    #   ⇒ 这里是代码层面的闸：**对照不过，下面的数字根本不会被打印。**
    print("=== 修订 81 J2：J1 的每一对差异都必须有核实记录 ===\n")
    print("⚠ 先跑阳性对照（不过则**不发数**，且这是同一次调用）\n")
    if selfcheck() != 0:
        print("\n⚠⚠⚠ 对照没过 ⇒ **本次调用到此为止，不发任何数**。")
        return 1
    print("-" * 78)

    j1 = load_j1()
    r = j1.scan_dir(DATA, "frontend/public/latent/data")

    if not VERIFIED.exists():
        print(f"❌ 找不到核实清单 {VERIFIED} ⇒ 判红")
        print("   ⚠ 本脚本**只读**清单，绝不自己创建 —— 创建必须由人完成。")
        return 1
    try:
        verified = json.loads(VERIFIED.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"❌ 核实清单读不了：{e} ⇒ **这是没读成，不是「没有记录」**")
        return 2

    res = check(r["diffs"], verified)

    print(f"J2a J1 扫了 {r['n_files']} 个产物、{r['n_tables']} 张 Record 表，"
          f"同名配对 {r['n_pairs']} 对")
    print(f"J2b ⚠ 其中 **key 集合不同**：{res['n_diff']} 对")
    print(f"J2c 其中**已核实**：{res['n_done']} ／ ⚠ **未核实**：{res['n_todo']}")
    print(f"J2d 核实清单共 {len(verified)} 条（本脚本**只读**，绝不自己加条目）")

    for label, a, b, _k in res["done"]:
        print(f"  ✓ 已核实 {label}")
    for label, a, b, k in res["todo"]:
        print(f"  ⚠⚠ **未核实** {label}")
        print(f"      {a}")
        print(f"      {b}")
        print(f"      配对键：{k}")

    # ⚠ render_marker 只**提醒**，不判红（判据未写这条，别偷偷扩大判据）
    src = (ROOT / "frontend/components/BPathPanel.tsx")
    if src.exists():
        text = src.read_text(encoding="utf-8")
        print()
        for v in verified:
            m = v.get("render_marker")
            if not m:
                continue
            present = m in text
            print(f"  {'✓' if present else '⚠⚠'} render_marker {m!r} "
                  f"{'仍在 BPathPanel.tsx 里' if present else '**已消失 ⇒ 该核实可能过期，须重新核实**'}")

    print()
    if res["n_diff"] == 0:
        print("✅ 本次 0 对差异 ⇒ **无待核实项**（不是「已证明没有」，是「这次没有」）")
        return 0
    if res["n_todo"] > 0:
        print(f"❌ 判红 {res['n_todo']} 对：key 集合不同却**没有核实记录**。")
        print("   ⇒ 须由人核实渲染方式（并集遍历？一张表两列？还是两张独立并排表？）")
        print("     并把记录写进 .cache/xcheck/j1_verified.json —— **不要把判据改宽**。")
        return 1
    print(f"✅ {res['n_diff']} 对差异**全部已核实** ⇒ 判绿。")
    print("   ⚠「已核实」不等于「已验证渲染正确」，只等于「渲染方式已被人看过并写下理由」。")
    return 0


if __name__ == "__main__":
    sys.exit(main())