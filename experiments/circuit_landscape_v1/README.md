# Circuit Landscape v1

在 4 条 AIME 25 轨迹上，逐位置注入 +v / −v / 随机方向 / 载体阻断 / 载体恢复，
并把**原生 SwiGLU 单元的残差写入**逐层精确记账。

- 采集器：`backend/examples/collect_circuit_landscape.py`（需 GPU）
- 记账核心：`backend/core/circuit_trace.py`（逐层挂 5 个 hook，闭合恒等式）
- 注入内核：`backend/core/neuron_mediation.py`（原生单元的 patch 语义）
- 页面构建器：`backend/examples/build_circuit_landscape.py`（**纯 CPU**）
- 页面：`/circuit-landscape`（`frontend/components/CircuitLandscape.tsx`）
- 进度图面板：`frontend/components/SteeringProgressMap.tsx`
- 详细审计与理论：`docs/STEERING_LEDGER.md`

## 6 个 arm

| arm | 干预 |
|---|---|
| `baseline` | 无 |
| `plus` | +v，block 20 最后一个输入位置 |
| `minus` | −v，同上 |
| `random` | 同范数随机方向（**本轮只有 1 个**） |
| `block` | +v **且** 256 个冻结单元的 product 换成 baseline 的 product |
| `restore` | 无注入 **且** 256 个冻结单元的 product 换成 +v 的 product |

`block` / `restore` 替换的是 down_proj 的**输入**（原生单元的激活 a），
不是写入方向 d_i。down_proj 是线性的，所以替换 a 的 32 个坐标
**精确等价于**让这 32 个单元按 donor 的激活去写残差。

## 闭合恒等式

    h_out = h_in + attn_write + Σ_i a_i · d_i

三个张量来自三个**互相独立**的模块（`self_attn` 输出 / `down_proj` 输出 / block 输出），
所以"hook 抓错张量"会让闭合炸掉，而不是悄悄通过。
实测最大相对闭合误差 **2.25e-07**（float32 噪声量级）。

## 主结果

| 量 | 值 |
|---|---|
| site 数 × arm 数 | 32 × 6 = 192 次前向 |
| 决策带（anchor，marker 就是下一个 token） | 4 site，baseline marker 集合概率 0.23 – 0.86 |
| 底噪带（非 anchor） | 28 site，baseline marker 集合概率 ~1e-7 – ~1e-21 |
| `+v` ΔlogP（决策带 / 底噪带 / 全样本） | +0.158 / +1.831 / +1.621 nats |
| `−v` ΔlogP（决策带 / 全样本） | −0.344 / −1.189 nats |
| 随机方向 ΔlogP（决策带 / 全样本） | −0.008 / +0.064 nats |
| 决策带 Δp（`+v` / `−v`） | **+8.6 pp / −17.1 pp** |
| 决策带 log-odds 位移比 \|Δ−v\| / \|Δ+v\| | **1.30**（nats 口径是 2.18） |
| 决策带信噪比 \|Δ+v\| / \|Δ随机\| | 2.8 / 3.1 / 7.1 / 4.4（几何均值 4.0） |
| 载体边际贡献（阻断效应 / 全效应，决策带） | 11.6% |
| 载体独立贡献（恢复效应 / 全效应，决策带） | 19.4% |
| 符号一致性 | `+v` 32/32 为正，`−v` 32/32 为负 |
| argmax 改动 | `+v` 3/32（全在底噪带），`random` 2/32，`restore` **0/32** |

**读法**：全样本那个 +1.62 nats **98.8% 来自底噪带**，而底噪带的 nats 变化是
尾概率的相对变化（1e-10 量级），行为上没有意义。
**决策带上的 +8.6 pp 才是本轮唯一可作行为主张的数字**，
而它只压过了**一个**随机方向（n=1 ⇒ 只能否证到 0.5 分位），
所以 L6（注入改变行为**且**专属于该方向）**仍然不能声称**。

## 文件

- `results/circuit_landscape.json`（8.5 MB）：原始导出，192 个 site×arm 的读数、逐层写入、unit 级 gate/value/product/write
- `results/circuit_landscape.npz`（81 MB）：审计档案，含**未投影的 2048 维**原始写、每层 basis/mean、down_proj 列
- `results/run.log`：逐 site 的闭合值
- `frontend/public/latent/data/circuit_landscape.json`：**页面读取的裁剪副本**（目录被 gitignore）
- `frontend/public/latent/data/steering_progress.json`：进度图面板的数据

## 边界

- **不是自由生成**：读数是"下一个 token 是 marker 的概率"，在**相同前缀**上做局部注入。
  产物自己的 `scope` 字段写着 `not free-running steered rollouts`。
- **随机臂只有 1 个**，32 个 site 共用。按项目自己的尺子，这轮只能说"压过了 1 个随机方向"。
- **读数是 7 个 marker id 的集合概率**；这 7 个 marker 逐个看符号是分裂的
  （只有 7196 是正向读出，见 `docs/READOUT_ATLAS.md`），集合口径把它们混在一起。
- **展示单元是按响应幅度选出来的**（每个 site/block 取 top-6 ∪ top-6），
  它的"响应排序"列按定义是构造出来的，不是重要性证据。
- 每层 32 个冻结载体候选中，平均只有约 1.2 个会落进展示表格。
- 逐层写入账本只覆盖 block 20–27（注入点及其后），不是全 28 层。
- 单模型、单向量、2 道题。

## 复现

```bash
# 1) 采集（需 GPU；本轮的产物已经在 results/ 里）
bash experiments/circuit_landscape_v1/start_remote.sh

# 2) 生成页面 payload 与进度图数据（纯 CPU，无 GPU）
python3 backend/examples/build_circuit_landscape.py --check     # 先看体积与账本
python3 backend/examples/build_circuit_landscape.py

# 3) 测试
python3 -m pytest backend/tests/test_circuit_landscape_build.py -q
```

⚠ **第 2 步必须先跑**，否则 `/circuit-landscape` 会 404：
页面读的两个 JSON 都在 `frontend/public/latent/data/`，而那个目录被 `.gitignore` 忽略，
所以仓库里没有、也没有任何脚本会自动生成它们 —— 除了第 2 步这个脚本。
