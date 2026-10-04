# -*- coding: utf-8 -*-
"""
V 组变异台：导读「五 · 这些数字的边界」那 4 条声明。

## 这一组测的是什么

第三十三笔之七的普查发现：`scan_panel_coverage.py` **从不打开
`#orientation` 浮层** ⇒ C5/C6 的结论只对浮层外成立。
搬进去重跑，浮层内 20 个「C6 口径下的真孤儿」，其中 14 条子树也没有标记；
最要紧的是**「五 · 这些数字的边界」整节 4 条 `<li>`** ——
它是全页的诚实性清单，而它一条 data-* 都没有、也不在任何欠账表上。

其中第 1 条是**三重错的边界声明**：

    页面原句：只有 6 道题做过"干预 vs 对照"（题号 1983 到 1988 连续 6 道）
    产物实测：n_in_screen=10，items=10 条，
              题号 1984/1987/1990/1991/1994/2000/2004/2014/2020/2025
    ⇒ 道数错、区间错、而且根本不连续。而 1983 根本不在这一批里
      （它是 steer_directions 那 23 题的题号）。

## 四条变异

| 变异 | 做了什么 | 期望红 |
|---|---|---|
| M-AH | 第 1 条的 10 改回 6 | V1 |
| M-AI | 题号改回「1983 到 1988 连续 6 道」 | V2 |
| M-AJ | 删掉一个 data-bound 标记 | V0 |
| M-AK | 把 data-f="label" 换成静态文本 | **V5 + Z11** |

⚠ **M-AK 是这一组最关键的一条**，它测的正是 V5 自己写在名字里的那句话：
「只核 1.7B 下对是发现不了『静态兜底』的」。

把标签换成静态 "Qwen3-1.7B" 之后，**V3 仍然是绿的** ——
因为 V3 在 1.7B 下核的是「这条声明写的是不是 1.7B 的名字」，
静态文本恰好也满足。**只有切到 0.6B 的 V5 才红。**
⇒ 这一条证明「跨模型核验」不是可有可无的仪式。

## 这条变异第一次跑就把判据的毛病照出来了（先怀疑判据，别急着改页面）

第一次跑 M-AK，V5 **没红**。查下去不是页面的问题，是判据**认错了对象**：

    页面上有**两个** [data-f="label"]：声明里 :314 一个、h1 标题 :334 一个
    VBOUND 用 document.querySelector('[data-f="label"]') —— 取全页第一个
    文档序里 :314 在前 ⇒ **基线下恰好读对**
    M-AK 删掉 :314 的槽 ⇒ 取法**静默漂移到 h1** ⇒ 而 h1 照样被
    applyModelFacts()（它用的是 querySelectorAll，填**全部**槽）填成
    "Qwen3-0.6B" ⇒ V5 读到 0.6B ⇒ **假绿**

⇒ 修法：VBOUND 改成 `[data-bound="model"] [data-f="label"]`（限定宿主），
  并把全页槽数一起带出来，好让红的时候能指出「它漂到哪去了」。
⇒ **教训：同一属性值有多个宿主时，「第一个匹配」不是判据想要的那个，
  而且它会在变异下自己换人。判据要按宿主元素定位，不是按属性值定位。**

同一次跑还带出 M-AJ 的额外红 V5，根因同类：V5 的就绪循环里藏着
`vB6.n === 4` —— 那是 **V0 的条件**（4 条声明都在）。于是删一条标记就把
V5 一起带红，看着像 V5 也依赖那条声明，其实只是就绪条件抄了 V0 的。
⇒ 判据里不该藏与别的判据重复的条件（第三十三笔之七第 ⑤ 条）。

## 三条没有被任何变异覆盖的判据

- **V3 / V4** 是**事实层**核（models.json 的层数与宽度、steer_directions.json
  的 layer/strength）。要打红得改产物 JSON，而产物是另一个账本的东西。
- **V6** 是**判据自己的导航逻辑**（跑完切回 1.7B），变异改页面碰不到它。
- 与第三十三笔之六的 U2 / U8 同一类，如实记下，不混在「全绿」里。

## 台子自己也漏过一次：收集器的正则只认 T/U/V

第二轮跑到 M-AK 时，判据报的是 **48/50**（**两条**红：Z11 + V5），
可台子收进来的红只有 `['V5']`，于是把 Z11 报成「该红没红」。

    判据实际输出的组：T U V W X Y Z（七组）
    台子的正则：      re.match(r"\[FAIL\] ([TUV]\d)", ...)   ← 只收三组

⇒ **W 组与 Z 组的红一直被静默丢掉。** 看着像判据漏检，其实是收集器漏了 ——
  与「变异台只查期望红 ⊆ 实际红」同一族：**少算的那部分永远不会报警**。
⇒ 我是把它单独跑一遍、拿**完整**输出才查出来的：台子把 FAIL 行截到 150 字，
  而槽数信息在消息**末尾**，恰好被截掉。

⇒ 两处修法：
  1. 正则放宽成 `([A-Z]\d)`；
  2. 加护栏：`[FAIL]` **行数**必须等于收进来的红数，对不上就判失败
     （否则「又漏了一类」这件事本身还是看不见）。

### ⚠⚠ 上面那条修法**当场把自己咬了一口**（第三轮实跑才发现）

改成 `([A-Z]\d)` 之后重跑，台子报：

    ❌ M-AK 期望 ['V5', 'Z11'] → ['V5', 'Z1']

`\d` 只吃**一位**数字 ⇒ `Z11` 被收成 `Z1`。
而**第 2 条护栏照样通过**：那一轮是 2 条 `[FAIL]`、收进来 2 个，2 == 2。

⇒ **只数「有多少」，抓不出「是哪几个」。** 计数护栏证明的是
  「没有漏收」，它对「收歪了」完全无感。
⇒ 补第 3 条护栏：从判据源码反推**名册**（`rec\('([A-Z]\d+)`，50 条，
  不手抄），收进来的每个 id 必须在名册里；`Z1` 不在 ⇒ 立刻报。
⇒ 正则改 `([A-Z]\d+)`。

⚠ 三条护栏的分工，缺一条都还会再犯：
  ① 行数 == 收进来的红数   → 抓「漏收」
  ② 每个 id 在名册里        → 抓「收歪」
  ③ 基线红 = 空             → 抓「判据本身就不绿」
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
def m_ah(p):
    """道数改回 6 ⇒ V1 必须红（产物 n_in_screen=10 / items=10）。"""
    s = rd(p)
    wr(p, sub(s,
        '只有 <b>10</b> 道题做过"干预 vs 对照"',
        '只有 <b>6</b> 道题做过"干预 vs 对照"', "M-AH"))


def m_ai(p):
    """题号改回「1983 到 1988 连续 6 道」⇒ V2 必须红。"""
    s = rd(p)
    wr(p, sub(s,
        '（题号 1984 到 2025，<b>不连续</b>；',
        '（题号 1983 到 1988 连续 6 道；', "M-AI"))


def m_aj(p):
    """删掉一个 data-bound 标记 ⇒ V0 必须红。"""
    s = rd(p)
    wr(p, sub(s, ' data-bound="summary"', '', "M-AJ"))


def m_ak(p):
    """把 data-f="label" 槽换成静态文本 ⇒ **V5** 必须红，而 V3 仍绿。"""
    s = rd(p)
    wr(p, sub(s,
        '<b data-f="label">Qwen3-1.7B</b>',
        '<b>Qwen3-1.7B</b>', "M-AK"))


MUTS = [
    ("M-AH", m_ah, ["V1"]),
    ("M-AI", m_ai, ["V2"]),
    ("M-AJ", m_aj, ["V0"]),
    # ⚠ M-AK 额外**不该**让 V3 红 —— 它绿才对（静态文本恰好满足 1.7B 下
    #   「这条声明写的就是 1.7B 的名字」）。若 V3 也红了，
    #   说明 V3 与 V5 判的是同一件事，那 V5 就是多余的。
    #
    # ⚠ Z11 也要红，而且是**该红**：它断言 `slotN === 14`（页面上 [data-f] 槽
    #   必须有 14 个），而 M-AK 恰好把其中一个换成了静态文本 ⇒ 13 个。
    #   第一次跑时它没被声明，台子打了「⚠ 额外红了（不判失败，但要记）」。
    #   那不是污染，是**漏声明**——把真检出当噪声，正是变异表该有的纪律。
    ("M-AK", m_ak, ["V5", "Z11"], {"must_not": ["V3"]}),
]


# 判据自己的名册（从判据源码反推，**不手抄**）。
# 用途：台子每收一个红，都要能在名册里找到它。
# ⚠ 这条护栏是被一次真实的自伤逼出来的：
#   我把收集正则从 `([TUV]\d)` 放宽成 `([A-Z]\d)` —— 组字母对了，
#   `\d` 却只吃**一位**数字 ⇒ `Z11` 被收成 `Z1`，`Z10` 被收成 `Z1`。
#   而上一条护栏（`[FAIL]` 行数 == 收进来的红数）照样通过：2 条对 2 条。
#   ⇒ **只数「有多少」抓不出「是哪几个」。**
#   名册校验抓的是后者：Z1 不在名册里（Z 组是 Z5..Z11）⇒ 立刻报。
JUDGE_IDS = set(re.findall(
    r"rec\('([A-Z]\d+)", io.open(JUDGE, encoding="utf-8").read()))
assert JUDGE_IDS, "判据里一条 rec('X# 都没解析到 —— 名册是空的，台子不能出结论"


def run():
    env = dict(os.environ, LAT_URL=URL)
    p = subprocess.run(["node", JUDGE], cwd=os.path.dirname(JUDGE),
                       env=env, capture_output=True, text=True, timeout=2400)
    out = p.stdout + p.stderr
    red = set()
    # ⚠⚠ 这里原来写的是 `([TUV]\d)` —— **只收 T/U/V 三组**。
    #   而判据实际会输出 T U V W X Y Z **七组**
    #   ⇒ W 组与 Z 组的红**一直被静默丢掉**。
    #   后果实测得到过一次：M-AK 那轮判据是 48/50（**两条**红：Z11 + V5），
    #   台子却只认出一条，报成「期望 Z11 → 该红没红」。
    #   看着像判据漏检，其实是**收集器自己漏了**——
    #   与「变异台只查期望红 ⊆ 实际红」同一族：少算的那部分永远不会报警。
    failLines = 0
    for line in out.split("\n"):
        m = re.match(r"\[FAIL\] ([A-Z]\d+)", line.strip())   # ⚠\d+ 不是 \d
        if m:
            red.add(m.group(1))
        if line.strip().startswith("[FAIL] "):
            failLines += 1
    tail = re.search(r"=== (\d+)/(\d+) passed ===", out)
    summ = tail.group(0) if tail else "(没读到判据汇总 —— 崩了?)"
    # 两条护栏，缺一不可：
    #   ① `[FAIL]` **行数**必须等于收进来的红数 —— 抓「漏收」（少算的永远不报警）
    #   ② 每个 id 必须在**名册**里         —— 抓「收歪」（`\d` 只吃一位 ⇒ Z11→Z1）
    # ① 单独不够：上面那次自伤里 2 条对 2 条，① 通过而 ② 才报出来。
    dropped = failLines - len(red)
    unknown = sorted(x for x in red if x not in JUDGE_IDS)
    if dropped:
        summ += "　⚠⚠ 有 %d 条 [FAIL] 没被收进 red（收集器又有漏的）" % dropped
    if unknown:
        summ += "　⚠⚠ 收进来但不在判据名册里的 id：%s（收集器收歪了）" % (
            "、".join(unknown))
    return red, summ, out, dropped, unknown


def main():
    only = os.environ.get("MUT_ONLY")
    pick = [m for m in MUTS if not only or m[0] in only.split(",")]
    orig = rd(PAGE)
    base = sha(PAGE)
    bak = PAGE + ".mutbak"
    if os.path.exists(bak):
        print("⚠ 上一次台子被中断，%s 还在 —— 先还原再跑" % bak)
        wr(PAGE, rd(bak)); os.remove(bak)
    io.open(bak, "w", encoding="utf-8").write(orig)
    print("变异台：%s" % URL)

    red0, sum0, out0, drop0, unk0 = run()
    print("基线：%s　红=%s　名册 %d 条判据" % (sum0, sorted(red0) or "无", len(JUDGE_IDS)))
    if red0 or drop0 or unk0:
        print("⚠ 基线就不绿（或收集器有漏/收歪），先修基线再谈变异")
        for l in out0.split("\n"):
            if l.startswith("FAIL: "):
                print("   " + l)
        sys.exit(2)

    bad = []
    try:
        for spec in pick:
            name, fn, want = spec[0], spec[1], spec[2]
            extra = spec[3] if len(spec) > 3 else {}
            must_not = extra.get("must_not", [])
            wr(PAGE, orig)          # 从干净基线出发（第三十三笔之六的血泪）
            fn(PAGE)
            red, summ, out, drop, unk = run()
            wr(PAGE, orig)
            got = sorted(red)
            miss = [x for x in want if x not in red]
            leak = [x for x in got if x not in want]
            flag = ("✅" if not miss and not drop and not unk
                    and not [x for x in must_not if x in red] else "❌")
            print("%s %s 期望 %s → %s  %s" % (flag, name, want, got, summ))
            for l in out.split("\n"):
                if l.startswith("FAIL: "):
                    print("      " + l[6:][:150])
            if miss:
                bad.append("%s（该红没红: %s）" % (name, miss))
            if drop:
                bad.append("%s（收集器漏了 %d 条 [FAIL]）" % (name, drop))
            if unk:
                bad.append("%s（收集器收歪，不在名册里: %s）" % (name, unk))
            if [x for x in must_not if x in red]:
                bad.append("%s（不该红却红了: %s）" % (
                    name, [x for x in must_not if x in red]))
            if leak:
                print("      ⚠ 额外红了（不判失败，但要记）：%s" % leak)
    finally:
        wr(PAGE, orig)
        if os.path.exists(bak):
            os.remove(bak)
        print("还原：%s（sha %s）" % ("一致 ✅" if sha(PAGE) == base else "⚠ 不一致！",
                                     sha(PAGE)[:12]))
    print()
    if bad:
        print("有问题 ⛔ %s" % bad)
        sys.exit(1)
    print("全部变异都按预期被抓到 ✅")


if __name__ == "__main__":
    main()
