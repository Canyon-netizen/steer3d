"""源级判据：电路景观页面与进度图面板（读源码，不渲染）。

## 为什么是**源级**判据

框架 §8.3 ⑨ 立了一条规矩：**判据与被观测层要分别记账**——
页面判据集里一定存在"渲染上看不见"的改动类别。
反过来，§8.9 立的规矩是：**页面上真实渲染的块，是不是都被判据读过**。

本文件管的是另一类：**根本不用渲染就能看出来的缺陷**。
它们全部是**结构性**的（模式匹配），不是数值比较，所以不需要浏览器、不需要产物。

## 它抓的七件事

| # | 规矩 | 出处 |
|---|---|---|
| C1 | `aria-selected` 不能是恒真式 | 修订里已修过一处（`unit.id === unit.id`） |
| C2 | 组件里不能写死**已公布的效应量** | 框架 §8.3 ⑨：写死的数会静默过期 |
| C3 | "未测"必须显式写成"未测"，不能被读成 0 | 框架 §4.14 |
| C4 | "最高能声称"与"最高有数据"必须分开印 | 框架 §8.6 第一条设计错误 |
| C5 | "最便宜的下一级"**不得**用本级的 `needs` | 框架 §8.6 第三条设计错误（错位一级） |
| C6 | 单元表的两列范数不能同名 | 本轮 §1.3 ⑧：真值范数 vs 投影范数 |
| C7 | 口径条必须同时给出 p / regime / α / ‖h‖ / 随机臂 n / 信噪比 | 本轮 §2.4：效应量与可分辨度正交 |

## 它**不能**做什么

- 不能证明页面渲染出来是对的（那是浏览器判据的事）。
- 不能证明产物里的数字对（那是 `test_circuit_landscape_build.py` 的事）。
- C2 的禁用清单是**已公布的那批数**，不是全部数——
  它防的是"把结论抄进组件"，防不住"把新结论抄进组件"。
  ⇒ 所以清单要跟着 `docs/STEERING_LEDGER.md` 一起更新。
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / "frontend/components/CircuitLandscape.tsx"
PANEL = ROOT / "frontend/components/SteeringProgressMap.tsx"
BUILDER = ROOT / "backend/examples/build_circuit_landscape.py"

# docs/STEERING_LEDGER.md §2 里已公布的效应量。它们**不允许**出现在组件里：
# 组件必须从产物读，读到的是多少就显示多少。
PUBLISHED_FIGURES = [
    "0.1577", "0.3436", "0.1395", "0.0307", "0.0641", "0.0080",
    "1.6214", "1.1893", "1.8305", "1.3101", "1.7797", "0.0350",
    "0.0862", "0.1711", "0.6478", "0.8432", "2.25e-07",
    "11.6", "19.4", "2.9", "2.18", "1.30", "8.6", "17.1", "87.5",
]


def read(path: Path) -> str:
    assert path.exists(), "缺少文件：%s" % path
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------- C1
def test_c1_aria_selected_is_not_a_tautology():
    """`aria-selected={a === a}` 每一行都会显示为选中。"""
    offenders = []
    for path in sorted((ROOT / "frontend/components").glob("*.tsx")):
        for m in re.finditer(r"aria-selected=\{([^}]*)\}", read(path)):
            expr = m.group(1)
            sides = [s.strip() for s in expr.split("==")]
            if len(sides) == 2 and sides[0] == sides[1]:
                offenders.append("%s: aria-selected={%s}" % (path.name, expr))
    assert not offenders, "恒真的 aria-selected：%s" % offenders


# ---------------------------------------------------------------------- C2
def test_c2_components_do_not_hardcode_published_figures():
    for path in (COMPONENT, PANEL):
        src = read(path)
        hits = [f for f in PUBLISHED_FIGURES if f in src]
        assert not hits, "%s 里写死了已公布的数：%s" % (path.name, hits)


def test_c2b_builder_does_not_hardcode_published_figures():
    src = read(BUILDER)
    hits = [f for f in PUBLISHED_FIGURES if f in src]
    assert not hits, "build 脚本里写死了已公布的数：%s" % hits


# ---------------------------------------------------------------------- C3
def test_c3_not_measured_is_written_out_and_never_as_zero():
    panel = read(PANEL)
    assert "未测" in panel, "面板必须显式写出'未测'"
    # 不适用的格子要写明"不是 0"
    assert "不是 0" in panel, "不适用的格子必须写明它不是 0"
    builder = read(BUILDER)
    assert "未测" in builder, "构建器必须把未测显式写出来"


# ---------------------------------------------------------------------- C4
def test_c4_claimed_and_with_data_are_two_separate_reads():
    panel = read(PANEL)
    assert "ladder_max_level_claimed" in panel
    assert "ladder_max_level_with_data" in panel
    # 而且必须分别渲染，不能只印一个
    assert panel.count("ladder_max_level_with_data") >= 2, "两个数要分别出现在渲染里"


# ---------------------------------------------------------------------- C5
def test_c5_next_level_is_not_this_levels_own_needs():
    panel = read(PANEL)
    # 下一级那一列取的是 next，不是 needs
    assert "row.needs" not in panel, "下一级提示不能用本级的 needs"
    assert re.search(r"cells\?\.\[\"向量\"\]\?\.next", panel), "下一级提示必须读 next 字段"
    builder = read(BUILDER)
    assert "rows[i + 1:]" in builder, "next 必须从**上面**那一级算出来"


# ---------------------------------------------------------------------- C6
def test_c6_unit_table_headers_are_all_distinct():
    src = read(COMPONENT)
    m = re.search(r'\["原生单元".*?\]', src, re.S)
    assert m, "找不到单元表的表头数组"
    headers = re.findall(r'"([^"]+)"', m.group(0))
    assert len(headers) >= 8, "单元表至少要有 8 列（旧版 6 列）"
    assert len(headers) == len(set(headers)), "单元表有重名列：%s" % headers
    # 真值范数与投影范数必须分列，且列名要能分辨
    assert any("2048" in h for h in headers), "缺少 2048 维真值范数列"
    assert any("3D 投影" in h for h in headers), "缺少 3 维投影列"


# ---------------------------------------------------------------------- C7
def test_c7_context_bar_carries_the_six_things():
    src = read(COMPONENT)
    for needle, why in [
        ("baseline p", "工作点 p"),
        ("data-regime-badge", "读数带徽标"),
        ("α =", "剂量 α"),
        ("‖h‖", "注入位置的残差范数"),
        ("随机臂 n", "随机臂数量"),
        ("data-random-quantile", "随机臂能支撑的分位"),
        ("信噪比", "效应量与可分辨度之比"),
    ]:
        assert needle in src, "口径条缺少：%s（%s）" % (needle, why)


# ---------------------------------------------------------------------- C8
def test_c8_both_norm_spaces_are_labelled_in_the_panel():
    src = read(COMPONENT)
    assert "‖写入‖(2048)" in src
    assert "3D 投影" in src
    assert "data-unit-proj-norm" in src, "投影长度要能被判据读到"


# ---------------------------------------------------------------------- C9
def test_c9_ledger_panel_reports_the_aggregate_not_one_site():
    src = read(COMPONENT)
    assert "data-ledger-n-sites" in src
    builder = read(BUILDER)
    assert '"n_sites": len(sites)' in builder, "逐层账本必须标明聚合了几个 site"
    assert '"space"' in builder, "逐层账本必须标明范数空间（真值 / 投影）"
