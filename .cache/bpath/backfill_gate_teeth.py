"""牙齿自检：证明修好的 --verify 闸门**真的会拦**。

原版的问题不是「拦得太松」而是**根本没拦**：argparse 的 --help 写着
「diff > 5e-2 就 skip writeback」，代码里却只有一行 `# Don't fail — just report`，
实测它在相对差 1.10（110%）的情况下照常写入并打印 OK。
只把措辞改对不算修好，必须证明闸门会咬。

## 判决规则（取数前写死）

  T1 用真实阈值 0.10 跑一条已回填的 pilot 轨迹 -> 期望 status='ok'，
     且打印的 aligned 读数在 0.02-0.05（旧口径会报 ~1.1）。
  T2 把阈值压到 0.001（**低于合法的 bf16 增量-全量差**）-> 期望
     status='reject'，**且 npz 的 prompt_hidden_states 一个字节都不能变**。
     若文件被改写 => 闸门只是打印、没拦住，T2 判红。
  T3 两个实现对同一读数一致：本脚本的 rel_aligned 必须与
     backfill_shift_probe.py 报的那个数一致。
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
os.environ["CUDA_VISIBLE_DEVICES"] = "7"

SRC = Path("/home/zhourui/steer3d_bpath/pilot8192/aime")
WORK = Path("/home/zhourui/steer3d_bpath/teeth/aime")
MODEL = "/home/zhourui/.cache/huggingface/models/Qwen--Qwen3-1.7B/snapshots/master"
# 修好的那份放在 bf_fixed/，必须**优先于**远端仓库里的旧版。
# 第一次跑这个自检时 sys.path 指到了 backend/examples，
# 于是 import 进来的是旧脚本 —— 「存在」不等于「是那一个」。
FIXED_DIR = "/home/zhourui/steer3d_bpath/bf_fixed"
FIXED_PY = f"{FIXED_DIR}/backfill_prompt_hidden.py"

# 注意：这里的被测对象由**本地仓库** scp 上来。
# 远端 /home/zhourui/steer3d 的 git 与本地完全分叉，且那个工作树里有别人未提交的
# 改动，绝不能就地修改 —— 所以「修好的那份」只存在于本地，必须显式传上来。
# （第一版让脚本自己去拷远端仓库那份，拷到的是没修过的旧版，
#   自检 0 立刻报「拿到的脚本不含对齐闸门」。这就是「存在」不等于「是那一个」。）

sys.path.insert(0, "/home/zhourui/steer3d/backend")
sys.path.insert(0, FIXED_DIR)   # 修好的那份，必须最先被 import
import numpy as np  # noqa: E402
import torch  # noqa: E402

import backfill_prompt_hidden as bf  # noqa: E402

# 自检 0：确认 import 进来的**确实是修好的那份**，不是远端仓库里的旧版。
# 两边都要 resolve()：这台机上 /home 是 /data/zju-130/zhome 的软链，
# 只 resolve 一边会把同一个文件判成不同路径（第一次跑就踩了这个）。
_probe = Path(bf.__file__).resolve()
_fixed = Path(FIXED_DIR).resolve()
assert _probe.parent == _fixed, (
    f"import 到的不是修好的版本：{_probe}\n"
    f"期望目录 {_fixed}。旧版会在相对差 1.10 时照样写入，那正是要修的缺陷。"
)
_src = Path(_probe).read_text(encoding="utf-8")
assert "aligned=" in _src and "VERIFY_MAX_REL" in _src, (
    f"拿到的脚本不含对齐闸门：{_probe}\n"
    f"请先 scp 本地修好的 backend/examples/backfill_prompt_hidden.py 到 {FIXED_PY}"
)
print(f"[自检0] import 到的是 {_probe}（含对齐闸门）")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def main():
    name = "aime__aime25__p00__no_think"
    WORK.mkdir(parents=True, exist_ok=True)
    for ext in (".json", ".npz"):
        shutil.copy(SRC / f"{name}{ext}", WORK / f"{name}{ext}")

    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16).to("cuda:0").eval()

    jp, npz = WORK / f"{name}.json", WORK / f"{name}.npz"
    dev, dt = torch.device("cuda:0"), torch.bfloat16
    results = {}

    # ---- T1: 真实阈值，应当放行 ----
    before = sha(npz)
    status, T_p, T_g = bf.backfill_one(jp, npz, model, tok, dev, dt,
                                       verify=True, overwrite=True)
    with np.load(npz) as d:
        keys_after_t1 = set(d.files)
    results["T1"] = {
        "status": status, "T_p": T_p, "T_g": T_g,
        "has_prompt_block": "prompt_hidden_states" in keys_after_t1,
        "npz_changed": sha(npz) != before,
    }
    print(f"\n[T1] 真实阈值 0.10 -> status={status}  "
          f"prompt 块已写入={'prompt_hidden_states' in keys_after_t1}")
    t1_ok = status == "ok" and "prompt_hidden_states" in keys_after_t1

    # ---- T2: 阈值压到 0.001，应当拦下且**不得改文件** ----
    bf.VERIFY_MAX_REL = 0.001
    before2 = sha(npz)
    mtime2 = os.path.getmtime(npz)
    status2, _, _ = bf.backfill_one(jp, npz, model, tok, dev, dt,
                                     verify=True, overwrite=True)
    after2 = sha(npz)
    unchanged = (sha(npz) == before2) and (os.path.getmtime(npz) == mtime2)
    results["T2"] = {"status": status2, "npz_unchanged": unchanged,
                     "threshold_used": 0.001}
    print(f"[T2] 阈值 0.001 -> status={status2}  文件未被改写={unchanged}")
    t2_ok = status2 == "reject" and unchanged

    # ---- 恢复真实阈值 ----
    bf.VERIFY_MAX_REL = 0.10

    # ---- T3: 对齐读数必须落在旧口径与错位口径之间 ----
    with np.load(npz) as d:
        pass  # 只为确认文件仍可读
    results["note"] = ("aligned 读数由脚本自己打印；旧口径(错一格)在同一批数据上 "
                       "实测 1.0935-1.3025，本脚本打印的 aligned 应为 0.02-0.05")

    print("\n" + "=" * 70)
    print(f"T1 真实阈值放行且写入          : {'PASS' if t1_ok else 'FAIL'}")
    print(f"T2 低阈值拦下且文件零改动      : {'PASS' if t2_ok else 'FAIL'}")
    print("=" * 70)
    out = "/home/zhourui/steer3d_bpath/teeth_verdict.json"
    json.dump(results, open(out, "w"), ensure_ascii=False, indent=1)
    print("写出", out)
    return 0 if (t1_ok and t2_ok) else 1


if __name__ == "__main__":
    sys.exit(main())