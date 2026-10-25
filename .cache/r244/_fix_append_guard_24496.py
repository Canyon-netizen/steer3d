#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_fix_append_guard_24496.py —— 修 **落账脚本的「防重复落账」闸**（244.92–244.96 五轮同病）。

⚖⚖⚖ **这是本轮抓到的真缺陷**（与「244.96 的判决」无关，是**顺手修的连带缺陷**）：

  · 症状：对**已经落过账**的账本再跑一次落账脚本 ⇒ ⇒ 它**又追加了一份**该轮段落
    （实测：244.96 段被追加了**第二份**，+95 行、md5 从 `912f7d6f…` 变成 `6196ce59…`）。
  · 根因：那五份脚本的幂等闸写的是 `old.startswith(MARK)`
    ⇒ ⇒ `MARK` 是**段标题**（「## 修订 244.96 ——」）⇒ ⇒ 整本账本的**第一行**永远不是它
    ⇒ ⇒ **这个闸从来没有触发过**（死闸）。
  · ⚖⚖⚖ **这是「退化」，不是「从来没有」**：账本 `:41731` 明写
    「**落账脚本的「防重复落账」闸**原来只做「拒绝」⇒ ⇒ 提交链**不可重跑**⇒ ⇒ 改成
     「**已落 ⇒ 必须与收据算出来的那段逐字节相同**，相同则不重写，不同则停下」⇒ ⇒ 幂等且**自证**」
    ⇒ ⇒ **244.86–244.91 时代已经修过一次**（`_append_24486.py` 等仍是那套写法）
    ⇒ ⇒ **244.92–244.96 这五轮把它退化掉了**。
  · ⇒ ⇒ 本脚本把五份脚本**恢复成 244.86 起的成规**，并补上成规里没有的一处：
      ① 段标题出现 **> 1 次** ⇒ ⇒ 停下；
      ② 段标题出现 **== 1 次** ⇒ ⇒ **绝不写**，只报告「账本里已有的那段」与
         「收据算出来的那段」的关系：
         · **逐字节相同** ⇒ ⇒ 「幂等命中 ⇒ ⇒ 不重写」（退出 0）；
         · **只有『落账前 md5（行数）』这一个 token 不同** ⇒ ⇒ 那是**重跑必然**的差异
           ⇒ ⇒ 仍然「不重写」（退出 0），并把这条差异**明说**；
         · **其它地方也不同** ⇒ ⇒ **停下**（⛔ 不许覆盖、⛔ 不许改数凑好看）
           ⇒ ⇒ 且**打印前 3 处差异**（⛔ 不许悄悄失败）。
      ③ 另：成规里比的是「从段标题到**文件末尾**」，这对**非最后一段**的历史轮次不成立
         （后面还跟着 244.93–244.96 的段）⇒ ⇒ 这里改成「从段标题到**下一段标题**」。

⚖ **不改变落账产物**：改的只是「已落过」这条分支 ⇒ ⇒ 从**落账前**的账本跑一遍，
  产出的字节**必须与当年入库那份逐字节相同**（由 `_verify_append_guard_24496.py` 逐轮实测）。

⚖ ⚠ **模板里的轮次号用 `{RD}` 占位**（补丁期替换）⇒ ⇒ ⛔ **不许**用 `%` 格式化整块模板
  （那会把脚本**运行期**的 `%` 运算符一起吃掉 ⇒ ⇒ 生成出 `NameError`）。
"""

import io
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DEV = os.path.join(REPO, ".cache", "r244")
ROUNDS = ["244.92", "244.93", "244.94", "244.95", "244.96"]

CANON = '''    # ---- 硬闸 2：**幂等**（已落 ⇒ **绝不重复写**；并逐条报告「已有段 vs 收据算出来的那段」）----
    # ⚖⚖⚖ **本轮修的真缺陷（244.92–244.96 五轮同病）**：原来写的是 `old.startswith(MARK)`
    #    ⇒ ⇒ MARK 是**段标题**（「## 修订 {RD} ——」）⇒ ⇒ 整本账本的**第一行**永远不是它
    #    ⇒ ⇒ **这个闸从来没有触发过**（死闸）⇒ ⇒ 拿已落过账的账本再跑一次
    #    ⇒ ⇒ 会**再追加一份** {RD} 段（实测 244.96 段被追加了第二份，+95 行）。
    #    ⇒ ⇒ 恢复 **244.86 起的成规**（账本 `:41731` 记着「改成『已落 ⇒ 必须与收据算出来的
    #    那段逐字节相同』⇒ ⇒ 幂等且**自证**」）⇒ ⇒ 这五轮把它**退化**掉了。
    n_have = len(re.findall(r"^" + re.escape(MARK), old, re.M))
    if n_have > 1:
        raise SystemExit("⛔ 账本里有 %d 处「%s」⇒ ⇒ 停下" % (n_have, MARK))
    if n_have == 1:
        # ⚖ 成规里比的是「段标题 → **文件末尾**」⇒ ⇒ 对**非最后一段**的历史轮次不成立
        #    （后面还跟着别的段）⇒ ⇒ 这里改成「段标题 → **下一段标题**」。
        _i = old.index(MARK)
        _m = re.search(r"^## 修订 ", old[_i + len(MARK):], re.M)
        _j = (_i + len(MARK) + _m.start()) if _m else len(old)
        _have = old[_i:_j].rstrip("\\n")
        _want = entry.rstrip("\\n")
        # ⚖ 段里唯一**账本派生**的 token 是「落账前 md5（行数）」⇒ ⇒ 重跑时它必然变
        _pre = r"落账前\\*\\* md5 `[0-9a-f]{32}`（\\d+ 行）"
        _h2 = re.sub(_pre, "落账前** md5 `<MD5>`（<N> 行）", _have)
        _w2 = re.sub(_pre, "落账前** md5 `<MD5>`（<N> 行）", _want)
        _n_pre = len(re.findall(_pre, _have))
        if _have == _want:
            print("✅ 幂等：账本里已有的 {RD} 段与**收据算出来的那段逐字节相同**"
                  " ⇒ ⇒ **不重复写**（本次落账无需再动）")
        elif _h2 == _w2 and _n_pre > 0:
            print("✅ 幂等：账本里已有的 {RD} 段与**收据算出来的那段**"
                  "（**除『落账前 md5（行数）』这 %d 处 token 外**）**逐字节相同**"
                  " ⇒ ⇒ **不重复写**（本次落账无需再动）" % _n_pre)
            print("   （那一个 token 指向『本次落账前那版账本』⇒ ⇒ **重跑时必然变**"
                  " ⇒ ⇒ ⛔ 不许据此改数）")
        else:
            _dl = [(x, y) for x, y in zip(_h2.split("\\n"), _w2.split("\\n")) if x != y][:3]
            raise SystemExit("⛔ 账本里已有 {RD} 段，但它与收据算出来的**不一致**"
                             "（**不止『落账前 md5』那一处**）⇒ ⇒ 停下"
                             "（⛔ 不许覆盖、⛔ 不许改数凑好看）\\n   前 3 处差异：%r" % (_dl,))
        print("LEDGER_LINES=%d" % len(old.split("\\n")))
        print("LEDGER_BYTES=%d" % len(old_b))
        print("LEDGER_MD5=%s" % old_md5)
        print("APPEND_RC=0")
        return 0
'''


def canon(rd):
    return CANON.replace("{RD}", rd)


def main():
    changed = []
    for rd in ROUNDS:
        p = os.path.join(DEV, "_append_%s.py" % rd.replace(".", ""))
        if not os.path.isfile(p):
            print("⛔ 找不到 %s" % p)
            return 2
        src = io.open(p, encoding="utf-8").read()
        # ⚖ 幂等可重跑：**按「硬闸 2 那一块」定位**（不论它是死闸形态还是已修形态）
        pat = re.compile(
            r"    # ---- 硬闸 2：\*\*幂等\*\*.*?\n"
            r"        return 0\n",
            re.S)
        ms = list(pat.finditer(src))
        if len(ms) != 1:
            print("⛔ %s：找到 %d 处「硬闸 2」块（期望恰好 1 处）⇒ ⇒ 中止" % (rd, len(ms)))
            return 3
        m = ms[0]
        new = src[:m.start()] + canon(rd) + src[m.end():]
        try:
            compile(new, p, "exec")
        except SyntaxError as e:
            print("⛔ %s：打完补丁编不过（%s）⇒ ⇒ 中止" % (rd, e))
            return 3
        # ⚖⚖⚖ 补丁自身也要**自检**：生成块里不许残留补丁期占位符，也不许出现未定义名
        blk = canon(rd)
        if "{RD}" in blk or "% rd" in blk or "% rd)" in blk:
            print("⛔ %s：生成块里还有占位符/错引用 ⇒ ⇒ 中止" % rd)
            return 3
        io.open(p, "w", encoding="utf-8", newline="").write(new)
        changed.append(rd)
        print("✅ %s：死闸 ⇒ ⇒ 恢复 244.86 成规（逐字节比对 ＋ 绝不重写）" % rd)
    print("FIX_RC=0 （改了 %d 份：%s）" % (len(changed), ", ".join(changed) or "无"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
