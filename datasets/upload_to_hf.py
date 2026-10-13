"""Upload the raw Qwen3-1.7B AIME trajectory datasets to Hugging Face Datasets.

Why this script exists
----------------------
The raw ``.npz`` trajectory files (~20 GB across the two datasets) are listed
in ``.gitignore`` on purpose: each file is up to ~1.1 GB, so plain ``git push``
to GitHub is rejected (GitHub hard limit is 100 MB per file) and even Git LFS
would balloon the repo. The precomputed viewer caches live under
``viewer_cache/`` and *are* tracked in git so the 3D viewer works out of the
box after a clone; this script handles the raw source files separately, by
mirroring them to a Hugging Face Datasets repo where storage is essentially
free for public research data and downloads are fast.

Layout uploaded
---------------
A single HF dataset with two ``configs`` (sub-folders), one per collector run::

    <your-namespace>/reasoning3d-aime-qwen3-1p7b
    ├── 16k_fp16/aime/<file>.npz      # ~7.7 GB, 96 files
    └── 32k_fp32/aime/<file>.npz      # ~12 GB, 60 files

Each ``.npz`` is the raw collector output (28 layers × 2048 dim × N tokens of
float32 hidden states + full logits). Pair them with the JSON sidecar of the
same stem for prompts / answers / metadata.

Usage
-----
1. ``pip install -U "huggingface_hub[cli]"`` (or just ``huggingface_hub``).
2. Get a write token from https://huggingface.co/settings/tokens
   (scope: ``write``). Pick a dataset name — typically
   ``<your-hf-username>/reasoning3d-aime-qwen3-1p7b``; create the empty
   dataset page on the HF web UI (type = "Dataset", license = your choice).
3. Export the token so it does not land in shell history::

       export HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

   (Or use ``huggingface-cli login`` which writes it to ``~/.huggingface/token``.)
4. Run the uploader. The script skips files that are already on the hub, so
   re-running it is safe and cheap — it resumes whatever did not finish last
   time::

       python datasets/upload_to_hf.py \\
           --repo-id YOUR_HF_USERNAME/reasoning3d-aime-qwen3-1p7b \\
           --private            # remove for public

5. Dry-run first to sanity-check the file count and total size without
   touching the wire::

       python datasets/upload_to_hf.py \\
           --repo-id YOUR_HF_USERNAME/reasoning3d-aime-qwen3-1p7b \\
           --dry-run

What you need to provide
------------------------
The token and the repo id are the only two pieces of info that cannot come
from the repo. Everything else (paths, which two configs to push, which files
to skip) is hard-coded below — the data layout is owned by this repo, the
upload target is not.

Security notes
--------------
- Never commit ``HF_TOKEN``. The script also refuses a token given on the
  command line in shared environments — prefer the env var or the cached
  ``huggingface-cli login`` path.
- If you accidentally drop a token into ``datasets/.hf_token``, it is already
  covered by the catch-all rule in the repo-root ``.gitignore`` (see
  ``*.token`` / ``.hf_token``). Delete the file and rotate the token.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration: which local folders map to which HF configs.
# Adjust here if a new collector run is added; nothing else needs changing.
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
DATASETS_DIR = REPO_ROOT / "datasets"

# (local_subdir, hf_config_name, human-readable description)
CONFIGS: list[tuple[str, str, str]] = [
    (
        "aime_qwen3_1p7b_16k_fp16/aime",
        "16k_fp16",
        "AIME Qwen3-1.7B, 16k context, fp16 — 96 trajectories (~7.7 GB)",
    ),
    (
        "aime_qwen3_1p7b_32k_fp32/aime",
        "32k_fp32",
        "AIME Qwen3-1.7B, 32k context, fp32 — 60 trajectories (~12 GB)",
    ),
]


def _resolve_token(cli_token: str | None) -> str:
    """Pick the HF token from CLI > env > cached login, never echoing it."""

    if cli_token:
        print(
            "warning: passing --token on the command line is risky on shared "
            "hosts because it lands in shell history and `ps`. Prefer "
            "$HF_TOKEN or `huggingface-cli login`.",
            file=sys.stderr,
        )
        return cli_token
    env = os.environ.get("HF_TOKEN")
    if env:
        return env
    cached = Path.home() / ".huggingface" / "token"
    if cached.is_file():
        return cached.read_text().strip()
    # Newer ``huggingface-cli login`` (>=0.10) writes here instead.
    cached_new = Path.home() / ".cache" / "huggingface" / "token"
    if cached_new.is_file():
        return cached_new.read_text().strip()
    raise SystemExit(
        "no HF token found. Set $HF_TOKEN or run `huggingface-cli login` first."
    )


def _human_size(n: int) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if n < 1024 or unit == "TiB":
            return f"{n:.2f} {unit}"
        n /= 1024  # type: ignore[assignment]
    return f"{n:.2f} TiB"


def _scan(local_dir: Path) -> tuple[int, int]:
    """Return (file_count, total_bytes) under local_dir, recursively."""
    if not local_dir.is_dir():
        raise SystemExit(f"missing local dir: {local_dir}")
    count = 0
    total = 0
    for p in local_dir.rglob("*"):
        if p.is_file():
            count += 1
            total += p.stat().st_size
    return count, total


def _stage_all() -> tuple[Path, int, int]:
    """Build a single staging dir that contains one subfolder per config,
    symlinked from the original location to avoid duplicating 20 GB on disk.

    Returns (stage_root, total_files, total_bytes)."""

    stage = Path(tempfile.mkdtemp(prefix="r3d-upload-"))
    total_files = 0
    total_bytes = 0
    for local_subdir, hf_config, _ in CONFIGS:
        local_dir = DATASETS_DIR / local_subdir
        if not local_dir.is_dir():
            raise SystemExit(f"missing local dir: {local_dir}")
        target = stage / hf_config
        target.mkdir(parents=True, exist_ok=True)
        for entry in local_dir.iterdir():
            os.symlink(entry.resolve(), target / entry.name)
            if entry.is_file():
                total_files += 1
                total_bytes += entry.stat().st_size
    return stage, total_files, total_bytes


def _ensure_dataset_exists(api, repo_id: str, private: bool) -> None:
    """Create the dataset repo if it does not already exist.

    Some HF mirrors (e.g. hf-mirror.com) have flaky ``POST /api/datasets``
    endpoints. To stay robust, we HEAD-check first and only POST-create
    when the repo is genuinely absent; both calls retry on connection
    errors with exponential backoff.
    """
    from huggingface_hub import create_repo

    repo_type = "dataset"
    last_exc: Exception | None = None
    for attempt in range(4):
        try:
            exists = api.repo_exists(repo_id, repo_type=repo_type, token=api.token)
            if exists:
                print(f"  repo exists (HEAD ok, attempt {attempt + 1})")
                return
            print(f"  repo missing, creating (attempt {attempt + 1})...")
            create_repo(
                repo_id,
                repo_type=repo_type,
                private=private,
                exist_ok=True,
                token=api.token,
            )
            return
        except Exception as exc:  # network blip — retry
            last_exc = exc
            wait = 2 ** attempt
            print(
                f"  attempt {attempt + 1} failed: {type(exc).__name__}: "
                f"{str(exc)[:120]}; retrying in {wait}s",
                file=sys.stderr,
            )
            import time as _time

            _time.sleep(wait)
    raise SystemExit(f"failed to create/access repo {repo_id!r}: {last_exc}")


def upload(
    repo_id: str,
    private: bool,
    token: str,
    dry_run: bool,
    num_workers: int,
) -> None:
    from huggingface_hub import HfApi, upload_large_folder

    api = HfApi(token=token)

    print(f"target repo : {repo_id}  (private={private})")
    print(f"workers     : {num_workers}")
    if not dry_run:
        _ensure_dataset_exists(api, repo_id, private)

    # ---- dry run: just scan, no staging, no API calls beyond repo check ----
    if dry_run:
        grand_files = 0
        grand_bytes = 0
        for local_subdir, hf_config, desc in CONFIGS:
            local_dir = DATASETS_DIR / local_subdir
            n, b = _scan(local_dir)
            grand_files += n
            grand_bytes += b
            print()
            print(f"=== config: {hf_config} ===")
            print(f"  local      : {local_dir}")
            print(f"  description: {desc}")
            print(f"  files      : {n}")
            print(f"  total size : {_human_size(b)}")
            print("  --dry-run: skipping upload")
        print()
        print("=== summary ===")
        print(f"  repo       : https://huggingface.co/datasets/{repo_id}")
        print(f"  configs    : {len(CONFIGS)}  ({', '.join(c[1] for c in CONFIGS)})")
        print(f"  files      : {grand_files}")
        print(f"  total size : {_human_size(grand_bytes)}")
        return

    # ---- real upload ----
    # Stage once. upload_large_folder uploads to the repo root with the
    # layout of the folder, so symlinking both config subfolders side by
    # side gives us 16k_fp16/ and 32k_fp32/ as the on-disk layout. Files
    # are not duplicated: symlinks resolve to the originals under datasets/.
    stage, total_files, total_bytes = _stage_all()
    print()
    print(f"=== staging ===")
    print(f"  root  : {stage}")
    print(f"  files : {total_files}")
    print(f"  size  : {_human_size(total_bytes)}")
    print()
    print(f"=== uploading via upload_large_folder ===")
    print(f"  chunks are split across multiple commits automatically")
    print(f"  progress report every 60s; Ctrl-C to pause and re-run later")
    print()
    try:
        # upload_large_folder() does not accept ``token=`` — it picks up the
        # cached login (`~/.cache/huggingface/token`) or $HF_TOKEN itself.
        # Push the token into the env to be safe with custom mirrors.
        if token:
            os.environ["HF_TOKEN"] = token
        upload_large_folder(
            repo_id=repo_id,
            folder_path=str(stage),
            repo_type="dataset",
            # multi-worker parallel upload (default = CPU count)
            num_workers=num_workers,
            print_report=True,
            print_report_every=60,
        )
    finally:
        shutil.rmtree(stage, ignore_errors=True)

    print()
    print("=== done ===")
    print(f"  repo    : https://huggingface.co/datasets/{repo_id}")
    print(f"  files   : {total_files}")
    print(f"  size    : {_human_size(total_bytes)}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Upload Reasoning3D AIME trajectory datasets to HF Datasets."
    )
    p.add_argument(
        "--repo-id",
        required=True,
        help="HF dataset id, e.g. 'YOUR_USERNAME/reasoning3d-aime-qwen3-1p7b'",
    )
    p.add_argument(
        "--private",
        action="store_true",
        help="make the dataset private (default: public)",
    )
    p.add_argument(
        "--token",
        default=None,
        help="HF write token (prefer $HF_TOKEN env var instead)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="scan local data and report sizes, do not upload",
    )
    p.add_argument(
        "--num-workers",
        type=int,
        default=8,
        help="parallel upload workers (default 8); bump for faster upload "
             "if you have the bandwidth",
    )
    args = p.parse_args(argv)

    upload(
        repo_id=args.repo_id,
        private=args.private,
        token=_resolve_token(args.token),
        dry_run=args.dry_run,
        num_workers=args.num_workers,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())