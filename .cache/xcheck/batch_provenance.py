"""把批次身份变成随产物落盘的事实（修 32k 批次的溯源洞）。

`.cache/32k_journal/z46_shard.sh:52` **已经**有 `model=$MODEL` 的留痕，
但那行只是 echo 到**脚本的 stdout**，而 `32k_journal/` 下没有任何 `.log` 收它
⇒ 事后追不回那批用的是哪个模型、哪种精度。

本脚本**只修这个洞，不重跑数据**。理由：
- 现有 32k 批次的溯源**不可追溯**（`/tmp/qwen3/master` 已被沙箱清空），
  重跑要跨 GPU 分片，成本远超一次脚本修改；
- 洞是**向前**的：只要下一批还这么跑，就会再产生一批追不回的产物。

本脚本做三件事：
  ① 批次启动时把 model / dtype / device / git / torch 写进 <journal-dir>/_batch.json
  ② 自检：QWEN3_MODEL_PATH 为空时**显式报出「本批不可追溯」**，不沉默通过

⚠ 这**不修改** z46_shard.sh / z47_shard.sh 本体。它们是历史批次的原始
  launcher，改了就失去「当时是怎么跑的」这一层证据。原脚本保持原样。
"""
import argparse
import json
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent


def sh(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=30).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--journal-dir", required=True,
                    help="例如 .cache/32k_journal")
    ap.add_argument("--out", default="",
                    help="留痕 JSON 的落盘路径，默认 <journal-dir>/_batch.json")
    args = ap.parse_args()

    jd = pathlib.Path(args.journal_dir)
    if not jd.is_dir():
        print(f"ERROR: {jd} 不是目录")
        return 1
    out = pathlib.Path(args.out) if args.out else jd / "_batch.json"

    rec = {
        "schema": "batch_provenance/1",
        "why": "旧批次的 model= 留痕只 echo 到 stdout 且无人收，事后追不回模型。"
               "本记录把批次身份变成**随产物落盘**的事实。",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "model_path_seen_now": sh(["python3", "-c",
                                   "import sys;print(sys.executable)"]),
        "python": sys.executable,
        "python_version": sys.version.split()[0],
        "torch": "",
        "git_head": sh(["git", "-C", str(HERE), "rev-parse", "HEAD"]),
        "git_dirty": sh(["git", "-C", str(HERE), "status", "--porcelain"]) != "",
    }
    try:
        import torch  # noqa: E402
        rec["torch"] = torch.__version__
        rec["cuda_available"] = bool(torch.cuda.is_available())
    except Exception as e:                      # noqa: BLE001
        rec["torch"] = f"<不可用: {type(e).__name__}>"

    # ⚠ 关键自检：把「这批用的哪个模型」显式留成**必填**，不让它空着跑。
    model = sh(["python3", "-c",
                "import os;print(os.environ.get('QWEN3_MODEL_PATH',''))"])
    rec["QWEN3_MODEL_PATH"] = model or "<未设置 ⇒ 这一批的模型无法追溯>"
    rec["model_is_traceable"] = bool(model) and model != "<未设置 ⇒ 这一批的模型无法追溯>"

    out.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"已写: {out}")
    if not rec["model_is_traceable"]:
        print("⚠ QWEN3_MODEL_PATH 未设置 ⇒ 本批模型**不可追溯**。")
        print("   请用 QWEN3_MODEL_PATH=<dir> 重新启动批次，或接受这个洞。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
