"""把修订 178 追加到 R-6 预登记。

本节：把「旧批 unlabeled 在新批里的归宿」**分类口径在数据到齐之前定死**，
并落第一条实测（已测 2/19，A=1 B=1 C=0）。

⚠ 为什么要预先定死：A（仍触顶）与 B（跑完但 wrong）都会让「unlabeled 变少」，
⚗ 而它们对 correct 的贡献都是 0 —— 只报「unlabeled 减少」会把 A 和 B 算成成功。

⚠ 写这一版不用长串 ⚠ 装饰：前两版曾因装饰过密被写坏（47KB / 1 个 U+FFFD / 引号未闭合）。
"""

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / ".cache/xcheck/R6_RERUN_PREREG.md"

SECTION = """
## 修订 178 —— 把「unlabeled 的归宿」分类口径在数据到齐前定死（四态）；落首条实测 2/19：A=1 B=1 C=0

### 178.0 候选池与门槛（数字侧，逐条算，不抽样）

- 旧批 aime25 think 池（n=30）：correct 7 / wrong 4 / **unlabeled 19**。
- P6 底线 think correct >= 10 ⇒ 已有 7 ⇒ **还需 3 条来自候选池**。
- 全池口径转化率门槛 = 3 / 19 = **15.8%**（⚠ 只有 19 条全测完才能对照这个数）。

### 178.1 四态分类口径（本节预登记的核心）

旧批 19 条 unlabeled 在新批（cap 32768）里有**四种**归宿，不是两种：

| 态 | 判据 | 对 correct 的贡献 |
|---|---|---|
| A 仍触顶 | `truncated == True` | **0** |
| B 跑完但 wrong | 未触顶且 strict == wrong | **0** |
| C 跑完且 correct | 未触顶且 strict == correct | 1 |
| D 跑完但仍 unlabeled | 未触顶却仍无答案陈述 | 0 |

⚠ 事先讲清楚为什么必须分开报 A 和 B：
「抬 cap 让它把话说完了」= A + B + C + D 的补集，而 **P6 只认 C**。
若只报「unlabeled 减少了多少」，A 与 B 会被一起算成成功，
而它们对 correct 的贡献是 **0**。

⚠ D 态是**新出现的第四种**，不得静默并入 A：
「没触顶却仍 unlabeled」与「触顶」是两回事（前者是没说出答案，后者是没说完）。
§177.0 那次 p06 的反证，正是因为把这两者混为一谈会高估抬 cap 的效果。

口径纪律（写死）：
- 分母固定 = 旧批 think 池里 strict == unlabeled 的题号（19 条），逐条处理，不抽样。
- 一题一条，不按 token 数聚合。
- 「未测」与「测到 A/B/C/D」分开列，未测的**不进任何一类的分母**。
- 新旧两侧题号必须对齐（都取 pNN），因为两批文件名相同、只有 cap 不同（§177.2）。

### 178.2 首条实测（⚠⚠ 样本 2 条，**不得外推**）

    题      旧(8192)   新n_tok   新strict     归宿
    p04    unlabeled    20360    wrong        B 跑完但 wrong
    p06    unlabeled    32768    unlabeled    A 仍触顶

- 已测 **2 / 19**，未测 17（p08 p09 p10 p11 p12 p13 p14 p17 p19 p20 p22 p23 p25 p26 p27 p28 p29）。
- **A = 1，B = 1，C = 0**；已测段转化率 0.0%。
- ⚠⚠⚠ **A + B = 2，两条都对 correct 贡献 0。⚠⚠⚠**
  ⚗ 这两条恰好各演示了一种失败模式：
  ⚗⚠ p04 抬 cap 让它**把话说完了**（20360 tok 未触顶），⚗⚠ **但答案是错的**；
  ⚗⚠ p06 抬 cap 四倍**仍不够**（32768 跑满仍截断）。
  ⚗⚠⚗⚠ **「不 truncated」与「correct」是两个独立条件**，⚗⚠ §177.1 那句现在有实例了。

⚠⚠⚠⚠ **⚠⚠ 0/2 是 n=2，几乎不比 n=1 更有信息量。⚠⚠⚠⚠**
⚗⚠ §177.0 已写死「绝不许由 1 条推论 19 条」；⚗⚠⚠ **同一条纪律在这里适用 2 条：
⚗⚠⚠ 0/2 **既不能**支持「32k 救不了 P6」，⚗⚠⚠ **也不能**支持「32k 救得了 P6」。
⚗⚠⚠ ⚗⚠ 它只支持一件事：**A 与 B 确实存在，且必须与 C 分开报。**⚗⚠⚠⚗⚠⚗⚠⚗⚠

⚠ 另附一条同口径旁证（同一批数据，不构成独立证据）：
think 臂已测 8 题 = correct 5 / wrong 2 / unlabeled 1；
旧批这 8 题里 5 correct 全部保持 correct、1 wrong 保持 wrong，
⚗⚠ **即「非 unlabeled 的旧标签在新 cap 下没被改动」**（已测段 6/6 一致）。

### 178.3 落地方式

新增 `.cache/mutbak/r178_uncapped_fate.py`：读旧批与新批两份标注，
自动输出候选池、未测清单、四态计数、P6 相关数、逐条明细。口径写在脚本头部，
⚠ 后续每一轮只需重跑它，不必重述规则。

⚠ 本节**不含 P6 结论**（§167：数据没跑完不许给结论；当前 16/60）。
"""

HEADER = "## 修订 178 "


def main():
    before = PREREG.read_bytes()
    if not before.endswith(bytes([10])):
        print("[错误] 追加前文件不以换行结尾 —— 硬门，不追加")
        raise SystemExit(2)
    txt_before = before.decode("utf-8")
    if txt_before.count(chr(0xFFFD)):
        print("[错误] 追加前已有坏字 —— 硬门，不追加")
        raise SystemExit(2)
    if chr(92) in SECTION:
        print("[错误] SECTION 含反斜杠 —— 硬门，不追加")
        raise SystemExit(2)
    if SECTION.count(chr(0xFFFD)):
        print("[错误] SECTION 含坏字 —— 硬门，不追加")
        raise SystemExit(2)
    if not SECTION.endswith("\n"):
        print("[错误] SECTION 不以换行结尾 —— 硬门，不追加")
        raise SystemExit(2)
    if not SECTION.lstrip("\n").startswith(HEADER):
        print("[错误] SECTION 首行不是「## 修订 178 」格式 —— 硬门，不追加")
        raise SystemExit(2)
    if HEADER in txt_before:
        print("[错误] 修订 178 段已存在 —— 硬门，不追加")
        raise SystemExit(2)

    sha_before = hashlib.sha256(before).hexdigest()
    n_before = txt_before.count("\n")
    PREREG.write_text(txt_before + SECTION, encoding="utf-8")

    after = PREREG.read_bytes()
    txt = after.decode("utf-8")
    ok = after[:len(before)] == before
    print("=== 追加结果 ===")
    print(f"  原文 {len(before):,} bytes / {n_before:,} 行")
    print(f"  现文 {len(after):,} bytes / {txt.count(chr(10)):,} 行")
    print(f"  原文逐字节未变：{ok}")
    print(f"  以换行结尾：{after.endswith(bytes([10]))}")
    print(f"  坏字：{txt.count(chr(0xFFFD))}")
    print(f"  修订 177 段仍在：{'## 修订 177 ' in txt}")
    print(f"  修订 178 段已在：{HEADER in txt}")
    if not ok or HEADER not in txt:
        print("[错误] 追加未生效 —— 不许当成成功")
        raise SystemExit(2)


if __name__ == "__main__":
    main()