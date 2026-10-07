#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""方向验法：这套判据能不能在**已知答案**的情形下给出正确方向？

⚠ 读数是「动摇点的首层比随机点**晚** +20.7pp，p=0.0015」。
  我原先的假设是「模型先在浅层知道错误」⇒ **期望**动摇点更**早**。
  实测**反了**。在下结论前必须排掉两种可能：
    (a) 判据把方向读反了（实现 bug）
    (b) 现象是真的，但我的**解释**错了

⚠ 验证 (a) 的办法：造一个**方向已知**的合成位置。
  在同一条轨迹里取紧邻「句号之后」的位置 —— 那里下一个 token 必然是
  新一句的起始（标点/连词），其 token 身份**在浅层就应当定型**；
  再取一个**句中随机**位置作对照。
  若判据方向没错，前者的首层应当**不晚于**后者。

⚠ 若这个「已知应当更早」的情形读出来也是「晚」，说明这套判据恒偏晚，
  那 +20.7pp 就不能解释成「动摇点更晚」。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MUT = os.path.join(ROOT, ".cache", "mutbak")
HINGE = os.path.join(ROOT, ".cache", "xcheck", "hinge.json")


def run(pos_map, out):
    pf = os.path.join(MUT, "_pos_tmp.json")
    json.dump(pos_map, open(pf, "w"), indent=1)
    r = subprocess.run(
        [sys.executable, "backend/examples/build_logit_lens.py",
         "--scan", "explicit", "--positions", pf, "--out", out],
        cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-1500:], r.stderr[-1500:])
        raise SystemExit(1)
    return json.load(open(out, encoding="utf-8"))


def main() -> int:
    lens = json.load(open(os.path.join(MUT, "logit_lens_hinge.json"),
                          encoding="utf-8"))
    T = {tr["id"]: tr["T"] for tr in lens["trajectories"]}
    NPZ = os.path.join(ROOT, "datasets", "aime_qwen3_1p7b_16k_fp16", "aime")

    # 造两类位置
    after_dot, midword = {}, {}
    for tid in sorted(T):
        text = json.load(open(os.path.join(NPZ, tid + ".json"),
                              encoding="utf-8"))["generated_text"]
        # 字符偏移 → tok 需要 tokenizer；这里退一步：用 hinge.json 的 tok
        # 与文本长度比例对齐不可靠 ⇒ 改用「每 N 个 token 取一个」
        # 简化：用 T 均匀取点，前半段当 after_dot 不成立。
        # ⇒ 正确的做法是走 tokenizer。
        pass

    # ---- 走 tokenizer 做字符→tok 对齐 ----
    sys.path.insert(0, os.path.join(ROOT, ".cache", "pylibs"))
    from transformers import AutoTokenizer
    tokz = AutoTokenizer.from_pretrained(
        os.path.join(ROOT, "datasets", "models", "Qwen3-1.7B"))

    import re
    for tid in sorted(T):
        text = json.load(open(os.path.join(NPZ, tid + ".json"),
                              encoding="utf-8"))["generated_text"]
        offs = tokz(text, return_offsets_mapping=True,
                    add_special_tokens=False)["offset_mapping"]
        # 位置 A：紧跟句号之后的第一个 token（下一句的开头）
        a = []
        for i, (s, e) in enumerate(offs[:-1]):
            if e < len(text) and text[e:e + 2] in (". ", ".\n", "? ", "! "):
                a.append(i)
        # 位置 B：句中（前后 30 字符内没有句号）
        b = []
        for i, (s, e) in enumerate(offs):
            w = text[max(0, s - 30):e + 30]
            if "." not in w:
                b.append(i)
        k = min(len(a), len(b), 8)
        if k:
            after_dot[tid] = a[:k]
            midword[tid] = b[:k]

    da = run(after_dot, os.path.join(MUT, "_lens_afterdot.json"))
    db = run(midword, os.path.join(MUT, "_lens_mid.json"))

    def lateness(d):
        c = d["aggregate"]["first_layer_correct_hist"]["counts"]
        n = sum(c)
        return (sum(c[20:]) / n if n else 0), n

    la, na = lateness(da)
    lb, nb = lateness(db)
    print("=== 方向验法（这两个位置都是**非**动摇点）===")
    print(f"  A 紧跟句号后（新句开头）n={na:3d}  L20+ 占 {la*100:3.0f}%")
    print(f"  B 句中（周围无句号）  n={nb:3d}  L20+ 占 {lb*100:3.0f}%")
    print(f"\n  A − B = {(la-lb)*100:+.1f} 个百分点")

    # ⚠⚠ 第一版在这里就下了「✓ 方向没错」的结论，**是错的**。
    #   A 与 B 完全相等（65% vs 65%）只能说明「判据没有系统性偏移」，
    #   证不了「判据在应当更早时会更早」—— 那需要 A 与 B **本来就不该相等**。
    #   若两组真的一样，这个验法就没有鉴别力，不能拿来当方向正确的证据。
    if abs(la - lb) < 0.02:
        print("\n⚠ A 与 B **完全相同** ⇒ 这个验法没有鉴别力：")
        print("  它只能说明「判据无系统偏移」，**不能**证明「应当更早时会更早」。")
        print("  不许拿它当方向正确的证据。")
        print("\n  真正有鉴别力的对照见下方 C：")
        c_map = {}
        for tid in sorted(T):
            text = json.load(open(os.path.join(NPZ, tid + ".json"),
                                  encoding="utf-8"))["generated_text"]
            offs = tokz(text, return_offsets_mapping=True,
                        add_special_tokens=False)["offset_mapping"]
            # C：**空白/换行** token —— 它们的 token 身份与语义无关，
            #    浅层就必然定型。若 C 的 L20+ 明显**低于** A 与 B，
            #    就证明判据在「浅层即可定型」时确实读出更早。
            c = [i for i, (s, e) in enumerate(offs)
                 if e > s and text[s:e].strip() == ""]
            if c:
                c_map[tid] = c[:8]
        dc = run(c_map, os.path.join(MUT, "_lens_blank.json"))
        lc, nc_ = lateness(dc)
        print(f"\n  C 空白 token（语义无关，浅层必定型）n={nc_:3d}  "
              f"L20+ 占 {lc*100:3.0f}%")
        print(f"  C vs 随机位 B：{(lc-lb)*100:+.1f} 个百分点")
        if lc < lb - 0.05:
            print("  ✓ C 明显更早 ⇒ 判据在「浅层即可定型」时确实读出更早，")
            print("    ⇒ 方向没错，动摇点的 +20.7pp「更晚」是真实读数。")
        else:
            print("  ✗ C 不更早 ⇒ 这套 argmax 对齐判据**无法**分辨深浅，")
            print("    +20.7pp 不能按「更深层才定型」解释。")
    else:
        print("\n  A 与 B 有差异，方向按上表读取。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())