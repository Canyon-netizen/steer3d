#!/usr/bin/env python3
"""修订 76 §76.2 的 S4 与修订 77 §77.1 的 S7：**路径指针必须指向已渲染的字段**。

⚠⚠ 触发：这两个缺陷指向同一处 `readability_static.caveat` 的末句
   ——「逐 id 明细在 `control_arm.per_id`」，而那个路径**从未被取值**。

判据分工（承预登记 §77.1 第 4 条，二者**分别列出，不许合并**）：
   - **S4** 判「同名字段两侧渲染不对称」（字段名按 §76.2 **字面**：
     `script` / `why` / `reason`）
   - **S7** 判「散文把读者指向一个没渲染的路径」

⚠⚠⚠ **S4 的字段名范围是一个真实的判据歧义，本脚本如实披露、不静默扩大**：
   §76.2 的判红条件字面写的是「携带**同名字段** `script` / `why` / `reason`」，
   而 §77.2 说 `control_arm.per_id`「同结构、同字段名 ⇒ S4 适用」。
   **`per_id` 不在那三个名字里。**
   ⇒ 判定**只按字面的三个字段名**（不改判据）；
     `per_id` 这条由 **S7** 抓（散文指针悬空，是 S7 的原文判红条件）。
   ⇒ 「扩到全部同名字段会多命中哪些」单列为**披露项**，**不参与 exit code**。
     扩判据是设计决定，须单独立修订并披露旧数字，不能在守卫里顺手做掉。

⚠ S7 只判「**指的那个东西在不在**」，**不判散文措辞**（§77.1 第 3 条）。

用法：python3 .cache/xcheck/check_path_pointer.py
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
PANEL = {
    "bpath_marker_steering.json": "frontend/components/BPathPanel.tsx",
    "heldout_readability.json": "frontend/components/HeldoutPanel.tsx",
    "evidence_ladder.json": "frontend/components/EvidenceLadderPanel.tsx",
}
DATA = ROOT / "frontend/public/latent/data"

# ⚠ §76.2 的**字面**字段名。不扩大 —— 扩判据要单独立修订。
S4_FIELDS = ("script", "why", "reason")

# ⚠ S7 的散文来源（§77.1 第 1 条列举）。
PROSE_KEYS = {"caveat", "note", "claim", "why", "reason"}

# ⚠ 反引号里「形如路径」的形状：至少两段，每段是标识符。
#   必须是标识符，否则 `26/26`、`+0.0317`、`4.487` 会混进来。
PATHLIKE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+$")

# ⚠ 披露项默认只展开前 N 条，但**总数照印**（样本列表不是装饰）。
SHOW_N = 12


def load_tiers():
    spec = importlib.util.spec_from_file_location(
        "tiers", HERE / "check_render_tiers.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def slash(p: str) -> str:
    """点号路径 → AST 仪器的斜杠路径。"""
    return "/".join(p.split("."))


class Art:
    """一个产物的三份索引，一次遍历建齐。"""

    def __init__(self, name: str, obj):
        self.name = name
        self.tree: set[str] = set()          # 产物里所有路径（含下标）
        # ⚠⚠ `families` 的键是「**容器元素携带的字段名**」，
        #   **不是**容器自己的名字。第一版把两者搞反了 ——
        #   于是 `families['script']` 永远是空，`script` 其实在
        #   `selfcheck_detail.suites[*]` 与 `selfcheck_unavailable[*]` 里，
        #   S4 全程跳过，却照样打印「无不对称」。
        #   **仪器盲区伪装成「没缺陷」** —— 比判红危险得多。
        self.families: dict[str, set[str]] = defaultdict(set)
        self.strings: list[tuple[str, str]] = []             # (路径, 字符串)
        self._rec(obj)

    def _rec(self, o, prefix: str = "") -> None:
        if isinstance(o, dict):
            for k, v in o.items():
                p = f"{prefix}.{k}" if prefix else k
                self.tree.add(p)
                # ⚠ dict 型容器：`Record<string, {...}>`（页面上也渲染成多行，
                #   与 list 等价，见 `readability_static.per_id`）。
                #   它的「元素」是**值**，所以字段名来自值而非键。
                if isinstance(v, dict) and v and all(isinstance(x, dict) for x in v.values()):
                    for x in v.values():
                        for f in x:
                            self.families[f].add(p)
                self._rec(v, p)
        elif isinstance(o, list):
            for i, v in enumerate(o):
                # ⚠ 容器路径记**剥掉下标**的形态（承 W8 的教训）
                for k in (v if isinstance(v, dict) else ()):
                    self.families[k].add(prefix)
                self._rec(v, f"{prefix}[{i}]")
        elif isinstance(o, str):
            self.tree.add(prefix)
            self.strings.append((prefix, o))


def main() -> int:
    print("=== 修订 76 S4（对称性）+ 修订 77 S7（路径指针）===\n")
    tiers = load_tiers()
    ast = tiers.run_instrument()["panels"]

    # 访问集合：产物 → AST 仪器的斜杠路径（去掉 `d/` 前缀）
    accessed: dict[str, set[str]] = {}
    for pname, blob in ast.items():
        art = next((k for k, v in PANEL.items()
                    if Path(v).name == pname), None)
        if art is None:
            continue
        s: set[str] = set()
        for _root, b in blob.items():
            for key in ("accesses", "loops"):
                for a in b[key]:
                    s.add(a[2:] if a.startswith("d/") else a)
        accessed[art] = s

    arts: dict[str, Art] = {}
    for art in PANEL:
        if art in accessed:
            arts[art] = Art(art, json.loads((DATA / art).read_text("utf-8")))

    red = 0

    # ================= S7 =================
    print("─" * 78)
    print("S7 散文里的路径指针必须指向已渲染的字段")
    print("─" * 78)
    s7_total = 0
    s7_bad: list[tuple[str, str, str, str]] = []
    for art, A in arts.items():
        acc = accessed[art]
        for spath, sval in A.strings:
            leaf = spath.rsplit(".", 1)[-1]
            if leaf not in PROSE_KEYS:
                continue
            root_path = re.sub(r"\[\d+\]$", "", spath.rsplit(".", 1)[0]) \
                if "." in spath else ""
            for code in re.findall(r"`([^`\n]+)`", sval):
                code = code.strip()
                if not PATHLIKE.match(code):
                    continue
                # ⚠ 判据自带的排除器（§77.1 第 1 条）：产物里解析不到 ⇒ 不判
                cands = ([f"{root_path}.{code}"] if root_path else []) + [code]
                cands = [c for c in cands if c in A.tree]
                if not cands:
                    continue
                s7_total += 1
                if any(slash(c) in acc for c in cands):
                    continue
                s7_bad.append((art, spath, code, " | ".join(cands)))
                red += 1

    print(f"S7a 扫到的散文路径指针（**在产物里能解析到路径**的）：{s7_total} 条")
    print(f"S7b 判红（指向的路径在 AST 访问集合里找不到）：{len(s7_bad)} 条")
    if s7_bad:
        print()
        for art, spath, code, cs in s7_bad:
            print(f"  ⚠ {art}")
            print(f"      散文所在：{spath}")
            print(f"      指针    ：{code}   →  折成斜杠：{cs}")
        print()
        print("  ⚠ 上面每一行都是**读者被指向了一个页面上不存在的东西**。")
        print("    S7 只判「指的那个东西在不在」，**不判散文措辞**（§77.1 第 3 条）。")
    else:
        print("  ✓ 无悬空指针。")

    # ================= S4 =================
    print()
    print("─" * 78)
    print("S4 同族字段的渲染必须对称")
    print("─" * 78)
    print(f"S4a 判红字段名（§76.2 **字面**，不扩大）：{' / '.join(S4_FIELDS)}")
    s4_paths = 0
    s4_bad: list[tuple[str, str, str]] = []
    for fld in S4_FIELDS:
        for art, A in arts.items():
            ps = sorted(A.families.get(fld, set()))
            if len(ps) < 2:
                continue
            s4_paths += len(ps)
            acc = accessed[art]
            hit = [p for p in ps if slash(p) in acc]
            miss = [p for p in ps if slash(p) not in acc]
            if hit and miss:
                for p in miss:
                    s4_bad.append((art, fld, p))
                    red += 1
                print(f"  ⚠ 判红 {art} 的 `{fld}`：")
                print(f"      已渲染：{', '.join(hit)}")
                print(f"      未渲染：{', '.join(miss)}")
    print(f"\nS4b 参与对称性判定的同名字段路径数：{s4_paths}")
    if not s4_bad:
        print("  ✓ 无不对称。")

    # ================= 披露项（不参与判定）=================
    print()
    print("─" * 78)
    print("⚠ 披露项（**不参与 exit code**）：S4 字段名扩到「全部同名字段」会多命中")
    print("─" * 78)
    extra: list[str] = []
    n_extra = 0
    for art, A in arts.items():
        acc = accessed[art]
        for fld, ps in sorted(A.families.items()):
            if fld in S4_FIELDS or len(ps) < 2:
                continue
            ps = sorted(ps)
            hit = [p for p in ps if slash(p) in acc]
            miss = [p for p in ps if slash(p) not in acc]
            if hit and miss:
                n_extra += 1
                extra.append(f"{art} / `{fld}`：已渲染 {len(hit)} 条"
                             f"（{', '.join(hit)}）／未渲染 {len(miss)} 条"
                             f"（{', '.join(miss)}）")
    if extra:
        for line in extra[:SHOW_N]:
            print(f"  · {line}")
        if n_extra > SHOW_N:
            print(f"  ⚠ 另有 {n_extra - SHOW_N} 条同型，未展开（共 {n_extra} 条）。")
        print()
        print(f"  ⚠⚠ 上面这 {n_extra} 条**当前不由 S4 判红**"
              "（字段名不在 §76.2 字面三个名字里）。")
        print("    扩判据是**设计决定**，须单独立修订并披露旧数字 —— 本守卫不做。")
        print("    ⚠ 同名字段**不足以**判红：§76.2 第 3 条要求两侧是"
              "「**同一个事实**的同名字段」，")
        print("      语义不同的必须先查清语义再判，**不许机械补齐**"
              " ⇒ 这份清单是**待核实的候选**，不是缺陷清单。")
        print("    ⚠ `control_arm.per_id` 由 **S7** 抓（散文指针悬空），不靠 S4。")
    else:
        print("  （无）")

    print()
    print("=" * 78)
    if red:
        print(f"❌ 判红 {red} 处：S7={len(s7_bad)}  S4={len(s4_bad)}")
        return 1
    print("✅ 全绿：S7=0 悬空指针，S4=0 不对称")
    print("⚠ 全绿只说明「没抓到现行」，不代表判据覆盖了所有形态。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
