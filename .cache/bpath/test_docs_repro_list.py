"""文档 §6「复算」清单 vs 构建器**实际读取**的文件 —— 自动核对。

## 为什么要有这个守卫

§6 曾经把 `layer_sweep_t1.json`（**臂 A**）列成输入，而构建器从来不读它 ——
读的是 `layer_sweep_B.json`。两者并排躺在同一个目录里，
早期版本正是这样读错了 `w`，推出了已撤回的「高估 43 倍」。

也就是说：**文档把最贵的一个坑写成了「照着做就行」**。
而清单里还漏了 7 个构建器真实读取的文件，照着文档复算根本跑不起来。

⇒ 清单必须**自动对着代码核对**，不能靠人记得更新。

## 它做什么

1. 从 `build_bpath_evidence.py` 里抽出所有 `jload(M / "...")` 的文件名；
2. 从 `docs/BPATH_MARKER_STEERING.md` 的 §6 表里抽出所有反引号文件名；
3. 断言：**构建器读的文件 ⊆ 文档列出的文件**（漏一个就失败）；
4. 断言：**`layer_sweep_t1.json` 不在文档的输入清单里**（臂 A 不是输入）。

## 纯 stdlib，本地秒级
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
BUILDER = os.path.join(ROOT, ".cache/bpath/build_bpath_evidence.py")
DOC = os.path.join(ROOT, "docs/BPATH_MARKER_STEERING.md")
ARM_A = "layer_sweep_t1.json"


def builder_inputs(path):
    src = open(path, encoding="utf-8").read()
    return set(re.findall(r'jload\(M / "([^"]+)"', src))


def doc_inputs(path):
    """只扫 §6 里**表格行**的反引号文件名。

    ⚠ 不能扫整节：警示段落里**故意**提到了臂 A 的文件名
    （「`layer_sweep_t1.json` 不是本文件的输入」），
    扫整节会把这条警告误当成「把它列成了输入」。
    """
    src = open(path, encoding="utf-8").read()
    sec = src.split("## 6. 复算", 1)
    if len(sec) != 2:
        raise SystemExit("文档里找不到 §6 复算")
    body = sec[1].split("\n## ", 1)[0]
    names = set()
    for line in body.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        names |= set(re.findall(
            r"`([A-Za-z0-9_.\-]+\.(?:json|jsonl|npy|txt|sh)"
            r"(?:\.bak_armA)?)`", line))
    return names


def main():
    bi, di = builder_inputs(BUILDER), doc_inputs(DOC)
    missing = sorted(bi - di)
    if missing:
        print("✗ 构建器读取但文档 §6 没列：")
        for m in missing:
            print("   ", m)
        raise SystemExit("文档复算清单已过时")
    if ARM_A in di:
        raise SystemExit(
            f"⚠ 文档 §6 把臂 A 的 {ARM_A} 列成了输入 —— "
            f"那正是撤回「高估 43 倍」的那个坑，不许再列为输入")
    print(f"✓ 构建器读取的 {len(bi)} 个文件，文档 §6 全部列出")
    print(f"✓ 臂 A 的 {ARM_A} 未被列为输入")
    extra = sorted(di - bi)
    if extra:
        print(f"  （文档另列了 {len(extra)} 个非 jload 引用：{extra}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())