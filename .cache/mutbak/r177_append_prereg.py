"""把修订 177 追加到 R-6 预登记。

本节三件事：
1. 作废本会话对 p06 的预期（我说过「p06 旧批是 unlabeled，抬 cap 就能说完」）
   —— 实测：p06 在 32768 下 n_tok=32768、truncated=True、strict=unlabeled，
   抬 cap 4 倍对它完全无效。
2. 基线的结构性事实：旧批 aime25 think 池 19 条 unlabeled 全部 truncated（19/19）。
3. 批次身份自证闸 r177_batch_identity.py：远端多批次文件名完全相同，traj 无分辨力，
   只有 cap 能分辨，故把「对着混批次出判决」做成可执行闸。

本节不含 P6 结论（§167：数据没跑完不许给结论；当前 14/60）。

⚠ 写这一版时刻意不用长串 ⚠ 装饰：上一版被写坏过（47KB、1 个 U+FFFD、三引号未闭合）。
"""

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / ".cache/xcheck/R6_RERUN_PREREG.md"

SECTION = """
## 修订 177 —— 作废「抬 cap 就能让 p06 说完」这条预期；旧批 unlabeled 与 truncated 是同一集合；新增批次身份自证闸

### 177.0 作废本会话说过的一句话（原话在对话里，现判无效）

**原话大意**：「p06 在旧批是 unlabeled，说明它被 8192 截断没来得及说答案；
新 cap 下它有空间跑完，有望转成 correct。」

**实测（真产物，已拉回本地逐条核对）**：

    traj                          mode      cap     n_tok  strict     truncated
    aime__aime25__p06__think      think     32768   32768  unlabeled  True
    aime__aime25__p06__no_think   no_think  32768    2033  wrong      False

- 结论 1：**抬 cap 4 倍（8192 -> 32768）对 p06 完全无效**。
  它不是「差一点说完」，是跑满 32768 仍未给出任何答案陈述。
- 结论 2：「需要多少 token」这个问题，在 8192 和 32768 两个点上都测过了，答案都是「不够」。
- 结论 3（边界）：**绝不许由 1 条推论 19 条**。19 条 unlabeled 里还有 18 条未测
  （当前只跑到 14/60）。p06 是第 1 个反例，不是「整体无效」的证明。

### 177.1 基线的结构性事实：旧批的 unlabeled 与 truncated 是同一个集合

旧批（cap=8192）aime25 池实测，逐条算，不做减法推断：

| 池 | n | correct | wrong | unlabeled |
|---|---:|---:|---:|---:|
| think | 30 | 7 | 4 | 19 |
| no_think | 30 | 4 | 23 | 3 |

- 19 条 unlabeled 里 truncated=True 的有 **19** 条，未触顶的 **0** 条。
  即 unlabeled 集合含于 truncated 集合，在旧批里两者是同一个东西。
- think 全池触顶率 **23/30 = 77%**。

对 32k 这一轮，同时是好消息和坏消息：

- 好消息：机制成立。旧批的 unlabeled 全是被 cap 截断造成的，
  抬 cap 确实给它们创造了「说完」的机会——而这一条原本是未经验证的假设。
- 坏消息：**机会不等于结果**。p06 已演示一次「给了机会仍没答对」。
  「不 truncated」与「correct」是两个条件，必须分别量、分别报。

P6 缺口（数字侧，重申，不作结论）：底线 think correct >= 10，现状 7，缺口 3。
候选只有那 19 条 unlabeled，转化率须 > 15.8%。

### 177.2 差点出事的地方：远端多个批次的文件名完全相同

`/home/zhourui/steer3d_bpath` 下实测（同名文件、不同目录、只有 cap 不同）：

| 目录 | aime__aime25__*.json 数 | cap |
|---|---:|---|
| gen_b2/ | 60 | 8192（旧批，对照） |
| gen_b2_max32768/ | 14（正在长） | 32768（本轮） |
| gen_smoke_32768/ | 2 | 32768（冒烟） |
| pilot8192/ | 4 | 8192 |
| teeth/ | 1 | — |

- `traj` 取自 `trajectory_id`（`strict_label_r167.py:105`），而**两批的 traj 命名一模一样**
  （`aime__aime25__pNN__think`）⇒ **`traj` 根本没有分辨力；唯一能分辨两批的字段是 `cap`。**
- `cap` 是从轨迹 JSON 自己的 `config` 读的（`:94` `cfg.get("max_new_tokens")`），
  不是脚本写死的常量 ⇒ 它是「我标的是哪一批」的真证据。
- 危险形态：一个 `gen_b2*/aime/*.json` 会把两批混成 120 条、traj 重复、cap 混杂，
  **而判决看起来完全正常**：有行数、有标签、有分数。

### 177.3 把「对着混批次出判决」做成可执行闸：r177_batch_identity.py

七条判据：行数 / cap 全等且等于本轮 / traj 无重复 / traj 形状合规 /
两臂齐全且等量 / 判据字段齐全 / truncated 与 cap 自洽。
身份不过 ⇒ 退出码 4，判决不许出。

双向证伪（恒绿不是绿；恒红且红错理由更坏）：

| 用例 | 输入 | 期望 | 实测 |
|---|---|---|---|
| A | 旧批 + 新批期望（cap 32768 / 60 行） | 红 | IDENTITY-FAIL，EXIT=4，3 条红 |
| B | 旧批 + 旧批期望（cap 8192 / 120 行） | 绿 | IDENTITY-OK，EXIT=0，7 条全绿 |
| C | 真产物（新批 14 条） | 只该行数红 | IDENTITY-FAIL，EXIT=4，只有「行数 = 14 != 60」红，其余六条绿 |

用例 C 最有说服力：它对真产物**只因为真正为真的那一条**而红（批次还没跑完），
**没有为假理由而红**。

附一条我自己犯、并且自己抓到的错：第一版把数据集正则写死成 aime25，
拿旧批（本来就含 60 条 aime26）去跑 ⇒ 恒红、且红的原因是错的 ⇒
**恒红且红错理由比恒绿更坏：它会让我否掉一个正确的文件。**
已改为可参数化（第 4 个命令行参数），并把判据名字改成跟着正则走
（否则就是「印出来的名字」与「实际量的东西」不一致，同 §168 那类）。

### 177.4 执行侧事实（本轮重新实测，不沿用记忆）

- 远端 `strict_label_r167.py` 与本地 `.cache/mutbak/strict_label.py`
  **md5 一致**：`1d74af82ab7010f048b7ae3aab88a09d`，均 6963 bytes。
- 远端标签脚本用 `globs` 位置参数取输入，**没有硬编码路径**
  ⇒ 风险不在「脚本写死」，而在「我传错 glob」，这正是 177.3 那道闸要拦的。
- 本轮一次 `-o` 写错（应为 `--out`）得到 EXIT=2 的用法错误，是干净的失败，非静默。
"""

HEADER = "## 修订 177 "


def main():
    before = PREREG.read_bytes()
    # ---- 追加前硬门 ----------------------------------------------------
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
        print("[错误] SECTION 首行不是「## 修订 177 」格式 —— 硬门，不追加")
        raise SystemExit(2)
    if HEADER in txt_before:
        print("[错误] 修订 177 段已存在 —— 硬门，不追加")
        raise SystemExit(2)

    sha_before = hashlib.sha256(before).hexdigest()
    n_before = txt_before.count("\n")
    PREREG.write_text(txt_before + SECTION, encoding="utf-8")

    after = PREREG.read_bytes()
    txt = after.decode("utf-8")
    ok = after[:len(before)] == before
    print("=== 追加结果 ===")
    print(f"  原文 {len(before):,} bytes / {n_before:,} 行 / sha256 {sha_before[:16]}")
    print(f"  现文 {len(after):,} bytes / {txt.count(chr(10)):,} 行")
    print(f"  原文逐字节未变：{ok}")
    print(f"  以换行结尾：{after.endswith(bytes([10]))}")
    print(f"  坏字（原始字节层）：{txt.count(chr(0xFFFD))}")
    print(f"  修订 176 段仍在：{'## 修订 176 ' in txt}")
    print(f"  修订 177 段已在：{HEADER in txt}")
    if not ok or HEADER not in txt:
        print("[错误] 追加未生效 —— 不许当成成功")
        raise SystemExit(2)


if __name__ == "__main__":
    main()