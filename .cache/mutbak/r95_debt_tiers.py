#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 95：513 条在册欠账的**成分分层** —— 有多少是「名字全站不存在」。

诊断探针，不判红绿。

⚠⚠ 动机：修订 94 撤回了「通用 key 渲染」那条解释之后，
  那 3 个产物剩下的 51 条候选**失去了「可能是假阳性」的托词**，
  ⇒ 必须重新回答「513 条欠账到底是什么构成的」才能决定下一步。

⚠⚠⚴ 本脚本**不**重新计算未渲染集合 —— 母判据已经算过，
  台账就是它的快照（修订 89 已核实：非 z5 513 == 实跑 513，逐条相等）。
  ⇒ 本脚本只做**分层**，不做判决。

分层定义（每条台账条目必落且只落一层）：
  A · 名字**全前端源码 0 处** —— 最强信号
  B · 名字出现在源码里，但**不在本条目的归属宿主**里 —— 作用域假阳性候选
  C · 名字在本条目的宿主里 —— ⚠ 按母判据规则这不可能发生，
      若真的 >0 ⇒ 说明台账与实跑已经漂移，是**红信号**，脚本要报出来

⚠⚠ **A 也不等于「没上屏」**：仍可能有动态 key 拼接、
  `JSON.stringify` 整块上屏（修订 94 已查到 10 条落在那条路上）等路径。
  ⇒ 输出只能叫「分层」，不能叫「判决」。

⚠ 校准：§90.4 在三个被排除产物上用**同一套判法**得出
  A 51 / B 13 / 共 64 ⇒ 本脚本把那三个产物也跑一遍，
  数字对不上就 exit 2 不发数（修订 94.5 的教训：重新实现必须先校准）。
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FE = ROOT / "frontend"
IDX = FE / "public/latent/index.html"
DEBT = ROOT / ".cache/xcheck/check_render_coverage_sitewide.debt.json"

# 修订 94 查到的 JSON.stringify 兜底渲染路径（evOneLine 的 default 分支）
DUMPED_GATES = {"阈值表有牙齿", "定律的适用率", "阈值可预测"}


def name_pattern(name):
    return re.compile(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])")


def load_all_src():
    """全前端源码。⚠ 刻意排除 node_modules 与 .next ——
    修订 87 已确认 .next 比源码旧（text-[9px] 源码 90 处 / .next 产物 0 次），
    拿旧产物当证据会得出「已渲染」的假阴性。"""
    out = {}
    for pat in ("components/*.tsx", "lib/*.ts", "app/**/*.tsx", "app/**/*.ts",
                "public/*.html", "public/latent/*.html"):
        for p in sorted(FE.glob(pat)):
            try:
                out[p] = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                pass
    return out


def load_hosts():
    """母判据 :121-128 的宿主集合。"""
    out = {}
    for p in sorted(FE.glob("components/*.tsx")):
        out[p] = p.read_text(encoding="utf-8")
    if IDX.exists():
        out[IDX] = IDX.read_text(encoding="utf-8")
    return out


def tier(field, artifact_name, all_src, hosts, owner_paths):
    hits = [p for p, s in all_src.items() if name_pattern(field).search(s)]
    if not hits:
        return "A", []
    in_owner = [p for p in hits if p in owner_paths]
    if in_owner:
        return "C", in_owner
    return "B", hits


def main():
    all_src = load_all_src()
    hosts = load_hosts()
    print("=" * 78)
    print("修订 95 · 513 条在册欠账的成分分层（诊断探针，不判红绿）")
    print("=" * 78)
    print(f"\n[口径·源码] 全前端源码 {len(all_src)} 个文件"
          f"（已排除 node_modules 与 .next；要求 > 0）")
    print(f"[口径·宿主] 母判据的宿主集合 {len(hosts)} 个")

    debt = json.loads(DEBT.read_text(encoding="utf-8"))
    ents = debt["debt"]
    in_scope = [e for e in ents if not e["artifact"].startswith("z5::")]
    z5 = [e for e in ents if e["artifact"].startswith("z5::")]
    print(f"[口径·台账] 总 {len(ents)} 条 = 在册非 z5 {len(in_scope)} + z5 {len(z5)}")

    buckets = {"A": [], "B": [], "C": []}
    for e in in_scope:
        art = Path(e["artifact"]).name
        owner_paths = {p for p, s in hosts.items() if art in s}
        t, hits = tier(e["field"], art, all_src, hosts, owner_paths)
        buckets[t].append((e, hits))

    n = len(in_scope)
    print(f"\n[分层] {n} 条：")
    for t, desc in (("A", "名字全前端源码 0 处（最强信号）"),
                    ("B", "名字在别处出现，但不在本条目宿主里（作用域假阳性候选）"),
                    ("C", "名字在本条目宿主里 —— ⚠ 按母判据规则不该发生")):
        k = len(buckets[t])
        print(f"  {t} · {k:>4} 条（{k/n*100:5.1f}%）  {desc}")

    if buckets["C"]:
        print(f"\n[红信号] C 层有 {len(buckets['C'])} 条 ⇒ 台账与实跑已漂移，"
              f"本轮分层不可信")
        for e, _h in buckets["C"][:8]:
            print(f"   {Path(e['artifact']).name:<26} {e['field']}")
        sys.exit(2)
    print(f"  ⇒ C = 0，符合母判据规则（名字在宿主里就不算未渲染）✔")

    # 与 §94 的 JSON.stringify 盲路对齐
    print("\n[与修订 94 对齐] 其中字段名落在 evOneLine 兜底渲染的 evidence 键里的：")
    ltv = json.loads((FE / "public/latent/data/ltv.json").read_text(encoding="utf-8"))
    ev_keys = set()
    def scan(o):
        if isinstance(o, dict):
            if "evidence" in o and isinstance(o["evidence"], dict) \
               and o.get("name") not in {"恒等自证", "幅度配平自证", "与录制数据一致",
                                        "反事实存在", "存在方向性层", "内容窗可定位",
                                        "描述-因果重叠", "对照不等价", "名字预测效果"}:
                ev_keys.update(o["evidence"].keys())
            for v in o.values():
                scan(v)
        elif isinstance(o, list):
            for v in o:
                scan(v)
    scan(ltv)
    dumped = [e for e, _ in buckets["A"] + buckets["B"] if e["field"] in ev_keys]
    print(f"  {len(dumped)} 条（修订 94 实测也是 10 条 —— 交叉核对点）")

    # ── 校准：对三个被排除产物用同一套判法，应复现 §90.4 的 A 51 / B 13 ──
    print("\n" + "=" * 78)
    print("[校准] 同一套判法跑三个被排除产物，应复现 §90.4 的 A 51 / B 13")
    print("=" * 78)
    excl = ["linearity_law.json", "logit_lens.json", "path_readout.json"]
    cal = {"A": 0, "B": 0, "C": 0}
    for art in excl:
        af = FE / "public/latent/data" / art
        data = json.loads(af.read_text(encoding="utf-8"))
        acc = []

        def walk(o, p="", acc=acc):
            if isinstance(o, dict):
                for k, v in o.items():
                    walk(v, f"{p}.{k}" if p else str(k), acc)
            elif isinstance(o, list):
                for i, v in enumerate(o):
                    walk(v, f"{p}[{i}]", acc)
            elif o is not None and not (isinstance(o, str) and o == ""):
                acc.append(p)
        walk(data)

        def fn(path):
            x = path.rsplit(".", 1)[-1] if "." in path else path
            if "[" in x:
                h = x.partition("[")[0]
                x = h if h else x
            return x

        names = {}
        for pth in acc:
            f_ = fn(pth)
            if f_ and f_ not in names:
                names[f_] = pth
        owner_paths = {p for p, s in hosts.items() if art in s}
        for f_ in sorted(names):
            if not any(name_pattern(f_).search(hosts[q]) for q in owner_paths):
                t, _h = tier(f_, art, all_src, hosts, owner_paths)
                cal[t] += 1
    print(f"\n  本脚本  A {cal['A']} / B {cal['B']} / C {cal['C']}   （应复现 §90.4 的 51 / 13 / 0）")
    if (cal["A"], cal["B"], cal["C"]) != (51, 13, 0):
        print(f"\n[错误] 校准不过 ⇒ 本脚本的分层判法与 §90.4 不是同一套，本轮不发数")
        sys.exit(2)
    print("  ⇒ 完全一致 ✔ （分层判法已通过已知答案校准）")

    print(f"\n[结论]")
    print(f"  {n} 条在册欠账里，**{len(buckets['A'])} 条（{len(buckets['A'])/n*100:.1f}%）"
          f"的字段名在整个前端源码里一次都没出现**。")
    print(f"  ⚠ 这**不等于**「它们没上屏」—— 动态 key 拼接、整块 JSON.stringify 等")
    print(f"    路径都没穷举（修订 94 只查到其中一条、影响 {len(dumped)} 条）。")
    print(f"  ⇒ 能支撑的结论只有：**这批欠账里占 {len(buckets['A'])/n*100:.1f}% 的那部分，")
    print(f"    连「名字被人引用过」都没有**，不是简单的按产物作用域误判。")

    print(f"\n[A 层 Top 10 产物分布]")
    import collections
    c = collections.Counter(Path(e["artifact"]).name for e, _ in buckets["A"])
    for nm, k in c.most_common(10):
        print(f"   {nm:<34}{k:>4}")


if __name__ == "__main__":
    main()