"""Tests for the read-out in `analyse_divergence_logits`.

The one that matters
--------------------
``post_norm`` exists because ``hidden_states[n_layers]`` is already past
``model.norm`` — transformers' capture appends the norm's output as the last
tuple entry. Applying the norm a second time is not a rounding difference; on
the real model it moves a logit by 16-19, which is enough to point a
"why this token" explanation at the wrong token while every plot still looks
correct.

A test that only checks the closed form of each variant would pass whether or
not anyone threads the flag through, so the tests below are built around
**discrimination**: each one compares the two variants on the same input and
requires them to differ. If a future change drops the flag, they go red instead
of quietly reading out a different function.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyse_divergence_logits import (  # noqa: E402
    RMS_EPS, decompose, flip_threshold, lens, lens_rows)

FAILURES: list = []
D = 16
V = 9


def check(ok: bool, name: str) -> None:
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}")
    if not ok:
        FAILURES.append(name)


def fixture(seed: int = 7):
    g = torch.Generator().manual_seed(seed)
    W = torch.randn(V, D, generator=g)
    norm_w = torch.rand(D, generator=g) + 0.5
    h = torch.randn(D, generator=g) * 3.0
    return W, norm_w, h


def apply_norm(h: torch.Tensor, g: torch.Tensor) -> torch.Tensor:
    return g * h / torch.sqrt((h * h).mean() + RMS_EPS)


def test_post_norm_is_a_plain_dot_product():
    print("\n[1] post_norm 读出就是 W @ h（不再套 norm）")
    W, g, h = fixture()
    a = lens(h, g, W, True)
    b = W @ h
    check(torch.allclose(a, b, atol=1e-6), f"post_norm 读出 == W@h  (max {float((a-b).abs().max()):.2e})")

    c = lens(h, g, W, False)
    d = W @ apply_norm(h, g)
    check(torch.allclose(c, d, atol=1e-6), f"pre_norm 读出 == W@norm(h)  (max {float((c-d).abs().max()):.2e})")

    # Discrimination: the two variants must NOT agree, or the flag means
    # nothing and this whole test would be satisfied by a constant.
    check(not torch.allclose(a, c, atol=1e-3),
          f"两种读出确实不同（否则 flag 无意义），max|差|={float((a-c).abs().max()):.3f}")

    # And the wrong one must be wrong by a lot, not by a hair: a 0.001
    # difference would not be able to move an argmax, so a test that only
    # checked "they differ" would be too weak to have caught the real bug.
    check(float((a - c).abs().max()) > 1.0,
          f"做错的那版差得足够大（>{1.0:.0f}），不是四舍五入（{float((a-c).abs().max()):.2f}）")


def test_rows_match_full_vocabulary():
    print("\n[2] 子集读出与全词表读出在对应行上一致")
    W, g, h = fixture()
    idx = torch.tensor([0, 3, 8])
    for pn in (False, True):
        full = lens(h, g, W, pn)
        sub = lens_rows(h, g, W[idx], pn)
        check(torch.allclose(full[idx], sub, atol=1e-6),
              f"post_norm={pn} 时候选集与全表一致  (max {float((full[idx]-sub).abs().max()):.2e})")


def test_decompose_sums_to_the_logit_difference():
    print("\n[3] 逐维贡献求和 == 直接算的 logit 差（两种 post_norm 都验）")
    W, g, h = fixture()
    delta = torch.randn(D, generator=torch.Generator().manual_seed(11)) * 0.4
    hp = h + delta
    for pn in (False, True):
        for v in (0, 5, V - 1):
            u = W[v]
            direct = float(lens_rows(hp, g, u.view(1, -1), pn)[0]
                           - lens_rows(h, g, u.view(1, -1), pn)[0])
            parts = decompose(h, hp, g, u, pn)
            check(abs(float(parts.sum()) - direct) < 1e-4,
                  f"post_norm={pn} token {v}: sum={float(parts.sum()):+.6f} "
                  f"direct={direct:+.6f}")

    # The decomposition must be *sensitive*: on a post-norm layer the
    # contributions are u*(h'-h), and a wrong sign convention would still sum
    # to something. Pin the sign. Exact equality is not available here and
    # asking for it would be asking for float32 to cancel `h + d - h` without
    # loss, which it does not do; the tolerance is the cancellation error of a
    # single subtraction, not a fudge factor.
    u = W[2]
    parts = decompose(h, hp, g, u, True)
    scale = float((u * delta).abs().max())
    check(torch.allclose(parts, u * delta, rtol=1e-3, atol=1e-6 * max(scale, 1.0)),
          f"post_norm 的逐维贡献 == u * (h' - h)  (max|差|={float((parts-u*delta).abs().max()):.2e})")
    # And it must be a different function from the pre-norm one, or the flag
    # could be dropped from the call site without this file noticing.
    pre = decompose(h, hp, g, u, False)
    check(not torch.allclose(parts, pre, atol=1e-3),
          f"post_norm 与 pre_norm 的逐维贡献不同（max|差|={float((parts-pre).abs().max()):.2f}）")


def test_flip_threshold_finds_a_known_crossing():
    print("\n[4] flip_threshold 在已知答案上正确")
    W, g, h = fixture()
    rows = torch.stack([W[0], W[1]])
    d = W[0] - W[1]
    # At alpha=0 the gap is logit0 - logit1; at alpha=1 the gap is d·d > 0, so
    # the crossover is strictly inside (0, 1].
    th = flip_threshold(h, d, g, W, 0, 1, False)
    check(th is not None, f"找到了交叉点 (got {th})")
    if th is not None:
        check(0.0 < th <= 1.0, f"交叉点落在 (0, 1]  (got {th})")
        lg_a = lens_rows(h + th * d, g, rows, False)
        lg_b = lens_rows(h + max(0.0, th - 0.02) * d, g, rows, False)
        check(float(lg_a[0]) > float(lg_a[1]),
              f"α={th:.2f} 处 token 0 确实已经反超 (got {float(lg_a[0]):.3f} vs {float(lg_a[1]):.3f})")
        check(float(lg_b[0]) <= float(lg_b[1]),
              f"再小一点点时还没有反超 (got {float(lg_b[0]):.3f} vs {float(lg_b[1]):.3f})")

    # A direction that never crosses must report None rather than the sweep's
    # last value. Returning 2.0 here would be a number that reads like a
    # measurement and is actually the loop's exit.
    far = -(W[0] - W[1])
    check(flip_threshold(h, far, g, W, 0, 1, False) is None,
          "永远不反超的方向返回 None，而不是扫描区间的末值")


def main() -> int:
    test_post_norm_is_a_plain_dot_product()
    test_rows_match_full_vocabulary()
    test_decompose_sums_to_the_logit_difference()
    test_flip_threshold_finds_a_known_crossing()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED: {FAILURES}")
        return 1
    print("all read-out tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
