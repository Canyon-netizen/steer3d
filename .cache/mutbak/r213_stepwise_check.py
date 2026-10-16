#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 213 —— ⛔ 探针与流水线的逐步（增量解码）逐位对账。

## 这条在补什么缺口

修订 210/211/212 已经立住：`probe(--inject-scope all)` 与流水线的读数
**20/20 逐位一致**（10 格 × 2 剂量，剂量逐字相等）。

⛔⛔ **但那个「一致」只发生在第 0 步（prefill）。**
真实流水线 `backend/examples/run_paired_steering.py:141-163` 是

    out = model(**enc, use_cache=True)          # prefill
    record_logits(out)
    for step in range(1, budget + 1):
        out = model(input_ids=[[nxt]], past_key_values=past, use_cache=True)
        record_logits(out)                       # ← **每一步**都有一个读数
        nxt = int(torch.argmax(out.logits[0, -1, :]))

⇒ 流水线在 **每一步**都取一个 marker 读数，而探针此前**只量第 0 步**。
⚠⚠ 「两者等价」这句话覆盖不到那些步 ⇒ 若探针要当流水线的替身，
⚠⚠ 这就是最后一道结构缺口。

## 三条纪律（都是本项目已付过代价的）

1. ⚠⚠⛔ **对账只用落盘原始浮点**，绝不用日志里的 `%.6f` 转录值。
   修订 212 的教训：拿转录值比会把 bf16 台阶当成不一致。

2. ⚠⚠⛔ **判据是恰好 `== 0`**，不是「小于某容差」。
   容差会把「差 1e-7」与「差 0」当成同一件事，而后者才是我们要的断言。

3. ⚠⚠⛔ **分母必须逐步报，且提前 EOS 的格不许算「跑满」**。
   撞 EOS 时流水线 `break` ⇒ 那一格只跑了 `n_ran < budget` 步。
   ⚗ 若把「只跑了 2 步且这 2 步全绿」写成「8 步全绿」，通过率不变而
   ⚗ **证据量少了一截** —— 这是「恒绿不是绿」那个家族：
   ⚗ **分母变小而通过率不变**。

## 附带必须一起报的（否则结论会被过度解读）

- **fed 序列逐位相同**：贪心 argmax 决定 token 链。若两边的 fed 序列在
  第 j 步不同 ⇒ 第 j 步之后比的是**两条不同历史** ⇒ 必须报
  `first_divergence_step`，不能只报「N/N 一致」。
- **逐步的因子分解**：A→B（上下文）/ B→C（kernel）/ C→D（注入范围）
  在每一步上的 Δ。单步 Δ=0 **不蕴含**逐步 Δ=0（cache 是逐步累积的），
  所以这两件事必须分别验。

用法：
    python3 r213_stepwise_check.py --anchor /tmp/r213_anchors.json \
        --probe-dir /home/zhourui/steer3d_bpath/r213_raw --out /tmp/r213.json

退出码：0 全部逐位一致且无未测格 / 3 有不一致 / 4 缺锚点或探针数据
"""

import argparse
import json
import os
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# 纯函数（可在无 GPU 的合成数据上自检）
# ---------------------------------------------------------------------------


def cmp_series(pipe, probe):
    """逐位比两条读数序列。判据是**恰好 == 0**。

    ⚠⚠⛔ 返回 `n_cmp` 而不是 `min(len(pipe), len(probe))` 就完事 ——
    ⚠⚠⛔ 两边长度不同本身就是一条**要报出来的**事实（一边提前 EOS 或
    ⚠⚠⛔ 少采了几步），把长的截到短的会让「多出来的那几步」凭空消失。
    """
    pipe = list(pipe or [])
    probe = list(probe or [])
    n = min(len(pipe), len(probe))
    diffs = []
    first_bad = None
    for i in range(n):
        d = float(pipe[i]) - float(probe[i])
        diffs.append(abs(d))
        # ⚠⚠⛔ 「恰好为 0」：不是 abs(d) < tol。
        if d != 0.0 and first_bad is None:
            first_bad = i
    return {
        "n_cmp": n,
        "n_exact": sum(1 for d in diffs if d == 0.0),
        "first_bad_step": first_bad,
        "max_abs_diff": max(diffs) if diffs else None,
        "len_pipe": len(pipe),
        "len_probe": len(probe),
        "len_agree": len(pipe) == len(probe),
    }


def first_divergence(seqs):
    """多条 token 序列（fed）第一次不同的下标；全同则 None。**纯函数**。

    ⚠⚠⛔ 分组按「位置 j 处的 token 是否全同」，而不是按整条序列去重 ——
    ⚠⚠⛔ 整条去重只能告诉你「有几条不同链」，告诉不了「从第几步开始不同」。
    """
    seqs = [list(s or []) for s in seqs]
    if not seqs:
        return None, 0
    n = min(len(s) for s in seqs)
    for j in range(n):
        if len({s[j] for s in seqs}) > 1:
            return j, n
    return None, n


def summarize(rows, budget=None):
    """把逐行结果折成汇总。**纯函数**。

    ⚠⚠⛔ 三态分开：`matched`（量了且逐位一致）/ `mismatch`（量了且不一致）
    ⚠⚠⛔ / `not_measured`（没量到）。⛔⛔ **绝不许把没量到的算进 matched** ——
    ⚠⚠⛔ `None != True` 为真 ⇒ 「没量」会被读成「不一致」；反过来若把
    ⚠⚠⛔ 没量到的当通过，通过率就会凭空变好。
    """
    out = {
        "n_rows": len(rows),
        "n_matched": 0, "n_mismatch": 0, "n_not_measured": 0,
        "n_cmp": 0, "n_exact": 0, "n_len_disagree": 0,
        "worst": None, "worst_row": None,
        "rows_short_of_budget": [],
        "first_divergences": [],
    }
    for r in rows:
        if r.get("status") == "not_measured":
            out["n_not_measured"] += 1
            continue
        out["n_cmp"] += r["n_cmp"]
        out["n_exact"] += r["n_exact"]
        if r["first_bad_step"] is None and r["len_agree"]:
            out["n_matched"] += 1
        else:
            out["n_mismatch"] += 1
        if not r["len_agree"]:
            out["n_len_disagree"] += 1
        if r.get("max_abs_diff") is not None:
            if out["worst"] is None or r["max_abs_diff"] > out["worst"]:
                out["worst"] = r["max_abs_diff"]
                out["worst_row"] = r.get("label")
        if budget is not None and r.get("n_ran") is not None \
                and r["n_ran"] < budget:
            out["rows_short_of_budget"].append(
                {"label": r.get("label"), "n_ran": r["n_ran"],
                 "eos_step": r.get("eos_step")})
        if r.get("first_divergence_step") is not None:
            out["first_divergences"].append(
                {"label": r.get("label"),
                 "step": r["first_divergence_step"]})
    return out


# ---------------------------------------------------------------------------
# 装配（读落盘 JSON）
# ---------------------------------------------------------------------------


def load_probe_dir(probe_dir, tids=None):
    """把探针 `--dump-raw` 的目录读成 {(tid, pos_frac): payload}。"""
    out = {}
    for p in sorted(Path(probe_dir).glob("*.json")):
        try:
            j = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        if "tid" not in j or "pos_frac" not in j:
            continue
        if tids and j["tid"] not in tids:
            continue
        out[(j["tid"], float(j["pos_frac"]))] = j
    return out


def build_rows(anchor, probe_map, budget=None):
    """把锚点（流水线侧）与探针逐格配对。**纯函数**（只吃已解析的 dict）。"""
    rows = []
    for cell in anchor.get("cells", []):
        tid, pf = cell["tid"], float(cell["pos_frac"])
        pj = probe_map.get((tid, pf))
        # ⛔⛔ 探针侧没有逐步数据 ⇒ 这一格**整格**记 not_measured，
        # ⛔⛔ 绝不许因为「探针没跑」就跳过（那会让分母变小、通过率虚高）。
        for akey, ab in cell.get("by_alpha", {}).items():
            al = float(ab["alpha"])
            cfgD = None
            for c in ab.get("configs", []):
                if c["name"].startswith("D"):
                    cfgD = c
            label = "%s pos=%.2f α=%.12f" % (tid.replace("aime__aime25__", ""),
                                              pf, al)
            if pj is None or not pj.get("dec") or not pj.get("dec_alpha"):
                rows.append({"label": label, "status": "not_measured",
                             "reason": "探针侧没有逐步数据（dec/dec_alpha 缺）"})
                continue
            if cfgD is None or not cfgD.get("dec"):
                rows.append({"label": label, "status": "not_measured",
                             "reason": "锚点侧配置 D 没有 dec"})
                continue
            # ⚠⚠⛔ 剂量按**数值**配对，不按标签顺序配对。
            dl = pj["dec_alpha"]
            lab = None
            for k, v in dl.items():
                if float(v) == al:
                    lab = k
                    break
            if lab is None:
                rows.append({"label": label, "status": "not_measured",
                             "reason": "探针三条剂量里没有 α=%.12f（%s）"
                                       % (al, dl)})
                continue
            pdec = pj["dec"][lab]
            r = cmp_series(cfgD["dec"]["marks"], pdec.get("marks"))
            r["label"] = label
            r["status"] = "measured"
            r["alpha"] = al
            r["tid"] = tid
            r["pos_frac"] = pf
            r["dose_label"] = lab
            r["n_ran"] = pdec.get("n_ran")
            r["eos_step"] = pdec.get("eos_step")
            fd, nfd = first_divergence([pdec.get("fed") or [],
                                        cfgD["dec"].get("fed") or []])
            r["first_divergence_step"] = fd
            r["fed_len"] = nfd
            rows.append(r)
    return rows


def factor_rows(anchor):
    """逐步的因子分解：A→B / B→C / C→D 在**每一步**上的 Δ。**纯函数**。

    ⚠⚠⛔ 单步 Δ=0 **不蕴含**逐步 Δ=0 —— KV cache 是逐步累积的，
    ⚠⚠⛔ 所以这两件事必须分别报，不能拿修订 209 的单步结论顶替。
    """
    out = {"A->B": [], "B->C": [], "C->D": [], "A->D": []}
    for cell in anchor.get("cells", []):
        for ab in cell.get("by_alpha", {}).values():
            by = {c["name"][0]: c for c in ab.get("configs", [])
                  if c.get("dec")}
            for x, y in (("A", "B"), ("B", "C"), ("C", "D"), ("A", "D")):
                if x not in by or y not in by:
                    continue
                mx, mxk = by[x]["dec"]["marks"], by[y]["dec"]["marks"]
                n = min(len(mx), len(mxk))
                for i in range(n):
                    out["%s->%s" % (x, y)].append(
                        (cell["tid"], float(cell["pos_frac"]),
                         float(ab["alpha"]), i, mx[i] - mxk[i]))
    return out


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--anchor", required=True, help="r209 --decode-steps 的 --out")
    ap.add_argument("--probe-dir", required=True, help="探针 --dump-raw 的目录")
    ap.add_argument("--budget", type=int, default=None,
                    help="逐步预算步数；给了就把「实跑 < 预算」的格单列出来")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    if not os.path.exists(a.anchor):
        print("⛔ 缺锚点文件：%s" % a.anchor)
        return 4
    anchor = json.load(open(a.anchor, encoding="utf-8"))
    if not any(c.get("dec") for cl in anchor.get("cells", [])
               for al in cl.get("by_alpha", {}).values()
               for c in al.get("configs", [])):
        print("⛔⛔ 锚点里**一个 dec 都没有** ⇒ 产锚点时没传 --decode-steps。")
        print("   （不是「全部一致」，是**没量**。）")
        return 4
    probe_map = load_probe_dir(a.probe_dir)
    if not probe_map:
        print("⛔⛔ 探针目录 %s 下没有可用的 *.json" % a.probe_dir)
        return 4

    rows = build_rows(anchor, probe_map, budget=a.budget)
    s = summarize(rows, budget=a.budget)
    fac = factor_rows(anchor)

    print("=== 修订 213：逐步（增量解码）逐位对账 ===")
    print("  探针：%s（%d 格）" % (a.probe_dir, len(probe_map)))
    print("  「格×剂量」共 %d 行：量了 %d、未量 %d"
          % (s["n_rows"], s["n_rows"] - s["n_not_measured"],
             s["n_not_measured"]))
    if s["n_not_measured"]:
        print("  ⛔⛔ 未量 %d 行 —— **不进通过率分母**，也不能算通过："
              % s["n_not_measured"])
        for r in rows:
            if r.get("status") == "not_measured":
                print("      - %s：%s" % (r["label"], r.get("reason")))
    print()
    print("  逐位一致：%d/%d 个「格×剂量」" % (s["n_matched"],
                                              s["n_rows"] - s["n_not_measured"]))
    print("  比较点数：%d，逐位 ==0 的点数：%d" % (s["n_cmp"], s["n_exact"]))
    if s["n_len_disagree"]:
        print("  ⚠⚠⛔ %d 行的**序列长度不同** —— 有一边提前 EOS 或少采了几步。"
              % s["n_len_disagree"])
    print("  最大 |Δ|：%s" % ("%.6e" % s["worst"] if s["worst"] is not None
                            else "N/A"))
    if s["first_divergences"]:
        print("  ⛔⛔ fed（token 链）分叉：%s"
              % [(d["label"], d["step"]) for d in s["first_divergences"][:5]])
    else:
        print("  fed（token 链）逐位相同：无分叉")
    if a.budget is not None:
        sh = s["rows_short_of_budget"]
        print()
        print("  ⚠⚠⛔ 预算 %d 步，实跑不足的「格×剂量」：%d"
              % (a.budget, len(sh)))
        for d in sh[:12]:
            print("      - %s  实跑=%d  EOS步=%s"
                  % (d["label"], d["n_ran"], d["eos_step"]))
        if sh:
            print("  ⛔⛔ 那些**不是跑满了**，是提前 EOS ⇒ 证据量比预算少。")

    print()
    print("=== 逐步的因子分解（每一步的 Δ）===")
    for k in ("A->B", "B->C", "C->D", "A->D"):
        v = fac[k]
        if not v:
            print("  %-6s 无数据" % k)
            continue
        nz = [x for x in v if x[4] != 0.0]
        mx = max(abs(x[4]) for x in v)
        print("  %-6s n=%-5d 恰好为 0：%-5d 非 0：%-5d  max|Δ|=%.6e"
              % (k, len(v), len(v) - len(nz), len(nz), mx))

    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump({"summary": s, "rows": rows,
                       "factor": {k: [list(x) for x in v]
                                  for k, v in fac.items()}},
                      fh, ensure_ascii=False, indent=1)
        print()
        print("已写 %s" % a.out)

    # ⛔⛔ 退出码必须**脱离管道**量：printf | grep 会把 grep 的码当成脚本的码。
    if s["n_not_measured"]:
        print("⛔⛔ 结论：**有未量到的格** ⇒ 不能宣布「全部一致」。")
        return 4
    if s["n_mismatch"]:
        print("⛔ 有 %d 个「格×剂量」不一致。" % s["n_mismatch"])
        return 3
    print("✅ 全部「格×剂量」逐位一致（判据：恰好 == 0）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
