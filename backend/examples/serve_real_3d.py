"""Serve the *measured* Qwen3-1.7B trajectories to the 3-D front end.

Why this exists
---------------
``server.py``'s default runner is :class:`SyntheticRunner`, so the stock
3-D view animates a path whose shape is invented. This module replays the
hidden states we actually captured on the GPU (the ``data/pairs/``
bundle) instead, so every point on screen is a real residual-stream
vector.

What is real here
-----------------
* ``pc_<id>_control_L<L>.bin``  — float32 ``[T, 2048]``, the residual
  stream at layer ``L`` for the unsteered arm. Genuinely measured.
* ``pc_<id>_delta_L<L>.bin``    — float16 ``[n_common_prefix, 2048]``,
  the difference the injection made. Genuinely measured, and only
  defined over the token prefix where the two arms still line up.
* token ids / text              — decoded with the shipped Qwen3 vocab;
  verified byte-identical to ``pairs.json``'s ``text.control``.
* ``steer_alignment`` / ``steer_shift`` — the real cosine and relative
  shift between the two arms at that token.

What is NOT real
----------------
* ``entropy`` / ``perplexity`` are ``None``. Those need a forward pass
  of the model, and these captures did not store the logits. The colour
  ramp in ``Scene3D`` therefore falls back to its neutral midpoint
  instead of showing a confidence gradient. Do not read the colour as
  confidence.
* The third principal component is computed *here* (the shipped bundle
  only stores PC1/PC2). It is a real PCA axis of the real states, but it
  is not the one the 2-D deck draws, so the two views' Z axes differ.

The layer axis is the interesting part
--------------------------------------
The injection is at L20. The captures sit at L4 / L12 / L20 / L26, and
the measured delta is **exactly zero** at the first three and clearly
non-zero at L26 — layers upstream of the injection are bit-identical by
construction. Dragging the layer slider in the UI walks that boundary,
which is the most direct answer to "what does the injected vector
actually do to the hidden states".

Usage
-----
    python3 examples/serve_real_3d.py --port 8010
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Callable, Optional

import numpy as np

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
sys.path.insert(0, str(BACKEND))

REPO = BACKEND.parent
# The measured bundle ships inside the static front-end's data dir.
DEFAULT_DATA = REPO / "frontend" / "public" / "latent" / "data"

LAYERS = [4, 12, 20, 26]

from core.model_runner import BaseModelRunner, looks_like_self_check  # noqa: E402
from core.protocol import Frame, Point3D  # noqa: E402


# ---------------------------------------------------------------------------
# Token decoding — byte-level BPE, vocab ships as a plain id->str array
# ---------------------------------------------------------------------------


def _bytes_to_unicode() -> dict:
    bs = (
        list(range(ord("!"), ord("~") + 1))
        + list(range(ord("\xa1"), ord("\xac") + 1))
        + list(range(ord("\xae"), ord("\xff") + 1))
    )
    cs = bs[:]
    n = 0
    for b in range(256):
        if b not in bs:
            bs.append(b)
            cs.append(256 + n)
            n += 1
    return dict(zip(bs, [chr(c) for c in cs]))


class TokenDecoder:
    """id -> text for Qwen3's byte-level BPE.

    Decoding needs no merge table, so the shipped ``vocab.json``
    (``{"n": ..., "ids": [...]}``) is sufficient on its own — no
    ``transformers`` / ``tokenizers`` install required.
    """

    def __init__(self, vocab_path: Path):
        blob = json.loads(Path(vocab_path).read_text(encoding="utf-8"))
        ids = blob["ids"] if isinstance(blob, dict) else blob
        self.ids = ids
        self._u2b = {c: b for b, c in _bytes_to_unicode().items()}

    def decode(self, ids) -> str:
        out = bytearray()
        for i in ids:
            for ch in self.ids[int(i)]:
                out.append(self._u2b.get(ch, ord(ch) & 0xFF))
        return out.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Bundle
# ---------------------------------------------------------------------------


class PairBundle:
    """The measured control/steered capture for one problem, all layers."""

    def __init__(self, data_dir: Path, decoder: TokenDecoder):
        self.dir = Path(data_dir)
        meta = json.loads((self.dir / "pairs" / "pairs.json").read_text(encoding="utf-8"))
        self.d_model = int(meta["d_model"])
        self.meta = meta
        self.decoder = decoder
        self._ids: dict[str, np.ndarray] = {}
        self._control: dict[tuple, np.ndarray] = {}
        self._delta: dict[tuple, np.ndarray] = {}
        self._basis: dict[int, tuple] = {}

    # -- metadata ---------------------------------------------------------

    def pair_ids(self) -> list:
        return [p["id"] for p in self.meta["pairs"]]

    def spec(self, pid: str) -> dict:
        for p in self.meta["pairs"]:
            if p["id"] == pid:
                return p
        raise KeyError(pid)

    def problem_text(self, pid: str) -> str:
        return self.spec(pid)["problem"]

    def pick(self, prompt: str) -> str:
        """Resolve a UI prompt to a problem id.

        Accepts a bare id ("1983_I_1"), a substring of the problem
        statement, or anything unrecognised (then the first pair).
        """
        q = (prompt or "").strip()
        if not q:
            return self.pair_ids()[0]
        for pid in self.pair_ids():
            if pid.lower() == q.lower():
                return pid
        qn = " ".join(q.lower().split())
        for pid in self.pair_ids():
            prob = " ".join(self.problem_text(pid).lower().split())
            if qn and (qn in prob or prob[: len(qn)] == qn):
                return pid
        return self.pair_ids()[0]

    # -- bulk arrays ------------------------------------------------------

    def ids(self, pid: str, arm: str = "control") -> np.ndarray:
        key = f"{pid}:{arm}"
        if key not in self._ids:
            path = self.dir / "pairs" / f"pc_{pid}_{arm}_ids.bin"
            self._ids[key] = np.fromfile(path, dtype=np.int32)
        return self._ids[key]

    def control(self, pid: str, layer: int) -> np.ndarray:
        """float32 ``[1024, 2048]`` residual stream for the control arm.

        The file is stored as **float16**, not float32: 4194304 bytes =
        1024 tokens x 2048 dims x 2 bytes, and 1024 is exactly the length
        of ``pc_<id>_control_ids.bin``. Reading it as float32 silently
        yields 512 garbage rows whose norms overflow to inf — so the
        dtype is derived from the file size here rather than trusted
        from the metadata, which only documents fp16 for the delta.
        """
        key = (pid, layer)
        if key not in self._control:
            f = self.dir / "pairs" / f"pc_{pid}_control_L{layer}.bin"
            a = np.fromfile(f, dtype=np.float16).astype(np.float32)
            a = a.reshape(-1, self.d_model)
            if not np.all(np.isfinite(a)):
                raise ValueError(f"{f.name} contains non-finite values")
            self._control[key] = a
        return self._control[key]

    def delta(self, pid: str, layer: int) -> np.ndarray:
        """float32 ``[n_common_prefix, 2048]``; empty when not measured."""
        key = (pid, layer)
        if key not in self._delta:
            f = self.dir / "pairs" / f"pc_{pid}_delta_L{layer}.bin"
            if f.exists():
                a = np.fromfile(f, dtype=np.float16).reshape(-1, self.d_model)
                self._delta[key] = a.astype(np.float32)
            else:
                self._delta[key] = np.zeros((0, self.d_model), dtype=np.float32)
        return self._delta[key]

    # -- projection basis -------------------------------------------------

    def basis(self, pid: str, layer: int) -> tuple:
        """``(mean, components)`` for a 3-axis PCA of the *control* arm.

        Fit on one problem's control arm and reused for every problem at
        that layer, so all six trajectories live in one common frame and
        can be compared without rescaling when the UI switches problems.
        The first pair (``self.meta["pairs"][0]``) is the reference; this
        is deliberate, not an accident of dict keys.

        Fit on the control arm only and then applied to both arms: if
        each arm were projected through its own basis, the two paths
        would be rotated into different frames and their separation
        would be meaningless.
        """
        if layer not in self._basis:
            ref = self.meta["pairs"][0]["id"]
            x = self.control(ref, layer).astype(np.float64)
            mean = x.mean(axis=0)
            centred = x - mean
            # economy SVD on 1024x2048 is milliseconds; no sklearn needed.
            _, _, vt = np.linalg.svd(centred, full_matrices=False)
            self._basis[layer] = (mean, vt[:3].astype(np.float64))
        return self._basis[layer]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class RealPairRunner(BaseModelRunner):
    """Streams a measured trajectory instead of a synthetic one."""

    def __init__(self, data_dir: Path = DEFAULT_DATA, pair_id: Optional[str] = None):
        self.bundle = PairBundle(Path(data_dir), TokenDecoder(Path(data_dir) / "vocab.json"))
        self.d_model = self.bundle.d_model
        self.default_pair = pair_id or self.bundle.pair_ids()[0]
        self._idx = 0

    def reset(self) -> None:
        self._idx = 0

    # -- the measured intervention telemetry, straight from pairs.json ----

    def _measured(self, pid: str, layer: int, i: int) -> tuple:
        """(cosine, rel_shift) between the arms at step ``i``.

        Sourced from the bundle's own ``stats`` rather than recomputed,
        so the numbers the UI shows are the ones the analysis produced.
        """
        try:
            stats = self.bundle.spec(pid)["arms"][str(layer)]["stats"]
        except (KeyError, TypeError):
            return None, None
        cos = stats.get("cosine") or []
        rel = stats.get("rel_shift") or []
        c = cos[i] if i < len(cos) else None
        r = rel[i] if i < len(rel) else None
        return c, r

    async def stream(
        self,
        prompt: str,
        layer: int,
        on_frame: Callable[[Frame], None],
        is_paused: Callable[[], bool],
        is_cancelled: Callable[[], bool],
        set_speed: Callable[[], float],
        inject_vector: Optional[Callable[[int, str], Optional[np.ndarray]]] = None,
    ) -> None:
        pid = self.bundle.pick(prompt)
        if layer not in LAYERS:
            layer = min(LAYERS, key=lambda x: abs(x - int(layer)))

        control = self.bundle.control(pid, layer)
        delta = self.bundle.delta(pid, layer)
        mean, comps = self.bundle.basis(pid, layer)
        ids = self.bundle.ids(pid, "control")
        text = self.bundle.decoder.decode(ids)

        n = min(control.shape[0], ids.shape[0], len(text))
        spec = self.bundle.spec(pid)
        n_prefix = int(spec.get("n_common_prefix") or 0)

        prev = np.zeros(3)
        last_delta = np.zeros(3)

        # Project the whole unsteered path once, then read the step-size
        # distribution off it. Doing this up front (instead of inside the
        # emit loop) also keeps the SVD to exactly one per layer.
        all_xyz = (control.astype(np.float64) - mean) @ comps.T
        all_xyz[~np.isfinite(all_xyz).all(axis=1)] = 0.0
        steps = np.linalg.norm(np.diff(all_xyz, axis=0), axis=1)
        med = float(np.median(steps)) if steps.size else 1.0
        gate = 2.0 * (med if med > 0 else 1.0)

        while self._idx < n:
            if is_cancelled():
                return
            while is_paused() and not is_cancelled():
                await asyncio.sleep(0.05)
            if is_cancelled():
                return

            speed = max(0.05, min(8.0, set_speed()))
            await asyncio.sleep(0.05 / speed)

            i = self._idx
            h = control[i].astype(np.float64)

            # The steering panel's live vector, applied to the *real*
            # residual stream. This is genuine surgery on real states,
            # unlike the synthetic runner which only fakes a z-displacement.
            steer_active = False
            steer_norm = None
            steer_align = None
            if inject_vector is not None:
                v = inject_vector(i, text[i])
                if v is not None:
                    v = np.asarray(v, dtype=np.float64).reshape(-1)
                    if v.shape[0] == h.shape[0]:
                        nrm = float(np.linalg.norm(v))
                        if np.isfinite(nrm):
                            steer_norm = nrm
                            steer_align = float(np.dot(h, v) / (np.linalg.norm(h) * nrm + 1e-12))
                            h = h + v
                            steer_active = True

            # Real measured effect of the *recorded* injection, when this
            # step lies inside the common prefix where a delta exists.
            cos, rel = self._measured(pid, layer, i)
            if i < n_prefix and i < delta.shape[0] and delta.shape[0] > 0:
                d = delta[i]
                steer_shift = float(np.linalg.norm(d) / (np.linalg.norm(h) + 1e-12))
                steer_proj = float(np.dot(h, d) / (np.linalg.norm(h) * np.linalg.norm(d) + 1e-12))
            else:
                steer_shift = None
                steer_proj = None

            xyz = (h - mean) @ comps.T
            if not np.all(np.isfinite(xyz)):
                xyz = np.zeros(3)

            step = xyz - prev
            # "Revisit" only when the reversal is a real excursion, not
            # token-to-token jitter. The synthetic runner could use an
            # absolute epsilon (its path spans ~1 unit); real Qwen3
            # states span ~1000, where any fixed epsilon flags 40-75% of
            # steps and the highlight stops meaning anything. The gate
            # is therefore derived from *this trajectory's own* step
            # distribution, computed once up front.
            rev = (
                np.linalg.norm(last_delta) > gate
                and np.linalg.norm(step) > gate
                and float(np.dot(step, last_delta)) < 0
            )
            last_delta = step
            prev = xyz

            frag = text[i]
            on_frame(
                Frame(
                    ts=time.time(),
                    step_id=i,
                    token=frag,
                    token_id=int(ids[i]),
                    point=Point3D(x=float(xyz[0]), y=float(xyz[1]), z=float(xyz[2])),
                    # Not recoverable without the logits; None keeps the
                    # front end from inventing a confidence colour.
                    perplexity=None,
                    entropy=None,
                    loss=None,
                    is_self_check=looks_like_self_check(frag),
                    is_revisit=bool(rev),
                    steer_active=steer_active,
                    steer_norm=steer_norm,
                    steer_alignment=steer_align,
                    steer_shift=steer_shift,
                    steer_projection=steer_proj,
                )
            )
            self._idx += 1

        self._idx = 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8010)
    ap.add_argument("--data-dir", default=str(DEFAULT_DATA))
    ap.add_argument(
        "--layer",
        type=int,
        default=14,
        help=(
            "initial layer to replay. The default of 14 sits in the shallow "
            "half of the network, where hidden-state variance is small "
            "(max |coord| ~41) and a scene authored in unit-scale numbers "
            "looks roughly right by luck. The deep layers are where it does "
            "not: L20 reaches ~344 and L26 ~1199. Replaying a deep layer by "
            "default is what made this visible."
        ),
    )
    ap.add_argument(
        "--speed",
        type=float,
        default=8.0,
        help=(
            "replay pacing (1.0 = one token per 50 ms). A recorded run has "
            "nothing to wait for, so the default plays the whole 1024-token "
            "trajectory in ~6 s. The UI slider can still slow it down."
        ),
    )
    args = ap.parse_args()

    import uvicorn

    from server import SessionState, app  # noqa: PLC0415  (needs sys.path set above)

    runner = RealPairRunner(Path(args.data_dir))
    app.state.runner_factory = lambda: runner

    # A browser tab that loses focus gets frozen, which tears down its
    # WebSocket; the whole trajectory then never arrives. Playing the
    # recording fast makes the replay finish inside a short focus window
    # instead of needing the tab to stay awake for ~50 s.
    orig_init = SessionState.__init__

    def patched_init(self, runner_factory=None):
        orig_init(self, runner_factory)
        self.speed = max(0.05, min(8.0, args.speed))
        # These four are the only layers the capture covers. Declared so the
        # layer picker offers exactly these instead of a hardcoded list that
        # both invents layers and misses L26.
        self.available_layers = list(LAYERS)
        # Snap *before* storing, not just at replay time. The runner already
        # snaps an unavailable layer, but it does that downstream of `ready`,
        # so the greeting would have announced the requested layer while the
        # stream ran a different one -- the client then labels the trajectory
        # with a layer the data is not from. Storing the snapped value makes
        # `ready` state what actually plays.
        self.layer = min(LAYERS, key=lambda x: abs(x - args.layer))

    SessionState.__init__ = patched_init

    print("=" * 66)
    print("Steering3D — MEASURED trajectories (not synthetic)")
    print("=" * 66)
    print(f"data dir : {args.data_dir}")
    print(f"pairs    : {', '.join(runner.bundle.pair_ids())}")
    print(f"layers   : {LAYERS}  (injection at L20)")
    replay_layer = min(LAYERS, key=lambda x: abs(x - args.layer))
    print(f"layer    : requested L{args.layer} -> replaying L{replay_layer}")
    print(f"d_model  : {runner.d_model}")
    print(f"speed    : {args.speed}x")
    print(f"ws       : ws://{args.host}:{args.port}/ws")
    print("=" * 66)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
