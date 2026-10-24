#!/usr/bin/env python3
"""N-A 结论页措辞守卫（标准库；不读数据库、远端或模型）。

默认检查真实结论页；--selftest 用临时 Markdown 调用同一 CLI，验证退出码。
--fixture NAME 单独运行合成正/负控，例如 --fixture assert_clean 返回 1。
rc=0: 通过；rc=1: 文档判红；rc=2: 输入错误或自检失败。

这是保守的词法守卫，不是任意自然语言的语义证明。全文检查目标词，
只豁免局部、明确的否定/未量到/识别假设；不因同一行出现“不许”而放行整行。
新措辞需增加相应正负控。数字及 B′ 的其他边界不属于本守卫。
"""

import argparse
from pathlib import Path
import re
import subprocess
import sys
import tempfile


DEFAULT_DOCUMENT = Path(__file__).resolve().parents[1] / "docs/BPATH_VERDICT.md"
MEANING = "rand臂的边际改判率没有可检出的高于零假设"
CLAIM = r"(?:无污染|没有污染|干净|污染不存在|不存在污染)"
SUBJECT = r"(?:(?:对照臂|rand臂)(?:是|已被证明)?(?:完全)?)?"
QUOTED = rf"「{SUBJECT}{CLAIM}」"
# 每个豁免只覆盖它所限定的命题，后面的新断言仍会被检查。
SAFE_PATTERNS = [
    rf"(?:不是|不等于|不能说|不得写成|不得称为|不许写成|不许说成|不应写成|不应说成)「?{SUBJECT}{CLAIM}」?",
    rf"{QUOTED}(?:⛔)?(?:尚未量到|未量到|未被证实)",
    # Markdown 边界表：命题单元格紧接证据强度单元格，仅保护命题部分。
    rf"\|{QUOTED}(?:/{QUOTED})*\|⛔?未量到",
    # 6.4.1 B-15：条件假设不等于观测。缺失“未独立验证”即不豁免。
    r"识别假设：「rand臂在无污染时的改判率＝零假设基准」\|⛔?未在本轮独立验证",
]


def normalize(text):
    """去除强调、代码标记与空白，同时保留原始行号（包括软换行）。"""
    chars, lines = [], []
    for number, line in enumerate(text.splitlines(), 1):
        for char in line:
            if not char.isspace() and char not in "*`":
                chars.append(char)
                lines.append(number)
    return "".join(chars), lines


def check(text):
    normalized, lines = normalize(text)
    errors = []
    if "N-A" not in normalized:
        errors.append((1, "NA_MISSING", "缺少 N-A 判决标识"))
    if MEANING not in normalized:
        errors.append((1, "NA_MEANING", "缺少含边际与可检出限定的 N-A 正面读法"))
    if not re.search(r"^#{1,6}\s+[^\n]*边界清单", text, re.M):
        errors.append((1, "NA_BOUNDARY", "缺少正式边界清单标题"))
    safe = [match.span() for pattern in SAFE_PATTERNS
            for match in re.finditer(pattern, normalized)]
    for match in re.finditer(CLAIM, normalized):
        if not any(start <= match.start() and match.end() <= end for start, end in safe):
            errors.append((lines[match.start()], "NA_OVERCLAIM",
                           "未被局部否定或未量到限定的措辞：" + match.group()))
    return errors


def fixtures():
    base = ("## 边界清单\nN-A：rand 臂的**边际**改判率"
            "**没有可检出的**高于零假设。\n")
    cases = {
        "clean": (base + "⛔ 不是「无污染」。\n", None),
        "prohibition": (base + "⛔ 不许写成「对照臂干净」。\n", None),
        "unmeasured": (base + "「没有污染」**未量到**。\n", None),
        "boundary_table": (base + "| B-01 | 「对照臂干净」/「污染不存在」 | ⛔ 未量到 |\n", None),
        "conditional": (base + "| B-15 | 识别假设：「rand 臂在无污染时的改判率 ＝ 零假设基准」 | ⛔ 未在本轮独立验证 |\n", None),
        "assert_clean": (base + "N-A 说明对照臂干净。\n", "NA_OVERCLAIM"),
        "assert_none": (base + "因此没有污染。\n", "NA_OVERCLAIM"),
        "assert_zero": (base + "结论：无污染。\n", "NA_OVERCLAIM"),
        "mixed_sentence": (base + "不是「无污染」，但对照臂干净。\n", "NA_OVERCLAIM"),
        "mixed_table": (base + "| 「对照臂干净」 | ⛔ 未量到；现在证明没有污染 |\n", "NA_OVERCLAIM"),
        "unrelated_negation": (base + "不许改数字；N-A 表明无污染。\n", "NA_OVERCLAIM"),
        "unrelated_unknown": (base + "污染精确幅度未量到；N-A 说明没有污染。\n", "NA_OVERCLAIM"),
        "quoted_assertion": (base + "结果就是「无污染」。\n", "NA_OVERCLAIM"),
        "code_assertion": (base + "```text\nN-A：干净\n```\n", "NA_OVERCLAIM"),
        "wrapped_assertion": (base + "没有\n污染。\n", "NA_OVERCLAIM"),
        "emphasis_assertion": (base + "对照臂**干净**。\n", "NA_OVERCLAIM"),
        "missing_marginal": (base.replace("**边际**", ""), "NA_MEANING"),
        "missing_detectability": (base.replace("可检出的", ""), "NA_MEANING"),
        "missing_boundary": (base.replace("## 边界清单\n", ""), "NA_BOUNDARY"),
        "missing_verdict": (base.replace("N-A", "N-B"), "NA_MISSING"),
        "empty": ("", "NA_MISSING"),
    }
    return cases


def selftest():
    failed = positive = negative = 0
    with tempfile.TemporaryDirectory(prefix="na-boundary-") as folder:
        path = Path(folder) / "verdict.md"
        for name, (text, expected_code) in fixtures().items():
            path.write_text(text, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--document", str(path)],
                capture_output=True, text=True, timeout=10)
            expected_rc = 1 if expected_code else 0
            ok = result.returncode == expected_rc and (
                expected_code is None or expected_code in result.stdout)
            failed += not ok
            positive += expected_rc == 0
            negative += expected_rc == 1
            print(f"{'PASS' if ok else 'FAIL'} {name}: expected_rc={expected_rc} actual_rc={result.returncode}")
            if not ok:
                print(result.stdout + result.stderr)
    print(f"正控={positive} 负控={negative} FAIL={failed}; 子进程 rc=0 绿 / rc=1 红")
    print(f"SELFTEST_RC={2 if failed else 0}")
    return 2 if failed else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--selftest", action="store_true")
    mode.add_argument("--document", type=Path)
    mode.add_argument("--fixture", choices=fixtures())
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    path = args.document or DEFAULT_DOCUMENT
    try:
        text = fixtures()[args.fixture][0] if args.fixture else path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        print(f"INPUT_ERROR: {error}", file=sys.stderr)
        return 2
    errors = check(text)
    label = f"fixture:{args.fixture}" if args.fixture else str(path)
    for line, code, message in errors:
        print(f"{label}:{line}: {code}: {message}")
    rc = 1 if errors else 0
    print(f"NA_BOUNDARY_ERRORS={len(errors)} NA_BOUNDARY_RC={rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
