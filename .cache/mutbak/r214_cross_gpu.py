#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 214 —— ⛔ 跨设备复验：同一批读数在**另一张卡**上是否仍逐位相同。

## 这条在补什么缺口

修订 210–213 立住的是「`probe(all)` 与流水线逐位一致」。
⚠⚠⛔ 但探针与锚点**始终跑在同一块卡上**（修订 213 = `GPU-fae7a2e0-…`）。
⚠⚠⛔ 「逐位一致」在数学上依赖两边的浮点求和顺序**完全一致**，
⚠⚠⛔ 而 GPU 的 kernel 选择、SM 数、split-k 策略都可能随**设备**变化。
⚗⇒ 若换一个物理设备读数就变了，那 180/180 那个数只在那块卡上成立。

## 一次只改一个变量

本轮把**设备**作为唯一变量，其余逐字照抄修订 213：

| | 修订 213 | 本轮 |
|---|---|---|
| 模型 | Qwen3-1.7B（同一路径） | 同 |
| 层 / marker 集合 / `w` | 20 / 7 个 / `/tmp/w_p2a.npy` | 同 |
| 剂量 | `56.73720169067383` / `113.47440338134766` | 同（逐字） |
| 格 | 10 格（5 轨迹 × pos 0.3/0.7） | 同 |
| 逐步预算 | 8 步 | 同 |
| **设备** | `GPU-fae7a2e0-…`（RTX PRO 5000 72GB Blackwell） | **`GPU-2828f5ba-…`（同型号）** |

⚠⚠⛔ **两张卡必须同型号**。`nvidia-smi` 显示 GPU 0/1/3 是 RTX PRO 5000、
⚠⚠⛔ GPU 2/6 是 RTX 6000D、GPU 4/5/7 是 RTX 6000 —— 换到不同型号就不是
⚠⚠⛔ 「换设备」而是「换架构」，两个变量混在一起，出问题也归因不了。

## 两件事，分别报

1. **跨设备**：GPU-0 的读数与 GPU-1 的读数是否逐位相同（**本条的主张**）。
2. **卡内等价**：GPU-1 上 `probe(all)` 与流水线是否仍然逐位一致
   （⇒ 修订 213 的结论不是那一张卡的偶然）。这一条由 `r213_stepwise_check.py`
   在 GPU-1 的数据上重跑得到，本脚本不重复做。

## 三条纪律

1. ⚠⚠⛔ 对账**只用落盘原始浮点**，绝不用日志里的 `%.6f` 转录值。
2. ⚠⚠⛔ 判据是**恰好 `== 0`**，不是「小于某容差」。
3. ⚠⚠⛔ **配对键必须含设备无关的成分**（tid / pos_frac / alpha / 配置名）。
   ⛔ 若只按文件顺序配对，两边行数或顺序一变就会**静默配错**，
   ⛔ 而配错之后两边都「自洽」，看不出来。

用法：
    python3 r214_cross_gpu.py --a-anchor <gpu0.json> --b-anchor <gpu1.json> --a-probe <gpu0dir> --b-probe <gpu1dir>

退出码：0 全部逐位一致且无未配对 / 3 有不一致 / 4 缺文件
"""

import argparse
import json
import os
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# 纯函数
# ---------------------------------------------------------------------------


def cmp_values(a, b):
    """逐位比两个**标量或序列**。判据是恰好 == 0。

    ⚠⚠⛔ 长度不同**本身就是一条要报出来的事实** —— 把长的截到短的会让
    ⚠⚠⛔ 多出来的那几项凭空消失，那正是「恒绿」的一种形态。
    """
    if isinstance(a, list) or isinstance(b, list):
        a = list(a or [])
        b = list(b or [])
        n = min(len(a), len(b))
        diffs = [abs(float(a[i]) - float(b[i])) for i in range(n)]
        nz = sum(1 for i in range(n) if float(a[i]) - float(b[i]) != 0.0)
        return {"n": n, "n_exact": n - nz, "len_a": len(a), "len_b": len(b),
                "len_agree": len(a) == len(b),
                "max_abs_diff": max(diffs) if diffs else None}
    d = float(a) - float(b)
    return {"n": 1, "n_exact": 1 if d == 0.0 else 0,
            "len_a": 1, "len_b": 1, "len_agree": True,
            "max_abs_diff": abs(d)}


def flatten_anchor(anchor):
    """把锚点摊成 {配对键: {"mark":…, "dec": [...]}}。**纯函数**。

    ⚠⚠⛔ 配对键必须由**内容**组成（tid + pos_frac + alpha + 配置名），
    ⚠⚠⛔ 绝不能用下标/序号 —— 两份文件只要有一格缺失，后面全部错位，
    ⚠⚠⛔ 而每一步都「看起来正常」。

    ⚠⚠⛔ `dec` 的形状必须与 `flatten_probe` **一致**：都是
    ⚠⚠⛔ `{剂量标签: [逐步读数…]}` 的字典。
    ⚠⚠⛔ 第一版这里存的是**裸 list**，而 `compare_maps` 按字典读
    ⚠⚠⛔ ⇒ `sorted(set(裸list))` 给出的是浮点数，`da[浮点数]` 直接
    ⚠⚠⛔ `TypeError: list indices must be integers or slices, not float`。
    ⚗⇒ 对账函数的**输入形状**也要写进自检，不能只测数值。
    """
    out = {}
    for cell in anchor.get("cells", []):
        for ab in cell.get("by_alpha", {}).values():
            al = "%.12f" % float(ab["alpha"])
            for c in ab.get("configs", []):
                nm = c["name"].split()[0]          # 'A'/'B'/'C'/'D'
                key = "%s|%.2f|%s|%s" % (cell["tid"], float(cell["pos_frac"]),
                                         al, nm)
                out[key] = {"mark": c.get("mark"),
                            "dec": {al: (c.get("dec") or {}).get("marks")},
                            "top1_stable": c.get("top1_stable")}
    return out


def flatten_probe(probe_dir):
    """把探针 --dump-raw 目录摊成 {配对键: {"dec": {剂量: [...]}}}。**纯函数**。"""
    out = {}
    for p in sorted(Path(probe_dir).glob("*.json")):
        try:
            j = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        if "tid" not in j or "pos_frac" not in j or not j.get("dec"):
            continue
        dec = {}
        for lab, v in j["dec"].items():
            dec[lab] = (v or {}).get("marks")
        out["%s|%.2f" % (j["tid"], float(j["pos_frac"]))] = {"dec": dec}
    return out


def compare_maps(ma, mb, with_dec=True):
    """比两个已摊平的 map。**纯函数**。三态分开，不许把未配对算成通过。"""
    rows = []
    for k in sorted(set(ma) | set(mb)):
        if k not in ma:
            rows.append({"key": k, "status": "not_measured",
                         "reason": "只在 B 侧有"})
        elif k not in mb:
            rows.append({"key": k, "status": "not_measured",
                         "reason": "只在 A 侧有"})
        else:
            va, vb = ma[k], mb[k]
            r = {"key": k, "status": "measured"}
            if "mark" in va and "mark" in vb:
                r["mark"] = cmp_values(va["mark"], vb["mark"])
            if with_dec and va.get("dec") and vb.get("dec"):
                da, db = va["dec"], vb["dec"]
                r["dec"] = {}
                for lab in sorted(set(da) | set(db)):
                    if lab in da and lab in db:
                        r["dec"][lab] = cmp_values(da[lab], db[lab])
                    else:
                        r["dec"][lab] = {"status": "not_measured",
                                         "reason": "剂量 %s 只在一侧" % lab}
            rows.append(r)
    return rows


def summarize(rows):
    """折汇总。**纯函数**。

    ⚠⚠⛔ `not_measured` 既不进 n_exact 的分母，**也不**当成通过。
    ⚠⚠⛔ 分母为 0 时不许报「一致」—— 那是「没量到」，不是「量到且相同」。
    """
    out = {"n_rows": len(rows), "n_measured": 0, "n_not_measured": 0,
           "n_cmp": 0, "n_exact": 0, "n_len_disagree": 0,
           "worst": None, "worst_key": None, "unmatched": []}
    for r in rows:
        if r.get("status") == "not_measured":
            out["n_not_measured"] += 1
            out["unmatched"].append((r["key"], r.get("reason")))
            continue
        out["n_measured"] += 1
        for part in [r.get("mark")] + list((r.get("dec") or {}).values()):
            if not isinstance(part, dict) or part.get("status"):
                continue
            out["n_cmp"] += part["n"]
            out["n_exact"] += part["n_exact"]
            if not part["len_agree"]:
                out["n_len_disagree"] += 1
            md = part.get("max_abs_diff")
            if md is not None and (out["worst"] is None or md > out["worst"]):
                out["worst"] = md
                out["worst_key"] = r["key"]
    return out


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--a-anchor", required=True, help="设备 A 的锚点 JSON")
    ap.add_argument("--b-anchor", required=True, help="设备 B 的锚点 JSON")
    ap.add_argument("--a-probe", required=True, help="设备 A 的探针 dump-raw 目录")
    ap.add_argument("--b-probe", required=True, help="设备 B 的探针 dump-raw 目录")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    for p in (a.a_anchor, a.b_anchor, a.a_probe, a.b_probe):
        if not os.path.exists(p):
            print("⛔ 缺输入：%s" % p)
            return 4

    # ⛔⛔⛔ **拒绝自我比较。**
    # ⚠⚠⛔ 我第一次跑本脚本时，探针那一侧还没跑出来，于是顺手把同一个
    # ⚠⚠⛔ dump-raw 目录当 A 和 B 都传了进去 ⇒ 脚本照常印
    # ⚠⚠⛔ 「✅ 跨设备逐位相同（270/270）」。
    # ⚠⚠⛔ 那是把一个东西和它自己比，**恒真**，证明不了任何事，
    # ⚠⚠⛔ 而且外观与真的跨设备结果**一模一样**。
    # ⛔⇒ 同一个路径当两侧必须直接拒绝，而不是照常跑。
    same_a = os.path.realpath(a.a_anchor) == os.path.realpath(a.b_anchor)
    same_p = os.path.realpath(a.a_probe) == os.path.realpath(a.b_probe)
    if same_a or same_p:
        print("⛔⛔⛔ 拒绝运行：%s 两侧是**同一个路径**。"
              % ("锚点" if same_a else "探针"))
        print("   把一个东西和它自己比是恒真的，**证明不了跨设备**；")
        print("   而它的外观与真结果一模一样 ⇒ 这正是「恒绿不是绿」那一族。")
        print("   A=%s" % (a.a_anchor if same_a else a.a_probe))
        print("   B=%s" % (a.b_anchor if same_a else a.b_probe))
        return 4

    ja = json.load(open(a.a_anchor, encoding="utf-8"))
    jb = json.load(open(a.b_anchor, encoding="utf-8"))
    pa = flatten_probe(a.a_probe)
    pb = flatten_probe(a.b_probe)
    if not pa or not pb:
        print("⛔⛔ 探针目录为空或没有 dec：%s(%d) / %s(%d)"
              % (a.a_probe, len(pa), a.b_probe, len(pb)))
        return 4

    rc_anchor = 4          # ⛔ 先给默认值：任何分支漏赋值都不至于 NameError
    print("=== 修订 214：跨设备逐位复验 ===")
    print("  A 锚点 %s（%d 格）" % (a.a_anchor, len(ja.get("cells", []))))
    print("  B 锚点 %s（%d 格）" % (a.b_anchor, len(jb.get("cells", []))))
    print("  ⚠⚠⛔ 只对**同一型号**的两张卡才有意义；换型号就是两个变量。")

    rows_anchor = compare_maps(flatten_anchor(ja), flatten_anchor(jb))
    rows_probe = compare_maps(pa, pb)

    for name, rows in (("锚点（mark + 逐步 marks）", rows_anchor),
                       ("探针（逐步 marks）", rows_probe)):
        s = summarize(rows)
        print()
        print("--- %s ---" % name)
        print("  配对键 %d 个：已配对 %d，未配对 %d"
              % (s["n_rows"], s["n_measured"], s["n_not_measured"]))
        if s["unmatched"]:
            for k, why in s["unmatched"][:10]:
                print("    ⛔ 未配对 %s：%s" % (k, why))
        print("  比较点数 %d，逐位 ==0：%d" % (s["n_cmp"], s["n_exact"]))
        if s["n_len_disagree"]:
            print("  ⚠⚠⛔ %d 项**序列长度不同**（一边撞 EOS 或少采了几步）"
                  % s["n_len_disagree"])
        print("  最大 |Δ|：%s"
              % ("%.6e @ %s" % (s["worst"], s["worst_key"])
                 if s["worst"] is not None else "N/A"))
        if s["n_cmp"] == 0:
            # ⚠⚠⛔ 这一分支是本条最重要的一次自检：
            # ⚠⚠⛔ 分母为 0 却印「一致」，就是把「没量」当「量到且相同」。
            print("  ⛔⛔ 比较点数 **0** ⇒ **不是一致，是没量到**。")
            if name.startswith("锚点"):
                rc_anchor = 4
        else:
            ok = (s["n_exact"] == s["n_cmp"] and s["n_not_measured"] == 0
                  and s["n_len_disagree"] == 0)
            print("  %s" % ("✅ 跨设备逐位相同。" if ok else "⛔ 有不一致。"))
            if name.startswith("锚点"):
                rc_anchor = 0 if ok else 3

    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump({"anchor_rows": rows_anchor, "probe_rows": rows_probe,
                       "anchor_summary": summarize(rows_anchor),
                       "probe_summary": summarize(rows_probe)},
                      fh, ensure_ascii=False, indent=1)
        print()
        print("已写 %s" % a.out)

    # ⛔⛔ 退出码必须**脱离管道**量（printf | grep 会把 grep 的码当成脚本的码）
    return rc_anchor


if __name__ == "__main__":
    sys.exit(main())
