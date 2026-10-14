"""执行 scan_panel_coverage.py:1110-1135 的**源码原文**（不是手抄副本）。

⚠⚠ 为什么要造样本：这两条 print 分支**本轮从未被执行过**（存档输出里没有它们），
⚗⚠ 而「从未执行过的 print」里可以有拼写错、格式错、NameError —— r168_teeth 的
⚗⚠ 判决中性 7/7 只证明了「改动没改判据」，**没证明「这条分支还能跑」**。

⚠⚠ 方法纪律：直接 exec 从文件里读出来的行，dedent 4 空格。
⚗⚠⚠ 手抄一遍等于验了副本，不是验了源码 —— 那是本会话已踩过三次的同族坑。
"""
import io
import pathlib
import contextlib

SRC = pathlib.Path('.cache/xcheck/scan_panel_coverage.py')
lines = SRC.read_text().split('\n')
lo, hi = 1110, 1135          # 1-indexed, 含两端；1136 引用 unread，故不可越界

block = '\n'.join(lines[lo - 1:hi])
code = '\n'.join(l[4:] if l.startswith('    ') else l for l in block.split('\n'))
print('=== 待执行源码（前 3 行 / 后 2 行，确认抽对了区间）===')
for l in block.split('\n')[:3]:
    print('   |', l)
print('   | …')
for l in block.split('\n')[-2:]:
    print('   |', l)

# 造样本：三个已知欠账条目，模拟「不在 dom 也不在 read」
_stale_k = ['data-replay-note', 'data-term', 'data-vec-scale']
_stale_x = ['data-bpath']

buf = io.StringIO()
print('\n=== 造样本执行结果 ===')
with contextlib.redirect_stdout(buf):
    exec(compile(code, '<src:1110-1135>', 'exec'), {'_stale_k': _stale_k, '_stale_x': _stale_x})
out = buf.getvalue()
print(out, end='')

print('=== 断言（对着修订 168 想要的措辞）===')
must = [
    '在本次捕获的 DOM 上没出现',
    '这不等于「它们不存在」',
    '条件渲染',
    '不许删',
    '得回【源码】核',
    '在两页 DOM 上都不存在',
]
for m in must:
    print(f'  [{"✅" if m in out else "❌"}] 含「{m}」')
# ⚠ 反向：修订 168 要删掉的旧措辞不得复活
forbidden = ['既不在页面上', '已不在页面上', '在页面上不存在']
for f in forbidden:
    hit = f in out
    print(f'  [{"❌ 旧措辞复活" if hit else "✅"}] 不含旧措辞「{f}」')
print(f'\n坏字: {out.count(chr(0xFFFD))}')
