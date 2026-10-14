#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 192 追加脚本 —— C2「真死引用」的根因不在标记上：数据源根本没活。

本节三块：
  192.1 帧从哪来，以及为什么它一帧都没来
  192.2 ⛔ 探针的「就绪」信号既接错了面板，又分不出「等到了」与「等超时」
  192.3 同一个盲点的上一层：J3b 把「流没开始」读成「流停了」
"""

from pathlib import Path

SECTION = """
## 修订 192 —— ⛔ C2 那条「真死引用」的根因不在标记上：**数据源根本没活**

修订 188 报 `data-scene-token-badge` 是真死引用，修订 191 已把它降级成
「条件标记，前提未满足」。⚠⚠⚴ **本节把前提本身查穿了：那不是一个「未满足」，
而是**采集时数据源就没活着** —— 而没有任何一层检查过这件事。

### 192.1 帧从哪来，以及为什么它一帧都没来

来源链（逐段读过）：

    frontend/lib/ws-client.ts:50    this.ws = new WebSocket(this.url)
    frontend/lib/ws-endpoint.ts:33  NEXT_PUBLIC_WS_URL 优先
    store.ts:119                    ingestFrame: (f) => set({ frames:[…], latest: f, … })
    Scene3D.tsx:346                 const latest = useApp((s) => s.latest)
    Scene3D.tsx:232                 if (!latest) { … }      <= 徽章挂在这

⚠⚠⚴ **实测 `lsof -nP -iTCP:9505 -sTCP:LISTEN` 为空 —— 后端没在听。**
⚠⇒ WebSocket 从来没连上 ⇒ 一帧都没进来 ⇒ `latest` 恒为 `null`
⚠⇒ 徽章永不渲染。**与 WebGL 无关、与降级无关、与代码没人走无关。**

⚠ 而本会话起 `next start` 时是**照 `mut_j12.sh` 配方**做的，
⚠ 配方里 `NEXT_PUBLIC_WS_URL` 设了、bundle 自证也验过 WS 地址在内联里 ——
⚗⚠ **验的是「地址被正确内联」，不是「那个地址上有人接」。**
⚗⇒ bundle 自证通过与后端活着，是两件独立的事；前者不能推出后者。

### 192.2 ⛔ 探针的「就绪」信号既接错了面板，又分不出等到了没有

`probe_panels.mjs` 的就绪循环：

    for (let i = 0; i < 20; i++) {
      const s = …; if (ready) break;
      await sleep(1200);
    }

⚠⚠⚴⚠ **三个问题叠在一起：**

1. **接错面板**：根页等的是 `[data-outcome="ready"]`，那是
   `InterventionOutcomePanel`（:476/487/500 三态），
   ⚠ 与 Scene3D 的 frame 流**没有任何因果关系**。
   ⇒ 该面板报 ready，**不代表数据源活着**。
2. **分不出等到了没有**：循环正常结束（20 次空转耗尽）与 `break` 走出去，
   ⚠⚠ **在控制台上长得一模一样**。
   ⚠ 脚本自己的注释（:58-60）已经写了这一条：
   「『等超时』和『等到了』长得一模一样」。
3. ⚠⚠⚴ **产物里没有记录**。实测根页存档 13 个顶层键，
   ⚠ **没有任何一个字段记录「就绪等到了没有」**。
   ⇒ 下游（`scan_panel_coverage.py` 的 C2）**无从判断**，
   ⚠ 只能把「这个标记不在」读成「这个标记不存在」。

⚠⚠⚴ **⇒ C2 那句「真死引用」是采集环境的产物，不是产品属性。**
⚗⚠ 与修订 180.3 同一族：**仪器在它没量到的那个维度上下了结论。**

### 192.3 同一个盲点的上一层：J3b 把「流没开始」读成「流停了」

`verify_scene_link.mjs` 里 J3b 是「3D 的数据流会**停下来**」
（它是 J4/J6/J7/J8/J9a/J10 的前提）。它的判法是**盯 `loaded` 不再变化**。

⚠⚠⚴⚠ **`loaded` 恒为 0 也同样「不再变化」** ⇒ 一个**从未开始**的流，
⚠⚠⚴ 在 J3b 眼里就是一个**已经停下**的流 ⇒ J3b 判 PASS，
⚠⚠⚴ 于是后面那六条「前提已建立」的判据全部照跑，读的是 frames=0 的页面。

⚠ 这不是我推测的：脚本注释 :432-433 已经记过同一个病：
「消息说一套、布尔值做另一套。于是 J3b 在 209/784 步时判 PASS，
⚠ 而它自己的 detail 明写着那不是真停。」
⚠⚠⚴ 差别只是：那次是**没跑完被误判成停了**，这次是**压根没跑也被当成停了**。
⚗⚠ **同一个判据，两种「停」，其中一个是假的。**

⚠⚠⚴ **「不再变化」与「曾经变化过」必须分开量。**
⚠ 一个只读「稳不稳」的探针，量不出「有没有开始过」。

### 192.4 由此得到的三条（待拍板，本节一条都不实施）

1. ⛔ **数据源存活检查**：任何要读 `data-scene-*` 的判据，
   ⚠ 前置必须是「帧流确实开始过」，而不是「loaded 不再变化」。
2. ⛔ **探针产物必须自报**：`readyWaited: true/false` + `readyAttr` + `waitedMs`，
   ⚠ 让「等到了」与「等超时」在产物里就是两种东西。
   ⚗⚠ 这一条是**最少改动、收益最大**的一条：它不改变任何判据语义，
   ⚗⚠ 只是让下游有可能知道它刚才看到的是什么状态。
3. ⛔ **C2 遇到「条件标记缺席」时不该直接判死引用** ——
   ⚠ 该先问「它的前提在本环境里成立过吗」。

⚠⚠⚴ 三条都不在本轮授权范围（用户拍的是 1/2/3 三项，都已落地），
⚠⚠⚴ 且第 2、3 条要改判据侧语义，**按修订 187 记的同一条纪律须先拍板**。

### 192.5 本节不含 P6 结论

§167 不变：跑批 48/60，未跑满，不给 P6 结论。
"""

PRECHECKS = (
    ("无 U+FFFD 坏字", lambda s: chr(0xFFFD) not in s),
    ("无反斜杠续行", lambda s: chr(92) + chr(10) not in s),
    ("以换行结尾", lambda s: s.endswith(chr(10))),
    ("标题格式合规", lambda s: s.lstrip(chr(10)).startswith("## 修订 192 ")),
    ("含本节入口", lambda s: "192.5 " in s),
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