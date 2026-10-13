"""验 `r139_run_arms.py` 的对账闸门**有没有牙齿**。

⚠⚠⚴ 为什么必须单独验：这台打印的是「基线绿 · 分母一致 · 落地两半成立 ·
每臂只翻它声明的那一条」——⚠⚠⚴ **四句全是绿的**。
⚠⚠⚴ 而本项目已发生 8 次「仪器自己发绿」。⇒ 不逐条证明它会红，
⚠⚠⚴ 这四句绿话和没跑没区别。

⚠ 为什么用合成日志而不是真跑浏览器：
  真跑一次基线+臂要 ~2 分钟，而要验的是**闸门逻辑**，不是浏览器。
  ⇒ 直接喂合成日志调用 `check_baseline` / `check_arm`（毫秒级）。
  ⚠⚠⚴ **但「合成日志能过」不等于「真跑能过」** ⇒ 真跑那一次仍要单独留档
  （见 `r139_run/` 里本轮的 baseline.log 与两个臂的 log）。
"""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MOD = ROOT / ".cache/mutbak/r139_run_arms.py"

spec_ = importlib.util.spec_from_file_location("r139_run_arms", MOD)
M = importlib.util.module_from_spec(spec_)
spec_.loader.exec_module(M)


def A(**kw):
    """造一个「臂跑完」的解析结果。"""
    d = {"result": "FAIL", "ok": 35, "total": 36, "red": ["D4"], "skip": [],
         "landed": ("d4", {"before": 1, "after": 0}), "notlanded": None, "tail": ""}
    d.update(kw)
    return d


def BASE(**kw):
    d = {"result": "OK", "ok": 36, "total": 36, "red": [], "skip": [],
         "landed": None, "notlanded": None, "tail": ""}
    d.update(kw)
    return d


ARM = {"name": "d4", "criterion": "D4 prod.problems[sw.after].k === String(sw.k)"}

CASES = [
    # (标签, 基线, 臂, 期望「有问题的判据子串」——None = 期望零问题)
    ("全过（对照）", BASE(), A(), None),
    ("基线不是 OK", BASE(result="FAIL", ok=35), A(), "基线不是 OK"),
    ("基线有跳过", BASE(skip=["D3"]), A(), "基线就有 1 条跳过"),
    ("臂崩了（无 RESULT）", BASE(), A(result=None, ok=None), "无 RESULT 行"),
    ("落地未落地", BASE(), A(notlanded=("d4", {"before": 0, "after": 0}),
                             landed=None), "扰动未落地"),
    ("落地第一半不成立 before=0", BASE(),
     A(landed=("d4", {"before": 0, "after": 0})), "第一半不成立"),
    ("落地第二半不成立 after=1", BASE(),
     A(landed=("d4", {"before": 1, "after": 1})), "第二半不成立"),
    ("没有取证行", BASE(), A(landed=None), "没有落地取证行"),
    ("分母与基线不一致", BASE(total=36), A(total=35), "分母与基线不一致"),
    ("翻面两条（臂不纯）", BASE(), A(red=["D4", "D1"]), "翻面判据 2 条"),
    ("翻面 0 条（扰动无效）", BASE(), A(red=[]), "翻面判据 0 条"),
    ("翻面的是别人", BASE(), A(red=["C3"]), "翻面的是 C3，规格声明的是 D4"),
]


def main():
    fails = []
    for label, b, a, want in CASES:
        probs = M.check_baseline(b)
        _want, why = M.check_arm(ARM, a, b)
        probs = probs + why
        if want is None:
            ok = not probs
            got = probs or ["（无问题）"]
        else:
            ok = any(want in p for p in probs)
            got = probs or ["（零问题 —— 闸门漏了！）"]
        print(f"  {'✅' if ok else '❌'} {label:<26} 期望含「{want}」")
        for g in got:
            print(f"        · {g}")
        if not ok:
            fails.append(label)
    print()
    if fails:
        print(f"[错误] {len(fails)} 个用例没过：{fails}")
        sys.exit(2)
    print(f"=== 闸门有牙齿：{len(CASES)}/{len(CASES)} 个用例按预期 ===")


if __name__ == "__main__":
    main()