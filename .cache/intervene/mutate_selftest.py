#!/usr/bin/env python3
"""变异：证明 selftest.py 的每一条判据都有牙齿。

装置类判据特别容易变成装饰 —— 因为「跑出来是绿的」和「它其实什么都没查」
在返回值上长得一样。所以每条判据都要有一条**专门打它**的变异。

| 变异 | 改坏的地方 | 必须变红的判据 |
|---|---|---|
| X1 | `attach` 挂到 `layers[layer-1]`（层号错位一位） | S4 / S4b |
| X2 | α=0 时仍注入一个 `or 1e-9` 的泄漏量 | **S1** |
| X3 | `random_directions` 返回**植入方向本身**（对照失效） | **S3** |
| X4 | `scale` 固定为 1.0（放弃相对幅度口径） | **S2b / S6** |
| X5 | 读出方向取成坐标 1 而不是植入坐标 0 | **S5** |
| X6 | 注入从加性改成乘性 `h*(1+α)` | **S2 / S2b** |

用法：python3 mutate_selftest.py <X1|X2|X3|X4|X5|X6|BASE>
BASE 必须绿；每条变异必须红在**它该红的那条**上。
"""
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path("/Users/zhourui/code/steer3d")
D = ROOT / ".cache/intervene"
HARNESS = D / "harness.py"
SELFTEST = D / "selftest.py"
PRISTINE = D / "harness.pristine.py"
SELFP = D / "selftest.pristine.py"

# 每条变异带自己的目标文件 —— harness 里的 bug 和 selftest 里的 bug
# 要能分别注入，不能只改一个地方。
MUTS = {
    # X1：层号错位。锚点是 **4 空格**缩进 —— 我第一版写成 8 空格，
    #     命中 0 次却在「命中 0 次」时才报出来，差一点就当成变异生效。
    "X1": [(HARNESS, "    blk = layers[layer]\n",
                   "    blk = layers[max(0, layer - 1)]  # MUT_X1\n")],
    # X2：α=0 仍然改一点点。
    #     ⚠ 第一版把泄漏写在 `if not self.active: return h` 的**下一行** ——
    #     而 α=0 时 active 就是 False，那行**永远走不到**，于是变异是死的、
    #     判据却「没有牙齿」。这正是「变异 rc=0 的第四种原因：
    #     改了一条几乎不可达的分支」。
    #     现在改的是那条**可达**的早退路径。
    # ⚠ 第二版泄漏取 1e-9，仍然绿 —— 因为 logit≈2.0 处 float32 的分辨率
    #     约 1.2e-7，2.1e-9 的扰动在浮点层面**根本不存在**。
    #     S1 断言的是**逐位相同**，所以只有超过分辨率的泄漏才可测。
    #     这不是判据的毛病，是「可测性有下限」这件事本身。
    "X2": [(HARNESS, "        if not self.active:\n            return h\n",
                   "        if not self.active:\n"
                   "            return h * (1.0 + 1e-4)  # MUT_X2 零 alpha 仍改一点点\n")],
    "X3": [(HARNESS, "        x = torch.randn(dim, generator=g)\n",
                   "        x = torch.zeros(dim); x[0] = 1.0  # MUT_X3\n")],
    "X4": [(HARNESS, "            self.scale = float(h.reshape(-1, h.shape[-1]).norm(dim=-1).mean())\n",
                   "            self.scale = 1.0  # MUT_X4\n")],
    "X5": [(SELFTEST, "    r = rho_on_direction(base.h_layer, y, v)\n",
                   "    v_bad = v.clone(); v_bad[0] = 0.0; v_bad[1 % D] = 1.0  # MUT_X5\n"
                   "    r = rho_on_direction(base.h_layer, y, v_bad)\n")],
    "X6": [(HARNESS, "        return h + (self.alpha * self.scale) * v\n",
                   "        return h * (1.0 + self.alpha)  # MUT_X6\n")],
}
EXPECT = {
    "X1": ["S4"], "X2": ["S1"], "X3": ["S3"],
    "X4": ["S2b", "S6"], "X5": ["S5"], "X6": ["S7"],
}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def restore():
    shutil.copy2(PRISTINE, HARNESS)
    shutil.copy2(SELFP, SELFTEST)
    for p in (HARNESS, SELFTEST):
        if sha(p) != sha(PRISTINE if p == HARNESS else SELFP):
            raise SystemExit("ABORT 还原后 sha 不一致 —— 还原本身坏了")
    return sha(HARNESS), sha(SELFTEST)


def run_all():
    """跑 BASE + 全部变异，末尾报「跑了 N 条，按预期变红 M 条」。

    ⚠ 子进程用 `subprocess.run` 取**它自己的**退出码，不用管道 + grep ——
      那个坑（退出码变成 grep 的、恒为 0）我刚在 run_all_outcome.sh 上踩过。
    ⚠ 判据是「它是不是红在**预期的那几条**上」，不是「它有没有红」——
      装置崩了、或一条都没跑，在只看 rc 的时候长得一样。
    """
    names = ["BASE"] + sorted(MUTS)
    bad = []
    for n in names:
        p = subprocess.run([sys.executable, str(Path(__file__)), n],
                           capture_output=True, text=True)
        out = p.stdout + p.stderr
        line = [l for l in out.splitlines() if l.startswith("RESULT ")]
        summary = line[0] if line else "（无 RESULT 行 —— 装置没跑完）"
        # 「ABORT 装置自身没跑完」是故障，不算判红，也不算通过。
        crashed = "装置自身没跑完" in out or not line
        if crashed or "GREEN" in summary and n != "BASE":
            bad.append(n)
        print("  %-5s %s" % (n, summary))
        if crashed:
            print("         !! 这一条是故障，不是判红，也不是通过")
        # 判「红在预期的那几条上」时，**必须按真实输出格式匹配**。
        # 我第一版找 "预期红在 S4"，而脚本印的是 "预期红在 ['S4'] —— 对上了"
        # （EXPECT 的 list repr）⇒ 6 条全部误报「没红在预期上」，
        # 而它们明明都红了。⇒ 先看它到底印什么，再写匹配。
        # 这里不按字符串硬匹配，而是逐行看：含「预期红在」的那行里有没有该判据号。
        redline = [l for l in out.splitlines() if "预期红在" in l]
        for e in EXPECT.get(n, []):
            if not any(e in l for l in redline):
                bad.append(n + "/" + e)
                print("         !! 没有红在预期的 %s 上" % e)
    print("\n跑了 %d 条（BASE + %d 变异），异常 %d 处"
          % (len(names), len(MUTS), len(bad)))
    if bad:
        print("  异常：%s" % ", ".join(bad))
    print("RESULT %s" % ("OK" if not bad else "RED"))
    return 1 if bad else 0


def main():
    # ⚠ 不带参数时它只跑 BASE，然后照样打「已还原（sha 自证通过）」——
    #   看着像跑完了，实际 6 条变异一条都没跑。这与 run_all_outcome.sh 是同一个病，
    #   而那边我差点就把它当「全量跑过」提交了。
    # ⇒ 改成：不给参数直接报错退出；给 ALL 则跑完全部并累计失败数。
    if len(sys.argv) < 2:
        print("用法：ALL | BASE | X1 X2 X3 X4 X5 X6")
        print("（不带参数就是零次运行。空跑打出的「已还原」看着像跑完了。）")
        return 2
    which = sys.argv[1]
    if which == "ALL":
        return run_all()
    if not PRISTINE.exists():
        shutil.copy2(HARNESS, PRISTINE)
    if not SELFP.exists():
        shutil.copy2(SELFTEST, SELFP)
    hs, ss = restore()
    print("pristine harness %s / selftest %s" % (hs[:12], ss[:12]))

    if which != "BASE":
        if which not in MUTS:
            print("用法：BASE | X1 | X2 | X3 | X4 | X5 | X6")
            return 2
        for path, old, new in MUTS[which]:
            s = Path(path).read_text()
            if s.count(old) != 1:
                print("ABORT %s 锚点在 %s 命中 %d 次（必须恰好 1 次）"
                      % (which, Path(path).name, s.count(old)))
                restore()
                return 2
            Path(path).write_text(s.replace(old, new, 1))
        # 施加后回读：用 **marker** 判定，而不是「old 不再出现」。
        # new 常常以 old 开头（X2 就是），那时 `old in back` 恒为真，
        # 第一次就是这么误判成「变异没生效」的。
        for path, old, new in MUTS[which]:
            back = Path(path).read_text()
            marker = "# MUT_" + which
            if marker not in back or back.count(marker) != 1:
                print("ABORT %s 施加后回读失败：%s 里 marker 出现 %d 次"
                      % (which, Path(path).name, back.count(marker)))
                restore()
                return 2
        print("%s 施加并回读自证通过（marker 恰好 1 次）" % which)

    r = subprocess.run([sys.executable, str(SELFTEST)], cwd=str(D),
                       capture_output=True, text=True)
    out, err = r.stdout, r.stderr
    fails = [ln for ln in out.splitlines() if ln.startswith("[FAIL]")]
    ran = [ln for ln in out.splitlines()
           if ln.startswith("[PASS]") or ln.startswith("[FAIL]")]
    verdict = [ln for ln in out.splitlines() if ln.startswith("RESULT selftest")]

    # ⚠⚠ **「一条都没跑」与「跑完全绿」必须分开**。
    #   这一版第一版只读 stdout，而装置崩溃的 traceback 走 **stderr** ——
    #   于是「装置已经死了、0 条断言」被报成 `GREEN 0 条`，
    #   六条变异**全部**显示「没有牙齿」，看起来像是判据全废，
    #   实际上是我自己把 selftest 写崩了（`del recorded` 引用未定义变量）。
    # ⚠⚠ 判崩溃**不能只看 stderr 非空**：torch 会往 stderr 打
    #   `OMP: Warning #179: Function Can't set size of /tmp file failed`，
    #   那是无害噪声。按第一版那样写会让**每一次**都误报 ABORT。
    #   正确判据：returncode ≠ 0（有 traceback 必然非 0），
    #   再加上「断言条数 > 0」与「有 RESULT 行」两道。
    # ⚠⚠ 判崩溃**不能**用「returncode ≠ 0」：selftest 判红时也返回 1，
    #   那是**合法结果**不是故障。把它当崩溃会让每一条变异都误报 ABORT
    #   （第三版就是这么错的：X1–X6 明明全红在正确的判据上，输出却是 ABORT）。
    #   可靠信号只有三个：stderr 里有 traceback / 没有 RESULT 行 / 一条断言都没跑。
    crashed = ("Traceback (most recent call last)" in err) or not verdict or not ran
    if crashed or not ran or not verdict:
        print("ABORT 装置自身没跑完 —— 这是故障，不是判红，也不能算 GREEN")
        print("  returncode=%s  跑到 %d 条断言，RESULT 行 %s"
              % (r.returncode, len(ran), "有" if verdict else "无"))
        if crashed:
            print("  stderr 末行: " + (err.strip().splitlines()[-1] if err.strip() else "(空)"))
        print(out[-1200:])
        restore()
        return 3
    print()
    for ln in fails:
        print("   " + ln[:150])
    red = bool(fails)
    print("\nRESULT %s  %s  红在 %d/%d 条" % (which, "RED" if red else "GREEN",
                                              len(fails), len(ran)))
    if which == "BASE":
        if red:
            print("!! BASE 竟然有红 —— 基线本身坏了")
        else:
            print("BASE 绿，符合预期")
    else:
        want = EXPECT[which]
        got = [f for f in fails]
        ok = any(any(w in ln for w in want) for ln in got)
        if not red:
            print("!! 变异没让任何判据变红 —— 这一支没有牙齿")
        elif not ok:
            print("!! 变红了，但没红在预期的 %s 上" % want)
        else:
            print("预期红在 %s —— 对上了" % want)
    restore()
    print("已还原（sha 自证通过）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
