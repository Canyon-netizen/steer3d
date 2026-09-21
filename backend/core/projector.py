"""Online dimensionality reduction for streaming activation data.

Two strategies are provided:
  * OnlinePCA  — incremental SVD with warm restart, O(d^2) per step.
    Fast, deterministic, perfect for the synthetic demo.
  * SketchUMAP  — wraps a small umap-learn model that is fit on the
    most recent window of points; slower but produces more
    topology-preserving projections for non-linear manifolds.

The frontend treats the (x, y, z) returned by `update()` as
final 3-D coordinates; it does not re-project.
"""

from __future__ import annotations

from collections import deque
from typing import Deque

import numpy as np

from .protocol import Point3D


class OnlinePCA:
    """Incremental PCA in the Welford style.

    Tracks running mean and covariance. On each `update()` call we
    project the new point using the top-3 eigenvectors of the
    covariance seen so far. Cost: O(d^2) per refit, amortized.
    """

    def __init__(self, d: int, target_dim: int = 3, window: int = 256):
        self.d = d
        self.k = target_dim
        self.window = window
        self.n = 0
        self.mean = np.zeros(d, dtype=np.float64)
        self._buf: Deque[np.ndarray] = deque(maxlen=window)
        self._components = np.eye(d, self.k, dtype=np.float64)
        self._fitted = False
        # A small jitter prevents the SVD from being singular on
        # the very first points when the buffer is empty.
        self._jitter = 1e-4

    def update(self, x: np.ndarray) -> Point3D:
        x = np.asarray(x, dtype=np.float64).reshape(-1)
        if x.shape[0] != self.d:
            raise ValueError(f"expected vector of dim {self.d}, got {x.shape[0]}")

        self.n += 1
        # Welford update of mean
        delta = x - self.mean
        self.mean += delta / self.n
        # Keep a rolling window for adaptive refit
        self._buf.append(x.copy())
        if self.n >= max(8, self.k * 4) and (self.n % 16 == 0 or not self._fitted):
            self._refit_components()

        xc = x - self.mean
        coords = self._components.T @ xc
        return Point3D(x=float(coords[0]), y=float(coords[1]), z=float(coords[2]))

    def _refit_components(self):
        if len(self._buf) < 4:
            return
        buf = np.stack(self._buf, axis=0)
        local_mean = buf.mean(axis=0)
        centered = buf - local_mean
        # Add a tiny jitter for numerical stability.
        centered += self._jitter * np.random.standard_normal(centered.shape)
        try:
            from sklearn.decomposition import IncrementalPCA  # type: ignore

            ipca = IncrementalPCA(n_components=self.k)
            ipca.fit(centered)
            self._components = ipca.components_.T.astype(np.float64)
        except Exception:
            U, S, Vt = np.linalg.svd(centered, full_matrices=False)
            self._components = Vt[: self.k].T.astype(np.float64)
        self._fitted = True

    def reset(self):
        self.n = 0
        self.mean = np.zeros(self.d, dtype=np.float64)
        self._buf.clear()
        self._components = np.eye(self.d, self.k, dtype=np.float64)
        self._fitted = False


class SketchUMAP:
    """Online-friendly UMAP wrapper.

    Periodically refits a small UMAP model on the rolling window.
    Projects the latest point using the latest model.
    """

    def __init__(self, d: int, target_dim: int = 3, window: int = 256, refit_every: int = 32):
        try:
            from umap import UMAP  # type: ignore  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "umap-learn is required for SketchUMAP. `pip install umap-learn`."
            ) from e

        from umap import UMAP  # noqa: F811

        self.d = d
        self.k = target_dim
        self.window = window
        self.refit_every = refit_every
        self._buf: Deque[np.ndarray] = deque(maxlen=window)
        self._model = UMAP(n_components=target_dim, n_neighbors=15, min_dist=0.1)
        self._fitted = False
        self._tick = 0

    def update(self, x: np.ndarray) -> Point3D:
        x = np.asarray(x, dtype=np.float64).reshape(1, -1)
        self._buf.append(x.reshape(-1))
        self._tick += 1
        if not self._fitted and len(self._buf) >= 16:
            self._refit()
        elif self._fitted and self._tick % self.refit_every == 0:
            self._refit()
        if self._fitted:
            y = self._model.transform(x)[0]
        else:
            # Until we have enough points, fall back to a tiny
            # deterministic projection so the frontend still receives
            # coordinates.
            y = np.array([x[0, 0], x[0, 1], x[0, 2]], dtype=np.float64) * 0.01
        return Point3D(x=float(y[0]), y=float(y[1]), z=float(y[2]))

    def _refit(self):
        from umap import UMAP

        X = np.stack(self._buf, axis=0)
        self._model = UMAP(n_components=self.k, n_neighbors=min(15, len(X) - 1), min_dist=0.1)
        self._model.fit(X)
        self._fitted = True

    def reset(self):
        self._buf.clear()
        self._fitted = False
        self._tick = 0