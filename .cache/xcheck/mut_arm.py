#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第三十三笔之四 W 组变异台：证明 W0–W6 每一条都有牙。

M-R 是本轮那个**真缺陷**的回归测试：
页面在每张 post 卡末尾说「…下文略，原文还有 M 字符…」，
实测印 7203 而正确值是 7143 —— 多算了整整一个 `split_char`。
把修复退回去，W2 必须报红。

其余五个分别打 W1 / W3 / W4 / W5 / W6。
每个变异只改一处，改完逐字节还原并校验 sha256。
"""
import hashlib
import io
import os
import re
import shutil
import subprocess
import sys

ROOT = "/Users/zhourui/code/steer3d"
PAGE = os.path.join(ROOT, "frontend/public/latent/index.html")
JUDGE = os.path.join(ROOT, ".cache/browser_verify/verify_latent_prose.mjs")
URL = os.environ.get("LAT_URL", "http://127.0.0.1:22208/latent/index.html")
W = ["W0", "W1", "W2", "W3", "W4", "W5", "W6"]


def sha(p):
    return hashlib.sha256(io.open(p, "rb").read()).hexdigest()


def rd(p):
    return io.open(p, encoding="utf-8").read()


def wr(p, s):
    io.open(p, "w", encoding="utf-8").write(s)


def sub_once(s, old, new, tag):
    if old not in s:
        raise SystemExit("%s 没匹配上 —— 源码变了？" % tag)
    if s.count(old) != 1:
        raise SystemExit("%s 匹配到 %d 处（应恰好 1 处）" % (tag, s.count(old)))
    return s.replace(old, new, 1)


# ------------------------------------------------------------------ 变异
def m_r(p):
    """退回归档修复：调用处不再传真实起点 ⇒ 「原文还有 M 字符」重新多算 split_char。"""
    s = rd(p)
    s = sub_once(s,
        "    it.zero, show(hinge(it.split.zero)[1], it.split.zero, it.zero.chars,\n"
        "                  (it.split.zero.start || 0) + (it.split_char || 0)),\n",
        "    it.zero, show(hinge(it.split.zero)[1], it.split.zero, it.zero.chars),\n",
        "M-R/post:zero")
    s = sub_once(s,
        "    it.steered, show(hinge(it.split.steered)[1], it.split.steered, it.steered.chars,\n"
        "                      (it.split.steered.start || 0) + (it.split_char || 0)),\n",
        "    it.steered, show(hinge(it.split.steered)[1], it.split.steered, it.steered.chars),\n",
        "M-R/post:steered")
    wr(p, s)


def m_s(p):
    """把印出来的分岔位置换成写死的 180 —— 正是源码注释里记着的那个历史 bug。"""
    s = rd(p)
    wr(p, sub_once(s, "第 ${it.split_char} 个字符</b>才分岔", "第 180 个字符</b>才分岔", "M-S"))


def m_t(p):
    """把 VD 表里两个方向性类别的措辞对调 ⇒ 方向读反了。"""
    s = rd(p)
    s = sub_once(s, '"right->wrong": ["原本答对，加向量后答错了"', '"right->wrong": ["原本答错，加向量后答对了"', "M-T/a")
    s = sub_once(s, '"wrong->right": ["原本答错，加向量后答对了"', '"wrong->right": ["原本答对，加向量后答错了"', "M-T/b")
    wr(p, s)


def m_u(p):
    """删掉 tail:steered 那张臂卡 ⇒ 四张变三张。"""
    s = rd(p)
    blk = re.search(r'  h \+= armCard\("tail:steered".*?\);\n', s, re.S)
    if not blk:
        raise SystemExit("M-U 没找到 tail:steered 那个 armCard")
    wr(p, s[:blk.start()] + s[blk.end():])


def m_v(p):
    """步数 +1 ⇒ 页面印的步数与产物差 1。"""
    s = rd(p)
    wr(p, sub_once(s, "${arm.steps}</b> 步", "${arm.steps + 1}</b> 步", "M-V"))


def m_w(p):
    """两臂印同一段文字 ⇒ 逐字对照什么也没证明。"""
    s = rd(p)
    wr(p, sub_once(s, 'arm("没加向量（对照臂）", "#ff8fa3", H.after_shadow, "", "shadow")',
                   'arm("没加向量（对照臂）", "#ff8fa3", H.after_primary, "", "shadow")', "M-W"))


MUTS = [
    ("M-R", m_r, "W2"),   # 本轮那个真缺陷
    ("M-S", m_s, "W3"),
    ("M-T", m_t, "W4"),
    ("M-U", m_u, "W1"),
    ("M-V", m_v, "W5"),
    ("M-W", m_w, "W6"),
]


def run():
    env = dict(os.environ, LAT_URL=URL)
    p = subprocess.run(["node", JUDGE], cwd=os.path.dirname(JUDGE),
                       env=env, capture_output=True, text=True, timeout=420)
    out = p.stdout + p.stderr
    red = set()
    for line in out.split("\n"):
        m = re.match(r"\[FAIL\] (W\d)", line.strip())
        if m:
            red.add(m.group(1))
    tail = re.search(r"=== (\d+)/(\d+) passed ===", out)
    diag = {}
    for line in out.split("\n"):
        m = re.match(r"\[(PASS|FAIL)\] (W\d[^\n]*)\n\s+(.*)", line)
        if m and m.group(2) not in diag:
            diag[m.group(2)] = m.group(3)[:150]
    return red, (tail.group(0) if tail else "(没读到汇总行)"), diag


def main():
    only = os.environ.get("MUT_ONLY", "").strip()
    base_red, base_sum, _ = run()
    print("变异台：%s" % URL)
    print("基线：%s　W 组红=%s" % (base_sum, sorted(base_red & set(W)) or "无"))
    if base_red & set(W):
        print("⛔ 基线 W 组就已经是红的，变异台不作数，先修判据")
        return 1
    if only:
        print("（MUT_ONLY=%s）" % only)

    ok = True
    for name, fn, expect in MUTS:
        if only and name not in [x.strip() for x in only.split(",")]:
            continue
        before = sha(PAGE)
        bak = PAGE + ".mutbak"
        shutil.copy2(PAGE, bak)
        try:
            fn(PAGE)
            if sha(PAGE) == before:
                print("%s ❌ 变异没真的改到文件" % name)
                ok = False
                continue
            red, summ, diag = run()
            hit = expect in red
            extra = sorted(red - {expect})
            print("%s 期望 %s 红 → %s　%s%s"
                  % (name, expect, "✅ 红了" if hit else "❌ 没红", summ,
                     ("　（顺带红了 %s）" % extra) if extra else ""))
            if hit:
                d = next((v for k, v in diag.items() if k.startswith(expect)), "")
                if d:
                    print("     诊断：%s" % d)
            if not hit:
                ok = False
        finally:
            shutil.move(bak, PAGE)
            if sha(PAGE) != before:
                print("⛔ %s 还原失败！手工检查 %s" % (name, PAGE))
                ok = False
    print("\n%s" % ("全部变异都被抓到 ✅" if ok else "有变异没被抓到 ⛔"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
