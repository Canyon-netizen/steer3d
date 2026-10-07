#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""面板覆盖矩阵：把「页面上真实渲染的块」与「判据实际读过的块」摆在一起对账。

## 为什么要它

§8.3 ⑨ 已经立了一条规矩：**判据与被观测层要分别记账**，
一个页面判据集里一定存在「渲染上看不见」的改动类别。
这条规矩的反面同样要立：**页面上的块是否都被判据读过**。
一个没人读的块，在覆盖率统计里和「不存在」是同一件事。

## 它**不能**证明什么（必须一起说，否则这张表会骗人）

1. **3D 的「存在性与接线」本环境可验；「像素保真度」与「射线拾取点击」验不了。**
   ⚠⚠ 第三十三笔之八**改写了这一条**，原话是「3D 场景的全部标记在本环境验不了」
   ——它在第三十二笔当时是对的，但**已经过期**，而且它把三类不同的东西
   混成了一类「无法验证」。实测（本轮，两页各测两次）：

       页        不开 flag        开 swiftshader
       根页      2/16             6/16   ← 2D 降级块 data-testid=scene3d-fallback 由 1 变 0
       latent    4/16             4/16   ← 与 WebGL 无关

   原来那份 16 条的 `CONDITIONAL_3D` 里：
     - **只有 8 条 `data-scene-*` 真的是「WebGL 可用才渲染」的条件块**；
     - **6 条一直在 DOM 里**（根页 `data-drawn`/`data-frac`；
       latent 页 `data-bmroot`/`data-bmstep`/`data-bmgrid`/`data-bmgridn`）
       ⇒ 白名单把它们挡在「死引用」统计之外，于是**从来没被核过**；
     - **2 条**（`data-pfinal`/`data-ok`）在 `verify_derivation` 点 reset+run
       之后才渲染，早已被它 26/26 验过。
   ⇒ 那 12 条与 3D 无关，**不该挂在一句「本环境无法验证」下面**。
     挂着的后果不是「说错话」，是**判据替自己的没看见背书**。

   仍然验不了的那部分必须留着：**软件光栅只保证能画，不保证画得对** ——
   3D 珠子的像素保真度、以及**用射线拾取点中珠子**这两件事，
   本环境给不出判决，必须在真机 Chrome 上验。
2. **「判据提到」≠「判据读对了」。** 这里只做**存在性**对账。
   一条判据读了一个块、但读错字段，那是变异台的事，不是这里的事。
3. **它不看「看得见的文案」。** 判据主体必须包含直接读渲染文本的那条
   （§8.7 N4 的教训）。这里只统计标记名，不替代那类判据。

## 三条纪律

- **探针必须能自证跑过。** 本轮第一次跑，探针因为注释里有一对反引号而
  `SyntaxError`，而我用了 `> /dev/null 2>&1` 把失败吞了 ⇒
  Python 读到了上一次跑出来的**旧 JSON**，数字一模一样地「没变」，
  我差点当成「我刚才的修复没生效」。⇒ C0 盯 JSON 的新鲜度与字段完整性。
- **少记也要算错。** 同一个探针连着三次因为「只记第一个属性 / 只记无子节点的元素 /
  框架内部属性没排除」而少记，每次都长得像**产品有 bug**。
  ⇒ C4 把框架内部属性显式排除并说明理由。
- **只报数不列名 = 没有信息。** 每一处「没读过」都必须逐个列出名字。
- **⚠⚠ 第二十三笔：这份扫描原来把两页当成一页。**
  「判据读过的标记」是把 `.cache/browser_verify/` 下**所有** verify*.mjs
  的 data-* **无差别合并**的，而 `dom` 只来自根页（Next.js `/`）那一份探针
  产物。打 `/latent/index.html` 的两条判据（backmap / divergence_readout）
  读的标记在根页 DOM 里根本不存在，于是 C2 报出 5 个「死引用」。
  ⇒ 死的是**扫描器的分页假设**，不是判据，也不是产品。
  ⇒ 但**只把两页分开对账是不够的**：那样 latent 页会从矩阵里消失，
    C2 变绿而那一页一个标记都没被看 —— 一个新的、看不见的洞。
  ⇒ 现在两页都探、都进矩阵（C0 盯两份产物的新鲜度），并新增 C7。
"""
import io
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BLOCKS = ROOT / ".cache/browser_verify/panel_blocks.json"
# ⚠ 第二十三笔新增：latent 静态页是**另一个产品页**，不是根页的一部分。
#   它有自己的 36 个 data-* 标记、自己的判据（backmap / divergence_readout），
#   而它那块「为什么最后吐出的是这个词」在第二十三笔之前**从来没渲染过**。
LATENT_BLOCKS = ROOT / ".cache/browser_verify/panel_blocks_latent.json"
BVDIR = ROOT / ".cache/browser_verify"

# 「产物是否新鲜」要比的不是**绝对年龄**，而是**它有没有比源码新**。
# ⚠ 第十二笔的教训：C0 原来只判 `age < 7200`（两小时），而我这一轮去重改了
#   两个组件、产物是 45 分钟前写的 —— 45 分钟前正好**在改动之前**。
#   于是扫描拿着**改动前的 DOM** 报出 235 个标记 / 94%，而真相是 227 / 97%，
#   它自己一声不吭。
#   ⇒ 两小时的窗口足够跨过好几次提交，所以「多久之前」这个问题问错了；
#     该问的是「它在最后一次改动之后吗」。
SRC_GLOBS = [
    "frontend/components/*.tsx",
    "frontend/components/*.ts",
    "frontend/app/**/*.tsx",
    "frontend/app/**/*.ts",
    "frontend/public/latent/data/*.json",
    "frontend/public/layer_profiles.json",
    # ⚠ 第二十三笔补：`latent/index.html` 原来**不在**被测源码里。
    #   它是 latent 页的全部产品代码（这一轮就改了三处），
    #   不在列表里意味着「改了它，C0 察觉不到」——
    #   而第十二笔立的那条规矩正是「产物必须比源码新」。
    "frontend/public/latent/index.html",
]

# ⚠ 第二十三笔新增：每条判据打的是**哪一页**。
# 判据的目标页由它自己读的环境变量 / 硬编码 URL 决定 ——
# LAT_URL 或硬编码 /latent/ ⇒ latent 静态页；T3D_URL / BV_URL ⇒ Next.js 根页。
# ⚠ 为什么不按「哪个判据文件在哪个目录」分：两页的判据都放在同一个 .cache 目录里。
LATENT_TARGET = re.compile(r"process\.env\.LAT_URL|127\.0\.0\.1:\d+/latent/")

# ⚠⚠⚠ 页面内判据（TSX）：第三十四笔新增。
#   背景：`RandomControlPanel` 的配套判据 `verifyRandomControl.tsx` **住进了页面**
#   （挂载在 `app/page.tsx`），不是 `.cache/browser_verify/verify*.mjs`。
#   而 read 集合只从那两个 glob 来 ⇒ 那个判据**真的读过** `data-rc*`，
#   扫描器却完全不知道有它 ⇒ C4 报 6 条「新增未分类」。
#
#   ⚠⚠⚠ **为什么不把那 6 条登记进装饰簿**：
#   登记簿是**分类**，不是**证据**。C4 自己的注释写着「那等于用登记簿把缺口藏起来」。
#   面板确实被一个判据读着 —— 缺的是扫描器的**文件口径**，不是缺口的分类。
#   把「有人读」记成「纯装饰」，等于把一条真覆盖说成没有覆盖。
#
#   ⚠⚠⚠ 关键守卫：**必须证明那个判据组件真的挂在 page.tsx 上**。
#   一个写好但没挂载的判据会把它的标记算成「被读过」——
#   那是**假绿**，比现在这条红坏得多：页面上那些标记从此再没人核，
#   而 C4 还会报绿。⇒ C4a 专抓这一条。
TSX_DIR = ROOT / "frontend/components"
PAGE_TSX = ROOT / "frontend/app/page.tsx"


def tsx_judgments():
    """页面内判据：[(路径, 组件名, 是否真的挂在 page.tsx 上)]。"""
    if not PAGE_TSX.is_file():
        return []
    page_txt = io.open(str(PAGE_TSX), encoding="utf-8").read()
    out = []
    for f in sorted(TSX_DIR.glob("verify*.tsx")):
        raw = io.open(str(f), encoding="utf-8").read()
        m = re.search(r"export\s+default\s+function\s+(\w+)", raw) \
            or re.search(r"export\s+default\s+(\w+)", raw)
        name = m.group(1) if m else None
        mounted = bool(name) and re.search(
            r"<\s*%s\b" % re.escape(name), page_txt) is not None
        out.append((f, name, mounted))
    return out


# ⚠⚠ C7 的例外登记簿。
#   C7 问的是「源码里写了这个标记，两遍 DOM（加载后 / 点遍控件后）里都没有」——
#   那通常是一段**死代码**：读代码的人以为它在页面上，读者永远看不到。
#   第二十三笔就是靠这条抓到 18 个，其中 15 个是「整块从没渲染」。
#   本表只登记**有正当理由**的例外，每条必须写清为什么它不出现。
#   ⚠ 本表不许「先全登记再说」：C8 会拒绝**已经不再需要**的条目 ——
#   页修好了却忘了删登记，那条死代码就永远不会被再发现。
# ⚠⚠ 第三十二笔：登记簿 ——「这个标记没有判据读它，但这是有理由的」。
#   每一条都必须写清**为什么**没人读它仍然可以；
#   光写「装饰」不算理由（第六十行那个 print 里已经说过
#   「不许因为『它只是装饰』就自动算数」）。
#   ⚠ 这本簿子与 DEAD_IN_SOURCE_EXEMPT 是**两个方向**：
#     那本收「判据读了但页面上没有」（死引用）；
#     这本收「页面上有但判据没读」（未覆盖）。
# ⚠⚠ 第三十二笔：两本簿子，方向相反。
#   DEAD_IN_SOURCE_EXEMPT（下面）收「判据读了但页面上没有」= 死引用；
#   CROSSCHECK_EXEMPT 收「页面上有但判据没读」= 未覆盖。
CROSSCHECK_EXEMPT = {
    # ---- 纯装饰：承载零信息，删掉也不会少任何可核的东西 ----
    "data-step": "第三十二笔核实：全部块 tc=0（只带 data-step 不带值），"
                 "是横向时间轴的定位锚点。删掉不影响任何可见内容或可核数字。",
}

# ⚠⚠ 第三十二笔：已定位但**尚未处置**的未读标记清单 —— 这是**欠账**，不是许可。
#   ⚠ 我第一版把这些直接写进 CROSSCHECK_EXEMPT（登记为「待处置」），
#     那等于**用登记簿把缺口藏起来**：C4 变绿了而缺口还在。
#     与第二十九笔 G9「要求那一份存在」是同一族错误的镜像 ——
#     那边是判据保护缺陷，这边是簿子保护缺口。
#   ⇒ 所以拆成两本：装饰进簿子，真缺口进这份清单。
#   ⇒ 清单里每条都写清「它承载什么、为什么现在没核」；
#     处置完一个就删一条，账会自己变短。
def okey(u):
    """一个真孤儿的**身份**：来源页 + 标签 + 文本前 24 字。

    ⚠ 用文本前缀而不是块计数：同一个标签同一段文字可能在页面上出现多次，
    只数数量会把「同一条被记了两遍」和「两条不同的」混起来
    （第三十三笔之六的 mut_panel_coverage.py 就栽过：子串 `in` 匹配
    把按钮栏那条和它内部那句提示语算成同一条）。
    """
    return (u.get("page", "?"), u.get("tag", "?"), u.get("head", "")[:24])


def assign_keys(items):
    """给一组块编号身份：okey + 出现次序。

    ⚠⚠ 第三十三笔之十一：只按 (页,标签,前缀) 会**碰撞** —— 实测
      latent 37 段塌成 36 个 key、root 81 段塌成 74 个（8 组碰撞），
      例如两个 `<div>` 的文字都是 `strong L14`（长度也相同），
      **加 len 也分不开**。⇒ 登记一条会静默盖住两块。
      ⇒ 只能靠**出现次序**区分：同页同 key 的第 k 个加后缀 #k。
      代价是页面里多插一个块会让后面的次序整体平移 ⇒ 它们重新变成
      「未分类」。这个方向的错**是安全的**（宁可多报不可漏报）。
    """
    seen = {}
    out = []
    for u in items:
        k = okey(u)
        seen[k] = seen.get(k, 0) + 1
        out.append((k[0], k[1], k[2] + ("#%d" % seen[k] if seen[k] > 1 else "")))
    return out


# ---- C6 的两个登记簿（第三十三笔之十一）--------------------------------
# 「真孤儿」这个集合在修完两个病因之后大 17 倍，里面混着**性质不同**的东西：
#   承载主张的散文（该还）、图表标签/按钮/图例/<select> 选项（不该算缺口）、
#   以及旧工具从没看见的承载论证的 <div> 散文（该还，而且是新发现）。
# ⇒ 与其用一个数去套，不如**逐条定归属**：进装饰簿或进欠账簿，两本都要写理由。
#   判据判「未登记的 = 0」—— 与 C4 的「新增未分类 = 0」同一形状。
# ⚠ **初始为空是有意的**：C6 现在红 118，那是诚实的初态，
#   那 118 条就是接下来几笔的活清单。**不许为了让它变绿而批量自动登记** ——
#   自动登记等于把「夸大」合法化，而夸大正是这本账一直在反的东西。
ORPHAN_DECORATION = {
    # ⚠ 2026-10-07：75 段真孤儿**逐条**定归属完毕（装饰 23 + 欠账 52）。
    #   key 由 `.cache/xcheck/gen_orphan_registry.py` 生成 —— **不要手写**：
    #   它逐字照搬本文件的装配口径（页名排序后拼全局列表 → orphan and not shell
    #   → not volatile → 对**全局列表**调 assign_keys），少写一个字就静默匹配不上。
    #   分类是人的判断；key 的绑定与条数对账由那个脚本负责。
    ('latent', 'div', '隐空间 2D 候选词 维度解读 干预 vs 对照'): "纯导航 / 读法说明（标题、图例、按钮、选择器选项），承载零可核数字 —— 删掉它不会少任何能被核对的东西。",
    ('latent', 'div', '当前层 L14 L0 = embedding 输'): "纯导航 / 读法说明（标题、图例、按钮、选择器选项），承载零可核数字 —— 删掉它不会少任何能被核对的东西。",
    ('latent', 'div', 'L0 = embedding 输出，Lk = 第'): "纯导航 / 读法说明（标题、图例、按钮、选择器选项），承载零可核数字 —— 删掉它不会少任何能被核对的东西。",
    ('latent', 'h2', '隐空间 2D 投影 · L14'): "纯导航 / 读法说明（标题、图例、按钮、选择器选项），承载零可核数字 —— 删掉它不会少任何能被核对的东西。",
    ('latent', 'div', '当前 token 已生成 token，按这一步的'): "纯导航 / 读法说明（标题、图例、按钮、选择器选项），承载零可核数字 —— 删掉它不会少任何能被核对的东西。",
    ('latent', 'h2', 'TOP-64 候选词 · 第 0 步'): "纯导航 / 读法说明（标题、图例、按钮、选择器选项），承载零可核数字 —— 删掉它不会少任何能被核对的东西。",
    ('latent', 'div', '每根 = 一步，高度 = 那一歩模型有多确定；红'): "纯导航 / 读法说明（标题、图例、按钮、选择器选项），承载零可核数字 —— 删掉它不会少任何能被核对的东西。",
    ('latent', 'div', '[29] post-canvas'): "纯导航 / 读法说明（标题、图例、按钮、选择器选项），承载零可核数字 —— 删掉它不会少任何能被核对的东西。",
    ('root', 'div', 'Reasoning3D live 3-D vis'): "纯导航 / 读法说明（标题、图例、按钮、选择器选项），承载零可核数字 —— 删掉它不会少任何能被核对的东西。",
    ('root', 'h1', 'Reasoning3D'): "纯导航 / 读法说明（标题、图例、按钮、选择器选项），承载零可核数字 —— 删掉它不会少任何能被核对的东西。",
    ('root', 'div', 'REASONING PATH'): "纯导航 / 读法说明（标题、图例、按钮、选择器选项），承载零可核数字 —— 删掉它不会少任何能被核对的东西。",
    ('root', 'div', 'confident (low entropy)'): "纯导航 / 读法说明（标题、图例、按钮、选择器选项），承载零可核数字 —— 删掉它不会少任何能被核对的东西。",
    ('root', 'div', 'very uncertain'): "纯导航 / 读法说明（标题、图例、按钮、选择器选项），承载零可核数字 —— 删掉它不会少任何能被核对的东西。",
    ('root', 'div', 'self-check token'): "纯导航 / 读法说明（标题、图例、按钮、选择器选项），承载零可核数字 —— 删掉它不会少任何能被核对的东西。",
    ('root', 'div', 'current token'): "纯导航 / 读法说明（标题、图例、按钮、选择器选项），承载零可核数字 —— 删掉它不会少任何能被核对的东西。",
    ('root', 'div', '▶ Run ⏸ pause ⟲ reset'): "纯导航 / 读法说明（标题、图例、按钮、选择器选项），承载零可核数字 —— 删掉它不会少任何能被核对的东西。",
    ('root', 'div', 'Playback speed 1.00x'): "纯导航 / 读法说明（标题、图例、按钮、选择器选项），承载零可核数字 —— 删掉它不会少任何能被核对的东西。",
    ('root', 'h2', 'STEERING CONTROL'): "纯导航 / 读法说明（标题、图例、按钮、选择器选项），承载零可核数字 —— 删掉它不会少任何能被核对的东西。",
    ('root', 'h2', 'INTERPRETATION'): "纯导航 / 读法说明（标题、图例、按钮、选择器选项），承载零可核数字 —— 删掉它不会少任何能被核对的东西。",
    ('root', 'div', 'WHERE CONFIDENCE LIVES'): "纯导航 / 读法说明（标题、图例、按钮、选择器选项），承载零可核数字 —— 删掉它不会少任何能被核对的东西。",
    ('root', 'div', 'TRAJECTORY'): "纯导航 / 读法说明（标题、图例、按钮、选择器选项），承载零可核数字 —— 删掉它不会少任何能被核对的东西。",
    ('root', 'div', 'self-check tokens 0'): "纯导航 / 读法说明（标题、图例、按钮、选择器选项），承载零可核数字 —— 删掉它不会少任何能被核对的东西。",
    ('root', 'h2', 'REASONING TRACE'): "纯导航 / 读法说明（标题、图例、按钮、选择器选项），承载零可核数字 —— 删掉它不会少任何能被核对的东西。",
}

ORPHAN_DEBT = {
    # ⚠ 这些是**该还的债**，不是「没问题」：块上带着可核的数字或主张，
    #   而没有任何按标记读的判据能定位到它。
    #   登记只让账目诚实，**不修缺口** —— 修法是给块加稳定标记 + 补一条读它的判据。
    ('latent', 'div', '1983_I_1 ✓ (1024 tok) 19'): "{DEBT_NUM}",
    ('latent', 'div', 'Let x, y, and z all exce'): "承载**读者必须读到才能读懂这个面板在说什么**的主张，同样没有按标记读的判据能定位它。这是**欠账**。",
    ('latent', 'div', '当前 token 0'): "{DEBT_NUM}",
    ('latent', 'div', '该 token 原始 token <think>'): "承载**读者必须读到才能读懂这个面板在说什么**的主张，同样没有按标记读的判据能定位它。这是**欠账**。",
    ('latent', 'div', '熵 / top1 概率 0.001 / 1.00'): "{DEBT_NUM}",
    ('latent', 'div', '‖h‖ 当前层 144.9'): "{DEBT_NUM}",
    ('latent', 'div', '相对 embedding 移动 1078.1%'): "{DEBT_NUM}",
    ('latent', 'div', '1983_I_1 · <think> · 共 1'): "{DEBT_NUM}",
    ('latent', 'div', 'L14：目前只有第 1 步这一个点，算不出离散度'): "{DEBT_NUM}",
    ('latent', 'div', '模型这一步选了 <think> 给了它 100.'): "{DEBT_NUM}",
    ('latent', 'div', '几乎不做取舍。熵 0.0004 nats（越接近'): "{DEBT_NUM}",
    ('latent', 'div', '没选它的话，第二可能是 </think>（0.0'): "{DEBT_NUM}",
    ('latent', 'div', '# 候选词 概率 占比 1 <think> ←选'): "{DEBT_NUM}",
    ('root', 'div', '当前层 L14：坐标最大绝对值 79'): "{DEBT_NUM}",
    ('root', 'div', '占画面宽度 6.6%（全局统一除以 1200，不'): "{DEBT_NUM}",
    ('root', 'div', '浅层的轨迹看着小，是因为隐状态方差本身随深度暴涨'): "承载**读者必须读到才能读懂这个面板在说什么**的主张，同样没有按标记读的判据能定位它。这是**欠账**。",
    ('root', 'div', 'Layer (residual stream) '): "承载**读者必须读到才能读懂这个面板在说什么**的主张，同样没有按标记读的判据能定位它。这是**欠账**。",
    ('root', 'div', 'Confidence ↑'): "承载**读者必须读到才能读懂这个面板在说什么**的主张，同样没有按标记读的判据能定位它。这是**欠账**。",
    ('root', 'div', 'lower entropy, firmer an'): "承载**读者必须读到才能读懂这个面板在说什么**的主张，同样没有按标记读的判据能定位它。这是**欠账**。",
    ('root', 'div', 'strong L14'): "{DEBT_NUM}",
    ('root', 'div', 'Confidence ↓'): "承载**读者必须读到才能读懂这个面板在说什么**的主张，同样没有按标记读的判据能定位它。这是**欠账**。",
    ('root', 'div', 'raise entropy, explore m'): "承载**读者必须读到才能读懂这个面板在说什么**的主张，同样没有按标记读的判据能定位它。这是**欠账**。",
    ('root', 'div', 'strong L14#2'): "{DEBT_NUM}",
    ('root', 'div', 'Deep reasoning'): "承载**读者必须读到才能读懂这个面板在说什么**的主张，同样没有按标记读的判据能定位它。这是**欠账**。",
    ('root', 'div', 'push toward late-chain s'): "承载**读者必须读到才能读懂这个面板在说什么**的主张，同样没有按标记读的判据能定位它。这是**欠账**。",
    ('root', 'div', 'moderate L14'): "{DEBT_NUM}",
    ('root', 'div', 'Quick answer'): "承载**读者必须读到才能读懂这个面板在说什么**的主张，同样没有按标记读的判据能定位它。这是**欠账**。",
    ('root', 'div', 'push toward early setup '): "承载**读者必须读到才能读懂这个面板在说什么**的主张，同样没有按标记读的判据能定位它。这是**欠账**。",
    ('root', 'div', 'moderate L14#2'): "{DEBT_NUM}",
    ('root', 'div', 'the verify-your-work sta'): "承载**读者必须读到才能读懂这个面板在说什么**的主张，同样没有按标记读的判据能定位它。这是**欠账**。",
    ('root', 'div', 'the <think> scratchpad s'): "承载**读者必须读到才能读懂这个面板在说什么**的主张，同样没有按标记读的判据能定位它。这是**欠账**。",
    ('root', 'div', 'extracted at L14'): "{DEBT_NUM}",
    ('root', 'div', 'from tokens 20,930 / 15,'): "{DEBT_NUM}",
    ('root', 'div', "Cohen's d 1.83"): "{DEBT_NUM}",
    ('root', 'div', 'Strength 10%'): "{DEBT_NUM}",
    ('root', 'div', '0.02 0.05 0.1 0.2 0.4'): "{DEBT_NUM}",
    ('root', 'div', 'Inject at layer L14 Laye'): "{DEBT_NUM}",
    ('root', 'div', 'Inject at layer L14'): "{DEBT_NUM}",
    ('root', 'div', 'CURRENT TOKEN'): "承载**读者必须读到才能读懂这个面板在说什么**的主张，同样没有按标记读的判据能定位它。这是**欠账**。",
    ('root', 'div', 'confidence Very confiden'): "承载**读者必须读到才能读懂这个面板在说什么**的主张，同样没有按标记读的判据能定位它。这是**欠账**。",
    ('root', 'div', 'perplexity 1.00'): "{DEBT_NUM}",
    ('root', 'div', 'LAYER 14 — MEASURED'): "{DEBT_NUM}",
    ('root', 'div', '‖h‖ ↔ entropy r=-0.145'): "{DEBT_NUM}",
    ('root', 'div', 'no coupling — this layer'): "承载**读者必须读到才能读懂这个面板在说什么**的主张，同样没有按标记读的判据能定位它。这是**欠账**。",
    ('root', 'div', 'effective rank 93 / 128'): "{DEBT_NUM}",
    ('root', 'div', 'self-check separability '): "承载**读者必须读到才能读懂这个面板在说什么**的主张，同样没有按标记读的判据能定位它。这是**欠账**。",
    ('root', 'div', 'cos gap between self-che'): "承载**读者必须读到才能读懂这个面板在说什么**的主张，同样没有按标记读的判据能定位它。这是**欠账**。",
    ('root', 'div', 'think-block separability'): "承载**读者必须读到才能读懂这个面板在说什么**的主张，同样没有按标记读的判据能定位它。这是**欠账**。",
    ('root', 'div', 'L23 r=+0.43'): "{DEBT_NUM}",
    ('root', 'div', 'L22 r=+0.40'): "{DEBT_NUM}",
    ('root', 'div', 'L21 r=+0.40'): "{DEBT_NUM}",
    ('root', 'div', 'We are given the followi'): "承载**读者必须读到才能读懂这个面板在说什么**的主张，同样没有按标记读的判据能定位它。这是**欠账**。",
}

KNOWN_UNREAD = {
    # ---- latent 页：动态渲染的解释块（合计上万字）----
    "data-arm": "4 块（COT 的干预臂/对照臂），tc=1035/1031/573/564 —— "
                "两臂逐字对照，承载判决。零判据覆盖。",
    "data-armtext": "4 块，tc=906/906/440/439 —— 上文略去的正文，零判据覆盖。",
    "data-cotarm": "2 块，tc=168/168 —— 「加了向量 / 没加向量」两臂。零判据覆盖。",
    "data-filled": "143 字「1983_I_1 共同前缀 27 步 未闭合…」—— 闭合状态表。",
    "data-arhead": "60 字「<think>」标签头。",
    "data-arto": "8 字「↓ 直接跳到这里」跳转按钮。",
    "data-cotpre": "7 字「Okay,」—— 推理前缀。",
    "data-term": "15 块术语表项（38–109 字/项）。"
                "⚠ 待核实：这些项里含的数（如 embedding=2048）是否在别处被核过。",
    "data-f": "20 块内联数字（2048 / 0.0%–20.7% / 587–831 / Qwen3-1.7B …）。"
              "⚠ **不是纯装饰** —— 它们是页面上真正在印的数，"
              "「这个 2048 是不是从产物来的」目前无人核。",
    "data-beats": "节拍标记，待核实承载什么。",
    "data-n-candidates": "候选词计数标记，待核实。",
    "data-specific": "specific 标记，待核实。",
    # ---- root 页：有意只作交叉核对的那些，源码注释里已明说 ----
    "data-invisible-verified": "第二十九笔加的「未复现」声明（191 字）；"
                               "源码注释已明说它只作交叉核对，主体断言在别处。",
    "data-thin-dir": "第二十八笔 thin-* 四件套；注释已明说 state.omitted 取 "
                     "textContent，判据查不到属性。",
    "data-thin-n": "同上。",
    "data-thin-pool": "同上。",
    "data-thin-rho": "同上。",
    "data-vec-scale": "第三十一笔加的标定显示（50 字，数字现算），本轮无判据核。",
    "data-replay-note": "第三十一笔加的「这是回放」声明（149 字）。"
                        "⚠ verify_picker 全文 includes 过这段文字，"
                        "但那是**全文读**不是**按标记读**。",
    "data-entropy-layer-note": "第三十一笔加（104 字），本轮无判据核。",
    "data-latent-lead": "第三十一笔加的纯导读（85 字，不含可核数字）。",
    "data-latent-not-claimed": "第三十一笔加（56 字）。"
                               "⚠ 这一段是**判决性的**（声明本页否掉了哪 4 种理解），"
                               "是本清单里最该优先补判据的一条。",
    # ---- root 页：真缺口；相关措辞更正见文档第三十二笔 ----
    "data-anchor-note": "245 字，第二十八笔「逐字引产物原句」的修复本体 —— "
                        "**那块散文当时正是无人可读的洞**。零判据覆盖。",
    "data-anchor-status": "19 字，与上面同一处的锚点状态。",
    "data-ca-self-quote": "72 字 claim_audit 的逐字引文。",
}

DEAD_IN_SOURCE_EXEMPT = {
    "data-jump": "DELTA 视图专属的跳转锚点，在 drawDeltaSide() 里 h +=，"
                 "只有用户点开「干预 vs 对照」标签才存在。#extras 那份有意不带。",
    "data-jumphint": "同上（跳转按钮的提示位）。",
    "data-cotjump": "同上：drawDeltaSide() 自己拼的入口行，不在 renderCotEffect() 里。",
    "data-arjump": "同上。",
    # ⚠⚠ 第三十六笔：第 5 屏「逐步路径」的 7 个标记。它们**不是**死代码，
    #   和上面 data-jump / data-cotjump 是同一类 —— 只在用户点开第 5 个标签
    #   （renderPathPanel() → layout() 的 PATH 分支）之后才在 DOM 里，
    #   而覆盖扫描的探针只点前四个标签，测的是默认视图。
    #   verify_path.mjs 会点开第 5 屏、把 36 条逐条读一遍（其中 8 条直接读这些标记，
    #   其余靠可见文案间接锁住）。不登记的话 C7 会把「条件渲染」误报成死代码，
    #   而把真死代码混进同一份名单，就等于让这份名单失去意义。
    "data-pathblock": "第 5 屏「逐步路径」整块的根标记（renderPathPanel 的返回值）。"
                      "只在该屏打开时渲染；verify_path 读它的 data-pathstate 三态"
                      "（ok / no-data / no-problem）与 data-pathpid、data-pathk。",
    "data-pathstate": "同上，三态标记。数据缺失时页面必须**明说**缺什么，"
                      "不能静默消失 —— verify_path 的 A1 查的就是这个。",
    "data-pathpid": "同上，当前题号。切题后必须跟着换，verify_path D3 查。",
    "data-pathk": "同上，当前题的分叉步。verify_path C1 拿它与产物里的 k 对账。",
    "data-patht": "同上，每一行的步号（t=0..k）。verify_path D1/D2 靠它数行、"
                  "点行展开。",
    "data-pathfork": "同上，标出哪一行是分叉步。verify_path C2 查「恰好一行且 t=k」。",
    "data-pathbtn": "同上，两个视图切换按钮（只看分叉前后 ±5 步 / 看全部）。"
                    "verify_path D2 点「看全部」查行数变成 k+1。",
    # ⚠ 第六屏「干预阈值」：整屏只在点了 #tabThresh 之后才渲染，而覆盖扫描
    #   逐页探针不会点那个标签 ⇒ 两遍 DOM（加载后 / 点遍控件后）都看不到它们。
    #   它们**不是**死代码：verify_thresh.mjs 点标签进去，逐条读了
    #   data-thresh-step / data-thresh-bracket / data-threshgen / data-threshstate
    #   / data-dr-mult，并与 intervention_threshold_law.json 逐格对账。
    #   登记理由是「**条件渲染**」，不是「判据没触发」——这两者不能混，
    #   混了就等于让白名单替真死代码背书（见下面 data-ta-* 那段的前车之鉴）。
    "data-threshblock": "第六屏「干预阈值」容器，条件渲染（只有点了 #tabThresh "
                        "才进 DOM）。verify_thresh T1/T2 靠它判「本屏已就绪」，"
                        "数据没载入时它落成 data-threshstate=no-data。",
    "data-threshstate": "同上，区分 ready / no-data —— 产物缺失与屏幕没渲染"
                        "是两件事，判红前要先分清。",
    "data-thresh-step": "第六屏逐步阈值表的行号，条件渲染。verify_thresh T4/T5 "
                        "逐行与产物 per_step[].step 对账，并强制右删失行印成 "
                        "\">\"（变异：去掉 > 前缀 ⇒ T5 红）。",
    "data-thresh-bracket": "同上，该行区间是 bracketed / left_censored / "
                           "right_censored。verify_thresh T5 按它分别要求 "
                           "区间 / \"<\" / \">\"，不许三者混用。",
    "data-threshgen": "第六屏「能不能迁移」那一节的判决标记，条件渲染。"
                      "verify_thresh T6/T7 要求它与产物 generality.verdict "
                      "**逐字相同**，且理由段落可见——判否时只印成立那半就红。",
    "data-dr-mult": "第六屏剂量-反应表的强度档，条件渲染。verify_thresh T3 "
                    "逐档与产物 dose_response[] 对账（档数、‖δ‖、|Δlogit|、翻盘数）。",
    "data-dr": "第六屏那张剂量-反应小 canvas，条件渲染。只作**交叉核对**用"
               "（证明曲线节点在）；T2 的单调性由判据从 JSON 独立重算，"
               "不信 canvas，也不信页面上的数。",
    # ⚠ 第三十八笔：第 7 屏「因果修补」的标记，同样是**条件渲染**，
    #   理由与上面第 5/6 屏完全一致 —— 覆盖扫描的探针只点前几个标签，
    #   不点 #tabPatch，测的是默认视图。verify_patch.mjs 会点开第 7 屏逐条读。
    "data-patchblock": "第七屏「因果修补」容器，条件渲染（只有点了 #tabPatch 才渲染）。"
                       "它同时承载 data-patchstate 三态：ok / no-data，"
                       "产物缺失时页面必须**明说缺什么**，不能静默消失。",
    "data-patchstate": "同上，与产物是否载入对应。",
    "data-patch-ask": "第七屏顶部的问句块，条件渲染。它的文字必须与产物 "
                      "what_it_asks 逐字相同 —— 读者第一眼看到的是它。",
    "data-patch-fails": "第七屏的「N/M 道门没有通过」块，条件渲染。"
                        "verify_patch 要求判否与没测的门都出现在这里，"
                        "不许把不成立的门折叠掉或藏进详情。",
    "data-patch-gates": "第七屏判决表的 tbody，条件渲染。每行一个门，"
                        "verify_patch P1 逐行核对 data-verdict 与产物 gates[].verdict"
                        "**逐字相同**（唯一结论字段，不许页面自己另判一次）。",
    "data-gate": "判决表每行的门名，与同行 data-verdict 配对。",
    # ⚠ data-key 漏登记过一次，让 C7 判红。漏登记的后果与登记错**方向相反**：
    #   登记簿是「这些标记读者看不到，但读代码的人会以为它在」的白名单；
    #   漏一条 ⇒ 真活着的标记被当成死代码，**把活判成死的**。
    #   而它偏偏是这一屏**唯一**的对账键：门名 `内容窗可定位` 在三个量上
    #   各出现一次，只有 data-key（形如 G4[word/excessm]）能分清是哪一道门。
    #   verify_patch 靠它与产物 gates 的键配对，漏了它页面就会互相认错门。
    "data-key": "判决表每行的**门键**（形如 G4[word/excessm]），与同行 "
                "data-gate / data-verdict 在同一个 <tr> 上，条件渲染。"
                "verify_patch 按**门键**而不是门名与产物 gates 对账 —— "
                "三个量共用门名，只按门名认会互相认错。",
    "data-verdict": "判决表每行的结论，取值 pass/fail/na 三者之一。"
                    "verify_patch P2 要求三态**都**可能出现在页面上，"
                    "并要求 na 行同时给出 why_na —— 没测说成不成立是伪造结论。",
    "data-patch-problems": "第七屏逐题表，条件渲染。每行一题，"
                           "verify_patch P3 逐题与产物 problems[] 对账"
                           "（题号、被解释 token、两臂改口与否）。",
    "data-patch-pid": "逐题表的题号，verify_patch P3 拿它与产物 pid 配对。",
    "data-patch-chart": "第七屏描述/因果对照图的容器，条件渲染。",
    "data-svg": "第七屏那张 SVG，条件渲染。只作**交叉核对**用（证明曲线在）；"
                "三条线的数值由判据从 JSON 独立重算，不信页面上的数。",
    "data-lines": "同上，记这张图画了几条线，跨屏可比的固定口径。",
    "data-patch-limits": "第七屏「这一屏不能回答的」诚实边界块，条件渲染。"
                         "verify_patch P4 要求它存在且非空 —— "
                         "只印成立那半就红。",
    # ⚠⚠ 第四十一笔：第 8 屏「阈值向量」的 13 个标记。理由与第 5/6/7 屏**完全一致**
    #   （条件渲染：只有点了 #tabLtv 才进 DOM），但这一屏多一条**别的屏都没有的**
    #   理由，值得单独写下来：
    #   ltv.json 此前**没有任何页面消费者** —— 产物发了、方法判完了，
    #   而「方法证据」在网站上是看不见的。所以这一屏不是「多加一屏好看的」，
    #   是把一份已经算完的东西接上读者。verify_ltv_panel.mjs 负责点开它并逐格对账。
    #   登记理由仍是「**条件渲染**」，不是「判据没触发」——
    #   登记错方向等于让白名单替真死代码背书（见 data-ta-* 那段前车之鉴）。
    "data-ltvblock": "第八屏「阈值向量」容器，条件渲染（只有点了 #tabLtv 才渲染）。"
                     "同时承载 data-ltvstate 三态：ready / no-data —— "
                     "产物缺失时页面必须**明说缺什么**，不能静默空屏。",
    "data-ltvstate": "同上，区分 ready / no-data。屏幕没渲染与产物没载入是两件事，"
                     "判红前必须先分清。",
    "data-ltv-slice": "第八屏顶部的判决切片声明块，条件渲染。它的文字必须与产物 "
                      "judge_slice / judge_slice_note **逐字相同** —— "
                      "G-a 的 claim 与预登记表都写着「留出」，而第一版的判决跑在"
                      "全量 36 个上下文上，所以这一块是那次口径偏离的现场披露。",
    "data-ltv-fails": "第八屏的「N/M 道门没有通过」块，条件渲染。"
                      "verify_ltv_panel 要求判否与没测的门都出现在这里，不许折叠。",
    "data-ltv-gates": "第八屏判决表的 tbody，条件渲染。每行一道门，"
                      "verify_ltv_panel 逐行核对 data-verdict 与产物 gates[].verdict "
                      "**逐字相同**（唯一结论字段，页面不许自己另判一次）。",
    "data-ltvgate": "判决表每行的**门键**（G-a0/G-a/G-b/G-c/S1），与同行 data-verdict "
                    "配对。按门键而不是门名与产物配对 —— 门名可能重名。",
    "data-ltv-variant": "第八屏 G-b 的**并列口径**块（variant_all_ctx），条件渲染。"
                        "verify_ltv_panel 要求它存在，且要求它与判决口径 "
                        "（+1 14／−1 0）**印在同一块里**，并显式标注"
                        "「不是判决」—— 只印全量那组数会把「抽取集上不显著」藏起来。",
    "data-ltvsent": "第八屏句子轴每一行的 S_k 名，条件渲染。"
                    "verify_ltv_panel 逐行与产物 sentence_diffs[].key 对账"
                    "（S、S′、‖S−S′‖ 三格）。",
    "data-ltvneg": "同上，标这一行是不是**负对照**。3 条负对照必须与 8 条真实轴"
                   "一起进稀疏分解，否则「confidence_up」这个名字是编的 —— "
                   "只挑有利的轴分解，结论就不可信。",
    "data-ltvctx": "第八屏逐上下文表每行的身份（pid@pos），条件渲染。"
                   "verify_ltv_panel 靠它与产物 contexts[] 配对，"
                   "并逐格对 m_p / g_v / α*预测 / α*实测 / 对照 α*。",
    "data-ltvslice": "同上，这一行属不属于判决切片（holdout / extract）。"
                     "G-b 在两个切片上一个显著一个不显著（p=1.22e-04 vs 9.23e-02），"
                     "所以切片必须**印在每一行上**，不能只印一个总数。",
    "data-ltvsens": "第八屏拟合窗敏感性每一行的拟合窗，条件渲染。"
                    "verify_ltv_panel 逐行与产物 fit_window_sensitivity 对账。",
    "data-ltv-caveats": "第八屏「这一屏不能回答的」诚实边界列表，条件渲染。"
                        "产物自带 8 条，页面必须**逐条转述、条数相等** —— "
                        "后 3 条是判决切片的披露，少印一条就等于把那次的偏离藏起来。",
    # ⚠⚠ 第四十二笔：第八屏「① 稀疏分解」那两个标记。登记理由与上面 13 条一致
    #   （条件渲染：只有点了 #tabLtv 才在 DOM 里），但它们承载的东西与那 13 条
    #   **不同**：那 13 条是「这一屏存在」，这两个是「**一个没发生过的分解被写成了事实**」。
    #   上一版屏上印着「它们和另外 8 条一起进稀疏分解」，而探针只算出 11 条 d_k
    #   就收工 —— 没有 c_k、没有按 |c_k| 选子集，K_MAX=8 被搬了三个文件却没人读。
    #   ⇒ 补算后实测全解只解释 7.807%，|c_k| 前 8 条里有 2 条负对照。
    "data-ltv-decomp": "第八屏「这个分解没有交付」那块头条，条件渲染。"
                       "verify_ltv_panel 要求它存在、可见，且里面印的"
                       "解释率 / 截断能量 / 负对照条数与产物 decomp 逐项相符 —— "
                       "这一块是**否定结论**，只印成立那半就红。",
    "data-ltvsenttop": "第八屏句子轴每一行「被 |c| 前 K_MAX 选中」的标记，条件渲染。"
                       "verify_ltv_panel 用它数**负对照有几条进了选中** —— "
                       "负对照混进选中是「名字可疑」最直接的证据，必须可数，"
                       "而且判据数的是**可见文案**（不是这个 data-*）。",
    # ⚠ 第三十一笔：这两个只在下拉框切到第 5 档（extraction_layer_effect.json）
    #   时才渲染，而默认 idx=0 ⇒ 覆盖扫描看到的根页 DOM 上没有它们。
    #   它们**不是**死引用：Q0 会逐档切过去，Q1 用它们做交叉核对。
    "data-ta-gap-lo": "ArchivedExperiments 第 5 档（ExtractionTable）专属，"
                      "默认 idx=0 不渲染；Q0 逐档切过去核，Q1 用它交叉核对。",
    "data-ta-gap-hi": "同上。",
    # ⚠⚠ 第三十三笔之八：这两个原本藏在 `CONDITIONAL_3D` 里，**理由是错的**
    #   （它们与 3D 毫无关系，是 LayerDerivationPanel 的柱子属性）。
    #   把它们移出白名单之后 C2 立刻报真红 —— 这正是白名单在替
    #   「判据没在默认视图里触发它」背书。真实原因是：
    #   `verify_derivation.mjs` 会先点 reset 再点 run（脚本 :68-69），
    #   柱子才画出来 ⇒ 默认视图（idx=0、未播放）上它们不存在。
    "data-ok": "LayerDerivationPanel 每根柱子的「这一层读对了没有」标志位，"
               "默认视图未播放时不渲染；verify_derivation 先点 reset+run 再读它，"
               "26/26 逐根核过。",
    "data-pfinal": "同上（柱子最终投影概率）。⚠ verify_derivation 刻意**同时**"
                   "读 rect.height：data-pfinal 是面板拿到的数字，读者看到的是"
                   "绘制高度，变异 D1 把 height 全改成常数而 data-pfinal 不变时"
                   "只查它的判据会假绿。",
    # ⚠⚠ C2 长期唯一剩下的红：根页死引用 `data-deriv-default`。
    #   它**不是**死代码，条件在 `openedByDefault`（LayerDerivationPanel.tsx:155）：
    #       openedByDefault = !currentTrajectory && !!artifactFirstId
    #   也就是「**后端没连上**，面板只好自己挑一条录制」时才渲染。
    #   本轮实测后端 9503 **在跑**（Python PID 23703 LISTEN）
    #   ⇒ currentTrajectory 被设上 ⇒ openedByDefault 为假 ⇒ 探针的 DOM 快照里没有它。
    #   ⇒ 扫描器把「这一轮没出现」当成了「从来没有过」——
    #   它没有条件渲染的概念，而**条件渲染与死代码在输出上完全同形**。
    #
    #   它是被读着的，而且是**当前提**读：`verify_derivation.mjs:263` 用
    #   `selfOpened` 判「播放期的断言能不能建立」，并且把「后端确实没连上」
    #   与「后端在线但还没开始播」分成两句不同的理由印出来
    #   （:274-279）。本轮它报 PASS 27/27，正是走了 selfOpened=false 那一支。
    "data-deriv-default": "LayerDerivationPanel 的「这条录制是面板自己挑的」声明块，"
                          "条件渲染于 openedByDefault = !currentTrajectory "
                          "&& !!artifactFirstId，即**后端没连上**时才出现。"
                          "verify_derivation :263 拿它当「播放期断言能否建立」的前提，"
                          "并把「后端确实没连上」与「后端在线但没开始播」"
                          "分成两句不同的理由印出来（:274-279）。"
                          "本轮后端在跑 ⇒ 不渲染 ⇒ 扫描器误当死引用。",
}


def newest_source_mtime():
    """被测源码里最新的 mtime；找不到任何源文件时返回 0（此时不判这一条）。"""
    newest, which = 0.0, ""
    for g in SRC_GLOBS:
        for p in ROOT.glob(g):
            try:
                m = p.stat().st_mtime
            except OSError:
                continue
            if m > newest:
                newest, which = m, str(p.relative_to(ROOT))
    return newest, which

# Next.js 14 会给 <link rel=stylesheet> 加 data-precedence="next"，
# 用来控制 CSS 注入顺序。它是**框架内部**属性，与本项目无关。
# ⚠ 第一版没排除它，于是它被当成一个「空的顶层面板」报了出来 ——
#   我第一反应是「页面上有个空面板」，差点去修一个根本不存在的产品 bug。
FRAMEWORK_INTERNAL = {
    "data-precedence": "Next.js 控制 CSS 注入顺序",
    "data-nscript": "Next.js 标记脚本已就绪",
}

# 只在 WebGL 可用时才渲染的标记 ⇒ 本环境**默认**验不了。
# ⚠⚠ 第三十三笔之八：**这份名单是实测标定的，不是凭印象写的。**
#   原名单 16 条里混了三类不同的东西：
#     ① 真·3D 条件块（下面这 8 条）—— 不开 WebGL 时根页走
#        `data-testid="scene3d-fallback"` 2D 降级，它们**根本不渲染**；
#     ② 一直在 DOM 里、却被白名单挡住**从来没被核过**的 6 条
#        （根页 data-drawn / data-frac，latent 页 data-bm* 四条）；
#     ③ 交互之后才渲染、且早已被 verify_derivation 26/26 验过的 2 条
#        （data-pfinal / data-ok）。
#   ②③ 与 3D 无关，**必须移出白名单**，让它们回到正常的对账里去。
#   ⚠ 移出去之前逐条查过「谁读过它」，8 条**全部有判据读过**：
#     data-drawn  ← verify_derivation / verify_structure
#     data-frac   ← verify_structure
#     data-bm*    ← verify_backmap / verify_delta_still_works
#     data-pfinal / data-ok ← verify_derivation
#   ⇒ 缩小名单**不会**让 C2 / C4 变红（实测）。
CONDITIONAL_3D = {
    "data-scene-loaded", "data-scene-focus", "data-scene-focus-miss",
    "data-scene-focus-state", "data-scene-focus-step", "data-scene-focus-token",
    "data-scene-window-high", "data-scene-window-low",
}

results = []


def strip_js_comments(src):
    """剥掉 JS 里的 // 与 /* */ 注释，保留字符串字面量的内容。

    ## 为什么需要它（第二十三笔）

    「判据读过的标记」是从 `verify*.mjs` 的**源码文本**里 grep `data-[a-z0-9-]+`
    得到的。而判据的源码里有**说明文字**，第二十三笔我自己就写了
    「那 16 个 `data-cot*` / `data-ar*`」——
    星号终止了匹配，于是散文里的 `data-cot` 与 `data-ar`
    被当成两个真标记，C2 报成「latent 页有 6 个死引用」。
    ⇒ **判据自己也是源码，扫它同样要先剥注释。**
    （第二十二笔那条同族教训：判据扫 Python 源码要先剥行注释。）

    ## 两个不能省的细节

    1. **字符串字面量要保留内容。** 判据里真正的标记引用几乎全在
       `page.eval(\`... [data-cotblock] ...\`)` 这种模板串里 ——
       把字符串一起剥掉的话，提取结果会是空的，而**空集合恒绿**。
    2. **`http://` 不能被当成注释。** 判据里满是
       `http://127.0.0.1:22113/latent/index.html`，
       天真的 `//` 剥离会从那里切到行尾，顺带吃掉同行的选择器
       ⇒ 变成**假绿**（少读标记，缺口被藏起来）。
       所以 `//` 只有在**前面不是 `:`** 时才算注释开头。
    """
    out = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            # `://` 里的两个斜杠不是注释
            if not (i > 0 and src[i - 1] == ":"):
                j = src.find("\n", i)
                i = n if j < 0 else j
                continue
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            j = src.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if c in "\"'`":
            q = c
            lit_start = i
            i += 1
            depth = 0
            while i < n:
                if src[i] == "\\":
                    i += 2
                    continue
                if q == "`" and src[i] == "$" and i + 1 < n and src[i + 1] == "{":
                    depth += 1
                    i += 2
                    continue
                if depth and src[i] == "}":
                    depth -= 1
                    i += 1
                    continue
                if not depth and src[i] == q:
                    i += 1
                    break
                i += 1
            # ⚠⚠ 字面量的**内容必须原样保留**。
            #   第一版这里写的是 out.append(" ")，把整个字符串丢掉 ——
            #   而判据里真正的标记引用几乎全在
            #   page.eval(`... [data-cotblock] ...`) 这种模板串里。
            #   ⇒ read 集合几乎清空 ⇒ C2「0 个死引用」**恒成立**，
            #     而它变成的是一条没有任何内容的绿。
            #   抓住它的是同一次改动里加的 C2a 负控 ——
            #   没有那道负控，这个假绿会一直绿到有人重新审计 C2。
            #   （一般形态：抽取器一旦**变少**，下游所有「缺失数」都会变好看。
            #     「少提取」的错误方向永远是假绿，必须有一道反向闸。）
            out.append(src[lit_start:i])
            continue
        out.append(c)
        i += 1
    return "".join(out)


def markers_in(src_text):
    """从一份 JS 源里提取它引用的 data-* 标记名（已剥注释）。"""
    return re.findall(r"data-[a-z0-9-]+", strip_js_comments(src_text))


def check(name, ok, detail):
    results.append({"name": name, "ok": bool(ok)})
    print("[%s] %s\n       %s" % ("PASS" if ok else "FAIL", name, detail))


def main():
    # ---- C0 探针自证：文件在、字段全、且是刚才跑出来的 ----
    # ⚠ 第二十三笔：**两份**产物都要验。原页要验 + latent 静态页也要验 ——
    #   只验一份的话，另一份可能是上一次跑出来的，而它读的是改动前的 DOM。
    missing = [p for p in (BLOCKS, LATENT_BLOCKS) if not p.exists()]
    if missing:
        check("C0 两页的探针产物都在", False,
              "缺 %s —— 探针没跑，或跑失败了"
              % ", ".join(p.name for p in missing))
        return abort("产物文件不存在",
                     ["两页都要跑，顺序有讲究（改完页面 → 起服务 → 逐页跑探针）：",
                      "  BV_URL=<根>/ node .cache/browser_verify/probe_panels.mjs",
                      "  BV_URL=<根>/latent/index.html PROBE_OUT="
                      "…/panel_blocks_latent.json node "
                      ".cache/browser_verify/probe_panels.mjs",
                      "⚠ 跑第二遍时**别忘了换 PROBE_OUT** —— 忘了它会覆盖根页那份，"
                      "于是根页看起来也覆盖了 latent 页，而其实根页一个标记都没量。"])
    ages = {p: time.time() - p.stat().st_mtime for p in (BLOCKS, LATENT_BLOCKS)}
    raws = {p: json.load(io.open(str(p), encoding="utf-8")) for p in (BLOCKS, LATENT_BLOCKS)}
    # 探针第二版把产物改成 {byDepth, unmarked}。兼容旧的纯 byDepth 结构。
    Bs = {p: (raws[p].get("byDepth", raws[p]) if isinstance(raws[p], dict) else raws[p])
          for p in (BLOCKS, LATENT_BLOCKS)}
    # ⚠ 两份产物必须**自报是哪一页**，且不能都报同一页。
    #   少了这一条，两次探针都跑同一个 URL 也会「都成功」，
    #   而 latent 页的 36 个标记一个都没进矩阵 —— 看起来一切正常。
    pages = {p.name: (raws[p].get("page") if isinstance(raws[p], dict) else None)
             for p in (BLOCKS, LATENT_BLOCKS)}
    # ⚠⚠⚠ 第三十三笔之六（病因 A）：这一段原来只有**一行** ——
    #   unmarked = raws[BLOCKS].get("unmarked") if isinstance(raws[BLOCKS], dict) else None
    #   **只读根页那一份**（panel_blocks.json），
    #   latent 页那份 panel_blocks_latent.json 的 unmarked 清单**整个被丢掉** ——
    #   而 C5/C6 印出来的「26 段 / 真孤儿 0 段」读起来像**两页**的结论。
    #   实测 latent 页那份里一直有 1 段（66 字的 `p.olead`，祖先链为空），
    #   从来没被 C6 看到过。
    # ⇒ 现在两页都收，且每条带上「来自哪一页」
    #   （下面 C5 的判据会盯着「两页都在」这件事）。
    #   ⚠⚠ 合并**不等于**混成一个总数报出去：第三十二笔吃过一次
    #     「两页互相对账」的假红（拿 latent 的标记去问根页的 DOM）。
    #     反过来的错在这里同样成立：把两页加在一起报成「444 段」，
    #     读者就看不出其中 231 段来自一个**python 从来没读过**的页。
    #     ⇒ 每条都带 page，且**所有计数按页分开报**。
    unmarked_by_page = {}
    unmarked_missing = []
    for p in (BLOCKS, LATENT_BLOCKS):
        pg = pages[p.name]
        lst = raws[p].get("unmarked") if isinstance(raws[p], dict) else None
        if not isinstance(lst, list):
            # ⚠ 少一份**不能**当成「那一页没有缺口」—— 那是把「没量」当「量过」。
            unmarked_missing.append("%s(page=%s)" % (p.name, pg))
            continue
        for it in lst:
            it = dict(it)
            it["page"] = pg
            unmarked_by_page.setdefault(pg, []).append(it)
    unmarked = [it for pg in sorted(unmarked_by_page) for it in unmarked_by_page[pg]]
    flat = [it for items in Bs[BLOCKS].values() for it in items]
    has_all = all("all_data" in it for it in flat)
    # ⚠⚠ 第三十三笔之十三：C0 现在**要求** ownLen/shell 也在产物里。
    #   这两个字段是「本块自己还剩多少字」/「它是不是纯壳」，
    #   C6 排除壳时要**用它们**。旧产物没有 ⇒ C0 红 ⇒ 逼人重跑探针。
    #   ⚠ 刻意**不做**「旧字段缺失就当 0」那种兼容 ——
    #     兼容等于让壳悄悄混回缺口里，而 C6 正是靠这个数在守。
    has_own = all("ownLen" in it and "shell" in it for it in unmarked)
    if not has_own:
        print("       ⚠ 产物里没有 ownLen/shell 字段 ⇒ 这是**旧版探针**的产物，")
        print("         C0 会红。重跑两页 probe_panels.mjs（第三十三笔之十三起才有）。")
    # ⚠⚠ 第三十三笔之十四：还要 `volatile`（这一块**自己会不会变**）。
    #   根页有一条会自己往前走的轨迹读数：同一份源码连跑 3 次，
    #   真孤儿**总数恒为 61**，但其中 **8~11 条每轮换一批身份**
    #   （connected ### steps / step ### · ppl / path length / ### tokens …）。
    #   ⇒ 「总数一样」会让人以为量是稳的，**而变的是身份**；
    #     任何按块内容对账的东西都会被它搅乱，报出来的现象
    #     （「还原后多了一条缺口」）**长得完全像真回归**。
    #   ⇒ 探针现在隔 4s 再采一次清单自己标出来，python 侧据此分层。
    #   ⚠ 同样**不做**「缺字段就当 False」那种兼容 —— 那等于让不可复现的块
    #     冒充可复现的，正是这个字段要防的那件事。
    has_vol = all("volatile" in it for it in unmarked)
    if not has_vol:
        print("       ⚠ 产物里没有 volatile 字段 ⇒ 旧版探针的产物，C0 会红。")
        print("         重跑两页 probe_panels.mjs（第三十三笔之十四起才有）。")
    # ⚠⚠ 第三十三笔之六：unmarked 的**口径**也变了（元素集 + 阈值），
    #   产物里必须自报这次用的门槛 —— 否则「清单里的数」与「阈值」会各说各话。
    thresh_by_page = {pages[p.name]: (raws[p].get("thresh") if isinstance(raws[p], dict) else None)
                      for p in (BLOCKS, LATENT_BLOCKS)}
    check("C0b 两页的未读清单必须用**同一个口径**（元素集与阈值都自报在产物里）",
          None not in thresh_by_page.values() and len(set(thresh_by_page.values())) == 1,
          "thresh：%s；census 齐全=%s"
          % ("、".join("%s=%s" % (pg, thresh_by_page[pg]) for pg in sorted(thresh_by_page)),
             all(isinstance(raws[p].get("census"), dict) for p in (BLOCKS, LATENT_BLOCKS))))
    page_ok = (pages[BLOCKS.name] == "root"
               and pages[LATENT_BLOCKS.name] == "latent")
    src_mt, src_which = newest_source_mtime()
    blocks_mt = min(p.stat().st_mtime for p in (BLOCKS, LATENT_BLOCKS))
    # 产物必须比**被测源码**新。只比绝对年龄是不够的（见 SRC_GLOBS 上方注释）。
    # ⚠ 用两份里**更旧**的那份比：只要有一份比源码旧，那一页的数字就不可信。
    newer_than_src = (src_mt == 0.0) or (blocks_mt > src_mt)
    check("C0 两页探针产物新鲜、字段完整、且各自自报是哪一页",
          has_all and has_own and has_vol and page_ok
          and max(ages.values()) < 7200 and newer_than_src,
          "根页 %d 秒前 / latent %d 秒前；根页 %d 个元素，all_data 齐全=%s，"
          "ownLen/shell 齐全=%s，volatile 齐全=%s；"
          "page 字段 根=%s latent=%s；产物比最新源码（%s）新=%s（取两份里更旧的比）"
          % (ages[BLOCKS], ages[LATENT_BLOCKS], len(flat), has_all, has_own, has_vol,
             pages[BLOCKS.name], pages[LATENT_BLOCKS.name],
             src_which or "（无源文件）", newer_than_src))
    if not page_ok:
        return abort("两份探针产物没有各自自报页面",
                     ["panel_blocks.json 的 page 必须是 root、"
                      "panel_blocks_latent.json 的 page 必须是 latent。",
                      "两页都跑同一个 URL 会让其中一份悄悄覆盖另一份。"])
    if not has_all:
        return abort("探针产物字段不完整",
                     ["这是**探针**坏了（第一版只记第一个 data-* 属性）。",
                      "别去改产品，先修探针。"])
    if not newer_than_src:
        return abort("产物比源码旧，页面侧输入是改动前的 DOM",
                     ["产物比源码**旧** ⇒ 后面每一个数字都不可信。",
                      "先重跑两页的探针（见上面的两条命令），",
                      "顺序很重要：改完页面 → 起服务 → 逐页跑探针 → 才跑本扫描。"])

    # ---- dom 按页分开，最后合并 ----
    # ⚠ 两遍（加载后 / 点遍控件后）的并集才是这一页真实的标记面。
    #   只用第一遍的话，按需渲染的块会被记成「源码里有、页面上没有」——
    #   那是**假红**：第二十三笔实测 latent 页点遍 13 组控件，
    #   从 37 个可点控件变成 58 个，带出 0 个新标记（因为它们本来就都在）。
    dom_by_page = {}
    for p, raw in raws.items():
        names = set()
        for it in [x for items in Bs[p].values() for x in items]:
            names |= set(it.get("all_data") or [it["data"]])
        if isinstance(raw, dict):
            names |= set(raw.get("beforeNames") or [])
            names |= set(raw.get("afterNames") or [])
        names.discard("data-nscript")
        dom_by_page[raw.get("page") if isinstance(raw, dict) else None] = names
    dom = {}
    for names in dom_by_page.values():
        for n in names:
            dom[n] = dom.get(n, 0) + 1
    fw_present = sorted(k for k in dom if k in FRAMEWORK_INTERNAL)
    dom = {k: v for k, v in dom.items() if k not in FRAMEWORK_INTERNAL}

    # ---- 判据按目标页分账 ----
    # ⚠⚠ 第二十三笔的教训：原来这里把**所有** verify*.mjs 的 data-*
    #   无差别合成一个 read 集合，而 dom 只来自根页 ⇒ 打 latent 页的判据
    #   读的标记在根页 DOM 里不存在，被 C2 报成「死引用」。
    #   ⇒ read 带上「这条判据打哪一页」，C2 按页各自对账。
    read = {}
    read_by_page = {"root": {}, "latent": {}}
    # ⚠⚠⚠ 第三十四笔的**顺序**闸：页面内判据清单必须在这里先算出来。
    #   第一版把它写在「收集 read 集合」那段（靠后），
    #   而 C2a（靠前）已经要用它 ⇒ 跑起来 UnboundLocalError。
    #   ⚠ 这条错误 **`ast.parse` 查不出来** —— 语法完全合法，
    #   只是名字在使用点还没绑定。
    #   ⇒ 「过了 ast.parse」只证明**能解析**，不证明**能跑**。
    #     与「拿 round(median,4) 比未舍入中位数」同族：装置自己通过了自己的检查。
    tsx_all = tsx_judgments()
    # ⚠⚠ 负控：剥注释之后，**任何出现在方括号选择器里的标记都必须在**。
    #   剥注释器要处理字符串字面量（`page.eval(\`[data-x]\`)`）与
    #   `http://` 这类假注释头，两处都可能整段吃掉内容 ——
    #   而「少提取标记」的方向恰好是**假绿**（缺口被藏起来）。
    #   ⇒ 这条不是装饰：它一红就说明提取器坏了，后面每一个数字都不可信。
    lost = []
    # ⚠ 第三十四笔：把页面内判据（TSX）也纳入这个负控。
    #   否则新加的那一路提取器**没人验**：它少提取标记时 C4 照样绿。
    c2a_files = list(BVDIR.glob("verify*.mjs")) + list(BVDIR.glob("shot*.mjs")) \
        + [f for f, _, ok in tsx_all if ok]
    for f in c2a_files:
        raw = io.open(str(f), encoding="utf-8").read()
        got = set(markers_in(raw))
        # ⚠ `=` 进字符类：TSX/JS 常写 `[data-rc="ok"]`（带值），
        #   而原式只认裸选择器 `[data-rc]` ⇒ 带值的那种**根本不会被要求存在**，
        #   于是「提取器把它整段吃掉」也照样绿。方向是少提取 = 假绿，必须堵。
        for m in re.findall(r"\[(data-[a-z0-9-]+)[\]\s'\",=]", raw):
            if m not in got:
                lost.append("%s: %s" % (f.name, m))
    check("C2a 剥注释不许吃掉任何方括号选择器里的标记（少提取 = 假绿）",
          not lost,
          "被剥掉 %d 个：%s" % (len(lost), ", ".join(lost[:6]))
          if lost else "全部 %d 个判据文件的选择器都保住了（含页面内 TSX 判据）"
          % len(c2a_files))

    # ---- C2b（第二十六笔）：注释写在 `page.eval(\`...\`)` 模板串内部 --------
    # ⚠⚠ 这条是被本轮自己的一个错误逼出来的，而且 11 个判据文件都有这个形状。
    #   `page.eval(\`...\`)` 里写 `// xxx`：那**不是注释**，那是要发给浏览器
    #   eval 的字符串。浏览器侧它确实是行注释（每条只注释自己那一行，所以
    #   页面侧**不会坏** —— 这正是它能潜伏很久的原因）。
    #   坏在另一头：`markers_in()` 有一条刻意的规则「字符串字面量要保留内容」
    #   （把字符串也剥掉的话提取结果会是空的，而空集合恒绿），
    #   ⇒ 写在模板串里的 `data-xxx` 会被**当成真的读取引用**提取出来。
    #   本轮实测：我把「data-cos-digit-newline 那一块已删」这句解释
    #   写进了 verify_subspace 的模板串，而那个元素本轮已从页面删除
    #   ⇒ C2 报「root 页死引用 1 个」，**死的是我自己那两行注释**。
    #   更糟的是 C2a（负控）恰好被这一行**喂饱**：负控的输入是未剥注释的原文，
    #   它看到 `[data-cos-digit-newline]` 就要求剥后文本里也有 ——
    #   而提供它的是同一处假引用。⇒ 负控被一个字符串里的假引用顶账。
    #   注意这与 C2a 是**相反**的方向：C2a 防「少提取」（假绿），
    #   C2b 防「多提取」（假红 + 负控被顶账）。两条都要。
    templ_comments = []
    for f in list(BVDIR.glob("verify*.mjs")) + list(BVDIR.glob("shot*.mjs")):
        text = io.open(str(f), encoding="utf-8").read()
        for m in re.finditer(r"page\.eval\(`", text):
            st, d, i = m.end(), 0, m.end()
            while i < len(text):
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == "`":
                    d += 1
                    if d > 0:
                        break
                i += 1
            for ln in text[st:i].split("\n"):
                s = ln.strip()
                # 排除 http:// 这种假注释头，也排除块注释的续行（* /）
                if s.startswith("//") and "http://" not in s and not s.startswith("*"):
                    for mk in re.findall(r"data-[a-z0-9-]+", s):
                        templ_comments.append("%s: %s" % (f.name, mk))
    check("C2b 模板串里的「// 注释」不许含 data- 标记名（会被当成真的读取引用）",
          not templ_comments,
          "以下标记名只存在于 page.eval 模板串内的注释里，而它们会被提取成"
          "「判据读过的标记」：%s" % ", ".join(templ_comments[:8])
          if templ_comments
          else "17 个判据里没有把 data-* 写进模板串内的注释"
          + "（注释请写在真正的注释位置，且别给已删标记加方括号）")

    for f in list(BVDIR.glob("verify*.mjs")) + list(BVDIR.glob("shot*.mjs")):
        text = io.open(str(f), encoding="utf-8").read()
        page = "latent" if LATENT_TARGET.search(text) else "root"
        for m in markers_in(text):
            read[m] = read.get(m, 0) + 1
            read_by_page[page][m] = read_by_page[page].get(m, 0) + 1

    # ---- 页面内判据（TSX）：只认**真的挂在 page.tsx 上**的那些 -------------
    # ⚠ 不挂载的不许进 read：那会让「写了没接上」的判据把缺口说成已覆盖。
    # ⚠ tsx_all 已在 read 初始化处算好（见那里的顺序闸）。
    tsx_live = [(f, n) for f, n, ok in tsx_all if ok]
    for f, name in tsx_live:
        text = io.open(str(f), encoding="utf-8").read()
        # TSX 判据一律打在**根页**（它们挂在 app/page.tsx 上）。
        # ⚠ 别用 LATENT_TARGET 判：那是给 .mjs 判据用的（看它们读哪个 URL），
        #   而 TSX 判据不读 URL，它读的是同一份 DOM —— 就是根页。
        for m in markers_in(text):
            read[m] = read.get(m, 0) + 1
            read_by_page["root"][m] = read_by_page["root"].get(m, 0) + 1

    check("C4a 页面内判据（verify*.tsx）必须真的挂在 page.tsx 上"
          "（没挂载的判据若被算成「读过」，那是假绿：那些标记从此没人核）",
          all(ok for _, _, ok in tsx_all) and bool(tsx_all),
          "共 %d 个页面内判据，已挂载 %d 个：%s"
          % (len(tsx_all), len(tsx_live),
             ", ".join("%s→%s" % (f.name, n) for f, n, ok in tsx_all))
          if tsx_all else "（frontend/components/ 下没有 verify*.tsx）")

    check("C1 框架内部属性已被识别并剔除（不是产品块）",
          fw_present == ["data-precedence"],
          "剔除 %s —— %s" % (fw_present or "（无）",
                            "；".join(FRAMEWORK_INTERNAL[k] for k in fw_present)) or "（无）")

    # C2：按页各自对账。
    # ⚠ 一条判据读的标记如果在**两页**里都不在，那才是真的死引用；
    #   只在「它自己那页」不在才算 —— 跨页不算，因为一条判据只打开一页。
    per_page = {}
    real_dead_all = []
    exempt_hits = []
    for pg, doms in sorted(dom_by_page.items()):
        only_here = sorted(k for k in read_by_page.get(pg, {})
                           if k not in doms and k not in FRAMEWORK_INTERNAL)
        real = [k for k in only_here if k not in dom]
        cond = [k for k in real if k in CONDITIONAL_3D]
        real = [k for k in real if k not in CONDITIONAL_3D]
        # ⚠ 判据读它、但它「有意不在默认 DOM 里」的条目，走同一本登记簿。
        #   两处各写一份名单的话，搬一次家要改两处，漏一处就是假红。
        exempted = [k for k in real if k in DEAD_IN_SOURCE_EXEMPT]
        exempt_hits += exempted
        real = [k for k in real if k not in DEAD_IN_SOURCE_EXEMPT]
        per_page[pg] = (real, cond, exempted)
        real_dead_all += real
    check("C2 判据里不许有真正的死引用（按它自己那页对账；不在页面、也不是 WebGL 条件块）",
          not real_dead_all,
          "；".join(
              "%s 页判据 %d 条 → 死引用 %d 个%s%s"
              % (pg, len(read_by_page.get(pg, {})), len(per_page[pg][0]),
                 ("：" + ", ".join(per_page[pg][0])) if per_page[pg][0] else "",
                 ("，已登记为「有意不在默认视图」%d 个" % len(per_page[pg][2]))
                 if per_page[pg][2] else "")
              for pg in sorted(per_page)))
    print("       ⚠ 跨页的标记**不算死引用**：一条判据只打开一页，"
          "它读的标记在它那页上就该在。")
    for k in sorted(set(exempt_hits)):
        print("       ○ %-16s %s" % (k, DEAD_IN_SOURCE_EXEMPT[k]))

    cond = sorted(set(k for v in per_page.values() for k in v[1]))
    # ⚠⚠⚠ 第三十三笔之八：**C3 原来是一条永远不可能失败的判据。**
    #   原式 `not cond or set(cond) <= CONDITIONAL_3D` —— 而 `cond` 在
    #   上游第 554 行已经被筛成 `[k for k in real if k in CONDITIONAL_3D]`
    #   ⇒ `set(cond) <= CONDITIONAL_3D` **恒为真**。
    #   实测证法：把 `CONDITIONAL_3D` 整个清空（其余一字不改），
    #   **C3 依然 PASS**，而 C2 正确转红。
    #   ⇒ 它占着一个绿位，而它宣称检查的那件事**从未被检查过**。
    #   （与 `None == None`、M2b 同族：恒真比假绿更坏。）
    #
    #   新形状：**两个方向都要能红**。
    #   方向一（藏）：名单里的某条这一轮**已经在 DOM 里** ⇒ 它此刻不是条件块。
    #     要么它被核过（可以留下），要么它该从名单里删掉（不许挂白名单）。
    #     两样都不做 = 判据在替自己的没看见背书。
    #   方向二（空转）：名单里的某条**从来没有判据读过** ⇒ 白名单是纯掩护。
    #     名单存在的唯一理由是「有判据想读它，本轮渲染不出来」。
    #   方向三（过期）：这一轮 DOM 里已经出现 `data-scene-*` ⇒ WebGL 本轮可用，
    #     不许再印「本环境无法验证」——那句话在这一轮是假的。
    hiding = sorted(k for k in CONDITIONAL_3D
                    if k in dom and k not in read)
    idle = sorted(k for k in CONDITIONAL_3D if k not in read)
    scene_live = sorted(k for k in dom if k.startswith("data-scene-"))
    check("C3 「3D 条件块白名单」必须只装**这一轮真的渲染不出来、"
          "却有判据想读**的标记（⚠ 恒真判据已修：原式被上游筛成恒真，"
          "清空整份名单它也 PASS）",
          not hiding and not idle,
          "名单 %d 条：藏了 %d 条（在 DOM 里却没人读：%s）、"
          "没有任何判据想读 %d 条（%s）"
          % (len(CONDITIONAL_3D), len(hiding), ", ".join(hiding) or "无",
             len(idle), ", ".join(idle) or "无")
          + ("　⚠ 这 %d 条此刻不是条件块：要么核它，要么从名单里删它"
             % len(hiding) if hiding else ""))
    print("       ⚠ 这 %d 个**不是死引用**，但也**不算验过**。" % len(cond))
    if scene_live:
        print("       ✓ **本轮 WebGL 可用**（DOM 里已出现 %d 个 data-scene-*：%s）"
              % (len(scene_live), ", ".join(scene_live)))
        print("         ⇒ 3D 的**存在性与接线**这一轮已进对账；")
        print("           但**像素保真度**与**射线拾取点击**软件光栅给不出判决，")
        print("           仍必须在真机 Chrome 上验。")
    else:
        print("         本轮 DOM 里没有 data-scene-* ⇒ WebGL 不可用（页面走 2D 降级），")
        print("         3D 联动与 3D 像素必须在能跑 WebGL 的浏览器里验。")

    unread = sorted(k for k in dom if k not in read)
    # ⚠⚠ 第三十二笔：这一条原来是 `isinstance(unread, list)` ——
    #   它**只判「unread 是个列表」**，所以 0 个缺口时 PASS、
    #   27 个缺口时**也 PASS**。判据名字写着「必须逐个列名」，
    #   而 PASS 读起来像「覆盖没有缺口」——
    #   ⇒ 第二十八笔的提交信息就是这么误读的：
    #     「它们立刻被 C4 算进『页面上有、判据读过』，所以没有新增覆盖缺口」
    #     实测那 8 个标记全部 0 命中，此刻就列在这份清单里。
    #   ⇒ 现在把它变成能红的：**未登记的未读标记必须为 0**。
    #     登记簿 CROSSCHECK_EXEMPT 收两类：
    #       「有意只作交叉核对」（源码注释里已明说，判据查不到属性）
    #       「纯装饰」（定位锚点 / 内联数字 / 术语表项，承载信息在别处被核）
    #   登记簿本身就是可核的：每条都要写清「为什么没人读它仍可以」。
    _unreg = [k for k in unread
              if k not in CROSSCHECK_EXEMPT and k not in KNOWN_UNREAD]
    check("C4 页面上存在、但没有任何判据读过的标记，必须逐个**分类**"
          "（纯装饰进装饰簿；真缺口进「已知欠账」清单；两者都不许悄悄放过）",
          not _unreg,
          "未读 %d = 装饰 %d + 已知欠账 %d ＋ **新增未分类 %d**"
          % (len(unread),
             len([k for k in unread if k in CROSSCHECK_EXEMPT]),
             len([k for k in unread if k in KNOWN_UNREAD]),
             len(_unreg))
          + "　新增未分类：%s" % (", ".join(_unreg) or "无")
          + "　⚠ 已知欠账 %d 条是**待还的账**，处置完一条删一条：%s"
            % (len([k for k in KNOWN_UNREAD if k in unread]),
               ", ".join(sorted(k for k in KNOWN_UNREAD if k in unread)) or "无"))
    _stale_x = sorted(k for k in CROSSCHECK_EXEMPT
                      if k not in dom and k not in read)
    _stale_k = sorted(k for k in KNOWN_UNREAD
                      if k not in dom and k not in read)
    if _stale_x:
        print("       ⚠ 装饰簿里有 %d 个在两页 DOM 上都不存在：%s"
              % (len(_stale_x), ", ".join(_stale_x)))
    if _stale_k:
        print("       ⚠ 已知欠账清单里有 %d 个既不在页面上也不在判据里"
              "（处置完了？请删掉，否则欠账数字虚高）：%s"
              % (len(_stale_k), ", ".join(_stale_k)))
    print("       ⇒ 这 %d 个是**覆盖缺口**。其中可能有一部分是纯装饰"
          % len(unread))
    print("         （如 data-painted / data-rendered-points 这类渲染状态标记），")
    print("         判它是不是缺口要看它们承载的信息有没有别的判据覆盖 ——")
    print("         **不许因为「它只是装饰」就自动算数**。")

    covered = len([k for k in dom if k in read])
    print("\n覆盖：两页合计 %d 个标记，被判据读过 %d 个（%.0f%%）；"
          % (len(dom), covered, 100.0 * covered / max(len(dom), 1)))
    print("      分页：%s"
          % "、".join("%s 页 %d 个" % (pg, len(doms))
                     for pg, doms in sorted(dom_by_page.items())))

    # ---- C7 / C8：源码里有、两遍 DOM 都没有的标记 ----
    # ⚠⚠ 这条是第二十三笔真正抓到东西的判据。
    #   C2 问的是「判据读的标记在不在页面上」，方向是**判据 → 页面**；
    #   C7 问的是「源码写了标记，页面上出不出来」，方向是**源码 → 页面**。
    #   两者都不能少：第二十三笔那 15 个 data-cot* / data-ar*
    #   **一条判据都没读过**，所以 C2 看不见它们、C4 也看不见它们
    #   （C4 问的是「在页面上的有没有人读」，方向正好相反）。
    #   而它们恰恰是**读者永远看不到**的那三块解释。
    # ⇒ 只有从**源码**出发才抓得到。
    src_markers = set()
    for g in ("frontend/public/latent/index.html",
              "frontend/components/*.tsx", "frontend/app/**/*.tsx"):
        for p in ROOT.glob(g):
            try:
                txt = io.open(str(p), encoding="utf-8").read()
            except OSError:
                continue
            src_markers |= set(re.findall(r"data-[a-z0-9-]+", txt))
    # 只在 latent 页那份 HTML 上做「源码 vs DOM」——
    # 根页的标记来自 React 组件，字符串出现在 .tsx 里不代表运行时会有
    # （三元表达式、条件渲染、模板拼接都会让静态 grep 说谎）。
    lat_src = set(re.findall(
        r"data-[a-z0-9-]+",
        io.open(str(ROOT / "frontend/public/latent/index.html"),
                encoding="utf-8").read()))
    lat_dom = dom_by_page.get("latent", set())
    dead_in_src = sorted(k for k in lat_src
                         if k not in lat_dom and k not in FRAMEWORK_INTERNAL)
    unexplained = [k for k in dead_in_src if k not in DEAD_IN_SOURCE_EXEMPT]
    check("C7 latent 页源码里有、两遍 DOM（加载后 / 点遍控件后）都没有的标记"
          "必须逐个登记理由（死代码：读代码的人以为它在，读者永远看不到）",
          not unexplained,
          "源码 %d 个标记 / 渲染 %d 个 / 源码有而渲染没有 %d 个"
          % (len(lat_src), len(lat_dom), len(dead_in_src)))
    for k in dead_in_src:
        why = DEAD_IN_SOURCE_EXEMPT.get(k)
        print("       %s %-18s %s" % ("○已登记" if why else "✗未登记", k,
                                       (why or "**没有登记理由 —— 这是死代码**")))
    if unexplained:
        print("       ⇒ 这 %d 个没登记：%s"
              % (len(unexplained), ", ".join(unexplained)))
        print("         两种可能：① 整块从没渲染（第二十三笔那 15 个就是这种）"
              " ② 判据该读它但读错了页。")
        print("         先顺着 SRC 找到它属于哪个 render 函数，再看那个函数谁调用。")

    stale = sorted(k for k in DEAD_IN_SOURCE_EXEMPT if k in lat_dom)
    check("C8 例外登记簿里不许留已经不再需要的条目（页修好了却忘了删登记，"
          "那条死代码就永远不会被再发现）",
          not stale,
          "已失效 %d 个：%s" % (len(stale), ", ".join(stale) or "无")
          if stale else "登记簿 %d 条，全部仍然必要" % len(DEAD_IN_SOURCE_EXEMPT))
    unknown_exempt = sorted(k for k in DEAD_IN_SOURCE_EXEMPT
                            if k not in lat_src)
    if unknown_exempt:
        print("       ⚠ 登记簿里有 %d 条在源码里**根本不存在**：%s"
              % (len(unknown_exempt), ", ".join(unknown_exempt)))

    # ---- C5 / C6：带文字、但**一个 data-* 都没有**的那些块 ----
    # 覆盖矩阵统计的是「带 data-* 的块」。D6（归属论证那段 note）与
    # G7（caution_absorbed / control.note）那两个洞，恰恰是**一个 data-* 都没有**
    # 的散文 —— 没有标记 ⇒ 不进矩阵。
    #
    # ⚠⚠ 但我原来在这里写的结论是**错的**，已改：
    #   「所以『未被读过』那一栏永远不会列出来」——**这句是错的，已改**。
    #   2026-10-03 实测（probe_unmarked_ancestors.mjs）：那 27 段**全部**落在
    #   某个带 data-* 的祖先里，祖先属性往往就带着同一句话的机器可读真值，
    #   例如 data-outcome#2 的祖先带 data-cos-up-down=-0.9999999999999997，
    #   正对应散文里的「cos = -1.0000」。
    # ⇒ 「自身无标记」≠「没人读」。真正无解的是**真孤儿**（祖先链为空），
    #   那是 C6；而 C5 只负责**列名**，不负责算数。
    #
    # ⚠⚠⚠ 第三十三笔之六：口径改了两处，两处都有实测依据
    #   ① **两页都用**（病因 A，见上面 unmarked_by_page）。
    #      原来只有根页 ⇒ latent 页的清单整份丢失，而数字读起来像两页的。
    #   ② **元素集与阈值**（病因 B）：原来「只扫 <p>、且 ≥40 字」。
    #      实测（.cache/browser_verify/probe_panels.mjs 的 census 字段，
    #      端口 22208）：导读浮层 #orientation 里 11 个真缺口有
    #      **10 个根本不是 <p>**（h1×1 / h2×5 / div×4），最短的一条只有 11 字
    #      （`<h2>五 · 这些数字的边界`）⇒ 旧口径**结构上**看不见它们。
    #      注意这与浮层开不开无关（.hide 是 visibility，innerText 读得到）。
    # ⇒ 阈值 10 不是挑的，是**被那 11 条决定的**：
    #   阈值必须 ≤ 11 才能收进最短那条，取 10 免得「刚好 11」像运气。
    #   规模代价（实测 census，两页合计）：
    #     阈值   0 → 565 段（孤儿 140）   10 → 451（128）   20 → 325（77）
    #     阈值  30 → 224（52）   40 → 182（44）  ← 40 是旧口径量级
    #   ⇒ **不因为清单变长就抬高阈值**：那正是这个项目反复栽的坑
    #     （为了让数字好看而收窄口径）。清单变长改用**分两层打印**解决：
    #     真孤儿层逐条列名（那才是缺口），在标记作用域内的只聚合计数
    #     （逐条全名在 probe_panels.mjs 的 stdout 里，一条不少）。
    if unmarked_missing or len(unmarked_by_page) < 2:
        check("C5 探针须给出「有文字但没标记」的块清单，**且两页都要有**"
              "（第三十三笔之六的病因 A：只读根页 ⇒ latent 页整份丢失）", False,
              "缺 %s —— 探针是旧版，或两页跑的是同一个 URL。"
              "两页都要重跑 probe_panels.mjs（latent 那遍别忘了换 PROBE_OUT）"
              % ("、".join(unmarked_missing) or "（有清单但只到一页）"))
    else:
        n_page = {pg: len(v) for pg, v in sorted(unmarked_by_page.items())}
        # ⚠⚠ 第三十三笔之十三：这里也**剔掉纯壳**，与 C6 同一口径 ——
        #   两处各算各的 ⇒ 「C5 说 N 段、C6 说 M 段」而没人知道差在哪。
        n_orph = {pg: sum(1 for u in v if u.get("orphan") and not u.get("shell"))
                  for pg, v in sorted(unmarked_by_page.items())}
        n_shell = {pg: sum(1 for u in v if u.get("orphan") and u.get("shell"))
                   for pg, v in sorted(unmarked_by_page.items())}
        # ⚠ 以**新清单**回算旧口径（tag=p 且 ≥40 字），
        #   这样「口径放宽了多少」是当场算出来的数，不是记忆里的数。
        #   ⚠ 而且**按页分开**：26 + 1 = 27 里那个 1 是 latent 页的 `p.olead` ——
        #     旧工具打出来的是「26 段」，那 1 段它**连读都没读过**
        #     （病因 A：unmarked 只从根页那份产物里取）。
        old_scope = [u for u in unmarked if u.get("tag") == "p" and u.get("len", 0) >= 40]
        old_pp = {pg: sum(1 for u in old_scope if u["page"] == pg) for pg in n_page}
        check("C5 「有实质文字、但自己没被登记」的块必须逐条列名并计数（两页合计）",
              len(unmarked) > 0 and len(unmarked_by_page) == 2,
              "%d 段；分页 %s；其中真孤儿 %d 段（分页 %s）"
              # ⚠⚠ 下面这段**必须留在同一个隐式拼接组里**：我用 `+ "；"` 切了一刀，
              #   而 Python 的 `%` 比 `+` 紧 ⇒ `%` 只作用到最后一段字面量 ⇒
              #   `TypeError: not all arguments converted during string formatting`。
              #   **症状指向最后一行，凶手在第一行。**
              "　⊘ 另有**纯壳** %d 段（分页 %s）：它们去掉子节点后一个字都不剩，"
              "不承载自己的主张，不算缺口（第三十三笔之十三）；"
              "⚠ 旧口径（只扫 <p> 且 ≥40 字）回算只有 %d 段（分页 %s）"
              "—— 差出来的 %d 段旧工具**从来没量过**"
              "（含导读浮层那 11 条实测全部在内，"
              "逐条断言见 mut_panel_coverage.py）"
              % (len(unmarked),
                 "、".join("%s 页 %d 段" % (pg, n) for pg, n in n_page.items()),
                 sum(n_orph.values()),
                 "、".join("%s 页 %d 段" % (pg, n) for pg, n in n_orph.items()),
                 sum(n_shell.values()),
                 "、".join("%s 页 %d 段" % (pg, n) for pg, n in n_shell.items()),
                 len(old_scope),
                 "、".join("%s 页 %d 段" % (pg, n) for pg, n in sorted(old_pp.items())),
                 len(unmarked) - len(old_scope)))
        print("       ⇒ 这 %d 段**块级**没有标记，所以它们自己不会进矩阵；"
              % len(unmarked))
        print("         但这不等于「没人读」——见下面 C6 的祖先统计。")
        print("         判据不许因为「它没被登记」就自动算数，必须逐段看。")
        nums = [u for u in unmarked if re.search(r"\d", u["head"])]
        print("         前 70 字里带数字的有 %d 段（更可能是承载论证的）："
              % len(nums))
        print("       ⚠ 清单按两层看：**真孤儿**（C6 的缺口）与**在标记作用域内**"
              "（祖先属性多半带着同一句话的机器可读真值）。")
        for pg, v in sorted(unmarked_by_page.items()):
            bpan = {}
            for u in v:
                bpan[u["panel"]] = bpan.get(u["panel"], 0) + 1
            print("       ── %s 页 %d 段（真孤儿 %d 段）：%s"
                  % (pg, len(v), n_orph[pg],
                     "、".join("%s=%d" % (k, x) for k, x in sorted(bpan.items()))))

        # ---- C6：真孤儿必须**逐条有归属** ----
        # 「承载判决的那句话必须落在某个可读作用域里」——
        # 祖先链为空 = 任何按标记读的判据都够不着它。
        # 这条**能变红**：删掉某个 data-*，那个块自己就成了孤儿。
        #
        # ⚠⚠ 第三十一笔：措辞已改。原话「承载判决的话不能无人可读」——**有反例**：
        #   ControlPanel 那 149 字的「这是回放」段落祖先链为空，
        #   但 verify_picker.mjs 里就写着 "Replaying a recorded"（全文 includes）。
        #   ⇒ **祖先链为空 ≠ 没人读**。它只说明「没有任何按标记读的判据能定位它」。
        #
        # ⚠⚠⚠ 第三十三笔之十一：**判据形状改了**，因为目标值必须在新集合上重新标定。
        #   C6 的「必须为 0」是在 **26 段散文 <p>** 上标定的。
        #   修完两个病因之后集合变成 440 段 / 118 个真孤儿：元素集从 <p> 扩到
        #   h1,h2,h3,p,li,div、阈值 40 → 10、还把 latent 页收了回来。
        #   ⇒ 同一个 0，被套在一个**大 17 倍、性质也变了**的集合上。
        #   实测这 118 条混着三类：
        #     ① 导读那 11 条真缺口（承载主张，该还）
        #     ② UI 文字：图表标签、按钮、图例、<select> 的 option 列表
        #        （"Layer (residual stream) layer 0 layer 1…"、"▶ Run ⏸ pause"）
        #     ③ **旧工具从没看见的承载论证的散文**（它们是 <div> 不是 <p>）：
        #        「这一层在做什么 L14：…单点的方差恒为 0」
        #        「几乎不做取舍。熵 0.0004 nats（越接近 0 = 越不做取舍）」
        #        「浅层的轨迹看着小，是因为隐状态方差本身随深度暴涨」
        #   ⇒ ② 不该叫缺口（把标签页文字算成「缺口」是**夸大**）；
        #     ①③ 该叫 —— 而 ③ 是**这一笔真正的收获**：工具变准了，不是变吵了。
        #
        #   ⇒ 处置照抄 C4 自己的形状（C4 判的就是「新增未分类 = 0」）：
        #     **判「未逐条登记的 = 0」，而不是「总数 = 0」。**
        #   这**不是放宽**：没登记的照样红，而且必须**逐条列名**（页 + 标签 + 文本）。
        #   打印上限改为**按页分列** —— 上一版是全局 40 条，
        #   118 条里 latent 页占前 40，**root 页一条都看不见**。
        #   ⇒ 登记表初始为空 ⇒ C6 现在红 118，这是**诚实的初态**，
        #     它就是接下来几笔的活清单。
        no_anc = [u for u in unmarked if "ancestors" not in u]
        no_pg = [u for u in unmarked if "page" not in u]
        if no_anc or no_pg:
            check("C6 探针须给出每段的祖先链与来源页（判断真孤儿的前提）", False,
                  "%d/%d 段缺 ancestors、%d 段缺 page —— 探针是旧版，重跑 probe_panels.mjs"
                  % (len(no_anc), len(unmarked), len(no_pg)))
        else:
            # ⚠⚠ 第三十三笔之十三：把**纯壳**从真孤儿里剔出去。
            #   壳 = 去掉「也在清单里的后代」之后**一个字都不剩**的块。
            #   它不该叫「没人读」：它**没有承载任何自己的主张**，
            #   而它的每一个字都出现在它某个子节点上 ——
            #   而那些子节点**各自都在这份清单里**。
            #   ⇒ 剔掉它不丢任何信息，只是不再**把壳算成缺口**（那是夸大）。
            #   ⚠ 上一版还只认「文本与某个后代**完全相同**」的纯壳，
            #     大量容器是**多个后代文字的拼接**，一个字都不少只是换个拼法
            #     ⇒ 溜过去被算成缺口。实测 107 条里有 25 条是这种。
            shells = [u for u in unmarked if u.get("orphan") and u.get("shell")]
            orphans = [u for u in unmarked if u.get("orphan") and not u.get("shell")]
            # ⚠ 剔壳**不是**让它悄悄消失：必须证明剔掉的确实是壳。
            #   判据：ownLen 必须真的是 0，且 len 不能也是 0
            #   （两者都 0 的话那是「本来就没文字」，不是壳，是另一回事）。
            bad_shell = [u for u in shells
                         if u.get("ownLen") != 0 or (u.get("len") or 0) == 0]
            check("C6a 被剔出缺口的「纯壳」必须真的一个字都不剩"
                  "（ownLen=0 且它本身 len>0；两者都 0 的不是壳，是空块）",
                  not bad_shell,
                  "壳 %d 条，冒充的有 %d 条" % (len(shells), len(bad_shell))
                  + ("：%s" % "、".join("%s/%s" % (u["tag"], u.get("head", "")[:20])
                                    for u in bad_shell[:4]) if bad_shell else ""))
            by_o = {}
            for u in orphans:
                by_o[(u["page"], u["panel"])] = by_o.get((u["page"], u["panel"]), 0) + 1
            # ⚠⚠ 第三十三笔之十四：会自己变的块**单独分层**，不混进「未分类」。
            #   它们的 key（含步号、tokens 数…）每轮都不同 ⇒ 登记必然 stale，
            #   而 stale 条目会被 stale_reg 报成「登记过但页面上没有」——
            #   那是**登记簿自己造的假警报**，会让人去删一条本来该留的登记。
            #   ⇒ 这类块的归属是**一个决定**（这类实时读数算不算覆盖缺口），
            #     不是逐条能定的事，所以先分层印出来等人裁决。
            orph_vol = [u for u in orphans if u.get("volatile")]
            # ⚠⚠⚠ **实时读数不算覆盖缺口** —— 政策裁决 2026-10-07。
            #
            #   这类块的文字里带**当前时刻的数**（`connected 112 steps`、
            #   `step 112 · change… ppl 1.00 · entropy 0.01`、`mean step 30.1150`…）。
            #   它们不能按 key 登记：okey 的第三段是 `head[:24]`，而 head 里就有那个数，
            #   ⇒ key 每轮都变 ⇒ 登记必然 stale ⇒ 登记簿自己会报
            #   「登记过但页面上没有」，那是**登记簿制造的假警报**。
            #   （这个坑原代码的注释已经预言了。）
            #
            #   **为什么它们不算缺口**，理由要能被下一个人核对：
            #     ① 任何按标记定位的判据，对它们最多只能做「此刻值是否自洽」；
            #     ② 而「此刻值」的**跨轮核对**已经由产物侧判据承担
            #        （每个数都是从 JSON 独立重算的，页面只是它的一份可见副本）；
            #     ③ 换句话说：它们**已经被核过**，只是核的入口在产物不在 DOM。
            #        C6 问的是「有没有判据能**定位到它**」，不是「有没有核过它」——
            #        这两个问题混在一起，正是 C6 自己警告过的「不等于没人读」。
            #
            #   ⇒ 豁免的粒度是**探针给的 volatile 标志**，不是任何一份手抄名单。
            #     这样它不会 stale，也不可能被「顺手多豁免几个」做坏：
            #     要多豁免只能去改探针的 volatile 判定，而那会被别的判据看见。
            #   ⚠ 每轮都把被豁免的原文打出来 —— 豁免不许是黑箱：
            #     如果哪天一个**不该变**的块被标成 volatile，输出里立刻看得见。
            ukeys = assign_keys([u for u in orphans if not u.get("volatile")])
            unclassified = sorted({k for k in ukeys
                                  if k not in ORPHAN_DECORATION
                                  and k not in ORPHAN_DEBT})
            orph_dec = [k for k in ukeys if k in ORPHAN_DECORATION]
            orph_debt = [k for k in ukeys if k in ORPHAN_DEBT]
            # 登记簿里已经不在页面上的条目要报出来（C4 有同样的 stale 检查）：
            #   否则「登记过就永远绿」—— 页面改了、标记搬走了，簿子不会自己发现。
            live = set(assign_keys(unmarked))
            stale_reg = sorted((set(ORPHAN_DECORATION) | set(ORPHAN_DEBT)) - live)
            if stale_reg:
                print("       ⚠ 登记簿里有 %d 条在两页 DOM 上都不存在：%s"
                      % (len(stale_reg), "、".join(k[1] for k in stale_reg[:6])))
            check("C6 「块级无标记且祖先链也为空」的块，必须**逐条有归属**"
                  "（= 没有任何按标记读的判据能定位到它；⚠ 这不等于「没人读」，"
                  "已有反例：ControlPanel 那段被 verify_picker 全文 includes 过）"
                  "　⚠ 第三十三笔之十一改过判据形状：判「未登记的 = 0」而非「总数 = 0」，"
                  "理由见上面那段注释",
                  len(unclassified) == 0,
                  "真孤儿 %d 段 %s；已登记 装饰簿 %d + 欠账簿 %d，**新增未分类 %d** 段%s%s"
                  % (len(orphans),
                     ("：" + "、".join("%s 页 %s=%d" % (pg, k, v)
                                      for (pg, k), v in sorted(by_o.items())))
                     if by_o else "",
                     len(orph_dec), len(orph_debt), len(unclassified),
                     ("：" + "、".join(k[1] for k in unclassified[:6])
                      + ("…" if len(unclassified) > 6 else ""))
                     if unclassified else "（全部已逐条登记）",
                     ("；⊘ 其中 **%d 段会自己变**（%s）——**按政策豁免，不算缺口**"
                      "（2026-10-07 裁决：实时读数的内容每轮都不同，**不能按 key 登记**，"
                      "登记必然 stale；而它们的**跨轮核对已由产物侧判据承担**，"
                      "C6 问的是「有没有判据能定位到它」，不是「有没有核过它」）"
                      % (len(orph_vol),
                         "、".join("%s 页 %d" % (pg, sum(1 for u in orph_vol
                                                       if u["page"] == pg))
                                   for pg in sorted({u["page"] for u in orph_vol}))))
                     if orph_vol else ""))
            # ⚠ 豁免不许是黑箱：被豁免的原文每轮都打出来。
            #   哪天一个**不该变**的块被探针标成 volatile，这里立刻看得见。
            for u in orph_vol[:12]:
                print("       ⊘ 已豁免（实时读数）：<%s> %s"
                      % (u.get("tag", "?"), u.get("head", "")[:64]))
            # ⚠ 逐条列名（这就是 C5 承诺的「只报数不列名 = 没有信息」）。
            for pg, v in sorted(unmarked_by_page.items()):
                og = [u for u in v if u.get("orphan")]
                if not og:
                    continue
                un = [u for u, k in zip(og, assign_keys(og)) if k in set(unclassified)]
                cap = 30
                print("       ── 真孤儿明细（%s 页 %d 段；未分类 %d 段%s）："
                      % (pg, len(og), len(un),
                         "，每页最多列 %d 条" % cap if len(un) > cap else ""))
                for u in un[:cap]:
                    print("         <%s> %3d 字 %s %s"
                          % (u.get("tag", "?"), u.get("len", 0),
                             "⚠会变" if u.get("volatile") else "    ",
                             u["head"][:60]))
                if len(un) > cap:
                    print("         …… 该页其余 %d 条未分类见 probe_panels.mjs 的 stdout"
                          % (len(un) - cap))


    failed = [r for r in results if not r["ok"]]
    print("\nRESULT panel_coverage  %s  %d/%d 条通过"
          % ("RED" if failed else "GREEN", len(results) - len(failed), len(results)))
    for f in failed:
        print("   [FAIL] " + f["name"])
    return 1 if failed else 0


def abort(reason, hint_lines):
    """提前退出时**必须自己明说**是哪一种状态。

    ⚠ 第十二笔：早退分支原来只 `return 1`，整个脚本**一行 RESULT 都不印**。
      调用方惯常 `grep '^RESULT'`，于是得到 0 行 ——
      分不清「判红」和「一条都没跑」，而这两者要做的动作完全不同。
      这与 §8.9 第十笔「汇总行自己也不许撒谎」同族：
      **判红 / 装置崩 / 一条都没跑是三件事，第三件要自己报出来。**
    """
    failed = [r for r in results if not r["ok"]]
    for ln in hint_lines:
        print("       ⇒ " + ln)
    print("\nRESULT panel_coverage  FAIL  %d/%d 条通过 —— **一条都没跑完**（%s）"
          % (len(results) - len(failed), len(results), reason))
    if failed:
        for f in failed:
            print("   [FAIL] " + f["name"])
    return 1


if __name__ == "__main__":
    sys.exit(main())
