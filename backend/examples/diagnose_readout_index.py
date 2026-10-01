"""Which `hidden_states` index is the one the logits were computed from?

This is a diagnostic, not a deliverable. It exists because the float32 final
residual, read out through ``model.norm`` and ``lm_head``, disagrees with the
token the model actually emitted on 2 of 6 problems -- by 0.42 and 2.42 logits,
with the read-out preferring the *control* arm's token both times.

Everything about the obvious explanations has been ruled out by measurement:

  * index convention -- the read-out reproduces the emitted token at every
    offset in {+-1, +-2, +-3} and fails only at the divergence step itself;
  * fp16 storage -- the quantisation moves a logit by 0.001-0.003 against
    top-2 gaps of 0.17-2.46, three orders of magnitude too small;
  * a mis-tied unembedding -- ``lm_head.weight`` and
    ``model.embed_tokens.weight`` are bit-identical in the checkpoint.

So the assumption being tested is the plainest one: that ``hidden_states[28]``
is the input to the final norm. For each index in the tuple, read it out and
compare against the logits the model actually returned from that same forward
pass. Whatever reproduces them is the index the logits come from.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_intervention import ResidualSteerer  # noqa: E402
from run_long_cot import build_prompt, load_model, load_problems  # noqa: E402

RMS_EPS = 1e-6


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model-path", required=True)
    ap.add_argument("--problems", required=True)
    ap.add_argument("--id", required=True)
    ap.add_argument("--steps", type=int, default=60)
    ap.add_argument("--layer", type=int, default=20)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--dtype", default="float32")
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    model, tok = load_model(a.model_path, a.device, a.dtype)
    n_layers = int(model.config.num_hidden_layers)
    probs = {str(p.get("id")): p for p in load_problems(a.problems, None)}
    prob = probs[a.id]
    prompt = build_prompt(tok, prob["prompt"])
    print(f"model n_layers={n_layers}  problem {a.id}")

    # Load the steering vector the same way the collector did.
    from core.steering import SteeringRegistry
    reg = SteeringRegistry(Path("output/steering_vectors"))
    reg.load()
    reg.load_layer_scales(Path("output/layer_profiles.json"))
    vec = reg.scaled("confidence_up", 0.2, a.layer)

    report = {}
    for arm in ("control", "steered"):
        steerer = ResidualSteerer(model, a.layer)
        if arm == "steered":
            steerer.set_vector(vec)
        ids, rows = [], []
        with steerer, torch.inference_mode():
            enc = tok(prompt, return_tensors="pt").to(model.device)
            out = model(**enc, output_hidden_states=True, use_cache=True,
                        return_dict=True)
            past = out.past_key_values
            nxt = int(torch.argmax(out.logits[0, -1, :]))
            for step in range(a.steps):
                if step > 0:
                    if nxt == tok.eos_token_id:
                        break
                    ids.append(nxt)
                    out = model(input_ids=torch.tensor([[nxt]], device=model.device),
                                past_key_values=past, output_hidden_states=True,
                                use_cache=True, return_dict=True)
                    past = out.past_key_values
                nxt = int(torch.argmax(out.logits[0, -1, :]))

                # Compare every hidden_states index against the logits this
                # same forward produced, at the step that predicted ids[step].
                if step != a.steps - 1:
                    continue
                real = out.logits[0, -1, :].to(torch.float32)
                entry = {"emitted": nxt, "real_argmax": int(real.argmax()),
                         "n_entries": len(out.hidden_states), "indices": []}
                for i in range(len(out.hidden_states)):
                    h = out.hidden_states[i][0, -1, :].to(torch.float32)
                    variants = {}
                    for tag, vec_in in (
                            ("norm", h / torch.sqrt((h * h).mean() + RMS_EPS)),
                            ("raw", h)):
                        got = model.lm_head(
                            model.model.norm(vec_in.unsqueeze(0).unsqueeze(0))
                            if tag == "norm" else vec_in.unsqueeze(0).unsqueeze(0))
                        got = got[0, -1, :].to(torch.float32)
                        variants[tag] = {
                            "max_abs_diff": float((got - real).abs().max()),
                            "argmax": int(got.argmax()),
                        }
                    entry["indices"].append({
                        "i": i,
                        "max_abs_diff": variants["norm"]["max_abs_diff"],
                        "argmax": variants["norm"]["argmax"],
                        "raw_max_abs_diff": variants["raw"]["max_abs_diff"],
                        "raw_argmax": variants["raw"]["argmax"],
                        "matches": int(variants["norm"]["argmax"])
                                   == int(real.argmax()),
                    })
                # The literal numbers, so a constant offset cannot hide inside a
                # max-abs summary.
                h28 = out.hidden_states[n_layers][0, -1, :].to(torch.float32)
                x28 = h28 / torch.sqrt((h28 * h28).mean() + RMS_EPS)
                got28 = model.lm_head(
                    model.model.norm(x28.unsqueeze(0).unsqueeze(0)))[0, -1, :]
                top = torch.topk(real, 5)
                entry["top5"] = [{
                    "id": int(i), "text": tok.decode([int(i)]),
                    "real": float(v), "readout": float(got28[i]),
                    "diff": float(got28[i] - v),
                } for v, i in zip(top.values, top.indices)]
                entry["mean_signed_diff"] = float(
                    (got28 - real).mean())
                entry["max_signed_diff"] = float((got28 - real).max())
                entry["min_signed_diff"] = float((got28 - real).min())
                rows.append(entry)
        report[arm] = rows[0] if rows else None
        e = report[arm]
        if e:
            best = min(e["indices"], key=lambda d: d["max_abs_diff"])
            bestraw = min(e["indices"], key=lambda d: d["raw_max_abs_diff"])
            print(f"\n[{arm}] emitted={e['emitted']}  out.logits.argmax={e['real_argmax']}  "
                  f"hidden_states 条目数={e['n_entries']}")
            print(f"  做 norm 读出最接近的下标: hs[{best['i']}] max|差|={best['max_abs_diff']:.3e}")
            print(f"  不做 norm 读出最接近的下标: hs[{bestraw['i']}] max|差|={bestraw['raw_max_abs_diff']:.3e}")
            print(f"  符号差: mean={e['mean_signed_diff']:+.4f} "
                  f"min={e['min_signed_diff']:+.4f} max={e['max_signed_diff']:+.4f}")
            print(f"  {'id':>7} {'真实':>9} {'读出':>9} {'差':>9}  词")
            for t in e["top5"]:
                print(f"  {t['id']:>7} {t['real']:>9.3f} {t['readout']:>9.3f} "
                      f"{t['diff']:>+9.3f}  {t['text']!r}")

    if a.out:
        Path(a.out).write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
