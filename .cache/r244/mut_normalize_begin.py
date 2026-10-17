#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""变异台：证明 `normalize_begin.py` 的四道闸**能红**。

⚖⚠⚠ 为什么台架要**独立**实现那四问（修订 244.1）
--------------------------------------------------
本轮实测：闸 3 的**第一版**在真实日志上印「非 BEGIN 行逐字节不变」而**实际改了字节**
（文本模式读入 ⇒ 通用换行转换把 274 个 `\r` 变成 `\n`）。
⇒ 「脚本自己印绿」不等于「产物合规」。

⚖ 如果台架只是**读脚本的 stdout 看有没有报错**，那么它验证的是
   「脚本认为自己绿」，⛔ 那正是本次翻车的形态。
⚖⚠ 本台架改为**自己动手量产物**（读文件、按字节切、算序号、算 tid 对齐、
   算 token 集合与行数），**不复用被测脚本的任何函数或正则**。
⚗ 于是两层互相独立：
     caught_by=script —— 被测脚本自己的闸抓到了
     caught_by=bench  —— 只有台架独立量才抓到（自查被删/失效时靠它兜底）

判据三元组（修订 244 的教训：不能只记 PASS/FAIL）：
  red        变异体退出码非 0
  right_test 红在**期望的那道闸**（stdout 含期望原因串）
  caught_by  script / bench / both / none
⛔ `none` = 台架没抓住 ⇒ 这是**台架的洞**，必须先修台架，不能记 PASS。

用法：
    python3 mut_normalize_begin.py
退出码：0 = 全部变异都被抓住；1 = 有变异没被抓住（台架失效）
"""

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
TARGET = os.path.join(HERE, "normalize_begin.py")
REAL_LOG = os.path.join(HERE, "r244_warm.log")
REAL_STATUS = os.path.join(HERE, "r244_warm_status.txt")
PY = sys.executable

BASELINE_MD5 = "ac39f192fbda3afc6a484b8ee52538bd"

# ⚖ 规范化后的真日志（契约格式）—— M7/M8/M9 的输入底本。
# ⚖⚠⚠ 它是**被测体的产物**，用它当下一轮的输入会形成循环依赖 ⚠
# ⚖  但这里只取它的**文本**当夹具（并由 bench 独立复核），⛔ 不采信它的任何结论。
REAL_NORM_LOG = os.path.join(HERE, "r244_warm.norm.log")
if not os.path.exists(REAL_NORM_LOG):
    REAL_NORM_LOG = ""
COMPLIANT_TEXT = (open(REAL_NORM_LOG, encoding="utf-8").read()
                  if REAL_NORM_LOG else "")

# ---- 台架自己的四问（⛔ 不 import 被测脚本，不复用它的正则） ----
# ⚠⚠⚠ 两个正则**必须都用命名组**：位置组在两者间的下标不同
#    （BAD 的 tid 是 3、GOOD 的 tid 是 1），混用位置组必然错一次。
RC_RE = re.compile(rb"\brc=(-?\d+)")
BAD_BEGIN_RE = re.compile(
    rb"^###\s+BEGIN\s+\[(?P<i>\d+)/(?P<n>\d+)\]\s+"
    rb"(?P<tid>\S+)(?P<rest>.*?)\s\s+(?P<time>\d\d:\d\d:\d\d)\s*$")
GOOD_BEGIN_RE = re.compile(
    rb"^###\s+BEGIN\s+(?P<tid>\S+)(?P<rest>.*?)\s\s+"
    rb"(?P<time>\d\d:\d\d:\d\d)\s*$")


def bench_verdict(out_path, status_path, src_log_path, expect_md5):
    """台架独立判定**产物**是否合规：返回 (合规?, 违反了哪一闸, 证据)。⛔ 不看 stdout。

    ⚠⚠⚠ 第一版的台架自己写错了：它拿**产物**的 md5 去比**输入**基线
    ⇒ 规范化必然改 BEGIN 行 ⇒ 产物 md5 必然不同 ⇒ 基线恒红
    （首跑就报「基线就不绿 ⇒ 台架本身有问题」，正是它自己抓到了自己）。
    ⚖ 闸 0 验的是**输入**；产物侧该验的是「与输入的对应关系」，即闸 1/2/3。
    ⚖⚠ 所以输入 md5 由台架**自己**算、自己比（不信被测脚本的 stdout），
    产物 md5 与谁都不比 —— 没有任何可比的基线。
    """
    # 闸 0（台架侧）：输入本身是不是我要的那份
    raw_in = open(src_log_path, "rb").read()
    if hashlib.md5(raw_in).hexdigest() != expect_md5:
        return False, "0", "输入 md5 != 台架期望（输入不是这一份）"

    raw = open(out_path, "rb").read()

    stids = []
    for line in open(status_path, "rb").read().split(b"\n"):
        s = line.strip()
        if not s or s.startswith(b"ALLDONE"):
            continue
        if RC_RE.search(s) is None:
            return False, "状态", "状态行读不出 rc"
        stids.append(s.split()[0])
    n_status = len(stids)

    lines = raw.split(b"\n")
    begins = []
    for ln in lines:
        if ln.startswith(b"### BEGIN"):
            m = GOOD_BEGIN_RE.match(ln)
            if m is None:
                return False, "契约", "BEGIN 行不符合契约且无法定位序号"
            begins.append((ln, m))

    # 闸 1：序号连续 + 分母 == 状态格数
    if not begins:
        return False, "1", "产物里一个 BEGIN 都没有"
    ns = set()
    for idx, (_ln, m) in enumerate(begins, start=1):
        rest = m.group(2)
        sm = re.search(rb"\[(\d+)/(\d+)\]", rest)
        if sm is None:
            return False, "1", "第 %d 个 BEGIN 没有 [i/n]" % idx
        if int(sm.group(1)) != idx:
            return False, "1", "序号不连续：第 %d 个印 [%s/%s]" % (
                idx, sm.group(1).decode(), sm.group(2).decode())
        ns.add(int(sm.group(2)))
    if len(ns) != 1:
        return False, "1", "分母不一致：%s" % sorted(ns)
    if ns.pop() != n_status:
        return False, "1", "分母 != 状态格数 %d" % n_status

    # 闸 2：tid 与状态逐格对齐
    for idx, (_ln, m) in enumerate(begins):
        if m.group(1) != stids[idx]:
            return False, "2", "第 %d 格 tid 对不上：%r vs %r" % (
                idx + 1, m.group(1), stids[idx])

    # 闸 3：与**输入**比 —— BEGIN 行 token 集合不变，非 BEGIN 行字节不变，行数不变
    # ⚠⚠⚠ 必须**按行序**配对，⛔ 不能按 tid 建字典：
    #    实测 137 格只有 14 个唯一 tid（每个出现 9–11 次且相邻重复）。
    #    第一版台架用 `src_begins[tid] = ln`，dict 去重把 137 塌成 14
    #    ⇒ 报「BEGIN 行数变了：源 14 出 137」—— 台架自己先红了。
    # ⚖ 格序才是「第 i 格」的真正标识，tid 不是。
    src = raw_in.split(b"\n")
    src_begins = [ln for ln in src if ln.startswith(b"### BEGIN")]
    out_begins = [ln for ln in lines if ln.startswith(b"### BEGIN")]
    if len(src_begins) != len(out_begins):
        return False, "3", "BEGIN 行数变了：源 %d 出 %d" % (
            len(src_begins), len(out_begins))
    for i, (a, b) in enumerate(zip(src_begins, out_begins), start=1):
        # ⚖⚠ 输入可能是**偏离**格式（本轮真日志）或**合规**格式（M7–M9 的夹具）
        # ⇒ 两种都要能取出 tid，不能只认一种（否则 bench 自己会假红）。
        # ⚖⚠⚠ **不能用 `BAD.match(x) or GOOD.match(x)`**：`re.Match` 没有
        #    `__bool__`，永远为真 ⇒ `or` **不会**按「是否匹配」短路，
        #    永远返回第一个结果（哪怕它是 None）⇒ 下面就会 `None.group(...)` 崩掉。
        ma = BAD_BEGIN_RE.match(a)
        if ma is None:
            ma = GOOD_BEGIN_RE.match(a)
        mb = BAD_BEGIN_RE.match(b)
        if mb is None:
            mb = GOOD_BEGIN_RE.match(b)
        if ma is None or mb is None:
            return False, "3", "第 %d 个 BEGIN 行有一侧两种格式都不匹配" % i
        if ma.group("tid") != mb.group("tid"):
            return False, "3", "第 %d 格 tid 变了：%r -> %r" % (
                i, ma.group("tid"), mb.group("tid"))
        if sorted(a.split()) != sorted(b.split()):
            return False, "3", "第 %d 行 token 集合变了（不只是重排）" % i
    src_pass = [l for l in src if not l.startswith(b"### BEGIN")]
    out_pass = [l for l in lines if not l.startswith(b"### BEGIN")]
    if src_pass != out_pass:
        i = next(k for k, (a, b) in enumerate(zip(src_pass, out_pass)) if a != b)
        return False, "3", "非 BEGIN 行字节被改动：第 %d 条\n    源 %r\n    出 %r" % (
            i + 1, src_pass[i][:100], out_pass[i][:100])
    if len(src) != len(lines):
        return False, "3", "总行数变了：%d -> %d" % (len(src), len(lines))

    return True, "-", "四问全过"


# ---- 变异定义 ----
def mut_seq_skip(text):
    """M1：第 5 个 BEGIN 的序号 5 -> 6。期望闸 1。"""
    parts = text.split("### BEGIN [5/137]")
    assert len(parts) == 2
    return parts[0] + "### BEGIN [6/137]" + parts[1]


def mut_tid_swap(text):
    """M2：第 5 个 BEGIN 的 tid 换成一个**不在状态文件里**的 tid。期望闸 2。

    ⚖⚠ 不用「第 6 格的 tid」：那会让输入里出现两个相同 tid（`src_begins` 按 tid
    建键会去重，少一格），把「tid 错位」混成「BEGIN 行数变了」。用一个
    全新 tid 才只破坏闸 2 这一条性质。
    """
    old = "### BEGIN [5/137] aime__aime25__p00__think "
    new = "### BEGIN [5/137] aime__aime25__p99__think "
    assert text.count(old) == 1, "M2 锚点没命中"
    return text.replace(old, new)


def mut_denom(text):
    """M3：全部分母 137 -> 138。期望闸 1（分母 != 状态格数）。"""
    return text.replace("/137]", "/138]")


def mut_drop_rest(td):
    """M4：偏离格式分支里丢掉 rest 段。期望闸 3（token 集合变了）。

    ⚠⚠ 锚点必须跟着被测代码的**形状**走：这条变异在 244.1.2b 修幂等时
    失效过一次（那段构造式被重写）。⚗ 锚点失配要当**台架的失效**查，不是当变异不适用。
    """
    old = ('new = "%s %s [%d/%d]%s  %s" % (BEGIN_PREFIX, tid, i_val,\n'
           '                                                   n_val, rest, time)')
    new = 'new = "%s %s [%d/%d]  %s" % (BEGIN_PREFIX, tid, i_val, n_val, time)'
    assert td.count(old) == 1, "M4 锚点没命中"
    return td.replace(old, new)


def mut_touch_passthrough(td):
    """M5：转换时给非 BEGIN 行加个字符。期望闸 3（字节被改动）。"""
    old = "            else:\n                out_lines.append(line)"
    new = "            else:\n                out_lines.append(line + \"X\")"
    assert td.count(old) == 1, "M5 锚点没命中"
    return td.replace(old, new)


def mut_text_mode_read(td):
    """M6：输入读法从 rb 退化回文本模式 ⇒ 通用换行转换吃掉 274 个 \\r。
    期望闸 3（字节级行数变了）。⚖ 这就是本轮第一版的真实缺陷。"""
    old = 'log_text = raw_bytes.decode("utf-8")'
    new = 'log_text = open(args.log, encoding="utf-8").read()'
    assert td.count(old) == 1, "M6 锚点没命中"
    return td.replace(old, new)


def mut_gut_gate3(td):
    """M7：把闸 3 整段自查删掉（转换逻辑不变）。
    ⚖ 预期：脚本**不该**红（它没破坏被测行为），但 M4/M5 型缺陷将失去兜底
    ⇒ 用「闸 3 删除版 + M5」这个组合变异证明台架独立性（G8）。"""
    start = td.index("        if src_pass != out_pass:")
    end = td.index("        got_passthrough = [ln for ln in out_lines")
    return td[:start] + td[end:]


def mut_compliant_seq_skip(text):
    """M7：合规格式日志里第 5 格序号错。期望闸 1（**合规路径也要红**）。"""
    old = "### BEGIN aime__aime25__p00__think [5/137] "
    new = "### BEGIN aime__aime25__p00__think [6/137] "
    assert text.count(old) == 1, "M7 锚点没命中"
    return text.replace(old, new)


def mut_compliant_tid(text):
    """M8：合规格式日志里第 5 格 tid 换掉。期望闸 2。"""
    old = "### BEGIN aime__aime25__p00__think [5/137] "
    new = "### BEGIN aime__aime25__p99__think [5/137] "
    assert text.count(old) == 1, "M8 锚点没命中"
    return text.replace(old, new)


def mut_mixed_format(text):
    """M9：把第 5 行改成**偏离**格式，与其余合规行混合。期望 HardFail（混合格式）。"""
    old = "### BEGIN aime__aime25__p00__think [5/137] "
    new = "### BEGIN [5/137] aime__aime25__p00__think "
    assert text.count(old) == 1, "M9 锚点没命中"
    return text.replace(old, new)


MUTS = [
    ("M1 序号跳号", "输入", mut_seq_skip, "1", "序号不连续"),
    ("M2 tid 错位一格", "输入", mut_tid_swap, "2", "tid 对不上"),
    ("M3 分母 137→138", "输入", mut_denom, "1", "分母"),
    ("M4 转换丢 rest 段", "实现", mut_drop_rest, "3", "token 集合变了"),
    ("M5 转换改非 BEGIN 行", "实现", mut_touch_passthrough, "3", "字节"),
    ("M6 输入读法退化文本模式", "实现", mut_text_mode_read, "3", "字节"),
    ("M7 合规格式序号错", "合规", mut_compliant_seq_skip, "1", "序号不连续"),
    ("M8 合规格式 tid 换掉", "合规", mut_compliant_tid, "2", "tid 对不上"),
    ("M9 混合格式", "合规", mut_mixed_format, "混", "混合格式"),
]

# ---- G 系列：台架独立性（⛔ 不能只测被测脚本，要测「台架 vs 脚本」） ----
# G8 = 「闸 3 被删」+ 「转换改非 BEGIN 行」⇒ 脚本必须**不**红，bench 必须抓。
#     若两者都抓不住 ⇒ 台架无效。
# G9 = 「闸 3 被删」+ 正常转换 ⇒ 脚本绿且 bench 绿 ⇒ 这是**合格**的绿（没破坏行为），
#     用来确认 G8 的红不是因为「删了闸 3 就该红」。


def run_case(work, name, target_src, log_src, status_src, expect_md5):
    out = os.path.join(work, "out_%s.log" % re.sub(r"\W+", "_", name))
    if os.path.exists(out):
        os.remove(out)
    p = subprocess.run(
        [PY, target_src, "--log", log_src, "--status", status_src,
         "--out", out, "--expect-md5", expect_md5],
        capture_output=True, text=True)
    stdout = p.stdout + p.stderr
    produced = os.path.exists(out)

    # ⚖⚠⚠ 「红」必须区分**闸不过**与**崩了**：
    #   rc=2 = 某道闸 HardFail（本台架要的）；rc=1/3 = argparse/IO 崩了（不要的）。
    # ⚖ 崩了也常常「没产出文件」，若把「没产出」一律当合规 ⇒ 崩掉的变异会被
    #   bench 判成「没问题」⇒ 台架自己假绿。⛔ 所以 rc!=2 的一律不算 script 抓。
    red_by_gate = (p.returncode == 2)
    crashed = p.returncode not in (0, 2)

    if not produced:
        # 承诺是「闸不过 ⇒ 不产出」。只有 rc=2 时这才是合规兑现；
        # rc=0 却没产出，或崩了没产出，都是不合规。
        if p.returncode == 2:
            ok, which, why = True, "-", "闸不过 ⇒ 确实没产出（承诺兑现）"
        elif p.returncode == 0:
            ok, which, why = False, "-", "rc=0 却没产出文件"
        else:
            ok, which, why = False, "崩", "rc=%d 崩了且没产出" % p.returncode
    else:
        ok, which, why = bench_verdict(out, status_src, log_src, expect_md5)

    return {"rc": p.returncode, "red": red_by_gate, "crashed": crashed,
            "stdout": stdout, "produced": produced, "bench_ok": ok,
            "bench_which": which, "bench_why": why, "out": out}


def main():
    if not os.path.exists(REAL_LOG) or not os.path.exists(REAL_STATUS):
        print("⛔ 缺真实输入：%s / %s" % (REAL_LOG, REAL_STATUS))
        return 1
    td0 = open(TARGET, encoding="utf-8").read()
    log0 = open(REAL_LOG, encoding="utf-8").read()

    work = tempfile.mkdtemp(dir=HERE, prefix="mut_")
    n_caught = n_total = 0
    rows = []
    try:
        # ---- 基线绿：不变异必须通过 ----
        base = run_case(work, "baseline", TARGET, REAL_LOG, REAL_STATUS,
                        BASELINE_MD5)
        n_total += 1
        if base["red"] or not base["bench_ok"] or not base["produced"]:
            print("⛔ 基线就不绿 ⇒ 台架本身有问题，先修台架：rc=%s bench=%s %s"
                  % (base["rc"], base["bench_ok"], base["bench_why"]))
            return 1
        n_caught += 1
        rows.append(("BASELINE", "绿（预期）", "script 绿 + bench 绿", "—"))

        # ---- M1..M6 ----
        for name, kind, fn, want_gate, want_why in MUTS:
            n_total += 1
            tdir = tempfile.mkdtemp(dir=work, prefix="m_")
            src_t = os.path.join(tdir, "t.py")
            log_t = os.path.join(tdir, "in.log")
            if kind == "输入":
                shutil.copy(TARGET, src_t)
                open(log_t, "w", encoding="utf-8").write(fn(log0))
            elif kind == "合规":
                # ⚖ 用**已规范化**的真日志当输入 ⇒ 走 compliant 分支。
                # ⚠ 若误用偏离格式的 log0，M7/M8 的锚点根本不存在 ⇒ 台架自己会报错。
                shutil.copy(TARGET, src_t)
                open(log_t, "w", encoding="utf-8").write(fn(COMPLIANT_TEXT))
            else:
                open(src_t, "w", encoding="utf-8").write(fn(td0))
                shutil.copy(REAL_LOG, log_t)
            md5 = hashlib.md5(open(log_t, "rb").read()).hexdigest()
            r = run_case(work, name, src_t, log_t, REAL_STATUS, md5)
            caught_by = []
            if r["red"]:
                caught_by.append("script")
            if not r["bench_ok"]:
                caught_by.append("bench")
            if not caught_by:
                rows.append((name, "❌ 没抓住", "—", r["bench_why"]))
                continue
            right = r["red"] and (want_why in r["stdout"]) and (want_gate in r["stdout"])
            rows.append((name, "✅ %s" % "/".join(caught_by),
                         "期望闸 %s，%s" % (want_gate,
                                           "原因串命中" if want_why in r["stdout"]
                                           else "原因串没命中"),
                         r["bench_why"].split("\n")[0][:70]))
            if caught_by:
                n_caught += 1
            if not right and r["red"]:
                print("⚠ %s 红了但红在别处（期望闸 %s / 原因 %r）"
                      % (name, want_gate, want_why))

        # ---- G8：台架独立性（闸 3 被删 + 转换改非 BEGIN 行）----
        n_total += 1
        tdir = tempfile.mkdtemp(dir=work, prefix="g8_")
        src_t = os.path.join(tdir, "t.py")
        open(src_t, "w", encoding="utf-8").write(
            mut_touch_passthrough(mut_gut_gate3(td0)))
        r = run_case(work, "G8", src_t, REAL_LOG, REAL_STATUS, BASELINE_MD5)
        if (not r["red"]) and (not r["bench_ok"]):
            n_caught += 1
            rows.append(("G8 台架独立性", "✅ bench", "script 绿 + bench 抓", r["bench_why"].split("\n")[0][:70]))
        else:
            rows.append(("G8 台架独立性",
                         "❌ script红" if r["red"] else "❌ 都没抓",
                         "期望 script 绿 + bench 红", r["bench_why"].split("\n")[0][:70]))

        # ---- G9：闸 3 被删但行为没坏 ⇒ 应当两绿（确认 G8 的红不是因为「删闸 3」）----
        n_total += 1
        tdir = tempfile.mkdtemp(dir=work, prefix="g9_")
        src_t = os.path.join(tdir, "t.py")
        open(src_t, "w", encoding="utf-8").write(mut_gut_gate3(td0))
        r = run_case(work, "G9", src_t, REAL_LOG, REAL_STATUS, BASELINE_MD5)
        if r["produced"] and r["bench_ok"]:
            n_caught += 1
            rows.append(("G9 闸3删除但行为正确", "✅ 两绿（预期）", "不该红", "—"))
        else:
            rows.append(("G9 闸3删除但行为正确", "❌", "期望两绿", r["bench_why"][:70]))

        print("=" * 78)
        for a, b, c, d in rows:
            print("%-24s %-16s %-34s %s" % (a, b, c, d))
        print("=" * 78)
        print("变异 %d 个，抓住 %d 个" % (n_total, n_caught))
        return 0 if n_caught == n_total else 1
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
