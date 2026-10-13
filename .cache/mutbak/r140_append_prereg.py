"""把**修订 140** 追加到 R-6 预登记。

⚠ 本轮只做**可行性调研**，**不改任何判据**：
  待拍板项是「E1 第四档怎么处置」，而**能不能补那条断言**是它的前提。
  ⚠⚠⚴ 前提没查就让人拍板，等于把一个选项凭空排除掉。
"""

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / ".cache/xcheck/R6_RERUN_PREREG.md"

SECTION = """
## 修订 140 —— ⚠ **E1 第四档的可行性已实测**：说法为真、只是没验；「补独立断言」立得住

### 140.0 结论先行

⚠⚠⚴ **E1 的判据名没说假话 —— 页面确实会在缺数据时喊缺，而且是读者看得见的文案。
⚠⚠⚴ 但 E1 判的是 `typeof renderPathPanel === 'function'`，那个量在两种情形下都不动
⚠⚠⚴ ⇒ 它证不了自己名字里那半句。**

⚠⚠⚴⇒ **待拍板项的选项 B（把判据名改成只说它真核的那件事）方向就是错的**：
⚠⚠⚴⚠⁴ **那半句是真话，只是没人验。改名字等于把一句真话扔掉。**

⚠ **选项 A（补一条独立断言）在装置上可行，且功效极高** —— 实测见下。

### 140.1 ⚠ 为什么先查可行性再拍板

⚠⚠⚴ 待拍板项本来是二选一：
  ① 补一条独立断言核「缺数据时会喊缺」
  ② 把判据名改成只说它真核的那件事
⚠⚠⚴⚠⚴ **① 的成立与否是个事实问题，不是偏好问题。**
⚠⚠⚴ **没查就让人在①②里选，等于把一个选项凭空排除掉。**
⚠⚠⚴ ⇒ 本节只量可行性，**判决留给拍板**。

### 140.2 ⚠ 第一分支：`!S.path`（整份数据取不到）—— 实测

⚠ 手法：CDP `Network.setBlockedURLs` 拦掉 `*path_readout.json*`
（⚠ **页面实例级扰动，不改任何文件**，K2 族新增的手法）

| 量 | 对照（数据在） | 扰动（拦掉 json） | |
|---|---|---|---|
| `typeof renderPathPanel` | `function` | `function` | ⚠ **分不开** |
| `[data-pathblock]` 存在 | true | true | ⚠ **分不开** |
| `data-pathstate` | `ok` | **`no-data`** | ✅ 可区分 |
| 屏上出现「未载入」 | false | **true** | ✅ 可区分 |
| 屏上出现 `path_readout.json` | false | **true** | ✅ 可区分 |
| 屏上文字长度 | 1267 字 | **94 字** | ✅ |

⚠ 扰动态下读者实际看到的：

```
逐步路径数据未载入，这一屏解释缺失
缺的是 path_readout.json。它不影响「干预 vs 对照」那一屏的任何数
（那些数来自 divergence_readout.json）。
```

### 140.3 ⚠ 第二分支：数据在、但**这一题**没记录 —— 实测

⚠⚠⚴ 只验第一个空值分支就下结论，是**只验了一半**。
⚠ `renderPathPanel` 有**两个**空值分支（`index.html:1581-1594`）。
⚠ 手法：数据**照常载入**，只把当前这道题从 `S.path.problems` 里摘掉
（⚠⚠⚴ 落地核验两半都成立：`hadBefore=true`、`hadAfter=false`）

```
pid 1983_I_1 · data-pathstate = "no-problem" · 屏上 78 字
这份逐步路径数据里没有题目 1983_I_1 的记录
逐步路径只覆盖 5 道题，而当前选中的是另一道。
在左边「配对题目」里换成有记录的那几道之一就能看到。
```

⚠⚠⚴⚠⁴ **注意最后那半句是「可操作的指引」** —— 不只是「出错了」，
⚠⚠⁴ 而是**告诉读者下一步该怎么办**。⚠ 这是设计得好的空值分支。

⇒ **两个分支都出声，且都是读者看得见的文案。**

### 140.4 ⚠⚠⚴ 这恰好坐实了「第四档」

⚠⚠⚴⚠⚴ 回头看 §140.2 那张表的第一行：

> ⚠⚠⚴ `typeof renderPathPanel` **对照与扰动都是 `function`** —— ⚠ **分不开**。

⚠⚠⚴⚠⁴ 这就是第四档的**机制**，不是它的描述：
> ⚠⚠⚴ **E1 够得着（第一档的机械表现：删掉函数它就红），
> ⚠⚠⚴ 但它红的那个量在「缺数据」这个真正该被测的情形下根本不动。**

⚠⚠⚴⚠⁴ ⚠⚠⚴ 对照修订 133「变异已生效 ≠ 判据全绿」的反向：
> ⚠⚠⚴⚠⁴ **判据会红 ≠ 判据判对了它名字里的那件事。**

### 140.5 ⚠ 若拍板选①，新判据该怎么写（草案，本轮**未落地**）

⚠⚠⚴ 三条设计约束：

1. ⚠⚠⚴ **主体必须是读者看到的可见文案**，
   ⚠ 「未载入」「没有题目」「path_readout.json」这类；
   ⚠⚠⚴ `data-pathstate` 只作**交叉核对**（证明节点在，证明不了人看得见）。
2. ⚠⚠⚴ **两个分支都要测** —— 只测一个就是「只验了一半」（§140.3 的教训）。
3. ⚠⚠⚴ **手法要在扰动手法选型表里登记**：
   ⚠ `Network.setBlockedURLs`（整份数据缺）· ⚠ `delete S.path.problems[pid]`（单题缺）。
   ⚠⚠⚴ 两者都是**页面实例级、不碰文件**，⚗ 与「删 DOM」（会被重渲染冲掉）不同族。

⚠⚠⚴ **⚠ 一处连带效应要先说清**：拦掉数据后 `data-pathstate` 从 `ok` 变 `no-data`
⚠⇒ **A1（判 `state === 'ok'`）会连带转红。**
⚠⚠⚴⚠⁴ 这是**正确行为**（数据确实没了），⚠ 但它意味着这条新臂**不是纯臂**
⚠⚠⁴ ⇒ 归属要写成「一条扰动打两条，各自有各自的 RED 行」，⚗ 不是 C2 那种
⚠⚠⁴「扰动打了两条但只归给一条」。

### 140.6 ⚠ 守卫生效记录

- ⚠ **19 个守卫：17 exit=0 + 2 条有意判红**（本轮**未改任何被守卫的对象**）
- ⚠ 本轮只追加披露：**没改任何判据、没改任何产品、没碰任何产物**

### 140.7 待拍板

⚠⚠⚴ **本节把待拍板项的选项收窄了一个**：选项②（改名）已被实测否掉
⚠（那半句是真话），⇒ **只剩选项①**，且它在装置上可行、功效极高。

⚠ **要拍的是**：批不批这条新判据（写进 `verify_path.mjs` 属于**判据笔**，
⚠ 按修订 118/124 的规矩要**单独一笔 commit**，⚠ 不与取数混在一起）。

⚠ 其余待拍板项见修订 139 §139.7，未变。

### 140.8 校验

- ⚠ 预登记以换行结尾 / **U+FFFD 0**（原始字节层 + Python 解析后层）
- ⚠⚠⚴ **追加前后原文逐字节未变**
- ⚠ `verify_path.mjs` **原文件未动**；产物 `path_readout.json` 未动
- ⚠ 两个探针各自**身份自证过**（`href` 打印在导航之后、任何测量之前）
- ⚠ 第二分支的扰动**落地两半都实测**（`hadBefore=true` / `hadAfter=false`）
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
    print(f"  ⚠ 修订 139 段仍在：{'## 修订 139 ' in txt}")
    print(f"  ⚠ 修订 140 段已在：{'## 修订 140 ' in txt}")
    if not ok:
        raise SystemExit(2)


if __name__ == "__main__":
    main()