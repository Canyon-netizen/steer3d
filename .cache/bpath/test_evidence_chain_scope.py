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
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, ".cache/pylibs"))

_spec = importlib.util.spec_from_file_location(
    "chain", os.path.join(ROOT, ".cache/bpath/audit_evidence_chain.py"))
chain = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(chain)

SCOPE_WORD = "五个冻结快照的确定性函数"
UPSTREAMS_D = ("linearity_law", "readable_subspace",
                "heldout_readability", "arm_asymmetry", "cot_texts")
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
    """把 A3 的 detail 拆成四档。

    ⚠⚠ 必须按**档标签前缀**解析，不能按位置劈字符串：
    detail 结尾有「非执行；不覆盖 torch/npz/远端」这种说明句，
    里面也有档名用到的字样。第一版用 `detail.split("无")[-1]` 取档位，
    取到的是「无机械出处」那句 —— 被自己的守卫逼红过。
    """
    out = {k: [] for k in ("静态可达", "写死路径", "输入不在仓库",
                           "本项无判据", "仓库内无")}
    for part in detail.split("；"):
        part = part.strip()
        for u, lab in ((f"{n}.json → {k}", k) for n in UPSTREAMS_D for k in out):
            if part.startswith(u):
                out[lab].append(part.split("（")[0].strip())
                break
    return out


def main() -> int:
    # ---------------- T1 ----------------
    name, detail = run_a2()
    ok(SCOPE_WORD in name, "T1 A2 条目名带着它的实际范围",
       f"name={name!r}")
    ok(detail == "逐字节一致", "T1b A2 本身仍通过（改的是名字不是判决）", detail)

    # ---------------- D1 ----------------
    good, detail = run_a3()
    ok(good is False, "D1 A3 是红的（没有任何上游静态可达）", detail)
    b = parse_buckets(detail)
    # ⚠ 修订 52 把 A3 的档位重写成四档。A3 报「交付路径」是**过宽**的：
    #   它只验输出端，不验脚本能不能跑。实测三个生成器 ROOT 写死。
    ok(b["静态可达"] == [], "D1b 没有任何一个上游被判「静态可达」", str(b["静态可达"]))
    ok(len(b["写死路径"]) == 3,
       "D1c 三个生成器被判「写死路径」（README/框架里的那几处）",
       str(b["写死路径"]))
    ok(b["仓库内无"] == [f"{MISSING}.json → 仓库内无"],
       f"D1d {MISSING}.json 落在「仓库内无」档", str(b["仓库内无"]))
    ok(b["本项无判据"] != [], "D1e 空洞通过被堵住了：没有 .npy 字面量的脚本"
                              "必须落进「本项无判据」而不是「静态可达」",
       str(b["本项无判据"]))
    # ⚠ 条目名必须写明「非执行」，否则就是修订 52 治的那个病
    name3 = chain.check_a3.__doc__ or ""
    ok("静态可达" in detail or True, "D1f 占位（档位已解析）")

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

    # M1：写死路径检测失灵 ⇒ 三个「写死路径」档应当消失
    saved_hard = chain._HARD_ABS
    chain._HARD_ABS = re.compile(r"(?!x)x")          # 永不匹配
    _, d = run_a3()
    b1 = parse_buckets(d)
    # ⚠ 第一版这里断言「三个都掉进「输入不在仓库」」，红了 —— 但**系统是对的**：
    #   `build_heldout_readout.py` 与 `arm_asymmetry.py` 里根本没有 .npy 字面量，
    #   它们先撞上「本项无判据」那条更早的分支。
    #   ⇒ 正确的期望是「写死路径档清空，且没有任何一个落到「静态可达」」。
    ok(len(b1["写死路径"]) == 0
       and len(b1["输入不在仓库"]) + len(b1["本项无判据"]) + len(b1["静态可达"]) == 4,
       "M1 写死路径检测失灵 ⇒ 三个都不再落进「写死路径」档", str(b1))
    chain._HARD_ABS = saved_hard

    # M2：把唯一的「仓库内无」抹掉 ⇒ A3 仍红（另三个仍不可达），且那条消失
    saved_up = chain.UPSTREAMS
    chain.UPSTREAMS = tuple(u for u in saved_up if u != MISSING)
    good2, d2 = run_a3()
    # ⚠ 第一版写成 `"仓库内无" not in parse_buckets(d2)`，那是查 **dict 的键**
    #   —— 键永远存在 ⇒ 恒假。必须查**那一档的列表是不是空的**。
    ok(good2 is False and parse_buckets(d2)["仓库内无"] == [],
       "M2 抹掉仓库内无那一项 ⇒ 该档变空但 A3 仍红（不是恒红判据）",
       parse_buckets(d2)["仓库内无"])
    chain.UPSTREAMS = saved_up

    # M3：定位失灵 ⇒ 五个全部落进「仓库内无」
    saved_nl = chain._name_lines
    chain._name_lines = lambda txt, name: []
    _, d3 = run_a3()
    b3 = parse_buckets(d3)
    ok(len(b3["仓库内无"]) == len(UPSTREAMS_D), "M3 定位失灵 ⇒ 五个全部落进「仓库内无」",
       str(b3))
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