# -*- coding: utf-8 -*-
"""
U 组变异台：导读「用页面上真实的数字走一遍」。

## 这一组为什么必须自己写一个台子

T 组的台子（mut_term.py）只认 T1/T2/T3 三条判据的红。
U 组是**新加的 9 条**，且它**自己会切模型**（U5 切 0.6B、U8 切回 1.7B），
一次跑完要 8 分钟左右，比 T 组的 5 分钟慢 ⇒ 变异台必须显式区分
「哪些红是期望的」和「哪些红是台子自己搞坏的」。

## 四条变异分别打哪几条

| 变异 | 做了什么 | 期望红 |
|---|---|---|
| M-AD | 把新措辞改回「十个机会里它选 's 七次半」 | **U4 / U7** |
| M-AE | 把 `pair()` 的 ent / top1 顺序写反 | **U3 / U5** |
| M-AF | 把导读里第 5 步的 token 从 's 改成 't | **U1 / U6** |
| M-AG | 删掉第二节的一整段（10 段 → 9 段） | **U0** |

## 为什么 M-AD 是这一组最关键的一条

它是**把页面上已经修掉的那个错数原样放回去**。
实测 1.7B 的 top1@5 = 0.7773、0.6B = 0.6776，而「七次半」= 0.75
⇒ 两个模型下都不对。

⚠ 但它同时测出 U4/U7 的一个**已知局限**：
   这两条只堵「次半」这个量词形。写「0.75 的把握」它就漏了。
   页面自己的注释（:624-629）要求的是「模型不同时不能印写死的数」，
   那是个更一般的性质，判据只测了它的一个子集 —— 文档里必须写明。

## 两条没有被任何变异覆盖的判据

- **U8**（跑完必须导航回 1.7B）：它是**判据自己的导航逻辑**，
  变异改页面碰不到它。它的负控是「U5 若不切模型则 U5 自己的
  walkTok==='384' 条件就不成立」—— 即 U5 的就绪条件已经是 U8 的半个负控。
- **U2**（top1@0 ≥ 0.99）：它是**事实层**的阈值判据，
  要打红得改产物（manifest.json），而产物是另一个账本的东西。
  变异台只改页面 ⇒ 明确记录它在本台子下不可测。
"""
import hashlib
import io
import os
import re
import subprocess
import sys

ROOT = "/Users/zhourui/code/steer3d"
PAGE = os.path.join(ROOT, "frontend/public/latent/index.html")
JUDGE = os.path.join(ROOT, ".cache/browser_verify/verify_latent_prose.mjs")
URL = os.environ.get("LAT_URL", "http://127.0.0.1:22208/latent/index.html")
EXPECT = ["U0", "U1", "U2", "U3", "U4", "U5", "U6", "U7", "U8"]


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
def m_ad(p):
    """把修好的措辞原样改回「十个机会里它选 's 七次半」。

    ⚠ 这是**把页面上已经修掉的错数放回去**：
      实测 top1@5 是 1.7B 0.7773 / 0.6B 0.6776，而「七次半」= 0.75
      ⇒ 两个模型下都不对，U4 与 U7 都必须红。
    """
    s = rd(p)
    wr(p, sub(s,
        "。意思是：它最有把握写 's，但远没到确定——同一行第二个数就是这个把握。",
        "。意思是十个机会里它选 's 七次半，剩下几次它在犹豫。", "M-AD"))


def m_ae(p):
    """把 pair() 的 ent / top1 顺序写反 ⇒ 页面印「0.777 / 0.530」。

    ⚠ 这是**渲染层**的变异：元素在、格式对、两个数也都在，
      只是反了顺序 ⇒ 只比「有没有两个小数」的判据照样绿。
    """
    s = rd(p)
    wr(p, sub(s,
        '? ti.ent.toFixed(3) + " / " + ti.top1.toFixed(3) : null;',
        '? ti.top1.toFixed(3) + " / " + ti.ent.toFixed(3) : null;', "M-AE"))


def m_af(p):
    """把导读写死的第 5 步 token 从 's 改成 't。

    ⚠ 导读那两个 token 是**硬写在 HTML 里**的。换题库 / 换模型后
      它们可能不再成立，而页面不会自己发现（applyWalkthroughFacts
      只填 walkEnt 槽，不校验导读正文）。
    """
    s = rd(p)
    wr(p, sub(s,
        "步：它正在写 <b>'s</b>",
        "步：它正在写 <b>'t</b>", "M-AF"))


def m_ag(p):
    """删掉第二节的一整段 ⇒ 10 段变 9 段。

    ⚠ 这一条打的是 U0：**那 10 段没有任何 data-* 标记**，
      删掉一段不会让任何「按标记名统计覆盖」的判据报警
      —— 覆盖扫描只会少算一个它本来就没算过的块。
      只有 U0 这种「按位置枚举 + 数段数」的判据才抓得到。
    """
    s = rd(p)
    line = [l for l in s.split("\n")
            if 'L0 是每个词的出厂编号' in l]
    assert len(line) == 1, "要找的段匹配到 %d 处" % len(line)
    wr(p, sub(s, line[0], "", "M-AG"))


MUTS = [
    ("M-AD", m_ad, ["U4", "U7"]),
    ("M-AE", m_ae, ["U3", "U5"]),
    ("M-AF", m_af, ["U1", "U6"]),
    # ⚠ M-AG 会**连带**让 T1 红，这不是误伤：被删掉的那一段里放着
    #   `embedding = 查表把词变成一串数字` 这个 inline-gloss
    #   ⇒ 删掉整段等于同时删掉了那个术语在首次出现处的解释。
    #   台子的正则因此从 (U\d) 扩到 ([TU]\d) —— 不扩的话这条连带会被
    #   当成「T1 在 U 组台子上莫名其妙地红」。
    ("M-AG", m_ag, ["U0", "T1"]),
]


def run():
    env = dict(os.environ, LAT_URL=URL)
    p = subprocess.run(["node", JUDGE], cwd=os.path.dirname(JUDGE),
                       env=env, capture_output=True, text=True, timeout=1800)
    out = p.stdout + p.stderr
    red = set()
    for line in out.split("\n"):
        m = re.match(r"\[FAIL\] ([TU]\d)", line.strip())
        if m:
            red.add(m.group(1))
    tail = re.search(r"=== (\d+)/(\d+) passed ===", out)
    return red, (tail.group(0) if tail else "(没读到判据汇总 —— 崩了?)"), out


def main():
    only = os.environ.get("MUT_ONLY")
    pick = [m for m in MUTS if not only or m[0] in only.split(",")]
    # ⚠ 还原必须真的还原。我第一版把 finally 写成
    #   io.open(PAGE,"w").write(io.open(PAGE).read())  ← 自我覆盖，空操作
    # ⇒ 台子跑完页面**停在最后一个变异态**，而下一步就是提交它。
    #   教训同 run_chain 那条：装置层的「看起来做了」必须核对它真的做了。
    orig = rd(PAGE)
    base = sha(PAGE)
    bak = PAGE + ".mutbak"
    if os.path.exists(bak):
        print("⚠ 上一次台子被中断，%s 还在 —— 先还原再跑" % bak)
        wr(PAGE, rd(bak)); os.remove(bak)
    io.open(bak, "w", encoding="utf-8").write(orig)
    print("变异台：%s" % URL)

    # 基线：T 组也必须全绿，否则测的不是 U 组
    red0, sum0, out0 = run()
    print("基线：%s　U 组红=%s" % (sum0, sorted(red0) or "无"))
    if red0:
        print("⚠ 基线就不绿，先修基线再谈变异")
        for l in out0.split("\n"):
            if l.startswith("FAIL: "):
                print("   " + l)
        sys.exit(2)

    bad = []
    try:
        for name, fn, want in pick:
            # ⚠⚠ 每个变异都必须**从干净基线出发**。我第一版写成
            #   fn(PAGE) → run() → 下一个 fn(PAGE)
            # 而还原只写在 finally 里（整轮末尾一次）
            # ⇒ 变异**逐个累积**：M-AE 跑的时候页面还带着 M-AD 的文案变异，
            #   于是 U4/U7 跟着一起红，看起来像「这几条判据很敏感」，
            #   其实是上一条变异没清干净。
            #   这个 bug 不会让任何**期望**红变成不红（M-AD 是第一个跑的），
            #   所以它只污染「额外红」那一栏 —— 也就是**最容易被当成新发现**的那一栏。
            wr(PAGE, orig)
            fn(PAGE)
            red, summ, out = run()
            wr(PAGE, orig)
            got = sorted(red)
            miss = [x for x in want if x not in red]
            extra = [x for x in red if x not in want]
            flag = "✅" if not miss else "❌"
            print("%s %s 期望 %s → %s  %s" % (flag, name, want, got, summ))
            for l in out.split("\n"):
                if l.startswith("FAIL: "):
                    print("      " + l[6:][:150])
            if miss:
                bad.append(name)
            if extra:
                print("      ⚠ 额外红了（不判失败，但要记）：%s" % extra)
    finally:
        wr(PAGE, orig)
        if os.path.exists(bak):
            os.remove(bak)
        after = sha(PAGE)
        print("还原：%s（sha %s）" % ("一致 ✅" if after == base else
                                     "⚠ 不一致！", after[:12]))
    print()
    if bad:
        print("有变异没被抓到 ⛔ %s" % bad)
        sys.exit(1)
    print("全部变异都被抓到 ✅")


if __name__ == "__main__":
    main()
