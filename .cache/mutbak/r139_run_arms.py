"""跑台：**基线 + 变异臂**一起跑，并把「落地两半 / 分母一致 / 只有目标判据翻面」做成硬门。

⚠⚠⚴ 为什么要有这个跑台（修订 134/136/138 各踩了一次）
  ① 修订 134：扰动把下拉框删成「只有一道题」⇒ D3 被判 `[SKIP]` ⇒ 我把它当成
     「真跳过」，而基线跑一次就能看出「基线本来就有 6 道题」——**假跳过**。
  ② 修订 136：d4 臂扰动改 `S.dv` ⇒ `RESULT OK 36/36` ⇒ 我一度以为 D4 没牙齿，
     而真因是**扰动改在这一屏不读的地方**。
  ③ 修订 138：预登记里写「基线仍是 OK 36/36」，引的却是**修订 136 的旧记录**。
     ⚠⚠⚴ 本轮自己跑出来才是硬的。⇒ **基线必须是本轮那次跑的，不能引旧记录。**

⚠⚠⚴ 跑台不做判定，只做**对账**：
  · 基线必须 `RESULT OK`（否则「扰动后转红」这句话根本无从谈起）
  · 每个臂的落地两半必须 before>0 且 after===0（修订 133：只判 after===0
    会在基线本就为 0 时**空洞成立**）
  · 分母必须与基线**相等**（修订 118：「跳过」不得进分母；两个数不是同一个量
    时必须钉口径）
  · 翻面的判据**必须与规格里声明的一致**，多一条少一条都算仪器不可信

⚠ 崩 / 红 / 绿 / 跳过 / 未落地 是**五种不同状态**，本跑台分开记，不合并。
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAT = "http://127.0.0.1:9006/latent/index.html"

RE_RESULT = re.compile(r"^RESULT\s+(OK|FAIL)\s+(\d+)/(\d+)\s*$")
RE_LANDED = re.compile(r"^\[扰动已落地\]\s*臂\s*(\S+?)：(\{.*\})\s*$")
RE_NOTLANDED = re.compile(r"^\[扰动未落地\]\s*臂\s*(\S+?)：(\{.*\})\s*$")
RE_RED = re.compile(r"^RED\s+(\S+)")
RE_SKIP = re.compile(r"^\[?SKIP\]?\s+(\S+)")


def run(node_script, log):
    # ⚠⚠⚴ 第一版把 PATH 写死成四个目录，跑台第一次跑就 `FileNotFoundError: node`。
    #   ⚗ 那是**仪器坏了**（不是被测物坏了）—— 两者必须分开判定。
    #   ⇒ 继承进程环境，只覆盖 LAT_URL。⚠ 自己拼 env 等于给自己造一个「缺东西」的世界。
    env = dict(os.environ)
    env["LAT_URL"] = LAT
    with open(log, "w", encoding="utf-8") as f:
        r = subprocess.run(["node", node_script], stdout=f, stderr=subprocess.STDOUT,
                           cwd=str(ROOT), env=env)
    return r.returncode


def parse(log):
    out = {"result": None, "ok": None, "total": None, "red": [], "skip": [],
           "landed": None, "notlanded": None, "tail": ""}
    lines = Path(log).read_text(encoding="utf-8", errors="replace").split("\n")
    for l in lines:
        m = RE_RESULT.match(l)
        if m:
            out["result"], out["ok"], out["total"] = m.group(1), int(m.group(2)), int(m.group(3))
        m = RE_RED.match(l)
        if m:
            out["red"].append(m.group(1))
        m = RE_SKIP.match(l)
        if m:
            out["skip"].append(m.group(1))
        m = RE_LANDED.match(l)
        if m:
            out["landed"] = (m.group(1), json.loads(m.group(2)))
        m = RE_NOTLANDED.match(l)
        if m:
            out["notlanded"] = (m.group(1), json.loads(m.group(2)))
    out["tail"] = "\n".join(l for l in lines if l.strip())[-400:]
    return out


def first_token(criterion):
    """从 criterion 文本里取判据代号（'D4 prod.problems…' → 'D4'）。"""
    m = re.match(r"^([A-Z]\d+[a-z]?)\b", criterion.strip())
    return m.group(1) if m else None


def check_baseline(b):
    """基线必须本轮绿且无跳过。⇒ 返回问题清单（空 = 过）。"""
    problems = []
    if b["result"] != "OK":
        problems.append(f"⚠⚠⚴ 基线不是 OK（{b['result']} {b['ok']}/{b['total']}）"
                        f"⇒ 「扰动后转红」这句话根本无从谈起，本轮不发数")
    if b["skip"]:
        problems.append(f"⚠⚠⚴ 基线就有 {len(b['skip'])} 条跳过：{b['skip']}"
                        f"⇒ 分母口径不干净")
    return problems


def check_arm(arm, a, b):
    """落地两半 + 分母一致 + 只翻声明的那一条。⇒ 返回问题清单（空 = 过）。"""
    name = arm["name"]
    want = first_token(arm.get("criterion", ""))
    why = []
    if a["notlanded"]:
        why.append(f"扰动未落地 {a['notlanded'][1]}")
    elif a["landed"]:
        ev = a["landed"][1]
        if ev.get("before", 0) <= 0:
            why.append(f"落地核验第一半不成立：before={ev.get('before')}")
        if ev.get("after", -1) != 0:
            why.append(f"落地核验第二半不成立：after={ev.get('after')}")
    else:
        why.append("日志里没有落地取证行")
    if a["result"] is None:
        why.append("无 RESULT 行（崩）")
    else:
        if b["total"] is not None and a["total"] != b["total"]:
            why.append(f"⚠⚠⚴ 分母与基线不一致：臂 {a['total']} vs 基线 {b['total']}")
        if len(a["red"]) != 1:
            why.append(f"⚠⚠⚴ 翻面判据 {len(a['red'])} 条，期望 1 条：{a['red']}")
        elif want and a["red"][0] != want:
            why.append(f"⚠⚠⚴ 翻面的是 {a['red'][0]}，规格声明的是 {want}")
    return want, why


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--src", default=None, help="基线用的判据（默认取 spec.src）")
    ap.add_argument("--outdir", default=".cache/mutbak/r139_run")
    args = ap.parse_args()

    spec = json.loads((ROOT / args.spec).read_text(encoding="utf-8"))
    outdir = ROOT / args.outdir
    outdir.mkdir(parents=True, exist_ok=True)

    # ---- 第 0 步：基线（⚠⚠⚴ 必须本轮跑，不许引旧记录）--------------------
    base_script = ROOT / (args.src or spec["src"])
    base_log = outdir / "baseline.log"
    run(str(base_script), str(base_log))
    b = parse(base_log)

    print("=== 基线（⚠ 本轮实跑，不引旧记录）===")
    print(f"  {b['result']} {b['ok']}/{b['total']}  红 {len(b['red'])} 跳过 {len(b['skip'])}"
          f"  日志 {base_log.relative_to(ROOT)}")

    problems = list(check_baseline(b))

    # ---- 第 1 步：逐臂 --------------------------------------------------
    rows = []
    for arm in spec["arms"]:
        name = arm["name"]
        node = outdir / f"{Path(spec['src']).stem}_{name}.mjs"
        # ⚠ 副本在 r13x_arms/ 里，跑台不复制，直接指向生成台产物
        cand = ROOT / spec["outdir"] / f"{Path(spec['src']).stem}_{name}.mjs"
        if cand.exists():
            node = cand
        log = outdir / f"{name}.log"
        run(str(node), str(log))
        a = parse(log)

        want, why = check_arm(arm, a, b)
        if why:
            problems.append(f"臂 {name}：{'；'.join(why)}")
        rows.append((name, want, a, why))

    print("\n=== 逐臂 ===")
    for name, want, a, why in rows:
        st = ("✅" if not why else "⚠")
        print(f"  {st} {name:<5} 期望翻面 {want or '?':<5} "
              f"实际 {a['result']} {a['ok']}/{a['total']}  红 {a['red'] or '[]'}  "
              f"落地 {a['landed'][1] if a['landed'] else a['notlanded'][1] if a['notlanded'] else '?'}")
        for w in why:
            print(f"      ⚠ {w}")

    print("\n=== 对账 ===")
    print(f"  基线分母 {b['total']} / 臂分母 {[r[2]['total'] for r in rows]}")
    if problems:
        print(f"\n[错误] {len(problems)} 条对账不过，本轮不发数：")
        for p in problems:
            print(f"  ⚠ {p}")
        sys.exit(2)
    print("  ✅ 基线绿 · 分母一致 · 落地两半成立 · 每臂只翻它声明的那一条")


if __name__ == "__main__":
    main()