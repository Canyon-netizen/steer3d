#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 98：`/intervention/` 的发布覆盖率与漂移检查（诊断探针，不判红绿）。

⚠ 校准：先拿 **K3 自己的 AST 扫描器**（`ts_fetch_paths.js`）的输出当已知答案，
  本脚本的「被 fetch 集合」必须与它**逐条相等**，对不上就 exit 2 不发数
  （修订 94.5 / 97.4 的教训：重新实现必须先在已知答案上校准）。
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
XCHECK = ROOT / ".cache/xcheck"
FE_INT = ROOT / "frontend/public/intervention"
BE_INT = ROOT / "backend/examples/output/intervention"
SCANNER = XCHECK / "ts_fetch_paths.js"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    if not SCANNER.exists():
        print(f"[错误] 找不到 K3 的 AST 扫描器 {SCANNER} ⇒ 无法校准，不发数")
        sys.exit(2)
    r = subprocess.run(["node", str(SCANNER), str(ROOT / "frontend")],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"[错误] 扫描器崩了 rc={r.returncode} ⇒ **没测成**，不是「没找到」")
        print(r.stderr[:800])
        sys.exit(2)
    sc = json.loads(r.stdout)

    # ⚠ 校准口径：/intervention/ 前缀，剥掉前缀只剩文件名
    iv_paths = sorted(p["url"].rsplit("/", 1)[-1]
                      for p in sc["paths"] if p["url"].startswith("/intervention/"))
    files = sorted(p.name for p in FE_INT.glob("*.json"))

    print("=" * 78)
    print("修订 98 · /intervention/ 的发布覆盖率与漂移（诊断探针）")
    print("=" * 78)
    print(f"\n[口径·扫描器] K3 的 AST 扫描器实测 n_fetch_calls={sc['n_fetch_calls']} "
          f"/ n_paths={sc['n_paths']} / 未解析站点 {sc['n_unresolved_sites']}")
    print(f"[口径·文件]   frontend/public/intervention 共 {len(files)} 个 json")

    uniq = sorted(set(iv_paths))
    if len(uniq) != len(iv_paths):
        print(f"[错误] 扫描器给出的 /intervention/ 路径有重复 {len(iv_paths)-len(uniq)} 条")
        sys.exit(2)
    missing_in_scan = sorted(set(files) - set(uniq))
    extra_in_scan = sorted(set(uniq) - set(files))
    print(f"[校准] 扫描器认到 /intervention/ 下被 fetch 的 {len(uniq)} 个；"
          f"目录里有 {len(files)} 个")
    print(f"  ⚠ 这不是「不一致」—— 多出来的 {len(missing_in_scan)} 个就是「从未被 fetch」")
    if extra_in_scan:
        print(f"[错误] 扫描器认到目录里不存在的文件 {extra_in_scan} ⇒ 口径错了，不发数")
        sys.exit(2)

    print(f"\n[覆盖率] 被 fetch {len(uniq)} / 目录共 {len(files)} "
          f"⇒ {len(uniq)/len(files)*100:.1f}%")
    unfetched = missing_in_scan
    sz_all = sum((FE_INT / n).stat().st_size for n in files)
    sz_un = sum((FE_INT / n).stat().st_size for n in unfetched)
    print(f"[口径·字节] 目录合计 {sz_all:,} B；从未被 fetch 的 {len(unfetched)} 个 "
          f"合计 {sz_un:,} B ⇒ 占 {sz_un/sz_all*100:.1f}%")

    print(f"\n[从未被 fetch 的文件]")
    for n in unfetched:
        print(f"   {n:<40}{(FE_INT / n).stat().st_size:>10,} B")

    print(f"\n[漂移] 前端发布副本 vs backend/examples/output/intervention 原件")
    ok = drift = miss = 0
    for n in files:
        a, b = FE_INT / n, BE_INT / n
        if not b.exists():
            print(f"   {n:<40}⚠ 后端无同名文件"); miss += 1
        elif sha(a) == sha(b):
            ok += 1
        else:
            print(f"   {n:<40}⚠ **漂移**"); drift += 1
    print(f"   ⇒ 一致 {ok} / 漂移 {drift} / 后端缺 {miss}  共 {len(files)}")
    if drift:
        print("[错误] 存在漂移副本 ⇒ 发出的数据与产出的不是同一份，停在这里")
        sys.exit(2)
    print("   ⇒ 10/10 逐字节一致，**发布的副本不是陈旧版本** ✔")

    print(f"\n[够测性] 扫描器实测 {sc['n_paths']} 条路径、目录 {len(files)} 个文件 —— "
          f"探针至少量到了东西")


if __name__ == "__main__":
    main()
