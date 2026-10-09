# B 路收尾补充测量协议

本协议追加于原剂量扫描完成后、补充位置及臂 B 层扫描取数之前。
不替换 R6_RERUN_PREREG.md，不修改 P9、P6、D1 至 D4，也不重训方向。

## 测量范围

- 使用既有 w_L19_m0.npy 及其 metadata 中的 class_gap。
- 剂量直接 import 原 dose_sweep.py 的 DOSE；P9 剂量直接 import r6_rerun.py。
- 四条轨迹固定为 p00/p01 的 think/no_think，不依据新响应选择轨迹。
- 位置直接调用 r6_rerun.sample_markers，覆盖最多六个非空分位。
- 在原 block 输入 LAYER=20 的最后一个前缀 token 注入，fresh forward，use_cache=False。
- 随机方向沿用 seed=42、单个标准正态单位向量，在全部位置和剂量保持不变。
- 层扫描直接 import layer_inject_sweep.LAYER_LADDER，使用上述四条轨迹的第一个抽样位置。
- 模型精度保持 bfloat16；补充 marker 集合的完整 softmax logprob，分别保留 raw logsumexp。
- 保存各 block 输入和最终 norm 输出的最后一个 token 状态。3D 用同一层的共享 PCA 基
  展示相对 baseline 的位移；不连接不同层的独立 PCA 坐标，不赋予 PCA 轴语义。

## 数据与装置核对

- NPZ 仅读数组头和 token_ids；核对 (T,28,2048)、T 与侧车生成数一致。
- prompt 重新分词必须与侧车 prompt_tokens 一致；marker id 从执行器 import。
- 预测 marker t 的前缀严格止于 P+t，不包含 marker 本身；注入在 P+t-1。
- 同一前缀重复 baseline 必须逐位相等。空挂钩不改变 logits。
- norm 后校准逐 marker token 使用实际有效的 norm 状态增量与 lm_head 权重计算，
  对比逐 token logit 差。误差界包含两端 bfloat16 舍入及 float32 累加的保守界；
  必须同时存在非零注入和非零预测。集合 logsumexp 不用向量点积的算术均值替代。

## 判决及陈述规则

- 主 R6 P6/P7/P8 是否可发布仅服从原 P9；P9 不过即交付“本轮不出主判决”。
- 补充扫描属于描述性机制证据，不构造新的显著性检验，不选择更有利剂量。
- D4 独立核对必须包括两条 no_think，逐条检查完整阶梯；空组不能 PASS。
  原脚本只检查已经通过单调性筛选的集合，存在恒绿漏洞；保留历史脚本并另作审计。
- 最小正剂量不是数学上的零点导数；bfloat16 量化粒度附近的读数不作导数结论。
- 区分方向、剂量、位置、模型精度、raw logits 与归一化概率。
- “43 倍”目前是频次加权 unembedding 参考值与某位置实测值的比，不能当作实测雅可比
  增益；已有 layer_sweep_t1.json 使用不同向量和 gap，不混作臂 B 的校准证据。
- 既有历史实验文件不改写；新结论引用文件哈希、向量哈希和坐标。
