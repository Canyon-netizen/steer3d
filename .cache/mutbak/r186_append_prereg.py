#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 186 追加脚本 —— 流水线落盘名写死，把上一轮的证据覆盖掉了。

本节两块：
  186.1 ⛔ 缺陷：STAMP 写死 r182_label.json，连续两次运行互相覆盖
  186.2 修法与自检：运行标签 + 两次运行的文件并存
"""

from pathlib import Path

SECTION = """
## 修订 186 —— ⛔ 流水线落盘名写死，上一轮的证据被静默覆盖

### 186.1 缺陷

`r182_verdict_pipeline.py` 的第 3 步（scp 拉回）落盘名由模块级常量拼出：

    STAMP = "r182"
    dest = MUT / ("%s_label.json" % STAMP)      ->  .cache/mutbak/r182_label.json

**每一次运行都写到同一个文件名。**

实测后果（本轮踩到，由 `git status --porcelain` 抓到）：

| 文件 | 修订 182 入库时 | 被覆盖后 |
|---|---:|---:|
| `.cache/mutbak/r182_label.json` | **20 行** | **32 行** |

即：修订 182 的账本引用了 `r182_label.json` 作为证据，
而**那一版文件已经不存在了** —— 账本里写着 20 行的口径，
磁盘上摆着 32 行的另一份，**读的人拿到的是错的那份，而没有任何报错**。

⚠⚠⚴ 这是「结论对但证据没进仓库」的**另一种形态**：
⚠ 前一种是「证据根本没提交」，这一种是「**证据提交过，但被后来的运行覆盖掉了**」。
⚠ 两者后果相同：账本与仓库对不上，且都不报错。

⚠ 抓它的是提交前那句 `git status --porcelain` ——
⚠ 若沿用「暂存集 == 意图清单」但不看工作区残留，这一次就会漏过去。

### 186.2 修法与自检

1. **恢复**：`git checkout -- .cache/mutbak/r182_label.json`，
   把修订 182 的 20 行证据放回磁盘（已验：20 行）。
2. **加运行标签**：落盘名改为 `r182_<MMDD_HHMMSS>_label.json`，不再跨运行复用。
   远端标注产物与本地拉回用同一个标签，两边对得上。
3. **自检**：连续跑两次后两个文件并存，互不覆盖：

       r182_label.json                 20 行   （修订 182 的入库证据）
       r182_1014_205923_label.json     32 行   （本轮增量）

⚠ 固化：**任何会落盘的脚本，落盘名必须能区分「哪一次运行」。**
⚠ 否则第二次运行就会把第一次的证据变成历史。
⚠ 这条与修订 180.4（权威脚本硬编码输入路径，读到旧文件）同族 ——
⚠ 那一条是「**读到**别的运行留下的东西」，本条是「**覆盖掉**别的运行留下的东西」。
⚠ 两条的共同根因：**把「文件名」当成了「数据身份」**。
⚠ 数据身份应该由内容（批次 + cap + 行数 + 时间）决定，不由文件名决定。
"""

PRECHECKS = (
    ("无 U+FFFD 坏字", lambda s: chr(0xFFFD) not in s),
    ("无反斜杠续行", lambda s: chr(92) + chr(10) not in s),
    ("以换行结尾", lambda s: s.endswith(chr(10))),
    ("标题格式合规", lambda s: s.lstrip(chr(10)).startswith("## 修订 186 ")),
    ("含本节入口", lambda s: "186.2 " in s),
)


def main():
    target = Path(__file__).resolve().parents[2] / ".cache/xcheck/R6_RERUN_PREREG.md"
    before_lines = len(target.read_text(encoding="utf-8").splitlines())

    bad = [name for name, fn in PRECHECKS if not fn(SECTION)]
    if bad:
        print("[前置检查失败] " + " / ".join(bad))
        return 2

    with target.open("a", encoding="utf-8") as fh:
        fh.write(SECTION)
    after_lines = len(target.read_text(encoding="utf-8").splitlines())

    print("追加完成：%d -> %d 行（+%d）" % (before_lines, after_lines,
                                        after_lines - before_lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())