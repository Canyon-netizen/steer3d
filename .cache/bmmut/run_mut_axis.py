#!/usr/bin/env python3
"""变异：证明 verify_axis_readout.mjs 有牙齿。

判据全绿本身不说明判据有效。这一支把面板改成两种**看起来完全正常**的样子，
判据必须变红：

M1 删掉对照栏（每个格子里不再印「对照 x.xxx」）
   —— 页面照样渲染、布局照样整齐，只是读者再也看不到那把尺子。
M2 把状态硬编码成 measured
   —— 四行都印「已测到读出方向」，与产物矛盾，但外观无异。

每条变异先回读自证产物真的变了，再 rebuild，再跑判据。
判据必须红；红在**声明的判据**上才算命中。

用法：python3 .cache/bmmut/run_mut_axis.py <M1|M2|BASE>
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path("/Users/zhourui/code/steer3d")
SRC = ROOT / "frontend/components/AxisReadoutPanel.tsx"
PRISTINE = ROOT / ".cache/bmmut/AxisReadoutPanel.pristine.tsx"
JUDGE = ROOT / ".cache/browser_verify/verify_axis_readout.mjs"
FRONT = ROOT / "frontend"
BACKUP = ROOT / ".cache/bmmut/_mut_backup.tsx"

M2_OLD = "const st = STATUS_TEXT[a.status];"
# 2026-10-03 重新瞄准：页面上已没有 measured 状态了（confidence 降为
# tautological、caution 降为 shared_readout）。所以「四行都印已测」这个
# 变异已经造不出来 —— 改成**四行都印最强的那句**（tautological），
# 这与原来那句一样是「页面在替产物撒谎，且外观完全正常」。
M2_NEW = 'const st = STATUS_TEXT["tautological"]; // MUT_M2'
# 加强版：徽章、data-status、判定句三处一起撒谎。
# 第一版 M2 只改徽章，结果判据全绿 —— 因为 A2 读 data-status、A3 读判定句，
# 两者都不受徽章影响。**「页面给四行都印『已测』而判据通过」**，
# 所以现在三处一起改，这才是读者真正会看到的样子。
M2_STRONG_OLD = ('className={`text-[9px] px-1.5 py-0.5 rounded border ${st.cls}`}\n'
                  '                      data-status-label={st.label}>')
M2_STRONG_NEW = ('className={`text-[9px] px-1.5 py-0.5 rounded border ${st.cls}`}\n'
                  '                      data-status-label={st.label} data-lie={a.status}>')
M2_VERDICT_OLD = ('<p className="text-[9px] mt-1 leading-snug"\n'
                  '                 data-verdict={a.status}>\n'
                  '                {a.status === "tautological" ? (')
M2_VERDICT_NEW = ('<p className="text-[9px] mt-1 leading-snug"\n'
                  '                 data-verdict={"tautological"}>\n'
                  '                {"tautological" === "tautological" ? (')
# M2_VERDICT_OLD 里第一处已随上面 2026-10-03 的改动单独处理：
# 原来的锚点是 `a.status === "measured"`，现在分支顺序变了，重建如下。

# M3 只把**印出来的那个数**写死，data-spec-cos 属性照旧。
# 这是 M2 那次教训的翻版：判据 D4 原本只读 data-spec-cos，
# 所以「文案撒谎、属性诚实」是能骗过它的。所以 M3 专打这一条。
# （第一版 M3 写成 `{false ? (`，TS 直接编译失败 —— 编译不过的变异
#   根本没进页面，不算命中，已废弃。）
M3_OLD = '                            {v.toFixed(3)}'
M3_NEW = '                            {(0.3077).toFixed(3)} // MUT_M3'
# M4 把撤回声明换成**那句具体的谎**：「四条轴的读出方向均已独立验证」。
# 第一版写成 `{false && (`，TS 报 `'d' is possibly 'null'` 编译失败 ——
# 编译不过的变异根本没进页面，不算命中，已废弃。保留结构、只换文案，
# 既类型安全，又正好是读者会看到的那种撒谎。
M4_OLD = '<b>⚠ 已撤回的结论：</b>{d.headline.retraction_note}'
M4_NEW = '<b>归属检验：</b>四条轴的读出方向均已独立验证。'


def restore():
    if PRISTINE.exists():
        shutil.copy2(PRISTINE, SRC)
    elif BACKUP.exists():
        shutil.copy2(BACKUP, SRC)


def save_pristine():
    if not PRISTINE.exists():
        PRISTINE.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SRC, PRISTINE)


def build():
    bid = FRONT / ".next/BUILD_ID"
    if bid.exists():
        subprocess.run(["/Users/zhourui/.minimax/bin/mavis-trash", str(bid)],
                       capture_output=True)
    r = subprocess.run(["npm", "run", "build"], cwd=FRONT,
                       capture_output=True, text=True)
    return bid.exists(), (r.stdout + r.stderr)


def judge(port):
    # 自己起服务：沙箱禁信号，旧进程杀不掉，而对着一个**没起服务的端口**跑判据
    # 会让 A1 假红（state=undefined）—— 第一版就栽在这里，把它误当成变异生效。
    srv = subprocess.Popen(
        ["npx", "next", "start", "-p", str(port)], cwd=FRONT,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        import time
        import urllib.request
        for _ in range(40):
            try:
                if urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/", timeout=2).status == 200:
                    break
            except Exception:
                time.sleep(0.5)
        else:
            print(f"ABORT 端口 {port} 上的服务没起来")
            return 3, "no server"
        r = subprocess.run(
            ["node", str(JUDGE)],
            cwd=ROOT, capture_output=True, text=True,
            env={**__import__("os").environ, "BV_URL": f"http://127.0.0.1:{port}/"},
        )
        return r.returncode, r.stdout + r.stderr
    finally:
        try:
            srv.kill()
        except Exception:
            pass


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "BASE"
    port = sys.argv[2] if len(sys.argv) > 2 else "10341"
    save_pristine()
    restore()

    if which == "BASE":
        print("BASE: 原始产物")
    elif which == "M1":
        s = SRC.read_text()
        pat = re.compile(
            r'\n\s*<div className="text-\[8\.5px\] font-mono text-gray-600"\n'
            r'\s*data-control-cos=\{c\.control_cos \?\? ""\}>\n'
            r'\s*对照 \{\(c\.control_cos \?\? 0\)\.toFixed\(3\)\}\n'
            r'\s*</div>')
        s2, n = pat.subn("", s)
        if n != 1:
            print(f"ABORT 对照栏没匹配到（n={n}），变异未施加")
            return 2
        SRC.write_text(s2)
        shutil.copy2(SRC, BACKUP)
        # 回读自证：产物里必须真的没有那个 data-control-cos 了
        back = SRC.read_text()
        if "对照 {" in back and "data-control-cos" in back:
            print("ABORT 施加后回读，对照栏还在 —— 变异没生效")
            return 2
        print(f"M1 施加：删掉对照栏（替换 {n} 处）；回读自证 data-control-cos 已消失")
    elif which in ("M2", "M2S"):
        s = SRC.read_text()
        strong = which == "M2S"
        if M2_OLD not in s:
            print("ABORT 锚点没找到，变异未施加")
            return 2
        s2 = s.replace(M2_OLD, M2_NEW, 1)
        if strong:
            if M2_STRONG_OLD not in s2 or M2_VERDICT_OLD not in s2:
                print("ABORT 加强版的锚点没找到")
                return 2
            s2 = s2.replace(M2_STRONG_OLD, M2_STRONG_NEW, 1)
            s2 = s2.replace(M2_VERDICT_OLD, M2_VERDICT_NEW, 1)
        SRC.write_text(s2)
        shutil.copy2(SRC, BACKUP)
        back = SRC.read_text()
        if M2_NEW not in back:
            print("ABORT 施加后回读，变异不在")
            return 2
        if strong and (M2_VERDICT_NEW not in back or M2_STRONG_NEW not in back):
            print("ABORT 施加后回读，加强版没全上")
            return 2
        what = ("徽章+data-status+判定句三处一起硬编码为 tautological" if strong
                else "只硬编码徽章")
        print(f"{which} 施加：{what}；回读自证通过")
    elif which in ("M3", "M4"):
        s = SRC.read_text()
        old = M3_OLD if which == "M3" else M4_OLD
        rep = M3_NEW if which == "M3" else M4_NEW
        if old not in s:
            print(f"ABORT {which} 锚点没找到，变异未施加")
            return 2
        s2 = s.replace(old, rep, 1)
        SRC.write_text(s2)
        shutil.copy2(SRC, BACKUP)
        back = SRC.read_text()
        if rep not in back or old in back:
            print(f"ABORT {which} 施加后回读，变异没生效")
            return 2
        what = ("把归属检验的可见文案全部写死成 0.308（data 属性照旧）" if which == "M3"
                else "把撤回声明替换成「四条轴的读出方向均已独立验证」")
        print(f"{which} 施加：{what}；回读自证通过")
    else:
        print(f"未知变异 {which}")
        return 2

    ok, log = build()
    if not ok:
        print("ABORT build 没落地 BUILD_ID")
        print(log[-2500:])
        restore()
        return 2
    print("build OK（BUILD_ID 已落地）")

    code, out = judge(port)
    red = code != 0
    failed = [ln for ln in out.splitlines() if ln.startswith("[FAIL]")]
    print()
    print(out[-3000:])
    print()
    print(f"RESULT {which}  {'RED' if red else 'GREEN'}  "
          f"红在 {len(failed)} 条：")
    for ln in failed:
        print("   " + ln[:150])
    if which == "BASE":
        print("BASE 必须 GREEN；若是 RED 说明基线本身有问题")
    else:
        if not red:
            print("!! 变异没让判据变红 —— 判据在这一支上没有牙齿")
        else:
            print(f"!! 命中检查：红点是否包含该变异声明的判据")
    return 0


if __name__ == "__main__":
    sys.exit(main())
