#!/usr/bin/env python3
"""
obs_series_export.py -- export per-step row series for the usable observables.

OWNERSHIP: this file, obs_series.npz, obs_series_meta.json. It does NOT modify
obs_extract.py or obs_extract.json.

WHY A SEPARATE SCRIPT
  obs_extract.py delivers screening statistics only. This script needs the raw
  per-step rows, and the task forbids changing the delivered extractor, so the
  extraction building blocks are IMPORTED from it rather than rewritten.

ANTI-DRIFT GUARANTEE
  Rewriting the loop is still a (small) re-implementation, so this script does
  not trust itself: after rebuilding the series it recomputes the full summary
  statistics for ALL 14 candidates -- including the 4 rejected controls -- and
  asserts they match the already-delivered obs_extract.json to 1e-9. If the
  export logic had drifted from the verified extractor, that assertion fails and
  no npz is written. The toy self-check is re-run from the same module too.

DETERMINISM
  np.savez stamps zip members with the current time, which would make the md5
  change on every run. The archive is therefore assembled by hand with a fixed
  1980-01-01 member timestamp and sorted member order, so obs_series.npz is
  byte-identical across runs. The meta json is dumped with sort_keys=True and
  deliberately carries no wall-clock time for the same reason.
"""

import io
import json
import os
import sys
import zipfile

import numpy as np
from numpy.lib import format as npformat

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import obs_extract as OE            # verified extraction building blocks

DELIVERED_JSON = os.path.join(HERE, "obs_extract.json")
OUT_NPZ = os.path.join(HERE, "obs_series.npz")
OUT_META = os.path.join(HERE, "obs_series_meta.json")
TOL = 1e-9


def save_deterministic_npz(path, arrays):
    """Write a .npz whose bytes do not depend on the clock."""
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(arrays):
            buf = io.BytesIO()
            npformat.write_array(buf, np.ascontiguousarray(arrays[name]),
                                 allow_pickle=False)
            zi = zipfile.ZipInfo(filename=name + ".npy",
                                 date_time=(1980, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o600 << 16
            zf.writestr(zi, buf.getvalue())
    os.replace(tmp, path)


def main():
    delivered = json.load(open(DELIVERED_JSON))
    usable = list(delivered["summary"]["usable"])
    by_name = {c["name"]: c for c in delivered["candidates"]}

    # ---- reuse the verified building blocks --------------------------
    id2s, vmeta = OE.build_id2surface()
    n_ids = vmeta["max_id"] + 1
    tab = OE.build_classtab(id2s, n_ids)

    toy = OE.run_toy(id2s, tab)
    if not toy["all_passed"] or toy["n_checks"] != delivered["toy_selfcheck"]["n_checks"]:
        raise SystemExit("toy self-check mismatch: %s" % toy)
    print("[toy] re-run from obs_extract: %d checks, %d failed"
          % (toy["n_checks"], toy["n_failed"]), flush=True)

    # ---- rebuild the per-step series for ALL 14 candidates ----------
    all_names = [c["name"] for c in OE.CANDIDATES]
    series = {n: [] for n in all_names}
    traj_id, step_id, traj_names, Ts = [], [], [], []
    first_traj = {}

    for path in OE.DATA_NPZ:
        z = np.load(path)
        tok = z["token_ids"].astype(np.int32)
        tk_i = z["topk_indices"].astype(np.int32)
        tk_l = z["topk_logits"]
        T = tok.size
        w, lse = OE.renorm_weights(tk_l)
        am = np.argmax(tk_l, axis=1)

        # family 1: sequential prefix state
        seen = np.zeros(n_ids, dtype=bool)
        rep_top1 = np.zeros(T)
        rep_frac = np.zeros(T)
        gram_seen = set()
        rep_n4 = np.zeros(T)
        for t in range(T):
            tt = int(tok[t])
            if t >= 3:
                g = (int(tok[t - 3]), int(tok[t - 2]), int(tok[t - 1]), tt)
                if g in gram_seen:
                    rep_n4[t] = 1.0
                else:
                    gram_seen.add(g)
            rep_frac[t] = float(seen[tk_i[t]].sum()) / 64.0
            if seen[tt]:
                rep_top1[t] = 1.0
            seen[tt] = True

        vals = {
            "rep_top1": rep_top1,
            "rep_ngram4": rep_n4,
            "rep_frac_topk": rep_frac,
            "backtrack_topk": tab[tk_i, OE.CLASSDIRS.index("marker")
                                  ].any(axis=1).astype(np.float64),
            "backtrack_frac": OE.class_mass(w, tk_i, tab,
                                            OE.CLASSDIRS.index("marker")),
            "digit_mass": OE.class_mass(w, tk_i, tab,
                                        OE.CLASSDIRS.index("digit")),
            "op_mass": OE.class_mass(w, tk_i, tab, OE.CLASSDIRS.index("op")),
            "newline_mass": OE.class_mass(w, tk_i, tab,
                                          OE.CLASSDIRS.index("newline")),
            "latex_mass": OE.class_mass(w, tk_i, tab,
                                        OE.CLASSDIRS.index("latex")),
            "top1_prob_renorm": w[np.arange(T), am],
        }
        side = json.loads(open(path.replace(".npz", ".json")).read())
        toks = side["tokens"]
        in_th = np.array([bool(x.get("is_in_think_block", False))
                          for x in toks], dtype=np.float64)
        sc_side = np.array([bool(x.get("is_self_check", False))
                            for x in toks], dtype=np.float64)
        surface = [id2s.get(int(x["token_id"]), "") for x in toks]
        sc_re = np.array([1.0 if OE.SELF_CHECK_RE.search(s) else 0.0
                          for s in surface], dtype=np.float64)
        vals["step_frac"] = (np.arange(T, dtype=np.float64)
                             / max(T - 1, 1))
        vals["in_think"] = in_th
        vals["self_check_regex"] = sc_re
        vals["self_check_sidecar"] = sc_side

        nm = os.path.basename(path).replace(".npz", "")
        traj_names.append(nm)
        Ts.append(T)
        if not first_traj:
            first_traj = dict(name=nm, tok=tok.copy(), tk_i=tk_i.copy(),
                              topk_l=tk_l.copy(), T=T)
        for n in all_names:
            series[n].append(vals[n])
        traj_id.append(np.full(T, len(traj_names) - 1, dtype=np.int32))
        step_id.append(np.arange(T, dtype=np.int32))
        print("  [%2d/%2d] %-46s T=%4d"
              % (len(traj_names), len(OE.DATA_NPZ), nm, T), flush=True)

    traj_id = np.concatenate(traj_id)
    step_id = np.concatenate(step_id)
    N = traj_id.size

    # ---- anti-drift: recompute the delivered statistics -------------
    ent = [np.array([float(x.get("entropy", np.nan))
                     for x in json.loads(open(p.replace(".npz", ".json"))
                                          .read())["tokens"]], dtype=np.float64)
           for p in OE.DATA_NPZ]
    ith = [series["in_think"][i] for i in range(len(series["in_think"]))]
    sfr = [series["step_frac"][i] for i in range(len(series["step_frac"]))]
    aux = {"self_check_regex": series["self_check_regex"],
           "in_think": ith, "entropy": ent, "step_frac": sfr}
    tlist = [np.arange(t, dtype=np.float64) for t in Ts]

    n_checked = 0
    bad = []
    for n in all_names:
        s = OE.summarize(n, series[n], tlist, aux, None)
        d = by_name[n]
        for key in ("mean", "sd", "p05", "p50", "p95", "within_traj_sd_mean",
                    "frac_constant_traj", "rho_with_t_within_mean_abs",
                    "rho_with_t_pooled", "acf_lag1", "acf_lag5", "acf_lag20"):
            a, b = s[key], d[key]
            if a is None or b is None:
                if a is not None or b is not None:
                    bad.append((n, key, a, b))
                continue
            if not (abs(float(a) - float(b)) <= TOL * max(1.0, abs(float(b)))):
                bad.append((n, key, a, b))
            n_checked += 1
        if s["n_steps_total"] != d["n_steps_total"]:
            bad.append((n, "n_steps_total", s["n_steps_total"],
                        d["n_steps_total"]))
        n_checked += 1
    if bad:
        for b_ in bad[:20]:
            print("DRIFT", b_, flush=True)
        raise SystemExit("export logic drifted from delivered extractor; "
                         "refusing to write npz")
    print("[drift] %d summary statistics recomputed and matched obs_extract.json"
          " within %.0e" % (n_checked, TOL), flush=True)

    # ---- assemble the usable matrix ----------------------------------
    obs = np.empty((N, len(usable)), dtype=np.float32)
    for j, n in enumerate(usable):
        obs[:, j] = np.concatenate(series[n]).astype(np.float32)
    names = np.array(usable)

    save_deterministic_npz(OUT_NPZ, dict(obs=obs, traj_id=traj_id,
                                          step=step_id, names=names,
                                          traj_names=np.array(traj_names),
                                          traj_T=np.array(Ts, dtype=np.int32)))

    # ---- redundancy matrix (10 x 10) ---------------------------------
    red_within = np.zeros((len(usable), len(usable)))
    red_pooled = np.zeros((len(usable), len(usable)))
    for a in range(len(usable)):
        for b in range(len(usable)):
            na, nb = usable[a], usable[b]
            wa, wb = [], []
            for k in range(len(Ts)):
                r = OE.spearman(series[na][k], series[nb][k])
                if r is not None:
                    wa.append(abs(r))
            red_within[a, b] = float(np.mean(wa)) if wa else float("nan")
            red_pooled[a, b] = float(OE.spearman(np.concatenate(series[na]),
                                                 np.concatenate(series[nb])))
    hi = []
    for a in range(len(usable)):
        for b in range(a + 1, len(usable)):
            if red_within[a, b] > 0.8:
                hi.append((usable[a], usable[b], round(float(red_within[a, b]), 4)))
    hi_p = []
    for a in range(len(usable)):
        for b in range(a + 1, len(usable)):
            if red_pooled[a, b] > 0.8:
                hi_p.append((usable[a], usable[b],
                             round(float(red_pooled[a, b]), 4)))

    # ---- hand-computed sanity value ----------------------------------
    # rep_frac_topk on the first trajectory, first 5 steps. Definition:
    #   value(t) = |{ i in 0..63 : topk_indices[t][i] already occurs in
    #                token_ids[0 .. t-1] }| / 64
    # Nothing renormalised and no probability involved, so it is checkable by
    # hand directly from the token ids.
    ft = first_traj
    sf = []
    sf_steps = []
    for t in range(5):
        pref = set(int(x) for x in ft["tok"][:t])
        hits = [int(i) for i in ft["tk_i"][t] if int(i) in pref]
        sf.append(len(hits) / 64.0)
        sf_steps.append(dict(
            step=t,
            generated_token_id=int(ft["tok"][t]),
            generated_token_surface=id2s.get(int(ft["tok"][t]), ""),
            prefix_token_ids=[int(x) for x in ft["tok"][:t]],
            prefix_len=t,
            n_topk_ids_already_in_prefix=len(hits),
            matching_topk_ids=sorted(set(hits))[:8],
            value=len(hits) / 64.0))
    # second sanity value: digit_mass step mass, with the actual share breakdown
    dm_series = np.concatenate(series["digit_mass"])
    dstep = int(np.nonzero(dm_series[:ft["T"]] > 0)[0][0]) if (dm_series[:ft["T"]] > 0).any() else 0
    lg = ft["topk_l"][dstep].astype(np.float64)
    mx = lg.max()
    lse = mx + np.log(np.exp(lg - mx).sum())
    sh = np.exp(lg - lse)
    dj = OE.CLASSDIRS.index("digit")
    dig_rows = [i for i in range(64) if tab[int(ft["tk_i"][dstep][i]), dj]]
    sanity2 = dict(
        observable="digit_mass", trajectory=ft["name"], step=dstep,
        definition=("sum over the 64 top-k slots whose token id decodes to a "
                    "pure digit of exp(logit - logsumexp(top64 logits))"),
        lse64_top64=float(lse),
        n_digit_slots=len(dig_rows),
        digit_slots_and_shares=[dict(slot=i,
                                     token_id=int(ft["tk_i"][dstep][i]),
                                     surface=id2s.get(int(ft["tk_i"][dstep][i]), ""),
                                     share=float(sh[i])) for i in dig_rows[:10]],
        value=float(dm_series[dstep]))

    meta = {
        "schema_version": "1",
        "generated_by": ".cache/rolesverify/obs_series_export.py",
        "source": {
            "npz": "obs_series.npz",
            "meta": "obs_series_meta.json",
            "extractor": "obs_extract.py (imported, not reimplemented)",
            "screening_report": "obs_extract.json",
            "note": ("obs_extract.py and obs_extract.json were NOT modified by "
                     "this export. Before writing the npz the export recomputed "
                     "the full summary statistics for all 14 candidates and "
                     "asserted they match the delivered obs_extract.json to "
                     "1e-9, so the exported rows are provably the same numbers "
                     "that were screened."),
        },
        "determinism": {
            "npz_bytes": ("assembled by hand with a fixed 1980-01-01 member "
                          "timestamp and sorted member order, because "
                          "np.savez stamps members with the current time and "
                          "would change the md5 on every run"),
            "meta_bytes": "json.dump(sort_keys=True), no wall-clock field",
            "reproduce": "rm obs_series.npz obs_series_meta.json && python3 obs_series_export.py",
        },
        "arrays": {
            "obs": dict(shape=list(obs.shape), dtype=str(obs.dtype),
                        axis0="concatenated steps, ordered by trajectory then "
                              "step; slice with traj_id",
                        axis1="candidate observable, see column_order"),
            "traj_id": dict(shape=[int(traj_id.size)],
                             dtype=str(traj_id.dtype),
                             meaning="0-based index into trajectories"),
            "step": dict(shape=[int(step_id.size)], dtype=str(step_id.dtype),
                         meaning="0-based step index within its own trajectory"),
            "names": dict(shape=[len(usable)], dtype=str(names.dtype),
                          meaning="column order of obs"),
            "traj_names": dict(shape=[len(traj_names)], dtype="<U64",
                               meaning="basename of each npz, in order"),
            "traj_T": dict(shape=[len(Ts)], dtype="int32",
                           meaning="step count of each trajectory, in order"),
        },
        "column_order": {str(j): n for j, n in enumerate(usable)},
        "n_columns": len(usable),
        "n_steps_total": int(N),
        "n_trajectories": len(Ts),
        "trajectory_table": [dict(index=i, traj_name=traj_names[i], T=Ts[i],
                                  row_offset=int(sum(Ts[:i])),
                                  row_end=int(sum(Ts[:i + 1])))
                             for i in range(len(Ts))],
        "renormalisation_convention": (
            "every *_mass / *_renorm column is a TOP-64-INTERNAL share: "
            "logits are log-sum-exp normalised across the 64 stored slots "
            "only, so a column sums to 1 over slots, not over the vocabulary. "
            "Measured on this dataset the truncation bias against the sidecar "
            "true top1_prob is mean|gap| = 1.9e-05 (see obs_extract.json "
            "renormalisation_convention), so the values are numerically close "
            "to true probabilities HERE, but they are not probabilities by "
            "definition."),
        "sanity_checks": {
            "how_to_verify": ("for any row, rebuild the value from the npz "
                              "token ids and the npz topk arrays using the "
                              "definition in the entry; the two worked examples "
                              "below are reproducible by hand"),
            "example_1_repeat_fraction": dict(
                observable="rep_frac_topk", trajectory=ft["name"],
                definition=("|{i in 0..63 : topk_indices[t][i] already occurs "
                            "in token_ids[0..t-1]}| / 64"),
                steps=sf_steps,
                values_first5=sf),
            "example_2_digit_mass": sanity2,
        },
        "redundancy_matrix": {
            "what": ("|Spearman rho| between every pair of usable candidates. "
                     "This tells the probe how much independent search space "
                     "it really has: a pair above 0.8 is effectively one "
                     "observable, not two."),
            "order": usable,
            "abs_rho_within_traj_mean": [[round(float(v), 4) for v in row]
                                         for row in red_within],
            "abs_rho_pooled": [[round(float(v), 4) for v in row]
                               for row in red_pooled],
            "definition_within": ("mean over trajectories of |Spearman rho| "
                                  "computed inside each trajectory; a pair is "
                                  "skipped for a trajectory only if one series "
                                  "is constant there"),
            "definition_pooled": ("|Spearman rho| over all %d steps pooled" % N),
            "pairs_above_0.8_within": hi,
            "pairs_above_0.8_pooled": hi_p,
            "n_effective_independent_columns_within": (
                len(usable) - len(hi)),
            "pairwise_median_within": round(float(np.median(
                red_within[np.triu_indices(len(usable), 1)])), 4),
            "pairwise_max_within": round(float(np.max(
                red_within[np.triu_indices(len(usable), 1)])), 4),
        },
        "entropy_redundancy_note": {
            "question": ("among the 10 usable candidates, which have |rho| > "
                         "0.8 against entropy?"),
            "per_candidate_abs_rho_vs_entropy": {
                n: round(abs(float(by_name[n]["rho_vs"]["entropy"]
                                    ["within_traj_mean_rho"])), 4)
                for n in usable},
            "exceeding_0.8": [n for n in usable if abs(float(
                by_name[n]["rho_vs"]["entropy"]["within_traj_mean_rho"])) > 0.8],
        },
        "rep_frac_topk_rho_with_t": {
            "question": ("is |rho| = 0.442 pooled or within-trajectory?"),
            "answer": ("within-trajectory. 0.442294 is "
                       "rho_with_t_within_mean_abs, the mean over 48 "
                       "trajectories of the within-trajectory Spearman against "
                       "the step index. The pooled value across all %d steps is "
                       "0.503404, which is the larger of the two."
                       % N),
            "within_traj_mean_abs": 0.442294,
            "within_traj_mean_signed": 0.442294,
            "pooled": 0.503404,
            "n_traj_within_defined": 48,
            "descriptor": "moderate_trend",
        },
        "caveats_carried_over": {
            "rho_vs_in_think_underpowered": (
                "obs_extract.json post_screen_caveats: in_think is constant on "
                "45 of 48 trajectories, so any correlation with the think-block "
                "boundary rests on 3 trajectories."),
            "top1_prob_renorm_redundant": (
                "top1_prob_renorm is |rho| = 0.985 against entropy and is a "
                "restatement of it. It is exported because it is in "
                "summary.usable and the delivered verdicts were not changed, but "
                "the probe should treat it as a duplicate of entropy, not as an "
                "independent column."),
        },
    }
    with open(OUT_META, "w") as f:
        json.dump(meta, f, indent=2, sort_keys=True)
        f.write("\n")

    print("[export] obs%s %s | traj_id%s | step%s | names%s"
          % (obs.shape, obs.dtype, traj_id.shape, step_id.shape,
             names.shape), flush=True)
    print("[export] redundancy within-traj max=%.4f median=%.4f | pairs>0.8: %s"
          % (meta["redundancy_matrix"]["pairwise_max_within"],
             meta["redundancy_matrix"]["pairwise_median_within"], hi), flush=True)
    print("[export] |rho|>0.8 vs entropy: %s"
          % meta["entropy_redundancy_note"]["exceeding_0.8"], flush=True)
    print("[export] wrote %s and %s" % (OUT_NPZ, OUT_META), flush=True)


if __name__ == "__main__":
    main()
