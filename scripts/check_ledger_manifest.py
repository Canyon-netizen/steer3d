#!/usr/bin/env python3
"""244.86 落账清单结构守卫（标准库，不依赖真库/远端/GPU）。

默认只读真实账本的 244.86【8】；--selftest 在临时合成 Markdown 上验证 CLI。
--fixture clean 返回 0；--fixture receipt_extension 等坏夹具返回 1。
rc=0: 通过；rc=1: 清单判红；rc=2: 输入错误或自检失败。

检查声明件数 vs 实列条数、重复项、登记文件集合（含 receipt.txt 和 R7 驱动）。
契约来自本轮修复后的清单，不能用被检清单自身生成预期文件集合。
不验证收据内容/MD5 的真实性，不验证预登记的签发时序，也不执行任何被检文件。
"""

import argparse
from pathlib import Path
import re
import subprocess
import sys
import tempfile


DEFAULT_LEDGER = Path(__file__).resolve().parents[1] / ".cache/xcheck/R6_RERUN_PREREG.md"
DRIVERS = (
    "control_arm_null_audit.py", "mut_control_arm_null_audit.py",
    "_cross_check_24486.py", "_spec_crosscheck_24486.py",
    "_run_24486_verify.sh", "R6_CONTROL_ARM_NULL_PREREG.md",
    "_run_24486_reg_shm.sh",
)
RECEIPTS = ("selftest.out", "de.out", "mut.out", "cross.out", "spec.out", "receipt.txt")
GROUPS = {"被检 / 口径 / 驱动": DRIVERS, "收据文件": RECEIPTS}


def check(text):
    errors = []
    lines = text.splitlines()
    rounds = [i for i, line in enumerate(lines)
              if re.match(r"^##\s+修订\s+244\.86(?![\d.])", line)]
    if len(rounds) != 1:
        return [(1, "LEDGER_ROUND", "必须恰有一段修订 244.86")]
    start = rounds[0]
    end = next((i for i in range(start + 1, len(lines))
                if re.match(r"^##\s+", lines[i])), len(lines))
    sections = [i for i in range(start + 1, end)
                if re.match(r"^####\s+【8】", lines[i])]
    if len(sections) != 1:
        return [(start + 1, "LEDGER_SECTION", "244.86 必须恰有一节【8】")]
    start = sections[0]
    end = next((i for i in range(start + 1, end)
                if re.match(r"^#{1,4}\s+", lines[i])), end)
    for title, expected in GROUPS.items():
        header = re.compile(r"^- \*\*" + re.escape(title) + r"（(\d+) 件）\*\*：\s*$")
        headers = [(i, header.fullmatch(lines[i])) for i in range(start + 1, end)
                   if header.fullmatch(lines[i])]
        if len(headers) != 1:
            errors.append((start + 1, "MANIFEST_GROUP", f"{title} 标题缺失、重复或格式错误"))
            continue
        index, match = headers[0]
        names = []
        cursor = index + 1
        while cursor < end and (not lines[cursor].strip() or lines[cursor].startswith("  ")):
            if not lines[cursor].strip():
                cursor += 1
                continue
            entry = re.fullmatch(r"  - `([0-9a-f]{32})`\s+`([^`]+)`(?:\s+.*)?", lines[cursor])
            if entry is None:
                errors.append((cursor + 1, "MANIFEST_ENTRY", "清单条目格式不合法"))
            else:
                names.append(entry.group(2))
            cursor += 1
        if int(match.group(1)) != len(names):
            errors.append((index + 1, "MANIFEST_COUNT",
                           f"{title} 声明 {match.group(1)} 件，实际列出 {len(names)} 件"))
        if len(names) != len(set(names)):
            errors.append((index + 1, "MANIFEST_DUPLICATE", f"{title} 有重复条目"))
        missing, extra = set(expected) - set(names), set(names) - set(expected)
        if missing or extra:
            errors.append((index + 1, "MANIFEST_FILES",
                           f"{title} 缺失={sorted(missing)} 多余={sorted(extra)}"))
    return errors


def fixtures():
    def entry(name):
        # 合成指纹仅用于格式；不冒充真实收据。
        return f"  - `{'0' * 32}`  `{name}`  合成夹具\n"

    base = "## 修订 244.86 —— 合成\n#### 【8】 这一轮的字节\n"
    for title, names in GROUPS.items():
        base += f"- **{title}（{len(names)} 件）**：\n"
        base += "".join(entry(name) for name in names)
    driver_removed = base.replace(entry(DRIVERS[-1]), "")
    return {
        "clean": (base, None),
        "spaced_entries": (base.replace("  - `", "\n  - `"), None),
        "other_round": ("## 修订 244.85 —— 旧段\n收据文件（999 件）\n" + base +
                        "## 修订 244.87 —— 后段\n收据文件（999 件）\n", None),
        "receipt_extension": (base.replace("`receipt.txt`", "`receipt.out`"), "MANIFEST_FILES"),
        "registered_total": (base.replace("收据文件（6 件）", "收据文件（13 件）"), "MANIFEST_COUNT"),
        "missing_driver": (driver_removed, "MANIFEST_FILES"),
        "missing_driver_recounted": (driver_removed.replace("驱动（7 件）", "驱动（6 件）"), "MANIFEST_FILES"),
        "duplicate_receipt": (base.replace(entry("spec.out"), entry("de.out")), "MANIFEST_DUPLICATE"),
        "extra_after_blank": (base + "\n" + entry("extra.out"), "MANIFEST_COUNT"),
        "missing_receipt": (base.replace(entry("receipt.txt"), ""), "MANIFEST_COUNT"),
        "bad_digest": (base.replace("0" * 32, "not-a-digest", 1), "MANIFEST_ENTRY"),
        "renamed_section": (base.replace("【8】", "【9】"), "LEDGER_SECTION"),
        "missing_group": (base.replace("收据文件", "收据清单"), "MANIFEST_GROUP"),
        "duplicate_group": (base + base[base.index("- **收据文件"):], "MANIFEST_GROUP"),
        "wrong_round": (base.replace("244.86", "244.87"), "LEDGER_ROUND"),
        "duplicate_round": (base + base, "LEDGER_ROUND"),
        "duplicate_section": (base + "#### 【8】 重复\n", "LEDGER_SECTION"),
        "empty": ("", "LEDGER_ROUND"),
    }


def selftest():
    failed = positive = negative = 0
    with tempfile.TemporaryDirectory(prefix="ledger-manifest-") as folder:
        path = Path(folder) / "ledger.md"
        for name, (text, expected_code) in fixtures().items():
            path.write_text(text, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--ledger", str(path)],
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
    mode.add_argument("--ledger", type=Path)
    mode.add_argument("--fixture", choices=fixtures())
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    path = args.ledger or DEFAULT_LEDGER
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
    print(f"LEDGER_MANIFEST_ERRORS={len(errors)} LEDGER_MANIFEST_RC={rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
