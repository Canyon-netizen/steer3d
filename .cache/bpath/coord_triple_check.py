"""坐标系三方核对：npz 的 hidden_states、侧车的 extra.prompt_tokens、注入时的 len(pid)。

## 为什么必须三方一起核

`r6_rerun.py` 的注入切片是 `ids[: m["P"] + t]`，其中
- `ids = pid + gen`，`pid` 是**当场重新分词** `chat_template_input` 得到的，
- `m["P"]` 是**侧车里记的** `extra.prompt_tokens`。

这两个数如果不相等，切片就切在错误的 token 上。
而 `load_xy` 读的是 npz 的 `hidden_states`，它又是**第三套**索引
（实测为「相对生成起点」，P_actual = 0）。

三套索引里只要有两套口径不一致，训练位置与注入位置就对不上——
而且**不报错、不崩**。

## 判据（取数前写死）

  C1 npz 的 `H.shape[0]` 是否等于 `n_generated_tokens`（即 H 是否只含生成段）
  C2 `len(pid)` 是否等于侧车的 `extra.prompt_tokens`
  C3 若 C1 成立，则注入位置（绝对 P+t-1）在 npz 里的下标恒为 **t-1**
  C4 三方口径不一致的轨迹数必须报出来，不许只报中位数
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import zipfile
from pathlib import Path

import numpy as np
from numpy.lib import format as npformat


def npz_shape(path, key):
    """只读 .npy 头部拿形状，**不加载数组**。

    hidden_states 动辄几百 MB，读全数组会把核对脚本拖死——
    而这里只需要 shape。
    """
    with zipfile.ZipFile(path) as z:
        with z.open(key + ".npy") as f:
            version = npformat.read_magic(f)
            rd = (npformat.read_array_header_1_0 if version == (1, 0)
                  else npformat.read_array_header_2_0)
            shape, _fortran, dtype = rd(f)
            return shape, str(dtype)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--npz-dir", required=True)
    ap.add_argument("--sidecar-dir", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(a.model)

    rows, c1_bad, c2_bad = [], 0, 0
    for i, f in enumerate(sorted(Path(a.npz_dir).glob("*.json"))):
        if i >= a.limit:
            break
        j = json.load(open(f, encoding="utf-8"))
        tid = j["trajectory_id"]
        H_shape, H_dtype = npz_shape(Path(a.npz_dir) / f"{tid}.npz", "hidden_states")
        gen_shape, _ = npz_shape(Path(a.npz_dir) / f"{tid}.npz", "token_ids")
        H_len = int(H_shape[0])
        gen_len = int(gen_shape[0])
        T = j["n_generated_tokens"]
        P_side = (j.get("extra") or {}).get("prompt_tokens")
        pid = tok(j["chat_template_input"], return_tensors="pt",
                  add_special_tokens=False).input_ids[0].tolist()
        c1 = (H_len == T == gen_len == len(j.get("tokens") or []))
        c2 = (len(pid) == P_side)
        if not c1:
            c1_bad += 1
        if not c2:
            c2_bad += 1
        rows.append({"tid": tid, "H_len": H_len, "T": int(T),
                     "len_pid": len(pid), "P_sidecar": P_side,
                     "c1_H_is_generation_only": bool(c1), "c2_pid_eq_sidecar": bool(c2)})
        print(f"  {tid[:36]:36s} H={H_len:5d} T={T:5d} len(pid)={len(pid):4d} "
              f"extra={P_side}  C1={'ok' if c1 else 'BAD'} C2={'ok' if c2 else 'BAD'}")

    n = len(rows)
    print()
    print("=" * 74)
    print(f"C1 npz 的 hidden_states 等于生成段: {n - c1_bad}/{n}")
    print(f"C2 len(pid) 等于侧车 extra.prompt_tokens: {n - c2_bad}/{n}")
    dl = [r["len_pid"] - r["P_sidecar"] for r in rows if r["P_sidecar"] is not None]
    if dl:
        print(f"   len(pid) - extra 中位 {st.median(dl):.0f} 范围 {min(dl)}~{max(dl)}")
    if c1_bad == 0:
        print("C3 => 注入位置（绝对 P+t-1）在 npz 里的下标恒为 **t-1**")
    print(f"C4 口径不一致的轨迹：C1 {c1_bad} 条、C2 {c2_bad} 条")

    json.dump({"n": n, "c1_bad": c1_bad, "c2_bad": c2_bad, "rows": rows},
              open(a.out, "w"), ensure_ascii=False, indent=1)
    print("\n写出", a.out)


if __name__ == "__main__":
    main()
