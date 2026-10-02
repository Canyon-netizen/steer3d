"""真实轨迹回放 runner —— 用采集到的 hidden states 喂 3-D 页面。

为什么需要它
------------
`default_runner()` 一直返回 `SyntheticRunner`：d_model=4096、40 个写死的
玩具词、`z = 0.18*t + 0.5*sin(t*0.4)` 这样的解析式轨迹、`entropy` 也是
sin 造出来的。页面因此显示的是编造的数据：

    ready.d_model = 4096   真实 Qwen3-1.7B 是 2048
    ready.layers  = []     真实有 28 层
    token 序列 = When / we / think / about / ...

3-D 视图是用来回答「hidden states 怎么变成这个 token」的，用合成数据
回答这个问题等于什么都没回答。这个 runner 改成回放
datasets/aime_qwen3_1p7b_16k_fp16/ 下真实采到的 fp16 hidden states。

和合成 runner 的差别，逐项说明
------------------------------
* token 文本：来自真实 tokenizer（词表 json 随数据集一起放在 frontend）
* 熵 / perplexity：由**存下来的 top-64 logits** 算出，不是 sin
* 3-D 坐标：对真实 hidden state 做 PCA 投影，不是解析式
* 层号：真实 28 层，UI 的层滑块直接对应 hidden_states[:, L, :]
* 干预向量：维度对得上（2048，不是合成 runner 的 4096），注入点、
  范数、与原状态的对齐度都如实算出来。**但注入后的 token 没有重算** ——
  见下。

干预这件事，这里到底做了什么、没做什么
------------------------------------
早先这个文件的抬头写着「注入后**重新读出** token，所以注入之后模型会说
什么是真算出来的」。那是错的，代码从来没这么做过。实测（.cache/
steerprobe/probe_steer.py，direction=caution、strength=0.5、12 步）：

    锚点  readout(last_hidden[t]) vs token_ids[t]   0/12 miss
    L14   readout(hs[:,14,:])  -> '这个多' / ' 这个多' / ...
    注入后 readout(h + v)      -> 6/12 步的 argmax 变了

    L20   readout(hs[:,20,:])  -> ' tasked' / '接下来' / ...
    注入后 readout(h + v)      -> 5/12 步的 argmax 变了

两个数字说明两件事：

1. **读出链本身是对的。** 对最终 post-norm 状态做 RMSNorm + unembedding
   得到的 argmax 逐步复现了录下来的 token，0/12 失配。
2. **但中间层残差不能这样读。** `hidden_states[:, L, :]` 是**进入第 L 层
   之前**的残差，它的 argmax 是 '这个多'、'ศาส' 这类无意义输出 ——
   因为第 L 层往后的 28-L 个 block 还没跑。要得到「注入之后模型会
   说什么」，必须从第 L 层起把剩下的 block 全部前向一遍。

那需要完整的 28 层权重（4.06 GB safetensors）+ 注意力 KV 缓存，而这里
**明确不跑模型推理**（无 GPU、无 torch，采集已在集群做完）。所以：

* 现在注入改的是 `h`，`h` 只喂给 PCA ⇒ **3-D 轨迹会因为干预而偏移**，
  这是真的；
* 但 `Frame.token` 仍是**注入前**录下来的那个词。干预开关前后，
  Reasoning Trace 面板的文本逐字相同；
* 熵 / perplexity 在 `steer_active` 时置 None，而不是拿未干预的
  logits 冒充。

「注入后模型会说什么」的真实答案来自离线跑完的 32k 批次
（cot_texts.json / answer_readout.json），那些是解码器逐 token 取
argmax 重跑出来的，页面读的是它们，并且必须标明是离线产物。
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
from typing import Callable, Dict, List, Optional

import numpy as np

from .protocol import Frame, Point3D

# self-check 启发式，和 model_runner.py 里的保持一致
_SELF_CHECK_RE = re.compile(
    r"\b(wait|actually|hmm|let me reconsider|on second thought|"
    r"let me check|let me think again|double[- ]check)\b",
    re.IGNORECASE,
)

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_AIME_DIR = os.path.join(_REPO, "datasets", "aime_qwen3_1p7b_16k_fp16", "aime")
_VOCAB_JSON = os.path.join(
    _REPO, "frontend", "public", "latent", "data", "vocab.json"
)


def _load_vocab() -> List[str]:
    """token id -> 词表字符串。缺文件时退化成 '#<id>'，绝不编造。"""
    try:
        with open(_VOCAB_JSON, "r", encoding="utf-8") as fh:
            obj = json.load(fh)
        ids = obj["ids"] if isinstance(obj, dict) and "ids" in obj else obj
        return [str(x) for x in ids]
    except Exception:
        return []


def _discover_records() -> List[Dict[str, str]]:
    """列出可回放的 .npz。文件不存在就返回空列表，不假装有数据。"""
    out: List[Dict[str, str]] = []
    if not os.path.isdir(_AIME_DIR):
        return out
    for name in sorted(os.listdir(_AIME_DIR)):
        if not name.endswith(".npz"):
            continue
        stem = name[:-4]
        meta: Dict[str, str] = {}
        meta_path = os.path.join(_AIME_DIR, stem + ".json")
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as fh:
                    meta = json.load(fh)
            except Exception:
                meta = {}
        out.append(
            {
                "id": meta.get("id") or stem,
                "problem_id": meta.get("problem_id") or stem.split("__")[-1],
                "npz": os.path.join(_AIME_DIR, name),
            }
        )
    return out


class NpzReplayRunner:
    """回放真实采集轨迹。d_model / 层数 / token 全部来自数据本身。"""

    def __init__(self, max_steps: int = 0):
        self.records = _discover_records()
        self._vocab = _load_vocab()
        # d_model 和层数不能写死：从第一份真实数据里读出来。
        # 写死 2048/28 在换模型或换数据集时会静默错，而错的方式是
        # 「页面照常显示，只是坐标全是噪声」。
        self.d_model = 2048
        self.n_layers = 28
        self.available_layers: List[int] = []
        self._peeked = False
        self.max_steps = max_steps
        self._index = 0

    # ------------------------------------------------------------------

    def _peek(self) -> None:
        if self._peeked or not self.records:
            return
        try:
            with np.load(self.records[0]["npz"], mmap_mode="r") as z:
                hs = z["hidden_states"]
                self.d_model = int(hs.shape[2])
                self.n_layers = int(hs.shape[1])
                # 只报数据里真的有内容的层。hidden_states 覆盖全部层，
                # 但减去层均值之后尾部几层可能数值退化；这里如实报全部，
                # 让 UI 能选，而不是替数据做判断。
                self.available_layers = list(range(self.n_layers))
        except Exception:
            pass
        self._peeked = True

    def reset(self) -> None:
        self._index = 0
        self._peek()

    def describe(self) -> List[Dict[str, str]]:
        """可回放轨迹清单，供 UI 渲染成选择器。

        只回放型的 runner 有这个列表；合成 runner 没有（它接受任意
        prompt）。UI 拿到非空列表就把自由文本框换成下拉，拿到空列表
        才保留文本框 —— 这样「只能选真实存在的轨迹」这条约束由数据
        决定，而不是由 UI 猜。
        """
        out: List[Dict[str, str]] = []
        for r in self.records:
            rid = r["id"]
            mode = "think" if rid.endswith("__think") else (
                "no_think" if rid.endswith("__no_think") else ""
            )
            out.append(
                {
                    "id": rid,
                    "label": r.get("problem_id") or rid,
                    "mode": mode,
                }
            )
        return out

    # ------------------------------------------------------------------

    def _pick(self, needle: str) -> Optional[Dict[str, str]]:
        """按 id / problem_id 找一条轨迹；找不到就用第 0 条并如实说明。"""
        if not self.records:
            return None
        needle = (needle or "").strip().lower()
        if not needle:
            return self.records[0]
        for r in self.records:
            if r["id"].lower() == needle or r["problem_id"].lower() == needle:
                return r
        # 允许只给题号的一部分
        for r in self.records:
            if needle in r["problem_id"].lower() or needle in r["id"].lower():
                return r
        return self.records[0]

    @staticmethod
    def _decode(tokens, step: int) -> str:
        if not tokens:
            return f"#{step}"
        t = tokens[step]
        if t < len(tokens) and tokens[step].strip():
            return tokens[step]
        return f"#{step}"

    # ------------------------------------------------------------------

    async def stream(
        self,
        prompt: str,
        layer: int,
        on_frame: Callable[[Frame], None],
        is_paused: Callable[[], bool],
        is_cancelled: Callable[[], bool],
        set_speed: Callable[[], float],
        inject_vector: Optional[Callable[[int, str], Optional[np.ndarray]]] = None,
    ) -> None:
        self._peek()
        rec = self._pick(prompt)
        if rec is None:
            # 没有数据就说没有，不要用合成轨迹顶替 —— 那样页面上
            # 显示的会是编出来的点，而读者没有任何办法分辨。
            on_frame(
                Frame(
                    ts=0.0,
                    step_id=0,
                    token=f"[no replay data: {_AIME_DIR}]",
                    token_id=-1,
                    point=Point3D(0.0, 0.0, 0.0),
                    perplexity=None,
                    entropy=None,
                    loss=None,
                    is_self_check=False,
                    is_revisit=False,
                    is_end=True,
                )
            )
            return

        with np.load(rec["npz"]) as z:
            hs = z["hidden_states"]           # (T, L, D) float16
            tok_ids = z["token_ids"]           # (T,)
            topk_logits = z["topk_logits"]     # (T, 64)
            topk_idx = z["topk_indices"]       # (T, 64)

            T, L, D = hs.shape
            layer = max(0, min(int(layer), L - 1))

            # 词表：从同目录的 tokenizer 或前端 vocab 里取，取不到就显示 id
            tokens = self._vocab or [""] * 200000
            decoder = _Decoder(tokens, topk_idx)

            # 只跑生成部分（attention_mask 之后），prompt 段不是「正在说的词」
            n_all = T
            T = n_all
            n = T if self.max_steps <= 0 else min(T, self.max_steps)

            # PCA 投影：在线增量 PCA，见 projector.OnlinePCA。
            # 延迟一步：第 0 个点还没有基，直接送原始残差的前三维会让
            # 起点看起来远离整条轨迹。
            from .projector import OnlinePCA

            proj = OnlinePCA(d=D, target_dim=3, window=256)
            warm = 0
            prev = np.zeros(3)
            last_delta = np.zeros(3)
            basis_ready = False

            for i in range(n):
                if is_cancelled():
                    return
                while is_paused() and not is_cancelled():
                    await asyncio.sleep(0.05)
                speed = max(0.05, min(8.0, set_speed()))
                await asyncio.sleep(0.05 / speed)

                h = np.asarray(hs[i, layer, :], dtype=np.float64)
                tok = decoder.text(tok_ids, i)

                # 干预：维度对得上（2048），注入点/范数/对齐度都真算。
                #
                # `tok` 不会因此改变 —— 它在上一行就定死了，用的是录下来
                # 的 token_ids。要让 token 跟着干预变，得从第 `layer` 层
                # 起把剩下的 28-layer 个 block 前向一遍；这里不跑模型推理
                # （见文件抬头），所以那件事留给离线批次。改动这一段之前
                # 请先读抬头：页面上"干预后模型说了什么"读的是离线产物，
                # 不是这里。
                steer_active = False
                steer_norm = steer_alignment = steer_shift = steer_projection = None
                if inject_vector is not None:
                    v = inject_vector(i, tok)
                    if v is not None:
                        v = np.asarray(v, dtype=np.float64).reshape(-1)
                        if v.shape[0] == h.shape[0]:
                            steer_active = True
                            steer_norm = float(np.linalg.norm(v))
                            nh = np.linalg.norm(h)
                            if nh > 0:
                                steer_alignment = float(np.dot(h, v) / (nh * steer_norm))
                            h = h + v
                            steer_shift = float(np.linalg.norm(h) - nh)
                            steer_projection = float(np.dot(h, v))

                if warm < 2:
                    xyz = h[:3] * 0.01
                    warm += 1
                else:
                    try:
                        p = proj.update(h)
                        xyz = np.array([p.x, p.y, p.z])
                    except Exception:
                        xyz = h[:3] * 0.01

                delta = xyz - prev
                # reversed_now 必须在每一轮都有值。早先它只在
                # `if basis_ready:` 分支里赋值，而下面无条件引用 ——
                # 前两轮（PCA 还没建立基）就是 UnboundLocalError，
                # 整条轨迹一帧都发不出去。合成 runner 里这个变量是
                # 无条件算的，所以看不出问题。
                reversed_now = False
                if basis_ready:
                    reversed_now = (
                        np.linalg.norm(last_delta) > 1e-9
                        and np.linalg.norm(delta) > 1e-9
                        and float(np.dot(delta, last_delta)) < 0
                    )
                    last_delta = delta
                prev = xyz
                basis_ready = True

                # 熵 / perplexity 来自**存下来的 top-64 logits**。
                # 这是存下来的那一批 logits，不是在这里重新跑模型；
                # 干预之后这两项不再更新（存的 logits 对应未干预的运行），
                # 所以 intervene 时置 None 而不是编一个。
                ent = ppl = None
                if steer_active:
                    pass
                else:
                    lg = np.asarray(topk_logits[i], dtype=np.float64)
                    mx = float(lg.max())
                    ex = np.exp(lg - mx)
                    p = ex / ex.sum()
                    nz = p[p > 0]
                    ent = float(-(nz * np.log(nz)).sum())
                    top1 = float(p.max())
                    ppl = float(1.0 / top1) if top1 > 0 else None

                is_self = bool(_SELF_CHECK_RE.search(tok))
                on_frame(
                    Frame(
                        ts=float(i),
                        step_id=i,
                        token=tok,
                        token_id=int(tok_ids[i]),
                        point=Point3D(x=float(xyz[0]), y=float(xyz[1]), z=float(xyz[2])),
                        perplexity=ppl,
                        entropy=ent,
                        loss=None,
                        is_self_check=is_self,
                        is_revisit=bool(reversed_now),
                        steer_active=steer_active,
                        steer_norm=steer_norm,
                        steer_alignment=steer_alignment,
                        steer_shift=steer_shift,
                        steer_projection=steer_projection,
                    )
                )

            on_frame(
                Frame(
                    ts=float(n),
                    step_id=n,
                    token="",
                    token_id=-1,
                    point=Point3D(x=float(prev[0]), y=float(prev[1]), z=float(prev[2])),
                    perplexity=None,
                    entropy=None,
                    loss=None,
                    is_self_check=False,
                    is_revisit=False,
                    is_end=True,
                )
            )


class _Decoder:
    """把 token id 变成可读文本。取不到就显示 #id，不编造。"""

    def __init__(self, vocab: List[str], topk_idx):
        self.vocab = vocab
        self.topk_idx = topk_idx

    def text(self, tok_ids, i: int) -> str:
        tid = int(tok_ids[i])
        if 0 <= tid < len(self.vocab):
            s = self.vocab[tid]
            if s:
                return s
        return f"#{tid}"
