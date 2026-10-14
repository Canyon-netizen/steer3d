#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 188 追加脚本 —— 用户拍板「3 跑」：C0 闸已实现、已跑、已双向证伪。

本节五块：
  188.1 C0 加第 7 条件：两支探针的 WebGL 档位必须一致
  188.2 前置：为什么必须用 next start 而不是静态服务器
  188.3 覆盖前先备份旧存档（沿用修订 186 的教训）
  188.4 双向证伪
  188.5 跑出来的附带发现：C2 转红（真死引用）
"""

from pathlib import Path

SECTION = """
## 修订 188 —— 用户拍板「3 跑」：C0 闸已实现并跑通；顺手查出一条真死引用

拍板记录：`1修了2改3跑` ⇒ 第 3 项「跑 C0 闸」。

### 188.1 C0 加第 7 个条件：两支探针的 WebGL 档位必须一致

**加之前**：`scan_panel_coverage.py` 全文 `grep webgl` = **零次**。
⚠⚠⚴ 而档位约定其实**写在探针的注释里**（`probe_panels.mjs:41-49`
「两支探针必须开同一个开关」）—— 也就是说这条约定只活在注释中，
**扫描器从来没查过**。

档位的来源链已核清：

    环境变量 BV_PROBE_WEBGL=1  ->  WEBGL_FLAGS（两个 swiftshader flag）
      ->  probe_panels.mjs:524   webglRequested = WEBGL_FLAGS.length > 0
      ->  产物 JSON 顶层字段

加进 C0 的判据（原 6 条变 7 条）：

    _webgl_by_page = {page: 产物里的 webglRequested}
    _wg_present = 两页都有该字段
    _wg_same    = 两页都有 且 取值集合大小为 1
    C0 判据 ... and _wg_same
    并且 _wg_same 为假时 **abort**（一条都不往下跑）

**为什么它必须进 C0 而不是只印出来**：
两页若跑在不同档位上，一页看得见 3D 块、另一页看不见，
合并后的 DOM 就会「多出」或「少掉」真 3D 标记 ——
报出来的现象长得像「覆盖矩阵有缺口」，**而缺口是采集环境造出来的**。
⚠ 与修订 180.3 同一族：让结论变得不可读的东西，在仪器里。

### 188.2 前置：必须用 `next start`，不能用静态服务器

⚠⚠⚴ 上一轮有人用 `python3 -m http.server` 起在 8931 上跑过一次装置自检，
拿到 `RESULT OK 36/36`，看着是通的。**但那不是产品的服务方式**：
根页是 Next.js 应用，`NEXT_PUBLIC_WS_URL` 是**构建期内联**的，
静态服务器直接把旧产物端出去，不代表产品真实服务的样子。

本轮按 `mut_j12.sh:100-130` 那条**已验证过**的配方起服，
并保留其中最要紧的一条 —— **bundle 自证**：

    curl 到 200 **不能**证明在服务的是本轮构建
    （端口上可能还挂着上一轮的 next start，它持有旧 .next 映射）
    => 必须回 chunk 里验 WS 地址；不对就换端口重跑

实测（`r188_start_next.sh`）：

    本轮端口 22655；就绪 6s
    本轮服务的 chunk /_next/static/chunks/app/page-c471fe264bf05dc4.js
    该 chunk 里的 WS 地址 ws://127.0.0.1:9505/ws  ⇒ 与 NEXT_PUBLIC_WS_URL 一致 ⇒ 自证通过

### 188.3 覆盖前先备份（沿用修订 186 的教训）

⚠ 修订 186 刚犯过「固定落盘名把上一轮证据覆盖掉」。本轮要重写两份存档，
⚠ 于是**先备份再覆盖**：

    panel_blocks.json         -> panel_blocks_r188bak_1014_223017.json
    panel_blocks_latent.json  -> panel_blocks_latent_r188bak_1014_223017.json

⚠⇒ 固化：**要覆盖任何已被引用为证据的文件，先按时间戳留一份。**
⚠ 这条是修订 186 的镜像（那里是「忘了留」，这里是「主动留」）。

### 188.4 双向证伪

| 方向 | 条件 | 期望 | 实得 |
|---|---|---|---|
| A | 两页都 `webglRequested=true`（实测采集） | C0 绿 | `[PASS] C0` 且印 `WebGL 档位 两页自报=latent=True、root=True，一致=True` |
| B | 人为把 latent 改成 `false` | C0 红 | `[FAIL] C0`，`一致=False`，**且 abort**：`RESULT panel_coverage FAIL 1/2 条通过 —— 一条都没跑完` |

⚠⚠⚴ 方向 B 的判据要看**红在哪**：`一致=False` 才是这一条该红的理由。
⚠ 若它红在「年龄」或「比源码旧」上，那是别的条件坏了，不是这条有牙齿。

### 188.5 跑出来的附带发现

**整体：`RESULT panel_coverage RED 11/14 条通过`。** 红的三条是 C2 / C4 / C6 ——
其中 C4、C6 正是待拍板的第 4、5 项（本轮用户未提及，按原状不动）。

⚠⚠ **C2 从「条件块」变成「真死引用」了**：

    ○ data-scene-token-badge 根页真 3D 路径专属的 HUD 标签（Scene3D.tsx:266）
      verify_scene_link :302 读它，且那条是**唯一**验「3D 展示 hidden states
      如何推导出 token」的判决（J6）

而本轮 C3 同时印了：

    ✓ **本轮 WebGL 可用**（DOM 里已出现 4 个 data-scene-*：
      data-scene-focus-state, data-scene-loaded, data-scene-window-high, data-scene-window-low）

⚠⇒ **WebGL 可用时，4 个 data-scene-* 真的进了 DOM，
⚠ 而 data-scene-token-badge 仍然没有。**
⚠⇒ 它不再能用「降级 DOM 上没有它」解释 —— 降级根本没发生。
⚠⚠⚴ **本轮把那个借口亲手拆掉了**：此前 C2 之所以没红，是因为它被算成
「WebGL 条件块」；而「WebGL 不可用」这个前提是探针默认关开关造成的，
⚠ 不是产品属性。开开关之后这个前提不成立了。

⚠ 这条**待拍板**（它涉及 J6 那条唯一验 token 推导的判决），本轮只报不改。

### 188.6 本节不含 P6 结论

§167 不变：本节写作时跑批 46/60，未跑满，不给 P6 结论。
"""

PRECHECKS = (
    ("无 U+FFFD 坏字", lambda s: chr(0xFFFD) not in s),
    ("无反斜杠续行", lambda s: chr(92) + chr(10) not in s),
    ("以换行结尾", lambda s: s.endswith(chr(10))),
    ("标题格式合规", lambda s: s.lstrip(chr(10)).startswith("## 修订 188 ")),
    ("含本节入口", lambda s: "188.6 " in s),
)


def main():
    target = Path(__file__).resolve().parents[2] / ".cache/xcheck/R6_RERUN_PREREG.md"
    before_lines = len(target.read_text(encoding="utf-8").splitlines())

    bad = [name for name, fn in PRECHECKS if not fn(SECTION)]
    if bad:
        print("[前置检查失败] " + " / ".join(bad))
        return 2

    with target.open("a", encoding="utf-8") as fh:
        fh.write(SECTION)
    after_lines = len(target.read_text(encoding="utf-8").splitlines())

    print("追加完成：%d -> %d 行（+%d）" % (before_lines, after_lines,
                                        after_lines - before_lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())