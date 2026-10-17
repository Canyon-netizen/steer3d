# Steering design guide (steer3d.steering_design/1)

Readout is positive for all 7 marker ids, but the measured +v effect on correctness is -0.06641 at the primary dose. Block 20 supports that negative effect; block 25 compensates it. The current vector is a readout direction, not a validated control direction. Hidden-state atlas: best layer 21, raw cos AUC 0.1991, orientation -1 (w·h is anti-aligned with marker positions).

> This is a **descriptive** guide built from existing artifacts. It does not rerun the model.

## Layer strategy

| layer | block | restore | support | compensation | same-sign block/restore | action | random rank |
|---:|---:|---:|---:|---:|---|---|---:|
| 20 | -0.04967 | -0.04533 | +0.04750 | -0.04750 | 5/6 / 5/6 | supporting | 2/5 |
| 21 | +0.03465 | +0.03723 | -0.03594 | +0.03594 | 4/6 / 5/6 | compensating | 2/5 |
| 22 | -0.00784 | -0.00723 | +0.00753 | -0.00753 | 4/6 / 4/6 | weak | 4/5 |
| 23 | +0.00629 | +0.00962 | -0.00796 | +0.00796 | 3/6 / 3/6 | weak | 4/5 |
| 24 | +0.02635 | +0.02774 | -0.02704 | +0.02704 | 6/6 / 6/6 | compensating | 2/5 |
| 25 | +0.08236 | +0.08939 | -0.08588 | +0.08588 | 6/6 / 6/6 | compensating | 2/5 |
| 26 | -0.00852 | -0.01217 | +0.01035 | -0.01035 | 4/6 / 4/6 | weak | 4/5 |
| 27 | -0.00673 | -0.00816 | +0.00745 | -0.00745 | 5/6 / 5/6 | weak | 4/5 |

## Dose / direction

| dose | w+ | w- |
|---:|---:|---:|
| 0.02 | -0.01600 | +0.01768 |
| 0.1 | -0.06641 | +0.10387 |
| 0.25 | -0.16295 | +0.30337 |

random primary: -0.02005

## Hidden-state readout atlas

- best layer: **21**
- raw cos AUC: 0.1991; oriented cos AUC: 0.8009; orientation: -1
- norm control AUC: 0.5632; residualised raw AUC: 0.1927
- 384 markers / 30 trajectories; negative orientation in 24/24 trajectories with both classes
- chance level: 0.5; this is descriptive, not a significance test

| marker | n | best layer | raw cos AUC | orientation |
|---|---:|---:|---:|---:|
| 6771 | 119 | 27 | 0.1453 | -1 |
| 7196 | 105 | 17 | 0.7305 | 1 |
| 10061 | 70 | 21 | 0.1620 | -1 |
| 14190 | 46 | 19 | 0.3690 | -1 |
| 13824 | 34 | 27 | 0.0725 | -1 |
| 88190 | 6 | 18 | 0.0297 | -1 |
| 80022 | 4 | 9 | 0.0197 | -1 |

## Construction probe

- 6 sites; alpha rule: 0.1 * measured block-20 input L2 norm at the last prefix position

| marker | n | mean delta w | mean delta g | mean delta w+g | best |
|---|---:|---:|---:|---:|---|
| 10061 | 2 | 0.1254 | 0.3643 | 0.3527 | gradient |
| 6771 | 2 | 0.1215 | 0.3419 | 0.3418 | gradient |
| 7196 | 2 | -0.0083 | 0.0159 | 0.0158 | gradient |

## Held-out transfer

| marker | w | mean g | sparse g | oracle g |
|---|---:|---:|---:|---:|
| 10061 | 0.0192 | 0.4363 | 0.3801 | 0.4729 |
| 6771 | 0.1314 | 0.1958 | 0.1942 | 0.1959 |
| 7196 | 0.1026 | 0.6514 | 0.6113 | 0.6686 |

Cross-marker mean-g transfer (source row -> target column):
- 10061 -> 6771 0.1952, 7196 0.3172
- 6771 -> 10061 0.3085, 7196 0.2576
- 7196 -> 10061 -0.4574, 6771 -5.7108

## Alpha / side-effect sweep

| marker | useful direction | dose | mean delta | mean KL |
|---|---|---:|---:|---:|
| 10061 | mean_g | 0.02 | 0.2005 | 0.0851 |
| 6771 | w | 0.1 | 0.1314 | 0.0850 |
| 7196 | sparse_g | 0.02 | 0.2639 | 0.0734 |

## Compiled recipe

| marker | direction | dose | expected delta | expected KL | verified delta | verified KL | file |
|---|---|---:|---:|---:|---:|---:|---|
| 10061 | mean_g | 0.02 | 0.2005 | 0.0851 | 0.2005 | 0.0851 | experiments/steering_recipe_v1/vectors/10061_mean_g.npy |
| 6771 | w | 0.1 | 0.1314 | 0.0850 | 0.1314 | 0.0850 | experiments/steering_recipe_v1/vectors/6771_w.npy |
| 7196 | sparse_g | 0.02 | 0.2639 | 0.0734 | 0.2639 | 0.0734 | experiments/steering_recipe_v1/vectors/7196_sparse_g.npy |

## Recommendations

- **[high] define_target** (global, measured): The vector is readable for the marker set but its measured causal effect is on multiplication correctness, and that effect is negative at the primary dose. Designing from w·U alone would optimise the wrong readout.
  - freq-weighted w·U = +0.18424, 7/7 marker ids positive
  - +v primary effect on correctness score = -0.06641
- **[high] avoid_positive_injection** (layer 20, measured): Block-20 units move with the vector's net (negative) effect: restoring them during +v lowers the score further, and restoring them into baseline lowers it too. Injecting +v at this layer pushes the measured readout the wrong way for a correctness target.
  - block -0.04967, restore -0.04533, support +0.04750
  - net +v effect at dose 0.1 = -0.06641
- **[high] test_compensator_removal** (layer 25, descriptive): Block-25 units oppose the vector's net effect: restoring them during +v raises the score, and restoring them into baseline also raises it. This is the first layer to test for removal / sign flip before building a new direction.
  - block +0.08236, restore +0.08939, compensation +0.08588
  - same-sign block/restore = True; random rank 2/5
- **[low] do_not_use_as_lever** (global, measured): These layers have no layer-specific block/restore effect above the floor; do not present them as a mechanism without new measurements.
  - weak layers: 22, 23, 26, 27
- **[high] choose_direction_by_sign** (global, measured): The effect reverses with the sign of the injected direction and grows with dose. For a correctness target the current +v is the wrong sign at the primary dose; -v is positive at every tested dose.
  - w+ primary -0.06641; w- primary +0.10387; random primary -0.02005
  - w+ at dose 0.02: -0.01600; w- at dose 0.02: +0.01768
- **[medium] condition_on_wording** (global, measured): The sign of the effect depends on wording and equation truth. Fix the target wording before comparing vectors or doses.
  - correct/neutral +0.10610; correct/self-check -0.25971; incorrect/neutral -0.13528; incorrect/self-check +0.02324
- **[high] do_not_treat_marker_set_as_one_concept** (global, measured): Readout is positive for all markers, but the injection effect depends on which marker token is present. The dominant marker is suppressed by +w in the original marker-steering report, so the set average is not a single control target.
  - dominant marker id 7196: w·U +0.17920, share 0.251
  - marker-steering report: +w suppresses the dominant marker while raising the others
- **[high] do_not_use_cos_h_w_as_positive_readout** (layer 21, descriptive): The hidden-state atlas finds its best marker separation at layer 21, but the orientation is negative: marker next-token positions have LOWER cos(h,w) (raw AUC 0.1991; oriented AUC 0.8009). This holds in 24/24 trajectories with both classes. The static w·U readout therefore does not transfer to a positive state-space projection; do not select layers or units by w·h.
  - best layer 21: raw cos AUC 0.1991, oriented cos AUC 0.8009, orientation -1
  - norm control AUC 0.5632; residualised raw AUC 0.1927
  - n_marker=384, n_trajectories=30
- **[high] split_marker_directions_by_sign** (global, descriptive): Per-marker readout resolves the set-level anti-alignment: marker 7196 (n=105) is positively oriented at layer 17 (raw cos AUC 0.7305), while marker 13824 is the strongest negative (n=34, layer 27, raw cos AUC 0.0725). The set-level AUC hides this sign split. A single direction/sign cannot positively read all seven; pick the target marker and build its own direction and layer.
  - marker 6771: n=119, best layer 27, raw cos AUC 0.1453, orientation -1
  - marker 7196: n=105, best layer 17, raw cos AUC 0.7305, orientation 1
  - marker 10061: n=70, best layer 21, raw cos AUC 0.1620, orientation -1
  - marker 14190: n=46, best layer 19, raw cos AUC 0.3690, orientation -1
  - marker 13824: n=34, best layer 27, raw cos AUC 0.0725, orientation -1
  - marker 88190: n=6, best layer 18, raw cos AUC 0.0297, orientation -1
  - marker 80022: n=4, best layer 9, raw cos AUC 0.0197, orientation -1
- **[low] do_not_adjudicate_small_n_markers** (global, measured): These markers have fewer than 10 occurrences in the 30-trajectory atlas; their per-marker AUC is not adjudicable and must not be used to choose a direction.
  - small-n markers: 88190, 80022
- **[high] use_gradient_direction_as_constructive_baseline** (layer 20, measured): On 6 short AIME prefixes, the normalized local gradient g = d log p(marker) / d h at layer 20 improved the target on every site and was the best candidate for all tested markers; w was negative for 7196 and weaker for 10061/6771, and w+g matched g. Use g as the constructive baseline, then audit native units.
  - marker 10061: mean delta w +0.12541 (improved 1.00), gradient +0.36427 (improved 1.00), n=2
  - marker 6771: mean delta w +0.12154 (improved 1.00), gradient +0.34194 (improved 1.00), n=2
  - marker 7196: mean delta w -0.00828 (improved 0.50), gradient +0.01589 (improved 1.00), n=2
- **[medium] treat_unit_decomposition_as_diagnostic** (global, descriptive): The per-unit decomposition is first-order and its sum-to-measured ratio varies across sites; the quadrants are useful for diagnosing carriers vs compensators, but they are not a validated mediation percentage, and naive removal of write-direction components failed in the prototype.
  - see experiments/steering_construction_v1/steering_construction.json decomposition.ratio
  - gradient is a white-box local direction; it is not a semantically named steering vector
- **[high] use_per_marker_mean_gradient_on_heldout** (layer 20, measured): A mean gradient built on calibration sites per marker improved held-out f on all tested markers and retained most of the per-site oracle effect; w was much weaker (and negative for 7196). The cross matrix shows the 7196 direction is negative for other markers while 10061/6771 directions are positive for all, so at least 7196 needs its own direction. Use per-marker mean g as the construct, with sparse g as the interpretable variant.
  - marker 10061: w +0.01922, mean g +0.43629, sparse g +0.38007, oracle +0.47286 (held-out n=2)
  - marker 6771: w +0.13136, mean g +0.19575, sparse g +0.19417, oracle +0.19594 (held-out n=2)
  - marker 7196: w +0.10259, mean g +0.65144, sparse g +0.61133, oracle +0.66858 (held-out n=2)
  - cross: 7196 mean g on 10061 -0.45743, on 6771 -5.71084; 10061 mean g on 7196 +0.31719
- **[medium] sparse_direction_retains_effect** (global, descriptive): Keeping only the top 10% of mean-gradient coordinates (sparse g) retained 78-100% of the held-out effect in this probe. It is a candidate for a more interpretable direction, but it is still a white-box local average, not a semantic vector.
  - see experiments/steering_transfer_v1/steering_transfer.json same_marker.*.g_sparse
- **[high] choose_direction_and_dose_by_kl_frontier** (layer 20, measured): The sweep makes the effect/side-effect tradeoff explicit: mean g reaches the largest delta log p but with large KL and entropy drop; sparse g has lower KL at the same dose; w is safest but weaker. Under a mean-KL budget of 0.1 the useful windows differ by marker, so do not use one direction/dose for all markers. Pick the window per marker, then verify side effects on more sites.
  - marker 10061: useful mean_g @ 0.02 (df +0.2005, KL 0.0851); at dose 0.05 mean g KL 0.3719 vs sparse g KL 0.2037
  - marker 6771: useful w @ 0.1 (df +0.1314, KL 0.0850); at dose 0.05 mean g KL 0.4504 vs sparse g KL 0.2480
  - marker 7196: useful sparse_g @ 0.02 (df +0.2639, KL 0.0734); at dose 0.05 mean g KL 0.6719 vs sparse g KL 0.3661
- **[medium] sparse_g_reduces_side_effect** (global, descriptive): At the same dose, sparse g (top 10% of mean-gradient coordinates) gives a lower global KL than dense mean g while retaining most of the target effect. It is a candidate for a more interpretable, lower-side-effect direction, but still a local white-box average.
  - see experiments/steering_sweep_v1/steering_sweep.json aggregate.*.directions.mean_g / sparse_g
- **[high] compiled_recipe_available** (layer 20, measured): One compiled .npy vector per marker is available, with the direction/dose chosen from the KL-budgeted sweep and a held-out verification. Treat it as a reproducible starting point: the verification reuses the transfer/sweep held-out sites, not a third independent split, and the files are local white-box directions rather than semantic production vectors.
  - marker 10061: mean_g @ dose 0.02 -> experiments/steering_recipe_v1/vectors/10061_mean_g.npy; verified mean delta +0.2005, mean KL 0.0851 (n=2)
  - marker 6771: w @ dose 0.1 -> experiments/steering_recipe_v1/vectors/6771_w.npy; verified mean delta +0.1314, mean KL 0.0850 (n=2)
  - marker 7196: sparse_g @ dose 0.02 -> experiments/steering_recipe_v1/vectors/7196_sparse_g.npy; verified mean delta +0.2639, mean KL 0.0734 (n=2)
- **[medium] do_not_use_readout_axis_blindly** (global, measured): The only readout axis that beats the position control is confidence, and it is marked tautological (its target is a restatement of top-1 probability). There is no specific, non-circular readout axis to steer by yet.
  - confidence axis: status=tautological, layers beating control 3/3
- **[medium] prefer_late_layers_for_answer** (global, measured): The final token only becomes linearly decodable late: mean p_final is near zero through the early layers and rises sharply after block 18. Early-layer injections must be verified with the readout atlas before being called answer-steering.
  - mean p_final layer 0 0.00019 -> layer 18 0.12629 -> layer 27 0.93604
  - logit-lens steps = 1536
- **[high] replicate_before_building** (global, measured): All layer/unit effects above are from six held-out multiplication problems, one model, one vector, and are descriptive. Treat them as hypotheses for the next measurement, not as a construction recipe.
  - n_evaluation_problems = 6; single model; single vector; per-unit causal alignment not measured

## Unmeasured

- per-unit causal alignment: gradient of the target readout with respect to each unit product, dotted with its write direction
- control direction: solve C v = a for a requested high-level effect instead of reusing a readout direction
- token-composition-matched control: swap the marker token at a fixed position and re-measure
- second model and second vector: external validity of the layer/compensation pattern
- closed-loop controller: recompute the direction per generated token instead of one fixed injection
- marker-specific steering vector: one direction per marker instead of a frequency-weighted set average

## Warnings

- This report is descriptive, not a validated construction recipe. The measured label means the number exists in the source artifact, not that the effect is statistically significant.
- Readout (w·U on the marker set) and causal effect (correctness score on held-out multiplication problems) are different targets; do not treat one as evidence for the other.
- Block/restore effects are group-level. The unit table is a response ranking, not a causal ranking.
- The marker-steering artifact reports selfcheck_passed=false (one Q3 check had no criterion); its readout numbers are usable but its verdict block is not a clean pass.
- The readout atlas keeps per-marker rows: best layers and orientations differ across markers (see readout_atlas.per_marker). The set-level AUC must not be used to choose one layer/sign, and small-n markers are not adjudicable.
- The construction probe is a local white-box measurement on short AIME prefixes: it compares candidate directions at one alpha, not a general recipe. The first-order unit decomposition is a diagnostic, not a validated mediation percentage.
- The held-out transfer has two calibration and two held-out sites per marker; the split is by prefix length, so length/position confounding is possible. Treat the transfer numbers as descriptive, not as a validated recipe.
- The alpha sweep has six held-out sites and a single model; KL/entropy are global side effects. High doses can be off-manifold, and the useful window is a descriptive choice under a chosen KL budget.
- The compiled recipe verifies on the same held-out sites used by the transfer/sweep, not on a third independent split. The .npy files are local candidate directions, not a validated production steering vector.

## Provenance

- atlas: experiments/readout_atlas_v1/readout_atlas.json
  - sha256 86c12c8279c4530747b0130d3ac0f2adc6a55b14423b68f6cbe0057ec4fd0223
- axis: frontend/public/latent/data/axis_readouts.json
  - sha256 a815f94a66c910f29a9f0570aaa6dcf18c416f4f1e9c57dcff2ad5c5c701a5da
- bpath: frontend/public/latent/data/bpath_marker_steering.json
  - sha256 dbcd6f8f709b095228fa5a67fe42850d6923e3fc33a0abd869399228a71faa46
- construction: experiments/steering_construction_v1/steering_construction.json
  - sha256 206ff0f46a2491985141a7173c2012fbdafeb71ef7d248c4577cf68350df47b7
- lens: frontend/public/latent/data/logit_lens.json
  - sha256 53583ee8071427b7d37075409f79876e3328390b46fa8f473d4898790658bb7e
- mediation: experiments/neuron_mediation_v1/results/native_mediation_v1.json
  - sha256 cc32ba87e6a3b9fa3d39b2bc02a317f2dc36e3fbb17c697b8909e0aaf12aba26
- steering_recipe: experiments/steering_recipe_v1/steering_recipe.json
  - sha256 2d545eee5e983ed3eb9d584d068da7468fd6cdac2f787c094cde49ebb92ec1ae
- steering_sweep: experiments/steering_sweep_v1/steering_sweep.json
  - sha256 2c696560172def08ab622a11d54d915bc78a228e4b986777d6e6a0e9f977b484
- steering_transfer: experiments/steering_transfer_v1/steering_transfer.json
  - sha256 735ad794d12fc435c6a1ca636faf21a799eb2d9df70aee22c4096c4e2fdc73b1
- summary: experiments/neuron_mediation_v1/results/summary.json
  - sha256 5f1f4ed124ed555b830ce5429aa31b14bd60128e351773abfd1b764b9f73c173

