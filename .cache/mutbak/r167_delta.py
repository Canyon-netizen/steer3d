"""cap 8192 → 32768 的【差分分析】：那批 unlabeled 到底翻成了什么。

⚠⚠⁴⚠ 为什么这个脚本要单独存在
──────────────────────────────
R-6 要回答的不是「32k 有没有用」，而是一个具体到数字的命题：

    前 30 题（aime25）原有 **19 条 unlabeled**，
    而 P6 的硬约束是 **correct 组 ≥ 10**（现在 **7**，缺口 **3**）
    ⇒ **必须有 ≥3 条 unlabeled 在 cap 32768 下翻成 correct**（转化率 > 16%）。

⚠⚠⚴ **而「标签产出率会变好看」与「P6 会够格」是两个不同的量。**
⚗ 提 cap 一定能把 unlabeled 变成 labeled（smoke 已证：p04 写了 boxed 297），
⚗⚠ **但那条翻成了 wrong。⚗⚠ 代理指标涨了，P6 要的 correct 未必动。**

⚠ 所以本脚本**只报三个数**，且每一个都要求能指回具体轨迹 id：

  1. 转移矩阵：unlabeled → correct / wrong / 仍 unlabeled
  2. P6 现状：aime25 的 correct 够不够 10，缺口还剩几条
  3. ⚠⚠ 转化率是否越过 16% 那条线 —— **够/不够分开写**，不许只写一个百分比

⚠⚠⁴ **不许做的事**：
  ⚗ 把两批的 unlabeled 分母混着算（8192 的 19 条 与 32768 的不是同一个东西）
  ⚗ 只报「标签产出率 X%」而不报 correct 的数（那正是要防的假指标）
  ⚗ 在数据没跑完时给结论 —— 本脚本对**部分数据**也照跑，但会显式标 n

用法：
    python3 r167_delta.py --old <b2标签json> --new <32768标签json>
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

# ⚠⚠ P6 的硬底线。⚗ **这里不许改** —— 改了等于改预登记口径。
# ⚗⚠ 本脚本只读它、不写它；p6_readiness.py 那一份才是判据来源。
P6_CORRECT_FLOOR = 10

# ⚠ 停止规则取的前 30 题就是 aime25 那一池（jsonl 顺序），判决按单池判。
BENCH = "aime25"


def key_of(traj):
    """aime__aime25__p04__think -> aime25/p04/think"""
    parts = (traj or "").split("__")
    if len(parts) >= 4:
        return "%s/%s/%s" % (parts[1], parts[2], parts[3])
    return traj


def load(p):
    blob = json.loads(Path(p).read_text(encoding="utf-8"))
    rows = blob.get("rows") or []
    return {key_of(r.get("traj")): r for r in rows}, blob


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True, help="cap 8192 批次的 strict_label 产物")
    ap.add_argument("--new", required=True, help="cap 32768 批次的 strict_label 产物")
    ap.add_argument("--show", type=int, default=12, help="逐条明细打印条数")
    a = ap.parse_args()

    old, old_blob = load(a.old)
    new, new_blob = load(a.new)
    print("=== 输入 ===")
    print("  旧（cap %s）：%d 条" % (sorted({r.get("cap") for r in old_blob["rows"]}), len(old)))
    print("  新（cap %s）：%d 条" % (sorted({r.get("cap") for r in new_blob["rows"]}), len(new)))
    if len(new) < 60:
        print("  ⚠⚠⚴ **新批次只完成 %d/60 条 —— 下面每个数都是【部分数据】的数。**" % len(new))

    def pool(d, mode):
        return {k: v for k, v in d.items()
                if k.startswith(BENCH + "/") and v.get("mode") == mode}

    # ---- 1. think 池的转移矩阵 ----
    ot, nt = pool(old, "think"), pool(new, "think")
    common = sorted(set(ot) & set(nt))
    print("\n=== 1. think 转移矩阵（%s 池，两批都有的 %d 条）===" % (BENCH, len(common)))
    mat = Counter()
    for k in common:
        mat[(ot[k].get("strict"), nt[k].get("strict"))] += 1
    labels = ["correct", "wrong", "unlabeled"]
    print("  %-10s -> %-10s %s" % ("旧", "新", "条数"))
    for o in labels:
        for n in labels:
            c = mat.get((o, n), 0)
            if c:
                print("  %-10s -> %-10s %3d %s" % (o, n, c, "⚠ 主路径" if (o, n) == ("unlabeled", "correct") else ""))

    unl = [k for k in common if ot[k].get("strict") == "unlabeled"]
    flipped_correct = [k for k in unl if nt[k].get("strict") == "correct"]
    flipped_wrong = [k for k in unl if nt[k].get("strict") == "wrong"]
    still_unl = [k for k in unl if nt[k].get("strict") == "unlabeled"]
    print("\n  ⚠⚠ 旧 unlabeled 共 %d 条 → 翻成 correct **%d** / wrong **%d** / 仍 unlabeled **%d**"
          % (len(unl), len(flipped_correct), len(flipped_wrong), len(still_unl)))

    # ---- 2. P6 现状 ----
    def tally(d):
        c = Counter(v.get("strict") for k, v in pool(d, "think").items())
        return c["correct"], c["wrong"], c["unlabeled"], sum(c.values())

    def tally_sub(d, keys):
        c = Counter(d[k].get("strict") for k in keys if k in d)
        return c["correct"], c["wrong"], c["unlabeled"], sum(c.values())

    oc, ow, ou, on = tally(old)
    nc, nw, nu, nn = tally(new)
    # ⚠⚠⁴⚠⚴ 第三列：**同 N 条**的旧值。
    # ⚗⚠⚴⚠⚴ 起因：本脚本第一版只印「旧 30 条」与「新 4 条」两列并排，
    # ⚗⚠ **读者一眼就会读成「unlabeled 19 → 0」** ——
    # ⚗⚠⚠⚠ **而那正是 §167.1 明令禁止的误读**（代理指标好看 ≠ P6 要的 correct）。
    # ⚗⚠⚴⚠⚴ ⚗⚠ **两列的 n 不同就不可逐格相减；n 一旦不同，unlabeled 那格最容易骗人。⚗⚠⁴⚗⚠**
    # ⚠ ⇒ 加一列「旧（同 N 条）」，让等 footing 的对比自己做出来。
    sc, sw_, su, sn = tally_sub(old, common)

    print("\n=== 2. P6 现状（%s think 单池，⚗⚠ 不许用合并池）===" % BENCH)
    if nn != on:
        print("  ⚠⚠⚴ **两列的 n 不同（%d vs %d）⇒ 不可逐格相减。**" % (on, nn))
        print("  ⚗⚠⚴⚠ **尤其别把「unlabeled %d → %d」读成「unlabeled 消失了」——⚗⚠⚴⚠"
              % (ou, nu))
        print("  ⚗⚠⚴⚠ 那是【只完成了 %d 条】造成的，⚗⚠⚴⚴ ⚠ **不是提 cap 的效果。⚠⚠⚴⚗⚠⚴⚠⚠**" % nn)
    print("  %-10s %-14s %-20s %s" % ("", "旧（全池）", "旧（同 %d 条）" % sn,
                                      "新（同 %d 条）" % nn))
    print("  %-10s %-14s %-20s %s" % ("correct", oc, sc, nc))
    print("  %-10s %-14s %-20s %s" % ("wrong", ow, sw_, nw))
    print("  %-10s %-14s %-20s %s" % ("unlabeled", ou, su, nu))
    print("  %-10s %-14s %-20s %s" % ("n", on, sn, nn))
    if sn != on:
        print("  ⚠ **第三列才是能和新列比的那一列**（同 %d 条）；⚗⚠ 第一列是全池 %d 条，⚗⚠ 混看会得出错的结论。"
              % (sn, on))

    # ---- 3. 那条 16% 的线 ----
    need = max(0, P6_CORRECT_FLOOR - nc)
    print("\n=== 3. P6 够不够格（底线 correct >= %d）===" % P6_CORRECT_FLOOR)
    if nn < 30:
        print("  ⚠⚠⚴ **新批次 think 只完成 %d 条 ⇒ correct 至少还会涨 ⇒ 现在判「不够」是不公平的。**" % nn)
        print("  ⚗⚠ 本行只说明【当前已完成的 %d 条里 correct=%d】。" % (nn, nc))
    if need == 0:
        print("  ✅ **已够格**：correct = %d ≥ %d。" % (nc, P6_CORRECT_FLOOR))
    else:
        print("  ⚠ **还差 %d 条** correct（现 %d）。" % (need, nc))
        done = len(flipped_correct)
        if unl:
            rate = done / len(unl)
            print("  ⚠⚠ 已翻 correct %d / 旧 unlabeled %d ⇒ 转化率 %.0f%%（门槛 > 16%%）"
                  % (done, len(unl), rate * 100))
            print("  ⚗⚠ **但这是部分数据的转化率**（新批次只完成 %d/%d 条）。" % (nn, on))

    # ---- 逐条明细：证据必须指得回去 ----
    if a.show and unl:
        print("\n=== 明细（旧 unlabeled 的 %d 条，前 %d 条）===" % (len(unl), min(a.show, len(unl))))
        print("  %-22s %-10s %-10s %s" % ("traj", "旧", "新", "新 n_tok"))
        for k in unl[:a.show]:
            r = nt[k]
            print("  %-22s %-10s %-10s %s"
                  % (k, ot[k].get("strict"), r.get("strict"), r.get("n_tok")))

    print("\n⚠ 本脚本【不判定 P6 通过与否】，⚗⚠ 只报数。判定走 p6_readiness.py。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())