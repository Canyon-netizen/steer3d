"""把**修订 150** 追加到 R-6 预登记。

本节：把修订 149 §149.0 那次重算，做成**任何人可复跑**的脚本，
并给它配一颗牙齿测试（9/9）——⚠ 因为一个永远 PASS 的检查等于没有检查。
"""

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / ".cache/xcheck/R6_RERUN_PREREG.md"

SECTION = """
## 修订 150 —— ⚠⚠⁴ 把「可复算」做成脚本，并给它配牙齿测试（9/9）

### 150.0 ⚠ 起因：§149.0 那次重算只有「我跑过一次」，**别人复跑不了**

⚠ 修订 149 §149.0 证明了已入库的判决能对账，但那段是**一次性**的：
⚠⚠⁴ 没有脚本 ⇒ 下一个想复核的人得自己重写一遍，而**重写的人会踩同一个坑**
⚠⚠⁴⚠ （我自己就踩过一次 —— §149.1 把 `byDepth` 深度桶当成了标记数）。

⚠⇒ 新增 `.cache/xcheck/recheck_c4_denominator.py`：
从**原始产物**重算 C4 分母，与已入库的 `r148_run/panel_coverage.log` 对账。

```
$ python3 .cache/xcheck/recheck_c4_denominator.py
[root]   panel_blocks.json        354 个标记 / 542 个块 / page=root
[latent] panel_blocks_latent.json  38 个标记 / 183 个块 / page=latent
  root + latent（相加）      = 354 + 38 = 392
  两页交集                   = 1   ['data-arm']
  并集 = 相加 − 交集          = 392 − 1 = 391
  剔除框架内部 data-precedence = 391 − 1 = 390
  脚本算出 390 = 账本印的 390  ✅ 逐位对上
exit=0
```

⚠⚠⁴ ⚠ **口径写在脚本的输出里，而不是只写在注释里** ——
⚠⚠⁴⚠⚠ **下一个读代码的人会跳过注释去读数据**（修订 144 已记过同一条纪律）。
⚠⚠⁴ ⚗ **「并集 ≠ 相加」这一条尤其要印出来**：⚗⚠ 相加会虚高 1，
⚗⚠⚠ 而 390 与 391 的差别**看起来只是舍入**。

### 150.1 ⚠⚠⁴⚠⚠ 关键设计：脚本**自己拒绝**在不可信前提下出数字

⚠⚠⚴⚠ 修订 149 §149.2 查明 `scan_panel_coverage.py` 的 C0 抓不到「产物被换掉」。
⚠⚠⁴ ⚗ **⇒ 新脚本不能重犯同一个错。** 它带三道**身份**闸：

```
① age < 7200                    —— 拒「过期」
② 指纹：root 542 块/354 标记、latent 183 块/38 标记  —— 拒「被顶掉」
③ 产物自报 page 必须相符          —— 拒「跑错页」
⇒ 任一不满足 ⇒ 打印拒绝理由 + 补救命令，**exit 2，不出数字**
```

⚠⚠⁴⚠⚠ **⚗⚠⚠⚠ 最要紧的设计决定：指纹是**写死的常量**，
⚗⚠⚠ 而**不是「现算现比」。⚗⚠**
⚠⚠⁴ ⚠ **现算现比等于没有指纹** —— ⚗⚠ 产物被顶掉之后，
⚗⚠⚠ **任何规模都「自洽」**，脚本会高高兴兴印一个看起来正常的数。
⚗⚠⚴ ⚗⚠ **指纹该更新时的正确做法是改常量并写进预登记，而不是让脚本自己放宽。**

### 150.2 ⚠⚠⁴⚠⚠⚠ 牙齿测试 9/9 —— ⚠⚠ **「它会拒」本身必须被验证**

⚠⚠⁴⚠ **一个永远 PASS 的检查，和没有检查，在日志上长得一模一样。**
⚠⇒ `.cache/mutbak/r149_teeth.py`，逐条注入失效：

```
[PASS] G0 被测脚本语法可解析
[PASS] G1 基线 exit=0（应为 0）
[PASS] T1 规模不符(被顶掉)  exit=2  拒了，且理由指认到本条
[PASS] T2 产物已过期        exit=2  拒了，且理由指认到本条
[PASS] T3 自报页不符        exit=2  拒了，且理由指认到本条
[PASS] G2 三次注入后产物逐字节还原：True
[PASS] G3 还原后 exit=0（应回到 0）
[PASS] G4 期望值改成 999 后 exit=3（应为 3 且印「对不上」）
[PASS] G5 被测脚本逐字节还原：True
[PASS] G6 全部还原后 exit=0（应为 0）
RESULT recheck_teeth  OK 9/9
```

⚠⚠⁴⚠⚠ ⚗⚠ **T1/T2/T3 三条各有一次注入，每次只改一个变量**
⚠⚠ ⚗⚠ **而 T3 特别值钱**：⚗⚠ 它**只**改自报的 `page`、别的都不动 ——
⚗⚠ **若只靠数量就能骗过 T3，说明指纹只挡了规模没挡住身份。** ⚗ **它没骗过。**

⚠⚠⁴⚠⚠ G4 是另一条独立的方向：⚗ **期望值本身错时必须 exit 3（对不上），
⚠⚠⚴⚠ 而不是含糊地 PASS。** ⚗⚠ 一个只会说「对上了」的脚本，
⚗⚠⚴ **在账本被改动时会静静地盖章** —— ⚗⚠⚗ **那是最坏的一种绿。**

⚠⚠⁴⚠ ⚠⚠⚴⚠⚠ 测试要动**真实产物**，所以三条铁律写死在脚本里：
⚠⚠⁴ 1 改动前备份 → 2 `finally` 里按备份还原 → 3 还原后**逐字节核 sha256**。
⚗⚠⚠ ⚗ **第 3 条不是形式** —— ⚠⚠⚠⚠⚠ 另一处教训：`xargs -a` 在 BSD 上不支持，
⚗⚠⚴ `git rm --cached` **静默失败**，随后 amend 等于原样重提交，
⚗⚠⚴⚠⚠ **只有回读才发现。** ⚗⚠⚴ **「跑完了没报错」不等于「它生效了」。**

### 150.3 ⚠⚠⁴⚠⚠⚠ 但要说清楚：**这个洞没有被补上，只是不再由我踩**

⚠⚠⁴⚠⚠ ⚗⚠⚴ **§149.2 指出的洞在 `scan_panel_coverage.py` 里**，
⚗⚠⚴ **依然在** —— ⚠⚠⚴ C0 到现在仍然不读 `webglRequested` / `webgl`，
⚠⚠⚴ ⚗⚠ **任何人跑正牌扫描，被顶掉的产物照样能让它一声不吭地报出别的数字。**
⚠⚠⁴ ⚠ **本节没有碰判据。**

⚠⚠⁴⚠ ⚗⚠ **⇒ 准确的说法是：**
⚠⚠⁴⚠⚠ 「**我自己的那个复核脚本**现在有身份闸」，
⚗⚠ **不是「C0 现在有身份闸」。**
⚠⚠⁴⚠ ⚠⚠⚴ ⚗⚠⚴⚠ **把这两件事说混，就是拿一个脚本的改进冒充判据的改进 ——**
⚗⚠ ⚠ **而那正是 §148.4/§149.2 一直在记的那个病的复发。**

⚠⇒ 补 C0 的身份闸 = 加一条判决（产物必须匹配本次声明的模式）
⇒ ⚠ **改判据 = 新实验，需先写预登记。本节没有做，列为待拍板。**

### 150.4 ⚠ 校验

- ⚠ `recheck_c4_denominator.py` 实跑 exit 0，390 与已入库 log **逐位对上**
- ⚠ `r149_teeth.py` 实跑 **OK 9/9**；三条拒绝路径各自指认到对应原因
- ⚠ 三次注入后**真实产物逐字节还原**（sha256 核过），被测脚本亦然
- ⚠ 预登记以换行结尾 / 追加前后原文**逐字节未变** / **坏字 0**
- ⚠⚠⁴ **本节没有改 `scan_panel_coverage.py`、没改 `probe_panels.mjs`、没改任何产品**
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
    print(f"  ⚠ 修订 149 段仍在：{'## 修订 149 ' in txt}")
    print(f"  ⚠ 修订 150 段已在：{'## 修订 150 ' in txt}")
    if not ok:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
