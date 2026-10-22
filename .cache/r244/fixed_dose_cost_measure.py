#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fixed_dose_cost_measure.py —— 量出「扩池 vs 先量后算」两条路线要花的**墙钟与字节**（零 GPU）。

⚖⚖⚖ **口径**（全部从**既有产物**里量，⛔ 不跑任何模型、⛔ 不写任何数据文件）：
  ① **探针单格墙钟** ⇒ 从 `r244_warm.log` / `r244_warm_rand.log` 的
     `### BEGIN [i/N] … HH:MM:SS` 与 `### END   [i/N] … rc=0  HH:MM:SS` 逐格配对
  ② **生成单条墙钟** ⇒ 从 `gen_b2_max32768/aime/*.npz` 的**完成时刻**（mtime）
     ＋ 生成日志的**逐条顺序** ⇒ 相邻完成时刻之差 = 那一段的生成耗时
  ③ **每条字节数** ⇒ npz 实际大小
  ④ **每条 token 数** ⇒ 生成日志里的 `tok` 列

⚖⚠⚖ **诚实声明**（⛔ 不许把估计说成实测）：
  · ② 的**第一条**轨迹没有起点戳（生成日志没打 `[start]`）⇒ 只给**下界**
  · ② 的间隔法把「相邻完成时刻之差」归给**后一条** ⇒ 那是**那一段的耗时**，
    不是「这一条的耗时」⇒ 本快照把它叫 `per_interval_s`（⛔ 不叫 per_tid）
  · ① 若某格 END < BEGIN ⇒ 跨零点 ⇒ +24h（代码里显式处理）

⚖ **产物**：`fixed_dose_cost_baseline.json`（带每个源的 md5 ⇒ 可复算）

⚖⚖⚖ **为什么它要入库**：这个快照是**成本基线**的**唯一出处** ⇒
  ⇒ 不入库 ⇒ 下一个接手的人**没法复算**那些墙钟 ⇒ ⇒ 那些数就变成了「信我」。

⚖ 用法：`STEER_BPATH=<共享目录> fixed_dose_cost_measure.py <输出 json>`
"""

import hashlib
import json
import os
import re
import sys
from datetime import datetime

# ⚖ 路径**可配**（⛔ 不写死服务器路径 ⇒ 快照在**任何**机器上都能复算）
B = os.environ.get("STEER_BPATH", "/home/zhourui/steer3d_bpath")
GEN_DIR = os.path.join(B, "gen_b2_max32768", "aime")
GEN_LOG = os.path.join(B, "gen_b2_max32768_zju53_cuda3.log")
W_LOG = os.path.join(B, "r244_warm.log")
R_LOG = os.path.join(B, "r244_warm_rand.log")
CELLS = os.path.join(B, "warm_cells.txt")

OUT = sys.argv[1] if len(sys.argv) > 1 else "fixed_dose_cost_baseline.json"


def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def stats(xs):
    xs = sorted(xs)
    n = len(xs)
    if n == 0:
        return {"n": 0}
    med = xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0
    return {"n": n, "min": xs[0], "median": med, "max": xs[-1],
            "mean": sum(xs) / float(n), "total": sum(xs)}


def parse_hms(s):
    return datetime.strptime(s, "%H:%M:%S")


def cell_times(log_path):
    """⚖ 逐格配对 BEGIN/END ⇒ 每格墙钟（秒）。

    ⚖⚠⚖⚖ **两臂的 BEGIN 行格式不一样**（实测）：
        w 臂（旧版脚本）：`### BEGIN [1/137] <tid> --inject-scope k --inject-n-sites 1  HH:MM:SS`
        rand 臂（新版脚本）：`### BEGIN <tid> [1/137] n_eff=1762 --inject-scope k …  HH:MM:SS`
      ⇒ ⇒ 解析器**两种都要认**（⛔ 只认一种 ⇒ 另一臂整批读不出来 ⇒ 看上去像「没数据」）
    """
    beg_old = re.compile(r"^### BEGIN\s+\[(\d+)/(\d+)\]\s+(\S+)(.*?)\s+(\d{2}:\d{2}:\d{2})\s*$")
    beg_new = re.compile(r"^### BEGIN\s+(\S+)\s+\[(\d+)/(\d+)\]\s+n_eff=\S+(.*?)\s+(\d{2}:\d{2}:\d{2})\s*$")
    end = re.compile(r"^### END\s+\[(\d+)/(\d+)\]\s+(\S+)\s+rc=(\d+)\s+(\d{2}:\d{2}:\d{2})\s*$")
    starts, ends = {}, []
    nline = 0
    fmt = {"old": 0, "new": 0}
    with open(log_path, encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            nline += 1
            m = beg_new.match(ln)
            if m:
                fmt["new"] += 1
                starts[int(m.group(2))] = (m.group(1), parse_hms(m.group(5)))
                continue
            m = beg_old.match(ln)
            if m:
                fmt["old"] += 1
                starts[int(m.group(1))] = (m.group(3), parse_hms(m.group(5)))
                continue
            m = end.match(ln)
            if m:
                ends.append((int(m.group(1)), m.group(3), int(m.group(4)),
                             parse_hms(m.group(5))))
    per = []
    per_arm = {"think": [], "no_think": []}
    bad = []
    for idx, tid, rc, t_end in ends:
        if idx not in starts:
            bad.append(idx)
            continue
        s_tid, t_beg = starts[idx]
        if s_tid != tid:
            bad.append(idx)
            continue
        d = (t_end - t_beg).total_seconds()
        if d < 0:
            d += 24 * 3600.0          # ⚖ 跨零点
        per.append(d)
        arm = "think" if tid.endswith("__think") else (
            "no_think" if tid.endswith("__no_think") else "other")
        per_arm.setdefault(arm, []).append(d)
    return per, bad, len(starts), len(ends), nline, fmt, per_arm


def gen_rows():
    """⚖ 生成日志 ⇒ 逐条 (序, tid, tok, ok)。"""
    pat = re.compile(r"^\[(\d+)/(\d+)\]\s+(think|no_think)\s+(p\d+)\s+…\s+([✓✗])\s+(\d+)\s+tok")
    rows = []
    with open(GEN_LOG, encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            m = pat.match(ln.strip())
            if m:
                rows.append({"order": len(rows), "arm": m.group(3), "p": m.group(4),
                             "ok": m.group(5), "tok": int(m.group(6)),
                             "tid": "aime__aime25__%s__%s" % (m.group(4), m.group(3))})
    return rows


def main():
    res = {"_note": "⚖ 244.71 的**成本基线快照**（零 GPU：从既有日志与文件 mtime 量出来的墙钟/字节）"
                    "⇒ ⛔ 里面的数是**实测**（不是估计）⇒ 但 §② 的口径有**下界**与**间隔法**两条限制"
                    "（见 `gen_track.caveats`）⇒ ⇒ **不许**把它当「精确的单条耗时」用",
           "measured_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

    # ---- ① 探针单格墙钟
    probe = {}
    for tag, path in (("w", W_LOG), ("rand", R_LOG)):
        per, bad, ns, ne, nline, fmt, per_arm = cell_times(path)
        if not per:
            raise SystemExit("%s 里没读到任何配对的格" % path)
        probe[tag] = {"per_cell_s": stats(per),
                      "per_cell_s_by_arm": dict((k, stats(v)) for k, v in per_arm.items()),
                      "n_begin": ns, "n_end": ne,
                      "begin_fmt_counts": fmt,
                      "unpaired_cells": bad,
                      "log_lines": nline,
                      "log_md5": md5(path),
                      "log_bytes": os.path.getsize(path)}
    res["probe_cell"] = probe
    res["probe_cell"]["per_cell_s_both_arms"] = stats(
        [probe["w"]["per_cell_s"]["median"]] + [probe["rand"]["per_cell_s"]["median"]])
    res["probe_cell"]["caveats"] = [
        "⚖ 每格是**独立子进程**（跑批脚本逐格起一个 r241_probe.py）⇒ 这个墙钟**含**每格的"
        "模型加载 ⇒ 它就是「一个格」的真实成本",
        "⚖ 这是**w 臂与 rand 臂**两批独立跑出来的 ⇒ 两个样本 ⇒ 可看离散度",
        "⚖⚠⚖ **两臂的 BEGIN 行格式不一样**（w 臂 = 旧版脚本，rand 臂 = 新版脚本，"
        "新版多带 `n_eff=`）⇒ ⇒ 「两臂之间**只差 --arm**」这句在**日志格式**上**并不成立**"
        "⇒ ⇒ ⚠ 这是**日志格式**的差异（`n_eff=` 只是多一个注释）⇒ ⛔ 但它说明"
        "**两臂不是同一次脚本版本跑的** ⇒ 以后要把这条当成**要核的项**，⛔ 不要默认成立",
    ]

    # ---- ② 生成：逐条顺序 + 完成时刻
    rows = gen_rows()
    if not rows:
        raise SystemExit("生成日志里没读到任何行")
    tids = sorted(os.listdir(GEN_DIR))
    npz = {t: os.path.join(GEN_DIR, t) for t in tids if t.endswith(".npz")}
    mtimes = {t: os.path.getmtime(p) for t, p in npz.items()}
    seq = []
    for r in rows:
        f = r["tid"] + ".npz"
        if f not in mtimes:
            raise SystemExit("生成日志里的 %s 在目录里没有 npz" % r["tid"])
        seq.append((r, mtimes[f], os.path.getsize(npz[f])))
    seq.sort(key=lambda x: x[1])          # ⚖ 按完成时刻排序
    intervals = []
    intervals_by_arm = {"think": [], "no_think": []}
    for i in range(1, len(seq)):
        d = seq[i][1] - seq[i - 1][1]
        intervals.append(d)
        intervals_by_arm.setdefault(seq[i][0]["arm"], []).append(d)
    # ⚖⚠⚖ **首条的下界**：目录 mtime **不是**起点（加文件会更新它 ⇒ 它比首条完成还晚）
    #   ⇒ ⛔ 不能拿它当起点 ⇒ 这里**只记**首条完成时刻与末条完成时刻，起点**未知**
    first_gap = None
    end_ts = None
    with open(GEN_LOG, encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            m = re.search(r"\[end\]\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", ln)
            if m:
                end_ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").timestamp()
    res["gen_track"] = {
        "n_tid": len(seq),
        "n_npz": len(npz),
        "n_json": len([t for t in tids if t.endswith(".json")]),
        "wall_total_s": (end_ts - seq[0][1]) if end_ts else None,
        "wall_total_is_lower_bound": True,
        "first_gap_unknown": first_gap,
        "per_interval_s": stats(intervals),
        "per_interval_s_by_arm": dict((k, stats(v)) for k, v in intervals_by_arm.items()),
        "n_pairs": len(seq) // 2,
        "bytes_per_pair_mean": (sum(x[2] for x in seq) / float(len(seq) // 2)),
        "bytes_total": sum(x[2] for x in seq),
        "per_tid_bytes": stats([x[2] for x in seq]),
        "per_tid_bytes_by_arm": {
            "think": stats([x[2] for x in seq if x[0]["arm"] == "think"]),
            "no_think": stats([x[2] for x in seq if x[0]["arm"] == "no_think"]),
        },
        "tokens_by_arm": {
            "think": stats([x[0]["tok"] for x in seq if x[0]["arm"] == "think"]),
            "no_think": stats([x[0]["tok"] for x in seq if x[0]["arm"] == "no_think"]),
        },
        "caveats": [
            "⚖⚖ **间隔法**：`per_interval_s` 是「**相邻两条的完成时刻之差**」⇒ 那一段的耗时"
            "**归给后一条** ⇒ ⛔ **不是**「这一条的耗时」⇒ 只可当**同分布的抽样**用",
            "⚖⚖ **第一条**没有起点戳（生成日志没打 `[start]`）⇒ `first_to_first_gap_s` 只是**下界**",
            "⚖ 生成是**串行**的（一条一条写）⇒ 间隔法成立；⛔ 若将来并行生成，这套口径就**失效**",
            "⚖⚠⚖⚖ **区间法的归因**：生成顺序是 think, no_think, think, no_think, … ⇒ "
            "「到 think 的间隔」= **think 那一条**的生成耗时，「到 no_think 的间隔」= **no_think 的**"
            "⇒ ⇒ `per_interval_s_by_arm` 才是**按臂**的可用量",
            "⚖⚠⚖⚖ **目录 mtime 不是起点**（加文件会更新它）⇒ ⛔ 不能拿它当「首条的起点」⇒ "
            "本快照**不给**首条耗时 ⇒ `wall_total_s` 是**下界**",
        ],
        "dir_mtime_s": os.path.getmtime(GEN_DIR),
        "first_completion_s": seq[0][1],
        "last_completion_s": seq[-1][1],
    }

    # ---- ③ 格清单格式（244.71 要加 pos_frac ⇒ 先把**现状**记下来）
    with open(CELLS, encoding="utf-8") as fh:
        clines = [ln.rstrip("\n") for ln in fh if ln.strip()]
    cols = set()
    for ln in clines:
        cols.add(len(ln.split("\t")))
    res["cell_list"] = {
        "path": CELLS, "md5": md5(CELLS), "n_cells": len(clines),
        "n_columns": sorted(cols),
        "columns": "tid \\t scope(k) \\t n_sites",
        "has_pos_frac_column": False,
        "note": "⚖⚠⚖ **现状是 3 列，没有 pos_frac** ⇒ 244.70 说的「格清单要加一维」是**真的**"
                "⇒ 而 244.70 也查清了：固定剂量下 **n_sites 与 scope 都被钉死** ⇒ 只剩 pos_frac"
                "⇒ ⇒ **要跑固定剂量，这一列必须加**（⇒ 生成侧改动 ⇒ 要用户点头）",
    }

    # ---- ④ 源 md5
    res["sources"] = {
        "gen_log": {"path": GEN_LOG, "md5": md5(GEN_LOG), "bytes": os.path.getsize(GEN_LOG)},
        "gen_dir": {"path": GEN_DIR, "n_npz": len(npz),
                    "bytes": sum(os.path.getsize(p) for p in npz.values())},
        "warm_w_log": {"path": W_LOG, "md5": md5(W_LOG), "bytes": os.path.getsize(W_LOG)},
        "warm_rand_log": {"path": R_LOG, "md5": md5(R_LOG), "bytes": os.path.getsize(R_LOG)},
        "cell_list": {"path": CELLS, "md5": md5(CELLS), "bytes": os.path.getsize(CELLS)},
    }

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    print("已写出 %s" % OUT)
    print("  探针单格：w 中位 %.1f s（n=%d）｜ rand 中位 %.1f s（n=%d）"
          % (probe["w"]["per_cell_s"]["median"], probe["w"]["per_cell_s"]["n"],
             probe["rand"]["per_cell_s"]["median"], probe["rand"]["per_cell_s"]["n"]))
    print("  生成间隔：中位 %.1f s（n=%d）｜ 每条中位 %.2f GB"
          % (res["gen_track"]["per_interval_s"]["median"],
             res["gen_track"]["per_interval_s"]["n"],
             res["gen_track"]["per_tid_bytes"]["median"] / 1e9))
    print("  格清单：%d 行 / %s 列（无 pos_frac）" % (len(clines), res["cell_list"]["n_columns"]))


if __name__ == "__main__":
    main()
