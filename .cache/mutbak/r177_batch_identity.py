"""批次身份自证 —— 在**拿到判决之前**定死，拒绝对着混批次出数。

⚠⚠⚴⚴ 为什么要专门写这个：远端 NFS 上**多个批次的文件名完全相同**，只有 cap 不同：

    gen_b2/aime/aime__aime25__p00__think.json              cap=8192   ← 旧批（对照）
    gen_b2_max32768/aime/aime__aime25__p00__think.json     cap=32768  ← 本轮
    gen_smoke_32768/…  pilot8192/…                          另有小批

⚠⚠⚴⚴⚠ 而 `traj` 取自 `trajectory_id`（`strict_label_r167.py` 第 105 行），
⚗⚠⚠⚠⚗⚠ **两批的 traj 命名一模一样** ⇒ ⚗⚠⁴⚗⚠⚗⚠ **`traj` 根本不具分辨力，唯一能分辨的是 `cap`。⚠⚠⁴⚗⚠⚗⚠⚗⚠**
⚗⚠⚠⚗⚠ 而一个 `gen_b2*/aime/*.json` 会把两批混成 120 条、`traj` 重复、`cap` 混杂 ——
⚗⚠⚗⚠⚗⚠⚗⚠ **而判决看起来完全正常。⚠⚠⚗⚠⚗⚠⚗⚠⚗⚠**

⚠⚠⁴ 纪律来源：§167「读数规则数据到前定死」。本脚本就是那条规则的可执行形式。
⚠⚠⁴⚠⚴ **恒绿不是绿** —— 本脚本必须能被证伪：拿旧批（cap=8192、120 行）跑它，
⚠⚠⁴⚠⚴⚠ **必须红**。若它对旧批也绿，说明它没在检查任何东西。
"""

import json
import re
import sys
from collections import Counter

# ⚠⚠⚴⚴ 数据集**可参数化**，不要写死。
# ⚠⚠⁴ 第一版把它写死成 aime25 ⇒ 拿旧批（它本来就含 60 条 aime26）去跑，恒红、
# ⚗⚠⁴ 红的原因还是错的（"混批" 被误报成 "数据集不对"）⇒ **恒红且红错理由，
# ⚗⚠⁴⚠⚠⁴ 比恒绿更坏：它会让我否掉一个正确的文件。**
TRAJ_RE = re.compile(r"^aime__aime25__p(\d{2})__(think|no_think)$")


def check(label_path, expect_cap, expect_rows, traj_re=None):
    """对一份标注产物做批次身份自证。返回 (是否通过, 逐条结果)。"""
    traj_re = traj_re or TRAJ_RE
    rows = []
    with open(label_path, encoding="utf-8") as fh:
        d = json.load(fh)
    rows = d["rows"] if isinstance(d, dict) and "rows" in d else d

    out = []

    def rec(name, ok, detail):
        out.append((name, bool(ok), detail))

    # 1) 行数
    rec(f"行数 = {expect_rows}", len(rows) == expect_rows, f"实际 {len(rows)}")

    # 2) cap 全等且等于本轮 cap —— ⚠ 这是【唯一】能分辨两批的字段
    caps = Counter(r.get("cap") for r in rows)
    rec(f"cap 全等且 = {expect_cap}",
        set(caps) == {expect_cap},
        f"cap 分布 {dict(caps)}")

    # 3) traj 无重复 —— ⚠ 混批次的典型签名就是「同一个 traj 出现两次、cap 不同」
    tj = [r.get("traj") for r in rows]
    dup = [k for k, n in Counter(tj).items() if n > 1]
    rec("traj 无重复", not dup, f"重复 {len(dup)} 个：{dup[:5]}")

    # 4) traj 形状合规（防止混进别的数据集/别的臂）
    # ⚠⚠⁴ 名字必须跟着正则走 —— 第一版把名字写死成「aime25」而正则可换，
    # ⚗⚠⁴⚠⚠⚴ 那就是「印出来的名字」与「实际量的东西」不一致（同 §168 那类）。⚠⚠⁴⚠⚠⚴
    bad = [t for t in tj if not traj_re.match(str(t))]
    rec(f"traj 形状匹配 {traj_re.pattern}", not bad, f"不合规 {len(bad)} 个：{bad[:5]}")

    # 5) 臂齐全：两臂各占一半
    modes = Counter(r.get("mode") for r in rows)
    rec("两臂齐全且等量",
        set(modes) == {"think", "no_think"} and len(set(modes.values())) == 1,
        f"mode 分布 {dict(modes)}")

    # 6) 判据字段齐全 —— 缺字段会让 strict 静默变 unlabeled
    need = ["traj", "mode", "cap", "n_tok", "stated", "gt", "strict"]
    missing = [k for k in need if any(k not in r for r in rows)]
    rec("判据字段齐全", not missing, f"缺失字段 {missing}")

    # 7) truncated 标记与 cap 自洽：若有 n_tok >= cap 却 truncated=False，说明读到别的字段
    bad_tr = [r.get("traj") for r in rows
              if r.get("n_tok") is not None and r.get("cap")
              and r["n_tok"] >= r["cap"] and not r.get("truncated")]
    rec("truncated 与 cap 自洽", not bad_tr, f"不自洽 {len(bad_tr)} 条：{bad_tr[:5]}")

    ok = all(o for _, o, _ in out)
    return ok, out


def main():
    if len(sys.argv) < 4:
        print("用法: r177_batch_identity.py <label.json> <expect_cap> <expect_rows> [dataset_re]")
        return 2
    label_path, expect_cap, expect_rows = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    # ⚠ 第 4 个参数可覆盖数据集正则。默认只认 aime25（本轮输入已校验纯 aime25）。
    # ⚠⚠⁴ 拿旧批（含 aime26）验它时，必须显式放宽，否则会恒红 —— 而恒红会让我否掉正确文件。
    traj_re = re.compile(sys.argv[4]) if len(sys.argv) > 4 else TRAJ_RE
    ok, out = check(label_path, expect_cap, expect_rows, traj_re)
    print(f"=== 批次身份自证：{label_path} ===")
    print(f"    期望 cap={expect_cap}  行数={expect_rows}  数据集正则={traj_re.pattern}")
    for name, o, detail in out:
        print(f"  [{'✅' if o else '❌'}] {name}  —— {detail}")
    print(f"\nRESULT {'IDENTITY-OK' if ok else 'IDENTITY-FAIL'}")
    # ⚠⚠⁴ 退出码：身份不过 ⇒ 判决不许出（不是 warning）
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())