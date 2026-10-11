#!/usr/bin/env python3
"""修订 75 §75.1 的 S1/S2/S3：**类型声明不是渲染证据**。

⚠⚠ 这一类 Y1 / W6 / W7 全都不覆盖：
   一个字段名可以出现在组件的**类型声明**里，因而在任何字符串搜索里
   都「有名字」，而它**从来没有被取值过**（`selfcheck_detail` 就这么漏过了 W7）。

⚠ S1 判的是「**没被取值**」，**不是**「读者看不到」——
   若某个组件把整个对象当 prop 传下去，本守卫看不见（承 W7c 的同一条限制）。

用法：python3 .cache/xcheck/check_type_only.py
"""
from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
INSTR = HERE / "ts_access_paths.js"
CTL = ROOT / ".cache/mutbak/typectl/components"


def load_tiers():
    spec = importlib.util.spec_from_file_location(
        "tiers", HERE / "check_render_tiers.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def type_names_for(component_dir: Path) -> tuple[set[str], set[str], dict]:
    p = subprocess.run(["node", str(INSTR), str(component_dir)],
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"⚠ 仪器自检未通过\n{p.stderr.strip()}")
    data = json.loads(p.stdout)
    tnames: set[str] = set()
    anames: set[str] = set()
    for _p, blob in data["panels"].items():
        for _r, b in blob.items():
            tnames |= set(b.get("type_names") or [])
            # ⚠ 一个访问路径 `d/a/b/*/c` 里，**每一段**都是被取过值的名字；
            #   只取最后一段会漏掉容器名（容器同样是被取过的证据）。
            for a in b["accesses"]:
                anames |= set(s for s in a.split("/") if s)
    return tnames, anames, data


def main() -> int:
    print("=== 修订 75 S1/S2/S3：类型声明不是渲染证据 ===\n")
    tiers = load_tiers()
    rows = tiers.classify()
    tnames, anames, data = type_names_for(ROOT / "frontend/components")

    nk = sum(1 for k in data["known_answers"] if k["ok"])
    print(f"仪器已知答案：{nk}/{len(data['known_answers'])} 成立；"
          f"type_names 共 {len(tnames)} 个不同名字")

    buckets: Counter = Counter()
    samples: dict[str, list[str]] = {}
    for r in rows:
        if r["tier"] in ("A", "B"):
            b = "已取值（这条路径被读）"
        elif r["name"] in tnames:
            # ⚠⚠ 措辞必须是「字段名在类型声明里出现过，**且这条路径**没被取值」，
            #   **不是**「仅类型声明」——
            #   「仅类型声明」严格义是「这个名字在全文件里只出现在类型位置」，
            #   那是**另一个、更小的集合**（见下面 n_strict）。
            #   ⚠ 两者混用会把一个更弱的结论读成更强的那个。
            b = "⚑ 名字在类型声明里、该路径未取值"
        else:
            b = "未引用"
        buckets[b] += 1
        samples.setdefault(b, [])
        if len(samples[b]) < 10:
            samples[b].append(f"{r['artifact']}: {r['path']}")

    n_strict = tnames - anames

    print(f"\nS2 分档（对 §73 分级里的 {len(rows)} 个「Y1 判已覆盖」的叶子）：")
    for b, n in buckets.most_common():
        print(f"   {b:<30} {n:5d}  {100*n/len(rows):5.1f}%")
        for s in samples[b][:5]:
            print(f"        · {s}")

    print(f"\n⚠⚠ **三个不同口径，不许混用**：")
    print(f"   (1) 严格 S1：字段名在全文件里**只**出现在类型声明 ⇒ {len(n_strict)} 个名字")
    print(f"       样例：{sorted(n_strict)[:12]}")
    print(f"   (2) 上面表里「⚑ 名字在类型声明里、该路径未取值」⇒ 那是**逐叶子**的判断，"
          f"弱得多：名字可能在别处被取值过，只是**这条路径**没读到。")
    print(f"   (3) 「未引用」：连类型声明里都没有。")
    print(f"\n⚠⚠ 「该路径未取值」的含义：这条字段路径没被组件读过。")
    print("   ⚠ 它**不等于**读者看不到 —— 若整个对象被当 prop 传下去，"
          "本守卫看不见（承 W7c）。")

    # ---- S3 正反对照：在副本上注入，两条缺一就没有牙齿 ----
    print("\nS3 正反对照（真实组件不许改，跑的是打过补丁的副本）：")
    if CTL.exists():
        shutil.rmtree(CTL)
    CTL.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "frontend/components", CTL)

    panel = CTL / "BPathPanel.tsx"
    src = panel.read_text(encoding="utf-8")
    panel.write_text(src + (
        "\ntype _Rev75Probe = { zzz_probe_x: { alpha: number; beta: string } };\n"),
        encoding="utf-8")

    t1, a1, _ = type_names_for(CTL)
    ok_type_only = "zzz_probe_x" in t1 and "zzz_probe_x" not in a1
    print(f"   [{'ok' if ok_type_only else '✗ 未触发'}] "
          f"只加类型声明 ⇒ 进 type_names、不进 accesses")

    src2 = panel.read_text(encoding="utf-8") + \
        "\nconst _p75 = (d: any) => d.zzz_probe_x;\n"
    panel.write_text(src2, encoding="utf-8")
    t2, a2, _ = type_names_for(CTL)
    ok_value = "zzz_probe_x" in a2
    print(f"   [{'ok' if ok_value else '✗ 未触发'}] "
          f"再加表达式取值 ⇒ 进 accesses ⇒ 不再算「该路径未取值」")

    shutil.rmtree(CTL, ignore_errors=True)

    if not (ok_type_only and ok_value):
        print("\n✗ 对照未全部触发 ⇒ 本守卫的判据没有牙齿。")
        return 1
    print("\n✓ S1/S2/S3 通过。⚠「通过」只说明「没抓到现行」，"
          "不代表读者真的看得到每个字段。")
    return 0


if __name__ == "__main__":
    sys.exit(main())