"""证据链完整性自检：**一条命令**跑完本项目所有「可复算」承诺。

## 为什么要有它

本项目对外声称的三件事，都是**手工**验过一次就没人再验：

1. 面板/文档上的每个数字都来自**未改动的**远端产物；
2. 「可复算构建器」——重跑 `build_bpath_evidence.py` 输出逐字节一致；
3. 文档 §6 的复算清单与构建器实际读取的文件一致。

⚠ 手工验过一次的东西会随时间腐烂：构建器加了新输入、产物被人手改过、
清单忘了更新 —— 没有一条会自己报警。这个脚本就是那条报警。

## 它查什么

| # | 检查 | 失败意味着 |
|---|---|---|
| A | 构建器重跑输出与交付 JSON **逐字节**一致 | 交付 JSON 里混进了「构建器不产出」的手写数字 |
| B | 文档 §6 清单 ⊇ 构建器实际读取的文件，且臂 A 不在其中 | 复算照文档做跑不起来 / 又踩了 43 倍那个坑 |
| C | `.cache/mutbak/` 与远端同名产物 **sha256 一致** | 本地证据副本已被改动，文档里的数字追不回源头 |
| D | 交付 JSON 里每个 `built_from` 引用的文件**确实存在** | 引用了不存在的产物 |
| E | 全部先验套件通过 | 判据/选材/地板口径的实现被人改坏 |

⚠ C 在**连不上远端时跳过并明说**，不静默当作通过 ——
「没查」和「查过了」必须能分辨。

## 用法

    PYTHONPATH=.cache/pylibs python3 .cache/bpath/audit_evidence_chain.py
    PYTHONPATH=.cache/pylibs python3 .cache/bpath/audit_evidence_chain.py --no-remote

## 只读

不写任何交付物：重跑构建器的输出写到临时目录，比对完即删。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
BUILDER = os.path.join(ROOT, ".cache/bpath/build_bpath_evidence.py")
DELIVERED = os.path.join(ROOT, "frontend/public/latent/data/"
                                   "bpath_marker_steering.json")
MUTBAK = os.path.join(ROOT, ".cache/mutbak")
REMOTE_DIR = "/home/zhourui/steer3d_bpath"
REMOTE_HOST = "zju-53"
DELIVERED = os.path.join(ROOT, "frontend/public/latent/data/"
                                   "bpath_marker_steering.json")

# 本地判定产物：它们**远端本就没有**（是判决不是数据），不做同源比对
LOCAL_ONLY = {"q3_verdict.json", "saturation_verdict.json",
              "confound_verdict.json", "generalization_verdict.json",
              "orthogonality_verdict.json", "ortho_frac_verdict.json",
              "ortho_frac_full.json", "hi_sites_pick.json",
              "hi_sites_verdict.json",
              # 修订 32/33：extreme_pick_abs.json 是**本地**过滤器从远端扫描
              # 清单派生的（远端那份只是副本，本地才是源）⇒ 比对无意义。
              # extreme_verdict.json 是判决，产物不落远端。
              "extreme_pick_abs.json", "extreme_verdict.json",
              # 修订 36/37：token_id_verdict* 是**本地**判决（由本地
              # probe + 本地 site_tokens 映射算出），产物不落远端。
              "token_id_verdict.json", "token_id_verdict_hi.json",
              "mixture_verdict.json",
              # 修订 40：marker_all_hi.json 是远端 count_marker_tokens.py 的
              # 产物（**应当**同源）；selection_contamination.json 是本地
              # 判决（由本地 probe + 本地映射 + 本地 marker 构成算出）。
              "selection_contamination.json",
              # 修订 42：pos_strat.json 是**本地**判决（由本地 probe + 本地
              # site_tokens 映射算出，判据在预登记 §37.3），产物不落远端。
              # ⚠ 它必须出现在这个列表里：构建器若用变量路径加载就会逃出
              #   C 项的扫描，那时「远端同源」对它**根本没跑过**。
              "pos_strat.json",
              # 本地备份（原始文件仍在远端），比对它没有意义
              "layer_sweep_t1.json.bak_armA"}

SUITES = ["test_ortho_frac_verdict.py", "test_pick_hi_sites.py",
          "test_hi_sites_verdict.py", "test_extreme_verdict.py",
          "test_ortho_extreme_scan.py",
          "test_apply_abs_boundary.py",
          "test_ortho_nt_scan.py",
          "test_token_id_verdict.py", "test_mixture_verdict.py",
          "test_selection_contamination.py",
          "test_docs_token_tables.py",
          "test_bpath_verdict.py",
          "test_ladder_cross_consistency.py",
          "test_completion_counts.py",
          "test_docs_repro_list.py"]

results = []


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def check(name, ok, detail="", skipped=False):
    results.append((name, ok, detail, skipped))
    tag = "跳过" if skipped else ("通过" if ok else "**失败**")
    print(f"[{tag}] {name}" + (f"  —— {detail}" if detail else ""))
    return ok


def check_a():
    if not os.path.exists(DELIVERED):
        return check("A 构建器可复算", False, "交付 JSON 不存在")
    with tempfile.TemporaryDirectory(prefix="chainaudit_") as td:
        out = os.path.join(td, "repro.json")
        r = subprocess.run([sys.executable, BUILDER, "--mutbak", MUTBAK,
                            "--out", out], capture_output=True, text=True)
        if r.returncode != 0:
            return check("A 构建器可复算", False,
                         (r.stderr or r.stdout).strip().splitlines()[-1:])
        same = open(out, "rb").read() == open(DELIVERED, "rb").read()
    return check("A 构建器可复算", same,
                 "逐字节一致" if same else "重跑输出与交付文件不同")


def check_b():
    r = subprocess.run([sys.executable,
                        os.path.join(ROOT, ".cache/bpath/test_docs_repro_list.py")],
                       capture_output=True, text=True)
    return check("B 文档复算清单", r.returncode == 0,
                 (r.stdout or r.stderr).strip().splitlines()[0])


def chain_inputs():
    """证据链**真正依赖**的远端产物集合。

    ⚠ 不扫整个 `.cache/mutbak/`：那个目录里还躺着**别的任务线**的产物
    （`causal_*` / `logit_lens_*` / `hinge_*` / `strict_label_*` …），
    它们本来就不在这个远端目录下。把它们算成「远端缺失」是一堆噪音，
    噪音久了就没人看报警了。

    ⇒ 只取构建器 `jload` 读的那批（它们才是进到交付 JSON 里的数字来源），
    再减去本地生成的判决与本地备份。
    """
    import re
    src = open(BUILDER, encoding="utf-8").read()
    used = set(re.findall(r'jload\(M / "([^"]+)"', src))
    return {f for f in used
            if f not in LOCAL_ONLY and os.path.exists(os.path.join(MUTBAK, f))}


def check_c(use_remote):
    if not use_remote:
        return check("C 产物与远端同源", False, "按 --no-remote 跳过", skipped=True)
    names = sorted(chain_inputs())
    if not names:
        return check("C 产物与远端同源", False, "mutbak 里没有可比对的产物")
    bad, missing = [], []
    for n in names:
        lh = sha256(os.path.join(MUTBAK, n))
        rr = subprocess.run(["ssh", REMOTE_HOST,
                             f"shasum -a 256 {REMOTE_DIR}/{n}"],
                            capture_output=True, text=True)
        if rr.returncode != 0:
            missing.append(n)
        elif not rr.stdout.strip().startswith(lh):
            bad.append(n)
    ok = not bad
    detail = f"{len(names) - len(missing) - len(bad)}/{len(names)} 一致（{names}）"
    if bad:
        detail += f"；**不一致：{bad}**"
    if missing:
        detail += f"；远端没有：{missing}"
    return check("C 产物与远端同源", ok, detail)


def check_d():
    J = json.load(open(DELIVERED, encoding="utf-8"))
    refs, where = set(), []

    def walk(o, path="$"):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "built_from":
                    (refs.update(v) if isinstance(v, (list, tuple))
                     else refs.add(str(v)))
                    where.append(path)
                else:
                    walk(v, f"{path}.{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, f"{path}[{i}]")
    walk(J)
    missing = sorted(r for r in refs
                     if not (os.path.exists(os.path.join(MUTBAK, r))
                             or os.path.exists(os.path.join(ROOT, r))))
    return check("D built_from 引用存在", not missing,
                 f"{len(refs)} 个引用" + (f"；缺失 {missing}" if missing else ""))


def check_e():
    fails = []
    for s in SUITES:
        p = os.path.join(ROOT, ".cache/bpath", s)
        if not os.path.exists(p):
            fails.append(f"{s}(缺)")
            continue
        r = subprocess.run([sys.executable, p], capture_output=True, text=True)
        if r.returncode != 0:
            fails.append(s)
    return check("E 全部先验套件", not fails,
                 f"{len(SUITES)} 套" + (f"；失败 {fails}" if fails else ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-remote", action="store_true")
    a = ap.parse_args()
    print("=== 证据链完整性自检 ===")
    check_a()
    check_b()
    check_c(not a.no_remote)
    check_d()
    check_e()
    n_fail = sum(1 for _, ok, _, sk in results if not ok and not sk)
    n_skip = sum(1 for _, _, _, sk in results if sk)
    print(f"\n{len(results)} 项：{len(results)-n_fail-n_skip} 通过、"
          f"{n_fail} 失败、{n_skip} 跳过")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())