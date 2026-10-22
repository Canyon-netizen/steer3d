#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""pooled_mode_audit.py —— 「**合池模式**」（`n_bands = 1`）的**可算性审计**（244.74，零 GPU）。

🔴🔴 **本工具问什么**
   244.72 查出「固定剂量」那一批的**后果③**：
   **当前分析管线没有合池模式**（`dose_confound_audit.dose_bands_v` 拒绝 `n_bands < 2`）
   ⇒ ⇒ 「固定剂量」⇒ **剂量轴没有离散度可分** ⇒ 4 个分位切点会**切穿复制组**
   ⇒ ⇒ 唯一正确的分析口径是**合池（1 档 = 全池）**
   ⇒ ⇒ 而管线没有这一支 ⇒ ⇒ **跑完也算不出判决数** ⇒ ⇒ 那 5.65 GPU h 不该烧。

   ⚖⚖⚖ **244.74 给管线补上 `n_bands = 1` 那一支** ⇒ ⇒ **本工具验收这件事**：
      ① 加完之后**生产口径（4 档）逐位不变**吗？
      ② 加完之后**「固定剂量」那一批算得出判决数**吗？
      ③ 加完之后**口径站得住**吗（「未量到」不许被渲染成「无差异」）？

⚖⚖⚖⚖⚖ **判据 P1–P12**（每条**能红** ⇒ 自检里每条都配**正样 + 反例**）：
   P1  **生产口径（4 档）逐位不变**（档名逐字 + 分位点单调 + 守恒 + 分区精确）
       （期望 = **244.72 基线**的冻结字面量 ⇒ ⛔ 不许从被检对象派生）
   P2  **合池模式可用**（1 档 + 分位点**空表** ⇒ 没有剂量轴）
   P3  **合池档含全部格、每格恰一次**（守恒）
   P4  合池下**剂量趋势 = 未量到**（⛔ 绝不能是 p=1.0，那是「没测」被读成「无差异」）
   P5  `n_bands = 0` 必须被**拒**（且是管线那个 `HardFail` ⇒ 崩 ⛔ 不算按判据转红）
   P6  合池下**坏口径取值**也必须被拒（⛔ 不许在合池下被静默接受）
   P7  预登记 `n_bands = 1` **被接受**，**且预登记文件本身没被改**（口径切换**未发生**）
   P8  合池模式下**整条管线算得出判决数**（改判数 / 差 pp / p / 区间 / 块级）
   P9  合池下**剂量轴量标「未量到」**（⛔ 不是 0.0、不是 NaN、不是「无效应」）
   P10 合池下 boundary / quantile **结构上不参与**（6 个组合逐位相同 ⇒ 这是**实测**）
   P11 **跨轮一致性**：244.72 的密度审计器 **D8 必须转绿**（且阻断集里**不再有 D8**）
   P12 合池下的**规模措辞**必须换掉（⛔ 不许印「阶梯要扫到现在的 N 倍」）
   T13 **名实核对**那行诊断**必须印出来**（⛔ 印不出来就等于没说）

⚖⚠⚠⚖⚖⚖⚖⚖⚖ **244.74 顺带查出一条**既有缺陷**：本工具的**独立手算期望**
   （「文档里 inclusive 的定义」⇒ 夹具上应是 0.20/0.30/0.40）与管线输出
   （0.15/0.30/0.45）**不一致** ⇒ ⇒ 顺着查下去发现：
   `dose_bands_v` 的 `quantile="inclusive"` 那支调的是 `statistics.quantiles(fr, n=n_bands)`
   ⇒ **没传 `method`** ⇒ 而 Python 的**默认 `method` 是 `'exclusive'`**
   ⇒ ⇒ **`inclusive` 与 `exclusive` 两支算的是同一件事**
   ⇒ ⇒ 「四分位算法」这一维**结构上就是空的**
   ⇒ ⇒ 在**真实数据**（w 臂 109 格）上实测：分位点两者**相同**（0.015/0.250/0.750），
      但**档大小**不同：默认(exclusive) **27/28/30/24**（= 账本 244.50 登记值）
      vs 真 inclusive **28/27/30/24**（第一、二档对调 1 格）
   ⇒ ⇒ **账本登记的生产剂量轴其实是 exclusive 口径**（只是名字叫 inclusive）
   ⇒ ⇒ ⚠ **本轮不修**（改了＝改生产剂量轴 ⇒ 244.50/244.63/244.72 的登记值要重推
      ⇒ ⇒ **口径决定 ⇒ 要点头**）⇒ ⇒ 本轮只把它**测出来、印出来、记进账本**

⚖⚠⚠⚠⚖⚖ **本工具⛔ 不发批、⛔ 不改预登记、⛔ 不改格清单、⛔ 不改探针、⛔ 不产生任何判决数**
   ⇒ 它只回答「**合池模式这个口径站不站得住、管线算不算得出判决数**」。

⚖⚠⚠⚠⚠⚖⚖ **合成夹具里的数字（尤其 P8 印出来的那些）不是判决数**
   ⇒ 那批真实读数**还没跑**（要 GPU + 点头）⇒ ⇒ **真实判决数未量到**
   ⇒ ⇒ 引用 P8 的数时**必须**带上这句话。

⚖ 用法：
   `pooled_mode_audit.py`            （出报告；退出码 = 判据是否全绿）
   `pooled_mode_audit.py --selftest` （自检；每条判据的正样 + 反例）
"""

import collections
import importlib.util
import io
import json
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))

# ⚖⚖⚖ **基线夹具 + 基线期望**（⛔ **不许从被检对象派生** ⇒ 下面是**冻结的字面量**）
#
# ⚖ 13 个注入比例 ⇒ `(N−1)·p`（p = 1/4, 2/4, 3/4）在**exclusive** 定义下 = 2.5 / 6 / 9.5
#   ⇒ ⇒ 分位点 = 0.15 / 0.30 / 0.45 ｜ 档（prod 边界）= **(3, 6, 1, 3)**
#   ⚠⚠⚠ **这三个数的出处是「244.72 基线」**：`.cache/r244/_baseline_24472_dose_confound_audit.py`
#   （= git `84ac076` 那一份文件）**在这同一夹具上的逐位输出**（服务器实测，
#   见 `_measure_24474_inclusive.py` 的 ①）⇒ ⇒ 它们是**回归护栏**，不是「正确值」的断言
#   ⇒ ⇒ ⛔ **不许**在改完之后去「修」成别的数（那就是拿期望凑被检对象）
FIX_FR = (0.10, 0.10, 0.10, 0.20, 0.20, 0.20, 0.30, 0.30, 0.30, 0.40, 0.50, 0.50, 0.90)
BASE_Q = (0.15, 0.30, 0.45)
BASE_SIZE = (3, 6, 1, 3)
FIX_NAMES = ("frac<=q1", "q1..q2", "q2..q3", "frac>q3")

# ⚖⚠⚖⚖⚖⚖ **244.74 的实测发现（既有缺陷，本轮只测、只记）**：
#   `dose_bands_v` 的 `quantile="inclusive"` 那支调的是 `statistics.quantiles(fr, n=n_bands)`
#   ⇒ **没传 `method`** ⇒ 而 Python 的**默认 `method` 是 `'exclusive'`**
#   ⇒ ⇒ **`inclusive` 与 `exclusive` 两支算的是同一件事** ⇒ 「四分位算法」这一维**结构上就是空的**
#   ⇒ ⇒ 在**真实数据**（w 臂 109 格）上：分位点两者**相同**（0.015/0.250/0.750），
#      但**档大小**不同：默认(exclusive) **27/28/30/24**（= 账本 244.50 的登记值）
#      vs 真 inclusive **28/27/30/24**（第一、二档对调 1 格）
#   ⇒ ⇒ **账本登记的生产剂量轴其实是 exclusive 口径**（只是名字叫 inclusive）
#   ⇒ ⇒ ⚠ **本轮不修**：改了 ⇒ 生产剂量轴的档大小会变 ⇒ 244.50/244.63/244.72 的登记值
#      要重推 ⇒ ⇒ **口径决定 ⇒ 要点头** ⇒ ⇒ 本轮只把它**测出来、印出来、记进账本**
#   ⇒ ⇒ 下面的 `DOC_Q` 是**文档里 inclusive 的定义**算出来的值（只作对照 ⇒ ⛔ 不作期望）
DOC_Q = (0.20, 0.30, 0.40)

# ⚖ 244.50 的**账本登记值**（生产剂量轴）—— 打印时做**人眼对照**（⛔ 不参与判据：
#   真数据文件 `_an.txt` / `_ra.txt` **不在库里** ⇒ 不能让判据依赖它们）
REG_QUANTILES = (0.015, 0.250, 0.750)
REG_BAND_SIZE = (27, 28, 30, 24)

# ⚖ P8 要查的**判决数字段**（⛔ 少一个 ⇒ 就算不出判决数）
VERDICT_FIELDS = ("kw", "nw", "kr", "nr", "diff_pp", "p_perm", "fisher",
                   "wilson_w", "wilson_r", "newcombe", "bkw", "bkr", "nb")


# ⚖⚠⚖⚖ **本文件**刻意**不再**定义自己的 `HardFail`
#   ⇒ 理由：管线（`dose_confound_audit`）有自己的 `HardFail` ⇒ 两个类**不是同一个**
#   ⇒ ⇒ 拿本地的类去接 ⇒ 管线抛的会被当成「别的异常」⇒ ⇒ **244.74 第一版就栽在这里**
#   ⇒ ⇒ 需要接管线异常的地方，一律用 `dconf().HardFail`（**现取**，不缓存）


# ---------------------------------------------------------------- 模块加载
_MODS = {}


def _load(path, name):
    """⚖ **按路径**加载既有机械（⛔ 244.72 的教训：`import` 来的那份**不是**管线用的那份
    ⇒ ⇒ 对它打属性补丁**打不到** ⇒ ⇒ 只能按路径加载同一份**文件**）。"""
    if name in _MODS:
        return _MODS[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    _MODS[name] = mod
    return mod


def dconf():
    return _load(os.path.join(HERE, "dose_confound_audit.py"), "dc_24474")


def dlayer():
    return _load(os.path.join(HERE, "dose_layer_audit.py"), "dl_24474")


def fda():
    return _load(os.path.join(HERE, "fixed_dose_audit.py"), "fa_24474")


def fden():
    return _load(os.path.join(HERE, "fixed_dose_density_audit.py"), "fd_24474")


# ---------------------------------------------------------------- 判据（**纯函数**）
# ⚖⚖⚖ 判据写成**纯函数**（吃结果、吐 (ok, detail)）⇒ 自检里可以把**手写的坏结果**喂进去
#   ⇒ ⇒ 每条判据的「**能红**」是**可证的**（⛔ 不用靠变异台替它证明）
def _cells_of(bands):
    out = []
    for _lab, sub in bands:
        out.extend(sub)
    return out


def _fr_by_id(ks, fr):
    return dict((id(r), f) for r, f in zip(ks, fr))


def chk_prod_structure(qs, bands, ks, fr):
    """P1：生产口径（4 档）必须**逐位不变**。

    ⚖ 期望集 = **手写字面量**（档名）+ **可证明的性质**（单调 / 守恒 / 分区精确）
      ⇒ ⛔ **不许**从被检对象派生（那叫自反比较 ⇒ 恒绿）。
    """
    names = tuple(lab for lab, _sub in bands)
    if names != FIX_NAMES:
        return False, "档名 %s ≠ 手写的 %s" % (list(names), list(FIX_NAMES))
    if len(qs) != 3 or not (qs[0] <= qs[1] <= qs[2]):
        return False, "分位点必须 **3 个且单调**：%s" % (list(qs),)
    cells = _cells_of(bands)
    if len(cells) != len(ks):
        return False, "**守恒破了**：Σ各档 %d 格 vs 输入 %d 格" % (len(cells), len(ks))
    if len(set(id(c) for c in cells)) != len(ks):
        return False, "有格被**重复**放进多个档"
    fmap = _fr_by_id(ks, fr)
    # 分区**精确**：每格必须落在「**它自己的 f** 所对应的那一档」
    for i, (lab, sub) in enumerate(bands):
        for c in sub:
            f = fmap[id(c)]
            if i == 0:
                good = (f <= qs[0])
            elif i == len(bands) - 1:
                good = (f > qs[-1])
            else:
                good = (qs[i - 1] < f <= qs[i])
            if not good:
                return False, "格 f=%.6f 不在它该在的档「%s」里" % (f, lab)
    return True, "档名逐字相符、分位点单调、Σ档内==输入、每格落在自己那一档"


def chk_pooled_shape(qs, bands):
    """P2：合池必须是 **1 档 + 分位点空表**（没有剂量轴 ⇒ 没有分位点）。"""
    if len(bands) != 1:
        return False, "合池必须**只有 1 档**，实际 %d 档（档名 %s）" \
            % (len(bands), [lab for lab, _s in bands])
    if len(qs) != 0:
        return False, "合池必须**没有分位点**（空表），实际 %s" % (list(qs),)
    return True, "1 档（%s）+ 分位点空表 ⇒ 没有剂量轴" % (bands[0][0],)


def chk_pooled_conservation(bands, ks):
    """P3：合池档必须**含全部格、每格恰一次**（⛔ 漏格 = 判决的分母被悄悄改小）。"""
    cells = _cells_of(bands)
    if len(cells) != len(ks):
        return False, "合池档 %d 格 vs 输入 %d 格（**漏了 %d 格**）" \
            % (len(cells), len(ks), len(ks) - len(cells))
    if len(set(id(c) for c in cells)) != len(ks):
        return False, "有格被**重复**放进合池档"
    return True, "合池档含全部 %d 格、每格恰一次" % len(ks)


def chk_trend_unmeasured(call):
    """P4：合池（1 档）下**剂量趋势必须「未量到」**。

    ⚖⚠⚠⚖ **为什么这条最要紧**：`trend_weights(1) = [0.0]` ⇒ 统计量恒 0
    ⇒ ⇒ 零假设模拟**每次都 `ge`** ⇒ p = 1.0 ⇒ ⇒ **「没测」被渲染成「无差异」**
    ⇒ ⇒ 所以必须**显式拒绝**，而不是让它跑出一个数。
    """
    try:
        res = call()
    except Exception as e:
        msg = str(e)
        if "未量到" not in msg:
            return False, "拒绝的**不是**「未量到」的理由：%s" % msg[:120]
        return True, "趋势被**显式拒绝**（未量到）：%s" % msg[:90]
    return False, "趋势**没有被拒** ⇒ 返回了 %r（⛔ p=1.0 会被读成「无差异」）" % (res,)


def chk_hardfail(call, what, exc_cls):
    """P5/P6：坏输入必须被**拒**，且必须是**管线自己那个** `HardFail`
    （⛔ 别的异常 = 崩 ⇒ 崩⛔不等于抓到；
     ⚠⚠⚠⚠ **必须用管线那个类**：本文件自己也定义了一个 `HardFail`
     ⇒ ⇒ 两个类**不是同一个** ⇒ ⛔ 拿本地的类去接 ⇒ 管线抛的会被当成「别的异常」）。"""
    try:
        call()
    except exc_cls as e:
        return True, "%s 被拒（%s）：%s" % (what, exc_cls.__name__, str(e)[:80])
    except Exception as e:
        return False, "%s 抛的是**别的**异常（%s）⇒ 崩 ⛔ 不算按判据转红" \
            % (what, type(e).__name__)
    return False, "%s **没有被拒**（应当抛 %s）" % (what, exc_cls.__name__)


def chk_prereg(raw, cfg_cls):
    """P7：预登记 `n_bands = 1` 必须**被接受**，且**预登记文件本身没被改**。

    ⚖⚠⚠⚖ **两件事缺一不可**：
      ① `Cfg` 接受 1 ⇒ 管线**有能力**走合池
      ② 预登记里**仍然是 4** ⇒ 口径**没有**被偷偷切换（切换要**点头**）
    """
    if int(raw.get("n_bands", -1)) != 4:
        return False, "预登记文件里的 n_bands 是 %r（**应当仍是 4** ⇒ 口径切换未发生）" \
            % (raw.get("n_bands"),)
    try:
        cfg_cls(dict(raw, n_bands=1))
    except Exception as e:
        return False, "Cfg **拒绝** n_bands=1：%s" % (str(e)[:120])
    return True, "预登记 n_bands 仍是 4（口径切换**未发生**）｜ Cfg 接受 n_bands=1"


def chk_verdict_fields(cross, need=VERDICT_FIELDS):
    """P8：合池模式下**判决数字段必须齐**（少一个 ⇒ 就算不出判决数）。"""
    if len(cross) != 1:
        return False, "合池下 cross 必须**只有 1 条**（1 档），实际 %d 条" % len(cross)
    c = cross[0]
    missing = [k for k in need if c.get(k) is None]
    if missing:
        return False, "判决数字段缺 %s" % (missing,)
    if not (c.get("nw") and c.get("nr")):
        return False, "两臂的轨迹数必须是**正数**（分母不能是 0）：w=%r rand=%r" \
            % (c.get("nw"), c.get("nr"))
    return True, "判决数字段齐（%d 项）" % len(need)


def chk_axis_unmeasured(axis):
    """P9：合池下**剂量轴量必须标「未量到」**（⛔ 不是 0.0、不是 NaN）。"""
    if axis.get("rho") is not None:
        return False, "合池下的 rho 必须是 **None（未量到）**，实际 %r" % (axis.get("rho"),)
    note = axis.get("dose_axis", "")
    if "未量到" not in note:
        return False, "轴的说明里必须写明「未量到」，实际 %r" % (note,)
    return True, "rho = None（未量到）｜ 轴说明：%s" % note


def chk_pooled_dims_same(sigs):
    """P10：合池下 boundary / quantile **结构上不参与** ⇒ 6 个组合必须**逐位相同**。

    ⚠ 这是**实测**（6 个组合的输出签名逐字相同），⛔ 不是「应该没影响」的断言。
    ⚠⚠⚠ **有组合没跑起来（ERR）⇒ 判红**：6 个**同样**的错误信息也是「逐位相同」
    ⇒ ⇒ 那不是「维度不参与」的证据 ⇒ ⇒ 那种情况下这一维**测不到**。
    """
    bad = [s for s in (sigs or []) if str(s).startswith("ERR:")]
    if bad:
        return False, "有 %d 个组合**没跑起来** ⇒ 这一维**测不到**（不是「不参与」）" % len(bad)
    if not sigs:
        return False, "一个组合都没跑 ⇒ 测不到"
    if len(set(sigs)) != 1:
        return False, "合池下 %d 个组合给出了 **%d 种**不同输出 ⇒ 口径维度**参与了**" \
            % (len(sigs), len(set(sigs)))
    return True, "%d 个组合（2 boundary × 3 quantile）**逐位相同** ⇒ 这两个维度结构上不参与" \
        % len(sigs)


def chk_d8_green(v):
    """P11：244.72 的密度审计器 **D8 必须转绿**（且阻断集里**不再有 D8**）。"""
    if not v.get("R", {}).get("D8"):
        return False, "密度审计器的 D8（当前管线有没有合池模式）**仍红** ⇒ 合池没真进管线"
    if "D8" in (v.get("blocking") or []):
        return False, "D8 还在阻断集里（%s）⇒ 244.72 的「算不出判决数」结论没被更新" \
            % (v.get("blocking"),)
    return True, "D8 绿（合池模式**已可用**）｜ 阻断集 %s（**不再有 D8**）" % (v.get("blocking"),)


def chk_pooled_budget(lines):
    """P12：合池下的规模措辞必须**换掉**。

    ⚖⚠⚖⚖ 4 档的措辞里有「阶梯要扫到现在的 **N 倍**」⇒ 在合池下印出来 ⇒
    「**固定剂量要不要扫阶梯**」这件事就被渲染成「要扫 3 倍」⇒ ⇒ 口径说反了。
    """
    bl = " ".join(lines or [])
    if "合池模式" not in bl:
        return False, "合池下的规模行里**没有**「合池模式」：%s" % bl[:160]
    if "阶梯要扫到现在的" in bl:
        return False, "合池下**不许**印「阶梯要扫到现在的 N 倍」（口径说反了）：%s" % bl[:160]
    return True, "合池下的规模措辞已换成合池口径（不再说「阶梯要扫到现在的 N 倍」）"


def namediag_lines(DC, ks, fr):
    """⚖ 244.74 的**名实核对**诊断行（**实测**：两个 quantile 分支是否逐位相同）。

    ⚖⚠⚖⚠ 为什么要单独印一行：`dose_bands_v` 的 `quantile="inclusive"` 那支
    调的是 `statistics.quantiles(fr, n=n_bands)` ⇒ **没传 `method`**
    ⇒ 而 Python 的**默认 `method` 是 `'exclusive'`**
    ⇒ ⇒ 两支算的是**同一件事** ⇒ 「四分位算法」这一维**结构上就是空的**
    ⇒ ⇒ **既有缺陷** ⇒ 本轮**只测、只记**（修它＝改生产剂量轴 ⇒ **要点头**）
    """
    try:
        _qi, _bi = DC.dose_bands_v(ks, fr, boundary="prod",
                                   quantile="inclusive", n_bands=4)
        _qe, _be = DC.dose_bands_v(ks, fr, boundary="prod",
                                   quantile="exclusive", n_bands=4)
    except Exception as e:
        return ["  · 【名实核对】**没测到**（%s）" % (str(e)[:100],)]
    same = ([round(q, 9) for q in _qi] == [round(q, 9) for q in _qe]
            and [len(b[1]) for b in _bi] == [len(b[1]) for b in _be])
    if same:
        return ["  · 【名实核对】两个 quantile 分支**逐位相同**"
                "（分位点 %s ｜ 档 %s）⇒ ⇒ ⚠⚠⚠ 代码的 `inclusive` 那支**没传 `method`**"
                " ⇒ 算的是 **exclusive** ⇒ ⇒ 「四分位算法」这一维**结构上就是空的**"
                "（既有缺陷 ⇒ 本轮**只测、只记** ⇒ 修它＝改生产剂量轴 ⇒ **要点头**）"
                % ("/".join("%.3f" % q for q in _qi),
                   "/".join(str(len(b[1])) for b in _bi))]
    return ["  · 【名实核对】两个 quantile 分支**不同**（inclusive 档 %s ｜ exclusive 档 %s）"
            " ⇒ ⇒ 代码**真的**切了 method ⇒ 「四分位算法」这一维**测得到**"
            % ("/".join(str(len(b[1])) for b in _bi),
               "/".join(str(len(b[1])) for b in _be))]


def chk_namediag(lines):
    """T13：**名实核对**那行诊断**必须印出来**（⛔ 印不出来就等于没说）。"""
    hit = [ln for ln in (lines or []) if "【名实核对】" in ln]
    if not hit:
        return False, "报告里**没有**【名实核对】那行 ⇒ 「名实不符」这件事就等于没说"
    return True, "已印出：%s" % hit[0].strip()[:130]


# ---------------------------------------------------------------- 夹具
def synth_fixed_dose(n_traj=14, pos_fracs=(0.25, 0.5, 0.75), target=0.25,
                     P=100, n_gen=200, seed=20261022):
    """⚖ **合成**「固定剂量」批（⛔ **不是实测读数** ⇒ ⇒ 印出来的数**不是判决数**）。

    ⚖ 密度**真的固定**：每个 pos_frac 下 `n_sites = round(target × inj)` ⇒ 密度 ≈ target
    ⚖ 两臂用**同一个** tid 集合 ⇒ 跨臂**配对**成立（否则跨臂比较无意义）
    ⚖ 档内 m = 每条轨迹的**复制格数** = 3 ⇒ ⇒ 「平票不出现」的门槛满足

    ⚖⚠⚠⚠⚖⚖ **两臂必须真的有对比**（244.74 第一版栽在这里）：
       格级正负的口径是 `cell_sign_p9` = **`d = p9_hi_meas − p9_lo_meas > 0`**
       ⇒ ⇒ 如果 rand 臂的格也是 `hi > lo` ⇒ ⇒ **两臂全都算「改判」**
       ⇒ ⇒ 演示会印出「差 **+0.0pp** / p = **1.000000**」⇒ ⇒ ⛔ 那会被读成「**无差异**」
       ⇒ ⇒ 那是**假的**（夹具退化，不是「没差异」）⇒ ⇒ rand 臂的格必须是 `hi < lo`
       ⇒ ⇒ 演示才有对比（w 臂多数为正、rand 臂多数为负）⇒ ⇒ 印出来的数才**像**判决数
       ⇒ ⇒ 但它**仍然是合成夹具** ⇒ ⛔ **不是**判决数（自检 T8c 盯这一条）
    """
    rnd = random.Random(seed)
    out = {}
    for arm, bias in (("w", 0.90), ("rand", 0.10)):
        recs = []
        for i in range(n_traj):
            tid = "syn%02d__think" % i
            for pf in pos_fracs:
                inj = P + max(1, int(n_gen * pf)) - 1
                ns = max(1, int(round(target * inj)))
                pos = (rnd.random() < bias)
                recs.append({"tid": tid, "inject_scope": "k", "inject_n_sites": ns,
                             "P": P, "n_gen": n_gen, "pos_frac": pf,
                             "p9_lo_meas": 0.30,
                             # ⚖ 正向：hi > lo（d > 0 ⇒ 「改判」）；反向：hi < lo（d < 0 ⇒ 「不改判」）
                             "p9_hi_meas": (0.55 if pos else 0.20)})
        out[arm] = recs
    return out


# ---------------------------------------------------------------- 审计主体
def audit():
    """⚖ 出判据行 + 报告。返回 `(行列表, {判据号: bool})`。"""
    L = ["【合池模式审计】244.74 ｜ 零 GPU ｜ ⛔ **本工具不产生任何判决数**"]
    R = collections.OrderedDict()

    def put(cid, ok, detail):
        R[cid] = bool(ok)
        L.append("  [%s] %s：%s" % ("PASS" if ok else "FAIL", cid, detail))

    DC, DL, FA = dconf(), dlayer(), fda()
    ks = [{"tid": "fix%02d" % i} for i in range(len(FIX_FR))]
    fr = list(FIX_FR)

    # ---- P1 生产口径（4 档）逐位不变 ----
    try:
        qs4, bands4 = DC.dose_bands_v(ks, fr, boundary="prod",
                                      quantile="inclusive", n_bands=4)
    except Exception as e:
        qs4, bands4 = [], []
        ok1, d1 = False, "生产口径调用**抛了异常**：%s" % (str(e)[:120],)
    else:
        ok1, d1 = chk_prod_structure(qs4, bands4, ks, fr)
        got_q = [round(q, 6) for q in qs4]
        got_s = tuple(len(b[1]) for b in bands4)
        if got_q != list(BASE_Q):
            ok1 = False
            d1 += " ｜ 分位点 %s ≠ **244.72 基线** %s" % (got_q, list(BASE_Q))
        if got_s != BASE_SIZE:
            ok1 = False
            d1 += " ｜ 档大小 %s ≠ **244.72 基线** %s" % (list(got_s), list(BASE_SIZE))
    put("P1", ok1, d1)

    # ---- P2 合池模式可用 ----
    res1 = None
    try:
        res1 = DC.dose_bands_v(ks, fr, boundary="prod", quantile="inclusive", n_bands=1)
        ok2, d2 = chk_pooled_shape(*res1)
    except Exception as e:
        ok2, d2 = False, "合池调用**抛了异常**（⛔ 合池模式不可用）：%s" % (str(e)[:120],)
    put("P2", ok2, d2)

    # ---- P3 合池档含全部格 ----
    if res1 is None:
        ok3, d3 = False, "P2 红 ⇒ 合池结果不存在 ⇒ 没法查守恒"
    else:
        ok3, d3 = chk_pooled_conservation(res1[1], ks)
    put("P3", ok3, d3)

    # ---- P4 合池下剂量趋势必须「未量到」 ----
    nzs = [[1, 2, 0, 1, 0, 2, 1, 0, 1, 2, 0, 1, 0, 2]]
    counts = [8]
    ok4, d4 = chk_trend_unmeasured(
        lambda: DL.mc_trend_p_geom(nzs, counts, n_layer=1))
    put("P4", ok4, d4)

    # ---- P5 n_bands = 0 必须被拒 ----
    ok5, d5 = chk_hardfail(
        lambda: DC.dose_bands_v(ks, fr, boundary="prod", quantile="inclusive", n_bands=0),
        "n_bands=0", DC.HardFail)
    put("P5", ok5, d5)

    # ---- P6 合池下坏口径取值也必须被拒 ----
    ok6a, d6a = chk_hardfail(
        lambda: DC.dose_bands_v(ks, fr, boundary="prod", quantile="bogus", n_bands=1),
        "合池 + quantile=bogus", DC.HardFail)
    ok6b, d6b = chk_hardfail(
        lambda: DC.dose_bands_v(ks, fr, boundary="bogus", quantile="inclusive", n_bands=1),
        "合池 + boundary=bogus", DC.HardFail)
    put("P6", ok6a and ok6b, "%s ｜ %s" % (d6a, d6b))

    # ---- P7 预登记接受 n_bands=1，且预登记文件没被改 ----
    try:
        raw = FA.read_prereg()
    except Exception as e:
        ok7, d7 = False, "读不到预登记文件 ⇒ **未量到**：%s" % (str(e)[:120],)
    else:
        ok7, d7 = chk_prereg(raw, FA.Cfg)
    put("P7", ok7, d7)

    # ---- P8 合池下整条管线算得出判决数 ----
    A = None
    if not ok7:
        ok8, d8 = False, "P7 红（预登记/口径没就位）⇒ 没法跑整条管线"
    else:
        cfg1 = FA.Cfg(dict(raw, n_bands=1))
        try:
            A = FA.build_all(cfg1, rows_by_arm=synth_fixed_dose())
        except Exception as e:
            ok8, d8 = False, "合池下 `build_all` **抛了异常**：%s" % (str(e)[:140],)
        else:
            ok8, d8 = chk_verdict_fields(A["cross"])
            if ok8:
                c = A["cross"][0]
                d8 += "（w %d/%d ｜ rand %d/%d ｜ 差 %+.1fpp ｜ p_perm=%.6f ｜ Fisher=%.6f）" \
                    % (c["kw"], c["nw"], c["kr"], c["nr"], c["diff_pp"],
                       c["p_perm"], c["fisher"])
            d8 += " ｜ ⚠⚠ **合成夹具 ⇒ 这些数不是判决数**（真实判决数**未量到**）"
    put("P8", ok8, d8)

    # ---- P9 合池下剂量轴量标「未量到」 ----
    if A is None:
        ok9, d9 = False, "P8 红 ⇒ 没有轴可查"
    else:
        ok9, d9 = chk_axis_unmeasured(A["axis"]["w"])
        ok9 = ok9 and chk_axis_unmeasured(A["axis"]["rand"])[0]
    put("P9", ok9, d9)

    # ---- P10 合池下 boundary/quantile 结构上不参与 ----
    sigs = []
    for b in ("prod", "alt"):
        for q in ("inclusive", "exclusive", "nearest_rank"):
            try:
                _qs, _bd = DC.dose_bands_v(ks, fr, boundary=b, quantile=q, n_bands=1)
                sigs.append(repr((tuple(_qs),
                                  tuple((lab, tuple(id(c) for c in sub))
                                        for lab, sub in _bd))))
            except Exception as e:
                sigs.append("ERR:%s" % (str(e)[:60],))
    ok10, d10 = chk_pooled_dims_same(sigs)
    put("P10", ok10, d10)

    # ---- P11 跨轮一致性：密度审计器的 D8 必须转绿 ----
    try:
        FD = fden()
        pool = FD.fdf().read_pool(FD.POOL_DEFAULT)
        base = FD._read_json(os.path.join(HERE, "fixed_dose_cost_baseline.json"),
                             "成本基线")
        route = {"route_id": "pooled_audit", "strategy": "measure_first",
                 "n_blocks": 2, "cells_per_track": 3,
                 "pos_fracs": [0.25, 0.5, 0.75], "arms": ["w", "rand"]}
        spec = {"spec_id": "pooled_audit", "route": route, "scope": "k",
                "frac": 0.25, "tol": FD.D_TOL_DEFAULT,
                "pos_fracs": [0.25, 0.5, 0.75], "n_blocks": 2, "cells_per_track": 3}
        import tempfile
        import shutil
        tmp = tempfile.mkdtemp(prefix="poolaudit_")
        try:
            txt = FD._fake_cells_fixed(pool, base)
            p = FD._mk(tmp, "fixed.tsv", txt)
            _rows, v = FD.audit_cells(spec, p, pool, base)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    except Exception as e:
        ok11, d11 = False, "跑不动密度审计器 ⇒ **未量到**：%s" % (str(e)[:140],)
    else:
        ok11, d11 = chk_d8_green(v)
    put("P11", ok11, d11)

    # ---- P12 合池下的规模措辞必须换掉 ----
    if A is None:
        ok12, d12 = False, "P8 红 ⇒ 没有预算表可查"
    else:
        ok12, d12 = chk_pooled_budget(A["budget"]["lines"])
    put("P12", ok12, d12)

    # ---- 诊断区（⛔ 不参与判据）----
    L.append("")
    L.append("【诊断】")
    L.append("  · 244.50 的**账本登记值**（生产剂量轴，人眼对照）：分位点 %s ｜ 档 %s"
             % ("/".join("%.3f" % q for q in REG_QUANTILES),
                "/".join(str(x) for x in REG_BAND_SIZE)))
    L.append("    （⛔ 真数据文件 `_an.txt` / `_ra.txt` **不在库里** ⇒ 判据**不依赖**它们 ⇒ "
             "这里只是提醒口径登记值长什么样）")
    L.append("  · **合池模式的口径含义**：1 档 = 全池 ⇒ **没有剂量轴** ⇒")
    L.append("    ① 剂量**趋势** = **未量到**（⛔ 不是「无趋势」）")
    L.append("    ② 剂量**相关性 rho** = **未量到**（⛔ 不是 0.0、不是 NaN）")
    L.append("    ③ 剂量**阶梯**：合池下**不需要扫**（同一剂量的复制格进同一档）")
    L.extend(namediag_lines(DC, ks, fr))
    L.append("  · ⚠ **本轮只加了「能力」**：预登记里的 n_bands **仍是 4** ⇒ "
             "**口径切换未发生** ⇒ ⇒ 「固定剂量」那一批的真实判决数**未量到**")
    return L, R


# ---------------------------------------------------------------- 自检
def selftest():
    """⚖⚠⚖ **每条判据都要有红化反例**（⛔ 恒绿的判据不许留）。

    ⚖ 本自检的两种证据：
      ① **正样**：真对象上判据必须绿（⇒ 证明它不是恒红、也不是恒真）
      ② **反样**：把**手写的坏结果**喂给判据函数 ⇒ 它必须转红（⇒ 证明它**能红**）
    """
    ok, bad = [], []

    def chk(name, cond, msg):
        (ok if cond else bad).append(name)
        print(("[PASS] %s %s" if cond else "[FAIL] %s %s") % (name, msg))

    DC, DL, FA = dconf(), dlayer(), fda()
    ks = [{"tid": "fix%02d" % i} for i in range(len(FIX_FR))]
    fr = list(FIX_FR)

    def _safe(fn, default=None):
        """⚖⚠⚖ **被变异打断的调用必须变成 FAIL，⛔ 不许变成「崩」**
        ⇒ ⇒ 凡是碰到**被检管线**的调用一律包起来
        （崩 ⛔ 不等于「抓到」⇒ 崩掉的变异会被台架记成「崩」⇒ 那一轮就废了）。
        """
        try:
            return fn(), None
        except Exception as e:
            return default, e

    # ---- P1：正样（真对象）+ 反样（手写的坏结果）----
    (qs4, bands4), e4 = _safe(
        lambda: DC.dose_bands_v(ks, fr, boundary="prod", quantile="inclusive", n_bands=4))
    if e4 is not None:
        chk("T1", False, "生产口径调用抛了异常：%s" % (str(e4)[:120],))
        qs4, bands4 = [], []
    else:
        ok1, d1 = chk_prod_structure(qs4, bands4, ks, fr)
        chk("T1", ok1 and [round(q, 6) for q in qs4] == list(BASE_Q)
            and tuple(len(b[1]) for b in bands4) == BASE_SIZE,
            "生产口径逐位等于 **244.72 基线**（分位点 %s ｜ 档 %s）"
            % ([round(q, 6) for q in qs4], [len(b[1]) for b in bands4]))
    _bad = ([("frac<q1", bands4[0][1])] + list(bands4[1:])) if bands4 else []
    ok1b, _d = chk_prod_structure(qs4, _bad, ks, fr)
    chk("T1b", (not ok1b), "把首档档名改掉 ⇒ P1 必须红（证明它不是恒绿）")
    _bad2 = ([bands4[0], bands4[1], bands4[2], (bands4[3][0], bands4[3][1][:-1])]
             if len(bands4) == 4 else [])
    ok1c, _d = chk_prod_structure(qs4, _bad2, ks, fr)
    chk("T1c", (not ok1c), "末档**少一格** ⇒ P1 必须红（守恒破了）")

    # ---- P2：正样 + 反样 ----
    res1, e1 = _safe(
        lambda: DC.dose_bands_v(ks, fr, boundary="prod", quantile="inclusive", n_bands=1))
    if e1 is not None:
        chk("T2", False, "合池调用抛了异常（⛔ 合池模式不可用）：%s" % (str(e1)[:120],))
    else:
        ok2, d2 = chk_pooled_shape(*res1)
        chk("T2", ok2, "合池：%s" % d2)
    ok2b, _d = chk_pooled_shape([0.5], list(res1[1]) if res1 else [])
    chk("T2b", (not ok2b), "喂「有分位点」的合池结果 ⇒ P2 必须红")
    ok2c, _d = chk_pooled_shape([], (list(res1[1]) + [("x", [])]) if res1 else [])
    chk("T2c", (not ok2c), "喂「2 档」的合池结果 ⇒ P2 必须红")

    # ---- P3：正样 + 反样 ----
    if res1 is None:
        chk("T3", False, "合池结果不存在 ⇒ 没法查守恒")
    else:
        ok3, d3 = chk_pooled_conservation(res1[1], ks)
        chk("T3", ok3, "合池守恒：%s" % d3)
        ok3b, _d = chk_pooled_conservation(
            [(res1[1][0][0], res1[1][0][1][:-1])] if res1[1] else [], ks)
        chk("T3b", (not ok3b), "合池档**少一格** ⇒ P3 必须红")
        ok3c, _d = chk_pooled_conservation(
            [(res1[1][0][0], res1[1][0][1] + res1[1][0][1][:1])] if res1[1] else [], ks)
        chk("T3c", (not ok3c), "合池档**多一格** ⇒ P3 必须红")

    # ---- P4：正样 + 反样 ----
    nzs = [[1, 2, 0, 1, 0, 2, 1, 0, 1, 2, 0, 1, 0, 2]]
    counts = [8]
    ok4, d4 = chk_trend_unmeasured(lambda: DL.mc_trend_p_geom(nzs, counts, n_layer=1))
    chk("T4", ok4, "1 档趋势：%s" % d4)
    ok4b, _d = chk_trend_unmeasured(lambda: 1.0)
    chk("T4b", (not ok4b), "喂一个「返回 p=1.0」的假实现 ⇒ P4 必须红")
    ok4c, _d = chk_trend_unmeasured(
        lambda: (_ for _ in ()).throw(ValueError("只是崩了")))
    chk("T4c", (not ok4c), "喂一个「理由不是未量到」的拒绝 ⇒ P4 必须红")

    # ---- P5：正样 + 反样 ----
    ok5, d5 = chk_hardfail(
        lambda: DC.dose_bands_v(ks, fr, boundary="prod", quantile="inclusive", n_bands=0),
        "n_bands=0", DC.HardFail)
    chk("T5", ok5, "n_bands=0：%s" % d5)
    ok5b, _d = chk_hardfail(lambda: (_ for _ in ()).throw(ValueError("崩了")), "假实现",
                            DC.HardFail)
    chk("T5b", (not ok5b), "喂一个「抛别的异常」的假实现 ⇒ P5 必须红（崩⛔不算按判据转红）")

    # ---- P6：正样 + 反样 ----
    ok6a, _d = chk_hardfail(
        lambda: DC.dose_bands_v(ks, fr, boundary="prod", quantile="bogus", n_bands=1),
        "合池 + quantile=bogus", DC.HardFail)
    ok6b, _d = chk_hardfail(
        lambda: DC.dose_bands_v(ks, fr, boundary="bogus", quantile="inclusive", n_bands=1),
        "合池 + boundary=bogus", DC.HardFail)
    chk("T6", ok6a and ok6b, "合池下坏口径取值必须被拒（quantile + boundary）")

    # ---- P7：正样 ----
    raw, e_raw = _safe(lambda: FA.read_prereg())
    if e_raw is not None:
        chk("T7", False, "读不到预登记文件：%s" % (str(e_raw)[:120],))
        raw = {}
    else:
        ok7, d7 = chk_prereg(raw, FA.Cfg)
        chk("T7", ok7, "预登记：%s" % d7)
        ok7b, _d = chk_prereg(dict(raw, n_bands=3), FA.Cfg)
        chk("T7b", (not ok7b), "预登记被改成 n_bands=3 ⇒ P7 必须红（口径切换未发生）")

    # ---- P8：正样 + 反样 ----
    cfg1, e_cfg = _safe(lambda: FA.Cfg(dict(raw, n_bands=1)))
    if e_cfg is not None:
        A, e_A = None, e_cfg
    else:
        A, e_A = _safe(lambda: FA.build_all(cfg1, rows_by_arm=synth_fixed_dose()))
    if A is None:
        chk("T8", False, "合池下 `build_all` 跑不起来：%s"
            % (str(e_A)[:140] if e_A is not None else "cfg 没建成"))
    else:
        ok8, d8 = chk_verdict_fields(A["cross"])
        chk("T8", ok8, "合池下整条管线：%s" % d8)
        _c = dict(A["cross"][0])
        _c["fisher"] = None
        ok8b, _d = chk_verdict_fields([_c])
        chk("T8b", (not ok8b), "把 Fisher p 弄没 ⇒ P8 必须红（判决数字段必须齐）")
        # ⚖⚠⚖⚖⚖⚖ 夹具**必须真的有对比**（244.74 第一版的夹具是**退化**的 ⇒
        #   ⇒ 演示印出「差 +0.0pp / p = 1.000000」⇒ ⇒ ⛔ 那会被读成「无差异」）
        ok8c = (A["cross"][0]["kw"] > A["cross"][0]["kr"])
        chk("T8c", ok8c,
            "合成夹具**必须有对比**（w 改判 %d/%d ｜ rand 改判 %d/%d）⇒ 否则演示是**退化的**"
            "（⛔ 退化的演示会印出「差 0.0pp」⇒ ⇒ 会被读成「无差异」）"
            % (A["cross"][0]["kw"], A["cross"][0]["nw"],
               A["cross"][0]["kr"], A["cross"][0]["nr"]))

    # ---- P9：正样 + 反样 ----
    if A is None:
        chk("T9", False, "没有轴可查（P8 红）")
    else:
        ok9, d9 = chk_axis_unmeasured(A["axis"]["w"])
        ok9 = ok9 and chk_axis_unmeasured(A["axis"]["rand"])[0]
        chk("T9", ok9, "合池轴：%s" % d9)
        ok9b, _d = chk_axis_unmeasured(dict(A["axis"]["w"], rho=0.0))
        chk("T9b", (not ok9b), "把 rho 换成 0.0 ⇒ P9 必须红（0.0 会被读成「无效应」）")

    # ---- P10：正样 + 反样 ----
    sigs = []
    for b in ("prod", "alt"):
        for q in ("inclusive", "exclusive", "nearest_rank"):
            _r, _e = _safe(
                lambda: DC.dose_bands_v(ks, fr, boundary=b, quantile=q, n_bands=1))
            if _e is not None:
                sigs.append("ERR:%s" % (str(_e)[:60],))
            else:
                sigs.append(repr((tuple(_r[0]),
                                  tuple((lab, tuple(id(c) for c in sub))
                                        for lab, sub in _r[1]))))
    ok10, d10 = chk_pooled_dims_same(sigs)
    chk("T10", ok10, "合池维度：%s" % d10)
    ok10b, _d = chk_pooled_dims_same(["a", "b"])
    chk("T10b", (not ok10b), "喂两个不同的签名 ⇒ P10 必须红")

    # ---- P11：正样 + 反例 ----
    FD = fden()
    pool = FD.fdf().read_pool(FD.POOL_DEFAULT)
    base = FD._read_json(os.path.join(HERE, "fixed_dose_cost_baseline.json"), "成本基线")
    route = {"route_id": "selftest", "strategy": "measure_first", "n_blocks": 2,
             "cells_per_track": 3, "pos_fracs": [0.25, 0.5, 0.75], "arms": ["w", "rand"]}
    spec = {"spec_id": "selftest", "route": route, "scope": "k", "frac": 0.25,
            "tol": FD.D_TOL_DEFAULT, "pos_fracs": [0.25, 0.5, 0.75],
            "n_blocks": 2, "cells_per_track": 3}
    import tempfile
    import shutil
    tmp = tempfile.mkdtemp(prefix="poolst_")
    try:
        txt = FD._fake_cells_fixed(pool, base)
        p = FD._mk(tmp, "fixed.tsv", txt)
        _rows, v = FD.audit_cells(spec, p, pool, base)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    ok11, d11 = chk_d8_green(v)
    chk("T11", ok11, "密度审计器 D8：%s" % d11)
    ok11b, _d = chk_d8_green(dict(v, R=dict(v["R"], D8=False)))
    chk("T11b", (not ok11b), "喂一个 D8=False 的假结果 ⇒ P11 必须红")
    ok11c, _d = chk_d8_green(dict(v, blocking=list(v["blocking"]) + ["D8"]))
    chk("T11c", (not ok11c), "喂一个「D8 还在阻断集里」的假结果 ⇒ P11 必须红")

    # ---- P12：正样 + 反样 ----
    if A is None:
        chk("T12", False, "没有预算表可查（P8 红）")
    else:
        ok12, d12 = chk_pooled_budget(A["budget"]["lines"])
        chk("T12", ok12, "合池下的规模措辞：%s" % d12)
        ok12b, _d = chk_pooled_budget(["每条轨迹平均 k 档 3.00 ⇒ 阶梯要扫到现在的 1.00 倍"])
        chk("T12b", (not ok12b), "喂 4 档的措辞 ⇒ P12 必须红")

    # ---- T13：名实核对那行诊断**必须印出来**（⛔ 印不出来就等于没说）----
    ok13, d13 = chk_namediag(namediag_lines(DC, ks, fr))
    chk("T13", ok13, "名实核对：%s" % d13)
    ok13b, _d = chk_namediag(["（这里没有那行）"])
    chk("T13b", (not ok13b), "喂一个没有【名实核对】的报告 ⇒ T13 必须红")

    print("自检 %d/%d 通过" % (len(ok), len(ok) + len(bad)))
    return 1 if bad else 0


def main():
    import argparse
    ap = argparse.ArgumentParser(description="「合池模式」（n_bands=1）的可算性审计（244.74，零 GPU）")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    L, R = audit()
    print("\n".join(L))
    n_ok = sum(1 for v in R.values() if v)
    print("")
    print("判据 %d/%d 绿%s" % (n_ok, len(R),
                                "" if n_ok == len(R) else
                                " ⇒ ⇒ ⛔ **合池模式还不能用** ⇒ ⇒ 「固定剂量」那一批"
                                "**算不出判决数** ⇒ ⇒ 先修，别跑批"))
    return 0 if n_ok == len(R) else 1


if __name__ == "__main__":
    sys.exit(main())
