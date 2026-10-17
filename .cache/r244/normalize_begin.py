#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 `### BEGIN [i/n] tid …` 规范成既有契约 `### BEGIN tid [i/n] …`。

⚠⚠ 为什么需要它（修订 244.1）
--------------------------
`r244_warm_sweep.sh:55` 把 `[i/n]` 印在 BEGIN 与 tid **之间**：

    ### BEGIN [1/137] aime__aime25__p00__think --inject-scope k  11:13:01

而 `r227_kcurve.py` 的 `BEGIN_RE` 契约是 **`tid` 必须是 BEGIN 后第一个 token**：

    ^###\s+BEGIN\s+(?P<tid>\S+)(?P<rest>.*?)\s\s+(?P<time>\d\d:\d\d:\d\d)\s*$

⇒ 读数器把 `[1/137]` 当成 tid，立刻 HardFail：
  「第 1 格 tid 对不上：日志 '[1/137]' vs 状态 'aime__aime25__p00__think'
   （错位一格会把上一格的 k 读成这一格的）」

⚖ 为什么不改读数器
------------------
读数器那条防错位守卫**是对的**，偏离方是生产者。改生产者意味着重跑 137 格
（本轮实测 11:13:01 → 13:18:00，约 2 小时），而规范化只需重排一行里的两个 token。
⚗ 且**不在本轮改** `r244_warm_sweep.sh`：产物是它产的，改了会让「脚本说的」与
「产物是的」不一致 —— 那正是「回读校验通过 ≠ 跑的是它」的同族。脚本偏离契约
这一事实单独入账本（修订 244.1），不在此处假装已经修好。

⚖⚠⚠ 为什么必须有闸
--------------------
规范化之后，**读数器读的不是原始产物，而是我的转换结果**。
若转换本身错了，读数器看不出来（它只负责校验转换后的文件是否自洽）。
⇒ 转换必须自证：

  闸 0 基线闸：原始日志 md5 == --expect-md5 传入的值（⚠ 给了才算数）
  闸 1 序号闸：`[i/n]` 严格 1..N 连续递增，且 N 一致，且 N == 状态文件格数
  闸 2 tid 闸 ：规范化后的 tid 与状态文件第 i 行 tid 逐格相等
  闸 3 纯重排：每行 BEGIN 的 token **集合**与原行完全相同（只许位置变），
               且非 BEGIN 行**逐字节不变**，且总行数不变

⚖⚠⚠ 闸 3 的边界（第一版把它叫「字节闸」，是误导，已改）
    闸 3 只证明**转换本身是纯重排**，⛔ 它**不**证明「输入日志没被人换过」——
    那是任何转换脚本都证明不了的事（自比自），只能靠外部基线，即闸 0。
    ⚗ 第一版的输出写着「非 BEGIN 行逐字节不变」，读起来像在验证输入完整性，
    ⚠ 实则只在比「输出 vs 输入」。这个措辞差一度就会让人把恒绿读成完整性验证。

⚖ 顺序不能反：闸 0 不过 ⇒ 后面三闸在别的文件上跑，结论无效；
闸 1 不通过 ⇒ tids 整体错位，闸 2 就没有意义。
⛔ 任何一闸不过 ⇒ 退出码 2，**不产出规范化文件**（不给半成品）。

用法：
    python3 normalize_begin.py --log IN --status IN --out OUT
退出码：0 = 三闸全过且已写出；2 = 某闸不过；3 = 文件读不了
"""

import argparse
import hashlib
import os
import re
import sys

# 本脚本专用的「偏离格式」：BEGIN 后紧跟 [i/n]，再跟 tid
BAD_BEGIN_RE = re.compile(
    r"^###\s+BEGIN\s+\[(?P<i>\d+)/(?P<n>\d+)\]\s+"
    r"(?P<tid>\S+)(?P<rest>.*?)\s\s+(?P<time>\d\d:\d\d:\d\d)\s*$")

RC_RE = re.compile(r"\brc=(-?\d+)")
BEGIN_PREFIX = "### BEGIN"
END_PREFIX = "### END"


class HardFail(Exception):
    """某闸不过。⛔ 一律硬失败，不降级。"""


def parse_status_tids(text):
    """状态文件 → (tids, n_rows)。`ALLDONE` 行不算一格。

    ⚖ 独立于 `r227_kcurve.parse_status` 重写一遍：这里要的是**第二意见**，
    两个解析器各自独立地读 tid，才能互为交叉验证（一个解析 bug 不该出两次）。
    """
    tids = []
    for line in text.split("\n"):
        s = line.strip()
        if not s or s.startswith("ALLDONE"):
            continue
        if RC_RE.search(s) is None:
            raise HardFail("状态行读不出 rc：%r" % s)
        tids.append(s.split()[0])
    return tids, len(tids)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="把偏离契约的 BEGIN 行规范化，附三道闸")
    ap.add_argument("--log", required=True, help="原始日志（偏离格式）")
    ap.add_argument("--status", required=True, help="状态文件（每格一行 + ALLDONE）")
    ap.add_argument("--out", required=True, help="规范化后的日志输出路径")
    ap.add_argument("--expect-md5", default=None,
                    help="闸 0：原始日志的期望 md5。⚠ 不给就不做基线校验，"
                         "且输出会明说「未验证输入完整性」")
    args = ap.parse_args(argv)

    # ================= 闸 0：基线闸 =================
    # ⚖ 必须最先跑：不在同一份字节上跑，后面三闸的结论无效。
    # ⚖⚠ 这一闸是**外部基线**（账本/远端另算的 md5），不是自比自 ——
    #    闸 3 的「输出 vs 输入」证明不了输入没被换过，闸 0 才能。
    try:
        raw_bytes = open(args.log, "rb").read()
    except OSError as e:
        print("⛔ 读不了日志：%s" % e)
        return 3
    got_md5 = hashlib.md5(raw_bytes).hexdigest()
    if args.expect_md5 is None:
        print("⚠ 闸 0 未做：没给 --expect-md5 ⇒ 本脚本**不**声称验证了输入完整性")
        print("   （日志 md5 = %s，记账时请以此为准）" % got_md5)
    else:
        if got_md5 != args.expect_md5.strip().lower():
            print("⛔ 闸 0（基线）不过：日志 md5 %s != 期望 %s ⇒ "
                  "拒绝在别的字节上转换" % (got_md5, args.expect_md5))
            return 2
        print("✅ 闸 0：日志 md5 = %s，与基线一致" % got_md5)

    try:
        log_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as e:
        print("⛔ 日志不是 utf-8：%s" % e)
        return 3
    try:
        status_text = open(args.status, encoding="utf-8").read()
    except OSError as e:
        print("⛔ 读不了状态文件：%s" % e)
        return 3

    try:
        status_tids, n_status = parse_status_tids(status_text)
    except HardFail as e:
        print("⛔ 状态文件本身不合法：%s" % e)
        return 3

    # ---- 扫一遍，分出 BEGIN / 非 BEGIN ----
    bad = []          # (行号, 解析出的结构)
    passthrough = []  # 非 BEGIN 行原文
    n_begins = 0
    n_unmatched_begin = 0
    for lineno, line in enumerate(log_text.split("\n")):
        if line.startswith(BEGIN_PREFIX):
            m = BAD_BEGIN_RE.match(line)
            if m is None:
                n_unmatched_begin += 1
                bad.append((lineno, None))
                continue
            n_begins += 1
            bad.append((lineno, m.groupdict()))
        else:
            passthrough.append((lineno, line))

    # ================= 闸 1：序号闸 =================
    try:
        if n_unmatched_begin:
            raise HardFail("有 %d 行以 `### BEGIN` 开头但不符合偏离格式，"
                           "无法证明只动了 token 顺序" % n_unmatched_begin)
        if n_begins == 0:
            raise HardFail("一个 BEGIN 行都没有 —— 日志读不出分块，拒绝转换")
        ns = set()
        for idx, (_lineno, g) in enumerate(bad, start=1):
            if g is None:
                raise HardFail("第 %d 个 BEGIN 行没解析出来" % idx)
            if int(g["i"]) != idx:
                raise HardFail("序号不连续：第 %d 个 BEGIN 印的是 [%s/%s]"
                               % (idx, g["i"], g["n"]))
            ns.add(int(g["n"]))
        if len(ns) != 1:
            raise HardFail("分母不一致：%s" % sorted(ns))
        n = ns.pop()
        if n != n_begins:
            raise HardFail("分母 %d != 实到 BEGIN 数 %d" % (n, n_begins))
        if n != n_status:
            raise HardFail("分母 %d != 状态文件格数 %d" % (n, n_status))
        if re.search(r"^###\s+END\s+\[\d+/", log_text, re.M):
            pass  # END 行也带 [i/n]，但读数器不解析 END（已 grep 确认），故不规范化
    except HardFail as e:
        print("⛔ 闸 1（序号）不过：%s" % e)
        return 2

    # ================= 闸 2：tid 闸 =================
    try:
        for idx, (_lineno, g) in enumerate(bad):
            if g["tid"] != status_tids[idx]:
                raise HardFail("第 %d 格 tid 对不上：日志 %r vs 状态 %r"
                               % (idx + 1, g["tid"], status_tids[idx]))
    except HardFail as e:
        print("⛔ 闸 2（tid 对齐）不过：%s" % e)
        return 2

    # ================= 闸 3：纯重排（构造后自查，字节级） =================
    # ⚠⚠⚠ 第一版的闸 3 是**假绿**：它读输入用 `open(..., encoding="utf-8")` 文本模式，
    #    Python 的通用换行转换把日志里的 274 个 `\r`（每格 2 个 tqdm 行）变成 `\n`，
    #    ⛔ 于是写出的文件字节**已经变了**，而闸 3 比的是「输出 vs 已被转换的内存文本」
    #    ⇒ 印出「逐字节不变」而实际改了字节。实测两版输出行数 1373 vs 1099 就是这个。
    # ⚖ 本版读输入用 `rb`，`\r` 原样保留；闸 3 另加**独立字节复核**：
    #    从**文件字节**重新切一遍，与输出字节的非 BEGIN 行逐条相等。
    # ⚗ 该复核能抓住「读法退化」这类变异（M6 证明）。
    out_lines = []
    pi = 0
    n_reordered = 0
    try:
        for lineno, line in enumerate(log_text.split("\n")):
            if line.startswith(BEGIN_PREFIX):
                g = bad[n_reordered][1]
                new = "%s %s [%s/%s]%s  %s" % (
                    BEGIN_PREFIX, g["tid"], g["i"], g["n"], g["rest"], g["time"])
                # 自查：除 `[i/n]` 的位置外，两行的 token 集合必须完全相同
                old_toks = line.split()
                new_toks = new.split()
                if sorted(old_toks) != sorted(new_toks):
                    raise HardFail("第 %d 行 token 集合变了（不只是重排）：\n  旧 %s\n  新 %s"
                                   % (lineno + 1, old_toks, new_toks))
                out_lines.append(new)
                n_reordered += 1
            else:
                out_lines.append(line)
        if n_reordered != n_begins:
            raise HardFail("重排行数 %d != BEGIN 数 %d" % (n_reordered, n_begins))
        if len(out_lines) != len(log_text.split("\n")):
            raise HardFail("行数变了：%d -> %d"
                           % (len(log_text.split("\n")), len(out_lines)))
        out_bytes = "\n".join(out_lines).encode("utf-8")

        # ---- 字节级独立复核（重新从文件字节切，不复用上面的内存文本）----
        src_lines_b = raw_bytes.split(b"\n")
        out_lines_b = out_bytes.split(b"\n")
        if len(src_lines_b) != len(out_lines_b):
            raise HardFail("字节级行数变了：%d -> %d"
                           % (len(src_lines_b), len(out_lines_b)))
        src_pass = [l for l in src_lines_b if not l.startswith(b"### BEGIN")]
        out_pass = [l for l in out_lines_b if not l.startswith(b"### BEGIN")]
        if src_pass != out_pass:
            bad_i = next(i for i, (a, b) in enumerate(zip(src_pass, out_pass)) if a != b)
            raise HardFail("非 BEGIN 行字节被改动：第 %d 条\n  源 %r\n  出 %r"
                           % (bad_i + 1, src_pass[bad_i][:120], out_pass[bad_i][:120]))
        got_passthrough = [ln for ln in out_lines if not ln.startswith(BEGIN_PREFIX)]
    except HardFail as e:
        print("⛔ 闸 3（纯重排）不过：%s" % e)
        return 2

    # ⚠⚠⚠ 必须用二进制写：文本模式写会再做一次通用换行转换（Windows 上 `\n`→`\r\n`），
    #    那样「字节不变」就不成立了。
    # ⚖⚠⚠ 「某闸不过 ⇒ 不产出文件」的承诺只能在**写之前**兑现；但「磁盘上的文件 == 内存构造」
    #    这一层又只能在写之后验。⇒ 先写同目录临时文件、回读校验，再 `os.replace` 原子改名。
    #    这样任何一步失败，目标路径都**根本不存在**，不留半成品。
    tmp_path = args.out + ".tmp"
    try:
        with open(tmp_path, "wb") as f:
            f.write(out_bytes)
        written = open(tmp_path, "rb").read()
        if written != out_bytes:
            os.remove(tmp_path)
            print("⛔ 写出去的不等于构造的：磁盘 %d 字节 vs 内存 %d 字节"
                  % (len(written), len(out_bytes)))
            return 2
        os.replace(tmp_path, args.out)
    except OSError as e:
        print("⛔ 写不了输出：%s" % e)
        return 3

    # ---- 证据 ----
    print("✅ 闸 1/2/3 全过，已写出 %s" % args.out)
    print("   闸 1 序号：[1/%d] 连续递增；分母 %d == 状态格数 %d" % (n, n, n_status))
    print("   闸 2 tid ：%d/%d 格与状态文件逐格相等" % (n_begins, n_begins))
    print("   闸 3 纯重排：%d 行 BEGIN 每行 token 集合不变（只换位置）；"
          "非 BEGIN 行 %d 行逐字节不变；总行数 %d 不变"
          % (n_reordered, len(got_passthrough), len(out_lines)))
    print("   ⚖ 闸 3 只证明「转换是纯重排」；输入完整性由闸 0 负责"
          "（%s）" % ("已给基线并一致" if args.expect_md5 is not None
                     else "⚠ 本次未给基线，未验证"))
    print("   ⚖⚠⚠ 闸 2 只按**块序**对齐 tid。本数据 137 格只有 14 个唯一 tid"
          "（每格 9–11 次、相邻重复）")
    print("       ⇒ tid **不是**格的唯一键，本闸**不覆盖 k**。"
          "k 的权威在读数器：k 取自块内读数自报的 `inject_n_sites`，"
          "并与状态文件交叉校验（`r227_kcurve.py` `join()`）。")
    print("   END 行未动（读数器不解析 END，已 grep 确认）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
