"""Minimal GGUF control-vector reader.

The `gguf` package in the conda env predates numpy 2.0 and dies on
`ndarray.newbyteorder`, and pinning numpy down is not worth it for one
file format. The control-vector subset of GGUF is small and stable, so
this parses it directly: a magic, a version, a count of key/value
metadata pairs, then the tensor descriptors, then the tensor data.

Written to be dependency-free (numpy only) so it runs anywhere the
analysis needs to, rather than only where a particular gguf build
happens to work.

Reference: https://github.com/ggml-org/ggml/blob/master/docs/gguf.md
"""

from __future__ import annotations

import re
import struct
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

# GGUF metadata value type ids
(
    T_UINT8, T_INT8, T_UINT16, T_INT16, T_UINT32, T_INT32,
    T_FLOAT32, T_BOOL, T_STRING, T_ARRAY, T_UINT64, T_INT64,
    T_FLOAT64,
) = range(13)

# ggml tensor type ids used by control-vector files. Exported as names
# rather than left as bare numbers so writers (including the test writer)
# cannot disagree with this table about what 0 means.
GGML_F32 = 0
GGML_F16 = 1

# (ggml type name, numpy dtype, itemsize)
GGML_TYPES: Dict[int, Tuple[str, Any, int]] = {
    GGML_F32: ("F32", np.float32, 4),
    GGML_F16: ("F16", np.float16, 2),
    2: ("Q4_0", None, 0),      # not needed for control vectors
    3: ("Q4_1", None, 0),
    6: ("Q5_0", None, 0),
    7: ("Q5_1", None, 0),
    8: ("Q8_0", None, 0),
    9: ("Q8_1", None, 0),
    10: ("Q2_K", None, 0),
    11: ("Q3_K", None, 0),
    12: ("Q4_K", None, 0),
    13: ("Q5_K", None, 0),
    14: ("Q6_K", None, 0),
    15: ("Q8_K", None, 0),
    30: ("BF16", None, 2),
}

_SCALARS = {
    T_UINT8: ("<B", 1), T_INT8: ("<b", 1),
    T_UINT16: ("<H", 2), T_INT16: ("<h", 2),
    T_UINT32: ("<I", 4), T_INT32: ("<i", 4),
    T_FLOAT32: ("<f", 4), T_BOOL: ("<?", 1),
    T_UINT64: ("<Q", 8), T_INT64: ("<q", 8), T_FLOAT64: ("<d", 8),
}


class GGUFError(RuntimeError):
    pass


class ControlVector:
    """A parsed `controlvector` GGUF: metadata plus the direction matrix."""

    def __init__(self, meta: Dict[str, Any], tensors: Dict[str, np.ndarray],
                 path: Path):
        self.meta = meta
        self.tensors = tensors
        self.path = path

    # -- convenience accessors ------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        return self.meta.get(f"controlvector.{key}", default)

    def get_int(self, key: str, default: Any = None) -> Any:
        """Metadata written as a float but meant as a count (n_pairs etc.)."""
        v = self.get(key, default)
        if v is None:
            return None
        try:
            return int(np.asarray(v).ravel()[0])
        except (TypeError, ValueError, IndexError):
            return v

    @property
    def layer_indices(self) -> List[int]:
        """Layer numbers present, parsed from each `direction.N` tensor name."""
        out = []
        for name, arr in self.tensors.items():
            m = re.fullmatch(r"direction\.(\d+)", name)
            if m and arr.ndim == 1:
                out.append(int(m.group(1)))
        return sorted(out)

    @property
    def direction_matrix(self) -> np.ndarray:
        """(n_layers, d_model) float32, ordered by layer index.

        Control-vector files store one direction PER LAYER — a Qwen3-1.7B
        file has 28 tensors named `direction.0`…`direction.27`, matching
        its `layer_count` of 28. They are not PCA components of a single
        vector, and the matching `explained_variance.N` values are per
        layer, not per component. Collapsing them into one matrix and
        comparing the rows would compare layer 0 against layer 27 and
        report the result as a "component cosine".
        """
        entries = []
        for name, arr in self.tensors.items():
            m = re.fullmatch(r"direction\.(\d+)", name)
            if m and arr.ndim == 1:
                entries.append((int(m.group(1)), arr.astype(np.float32)))
        if entries:
            entries.sort(key=lambda t: t[0])
            return np.stack([a for _, a in entries])
        # Fallbacks for files that store one multi-row matrix instead.
        for arr in self.tensors.values():
            if arr.ndim == 2:
                return arr.astype(np.float32)
        for arr in self.tensors.values():
            if arr.ndim == 1:
                return arr.astype(np.float32).reshape(1, -1)
        raise GGUFError("no direction tensor found")

    def direction(self, layer: int) -> np.ndarray:
        """The single (d_model,) direction for one layer."""
        for name, arr in self.tensors.items():
            m = re.fullmatch(r"direction\.(\d+)", name)
            if m and int(m.group(1)) == layer:
                return arr.astype(np.float32)
        raise GGUFError(f"no direction for layer {layer}")

    @property
    def explained_variance(self) -> np.ndarray:
        """Per-layer variance, keyed `controlvector.explained_variance.N`.

        Real files store these as one-element arrays; accept a bare scalar
        too, since either encoding means the same thing.
        """
        vals = []
        for k, v in self.meta.items():
            if not k.startswith("controlvector.explained_variance."):
                continue
            try:
                idx = int(k.rsplit(".", 1)[1])
                vals.append((idx, float(np.asarray(v).ravel()[0])))
            except (ValueError, TypeError, IndexError):
                continue
        return np.array([v for _, v in sorted(vals)], dtype=np.float64)

    def __repr__(self) -> str:
        return (
            f"<ControlVector {self.path.name} "
            f"layers={len(self.layer_indices) or self.get('layer_count')} "
            f"pairs={self.get_int('n_pairs')} "
            f"contrast={self.get('pos_field')}/{self.get('neg_field')}>"
        )


def _read_string(buf: bytes, off: int) -> Tuple[str, int]:
    (n,) = struct.unpack_from("<Q", buf, off)
    off += 8
    s = buf[off:off + n].decode("utf-8", errors="replace")
    return s, off + n


def _read_value(buf: bytes, off: int, vtype: int):
    if vtype == T_STRING:
        return _read_string(buf, off)
    if vtype == T_ARRAY:
        (elem_type,) = struct.unpack_from("<I", buf, off)
        (count,) = struct.unpack_from("<Q", buf, off + 4)
        off += 12
        # Elements in an array are stored back to back with no padding.
        if elem_type == T_STRING:
            items = []
            for _ in range(count):
                v, off = _read_string(buf, off)
                items.append(v)
            return items, off
        if elem_type in _SCALARS:
            fmt, size = _SCALARS[elem_type]
            arr = np.array(
                struct.unpack_from(f"<{count}{fmt[1]}", buf, off)
            ) if count else np.array([])
            return arr, off + size * count
        raise GGUFError(f"unsupported array element type {elem_type}")
    if vtype in _SCALARS:
        fmt, size = _SCALARS[vtype]
        (val,) = struct.unpack_from(fmt, buf, off)
        if vtype == T_BOOL:
            val = bool(val)
        return val, off + size
    raise GGUFError(f"unsupported value type {vtype}")


def read_control_vector(path) -> ControlVector:
    """Parse a control-vector GGUF without depending on the gguf package."""
    path = Path(path)
    buf = path.read_bytes()
    if len(buf) < 24 or buf[:4] != b"GGUF":
        raise GGUFError(f"{path.name} is not a GGUF file")

    off = 4
    (version,) = struct.unpack_from("<I", buf, off); off += 4
    (n_tensors,) = struct.unpack_from("<Q", buf, off); off += 8
    (n_kv,) = struct.unpack_from("<Q", buf, off); off += 8

    if version not in (2, 3):
        raise GGUFError(f"unsupported GGUF version {version}")

    meta: Dict[str, Any] = {}
    for _ in range(n_kv):
        key, off = _read_string(buf, off)
        (vtype,) = struct.unpack_from("<I", buf, off); off += 4
        val, off = _read_value(buf, off, vtype)
        meta[key] = val

    # Tensor descriptors, then a jump to the data section.
    descriptors = []
    for _ in range(n_tensors):
        name, off = _read_string(buf, off)
        (n_dims,) = struct.unpack_from("<I", buf, off); off += 4
        dims = struct.unpack_from(f"<{n_dims}Q", buf, off); off += 8 * n_dims
        (ggml_type,) = struct.unpack_from("<I", buf, off); off += 4
        (offset,) = struct.unpack_from("<Q", buf, off); off += 8
        descriptors.append((name, dims, ggml_type, offset))

    alignment = int(meta.get("general.alignment", 32))
    data_start = (off + alignment - 1) // alignment * alignment

    tensors: Dict[str, np.ndarray] = {}
    for name, dims, ggml_type, toff in descriptors:
        if ggml_type not in GGML_TYPES:
            raise GGUFError(
                f"tensor {name!r} has ggml type {ggml_type}, which this "
                f"minimal reader does not decode"
            )
        _, np_dtype, size = GGML_TYPES[ggml_type]
        if np_dtype is None:
            raise GGUFError(f"quantised tensor {name!r} is not supported")
        count = int(np.prod(dims)) if dims else 1
        start = data_start + toff
        arr = np.frombuffer(
            buf, dtype=np.dtype(np_dtype), count=count, offset=start
        )
        tensors[name] = arr.reshape(dims) if dims else arr

    return ControlVector(meta, tensors, path)


def load_all(pattern_dir) -> List[ControlVector]:
    d = Path(pattern_dir).expanduser()
    out = []
    for f in sorted(d.glob("*.gguf")):
        try:
            out.append(read_control_vector(f))
        except GGUFError as e:
            print(f"  skip {f.name}: {e}")
    return out
