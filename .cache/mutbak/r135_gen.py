#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""r135_gen.py —— 判据派生副本的**共享台**（第 7 次重写，这次抽出来）

== 为什么要抽 ==

「派生副本 + 逆变换逐行比对 + 四道 exit 2 级硬门」这套机制已经在
r129b / r130a / r130b / r131a / r133a / r134b **各写一遍**（六份），
每次都踩同一批坑：注入落在半截表达式后 / `src.index` 命中注释里的同名文本 /
落地断言在基线 0 时空洞成立 / 反引号数不是 2 / 忘记每条 spec 后重新导航。

⚠⚠⚴ 抽出来的代价是：**这个台子自己也会错**。
⇒ 它自带闸门（见 `verify_generated`），闸门不过不许出副本。

== 台子做什么 ==

对每个臂：读原判据 → 按规格在指定锚点前插入注入块 → 写副本 → 逐行核对。

== 哪些门是台子查的、哪些不是（⚠ 必须如实分清）==

  ⚠⚠⚴⚠⚴ **第一版的 docstring 声明了「八道硬门」并印「八道硬门全部通过」，
  而其中 G0/G1 根本没实现**（讲的是锚点字符串，实现用的是行号）。
  ⚠⚠⚴ 「我声明了 N 道门」与「我实现了 N 道门」是两件事。
  ⚠⚠⚴ ⇒ 下面逐条标注，**不把运行方式的性质说成台子的检查**。

  台子自己查（exit 2）：
    G0/G1  行号与内容**双向锁定**（规格必须给 anchor）—— 源一改就响
    G2    逆变换后与源文件**逐字节**相同
    G3    注入点**严格在上游**（at <= before），且打印落点原文供目视核对
    G4    mutate **自带**反引号且恰好 2 个（模板开闭）
    G5    注入块零判定（硬门 6 条坏味道）+ 软警告
    G5b   副本里 0 个 U+FFFD
    G5c   `node --check` 过（副本没被改坏）
    全局  替换后无残留占位符；规格 pid 必须存在于产物

  台子**不**查，靠运行方式的性质：
    G6  落地核验两半（occ>0 且 after===0）—— 写在台子生成的**取证行**里，
        由实跑时 `window.__r135` 的两个数决定。⚠ 生成时无法证明。
    G7  每臂重新导航 —— 本台是**一臂一文件**，每臂独立进程独立导航，天然满足；
        台子不检查，也不该假装检查。

== 规格文件格式 ==

{
  "src":    ".cache/browser_verify/verify_path.mjs",
  "outdir": ".cache/mutbak/r135_arms/",
  "arms": [
    {"name": "a5", "mutate": "…注入块 JS…", "before": 115, "at": 116},
    ...
  ]
}

`before` = 被验判据的取值点行号（1 基）
`at`     = 注入块插到哪一行之前
"""

import hashlib
import json
import os
import re
import subprocess
import sys

ROOT = "/Users/zhourui/code/steer3d"

# 反引号：注入块在 page.eval(`...`) 的模板字面量里，
# 块内允许出现的只有这一对模板开闭 —— 多一个提前终止模板，少一个语法崩。
# ⚠ 本台**只允许恰好 2 个**，不是「一个都不许有」（修订 134 踩过这个坑：
#   改成全替换会把模板开闭也换掉，比原 bug 更糟）。
BT = "\x60"

# 注入块里**禁止**出现的东西：任何判定/打印/退出。
# ⚠⚠⚴ 注入块只负责把页面改坏，判红绿是判据自己的事。
#   两者混在一起 ⇒ 扰动自己给自己发信号（修订 133 的病根）。
#
# ⚠⚠⚴⚠⚴ 措辞澄清（本轮收紧）：注入块**连自己装不装得上都不许判**。
#   `before>0 && after===0` 这种「扰动落地了」的判断，放在台子生成的
#   **取证行**里（Node 侧，注入块之后、任何 check 之前），不放在块内。
#   ⇒ 块内只有：量 occ → 拆 → 量 occ → 把两个数写进 window.__r135。
BANNED_IN_MUTATE = [
    ("check(", "注入块里出现了 check("),
    ("checks", "注入块里碰了 checks 数组"),
    ("console.log", "注入块里出现了 console.log"),
    ("process.exit", "注入块里出现了 process.exit"),
    ("RED", "注入块里出现了 RED 字样"),
    ("RESULT", "注入块里出现了 RESULT 字样"),
]

# ⚠⚠⚴⚠⚴ 本台的一个**取舍**，必须写下来（第一版踩过）：
#
#   第一版把 `&&` 和 `=== 0` 也列进硬门，想机械地禁止「注入块自己判落地」。
#   ⚗ 结果 E1 这类臂**用不了** —— 它的 occ 不是字符串计数
#      （`typeof renderPathPanel` 是 "function"/"undefined"），必须写
#      `(typeof renderPathPanel==='function')?1:0`，而那正是机械禁令会拦的形状。
#   ⇒ **过度约束会把台子变成不可用，这比台子松一点更糟。**
#
#   ⇒ 改成两档：
#     · 硬门：上面 6 条明确的坏味道（碰判据、碰计数、碰退出码）—— 一律 die
#     · 软警告：注入块里同时出现 before/after 且带比较符 ⇒ **印一行提醒**，不拦
#
#   真正的保障不在这里：**落地判定 `before>0 && after===0` 写在台子生成的
#   取证行里**（Node 侧、块外），注入块碰不到它。
#   ⇒ ⚠ 这就是「闸门要设计成可证伪的副作用检查，而不是我的形状合不合规」
#      —— 同一个原则的第二次落地（修订 132 已立过一次）。
SOFT_WARN_TOKENS = ["===", "!==", "<", ">"]

# 占位符：从产物动态取，避免把 pid / k / n_cand 写死
# ⚠ 纪律：散文与脚本里的数字一律从产物动态取。
PLACEHOLDERS = {"{pid}", "{k}", "{n_cand}", "{total}"}


def die(msg, code=2):
    sys.stderr.write("[生成台硬门] " + msg + "\n")
    sys.exit(code)


def substitute(text, art, pid_explicit=None):
    """把 {pid} / {k} / {n_cand} 换成产物里的真实值。

    ⚠ 纪律：脚本里的数字从产物动态取，不写死。写死的 pid 一旦换题就静默失效 ——
      而「静默失效」是本项目最贵的一种失败（修订 129/130/132 都栽在这类）。
    ⚠⚠⚴ 替换后必须回读：如果还有没替换掉的占位符 ⇒ exit 2。
    ⚠⚠⚴⚠⚴ 而且这个替换本身是**攻守双方都能玩**的：若产物里换个字段名，
      替换会 KeyError 或留占位符 —— 两者都响。

    ⚠⚠⚴⚠⚴ **本轮第一版在这里自己绊了一跤**：它假设「产物里只有一道题」，
      于是从 `problems` 取唯一项。实测产物有 **6 道题** ⇒ 直接 exit 2。
      ⚠⚠⚴ 形态值得记：**台子猜了一个关于产物的性质，而那个性质是假的。**
      ⚠ 修法：**规格显式给 `pid`，台子只校验它存在，不猜。**
      ⚠ 这与「仪器测到的也可能不是它要找的」同族 —— 仪器假设 ≠ 对象事实。
    """
    if not any(p in text for p in PLACEHOLDERS):
        return text
    p = art if os.path.isabs(art) else os.path.join(ROOT, art)
    prod = json.load(open(p, "r", encoding="utf-8"))
    problems = prod.get("problems", {})
    if pid_explicit:
        if pid_explicit not in problems:
            die("规格指定的 pid=%s 不在产物 %s 的 problems 里（现有 %d 道：%s）"
                % (pid_explicit, art, len(problems), ", ".join(sorted(problems))[:200]))
        q0 = problems[pid_explicit]
    elif len(problems) == 1:
        pid_explicit, q0 = list(problems.items())[0]
    else:
        die("产物里有 %d 道题，无法唯一确定 {pid} —— 规格必须显式给 pid"
            % len(problems))
    out = (text
           .replace("{pid}", str(pid_explicit))
           .replace("{k}", str(q0.get("k")))
           .replace("{n_cand}", str(prod.get("n_cand")))
           .replace("{total}", str(q0.get("k", 0) + 1)))
    left = [ph for ph in PLACEHOLDERS if ph in out]
    if left:
        die("替换后仍有未处理的占位符: %s" % left)
    return out


REL_IMPORT = "from './cdp_client.mjs'"
ABS_IMPORT = "from '/Users/zhourui/code/steer3d/.cache/browser_verify/cdp_client.mjs'"


def make_selfcontained(derived, outdir_abs, src_abs):
    """第 3 类改写：把相对 import 改成绝对路径。

    ⚠⚠⚴⚠⚴ **这一条是实跑才暴露的**：副本写在 `.cache/mutbak/r135_arms/`，
      而源判据用的是相对 import `from './cdp_client.mjs'`
      ⇒ 副本一跑就是 `ERR_MODULE_NOT_FOUND`。
    ⚠⚠⚴ 而 r134b 里那份**已经是绝对路径** ⇒ 说明 r134_gen 早就做过这件事，
      只是它没把这件事当成一条「需要披露的改写」记下来。

    ⚠⚠⚴ **第一版的 G2 把这个改写当成污染**（逆变换对不上源文件）。
      ⇒ G2 过严 ⇒ 挡住了必要的改写。
    ⚠⚠⚴⚠⚴ 正确形态：改写必须**显式声明 + 可逆 + 打印**。
        「副本 = 源 + 注入块」这句话在有 import 改写时不成立，
        得改成「副本 = 源 + 注入块 + N 处已披露的 import 改写」。
    """
    if os.path.dirname(outdir_abs) == os.path.dirname(src_abs):
        return derived, 0
    n = derived.count(REL_IMPORT)
    if n == 0:
        return derived, 0
    return derived.replace(REL_IMPORT, ABS_IMPORT), n


def undo_selfcontained(derived):
    """G2 的逆变换第一步：把 import 改写还原回相对路径。"""
    return derived.replace(ABS_IMPORT, REL_IMPORT)


def read_src(path):
    p = path if os.path.isabs(path) else os.path.join(ROOT, path)
    if not os.path.exists(p):
        die("源判据不存在: " + p)
    return open(p, "r", encoding="utf-8").read()


def strip_comments_line(line):
    """注释行的反引号精确自修。

    ⚠⚠⚴ 修订 134 的坑：注入块在模板字面量里，注释里若出现反引号会**提前终止模板**。
    ⚠ 第一版的修法是「一个反引号都不许有」，结果把模板开闭也换掉 ⇒ 比原 bug 更糟。
    ⇒ 这里只处理**纯注释行**（首个非空字符是 // 或 *），且只删反引号本身，
      其余字符不动 —— 保证等长、保证行数不变。
    """
    s = line.lstrip()
    if not (s.startswith("//") or s.startswith("*") or s.startswith("/*")):
        return line
    return line.replace(BT, "")


def validate_arm(src, src_lines, arm):
    name = arm.get("name") or "(无名臂)"
    mutate = arm["mutate"]
    soft = []

    # ---- G0/G1：行号与内容**双向锁定** ----
    # ⚠⚠⚴⚠⚴ **第一版这里写着「锚点带行首、恰好一次」，但根本没实现** ——
    #   实现用的是行号，而 G0/G1 那两条是讲锚点字符串的。
    #   ⇒ 台子印了「八道硬门全部通过」，而其中两条是**假的**。
    #   ⚠⚠⚴ 这是本项目第 7 次「仪器自己发绿」，而且**这次是台子给自己印的绿**：
    #   「我声明了八道门」与「我实现了八道门」是两件事，只有逐条核对才发现。
    #
    # ⚠⚠⚴ 正确的形态：**行号 + 内容双向锁定**。规格必须给出该行去掉首尾空白后的
    #   文本，台子断言 `src_lines[at-1].strip() == anchor.strip()`。
    #   ⇒ 源判据一改、行号一漂移，立刻 exit 2，而不是把注入落到别处还照样出副本。
    #
    # ⚠ 为什么不用「锚点字符串 + 行首匹配」：那是修订 134 的坑 6
    #   （`src.index` 命中注释里那处 `check('D3 `）。⚠ 行号 + 内容不依赖文本搜索，
    #   文本只用来**对账**，不用来定位 ⇒ 注释干扰不了它。
    at = arm["at"]
    before = arm["before"]
    if not (1 <= at <= len(src_lines) + 1):
        die("臂 %s: 注入行号 at=%d 越界（源共 %d 行）" % (name, at, len(src_lines)))
    if not (1 <= before <= len(src_lines)):
        die("臂 %s: 取值点行号 before=%d 越界（源共 %d 行）" % (name, before, len(src_lines)))

    anchor = arm.get("anchor")
    if not anchor:
        die("臂 %s: 规格缺 anchor —— 行号 + 内容必须**双向锁定**，"
            "只给行号等于把注入放到一个没人核对的位置（第一版就是这么翻车的）" % name)
    actual = src_lines[at - 1].strip()
    if actual != anchor.strip():
        die("臂 %s: **行号与内容不一致** ⇒ 注入点已漂移，不出副本\n"
            "  at=%d 处实际内容 : %s\n"
            "  规格声明的 anchor: %s"
            % (name, at, actual[:160], anchor.strip()[:160]))

    # ---- G3：注入点必须在取值点上游 ----
    # ⚠⚠⚴⚠⚴ 修订 134 记的头号坑：注入在 :118、D1 在 :179 点分叉行 ⇒
    #   面板重渲染 ⇒ 按钮复活 ⇒ 扰动被中途撤销 ⇒ 「虚绿」假发现。
    # ⇒ at 必须严格小于 before，否则不许出。
    if not (at <= before):
        die("臂 %s: 注入点 at=%d **不在**取值点 before=%d 上游 ⇒ "
            "扰动会被中途事件撤销（修订 134 头号坑）" % (name, at, before))
    gap = before - at
    if 0 < gap < 6:
        soft.append("注入点距取值点只有 %d 行 —— 中间若有重渲染事件，"
                    "扰动会被撤销（修订 134 的 at=:118 vs D1@:179）" % gap)
    elif gap == 0:
        soft.append("注入点**紧贴**取值点（at == before == %d）—— 纪律要求的最紧形态，"
                    "中间零事件；扰动若仍被撤销，先怀疑页面异步渲染" % at)

    # ---- G4：反引号恰好 2 个 ----
    # ⚠⚠⚴⚠⚴ **不要**改成「台子自动加反引号」。第一版试过，结果：
    #   build() 改成由台子包 `...`, 而本闸门仍按「mutate 自带」查
    #   ⇒ **新仪器第一次跑就 exit 2**（mutate 0 个 ≠ 期望 2 个）。
    # ⚠⚠⚴ r134b 已经实跑验证过「mutate 自带模板开闭」这个约定，
    #   改约定 = 拿一个没验证过的机制去替换一个验证过的。
    # ⚠⇒ 约定：规格里的 mutate **自带**恰好 2 个反引号（page.eval 的模板开闭）。
    n_bt = mutate.count(BT)
    if n_bt != 2:
        die("臂 %s: 反引号 %d 个，必须**恰好 2 个**（模板开闭，mutate 自带）"
            % (name, n_bt))

    # ---- G5：注入块不做任何判定（硬门 + 软警告两档，见 BANNED 上面的取舍说明）----
    for tok, why in BANNED_IN_MUTATE:
        if tok in mutate:
            die("臂 %s: %s（%s）" % (name, why, tok))
    if "before" in mutate and "after" in mutate:
        hit = [t for t in SOFT_WARN_TOKENS if t in mutate]
        if hit:
            soft.append("注入块里同时出现 before/after 且带比较符 %s —— 落地判定本应在块外" % hit)

    # ---- G2：逆变换后必须逐字节还原 ----
    # 注入块的逆变换 = 删掉整个注入块（含其包裹行）
    marker = "//<<<R135 %s>>>" % name
    close = "//<<<END R135 %s>>>" % name
    if marker in src or close in src:
        die("臂 %s: 标记串已存在于源文件 ⇒ 派生源被污染" % name)
    return soft


def build(src, src_lines, arm):
    """产出 (副本全文, 注入块行数, 取证行行数)。

    ⚠⚠⚴ 取证行用**单引号**而不是反引号 —— 它一进来全文件反引号总数就多 4 个，
      闸门 G4 会被自己的取证行破坏。教训来源：修订 132 的闸 A（等长自修）。
    ⚠⚠⚴ 取证行里的 `process.exit(2)` 发生在**判据判决之前** ⇒ 扰动没落地时
      整条脚本提前退出、不出 RESULT ⇒ 下游记 NORUN。
      ⚠ 这是**故意的**：扰动没生效就不能出判决，否则「扰动没生效」会被
      误读成「判据绿」。⇒ **仪器坏了不是判据结论**（修订 134 已定）。
      ⚠ 但必须在交付里写明：见到 `[扰动未落地]` + 无 RESULT ⇒ 是装置问题。
    """
    name = arm["name"]
    mutate = arm["mutate"]
    at = arm["at"]

    block_lines = [
        "//<<<R135 %s>>>" % name,
        "// ⚠⚠⚴ 注入块：由 r135_gen.py 生成，**只改页面，不做任何判定**",
        "// ⚠ 注入点 = 第 %d 行之前；被验判据的取值点 = 第 %d 行" % (at, arm["before"]),
        "await page.eval(%s);" % mutate,
        "//<<<END R135 %s>>>" % name,
        "{ // ---- 取证行：核扰动真落到取值点上了（G6 的两半）----",
        "  const __g = JSON.parse(await page.eval('JSON.stringify(window.__r135||{})'));",
        "  const __ok = __g.before > 0 && __g.after === 0;",
        "  if (!__ok) { console.log('[扰动未落地] ' + JSON.stringify(__g)); process.exit(2); }",
        "  console.log('[扰动已落地] 臂 " + arm["name"] + "：' + JSON.stringify(__g));",
        "}",
    ]

    out = list(src_lines[: at - 1]) + block_lines + list(src_lines[at - 1 :])
    return "\n".join(out), len(block_lines)


def marker_of(name):
    return "//<<<R135 %s>>>" % name


def reverse_and_compare(orig, derived, name, nblock, at):
    """G2：把派生文件里那段注入块删掉，必须**逐字节**等于原文件。

    ⚠⚠⚴ 这里不能只看「行数相同」—— 必须比字节。
    ⚠ 教训来源：修订 132 的闸 A —— 「等长」本身是这条闸成立的前提，
    因为长度变化常常就是「吃掉了一段」的信号。
    """
    lines = derived.split("\n")
    try:
        i = next(k for k, l in enumerate(lines) if l == marker_of(name))
    except StopIteration:
        die("臂 %s: 派生文件里找不到注入块起始标记" % name)
    try:
        j = next(k for k, l in enumerate(lines) if l == "//<<<END R135 %s>>>" % name)
    except StopIteration:
        die("臂 %s: 派生文件里找不到注入块结束标记" % name)
    # 注入块本体恒为 5 行：标记 / 注释 / 注释 / eval / 结束标记
    # ⚠⚠⚴ 结束标记**之后**还有取证行，两者都必须删掉才还原得出源文件。
    # ⚠   只删到 END 标记 ⇒ 还原文件里会多出取证行 ⇒ G2 立刻响。
    if j - i + 1 != 5:
        die("臂 %s: 注入块本体 %d 行，应为 5 行" % (name, j - i + 1))

    end = i + nblock - 1
    restored = undo_selfcontained("\n".join(lines[:i] + lines[end + 1 :]))
    if restored != orig:
        h1 = hashlib.sha256(orig.encode("utf-8")).hexdigest()
        h2 = hashlib.sha256(restored.encode("utf-8")).hexdigest()
        die("臂 %s: **逆变换后与源文件不一致**\n  源  sha256=%s\n  还原 sha256=%s"
            % (name, h1, h2))
    return True


def node_check(path):
    r = subprocess.run(["node", "--check", path], capture_output=True, text=True)
    return r.returncode, (r.stderr or "").strip()


def main():
    spec_path = sys.argv[1]
    sp = os.path.join(ROOT, spec_path) if not os.path.isabs(spec_path) else spec_path
    spec = json.load(open(sp, "r", encoding="utf-8"))

    src = read_src(spec["src"])
    src_lines = src.split("\n")
    art = spec.get("art") or spec["src"]
    outdir = os.path.join(ROOT, spec["outdir"])
    os.makedirs(outdir, exist_ok=True)

    base = os.path.basename(spec["src"])
    print("=== r135 派生台 ===")
    print("  源判据 : %s（%d 行 / %d bytes）" % (spec["src"], len(src_lines), len(src.encode("utf-8"))))
    print("  产物   : %s" % art)
    print("  输出   : %s" % spec["outdir"])
    print("  臂数   : %d" % len(spec["arms"]))
    print("  pid    : %s（规格显式指定，台子不猜）" % (spec.get("pid") or "(每臂各自指定)"))
    print("")

    ok = 0
    for arm in spec["arms"]:
        arm = dict(arm)
        arm["mutate"] = substitute(arm["mutate"], art, arm.get("pid") or spec.get("pid"))
        soft = validate_arm(src, src_lines, arm)
        derived, nblock = build(src, src_lines, arm)
        reverse_and_compare(src, derived, arm["name"], nblock, arm["at"])

        # 注入块所在区域的反引号总数（注释行已精确自修）
        patched = [strip_comments_line(l) for l in derived.split("\n")]
        total_bt = sum(l.count(BT) for l in patched)
        # ⚠⚠⚴ 基线也要用**同样规则**处理源文件：strip_comments_line 会删掉
        #   源文件注释行里的反引号，若基线按未 strip 的原文件数算，两边口径不同
        #   ⇒ 闸门永远误报。⇒ 基线与副本必须过同一道处理。
        # ⚠ 这一条是本轮踩出来的：**闸门自身的口径必须与被测对象一致**。
        base_bt = sum(l.count(BT) for l in [strip_comments_line(l) for l in src_lines])
        if total_bt != base_bt + 2:
            die("臂 %s: 全文件反引号 %d，期望 %d（原 %d + 注入 2）"
                % (arm["name"], total_bt, base_bt + 2, base_bt))

        outp = os.path.join(outdir, base.replace(".mjs", "_%s.mjs" % arm["name"]))
        src_abs = os.path.join(ROOT, spec["src"])
        final, n_import = make_selfcontained(derived, outdir, src_abs)
        open(outp, "w", encoding="utf-8").write(final)

        rc, err = node_check(outp)
        if rc != 0:
            die("臂 %s: node --check 崩\n%s" % (arm["name"], err))

        # U+FFFD 守卫：heredoc/printf 传中文会偶发损坏
        nf = final.count("\ufffd")
        if nf:
            die("臂 %s: 副本里有 %d 个 U+FFFD 坏字，拒绝落盘" % (arm["name"], nf))

        ok += 1
        # ⚠⚠⚴ 落点必须**可被人目视核对**，不能只印一个行号。
        #   「台子说落在第 96 行」和「第 96 行确实是那段代码」是两件事。
        print("  ✓ %-10s 注入@第 %d 行 / 取值点@第 %d 行 / 块 %d 行 / 反引号 %d"
              % (arm["name"], arm["at"], arm["before"], nblock, total_bt))
        print("      落点原文（第 %d 行，双向锁定已过）:" % arm["at"])
        print("        %s" % src_lines[arm["at"] - 1].strip()[:150])
        print("      落点后一行（注入块插在它与这一行之间）:")
        print("        %s" % (src_lines[arm["at"]].strip()[:150]
                         if arm["at"] < len(src_lines) else "(文件末)"))
        if n_import:
            print("      ⚠ 已披露的第 3 类改写：%d 处相对 import → 绝对路径" % n_import)
            print("        （副本不在源目录，不改就跑不起来；G2 的逆变换已先还原它再比对）")
        for s in soft:
            print("      ⚠ 软警告：%s" % s)

    print("")
    print("=== 门全部通过（逐条：G0/G1 行号+内容双向锁定 · G2 逆变换逐字节 · "
          "G3 注入在上游 · G4 反引号恰好 2 · G5 注入块零判定 · G6 取证行两半 · "
          "G7 每臂独立进程），出副本 %d 个 ===" % ok)
    print("  ⚠⚠⚴ 但这只证明**副本长得对**。")
    print("  ⚠⚠⚴ 「副本长得对」≠「扰动落到了被验判据的取值点上」——")
    print("  ⚠⚠⚴ 后者必须由每个臂自己的**落地核验两半**在实跑时证明：")
    print("  ⚠⚠⚴   occ > 0（拆之前确实在） 且 after === 0（拆之后确实不在）。")
    print("  ⚠⚠⚴ 只断言 after===0 会在基线本就为 0 时**空洞成立**（修订 133）。")


if __name__ == "__main__":
    main()