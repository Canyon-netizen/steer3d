"""把**修订 171** 追加到 R-6 预登记。

本节：⚠✅ **拿【真】32768 产物端到端跑通**了修订 166 那道身份闸；
⚠⚠⚴ 并查出**我自己的差分脚本**有一个会诱发误读的输出缺陷（已修）。
"""

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / ".cache/xcheck/R6_RERUN_PREREG.md"

SECTION = """
## 修订 171 —— ⚠✅ **真产物端到端跑通身份闸**；⚠⚠⚴ 查出**我的差分脚本**会诱发误读（已修）

### 171.0 ⚠⚠ **先补一个真实缺口：合成 fixture ≠ 真实管道**

⚠⚠⚴ 修订 166 我用**合成 fixture** 证明了批次身份闸的逻辑（5/5）。
⚗⚠⚴⚠⚴ **但那证的是【逻辑】，⚗⚠ 不是【管道通不通】——⚗⚠⚠**
⚗⚠ **一个真批次能不能从产物一路走到判决，中间还要过：远端标注 → 拉回 → 标签 json → p6_readiness。⚗⚠⁴⚗⚠**
⚗⚠⚴⚠ **而这条链我从来没拿真 32768 产物走通过。⚗⚠⁴⚗⚠⚗⚠⚴⚗⚠⚴**

### 171.1 ⚠✅ **真产物实跑（8/60 条时）**

⚠ 路径：远端 `strict_label_r167.py`（md5 与本地一致）→ `label_32768_partial.json` → 拉回 → 判决

⚠✅ **身份闸这次是放行的**（⚗ **不是 MISMATCH** ⇒ 修订 166 的改动在真实管线上生效）：

```
[think]   n=4  correct=4  wrong=0  unlabeled=0  触顶=0  幻觉=0  cap=[32768]
[no_think] n=4  correct=1  wrong=3  unlabeled=0  触顶=0  幻觉=0  cap=[32768]
⚠ 实际加载：/Users/zhourui/code/steer3d/.cache/mutbak/strict_label.py   ← R-27 唯一来源
RESULT p6_readiness  UNDERPOWERED  think correct=4 < 10
真实退出码 exit=3   ⚠⚠⚴（第一遍我用 `| head` 量退出码，拿到的是 head 的 0 ——
                    ⚗⚠⚴ **退出码必须脱离管道量**，这个坑本会话已犯过一次）
```

⚠⚠ **⚠⚠⚴⚠ 本次实跑暴露的第一个真事实：⚠⚠⚴⚠**
⚠ **已完成的 4 条 think 在旧批（8192）里【本来就全是 correct】** ⇒ 转移矩阵是
```
correct -> correct  4
旧 unlabeled 共 0 条 → 翻成 correct 0 / wrong 0 / 仍 unlabeled 0
```
⚗⚠⚴ **⇒ 「unlabeled → correct 的转化率」目前仍是 0/0【没测到任何一条 unlabeled】。⚗⚠⁴⚗⚠⚴**
⚠ **前几题（p00/p01…）本来就不是那 19 条 unlabeled，⚗⚠ 所以现在这个 0 不是「转化失败」，⚗⚠ 是【还没跑到】。⚗⚠⚠⚠**

### 171.2 ⚠⚠⚴⚠ **查出我自己的差分脚本有个会诱发误读的缺陷（已修）**

⚠⚠⚴⚠ **⚠⚠⚴ 第一版的第 2 节把「旧全池 30 条」与「新 4 条」并排印出：⚠⚠⚴⚠**

```
            旧 cap 8192    新 cap 32768
  correct       7               4
  unlabeled    19               0     ← ⚠⚠⚴⚠⚠ 一眼就会被读成「unlabeled 全消失了」
```

⚠⚠⚴⚠⚠ **⇒ 而那正是 §167.1 明令禁止的误读：⚠⚠⚴⚠⚠**
⚗⚠⚴⚠ **代理指标（unlabeled 归零）好看，⚗⚠⚴⚠ 而它既不是 P6 要的 correct，⚗⚠⚴⚠ 也不是提 cap 的效果 ——⚗⚠⚴⚠**
⚗⚠⚴⚠⚴ **它只是【只完成了 4 条】造成的。⚗⚠⁴⚗⚠⚴⚗⚠⚴**

⚠✅ **修法：加第三列「旧（同 N 条）」，让等 footing 的对比由脚本自己做出来。**

⚠ **修后的实跑输出**：

```
⚠⚠⚴ **两列的 n 不同（30 vs 4）⇒ 不可逐格相减。**
⚗⚠⚴⚠ **尤其别把「unlabeled 19 → 0」读成「unlabeled 消失了」——⚗⚠⚴⚠
⚗⚠⚴⚠ 那是【只完成了 4 条】造成的，⚗⚠⚴⚴ ⚠ **不是提 cap 的效果。⚠⚠⚴⚗⚠⚴⚠⚠**
           旧（全池）      旧（同 4 条）     新（同 4 条）
correct       7            4                4
wrong        4            0                0
unlabeled   19            0                0
n           30            4                4
⚠ **第三列才是能和新列比的那一列**（同 4 条）；⚗⚠ 第一列是全池 30 条，⚗⚠ 混看会得出错的结论。
```

⚠✅ **等 footing 一列一摆出来，「unlabeled 19 → 0」这个假象自己就散了** ——
⚗⚠ **同 4 条上，旧批也是 0 条 unlabeled、4 条 correct，⚗⚠ 与新批【完全一致】。⚗⚠⁴⚗⚠⚠⚠⚠⚠**

⚠⚠ **固化**：⚠⚠⁴ **任何「新旧对比」表，若两侧样本量不同，必须并列一列「旧（同 N 条）」。⚠⚠⁴**
⚗⚠⚴⚠ **否则「分母缩小」会被读成「指标改善」——⚗⚠⚴⚠ 而这两个在纸上长得一模一样。⚗⚠⁴⚗⚠⚴⚗⚠⚴⚗⚠⚴⚠⚠**

⚠ **本轮另一个自己犯的小错**：修的时候把警告行写成普通字符串、忘了格式化，
⚗⚠⚴ 印出了**未替换的 `%d`**，⚗⚠ **靠「扫残留占位符」抓到并修掉。⚗⚠⁴⚗⚠⚴**
⚗⚠⚴ **⇒ 输出里出现 `%d`/`%s`，就是格式化漏了一处；⚗⚠⁴ 这个 grep 便宜到应该每次都跑。⚗⚠⁴⚗⚠⚴**

### 171.3 ⚠ 校验 / 本节边界

- ⚠✅ **真 32768 产物端到端跑通**：身份闸放行、加载本地 R-27、判出 UNDERPOWERED、真实 exit=3
- ⚠⚠ **当前已完成 4 条 think 全是旧批本来就 correct 的** ⇒ ⚗⚠ **转化率仍 0/0（未测到 unlabeled）**
- ⚠✅ 差分脚本的误读陷阱已修（三列等 footing + 显式警告），⚠⚠ **已复跑确认输出正确**
- ⚠ **未改任何判据口径**：`P6_CORRECT_FLOOR` 仍 10、标签规则未动、`p6_readiness.py` 未动
- ⚠⚠ **本节仍不含任何关于「32k 能否救 P6」的结论** —— ⚗ **样本还没跑到那 19 条 unlabeled**
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
    print(f"  ⚠ 修订 170 段仍在：{'## 修订 170 ' in txt}")
    print(f"  ⚠ 修订 171 段已在：{'## 修订 171 ' in txt}")
    if not ok or "## 修订 171 " not in txt:
        print("[错误] 追加未生效 —— 不许当成成功")
        raise SystemExit(2)


if __name__ == "__main__":
    main()