#!/usr/bin/env python3
"""修订 71 §71.1 的 W1–W5：散文断言的可核性。

⚠ 本守卫的定位：X4 把 `1928` / `0.0317` / `4.487` **同质**地登记为
  「无出处」。本轮查证发现三者病因不同（预登记 §71.0），判据据此拆成
  三种状态：derived / unreconstructable / dropped_from_prose。

⚠ 与 `check_bpath_static.py` 的 `KNOWN_NO_SOURCE` 的关系：
  **两张表必须互相核对**（W4b）。任一张少登记一个散文里的数 ⇒ 判红。
  理由：一张能悄悄变小的登记表，等于一个没人看的欠账清单。

⚠ 自曝弱点（先写在这里，免得以后有人当成更强的判据）：
  - ⚠⚠ **这一段是量出来的，不是想出来的**（修订 71.1）。
    第一版我写「W5a 抓不到本次缺陷，因为 0.031732 在产物里」——
    **错**：`0.031732` 在 `marker_freq5.json`，**不在**交付产物里。
    实测交付产物按 4 位精度命中 **0 次** ⇒ W5a 单独就能抓到它。
  - W1 只判「产物里有这条记录」，不判「这条记录支持那条断言」。
  - W5 的 `cross_artifact` 状态**不判散文措辞** ⇒ 「措辞点名的来源
    与数字真正的来源不是同一份产物」这类缺陷**逃出了判据**
    （`1.15` 就是一例，已在 REGISTRY 的 `known_defect` 里单独记在案）。

用法：python3 .cache/xcheck/check_prose_traceability.py
退出码 0 = 全过；非 0 = 有判红。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# ⚠⚠ **复用** `check_bpath_static` 的排除表与引用判定，不自己再造一套。
#   第一版的 NUM_LIT 把「修订 37」「§11.6」这类**编号**当成测量量，
#   一口气误报 12 条 —— 少报比多报危险，但**误报的判据更没价值**：
#   它会把真缺陷淹在一堆假警报里。
import check_bpath_static as CBS   # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "frontend/public/latent/data/bpath_marker_steering.json"
FREQ = ROOT / ".cache/bpath/results_B/marker_freq5.json"
SWEEP = ROOT / ".cache/bpath/results_B/layer_sweep_t1.json"
STATIC = ROOT / ".cache/xcheck/check_bpath_static.py"

# 散文字段（与预登记 §71.1 的枚举一致）
PROSE_KEY = re.compile(
    r"^(caveat|note|claim|reason|verdict_reason|why_.*|findings?|caveats?)$"
)

# 产物里的臂全名 -> 散文里可能出现的简称（用于 W1/W3）
# ⚠ 正则按**简称**列，不按全名自动生成：`old_w_t1(错层)` 里的 `[t]`、`()`
# 是正则元字符，自动生成会把「匹配不到」伪装成「判红」，那正是我踩过的坑。
MENTION = [
    ("old_w_t1(错层)", r"(?:old_w_)?w_t1"),
    ("old_w_real(错层)", r"(?:old_w_)?w_real"),
    ("A_L19_m1(H[t-1])", r"A_L19_m1|A_L19"),
    ("B_L19_m0(H[t])", r"B_L19_m0|B_L19"),
]

# ⚠ 散文里出现的数 -> 三种状态之一（预登记 §71.1 W4/W5）
REGISTRY = {
    "0.0317": {
        "status": "derived",
        # 本轮落地的路径：对照臂自己的算术均值，由 marker_freq5.json 现算
        "path": ["readability_static", "control_arm", "arith_mean"],
        "expr": "round(sum(rows['old_w_t1(错层)'].dots)/len(dots), 5)",
        "where": "readability_static.caveat",
    },
    "4.487": {
        "status": "unreconstructable",
        "where": "orthogonality 下 shape_contrast 的 caveat",
        # W4 要求的三样：输入列表 / 每个输入的重建值 / 次数
        "inputs": [
            ".cache/mutbak/orthogonality_nt8.json",
            ".cache/mutbak/orthogonality_hi.json",
            ".cache/mutbak/orthogonality_extreme.json",
            ".cache/mutbak/orthogonality.json",
        ],
        "values": [0.2269, 3.9167, 1.8750, 0.1517],
        "n_rebuilds": 4,
        "note": "两次独立重建互不相等（3.973 / 3.9167）⇒ 口径不唯一，"
                "不是「口径未知所以没重建」",
    },
    "1928": {
        "status": "dropped_from_prose",
        # W4c：状态是「已从散文撤下」的，必须**在散文里查不到**
        "must_absent_from": ["coordinates"],
    },
    "1.15": {
        "status": "cross_artifact",
        # 修订 71.1：引用的是**另一份产物**的读数，判定要**去那份产物里解析**
        "artifact": "frontend/public/latent/data/heldout_readability.json",
        "path": ["recipe", "specificity_margin"],
        "expr": "round(recipe.specificity_margin, 2)",
        "where": "ladder_mapping/[1]/note",
        # ⚠⚠ 散文写的是「**主阶梯那一块**」，而这个数住在 heldout_readability.json
        #   —— **措辞点名的来源与数字真正的来源不是同一份产物**。
        #   `cross_artifact` **不判措辞**（预登记 §71.1：判据一旦开始管文风，
        #   文风改动就会让判据变红），所以这一条**逃出了判据**，单独记在案。
        "known_defect": "措辞点名的来源与数字实际所在不是同一份产物",
    },
}

# 散文里必然存在、但属于「更正披露引用旧值」的（承 X5，按设计查不到出处）
# ⚠⚠ **必须带符号**。第一版不捕获 `-`，于是散文里的 `-0.01321`
#   被当成 `0.01321` 去找正的值 ⇒ 一律判「不在」。
#   而散文说 `-0.01321` 与说 `+0.01321` 是**两个不同的断言** ——
#   把符号丢掉，判据就在替我改写那句话。
NUM_LIT = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])")

CITED_OLD = set(CBS.KNOWN_NO_SOURCE) - {"1928", "0.0317", "4.487"}


def measurement_literals(txt: str):
    """散文里的**测量量**字面量（编号/日期按 CBS 的豁免表排除）。"""
    out = []
    for m in NUM_LIT.finditer(txt):
        # ⚠ 用整个 match 的 span，不是 group(1)：NUM_LIT 现在**没有捕获组**
        #   （带符号后整段就是数字），`m.start(1)` 会 IndexError。
        if CBS._cited(txt, m.start(), m.end()):
            continue
        out.append(m.group(0))
    return out

RED: list[str] = []
NOTES: list[str] = []
# ⚠ 崩溃与判红必须**在输出上可区分**：守卫自己崩了，它的判决就是不完整的，
#   而 exit code 两者都是 1 —— 只看退出码会把「没跑完」当成「跑完了，红」。
CRASHED: list[str] = []
# 阳性对照期间静音正式输出（见 positive_control 的注释）
QUIET = False


def say(*a):
    if not QUIET:
        print(*a)


class _Quiet:
    def __enter__(self):
        global QUIET
        self._old = QUIET
        QUIET = True

    def __exit__(self, *exc):
        global QUIET
        QUIET = self._old
        return False


QUIET_CTX = _Quiet()


def stage(name, fn, *a):
    """跑一段判据；崩了记进 CRASHED，**不让它吞掉其余段的判决**。"""
    try:
        return fn(*a)
    except Exception as exc:                      # noqa: BLE001
        CRASHED.append(name)
        print(f"  ✗✗ {name} **自身崩了**：{type(exc).__name__}: {exc}")
        return None


def red(tag: str, msg: str) -> None:
    RED.append(f"[{tag}] {msg}")


def walk(obj, path=()):
    """产出 (路径, 标量值)。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk(v, path + (str(k),))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, path + (f"[{i}]",))
    else:
        yield path, obj


def prose_pairs(art):
    for path, val in walk(art):
        if path and PROSE_KEY.match(path[-1]) and isinstance(val, str):
            yield path, val


def ndigit(lit: str) -> int:
    body = lit.lstrip("-+")            # ⚠ 带符号后，位数必须先剥掉符号
    return len(body.split(".")[1]) if "." in body else 0


def present(art, lit: str) -> bool:
    """产物里是否存在一条记录，其值（或键的文本）在字面精度上等于 `lit`。

    ⚠⚠ 第一版只扫**值**，且只认数值型 ⇒ token id 这类**以键出现**的数
      （`per_id` 的 key 是 `str(id)`，`neg_ids[].id` 是字符串）一律判「不在」。
      ⚠ 那不是产物缺记录，是**扫描器看不见以键/字符串形式存在的记录** ——
      假警报会把真缺陷淹掉。
    """
    tgt = float(lit)
    nd = ndigit(lit)
    for p, v in walk(art):
        for cand in (v, p[-1] if p else None):   # 值 **和** 键的文本
            if isinstance(cand, bool):
                continue
            if isinstance(cand, (int, float)) and round(float(cand), nd) == tgt:
                return True
            if isinstance(cand, str) and cand.strip() == lit:
                return True
    return False


def load_known_no_source() -> set[str]:
    return set(CBS.KNOWN_NO_SOURCE)


# ---------------------------------------------------------------- W2 先跑
def w2():
    """同量双路必须相等。这是 W1 的阳性对照，也是「别拿另一个量顶」的护栏。"""
    F = json.loads(FREQ.read_text(encoding="utf-8"))
    S = json.loads(SWEEP.read_text(encoding="utf-8"))
    arm = "old_w_t1(错层)"
    dots = F["rows"][arm]["dots"]
    lhs = sum(dots.values()) / len(dots)
    rhs = S["pred_w_dot_Weff_marker"]
    diff = abs(lhs - rhs)
    print(f"  LHS 现算 arith_mean({arm}) = {lhs!r}  (n_ids={len(dots)})")
    print(f"  RHS layer_sweep_t1.pred_w_dot_Weff_marker = {rhs!r}")
    print(f"  diff = {diff:.3e}   判据：< 1e-6")
    if diff >= 1e-6:
        red("W2", f"两条独立路径差 {diff:.3e} ≥ 1e-6 ⇒ 它们**不是同一个量**，"
                  f"拿其中一个去顶散文里的数会是错的")
    return lhs, rhs


# ---------------------------------------------------------------- W1 / W3
def w1_w3(art, current_arm: str):
    for path, txt in prose_pairs(art):
        where = "/".join(path)
        for full, pat in MENTION:
            if not re.search(pat, txt):
                continue
            if full == current_arm:
                continue  # 当前臂本来就该在产物里
            # —— W1：产物侧 ——
            hit = False
            for p, v in walk(art):
                joined = "/".join(p)
                if full in joined or (isinstance(v, str) and full in v):
                    hit = True
                    break
            if not hit:
                red("W1", f"{where} 提到 `{full}` 语境里的数值断言，"
                          f"但产物里搜不到 `{full}` 的任何字段名或字符串值")
            # —— W3：散文侧 ——
            if full not in txt:
                red("W3", f"{where} 提到非当前臂，但散文里没有逐字 key `{full}` "
                          f"⇒ 限定词（如「错层」）被丢掉，读者会当成同层对照")


# ---------------------------------------------------------------- W5a / W5b
def w5a(art):
    found = []
    for path, txt in prose_pairs(art):
        for lit in measurement_literals(txt):
            if lit in CITED_OLD:
                continue
            # ⚠ 修订 71.1：`cross_artifact` 的数由 **W5b** 去它自己那份产物里判。
            #   在这里再判一次「本产物里有没有」是**重复且错的** ——
            #   本产物里没有正是 cross_artifact 的定义。
            if REGISTRY.get(lit, {}).get("status") == "cross_artifact":
                continue
            found.append((path, txt, lit))
    miss = [(p, t, l) for p, t, l in found if not present(art, l)]
    print(f"  散文里的数值字面量 {len(found)} 个（已剔除「更正披露引用旧值」"
          f"与移交 W5b 的 cross_artifact）；在本产物里按字面精度对不上的 "
          f"{len(miss)} 个")
    for p, t, l in miss:
        red("W5a", f"{'/'.join(p)} 里的 `{l}` 在产物里找不到任何按该精度对得上的值")
    return found, miss


def _resolve(doc, path):
    cur = doc
    for seg in path:
        if isinstance(cur, list) and seg.startswith("[") and seg.endswith("]"):
            i = int(seg[1:-1])
            if not (0 <= i < len(cur)):
                return None, False
            cur = cur[i]
        elif isinstance(cur, dict) and seg in cur:
            cur = cur[seg]
        else:
            return None, False
    return cur, True


def w5b(art, lhs, rhs):
    for num, rec in REGISTRY.items():
        st = rec["status"]
        if st == "cross_artifact":
            # ⚠ 判定必须在**它真正所在的那份产物**里做，
            #   否则「跨产物引用」会退化成「随便哪个产物里有就算过」
            tgt_path = ROOT / rec["artifact"]
            if not tgt_path.exists():
                red("W5b", f"`{num}` 声明引用 {rec['artifact']}，但该文件不存在")
                continue
            doc = json.loads(tgt_path.read_text(encoding="utf-8"))
            label = rec["artifact"] + ":" + "/".join(rec["path"])
        elif st == "derived":
            doc = art
            label = "/".join(rec["path"])
        else:
            continue

        cur, ok = _resolve(doc, rec["path"])
        if not ok:
            red("W5b", f"`{num}` 登记为 {st}，路径 {label} "
                        f"**解析不出来** ⇒ 它仍然是无出处的")
            continue
        nd = ndigit(num)
        if round(float(cur), nd) != float(num):
            red("W5b", f"`{num}` 登记为 {st}，但 {label} 的值是 {cur!r}，对不上")
        else:
            extra = (f"　⚠已知逃逸：{rec['known_defect']}"
                     if rec.get("known_defect") else "")
            say(f"  ✓ {num} ← {label} = {cur!r}  （{rec['expr']}）{extra}")


# ---------------------------------------------------------------- W4 / W4b / W4c
def w4():
    for num, rec in REGISTRY.items():
        st = rec["status"]
        if st == "unreconstructable":
            need = ("inputs", "values", "n_rebuilds")
            miss = [k for k in need if not rec.get(k)]
            if miss:
                red("W4", f"`{num}` 登记为 unreconstructable，但缺 {miss} "
                          f"⇒ 分不清「没试过」与「试过、口径不唯一」")
            elif len(rec["inputs"]) != len(rec["values"]) or \
                    rec["n_rebuilds"] != len(rec["inputs"]):
                red("W4", f"`{num}` 的重建记录不自洽：inputs={len(rec['inputs'])} "
                          f"values={len(rec['values'])} n={rec['n_rebuilds']}")


def w4b(art):
    """新旧两张登记表必须互相核对。

    ⚠⚠ 第一版写成「散文里的每个数都必须登记」，一口气要求登记 32 个
      （`0` `1` `2` `7196` …）—— 登记表根本不是**每个数**的清单，
      它只是「争议中的那几个数」的处置状态。
      ⇒ 那等于逼我把编号也登记一遍，把一张有意义的表变成一张没人看的表。
      ⇒ 改成**只核对争议项**：旧表里有、仍在散文里、而新表没登记的。
    """
    in_prose = {l for _, _, l in w5a_cache[0]}
    ghost = sorted((load_known_no_source() - set(REGISTRY)) & in_prose)
    if ghost:
        red("W4b", f"check_bpath_static.KNOWN_NO_SOURCE 里有 {ghost}，"
                   f"它仍出现在散文里，却没在本守卫登记 ⇒ 两张表不一致，"
                   f"等于有人从欠账清单里悄悄删掉了一项")
    else:
        print(f"  两表一致：旧表 {len(load_known_no_source())} 项 / "
              f"新表 {len(REGISTRY)} 项，无「只在旧表且仍在散文」的争议项")


def w4c(art):
    """状态 = dropped_from_prose 的，必须在散文里**查不到**。"""
    for num, rec in REGISTRY.items():
        if rec["status"] != "dropped_from_prose":
            continue
        for path, txt in prose_pairs(art):
            if num in txt:
                red("W4c", f"`{num}` 登记为已从散文撤下，"
                           f"但仍在 {'/'.join(path)} 里出现")


# ---------------------------------------------------------------- 阳性对照
def positive_control():
    """⚠ 对照必须**证明判据**，不是一个接近判据的东西。

    ⚠⚠ 对照会把红写进**同一个** RED 列表。第一版没截断，
      于是 3 条对照的红混进正式判决，输出里出现同一判红重复两遍 ——
      看着像「两条独立证据」，其实一条真、一条是我自己造的。
      ⇒ 每段对照前后各截一次 RED。
    """
    art = json.loads(ART.read_text(encoding="utf-8"))
    ok = {}

    def trial(name, fn):
        mark = len(RED)
        try:
            with QUIET_CTX:                  # ⚠ 对照不许打正式判决那一行，
                fn()                         #   否则输出里同一行出现两遍，
        except Exception as exc:              #   看着像「两条独立证据」
            ok[name] = False
            print(f"  ✗✗ 对照「{name}」**崩了**（不是未触发）："
                  f"{type(exc).__name__}: {exc}")
            del RED[mark:]
            return
        fired = len(RED) > mark
        ok[name] = fired
        del RED[mark:]

    # ⚠⚠⚠ 三条对照各自的写法都被前两版写错过：
    #   (a) 注入 `_probe` 键 ⇒ PROSE_KEY 不认它 ⇒ 注入没进扫描范围，
    #       对照是被**真实数据**带动的，不是被注入带动的；
    #   (b) 注入 `FAKE_ARM` ⇒ MENTION 表里没有它 ⇒ 判据**根本没被走到**，
    #       对照靠巧合通过。
    # ⇒ 对照必须让判据的**每一个条件同时成立**，且失败原因只能是判据红。

    # 对照 A（W1 侧）：散文用简称提到非当前臂，且产物里**没有**逐字 key
    badA = json.loads(json.dumps(art))
    badA["readability_static"]["note"] = "对照：w_t1 的读数 77.7"
    badA["readability_static"].pop("control_arm", None)   # 产物里逐字 key 被摘掉
    trial("W1 产物缺逐字 key + 散文提简称", lambda: w1_w3(badA, "B_L19_m0(H[t])"))

    # 对照 B（W3 侧）：产物里**有**逐字 key，但散文仍只用简称
    badB = json.loads(json.dumps(art))
    badB["readability_static"]["note"] = "对照：w_t1 的读数 77.7"
    trial("W3 产物有 key 但散文只写简称", lambda: w1_w3(badB, "B_L19_m0(H[t])"))

    # 对照 C：把 derived 的路径摘掉 → W5b 必红
    badC = json.loads(json.dumps(art))
    badC["readability_static"].pop("control_arm", None)
    trial("W5b 摘掉 derived 路径", lambda: w5b(badC, 0.0, 0.0))

    # 对照 D：把 1928 塞回**真实的 note 字段** → W4c 必红
    badD = json.loads(json.dumps(art))
    badD["coordinates"]["note"] += "；与倒数第二层差 1928"
    trial("W4c 把 dropped 的数塞回散文", lambda: w4c(badD))

    return ok


def main():
    print("=== 修订 71 W1–W5：散文断言的可核性 ===\n")
    art = json.loads(ART.read_text(encoding="utf-8"))
    current = art.get("arm")
    print(f"产物 {ART.relative_to(ROOT)}  当前臂 = {current!r}\n")

    global w5a_cache
    print("W2（同量双路 —— 阳性对照，先跑）")
    r2 = stage("W2", w2)
    lhs, rhs = (r2 if r2 else (0.0, 0.0))
    print()

    w5a_cache = stage("W5a", w5a, art) or ([], [])
    print()

    print("W5b（derived 必须有可解析的路径）")
    stage("W5b", w5b, art, lhs, rhs)
    print()

    print("W1 / W3（散文提到的臂，产物与散文各要写全）")
    stage("W1/W3", w1_w3, art, current)
    print()

    print("W4 / W4b / W4c（登记表三态 + 两表互核）")
    stage("W4", w4)
    stage("W4b", w4b, art)
    stage("W4c", w4c, art)
    print()

    print("阳性对照（对照崩了是「对照没跑」，不是「判据失败」）")
    try:
        ok = positive_control()
    except Exception as exc:                      # noqa: BLE001
        ok = {}
        print(f"  ✗✗ 阳性对照**自身崩了**：{type(exc).__name__}: {exc}")
        CRASHED.append("positive_control")
    for k, v in ok.items():
        print(f"  {'ok_inj' if v else '✗ 未触发'}  {k}")
    if not all(ok.values()):
        red("CTRL", "阳性对照未触发 ⇒ 本守卫的判据没有牙齿")

    print()
    if CRASHED:
        print(f"✗✗ 守卫自身在 {CRASHED} 处崩溃 —— **这是「没跑完」，"
              f"不是「判红」**。下面的判决不完整，不能当结论用。")
    if RED:
        print(f"✗ 判红 {len(RED)} 条：")
        for r in RED:
            print("   " + r)
    elif not CRASHED:
        print("✓ W1–W5 全过。⚠ 注意「全过」只说明「没抓到现行」，"
              "不代表散文断言**正确**。")
    return 1 if (RED or CRASHED) else 0


if __name__ == "__main__":
    sys.exit(main())