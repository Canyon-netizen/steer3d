#!/usr/bin/env python
"""Mutation bench for rerun_sign_stability.py (revision 244.22).

The tool's whole claim is "the two rounds agree".  A comparison tool that can
only ever print agreement is indistinguishable from a correct one until
something tries to make it disagree and it is watched to fail.  That is what
this file is for.

Fixtures reuse r227_kcurve._synthetic (the reader's OWN fixture builder) rather
than a second generator, so the log/status format is the reader's, not mine.
A PINNED header and one "Loading weights: 100%" line per cell are appended
because real logs carry them and the tool reads them.

⚠⚠ The two mutations that matter most:
  M1  a flipped sign in round B          -> must be CAUGHT (rc=1, named)
  M2  a small numeric change, same sign   -> the tool must STOP calling it
                                             "bit-identical / always green"
                                             and must switch to the
                                             "this IS robustness evidence"
                                             branch.
      M2 is the anti-postcard: without it the tool could print the determinism
      warning unconditionally and this bench would never notice.

Exit: 0 all behaved as required; 1 otherwise.
"""
import importlib.util
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "rerun_sign_stability.py")
READER = os.path.join(os.path.dirname(HERE), "mutbak", "r227_kcurve.py")
TMP = os.path.join(HERE, "_mut_rss")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


R = _load("r227_kcurve", READER)


def fixture(tag, gpu, mutate=None):
    log, st = R._synthetic(mutate=mutate)
    cells = st.count("\n")
    lines = log.rstrip("\n").split("\n")
    lines.insert(0, "PINNED GPU=%s  CELLS=x  ARM=rand  00:00:00" % gpu)
    for _ in range(cells):
        lines.append("Loading weights: 100%|##########| 311/311 [00:00<00:00, 1it/s]")
    path = os.path.join(TMP, "%s.log" % tag)
    spath = os.path.join(TMP, "%s_status.txt" % tag)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    with open(spath, "w", encoding="utf-8") as fh:
        fh.write(st)
    return path, spath


def run(args):
    p = subprocess.run([sys.executable, TOOL] + args, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def pair(tag_a, a, tag_b, b):
    return ["--a-label", tag_a, "--a-log", a[0], "--a-status", a[1],
            "--b-label", tag_b, "--b-log", b[0], "--b-status", b[1]]


RESULTS = []


def record(name, ok, why=""):
    RESULTS.append((name, ok, why))
    print("  %-5s %s%s" % ("ok" if ok else "BAD", name, ("  -- " + why) if why else ""))


def main():
    os.makedirs(TMP, exist_ok=True)
    for f in os.listdir(TMP):
        os.remove(os.path.join(TMP, f))

    # ---- baseline: identical rounds -------------------------------------
    a = fixture("a", "GPU-aaa")
    b = fixture("b", "GPU-bbb")
    rc, out = run(pair("A", a, "B", b))
    bit = "全部读数逐位相同" in out
    warn = "恒绿的" in out
    record("BASE 同一份数据两份日志 ⇒ 报「逐位相同」+ 印出恒绿警告",
           rc == 0 and bit and warn,
           "" if (rc == 0 and bit and warn) else "rc=%d bit=%s warn=%s" % (rc, bit, warn))

    # ---- M1: flipped sign in B ------------------------------------------
    # ⚠ _synthetic's mutate hook gets LISTS, not strings.
    def flip(log, st):
        out, hit = [], 0
        for ln in log:
            if hit < 2 and '"inject_scope": "all"' in ln:
                ln = re.sub(r'"p9_lo_meas": -?[0-9.]+',
                            '"p9_lo_meas": 99.000000', ln, count=1)
                hit += 1
            out.append(ln)
        return out, st
    b1 = fixture("b1", "GPU-bbb", mutate=flip)
    rc, out = run(pair("A", a, "B", b1))
    caught = rc == 1 and "符号相反" in out
    record("M1 B 轮符号翻转 ⇒ rc=1 且指名「符号相反」（检查能红）",
           caught, "" if caught else "rc=%d" % rc)

    # ---- M2: same sign, different number --------------------------------
    def tweak(log, st):
        out = []
        for ln in log:
            ln = re.sub(r'"p9_lo_meas": (-?[0-9.]+)',
                        lambda m: '"p9_lo_meas": %.6f' % (float(m.group(1)) + 0.01),
                        ln, count=1)
            out.append(ln)
        return out, st
    b2 = fixture("b2", "GPU-bbb", mutate=tweak)
    rc, out = run(pair("A", a, "B", b2))
    no_bit = "全部读数逐位相同" not in out
    said_rob = "这才是稳健性证据" in out
    still_warn = "恒绿的" in out
    record("M2 读数不同但符号全同 ⇒ 必须说「这才是稳健性证据」且⛔不再印恒绿",
           rc == 0 and no_bit and said_rob and not still_warn,
           "" if (rc == 0 and no_bit and said_rob and not still_warn)
           else "rc=%d bit=%s rob=%s warn=%s" % (rc, no_bit, said_rob, still_warn))

    # ---- gates ----------------------------------------------------------
    rc, out = run(pair("A", a, "B", a))
    record("G0 同一文件比两次 ⇒ md5 相同 ⇒ 硬失败「同一份文件」",
           rc != 0 and "同一份文件" in out, "" if rc != 0 else "rc=%d" % rc)

    def other_arm(log, st):
        return [ln.replace('"arm": "rand"', '"arm": "w"') for ln in log], st
    b3 = fixture("b3", "GPU-bbb", mutate=other_arm)
    rc, out = run(pair("A", a, "B", b3))
    record("G1 两轮 arm 不同 ⇒ 硬失败并指向 arm_verdict.py",
           rc != 0 and "arm_verdict" in out, "" if rc != 0 else "rc=%d" % rc)

    def other_pf(log, st):
        return [ln.replace('"pos_frac": 0.5', '"pos_frac": 0.25') for ln in log], st
    b4 = fixture("b4", "GPU-bbb", mutate=other_pf)
    rc, out = run(pair("A", a, "B", b4))
    record("G2 B 轮 pos_frac 不同 ⇒ 硬失败「扫描参数不同」",
           rc != 0 and "扫描参数不同" in out, "" if rc != 0 else "rc=%d" % rc)

    rc, out = run(pair("A", a, "B", fixture("b5", "GPU-bbb")))
    record("G3 正常两轮 ⇒ rc=0（对照：闸不会误伤）", rc == 0, "" if rc == 0 else "rc=%d" % rc)

    # ---- the GPU-unknown branch must not read as "same" NOR as "different" --
    # ⚠ Two DIFFERENT logs (gate 0 needs distinct md5), both lacking PINNED.
    # ⚖ An earlier version compared one file to itself; gate 3 fired first on
    # ⚖ equal md5 and the GPU branch was never reached -- fixture measured
    # ⚖ the wrong gate, same shape of mistake as B4 earlier.
    def tweak2(log, st):
        out = []
        for ln in log:
            ln = re.sub(r'"p9_lo_meas": (-?[0-9.]+)',
                        lambda m: '"p9_lo_meas": %.6f' % (float(m.group(1)) + 0.01),
                        ln, count=1)
            out.append(ln)
        return out, st
    def strip_pinned(log, st):
        return [ln for ln in log if not ln.startswith("PINNED ")], st

    def fixture_nopin(tag, mutate):
        p, s = fixture(tag, "GPU-x", mutate=mutate)
        text = open(p, encoding="utf-8").read()
        text = "\n".join(ln for ln in text.split("\n")
                         if not ln.startswith("PINNED ")) + "\n"
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)
        return p, s

    c1 = fixture_nopin("c1", None)
    c2 = fixture_nopin("c2", tweak2)
    rc, out = run(pair("C", c1, "D", c2))
    # ⚠⚠⁴ Match the CONCLUSION line, not a keyword anywhere in the text.
    # ⚖ First version searched for "同一张卡" and it matched the tool's own
    # ⚖ warning ("⛔ 不许把「未量到」读成「同一张卡」") -- the bench measured
    # ⚖ its own grep, not the tool's verdict.  The verdict is the line that
    # ⚖ starts with "⚖ 两轮 GPU"; there are exactly three possible texts.
    verdict_lines = re.findall(r"^\s*\S* 两轮 GPU.*$", out, re.M)
    unknown = any("未量到" in v for v in verdict_lines)
    said_same = any("相同" in v for v in verdict_lines)
    said_diff = any("不同物理卡" in v for v in verdict_lines)
    record("G4 无 PINNED ⇒ 结论行印「未量到」；⛔不得断言同卡或异卡",
           unknown and not said_same and not said_diff and len(verdict_lines) == 1,
           "" if (unknown and not said_same and not said_diff and len(verdict_lines) == 1)
           else "rc=%d verdict_lines=%r" % (rc, verdict_lines))

    bad = [r for r in RESULTS if not r[1]]
    print("\n" + "-" * 70)
    print("caught=%d bad=%d total=%d" % (len(RESULTS) - len(bad), len(bad), len(RESULTS)))
    if bad:
        print("⛔ 没按预期表现：")
        for r in bad:
            print("   %s  %s" % (r[0], r[2]))
        return 1
    print("⚖ rc=0 只读作「所有**能**被本台架分辨的变异都抓住了」，不是「没有洞」")
    return 0


if __name__ == "__main__":
    sys.exit(main())
