#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""面板覆盖矩阵：把「页面上真实渲染的块」与「判据实际读过的块」摆在一起对账。

## 为什么要它

§8.3 ⑨ 已经立了一条规矩：**判据与被观测层要分别记账**，
一个页面判据集里一定存在「渲染上看不见」的改动类别。
这条规矩的反面同样要立：**页面上的块是否都被判据读过**。
一个没人读的块，在覆盖率统计里和「不存在」是同一件事。

## 它**不能**证明什么（必须一起说，否则这张表会骗人）

1. **3D 场景的全部标记在本环境验不了。** 沙箱 Chromium 没有 WebGL，
   页面走的是 `data-testid="scene3d-fallback"` 2D 降级，
   于是 `data-scene-*` / `data-bm*` 在 DOM 里**根本不存在**。
   ⇒ 它们不算「死引用」，但**也不能算「验过了」**。
   本守卫把它们单列成一类，并要求把这句话印出来。
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
    # ⚠ 第三十一笔：这两个只在下拉框切到第 5 档（extraction_layer_effect.json）
    #   时才渲染，而默认 idx=0 ⇒ 覆盖扫描看到的根页 DOM 上没有它们。
    #   它们**不是**死引用：Q0 会逐档切过去，Q1 用它们做交叉核对。
    "data-ta-gap-lo": "ArchivedExperiments 第 5 档（ExtractionTable）专属，"
                      "默认 idx=0 不渲染；Q0 逐档切过去核，Q1 用它交叉核对。",
    "data-ta-gap-hi": "同上。",
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

# 只在 WebGL 可用时才渲染的标记 ⇒ 本环境**无法验证**，既不算死引用，
# 也不能算验过。必须连同这句话一起印出来。
CONDITIONAL_3D = {
    "data-scene-loaded", "data-scene-focus", "data-scene-focus-miss",
    "data-scene-focus-state", "data-scene-focus-step", "data-scene-focus-token",
    "data-scene-window-high", "data-scene-window-low",
    "data-bmroot", "data-bmstep", "data-bmgrid", "data-bmgridn",
    "data-drawn", "data-frac", "data-pfinal", "data-ok",
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
    unmarked = raws[BLOCKS].get("unmarked") if isinstance(raws[BLOCKS], dict) else None
    flat = [it for items in Bs[BLOCKS].values() for it in items]
    has_all = all("all_data" in it for it in flat)
    # ⚠ 两份产物必须**自报是哪一页**，且不能都报同一页。
    #   少了这一条，两次探针都跑同一个 URL 也会「都成功」，
    #   而 latent 页的 36 个标记一个都没进矩阵 —— 看起来一切正常。
    pages = {p.name: (raws[p].get("page") if isinstance(raws[p], dict) else None)
             for p in (BLOCKS, LATENT_BLOCKS)}
    page_ok = (pages[BLOCKS.name] == "root"
               and pages[LATENT_BLOCKS.name] == "latent")
    src_mt, src_which = newest_source_mtime()
    blocks_mt = min(p.stat().st_mtime for p in (BLOCKS, LATENT_BLOCKS))
    # 产物必须比**被测源码**新。只比绝对年龄是不够的（见 SRC_GLOBS 上方注释）。
    # ⚠ 用两份里**更旧**的那份比：只要有一份比源码旧，那一页的数字就不可信。
    newer_than_src = (src_mt == 0.0) or (blocks_mt > src_mt)
    check("C0 两页探针产物新鲜、字段完整、且各自自报是哪一页",
          has_all and page_ok and max(ages.values()) < 7200 and newer_than_src,
          "根页 %d 秒前 / latent %d 秒前；根页 %d 个元素，all_data 齐全=%s；"
          "page 字段 根=%s latent=%s；产物比最新源码（%s）新=%s（取两份里更旧的比）"
          % (ages[BLOCKS], ages[LATENT_BLOCKS], len(flat), has_all,
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
    # ⚠⚠ 负控：剥注释之后，**任何出现在方括号选择器里的标记都必须在**。
    #   剥注释器要处理字符串字面量（`page.eval(\`[data-x]\`)`）与
    #   `http://` 这类假注释头，两处都可能整段吃掉内容 ——
    #   而「少提取标记」的方向恰好是**假绿**（缺口被藏起来）。
    #   ⇒ 这条不是装饰：它一红就说明提取器坏了，后面每一个数字都不可信。
    lost = []
    for f in list(BVDIR.glob("verify*.mjs")) + list(BVDIR.glob("shot*.mjs")):
        raw = io.open(str(f), encoding="utf-8").read()
        got = set(markers_in(raw))
        for m in re.findall(r"\[(data-[a-z0-9-]+)[\]\s'\",]", raw):
            if m not in got:
                lost.append("%s: %s" % (f.name, m))
    check("C2a 剥注释不许吃掉任何方括号选择器里的标记（少提取 = 假绿）",
          not lost,
          "被剥掉 %d 个：%s" % (len(lost), ", ".join(lost[:6]))
          if lost else "全部 %d 个 verify/shot 文件的选择器都保住了"
          % len(list(BVDIR.glob("verify*.mjs")) + list(BVDIR.glob("shot*.mjs"))))

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
    check("C3 WebGL 条件块必须被显式标注为「本环境无法验证」",
          not cond or set(cond) <= CONDITIONAL_3D,
          "%d 个条件标记在本环境不可验（页面走 2D 降级）：%s"
          % (len(cond), ", ".join(cond) or "无"))
    print("       ⚠ 这 %d 个**不是死引用**，但也**不算验过**。" % len(cond))
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

    # ---- C5 / C6：段落级没有标记的那些 <p> ----
    # 覆盖矩阵统计的是「带 data-* 的块」。D6（归属论证那段 note）与
    # G7（caution_absorbed / control.note）那两个洞，恰恰是**一个 data-* 都没有**
    # 的 <p> —— 没有标记 ⇒ 不进矩阵。
    #
    # ⚠⚠ 但我原来在这里写的结论是**错的**，已改：
    #   「所以『未被读过』那一栏永远不会列出来」——**这句是错的，已改**。
    #   2026-10-03 实测（probe_unmarked_ancestors.mjs）：这 27 段**全部**落在
    #   某个带 data-* 的祖先里，祖先属性往往就带着同一句话的机器可读真值，
    #   例如 data-outcome#2 的祖先带 data-cos-up-down=-0.9999999999999997，
    #   正对应散文里的「cos = -1.0000」。
    # ⇒ 「自身无标记」≠「没人读」。真正无解的是**真孤儿**（祖先链为空），
    #   那是 C6；而 C5 只负责**列名**，不负责算数。
    if unmarked is None:
        check("C5 探针须给出「有文字但没标记」的段落清单", False,
              "探针产物里没有 unmarked 字段 —— 探针是旧版，重跑 probe_panels.mjs")
    else:
        by_panel = {}
        for u in unmarked:
            by_panel[u["panel"]] = by_panel.get(u["panel"], 0) + 1
        check("C5 「有实质文字、但段落级没被登记」的段落必须被逐条列名并计数",
              isinstance(unmarked, list) and len(unmarked) > 0,
              "%d 段，按面板：%s" % (len(unmarked),
              "、".join("%s=%d" % (k, v) for k, v in sorted(by_panel.items()))))
        nums = [u for u in unmarked if re.search(r"\d", u["head"])]
        print("       ⇒ 这 %d 段**段落级**没有标记，所以它们自己不会进矩阵；"
              % len(unmarked))
        print("         但这不等于「没人读」——见下面 C6 的祖先统计。")
        print("         其中一部分是纯说明文字（不该算缺口），")
        print("         另一部分带数字并承载论证（是真缺口）——")
        print("         **判据不许因为「它没被登记」就自动算数，必须逐段看。**")
        print("         前 70 字里带数字的有 %d 段（更可能是承载论证的）："
              % len(nums))

        # ---- C6：真孤儿必须为 0 ----
        # 「承载判决的那句话必须落在某个可读作用域里」——
        # 祖先链为空 = 任何按标记读的判据都够不着它，那才是真正的缺口。
        # 这条**能变红**：把任一段落挪到带标记容器之外，或删掉祖先的 data-*，
        # 孤儿数就会 >0。
        no_anc = [u for u in unmarked if "ancestors" not in u]
        if no_anc:
            check("C6 探针须给出每段的祖先链（判断真孤儿的前提）", False,
                  "%d/%d 段缺 ancestors 字段 —— 探针是旧版，重跑 probe_panels.mjs"
                  % (len(no_anc), len(unmarked)))
        else:
            orphans = [u for u in unmarked if u.get("orphan")]
            by_o = {}
            for u in orphans:
                by_o[u["panel"]] = by_o.get(u["panel"], 0) + 1
            # ⚠⚠ 第三十一笔：措辞不准确，已改。
        #   原话「承载判决的话不能无人可读」——**有反例**：
        #   ControlPanel 那 149 字的「这是回放」段落祖先链为空，
        #   但 verify_picker.mjs 里就写着 "Replaying a recorded"（全文 includes）。
        #   ⇒ **祖先链为空 ≠ 没人读**。它只说明「没有任何按标记读的判据能定位它」。
        #   阈值不动（仍然是 0），改的是这句话对自己的描述。
        check("C6 「段落级无标记且祖先链也为空」的段落必须为 0"
              "（= 没有任何按标记读的判据能定位到它；⚠ 这不等于「没人读」，"
              "已有反例：ControlPanel 那段被 verify_picker 全文 includes 过）",
                  len(orphans) == 0,
                  "真孤儿 %d 段 %s；其余 %d 段都落在带标记祖先里（祖先属性多半带着"
                  "同一句话的机器可读真值，是否真被核过仍要逐段看）"
                  % (len(orphans),
                     ("：" + "、".join("%s=%d" % (k, v) for k, v in sorted(by_o.items())))
                     if by_o else "",
                     len(unmarked) - len(orphans)))

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
