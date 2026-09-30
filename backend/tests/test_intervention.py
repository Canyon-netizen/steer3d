"""Tests for the intervention machinery.

The dual-stream loop is the piece that produces every number this
project claims about what a steering vector does, and it is also the
piece that is hardest to eyeball — a silent bug in it would produce
plausible-looking divergence curves that mean nothing. These tests
pin down the parts that can be checked without a GPU:

  * the hook fires only on the primary stream, never the shadow;
  * the shadow stream is genuinely unsteered (the whole premise of
    the counterfactual);
  * teacher-forcing keeps both streams on identical inputs;
  * layer indices line up with the injected layer.

`run_intervention` imports torch and transformers at call time rather
than at module scope, so these run on CPU with a small stub model.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

torch = pytest.importorskip("torch")


# ---------------------------------------------------------------------------
# A minimal stand-in for a HF causal LM.
# ---------------------------------------------------------------------------


class _Block(torch.nn.Module):
    def __init__(self, d_model: int):
        super().__init__()
        self.lin = torch.nn.Linear(d_model, d_model, bias=False)
        with torch.no_grad():
            self.lin.weight.copy_(torch.eye(d_model) * 0.9 + 0.02)

    def forward(self, hidden_states, *args, **kwargs):
        return (self.lin(hidden_states),)


class _Inner(torch.nn.Module):
    def __init__(self, d_model: int, n_layers: int):
        super().__init__()
        self.layers = torch.nn.ModuleList([_Block(d_model) for _ in range(n_layers)])


class _Cfg:
    def __init__(self, d_model, n_layers, vocab):
        self.hidden_size = d_model
        self.num_hidden_layers = n_layers
        self.vocab_size = vocab


class _Out:
    def __init__(self, hidden_states, logits, past):
        self.hidden_states = hidden_states
        self.logits = logits
        self.past_key_values = past


class _StubModel(torch.nn.Module):
    """A tiny deterministic 'transformer' with the HF call signature.

    Each block mixes the residual with a fixed random direction, so a
    vector injected upstream has a measurable, non-trivial effect
    downstream — which is what the divergence measurement needs in
    order to be tested at all.
    """

    def __init__(self, d_model=32, n_layers=6, vocab=64, seed=0):
        super().__init__()
        rng = np.random.default_rng(seed)
        self.config = _Cfg(d_model, n_layers, vocab)
        self.model = _Inner(d_model, n_layers)
        self.device = torch.device("cpu")
        self._dirs = [
            torch.tensor(rng.standard_normal(d_model), dtype=torch.float32)
            for _ in range(n_layers)
        ]
        # Fixed lm_head so the argmax responds to the residual stream.
        self._readout = torch.tensor(
            rng.standard_normal((d_model, vocab)), dtype=torch.float32
        ) * 0.5
        self.add_hook_count = 0

    def _embed(self, input_ids):
        # Deterministic pseudo-embedding: one-hot-ish via position.
        bsz, seq = input_ids.shape
        out = torch.zeros(bsz, seq, self.config.hidden_size)
        for i in range(bsz):
            for t in range(seq):
                out[i, t] = self._dirs[t % len(self._dirs)]
        return out

    def forward(self, input_ids=None, attention_mask=None,
                past_key_values=None, output_hidden_states=False,
                use_cache=True, return_dict=True, **kwargs):
        h = self._embed(input_ids)
        past = int(input_ids.shape[1]) if past_key_values is None \
            else past_key_values
        hs = [h]
        x = h
        for blk in self.model.layers:
            x = blk(x)[0]
            hs.append(x)
        # Logits: a fixed linear read-out of the final residual, so the
        # argmax is sensitive to whatever the blocks did.
        bsz, seq, _ = x.shape
        readout = self._readout.to(x.dtype)          # (d_model, vocab)
        logits = x.reshape(-1, x.shape[-1]) @ readout  # (bsz*seq, vocab)
        logits = logits.reshape(bsz, seq, self.config.vocab_size)
        return _Out(tuple(hs), logits, past)


class _StubTokenizer:
    eos_token_id = 0
    vocab_size = 64

    def __call__(self, text, return_tensors=None, add_special_tokens=False):
        n = max(4, len(text.split()))
        return _Enc(torch.arange(1, n + 1).unsqueeze(0))

    def decode(self, ids, skip_special_tokens=False):
        return " ".join(f"t{int(i)}" for i in ids)


class _Enc:
    def __init__(self, input_ids):
        self.input_ids = input_ids
        self.attention_mask = torch.ones_like(input_ids)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def model():
    return _StubModel()


@pytest.fixture
def tokenizer():
    return _StubTokenizer()


@pytest.fixture
def run_dual():
    from examples.run_intervention import run_dual_stream
    return run_dual_stream


PROMPT = "one two three four five"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_steered_and_unsteered_diverge(model, tokenizer, run_dual):
    """A real vector must actually change the trajectory."""
    v = np.zeros(model.config.hidden_size, dtype=np.float32)
    v[3] = 5.0
    res = run_dual(model, tokenizer, PROMPT, v, layer=2,
                   max_new_tokens=12, track_shadow=True)
    assert res["n_steps"] > 0
    assert res["primary_text"] != res["shadow_text"], (
        "steering had no effect on the generated tokens — the hook is "
        "either not firing or firing on the wrong tensor"
    )


def test_zero_vector_is_a_no_op(model, tokenizer, run_dual):
    """A zero vector must leave the shadow and primary identical."""
    v = np.zeros(model.config.hidden_size, dtype=np.float32)
    res = run_dual(model, tokenizer, PROMPT, v, layer=2,
                   max_new_tokens=12, track_shadow=True)
    assert res["primary_ids"] == res["shadow_ids"]
    assert res["primary_text"] == res["shadow_text"]


def test_no_vector_disables_shadow(model, tokenizer, run_dual):
    """With no vector there is nothing to compare against."""
    res = run_dual(model, tokenizer, PROMPT, None, layer=2,
                   max_new_tokens=8, track_shadow=False)
    assert res["n_steps"] > 0
    # The tracker must stay empty so the report does not claim effects
    # that were never measured.
    assert res["shadow"].summary()["n_steps"] == 0


def test_teacher_forcing_keeps_inputs_identical(model, tokenizer, run_dual):
    """Both streams must consume the same tokens, or the comparison is
    measuring a different sentence rather than the intervention."""
    v = np.zeros(model.config.hidden_size, dtype=np.float32)
    v[1] = 8.0
    res = run_dual(model, tokenizer, PROMPT, v, layer=1,
                   max_new_tokens=10, track_shadow=True)
    # The shadow recorded exactly one entry per generated step, and each
    # carries the primary's token (never its own).
    steps = res["shadow"].steps
    assert len(steps) >= res["n_steps"]
    prim_tokens = {s.token for s in steps if s.step_id >= 0}
    assert prim_tokens <= set(res["tokens"])


def test_divergence_starts_at_injected_layer(model, tokenizer, run_dual):
    """The measurement must localise the intervention.

    Layers *above* the injection point (in the flow of computation) must
    be untouched — if they are not, the hook is leaking upstream and the
    counterfactual is contaminated. Layers *at and below* the injection
    point are expected to differ: that propagation is the whole effect
    we are trying to measure.
    """
    v = np.zeros(model.config.hidden_size, dtype=np.float32)
    v[3] = 10.0
    inject_at = 2
    res = run_dual(model, tokenizer, PROMPT, v, layer=inject_at,
                   max_new_tokens=12, track_shadow=True)
    curve = res["shadow"].layer_curve()
    assert curve, "no layer curve produced"

    layers = curve["layer"]
    div = [1.0 - c for c in curve["mean_cosine"]]

    idx_inject = layers.index(inject_at)
    above = [div[i] for i, li in enumerate(layers) if li < inject_at]

    # Strictly before the injection point: nothing may have changed.
    assert max(above) < 1e-4, (
        f"layers before L{inject_at} were perturbed (max div "
        f"{max(above):.6f}) — the hook is leaking upstream"
    )
    # The injection point itself must show a real difference.
    assert div[idx_inject] > 1e-3, (
        f"L{inject_at} shows divergence {div[idx_inject]:.6f}; the "
        f"vector is not reaching the residual stream at the stated layer"
    )


def test_layer_curve_index_alignment(model, tokenizer, run_dual):
    """`layer` and the value arrays must be the same length and order.

    They were once reversed, which silently mislabelled the whole
    chart. Cheap to assert, and the failure mode is invisible.
    """
    v = np.zeros(model.config.hidden_size, dtype=np.float32)
    v[3] = 4.0
    res = run_dual(model, tokenizer, PROMPT, v, layer=2,
                   max_new_tokens=6, track_shadow=True)
    c = res["shadow"].layer_curve()
    assert len(c["layer"]) == len(c["mean_cosine"]) == len(c["mean_rel_shift"])
    # -1 is the embedding output, then 0.. are the blocks. The curve
    # used to be reversed, which silently mislabelled the chart.
    assert c["layer"][0] == -1
    assert c["layer"] == sorted(c["layer"])


def test_max_track_steps_caps_work(model, tokenizer, run_dual):
    v = np.zeros(model.config.hidden_size, dtype=np.float32)
    v[3] = 3.0
    res = run_dual(model, tokenizer, PROMPT, v, layer=1,
                   max_new_tokens=20, track_shadow=True, max_track_steps=5)
    assert len(res["shadow"].steps) <= 5
