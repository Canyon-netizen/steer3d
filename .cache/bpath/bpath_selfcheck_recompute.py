"""B 路产物 `selfcheck` 的**复算器**（修订 62 T2）。

## 它替掉什么

`build_bpath_evidence.py` 里原本写死两句：

```python
"selfcheck_passed": True,
"selfcheck": "位置+层轴 12/12；P9 判定 11/11（含新旧闸门对照）；判决脚本 26/26；"
             "正交度判定器（Q3）带类型断言",
```

⚠⚠ 那三个计数**不由这个生成器计算**，`true` 也是字面量
⇒ 它报的是「**上次跑过**」，不是「**现在成立**」。
⇒ 本模块每次构建都**真跑**那几套脚本，并把结果写进产物。

## ⚠⚠ 跑不起来的项必须显式 `unavailable`，不许沿用旧结论

实测第四项（正交度自检）把**远端绝对路径**写死：

```
FileNotFoundError: '/home/zhourui/steer3d_bpath/w_L19_m0.npy'
```

⇒ 它在本机**跑不起来**。产物原先照旧宣称「带类型断言」成立。
⇒ 本模块把它记成 `{"status": "unavailable", "reason": …}`，
并要求构建器把 `unavailable` 的项**显式写进产物**。
这是 §4「空洞通过要显式报『本项无判据』」在产物层的落地。

## 用法

    PYTHONPATH=.cache/pylibs python3 .cache/bpath/bpath_selfcheck_recompute.py
"""
from __future__ import annotations

import io
from pathlib import Path
import os
import re
import subprocess
import sys

HERE = Path(os.path.dirname(os.path.abspath(__file__)))
ROOT = HERE.parent.parent
PYLIBS = str(ROOT / ".cache/pylibs")

# (显示名, 脚本, 说明)
SUITES = [
    ("位置+层轴", "load_xy_pos_selftest.py",
     "把 x/y 的位置+层轴读法与产物自洽性"),
    ("P9 判定", "p9_verdict_selftest.py",
     "P9 判决脚本的 11 项（含新旧闸门对照）"),
    ("判决脚本", "r6_verdict_selftest.py",
     "R-6 判决脚本的 26 项"),
    ("正交度判定器(Q3)", "ortho_frac_selfcheck.py",
     "同口径先验检查（带类型断言）"),
]

_TOTAL = re.compile(r"总计\s*(\d+)\s*项，失败\s*(\d+)")


def _run(name, script, why):
    path = os.path.join(HERE, script)
    if not os.path.exists(path):
        return {"name": name, "script": script, "why": why,
                "status": "unavailable", "reason": "脚本不在 %s" % HERE}
    env = dict(os.environ)
    env["PYTHONPATH"] = PYLIBS + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONPYCACHEPREFIX"] = str(ROOT / ".cache/mutbak/pyc")
    try:
        p = subprocess.run([sys.executable, path], env=env, cwd=ROOT,
                           capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired:
        return {"name": name, "script": script, "why": why,
                "status": "unavailable", "reason": "超时 900s"}
    out = (p.stdout or "") + (p.stderr or "")
    m = _TOTAL.search(out)
    if not m:
        # ⚠ 跑不动 / 崩了 —— 都要**说清楚**，不能算成通过。
        tail = " ".join(out.strip().splitlines()[-1:])[:200]
        return {"name": name, "script": script, "why": why,
                "status": "unavailable",
                "reason": "退出码 %s，没跑到「总计」行（末行：%s）"
                          % (p.returncode, tail)}
    total, failed = int(m.group(1)), int(m.group(2))
    return {"name": name, "script": script, "why": why,
            "status": "ran", "total": total, "failed": failed}


def recompute():
    items = [_run(*s) for s in SUITES]
    ran = [x for x in items if x["status"] == "ran"]
    unav = [x for x in items if x["status"] != "ran"]
    return {
        "suites": items,
        "n_ran": len(ran),
        "n_unavailable": len(unav),
        "n_failed": sum(x["failed"] for x in ran),
        # ⚠ `passed` 只表达「**跑起来的**那一部分全过」。
        # ⚠⚠ 它**不是**「全部通过」—— 跑不起来的项不许被算成通过。
        "passed": (not unav) and all(x["failed"] == 0 for x in ran),
        "all_ran": len(unav) == 0,
    }


def one_line(r):
    """人读的一行（**只报实况**，不许把 unavailable 写成通过）。"""
    bits = []
    for x in r["suites"]:
        if x["status"] == "ran":
            bits.append("%s %d/%d" % (x["name"], x["total"] - x["failed"],
                                      x["total"]))
        else:
            # ⚠ 截断长度不是随手定的：原来截到 60 字符时，末行只剩
            #   「…No such file 」，**缺的哪个文件被切掉了** ——
            #   而 T2 要求的是「**写明缺什么**」。
            #   ⇒ 取到 110，让 `/home/…/w_L19_m0.npy` 这种路径能露出来。
            bits.append("%s ⚠**本项无判据**（%s）" % (x["name"],
                                                      x["reason"][:110]))
    return "；".join(bits)


def main():
    r = recompute()
    print("=== B 路 selfcheck 复算（修订 62 T2）===")
    print(one_line(r))
    print("  跑起来 %d 项，失败 %d 项，跑不起来 %d 项"
          % (r["n_ran"], r["n_failed"], r["n_unavailable"]))
    print("  passed=%s（⚠ 只表示「跑起来的全过」；all_ran=%s）"
          % (r["passed"], r["all_ran"]))
    return 0 if (r["n_failed"] == 0) else 1


if __name__ == "__main__":
    sys.exit(main())