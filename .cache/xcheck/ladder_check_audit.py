"""阶梯自检的**空转审计**：找出那些「任何变异都翻不动」的自检。

## 为什么要有它

阶梯生成器有 **41** 条自检，但**没有任何机制**说明它们还在承重。
修订 55 已经出现过一次：三条自检钉的是修订 49 那个**被证伪的因子** ——
它们照样每轮都「全过」。**「全过」不等于「有牙齿」**。

⇒ 本脚本把每条自检在**一批产物变异**下跑一遍，
凡是**一条都翻不动**的自检，直接列成「恒绿候选」。

## 三条必须分开的判读（否则报告本身会骗人）

1. **变异有没有生效**。自己写的变异也可能打空 ⇒ 先比文件是否真的变了。
   「变异没生效」与「判据没牙齿」在报告里**长得一模一样**。
2. **判据有没有牙齿**。要测这条，必须让构建器**跑到那条判据**。
   ⇒ 每个变异跑**两遍**：
   · **门开**（生产行为）：`_abort_if_problems()` 生效 ⇒ 一旦有红就
     `SystemExit(2)`，**排在后面的自检根本不会执行**。
     第一版只跑这一遍，于是任何早期变异都让后面二十几条自检「测不到」，
     而「测不到」被当成了「翻不动」。
   · **门关**（测牙齿用）：把那道门换成空函数 ⇒ 全部自检都会跑到。
3. **恒绿 vs 测不到**。「恒绿」= 跑到了、当前是绿的、一条变异都没翻动它。
   「测不到」= 门关之后它**仍然没出现**（被崩掉了 / 走不到）。
   两者必须分开印，混在一起会把「不可达」误报成「无牙齿」。

## 身份：**源码行号 + 同一次运行内的迭代序号**

第一版拿「文案」当身份，踩了两个坑，两个方向都有：

1. **文案里嵌了数值**（「…幅度算出来只有 %.4f…」）：基线 0.1044、变异后 0.0000
   ⇒ 两个字符串不相等 ⇒ 「真的翻红了」被算成「没翻」⇒ 整轮审计全绿。
2. ⚠⚠ **抹数字又会撞车**：把 `L1`、`L2` 里的数字也抹掉 ⇒ 41 条自检塌成
   **39** 个身份（`base_ok` 是**集合**，我假设它等于基线条数，一验就露馅）。
   而文案里插值的**列表**（`[]` → `['c_points@strength=0.05']`）同样改身份。
⇒ 身份改用 `sys._getframe(1).f_lineno`（`need()` 在 `main()` 里的调用行）
  \+ 该行在本次运行里第几次被调用。构建器本身不被变异 ⇒ 行号稳定；
  循环里的多次调用按迭代序号分开。

## 还要报一条最值钱的信号：**产物变了但零自检翻红**

「恒绿」有两种完全不同的成因，必须分开：

- **变异打空** —— 被测对象根本不读那个字段（例：`real_dev_spread`
  构建器从未引用）⇒ 怪变异，不怪判据。
- **判据没牙齿** —— 产物**确实变了**（L1 的 note / claim 逐字不同），
  而**一条自检都没红** ⇒ 真空缺口。

⇒ 每条变异都比一次「产物可见文本」（L1 的 claim + note）有没有变。

## 怎么做到不碰仓库

构建器所有产物都是从模块级 `DATA` 目录 `read_text()` 读的
⇒ 把 `DATA` 指向临时目录里的**副本**，仓库原封不动。

## 用法

    PYTHONPATH=.cache/pylibs python3 .cache/xcheck/ladder_check_audit.py
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
BUILDER = os.path.join(ROOT, ".cache/xcheck/build_evidence_ladder.py")
DATA = os.path.join(ROOT, "frontend/public/latent/data")


def _visible_text(path):
    """产物里**读者能看到**的全部文本，用于判「产物变了没有」。

    ⚠⚠ 第一版只取 L1 的 `claim + note` ⇒ L6 的「92 个真 run / 23 题配对」
    那类改动被判成「产物没变」，于是 `cot.n_runs` 变异明明改了页面上的字，
    审计却说「没变、所以不是真空缺口」。
    ⚠ 「同屏渲染的东西都要比」—— 只看一个面板就是在给自己开豁免。
    """
    try:
        d = json.loads(open(path, encoding="utf-8").read())
    except Exception:
        return None
    parts = []
    for x in d.get("ladder", []):
        parts.append("|".join(str(x.get(k, "")) for k in
                              ("level", "state", "claim", "here", "note")))
    for k in ("not_answerable", "answerable", "most_common_overreach",
              "max_level_claimed", "max_level_with_data", "max_level_reached",
              "overreach_numbers"):
        if k in d:
            parts.append("%s=%s" % (k, json.dumps(d[k], ensure_ascii=False)))
    return "\n".join(parts)


def load_mod(path=None):
    spec = importlib.util.spec_from_file_location(
        "ladder_audit", path or BUILDER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_once(mod, data_dir, out_path, gate):
    """跑一次构建器。返回 (seen, crashed)。

    `seen` 是 [(身份, 是否通过, 文案)]，身份 = "调用行:该行第几次被调用"。
    ⚠ `gate=False` 时把 `_abort_if_problems()` 换成空函数 —— 它是
      `main()` 里按**模块全局名**查的，所以改模块属性就生效。
    ⚠ 构建器里 `DATA / "x.json"` ⇒ 必须是 Path，不是 str。
    """
    mod.DATA = Path(data_dir)
    mod.PROBLEMS = []
    mod.CHECKS = [0]
    seen = []
    per_line = Counter()
    real_need = mod.need
    real_gate = mod._abort_if_problems

    def rec(cond, msg):
        ln = sys._getframe(1).f_lineno
        per_line[ln] += 1
        seen.append(("%d:%d" % (ln, per_line[ln]), bool(cond), str(msg)))
        return real_need(cond, msg)

    mod.need = rec
    if not gate:
        mod._abort_if_problems = lambda: None
    buf, old = io.StringIO(), sys.stdout
    sys.stdout = buf
    crashed = None
    try:
        try:
            mod.main(["--out", out_path])
        except SystemExit as e:
            if gate and e.code not in (0, None):
                crashed = "SystemExit(%s)（门开：自检红，构建器**拒绝出文件**）" % e.code
        except AssertionError as e:
            # ⚠ 记成一条红，而不是当「崩」：崩会让后面所有自检变成「测不到」，
            #   而 assert 触发本身就是一个真信号。修订 56 已把两条 assert 换成
            #   need()，这里留着是为了**将来又有人写 assert 时不漏报**。
            ln = sys._getframe(1).f_lineno
            per_line[ln] += 1
            seen.append(("%d:assert" % ln, False, "【assert】%s" % e))
            crashed = "AssertionError（已记为一条红）"
        except Exception as e:            # ⚠ 硬崩**也算**「这条断言没能守住」
            crashed = "%s: %s" % (type(e).__name__, e)
    finally:
        sys.stdout = old
        mod.need = real_need
        mod._abort_if_problems = real_gate
    return seen, crashed


LAW = "linearity_law.json"
SUB = "readable_subspace.json"
HEL = "heldout_readability.json"
ARM = "arm_asymmetry.json"
COT = "cot_texts.json"
ARTEFACTS = [LAW, SUB, HEL, ARM, COT]


# ---- 变异：每个都改产物里**一个**具体的东西 ------------------------------------
# ⚠⚠ 修订 56（W6）：第一版 15 条变异**全部只改 linearity_law.json** ⇒
#   L2/L3/L4/L5/L6 那些自检一条都没被碰过，那「35 条恒绿」是**覆盖不足**、
#   不是无牙齿。⇒ 下面按产物分组，五项都要有变异。
# ⚠ 第一版把「文件名」隐含在函数里 ⇒ 统计不了覆盖 ⇒ 改成显式三元组。
def mut_cos_zero(d):
    for r in d["rows"]:
        for k in r["real"]:
            r["real"][k]["cos_mean"] = 0.0


def mut_cos_same(d):
    v = d["rows"][0]["real"]["caution"]["cos_mean"]
    for r in d["rows"]:
        for k in r["real"]:
            r["real"][k]["cos_mean"] = v


def mut_npoints_big(d):
    d["design"]["n_points"] = 100000


def mut_npoints_zero(d):
    d["design"]["n_points"] = 0


def mut_drop_c(d):
    for r in d["rows"]:
        r.pop("c_points", None)


def mut_drop_a(d):
    for r in d["rows"]:
        r.pop("a_points", None)


def mut_drop_rndc(d):
    for r in d["rows"]:
        r.pop("random_c_points", None)


def mut_drop_rnda(d):
    for r in d["rows"]:
        r.pop("random_a_points", None)


def mut_pred_scale(d):
    for r in d["rows"]:
        r["pred_points"] = [x * 1.01 for x in r["pred_points"]]


def mut_dev_perturb(d):
    for r in d["rows"]:
        k = list(r["real_dev_points"])[0]
        v = list(r["real_dev_points"][k])
        v[0] = v[0] * 1.5 + 0.1
        r["real_dev_points"][k] = v


def mut_safe_max(d):
    d["conclusions"]["safe_regime"]["strength_max"] = 0.5


def mut_thr(d):
    d["conclusions"]["safe_regime"]["random_indistinguishable"] = False


def mut_spread_zero(d):
    for r in d["rows"]:
        r["real_dev_spread"] = 0.0


def mut_nrand(d):
    d["design"]["n_random"] = 2


def mut_sem_key(d):
    """塞一个语义类键名进去 —— 测「L1 note 说『从未进入这次测量』」
    那条自检是不是真的有牙齿（修订 50 立的那条）。"""
    d["rows"][0]["readability_margin"] = 0.7


# ---- 另外四个产物（W6 新增）--------------------------------------------------
def mut_sub_lb(d):
    d["headline"]["readable_directions_lower_bound"] = 13


def mut_sub_perm(d):
    d["headline"]["order_dependence"]["n_perm"] = 100


def mut_hel_rho(d):
    d["recipe"]["loo_rho"] = 0.08


def mut_hel_verdict(d):
    for r in d["rows"]:
        if r.get("verdict") == "same_direction":
            r["verdict"] = "new_clean"
            return
    d["rows"][0]["verdict"] = "new_clean"


def mut_hel_margin(d):
    d["recipe"]["specificity_margin"] = 2.4


def mut_arm_dirs(d):
    """⚠⚠ 第一版写成「顶层每个 list 都 append 一个字符串」⇒ 把 `metrics`
    （list of dict）塞进字符串 ⇒ `m["metric"]` 抛
    `TypeError: string indices must be integers`，23 条自检全变成「测不到」。
    ⇒ 崩掉的不是判据，是**变异自己**。教训与 §53 的 N4 同源：
    变异打空/写坏时，先怀疑变异。
    """
    d["metrics"].append({"metric": "random_control", "distinguishable": True})


def mut_arm_pairs(d):
    d["n_pairs"] = 99


def mut_cot_dir(d):
    d["runs"][0]["direction"] = "random_control"


def mut_cot_nruns(d):
    d["n_runs"] = 1


# ---- 第二批：把第一版「够不着」的自检也纳入覆盖（W6 补漏）--------------------
def mut_dir_ind_false(d):
    d["conclusions"]["safe_regime"]["direction_independent"] = False


def mut_beyond_ind_true(d):
    d["conclusions"]["beyond_safe_regime"]["direction_independent"] = True


def mut_drop_safe_rows(d):
    sm = d["conclusions"]["safe_regime"]["strength_max"]
    d["rows"] = [r for r in d["rows"] if abs(r["strength"] - sm) > 1e-9]


def mut_real_dirs3(d):
    d["design"]["real_directions"] = d["design"]["real_directions"][:3]


def mut_a_mean(d):
    """动 `a_mean` ⇒ 行均值口径的跨方向幅度会变 ⇒ 应翻 [660]/[663] 两条
    「note 必须印出旧数/新数」。第一版没有任何变异碰得到它们。

    ⚠⚠ 第一版打的是 `rows[0]`（s=0.05）—— 而 `_sp_claim / _sp_exact` 是
    **跨行取 max**，s=0.05 的 a 最小 ⇒ max 根本不动 ⇒ 产物不变、零翻红。
    **「变异没生效」与「判据没牙齿」又一次长得一模一样。**
    ⇒ 必须打**安全区最大档**那一行。
    """
    sm = d["conclusions"]["safe_regime"]["strength_max"]
    for r in d["rows"]:
        if abs(r["strength"] - sm) < 1e-9:
            r["a_mean"] = float(r["a_mean"]) * 1.5
            return
    d["rows"][0]["a_mean"] = float(d["rows"][0]["a_mean"]) * 1.5


ARTEFACT_MUTATIONS = [
    # (说明, 目标文件, 变异函数)
    ("所有 cos_mean 置 0", LAW, mut_cos_zero),
    ("所有 cos_mean 设成同一个值", LAW, mut_cos_same),
    ("n_points 改成 100000", LAW, mut_npoints_big),
    ("n_points 改成 0", LAW, mut_npoints_zero),
    ("删掉 c_points（真实臂）", LAW, mut_drop_c),
    ("删掉 a_points（真实臂）", LAW, mut_drop_a),
    ("删掉 random_c_points（随机臂）", LAW, mut_drop_rndc),
    ("删掉 random_a_points（随机臂）", LAW, mut_drop_rnda),
    ("pred_points 整体 ×1.01", LAW, mut_pred_scale),
    ("改一个真实方向的 dev 点（远超阈值）", LAW, mut_dev_perturb),
    ("safe_regime.strength_max 改 0.5", LAW, mut_safe_max),
    ("random_indistinguishable 翻 False", LAW, mut_thr),
    ("所有 real_dev_spread 置 0", LAW, mut_spread_zero),
    ("n_random 改成 2", LAW, mut_nrand),
    ("加语义类键名 readability_margin", LAW, mut_sem_key),
    ("a_mean 第一行 ×1.5", LAW, mut_a_mean),
    ("safe_regime.direction_independent 翻 False", LAW, mut_dir_ind_false),
    ("beyond_safe_regime.direction_independent 翻 True", LAW, mut_beyond_ind_true),
    ("删掉 s=0.2 那一档的全部行", LAW, mut_drop_safe_rows),
    ("design.real_directions 只留 3 条", LAW, mut_real_dirs3),
    # ↓ W6：下面覆盖另外四个产物
    ("L2 可读下界 14 → 13", SUB, mut_sub_lb),
    ("L2 顺序依赖 n_perm 200 → 100", SUB, mut_sub_perm),
    ("L4 配方 loo_rho 82× → 17×", HEL, mut_hel_rho),
    ("把一条 same_direction 翻成 new_clean", HEL, mut_hel_verdict),
    ("L5 余量 1.15× → 2.4×", HEL, mut_hel_margin),
    ("arm 加一个可分辨的随机对照指标", ARM, mut_arm_dirs),
    ("arm n_pairs 23 → 99", ARM, mut_arm_pairs),
    ("cot 某个 run 的方向改成随机对照", COT, mut_cot_dir),
    ("cot n_runs 92 → 1", COT, mut_cot_nruns),
]

# ---- 源码变异：note / claim 是**构建器写出来的**，改产物永远删不掉一个片段 ----
# ⚠⚠ 那十几条「note 必须包含某片段」的自检，只靠产物变异**一条都测不到**
#   （note 每次都是从模板重建的）。⇒ 必须能改构建器自己的源码。
# ⚠ 锚点必须**足够长且唯一**：第一版想改 claim 里的因子，
#   而同一个式子还出现在模块级注释里 ⇒ 只替换第一个出现会改错地方
#   （「断言定位的特征不唯一时，会找到检查但找错那条检查」的同类）。
#   ⇒ 每条都锚到 `"claim": "破坏量 = …` 这种整行前缀。
SRC_MUTATIONS = [
    ("claim 写回修订 49 那个错因子",
     '"claim": "破坏量 = ½(s·rms/‖h‖)²·2(1−c²)/[(1+ac)(√(1+2ac+a²)+1+ac)]"',
     '"claim": "破坏量 = ½(s·rms/‖h‖)²·(1−a·c)/(1+a·c)"'),
    ("claim 去掉「任何 a>0 都不与方向无关」",
     "故任何 a>0 都不与方向无关，只能说幅度小",
     "故与方向无关，只能说幅度小"),
    ("note 去掉「命名轴」",
     "**%d 条命名轴**", "**%d 个轴**"),
    ("note 去掉「不构成」",
     "它**不构成**「与语义无关」的证据", "它是「与语义无关」的证据"),
    ("note 去掉「方向重采样」",
     "**按方向重采样**的零分布后", "某个零分布后"),
    ("note 去掉「分母用错」",
     "⇒ **分母用错**。", "。"),
    ("note 去掉「随强度翻转」",
     "⚠ 符号**随强度翻转**", "⚠ 符号"),
    ("把 l1_c_spread 换回错因子（**预期不翻**：量级没变）",
     "_f = [_rel_exact(_a, _x) for _x in _c]",
     "_f = [_rel_claim(_a, _x) for _x in _c]"),
    # ⚠ 阶梯状态是**源码里的字面量**，产物改不了 ⇒ 必须改源码才能测
    ("把 L5 状态改成 done",
     '"state": "missing", "here": "0 条（余量 %.2f× < 2×）"',
     '"state": "done", "here": "0 条（余量 %.2f× < 2×）"'),
]

# ---- 第六个「输入」：生成器源码（阈值出处）------------------------------------
# ⚠⚠ 上面三条自检（[268] 找不到生成器 / [274:1] / [274:2] 读不到阈值）
#   查的是 `.cache/strengthscan/linearity_law.py` 的**文本**，它不在 `DATA` 里。
# ⚠ 做法：**不改仓库里那个生成器**，而是把变异后的副本写进 `.cache/mutbak/`，
#   再把构建器里那行 `GEN = ROOT / "…"` 指过去。
#   ⇒ 仓库文件全程只读；万一进程被杀，也不会留下半截的生成器。
GEN_LINE = 'GEN = ROOT / ".cache/strengthscan/linearity_law.py"'
GEN_MUTATIONS = [
    ("生成器路径指到不存在的文件",
     GEN_LINE, 'GEN = ROOT / ".cache/mutbak/_no_such_gen.py"', None),
    ("删掉 direction_independent 的阈值行",
     GEN_LINE, 'GEN = ROOT / ".cache/mutbak/_mut_gen.py"',
     '"direction_independent": sp < 1.0,'),
    ("把 random_indistinguishable 的阈值写成表达式（读不出来）",
     GEN_LINE, 'GEN = ROOT / ".cache/mutbak/_mut_gen.py"',
     '"random_indistinguishable": gap < 1.0}',
     '"random_indistinguishable": gap <= 1.0}'),
    # ⚠⚠⚠ **重言式的决定性实验**：把两个判定阈值从 1.0 改成 7.0。
    #   note 里「允许差到信号的 %.1f%%」会从 49.5% 变成 347% —— **读者看得见**。
    #   而 [697:4]/[697:12] 那两条自检的期望串是
    #   `("%.1f%%" % (100.0*l1_thr[...]/l1_base))` —— **同一个变量算出来的**。
    #   ⇒ 若它们是恒真重言式，这两条**不会红**，且「49.5%」会从 note 里消失。
    #   这不是「恒绿」，是「**恒真**」—— 比恒绿更坏：它长得像在查东西。
    ("判定阈值 1.0 → 7.0（**重言式实验**：note 会变，期望串也会跟着变）",
     GEN_LINE, 'GEN = ROOT / ".cache/mutbak/_mut_gen.py"',
     '                "direction_independent": sp < 1.0,\n'
     '                "random_indistinguishable": gap < 1.0}',
     '                "direction_independent": sp < 7.0,\n'
     '                "random_indistinguishable": gap < 7.0}'),
]


def main():
    print("=== 阶梯自检空转审计 ===")
    print("构建器：%s" % os.path.relpath(BUILDER, ROOT))
    print("产物变异 %d 条 + 源码变异 %d 条；每个跑两遍（门开=生产行为，门关=测牙齿）\n"
          % (len(ARTEFACT_MUTATIONS), len(SRC_MUTATIONS)))

    # ⚠⚠ W6：**审计自己**先判覆盖。某个产物一条变异都没有 ⇒
    #   那份产物驱动的自检的「恒绿」是**覆盖不足**，不是无牙齿。
    #   「空洞通过要显式报『本项无判据』」用在审计工具自己身上。
    cover = Counter(f for _, f, _ in ARTEFACT_MUTATIONS)
    holes = [f for f in ARTEFACTS if cover.get(f, 0) == 0]
    if holes:
        print("⚠⚠⚠ 本审计**本项无判据**：这些产物一条变异都没有 → %s" % holes)
        print("   它们驱动的自检的「恒绿」结论**无效**（覆盖不足 ≠ 没牙齿）。\n")

    with tempfile.TemporaryDirectory(prefix="ladaudit_") as td:
        data_dir = os.path.join(td, "data")
        shutil.copytree(DATA, data_dir)
        pristine = {f: open(os.path.join(data_dir, f), encoding="utf-8").read()
                    for f in ARTEFACTS}
        src_pristine = open(BUILDER, encoding="utf-8").read()
        mout = os.path.join(td, "m.json")
        base_out = os.path.join(td, "base.json")

        def restore():
            for f, txt in pristine.items():
                with open(os.path.join(data_dir, f), "w", encoding="utf-8") as fh:
                    fh.write(txt)

        # 基线：门关跑法（此时没有变异，应当**一条都不红**）
        base_off, base_crash = run_once(load_mod(), data_dir, base_out, False)
        base_gate, _ = run_once(load_mod(), data_dir, base_out, True)
        base_vis = _visible_text(base_out)
        n0 = len(base_off)
        # ⚠⚠ 别假设 len(set(身份)) == len(身份)：第一版用文案当身份，
        #   `L1`/`L2` 里的数字一被抹掉就撞车，41 条塌成 39 个而我毫无察觉。
        ids = [i for i, _, _ in base_off]
        n_fail0 = sum(1 for _, ok, _ in base_off if not ok)
        print("基线（门关）：%d 条自检 / **%d 个身份**（必须相等，撞车说明身份规则有毛病）、"
              "%d 条红，崩=%s" % (n0, len(set(ids)), n_fail0, base_crash or "无"))
        if n_fail0 or base_crash or len(set(ids)) != n0:
            print("\n⚠ 基线本身不干净 ⇒ 下面所有判读都不可信，先修基线。")
            for _, ok, m in base_off:
                if not ok:
                    print("   ✗ 基线就红：%s" % m[:150])
            if base_crash:
                print("   ✗ 基线崩：%s" % base_crash)
            return 2
        base_ok = {i for i, ok, _ in base_off if ok}
        base_msg = {i: m for i, _, m in base_off}
        print("基线（门开）：%d 条自检\n" % len(base_gate))

        flipped, ever_lost, rows = {}, {}, []

        def measure(tag, mod, label):
            """跑门关 + 门开两遍，返回 (新翻红数, 丢失数, 门开红数, 崩, 产物可见变化)。"""
            try:
                seen_off, crash_off = run_once(mod, data_dir, mout, False)
                seen_on, crash_on = run_once(mod, data_dir, mout, True)
                vis = _visible_text(mout)
            finally:
                restore()
            red = {i for i, ok, _ in seen_off if not ok}
            allseen = {i for i, _, _ in seen_off}
            newly = sorted(base_ok & red)
            lost = sorted(base_ok - allseen)
            for i in newly:
                flipped.setdefault(i, []).append(label)
            for i in lost:
                ever_lost.setdefault(i, []).append(label)
            vis_changed = (vis is not None and base_vis is not None and vis != base_vis)
            rows.append((tag, len(newly), len(lost),
                         sum(1 for _, ok, _ in seen_on if not ok),
                         crash_off or crash_on, vis_changed))

        # ---- 产物变异 ----
        for why, fname, fn in ARTEFACT_MUTATIONS:
            d = json.loads(pristine[fname])
            fn(d)
            blob = json.dumps(d, ensure_ascii=False)
            if blob == pristine[fname]:
                rows.append(("%s [%s]" % (why, fname), None, None, None,
                             "⚠ 变异未生效", None))
                continue
            with open(os.path.join(data_dir, fname), "w", encoding="utf-8") as fh:
                fh.write(blob)
            measure("%s [%s]" % (why, fname.replace(".json", "")),
                    load_mod(), why)

        # ---- 源码变异（note/claim 片段只在源码里存在）----
        # ⚠ 必须落在 `.cache/mutbak/`：`ROOT` 由 `__file__` 往上两级推导，
        #   换个别的深度会指向错误目录；而那个目录是 `.gitignore` 的，
        #   临时副本不会污染仓库。
        for why, old, new in SRC_MUTATIONS:
            if old not in src_pristine:
                rows.append(("源码：%s" % why, None, None, None,
                             "⚠ 锚点没找到（源码已变？特征不唯一？）", None))
                continue
            mut_src = src_pristine.replace(old, new, 1)
            if mut_src == src_pristine:
                rows.append(("源码：%s" % why, None, None, None,
                             "⚠ 变异未生效", None))
                continue
            p = os.path.join(ROOT, ".cache/mutbak/_mut_builder.py")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(mut_src)
            try:
                measure("源码：%s" % why, load_mod(p), "源码变异·%s" % why)
            finally:
                if os.path.exists(p):
                    os.remove(p)

        # ---- 第六个输入：生成器源码（只改副本，仓库那个全程只读）----
        # ⚠ 上面三条自检（[268] 找不到生成器 / [274:1] / [274:2] 读不到阈值）
        #   查的是 `.cache/strengthscan/linearity_law.py` 的**文本**，它不在 `DATA` 里。
        # ⚠ 做法：**不改仓库里那个生成器**，把变异副本写进 `.cache/mutbak/`，
        #   再把构建器里那行 `GEN = ROOT / "…"` 指过去。
        #   ⇒ 仓库文件全程只读；万一进程被杀，也不会留下半截的生成器。
        gen_src = open(os.path.join(ROOT, ".cache/strengthscan/linearity_law.py"),
                       encoding="utf-8").read()
        for entry in GEN_MUTATIONS:
            why, old, new = entry[0], entry[1], entry[2]
            drop = entry[3] if len(entry) > 3 else None
            repl = entry[4] if len(entry) > 4 else None
            if old not in src_pristine:
                rows.append(("生成器：%s" % why, None, None, None,
                             "⚠ GEN 行没找到", None))
                continue
            if drop is not None and drop not in gen_src:
                rows.append(("生成器：%s" % why, None, None, None,
                             "⚠ 生成器锚点没找到", None))
                continue
            gp = os.path.join(ROOT, ".cache/mutbak/_mut_gen.py")
            p = os.path.join(ROOT, ".cache/mutbak/_mut_builder.py")
            try:
                if drop is not None:
                    with open(gp, "w", encoding="utf-8") as fh:
                        fh.write(gen_src.replace(drop, repl or "", 1))
                with open(p, "w", encoding="utf-8") as fh:
                    fh.write(src_pristine.replace(old, new, 1))
                measure("生成器：%s" % why, load_mod(p), "生成器变异·%s" % why)
            finally:
                for f in (gp, p):
                    if os.path.exists(f):
                        os.remove(f)

        print("%-40s %5s %5s %5s %6s  %s"
              % ("变异", "门关红", "门关丢", "门开红", "产物变", "崩"))
        for tag, n_new, n_lost, n_on, crash, vis_changed in rows:
            if n_new is None:
                print("%-40s %5s %5s %5s %6s  %s"
                      % (tag[:40], "—", "—", "—", "—", crash))
                continue
            print("%-40s %5d %5d %5d %6s  %s"
                  % (tag[:40], n_new, n_lost, n_on,
                     "是" if vis_changed else "否", crash or ""))

        # ---- ⚠⚠⚠ W7：产物变了但零自检翻红 ----
        vac = [(tag, c) for tag, n, _, _, c, vc in rows
               if n is not None and vc and n == 0]
        print("\n=== ⚠ 产物变了但零自检翻红：%d 条 ===" % len(vac))
        print("   （这才是真空缺口。恒绿若**产物没变**，那是变异打空，怪变异不怪判据。）")
        for tag, c in vac:
            print("  ✗ %-40s 崩=%s" % (tag[:40], c or "无"))

        never = sorted(base_ok - set(flipped))
        print("\n--- 恒绿候选：跑到了、当前是绿的、%d 条变异一条都翻不动（%d 条）---"
              % (len(rows), len(never)))
        for i in never:
            print("  ✗ [%s] %s" % (i, base_msg[i][:130]))

        unreachable = sorted(base_ok & set(ever_lost))
        print("\n--- 测不到（门关之后仍然没跑到 ⇒ 不可达，不是「无牙齿」）：%d 条 ---"
              % len(unreachable))
        for i in unreachable:
            print("  ? [%s] %s" % (i, base_msg[i][:130]))
            print("      触发于：%s" % "、".join(ever_lost[i][:3]))
        if not unreachable:
            print("  （无）")

        covered = set(base_ok) - set(never) - set(unreachable)
        print("\n基线 %d 条：至少被翻动过 %d / 恒绿 %d / 测不到 %d"
              % (len(base_ok), len(covered), len(never), len(unreachable)))
        print("产物覆盖：%s" % {f.replace(".json", ""): cover.get(f, 0)
                                for f in ARTEFACTS})
        bad = (len(vac) > 0) or bool(holes)
        print("\n判决：%s" % ("❌ 审计不通过（W7/W6）" if bad else "✅ 通过："
                             "没有「产物变了却零自检翻红」的缺口，五产物全覆盖"))
        return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
