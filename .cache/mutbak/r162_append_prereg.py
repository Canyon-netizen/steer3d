"""把**修订 162** 追加到 R-6 预登记。

本节：状态生成器在**崩**的时候也给出可执行修复，⚠ 并当场验证那条命令真的有效。
"""

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / ".cache/xcheck/R6_RERUN_PREREG.md"

SECTION = """
## 修订 162 —— ✅ **崩也给可执行修复**，并当场验证那条命令有效（第二次撞上服务回收）

### 162.0 ⚠ 起因：11:38 服务**再次**被回收（正好又是一个小时）

⚠⚠⁴ ⚠ §161 刚记下「后台服务 maxRunMs = 3600 秒」，⚗⚠ **一小时后它准时又没了。**
⚗⚠ ⚠⇒ **§161 那条从「观察」升级成「规律」。⚠⚠⁴⚠⚴⚠⚴⚠⚴⚠⚴⚠⚴⚠⚴⚠⚴⚠⚴⚠⚴⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠**

⚠⚠⁴ ⚠ `status.py` 这时报的是 **崩：verify_path「装置故障：页面 40s 内没 boot」**，
⚗⚠⚴⚗⚠⚗⚠⚗ **⚗⚠⚴⚗⚗⚗⚗⚗⚗⚗⚗ 但它只说了「故障」，⚗⚠⚴⚗⚗⚗⚗⚗⚗⚗ ⚗ 没给怎么修。⚗⚠⚴⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗**

### 162.1 ⚠⚠⁴⚠⚴⚠⚠ **把修订 151 那套搬过来：崩 ⇒ 印可执行命令**

⚠ §151 已把这套做给了 `scan_panel_coverage.py`（C0 判红时印真命令）。
⚠⚠⁴⚠⚴ ⚗⚠⚴⚗⚗⚗⚗⚗ **⚗⚠⚴⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗**
⚠⚠⚴ ⚗⚠⚴⚗⚗⚗⚗⚗⚗ **⚗⚠⚴⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗ 判红却给不出可执行路径的判据，⚗⚠⚴⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗ 等于半个判据。⚗⚠⚴⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗**

⚠⚠⁴ ⚠ 新增 `FIXES` 表：崩的仪表**逐个**印出修复命令；
⚗⚠⚴ ⚗⚠⚴⚗ **而红的仪表不给** ⚗⚠⚴⚗⚗⚗⚗ ⚗ **—— 红的下一步是拍板，不是修文件。⚗⚗⚗⚗⚗⚗⚗⚗**

```
--- 崩掉的仪表：可执行修复 ---
  [verify_path] 装置故障：页面 40s 内没 boot，判据无法开始  [40.5s]
页面服务不在 —— 本机 `next start` **每 3600 秒会被后台任务回收一次**，
                而 C0 的窗口是 7200 秒 ⇒ **约每 1 小时就得重起一次**。
     → cd frontend && npx next start -p 22224   （⚠ 必须作为后台任务起，别用 `(... &)`）
     → 重跑本脚本即可；产物若也过期，另跑两页探针（见 scan_panel_coverage 的指引）
```

### 162.2 ⚠⚠⁴⚠⚴⚠⚠⚠⚠ **印出修复 ≠ 修复有效 —— 所以当场验**

⚠⚠⁴ ⚠⚠⚴⚠⚴⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠
⚗⚠⚴⚗⚠⚴⚗⚠⚴ ⚗⚠ **⚗⚠⚴⚗⚠⚴⚗⚠⚴ 一条没被验证过的「修复命令」，⚗⚠⚴⚗⚠⚴⚗⚠⚴ 和一句空话在效果上没区别。⚗⚠⚴⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗**
⚠⚠⁴⚠⚴⚠ ⇒ **照着它跑了一遍**（`cd frontend && npx next start -p 22224`）：

```
改前：崩 1 / 绿 5 / 红 2    verify_path 崩（装置故障）
改后：崩 0 / 绿 6 / 红 2    verify_path 绿  RESULT OK 39/39
```

⚠⚠⁴ ⚗⚠ **⇒ 那条命令真的有效。⚗⚠⚴⚗⚗⚗⚗⚗⚗⚗** ⚠⚠⚴ ⚗⚠⚴⚗⚗⚗⚗⚗⚗ **且它现在是一条**被验证过的**路径，不是承诺。⚗⚠⚴⚗⚗⚗⚗⚗⚗⚗**

### 162.3 ⚠ 校验

- ⚠ 服务**第二次**在整点被回收（11:38，与 §161 的 3600 秒吻合）
- ⚠ 崩时印出可执行修复；红时不印（红的下一步是拍板）
- ⚠ **照着修复命令跑了一遍**：崩 1 → 崩 0，`verify_path` 回到 `RESULT OK 39/39`
- ⚠ 当前状态：**绿 6 / 红 2 / 崩 0**；产物年龄 3198 / 3056 秒（窗口 7200，⚗⚠⚴ 剩约 65 分钟）
- ⚠ 预登记以换行结尾 / 追加前后原文**逐字节未变** / **坏字 0**
- ⚠ **本节只改了 `status.py` 的输出；没改任何判据口径、没改 FINGERPRINT、没改产品**
"""


def main():
    before = PREREG.read_bytes()
    if not before.endswith(bytes([10])):
        print("[错误] 追加前文件不以换行结尾 —— 硬门，不追加")
        raise SystemExit(2)
    if before.decode("utf-8").count(chr(0xFFFD)):
        print("[错误] 追加前已有坏字 —— 硬门，不追加")
        raise SystemExit(2)

    sha_before = hashlib.sha256(before).hexdigest()
    n_before = before.decode("utf-8").count("\n")
    PREREG.write_text(before.decode("utf-8") + SECTION, encoding="utf-8")

    after = PREREG.read_bytes()
    txt = after.decode("utf-8")
    ok = after[:len(before)] == before
    print("=== 追加结果 ===")
    print(f"  原文 {len(before):,} bytes / {n_before:,} 行 / sha256 {sha_before[:16]}")
    print(f"  现文 {len(after):,} bytes / {txt.count(chr(10)):,} 行")
    print(f"  ⚠ 原文逐字节未变：{ok}")
    print(f"  ⚠ 以换行结尾：{after.endswith(bytes([10]))}")
    print(f"  ⚠ 坏字（原始字节层）：{txt.count(chr(0xFFFD))}")
    print(f"  ⚠ 修订 161 段仍在：{'## 修订 161 ' in txt}")
    print(f"  ⚠ 修订 162 段已在：{'## 修订 162 ' in txt}")
    if not ok or "## 修订 162 " not in txt:
        print("[错误] 追加未生效 —— 不许当成成功")
        raise SystemExit(2)


if __name__ == "__main__":
    main()