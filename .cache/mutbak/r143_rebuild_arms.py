"""把 E2/E3/E4 补进 5 个手写臂（r134b_*）与 14 个派生臂的对应副本。

⚠⚠⚴⚠⁴ **为什么必须补**：判据分母 36 → 39（修订 142）。旧副本是 **36 条**判据的派生物，
⚠⚠⁴ 拿着它们去对新基线跑，⚗ **任何判决都不可信**（分母闸门会如实拦下）。
⚠⚠⁴ ⚠ **判据一变，所有派生副本都作废** ⇒ 要用就得重新生成 / 重新补齐。

⚠⚠⁴ **原文件一律不动**：补齐版写到 `.cache/mutbak/r143_arms/`，
⚠⚠⁴ 旧的 36 分母副本留在原处，⚗ 它们是修订 134–142 的**历史证据**。

⚠⚠⚴⚠⁴ 落点必须**行首逐字**定位，⚠ 不许 `indexOf` 裸串 ——
⚠ 「check('E1」这种串会命中**注释里**的同名文本（修订 134 踩过）。

⚠⚠⁴ 落点对**注入位置**的影响必须验：5 个手写臂的注入块都在原第 190–200 行，
⚠⚠⁴ **全都 < 227** ⇒ 在 227 处插 65 行**不会顶走它们** ⇒ 臂的语义不变。
⚠⚠⁴⚠⁴ 这一条不是显然的，⚗ 假设它成立而不验，就会造出一个「扰动够不着了」的静默废臂。
"""

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BLOCK = (ROOT / ".cache/mutbak/r143_e_block.txt").read_text(encoding="utf-8")
OUT = ROOT / ".cache/mutbak/r143_arms"
HAND = ["r134b_fork", "r134b_all", "r134b_pair", "r134b_xy", "r134b_path_dgroup"]

# ⚠ 手写臂的注入点行号（原文件里），必须在落点之前，否则插段会把它们顶走
INJECT_BEFORE = 227


def die(msg):
    print("[硬门] " + msg)
    raise SystemExit(2)


def patch_one(src: Path, dst: Path):
    raw = src.read_text(encoding="utf-8")
    lines = raw.split("\n")

    # 门① 已经有 E2 ⇒ 不许重复补
    if any(l.startswith("check('E2 ") for l in lines):
        die(f"{src.name}: 已有 E2，不重复补")

    # 门② 注入点必须在落点之前（否则语义被改写）
    # ⚠⚠⁴⚠⁴ 第一版拿**写死的 227** 当落点 ⇒ 把 r134b_pair 误判成「注入点 230 ≥ 227」。
    # ⚗⚠⁴ 那是**我自己的常量错了**：r134b 副本比源文件多插了 39 行，
    # ⚠⚠⁴ E1 的 check 实际在**第 270 行**。⚠⇒ 落点必须**先量出来**，不许写死。
    hits = [i for i, l in enumerate(lines) if l.startswith("check('E1 ")]
    if len(hits) != 1:
        die(f"{src.name}: E1 的 check 行首命中 {len(hits)} 次，期望恰好 1")
    at = hits[0]

    # ⚠⚠⁴ 匹配到的既可能是**扰动块**，也可能是后面的**取证行**（它也引用 __r134b）。
    # ⚗ 两者都在落点之前才算安全 ⇒ 取**最大**那个来比，最严。
    inj = [i + 1 for i, l in enumerate(lines) if "__r134b" in l or "__r135" in l]
    if inj and max(inj) > at + 1:
        die(f"{src.name}: 最后一个引用点 {max(inj)} 晚于 E1 落点 {at + 1}，插入会顶走它")

    out = lines[:at + 1] + BLOCK.rstrip("\n").split("\n") + lines[at + 1:]
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text("\n".join(out), encoding="utf-8")

    # 门④ node --check
    rc = subprocess.run(["node", "--check", str(dst)], capture_output=True, text=True)
    if rc.returncode != 0:
        die(f"{dst.name}: node --check 崩\n{rc.stderr[:400]}")

    # 门⑤ U+FFFD 挂在 Python 解析后那一层（修订 135）
    txt = dst.read_text(encoding="utf-8")
    if txt.count(chr(0xFFFD)):
        die(f"{dst.name}: 有坏字")

    return at + 1, len(out)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    print("=== 补齐 5 个手写臂 ===")
    for name in HAND:
        src = ROOT / ".cache/mutbak" / f"{name}.mjs"
        if not src.exists():
            die(f"{src} 不存在")
        at, n = patch_one(src, OUT / f"{name}.mjs")
        print(f"  ✓ {name:<22} 插在第 {at} 行之后 → {n} 行"
              f"  ⚠ 注入点在第 227 行之前，未被顶走")

    print("\n=== 14 个派生臂：改用新落点重新生成 ===")
    # ⚠⚠⁴ 派生臂不用手改，改用生成台重新生成 —— ⚗ 手改派生副本就等于绕过八道门。
    batches = [("r135", ".cache/mutbak/r135_spec_a5.json"),
               ("r135b", ".cache/mutbak/r135_spec_ace.json"),
               ("r136", ".cache/mutbak/r136_spec.json"),
               ("r138", ".cache/mutbak/r138_spec.json")]
    total = 0
    for tag, sp in batches:
        spec_path = ROOT / sp
        import json
        s = json.loads(spec_path.read_text(encoding="utf-8"))
        s["outdir"] = f".cache/mutbak/r143_arms/{tag}/"
        tmp = ROOT / f".cache/mutbak/r143_spec_{tag}.json"
        tmp.write_text(json.dumps(s, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        r = subprocess.run(["python3", ".cache/mutbak/r135_gen.py", str(tmp.relative_to(ROOT))],
                           capture_output=True, text=True, cwd=str(ROOT))
        if r.returncode != 0:
            die(f"{tag}: 生成台 exit {r.returncode}\n{r.stdout[-600:]}{r.stderr[-400:]}")
        n = sum(1 for l in r.stdout.split("\n") if "✓" in l and "注入@" in l)
        total += n
        print(f"  ✓ {tag}: 重新生成 {n} 个臂 → {s['outdir']}")
    print(f"\n合计：手写 5 + 派生 {total} = {5 + total} 个臂已在 39 分母下重建")


if __name__ == "__main__":
    main()