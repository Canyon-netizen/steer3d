#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""fixed_dose_split_log —— 把**一趟**固定剂量跑批日志按 `pos_frac` 拆成多份（⛔ 每个 `pos_frac` 一份）。

## 为什么需要它（244.79 的「甲」）

权威读数器 `r227_kcurve.py` 对**单份日志内**混了 `pos_frac` ⇒ **HardFail**
（`r227_kcurve.py:382-384`：混了不同 `pos_frac` ⇒ 「量的不是同一个东西」⇒ 拒绝合池）。
而固定剂量那一批的 168 格横跨 **三个** `pos_frac`（0.25 / 0.5 / 0.75）⇒ ⇒
那一份日志**读不出来**。

⇒ 「甲」的办法：**跑批仍是一趟一份日志** ⇒ ⇒ **收据后处理**按 `pos_frac` 拆成三份
⇒ ⇒ 每份内部 `pos_frac` 单一 ⇒ ⇒ **现有读数器读得动**（⛔ 读数器**一个字都不改**
⇒ ⇒ 既有收据全部有效）⇒ ⇒ 「三个 `pos_frac` 合池」这一步**上移**到新的分析层。

## 这个工具**做什么**、**不做什么**

· ✅ **做**：把日志按 `pos_frac` 分组，每组写一份日志 ＋ 一份状态文件。
· ✅ **做**：给每份日志写**该 `pos_frac` 那张表的** NMAP 来源戳（行首严格
  `NMAP rows=<N> md5=<32hex>`）⇒ ⇒ 读数器才能判「`n_eff` 交叉校验**能红**」。
· ⛔ **不改任何一个读数**：读数 JSON **逐字节**照抄（判据 J6）。
· ⛔ **不改任何一个 `n_eff`**：BEGIN 里的 `n_eff=` 逐字照抄（判据 J7）。
· ⛔ **BEGIN 行一个字节都不动**（⛔ 连 `[i/N]` 也不重编）：那个号是「日志第几格 ⇔
  清单第几行」的**对齐机制** ⇒ ⇒ 重编它就断了 ⇒ ⇒ 而读数器**不校验**它
  （它自己按位置编号）⇒ ⇒ 没有理由改 ⇒ ⇒ 每份的「原区间」写在头部 `SPLIT` 行里。

## 怎么把「日志里的第 i 格」对上「清单里的第 i 行」

跑批脚本的循环顺序 **就是** 清单的数据行顺序 ⇒ ⇒ 日志 BEGIN 行里的 `[i/N]`
（i 从 1 起）**就是**清单第 i 个数据行 ⇒ ⇒ **按序号**对齐 ⇒ ⇒
**崩掉的格（没有读数）也认得出来** ⇒ ⇒ 它属于哪个 `pos_frac` 不靠猜。

## 判据（每条都能红）

J1 格集合守恒（格数一致 ＋ 每格的 `(tid, pos_frac)` 与清单**对应行**逐条相同）
｜ J2 清单的 `pos_frac` == 读数里的 `pos_frac`（抓口径漂移）｜ J3 格数守恒
（各份之和 == 总数）｜ J4 无重复且不漏（**按格的序号** —— 序号才是格的真身份）
｜ J5 每份内部 `pos_frac` 单一 ｜ J6 读数 JSON 逐字节相同 ｜ J7 BEGIN 的 `n_eff` 逐字相同
｜ J8 每份 status 行数 == 该份格数且末行是 `ALLDONE` ｜ J9 每份的来源戳 == 那张表的
(rows, md5)（**独立重算**，⛔ 不许自指）｜ J10 顺序保持 ｜ J11 各份格数 == 清单按
`pos_frac` 的分组数 ｜ **J12 每份的格区与原日志逐字节相同**（⛔ 裸 `\r` 不许被改写）

Exit: 0 全绿；1 有判据红；2 前置不过。
"""
import argparse
import hashlib
import json
import os
import re
import sys

# ⚖ BEGIN 行的形状。⛔ **独立**于读数器的正则（⇒ 拆出来的日志能被读数器读动，
#   是**交叉**验证，不是「用被检对象验自己」）。
# ⚖ 两种排版都认：runner 现在写的是「tid 在前」；老排版是「[i/n] 在前」。
BEGIN_RE = re.compile(
    r"^###\s+BEGIN\s+"
    r"(?:"
    r"(?P<tidnew>\S+)\s+\[(?P<idxnew>\d+)/(?P<totnew>\d+)\]"   # 新排版（runner 现在写的）
    r"|"
    r"\[(?P<idxold>\d+)/(?P<totold>\d+)\]\s+(?P<tidold>\S+)"   # 老排版
    r")"
    r"\s+(?:n_eff=(?P<neff>\d+)\s+)?(?P<rest>.*?)\s\s+(?P<time>\d\d:\d\d:\d\d)\s*$")
NMAP_RE = re.compile(r"^NMAP rows=(\d+) md5=([0-9a-f]{32})(?:\s|$)")
CELLS_HEADER = "tid\tscope\tn_sites\tpos_frac"


def _read(path):
    """⚖⚠⚠ **必须** `newline=""`（244.79 的 Phase-0 G0-1 实测抓到的一条**真红**）。

    ⚖⚠⚠ **通用换行模式会把 tqdm 写的裸 `\\r`（不带 LF）当成行分隔符并改写成 `\\n`**
       ⇒ ⇒ **每一格的进度条行**都被改了（实测：137 格 ⇒ 137 行含裸 `\\r` ⇒ 274 个 `\\r`
       ⇒ ⇒ 通用换行把 1 行变 3 行）⇒ ⇒ 「拆分**不改任何一格**」这条按**字节**口径就不成立。
       ⇒ ⇒ 读的时候**保留原始字节**，一行都不许动。
    """
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def _data_rows(path):
    """⚖ 数据行数 = **`\\n` 结尾的行数 − 1**（减掉表头那行）⇒ ⇒ 与生产者的
    **`wc -l − 1` 同口径**（244.79 G0-1 的 D1：生产者 60，旧的拆分器算成 61 ⇒ 差 1）。
    """
    return _read(path).count("\n") - 1


def _data_rows_alt(path):
    """⚖ **另一条独立算法**（给判据 J9 用 ⇒ ⛔ 不许和写入方共用同一条路）：
    split 后去掉空行，再减去表头 ⇒ 与 `_data_rows` 的口径若不一致 ⇒ J9 必须红。
    """
    return len([l for l in _read(path).split("\n") if l != ""]) - 1


def _md5(path):
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for c in iter(lambda: fh.read(65536), b""):
            h.update(c)
    return h.hexdigest()


def parse_cells(path):
    """日志 → 每格一个块（不改一个字节）。返回 (blocks, stamps)。"""
    blocks, stamps, cur = [], [], None
    for ln in _read(path).split("\n"):
        m = BEGIN_RE.match(ln)
        if m:
            if cur is not None:
                blocks.append(cur)
            tid = m.group("tidnew") or m.group("tidold")
            idx = m.group("idxnew") or m.group("idxold")
            tot = m.group("totnew") or m.group("totold")
            neff = m.group("neff")
            cur = {"begin": ln, "tid": tid, "idx": int(idx), "tot": int(tot),
                   "neff": int(neff) if neff is not None else None,
                   "rest": m.group("rest"), "time": m.group("time"), "lines": []}
            continue
        ms = NMAP_RE.match(ln)
        if ms:
            stamps.append((int(ms.group(1)), ms.group(2)))
            continue
        if cur is not None:
            cur["lines"].append(ln)
    if cur is not None:
        blocks.append(cur)
    return blocks, stamps


def reading_of(block):
    """块里的读数 JSON（逐字节那一行）。"""
    for ln in block["lines"]:
        s = ln.strip()
        if s.startswith("{") and '"tid"' in s:
            return ln
    return None


def read_pos_frac(block):
    r = reading_of(block)
    if r is None:
        return None
    try:
        d = json.loads(r.strip().rstrip(","))
    except Exception:
        return None
    v = d.get("pos_frac")
    return float(v) if v is not None else None


def read_cells_list(path):
    """4 列清单 → **有序**的数据行列表（⛔ 表头必须逐字相符，⛔ 不许悄悄跑）。"""
    with open(path, encoding="utf-8", newline="") as fh:
        lines = fh.read().split("\n")
    while lines and lines[-1] == "":
        lines.pop()
    if not lines or lines[0] != CELLS_HEADER:
        raise ValueError("清单表头不符：%r（期望 %r）" % (lines[0] if lines else None, CELLS_HEADER))
    rows = []
    for ln in lines[1:]:
        f = ln.split("\t")
        if len(f) != 4 or not f[0]:
            continue
        rows.append({"tid": f[0], "scope": f[1], "n_sites": int(f[2]), "pos_frac": float(f[3])})
    return rows


def split(log_path, status_path, cells_path, nmap_prefix, outdir):
    blocks, stamps = parse_cells(log_path)
    rows = read_cells_list(cells_path)
    os.makedirs(outdir, exist_ok=True)
    groups = {}
    for b in blocks:
        # ⚖ 按**序号**对清单（⛔ 崩掉的格也认得出来 ⇒ ⇒ 不用猜它属于哪个 pos_frac）
        r = rows[b["idx"] - 1] if 0 < b["idx"] <= len(rows) else None
        pf = r["pos_frac"] if r else None
        groups.setdefault(pf, []).append(b)
    written = {}
    for pf, bs in sorted(groups.items(), key=lambda kv: (kv[0] is None, kv[0])):
        key = ("%.2f" % pf).replace(".", "") if pf is not None else "NA"
        tname = "%s_pf%s.tsv" % (nmap_prefix, key)
        # ⚖⚠ **与生产者同口径**（`wc -l − 1`）⇒ ⇒ 244.79 G0-1 的 D1（差 1）在这儿修掉
        nrows = _data_rows(tname) if os.path.isfile(tname) else 0
        md5 = _md5(tname) if os.path.isfile(tname) else ""
        lpath = os.path.join(outdir, "pf%s.log" % key)
        spath = os.path.join(outdir, "pf%s_status.txt" % key)
        with open(lpath, "w", encoding="utf-8", newline="") as fh:
            fh.write("NMAP rows=%d md5=%s  %s\n" % (nrows, md5, bs[0]["time"]))
            # ⚖⚠ **BEGIN 行一个字都不动**（⛔ 连 `[i/N]` 也不重编）：
            #   序号是「日志第几格 ⇔ 清单第几行」的**对齐机制** ⇒ ⇒ 重编它就断了
            #   ⇒ ⇒ 而且读数器**不校验**这个号（它自己按位置编号）⇒ ⇒ 不必改
            fh.write("SPLIT pf=%s cells=%d orig_index=%d..%d of %d from=%s\n"
                     % (("%.2f" % pf) if pf is not None else "NA", len(bs),
                        bs[0]["idx"], bs[-1]["idx"], bs[0]["tot"], log_path))
            for b in bs:
                fh.write(b["begin"] + "\n")
                for ln in b["lines"]:
                    fh.write(ln + "\n")
        st_lines = []
        all_done_line = "ALLDONE"
        if os.path.isfile(status_path):
            allst = _read(status_path).split("\n")
            # ⚖ **原样保留**生产者的 `ALLDONE` 行（它带时间戳：实测 `ALLDONE 21:16:01`）
            #   ⇒ ⇒ 不许自己另写一个裸 `ALLDONE`（244.79 G0-1 的 D3：措辞差 1 行）
            for l in allst:
                if l.startswith("ALLDONE"):
                    all_done_line = l
            for b in bs:
                r = rows[b["idx"] - 1] if 0 < b["idx"] <= len(rows) else None
                if r is None:
                    continue
                # ⚖ **精确**匹配：同一 tid 有 3 个 `pos_frac` 的格 ⇒ 只按 tid 前缀会串行
                prefix = ("%s k=%d " % (b["tid"], r["n_sites"])) if r["scope"] == "k" \
                    else ("%s scope=%s " % (b["tid"], r["scope"]))
                hit = [l for l in allst if l.startswith(prefix)]
                st_lines.append(hit[0] if hit else "")
        with open(spath, "w", encoding="utf-8", newline="") as fh:
            for ln in st_lines:
                fh.write(ln + "\n")
            fh.write(all_done_line + "\n")
        written[pf] = {"log": lpath, "status": spath, "n": len(bs), "rows": nrows,
                        "md5": md5, "key": key, "table": tname}
    return blocks, groups, written, stamps


def _pf_of(b, rows):
    """块所属的 `pos_frac` ⇒ **按序号**对清单（⛔ 崩掉的格也认得出来）。"""
    r = rows[b["idx"] - 1] if 0 < b["idx"] <= len(rows) else None
    return r["pos_frac"] if r else None


def judge(orig_blocks, orig_stamps, written, rows):
    """⚠⚠ **基于产物**判定：把**写出来的文件重读一遍**再验 ⇒ ⇒ 变异打得到它
    （⛔ 判内存里的模型 ⇒ 变异改了文件也照样「全绿」⇒ ⇒ 那是假绿）。

    返回 (results, failures)。
    """
    R = []

    def ck(name, ok, detail=""):
        R.append((name, bool(ok), detail))

    # ---- J1（输入侧）：格数一致 ＋ 每格 (tid,pos_frac) 与清单**对应行**相同
    bad = []
    if len(orig_blocks) != len(rows):
        bad.append("格数 %d != 清单 %d" % (len(orig_blocks), len(rows)))
    for b in orig_blocks:
        r = rows[b["idx"] - 1] if 0 < b["idx"] <= len(rows) else None
        if r is None:
            bad.append("%s 序号 %d 越界" % (b["tid"], b["idx"]))
            continue
        if r["tid"] != b["tid"]:
            bad.append("%s 序号 %d 对应清单是 %s" % (b["tid"], b["idx"], r["tid"]))
        got = read_pos_frac(b)
        if got is not None and abs(got - r["pos_frac"]) > 1e-12:
            bad.append("%s 清单 pf=%s 读数 pf=%s" % (b["tid"], r["pos_frac"], got))
    ck("J1 格集合守恒（格数一致 ＋ 每格 (tid,pos_frac) 与清单对应行相同）", not bad,
       "; ".join(bad[:3]))

    # ---- J2 清单 pos_frac == 读数里的 pos_frac（口径漂移，⛔ 单列一条）
    bad2 = []
    for b in orig_blocks:
        r = rows[b["idx"] - 1] if 0 < b["idx"] <= len(rows) else None
        if r is None:
            continue
        got = read_pos_frac(b)
        if got is None:
            continue
        if abs(got - r["pos_frac"]) > 1e-12:
            bad2.append("%s 清单=%s 读数=%s" % (b["tid"], r["pos_frac"], got))
    ck("J2 清单 pos_frac == 读数 pos_frac（无口径漂移）", not bad2, "; ".join(bad2[:3]))

    # ---- 逐份**重读产物**
    part = {}
    for pf, w in written.items():
        pb, _ps = parse_cells(w["log"])
        part[pf] = pb

    # ---- J3 格数守恒
    tot = sum(len(pb) for pb in part.values())
    ck("J3 格数守恒（各份之和 == 原格数）", tot == len(orig_blocks),
       "%d vs %d" % (tot, len(orig_blocks)))

    # ---- J4 无重复且不漏（**按格的序号**：序号才是格的**真身份**）
    #   ⚖⚠ 244.79 G0-1 的 D2：原先用 `(tid, pos_frac)` 当唯一键 ⇒ ⇒ 旧批同一 tid 在
    #   **同一个** `pos_frac` 上有 9~10 个格（剂量阶梯）⇒ ⇒ 报 81 处假「重复」
    #   ⇒ ⇒ 而**序号**（日志第几格）在任何形状下都唯一 ⇒ ⇒ 改用它。
    seen, dup = {}, []
    for pf, pb in part.items():
        for b in pb:
            key = b["idx"]
            if key in seen:
                dup.append("序号 %s 出现在两份里" % key)
            seen[key] = pf
    missing = [b["idx"] for b in orig_blocks if b["idx"] not in seen]
    ck("J4 无重复且不漏（每格序号恰好出现在一份里）", not dup and not missing,
       "; ".join((dup + ["漏 序号 %s" % m for m in missing])[:3]))

    # ---- J5 每份内部 pos_frac 单一
    mixed = []
    for pf, pb in part.items():
        s = set(read_pos_frac(b) for b in pb if read_pos_frac(b) is not None)
        if len(s) > 1:
            mixed.append("pf=%s 混了 %s" % (pf, sorted(s)))
        elif s and pf not in s:
            mixed.append("pf=%s 里装着 %s" % (pf, sorted(s)))
    ck("J5 每份内部 pos_frac 单一", not mixed, "; ".join(mixed[:3]))

    # ---- J6 读数 JSON 逐字节相同（产物 vs 原日志）
    diff = []
    for pf, pb in part.items():
        want = [b for b in orig_blocks if _pf_of(b, rows) == pf]
        if len(pb) != len(want):
            diff.append("pf=%s 格数 %d != %d" % (pf, len(pb), len(want)))
            continue
        for a, b2 in zip(want, pb):
            if reading_of(a) != reading_of(b2):
                diff.append(a["tid"])
                break
    ck("J6 读数 JSON 逐字节相同（拆分没改任何数）", not diff, str(diff[:3]))

    # ---- J7 BEGIN 的 n_eff 逐字相同
    ne = []
    for pf, pb in part.items():
        want = [b for b in orig_blocks if _pf_of(b, rows) == pf]
        if len(pb) != len(want):
            continue
        for a, b2 in zip(want, pb):
            if a["neff"] is not None and ("n_eff=%d" % a["neff"]) not in b2["begin"]:
                ne.append(a["tid"])
                break
    ck("J7 BEGIN 的 n_eff 逐字相同", not ne, str(ne[:3]))

    # ---- J8 status 行数 + 逐行对得上 + 末行 ALLDONE
    st = []
    for pf, w in written.items():
        lines = [l for l in _read(w["status"]).split("\n") if l]
        # ⚖ 尾行是 `ALLDONE` **或** `ALLDONE 21:16:01`（生产者带钟面）⇒ ⇒ 用 **startswith**
        #   （⛔ 精确等于会把带钟面的尾行算进 body ⇒ 138 vs 137 ⇒ J8 假红）
        body = [l for l in lines if not l.startswith("ALLDONE")]
        pb = part.get(pf, [])
        if len(body) != len(pb) or not lines or not lines[-1].startswith("ALLDONE"):
            st.append("pf=%s body=%d 期望=%d 末行=%r"
                      % (pf, len(body), len(pb), lines[-1] if lines else None))
            continue
        for b, ln in zip(pb, body):
            r = rows[b["idx"] - 1] if 0 < b["idx"] <= len(rows) else None
            if r is None:
                continue
            prefix = ("%s k=%d " % (r["tid"], r["n_sites"])) if r["scope"] == "k" \
                else ("%s scope=%s " % (r["tid"], r["scope"]))
            if not ln.startswith(prefix):
                st.append("pf=%s status 行对不上：%r" % (pf, ln))
                break
    ck("J8 每份 status 行数 == 该份格数、逐行对得上、末行 ALLDONE", not st,
       "; ".join(st[:3]))

    # ---- J9 来源戳 == 那张表的 (rows, md5)
    #   ⚖⚠ 244.79 G0-1 的 D1：原先 J9 拿写出的戳跟**写入方自己算的** `w["rows"]` 比
    #   ⇒ ⇒ **自指** ⇒ ⇒ 口径错 1 也照样绿（恒绿护栏！）⇒ ⇒ 现在**独立重算**：
    #   判据方用**另一条算法**（`_data_rows_alt`）从**表文件本身**数 ⇒ ⇒ 口径不一致就红。
    stm = []
    for pf, w in written.items():
        head = [l for l in _read(w["log"]).split("\n") if NMAP_RE.match(l)]
        if not head:
            stm.append("pf=%s 没有来源戳" % pf)
            continue
        m = NMAP_RE.match(head[0])
        exp_rows, exp_md5 = w["rows"], w["md5"]
        tbl = w.get("table")
        if tbl and os.path.isfile(tbl):
            exp_rows = _data_rows_alt(tbl)
            exp_md5 = _md5(tbl)
        if int(m.group(1)) != exp_rows or m.group(2) != exp_md5:
            stm.append("pf=%s 戳=%s/%s 期望=%s/%s"
                       % (pf, m.group(1), m.group(2), exp_rows, exp_md5))
    ck("J9 每份的来源戳 == 那张表的 (rows, md5)（**独立重算**，不许自指）", not stm,
       "; ".join(stm[:3]))

    # ---- J10 顺序保持（按原日志的序号**严格递增**）
    ordr = []
    for pf, pb in part.items():
        idxs = [b["idx"] for b in pb]
        if idxs != sorted(idxs) or len(set(idxs)) != len(idxs):
            ordr.append("pf=%s 序号 %s" % (pf, idxs[:8]))
    ck("J10 每份内顺序与原日志一致", not ordr, "; ".join(ordr[:3]))

    # ---- J11 各份格数 == 清单按 pos_frac 的分组数
    want = {}
    for r in rows:
        want[r["pos_frac"]] = want.get(r["pos_frac"], 0) + 1
    got = {pf: len(pb) for pf, pb in part.items()}
    ck("J11 各份格数 == 清单按 pos_frac 的分组数", want == got,
       "清单 %s / 实际 %s" % (want, got))

    # ---- J12 每份的**格区**与原日志**逐字节**相同（⛔ 头部两行除外）
    #   ⚖⚠⚠ 这是 244.79 **Phase-0 G0-1 的核心判据**：通用换行模式把 tqdm 的裸 `\r`
    #   改写成 `\n`（137 格全中）⇒ 就是被这条抓到的 ⇒ ⇒ 它必须**留在工具里**。
    diffb = []
    for pf, w in written.items():
        want_blocks = [b for b in orig_blocks if _pf_of(b, rows) == pf]
        want = "".join(("\n".join([b["begin"]] + b["lines"]) + "\n") for b in want_blocks)
        parts = _read(w["log"]).split("\n")
        got = "\n".join(parts[2:])          # 去掉头部两行（NMAP + SPLIT）
        if got.rstrip("\n") != want.rstrip("\n"):
            diffb.append("pf=%s 字节不同（原 %d vs 拆 %d）"
                         % (pf, len(want), len(got)))
    ck("J12 每份的格区与原日志逐字节相同（裸 \\r 不许被改写）", not diffb,
       "; ".join(diffb[:3]))

    fails = [n for n, ok, d in R if not ok]
    return R, fails


# ------------------------------------------------------------------ 自检

def _fixture(n_tracks=6, pfs=(0.25, 0.5, 0.75), root=None):
    """造一份**结构与真跑批一致**的混合 `pos_frac` 夹具（日志 + 状态 + 清单 + 三张表）。"""
    import tempfile
    root = root or tempfile.mkdtemp(prefix="fdsplit_")
    os.makedirs(root, exist_ok=True)
    tids = ["aime__aime25__p%02d__%s" % (i, "think" if i % 2 else "no_think")
            for i in range(n_tracks)]
    clist, clog, cst = [], [], []
    for i, tid in enumerate(tids):
        for pf in pfs:
            n_sites = 10 + i * 3 + int(pf * 100)
            clist.append("%s\tk\t%d\t%.2f" % (tid, n_sites, pf))
            clog.append("### BEGIN %s [%d/%d] n_eff=%d --inject-scope k --inject-n-sites %d  10:00:00"
                        % (tid, len(clist), n_tracks * len(pfs), 300 + i, n_sites))
            # ⚖⚠ **裸 `\r`（不带 LF）** 的 tqdm 进度条行 ⇒ ⇒ 与真跑批日志**同形**
            #   （实测真批 137 格 ⇒ 137 行含裸 `\r` ⇒ 274 个 `\r`）
            #   ⇒ ⇒ 它就是「通用换行模式会把 `\r` 改写成 `\n`」那个坑的现场
            clog.append("Loading weights:   0%|          | 0/311 [00:00<?, ?it/s]\r"
                        "Loading weights: 100%|##########| 311/311 [00:00<00:00, 1.23it/s]")
            clog.append('{"tid": "%s", "pos_frac": %.2f, "t": 1, "n_gen": 2, "P": 3, '
                        '"n_steps": 60, "gap": 113.474, "arm": "w"}' % (tid, pf))
            clog.append("### END   [%d/%d] %s rc=0  10:00:01"
                        % (len(clist), n_tracks * len(pfs), tid))
            cst.append("%s k=%d rc=0" % (tid, n_sites))
    cst.append("ALLDONE")
    logp = os.path.join(root, "fix.log")
    statp = os.path.join(root, "fix_status.txt")
    clp = os.path.join(root, "fix_cells.tsv")
    with open(logp, "w", encoding="utf-8") as fh:
        fh.write("NMAP rows=60 md5=%s  10:00:00\n" % ("a" * 32))
        fh.write("\n".join(clog) + "\n")
    with open(statp, "w", encoding="utf-8") as fh:
        fh.write("\n".join(cst) + "\n")
    with open(clp, "w", encoding="utf-8") as fh:
        fh.write(CELLS_HEADER + "\n")
        fh.write("\n".join(clist) + "\n")
    nmap = os.path.join(root, "nmap")
    for pf in pfs:
        key = ("%.2f" % pf).replace(".", "")
        p = "%s_pf%s.tsv" % (nmap, key)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("tid\tP\tn_gen_sidecar\tn_gen_npz\tt\tn_eff\n")
            for tid in tids:
                fh.write("%s\t100\t200\t200\t50\t150\n" % tid)
    return root, logp, statp, clp, nmap


def selftest():
    import shutil
    T = []

    def ck(name, ok, detail=""):
        T.append((name, bool(ok), detail))

    root, logp, statp, clp, nmap = _fixture()
    outdir = os.path.join(root, "out")
    try:
        blocks, groups, written, stamps = split(logp, statp, clp, nmap, outdir)
        R, fails = judge(blocks, stamps, written, read_cells_list(clp))
        ck("自检：夹具上 12 条判据全绿", not fails, ",".join(fails))
        ck("自检：夹具解析出 %d 格（期望 18）" % len(blocks), len(blocks) == 18, str(len(blocks)))
        ck("自检：拆成 3 份（期望 3）", len(written) == 3, str(sorted(str(k) for k in written)))
        ck("自检：拆出来的每份 pos_frac 单一",
           all(len(set(read_pos_frac(b) for b in bs if read_pos_frac(b) is not None)) == 1
               for bs in groups.values()), "")
    except Exception as e:
        ck("自检：夹具上 12 条判据全绿", False, repr(e))

    def rerun(sub, name, want_fail, mutate):
        try:
            r, lp, sp, cp, np_ = _fixture(root=os.path.join(root, sub))
            mutate(lp, sp, cp)
            b, g, w, s = split(lp, sp, cp, np_, os.path.join(r, "out"))
            Rr, fr = judge(b, s, w, read_cells_list(cp))
            ck(name, want_fail in fr, str(fr))
        except Exception as e:
            ck(name, False, repr(e))

    # 红 1：读数里的 pos_frac 与清单不符 ⇒ J2 红
    def m1(lp, sp, cp):
        t = _read(lp).replace('"pos_frac": 0.25', '"pos_frac": 0.50')
        with open(lp, "w", encoding="utf-8") as fh:
            fh.write(t)
    rerun("r1", "红 1：读数 pos_frac 与清单不符 ⇒ J2 红",
          "J2 清单 pos_frac == 读数 pos_frac（无口径漂移）", m1)

    # 红 2：清单少一格 ⇒ J1 红
    def m2(lp, sp, cp):
        lines = _read(cp).split("\n")
        with open(cp, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines[:1] + lines[2:]))
    rerun("r2", "红 2：清单少一格 ⇒ J1 红",
          "J1 格集合守恒（格数一致 ＋ 每格 (tid,pos_frac) 与清单对应行相同）", m2)

    # 红 3：表头不对 ⇒ 硬失败
    try:
        r, lp, sp, cp, np_ = _fixture(root=os.path.join(root, "r3"))
        with open(cp, "w", encoding="utf-8") as fh:
            fh.write(_read(cp).replace("n_sites", "n_site"))
        raised = False
        try:
            read_cells_list(cp)
        except ValueError:
            raised = True
        ck("红 3：清单表头不对 ⇒ 硬失败（不许悄悄跑）", raised, "")
    except Exception as e:
        ck("红 3：清单表头不对 ⇒ 硬失败（不许悄悄跑）", False, repr(e))

    # 红 4：某份的来源戳指向**错的表** ⇒ J9 红
    def m4(lp, sp, cp):
        pass
    try:
        r, lp, sp, cp, np_ = _fixture(root=os.path.join(root, "r4"))
        b, g, w, s = split(lp, sp, cp, np_, os.path.join(r, "out"))
        pf0 = sorted(w.keys())[0]
        lines = _read(w[pf0]["log"]).split("\n")
        lines[0] = "NMAP rows=60 md5=%s  10:00:00" % ("b" * 32)
        with open(w[pf0]["log"], "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        Rr, fr = judge(b, s, w, read_cells_list(cp))
        ck("红 4：某份的来源戳指向错的表 ⇒ J9 红",
           "J9 每份的来源戳 == 那张表的 (rows, md5)（**独立重算**，不许自指）" in fr, str(fr))
    except Exception as e:
        ck("红 4：某份的来源戳指向错的表 ⇒ J9 红", False, repr(e))

    # 红 5：status 少一行 ⇒ J8 红
    try:
        r, lp, sp, cp, np_ = _fixture(root=os.path.join(root, "r5"))
        b, g, w, s = split(lp, sp, cp, np_, os.path.join(r, "out"))
        pf0 = sorted(w.keys())[0]
        lines = [l for l in _read(w[pf0]["status"]).split("\n") if l and l != "ALLDONE"]
        with open(w[pf0]["status"], "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines[:-1] + ["ALLDONE"]) + "\n")
        Rr, fr = judge(b, s, w, read_cells_list(cp))
        ck("红 5：某份 status 少一行 ⇒ J8 红",
           "J8 每份 status 行数 == 该份格数、逐行对得上、末行 ALLDONE" in fr, str(fr))
    except Exception as e:
        ck("红 5：某份 status 少一行 ⇒ J8 红", False, repr(e))

    # 红 6：读数 JSON 被改写 ⇒ J6 红
    try:
        r, lp, sp, cp, np_ = _fixture(root=os.path.join(root, "r6"))
        b, g, w, s = split(lp, sp, cp, np_, os.path.join(r, "out"))
        pf0 = sorted(w.keys())[0]
        with open(w[pf0]["log"], "w", encoding="utf-8") as fh:
            fh.write(_read(w[pf0]["log"]).replace('"n_steps": 60', '"n_steps": 61'))
        Rr, fr = judge(b, s, w, read_cells_list(cp))
        ck("红 6：读数 JSON 被改写 ⇒ J6 红",
           "J6 读数 JSON 逐字节相同（拆分没改任何数）" in fr, str(fr))
    except Exception as e:
        ck("红 6：读数 JSON 被改写 ⇒ J6 红", False, repr(e))

    # 红 7：一份里塞进别的 pos_frac 的格 ⇒ J5 红
    try:
        r, lp, sp, cp, np_ = _fixture(root=os.path.join(root, "r7"))
        b, g, w, s = split(lp, sp, cp, np_, os.path.join(r, "out"))
        pf0 = sorted(w.keys())[0]
        pf1 = [k for k in sorted(w.keys()) if k != pf0][0]
        # 把 pf1 的一份的日志内容并进 pf0 的那份 ⇒ ⇒ 那份内部就混了 pos_frac
        with open(w[pf0]["log"], "a", encoding="utf-8") as fh:
            fh.write(_read(w[pf1]["log"]).split("\n", 2)[2])
        Rr, fr = judge(b, s, w, read_cells_list(cp))
        ck("红 7：一份里混进别的 pos_frac ⇒ J5 红",
           "J5 每份内部 pos_frac 单一" in fr, str(fr))
    except Exception as e:
        ck("红 7：一份里混进别的 pos_frac ⇒ J5 红", False, repr(e))

    # ⚖⚠ 下面 5 条：**J3 / J4 / J7 / J10 / J11** 各自的**红化反例**
    #   （244.79 自查发现：原先 11 条判据**只**有 7 条配了反例 ⇒ ⇒ 补齐 ⇒ 16 条）
    #   ⚖ 全部**基于产物**改写（⛔ 改内存模型 ⇒ 变异打不到 ⇒ 那是假绿）

    def _split_log(path):
        """份日志 → (头部行, [块行列表])。头部 = 第一条 BEGIN 之前的行（NMAP / SPLIT）。"""
        hdr, blocks, cur = [], [], None
        for ln in _read(path).split("\n"):
            if BEGIN_RE.match(ln):
                if cur is not None:
                    blocks.append(cur)
                cur = [ln]
            elif cur is None:
                hdr.append(ln)
            else:
                cur.append(ln)
        if cur is not None:
            blocks.append(cur)
        return hdr, blocks

    def _write_log(path, hdr, blocks):
        with open(path, "w", encoding="utf-8") as fh:
            for ln in hdr:
                fh.write(ln + "\n")
            for b in blocks:
                for ln in b:
                    fh.write(ln + "\n")

    def _red(name, want, mutate, sub):
        """跑一遍夹具 → 改产物 → 重判 ⇒ 断言 `want` 那条判据真的红了。"""
        try:
            r, lp, sp, cp, np_ = _fixture(root=os.path.join(root, sub))
            b, g, w, s = split(lp, sp, cp, np_, os.path.join(r, "out"))
            pf0 = sorted(w.keys())[0]
            mutate(w, cp, pf0)
            Rr, fr = judge(b, s, w, read_cells_list(cp))
            ck(name, want in fr, str(fr))
        except Exception as e:
            ck(name, False, repr(e))

    def m8(w, cp, pf0):
        """少一整块 ⇒ 格数守恒破。"""
        hdr, blocks = _split_log(w[pf0]["log"])
        _write_log(w[pf0]["log"], hdr, blocks[:-1])

    _red("红 8：一份里少了一整块 ⇒ J3 红",
         "J3 格数守恒（各份之和 == 原格数）", m8, "r8")

    def m9(w, cp, pf0):
        """同一格出现两次 ⇒ (tid,pos_frac) 不唯一。"""
        hdr, blocks = _split_log(w[pf0]["log"])
        _write_log(w[pf0]["log"], hdr, blocks + [blocks[0]])

    _red("红 9：一份里同一格出现两次 ⇒ J4 红",
         "J4 无重复且不漏（每格序号恰好出现在一份里）", m9, "r9")

    def m10(w, cp, pf0):
        """BEGIN 行的 n_eff 被改 ⇒ 读数没动 ⇒ 只该 J7 红。"""
        hdr, blocks = _split_log(w[pf0]["log"])
        blocks[0][0] = re.sub(r"n_eff=\d+", "n_eff=999", blocks[0][0], count=1)
        _write_log(w[pf0]["log"], hdr, blocks)

    _red("红 10：BEGIN 的 n_eff 被改 ⇒ J7 红",
         "J7 BEGIN 的 n_eff 逐字相同", m10, "r10")

    def m11(w, cp, pf0):
        """前两块对调 ⇒ 顺序不再递增。"""
        hdr, blocks = _split_log(w[pf0]["log"])
        blocks = [blocks[1], blocks[0]] + blocks[2:]
        _write_log(w[pf0]["log"], hdr, blocks)

    _red("红 11：一份里两格对调 ⇒ J10 红",
         "J10 每份内顺序与原日志一致", m11, "r11")

    def m12(w, cp, pf0):
        """清单里一行 pos_frac 被改 ⇒ 各份格数与清单分组数对不上。"""
        lines = _read(cp).split("\n")
        f = lines[2].split("\t")
        f[3] = "0.50" if f[3] != "0.50" else "0.75"
        lines[2] = "\t".join(f)
        with open(cp, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))

    _red("红 12：清单里一行的 pos_frac 被改 ⇒ J11 红",
         "J11 各份格数 == 清单按 pos_frac 的分组数", m12, "r12")

    def m13(w, cp, pf0):
        """把拆出来的份里的裸 `\\r` 换成 `\\n` ⇒ ⇒ 字节被改 ⇒ J12 必须红。"""
        raw = _read(w[pf0]["log"])
        with open(w[pf0]["log"], "w", encoding="utf-8", newline="") as fh:
            fh.write(raw.replace("\r", "\n"))

    _red("红 13：拆出来的份里裸 \\r 被换成 \\n ⇒ J12 红",
         "J12 每份的格区与原日志逐字节相同（裸 \\r 不许被改写）", m13, "r13")

    shutil.rmtree(root, ignore_errors=True)
    npass = sum(1 for _, ok, _ in T if ok)
    for name, ok, msg in T:
        print("[%s] %s%s" % ("OK  " if ok else "FAIL", name, ("  ← " + msg) if msg else ""))
    print("fixed_dose_split_log --selftest: %d/%d" % (npass, len(T)))
    return 0 if npass == len(T) else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log")
    ap.add_argument("--status")
    ap.add_argument("--cells")
    ap.add_argument("--nmap-prefix")
    ap.add_argument("--outdir")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    for k in ("log", "status", "cells", "nmap_prefix", "outdir"):
        if not getattr(a, k):
            print("⛔ 缺 --%s ⇒ 硬停" % k.replace("_", "-"))
            return 2
    blocks, groups, written, stamps = split(a.log, a.status, a.cells, a.nmap_prefix, a.outdir)
    rows = read_cells_list(a.cells)
    R, fails = judge(blocks, stamps, written, rows)
    for name, ok, msg in R:
        print("[%s] %-46s %s" % ("OK  " if ok else "FAIL", name, msg))
    print("--- 拆出来的份 ---")
    for pf, w in sorted(written.items(), key=lambda kv: (kv[0] is None, kv[0])):
        print("  pos_frac=%-6s → %s（%d 格）  status=%s"
              % (("%.2f" % pf) if pf is not None else "NA", os.path.basename(w["log"]),
                 w["n"], os.path.basename(w["status"])))
    print("checks_failed=%d  %s" % (len(fails), ",".join(fails) if fails else "ALL_GREEN"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
