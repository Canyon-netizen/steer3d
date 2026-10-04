#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第三十三笔之五 T 组变异台：证明 T0–T3 每一条都有牙。

T 组核的是页面自己写着的一条规则（index.html:242「术语的第一次出现必须就地有
白话解释」）—— 而这条规则**从来没有过任何判据**：`inline-gloss` 在整个 git 历史里
只出现在 c9ee868（加导读层那次提交，也就是页面自己）。

最关键的是 `M-Y`：它证明 T1 判的是「那个 gloss **自己在讲这个词**」，
而不只是「同块里有个 gloss」。把 gloss 换成讲别的词的，判据仍红。
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
T = ["T0", "T1", "T2", "T3"]


def sha(p):
    return hashlib.sha256(io.open(p, "rb").read()).hexdigest()


def rd(p):
    return io.open(p, encoding="utf-8").read()


def wr(p, s):
    io.open(p, "w", encoding="utf-8").write(s)


def sub(s, old, new, tag):
    if old not in s:
        raise SystemExit("%s 没匹配上 —— 源码变了？" % tag)
    if s.count(old) != 1:
        raise SystemExit("%s 匹配到 %d 处（应恰好 1 处）" % (tag, s.count(old)))
    return s.replace(old, new, 1)


# ------------------------------------------------------------------ 变异
def m_x(p):
    """删掉残差流那处 gloss ⇒ 回到「判决性段落里首次出现而没解释」的真违规。"""
    s = rd(p)
    wr(p, sub(s,
        '第 20 层往<i class="inline-gloss">残差流 = 模型每一道工序都往同一份草稿上加东西，那份草稿就叫残差流</i>里推',
        '第 20 层往残差流里推', "M-X"))


def m_y(p):
    """把 logit 那处 gloss 换成一个**只重复术语名、不解释**的。

    ⚠ 这是本组最关键的一条：只问「同块里有没有 gloss」的话，
      它**照样绿** —— 因为那里仍然有一个 .inline-gloss 元素。
      T1 必须红，才证明它判的是「那个 gloss 自己在讲这个词」。
    """
    s = rd(p)
    wr(p, sub(s,
        '<i class="inline-gloss">（logit = 候选词还没归一化的原始打分，只有相对大小有意义）</i>',
        '<i class="inline-gloss">（logit）</i>', "M-Y"))


def m_ac(p):
    """把残差流那处 gloss 换成一个**主语是别的词**的：形状全对，内容是假的。

    ⚠ 这是 M-X 那个漏洞的**直接**负控，两者测的不是同一件事：
      M-X  = 「把真解释整个删掉」        ⇒ 那个块上就一个 gloss 都没有
      M-AC = 「把真解释换成一个假的」    ⇒ gloss 元素**还在**、里面**还写着
             「残差流」、剥掉术语与标点后也远不止 6 个字，可它的主语是
             「干预」—— 读者在那里读到的是干预怎么干，不是残差流是什么。
    ⇒ 只问「这个 gloss 含不含这个词」的话，M-AC 照样绿（34/34）。
      必须额外问一句「它是不是**在定义**这个词」。
    """
    s = rd(p)
    wr(p, sub(s,
        '<i class="inline-gloss">残差流 = 模型每一道工序都往同一份草稿上加东西，'
        '那份草稿就叫残差流</i>',
        '<i class="inline-gloss">干预 = 人为往残差流里推一把</i>', "M-AC"))


def m_z(p):
    """把「干预 / 对照」那一项的「在哪儿看」清空 ⇒ 读者来了不知道去哪找。"""
    s = rd(p)
    wr(p, sub(s,
        '<span class="where">在哪儿看：左边第 4 个按钮「干预 vs 对照」，'
        '绿色那条线是干预，灰色那条是对照。</span>',
        '<span class="where"></span>', "M-Z"))


def m_aa(p):
    """把术语表点名的一个控件改掉名字 ⇒ 「在哪儿看」指了个不存在的东西。

    ⚠⚠ 这一条**换过目标**。原来改的是「当前 token」那个 label，
      连踩三个「同名副本」，所以它从一开始就打不到 T3：
        :286  术语表第 2 项自己写着「当前 token」  ← 被判的那句话本身
        :276  浮层内导读文案也写着「当前 token」滑块
        :403  图例里**另有一个**「当前 token」色块    ← 真正的拦路虎
      前两个由「T3 的匹配集排除 #orientation 浮层」修掉；
      第三个是**真实的另一个控件** —— 读者在图例上看到的确实还是
      「当前 token」，所以判据不红是**对的**，是这条变异选错了控件。
      ⇒ 换成「PC1/PC2 轴」（:408）：纯静态 span、JS 不重写、
        术语表第 6 项点名了它、页面上再没有第二处。

    ⚠ 顺带记下 T3 的另一个已知局限：它只查**文字节点**，
      所以画在 canvas 上的字（:1290 的「每一步的位移 Δ」）它查不到。
      那一项是「查不到就可能误报」，方向与本次相反，且不影响本条的判定。
    """
    s = rd(p)
    wr(p, sub(s, '<i style="background:#ff6b81"></i>PC1/PC2 轴</span>',
              '<i style="background:#ff6b81"></i>PC1/PC2 方向</span>', "M-AA"))


def m_ab(p):
    """让 #orientation 永远展不开 ⇒ 这一整层对读者不存在。"""
    s = rd(p)
    wr(p, sub(s, '<div id="orientation" class="hide">',
              '<div id="orientation" class="hide" style="display:none!important">',
              "M-AB"))


MUTS = [
    ("M-X", m_x, "T1"),
    ("M-Y", m_y, "T1"),
    ("M-AC", m_ac, "T1"),
    ("M-Z", m_z, "T2"),
    ("M-AA", m_aa, "T3"),
    ("M-AB", m_ab, "T0"),
]


def run():
    env = dict(os.environ, LAT_URL=URL)
    p = subprocess.run(["node", JUDGE], cwd=os.path.dirname(JUDGE),
                       env=env, capture_output=True, text=True, timeout=500)
    out = p.stdout + p.stderr
    red = set()
    for line in out.split("\n"):
        m = re.match(r"\[FAIL\] (T\d)", line.strip())
        if m:
            red.add(m.group(1))
    tail = re.search(r"=== (\d+)/(\d+) passed ===", out)
    diag = {}
    for line in out.split("\n"):
        m = re.match(r"\[(PASS|FAIL)\] (T\d[^\n]*)\n\s+(.*)", line)
        if m and m.group(2) not in diag:
            diag[m.group(2)] = m.group(3)[:170]
    return red, (tail.group(0) if tail else "(没读到汇总行)"), diag


def main():
    only = os.environ.get("MUT_ONLY", "").strip()
    base_red, base_sum, _ = run()
    print("变异台：%s" % URL)
    print("基线：%s　T 组红=%s" % (base_sum, sorted(base_red & set(T)) or "无"))
    if base_red & set(T):
        print("⛔ 基线 T 组就已经是红的，变异台不作数，先修判据")
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
