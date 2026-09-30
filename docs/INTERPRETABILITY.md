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

# 5. does the extraction layer matter behaviourally? Extract the same
#    contrast at four layers, inject at one.
./scripts/run_extraction_layer_experiment.sh
python3 backend/examples/analyse_extraction_layer_effect.py --dir /tmp/iv_ext

# 6. every cross-layer cosine needs its null floor
python3 backend/examples/compare_extraction_layers.py --layers 8 14 20 24

# 7. what is inside a llama.cpp control-vector GGUF
python3 backend/examples/inspect_control_vectors.py --dir ~/test/vectors/Qwen3-1.7B
python3 backend/examples/diagnose_vector_signs.py --dir ~/test/vectors/Qwen3-1.7B

# 7b. use one - picks a layer, optionally repairs the per-layer sign
python3 backend/examples/gguf_to_npy.py \
    --gguf ~/test/vectors/Qwen3-1.7B/entry_05.gguf \
    --name sound_vs_flawed --layer 20 --sign-fix \
    --layer-profiles backend/examples/output/layer_profiles.json \
    --out-dir backend/examples/output/steering_vectors_user

# 8. publish to the UI
./scripts/publish_artifacts.sh
```

On a network filesystem, copy the model to local disk first and set
`HF_HUB_OFFLINE=1`; the import alone can cost minutes and a blocking network
call looks exactly like a hang.

## Finding 5: "the confidence direction" is not one direction

Every result above extracts a vector at L14 and injects it at L20. That
mixes two things — the direction is *about* confidence, and it was *read out*
somewhere specific. Extracting the same semantic contrast at four different
layers and comparing the resulting vectors (`compare_extraction_layers.py`,
same 48 trajectories) separates them:

| cosine between extractions | L8↔L14 | L14↔L20 | L20↔L24 | L8↔L24 |
|---|---|---|---|---|
| confidence_up | 0.825 | 0.623 | 0.830 | **0.395** |
| caution | 0.756 | 0.554 | 0.796 | **0.319** |
| creativity | 0.675 | 0.510 | 0.776 | **0.243** |
| reasoning_deep | 0.737 | 0.629 | 0.813 | **0.344** |

**Every one of those numbers needs the null floor beside it.** Two vectors
extracted from the same model share most of their direction through the
residual stream's own geometry, so a high cosine is the expected result
rather than evidence of a shared concept. `compute_steering_vectors.py
--with-null` therefore also extracts a matched random control per direction —
the same two sample sizes, assigned at random from the same pool, so it
differs from the real contrast only in that the grouping carries no
information. Mean off-diagonal cosine, real vs null:

| direction | real | null floor | excess |
|---|---|---|---|
| confidence_up | +0.613 | +0.039 | **+0.574** |
| reasoning_deep | +0.576 | −0.006 | +0.582 |
| caution | +0.547 | −0.020 | +0.567 |
| creativity | +0.486 | +0.011 | +0.474 |

The floor is near zero for this construction and the real directions clear it
by a wide margin, so the differences above are real. The L8 and L24 versions
of "the confidence direction" have a cosine of 0.395 against a floor of ~0.03:
they share almost nothing. There is a shared component — adjacent layers stay
well correlated — but the direction is substantially rebuilt through the
stack rather than merely rotated.

Separately, the confidence contrast is *cleaner* deeper in: Cohen's d rises
from 1.70 at L8 to 2.26 at L20 before easing to 2.11 at L24. So a vector can
be better separated at depth and still point somewhere else — those are two
different properties, and the d column alone would mislead.

## Finding 6: the extraction layer changes the effect, 2.15×

Finding 5 is representational. This is the behavioural consequence, and it
is the confound named at the end of Finding 5 actually mattering.

Same 24 problems, injection held fixed at L20, strength 0.20, paired. Only
the layer the vector was **read out at** varies:

| extracted at | control | Δ logit KL | sd | t(23) | p | token agree |
|---|---|---|---|---|---|---|
| L8 | 0.0000 | +0.0953 | 0.069 | 6.74 | 7.1e−07 | 0.9460 |
| L14 | 0.0000 | +0.1358 | 0.088 | 7.55 | 1.1e−07 | 0.9399 |
| L20 | 0.0000 | +0.1965 | 0.084 | 11.45 | 5.6e−11 | 0.9440 |
| L24 | 0.0000 | +0.2048 | 0.085 | 11.74 | 3.4e−11 | 0.9447 |

Friedman across the four layers: χ² = 32.95, p = 3.3e−07. The effect rises
monotonically with extraction depth — **2.15× from L8 to L24** — and every
pairwise difference is significant except L24 vs L20 (t = 0.39, p = 0.70).

That last row is the informative one. The gain stops exactly at the injection
layer: reading the direction out *at or past* where it is applied buys
nothing further, while reading it out well below costs about half the effect.
The confound is not a footnote after all, and the right default is to extract
at the layer you inject at.

Token agreement barely moves (0.940–0.946) while logit KL doubles. The extra
divergence is therefore distributional — the shadow stream moves further into
the tail of the distribution without changing which token is usually picked.
That is a meaningfully different thing from "the model behaves differently",
and the two should not be conflated.

## Finding 7: a cross-layer cosine has no meaning without its control

While checking the user's GGUF control vectors (below) it became clear that
the null floor for this family of statistics is not a constant, and quoting a
cosine without saying which control produced it is meaningless. Two
constructions, both legitimate, both measured on this corpus:

| null construction | adjacent-layer floor | ≥4 layers apart | L0↔L27 |
|---|---|---|---|
| balanced random split of one pool | ~0.00 | −0.01 | +0.10 |
| two small random subsets of all positions | **+0.87** | +0.38 | +0.10 |

The second has a floor of 0.87 because the positive group is a small,
selected subset: its mean is a biased estimate of something, and that bias
persists across layers, so a difference of means built from it inherits a
shared component whether or not the grouping means anything. `null` mode in
`position_pooling_test.py` measures it; the floor is what any cross-layer
cosine from that construction has to be read against.

The practical consequence: **the same number, 0.4, is either strong evidence
or pure noise depending on the control.** Finding 5's 0.395 is real because
it is measured against the first construction. Any cross-layer cosine
reported anywhere in this project now ships with its floor.

The same file also showed that **separation**, not cosine, is what actually
discriminates a real contrast. Extracting the self-check contrast four ways
on 27 trajectories, with a random-split null:

| mode | separation (L0 → L27) | adjacent cosine |
|---|---|---|
| last position only | 30.1 → 43.8 | +0.899 |
| final fifth of each trajectory | 25.9 → 39.3 | +0.903 |
| every position | 24.9 → 38.3 | +0.906 |
| **random split (null)** | **3.3 → 3.8** | +0.873 |

A real contrast separates by 25–44 where a null separates by ~3.4 — a factor
of ten — while the adjacent cosine barely moves (0.906 vs 0.873). Cohen's d
and effect-size proxies are the statistics that carry information here; the
cosine is mostly measuring the residual stream's own geometry.

This also **overturns an earlier hypothesis in this project.** The
`token_pos` flip in the user's files looked like a position-pooling failure,
and the natural experiment on our own data found no such effect: all three
pooling modes were equally stable (0 sign changes, adjacent cosine 0.90). The
failure is in the null control, not in the position handling.

## The user's GGUF control vectors

`~/test/vectors` holds llama.cpp `controlvector` files (method
`pca_cv:center`), six model directories, `entry_01`–`entry_08` each. They are
read by `examples/gguf_cv.py`, a dependency-free parser — the `gguf` package
in the conda env predates numpy 2.0 and dies on `ndarray.newbyteorder`.

Their structure is easy to misread, and this project misread it once. The
files store **one direction per layer** — a Qwen3-1.7B file has 28 tensors
named `direction.0`…`direction.27`, matching its `layer_count` of 28 — and
the 28 `explained_variance.N` values are per layer, not per component.
Treating them as components of one vector produced a "flat, no dominant
direction" verdict that was an artefact. `test_rows_are_layers_not_components`
pins the real layout.

What the files actually contain, and what bears on the reported low
interpretability:

1. **The sample is 4–30 pairs.** `n_pairs` is 30 for the reasoning and safety
   vectors, 10 for the style and creative ones, and **4** for
   `Qwen2.5-7B-Instruct`, whose files carry no `dataset` or contrast fields at
   all. Vectors in this repo are built from 15,679–20,930 tokens. A
   difference of means over 4 pairs in 3584 dimensions is close to a random
   draw with a label attached.
2. **The `token_pos=all` files have inconsistent per-layer signs.**
   Adjacent-layer cosines, which should be strongly positive for one
   semantic contrast:

   | entry | contrast | pairs | token_pos | negative adjacent pairs | sign changes |
   |---|---|---|---|---|---|
   | entry_01 | sound/flawed | 30 | −1 | 0/27 | 0 |
   | entry_02 | harmful/benign | 30 | −1 | 0/27 | 0 |
   | entry_03 | adult/child | 10 | −1 | 0/27 | 0 |
   | entry_04 | creative/mundane | 10 | −1 | 0/27 | 0 |
   | entry_05 | sound/flawed | 29 | all | 7/27 | 9 |
   | entry_06 | planned/impulsive | 29 | all | 6/27 | 8 |
   | entry_07 | sound/flawed | 10 | all | 8/27 | 10 |
   | entry_08 | adult/child | 10 | all | 13/27 | 16 |

   entries 1 and 5 are the *same contrast* at the *same sample size*
   (30 vs 29 pairs) and differ only in `token_pos`; entries 1–4 all use
   `token_pos=-1` and none of them flip, while every `token_pos=all` file
   does. Magnitudes reach −0.89, and the sign alternates rather than
   inverting a contiguous run.

   **This is confirmed, not inferred.** Propagating a single sign
   convention from layer 0 — carry the previous layer's sign forward,
   flipping the current one only if it points against its predecessor —
   makes *every* adjacent cosine positive in all four files, and the
   profile becomes smooth and rising with depth, the same shape as the
   clean files:

   | entry | before (min adj) | after sign-aligning from L0 |
   |---|---|---|
   | entry_05 | −0.89 | +0.47 … +0.89, all positive |
   | entry_06 | −0.81 | +0.36 … +0.85, all positive |
   | entry_07 | −0.85 | +0.48 … +0.76, all positive |
   | entry_08 | −0.72 | +0.03 … +0.72, all positive |

   So the direction itself is coherent and the *sign* is not: it is being
   decided per layer, and one global convention repairs every file. That
   is the most likely single cause of the vectors reading as
   uninterpretable in use — a steering vector whose sign alternates with
   depth is not steering, it is applying a random perturbation at some
   layers and its negation at others. `diagnose_vector_signs.py`
   reproduces the before and after.

   The extraction code is `~/test/steer/extract/extract_vectors.py`, which
   delegates to a library object via `cv.export_gguf()`. Which layer
   chooses the sign is inside that library and was not traced; the data
   above localises the fault to it either way.
3. **The vectors are unit-norm** (‖v‖ = 1.00 at every layer, ratio 1.000).
   That is fine as a format, but it means the file cannot express *how much*
   to add. The same nominal strength is 343% of the state norm at L4 and 4% at
   L26 (Finding 4), so a per-layer scale has to come from outside the format.
   This is exactly what `SteeringRegistry.load_layer_scales()` does, sourced
   from the measured `layer_profiles.json`, and what the UI reports as
   "scale not measured" when it has no profile for a layer.
4. **`correct_direction` is set**, so "up" is a stored convention rather than
   a fact, and the sign question above cannot be settled from the file.
5. **They are not interchangeable with this project's vectors.** Cosine
   between each of the eight per-layer directions and this repo's
   `reasoning_deep` at L20 stays at the random floor: mean |cos| 0.010–0.036
   against √(2/π·2048) = 0.018. So "sound vs flawed reasoning" and "late
   vs early reasoning" are different concepts here, at every layer. They
   should be chosen between on the basis of which contrast is wanted, not
   treated as two versions of a reasoning direction.

`gguf_to_npy.py` exports any of these into the registry's format, picking a
layer, optionally applying the sign fix, and reporting the before/after. The
scale still has to come from outside the format:
`--layer-profiles layer_profiles.json`, and the UI will otherwise show the
direction as uncalibrated.

The format itself is fine; the extraction behind it is where the work is.
Extracting at the injection layer (Finding 6), from hundreds of pairs rather
than tens, with the per-layer sign taken from a fixed convention rather than
per-layer, are the three changes that would most improve these vectors.

## What is not established

- **Effect sizes are small and per-problem variance is large.** The
  confidence direction moves mean entropy by 0.012–0.022 nats and costs
  ~6% token agreement. Individual problems range from −0.072 to +0.040, so
  a single run predicts almost nothing. The n = 24 result establishes that
  the *mean* effect is real, not that any individual run is predictable.
- **Why `caution` and `creativity` degrade is unexplained.** The
  categorical-vs-continuous contrast offered above is a hypothesis this
  data does not test.
- Vectors are extracted at L14 and tested at L20. Finding 6 quantifies
  what that costs: **2.15× in logit KL** between the L8 and L24
  extractions, with injection held fixed. Every effect size in the
  earlier sections is specific to that pairing, and the gap is large
  enough that quoting a number without naming both layers is misleading.
- **Which layer chooses the sign is not traced.** The fault is localised
  to a per-layer sign decision inside the library that writes the GGUF,
  and the data shows a single global convention repairs all four files —
  but the specific line is in code this project did not write and has
  not read.
- Everything is Qwen3-1.7B. The layer conclusions are model-specific and
  should not be assumed to transfer.
- The strength-0.0 control proves the *hook* is inert when it should be. It
  does not rule out a systematic bias present at every non-zero strength,
  such as the perturbation itself changing the layer statistics the
  divergence is measured against.
- **Logit KL and behaviour are not the same quantity.** Finding 6's 2.15×
  is a distributional divergence that leaves token agreement flat at
  ~0.94. No claim here establishes that the model's *answers* get better
  or worse — only that its output distribution moves.

## Reporting standard used here

Every effect size is reported with the number of problems behind it and,
where n permits, a test statistic. Single-prompt numbers are labelled as
such, and a paired contrast is distinguished from a one-sample test — the
two differ enough at small n to change the p-value, and conflating them is
easy to do by accident.

Any statistic comparing two vectors extracted from the same model is
reported with the null floor it was measured against, for the reason in
Finding 7: the floor ranges from ~0 to ~0.87 depending on how the control
is built, so the bare number is not interpretable on its own.

Three claims in earlier drafts of this file did not survive checking and
have been corrected above:

1. That the `confidence_up`/`confidence_down` antisymmetry was "the single
   strongest piece of evidence" for the pipeline measuring causal effect.
   At the time it rested on one prompt, and at n = 5 it did not reach
   significance. It is now supported at n = 24, but by the replication
   rather than by the antisymmetry alone.
2. That `caution`'s fragility is explained by its 165:1 extraction
   imbalance. It is not — `creativity` is near-balanced and degrades just
   as much, so the imbalance story does not survive contact with the other
   four directions.
3. That pooling the contrast over token positions destabilises the
   extracted direction, offered as the explanation for the sign flips in
   the user's GGUF vectors. It does not: all three pooling modes were
   equally stable on this corpus, with zero sign changes and adjacent
   cosine ~0.90 against a null floor of 0.87. The null floor is high
   enough that this test could not have detected the effect even if it
   were present, which is itself the lesson of Finding 7. The flips are
   instead a per-layer sign decision, confirmed by sign-aligning from
   L0 and recovering a smooth profile in every affected file.

