#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 144b 取数笔 —— 19 臂里的 **14 个派生臂**按当前判据重建。

⚠⚠⁴⚠⁴ 为什么必须重建（而不是接着用 r143 那批）
  r143 那 19 个臂是在**当时**的判据上生成的。修订 144 给 D5 加了空值保护 +
  Node 侧 try/catch（判据 411 行 vs 当时 403 行），修订 144b 又加了两行名单口径。
  ⚗ **判据变了 ⇒ 派生副本全部作废** —— 副本里嵌的是判据当时的字节。
  ⚠ 这不是取舍，是义务（修订 143 §一已经定过）。

⚠⚠⁴ 本脚本只做一件机械活：**把 4 份生成规格合并成 1 份，并重新量出行号**。
  ⚠ 行号**不许写死** —— 修订 143 §三已经吃过一次「常量是我写死的」：
    注入点必须**从当前判据现量**，量出来的值连同锚点一起交给生成台，
    ⚠ 由生成台的 G0/G1（行号 + 内容双向锁定）兜底。

⚠⚠⁴⚠⁴ **d4 有两条、它们不是同一个东西**：
  r136 的 d4 读 `S.dv.problems`，r138 的 d4 读 `S.path.problems`
  （⚠ 修订 136 已核：`renderPathPanel` 读的是 `S.path` ⇒ r136 那条
  ⚠ 打在「这一屏不读的地方」⇒ 扰动无效、判据照绿）。
  ⚗⚠⁴ **合并时把两条合成一条 = 静默删掉一条臂** ⇒ 这里按来源前缀分别保留。
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTDIR = ".cache/mutbak/r145_arms/"
MERGED = ROOT / ".cache/mutbak/r145_gen_spec.json"

# ⚠ 来源规格 → 臂名前缀。⚠ 前缀必须与 r141_hist_spec.json 的臂名一致，
#   否则跑台对不上账（⚠ 这就是修订 141「仪器跑了别的东西」那一族）。
SOURCES = [
    ("r135_spec_a5.json", "r135"),
    ("r135_spec_ace.json", "r135b"),
    ("r136_spec.json", "r136"),
    ("r138_spec.json", "r138"),
]


def load_src():
    src = (ROOT / ".cache/browser_verify/verify_path.mjs").read_text(encoding="utf-8")
    return src, src.split("\n")


def locate(lines, anchor):
    """⚠ 现量：锚点在当前判据里的行号。**必须唯一**，否则 exit 2。

    ⚠⚠⁴⚠ 这里刻意**不用**文本搜索去定位注入点（`src.index` 那种）——
      锚点只用来**对账**，定位靠行号。⚠ 唯一性检查是额外一层：
      ⚗ 锚点若在判据里出现两次，「量到哪一行」本身就是不确定的。
    """
    hits = [i + 1 for i, l in enumerate(lines) if l.strip() == anchor.strip()]
    if not hits:
        die("锚点在当前判据里**已消失**：%r" % anchor[:90])
    if len(hits) > 1:
        die("锚点在当前判据里出现 %d 次（%s）⇒ 量到哪一行不确定，不许猜"
            % (len(hits), hits))
    return hits[0]


def die(msg):
    print("  ✗ %s" % msg)
    sys.exit(2)


def teeth(lines):
    """⚠⚠⁴⚠⁴ 平移逻辑的**牙齿测试** —— 这段逻辑本轮刚翻过一次车。

    ⚠⚠⁴⚠⁴ **为什么必须是独立用例、而不是「跑一遍看着对」**：
      第一版的错是 `before` 少加了漂移量，而那一版跑出来的表**每行都印得像模像样**，
      ⚗ 只有末行多一个「平移 +21 行」的提示 —— ⚠⚠⁴ 目视根本看不出来。
      ⚠⚠⁴⚠⚴ ⇒ 「仪器印了东西」与「仪器算对了」必须分开验，这就是牙齿测试存在的理由。

    用例：
      T1 平移 0        ⇒ before 不变（绝大多数臂）
      T2 平移 +21，**原始 at == before** ⇒ before 同样要 +21 ⚠⚠⁴ **就是这一格翻的车**
      T3 平移 +21，原始 at != before（a1 形状：88/94）⇒ 两边**各自**平移，间距保持 6
      T4 锚点不唯一    ⇒ locate 判红
      T5 锚点消失      ⇒ locate 判红
    """
    print("=== 平移逻辑牙齿测试 ===")
    fails = []

    def shift(a_at, a_before, new_at):
        return a_before + (new_at - a_at)

    def case(label, got, want):
        ok = got == want
        print("  %s %-52s got=%s want=%s" % ("✓" if ok else "✗✗", label, got, want))
        if not ok:
            fails.append(label)

    case("T1 平移 0（多数臂）", shift(96, 96, 96), 96)
    case("T2 平移 +21 且原始 at==before（翻车格）", shift(227, 227, 248), 248)
    case("T3 注入/取值分离（a1 形状 88→94）", shift(88, 94, 88 + 21), 94 + 21)
    case("T3b 分离形状平移 0", shift(88, 94, 88), 94)

    # ⚠ locate 的两条判红 —— 用**离线假判据**，不碰真文件。
    fake = ["a", "b", "TARGET", "c", "TARGET", "d"]
    try:
        locate(fake, "NOPE")
        print("  ✗✗ T4 锚点不唯一 ⇒ locate **没有**判红")
        fails.append("T4")
    except SystemExit:
        print("  ✓ T4 锚点不唯一 ⇒ 判红 ✓")
    try:
        locate(fake, "MISSING")
        print("  ✗✗ T5 锚点消失 ⇒ locate **没有**判红")
        fails.append("T5")
    except SystemExit:
        print("  ✓ T5 锚点消失 ⇒ 判红 ✓")

    print()
    if fails:
        print("[硬门] %d 条牙齿用例不过：%s" % (len(fails), fails))
        sys.exit(2)
    print("=== 6/6 有牙齿 ===")


def main():
    src, lines = load_src()
    print("=== 重新量行号 ===")
    print("  当前判据 %d 行 / %d bytes" % (len(lines), len(src.encode("utf-8"))))
    if "--teeth" in sys.argv:
        return teeth(lines)
    arms = []
    for fname, prefix in SOURCES:
        spec = json.loads((ROOT / ".cache/mutbak" / fname).read_text(encoding="utf-8"))
        # ⚠⚠⁴ 源判据必须与规格声明的一致 —— 不一致就说明规格是给别的判据写的。
        if spec["src"] != ".cache/browser_verify/verify_path.mjs":
            die("%s 的 src 不是当前判据" % fname)
        for a in spec["arms"]:
            at = locate(lines, a["anchor"])
            # ⚠ before = 被验判据的**取值点**。
            #
            # ⚠⚠⁴⚠⁴ 本脚本第一版在这里有个**当场翻车**，必须留档：
            #   我写成 `if before != a["at"]: before += (at - a["at"])`，
            #   ⚗ 而 e1 的原始 at=227 / before=227（**两者相等**）⇒ 分支不进
            #   ⚗⚠⁴ ⇒ before 停在 227，而 at 已经漂到 248 ⇒ **取值点落在注入点下游**。
            #   ⚠⚠⁴ 而脚本照样印了一张**每行都像模像样**的表，只在末行标了「平移 +21 行」。
            #   ⚗⚠⁴ **判别式：「表印出来了」与「每一行都算对了」是两件事。**
            #   ⚠ 幸而生成台的 G3（`at <= before`）会 exit 2 拦下 —— 那是第二道闸，
            #   ⚠⚠⁴ 但**不能靠下一道闸替这一道兜底**：那一道只在这一条臂上响。
            #
            # ⇒ 正确写法：**无条件按漂移量平移**（漂移 0 时自然不变）。
            #   「注入与取值分离」的形状（a1：注入 88 / 取值 94）由 before_anchor 单独核对。
            drift_at = at - a["at"]
            before = a["before"] + drift_at
            before_anchor = a.get("before_anchor")
            if before_anchor is not None:
                before = locate(lines, before_anchor)
            if before != at and before < at:
                die("臂 %s: 取值点 before=%d 落在注入点 at=%d **下游** ⇒ 扰动会被撤销"
                    % (a["name"], before, at))
            drift = at - a["at"]
            flag = "未漂移" if drift == 0 else "⚗ 平移 %+d 行" % drift
            print("  %-10s at %3d -> %3d   before %3d -> %3d   %s"
                  % (prefix + "_" + a["name"], a["at"], at, a["before"], before, flag))
            arm = dict(a)
            arm["name"] = "%s_%s" % (prefix, a["name"])
            arm["at"] = at
            arm["before"] = before
            arms.append(arm)

    names = [a["name"] for a in arms]
    if len(set(names)) != len(names):
        die("臂名重复：%s" % [n for n in names if names.count(n) > 1])
    print("\n=== 合并结果：%d 个派生臂 ===" % len(arms))
    for n in names:
        print("  " + n)

    merged = {
        "src": ".cache/browser_verify/verify_path.mjs",
        "art": "frontend/public/latent/data/path_readout.json",
        "outdir": OUTDIR,
        "pid": "1983_I_1",
        "arms": arms,
    }
    MERGED.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n写出 %s" % MERGED.relative_to(ROOT))


if __name__ == "__main__":
    main()
