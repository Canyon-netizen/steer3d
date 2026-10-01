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
the inverse pattern, though not a simple one — the cosine gap between
self-check and ordinary tokens runs 0.900–0.917 through L12, drops to
0.776–0.788 across L16–L18, bottoms at 0.736 at L19, recovers to 0.828 at
L24, and then collapses to 0.355 at L27. An earlier draft of this file
reported only the L19 dip, which reads as a single excursion; the curve
actually falls, partly recovers, and then falls off a cliff at the last
layer. "Verification" is encoded early and stays available through most of
the stack; *confidence as magnitude* is a late-layer phenomenon. Those are
two different things, and conflating them was the original error.

Layer 27 dropping to about half the effective rank of other layers (42.9 vs
84–94 with the random-projection sketch used here) is the model compressing
toward the output vocabulary — the last step before the logits are not really
"reasoning" any more. Absolute values are method-dependent: a full-spectrum
computation gives lower numbers everywhere (29.3 at L27, 53–62 elsewhere) but
the same ~50% reduction, so the *ratio* is the durable claim and the absolute
effective rank is not comparable across estimators.

## Finding 2: the confidence vector works, and over-driving it inverts

`confidence_up` extracted at L14, injected at L20, on "What is 17 × 23?".
**This is n = 1.** It is the clearest illustration of the shape of the
dose-response, and the shape is the point — but nothing here establishes
where the turning point is in general, and Finding 3b's 24-problem run
covers only strength 0.20:

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
it degrades fluency instead of shifting a tunable scalar.

**That hypothesis was tested, and it does not survive.** `cat_matched` and
`cont_matched` hold everything fixed except the kind of split: both take
379 samples per side, one grouping self-check tokens against other tokens
(categorical) and the other the top 379 entropy tokens against the bottom
379 (a continuous score), both injected at L20 at strength 0.20 over the
same 24 problems:

| direction | kind of split | n per side | Cohen's d | Δ logit KL |
|---|---|---|---|---|
| cat_matched | categorical | 379 / 379 | −1.15 | 0.1114 |
| cont_matched | continuous score | 379 / 379 | −1.63 | 0.0879 |

The categorical direction is 26.7% more damaging, in the predicted
direction, and higher on 18 of 24 problems — but **t = 1.50, p = 0.15, not
significant.** And the grouping does not survive contact with the other four
directions:

| | directions | mean Δ logit KL |
|---|---|---|
| categorical | cat_matched, caution, creativity | 0.1158 |
| continuous | cont_matched, reasoning_deep, confidence_up | 0.1252 |

The continuous set is *higher* on average, because `confidence_up` — a
continuous contrast, and the most damaging of all six — sits at 0.1965. So
the original pattern was an artefact of which concepts happened to land in
each group, not a property of categoricity. The two groups are not matched
on effect size either (`confidence_up` has d = +1.83 against cat_matched's
−1.15), so the only like-for-like evidence is the matched pair above, and it
is not significant. **Stop attributing the fragility of `caution` and
`creativity` to categoricity; the data does not support it.**

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

- **The two directions differ by 1.9× in mean effect** (0.0224 against
  0.0118). The vectors are exact negations, so a linear response would give
  equal magnitudes. **That nonlinearity is not established**: the test it
  requires is a one-sample test on the *sum* of the two per-problem effects,
  and at n = 24 that gives t = 1.80, p = 0.085. The paired t(23) = −4.72,
  p = 0.00009 reported above tests whether the average effect is non-zero,
  which is a different and easier question — it would come out significant
  even if the two sides were exactly symmetric. So the asymmetry is a real
  difference between two measured means and nothing more. Both directions
  have only been measured at 0.0 and 0.2; a dose-response for
  `confidence_down`, which Finding 2 has for `confidence_up`, is what would
  characterise the shape.
- **Token agreement falls to 94.0% (up) and 93.5% (down)** at this strength,
  so roughly one token in twenty is different from baseline. Most of the
  entropy shift is achieved without the model producing a visibly different
  answer.

## Finding 4: a fixed norm is not a fixed intervention

Injecting ‖v‖ = 130 at ten different layers. **This is also n = 1** — one
AIME problem. The relative magnitudes are a property of how the residual
stream grows, which is measured over the whole corpus, but the
agreement and KL columns are one problem's worth of damage and the exact
cliff location should be treated as a single observation:

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

## Finding 8: which layer picks the token

Findings 1–7 all ask what a *vector* does. None of them asked the question
this project is named after: at a given decoding step, **why is the output
token this one and not the next one?**

`attribute_token_choice.py` answers it with a logit lens. For each step it
takes the chosen token and its top-1 alternative and decomposes the logit
gap between them layer by layer, reporting each layer's lens fidelity
(KL against the model's own logits) beside the attribution.

Two things had to be fixed before any of it was trustworthy, and both
produced plausible-looking output while being wrong:

1. **bfloat16 silently zeroes the whole curve.** Read through the
   unembedding in bf16, the un-normalised residual stream collapses to a
   constant, so every layer's gap is exactly `0.000` — a flat, perfectly
   "consistent" attribution that means nothing. float32 is required, and
   the script now raises if the lens is degenerate rather than reporting it.
2. **`hidden_states[-1]` is not the model's own final state.** Under
   transformers 5.x, rebuilding the last layer from it disagrees with
   `model(...).logits` by up to 15 nats and even changes which token ranks
   second. The last layer is therefore taken from the model's own logits.
   Verified: the L28 gap is −6.674 against a true margin of 6.674.

### 8a: the decision is made in the last quarter of the stack

24 AIME problems × 12 greedy steps per model, 288 steps each, restricted to
steps with a real decision (top-2 margin > 0.5; 278 and 280 qualify). The
statistic is **sign agreement** — how often the layer's partial model
already prefers the token that is ultimately chosen, against its top-1
alternative:

| layer | Qwen3-1.7B (28L) | Qwen3-4B (36L) | Qwen3-8B (36L) |
|---|---|---|---|
| 0 | 56% | 42% | 60% |
| 4 | 67% | 48% | 46% |
| 8 | 71% | 57% | 58% |
| 12 | 73% | 64% | 64% |
| 16 | 75% | 63% | 68% |
| 20 | **83%** | 70% | 74% |
| 24 | **91%** | 72% | 61% |
| 28 | **100%** | 79% | 78% |
| 32 | — | 83% | 78% |
| 36 | — | **100%** | **100%** |

| model | 80% agreement | as % of depth | 90% agreement |
|---|---|---|---|
| Qwen3-1.7B | L20 | 71% | L24 (86%) |
| Qwen3-4B | L30 | 83% | L35 (97%) |
| Qwen3-8B | L23 | 64% | L35 (97%) |

The early stack is near chance — L0 sits at 56%, 42% and 60%, which is a
coin flip — and agreement climbs late. **The token is not chosen early and
merely read out late; the choice is made in the last third of the stack.**
The absolute layer index does not transfer across model sizes, which is the
same warning Finding 1's closing note carries.

**The 8B column is visibly noisier and is reported that way rather than
smoothed.** With n = 280 the standard error on each point is about 3.0
points, and 8B's curve falls from 74% at L20 to 61% at L24 before
recovering — a 13-point move that is four standard errors, so it is a real
departure from the clean monotonic shape of 1.7B and 4B, not a rendering
artefact. The other two models rise monotonically. What survives across all
three is the *late* rise and the 97–100% endpoint; the intermediate
thresholds do not, and the 64% figure in the table is a first crossing
through a fluctuating curve rather than a stable plateau.

This corroborates Finding 1 from an independent direction for the two
cleaner models. That finding measured ‖h‖ correlating with next-token
entropy and put certainty in L17–23; this one puts the *decision* at 64–83%
of depth. Two unrelated statistics landing in the same third of the stack
is stronger than either alone — but see 8a-null below before treating the
early-layer values as measured chance rather than an assumed one.

### 8a-null: the raw agreement curve has no 50% baseline

The obvious reading of the table above is "the early layers sit near 50%,
i.e. near chance". That was asserted, not measured, so it was measured: the
same 288 steps were re-attributed against an alternative token drawn **at
random from the vocabulary** instead of the model's own top-1
(`--random-alternatives 1`, seed 0).

The null is **not 50%**. It runs 78.5% at L0 and reaches 100% by L24:

| layer | real (vs top-1 alt) | null (vs random token) | excess |
|---|---|---|---|
| 0 | 55.8% | 78.5% | **−22.7** |
| 4 | 66.5% | 85.4% | −18.9 |
| 8 | 70.5% | 88.5% | −18.0 |
| 12 | 73.0% | 90.6% | −17.6 |
| 16 | 75.2% | 92.0% | −16.8 |
| 20 | 83.1% | 94.8% | −11.7 |
| 24 | 91.4% | 100.0% | −8.6 |
| 28 | 100.0% | 100.0% | 0.0 |

A random token's logit is uniformly low, so *which way round* it loses is
decided early and confidently — the null picks "the real token wins" ~78%
of the time from L0. Against that baseline the real comparison is not
merely uninformative early, it is **below** the null: the early layers are
if anything mildly *anti*-aligned with the eventual answer, which is what
an actively-wrong intermediate prediction looks like.

This does not change the conclusion and it sharpens it. The real signal is
the part of the curve that runs *ahead* of the null, and the excess decays
monotonically from −22.7 to exactly 0, with the two conditions becoming
indistinguishable at **L27**. So the decision is not merely "completed" at
L24 — the late-layer read-out stops being distinguishable from a coin flip
against a meaningless token only in the last two layers.

The generalisable lesson is the same one as Finding 7, and it is now the
third time: **a statistic quoted without its baseline is not interpretable,
and the baseline here was not the one assumed.** 56% "looks like chance" and
is in fact 23 points worse than chance.

### 8b: the obvious summary statistic is an artefact

The first version of this section reported a "flip layer" — the first layer
where |gap| reaches 50% of the final gap — and the answer was **L0**, with
191 of 288 steps committing there. That is wrong, and the reason is visible
in the same table: L0's lens KL is 145, far above every other layer, and its
gap agrees with the final answer only 56% of the time. The gap is *large*
and *meaningless*, so the magnitude threshold fires on noise.

`flip_layer` is still reported, labelled as not a decision-depth measure.
The claim is made from the sign-agreement curve instead. This is the same
error as quoting a cosine without its floor (Finding 7): a statistic that
looks clean because it is dominated by an unfaithful regime.

### 8c: magnitude says nothing until the decision is made

The mean |gap| relative to the final gap sits at 88–110 from L2 through
L19 — the lens is moving the gap around, sometimes past the answer and
sometimes back — and only then rises to 139 at L20 and ~200+ from L22. So
the mid-stack is genuinely still deliberating rather than weakly
pre-committed. The two statistics disagree in an informative way: **sign
agreement crosses 80% at L20 while magnitude is only 1.4× the final gap
there.** What rises first is the *choice*, not the *conviction*.

## Finding 10: where the decision is visible is not where steering works

Finding 8 says the chosen-vs-runner-up gap only separates from a random-token
baseline in the last third of the stack. That is an observation about where a
*difference* lives, and the obvious extrapolation — that late layers are
therefore where you should intervene — is testable, and it is **wrong**.

`verify_decision_depth.py` injects the same `confidence_up` direction at
eight depths, each at **20% of that layer's own measured ‖h‖**, so no layer is
under-dosed relative to its own state. 24 AIME problems, 48 generated tokens,
greedy, dual-stream. `confidence_up` at 0.2 of the state norm:

| layer | depth | ‖v‖ (absolute) | mean logit KL | token agree | frac. problems diverged |
|---|---|---|---|---|---|
| 8 | 29% | 11.5 | 0.0815 | 0.9617 | 0.75 |
| 12 | 43% | 24.2 | 0.1716 | 0.9430 | 0.92 |
| 16 | 57% | 50.3 | **0.2080** | **0.9362** | 0.92 |
| 18 | 64% | 95.6 | 0.1884 | 0.9388 | **0.96** |
| 20 | 71% | 173.2 | 0.1091 | 0.9456 | **0.96** |
| 22 | 79% | 252.8 | 0.0579 | 0.9583 | 0.92 |
| 24 | 86% | 385.6 | 0.0553 | 0.9685 | 0.71 |
| 26 | 93% | 610.6 | 0.0374 | 0.9736 | 0.62 |

The control is exact: **all 192 strength-0.0 runs return token agreement
1.0, logit KL 0.0, and `first_diverged_step` None.** Nothing below is the hook.

### 10a: the prediction is refuted

Finding 8 put the decision at 71% of depth (L20 of 28). If that is where the
choice is made, late injection should beat early. Paired per-problem
contrasts over the same 24 problems:

| contrast | mean Δ KL | t(23) | pos/neg |
|---|---|---|---|
| L20 − L26 | +0.0718 | 5.40 | 24/0 |
| **L8 − L26** | **+0.0441** | **3.01** | 16/8 |
| L16 − L26 | +0.1706 | 6.03 | 23/1 |

The sign is wrong. **L8 is more effective than L26**, and L20 is more
effective than L26 by a hair-over-5 t-statistic with 24 of 24 problems
agreeing. The prediction is not merely unsupported — it is refuted with
consistent signs.

### 10b: the profile is a plateau, not a peak

Calling L16 "the peak" would overstate it. Against the plateau:

| contrast | mean Δ KL | t(23) | pos/neg | verdict |
|---|---|---|---|---|
| L16 − L12 | +0.0364 | 1.45 | 14/10 | **not separable** |
| L16 − L18 | +0.0196 | 0.53 | 13/11 | **not separable** |
| L16 − L8 | +0.1265 | 4.95 | 22/2 | significant |
| L16 − L20 | +0.0989 | 3.71 | 17/7 | significant |
| L16 − L24 | +0.1527 | 5.40 | 22/2 | significant |

L12–L18 is a flat optimum, and only its *edges* separate. The defensible
statement is that a broad band in the middle of the stack — 43%–64% of
depth — resists redirection far more than either the early stack or the
post-decision layers.

The three columns also disagree about where the maximum is, which is worth
stating rather than picking the flattering one: KL and token agreement peak
at L16, while "fraction of problems with any token divergence" peaks later
at L18–L20 (0.96). A perturbation at L16 changes *how much* the output
distribution moves; one at L18–L20 is more likely to change some token.

### 10c: what this does and does not explain

The late-layer weakness is **not** a dosing artefact, and this is checkable
from the table: L26 receives an absolute vector **12.1× larger** than L16
(610.6 vs 50.3) and produces **5.6× less** divergence. A larger perturbation
doing less means there is simply less computation left to convert a state
change into a different argmax — the decision is already formed.

The early-layer (L8) weakness **is** confounded with dose and this design
cannot separate them: L8's absolute vector is 4.4× smaller than L16's, so
"L8 is worse" may be "a smaller absolute perturbation is weaker" rather than
"perturbing early is worse". Separating them needs a fixed-absolute-dose
sweep across layers, which has not been run.

The structural lesson matches Finding 6 exactly. There, reading a direction
out at one layer and injecting it at another changed the effect by 2.15×;
here, the layer where the decision becomes *legible to a logit lens* sits at
71% of depth while the layer where a perturbation does the most *behavioural*
work sits at 43%–64%. **Attribution depth and intervention depth are
different quantities, and reading one off the other is a mistake in both
directions.**

## Finding 9: what the vector does to the reasoning

Every earlier finding measures intervention as a number on a distribution —
Δentropy, logit KL, token agreement. None of them looks at the reasoning
text, which is the thing a person reads and the thing a steering vector is
supposed to change.

`analyse_cot_divergence.py` reads the `primary_text` (steered) and
`shadow_text` (unsteered, teacher-forced on the same tokens) that
`run_intervention.py` has been persisting all along. The dual-stream
construction matters: because the shadow consumes the primary's own tokens,
a divergence in the text is not two streams wandering onto different
sentences — it is the same prefix carrying a different state.

Over the 168 runs already on disk (24 problems × 3 directions × strengths):

| direction | strength | diverged | median first-divergence | verbatim step overlap |
|---|---|---|---|---|
| confidence_up | 0.0 | 0/24 | — | 1.000 |
| confidence_up | +0.20 | **24/24** | char 56.5 | 0.060 |
| confidence_down | +0.20 | 23/24 | char 47.0 | 0.092 |
| sound_vs_flawed | −0.20 | 22/24 | char 8.5 | 0.104 |
| sound_vs_flawed | +0.20 | 24/24 | char 72.0 | 0.042 |
| *all three* | 0.0 | *0/72* | *—* | *1.000 (exact)* |

**The intervention rewrites the reasoning almost immediately.** The median
trace diverges within the first ~50 characters — the opening sentence of
the chain of thought — and the two traces share almost no reasoning steps
verbatim (overlap 0.04–0.10 against an exactly 1.000 control). This is not
a late divergence that propagates; the reasoning is different from its
first clause.

The zero-strength control is exact on all 72 runs — verbatim overlap
identically 1.000, token agreement identically 1.000 — so none of this is
the hook, the template, or the teacher forcing.

### 9a: the answer-level effect is not measurable, and effect sizes are
### length-dependent

Two results from a 1024-token rerun of the same 24 problems at the same dose
(`--max-new-tokens 1024`, 96 runs, `confidence_up` and `confidence_down` at
0 and 0.2):

**The answer-level effect cannot be measured at all.** Raising the budget
from 60 to 1024 tokens extended the mean reasoning body from 221 to 3,258
characters — the model was clearly thinking far longer — and `</think>` still
never closed: **0 of 96**. Only 12 of 96 runs contain any extractable number
at all. So this is not "the answer never changed"; it is "the answer never
appeared". The 9a section of the viewer says exactly that.

**Every effect size in this file is a function of generation length.** Same
dose, same problems, same direction:

| run | max tokens | token agreement | mean logit KL | verbatim overlap |
|---|---|---|---|---|
| short | 60 | 0.9399 | 0.1358 | 0.060 |
| long | 1024 | 0.9953 | 0.0005 | 0.592 |

The 6%-of-tokens-differ figure quoted in Findings 3b, 6 and elsewhere is
**specific to short generations**. The reason is not subtle: the opening
tokens of a chain of thought ("Okay", "So") are genuinely uncertain and are
divergent under steering, and in a 60-token window they are a large fraction
of the trace. Over 1024 tokens the model is mostly continuing reasoning that
is already determined, which a 20%-of-state-norm vector does not overturn.

So "the intervention changes 6% of tokens" and "the intervention changes
0.5% of tokens" are both true, of different runs. **Quoting an effect size
without the token budget is not a complete statement**, which retroactively
qualifies every agreement number in this document.

The reasoning-level effects survive this correction, because they are not
rate-based: the traces still diverge near their first clause, and the
divergence onset is a position, not a fraction.

## Reproducing

### Three traps that silently invalidate any new run

All three were hit while building the section above, and all three produce output that
looks entirely reasonable. (A third, the double-applied dose, was found
later and is written up as well — see below.)

**1. `SteeringRegistry` is uncalibrated until you ask.** `scaled()` calls
`layer_rms(layer)`, which returns a default of **1.0** for every layer
unless `load_layer_scales()` has been called. A strength of 0.2 then means
"a vector of length 0.2" rather than "20% of this layer's state" — on
Qwen3-1.7B at L20 that is 0.2 against a real ‖h‖ of 865.8, i.e. about
4000× too small, with no error and no warning. A fresh registry reports
`calibrated_layers() == []`.

`run_intervention.py` handles this (line ~364). Any new script must call it
too, and should assert it:

```python
n_cal = registry.load_layer_scales(Path("output/layer_profiles.json"))
assert n_cal, "uncalibrated: strength is not a fraction of the state norm"
```

The check that caught it: a run at L20 that printed `‖v‖ = 0.2` when every
earlier run at L20 printed `173.15`.

**2. A zero vector is the correct control, `None` removes it.** In
`run_dual_stream`, `shadow_ok = track_shadow and steer_vec is not None`.
Passing `None` therefore disables the shadow stream entirely — the control
is not measured, it is *absent*, and `summary()` comes back nearly empty
rather than reporting an error. The inert control is a real zero array,
which keeps the dual-stream path alive and returns KL exactly 0.000
(verified: 3 trials × 2 layers, token agreement 1.0, max divergence 1.8e-07).

Also relevant: `set_vector` does `.view(1, 1, -1)` on the array it is
given, so any later in-place scaling of that same buffer mutates a tensor
the steerer still holds. Build a fresh array per call.

**3. Two dose parameters means the dose gets applied twice.** This is the
subtlest of the three, and it did not raise an error — it just made every
effect 5× too small while the log line printed the intended norm.

The scan script had both `--strength` and `--frac-of-state-norm`. It built
`injected = vec * frac * ‖h‖` and then passed `injected * strength` to
`run_dual_stream`, so a run labelled "20% of the state" delivered 4%. The
printed `‖v‖ = 173.15` was the pre-multiplication value, matching the
historical runs exactly, which is precisely why it looked right.

It was caught by a cross-check, not by reading the code: the same layer and
the same nominal dose gave

| run | ‖v‖ reported | mean logit KL |
|---|---|---|
| `run_intervention.py`, L20, 0.2 | 173.1543 | **0.1606** |
| scan script, L20, "0.2" | 173.15 | **0.0042** |

a 38× gap on the same model, layer, norm and token budget. The fix was to
delete the redundant parameter so the dose has exactly one source of truth,
and to print `‖steer_vec‖` as it is handed over rather than a re-derivation
of it — the same rule `run_intervention.py` already follows with its
"report the norm actually injected" comment.

**The generalisable form: if a new tool disagrees with an existing one on
the same condition, believe the disagreement before the numbers.**
Everything about the scan run looked internally consistent.


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

# 4b. the same scan over the whole problem index, so the agreement and KL
#     columns are not one problem's worth of damage
python3 backend/examples/layer_scan.py \
    --model-path /path/to/Qwen3-1.7B \
    --direction confidence_up --norm 130 \
    --layers 4 8 12 14 16 18 20 22 24 26 \
    --problems-file /tmp/problem_index.json \
    --out backend/examples/output/intervention/layer_scan_24problems.json

# 5. does the extraction layer matter behaviourally? Extract the same
#    contrast at four layers, inject at one.
./scripts/run_extraction_layer_experiment.sh
python3 backend/examples/analyse_extraction_layer_effect.py --dir /tmp/iv_ext

# 6. every cross-layer cosine needs its null floor
python3 backend/examples/compare_extraction_layers.py --layers 8 14 20 24

# 6b. categorical vs continuous contrast, matched on sample size
python3 backend/examples/compute_steering_vectors.py \
    --layer 20 --matched-set --out-dir /tmp/steer3d_matched
python3 backend/examples/run_intervention.py \
    --model-path /path/to/Qwen3-1.7B \
    --vector-dir /tmp/steer3d_matched \
    --problems-file /tmp/problem_index.json \
    --directions cat_matched cont_matched caution creativity confidence_up reasoning_deep \
    --sweep 0.0 0.2 --layer 20 \
    --out backend/examples/output/intervention/matched_cat_vs_cont.json

# 7. what is inside a llama.cpp control-vector GGUF
python3 backend/examples/inspect_control_vectors.py --dir ~/test/vectors/Qwen3-1.7B
python3 backend/examples/diagnose_vector_signs.py --dir ~/test/vectors/Qwen3-1.7B

# 7b. use one - picks a layer, optionally repairs the per-layer sign
python3 backend/examples/gguf_to_npy.py \
    --gguf ~/test/vectors/Qwen3-1.7B/entry_05.gguf \
    --name sound_vs_flawed --layer 20 --sign-fix \
    --layer-profiles backend/examples/output/layer_profiles.json \
    --out-dir backend/examples/output/steering_vectors_user

# 7c. check the repaired vector actually behaves as a signed quantity
python3 backend/examples/run_intervention.py \
    --model-path /path/to/Qwen3-1.7B \
    --vector-dir backend/examples/output/steering_vectors_user \
    --problems-file /tmp/problem_index.json \
    --directions sound_vs_flawed --sweep -0.2 0.0 0.2 --layer 20 \
    --out backend/examples/output/intervention/antisymmetry_user_vector.json

# 8. publish to the UI
./scripts/publish_artifacts.sh
```

```bash
# 9. why THIS token and not the next one — logit-lens attribution.
#    float32 is required; bf16 zeroes the entire curve and the degeneracy
#    guard will say so. On a network filesystem copy the model to local
#    disk first and set HF_HUB_OFFLINE=1.
python3 backend/examples/attribute_token_choice.py \
    --model-path /path/to/Qwen3-1.7B \
    --problem-file backend/examples/output/problem_index.json \
    --limit 24 --steps 12 --mode layers \
    --out backend/examples/output/attr_qwen3_1p7b.json

# 9b. the decision-depth curve. Do not read the flip_layer field; see 8b.
#     The raw agreement curve has no 50% baseline, so the --null run is not
#     optional — see 8a-null.
python3 backend/examples/attribute_token_choice.py \
    --model-path /path/to/Qwen3-1.7B \
    --problem-file backend/examples/output/problem_index.json \
    --limit 24 --steps 12 --mode layers --random-alternatives 1 \
    --out backend/examples/output/attr_null_1p7b.json

python3 backend/examples/summarise_attribution.py \
    --json backend/examples/output/attr_qwen3_1p7b.json \
    --null backend/examples/output/attr_null_1p7b.json \
    --out backend/examples/output/token_attribution_1p7b.json

# 9c. what steering does to the reasoning text. Needs no GPU — it reads the
#     primary/shadow traces run_intervention.py already writes.
python3 backend/examples/analyse_cot_divergence.py \
    --json backend/examples/output/intervention/replication_24problems_L20.json \
    --out backend/examples/output/intervention/cot_divergence_summary.json

# 9d. where steering actually works, against the prediction from 8.
#     Note: one dose parameter only. A second one silently applies the
#     dose twice — see the traps above.
python3 backend/examples/verify_decision_depth.py \
    --model-path /path/to/Qwen3-1.7B \
    --problems-file /tmp/problem_index.json \
    --layers 8 12 16 18 20 22 24 26 \
    --frac-of-state-norm 0.2 --max-new-tokens 48 \
    --out backend/examples/output/intervention/vdd_final.json

# 9e. traces long enough to contain an actual answer. The runs above used
#     60 steps, which truncates every chain of thought before </think>.
python3 backend/examples/run_intervention.py \
    --model-path /path/to/Qwen3-1.7B \
    --problems-file /tmp/problem_index.json \
    --directions confidence_up confidence_down --sweep 0.0 0.2 --layer 20 \
    --max-new-tokens 1024 \
    --out backend/examples/output/intervention/cot_long_L20.json
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

Token agreement is nearly constant *across the four extraction layers*
(0.940–0.946, a range of 0.006) while logit KL doubles. But it is not
unchanged: every one of those is about 6% below the inert control's 1.0, and
that cost is the same at all four extraction depths. So the honest reading is
two separate facts, not one — the *distributional* divergence varies 2.15×
with where the vector was read out, while the *behavioural* cost of
disrupting the model does not vary at all. Which is a slightly weaker claim
than "the extra divergence is distributional", and a truer one: the deeper
extraction buys a larger change in the output distribution without buying a
larger change in which token the model picks, and without making the
disruption more damaging either.

## Finding 7: a cross-layer cosine has no meaning without its control

While checking the user's GGUF control vectors (below) it became clear that
the null floor for this family of statistics is not a constant, and quoting a
cosine without saying which control produced it is meaningless. Two
constructions, both balanced random splits, both legitimate, both measured on
this corpus — and they differ by a factor of 30:

| null construction | adjacent-layer floor | ≥4 layers apart | L0↔L27 |
|---|---|---|---|
| split the **global** pool in two | ~0.00 | −0.01 | +0.10 |
| split **within each trajectory** | **+0.87** | +0.38 | +0.10 |

The first is `matched_null` in `compute_steering_vectors.py`; the second is
`null` mode in `position_pooling_test.py`. The difference is not the sample
sizes, which are matched in both, but *where* the two halves are drawn from.
A within-trajectory split leaves both halves drawn from the same small set of
sequences, and the per-trajectory offsets that dominate a difference of means
therefore survive into both halves and cancel nowhere — they persist across
layers, giving a floor of 0.87. Drawing the two halves from the pooled
activations instead lets the between-trajectory structure cancel, and the
floor drops to ~0.

Both are correct controls for the thing they control. What is not acceptable
is the label: describing these as "balanced" versus "small subsets"
conceals the mechanism entirely, and that description is what an earlier
draft of this file used. A reader could not have known which floor applied to
which number.

The practical consequence: **the same number, 0.4, is either strong evidence
or pure noise depending on the control.** Finding 5's 0.395 is real because
it is measured against the first construction. Any cross-layer cosine
reported anywhere in this project now ships with its floor.

The same file also showed that **separation**, not cosine, is what actually
discriminates a real contrast — and, just as importantly, that the cosine
cannot be used to argue anything here. Extracting the self-check contrast
four ways on 27 trajectories, with a random-split null:

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

**This table cannot answer the question it was built to answer, and the
reason is the floor.** The real modes and the null differ by 0.03 on
adjacent cosine and by *nothing at all* on sign changes — all four rows
have zero. So the test has no power to distinguish a stable direction from
an unstable one, and "position pooling looks harmless" would be reading
signal out of noise.

This also **retracts an earlier hypothesis in this project.** The
`token_pos` flip in the user's files looked like a position-pooling failure,
so a natural experiment was run on our own data. I originally read it as
refuting the hypothesis — "all three pooling modes were equally stable". That
was wrong, and the table above is why: the real modes and the null are
indistinguishable on both statistics the test used, so it had no power in
either direction. An underpowered test reported as a negative result is the
same error as quoting a cosine without its floor. The flips are explained by a
per-layer sign decision (confirmed below), and position pooling remains
untested rather than cleared.

## Finding 11: 32k budget, and a number that looked like a result

Earlier sections ended with a structural impossibility: 0 of 96 traces closed
`</think>` inside 1024 tokens, so the answer-level effect of steering could not
be measured, and every agreement number was a statement about a chain that
never finished. That impossibility was an artefact of the budget, not a fact
about steering. This finding reopens it — and the answer turns out to be
"still not measurable", for a reason worth more than the one it replaces.

### Calibration first, because the budget cannot be guessed

`run_32k_study.py` runs three phases in a fixed order, and the middle one
exists because the first one failed to be interesting often enough to guess
around. Phase A generates unsteered with a 32 768 budget and records the step
at which `</think>` closes:

| problem | `</think>` closed at |
|---|---|
| 1983 | 3037 |
| 1984 | 5658 |

Phase B sets the measurement budget to `5658 × 1.15 = 6507` steps — sized
from the measurement, not chosen. Both numbers land inside 32k, so the
structural block is gone: **chains do close, they just need thousands of
tokens, and 1024 was never enough to find out.** Phase C then runs both arms
at 6507.

### The instrument is exact

The zero-vector control is the check that makes any of the rest readable:

| control arm | agreement | mean KL | first divergence |
|---|---|---|---|
| 1983 | 1.0000 | 0.00000 | none |
| 1984 | 1.0000 | 0.00000 | none |
| 1985 | 1.0000 | 0.00000 | none |
| 1986 | 1.0000 | 0.00000 | none |
| 1987 | 1.0000 | 0.00000 | none |
| 1988 | 1.0000 | 0.00000 | none |

6 of 6, exact — bit-identical token streams, not "close". A shadow fed a
zero vector reproduces the primary step for step, so every difference reported
below is attributable to the injection and not to the measurement apparatus.

### What the steered arm does

| problem | control | steered | agreement | mean KL | first divergence |
|---|---|---|---|---|---|
| 1983 | 3792 steps, closed | 3409, closed | 0.9235 | 0.1136 | 26 |
| 1984 | 6311, closed | 6506, **open** | 0.9199 | 0.1099 | 14 |
| 1985 | 6506, open | 6506, open | 0.9802 | 0.0340 | 3 |
| 1986 | 3941, closed | 6506, **open** | 0.9556 | 0.0707 | 22 |
| 1987 | 6506, open | 6506, open | 0.9139 | 0.1330 | 43 |
| 1988 | 6506, open | 6506, open | 0.9619 | 0.0712 | 15 |

Two things are established. **Divergence is early** — first disagreement at
step 3 to 43, median 18.5, out of sequences up to 6506 long. And **the effect
decays with length**: the same dose and the same problems gave 0.995 / 0.0005
at 1024 tokens (Finding 9a) and give 0.9425 / 0.0887 here. This is the same
budget-dependence the earlier sections carry, now extended 6× further along
the curve, and it is a caution against reading any short-budget agreement
number as a property of the intervention rather than of the budget.

### The answer-level effect: still not measurable

| | chain closed | answer usable |
|---|---|---|
| control | 3 / 6 | 3 / 6 |
| steered | 1 / 6 | 1 / 6 |

Fisher exact **p = 0.55**. The direction of that gap is suggestive — the
steered arm leaves `</think>` open on both problems whose control chain closed
— but n = 6 supports nothing, and the honest reading is that **at 6506 steps
this model on AIME usually does not finish deliberating**, so the question
"did the intervention change the answer" is still not reachable. Exactly one
problem (1983) has a usable answer on both arms, and it agrees: 60 → 60. One
agreement out of one comparison is not a result.

Any statement of the form "steering makes the model reason longer" has to be
handled with the same care. The steered arm produces more characters on 3 of 6
problems, but 5 of 6 steered chains were forced to run the full 6506 steps
while 3 of 6 control chains stopped early — the extra length is largely the
mechanical consequence of not closing, not a measured behavioural effect. The
only problem where both arms closed is 1983, at 7507 → 6988 characters:
n = 1.

### The number that looked like a result

The summary table for 1987 reads:

```
1987_I_1  control_zero        closed=False  answer=1
1987_I_1  confidence_up@0.2   closed=False  answer=2
```

*"The intervention moved the answer from 1 to 2."* That is a clean,
attractive, publishable sentence, and **both numbers are noise.** (1988 is
the same shape: 0 and 0, both scraped from unclosed chains. They happen to
match, which is why it is the one that did not get noticed.)

`extract_answer` tries `ANSWER_RE`, then `BOXED_RE`, then `TAIL_INT_RE` — the
last integer in the text. Neither arm closed `</think>`, so the answer segment
is empty, so the rule that fires is the third one, applied to a *truncated
derivation*. The 1 and the 2 are intermediate quantities from the middle of
each chain's reasoning.

Nothing flagged it. `answer_known` was `True`, because the fallback returns an
integer rather than `None`. `answer_changed` was `False`, because that field
compares primary against shadow *within one run* — it never looks across
arms, so a cross-arm difference is invisible to it. Both values sit inside
AIME's 0–999 range. And the divergence statistics on that row are among the
healthiest in the table (agreement 0.9139, KL 0.1330), which reads as
corroboration rather than as a warning.

The fix, now in `analyse_cot_divergence.extract_answer_sourced`, is that
extraction reports which rule fired (`explicit` / `boxed` / `tail_guess` /
`unclosed_guess`), and `_answer_of(..., strict=True)` refuses the fallback
entirely. `strict` defaults to `False` so existing callers are unaffected; the
measurement path uses it, and `answer_known` is now False whenever the value
was guessed. The run that produced this table did not persist its raw text, so
the 1 and the 2 cannot be traced back to what they actually were — which is
the second half of the lesson: **an answer extracted by regex from generated
text is a derived quantity, so the text has to be kept.** `--save-text` exists
and was off.

### A third fix, from a field name

The same table reports `n_bad_steps: 0` next to `token_agreement: 0.9386`,
which cannot both be true of divergence, and reading it as "the arms never
diverged" would be a mistake. `n_bad` counts steps whose KL or entropy came
out non-finite — numerical garbage, not disagreement. It is renamed
`n_bad_numeric_steps` with an inline `n_bad_meaning` string, because a field
name that reads like the neighbouring statistic will eventually be read as
that statistic.

The run also kept the per-step match bits in memory and dropped them from
`summary()`. That is the series that would answer the most interesting
question here — whether a 6% disagreement rate over 6507 steps means the
perturbation compounds into a different derivation, or flips a few tokens
early and the chains re-synchronise. A mean of 0.9386 is consistent with both.
814 bytes of payload was not a reason to discard it. It is persisted now and
round-trip tested in `--self-test`; `run_paired_steering.py` additionally
stores both token streams in full, so the question is answerable without
re-running this study.

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

   **Scope of the damage.** This is a *between*-layers fault, so it does
   not by itself corrupt a single-layer injection — applying only
   `direction.20` at L20 uses one layer's sign and is unaffected. It
   bites where a control vector is actually used that way: applied across
   a range of layers, which is what llama.cpp does with these files;
   aggregated across layers, which `gguf_to_npy.py --all-layers` does for
   a layer scan; or compared across files, where "the sound direction"
   would not mean a consistent thing. For those uses the fix is not
   cosmetic — a vector whose sign alternates with depth is applying a
   perturbation at some layers and its negation at others, and the two
   roughly cancel.

   The extraction code is `~/test/steer/extract/extract_vectors.py`, which
   delegates to a library object via `cv.export_gguf()`. Which line
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
   `reasoning_deep` **extracted at L20** runs 1.1×–2.7× the random floor
   √(2/π·2048) = 0.018: mean |cos| 0.010–0.036, with entry_04 at 0.010
   (below the floor) and entry_01 at 0.027 (1.5×). An earlier draft called
   this "at the random floor", which overstates it — the code's own bands
   call anything under 2× "unrelated" and 2–3× "barely related", and half
   these files fall in the second band. The honest summary is: **no
   relationship strong enough to call them the same concept, and none
   strong enough to call them provably unrelated either.** They should be
   chosen between on which contrast is wanted, not treated as two versions
   of a reasoning direction.

   The layer matters to this comparison and is easy to get wrong. The
   comparison is against a single `reasoning_deep` vector extracted at L20,
   dotted against all 28 of the GGUF's per-layer directions. That answers
   "is any layer of this file aligned with our L20 direction", which is
   what was asked; it does not answer "is this the same concept", and a
   contrast could score well simply by peaking at a different depth. An
   earlier run of this same comparison against an L14-extracted
   `reasoning_deep` gave a different range (0.020–0.048) — the same
   verdict, but a reminder that the number is a function of which
   extraction it is compared against.

`gguf_to_npy.py` exports any of these into the registry's format, picking a
layer, optionally applying the sign fix, and reporting the before/after. The
scale still has to come from outside the format:
`--layer-profiles layer_profiles.json`, and the UI will otherwise show the
direction as uncalibrated.

### The sign fix is validated behaviourally

A static cosine profile shows the stored vectors are internally inconsistent
after the repair. That does not by itself show the exported vector *works*,
so it was checked by injection: the sign-fixed `sound_vs_flawed` at L20,
strengths −0.2 / 0.0 / +0.2, over the same 24 problems. 72 counterfactual
runs.

| strength | Δentropy (primary − shadow) | logit KL |
|---|---|---|
| −0.2 | −0.01363 | 0.0611 |
| 0.0 | +0.00000 (exactly, all 24) | 0.0000 (exactly) |
| +0.2 | **+0.02255** | 0.0485 |

**The sign is real.** Adding the vector raises the shadow stream's entropy
and subtracting it lowers it, with the two effects in opposite directions on
**19 of 24 problems (exact sign test p = 0.0066)**, paired t(23) = 5.55. So
once the convention is fixed, the exported vector is a signed quantity whose
sign determines the direction of the effect — which is the property that
makes it usable, and the alternating per-layer sign would have destroyed it.

Two things this does *not* show:

- **The magnitudes are not established as asymmetric.** 0.0226 against 0.0136
  is a 1.65× ratio in the same direction as the confidence pair's 1.9×, but
  the test that matters — a one-sample test on the sum of the per-problem
  effects — gives p = 0.18. Same verdict as Finding 3b: a difference
  between two means, not an established nonlinearity.
- **Logit KL is the wrong quantity for this test and must not be used here.**
  KL is a divergence and is non-negative by construction, so +v and −v both
  produce it, and the "opposing signs on 0/24" an antisymmetry check
  reports for it is a property of the metric rather than of the vector.

The format itself is fine; the extraction behind it is where the work is.
Extracting at the injection layer (Finding 6), from hundreds of pairs rather
than tens, with the per-layer sign taken from a fixed convention rather than
per-layer, are the three changes that would most improve these vectors.

## What is not established

- **Finding 8 measures the runner-up, not the whole distribution.** The
  sign-agreement curve compares the chosen token against its top-1
  alternative. A step where the top-4 are nearly tied would look decisive
  under this statistic and ambiguous under any measure of the full
  distribution. The margin distribution is reported beside it (median 12.3
  and 12.7, minimum 0.51 and 0.60) so the hard steps are visible, but the
  curve is not a statement about the whole vocabulary.
- **The null exists only for Qwen3-1.7B.** The random-alternative control
  (8a-null) was run at one model size. The 4B and 8B excess-over-null
  curves are not measured, so the claim that the late rise is *relative to
  a null* is established at 1.7B only. Their raw curves are in the tables
  above and their baselines are not.
- **Finding 10 cannot separate "early is weak" from "small absolute dose is
  weak."** The dose is proportional (20% of each layer's own ‖h‖) so no layer
  is under-dosed *relative to its state*, but the absolute vectors still span
  11.5 to 610.6. The late-layer result is safe — L26's absolute dose is 12×
  L16's and its effect is 5.6× smaller, so dose cannot explain that. The
  early-layer result is not safe: L8's absolute dose is 4.4× smaller than
  L16's. A fixed-absolute-dose sweep is what would settle it.
- **Finding 10 is one direction, one strength, one model.** The profile is
  measured for `confidence_up` at 0.2 on Qwen3-1.7B. Whether the plateau
  sits at 43–64% of depth on 4B/8B, or for other directions, is untested —
  and Finding 8's cross-model result showed absolute layer indices do not
  transfer, so the depth fraction is the only thing worth comparing.
- **Findings 8 and 9 do not establish causality.** Both are
  observational: the lens describes where a decision is visible, and the
  CoT divergence describes that steering changes the trace. Neither shows
  that intervening at the identified layer would change the decision.
  Finding 10 is the experiment that connects them, and its answer was
  negative — intervening where the decision is legible is *not* where
  steering works best.
- **The answer-level effect of steering is not measured** (Findings 9a and
  11). At 60 steps the traces contain no completed chain of thought; at
  1024 tokens 0 of 96 traces close `</think>`. Raising the budget to 32k and
  sizing it from a calibration run (Finding 11) does reopen the question —
  chains do close, at 3037 and 5658 steps — but 3 of 6 control chains still
  fail to close inside 6506 steps, so exactly one problem has a usable answer
  on both arms. The effect remains unmeasured, now for a different and
  more interesting reason: not that the budget is too small to ever reach an
  answer, but that this model on AIME spends several thousand tokens of
  deliberation and the intervention is small.
- **The 32k study is 6 problems, and its one interesting contrast is not
  significant** (Finding 11). 3/6 control chains close versus 1/6 steered,
  Fisher exact p = 0.55. It is reported as a hypothesis — "the confidence
  direction may lengthen deliberation" — and nothing more. The per-step
  match bits that would separate compounding divergence from early
  divergence followed by re-synchronisation were not persisted by the run
  that produced these numbers; the accumulator kept them in memory and
  `summary()` dropped them. The fix is in `_LongAccumulator.summary()` and
  is exercised by `--self-test`, and the paired collection
  (`run_paired_steering.py`) records both token streams in full, so the
  question becomes answerable without re-running this study.
- **Every agreement and KL number in this file is tied to a token budget**
  (Finding 9a). 60 tokens gives 0.94 / 0.136; 1024 gives 0.995 / 0.0005 for
  the same dose and the same problems. The short-budget numbers were used
  throughout the earlier sections and are quoted there without the budget;
  they should be read as "at 60 tokens".
- **Findings 2 and 4 are single-prompt.** The dose-response shape and the
  L12 destruction cliff both rest on n = 1. What carries over from the
  corpus is the layer geometry underneath them — the 80× growth and the
  measured per-layer norms are averaged over 48 trajectories — not the
  behavioural columns.
- **Effect sizes are small and per-problem variance is large.** The
  confidence direction moves mean entropy by 0.012–0.022 nats and costs
  ~6% token agreement. Individual problems range from −0.072 to +0.040, so
  a single run predicts almost nothing. The n = 24 result establishes that
  the *mean* effect is real, not that any individual run is predictable.
- **Why `caution` and `creativity` degrade is still unexplained.** The
  categorical-vs-continuous explanation has been tested and refuted above.
  What is left is the open question: both point away from the confidence
  axis (cos −0.54 and −0.84 against +1.83 for `confidence_up`), so part of
  what looks like "damage" may simply be a direction that is further from
  wherever the model's distribution is heading, rather than a harmful
  state. Nothing here separates those.
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
Finding 7: the floor ranges from ~0 to ~0.87 depending on whether the
control splits the global pool or splits within each trajectory, so the bare
number is not interpretable on its own.

Ten claims in earlier drafts of this file did not survive checking and
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
3. That the fragility of `caution` and `creativity` is explained by their
   being built from categorical token sets. Tested with a matched pair
   differing only in the kind of split: the predicted direction appears
   (+26.7%, 18/24 problems) but is not significant (p = 0.15), and the
   group means run the wrong way because `confidence_up` is continuous and
   the most damaging direction of the six. Refuted.
4. That pooling the contrast over token positions destabilises the
   extracted direction, offered as the explanation for the sign flips in
   the user's GGUF vectors. The test meant to check it **could not have
   detected the effect in either direction**: all three pooling modes and
   the null all show zero sign changes, and adjacent cosine 0.899 / 0.903
   / 0.906 against a null of 0.873. I originally wrote that pooling "does
   not" destabilise the direction. That was an underpowered test reported
   as a negative result, which is the same error as reporting a bare
   cosine without its floor. The flips are explained instead by a per-layer
   sign decision, confirmed by sign-aligning from L0 and recovering a
   smooth profile in every affected file — but position pooling remains
   untested rather than exonerated.
5. That the 1.9× up/down asymmetry shows the response is nonlinear. It does
   not follow: the paired t(23) = −4.72, p = 0.00009 quoted in its support
   tests whether the average effect is non-zero, which comes out
   significant even if the two sides are exactly symmetric. The test
   nonlinearity requires is a one-sample test on the *sum* of the
   per-problem effects, and that gives t = 1.80, p = 0.085. The sign-fixed
   user vector shows the same pattern (1.65×, p = 0.18). Both are now
   described as a difference between two measured means.
6. That the token decision is made at L0. It is not, and the statistic that
   said so was measuring the wrong thing: the "flip layer" fires on
   |gap| ≥ 50% of the final, and L0's gap is large *and* uninformative
   (lens KL 145 against ≤12 everywhere else; sign agreement 56%, i.e. a
   coin flip). 191 of 288 steps "committed" at a layer that is measurably
   guessing. Replaced by the sign-agreement curve, which puts the decision
   at 71–83% of depth. The failure is the mirror image of the earlier ones:
   there, a real signal was reported without its floor; here, a large
   unfaithful number was read as a confident one.
7. That a flat attribution curve meant a stable decision. It meant the
   opposite — bf16 had collapsed the unembedding, and the first version of
   the lens reported a perfectly flat, perfectly consistent `0.000` gap at
   every layer. Smoothness is not fidelity; `attribute_token_choice.py` now
   raises on a degenerate lens rather than reporting it.
8. That the early layers' 56% agreement was "near chance". It was 23
   points *below* the measured null (8a-null), because a random token's
   sign is settled early and confidently. An assumed 50% baseline was
   wrong by a wide margin, and the correct reading — the early stack is
   mildly anti-aligned with the eventual answer — is the opposite of the
   one originally written.
9. That the decision-depth curve rises monotonically. It does so for
   Qwen3-1.7B and Qwen3-4B. Qwen3-8B falls from 74% at L20 to 61% at L24
   — four standard errors, so a real departure, not noise. Reported as
   such rather than smoothed into agreement with the other two.
10. That because the decision forms at L20–L24, steering there is most
    effective. This was my own stated prediction and it is refuted
    (Finding 10): the most effective band is L12–L18, at 43–64% of depth,
    and L8 beats L26 with t = 3.01 while L20 beats L26 with 24 of 24
    problems agreeing. A logit lens showing you where a decision lives is
    not a recommendation about where to intervene.
11. That problem 1987's answer moved from 1 to 2 under the intervention
    (Finding 11). It did not, and the two numbers were never answers. Both
    arms left `</think>` unclosed, and the extractor's last-resort rule —
    "take the last integer in the text" — scraped an intermediate quantity
    out of each truncated derivation. Every guard that should have caught
    this passed: `answer_known` was True, both values sat inside AIME's
    0–999 range, and the divergence statistics were healthy. Extraction now
    reports *which* rule fired, and the measurement path refuses to read an
    answer out of an unclosed chain.

