#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 88 守卫的扰动测试（证明它有牙齿，而不是恒绿）。

铁律：全过只说明没抓到现行 ⇒ 新判据上线前必须扰动。
⚠ 每条臂都必须**断言判红理由**（want_sub），不能只断言 exit code ——
  「崩了」也是非零，那不是判红。

六条臂：
  A1 标签漂移（meta→ 伪造）：某 unclassified 改成 meta ⇒ 必红
  A2 标签漂移（反向）：某 data-key 改成 unclassified ⇒ 必红
  A3 规则漂移（正则）：本守卫 DATA_KEY 换成几乎不匹配的 ⇒ 必红
  A4 规则漂移（meta 集合）：本守卫 META_NAMES 少一个成员 ⇒ 必红
  A5 重复键：台账插一条重复 artifact|field ⇒ 必红
  A6 负对照：全部改成 unclassified ⇒ ⚠ 期望**仍绿**
     （一致性确实没破；这条用来确认 A3/A4 抓的是「真失配」
       而不是「兜底变多就判红」）

⚠ 台账与守卫脚本在每条臂前后都必须还原 ⇒ try/finally + 先备份字节。
⚠ A3/A4 改的是**守卫脚本本身**，所以要改副本跑，不动工作区那份。
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

# ⚠⚠ v1 用 `Path(__file__).parent` 当守卫目录 —— 但本脚本住在 `.cache/mutbak`，
#   而守卫在 `.cache/xcheck` ⇒ 路径指错，FileNotFoundError。
#   ⇒ 固化：**扰动台不在守卫目录里**（它自己要改动副本），
#     所以两个目录必须各自显式写出来，别靠 __file__ 推。
HERE = Path("/Users/zhourui/code/steer3d/.cache/xcheck")   # 守卫与台账所在
WORK_ROOT = Path("/Users/zhourui/code/steer3d/.cache/mutbak/r88_mut")  # 副本工作区
GUARD_SRC = HERE / "check_debt_category_consistent.py"
DEBT = HERE / "check_render_coverage_sitewide.debt.json"
WORK = WORK_ROOT
PY = sys.executable

ENV = {"PYTHONPATH": ".cache/pylibs",
       "PYTHONPYCACHEPREFIX": ".cache/mutbak/pyc",
       "PATH": "/usr/bin:/bin"}


def run_guard(path: Path) -> tuple:
    p = subprocess.run([PY, str(path)], capture_output=True, text=True,
                       env=ENV, cwd=str(Path.cwd()))
    return p.returncode, p.stdout + p.stderr


def setup() -> Path:
    WORK.mkdir(parents=True, exist_ok=True)
    g = WORK / "guard.py"
    d = WORK / "debt.json"
    shutil.copy2(GUARD_SRC, g)
    shutil.copy2(DEBT, d)
    # ⚠ 守卫用 __file__.parent 找台账 ⇒ 副本必须同名
    (WORK / "check_render_coverage_sitewide.debt.json").unlink(missing_ok=True)
    shutil.copy2(DEBT, WORK / "check_render_coverage_sitewide.debt.json")
    # ⚠ 守卫还要读源脚本抄口径 ⇒ 源脚本必须也在同目录
    shutil.copy2(HERE / "check_render_coverage_sitewide.py", WORK)
    return g


def load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def save(p: Path, d: dict) -> None:
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def pick(d: dict, cat: str):
    """⚠⚠ v1 的调用方传进来的是 **Path**（台账文件路径），我在这里当 dict 用了
    ⇒ TypeError: 'PosixPath' object is not subscriptable。
    ⇒ 固化：**类型边界只在一个函数里跨**（load/save），其余一律传 dict。
    """
    for e in d["debt"]:
        if e.get("category") == cat and not str(e.get("artifact", "")).startswith("z5::"):
            return e
    raise SystemExit(f"⚠ 台账里没有 category=={cat!r} 的非 z5 条目 —— 臂的前提不成立")


def mutate_debt(dpath: Path, fn):
    """所有改台账的臂都走这里：load → 改 → save。"""
    d = load(dpath)
    fn(d)
    save(dpath, d)


ARMS = []


def arm(name, why):
    def deco(fn):
        ARMS.append((name, fn, why))
        return fn
    return deco


@arm("A1 标签漂移→meta", "把某 unclassified 条目的 category 改成 meta")
def a1(g, dpath):
    def f(d):
        pick(d, "unclassified")["category"] = "meta"
    mutate_debt(dpath, f)
    return 1, "n_mismatch（标签≠现算，仅判定范围内）= 1"


@arm("A2 标签漂移→unclassified", "把某 data-key 条目的 category 改成 unclassified")
def a2(g, dpath):
    def f(d):
        pick(d, "data-key")["category"] = "unclassified"
    mutate_debt(dpath, f)
    return 1, "n_mismatch（标签≠现算，仅判定范围内）= 1"


@arm("A3 规则漂移→DATA_KEY 失配",
     "本守卫的正则换成几乎不匹配的 ⇒ ⚠ 期望 exit=2 而**不是 1**："
     "规则侧漂移必然先触发自证闸门（对照没过 ⇒ 中止），那才是正确行为")
def a3(g, dpath):
    s = g.read_text(encoding="utf-8")
    s2 = re.sub(r'^DATA_KEY = re\.compile\(.*\)$',
                'DATA_KEY = re.compile(r"^(?!x)x$")', s, count=1, flags=re.M)
    assert s2 != s, "A3 没改成 —— 正则那行没匹配上，先读真实内容"
    g.write_text(s2, encoding="utf-8")
    return 2, "对照没过"


@arm("A4 规则漂移→META_NAMES 少一员",
     "本守卫的 META_NAMES 删掉 schema ⇒ ⚠ 期望 exit=2（自证闸门先拦）")
def a4(g, dpath):
    s = g.read_text(encoding="utf-8")
    s2 = s.replace('META_NAMES = {"schema", "design"', 'META_NAMES = {"design"', 1)
    assert s2 != s, "A4 没改成 —— 先读 META_NAMES 那几行的真实内容"
    g.write_text(s2, encoding="utf-8")
    return 2, "对照没过"


@arm("A5 重复键", "往台账插一条与现有键相同的条目")
def a5(g, dpath):
    def f(d):
        d["debt"].append(dict(pick(d, "unclassified")))
    mutate_debt(dpath, f)
    return 1, "重复键"


@arm("A6 负对照·只改范围外的 z5 条目",
     "把 12 条 z5 条目的 category 全改成乱七八糟 ⇒ 它们**不在判定范围内** ⇒ 期望仍绿。"
     "⚠ v1 这条负对照是「全改 unclassified」，期望仍绿 —— **错了**："
     "台账里有 41 条 data-key + 18 条 meta，全改会真产生 59 条失配，"
     "守卫判红是对的、我的期望是错的 ⇒ 这正是「期望填错伪装成判据没分辨力」的同族")
def a6(g, dpath):
    def f(d):
        for e in d["debt"]:
            if str(e.get("artifact", "")).startswith("z5::"):
                e["category"] = "故意写错"
    mutate_debt(dpath, f)
    return 0, "判绿"


def main():
    # ⚠⚠ 每条臂都在**全新副本**上跑：setup() 重新复制 guard.py / 台账 / 源脚本，
    #   所以臂之间不会互相污染，也不会碰到工作区那份。
    g0 = setup()
    rc, out = run_guard(g0)
    base_ok = (rc == 0)
    print(f"基线（无扰动）exit={rc} {'✅' if base_ok else '⚠⚠ 基线就红 ⇒ 后面的臂无意义'}")
    if not base_ok:
        print(out[-800:])
        return 2

    print()
    n_ok = 0
    for name, fn, why in ARMS:
        g = setup()
        d = g.parent / "check_render_coverage_sitewide.debt.json"
        want_rc, want_sub = fn(g, d)
        rc, out = run_guard(g)
        ok = (rc == want_rc) and (want_sub in out)
        n_ok += ok
        print(f"  {'✅' if ok else '⚠⚠'} {name}")
        print(f"        {why}")
        print(f"        期望 exit={want_rc} 且输出含 {want_sub!r}　"
              f"实得 exit={rc}　命中={want_sub in out}")
        if not ok:
            print("        ---- 实际输出尾部 ----")
            print("        " + out[-600:].replace("\n", "\n        "))
    print(f"\n扰动 {n_ok}/{len(ARMS)} 通过")
    return 0 if n_ok == len(ARMS) else 1


if __name__ == "__main__":
    sys.exit(main())
