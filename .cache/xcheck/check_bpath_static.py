"""B 路构建器的**静态守卫**（修订 62 T3/T4，判据见预登记 §62.4）。

## 它替掉什么

`test_bpath_verdict.py:149` 对 `here` 的判据是：

```python
re.search(r"\d", here)
```

⚠⚠ 那是**近乎恒真**的：`here` 里出现**任何一个数字**就算过 ——
哪怕那个数字与该格要说的量毫无关系。
⇒ 「弱到近乎恒真的判据等于没有判据」（§4）。
本守卫把「带具体数字」收紧成「**每个数字都能报出出处**」。

同时执行 T3：本生成器**不许有裸 `assert`**
（`python -O` 会把它们全关掉，而它**正是**产出 `selfcheck_passed` 的那个）。

## ⚠⚠ 本守卫自己报出的两个「本项无判据」位

1. **T3 只数 `ast.Assert` 节点**，不判条件对错
   —— 它拦的是「判据被优化关掉」，不是「判据写错了」。
2. **T4a 对小整数几乎没有牙齿**（见 `report()` 里 `weak` 的输出）：
   本产物有 276 个数值，`here` 里的 `0/1/3/5` 几乎必然能撞上某个。
   ⇒ 真正承重的是**连续量**（`0.18424` / `53.96` / `239.99` / `144.86`）。
   ⚠ 这个事实**必须每次都报出来**，不许因为「全过」就当它有牙齿。

## 用法

    PYTHONPATH=.cache/pylibs python3 .cache/xcheck/check_bpath_static.py
    PYTHONPATH=.cache/pylibs python3 .cache/xcheck/check_bpath_static.py --self-test
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
from pathlib import Path

HERE = Path(os.path.dirname(os.path.abspath(__file__)))
ROOT = HERE.parent.parent
BUILDER = ROOT / ".cache/bpath/build_bpath_evidence.py"
ARTIFACT = ROOT / "frontend/public/latent/data/bpath_marker_steering.json"

# ⚠⚠ 不许把标识符里的数字当成「该格报出的数」：
#   `P9` 的 9、`Q3` 的 3、`L6` 的 6 全是**名字的一部分**，不是量。
#   代理指标（"有数字就算"）正是 §62 要拆掉的那条。
# ⚠⚠⚠ 修订 63 补 `(?<![A-Za-z]-)`：**带连字符的标识符**也算名字 ——
#   `R-6` 的 6 若被计入，`not_answerable` 里那句「R-6 的 P6」就会一直判红，
#   而它是**正当引用**（预登记里的臂编号/条目号），不是测量量。
#   ⚠ 这个边界放宽过判据，所以要**连着看 T4b 报告的 `n_seen`**：
#   若哪天有人把真正的测量量写成 `X-1` 的形式，会被这个规则放过。
TOK = re.compile(r"(?<![0-9A-Za-z_.])(?<![A-Za-z]-)(-?\d+(?:\.\d+)?)(?![0-9A-Za-z_.])")

# ⚠ 阈值不是拍脑袋的：连续量与整数要分开报，
#   否则「11/11 全过」会掩盖「只有 4 个真的承重」。
SMALL_INT_ABS = 1000.0


def _nums(o, acc):
    if isinstance(o, dict):
        for v in o.values():
            _nums(v, acc)
    elif isinstance(o, list):
        for v in o:
            _nums(v, acc)
    elif isinstance(o, (int, float)) and not isinstance(o, bool):
        acc.add(float(o))
    return acc


def check_t3(builder=None):
    """T3：裸 `assert` 数量必须为 0。"""
    builder = builder or BUILDER
    if not builder.exists():
        return {"name": "T3 裸 assert", "ok": False, "n": None,
                "detail": "构建器不在 %s ⇒ 本项无判据" % builder}
    src = builder.read_text(encoding="utf-8")
    tree = ast.parse(src)
    hits = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Assert)]
    # ⚠ 把 `raise SystemExit` 也数出来，好让人看见「判据搬去哪了」——
    #   否则「0 个 assert」既可能是搬走了，也可能是**判据被删干净了**。
    n_gate = len([n for n in ast.walk(tree)
                  if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Name) and n.func.id == "_gate"])
    return {"name": "T3 裸 assert", "ok": len(hits) == 0,
            "n": len(hits), "lines": hits, "n_explicit_gate": n_gate,
            "detail": ("裸 assert %d 处（要求 0）；显式 `_gate()` 门 %d 处"
                       % (len(hits), n_gate))}


def check_t4(path):
    """T4a：`here` 里每个计入的数字都必须等于产物中某个数值的四舍五入。"""
    if not path.exists():
        return {"name": "T4 here 数字可溯源", "ok": False, "n": None,
                "detail": "产物不在 %s ⇒ 本项无判据" % path,
                "n_tok": None, "weak": None}
    j = json.loads(path.read_text(encoding="utf-8"))
    vals = _nums(j, set())
    rows = j.get("ladder_mapping") or []
    if not rows:
        return {"name": "T4 here 数字可溯源", "ok": False, "n": None,
                "detail": "产物里没有 ladder_mapping ⇒ 本项无判据",
                "n_tok": None, "weak": None}

    bad, n_tok, weak = [], 0, 0
    for r in rows:
        here = r.get("here", "")
        for m in TOK.finditer(here):
            t = m.group(1)
            n_tok += 1
            f = float(t)
            dec = len(t.split(".")[1]) if "." in t else 0
            ok = any(abs(round(v, dec) - f) < 1e-12 for v in vals)
            if not ok:
                bad.append((r.get("level"), t))
            elif abs(f) < SMALL_INT_ABS and dec == 0:
                weak += 1
    return {"name": "T4 here 数字可溯源", "ok": not bad,
            "n": n_tok, "bad": bad, "n_tok": n_tok,
            "weak": weak,
            "detail": ("计入 %d 个数字，查不到出处 %d 个；"
                       "⚠ 其中 %d 个是小整数（在 %d 个产物数值里几乎必然撞上，"
                       "**近乎无判据**）⇒ 真正承重的是 %d 个连续量"
                       % (n_tok, len(bad), weak, len(vals), n_tok - weak))}


def _str_parts(node, seen=None):
    """取出 `node` 底下**所有**字符串字面量片段（递归）。

    ⚠⚠⚠ 这一段是被第三条阳性对照逼出来的：
      第一版只认 `JoinedStr` 与 `Constant` 两种形态，
      而 `answerable` / `not_answerable` 的值是 **List**
      ⇒ 两个分支都不进，`parts` 恒为空
      ⇒ 守卫报「扫描 3 个散文块字段，手打数字 **0** 个（要求 0）」并 **PASS**。
    ⚠⚠ 那是**恒真**：它一个字都没看，却长得像一条真判据。
      ⇒ 「全过」又一次被证明只说明「没抓到现行」。
      ⇒ 守卫现在必须报**扫了多少个字符串片段**（`n_parts`），
        `n_parts == 0` 与 `n_seen == 0` 一样直接判红。
    """
    seen = set() if seen is None else seen
    out = []
    if id(node) in seen:
        return out
    seen.add(id(node))
    if isinstance(node, ast.JoinedStr):
        # ⚠⚠ **不下钻 FormattedValue**：插值里的 `'n_pass'`、`'w·ĥ>0'`
        #   是**字段名/比较串**，不是散文。第一版递归下去，
        #   T4b 的阳性对照就从「数到 1」变成「数到 2」。
        #   ⇒ f-string 只取它自己的 Constant 片段。
        return [x.value for x in node.values
                if isinstance(x, ast.Constant) and isinstance(x.value, str)]
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    for child in ast.iter_child_nodes(node):
        out.extend(_str_parts(child, seen))
    return out


def check_t4b(builder=None, fields=("here",), label=None):
    """T4b / U1：指定字段里**不许有手打的数字字面量**。

    ⚠⚠ 为什么 T4a 不够：T4a 只能验「产物里能不能找到这个数」。
      而字段里手打的数**恰好**能被产物里的别的数撞上
      （实测：L6 的「5/5」被放过了，因为 "5" 在产物别处也存在）
      ⇒ T4a 对整数层近乎无判据。
    ⇒ T4b 从**源头**拦：数字只能从插值 `{...}` 或**具名常量**来，
      不能是键字面量里的字符。

    ⚠ 作用域由 `fields` 决定，**不是**全文件：全文件有 113 处字符串常量带数字，
      其中绝大多数是正当引用（`§37.3`、`修订 42`）——
      对它们一刀切会把「不许写死数字」变成「不许写编号」。
      - 修订 62：`fields = ("here",)`
      - 修订 63（U1）：扩到 `answerable` / `not_answerable` / `the_one_line`
    """
    builder = builder or BUILDER
    label = label or ("/".join(fields))
    if not builder.exists():
        return {"name": "T4b %s 无手打数字" % label, "ok": False, "n": None,
                "detail": "构建器不在 %s ⇒ 本项无判据" % builder}
    tree = ast.parse(builder.read_text(encoding="utf-8"))
    bad, n_seen, n_parts = [], 0, 0
    for nd in ast.walk(tree):
        if not isinstance(nd, ast.Dict):
            continue
        for k, v in zip(nd.keys, nd.values):
            if not (isinstance(k, ast.Constant) and k.value in fields):
                continue
            n_seen += 1
            # ⚠ 必须**递归**取片段：字段值可能是 List（answerable 就是），
            #   只认 JoinedStr/Constant 会让这条判据恒真（见 `_str_parts`）。
            parts = _str_parts(v)
            n_parts += len(parts)
            for p in parts:
                for m in TOK.finditer(p):
                    bad.append((getattr(v, "lineno", 0), m.group(1)))
    if n_seen == 0:
        return {"name": "T4b %s 无手打数字" % label, "ok": False, "n": None,
                "detail": "构建器里 0 个 %s 字段 ⇒ 本项无判据" % label}
    # ⚠⚠ 扫到 0 个字符串片段 ⇒ 一个字都没看 ⇒ 与「0 个字段」同样是无判据，
    #   绝不能报 PASS（这正是本条判据自己的漏洞）。
    if n_parts == 0:
        return {"name": "T4b %s 无手打数字" % label, "ok": False, "n": None,
                "detail": ("扫到 %d 个字段但 **0 个字符串片段** ⇒ "
                           "本项无判据（不是「0 个手打数字」）" % n_seen)}
    return {"name": "T4b %s 无手打数字" % label, "ok": not bad,
            "n": len(bad), "lines": bad, "n_seen": n_seen, "n_parts": n_parts,
            "detail": ("扫描 %d 个 %s 字段 / %d 个字符串片段，"
                       "手打数字 %d 个（要求 0）"
                       % (n_seen, label, n_parts, len(bad)))}


def check_u2(builder=None, src=None):
    """U2：判据常量必须与**源产物**交叉核对（「只钉一个数字不够，还要钉出处」）。

    ⚠ 改的是构建器里的 `ORTH_MIN`，比的是 `extreme_pick_abs.json` 的 `orth_min`。
    ⇒ 两边漂了 ⇒ 判红，而不是让散文里的所有 `|w·ĥ|>0.1` 继续按旧阈值说。
    """
    builder = builder or BUILDER
    src = src or (ROOT / ".cache/mutbak/extreme_pick_abs.json")
    if not builder.exists() or not src.exists():
        return {"name": "U2 判据常量对源产物", "ok": False, "n": None,
                "detail": "构建器或源产物缺失（%s / %s）⇒ 本项无判据"
                          % (builder.exists(), src.exists())}
    # ⚠ 行尾可以有注释（`ORTH_MIN = 0.1   # 判据常量…`），
    #   所以不能锚 `$` —— 第一版用 `^...$` 结果报「找不到常量 ⇒ 本项无判据」，
    #   而常量明明在。判据自己报「无判据」比判红更需要当回事。
    m = re.search(r"^ORTH_MIN\s*=\s*([0-9.]+)", builder.read_text(encoding="utf-8"), re.M)
    if not m:
        return {"name": "U2 判据常量对源产物", "ok": False, "n": None,
                "detail": "构建器里找不到 ORTH_MIN 常量 ⇒ 本项无判据"}
    used = float(m.group(1))
    j = json.loads(src.read_text(encoding="utf-8"))
    orth, dec = j.get("orth_min"), j.get("decile")
    ok = orth is not None and dec is not None and float(orth) == used == float(dec)
    return {"name": "U2 判据常量对源产物", "ok": ok,
            "n": 1, "used": used, "orth_min": orth, "decile": dec,
            "detail": ("构建器 ORTH_MIN=%g vs 源产物 orth_min=%r / decile=%r"
                       % (used, orth, dec))}


def check_u3(path=None):
    """U3：L5 `here` 必须**分域陈述**。

    ⚠⚠ 这条判据是**弱代理**：它只查「注入域」与「预测域」两个标记词同时出现，
      查不出「分域了但分错域」。报出来是为了让弱点可见，不是假装它够用。
    ⚠ 它拦的正是修订 62 那个真实缺陷：当时那句只讲了注入域，
      读起来却是本项目级的断言。
    """
    path = path or ARTIFACT
    if not path.exists():
        return {"name": "U3 L5 分域陈述", "ok": False, "n": None,
                "detail": "产物不在 %s ⇒ 本项无判据" % path}
    j = json.loads(path.read_text(encoding="utf-8"))
    l5 = [r for r in (j.get("ladder_mapping") or []) if r.get("level") == "L5"]
    if not l5:
        return {"name": "U3 L5 分域陈述", "ok": False, "n": None,
                "detail": "产物里没有 L5 ⇒ 本项无判据"}
    here = l5[0].get("here", "")
    hit_inj, hit_pre = "注入" in here, "预测" in here
    ok = hit_inj and hit_pre
    return {"name": "U3 L5 分域陈述", "ok": ok, "n": 1,
            "detail": ("L5 here 注入域标记=%s、预测域标记=%s（要求同时为真）；"
                       "⚠ 本判据是**弱代理**，查不出「分域但分错域」"
                       % (hit_inj, hit_pre))}


def report(res):
    print("=== B 路静态守卫（修订 62 T3/T4 ｜ 修订 63 U1/U2/U3）===")
    allok = True
    for r in res:
        ok = r["ok"]
        allok = allok and ok
        print("  %s %s：%s" % ("PASS" if ok else "FAIL", r["name"], r["detail"]))
    print("  判决：%s" % ("✅" if allok else "❌"))
    return allok


def _self_test(tmp):
    """阳性对照：注入一个查不到出处的数字，两条判据都**必须**变红。

    ⚠⚠ 阳性对照自己写错等于没有对照，所以注入物是**机械构造**的
      （从产物里现有的数字里挑一个，再 ±1 造一个必然不存在的），
      不是手写「一个不可能的数字」。
    """
    j = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    vals = sorted(_nums(j, set()))
    # ⚠ 挑一个产物里没有的整数：用「最大整数 + 12345」，机械可复算
    biggest = max(v for v in vals if abs(v) < 1e15 and float(v).is_integer())
    bogus = int(biggest) + 12345
    rows = json.loads(json.dumps(j))
    rows["ladder_mapping"][0]["here"] += "（注入 %d）" % bogus
    tmp.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    r = check_t4(tmp)
    tmp.unlink()
    # ⚠⚠ 这里**必须按数值比，不能按字符串比**：
    #   第一次写成 `t == str(bogus)`，而 `bogus` 是 float 时
    #   `str()` 给出 "19541.0"、token 是 "19541" ⇒ 对照自己报 FAIL，
    #   **而判据其实正确地判红了**。
    #   ⚠ 这就是「阳性对照自己写错等于没有对照」的一次实例：
    #     对照的红有时是它自己坏了，不是被测物坏了。
    ok = (not r["ok"]) and any(float(t) == float(bogus)
                               for _, t in r.get("bad", []))
    print("  %s T4 阳性对照：注入 %s（产物最大整数 %s + 12345）⇒ 判红=%s"
          % ("PASS" if ok else "FAIL", bogus, int(biggest), not r["ok"]))

    # T3 的阳性对照：往构建器副本里塞一个裸 assert
    src = BUILDER.read_text(encoding="utf-8")
    lines = src.splitlines(True)
    lines.insert(0, "def _self_test_probe():\n    assert True\n")
    bak = tmp.with_suffix(".py")
    bak.write_text("".join(lines), encoding="utf-8")
    tree = ast.parse(bak.read_text(encoding="utf-8"))
    n = len([x for x in ast.walk(tree) if isinstance(x, ast.Assert)])
    bak.unlink()
    ok3 = n >= 1
    print("  %s T3 阳性对照：注入 1 个裸 assert ⇒ AST 数到 %d 个"
          % ("PASS" if ok3 else "FAIL", n))

    # T4b 的阳性对照：把一个手打数字塞进 here 字段
    bak = bak.with_name(bak.stem + "_b.py")
    bak.write_text(src, encoding="utf-8")
    t = ast.parse(bak.read_text(encoding="utf-8"))
    # ⚠⚠ 注入必须同时吃 plain str 与 f-string（JoinedStr）。
    #   第一版只写了 `v.value = …`，而第一个 `here` 是 f-string
    #   ⇒ 阳性对照自己抛 AttributeError。
    #   ⚠ **对照崩了不是「对照失败」，是「对照没跑」** —— 必须当失败记。
    injected = 0
    for nd in ast.walk(t):
        if injected:
            break
        if not isinstance(nd, ast.Dict):
            continue
        for k, v in zip(nd.keys, nd.values):
            if not (isinstance(k, ast.Constant) and k.value == "here"):
                continue
            if isinstance(v, ast.JoinedStr):
                for part in reversed(v.values):
                    if isinstance(part, ast.Constant):
                        part.value = part.value + "（手打 4242）"
                        injected = 1
                        break
            elif isinstance(v, ast.Constant):
                v.value = v.value + "（手打 4242）"
                injected = 1
            break
    ok4b_inj = (injected == 1)
    bak.write_text(ast.unparse(t), encoding="utf-8")
    r4b = check_t4b(bak)
    bak.unlink()
    ok4b = ok4b_inj and (not r4b["ok"]) and r4b["n"] == 1
    print("  %s T4b 阳性对照：注入 %d 个手打数字 ⇒ 数到 %s 个"
          % ("PASS" if ok4b else "FAIL", injected, r4b["n"]))

    # ---- 修订 63：U1（散文块）/ U2（常量对源产物）/ U3（L5 分域）----
    PROSE = ("answerable", "not_answerable", "the_one_line")

    def _inject_field(field):
        """往指定字段的字面片段里塞一个手打数字，返回是否注入成功。

        ⚠⚠ 第二版又坏了一次：只处理 `JoinedStr` 与 `Constant`，
          而 `answerable` 的值是 **List**（里面才是那些字符串）
          ⇒ 什么都没注入，对照报「数到 0 个」。
          ⚠ 对照报 0 与判据报红长得一样，必须靠 `ok_inj` 分开。
        ⇒ 递归找该值底下**第一个**字符串字面量，不猜容器类型。
        """
        t2 = ast.parse(src)
        holder = None
        for nd in ast.walk(t2):
            if not isinstance(nd, ast.Dict):
                continue
            for k, v in zip(nd.keys, nd.values):
                if isinstance(k, ast.Constant) and k.value == field:
                    holder = v
                    break
            if holder is not None:
                break
        if holder is None:
            return t2, 0
        for sub in ast.walk(holder):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                sub.value = sub.value + "（手打 777）"
                return t2, 1
        return t2, 0

    b2 = bak.with_name(bak.stem + "_u1.py")
    t2, got = _inject_field("answerable")
    ok_inj = (got == 1)
    b2.write_text(ast.unparse(t2), encoding="utf-8")
    r_u1 = check_t4b(b2, fields=PROSE, label="散文块")
    b2.unlink()
    ok_u1 = ok_inj and (not r_u1["ok"]) and r_u1["n"] == 1
    print("  %s U1 阳性对照：往 answerable 注入 1 个手打数字 ⇒ 数到 %s 个"
          % ("PASS" if ok_u1 else "FAIL", r_u1["n"]))

    # U2：把 ORTH_MIN 改成 0.2（源产物仍是 0.1）⇒ 必须判红
    b3 = bak.with_name(bak.stem + "_u2.py")
    b3.write_text(re.sub(r"^ORTH_MIN\s*=\s*[0-9.]+", "ORTH_MIN = 0.2", src,
                         count=1, flags=re.M), encoding="utf-8")
    r_u2 = check_u2(b3)
    b3.unlink()
    ok_u2 = (not r_u2["ok"])
    print("  %s U2 阳性对照：把 ORTH_MIN 改成 0.2（源产物 0.1）⇒ 判红=%s"
          % ("PASS" if ok_u2 else "FAIL", not r_u2["ok"]))

    # U3：把 L5 的 `here` 换成单域陈述（删掉「预测」二字）⇒ 必须判红
    b4 = tmp.with_name(tmp.stem + "_u3.json")
    j4 = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    for rr in j4["ladder_mapping"]:
        if rr["level"] == "L5":
            rr["here"] = rr["here"].replace("预测域", "另一处").replace("预测", "别处")
    b4.write_text(json.dumps(j4, ensure_ascii=False), encoding="utf-8")
    r_u3 = check_u3(b4)
    b4.unlink()
    ok_u3 = (not r_u3["ok"])
    print("  %s U3 阳性对照：把 L5 here 改成单域陈述 ⇒ 判红=%s"
          % ("PASS" if ok_u3 else "FAIL", not r_u3["ok"]))

    return ok and ok3 and ok4b and ok_u1 and ok_u2 and ok_u3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", default=str(ARTIFACT))
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        tmp = ROOT / ".cache/mutbak/_t4_selftest.json"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        return 0 if _self_test(tmp) else 1
    res = [check_t3(), check_t4(Path(a.artifact)),
           check_t4b(),
           check_t4b(fields=("answerable", "not_answerable", "the_one_line"),
                     label="散文块"),
           check_u2(), check_u3(Path(a.artifact))]
    return 0 if report(res) else 1


if __name__ == "__main__":
    raise SystemExit(main())
