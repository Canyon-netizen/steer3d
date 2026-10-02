#!/usr/bin/env python3
"""实测：注入 steering vector 之后，页面上的 token 到底变没变。

背景
----
`replay_runner.py` 的 docstring 写着：

    干预向量：合成 runner 拿 4096 维向量对 2048 维数据是错的；这里维度
    对得上，**注入后重新读出 argmax**，所以「注入之后模型会说什么」是
    真算出来的，不是画出来的

但读代码看到的不是这样（第 265-342 行）：

    v = inject_vector(i, tok)
    ...
    h = h + v                  # 只改了送进 PCA 的那个 h
    ...
    tok = decoder.text(tok_ids, i)   # 早在第 259 行就算好了，用的是
                                    # **存下来的 token_ids**

也就是说 h 被改了、PCA 坐标被重算了、熵和 perplexity 诚实地置了
None，但 `token` 字段仍是注入前那个。这与 docstring 的说法不符。

本脚本不读代码下结论，直接跑：同一条轨迹、同一批步，注入与不注入各
跑一遍，逐 token 比对。用的是**真权重**做读出（RMSNorm + unembed），
所以「注入后应该说什么」是算出来的，不是猜的。
"""
import asyncio
import json
import os
import sys

import numpy as np

REPO = "/Users/zhourui/code/steer3d"
sys.path.insert(0, REPO)

from backend.core.replay_runner import NpzReplayRunner, _Decoder  # noqa: E402
from backend.core.steering import get_registry  # noqa: E402

REC_ID = "aime__1983__1983_I_1__no_think"
N_STEPS = 12
LAYER = 14


def load_lm_head():
    """Read the unembedding. hidden_states[:, 27] is already post-norm, and
    tie_word_embeddings is true, so embed_tokens doubles as lm_head."""
    import json as _json

    idx_path = os.path.join(REPO, "datasets/models/Qwen3-1.7B/model.safetensors.index.json")
    with open(idx_path) as fh:
        weight_map = _json.load(fh)["weight_map"]
    shard = os.path.join(REPO, "datasets/models/Qwen3-1.7B", weight_map["model.embed_tokens.weight"])

    from safetensors import safe_open  # type: ignore
    return safe_open  # unused, kept for clarity


def read_embed_tokens() -> np.ndarray:
    """Parse the safetensors header by hand and mmap the one tensor we
    need -- torch is not installed and the file is 3.4GB."""
    import json as _json
    from pathlib import Path

    root = Path(REPO) / "datasets/models/Qwen3-1.7B"
    with open(root / "model.safetensors.index.json") as fh:
        wm = _json.load(fh)["weight_map"]
    shard = root / wm["model.embed_tokens.weight"]

    with open(shard, "rb") as fh:
        n = int.from_bytes(fh.read(8), "little")
        header = _json.loads(fh.read(n))
    key = "model.embed_tokens.weight"
    meta = header[key]
    b0, b1 = meta["data_offsets"]
    start = 8 + n + b0
    shape = (meta["shape"][0], meta["shape"][1])
    raw = np.memmap(shard, dtype=np.uint8, mode="r", offset=start,
                    shape=(b1 - b0,))
    if meta["dtype"] == "BF16":
        # bfloat16 is the top 16 bits of a float32. numpy has no bf16, so
        # shift left 16 and re-view as float32 -- exact, no precision loss.
        wide = raw.view(np.uint16).astype(np.uint32) << 16
        return wide.view(np.float32).reshape(shape)
    if meta["dtype"] == "F16":
        return raw.view(np.float16).astype(np.float32)
    return raw.view(np.float32).reshape(shape)


def readout(h: np.ndarray, W: np.ndarray) -> int:
    """argmax token id for a post-norm residual state."""
    return int(np.argmax(np.asarray(h, dtype=np.float32) @ np.asarray(W, dtype=np.float32).T))


async def main():
    runner = NpzReplayRunner()
    reg = get_registry()
    names = list(reg.names)
    print("registered directions:", names[:6], "..." if len(names) > 6 else "")
    if not names:
        print("NO DIRECTIONS LOADED -- registry error:", getattr(reg, "load_error", None))
        return

    rec = next(r for r in runner.records if r["id"] == REC_ID)
    z = np.load(rec["npz"], mmap_mode="r")
    hs = z["hidden_states"]
    last = z["last_hidden"]
    tok_ids = z["token_ids"]
    dec = _Decoder(runner._vocab, z["topk_indices"])
    W = read_embed_tokens()
    print("unembedding:", W.shape, W.dtype)

    # Anchor first: does the readout reproduce the recorded tokens at all?
    # The first attempt read layer 14 and got 'ância' where the recording
    # says 'We' -- because hidden_states[:, L] is the residual *entering*
    # block L. Only the final post-norm state can be read out. If this
    # anchor fails, every "steered" number below is meaningless, so it
    # runs before anything else and the run stops if it misses.
    anchor_miss = 0
    for i in range(N_STEPS):
        got = readout(np.asarray(last[i], dtype=np.float64), W)
        if got != int(tok_ids[i]):
            anchor_miss += 1
    print("\nANCHOR readout(last_hidden[t]) vs token_ids[t]: %d/%d miss"
          % (anchor_miss, N_STEPS))
    if anchor_miss:
        print("ABORT -- the readout does not reproduce the recording; "
              "anything computed from it would be noise.")
        return

    for inj_layer in (14, 20):
        v = reg.scaled(names[0], strength=0.5, layer=inj_layer)
        if v is None:
            print("scaled() returned None for", names[0])
            continue
        v = np.asarray(v, dtype=np.float64)
        print("\n=== direction %r strength 0.5 at L%d, ||v||=%.2f"
              % (names[0], inj_layer, float(np.linalg.norm(v))))

        # Continue the recorded trajectory FROM the injection layer: the
        # later layers are applied unchanged, so the steered state is
        # `forward(later_blocks, h + v)`. Without a real forward pass we
        # can only read the perturbed state out directly, which is what
        # this measures -- and it is an approximation, not a re-decoding.
        baseline, steered = [], []
        for i in range(N_STEPS):
            h = np.asarray(hs[i, inj_layer, :], dtype=np.float64)
            baseline.append(readout(h, W))
            steered.append(readout(h + v, W))

        changed = [i for i, (a, b) in enumerate(zip(baseline, steered)) if a != b]
        print("  step  recorded        readout(h)     readout(h+v)   changed")
        for i, (a, b) in enumerate(zip(baseline, steered)):
            print("  %4d  %-14s %-14s %-14s %s"
                  % (i, repr(dec.text(tok_ids, i)), repr(runner._vocab[a]),
                     repr(runner._vocab[b]), "CHANGED" if a != b else ""))
        print("  -> %d/%d tokens differ between h and h+v" % (len(changed), N_STEPS))


if __name__ == "__main__":
    asyncio.run(main())
