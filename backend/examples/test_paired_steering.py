"""Wiring tests for ``run_paired_steering``.

These run on CPU with a mock model. The point is the *glue* — the index
alignment between ``ids`` and ``hs``, the EOS truncation, and the arithmetic
inside ``analyze`` — none of which needs 1.7B parameters to be wrong.

The rule these obey: the test **calls** the functions under test. It never
re-implements a copy of the formula to compare against. A test that computes
its own ``‖steered − control‖`` and compares it to ``analyze``'s value is
testing whether the two copies agree, which is a different question from
whether either is right, and a bug placed at the call site survives it.

Run: ``python3 backend/examples/test_paired_steering.py``
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_paired_steering as P  # noqa: E402

FAILURES = []


def check(cond: bool, label: str) -> None:
    if cond:
        print(f"  ok    {label}")
    else:
        print(f"  FAIL  {label}")
        FAILURES.append(label)


# ---------------------------------------------------------------------------
# Mock model / tokenizer
# ---------------------------------------------------------------------------


class _Block:
    """Stands in for one decoder block, only as a hook registration target."""

    def parameters(self):
        return [torch.zeros(1)]

    def register_forward_pre_hook(self, hook):
        return SimpleNamespace(remove=lambda: None)

    def __call__(self, *a, **k):
        return a


class _MockModel:
    """Emits a deterministic stream and a hidden state that encodes *when*
    it was produced.

    ``hidden_states[L][0, -1, 0]`` is set to the 1-based count of the forward
    pass that produced it. So after truncation, ``hs[i][0] == i + 1`` and
    ``ids[i]`` is the token that pass predicted. If the off-by-one ever
    comes back — store one longer than the token list, or trimmed to the
    wrong end — this stops being true and the test goes red.
    """

    def __init__(self, n_layers=28, d=8, vocab=50, eos=None, script=None):
        self.model = SimpleNamespace(layers=[_Block() for _ in range(n_layers)])
        self.config = SimpleNamespace(num_hidden_layers=n_layers,
                                      hidden_size=d,
                                      max_position_embeddings=32768)
        self.device = "cpu"
        self._n, self._d, self._vocab = n_layers, d, vocab
        self._eos = eos
        # script: list of token ids to emit, one per forward, cycled.
        self._script = list(script) if script else [5, 5, 5, 5, 5]
        self._i = 0

    def __call__(self, input_ids=None, past_key_values=None, **kw):
        T = input_ids.shape[-1]
        self._i += 1
        hs = tuple(torch.full((1, T, self._d), float(self._i))
                   for _ in range(self._n + 1))
        logits = torch.zeros(1, T, self._vocab)
        logits[0, -1, self._script[self._i % len(self._script)]] = 1.0
        return SimpleNamespace(logits=logits, past_key_values=object(),
                               hidden_states=hs)


class _Enc(dict):
    """dict that pretends to be a BatchEncoding: ``.to(device)`` is a no-op."""

    def to(self, device):
        return self


class _MockTok:
    def __init__(self, eos=None):
        self.eos_token_id = eos

    def __call__(self, prompt, return_tensors=None):
        return _Enc(input_ids=torch.zeros(1, 3, dtype=torch.long))

    def decode(self, ids, skip_special_tokens=True):
        return " ".join(str(i) for i in ids)


def _mock_stream(tokens, n_layers=28, d=8):
    """Prebuild the dicts ``run_one`` returns, without the decode loop."""
    ids = list(tokens)
    hs = {L: np.stack([np.full(d, i + 1, dtype=np.float32) for i in range(len(ids))])
          .astype(np.float16) for L in (0, 1, 2)}
    return {"text": " ".join(map(str, ids)), "ids": ids,
            "n_steps": len(ids), "hs": hs, "closed_think": False}


# ---------------------------------------------------------------------------
# 1. ids / hs alignment through the real decode loop
# ---------------------------------------------------------------------------
def test_alignment():
    print("\n[1] run_one: hs[i] predicts ids[i]")
    layers = [0, 1, 2]
    out = P.run_one(_MockModel(), _MockTok(), "p", budget=6, layers=layers,
                    steer_vec=None, layer=1, log_every=10**9)
    n = out["n_steps"]
    check(n == 6, f"n_steps == budget (got {n})")
    for L in layers:
        check(out["hs"][L].shape[0] == n,
              f"L{L}: len(hs) {out['hs'][L].shape[0]} == len(ids) {n}")
        # pass i+1 produced ids[i]; store index i holds that pass
        vals = [float(out["hs"][L][i][0]) for i in range(n)]
        check(vals == [float(i + 1) for i in range(n)],
              f"L{L}: hs[i] carries pass i+1  -> {vals[:3]}...")


def test_eos_truncation():
    print("\n[2] run_one: EOS truncates ids *and* hs together")
    m = _MockModel(eos=5, script=[5])
    out = P.run_one(m, _MockTok(eos=5), "p", budget=8, layers=[0, 1, 2],
                    steer_vec=None, layer=1, log_every=10**9)
    check(out["n_steps"] == 0, f"n_steps == 0 (got {out['n_steps']})")
    for L in (0, 1, 2):
        check(out["hs"][L].shape[0] == out["n_steps"],
              f"L{L}: truncated hs matches truncated ids "
              f"({out['hs'][L].shape[0]} vs {out['n_steps']})")


# ---------------------------------------------------------------------------
# 3-4. analyze arithmetic, against hand-computed cases
# ---------------------------------------------------------------------------
def test_analyze_identical():
    print("\n[3] analyze: identical arms -> zero shift, cosine 1")
    s = _mock_stream([5] * 10)
    a = P.analyze(s, s, [0, 1, 2], unit=None)
    check(a["n_common_prefix"] == 10, f"n_common_prefix == 10 ({a['n_common_prefix']})")
    check(a["diverged"] is False, "diverged is False")
    for L in (0, 1, 2):
        e = a["per_layer"][str(L)]
        check(max(e["abs_shift"]) == 0.0, f"L{L}: max abs_shift == 0")
        # fp32 norm and fp32 dot product sum in different orders, so a vector
        # compared with itself lands ~1e-7 off 1.0 rather than on it. Assert
        # the tolerance, not the identity.
        worst = max(abs(c - 1.0) for c in e["cosine"])
        check(worst < 1e-5,
              f"L{L}: all cosine == 1.0 within fp32 noise (worst {worst:.2e})")


def test_analyze_divergence():
    print("\n[4] analyze: divergence point and signed top dims")
    c = _mock_stream([5, 5, 5, 5, 5, 5])
    s = _mock_stream([5, 5, 9, 9, 9, 9])          # diverges at index 2
    a = P.analyze(c, s, [0], unit=None)
    check(a["n_common_prefix"] == 2, f"n_common_prefix == 2 ({a['n_common_prefix']})")
    check(a["diverged"] is True, "diverged is True")
    e = a["per_layer"]["0"]
    check(e["n_compared"] == 2, f"n_compared == 2 ({e['n_compared']})")
    check(len(e["cosine"]) == 2, f"cosine has 2 entries ({len(e['cosine'])})")

    # rel_shift must equal ‖Δ‖/‖h‖ computed by hand for step 0.
    # hs[i] = (i+1) everywhere, so h = 1, Δ = 0 at the identical prefix.
    check(abs(e["rel_shift"][0] - 0.0) < 1e-6,
          f"step 0 rel_shift == 0 ({e['rel_shift'][0]})")

    # Offset ONE coordinate by +1. hs rows are [i+1]*8, so at step 0:
    #   h = [1]*8,  ‖h‖ = sqrt(8)
    #   s = [2,1,1,1,1,1,1,1],  Δ = [1,0,...],  ‖Δ‖ = 1
    #   rel_shift = 1/sqrt(8)
    #   cosine    = h·s/(‖h‖‖s‖) = 9/(sqrt(8)*sqrt(11))
    # These are worked out by hand here rather than recomputed with numpy, so
    # the assertion and the implementation cannot drift together.
    c2 = _mock_stream([5] * 4)
    s2 = _mock_stream([5] * 4)
    s2["hs"][0] = c2["hs"][0].copy()
    s2["hs"][0][:, 0] = (s2["hs"][0][:, 0].astype(np.float32) + 1.0).astype(np.float16)
    a2 = P.analyze(c2, s2, [0], unit=None)
    e2 = a2["per_layer"]["0"]
    exp_abs = 1.0
    exp_rel = 1.0 / np.sqrt(8.0)
    exp_cos = 9.0 / (np.sqrt(8.0) * np.sqrt(11.0))
    check(abs(e2["abs_shift"][0] - exp_abs) < 1e-3,
          f"‖Δ‖ == {exp_abs} for a single-coordinate +1 "
          f"(got {e2['abs_shift'][0]:.4f})")
    check(abs(e2["rel_shift"][0] - exp_rel) < 1e-3,
          f"rel_shift == 1/sqrt(8) = {exp_rel:.4f} "
          f"(got {e2['rel_shift'][0]:.4f})")
    check(abs(e2["cosine"][0] - exp_cos) < 1e-3,
          f"cosine == 9/(sqrt8*sqrt11) = {exp_cos:.4f} "
          f"(got {e2['cosine'][0]:.4f})")

    # top_dims must keep the sign, not just the magnitude.
    dm = np.zeros(8, dtype=np.float32)
    dm[3] = -5.0
    dm[6] = +2.0
    td = P.top_dims(dm, k=2)
    got = {d["dim"]: d["delta"] for d in td}
    check(got.get(3) == -5.0, f"top_dims keeps the negative sign ({got})")
    check(got.get(6) == 2.0, f"top_dims keeps the positive dim ({got})")


def test_proj_fraction():
    print("\n[5] analyze: projection fraction separates steer-aligned from drift")
    d = 4
    u = np.zeros(d, dtype=np.float32)
    u[0] = 1.0

    def arm(offset):
        ids = [5] * 3
        hs = np.zeros((3, d), dtype=np.float32)
        hs[:, 0] = 2.0
        for i in range(3):
            hs[i, 0] += offset
        return {"text": "", "ids": ids, "n_steps": 3,
                "hs": {0: hs.astype(np.float16)}, "closed_think": False}

    along = P.analyze(arm(0.0), arm(1.0), [0], unit=u)
    off = P.analyze(arm(0.0), arm(0.0), [0], unit=u)
    off["per_layer"]["0"]["abs_shift"] = [0.0, 0.0, 0.0]
    # Purely along the steering direction -> fraction 1.0.
    check(abs(along["per_layer"]["0"]["proj_fraction"] - 1.0) < 1e-3,
          f"steer-aligned Δ -> proj_fraction 1.0 "
          f"(got {along['per_layer']['0']['proj_fraction']})")
    # Drift on an orthogonal coordinate -> fraction 0.0.
    c = arm(0.0)
    s = arm(0.0)
    s["hs"][0] = c["hs"][0].copy()
    s["hs"][0][:, 2] += 1.0
    orth = P.analyze(c, s, [0], unit=u)
    check(abs(orth["per_layer"]["0"]["proj_fraction"]) < 1e-3,
          f"orthogonal Δ -> proj_fraction 0.0 "
          f"(got {orth['per_layer']['0']['proj_fraction']})")


def main() -> int:
    test_alignment()
    test_eos_truncation()
    test_analyze_identical()
    test_analyze_divergence()
    test_proj_fraction()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED: {FAILURES}")
        return 1
    print("all wiring tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
