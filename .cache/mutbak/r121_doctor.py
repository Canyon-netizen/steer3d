#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 121 —— doctored 产物扰动台（K1 类）。

⚠⚠⚠ **先说清 K1 能测什么、不能测什么**（这一条比工具本身重要）：

  页面上的字/属性是由产物渲染出来的，判据脚本也从**同一个文件**读期望值。
  ⇒ **改产物 ⇒ 页面与判据一起变 ⇒ 恒绿**。
  ⇒ 所以 **K1 扰动测不了「页面 vs 产物」那一类判据**（PAGE_TEXT / PAGE_ATTR），
     那一类必须用 **K2 页面实例扰动**（r116 的 `selfTest()` 模式：
     改已渲染 DOM 的 innerText，不重建、不碰源码、不碰产物）。

  K1 真正能测的是：
   ① **判据内部一致性**（ARTIFACT 桶）—— 页面上根本没有对应渲染，
      例如 `verify_axis_readout` 的 E1/E2/E3/E4/E5/E8/A10。
   ② **判据侧写死的字面量**—— 它的 needle 不来自产物，
      于是产物一变、页面跟着变、needle 不变 ⇒ 转红。
      ⚠ 这正是 `probe_dedup_rendered.mjs:186` 把 `0.7087` 写死的那条。

⚠ 还原纪律（沿用修订 118，不打折）：
   · 动之前先备份 + 记 sha256
   · `--restore` 在**备份缺失时拒绝还原并 exit 2**（不允许凭记忆重写）
   · 还原后**逐字节**核对 sha256，并要求 `git status --porcelain -- <path>` 为空
   · **不用 `git checkout` 当还原手段**（git 还要考虑工作区其它状态）

用法：
  python3 r121_doctor.py set   <相对路径> <点分键> <新值JSON>
  python3 r121_doctor.py show  <相对路径>
  python3 r121_doctor.py restore
"""
import copy
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys

ROOT = '/Users/zhourui/code/steer3d'
BAK = '/Users/zhourui/code/steer3d/.cache/mutbak/r121_backup.json'


def sha256(p):
    return hashlib.sha256(io.open(p, 'rb').read()).hexdigest()


def git_clean(path):
    r = subprocess.run(['git', 'status', '--porcelain', '--', path],
                       cwd=ROOT, capture_output=True, text=True)
    return r.stdout.strip() == ''


def _step(cur, k):
    """⚠ 键名长得像数字（'100'）时不能当下标用 —— `delta` 是 dict 而不是 list。
    判据是**容器类型**，不是键的形状。"""
    if isinstance(cur, list):
        return cur[int(k)]
    return cur[k]


def dig(obj, dotted):
    cur = obj
    for k in dotted.split('.'):
        cur = _step(cur, k)
    return cur


def put(obj, dotted, val):
    keys = dotted.split('.')
    cur = obj
    for k in keys[:-1]:
        cur = cur[int(k)] if k.lstrip('-').isdigit() else cur[k]
    last = keys[-1]
    if isinstance(cur, list):
        cur[int(last)] = val
    else:
        cur[last] = val


def main():
    # ⚠⚠ restore / show 不需要 rel。原先无差别地要求 3 个参数，
    #   结果在最需要还原的时候打印用法并 exit 2 —— **工具在最关键的时刻拒绝干活**。
    #   这不是数据的问题，是工具的易用性问题；但后果是真实产物留在扰动态。
    cmd = sys.argv[1] if len(sys.argv) > 1 else None
    if cmd == 'restore' or cmd == 'help' or cmd is None:
        rel = None
    elif len(sys.argv) < 3:
        print(__doc__)
        return 2
    else:
        rel = sys.argv[2]
    abspath = os.path.join(ROOT, rel) if rel else None

    if cmd == 'set':
        if len(sys.argv) < 5:
            print('用法: set <相对路径> <点分键> <新值JSON>')
            return 2
        dotted, newv = sys.argv[3], json.loads(sys.argv[4])
        meta = None
        if os.path.exists(BAK):
            meta = json.load(io.open(BAK, encoding='utf-8'))
        if not (meta and meta.get('path') == rel):
            if not git_clean(rel):
                print('❌ %s 在工作区已有未提交改动，**拒绝在别人的改动上叠加扰动**' % rel)
                return 2
            meta = {'path': rel, 'abs': abspath,
                    'sha_before': sha256(abspath),
                    'backup': '/Users/zhourui/code/steer3d/.cache/mutbak/r121_backup_file.json'}
            shutil.copyfile(abspath, meta['backup'])
            json.dump(meta, io.open(BAK, 'w', encoding='utf-8'),
                      ensure_ascii=False, indent=2)
            print('已备份 %s' % rel)
            print('  sha256(前) = %s' % meta['sha_before'])
        else:
            print('复用既有备份 %s' % meta['path'])

        d = json.load(io.open(abspath, encoding='utf-8'))
        old = copy.deepcopy(dig(d, dotted))
        print('  改前 %s = %r' % (dotted, old))
        put(d, dotted, newv)
        with io.open(abspath, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
            f.write('\n')
        print('  改后 %s = %r' % (dotted, newv))
        print('  sha256(后) = %s' % sha256(abspath))
        return 0

    if cmd == 'show':
        if len(sys.argv) < 4:
            print('用法: show <相对路径> <点分键>')
            return 2
        d = json.load(io.open(abspath, encoding='utf-8'))
        print('%s 当前 %s = %r' % (rel, sys.argv[3], dig(d, sys.argv[3])))
        return 0

    if cmd == 'restore':
        if not os.path.exists(BAK):
            print('❌ 没有备份元数据 %s' % BAK)
            print('❌ **拒绝还原**（不允许凭记忆重写产物）；请人工核对 git 状态')
            return 2
        meta = json.load(io.open(BAK, encoding='utf-8'))
        if not os.path.exists(meta['backup']):
            print('❌ 备份文件缺失 %s' % meta['backup'])
            print('❌ **拒绝还原**')
            return 2
        shutil.copyfile(meta['backup'], meta['abs'])
        now = sha256(meta['abs'])
        ok = now == meta['sha_before']
        clean = git_clean(meta['path'])
        print('还原 %s' % meta['path'])
        print('  备份 sha256 = %s' % meta['sha_before'])
        print('  还原后 sha256 = %s' % now)
        print('  逐字节一致 = %s' % ok)
        print('  git status 对该路径为空 = %s' % clean)
        os.remove(BAK)
        print('  已删除备份元数据 %s' % BAK)
        return 0 if (ok and clean) else 1

    if cmd == 'help' or cmd is None:
        print(__doc__)
        return 0
    print('未知子命令 %s' % cmd)
    return 2


if __name__ == '__main__':
    sys.exit(main())