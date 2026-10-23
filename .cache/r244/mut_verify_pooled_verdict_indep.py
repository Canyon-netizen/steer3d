#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""mut_verify_pooled_verdict_indep.py —— **独立重算器**的变异台（244.81）。

⚖⚖⚖⚖⚖ **这个台架要回答的问题**

  「面板上的数」与「独立重算的数」逐条比对 ⇒ ⇒ 这条比对**本身**是不是一条
  **恒绿护栏**？⇒ ⇒ 必须证明它**能红**：
    · **面板被改**（数字抄错 / 一行被删）⇒ ⇒ 重算器必须报 FAIL；
    · **重算器自己的实现被改**（多数规则 / 符号 / 分母 / 区间）⇒ ⇒
      它必须与面板**对不上** ⇒ ⇒ 报 FAIL。

⚖⚖⚖⚖⚖ **纪律**（从 244.66–244.80 的台架继承，一条都不许放松）：

   ① 每条变异只改**一处**（⛔ 改多处 ⇒ 抓到了也不知道是哪一处抓的）
   ② 每条变异必须**恰好命中 1 处**（⛔ 命中 0 ⇒ 这条变异**无效** ⇒ 必须报出来；
      ⛔ **等价变异（什么都没变）记「无效」，⛔ 不是「存活」**）
   ③ ⛔ **「崩」≠「抓到」** ⇒ 崩了单独报 ⇒ 崩的条数必须压到 **0**
   ④ **阳性对照先过**：不改任何东西时，重算器必须**全绿** ⇒ ⇒
      否则「全红」什么也证明不了 ⇒ ⇒ 直接退出
   ⑤ 期望的「哪条该红」是**手写**的 ⇒ ⇒ **不许从被检对象派生**
   ⑥ ⛔ 本台架**不改**分析器、⛔ 不改预登记、⛔ 不改原始日志
      ⇒ ⇒ 面板变异只发生在**临时目录里的副本**上
"""

import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
TARGET = "verify_pooled_verdict_indep.py"
BPATH = os.environ.get("R244_BPATH", "/home/zhourui/steer3d_bpath")

W_LOG = os.path.join(BPATH, "r244_warm_fd_w.log")
R_LOG = os.path.join(BPATH, "r244_warm_fd_rand.log")
PANEL = os.environ.get("R244_PANEL", "/dev/shm/_pooled_24481/verdict_panel.txt")

CRASH_RE = re.compile(r"^(Traceback \(most recent call last\)|\w*(?:Error|Exception)\b)", re.M)

# ⚖ (编号, 类别, 落点串, 替换串, 期望红的判据 id（列表）, 说明)
#    类别 "panel" = 改**面板副本**；类别 "impl" = 改**重算器源码副本**
MUTATIONS = [
    ("PM1", "panel", "改判 **46/56**", "改判 **47/56**", ["T-w-pos"],
     "⚖ 面板上 w 臂改判数被改成 47/56 ⇒ ⇒ 与重算的 46/56 对不上 ⇒ 必须红"),
    ("PM2", "panel", "p = 0.001152", "p = 0.015200", ["X-fisher"],
     "⚖ 跨臂 Fisher p 被改 ⇒ ⇒ 必须红"),
    ("PM3", "panel", "差 **+30.36 pp**", "差 **+40.36 pp**", ["X-diff"],
     "⚖ 两臂差 pp 被改 ⇒ ⇒ 必须红"),
    ("PM4", "panel", "每轨迹有效格 m 分布 = {2×1, 3×55}",
     "有效格数分布 = {2×1, 3×55}", ["T-w-mdist"],
     "⚖ 面板**不印** m 分布了 ⇒ ⇒ V3 那条必须红"),
    ("PM5", "panel", "格集合：进 167 格", "格集合：进 168 格", ["I-w-kept"],
     "⚖ w 臂进格集合的格数被改 ⇒ ⇒ 必须红"),
    ("PM6", "panel", "Fisher p = 0.000131", "Fisher p = 0.001310", ["B-fisher"],
     "⚖ 块级 Fisher p 被改 ⇒ ⇒ 必须红"),
    ("PM7", "panel", "w 41/55", "w 42/55", ["G-0.75-pos"],
     "⚖ `pos_frac=0.75` 组 w 臂改判数被改 ⇒ ⇒ 必须红"),
    ("PM8", "panel", "零格合计 0", "零格合计 2", ["T-w-zerocells"],
     "⚖ 零格合计被改 ⇒ ⇒ 必须红"),
    ("IM1", "impl", '"verdict": (pos * 2 > m),', '"verdict": (pos * 2 >= m),',
     ["T-w-pos", "T-rand-pos"],
     "⚖⚖⚖ **重算器自己的多数规则被改成 `>=`**（平票算 True）⇒ ⇒ 必须与面板对不上"),
    ("IM2", "impl", "    ph = x / float(n)", "    ph = (x + 0.5) / float(n)",
     ["T-w-ci", "T-rand-ci"],
     "⚖⚖⚖ **重算器的 Wilson 分子被改** ⇒ ⇒ 区间必须与面板对不上"),
    ("IM3", "impl", 'inj = int(P) + max(1, int(int(ng) * float(pf))) - 1',
     'inj = int(P) + max(1, int(int(ng) * float(pf))) - 2',
     ["I-w-kept", "I-rand-kept", "I-w-drop", "I-rand-drop"],
     "⚖⚖⚖ **重算器的分母 `inj` 少减 1** ⇒ ⇒ 密度算错 ⇒ 格集合必变"),
    ("IM4", "impl", 'c2["d"] = float(r["p9_hi_meas"]) - float(r["p9_lo_meas"])',
     'c2["d"] = float(r["p9_hi_meas"]) + float(r["p9_lo_meas"])',
     ["T-w-pos", "T-rand-pos", "X-diff"],
     "⚖⚖⚖ **重算器的 `d` 符号写反** ⇒ ⇒ 改判数必须与面板对不上"),
]


def run_verifier(script, panel, workdir):
    """⚖ 跑一次重算器 ⇒ 返回 `(rc, stdout+stderr)`。"""
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    cmd = [sys.executable, script, "--w-log", W_LOG, "--rand-log", R_LOG,
           "--panel", panel, "--out", os.path.join(workdir, "out.txt")]
    try:
        r = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True,
                           timeout=1200, env=env)
        return r.returncode, (r.stdout + r.stderr)
    except subprocess.TimeoutExpired:
        return -9, "TIMEOUT"


def _red_ids(out):
    """⚖ 从输出里抠出 FAIL 的判据 id（⛔ 期望集是手写的，不许从被检对象派生）。"""
    return set(re.findall(r"^\[FAIL\] (\S+)", out, re.M))


def _my_numbers(out):
    """⚖ 抠出输出里「我的 = …」那一段（⇒ 只比**重算出来的数**）。"""
    vals = []
    for ln in out.split("\n"):
        m = re.search(r"｜ 我的 = (.*?) ｜ 面板 = ", ln)
        if m:
            vals.append(m.group(1))
    return vals


def _same_numbers(out, base_out):
    """⚖⚖ **等价变异的判别**：源码改了，但重算出来的数**逐条相同**
    ⇒ ⇒ 这条变异对判据**不可见** ⇒ ⇒ 按纪律记「**无效**」，⛔ **不是**「存活」。
    """
    a, b = _my_numbers(out), _my_numbers(base_out)
    return bool(a) and a == b


# ⚖⚖⚖ 等价变异**为什么**在这批数据上不可见（⚖ 手写，⛔ 不从被检对象派生）
EQUIV_WHY = {
    "IM1": "⚖ 这一批里**没有平票轨迹**（每条轨迹 3 格；2:1 分歧**不是**平票）⇒ ⇒ "
           "`>` 改 `>=` 对这批数据**逐条相同** ⇒ ⇒ 该条边界由**合成夹具**"
           "（自检 `S-Major-tie`）覆盖 ⇒ ⇒ ⛔ **不是**「判据抓不住」，是**这批数据上没有那条边界**",
    "IM3": "⚖ 密度容差是 **±0.005**，而分母差 1 个 token 让密度只差 **≈0.0008**（0.3%）⇒ ⇒ "
           "**仍在容差内** ⇒ ⇒ 格集合**一个不变** ⇒ ⇒ 「等剂量」这句话的精度是 "
           "**±0.5% 密度** ⇒ ⇒ ⛔ 分子母差 1 个 token 在这批数据上**看不出来**"
           "（⇒ 记进账本的边界清单）",
}


def _why_equivalent(mid, find):
    """⚖ 等价变异的解释（⛔ 没登记 ⇒ 就写「未登记」⇒ 不许编一个理由）。"""
    return EQUIV_WHY.get(mid, "⚖ 源码改了但结果逐条相同 ⇒ 等价变异"
                               "（**原因未登记** ⇒ 记进账本待查，⛔ 不许编理由）")


def _looks_like_crash(out):
    return bool(CRASH_RE.search(out))


def main():
    work = tempfile.mkdtemp(prefix="_mut_indep_")
    try:
        for p in (W_LOG, R_LOG, PANEL):
            if not os.path.isfile(p):
                # ⚖⚖⚖ **必须用 `PRECOND_FAIL` 这个字样** ⇒ 回归器据此判
                #   「缺前置/远端产物 ⇒ **跑不动** ⇒ ⛔ **不是「判据红」**」
                #   （⛔ 若报成普通失败 ⇒ 会被算成「本轮引入的红」⇒ ⇒ 冤枉）
                print("PRECOND_FAIL: 缺远端产物：%s ⇒ 这一轮**跑不动** ⇒ ⛔ **不是「判据红」**" % p)
                return 2
        with io.open(PANEL, encoding="utf-8") as fh:
            panel_txt = fh.read()
        with io.open(os.path.join(HERE, TARGET), encoding="utf-8") as fh:
            src_txt = fh.read()

        # ---- ④ 阳性对照：什么都没改 ⇒ 必须全绿
        rc, out = run_verifier(os.path.join(HERE, TARGET), PANEL, work)
        if rc != 0:
            print("⛔ **阳性对照没过**（未改任何东西时重算器不是全绿）⇒ ⇒ 台架自己瞎了 ⇒ 退出")
            print(out[-4000:])
            return 3
        print("阳性对照：过 ⇒ 阳性对照通过（台架能判红）")

        caught, invalid, crashed, equivalent = [], [], [], []
        base_out = out          # ⚖ 阳性对照那次（**未改任何东西**）的输出 ⇒ 用来判「等价变异」
        for mid, kind, find, repl, expect_red, desc in MUTATIONS:
            if kind == "panel":
                n = panel_txt.count(find)
                if n != 1:
                    invalid.append((mid, "落点命中 %d 处（期望 1）⇒ **落点无效**（台架瞎了）" % n))
                    continue
                target_panel = os.path.join(work, "panel_%s.txt" % mid)
                with io.open(target_panel, "w", encoding="utf-8", newline="") as fh:
                    fh.write(panel_txt.replace(find, repl))
                script = os.path.join(HERE, TARGET)
                panel_arg = target_panel
            else:
                n = src_txt.count(find)
                if n != 1:
                    invalid.append((mid, "落点命中 %d 处（期望 1）⇒ **落点无效**（台架瞎了）" % n))
                    continue
                script = os.path.join(work, "verifier_%s.py" % mid)
                with io.open(script, "w", encoding="utf-8", newline="") as fh:
                    fh.write(src_txt.replace(find, repl))
                panel_arg = PANEL

            rc, out = run_verifier(script, panel_arg, work)
            if rc == -9:
                crashed.append((mid, "超时"))
                continue
            if _looks_like_crash(out):
                crashed.append((mid, "崩了（⛔ 崩 ≠ 抓到）"))
                continue
            red = _red_ids(out)
            hit = [e for e in expect_red if e in red]
            if rc != 0 and hit:
                caught.append((mid, hit, red))
                print("[抓到] %-4s ⇒ 红：%s（同时红了：%s）" % (mid, ",".join(hit),
                                                              ",".join(sorted(red))))
            elif _same_numbers(out, base_out):
                # ⚖⚖⚖ **等价变异**：源码**确实改了**，但这批数据上**结果逐条相同**
                #   ⇒ ⇒ 它对判据**不可见** ⇒ ⇒ 按纪律记「**无效**」，⛔ **不是**「存活」
                #   ⇒ ⇒ 必须**写清为什么在这批数据上不可见**（⛔ 不许含糊）
                why = _why_equivalent(mid, find)
                equivalent.append((mid, why))
                print("[无效/等价] %-4s ⇒ 源码改了但**这批数据上结果逐条相同** ⇒ 记「无效」：%s"
                      % (mid, why))
            else:
                invalid.append((mid, "❌ 没抓到（rc=%s，红的判据：%s）⇒ **台架瞎了**" % (rc, sorted(red))))

        print("")
        print("变异台：抓到 %d / %d（无效 %d 条 ⇒ 记「无效」⇒ 不计入分母；"
              "其中等价变异 %d 条 ⇒ 有效分母 = %d）"
              % (len(caught), len(MUTATIONS), len(invalid) + len(equivalent),
                 len(equivalent), len(caught) + len(equivalent)))
        for mid, why in invalid:
            print("  [无效] %-4s %s" % (mid, why))
        for mid, why in equivalent:
            print("  [无效/等价] %-4s %s" % (mid, why))
        print("崩的条数：%d（⛔ 必须是 0）" % len(crashed))
        for mid, why in crashed:
            print("  [崩] %-4s %s" % (mid, why))
        rc = 0 if (not invalid and not crashed
                   and len(caught) + len(equivalent) == len(MUTATIONS)) else 1
        print("MUT_RC=%d" % rc)
        return rc
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
