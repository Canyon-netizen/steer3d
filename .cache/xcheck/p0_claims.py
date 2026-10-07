#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P0 阶段：把「思维链里哪个数算错了」定位到**具体 token 位置**。

判决规则全部写在 `.cache/xcheck/P0_PREREG.md` 里，**取数之前**定死。
本文件是那份文件的实现，逐条照抄，不许事后放宽解析范围。

⚠ 与本项目之前那些探针最大的不同：这一支**不碰模型**，纯 CPU、纯标准库
  （位置映射那一步要用 tokenizer，那是唯一需要 torch/transformers 的地方，
  可用 `--no-pos` 关掉）。

## 三支装置自检（先于任何真实数据）

    P0-1 负控：30 条**算术正确**的声称 ⇒ 必须 0 条被判错
    P0-2 正控：同一批，结果改成错值 ⇒ 必须 30/30 全被判错
    P0-3 失效自检：5 条「像算式但不可验证」的串 ⇒ 必须一条都不产出声称

⚠ 这三支的顺序不能换，且正控必须走**与负控完全相同的输入路径**
  —— 之前本项目栽过：负控的替换串用了 dedent 之前的缩进，压根没匹配上，
  于是「负控通过」是因为它根本没跑。
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
# 算式词法：只认这些。别的字符一律是边界。
# --------------------------------------------------------------------------
# ⚠ 千分位逗号必须成组：`\d+(?:,\d{3})*`。
#   第一版写的是 `[\d,]+`，它会把 `850,` 里的**句末逗号**当成数字的一部分，
#   于是尾部检查看到的是 ` so 1×28…`、判成「不是完整结果」——
#   正控因此漏掉一条，而真实语料里带逗号的数字全被静默丢掉。
_NUM = r"\d+(?:,\d{3})*(?:\.\d+)?"
_SUP = {"²": 2, "³": 3}
# ⚠ `×` 是 U+00D7，与 ASCII `x` 是**两个字符**。第一版这里只写了 `xX`，
#   于是往回扫算式时一遇到 `×` 就断，`31×31` 只取到 `31` ——
#   负控当场报 `computed=31.0`。负控就是为这类字符级错误准备的。
_ALLOWED = set("0123456789,+-.xX*/÷×·() \t²³")

T_NUM = "N"
T_OP = "O"
T_POW = "P"          # ² / ³（跟在**右括号**之后的那个）
T_LP = "("
T_RP = ")"

# 乘法记号：x / X / * / × / · ；除法：/ ÷
_MUL = {"x", "X", "*", "×", "·"}
_DIV = {"/", "÷"}


def _lex(s: str):
    """把算式串切成 N/O/( / ) 记号流；遇到非法字符立刻停。"""
    out, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c in " \t":
            i += 1
            continue
        if c == "(":
            out.append((T_LP, c)); i += 1; continue
        if c == ")":
            out.append((T_RP, c)); i += 1
            # `(5-3)²`：平方记号跟在**右括号**后面。第一版只在数字后处理，
            # 于是这一类算式被判成「不可解析」而被静默丢掉。
            if i < n and s[i] in _SUP:
                out.append((T_POW, _SUP[s[i]])); i += 1
            continue
        m = re.match(_NUM, s[i:])
        if m:
            txt = m.group(0)
            j = i + len(txt)
            # 平方/立方记号
            if j < n and s[j] in _SUP:
                out.append((T_NUM, float(txt.replace(",", "")) ** _SUP[s[j]]))
                i = j + 1
            else:
                out.append((T_NUM, float(txt.replace(",", ""))))
                i = j
            continue
        if c in _MUL:
            out.append((T_OP, "*")); i += 1; continue
        if c in _DIV:
            out.append((T_OP, "/")); i += 1; continue
        if c in "+-":
            out.append((T_OP, c)); i += 1; continue
        return None                      # 非法字符 ⇒ 整个串不是纯算式
    return out


def _eval_toks(toks):
    """递归下降求值。**整个记号流必须被吃干净**，否则返回 None。"""
    pos = 0

    def peek():
        return toks[pos][0] if pos < len(toks) else None

    def expr():                          # 加减
        nonlocal pos
        v = term()
        if v is None:
            return None
        while peek() == T_OP and toks[pos][1] in "+-":
            op = toks[pos][1]; pos += 1
            r = term()
            if r is None:
                return None
            v = v + r if op == "+" else v - r
        return v

    def term():                          # 乘除
        nonlocal pos
        v = atom()
        if v is None:
            return None
        while peek() == T_OP and toks[pos][1] in "*/":
            op = toks[pos][1]; pos += 1
            r = atom()
            if r is None:
                return None
            if op == "*":
                v = v * r
            else:
                if r == 0:
                    return None           # 除零 ⇒ 不可验证
                v = v / r
        return v

    def atom():
        nonlocal pos
        if pos >= len(toks):
            return None
        t, v = toks[pos]
        base = None
        if t == T_NUM:
            base = v; pos += 1
        elif t == T_LP:
            pos += 1
            base = expr()
            if base is None or pos >= len(toks) or toks[pos][0] != T_RP:
                return None
            pos += 1
        elif t == T_OP and v in "+-":    # 一元正负号
            pos += 1
            base = atom()
            if base is None:
                return None
            base = base if v == "+" else -base
        else:
            return None
        while pos < len(toks) and toks[pos][0] == T_POW:
            base = base ** toks[pos][1]; pos += 1
        return base

    val = expr()
    if val is None or pos != len(toks):
        return None
    return val


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= max(1e-9, abs(b) * 1e-9)


# --------------------------------------------------------------------------
# 声称抽取：形如  <算式>  =  <数>       （也认 is / gives / equals）
# --------------------------------------------------------------------------
_EQWORD = re.compile(r"(?:(?<=\s)|(?<=^))(is|equals?|gives)(?=\s+\(?-?[\d,])", re.I)

# 声称的**结果**必须是一个完整的数。
# ⚠⚠ 第一版只要求「= 后面有个数」，于是
#     `5/120 + 3/120 = 8/120` 被读成「结果 = 8」，与真值 0.0667 一比就成了一条
#     「算错」—— 24 条轨迹里 94 条「错」里绝大多数是这种**假阳性**。
#   所以：数的**后面**不能紧跟运算符/括号/等号，否则那只是更长表达式的前缀。
_RES = re.compile(r"\s*\(?\s*(-?\d+(?:,\d{3})*(?:\.\d+)?)\s*\)?")
_RES_TAIL_OK = re.compile(r"[\s]*([.,;:!?)\]]|$)")


def _read_result(text: str, at: int):
    """读 `at` 处的声称结果。返回 (值, 结束下标)；不是完整结果则 None。

    ⚠ 「完整」的标准是：**这个数后面只能跟终止标点**。
      第一版只检查「后面是不是运算符」，于是 `= (8 ln w)/120` 里的 `8`
      被当成完整结果（后面跟的是字母 `l`）—— 又是一条假阳性。
    """
    m = _RES.match(text, at)
    if not m:
        return None
    # ⚠ 只看**紧随其后的第一个非空白字符**。
    #   中间一版用了 fullmatch（要求剩余全文都是终止标点），结果真实语料
    #   直接掉到 0 条声称 —— `868 + 1 = 869. Then add …` 后面全是正文。
    if not _RES_TAIL_OK.match(text, m.end()):
        return None                      # `8/120`、`3/(-1)`、`8 ln w` 都不是单个结果
    return float(m.group(1).replace(",", "")), m.end()


def _lhs_before(eq_at: int, text: str, max_back: int = 80) -> tuple[str, int] | None:
    """从 `=` 往前取最长的一段纯算式，返回 (算式串, 起点下标)。"""
    lo = max(0, eq_at - max_back)
    buf = []
    for i in range(eq_at - 1, lo - 1, -1):
        c = text[i]
        if c not in _ALLOWED:
            break
        buf.append(c)
    if not buf:
        return None
    s = "".join(reversed(buf))
    base = eq_at - len(s)
    # 逐个去掉左边的字符，直到剩下的整段能被干净求值
    for k in range(len(s)):
        cand = s[k:]
        toks = _lex(cand)
        if toks and _eval_toks(toks) is not None:
            return cand, base + k
    return None


def extract_claims(text: str):
    """返回 [{start,end,lhs,stated,computed,ok}]，`ok=False` 即「这个数算错了」。"""
    claims = []
    n = len(text)
    i = 0
    while i < n:
        c = text[i]
        if c == "=":
            lhs = _lhs_before(i, text)
            res = _read_result(text, i + 1)
            if lhs and res:
                expr_s, start = lhs
                toks = _lex(expr_s)
                val = _eval_toks(toks) if toks else None
                if val is not None:
                    stated, end = res
                    claims.append({
                        "start": start, "end": end, "lhs": expr_s.strip(),
                        "stated": stated, "computed": val,
                        "ok": _close(val, stated),
                    })
                i = res[1]
                continue
            i += 1
            continue
        wm = _EQWORD.match(text, i)
        if wm:
            lhs = _lhs_before(wm.end(), text)
            res = _read_result(text, wm.end())
            if lhs and res:
                expr_s, start = lhs
                toks = _lex(expr_s)
                val = _eval_toks(toks) if toks else None
                if val is not None:
                    stated, end = res
                    claims.append({
                        "start": start, "end": end, "lhs": expr_s.strip(),
                        "stated": stated, "computed": val,
                        "ok": _close(val, stated),
                    })
                i = res[1]
                continue
            i = wm.end()
            continue
        i += 1
    return claims


def dedup(claims):
    """同一轨迹里同一个 (算式, 结果) 重复书写只留一次 —— 模型常把同一段
    计算在「探索」和「复核」里各写一遍，不去重会系统性高估错误数。"""
    seen, out = set(), []
    for c in claims:
        k = (c["lhs"].replace(" ", ""), round(c["stated"], 6))
        if k in seen:
            continue
        seen.add(k)
        out.append(c)
    return out


# --------------------------------------------------------------------------
# 装置自检（预登记 P0-1 / P0-2 / P0-3）
# --------------------------------------------------------------------------
# 覆盖四则、链式、括号、千分位、平方、负数 —— 每一条**算术上都是对的**
GOOD = [
    ("So 31×31 = 961.", 961.0),
    ("Then compute 3×31 = 93.", 93.0),
    ("So 961 - 93 = 868.", 868.0),
    ("Then add 1: 868 + 1 = 869.", 869.0),
    ("First compute 31×30 = 930.", 930.0),
    ("Then 29×28 = 812.", 812.0),
    ("30×28 = 840, so 1×28 = 28.", 840.0),
    ("so total 840 + 28 = 868.", 868.0),
    ("Add them together: 694,400 + 60,760 = 755,160.", 755160.0),
    ("31² = 961.", 961.0),
    ("Now -5 + 8 = 3.", 3.0),
    ("12 / 4 = 3.", 3.0),
    ("2 × (3 + 4) = 14.", 14.0),
    ("(100 + 50) / 5 = 30.", 30.0),
    ("7 - 2 - 3 = 2.", 2.0),
    ("2 + 3 × 4 = 14.", 14.0),
    ("100 / 5 / 2 = 10.", 10.0),
    ("1,000 - 1 = 999.", 999.0),
    ("0.5 + 0.25 = 0.75.", 0.75),
    ("9 × 9 = 81.", 81.0),
    ("100 - 99 = 1.", 1.0),
    ("6 × 7 = 42.", 42.0),
    ("144 / 12 = 12.", 12.0),
    ("8 + 8 + 8 = 24.", 24.0),
    ("5² = 25.", 25.0),
    ("10 - 4 × 2 = 2.", 2.0),
    ("(5 - 3)² = 4.", 4.0),
    ("81 / 9 = 9.", 9.0),
    ("13 + 29 = 42.", 42.0),
    ("1000 - 999 = 1.", 1.0),
]

# 看起来像算式但**不可验证** —— P0-3，一条都不许产出声称
NOT_VERIFIABLE = [
    "First, let me compute the product 31×30×29×28.",
    "n(n-1)(n-2)(n-3) = (n²-3n)(n²-3n + 2).",
    "Let me try 930×812. Hmm, that's going to be a big number.",
    "868×870 = 868×(800 + 70) = 868×800 + 868×70.",
    "Maybe 31×30×29×28 + 1 = some perfect square?",
    # ↓ 下面两条是**人工抽查时才发现的**那一类误报，加进来是对照集的**加强**，
    #   不是放宽：分式链的右边不是「一个数」，按 P0_PREREG §1 本就不算声称。
    #   漏了它，正控/负控都测不出「只匹配前导整数」这个 bug ——
    #   第一版正是栽在这里，24 条轨迹里报出 94 条「错」，绝大多数是这种假阳性。
    "Convert to common denominator 120: 5/120 + 3/120 = 8/120 = 1/15.",
    "(5 ln w)/120 + (3 ln w)/120 = (8 ln w)/120 = (ln w)/15.",
    # ↓↓ 这三条是**真实语料跑完之后人工读**才发现的第三批假阳性形态。
    #   它们不是「不可验证」，是**会被误判成算错**：往回扫的边界一旦撞上
    #   变量/函数名/同余号/脱字符，就只截到前面那个纯数字，于是
    #   `φ(s) + 1 = 2`、`floor(299/2) = 149`、`10^6 = 11,232,000`
    #   全被读成「左边算出来只有 2 / 2 / 6」⇒ 假阳性。
    #   ⚠ 补进对照集之后如果 P0-3 转红，那说明**装置自检之前全绿这件事
    #     本身就是不够的** —— 负控没覆盖真实语料里出现过的形态。
    "For s=1, φ(1)=1, so φ(s) + 1 = 2, which matches.",
    "The number of terms is floor(299/2) = 149.",
    "So 11.232 * 10^6 = 11,232,000.",
    "The squares mod 16 are: 0²=0, 1=1, 2=4, 3=9, 4=0, 5=25≡9.",
]


def selfcheck(verbose=True):
    R = []

    def rec(name, ok, detail):
        R.append((name, ok))
        if verbose:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}\n         {detail}")

    # P0-1 负控：正确的必须一条都不被判错
    fp = []
    for s, want in GOOD:
        for c in extract_claims(s):
            if not c["ok"]:
                fp.append((s.strip()[:46], c["stated"], c["computed"]))
    rec("P0-1 负控：30 条算术正确的声称，0 条误报",
        not fp, f"共 {len(GOOD)} 条输入；误报 {len(fp)} 条" + (f"：{fp[:3]}" if fp else ""))

    # P0-2 正控：**同一批**，结果改错 ⇒ 必须全中
    import random
    rnd = random.Random(20261007)
    fn = []
    made = 0
    for s, want in GOOD:
        bad = s.replace(str(int(want)) if float(want).is_integer() else str(want),
                        str(int(want) + rnd.choice([1, 2, 5, 7, 10])), 1)
        if bad == s:
            continue
        made += 1
        hits = [c for c in extract_claims(bad) if not c["ok"]]
        if not hits:
            fn.append(bad.strip()[:46])
    rec("P0-2 正控：同一批把结果改错，30/30 全被抓出",
        made > 0 and not fn,
        f"构造 {made} 条错值声称；漏报 {len(fn)} 条" + (f"：{fn[:3]}" if fn else ""))

    # P0-3 失效自检：不可验证的串，一条声称都不许产出
    over = []
    for s in NOT_VERIFIABLE:
        cs = extract_claims(s)
        if cs:
            over.append((s.strip()[:40], len(cs)))
    rec("P0-3 失效自检：5 条不可验证串，0 条假声称",
        not over, f"共 {len(NOT_VERIFIABLE)} 条；误产出 {len(over)} 条"
        + (f"：{over[:3]}" if over else ""))
    return R


# --------------------------------------------------------------------------
# 真实语料
# --------------------------------------------------------------------------
def scan_corpus(with_pos: bool, limit: int | None = None):
    files = sorted(f for f in glob.glob(os.path.join(NPZ_DIR, "*.json"))
                   if f.endswith("__think.json"))
    if limit:
        files = files[:limit]

    tok = None
    if with_pos:
        os.environ.setdefault("PYTHONPATH", os.path.join(ROOT, ".cache", "pylibs"))
        sys.path.insert(0, os.path.join(ROOT, ".cache", "pylibs"))
        from transformers import AutoTokenizer
        tok = AutoTokenizer.from_pretrained(os.path.join(ROOT, "datasets", "models", "Qwen3-1.7B"))

    rows, per_trace = [], []
    for f in files:
        d = json.load(open(f, encoding="utf-8"))
        text = d.get("generated_text") or ""
        raw = extract_claims(text)
        dd = dedup(raw)
        wrong_raw = [c for c in raw if not c["ok"]]
        wrong = [c for c in dd if not c["ok"]]

        mapped = 0
        if tok is not None and dd:
            enc = tok(text, return_offsets_mapping=True, add_special_tokens=False)
            offs = enc["offset_mapping"]
            for c in dd:
                for a, b in offs:
                    if a <= c["start"] < b or a < c["end"] <= b or (a <= c["start"] and c["end"] <= b):
                        c["tok"] = offs.index((a, b))
                        mapped += 1
                        break
        per_trace.append({
            "trajectory_id": d.get("trajectory_id"),
            "is_correct": d.get("is_correct"),
            "n_claims_raw": len(raw), "n_claims_dedup": len(dd),
            "n_wrong_raw": len(wrong_raw), "n_wrong_dedup": len(wrong),
            "n_mapped": mapped,
        })
        rows.append({"trajectory_id": d.get("trajectory_id"), "claims": dd})

    tot_claims = sum(p["n_claims_dedup"] for p in per_trace)
    tot_wrong = sum(p["n_wrong_dedup"] for p in per_trace)
    tot_raw = sum(p["n_claims_raw"] for p in per_trace)
    tot_wrong_raw = sum(p["n_wrong_raw"] for p in per_trace)
    tot_mapped = sum(p["n_mapped"] for p in per_trace)
    n_with_wrong = sum(1 for p in per_trace if p["n_wrong_dedup"] > 0)
    return {
        "n_traces": len(per_trace),
        "n_claims_raw": tot_claims if False else tot_raw,
        "n_claims_dedup": tot_claims,
        "n_wrong_raw": tot_wrong_raw,
        "n_wrong_dedup": tot_wrong,
        "n_traces_with_wrong": n_with_wrong,
        "n_mapped": tot_mapped,
        "map_rate": (tot_mapped / tot_claims) if tot_claims else 0.0,
        "per_trace": per_trace, "rows": rows,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-pos", action="store_true", help="跳过 token 位置映射")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", default=os.path.join(ROOT, ".cache", "xcheck", "p0_claims.json"))
    ap.add_argument("--examples", type=int, default=8)
    a = ap.parse_args()

    print("P0 装置自检（先于任何真实数据）")
    R = selfcheck()
    print()
    print("P0 真实语料（think 轨迹）")
    res = scan_corpus(with_pos=not a.no_pos, limit=a.limit)

    P04 = res["n_wrong_dedup"] >= 200
    P05 = res["n_traces_with_wrong"] >= 12
    P06 = (not a.no_pos) and res["map_rate"] >= 0.90
    print(f"  轨迹 {res['n_traces']} 条")
    print(f"  可验证声称：原始 {res['n_claims_raw']} 条 → 去重后 {res['n_claims_dedup']} 条")
    print(f"  其中验出错：原始 {res['n_wrong_raw']} 条 → 去重后 **{res['n_wrong_dedup']}** 条")
    print(f"  含错误的轨迹 {res['n_traces_with_wrong']}/{res['n_traces']} 条")
    if not a.no_pos:
        print(f"  token 位置映射率 {res['map_rate']*100:.1f}%（{res['n_mapped']}/{res['n_claims_dedup']}）")
    print()
    verdicts = [
        ("P0-4 可定位错误位置 ≥ 200", P04, f"{res['n_wrong_dedup']} 条（阈值 200）"),
        ("P0-5 分布在 ≥ 12 条轨迹", P05, f"{res['n_traces_with_wrong']} 条（阈值 12）"),
        ("P0-6 位置映射率 ≥ 90%", P06 if not a.no_pos else True,
         "跳过（--no-pos）" if a.no_pos else f"{res['map_rate']*100:.1f}%"),
    ]
    for name, ok, detail in verdicts:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}  —— {detail}")
    allok = all(r[1] for r in R) and all(v[1] for v in verdicts)
    print()
    print(f"RESULT P0  {'PASS' if allok else 'FAIL'}  "
          f"{sum(1 for r in R if r[1]) + sum(1 for v in verdicts if v[1])}/"
          f"{len(R) + len(verdicts)} 条通过")

    out = {k: v for k, v in res.items()}
    out["selfcheck"] = [{"name": n, "ok": o} for n, o in R]
    out["verdicts"] = [{"name": n, "ok": o, "detail": d} for n, o, d in verdicts]
    out["verdict"] = "PASS" if allok else "FAIL"
    out["prereg"] = "P0_PREREG.md"
    json.dump(out, open(a.out, "w"), ensure_ascii=False, indent=1)
    print(f"已写出 {a.out}")

    # 人工抽查：把判错的算式连同上下文印出来
    if a.examples:
        print(f"\n  抽查 {a.examples} 条判错算式（**必须人工读**，自动抽取可能读错语境）：")
        shown = 0
        for row in res["rows"]:
            for c in row["claims"]:
                if c["ok"]:
                    continue
                text = json.load(open(os.path.join(
                    NPZ_DIR, row["trajectory_id"] + ".json"), encoding="utf-8")).get("generated_text", "")
                s, e = max(0, c["start"] - 40), min(len(text), c["end"] + 20)
                print(f"    · …{text[s:e].strip()}…")
                shown += 1
                if shown >= a.examples:
                    break
            if shown >= a.examples:
                break
    return 0 if allok else 1


if __name__ == "__main__":
    raise SystemExit(main())
