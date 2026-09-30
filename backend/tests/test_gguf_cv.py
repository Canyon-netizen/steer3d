"""Tests for the minimal GGUF control-vector reader.

The reader is a hand-rolled parser, so it gets checked against a
synthetic file written to the GGUF spec before anyone points it at a
real vector. A parser that silently mis-reads a tensor's dtype or
offset would produce a plausible-looking direction matrix and no
error, which is the worst possible failure for the thing it is used
for.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from examples.gguf_cv import (  # noqa: E402
    GGML_F32,
    GGUFError,
    T_ARRAY,
    T_BOOL,
    T_FLOAT32,
    T_STRING,
    T_UINT32,
    T_UINT64,
    read_control_vector,
)


def _str(s: str) -> bytes:
    b = s.encode("utf-8")
    return struct.pack("<Q", len(b)) + b


def _kv_scalar(key: str, vtype: int, packed: bytes) -> bytes:
    return _str(key) + struct.pack("<I", vtype) + packed


def _write_gguf(path: Path, meta: dict, arrays: dict, directions: np.ndarray,
                version: int = 3) -> None:
    """Write a minimal control-vector GGUF the reader should accept.

    Type ids come from the reader module rather than being spelled out
    here. Hand-copying them is how this file got a bool written as
    T_ARRAY in the first place: the reader consumed a 1-byte bool as a
    12-byte array header and every following offset was garbage.

    ``arrays`` maps a key to a list of values; ints go out as u64 and
    floats as f32, matching what real control-vector files use for the
    explained-variance keys.
    """
    n_layers, d_model = directions.shape
    body = bytearray()
    body += b"GGUF"
    body += struct.pack("<I", version)
    body += struct.pack("<Q", n_layers)      # one tensor per layer
    # general.alignment is a key/value pair like any other, and is counted
    # here even though it is not in `meta`.
    body += struct.pack("<Q", 1 + len(meta) + len(arrays))

    # general.alignment first, as real writers do.
    body += _kv_scalar("general.alignment", T_UINT32, struct.pack("<I", 32))
    for k, v in meta.items():
        if isinstance(v, str):
            body += _kv_scalar(k, T_STRING, _str(v))
        elif isinstance(v, bool):
            body += _kv_scalar(k, T_BOOL, struct.pack("<?", v))
        elif isinstance(v, int):
            body += _kv_scalar(k, T_UINT64, struct.pack("<Q", v))
        else:
            raise TypeError(f"unsupported metadata type for {k}: {type(v)}")
    for k, vals in arrays.items():
        as_float = any(isinstance(x, float) for x in vals)
        etype, fmt = (T_FLOAT32, "<f") if as_float else (T_UINT64, "<Q")
        body += _str(k) + struct.pack("<I", T_ARRAY)
        body += struct.pack("<I", etype)
        body += struct.pack("<Q", len(vals))
        for x in vals:
            body += struct.pack(fmt, x)

    # One tensor per layer, named `direction.N`, each a flat d_model
    # vector — this is the layout real control-vector files use, and the
    # one the reader is written against.
    for i in range(n_layers):
        body += _str(f"direction.{i}") + struct.pack("<I", 1)
        body += struct.pack("<Q", d_model)
        body += struct.pack("<I", GGML_F32)
        body += struct.pack("<Q", i * d_model * 4)      # byte offset

    pad = (32 - (len(body) % 32)) % 32
    body += b"\x00" * pad
    body += directions.astype(np.float32).tobytes()
    path.write_bytes(bytes(body))


@pytest.fixture
def sample(tmp_path):
    rng = np.random.default_rng(0)
    W = rng.standard_normal((3, 16)).astype(np.float32)
    meta = {
        "controlvector.method": "pca_cv:center",
        "controlvector.model_hint": "Qwen3-1.7B",
        "controlvector.n_components": 1,
        "controlvector.layer_count": 3,
        "controlvector.n_pairs": 30,
        "controlvector.n_positive": 30,
        "controlvector.n_negative": 30,
        "controlvector.pos_field": "sound",
        "controlvector.neg_field": "flawed",
        "controlvector.correct_direction": False,
    }
    arrays = {
        "controlvector.explained_variance.0": [0.5],
        "controlvector.explained_variance.1": [0.3],
        "controlvector.explained_variance.2": [0.2],
    }
    p = tmp_path / "cv.gguf"
    _write_gguf(p, meta, arrays, W)
    return p, W, meta


def test_directions_are_bit_exact(sample):
    """A dtype or offset error would show up here and nowhere else."""
    p, W, _ = sample
    cv = read_control_vector(p)
    assert cv.direction_matrix.shape == W.shape
    np.testing.assert_array_equal(cv.direction_matrix, W)


def test_rows_are_layers_not_components(sample):
    """The 28 tensors in a real file are 28 layers, not 28 components.

    Reading only the first one made a layer-0-vs-layer-27 comparison look
    like a decomposition with no dominant direction. This pins both the
    ordering and the per-layer accessor.
    """
    p, W, _ = sample
    cv = read_control_vector(p)
    assert cv.layer_indices == [0, 1, 2]
    for i in range(3):
        np.testing.assert_array_equal(cv.direction(i), W[i])
    with pytest.raises(GGUFError):
        cv.direction(7)


def test_provenance_metadata_roundtrips(sample):
    """The contrast and its sample size are the interpretability question."""
    p, _, _ = sample
    cv = read_control_vector(p)
    assert cv.get("pos_field") == "sound"
    assert cv.get("neg_field") == "flawed"
    assert cv.get_int("n_pairs") == 30
    assert cv.get_int("layer_count") == 3


def test_explained_variance_is_ordered(sample):
    p, _, _ = sample
    cv = read_control_vector(p)
    ev = cv.explained_variance
    assert ev.shape == (3,)
    np.testing.assert_allclose(ev, [0.5, 0.3, 0.2])


def test_rejects_non_gguf(tmp_path):
    bad = tmp_path / "bad.gguf"
    bad.write_bytes(b"NOTGGUF" + b"\x00" * 40)
    with pytest.raises(GGUFError):
        read_control_vector(bad)


def test_rejects_unknown_version(tmp_path):
    rng = np.random.default_rng(1)
    p = tmp_path / "v9.gguf"
    _write_gguf(p, {"controlvector.method": "x"}, {},
                rng.standard_normal((2, 8)).astype(np.float32), version=9)
    with pytest.raises(GGUFError):
        read_control_vector(p)
