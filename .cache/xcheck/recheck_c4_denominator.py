"""从**原始探针产物**独立重算 C4 的分母，与已入库的判决对账。

⚠ 为什么需要这个文件
──────────────────
修订 148 把 `.cache/mutbak/r148_run/panel_coverage.log` 入库了，
但两份探针产物（481 KB）**没有**入库 —— 它们躺在探针的**默认**输出路径上
（`probe_panels.mjs:24-25`：不设 `PROBE_OUT` 就写那一个路径），
任何一次忘了设 `PROBE_OUT` 的探针跑都会顶掉它们。

⚠⚠⚴⚠ 本脚本是那半个缺口的补法：让「已入库的判决」能被第三方重算。

⚠⚠⚴⚠ 本脚本**自己拒绝**在不可信的前提下出数字（修订 149 §149.2 的教训）：
  ⚗ 产物过期            ⇒ 拒绝（age >= 7200）
  ⚗ 产物被换掉          ⇒ **拒绝**（不匹配下面硬编码的指纹，见 FINGERPRINT）
  ⚗ 产物跑错页          ⇒ 拒绝（自报 page 不符）
  ⚗ 产物缺字段          ⇒ 拒绝
⇒ 它宁可印「拒绝出数字」，也**绝不拿一份身份不明的产物算出一个看起来正常的数**。

用法：  python3 .cache/xcheck/recheck_c4_denominator.py
退出码：0 = 对上账；2 = 拒绝出数字（原因会印出来）；3 = 对不上（是账或产物变了）
"""

import io
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROOT_BLOCKS = ROOT / ".cache/browser_verify/panel_blocks.json"
LAT_BLOCKS = ROOT / ".cache/browser_verify/panel_blocks_latent.json"

MAX_AGE = 7200          # 与 scan_panel_coverage.py 的 C0 同一个窗口
FRAMEWORK_INTERNAL = {"data-precedence"}   # 判据 C1 剔除的那一个

# ⚠⚠⚴⚠⚠ 指纹：修订 148 那次扫描所依据的产物的规模。
# ⚠⚠ 这一段**必须**是写死的常量，而不是「现算现比」——
# ⚠⚠ 现算现比等于没有指纹：产物被顶掉后，任何规模都「自洽」。
# ⚗⚠ 当探针或页面真的变了、这个指纹该更新时，
# ⚗⚠ 正确的做法是**改这里并写进预登记**，而不是让脚本自己放宽。
FINGERPRINT = {
    "root":   {"blocks": 542, "markers": 354, "page": "root"},
    "latent": {"blocks": 183, "markers": 38,  "page": "latent"},
}
EXPECTED_TOTAL = 390    # 账本 line 76 印的「两页合计 390 个标记」


def die(code, why, fix=None):
    print("⚠ 拒绝出数字（退出码 %d）：%s" % (code, why))
    if fix:
        for line in fix:
            print("   → %s" % line)
    raise SystemExit(code)


def markers_of(raw):
    """两遍（加载后 / 点遍控件后）的**并集**才是这一页真实的标记面。
    ⚠⚠ 只用第一遍的话，按需渲染的块会被记成「源码里有、页面上没有」—— 那是假红。"""
    return set(raw.get("beforeNames") or []) | set(raw.get("afterNames") or [])


def block_count(raw):
    by_depth = raw.get("byDepth") or {}
    return sum(len(v) for v in by_depth.values())


def load(path, tag):
    if not path.exists():
        die(2, "产物不存在：%s" % path.name, [
            "两页都要跑，顺序有讲究（改完页面 → 起服务 → 逐页跑探针）：",
            "  BV_URL=<根>/ node .cache/browser_verify/probe_panels.mjs",
            "  BV_URL=<根>/latent/index.html PROBE_OUT="
            "…/panel_blocks_latent.json node .cache/browser_verify/probe_panels.mjs",
            "⚠ 跑第二遍时**别忘了换 PROBE_OUT** —— 忘了它会覆盖根页那份。",
        ])
    age = time.time() - path.stat().st_mtime
    if age >= MAX_AGE:
        die(2, "产物已过期：%s（%.0f 秒前，窗口 %d 秒）" % (path.name, age, MAX_AGE), [
            "⚠ 过期**不等于**坏了：这份测量可能是对的，只是放久了。",
            "  重跑探针即可，不必先怀疑页面。",
        ])
    try:
        raw = json.load(io.open(str(path), encoding="utf-8"))
    except ValueError as exc:
        die(2, "产物不是合法 JSON：%s（%s）" % (path.name, exc))

    want = FINGERPRINT[tag]
    if raw.get("page") != want["page"]:
        die(2, "%s 自报 page=%r，应为 %r —— **跑错页**了"
            % (path.name, raw.get("page"), want["page"]))

    marks = markers_of(raw)
    blocks = block_count(raw)
    # ⚠⚠⚴ 这两道才是真正挡「产物被换掉」的闸。字段齐全那一类检查
    # ⚠⚠⚴ 一份**被顶掉的**产物同样全过（它也是一份合法产物）。
    if len(marks) != want["markers"] or blocks != want["blocks"]:
        die(2, "%s 规模对不上指纹 —— ⚠⚠⚴ **它很可能已经被顶掉了**\n"
               "        现测 %d 个标记 / %d 个块；修订 148 那次是 %d 个标记 / %d 个块"
            % (path.name, len(marks), blocks, want["markers"], want["blocks"]), [
            "最可能的原因：某次探针跑**没设 PROBE_OUT**，写到了默认路径上",
            "（probe_panels.mjs:24-25）。**对照实验尤其容易踩** ——",
            "它换了 WebGL 模式，却很可能没换输出路径。",
            "⚠ 若探针/页面确实变了，就该改本文件里的 FINGERPRINT 并写进预登记，",
            "⚠⚠ 而**不是**让脚本自己放宽 —— 放宽的指纹等于没有指纹。",
        ])
    return raw, marks, blocks, age


def main():
    print("=== 从原始产物独立重算 C4 分母（对账对象：.cache/mutbak/r148_run/panel_coverage.log）===\n")
    sets, rows = {}, []
    for tag, path in (("root", ROOT_BLOCKS), ("latent", LAT_BLOCKS)):
        raw, marks, blocks, age = load(path, tag)
        sets[tag] = marks
        rows.append((tag, path.name, len(marks), blocks, age))
        print("[%s] %-24s %3d 个标记 / %3d 个块 / %.0f 秒前 / page=%s"
              % (tag, path.name, len(marks), blocks, age, raw.get("page")))

    r, l = sets["root"], sets["latent"]
    both = r | l
    shared = r & l
    cleaned = both - FRAMEWORK_INTERNAL

    print("\n--- 口径演算（每一步都印出来，不允许跳步）---")
    print("  root + latent（**相加**）      = %d + %d = %d" % (len(r), len(l), len(r) + len(l)))
    print("  两页交集（同一个标记两页都有）  = %d  %s" % (len(shared), sorted(shared) or ""))
    print("  并集 = 相加 − 交集              = %d − %d = %d" % (len(r) + len(l), len(shared), len(both)))
    print("  剔除框架内部属性 %-18s = %d − %d = %d"
          % (sorted(FRAMEWORK_INTERNAL), len(both), len(FRAMEWORK_INTERNAL), len(cleaned)))
    print("\n  ⚠⚠⚴ 注意口径：账本那个数是**并集**，不是相加。")
    print("  ⚠⚠⚴ 相加会把两页共有的 %d 个标记算两次，分母就虚高了。" % len(shared))

    print("\n=== 对账 ===")
    print("  脚本算出 = %d" % len(cleaned))
    print("  账本印的 = %d" % EXPECTED_TOTAL)
    if len(cleaned) != EXPECTED_TOTAL:
        print("\n❌ **对不上**（退出码 3）：要么账本变了，要么产物变了。")
        print("   ⚠⚠⚴ 两者的差别不是「差 1 个数」，是「其中一个已经不是你以为的那个东西」。")
        raise SystemExit(3)
    print("  ✅ **逐位对上** —— 修订 148 入库的那份判决，其分母可被独立复算。")
    print("\n⚠ 这一句对账能成立，靠的是上面两道指纹检查 ——")
    print("⚠⚠ 换成一份同样字段齐全、同样新鲜、但已被顶掉的产物，它会**拒绝出数字**。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
