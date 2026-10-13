"""离线校验 r142 补丁：锚点 + **模板字面量内部不许有反引号**。

⚠⚠⚴⚠⚴ **正确的判据不是「整个新块的反引号数」** —— 新块里本来就有活代码用的
反引号（E1 的 eval 一对、E2 的 eval 一对、三条 detail 的模板串），
⚠⚠⚴ **它们合法**。⚗ 真正致命的是**落在 `page.eval` 的模板字面量内部**的那些
⚠ （尤其**注释行里的**）—— 它们会**提前终止模板**，整条判据崩在语法错误上。

⚠⚠⚴⚠⚴⇒ **判据只能是「E2 那对界定符之间，一个反引号都没有」**，
⚠⚠⚴ 而不是「总数是 2」——⚗ 后者会把这个补丁误判成坏的（我第一版就是这么错的）。

⚠⚠⚴ 本文件**不用 shell 传反引号**：第一版把 `chr(96)` 直接写进 `python3 -c "..."`，
⚠ bash 的命令替换吃掉了它 ⇒ 数出「18」这个**看起来精确、实际无意义**的数字。
⚠⚠⚴ **检查自己被 shell 改写 ⇒ 它的结论一律作废。**
"""

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BT = chr(96)

src = (ROOT / ".cache/mutbak/r142_apply_e2.py").read_text(encoding="utf-8")
old = src.split('OLD = """')[1].split('"""')[0]
new = src.split('NEW = """')[1].split('"""')[0]
target = ROOT / ".cache/browser_verify/verify_path.mjs"
f = target.read_text(encoding="utf-8")
nl = new.split("\n")

ok = True

# ---- ① 锚点 ---------------------------------------------------------
c = f.count(old)
print(f"[锚点] 旧块出现 {c} 次（必须恰好 1）{'✅' if c == 1 else '❌'}")
ok &= (c == 1)

# ---- ② 门①的 sha ----------------------------------------------------
sha = hashlib.sha256(target.read_bytes()).hexdigest()[:16]
want = "272929ca57e19d8a"
print(f"[sha ] 实测 {sha} / 期望 {want} {'✅' if sha == want else '❌'}")
ok &= (sha == want)

# ---- ③ ⚠ 核心：E2 的模板字面量内部不许有反引号 -----------------------
start = None
for i, l in enumerate(nl):
    if l.strip().startswith("const said = JSON.parse(await page.eval(" + BT):
        start = i
        break
end = None
for j in range(start + 1, len(nl)):
    if nl[j].strip().startswith("})()"):
        end = j
        break
if start is None or end is None:
    print("[模板] ❌ 找不出 E2 的 page.eval 界定符 —— 判据脚本本身变了，不测")
    raise SystemExit(2)
inside = [(k, nl[k].strip()[:78]) for k in range(start, end + 1) if BT in nl[k] and k not in (start, end)]
print(f"[模板] E2 的 eval 界定在第 {start+1}…{end+1} 行（1-based）")
print(f"[模板] 内部带反引号的行：{len(inside)}（必须 0）{'✅' if not inside else '❌'}")
for k, l in inside:
    print(f"          ⚠ 行{k+1}: {l}")
ok &= not inside

# ---- ④ 全块反引号账（透明起见，不作为判据）--------------------------
bt_lines = [(i + 1, l.strip()[:64]) for i, l in enumerate(nl) if BT in l]
print(f"[账  ] 新块全文反引号 {new.count(BT)} 个，分布在 {len(bt_lines)} 行：")
for i, l in bt_lines:
    tag = "（模板内 ⚠）" if start < i - 1 < end else "（活代码，合法）"
    print(f"          行{i} {tag} {l}")

print("\n=== 结论：" + ("✅ 补丁可应用" if ok else "❌ 有不过的项，见上") + " ===")
raise SystemExit(0 if ok else 2)