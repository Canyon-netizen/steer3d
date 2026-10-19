#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""nmap_coverage_audit.py —— 跑批用的 `n_eff_map` 到底覆盖了本批哪些轨迹（零 GPU）

🔴🔴 **本工具问什么**

  244.51 登记了一条缺口：「已验的那 60 条侧车里**有没有**本批这 14 个 tid」
  —— 当时的结论是「244.7 只把 60/60 这个数记进账本，**没落 key 清单** ⇒ 本地量不到」。

  ⚖⚠⚠⚠ **那条结论只对了一半**：清单**其实早就在本地**，
  但有**两份同名兄弟**，只有一份带戳：

      .cache/r244/n_eff_map.tsv       md5=2edb95fa…  （20:23 的旧版）
      .cache/r244/n_eff_map.new.tsv   md5=c0d30d22…  （20:25，**跑批用的就是它**）

  ⚖ **跑批戳**（`r244_warm_*.log` 第 2 行 与 结果文件 `_an.txt` 第 2 行）：

      NMAP rows=60 md5=c0d30d22226765b71107ba4db8a2f5af

  ⇒ **权威文件必须靠 md5 戳认，⛔ 不能靠文件名**。

⚖⚠⚖⚖ **实测结论（本工具算出来的）**

  · 权威 map（带戳那份）= **60 行 / 60 个 tid** = `p00…p29 × {think, no_think}`
  · 本批 14 条轨迹 **14/14 命中**，且 `P` **14/14 逐条相等**
  · `n_gen_sidecar` vs `n_gen_npz` **0/60 不一致** ⇒ **t 半边也有独立证据**
  · 权威 map 的 `P` 分布（n=60 / min 108 / max 914 / mean 256.033 / 56 个唯一值）
    与**账本 244.7.2 记的复算分布逐项相等** ⇒ 这是「复算集合 == 跑批集合」的那座桥

  ⇒ ✅ **244.51 登记的覆盖缺口闭合**（w 臂那 14 条**在**已验集合内）。

⚠⚠⚠ 本工具⛔ **不发批**、⛔ 不改探针、⛔ 不连远端、⛔ 不写/删任何文件。
⚖⚠⚠⚖ 每条判据都必须**能红**：变异台改的是喂进来的**数据形状**。
"""

import argparse
import glob
import hashlib
import io
import json
import os
import re
import sys

MAP_GLOB = ".cache/r244/n_eff_map*.tsv"
RESULT_FILES = {"w": ".cache/r244/_an.txt", "rand": ".cache/r244/_ra.txt"}
# ⚖ 跑批戳的落点（结果文件头部自带一行 + 跑批日志各一行）
LOG_GLOB = ".cache/r244/r244_warm_*.log"
# ⚖⚖ 账本 244.7.2 记的**复算**分布 —— 本工具必须**逐项复现它**，
#     否则「清单 == 复算集合」这座桥就没有依据。
LEDGER_P_DIST = {"n": 60, "min": 108, "max": 914, "mean": 256.033, "uniq": 56}
# ⚖ 账本 244.7.7 记的题数
LEDGER_N_QUESTIONS = 30
STAMP_RE = re.compile(r"NMAP rows=(\d+) md5=([0-9a-f]{32})")


class HardFail(Exception):
    pass


# --------------------------------------------------------------- 小工具
def md5_of(path):
    return hashlib.md5(io.open(path, "rb").read()).hexdigest()


def read_stamp(path):
    """⚖ 从一个文件里取 `NMAP rows=N md5=…` 戳。

    ⚖⚠⚠⚠ **只认行首的戳**：⛔ 不许 `search` 全文 —— 那样会命中**别的文件内容里
    恰好包含这串 md5** 的行（本次就撞到过：`_an.txt` 里既有戳行，也有别处提到它）。
    ⇒ 逐行扫、只取**以 `NMAP ` 开头**的行。"""
    for line in io.open(path, encoding="utf-8", errors="replace"):
        if line.startswith("NMAP "):
            m = STAMP_RE.search(line)
            if m:
                return int(m.group(1)), m.group(2)
    return None


def read_map(path):
    rows = [l.split("\t") for l in io.open(path, encoding="utf-8").read().split("\n") if l.strip()]
    if not rows:
        raise HardFail("map %s 是空的 ⇒ ⛔ 拒读" % path)
    hdr = rows[0]
    body = rows[1:]
    return hdr, body


def read_result(path):
    """⚖ 读结果文件：**头部的戳行**与**JSON 行**都要拿到。"""
    stamp, recs = None, []
    for line in io.open(path, encoding="utf-8", errors="replace"):
        t = line.strip()
        if t.startswith("NMAP "):
            m = STAMP_RE.search(t)
            if m:
                stamp = (int(m.group(1)), m.group(2))
            continue
        if not t.startswith("{"):
            continue
        try:
            recs.append(json.loads(t))
        except Exception:
            raise HardFail("结果文件 %s 有坏 JSON 行 ⇒ ⛔ 拒读" % path)
    if not recs:
        raise HardFail("结果文件 %s 一条记录都没有 ⇒ ⛔ 拒读" % path)
    return stamp, recs


def read_begins(path):
    """⚖ 读原始日志里的 `### BEGIN <tid> [i/N] n_eff=X` 行。

    ⚖⚖⚖ 这是**跑批自己印出来的**那一格用的 `n_eff` ⇒ 与权威 map 逐条对上，
    就是「跑批用的就是这份 map 的数」的**逐格**证据。"""
    out = []
    pat = re.compile(r"^### BEGIN (\S+) \[(\d+)/(\d+)\] n_eff=(\d+)")
    for line in io.open(path, encoding="utf-8", errors="replace"):
        m = pat.match(line)
        if m:
            out.append((m.group(1), int(m.group(2)), int(m.group(4))))
    return out


def p_dist(body, i_p):
    Ps = sorted(int(r[i_p]) for r in body)
    return {"n": len(Ps), "min": min(Ps), "max": max(Ps),
            "mean": round(sum(Ps) / float(len(Ps)), 3), "uniq": len(set(Ps))}


# --------------------------------------------------------------- 判据
def audit(map_glob=MAP_GLOB, results=None, logs=None):
    results = results or RESULT_FILES
    L = ["【n_eff_map 覆盖审计】"]
    ok = True

    # ---- C1 戳：原始日志/结果文件里自带的 + 跑批日志里的，必须一致 -------
    # ⚖⚠⚠⚠ **只有原始日志带戳**：`_an.txt` 是**原始驱动日志**（PINNED / NMAP 戳 /
    #   `### BEGIN` 行），而 `_ra.txt` 之类是**纯 JSONL 提取件**（戳被剥掉了）。
    #   ⇒ 「某个文件没戳」是**事实**（提取件），⛔ 不等于「它用的 map 不明」——
    #   跑批日志那一路仍然能给出权威戳。⇒ 判据改成「所有来源的戳必须一致且非空」。
    stamps = {}
    for arm, p in sorted(results.items()):
        if not os.path.exists(p):
            L.append("  C1 ⛔ 结果文件不存在：%s" % p)
            ok = False
            continue
        st, recs = read_result(p)
        if st is None:
            L.append("  C1 %-5s %-14s **无戳**（纯 JSONL 提取件）⇒ 它的 map 身份靠跑批日志兜底"
                     % (arm, os.path.basename(p)))
            continue
        stamps[arm] = st
        L.append("  C1 %-5s %-14s 自带戳：rows=%d md5=%s"
                 % (arm, os.path.basename(p), st[0], st[1]))
    log_stamps = set()
    for lp in sorted(glob.glob(logs or LOG_GLOB)):
        st = read_stamp(lp)
        if st:
            log_stamps.add(st)
    all_st = set(stamps.values()) | log_stamps
    L.append("  C1b 跑批日志里的戳：%s" % sorted(all_st))
    L.append("     来源共 %d 个（结果文件 %d + 跑批日志 %d）⇒ %s"
             % (len(all_st), len(stamps), len(log_stamps),
                "✅ 全部**逐位一致** ⇒ 两臂用的是同一份 map" if len(all_st) == 1
                else "⛔ 戳不一致 ⇒ 两臂用的可能不是同一份 map"))
    ok &= (len(all_st) == 1 and len(all_st) > 0)
    if not all_st:
        return L, 1
    rows_n, want_md5 = list(all_st)[0]

    # ---- C2 必须**按 md5** 定位权威文件，并点名「同名兄弟」 ---------------
    cands = sorted(glob.glob(map_glob))
    if not cands:
        L.append("  C2 ⛔ 找不到任何 map：%s" % map_glob)
        return L, 1
    auth = [p for p in cands if md5_of(p) == want_md5]
    L.append("  C2 候选 map %d 份：" % len(cands))
    for p in cands:
        m = md5_of(p)
        L.append("     %-34s md5=%s %s" % (os.path.basename(p), m,
                                           "✅ **权威（与戳相同）**" if m == want_md5
                                           else "⚠ **兄弟**：md5 与戳不同，⛔ 不是权威"))
    one_auth = (len(auth) == 1)
    L.append("     ⇒ %s" % ("✅ 恰好一份与戳相符" if one_auth else
                            "⛔ 与戳相符的有 %d 份 ⇒ 权威性不唯一" % len(auth)))
    ok &= one_auth
    if not one_auth:
        return L, 1
    MAP = auth[0]
    hdr, body = read_map(MAP)
    ok &= (len(body) == rows_n)
    L.append("     行数 %d（戳记 rows=%d）⇒ %s" % (len(body), rows_n,
                                                  "✅" if len(body) == rows_n else "⛔ 不符"))

    # ---- C3 覆盖：本批轨迹必须 100% 落在权威 map 内 ---------------------
    M = {r[0]: r for r in body}
    i_p = hdr.index("P")
    for arm, p in sorted(results.items()):
        _st, recs = read_result(p)
        used = sorted({r["tid"] for r in recs})
        hit = [t for t in used if t in M]
        miss = [t for t in used if t not in M]
        L.append("  C3 %-5s 轨迹 %d 条 ⇒ 命中权威 map **%d/%d**%s"
                 % (arm, len(used), len(hit), len(used),
                    "" if not miss else "　⛔ 未命中：%s" % (miss,)))
        ok &= (not miss and len(hit) == len(used))

        # ---- C4 命中条的 P 必须与读数**逐条相等** -----------------------
        Pm = {}
        for r in recs:
            Pm.setdefault(r["tid"], r.get("P"))
        bad = [(t, M[t][i_p], Pm.get(t)) for t in hit
               if str(M[t][i_p]) != str(Pm.get(t))]
        L.append("  C4 %-5s 命中条的 P 与读数逐条相等：%s"
                 % (arm, "✅ %d/%d" % (len(hit) - len(bad), len(hit)) if not bad
                    else "⛔ 不等 %s" % (bad[:3],)))
        ok &= (not bad)

    # ---- C5 桥：权威 map 的 P 分布必须**逐项复现**账本 244.7 记的复算分布 --
    d = p_dist(body, i_p)
    L.append("  C5 权威 map 的 P 分布 vs 账本 244.7.2 记的**复算**分布：")
    for k in ("n", "min", "max", "mean", "uniq"):
        same = (d[k] == LEDGER_P_DIST[k])
        L.append("     %-5s map=%-10s 账本=%-10s %s"
                 % (k, d[k], LEDGER_P_DIST[k], "✅" if same else "⛔"))
        ok &= same
    qs = sorted({r[0].split("__")[2] for r in body})
    sfx = sorted({r[0].split("__")[-1] for r in body})
    L.append("     题数 %d（账本记 %d）｜ 后缀 %s ⇒ %s"
             % (len(qs), LEDGER_N_QUESTIONS, sfx,
                "✅" if len(qs) == LEDGER_N_QUESTIONS else "⛔"))
    ok &= (len(qs) == LEDGER_N_QUESTIONS)

    # ---- C6 t 半边：sidecar 的 n_gen 与 npz 的 n_gen 必须 0 不一致 --------
    if "n_gen_sidecar" in hdr and "n_gen_npz" in hdr:
        i_s, i_n = hdr.index("n_gen_sidecar"), hdr.index("n_gen_npz")
        dis = [r[0] for r in body if r[i_s] != r[i_n]]
        L.append("  C6 n_gen_sidecar vs n_gen_npz 不一致 **%d/%d** ⇒ %s"
                 % (len(dis), len(body),
                    "✅ t 半边也有独立证据" if not dis else "⛔ %s" % (dis[:3],)))
        ok &= (not dis)
    else:
        L.append("  C6 ⚠ 这份 map 没有 n_gen_sidecar/n_gen_npz 两列 ⇒ t 半边**未量到**")

    # ---- C7 ⚖⚖⚖ **逐格**核对：跑批日志**自己印的** n_eff -----------------
    # ⚖ 原始日志的每一格都有 `### BEGIN <tid> [i/N] n_eff=X`
    #   ⇒ 把这 137 个 X 与权威 map 的 `n_eff`（以及 `P + t`）**逐条**对上
    #   ⇒ 这就是「跑批用的就是这份 map 的数」的**逐格**证据，
    #   比「P 相等」和「分布相同」都强。
    i_ne = hdr.index("n_eff") if "n_eff" in hdr else None
    i_P2, i_t2 = hdr.index("P"), hdr.index("t")
    tot, good, badb = 0, 0, []
    for arm, p in sorted(results.items()):
        if not os.path.exists(p):
            continue
        for tid, idx, ne in read_begins(p):
            tot += 1
            if tid not in M or i_ne is None:
                badb.append((tid, ne, "map 里没有"))
                continue
            P_, t_, ne_map = int(M[tid][i_P2]), int(M[tid][i_t2]), int(M[tid][i_ne])
            if ne == ne_map and ne == P_ + t_:
                good += 1
            else:
                badb.append((tid, ne, ne_map, P_ + t_))
    L.append("  C7 跑批日志 `### BEGIN … n_eff=X` 与权威 map 逐条相等：**%d/%d** ⇒ %s"
             % (good, tot, "✅ 逐格证实跑批用的就是这份 map 的数" if tot and not badb
                else "⛔ %s" % (badb[:3],)))
    ok &= (bool(tot) and not badb)

    L.append("")
    L.append("⚖⚖⚖ **本工具没查的**：")
    L.append("  · 「复算的 60 条」与「跑批的 60 条」是**同一个集合**这一步，"
             "本工具靠的是「5 项分布逐项相等 + 题集同为 p00…p29 × 2」")
    L.append("    —— 是**实测吻合**，⛔ 不是逐 tid 的同一性证明（要证那个，需远端比对）。")
    L.append("  · `P == len(pid)` 本身（244.50 登记的另一半）—— 本工具**不涉及**。")
    return L, (0 if ok else 1)

# --------------------------------------------------------------- 自检
def selftest(files=None):
    ok, bad = [], []

    def chk(t, cond, why=""):
        (ok if cond else bad).append(t)
        print(("[PASS] %s %s" if cond else "[FAIL] %s %s") % (t, why))

    import tempfile
    d = tempfile.mkdtemp()

    def w(p, s):
        io.open(os.path.join(d, p), "w", encoding="utf-8").write(s)

    # ---- 造一份**权威 map**（60 行、P 分布与账本 244.7.2 记的逐项相等）----
    # ⚖⚖ 这 60 个 P 值是**从权威 map 逐条抄下来的**（结构量，⛔ 不含任何读数），
    #   抄来是为了让夹具的分布**逐项**等于账本记的那一组
    #   （min 108 / max 914 / mean 256.033 / 56 个唯一值）⇒ C5 才验得到东西。
    #   ⚖ 抄来的动机：自己构造 60 个数且同时满足「sum=15362、56 个唯一值、
    #   min 108、max 914」是**凑数**，凑出来的分布可能只对四项、对第五项不对。
    GOLD_P = [
        112, 120, 139, 140, 150, 154, 159, 163, 164, 165, 166, 171,
        173, 174, 188, 193, 196, 196, 203, 216, 226, 241, 268, 277,
        308, 337, 573, 592, 663, 914, 108, 116, 135, 136, 146, 150,
        155, 159, 160, 161, 162, 167, 169, 170, 184, 189, 192, 192,
        199, 212, 222, 237, 264, 273, 304, 333, 569, 588, 659, 910,
    ]
    assert len(GOLD_P) == 60 and len(set(GOLD_P)) == 56
    assert min(GOLD_P) == 108 and max(GOLD_P) == 914
    assert round(sum(GOLD_P) / 60.0, 3) == 256.033
    lines = ["tid\tP\tn_gen_sidecar\tn_gen_npz\tt\tn_eff"]
    tids = []
    for i in range(30):
        q = "p%02d" % i
        for sfx in ("no_think", "think"):
            t = "aime__aime25__%s__%s" % (q, sfx)
            tids.append(t)
    for i, t in enumerate(tids):
        P = GOLD_P[i]
        lines.append("%s\t%d\t500\t500\t249\t%d" % (t, P, P + 249))
    w("n_eff_map.new.tsv", "\n".join(lines) + "\n")
    # ⚖ 兄弟文件：内容**不同**（P 全部 +1、且多一列）⇒ md5 必然不同。
    #   ⚖⚠⚠⚠ **必须让兄弟的 P 也不同**：否则「选错文件」这个错**查不出来**
    #   （P 与分布都一样 ⇒ 判据照样全绿 ⇒ 那是恒绿）。
    #   ⇒ 兄弟的 P 全 +1 ⇒ 一旦权威文件选错，C3/C4/C5 立刻红。
    sib = [lines[0] + "\tX"]
    for l in lines[1:]:
        f = l.split("\t")
        sib.append("%s\t%d%s" % (f[0], int(f[1]) + 1,
                                 "".join("\t" + x for x in f[2:])))
    w("n_eff_map.tsv", "\n".join(sib) + "\n")
    auth_md5 = md5_of(os.path.join(d, "n_eff_map.new.tsv"))
    stamp = "NMAP rows=60 md5=%s" % auth_md5

    # ---- 造两份结果文件（w 用前 14 条，rand 用后 14 条）----------------
    def res(tids_used, tag, with_begins=False, bad_p=None, bad_n_eff=None):
        out = ["# header %s" % tag, stamp]
        for t in tids_used:
            P = dict(l.split("\t")[0:2] for l in lines[1:] if l)[t]
            if bad_p is not None and t == tids_used[0]:
                P = str(int(P) + 1)
            out.append(json.dumps({"tid": t, "arm": tag, "P": int(P),
                                   "n_gen": 500, "pos_frac": 0.5,
                                   "inject_scope": "k", "inject_n_sites": 1,
                                   "p9_lo_meas": 0.0, "p9_hi_meas": 1.0}))
            if with_begins:
                ne = int(P) + 249
                if bad_n_eff is not None and t == tids_used[0]:
                    ne = bad_n_eff
                out.append("### BEGIN %s [1/14] n_eff=%d --inject-scope k" % (t, ne))
        return "\n".join(out) + "\n"
    w("_an.txt", res(tids[:14], "w", with_begins=True))
    w("_ra.txt", res(tids[-14:], "rand"))
    w("warm.log", stamp + "  00:00:00\n")

    L, rc = audit(map_glob=os.path.join(d, "n_eff_map*.tsv"),
                  results={"w": os.path.join(d, "_an.txt"),
                           "rand": os.path.join(d, "_ra.txt")},
                  logs=os.path.join(d, "warm.log"))
    chk("C1", rc == 0, "干净夹具 rc=%d" % rc)
    chk("C2", any("恰好一份与戳相符" in x for x in L), "C2 必须印出权威唯一")
    chk("C2b", any("兄弟" in x and "不是权威" in x for x in L),
        "C2 必须**点名**那份 md5 不同的兄弟")
    chk("C3", any("命中权威 map **14/14**" in x for x in L), "C3 必须印出 14/14")
    chk("C5", any("账本 244.7.2 记的**复算**分布" in x for x in L)
        and not any(x.strip().startswith(("n ", "min ", "max ", "mean ", "uniq "))
                    and "⛔" in x for x in L),
        "C5 必须印出分布对照，且五项**逐项**都是 ✅（⛔ 任何一项不符都要红）")
    chk("C6", any("t 半边也有独立证据" in x for x in L), "C6 必须印出 t 半边证据")

    # ---- 必须能红：把权威 map 换掉（戳对不上）--------------------------
    w("n_eff_map.new.tsv", "\n".join(l + "\tY" for l in lines) + "\n")
    L2, rc2 = audit(map_glob=os.path.join(d, "n_eff_map*.tsv"),
                    results={"w": os.path.join(d, "_an.txt"),
                             "rand": os.path.join(d, "_ra.txt")},
                    logs=os.path.join(d, "warm.log"))
    chk("C7", rc2 != 0 and any("不唯一" in x or "没有" in x for x in L2),
        "戳对不上任何 map ⇒ 必须报红（rc=%d）" % rc2)

    # ---- 必须能红：覆盖不全（结果里塞一条不在 map 的 tid）--------------
    w("n_eff_map.new.tsv", "\n".join(lines) + "\n")
    auth_md5 = md5_of(os.path.join(d, "n_eff_map.new.tsv"))
    stamp2 = "NMAP rows=60 md5=%s" % auth_md5
    w("_an.txt", res(tids[:13], "w").replace(stamp, stamp2)
      + json.dumps({"tid": "aime__aime25__p99__think", "arm": "w", "P": 1,
                    "n_gen": 500, "pos_frac": 0.5, "inject_scope": "k",
                    "inject_n_sites": 1, "p9_lo_meas": 0.0, "p9_hi_meas": 1.0}) + "\n")
    w("warm.log", stamp2 + "  00:00:00\n")
    L3, rc3 = audit(map_glob=os.path.join(d, "n_eff_map*.tsv"),
                    results={"w": os.path.join(d, "_an.txt"),
                             "rand": os.path.join(d, "_ra.txt")},
                    logs=os.path.join(d, "warm.log"))
    chk("C8", rc3 != 0 and any("未命中" in x for x in L3),
        "有一条不在 map 里 ⇒ 必须报红（rc=%d）" % rc3)

    # ---- C9：两臂戳不一致时必须报红 ------------------------------------
    w("_an.txt", res(tids[:14], "w", with_begins=True))
    w("_ra.txt", res(tids[-14:], "rand").replace(
        stamp, "NMAP rows=60 md5=%s" % ("0" * 32)))
    L4, rc4 = audit(map_glob=os.path.join(d, "n_eff_map*.tsv"),
                    results={"w": os.path.join(d, "_an.txt"),
                             "rand": os.path.join(d, "_ra.txt")},
                    logs=os.path.join(d, "warm.log"))
    chk("C9", rc4 != 0 and any("戳不一致" in x for x in L4),
        "两臂戳不一致 ⇒ 必须报红（rc=%d）" % rc4)
    w("_ra.txt", res(tids[-14:], "rand"))

    # ---- C10：逐格 n_eff 对不上时必须报红 ------------------------------
    w("_an.txt", res(tids[:14], "w", with_begins=True, bad_n_eff=12345))
    L5, rc5 = audit(map_glob=os.path.join(d, "n_eff_map*.tsv"),
                    results={"w": os.path.join(d, "_an.txt"),
                             "rand": os.path.join(d, "_ra.txt")},
                    logs=os.path.join(d, "warm.log"))
    chk("C10", rc5 != 0 and not any("✅ 逐格证实" in x for x in L5),
        "有一格 n_eff 对不上 ⇒ 必须报红（rc=%d）" % rc5)
    w("_an.txt", res(tids[:14], "w", with_begins=True))

    # ---- C11：命中条的 P 与读数不等时必须报红 --------------------------
    w("_an.txt", res(tids[:14], "w", with_begins=True, bad_p=True))
    L6, rc6 = audit(map_glob=os.path.join(d, "n_eff_map*.tsv"),
                    results={"w": os.path.join(d, "_an.txt"),
                             "rand": os.path.join(d, "_ra.txt")},
                    logs=os.path.join(d, "warm.log"))
    chk("C11", rc6 != 0 and any("不等" in x for x in L6),
        "P 与读数不等 ⇒ 必须报红（rc=%d）" % rc6)

    # ---- C13：分布不符时，C5 的五项必须逐项报 ⛔ -----------------------
    # ⚖⚠⚠ 干净夹具上五项**全对** ⇒ 「同一项不等」那一支**走不到**
    #   ⇒ 把比较焊成恒真是**死变异**（㊹）。⇒ 另造一份**分布不同**的 map。
    lines2 = [lines[0]] + [
        "%s\t%d\t500\t500\t249\t%d" % (l.split("\t")[0], int(l.split("\t")[1]) + 7,
                                      int(l.split("\t")[1]) + 256)
        for l in lines[1:]]
    w("n_eff_map.new.tsv", "\n".join(lines2) + "\n")
    st2 = "NMAP rows=60 md5=%s" % md5_of(os.path.join(d, "n_eff_map.new.tsv"))
    w("_an.txt", res(tids[:14], "w", with_begins=True).replace(stamp, st2))
    w("_ra.txt", res(tids[-14:], "rand").replace(stamp, st2))
    w("warm.log", st2 + "  00:00:00\n")
    L7, rc7 = audit(map_glob=os.path.join(d, "n_eff_map*.tsv"),
                    results={"w": os.path.join(d, "_an.txt"),
                             "rand": os.path.join(d, "_ra.txt")},
                    logs=os.path.join(d, "warm.log"))
    chk("C13", rc7 != 0 and any(x.strip().startswith(("n ", "min ", "max ", "mean ", "uniq "))
                                 and "⛔" in x for x in L7),
        "分布与账本不符时，C5 的五项里**至少一项**必须报 ⛔（rc=%d）" % rc7)

    for f in glob.glob(os.path.join(d, "*")):
        try:
            os.unlink(f)
        except OSError:
            pass
    try:
        os.rmdir(d)
    except OSError:
        pass

    print("自检 %d/%d 通过" % (len(ok), len(ok) + len(bad)))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description="n_eff_map 覆盖面审计（零 GPU、不连远端）")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    L, rc = audit()
    print("\n".join(L))
    return rc


if __name__ == "__main__":
    sys.exit(main())
