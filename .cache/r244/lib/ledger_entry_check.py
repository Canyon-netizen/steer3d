#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ledger_entry_check.py —— **账本追加段的机械形状检查**（唯一实现）。

⚖⚠⚠⚖⚖ **为什么要有它**：244.64 的追加脚本在**重活跑完之后**炸了两次，
   而那两条断言**都是假红的**：
     ① `ENTRY2.startswith(TITLE)` —— ENTRY 首字符是换行，
        而那个换行**正是账本的分节惯例**（每两个修订段之间是 `\n\n`）
     ② `assert "%" not in ENTRY2` —— 账本里 `%` 共 993 处（`MC95%`）
        ⇒ 「任何 `%` 都不许」**与账本现实矛盾** ⇒ 拦路石

⚖⚠⚠⚖⚖ **判别式（本模块存在的理由）**：
   > **护栏的规则必须与「被它保护的那个对象的现实」一致。**
   > ⚖ **宁可严到全红的护栏不是护栏，是拦路石** ⇒ 一次假红就足以让人把整段判据改松。
   > ⚖ 规则要么**收窄到零假阳性**，要么**改到能对齐现实** —— ⛔ 不能留在中间。

⚖⚠⚠ **「像 %-格式化占位」的判定必须用 printf 的真实文法**：
   - ⛔ **不能用** `%[-+ #0-9.]*[a-zA-Z]` ⇒ 它把散文里的 **`% vs` / `% CI` / `% of`**
     全判成占位（实测账本里 67 处命中，其中绝大多数是假阳性）
   - ✅ 真实文法：`%` + 标志(`-+0 #`) + 宽度 + `.精度` + **转换字符**(`sdifgeExXocr`)
     ⇒ 再加一条：**后面还跟字母 ⇒ 判为散文**（`% of`、`% s` 都是散文，不是占位）

⚖ 本模块是**唯一实现** ⇒ 追加脚本与静态预检都 import 它 ⇒ ⛔ 不写第二份。
"""
import re

# ---- printf 转换规格（真实文法）⇒ ⛔ 不含 `v`（无此转换符）----
_PRINTF = re.compile(r"%(?:\([^)]*\)|[-+0 #]*\d*(?:\.\d+)?)[sdifgeExXocr]")


def printf_specs(text):
    """⛔ 返回 text 里**像 printf 占位**的片段（已剔除散文误判）。

    ⚖ **「后面还跟字母 ⇒ 判为散文」**：这是把规则收窄到零假阳性的关键。
      - `% vs` ⇒ `v` 不是转换符 ⇒ 不命中
      - `% of` ⇒ `o` 是转换符，但后面还跟 `f`（字母）⇒ 判散文 ⇒ 不命中
      - `% CI` ⇒ `C` 不是转换符 ⇒ 不命中
      - `%s` / `%d` / `%.2f` / `%02d` / `%(k)s` ⇒ 命中（这才是要抓的）
    """
    out = []
    for m in _PRINTF.finditer(text):
        nxt = text[m.end():m.end() + 1]
        if nxt.isalpha():
            continue
        out.append(m.group(0))
    return out


def code_fence_mask(text):
    """⚖ 返回「不在代码围栏里」的那些片段（**按对配**）。

    ⚖⚠⚠ **按对配，不许「遇 ``` 就取反」**：账本里围栏标记是**奇数个**
      ⇒ 简单的取反掩码会让后面几千行散文被当成代码（洞全被吞掉）
      ⇒ 末尾没配上的那个围栏，其后的内容**按散文处理**（保守方向：宁可多报）
    """
    lines = text.split("\n")
    fences = [i for i, ln in enumerate(lines) if ln.lstrip().startswith("```")]
    code = set()
    for a, b in zip(fences[0::2], fences[1::2]):
        for i in range(a, b + 1):
            code.add(i)
    return "\n".join(ln for i, ln in enumerate(lines) if i not in code)


def shape_problems(text, title):
    """⛔ 返回**问题清单**（空列表 = 通过）⇒ 同一个函数既验真样也验负控制。

    ⚖⚠⚠ **分节惯例**：账本里每两个修订段之间是 `\n\n`（244.61/244.62/244.63 实测）
      ⇒ 新段必须**正好**是「空行分隔的新修订段」⇒ ⛔ 不许顶格、不许有前导空白。
    """
    bad = []
    if not text.startswith("\n" + title):
        bad.append("首行不是「空行分隔的新修订段」（必须正好是 %r）" % title)
    if not text.endswith("\n"):
        bad.append("没有以换行结尾")
    if "\ufffd" in text:
        bad.append("含坏字 U+FFFD")
    if "\\" in text:
        bad.append("含反斜杠")
    if "%s" in text or "%d" in text or "%%" in text:
        bad.append("含没被替换的 %-占位（%s / %d / %%）")
    sp = printf_specs(text)
    if sp:
        bad.append("含 printf 占位：%s" % sorted(set(sp)))
    if '"""' in text:
        bad.append("含三引号")
    return bad


def overstrict_assert_hits(src):
    """⛔ 返回 src 里「`"%\" not in …`」这类**过严的整本账本级断言**的行号。

    ⚖⚠⚠ **用 AST 找断言**，⛔ 不用文本匹配：
      ⇒ 注释里**引用**那条坏规则（说明「本轮修掉了它」）不该被判违规
      ⇒ 守卫自己的**搜索串**也不该被判违规
      ⇒ 只认 `ast.NotIn` ＋ 常量 `"%"` ⇒ `"%s" not in` / `"%d" not in` **不**算违规

    ⚖⚠⚠⚖ **本函数自己踩过一次坑**（244.64）：第一版只扫 `Compare.comparators`
      ⇒ `assert "%" not in t` 里 `"%"` 在**左侧** ⇒ 守卫**抓不到** ⇒ 恒绿
      ⇒ ⇒ 负控制当场抓到 ⇒ 现在**左右两边都看**。
    """
    import ast

    hits = []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return hits
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assert):
            continue
        for sub in ast.walk(node.test):
            if not (isinstance(sub, ast.Compare)
                    and any(isinstance(op, ast.NotIn) for op in sub.ops)):
                continue
            consts = []
            if isinstance(sub.left, ast.Constant):
                consts.append(sub.left)
            consts.extend(c for c in sub.comparators if isinstance(c, ast.Constant))
            if any(c.value == "%" for c in consts):
                hits.append(node.lineno)
    return hits


# ================================================================ 自检
# ⚖⚠⚠⚖ **为什么住在 `lib/` 而不在 `lib/` 外面**（244.64）：
#   全回归脚本是按 `.cache/r244/` 下的文件名**自动发现**工具的
#   （`os.listdir(R244)` ⇒ `*.py` 且不以 `mut_`/`_` 开头 = 工具）
#   ⇒ 本模块若放在那一层 ⇒ 它会变成一个「无 --selftest 入口」的**跳过项**
#   ⇒ 回归的「跑不动 / 跑得动」计数会 +1 ⇒ 账本 244.64 段【9】里
#     **实测登记的那两个数**（自检 31/32、工具跳过 16 个）就**过期了**
#   ⇒ ⇒ 放到 `lib/` 子目录 ⇒ **不在自动发现范围内** ⇒ 计数不动 ⇒ 账本登记的数仍然为真
#   ⇒ ⚖⚠⚖ **判别式**：**回归的计数是「文件集」的指纹** ⇒ 动文件集就会动那些数
#     ⇒ 要么让文件集与登记时的快照一致，要么**重新登记**（⛔ 别让快照悄悄过期）
TITLE = "## 修订 244.64 —— "


def _selftest():
    """⚖ 自检：每条规则都要**能红**（负控制）且**零假阳性**（正控制）。"""
    ok = True
    base = "\n" + TITLE + "标题\n正文 MC95% 带 [0.0000, 0.0008]\n"

    # ---- ① 形状检查：真样 ----
    p = shape_problems(base, TITLE)
    print("%s 形状检查（真样）%s" % ("✅" if not p else "⛔", p or ""))
    ok = ok and not p

    # ---- ② 形状检查：负控制（改坏必被抓）----
    neg = [
        ("顶格写标题", lambda t: t.lstrip("\n")),
        ("没有以换行结尾", lambda t: t.rstrip("\n")),
        ("混入 %s", lambda t: t + "尾部 %s\n"),
        ("混入 %.2f", lambda t: t + "尾部 %.2f\n"),
        ("混入 %(k)s", lambda t: t + "尾部 %(k)s\n"),
        ("混入反斜杠", lambda t: t + "尾部 C:\\x\n"),
        ("混入坏字 U+FFFD", lambda t: t + "尾部 \ufffd\n"),
    ]
    for name, mut in neg:
        p = shape_problems(mut(base), TITLE)
        good = bool(p)
        print("%s 负控制：%s ⇒ %s" % ("✅" if good else "⛔", name, (p or ["没抓到！"])[0]))
        ok = ok and good

    # ---- ③ printf 判定：正控制（散文必不误伤）----
    for s in ("MC95% 带 [0.0000, 0.0008]", "58.7% vs 全体", "95% CI",
              "last 25% of long", "60%（12/20）", "95% 的上限"):
        sp = printf_specs(s)
        good = not sp
        print("%s 正控制：%r ⇒ %s" % ("✅" if good else "⛔", s, sp or "零假阳性"))
        ok = ok and good

    # ---- ④ printf 判定：负控制（真占位必被抓）----
    for s in ("尾部 %s", "尾部 %d", "尾部 %.2f", "尾部 %(k)s", "尾部 %02d"):
        sp = printf_specs(s)
        good = bool(sp)
        print("%s 负控制：%r ⇒ %s" % ("✅" if good else "⛔", s, sp or "没抓到！"))
        ok = ok and good

    # ---- ⑤ 作用域守卫：能抓过严规则、不误伤窄规则 ----
    good = bool(overstrict_assert_hits('assert "%" not in t\n'))
    print("%s 作用域守卫抓到 `assert \"%%\" not in t`" % ("✅" if good else "⛔"))
    ok = ok and good
    good = not overstrict_assert_hits('assert "%s" not in t and "%d" not in t\n')
    print("%s 作用域守卫不误伤窄规则（%%s / %%d）" % ("✅" if good else "⛔"))
    ok = ok and good

    print("✅ 自检全过" if ok else "⛔ 自检有红")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(_selftest())
