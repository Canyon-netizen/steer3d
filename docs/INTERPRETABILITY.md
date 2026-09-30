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

Layer 27 dropping to about half the effective rank of other layers (42.9 vs
84–94 with the random-projection sketch used here) is the model compressing
toward the output vocabulary — the last step before the logits are not really
"reasoning" any more. Absolute values are method-dependent: a full-spectrum
computation gives lower numbers everywhere (29.3 at L27, 53–62 elsewhere) but
the same ~50% reduction, so the *ratio* is the durable claim and the absolute
effective rank is not comparable across estimators.

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

## Finding 3: the negative control moves in the opposite direction

`confidence_down` is constructed as the exact negation of `confidence_up`.
On an AIME problem at L20, strength 0.20:

- `confidence_up` → Δentropy **−0.0147**
- `confidence_down` → Δentropy **+0.0257**

They land on opposite sides of zero, which is what a real causal direction
should do. It is *not*, on its own, proof that the measurement is sound —
with one prompt there is no way to tell a genuine antisymmetric effect from
one prompt's noise happening to fall that way. Replication on five problems
(§ below) is what makes the claim worth anything, and it is also what
showed how weak the single-prompt version was.

It also surfaced something that is *not* yet explained. Two directions —
`caution` and `creativity` — degrade sharply under steering (logit KL 0.141
and 0.133 at strength 0.20) while the rest stay far cleaner (0.035–0.060).
The obvious hypothesis is extraction imbalance: `caution` came from 379
self-check tokens against 62,420 ordinary ones, a 165:1 skew. That hypothesis
is wrong. `creativity` is extracted from a near-balanced 1.80:1 contrast and
degrades just as much:

| direction | n_pos | n_neg | ratio | logit KL @ 0.20 |
|---|---|---|---|---|
| caution | 379 | 62,420 | 164.7 | 0.141 |
| creativity | 40,338 | 22,461 | 1.80 | 0.133 |
| reasoning_deep | 15,679 | 15,679 | 1.00 | 0.060 |
| confidence_up | 20,930 | 15,718 | 1.33 | 0.053 |
| confidence_down | 20,930 | 15,718 | 1.33 | 0.035 |

Across these five there is no relationship between sample balance and how
much damage the injection does. What the two sensitive directions have in
common is something else — `caution` and `creativity` are the two vectors
built from *categorical* token sets (self-check / in-think-block) rather
than from a continuous score (entropy quantile, sequence position). A
difference-of-means over a bimodal set of token types may be pointing at a
state the network uses for a categorical decision, which is why over-driving
it degrades fluency instead of shifting a tunable scalar. That is a
hypothesis, and this data does not test it — it would need directions built
from matched categorical and continuous contrasts, varying only in that
respect.

## Finding 3b: does it hold up across problems?

A single prompt proves very little. Replicated across all 24 AIME problems
in the collected dataset, at L20, strength 0.20, with `confidence_down` the
exact negation of `confidence_up`:

| condition | n | Δentropy (mean ± sd) | t(23) | p | signs |
|---|---|---|---|---|---|
| confidence_up @ 0.00 | 24 | +0.0000 ± 0.0000 | — | — | control |
| confidence_up @ 0.20 | 24 | −0.0118 ± 0.0234 | −2.47 | 0.021 | 17/24 negative |
| confidence_down @ 0.00 | 24 | +0.0000 ± 0.0000 | — | — | control |
| confidence_down @ 0.20 | 24 | +0.0224 ± 0.0225 | +4.90 | 0.00006 | 21/24 positive |
| paired (up − down)/2 | 24 | −0.0171 ± 0.0178 | −4.72 | 0.00009 | — |

The effect is real and small: a 20%-of-state-norm push moves mean entropy by
about 0.012–0.022 nats, at a cost of 6% token agreement. The zero-strength
controls are exactly 0.0000 with zero variance on all 24 problems, so nothing
here is an artefact of the hook.

An earlier version of this file drew a conclusion from five problems, where
the paired t(4) was −2.43 and −2.18 and did not reach p < 0.05. It reported
"significance not established", which was the right call at that n but left
the impression the effect was in doubt. At n = 24 it is established. Note
also that the per-problem spread remains large — individual problems range
from −0.072 to +0.040 — so a single run still predicts very little.

Two things worth noting:

- **The effect is asymmetric by about 1.9×.** The vectors are exact
  negations, so under a linear readout the two effects would be equal.
  They are not, which means the response is nonlinear: entropy is much
  cheaper to raise than to suppress. A "confidence" direction is a weaker
  lever than its "uncertainty" counterpart.
- **Token agreement falls to 94.0% (up) and 93.5% (down)** at this strength,
  so roughly one token in twenty is different from baseline. Most of the
  entropy shift is achieved without the model producing a visibly different
  answer.

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

# 3b. multi-problem replication. Build the small problem index first —
#     the trajectory sidecars are tens of MB each and reading them over a
#     network filesystem just for the problem text is needlessly slow.
python3 backend/examples/make_problem_index.py --out /tmp/problem_index.json
python3 backend/examples/run_intervention.py \
    --model-path /path/to/Qwen3-1.7B \
    --problems-file /tmp/problem_index.json \
    --directions confidence_up confidence_down --sweep 0.0 0.2 --layer 20 \
    --out backend/examples/output/intervention/replication_24problems_L20.json

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

- **Effect sizes are small and per-problem variance is large.** The
  confidence direction moves mean entropy by 0.012–0.022 nats and costs
  ~6% token agreement. Individual problems range from −0.072 to +0.040, so
  a single run predicts almost nothing. The n = 24 result establishes that
  the *mean* effect is real, not that any individual run is predictable.
- **Why `caution` and `creativity` degrade is unexplained.** The
  categorical-vs-continuous contrast offered above is a hypothesis this
  data does not test.
- Vectors are extracted at L14 and tested at L20. The extraction layer was
  not swept — that confound is not yet separated.
- Everything is Qwen3-1.7B. The layer conclusions are model-specific and
  should not be assumed to transfer.
- The strength-0.0 control proves the *hook* is inert when it should be. It
  does not rule out a systematic bias present at every non-zero strength,
  such as the perturbation itself changing the layer statistics the
  divergence is measured against.

## Reporting standard used here

Every effect size is reported with the number of problems behind it and,
where n permits, a test statistic. Single-prompt numbers are labelled as
such, and a paired contrast is distinguished from a one-sample test — the
two differ enough at small n to change the p-value, and conflating them is
easy to do by accident.

Two claims in earlier drafts of this file did not survive checking and have
been corrected above:

1. That the `confidence_up`/`confidence_down` antisymmetry was "the single
   strongest piece of evidence" for the pipeline measuring causal effect.
   At the time it rested on one prompt, and at n = 5 it did not reach
   significance. It is now supported at n = 24, but by the replication
   rather than by the antisymmetry alone.
2. That `caution`'s fragility is explained by its 165:1 extraction
   imbalance. It is not — `creativity` is near-balanced and degrades just
   as much, so the imbalance story does not survive contact with the other
   four directions.
