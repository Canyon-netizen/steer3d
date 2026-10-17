#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mut_r227_kcurve —— r227_kcurve.py 自检的**变异台**。

## 这条在量什么

`r227_kcurve.py --selftest` 报 13/13。⚠⚠ 那**只证明「没报错」**，
⛔ 不证明「能红」—— 一套恒绿的检查和一个真正有牙的检查，在输出上长得一模一样。

⚖ 所以本脚本拿 7 个**定点变异**去咬它：
每条变异都必须让**指定的**那条判据由 PASS 变 FAIL。
⚖ 只要有哪条变异「STAYED GREEN」，就说明那条判据是恒绿的装饰品。

## ⚠⚠⁴ 变异台设计纪律

1. ⚠⚠⁴ **变异必须只改一处代码点**，⛔ 不许顺手改注释/散文。
   改散文等于没改代码 —— 那样「变异后仍绿」会被误读成「判据有牙」。
2. ⚖ **定位按代码行，不按文件子串**：先确认目标串落在**唯一一行**上，
   不唯一就先停下重新定位，⛔ 不许猜。
3. ⛔ **不许事后调变异调到绿为止**。台架红了就是红了，说明该修判据或换变异。
4. ⚖ 变异在**内存里**做（`exec` 一份改过的源码），⛔ 不落临时文件、不动原件。

跑法：
    python3 mut_r227_kcurve.py           # 变异台
    python3 mut_r227_kcurve.py --selftest # 自检（变异台自身：台架本身也要能红）
退出码：0 = 全部变异都被抓住；1 = 有变异存活，或台架自身自检失败。
"""

import argparse
import io
import contextlib
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "..", "mutbak", "r227_kcurve.py")


# ⚖ 变异表：每一项 = (名字, 唯一代码串, 替身, 必须变红的那条判据)
# ⚠⚠ 每条的替身只改**一个条件/一个表达式**，不改别的。
MUTATIONS = [
    # G1 去掉「块数 ≠ 状态行数 ⇒ 硬失败」⇒ K3 该红（错位防护被拆）
    ("G1", "if len(blocks) != len(rows):",
     "if False and len(blocks) != len(rows):", "K3"),
    # G2 去掉「rc=0 却没读数 ⇒ 硬失败」⇒ K8 该红
    ("G2", "elif r[\"rc\"] == 0:",
     "elif False and r[\"rc\"] == 0:", "K8"),
    # G3 去掉「状态 k ≠ 读数自报 k ⇒ 硬失败」⇒ K5 该红
    ("G3", "if r[\"scope\"] == \"k\" and c[\"k\"] != r[\"k\"]:",
     "if False and r[\"scope\"] == \"k\" and c[\"k\"] != r[\"k\"]:", "K5"),
    # G4 去掉「n_eff ≠ P+t ⇒ 硬失败」⇒ K6 该红（**正是修订 226 排错阶梯那道**）
    ("G4", "if b[\"n_eff\"] != pt_sum:",
     "if False and b[\"n_eff\"] != pt_sum:", "K6"),
    # G5 去掉「tid 对不上 ⇒ 硬失败」⇒ K4 该红
    ("G5", "if b[\"tid\"] != r[\"tid\"]:",
     "if False and b[\"tid\"] != r[\"tid\"]:", "K4"),
    # G6 把「差值 ≪ 抖动 ⇒ 噪声主导」的判据**反过来** ⇒ K9 该红
    # ⚗ needle 原来带 `if …:`；⚖ 修订 236 把 `_verdict` 的两支改成条件表达式
    # ⚖ （为了在两支后面都能接上「余量/比值」尾巴），⚖ 那串就不存在了
    # ⚖ ⇒ 台架**定位失败**而不是静默放过 —— 这正是 needle 必须随实现一起改的原因。
    ("G6", "if abs(diff) < jitter else",
     "if abs(diff) > jitter else", "K9"),
    # G7 把功效下界公式改成常数 0 ⇒ K10 该红
    ("G7", "lb = 2.0 ** (1 - n)",
     "lb = 0.0", "K10"),
    # G8 把**精确**二项换回正态近似 ⇒ K14 该红
    # ⚠⚠ 2026-10-17 真机读数时撞出来的：近似在 n=4 全同向给 p=0.0455，
    # ⚖ 而理论下界是 0.125 —— 一个**不可能达到**的显著水平。
    ("G8", "p = sum(c for c in probs if c <= obs) / float(2 ** n)",
     "p = math.erfc(abs((pos - neg) / math.sqrt(n)) / math.sqrt(2.0))", "K14"),
    # G9 把位置身份差**减反**（single−k=1 ⇒ k=1−single）⇒ K15 该红
    # ⚖ 符号反了仍是一条「有读数、有 p」的曲线 ⇒ ⛔ 不可能被结构性检查抓到，
    # ⚖ 只能靠一条**知道正确答案**的判据（K15 拿夹具的 SINGLE_LO/LADDER_LO 算）。
    ("G9", "(lo_s - lo_1) if (lo_s is not None",
     "(lo_1 - lo_s) if (lo_s is not None", "K15"),
    # G10 拆掉**重复档检测** ⇒ K16 该红
    # ⚖ 拆掉它之后，重复档两次都能通过其余交叉校验 ⇒ 会**静默混进曲线**。
    ("G10", "if key in seen:",
     "if False and key in seen:", "K16"),
    # G11 把尾段阈值从「整整一半」改成「任何档」（等于把整条阶梯都算进尾段）⇒ K17 该红
    # ⚖ 症状：尾段「有四档」的断言失效，而输出看上去仍然四平八稳。
    ("G11", "if c[\"k\"] * 2 >= n_eff:",
     "if c[\"k\"] * 1 >= n_eff:", "K17"),
    # G12 把**稳健尺** jitter_med 换成 max ⇒ K18 该红
    # ⚠⚠ 症状：med 与 max 变成同一个数，跨轮次比较的尺子**静默退化成极值统计量**
    # ⚖ ⇒ 「多测两档就更容易判噪声主导」那个坑又回来了，而输出上看不出来。
    ("G12", "row[\"jitter_med\"] = _median(diffs) if diffs else None",
     "row[\"jitter_med\"] = max(diffs) if diffs else None", "K18"),
    # G13 让 `k_n_uniform` **恒为真** ⇒ 跨尺度警告永远不触发 ⇒ K19 该红
    # ⚠⚠ 症状：阶梯档数明明不一样（5 档 vs 6 档），报告却印「max 尺本轮内可比」
    # ⚖ ⇒ 下一个人会把两把不同刻度的尺子的数排进同一列比大小，
    # ⚖ 而输出上**看不出**任何异常 —— 这正是修订 232 那条坑原地复活。
    # ⚗ needle 从 `len` 起（NAME token）而不是从 `"k_n_uniform"` 起：
    # ⚖ 第一版从第 12 列的字符串字面量起，⚖ 台架直接判「落在散文 token 上」
    # ⚖ 而拒收 —— 这正是那个 tokenize 判据该干的事。
    ("G13", "len(k_n_hist) <= 1,",
     "True,  # mutated", "K19"),
    # G14 把 `k_hi` 退回 `ladder[-1]` ⇒ K20 该红
    # ⚠⚠⚠ 这是**已经真实发生过一次**的错误（修订 232）：阶梯一旦有 >50% 的档，
    # ⚖ `ladder[-1]` 就是最后一档，`k_hi→all` 的区间从「最后 50%」缩成
    # ⚖ 「最后 12.5%」，⛔ 而输出上**看不出任何区别**（符号、口径名都一样）。
    # ⚖⇒ 这个变异不是假想，是**回归**：它保证没人能悄悄把这个坑改回来。
    ("G14", "below = [c for c in ladder if n_eff and 2 * c[\"k\"] <= n_eff]",
     "below = list(ladder)", "K20"),
    # G15 把贴地板的**标记阈值**放大到 100% ⇒ 全部都标 ⇒ K21 必须红
    # ⚠⚠ 症状：判决照样印「超过 / 噪声」，⚖ 但「贴地板」这行警告**永远出现**，
    # ⚖ 读者会以为所有条目都靠不住 ⇒ ⚖ 一个恒真的警告等于没有警告
    # ⚖（这正是「恒红与恒绿一样是缺陷」那条）。
    ("G15", "KNIFE_EDGE = 0.05", "KNIFE_EDGE = 100.0", "K21"),
    # G16 把「|Δ| < 地板」的反号去掉 ⇒ 「低于地板」计数恒为 0 ⇒ K22 该红
    # ⚠⚠ 症状：报告印「✅ 每条都超过自己的地板」，⚖ 而实测 14 条里 10 条低于地板
    # ⚖ ⇒ 一个**恒真的安慰句**，⚖ 比不报更坏。
    # ⚖⚠ 这条与 G15 同源：**恒绿与恒红一样是缺陷**。
    ("G16", "and abs(d) < j)", "and False)", "K22"),
    # G17 从扫描参数一致性检查里**拿掉 gap** ⇒ K23 该红
    # ⚠⚠⚠ 症状：混了剂量尺度的格子**照样合池** ⇒ Δ 的量纲都不一样，
    # ⚖ 却会被静默算进同一个符号检验 ⇒ 而报告上还印着「gap=…」（单个值）。
    # ⚖⚠ 这是本笔最危险的一条：`gap` 不查 ⇒ **剂量层面的静默污染**。
    # ⚗⚠ 它**不是假想**：修订 238 之前 `gap` 真的**一直没被查**过。
    ("G17", 'for key in ("pos_frac", "n_steps", "gap"):',
     'for key in ("pos_frac", "n_steps"):', "K23"),
    # ---- 修订 244.24：n_eff 的来源戳与「独立来源」标签 ----
    # G18 把「有戳才准说独立」的条件抹平 ⇒ 无戳的日志也打「独立来源」
    # ⚠⚠⚠ 症状：旧 rand 日志（账本 244.11.4 明判「来源不可分辨」）的 137 格
    # ⚖ 全部被标成「BEGIN（独立来源，与读数 P+t 已互证）」⇒ 仪器在**没有证据
    # ⚖ 的地方断言独立**，且断言方向与账本结论相反。这就是本次实测抓到的那条。
    ("G18", 'if b.get("nmap"):', 'if True:', "K1b"),
    # G19 拿掉「两个不同来源戳 ⇒ 硬失败」⇒ 两轮追加的日志照读
    # ⚠⚠ 症状：两轮各写一行 NMAP，BEGIN 里那些 n_eff 来自哪张表已不可分辨，
    # ⚖ 而读数器会挑其中**一个**（排序后第一个）当作全篇的来源 ⇒ 半数格的
    # ⚖ 来源被**贴错标签**，且看不出来。与 K0c「排版混用即拒读」同族。
    ("G19", "if len(uniq) > 1:", "if False:", "K1c"),
    # G20 把统计口径退回 `c["n_eff"]` ⇒ 恒等于格数
    # ⚠⚠⚠ 症状：w_old 的 BEGIN 实测 0 格带 n_eff，页眉却印「137/137 格带
    # ⚖ n_eff」，而逐轨迹标签写着「未与 BEGIN 互证」⇒ 报告**自相矛盾**。
    # ⚖ 这条变异复现的就是本轮实测抓到的那次真 bug。
    ("G20", 'if c.get("n_eff_from_begin")', 'if c.get("n_eff") is not None', "K1e"),
    # G21 让来源戳**永远认不出来** ⇒ 有戳的日志也被降级
    # ⚖ 这条测的是「戳这条路径真的承重」：认不出戳 ⇒ 新跑批的两份日志
    # ⚖ 会从「独立来源」掉到「来源未标注」⇒ 判据会被 K1a 抓住。
    ("G21", 'NMAP_STAMP_RE = re.compile(r"^NMAP rows=(\\d+) md5=([0-9a-f]{32})(?:\\s|$)")',
     'NMAP_STAMP_RE = re.compile(r"^NEVER_MATCH$")', "K1a"),
]


def token_at(src, lineno, col):
    """⚖ 覆盖 (lineno, col) 那个位置的 token 的 (类型, 文本)。

    ⚠⚠⁴ 为什么问「**这个点**」而不是「**这一行**是不是散文」：
    ⚖ 2026-10-17 实测踩到 —— 代码行 `if b["tid"] != r["tid"]:` 里有个
    ⚖ 字符串字面量 `"tid"`，它的 STRING token 就落在那一行 ⇒
    ⚖ 按行判断会把**真代码**判成散文，于是 4 条变异定位全部失败。
    ⚖ 「行是散文」与「匹配点是散文」是两个不同的量，别混。
    ⚖ 所以这里**问解释器**，⛔ 不自己判断。
    """
    import tokenize
    from io import StringIO
    try:
        for tok in tokenize.generate_tokens(StringIO(src).readline):
            (srow, scol), (erow, ecol) = tok.start, tok.end
            if srow > lineno:
                break
            if srow <= lineno <= erow:
                if srow == erow:
                    if scol <= col < ecol:
                        return tok.type, tok.string
                elif col >= scol:
                    return tok.type, tok.string
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return None, None
    return None, None


def _is_prose(tok_type):
    """⚖ COMMENT / STRING / FSTRING_* 才算散文。⛔ INDENT/DEDENT/NL 不是。"""
    import token as _t
    import tokenize as _tz
    prose = {_t.COMMENT, _t.STRING}
    # ⚖ Python 3.12+ 才有 f-string 分 token；老版本没有这两个常量。
    for name in ("FSTRING_START", "FSTRING_MIDDLE", "FSTRING_END"):
        prose.add(getattr(_t, name, -1))
    return tok_type in prose


def find_code_line(src, needle):
    """⚖ 按**代码点**定位：needle 必须落在唯一一行的**代码 token** 上。

    ⛔ 不唯一就抛错 —— 变异台定位错了，台架报什么都不可信。
    ⚖ 落在注释/docstring 上也抛错 —— 变异散文不叫变异，
    ⚖ 那种「变异后仍绿」会被误读成「判据恒绿」。
    """
    hits = [(i + 1, l) for i, l in enumerate(src.split("\n")) if needle in l]
    if len(hits) != 1:
        # ⚠ 这条报错路径只在**多行命中**时才走到 —— 单行命中根本不走它。
        # ⚠ 所以它必须被 T3 显式验到，否则它坏了没人知道（2026-10-17 实测）。
        detail = "\n".join("  第%d行: %s" % (h[0], h[1]) for h in hits)
        raise AssertionError(
            "目标串在 %d 行上出现（应为 1 行）⇒ 变异定位不可靠，先停下重新定位：\n%s"
            % (len(hits), detail))
    lineno, line = hits[0]
    col = line.index(needle)
    # ⚠ needle 的起点**不许落在前导空白里**：函数体延续行上 col 0 那里
    # ⚖ **没有 token**（Python 只在缩进列变大时发 INDENT）⇒ 指到那里得 None。
    # ⚖ ⚠ 但 needle 起点落在**行中**（如 docstring 内部）是合法的，别误伤。
    lead = len(line) - len(line.lstrip())
    if col < lead:
        raise AssertionError(
            "needle 指到第%d行第%d列，落在前导缩进里（前导空白占 %d 列）"
            "⇒ 请去掉 needle 的前导空格" % (lineno, col, lead))
    tok_type, tok_str = token_at(src, lineno, col)
    if tok_type is None:
        raise AssertionError(
            "第%d行第%d列没落在任何 token 上（多半是指到了空白/标点之间的缝）"
            "⇒ 先停下重新定位" % (lineno, col))
    if _is_prose(tok_type):
        raise AssertionError("第%d行第%d列落在**散文** token（%s）上，不是代码：%s"
                             % (lineno, col,
                                {62: "COMMENT", 3: "STRING"}.get(tok_type, tok_type),
                                line.strip()))
    return lineno, line


def apply_mutation(src, needle, repl):
    lineno, line = find_code_line(src, needle)
    # ⚖ 只替换那一行里的目标串，别的一律不动
    new_line = line.replace(needle, repl)
    out = src.replace(line, new_line)          # ⚠ 按整行替换，缩进原样保留
    if out == src:
        raise AssertionError("变异没有真的改到文件（needle=%r）" % needle)
    return out, lineno


def run_selftest(src):
    """在内存里跑一份改过的源码的 --selftest，返回 (rc, 输出文本)。

    ⚖ ⚠ `__name__` 不叫 __main__ ⇒ 模块底部的 sys.exit(main()) 不会触发，
    ⚖ 于是我们能干净地只调 selftest()。
    """
    mod = types.ModuleType("mutant_r227_kcurve")
    mod.__file__ = "r227_kcurve.py(mutant)"
    code = compile(src, "r227_kcurve.py(mutant)", "exec")
    exec(code, mod.__dict__)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = mod.selftest()
    return rc, buf.getvalue()


def failed_tests(text):
    """从自检输出里抽出 FAIL 的判据编号。

    ⚠⚠⚠ 修订 244.24：编号匹配必须是 `K` + **字母数字**（`K1a`/`K0b` 也算），
    ⚖⛔ 原来的 `tok[1:].isdigit()` 只认 `K1`/`K23` 这种纯数字 ⇒ **所有带字母的
    ⚖ 判据对本台架完全不可见**：它们既不会计入基线，也不会被算作「被抓住」。
    ⚖ 那不是显示瑕疵，是**真盲区** —— 指向带字母判据的变异会永远「存活」，
    ⚖ 而台架会把这当成「判据恒绿」。实测：K0a/K0b/K0c 三条一直不在计数里。
    """
    out = set()
    for line in text.split("\n"):
        if line.startswith("[FAIL]"):
            tok = line.split()[1] if len(line.split()) > 1 else ""
            if tok and tok[0] == "K" and tok[1:].isalnum():
                out.add(tok)
    return out


def passed_tests(text):
    """⚠⚠ 修订 244.24：与 `failed_tests` 同一条纪律 —— 必须 `isalnum()`，
    ⛔ 不可用 `isdigit()`（那会让带字母的判据从基线计数里消失）。"""
    out = set()
    for line in text.split("\n"):
        if line.startswith("[PASS]"):
            tok = line.split()[1] if len(line.split()) > 1 else ""
            if tok and tok[0] == "K" and tok[1:].isalnum():
                out.add(tok)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=TARGET)
    ap.add_argument("--selftest", action="store_true",
                    help="变异台自身的自检（用坏变异证明本台架会红）")
    a = ap.parse_args()

    with open(a.target) as f:
        base = f.read()

    # ---- 变异台自身的自检：证明**定位器**该成功时成功、该报错时报错
    # ⚠⚠ 极性必须写对：合法变异**本来就该定位成功**，
    # ⚠⚠ 自检若期待它报错，那是在测一个相反的东西 —— 自检红了不等于台架坏了。
    if a.selftest:
        ok = 0
        total = 0

        # T1 合法串：恰好一行、且是代码行 ⇒ 必须定位成功
        total += 1
        try:
            ln, line = find_code_line(base, MUTATIONS[0][1])
            assert "if " in line, line
            print("[PASS] T1 合法串定位成功且是代码行（第%d行）" % ln)
            ok += 1
        except Exception as e:
            print("[FAIL] T1 合法串竟然定位失败：%s" % e)

        # T2 不存在的串：必须被拒（不许「变异了一个不存在的地方」）
        total += 1
        try:
            find_code_line(base, "这段串在文件里根本不存在_zzz")
            print("[FAIL] T2 不存在的串居然定位成功")
        except AssertionError:
            print("[PASS] T2 不存在的串被正确拒绝")
            ok += 1

        # T3 出现在多行的串：必须被拒（定位不唯一 ⇒ 变异不可靠）
        total += 1
        try:
            find_code_line(base, "HardFail")
            print("[FAIL] T3 多行串居然定位成功 —— 会『猜中一个地方』")
        except AssertionError as e:
            assert "应为 1 行" in str(e), str(e)
            print("[PASS] T3 多行串被正确拒绝（%s）" % str(e).split("⇒")[0].strip())
            ok += 1

        # T4 落在散文（注释/docstring）上的串：必须被拒
        # ⚖ 两例都要：一条真 `#` 注释，一条**模块 docstring 里的续行**
        # ⚖ （后者是 `startswith("#")` 测不到的那一类，2026-10-17 实测）
        for label, needle, expect in (
                ("#注释", "# ⚖ 两个尺子", "落在**散文** token"),
                ("docstring续行", "读一半比读错强这句话是错的", "落在**散文** token")):
            total += 1
            try:
                find_code_line(base, needle)
                print("[FAIL] T4 %s 串居然定位成功 —— 会变异散文" % label)
            except AssertionError as e:
                if expect not in str(e):
                    print("[FAIL] T4 %s 报错信息不对：%s" % (label, e))
                else:
                    print("[PASS] T4 %s 串被正确拒绝（变异的是散文，不是代码）" % label)
                    ok += 1

        # T5 逐条变异都必须真的改到文件（改了 0 处也要报错）
        total += len(MUTATIONS)
        for name, needle, repl, expect in MUTATIONS:
            try:
                mut_src, ln = apply_mutation(base, needle, repl)
                assert mut_src != base, name
                print("[PASS] T5.%s 变异确实改到了第%d行" % (name, ln))
                ok += 1
            except Exception as e:
                print("[FAIL] T5.%s 变异没改到：%s" % (name, e))

        print("mut_r227_kcurve --selftest: %d/%d" % (ok, total))
        return 0 if ok == total else 1

    # ---- 变异台本体
    rc0, text0 = run_selftest(base)
    n0 = len(passed_tests(text0)) + len(failed_tests(text0))
    print("=" * 74)
    print("变异台：目标 %s" % os.path.basename(a.target))
    print("基线自检：%d/%d%s" % (len(passed_tests(text0)), n0,
                                 "（基线就不绿，先修判据再谈变异）"
                                 if rc0 != 0 else ""))
    print("=" * 74)
    if rc0 != 0:
        print("⛔ 基线就不全绿 —— 变异结果没有意义，先修判据。")
        return 1
    base_pass = passed_tests(text0)
    print("基线判据：%s\n" % ",".join(sorted(base_pass)))

    survived = []
    for name, needle, repl, expect in MUTATIONS:
        try:
            mut_src, lineno = apply_mutation(base, needle, repl)
        except AssertionError as e:
            print("[台架坏了] %s 定位失败：%s" % (name, e))
            survived.append(name + "(定位失败)")
            continue
        rc, text = run_selftest(mut_src)
        red = failed_tests(text)
        if expect in red:
            print("[抓住了] %-3s 第%-4d行  %-46s ⇒ %s 由 PASS 变 FAIL ✅"
                  % (name, lineno, needle[:46], expect))
        else:
            print("[存活!!] %-3s 第%-4d行  %-46s ⇒ %s **仍是 PASS** ⛔"
                  % (name, lineno, needle[:46], expect))
            survived.append("%s→%s" % (name, expect))

    print("\n" + "=" * 74)
    if survived:
        print("⛔ 有 %d 个变异存活：%s" % (len(survived), "、".join(survived)))
        print("   ⇒ 这些判据是**恒绿的装饰品**，要么修判据，要么换能改变被观测量的变异。")
        return 1
    print("✅ %d 个变异全部被抓住（每条都让**指定的**那条判据由 PASS 变 FAIL）"
          % len(MUTATIONS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
