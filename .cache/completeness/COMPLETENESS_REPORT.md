# 完备性检验：4 条命名轴是不是残差流里可解释行为的完备描述？

脚本 `.cache/completeness/completeness.py` → `completeness.json`；本文每个数字都从该 JSON 读出，键名标在括号里。

装置：L14 / K=256 PCA / stride=2 / 48 条轨迹 / 34583 步 / 留一轨迹岭回归（λ∈[0.001, 0.01]）/ 轨迹内去均值 / 主判据=留一样本外 Pearson。

## 0. 先验装置：7/7 复现（`apparatus_repro`）

| 报告行 | 目标 | Δ | 声称 cos | 实测 cos | 差 | 容差内 | 角色 |
|---|---|---|---|---|---|---|---|
| confidence | `top1_prob_renorm` | 0 | 0.412 | 0.4125 | 0.0005 | 是 | 已测读出方向 |
| caution | `backtrack_topk` | 0 | 0.308 | 0.3077 | 0.0003 | 是 | 已测读出方向 |
| creativity | `backtrack_topk` | 0 | 0.039 | 0.0395 | 0.0005 | 是 | 对照组（< 位置对照 0.057 ⇒ 测不出） |
| reasoning_deep | `rep_ngram4` | 0 | 0.339 | 0.3387 | 0.0003 | 是 | 对照组（< 位置对照 0.628 ⇒ 测不出） |
| reasoning_deep（尺子） | `step_frac` | 0 | 0.628 | 0.6279 | 0.0001 | 是 | 装置阳性对照 |
| reasoning_deep（尺子） | `step_frac` | 20 | 0.625 | 0.6245 | 0.0005 | 是 | 装置阳性对照 |
| reasoning_deep（尺子） | `step_frac` | 400 | 0.614 | 0.6137 | 0.0003 | 是 | 装置阳性对照 |

`step_frac` 三个 Δ 全部复现 ⇒ 装置能在样本外以 cos≈0.62 测出「轨迹位置」。step_frac 行是**装置阳性对照**：step_frac = t/(T−1) 正是 reasoning_deep 的 positive_group（原文 last 25% of long trajectories）。

**复现时新发现的一条串扰**（`cross_talk_flag`，只对有正向主张的两条轴报）：
- `backtrack_topk` 那一格：**confidence 轴 = 0.3341 > 报告行所属的 `caution` 轴 = 0.3077**。

⇒ 「`caution` 测到回退标记」那一格的读出方向，在**同一格**上与 `confidence` 轴的对齐更强。这不推翻 0.308 的复现，但意味着 `backtrack_topk` 那一格**不能算 `caution` 的专属读出** —— 它对 `confidence` 轴的可读性更高。

## 1. ICC：哪些列有资格当候选（`icc_table`）

门槛：合格 = 轨迹内零方差 <20% 且 ICC1<0.5。已知靶子：entropy≈0.045 / self_check_regex≈0.006 / in_think≈0.955

| 观测量 | ICC(1) | 轨迹间方差份额 | 轨迹内零方差 | 合格 |
|---|---|---|---|---|
| `rep_top1` | 0.0221 | 0.0229 | 0/48 | ✅ |
| `rep_ngram4` | 0.0585 | 0.0584 | 0/48 | ✅ |
| `rep_frac_topk` | 0.1068 | 0.1056 | 0/48 | ✅ |
| `backtrack_topk` | 0.0656 | 0.0654 | 0/48 | ✅ |
| `backtrack_frac` | 0.0169 | 0.0178 | 0/48 | ✅ |
| `digit_mass` | 0.0770 | 0.0764 | 0/48 | ✅ |
| `op_mass` | 0.0865 | 0.0858 | 0/48 | ✅ |
| `newline_mass` | 0.0291 | 0.0297 | 0/48 | ✅ |
| `latex_mass` | 0.1760 | 0.1735 | 0/48 | ✅ |
| `top1_prob_renorm` | 0.0374 | 0.0378 | 0/48 | ✅ |
| `entropy`（定义式目标） | 0.0444 | 0.0447 | 0/48 | ✅ |
| `in_think`（定义式目标） | 0.9562 | 0.9552 | 45/48 | ❌ |
| `self_check_regex`（定义式目标） | 0.0051 | 0.0063 | 23/48 | ❌ |
| `step_frac`（定义式目标） | -0.0014 | 0.0000 | 0/48 | ✅ |

### 冗余审计：必须区分 Spearman 与 Pearson（`redundancy_audit`）

`obs_series_meta.json` 的 `redundancy_matrix` 键名叫 `abs_rho_pooled`，但它自己的 `definition_pooled` 字段写明存的是 **|Spearman|**。本任务的统计量是**线性探针的 Pearson**，两列必须分开看。

| 观测量对 | Pearson | Spearman | 之前报告引用的数 | 处理 |
|---|---|---|---|---|
| `backtrack_topk__backtrack_frac` | **0.2686** | 0.9660 | 0.965（Spearman） | 秩相关高但线性相关低 ⇒ 对**线性**探针不是重复，不能据此从搜索里剔除 |
| `top1_prob_renorm__entropy` | **0.9601** | 0.9915 | 0.985（Spearman） | 线性探针口径下视为重复，不作独立证据 |

- Pearson > 0.8 的对：1 对 ⇒ `top1_prob_renorm`|`entropy` (P=0.9601,S=0.9915)
- Spearman > 0.8 但 Pearson ≤ 0.8 的对：1 对 ⇒ `backtrack_topk`|`backtrack_frac` (P=0.2686,S=0.9660)

**因此本轮搜索保留全部 10 个可用观测量**（`effective_dof.deviation_from_probe_axes`）：

> probe_axes.py 以 |ρ|(backtrack_topk,backtrack_frac)=0.965 为由把 backtrack_frac 剔出搜索、把有效自由度记成 9。实测该 0.965 是 Spearman；Pearson 只有 0.27。对线性探针而言二者不是重复，故本轮 10 个全留，有效自由度按 10 记。

有效自由度（`effective_dof`）：**全部保留**，计入搜索的观测量 **10** 个；另有 4 个定义式/尺子目标（`entropy`, `in_think`, `self_check_regex`, `step_frac`）不进搜索。`top1_prob_renorm` 与 entropy 仍合并算一份证据（与 entropy 的 Pearson |ρ| 也 >0.8，两者合计算一份证据（这一条在两种口径下都成立））⇒ 实质自由度 9。

## 2. 同格对照尺子：每条轴的定义式那一格是阳性对照，不是发现

规则（`axis_readout_summary.rule`）：每个高余弦格子都要问「这条轴自己的定义式在这个格子上是多少」。定义式目标那一行是**阳性对照**，不是发现。

| 轴 | 定义式分组 | 定义式目标 | 定义式格 cos（Δ=0） | 最佳**非**定义式格 | 其 cos | 两格 \|ρ\| | 定义式 − 最佳非定义式 |
|---|---|---|---|---|---|---|---|
| `confidence` | low-entropy tokens (p30) vs high-entropy tokens (p75) | `entropy` | 0.4075 | `top1_prob_renorm` Δ=0 | 0.4125 | 0.9601 | -0.0050 |
| `caution` | self-check tokens (wait/actually/…) vs ordinary generated tokens | `self_check_regex` | 0.5325 | `backtrack_frac` Δ=0 | 0.4840 | 0.3969 | 0.0485 |
| `creativity` | tokens inside <think> vs tokens outside <think> | `in_think` | 0.1440 | `latex_mass` Δ=100 | 0.0767 | 0.3392 | 0.0672 |
| `reasoning_deep` | last 25% of long trajectories vs first 25% of long trajectories | `step_frac` | 0.6279 | `rep_frac_topk` Δ=20 | 0.5206 | 0.4087 | 0.1073 |

读法（**不要把这一列当成通过/不通过的开关**）：

- `caution` / `creativity` / `reasoning_deep` 三行的「定义式 − 最佳非定义式」为正，且两格之间 |ρ| 很低 ⇒ 定义式那一格确实是更高的天花板，那些漂亮数字可以被同源构造追平。
- `confidence` 那一行为**负**，但这**不是**「定义式追不上」：它的定义式目标是 `entropy`，而最佳非定义式格是 `top1_prob_renorm`，两者 Pearson |ρ| = 0.96 —— **它们本来就是同一个观测量**，两列的数字在数值上不可区分。换句话说这一行没有提供任何独立于定义式的证据。

**四格全部标为装置阳性对照（`is_positive_control_cell = true`），不计入任何完备性结论。**

## 3. 循环性用语义无关的假观测量证伪（`fake_observable_controls`）

**step_frac 尺子**：1−step_frac（语义相反的 t 斜坡）以等幅反号复现 step_frac 的全部信号 ⇒ 测到的是「随 t 单调漂移」，不含任何哪一端更晚的信息。该行只能当装置尺子，不能当发现。

| 观测量 | 协议 | OOF Pearson | cos(reasoning_deep) | \|rho\| 相对真值 | 符号相反 |
|---|---|---|---|---|---|
| `step_frac (fit & score)` | fit_real_score_real | 0.738695 | 0.6279 | — | — |
| `fake_rev_ramp` | fit_real_score_fake | -0.738695 | — | 1.000000 | 是 |
| `fake_sqrt_ramp` | fit_real_score_fake | 0.782927 | — | 1.059878 | 否 |
| `fake_rev_ramp` | fit_fake | 0.738695 | 0.6279 | 1.000000 | — |

复现比例 `|rho(1−step_frac)| / |rho(step_frac)|` = **1.0000000000000000**，且**符号相反**。

（FAILED_OBS_FORENSICS §4 记的是 1.0000000000000004；本轮在 float64 下得到精确的 1.0，两者是同一个「完全复现」，差别只是浮点噪声的末位。）⇒ 装置复现通过，且该行是构造循环。

**confidence 那一格的地板**：confidence 的定义式就是 entropy 的 30/75 分位差（steering_vectors.json），⇒ Δ=0 上 confidence×熵那一格是**构造恒等式**，只能当装置阳性对照。语义无关的假观测量给出的 cos 地板见 floor_cos_confidence_of_semantically_irrelevant_fakes，0.412 比该地板高出一个量级 ⇒ 不是装置噪声，但仍是构造循环。

| 观测量 | 语义 | cos(confidence) | 相对真值比例 |
|---|---|---|---|
| `(真) top1_prob_renorm` | 真实观测量 | 0.4125 | — |
| `fake_shuffle_within_traj` | 轨迹内随机打乱真实 entropy（破坏时间-语义对应，保留边缘分布） | 0.0204 | 0.0496 |
| `fake_anti_entropy_perm` | 轨迹内打乱 −entropy：检验 0.412 是否只是 \|rho\| 的方向无关性 | 0.0116 | 0.0281 |
| `fake_traj_const_rand` | 按轨迹随机的常数（只有轨迹级结构，无逐步信息） | 0.0032 | 0.0077 |
| `fake_white` | 纯 i.i.d. 高斯噪声（零假设地板） | 0.0035 | 0.0084 |

语义无关的假观测量给出的地板 = **0.0204**，0.412 是它的 20.2 倍 ⇒ 不是装置噪声；但它同时是构造恒等式，仍只作阳性对照。

定义式目标的实测口径（`definition_target_diagnostics`）：self_check 正例 193 步、23/48 条轨迹零正例（391 个正例 / 21 条轨迹零正例）；in_think 轨迹内零方差 45/48。

self_check 正则取自 backend/examples/compute_steering_vectors.py 的 11 词项版本（定义 caution 轴的那一份）。

## 4. 投影检验：4 条轴漏掉多少（`readout` / `headline.completeness_per_target`）

4 条命名张成的子空间 S：条件数 `cond(S) = 2.1595`（奇异值 1.387, 1.022, 0.787, 0.642），Gram-Schmidt 后条件数 1.201，正交化误差 4.44e-16 ⇒ **4 条线性无关**。

两两 |cos|（`pairwise_abs_cos`）：
- `confidence|caution` = 0.5537
- `confidence|creativity` = 0.4155
- `confidence|reasoning_deep` = 0.1651
- `caution|creativity` = 0.3429
- `caution|reasoning_deep` = 0.0315
- `creativity|reasoning_deep` = 0.2185

### Δ = 0

| 观测量 | \|r\|/\|d*\|（方向里 4 条轴没覆盖的比例） | OOF Pearson(d*) | OOF Pearson(r) | 1−ρ²(r)/ρ²(d*) = S 解释份额 | r 超零分布 p99 |
|---|---|---|---|---|---|
| `rep_top1` | 0.9534 | 0.5106 | 0.3660 | 0.4862 | 是（p99=0.1755） |
| `rep_ngram4` | 0.9243 | 0.6149 | 0.3889 | 0.6000 | 是（p99=0.2167） |
| `rep_frac_topk` | 0.9146 | 0.7120 | 0.5442 | 0.4158 | 是（p99=0.1949） |
| `backtrack_topk` | 0.9208 | 0.6760 | 0.2661 | 0.8450 | 是（p99=0.2583） |
| `backtrack_frac` | 0.8570 | 0.6223 | 0.0494 | 0.9937 | 否（p99=0.1683） |
| `digit_mass` | 0.9570 | 0.8588 | 0.7667 | 0.2031 | 是（p99=0.3074） |
| `op_mass` | 0.9993 | 0.5701 | 0.5654 | 0.0162 | 是（p99=0.1894） |
| `newline_mass` | 0.9967 | 0.6128 | 0.6046 | 0.0265 | 是（p99=0.1584） |
| `latex_mass` | 0.9980 | 0.4379 | 0.4291 | 0.0398 | 是（p99=0.1150） |
| `top1_prob_renorm` | 0.8935 | 0.5203 | 0.1592 | 0.9064 | 否（p99=0.2183） |
| `entropy` ⚠️定义式目标 | 0.8960 | 0.5933 | 0.2100 | 0.8746 | 否（p99=0.2469） |
| `in_think` ⚠️定义式目标 | 0.9856 | 0.2742 | 0.1999 | 0.4685 | 是（p99=0.0700） |
| `self_check_regex` ⚠️定义式目标 | 0.7967 | 0.3525 | -0.0117 | 0.9989 | 否（p99=0.0715） |
| `step_frac` ⚠️定义式目标 | 0.7735 | 0.7387 | -0.0380 | 0.9974 | 否（p99=0.2269） |

零分布分母：**240 个随机单位方向**（`direction_search.delta0.n_random_directions_in_null`），搜索分母：**400 个方向**（240 随机 + 80 PCA 主方向 + 80 轴扰动）。

### Δ = 1

| 观测量 | \|r\|/\|d*\|（方向里 4 条轴没覆盖的比例） | OOF Pearson(d*) | OOF Pearson(r) | 1−ρ²(r)/ρ²(d*) = S 解释份额 | r 超零分布 p99 |
|---|---|---|---|---|---|
| `rep_top1` | 0.9451 | 0.4293 | 0.3191 | 0.4473 | 是（p99=0.1410） |
| `rep_ngram4` | 0.9155 | 0.5308 | 0.3305 | 0.6125 | 是（p99=0.1926） |
| `rep_frac_topk` | 0.9026 | 0.5043 | 0.2940 | 0.6601 | 是（p99=0.1476） |
| `backtrack_topk` | 0.9785 | 0.4291 | 0.3200 | 0.4441 | 是（p99=0.1431） |
| `backtrack_frac` | 0.9862 | 0.2419 | 0.2077 | 0.2624 | 是（p99=0.0643） |
| `digit_mass` | 0.9891 | 0.3927 | 0.3332 | 0.2800 | 是（p99=0.1512） |
| `op_mass` | 0.9892 | 0.2077 | 0.1591 | 0.4135 | 是（p99=0.0874） |
| `newline_mass` | 0.9977 | 0.2412 | 0.2400 | 0.0097 | 是（p99=0.0706） |
| `latex_mass` | 0.9948 | 0.1997 | 0.1747 | 0.2350 | 是（p99=0.0751） |
| `top1_prob_renorm` | 0.9593 | 0.3427 | 0.1613 | 0.7784 | 是（p99=0.1257） |
| `entropy` ⚠️定义式目标 | 0.9581 | 0.3948 | 0.1909 | 0.7661 | 是（p99=0.1416） |
| `in_think` ⚠️定义式目标 | 0.9855 | 0.2740 | 0.1995 | 0.4702 | 是（p99=0.0737） |
| `self_check_regex` ⚠️定义式目标 | 0.9986 | 0.1101 | 0.1064 | 0.0653 | 是（p99=0.0452） |
| `step_frac` ⚠️定义式目标 | 0.7739 | 0.7379 | -0.0378 | 0.9974 | 否（p99=0.2273） |

零分布分母：**240 个随机单位方向**（`direction_search.delta1.n_random_directions_in_null`），搜索分母：**400 个方向**（240 随机 + 80 PCA 主方向 + 80 轴扰动）。

### Δ = 20

| 观测量 | \|r\|/\|d*\|（方向里 4 条轴没覆盖的比例） | OOF Pearson(d*) | OOF Pearson(r) | 1−ρ²(r)/ρ²(d*) = S 解释份额 | r 超零分布 p99 |
|---|---|---|---|---|---|
| `rep_top1` | 0.9274 | 0.2477 | 0.1563 | 0.6018 | 是（p99=0.0807） |
| `rep_ngram4` | 0.8660 | 0.2548 | 0.0752 | 0.9129 | 否（p99=0.0869） |
| `rep_frac_topk` | 0.8436 | 0.3724 | 0.1215 | 0.8936 | 是（p99=0.1162） |
| `backtrack_topk` | 0.9812 | 0.0525 | 0.0331 | 0.6033 | 否（p99=0.0497） |
| `backtrack_frac` | 0.9864 | 0.0365 | 0.0255 | 0.5105 | 否（p99=0.0373） |
| `digit_mass` | 0.9884 | 0.0725 | 0.0512 | 0.5008 | 是（p99=0.0452） |
| `op_mass` | 0.9982 | 0.0305 | 0.0264 | 0.2507 | 否（p99=0.0438） |
| `newline_mass` | 0.9997 | 0.0146 | 0.0148 | -0.0394 | 否（p99=0.0462） |
| `latex_mass` | 0.9889 | 0.0340 | 0.0217 | 0.5944 | 否（p99=0.0564） |
| `top1_prob_renorm` | 0.9942 | 0.0816 | 0.0782 | 0.0795 | 是（p99=0.0536） |
| `entropy` ⚠️定义式目标 | 0.9926 | 0.0917 | 0.0878 | 0.0840 | 是（p99=0.0525） |
| `in_think` ⚠️定义式目标 | 0.9824 | 0.2686 | 0.1875 | 0.5126 | 是（p99=0.0702） |
| `self_check_regex` ⚠️定义式目标 | 0.9968 | 0.0037 | 0.0015 | 0.8283 | 否（p99=0.0358） |
| `step_frac` ⚠️定义式目标 | 0.7766 | 0.7257 | -0.0287 | 0.9984 | 否（p99=0.2248） |

零分布分母：**240 个随机单位方向**（`direction_search.delta20.n_random_directions_in_null`），搜索分母：**400 个方向**（240 随机 + 80 PCA 主方向 + 80 轴扰动）。

### Δ = 100

| 观测量 | \|r\|/\|d*\|（方向里 4 条轴没覆盖的比例） | OOF Pearson(d*) | OOF Pearson(r) | 1−ρ²(r)/ρ²(d*) = S 解释份额 | r 超零分布 p99 |
|---|---|---|---|---|---|
| `rep_top1` | 0.9487 | 0.0890 | 0.0307 | 0.8811 | 否（p99=0.0416） |
| `rep_ngram4` | 0.9109 | 0.1582 | 0.0425 | 0.9279 | 否（p99=0.0657） |
| `rep_frac_topk` | 0.8733 | 0.2277 | 0.0499 | 0.9519 | 否（p99=0.0680） |
| `backtrack_topk` | 0.9964 | 0.0161 | 0.0142 | 0.2230 | 否（p99=0.0530） |
| `backtrack_frac` | 0.9929 | 0.0033 | 0.0013 | 0.8544 | 否（p99=0.0415） |
| `digit_mass` | 0.9909 | 0.0287 | 0.0122 | 0.8192 | 否（p99=0.0466） |
| `op_mass` | 0.9986 | 0.0135 | 0.0143 | -0.1191 | 否（p99=0.0461） |
| `newline_mass` | 0.9973 | 0.0112 | 0.0105 | 0.1242 | 否（p99=0.0508） |
| `latex_mass` | 0.9883 | 0.0164 | 0.0088 | 0.7146 | 否（p99=0.0590） |
| `top1_prob_renorm` | 0.9985 | 0.0092 | 0.0074 | 0.3498 | 否（p99=0.0483） |
| `entropy` ⚠️定义式目标 | 0.9991 | 0.0136 | 0.0133 | 0.0434 | 否（p99=0.0494） |
| `in_think` ⚠️定义式目标 | 0.9708 | 0.1072 | 0.0495 | 0.7867 | 否（p99=0.1281） |
| `self_check_regex` ⚠️定义式目标 | 0.9983 | 0.0082 | 0.0089 | -0.1904 | 否（p99=0.0324） |
| `step_frac` ⚠️定义式目标 | 0.7823 | 0.7090 | -0.0132 | 0.9997 | 否（p99=0.2277） |

零分布分母：**240 个随机单位方向**（`direction_search.delta100.n_random_directions_in_null`），搜索分母：**400 个方向**（240 随机 + 80 PCA 主方向 + 80 轴扰动）。

### Δ = 400

| 观测量 | \|r\|/\|d*\|（方向里 4 条轴没覆盖的比例） | OOF Pearson(d*) | OOF Pearson(r) | 1−ρ²(r)/ρ²(d*) = S 解释份额 | r 超零分布 p99 |
|---|---|---|---|---|---|
| `rep_top1` | 0.9960 | -0.0091 | -0.0133 | -1.1127 | 否（p99=0.0505） |
| `rep_ngram4` | 0.9977 | 0.0186 | 0.0197 | -0.1169 | 否（p99=0.0574） |
| `rep_frac_topk` | 0.9855 | 0.0227 | 0.0032 | 0.9803 | 否（p99=0.0536） |
| `backtrack_topk` | 0.9994 | -0.0061 | -0.0030 | 0.7536 | 否（p99=0.0449） |
| `backtrack_frac` | 0.9997 | -0.0145 | -0.0130 | 0.1935 | 否（p99=0.0403） |
| `digit_mass` | 0.9985 | -0.0307 | -0.0275 | 0.1978 | 否（p99=0.0537） |
| `op_mass` | 0.9984 | -0.0022 | -0.0005 | 0.9528 | 否（p99=0.0494） |
| `newline_mass` | 0.9985 | 0.0077 | 0.0058 | 0.4365 | 否（p99=0.0452） |
| `latex_mass` | 0.9961 | 0.0107 | 0.0102 | 0.0845 | 否（p99=0.0554） |
| `top1_prob_renorm` | 0.9959 | -0.0172 | -0.0122 | 0.4910 | 否（p99=0.0545） |
| `entropy` ⚠️定义式目标 | 0.9966 | -0.0240 | -0.0190 | 0.3728 | 否（p99=0.0504） |
| `in_think` ⚠️定义式目标 | 0.9586 | 0.0782 | 0.0244 | 0.9024 | 否（p99=0.1034） |
| `self_check_regex` ⚠️定义式目标 | 0.9992 | 0.0007 | 0.0015 | -3.7143 | 否（p99=0.0385） |
| `step_frac` ⚠️定义式目标 | 0.7760 | 0.7829 | 0.1231 | 0.9753 | 否（p99=0.2521） |

零分布分母：**240 个随机单位方向**（`direction_search.delta400.n_random_directions_in_null`），搜索分母：**400 个方向**（240 随机 + 80 PCA 主方向 + 80 轴扰动）。

## 5. 方向搜索与搜索修正（`direction_search`）

### Δ = 0（48 条轨迹 / 34583 步 / 400 个方向）

| 观测量 | max OOF Pearson | 来自哪类方向 | 零分布 p95 | p99 | 搜索修正后 p | 轴外方向上的 max | 轴外 p |
|---|---|---|---|---|---|---|---|
| `rep_top1` | 0.2756 | axis_perturbed | 0.1383 | 0.1755 | 0.0000 | 0.2225 | 0.0042 |
| `rep_ngram4` | 0.3307 | axis_perturbed | 0.1805 | 0.2167 | 0.0000 | 0.2693 | 0.0000 |
| `rep_frac_topk` | 0.2974 | axis_perturbed | 0.1720 | 0.1949 | 0.0000 | 0.2951 | 0.0000 |
| `backtrack_topk` | 0.4976 | axis_perturbed | 0.2132 | 0.2583 | 0.0000 | 0.3497 | 0.0000 |
| `backtrack_frac` | 0.3816 | axis_perturbed | 0.1343 | 0.1683 | 0.0000 | 0.1941 | 0.0042 |
| `digit_mass` | 0.4164 | pca_top | 0.2395 | 0.3074 | 0.0000 | 0.4164 | 0.0000 |
| `op_mass` | 0.2648 | random | 0.1693 | 0.1894 | 0.0042 | 0.2648 | 0.0042 |
| `newline_mass` | 0.2049 | pca_top | 0.1249 | 0.1584 | 0.0000 | 0.2049 | 0.0000 |
| `latex_mass` | 0.1279 | random | 0.0886 | 0.1150 | 0.0042 | 0.1279 | 0.0042 |
| `top1_prob_renorm` | 0.3855 | axis_perturbed | 0.1658 | 0.2183 | 0.0000 | 0.2873 | 0.0000 |
| `entropy` ⚠️ | 0.4348 | axis_perturbed | 0.1873 | 0.2469 | 0.0000 | 0.3265 | 0.0000 |
| `in_think` ⚠️ | -0.0952 | random | 0.0480 | 0.0700 | 0.0042 | -0.0952 | 0.0042 |
| `self_check_regex` ⚠️ | 0.1927 | axis_perturbed | 0.0624 | 0.0715 | 0.0000 | 0.0883 | 0.0042 |
| `step_frac` ⚠️ | 0.6072 | axis_perturbed | 0.1751 | 0.2269 | 0.0000 | 0.2997 | 0.0000 |

### Δ = 1（48 条轨迹 / 34535 步 / 400 个方向）

| 观测量 | max OOF Pearson | 来自哪类方向 | 零分布 p95 | p99 | 搜索修正后 p | 轴外方向上的 max | 轴外 p |
|---|---|---|---|---|---|---|---|
| `rep_top1` | 0.2447 | axis_perturbed | 0.1198 | 0.1410 | 0.0000 | 0.1886 | 0.0042 |
| `rep_ngram4` | 0.2940 | axis_perturbed | 0.1669 | 0.1926 | 0.0000 | 0.2478 | 0.0000 |
| `rep_frac_topk` | 0.3076 | axis_perturbed | 0.1151 | 0.1476 | 0.0000 | 0.1629 | 0.0000 |
| `backtrack_topk` | 0.2252 | axis_perturbed | 0.1088 | 0.1431 | 0.0000 | 0.2159 | 0.0000 |
| `backtrack_frac` | 0.0830 | pca_top | 0.0533 | 0.0643 | 0.0000 | 0.0830 | 0.0000 |
| `digit_mass` | 0.2205 | pca_top | 0.1200 | 0.1512 | 0.0000 | 0.2205 | 0.0000 |
| `op_mass` | 0.1469 | axis_perturbed | 0.0739 | 0.0874 | 0.0000 | 0.1337 | 0.0000 |
| `newline_mass` | 0.0763 | random | 0.0490 | 0.0706 | 0.0042 | 0.0763 | 0.0042 |
| `latex_mass` | -0.0782 | random | 0.0583 | 0.0751 | 0.0042 | -0.0782 | 0.0042 |
| `top1_prob_renorm` | 0.2247 | axis_perturbed | 0.1071 | 0.1257 | 0.0000 | 0.1871 | 0.0000 |
| `entropy` ⚠️ | 0.2578 | axis_perturbed | 0.1232 | 0.1416 | 0.0000 | 0.2126 | 0.0000 |
| `in_think` ⚠️ | -0.0872 | random | 0.0524 | 0.0737 | 0.0042 | -0.0872 | 0.0042 |
| `self_check_regex` ⚠️ | -0.0469 | random | 0.0337 | 0.0452 | 0.0042 | -0.0469 | 0.0042 |
| `step_frac` ⚠️ | 0.6064 | axis_perturbed | 0.1750 | 0.2273 | 0.0000 | 0.2990 | 0.0000 |

### Δ = 20（48 条轨迹 / 33623 步 / 400 个方向）

| 观测量 | max OOF Pearson | 来自哪类方向 | 零分布 p95 | p99 | 搜索修正后 p | 轴外方向上的 max | 轴外 p |
|---|---|---|---|---|---|---|---|
| `rep_top1` | 0.1659 | axis_perturbed | 0.0683 | 0.0807 | 0.0000 | 0.0973 | 0.0000 |
| `rep_ngram4` | 0.2156 | axis_perturbed | 0.0734 | 0.0869 | 0.0000 | 0.1100 | 0.0000 |
| `rep_frac_topk` | 0.2817 | axis_perturbed | 0.0942 | 0.1162 | 0.0000 | 0.1445 | 0.0000 |
| `backtrack_topk` | -0.0623 | random | 0.0354 | 0.0497 | 0.0042 | -0.0623 | 0.0042 |
| `backtrack_frac` | -0.0418 | random | 0.0303 | 0.0373 | 0.0042 | -0.0418 | 0.0042 |
| `digit_mass` | 0.0609 | axis_perturbed | 0.0360 | 0.0452 | 0.0000 | -0.0581 | 0.0000 |
| `op_mass` | -0.0475 | pca_top | 0.0328 | 0.0438 | 0.0000 | -0.0475 | 0.0000 |
| `newline_mass` | -0.0538 | pca_top | 0.0384 | 0.0462 | 0.0000 | -0.0538 | 0.0000 |
| `latex_mass` | -0.0651 | random | 0.0434 | 0.0564 | 0.0042 | -0.0651 | 0.0042 |
| `top1_prob_renorm` | -0.0656 | axis_perturbed | 0.0349 | 0.0536 | 0.0000 | -0.0597 | 0.0042 |
| `entropy` ⚠️ | -0.0650 | random | 0.0359 | 0.0525 | 0.0042 | -0.0650 | 0.0042 |
| `in_think` ⚠️ | -0.0915 | pca_top | 0.0493 | 0.0702 | 0.0000 | -0.0915 | 0.0000 |
| `self_check_regex` ⚠️ | -0.0435 | pca_top | 0.0282 | 0.0358 | 0.0000 | -0.0435 | 0.0000 |
| `step_frac` ⚠️ | 0.5973 | axis_perturbed | 0.1734 | 0.2248 | 0.0000 | 0.2894 | 0.0000 |

### Δ = 100（47 条轨迹 / 29750 步 / 400 个方向）

| 观测量 | max OOF Pearson | 来自哪类方向 | 零分布 p95 | p99 | 搜索修正后 p | 轴外方向上的 max | 轴外 p |
|---|---|---|---|---|---|---|---|
| `rep_top1` | 0.0786 | axis_perturbed | 0.0337 | 0.0416 | 0.0000 | -0.0497 | 0.0000 |
| `rep_ngram4` | 0.1402 | axis_perturbed | 0.0519 | 0.0657 | 0.0000 | 0.0773 | 0.0000 |
| `rep_frac_topk` | 0.1818 | axis_perturbed | 0.0590 | 0.0680 | 0.0000 | 0.0983 | 0.0000 |
| `backtrack_topk` | -0.0570 | random | 0.0432 | 0.0530 | 0.0042 | -0.0570 | 0.0042 |
| `backtrack_frac` | -0.0472 | random | 0.0323 | 0.0415 | 0.0042 | -0.0472 | 0.0042 |
| `digit_mass` | -0.0544 | random | 0.0358 | 0.0466 | 0.0042 | -0.0544 | 0.0042 |
| `op_mass` | -0.0510 | random | 0.0376 | 0.0461 | 0.0042 | -0.0510 | 0.0042 |
| `newline_mass` | -0.0586 | random | 0.0378 | 0.0508 | 0.0042 | -0.0586 | 0.0042 |
| `latex_mass` | -0.0636 | pca_top | 0.0453 | 0.0590 | 0.0000 | -0.0636 | 0.0000 |
| `top1_prob_renorm` | -0.0552 | random | 0.0396 | 0.0483 | 0.0042 | -0.0552 | 0.0042 |
| `entropy` ⚠️ | -0.0514 | random | 0.0406 | 0.0494 | 0.0042 | -0.0514 | 0.0042 |
| `in_think` ⚠️ | -0.1657 | random | 0.0885 | 0.1281 | 0.0042 | -0.1657 | 0.0042 |
| `self_check_regex` ⚠️ | -0.0396 | random | 0.0280 | 0.0324 | 0.0042 | -0.0396 | 0.0042 |
| `step_frac` ⚠️ | 0.5931 | axis_perturbed | 0.1795 | 0.2277 | 0.0000 | 0.2881 | 0.0000 |

### Δ = 400（34 条轨迹 / 16944 步 / 400 个方向）

| 观测量 | max OOF Pearson | 来自哪类方向 | 零分布 p95 | p99 | 搜索修正后 p | 轴外方向上的 max | 轴外 p |
|---|---|---|---|---|---|---|---|
| `rep_top1` | -0.0564 | random | 0.0413 | 0.0505 | 0.0042 | -0.0564 | 0.0042 |
| `rep_ngram4` | -0.0712 | random | 0.0483 | 0.0574 | 0.0042 | -0.0712 | 0.0042 |
| `rep_frac_topk` | -0.0616 | random | 0.0436 | 0.0536 | 0.0042 | -0.0616 | 0.0042 |
| `backtrack_topk` | -0.0550 | pca_top | 0.0405 | 0.0449 | 0.0000 | -0.0550 | 0.0000 |
| `backtrack_frac` | -0.0416 | random | 0.0367 | 0.0403 | 0.0042 | -0.0416 | 0.0042 |
| `digit_mass` | -0.0714 | axis_perturbed | 0.0440 | 0.0537 | 0.0000 | -0.0660 | 0.0042 |
| `op_mass` | -0.0605 | random | 0.0418 | 0.0494 | 0.0042 | -0.0605 | 0.0042 |
| `newline_mass` | -0.0513 | pca_top | 0.0377 | 0.0452 | 0.0000 | -0.0513 | 0.0000 |
| `latex_mass` | -0.0743 | random | 0.0417 | 0.0554 | 0.0042 | -0.0743 | 0.0042 |
| `top1_prob_renorm` | -0.0702 | axis_perturbed | 0.0411 | 0.0545 | 0.0000 | -0.0547 | 0.0042 |
| `entropy` ⚠️ | -0.0782 | axis_perturbed | 0.0444 | 0.0504 | 0.0000 | -0.0547 | 0.0042 |
| `in_think` ⚠️ | -0.1517 | random | 0.0702 | 0.1034 | 0.0042 | -0.1517 | 0.0042 |
| `self_check_regex` ⚠️ | -0.0427 | pca_top | 0.0332 | 0.0385 | 0.0000 | -0.0427 | 0.0000 |
| `step_frac` ⚠️ | 0.5985 | axis_perturbed | 0.2077 | 0.2521 | 0.0000 | 0.2970 | 0.0000 |

## 6. 互检：这 4 条互相冗余吗（`mutual_redundancy`）

对每条轴 a：取它自己的最优读出方向 d*(a)（Δ=0，λ=0.01，K=256 PCA），用**其余 3 条**轴的 Gram-Schmidt 正交基投影，看 |r|/|d*| 与残差样本外 Pearson

| 轴 | 它自己的读出目标 | 投影掉 | \|r\|/\|d*\| | OOF Pearson(d*) | OOF Pearson(r) | 其他 3 条解释份额 |
|---|---|---|---|---|---|---|
| `confidence` | `top1_prob_renorm` | `caution`, `creativity`, `reasoning_deep` | 0.9612 | 0.5203 | 0.4424 | 0.2773 |
| `caution` | `backtrack_topk` | `confidence`, `creativity`, `reasoning_deep` | 0.9327 | 0.6760 | 0.4471 | 0.5624 |
| `creativity` | `backtrack_topk` | `confidence`, `caution`, `reasoning_deep` | 0.9283 | 0.6760 | 0.1693 | 0.9372 |
| `reasoning_deep` | `rep_ngram4` | `confidence`, `caution`, `creativity` | 0.9792 | 0.6149 | 0.5386 | 0.2327 |

## 7. 还剩几个互相独立的方向（下界）（`independent_direction_count`）

阈值来源：τ = 240 个随机单位方向 OOF |Pearson| 的分位数（逐目标逐 Δ）；互低余弦阈值 |cos| < 0.5（另报 [0.3, 0.5, 0.7]）；「在 S 之外」判据：投影掉 span(S) 后残差范数占比 ≥ 0.5。

| 观测量 | Δ | 超零分布 p99 的方向数 / 分母 | 超零分布 p95 的方向数 | 贪心后互相独立方向数 | 其中在 S 之外 |
|---|---|---|---|---|---|
| `rep_top1` | 0 | 45 / 401 | 76 / 401 | 6 | 4 |
| `rep_ngram4` | 0 | 45 / 401 | 64 / 401 | 7 | 5 |
| `rep_frac_topk` | 0 | 25 / 401 | 34 / 401 | 6 | 5 |
| `backtrack_topk` | 0 | 46 / 401 | 56 / 401 | 6 | 5 |
| `backtrack_frac` | 0 | 45 / 401 | 56 / 401 | 7 | 5 |
| `digit_mass` | 0 | 26 / 401 | 35 / 401 | 7 | 6 |
| `op_mass` | 0 | 5 / 401 | 15 / 401 | 5 | 5 |
| `newline_mass` | 0 | 5 / 401 | 28 / 401 | 5 | 5 |
| `latex_mass` | 0 | 4 / 401 | 20 / 401 | 4 | 4 |
| `top1_prob_renorm` | 0 | 45 / 401 | 75 / 401 | 6 | 4 |
| `entropy` ⚠️ | 0 | 45 / 401 | 75 / 401 | 6 | 4 |
| `in_think` ⚠️ | 0 | 24 / 401 | 38 / 401 | 5 | 4 |
| `self_check_regex` ⚠️ | 0 | 27 / 401 | 59 / 401 | 7 | 6 |
| `step_frac` ⚠️ | 0 | 26 / 401 | 36 / 401 | 6 | 6 |
| `rep_top1` | 1 | 45 / 401 | 62 / 401 | 6 | 5 |
| `rep_ngram4` | 1 | 46 / 401 | 56 / 401 | 8 | 6 |
| `rep_frac_topk` | 1 | 26 / 401 | 38 / 401 | 7 | 6 |
| `backtrack_topk` | 1 | 46 / 401 | 75 / 401 | 7 | 5 |
| `backtrack_frac` | 1 | 8 / 401 | 40 / 401 | 8 | 6 |
| `digit_mass` | 1 | 45 / 401 | 74 / 401 | 6 | 5 |
| `op_mass` | 1 | 45 / 401 | 55 / 401 | 6 | 4 |
| `newline_mass` | 1 | 4 / 401 | 22 / 401 | 4 | 4 |
| `latex_mass` | 1 | 6 / 401 | 71 / 401 | 6 | 6 |
| `top1_prob_renorm` | 1 | 46 / 401 | 74 / 401 | 7 | 4 |
| `entropy` ⚠️ | 1 | 45 / 401 | 74 / 401 | 6 | 4 |
| `in_think` ⚠️ | 1 | 24 / 401 | 38 / 401 | 5 | 4 |
| `self_check_regex` ⚠️ | 1 | 4 / 401 | 19 / 401 | 4 | 4 |
| `step_frac` ⚠️ | 1 | 26 / 401 | 36 / 401 | 6 | 6 |
| `rep_top1` | 20 | 26 / 401 | 35 / 401 | 7 | 6 |
| `rep_ngram4` | 20 | 28 / 401 | 37 / 401 | 9 | 8 |
| `rep_frac_topk` | 20 | 27 / 401 | 37 / 401 | 8 | 7 |
| `backtrack_topk` | 20 | 5 / 401 | 30 / 401 | 5 | 5 |
| `backtrack_frac` | 20 | 3 / 401 | 15 / 401 | 3 | 3 |
| `digit_mass` | 20 | 27 / 401 | 43 / 401 | 8 | 7 |
| `op_mass` | 20 | 5 / 401 | 20 / 401 | 5 | 5 |
| `newline_mass` | 20 | 6 / 401 | 17 / 401 | 6 | 6 |
| `latex_mass` | 20 | 4 / 401 | 18 / 401 | 4 | 3 |
| `top1_prob_renorm` | 20 | 6 / 401 | 30 / 401 | 5 | 4 |
| `entropy` ⚠️ | 20 | 5 / 401 | 30 / 401 | 5 | 4 |
| `in_think` ⚠️ | 20 | 8 / 401 | 37 / 401 | 6 | 5 |
| `self_check_regex` ⚠️ | 20 | 5 / 401 | 15 / 401 | 5 | 5 |
| `step_frac` ⚠️ | 20 | 26 / 401 | 37 / 401 | 6 | 6 |
| `rep_top1` | 100 | 27 / 401 | 47 / 401 | 8 | 7 |
| `rep_ngram4` | 100 | 26 / 401 | 39 / 401 | 7 | 6 |
| `rep_frac_topk` | 100 | 26 / 401 | 37 / 401 | 7 | 6 |
| `backtrack_topk` | 100 | 3 / 401 | 13 / 401 | 3 | 3 |
| `backtrack_frac` | 100 | 3 / 401 | 15 / 401 | 3 | 3 |
| `digit_mass` | 100 | 3 / 401 | 27 / 401 | 3 | 3 |
| `op_mass` | 100 | 3 / 401 | 21 / 401 | 3 | 3 |
| `newline_mass` | 100 | 5 / 401 | 19 / 401 | 5 | 5 |
| `latex_mass` | 100 | 4 / 401 | 15 / 401 | 4 | 4 |
| `top1_prob_renorm` | 100 | 3 / 401 | 12 / 401 | 3 | 3 |
| `entropy` ⚠️ | 100 | 3 / 401 | 16 / 401 | 3 | 3 |
| `in_think` ⚠️ | 100 | 4 / 401 | 14 / 401 | 4 | 4 |
| `self_check_regex` ⚠️ | 100 | 13 / 401 | 33 / 401 | 5 | 4 |
| `step_frac` ⚠️ | 100 | 26 / 401 | 37 / 401 | 6 | 6 |
| `rep_top1` | 400 | 3 / 401 | 18 / 401 | 3 | 3 |
| `rep_ngram4` | 400 | 3 / 401 | 16 / 401 | 3 | 3 |
| `rep_frac_topk` | 400 | 3 / 401 | 35 / 401 | 3 | 3 |
| `backtrack_topk` | 400 | 5 / 401 | 14 / 401 | 5 | 5 |
| `backtrack_frac` | 400 | 4 / 401 | 20 / 401 | 4 | 3 |
| `digit_mass` | 400 | 20 / 401 | 38 / 401 | 4 | 3 |
| `op_mass` | 400 | 14 / 401 | 31 / 401 | 4 | 3 |
| `newline_mass` | 400 | 4 / 401 | 14 / 401 | 4 | 4 |
| `latex_mass` | 400 | 4 / 401 | 17 / 401 | 4 | 4 |
| `top1_prob_renorm` | 400 | 13 / 401 | 34 / 401 | 4 | 3 |
| `entropy` ⚠️ | 400 | 25 / 401 | 37 / 401 | 6 | 5 |
| `in_think` ⚠️ | 400 | 4 / 401 | 25 / 401 | 4 | 4 |
| `self_check_regex` ⚠️ | 400 | 4 / 401 | 17 / 401 | 4 | 4 |
| `step_frac` ⚠️ | 400 | 26 / 401 | 37 / 401 | 6 | 6 |

阈值敏感性（贪心后互相独立方向数，|cos| 阈值 0.3 / 0.5 / 0.7）：

|观测量|Δ|sep0.3|sep0.5|sep0.7|
|---|---|---|---|
|rep_top1|delta0|6|6|6|
|rep_ngram4|delta0|5|7|7|
|rep_frac_topk|delta0|6|6|6|
|backtrack_topk|delta0|6|6|7|
|backtrack_frac|delta0|6|7|7|
|digit_mass|delta0|7|7|7|
|op_mass|delta0|5|5|5|
|newline_mass|delta0|5|5|5|
|latex_mass|delta0|4|4|4|
|top1_prob_renorm|delta0|5|6|6|
|entropy|delta0|5|6|6|
|in_think|delta0|5|5|5|
|self_check_regex|delta0|7|7|8|
|step_frac|delta0|6|6|7|
|rep_top1|delta1|6|6|6|
|rep_ngram4|delta1|7|8|8|
|rep_frac_topk|delta1|6|7|7|
|backtrack_topk|delta1|5|7|7|
|backtrack_frac|delta1|8|8|8|
|digit_mass|delta1|5|6|6|
|op_mass|delta1|5|6|6|
|newline_mass|delta1|4|4|4|
|latex_mass|delta1|6|6|6|
|top1_prob_renorm|delta1|5|7|7|
|entropy|delta1|5|6|6|
|in_think|delta1|5|5|5|
|self_check_regex|delta1|4|4|4|
|step_frac|delta1|6|6|7|
|rep_top1|delta20|6|7|7|
|rep_ngram4|delta20|8|9|9|
|rep_frac_topk|delta20|7|8|8|
|backtrack_topk|delta20|5|5|5|
|backtrack_frac|delta20|3|3|3|
|digit_mass|delta20|8|8|8|
|op_mass|delta20|5|5|5|
|newline_mass|delta20|6|6|6|
|latex_mass|delta20|4|4|4|
|top1_prob_renorm|delta20|5|5|5|
|entropy|delta20|5|5|5|
|in_think|delta20|6|6|6|
|self_check_regex|delta20|5|5|5|
|step_frac|delta20|6|6|7|
|rep_top1|delta100|7|8|8|
|rep_ngram4|delta100|6|7|7|
|rep_frac_topk|delta100|6|7|7|
|backtrack_topk|delta100|3|3|3|
|backtrack_frac|delta100|3|3|3|
|digit_mass|delta100|3|3|3|
|op_mass|delta100|3|3|3|
|newline_mass|delta100|5|5|5|
|latex_mass|delta100|4|4|4|
|top1_prob_renorm|delta100|3|3|3|
|entropy|delta100|3|3|3|
|in_think|delta100|4|4|4|
|self_check_regex|delta100|5|5|5|
|step_frac|delta100|6|6|7|
|rep_top1|delta400|3|3|3|
|rep_ngram4|delta400|3|3|3|
|rep_frac_topk|delta400|3|3|3|
|backtrack_topk|delta400|5|5|5|
|backtrack_frac|delta400|4|4|4|
|digit_mass|delta400|4|4|4|
|op_mass|delta400|4|4|4|
|newline_mass|delta400|4|4|4|
|latex_mass|delta400|4|4|4|
|top1_prob_renorm|delta400|4|4|4|
|entropy|delta400|6|6|6|
|in_think|delta400|4|4|4|
|self_check_regex|delta400|4|4|4|
|step_frac|delta400|6|6|7|

## 8. 结论

**判定：不完备**（`headline.completeness_verdict`）

- 分母：非定义式目标格 **50** 个（每个观测量 × 5 个 Δ），其中残差仍超零分布尾部的 **22** 个（`headline.n_non_definitional_cells_with_readable_residual`）
- 每格搜索分母 **400** 个方向，零分布 **240** 个随机方向（`direction_search.delta0.n_random_directions_in_null`）

**候选池 = 400 个采样方向 + 1 个该观测量自己的最优读出方向；门槛 = 240 个随机方向 OOF |Pearson| 的 p99；去重 = 贪心取 |cos| < 0.5。在 Δ=0 上，10 个非定义式观测量每一个都还剩至少 4 个互相近正交、且落在 4 条命名轴张成之外的可读方向（下界），中位数 5.0 个。**

| Δ | 观测量数 | 候选池 | 互相独立方向数 min/中位/max | 其中在 S 之外 min/中位/max |
|---|---|---|---|---|
| 0 | 10 | 401 | 4 / 6.0 / 7 | 4 / 5.0 / 6 |
| 1 | 10 | 401 | 4 / 6.5 / 8 | 4 / 5.0 / 6 |
| 20 | 10 | 401 | 3 / 5.5 / 9 | 3 / 5.5 / 8 |
| 100 | 10 | 401 | 3 / 3.5 / 8 | 3 / 3.5 / 7 |
| 400 | 10 | 401 | 3 / 4.0 / 5 | 3 / 3.0 / 5 |

残差仍可读的非定义式格（按 OOF |Pearson| 排，前 15）：

| 观测量 | Δ | 残差 OOF Pearson | 零分布 p99 | S 解释份额 |
|---|---|---|---|---|
| `digit_mass` | 0 | 0.7667 | 0.3074 | 0.2031 |
| `newline_mass` | 0 | 0.6046 | 0.1584 | 0.0265 |
| `op_mass` | 0 | 0.5654 | 0.1894 | 0.0162 |
| `rep_frac_topk` | 0 | 0.5442 | 0.1949 | 0.4158 |
| `latex_mass` | 0 | 0.4291 | 0.1150 | 0.0398 |
| `rep_ngram4` | 0 | 0.3889 | 0.2167 | 0.6000 |
| `rep_top1` | 0 | 0.3660 | 0.1755 | 0.4862 |
| `digit_mass` | 1 | 0.3332 | 0.1512 | 0.2800 |
| `rep_ngram4` | 1 | 0.3305 | 0.1926 | 0.6125 |
| `backtrack_topk` | 1 | 0.3200 | 0.1431 | 0.4441 |
| `rep_top1` | 1 | 0.3191 | 0.1410 | 0.4473 |
| `rep_frac_topk` | 1 | 0.2940 | 0.1476 | 0.6601 |
| `backtrack_topk` | 0 | 0.2661 | 0.2583 | 0.8450 |
| `newline_mass` | 1 | 0.2400 | 0.0706 | 0.0097 |
| `backtrack_frac` | 1 | 0.2077 | 0.0643 | 0.2624 |

### 结论要说清的三件事

1. **S-share 是可信的，因为它有阳性对照也有阴性对照。** 4 条轴的定义式目标（`step_frac` 给 S-share 0.997、`self_check_regex` 给 0.999、`entropy` 给 0.875）说明装置在 S 真的覆盖该方向时**会**报出接近 1 的份额；而 `op_mass` / `newline_mass` / `latex_mass` / `digit_mass` 只得到 0.016–0.20，同一把尺子读出的完全不同的数。
2. **缺口集中在 Δ=0–20，Δ≥100 全部落回噪声。** 这与 4 条轴都是「token 局部状态」的定位一致：它们描述的是当前 token，不描述更远未来。
3. **必须扣掉定义式格。** `step_frac`、`self_check_regex`、`in_think`、`entropy` 这四列的漂亮数字是构造必然，本报告把它们全部标为阳性对照，不作为不完备性的证据。
