#!/usr/bin/env python
"""244.77 的**独立**核对：n_eff 三表 + 168 格清单（⛔ 不入库，一次性）。

为什么需要它：`precompute_n_eff.py` **没有 `--selftest` 入口** ⇒ 那张表这一侧
本来**没有判据保护**。本脚本刻意**不复用**那个工具的代码路径：

  · P        ⛔ 不信表里第 2 列 ⇒ 改从**侧车** `extra.prompt_tokens` 取（另一个来源）
  · n_gen    ⛔ 不信表里第 3/4 列 ⇒ 改从**原始侧车** `n_generated_tokens`
              与**原始 npz** `token_ids` 长度现算
  · t        ⛔ 不信表里第 5 列 ⇒ 现算 `max(1, int(n_gen * pos_frac))`
  · n_eff    ⛔ 不信表里第 6 列 ⇒ 现算 `P + t`
  · 密度     ⛔ 不复用池快照 ⇒ 用**表**算 `n_sites / (n_eff - 1)` 再比 ρ*±tol
              （⇒ 格清单生成器走的是「池快照」管线，本脚本走的是「侧车/npz」管线，
                 两条独立管线算出同一个密度 ⇒ 才算互相印证）

每条判据都能红：任何一条不符 ⇒ 退出码非 0 且逐条打印 `FAIL`。
"""
import argparse
import hashlib
import json
import os
import sys
from glob import glob

HEADER = "tid\tP\tn_gen_sidecar\tn_gen_npz\tt\tn_eff"
PFS = [0.25, 0.5, 0.75]


def md5_of(path):
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_table(path):
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    while lines and lines[-1] == "":
        lines.pop()
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--nmap-prefix", required=True)
    ap.add_argument("--existing-single", default="")
    ap.add_argument("--cells", required=True)
    ap.add_argument("--rho", type=float, required=True)
    ap.add_argument("--tol", type=float, required=True)
    args = ap.parse_args()

    fails = []
    notes = []

    def chk(name, ok, detail=""):
        tag = "OK  " if ok else "FAIL"
        print("[%s] %-46s %s" % (tag, name, detail))
        if not ok:
            fails.append(name)

    # ---------- 侧车/npz 原始来源 ----------
    raw = {}
    for f in sorted(glob(os.path.join(args.data_dir, "*.json"))):
        tid = os.path.basename(f)[:-5]
        npz = os.path.join(args.data_dir, tid + ".npz")
        j = json.load(open(f, encoding="utf-8"))
        import numpy as np
        z = np.load(npz)
        try:
            n_npz = len(z["token_ids"])
        finally:
            z.close()
        raw[tid] = {
            "P_sidecar": int(j.get("extra", {}).get("prompt_tokens", -1)),
            "n_side": int(j["n_generated_tokens"]),
            "n_npz": int(n_npz),
        }
    chk("S0 原始来源条数=60", len(raw) == 60, "got=%d" % len(raw))

    # ---------- 三张表 ----------
    tabs = {}
    for pf in PFS:
        key = ("%.2f" % pf).replace(".", "")
        path = "%s_pf%s.tsv" % (args.nmap_prefix, key)
        tabs[pf] = path
        if not os.path.isfile(path):
            chk("S1 表存在 pf=%s" % pf, False, path)
            continue
        lines = read_table(path)
        chk("S1 表头逐字相符 pf=%s" % pf, lines and lines[0] == HEADER,
            repr(lines[0]) if lines else "<empty>")
        body = lines[1:]
        chk("S2 数据行=60 pf=%s" % pf, len(body) == 60, "got=%d" % len(body))
        nf = [len(r.split("\t")) for r in body]
        chk("S2 每行 6 列 pf=%s" % pf, all(n == 6 for n in nf),
            "bad_rows=%d" % sum(1 for n in nf if n != 6))
        tids = [r.split("\t")[0] for r in body]
        chk("S2 tid 唯一且已排序 pf=%s" % pf,
            len(set(tids)) == len(tids) and tids == sorted(tids), "")

        bad = []
        for r in body:
            f_ = r.split("\t")
            tid = f_[0]
            Pt, nst, nnt, tt, net = (int(f_[1]), int(f_[2]), int(f_[3]),
                                     int(f_[4]), int(f_[5]))
            src = raw.get(tid)
            if src is None:
                bad.append("%s 不在原始侧车里" % tid)
                continue
            # S3 P 的独立来源
            if Pt != src["P_sidecar"]:
                bad.append("%s P表=%d 侧车=%d" % (tid, Pt, src["P_sidecar"]))
            # S4/S5 n_gen 的独立来源
            if nst != src["n_side"]:
                bad.append("%s n_gen_sidecar列=%d 侧车=%d" % (tid, nst, src["n_side"]))
            if nnt != src["n_npz"]:
                bad.append("%s n_gen_npz列=%d npz=%d" % (tid, nnt, src["n_npz"]))
            # S6/S7 t 与 n_eff 现算
            t_calc = max(1, int(src["n_side"] * pf))
            if tt != t_calc:
                bad.append("%s t列=%d 现算=%d" % (tid, tt, t_calc))
            if net != Pt + t_calc:
                bad.append("%s n_eff列=%d 现算=%d" % (tid, net, Pt + t_calc))
        chk("S3-S7 逐行独立复算一致 pf=%s" % pf, not bad,
            "; ".join(bad[:3]) if bad else "60/60")

    # ---------- SAME_050 ----------
    if args.existing_single:
        p50 = tabs.get(0.5, "")
        same = (os.path.isfile(p50) and os.path.isfile(args.existing_single)
                and md5_of(p50) == md5_of(args.existing_single))
        chk("S8 SAME_050（pf050 与现有表逐字节相同）", same,
            "%s vs %s" % (md5_of(p50) if os.path.isfile(p50) else "?",
                          md5_of(args.existing_single)
                          if os.path.isfile(args.existing_single) else "?"))

    # ---------- 三表间单调 ----------
    mono_ok, mono_detail = True, ""
    for tid in raw:
        vals = []
        for pf in PFS:
            path = tabs.get(pf)
            if not path or not os.path.isfile(path):
                mono_ok = False
                continue
            for r in read_table(path)[1:]:
                f_ = r.split("\t")
                if f_[0] == tid:
                    vals.append((pf, int(f_[4]), int(f_[5])))
                    break
        if len(vals) == len(PFS):
            ts = [v[1] for v in sorted(vals)]
            es = [v[2] for v in sorted(vals)]
            if ts != sorted(ts) or es != sorted(es):
                mono_ok = False
                mono_detail = "%s t=%s n_eff=%s" % (tid, ts, es)
                break
    chk("S9 同 tid 的 t/n_eff 随 pos_frac 单调不减", mono_ok, mono_detail)

    # ---------- 168 格清单 ----------
    with open(args.cells, encoding="utf-8") as fh:
        clines = fh.read().split("\n")
    while clines and clines[-1] == "":
        clines.pop()
    chk("S10 清单表头逐字相符",
        clines and clines[0] == "tid\tscope\tn_sites\tpos_frac",
        repr(clines[0]) if clines else "<empty>")
    crows = clines[1:]
    chk("S10 清单数据行=168", len(crows) == 168, "got=%d" % len(crows))

    tbl_by_pf = {}
    for pf in PFS:
        p = tabs.get(pf)
        if p and os.path.isfile(p):
            tbl_by_pf[pf] = {r.split("\t")[0]: r.split("\t")
                             for r in read_table(p)[1:]}

    miss_tab, miss_tid = [], []
    dens, dens_bad = [], []
    for r in crows:
        f_ = r.split("\t")
        tid, n_sites, pf = f_[0], int(f_[2]), float(f_[3])
        tab = tbl_by_pf.get(pf)
        if tab is None:
            miss_tab.append(pf)
            continue
        if tid not in tab:
            miss_tid.append(tid)
            continue
        n_eff = int(tab[tid][5])
        d = n_sites / float(n_eff - 1)
        dens.append((d, tid, pf))
        if abs(d - args.rho) > args.tol:
            dens_bad.append("%s pf=%g d=%.6f" % (tid, pf, d))
    chk("S10 每格 pos_frac 都有对应表", not miss_tab, str(sorted(set(miss_tab))))
    chk("S10 每格 tid 都在表里", not miss_tid, str(sorted(set(miss_tid))[:3]))
    chk("S11 端到端密度 ∈ ρ*±tol", not dens_bad,
        "; ".join(dens_bad[:3]) if dens_bad else "%d/%d" % (len(dens), len(crows)))

    if dens:
        vals = [d for d, _, _ in dens]
        worst = max(abs(v - args.rho) for v in vals)
        print("     密度 min=%.6f max=%.6f 最坏|d-ρ*|=%.6f tol=%.6f"
              % (min(vals), max(vals), worst, args.tol))
        lo = min(dens)
        hi = max(dens)
        print("     最小: %s (d=%.6f pf=%g)   最大: %s (d=%.6f pf=%g)"
              % (lo[1], lo[0], lo[2], hi[1], hi[0], hi[2]))

    # ---------- 每张表的 md5 落日志 ----------
    print("--- md5 ---")
    for pf in PFS:
        p = tabs.get(pf)
        if p and os.path.isfile(p):
            print("md5_pf%s=%s  file=%s" % (("%.2f" % pf).replace(".", ""),
                                           md5_of(p), os.path.basename(p)))

    print("--- summary ---")
    print("checks_failed=%d  %s" % (len(fails), ",".join(fails) if fails else "ALL_GREEN"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
