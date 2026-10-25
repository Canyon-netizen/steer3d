#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_spec_crosscheck_24492.py —— **预登记 ↔ 实现** 的机械对账（244.92）。

⚖ 逐条检查：检查项 id 集合、判据 id 集合、硬失败集合、形态级联顺序、
   内嵌模板与预登记 §3.2 是否**逐字节**相同、页面锚点行格式（§2.1）、
   变异台的覆盖（§5）、复算入口 id（§2.1）、「改前 ⇒ 改后」两次运行（§2.2）。
⚖ **期望值一律手写**（⛔ 不从实现派生 ⇒ ⇒ 否则两边一起变 ⇒ ⇒ 恒绿）。

⚖ **用法**：
   R244_PREREG=… R244_CONF_PREREG=… R244_PAGE=… python3 _spec_crosscheck_24492.py
"""

import io
import os
import re
import sys
import importlib.util

PREREG = os.environ.get("R244_PREREG", ".cache/xcheck/R6_DOC_CONSISTENCY_PREREG.md")
CONF_PREREG = os.environ.get("R244_CONF_PREREG", ".cache/xcheck/R6_CONFIDENCE_LEVEL_PREREG.md")
LEDGER = os.environ.get("R244_LEDGER", ".cache/xcheck/R6_RERUN_PREREG.md")
PAGE = os.environ.get("R244_PAGE", "docs/BPATH_VERDICT.md")
IMPL = os.environ.get("R244_IMPL", ".cache/r244/doc_consistency_audit.py")
MUT = os.environ.get("R244_MUT", ".cache/r244/mut_doc_consistency_audit.py")
DRIVER = os.environ.get("R244_DRIVER", ".cache/r244/_run_24492_verify.sh")


def read(path):
    with io.open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def load(path):
    spec = importlib.util.spec_from_file_location("impl24492", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    ok = 0
    bad = []

    def chk(name, cond, detail=""):
        nonlocal ok
        if cond:
            ok += 1
        else:
            bad.append("%s%s" % (name, ("：" + detail) if detail else ""))

    impl = load(IMPL)
    pre = read(PREREG)
    conf_pre = read(CONF_PREREG)
    impl_src = read(IMPL)
    page = read(PAGE)

    # ---- 1. 检查项 id 集合：预登记 §2 的表 ↔ 实现的 CHECK_IDS ----
    pre_a = set(re.findall(r"^\| \*\*(A\d)\*\* \|", pre, re.M))
    chk("§2 检查项集合", pre_a == set(impl.CHECK_IDS),
        "预登记 %s vs 实现 %s" % (sorted(pre_a), sorted(impl.CHECK_IDS)))
    # ⚖ **顺序**只按 §2 那一段取（⛔ §2.1 里还有一张「七行 ↔ 九个检查项」的分工表 ⇒ ⇒ 不能混着数）
    sec2 = pre.split("## §2.1", 1)[0]
    pre_a_order = re.findall(r"^\| \*\*(A\d)\*\* \|", sec2, re.M)
    chk("§2 检查项顺序", pre_a_order == list(impl.CHECK_IDS),
        "预登记顺序 %s" % pre_a_order)

    # ---- 2. 判据 id 集合：预登记 §3 的表 ↔ 实现的 CRIT_IDS ----
    pre_h = set(re.findall(r"^\| \*\*(H\d)\*\* \|", pre, re.M))
    chk("§3 判据集合", pre_h == set(impl.CRIT_IDS),
        "预登记 %s vs 实现 %s" % (sorted(pre_h), sorted(impl.CRIT_IDS)))

    # ---- 3. 硬失败集合（手写期望）----
    chk("硬失败集合 == {H1,H2}", set(impl.HARD_FAIL_IDS) == {"H1", "H2"},
        "实现 %s" % (impl.HARD_FAIL_IDS,))

    # ---- 4. 形态级联顺序（手写期望 E→D→C→B→A）----
    body = impl_src.split("def verdict_from", 1)[1].split("def ", 1)[0]
    order = re.findall(r'return "([A-E])", failed', body)
    chk("形态级联顺序 == E,D,C,B,A", order == ["E", "D", "C", "B", "A"], "实现 %s" % order)
    chk("级联里 H7 落在 C（H5/H7 同类）", '"H5" in failed or "H7" in failed' in body.replace("(", " ").replace(")", " "),
        "实现里没有把 H7 与 H5 并列")

    # ---- 5. 内嵌模板 ↔ 244.89 预登记 §3.2 模板（逐字节）----
    conf_tmpl = [l for l in conf_pre.split("\n") if l.startswith("> 「『污染解释不了观测差』")]
    chk("内嵌模板 == §3.2 模板（逐字节）",
        len(conf_tmpl) == 1 and conf_tmpl[0] == impl.FIXTURE_TEMPLATE,
        "§3.2 有 %d 行" % len(conf_tmpl))

    # ---- 6/7/8. §2.1 的行 id、行形态、归属表 ↔ 实现 ----
    sec21 = pre.split("## §2.1", 1)[1].split("\n## ", 1)[0] if "## §2.1" in pre else ""
    shapes = dict(re.findall(r"^\| `(L_\w+)` \| `([^`]+)` \|$", sec21, re.M))
    chk("§2.1 的 7 个行 id", set(shapes.keys()) == {
        "L_verdict", "L_counts", "L_allbrk", "L_decbrk", "L_ci_traj", "L_ci_blk", "L_c_lo"},
        "§2.1 里有 %s" % sorted(shapes.keys()))
    src = impl.parse_source(LEDGER, CONF_PREREG)
    el = impl.expected_lines(src)
    chk("实现的行 id == §2.1 的行 id", set(el.keys()) == set(shapes.keys()),
        "实现 %s" % sorted(el.keys()))
    bad_shape = []
    for k, shp in shapes.items():
        prefix = shp.split("<")[0]
        if not el.get(k, "").startswith(prefix):
            bad_shape.append("%s：%r 不以 %r 开头" % (k, el.get(k, ""), prefix))
    chk("实现的行形态 == §2.1 的形态", not bad_shape, "；".join(bad_shape))
    # 归属表：§2.1 的「七行 ↔ 九个检查项」分工
    owner_rows = re.findall(r"^\| \*\*(A\d)\*\* \| (.+?) \|$", sec21, re.M)
    chk("§2.1 的归属表覆盖 A1..A9", [a for a, _ in owner_rows] == list(impl.CHECK_IDS),
        "§2.1 %s" % [a for a, _ in owner_rows])

    # ---- 9. §5 的变异覆盖 ↔ 变异台 ----
    mut_src = read(MUT)
    mut_ids = set(re.findall(r'\("(MU\d+)"', mut_src))
    cover = [
        ("把形态改掉", ["MU11", "MU13", "MU25"]),
        ("把 4/12 改成别的", ["MU02", "MU29"]),
        ("把三个下端点之一改掉", ["MU04"]),
        ("把违例清单删一条", ["MU05", "MU22"]),
        ("把 B-14 改回未量到", ["MU06"]),
        ("把逐字引用句改一个字", ["MU26"]),
        ("把复算入口删掉", ["MU08"]),
        ("把行号挪走", ["MU07", "MU09"]),
        ("把已入库改回待收尾", ["MU27"]),
        ("把无出处数检查改成恒真", ["MU14", "MU15"]),
        ("把检查的比较表达式改成恒真", ["MU01", "MU16", "MU21"]),
        ("把硬失败集合从常量派生", ["MU12", "MU13"]),
    ]
    miss = [name for name, ids in cover for i in ids if i not in mut_ids]
    chk("§5 的 12 项变异覆盖都有对应的变异条", not miss, "缺 %s" % miss)
    n_mut = len(re.findall(r'\("MU\d+"', mut_src))
    chk("变异台条数 ≥ 26", n_mut >= 26, "实际 %d 条" % n_mut)

    # ---- 10. 复算入口 id（§2.1）↔ 实现 ↔ 页面 ----
    need_rc = ("RC-8a", "RC-8b", "RC-8c")
    impl_rc = re.findall(r'need_rc = \(([^)]*)\)', impl_src)
    chk("实现要求的复算入口 == RC-8a/b/c",
        len(impl_rc) == 1 and all(('"%s"' % r) in impl_rc[0] for r in need_rc),
        "实现 %s" % impl_rc)
    page_rc = set(re.findall(r"^\| \*\*(RC-\d+[a-z]?)\*\* \|", page, re.M))
    chk("页面在案 RC-8a/8b/8c", all(r in page_rc for r in need_rc), "页面 %s" % sorted(page_rc))

    # ---- 11. §2.2 的「改前 ⇒ 改后」两次运行 ↔ 驱动脚本 ----
    drv = read(DRIVER)
    chk("驱动脚本有 before/after 两次 --data", drv.count("--data") >= 2,
        "驱动里 --data 出现 %d 次" % drv.count("--data"))
    chk("驱动脚本调用了变异台/互证/对账",
        all(k in drv for k in ("mut_doc_consistency_audit.py", "_cross_check_24492.py",
                               "_spec_crosscheck_24492.py")), "")

    # ---- 12. 页面必须真的引用了本轮的形态/口径 ----
    chk("页面提到 244.89", "244.89" in page, "")
    chk("页面提到 §6.7 可对账块", "## 6.7 " in page, "")

    print("──── 对账逐条 ────")
    for x in bad:
        print("[RED] %s" % x)
    print("对账条数：OK %d ｜ 红 %d" % (ok, len(bad)))
    print("===== SPEC_KEYS =====")
    print("SPEC_OK=%d" % ok)
    print("SPEC_RED=%d" % len(bad))
    print("SPEC_RC=%d" % (0 if not bad else 1))
    print("===== END_SPEC_KEYS =====")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
