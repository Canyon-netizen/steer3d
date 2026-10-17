"""Hidden-state readout statistics for a steering vector.

Pure numpy helpers: project stored hidden states onto a unit vector, label the
next token, and summarize per-layer rank AUC / effect size.  No model forward
pass and no tokenizer are required here.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np


class AtlasError(ValueError):
    """Raised when the readout atlas inputs are malformed."""


def _as_1d(values: Any, name: str) -> np.ndarray:
    array = np.asarray(values)
    if array.ndim != 1:
        raise AtlasError("%s: expected a 1-D array, got shape %r" % (name, array.shape))
    if array.size == 0:
        raise AtlasError("%s: empty array" % name)
    return array


def rank_auc(scores: Any, labels: Any) -> Optional[float]:
    """Rank AUC with average ranks for ties.

    Returns None when a class is absent (AUC is undefined, not 0.5).
    """
    scores = _as_1d(scores, "scores").astype(float)
    labels = _as_1d(labels, "labels").astype(bool)
    if scores.shape != labels.shape:
        raise AtlasError("scores and labels must have the same shape")
    if not np.isfinite(scores).all():
        raise AtlasError("scores contain non-finite values")
    n_pos = int(labels.sum())
    n_neg = int(len(labels) - n_pos)
    if n_pos == 0 or n_neg == 0:
        return None

    order = np.argsort(scores, kind="mergesort")
    sorted_scores = scores[order]
    ranks = np.empty(len(scores), dtype=float)
    start = 0
    while start < len(scores):
        end = start + 1
        while end < len(scores) and sorted_scores[end] == sorted_scores[start]:
            end += 1
        average_rank = (start + 1 + end) / 2.0
        ranks[order[start:end]] = average_rank
        start = end
    u = float(ranks[labels].sum()) - n_pos * (n_pos + 1) / 2.0
    return u / (n_pos * n_neg)


def cohen_d(positive: Any, negative: Any) -> Optional[float]:
    """Standardized mean difference positive - negative; None if undefined."""
    positive = np.asarray(positive, dtype=float).reshape(-1)
    negative = np.asarray(negative, dtype=float).reshape(-1)
    if positive.size == 0 or negative.size == 0:
        return None
    if not np.isfinite(positive).all() or not np.isfinite(negative).all():
        raise AtlasError("cohen_d inputs contain non-finite values")
    if len(positive) < 2 or len(negative) < 2:
        return None
    var_pos = float(np.var(positive, ddof=1))
    var_neg = float(np.var(negative, ddof=1))
    pooled = math.sqrt((var_pos + var_neg) / 2.0)
    if pooled == 0.0:
        return None
    return float((np.mean(positive) - np.mean(negative)) / pooled)


def layer_stats(proj: Any, cos: Any, norm: Any, labels: Any) -> List[Dict[str, Any]]:
    """Per-layer readout statistics for one trajectory.

    proj / cos / norm have shape (n_positions, n_layers); labels is (n_positions,).
    """
    proj = np.asarray(proj, dtype=float)
    cos = np.asarray(cos, dtype=float)
    norm = np.asarray(norm, dtype=float)
    labels = _as_1d(labels, "labels").astype(bool)
    if proj.ndim != 2 or cos.shape != proj.shape or norm.shape != proj.shape:
        raise AtlasError("proj/cos/norm must all be 2-D with the same shape")
    if len(labels) != proj.shape[0]:
        raise AtlasError("labels length must match the first axis of proj")
    if not (np.isfinite(proj).all() and np.isfinite(cos).all() and np.isfinite(norm).all()):
        raise AtlasError("proj/cos/norm contain non-finite values")

    rows = []
    for layer in range(proj.shape[1]):
        scores = proj[:, layer]
        cosines = cos[:, layer]
        norms = norm[:, layer]
        positive = labels
        negative = ~labels
        auc_proj = rank_auc(scores, labels)
        auc_cos = rank_auc(cosines, labels)
        auc_norm = rank_auc(norms, labels)
        auc_resid = None
        spread = float(np.std(norms))
        if spread > 1e-12:
            normalized = (norms - float(np.mean(norms))) / spread
            design = np.column_stack([np.ones_like(normalized), normalized]).astype(np.float64)
            try:
                with np.errstate(all="ignore"):
                    coefficients, *_ = np.linalg.lstsq(design, scores.astype(np.float64), rcond=None)
                    residual = scores.astype(np.float64) - design @ coefficients
                if np.isfinite(residual).all():
                    auc_resid = rank_auc(residual, labels)
            except np.linalg.LinAlgError:
                auc_resid = None
        effect_proj = cohen_d(scores[positive], scores[negative]) if positive.any() and negative.any() else None
        effect_cos = cohen_d(cosines[positive], cosines[negative]) if positive.any() and negative.any() else None
        auc_cos_oriented = None if auc_cos is None else max(float(auc_cos), 1.0 - float(auc_cos))
        orientation = None if auc_cos is None else (1 if float(auc_cos) >= 0.5 else -1)
        rows.append({
            "layer": layer,
            "auc": auc_proj,
            "auc_cos": auc_cos,
            "auc_cos_oriented": auc_cos_oriented,
            "cos_orientation": orientation,
            "auc_norm": auc_norm,
            "auc_proj_resid": auc_resid,
            "effect": effect_proj,
            "effect_cos": effect_cos,
            "mean_proj_marker": float(scores[positive].mean()) if positive.any() else None,
            "mean_proj_nonmarker": float(scores[negative].mean()) if negative.any() else None,
            "mean_cos_marker": float(cosines[positive].mean()) if positive.any() else None,
            "mean_cos_nonmarker": float(cosines[negative].mean()) if negative.any() else None,
            "mean_norm_marker": float(norms[positive].mean()) if positive.any() else None,
            "mean_norm_nonmarker": float(norms[negative].mean()) if negative.any() else None,
            "mean_norm": float(norms.mean()),
            "n_marker": int(positive.sum()),
            "n_total": int(len(labels)),
        })
    return rows


def aggregate_layers(per_trajectory: Sequence[Sequence[Mapping[str, Any]]]) -> List[Dict[str, Any]]:
    """Equal-weight trajectories per layer; skip AUC when a class is absent."""
    if not per_trajectory:
        raise AtlasError("no trajectory statistics to aggregate")
    n_layers = len(per_trajectory[0])
    rows = []
    for layer in range(n_layers):
        aucs = []
        aucs_cos = []
        aucs_cos_oriented = []
        aucs_norm = []
        aucs_resid = []
        effects = []
        effects_cos = []
        coss_marker = []
        coss_non = []
        norms = []
        norms_marker = []
        norms_non = []
        n_traj = 0
        n_marker = 0
        n_total = 0
        orientations = []
        for trajectory in per_trajectory:
            row = trajectory[layer]
            n_marker += int(row["n_marker"])
            n_total += int(row["n_total"])
            norms.append(float(row["mean_norm"]))
            if row["auc"] is not None:
                aucs.append(float(row["auc"]))
                n_traj += 1
            if row.get("auc_cos") is not None:
                aucs_cos.append(float(row["auc_cos"]))
            if row.get("auc_cos_oriented") is not None:
                aucs_cos_oriented.append(float(row["auc_cos_oriented"]))
            if row.get("auc_norm") is not None:
                aucs_norm.append(float(row["auc_norm"]))
            if row.get("auc_proj_resid") is not None:
                aucs_resid.append(float(row["auc_proj_resid"]))
            if row["effect"] is not None:
                effects.append(float(row["effect"]))
            if row.get("effect_cos") is not None:
                effects_cos.append(float(row["effect_cos"]))
            if row["mean_cos_marker"] is not None:
                coss_marker.append(float(row["mean_cos_marker"]))
            if row["mean_cos_nonmarker"] is not None:
                coss_non.append(float(row["mean_cos_nonmarker"]))
            if row.get("mean_norm_marker") is not None:
                norms_marker.append(float(row["mean_norm_marker"]))
            if row.get("mean_norm_nonmarker") is not None:
                norms_non.append(float(row["mean_norm_nonmarker"]))
            if row.get("cos_orientation") is not None:
                orientations.append(int(row["cos_orientation"]))
        rows.append({
            "layer": layer,
            "mean_auc": float(np.mean(aucs)) if aucs else None,
            "median_auc": float(np.median(aucs)) if aucs else None,
            "mean_auc_cos": float(np.mean(aucs_cos)) if aucs_cos else None,
            "mean_auc_cos_oriented": float(np.mean(aucs_cos_oriented)) if aucs_cos_oriented else None,
            "mean_auc_norm": float(np.mean(aucs_norm)) if aucs_norm else None,
            "mean_auc_proj_resid": float(np.mean(aucs_resid)) if aucs_resid else None,
            "n_trajectories_with_both_classes": n_traj,
            "mean_effect": float(np.mean(effects)) if effects else None,
            "mean_effect_cos": float(np.mean(effects_cos)) if effects_cos else None,
            "cos_orientation": int(round(float(np.mean(orientations)))) if orientations else None,
            "n_trajectories_with_orientation": len(orientations),
            "n_trajectories_negative_orientation": sum(1 for item in orientations if item < 0),
            "mean_cos_marker": float(np.mean(coss_marker)) if coss_marker else None,
            "mean_cos_nonmarker": float(np.mean(coss_non)) if coss_non else None,
            "mean_norm_marker": float(np.mean(norms_marker)) if norms_marker else None,
            "mean_norm_nonmarker": float(np.mean(norms_non)) if norms_non else None,
            "mean_norm": float(np.mean(norms)),
            "n_marker": n_marker,
            "n_total": n_total,
        })
    return rows


def best_layer(layers: Sequence[Mapping[str, Any]]) -> Optional[int]:
    """Best layer by oriented cosine AUC (scale-free), falling back to raw AUC."""
    candidates = []
    for row in layers:
        value = row.get("mean_auc_cos_oriented")
        if value is None:
            value = row.get("mean_auc")
        if value is not None:
            candidates.append((float(value), int(row["layer"])))
    if not candidates:
        return None
    return max(candidates)[1]


def aggregate_marker_layers(
    per_trajectory: Mapping[int, Sequence[Sequence[Mapping[str, Any]]]],
    marker_ids: Sequence[int],
) -> Dict[str, Dict[str, Any]]:
    """Per-marker layer curves.

    The set-level AUC can hide opposite signs across markers; this function
    keeps each marker separate and reports its own best layer / orientation.
    per_trajectory[marker] is a list of per-layer row lists (layer_stats
    output for that marker's binary labels).
    """
    output: Dict[str, Dict[str, Any]] = {}
    for marker in marker_ids:
        trajectories = list(per_trajectory.get(marker, []))
        if not trajectories:
            output[str(marker)] = {
                "n_occurrences": 0,
                "n_trajectories": 0,
                "best_layer": None,
                "best_layer_mean_auc_cos": None,
                "best_layer_mean_auc_cos_oriented": None,
                "best_layer_orientation": None,
                "layers": [],
            }
            continue
        n_layers = len(trajectories[0])
        n_occurrences = sum(int(trajectory[0]["n_marker"]) for trajectory in trajectories)
        layers: List[Dict[str, Any]] = []
        for layer in range(n_layers):
            aucs: List[float] = []
            oriented: List[float] = []
            cos_marker: List[float] = []
            cos_non: List[float] = []
            for trajectory in trajectories:
                row = trajectory[layer]
                if row.get("auc_cos") is not None:
                    aucs.append(float(row["auc_cos"]))
                if row.get("auc_cos_oriented") is not None:
                    oriented.append(float(row["auc_cos_oriented"]))
                if row.get("mean_cos_marker") is not None:
                    cos_marker.append(float(row["mean_cos_marker"]))
                if row.get("mean_cos_nonmarker") is not None:
                    cos_non.append(float(row["mean_cos_nonmarker"]))
            mean_auc = float(np.mean(aucs)) if aucs else None
            layers.append({
                "layer": layer,
                "mean_auc_cos": mean_auc,
                "mean_auc_cos_oriented": float(np.mean(oriented)) if oriented else None,
                "mean_cos_marker": float(np.mean(cos_marker)) if cos_marker else None,
                "mean_cos_nonmarker": float(np.mean(cos_non)) if cos_non else None,
                "n_trajectories": len(aucs),
            })
        best = best_layer(layers)
        best_row = next((row for row in layers if row["layer"] == best), None) if best is not None else None
        orientation = None
        if best_row is not None and best_row["mean_auc_cos"] is not None:
            orientation = 1 if float(best_row["mean_auc_cos"]) >= 0.5 else -1
        output[str(marker)] = {
            "n_occurrences": n_occurrences,
            "n_trajectories": len(trajectories),
            "best_layer": best,
            "best_layer_mean_auc_cos": best_row["mean_auc_cos"] if best_row else None,
            "best_layer_mean_auc_cos_oriented": best_row["mean_auc_cos_oriented"] if best_row else None,
            "best_layer_orientation": orientation,
            "layers": layers,
        }
    return output

