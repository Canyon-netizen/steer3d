#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HINGE 判据：把「模型自己动摇的那一刻」定位到**具体 token 位置**。

判决规则全部在 `.cache/xcheck/HINGE_PREREG.md` 里，**取数之前**定死。
本文件是那份文件的实现，逐条照抄，**不许事后放宽词表**。

## 三支装置自检（先于任何真实数据）

    H-1 负控：20 段无自我怀疑的 CoT（含探索句/疑问句/引述题目）
            ⇒ 必须 0 个动摇点
    H-2 正控：20 段明确自查的文本 ⇒ 每个标记都必须标出，漏 1 条即红
    H-3 失效自检：5 段含 A/B 类字面词但不属于自查的串
            ⇒ 必须一条都不产出

## 真实语料

    H-4 动摇点总数 >= 100
    H-5 分布在 >= 15 条轨迹上（共 24）
    H-6 位置映射率 >= 90%

⚠ 与 P0 的区别：P0 判「算式对不上」，那 14 条逐条人工读后**全是假阳性**，
  因为 1.7B 的错误主要在假设层/题意层，不在算术层。本支找的是**模型
  自己说它可能错了**——不依赖模型会算对。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NPZ_DIR = os.path.join(ROOT, "datasets", "aime_qwen3_1p7b_16k_fp16", "aime")

# --------------------------------------------------------------------------
# §1 A/B 两类的字面标记。**照抄预登记，不许增删。**
# --------------------------------------------------------------------------
# A 类·自查：说要回头验自己已写的结论
_A = [
    r"Let me check again\.",
    r"Let me check\.",
    r"Let me check that\.",
    r"Wait,\s*let me check(?: again)?\.",
    r"But let me check again\.",
    r"But let me check once again\.",
    r"Let me think again\.",
    r"But let me think again\.",
    r"Wait,\s*no\.",
    r"Wait,\s*let me think again\.",
    r"Hmm\.",
    r"Hmm,\s*okay\.",
    r"let me verify",
    r"Let me verify each step again\.",
    r"Let me re-examine",
    r"reconsider",
    r"But let me check if",
    r"But hold on",
    r"Let me double-check",
    r"double check",
    r"Let me recalculate",
    r"Let me recompute",
    r"Let me check with another approach\.",
]
# B 类·自疑：直接说自己可能错了
_B = [
    r"maybe I miscalculated",
    r"maybe I misread the problem",
    r"maybe I made a mistake",
    r"I made a mistake",
    r"may have made a mistake",
    r"my assumption is wrong",
    r"my reasoning is wrong",
    r"maybe I made an error",
    r"maybe I did something wrong",
    r"there's a mistake in my",
]
# ⚠⚠ 第一版这里还有两条通配：`but maybe I` 和 `maybe my`。
#   人工读真实语料发现它们抓进来的全是**推进**不是**动摇**：
#     · "But maybe I don't need to worry about …"   免除
#     · "But maybe I can use the principle …"       想到新方法
#     · "But maybe I need to handle m=0 separately" 想到要补的边界
#     · "But maybe it's better to think in terms of…" 换更好的思路
#   ⇒ 「maybe + I」本身**不蕴含**自我怀疑，必须点明**怀疑的对象是我已写的东西**。
#   已删（见 HINGE_PREREG.md 修订 1）。
MARK_A = re.compile("|".join(_A), re.IGNORECASE)
MARK_B = re.compile("|".join(_B), re.IGNORECASE)

# §1 排除：引述题目 / 换措辞往前走 / 无标记困惑 / 疑问句
# ⚠⚠ 第一版 EXCLUDE 的模式锚在 `^` 上，只匹配「句首**恰好**是 the problem says」。
#   于是 `But hold on, the problem says "the total cost is at most $100".`
#   句首是 `But hold on`，整句绕过排除被判成 A 类 —— 人工读确认是**重读题目**，
#   不是自查。⇒ 排除必须看**整句里是否出现引述**，不是只看句首。
#   真实语料里这类句子至少 6 句（预登记 §1 表最后一行的判断是对的，
#   是实现没做到）。
EXCLUDE = re.compile(
    r"\bthe\s+(?:problem|question)\s+says\b"
    r"|\bit\s+says\b"
    r"|\bthe\s+(?:problem|question)\s+states\b"
    r"|^\s*(?:alternatively\s*,?\s*)?maybe\s+(?:we|i)\s+can\b"
    r"|^\s*let\s+me\s+try\b"
    r"|\bi\s+(?:can|could|will)\s+use\b"
    r"|\bit'?s\s+better\s+to\b",
    re.IGNORECASE)

# §1 句首 12 字符内必须出现的自我指涉开头
HEAD_OK = re.compile(
    r"^\s*(?:but\s+|so\s+|and\s+|also\s+|or\s+)*"
    r"(?:wait|hmm|let\s+me|let's|i|alternatively|but|so)\b",
    re.IGNORECASE)

_SENT = re.compile(r"[^.!?\n]+[.!?]")


def find_hinges(text: str):
    """返回 [(start, end, cls, sentence)]，cls ∈ {'A','B'}。"""
    out = []
    for m in _SENT.finditer(text):
        sent = m.group(0)
        cls = None
        if MARK_A.search(sent):
            cls = "A"
        elif MARK_B.search(sent):
            cls = "B"
        if cls is None:
            continue
        if EXCLUDE.search(sent):
            continue
        head = sent[:12]
        if not HEAD_OK.search(head):
            continue
        # 只取到标记结束处，避免整句都算进动摇点
        mm = (MARK_A if cls == "A" else MARK_B).search(sent)
        out.append((m.start() + mm.start(), m.start() + mm.end(), cls,
                    " ".join(sent.split())))
    return out


# --------------------------------------------------------------------------
# 自检
# --------------------------------------------------------------------------
NEG = [
    "Let me try that approach and see if it works.",
    "Alternatively, maybe we can find a relationship between h and r?",
    "Wait, the problem says \"each of whom has two brothers.\"",
    "But wait, the problem says \"the total cost is at most $100\".",
    "So, maybe we can substitute these into the product.",
    "This is confusing, but let me move on to the next case.",
    "Let me try using natural logarithms (ln) for simplicity.",
    "Therefore, maybe the lines are not both vertical?",
    "Alternatively, maybe we can find a value for r?",
    "First, maybe I can compute θ + φ first, then add ψ to it.",
    "Let me recall that log_z w = ln w / ln z.",
    "Hmm, how do I approach this?",
    "Wait, but they have to be parallel to the short side.",
    "Maybe we can use that to simplify expressions involving the cubes.",
    "Let me check the approximate values.",
    "So, maybe the shorter sides have no eyelets?",
    "Alternatively, maybe the formula is different.",
    "Let me think about how to approach this step by step.",
    "Hmm, maybe I can express ln x in terms of ln w?",
    "Maybe I can think of it as a problem of counting coprime pairs.",
]

POS = [
    "Wait, no.", "Wait, no.", "Let me check again.", "Wait, let me check again.",
    "Let me check.", "Let me check that.", "But let me check again.",
    "Let me think again.", "But let me think again.", "Hmm.",
    "Hmm, okay.", "Let me verify each step again.", "Let me re-examine this.",
    "Wait, maybe I miscalculated 1988 mod 625?",
    "But maybe I made a mistake here?", "Wait, maybe I misread the problem.",
    "But let me check once again.", "Wait, let me think again.",
    "But let me check if there are other constraints.",
]

# H-3：含 A/B 字面词但**不属于**自查
# ⚠⚠ 后六条是**真实语料里逐条读出来的**假阳性原句，不是构造的。
#   P0 修订 1 的教训：三支自检「全绿」而真实语料几乎全是假阳性，
#   根因是对照集只覆盖「我想象的失败形态」。这里必须用真句子。
FAILMODE = [
    "But wait, the problem says \"the sum of the solutions\".",
    "Let me try that approach.",
    "Hmm, how do I approach this?",
    "So, maybe we can substitute these into the product.",
    "Alternatively, maybe we can find a value for r?",
    # ↓ 真实语料的假阳性原句（人工逐条读确认）
    "But hold on, the problem says \"the total cost is at most $100\".",
    "But maybe I don't need to worry about the exact value of θ + φ.",
    "But maybe I can use the principle of inclusion-exclusion for coprimality.",
    "But maybe I need to handle m=0 and n=0 separately.",
    "But maybe it's better to think in terms of possible digits.",
    "But since the side length here is 4, the distance between opposite sides "
    "is 2*radius, but maybe I need to think about the number of points.",
]


def selfcheck() -> int:
    fails = []

    # H-1 负控：必须 0
    got = []
    for s in NEG:
        for h in find_hinges(s):
            got.append((s, h[3]))
    if got:
        fails.append(f"H-1 负控应 0 个，实际 {len(got)} 个：{got[:3]}")

    # H-2 正控：每个都必须标出
    miss = []
    for s in POS:
        if not find_hinges(s):
            miss.append(s)
    if miss:
        fails.append(f"H-2 正控漏标 {len(miss)}/{len(POS)}：{miss[:5]}")

    # H-3 失效自检：必须一条都不产出
    got3 = []
    for s in FAILMODE:
        for h in find_hinges(s):
            got3.append((s, h[3]))
    if got3:
        fails.append(f"H-3 应 0 个，实际 {len(got3)} 个：{got3[:3]}")

    print("=== 装置自检 ===")
    for name, ok in (("H-1 负控（不许误报）", not any(f.startswith("H-1") for f in fails)),
                     ("H-2 正控（不许漏报）", not any(f.startswith("H-2") for f in fails)),
                     ("H-3 失效自检（不许乱抓）", not any(f.startswith("H-3") for f in fails))):
        print(f"  {name:26s} {'PASS' if ok else 'FAIL'}")
    for f in fails:
        print(f"    ! {f}")
    return 1 if fails else 0


# --------------------------------------------------------------------------
# 真实语料
# --------------------------------------------------------------------------
def scan_corpus(with_pos: bool, limit=None):
    files = sorted(f for f in glob.glob(os.path.join(NPZ_DIR, "*.json"))
                   if f.endswith("__think.json"))
    if limit:
        files = files[:limit]

    tok = None
    if with_pos:
        # ⚠⚠ tokenizer 路径**不许 glob 猜**。第一版我去 `datasets/aime_*`
        #   底下 glob 模型目录，结果那里只有 `aime/` 和 `viewer_cache/`，
        #   载入失败只印一行 WARN，然后 H-6 被**静默跳过**、RESULT 照样 PASS。
        #   —— 正是 P0 骗了我两次的那个形态（「判据恒绿」）。
        #   现在：路径写死 + 载入失败直接 SystemExit，不许降级。
        #   与 p0_claims.py:412 同一条路径。
        path = os.path.join(ROOT, "datasets", "models", "Qwen3-1.7B")
        if not os.path.isdir(path):
            raise SystemExit(f"ABORT tokenizer 目录不存在：{path}")
        sys.path.insert(0, os.path.join(ROOT, ".cache", "pylibs"))
        from transformers import AutoTokenizer
        tok = AutoTokenizer.from_pretrained(path)

    rows, per_trace = [], {}
    tot, mapped = 0, 0
    for f in files:
        t = os.path.basename(f)[:-5]
        text = json.load(open(f, encoding="utf-8")).get("generated_text", "")
        hs = find_hinges(text)
        # ⚠ 用 `offset_mapping` 对齐，不用「tokenize 前缀再数长度」——
        #   后者要在同一个字符串上跑两次分词，且 O(n²)，前缀里的空格/换行
        #   归一化一旦与主编码不一致就会整体偏移。
        offs = None
        if tok is not None:
            offs = tok(text, return_offsets_mapping=True,
                       add_special_tokens=False)["offset_mapping"]
        items = []
        for (s, e, cls, sent) in hs:
            it = {"start": s, "end": e, "cls": cls, "sentence": sent}
            if offs is not None:
                hit = -1
                for i, (a, b) in enumerate(offs):
                    if a <= s < b or a < e <= b or (a <= s and e <= b):
                        hit = i
                        break
                # ⚠ 映射不上必须**如实留在分母里**。第一版这里
                #   只在 mapped 时计数，映射失败的那些悄悄消失了，
                #   map_rate 于是用「映射成功的」做分子**和**分母 —— 恒 100%。
                it["tok"] = hit
                it["mapped"] = hit >= 0
                mapped += 1 if hit >= 0 else 0
            items.append(it)
        per_trace[t] = len(items)
        tot += len(items)
        rows.append({"trajectory_id": t, "n": len(items), "hinges": items})

    n_with = sum(1 for v in per_trace.values() if v > 0)
    return {
        "n_traces": len(files),
        "n_hinges": tot,
        "n_traces_with_hinge": n_with,
        "n_mapped": mapped if tok is not None else 0,
        "map_rate": (mapped / tot) if (tot and tok is not None) else None,
        "per_trace": per_trace,
        "rows": rows,
        "prereg": "HINGE_PREREG.md",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-pos", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", default=os.path.join(ROOT, ".cache", "xcheck", "hinge.json"))
    ap.add_argument("--selfcheck", action="store_true")
    a = ap.parse_args()

    if a.selfcheck:
        return selfcheck()

    res = scan_corpus(not a.no_pos, a.limit)
    print(f"轨迹 {res['n_traces']}  动摇点 {res['n_hinges']}  "
          f"分布在 {res['n_traces_with_hinge']} 条")
    if res["map_rate"] is not None:
        print(f"位置映射 {res['n_mapped']}/{res['n_hinges']} = "
              f"{res['map_rate']*100:.1f}%")
    else:
        # ⚠⚠ 不许「跳过即通过」。本项目栽过：H-6 因 tokenizer 载入失败被
        #   跳过，汇总行照样印 RESULT PASS —— 6 条判决里其实只跑了 5 条。
        print("\nABORT 位置映射没跑（H-6 无法判决）。"
              "本判据不允许跳过；用 --no-pos 跑请自行忽略 H-6。")
        raise SystemExit(2)

    verdicts = [
        {"name": "H-4 动摇点 >= 100", "ok": res["n_hinges"] >= 100,
         "detail": f"{res['n_hinges']} 条（阈值 100）"},
        {"name": "H-5 分布在 >= 15 条轨迹", "ok": res["n_traces_with_hinge"] >= 15,
         "detail": f"{res['n_traces_with_hinge']} 条（阈值 15）"},
        {"name": "H-6 位置映射率 >= 90%", "ok": res["map_rate"] >= 0.90,
         "detail": f"{res['n_mapped']}/{res['n_hinges']} = {res['map_rate']*100:.1f}%"},
    ]
    res["verdicts"] = verdicts
    res["verdict"] = "PASS" if all(v["ok"] for v in verdicts) else "FAIL"

    json.dump(res, open(a.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print()
    for v in verdicts:
        print(f"  {'PASS' if v['ok'] else 'FAIL'}  {v['name']}  —— {v['detail']}")
    print(f"\nRESULT {res['verdict']}")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())