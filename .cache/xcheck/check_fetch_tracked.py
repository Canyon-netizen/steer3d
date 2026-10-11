#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 83 K3：**页面运行时取的每一个数据文件，都必须在仓库里被 git 跟踪**。

判据原文：预登记 §83.1（形态侦察）+ §83.2（K3a/K3b/K3c/K3d）+ §83.3（6 条对照）。

⚠⚠⚴ 为什么要用 AST 仪器而不是正则（§83.1 的实测）：
   `frontend/` 共 26 处 `fetch()`，只有 20 处是字面量 URL；
   ⚠ 其余是 helper 形参 / `.url` 属性 / 模板串常量三种形式
   ⇒ 逐行正则会**低报 6 个真实依赖**，其中包含一整个从未审计过的 `/intervention/` 目录。

⚠⚠⚴ 三条实现纪律：
  1. **取数与对照在同一次调用里**：`main()` 先跑 6 条对照，不过就 `return`。
  2. **守卫用显式 raise / sys.exit，不用 assert**（`python -O` 会关掉 assert）。
  3. **崩溃必须与判红可区分**：崩 ⇒ 打印「⚠⚠⚠ 崩了」rc=2；判红 ⇒ rc=1。
"""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
FRONTEND = ROOT / "frontend"
SCANNER = HERE / "ts_fetch_paths.js"
EXEMPT = HERE / "fetch_exempt.json"
CTL_ROOT = ROOT / ".cache" / "mutbak" / "k3ctl"


# ---------------------------------------------------------------- node 侧

def run_scanner(fe_dir: pathlib.Path) -> dict:
    p = subprocess.run(["node", str(SCANNER), str(fe_dir)], capture_output=True, text=True)
    if p.returncode != 0:
        print(f"⚠⚠⚠ AST 仪器崩了（rc={p.returncode}）⇒ **这是没测成，不是「没找到」**")
        print(p.stderr[:2000])
        raise SystemExit(2)
    try:
        return json.loads(p.stdout)
    except Exception as e:
        print(f"⚠⚠⚠ AST 仪器输出不是 JSON：{e} ⇒ **这是没测成**")
        print(p.stdout[:800])
        raise SystemExit(2)


# ---------------------------------------------------------------- git 侧

def _git(repo: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def git_tracked(repo: pathlib.Path, rel: str) -> bool:
    return _git(repo, "ls-files", "--error-unmatch", "--", rel).returncode == 0


def git_ignored(repo: pathlib.Path, rel: str) -> str:
    p = _git(repo, "check-ignore", "-v", "--", rel)
    return p.stdout.strip() if p.returncode == 0 else ""


def load_exempt(path: pathlib.Path) -> dict[str, str]:
    """⚠ 只读。⚠ 守卫**绝不**往里写条目（承 J2：挂账表不许自动增长）。"""
    if not path.exists():
        print(f"⚠⚠⚠ 豁免登记表不存在：{path} ⇒ 视为**空表**（不猜、不代填）")
        return {}
    d = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for e in d.get("exempt", []):
        # ⚠ 必须写清渠道；空渠道视为没登记（§83.2 K3b）
        ch = str(e.get("channel", "")).strip()
        if e.get("url") and ch:
            out[e["url"]] = ch
    return out


# ---------------------------------------------------------------- 判定

def judge(scan: dict, repo: pathlib.Path, exempt: dict[str, str], label: str) -> dict:
    paths = scan["paths"]
    reds: list[str] = []
    untracked, ignored, missing, exempt_used, tracked = [], [], [], [], []

    for p in paths:
        url = p["url"]
        rel = "frontend/public" + url
        sites = "; ".join(p["sites"])
        if exempt.get(url):
            exempt_used.append((url, exempt[url], sites))
            continue
        if not (repo / rel).exists():
            missing.append((url, rel, sites))
            reds.append(f"⚠ 文件不存在：{url} → {rel}\n    取它的位置：{sites}")
        elif git_tracked(repo, rel):
            tracked.append(url)
        else:
            ig = git_ignored(repo, rel)
            if ig:
                ignored.append((url, rel, ig, sites))
                reds.append(f"⚠ 被 .gitignore 排除且**不在**豁免登记里（排除 ≠ 通过）：{url}\n"
                            f"    {rel}\n    规则：{ig}\n    取它的位置：{sites}")
            else:
                untracked.append((url, rel, sites))
                reds.append(f"⚠ 存在但**未被 git 跟踪**（clone 下来这块面板会整块消失）：{url}\n"
                            f"    {rel}\n    取它的位置：{sites}")

    # K3c：还原不出来的 fetch 必须判红
    for u in scan["unresolved"]:
        reds.append(f"⚠ K3c：fetch 参数无法静态还原成路径 @ {u['file']}:{u['line']} ⇒ 无法判定")

    # K3d：空扫描不得判绿
    if scan["n_fetch_calls"] == 0 or scan["n_paths"] == 0:
        reds.append(f"⚠ K3d：{label} 的 fetch 调用点={scan['n_fetch_calls']}、路径={scan['n_paths']}"
                    f" ⇒ 空扫描，判红")

    return {
        "label": label, "n_fetch_calls": scan["n_fetch_calls"], "by_kind": scan["by_kind"],
        "n_paths": scan["n_paths"], "n_unresolved_sites": scan["n_unresolved_sites"],
        "n_tracked": len(tracked), "n_exempt_used": len(exempt_used),
        "tracked": tracked, "untracked": untracked, "ignored": ignored,
        "missing": missing, "exempt_used": exempt_used,
        "reds": reds, "green": not reds,
    }


# ---------------------------------------------------------------- 对照

TSX_FETCH_LITERAL = '''export default function P() {
  useEffect(() => {
    fetch("/data/tracked.json").then((r) => r.json());
  }, []);
  return null;
}
'''

TSX_FETCH_UNRESOLVABLE = '''const F = "/data";
export default function P() {
  useEffect(() => {
    fetch(makeUrl()).then((r) => r.json());
  }, []);
  return null;
}
'''

TSX_NO_FETCH = '''export default function P() {
  return <div>这个面板不取任何数据</div>;
}
'''


def make_repo(name: str, tsx: str, data_files: dict[str, str],
              commit: list[str], gitignore: list[str]) -> pathlib.Path:
    """⚠ 每条对照一个**独立**临时 git 仓库（共用目录会让它们的文件混在一起）。"""
    d = CTL_ROOT / name
    if d.exists():
        shutil.rmtree(d)
    (d / "frontend" / "components").mkdir(parents=True)
    (d / "frontend" / "public" / "data").mkdir(parents=True)
    (d / "frontend" / "components" / "P.tsx").write_text(tsx, encoding="utf-8")
    for rel, body in data_files.items():
        f = d / "frontend" / "public" / rel.lstrip("/")
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(body, encoding="utf-8")
    if gitignore:
        (d / ".gitignore").write_text("\n".join(gitignore) + "\n", encoding="utf-8")
    _git(d, "init", "-q")
    _git(d, "config", "user.email", "ctl@example.invalid")
    _git(d, "config", "user.name", "K3 control")
    paths = ["frontend/components/P.tsx"]
    if gitignore:
        paths.append(".gitignore")
    paths += ["frontend/public" + p for p in commit]
    # ⚠ 逐个 add（`git add -A` 会被 .gitignore 静默改变结果，且本机 add 被忽略文件返回非零）
    for p in paths:
        _git(d, "add", "-f", "--", p)
    _git(d, "commit", "-q", "-m", "ctl")
    return d


def _yn(b: bool) -> str:
    return "是" if b else "否"


def run_controls() -> tuple[bool, list[str]]:
    lines: list[str] = []
    ok = True

    # 对照 1：被取的文件**已跟踪** ⇒ 绿
    d1 = make_repo("c1_tracked", TSX_FETCH_LITERAL, {"/data/tracked.json": '{"a":1}'},
                   ["/data/tracked.json"], [])
    r1 = judge(run_scanner(d1 / "frontend"), d1, {}, "对照1")
    ok1 = r1["green"] and r1["n_tracked"] == 1
    lines.append("对照1 被取文件已跟踪        : 判绿=%s n_tracked=%d（期望 绿 / 1）%s"
                 % (_yn(r1["green"]), r1["n_tracked"], "✅" if ok1 else "✗")); ok &= ok1

    # 对照 2：存在但**未跟踪** ⇒ 红，且必须印出 URL 与代码位置
    d2 = make_repo("c2_untracked", TSX_FETCH_LITERAL, {"/data/tracked.json": '{"a":1}'}, [], [])
    r2 = judge(run_scanner(d2 / "frontend"), d2, {}, "对照2")
    has_url = any("/data/tracked.json" in x for x in r2["reds"])
    has_site = any("P.tsx" in x for x in r2["reds"])
    ok2 = bool(r2["reds"]) and has_url and has_site and r2["n_tracked"] == 0
    lines.append("对照2 存在但未跟踪          : 判红=%s 印出URL=%s 印出代码位置=%s（期望 红 / 是 / 是）%s"
                 % (_yn(bool(r2["reds"])), _yn(has_url), _yn(has_site), "✅" if ok2 else "✗")); ok &= ok2

    # 对照 3（**排除对照**）：被 .gitignore 排除、未登记 ⇒ 红
    d3 = make_repo("c3_ignored", TSX_FETCH_LITERAL, {"/data/tracked.json": '{"a":1}'},
                   [], ["frontend/public/data/"])
    r3 = judge(run_scanner(d3 / "frontend"), d3, {}, "对照3")
    ok3 = bool(r3["reds"]) and len(r3["ignored"]) == 1
    lines.append("对照3 被 .gitignore 排除、未登记: 判红=%s 命中 ignored=%d（期望 红 / 1）%s"
                 % (_yn(bool(r3["reds"])), len(r3["ignored"]), "✅" if ok3 else "✗")); ok &= ok3

    # 对照 4：同上但**在**豁免登记里 ⇒ 绿，且必须印「用了 N 条豁免」
    d4 = make_repo("c4_exempt", TSX_FETCH_LITERAL, {"/data/tracked.json": '{"a":1}'},
                   [], ["frontend/public/data/"])
    r4 = judge(run_scanner(d4 / "frontend"), d4, {"/data/tracked.json": "HF 数据集 steer3d/latent"}, "对照4")
    ok4 = r4["green"] and r4["n_exempt_used"] == 1
    lines.append("对照4 被排除但在豁免登记里   : 判绿=%s 豁免计数=%d（期望 绿 / 1）%s"
                 % (_yn(r4["green"]), r4["n_exempt_used"], "✅" if ok4 else "✗")); ok &= ok4

    # 对照 5：fetch 参数还原不出 ⇒ 红（K3c）
    d5 = make_repo("c5_unresolvable", TSX_FETCH_UNRESOLVABLE, {}, [], [])
    r5 = judge(run_scanner(d5 / "frontend"), d5, {}, "对照5")
    ok5 = bool(r5["reds"]) and r5["n_unresolved_sites"] == 1
    lines.append("对照5 fetch 参数还原不出    : 判红=%s 未还原点=%d（期望 红 / 1）%s"
                 % (_yn(bool(r5["reds"])), r5["n_unresolved_sites"], "✅" if ok5 else "✗")); ok &= ok5

    # 对照 6：0 处 fetch ⇒ 红（K3d）
    d6 = make_repo("c6_no_fetch", TSX_NO_FETCH, {}, [], [])
    r6 = judge(run_scanner(d6 / "frontend"), d6, {}, "对照6")
    ok6 = bool(r6["reds"]) and r6["n_fetch_calls"] == 0
    lines.append("对照6 全站 0 处 fetch       : 判红=%s n_fetch_calls=%d（期望 红 / 0）%s"
                 % (_yn(bool(r6["reds"])), r6["n_fetch_calls"], "✅" if ok6 else "✗")); ok &= ok6

    return ok, lines


# ---------------------------------------------------------------- main

def main() -> int:
    print("=== 修订 83 K3：页面运行时取的数据文件必须在仓库里被 git 跟踪 ===\n")
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
    scan = run_scanner(FRONTEND)
    exempt = load_exempt(EXEMPT)
    res = judge(scan, ROOT, exempt, "真实扫描")

    print(f"fetch() 调用点                        : {res['n_fetch_calls']}")
    print(f"  形式（字面量/helper 形参/.url/模板串常量）: "
          f"{res['by_kind']['literal']} / {res['by_kind']['helper']} / "
          f"{res['by_kind']['url_prop']} / {res['by_kind']['template_const']}")
    print(f"⚠ 未还原的 fetch 点                   : {res['n_unresolved_sites']}")
    print(f"还原出的不同数据路径                  : {res['n_paths']}")
    print(f"✅ 已被 git 跟踪                      : {res['n_tracked']}")
    print(f"⚠ 豁免登记里用掉的（本次）             : {res['n_exempt_used']}")
    print(f"⚠ 存在但未跟踪                        : {len(res['untracked'])}")
    print(f"⚠ 被 .gitignore 排除且未登记           : {len(res['ignored'])}")
    print(f"⚠ 文件不存在                          : {len(res['missing'])}")
    if res["exempt_used"]:
        print("\n-- 用了豁免的路径 --")
        for u, ch, sites in res["exempt_used"]:
            print(f"   {u}  渠道：{ch}\n      ← {sites}")

    print()
    if res["reds"]:
        print("⚠⚠⚴ 判红：")
        for r in res["reds"]:
            print("  " + r)
        print()
        print("⚠⚠⚴ 本判据**如实判红**，因为它指出的不是渲染缺陷，而是**交付完整性缺陷**：")
        print("   页面在运行时依赖的文件不在仓库里 ⇒ 任何人 clone 下来，这块面板直接进")
        print("   `missing` 分支，整块内容消失，而且**没有任何其它判据会响**。")
        print("   ⚠ 是否把它入库是**用户拍板**的事（它是作者的未提交制品，由")
        print("     `backend/examples/measure_layers.py` 生成）—— 本判据不替人决定，")
        print("     也不自动 `git add`。")
        return 1
    print("✅ K3 判绿：全部运行时数据文件均已被 git 跟踪（或在豁免登记里）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
