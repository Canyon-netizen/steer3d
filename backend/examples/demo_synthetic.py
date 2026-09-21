"""Run the synthetic demo (no GPU needed).

Usage:
    python examples/demo_synthetic.py

Boots FastAPI on http://localhost:8000 with a synthetic runner that
produces a CoT-shaped 3-D trajectory. Then open the frontend to
watch it stream in real time.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make `core` importable when running this file directly
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import uvicorn

if __name__ == "__main__":
    print("=" * 60)
    print("Reasoning3D — Synthetic Demo")
    print("=" * 60)
    print("WebSocket:  ws://localhost:8000/ws")
    print("HTTP root:  http://localhost:8000/")
    print("Open the frontend (cd ../frontend && npm run dev) to view")
    print("the 3-D visualization. Press Ctrl-C to stop.")
    print("=" * 60)
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)