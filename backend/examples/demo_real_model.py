"""Real-model demo (requires GPU + transformers).

Boot a HuggingFace causal LM and stream its reasoning trace +
per-token hidden states through the WebSocket. This is the
template you fill in to connect your own model.

Key steps:
  1. Load the model (HF + tokenizer)
  2. Use your vector-injection logic. The default is a no-op
     placeholder; replace with whatever you want to study.
  3. Implement streaming token generation, capturing activations
     at `layer_idx` for the new last token after the forward.
  4. Compute perplexity / entropy from logits.
  5. Emit Frame objects to the WebSocket.

The synthetic demo shows the full visualization working end-to-end;
once this template is filled in, the frontend stays unchanged.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from server import app  # noqa: F401
from core import install_residual_add_hook, remove_hook
from core.model_runner import HFTransformerRunner
from core.projector import OnlinePCA

import numpy as np
import uvicorn


async def main_async(args):
    print(f"[demo_real_model] Loading {args.model}...")
    runner = HFTransformerRunner(model_name=args.model)

    projector = OnlinePCA(d=runner.d_model, target_dim=3, window=256)

    # ----- Vector injection stub ------------------------------------
    # Replace this with whatever logic you want to study. It is
    # called before each token; whatever vector it returns is
    # injected into the residual stream at `layer_idx` via
    # install_residual_add_hook. Return None to skip injection.
    def inject_vector(step_id: int, token: str) -> np.ndarray | None:
        # Example: inject a fixed "sycophancy" direction every 5 steps.
        if step_id % 5 != 0:
            return None
        rng = np.random.default_rng(args.layer)
        v = rng.standard_normal(runner.d_model).astype(np.float32) * 0.5
        return v

    print("[demo_real_model] Loaded; runner + injector ready.")
    print("[demo_real_model] NOTE: HFTransformerRunner.stream() is a scaffold.")
    print("Fill it in (see comments in model_runner.py). The synthetic")
    print("demo proves the wire protocol works end-to-end.")
    print("[demo_real_model] Booting uvicorn on port", args.port)

    config = uvicorn.Config(app, host="0.0.0.0", port=args.port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="meta-llama/Llama-3.1-8B-Instruct")
    ap.add_argument("--layer", type=int, default=14)
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()