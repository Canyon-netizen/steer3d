"""Small-model causal oracles and strict trajectory joins, without model weights."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
from core.vector_explanation import explain_observations, explain_response, unit_direction
from explain_vector import load_records, main, recorded_prefix


def record(tid="a", problem="p", sign=1):
    t = np.arange(8, dtype=float)
    return {"trajectory_id": tid, "problem_id": problem,
            "hidden": np.column_stack([sign * (t - 3.5), np.ones(8)]),
            "observables": {"position": t, "constant": np.ones(8)},
            "texts": [str(int(v)) for v in t]}


def test_problem_weighting_constants_and_conservative_null():
    # Two opposite traces of p average to zero, q contributes +1: mean = .5.
    result = explain_observations([record("a", "p"), record("b", "p", -1), record("c", "q")],
                                  np.array([1, 0]), n_random=15, seed=4)
    row = result["associations"]["position"]
    assert row["rho_cosine"] == pytest.approx(0.5)
    assert row["n_problems"] == 2 and row["n_variable_trajectories"] == 3
    assert row["random_max_stat_p"] >= 1 / 16
    assert result["associations"]["constant"]["status"] == "unmeasured"
    assert result["evidence_status"] == "exploratory_possible_extraction_overlap"
    json.dumps(result, allow_nan=False)


def test_direction_sign_and_declared_independence():
    a = explain_observations([record()], np.array([1, 0]), n_random=8, evaluation_split="independent")
    b = explain_observations([record()], np.array([-1, 0]), n_random=8, evaluation_split="independent")
    assert a["associations"]["position"]["rho_cosine"] == -b["associations"]["position"]["rho_cosine"]
    assert a["associations"]["position"]["problem_bootstrap_ci95"] is None
    assert a["evidence_status"] == "association_only"
    assert a["contexts"]["positive"][0]["step"] == 7


def test_lag_does_not_wrap_end_of_trajectory():
    r = record()
    r["observables"]["position"] = np.array([np.nan, 0, 1, 2, 3, 4, 5, 6])
    out = explain_observations([r], np.array([1, 0]), lag=1, n_random=8)
    assert out["associations"]["position"]["rho_cosine"] == pytest.approx(1)
    empty = explain_observations([r], np.array([1, 0]), lag=8, n_random=8)
    assert empty["associations"]["position"]["status"] == "unmeasured"


def test_constant_raw_projection_can_have_variable_cosine_without_nan_export():
    r = record()
    r["hidden"] = np.column_stack([np.ones(8), np.arange(1, 9)])
    out = explain_observations([r], np.array([1., 0.]), n_random=8)
    row = out["associations"]["position"]
    assert row["rho_cosine"] == pytest.approx(-1)
    assert row["rho_raw_projection"] is None and row["n_raw_projection_problems"] == 0
    json.dumps(out, allow_nan=False)


@pytest.mark.parametrize("v", [np.zeros(2), np.array([np.nan, 1]), np.ones((1, 2))])
def test_invalid_vectors(v):
    with pytest.raises(ValueError):
        unit_direction(v)


def write_pair(tmp_path, mismatch=False):
    r = record()
    tokens = [{"token_id": i, "token": str(i), "entropy": float(i),
               "top1_prob": .5, "is_in_think_block": True} for i in range(8)]
    side = {"trajectory_id": "trace", "dataset": "toy", "split": "test", "problem_id": "p",
            "n_prompt_tokens": 100, "n_generated_tokens": 8, "tokens": tokens,
            "config": {"model": "toy"}}
    (tmp_path / "trace.json").write_text(json.dumps(side))
    np.savez(tmp_path / "trace.npz", hidden_states=r["hidden"][:, None, :],
             token_ids=np.arange(8) + int(mismatch), attention_mask=np.ones(8))


def test_loader_never_removes_prompt_count_from_generated_rows(tmp_path):
    write_pair(tmp_path)
    records, model = load_records(tmp_path, 0, 2)
    assert model == "toy" and records[0]["hidden"].shape == (8, 2)
    write_pair(tmp_path, mismatch=True)
    with pytest.raises(ValueError, match="alignment"):
        load_records(tmp_path, 0, 2)


def test_observe_cli_exports_parseable_report(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    write_pair(data)
    vec, out = tmp_path / "v.npy", tmp_path / "report.json"
    np.save(vec, np.array([1., 0.]))
    assert main(["observe", "--vector", str(vec), "--data-root", str(data),
                 "--hidden-index", "0", "--random-directions", "8", "--out", str(out)]) == 0
    report = json.loads(out.read_text())
    assert report["schema"] == "steer3d.vector_explanation/1"
    assert len(report["vector"]["sha256"]) == 64
    assert report["n_tokens"] == 8


def test_recorded_prefix_excludes_token_being_predicted(tmp_path):
    write_pair(tmp_path)
    p = tmp_path / "trace.npz"
    with np.load(p) as z:
        arrays = {k: z[k] for k in z.files}
    np.savez(p, **arrays, prompt_token_ids=np.array([10, 11]))
    ids, meta = recorded_prefix(p, 3)
    assert ids.tolist() == [10, 11, 0, 1, 2]
    assert meta["stored_next_token_id"] == 3
    with pytest.raises(ValueError, match="step"):
        recorded_prefix(p, 8)


def toy_model():
    torch = pytest.importorskip("torch")

    class Model(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.config = SimpleNamespace(hidden_size=2, vocab_size=3)
            self.model = torch.nn.Module()
            first = torch.nn.Linear(2, 2, bias=False)
            second = torch.nn.Linear(2, 2, bias=False)
            self.model.layers = torch.nn.ModuleList([first, second])
            self.model.norm = torch.nn.Identity()
            self.lm_head = torch.nn.Linear(2, 3, bias=False)
            with torch.no_grad():
                first.weight.copy_(torch.eye(2))
                second.weight.copy_(-2 * torch.eye(2))
                self.lm_head.weight.copy_(torch.tensor([[1., 0.], [0., 1.], [0., 0.]]))
            self.prefixes = []
            self.nondeterministic = False

        def forward(self, input_ids, use_cache, return_dict):
            assert use_cache is False
            self.prefixes.append(input_ids.clone())
            h = torch.tensor([.5, 1.]).expand(1, input_ids.shape[1], 2).clone()
            for block in self.model.layers:
                h = block(h)
            logits = self.lm_head(self.model.norm(h))
            if self.nondeterministic:
                logits = logits + len(self.prefixes)
            return SimpleNamespace(logits=logits)
    return Model()


def test_downstream_flip_actual_probability_and_linearity():
    torch = pytest.importorskip("torch")
    model = toy_model()
    ids = torch.tensor([[1, 2, 0]])
    report = explain_response(model, {"input_ids": ids}, np.array([1., 0.]), 0,
                              strengths=[-.01, .01], n_random=4, targets={"token0": [0]}, top_k=3)
    minus, plus = report["arms"]
    # Direct unembedding says +v favors token0; the actual downstream -2I reverses it.
    assert plus["target_probability_delta"]["token0"] < 0 < minus["target_probability_delta"]["token0"]
    assert plus["layers"][0]["delta_cosine_with_vector"] == pytest.approx(1)
    assert plus["layers"][1]["delta_cosine_with_vector"] == pytest.approx(-1)
    assert plus["linear_prediction_relative_error"] < .01
    assert report["finite_difference_relative_disagreement_at_half_epsilon"] < .001
    assert all(torch.equal(ids, p) for p in model.prefixes)
    assert report["zero_control_max_state_error"] == report["zero_control_max_logit_error"] == 0
    assert report["baseline_site_norm"] == pytest.approx(np.sqrt(1.25))
    assert all(t["delta_log_probability"] > 0 for t in plus["promoted_tokens"])
    assert all(t["delta_log_probability"] < 0 for t in plus["suppressed_tokens"])
    assert model.training
    assert all(not b._forward_hooks and not b._forward_pre_hooks for b in model.model.layers)
    json.dumps(report, allow_nan=False)


def test_upstream_does_not_move_and_target_ids_are_validated():
    torch = pytest.importorskip("torch")
    model = toy_model()
    inp = {"input_ids": torch.tensor([[0, 1]])}
    report = explain_response(model, inp, np.array([1., 0.]), 1, strengths=[.01], n_random=2)
    assert report["arms"][0]["layers"][0]["relative_shift"] == 0
    with pytest.raises(ValueError, match="target token"):
        explain_response(model, inp, np.array([1., 0.]), 1, targets={"bad": [3]}, n_random=2)
    with pytest.raises(ValueError, match="KV cache"):
        explain_response(model, {**inp, "past_key_values": object()}, np.array([1., 0.]), 1)


def test_hooks_restore_when_zero_control_fails():
    torch = pytest.importorskip("torch")
    model = toy_model()
    model.nondeterministic = True
    with pytest.raises(ValueError, match="zero control"):
        explain_response(model, {"input_ids": torch.tensor([[0]])}, np.array([1., 0.]), 0, n_random=2)
    assert model.training
    assert not model.model.norm._forward_hooks
    assert all(not b._forward_hooks and not b._forward_pre_hooks for b in model.model.layers)
