#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 191 追加脚本 —— commit message 引用的备份文件没进仓库。

起因：把最近四笔 commit message 里提到的每个文件路径逐条核对
（「能不能在 git show --name-only 里找到，或已被跟踪」），
发现修订 188 message 里引用的两份存档备份**未被跟踪**。
"""

from pathlib import Path

SECTION = """
## 修订 191 —— 复核 commit message 的文件引用：抓到一份「引用了但没入库」

### 191.1 怎么发现的

对最近四笔提交做了一次机械核对：
**message 里提到的每个文件名，要么在 `git show --name-only` 里，要么已被 git 跟踪。**

这条核对本身抓到两个不同性质的问题：

| 现象 | 性质 |
|---|---|
| message 明确写了「未入版本控制（合成夹具）」 | ✅ 声明过，正常 |
| message 引用了某文件当证据，而那个文件**没被跟踪** | ⚠⚠ 本节要处理的 |

第一类出现在修订 187（两份合成夹具）与修订 190（改前备份），
message 里都写明了为什么不提交，**不算漏**。
第二类出现在修订 188。

### 191.2 修订 188 引用的备份没进仓库

修订 188 的 message 写：

    三、覆盖前先备份（修订 186 的镜像）
      panel_blocks_r188bak_1014_223017.json /
      panel_blocks_latent_r188bak_1014_223017.json

⚠⚠⚴ **这两份文件没有被 git 跟踪。**
⚠⚠⚴ 而更要紧的是，查提交历史发现：

    `git log -- .cache/browser_verify/panel_blocks.json` **只有一笔提交**，
    就是修订 188 本身。

⚠⚠⚴⚠ **⇒ 本会话之前那份存档（7+ 小时前的那份）从未进过任何仓库。**
⚠⚠⚴⚠ ⇒ 刷新前的状态**只存在于这两份未跟踪的备份文件里**。
⚠⇒ 它们一旦被清掉，「先备份再覆盖」这个动作**就不可复核了** ——
⚗ 而那正是修订 186 刚立的纪律（「结论对但证据没进仓库」是同一种不可复核）。

⚠ 顺带核实过：备份文件**确实存在**（337 KB / 144 KB，mtime 22:30），
⚠ 第一次核对报「文件不存在」是我那个核对脚本的兜底路径只查了
`mutbak/` 与 `xcheck/` 两处，漏了 `browser_verify/` ——
⚗⚠ **假警报**。已改为按 basename 全仓找。

**处置：两份备份入库**（合计约 480 KB）。

### 191.3 顺带记两件事

**(a) `mut_j12.sh` 未被跟踪，但配方已经固化。**
修订 188 的 message 引用了 `mut_j12.sh:100-130` 那条起服配方。
⚠ 那份脚本本身不在 git 里。
⚠ 但本轮起服用的 `r188_start_next.sh`（**已跟踪**）把配方逐条抄了进去，
⚠ 含 bundle 自证那段。⇒ 配方本身**不依赖**那个未跟踪文件，可独立复核。

**(b) 旧存档为何从未进仓库，值得单独问一句。**
`.cache/browser_verify/panel_blocks*.json` 是探针产物，
量级几百 KB 到几 MB。⚠ 「没进仓库」可能是**有意的**（产物不入库，gitignore 覆盖），
⚠ 也可能是**一直没想起来**。
⚠⚠⚴ 本节不擅自改这个策略 —— 但它直接决定了 191.2 是不是「我该补救」还是「按规矩本就不入」：
⚠ **探针产物若是产物，就不该只靠工作区留存**，
⚠ 因为 C0/C2/C4 全部以它为唯一输入，**它没了这整套判据就没有数据源**。

⛔ **待拍板**：`.cache/browser_verify/` 下的探针产物要不要入库？
⚠ 本节只把「旧存档从未入库」这个事实记下来，不改策略。

### 191.4 顺带查清了「token-badge 是真死引用吗」

修订 188 报 C2 转红，说 `data-scene-token-badge` 是真死引用，
并把它列为**新增待拍板项**。本轮把它查成了可决策的证据。

**渲染条件链**（逐段读过源码）：

    Scene3D.tsx:223  function CurrentTokenPulse({ latest })
    Scene3D.tsx:232    if (!latest) { … }        <= 徽章挂在这个函数里
    Scene3D.tsx:365    <CurrentTokenPulse latest={latest} />
    Scene3D.tsx:346    const latest = useApp((s) => s.latest)
    store.ts:119       ingestFrame: (f) => set({ …, latest: f, … })
    store.ts:165       reset: () => set({ …, latest: null, … })

⇒ **徽章要等第一帧 ingest 之后才出现**，与 WebGL、与降级路径都无关。

⚠⚠⚴ 而面板探针 `probe_panels.mjs:32` 的根页就绪信号是 `[data-outcome="ready"]`，
⚠⚠⚴ 那是 `InterventionOutcomePanel`（:476/487/500 三态），
⚠⚠⚴ **与 Scene3D 的 frame 流没有任何因果关系**。
⚠⇒ 「存档里没有这个标记」与「这个标记永远不存在」**是两件事**，而 C2 报的是后者。

**实测分辨**（`r190_token_badge_probe.mjs`，开 WebGL，**不设就绪门**，
每 3s 轮询、最多 150s）：

    t= 66s  token-badge=（无）  data-scene-loaded=0  canvas=true  fallback=false
    …
    t=150s  token-badge=（无）  data-scene-loaded=0  canvas=true  fallback=false

⚠⚠⚴⚠ **判读（这一步是本节的重点）：**

- `canvas=true, fallback=false` ⇒ **真 3D 路径确实在跑**，降级没发生
  ⇒ 修订 188.5 里「不再能用降级 DOM 解释」那句**是对的**；
- 但 `data-scene-loaded=0` 全程没变 ⇒ **一帧都没进来**
  ⇒ 徽章不出现的原因是 **`latest` 恒为 null**，不是「这段代码没人走」。

⇒ **C2 的「真死引用」判错了理由。** 准确说法是：
   它是一个**条件标记，其前提（frames 已 ingest）在探针环境里从未被满足**。

⚠⚠⚴ 而这牵出**另一件更要紧的事**：`data-scene-loaded=0` 持续 150 秒，
⚠⚠⚴ 说明**这个环境里根本没有轨迹在流**。
⚠⚠⚴ 根因不在 `token-badge` 上，而在「页面没有被喂一条轨迹」这一步。
⚠⚠⚴ 而 J6（`verify_scene_link.mjs:302`）读的正是那个徽章 ——
⚠⚠⚴ **它在「没有轨迹」的状态下读一个「只在有轨迹时才存在」的标记。**
⚗⚠ 这不是判据写错了，是**判据与就绪条件脱节**：
⚗ 要么判据该自己把轨迹喂上再读，要么该把这条登记成「前提不满足」而不是「死引用」。

⚠ 顺带对照：另外 4 个 `data-scene-*`（loaded / window-high / window-low /
⚠ focus-state）挂在**无条件**渲染的那个 `<Html>` 上，它们在 frames=0 时也在 ——
⚗⇒ 所以探针快照里看得到 4 个、看不到第 5 个，**这个「4 vs 1」的落差本身就是线索**。

⛔ **待拍板（本节只把证据摆齐，不改代码）**：J6 与 token-badge 这条怎么办 ——
⚠ 三个方向：① 判据侧先把轨迹喂上 ② 登记成「前提不满足」而非死引用
⚠ ③ 页面侧让徽章在 frames=0 时也渲染一个空态。

### 191.5 本节不含 P6 结论

§167 不变：跑批 46/60，未跑满，不给 P6 结论。
"""

PRECHECKS = (
    ("无 U+FFFD 坏字", lambda s: chr(0xFFFD) not in s),
    ("无反斜杠续行", lambda s: chr(92) + chr(10) not in s),
    ("以换行结尾", lambda s: s.endswith(chr(10))),
    ("标题格式合规", lambda s: s.lstrip(chr(10)).startswith("## 修订 191 ")),
    ("含本节入口", lambda s: "191.4 " in s),
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