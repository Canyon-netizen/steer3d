# logit_lens.json 独立复算核验

产物 `frontend/public/latent/data/logit_lens.json`（`12ddcf8`）。复算用 numpy 1.26.4 独立实现
RMSNorm+unembedding，safetensors 手工解析 + mmap，未用 torch（未装）。脚本 `.cache/lensverify/*.py`。

## 结论速览

**数据可信，可以上页面。** 全部 1536 步的自报统计我用原始 npz + 权重重算，argmax 层面 bit-exact 吻合。
问题只在 `method` 里两句说明性数字复算不出，以及页面一个 `-1` 死分支。

## 1. 第 27 层能否复现真实 token

全量 1536 步，`argmax(W @ hidden_states[t,27,:])` vs `topk_indices[t,0]`：

| 指标 | 实测 | 自报 | 吻合 |
|---|---|---|---|
| 锚点命中（全量） | **1532/1536 = 99.74%** | 1532/1536 = 0.9974 | ✅ |
| 可判定步 margin≥1.0 | **1420/1420** | 1420/1420 | ✅ |
| max \|logit 误差\| | **0.12498** | 0.125 | ✅ |
| 48 条各自最后一步 | 48/48 | — | ✅ |

4 个失败步 `real_margin` **全为 0.0**（存盘 fp16 里 top1/top2 完全相等），全部 `decidable=false`，
`honest_caveat` 成立。

**两处前提要纠正：**
- **「40/40、0.10539」不是 JSON 的自报值。** JSON 写的是 1532/1536 与 0.125。「40/40」只在
  `index.html:927`、`:1606` 的**注释**里（作者 40 步抽查）；「0.10539」是第一步（`1983/no_think` t=752）的
  `anchor_logit_err` **逐点值**，非最大值——我重算该点 0.10536。
- **第 27 层不能再做 RMSNorm。** 我实测 `hidden_states[t,27,:] == last_hidden[t]` 逐位相同，即存的是 `model.norm`
  之后的量。按简报字面配方再归一化，48 步只中 34/48，误差 max 24.84。产物的不归一化是对的。

`topk_indices[t,0]` vs `token_ids[t]`：命中 1533/1536。npz 里两者本身有 3 处不等（采集批性质），
拿 `token_ids` 当标签会引入 ~0.4% 噪声底，产物选 `topk_indices[t,0]` 正确。

## 2. first_layer_correct 可信吗

定义（`build_logit_lens.py:203-208`）：`argmax[l]==final_id` 的**第一个**层号，28 层全错则 `-1`。
从 `per_layer.argmax`+`final_id` 重算 1536 步：`first_layer_correct` / `n_layers_correct` /
`per_layer.correct` / `monotone` **各 0 处不符**（monotone 我独立得 1136，与自报一致）。

**它衡量「第一次说对」，不是「稳定指向」。** ever_correct 1535 步里只有 1136 步单调。「第几层开始稳定指向」
须读 `monotone`+`n_layers_correct`。`monotone` = 一旦说对则之后每层都对（无回退）。

## 3. 覆盖边界

48 npz ↔ 48 JSON，一一对应无缺失。`T` 从 **265 到 2048**。全部 48 条 `window==[T-32,T]`、32 步、
`t` 连续覆盖 `[T-32,T-1]`，**无一条不足 32**。`real_margin` 逐点 == npz `topk_logits[t,0]-[t,1]`
（fp16→f32），1536/1536 吻合；`tok` 逐点 == `vocab[final_id]`，同样全中。
`decidable` = `real_margin>=1.0`：1420 可判定 / 116 不可判定。`real_margin` **就是** top1−top2 的 logit 间距。

## 4. per_layer 的字段

是 **dict**，每个值 28 长（索引=层号）：

| 字段 | 含义 | 量纲 |
|---|---|---|
| `argmax` | 该层说的 token id | int |
| `p_argmax` | 该层 softmax 后 argmax 的概率 | 概率 5 位小数 |
| `p_final` | 该层 softmax 后**最终 token** 的概率 | 概率 5 位小数 |
| `margin` | 该层**自己**的 top1−top2 间距（**非**与 final_id 的间距） | logit 4 位小数 |
| `correct` | `argmax[l]==final_id` | bool |

抽 2 轨迹 × 32 步 × 28 层用原始 npz 重算：`argmax`/`correct`/`first_layer_correct`/`n_layers_correct`
**64/64 bit-exact**；`p_*` 差 ≤9.7e-4、`margin` ≤2e-4，纯 float32 累加顺序（产物 `X@W.t()`，我用 `W@x`）。

## 发现的不一致

1. **`method.note_final_layer` 的「值 ~34.9 logits」复算不出。** 候选量全非 34.9：max 24.84 / mean 15.00 /
   median 15.47 / 选中 token 上 max 18.40 / ‖Δx‖₂ max 262.6 / 平均 1−cos 0.1415 / L27 logit 全幅 66.5。
   同句在 `index.html:1609` 重复。
2. **「命中率掉到 85%」对不上。** 同 scope（首轨迹 step 1..160）我测 **76.9%**（123/160）；post-norm 的
   98.8%（158/160）吻合 → scope 没错，是 85% 本身错。
3. `storage_dtype_note` 称「~0.09 logits (median)」：中位实测 **0.0769**、均值 0.0835。量级对，措辞不准。
4. 页面死分支：`index.html:1735` 判 `flc != null`，但产物有 1 步 `first_layer_correct = -1`
   （`1991/think` t=2046）。`-1` 非 null，故「28 层里没有一层说对过」**永不触发**，改渲染成「第 **-1** 层开始就说对了」。
5. 3 步 `flc>=0` 但 L27 错（`1984/think` t=1011、`1989/think` t=2037、`2000/think` t=2027）——即 3 个
   `anchor_ok=false` 步。数据没错、`:1754` 也打了红字，但 caption 说「第 N 层开始说对」而 L27 柱是灰的。

## 页面可用但目前没用的字段

lens 面板现只读 `per_layer.argmax`、`final_id`、`first_layer_correct`、`t`、`tok`、`anchor_ok`、
`agg.first_layer_correct_hist`（`index.html:1722-1792`）。以下全部闲置：

- **`per_layer.p_final`** — 信息量最大的闲置字段。0/1 柱图丢了强度：跨步均值 L0 0.00019 → L18 0.126 →
  L20 0.355 → L22 0.695 → L27 0.936，可直接当参考曲线叠柱图或驱动 3D 颜色。
- **`per_layer.margin`** — 每层自己的确定度。与 p_final 配对才能区分「确信但确信别的词」vs「两词间摇摆」，
  判别一次 0/1 转折是硬是软全靠它。
- **`per_layer.argmax` 的词本身** — 现在只画绿/灰柱。`vocab.json` 在手，列 28 个词即可分辨「逐层换词」vs「早早锁定再微调」。
- **`monotone` / `n_layers_correct`** — 区分「第 21 层第一次对」与「21..27 全对」（1535 vs 1136 步）。
  `monotone` 是干净布尔量，适合 3D 点着色。
- **`real_margin` / `decidable` / `anchor_ok` / `anchor_logit_err`** — 3D 点置信度着色。116 步 `decidable=false`、
  4 步 `anchor_ok=false`，不区分会让用户点到模型本身没定下来的 token。
- **`aggregate.by_mode`** — think/no_think 的 monotone 561/768 vs 575/768，差异小，不值得单独一屏。

## 置信度边界

**实算：** 全部 1536 步的 L27 锚点（argmax、logit 误差、decidable 分母、4 个失败步明细）；48 条各自最后一步；
2 条完整轨迹 × 32 步 × 28 层（1792 次读出，argmax bit-exact）；1536 步的 first_layer_correct / n_layers_correct /
monotone / correct 与**全部 aggregate 直方图**（含 by_mode、committed、per_layer_mean_p_final，逐字段全等）；
48 条 T / window / t 连续性 / real_margin / tok 对 npz 的一致性；`lm_head==embed_tokens`（max|diff|=0）；
`hidden_states[:,27,:]==last_hidden[t]`。

**没算：** 剩下 46 条轨迹的 28 层完整重算（13 TFLOP，没跑）。故「1532/1536」覆盖全部 48 条，
而「per_layer 逐层 bit-exact」只覆盖 2 条。

**读 JSON/源码才信的：** `margin` 是「该层自己的 top1−top2」来自 `build_logit_lens.py:196-235` 的代码语义，
虽数值复现但非数据自证。

**假设：** 第 27 层为 post-norm。实测支持（不归一化 99.74%，归一化掉到 71%），但「npz 来自
`output_hidden_states=True` 故含 final norm」是我从数据一致性反推，**未读采集脚本**。

**另注：** `git status` 里 `frontend/{app/page.tsx,components/ControlPanel.tsx,lib/store.ts}` 与新增的
`LayerDerivationPanel.tsx` **不是我改的**（本会话只写 `.cache/lensverify/`，已 gitignore），推测为并行 worker。
