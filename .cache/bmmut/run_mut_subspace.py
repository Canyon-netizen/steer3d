#!/usr/bin/env python3
"""变异：证明 verify_subspace.mjs 有牙齿。

这块面板的价值全在三样「并排的东西」上，所以变异专打那三样 ——
每一条都会让页面**照样渲染、布局照样整齐**，只是读者再也看不到那把尺子。

M1 删掉「地板」栏        —— 0.86 看着漂亮，但那可能是判据的噪声水平
M2 只把**可见文案**写死  —— data-value 属性照旧（专打「文案撒谎、属性诚实」）
M3 删掉位置轴对照行      —— 「六条都塌了」和「装置测不出持续方向」分不开
M4 把下界写死成 4        —— 结论直接反过来（4 条就是全部），而页面看着正常

每条变异先回读自证产物真的变了，再 rebuild，再跑判据。
**编译不过的变异不算命中**（第一版 M3 写成 `{false ? (` 就是这么废掉的）。

用法：python3 .cache/bmmut/run_mut_subspace.py <M1|M2|M3|M4|BASE> <port>
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path("/Users/zhourui/code/steer3d")
SRC = ROOT / "frontend/components/SubspacePanel.tsx"
PRISTINE = ROOT / ".cache/bmmut/SubspacePanel.pristine.tsx"
JUDGE = ROOT / ".cache/browser_verify/verify_subspace.mjs"
FRONT = ROOT / "frontend"
BACKUP = ROOT / ".cache/bmmut/_mut_backup_sub.tsx"
TRASH = "/Users/zhourui/.minimax/bin/mavis-trash"

M1_OLD = '''              <div className="rounded bg-bg/30 px-1 py-0.5" data-guard={`${r.key}-floor`}>
                <div className="text-[8px] text-gray-600">地板（打乱后）</div>
                <div className="text-[11px] font-mono text-gray-400"
                     data-kind="floor" data-value={r.diagnostic.floor}>
                  {r.diagnostic.floor.toFixed(4)}
                </div>
              </div>
'''
M1_NEW = ""

# M2 只改可见文案，data-kind / data-value 全部照旧 —— 判据的「文字那半」必须红、
# 「属性那半」必须保持绿，这样才能证明判据确实分别长在两条渲染路径上。
M2_OLD = "                  {r.diagnostic.diagonal.toFixed(4)}"
M2_NEW = "                  {(0.9999).toFixed(4)} // MUT_M2"

# M3 **真删**掉位置轴对照行。
# 第一版只把 data-control-row 改成 "removed"、保留整块 ⇒ 判据 C1/C2 按
# data-control-delta="100" 那个 span 读，根本没查 data-control-row，
# 于是判据全绿 —— **变异没真的改变判据读的那条路径**。
# 教训与 M2 同族但方向相反：不是「判据漏了路径」，是「变异压根没落在路径上」。
M3_OLD = """      {/* 位置轴对照：没有它，「六条都塌」和「装置测不出持续」分不开 */}
      <div className="rounded border border-emerald-800/60 bg-emerald-900/10 p-1.5 mt-1.5"
           data-control-row="true"
           data-control-delta100={d.control.delta["100"]}>
        <p className="text-[9.5px] text-emerald-300/90 leading-snug">
          <b>装置阳性对照：{d.control.label}</b>
          {" "}Δ=0 <span className="font-mono">{d.control.delta["0"].toFixed(4)}</span> →{" "}
          Δ=100 <span className="font-mono" data-control-delta="100"
                        data-control-value={d.control.delta["100"]}>
            {d.control.delta["100"].toFixed(4)}
          </span>{" "}
          （<span className="font-mono">{d.control.decay_x20}×</span>，几乎不塌）
        </p>
        <p className="text-[8.5px] text-gray-500 mt-0.5 leading-snug">{d.control.note}</p>
      </div>
"""
M3_NEW = ""

M4_OLD = "<b className=\"text-amber-300\"> 至少 {h.readable_directions_lower_bound} 条 </b>"
M4_NEW = "<b className=\"text-amber-300\"> 4 条 </b>"

MUTS = {"M1": (M1_OLD, M1_NEW), "M2": (M2_OLD, M2_NEW),
        "M3": (M3_OLD, M3_NEW), "M4": (M4_OLD, M4_NEW)}


def restore():
    if PRISTINE.exists():
        shutil.copy2(PRISTINE, SRC)
    elif BACKUP.exists():
        shutil.copy2(BACKUP, SRC)


def build():
    bid = FRONT / ".next/BUILD_ID"
    if bid.exists():
        subprocess.run([TRASH, str(bid)], capture_output=True)
    r = subprocess.run(["npm", "run", "build"], cwd=FRONT, capture_output=True, text=True)
    return bid.exists(), (r.stdout + r.stderr)


def judge(port):
    import time
    import urllib.request
    srv = subprocess.Popen(["npx", "next", "start", "-p", str(port)], cwd=FRONT,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(40):
            try:
                if urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2).status == 200:
                    break
            except Exception:
                time.sleep(0.5)
        else:
            print(f"ABORT 端口 {port} 上的服务没起来")
            return 3, "no server"
        r = subprocess.run(["node", str(JUDGE)], cwd=ROOT, capture_output=True, text=True,
                           env={**__import__("os").environ, "BV_URL": f"http://127.0.0.1:{port}/"})
        return r.returncode, r.stdout + r.stderr
    finally:
        try:
            srv.kill()
        except Exception:
            pass


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "BASE"
    port = sys.argv[2] if len(sys.argv) > 2 else "10440"
    if not PRISTINE.exists():
        PRISTINE.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SRC, PRISTINE)
    restore()

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
            return 2
        what = {"M1": "删掉「地板」栏", "M2": "只把可见的对角文案写死成 0.9999（属性照旧）",
                "M3": "整块删掉位置轴对照行",
                "M4": "把下界写死成 4 条"}[which]
        print(f"{which} 施加：{what}；回读自证通过")
    else:
        print("用法：BASE | M1 | M2 | M3 | M4")
        return 2

    ok, log = build()
    if not ok:
        print("ABORT build 没落地 BUILD_ID")
        print(log[-2000:])
        restore()
        return 2
    print("build OK")

    code, out = judge(port)
    failed = [ln for ln in out.splitlines() if ln.startswith("[FAIL]")]
    print()
    for ln in failed:
        print("   " + ln[:160])
    red = code != 0
    print(f"\nRESULT {which}  {'RED' if red else 'GREEN'}  红在 {len(failed)} 条")
    if which == "BASE":
        print("BASE 必须 GREEN；若是 RED 说明基线本身有问题")
    elif not red:
        print("!! 变异没让判据变红 —— 判据在这一支上没有牙齿")
    return 0


if __name__ == "__main__":
    sys.exit(main())
