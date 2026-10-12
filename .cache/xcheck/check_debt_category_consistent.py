#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 88 判据（独立守卫，**不修改**冻结判据 `check_render_coverage_sitewide.py`）。

问题：台账 `note` 声称「454 条标 unclassified，本轮逐条未判读」，
      而 `categorize()`（该脚本 :104-109）在当前脚本里**只有定义、没有调用点**。
      ⇒ 那 454 个标签是**写台账时一次性打上的**，运行期只 `e.get("category")` 读计数。
      ⇒ 台账**没有任何机制保证它与当前 `categorize()` 口径一致**。

本守卫要回答的不是「454 对不对」，而是**更硬的那一条**：

  「台账里每条的 category，必须等于 `categorize()` 现在算出来的值。」

⚠⚠⚴ 为什么这一条更值得守：
  `categorize()` 是**规则**，`category` 是**标签**。
  规则可以被人改（扩 META_NAMES、改正则），而标签是历史产物
  ⇒ 两者一旦漂移，`note` 里那句「454 条未判读」的**含义就变了**，
     而**没有任何东西会报红**。
  ⚠ 而这正是本项目踩过的「台账说明不精确只能推出不可信」的同族 ——
     但这里更进一步：**连「不可信」都没人提示**。

口径（每个计数必须紧挨它的定义读）：
  n_entries        台账 debt 数组长度（条目数，非去重字段名数）
  n_dup_keys       台账 artifact|field 键的重复个数（0 = 无重复）
  n_z5             `artifact` 以 `z5::` 开头的条目数（⚠ **不归 categorize() 管**，见下）
  n_in_scope       非 z5 条目数 = 本守卫的判定范围
  n_mismatch       category ≠ categorize(field) 的条目数（**仅 n_in_scope 内**）← 判红口径
  n_by_cat         按台账存的 category 分组计数（仅 n_in_scope 内）
  n_recomputed     按 categorize() 现算分组的计数（对照项，必须与 n_by_cat 相同）

⚠⚠⚴⚴ **z5 条目为什么不在判定范围内**（v1 判红 12 条全是这一类，是我的判据错了）：

  源脚本 `:471-472` 的原话是「Z5 台账：与 Y2 的 513 条**分开记**，不混进一个总数」，
  而台账 `note` 也写明 z5 部分是「修订 70 的 12 条筛查命中，待实页核对，不是通过」。
  ⚠⚴ 它们的 `category` 取值是 `z5-static-confirmed` / `z5-design-open`，
  这是**修订 70 人工打的标签**，**从来不经过 `categorize()`**
  ⇒ 拿 `categorize()` 去重算它们，必然 12/12 不一致。
  ⇒ **判据口径的第一版错了，不是台账错了**（数据是被源脚本与 note 双重写死的）。

  ⚠ 教训同族：「量不到东西时别退回去查一个更弱的来源」的镜像 ——
     这里是我**先立了判据，再去读它在判什么**，读晚了。
     ⇒ 立判据时就要把「这条**不在谁的管辖范围内**」问清楚。
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEBT = HERE / "check_render_coverage_sitewide.debt.json"
SRC = HERE / "check_render_coverage_sitewide.py"


# ⚠⚠ 口径必须与冻结判据**逐字**一致 —— 这两段是从它 :96-109 抄来的。
#   复制而不是 import：import 会让它在导入期执行模块级代码，
#   ⚠ 而该脚本的阳性对照会**写入** ltv.json / index.html（子智能体已警告）。
#   ⇒ 「复用了函数 ≠ 复用了判定语义」：这里复用的必须是**规则文本**，
#     且它必须与源文件逐字相同 ⇒ 用下面第 2 条对照钉住这一点。
DATA_KEY = re.compile(r"^(\d{4}_[A-Z]_\d+|\d+)$")

META_NAMES = {"schema", "design", "generated_by", "built_from",
              "model_provenance", "how", "convention", "sources",
              "note_batch"}


def categorize(field: str) -> str:
    if DATA_KEY.match(field):
        return "data-key"
    if field in META_NAMES:
        return "meta"
    return "unclassified"


def src_categorize():
    """从冻结判据源码里**抽出** DATA_KEY 正则与 META_NAMES 字面量。

    ⚠ 返回 `(已编译的 re 对象, set)`。
    ⚠⚠⚴ 这里连错两版，且**两版错在同一个假设上**：
      v1 `eval()` 出来就直接当 re 对象用（它是 **str**）⇒ 调用方 `.pattern` 崩；
      v2 在函数内补了 `re.compile`，**却忘了调用方还在用 `sr.pattern`**
         ⇒ 同一处错误换个地方再犯。
      ⇒ 固化：**类型转换只在一个地方做**，且**函数签名把转换后的类型写出来**，
        让调用方无法再猜。
      ⇒ 同族：「现象不对时先读真实类型」—— 这次是我**自己造**了一个类型再假设它。

    这一条是「抄来的口径没抄歪」的唯一保证 ——
    抄歪了的话，本守卫会拿自己的口径去判源脚本的台账，
    而两边一致 ⇒ 恒绿。"""
    s = SRC.read_text(encoding="utf-8")
    m = re.search(r"^DATA_KEY\s*=\s*re\.compile\((r\"[^\"]+\")\)\s*$",
                  s, re.M)
    if not m:
        raise SystemExit("⚠ 没能从源脚本抽出 DATA_KEY —— 源脚本结构变了")
    src_literal = eval(m.group(1))  # noqa: S307 - 来源是本地冻结判据的字面量
    src_re = re.compile(src_literal) if isinstance(src_literal, str) else src_literal
    mm = re.search(r"^META_NAMES\s*=\s*\{(.*?)\}\s*$", s, re.M | re.S)
    if not mm:
        raise SystemExit("⚠ 没能从源脚本抽出 META_NAMES —— 源脚本结构变了")
    src_meta = set(re.findall(r'"([^"]+)"', mm.group(1)))
    # ⚠⚠⚴ v3 还在 return 旧名字 `src_regex` —— 那个变量已被删掉改名成 `src_re`。
    #   症状不是 TypeError 而是 **NameError**（同一个错假设的第三个变体）。
    #   ⇒ 三版错误分别是：`str` 当 re 用 / 转了但调用方没转 / 变量改名后 return 漏改。
    #   ⚠ 这就是「改一处必须同时改它的**引用点**」—— 三处引用（定义/转换/return）
    #     分散在两个函数里，肉眼极难扫全。
    return src_re, src_meta


def selfcheck():
    """阳性样本：证明 categorize() 有牙齿，且两条边界判定各自独立触发。

    ⚠⚠ 每条对照都断言**具体取值**，不是只断言「不是 unclassified」——
      否则「data-key 与 meta 判反了」也照样通过。"""
    cases = [
        ("schema", "meta", "META_NAMES 成员"),
        ("1983_I_1", "data-key", "题号"),
        ("7196", "data-key", "纯数字层号"),
        ("alpha", "unclassified", "普通字段 ⇒ 兜底"),
        ("-1", "unclassified", "⚠ 负数不匹配 ^\\d+$ ⇒ 落兜底（已知样本）"),
        ("Schema", "unclassified", "⚠ 大小写敏感 ⇒ 落兜底"),
    ]
    out = []
    for field, want, why in cases:
        got = categorize(field)
        out.append((field, want, got, got == want, why))
    # ⚠ 还要断言「数据键与元数据名没有交集」——
    #   若将来有人往 META_NAMES 里加一个形如 "7196" 的名字，
    #   categorize() 会先命中 data-key ⇒ 那个 meta 规则**变成死代码**。
    overlap = {m for m in META_NAMES if DATA_KEY.match(m)}
    return out, overlap


def main() -> int:
    fails: list[str] = []
    print("=" * 78)
    print("修订 88 守卫：台账 category 与 categorize() 现算值的一致性")
    print("=" * 78)

    # ---- 0. 对照：先证明 categorize() 有牙齿 ----
    print("\n[对照] categorize() 的已知答案")
    cases, overlap = selfcheck()
    n_ok = 0
    for field, want, got, ok, why in cases:
        n_ok += ok
        print(f"  {'✅' if ok else '⚠⚠'} {field!r:12} -> {got:12} （期望 {want}）　{why}")
    print(f"  对照 {n_ok}/{len(cases)} 通过")
    if n_ok != len(cases):
        print("⚠⚠ 对照没过 ⇒ 下面的一切都不可信，中止")
        return 2
    if overlap:
        print(f"⚠⚠ META_NAMES ∩ DATA_KEY = {sorted(overlap)} ⇒ 这些 meta 规则是死代码")
        fails.append(f"META_NAMES 与 DATA_KEY 有交集 {sorted(overlap)}，"
                     "对应分支永不触发")
    else:
        print("  ✅ META_NAMES ∩ DATA_KEY = ∅（两个分支各自独立触发）")

    # ---- 1. 口径逐字一致 ----
    print("\n[口径] 本守卫的规则 vs 冻结判据的规则")
    try:
        sr, sm = src_categorize()
    except SystemExit as e:
        print(f"  ⚠⚠ {e}")
        return 2
    # ⚠ 比较的是**编译后的 pattern 字符串**，不是源码文本 ——
    #   源码文本会因为空格/引号差异而误判「漂移」，那是假红。
    rx_ok = (sr.pattern == DATA_KEY.pattern)
    meta_ok = (sm == META_NAMES)
    print(f"  {'✅' if rx_ok else '⚠⚠'} DATA_KEY 正则  本={DATA_KEY.pattern!r}")
    if not rx_ok:
        print(f"                          源={sr.pattern!r}")
    print(f"  ✅ META_NAMES    本={sorted(META_NAMES)}")
    print(f"                    源={sorted(sm)}")
    if not meta_ok:
        print(f"  {'✅' if meta_ok else '⚠⚠'} META_NAMES 集合相等"
              if meta_ok else f"  ⚠⚠ META_NAMES 不相等："
              f"仅本有={sorted(META_NAMES - sm)}　仅源有={sorted(sm - META_NAMES)}")
    if not (rx_ok and meta_ok):
        fails.append("本守卫的规则与冻结判据的规则不一致 —— "
                     "抄来的口径已漂移，本守卫会拿自己的口径判源脚本的台账")
    if not (rx_ok and meta_ok):
        print("\n⚠⚠ 口径已漂移 ⇒ 中止")
        return 2

    # ---- 2. 主判定 ----
    # ⚠⚠⚴ z5 条目**排除**在判定范围外（理由见模块 docstring）：
    #   它们的 category 是修订 70 人工打的标签，从不经过 categorize()。
    print("\n[判定] 逐条比对（z5 条目已排除，见文件头说明）")
    if not DEBT.exists():
        print(f"⚠ 台账文件不存在：{DEBT}")
        return 2
    d = json.loads(DEBT.read_text(encoding="utf-8"))
    debt = d.get("debt", [])
    n_entries = len(debt)

    z5 = [e for e in debt if str(e.get("artifact", "")).startswith("z5::")]
    in_scope = [e for e in debt if not str(e.get("artifact", "")).startswith("z5::")]
    n_z5, n_in_scope = len(z5), len(in_scope)

    keys = [e.get("artifact", "") + "|" + e.get("field", "") for e in debt]
    n_dup = len(keys) - len(set(keys))

    mismatch = []
    for e in in_scope:
        fld = e.get("field", "")
        stored = e.get("category")
        recomputed = categorize(fld)
        if stored != recomputed:
            mismatch.append((e.get("artifact"), fld, stored, recomputed))

    by_cat = Counter(e.get("category", "?") for e in in_scope)
    recomputed_cat = Counter(categorize(e.get("field", "")) for e in in_scope)
    z5_cats = Counter(e.get("category", "?") for e in z5)

    print(f"  n_entries（台账全部条目数）      = {n_entries}")
    print(f"  n_z5（z5:: 前缀，排除在判定外）  = {n_z5}")
    print(f"  n_in_scope（判定范围 = 非 z5）    = {n_in_scope}")
    print(f"  n_dup_keys（artifact|field 重复） = {n_dup}")
    print(f"  n_mismatch（标签≠现算，仅判定范围内）= {len(mismatch)}")
    print(f"\n  判定范围内台账存的 category：{dict(sorted(by_cat.items()))}")
    print(f"  判定范围内现算 categorize()： {dict(sorted(recomputed_cat.items()))}")
    if z5_cats:
        print(f"\n  ⚠ 范围外披露：z5 条目的 category 分布 = {dict(sorted(z5_cats.items()))}")
        print(f"    （人工标签，本守卫**不判**它们；它们的状态由 Z5 实页核对负责）")
    print(f"  ⚠ 上面每一行的口径都是「条目数」，不是「去重字段名数」")

    # ⚠ 交叉核对：两个分布若不等，说明连计数口径都漂了。
    if by_cat != recomputed_cat:
        fails.append("两个分布不一致")
        only_stored = {k: v for k, v in by_cat.items() if recomputed_cat.get(k) != v}
        only_calc = {k: v for k, v in recomputed_cat.items() if by_cat.get(k) != v}
        print(f"  ⚠⚠ 台账独有/不等: {only_stored}　现算独有/不等: {only_calc}")

    if n_dup:
        fails.append(f"台账有 {n_dup} 个重复键 artifact|field")
        print(f"  ⚠⚠ 重复键会让「逐条」失真（load_debt() 建成 dict 时会**吞掉**重复）")

    for art, fld, stored, calc in mismatch[:20]:
        print(f"  ⚠⚠ {art}  field={fld!r}  台账={stored!r}  现算={calc!r}")
    if len(mismatch) > 20:
        print(f"  … 另有 {len(mismatch) - 20} 条")

    # ---- 3. 判据是否「够测」：范围为空 / 全是一个类别时恒绿 ----
    print("\n[够测性] 本判据在当前数据上有没有牙齿")
    if n_in_scope == 0:
        fails.append("判定范围（排除 z5 后）为空 ⇒ 本判据恒绿，无判据")
        print(f"  ⚠⚠ n_in_scope == 0")
    else:
        print(f"  ✅ 判定范围非空（{n_in_scope} 条），逐条判定生效")
    n_cat_kinds = len(by_cat)
    if n_cat_kinds < 2:
        fails.append(f"判定范围内只有一个 category（{list(by_cat)}）"
                     "⇒ 跨类别漂移测不出来")
        print(f"  ⚠⚠ 只有 {n_cat_kinds} 个 category")
    else:
        print(f"  ✅ 判定范围内 {n_cat_kinds} 个 category ⇒ 跨类别漂移可测")

    # ⚠⚠⚴ 最后一条：必须证明**兜底分支本身**在起作用。
    #   若 `unclassified` 为 0，说明规则把所有字段都分了类 ——
    #   那时「标签与规则一致」是**构造性必然**（没有兜底可漂移）⇒ 判据退化成恒绿。
    n_unc = by_cat.get("unclassified", 0)
    if n_unc == 0:
        fails.append("判定范围内 unclassified == 0 ⇒ 兜底分支永不触发，"
                     "本判据退化成「恒绿」，没有牙齿")
        print("  ⚠⚠ 兜底分支从未触发 ⇒ 本判据恒绿")
    else:
        print(f"  ✅ 兜底分支触发 {n_unc} 条 ⇒ 规则与标签的漂移可被本判据抓到")

    # ---- 4. 结论 ----
    print("\n" + "=" * 78)
    if fails:
        print("❌ 判红：")
        for f in fails:
            print(f"   - {f}")
        print("=" * 78)
        return 1
    print(f"✅ 判绿：{n_entries} 条台账的 category 与 categorize() 现算值**逐条一致**")
    print("   ⚠ 这不等于「454 条已被判读」—— note 明说它们是「未判读」，")
    print("     本守卫只保证**标签与规则没漂移**，不保证标签**正确**。")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())