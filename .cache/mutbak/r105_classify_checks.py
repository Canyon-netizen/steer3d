#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
r105_classify_checks.py —— 把 verify_subspace.mjs 的每一条判据，
按「它读的到底是页面 / 产物 / 源码 / 跨产物」分类。

为什么做这个：修订 103 发现 P1–P8 读的是产物而非页面。那是**单点发现**。
这里把它系统化 —— 出一张覆盖图，才知道「读产物」是个例还是通例，
以及「哪些判据真的在盯页面」。

两条纪律：
  1) **先剥注释**再数/再解析。⚠ 教训：用 text.count("X(") 判断调用数，
     会把注释里那句一起数进去。
  2) **溯源表必须打印出来**。分类结论是人工判读的产物，
     不印出来就等于让人信一个黑箱。
"""
import io
import re
import sys

PATH = ".cache/browser_verify/verify_subspace.mjs"
SRC = io.open(PATH, encoding="utf-8").read()


def strip_js(s):
    """剥 JS 注释，但不动字符串/模板串里的内容。"""
    out, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c == "/" and i + 1 < n and s[i + 1] == "/":
            while i < n and s[i] != "\n":
                i += 1
        elif c == "/" and i + 1 < n and s[i + 1] == "*":
            i += 2
            while i + 1 < n and not (s[i] == "*" and s[i + 1] == "/"):
                i += 1
            i += 2
        elif c in "`\"'":
            q, i = c, i + 1
            out.append(c)
            while i < n and s[i] != q:
                if s[i] == "\\":
                    out.append(s[i]); i += 1
                if i < n:
                    out.append(s[i]); i += 1
            if i < n:
                out.append(s[i]); i += 1
        else:
            out.append(c); i += 1
    return "".join(out)


CODE = strip_js(SRC)

# ---------- 自证：必须真的剥掉了注释，否则后面全是错的 ----------
if CODE.count("check(") != SRC.count("check("):
    die = ("⚠ 注释剥离失败：剥离后 check( 数 %d ≠ 原文 %d" % (CODE.count("check("), SRC.count("check(")))
    print("[自证失败] " + die); sys.exit(2)
print("[自证] check( 出现次数剥离前后一致（%d），说明源里没有藏在注释里的调用"
      % CODE.count("check("))
print("[自证] 注释长度 %d → %d" % (len(SRC), len(CODE)))

# ---------- 变量溯源表 ----------
# 只看顶层/块内的 const|let 声明，按右侧表达式归类。
# ⚠ 这是**人工规则**，所以全部打印出来供审计。
VAR_SRC = []
for m in re.finditer(r"\b(?:const|let)\s+([A-Za-z_$][\w$]*)\s*=\s*", CODE):
    name = m.group(1)
    j = m.end()
    depth = 0
    buf = []
    while j < len(CODE):
        ch = CODE[j]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                break
            depth -= 1
        elif ch in ";" and depth == 0:
            break
        buf.append(ch); j += 1
    rhs = " ".join("".join(buf).split())
    if "page.eval" in rhs or "await page" in rhs:
        k = "PAGE"
    elif re.search(r"readFileSync\([^)]*\.tsx", rhs):
        k = "SOURCE"
    elif "readFileSync" in rhs or "truth" in rhs or re.search(r"\bH\.|\bSUB\.|\bTS\[|\bAX\b", rhs):
        k = "ARTIFACT"
    else:
        k = "?" if rhs else "?"
    VAR_SRC.append((name, k, rhs[:70]))

print()
print("=== 变量溯源表（人工规则，全印供审计）===")

# ⚠⚠ 第一版只按**顶层 RHS 的字面形态**归类，结果把 15 条判据落进 OTHER ——
#   它们的 ok 表达式用的是**局部变量**（gotN / caveat / absorbedNote …），
#   而我没追进去。照那个输出报「只有 2 条只读产物」就是**一台干净的错误仪器**。
# ⇒ 改成**传递闭包**：一个变量的类别 = 它 RHS 里引用的变量类别之并。
IDENT = re.compile(r"\b([A-Za-z_$][\w$]*)\b")
DIRECT = {}   # name -> (kind, rhs)  只记字面可判的
for name, k, rhs in VAR_SRC:
    if k != "?":
        DIRECT[name] = k

PROV = dict(DIRECT)
for _ in range(8):                       # 不动点迭代，传递闭包
    changed = False
    for name, k, rhs in VAR_SRC:
        if k != "?":
            continue
        tags = set()
        for ident in IDENT.findall(rhs):
            if ident in PROV:
                tags.add(PROV[ident])
        if tags:
            new = "+".join(sorted(tags))
            if PROV.get(name) != new:
                PROV[name] = new
                changed = True
    if not changed:
        break

for name, k, rhs in VAR_SRC:
    final = PROV.get(name, "?")
    mark = "" if final == k else "   <- 由引用推出"
    print("  %-12s %-11s <- %s%s" % (name, final, rhs[:62], mark))


def classify(ok_expr):
    """按 ok 表达式里出现的标识符判定它读的是哪一层。"""
    if re.search(r"\b(g|P|notes|grow|got|rows|NC|VD|flatG)\b\.", ok_expr) \
       or "page.eval" in ok_expr:
        return "PAGE"
    return "OTHER"


# ---------- 提取每个 check(name, ok) ----------
checks = []
for m in re.finditer(r"\bcheck\(\s*(['\"])", CODE):
    q = CODE[m.start() + len("check(")]
    j = m.end()
    k = j
    while k < len(CODE) and CODE[k] != q:
        k += 1
    name = CODE[j:k]
    a = CODE.index("(", m.start())
    depth = 0
    parts, cur = [], ""
    for t in range(a, len(CODE)):
        ch = CODE[t]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                parts.append(cur); break
            depth -= 1
        if ch == "," and depth == 1:
            parts.append(cur); cur = ""
        else:
            cur += ch
    ok = parts[1].strip() if len(parts) > 1 else ""
    checks.append((name, ok))

print()
print("=== 判据清单（%d 处调用点；运行期会因循环展开成 %d 条）===" % (len(checks), 51))
print()

bucket = {"PAGE": [], "ARTIFACT": [], "SOURCE": [], "MIXED": [], "UNRESOLVED": []}
for name, ok in checks:
    tags = set()
    for ident in IDENT.findall(ok):
        p = PROV.get(ident)
        if p:
            tags.update(p.split("+"))
    if not tags:
        bucket["UNRESOLVED"].append((name, ["?"]))
        print("  %-52s ⚠ 未解析（引用的标识符都不在溯源表里）" % name[:52])
        continue
    tags = sorted(tags)
    key = "MIXED" if len(tags) > 1 else tags[0]
    bucket[key].append((name, tags))
    print("  %-52s %s" % (name[:52], "+".join(tags)))

print()
print("=== 汇总（34 处调用点；运行期循环展开成 51 条）===")
for k in ["PAGE", "MIXED", "ARTIFACT", "SOURCE", "UNRESOLVED"]:
    print("  %-11s %d 处" % (k, len(bucket[k])))
print()
print("⚠ **不覆盖页面**的判据（纯产物 / 纯源码）：")
for n, t in bucket["ARTIFACT"] + bucket["SOURCE"]:
    print("     -", n)
print("⚠ 跨产物与页面的（这类才是真的在盯页面）：", len(bucket["MIXED"]), "处")