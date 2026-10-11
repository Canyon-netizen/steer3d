#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 82 K1：**被序数指称的 Record 表，其渲染行序必须是主键升序**。

判据原文：预登记 §82.4（K1a/K1b/K1c）+ §82.5（对照）+ §82.8（判据更正）。

⚠⚠⚠ 三条实现纪律（承本项目的既有规矩，不是新发明）：
  1. **取数与对照在同一次调用里**：`main()` 先跑 4 条对照，不过就 `return`，
     数字根本不会被打印（§80.7 失误 3 / §81 落地失误 2 的教训）。
  2. **守卫用显式 `raise` / `sys.exit`，不用 `assert`**（`python -O` 会关掉 assert）。
  3. **崩溃必须与判红在输出上可区分**：崩 ⇒ 打印 `⚠⚠ 崩了`，rc=2；判红 ⇒ rc=1。

⚠⚠⚠ 两条「不许自己重写面板」的规矩：
  - 渲染行序**交给真 JS 引擎**（`node`）算 `Object.keys`，**不**在 Python 里
    复现 ECMA-262 的「canonical numeric 键提前并升序」规则 ——
    §78.4/§80 证明我对这条规则的直觉错过一次。
  - K1b **执行面板那行表达式本身**（`init_src` 原文），**不**复现 `findIndex`。
"""
from __future__ import annotations

import importlib.util
import json
from collections import defaultdict
import pathlib
import shutil
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DATA = ROOT / "frontend/public/latent/data"
COMPONENTS = ROOT / "frontend/components"
SCANNER = HERE / "ts_ordinal_refs.js"
CTL_ROOT = HERE.parent / "mutbak" / "k1ctl"

# ---------------------------------------------------------------- node 侧

def run_scanner(components_dir: pathlib.Path) -> dict:
    """跑 AST 仪器。⚠ 崩了就崩，不许静默返回空 —— 空是「测不到」与「不存在」唯一无法区分的值。"""
    p = subprocess.run(["node", str(SCANNER), str(components_dir)],
                       capture_output=True, text=True)
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


def js_object_keys(artifact: pathlib.Path, dotted: str) -> list[str]:
    """⚠ 用**真 JS 引擎**问「页面上会渲染成什么顺序」。
       ⚠ 不在 Python 里复现 ECMA-262 的 key 排序规则（§78.4/§80：我错过一次）。
       ⚠ 实测过这个差别是真的：`readability_static.per_id` 的 7 个键在 JSON 里
          不是升序（6771 排最后），而 V8 渲染出来是升序。"""
    code = (
        "const fs=require('fs');"
        f"const root=JSON.parse(fs.readFileSync({str(artifact)!r},'utf8'));"
        "const parts=" + json.dumps(dotted.split(".")) + ";"
        "let cur=root; for(const p of parts){ if(cur==null||!(p in cur)){"
        "console.log(JSON.stringify({missing:true})); process.exit(0);} cur=cur[p];}"
        "console.log(JSON.stringify({keys:Object.keys(cur)}));"
    )
    p = subprocess.run(["node", "-e", code], capture_output=True, text=True)
    if p.returncode != 0:
        print(f"⚠⚠⚠ node 求键序失败（rc={p.returncode}）⇒ **这是没测成**")
        print(p.stderr[:1500])
        raise SystemExit(2)
    return json.loads(p.stdout)



def js_table_key_orders(artifact: pathlib.Path, paths: list[str]) -> dict[str, list[str]]:
    """⚠⚠ 必须用**真引擎**拿有序键：`J1.collect()` 返回的是 **frozenset**，
       顺序在它那里就已经丢了 ⇒ `list(frozenset)` 的迭代顺序是任意的，
       拿它比「是否升序」是**无效比较**（我第一版就是这么写的）。"""
    if not paths:
        return {}
    code = (
        "const fs=require('fs');"
        f"const root=JSON.parse(fs.readFileSync({str(artifact)!r},'utf8'));"
        "const out={};"
        "for(const p of " + json.dumps(paths) + "){"
        "  let cur=root; for(const seg of p.split('.')){ if(cur==null||!(seg in cur)){cur=null;break;} cur=cur[seg]; }"
        "  out[p] = (cur && typeof cur==='object' && !Array.isArray(cur)) ? Object.keys(cur) : null;"
        "}"
        "console.log(JSON.stringify(out));"
    )
    pr = subprocess.run(["node", "-e", code], capture_output=True, text=True)
    if pr.returncode != 0:
        print(f"\u26a0\u26a0\u26a0 node 取表键序失败（rc={pr.returncode}）\u21d2 **这是没测成**")
        print(pr.stderr[:1500])
        raise SystemExit(2)
    return json.loads(pr.stdout)


def js_eval_panel_expr(artifact: pathlib.Path, prefix_path: str, alias: str,
                       via: str, init_src: str) -> dict:
    """⚠⚠ K1b：**执行面板那行表达式本身**（`init_src` 原文），不是 Python 复现。
       ⚠ 复现过一次就会踩 `"0.5"` vs `"0.50"` 的老坑（`SubspacePanel.tsx:134` 的注释）。"""
    code = (
        "const fs=require('fs');"
        f"const root=JSON.parse(fs.readFileSync({str(artifact)!r},'utf8'));"
        f"const {alias}=" + (f"root.{prefix_path}" if prefix_path else "root") + ";"
        f"const {via}={init_src};"
        f"console.log(JSON.stringify({{idx:{via}}}));"
    )
    p = subprocess.run(["node", "-e", code], capture_output=True, text=True)
    if p.returncode != 0:
        print(f"⚠⚠⚠ node 跑面板表达式失败（rc={p.returncode}）⇒ **这是没测成**")
        print(p.stderr[:1500])
        raise SystemExit(2)
    return json.loads(p.stdout)


# ------------------------------------------------- 借用 J1 的表枚举（不复算）

def _load_j1_collect():
    spec = importlib.util.spec_from_file_location("j1", HERE / "check_record_key_sets.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.collect


# ---------------------------------------------------------------- 判定

def collect_refs(scout: dict) -> list[dict]:
    out = []
    for f in scout["files"]:
        for r in f["refs"]:
            out.append({**r, "file": f["file"]})
    return out


def judge(scout: dict, label: str, data_dir: pathlib.Path) -> dict:
    """对一份扫描结果做 K1a/K1b/K1c 判定。真实扫描与 4 条对照**共用**这一个函数。"""
    refs = collect_refs(scout)
    subjects = [r for r in refs if r["kind"] == "record_table"]
    unresolved = [r for r in refs if r["kind"] == "unresolved"]
    n_tsx = len(scout["files"])
    n_obj = sum(f["n_object_calls"] for f in scout["files"])

    reds: list[str] = []
    details = []
    k1b_notes = []

    for r in subjects:
        art = data_dir / r["artifact"]
        got = js_object_keys(art, r["table_path"])
        if got.get("missing"):
            reds.append(f"⚠ 表路径在产物里不存在：{r['artifact']} :: {r['table_path']}")
            continue
        keys = got["keys"]
        asc = sorted(keys, key=float)
        ok = (keys == asc)
        # ⚠ 对称：同样报「JSON 里的序」和「渲染出来的序」，两者可能不同（§78.4）
        json_order = list(json.loads(art.read_text(encoding="utf-8")))
        json_order = None  # 顶层不是表，下面按 table_path 取
        raw = json.loads(art.read_text(encoding="utf-8"))
        cur = raw
        for part in r["table_path"].split("."):
            cur = cur[part]
        json_order = list(cur.keys())
        details.append({
            "site": f"{r['file']}:{r['line']}", "artifact": r["artifact"],
            "table_path": r["table_path"], "n_keys": len(keys),
            "json_order": json_order, "rendered_order": keys,
            "js_reordered": json_order != keys, "ascending_ok": ok,
        })
        if not ok:
            first = next((i for i, (a, b) in enumerate(zip(keys, asc)) if a != b), None)
            reds.append(
                f"⚠ 键序不是升序 @ {r['file']}:{r['line']}（{r['artifact']} :: {r['table_path']}）\n"
                f"    渲染序 : {keys}\n"
                f"    升序   : {asc}\n"
                + (f"    首个不同下标 {first}：{keys[first]!r} vs {asc[first]!r}"
                   f"（两侧 {keys[max(0,first-1):first+2]} / {asc[max(0,first-1):first+2]}）"
                   if first is not None else "    ⚠ 长度不同，无「首个不同下标」"))
            continue
        # K1b：跑面板那行表达式
        if r.get("init_src"):
            got2 = js_eval_panel_expr(art, r.get("prefix_path", ""), r["alias_name"],
                                      r["via"], r["init_src"])
            if "idx" not in got2:
                k1b_notes.append(f"⚠ K1b 表达式跑不出 {r['via']} ⇒ 判红")
                reds.append(f"⚠ K1b：{r['file']}:{r['line']} 的面板表达式跑不出 {r['via']}")
            else:
                one_based = got2["idx"] + 1
                same = (one_based == asc.index(keys[got2["idx"]]) + 1) if keys[got2["idx"]] == asc[got2["idx"]] else False
                same = one_based == (asc.index(keys[got2["idx"]]) + 1)
                k1b_notes.append(
                    f"    K1b 面板表达式 {r['via']} ⇒ 第 {one_based} 档"
                    f"（键 {keys[got2['idx']]}）；K1a 升序里同位置也是第 {asc.index(keys[got2['idx']]) + 1}"
                    f" ⇒ {'一致' if same else '⚠ 不一致（判红）'}")
                if not same:
                    reds.append(f"⚠ K1b 与 K1a 同源位置不一致 @ {r['file']}:{r['line']}")

    # ⚠ 「扫到但未判红」的乱序表：证明排除机制**看见了**它而不是漏了它
    seen_unflagged = []
    if subjects:
        collect = _load_j1_collect()
        for r in subjects:
            art = data_dir / r["artifact"]
            try:
                raw = json.loads(art.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"\u26a0\u26a0\u26a0 读 {r['artifact']} 失败：{e} \u21d2 **这是没读成**")
                raise SystemExit(2)
            tables: dict = defaultdict(list)
            try:
                collect(raw, "", tables)
            except Exception as e:                      # \u26a0 崩了要说，不静默
                print(f"\u26a0\u26a0\u26a0 J1.collect 在 {r['artifact']} 上崩了：{e!r} \u21d2 排除机制无法自证")
                raise SystemExit(2)
            # ⚠⚠⚴ `J1.collect()` 的键是**叶子名**，全路径在 `value[i][0]` 里。
            #   我第一版把叶子名当路径传给 node 去查全路径 ⇒ 全部查不到 ⇒
            #   「扫到但未判红」恒为 0 ⇒ **排除对照 2b 变成恒绿**。
            all_paths = [entry[0] for lst in tables.values() for entry in lst]
            refd = {r["table_path"]}
            cand = [pth for pth in all_paths if pth not in refd]
            orders = js_table_key_orders(art, cand)
            for pth, ks in orders.items():
                if not ks:
                    continue
                # \u26a0 \u5224\u636e\u53e3\u5f84\uff1a\u88ab K1 \u770b\u89c6\u7684\u662f**\u6e32\u67d3\u51fa\u6765\u7684\u5e8f**\uff0c\u6240\u4ee5\u7528 node \u7ed9\u7684\u6709\u5e8f\u952e
                if ks != sorted(ks, key=float):
                    seen_unflagged.append(pth)

    # K1c：空扫描不得判绿
    if len(subjects) == 0:
        reds.append(f"⚠ K1c：{label} 认到 **0** 张被序数指称的 Record 表 ⇒ 无法判定，判红")

    return {
        "label": label, "n_tsx": n_tsx, "n_object_calls": n_obj,
        "n_ordinal_refs": len(refs), "n_tables": len(subjects),
        "n_not_record_table": len(refs) - len(subjects) - len(unresolved),
        "n_unresolved": len(unresolved),
        "unresolved": [{"file": r["file"], "line": r["line"], "why": r.get("why")}
                       for r in unresolved],
        "details": details, "k1b": k1b_notes,
        "seen_unflagged_out_of_order": sorted(set(seen_unflagged)),
        "reds": reds, "green": not reds,
    }


# ---------------------------------------------------------------- 对照

# ⚠⚠ 模板**不用 str.format**：TSX 里的 `{…}`（JSX 表达式容器）与 format 的字段语法
#   直接冲突（第一次跑就崩在 `unexpected '{' in field name`）。
#   ⇒ 改用**唯一占位符 + str.replace**，模板里的花括号原样保留。
COMPONENT_TPL = """import { useEffect, useState } from "react";

type Row = { [k: string]: { n: number } };
type Payload = { headline: { __FIELD__: Row; separation_threshold: number } };

export default function C() {
  const [d, setD] = useState<Payload | null>(null);
  useEffect(() => {
    fetch("/latent/data/__ARTIFACT__")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then(setD)
      .catch(() => null);
  }, []);
  if (!d) return null;
  const h = d.headline;
  const opIdx = Object.keys(h.__FIELD__)
    .findIndex(k => Number(k) === Number(h.separation_threshold));
  return (
    <div>
__ORDINAL__
    </div>
  );
}
"""

# ⚠ 开启：序数指称，且 `第 … 档` 与量词之间有一个 JSX 空白间隔容器 `{" "}`
#   —— §82.8 更正 1 的要点，合成用例必须**带上这个形状**，否则对照测不到真正的机制。
ORDINAL_BLOCK_ON = """      <p>
        上面 {Object.keys(h.__FIELD__).length} 档门槛
        {" "}· 而且第 {opIdx >= 0 ? opIdx + 1 : "?"}{" "}
        档 是操作点
      </p>"""

# ⚠ 关闭：同样渲染这张表，但**没有**序数指称（只报个数）
ORDINAL_BLOCK_OFF = """      <p>
        上面 {Object.keys(h.__FIELD__).length} 档门槛 {" "}· 明细见下表
      </p>"""


def make_case(name: str, artifact_obj: dict, artifact_name: str,
              table_field: str, ordinal_on: bool) -> pathlib.Path:
    d = CTL_ROOT / name
    if d.exists():
        shutil.rmtree(d)
    (d / "components").mkdir(parents=True)
    src = (COMPONENT_TPL
           .replace("__ARTIFACT__", artifact_name)
           .replace("__FIELD__", table_field)
           .replace("__ORDINAL__", ORDINAL_BLOCK_ON if ordinal_on else ORDINAL_BLOCK_OFF))
    (d / "components" / "C.tsx").write_text(src, encoding="utf-8")
    (d / "data").mkdir(exist_ok=True)
    (d / "data" / artifact_name).write_text(
        json.dumps(artifact_obj, ensure_ascii=False, indent=1), encoding="utf-8")
    return d


def synth_table(order: list[str]) -> dict:
    return {k: {"n": 1} for k in order}


def synth_artifact(thresholds: dict, extra: dict | None = None) -> dict:
    headline = {
        "threshold_sensitivity": thresholds,
        "separation_threshold": 0.5,
    }
    if extra:
        headline.update(extra)
    return {"headline": headline}


def _yn(b: bool) -> str:
    """⚠ f-string 里不能写 `x and '是' else '否'`（同引号嵌套在 3.9 直接语法错）"""
    return "是" if b else "否"


def run_controls() -> tuple[bool, list[str]]:
    """⚠ 5 条对照，**各自独立目录**（共用目录会把它们的表混在一起，§81 的教训）。"""
    lines: list[str] = []
    ok = True
    ART = "synth.json"
    F = "threshold_sensitivity"

    # ---- 对照 1：乱序表 **被**序数指称 ⇒ 必须判红
    d1 = make_case("c1_ordinal_on_out_of_order",
                   synth_artifact(synth_table(["0.50", "0.35", "0.40"])), ART, F, True)
    r1 = judge(run_scanner(d1 / "components"), "对照1", d1 / "data")
    ok1 = bool(r1["reds"]) and r1["n_tables"] == 1
    lines.append("对照1 乱序表 + 被序数指称      : 判红=%s n_tables=%d（期望 红 / 1）%s"
                 % (_yn(bool(r1["reds"])), r1["n_tables"], "✅" if ok1 else "✗"))
    ok &= ok1

    # ---- 对照 2：**同一张乱序表不被序数指称** ⇒ 判红主体为 0 ⇒ K1c 判红
    #      （这一条是「排除机制下界」：证明乱序表本身不构成判红，判红来自 K1c）
    art2 = synth_artifact(synth_table(["0.35", "0.40", "0.45", "0.50"]),
                          extra={"other_table": synth_table(["0.50", "0.35", "0.40"])})
    d2 = make_case("c2_ordinal_off_excluded", art2, ART, F, False)
    r2 = judge(run_scanner(d2 / "components"), "对照2", d2 / "data")
    ok2 = bool(r2["reds"]) and r2["n_tables"] == 0
    lines.append("对照2 乱序表 + **不**被序数指称  : 判红=%s n_tables=%d（期望 红（K1c）/ 0）%s"
                 % (_yn(bool(r2["reds"])), r2["n_tables"], "✅" if ok2 else "✗"))
    ok &= ok2

    # ---- 对照 2b（**排除对照本体**）：升序表被指称 ⇒ 判绿，
    #      ⚠ 且必须报「扫到 1 张乱序但不被指称的表」——
    #      否则「没扫到」与「判绿」在输出上完全一样（§82.5 的配对要求）。
    d2b = make_case("c2b_exclusion_in_scope", art2, ART, F, True)
    r2b = judge(run_scanner(d2b / "components"), "对照2b", d2b / "data")
    n_excl = len(r2b["seen_unflagged_out_of_order"])
    ok2b = r2b["green"] and n_excl == 1
    lines.append("对照2b 升序被指称 + 乱序未被指称: 判绿=%s n_tables=%d 未判红的乱序表=%d 张"
                 "（期望 绿 / 1 / 1）%s"
                 % (_yn(r2b["green"]), r2b["n_tables"], n_excl, "✅" if ok2b else "✗"))
    ok &= ok2b

    # ---- 对照 3：升序表被序数指称 ⇒ 判绿
    d3 = make_case("c3_ordinal_on_ascending",
                   synth_artifact(synth_table(["0.35", "0.40", "0.45", "0.50"])), ART, F, True)
    r3 = judge(run_scanner(d3 / "components"), "对照3", d3 / "data")
    ok3 = r3["green"] and r3["n_tables"] == 1
    lines.append("对照3 升序表 + 被序数指称      : 判绿=%s n_tables=%d（期望 绿 / 1）%s"
                 % (_yn(r3["green"]), r3["n_tables"], "✅" if ok3 else "✗"))
    ok &= ok3

    # ---- 对照 4：全站 0 张被序数指称的 Record 表 ⇒ K1c 必须判红
    d4 = make_case("c4_no_record_table", synth_artifact(
        synth_table(["0.35", "0.40", "0.45", "0.50"])), ART, F, False)
    r4 = judge(run_scanner(d4 / "components"), "对照4", d4 / "data")
    ok4 = bool(r4["reds"]) and r4["n_tables"] == 0
    lines.append("对照4 无被序数指称的 Record 表 : 判红=%s n_tables=%d（期望 红 / 0）%s"
                 % (_yn(bool(r4["reds"])), r4["n_tables"], "✅" if ok4 else "✗"))
    ok &= ok4

    return ok, lines


# ---------------------------------------------------------------- main

def main() -> int:
    print("=== 修订 82 K1：被序数指称的 Record 表，渲染行序必须是主键升序 ===\n")

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
    scout = run_scanner(COMPONENTS)
    res = judge(scout, "真实扫描", DATA)

    print(f"扫的 tsx                          : {res['n_tsx']}")
    print(f"Object.keys/entries 调用点（AST，不含注释）: {res['n_object_calls']}")
    print(f"序数指称（去重后，可见文本流）     : {res['n_ordinal_refs']}")
    print(f"  其中 kind=not_record_table（合法排除）: {res['n_not_record_table']}")
    print(f"  其中 kind=unresolved（无法判定）    : {res['n_unresolved']}")
    print(f"⚠ K1 判红主体（被序数指称的 Record 表）: {res['n_tables']}")
    if res["unresolved"]:
        for u in res["unresolved"]:
            print(f"    ⚠ 无法判定 @ {u['file']}:{u['line']} —— {u['why']}")
    print()
    for d in res["details"]:
        print(f"  {d['site']}  {d['artifact']} :: {d['table_path']}")
        print(f"    键数           : {d['n_keys']}")
        print(f"    JSON 里的序    : {d['json_order']}")
        print(f"    ⚠ 渲染出来的序  : {d['rendered_order']}   （JS 是否重排：{d['js_reordered']}）")
        print(f"    是否升序       : {d['ascending_ok']}")
    for k in res["k1b"]:
        print(k)
    print()
    print(f"扫到但**未判红**的乱序表（证明排除机制看得见它们）："
          f"{len(res['seen_unflagged_out_of_order'])} 张")
    for p in res["seen_unflagged_out_of_order"][:10]:
        print(f"    · {p}")

    print()
    if res["reds"]:
        print("⚠⚠⚴ 判红：")
        for r in res["reds"]:
            print("  " + r)
        return 1
    print(f"✅ K1 判绿：{res['n_tables']} 张表渲染行序均为主键升序，K1b 与 K1a 同源一致。")
    print(f"   （判绿只说明**没抓到现行**；分母 {res['n_tables']} 张表，判据主体只覆盖到这一类。）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
