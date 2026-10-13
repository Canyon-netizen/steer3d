"""⚠⚠⚴⚠⁴ `_assert_no_dup()` 这条硬门的**牙齿测试**。

⚠⚠⚴⚠⚠⚠ **为什么必须是独立脚本、而不是临时改坏的副本**：
  ⚗ 本轮第一版牙齿测试就是「把真门复制一份、手工注入重复项」。
  ⚠⚠⁴⚠⚠⚠ 而那份副本**硬编码了绝对路径**（`ROOT = Path("/Users/…"），
  ⚠⚠⁴⚠ ⚠⚠⚴⚠⚠⚠⚠⚠⚠ ⇒ 它只在**这一台机器这一个目录**下成立，⚠⚠⚴⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠
  ⚠⚠⚴⚠⚠⚠⚠⚠⚠ **换目录就静默失效** ⇒ ⚠⚠⚴⚠⚠ 那不叫牙齿测试，叫一次性巧合。
  ⚠⚠⁴⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠ ⚠⚠⚴⚠⚠⚠⚠⚠⚠⚠ ⚠⚠⚴⚠ ⚠⚠⚴⚠ ⚠⚠⚴⚠ ⚠ ⚠⚠⚴⚠ ⚠⚠⚴⚠ ⚠⚠⁴ ⚠⚠⚴⚠⚠⚠⚠ ⚠⚠⚴⚠
  ⚠⚠⁴ ⚠⚠⚴⚠ ⚠⚠⚴⚠ ⚠⚠⁴⚠ ⚠⚠⚴⚠ ⚠⚠⚴⚠ ⚠⚠⚴⚠ ⚠⚠⚴⚠ ⚠⚠⁴⚠ ⚠⚠⚴⚠⚠⚠⚠ ⚠⚠⚴⚠

⚠⚠⁴⚠ **纪律：牙齿测试必须在**任何**目录、任何机器上都能复现**，
⚠⚠⁴⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠ ⚠⚠⚴⚠ ⚠⚠⚴⚠ ⚠⚠⚴⚠ ⚠⚠⚴⚠ ⚠⚠⚴⚠ ⚠⚠⚴⚠ ⚠ ⚠⚠⁴⚠⚠⚠ ⚠⚠⚴⚠
⚠⚠⁴ ⚠⚠⚴⚠ ⚠⚠⚴⚠ ⚠⚠⁴⚠ ⚠⚠⚴⚠ ⚠⚠⚴⚠ ⚠⚠⚴⚠ ⚠⚠⚴⚠ ⚠⚠⁴⚠ ⚠⚠⚴⚠⚠⚠⚠ ⚠⚠⚴⚠

做法：**在内存里改 AST / 清单，再调真门那个函数**，不落第二个脚本文件。
⇒ 路径来自真门自己（`__file__` ⇒ `parents[2]`），**不硬编码任何路径**。

⚠⚠⁴⚠ 用例：
  U1 基线 —— 不注入 ⇒ 门**通过**（证明这条门不是恒红的）
  U2 注入一个**重复名** ⇒ 门**判红**（证明它有牙齿）
  U3 注入一个**重复锚点字符串**（名字不同、内容相同）⇒ 门**判红**
  U4 清空清单 ⇒ 门**通过**（空清单无重复；⚠ 这条同时说明门只看清单自身，
     ⚠⚠⁴⚠⚠⚠⚠ ⚠⚠⚴⚠⚠ ⚠⚠⚴⚠ ⚠ ⚠⚠⚴⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠ ⚠⚠⚴⚠ ⚠⚠⁴⚠ ⚠⚠⚴⚠ ⚠⚠⚴⚠ ⚠ ⚠⚠⁴⚠⚠⚠ ⚠⚠⚴⚠
     ⚠⚠⁴⚠⚠ ⚠⚠⚴⚠⚠⚠ ⚠⚠⚴⚠ ⚠⚠⚴⚠ ⚠⚠⚴⚠ ⚠⚠⁴⚠ ⚠⚠⚴⚠⚠⚠⚠ ⚠⚠⚴⚠
     ⚠⚠⁴⚠⚠⚠⇒ **它不检查清单对不对，只检查清单里有没有重名** ——
     ⚠⚠⁴⚠⚠⚠⚠ ⚠ 「清单漏了一项」是另一类病，由门① 的 diff 对账兜着。
"""

import importlib.util
import sys
from pathlib import Path

GATE = Path(__file__).resolve().parent / "r144_precheck.py"


def load():
    spec = importlib.util.spec_from_file_location("r144_precheck_t", GATE)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Dup(SystemExit):
    pass


def call(M, items):
    """⚠⚠⁴⚠ 临时把清单换成 items，看 _assert_no_dup 判不判红。
    ⚠ 门自己 `die()` ⇒ SystemExit(2)；不判红就正常返回。"""
    saved = M.EXPECTED_HUNKS
    M.EXPECTED_HUNKS = items
    try:
        M._assert_no_dup()
        return False          # 通过
    except SystemExit as e:
        assert e.code == 2, f"门不该 exit 2，实际 exit {e.code}"
        return True           # 判红
    finally:
        M.EXPECTED_HUNKS = saved


def main():
    M = load()
    base = list(M.EXPECTED_HUNKS)
    fails = []

    def case(label, items, want_red):
        got = call(M, items)
        ok = got == want_red
        print(f"  {'✓' if ok else '⚠⚠⁴✗✗'} {label:<46} "
              f"{'判红 ✓' if got else '通过 ✓' if not want_red else '⚗ 通过（应有牙齿）'}")
        if not ok:
            fails.append(label)

    print("=== _assert_no_dup 牙齿测试 ===")
    print(f"  清单当前 {len(base)} 项；不注入 = {call(M, base)} （False=通过）")
    case("U1 基线：原样清单", base, False)
    case("U2 注入重复**名**", base + [base[-1]], True)
    case("U3 注入重复**锚点字符串**（名字不同）",
         base + [("新名字", base[-1][1])], True)
    case("U4 清空清单（无重名 ⇒ 通过）", [], False)
    case("U5 单项清单（无重复）", base[:1], False)

    print()
    if fails:
        print(f"[硬门] {len(fails)} 条牙齿用例不过：{fails}")
        sys.exit(2)
    print(f"=== 5/5 有牙齿 ===")


if __name__ == "__main__":
    main()