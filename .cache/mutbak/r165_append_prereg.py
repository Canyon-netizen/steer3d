"""把**修订 165** 追加到 R-6 预登记。

本节：smoke **结果**出来了 —— ⚠✅ 机制成立（越过旧 cap 2.48 倍、自然写完），
⚠⚠⚠ **但它把 unlabeled 变成 wrong 而非 correct**，而 P6 卡的是 correct ≥ 10；
⚠ 速率实测比旧账快 8.8 倍，代价区间随之改写。
"""

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / ".cache/xcheck/R6_RERUN_PREREG.md"

SECTION = """
## 修订 165 —— ⚠✅ smoke **通过**：越过旧 cap 2.48 倍；⚠⚠⚠ 但 unlabeled → **wrong**，不是 correct；⚠ 代价区间改写

### 165.0 ✅⚠ **smoke 实测结果**（aime25 p04 = C 组，zju-53 卡 0，cap 32768 / context 40960）

| 项 | think | no_think |
|---|---:|---:|
| 生成 token | **20,360** | 1,737 |
| 旧 cap（8192）下 | 撞顶、`n_statements=0`、无答案 | — |
| 是否自然写完 | ✅ `### Final Answer` + boxed | ✅ |
| 模型答案 | 297 | -193 |
| ground truth | **279** | — |
| **对错** | ❌ | ❌ |
| 耗时 | 527.5 s | 45.9 s |

⚠✅ **机制成立**：20,360 = 旧 cap 的 **2.48 倍**，⚗ **自然写完、不再撞顶**。
⚠✅ `config.max_context = 40960` **已生效**（产物 config 内可核）⇒ §164.1 那道耦合闸确实必须一起过。

### 165.1 ⚠⚠⚠⚠⚴ **最要紧的一条：它把 unlabeled 变成了 wrong，不是 correct**

⚠ §163.3 那条「为什么提 cap」的推理链是：`unlabeled` 无法进 P6 ⇒ 提 cap 换标签。
⚠⚠⚠ **机制这一半被证实了；⚗⚠⚴⚠⚴⚠⚴ 但【换来的标签是什么】这一半，本轮的第一个数据点是 wrong。⚗⚠⚴⚠⚴⚠⚴⚠⚠**

⚠ P6 的硬约束原文：**correct 组 ≥ 10 条**（think 现为 **13**）。
⚠⚠⚴⚠⚴ **⇒ 把 39 条 unlabeled 转成 labeled，只有落在 correct 上才动得了这个约束。⚠⚠⚴⚠⚴**
⚗⚠⚴⚠⚴ **⇒ 若 C 组多数是模型本来就不会的题，提 cap 只会把 wrong 池灌大，correct 停在 13。⚗⚠⚴⚗⚠⚠⚴⚴⚴**

⚠⚠ **⚠⚠⚴ 这正是「代理指标涨了，而它要衡量的性质没涨」：⚠⚠⚴**
⚗⚠ **标签产出率会从 39 unlabeled 掉到接近 0 —— 那个数会非常好看，⚗**
⚗⚠⚴⚠ **而 P6 要的是 correct，不是 labeled。⚗⚠⚴⚠⚗⚠⚴⚠⚴**

⚠ **诚实的限度**：⚠⚠ **n=1**。⚠⚠ **「C 组多数会答错」目前是【一个观察】，不是结论。**
⚗⚠⚴⚠ **⇒ 它足以要求「别默认 32k 会救 P6」，⚗ 不足以要求「别跑 32k」。⚗⚠⚴⚠⚗⚠⚴⚠⚴⚠⚠⚠**

### 165.2 ⚠ **速率实测：比旧账快 8.8 倍，代价区间必须改写**

⚠ 两条**互相独立**的估计（同一张卡、同一次跑）：

```
think    527.46 s / 20,360 tok = 0.0259 s/token
no_think  45.90 s /  1,737 tok = 0.0264 s/token
```

⚠⚠✅ **两条互证 ⇒ 0.026 这个量级可信。**
⚠⚠⁴ ⚠⚠ **⇒ 而 §163.2 用的 0.227 s/token 是【卡被抢时】的速率（§修订 1 已记「抢占是主因」）。⚠⚠⁴⚠⚠⚠**

⚠⚠ **代价区间改写（120 条 = 60 think + 60 no_think）**：

| 口径 | 旧（0.227 s/tok） | 新（0.026 s/tok） |
|---|---:|---:|
| 最坏（全跑满 32768） | 124 h | **28.6 h** |
| 典型（按本条实测 20,360 / 1,737） | — | **9.6 h** |

⚠⚠⁴ ⚗⚠⚴⚠⚴ **⚠⚠⚴ 但这个 8.8 倍有一个前提，且它正是当初慢 3.4 倍的同一个原因：⚠⚠⚴⚗⚠⚴⚗⚠⚴**
⚗⚠ **卡被抢 ⇒ 速率回落 ⇒ 代价区间回落。⚗⚠⚴⚠⚠**
⚗⚠⚴ **⇒ 新数字只在「独占卡」下成立；⚗⚠⚴ 一旦有人上同一张卡，28.6 h 会往 124 h 方向走。⚗⚠⁴⚗⚠⚴⚗⚠⚴⚠**
⚠ **⇒ 整轮开工前要先问「这轮能不能独占卡」，⚗⚠⚴⚠⚴ 而不是问「卡型号对不对」。⚠⚗⚠⚴**

### 165.3 ⚠ 校验 / 本节边界

- ⚠✅ smoke 单题**通过**：越过旧 cap **2.48 倍**、自然写完、`max_context 40960` 生效
- ⚠⚠⚠ **但该题答案错**（297 vs 279）⇒ 提 cap 换来的标签**不是 correct**
- ⚠ 速率 0.026 s/token 双估计互证；⚠ **代价区间从 124 h/42 h 改写为 28.6 h/9.6 h，且只在独占卡下成立**
- ⚠ **本节不改任何判据口径、不改 FINGERPRINT、不改产品**
- ⚠ **整轮 120 条尚未启动**；⚠⚠ **本节不构成「该跑整轮」的结论 —— 那是用户的下一步拍板**
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
    print(f"  ⚠ 修订 164 段仍在：{'## 修订 164 ' in txt}")
    print(f"  ⚠ 修订 165 段已在：{'## 修订 165 ' in txt}")
    if not ok or "## 修订 165 " not in txt:
        print("[错误] 追加未生效 —— 不许当成成功")
        raise SystemExit(2)


if __name__ == "__main__":
    main()