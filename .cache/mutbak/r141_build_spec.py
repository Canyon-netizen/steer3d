"""汇编历史重跑清单 `r141_hist_spec.json`。

⚠⚠⚴ **每个臂的 `expect`（期望形状）必须能追到出处**，⚠ 不许凭印象填。
  · 派生臂（r135/r136/r138）：`criterion` 直接从**当时的 spec** 里读，不手抄。
  · 手写臂（r134b_*）：从**修订 134 的正文**里读 ⚠⚠⚴ 读不到的标 `expect: null`。
⚠⚠⚴ **无声明 ⇒ 跑台只记录实测、不发合格/不合格**（⚗「跳过」≠「通过」）。
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".cache/mutbak/r141_hist_spec.json"

# ⚠ 手写臂的声明，出处全部是修订 134 的正文（行号在注释里）
# ⚠⚠⚴⚠⚴ **这三个臂靠环境变量 `R134_ARM` 选臂，默认值是 `'fork'`。**
#   第一版重跑**没设这个变量** ⇒ `r134b_all/pair/xy.mjs` **三个全都跑了 fork**，
#   ⚗ 还给出了一张「D2 没牙齿、D3 没跳过、D5 不崩」的**看起来完全正常**的判决表。
#   ⚠⚠⚴ 日志里其实**自己写着** `[扰动已落地] 臂 fork` —— ⚠ **信息一直在，是我没核。**
#   ⇒ 固化：**文件名 ≠ 跑的臂；必须核日志自称的臂名。**
HAND = [
    # 臂名,               node,                          R134_ARM, 自称臂名, expect,             出处
    ("r134b_fork", ".cache/mutbak/r134b_fork.mjs", "fork", "fork",
     {"flips": ["D1"]}, "修订 134 §134.1：RED D1 … -1 → -1（应为 2 → 8）/ FAIL 35/36"),
    ("r134b_all", ".cache/mutbak/r134b_all.mjs", "all", "all",
     {"flips": ["D2"]}, "修订 134 §134.2：RED D2 「看全部」6 → 6，应 28 / FAIL 35/36"),
    ("r134b_pair", ".cache/mutbak/r134b_pair.mjs", "pair", "pair",
     # ⚠⚠⚴⚠⁴ 这里**只列 D3**，⚠ 不列 D4 —— 而修订 134 §134.4 写的是
     #   「D3 **与 D4**（同在一个 else { } 里）**一起被跳过**」。
     #   ⚠⚠⁴ **那句话把两件事混成了一件**（实测发现，判据源码 :203-209 为证）：
     #     · D3 在 if 分支 ⇒ 走 `skip(...)` ⇒ **打出一行 [SKIP]**、显式不进分母
     #     · D4 在 **else 里** ⇒ D3 跳过时它**压根没执行** ⇒ **没有 [SKIP] 行**
     #   ⇒ 两者都从 36 里掉出去（所以分母是 34），⚠⚠⁴ **但机制完全不同**：
     #     一个是「被判据自己声明跳过」，一个是「压根没被调用」。
     #   ⚗ 把后者写成「被跳过」⇒ 将来有人去修 D3 的跳过逻辑，会以为 D4 也有个跳过分支。
     {"skip": ["D3"]}, "修订 134 §134.4：[SKIP] D3 / RESULT OK 34/34"
     "（⚠⚠⚴⚠⁴ 修订 134 说 D4「一起被跳过」是**误读** —— D4 在 else 里，"
     "D3 跳过时它**压根没执行**；⚠ 修订 136 证明这次跳过本身还是假的）"),
    ("r134b_xy", ".cache/mutbak/r134b_xy.mjs", "xy", "xy",
     {"crash": True}, "修订 134 §134.5：删掉 #tabXY ⇒ TypeError，压根不打印 RESULT"),
    ("r134b_path_dgroup", ".cache/mutbak/r134b_path_dgroup.mjs", "path_dgroup", None,
     None, "⚗ 预登记里**没有点名**这个臂 ⇒ 无可引用的声明"),
]

# ⚠ 臂名会跨批次撞车（r136_arms/d4 与 r138_arms/d4 同名）⇒ 键上加批次前缀
BATCHES = [
    ("r135", ".cache/mutbak/r135_spec_a5.json", ".cache/mutbak/r135_arms/"),
    ("r135b", ".cache/mutbak/r135_spec_ace.json", ".cache/mutbak/r135_arms/"),
    ("r136", ".cache/mutbak/r136_spec.json", ".cache/mutbak/r136_arms/"),
    ("r138", ".cache/mutbak/r138_spec.json", ".cache/mutbak/r138_arms/"),
]

# ⚠⚠⚴⚠⁴ 少数臂**声明的形状与「恰好一条红」不同**，必须单列（出处=各修订正文）
OVERRIDE = {
    "r136_c2": {"flips": ["C2", "D1"]},   # 修订 137 §137.1：C2 臂不纯（一处扰动打两条）
    "r135b_c4": {"flips": ["C4", "D1"]},  # 修订 135：C4 臂连带 D1（末行 = 分叉行）
    "r136_d4": {"flips": []},             # 修订 136：改错文件那一版，**实测就是一条都不翻**
    "r136_a1": {"flips": []},             # ⚗ 修订 137 §137.2：装置前置不成立，本轮仍不发数
}


def first_token(c):
    """从 criterion 文本取**判据代号**（'D4 prod.problems…' → 'D4'）。"""
    import re
    m = re.match(r"^([A-Z]\d+[a-z]?)\b", (c or "").strip())
    return m.group(1) if m else None


def main():
    arms, srcs, missing = [], [], []
    for batch, spec_path, outdir in BATCHES:
        p = ROOT / spec_path
        if not p.exists():
            missing.append(spec_path)
            continue
        s = json.loads(p.read_text(encoding="utf-8"))
        srcs.append(s["src"])
        for a in s["arms"]:
            key = f"{batch}_{a['name']}"
            # ⚠⚠⚴⚠⁴ 第一版写的是 `{"flips": [a["name"]]}` —— 那是**臂名**（'a5'、'c4'），
            # ⚠ 不是**判据代号**（'A5'、'C4'）⇒ 12 个臂全被误报成「翻面的是 A5，声明的是 a5」。
            # ⚠⚠⁴ 那 12 条**全是规格的错，不是臂的错** —— ⚗ 一旦不查就会写成
            # ⚠ 「这批臂的声明对不上」，⚗ **方向完全相反的结论。**
            code = first_token(a.get("criterion", ""))
            # ⚠⚠⚴⚠⁴ **r135 那两批 spec 压根没有 `criterion` 字段** ——
            #   ⚠ 实测 `KeyError: 'criterion'`。⇒ 只能从**臂名大写**回退。
            #   ⚠⚠⁴ 这正是待拍板那条「台子的 criterion 字段要不要升成必填闸门」的**直接证据**：
            #   ⚗ 缺了这个字段，跑台就**不知道该期望哪条判据翻面**，只能靠约定猜。
            #   ⚠ 所以这里**显式记录 code 的来源**，⚗ 不让回退看起来像本来就有的。
            code_src = "criterion" if code else ("arm名大写（spec 无 criterion 字段）" if code is None else None)
            if code is None:
                code = str(a["name"]).upper()
            arms.append({
                "name": key,
                "node": f"{outdir}{Path(s['src']).stem}_{a['name']}.mjs",
                "criterion": a.get("criterion", ""),
                "code": code,
                "code_src": code_src,
                "expect": OVERRIDE.get(key, {"flips": [code]}),
                "env": {},
                "self": None,
                "from": spec_path,
            })

    for name, node, sel, self_name, exp, src in HAND:
        arms.append({"name": name, "node": node, "criterion": "", "code": None,
                     "expect": exp, "env": {"R134_ARM": sel}, "self": self_name,
                     "from": src})

    # ⚠ 臂文件必须真的存在 —— 不存在的臂跑台会记成「仪器坏了」，不是「臂不通过」
    gone = [a["node"] for a in arms if not (ROOT / a["node"]).exists()]

    spec = {"src": srcs[0] if srcs else ".cache/browser_verify/verify_path.mjs", "arms": arms}
    OUT.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"已写出 {OUT.relative_to(ROOT)}：{len(arms)} 个臂")
    print(f"  基线源 {spec['src']}")
    print(f"  ⚗ 无声明只记录的：{[a['name'] for a in arms if a['expect'] is None]}")
    print(f"  ⚗ 期望崩：{[a['name'] for a in arms if a['expect'] and a['expect'].get('crash')]}")
    print(f"  ⚗ 期望跳过：{[a['name'] for a in arms if a['expect'] and a['expect'].get('skip')]}")
    print(f"  ⚠ 翻面不止一条：{[a['name'] for a in arms if a['expect'] and len(a['expect'].get('flips', [])) > 1]}")
    guessed = [a["name"] for a in arms if a.get("code_src", "").startswith("arm")]
    if guessed:
        print(f"  ⚠⚠⚴ 判据代号靠臂名大写回退的：{guessed}（原 spec 无 criterion 字段）")
    if missing:
        print(f"  [错误] 找不到 spec：{missing}")
    if gone:
        print(f"  [错误] 臂文件不存在：{gone}")
    if missing or gone:
        raise SystemExit(2)


if __name__ == "__main__":
    main()