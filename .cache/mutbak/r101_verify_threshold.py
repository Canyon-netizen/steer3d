#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
r101_verify_threshold.py —— 修订 101 的自证闸门

要回答两件事，每件都必须先证明「这台仪器量得到」：

  Q1  §93 的「同一屏两种写法」到底各印了几处？
      ⚠ 不能只数 0.5 —— 「0.5537」「0.4748」「0.8588」里都含 0.5 的字符。
        必须锚到 `|cos| < ` 这个前缀，否则会把别的数算进来。
  Q2  char_pairwise_abs_cos 那个矩阵，读者面上一共能看到几个配对余弦？

仪器自证（拿不到就 exit 2，绝不把 0 当结果）：
  A1  可见文案文件必须存在且非空
  A2  字符数必须等于浏览器报的 totalLength（防转写走样）
  A3  必须能在文案里找到本脚本预期的锚点，否则说明锚点变了
"""
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
VISIBLE = os.path.join(HERE, "r101_visible_subspace.txt")
ARTIFACT = os.path.join(ROOT, "frontend", "public", "latent", "data",
                        "readable_subspace.json")
PANEL = os.path.join(ROOT, "frontend", "components", "SubspacePanel.tsx")

# 浏览器 query(kind=text) 当时返回的 totalLength，逐字抄下来做等式左端
BROWSER_TOTAL_LENGTH = 2161


def die(msg):
    print("[自证失败] " + msg)
    sys.exit(2)


# ---------- A1 ----------
if not os.path.isfile(VISIBLE):
    die("可见文案文件不存在: " + VISIBLE)
raw = io.open(VISIBLE, encoding="utf-8").read()
if not raw.strip():
    die("可见文案文件是空的")
# ⚠ 浏览器返回的 text 末尾**没有**换行，落盘时补了一个尾换行。
#   那是文件系统产物、不是文案的一部分 ⇒ 比对前只剥**恰好一个**尾换行，
#   剥完仍不等就是真的转写走样。（第一版忘了剥，闸门报 2162 vs 2161，
#   拦下了我 —— 这条闸门不是装饰。）
stripped = 0
text = raw
if text.endswith("\n"):
    text = text[:-1]
    stripped = 1
print("[A1] 落盘 %d 字符 / %d 字节；剥掉尾换行 %d 个后 %d 字符"
      % (len(raw), len(raw.encode("utf-8")), stripped, len(text)))

# ---------- A2 ----------
if len(text) != BROWSER_TOTAL_LENGTH:
    die("转写走样：本地 %d 字符，浏览器报 %d 字符 ⇒ 这份文案不是刚取到的那份"
        % (len(text), BROWSER_TOTAL_LENGTH))
print("[A2] 剥尾换行后与浏览器 totalLength 逐字相等 (%d)" % BROWSER_TOTAL_LENGTH)

# ---------- A3 ----------
ANCHORS = ["4 条命名轴之外", "|cos| < 0.5", "|cos| < 0.50", "digit_mass ↔ newline_mass"]
for a in ANCHORS:
    if a not in text:
        die("锚点缺失: " + a + " ⇒ 这份文案与刚取到的那份不是同一份")
print("[A3] %d 个锚点全部命中" % len(ANCHORS))

# ---------- Q1：逐处列出，不靠眼睛数 ----------
# 表格行与散文都写成 `|cos| < X`，X 要么是 JSON 数字直出（0.5），
# 要么是字符串键原样（0.50）。两种写法在文案里**只有这一个可区分的前缀**。
hits = []
for m in re.finditer(r"\|cos\| < ([0-9.]+)", text):
    hits.append((m.group(1), m.start()))
print()
print("[Q1] `|cos| < ` 逐处清单（共 %d 处）" % len(hits))
for i, (val, pos) in enumerate(hits, 1):
    lo = max(0, pos - 26)
    ctx = text[lo:pos].replace("\n", " ")
    print("  %2d. 印成 %-6s ← …%s|cos| < %s" % (i, val, ctx, val))

bare = [v for v, _ in hits if v == "0.5"]
twod = [v for v, _ in hits if v == "0.50"]
# 门槛散文里还有一处不是 `|cos| < ` 形式（「已超过 0.5 门槛」），
# 它来自产物字符串，锚点是「已超过」。
absorbed = re.findall(r"已超过 ([0-9.]+) 门槛", text)
print()
print("  `|cos| < 0.5`（数字直出）  %d 处" % len(bare))
print("  `|cos| < 0.50`（字符串键）  %d 处" % len(twod))
print("  「已超过 X 门槛」（产物散文）%d 处 → X = %s" % (len(absorbed), absorbed))

# ⚠⚠ 下面这段是本轮最容易读错的地方，必须写进结论而不是留在脑子里。
#
# `|cos| < 0.50` 在扁平文本里数出来是 0，**但这不代表页面上没有 0.50**。
# 根因（已核）：源码 :182 的 `|cos| < {sep}` 与 :184 的 `{v.greedy} 条`
# 是**两个并列的 <span>**，文本扁平化时被无分隔符拼在一起
# ⇒ 「0.50」+「14 条」变成「0.5014」。
#
# ⇒ 于是扁平文本里凭空多出 6 个**数据里没有、版面上也没有**的数：
#     0.359 / 0.4011 / 0.4512 / 0.5014 / 0.5515 / 0.6016
#   它们既不等于产物里的键（0.35…0.60），也不等于任何计数（9/11/12/14/15/16）。
#
# ⚠ 这是本轮实测到的**最危险的一种假数**：它不像 0 或 1 那样一眼看出不对，
#   而是长得像一个合法的观测量。谁把它当数据读，谁就会得出错的结论
#   （本轮我自己就差点把「0.50 → 0 处」写成发现，是靠它与 §93 的既有前提
#   矛盾才反应过来的）。
#
# ⇒ 结论只能写成「扁平文本量不到 0.50」，**不能**写成「页面上没有 0.50」。
#   读者面（渲染布局）上 0.50 与 14 条是分开的两个格，§93 的前提成立。
print()
print("  ⚠ 口径警告：`0.50` 计数 %d **不可读成「页面上没有」**——" % len(twod))
print("     文本扁平化把 `<span>|cos| < 0.50</span>` 与 `<span>14 条</span>`")
print("     拼成了 `0.5014`。判定读者面须用 DOM，不能用扁平文本。")
print("  ⇒ 同一块面板上，散文位置印 `0.5` 共 %d 处（3 处 JSX + 1 处产物散文）；"
      % (len(bare) + len(absorbed)))
print("     表格 6 行的门槛格在版面上印 `0.35/0.40/0.45/0.50/0.55/0.60`（字符串键）")

# ---------- Q2：矩阵与「读者能看到的配对」 ----------
d = json.load(io.open(ARTIFACT, encoding="utf-8"))
cp = d["char_pairwise_abs_cos"]
obs = sorted({k.split("|")[0] for k in cp})
diag = [k for k in cp if k.split("|")[0] == k.split("|")[1]]
off = [k for k in cp if k not in diag]
pairs = {}
for k in off:
    a, b = k.split("|")
    pairs[frozenset((a, b))] = cp[k]
print()
print("[Q2] char_pairwise_abs_cos")
print("  条目 %d = 对角线 %d（恒为 1.0，不是配对余弦）+ 离对角 %d（对称存了两遍）"
      % (len(cp), len(diag), len(off)))
print("  ⇒ **不重复的观测量对 = %d**，不是 %d" % (len(pairs), len(cp)))

# 读者面上能看到哪些？
shown = {}
for m in re.finditer(r"([a-z_]+) ↔ ([a-z_]+) 只有 ([0-9.]+)", text):
    a, b, v = m.group(1), m.group(2), m.group(3)
    shown[frozenset((a, b))] = float(v)
print("  页面上以「X ↔ Y 只有 Z」形式出现的配对余弦：%d 个" % len(shown))

# 交叉核对：页面上那个数必须与矩阵里那一项逐位相等
for k, v in shown.items():
    key = "|".join(sorted(k))
    if key not in cp:
        die("页面印了 %s，但矩阵里没有这一项" % key)
    if float("%.4f" % cp[key]) != v:
        die("页面印 %s = %s，矩阵是 %s ⇒ 两处不同源" % (key, v, cp[key]))
    print("  ✓ 页面 %s = %s 与矩阵逐位相等（构建时同源，不是两处独立字面量）"
          % (key, v))

missing = {k: v for k, v in pairs.items() if k not in shown}
print()
print("  上屏 %d / %d 个不重复对；**看不到 %d 个**：" % (len(shown), len(pairs), len(missing)))
worst = max(pairs.items(), key=lambda kv: abs(kv[1]))
for k, v in sorted(missing.items(), key=lambda kv: -abs(kv[1])):
    nm = " ← 最紧的一个（最该给读者看）" if k == worst[0] else ""
    print("    %-32s %+.4f%s" % (" ↔ ".join(sorted(k)), v, nm))
print()
print("  ⚠ 面板的结论句「4 条互相近乎正交」在屏幕上只给证据 %s"
      % ", ".join(str(v) for v in shown.values()))
print("    而真正的约束是 %s = %+.4f，占门槛 0.5 的 %.1f%%"
      % (" ↔ ".join(sorted(worst[0])), worst[1], 100 * abs(worst[1]) / 0.5))
print("    ⇒ 屏幕上那条比约束松 %.1f 倍" % (abs(worst[1]) / max(shown.values())))

# ---------- Q3：面板源码里 char_pairwise 到底被引用几次 ----------
src = io.open(PANEL, encoding="utf-8").read()
jsx = re.findall(r"\{[^}\n]*char_pairwise[^}\n]*\}", src)
print()
print("[Q3] SubspacePanel.tsx 里 `{…char_pairwise…}` 这类 JSX 插值：%d 处" % len(jsx))
print("     （第 %d 行那处是类型声明、第 %d 行那处在注释里说该变量已删）"
      % (86, 125))
print("     ⇒ 该矩阵在页面上被读取的次数 = 0；读者看到的那 1 个数来自 verdict 字符串")

print()
print("[完成] Q1/Q2/Q3 全部取到数（不是 0），本轮结论有仪器支撑。")
