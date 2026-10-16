# ⚠⚠ 修订 233 前置勘查：每格那 1-2 分钟**到底花在哪** —— 先量后排。
#
# ⚖⚖ 为什么必须先量：
#   症状是「40 格跑了 1-2 分钟/格」。但**候选原因不止一个**：
#     (a) 每格从 NFS 重载 3.4 GB 权重；
#     (b) 权重在本地盘但 GPU 初始化本身慢；
#     (c) npz 在 NFS 上、同 tid 的多个 k 反复读同一份；
#     (d) prefill 本身就贵（长序列 + 80 点 alpha 网格）。
#   ⛔ 不分清就动手 ⇒ 改完发现省的不是那一块。
#
# ⚖ 产出要求：**每一项单独计时 + 说明它在不在 NFS 上**，
#   两者合起来才能推出「改哪一处最值」。
import os
import subprocess
import time


_START = time.time()


def stamp(tag, t):
    print("[计时] %-38s %7.2f s" % (tag, time.time() - t), flush=True)


MODEL = "/home/zhourui/.cache/huggingface/models/Qwen--Qwen3-1.7B/snapshots/master"
NPZ_DIR = "/home/zhourui/steer3d_bpath/gen_b2_max32768/aime"

print("=== 0. 各路径在哪个挂载点上（NFS 与否）===", flush=True)
for p in ("/home/zhourui/.cache/huggingface",
          "/home/zhourui/steer3d_bpath",
          NPZ_DIR,
          "/home/zhourui/.cache/huggingface/models",
          "/tmp", "/data"):
    try:
        o = subprocess.run(["df", "-H", p], capture_output=True, text=True, timeout=30)
        line = o.stdout.strip().splitlines()[-1] if o.stdout else o.stderr.strip()
        print("  %-46s %s" % (p, line), flush=True)
    except Exception as e:
        print("  %-46s ERR %s" % (p, e), flush=True)

print("\n=== 0b. 权重文件逐个大小 ===", flush=True)
tot = 0
for root, _dirs, files in os.walk(MODEL):
    for f in sorted(files):
        fp = os.path.join(root, f)
        sz = os.path.getsize(fp)
        tot += sz
        print("  %10.1f MB  %s" % (sz / 1e6, f), flush=True)
print("  ---- 合计 %.2f GB ----" % (tot / 1e9), flush=True)

os.environ["CUDA_VISIBLE_DEVICES"] = "GPU-2828f5ba-f9ea-5e83-d270-4cb229dce027"

print("\n=== 1. 冷加载计时 ===", flush=True)
t = time.time()
import torch
stamp("import torch", t)
from transformers import AutoModelForCausalLM, AutoTokenizer
t = time.time()
tok = AutoTokenizer.from_pretrained(MODEL)
stamp("AutoTokenizer.from_pretrained", t)
t = time.time()
m = AutoModelForCausalLM.from_pretrained(MODEL, torch_dtype=torch.bfloat16)
stamp("from_pretrained（仅 CPU 侧读取）", t)
t = time.time()
m = m.cuda().eval()
stamp(".cuda().eval()（H2D + 分配）", t)
t = time.time()
_ = m.model.layers[20]
stamp("取 layers[20]", t)

print("\n=== 2. 一次 prefill（长序列那一种）===", flush=True)
for n in (490, 1762, 3786):
    ids = torch.arange(1, n + 1, device="cuda:0")[None]
    t = time.time()
    with torch.no_grad():
        o = m(input_ids=ids, use_cache=False, return_dict=True)
    stamp("prefill n=%d" % n, t)

print("\n=== 2b. 权重**复制到本地 NVMe** 后重载一次（量化 NFS 那部分）===", flush=True)
LOCAL = "/data/local_model_probe"
if not os.path.isdir(LOCAL):
    import shutil
    t = time.time()
    shutil.copytree(MODEL, LOCAL)
    stamp("copytree 4.08GB 到 /data（本地 NVMe）", t)
t = time.time()
_m2 = AutoModelForCausalLM.from_pretrained(LOCAL, torch_dtype=torch.bfloat16).cuda().eval()
stamp("本地盘 from_pretrained + .cuda()", t)
del _m2
import torch as _t; _t.cuda.empty_cache()

print("\n=== 3. npz 冷读 ===", flush=True)
import numpy as np
tids = sorted(f[:-4] for f in os.listdir(NPZ_DIR) if f.endswith(".npz"))[:3]
for tid in tids:
    t = time.time()
    z = np.load(os.path.join(NPZ_DIR, tid + ".npz"))
    g = z["token_ids"].tolist()
    z.close()
    stamp("np.load %s (n=%d)" % (tid[:26], len(g)), t)

print("\n=== 4. npz 再读（页缓存已热）===", flush=True)
for tid in tids:
    t = time.time()
    z = np.load(os.path.join(NPZ_DIR, tid + ".npz"))
    g = z["token_ids"].tolist()
    z.close()
    stamp("np.load(热) %s" % tid[:26], t)

print("\n=== 5. 整个进程从起跑到读完数据的总账 ===", flush=True)
print("WALL_TOTAL_S=%.2f" % (time.time() - _START), flush=True)
print("TIMING_DONE", flush=True)
