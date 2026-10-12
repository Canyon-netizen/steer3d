#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
r118_doctor_hinge.py —— 修订 118：造一份 doctored 产物，把 `skip()` 那条路径真正跑起来

## 为什么需要它

修订 118 把三处「恒绿跳过分支」改成了 `skip()`（不进红绿分母），
但**那三处今天都触发不了** ⇒ 新加的 `skip()` 与 `[SKIP]` 列表块
⚠ **一次都没被执行过** —— 属未经扰动的新代码。

⚠ 本脚本不碰源码，只**临时**把一份 doctored 产物放到真实路径上，
跑一次判据，然后**按字节还原**。

## 触发哪两条分支

| 分支 | 触发条件 | doctored 做法 |
|---|---|---|
| `verify_hinge_panel.mjs:163` H6 | `art.trajectories.length > 1` 为假 | `trajectories` 只留 1 条 |
| `verify_hinge_panel.mjs:147` H5 | `expIndec > 0` 为假 | 首条轨迹的 hinges 全部 `decidable: true` |

⚠ **只动这两处**，其余字段（`probe` / `caveats` / 标题 / 审计数）一字不改
⇒ H2/H3/H7/H8 这些读它们的判据**应当不受影响**，
⚠ 若它们变红，说明 doctored 动到了别的东西 ⇒ 那正是要抓的。

## 预期结果

```
改动后正常运行   RESULT PASS 28/28   [SKIP] 0 行
doctored 运行   RESULT PASS 26/26   [SKIP] 2 行   ← 两条被跳过的
```

⚠ 分母从 28 降到 26 **是正确的**：跳过的两条**不再计入通过**。
⚠ 若分母仍是 28，说明 `skip()` 仍在往 `results` 里 push ⇒ 记账没改对。

⚠ 若 `[SKIP]` 行数是 0 而分母是 26 ⇒ 记账对了但**没打印** ⇒ 打印块有问题。

## 还原

`--restore` 用**事先存下的备份**还原，并逐字节核对 sha256。
⚠ 不依赖 `git checkout`，因为 git 还要考虑工作区其它状态。
"""
import hashlib
import io
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "frontend/public/latent/data/hinge_hinges.json"
BAK = ROOT / ".cache/mutbak/r118_hinge_real.json"


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def die(m):
    print("[自证失败] " + m)
    sys.exit(2)


if "--restore" in sys.argv:
    if not BAK.exists():
        die("备份不存在：%s ⇒ 拒绝还原（不能凭记忆重写产物）" % BAK)
    before = sha(ART)
    shutil.copyfile(BAK, ART)
    after = sha(ART)
    ok = (after == sha(BAK))
    print("还原：%s" % ART)
    print("  还原前 sha256 = %s" % before)
    print("  还原后 sha256 = %s" % after)
    print("  备份 sha256   = %s" % sha(BAK))
    print("  逐字节一致 = %s%s" % (ok, "" if ok else "  ← ✗ 不一致！"))
    sys.exit(0 if ok else 2)

# ---- 造 doctored ----
if not BAK.exists():
    die("备份不存在：%s ⇒ 先备份再 doctor" % BAK)
real_sha = sha(BAK)
d = json.loads(BAK.read_text(encoding="utf-8"))
if len(d["trajectories"]) < 2:
    die("产物只有 %d 条轨迹 ⇒ doctored 无法触发 H6 跳过" % len(d["trajectories"]))

n_before = len(d["trajectories"])
indec_before = sum(1 for h in d["trajectories"][0]["hinges"] if not h.get("decidable"))
d["trajectories"] = [d["trajectories"][0]]
flipped = 0
for h in d["trajectories"][0]["hinges"]:
    if not h.get("decidable"):
        h["decidable"] = True
        flipped += 1

# ⚠ 自证：doctored 之后两条分支的前提必须都不成立
assert len(d["trajectories"]) == 1, "H6 分支没被触发"
assert sum(1 for h in d["trajectories"][0]["hinges"] if not h.get("decidable")) == 0, \
    "H5 分支没被触发"

ART.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("doctored 已写入：%s" % ART)
print("  真产物 sha256 = %s（备份在 %s）" % (real_sha, BAK.name))
print("  trajectories  %d → 1        ⇒ 触发 H6 跳过" % n_before)
print("  首条不可判定   %d → 0（翻了 %d 个） ⇒ 触发 H5 跳过" % (indec_before, flipped))
print()
print("⚠ 现在跑：BV_URL=http://127.0.0.1:9006/ node .cache/browser_verify/verify_hinge_panel.mjs run")
print("⚠ 跑完**必须**执行：python3 .cache/mutbak/r118_doctor_hinge.py --restore")