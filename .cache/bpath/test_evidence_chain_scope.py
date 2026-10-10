#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 48 守卫：证据链的**条目名覆盖范围**，与第二层欠账。

三件事，每一件都有变异台架：

**T1** A2 的条目名必须带着它的实际范围（「仅：重跑==五个冻结快照的确定性函数」）。
  修订 48 之前它叫「阶梯产物可复算」，而它验的只是
  「重跑 `build_evidence_ladder.py` 的输出 == 交付文件」。名字比判据宽 ⇒
  读者会以为阶梯里的数字能从干净克隆重造出来。名字改回去，这里就红。

**D1** A3 必须**红**，且红的原因必须**恰好是 `cot_texts.json` 一个**。
  ⚠ 这里钉的不是「必须红」这个结论，而是**红的粒度**：如果哪天
  `cot_texts` 的生成器被 track 进来，A3 应当转绿；如果另外四份退化回
  「只写本地副本」，A3 也应当改变说法。两个方向都要能变。

**D2/D3** 检测器本身的牙齿：
  · 阳性对照 —— `arm_asymmetry` 必须找得到仓库内生成器
    （否则 A3 只是一条**恒红**判据，和恒绿一样没用）；
  · 反向锚点 —— `build_evidence_ladder.py` 是这五份产物的**消费者**，
    它自己也写盘且五个名字全都在文件里；它**绝不能**被判成其中任何一份的生成器。
    第一版检测器正是漏了这一条（写条件不带名字），把 4/5 个真实生成器报成 0 个。

用法：
    PYTHONPATH=.cache/pylibs python3 .cache/bpath/test_evidence_chain_scope.py
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, ".cache/pylibs"))

_spec = importlib.util.spec_from_file_location(
    "chain", os.path.join(ROOT, ".cache/bpath/audit_evidence_chain.py"))
chain = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(chain)

SCOPE_WORD = "五个冻结快照的确定性函数"
UPSTREAMS_D = ("linearity_law", "readable_subspace",
                "heldout_readability", "arm_asymmetry", "cot_texts")
# 这四个的生成器确实在仓库内且写的就是交付那份（2026-10-11 实测逐条核对过）
FOUND = ("linearity_law", "readable_subspace", "heldout_readability",
         "arm_asymmetry")
MISSING = "cot_texts"
CONSUMER = ".cache/xcheck/build_evidence_ladder.py"

fails: list[str] = []


def ok(cond, label, detail=""):
    print(f"[{'通过' if cond else '**失败**'}] {label}" + (f"  —— {detail}" if detail else ""))
    if not cond:
        fails.append(label)
    return cond


def run_a2() -> tuple[str, str]:
    chain.results = []
    chain.check_a2()
    name, _, detail, _ = chain.results[-1]
    return name, detail


def run_a3() -> tuple[bool, str]:
    chain.results = []
    chain.check_a3()
    _, good, detail, _ = chain.results[-1]
    return good, detail


def parse_buckets(detail: str) -> dict[str, list[str]]:
    """把 A3 的 detail 拆成六档（修订 53 加了「输入名不可静态定名」）。

    ⚠⚠ 必须按**档标签前缀**解析，不能按位置劈字符串：
    detail 结尾有「非执行；不覆盖 torch/npz/远端」这种说明句，
    里面也有档名用到的字样。第一版用 `detail.split("无")[-1]` 取档位，
    取到的是「无机械出处」那句 —— 被自己的守卫逼红过。
    """
    out = {k: [] for k in ("静态可达", "写死路径", "输入不在仓库",
                           "输入名不可静态定名", "本项无判据", "仓库内无")}
    for part in detail.split("；"):
        part = part.strip()
        for u, lab in ((f"{n}.json → {k}", k) for n in UPSTREAMS_D for k in out):
            if part.startswith(u):
                out[lab].append(part.split("（")[0].strip())
                break
    return out


def main() -> int:
    # ---------------- T1 ----------------
    name, detail = run_a2()
    ok(SCOPE_WORD in name, "T1 A2 条目名带着它的实际范围",
       f"name={name!r}")
    ok(detail == "逐字节一致", "T1b A2 本身仍通过（改的是名字不是判决）", detail)

    # ---------------- D1 ----------------
    good, detail = run_a3()
    ok(good is False, "D1 A3 仍是红的（cot_texts 无生成器，subspace 输入未跟踪）", detail)
    b = parse_buckets(detail)
    # ⚠⚠ 修订 53 改了口径，A3 的档位分布随之改变。**这不是把红改成绿** ——
    #   仍然是红，只是红的理由从「三个都写死路径」变成了下面这组更准的分布。
    # ⚠⚠ **每个断言都要写清「为什么是这一档」**，否则以后有人把它改回去
    #   也没有线索知道改错了什么。
    ok(b["静态可达"] == ["heldout_readability.json → 静态可达",
                        "arm_asymmetry.json → 静态可达"],
       "D1b 恰好两项静态可达：heldout（7 个 .json 全在仓库）与 arm_asymmetry"
       "（4 个输入全在仓库）—— 这正是 U1b′ 扩到数据类扩展名后的效果",
       str(b["静态可达"]))
    ok(b["写死路径"] == [],
       "D1c 「写死路径」档已清空（修订 53 把四个生成器的 ROOT 改成 __file__ 推导）",
       str(b["写死路径"]))
    ok(b["仓库内无"] == [f"{MISSING}.json → 仓库内无"],
       f"D1d {MISSING}.json 落在「仓库内无」档", str(b["仓库内无"]))
    ok(b["本项无判据"] == ["linearity_law.json → 本项无判据"],
       "D1e 空洞通过被堵住：linearity_law 唯一的数据类字面量是**它自己的输出路径**，"
       "剔掉之后输入集为空 ⇒ 必须落进「本项无判据」而不是「静态可达」",
       str(b["本项无判据"]))
    ok("linearity_law.json → 静态可达" not in detail,
       "D1f 反向锚点：linearity_law 绝不能被判「静态可达」"
       "（它真正的输入是远端 npz，不在仓库里）", "")
    ok(b["输入不在仓库"] == ["readable_subspace.json → 输入不在仓库"],
       "D1g subspace 落在「输入不在仓库」（P.npy / axes.npy / dim_names.json 未跟踪）",
       str(b["输入不在仓库"]))

    # ---------------- D2 阳性对照 ----------------
    gen = chain.generator_of("arm_asymmetry")
    ok(gen is not None, "D2 检测器能找到真实的仓库内生成器（非恒红）", str(gen))
    ok(gen == ".cache/xcheck/arm_asymmetry.py", "D2b 找对了那一个", str(gen))

    # ---------------- D3 反向锚点 ----------------
    for u in chain.UPSTREAMS:
        hits = [r for r, _ in chain.writes_named_artifact(u)]
        ok(CONSUMER not in hits,
           f"D3 消费者 {CONSUMER.split('/')[-1]} 未被当成 {u} 的生成器",
           f"hits={hits}")

    # ---------------- 变异台架 ----------------
    print("\n--- 变异（每条都必须让上面某条断言红）---")

    # M1：写死路径检测失灵 ⇒ 三个「写死路径」档应当消失
    saved_hard = chain._HARD_ABS
    chain._HARD_ABS = re.compile(r"(?!x)x")          # 永不匹配
    _, d = run_a3()
    b1 = parse_buckets(d)
    # ⚠ 第一版这里断言「三个都掉进「输入不在仓库」」，红了 —— 但**系统是对的**：
    #   `build_heldout_readout.py` 与 `arm_asymmetry.py` 里根本没有 .npy 字面量，
    #   它们先撞上「本项无判据」那条更早的分支。
    #   ⇒ 正确的期望是「写死路径档清空，且没有任何一个落到「静态可达」」。
    ok(len(b1["写死路径"]) == 0
       and len(b1["输入不在仓库"]) + len(b1["本项无判据"]) + len(b1["静态可达"]) == 4,
       "M1 写死路径检测失灵 ⇒ 档位分布不变", str(b1))
    chain._HARD_ABS = saved_hard
    # ⚠⚠ M1 现在**打空**了 —— 因为它针对的缺陷已在修订 53 里修掉（四个生成器
    #   的 ROOT 都不再写死）。「变异没生效」和「判据没牙齿」在报告里长得一样，
    #   所以必须补一条**阳性对照**证明检测器本身还活着，否则这条变异就是恒真。
    # ⚠ 探针用拼接构造，不在文件里留下完整字面形态。
    # ⚠⚠ 第二版用 `repr()` 造探针 —— 它产出**单引号**，而 `_HARD_ABS` 只认双引号
    #   ⇒ 探针不命中、被守卫逼红。**阳性对照自己写错，等于没有对照。**
    #   这里用 chr(34) 明确要一个双引号。
    _probe = "ROOT = Path(" + chr(34) + "/Users/zhourui/code/steer3d" + chr(34) + ")"
    ok(bool(chain._HARD_ABS.search(_probe)),
       "M1b 阳性对照：写死路径检测对拼接出来的绝对路径字面量确实命中"
       "（证明 M1 打空是因为缺陷已修，不是因为检测器失灵）", _probe)

    # M2：把唯一的「仓库内无」抹掉 ⇒ A3 仍红（另三个仍不可达），且那条消失
    saved_up = chain.UPSTREAMS
    chain.UPSTREAMS = tuple(u for u in saved_up if u != MISSING)
    good2, d2 = run_a3()
    # ⚠ 第一版写成 `"仓库内无" not in parse_buckets(d2)`，那是查 **dict 的键**
    #   —— 键永远存在 ⇒ 恒假。必须查**那一档的列表是不是空的**。
    ok(good2 is False and parse_buckets(d2)["仓库内无"] == [],
       "M2 抹掉仓库内无那一项 ⇒ 该档变空但 A3 仍红（不是恒红判据）",
       parse_buckets(d2)["仓库内无"])
    chain.UPSTREAMS = saved_up

    # M3：定位失灵 ⇒ 五个全部落进「仓库内无」
    saved_nl = chain._name_lines
    chain._name_lines = lambda txt, name: []
    _, d3 = run_a3()
    b3 = parse_buckets(d3)
    ok(len(b3["仓库内无"]) == len(UPSTREAMS_D), "M3 定位失灵 ⇒ 五个全部落进「仓库内无」",
       str(b3))
    chain._name_lines = saved_nl

    # M4（打空是正确性质，必须写进用例）：写盘条件放宽会怎样
    saved_wc = chain._WRITE_CALL
    import re as _re
    chain._WRITE_CALL = _re.compile(r"^")
    hits_loose = [r for r, _ in chain.writes_named_artifact("linearity_law")]
    chain._WRITE_CALL = saved_wc
    ok(CONSUMER in hits_loose or hits_loose,
       "M4 写盘条件确实是承重的（放宽后定位到的集合改变）",
       f"放宽后 hits={hits_loose}；严格时 "
       f"{[r for r, _ in chain.writes_named_artifact('linearity_law')]}")

    # ================= 修订 53：U1b′ 口径与 A4 的变异台架 =================
    # ⚠ 预登记 §53.4 写死了 N3/N4/N5 三条，并在末尾写明：
    #   「若这两条打不空，说明新口径没有实际作用，应当**撤回**而不是硬留着」。

    # N3：把扩展名集缩回修订 52 的那 1 项 ⇒ heldout 必须被打回「本项无判据」
    saved_ext = chain._DATA_EXT
    chain._DATA_EXT = (".npy",)
    _, dN3 = run_a3()
    chain._DATA_EXT = saved_ext
    bN3 = parse_buckets(dN3)
    ok(bN3["静态可达"] == ["arm_asymmetry.json → 静态可达"]
       and "heldout_readability.json → 本项无判据" in bN3["本项无判据"],
       "N3 扩展名集缩回只有 .npy ⇒ heldout 从「静态可达」打回「本项无判据」"
       "（证明 U1b′ 的扩展名扩展真的在起作用，不是摆设）", str(bN3))

    # N4：精确路径 vs basename 兜底
    # ⚠⚠ **在当前数据上 N4 是打空的** —— 五个上游的输入没有任何一个出现
    #   「basename 命中但精确路径没命中」的情形，所以缩掉精确匹配不会改变
    #   任何一档。**打空是正确性质，必须写进用例**（同 M4）。
    #   所以另配一条**合成阳性对照**证明精确匹配确实有牙齿。
    _unchanged = run_a3()[1]
    saved_dp = chain._dir_prefixes
    chain._dir_prefixes = lambda s: {}
    _, dN4 = run_a3()
    chain._dir_prefixes = saved_dp
    bN4 = parse_buckets(dN4)
    ok(bN4 == b,
       "N4（打空是正确性质）关掉精确匹配后当前五项档位不变 ⇒ "
       "精确匹配在**这批数据**上未被区分，必须靠合成阳性对照证明它有牙齿",
       f"关掉后={bN4}")

    _src_syn = ('XC = ROOT / ".cache/xcheck"\n'
                'A = json.loads((XC / "axis_readouts.json").read_text())\n')
    ex_exact, _, _ = chain.data_inputs(_src_syn)
    chain._dir_prefixes = lambda s: {}
    _, _, ex_bare = chain.data_inputs(_src_syn)
    chain._dir_prefixes = saved_dp
    _tset, _tb = set(chain.tracked_files()), chain.tracked_basenames()
    ok(ex_exact == {".cache/xcheck/axis_readouts.json"}
       and not (ex_exact & _tset)          # 精确路径**确实**没被跟踪
       and "axis_readouts.json" in ex_bare
       and "axis_readouts.json" in _tb,    # 而 basename **会**命中 ⇒ 兜底会误判
       "N4b 合成阳性对照：同一 basename 在别的目录时，精确判「未跟踪」而 "
       "basename 兜底会误判为命中 ⇒ 精确匹配确实强于兜底",
       f"exact={sorted(ex_exact)}（未跟踪={not (ex_exact & _tset)}）；"
       f"bare={sorted(ex_bare)}（basename 命中={'axis_readouts.json' in _tb}）")

    # N5：A4 的反空洞条款 —— 一个都没执行时必须自己判红
    saved_nr = chain._NEEDS_REMOTE
    chain._NEEDS_REMOTE = re.compile(".*")          # 谁都变成「要 torch/远端」
    okN5, detN5 = chain.a4_report()
    chain._NEEDS_REMOTE = saved_nr
    ok(okN5 is False and "本项无判据" in detN5,
       "N5 一个都没执行时 A4 必须自己判红并报「本项无判据」，不许报「0 失败」",
       detN5[:110])

    # ---------------- A4 的牙齿（在真实数据上） ----------------
    okA4, detA4 = chain.a4_report()
    ok("2/3 跑通且逐字节相同" in detA4,
       "T4 A4 在干净克隆里真跑：2/3 逐字节相同（heldout + arm_asymmetry）",
       detA4[:130])
    ok("执行失败·缺输入" in detA4 and "**未**被跟踪" in detA4,
       "T4b A4 的执行失败必须点名**缺哪个输入**并说明它在仓库里未被跟踪"
       "（不许合成一句「跑不起来」）", "")
    # ⚠⚠ T4c 第一版从「执行失败·缺输入：」后面抠名字，而那段第二版打的是
    #   **绝对路径**且被 [:90] 截断 ⇒ 抠出来的是个残串，拿它去问
    #   「在不在 git ls-files 里」必然答「不在」⇒ **空洞通过**。
    #   修法：从 note 里抠**仓库相对路径**，并要求它**没被截断**（含 "/" 且够长）。
    _m = re.search(r"执行失败·缺输入：(\S+?)（(\S+) 在仓库里\*\*未\*\*被跟踪）", detA4)
    _rel = _m.group(1) if _m else None
    ok(_m is not None and _rel == _m.group(2)
       and "/" in _rel and _rel not in _tset and os.path.exists(
           os.path.join(chain.ROOT, _rel)),
       "T4c 被点名的那个输入是**完整的仓库相对路径**，且它确实不在 git ls-files 里、"
       "但在本机存在（⇒ 是「没进仓库」而不是「压根没有」）",
       f"rel={_rel!r}；在 git ls-files 里={_rel in _tset if _rel else '?'}")
    ok("克隆自证" in detA4 and "不在=True" in detA4,
       "T4d A4 自证那个目录确实是干净克隆（被跟踪的在、未跟踪的不在）", "")

    # N1：逐字节比对器必须有牙齿 —— 两份只在空白/键序上不同的 JSON 不算相等
    import tempfile as _tf
    with _tf.TemporaryDirectory() as _td:
        _p1 = os.path.join(_td, "a.json")
        _p2 = os.path.join(_td, "b.json")
        with open(_p1, "w", encoding="utf-8") as _f:
            _f.write('{"a":1,"b":2}')
        with open(_p2, "w", encoding="utf-8") as _f:
            _f.write('{"b":2, "a":1}')          # 解析成 JSON **相等**，字节不同
        _same = chain._same_bytes(_p1, _p1)
        _diff = chain._same_bytes(_p1, _p2)
    ok(_same is True and _diff is False,
       "N1 逐字节比对器有牙齿：同一文件为真、键序不同的两份 JSON 为假"
       "（⚠ 解析成 JSON 再比相等会把键序/空白差异全吞掉）",
       f"same={_same} diff={_diff}")

    # 收尾：全部恢复后再跑一遍，确认状态没被变异污染
    run_a2()
    good3, detail3 = run_a3()
    ok(good3 is False and f"{MISSING}.json" in detail3,
       "恢复后 A3 回到原始红态", detail3)

    print(f"\n{len(fails)} 条失败" + ("" if not fails else "：" + "、".join(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())