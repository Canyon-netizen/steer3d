"""历史臂重跑：用修订 139 的跑台过一遍修订 128–138 跑过的**全部**臂。

⚠⚠⚴ 为什么要有第二个跑台（而不是直接用 r139_run_arms.py）
  `r139_run_arms.py` 只建模**一种形状**：「扰动 ⇒ 恰好一条判据转红」。
  ⚗ 但历史 19 个臂里有**三种不同形状**：
    ① 标准：扰动 ⇒ 恰好一条红（D1/D2/A5/… 共 14 个）
    ② **合法跳过**：扰动把题数砍到 1 ⇒ D3/D4 被 `[SKIP]`、**不进分母**
       （r134b_pair：`RESULT OK 34/34`）——⚠⚠⚴ 这正是修订 134 那次**假跳过**的现场
    ③ **崩**：删掉 `#tabXY` ⇒ D5 抛异常、**压根不打印 RESULT**（r134b_xy）
  ⇒ 拿标准形状的闸门去卡 ②③，⚠⚠⚴ **会把「形状不同」误报成「臂不可信」**。

⚠⚠⚴⇒ **本台复用 r139_run_arms.py 的 `parse` / `run` / `check_baseline`**
（⚠ 不复制一份：复制＝把它的 bug 也复制过去；改它则要连带重验它的牙齿测试）。

⚠⚠⚴ 落地两半的**形状**也要分开判（这是本轮新踩的）：
  · **布尔型** occ（before/after 是 0/1）：要求 `before>0 且 after===0`
  · **取数型** occ（before/after 是计数）：要求 `before != after`
  ⚗⚠⚴⚠⚴ **两者混用就会误报**：r134b_pair 的 landing 是 `{"before":6,"after":1}`
  ⚗（选项数 6→1），⚗ 用「after===0」去卡它 ⇒ **恒判不成立**，而扰动其实生效了。

⚠⚠⚴⚠⚴ **无声明的臂不许判合格**：`r134b_path_dgroup` 在预登记里**没被点名**，
⚠ 没有可引用的声明 ⇒ 本台只**记录实测**，⚠ **不发合格/不合格**。
⚠⚠⚴ **「没记录」≠「合格」**，⚠ 也不等于「不合格」——⚗ **跳过 ≠ 通过**。
"""

import importlib.util
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec_ = importlib.util.spec_from_file_location(
    "r139_run_arms", ROOT / ".cache/mutbak/r139_run_arms.py")
R139 = importlib.util.module_from_spec(spec_)
spec_.loader.exec_module(R139)

OUT = ROOT / ".cache/mutbak/r141_hist"
SPEC = ROOT / ".cache/mutbak/r141_hist_spec.json"


def find_before_after(obj):
    """递归找出 JSON 里第一对 before/after —— 形状不一（布尔型 / 取数型 / 嵌套）都能取到。"""
    befores, afters = [], []

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k == "before" and not isinstance(v, (dict, list)):
                    befores.append(v)
                elif k == "after" and not isinstance(v, (dict, list)):
                    afters.append(v)
                else:
                    walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(obj)
    return (befores[0] if befores else None, afters[0] if afters else None)


def landed_evidence(a):
    """从日志里取落地取证（兼容 `[扰动已落地]` 与修订 134 的裸 `臂 X：{…}` 两种写法）。"""
    for key in ("landed", "notlanded"):
        hit = a.get(key)
        if hit:
            b, aft = find_before_after(hit[1])
            return hit[0], hit[1], b, aft, key == "notlanded"
    # ⚠ r139 的两条正则只认「[扰动已落地] 臂 X：」这一种写法；修订 134 的臂打的是
    #   「臂 fork：{...}」，⇒ 这里补一次宽松匹配。⚗⚠⚴ 放宽只放宽**取证行的前缀**，
    # ⚗ 判据侧的 RED/SKIP 匹配一个字都没放宽。
    # ⚠⚠⚴⚠⁴ 但还有一格更窄的：**r136 的 a1 臂打的是「[扰动未落地] {json}」——
    #   连 `臂 X：` 那一段都没有** ⇒ r139 的正则匹配不上 ⇒ 被记成「日志里没有取证行」。
    # ⚠⚠⁴ **日志里明明有取证**，⚗ 是匹配器窄了一格 ⇒ ⚗ **仪器读不到 ≠ 对象不存在**
    # ⚠ （这一族已栽过 8 次，见修订 135/139）。⚠ 这里补，**不改 r139**
    # ⚠ （它有已通过的牙齿测试，改它要连带重验）。
    import re
    txt = Path(a["_log"]).read_text(encoding="utf-8", errors="replace")
    m = re.search(r"\[扰动未落地\]\s*(?:臂\s*(\S+?)：)?\s*(\{.*\})", txt)
    if m:
        try:
            obj = json.loads(m.group(2))
        except Exception:
            return (m.group(1), None, None, None, True)
        b, aft = find_before_after(obj)
        return (m.group(1), obj, b, aft, True)
    m = re.search(r"臂\s*(\S+?)：(\{.*\})", txt)
    if m:
        try:
            obj = json.loads(m.group(2))
        except Exception:
            return None, None, None, None, False
        b, aft = find_before_after(obj)
        return m.group(1), obj, b, aft, False
    return None, None, None, None, False


def check_landing(a):
    """落地核验。返回 (问题清单, 证据文本)。⚠ 形状不同 ⇒ 判据不同。"""
    # ⚠⚠⚴ 第一版在这里写了一句 `a["_log"] = str(OUT / "placeholder")`，
    #   ⚗ 把调用方刚设好的**正确日志路径冲成了占位路径** ⇒ 后面 read_text 抛
    #   FileNotFoundError、整个跑台在第一个臂上就崩了。
    #   ⚠⚠⚴ **基线那一行已经打印完了**（它走的是另一条路径），
    #   ⚠ **所以这一崩看起来像「跑臂失败」，其实是仪器自己坏了** ——
    #   ⚗⚠⚴ **绝不能把「仪器报错」记成「臂不通过」**（修订 139 §139.3 同族）。
    name, obj, b, aft, notlanded = landed_evidence(a)
    if notlanded:
        return [f"扰动未落地 {obj}"], f"未落地 {obj}"
    if obj is None:
        return ["日志里没有落地取证行"], "无"
    if b is None or aft is None:
        return [f"取证行里取不到 before/after：{obj}"], str(obj)
    # ⚠⚠⚴⚠⁴ 第一版写的是 `b in (0,1) or aft in (0,1)` ⇒ **只要有一边是 1 就判成布尔型**。
    # ⚗ `r134b_pair` 的落地是 `{"before":6,"after":1}`（配对题 6→1）——
    # ⚗ after 是 1 ⇒ 被误判成布尔型 ⇒ 报「落地不成立」，⚗**而扰动其实生效了**。
    # ⚠⇒ 布尔型的定义是**两边都在 {0,1}**，⚠ 只要有一边是别的整数就是**取数型**。
    booleany = (isinstance(b, int) and isinstance(aft, int)
                and b in (0, 1) and aft in (0, 1))
    if booleany:
        if not (b > 0 and aft == 0):
            return [f"⚠⚠⚴ 布尔型落地不成立：before={b} after={aft}"], f"布尔 {b}→{aft}"
        return [], f"布尔 {b}→{aft}"
    if b == aft:
        return [f"⚠⚠⚴ 取数型落地不成立：before={b} after={aft}（没变）"], f"取数 {b}→{aft}"
    return [], f"取数 {b}→{aft}"


def check_shape(arm, a, b, base_total):
    """按臂**声明的形状**对账。⚠ 无声明 ⇒ 只记录，不判合格。"""
    exp = arm.get("expect")
    name = arm["name"]
    why = []
    if exp is None:
        return ["⚗ 无声明 —— 只记录实测，不判合格"], None
    if exp.get("crash"):
        if a["result"] is not None:
            why.append(f"声明期望崩，实际打出了 RESULT {a['result']} {a['ok']}/{a['total']}")
        return why, "期望崩"
    if exp.get("skip"):
        want = exp["skip"]
        miss = [w for w in want if w not in a["skip"]]
        if miss:
            why.append(f"⚠⚠⚴ 期望跳过的没跳过：缺 {miss}（实测 {a['skip']}）")
        extra = [s for s in a["skip"] if s not in want]
        if extra:
            why.append(f"⚠ 多跳了 {extra}")
        if a["total"] is not None and base_total is not None and a["total"] >= base_total:
            why.append(f"⚠⚠⚴ 声明分母应变小，实际 {a['total']} ≥ 基线 {base_total}")
        return why, "期望跳过"
    want = exp.get("flips")
    if want is None:
        return ["⚗ expect 既没 flips 也没 skip/crash —— 不判"], None
    if sorted(want) != sorted(a["red"]):
        why.append(f"⚠⚠⚴ 翻面的是 {a['red']}，声明的是 {want}")
    if a["total"] is not None and base_total is not None and a["total"] != base_total:
        why.append(f"⚠⚠⚴ 分母与基线不一致：臂 {a['total']} vs 基线 {base_total}")
    return why, f"期望翻面 {want}"


def main():
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)

    # ---- 基线（本轮实跑）--------------------------------------------------
    base_script = ROOT / spec["src"]
    base_log = OUT / "baseline.log"
    t0 = time.time()
    R139.run(str(base_script), str(base_log))
    b = R139.parse(base_log)
    b["_log"] = str(base_log)
    print("=== 基线（本轮实跑）===")
    print(f"  {b['result']} {b['ok']}/{b['total']}  红 {b['red']} 跳过 {b['skip']}"
          f"  用时 {time.time()-t0:.0f}s")
    base_problems = R139.check_baseline(b)
    for p in base_problems:
        print(f"  ⚠⚠⚴ {p}")

    # ⚠⚠⚴⚠⚴ **基线不绿 ⇒ 一个臂都不要再跑。**
    #   第一版基线装置故障（页面 40s 没 boot，压根没有 RESULT 行）时，
    #   它照样往下跑了第一个臂，然后因为仪器 bug 崩掉 ——
    #   ⚗ 那样的话，**「臂跑失败」和「基线没起来」会被混成同一件事**。
    #   ⚠⚠⚴ 而基线没起来时跑出来的任何红，⚗ **都证明不了任何东西**（装置坏了）。
    if base_problems:
        print("\n[停止] ⚠⚠⚴ 基线不绿 —— 装置问题，本轮不发数，"
              "**一个臂都不跑**（跑出来的红证明不了任何东西）。")
        print(f"[错误] 基线日志：{base_log.relative_to(ROOT)}")
        return 2

    rows = []
    for arm in spec["arms"]:
        node = ROOT / arm["node"]
        log = OUT / f"{arm['name']}.log"
        t1 = time.time()
        # ⚠⚠⚴⚠⚴ **必须按臂设环境变量。**
        #   r134b_*.mjs 是**同一个文件带 `R134_ARM` 开关**（默认 `'fork'`）。
        #   ⚗ 不设 ⇒ all/pair/xy 三个臂**全都静默跑成 fork**，还会给出一张
        #   ⚗ 「D2 没牙齿、D3 没跳过、D5 不崩」的**看起来完全正常**的判决表。
        #   ⚠⚠⁴ 这里不改动 r139_run_arms.py（它有已通过的牙齿测试，⚠ 改它要连带重验），
        #   ⚠ 只在调用前后临时改 os.environ —— R139.run 继承的就是它。
        saved_env = {k: os.environ.get(k) for k in (arm.get("env") or {})}
        for k, v in (arm.get("env") or {}).items():
            os.environ[k] = v
        try:
            R139.run(str(node), str(log))
        finally:
            for k, v in saved_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        a = R139.parse(log)
        a["_log"] = str(log)
        lwhy, ldesc = check_landing(a)

        # ⚠⚠⚴⚠⁴ 新闸门：**日志自称的臂名必须等于声明的臂名。**
        #   ⚗ 第一版没有这道闸 ⇒ 三个臂跑成了 fork 却照样出了判决表。
        #   ⚠⚠⁴ 日志里本来就写着 `[扰动已落地] 臂 fork` —— ⚠ **信息一直在，是没人核。**
        want_self = arm.get("self")
        if want_self:
            got_self = a["landed"][0] if a["landed"] else (
                a["notlanded"][0] if a["notlanded"] else None)
            if got_self != want_self:
                lwhy.append(f"⚠⚠⚴⚠⚴ **日志自称跑的是 `{got_self}`，声明要跑的是 `{want_self}`**"
                            f" ⇒ 这不是 {arm['name']} 的结果")

        swhy, sdesc = check_shape(arm, a, b, b["total"])
        why = lwhy + swhy
        rows.append((arm["name"], sdesc, ldesc, a, why, time.time() - t1))
        st = "✅" if not why else ("⚗" if sdesc is None else "⚠")
        print(f"\n  {st} {arm['name']:<14} {str(sdesc):<22} 落地:{ldesc:<14} "
              f"实测 {a['result'] or '(无RESULT)'} {a['ok']}/{a['total']} "
              f"红{a['red']} 跳过{a['skip']} {time.time()-t1:.0f}s")
        for w in why:
            print(f"        ⚠ {w}")

    print("\n=== 汇总 ===")
    ok = [r for r in rows if not r[4]]
    bad = [r for r in rows if r[4] and r[1] is not None]
    nod = [r for r in rows if r[1] is None]
    print(f"  过 {len(ok)} / 有问题 {len(bad)} / 无声明只记录 {len(nod)}  合计 {len(rows)}")
    print(f"  ⚠ 基线问题 {len(base_problems)} 条")
    if base_problems or bad:
        print("\n[注意] 以上问题的性质各不相同，⚠ **不要合并成一个数字**。")
    return 0 if (not base_problems and not bad) else 2


if __name__ == "__main__":
    sys.exit(main())