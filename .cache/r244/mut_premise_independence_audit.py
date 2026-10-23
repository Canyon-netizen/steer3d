#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""mut_premise_independence_audit.py —— **前提独立性第二条实现**的变异台（244.82）。

⚖⚖⚖⚖⚖ **这个台架要回答的问题**
   「`premise_independence_audit.py` 的每条判据**是不是恒绿的**？」
   ⇒ ⇒ 必须证明它们**能红**：
     · **实现被改**（多数规则 / 块键路线 / DP 组合数 / t 分位数 / 二项定义 / 口径常量 …）
       ⇒ ⇒ 对应判据必须由 PASS 变 FAIL；
     · **数据被改**（删一条轨迹 / 把 scope 改掉 …）⇒ ⇒ **G0-3 自检闸必须把它拦下**。

⚖⚖⚖⚖⚖ **纪律（从 244.66–244.81 的台架继承，一条都不许放松）**

   ① 每条变异只改**一处**（⛔ 改多处 ⇒ 抓到了也不知道是哪一处抓的）
   ② 每条变异必须**恰好命中 1 处**（⛔ 命中 0 ⇒ 这条变异**无效** ⇒ 必须报出来；
      ⛔ **等价变异（什么都没变）记「无效」，⛔ 不是「存活」**）
   ③ ⛔ **「崩」≠「抓到」** ⇒ 崩了单独报 ⇒ 崩的条数必须压到 **0**
      （⚠ 例外：**G0-3 硬停**是**被闸门拦下**，⛔ **不是**崩 ⇒ 单独归类为「硬停抓到」）
   ④ **阳性对照先过**：不改任何东西时，目标必须**全绿** ⇒ ⇒
      否则「全红」什么也证明不了 ⇒ ⇒ 直接退出
   ⑤ 期望的「哪条该红」是**手写**的 ⇒ ⇒ **不许从被检对象派生**
   ⑥ ⛔ 本台架**不改**目标实现、⛔ 不改预登记、⛔ 不改原始日志
      ⇒ ⇒ 数据变异只发生在**临时目录里的副本**上
   ⑦ ⛔ 缺前置/远端产物 ⇒ 报 **`PRECOND_FAIL`**（⛔ 这样回归器才判「跑不动」，
      ⛔ **不是**「本轮引入的红」⇒ ⇒ 冤枉）
"""

import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BPATH = os.environ.get("R244_BPATH", "/home/zhourui/steer3d_bpath")
TARGET = "premise_independence_audit.py"
W_LOG = os.path.join(BPATH, "r244_warm_fd_w.log")
R_LOG = os.path.join(BPATH, "r244_warm_fd_rand.log")

CRASH_RE = re.compile(r"^(Traceback \(most recent call last\)|\w*(?:Error|Exception)\b)", re.M)
HARDSTOP_RE = re.compile(r"^G0_3_HARDSTOP:", re.M)

# ⚖ (编号, 类别, 模式, 落点串, 替换串, 期望红的判据 id（列表）, 说明)
#    模式 "self" = 跑 `--selftest`（⛔ 不依赖真数据）；"data" = 跑真数据路径
#    类别 "impl" = 改**实现源码副本**；"data" = 改**日志副本**
MUTATIONS = [
    # ---------------- 实现被改（自检模式，⛔ 零 GPU、不依赖远端产物）----------------
    ("PM1", "impl", "self", '"tol": 0.0050,           # P2：密度容差', '"tol": 0.0500,           # P2：密度容差', ["S-SPEC"],
     "⚖⚖⚖ **密度容差被放宽 10 倍**（0.0050 → 0.0500）⇒ ⇒ 口径常量与预登记不符 ⇒ 必须红"),
    ("PM2", "impl", "self", '"alpha": 0.05,', '"alpha": 0.50,', ["S-SPEC"],
     "⚖⚖⚖ **α 被改**（0.05 → 0.50）⇒ ⇒ 口径常量与预登记不符 ⇒ 必须红"),
    ("PM3", "impl", "self", "nd[s + (2 * j - c) * v] += ways * math.comb(c, j)",
     "nd[s + (2 * j - c) * v] += ways", ["S-DP", "S-DP-TOTAL", "S-EXACT-P"],
     "⚖⚖⚖ **DP 的组合数因子被删掉** ⇒ ⇒ 零分布的**计数总数**不再等于 2^n ⇒ "
     "⇒ 自检的 DP-vs-暴力枚举必须红、真数据的 S-DP-TOTAL / S-EXACT-P 也必须红"),
    ("PM4", "impl", "self", "    return 0.5 * (lo + hi)", "    return 1.96",
     ["S-TQ"],
     "⚖⚖⚖ **t 分位数被换成正态近似常数 1.96**（⛔ 预登记要求自己算）⇒ ⇒ 必须红"),
    ("PM5", "impl", "self", "    var = (n - 1) / float(n) * sum((v - mbar) ** 2 for v in th)",
     "    var = sum((v - mbar) ** 2 for v in th)", ["S-JACK", "S-JACK-LINEAR"],
     "⚖⚖⚖ **jackknife 的 (n−1)/n 因子被删掉** ⇒ ⇒ 方差不对 ⇒ 自检夹具必须红"),
    ("PM6", "impl", "self", "    return min(1.0, sum(pmf(x) for x in range(n + 1) if pmf(x) <= p_obs * (1 + 1e-12)))",
     "    return min(1.0, 2.0 * sum(pmf(x) for x in range(0, min(k, n - k) + 1)))",
     ["S-BINOM"],
     "⚖⚖⚖ **精确二项两侧检验被换成「2×单尾」的凑法**（⛔ 预登记明写不许）⇒ ⇒ 必须红"),
    ("PM7", "impl", "self", '    return "__".join(parts[:-1])', "    return tid",
     ["S-BLOCKKEY", "S-BLOCKROUTE", "S-SELFPANEL"],
     "⚖⚖⚖ **块键路线被改**（按 `__` 切分 ⇒ 直接用整个 tid）⇒ ⇒ 块集合变了 ⇒ 必须红"),

    # ---------------- 实现被改（真数据模式）----------------
    ("PM8", "impl", "self", '"verdict": bool(nT * 2 > m)}', '"verdict": bool(nT * 2 >= m)}',
     ["S-TIE"], "⚖⚖⚖ **多数规则被改成 `>=`**（平票算 True）⇒ ⇒ 这一批真数据里**没有平票轨迹**"
     "（w 臂那唯一一条 m=2 的是 2 正 0 负）⇒ ⇒ 真数据上**不可见** ⇒ ⇒ **靠合成平票夹具 `S-TIE` 抓**"),
    ("PM9", "impl", "data", "    return bool(all(v[\"verdict\"] for v in blk.values()))",
     "    return bool(any(v[\"verdict\"] for v in blk.values()))", ["S-SELFPANEL"],
     "⚖⚖⚖ **块级判决被改成「任一为正」**（⛔ 预登记是「两条都正」）⇒ ⇒ 必须红"),
    ("PM10", "impl", "data", '"scout_blk_perm_p": 0.002700,', '"scout_blk_perm_p": 0.050000,',
     ["S-EXACT-P"],
     "⚖⚖⚖ **与先导探查 MC p 的对账基准被改**（0.002700 → 0.05）⇒ ⇒ "
     "精确 p 与它差了 3 SE 以上 ⇒ 必须红"),
    ("PM11", "impl", "data", "        nT = sum(1 for v in vals if v > 0)",
     "        nT = sum(1 for v in vals if v >= 0)", ["S-SELFPANEL"],
     "⚖⚖⚖ **正号计数把「零格」也算成正**（`v > 0` ⇒ `v >= 0`）⇒ ⇒ rand 臂有 2 条轨迹含零格 "
     "⇒ ⇒ 改判数变了 ⇒ G0-3 自检必须红"),

    # ---------------- 数据被改（真数据模式）----------------
    ("DM1", "data", "data", "__DELETE_FIRST_TID__", "", ["S-SELFPANEL"],
     "⚖⚖⚖ **w 臂日志副本里删掉一整条轨迹的全部记录** ⇒ ⇒ 轨迹数 56 → 55 ⇒ "
     "⇒ G0-3 自检必须红（硬停）"),
    ("DM2", "data", "data", "__SCOPE_ALL__", "", ["S-SELFPANEL"],
     "⚖⚖⚖ **rand 臂日志副本里所有格的 inject_scope 改成 'all'** ⇒ ⇒ 一格都进不了 ⇒ "
     "⇒ G0-3 自检必须红（硬停）"),
]

# ⚖⚖⚖ 等价变异**为什么**在这批数据上不可见（⚖ 手写，⛔ 不从被检对象派生）
EQUIV_WHY = {
    # ⚠ 目前**没有**等价变异（PM8 已由合成平票夹具 `S-TIE` 覆盖 ⇒ ⇒ 不再是等价变异）
}


def run_target(script, mode, workdir, w_log, r_log):
    """⚖ 跑一次目标实现 ⇒ 返回 `(rc, stdout+stderr)`。"""
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if mode == "self":
        cmd = [sys.executable, script, "--selftest"]
    else:
        cmd = [sys.executable, script, "--w-log", w_log, "--rand-log", r_log]
    try:
        r = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True,
                           timeout=1800, env=env)
        return r.returncode, (r.stdout + r.stderr)
    except subprocess.TimeoutExpired:
        return -9, "TIMEOUT"


def _red_ids(out):
    """⚖ 抠出 FAIL 的判据 id（⛔ 期望集是手写的，不许从被检对象派生）。"""
    return set(re.findall(r"^\[FAIL\] (\S+)", out, re.M))


def _my_numbers(out):
    """⚖ 抠出输出里所有 `CROSS|k=v` 与 `= <数>` 的数 ⇒ 用来判「等价变异」。"""
    vals = []
    for ln in out.split("\n"):
        if ln.startswith("CROSS|"):
            vals.append(ln.strip())
            continue
        m = re.search(r"= ([-+0-9.]+)", ln)
        if m:
            vals.append(m.group(1))
    return vals


def _same_numbers(out, base_out):
    """⚖⚖ **等价变异的判别**：源码改了，但算出来的数**逐条相同** ⇒ ⇒ 记「无效」。"""
    a, b = _my_numbers(out), _my_numbers(base_out)
    return bool(a) and a == b


def _mutate_log(src, dst, kind):
    """⚖ 造一份**日志副本**并施加数据变异（⛔ 原件一个字节都不动）。"""
    with io.open(src, encoding="utf-8", errors="replace") as fh:
        lines = fh.read().split("\n")
    out = []
    if kind == "__DELETE_FIRST_TID__":
        first_tid = None
        for ln in lines:
            m = re.match(r'^RESULT\s+r204_cell\s+(\S+)', ln)
            if m and first_tid is None:
                first_tid = m.group(1)
                out.append(ln)
                continue
            if first_tid is not None and m and m.group(1) == first_tid:
                continue          # 删掉这条轨迹的 RESULT 头
            if first_tid is not None and '"tid"' in ln and first_tid in ln:
                continue          # 删掉这条轨迹的 JSON 行
            out.append(ln)
    elif kind == "__SCOPE_ALL__":
        for ln in lines:
            out.append(ln.replace('"inject_scope": "k"', '"inject_scope": "all"'))
    else:
        raise SystemExit("⛔ 未知的数据变异：%s" % kind)
    with io.open(dst, "w", encoding="utf-8", newline="") as fh:
        fh.write("\n".join(out))


def main():
    work = tempfile.mkdtemp(prefix="_mut_pi_")
    try:
        for p in (W_LOG, R_LOG):
            if not os.path.isfile(p):
                print("PRECOND_FAIL: 缺远端产物：%s ⇒ 这一轮**跑不动** ⇒ ⛔ **不是「判据红」**" % p)
                return 2
        with io.open(os.path.join(HERE, TARGET), encoding="utf-8") as fh:
            src_txt = fh.read()

        # ---- ④ 阳性对照：什么都没改 ⇒ 必须全绿（自检模式 + 真数据模式各一次）
        for mode, tag in (("self", "自检模式"), ("data", "真数据模式")):
            rc, out = run_target(os.path.join(HERE, TARGET), mode, work, W_LOG, R_LOG)
            if rc != 0:
                print("⛔ **阳性对照没过**（未改任何东西时目标不是全绿，%s）⇒ ⇒ 台架自己瞎了 ⇒ 退出" % tag)
                print(out[-4000:])
                return 3
            print("阳性对照（%s）：过 ⇒ 阳性对照通过（台架能判红）" % tag)
        base_self = run_target(os.path.join(HERE, TARGET), "self", work, W_LOG, R_LOG)[1]
        base_data = run_target(os.path.join(HERE, TARGET), "data", work, W_LOG, R_LOG)[1]

        caught, invalid, crashed, equivalent, hardstop = [], [], [], [], []
        for mid, kind, mode, find, repl, expect_red, desc in MUTATIONS:
            if kind == "impl":
                n = src_txt.count(find)
                if n != 1:
                    invalid.append((mid, "落点命中 %d 处（期望 1）⇒ **落点无效**（台架瞎了）" % n))
                    continue
                script = os.path.join(work, "target_%s.py" % mid)
                with io.open(script, "w", encoding="utf-8", newline="") as fh:
                    fh.write(src_txt.replace(find, repl))
                w_log, r_log = W_LOG, R_LOG
            else:
                script = os.path.join(HERE, TARGET)
                w_log = os.path.join(work, "w_%s.log" % mid)
                r_log = os.path.join(work, "r_%s.log" % mid)
                _mutate_log(W_LOG, w_log, find)
                if find == "__SCOPE_ALL__":
                    _mutate_log(R_LOG, r_log, find)
                else:
                    shutil.copyfile(R_LOG, r_log)

            rc, out = run_target(script, mode, work, w_log, r_log)
            if rc == -9:
                crashed.append((mid, "超时"))
                continue
            red = _red_ids(out)
            hard = bool(HARDSTOP_RE.search(out))
            if hard:
                hardstop.append((mid, sorted(red)))
                print("[硬停抓到] %-4s ⇒ G0-3 自检闸把它拦下了（红的判据：%s）"
                      % (mid, ",".join(sorted(red))))
                continue
            if _looks_like_crash(out):
                crashed.append((mid, "崩了（⛔ 崩 ≠ 抓到）"))
                print("[崩] %-4s ⇒ %s" % (mid, "崩了（⛔ 崩 ≠ 抓到）"))
                continue
            hit = [e for e in expect_red if e in red]
            if expect_red and rc != 0 and hit:
                caught.append((mid, hit, sorted(red)))
                print("[抓到] %-4s ⇒ 红：%s（同时红了：%s）" % (mid, ",".join(hit),
                                                               ",".join(sorted(red))))
            elif not expect_red and _same_numbers(out, base_data if mode == "data" else base_self):
                why = EQUIV_WHY.get(mid, "⚖ 源码改了但结果逐条相同 ⇒ 等价变异"
                                           "（**原因未登记** ⇒ 记进账本待查，⛔ 不许编理由）")
                equivalent.append((mid, why))
                print("[无效/等价] %-4s ⇒ 源码改了但**这批数据上结果逐条相同** ⇒ 记「无效」：%s"
                      % (mid, why))
            else:
                invalid.append((mid, "❌ 没抓到（rc=%s，红的判据：%s）⇒ **台架瞎了**" % (rc, sorted(red))))

        print("")
        print("变异台：抓到 %d / %d（无效 %d 条 ⇒ 记「无效」⇒ 不计入分母；"
              "其中等价变异 %d 条 ⇒ 有效分母 = %d）"
              % (len(caught) + len(hardstop), len(MUTATIONS),
                 len(invalid) + len(equivalent), len(equivalent),
                 len(caught) + len(hardstop) + len(equivalent)))
        for mid, why in invalid:
            print("  [无效] %-4s %s" % (mid, why))
        for mid, why in equivalent:
            print("  [无效/等价] %-4s %s" % (mid, why))
        print("崩的条数：%d（⛔ 必须是 0）" % len(crashed))
        for mid, why in crashed:
            print("  [崩] %-4s %s" % (mid, why))
        rc = 0 if (not invalid and not crashed
                   and len(caught) + len(hardstop) + len(equivalent) == len(MUTATIONS)) else 1
        print("MUT_RC=%d" % rc)
        return rc
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _looks_like_crash(out):
    return bool(CRASH_RE.search(out))


if __name__ == "__main__":
    sys.exit(main())
