#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Z12–Z14 的变异台：证明导读骨架的三条新判据**真的能红**。

## 为什么必须有它

第三十三笔之十给导读浮层补了 10 个 `data-orient-part` 标记 + 三条新判据
（Z12 骨架完整 / Z13 不许空节 / Z14 四条论断都可达）。加完跑一次 53/53 绿。

**绿本身不构成证据。** 这个项目反复吃过的亏是：判据看着在判某件事，
实际那个量恒成立。⇒ 每条新判据都要有一条变异把它逼红。

## 三条变异各自证明什么

| 变异 | 删/改什么              | 期望红 | 证明的是 |
|---|---|--------|----------|
| M1  | 抽掉 `sec3` 的标记     | Z12 Z13 | 「每个小节都得有标记」+「sec 数量得是 5」 |
| M2  | 抽掉**两条** claim 标记 | Z12 Z14 | 「没有数字槽的那两条也必须被登记」 |
| M3  | 把小节三的编号改成「六」 | Z12     | **编号必须连续**（这一条 M1/M2 都碰不到） |

⚠ M3 是三条里唯一只有它能覆盖的性质 —— 删标记只能证明「有没有」，
  证明不了「对不对」。

## 四条纪律

1. **期望红必须命中** —— 逐条点名，不许只看「整体变红」。
2. **不许有额外红** —— 红的对象必须与期望集合**完全相同**。
3. **还原后逐字节比对 sha256** —— 「看起来改回去了」不算还原。
4. **每个变体先自检** —— html 变异也要确认没把文件改坏
   （`body_span` 吞掉右花括号那一课：装置坏了与判据没红同形）。
"""

import hashlib
import io
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path("/Users/zhourui/code/steer3d")
SRC = ROOT / "frontend/public/latent/index.html"
BAK = ROOT / "frontend/public/latent/index.html.mutbak"
LAT = "http://127.0.0.1:22208/latent/index.html"

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print("  [%s] %s" % ("PASS" if ok else "FAIL", name))
    if detail:
        print("         %s" % detail)


def sha256(path):
    h = hashlib.sha256()
    with open(str(path), "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def run_judge():
    p = subprocess.run(["node", str(ROOT / ".cache/browser_verify/verify_latent_prose.mjs")],
                       capture_output=True, text=True,
                       env={**os.environ, "LAT_URL": LAT})
    out = p.stdout + p.stderr
    fails = sorted(set(re.findall(r"^\[FAIL\] (Z\d+|W\d+|T\d+|U\d+|V\d+|Y\d+|X\d+|\d+)", out, re.M)))
    return fails, out


def apply_and_check(label, text, expect_red, base_sha):
    """写盘 → 自检 → 跑判据 → 逐条对红 → 还原。"""
    io.open(str(SRC), "w", encoding="utf-8").write(text)
    # 装置自检：变异后的 html 必须还是「一个完整的 orientation 浮层」，
    # 否则扫描崩掉 / 页面报错，输出上与「判据没红」一模一样。
    if text.count("<div id=\"orientation\"") != 1 or text.count("</div>") < 40:
        check("装置自检：%s 的变体没把页面改坏" % label, False,
              "orientation 块数 = %d、</div> 数 = %d ⇒ 变异坏了"
              % (text.count("<div id=\"orientation\""), text.count("</div>")))
        shutil.copy2(str(BAK), str(SRC))
        sys.exit(2)
    fails, out = run_judge()
    check("%s 期望红 %s，实到 %s" % (label, expect_red, fails),
          fails == sorted(expect_red),
          ("完全一致" if fails == sorted(expect_red)
           else "⚠ 红的对象对不上 —— 期望 %s" % sorted(expect_red)))
    for line in out.splitlines():
        if re.match(r"^\[(PASS|FAIL)\] Z1[2-4]", line):
            print("         " + line.strip()[:150])
    shutil.copy2(str(BAK), str(SRC))
    if sha256(SRC) != base_sha:
        print("         ⚠ 还原后 sha 不对，停止")
        sys.exit(2)


def main():
    pristine = io.open(str(SRC), encoding="utf-8").read()
    if not BAK.exists():
        shutil.copy2(str(SRC), str(BAK))
    base_sha = sha256(SRC)
    print("基线 sha256 = %s　（页面有 %d 个 data-orient-part）\n"
          % (base_sha[:16], pristine.count("data-orient-part")))

    fails, _ = run_judge()
    check("M0 基线：53/53 全绿，一条都不许红", fails == [],
          "红项 = %s（预期 []）" % fails)
    if fails:
        print("       ⚠ 基线就不绿 —— 下面的「有没有额外红」无从判起，停止。")
        return 2

    # ---- M1：抽掉 sec3 的标记 ----
    m1 = pristine.replace('<h2 data-orient-part="sec3">', "<h2>")
    check("M1 前提：确实只改到一处（sec3）", m1 != pristine and m1.count("data-orient-part") == 9,
          "变体里还剩 %d 个标记" % m1.count("data-orient-part"))
    apply_and_check("M1（抽掉 sec3 标记）", m1, ["Z12", "Z13"], base_sha)

    # ---- M2：抽掉两条 claim 标记 ----
    m2 = pristine.replace(' class="noitem" data-orient-part="claim"', ' class="noitem"')
    check("M2 前提：确实改到两处（两条 claim）",
          m2.count("data-orient-part") == 8
          and m2.count('class="noitem" data-orient-part') == 0,
          "变体里还剩 %d 个标记" % m2.count("data-orient-part"))
    apply_and_check("M2（抽掉两条 claim 标记）", m2, ["Z12", "Z14"], base_sha)

    # ---- M3：把小节三的编号改成「六」（跳号）----
    m3 = pristine.replace('data-orient-part="sec3">三 ·', 'data-orient-part="sec3">六 ·')
    check("M3 前提：确实只改了编号（标记一个都没少）",
          m3 != pristine and m3.count("data-orient-part") == 10,
          "变体里还有 %d 个标记" % m3.count("data-orient-part"))
    apply_and_check("M3（小节编号 三→六，标记不动）", m3, ["Z12"], base_sha)

    # ---- 收尾 ----
    now = sha256(SRC)
    check("M4 收尾：页面 sha256 回到基线（逐字节相同）", now == base_sha,
          "还原后 %s vs 基线 %s" % (now[:16], base_sha[:16]))
    if BAK.exists():
        os.remove(str(BAK))
    check("M5 收尾：没有 .mutbak 残留", not BAK.exists(),
          "无残留" if not BAK.exists() else "⚠ %s 还在" % BAK.name)

    bad = [n for n, ok, _ in results if not ok]
    print("\n%s　%d/%d 条通过%s"
          % ("RESULT FAIL" if bad else "RESULT PASS",
             len(results) - len(bad), len(results),
             ("　红：" + "、".join(bad)) if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
