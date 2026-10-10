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
| **A2** | 阶梯产物重跑**逐字节**一致 | 阶梯表里混进了「生成器不产出」的手写数字 |
| **A3** | 阶梯的**五个上游快照**都有仓库内生成器 | 阶梯的**上游**没有机械出处（A2 只管第二层） |

⚠⚠ **A2 的覆盖范围比它的名字窄**（修订 48 改写过一次措辞）：它验的是
「阶梯 = 五个冻结快照的确定性函数」，**不是**「阶梯里的数字能被重造出来」。
A2 曾做过牙齿实测（改 L2 可读下界 14→13 即红），那次实测恰恰**只覆盖第二层**。
A3 把这一层缺口单独报出来，落地时是 **0/5 ⇒ 故意保持红**。

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
import re
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
# 修订 46 R-3：阶梯生成器 + 它的交付产物（A2 项用）
LADDER = os.path.join(ROOT, ".cache/xcheck/build_evidence_ladder.py")
DATA = os.path.join(ROOT, "frontend/public/latent/data")
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

SUITES = ["test_evidence_chain_scope.py",
          "test_ortho_frac_verdict.py", "test_pick_hi_sites.py",
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
          "test_framework_doc_ladder.py",
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


def check_a2():
    """证据链 A 项的姊妹：阶梯产物也必须**逐字节**可复算（修订 46 R-3）。

    ⚠ 为什么单列：A 项只重建 `bpath_marker_steering.json`，
      而 `evidence_ladder.json` 是框架文档称为「这份文档真正的产物」的那张表，
      此前**没有任何字节级复现检查**。
    ⚠ 临时目录放在 `.cache/mutbak/` 下而不是系统 temp：**`/tmp` 在本机不可写**。

    ⚠⚠ 条目名在修订 48 改过一次（这是本轮唯一的**措辞**更正，不是判决变更）。
      原名「阶梯产物可复算」覆盖范围**大于**本函数验证的范围：它验的是
      「重跑 `build_evidence_ladder.py` 的输出 == 交付文件」，而那个脚本的五个输入
      （`linearity_law` / `readable_subspace` / `heldout_readability` /
      `arm_asymmetry` / `cot_texts`）**全部是仓库里的冻结快照，全部没有生成器**。
      ⇒ 本项只证明「阶梯 = 五个冻结快照的确定性函数」，
      **不**证明「阶梯里的数字能被重造出来」。第二层由 A3 单独报。
    """
    delivered = os.path.join(DATA, "evidence_ladder.json")
    name = "A2 阶梯产物可复算（仅：重跑==五个冻结快照的确定性函数）"
    if not os.path.exists(delivered):
        return check(name, False, "evidence_ladder.json 不存在")
    with tempfile.TemporaryDirectory(prefix="chainaudit_a2_",
                                     dir=os.path.join(ROOT, ".cache/mutbak")) as td:
        out = os.path.join(td, "ladder.json")
        r = subprocess.run([sys.executable, LADDER, "--out", out],
                           capture_output=True, text=True)
        if r.returncode != 0:
            return check(name, False,
                         (r.stderr or r.stdout).strip().splitlines()[-1:])
        same = open(out, "rb").read() == open(delivered, "rb").read()
    return check(name, same,
                 "逐字节一致" if same else "重跑输出与交付文件不同")


# ---- 修订 48 W3：证据链第二层。A2 的覆盖到此为止。----------------------
# 「在仓库内」= 被 `git ls-files` 跟踪。`.cache/` 整个被 ignore，
# 那里的脚本**不算**仓库内的生成器 —— 想算数必须先被跟踪。
UPSTREAMS = ("linearity_law", "readable_subspace", "heldout_readability",
             "arm_asymmetry", "cot_texts")
DELIVERED_DIR = "frontend/public/latent/data"

# ⚠⚠ 判「生成器」不能只看「文件里出现了这个名字」+「文件里有写盘调用」。
#   `build_evidence_ladder.py` 五个名字**全部**出现、也**确实**写盘 ——
#   但它写的是 `evidence_ladder.json`，是这五份产物的**消费者**不是生成器。
#   反过来第一版把写条件写成无名的 `write_text|json\.dump|OUT|--out`，
#   再叠加一个只认 `read_text(...name...)` 的读条件（项目实际都写成
#   `json.loads((DATA / "x.json").read_text())`，名字在 `read_text(` **之前**），
#   结果把 4/5 个真实存在的生成器全判成 0 个 ⇒ A3 报出一条**假的欠账**。
#   ⚠ 这是本项目第 N 次「独立复算的实现本身才是坏的东西」。
#
# 现在三条都**带名字**：
#   ① 名字出现在某个**输出声明**上（OUT/DST/--out = …name.json）
#   ② 或名字所在行的 ±3 行窗口内有写盘调用（覆盖 `path = …` 下一行才 dump 的写法）
#   ③ 且该路径落在**交付目录** `frontend/public/latent/data/` 下
#      —— 只写到 `.cache/` 本地副本不算，那不是读者拿到的那一份。
_OUT_DECL = re.compile(r"(?:OUT|DST|OUTFILE|OUTPATH|OUTPUT|--out)\w*\s*[=:]")
_WRITE_CALL = re.compile(r"write_text|json\.dump|json\.dumps|\bopen\s*\([^)]*[\"']w[\"']")


def tracked_files():
    try:
        r = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                           text=True)
        if r.returncode == 0:
            return r.stdout.split()
    except OSError:
        pass
    return []


def _name_lines(txt, name):
    base = re.compile(rf"\b{re.escape(name)}\.json\b")
    return [i for i, ln in enumerate(txt.splitlines()) if base.search(ln)]


def writes_named_artifact(name):
    """被跟踪的源文件里，**把 `name.json` 当输出写下来**的那些。

    返回 (相对路径, 写到交付目录了吗)。两者要分开：脚本存在 ≠ 交付的那份
    能从干净克隆重造出来。
    """
    hits = []
    for rel in tracked_files():
        if not rel.endswith((".py", ".sh")):
            continue
        try:
            txt = open(os.path.join(ROOT, rel), encoding="utf-8",
                       errors="ignore").read()
        except OSError:
            continue
        lines = txt.splitlines()
        for i in _name_lines(txt, name):
            window = lines[max(0, i - 3): i + 4]
            is_write = (_OUT_DECL.search(lines[i])
                        or any(_WRITE_CALL.search(w) for w in window))
            if not is_write:
                continue
            # 这一行（及窗口）里该名字所在的完整路径
            ctx = "\n".join(window)
            hits.append((rel, DELIVERED_DIR in ctx))
            break
    return hits


def generator_of(name):
    """判据口径：**写到交付目录**的那一个才算数。

    ⚠ 只写到 `.cache/` 本地副本的生成器（`linearity_law.py` 就是）不算 ——
      它证明的是「这些数在本机上量过一次」，不是「读者能重造」。
    """
    for rel, to_delivery in writes_named_artifact(name):
        if to_delivery:
            return rel
    return None


# ---- 修订 52：A3 的判定条件加两层（写死路径 / 输入是否在仓库里）---------
# ⚠ 修订 48 的 A3 只验「被跟踪的源文件里有没有把 <name>.json 写到交付目录」。
#   那个条件**只验了输出端**。实测：四个「交付路径」档的生成器全部
#   `ROOT = Path("/Users/zhourui/code/steer3d")` 写死，而且它们要的
#   `dir_cache/w_*.npy`（本机 14 个）、`confidence_*.npy`（作者的未跟踪 WIP）
#   **在仓库里一个副本都没有** ⇒ 干净克隆上第一行就 FileNotFoundError。
# ⚠⚠ 本节只做**静态**判定，**不执行**那些脚本（要 torch / npz / 远端）。
#   所以判决里出现的是「静态可达」，**不是**「跑通了」。
_HARD_ABS = re.compile(
    r'(?:ROOT|OUT|DST|OUTFILE|OUTPATH|SRC|CACHE|DATA|X)\s*=\s*Path\(\s*"/'
    r'|sys\.path\.insert\(\s*0\s*,\s*"/'
    r'|(?:np\.load|open|json\.load)\(\s*["\']/(?:Users|home)/')
_NPY_LITERAL = re.compile(r'["\']([^"\']+\.npy)["\']')


def tracked_basenames():
    return {os.path.basename(rel) for rel in tracked_files()}


def static_reachable(rel):
    """静态判定一个生成器在**干净克隆**上能不能跑（返回 档位, 细节）。

    ⚠ 只查两个**必要方向**：写死绝对路径、以及脚本要的 `.npy` 在仓库里
    有没有被跟踪的副本。任一不成立就**确定**跑不起来。
    ⚠ 两个都成立**不等于**能跑（还有 torch / npz / 远端等未查项），
      所以最高档叫「静态可达」，**不叫**「可跑」。
    ⚠ 档位按 U2 的**顺序**判定 —— 先撞上的先报，否则读者会以为「只差一样」。
    """
    fp = os.path.join(ROOT, rel)
    try:
        src = open(fp, encoding="utf-8", errors="ignore").read()
    except OSError as e:
        return "读不到", [str(e)]
    hard = sorted({m.group(0).strip()[:70] for m in _HARD_ABS.finditer(src)})
    if hard:
        return "写死路径", ["%s: %s" % (rel, " / ".join(hard[:2]))]
    tb = tracked_basenames()
    need = sorted({os.path.basename(m) for m in _NPY_LITERAL.findall(src)})
    missing = [n for n in need if n not in tb]
    if missing:
        return "输入不在仓库", ["%s 要的 %s 在仓库里无被跟踪副本"
                                % (rel, ", ".join(missing))]
    if not need:
        # ⚠⚠⚠ **空洞通过**：脚本里一个 `.npy` 字面量都没有 ⇒
        #   「都有被跟踪副本」是**空真**，和恒绿判据一样没有信息量。
        #   实测就踩到了：`linearity_law.py` 通过 `NpzReplayRunner` 读 npz，
        #   一个 `.npy` 都没有 ⇒ 第一版给它判了「静态可达」，
        #   而它真正需要的远端 npz **根本不在仓库里**。
        # ⇒ 显式报「本项对它无判据」，**不许**顺着空真报可达。
        return "本项无判据", ["%s 里没有 .npy 字面量（它走别的读法）"
                              "⇒ 本项对它无判据，不能报可达" % rel]
    # ⚠⚠ **按 basename 匹配是弱近似**：同名文件在仓库的**别的目录**下也会算命中。
    #   所以「静态可达」**只代表这一项没查出缺口**，不代表输入真的齐 ——
    #   与「本项无判据」一样，措辞必须如实。
    return "静态可达", ["%s 无写死路径、%d 个 .npy 按 basename 在仓库有副本"
                        "（⚠ basename 匹配是弱近似，同名不同目录会误判为命中）"
                        % (rel, len(need))]


def check_a3():
    """五个上游快照的生成器，在干净克隆上**静态可达**吗。

    ⚠ 本项**不改判 A2**：A2 判的命题为真，错的只是它的条目名（已改写）。
    ⚠⚠ 本项只做**静态**判定，**不执行**那些生成器（要 torch / 远端 npz）。
      「静态可达」**不等于**「跑通了」。
      ⚠ 这是修订 52 写死的措辞纪律：上一版报「4/5 在交付路径」用的就是
      「在交付路径」这种**没有覆盖执行**的说法，而实测四个都跑不起来。
    """
    order = ["静态可达", "写死路径", "输入不在仓库", "本项无判据", "仓库内无"]
    buckets = {k: [] for k in order}
    parts = []
    for u in UPSTREAMS:
        hits = writes_named_artifact(u)
        if not hits:
            buckets["仓库内无"].append(u)
            parts.append("%s.json → 仓库内无（已知欠账）" % u)
            continue
        cand = next((r for r, d in hits if d), hits[0][0])
        bucket, why = static_reachable(cand)
        buckets[bucket].append(u)
        parts.append("%s.json → %s（%s）" % (u, bucket, why[0][:100]))
    ok = all(not buckets[k] for k in order if k != "静态可达") \
        and len(buckets["静态可达"]) == len(UPSTREAMS)
    return check("A3 五个上游的生成器静态可达（非执行；不覆盖 torch/npz/远端）",
                 ok, "；".join(parts))


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
    check_a2()
    check_a3()
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