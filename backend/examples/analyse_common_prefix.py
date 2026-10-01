"""Why do the two arms emit the *same* token for 8-44 steps after their
representations have already separated?

This is the part Finding 13 could not answer, and it is the part a mechanism
story has to start from. The finding covers one step per problem — the step
where the text diverges. It says nothing about the 8-44 steps *before* it,
where the residual streams differ by 25-34% of their norm (Finding 12) and the
model still produces byte-identical output.

There is a tempting answer and it is checkable: the steer is slowly eroding the
margin, and the text diverges on the step the erosion crosses zero. If that
were true, the control arm's top-1/top-2 margin would shrink as the divergence
step approaches.

The alternative is a threshold crossing on a decision that was *already* soft:
the margin stays flat, the per-step logit shift stays small, and the flip is
just where a slowly-accumulating shift happened to pass a boundary that was
never far away.

**Which one it is decides whether "the steer changed the answer" is a mechanism
or a coincidence of geometry**, so this file is built to be able to return
either answer, and reports the trajectory rather than a summary of it.

What is exact here
-----------------
The final residual is stored in float32 and is already past ``model.norm``
(see ``analyse_divergence_logits``), so every number here is the model's own
read-out rather than a lens approximation. Each step is cross-checked against
the top-8 logits the collector stored, which means the whole analysis is
verifiable from the data file with no model loaded.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

import numpy as np
import torch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyse_divergence_logits import (  # noqa: E402
    load_dim_names, load_readout, load_vocab, lens,
)


def analyse(pid: str, npz_path: Path, json_path: Path, upto: int,
            g: torch.Tensor, W: torch.Tensor, vocab: Dict[int, str]) -> dict:
    z = np.load(npz_path)
    rec = json.loads(json_path.read_text())
    k = int(rec["paired"]["n_common_prefix"])

    rows: List[dict] = []
    n_repro = n_repro_stored = n_steps = 0
    # Largest |read-out - stored| seen, per arm. Reported rather than hidden:
    # the stored logits come from ``out.logits`` in the *model's* compute
    # dtype, so a bfloat16 collection disagrees with an fp32 read-out by up to
    # half a bf16 ULP (0.06 at logit 30) and that is not an error. A fixed
    # 1e-3 threshold silently turned that into "0/10 match" on a bf16 dataset
    # and "10/10" on an fp32 one, with nothing in the output saying which.
    dev = {"control": 0.0, "steered": 0.0}

    for t in range(min(upto, k) + 1):
        entry: dict = {"t": t}
        per_arm = {}
        for arm in ("control", "steered"):
            h = torch.from_numpy(z[f"{arm}_last32"][t].astype(np.float32))
            lg = lens(h, g, W, True)
            top = torch.topk(lg, 2)
            emitted = int(z[f"{arm}_ids"][t])
            st_id = int(z[f"{arm}_top_ids"][t][0])
            st_l0 = float(z[f"{arm}_top_logits"][t][0])
            st_l1 = float(z[f"{arm}_top_logits"][t][1])
            per_arm[arm] = {
                "argmax": int(lg.argmax()),
                "emitted": emitted,
                "stored_top1": st_id,
                "logit_top1": float(top.values[0]),
                "logit_top2": float(top.values[1]),
                "margin": float(top.values[0] - top.values[1]),
                "stored_logit_top1": st_l0,
                "stored_margin": st_l0 - st_l1,
            }
            n_steps += 1
            n_repro += int(per_arm[arm]["argmax"] == emitted)
            # The dtype-independent claim: the read-out picks the same token
            # the model recorded as its own top-1. Exact under any compute
            # dtype, so this is the check that can actually fail.
            n_repro_stored += int(int(top.indices[0]) == st_id)
            dev[arm] = max(dev[arm], abs(per_arm[arm]["logit_top1"] - st_l0))

        tok = per_arm["control"]["emitted"]
        # The steered arm's logit for the *shared* token, computed directly.
        # Taking it from the steered arm's own top-1 would silently measure a
        # different token at and after k, which is the one place the number
        # matters most.
        for arm in ("control", "steered"):
            h = torch.from_numpy(z[f"{arm}_last32"][t].astype(np.float32))
            lg = lens(h, g, W, True)
            per_arm[arm]["tok_logit"] = float(lg[tok])
        dl = per_arm["steered"]["tok_logit"] - per_arm["control"]["tok_logit"]

        entry.update({
            "token": tok, "text": vocab.get(tok, f"<{tok}>"),
            "is_divergence_step": t == k,
            "arms_agree": per_arm["control"]["emitted"] == per_arm["steered"]["emitted"],
            "readout_agrees_with_emitted": (
                per_arm["control"]["argmax"] == per_arm["control"]["emitted"]
                and per_arm["steered"]["argmax"] == per_arm["steered"]["emitted"]),
            "margin_control": per_arm["control"]["margin"],
            "margin_steered": per_arm["steered"]["margin"],
            "dlogit_shared_token": float(dl),
            "delta_norm": float(np.linalg.norm(
                z["steered_last32"][t].astype(np.float32)
                - z["control_last32"][t].astype(np.float32))),
        })
        # How close the steered arm came to flipping, in units of the control
        # arm's own top-1/top-2 gap. < 1 means it did not cross.
        m = entry["margin_control"]
        entry["distance_to_flip"] = (abs(float(dl)) / m) if m > 1e-6 else None
        rows.append(entry)

    return {"id": pid, "k": k, "rows": rows, "n_steps": n_steps,
            "n_repro": n_repro, "n_repro_stored": n_repro_stored,
            "max_logit_dev": dev,
            # Half a ULP of bfloat16 at |logit| 30, the regime these run in.
            "bf16_half_ulp_at_30": 30.0 * 2 ** -9}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--paired-dir", required=True)
    ap.add_argument("--readout", required=True)
    ap.add_argument("--vocab", required=True)
    ap.add_argument("--upto", type=int, default=8,
                    help="how many steps PAST the divergence to include. This "
                         "used to be an absolute step cap of 48 while the help "
                         "text said 'past the divergence', so any problem whose "
                         "divergence sat at step >= 48 raised StopIteration -- "
                         "and raised it *after* the earlier problems had been "
                         "analysed, discarding their results too. It only "
                         "surfaced when a weaker steering strength pushed the "
                         "divergence out to steps 50 and 86.")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    g, W = load_readout(Path(a.readout))
    vocab = load_vocab(Path(a.vocab))
    pdir = Path(a.paired_dir)

    results = []
    for npz_path in sorted(pdir.glob("pair_*.npz")):
        pid = npz_path.stem.replace("pair_", "")
        k_rec = int(json.loads((pdir / f"pair_{pid}.json").read_text())
                    ["paired"]["n_common_prefix"])
        # ``a.upto`` counts steps *past* the divergence, so the window ends at
        # k + upto -- capped by however many steps the trajectory actually has.
        n_avail = min(len(np.load(npz_path)["control_ids"]),
                      len(np.load(npz_path)["steered_ids"]))
        upto = min(k_rec + a.upto, n_avail - 1)
        r = analyse(pid, npz_path, pdir / f"pair_{pid}.json", upto, g, W, vocab)
        pre = [x for x in r["rows"] if not x["is_divergence_step"]]
        at = next((x for x in r["rows"] if x["is_divergence_step"]), None)
        if at is None or not pre:
            # A per-problem skip, recorded and reported. One bad problem must
            # not take the other five down with it.
            r["skipped"] = "no divergence step inside the analysed window"
            results.append(r)
            print(f"  {pid}  k={r['k']:3d}  跳过：{r['skipped']}")
            continue

        r["summary"] = {
            "k": r["k"],
            "n_prefix_steps": len(pre),
            "readout_reproduces_emitted": f"{r['n_repro']}/{r['n_steps']}",
            "readout_argmax_is_stored_top1": f"{r['n_repro_stored']}/{r['n_steps']}",
            "max_logit_dev_vs_stored": r["max_logit_dev"],
            "bf16_half_ulp_at_30": r["bf16_half_ulp_at_30"],
            "prefix_arms_agree": sum(x["arms_agree"] for x in pre),
            "margin_control_first": pre[0]["margin_control"],
            "margin_control_last": pre[-1]["margin_control"],
            "margin_control_min": min(x["margin_control"] for x in pre),
            "margin_control_median": float(np.median([x["margin_control"] for x in pre])),
            "margin_steered_median": float(np.median([x["margin_steered"] for x in pre])),
            "steered_margin_narrower": sum(
                x["margin_steered"] < x["margin_control"] for x in pre),
            "dlogit_prefix_absmax": max(abs(x["dlogit_shared_token"]) for x in pre),
            "dlogit_prefix_median_abs": float(np.median(
                [abs(x["dlogit_shared_token"]) for x in pre])),
            "dlogit_at_divergence": at["dlogit_shared_token"],
            "distance_to_flip_max_prefix": max(
                [x["distance_to_flip"] for x in pre if x["distance_to_flip"] is not None]),
            "distance_to_flip_at_divergence": at["distance_to_flip"],
            "delta_norm_prefix_median": float(np.median([x["delta_norm"] for x in pre])),
            "delta_norm_at_divergence": at["delta_norm"],
        }
        results.append(r)
        s = r["summary"]
        print(f"  {pid}  k={s['k']:3d}  读出复现 {s['readout_reproduces_emitted']}"
              f"（读出argmax==存储top1 {s['readout_argmax_is_stored_top1']}"
              f"，logit最大偏差 {max(s['max_logit_dev_vs_stored'].values()):.4f}）"
              f"  margin_ctl 首{s['margin_control_first']:.2f} 末{s['margin_control_last']:.2f} "
              f"中位{s['margin_control_median']:.2f}")
        print(f"          前缀内 |dlogit| 中位 {s['dlogit_prefix_median_abs']:.2f} "
              f"最大 {s['dlogit_prefix_absmax']:.2f}   分叉步上 {s['dlogit_at_divergence']:+.2f}"
              f"   离翻转最近 {s['distance_to_flip_max_prefix']:.2f} 倍 margin")

    Path(a.out).write_text(json.dumps(
        {"schema": "common_prefix_v1", "problems": results},
        ensure_ascii=False, indent=2))
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
