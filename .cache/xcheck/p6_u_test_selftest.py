#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P6 判决仪器自检（修订 202 立）—— 16 项，四向证伪。

按修订 8 §8.3 的纪律：**判据必须能红**。一个永远给 p=0.51 的检验没用，
一个永远给 p<0.001 的检验更没用 —— 两头都要测。

四向：
  T1 空/单点           必须拒，不得出判决
  T2 已知答案的解析解   U / HL / Cliff 必须与手算一致
  T3 双实现交叉验证     与 scipy.stats.mannwhitneyu 逐位比对
  T4 真数据形状         device_validated=false 必须 BLOCKED；缺字段同样 BLOCKED

⚠⚠ **「缺字段 ≠ 通过」**单独占一项（U4）：
⚠⚠ 修订 195 的教训是「闸没接上 ≠ 闸通过」；同一形态在这里是
⚠⚠ 「产物里没有那个字段」很容易被读成「没发现问题」。

退出码：0 全过 / 1 有项红 / 2 导入失败
"""

import io
import json
import math
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

try:
    import p6_u_test as M
except Exception as e:                            # noqa: BLE001
    print("[错误] 导入 p6_u_test 失败：%r" % (e,))
    sys.exit(2)

FAILS = []
CHECKS = [0]          # ⚠ 计数是真数的：修订 202 之前这里硬编码 "16/16"，
                      # ⚠ 实际早就不止 16 项了 —— 写死的数字会骗下一个人。


def check(name, cond, detail=""):
    CHECKS[0] += 1
    print("  %-52s %s%s" % (name, "PASS" if cond else "FAIL",
                            ("  <- " + detail) if (detail and not cond) else ""))
    if not cond:
        FAILS.append(name)


def run_main(argv):
    """跑 p6_u_test 的 main()，返回 (退出码, 打印文本)。"""
    old = sys.argv
    sys.argv = ["p6_u_test"] + argv
    buf = io.StringIO()
    err = io.StringIO()
    try:
        with redirect_stdout(buf), redirect_stderr(err):
            rc = M.main()
    except SystemExit as e:            # argparse 报用法错走 SystemExit，不接会把自检打死
        rc = e.code if isinstance(e.code, int) else 1
    finally:
        sys.argv = old
    return rc, buf.getvalue()


def main():
    print("=== T1：退化输入必须拒 ===")
    rc, _ = run_main(["--a", "1.0", "--b"])
    check("T1a 缺 --b ⇒ EXIT 2", rc == 2, "实得 %r" % rc)

    a11 = [float(x) for x in range(1, 12)]      # {1..11}
    b11 = [float(x) for x in range(2, 13)]      # {2..12}
    # 手算 U_a = #(a>b) + 0.5#(a=b)：
    #   #(a>b)：a=1→0, a=2→0, a=3→1, …, a=11→9，合计 0+0+1+2+…+9 = 45
    #   #(a=b)：值 2..11 各 1 对，合计 10
    #   ⇒ U_a = 45 + 0.5×10 = 50.0
    # ⚠ 这里原来写的是 55.0 —— 那是我上一轮的心算错（把并列只数了 1 对），不是仪器错。
    # ⚠ 同一对 (a11,b11) 在 T3 里还会与 scipy 逐位比对，构成独立第三方确认。
    check("T1b 交叠且有并列 ⇒ U = 45+0.5×10 = 50（手算）",
          M.mannwhitney_u(a11, b11) == 50.0,
          "实得 %r" % M.mannwhitney_u(a11, b11))

    print("\n=== T2：解析解对照（手算，不是抄输出）===")
    # 完全分离：a 全大于 b ⇒ U = n1*n2（取 b 在前的约定下为 0）
    a_sep = [10.0, 11.0, 12.0, 13.0, 14.0]
    b_sep = [1.0, 2.0, 3.0, 4.0, 5.0]
    u_sep = M.mannwhitney_u(a_sep, b_sep)
    check("T2a 完全分离 ⇒ U = n1*n2 = 25", u_sep == 25.0, "实得 %r" % u_sep)
    check("T2b 完全分离 ⇒ Cliff's delta = +1",
          M.cliffs_delta(a_sep, b_sep) == 1.0,
          "实得 %r" % M.cliffs_delta(a_sep, b_sep))
    # HL：全部差的中位数。a-b 的 25 个差值范围 5..13，中位 = 9
    hl = M.hodges_lehmann(a_sep, b_sep)
    check("T2c HL = 全部 (a-b) 的中位数 = 9", hl == 9.0, "实得 %r" % hl)
    # 对称：delta 应为 0
    sym = [-3.0, -1.0, 0.0, 1.0, 3.0]
    check("T2d 对称分布 ⇒ Cliff's delta = 0",
          M.cliffs_delta(sym, sym) == 0.0,
          "实得 %r" % M.cliffs_delta(sym, sym))
    # 全并列：U 应恰为期望值 n1*n2/2
    tie = [1.0] * 6
    # 手算：12 个值全并列 ⇒ 每值秩 = 6.5；R_a = 6×6.5 = 39
    #       U = 39 − 6×7/2 = 39 − 21 = 18 = n1·n2/2 = 36/2
    # ⚠ 这里原来写的是 18/2.0 = 9 —— 我把 n1·n2(=36) 写成 18 又除了 2，断言错，仪器对。
    check("T2e 全并列 ⇒ U = R_a − n1(n1+1)/2 = 39−21 = 18（手算）",
          M.mannwhitney_u(tie, tie) == 18.0,
          "实得 %r" % M.mannwhitney_u(tie, tie))

    # ⚠ 修订 202 新增：**不依赖 scipy** 的精确 p 锚点。
    # n1=n2=5 完全分离 ⇒ U=25（唯一取到该 U 的秩组合是 {6,7,8,9,10}，共 1 个）
    # ⇒ 单侧 p = 1/C(10,5) = 1/252；双侧 = 2/252 = 0.007936507936…
    p_exact_sep = M.u_pvalue_exact(M.mannwhitney_u(a_sep, b_sep), 5, 5)
    check("T2f ⛔ 精确 p 必须双侧 = 2/252（曾错为单侧 1/252）",
          abs(p_exact_sep - 2.0 / 252.0) < 1e-12,
          "实得 %r，应为 %r" % (p_exact_sep, 2.0 / 252.0))
    # 精确分布关于 n1·n2/2 对称 ⇒ U 与 n1·n2−U 必须给出**同一个**双侧 p。
    # ⚠ 若哪天有人把 ×2 删掉、或只数单尾，这项立刻红。
    check("T2g 精确 p 对称：U 与 n1·n2−U 同 p",
          abs(M.u_pvalue_exact(25.0, 5, 5) - M.u_pvalue_exact(0.0, 5, 5)) < 1e-12,
          "U=25:%r  U=0:%r" % (M.u_pvalue_exact(25.0, 5, 5),
                               M.u_pvalue_exact(0.0, 5, 5)))

    # ⚠⚠⚴ 修订 202 追加：上面对**完全分离**那例的锚点是有分辨力上限的 ——
    # ⚠⚠⚴ 那里「2×单尾」与正确值恰好相等 ⇒ 它绿了也证明不了什么。
    # ⚠⚠⚴ 必须再有一个**分布中段**的锚点，那里两法差得最开。
    # 手算 n1=n2=4, U=7（μ=8, dev=1）：
    #   两 sided p = P(|U−8| ≥ 1) = 1 − P(U=8)
    #   P(U=8)：4-子集 of {1..8} 和为 18，按最大元分：max=8 → 4 个(1,2,7)(1,3,6)(1,4,5)(2,3,5)
    #   max=7 → 3 个(1,4,6)(2,3,6)(2,4,5)；max=6 → 1 个(3,4,5)；合计 8
    #   ⇒ p = (70 − 8)/70 = 62/70 = 0.8857142857
    # ⛔ 而「2×单尾」在这里会给 14/70 = 0.200 —— 差 4.4 倍，这就是分辨力。
    check("T2h ⛔ 中段精确双侧 p = 1 − P(U=μ) = 62/70（2×单尾会给 0.200）",
          abs(M.u_pvalue_exact(7.0, 4, 4) - 62.0 / 70.0) < 1e-12,
          "实得 %r，应为 %r" % (M.u_pvalue_exact(7.0, 4, 4), 62.0 / 70.0))

    print("\n=== T3：与 scipy 双实现交叉验证（**同口径**）===")
    # ⚠⚠ 修订 202：本节原来只拿**正态近似**去比 scipy 的 method="auto"，
    # ⚠⚠ 而 auto 在「无并列 + 小样本」时选**精确** ⇒ 口径错配，那一次红是白红。
    # ⚠⚠ 现在拆成两条分别同口径比对，正态路径与精确路径**各自**都被验到。
    try:
        from scipy.stats import mannwhitneyu
        have = True
    except Exception:                             # noqa: BLE001
        have = False
    if not have:
        print("  ⚠ 本机无 scipy，T3 跳过（远端 easysteer 环境也无）")
    else:
        cases = [
            ("分离", a_sep, b_sep),
            ("交叠", a11, b11),
            ("有并列", [1.0, 2.0, 2.0, 3.0, 9.0], [1.0, 2.0, 4.0, 4.0, 5.0]),
            ("等长等距", [1.0, 2, 3, 4, 5, 6], [2, 3, 4, 5, 6, 7]),
            ("带负值", [-5.0, -1.0, 0.5, 2.0], [-3.0, 0.0, 1.0, 1.5]),
        ]
        for nm, a_, b_ in cases:
            u_mine = M.mannwhitney_u(a_, b_)
            # ---- 3a 正态近似 vs scipy asymptotic ----
            p_mine = M.u_pvalue_normal(u_mine, len(a_), len(b_), a_ + b_)
            r = mannwhitneyu(a_, b_, alternative="two-sided", method="asymptotic")
            ok_u = abs(float(r.statistic) - u_mine) < 1e-9
            ok_p = abs(float(r.pvalue) - p_mine) <= max(2e-4, 0.02 * float(r.pvalue))
            check("T3a 正态 %s：U 与 p 对齐 scipy(asymptotic)" % nm, ok_u and ok_p,
                  "U %r/%r  p %r/%r" % (u_mine, float(r.statistic), p_mine, float(r.pvalue)))
            # ---- 3b 精确 vs scipy exact（仅无并列且枚举量可控时）----
            if not M._tie_groups(a_ + b_):
                ncomb = M.comb(len(a_) + len(b_), len(a_))
                if ncomb <= M.EXACT_MAX_COMB:
                    pe_mine = M.u_pvalue_exact(u_mine, len(a_), len(b_))
                    re_ = mannwhitneyu(a_, b_, alternative="two-sided", method="exact")
                    check("T3b 精确 %s：p 对齐 scipy(exact)" % nm,
                          abs(float(re_.pvalue) - pe_mine) <= max(2e-9, 1e-9),
                          "mine %r  scipy %r" % (pe_mine, float(re_.pvalue)))
                    check("T3c 精确 %s：p ≤ 1.0 且 > 0" % nm,
                          0.0 < pe_mine <= 1.0, "实得 %r" % pe_mine)

    print("\n=== T4：真数据形状（device_validated 闸）===")
    tmp = tempfile.mkdtemp(prefix="p6u_")

    def mk_rows(n_correct, n_wrong, per_traj=1, val_c=0.0, val_w=0.0, with_traj=True):
        """造 §P6 真实形状的行：n_correct 条 correct 轨迹 + n_wrong 条 wrong 轨迹，
        **每条轨迹 per_traj 个位置**。位置值带 +j*0.01 的偏移，使平均有意义。"""
        out = []
        kt = 0
        for lab, n, val in (("correct", n_correct, val_c), ("wrong", n_wrong, val_w)):
            for _i in range(n):               # 每条**轨迹**
                tid = "tj%03d" % kt
                kt += 1
                for j in range(per_traj):      # 每条轨迹的各**位置**
                    r = {"t": j, "label": lab, "mark_w+_1.0": val + j * 0.01}
                    if with_traj:
                        r["traj"] = tid
                    out.append(r)
        return out

    # ⚠⚠⚴ 修订 202：这两个夹具原来只有 n1=1 / n2=1，而 P6_CORRECT_FLOOR=10。
    # ⚠⚠⚴ 于是 rc=4 会**同时**被「样本量不足」触发 —— 变异台把闸打掉后
    # ⚠⚠⚴ T4a/T4c 依然绿 ⇒ **绿是假阳性**（红对了，但绿没有分辨力）。
    # ⚠⚠◴ 现在固定 11 条 correct / 17 条 wrong 轨迹、每条 1 个位置，
    # ⚠⚠◴ 让 rc=4 的**唯一**来源就是 device_validated 那道闸。
    good_rows = mk_rows(11, 17, per_traj=1)

    p_bad = Path(tmp) / "bad.json"
    p_bad.write_text(json.dumps(
        {"device_validated": False, "pos_ok": False, "rows": good_rows}),
        encoding="utf-8")
    rc, txt = run_main(["--rows", str(p_bad)])
    check("T4a device_validated=false ⇒ EXIT 4", rc == 4, "实得 %r" % rc)
    check("T4b 且打印明说「未验证的装置」",
          "未验证" in txt or "device_validated=false" in txt)

    p_miss = Path(tmp) / "miss.json"
    p_miss.write_text(json.dumps(
        {"pos_ok": True, "rows": good_rows}), encoding="utf-8")
    rc, txt = run_main(["--rows", str(p_miss)])
    check("T4c ⛔ 缺 device_validated 字段 ⇒ EXIT 4（缺字段≠通过）",
          rc == 4, "实得 %r" % rc)
    check("T4d 且理由写明「缺字段 ≠ 通过」", "缺字段" in txt)

    p_ok = Path(tmp) / "ok.json"
    # 11 条 correct / 17 条 wrong 轨迹，每条 1 个位置，且 correct 全高于 wrong
    p_ok.write_text(json.dumps({"device_validated": True, "pos_ok": True,
                                "rows": mk_rows(11, 17, 1, 1.0, -1.0)}),
                    encoding="utf-8")
    rc, txt = run_main(["--rows", str(p_ok)])
    check("T4e device_validated=true + 明显分离 ⇒ EXIT 0", rc == 0, "实得 %r" % rc)
    check("T4f 且判「显著」", "显著" in txt and "NS" not in txt.split("RESULT")[-1])
    check("T4g 且强制打印功效披露", "功效" in txt)

    print("\n=== T5：功效披露与样本量底线，各管一头 ===")
    p_s = Path(tmp) / "small.json"
    p_s.write_text(json.dumps({"device_validated": True,
                               "rows": mk_rows(11, 3, 1, 0.5, -0.5)}),
                   encoding="utf-8")
    rc, txt = run_main(["--rows", str(p_s)])
    check("T5a wrong n=3 ⇒ 功效警告必须出现", "功效极低" in txt)

    # ---- 5b ⛔ correct 组低于 §P6 的 10 条**轨迹**底线 ⇒ 必须 BLOCKED ----
    # ⚠⚠⚴ 修订 202：变异台 M8 把 P6_CORRECT_FLOOR 改成 0，**判据一条没红** ——
    # ⚠⚠⚴ 因为 T5 只覆盖了 wrong 组的功效警示，correct 组的底线**没有任何一项在看**。
    # ⚠⚠◴ 「已覆盖」和「真的会红」是两件事；这里是没有第二个人问过的那一件。
    # ⚠⚠⚴ 且这里特意用 **per_traj=6**：9 条轨迹 × 6 位置 = 54 **行**。
    # ⚠⚠⚴ 若代码按行计数，n1=54 ≫ 10 ⇒ 底线不会触发 ⇒ 这一项就抓得到它。
    p_f = Path(tmp) / "few.json"
    p_f.write_text(json.dumps({"device_validated": True,
                               "rows": mk_rows(9, 17, 6, 0.5, -0.5)}),
                   encoding="utf-8")
    rc, txt = run_main(["--rows", str(p_f)])
    check("T5b ⛔ correct 9 条轨迹(54 行) < 10 ⇒ EXIT 4（底线按**轨迹**数，不按行）",
          rc == 4, "实得 %r" % rc)
    check("T5c 且文本明说「样本不足，不构成结论」", "样本不足" in txt)

    print("\n=== T7：§P6 聚合口径（伪重复）===")
    # ⚠⚠⚴ 修订 202 最重的一处：原实现逐行 append，n = 行数。
    # ⚠⚠⚴ r6_rerun 的 rows 是按**位置**记的（MAX_POS_PER_TRAJ = 6），
    # ⚠⚠⚴ 而 §P6 原文要求「对每条轨迹先算一个数」。
    # ⚠⚠◴ 夹具：11 条 correct 轨迹 × 6 位置 = 66 行；17 条 wrong × 6 = 102 行。
    # ⚠⚠◴ 按行算是 n1=66 / n2=102（远超 n<20 的功效警示线 ⇒ 不警示，
    # ⚠⚠◴     且 correct 组看起来样本充足）；按轨迹算是 n1=11 / n2=17。
    rows6 = mk_rows(11, 17, 6, 1.0, -1.0)
    p_agg = Path(tmp) / "agg.json"
    p_agg.write_text(json.dumps({"device_validated": True, "rows": rows6}),
                     encoding="utf-8")
    rc, txt = run_main(["--rows", str(p_agg)])
    check("T7a 168 行 ⇒ 文本必须显示「行 168 → 轨迹 28」",
          ("行 %d → 轨迹 28" % len(rows6)) in txt,
          "实得文本行：%s" % [l.strip() for l in txt.splitlines() if "→" in l][:2])
    check("T7b 且两组 n 必须是 11 / 17（轨迹数），不是 66 / 102",
          ("correct 组 n=11 " in txt) and ("wrong 组 n=17 " in txt),
          "实得：%s" % [l.strip() for l in txt.splitlines() if "组 n=" in l])
    check("T7c ⛔ wrong n=17 < 20 ⇒ 必须出现功效警示（按行计数时不会出现）",
          "功效极低" in txt)

    # T7d：--by-position 是诊断档，恒不给判决
    rc, txt = run_main(["--rows", str(p_agg), "--by-position"])
    check("T7d ⛔ --by-position ⇒ EXIT 4（伪重复口径不得出判决）",
          rc == 4, "实得 %r" % rc)
    check("T7e 且明说「不构成 §P6 判决」", "不构成 §P6 判决" in txt)

    # T7f：缺 traj 字段必须拒绝，而不是悄悄把每行当一条轨迹
    p_nt = Path(tmp) / "notraj.json"
    p_nt.write_text(json.dumps({"device_validated": True,
                                "rows": mk_rows(11, 17, 6, 1.0, -1.0, with_traj=False)}),
                    encoding="utf-8")
    rc, txt = run_main(["--rows", str(p_nt)])
    check("T7f ⛔ rows 缺 traj ⇒ EXIT 4（不能默认每行一条轨迹）",
          rc == 4, "实得 %r" % rc)
    check("T7g 且理由写明「缺 traj」", "缺 traj" in txt)

    print("\n=== 汇总 ===")
    if FAILS:
        print("RESULT p6_u_test_selftest  FAIL  %d 项红：%s"
              % (len(FAILS), FAILS))
        return 1
    print("RESULT p6_u_test_selftest  OK  %d/%d" % (CHECKS[0], CHECKS[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
