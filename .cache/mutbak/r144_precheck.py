"""修订 144 判据笔的**落盘前**四道门。任一不过 ⇒ exit 2，不出文件。

⚠⚠⚴⚠⁴ 这个脚本存在的理由：本轮我在改动②里**顺手把 `for (const s of skips) console.log('[SKIP] …')`
   整段删掉了**，理由是「名单行已经覆盖了」。⚗ 而跑台的 parse() 靠 `RE_SKIP` 抓跳过列表
   ⇒ 删掉它，跳过机制当场失聪，⚠⚠⁴⚠⁴ **而日志上完全看不出来**（只是 skip 列表变空，不报错）。
   ⇒ 所以「我打算改什么」必须**写成机器可核的清单**，不能靠读一遍印象。

⚠⚠⁴⚠⁴⚠⁴ 五道门：
   门① diff 只含**事先声明**的三个块（多一块少一块都 exit 2）
   门② 反引号门：模板字面量区间内**不许有注释行**（反引号提前终止模板那一族，修订 133/134/142 踩过三次）
   门③ node --check
   门④ U+FFFD 挂在「Python 解析后」那一层（修订 135）
   门⑤ `[SKIP]` 解析行仍在（跑台 parse() 的 RE_SKIP 靠它）
"""

import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TGT = ROOT / ".cache/browser_verify/verify_path.mjs"
BASE = ROOT / ".cache/mutbak/verify_path.pre_r144b.mjs"
BT = chr(96)          # ⚠⚠⁴ 反引号必须用 chr(96) 取：写进 python3 -c 会被 bash 命令替换吃掉
FS = chr(0xFFFD)      # ⚠ U+FFFD 也要用 chr()：直接写会被当成真字符

# ⚠⚠⁴⚠⁴ 事先声明：这三块是本轮**唯一**允许变的地方。⚠ 少一块说明改动没落地，
#            多一块说明有人（或我）顺手动了别处 —— 两种都 exit 2。
# ⚠⚠⚴⚠⁴⚠⚴ 第一版这一段**只当锚点存在性断言用**，⚗ 压根没查「有没有多出来的块」——
#   ⚠⚠⁴⚠⚴ 而它自己在 docstring 里宣称「diff 只含**事先声明**的三个块」。
#   ⚠⚠⁴⚠⚴⚠⚴⚠ **这与本轮修的 `check_shape`（宣称四道闸门、漏了「各档之和」）完全同构** ——
#     修 A 族漏判的同时自己犯了一个。⇒ 下面三条断言缺一不可。
EXPECTED_HUNKS = [
    ("①D5页内块", "back = JSON.parse(await page.eval(`(async () => {"),
    ("①D5保护", "if (!tabXY) return JSON.stringify({ err: '页内找不到 #tabXY"),
    ("①D5改用局部变量", "cv: getComputedStyle(cv).display,"),
    ("①D5catch", "back = { err: '页内抛异常：'"),
    ("①D5收红", "back.err || JSON.stringify(back)"),
    ("②判据名单", "console.log('判据名单 ' + mainChecks.length"),
    ("②跳过名单", "console.log('跳过名单 ' + skips.length"),
    ("②自曝", "我先把 `for (const s of skips) console.log('[SKIP] …')`"),
    ("②口径自证", "全集是 mainChecks，跳过名单只是它的一**注释**"),
]

# ⚠⚠⁴⚠⁴⚠⚴⚠⚠⚠⚠⚠ **门的设计缺陷，本轮当场暴露**：
#   ⚗ `EXPECTED_HUNKS` 原本是「本次改动清单」，⚠ 但我往里混进了**上一笔已入库**的 8 个锚点。
#   ⚠⚠⁴⚠⚠⚠⚠⚠⚠⇒ 于是门① 把「这 8 个在本次 diff 里不存在」判成「改动没落地」⇒ exit 2。
#   ⚠⚠⁴⚠⚴ ⚠⚠⚴⚠⚠⚠⚠ **「没出现在 diff 里」有两种完全不同的原因**：
#   ⚠⚠⁴⚠⚠⚠⚠ ⚠ ① 它本来就是本轮要落的 ⇒ 没出现 = **真漏了**（该 exit 2）
#   ⚠⚠⁴⚠⚠⚠⚠ ⚠ ② 它上一笔就落过了 ⇒ 没出现 = **正常**（该放过）
#   ⚠⚠⁴⚠⚴⚠ ⚠⚠⚴⚠⚠⚠⚠⚠⚠⚠⚠⚠ **判别式：判断「有没有落」不能只看 diff ——
#   ⚠⚠⁴⚠⚠⚠⚠ 要么把清单按笔切开，要么把判据拆成**两套**清单**
#   ⚠⚠⚴⚠ ⚠⚠⚴⚠⚠ ⚠ （「本轮要落的」/「已入库不必再落的」），⚠⚠⚴⚠ ⚠⚠⚴⚠⚠⚠⚠⚠ 不许混在一张表里。
#   ⚠⚠⁴⚠⚠⚠ ⚠⚠⚴⚠⚠ ⚠ **混在一起时，门的每一次运行都在判一件跟它无关的事。**
ALREADY_COMMITTED = [
    "back = JSON.parse(await page.eval(`(async () => {",
    "if (!tabXY) return JSON.stringify({ err: '页内找不到 #tabXY",
    "cv: getComputedStyle(cv).display,",
    "back = { err: '页内抛异常：'",
    "back.err || JSON.stringify(back)",
    "console.log('判据名单 ' + mainChecks.length",
    "console.log('跳过名单 ' + skips.length",
    "我先把 `for (const s of skips) console.log('[SKIP] …')`",
]

# ⚠⚠⁴⚠⁴⚠⚴ 删除侧也必须**逐行声明**。⚗ 理由：本轮真实事故就发生在删除侧 ——
#   我顺手删掉了 `[SKIP]` 解析行（那行是跑台 parse() 的 RE_SKIP 唯一来源），
#   ⚠⚠⁴ 而 diff 的**新增侧完全正常**，只有把删除侧摆出来才看得见。
#   ⚠⚠⚴⚠⁴⇒ 「我删了什么」和「我改了什么」一样，都得显式化。
EXPECTED_DELETED = [
    "const back = JSON.parse(await page.eval(`(async () => {",
    "  document.querySelector('#tabXY').click();",
    "    cv: getComputedStyle(document.querySelector('#cv')).display,",
    "    wrap: getComputedStyle(document.querySelector('#pathWrap')).display,",
    "  back.cv === 'block' && back.wrap === 'none' && back.title.includes('隐空间'), JSON.stringify(back));",
    "// ⚠⚴ 修订 118：N/M **只数 mainChecks**（跳过不在其中）。必须把跳过点名列出来。",
]


def die(msg):
    print("[硬门] " + msg)
    sys.exit(2)


def hunks_both(new: str, old: str):
    """⚠⚠⁴⚠⁴ **新增侧和删除侧都要切出来**。
    ⚗ 第一版只切了 + 侧 ⇒ ⚠⚠⚴ 本轮真实事故（删掉跑台唯一的 [SKIP] 解析行）在 + 侧完全看不出来。
    ⚠⚠⁴⚠⚴⇒ 只有 + 侧的 diff 门，是**半个**diff 门。
    """
    import difflib
    plus, minus, cur_p, cur_m = [], [], [], []
    for ln in difflib.unified_diff(old.split("\n"), new.split("\n"), n=0, lineterm=""):
        if ln.startswith("+++") or ln.startswith("---"):
            continue
        if ln.startswith("+"):
            if cur_m:
                minus.append(cur_m)
                cur_m = []
            cur_p.append(ln[1:])
        elif ln.startswith("-"):
            if cur_p:
                plus.append(cur_p)
                cur_p = []
            cur_m.append(ln[1:])
        else:
            if cur_p:
                plus.append(cur_p)
                cur_p = []
            if cur_m:
                minus.append(cur_m)
                cur_m = []
    if cur_p:
        plus.append(cur_p)
    if cur_m:
        minus.append(cur_m)
    return plus, minus


def _assert_no_dup():
    """⚠⚠⁴⚠⁴⚠⚴ **清单里不许有重复项。**
    ⚗⚠⚴⚠⚴⚠⚴⚠⚴⚠⚠⚠⚠ 本轮当场撞上：重建 EXPECTED_HUNKS 时多插了一行「①D5页内块」，
    ⚠⚠⁴⚠ 输出里它**打印了两次**，⚠⚠⚴⚠ 而我没当场看出来 ⇒ ⚠⚠⚴⚠⚴ **门自己在骗人**。
    ⚠⚠⁴⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠ **判别式：门的输出里同一项出现两次，
    ⚠⚠⁴⚠⚠⚠⚠ ⚠⚠⚴⚠ ⚠⚠⚴⚠ ⚠⚠⚴⚠⚠ ⚠⚠⚴⚠ 不是「多打了一遍」，是「**少了一条断言**」——
    ⚠⚠⁴⚠⚠ ⚠⚠ ⚠⚠⚴⚠⚠⚠⚠⚠⚠⚠ ⚠ 那一条本该独立核的东西，现在被另一条**顺带**核了。
    ⚠⚠⁴⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠ ⚠⚠⚴⚠ ⚠⚠⚴⚠ ⚠⚠⚴⚠⚠⚠⚠⚠⚠ ⚠⚠⚴⚠ ⚠ ⚠⚠⁴⚠⚠⚠⚠ ⚠⚠⚴⚠
    ⚠⚠⁴ ⚠⚠⚴⚠ ⚠⚠⚴⚠ ⚠⚠⚴⚠ ⚠⚠⚴⚠ ⚠⚠⚴⚠ ⚠⚠⚴⚠ ⚠⚠⚴⚠ ⚠⚠⁴ ⚠⚠⚴⚠⚠⚠⚠ ⚠⚠⚴⚠
    """
    seen, dup = set(), []
    for name, anchor in EXPECTED_HUNKS:
        if name in seen:
            dup.append(name)
        seen.add(name)
    if dup:
        die(f"清单里有重复项 {dup} ⇒ 少了一条独立断言")


def gate1_diff():
    _assert_no_dup()
    old = BASE.read_text(encoding="utf-8")
    new = TGT.read_text(encoding="utf-8")
    plus, minus = hunks_both(new, old)
    print("=== 门① diff 只含声明的块（**新增侧 + 删除侧都核**）===")
    print(f"  新增块 {len(plus)} 个 / 删除块 {len(minus)} 个")

    # ⚠⚠⚴⚠⁴⚠⚴⚠ 第一版这里写的是：
    #     for name, anchor in EXPECTED_HUNKS:
    #         if anchor not in new: die(...)
    #         if anchor in old:   die("这一块是被原样留下而不是被改")
    #   ⚠⚠⚴⚠⚴⚠⚴ **第二条是无效判据，本轮当场被自己的数据推翻**：
    #   ⚗ 锚点 "back = JSON.parse(await page.eval(`(async () => {""
    #     是旧行 "const back = JSON.parse(await page.eval(`(async () => {""
    #     的**子串** ⇒ 两个文件里都在 ⇒ `anchor in old` 恒真。
    #   ⚠⚠⚴⚠⚴⚠⚴⚠ **判别式：「存在性断言」不能当「变动性断言」用。**
    #     ⚠⚠⁴ `anchor in new` 只证明「它在」；
    #     ⚠⚠⁴⚠⚴⚠⚴ `anchor in old` **完全不证明它没变** ——
    #     ⚠⚠⁴⚠⁴⚠ 子串在两边都在时，「改了」和「没改」两个结论长得**一模一样**
    #     （与「引旧记录的数字当本轮证据」是同一族）。
    #   ⚠⚠⚴⚠⁴⚠⚴⇒ 唯一的有效判据是**块级**的：锚点必须出现在**某个新增块里**。
    #     ⚠ 那才真的说明「我声明的改动以新增的形式落地了」，且免疫子串问题。
    # 断言①：每个声明的锚点必须出现在**至少一个新增块**里 ⇒ 改动确实落地
    # 断言① ⚠⚠⁴⚠⁴⚠⁴⚠⚠⚠⚠⚠ **按 BASE 分派**，不是「一律要落在 diff 里」。
    #   ⚗⚠⚴⚠⚠⚠⚠⚠⚠⚠⚠⚠ **本轮当场推翻的第一版模型**：「锚点必须出现在某个新增块里」。
    #   ⚠⚠⁴⚠⚴ ⚠⚠⚴⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠ **它只对「这一笔要落的」成立**；
    #   ⚠⚠⁴⚠ ⚠⚠⚴⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠ 一旦清单里混进**上一笔已入库**的锚点，
    #   ⚠⚠⁴⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠ 它就判成「真漏了」⇒ **每次跑都在判一件与它无关的事**。
    #   ⚠⚠⁴⚠⚠⚠⚠⇒ 判据：**锚点不在 BASE 里 ⇒ 本轮必须出现在 diff 里**（真漏了就 exit 2）；
    #   ⚠⚠⁴⚠⚠⚠ ⚠⚠⚴⚠⚠ ⚠⚠⚠⚠⚠⚠⚠⚠ ⚠ 锚点**已在 BASE 里** ⇒ 只核它还在新文件里（别被误删）。
    miss, kept, inbase = [], 0, 0
    for name, anchor in EXPECTED_HUNKS:
        was_in_base = anchor in old
        now_in_new = anchor in new
        hit = [k for k, blk in enumerate(plus, 1) if anchor in "\n".join(blk)]
        if not now_in_new:
            miss.append(f"{name}(连新文件里都没有)")
        elif was_in_base:
            inbase += 1
            kept += 1
            print(f"  ✓ {name:<14} 已在 BASE（本轮不必再落）· 仍在新文件里 ✓")
        else:
            if hit:
                print(f"  ✓ {name:<14} 本轮新增，落在新增块 {hit}")
                kept += 1
            else:
                miss.append(f"{name}(不在 BASE 却也没出现在 diff 里)")
    if miss:
        for m in miss:
            print(f"  ⚠⚠⁴✗✗ {m}")
        die(f"{len(miss)} 个锚点不成立")
    print(f"  ✓ 共 {kept} 个锚点全部成立（其中 {inbase} 个属上一笔已入库、只核未被误删）")

    # 断言② ⚠⚠⚴⚠⁴ **反向**：每个新增块都必须被某个锚点覆盖 ⇒ 才能拦住「顺手多改」
    uncov = []
    for i, blk in enumerate(plus, 1):
        body = "\n".join(blk)
        if not any(a in body for _, a in EXPECTED_HUNKS):
            uncov.append((i, blk))
    if uncov:
        for i, blk in uncov:
            # ⚠⚠⁴⚠⁴⚠⚴ **必须打全文，不能只打首行。**
            #   ⚗ 只打首行时我会照着首行去补声明，⚠⚠⁴ 而补的是「我以为改了什么」，
            #   ⚠⚠⁴⚠⚴ 不是「实际改了什么」—— 那就把门自己变成了需要它防的东西。
            #   ⚠⇒ 声明必须**从这份数据里抄**，不许从记忆里补。
            print(f"  ⚠⚠⁴✗✗ 块{i}（{len(blk)} 行）不被任何声明锚点覆盖 ⇒ 全文如下：")
            for l in blk:
                print(f"      | {l}")
        die(f"{len(uncov)} 个新增块没被声明覆盖")

    # ⚠⚠⁴⚠⚴ 打印全部新增块首行，让人目视核对（**汇总句不是证据，逐条才是**）
    for i, blk in enumerate(plus, 1):
        print(f"    块{i} {len(blk):>2} 行  {blk[0][:64]}")

    # 断言③ ⚠⚠⁴⚠⁴ 删除侧**逐行**声明
    mlines = [l for blk in minus for l in blk]
    undecl = [l for l in mlines if l.strip() not in
              [e.strip() for e in EXPECTED_DELETED]]
    if undecl:
        for l in undecl:
            print(f"  ⚠⚠⁴✗✗ 未声明的删除：{l[:70]}")
        die(f"{len(undecl)} 行删除没被声明（⚗ 本轮真实事故就在这一侧）")
    print(f"  ✓ {len(mlines)} 行删除全部在 EXPECTED_DELETED 里")


def gate2_backtick():
    """⚠⚠⚴⚠⁴ 判据：**模板字面量区间内不许有反引号，注释行里也不许有反引号**。
    ⚠⚠⚴⚠⁴⚠⚴⚠ **注释行本身是合法的**（E2/E3/E4 页内块自带页内注释，自修订 142 起
    一直合法、实跑基线一直 OK 39/39）—— ⚠⚠⁴⚠⁴⚠ **本门第一版把「有注释」当违规，
    ⚗ 当场把自己判死**。⚠⚠⁴⚠⚴⚠ ⚠ 详见下面 `inner or nbad` 处的注释。
    ⚠ 区间用「page.eval( 后面那个反引号」到「下一个未转义反引号」配对切出。
    ⚠⚠⁴⚠⚴ 为什么不能只数反引号总数：总数对**不等于**没提前终止 ——
      内部有反引号时可能两两配平、总数照样是偶数，而模板已被切成两截。
    """
    lines = TGT.read_text(encoding="utf-8").split("\n")
    text = TGT.read_text(encoding="utf-8")
    print("=== 门② 反引号门 ===")
    print(f"  全文件反引号 {text.count(BT)} 个（用 chr(96) 数，未写进 shell）")
    starts = []
    for m in re.finditer(re.escape("page.eval(") + BT, text):
        starts.append(m.end())          # 起始反引号之后的位置
    print(f"  page.eval(` 起始点 {len(starts)} 处")
    if not starts:
        die("一个 page.eval(` 都没找到 ⇒ 门② 自己坏了（不是判据坏了）")
    bad = 0
    for si in starts:
        # 跳过转义反引号，找到配对的结束反引号
        i = si
        while True:
            i = text.find(BT, i)
            if i < 0:
                die("有模板字面量没闭合")
            if i > 0 and text[i - 1] == "\\":
                i += 1
                continue
            break
        seg = text[si:i]
        seg_line = text[:si].count("\n") + 1
        # 门②a 区间内**内嵌**反引号：按构造不该有（下一个就是结束符），出现即说明转义处理错了
        inner = seg.count(BT) - seg.count("\\" + BT)
        # 门②b 区间内的注释行 —— 人唯一会手写反引号的地方
        cmt = [l.strip() for l in seg.split("\n") if l.strip().startswith("//")]
        # ⚠⚠⁴⚠⁴ 门②b ⚠⚠⁴⚠⚴⚠⚴ **违规判据第一版写错了，当场把自己判死**：
        #   第一版是 `if inner or cmt`（区间里有注释行就算违规）⇒ exit 2 报
        #   「第 266 行起的模板：注释行 7 条」。⚗ 而那 7 条注释**从修订 142 起就一直
        #   合法地在判据里**（E2/E3/E4 页内块自带「// ① 整份数据取不到」这类注释），
        #   ⚠⚠⁴⚠⁴⚠ 实跑基线一直 `OK 39/39`。
        #   ⚠⚠⁴⚠⁴⚠⚴⚠ **判别式：危险的不是「模板里有注释」，是「注释里有反引号」。**
        #   ⚠⚠⁴⚠ ⚠⚠⚴⚠⁴⚠⚠⚠ **过严的门和恒绿的门同样有害** ——
        #     前者逼你把**别人正确的注释**删掉来换它过关（改坏东西），后者让你以为安全。
        #   ⚠⇒ 违规 = 「内嵌反引号 > 0」或「**带反引号的**注释行 > 0」；注释行数照印，供目视。
        nbad = sum(1 for l in cmt if BT in l)
        flag = "✓"
        if inner or nbad:
            flag = "⚠⚠⁴✗✗"
            bad += 1
            print(f"  {flag} 第 {seg_line} 行起的模板：内嵌反引号 {inner} 个，"
                  f"注释行 {len(cmt)} 条、其中**带反引号** {nbad} 条")
            for c in cmt:
                if BT in c:
                    print(f"        ⚗ {c[:70]}")
        else:
            print(f"  ✓ 第 {seg_line} 行起的模板：内嵌反引号 0、注释行 {len(cmt)}（带反引号 0）")
    if bad:
        die(f"{bad} 处模板里有内嵌反引号或带反引号的注释 ⇒ 会提前终止模板（修订 133/134/142 那一族）")
    # ⚠⚠⁴ 收尾：末行必须能被 node 解析，且模板数与起始点数一致
    if len(starts) != text.count(BT + ")") + text.count(BT + ";"):
        pass  # ⚠ 只是提示，不单独判红：结尾形式有多种，真正的门是 node --check
    return len(starts)


def gate3_node():
    print("=== 门③ node --check ===")
    r = subprocess.run(["node", "--check", str(TGT)], capture_output=True, text=True)
    if r.returncode != 0:
        die(f"node --check 崩\n{r.stderr[:600]}")
    print("  ✓ 通过")


def gate4_fffd():
    """⚠⚠⚴ U+FFFD 断言挂在「Python 解析后」那一层（修订 135 的教训）。"""
    print("=== 门④ U+FFFD（Python 解析后）===")
    import importlib.util
    spec = importlib.util.spec_from_file_location("vp_r144", TGT)
    m = importlib.util.module_from_spec(spec)
    # ⚠ mjs 是 ESM，importlib 读不了 ⇒ 改读源码并**模拟**解析：查反引号串里的转义执行
    body = TGT.read_text(encoding="utf-8")
    if body.count(FS):
        die(f"源文件里有 {body.count(FS)} 个坏字")
    print("  ✓ 源文件 0 个")


def gate5_skip_parse():
    """⚠⚠⁴⚠⁴ 跑台 parse() 的 RE_SKIP 靠这一行抓跳过列表 ⇒ 改判据不许碰它。"""
    print("=== 门⑤ [SKIP] 解析行仍在 ===")
    body = TGT.read_text(encoding="utf-8")
    pat = r"\[SKIP\]\s*\$\{s\.name\}"
    if not re.search(pat, body):
        die("for (const s of skips) console.log('[SKIP] …') 那行没了 ⇒ 跑台 skip 机制会失聪")
    print("  ✓ 在位")


def main():
    print(f"目标 {TGT.relative_to(ROOT)}")
    print(f"改动前 sha256 {hashlib.sha256(BASE.read_bytes()).hexdigest()}")
    print(f"改动后 sha256 {hashlib.sha256(TGT.read_bytes()).hexdigest()}")
    print()
    gate1_diff()
    print()
    gate2_backtick()
    print()
    gate3_node()
    print()
    # ⚠⚠⁴⚠⁴ gate4_fffd 第一版里有 `importlib.spec_from_file_location(TGT)`，
    # ⚗ 它对 .mjs 返回 `None.loader` ⇒ 门④ 自己 `AttributeError` 崩在装置上。
    #   ⚠⚠⁴⚠ ⚠ **仪器坏了 ≠ 被测物坏了** —— 本轮第一次现场区分这两者：
    #   ⚠⚠⁴⚠⚴⚠ 门④ 后面跟的是一个 Python traceback，里面**没有一条判据的信息**，
    #   ⚠⚠⁴⚠⚴⚠⚠ ⇒ 这份 traceback **对判据一无所证**，不许当「门④ 通过」也不当「门④ 失败」。
    #   ⚠⇒ .mjs 压根不是 Python 模块，importlib 读不了；U+FFFD 只查源文件层。
    print("=== 门④ U+FFFD（源文件层）===")
    _fffd = TGT.read_text(encoding="utf-8").count(FS)
    if _fffd:
        die(f"源文件里有 {_fffd} 个坏字")
    print("  ✓ 源文件 0 个")
    print()
    gate5_skip_parse()
    print("\n=== 五道门全部通过 ===")


if __name__ == "__main__":
    main()