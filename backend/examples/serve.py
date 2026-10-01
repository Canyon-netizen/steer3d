"""Custom HTTP server that serves:

  1. Static files from `output/` (the HTML player, qwen3_global.json, etc.)
  2. A binary endpoint that streams a run's raw hidden states for a
     given layer, packed as float16:

       GET /hidden/<run_id>/<layer>

     returns:
       bytes: hidden_states[:, layer, :].astype(float16).tobytes()
       Content-Type: application/octet-stream
       X-Shape:    "<N>,<d_model>"

     This lets the player render the 2048-D "fingerprint" terrain
     without baking ~12 MB per (run, layer) into qwen3_global.json.

  3. Endpoints that expose a row of the LM head for logit-lens-style
     per-dim attribution of a hidden state:

       GET /lm_head_row/<token_id>

     returns:
       bytes: lm_head.weight[token_id].astype(float16).tobytes()
       Content-Type: application/octet-stream
       X-Shape: "<d_model>"

     This is the projection vector for the *output* token whose id is
     <token_id>. The contribution of hidden dim k to that token's logit
     is  hidden[k] * W[token_id][k].  The fingerprint view can color
     each cell by that per-dim contribution (red = pushes toward this
     token, blue = pushes away).

       GET /lm_head_meta

     returns JSON: {"vocab_size": N, "d_model": D, "dtype": "float16"}
     so the player can show "no attribution available" gracefully when
     the weights haven't been loaded.

Run:
    python backend/examples/serve.py
→ listens on port 8765 (same as `python -m http.server`)
"""

from __future__ import annotations

import json
import re
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
WEB_ROOT = HERE / "output"   # serves token_terrain.html, qwen3_global.json, etc.
DATA_ROOT = HERE.parent.parent / "datasets"
PORT = 8765

# Try to load the LM head from a downloaded Qwen3-1.7B checkpoint. The
# path is configurable via env var STEER3D_LM_HEAD; otherwise we look
# for datasets/models/Qwen3-1.7B/model-*.safetensors in the standard
# ModelScope layout. Loaded once at startup, kept in memory as a single
# float16 array of shape (vocab_size, d_model). For Qwen3-1.7B this is
# 151936 × 2048 × 2 = ~622 MB.
LM_HEAD: np.ndarray | None = None
LM_HEAD_VOCAB = 0
LM_HEAD_DMODEL = 0


def _try_load_lm_head() -> np.ndarray | None:
    """Locate Qwen3-1.7B safetensors and pull out lm_head.weight.

    We don't need transformers / torch — safetensors is a self-contained
    format. numpy is enough.
    """
    import os
    candidates = []
    env = os.environ.get("STEER3D_LM_HEAD")
    if env:
        candidates.append(Path(env))
    candidates.append(DATA_ROOT / "models" / "Qwen3-1.7B")

    candidates_files: list[Path] = []
    for root in candidates:
        if root.is_file() and root.suffix == ".safetensors":
            candidates_files = [root]
            break
        if root.is_dir():
            sharded = sorted(root.glob("model-*.safetensors"))
            if sharded:
                candidates_files = sharded
                break
    if not candidates_files:
        return None

    try:
        # Lazy-import safetensors; if it's not installed fall through.
        from safetensors import safe_open
    except Exception:
        print("[serve] safetensors not installed; LM head attribution disabled")
        return None

    # Find which file holds lm_head.weight via the index.
    index_path = candidates_files[0].parent / "model.safetensors.index.json"
    weight_map = None
    if index_path.exists():
        with open(index_path) as f:
            weight_map = json.load(f).get("weight_map", {})
    lm_head_file: Path | None = None
    lm_head_key: str | None = None
    for key in ("lm_head.weight", "output.weight", "embed_out.weight"):
        if weight_map and key in weight_map:
            lm_head_key = key
            lm_head_file = candidates_files[0].parent / weight_map[key]
            break
    if lm_head_file is None:
        # Single-file checkpoint — try a few common names.
        for key in ("lm_head.weight", "output.weight", "embed_out.weight"):
            try:
                with safe_open(str(candidates_files[0]), framework="np") as f:
                    if key in f.keys():
                        lm_head_key = key
                        lm_head_file = candidates_files[0]
                        break
            except Exception:
                pass
    if lm_head_file is None or lm_head_key is None:
        print(f"[serve] no lm_head.weight found in {candidates_files[0].parent}")
        return None

    print(f"[serve] loading {lm_head_key} from {lm_head_file.name}")
    try:
        # bfloat16 weights are common in Qwen3 — only the torch framework
        # supports them in safetensors' numpy backend.
        import torch
        from safetensors import safe_open as _safe_open
        with _safe_open(str(lm_head_file), framework="pt") as f:
            w = f.get_tensor(lm_head_key).to(torch.float16).numpy()
    except Exception as e:
        print(f"[serve] failed to read lm_head tensor: {e}")
        return None
    print(f"[serve] lm_head loaded: shape={w.shape} dtype={w.dtype}")
    return w


try:
    LM_HEAD = _try_load_lm_head()
    if LM_HEAD is not None:
        LM_HEAD_VOCAB, LM_HEAD_DMODEL = LM_HEAD.shape
except Exception as e:
    print(f"[serve] failed to load LM head: {e}")
    LM_HEAD = None


def find_npz_for_run(run_id: str) -> Path | None:
    """Locate the .npz file matching the trajectory_id.

    The trajectory_id looks like `aime__1983__1983_I_1__no_think` and the
    .npz files are named the same way under each config's `aime/` subdir.
    """
    for cfg in DATA_ROOT.iterdir():
        npz = cfg / "aime" / f"{run_id}.npz"
        if npz.exists():
            return npz
    return None


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_ROOT), **kwargs)

    def log_message(self, format, *args):
        # Quieter log; comment out for verbose tracing.
        pass

    def do_GET(self):
        m = re.match(r"^/hidden/([^/]+)/(\d+)$", self.path)
        if m:
            self._serve_hidden(m.group(1), int(m.group(2)))
            return
        m = re.match(r"^/layer_xyz/([^/]+)/(\d+)$", self.path)
        if m:
            self._serve_layer_xyz(m.group(1), int(m.group(2)))
            return
        m = re.match(r"^/token_all_layers/([^/]+)/(\d+)$", self.path)
        if m:
            self._serve_token_all_layers(m.group(1), int(m.group(2)))
            return
        m = re.match(r"^/lm_head_row/(\d+)$", self.path)
        if m:
            self._serve_lm_head_row(int(m.group(1)))
            return
        if self.path == "/lm_head_meta" or self.path == "/lm_head_meta/":
            self._serve_lm_head_meta()
            return
        super().do_GET()

    def _serve_token_all_layers(self, run_id: str, token_idx: int):
        """All 28 layers' hidden state for ONE token (~115 KB Float16).

        Used by the "layer sweep" view to show how a single token's
        residual stream evolves from layer 0 to layer 27.
        """
        npz = find_npz_for_run(run_id)
        if npz is None:
            self.send_error(404, f"no .npz found for run {run_id}")
            return
        try:
            d = np.load(npz, allow_pickle=True)
            hs = d["hidden_states"]
            N, n_layer, d_model = hs.shape
            if token_idx >= N:
                self.send_error(400, f"token_idx {token_idx} >= N ({N})")
                return
            # (n_layer, d_model) Float16 — tightly packed
            data = hs[token_idx, :, :].astype(np.float16)
            payload = data.tobytes()
        except Exception as e:
            self.send_error(500, f"server error: {e}")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Shape", f"{n_layer},{d_model}")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def _serve_layer_xyz(self, run_id: str, layer: int):
        """Serve per-run per-layer xyz as float16 binary.

        Lazy-loaded by the player when the user switches to a layer that
        wasn't inlined into qwen3_global.json.
        """
        # run_id may contain 'aime__' which has underscores but no slashes
        path = WEB_ROOT / "layer_xyz" / f"{run_id}__l{layer}.bin"
        if not path.exists():
            self.send_error(404, f"no xyz file for run {run_id} layer {layer}")
            return
        try:
            payload = path.read_bytes()
        except Exception as e:
            self.send_error(500, f"server error: {e}")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def _serve_hidden(self, run_id: str, layer: int):
        npz = find_npz_for_run(run_id)
        if npz is None:
            self.send_error(404, f"no .npz found for run {run_id}")
            return
        try:
            d = np.load(npz, allow_pickle=True)
            hs = d["hidden_states"]
            N, n_layer, d_model = hs.shape
            if layer >= n_layer:
                self.send_error(400, f"layer {layer} out of range (max {n_layer-1})")
                return
            layer_hs = hs[:, layer, :].astype(np.float16)
            payload = layer_hs.tobytes()
        except Exception as e:
            self.send_error(500, f"server error: {e}")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Shape", f"{layer_hs.shape[0]},{layer_hs.shape[1]}")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def _serve_lm_head_meta(self):
        if LM_HEAD is None:
            payload = json.dumps({"loaded": False}).encode()
        else:
            payload = json.dumps({
                "loaded": True,
                "vocab_size": int(LM_HEAD_VOCAB),
                "d_model": int(LM_HEAD_DMODEL),
                "dtype": "float16",
            }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def _serve_lm_head_row(self, token_id: int):
        if LM_HEAD is None:
            self.send_error(503, "LM head not loaded — install safetensors and place Qwen3-1.7B at datasets/models/Qwen3-1.7B/")
            return
        if token_id < 0 or token_id >= LM_HEAD_VOCAB:
            self.send_error(400, f"token_id {token_id} out of range [0, {LM_HEAD_VOCAB})")
            return
        try:
            row = LM_HEAD[token_id].tobytes()
        except Exception as e:
            self.send_error(500, f"server error: {e}")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(row)))
        self.send_header("X-Shape", f"{LM_HEAD_DMODEL}")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(row)


def main():
    print(f"serving {WEB_ROOT} on http://localhost:{PORT}")
    print(f"  static:        GET /<file>")
    print(f"  hidden:        GET /hidden/<run_id>/<layer>   (returns float16 bytes)")
    if LM_HEAD is not None:
        print(f"  lm_head_row:   GET /lm_head_row/<token_id>   ({LM_HEAD_DMODEL} floats)")
        print(f"  lm_head_meta:  GET /lm_head_meta             (JSON)")
    else:
        print(f"  lm_head_row:   DISABLED (no weights found)")
    HTTPServer(("", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
