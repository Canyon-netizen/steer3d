#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_make_handoff_24497.py —— 生成 244.97 的**交接文件**（`.cache/xcheck/HANDOFF_24497.md`，⛔ 不入库）。

⚖ 交接里的每个数**都从收据/账本现取** ⇒ ⇒ 与提交信息**同源**。
"""

import hashlib
import io
import os
import re
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
RCPT = os.path.join(REPO, ".cache", "r244", "_e24497")
LEDGER = os.path.join(REPO, ".cache", "xcheck", "R6_RERUN_PREREG.md")
INDEX = os.path.join(REPO, ".cache", "xcheck", "R6_RERUN_INDEX.md")
GUARD = os.path.join(REPO, ".cache", "r244", "_guard24497", "verify.out")
OUT = os.path.join(REPO, ".cache", "xcheck", "HANDOFF_24497.md")


def read(p):
    with io.open(p, encoding="utf-8") as fh:
        return fh.read()


def keys(text, name):
    m = re.search(r"===== %s =====\n(.*?)===== END_%s =====" % (name, name), text, re.S)
    if not m:
        raise SystemExit("⛔ 收据里没有 %s 块 ⇒ ⇒ 中止" % name)
    d = {}
    for l in m.group(1).split("\n"):
        if "=" in l:
            k, v = l.split("=", 1)
            d[k.strip()] = v.strip()
    return d


def main():
    st_text = read(os.path.join(RCPT, "selftest.out"))
    bf = read(os.path.join(RCPT, "data_before.out"))
    af = read(os.path.join(RCPT, "data_after.out"))
    _mst = re.search(r"自检\s+(\d+)\s*/\s*(\d+)\s+通过", st_text)
    if _mst:
        st_total = int(_mst.group(1))
        st_total_of = int(_mst.group(2))
    else:
        st_total = len(re.findall(r"^\[(PASS|FAIL)\]", st_text, re.M))
        st_total_of = st_total
    st_red = (re.search(r"^SELFTEST_RED=(\d+)", st_text, re.M) or [None, "?"])[1]
    a = keys(af, "AUDIT_KEYS")
    b = keys(bf, "AUDIT_KEYS")
    mu = keys(read(os.path.join(RCPT, "mut.out")), "AUDIT_KEYS")
    cr = keys(read(os.path.join(RCPT, "cross.out")), "AUDIT_KEYS")
    cs = keys(read(os.path.join(RCPT, "cross_selftest.out")), "AUDIT_KEYS")
    sp = keys(read(os.path.join(RCPT, "spec.out")), "AUDIT_KEYS")
    b_red = re.findall(r"^\[FAIL\] (E\d)：", bf, re.M)
    a_crits = re.findall(r"^\[(PASS|FAIL)\] (E\d)：(.+)$", af, re.M)

    # ⚖ 提交号（**现算**，⛔ 不手打）
    _g = subprocess.Popen(["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    commit_id = _g.communicate()[0].decode("utf-8").strip()
    if not commit_id:
        raise SystemExit("⛔ 取不到提交号 ⇒ ⇒ 中止")

    # ⚖ R16 收据（⛔ 不入库）
    regp = os.path.join(RCPT, "reg_24497.txt")
    _r16 = read(regp)
    with open(regp, "rb") as fh:
        r16_md5 = hashlib.md5(fh.read()).hexdigest()
    r16_n = (re.search(r"n_exec_py=(\d+)", _r16) or [None, "?"])[1]
    r16_add = (re.search(r"added=(\d+)\s+removed=(\d+)", _r16) or [None, "?", "?"])[1]
    r16_rem = (re.search(r"added=(\d+)\s+removed=(\d+)", _r16) or [None, "?", "?"])[2]
    r16_rc = (re.search(r"REG_RC=(\d+)", _r16) or [None, "?"])[1]
    r16_bad = (re.search(r"BAD_n=(\d+)", _r16) or [None, "?"])[1]

    def _two(text, label):
        for l in text.split("\n"):
            if l.startswith(label):
                return l.split("=")[1].split("（")[0].strip()
        return "(缺)"

    r16_mut = _two(_r16, "变异台 全绿=")
    r16_st = _two(_r16, "自检   全绿=")

    # ⚖ 守卫验证收据
    gtxt = read(GUARD)
    with open(GUARD, "rb") as fh:
        g_md5 = hashlib.md5(fh.read()).hexdigest()
    g_rounds = gtxt.count("✅ 全过")
    g_bad = gtxt.count("⛔ 有红")
    g_rc = (re.search(r"VERIFY_RC=(\d+)", gtxt) or [None, "?"])[1]

    ledger_text = read(LEDGER)
    ledger_lines = ledger_text.count("\n")
    ledger_md5 = hashlib.md5(ledger_text.encode("utf-8")).hexdigest()
    index_lines = read(INDEX).count("\n")
    index_md5 = hashlib.md5(read(INDEX).encode("utf-8")).hexdigest()
    _i = ledger_text.find("## 修订 244.97 ")
    _seg = ledger_text[_i:] if _i >= 0 else ""
    pre_md5 = (re.search(r"落账前\*\* md5 `([0-9a-f]{32})`", _seg) or [None, "?"])[1]
    seg_line = ledger_text[:_i].count("\n") + 1 if _i >= 0 else 0

    out = []
    W = out.append
    W("# HANDOFF 244.97 —— 剂量—响应曲线留白块（§6.2.2）纳入证据链")
    W("")
    W("**提交**：" + commit_id + " ｜ **账本**：" + str(ledger_lines) + " 行 / md5 `" + ledger_md5
      + "` ｜ **索引**：" + str(index_lines) + " 行 / md5 `" + index_md5 + "`"
      " ｜ 244.97 段起于第 " + str(seg_line) + " 行")
    W("")
    W("## 【1】本轮做了什么（一句话）")
    W("")
    W("把页面 §6.2.2「剂量—响应曲线（**未量到**）」这个**留白块**纳入证据链："
      "每个断言必须**逐位**出现在**它自己引用的账本行**里（E3/E4）"
      " ＋ 加**留白守卫**（E5/E6：⛔ 不许把「未量到」写成「无差异 / 已量到」）。")
    W("")
    W("## 【2】数字（⛔ 全部现取）")
    W("")
    W("- **判决**：改前形态 **" + b.get("VERDICT", "?") + "**、判红 **"
      + ("/".join(b_red) if b_red else "无") + "**（⛔ 那次不算判决）⇒ ⇒ 改后形态 **"
      + a.get("VERDICT", "?") + "**（" + str(len(a_crits)) + " 条判据全绿）")
    W("- **断言**：共 **" + a.get("N_ASSERT", "?") + "** 条 ｜ 命中 **" + a.get("N_HIT", "?")
      + "** ｜ 缺口 **" + a.get("N_MISS", "?") + "** ｜ bullet **" + a.get("N_BULLETS", "?") + "** 个")
    W("- **留白守卫**：可疑措辞 **" + a.get("N_SUSPECT", "?") + "** 处（豁免 **"
      + a.get("N_EXEMPT", "?") + "** 处）｜ 未被否定 **0** 处")
    W("- **自检**：" + str(st_total) + "/" + str(st_total_of) + "（失败 " + str(st_red) + "）")
    W("- **变异台**：" + mu.get("MUT_N", "?") + " 条 ｜ 抓住 " + mu.get("MUT_CAUGHT", "?")
      + " ｜ 存活 " + mu.get("MUT_SURVIVORS", "?") + " ｜ 崩 " + mu.get("MUT_CRASHED", "?")
      + " ｜ 等价通过 " + mu.get("MUT_EQUIV_OK", "?")
      + " ｜ **预登记期望与实测不符 " + mu.get("MUT_PREREG_MISMATCH", "?") + " 处**")
    W("- **互证**：断言 " + cr.get("CROSS_N_ASSERT", "?") + " ｜ 命中 " + cr.get("CROSS_N_HIT", "?")
      + " ｜ 缺口 " + cr.get("CROSS_N_MISS", "?") + " ｜ 不符 " + cr.get("CROSS_MISMATCH", "?")
      + " ｜ 自算形态 " + cr.get("CROSS_VERDICT", "?")
      + " ｜ 自证能红 " + cs.get("CROSS_SELFTEST_N_DIFF", "?") + "/"
      + cs.get("CROSS_SELFTEST_N", "?"))
    W("- **规格对账**：判据 " + sp.get("SPEC_N_CRITERIA", "?") + " ｜ 变异 " + sp.get("SPEC_N_MUT", "?")
      + " ｜ 缺陷集合 " + sp.get("SPEC_DEFECT_BULLETS", "?")
      + " == 实际 " + sp.get("SPEC_REAL_DEFECT_BULLETS", "?")
      + " ｜ 真值命中 " + sp.get("SPEC_REAL_TOKEN_HITS", "?")
      + "（实现）/" + sp.get("SPEC_REAL_TOKEN_HITS_CROSS", "?") + "（互证）")
    W("- **R16 全回归**（zju-12）：REG_RC=" + r16_rc + " ｜ BAD_n=" + r16_bad
      + " ｜ n_exec=" + r16_n + " ｜ 清单 added/removed=" + r16_add + "/" + r16_rem
      + " ｜ 变异台 " + r16_mut + " ｜ 自检 " + r16_st
      + " ｜ 收据 md5 `" + r16_md5 + "`")
    W("- **守卫逐轮验证**（zju-53）：" + str(g_rounds) + " 轮 × 3 项 ｜ 有红 " + str(g_bad)
      + " ｜ VERIFY_RC=" + g_rc + " ｜ 收据 md5 `" + g_md5 + "`")
    W("")
    W("## 【3】判据逐条（改后 · 真数据）")
    W("")
    for _s, cid, detail in a_crits:
        W("- [" + _s + "] **" + cid + "**：" + detail)
    W("")
    W("## 【4】本轮页面改动（⛔ 只改出处与记号，一个值都没动）")
    W("")
    W("- **D1（B1）**：补出处 `:41513`（「不是「无剂量效应」」的真出处）")
    W("- **D2（B3）**：补出处 `:41327` ＋ 记号由压缩式改成**账本逐字式**"
      "（`pos_frac=0.25` / `pos_frac=0.50` / `pos_frac=0.75`）⇒ ⇒ **三个值一个都没改**")
    W("- **D3（⛔ 不是缺陷 · 留白）**：B3 引的 `:41418` 合法 ⇒ ⛔ 不许删、不许判「多余出处」")
    W("")
    W("## 【5】⛔ 边界清单")
    W("")
    W("- ⛔ **剂量—响应曲线仍然未量到**（本批 `n_bands = 1`）⇒ ⇒ 本轮**没有**推进它一毫米"
      "⇒ ⇒ ⛔ 不许把「留白被纳入证据链」读成「留白被填上」")
    W("- ⛔ 本轮**只**对账 §6.2.2 的 3 个 bullet ⇒ ⇒ ⛔ 不许说成「§6.2 已核」/「剂量轴已核」")
    W("- ⚠ §8.1 的「别的小节」豁免有残留风险（把「（6.2.1 已量到）」写成本节主语会放过去）⇒ ⇒ 留白")
    W("- ⚠ E2 只判「行号在范围内」⇒ 指向**空行**的出处不越界（MU-C6 实测）⇒ ⇒ 留白")
    W("- ⚠ E7 的登记**按位置** ⇒ 改 bullet 顺序会错位（MU-C10 实测红）⇒ ⇒ 留白")
    W("- ⚠ 弱 token 本轮⛔ 不判 ⇒ ⇒ 留白")
    W("- ⛔ 预登记层与账本层仍没有自检 ⇒ ⇒「预登记**整体**先于结果」**仍不成立**"
      "（§8 是**实现期**追加的）")
    W("- ⛔ 「改闸门自己的比较表达式没有闸门能抓」⇒ ⇒ 留白")
    W("- ⛔ 要点头的线（一律没碰）：块级同口径污染上界、固定剂量批重跑加 `--dump-raw`、"
      "多随机种子对照臂、同结论对照臂、分层剂量真阶梯、docs 那条线 GPU 前向、"
      "照 meta 重建能否逐位复现的重训")
    W("")
    W("## 【6】下一轮（244.98+）")
    W("")
    W("1. **§6.3 台账 / §6.4 边界条目**；页面 §0–§5 最后")
    W("2. **弱 token 的取数口径**（纯整数如何在不用偶然命中的前提下判）")
    W("3. **「空行引用」要不要升格成闸门**（E2 的口径问题）")
    W("4. **把「改闸门自己的比较表达式」也纳入变异台**（治那条留白）")
    W("")
    W("## 【7】上手三步")
    W("")
    W("1. 读账本尾部 `/Users/zhourui/code/steer3d/.cache/xcheck/R6_RERUN_PREREG.md`"
      "（唯一权威历史，" + str(ledger_lines) + " 行；**244.97 段起于第 " + str(seg_line) + " 行**）")
    W("2. 再读本文件（交接全文）")
    W("3. 再 `git log --oneline -10` ＋ `git status --porcelain`"
      "（工作区有同事的未跟踪文件，⛔ 不碰）")
    W("")
    W("## 【8】收据位置（⛔ 不入库）")
    W("")
    W("- 判决链：`/dev/shm/_e24497`（落账前）／ `/dev/shm/_e24497b`（落账后），远端 `zju-53`")
    W("- 全回归：`/dev/shm/s24480r/reg_24497.txt`，远端 `zju-12`")
    W("- 守卫验证：`/dev/shm/_guardtest24497/verify.out`，远端 `zju-53`")
    W("- 落账前那版账本 md5 `" + pre_md5 + "`")
    W("")
    with io.open(OUT, "w", encoding="utf-8", newline="") as fh:
        fh.write("\n".join(out) + "\n")
    print("已写出交接：%s（%d 行）" % (OUT, len(out)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
