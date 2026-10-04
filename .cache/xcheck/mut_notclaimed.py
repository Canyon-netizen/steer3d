#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第三十三笔之三 Z 组变异台：证明 Z5–Z10 每一条都有牙。

## 为什么要有这个

判据绿只说明「它没红」。要说明它**能**红，必须把被测物改坏一次看它报红。
第三十二笔的教训：`C4` 的表达式是 `isinstance(unread, list)` ——
0 个缺口 PASS、27 个缺口也 PASS，**恒真**，所以任何变异都抓不到它。

## 每个变异只改一处，且改完必须还原

用 `git stash` 不行：工作区有 7 项与本轮无关的既有改动。
所以这里自己做「备份 → 改 → 跑 → 还原」，逐字节还原并校验哈希。

## 变异清单

  M-J  Z8  把 index.html:291 的措辞退回「真正参与的维度是 587–831 / 2048」
  M-K  Z7  让 applyModelFacts() 跳过 #orientation 内的 [data-f]（覆盖范围被缩掉）
  M-L  Z10 把 models.json 的 n_eff_pct 改成不是 n_eff/d_model 的值
  M-M  Z9  把 analyse_spread.py 里 n_eff 的「个数 / 上界是宽度」定义改掉
  M-N  Z5  删掉第 3 条 .noitem（标题还写着「4 种说法」）
  M-O  Z6  给 #orientation 加一条永不消掉的 display:none
"""
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time

ROOT = "/Users/zhourui/code/steer3d"
PAGE = os.path.join(ROOT, "frontend/public/latent/index.html")
REGISTRY = os.path.join(ROOT, "frontend/public/latent/models.json")
SPREAD = os.path.join(ROOT, "backend/examples/analyse_spread.py")
JUDGE = os.path.join(ROOT, ".cache/browser_verify/verify_latent_prose.mjs")
URL = os.environ.get("LAT_URL", "http://127.0.0.1:22220/latent/index.html")

ZONES = ["Z5", "Z6", "Z7", "Z8", "Z9", "Z10"]


def sha(p):
    return hashlib.sha256(io.open(p, "rb").read()).hexdigest()


def rd(p):
    return io.open(p, encoding="utf-8").read()


def wr(p, s):
    io.open(p, "w", encoding="utf-8").write(s)


# ---------------------------------------------------------------- 变异定义
def m_j(p):
    """退回原来的措辞：'维度是 587–831 / 2048'，并删掉就地解释。"""
    s = rd(p)
    new = re.sub(
        r'；这份推动量摊在 <b data-f="neff">[^<]*</b> 个维度上'
        r'（这个模型一共 <span data-f="d">[^<]*</span> 个）。'
        r'<i class="inline-gloss">[^<]*</i>',
        '；真正参与的维度是 <b data-f="neff">587–831</b> / <span data-f="d">2048</span>。',
        s)
    if new == s:
        raise SystemExit("M-J 没匹配上：措辞已经变了？")
    wr(p, new)


def m_k(p):
    """让 applyModelFacts() 跳过 #orientation 里的槽 —— 覆盖范围被缩掉。"""
    s = rd(p)
    old = '  for(const el of document.querySelectorAll("[data-f]")){'
    new = ('  const _ov = document.getElementById("orientation");\n'
           '  for(const el of document.querySelectorAll("[data-f]")){\n'
           '    if(_ov && _ov.contains(el)) continue;   // MUTATION M-K')
    if old not in s:
        raise SystemExit("M-K 没匹配上：applyModelFacts 的循环变了？")
    wr(p, s.replace(old, new, 1))


def m_l(p):
    """n_eff_pct 改成不是 n_eff/d_model 的值。"""
    d = json.loads(rd(p))
    d["models"][0]["n_eff_pct"] = [11.1, 22.2]
    wr(p, json.dumps(d, ensure_ascii=False, indent=2) + "\n")


def m_m(p):
    """把 n_eff 的定义改成「超过阈值的维数」—— 页面那句「等效 N 个维度」就变假了。

    ⚠ 用正则而不是逐字匹配：这段 docstring 里有换行 + 40 空格缩进，
      逐字写死会在别人调整过排版后静默失配（而失配 = 变异没发生 =
      判据看起来「抓不到」，实际是台子没改到东西）。
    """
    s = rd(p)
    s2, n1 = re.subn(r"the number of\s+equally-weighted dimensions",
                     "the count of dimensions above a fixed threshold", s, count=1)
    s2, n2 = re.subn(r"bounded\s+by the width", "unbounded by anything", s2, count=1)
    if n1 != 1 or n2 != 1:
        raise SystemExit("M-M 匹配失败：个数定义 %d 处 / 上界 %d 处（应各 1）" % (n1, n2))
    wr(p, s2)


def m_n(p):
    """删掉第 3 条 .noitem（标题还自称「4 种说法」）。"""
    s = rd(p)
    lines = s.split("\n")
    idx = [i for i, l in enumerate(lines) if 'class="noitem"' in l]
    if len(idx) != 4:
        raise SystemExit("M-N 找到 %d 条 .noitem，不是 4 条" % len(idx))
    del lines[idx[2]]
    wr(p, "\n".join(lines))


def m_o(p):
    """给 #orientation 加一条永不消掉的 display:none —— 在 DOM 里但读者看不见。"""
    s = rd(p)
    old = '<div id="orientation" class="hide">'
    new = '<div id="orientation" class="hide" style="display:none!important">'
    if old not in s:
        raise SystemExit("M-O 没匹配上：orientation 的开标签变了？")
    wr(p, s.replace(old, new, 1))


def m_p(p):
    """把 near 从 applyModelFacts() 的 v 里删掉 ⇒ 那个槽永远停在静态兜底。

    打的是 Z11 的**前半段**：页面上有个 [data-f] 键，而填它的代码不认这个键。
    这正是 applyModelFacts() 注释（:613-618）自己担心的那种静默失败。
    """
    s = rd(p)
    old = "    near: m.near_miss_text,\n"
    if old not in s:
        raise SystemExit("M-P 没匹配上：v 里没有 near 那行？")
    wr(p, s.replace(old, "", 1))


def m_q(p):
    """把 near 错接到 c4_short 上 ⇒ 槽里的值与注册表对不上。"""
    s = rd(p)
    old = "    near: m.near_miss_text,\n"
    if old not in s:
        raise SystemExit("M-Q 没匹配上：v 里没有 near 那行？")
    wr(p, s.replace(old, "    near: m.c4_short,\n", 1))


MUTS = [
    ("M-J", PAGE, m_j, "Z8"),
    ("M-K", PAGE, m_k, "Z7"),
    ("M-L", REGISTRY, m_l, "Z10"),
    ("M-M", SPREAD, m_m, "Z9"),
    ("M-N", PAGE, m_n, "Z5"),
    ("M-O", PAGE, m_o, "Z6"),
    ("M-P", PAGE, m_p, "Z11"),
    ("M-Q", PAGE, m_q, "Z11"),
]


def run_judge():
    env = dict(os.environ, LAT_URL=URL)
    p = subprocess.run(["node", JUDGE], cwd=os.path.dirname(JUDGE),
                       env=env, capture_output=True, text=True, timeout=300)
    out = p.stdout + p.stderr
    red = set()
    for line in out.split("\n"):
        m = re.match(r"\[FAIL\] (Z\d+)", line.strip())
        if m:
            red.add(m.group(1))
    tail = re.search(r"=== (\d+)/(\d+) passed ===", out)
    return red, (tail.group(0) if tail else "(没读到汇总行)"), out


def main():
    print("变异台：%s" % URL)
    only = os.environ.get("MUT_ONLY", "").strip()
    base_red, base_sum, _ = run_judge()
    print("基线：%s　红=%s" % (base_sum, sorted(base_red) or "无"))
    if base_red - {"Z5", "Z6", "Z7", "Z8", "Z9", "Z10", "Z11"}:
        print("⚠ 基线里就有本组之外的红，先查那个")
    baseline_zone_red = base_red & set(ZONES)
    if baseline_zone_red:
        print("⛔ 基线 Z 组就已经是红的（%s），变异台不作数，先修判据"
              % sorted(baseline_zone_red))
        return 1
    if only:
        print("（MUT_ONLY=%s ⇒ 只跑这些）" % only)

    ok = True
    for name, path, fn, expect in MUTS:
        if only and name not in [x.strip() for x in only.split(",")]:
            continue
        before = sha(path)
        bak = path + ".mutbak"
        shutil.copy2(path, bak)
        try:
            fn(path)
            if sha(path) == before:
                print("%s ❌ 变异没真的改到文件" % name)
                ok = False
                continue
            red, summ, _ = run_judge()
            hit = expect in red
            extra = sorted(red - {expect})
            print("%s 期望 %s 红 → %s　%s%s"
                  % (name, expect, "✅ 红了" if hit else "❌ 没红", summ,
                     ("　（顺带红了 %s）" % extra) if extra else ""))
            if not hit:
                ok = False
        finally:
            shutil.move(bak, path)
            if sha(path) != before:
                print("⛔ %s 还原失败！手工检查 %s" % (name, path))
                ok = False
    print("\n%s" % ("全部变异都被抓到 ✅" if ok else "有变异没被抓到 ⛔"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
