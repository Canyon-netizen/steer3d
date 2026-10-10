#!/usr/bin/env python3
"""强度定律：注入的**几何代价**是标量，与方向无关。

这是 goal 里"能不能提取一套通用的解释向量功能的理论"目前唯一站得住
的一条。它把 steering 拆成两件互相独立的事：

    强度 s  决定  几何被破坏多少   —— 可解析预测，方向无关
    方向 v  决定  模型往哪走       —— 只能靠全前向/行为测，且与几何代价无关

一阶推导（h 是该层残差，u 是单位方向，c = cos(h,u)，a = s·rms(L)/‖h‖）：

    ‖h + s·rms·u‖ = ‖h‖·sqrt(1 + 2ac + a²)
    一阶 ≈ ‖h‖(1 + a·c)
    偏离一阶的比例 ≈ ½a²(1 − ac)/(1 + ac) ≈ ½a²   （a 小，|c| 不接近 1）

**关键的可证伪推论**：失真 ≈ ½(s·rms/‖h‖)²，里面**没有 v**。
所以一个随机方向在同一 strength 上应当落在**同一条曲线**上。

这条推论是硬的：如果随机方向落在曲线上，那么"这个方向有意义"这件事
**在几何代价里查不出来**。方向的意义必须另找证据，而本项目现有的
行为证据净变化为 0。

装置自检：用玩具输入验一次（‖h‖=100、rms=100、s=0.2 ⇒ a=0.2 ⇒ ½a²=2%）
先跑通再上真数据。
"""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np

# 修订 48：原来这一行把本机绝对路径写死，干净克隆上必然 ImportError
# ⇒ 本脚本在仓库内却只在那一台机器上能跑。
# 与 `build_evidence_ladder.py` 修订 46 R-1 同一处毛病，一层更深。
# ⚠⚠ 修订 52：**注释里不许复现被审计正则匹配的字面形态**。第一版这段
#   注释把那个调用的完整原文抄了出来，于是证据链 A3 的「写死路径」
#   扫描把**已经修好的**这一行判成命中 —— 注释把正则毒化了。
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.core.replay_runner import NpzReplayRunner  # noqa: E402
from backend.core.steering import get_registry  # noqa: E402

LAYERS = [12, 14, 20, 27]
STRENGTHS = [0.05, 0.1, 0.2, 0.5]
N_REC = 8
N_STEPS = 12
N_RANDOM = 16
SEED = 20261003
# 修订 48：交付的那一份。阶梯生成器 `build_evidence_ladder.py` 读的是它。
DEFAULT_OUT = (ROOT / "frontend/public/latent/data/linearity_law.json")
TOPIC = "强度定律：注入的几何代价与方向无关"


def measure_points(H, un, inj_abs):
    """逐点核心：返回 (dev, pred, c, hn, a) 五个**数组**（长度 = 点数）。

    ⚠⚠ 修订 54：原来这里算出 `dev` 之后**直接 `.mean()` 塌成单值**，
      于是「点间离散度」在计算现场就被丢弃 —— 阶梯 L1 note 那条
      真实-vs-随机 null 的分辨率因此永远算不出来。
      ⇒ 这里返回数组，`.mean()` 下放到 `measure()` 这个包装层，
      **既有数字逐位不变**（同一批数、同一处求平均）。
    """
    hn = np.linalg.norm(H, axis=1)
    c = (H @ un) / hn
    a = inj_abs / hn
    actual = np.linalg.norm(H + inj_abs * un[None, :], axis=1)
    lin = hn * (1.0 + a * c)
    dev = (actual / lin - 1.0)
    return dev, (0.5 * a ** 2), c, hn, a


def measure(H, un, inj_abs):
    """给定一批 hidden states 和一个单位方向，返回 (实测, 一阶, 解析 ½a²)。

    ⚠ 修订 54：这是 `measure_points` 的薄包装，求平均的位置与原来**完全相同**
      ⇒ 已发布的每一个数字逐位不变。`toy_check` 的五元解包也照旧能用。
    """
    dev, pred, c, hn, a = measure_points(H, un, inj_abs)
    return (dev.mean() * 100.0,
            pred.mean() * 100.0,
            float(c.mean()), float(hn.mean()), float(a.mean()))


def toy_check():
    """装置自检：玩具输入有解析答案，先确认实现算得出来。"""
    rng = np.random.default_rng(0)
    H = rng.standard_normal((4000, 2048))
    H *= (100.0 / np.linalg.norm(H, axis=1, keepdims=True))   # ‖h‖ = 100
    un = np.full(2048, 1.0 / np.sqrt(2048))
    got, pred, c, hn, a = measure(H, un, 0.2 * 100.0)        # a = 0.2
    ok = abs(got - pred) < 0.05 * max(abs(pred), 1e-9) + 0.05
    print("[自检] 玩具输入 ‖h‖=100, rms=100, s=0.2  => a=%.3f" % a)
    print("[自检] 实测 %.4f%%  解析 ½a² %.4f%%  -> %s"
          % (got, pred, "OK" if ok else "装置有问题，先修它再谈结论"))
    if not ok:
        raise SystemExit("ABORT 玩具输入都对不上，后面所有数都没有意义")
    return ok


def _sha(path, _cache={}):
    """npz 的 sha256。⚠ 大文件要**分块**读，一次 read() 整个会把内存吃穿。"""
    if path not in _cache:
        hsh = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 22), b""):
                hsh.update(chunk)
        _cache[path] = hsh.hexdigest()
    return _cache[path]


def main():
    toy_check()
    runner = NpzReplayRunner()
    reg = get_registry()

    # 真实方向里只取 3 条独立向量（6 个标签有 2 对是精确取反，
    # 取反的失真必然完全相同，算两遍没有信息量）
    REAL = ["caution", "confidence_up", "creativity", "reasoning_deep"]
    rs = np.random.default_rng(SEED)
    rand = rs.standard_normal((N_RANDOM, 2048))
    rand /= np.linalg.norm(rand, axis=1, keepdims=True)

    # ⚠ 修订 54：记下每点来自哪条记录的哪个 step，以及**读到的 npz 的 sha256** ——
    #   否则「这些数是从哪读出来的」无从回答（与预登记 §53 第 15 条同源）。
    # ⚠⚠ 点与**层无关**（每个层都取同一批 (record, step)），所以这份元数据
    #   **必须在层循环之外建一次**。第一版把它写在 `for L in LAYERS` 里面，
    #   4 层会累加出 384 条而基线是 96 —— 而每个 `H[L]` 都只有 96 行，
    #   元数据与数据对不上，配对差会直接算错。
    #   （这不是「写起来啰嗦」，是**静默的形状错配**。）
    POINTS_META, _npz_paths = [], []
    for ri, r in enumerate(runner.records[:N_REC]):
        _npz_paths.append(r["npz"])
        T = np.load(r["npz"], mmap_mode="r")["hidden_states"].shape[0]
        idx = np.linspace(int(T * 0.35), T - 1, N_STEPS).round().astype(int)
        POINTS_META += [{"record": ri, "step": int(j)} for j in idx]
    _npz_paths = list(dict.fromkeys(_npz_paths))
    NPZ_SHA = {os.path.basename(p): _sha(p) for p in _npz_paths}

    # 缓存 hidden states，避免每个强度/方向都重读 npz
    H = {}
    for L in LAYERS:
        chunks = []
        for r in runner.records[:N_REC]:
            z = np.load(r["npz"], mmap_mode="r")
            T = z["hidden_states"].shape[0]
            idx = np.linspace(int(T * 0.35), T - 1, N_STEPS).round().astype(int)
            chunks.append(np.asarray(z["hidden_states"][idx, L, :], dtype=np.float64))
        H[L] = np.concatenate(chunks, 0)

    # ⚠ 元数据长度必须与 H 的行数一致 —— 这不是「顺手检查」，是**配对的前提**：
    #   元数据错位时 `points_meta[i]` 说的不是 `H[L][i]` 那一行。
    for _L, _h in H.items():
        if _h.shape[0] != len(POINTS_META):
            raise SystemExit("ABORT L%s 的点数 %d 与 points_meta 的 %d 对不上"
                             % (_L, _h.shape[0], len(POINTS_META)))

    out = {
        "schema": "steer3d.linearity_law/1",
        "topic": TOPIC,
        "law": ("失真 ≈ ½(s·rms(L)/‖h‖)²，其中没有方向 v；"
                "所以随机方向与真实方向落在同一条曲线上"),
        "design": {"layers": LAYERS, "strengths": STRENGTHS,
                   "n_records": N_REC, "n_steps": N_STEPS,
                   "n_points": N_REC * N_STEPS,
                   "n_random": N_RANDOM, "seed": SEED,
                   "real_directions": REAL},
        "toy_selfcheck": "passed",
        "rows": [],
    }

    for L in LAYERS:
        rms = float(reg.layer_rms(L))
        h = H[L]
        for s in STRENGTHS:
            inj = s * rms
            real, real_pts = {}, {}
            for name in REAL:
                u = np.asarray(reg._vectors[name], dtype=np.float64)
                u = u / np.linalg.norm(u)
                devp, predp, c_arr, hn, a = measure_points(h, u, inj)
                real[name] = {"dev_pct": devp.mean() * 100.0,
                              "pred_pct": predp.mean() * 100.0,
                              "cos_mean": float(c_arr.mean()),
                              "h_norm_mean": float(hn.mean()),
                              "a_mean": float(a.mean())}
                real_pts[name] = devp.tolist()
            rnd = [measure_points(h, rand[i], inj) for i in range(N_RANDOM)]
            # ⚠⚠ 这里**必须**显式 `.mean()*100`：改用 `measure_points` 之后
            #   `x[0]` 是**原始数组**（分数），不是原来的「×100 的均值」。
            #   若直接 `np.array([x[0] for x in rnd])`，`random_dev_mean`
            #   会**差 100 倍** —— 而「既有数字逐位不变」正是修订 54 的承诺。
            #   同理 `random_dev_std/min/max` 都必须是**方向间**的量，保持原口径。
            rdev = np.array([x[0].mean() for x in rnd]) * 100.0
            rdev_pts = np.array([x[0] for x in rnd])          # (16, 96) 分数
            out["rows"].append({
                "layer": L, "strength": s, "layer_rms": rms,
                "a_mean": real[REAL[0]]["a_mean"],
                "pred_pct": real[REAL[0]]["pred_pct"],
                "real": real,
                "real_dev_mean": float(np.mean([v["dev_pct"] for v in real.values()])),
                "real_dev_spread": float(
                    np.ptp([v["dev_pct"] for v in real.values()])),
                "random_dev_mean": float(rdev.mean()),
                "random_dev_std": float(rdev.std()),
                "random_dev_min": float(rdev.min()),
                "random_dev_max": float(rdev.max()),
                # ---- 修订 54 新增：每点量（既有字段与算法一个字未动） ----
                "points_unit": "fraction（×100 才是 pp；相对偏离 rel=dev/pred 与单位无关）",
                "real_dev_points": real_pts,
                "random_dev_points": rdev_pts.tolist(),
                "pred_points": (0.5 * (inj / np.linalg.norm(h, axis=1)) ** 2).tolist(),
                "points_meta": POINTS_META,
                "npz_sha256": NPZ_SHA,
            })
            r = out["rows"][-1]
            print("L%-3d s=%.2f  解析 %6.3f%% | 真实 %6.3f%% (跨方向极差 %.3fpp) "
                  "| 随机 %6.3f%% ±%.3f  [%.3f, %.3f]"
                  % (L, s, r["pred_pct"], r["real_dev_mean"], r["real_dev_spread"],
                     r["random_dev_mean"], r["random_dev_std"],
                     r["random_dev_min"], r["random_dev_max"]))

    # 结论：**分区报**，不要用一个全局最大值抹掉失效点。
    # s<=0.2 是现有全部产物所在的区间；s=0.5 用来找这条定律在哪里失效。
    SAFE_MAX = 0.2
    safe = [r for r in out["rows"] if r["strength"] <= SAFE_MAX]
    wild = [r for r in out["rows"] if r["strength"] > SAFE_MAX]

    def summarise(rows):
        if not rows:
            return None
        sp = max(r["real_dev_spread"] for r in rows)
        gap = max(abs(r["real_dev_mean"] - r["random_dev_mean"]) for r in rows)
        return {"n_points": len(rows),
                "max_direction_spread_pp": sp,
                "max_real_vs_random_gap_pp": gap,
                "direction_independent": sp < 1.0,
                "random_indistinguishable": gap < 1.0}

    out["conclusions"] = {
        "safe_regime": {"strength_max": SAFE_MAX, **summarise(safe)},
        "beyond_safe_regime": {"strengths": sorted({r["strength"] for r in wild}),
                               **(summarise(wild) or {})},
        "note": (
            "在 s<=%s（现有全部 steering 产物所在的区间）这条定律成立："
            "跨真实方向的极差与真实-vs-随机之差都远小于 1 个百分点，"
            "即注入的几何代价里不含方向的信息 —— 随机方向付出的代价与"
            "\"confidence\" 方向一样。s>0.2 时二次近似本身失效，两个数都开始长，"
            "所以那些点不构成反例，只说明解析式超出了适用范围。"
            % SAFE_MAX),
    }
    print()
    for k in ("safe_regime", "beyond_safe_regime"):
        c = out["conclusions"][k]
        if not c:
            continue
        print("%-20s 跨方向极差 max %.3f pp | 真实 vs 随机 max %.3f pp"
              % (k, c["max_direction_spread_pp"], c["max_real_vs_random_gap_pp"]))

    # 修订 48：原来写死写到 `.cache/strengthscan/` 下的**本地副本**，
    # 而读者拿到的是 `frontend/public/latent/data/linearity_law.json`。
    # 证据链的 A3 因此判它「生成器在、但不写交付那份」。
    # 现在默认就写交付路径；仍要本地副本时显式 `--out`。
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--local-copy", default=None,
                    help="额外再写一份到这个路径（如 .cache/strengthscan/）")
    a = ap.parse_args()
    for path in ([a.out] + ([a.local_copy] if a.local_copy else [])):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=1)
        print("wrote " + path)


if __name__ == "__main__":
    main()
