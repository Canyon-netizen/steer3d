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
| **A4** | 上游生成器在 `git archive` 出的**干净克隆**里真跑通且产物逐字节一致 | 静态看着可达、干净克隆上其实跑不起来（写死路径 / 输入未跟踪） |

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


def _same_bytes(a, b):
    """逐字节比对两个文件（修订 53 A4 用）。

    ⚠ **不许**用「解析成 JSON 再比相等」—— 那会把键序、空白、数字格式的
    差异全吞掉，而本项目要的正是「构建器重跑逐字节一致」这条承诺。
    """
    try:
        if os.path.getsize(a) != os.path.getsize(b):
            return False
    except OSError:
        return False
    with open(a, "rb") as fa, open(b, "rb") as fb:
        return fa.read() == fb.read()


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
# ⚠⚠⚠ **下面这行正则和 _HARD_ABS 一样是「被审计的对象」** ——
#   本文件里任何地方都**不许**写出它要匹配的完整字面形态，否则会把自己判成命中。
#   （修订 52 在 linearity_law.py 的注释里踩过；这里主动写一条提醒。）
_NPY_LITERAL = re.compile(r'["\']([^"\']+\.npy)["\']')

# ---- 修订 53：U1b′ 的输入字面量口径 ------------------------------------------------
# ⚠⚠ **修订 52 的 U1b 只认 `.npy`，而实测这三个生成器的主要输入是 `.json`**：
#   `build_heldout_readout.py` 一个 `.npy` 都没有、7 个 `.json` 全部被跟踪，
#   旧口径却判它「本项无判据」⇒ **查到的子集几乎是空的**，
#   「查不到缺口」与「没有缺口」被压成同一句话。空洞判据的另一个面。
#
# 新口径两条：
#   ① **数据类扩展名**从 1 项扩到 6 项。
#   ② **优先精确解析**：抓 `<目录常量> / "<文件名>"` 的拼接形态，
#      把目录常量沿赋值链展开成**仓库相对路径**再查 git ls-files ——
#      比修订 52 的 basename 匹配强（同名不同目录不再误判为命中）。
_DATA_EXT = (".npy", ".npz", ".json", ".csv", ".tsv", ".txt")
_DIR_ASSIGN = re.compile(r'^\s*([A-Z_][A-Z_0-9]*)\s*=\s*([A-Z_][A-Z_0-9]*)?\s*/\s*"([^"]*)"')
# `<目录常量> / "<文件名>"`，文件名可以带 f 前缀（那样会含 {，见下）
_LIT_JOIN = re.compile(r'([A-Z_][A-Z_0-9]*)\s*/\s*f?"([^"]+)"')


def _dir_prefixes(src):
    """`<常量> = [别的常量] / "子目录"` 的赋值链 → {常量: 仓库相对子目录}。

    例：`X = ROOT / ".cache/xcheck"` 之后 `CACHE = X / "dir_cache"`
    ⇒ CACHE 展开成 `.cache/xcheck/dir_cache`。迭代到不动点（上限 8 轮）。
    ⚠ `ROOT` 自身不在表里（它是仓库根，等价于空前缀）。
    """
    pref, lines = {}, src.splitlines()
    for _ in range(8):
        changed = False
        for ln in lines:
            m = _DIR_ASSIGN.match(ln)
            if not m:
                continue
            var, base, sub = m.group(1), m.group(2), m.group(3)
            if base is None:                      # `VAR = ROOT / "…"` —— ROOT 是根
                new = sub
            elif base == "ROOT":
                new = sub
            elif base in pref:
                new = (pref[base] + "/" + sub).strip("/")
            else:
                continue                          # base 还没解析出来，下轮再来
            if pref.get(var) != new:
                pref[var] = new
                changed = True
        if not changed:
            break
    return pref


def data_inputs(src):
    """抽出脚本的**数据类输入**，返回 (精确相对路径集, 模式串集, 裸字面量集)。

    - 精确相对路径：目录常量能解析出来、且文件名里没有 `{}`
    - 模式串：文件名是 f-string（`w_{key}.npy`）⇒ **静态无法定名**
    - 裸字面量：有数据类扩展名但前面没有可解析的目录常量
      ⇒ 只能退回 basename 匹配（弱近似）
    """
    pref = _dir_prefixes(src)
    exact, patterns, bare = set(), set(), set()
    for m in _LIT_JOIN.finditer(src):
        var, fname = m.group(1), m.group(2)
        if not fname.endswith(_DATA_EXT):
            continue
        if "{" in fname:
            patterns.add(fname)
            continue
        base = "" if var == "ROOT" else pref.get(var)
        if base is None:
            bare.add(fname)
        else:
            exact.add((base + "/" + fname).strip("/"))
    # 裸出现的数据类字面量（不在 `<常量> / "…"` 形态里）也计入 bare
    for m in _NPY_LITERAL.finditer(src):
        bare.add(m.group(1))
    return exact, patterns, bare


def tracked_basenames():
    return {os.path.basename(rel) for rel in tracked_files()}


def static_reachable(rel, artifact):
    """静态判定一个生成器在**干净克隆**上能不能跑（返回 档位, 细节）。

    ⚠ 修订 53：U1b 的口径从「只查 `.npy`」扩到「查全部数据类输入，
      且优先按目录拼接出的仓库相对路径**精确**判定」。
    ⚠ 两个方向都成立**仍然不等于**能跑（还有 torch / npz / 远端等未查项），
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

    tracked = set(tracked_files())
    exact, patterns, bare = data_inputs(src)

    # ⚠⚠⚠ **必须把「自己的输出」从输入里剔掉**，否则又是一个空洞通过。
    #   交付的那份 `<artifact>.json` 本身就是被跟踪的，把它算成「输入在仓库里
    #   有副本」⇒ 恒真。实测当场踩到：`linearity_law.py` 里**唯一**的数据类字面量
    #   是它自己的 DEFAULT_OUT（输出路径）⇒ 旧口径判「无判据」（对的），
    #   而扩了口径的新版本却报「静态可达（1 个输入有副本）」—— **换判据时把一个
    #   更隐蔽的空洞带进来了**。本项目第 N 次「量具自己先坏」。
    exact = {p for p in exact
             if os.path.basename(p) != artifact + ".json"}
    bare = {b for b in bare if os.path.basename(b) != artifact + ".json"}

    miss = sorted(p for p in exact if p not in tracked)
    # ⚠ 裸字面量只能按 basename 兜底，且**必须**标注是弱近似
    tb = tracked_basenames()
    miss_base = sorted(b for b in bare if os.path.basename(b) not in tb)

    why = []
    if miss:
        why.append("未跟踪的精确路径 %d 个：%s" % (len(miss), ", ".join(miss[:4])))
    if miss_base:
        why.append("未跟踪的裸字面量：%s" % ", ".join(miss_base[:4]))
    # ⚠ 即使先报了「输入不在仓库」，也要把 f-string 模式一并点出来 ——
    #   否则读者会以为「force-add 上面那几个就够了」，而实际还有一批定不出名的。
    if patterns:
        why.append("另有静态定不出名的输入模式：%s" % ", ".join(sorted(patterns)[:3]))
    if miss or miss_base:
        return "输入不在仓库", ["%s %s" % (rel, "；".join(why))]

    if patterns:
        # ⚠⚠ f-string 模式（如 `w_{key}.npy`）**静态无法定名** ⇒ 单列一档。
        #   **不许**顺着 basename 兜底报可达：那正是修订 52 判
        #   `build_subspace_readout.py` 时「0 个 .npy ⇒ 空真 ⇒ 静态可达」的同款错误。
        return "输入名不可静态定名", [
            "%s 的输入含 f-string 模式 %s ⇒ 静态判不出它要哪些文件，"
            "**不许**顺着兜底报可达" % (rel, ", ".join(sorted(patterns)[:3]))]

    if not exact and not bare:
        # ⚠⚠⚠ **空洞通过**：脚本里一个数据类字面量都没有 ⇒「都在仓库里」是**空真**。
        #   实测就踩到了：`linearity_law.py` 通过 `NpzReplayRunner` 读 npz，
        #   而它真正需要的远端 npz **根本不在仓库里**。
        # ⇒ 显式报「本项无判据」，**不许**顺着空真报可达。
        return "本项无判据", ["%s 里没有数据类文件字面量（它走别的读法）"
                              "⇒ 本项对它无判据，不能报可达" % rel]

    detail = ["%s 无写死路径；%d 个数据类输入按**精确路径**在仓库有副本"
              % (rel, len(exact))]
    if bare:
        detail.append("（另有 %d 个裸字面量按 basename 兜底命中，⚠ 弱近似："
                      "同名不同目录会误判）" % len(bare))
    return "静态可达", detail


def check_a3():
    """五个上游快照的生成器，在干净克隆上**静态可达**吗。

    ⚠ 本项**不改判 A2**：A2 判的命题为真，错的只是它的条目名（已改写）。
    ⚠⚠ 本项只做**静态**判定，**不执行**那些生成器（要 torch / 远端 npz）。
      「静态可达」**不等于**「跑通了」。
      ⚠ 真执行的判据是 **A4**（修订 53 新增）：它在 `git archive` 出来的
      **干净克隆**里把这几个脚本真跑一遍。两者分工：A3 查静态可移植性，A4 查真跑。
    """
    order = ["静态可达", "写死路径", "输入不在仓库", "输入名不可静态定名",
             "本项无判据", "仓库内无"]
    buckets = {k: [] for k in order}
    parts = []
    for u in UPSTREAMS:
        hits = writes_named_artifact(u)
        if not hits:
            buckets["仓库内无"].append(u)
            parts.append("%s.json → 仓库内无（已知欠账）" % u)
            continue
        cand = next((r for r, d in hits if d), hits[0][0])
        bucket, why = static_reachable(cand, u)
        buckets[bucket].append(u)
        parts.append("%s.json → %s（%s）" % (u, bucket, why[0][:100]))
    ok = all(not buckets[k] for k in order if k != "静态可达") \
        and len(buckets["静态可达"]) == len(UPSTREAMS)
    return check("A3 五个上游的生成器静态可达"
                 "（U1a 无写死绝对路径 ∧ U1b′ 数据类输入在仓库有副本；"
                 "非执行，不覆盖 torch/npz/远端/运行时缺库）",
                 ok, "；".join(parts))


# ---- 修订 53：A4 在**干净克隆**里真跑一遍 ------------------------------------------------
# ⚠⚠ A3 只做**静态**判定。A3 说「静态可达」也**不等于**跑得通 ——
#   还有运行时缺库、npz、远端这些静态查不到的东西。本项把那一层补上：
#   把 HEAD 解包成一个只含**被跟踪**文件的目录，在里面把这些脚本**真跑一遍**，
#   再把产物和交付的那份 `cmp` 比对。
#
# ⚠ 为什么不用 `git clone`（要拉全量、要写 .git）、也不用 `cp -r`：
#   `cp -r` 会把作者那十几项**未跟踪**的 WIP 一起带进去 —— 那就不是干净克隆了，
#   任何「输入齐不齐」的检查都会虚假通过。`git archive` 恰好只给被跟踪的文件。
#
# ⚠⚠ **诚实边界（必须写进 detail，不许含糊）**：克隆里**没有** `.cache/pylibs`
#   （`.cache/` 被 .gitignore 排除，第三方库不在仓库里）。
#   所以本项给 PYTHONPATH 指向**本机**那份 `.cache/pylibs`。
#   ⇒ A4 验的是**本项目自己的数据与代码是否闭合**，**不验第三方库是否可得**。
#   一个缺 numpy 的干净环境照样会让它失败 —— 那时失败原因是「缺库」，已单独分档。
_A4_ORDER = ("跑通且逐字节相同", "跑通但产物不同", "执行失败",
             "未执行（要 torch/npz/远端）", "克隆内无生成器")
_NEEDS_REMOTE = re.compile(r"import torch|NpzReplayRunner|\.npz")


def _missing_input(err, clone):
    """从异常文本里抠出缺的那个文件，并判它在仓库里到底有没有被跟踪。

    ⚠⚠ `os.path.realpath` 两边都要做：macOS 上 `tempfile` 给的是
    `/var/folders/…`，而子进程报的路径可能是 `/private/var/folders/…`
    ⇒ 不解析的话 `startswith` 会假阴性，把「缺输入」误报成「缺库·要远端」。
    """
    m = re.search(r"No such file or directory: '([^']+)'", err)
    if not m:
        return None, None
    p = m.group(1)
    cl, pp = os.path.realpath(clone), os.path.realpath(p)
    rel = os.path.relpath(pp, cl) if pp.startswith(cl) else None
    return (p, rel)


def a4_report():
    """A4 的本体：返回 `(ok, detail)`，**不打印、不记账**。

    ⚠ 拆出来是为了让守卫能直接断言它的 detail —— `check()` 一打印一记账就
      没法在测试里「跑一次并检查它说了什么」。
    """
    buckets = {k: [] for k in _A4_ORDER}
    detail = []
    targets = []
    for u in UPSTREAMS:
        rel = generator_of(u)
        if rel is None:
            detail.append("%s.json → 仓库内无生成器（不执行）" % u)
            continue
        targets.append((u, rel))

    tracked = set(tracked_files())
    with tempfile.TemporaryDirectory(prefix="chainclone_") as td:
        # ⚠ 走两个进程而不是 shell 管道：临时目录名里可能带空格，
        #   拼成 shell 字符串就得引号，少一层引号就少一层出错的地方。
        arc = subprocess.run(["git", "archive", "HEAD"], cwd=ROOT,
                             capture_output=True)
        tar = subprocess.run(["tar", "-x", "-C", td], input=arc.stdout,
                             capture_output=True)
        if arc.returncode or tar.returncode:
            return False, ("git archive 解包失败（git rc=%d / tar rc=%d）：%s"
                           % (arc.returncode, tar.returncode,
                              (tar.stderr or arc.stderr).decode("utf-8", "ignore")[:120]))
        # 先自证这个目录确实是「干净」的：被跟踪的文件在，未跟踪的不在。
        untracked_probe = "frontend/public/latent/data/dim_names.json"
        has_tracked = os.path.exists(os.path.join(
            td, ".cache/xcheck/build_evidence_ladder.py"))
        has_untracked = os.path.exists(os.path.join(td, untracked_probe))
        if not has_tracked:
            return False, "git archive 解包失败或不含被跟踪文件 ⇒ 本项无判据"
        detail.append("克隆自证：被跟踪文件在=%s、未跟踪的 %s 不在=%s"
                      % (has_tracked, os.path.basename(untracked_probe),
                         not has_untracked))
        if has_untracked:
            return False, "克隆里出现了未跟踪文件 ⇒ 它不是干净克隆，本项无判据"

        env = dict(os.environ)
        env["PYTHONPATH"] = os.path.join(ROOT, ".cache/pylibs")
        env["PYTHONPYCACHEPREFIX"] = os.path.join(td, "_pyc")
        for u, rel in targets:
            p = os.path.join(td, rel)
            if not os.path.exists(p):
                buckets["克隆内无生成器"].append(u)
                detail.append("%s.json → 克隆内无 %s" % (u, rel))
                continue
            src = open(p, encoding="utf-8", errors="ignore").read()
            if _NEEDS_REMOTE.search(src):
                buckets["未执行（要 torch/npz/远端）"].append(u)
                detail.append("%s.json → 未执行（要 torch/npz/远端）" % u)
                continue
            r = subprocess.run([sys.executable, os.path.relpath(p, td)], cwd=td,
                               env=env, capture_output=True, text=True,
                               timeout=900)
            if r.returncode != 0:
                miss_abs, miss_rel = _missing_input(r.stderr or r.stdout, td)
                why = "缺输入" if miss_rel else "缺库·要远端"
                # ⚠⚠ 这里第一版写成了 `(miss_abs or …splitlines() or [...])[-1]` ——
                #   miss_abs 是**字符串**不是列表，`[-1]` 取到的是它的**最后一个字符**
                #   （实测打出来是「执行失败·缺输入：y」）。字符串不许套 `[-1]`。
                # ⚠⚠ 第二版打印的是**绝对路径**，被 `[:90]` 截断成 89 字符 ——
                #   守卫据此做的「这个名字确实不在 git ls-files 里」断言就成了
                #   **空洞通过**（截断串当然不在）。⇒ 改打**仓库相对路径**：
                #   它才是可处置的东西，而且短到不会被截断。
                if miss_rel:
                    tail = miss_rel
                elif miss_abs:
                    tail = miss_abs
                else:
                    _lines = (r.stderr or r.stdout or "").strip().splitlines()
                    tail = _lines[-1] if _lines else "(无输出)"
                note = ""
                if miss_rel:
                    note = "（%s 在仓库里%s被跟踪）" % (
                        miss_rel, "" if miss_rel in tracked else "**未**")
                buckets["执行失败"].append("%s:%s" % (u, why))
                detail.append("%s.json → 执行失败·%s：%s%s" % (
                    u, why, tail[:90], note))
                continue
            out = os.path.join(td, DELIVERED_DIR, u + ".json")
            ref = os.path.join(ROOT, DELIVERED_DIR, u + ".json")
            if not os.path.exists(out):
                buckets["执行失败"].append("%s:没产出" % u)
                detail.append("%s.json → exit=0 但没产出文件" % u)
            elif _same_bytes(out, ref):
                buckets["跑通且逐字节相同"].append(u)
                detail.append("%s.json → 跑通且逐字节相同" % u)
            else:
                buckets["跑通但产物不同"].append(u)
                detail.append("%s.json → **跑通但产物不同**（exit=0，cmp 不等）" % u)

    attempted = len(targets) - len(buckets["未执行（要 torch/npz/远端）"])
    ok_items = buckets["跑通且逐字节相同"]
    summary = ("%d/%d 跑通且逐字节相同（另：产物不同 %d、执行失败 %d、"
               "未执行 %d、克隆内无 %d）" % (
                   len(ok_items), attempted,
                   len(buckets["跑通但产物不同"]),
                   len(buckets["执行失败"]),
                   len(buckets["未执行（要 torch/npz/远端）"]),
                   len(buckets["克隆内无生成器"])))
    detail.insert(0, summary)
    # ⚠⚠ 反空洞条款：一个都没执行 ⇒ 判红，不许报「0 失败」
    if attempted == 0:
        return False, "**本项无判据**：0 个生成器被执行 —— " + summary
    ok = (len(ok_items) == attempted and not buckets["跑通但产物不同"]
          and not buckets["执行失败"])
    return ok, "；".join(detail)


def check_a4():
    """在 `git archive` 出来的干净克隆里，把能本机跑的生成器真跑一遍。

    ⚠⚠ **反空洞条款（修订 53 写死）**：若一个都没执行（`n_attempted == 0`），
      本项**必须自己判红并报「本项无判据」**，**不许**报「0 失败」。
      「没跑」和「跑过没失败」必须能分辨 —— 这是预登记 §53.3.2 的第 6 条。
    """
    ok, detail = a4_report()
    return check("A4 干净克隆里真跑上游生成器"
                 "（真执行；第三方库取自本机 .cache/pylibs，不验缺库环境）",
                 ok, detail)


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
    check_a4()
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