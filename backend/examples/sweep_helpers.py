"""Helpers for the 32k sweep, kept as real .py files rather than heredocs.

Heredocs inside the shell driver cost two debugging rounds already: a shell
file that opened with a Python docstring, and an assert whose f-string
referenced a variable that only existed in the outer shell. Plain files fail
loudly and can be run standalone to check.
"""
import json
import os
import sys


def slice_helper():
    src, dst, idx, n = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    rows = json.load(open(src))
    mine = [r for i, r in enumerate(rows) if i % n == idx]
    if not mine:
        raise SystemExit(f"shard {idx}/{n} came out empty")
    json.dump(mine, open(dst, "w"), ensure_ascii=False, indent=1)
    ids = ", ".join(r["id"] for r in mine)
    print(f"  shard {idx}: {len(mine)} problems -> {ids}")


def one_helper():
    """Write a single-problem index. Fails loudly if the id is not ours."""
    src, dst, pid = sys.argv[1], sys.argv[2], sys.argv[3]
    rows = json.load(open(src))
    hit = [r for r in rows if r["id"] == pid]
    if len(hit) != 1:
        raise SystemExit(f"slice {src} has {len(hit)} rows for {pid}, expected 1")
    json.dump(hit, open(dst, "w"), ensure_ascii=False, indent=1)


def append_helper():
    """Append one invocation's results to the shard journal, one JSON per line."""
    src, journal, shard, gpu = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    data = json.load(open(src))
    if not isinstance(data, list):
        data = [data]
    with open(journal, "a", encoding="utf-8") as f:
        for r in data:
            r["_shard"] = int(shard)
            r["_gpu"] = gpu
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())  # a killed process must not lose a journalled run
    print(f"  appended {len(data)} result(s)")


if __name__ == "__main__":
    # argv[1] is the function name; shift it away so each helper can keep
    # reading its own arguments from argv[1:].
    name, sys.argv = sys.argv[1], [sys.argv[0]] + sys.argv[2:]
    {"slice_helper": slice_helper,
     "one_helper": one_helper,
     "append_helper": append_helper}[name]()
