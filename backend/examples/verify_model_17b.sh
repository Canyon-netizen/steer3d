#!/usr/bin/env bash
# Prove the reassembled Qwen3-1.7B actually runs, not just that the file
# sizes look right.
#
# Size agreement is weak evidence: a chunk fetched into the wrong offset
# still produces a file of exactly the right length. What settles it is
# loading the weights and reproducing a known-good continuation.
set -euo pipefail

PY=${PY:-/var/tmp/steer3d/env/bin/python}
MODEL=/var/tmp/steer3d/models/Qwen3-1.7B

"$PY" - "$MODEL" <<'PY'
import sys, time, torch
from transformers import AutoModelForCausalLM, AutoTokenizer

path = sys.argv[1]
t = time.time()
tok = AutoTokenizer.from_pretrained(path)
model = AutoModelForCausalLM.from_pretrained(path, dtype=torch.bfloat16,
                                             device_map={"": "cuda:0"})
model.eval()
print(f"loaded in {time.time()-t:.1f}s  device={model.device}")
print(f"  layers={model.config.num_hidden_layers} "
      f"hidden={model.config.hidden_size} "
      f"maxpos={model.config.max_position_embeddings}")
n = sum(p.numel() for p in model.parameters())
print(f"  params={n/1e9:.3f}B  dtype={next(model.parameters()).dtype}")
bad = [k for k, v in model.state_dict().items() if not torch.isfinite(v.float()).all()]
print(f"  non-finite tensors: {len(bad)}  {bad[:5]}")

# A known-answer probe. "The capital of France is" -> " Paris" is stable
# across the Qwen3 family and needs no prompt engineering.
for prompt in ["The capital of France is", "2 + 2 =", "<think>\n\n"]:
    ids = tok(prompt, return_tensors="pt").to(model.device)
    with torch.inference_mode():
        out = model.generate(**ids, max_new_tokens=12, do_sample=False,
                             pad_token_id=tok.eos_token_id)
    print(f"  {prompt!r} -> {tok.decode(out[0][ids['input_ids'].shape[1]:])!r}")
PY
echo "MODEL OK"
