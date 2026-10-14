"""把**修订 166** 追加到 R-6 预登记。

本节：⚠⚠ **更正修订 163 的范围**（记的是 120 条，实际开跑 60 条 = 30 题）；
⚠ **判据改动**：`p6_readiness.py` 的批次身份集收进 32768（附牙齿 5/5 与改前 FAIL 的对照）；
✅ 顺带坐实「合并池会把结论翻过来」那条陷阱。
"""

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / ".cache/xcheck/R6_RERUN_PREREG.md"

SECTION = """
## 修订 166 —— ⚠⚠ **更正修订 163 的范围**；⚠ **判据改动：批次身份集收进 32768**（牙齿 5/5）

### 166.0 ⚠⚠⚠ **账本与现实不符，本节更正：不是 120 条，是 60 条**

⚠⚠⚴ **修订 163 写的是「一轮全量 120 条」。⚗⚠ 实际 17:00 开跑的是 60 条（30 题）。⚗⚠⚠⚠⚠**

⚠ **理由（不是省事，是判决只用这一半）：**
⚠ 预登记停止规则（修订 1）原文：**「停止点 = jsonl 顺序里的前 30 题（60 条轨迹）」**
⚠⇒ **判决只吃前 30 题**，⚗⚠ **跑满 60 题是 2 倍代价，而后一半不进判决。⚗⚠⚠⚠⚠⚠**

⚠⚠ **⚠⚠⁴ 好副作用：只跑 aime25 ⇒ 合并池陷阱【结构上不可能发生】。⚠⚠⁴**
⚗⚠ 因为合并池要两个 benchmark 都在场才谈得上「合并」，⚗⚠ **这里只有一个。⚗⚠⚠⚠⚠⚠**

⚠⚠⚠ **⚠⚠⁴ 本次拍板来源要写清：两个问卷都是【超时自动选中推荐项】，
⚗⚠⚴ `responseSource = automatic_timeout`、`explicitUserConfirmation = false` —— ⚗⚠ **不是用户点的确认。⚗⚠⁴⚠**
⚗⚠⚴ 两个选项都保守可逆（60 条 vs 120 条），⚗⚠⁴ 但**记账必须按实际来源写**，不许写成「用户要求」。⚗⚠⁴**

### 166.1 ✅ **「独占卡」是量出来的，不是说出来的**

⚠ 开跑前实测（16:59:30）：⚠⚠ **卡 0 / 卡 1 已被别人各占 30 GB；卡 3 是唯一空的。**
⚠⇒ ⚗⚠ **卡 0/1 直接出局**，⚗⚠⁴ **独占的那张是卡 3。**

⚠✅ **基线写进了 launcher 日志**（速率一旦异常，可归因到「被抢」而不是猜）：

```
[start] 2026-10-14 17:00:09
[torch] dev3 = RTX PRO 5000 72GB Blackwell freeMiB 72481
[gpu] 0 = 30010 MiB / [gpu] 1 = 30012 MiB / [gpu] 3 = 2 MiB, 0 %
```

⚠⚠ ⚗⚠⚴ **⇒ 这一条现在有【可复核的证据链】，⚗⚠⁴ 而不只是一句「我确认过是独占」。⚗⚠⁴⚗⚠⚴**

### 166.2 ⚠ 启动参数（三处「漏一处就前功尽弃」写进了脚本）

⚠ `--max-context 40960`（不写就崩，§164.1）｜⚠ 输出目录 `gen_b2_max32768`（不换就全被 SKIP）
⚗ 日志名 `gen_b2_max32768_zju53_cuda3.log`（**带机器标识**，§164.4 共享 NFS 同名日志会串台）
⚠ 输入 `problems_b2_first30.jsonl`（已校验：纯 aime25、p00–p29、**无重复**）

### 166.3 ⚠⚠⚴ **判据改动：批次身份集**（⚠⚠ 这是本节唯一动判据的地方）

⚠⚠⚴ **问题**：`p6_readiness.py` 的 `NEW_CAP = 8192`，
⚗⚠ ⇒ cap 32768 的批次会落进 `MISMATCH` 分支（`return 4`），
⚗⚠⚴⚠⚴⚠ **⇒ 花 4.8 h 算出来的数据，会被自己的身份闸当「身份不明」拒掉。⚗⚠⚴⚠⚠⚠⚠⚠**

⚠⚠⚠⚠⚴ **⚠⚠⁴ 错误的修法（我也差点这么改）：把 `NEW_CAP` 改成 32768。⚠⚠⁴⚠⚠⚴⚠⚠**
⚗⚠⚴⚠ **那样会让已有的 cap 8192 批次（`gen_b2` / `strict_label_b2_full60`）
反过来变成「身份不明」——⚗⚠ **那是倒退。⚗⚠⚠⚠⚠⚠⚠⚠⚠⚠**

⚠✅ **正解**：`KNOWN_NEW_CAPS = (8192, 32768)`，
⚠⚠ 判据写成「⚗⚠ **批次内 cap 全等** ⚗⚠ 且 ⚗⚠ 落在已知集合里」——
⚗⚠⚠⚠⚴⚠ **放宽成集合最容易顺手把「混池」也一起放宽了**，⚗⚠⚴⚠ **而混池正是 P0 明写要防的。⚗⚠⁴⚗⚠⚴**

⚠ **牙齿 5/5（`r166_teeth.py`），含改前对照**：

| 牙齿 | 改前 | 改后 |
|---|---|---|
| T1 纯 32768 | ⚠ **FAIL**（MISMATCH rc=4） | ✅ POOL_ONLY |
| T2 混 8192+32768 | ✅ MISMATCH | ✅ **仍 MISMATCH**（⚠ 最要紧） |
| T3 纯 8192 | ✅ 非 MISMATCH | ✅ 非 MISMATCH（回归护栏） |
| T4 纯 2048 | ✅ OLD_BATCH | ✅ OLD_BATCH |
| T5 `P6_CORRECT_FLOOR` | ✅ 10 | ✅ **仍是 10** |

⚠⚠ **改动发生在【看到任何 32768 数据之前】** ⚗⚠ —— 生成 17:00 才起跑，
⚗⚠ **而这道闸当时只会有一个结果：拒绝。⚗⚠ ⚠⚠⁴ 所以「先改了闸」这件事本身没有吃到结果的便宜。⚠⚠⁴**

⚠⚠⁴ **⚠⚠ 没动的东西（比动了什么更要紧）：⚠⚠⁴**
⚗ `P6_CORRECT_FLOOR = 10`（⚠ **P6 门槛原样**）｜⚗ `OLD_CAP = 2048`｜
⚗ `OLD_BATCH_BASELINE` 回归常量｜⚗ **标签规则仍是 `strict_label.label()` 唯一来源**

⚠✅ 回归：既有牙齿 `r152_teeth.py` **12/12 未破**（含 T3 混池仍 MISMATCH、T6a/T6b 合并池逻辑）。

### 166.4 ⚠✅ 顺带坐实：合并池**确实**会把结论翻过来

⚠ r152/r166 牙齿的 T3 顺带打出了 8192 批次的真实分布：

```
aime25 correct= 7   aime26 correct= 6   ← 两个都够不到 P6 的 10
合并池 correct=13                          ← 只有合并够格 ⇒ POOL_ONLY
```

⚠⚠⚴ **⇒ §修订 153 那条「合并池 13 看着够格、两个单池都不够」被再次实测坐实。⚠⚠⚴**
⚠⚠ ⚗⚠⁴ **⇒ 而这正是 §166.0 只跑 aime25 的另一个理由：⚗⚠⁴ 单池上根本产生不了这个假象。⚗⚠⁴**

### 166.5 ⚠ 校验 / 本节边界

- ⚠ 范围已与现实对齐：**60 条 / 30 题**，⚗ **不再写「全量 120 条」**
- ⚠ 拍板来源如实记：**超时自动选中**，非用户点选
- ⚠ 判据只动**批次身份集**；⚠⚠ **P6 门槛、标签规则、回归常量均未动**
- ⚠ 新牙齿 **5/5**、既有牙齿 **12/12**
- ⚠ **本节不含任何关于 32768 数据效果的结论** —— 那批数据还在跑（约 4.8 h）
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
    print(f"  ⚠ 修订 165 段仍在：{'## 修订 165 ' in txt}")
    print(f"  ⚠ 修订 166 段已在：{'## 修订 166 ' in txt}")
    if not ok or "## 修订 166 " not in txt:
        print("[错误] 追加未生效 —— 不许当成成功")
        raise SystemExit(2)


if __name__ == "__main__":
    main()