#!/usr/bin/env python3
"""单条变异施加器。用法: python3 apply_mut.py M1

每条变异一个函数，各自 assert 锚点存在。单独成文件而不是塞进 shell
heredoc：上一版把 Python 写在 bash 的多行字符串里，$ 和引号被吃掉，
改写静默失败而脚本继续往下跑并报告"变异已生效"——那正是"变异打在死代码上"
的典型形态。锚点 assert 就是为了不发生这件事。
"""
import io
import sys

P = "frontend/public/latent/index.html"


def read():
    return io.open(P, encoding="utf-8").read()


def write(s):
    io.open(P, "w", encoding="utf-8").write(s)


def m1(s):
    """boot() 不再加载叙述性数据 —— 还原这一轮真实发生的事故。"""
    old = """  try{
    await loadNarrative();
    renderExtras();
    trace("narrative loaded");
  }catch(e){ trace("loadNarrative failed: " + e.message); }"""
    new = "  // MUT_NO_NARRATIVE"
    assert old in s, "M1 anchor not found"
    return s.replace(old, new, 1)


def m2(s):
    """删掉「零空间是空的」这个被推翻的说法。"""
    old = "读出矩阵是满秩的，所以精确零空间是空的："
    new = "读出矩阵的 MUT_ZEROSPACE 情况："
    assert old in s, "M2 anchor not found"
    return s.replace(old, new, 1)


def m3(s):
    """条件数字段名取错 —— 页面会把 33.0 渲染成破折号。"""
    old = "${nfmt(rk.cond, 1)}"
    new = "${nfmt(rk.condition, 1)}"
    assert old in s, "M3 anchor not found"
    return s.replace(old, new, 1)


def m4(s):
    """厚锥/薄锥合并成一行 —— 平均值会把两个数量级的差异抹平。"""
    old = ('    ${coneRow("读出已指向该词", thick, "#7cc0ff")}\n'
           '    ${coneRow("靠微调才指向该词", thin, "#e0a04a")}')
    new = '    ${coneRow("MUT_MERGED", thick, "#7cc0ff")}'
    assert old in s, "M4 anchor not found"
    return s.replace(old, new, 1)


def m5(s):
    """步按钮点击无响应 —— 交互失效但 DOM 判据全绿。"""
    old = "if(Number.isFinite(v)){ S.bmStep = v; renderExtras(); }"
    new = "if(Number.isFinite(v)){ S.bmStep = v; /* MUT_NO_OP */ }"
    assert old in s, "M5 anchor not found"
    return s.replace(old, new, 1)


def m6(s):
    """删掉「是并列而不是翻转」—— 读者会以为那就是翻转点。"""
    old = '${best.margin_is_zero_at_boundary ? "（恰好为 0，是<b>并列</b>而不是翻转）" : ""}'
    new = '${"" /* MUT_TIE_GONE */}'
    assert old in s, "M6 anchor not found"
    return s.replace(old, new, 1)


MUTS = {"M1": m1, "M2": m2, "M3": m3, "M4": m4, "M5": m5, "M6": m6}

if __name__ == "__main__":
    which = sys.argv[1]
    if which not in MUTS:
        print("unknown mutation", which)
        sys.exit(2)
    write(MUTS[which](read()))
    print("  applied", which)
