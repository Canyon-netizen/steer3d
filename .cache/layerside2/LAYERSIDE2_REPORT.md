# off-by-one 到底改变了多少可测量的东西

Qwen3-1.7B，28 block，48 条 AIME 轨迹，**69155 步**（无 padding，见 §6.1）。
全部测量在本机 Mac CPU 上重跑，未申请 GPU，未触碰任何 NFS 挂载，
未修改任何产品代码、未 commit、未改
`docs/STEERING_INTERPRETABILITY_FRAMEWORK.md`。

**唯一权威数值源：`layerside2.json`。** 本报告不新增任何数字，每个数字后面
标注它来自 `layerside2.json` 的哪个键。逐值对账见 §7（236 条声明，236 条通过）。

复跑顺序（每个脚本顶部也有说明）：

```
python3 .cache/layerside2/s1_cache_facts.py    # 单遍抽层 + 层语义核验 + 范数
python3 .cache/layerside2/s1b_vectors.py       # L12..L15 的 4 条 contrast 方向
python3 .cache/layerside2/s2_probe.py          # 读出层 × 向量层的 2×4 网格
python3 .cache/layerside2/s3_injection_amp.py  # 注入点幅度
python3 .cache/layerside2/s4_consolidate.py    # 合并成 layerside2.json
python3 .cache/layerside2/s5_audit_values.py   # 逐值对账
```

统一口径：`λ=0.01`、轨迹内去均值、stride=2、`k_pca=256`、留一轨迹（每折重解 w）、
逐折配对的中位数 —— 与 `.cache/rolesverify/probe_axes.json` 出 0.412/0.308 的那一格完全一致。

**两种余弦口径。** `probe_axes` 报的是 `|w_n · normalize(Pᵀv)|`（先按天花板
`‖Pᵀv‖` 归一，下称 `pca_norm`）；真 2048 维余弦是 `pca_norm × 天花板`（下称
`dspace`）。两者在 768 个格子上恒等，最大误差 **2.8e-16**
（`conventions.identity_max_abs_err`）。已发表的 0.412/0.308 是 `pca_norm`；
下文结论用 `dspace`，并同时给出 `pca_norm`。

---

## 0. 一句话答案

| | confidence → 熵 | caution → 回退 |
|---|---|---|
| 已发表（Lr=14, Lv=14, pca_norm） | **0.4125** | **0.3077** |
| 同一格换成真 2048 维余弦（dspace） | 0.4121 | 0.3039 |
| **在注入点重测（Lr=13, Lv=13, dspace）** | **0.4166**（+0.0045, **+1.1%**） | **0.3065**（+0.0026, **+0.9%**） |
| 只把向量挪到 L13（读出仍在 L14） | 0.3782（−0.0339, −8.2%） | 0.2735（−0.0304, −10.0%） |
| 只把读出挪到 L13（向量仍在 L14） | 0.4065（−0.0057, −1.4%） | 0.2989（−0.0050, −1.7%） |

**方向层面：几乎没变。** 在注入点重测两条已发表结论分别只动 1.1% 和 0.9%，
仍然远超同格位置对照（38.1× / 171.0×）和 400 随机方向地板（0.075 / 0.080）。
Δ=20 的塌陷形状也逐位复现。

**标量层面：变了，而且是唯一真正变了的东西。** 注入点相对幅度 0.2358
（标称 0.2 的 1.179 倍），同层几何代价从 2.07% 涨到 2.87%（**+39%**）。

**对「改注入点是否值得重跑」：不值得。** 见 §8。

---

## 1. 复现基线：6 个发布向量逐位重建

判据不是「cos 差不多」，而是 **`n_positive` / `n_negative` 逐个相等** 且 cos > 0.999。
分组谓词逐字照搬 `compute_steering_vectors.py`，跳过每个轨迹的前
`n_prompt_tokens` 个 token（Σ = **6356**，69155 − 6356 = **62799** 个进入分组；
`item1_baseline_reproduction.sum_n_prompt_tokens` /
`.n_tokens_after_n_prompt_skip`）。

| 方向 | n_positive（发布=重算） | n_negative（发布=重算） | cos(重算 L14, 发布) | JSON 键 |
|---|---|---|---|---|
| confidence_up | 20930 = 20930 | 15718 = 15718 | 0.9999999999998 | `item1_baseline_reproduction.per_axis.confidence_up` |
| reasoning_deep | 15679 = 15679 | 15679 = 15679 | 0.9999999999986 | `…per_axis.reasoning_deep` |
| caution | 379 = 379 | 62420 = 62420 | 0.9999999999979 | `…per_axis.caution` |
| creativity | 40338 = 40338 | 22461 = 22461 | 0.9999999999973 | `…per_axis.creativity` |
| confidence_down | 派生 | 派生 | cos(发布, −confidence_up) = **1.0000000000000** | `…per_axis.confidence_down.cos_published_vs_neg_base` |
| reasoning_shallow | 派生 | 派生 | cos(发布, −reasoning_deep) = **1.0000000000000** | `…per_axis.reasoning_shallow.cos_published_vs_neg_base` |

**6/6 复现**（`item1_baseline_reproduction.all_reproduced = true`）。
两条负向派生方向 cos 恰为 −1.0000000000000 对发布基向量 —— 确认
`confidence_down ≡ −confidence_up`、`reasoning_shallow ≡ −reasoning_deep`，
**只有 4 条独立轴**。

### 1.1 顺带修正上游一处不自洽

上游 `layer_side_forensics.json` 同时给了 `cos_recomputed_L13_vs_L14 = 0.95649`
与 `cos_stored_vs_recomputed/14 = 0.99896`。既然发布向量就等于 `v_L14`，
这两者本应给出同一组数；它们不等，说明那次重算的 `v_L14` 并不是发布向量。
修正后（发布向量重建到 1−2e-12）：

| 轴 | cos(发布 v_L14, 重算 v_L13) | cos(v_L13, v_L14) | 差 |
|---|---|---|---|
| confidence_up | 0.9551222 | 0.9551222 | 7.0e-09 |
| caution | 0.9420589 | 0.9420589 | 1.2e-08 |
| reasoning_deep | 0.9121105 | 0.9121104 | 3.6e-08 |
| creativity | 0.9143342 | 0.9143344 | 1.3e-07 |

（`item2_vector_across_layers.identity_published_L13_equals_L13_vs_L14`；
残差量级是发布 `.npy` 为 float32 所致。）

**所以任务书里「相邻层 cos = 0.9565」与「磁盘向量 vs L13 = 0.9546」这一对
「已确证」数字，本身互不自洽；正确的单一数值是 0.9551（confidence）/ 0.9421（caution）。**

---

## 2. 向量本身随层的变化

`cos(v_Li, v_Lj)`（`item2_vector_across_layers.adjacent_cos`）：

| 轴 | L12↔L13 | **L13↔L14** | L14↔L15 |
|---|---|---|---|
| confidence_up | 0.9511 | **0.9551** | 0.9236 |
| reasoning_deep | 0.9145 | **0.9121** | 0.8868 |
| caution | 0.9412 | **0.9421** | 0.8962 |
| creativity | 0.9259 | **0.9143** | 0.8397 |

`cos(发布 L14 向量, 重算 v_Lv)`（`item2_vector_across_layers.cos_published_L14_vector_vs_recomputed`）：

| 轴 | v_L12 | **v_L13** | v_L14 | v_L15 |
|---|---|---|---|---|
| confidence_up | 0.9080 | **0.9551** | 1.0000 | 0.9236 |
| caution | 0.8876 | **0.9421** | 1.0000 | 0.8962 |
| reasoning_deep | 0.8570 | 0.9121 | 1.0000 | 0.8868 |
| creativity | 0.8597 | 0.9143 | 1.0000 | 0.8397 |

**读法：把向量的定义挪一个 block，方向只偏 4.4%（confidence）／5.8%（caution）。**
L12→L13 与 L13→L14 大致同量级，L14→L15 掉得更多，所以 14 附近正好是一个
局部高原 —— 14 选得不算差。

---

## 3. 读出方向随层的变化（核心）

把**读出层 Lr**（w 由哪一层的隐状态拟合）与**向量层 Lv**（与 w 比余弦的
steering 向量取自哪一层）解耦。已发表的 0.412/0.308 在 **Lr=14, Lv=14** 这一格。

### 3.1 Δ=0 的 2×4 网格（dspace，`item3_readout_grid.grid`）

**confidence → `top1_prob_renorm`（熵的重述）**

| 读出层 Lr ＼ 向量层 Lv | L12 | **L13** | L14 | L15 | oof Pearson | 位置对照（同格） | 阴性地板 |
|---|---|---|---|---|---|---|---|
| **L13** | 0.3742 | **0.4166** ← | 0.4065 | 0.3727 | +0.5135 | 0.0109 | 0.0754 |
| **L14** | 0.3360 | 0.3782 | **0.4121** ←已发表格 | 0.3626 | +0.5203 | 0.0114 | 0.0752 |

**caution → `backtrack_topk`**

| 读出层 Lr ＼ 向量层 Lv | L12 | **L13** | L14 | L15 | oof Pearson | 位置对照（同格） | 阴性地板 |
|---|---|---|---|---|---|---|---|
| **L13** | 0.2942 | **0.3065** ← | 0.2989 | 0.2669 | +0.6709 | 0.0018 | 0.0799 |
| **L14** | 0.2649 | 0.2735 | **0.3039** ←已发表格 | 0.2524 | +0.6760 | 0.0016 | 0.0709 |

两条轴的对角线在 Δ=0 都**翻到了 L13**（注入点那一层）——
向量与读出放在同一层时对齐最好，这符合预期。上表的 `←` 标记是对角最大格。

### 3.2 已发表的两个 cos 变成多少？差多少？

| 口径 | confidence | caution |
|---|---|---|
| 已发表（pca_norm, Lr=Lv=14） | 0.4125 | 0.3077 |
| 同一格改用 dspace | 0.4121 | 0.3039 |
| **注入点重测（Lr=Lv=13, dspace）** | **0.4166**，Δ=**+0.0045**（**+1.1%**） | **0.3065**，Δ=**+0.0026**（**+0.9%**） |
| 只换向量层（Lr=14, Lv=13） | 0.3782，Δ=−0.0339（−8.2%） | 0.2735，Δ=−0.0304（−10.0%） |
| 只挪读出层（Lr=13, Lv=14） | 0.4065，Δ=−0.0057（−1.4%） | 0.2989，Δ=−0.0050（−1.7%） |
| 对位置对照的倍数（注入点格 / 已发表格） | 38.1× / 36.1× | 171.0× / 189.0× |
| 阴性地板（400 随机方向 max） | 0.0754 / 0.0752 | 0.0799 / 0.0709 |
| 已付搜索成本的 p | 0.0000 | 0.0000 |

**答案：在注入点重测，0.4125 → 0.4166、0.3077 → 0.3065（pca_norm 口径）。**
变动 +1.1% / +0.9%，两条都仍然是对照的 38× / 171×，p 仍为 0.0000。
**方向层面的结论不受这个 off-by-one 影响。**

### 3.3 Δ=20 的塌陷也复现

| 轴 | 已发表格 (Lr14,Lv14) | 注入点格 (Lr13,Lv13) | 阴性地板 | p_search |
|---|---|---|---|---|
| confidence | 0.0386 | 0.0386 | 0.0686 | 1.0000（不显著） |
| caution | 0.0086 | 0.0082 | 0.0710 | 1.0000（不显著） |

Δ=20 时两条轴都塌到**随机地板以下**，与文档「Δ=20 塌到 0.039 / 0.011 且不再显著」
一致，跨层无差异。

### 3.4 读出方向自己挪一个 block 变多少

`cos(w_L13, w_L14)`，逐折配对（同一折在两层里是同一条留出轨迹）：

| 观测量 | Δ=0 | Δ=20 |
|---|---|---|
| `top1_prob_renorm`（confidence） | 0.8623 | 0.7686 |
| `backtrack_topk`（caution） | 0.8763 | 0.7601 |
| `step_frac`（位置对照） | 0.8147 | 0.8141 |

（`item3_readout_grid.readout_direction_across_layers`）

**值得注意：读出方向比 steering 向量更容易随层漂。** 向量挪一层只掉到
0.955/0.942，读出方向掉到 0.862/0.876。也就是说 off-by-one 对**读出侧**的
影响比对**向量侧**更大 —— 但由于两侧都在同一格里测量，净效果仍然很小（§3.2）。

### 3.5 数据路径保真

- `pca_var_cum(L14) = 0.7287951021859504`，与 `probe_axes.json` 的已发表值
  **完全相同**（`item3_readout_grid.pca_var_cum_matches_published_L14 = true`）
- Gram 矩阵缓存版与 `probe_readout._loo_ridge_fit` 逐折 **max|Δw| = 0.0**、
  Δoof = 0.0（`item3_readout_grid.gram_cache_alignment_vs_reference_impl`）
- 已发表格复现：`cos` 差 **3.5e-05**（confidence）、**3.4e-05**（caution）；
  位置对照 0.01144（发布 0.01144）、0.00163（发布 0.00163）
  （`item6_selfcheck.baseline_reproduction`，4/4 通过，偏离格数 = 0）

---

## 4. 注入点层面的额外影响（标量）

代码证据（`item4_injection_amplitude.code_evidence`）：

- `backend/core/steering.py:218` → `v * (strength * layer_rms(layer))`，
  幅度按**被请求的层号 L=14** 定标
- `register_forward_pre_hook(block 14)` 扰动 block 14 的**输入** = `hidden_states[:,13]`

于是 ‖δ‖ = s · mean‖h_L14‖，却落在范数为 mean‖h_L13‖ 的状态上：

    注入点相对幅度 a = s · mean‖h_L14‖ / mean‖h_L13‖ = s · R

| 量 | 值（layer_profiles.json，即在线实际读取的定标值） | 值（全量 69155 步重算） | JSON 键 |
|---|---|---|---|
| mean‖h‖ L13 | 139.32299807127686 | 139.37692279469584 | `item4..norms_full_69155_steps.13.mean_L2norm` |
| mean‖h‖ L14 | 164.28964755903297 | 164.42098847676215 | `…norms.14.mean_L2norm` |
| **R = M14/M13** | **1.1791997719930152** | 1.1796858847210778 | `…variants.*.R_ratio_L14_over_L13` |
| **s=0.2 在注入点的实际相对幅度** | **0.23583995439860306** | 0.23593717694421557 | `…relative_amplitude_at_injection_point` |
| **「L14 处的 s=0.2 等价于 L13 处的 s=?」** | **0.23583995439860306** | 0.23593717694421557 | `…s_equivalent_at_L13_for_same_delta` |
| ‖δ‖ at s=0.2 | 32.857929511806596 | 32.88419769535243 | `…injected_delta_norm_at_s_nominal` |

**任务书的 0.236 复现成立**（0.23584 / 0.23594，两套定标值都是 0.236）。
等价标称强度 0.2358 —— 即**在线标称 s 比离线扫描的同一绝对扰动弱 15%**。

### 4.1 几何代价，以及上游 +24% 的口径问题

`layer_rms` 是 `mean(‖h‖)` 而不是 `‖mean(h)‖`（后者为 103.94 / 121.55）。
逐 token 的 a 不同，文档 §2 的「实测代价」应是对每个 token 各自算 a 再平均：

    E[½a²] = ½ s² M² E[1/‖h‖²]

| 量 | 值 | JSON 键 |
|---|---|---|
| 纯代入 ½(0.2)² | 0.020000 | `…geometric_cost_half_a2_nominal_s_plain` |
| 逐 token 平均 @L14（= 扰动落对了层） | 0.020651 = **2.07%** | `…geometric_cost_per_token_avg_at_L14` |
| 逐 token 平均 @注入点 L13（= 在线实际） | 0.028743 = **2.87%** | `…geometric_cost_per_token_avg_at_injection_point` |
| 纯代入 ½(0.236)²（文档的 2.78%） | 0.027848 | `item4.½(0.236)²` |
| **同层膨胀比 注入点 / L14** | **1.3918（+39.2%）** | `item4_injection_amplitude.same_layer_inflation.ratio_injection_over_L14` |

**上游写「比标称暗示的 2.03%–2.25% 高约 24%」，那是拿 L20 的 2.236% 与
L13 注入点的 2.78% 跨层比。** 同层比应当是 2.87% / 2.07% = **+39%**，
或纯代入 2.78% / 2.00% = +39%。任务书的「2.78% 而非 2.24%」在**代入值**上
成立（½(0.236)²=2.78%），但 2.24% 不是同层同口径的数。

---

## 5. 阴性 / 阳性对照

### 5.1 阴性对照：400 个随机单位方向的**分布**（不是单点）

seed 20261003，统计量按 折 × 随机方向 展开 19200 个值
（`item5_controls.negative_400_random_directions.cells`）：

| 格 | max | p99 | p95 | 中位 |
|---|---|---|---|---|
| L13 Δ=0 `top1_prob_renorm` | 0.0754 | 0.0676 | 0.0435 | 0.0152 |
| L13 Δ=0 `backtrack_topk` | 0.0799 | 0.0665 | 0.0445 | 0.0160 |
| L14 Δ=0 `top1_prob_renorm` | 0.0752 | 0.0581 | 0.0444 | 0.0159 |
| L14 Δ=0 `backtrack_topk` | 0.0709 | 0.0651 | 0.0454 | 0.0150 |
| L14 Δ=20 `top1_prob_renorm` | 0.0686 | 0.0564 | 0.0412 | 0.0156 |
| L14 Δ=20 `backtrack_topk` | 0.0710 | 0.0575 | 0.0445 | 0.0145 |

**地板远低于实测**：Δ=0 的 0.4166 / 0.3065 是同格地板 max 的 **5.52× / 3.84×**，
是 p95 的 **9.58× / 6.89×**（`item3_readout_grid.derived.conclusion_over_floor`
/ `.conclusion_over_p95_floor`）。Δ=20 的 0.0386 / 0.0086 **低于**地板 max
—— 即 Δ=20 的「塌陷」其实是「掉进噪声里」，与文档的 p=0.229 一致。

### 5.2 阳性对照：`step_frac` 必须测得出

（`item5_controls.positive_control_step_frac.cells`；全部 Δ 含 Δ=20 均在地板之上）

| 读出层 | Δ=0 | Δ=20 |
|---|---|---|
| L13 | 0.6273（oofR +0.7383） | 0.6236（oofR +0.7254） |
| L14 | 0.6279（oofR +0.7387） | 0.6245（oofR +0.7257） |

与已发表的 0.61–0.65 一致。**装置没坏。**

### 5.3 位置对照必须同格

`step_frac` 对 confidence / caution 的同格余弦：L13 Δ=0 为 0.0109 / 0.0018，
L14 Δ=0 为 0.0114 / 0.0016（`item3_readout_grid.grid.*.control_step_frac_cos_pca_norm_same_cell`）。
没有这列，0.4166 / 0.3065 就是无意义的两个数。

---

## 6. 装置自检

### 6.1 数据与层语义

- **无 padding**：`attention_mask` 在 48 个文件里全为 1 且 sum 等于行数
  （`item6_selfcheck.attention_mask_audit.n_files_with_padding = 0`，
  `per_file_mismatch = []`）。总行数 69155 = `obs_series` 的 69155。
  **任务书要求「必须用 attention_mask 过滤」在本次数据上是恒等操作** ——
  过滤逻辑仍然逐文件执行并核验，只是没有 padding 可滤。
- **`hidden_states[:,27] == last_hidden` 逐位相同**：max|diff| = **0.0**，
  141,629,440 / 141,629,440 个元素相同，比例 **1.0**
  （`item6_selfcheck.layer_convention_audit`）。范数 L26 = 3045.75 → L27 = 127.49，
  比值 0.04186。**层语义成立：`hidden_states[:,L]` 是第 L 个 block 的输出。**
- stride 对齐：隐状态与观测量用同一个 stride=2 抽步，长度断言检查
  **等于预期值** `len(series[i]) − delta`（不是两个都错时的等式）。

### 6.2 两个自检闸门

| 自检 | 结果 | JSON 键 |
|---|---|---|
| `probe_readout.toy_selfcheck()`（沿用已通过的实现） | pass | `item6_selfcheck.toy_selfcheck.pass` |
| **层号分辨力自检**（新增） | pass | `item6_selfcheck.layer_resolution_selfcheck` |

**层号分辨力自检**是这次专门加的：扫的维度是层号，所以判据必须在层号上
真的动。造一份**已知**跨层旋转角的合成数据（两层的读出方向夹角
`acos(0.9565)`），要求装置把它测回来：

| 量 | 值 |
|---|---|
| 目标 cos | 0.9565 |
| **装置测得 cos(w_L13, w_L14)** | **0.9571451223377447** |
| 绝对误差 | **0.000645**（容差 0.02） |
| 交叉项 cos(w_L13, a₂) / cos(w_L14, a) | 0.9371 / 0.9366（均落在容差内） |
| 与恒定分量（rogue dimension）的 cos | 0.0892 / 0.0917（未被它骗到） |
| 样本外 Pearson | +0.9995 / +0.9995 |

**装置在 0.9565 这个量级上分辨得动层号**，所以 §3 那些 0.95 量级的层间差
是真的差，不是装置噪声。

---

## 7. 逐值对账

`python3 .cache/layerside2/s5_audit_values.py` → `s5_audit.json` / `s5_audit.log`

```
逐值对账：236/236 通过 (100.0%)  all_pass=True
归因（只看失败行）：0 条
```

审计方式：报告里每个绝对值在审计脚本里作为**字面量**登记一次，
再从 `layerside2.json` 按点分路径重新取值比对 —— 而不是拿 JSON 的值和它自己比
（第一版就是这么写的，等于没审）。容差按报告**印出的位数**自动取末位半个单位：
验的是「报告印出来的那些位对不对」，誊抄错位一定会被抓到，正常四舍五入不会误报。

**审计自身的阴性对照**：把 `layerside2.json` 里
`item3_readout_grid.grid.confidence|delta0|readoutL13.cos_dspace_by_vector_layer.13`
从 0.4166 改成 0.4415、`derived.matched_rel_pct.confidence` 从 1.1 改成 7.1，
重跑审计：

```
逐值对账：234/236 通过 (99.2%)  all_pass=False
  [BAD] §0 摘要  confidence 注入点重测(dspace)  report=0.4166  json=0.4415
  [BAD] §0 摘要  confidence 相对 +1.1%           report=1.1      json=7.1
归因（只看失败行）：2 条
```

即这张表不是恒真的（改完已复原，复跑仍 236/236）。

两个函数判据方向相反且不混用：`verify_all_claims()` 看**全部**行下判决，
`failing_claims()` **只**返回失败行。

---

## 8. 这个 off-by-one 改变了什么、没改变什么

**没改变（方向层面）：**

1. 两条已发表读出结论在注入点重测后只动 **+1.1% / +0.9%**
   （0.4125→0.4166、0.3077→0.3065），仍是对照的 38× / 171×，p 仍 0.0000。
2. 超过阴性地板的倍数（5.5× / 4.3×）、Δ=20 的塌陷形状与不显著性，全部跨层不变。
3. `pca_var_cum`、已发表格的 cos（差 3.5e-05）、已发表向量本身（cos 1−2e-12）全部复现。

**改变了（标量层面）：**

4. 注入点相对幅度 0.2358 而非 0.2（**1.179×**）；等价标称强度 0.2358。
5. 同层几何代价 2.07% → **2.87%（+39%）**，不是上游跨层比出来的 +24%。

**顺带修正的两处上游不自洽：**

6. 任务书的「0.9565」与「0.9546」不能同时成立；正确值 **0.9551 / 0.9421**。
7. 上游 `cos_stored_vs_recomputed/14 = 0.99896` 说明当时的重算没能复现发布向量；
   本次用逐字相同的分组谓词 + 全局池化做到 1−2e-12，样本数也逐个相等。

**「改注入点是否值得重跑」：不值得。**

理由是量级，不是偏好：

- 方向侧的最大变动是**挪一个 block** 时的 0.0339（caution 只换向量层的 −10.0%；
  `item3_readout_grid.derived.one_block_max_abs_change`），而结论的判据间距是
  0.42 vs 0.075（地板）—— **变动比判据间距小一个量级**。在注入点重测的
  变动更小（0.0045 / 0.0026）。
- 强度侧确实有 1.179× 的系统性偏差，**但它可以解析地补偿**：把
  `registry.set_layer_rms` 的定标层从 14 改成 13（或在注入处乘
  M13/M14 = 0.8480）即可，不必重跑任何实验。
- 唯一值得单独做的是**把标称 s 重新对齐**：现有 32k 行为产物是在
  「标称 0.2 = 实际 0.236」下测的，报告强度效应时必须按 0.236 陈述；
  若未来要做 s 的扫描，那是**新的强度点**，不是 off-by-one 的修法。

**一句话：这个 off-by-one 是一个标量定标错误，被一个恰好落在局部高原上的
方向（相邻层 cos 0.94–0.96）掩盖了。方向结论可以继续引用；强度结论必须
改口径陈述。**

---

## 9. 复现产物清单

| 文件 | 内容 |
|---|---|
| `s1_cache_facts.py` → `s1_facts.json` | 层语义核验、attention_mask 审计、范数、`hidden_L{12..15}.npy` 缓存 |
| `s1b_vectors.py` → `s1b_vectors.json`, `vecs_L12_L15.npz` | L12..L15 的 4 条 contrast 方向 + 复现判据 |
| `s2_probe.py` → `s2_probe.json` | 2×4 读出网格、每折全量 cos、400 随机方向分布、两个自检 |
| `s3_injection_amp.py` → `s3_injection_amp.json` | 注入点幅度与几何代价 |
| `s4_consolidate.py` → **`layerside2.json`** | 唯一权威数值源 |
| `s5_audit_values.py` → `s5_audit.json`, `s5_audit.log` | 236 条逐值对账 |

> `s1_facts.json` 里带 `"VOID"` 标记的 `contrast_vectors` /
> `baseline_reproduction` 两段是第一版脚本的错误产物（把 flag 池的**全局**
> 闸门误当逐轨迹闸门），已由 `s1b_vectors.py` 取代，**不得引用**。
> 同段的 `attention_mask_audit` / `layer_convention_audit` / `norms` 仍然有效。
