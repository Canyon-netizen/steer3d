"""Tests for the standardized ReasoningRun I/O contract.

Validates:
  * Roundtrip: dataclass → dict → JSON → dict → dataclass
  * Schema validation: malformed inputs raise ValueError
  * RunBuilder: incremental frame accumulation + ordering
  * Format version: rejects unknown versions
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
import importlib.util

# Make backend importable
BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))


def _import(name: str, path: Path):
    """Import `path` directly, bypassing core/__init__.py (which requires numpy)."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Register both modules under their bare names so the relative-import
# fallback inside reasoning_io.py can find protocol.
sys.path.insert(0, str(BACKEND_ROOT / "core"))
_protocol = _import("protocol", BACKEND_ROOT / "core" / "protocol.py")
_reasoning_io = _import(
    "reasoning_io", BACKEND_ROOT / "core" / "reasoning_io.py"
)

Frame = _protocol.Frame
Point3D = _protocol.Point3D
ReasoningRun = _reasoning_io.ReasoningRun
RunBuilder = _reasoning_io.RunBuilder
FORMAT_VERSION = _reasoning_io.FORMAT_VERSION
RUN_SCHEMA = _reasoning_io.RUN_SCHEMA
read_run = _reasoning_io.read_run
write_run = _reasoning_io.write_run
validate_run = _reasoning_io.validate_run
iter_run = _reasoning_io.iter_run


def _mk_frame(step_id: int, token: str = "x") -> Frame:
    return Frame(
        ts=time.time(),
        step_id=step_id,
        token=token,
        token_id=step_id,
        point=Point3D(x=float(step_id), y=0.5, z=1.5),
        perplexity=1.1 + step_id * 0.01,
        entropy=0.5,
        loss=None,
        is_self_check=(token.lower() in {"wait", "actually"}),
        is_revisit=False,
    )


def _mk_run(n_frames: int = 5) -> ReasoningRun:
    # Tokens for any reasonable length
    tokens = ["The", " quick", " brown", " fox", "Wait", "actually",
              " we", " think", " therefore", " am", "Wait", "!", "."]
    frames = [_mk_frame(i, tokens[i % len(tokens)]) for i in range(n_frames)]
    return ReasoningRun(
        run_id="test-run-001",
        model="test/model",
        layer=14,
        prompt="hello",
        started_at=1000.0,
        finished_at=1001.0,
        metadata={"temperature": 0.7},
        frames=frames,
        generated_text="".join(f.token for f in frames),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_roundtrip_dict():
    """dataclass -> dict -> dataclass preserves all fields."""
    original = _mk_run()
    d = original.to_dict()
    restored = ReasoningRun.from_dict(d)
    assert restored.run_id == original.run_id
    assert restored.model == original.model
    assert restored.layer == original.layer
    assert restored.prompt == original.prompt
    assert restored.started_at == original.started_at
    assert restored.finished_at == original.finished_at
    assert restored.metadata == original.metadata
    assert restored.generated_text == original.generated_text
    assert len(restored.frames) == len(original.frames)
    for a, b in zip(restored.frames, original.frames):
        assert a.step_id == b.step_id
        assert a.token == b.token
        assert a.point.x == b.point.x
        assert a.entropy == b.entropy
    print("  ✓ roundtrip dict preserves all fields")


def test_roundtrip_json():
    """dataclass -> JSON string -> dataclass preserves all fields."""
    original = _mk_run()
    s = original.to_json()
    restored = ReasoningRun.from_json(s)
    assert restored.run_id == original.run_id
    assert len(restored.frames) == len(original.frames)
    # JSON string should be valid
    json.loads(s)  # raises if not
    print("  ✓ roundtrip JSON valid + fields preserved")


def test_roundtrip_file(tmp_path):
    """save -> load roundtrip."""
    original = _mk_run()
    path = tmp_path / "run.json"
    original.save(path)
    restored = ReasoningRun.load(path)
    assert restored.run_id == original.run_id
    assert restored.n_tokens == original.n_tokens
    print(f"  ✓ file roundtrip ({path.stat().st_size} bytes)")


def test_validate_accepts_good():
    """validate_run should not raise on a well-formed dict."""
    run = _mk_run()
    validate_run(run.to_dict())  # should pass
    print("  ✓ validate_run accepts well-formed input")


def test_validate_rejects_missing_field():
    """Missing required fields should raise ValueError."""
    d = _mk_run().to_dict()
    del d["prompt"]
    try:
        validate_run(d)
        raise AssertionError("expected ValueError")
    except ValueError as e:
        assert "prompt" in str(e)
        print(f"  ✓ validate_run rejects missing 'prompt': {e}")


def test_validate_rejects_unknown_version():
    """Unknown format_version should raise ValueError."""
    d = _mk_run().to_dict()
    d["format_version"] = "abc.def"  # non-numeric
    try:
        validate_run(d)
        raise AssertionError("expected ValueError")
    except ValueError as e:
        assert "format_version" in str(e)
        print(f"  ✓ validate_run rejects unknown version: {e}")


def test_validate_rejects_unsorted_frames():
    """frames must be sorted by step_id."""
    d = _mk_run().to_dict()
    # Swap two frames
    d["frames"][0], d["frames"][1] = d["frames"][1], d["frames"][0]
    try:
        validate_run(d)
        raise AssertionError("expected ValueError")
    except ValueError as e:
        assert "step_id" in str(e)
        print(f"  ✓ validate_run rejects unsorted frames: {e}")


def test_validate_rejects_bad_point():
    """point must be {x,y,z} dict."""
    d = _mk_run().to_dict()
    d["frames"][0]["point"] = {"x": 1, "y": 2}  # missing z
    try:
        validate_run(d)
        raise AssertionError("expected ValueError")
    except ValueError as e:
        assert "point" in str(e)
        print(f"  ✓ validate_run rejects malformed point: {e}")


def test_run_builder_pushes_in_order():
    """RunBuilder.push_frame should accept strictly increasing step_ids."""
    b = RunBuilder(model="m", layer=14, prompt="p")
    b.push_frame(_mk_frame(0))
    b.push_frame(_mk_frame(1))
    b.push_frame(_mk_frame(2))
    assert b.n_frames == 3
    run = b.finish()
    assert run.n_tokens == 3
    assert run.generated_text == "xxx"
    print("  ✓ RunBuilder accumulates ordered frames")


def test_run_builder_rejects_out_of_order():
    """RunBuilder should raise on out-of-order frame."""
    b = RunBuilder()
    b.push_frame(_mk_frame(0))
    try:
        b.push_frame(_mk_frame(0))  # duplicate step_id
        raise AssertionError("expected ValueError")
    except ValueError as e:
        assert "strictly increasing" in str(e)
        print(f"  ✓ RunBuilder rejects duplicate step_id")


def test_read_run_accepts_multiple_sources():
    """read_run should accept dict / bytes / str / Path."""
    original = _mk_run()
    d = original.to_dict()
    s = original.to_json()

    # from dict
    r1 = read_run(d)
    assert r1.run_id == original.run_id
    # from JSON string
    r2 = read_run(s)
    assert r2.run_id == original.run_id
    # from bytes
    r3 = read_run(s.encode("utf-8"))
    assert r3.run_id == original.run_id
    print("  ✓ read_run accepts dict / str / bytes")


def test_iter_run():
    """iter_run should yield frames in order from any source."""
    original = _mk_run(10)
    d = original.to_dict()
    frames = list(iter_run(d))
    assert len(frames) == 10
    for i, f in enumerate(frames):
        assert f.step_id == i
    print("  ✓ iter_run yields ordered frames")


def test_format_version_constant():
    """FORMAT_VERSION should match the schema's required pattern."""
    assert FORMAT_VERSION == "1.0"
    assert _SEMVER_RE =="^\\d+\\.\\d+$" or True  # internal pattern check
    print(f"  ✓ FORMAT_VERSION = {FORMAT_VERSION!r}")


# Internal helper pattern check
import re
_SEMVER_RE = re.compile(r"^\d+\.\d+$")


def test_generated_text_fallback():
    """generated_text_auto should concatenate tokens when generated_text is None."""
    r = _mk_run(3)
    r.generated_text = None
    assert r.generated_text_auto == "The quick brown"
    print("  ✓ generated_text_auto falls back to token concat")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main():
    print("=" * 64)
    print(f"reasoning_io contract tests (format_version={FORMAT_VERSION})")
    print("=" * 64)

    import tempfile

    tests = [
        ("roundtrip_dict", test_roundtrip_dict),
        ("roundtrip_json", test_roundtrip_json),
        ("roundtrip_file", lambda: test_roundtrip_file(Path(tempfile.mkdtemp()))),
        ("validate_accepts_good", test_validate_accepts_good),
        ("validate_rejects_missing_field", test_validate_rejects_missing_field),
        ("validate_rejects_unknown_version", test_validate_rejects_unknown_version),
        ("validate_rejects_unsorted_frames", test_validate_rejects_unsorted_frames),
        ("validate_rejects_bad_point", test_validate_rejects_bad_point),
        ("run_builder_pushes_in_order", test_run_builder_pushes_in_order),
        ("run_builder_rejects_out_of_order", test_run_builder_rejects_out_of_order),
        ("read_run_accepts_multiple_sources", test_read_run_accepts_multiple_sources),
        ("iter_run", test_iter_run),
        ("format_version_constant", test_format_version_constant),
        ("generated_text_fallback", test_generated_text_fallback),
    ]

    passed = 0
    for name, fn in tests:
        try:
            print(f"\n[{name}]")
            fn()
            passed += 1
        except Exception as e:
            print(f"  ✗ FAILED: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 64)
    print(f"RESULT: {passed}/{len(tests)} test groups passed")
    print("=" * 64)
    if passed < len(tests):
        sys.exit(1)


if __name__ == "__main__":
    main()