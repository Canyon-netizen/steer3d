"""Known gated networks test whether interventions touch the intended computation."""
import sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
import torch
from torch import nn

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.neuron_mediation import native_forward, sign_regimes, select_units, matched_random_groups


class Gated(nn.Module):
    def __init__(self):
        super().__init__()
        self.gate_proj = nn.Linear(4,8,bias=False)
        self.up_proj = nn.Linear(4,8,bias=False)
        self.down_proj = nn.Linear(8,4,bias=False)
        self.act_fn = nn.SiLU()

    def forward(self,x):
        return self.down_proj(self.act_fn(self.gate_proj(x))*self.up_proj(x))


class Block(nn.Module):
    def __init__(self):
        super().__init__()
        self.mlp = Gated()

    def forward(self,h):
        return h+self.mlp(h)


class Tiny(nn.Module):
    def __init__(self):
        super().__init__()
        torch.manual_seed(17)
        self.model = nn.Module()
        self.model.layers = nn.ModuleList([Block(),Block()])
        self.embed = nn.Embedding(7,4)
        self.lm_head = nn.Linear(4,3,bias=False)
        self.config = SimpleNamespace(hidden_size=4)

    def forward(self,input_ids,use_cache=False,return_dict=True):
        h = self.embed(input_ids)
        for layer in self.model.layers:
            h = layer(h)
        return SimpleNamespace(logits=self.lm_head(h))


@pytest.fixture
def sample():
    model = Tiny().eval()
    ids = torch.tensor([[1,2,3]])
    vector = np.array([1.,0.,0.,0.],dtype=np.float32)
    return model,ids,vector


def test_four_sign_routes_preserve_positive_and_negative_poles():
    regimes = sign_regimes([1,1,-1,-1,0],[1,-1,1,-1,7])
    assert regimes.tolist() == [0,1,2,3,4]
    # ++ and -- have the same output sign but remain distinct mechanisms.
    assert 1*1 == (-1)*(-1) and regimes[0] != regimes[3]
    with pytest.raises(ValueError):
        sign_regimes([np.nan],[1])


def test_capture_and_zero_injection_do_not_change_model(sample):
    model,ids,vector = sample
    with torch.inference_mode():
        expected = model(ids).logits[0,-1].numpy()
    got = native_forward(model,ids,injection_layer=0,vector=vector,alpha=0)
    assert np.array_equal(expected,got["logits"])
    for state in got["states"].values():
        assert np.array_equal(state["effective_gate"]*state["value"],state["product"])


def test_natural_donor_is_assigned_exactly_and_only_at_last_position(sample):
    model,ids,vector = sample
    base = native_forward(model,ids,injection_layer=0)
    donor = base["states"][0]["product"].copy()
    donor[0] = 7.125
    observed = []
    handle = model.model.layers[0].mlp.down_proj.register_forward_pre_hook(lambda m,x:observed.append(x[0].detach().clone()))
    try:
        # Capture hook above runs before the instrument's edit; output hook sees actual input.
        actual = []
        out_handle = model.model.layers[0].mlp.down_proj.register_forward_hook(lambda m,x,y:actual.append(x[0].detach().clone()))
        try:
            changed = native_forward(model,ids,injection_layer=0,collect=False,patches={0:{"indices":[0],"donor":donor}})
        finally:
            out_handle.remove()
    finally:
        handle.remove()
    assert torch.equal(observed[0][0,:-1],actual[0][0,:-1])
    assert actual[0][0,-1,0].item() == 7.125
    assert torch.equal(observed[0][0,-1,1:],actual[0][0,-1,1:])
    assert not np.allclose(changed["logits"],base["logits"])


def test_identity_donors_preserve_baseline_and_steered_worlds(sample):
    model,ids,v = sample
    for alpha in (0.,.7):
        first = native_forward(model,ids,injection_layer=0,vector=v,alpha=alpha)
        patches = {i:{"indices":list(range(8)),"donor":state["product"]} for i,state in first["states"].items()}
        second = native_forward(model,ids,injection_layer=0,vector=v,alpha=alpha,patches=patches)
        assert np.array_equal(first["logits"],second["logits"])


def test_matched_control_matches_actual_residual_write_not_product_norm(sample):
    model,ids,v = sample
    base = native_forward(model,ids,injection_layer=0)
    donor = base["states"][0]["product"]+np.arange(1,9,dtype=np.float32)
    first = native_forward(model,ids,injection_layer=0,collect=False,patches={0:{"indices":[0,1],"donor":donor}})
    target = first["writes"][0]["applied_write_norm"]
    second = native_forward(model,ids,injection_layer=0,collect=False,
        patches={0:{"indices":[5,6],"donor":donor,"target_write_norm":target}})
    assert second["writes"][0]["applied_write_norm"] == pytest.approx(target,rel=1e-5)
    assert second["writes"][0]["scale"] != 1


@pytest.mark.parametrize("indices",[[],[0,0],[-1],[8]])
def test_wrong_coordinate_patches_are_rejected_and_hooks_are_removed(sample,indices):
    model,ids,v = sample
    model.train()
    with pytest.raises(ValueError):
        native_forward(model,ids,injection_layer=0,patches={0:{"indices":indices,"donor":np.zeros(8)}})
    assert model.training
    assert not model.model.layers[0]._forward_pre_hooks
    for block in model.model.layers:
        for module in (block.mlp.gate_proj,block.mlp.up_proj,block.mlp.down_proj):
            assert not module._forward_pre_hooks and not module._forward_hooks


def test_zero_donor_difference_cannot_match_nonzero_control(sample):
    model,ids,v = sample
    base = native_forward(model,ids,injection_layer=0)
    with pytest.raises(ValueError,match="unmatchable"):
        native_forward(model,ids,injection_layer=0,patches={0:{"indices":[0],
            "donor":base["states"][0]["product"],"target_write_norm":1.}})


def test_selection_uses_discovery_change_and_random_units_exclude_candidates():
    a = {0:{"product":np.arange(16,dtype=np.float32)}}
    b = {0:{"product":a[0]["product"]+np.array([0,0,0,5]+[0]*12)}}
    groups,scores,profiles = select_units([(a,b)],{0:np.ones(16)},1)
    assert groups == {0:[3]}
    random,audit = matched_random_groups(groups,profiles,{0:np.ones(16)},4,17)
    assert all(len(g[0]) == 1 and 3 not in g[0] for g in random)
    assert len(audit) == 4
    with pytest.raises(ValueError,match="no measured response"):
        select_units([(a,a)],{0:np.ones(16)},1)


def test_factorial_corpus_has_independent_truth_and_wording_and_problem_split():
    import importlib.util,json
    path = Path(__file__).parents[1]/"examples/run_neuron_mediation.py"
    spec = importlib.util.spec_from_file_location("mediation_cli_test",path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    protocol = json.loads((Path(__file__).parents[2]/"experiments/neuron_mediation_v1/protocol.json").read_text())
    cases = module.problem_specs(protocol)
    assert len(cases) == 48
    for index in range(12):
        cells = [c for c in cases if c["problem_id"] == f"math{index:02d}"]
        assert {(c["correct_equation"],c["wording"]) for c in cells} == {(True,"neutral"),(False,"neutral"),(True,"self_check_phrase"),(False,"self_check_phrase")}
        assert all((c["a"]*c["b"] == c["stated_result"]) == c["correct_equation"] for c in cells)
    train = {c["problem_id"] for c in cases if c["split"] == "discovery"}
    test = {c["problem_id"] for c in cases if c["split"] == "evaluation"}
    assert len(train) == len(test) == 6 and train.isdisjoint(test)
    # A large outside-class logit must reduce coverage, even when the A/B margin looks good.
    readout = module.outcome(np.array([10.,9.,20.]),[[0],[1]],"equation")
    assert readout["score"] == pytest.approx(1.)
    assert readout["p_correct"] < .001 and readout["answer_set_coverage"] < .001
    assert readout["argmax_outside_answer_set"] and not readout["argmax_correct"]
