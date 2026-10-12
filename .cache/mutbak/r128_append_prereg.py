#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 128 追加器 —— 纯披露：静态产物页 `verify_path` 的 B 组牙齿验证。

纪律：原文只追加不改写；追加前断言以 '\\n' 结尾；
追加后断言原文前缀逐字节未变；断言 U+FFFD == 0。
"""
import hashlib
import os

P = '/Users/zhourui/code/steer3d/.cache/xcheck/R6_RERUN_PREREG.md'

SECTION = """
## 修订 128 —— 静态产物页 `verify_path` 的 B 组牙齿验证：15/15；⚗⚗ 撤回本台首版自己撒的一个谎

### 128.0 为什么新写一台，而不是复用 `r125_k2_teeth.mjs`

⚠⚠⚴⚠ 修订 127 实测：那台的 SPEC 是照 **React 页**的 `[data-*]` 写的，
而 `verify_path.mjs` 用 `LAT_URL` 跑的是**静态产物页**
（`#pathWrap` / `[data-patht]` / `[data-pathfork]` / `[data-pathblock]` 这套）。
⇒ ⚠ **两个页面的 DOM 结构完全不同，换 URL 复用会让 SPEC 全部失效。**

⚠ 于是新写 `.cache/mutbak/r128_k2_latent_teeth.mjs`，
只做 **B 组 13 条 needle 判据**（`verify_path.mjs:138-148`）：

```javascript
const phrases = [
  ['B1 抬头说清这屏讲什么', '每一步各自在考虑哪几个词'],
  …
  ['B13 印出共享前缀的原文', "let's try to solve"],
];
for (const [name, needle] of phrases)
  check(name, T.includes(needle), `找不到「${needle}」`);
```

`T = document.querySelector('#pathWrap').innerText`（`:97` / `:114` / `:117`）
⇒ 13 条**全是「屏上可见文字里有没有这一句」** ⇒ 天然属 PAGE_TEXT 桶，
且**各自只锁一个 needle** ⇒ 「把这个 needle 从屏上抹掉」是最干净的定向扰动。

⚠⚠ 这一族是静态产物页 36 条判据里**从未验过牙齿**的部分中
**信息量最高的一批**：全过只说明没抓到现行（修订 88 的老结论），
**新判据上线前必须扰动**。

### 128.1 ✅ 结果：RESULT PASS 15/15

基线：`#pathWrap.innerText` **1267 字**，13 条 needle 命中 **13/13**。
定向扰动：13/13 条 needle **已从屏上抹掉** ⇒ 谓词 `T.includes` 转 false
⇒ 对应判据**全部转红**。
收尾：全部扰动跑完后再跑一次未扰动基线 ⇒ **13/13 命中、1267 字**
⇒ ⚠ **扰动没有把页面弄坏**。

⚠⚠⚠⚠⚴ **这一条同时否掉了一个「预期中的坑」**：
修订 126 在 React 页上实测到「动容器 `innerText` 会换掉整棵子树，
新节点不被 React 持有 ⇒ 后续 spec 读到被冲掉的结构」。
⚠ 静态产物页是**手写 HTML、无 React reconcile**
⇒ 实测容器级扰动**不会**被冲掉（收尾基线全绿即为证据）。
⚠⚠ 但**这不能推广**：同一手法在 React 页上仍然要排到最后 + 重载。

⚠⚠⚠⚠⚴⚠⚴ **因此本页的 49 条里有 13 条第一次拿到牙齿证据**：
`verify_path` B 组 13 条 ✅ · `verify_patch` 13 条 ✅（实跑 13/13，
但 ⚠⚠ **K2 扰动尚未做**）。
⚠⚠⚴⚠⚴ **其余 23 条（path 的 A/C/D 组）仍属「未验牙齿」**，
⚠ 本节**不给它们任何红绿结论**。

### 128.2 ⚗⚗⚗⚗ 撤回本台首版自己撒的一个谎

首版输出打印「**13 条 needle 基线命中 12/12**」，
而顶部 `[自证]` 只列到 **B1–B12**（12 条）——
⚠⚠⚴⚠⚴ **分子分母都不是真的**。

**根因（已当场用判据原文核实）**：`verify_path.mjs:138` 那一行**确实有 B13**，
needle 是 `"let's try to solve"` ——
⚠⚠⚴ **双引号串里裹着单引号**，而本台原来的抽取正则
`(?:[^'"\\]|\\.)*` **两种引号都排除** ⇒ 整行匹配失败、B13 被**静默丢掉**。

⚠⚠⚴⚠⚴⚠⚴ **真正危险的不是漏一条，是那句自相矛盾的输出看起来完全正常**：
若不是当场对着判据文件数 `phrases` 行数（13），
那个「12/13」会被当成「**有一条基线就红**」发出去，
而真相是**解析器坏了**。

⚠⚠⚴⚠⚴⚠⚴ **这是本项目第三次「仪器自己给自己发绿」**
（修订 127 的四级转义假绿、修订 127 的索引部分丢、这次的正则漏条）。
⚠ **三次全部靠「当场拿源码/判据原文复核」抓住，没有一次是靠仪器自己报错。**

⇒ ⚠⚴⚴⚴ **固化（三条都加进本台）**：

1. ⚠⚠⚴ **不自己写正则去猜引号配对** —— 改成**引号感知的扫描**
   （扫到哪个引号就从哪个闭合，转义按 `\` 逐字符处理）。
2. ⚠⚠⚴⚠ **反漂移守卫要有下半道**：抽取条数必须**等于**判据文件里
   `[` 开头的行数，少一条就 `exit 2` 拒绝发布（只报数，不下结论）：
   ```
   [自证] 判据文件里 phrases 13 行 · 本台解析出 13 条
   ```
3. ⚠⚠⚴ **分母一律从 `SPECS.length` 取，禁止写死。**
   ⚠ 首版把 13 写死，于是打印出「命中 12/13」这种自相矛盾的数；
   修后基线为真的 **13/13**。

### 128.3 本节口径

- ⚠ K2 页面实例扰动证明「**判据读的就是读者看到的那句话**」；
  ⚠ **不**证明「产品写错时一定红」——那要改源码 + 重建。
- ⚠ 本节**没有改任何判据、没有改任何产品、没有碰任何产物**。
- ⚠ 本节**不声称** `verify_path` 36 条已全部验过：只有 B 组 13 条有牙齿证据。
"""


def main():
    assert os.path.exists(P), '预登记不存在'
    with open(P, 'rb') as f:
        before = f.read()
    assert before.endswith(b'\n'), '原文件不以 \\n 结尾，拒绝追加'
    n_before = before.count(b'\n')
    h_before = hashlib.sha256(before).hexdigest()

    with open(P, 'ab') as f:
        f.write(SECTION.encode('utf-8'))

    with open(P, 'rb') as f:
        after = f.read()
    assert after[:len(before)] == before, '原文前缀被改动 —— 违反「只追加」'
    assert hashlib.sha256(after[:len(before)]).hexdigest() == h_before
    assert after.endswith(b'\n'), '追加后不以 \\n 结尾'
    assert after.decode('utf-8').count('\ufffd') == 0, '含 U+FFFD'

    print('✅ 已追加修订 128')
    print('   原文行数 %d → 全文 %d（+%d）' % (
        n_before, after.count(b'\n'), after.count(b'\n') - n_before))
    print('   原文字节 %d → 全文 %d（+%d）' % (
        len(before), len(after), len(after) - len(before)))
    print('   原文前缀 sha256 追加前后一致：%s' % h_before[:16])
    print('   U+FFFD = %d' % after.decode('utf-8').count('\ufffd'))


if __name__ == '__main__':
    main()
