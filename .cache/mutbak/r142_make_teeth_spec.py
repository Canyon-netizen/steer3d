"""给 E2/E3/E4 造牙齿臂。

⚠⚠⚴ 为什么这个扰动能证明它们有牙齿
  E2/E3 断言的是「**缺数据时屏上必须明说缺什么**」。
  ⇒ 扰动就是让这个**恰好不成立**：`renderPathPanel` 在缺数据时**静默返回空**
  ——⚠⚠⁴ **这正是 E1 判据名里警告的失败形态**（「不能静默消失」）。
  ⚗⇒ 扰动打的是**判据断言的那个量**本身，不是「我扰动的那个东西」。

⚠⚠⁴ **E1 不许被连带打红**：`typeof renderPathPanel` 包完之后**仍然是 function**
  ⇒ E1 照绿。⚠⚠⁴ 这正好把修订 140 说的第四档**再演示一遍**：
  ⚠⚠⁴ **E1 量的是「函数在」，而本臂破坏的是「函数在的时候它说不说缺」——
  ⚗⚠⁴ 两者不是同一个量。**

⚠ occ 口径（修订 135 c4 / 136 d4 两次栽在这里，本轮不能再栽）：
  occ = 「**E2 断言的那个量**（屏上有没有那句『未载入』），当前是否为真」转 0/1。
  ⚠⚠⁴ **不是**「wrapper 装上没有」——⚠ 那是个恒真的量，量不出任何东西。

⚠⚠⚴⚠⁴ 生成台的拼法是 `await page.eval(` + mutate + `);`
  ⇒ **mutate 只该是页内那段模板字面量**。
  ⚗⚠⁴ 第一版把 `await page.eval(...)` 和结尾的 `);true` 一起包了进去
  ⇒ 反引号 5 个（应为 2），⚠ 是生成台闸门抓到的。
⚠⚠⁴⚠⁴ 另一个错：第一版写 `window.S` —— ⚠ **`S` 是顶层 `const`，只有裸名可达**，
⚗ `window.S` 恒为 `undefined`。⚠（修订 136 §136.2 记过同一族。）
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BT = chr(96)

# ⚠⚠⚴⚠⁴ 反引号纪律：整条 mutate 里**恰好 2 个**（首尾包裹模板字面量），内部一个都不能有。
MUTATE = (
    "`(()=>{"
    "const orig=renderPathPanel;"
    # occ 的量 = 「屏上有没有那句『未载入』」⇒ 正是 E2 断言的那个量
    "const probe=()=>{const save=S.path;S.path=null;"
    "const b=document.createElement('div');b.innerHTML=renderPathPanel();"
    "const t=b.innerText||b.textContent||'';S.path=save;"
    "return t.indexOf('未载入')>=0?1:0;};"
    "const before=probe();"
    # 扰动：缺数据时**静默返回空**
    "window.renderPathPanel=function(){"
    "const path=S.path;"
    "const pid=(S.pm&&S.pm.pairs&&S.pm.pairs[S.pi])?S.pm.pairs[S.pi].id:null;"
    "if(!path||!((path.problems||{})[pid]))return '';"
    "return orig.apply(this,arguments);};"
    "const after=probe();"
    "window.__r135={k:'e2e3',before:before,after:after,"
    "note:'包住 renderPathPanel：缺数据时静默返回空（正是 E1 名字里警告的形态）'};"
    "return true;})()`"
)

ARM = {
    "name": "e2e3",
    "at": 227,
    "before": 227,
    "anchor": "const missing = JSON.parse(await page.eval(`(() => {",
    "criterion": "E2/E3 缺数据时屏上明说缺什么（可见文案）",
    "mutate": MUTATE,
}


def main():
    spec = json.loads((ROOT / ".cache/mutbak/r138_spec.json").read_text(encoding="utf-8"))
    out = dict(spec)
    out["outdir"] = ".cache/mutbak/r142_arms/"
    out["arms"] = [ARM]
    (ROOT / ".cache/mutbak/r142_teeth_spec.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    n = MUTATE.count(BT)
    inner = MUTATE[1:-1]
    print("=== mutate 的反引号账 ===")
    print(f"  总数 {n}（必须 2）  内部 {inner.count(BT)}（必须 0）")

    src = (ROOT / ".cache/browser_verify/verify_path.mjs").read_text(encoding="utf-8")
    lines = src.split("\n")
    at_line = lines[ARM["at"] - 1]
    hit = ARM["anchor"] in at_line
    print(f"  落点第 {ARM['at']} 行：{at_line[:72]}")
    print(f"  ⚠⚠⁴ 锚点**行首**逐字命中：{hit}（⚠ indexOf 会命中注释里的同名文本）")

    # ⚠⚠⁴ 页内代码不许出现裸名 window.S —— S 是顶层 const，不挂 window
    bad = "window.S" in MUTATE
    print(f"  ⚠ 页内误用 window.S：{bad}")
    ok = n == 2 and inner.count(BT) == 0 and hit and not bad
    print("=== " + ("✅ 可生成" if ok else "❌ 有不过的项") + " ===")
    raise SystemExit(0 if ok else 2)


if __name__ == "__main__":
    main()