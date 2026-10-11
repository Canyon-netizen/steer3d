#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""K3 的扰动测试：**用真实扫描出来的 29 个路径**跑判据，不碰作者的文件、不动 git index。

⚠⚠ 为什么必须在**真实路径集**上扰动，而不能只靠 6 条合成对照：
   合成对照只证明「判据会对一个我造的文件红」；
   ⚠ 这条要证明「判据对**真实的那 1 条**红，且只红那 1 条」——
   ⚠ 承记忆条目「扰动命中真实数据 ⇒ 它不是恒绿摆设」。
"""
import importlib.util, json, pathlib, shutil, subprocess, sys

ROOT = pathlib.Path('.').resolve()
spec = importlib.util.spec_from_file_location('k3', ROOT / '.cache/xcheck/check_fetch_tracked.py')
k3 = importlib.util.module_from_spec(spec); spec.loader.exec_module(k3)

scan = k3.run_scanner(ROOT / 'frontend')
urls = [p['url'] for p in scan['paths']]
print(f"真实路径集：{len(urls)} 个")

# ---- A. 全部入库 ⇒ 期望判绿 ----
def build(name, tracked: set[str]):
    d = ROOT / '.cache/mutbak/k3perturb' / name
    if d.exists():
        shutil.rmtree(d)
    for u in urls:
        f = d / 'frontend/public' / u.lstrip('/')
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text('{"placeholder":true}', encoding='utf-8')
    subprocess.run(['git', '-C', str(d), 'init', '-q'], check=True)
    subprocess.run(['git', '-C', str(d), 'config', 'user.email', 'p@example.invalid'], check=True)
    subprocess.run(['git', '-C', str(d), 'config', 'user.name', 'perturb'], check=True)
    for u in tracked:
        subprocess.run(['git', '-C', str(d), 'add', '-f', '--',
                        'frontend/public' + u], check=True)
    subprocess.run(['git', '-C', str(d), 'commit', '-q', '-m', 'real paths'], check=True)
    return d

ALL = set(urls)
dA = build('all_tracked', ALL)
rA = k3.judge(scan, dA, {}, '扰动A 全部入库')
print(f"A 全部 {len(ALL)} 个都入库 : green={rA['green']} reds={len(rA['reds'])} n_tracked={rA['n_tracked']}")

# ---- B. 抽掉真实的那 1 个 ⇒ 期望恰好红它 ----
target = '/layer_profiles.json'
B = ALL - {target}
dB = build('one_missing', B)
rB = k3.judge(scan, dB, {}, '扰动B 抽掉 1 个')
print(f"B 抽掉 {target} : green={rB['green']} reds={len(rB['reds'])} n_tracked={rB['n_tracked']}")
for r in rB['reds']:
    print('   ' + r.replace('\n', '\n   '))

# ---- C. 同一份数据 + 豁免登记 ⇒ 期望绿，且豁免计数 = 1 ----
rC = k3.judge(scan, dB, {target: 'HF 数据集 steer3d/latent'}, '扰动C 登记豁免')
print(f"C 同一份 + 豁免登记      : green={rC['green']} 豁免计数={rC['n_exempt_used']}")

ok = rA['green'] and (not rB['green']) and len(rB['reds']) == 1 and target in rB['reds'][0] \
     and rC['green'] and rC['n_exempt_used'] == 1
print()
print('✅ 扰动通过：全入库→绿 / 抽掉真实那 1 个→恰好红它 / 登记豁免→绿（且豁免计数=1）'
      if ok else '⚠⚠ 扰动不符合期望')
sys.exit(0 if ok else 1)
