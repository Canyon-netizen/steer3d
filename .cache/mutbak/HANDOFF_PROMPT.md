# steer3d 续做交接提示词（可直接整段粘贴给新会话）

> 这段提示词是**自足**的：一个没见过本项目的新模型读完应当能直接接着干。
> 数字全部来自实测产物，标注了来源文件；没有一条是凭印象写的。

---

## 0. 你的任务

继续完成 steer3d 项目的最终目标。这个项目的产出要求是**六件**：

1. 把 AIME 相关问题全部用 **Qwen3-1.7B** 跑一遍；
2. 生成 **2D 网站**并升级为 **3D**，展示 hidden states 的变化；
3. 展示**各 hidden states 如何推导出 token**；
4. 把 **token 映射回 hidden states**；
5. 输出**向量干预结果并解释向量作用**；
6. 提取一套**通用的「解释向量可解释性理论」**。

**当前进度：1、2、4、6 已有实质交付；3 有部分设施；5（B 路干预实验）卡在一个科学问题上。**
你要做的是把 5 收尾，并把 6 与 B 路的新发现打通。

---

## 1. 仓库与环境（照抄，不要自己猜）

| 项 | 值 |
|---|---|
| 本地仓库 | `/Users/zhourui/code/steer3d`，分支 `main`，HEAD = `4ec77ba` |
| 远端 | `zju-53`（Linux，共享集群，**别人的卡也在跑，认卡一律用 GPU UUID**） |
| 远端工作树 | `/home/zhourui/steer3d` —— **git 已分叉且有他人未提交改动，禁止任何 git 操作** |
| 本任务全部产物 | `/home/zhourui/steer3d_bpath/` |
| 远端 python | `/home/zhourui/miniconda3/envs/easysteer/bin/python`（3.12.13 / torch 2.11.0+cu130） |
| 模型 | `/home/zhourui/.cache/huggingface/models/Qwen--Qwen3-1.7B/snapshots/master` |
| 本机 python | `python3` = CommandLineTools **3.9.6**；跑任何东西要 `PYTHONPATH=.cache/pylibs` |
| 依赖位置 | torch / transformers / websockets / scipy 都在 `.cache/pylibs` |
| 本机卡 | `/tmp` 不可写；`ps`/`pgrep`/`pkill`/`kill`/`timeout` 本地不可用（远端可用） |
| 改含中文的文件 | **绝不用 `sed -i`**（会把中文重编码成乱码）。用 `edit` 工具，或 Python 显式 `encoding="utf-8"` |
| 改完含中文的大文件 | 必须验坏字：`src.count("\ufffd") == 0` |

**关键环境坑**
- 安全网关拦含 heredoc 的 bash ⇒ 复杂脚本一律 `write` 成文件再 scp / 执行。
- 安全网关拦 `rm -rf` ⇒ 删除用 `"/Users/zhourui/.minimax/bin/mavis-trash" -- "<path>"`。
- `.cache/` 被 `.gitignore` 整目录忽略 ⇒ 提交要 `git add -f`；**绝不 force-add 目录**，只点名文件。
- commit 用 `git commit -F <msgfile> -- <显式路径>`，然后 `git show --name-only` 回读。**绝不用 `git add -A`**。
- 远端后台任务不要挂在受 400/600 s 限制的 bash 里 ⇒ `nohup ... > log 2>&1 &`，写脚本文件再跑，加 `-u`（否则输出缓冲，日志是空的）。
- **带正则的 Python 永远写成文件**，不进 shell 单行、不进 ssh 单行。
- 大数组不要 `np.load` 整块读（远端 hidden_states 单文件 380 MB）⇒ 形状用 `zipfile` + `numpy.lib.format.read_array_header_1_0/2_0` 读 `.npy` 头。注意 **numpy 2.x 已删掉 `format._read_array_header`**，必须按版本分派。
- 远端 safetensors 含 bfloat16 ⇒ `safe_open(..., framework="np")` 会 TypeError，**必须用 `framework="pt"`** 再 `.to(torch.float32)`。
- numpy 数组轴序：npz 的 `hidden_states` 是 `(T, L, D)` ⇒ 取 `[t-1, LAYER, :]`。写成 `[LAYER][t-1]` 会切错轴（我踩过，第一次运行就 IndexError）。

---

## 2. 铁律（违反过很多次，每条都有代价）

1. **判据的输入必须用被测代码自己用的那个来源。** 常量从 `r6_rerun.py` import，不要复制一份。
   （我凭印象写过 `MARKER_IDS=[151645,151644]`，真值是 7 个 `[13824,14190,6771,10061,7196,88190,80022]`，照抄会把 marker 全漏掉。）
2. **动任何跨产物取数的下标之前，先跑只读坐标系核对。** 本项目因此栽了**三次**（token 位置差 1、相对/绝对混用、**层差 1**），三次都不报错、不崩、照常训出 `w`。
3. **判红先怀疑判据 / 变异 / 环境 / 坐标系**，最后才怀疑模型。
4. **「变异打空」与「判据没牙齿」必须分开**；**全 PASS 的判据等于没有判据**。
5. **饱和断言恒真。** `0.0 >= 0.0` 成立 ⇒ 零响应也能判通过。凡判据涉及比较，先想「全等时会不会恒真」。
6. **判决规则必须取数前写死。** 不许事后挑 α、改词表、挪词、改剂量求绿。预登记原文不许改，只追加修订记录，披露制。
7. **判绿也不算证据，除非证明判据有牙齿。** 把「旧实现」原样抄进自检文件当参照，断言同一份数据下旧判红、新判绿。
8. **既测判红也测判绿。** 永远红的闸门和永远绿的闸门一样没用。
9. **临时文件不能放在判据扫描目录内。** 显式落到 `.cache/mutbak/`，并用 `atexit` 清理（本机 `TMPDIR` 指向仓库根目录，`mkdtemp()` 会把夹具丢在仓库里，我已经漏出过 `tmpujiphne5/`，18 个文件）。
10. **Python 的 `str.replace` 没命中时静默返回原串。** 批量改脚本时**每处都要断言命中**，否则改了一处忘了另一处（我踩过：夹具根本没改，报出来的红是假的）。
11. **历史探针脚本刻意不改。** 结论已被引用的，只加文件头警示，改了会让已记录数字无法复现（例：`.cache/bpath/gap_norm_measure.py`）。
12. **无关的既有改动原样保留**，不要顺手清理。

---

## 3. B 路现状（你接手的就是这里）

### 3.1 数据已经齐了，不要重跑

- **B 路生成：120/120 轨迹，0 OOM，0 ERROR，11h14m**（每条 338 s，cap 8192，think + no_think 各 60）。
  位置：`/home/zhourui/steer3d_bpath/gen_b2/aime/`（`.npz` + `.json` 侧车）。
- **60 题最终标签**（R-27 四类陈述规则），已在远端 `labels_full60.json`，本地副本 `.cache/mutbak/strict_label_b2_full60.json`：

  | 模式 | n | 触顶 | 有标签 | correct | wrong | unlabeled |
  |---|---|---|---|---|---|---|
  | think | 60 | 49 (82%) | 21 (35%) | **13** | **8** | 39 |
  | no_think | 60 | 6 (10%) | 54 (90%) | **6** | **48** | 6 |

  ⇒ P6 要求 correct≥10 且 wrong≥8：**think 两项都过，可以出判决**；no_think correct 不足 ⇒ 样本不足。

### 3.2 判决链已就绪并自检通过，可以直接用

| 脚本 | 作用 | 自检 |
|---|---|---|
| `.cache/bpath/r6_rerun.py` | P0–P9 执行（训 w、注入、读数） | — |
| `.cache/bpath/r6_verdict.py` | P6/P7/P8 + 次级 S1–S3 判决 | 26/26 |
| `.cache/bpath/p9_verdict_selftest.py` | P9 判定器（含新旧闸门对照） | 11/11 |
| `.cache/bpath/load_xy_pos_selftest.py` | token 轴 + **层轴** 坐标 | 12/12 |
| `.cache/bpath/r6_verdict_scipy_check.py` | 与 scipy 交叉验证 | 0 失败 |
| `.cache/bpath/coord_triple_check.py` | 三方坐标系核对 | 24/24 |
| `.cache/bpath/hs_layer_index_check.py` | **层映射判据 J1** | — |
| `.cache/bpath/layer_inject_sweep.py` | 注入层扫描（含校准点） | — |
| `.cache/bpath/marker_id_frequency.py` | marker 逐 id 点积 × 语料频次 | — |
| `.cache/bpath/w_unembed_align.py` | `w·U[marker]` 对齐度 | — |

### 3.3 卡在哪：P9 判据 1/3

最新 P9（臂 B，`w_L19_m0.npy`，剂量 `rel×class_gap`，`dose_source=w_meta`）：

| 轨迹 | mode | w+@0.5→1.0 | w−@0.5→1.0 | rand@1.0 | 判定 |
|---|---|---|---|---|---|
| `p00__no_think` | no_think | **0.5 → 1.0** | −1.0 → **−3.0** | −0.25 | **PASS** |
| `p00__think` | think | 0.0 → **−0.5** | −1.0 → **−7.75** | −0.25 | FAIL（+w 不单调升） |
| `p01__no_think` | no_think | **0.5 → 1.0** | −1.25 → **−3.125** | −1.0 | FAIL（1.0 未超过 1.0） |

读法：
- **两条 no_think 已经单调、符号正确**，且 −w 效应远超同剂量随机方向 ⇒ **装置是好的**。
- `p01__no_think` 是**并列边界**（1.0 == 1.0，`>` 不成立），它本身满足单调性与符号正确。要不要把并列算通过 = 改判据，**当前决定是不改**。
- `p00__think` 的 **−w 效应 −7.75 极大且单调**，说明 think 上装置**有作用**，缺的只是「+w 把 marker 抬上去」这一半 ⇒ **待归因**。

---

## 4. 必须知道的坐标系事实（都已实测钉死，别再重犯）

```
npz 的第 k 层 == HF 的 hs[k+1]        （不是 hs[k]！采集端 for li in range(1, len(hs)) 丢了 embedding 那层）
注入点 = block LAYER 的**输入** = hs[LAYER] = **npz 第 LAYER-1 层**（LAYER=20 ⇒ npz 第 19 层）
注入下标 = ids[:P+t] 的最后一位 = **生成段内 t-1**（npz 只含生成段，不含 prompt）
npz 的**最后一层是过了最终 RMSNorm 的**（HF 的 all_hidden_states 末项就是 norm 之后的值）
lm_head.weight 与 embed_tokens.weight **逐位相同**（tied）
```

**J1 判据（逐位相等，不靠文档不靠记忆）**：`last_hidden` 与 `hidden_states[:,27]` 最大绝对差 **0**，
与第 26 层差 **1928**。⇒ 把 `npz[k]==hs[k+1]` 钉死。

**这三条现在都有运行期守卫**（`r6_rerun.py`）：
- 守卫 1（逐条）：`shape[1] != N_BLOCKS(28)` 抛错（若哪天改成 29 层，映射会翻转，必须重算 `NPZ_LAYER`）。
- 守卫 2（逐条）：`shape[0] != n_generated_tokens` 抛错。
- 守卫 3（开训前一次）：`verify_npz_layer_map()` 做 `last_hidden == hidden_states[:,-1]` 逐位比对。

---

## 5. 本项目已经拿到的实质结论（这些是资产，别推翻）

### 5.1 装置是好的，但**一阶预测被下游 8 层高估约 43 倍**

在 `L=-1`（`model.norm` **输出**之后、`lm_head` 之前）注入时，下游是恒等映射，
`Δlogit = α·(w·lm_head[marker])` **精确成立**（校准点）：

```
预测 = class_gap 231.978 × 频次加权点积 0.18424 ≈ +42.7
实测（L=20 注入，两条 no_think）            = +1.0
```

同一批数据里 `' the '` 预测 −5.7944 / 实测 −5.7969、−5.7891、−5.8047 **逐位吻合**
⇒ 钩子、公式、归一化口径都没错，差的正是下游 block。

层扫描给出同一机制的直接证据（注入层 0 → −1，效应跨两个数量级）：
`L=0 −32.7 | L=12 −29.5 | L=20 −1.25 | L=27 +0.5` ⇒ **注入越早效应越大，越晚越小**。

> **结论：`w·U[marker]` 是可靠的「符号与相对排序」指标，但绝不是效应幅度的预测器，
> 两者之间隔着一个未建模的下游增益 G。不得因为实测远小于预测就判「装置无效」。**

### 5.2 「推理正确」不等于「结果变好」

修订 7 出于坐标系把训练位置从 `H[t]` 改成 `H[t-1]`（注入点确实在 `t-1`，推理成立），
但实测 `H[t]` 训出的 `w` 对 marker 的对齐度是 `H[t-1]` 的 **5.8 倍**：
算术均值 +0.1855（7/7 全正）vs +0.0317（4/7）。
**「坐标系对齐」是必要条件（同空间），不是充分条件**——该空间里训出的方向
还得恰好指向目标 token。

### 5.3 算术均值会掩盖符号分裂

`w·U[marker]` 的**算术均值**是粗指标。`old_w_t1` 算术均值 +0.0317（看着是正的），
逐 id 却是 13824 −0.013 / 14190 −0.039 / 10061 −0.007，
而 13824 与 10061 各占语料 **21%**。
P9 读的是 `lse(lg[MARKER_IDS])`，一阶近似是 `Σ_j p_j·α·(w·U[j])`，
**起决定作用的是当前概率最高的那一个** ⇒ 必须逐 id + 词频看。
用 `.cache/bpath/marker_id_frequency.py`，看「频次加权」与「高频负 id」两项。

### 5.4 选臂规则已取数前写死，且执行结果是臂 B

两臂都修好层（`npz_layer=19`）：

| 臂 | `pos_offset` | sign_gap | class_gap | 频次加权 | 高频负 id |
|---|---|---|---|---|---|
| A | −1（`H[t-1]`） | 0.0664 | 126.94 | +0.0286 | 13824, 10061 |
| **B** | **0（`H[t]`）** | **0.2165** | **231.98** | **+0.1842** | **无** ← 选中 |

---

## 6. 下一步（已在预登记里写死，照做）

**完整预登记：`.cache/xcheck/R6_RERUN_PREREG.md`，1054 行，修订 1–11（§11.7 是执行记录）。**
**动 B 路之前先读修订 9、10、11 三节**，那里有全部实测数字与作废清单。

0. ⚠ **【进行中，接手先查】** 臂 B 的 think 剂量扫描**已启动、可能已跑完**：
   ```
   ssh zju-53 'cd /home/zhourui/steer3d_bpath && cat dose_B.done 2>/dev/null && tail -40 dose_B.log'
   ```
   - 脚本：`run_dose_B.sh`；产物 `dose_sweep_B.json`；日志 `dose_B.log`
   - 用的阶梯 `[0.02,0.05,0.1,0.25,0.5,1.0]` 与 D1–D4 判据**一个字未改**
     （写于发现层错位之前，先于任何臂 B 结果）
   - **要回答的唯一问题**：think 上 `+w` 是「小剂量也不升」（D2 ⇒ 方向问题），
     还是「大剂量转负、小剂量其实正常」（D1 ⇒ 量纲问题）
   - **不管结果如何，剂量阶梯与判据都不许改。** 若 D1 成立，如实报
     「P9 那条要求 rel{0.5,1.0} 单调升的闸门本身过严」，**但本轮仍不改闸门**
     ——改剂量和改闸门是两回事：前者永远不做，后者要单独立修订说明理由。
1. **think 轨迹上的剂量-位置二维扫描**（若上面那次已覆盖剂量，则补「位置」这一维）。
2. **P9 的处置**：若 P9 过 ⇒ 直接跑 R-6 全量 + `r6_verdict.py` 出 P6（think）+ S1–S3。
   若始终不过 ⇒ **如实交付「不出判决」+ §5.1 的机制结论**。
   **这本身就是可发表的实质结果，不得硬凑。**
3. **把 §5.1 的结论并入理论交付**（见下节），这是当前最有价值的一步。
4. **把臂 B 的结果接进网站**（见 §8）。这是当前**最明确的产品缺口**：
   网站里已有 177 个数据文件（`hs_00..23.bin`、`mean_*.bin`、`pca_*.bin`、
   `logit_lens.json`、`token_backmap.html`、`steer_directions.json`、
   `intervention_threshold_law.json`、`evidence_ladder.json`），
   但**最新这几轮的 B 路结果一个都没进去**。
5. 不要重跑 B 路生成、不要重训 `w_real`/`w_old`/`w_t1`（**已全部作废**，
   它们是在错的那一层上训的）。

---

## 7. 交付第 6 项（理论）时的现状与建议

**已有：**
- `docs/STEERING_INTERPRETABILITY_FRAMEWORK.md`（8832 行，已提交 446c634）
  —— 它的 §8 自称是「本项目真正的产物」：**八级证据阶梯 + 六条可迁移断言**。
- `docs/VECTOR_FUNCTION_THEORY.md`（40 KB，**今天 19:58 生成，尚未提交**）。

**⚠ 以下是别人的在制品，不要改动、不要提交、不要用 `git add -A`：**
```
 M README.md
 M backend/README.md
 M backend/requirements.txt
 M datasets/upload_to_hf.py
 M docs/STEERING_INTERPRETABILITY_FRAMEWORK.md
?? backend/core/vector_explanation.py        （334 行，今天新增）
?? backend/examples/explain_vector.py        （198 行，今天新增）
?? backend/examples/analyse_answer_shift.py
?? backend/examples/output/layer_profiles.json
?? datasets/upload_with_dns_patch.py
?? frontend/public/layer_profiles.json
?? lockfile
?? scripts/refresh_layer_profiles.sh
```

**重要**：`backend/core/vector_explanation.py` 的 docstring 已经写了
「Observation measures association on recorded states. **Response runs the actual model at a fixed
prefix, so downstream blocks and normalization are included.** Neither instrument identifies a
reasoning algorithm or causal necessity.」
—— 这与 §5.1 的 43 倍衰减**是同一件事**，说明作者已经知道一阶预测不够。
你的增量应该是**把这个量化的 43 倍和层剖面写进理论**：
「一阶可读性 ≠ 因果有效性，中间隔着一个下游增益；必须实测响应，不能靠观测推幅度」。
这条正好补上 `VECTOR_FUNCTION_THEORY.md` 缺的**定量锚点**。

---

## 8. 网站侧（交付第 2–4 项）

- 现状：`frontend/public/latent/`（`index.html` + `data/` 261 MB + `data06/` +
  `token_backmap.html` + `models.json` + `INTERPRETABILITY.md`）。
- **3D / 页面改动必须用 `mcp_browser` 实际点过**，不能只看代码。
- 构建注意：`NEXT_PUBLIC_WS_URL` 是构建时内联的；
  `verify_scene_link.mjs` 需要 `STEER3D_WEBGL=1`；后端端口变量是 `REASONING3D_PORT`。

**建议的增量**：把 B 路的注入实验做成一屏可交互的「干预」页——
选一条轨迹 → 选一个 marker 位置 → 扫剂量 → 同时显示
(a) 该位置的 marker logprob 随剂量变化（+w / −w / 随机三条）、
(b) **注入层阶梯曲线**（§5.1 的层剖面，直接可视化「注入越早效应越大」）、
(c) 逐 marker id 的 `w·U` 与语料频次（§5.3）。
这三样合起来就是「hidden states 如何推导出 token」+「token 映射回 hidden states」+「干预结果与向量作用解释」的**可交互证据**。

---

## 9. 提交纪律

- commit message **用中文**，代码标识符与 CLI 用英文。
- `.cache/` 下的脚本与**小型**判决产物用 `git add -f` 点名添加；
  **绝不 force-add 目录、大体量原始数据、日志、`.pyc`**。
- 每笔提交后 `git show --name-only` 回读，确认没混入他人改动。
- 用户的 `.gitignore` 是有意的设计，绕过它会把刻意排除的路径塞进不可撤销的历史。

---

## 10. 一句话交代现在的处境

B 路的数据、判决链、坐标系守卫、自检全部就绪；**卡点是一个科学问题而不是工程问题**：
在 think 轨迹上，注入 `+w` 不单调地把 `\boxed` 抬上去（但 `−w` 效应很大且单调，
说明装置有作用）。同时我们已经拿到一条**可发表的机制结论**：
**`w·U` 只预测符号与排序，不预测幅度；幅度会被下游 8 层衰减约 43 倍。**
按纪律走：如实出结论，不调剂量求绿，把机制结论并进理论交付。