# `datasets/` — AIME trajectory datasets for Reasoning3D

This folder holds the two Qwen3-1.7B AIME collector runs the 3D viewer was
built on. Each run is one subfolder; each subfolder contains two more:

```
datasets/
├── aime_qwen3_1p7b_16k_fp16/
│   ├── aime/             # raw trajectories (.npz) — gitignored, ~7.7 GB
│   └── viewer_cache/     # precomputed per-layer JSON — tracked in git
└── aime_qwen3_1p7b_32k_fp32/
    ├── aime/             # raw trajectories (.npz) — gitignored, ~12 GB
    └── viewer_cache/     # precomputed per-layer JSON — tracked in git
```

| Subdir                | Context | Precision | Files | Size   |
|-----------------------|---------|-----------|-------|--------|
| `aime_qwen3_1p7b_16k_fp16` | 16k     | fp16      | 96    | ~7.7 GB |
| `aime_qwen3_1p7b_32k_fp32` | 32k     | fp32      | 60    | ~12 GB  |

## What's tracked in git vs. what's not

- **Tracked (`viewer_cache/`)**: precomputed per-layer JSON (~17–23 MB each,
  no single file >50 MB so plain git works without LFS). After a normal clone
  the 3D viewer works out of the box — no extra download needed.
- **Ignored (`aime/`)**: the raw `.npz` trajectory files. Up to ~1.1 GB each
  (>100 MB each, 60 of them), which GitHub rejects outright. Even with LFS
  the resulting repo would be heavy. Keep these local; mirror them to
  external storage separately (see below).

## Mirroring the raw data to Hugging Face Datasets

A helper script lives at [`upload_to_hf.py`](upload_to_hf.py). It pushes both
`aime/` folders to a single HF dataset with two configs (`16k_fp16` and
`32k_fp32`), so anyone can `datasets.load_dataset(...)` or pull files
individually with `huggingface-cli download`.

```bash
# one-time setup
pip install -U "huggingface_hub[cli]"
huggingface-cli login        # paste a write token from
                             # https://huggingface.co/settings/tokens

# dry run — confirm file counts and sizes without touching the wire
python datasets/upload_to_hf.py \
    --repo-id YOUR_HF_USERNAME/reasoning3d-aime-qwen3-1p7b \
    --dry-run

# actual upload (re-runnable; skipped files are not re-sent)
python datasets/upload_to_hf.py \
    --repo-id YOUR_HF_USERNAME/reasoning3d-aime-qwen3-1p7b \
    --private    # remove for public
```

The HF token must come from `$HF_TOKEN` (or `huggingface-cli login`); the
script deliberately warns if you pass it on the command line.

After the upload completes, the dataset page looks like:

```
https://huggingface.co/datasets/YOUR_HF_USERNAME/reasoning3d-aime-qwen3-1p7b
├── 16k_fp16/aime/<problem>__<mode>.npz
└── 32k_fp32/aime/<problem>__<mode>.npz
```

## Re-creating the data from scratch

The collectors under `backend/examples/` regenerate the raw `aime/`
trajectories. The viewer cache (`viewer_cache/`) is then built by
`backend/examples/build_per_layer.py`. See the top-level `README.md` for
the end-to-end pipeline.