#!/usr/bin/env python3
"""变异：证明 verify_ladder.mjs 有牙齿 —— 尤其「阶梯不许被画圆」。

这一块最危险的失败模式不是画错某一格，而是**画得比事实乐观**：
把 L5（0 条可注入轴）标成 done，或者把「未测」写成「实测为 0」。

| 变异 | 改坏的地方 | 必须变红的判据 |
|---|---|---|
| P1 | L5 的状态从 missing 改成 done（「差一点就到了」） | **L4** |
| P2 | L2 的条数写死成 20（产物是 14），属性照旧 | L3 / L5 |
| P3 | 删掉「不能回答」那半 | L9 |
| P4 | 把「未测」改成「实测为 0」 | **L8** |

用法：python3 run_mut_ladder.py <BASE|P1|P2|P3|P4> <port>
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
PANEL = ROOT / "frontend/components/EvidenceLadderPanel.tsx"
PRISTINE = ROOT / ".cache/bmmut/EvidenceLadderPanel.pristine.tsx"
JUDGE = ROOT / ".cache/browser_verify/verify_ladder.mjs"
FRONT = ROOT / "frontend"
TRASH = "/Users/zhourui/.minimax/bin/mavis-trash"

MUTS = {
    # P1：「画圆」的**摘要入口** —— 把最高级写死成 L6。
    # ⚠ 第一版改成给 STATE_TXT 加一个重复的 `missing: "有"` 键，
    #   那是 TS 重复键、**编译不过** —— 而编译失败的变异不算命中，
    #   差点被当成「判据抓不住」。写死属性才是合法且真正改变行为的。
    "P1": ('         data-max-level={d.max_level_reached}',
           '         data-max-level="L6"  /* MUT_P1 摘要行画圆 */'),
    # P2：写死 L2 的条数。属性 data-rung-here 照旧，只有可见文字错。
    "P2": ('            <div className="text-[9.5px] text-gray-400 leading-snug mt-0.5 pl-[4.4rem]">\n'
           '              本项目：<span className="font-mono">{r.here}</span>\n'
           '            </div>',
           '            <div className="text-[9.5px] text-gray-400 leading-snug mt-0.5 pl-[4.4rem]">\n'
           '              本项目：<span className="font-mono">20 条  {/* MUT_P2 */}</span>\n'
           '            </div>'),
    # P3：删掉「不能回答」那半 —— 只留能回答的一半。
    #     ⚠ 替换成空串的话就没有 marker 可查了，ABORT 判据无从下手
    #     （第一版就这么把自己坑了）。留一行带 marker 的空注释。
    "P3": ('        <p className="text-[9.5px] text-gray-400 leading-relaxed" data-not-answerable>\n'
           '          <b className="text-red-300">不能回答：</b>\n'
           '          {d.not_answerable.join("；")}。\n'
           '        </p>',
           '        {/* MUT_P3 删掉了「不能回答」那半 */}\n'),
    # P4：把「未测」说成「实测为 0」—— 这两个是相反的意思
    "P4": ('{d.overreach_numbers.note}。', '{String("实测为 0")}。  {/* MUT_P4 */}'),
    # P5：「画圆」的**单行入口** —— 把「没有」印成「有」。
    #     它**不动** data-rung-state、也**不动** MARK（破折号照旧），
    #     所以只查状态/标记的判据会照样绿。这条专打那个漏洞。
    "P5": ('  missing: "没有",', '  missing: "有",  /* MUT_P5 单行画圆 */'),
}
EXPECT = {"P1": ["L1", "L1b"], "P2": ["L3"], "P3": ["L9"], "P4": ["L8"],
          "P5": ["L4"]}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def restore():
    if not PRISTINE.exists():
        raise SystemExit("ABORT 没有 pristine 快照，无从还原")
    shutil.copy2(PRISTINE, PANEL)
    if sha(PANEL) != sha(PRISTINE):
        raise SystemExit("ABORT 还原后 sha 与 pristine 不一致 —— 还原本身坏了")
    return sha(PANEL)


def build():
    r = subprocess.run(["npm", "run", "build"], cwd=str(FRONT),
                       capture_output=True, text=True, timeout=900)
    bid = FRONT / ".next/BUILD_ID"
    if r.returncode != 0 or not bid.exists():
        print(r.stdout[-1200:]); print(r.stderr[-1200:])
        return False, r.stdout + r.stderr
    return True, "BUILD_ID=%s" % bid.read_text().strip()


def wait_http(url, seconds=30):
    for _ in range(seconds):
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status < 500:
                    return True
        except Exception:
            time.sleep(1)
    return False


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "BASE"
    port = sys.argv[2] if len(sys.argv) > 2 else "10100"
    if not PRISTINE.exists():
        PRISTINE.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PANEL, PRISTINE)
    print("pristine sha %s" % restore()[:16])

    if which != "BASE":
        if which not in MUTS:
            print("用法：BASE | P1 | P2 | P3 | P4 | P5")
            return 2
        old, new = MUTS[which]
        s = PANEL.read_text(encoding="utf-8")
        if s.count(old) != 1:
            print("ABORT %s 锚点命中 %d 次（必须恰好 1 次）" % (which, s.count(old)))
            return 2
        PANEL.write_text(s.replace(old, new, 1), encoding="utf-8")
        back = PANEL.read_text(encoding="utf-8")
        marker = "MUT_" + which
        # ⚠ 只查 marker，**不要**再查 `old in back` ——
        #   P1 的 new 是以 old 开头的（多插了一行），那个条件恒为真，
        #   于是每一��都误报「回读失败」。第一版就是这么白跑的。
        if back.count(marker) != 1:
            print("ABORT %s 施加后回读失败（marker 出现 %d 次）"
                  % (which, back.count(marker)))
            restore()
            return 2
        print("%s 施加并回读自证通过（marker 恰好 1 次）" % which)

    ok, log = build()
    if not ok:
        print("ABORT build 没落地 —— 编译失败的变异不算命中")
        restore()
        return 2
    proc = subprocess.Popen(
        ["npx", "next", "start", "-p", port], cwd=str(FRONT),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        if not wait_http("http://127.0.0.1:%s/" % port):
            print("ABORT 前端没起来")
            return 3
        # ⚠ 括号不能省：`/` 的优先级高于 `%`，写成
        #   `ROOT / "x%s" % which` 实际是 `(ROOT / "x%s") % which`
        #   ⇒ TypeError: PosixPath % str。第一版就这么每条都崩。
        env = dict(os.environ,
                   T3D_URL="http://127.0.0.1:%s/" % port,
                   # ⚠ 目录要放在 .cache/browser_verify 下面。第一版写成
        #   ROOT / ("profile_ml_" + which)
        # 于是 Chromium 的 profile 直接落在**仓库根目录**，六条变异留下
        # 六个未跟踪目录。路径层级要在拼接之后再补。
                   T3D_PROFILE=str(ROOT / ".cache/browser_verify"
                                 / ("profile_ml_" + which)))
        r = subprocess.run(["node", str(JUDGE)], capture_output=True, text=True,
                           timeout=420, env=env)
        out = r.stdout + r.stderr
        fails = [ln for ln in out.splitlines() if ln.startswith("[FAIL]")]
        ran = [ln for ln in out.splitlines()
               if ln.startswith("[PASS]") or ln.startswith("[FAIL]")]
        if not ran:
            print("ABORT 判据一条都没跑起来 —— 装置故障，不是判红")
            print(out[-1500:])
            return 3
        for ln in out.splitlines():
            if ln.startswith("[PASS]") or ln.startswith("[FAIL]") or ln.startswith("==="):
                print("  " + ln[:150])
        red = bool(fails)
        print("\nRESULT %s  %s  红在 %d/%d 条"
              % (which, "RED" if red else "GREEN", len(fails), len(ran)))
        if which == "BASE":
            print("BASE 绿，符合预期" if not red else "!! BASE 有红，基线本身坏了")
        else:
            want = EXPECT[which]
            if not red:
                print("!! 变异没让判据变红 —— 这一支没有牙齿")
            elif not any(any(w in ln for w in want) for ln in fails):
                print("!! 变红了，但没红在预期的 %s 上" % want)
            else:
                print("预期红在 %s —— 对上了" % want)
    finally:
        try:
            proc.kill()
        except Exception:
            pass
        restore()
        if which != "BASE":
            print("已还原并重建干净 bundle")
            build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
