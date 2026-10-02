"""M1: Frame.to_dict() 不再带 kind 标签（还原原始协议不一致）。

单独成文件而不是塞进 shell heredoc：第一版把 Python 写在
mutate() 函数的参数里，heredoc 在函数体内没有按预期展开，
改写静默没执行，脚本却继续往下跑并报告"变异已生效"。
"""
import io

p = "backend/core/protocol.py"
s = io.open(p, encoding="utf-8").read()
old = '        return {"kind": "frame", **asdict(self)}'
assert old in s, "M1 anchor not found in protocol.py"
io.open(p, "w", encoding="utf-8").write(s.replace(old, "        return asdict(self)", 1))
print("  M1 applied: frames no longer carry kind")
