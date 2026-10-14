"""把**修订 167** 追加到 R-6 预登记。

本节：⚠⚠ **把「32768 的结果怎么读」在数据到之前定死**（判据口径预登记）；
附差分分析脚本 `r167_delta.py`，已端到端试跑通。
"""

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / ".cache/xcheck/R6_RERUN_PREREG.md"

SECTION = """
## 修订 167 —— ⚠⚠⚴ **「32768 的结果怎么读」在数据到之前定死**（判据口径预登记）

### 167.0 ⚠⚠⚴⚠ **为什么必须在数据到之前写**

⚠ **时点**：`r167_delta.py` 写于 **17:2x**，⚗⚠ 而 32k 批次 **17:00 才起跑、只完成 4/60 条**。
⚠⚠⁴⚠⚴⚠ **⇒ 读数规则定在【看到结果之前】。⚠⚠⁴⚠⚴⚠**
⚗⚠⚴ **⇒ 这不是为了显得严谨，是因为 §165.1 已经指出了一个具体的诱惑：⚗⚠⚴**
⚗⚠ **「标签产出率从 39 unlabeled 掉到接近 0」会是一个非常好看的数，⚗⚠⁴⚠⚴ 而 P6 要的是 correct。⚗⚠⁴⚠⁴⚠**

⚠ **§165.1 已经发生的那一条**：smoke 的 p04 确实从 unlabeled 变成了 labeled，
⚗⚠ **但翻成了 wrong（297 vs 279）。⚗⚠** ⚠⚠⚴ **⇒ 诱惑是真实的，不是假想。⚠⚠⚴**

### 167.1 ⚠ **P6 够格与否，被压成一个可判定的数字**

⚠ 前 30 题（aime25）think 池：**correct 7 / wrong 4 / unlabeled 19**
⚠⇒ P6 硬底线 correct ≥ 10 ⇒ **缺口 3 条**
⚠⚠⚴⚠⚴ **⇒ 判据：旧 unlabeled 的 19 条里，须有 ≥3 条在 cap 32768 下翻成 correct，**
⚗⚠⚴⚠ **即 unlabeled→correct 转化率 > 16%。⚗⚠⚴⚠⚗⚠⚴⚠⚠⚠⚴⚠⚴**

⚠⚠ **⚠⚠⁴ 三条硬性读法（写死）：⚠⚠⁴**
⚗ ① **不许只报「标签产出率」** —— ⚗⚠ **那个数一定好看，而它不是 P6 要的量。⚗⚠⁴⚠**
⚗ ② **必须逐条指回轨迹 id** —— ⚠⚠ **任何比例都要能被 `grep` 回具体文件。⚠⚠⁴**
⚗ ③ ⚠⚠ **数据没跑完就不许给结论** —— ⚗⚠ **部分数据的 correct 至少还会涨，⚗⚠
   ⚗⚠⚠ **拿半成品说「不够」和说「够」一样是不公平的**。⚗⚠⁴⚠**

### 167.2 ⚠ **差分分析脚本 `r167_delta.py`**（已试跑通）

⚠ 它只报三个数，且每个都能指回具体轨迹：

```
1. 转移矩阵：unlabeled → correct / wrong / 仍 unlabeled
2. P6 现状：aime25 单池的 correct/wrong/unlabeled（⚗⚠ 不许用合并池）
3. 那条 16% 的线：够/不够【分开写】，不许只给一个百分比
```

⚠⚠ **⚠⚠⚴ 试跑实测（只 4/60 条，仅验证流水线）：⚠⚠⚴**
⚠ 远端标注器与本地 **md5 一致**（`1d74af82ab7010f048b7ae3aab88a09d`）⇒ 用的就是 R-27 同一套规则；
⚠ 脚本在只有 2 条 think 数据时**主动拒绝判定**：

```
⚠⚠⚴ **新批次 think 只完成 2 条 ⇒ correct 至少还会涨 ⇒ 现在判「不够」是不公平的。**
⚗⚠ 本行只说明【当前已完成的 2 条里 correct=2】。
```

⚠✅ **⇒ 「半成品不许下结论」这条规则当场生效过一次，不是摆设。⚠⚠**

⚠ **它与判决的分工**：⚠⚠ `r167_delta.py` **只报数、不判定**；
⚗⚠⚠⚠ **判定仍走 `p6_readiness.py`**（§166 已把 32768 收进批次身份集）。
⚗⚠⚠ ⚠⚠⚴⚠ **两个脚本不许互相代替** —— ⚗⚠ **一个报数、一个判，避免「自己给自己发合格证」。⚗⚠⚴⚗⚠⚠**

### 167.3 ⚠ 速率与 ETA（部分数据，只能当下界用）

⚠ 已完成 4 条 / 纯生成 **556.1 s** ⇒ 每条均 **139.0 s** ⇒ 按此均速 60 条 ≈ **2.3 h**

⚠⚠⚴ **⚠⚠⚴ 但这是【下界】，⚗⚠ 已完成的 4 条平均只有 4,507 token，⚗⚠⚴⚠⚴**
⚗ **而 b2 批 49/60 条撞过 8192 顶 —— 32k 下这类题会跑到上万 token（smoke 的 p04 是 20,360）。⚗⚠⚴**
⚗⚠⇒ **⇒ 2.3 h 会明显往上走；⚗⚠ 收工时间以届时实测为准，不拿这个数当承诺。⚗⚠⚴**

⚠ 实测速率 **0.0308 s/token**，⚗⚠ 比 smoke 的 0.0259/0.0264 略慢，
⚗⚠⚴⚠⚴ **但样本只有 4 条且长度偏短，⚗⚠⚴ 不足以判「卡 3 被抢」** —— ⚠⚠ **卡被抢的判据是看这条速率随时间是否持续劣化。⚠⚠**

### 167.4 ⚠ 校验 / 本节边界

- ⚠⚠ **读数规则定在数据到之前**（17:00 起跑，本节写于 17:2x，仅 4/60 条）
- ⚠ 差分脚本端到端试跑通；⚠⚠ 标注器 md5 两侧一致
- ⚠ 半成品拒绝判定**当场触发过一次**
- ⚠ **本节不含任何关于 32768 数据效果的结论**
- ⚠ 未改 P6 门槛（10）、未改标签规则、未改 `p6_readiness.py` 的任何判据
"""


def main():
    before = PREREG.read_bytes()
    if not before.endswith(bytes([10])):
        print("[错误] 追加前文件不以换行结尾 —— 硬门，不追加")
        raise SystemExit(2)
    if before.decode("utf-8").count(chr(0xFFFD)):
        print("[错误] 追加前已有坏字 —— 硬门，不追加")
        raise SystemExit(2)

    sha_before = hashlib.sha256(before).hexdigest()
    n_before = before.decode("utf-8").count("\n")
    PREREG.write_text(before.decode("utf-8") + SECTION, encoding="utf-8")

    after = PREREG.read_bytes()
    txt = after.decode("utf-8")
    ok = after[:len(before)] == before
    print("=== 追加结果 ===")
    print(f"  原文 {len(before):,} bytes / {n_before:,} 行 / sha256 {sha_before[:16]}")
    print(f"  现文 {len(after):,} bytes / {txt.count(chr(10)):,} 行")
    print(f"  ⚠ 原文逐字节未变：{ok}")
    print(f"  ⚠ 以换行结尾：{after.endswith(bytes([10]))}")
    print(f"  ⚠ 坏字（原始字节层）：{txt.count(chr(0xFFFD))}")
    print(f"  ⚠ 修订 166 段仍在：{'## 修订 166 ' in txt}")
    print(f"  ⚠ 修订 167 段已在：{'## 修订 167 ' in txt}")
    if not ok or "## 修订 167 " not in txt:
        print("[错误] 追加未生效 —— 不许当成成功")
        raise SystemExit(2)


if __name__ == "__main__":
    main()