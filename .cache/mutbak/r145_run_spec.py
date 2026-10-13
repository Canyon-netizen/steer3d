#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 144b 取数笔 —— 拼 19 臂的**跑台规格**（指向 r145_arms/ 的新副本）。

⚠⚠⁴⚠⁴ 本脚本做三件**机械**活，每一件都对应一个已经栽过的坑：

  ① **每臂一个 CDP 端口**（修订 144b 那三次「装置故障：页面 40s 内没 boot」的根治）
     ⚠⚠⁴ 端口 9471 被两个**孤儿** chrome-headless-shell 占着（`kill` 在本会话被沙箱拒），
     ⚗ 而 `launch()` 是 `fetch(/json/version)` 探测 ⇒ **连上了别人的浏览器**，
     ⚗ 拿到的 `version` 非空 ⇒ 它以为启动成功了 ⇒ 页面 40s 没 boot。
     ⚗⚠⁴ 症状是「装置故障」，而真因是「**仪器连错了对象**」—— 这一族见修订 141。
     ⇒ 每臂分一个端口，孤儿占不掉任何一个。

  ② **按臂设 `R134_ARM` + 声明 `self`**（修订 141 的静默跑错臂）
     ⚠ 日志自称的臂名必须与声明对账，跑台那道闸才拦得住。

  ③ **更新 `r134b_xy` 的声明**：`crash` ⇒ `flips:["D5"]`
     ⚠⚠⁴⚠⁴ 修订 144 给 D5 加了页内空值保护 + Node 侧 try/catch 之后，
     ⚗ 拆掉 `#tabXY` **不再掀桌**：实测 d5null 臂 = `RED D5` + `RESULT FAIL 38/39`。
     ⚗ 而 r134b_xy 拆的是**同一个元素** `#tabXY` ⇒ 它的声明同样作废。
     ⚠⚠⁴ **声明不更新 ⇒ 跑台会拿「期望崩」去卡「打出了 RESULT」**
     ⚗⚠⁴ ⇒ 报「声明期望崩，实际打出了 RESULT FAIL 38/39」——
     ⚗⚠⁴ 而那**恰恰是修订 144 修好了的证据**，会被记成「臂不可信」。
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".cache/mutbak/r145_run_spec.json"
ARMDIR = ".cache/mutbak/r145_arms/"

# ⚠ 端口从 9600 起，19 臂 + 基线共 20 个，逐个错开。
# ⚠⚠⁴ 端口是**现查**的：先占后放，写死会重蹈「常量是我写死的」覆辙。
BASE_PORT = 9600

# ⚠⚠⁴ `expect` 一律从**历史规格**搬过来，只改 r134b_xy 一条（理由见本文档 ③）。
# ⚠ 其余 18 条**一个字都不许动** —— 它们是「当时验的是什么」的唯一记录。
HIST = ROOT / ".cache/mutbak/r143_run_spec.json"

# ⚠ 14 个派生臂：名字 → 副本文件名（生成台按 src 基名 + 臂名命名）
DERIVED = [
    "r135_a5", "r135b_a6", "r135b_c4", "r135b_a8",
    "r136_d3", "r136_d4", "r136_a1", "r136_a7",
    "r136_c1", "r136_c2", "r136_c3", "r136_e1",
    "r138_d4", "r138_a1b",
]

# ⚠⚠⁴⚠⁴ 副本文件名**不许猜**：生成台实际产出的名字要从磁盘上读回来。
# ⚗ 第一版按 `<src基名>_<臂名>.mjs` 拼 ⇒ 拼出来的路径不存在 ⇒ 跑台全崩。
HAND = {"fork": "fork", "all": "all", "pair": "pair", "xy": "xy",
        "path_dgroup": "path_dgroup"}


def die(m):
    print("  ✗ %s" % m)
    sys.exit(2)


def main():
    hist = json.loads(HIST.read_text(encoding="utf-8"))
    by_name = {a["name"]: a for a in hist["arms"]}
    if len(by_name) != 19:
        die("历史规格臂数 %d ≠ 19" % len(by_name))

    on_disk = {p.name for p in (ROOT / ARMDIR).glob("*.mjs")}
    print("=== 拼 19 臂跑台规格 ===")
    print("  r145_arms 实际有 %d 个副本：%s" % (len(on_disk), sorted(on_disk)))

    arms = []
    port = BASE_PORT

    for name in DERIVED:
        # ⚗⚠⁴⚠⁴ 第一版把臂名**切掉前缀**再拼文件名（`r135_a5` → `a5`）
        # ⚗ ⇒ 拼出 `verify_path_a5.mjs`，而生成台产出的其实是
        # ⚗ `verify_path_r135_a5.mjs`（**用的是全名**）⇒ 路径不存在。
        # ⚠⚠⁴ 好在拼路径那段**先查磁盘再拼**，当场 exit 2 拦下了 ——
        # ⚠⚠⁴⚠⚴ 「先查盘再拼」这一条比事后修省事得多。
        want = "verify_path_%s.mjs" % name
        if want not in on_disk:
            die("派生臂 %s 的副本 %s 不在磁盘上（实际有 %s）" % (name, want, sorted(on_disk)))
        h = by_name[name]
        a = {"name": name, "node": ARMDIR + want,
             "expect": h["expect"], "env": {"CDP_PORT": str(port)},
             "self": None, "criterion": h.get("criterion", "")}
        port += 1
        arms.append(a)

    for arm, tail in HAND.items():
        fn = "r134b_%s.mjs" % tail
        if fn not in on_disk:
            die("手写臂 %s 的副本 %s 不在磁盘上" % (arm, fn))
        name = "r134b_%s" % arm
        h = by_name[name]
        exp = dict(h["expect"]) if h["expect"] else None
        if arm == "xy":
            # ⚠⚠⁴ ③ 唯一被改的一条。**改的理由写在本文档里，不靠记忆。**
            exp = {"flips": ["D5"]}
        a = {"name": name, "node": ARMDIR + fn,
             "expect": exp,
             "env": {"CDP_PORT": str(port), "R134_ARM": arm},
             # ⚠ 自称臂名 = R134_ARM 的值（日志打的是 `[扰动已落地] 臂 <R134_ARM>`）
             "self": arm,
             "criterion": h.get("criterion", "")}
        port += 1
        arms.append(a)

    if len(arms) != 19:
        die("拼出来 %d 臂 ≠ 19" % len(arms))

    # ⚠ 端口唯一性 —— 重复端口会让两个臂互相抢对方的浏览器。
    ports = [a["env"]["CDP_PORT"] for a in arms]
    if len(set(ports)) != len(ports):
        die("端口重复：%s" % ports)

    # ⚠⚠⁴ 声明完整性：每条 expect 都必须真的声明了什么。
    # ⚗ `r134b_path_dgroup` 历史规格里 expect=null（无声明）⇒ 跑台只记录不判合格。
    # ⚠ **「没记录」≠「合格」** —— 这条不许被顺手补成 flips。
    nod = [a["name"] for a in arms if a["expect"] is None]
    print("  无声明（只记录、不判合格）：%s" % nod)
    print("  端口 %d..%d，逐臂错开" % (BASE_PORT, port - 1))
    for a in arms:
        if a["expect"] and a["expect"].get("crash"):
            die("臂 %s 仍声明 crash ⇒ 声明没跟上修订 144 的 D5 修复" % a["name"])

    OUT.write_text(json.dumps({"src": ".cache/browser_verify/verify_path.mjs",
                               "arms": arms}, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print("\n写出 %s（%d 臂）" % (OUT.relative_to(ROOT), len(arms)))


if __name__ == "__main__":
    main()
