# Steering3D Backend

FastAPI + WebSocket server that streams per-token frames
describing the model's reasoning trajectory and steering state.

## Quick start (synthetic demo, no GPU needed)

```bash
pip install fastapi uvicorn numpy scikit-learn
python examples/demo_synthetic.py
```

This will start:
- HTTP at `http://localhost:8000`
- WebSocket at `ws://localhost:8000/ws`

The server emits `Frame` JSON objects on the WebSocket at a
rate of ~20 Hz (50 ms per simulated token). Frames contain the
3-D projected coordinates of baseline and steered paths plus
top-K token predictions.

## Quick start (real model, needs GPU)

```bash
pip install -r requirements.txt
python examples/demo_real_model.py \
    --model meta-llama/Llama-3.1-8B-Instruct \
    --layer 14 \
    --preset sycophancy
```

## Architecture

The backend is intentionally modular:

```
core/
├── protocol.py     # Frame dataclass + ControlMessage
├── steerer.py      # CAA-style steering vector extraction
├── activation.py   # PyTorch hooks for residual capture/injection
├── projector.py    # OnlinePCA / SketchUMAP for 3-D projection
└── model_runner.py # SyntheticRunner + HFTransformerRunner
server.py            # FastAPI + WebSocket glue
examples/            # demo entry points
```

The protocol is the only contract with the frontend — if you want
to swap in a different model implementation (nnsight, vLLM,
custom CUDA, etc.), just produce `Frame` instances and stream
them. Everything else is unchanged.

## WebSocket protocol

See `docs/PROTOCOL.md` in the project root for the full spec.

Quick summary:

- **Server → Client (Frame)** — sent once per token, contains 3-D
  path points for baseline and steered runs, top-K next-token
  predictions, scalar metrics, and a small projection of the
  steering vector for the front-end arrow.
- **Client → Server (ControlMessage)** — `start`, `cancel`,
  `set_alpha`, `set_preset`, `set_layer`, `reset`.

## Adding a new preset

Edit `core/protocol.py`'s `DEFAULT_PRESETS` dict:

```python
DEFAULT_PRESETS = {
    "my_new_preset": {
        "positive": "Prompt that strongly elicits the trait",
        "negative": "Prompt that strongly suppresses it",
    },
    ...
}
```

At boot, `extract_all_presets()` runs each contrastive pair
through the model and stores the resulting unit vector under
`PRESET_VECTORS[name]`.

## Adding SAE features

Replace the simple `OnlinePCA` in `model_runner.py` with a hybrid
pipeline:

1. Pull the residual stream as usual.
2. Encode via `sae_lens.SAE.from_pretrained(...)`.
3. Treat the top-K SAE indices as a sparse "feature vector" of
   length `d_sae` (e.g. 32 768).
4. Project that vector into 3-D via PCA / UMAP (same code path).

The frontend doesn't care whether the projection axis came from
a raw residual stream or a sparse SAE code; both produce a 3-D
point per token.

## Performance notes

- The synthetic demo generates ~20 frames per second. The
  pipeline uses ~50 ms per frame, so there's headroom for a real
  model on a single A100.
- `OnlinePCA` refits every 16 frames (in `_refit_components`)
  on the rolling 256-point window. The dominant cost is the SVD;
  switch to `IncrementalPCA` (default) which is `O(window * d)`.
- For >1M tokens, switch `OnlinePCA` to a fixed PCA basis that
  you pre-fit on a calibration set; or use a true online
  algorithm like CCIPCA / Oja's.