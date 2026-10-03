#!/usr/bin/env python3
"""变异：证明 verify_heldout.mjs 有牙齿。

这块面板守的是三样并排的东西，每条变异都让页面**照样渲染、布局照样整齐**，
只是读者再也看不到那把尺子，或者看到的结论是反的。

M1 倍数**文案**写死成 110.0×，data-value 属性照旧
   —— 专打「文案撒谎、属性诚实」。期望：B 组文字那半红、属性那半绿。
M2 倍数改用**共用分母** 0.0067（属性+文案都错）
   —— 这正是 §4.9 文档里我自己犯的错（把三条地板混着当分母），
     写在这里就是为了让判据 B3 必须能抓住它。
M3 把「未测」渲染成 Δ=20 0.0000 并挂上 data-value={0}
   —— 「没测」与「测出零」在页面上变成同一个数。
M4 把 same_direction 的**文案**也标成「新方向（干净）」，属性照旧
   —— 四条本来不是新方向的量被说成是新方向，页面看不出破绽。
M5 把自我纠正的**结论反转**成「是两条不同的观测量」，所有数字照旧
   —— 最危险的一类：数值全对，结论反了。
M6 整块删掉自我纠正
   —— 读者就不知道自己错过过一个「新家族」。

每条变异：先回读自证产物真的变了 → rebuild → 跑判据。
**编译不过的变异不算命中。**

还原自证：restore() 之后比对 SRC 与 PRISTINE 的 sha256。
上一版 runner 的收尾校验是「刚还原完就读两个文件比相等」—— 那是**同义反复**，
必然相等。这一版比的是快照那一刻就固定下来的常量。

用法：python3 .cache/bmmut/run_mut_heldout.py <M1|M2|M3|M4|M5|M6|BASE> <port>
"""
import hashlib
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path("/Users/zhourui/code/steer3d")
SRC = ROOT / "frontend/components/HeldoutPanel.tsx"
PRISTINE = ROOT / ".cache/bmmut/HeldoutPanel.pristine.tsx"
JUDGE = ROOT / ".cache/browser_verify/verify_heldout.mjs"
FRONT = ROOT / "frontend"
BACKUP = ROOT / ".cache/bmmut/_mut_backup_heldout.tsx"
TRASH = "/Users/zhourui/.minimax/bin/mavis-trash"


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


# --- M1：只改文案，属性照旧 ---
M1_OLD = "                  {t.ratio.toFixed(1)}×"
M1_NEW = "                  {(110).toFixed(1)}× // MUT_M1"

# --- M2：属性与文案都用共用分母（= 真实犯过的错）---
M2_OLD = '''                <span className="font-mono text-amber-300"
                      data-kind="ratio" data-value={t.ratio}>
                  {t.ratio.toFixed(1)}×
                </span>'''
M2_NEW = '''                <span className="font-mono text-amber-300"
                      data-kind="ratio" data-value={Math.abs(t.rho) / 0.0067}>
                  {(Math.abs(t.rho) / 0.0067).toFixed(1)}×
                </span>'''

# --- M3：未测 → 0.0000 ---
# 第一版把条件本身换成 `{false ? ... : ...}`，**编译不过**：
# TS 靠 `r.rho_delta20 === null` 把 `number | null` 窄化成 `number`，
# 条件没了，`: ` 分支里的 `.toFixed` 就在 `number | null` 上报错。
# 编译失败的变异不算命中 —— 改成保留三元结构、只换 null 分支渲染什么。
M3_OLD = '''                  /* 未测就写「未测」，绝不能渲染成 0.0000 —— 那会把
                     「没测」与「测出零」混成一个数。判据专门查这一格。 */
                  <span className="text-gray-600" data-kind="delta20-missing">
                    Δ=20 未测
                  </span>'''
M3_NEW = '''                  /* MUT_M3：把「未测」渲染成 0.0000 —— 「没测」与「测出零」同形 */
                  <span className="font-mono text-gray-500"
                        data-kind="delta20" data-value={0}>
                    Δ=20 {(0).toFixed(4)}
                  </span>'''

# --- M4：判定文案撒谎，属性照旧 ---
M4_OLD = '  same_direction: "同一个方向",'
M4_NEW = '  same_direction: "新方向（干净）", // MUT_M4'

# --- M5：结论反转，数字全对 ---
M5_OLD = "          —— <b>就是同一个观测量</b>，我却当成「新家族」提交了。"
M5_NEW = "          —— <b>是两条不同的观测量</b>，我原先的怀疑没有根据。 // MUT_M5"

# --- M6：整块删掉自我纠正 ---
M6_OLD = '''      {/* ③ 自我纠正：我自己把同一个量当成了新家族 */}
      <div className="rounded border border-amber-800/60 bg-amber-900/10 p-1.5 mb-1.5"
           data-block="selfdup"
           data-selfdup-verdict={sd.verdict}
           data-selfdup-same={sd.pooled.same_step}
           data-selfdup-lag1={sd.pooled.lag1}
           data-selfdup-per-traj={sd.per_traj_mean.same_step}
           data-selfdup-n-traj={sd.n_traj}>
        <p className="text-[9.5px] text-amber-300/90 leading-snug">
          <b>③ 仪器抓到我的一个设计失误：</b>
          「本步发出的 token 含数字」与「本步记录的 top-1 是数字」
          同一步相关 <span className="font-mono" data-selfdup-cell="same">
            {sd.pooled.same_step.toFixed(4)}
          </span>
          ，而与错开一步只有{" "}
          <span className="font-mono" data-selfdup-cell="lag1">
            {sd.pooled.lag1.toFixed(4)}
          </span>{" "}
          —— <b>就是同一个观测量</b>，我却当成「新家族」提交了。
        </p>
        <p className="text-[8.5px] text-gray-500 mt-0.5 leading-snug">
          对照口径：逐轨迹算再平均 同一步{" "}
          <span className="font-mono" data-selfdup-cell="per-traj">
            {sd.per_traj_mean.same_step.toFixed(4)}
          </span>
          （{sd.per_traj_mean.n_used}/{sd.n_traj} 条轨迹有效）
          —— 与整段拼接差 {Math.abs(sd.pooled.same_step - sd.per_traj_mean.same_step).toFixed(4)}
          ，所以它不是跨轨迹拼接造出来的伪影。
        </p>
      </div>
'''
M6_NEW = ""

# --- M7：把「最强对手」的标签写长 + 不换行 ⇒ 内容溢出被裁 ---
# 这一条专打截图打脸过的那类缺陷：数值仍在 DOM 里、判据的数值断言仍全绿，
# 但侧栏太窄，读者**根本看不到完整的那一格**。只有 F 组能抓住。
M7_OLD = '''                <span className="font-mono text-orange-300/80"
                      data-kind="worst-other" data-value={r.worst_other_value}>
                  最强对手 {r.worst_other}
                </span>'''
M7_NEW = '''                <span className="font-mono text-orange-300/80 whitespace-nowrap"
                      data-kind="worst-other" data-value={r.worst_other_value}>
                  最强对手（同一张表里相关系数最高的另一个观测量）{r.worst_other}
                </span>'''

MUTS = {
    "M1": (M1_OLD, M1_NEW),
    "M2": (M2_OLD, M2_NEW),
    "M3": (M3_OLD, M3_NEW),
    "M4": (M4_OLD, M4_NEW),
    "M5": (M5_OLD, M5_NEW),
    "M6": (M6_OLD, M6_NEW),
    "M7": (M7_OLD, M7_NEW),
}
WHAT = {
    "M1": "倍数**文案**写死成 110.0×（data-value 属性照旧）",
    "M2": "倍数改用共用分母 0.0067（属性+文案都错）",
    "M3": "「未测」渲染成 Δ=20 0.0000 并挂 data-value={0}",
    "M4": "same_direction 的**文案**也标成「新方向（干净）」（属性照旧）",
    "M5": "自我纠正的**结论反转**成「是两条不同的观测量」（数字全对）",
    "M6": "整块删掉自我纠正",
    "M7": "「最强对手」标签写长且不换行 ⇒ 内容溢出被裁（数值断言仍全绿）",
}


def restore():
    """还原并自证。比的是快照那一刻固定下来的 sha，不是「刚还原完的两个文件」
    —— 后者是同义反复，必然相等。"""
    if PRISTINE.exists():
        shutil.copy2(PRISTINE, SRC)
    elif BACKUP.exists():
        shutil.copy2(BACKUP, SRC)
    else:
        raise SystemExit("ABORT 既没有 pristine 也没有 backup，无从还原")
    if PRISTINE.exists() and sha(SRC) != sha(PRISTINE):
        raise SystemExit("ABORT 还原后 sha256 与 pristine 不一致 —— 还原本身坏了")
    return sha(SRC)


def build():
    bid = FRONT / ".next/BUILD_ID"
    if bid.exists():
        subprocess.run([TRASH, str(bid)], capture_output=True)
    r = subprocess.run(["npm", "run", "build"], cwd=FRONT, capture_output=True, text=True)
    return bid.exists(), (r.stdout + r.stderr)


def judge(port):
    srv = subprocess.Popen(["npx", "next", "start", "-p", str(port)], cwd=FRONT,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                if urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2).status == 200:
                    break
            except Exception:
                time.sleep(0.5)
        else:
            print(f"ABORT 端口 {port} 上的服务没起来")
            return 3, "no server"
        r = subprocess.run(["node", str(JUDGE)], cwd=ROOT, capture_output=True, text=True,
                           env={**os.environ, "BV_URL": f"http://127.0.0.1:{port}/"})
        return r.returncode, r.stdout + r.stderr
    finally:
        try:
            srv.kill()
        except Exception:
            pass


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "BASE"
    port = sys.argv[2] if len(sys.argv) > 2 else "10470"
    if not PRISTINE.exists():
        PRISTINE.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SRC, PRISTINE)
    base_sha = restore()
    print(f"pristine sha256 {base_sha[:16]}")

    if which == "BASE":
        print("BASE: 原始产物")
    elif which in MUTS:
        old, new = MUTS[which]
        s = SRC.read_text()
        if old not in s:
            print(f"ABORT {which} 锚点没找到，变异未施加")
            return 2
        s2 = s.replace(old, new, 1)
        SRC.write_text(s2)
        shutil.copy2(SRC, BACKUP)
        back = SRC.read_text()
        if new not in back or old in back:
            print(f"ABORT {which} 施加后回读，变异没生效")
            restore()
            return 2
        print(f"{which} 施加：{WHAT[which]}；回读自证通过（源文件确实变了）")
    else:
        print("用法：BASE | M1 | M2 | M3 | M4 | M5 | M6")
        return 2

    ok, log = build()
    if not ok:
        print("ABORT build 没落地 BUILD_ID —— 编译失败的变异不算命中")
        print(log[-1500:])
        restore()
        return 2
    print("build OK")

    code, out = judge(port)
    failed = [ln for ln in out.splitlines() if ln.startswith("[FAIL]")]
    total = [ln for ln in out.splitlines() if ln.startswith("[PASS]") or ln.startswith("[FAIL]")]
    # 「一条都没跑起来」与「跑起来全绿」在 returncode 上长得一样（都是 0 vs 非 0，
    # 但前者常常是模块级语法错误 ⇒ 干脆没有输出）。第一版就撞上过一次：
    # 判据里在模板字符串**内部**写了反引号，模板提前结束，node 直接 SyntaxError，
# 于是报成「红在 0/0 条」——看起来像变异生效，其实是装置根本没跑。
    if not total:
        print("ABORT 判据一条都没跑起来 —— 装置故障，不是判红")
        print(out[-2000:])
        return 3
    print()
    for ln in failed:
        print("   " + ln[:170])
    red = code != 0
    print(f"\nRESULT {which}  {'RED' if red else 'GREEN'}  红在 {len(failed)}/{len(total)} 条")
    if which == "BASE":
        print("BASE 必须 GREEN；若是 RED 说明基线本身有问题")
    elif not red:
        print("!! 变异没让判据变红 —— 判据在这一支上没有牙齿")
    print(f"提示：本轮结束后源码处于变异态，提交前必须显式复跑 BASE（port 换新的）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
