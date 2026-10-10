#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 48 守卫：证据链的**条目名覆盖范围**，与第二层欠账。

三件事，每一件都有变异台架：

**T1** A2 的条目名必须带着它的实际范围（「仅：重跑==五个冻结快照的确定性函数」）。
  修订 48 之前它叫「阶梯产物可复算」，而它验的只是
  「重跑 `build_evidence_ladder.py` 的输出 == 交付文件」。名字比判据宽 ⇒
  读者会以为阶梯里的数字能从干净克隆重造出来。名字改回去，这里就红。

**D1** A3 必须**红**，且红的原因必须**恰好是 `cot_texts.json` 一个**。
  ⚠ 这里钉的不是「必须红」这个结论，而是**红的粒度**：如果哪天
  `cot_texts` 的生成器被 track 进来，A3 应当转绿；如果另外四份退化回
  「只写本地副本」，A3 也应当改变说法。两个方向都要能变。

**D2/D3** 检测器本身的牙齿：
  · 阳性对照 —— `arm_asymmetry` 必须找得到仓库内生成器
    （否则 A3 只是一条**恒红**判据，和恒绿一样没用）；
  · 反向锚点 —— `build_evidence_ladder.py` 是这五份产物的**消费者**，
    它自己也写盘且五个名字全都在文件里；它**绝不能**被判成其中任何一份的生成器。
    第一版检测器正是漏了这一条（写条件不带名字），把 4/5 个真实生成器报成 0 个。

用法：
    PYTHONPATH=.cache/pylibs python3 .cache/bpath/test_evidence_chain_scope.py
"""
from __future__ import annotations

import importlib.util
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, ".cache/pylibs"))

_spec = importlib.util.spec_from_file_location(
    "chain", os.path.join(ROOT, ".cache/bpath/audit_evidence_chain.py"))
chain = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(chain)

SCOPE_WORD = "五个冻结快照的确定性函数"
# 这四个的生成器确实在仓库内且写的就是交付那份（2026-10-11 实测逐条核对过）
FOUND = ("linearity_law", "readable_subspace", "heldout_readability",
         "arm_asymmetry")
MISSING = "cot_texts"
CONSUMER = ".cache/xcheck/build_evidence_ladder.py"

fails: list[str] = []


def ok(cond, label, detail=""):
    print(f"[{'通过' if cond else '**失败**'}] {label}" + (f"  —— {detail}" if detail else ""))
    if not cond:
        fails.append(label)
    return cond


def run_a2() -> tuple[str, str]:
    chain.results = []
    chain.check_a2()
    name, _, detail, _ = chain.results[-1]
    return name, detail


def run_a3() -> tuple[bool, str]:
    chain.results = []
    chain.check_a3()
    _, good, detail, _ = chain.results[-1]
    return good, detail


def parse_buckets(detail: str) -> dict[str, list[str]]:
    """把 A3 的 detail 拆成三档。

    ⚠ 第一版用 `detail.split("无")[-1]` 取「无」那一档，红了。
      错因：detail 结尾「⇒ 阶梯的**无**机械出处」里还有一个「无」，
      `[-1]` 取到的是那一句，不是档位。**按位置劈字符串**去猜档位，
      在这种「档名本身是常用词」的文本上必然劈错。
      ⇒ 改成按**档标签前缀**解析，并且只认 `标签 + 空格` 开头的段。
    """
    out = {"交付路径": [], "本地副本": [], "仓库内无": []}
    for part in detail.split("；"):
        for lab in out:
            if part.startswith(lab + " "):
                body = part[len(lab) + 1:].split(" ⇒")[0]
                items = [x.strip() for x in body.split("、") if x.strip()]
                out[lab] = [x for x in items if x != "（空）"]
    return out


def main() -> int:
    # ---------------- T1 ----------------
    name, detail = run_a2()
    ok(SCOPE_WORD in name, "T1 A2 条目名带着它的实际范围",
       f"name={name!r}")
    ok(detail == "逐字节一致", "T1b A2 本身仍通过（改的是名字不是判决）", detail)

    # ---------------- D1 ----------------
    good, detail = run_a3()
    ok(good is False, "D1 A3 是红的（cot_texts 的生成器确实不在仓库内）", detail)
    b = parse_buckets(detail)
    ok(set(b["交付路径"]) == {f"{u}.json" for u in FOUND},
       "D1b 四份的生成器都落在「交付路径」档", str(b["交付路径"]))
    ok(b["本地副本"] == [], "D1d 「本地副本」档已清空",
       "linearity_law.py 修订 48 已改成默认写交付路径")
    ok(b["仓库内无"] == [f"{MISSING}.json"],
       f"D1c 欠账恰好一条：{MISSING}.json", str(b["仓库内无"]))

    # ---------------- D2 阳性对照 ----------------
    gen = chain.generator_of("arm_asymmetry")
    ok(gen is not None, "D2 检测器能找到真实的仓库内生成器（非恒红）", str(gen))
    ok(gen == ".cache/xcheck/arm_asymmetry.py", "D2b 找对了那一个", str(gen))

    # ---------------- D3 反向锚点 ----------------
    for u in chain.UPSTREAMS:
        hits = [r for r, _ in chain.writes_named_artifact(u)]
        ok(CONSUMER not in hits,
           f"D3 消费者 {CONSUMER.split('/')[-1]} 未被当成 {u} 的生成器",
           f"hits={hits}")

    # ---------------- 变异台架 ----------------
    print("\n--- 变异（每条都必须让上面某条断言红）---")

    # M1：交付目录判据失灵 ⇒ 四个都退到「无」档
    saved_dir = chain.DELIVERED_DIR
    chain.DELIVERED_DIR = "frontend/public/latent/data/NOPE"
    _, d = run_a3()
    b1 = parse_buckets(d)
    ok(b1["交付路径"] == [],
       "M1 交付目录判据失灵 ⇒ 四份全部掉出「交付路径」档", str(b1))
    ok(set(b1["本地副本"]) == {f"{u}.json" for u in FOUND},
       "M1b 它们退到了「本地副本」档（判据变红而不是消失）")
    chain.DELIVERED_DIR = saved_dir

    # M2：把唯一的欠账从清单里拿掉 ⇒ A3 变绿（证明 A3 能变绿）
    saved_up = chain.UPSTREAMS
    chain.UPSTREAMS = tuple(u for u in saved_up if u != MISSING)
    good2, _ = run_a3()
    ok(good2 is True, "M2 欠账被抹掉 ⇒ A3 转绿（恒红判据被排除）")
    chain.UPSTREAMS = saved_up

    # M3：定位特征失灵（一个名字都找不到）
    saved_nl = chain._name_lines
    chain._name_lines = lambda txt, name: []
    _, d3 = run_a3()
    b3 = parse_buckets(d3)
    ok(b3["仓库内无"] == [f"{u}.json" for u in chain.UPSTREAMS],
       "M3 定位失灵 ⇒ 五个全部落进「无」档", str(b3))
    chain._name_lines = saved_nl

    # M4（打空是正确性质，必须写进用例）：写盘条件放宽会怎样
    saved_wc = chain._WRITE_CALL
    import re as _re
    chain._WRITE_CALL = _re.compile(r"^")
    hits_loose = [r for r, _ in chain.writes_named_artifact("linearity_law")]
    chain._WRITE_CALL = saved_wc
    ok(CONSUMER in hits_loose or hits_loose,
       "M4 写盘条件确实是承重的（放宽后定位到的集合改变）",
       f"放宽后 hits={hits_loose}；严格时 "
       f"{[r for r, _ in chain.writes_named_artifact('linearity_law')]}")

    # 收尾：全部恢复后再跑一遍，确认状态没被变异污染
    run_a2()
    good3, detail3 = run_a3()
    ok(good3 is False and f"{MISSING}.json" in detail3,
       "恢复后 A3 回到原始红态", detail3)

    print(f"\n{len(fails)} 条失败" + ("" if not fails else "：" + "、".join(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())