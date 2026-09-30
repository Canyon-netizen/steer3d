# Interpretability: what this project measures, and what it found

This started as a 3-D viewer of a model's hidden states. That part was never
the hard part — you can project a residual stream through PCA and draw a
ribbon. What was missing was any way to answer the two questions that make
the picture mean something:

1. **What is the model doing at this point?** Not "where did it move", but
   what does this layer's activation actually encode?
2. **What did my intervention do?** Not "the path changed", but did the
   change come from the vector, and where did it go?

Both are answered here with measurement. Every number the UI shows is
computed from the collected trajectories; where a measurement is missing
the UI says so rather than substituting a plausible-looking label.

## The counterfactual

Injecting a vector and watching the trajectory move tells you nothing on its
own — the trajectory moves anyway, every token changes the state. To attribute
a change to the intervention you need a counterfactual.

So every steered step runs **two** forward passes over the same KV-cache
prefix: the primary, with the vector added at layer *L*, and a shadow,
identical except the vector is absent. Both consume the *same* token,
teacher-forced from the primary's own argmax. That is deliberate — it makes
the comparison well-posed. The shadow asks "given exactly this text, where
would the state have been?", which is a question about representation. If
each stream instead fed its own argmax, divergence would compound into a
different sentence and you could no longer separate a representational change
from a behavioural one.

What that buys you, per step and per layer:

- `cos(h_steered, h_baseline)` — how much the perturbation survives
- `‖h_steered − h_baseline‖ / ‖h_baseline‖` — the same, scale-free
- logit KL and the entropy delta — whether it reached the output
- `first_diverged_step` — where behaviour, not just representation, splits

The strength-0.0 control injects a zero vector and must come back at exactly
zero divergence. Every table below includes it, because it is what makes the
rest attributable.

## Finding 1: confidence lives in late layers, not where the old UI said

`measure_layers.py` computes, over 48 AIME trajectories and 20,010 sampled
tokens, the correlation between a layer's activation magnitude and the
model's next-token entropy:

| layers | r(‖h‖, entropy) |
|---|---|
| 0–16 | \|r\| < 0.15 — magnitude says nothing about certainty |
| 17–23 | +0.27 … +0.43, peaking at L23 |
| 27 | collapses: effective rank 42.9 vs ~90 elsewhere |

The frontend used to carry a hand-written table — "L12 semantic, L16
reasoning, L20 deep reasoning". The measurement contradicts it. L12 sits in
the flat region; the entropy signal lives at L17–23. Self-check states show
the inverse pattern: most separable early (cos gap 0.90–0.93), dipping to
0.736 at L19. "Verification" is encoded early and stays available;
*confidence as magnitude* is a late-layer phenomenon. Those are two
different things, and conflating them was the original error.

Layer 27 dropping to effective rank 42.9 is the model compressing toward the
output vocabulary — the last step before the logits are not really
"reasoning" any more.

## Finding 2: the confidence vector works, and over-driving it inverts

`confidence_up` extracted at L14, injected at L20, on "What is 17 × 23?":

| strength | ‖v‖ | token agree | Δentropy | max divergence |
|---|---|---|---|---|
| 0.00 | 0.0 | 100.0% | +0.0000 | 0.0000 |
| 0.05 | 43.3 | 96.1% | −0.0064 | 0.0113 |
| 0.15 | 129.9 | 96.1% | **−0.0303** | 0.1250 |
| 0.30 | 259.7 | 86.3% | **+0.0233** | 0.4143 |

Entropy falls most at 0.15 and *reverses* at 0.30 while agreement collapses
to 86%. Past roughly 0.2 the perturbation is no longer a stronger version of
the same intervention — it is damaging the computation, and a damaged
computation is not a confident one. This is why a single strength is not
evidence: the dose-response is non-monotone.

## Finding 3: the negative control is antisymmetric

`confidence_down` is constructed as the exact negation of `confidence_up`.
On an AIME problem at L20, strength 0.20:

- `confidence_up` → Δentropy **−0.0147**
- `confidence_down` → Δentropy **+0.0257**

A measurement picking up noise, drift, or an artefact of the hook would not
come out antisymmetric to that degree. This is the single strongest piece of
evidence that the extract → inject → shadow-compare pipeline measures real
causal effect.

It also surfaces a real weakness: `caution` is the one direction whose
entropy effect reverses with strength (−0.002 at 0.10, +0.022 at 0.20) while
token agreement falls furthest, to 91.4%. It was extracted from a
379-self-check-token vs 62,420-ordinary-token contrast — roughly 165:1. That
is the likely reason, and it means direction quality tracks *sample balance*,
not just the reported Cohen's d. The UI shows both.

## Finding 4: a fixed norm is not a fixed intervention

Injecting ‖v‖ = 130 at ten different layers:

| layer | ‖h‖ | ‖v‖/‖h‖ | token agree | logit KL |
|---|---|---|---|---|
| 4 | 37.9 | 343% | 86.4% | 1.21 |
| 8 | 57.5 | 226% | 86.4% | 1.35 |
| **12** | 120.9 | 108% | **0.0%** | **6.98** |
| 16 | 251.5 | 52% | 90.1% | 0.68 |
| 20 | 865.8 | 15% | 95.1% | 0.025 |
| 26 | 3052.8 | 4.3% | 97.5% | 0.002 |

The residual stream grows about 80× from L4 to L26. One absolute norm is
343% of the state at L4 and 4% at L26.

L12 is a cliff, not a slope. Between 226% (86% agreement) and 108% (0%
agreement) there is no graceful degradation — past about 1× the state norm
the residual stream stops carrying usable signal. The usable band for this
model is L18–L24.

This is why `SteeringRegistry.scaled()` expresses strength as a *fraction of
that layer's measured ‖h‖*, loaded from `layer_profiles.json`, and why the UI
says "scale not measured" rather than showing a percentage it cannot
honour.

## Reproducing

```bash
# 1. steering vectors from the collected .npz trajectories
python3 backend/examples/compute_steering_vectors.py --layer 14

# 2. measured layer profiles (feeds the UI and the strength calibration)
./scripts/refresh_layer_profiles.sh

# 3. counterfactual intervention sweeps
python3 backend/examples/run_intervention.py \
    --model-path /path/to/Qwen3-1.7B \
    --directions confidence_up confidence_down caution reasoning_deep creativity \
    --sweep 0.0 0.1 0.2 --layer 20 \
    --out backend/examples/output/intervention/directions_L20_aime2023.json

# 4. where in depth to inject
python3 backend/examples/layer_scan.py \
    --model-path /path/to/Qwen3-1.7B \
    --direction confidence_up --norm 130 --layers 4 8 12 14 16 18 20 22 24 26

# 5. publish to the UI
./scripts/publish_artifacts.sh
```

On a network filesystem, copy the model to local disk first and set
`HF_HUB_OFFLINE=1`; the import alone can cost minutes and a blocking network
call looks exactly like a hang.

## What is not established

- Most numbers here come from a single prompt with greedy decoding. The
  structural claims (80× growth, the L12 cliff, the zero-control) are robust;
  individual Δentropy values in the 10⁻³ range are within single-run noise.
- Vectors are extracted at L14 and tested at L20. The extraction layer was
  not swept — that confound is not yet separated.
- Everything is Qwen3-1.7B. The layer conclusions are model-specific and
  should not be assumed to transfer.
