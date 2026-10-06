#!/usr/bin/env python3
"""生成 ORPHAN_DECORATION / ORPHAN_DEBT 的登记字面量。

⚠⚠ **key 必须由程序算，不能手写。** 两处都会出事：
  · `okey` = (page, tag, head[:24])，`assign_keys` 再按**出现次序**加 `#k` 后缀。
    少写一个字 ⇒ 那条匹配不上 ⇒ C6 仍红且看不出错在哪；
    多写一条 ⇒ 登记簿自己报「登记过但页面上没有」，制造假警报。
  · `page` 字段**探针产物里没有**（每条 unmarked 上都没有），是判据在
    `unmarked_by_page` 装配时用产物自报的 `page` 注入的。少了它，key 会全是 '?'。

⚠⚠ 口径必须与 `scan_panel_coverage.py` **逐字一致**，否则次序后缀会错位：
    · 两页先按**页名排序**再拼成全局列表（不是按页各算一遍）；
    · 过滤是 `orphan and not shell`，然后 `not volatile`；
    · `assign_keys` 对**整个全局列表**调用，不是对每页调用。
  第一版生成器按页各算一遍，产出里 7 条的 `#k` 与判据实际用的对不上 ——
  那 7 条会静默地登记不上，C6 照红，而输出里看不出是哪里的错。

⚠⚠ 分类是**人的判断**；脚本只负责把判断绑到正确的 key 上，并做对账。

用法:
  python3 .cache/xcheck/gen_orphan_registry.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import scan_panel_coverage as S  # noqa: E402

# 与判据里的 BLOCKS / LATENT_BLOCKS 同序；页名从产物自报字段取
PROBE = [("root", os.path.join(REPO, ".cache/browser_verify/panel_blocks.json")),
         ("latent", os.path.join(REPO, ".cache/browser_verify/panel_blocks_latent.json"))]

# ── 人的判断：按**全局出现次序**分类 ────────────────────────────────────
# 下标 1..N，对应「按页名排序后拼起来的 orphan-and-not-shell-and-not-volatile 列表」。
# ⚠ 页面结构一变，下标整体平移 ⇒ 那个方向是安全的（对不上，不会误登记）。
DECORATION_IDX = set()

DECOR_BY_TEXT = {
    # latent：标签栏 / 图例定义 / 两个 <h2> 标题 / 脚注锚 —— 导航或读法说明，零可核数字
    "隐空间 2D 候选词", "当前层 L14 L0 = embedding", "L0 = embedding 输出",
    "隐空间 2D 投影 · L14", "当前 token 已生成 token", "TOP-64 候选词",
    "每根 = 一步，高度", "[29] post-canvas",
    # root：h1/h2/小标题、图例项、按钮、层选择器、播放速度
    "Reasoning3D", "REASONING PATH", "confident (low entropy)",
    "very uncertain", "self-check token", "current token",
    "▶ Run ⏸ pause", "Layer (residual stream) layer", "Playback speed",
    "STEERING CONTROL", "INTERPRETATION", "WHERE CONFIDENCE LIVES",
    "TRAJECTORY", "REASONING TRACE",
}

DECOR_REASON = ("纯导航 / 读法说明（标题、图例、按钮、选择器选项），"
                "承载零可核数字 —— 删掉它不会少任何能被核对的东西。")
DEBT_NUM = ("带**可核的数字**，而没有任何按标记读的判据能定位到它 —— "
            "数字本身没错，缺的是「谁核过它」的入口。这是**欠账**："
            "该给它加一个稳定标记，再补一条读它的判据。")
DEBT_CLAIM = ("承载**读者必须读到才能读懂这个面板在说什么**的主张，"
              "同样没有按标记读的判据能定位它。这是**欠账**。")


def build():
    """逐字照搬 scan_panel_coverage 的装配口径。"""
    by_page = {}
    for pg, path in PROBE:
        raws = json.load(open(path, encoding="utf-8"))
        selfpage = raws.get("page")
        for it in raws.get("unmarked") or []:
            it = dict(it)
            it["page"] = selfpage          # ← 判据第 581 行做的事
            by_page.setdefault(selfpage, []).append(it)
    unmarked = [it for pg in sorted(by_page) for it in by_page[pg]]   # ← 第 583 行
    orphans = [u for u in unmarked if u.get("orphan") and not u.get("shell")]  # 1114
    return [u for u in orphans if not u.get("volatile")]            # 1158


def main():
    items = build()
    keys = S.assign_keys(items)          # ← 对**全局列表**调用，不是每页
    rows = []
    for i, (okey, key, u) in enumerate(zip(map(S.okey, items), keys, items), 1):
        rows.append((i, okey, key, u))

    is_dec = lambda o: any(o[2].startswith(t) for t in DECOR_BY_TEXT)
    dec = [(k, u) for i, o, k, u in rows if is_dec(o)]
    debt = [(k, u) for i, o, k, u in rows if not is_dec(o)]

    print(f"装饰簿 {len(dec)} ／ 欠账簿 {len(debt)} ／ 合计 {len(dec)+len(debt)}")
    print(f"两页待归属共 {len(items)} 段 —— 对账 "
          f"{'**通过**' if len(dec)+len(debt) == len(items) else '**失败**'}")
    nsuff = [k for k, u in dec+debt if "#" in k[2]]
    print(f"其中带次序后缀的 {len(nsuff)} 条（同名块在页面上出现多次）："
          f"{[k[2] for k in nsuff]}")
    print(f"分类按文本前缀匹配（DECOR_BY_TEXT {len(DECOR_BY_TEXT)} 条）；"
          f"未落进任何一条前缀的：{len(debt)} 条，全部记为欠账")

    print("\n--- ORPHAN_DECORATION ---")
    for k, u in dec:
        print(f'    {k!r}: "{DECOR_REASON}",')
    print("\n--- ORPHAN_DEBT ---")
    for k, u in debt:
        has_num = any(ch.isdigit() for ch in k[2])
        print(f'    {k!r}: "{"{DEBT_NUM}" if has_num else DEBT_CLAIM}",')


if __name__ == "__main__":
    sys.exit(main())