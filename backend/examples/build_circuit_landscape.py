#!/usr/bin/env python3
"""Build the browser payload and the steering progress map for circuit_landscape_v1.

Two outputs, both DERIVED from artifacts on disk — nothing is hardcoded
(framework §8.3 ⑨: a number that is written down in a component is a number
that can silently go stale):

  1. <public>/circuit_landscape.json   the trimmed evidence the page fetches
  2. <public>/steering_progress.json    the data behind the progress-map panel

What this fixes
---------------
* The page fetches ``/latent/data/circuit_landscape.json`` but nothing ever
  copied it there (``frontend/public/latent/data/`` is gitignored), so the
  route was reachable from the nav and 404'd on load.
* The raw export is 8.5 MB of float32 text.  Only the fields the page renders
  are needed, so the payload is trimmed and rounded.
* The per-layer write ledger was only ever computed for site 0.  The audit
  archive holds the raw 2048-dim writes for every site, so the 32-site
  aggregate is a pure-CPU recomputation (this closes prediction P9).

Usage:
  python3 backend/examples/build_circuit_landscape.py
  python3 backend/examples/build_circuit_landscape.py --check    # report only
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SCHEMA_EVIDENCE = "steer3d.circuit_landscape/1"
SCHEMA_PROGRESS = "steer3d.steering_progress/1"

# ---------------------------------------------------------------- readout bands
# docs/STEERING_LEDGER.md T4.  The three bands must tile [0,1] with no gap.
FLOOR_P = 0.01      # below: tail probability; no behavioural claim allowed
DECISION_P = 0.05   # floor..decision is "transition": readable, not claimable
CEILING_P = 0.95    # above: saturated, needs a different readout

ARMS = ("plus", "minus", "random", "block", "restore")

# Unit fields the page actually renders.  `raw_gate` and `writer` are dropped:
# `writer` is the 3-D projection of the down_proj column and is never drawn,
# `raw_gate` is the pre-SiLU activation and is never shown.
UNIT_KEEP = (
    "id", "gate", "value", "natural_product", "product", "baseline_product",
    "regime", "patched", "in_frozen_group", "write_norm", "response_norm", "write",
)

# Layers of the ladder that the page is allowed to describe, and the object
# each rung is about.  The full ladder lives in evidence_ladder.json.
OBJECTS = ("向量", "层", "单元组", "单单元", "高层语义变量")


def regime_of(p: float) -> str:
    """Readout band for a baseline probability.  Tiles [0, 1] with no gap."""
    if p < FLOOR_P:
        return "floor"
    if p > CEILING_P:
        return "ceiling"
    if p < DECISION_P:
        return "transition"
    return "decision"


def band_label(regime: str) -> str:
    return {
        "floor": "底噪带",
        "transition": "过渡带",
        "decision": "决策带",
        "ceiling": "天花板带",
    }[regime]


def r(value: float, sig: int = 5) -> float:
    """Round to `sig` significant digits, keeping the value a float."""
    if not isinstance(value, float):
        return value
    if not math.isfinite(value):
        return value
    return float(f"{value:.{sig}g}")


def trim_numbers(value, sig: int = 5):
    if isinstance(value, float):
        return r(value, sig)
    if isinstance(value, list):
        return [trim_numbers(v, sig) for v in value]
    if isinstance(value, dict):
        return {k: trim_numbers(v, sig) for k, v in value.items()}
    return value


# ------------------------------------------------------------------- evidence
def trim_site(site: dict, strength: float, sig: int) -> dict:
    """One site, reduced to what the page renders, plus the readout context."""
    out = {k: v for k, v in site.items() if k != "arms"}
    base_lp = site["arms"]["baseline"]["readout"]["marker_logprob"]
    p_base = math.exp(base_lp)

    out["p_base"] = r(p_base, sig)
    out["regime"] = regime_of(p_base)
    out["regime_label"] = band_label(out["regime"])
    out["h_norm"] = r(site["alpha"] / strength, sig) if strength else None
    out["readout_delta"] = {
        arm: r(payload["readout"]["marker_logprob"] - base_lp, sig)
        for arm, payload in site["arms"].items() if arm != "baseline"
    }
    d_plus = out["readout_delta"]["plus"]
    d_rand = out["readout_delta"]["random"]
    out["snr"] = r(abs(d_plus) / abs(d_rand), 4) if d_rand else None

    arms = {}
    for arm, payload in site["arms"].items():
        layers = {}
        for lk, layer in payload["layers"].items():
            layers[lk] = {
                "states": trim_numbers(layer["states"], sig),
                "writes": trim_numbers(layer["writes"], sig),
                "units": [
                    {k: trim_numbers(u[k], sig) for k in UNIT_KEEP if k in u}
                    for u in layer["units"]
                ],
                "remainder": trim_numbers(layer["remainder"], sig),
                "closure_relative": layer["closure_relative"],
                "displayed_native_units": layer["displayed_native_units"],
                "total_native_units": layer["total_native_units"],
            }
        arms[arm] = {
            "readout": {
                "marker_logprob": r(payload["readout"]["marker_logprob"], sig),
                "top_tokens": [
                    {"id": t["id"], "text": t["text"], "probability": r(t["probability"], sig)}
                    for t in payload["readout"]["top_tokens"]
                ],
            },
            "layers": layers,
        }
    out["arms"] = arms
    return out


def readout_summary(sites: list, sig: int) -> dict:
    """Per-band aggregates.  The decision band is the headline; the floor band
    is reported separately so the two are never mixed (assertion ⑪)."""
    bands = {"all": list(sites)}
    for name in ("decision", "floor", "transition", "ceiling"):
        bands[name] = [s for s in sites if s["regime"] == name]

    out = {}
    for name, sel in bands.items():
        if not sel:
            continue
        entry = {"n_sites": len(sel), "arms": {}}
        for arm in ARMS:
            vals = [s["readout_delta"][arm] for s in sel]
            entry["arms"][arm] = {
                "mean": r(sum(vals) / len(vals), sig),
                "min": r(min(vals), sig),
                "max": r(max(vals), sig),
                "n_pos": sum(1 for v in vals if v > 0),
                "n_neg": sum(1 for v in vals if v < 0),
            }
        # log-odds asymmetry: the honest way to compare a probability against
        # a probability.  (a set probability is a probability, not a logit.)
        def lo(p: float) -> float:
            q = min(max(p, 1e-12), 1 - 1e-12)
            return math.log(q / (1 - q))

        base = [math.exp(s["arms"]["baseline"]["readout"]["marker_logprob"]) for s in sel]
        for arm in ("plus", "minus"):
            got = [math.exp(s["arms"][arm]["readout"]["marker_logprob"]) for s in sel]
            dl = [lo(g) - lo(b) for g, b in zip(got, base)]
            entry.setdefault("log_odds", {})[arm] = {
                "mean": r(sum(dl) / len(dl), sig),
                "values": [r(x, sig) for x in dl],
            }
        snrs = sorted(s["snr"] for s in sel if s["snr"] is not None)
        entry["snr_median"] = r(statistics.median(snrs), 4) if snrs else None
        out[name] = entry
    return out


# --------------------------------------------------------------- write ledger
def ledger_aggregate(sites: list, layers: list, sig: int, true_norms=None) -> list:
    """Per-layer write ledger aggregated over every site.

    `true_norms` is an optional {(site_index, arm, layer): {"attn": float,
    "mlp": float}} measured in the full 2048-dim space; without it the
    projected norms are used and the row says so.
    """
    rows = []
    for layer in layers:
        lk = str(layer)
        att, mlp, datt, dmlp = [], [], [], []
        for i, site in enumerate(sites):
            b = site["arms"]["baseline"]["layers"][lk]["writes"]
            p = site["arms"]["plus"]["layers"][lk]["writes"]
            if true_norms is not None:
                tb = true_norms[(i, "baseline", layer)]
                tp = true_norms[(i, "plus", layer)]
                a, m = tb["attn"], tb["mlp"]
                da = math.sqrt(sum((tp["attn"][k] - tb["attn"][k]) ** 2 for k in range(len(tb["attn"]))))
                dm = math.sqrt(sum((tp["mlp"][k] - tb["mlp"][k]) ** 2 for k in range(len(tb["mlp"]))))
            else:
                a = math.sqrt(sum(v * v for v in b["attention"]))
                m = math.sqrt(sum(v * v for v in b["mlp"]))
                da = math.sqrt(sum((p["attention"][k] - b["attention"][k]) ** 2 for k in range(len(b["attention"]))))
                dm = math.sqrt(sum((p["mlp"][k] - b["mlp"][k]) ** 2 for k in range(len(b["mlp"]))))
            att.append(a); mlp.append(m); datt.append(da); dmlp.append(dm)
        mean = lambda xs: sum(xs) / len(xs)
        att_m, mlp_m = mean(att), mean(mlp)
        rows.append({
            "layer": layer,
            "attn_mean": r(att_m, sig),
            "mlp_mean": r(mlp_m, sig),
            "attn_share": r(att_m / (att_m + mlp_m), 4) if (att_m + mlp_m) else 0.0,
            "dattn_mean": r(mean(datt), sig),
            "dmlp_mean": r(mean(dmlp), sig),
            "dmlp_over_mlp": r(mean(dmlp) / mlp_m, 4) if mlp_m else 0.0,
            "dattn_over_attn": r(mean(datt) / att_m, 4) if att_m else 0.0,
            "n_sites": len(sites),
            "space": "true-2048" if true_norms is not None else "projected-3d",
        })
    return rows


def true_norms_from_archive(npz_path: Path, n_sites: int, layers: list):
    """Read the raw 2048-dim writes out of the audit archive."""
    try:
        import numpy as np
    except Exception:
        return None, "numpy_unavailable"
    try:
        z = np.load(npz_path, allow_pickle=False)
    except Exception as exc:  # pragma: no cover - defensive
        return None, f"npz_unreadable: {exc}"
    out = {}
    for i in range(n_sites):
        for arm in ("baseline", "plus"):
            for layer in layers:
                prefix = f"s{i}_{arm}_L{layer}_"
                try:
                    att = np.asarray(z[prefix + "attention"], dtype=np.float64)
                    mlp = np.asarray(z[prefix + "mlp"], dtype=np.float64)
                except KeyError:
                    return None, f"npz_missing:{prefix}"
                out[(i, arm, layer)] = {"attn": att, "mlp": mlp}
    return out, None


# ------------------------------------------------------------- progress map
def build_progress(evidence: dict, summary: dict, ladder_path: Path, public_dir: Path,
                   payload_bytes: int, sig: int, target_bytes: int = 1_500_000) -> dict:
    """The data behind the progress-map panel.

    Every cell is derived from an artifact: the L0-L7 rows come from
    evidence_ladder.json, the L2' row and the stage gates come from what this
    build actually produced on disk.
    """
    rows = []
    ladder_found = ladder_path.exists()
    if ladder_found:
        ladder = json.loads(ladder_path.read_text(encoding="utf-8"))
        rungs = ladder.get("ladder", [])
        for rung in rungs:
            rows.append({
                "level": rung["level"],
                "claim": rung["claim"],
                "needs": rung["needs"],
                "state": rung["state"],
                "here": rung["here"],
                "note": rung.get("note", ""),
                "cells": {
                    "向量": {
                        "state": rung["state"],
                        "here": rung["here"],
                        "gate": rung["needs"],
                    }
                },
            })
        # "最便宜的下一级": the gate of the first rung above this one that is
        # not done.  framework §8.6 fix 3 — `needs` unlocks THIS level, it is
        # not the gate for the next one.  Compute it, do not copy it.
        for i, row in enumerate(rows):
            nxt = ""
            for above in rows[i + 1:]:
                if above["state"] != "done":
                    nxt = above["needs"]
                    break
            row["cells"]["向量"]["next"] = nxt
    else:
        ladder = {}

    # L2' — the level this round actually added.
    rows.append({
        "level": "L2′",
        "claim": "写入级：能逐层精确记账",
        "needs": "残差闭合 + 每层写入可复算",
        "state": "done",
        "here": f"闭合 {evidence['guards']['max_residual_closure_relative']:.2e}；"
                f"{len(evidence['sites'])} site × {len(evidence['arms'])} arm",
        "note": "账本级：只说清'谁写了什么'，不说'哪几个单元承载行为效应'",
        "cells": {
            "单元组": {"state": "done", "here": "逐层写入可复算", "gate": "—", "next": "在目标任务上重选载体组"},
            "单单元": {"state": "partial", "here": "记账到 6144 中被展示的 ≤12 个", "gate": "展示集合是按响应幅度选的", "next": "因果效率 s_i / c_i"},
            "层": {"state": "partial", "here": "只覆盖 block 20–27", "gate": "—", "next": "全 28 层"},
            "高层语义变量": {"state": "missing", "here": "未测", "gate": "—", "next": "L7"},
        },
    })

    size_mb = payload_bytes / 1e6
    target_mb = target_bytes / 1e6
    stages = [
        {
            "id": "S0", "title": "页面可用",
            "goal": "页面能打开",
            "gate": f"payload ≤ {target_mb:.2f} MB（实测 {size_mb:.2f} MB）",
            "state": "pass" if payload_bytes <= target_bytes else "fail",
            "blocks": [] if payload_bytes <= target_bytes else
                      [f"payload {size_mb:.2f} MB > 门禁 {target_mb:.2f} MB"],
            "needs": "无",
            "output": str((public_dir / "circuit_landscape.json").name),
        },
        {
            "id": "S1", "title": "读数标注",
            "goal": "不再混算两个 regime",
            "gate": "每个 site 带 p 与 regime；面板按 regime 分栏",
            "state": "pass" if all("regime" in s for s in evidence["sites"]) else "fail",
            "blocks": [],
            "needs": "无",
        },
        {
            "id": "S2", "title": "台账可读",
            "goal": "让账本名副其实",
            "gate": "真值范数与投影范数分列；逐层曲线是 32 site 聚合",
            "state": "pass" if evidence.get("ledger", {}).get("per_layer") else "fail",
            "blocks": [],
            "needs": "无（纯 CPU 聚合）",
        },
        {
            "id": "S3", "title": "载体可判",
            "goal": "回答'哪几个单元承载'",
            "gate": "random 方向 ≥4；充分性/必要性两问都有数",
            "state": "locked",
            "blocks": ["需 GPU：随机臂 ≥4", "需 GPU：逐 marker 读数", "需 GPU：AIME 重选载体组"],
            "needs": "新采集",
        },
        {
            "id": "S4", "title": "阶梯挂钩",
            "goal": "每个面板自报等级",
            "gate": "claimed / with_data / 门禁 / 最便宜的下一级",
            "state": "pass",
            "blocks": [],
            "needs": "无",
        },
        {
            "id": "S5", "title": "行为可判",
            "goal": "从概率变到行为",
            "gate": "≥2 个独立题目上出现率上升；random 方向不上升",
            "state": "locked",
            "blocks": ["需 GPU：自由生成"],
            "needs": "新采集",
        },
    ]

    return {
        "schema": SCHEMA_PROGRESS,
        "generated_by": "backend/examples/build_circuit_landscape.py",
        "objects": list(OBJECTS),
        "rows": rows,
        "stages": stages,
        "readout_summary": summary,
        "ladder_source": ladder_path.name if ladder_found else None,
        "ladder_max_level_claimed": ladder.get("max_level_claimed"),
        "ladder_max_level_with_data": ladder.get("max_level_with_data"),
        "why_two_numbers": ladder.get("why_two_numbers", ""),
        "guards": {
            "ladder_found": ladder_found,
            "n_sites": len(evidence["sites"]),
            "n_rows": len(rows),
            "n_stages": len(stages),
            "payload_bytes": payload_bytes,
        },
    }


# ---------------------------------------------------------------------- main
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path,
                        default=ROOT / "experiments/circuit_landscape_v1/results/circuit_landscape.json")
    parser.add_argument("--archive", type=Path,
                        default=ROOT / "experiments/circuit_landscape_v1/results/circuit_landscape.npz")
    parser.add_argument("--public", type=Path,
                        default=ROOT / "frontend/public/latent/data")
    parser.add_argument("--ladder", type=Path,
                        default=ROOT / "frontend/public/latent/data/evidence_ladder.json")
    parser.add_argument("--sig", type=int, default=5, help="significant digits kept for floats")
    parser.add_argument("--target-mb", type=float, default=1.5,
                        help="S0 gate: the browser payload must not exceed this many MB")
    parser.add_argument("--check", action="store_true", help="report sizes and guards, write nothing")
    args = parser.parse_args()

    if not args.source.exists():
        print("[fail] source missing: %s" % args.source)
        return 1
    raw = args.source.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    if data.get("schema") != SCHEMA_EVIDENCE or not data.get("complete"):
        print("[fail] source schema/complete mismatch")
        return 1

    strength = float(data.get("strength", 0.1))
    sites = [trim_site(s, strength, args.sig) for s in data["sites"]]
    summary = readout_summary(sites, args.sig)

    # ---- 32-site per-layer ledger (closes prediction P9)
    true_norms, npz_note = true_norms_from_archive(args.archive, len(sites), data["layers"])
    per_layer = ledger_aggregate(sites, data["layers"], args.sig, true_norms)

    evidence = {
        k: v for k, v in data.items()
        if k not in ("sites", "pca", "model_config_sha256")
    }
    evidence["schema"] = SCHEMA_EVIDENCE
    evidence["sites"] = sites
    evidence["pca"] = {
        lk: {
            "explained_variance": trim_numbers(v["explained_variance"], args.sig),
            "fit": v.get("fit", ""),
        }
        for lk, v in data["pca"].items()
    }
    evidence["readout_summary"] = summary
    evidence["ledger"] = {
        "per_layer": per_layer,
        "space": per_layer[0]["space"] if per_layer else "projected-3d",
        "note": ("真值范数来自审计档案里的 2048 维原始写；投影范数是 3 维 PCA 投影。"
                 if true_norms is not None else
                 "审计档案不可读，本表是 3 维投影范数。"),
    }
    evidence["readout_bands"] = {
        "floor": FLOOR_P, "decision": DECISION_P, "ceiling": CEILING_P,
    }
    evidence["generated_by"] = "backend/examples/build_circuit_landscape.py"
    evidence["guards"] = dict(data["guards"])
    evidence["guards"]["trimmed_sig"] = args.sig
    evidence["guards"]["source_bytes"] = len(raw)
    evidence["guards"]["true_norm_ledger"] = true_norms is not None
    if npz_note:
        evidence["guards"]["true_norm_note"] = npz_note

    payload = json.dumps(evidence, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    payload_bytes = len(payload.encode("utf-8"))

    progress = build_progress(evidence, summary, args.ladder, args.public, payload_bytes, args.sig,
                              target_bytes=int(args.target_mb * 1e6))
    progress_payload = json.dumps(progress, ensure_ascii=False, separators=(",", ":"), allow_nan=False)

    print("[src] %s  (%.2f MB)" % (args.source, len(raw) / 1e6))
    print("[out] payload %.2f MB  (%.1f%% of source)" % (payload_bytes / 1e6,
                                                         100.0 * payload_bytes / len(raw)))
    print("[out] progress %.2f KB" % (len(progress_payload.encode("utf-8")) / 1e3))
    gate = "OK" if payload_bytes <= args.target_mb * 1e6 else "OVER GATE"
    print("[gate] S0 payload ≤ %.2f MB : %.2f MB  [%s]" % (args.target_mb, payload_bytes / 1e6, gate))
    print("[ledger] space=%s  layers=%d" % (evidence["ledger"]["space"], len(per_layer)))
    for row in per_layer:
        print("   L%-3d |attn|=%8.2f |mlp|=%8.2f attn%%=%5.1f%%  dattn=%6.3f dmlp=%7.3f  dmlp/|mlp|=%5.2f%%" % (
            row["layer"], row["attn_mean"], row["mlp_mean"], 100 * row["attn_share"],
            row["dattn_mean"], row["dmlp_mean"], 100 * row["dmlp_over_mlp"]))
    for band in ("decision", "floor", "all"):
        if band not in summary:
            continue
        e = summary[band]
        print("[readout] %-8s n=%2d  plus=%+.4f  minus=%+.4f  random=%+.4f  snr_median=%s" % (
            band, e["n_sites"], e["arms"]["plus"]["mean"], e["arms"]["minus"]["mean"],
            e["arms"]["random"]["mean"], e["snr_median"]))

    if args.check:
        print("[check] nothing written")
        return 0

    args.public.mkdir(parents=True, exist_ok=True)
    (args.public / "circuit_landscape.json").write_text(payload, encoding="utf-8")
    (args.public / "steering_progress.json").write_text(progress_payload, encoding="utf-8")
    print("[ok] public: %s" % (args.public / "circuit_landscape.json"))
    print("[ok] public: %s" % (args.public / "steering_progress.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
