"""给 `r138_spec.json` 追加 a1b 臂：A1 换手法重验。

⚠ 为什么第一版 a1 臂失败（修订 137 §137.2）
  它的注入点在 `:88`，occ 读 `[data-pathblock]` 的 `data-pathstate`；
  而 `:86` 刚点完 `#tabPath`，**面板还没渲染** ⇒ 那一刻 occ 恒为 0
  ⇒ `[扰动未落地] before=0 after=0`。
  ⚠⚠⚴ 这撞的是「上游注入」纪律的**前提**：那个取值点在注入时必须**已经存在**。

⚠ a1b 换的手法：**注入块自己等元素出现，再扰动**
  `cdp_client.mjs:191` 的 `eval` 默认 `awaitPromise: true`
  ⇒ 注入块返回 Promise 会被 `page.eval` 等到。
  ⇒ 于是在同一个块里依次取到：元素出现（before=1）→ 改属性（after=0），
  **落地两半都在「那个量已经存在」的时刻测**，不是都在 0。

⚠⚠ occ 口径（修订 135 c4 / 136 d4 两次栽在这里）
  occ = 「**被判据断言的那个量**，当前是否为真」转 0/1。
  A1 断言的是 `state === 'ok'`（`:94`），所以 occ 就是
  `块存在 且 data-pathstate === 'ok'` —— 不是「块的个数」，不是「属性在不在」。
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / ".cache/mutbak/r138_spec.json"

# ⚠ 反引号纪律：整条 mutate 里**一个反引号都不能有**（它会被塞进模板字面量）。
#    这里用单引号；G4 闸门会数全文件反引号总数并要求恰好 = 源文件 + 2。
MUTATE = (
    "`(()=>{const occ=()=>{const b=document.querySelector('[data-pathblock]');"
    "return (b&&(b.getAttribute('data-pathstate')||'')==='ok')?1:0;};"
    "const done=(before,after)=>{window.__r135={k:'a1b',before:before,after:after,"
    "note:'等 [data-pathblock] 出现后把 data-pathstate 改成 BROKEN'};return true;};"
    "if(occ()){const b0=document.querySelector('[data-pathblock]');"
    "b0.setAttribute('data-pathstate','BROKEN');return done(1,occ());}"
    "return (async()=>{for(let w=0;w<80;w++){await new Promise(r=>setTimeout(r,250));"
    "if(occ())break;}"
    "const before=occ();const b=document.querySelector('[data-pathblock]');"
    "if(b)b.setAttribute('data-pathstate','BROKEN');return done(before,occ());})();})()`"
)

ARM = {
    "name": "a1b",
    "at": 88,
    "before": 88,
    "anchor": "for (let i = 0; i < 60; i++) {",
    "criterion": "A1 state === 'ok'（切到第 5 屏后 [data-pathblock] 的 data-pathstate）",
    "mutate": MUTATE,
}


def main():
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    names = [a["name"] for a in spec["arms"]]
    if "a1b" in names:
        print("[错误] a1b 已在规格里，不重复追加")
        raise SystemExit(2)
    assert "`" not in MUTATE[1:-1], "mutate 内部出现反引号"
    spec["arms"].append(ARM)
    SPEC.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已追加 a1b 到 {SPEC.relative_to(ROOT)}")
    print(f"  现有臂：{[a['name'] for a in spec['arms']]}")
    print(f"  mutate 里的反引号数（含首尾包裹）：{MUTATE.count('`')}")
    print(f"  anchor  {ARM['anchor']}")


if __name__ == "__main__":
    main()