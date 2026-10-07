#!/usr/bin/env python3
"""死 URL 扫描的判据：**没有任何一个判据脚本能在「页面压根没加载」时报绿。**

为什么它必须存在（第十笔）：verify_scene_link 曾在 chrome-error 页上报
PASS + SKIP，因为分支判据是「两个 testid 都不存在 ⇒ fallback」——
默认分支在错误页上正好给出 PASS。修法是加存活前置（E0）。
但「加过了」必须**持续**成立，所以把它变成会变红的检查：
  · 有人重构掉某条脚本的存活前置 ⇒ 该脚本变 GREEN ⇒ 本条立刻红
  · 有人新增一个判据脚本却没加前置 ⇒ 同上

读 .cache/xcheck/dead_url_last.txt（由 dead_url_sweep.sh 写）。
"""
import io, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
LAST = os.path.join(HERE, 'dead_url_last.txt')
EXPECTED = ['verify_outcome', 'verify_law', 'verify_ladder', 'verify_subspace',
            'verify_axis_readout', 'verify_heldout', 'verify_structure',
            'verify_derivation', 'verify_scene_link']


def check(name, ok, detail):
    print(('[PASS] ' if ok else '[FAIL] ') + name)
    print('       ' + detail)
    return ok


def main():
    if not os.path.exists(LAST):
        print('❌ 没有 %s —— 先跑 bash .cache/xcheck/dead_url_sweep.sh' % LAST)
        return 1
    raw = io.open(LAST, encoding='utf-8').read()
    if 'SWEEP DONE' not in raw:
        print('❌ 扫描没跑完（没有 SWEEP DONE 标记）—— 中途崩了，不能算数')
        return 1
    rows = {}
    for ln in raw.splitlines():
        m = re.match(r'^(verify_\w+)\s+(\S+)\s+判红=(\d+)\s+其中装置崩=(\d+)\s*(.*)$', ln)
        if m:
            # ⚠ 不信扫描器写的 verdict —— 从汇总列**独立重算**。
            #   理由同上：扫描器自己的分类逻辑也犯过「0/4 passed 当成绿」。
            #   两处独立算，才有一个能发现另一个错了。
            c = re.search(r'(?:RESULT (?:PASS|FAIL)|=== )\s*(\d+)/(\d+)', m.group(5))
            if not c:
                v = 'NO-SUMMARY'
            else:
                passed, total = int(c.group(1)), int(c.group(2))
                v = ('NOTHING-RAN' if total == 0
                     else ('RED' if passed < total else 'GREEN'))
            rows[m.group(1)] = {'v': v, 'scan_v': m.group(2),
                                'red': int(m.group(3)),
                                'crash': int(m.group(4)), 'sum': m.group(5).strip()}
    ok = True
    ok &= check('扫描覆盖全部 %d 个判据脚本' % len(EXPECTED),
                all(s in rows for s in EXPECTED),
                '读到 %d 个：%s' % (len(rows), '、'.join(sorted(rows))))
    green = [s for s in EXPECTED if rows.get(s, {}).get('v') == 'GREEN']
    ok &= check('没有任何脚本在死 URL 上报绿（输入缺失不得落到看似合理的默认值）',
                not green,
                '报绿的：%s' % ('、'.join(green) if green else '无（9/9 全部判红）'))
    # 扫描器的 verdict 与本判据独立重算的必须一致 —— 不一致本身就是一条判据
    mismatch = [s for s in EXPECTED
                if s in rows and rows[s].get('scan_v') != rows[s].get('v')]
    ok &= check('扫描器写的 verdict 必须与本判据独立重算的一致（两个分类器互为对照）',
                not mismatch,
                '不一致：%s' % ('、'.join(
                    '%s(扫描器=%s/我=%s)' % (s, rows[s]['scan_v'], rows[s]['v'])
                    for s in mismatch) if mismatch else '无'))
    norun = [s for s in EXPECTED if rows.get(s, {}).get('v') == 'NOTHING-RAN']
    ok &= check('不能有脚本「一条都没跑」（那是第三种状态，既不算红也不算绿）',
                not norun, '一条都没跑：%s' % ('、'.join(norun) if norun else '无'))
    nosum = [s for s in EXPECTED if rows.get(s, {}).get('v') == 'NO-SUMMARY']
    ok &= check('每个脚本都必须打出可读的汇总行（否则无法区分「跑红」与「崩了」）',
                not nosum,
                '缺汇总行：%s' % ('、'.join(nosum) if nosum else '无'))
    # 「判红」与「装置崩」必须能分开：崩掉的条数不能掩盖真实判红数
    crashy = [s for s in EXPECTED if rows.get(s, {}).get('crash', 0) > 0]
    print('       注：%d 个脚本在死 URL 上会先崩再判红（%s）——'
          % (len(crashy), '、'.join(crashy) if crashy else '无'))
    print('          它们的「面板已就绪」前置仍然把它们判红了，所以不影响本条结论；')
    print('          但崩溃会污染判红计数，所以死 URL 扫描必须把两列分开报。')
    print('\nRESULT dead_url  %s  %d/5 条通过' % ('GREEN' if ok else 'RED',
          sum([all(s in rows for s in EXPECTED), not green, not nosum,
               not mismatch, not norun])))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
