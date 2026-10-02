# vector_roles.json 独立复算核验报告

核验人：独立复算（未修改任何被跟踪文件；`git status` 中已有的 5 处改动是本次之前就存在的）
环境：`/Users/zhourui/code/steer3d`，`.cache/venv3d/bin/python`（numpy 1.26.4，**无 scipy**——统计量我自己按 scipy 的 average-tie 秩算法重写）
产物：`frontend/public/latent/data/vector_roles.json`（`generated_by: backend/examples/analyse_vector_roles.py`）
临时脚本：`.cache/rolesverify/`

---

## 结论速览

**这份产物的算术是可信的、而且异常干净——我独立重算的每一个数字都在浮点精度内吻合（最大偏差 1.2e-08）；但它能支撑的结论比它的篇幅小得多：三条测量里两条（充分性、特异性）只覆盖 6 个方向中的 2 个，而必要性里所有高相关的数字都是循环论证的。** 唯一真正非循环的证据是 `heldout_non_circular`（我没有复算它），它只覆盖 L14。

---

## 逐项复算

### 复算总表（我实测 vs JSON）

| 项目 | 我的方法 | 我的结果 | JSON | 最大偏差 |
|---|---|---|---|---|
| `n_steps_total` | 数 48 个 npz | 69155 | 69155 | 0 |
| `observable_audit` 6/6 | sidecar json + npz | 全部吻合 | — | **0**（需复刻脚本的 `int()` 截断） |
| `in_sample_circular` 全部 rho/auc/median/n_defined/shuffled | 重算投影+Spearman+AUC | 吻合 | — | **1.2e-08** |
| `random_direction_control` 16 方向 × 12 格 mean/sd/min/max | 复刻 seed 20261002 | 吻合 | — | **5.55e-17** |
| 门判定 12/12 | 复刻双合取门 | 全部一致 | — | **0 处分歧** |
| anchors A1/A2/A3 | 前 6 个文件 | 5820/5790/5799 of 5820 | 同 | 0 |
| `sufficiency.cells` 4 格 × 5 字段 | 从 journal 重算 | 吻合 | — | **0.00e+00** |
| `specificity.locality` 2×2 | 从 journal 重算 | 吻合 | — | **0.00e+00** |
| `specificity.mirror_test` 5 字段 | 23 对配对 | 吻合 | — | **5.55e-17** |
| 4 个向量 = 本批 token 的 diff-of-means | 复刻抽取器（含剔除 prompt 行） | **cos 1.000000** | — | — |

> 说明两处**我自己**的错误（已在报告中更正，勿采信我中途的数）：① anchors 的 A3 循环用累计 `n` 当切片上界（无害，恰好等价）；② 我最初用 `Σpos−Σneg` 归一化而非 `mean(pos)−mean(neg)`，导致只有正负样本数相等的 `reasoning_deep` 吻合。

### 1. `random_direction_control` — 真的跑满了吗？**跑满了。**

| 项 | 值 | 证据 |
|---|---|---|
| 随机方向数 N | **16**（`analyse_vector_roles.py:122`） | 我用 seed 20261002 复刻 16 个 `standard_normal(2048)` 单位向量，mean/sd/min/max 与 JSON 差 **5.55e-17** |
| 实际阈值 | `max(16 个随机方向的最大值, 1/√(n_traj−3))` **且** `\|shuffled_control\| < 1/√(n_traj−3)`（双合取，`:999-1001`） | 12/12 判定我全对 |
| `1/√(n−3)` 算在 n=几 | **n=48（轨迹数）= 0.149071198**；另报 n=69155（步数）= 0.003802749 但**明确不用** | 我复算两个数均吻合 |
| 步数地板是否被弃用 | 是，理由写在 `why_by_traj`（解码步自相关） | 合理 |

**统计效力（这是最该被页面说清的部分）：**

| 观察量 | 有效轨迹数 n | 随机零假设 sd | 实际生效地板 | 问题 |
|---|---|---|---|---|
| entropy | 48 | 0.103 / 0.162 | 0.172 / 0.255 | 可接受 |
| step_frac | 48 | 0.067 / 0.059 | 0.149（naive 绑定） | 可接受 |
| self_check | **27** | 0.140 / 0.212 | 0.741 / 0.749 | 真地板应是 1/√24=**0.204**，JSON 统一用 0.1491 |
| in_think | **3** | 0.0054 | 0.511 | **n=3 时 1/√(n−3) 无定义**；0.1491 对此格不是有效地板 |

- 「打败全部 16 个」= 零假设方向通过概率**恰为 1/16 = 6.25%**。6 次检验至少一次假通过 = **32%**，12 次 = **54%**。第一个合取项很弱，真正起作用的是 shuffled 对照。
- `creativity` 的随机 sd 只有 0.0054（naive 地板的 4%），是 n=3 的产物，其 z=5.5 **没有意义**。
- 生效地板本身是 16 个次序统计量的最大值：L20 self_check 地板 0.7494 而零假设 sd=0.2122，地板自身只钉得住 ±0.07 量级。

### 2. `circularity_warning` — **成立，且我做了决定性验证**

我按抽取器原样（含剔除每条轨迹开头 `n_prompt_tokens`，合计 6356 = 69155−62799，分组计数 20930/379/40338/15679 与 `steering_vectors.json` **逐一相等**）重建 diff-of-means：

| 向量 | 与出厂 `.npy` 的 cosine |
|---|---|
| confidence_up / caution / creativity / reasoning_deep | **全部 1.000000** |

**循环的具体位置**：向量 = `mean(h|组A) − mean(h|组B)`，组 A/B 就定义在这 69155 步里；再把同一步的 `h` 投影回该向量，与**定义这些组的那同一个标签**求相关。对 `caution`/`creativity`，标签本身就是分组谓词（self_check / in_think），AUC 0.98/0.53 是算术恒等式，不是证据。警告正确且应视为**约束**：只有 `heldout_non_circular` 可作必要性证据——**我没有复算它**（需第二遍重拟合+重打分），仍属未独立验证。

### 3. `sufficiency.coverage_gap` — 缺 **4/6 = 67%** 的方向

journal 里 `direction × strength` 只有 4 格、每格 23 次运行、共 92 条；`caution / creativity / reasoning_deep / reasoning_shallow` 干预运行数为 **0**。

- 用 **6**（注册表语义方向）作分母 → **67% 无数据**。
- 用 **22**（6 真实 + 16 随机）作分母 → 18%，但那是**错的分母**，它把 16 个零假设探针当成概念。`n_directions_projected=22` 是投影分母，不是覆盖面分母。
- 后果：三条测量里**两条**（充分性、特异性）只建立在 2/6 方向上，且只有 2 个强度档，其中 `strength=0.0` 是喂零向量的地板（我验证 46 次运行只产生 23 个不同文本摘要，up/down 两臂逐字相同），**不是数据点**。

### 4. `unmeasured` 三项

| 项 | 是什么 | 为什么没测 | 致命吗 |
|---|---|---|---|
| `per_step_entropy_of_steered_runs` | 干预后**逐步**熵序列（整体 vs 局部效应） | 我验证：92 条 per_run 中**列表型字段为 0 个**，只有 `mean_*` 汇总 | **不致命**。结论被压到「输出分布整体变了」，不能说「每步都变」。locality/mirror 是真替代且都已复算 |
| `directions_without_intervention_runs` | 4 个方向一次干预都没有 | 采集覆盖面缺口 | **对这 4 个方向致命**。不能推广到「向量」整体，只能说 confidence_up/down |
| `lm_head_anchor` | `argmax(lm_head·h[27])` 是否复现真实选择 | 声称本机无权重 | **不致命——我已经补上**（见下）；但**声称的理由是错的** |

### 5. `lm_head_anchor` — 声明成立，我已独立验证

用 `datasets/models/Qwen3-1.7B` 的 `lm_head.weight`（bf16→fp32），`hidden_states[t,27,:]` 为 post-norm **未再归一化**：

| 指标 | 我的实测 | JSON 引用 |
|---|---|---|
| argmax == `topk_indices[t,0]` | **398/400 = 0.9950**（8 轨迹 × 50 步，einsum 路径） | NOT_RECOMPUTED |
| 限 top1−top2 margin ≥ 1.0 | **281/281 = 1.0000** | 引用 1420/1420 = 1.0 |
| max logit 误差 | **0.1250** | 引用 0.125 ✅ 精确吻合 |
| top-64 集合 Jaccard / 已降序 | 0.9944 / 100% | — |

**声明里的理由不成立**：`datasets/models/Qwen3-1.7B/` 存在，mtime **2026-09-24**，比 JSON（2026-10-02 22:33）**早 8 天**。复算**不需要 GPU、不需要 transformers**：纯 numpy，`einsum("td,vd->tv")` 400 步 **24 秒**。「GPU 被占用所以不能做」与「没有权重」两条都站不住。

### 6. `observable_audit` 六个量

| 量 | 量纲 | 能否从 npz 复算 | 复算结果 |
|---|---|---|---|
| `entropy` | nats，0–ln(64) | **近似**：top-64 重归一化熵 vs 存储值 r=0.999953、mean abs diff 3.5e-4（top-64 是下界）；精确值在 sidecar json | ✅ 精确 |
| `top1_prob` | [0,1] | **是**：softmax(topk_logits)[0]，99.86% 落在 2e-3 内 | ✅ 精确 |
| `self_check` | 0/1 | **是**：token 文本正则 | ✅ 精确 |
| `in_think` | 0/1 | **是**：sidecar `is_in_think_block` | ✅ 精确 |
| `top1_switch` | 0/1 | **是**：`topk_indices` 逐行变化 | ✅ 精确 |
| `step_frac` | [0,1] 线性 | **是**：`arange(T)/(T−1)` | ✅ 精确 |

`in_think ≡ 运行模式` 我独立确认：48/48 条轨迹第 0 步即由模式决定，45/48 条轨迹内部恒定。

---

## 发现的不一致

1. **`lm_head_anchor.reason` 事实错误**（最严重）。权重在仓库内、已存在 8 天、CPU 24 秒可算。状态应改为 `RECOMPUTED`，附 398/400 与 margin≥1 下的 281/281。
2. **`frac_steps_positive` 被 `int()` 截断**。脚本用 `int(sum(float32 .sum()))`，对非整数和向下截断：`entropy` 0.228361792→0.228356590，`step_frac` **精确值恒为 0.5** 却报 0.499993。页面若显示「49.999%」是在展示一个截断残差。
3. **anchors 覆盖面未声明**：只查 6/48 轨迹、5820/69155 步 = **8.4%**，而 `observable_audit`/`necessity` 用全部 48 条。`anchors.note` 只说「分母 = 被检查的步数」，没说这是全量的 8.4%。
4. **地板与有效 n 不匹配**：`1/√(n_traj−3)=0.1491` 被统一套用，但 caution 有效 n=27、creativity 有效 n=**3**（此时公式无定义）。`per_traj_denominator_note` 说了剔除机制，但没说地板也失配。
5. **「打败 16 个」= 每检验 6.25% 假通过率，JSON 从未声明**。`random_control_is_the_real_null` 把 mean+3sd 称作「natural threshold」，但代码用的是 max-of-16（mean+3sd 在 L20 self_check 上算出 1.128，不可达，已弃用）。
6. **循环块里带 `passes_gate: true`**。`in_sample_circular` 的每个条目都有 `passes_gate`，UI 若把「PASS」渲染出来，等于把循环论证的判定当证据展示。`circularity_warning` 是**独立字符串**，不与这些数字在结构上绑定。

---

## 页面展示时的红线

| 档位 | 具体内容 |
|---|---|
| ✅ **可直接展示** | 全部 4 个充分性格、locality、mirror_test（均带 n=23、d=0.00e+00 可复算）；16 个随机方向的 null 分布；anchors 三个率（但须标 6/48）；`observable_audit` 六个值（须改掉 `int()` 截断）；coverage_gap 本身 |
| ⚠️ **必须同时展示分母/缺口** | 任何 rho/AUC：**紧挨着** `n_traj_within_which_rho_is_defined`（27 或 3 时尤其）；随机控制必须带 `n_random_directions=16` 和地板来源；`in_think`/`self_check` 任何数字必须带「基率 0.006 / 0.629」与「in_think ≡ 运行模式」警告；充分性/特异性每处必须写「仅 2/6 方向、2 档强度、其中一档是零向量地板」；`n_steps=69155` 必须配 `n_traj=48` |
| ⛔ **绝对不能单独展示** | ① `in_sample_circular` 的任何 `passes_gate`/相关数字——**不得脱离 `heldout_non_circular` 出现**；② `creativity` 的任何数字（in_think ≡ 模式，n=3，地板无定义）；③ `caution` 的 in-sample AUC 0.98（标签即分组谓词，恒等式）；④ 任何未带分母的「48/48 轨迹支持」式表述；⑤ `step_frac` 的 0.499993；⑥ 页面若展示 4/6 无干预运行，**不得**同时展示「充分性/特异性」小标题而不带缺口说明 |

---

## 置信度边界

| 结论 | 置信度 | 依据 |
|---|---|---|
| 全部可复算数字的算术正确 | **极高** | 独立重算，最大偏差 1.2e-08；`observable_audit` 与充分性/特异性逐位吻合 |
| 随机对照是真零假设且跑满 16 个 | **极高** | 16 个方向全部复现到 5.55e-17 |
| 循环警告成立 | **极高** | 4 个向量 cosine 1.000000 重建，分组计数逐一相等 |
| `lm_head_anchor` 成立 | **高** | 398/400、margin≥1 下 281/281、logit 误差 0.1250 精确吻合引用值 |
| `heldout_non_circular` 正确 | **未验证** | 我**没有**复算（需第二遍重拟合+重打分）。这是唯一非循环的必要性证据，仍是引用 |
| 充分性/特异性可推广到「向量」 | **不可** | 4/6 方向零数据；强度只有 0.2 一档是真数据 |
| 逐步/局部效应结论 | **不可** | 92 条运行无任何逐步序列字段 |
| 关于「通用理论」的回答 | **本产物答不了** | 它只测了 2 个方向、1 个模型、1 个数据集、1 个注入层；necessity 的非循环部分只到 L14 |

**净判断**：这份产物作为「2 个 confidence 方向 + 1 个模型上的测量记录」是可信且诚实的，作为「向量起什么作用 / 能否抽出通用理论」的证据是不够的——不是因为算错了，而是因为覆盖面（2/6 方向）和非循环证据（L14、24 轨迹/折）都还没到。
