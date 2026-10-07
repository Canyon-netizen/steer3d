#!/usr/bin/env python3
"""死 URL 扫描：把每个判据脚本指向一个**无人监听**的端口，看有没有谁会报**绿**。

为什么它必须存在（§8.9 第十笔）：
  `verify_scene_link` 曾在 `chrome-error://chromewebdata/` 页上报
  `[PASS] E4 页面确实走了 2D fallback` + `RESULT SKIP 4/5`，
  因为它的分支判据是「两个 testid 都不存在 ⇒ fallback」——
  **默认分支在错误页上正好给出 PASS**，而死 URL 与活页面在自报里长得一样。
  修法是给每个脚本加存活前置（E0）。但「加过了」必须**持续**成立：
  以后任何人重构掉那条前置、或新增脚本却忘了加，本扫描立刻变红。

零成本：不需要 rebuild，不碰产品，不改任何数据。
用法：python3 .cache/xcheck/dead_url_sweep.py      （约 7 分钟，九个脚本各起一次浏览器）

⚠ 第一版是 bash 写的，坏在两处：
  ① 双引号里的全角括号让 bash 把 `$DEAD` 连着 `）` 一起当变量名 ⇒ unbound variable
  ② 一串 `command not found` 连锁
  ⇒ 扫描器自己也必须先被审：**它的失败方向同样是「让我以为没问题」**。
    所以配了一个判据器（`check_dead_url.py`）读它的落盘文件，
    缺 `SWEEP DONE` 标记就直接判红 —— 崩溃的扫描不许被当成通过。
"""
import io, os, re, subprocess, sys, time

REPO = '/Users/zhourui/code/steer3d'
HERE = os.path.dirname(os.path.abspath(__file__))
LAST = os.path.join(HERE, 'dead_url_last.txt')
DEAD = os.environ.get('DEAD_URL', 'http://127.0.0.1:10999/')
SCRIPTS = ['verify_outcome', 'verify_law', 'verify_ladder', 'verify_subspace',
           'verify_axis_readout', 'verify_heldout', 'verify_structure',
           'verify_derivation', 'verify_scene_link']

SUM_PAT = re.compile(r'^(RESULT .*|=== \d+/\d+ passed ===)$', re.M)
FAIL_PAT = re.compile(r'^\[FAIL\]', re.M)
CRASH_PAT = re.compile(r'^\[FAIL\] (X 脚本崩了|装置)', re.M)


def main():
    lines = []
    t0 = time.time()
    for f in SCRIPTS:
        env = dict(os.environ, T3D_URL=DEAD, BV_URL=DEAD)
        try:
            p = subprocess.run(['node', '.cache/browser_verify/%s.mjs' % f],
                               cwd=REPO, env=env, capture_output=True,
                               text=True, timeout=300)
            out, rc = (p.stdout or '') + (p.stderr or ''), p.returncode
        except subprocess.TimeoutExpired:
            out, rc = '', 'TIMEOUT'
        sums = SUM_PAT.findall(out)
        summary = sums[-1].strip() if sums else ''
        # ⚠⚠ 分类必须按**通过数**，不能按「有没有 FAIL 这个词」。
        #   我第一版写的是 re.search(r'\bFAIL\b', summary)，于是
        #     === 0/4 passed ===   ← 4 条全灭、0 条通过
        #   因为句子里没有 FAIL 这个词而落进 GREEN 分支。
        #   ⇒ 这就是第十笔那个洞（输入不落到默认分支）**在我自己的判据里复现**：
        #     「找不到 FAIL 就当没事」正是 E4 那句 `|| fallback` 的形状。
        # ⇒ 判据的默认分支也会出现在判据作者自己身上，所以分类器也要被审。
        m = re.search(r'(?:RESULT (?:PASS|FAIL)|=== )\s*(\d+)/(\d+)', summary)
        if not summary:
            verdict = 'NO-SUMMARY'
        elif not m:
            verdict = 'NO-SUMMARY'
        else:
            passed, total = int(m.group(1)), int(m.group(2))
            # 0 条通过 = 全灭；0 条总数 = 一条都没跑（第三种状态，不能算红也不能算绿）
            verdict = 'RED' if (total > 0 and passed < total) else (
                     'NOTHING-RAN' if total == 0 else 'GREEN')
        nred = len(FAIL_PAT.findall(out))
        ncrash = len(CRASH_PAT.findall(out))
        row = '%-22s %-11s 判红=%-3s 其中装置崩=%-3s %s' % (
            f, verdict, nred, ncrash, summary)
        lines.append(row)
        print(row, flush=True)

    lines.append('SWEEP DONE (DEAD=%s, %.0fs)' % (DEAD, time.time() - t0))
    io.open(LAST, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print('\n已写出 %s' % LAST)
    greens = [l.split()[0] for l in lines if ' GREEN ' in l]
    print('报绿的：%s' % ('、'.join(greens) if greens else '无'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
