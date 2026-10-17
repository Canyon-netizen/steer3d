#!/usr/bin/env python
"""Cross-round sweep-parameter check (revision 244.22).

Division of labour, deliberately narrow:
  This script reads the instrument's OWN self-reported scan params out of the
  per-cell JSON readouts.  It does NOT parse ladders, does NOT compute deltas,
  does NOT touch r227_kcurve's block/join logic.

Why that matters: two parsers are two truths.  But here the opposite also
holds -- importing the reader would drag in BEGIN-format assumptions that
have nothing to do with scan params, and the params are stable across every
BEGIN format revision so far.  So the honest cut is: params come from the
readout lines, verdict logic comes from nobody else.

Why this script exists at all:
  Revision 232 already established that "adjacent-gap max" is not comparable
  across rounds because it grows with ladder length.  The same hazard applies
  to ANY cross-round comparison, including the sign of the dose response: if
  the two rounds ran with different pos_frac / n_steps / gap, then "the signs
  agree" is not evidence of reproducibility, it is evidence that you compared
  two different instruments.  So before asking "are the signs stable across
  reruns", the params must be shown equal.

What it adds, and only this:
  1. Gate 0: refuse to compare a file against itself.  A comparison tool whose
     most dangerous defect is "comparing one thing to itself and reporting
     agreement" has to say so out loud (same lesson as arm_verdict.py gate 0).
  2. Per-file: every scan param must have EXACTLY ONE distinct value across
     all cells.  More than one means the round mixed instruments mid-sweep.
  3. Across files: all params must be identical, else print WHICH key differs.
  4. Distinguishes "measured and equal" from "not measured".  A file with no
     readable readout lines is NOT evidence of agreement.

⚠⚠ What this cannot settle, stated so it is not read as settled:
  - Equal params do NOT establish reproducibility.  They only remove one
    confound.  Reproducibility still has to be shown from the readings.
  - It does not check that the two rounds used the same MODEL, the same w
    vector, the same data files, or ran at the same time.  Those are separate
    confounds and this script is silent about all of them.
  - It says nothing about whether the ladder was placed correctly.

Exit: 0 params identical and measured; 2 precondition failure (no verdict);
     1 params differ (a real finding, not an error).
"""
import argparse
import json
import os
import re
import sys

# The params that define the sweep.  Adding/removing a key here changes what
# "identical" means, so the key list is explicit rather than discovered.
SCAN_PARAMS = ("pos_frac", "n_steps", "gap", "arm", "inject_nested")

READ_MARKERS = ('"tid"', '"p9_lo_meas"')


class Fail(Exception):
    """⛔ Precondition failure. No verdict is printed."""


def _fmt(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return repr(v)
    return str(v)


def scan_params(path):
    """Read one log -> (params, n_cells, n_bad_lines).

    params: {key: (only_value, n_distinct)}.  Never a bare value: "there was
    exactly one" and "there were several" must stay distinguishable all the
    way to the caller, because "not measured" and "measured and equal" are
    different claims.
    """
    if not os.path.isfile(path):
        raise Fail("找不到日志：%s" % path)
    seen = {k: {} for k in SCAN_PARAMS}
    n_cells = 0
    n_bad = 0
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not all(m in line for m in READ_MARKERS):
                continue
            n_cells += 1
            try:
                obj = json.loads(line[line.index("{"):])
            except Exception:
                n_bad += 1
                continue
            for k in SCAN_PARAMS:
                if k in obj:
                    seen[k][repr(obj[k])] = obj[k]
    if n_cells == 0:
        raise Fail("日志 %s 里 0 条可读读数行（坏行 %d）⇒ **未量到**，"
                   "不是「参数相同」" % (os.path.basename(path), n_bad))
    return seen, n_cells, n_bad


def resolve(path, seen):
    """{key: value} or Fail.  Reports missing-vs-mixed explicitly."""
    out = {}
    for k in SCAN_PARAMS:
        vals = seen[k]
        if len(vals) == 0:
            raise Fail("%s 的读数里没有 %r 这一项 ⇒ **未量到**"
                       % (os.path.basename(path), k))
        if len(vals) > 1:
            raise Fail("%s 的 %s 在格间混用 %d 个值 %s ⇒ 这一轮换了仪器，"
                       "拒绝当同一轮读"
                       % (os.path.basename(path), k, len(vals), sorted(vals)))
        out[k] = next(iter(vals.values()))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="+", help=">=2 个日志；全部参数必须相同")
    ap.add_argument("--expect-cells", type=int, default=None,
                    help="每个日志应有的格数（不含 ALLDONE 行）")
    args = ap.parse_args(argv)

    # ---- 闸 0：拒绝自己比自己 -------------------------------------------
    names = [os.path.abspath(p) for p in args.logs]
    if len(set(names)) != len(names):
        dup = sorted({os.path.basename(n) for n in names})
        raise Fail("⛔ 同一个文件被传了多次：%s —— 拿一个东西跟自己比，"
                   "必然「相同」，那不是证据" % dup)
    if len(names) < 2:
        raise Fail("至少要两个日志才能比")

    resolved = {}
    for p, ap_path in zip(args.logs, names):
        seen, n_cells, n_bad = scan_params(p)
        resolved[ap_path] = resolve(p, seen)
        resolved[ap_path + "##meta"] = (n_cells, n_bad)

    # ---- 报告 -----------------------------------------------------------
    print("=" * 78)
    print("跨轮扫描参数核对（只比参数，不碰读数）")
    print("=" * 78)
    for p in args.logs:
        ap_path = os.path.abspath(p)
        n_cells, n_bad = resolved[ap_path + "##meta"]
        r = resolved[ap_path]
        print("\n  %s" % os.path.basename(p))
        print("    读数格数 %d（坏行 %d）" % (n_cells, n_bad))
        for k in SCAN_PARAMS:
            print("      %-14s %s" % (k, _fmt(r[k])))
        if args.expect_cells is not None and n_cells != args.expect_cells:
            print("    ⚠ 格数 %d ≠ 期望 %d" % (n_cells, args.expect_cells))

    base = resolved[os.path.abspath(args.logs[0])]
    diffs = []
    for p in args.logs[1:]:
        r = resolved[os.path.abspath(p)]
        # ⚠⚠⁴ 比较用**原始值**，绝不经过 _fmt。
        # ⚖ _fmt 只管打印。若判定也走它，那么「把浮点打成同一串」会同时
        # ⚖ 毁掉判定与产物 —— 那样 rc 与产物就一起说谎，台架原理上抓不到。
        # ⚖ 判定与打印分开之后，_fmt 被破坏时 rc 仍是对的、产物反而露馅。
        for k in SCAN_PARAMS:
            if repr(r[k]) != repr(base[k]):
                diffs.append((os.path.basename(p), k, _fmt(base[k]), _fmt(r[k])))

    print("\n" + "-" * 78)
    if diffs:
        print("⛔ 参数不同 ⇒ 跨轮判决不可比（不要在这两轮之间比任何读数）")
        for name, k, a, b in diffs:
            print("   %s: %s  %s  ≠  %s" % (name, k, a, b))
        print("-" * 78)
        return 1

    print("✅ 各轮扫描参数逐项相同：%s"
          % ", ".join("%s=%s" % (k, _fmt(base[k])) for k in SCAN_PARAMS))
    print("⚖ 这只消掉了一个混淆（仪器配置不同）。")
    print("⚖ ⚠ **参数相同 ≠ 读数可重现** —— 重现性仍要看读数本身。")
    print("⚖ ⚠ 本脚本**没查**模型 / w 向量 / 数据文件 / 是否同时跑。")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Fail as e:
        print("PRECOND_FAIL: %s" % e, file=sys.stderr)
        sys.exit(2)
