"""把**修订 164** 追加到 R-6 预登记。

本节：执行侧四个新事实 —— ⚠⚠ `max_context` 与 `max_new_tokens` **耦合**（不一起抬就崩）；
zju-54 **崩**且整台不可用；zju-53 恢复 ⇒ **跨型号偏离不再必要**；
⚠⚠⚠ 共享 NFS 让**旧日志冒充现状**，我连读两次。
"""

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / ".cache/xcheck/R6_RERUN_PREREG.md"

SECTION = """
## 修订 164 —— ⚠⚠ 执行侧四个新事实：**cap 与 context 耦合**、zju-54 **崩**、zju-53 恢复、⚠⚠⚠ 共享 NFS 旧日志

### 164.0 ✅ **采集脚本本体定位到了**（此前一直只有 `[collect]` 前缀）

⚠⚠⁴⚠ **`run_bpath.sh` 的注释里就写着路径**，而日志里当然不会有：

```
COLLECT=/home/zhourui/steer3d/backend/examples/collect_qwen3_aime.py
用法: bash run_bpath.sh <max_new_tokens> <batch_tag> <device_cvd>
```

⚠✅ **md5 两边一致**（本地仓库那份 = 远端在跑那份）：
`b935d00125840e23aa2de578d9ebcad4`，**均 18,673 bytes**。
⚠⚠ ⚗⚠⚴⚠⚠ **⇒ 本地 `backend/examples/collect_qwen3_aime.py` 可以直接当事实源读，不必再上远端。⚗⚠⚴⚠⚠⚠⚠⚠**

⚠ **wrapper 里另两条规矩**（本轮沿用）：`PYTHONDONTWRITEBYTECODE=1`（不许在远端树里生成 pycache）；
⚗ **日志名必须带批次标识**（后台进程不随后台任务死）。

### 164.1 ⚠⚠⁴⚠⚴⚠⚠ **cap 与 context 是【耦合】的 —— 只抬 cap 会崩，不是「少跑一点」**

⚠⚠⚠ **这一条是第一版完全没看到的，写在这里是因为它能让整轮 42–124 h 直接归零。**

⚠ wrapper 的参数：**`--max-new-tokens` 是参数，`--max-context 16384` 是写死的常量。**

⚠ 而脚本 `generate_full` 的第 149–152 行：

```
if input_ids.shape[1] >= max_context - max_new_tokens:
    keep = max_context - max_new_tokens - 1
    input_ids = input_ids[:, -keep:]
```

⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠
⚗ **代入 cap=32768：`keep = 16384 - 32768 - 1 = -16385`，**
⚗ **⇒ `input_ids[:, 16385:]`，而 prompt 只有 ~108 token ⇒ 空切片 ⇒ 模型拿到空输入。⚗**
⚗⚠⚴⚠ **⇒ 不是「被截到 16384」，是直接崩。⚗⚠⚴⚠**
⚠⚠ ⚗⚠⚴ **⇒ 处方：`--max-context 40960`（= `max_position_embeddings`，config 已核）。⚗⚠⚴⚠**

⚠ **这不是「一次改了两个变量」**：⚗ `max_context` 是 cap 的**机械后果**，不改它 cap 就不生效。
⚠⚠ ⚗⚠⚴⚠⚠ **⇒ 但它确实是两次改动，所以**必须一起记、一起审**，不能只审 cap 那一半。⚗⚠⚴⚠⚠⚠⚠⚠**

### 164.2 ⚠ **zju-54 崩了，而且是整台机器不可用（不是参数错）**

⚠ 首轮 smoke 落在 zju-54 的空卡上，报：

```
RuntimeError: The NVIDIA driver on your system is too old (found version 12080)
```

⚠⚠ **根因实测**（同机当场测）：

| 项 | 值 |
|---|---|
| 驱动 | **570.133.07** ⇒ 最高 CUDA **12.8** |
| torch | **2.11.0+cu130** ⇒ 按 CUDA **13.0** 编译 |

⚠⚠⚠⚠⚴ **⇒ zju-54 上 `easysteer` 环境的 torch 根本初始化不了 CUDA，整台不可用。⚠⚠⚠⚠⚴**
⚠ ⚗⚠⚴⚠ **处置**：⚗ **不换环境**（原批 b2 就是用 `easysteer` 跑的，换 env 等于把栈也换掉，
⚗⚠⚴⚠⚴⚠⚴ 那比换机器更大的偏离）⇒ **换机器、不换 env。⚗⚠⚴⚠⚴⚠⚴**
⚠✅ 对照：zju-53 / zju-57 驱动均为 **580.178.04**（支持 CUDA 13.0）⇒ 兼容。

### 164.3 ✅⚠ **zju-53 恢复 ⇒ 跨型号偏离不再必要**（第二问自动作废）

⚠ 上一轮我报「zju-53 连续 6 次超时不可达」——⚠⚠ **那是真的，但只持续了约 40 分钟**：

⚠✅ **它回来了，而且 0/1/3 号 RTX PRO 5000 72GB Blackwell 全部空闲**（2 MiB / 0%）：

```
0, NVIDIA RTX PRO 5000 72GB Blackwell,  2 MiB, 73415 MiB, 0 %
1, NVIDIA RTX PRO 5000 72GB Blackwell,  2 MiB, 73415 MiB, 0 %
3, NVIDIA RTX PRO 5000 72GB Blackwell,  2 MiB, 73415 MiB, 0 %
```

⚠⚠⁴ ⚗⚠ **⇒ 可以跑在原批【同一型号】上 ⇒ 跨型号偏离整个消失 ⇒ §163 第二个待拍板项作废。⚗⚠⚠⁴⚠⚠**
⚠⚠ ⚗⚠⚴ **⇒ 上一轮那个「只能上 3090」的方案是有前提的，而那个前提已经不成立。⚗⚠⚴⚗⚠**
⚠ ⚠ CVD 映射两种顺序都核过（`PCI_BUS_ID` / `FASTEST_FIRST` 结果一致），⚗ 并在启动脚本里**显式固定**
`CUDA_DEVICE_ORDER=PCI_BUS_ID`，⚠⚠ **不凭记忆指定 CVD**（§163.3 ②）。

⚠ **同时更正我上一轮的一句错话**：⚠⚠⚴ 我说「zju-57 八张全有显存占用、**无一张全空**」——
⚗⚠⚴⚠⚴ **那是我自己设的「全空 / 全占」二元标准，不是判据。⚗⚠⚴⚠⚴⚗⚠⚴⚠**
⚗ wrapper 自己的注释就写着「**快照余量不是可用余量，但模型只要 3.4G，够用即可**」——
⚗⚠⚴⚠ 78 GB 的卡占掉 19 GB，余量远够。⚗⚠⚴ **⇒ 该问的是「余量够不够」，不是「是不是全空」。⚗⚠⚴**

### 164.4 ⚠⚠⁴⚠⚴⚠⚴ **共享 NFS ⇒ 旧日志冒充现状，我连中两次**

⚠⚠⚠ **新事实：`/home/zhourui/steer3d_bpath` 就是共享 NFS**（进程 fd 实测）：

```
1 -> /data/zju-130/zhourui/steer3d_bpath/smoke_32768_cuda0.log
2 -> /data/zju-130/zhourui/steer3d_bpath/smoke_32768_cuda0.log
```

⚠⚠⚠⚠ **⇒ zju-54 崩在里面的那份日志，zju-53 上【原样可见】。⚠⚠⚠⚠**

⚠⚠⚠⚠⁴ **而我连读两次，每次都当成 zju-53 的现状：⚠⚠⚠⚠⁴**

```
第一次  launcher 只有「Python 3.12.13」⇒ 脚本还没到重定向那步
        主日志：完整 driver too old traceback   ← ⚠ 这是 zju-54 的旧文件
第二次  torch 自检说 cuda 13.0 / avail True / dev0 RTX PRO 5000 Blackwell
        主日志：同一份 traceback               ← ⚠ 还是旧文件
```

⚠⚠⚠⚠ ⚠⚠⚴⚠⚴ **两个事实直接矛盾时，我选了「相信日志」而不是「怀疑日志的年龄」。⚠⚠⚴⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠**
⚠⚠⚠⚠⚠ **判别式：⚗⚠⚴ 多机共享存储上，日志的【内容】不能单独证明它是【这次】的。⚗⚠⚴⚠⚠⚠⚠⚠⚠**

**固化（本轮照做才查出来的）：**

1. ⚠⚠⁴ **跨机读日志必须核 mtime，且 mtime 要比「本机启动时刻」新。**
2. ⚠⚠⁴ **判进程真伪用 `ps` 与 `/proc/<pid>/fd`，不要用日志内容。**
3. ⚠⚠ **多机共用存储 ⇒ 日志文件名必须带机器标识**（现在只带批次与卡号，⚗⚠ **两机同名**）。

⚠ 真相是靠三条独立证据定下的，⚗⚠ **不靠日志**：
`ps` 进程在跑（etime 递增）/ 日志 **0 bytes** 且 mtime 已刷新 / `grep -c 12080` = **0**。

### 164.5 ⚠ **两个「不是崩」的分辨**（装置没坏，是慢）

⚠ smoke 在 zju-53 起初 5 分钟**显存 2 MiB、日志 0 字节、进程 `DNsl`** ⇒ 看着像卡死。
⚠⚠⁴ **实测排除了卡死**：15 秒内 `/proc/<pid>/io` 的 `read_bytes` **涨了 1.02 GB**（约 68 MB/s）
⇒ ⚗⚠⚴ **它在从 NFS 拉模型权重**（`~/.cache/huggingface` 也在同一 NFS 上）。
⚗⚠⚴ `wchan=folio_wait_bit_common` = ⚗⚠ **在等页缓存，不是死锁**；内存 503 GB 充裕（available 486）。
⚠ **判据**：⚠⚠ **「没进展」要区分「没动」和「在动但没产出」。⚠⚠**
⚠⚠ ⚗⚠⚴ 旁证：`head -c 8000000 baseline.json` 瞬间读完 ⇒ ⚗⚠ **NFS 本身不慢，是模型文件冷。⚗⚠⚠⚠**
⚠⚠⁴ ⚗⚠⚴ **⇒ 冷启动要按 NFS 冷读算，不能按缓存热读算；⚗⚠⚴ 这是整轮 42–124 h 之外的额外固定开销。⚗⚠⁴**

⚠ 后来状态码从 `D` 变 `R`、显存 **4214 MiB / 29%**、日志出现 `[1/1] think p04 …` ⇒ **生成正常开始。**

### 164.6 ⚠ 校验 / 本节边界

- ⚠ **smoke 单题（aime25 p04 = C 组，`n_statements=0`）已在 zju-53 卡 0 起跑**，参数：cap 32768 / context 40960 / bf16 / seed 42
- ⚠ **判据口径未动**：本节没改任何判据、没改 FINGERPRINT、没改产品
- ⚠ **smoke 结果未出**：⚠⚠ **本节只记「已发生的故障与约束」，不记任何关于 32k 有效性的结论** ⚠⚠
- ⚠⚠ **待验的里程碑只有一个**：⚗ **能不能越过 8192 token 继续生成**（旧 cap 的绑定点）
- ⚠ **C 组定义已独立复现**：think 60 = A 11（correct 8）+ B 10（correct 5）+ C **39**，
  ⚗⚠ 且「`boxed=0 且撞 cap`」与「`stated is None 且撞 cap`」给出**同一集合**（39 条）
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
    print(f"  ⚠ 修订 163 段仍在：{'## 修订 163 ' in txt}")
    print(f"  ⚠ 修订 164 段已在：{'## 修订 164 ' in txt}")
    if not ok or "## 修订 164 " not in txt:
        print("[错误] 追加未生效 —— 不许当成成功")
        raise SystemExit(2)


if __name__ == "__main__":
    main()