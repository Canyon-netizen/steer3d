"""从 `r136_spec.json` 的 d4 臂**转换**出修正版，落到 `r138_spec.json`。

为什么不手抄：修订 136 那次跑错文件（改 `S.dv` 而 `renderPathPanel` 读 `S.path`），
错因就是把「我以为页面读哪一份」当成了事实。手抄一份新的 mutate，
等于把这个隐患原样带过来。⇒ **转换必须可核对**，所以下面把改前改后都打出来。

⚠ 这一臂要破的是 D4：`prod.problems[sw.after].k === String(sw.k)`
  （`verify_path.mjs:206-208`）。⚠⚠⚴ `prod` 是**独立从磁盘 JSON 读的**
  （`:150-151`），**不共用页面那份** ⇒ 改页面侧 `S.path` 正是它该抓的裂缝。
"""

import difflib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / ".cache/mutbak/r136_spec.json"
OUT = ROOT / ".cache/mutbak/r138_spec.json"

OLD = "S.dv"
NEW = "S.path"
# ⚠⚠⚴ 第一版这里写「期望 2 次」，脚本当场 exit 2 —— 因为实际是 **4 次**：
#   代码里 3 处（`&&S.dv&&` / `S.dv.problems` / `?S.dv.problems:`），
#   **note 字符串里还有 1 处**。少算的那处正是 note —— 而 note 恰恰是人读的。
#   ⇒ 期望值必须是「数出来的」，不是「想当然的」；数错就 exit 2，不许将就。
EXPECTED = 4


def show_occurrences(text, needle):
    print(f"=== mutate 里 {needle!r} 的每一处上下文（{text.count(needle)} 处）===")
    i = 0
    while True:
        p = text.find(needle, i)
        if p < 0:
            break
        print(f"  …{text[max(0, p - 26):p + 34]}…")
        i = p + 1


def main():
    spec = json.loads(SRC.read_text(encoding="utf-8"))
    d4 = next(a for a in spec["arms"] if a["name"] == "d4")
    before = d4["mutate"]

    # ⚠ 只允许改「读哪一份状态」这一处：出现次数必须精确对上，
    #   否则就是我以为我改了这一处、其实还改了别的。
    n_before = before.count(OLD)
    show_occurrences(before, OLD)
    if n_before != EXPECTED:
        print(f"[错误] mutate 里 {OLD} 出现 {n_before} 次，期望 {EXPECTED} —— 不改了，不猜")
        raise SystemExit(2)
    after = before.replace(OLD, NEW)
    if OLD in after or "S.dv" in after:
        print("[错误] 替换后仍有 S.dv")
        raise SystemExit(2)

    print("=== d4 臂 mutate 的改前/改后（逐行 diff）===")
    for line in difflib.unified_diff(
            before.split("`"), after.split("`"),
            fromfile="r136（改错文件）", tofile="r138（改对文件）", lineterm="", n=0):
        print(line)

    arm = dict(d4)
    arm["mutate"] = after
    arm["note"] = ("⚠ 修订 136 的 d4 臂改的是 S.dv —— renderPathPanel 不读那份，"
                   "所以扰动无效、判据照绿；本臂改 S.path（它真正读的那份）")

    out = dict(spec)
    out["outdir"] = ".cache/mutbak/r138_arms/"
    out["arms"] = [arm]
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n已写出 {OUT.relative_to(ROOT)}")
    print(f"  outdir {out['outdir']}")
    print(f"  at     {arm['at']}  anchor {arm['anchor'][:40]}…")
    print(f"  判据   {arm['criterion']}")


if __name__ == "__main__":
    main()