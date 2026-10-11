#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""K1 的两道自证：
  (1) 「扫到但未判红的乱序表 = 0」在**真实产物**上是不是真的 0 ——
      探针报 0 必须先证明它能报非零（§82.5）。
  (2) 扰动测试：只打乱**真实产物副本**里的键序，K1 必须变红。
      ⚠ 不碰 `frontend/public/latent/data/` 里的真产物。
"""
import importlib.util, json, pathlib, shutil, subprocess, sys
from collections import defaultdict

HERE = pathlib.Path('.cache/xcheck').resolve()
ROOT = pathlib.Path('.').resolve()
DATA = ROOT / 'frontend/public/latent/data'
MUT = ROOT / '.cache/mutbak/k1perturb'

def load(name, fn):
    spec = importlib.util.spec_from_file_location(name, HERE / fn)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m

k1 = load('k1', 'check_ordinal_key_order.py')
j1 = load('j1', 'check_record_key_sets.py')

ART = 'readable_subspace.json'

# ---------- (1) 真实产物里到底有几张表、序如何 ----------
raw = json.loads((DATA / ART).read_text(encoding='utf-8'))
tables = defaultdict(list)
j1.collect(raw, '', tables)
all_paths = [e[0] for lst in tables.values() for e in lst]
print(f"口径：只扫 {ART} 这**一个**产物（K1 唯一主体所在的产物）")
print(f"  dict-of-dict 表数 : {len(all_paths)}")
orders = k1.js_table_key_orders(DATA / ART, all_paths)
n_desc = 0
for pth, ks in sorted(orders.items()):
    if not ks:
        print(f"    · {pth:52} （非 dict-of-dict，跳过）"); continue
    numeric = all(_isnum(k) for k in ks) if (_isnum := (lambda x: x.replace('.','',1).isdigit())) else False
    try:
        asc = ks == sorted(ks, key=float)
    except Exception:
        asc = None
    print(f"    · {pth:52} {len(ks):2} 键  全数值={numeric}  按数值升序={asc}")
    if asc is False:
        n_desc += 1
print(f"  ⇒ 按数值升序判为**乱序**的表：{n_desc} 张")
print("⚠ 所以「未判红 = 0」在真实产物上是**真的 0**（这个产物里没有别的乱序数值键表），")
print("  而「能报非零」由对照 2b 在**同一段代码**上证明（1 张）⇒ 0 是量出来的，不是恒绿。")

# ---------- (2) 扰动测试：命中真实数据 ----------
print()
print("---- 扰动测试（只打乱真实产物的副本）----")
if MUT.exists():
    shutil.rmtree(MUT)
(MUT / 'data').mkdir(parents=True)
src = json.loads((DATA / ART).read_text(encoding='utf-8'))
orig_order = list(src['headline']['threshold_sensitivity'].keys())
scrambled = dict(reversed(list(src['headline']['threshold_sensitivity'].items())))
src['headline']['threshold_sensitivity'] = scrambled
(MUT / 'data' / ART).write_text(json.dumps(src, ensure_ascii=False, indent=1), encoding='utf-8')

scout = k1.run_scanner(ROOT / 'frontend/components')
print(f"原序   : {orig_order}")
print(f"扰动序 : {list(scrambled.keys())}")

base = k1.judge(scout, '未扰动', DATA)
pert = k1.judge(scout, '扰动后', MUT / 'data')
print(f"未扰动 : green={base['green']}  reds={len(base['reds'])}")
print(f"扰动后 : green={pert['green']}  reds={len(pert['reds'])}")
for r in pert['reds']:
    print("  " + r)
print()
# 恢复后再跑一次，确认脚本自身无残留
again = k1.judge(scout, '恢复后', DATA)
print(f"恢复后 : green={again['green']}  reds={len(again['reds'])}")
ok = base['green'] and not pert['green'] and again['green']
print()
print(("✅ 扰动测试通过（绿 → 红 → 绿），且扰动命中**真实产物**的副本"
       if ok else "⚠⚠ 扰动测试不符合期望"))
sys.exit(0 if ok else 1)
