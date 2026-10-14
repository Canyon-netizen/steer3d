"""旧批 unlabeled 的【三种归宿】分类器 —— 数据到之前定死口径。

⚠ 为什么要预先定死：旧批 aime25 think 池有 19 条 unlabeled（P6 唯一候选池），
⚗⚠ 而它们在新批（cap 32768）里的归宿有**三种**，不是两种：

    A 仍 truncated   —— cap 还是不够（p06：8192 截断，32768 仍跑满截断）
    B 跑完但 wrong   —— cap 够了、模型说完了，但答案是错的（p04：20360 tok 未触顶）
    C 跑完且 correct —— 这才是 P6 需要的

⚠⚠ 事先讲清楚为什么必须分开报 A 和 B：
⚗⚠ 「抬 cap 让它把话说完了」= A + B + C，而 **P6 只认 C**。
⚗⚠ 若只报「unlabeled 减少了多少」，A 和 B 会被一起算成成功
⚗⚠ —— 而它们对 correct 数的贡献是 **0**。

⚠ 口径纪律：
  · 分母固定 = 旧批 think 池里 strict == unlabeled 的题号（19 条），逐条处理，不抽样。
  · 一题一条，不按 token 数聚合。
  · 「未测」与「测到 A/B/C」分开列，未测的**不进任何一类的分母**。
  · 新旧两侧题号必须对齐（都取 pNN），因为两批文件名相同、只有 cap 不同。
"""

import json
import re
from collections import Counter
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT / ".cache/mutbak/strict_label_b2_full60.json"
# 修订 180：新批标注走位置参数。原先写死 label_32768_r177.json（16 行），
# 生成继续推进后这个脚本会**静默读旧文件**——仪器跑的不是你以为的那份。
DEFAULT_NEW = ROOT / ".cache/mutbak/label_32768_r177.json"
NEW = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_NEW
POOL = "aime__aime25__"
TT_RE = re.compile(r"^aime__aime25__p(\d{2})__think$")


def load_rows(path):
    d = json.load(open(path, encoding="utf-8"))
    return d["rows"] if isinstance(d, dict) and "rows" in d else d


def prob_of(traj):
    m = TT_RE.match(str(traj))
    return int(m.group(1)) if m else None


def main():
    for _p in (OLD, NEW):
        if not _p.exists():
            print("[错误] 读不到标注文件：%s" % _p)
            return 2
    print("=== 实际读入（先看这两行再信下面任何数）===")
    print("  旧批 = %s" % OLD.name)
    print("  新批 = %s" % NEW.name)

    old = {prob_of(r["traj"]): r for r in load_rows(OLD)
           if prob_of(r["traj"]) is not None}
    new = {prob_of(r["traj"]): r for r in load_rows(NEW)
           if prob_of(r["traj"]) is not None}

    # 候选池：旧批 think 池里 strict == unlabeled 的题号（固定分母）
    cands = sorted(p for p, r in old.items() if r["strict"] == "unlabeled")
    if not cands:
        print("[错误] 候选池为空 —— 旧批标注结构变了，先查再跑")
        return 2

    fates = {}
    untested = []
    for p in cands:
        r = new.get(p)
        if r is None:
            untested.append(p)
            continue
        if r.get("truncated"):
            fates[p] = "A 仍触顶"
        elif r["strict"] == "correct":
            fates[p] = "C 跑完且 correct"
        elif r["strict"] == "wrong":
            fates[p] = "B 跑完但 wrong"
        else:
            # 跑完了却仍 unlabeled —— 新出现的第四种，不该被静默并入 A
            fates[p] = "D 跑完但仍 unlabeled"

    measured = sorted(fates)
    cnt = Counter(fates.values())
    print("=== 旧批 unlabeled 候选池（think 臂，aime25）===")
    print(f"  候选总数（旧批 unlabeled）: {len(cands)}")
    print(f"  已测: {len(measured)}    未测: {len(untested)}")
    if untested:
        print(f"  未测题号: {['p%02d' % p for p in untested]}")
    print()
    print("=== 已测部分的归宿（分母 = 已测数，不是候选总数）===")
    for k in sorted(cnt):
        print(f"  {k:22s} {cnt[k]:3d}")
    print()
    c = cnt.get("C 跑完且 correct", 0)
    print(f"=== P6 相关（⚠ 仅就「已测」这一段，不外推到全池）===")
    print(f"  A+B 合计 = {cnt.get('A 仍触顶', 0) + cnt.get('B 跑完但 wrong', 0)}"
          f"（把话说完了但对 correct 贡献 0）")
    print(f"  C = {c}；已测段转化率 = "
          f"{'—（已测为 0）' if not measured else f'{100.0 * c / len(measured):.1f}%'}")
    # ⚠⚠⁴⚠⁴ 修订 189：这一行原来写的是
    #     need = 10 - sum(1 for p, r in old.items() if r["strict"] == "correct")
    #   即拿**旧批**的 correct 数当「已锁死」。
    #   ⚠⚠⚴⚠⚴ 那只在**漂移恒为 0** 时成立。实测打脸：
    #     新批出现一条 `wrong -> correct`（p18 think，8192 触顶答错 -> 10094 未触顶答对）
    #   ⇒ 旧批 correct=7，而新批实际**已经到手 8** ⇒ 缺口是 **2** 不是 3。
    #   ⛔ 一个「权威口径」脚本印错缺口，比没有脚本更坏 —— 它会被直接引用。
    #   ⇒ 「锁死」必须按【新批标签 ∩ 旧批已确立题集】算，漂移单列。
    established = sorted(p for p, r in old.items() if r["strict"] != "unlabeled")
    locked_correct = sum(1 for p in established
                         if new.get(p, {}).get("strict") == "correct")
    drifted = [(p, old[p]["strict"], new[p]["strict"]) for p in established
               if p in new and new[p]["strict"] != old[p]["strict"]]
    need = max(0, 10 - locked_correct)
    print(f"  P6 底线 think correct >= 10")
    print(f"  已确立题集（旧批 correct/wrong）{len(established)} 题里，"
          f"新批拿到 correct **{locked_correct}** 条 ⇒ 还需 **{need}** 条来自候选池")
    if drifted:
        print(f"  ⚠⚠⚴⚠⚴ **已确立标签被改了 {len(drifted)} 条**（这不算「重跑扰动」，"
              f"是抬 cap 本身的效果）：")
        for p, o_, n_ in drifted:
            print(f"       p%02d  {o_} -> {n_}" % p)
        print(f"     ⇒ 「旧批 correct 数」**不能**当锁死值；上面那个 {locked_correct} 才是。")
    else:
        print(f"  已确立标签 0 处改动 ⇒ 锁死值与旧批一致。")
    # ⚠⚠⁴⚠⚴ 修订 189：C 落袋之后，**两个分母都必须印**。
    #   全池门槛 need/len(cands) 在 C 已落地时**仍然对**，但它不是行动数 ——
    #   行动数是「剩下那几条里还要几条」，分母是**未测数**，不是全池。
    #   只印全池门槛会让人以为「还差 2/19 就行」，而实际只剩 6 条可捞。
    print(f"  全池口径门槛 = {100.0 * need / len(cands):.1f}%"
          f"（{need} / {len(cands)}）—— 只有全池测完才能对照这个数")
    if untested:
        print(f"  ⚠⚠ **行动数**：还需 {need} 条，而**只剩 {len(untested)} 条未测**"
              f" ⇒ 所需转化率 = {100.0 * need / len(untested):.1f}%（分母是未测数，不是全池）")
    print()
    print("=== 逐条（不抽样）===")
    print("  %-6s %-24s %-8s %-10s" % ("题", "旧", "新n_tok", "归宿"))
    for p in measured:
        r = new[p]
        print("  %-6s %-24s %-8s %-10s"
              % ("p%02d" % p, old[p]["strict"], r["n_tok"], fates[p]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())