"""把 E 组的新判据（E2/E3/E4）写进 `verify_path.mjs`。

⚠⚠⚴ **判据笔**：按修订 118/124 的规矩，**判据与取数严格分离** ——
本脚本只改判据文件，**单独一笔 commit**，⚠ 不与取数/落地混在一起。

⚠⚠⚴⚠⚴ 三条前置硬门（任何一条不过就 exit 2，**不改**）：
  ① 目标文件的 sha256 必须等于预期值 ⇒ 防止改到别的版本
  ② E 组那一段必须**逐字**等于本脚本读到的原文（**行首锚点**，不用 indexOf）
     ⚠⚠⚴ 纪律：`src.index(...)` 会命中**注释里**的同名文本（修订 134 踩过）
  ③ 改完 `node --check` + U+FFFD 守卫必须过（挂在 **Python 解析后**那一层，修订 135）

⚠⚠⚴ **为什么 E2/E3/E4 长这样**（依据全在修订 140 的实测，不是设计偏好）：
  · E1 判 `typeof renderPathPanel`，而它**在「数据在」与「数据缺」下都是 function**
    ⇒ 分不开 ⇒ E1 是「够得着但没核名字说的那件事」那一档
  · 两个空值分支都**真的会出可见文案**（实测 94 字 / 78 字）
  · ⇒ 把页面**拨到那两种情形**各一次，核**可见文案**，核完**原样还原**
  · ⚠ `data-pathstate` 只作**交叉核对**；**主体断言是可见文字**
    （纪律：判据主体必须是读者看到的可见文案，data-* 只证明「节点在」）
"""

import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / ".cache/browser_verify/verify_path.mjs"
EXPECT_SHA = "272929ca57e19d8a"          # ⚠ 前置门①：防改错版本
BACKUP = ROOT / ".cache/mutbak/verify_path.pre_e2.mjs"

OLD = """// ---- E 组：数据没载入时必须**明说**，不能静默消失 -----------------------
const missing = JSON.parse(await page.eval(`(() => {
  const savePath = window.__pathSaved;
  return JSON.stringify({ hasHandler: typeof renderPathPanel === 'function' });
})()`));
check('E1 渲染函数存在（缺数据时才有人喊缺）', missing.hasHandler, JSON.stringify(missing));
"""

NEW = """// ---- E 组：数据没载入时必须**明说**，不能静默消失 -----------------------
const missing = JSON.parse(await page.eval(`(() => {
  const savePath = window.__pathSaved;
  return JSON.stringify({ hasHandler: typeof renderPathPanel === 'function' });
})()`));
check('E1 渲染函数存在（缺数据时才有人喊缺）', missing.hasHandler, JSON.stringify(missing));

// ⚠⚠⚴⚠⚴ E2/E3/E4（修订 141 新增）。E1 只证明「函数在」，**证不了它名字里那半句**：
//   实测（修订 140）「typeof renderPathPanel」在「数据在」与「数据缺」两种情形下
//   **都是「function」** ⇒ 分不开 ⇒ 这就是 E1 落「第四档」的**机制**（不是它的描述）。
//   ⇒ 这里把页面**拨到缺数据的两种情形**各一次，核**读者看得见的文案**：
//     ① 整份 path_readout 取不到 → 屏上须说「逐步路径数据未载入」
//     ② 数据在、当前这道题没记录 → 屏上须说「这份…里没有题目…只覆盖 N 道题」
//   ⚠⚠⚴ **两个情形都要测** —— 只测一个就是「只验了一半」。
//   ⚠「data-pathstate」**只作交叉核对**（证明节点在）；**主体断言是可见文字**。
//   ⚠⚠⚴ 拨完必须**原样还原**：不还原会污染紧随其后的变异台（M0–M2）。
//   ⚠⚠⚴⚠⚴ **下面这段注释里一个字都不能出现反引号**：它整体在 page.eval 的
//     模板字面量内部，反引号会**提前终止模板** ⇒ 整条判据崩在语法错误上
//     （修订 133/134 踩过；派生台会剥注释里的反引号，但主文件不会）。
const said = JSON.parse(await page.eval(`(async () => {
  const wrap = document.querySelector('#pathWrap');
  const savePath = S.path;
  const saveText = wrap ? wrap.innerText : '';
  const pid = (S.pm && S.pm.pairs && S.pm.pairs[S.pi]) ? S.pm.pairs[S.pi].id : null;
  const grab = () => {
    wrap.innerHTML = renderPathPanel();
    const b = wrap.querySelector('[data-pathblock]');
    return { text: (b ? (b.innerText || '') : ''),
             state: (b ? (b.getAttribute('data-pathstate') || '') : '(无块)') };
  };
  const out = {};
  try{
    // ① 整份数据取不到
    S.path = null;
    out.noData = grab();
    S.path = savePath;
    // ② 数据在、这一题没记录
    const saved = (pid && savePath && savePath.problems) ? savePath.problems[pid] : null;
    if (saved) delete savePath.problems[pid];
    out.noProblem = grab();
    if (saved) savePath.problems[pid] = saved;
    // 还原面板，并**自证还原成功**
    wrap.innerHTML = renderPathPanel();
    out.restoredOK = (wrap.innerText === saveText);
    out.pathIntact = (S.path === savePath);
    out.beforeLen = saveText.length;
    out.afterLen = wrap.innerText.length;
  }catch(e){
    // ⚗⚠⚴⚠⚴ **页内失败必须变成一条红，不能变成掀桌。**
    //   D5 的教训（修订 134 §134.5）：「#tabXY.click()」没有空值保护，
    //   元素一被删就抛异常 ⇒ 脚本直接崩、**压根不打印 RESULT** ⇒ 判决变成一段堆栈。
    //   ⇒ 这里 catch 住并把消息带出去，交给下面的 check 判红。
    out.err = String((e && e.message) || e);
  }
  return JSON.stringify(out);
})()`));
const saidNoData = !said.err && said.noData.text.indexOf('未载入') >= 0
  && said.noData.text.indexOf('path_readout.json') >= 0;
const saidNoProblem = !said.err && said.noProblem.text.indexOf('没有题目') >= 0
  && said.noProblem.text.indexOf('逐步路径只覆盖') >= 0;
const d0 = said.err ? '页内失败：' + said.err
  : `state=${said.noData.state} ${said.noData.text.length} 字`;
const d1 = said.err ? '页内失败：' + said.err
  : `state=${said.noProblem.state} ${said.noProblem.text.length} 字`;
check('E2 整份路径数据取不到时，屏上明说缺什么（可见文案）', saidNoData, d0);
check('E3 这一题没记录时，屏上明说并给出换题指引（可见文案）', saidNoProblem, d1);
// ⚗⚠⚴ E4 是**台架自检**，不是产品性质：拨完必须原样还原，否则污染后面的变异台。
check('E4 【台架自检】上面两次拨动已原样还原',
  !said.err && said.pathIntact && said.restoredOK,
  said.err ? '页内失败：' + said.err
    : `pathIntact=${said.pathIntact} ${said.beforeLen} → ${said.afterLen} 字`);
"""


def die(msg):
    print("[硬门] " + msg)
    raise SystemExit(2)


def main():
    raw = SRC.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()[:len(EXPECT_SHA)]
    if sha != EXPECT_SHA:
        die(f"目标文件 sha256 = {sha}，期望 {EXPECT_SHA} —— 不改")
    text = raw.decode("utf-8")

    # ⚠⚠⚴ 前置门②：**逐字**匹配（行首锚点），且必须**恰好出现一次**
    n = text.count(OLD)
    if n != 1:
        die(f"E 组那段原文出现 {n} 次，期望恰好 1 次 —— 不改")
    BACKUP.write_bytes(raw)
    print(f"已备份原文件 → {BACKUP.relative_to(ROOT)}")

    out = text.replace(OLD, NEW)
    SRC.write_text(out, encoding="utf-8")

    # ⚠⚠⚴ 前置门③：U+FFFD 挂在 **Python 解析后**那一层（修订 135 §135.7）
    parsed = SRC.read_text(encoding="utf-8")
    bad = parsed.count(chr(0xFFFD))
    if bad:
        SRC.write_bytes(raw)
        die(f"改后有 {bad} 个坏字 —— 已回滚")
    print(f"⚠ 坏字（Python 解析后）：{bad}")

    rc = subprocess.run(["node", "--check", str(SRC)], capture_output=True, text=True)
    if rc.returncode != 0:
        SRC.write_bytes(raw)
        die("node --check 崩 —— 已回滚\n" + rc.stderr[:600])
    print("⚠ node --check 通过")

    # ⚠⚠⚴ 反引号纪律：本文件全文件反引号总数**没变**（注入块自带，E2 块里一个都没有）
    print(f"⚠ 全文件反引号数：{text.count(chr(96))} → {out.count(chr(96))}")
    print(f"⚠ 文件大小：{len(raw):,} → {len(out.encode('utf-8')):,} bytes")
    print(f"⚠ 行数：{text.count(chr(10))} → {out.count(chr(10))}")


if __name__ == "__main__":
    main()