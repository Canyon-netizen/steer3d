#!/usr/bin/env python3
"""X0 存活前置的**九份副本必须等价**——因为它们没法不重复。

背景（§8.9 第十一笔）：
  九个判据脚本都是**已跟踪**的，而共享模块放在 `.cache/` 下会被 `.gitignore`
  排除；按规矩不 force-add，所以 X0 只能**就地内联**进九个脚本。
  ⇒ 于是同一判据有九份副本，而副本会漂移。
  ⇒ 这正是第八笔那个形状的翻版：
      表格印 0.35→9、散文印 0.35→7，同屏矛盾却没人管。
  处置同样是**把重复变成可核的**，而不是靠自觉。

本判据查三件事：
  1. 九个脚本**都在**导航后带着 X0（少一个就有一个脚本能在死页面上报绿）
  2. 九份副本**除两处允许的差异外逐字相同**（记录函数名、结果数组名）
  3. 阈值是文档里写的那一个（bodyLen > 0 且 script[src] >= 1）——
     有人悄悄收紧或放宽，这一条会红

⚠ 只查源码，零成本，不起浏览器。
"""
import io, os, re, sys

REPO = '/Users/zhourui/code/steer3d'
DIR = os.path.join(REPO, '.cache/browser_verify')
SCRIPTS = ['verify_outcome', 'verify_law', 'verify_ladder', 'verify_subspace',
           'verify_axis_readout', 'verify_heldout', 'verify_structure',
           'verify_derivation', 'verify_scene_link']
BLOCK_RE = re.compile(r'  // ---- X0 存活前置 \+ 早退出.*?\n  \}\n', re.S)

results = []


def check(name, ok, detail):
    results.append(ok)
    print(('[PASS] ' if ok else '[FAIL] ') + name)
    print('       ' + detail)


def normalise(txt):
    """抹掉两处**允许**的差异：记录函数名与结果数组名。"""
    txt = re.sub(r"\b(rec|check)\('X0 页面必须真的加载出来",
                 "@REC@('X0 页面必须真的加载出来", txt)
    txt = re.sub(r'\$\{(R|results)\.length\}', '${@ARR@.length}', txt)
    return txt


def main():
    blocks = {}      # 归一化后的（用于「必须逐字相同」）
    raw_blocks = {}  # 原始的（用于「引用的符号必须存在」）
    missing = []
    for f in SCRIPTS:
        p = os.path.join(DIR, f + '.mjs')
        if not os.path.exists(p):
            missing.append(f + '（文件不在）')
            continue
        m = BLOCK_RE.search(io.open(p, encoding='utf-8').read())
        if not m:
            missing.append(f)
        else:
            raw_blocks[f] = m.group(0)
            blocks[f] = normalise(m.group(0))

    check('X0 存活前置必须出现在全部 %d 个判据脚本里（少一个就有一个能在死页面上报绿）' % len(SCRIPTS),
          not missing, '缺：%s' % ('、'.join(missing) if missing else '无'))

    if blocks:
        uniq = {}
        for f, b in blocks.items():
            uniq.setdefault(b, []).append(f)
        if len(uniq) == 1:
            detail = '全部一致（各 %d 字符）' % len(next(iter(uniq)))
        else:
            detail = '%d 份互不相同；分组：%s' % (
                len(uniq), ' | '.join('{%s}' % '、'.join(v) for v in uniq.values()))
        check('九份 X0 副本除「记录函数名 / 结果数组名」外必须逐字相同（副本漂移会红）',
              len(uniq) == 1, detail)

    # ⚠ 必须**逐份**查，不能只查第一份：
    #   我第一版写的是 b0 = next(iter(blocks.values()))，
    #   于是「只改一份」的变异若恰好不是第一份，阈值那条会漏 ——
    #   而它正是这条判据声称在防的事。
    #   （漂移那条会抓到，但那时阈值那条在说谎。）
    bad_thr = [f for f, b in blocks.items()
               if not ('L.bodyLen > 0 && L.scripts >= 1' in b
                       and 'L.bodyLen > 2000' not in b
                       and 'outcome.length > 0' not in b)]
    thr_ok = blocks and not bad_thr
    check('九份的阈值都必须等于文档写的那一个：bodyLen>0 且 script[src]>=1（不越权到「数据就绪」）',
          bool(thr_ok),
          '实测外壳 bodyLen≈1190 / script[src]=6 —— 阈值若写成 bodyLen>2000 会在活页面上判红'
          if not thr_ok else
          ('阈值不对的：%s' % '、'.join(bad_thr)) if bad_thr else
          '九份都等于 bodyLen > 0 && script[src] >= 1，且都未出现 data-outcome 门控'
          '（那是各脚本自己的 ready 轮询，不该由 X0 越权代劳）')

    # 早退出必须在：判红就退出，否则判红计数仍被装置崩污染
    exits = 0
    for f in SCRIPTS:
        p = os.path.join(DIR, f + '.mjs')
        if not os.path.exists(p):
            continue
        s = io.open(p, encoding='utf-8').read()
        m = BLOCK_RE.search(s)
        if m and 'process.exit(1)' in m.group(0) and '一条都没跑' in m.group(0):
            exits += 1
    check('X0 判红后必须**早退出**（否则「判红 / 装置崩 / 一条都没跑」三件事又混在一起）',
          exits == len(SCRIPTS),
          '带早退出的：%d/%d' % (exits, len(SCRIPTS)))

    # ⚠ 归一化 `rec|check` 有一个**危险面**：它抹掉的差异里，
    #   正好有「这个脚本到底用哪个记录函数」——那是会**真的跑不起来**的差异。
    #   实测我「逐字复用」时把 rec 带进了用 check 的 verify_scene_link，
    #   判据 4/4 全绿，而脚本直接 `rec is not defined` 崩了。
    # ⇒ 所以补第五条：块里引用的记录函数与结果数组，必须在该脚本里真实存在。
    bad_ref = []
    for f, b in raw_blocks.items():
        src = io.open(os.path.join(DIR, f + '.mjs'), encoding='utf-8').read()
        fn = re.search(r"\b(rec|check)\('X0 页面必须真的加载出来", b)
        arr = re.search(r'\$\{(\w+)\.length\}', b)
        fn_ok = fn and re.search(r'(const|let|var|function)\s+%s\b' % fn.group(1), src)
        arr_ok = arr and re.search(r'\b(let|const|var)\s+%s\b' % arr.group(1), src)
        if not (fn_ok and arr_ok):
            bad_ref.append('%s(函数=%s 数组=%s)' % (f, fn.group(1) if fn else '?',
                                                   arr.group(1) if arr else '?'))
    check('块里引用的「记录函数」与「结果数组」必须在该脚本里真实存在（归一化会抹掉这个差异）',
          not bad_ref,
          '引用不存在：%s' % ('、'.join(bad_ref) if bad_ref else '无（九个都对得上）'))

    n = sum(results)
    print('\nRESULT live_blocks  %s  %d/%d 条通过'
          % ('GREEN' if n == len(results) else 'RED', n, len(results)))
    return 0 if n == len(results) else 1


if __name__ == '__main__':
    sys.exit(main())
