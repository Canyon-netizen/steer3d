"""M3: 后端忽略 start 指令 —— 客户端等不到帧，P7 必须红。

改条件而不是删分支：删掉整段会让 `stream_task` 失去定义点，
后面 `elif` 链的语法虽然仍合法，但 pydoc/flake 层面的可读性变差；
改条件是最小、最可逆、语义最清楚的破坏。
"""
import io

p = "backend/server.py"
s = io.open(p, encoding="utf-8").read()
old = '            if kind == "start":'
assert old in s, "M3 anchor not found in server.py"
io.open(p, "w", encoding="utf-8").write(
    s.replace(old, '            if kind == "start" and False:', 1)
)
print("  M3 applied: start branch is now dead")
