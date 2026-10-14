"""把修订 179 追加到 R-6 预登记。

本节：⚠⚠⚴ 登记【两个差分脚本分母不同、且其中一个数会被误引】这件事，
并钉死 P6 口径的权威来源（§179.2）。

⚠ 不改 r167_delta.py —— 它内部自洽（已印部分数据警告、三列等 footing）；
⚠⚠ 要改它属于改判据侧的东西，须先拍板。本节只登记口径差异与权威来源。
"""

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / ".cache/xcheck/R6_RERUN_PREREG.md"

SECTION = """
## 修订 179 —— 钉死 P6 口径的权威来源：两个差分脚本分母不同，其中「还差 5 条」是部分数据的产物

### 179.0 ⚠⚠⚴ 两个脚本答的是**同一个问题**，却用**不同分母**

同一份数据（旧批 120 条 + 新批 16 条）分别喂给两个脚本，实跑结果：

| | `r167_delta.py` | `r178_uncapped_fate.py` |
|---|---|---|
| 分母口径 | `common`（**两批都有的** 8 条） | 旧批 think 池里 unlabeled 的**全部 19 条**，未测单列 |
| 转移矩阵 | 3×3，8 条 | 四态 A/B/C/D，逐条 |
| 印出的转化率 | `0%（门槛 > 16%）` | `0/19 = 0.0%`，另列「未测 17」 |
| 印出的「还差几条 correct」 | **还差 5**（8 条里 correct=5） | **还需 3**（全池旧 correct=7） |

⚠⚠⚠⚠⚠⚠⚠⚠ **⚠⚠⚴「还差 5」是【部分数据】造出来的数：⚠⚠⁴⚠⚠⚗⚠**
⚗⚠ **剩下 22 条没测的题里，还有 2 条旧批 correct。⚠⚠⁴⚗⚠⚗⚠⚗⚠⚗⚠**
⚗⚠ ⚗⚠⚴⚴ **若那 2 条保持 correct，全池 correct = 7 ⇒ 缺口是 3，不是 5。⚠⚠⁴⚗⚠⚗⚠⚗⚠⚗⚠⚗⚠⚗⚠⚗⚠**
⚗⚠ ⚗⚠ ⚗⚠⚴⚴⚴⚠⚠ **⇒ 全池口径的 P6 缺口 = 3，权威来源是 `r178_uncapped_fate.py`。⚠⚠⁴⚗⚠⚗⚠⚗⚠⚗⚠⚗⚠⚗⚠⚗⚠**

⚠⚠⁴⚠⚠⚠⚠ **⚠⚠⚴⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠ 危险形态（⚠⚠⁴ 引用侧，不是计算侧）：⚠⚠⁴⚗⚠⚗⚠⚗⚠⚗⚠⚗⚠⚗⚠⚗⚠⚗⚠⚗⚠⚗⚠⚗⚠**
⚗⚠⁴⚗⚠ ⚗⚠ `r167_delta.py` 那两行印的是**并排**的：
⚗⚠⁴⚗⚠⚗⚠ ⚗⚠⚴⚴⚴ `已翻 correct 0 / 旧 unlabeled 2 ⇒ 转化率 0%（门槛 > 16%）`
⚗⚠⁴⚗⚠ ⚗⚠ ⚗⚠⚴⚴⚴ **⇒ 两数并排，读起来像「0% 对 16% ⇒ 不够」。⚠⚠⁴⚗⚠⚗⚠⚗⚠⚗⚠⚗⚠⚗⚠⚗⚠**
⚗⚠⁴⚗⚠ ⚗⚠ ⚗⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠ **⚠⚠⚠ 而 P6 的那条 16% 门槛是拿【19 条全池】算的，不是拿【已测 2 条】算的。⚠⚠⁴⚗⚠⚗⚠⚗⚠⚗⚠⚗⚠⚗⚠⚗⚠**
⚗⚠⁴⚗⚠ ⚗⚠ ⚗⚠ ⚗⚠⚴⚴⚴⚴⚴⚴ **⚠⚠⚴ 两个分母都真实，⚠⚠⚴ 但只有其中一个是 P6 的分母。⚠⚠⚴⚗⚠⚗⚠⚗⚠⚗⚠⚗⚠⚗⚠⚗⚠⚗⚠⚗⚠**

### 179.1 ✅ 两边**各自都已经很谨慎**（先说清楚，避免误伤）

- `r167_delta.py` 并不糊涂，它已经做了三件对的事：
  开头印「新批次只完成 16/60 条 —— 下面每个数都是【部分数据】的数」；
  转移矩阵只取 `common`；表头明写「两列的 n 不同（30 vs 8）⇒ 不可逐格相减」，
  并列出「旧（全池）/ 旧（同 N 条）/ 新（同 N 条）」三列等 footing。
- `r178_uncapped_fate.py` 口径见 §178.1：固定 19 条分母、未测单列不进分母。
- ⚠⚠ **⚠⚠⚴⚠⚠⇒ 问题不在任何一个脚本的内部，而在【它们之间没有互相声明哪个分母对 P6 有效】。⚠⚠⚴⚗⚠⚗⚠⚗⚠⚗⚠⚗⚠⚗⚠⚗⚠⚗⚠⚗⚠⚗⚠**

### 179.2 ✅ 钉死（P6 口径的引用规则）

引用 P6 相关数时，**一律以 `r178_uncapped_fate.py` 的输出为准**：

| 要报的数 | 口径 | 来源 |
|---|---|---|
| 候选池大小 | 19 | r178 |
| 已测 / 未测 | 已测 N / 未测 19-N | r178 |
| A / B / C / D 计数 | 分母 = 已测数 | r178 |
| **P6 缺口** | **3**（全池旧 correct=7，底线 10） | r178 |
| 全池转化率门槛 | 15.8% = 3/19 | r178 |
| 转化率 | 须同时印「已测 N」与「未测 19-N」 | r178 |

⚠⚠⁴ ⚠⚠⚴ **⛔ 不得单独引用 `r167_delta.py` 的「还差 5 条 correct」或「转化率 0%」。⛔**
⚠ ⚠⚠ 除非**同时**印上「该分母是已完成的 8 条，而非 19 条候选池」。

⚠ 本节**不改** `r167_delta.py`：它内部自洽，改它属于改判据侧的东西，须先拍板。
⚠ 本节**不含 P6 结论**（§167：数据没跑完不许给结论；当前 16/60）。
"""

HEADER = "## 修订 179 "


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
        print("[错误] SECTION 首行不是「## 修订 179 」格式 —— 硬门，不追加")
        raise SystemExit(2)
    if HEADER in txt_before:
        print("[错误] 修订 179 段已存在 —— 硬门，不追加")
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
    print(f"  修订 178 段仍在：{'## 修订 178 ' in txt}")
    print(f"  修订 179 段已在：{HEADER in txt}")
    if not ok or HEADER not in txt:
        print("[错误] 追加未生效 —— 不许当成成功")
        raise SystemExit(2)


if __name__ == "__main__":
    main()