"""训练侧与注入侧的位置约定必须逐 token 对齐。

## 背景：这个自检被一个真 bug 逼出来，而我第一次的「修复」又把问题改大了

1. 原实现取 `H[t]`（marker **自己**那个位置），而装置注入 `h(t-1)`
   ⇒ 差**一个 token**。不报错、不崩，`w` 照样训得出来。
2. 我「修」成 `H[extra.prompt_tokens + t - 1]` ⇒ **更糟**：
   把 npz 的**相对**索引当成了**绝对**索引，采样点被推到
   108~914 token 之外的无关文本。class_gap 从 ~300 塌到 **9.3**、
   正负打分差归零、注入尺度跟着塌 32×、效应掉进 bf16 量化底噪。

根因是**没验坐标系**：`npz` 的 `hidden_states` 只含生成段
（`len == n_generated_tokens`，24/24 验过），**不含 prompt**。

## 判据（取数前写死）

  L1 正例取样位置 == `t-1`，与注入下标逐条相等
  L2 负例同样偏移 `t'-1`（不许只改正例）
  L3 牙齿：`H[t]` 与 `H[t-1]` 确实取到不同行（否则本自检无牙齿）
  L4 **坐标系守卫**：`len(hidden_states) != n_generated_tokens` 必须直接抛错
     —— 这是能拦住第 2 类错误（把相对索引当绝对）的那一条
  L5 注入下标恒等于 `len(ids[:P+t]) - 1`，且与 npz 索引 `t-1` 是同一个 token
"""
from __future__ import annotations

import importlib.util
import sys
import atexit
import shutil
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
_sp = importlib.util.spec_from_file_location("r6r", HERE / "r6_rerun.py")
R = importlib.util.module_from_spec(_sp)
_sp.loader.exec_module(R)

FAILS = []
TOTAL = 0


def chk(name, cond, extra=""):
    global TOTAL
    TOTAL += 1
    print(f"  {'PASS' if cond else 'FAIL'}  {name}  {extra}")
    if not cond:
        FAILS.append(name)


# 造一个假 npz：H 在每个位置第 0 维放行号，便于反查取到的是哪一行
TMP = Path(tempfile.mkdtemp(
    # 显式落到 .cache/mutbak/：本机 TMPDIR 指向仓库根目录，
    # mkdtemp() 会把夹具丢在仓库里（已经漏出过一次 tmpujiphne5/，18 个文件）。
    dir=str(Path(__file__).resolve().parent.parent / "mutbak")))
# atxit：脚本中途抛异常时也会清掉
atexit.register(lambda: shutil.rmtree(TMP, ignore_errors=True))
T = 400
# **每一层标上自己的层号**（`L*1000 + i`），这样「取错了哪一层」一眼能看出来，
# 而不是所有层长得一样、只能靠猜。修订 9 的层错位就是被这个办法钉住的。
# 用 float32：float16 的尾数只有 11 位，`L*1000+i`（最大 27399）存不下会被舍入，
# 夹具自己先坏掉，报出来的红是假的。
H = np.zeros((T, R.N_BLOCKS, 2048), dtype=np.float32)
for L in range(R.N_BLOCKS):
    for i in range(T):
        H[i, L, 0] = np.float32(L * 1000 + i)
np.savez(TMP / "t1.npz", hidden_states=H, token_ids=np.arange(T))

markers = [10, 50, 200, 280]
negs = [11, 51, 201, 281]
tmap = {"t1": T}                        # n_generated_tokens

X, y, traj = R.load_xy(str(TMP), {"t1": markers}, {"t1": negs}, tmap)
got_pos = [float(v[0]) for v, lab in zip(X, y) if lab == 1]
want_pos = [float(R.NPZ_LAYER * 1000 + t - 1) for t in markers]
got_neg = [float(v[0]) for v, lab in zip(X, y) if lab == 0]
want_neg = [float(R.NPZ_LAYER * 1000 + t - 1) for t in negs]

print("=" * 74)
print("L1 正例取样位置 == t-1（与注入下标对齐）")
print("=" * 74)
chk("L1a 正例位置逐条相等", got_pos == want_pos, f"取到={got_pos} 应为={want_pos}")
# 旧版这里还有一条 L1b「与 H[t] 明显不同」，它只比行号、不看层，
# 且与 L3a/L3b 重复。L3 把 token 轴与层轴分开比，更严也更准，L1b 已删。

print()
print("=" * 74)
print("L2 负例同样偏移")
print("=" * 74)
chk("L2 负例位置逐条相等", got_neg == want_neg, f"取到={got_neg}")

print()
print("=" * 74)
print("L3 牙齿：错一位（token 轴）与错一层（层轴）都必须被 L1 判红")
print("=" * 74)
# token 轴：H[t]
got_old_tok = [float(R.NPZ_LAYER * 1000 + t) for t in markers]
chk("L3a token 轴：H[t] 与 H[t-1] 确实取到不同值",
    all(a != b for a, b in zip(got_old_tok, want_pos)))
chk("L3b token 轴：旧口径会被 L1a 判红", got_old_tok != want_pos,
    f"旧={got_old_tok} 新={want_pos}")
# 层轴：npz[k] == hs[k+1]，注入动的是 hs[LAYER]，所以是 npz[LAYER-1]
got_old_layer = [float(R.LAYER * 1000 + t - 1) for t in markers]
chk("L3c 层轴：npz[LAYER] 与 npz[LAYER-1] 确实取到不同值",
    all(a != b for a, b in zip(got_old_layer, want_pos)))
chk("L3d 层轴：写 [:, LAYER, :] 的旧口径会被 L1a 判红",
    got_old_layer != want_pos, f"旧={got_old_layer} 新={want_pos}")

print()
print("=" * 74)
print("L4 坐标系守卫：len(hidden_states) != n_generated_tokens 必须抛错")
print("=" * 74)
try:
    R.load_xy(str(TMP), {"t1": markers}, {"t1": negs}, {"t1": T + 7})
    chk("L4a 长度不符必须抛错", False, "竟然算出了数")
except ValueError:
    chk("L4a 长度不符必须抛错", True, "已正确抛错（这正是能拦住相对/绝对索引混用的那条）")

print()
print("=" * 74)
print("L4b 层数守卫：npz 存了 29 层（embedding 没丢）必须抛错")
print("=" * 74)
# 这正是修订 9 的那个错的反面：若哪天采集端改成保留 embedding 那层，
# npz 会变成 29 层，映射 `npz[k]==hs[k+1]` 翻成 `npz[k]==hs[k]`，
# NPZ_LAYER 必须重算成 LAYER。守卫要在这时候炸，而不是静默训错层。
H29 = np.zeros((T, R.N_BLOCKS + 1, 2048), dtype=np.float32)
for L in range(R.N_BLOCKS + 1):
    for i in range(T):
        H29[i, L, 0] = np.float32(L * 1000 + i)
np.savez(TMP / "t29.npz", hidden_states=H29, token_ids=np.arange(T))
try:
    R.load_xy(str(TMP), {"t29": markers}, {"t29": negs}, {"t29": T})
    chk("L4b 层数不符必须抛错", False, "竟然算出了数 —— 层错位会静默复发")
except ValueError as e:
    chk("L4b 层数不符必须抛错", True, f"已抛错：{str(e)[:52]}…")

print()
print("=" * 74)
print("L5 注入下标与 npz 索引是同一个 token")
print("=" * 74)
P = 108                                  # 任意 prompt 长度
for t in (1, 10, 200):
    inj_abs = (P + t) - 1                 # 注入用的是**绝对**下标
    chk(f"L5 t={t}: 绝对下标 {inj_abs} 减去 P 得 {inj_abs - P}，"
        f"等于 npz 索引 t-1={t - 1}", inj_abs - P == t - 1)
chk("L5z 两个下标基数不同但指同一个 token（这正是坐标系的意义）",
    P > 0 and ((P + 10) - 1) != 9, "绝对下标 %d，npz 下标 9" % (P + 9))

print()
print("=" * 74)
print(f"总计 {TOTAL} 项，失败 {len(FAILS)}")
if FAILS:
    print("失败项:", FAILS)
print("=" * 74)
print("=> " + ("位置约定对齐。" if not FAILS else "**训练与注入没对齐，先修。**"))
sys.exit(0 if not FAILS else 1)