"""M2: 后端 /ws 路由改名 —— 客户端握手应当全部失败。"""
import io

p = "backend/server.py"
s = io.open(p, encoding="utf-8").read()
old = '@app.websocket("/ws")'
assert old in s, "M2 anchor not found in server.py"
io.open(p, "w", encoding="utf-8").write(s.replace(old, '@app.websocket("/ws-gone")', 1))
print("  M2 applied: /ws -> /ws-gone")
