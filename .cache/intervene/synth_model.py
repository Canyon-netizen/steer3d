"""合成模型：植入一条已知方向，用来验干预装置本身。

## 为什么需要它

坏装置跑出来的**阴性**结果和有意义的阴性结果长得一模一样。
在拿 Qwen 的空结果去论证「这个方向干预不了」之前，
必须先证明这套注入代码在**答案已知**的情况下能拿到正确答案。

## 结构必须和 Qwen 对齐

Qwen 里 `embed_tokens` 独立于 decoder layers，且**每个 decoder layer
模块的输出就是更新后的残差流**。所以 `attach()` 挂在 layer 模块输出上
= 注入进残差流。这里刻意用同一个形状：

    h_in = emb(ids)                  # embedding，不算 layer
    layers[0] = Block(mlp0)          # 输出 = 残差流 h0
    layers[1] = Block(mlp1)          # 输出 = 残差流 h1
    logits = head(h1)

如果合成模型自己搞一套「层内残差」或者把 embedding 算成 layer，
harness 挂的位点和 Qwen 挂的位点就不是同一个地方，自证就白做了。

## 植入的通路（真值可解析）

    emb :  h_in[COORD] = x[:,0]
    Block(mlp0) 的 COORD 行全 0  ⇒  h0[COORD] = x[:,0]
    Block(mlp1) 的 COORD 行 = (GAIN−1)·e_COORD  ⇒  h1[COORD] = GAIN·x[:,0]
    head: logit[K] 的 COORD 列 = 1.0

于是 **gain0（第 0 层残差 → logit）= GAIN，gain1（第 1 层 → logit）= 1.0**，
比值恰好 GAIN = 2。这不是巧合，是刻意留的检查点：
它让「harness 是不是真的按层号挂对了地方」变成可解析验证的事。

⚠ 增益必须按**对所有 token 求和**的口径取（见 selftest.py）。
注入器给每个 token 都加 δ，所以 ∂mean(logit)/∂δ = Σ_t ∂mean(logit)/∂h[t]；
取单个 token 的导数会差一个 T 倍。
"""
import torch
import torch.nn as nn

D = 24
N_VOCAB = 40
CONCEPT_LOGIT = 7          # 被植入驱动的那个输出位
CONCEPT_COORD = 0          # 被植入的那个隐藏坐标
GAIN = 2.0                 # 第 0 层残差 → logit 的通路增益


class Block(nn.Module):
    """`x + inner(x)`：模块的**输出**就是残差流，与 Qwen decoder layer 同形。"""

    def __init__(self, inner: nn.Module):
        super().__init__()
        self.inner = inner

    def forward(self, x):
        return x + self.inner(x)


class Synth(nn.Module):
    def __init__(self, seed: int = 7):
        super().__init__()
        g = torch.Generator().manual_seed(seed)
        self.emb = nn.Linear(N_VOCAB, D)
        self.mlp0 = nn.Linear(D, D)
        self.mlp1 = nn.Linear(D, D)
        self.head = nn.Linear(D, N_VOCAB)
        for m in (self.emb, self.mlp0, self.mlp1, self.head):
            with torch.no_grad():
                m.weight.copy_(torch.randn(m.weight.shape, generator=g) * 0.15)
                m.bias.zero_()
        self.layers = nn.ModuleList([Block(self.mlp0), Block(self.mlp1)])
        self._plant()

    def _plant(self):
        with torch.no_grad():
            self.emb.weight[CONCEPT_COORD].fill_(0.0)
            self.emb.weight[CONCEPT_COORD, 0] = 1.0
            # mlp0 的 COORD 行全 0 ⇒ h0[COORD] = h_in[COORD]
            self.mlp0.weight[CONCEPT_COORD].fill_(0.0)
            # mlp1 在 COORD 上乘 (GAIN−1) ⇒ h1[COORD] = GAIN · h0[COORD]
            self.mlp1.weight[CONCEPT_COORD].fill_(0.0)
            self.mlp1.weight[CONCEPT_COORD, CONCEPT_COORD] = GAIN - 1.0
            self.head.weight[CONCEPT_LOGIT].fill_(0.0)
            self.head.weight[CONCEPT_LOGIT, CONCEPT_COORD] = 1.0
            for m in (self.emb, self.mlp0, self.mlp1, self.head):
                m.bias.zero_()

    def forward(self, ids):
        """注意：**没有 injector 参数**。注入只允许走 `attach()` 的 hook ——
        一旦这里也能注入，`forward_fn` 里挂 hook + 传参就会打两遍，
        而装置照样「看起来正常」。"""
        h = self.emb(ids)
        for blk in self.layers:
            h = blk(h)
        return self.head(h), h

    @property
    def planted_direction(self):
        v = torch.zeros(D)
        v[CONCEPT_COORD] = 1.0
        return v


def make_batch(n_tokens=64, seed=3):
    """前 1/4 段「概念」为 1，其余段**严格为 0**。

    ⚠ 必须是严格 0，不能是 `rand*0.3`。因为读出自证要的是
    `corr(h·ê₀, y) = 1` 这个**精确**真值：off 段若带随机残值，
    特征就是分级的、而标签 y 是硬阈值，rho 只能到 0.9788 ——
    那时候红灯指向的是**夹具把真值做脏了**，不是装置不对。
    """
    g = torch.Generator().manual_seed(seed)
    x = torch.rand(n_tokens, N_VOCAB, generator=g) * 0.3
    x[:, 0] = 0.0
    x[:n_tokens // 4, 0] = 1.0        # 前 1/4 段「概念」为正
    return x                            # [T, N_VOCAB] 的软 one-hot
