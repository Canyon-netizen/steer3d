#!/usr/bin/env python3
"""Path patching：把第 L 层残差换掉，看这个 token 还解不解得出来。

判据全部在 `PATH_PATCHING_PREREG.md` 里**取数前**写死。
本脚本只允许**执行**那七道门，不允许新增门、不允许改门。
门不过就照实报不过。

节点编号约定（写死，避免和旧脚本差一位）：**节点 i = 第 i-1 层的输出**，
所以节点 1 = embedding 之后，节点 28 = 最后一层之后、进 norm/lm_head 之前。

用法:
  PYTHONPATH=.cache/pylibs python3 .cache/xcheck/probe_path_patching.py
"""
import json
import os
import re
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL = os.environ.get("PROBE_MODEL", os.path.join(REPO, "datasets", "models", "Qwen3-1.7B"))
# 源是 paired_v2，**不是** 784 步的 aime npz。
# 两者是两次不同的生成：paired_v2 是 max_new_tokens=128 / inject_layer=20 /
# direction=confidence_up 的那套，`divergence_readout.json` 里的 k 与 c_id/s_id
# 全部来自它。拿 784 步 npz 去对 k，第 1 题的 gen_ids[27] 是空格 ' '，
# 而 divergence_readout 记的 c_id=7046(' greater') —— 两套记录根本不是一回事。
PAIRED = os.environ.get("PAIRED_DIR", os.path.join(REPO, ".cache", "analysis", "paired_v2"))
DIVERGE = os.path.join(REPO, "frontend", "public", "latent", "data",
                        "divergence_readout.json")
OUT = os.environ.get("OUT", os.path.join(REPO, ".cache", "xcheck", "path_patching.json"))

log = lambda *a: print(*a, flush=True)

# ── 预登记的窗（来自上一轮 logit_lens 描述分析，不是本轮测的） ──────────
PREREG_WINDOW = [17, 18, 19, 20, 21, 22]
PREREG_TOPK = 6          # G5：excess 前 6 层
PREREG_MAXSPAN = 12      # G4：窗的跨度上限（层）
PREREG_MIN_W = 2         # G4：窗至少几层
PREREG_G1_STEP = 0.8     # G1：与录制一致率
PREREG_G2_PROB = 4       # G2：至少几题要有反事实
# ⚠ 算力裁剪（写死在这里，不是临场决定）：G2[num] 实测 1/6，按**本项目自己的门**，
#   num 臂的 G3-G6 一律是 na —— 它没有可解释的产出。算力全部给措辞臂。
#   留着它只会烧掉一半前向，换回一整列 na。要恢复：SKIP_NUM=0。
SKIP_NUM = os.environ.get("SKIP_NUM", "1") == "1"
ARMS = ("word",) if SKIP_NUM else ("num", "word")
# 幅度配平的随机对照臂（v4 引入）：v3 的教训是换题臂天生破坏更大，
# 任何「A 臂 − 换题臂」的量都被破坏幅度支配。这里让对照与该臂补丁
# **偏离 clean 的距离逐节点完全相等**，差别只剩方向。
NM_SEEDS = (20251006, 20251007)   # 两个对照取均值；单个随机方向方差太大
NM_ARMS = ("nm1", "nm2")

# ── 措辞改写表：人写，照题干写的，**取数前定死** ──────────────────────
# 打印 before/after 供核对。它有拟合风险，prereg 里已写明风险与限制。
WORD_EDITS = {
    "1983_I_1": {"old": "all exceed 1", "new": "are all larger than 1"},
    "1984_I_1": {"old": "10 * cot(", "new": "10 cot("},
    "1985_I_1": {"prefix": "Solve. "},
    "1986_I_1": {"old": "What is the sum of the solutions to the equation",
                 "new": "Compute the sum of all roots of"},
    "1987_I_1": {"old": "is called primitive if gcd(m, n) = 1",
                 "new": "is called primitive if m and n are relatively prime"},
    "1988_I_1": {"old": "Find the smallest positive integer n such that n^2 ends "
                        "in 1988 (the last four digits of n^2 are 1988).",
                 "new": "Find the least positive integer n whose square ends in "
                        "the digits 1988."},
}


def apply_word_edit(pid, prob):
    e = WORD_EDITS.get(pid)
    if not e:
        return None, None
    if "prefix" in e:
        return e["prefix"] + prob, (prob[:70], e["prefix"] + prob[:70])
    old, new = e["old"], e["new"]
    if prob.count(old) != 1:
        # 不唯一或找不到就**不用**，不许悄悄替换多处
        return None, (f"✗ 匹配 {prob.count(old)} 次", None)
    return prob.replace(old, new), (old, new)


def main():
    import numpy as np
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch.set_grad_enabled(False)

    # ── 取题 ──────────────────────────────────────────────────────────
    div = json.load(open(DIVERGE, encoding="utf-8"))
    items = []
    for pid, v in sorted(div["problems"].items()):
        pj = os.path.join(PAIRED, f"pair_{pid}.json")
        pn = os.path.join(PAIRED, f"pair_{pid}.npz")
        if not (os.path.exists(pj) and os.path.exists(pn)):
            log(f"⚠ {pid} 找不到 paired_v2 记录，跳过")
            continue
        items.append({"pid": pid, "json": pj, "npz": pn, "k": int(v["k"]),
                      "problem": json.load(open(pj, encoding="utf-8"))["problem"]})
    log(f"题 {len(items)} 道，分叉步 k = {[it['k'] for it in items]}")
    log(f"源 {PAIRED}")

    tok = AutoTokenizer.from_pretrained(MODEL)
    t0 = time.time()
    model = AutoModelForCausalLM.from_pretrained(MODEL, torch_dtype=torch.bfloat16)
    model.eval()
    nL = model.config.num_hidden_layers
    layers = model.model.layers
    log(f"模型载入 {time.time()-t0:.1f}s  {nL} 层")

    # prompt 构造**从生产模块原样 import**，不手抄。手抄 = 在包装层引入缺陷，
    # 缺陷会伪装成判据的红/绿，而判据本身一动不动。
    sys.path.insert(0, os.path.join(REPO, "backend", "examples"))
    try:
        from run_long_cot import build_prompt as prod_build_prompt
        log("prompt 构造：run_long_cot.build_prompt（生产代码原样）")
    except Exception as e:
        log(f"⚠ 生产 build_prompt 不可用（{type(e).__name__}: {e}）")
        prod_build_prompt = None

    # ── 工具 ──────────────────────────────────────────────────────────
    def as_enc(ids):
        """str → 编码；已是 (1,L) 张量就原样用。list[int] 也走编码。"""
        if hasattr(ids, "shape") and len(ids.shape) == 2:
            return {"input_ids": ids}
        if isinstance(ids, str):
            return tok(ids, return_tensors="pt")
        return tok(list(ids), return_tensors="pt")

    def resid(ids):
        """返回 {节点i: (2048,) 最后一位置残差}，节点 1..28"""
        enc = as_enc(ids)
        out = model(**enc, output_hidden_states=True)
        hs = out.hidden_states
        return {i: hs[i][0, -1, :].float().clone() for i in range(1, nL + 1)}, out.logits[0, -1].float()

    def gen(prompt, steps):
        """贪心生成 steps 步，返回 token 列表"""
        ids = tok(prompt, return_tensors="pt")["input_ids"]
        toks = []
        for _ in range(steps):
            lg = model(ids).logits[0, -1]
            t = int(torch.argmax(lg))
            toks.append(t)
            ids = torch.cat([ids, torch.tensor([[t]])], dim=1)
        return toks

    def patch_forward_batch(prompt_ids, node, vecs):
        """一次前向同时打 N 个补丁（batch=N）。

        为什么值得改成批量：每个节点原来要跑 8 次**完整前缀**的前向，
        而 batch=1 时 CPU 核是用不满的（实测 1.17 s/次 @81 tok）。
        8 个补丁的序列长度完全一样，堆成一个 batch 就能把核喂饱，
        实测快约 2.4 倍，6 题从 ~60 分钟降到 ~25 分钟。

        ⚠ 批量会轻微改变浮点结果。**G0 恒等自证正是为了这一点存在**：
           把干净臂自己的残差也放进 batch，若批量化引入偏差，恒等立刻会红。
        """
        n = len(vecs)
        enc = as_enc(prompt_ids)
        ids = enc["input_ids"].repeat(n, 1)
        V = torch.stack([v.to(torch.float32) for v in vecs])
        handle = layers[node - 1].register_forward_hook(
            lambda _m, _i, outp: _splice(outp, V))
        try:
            lg = model(ids).logits[:, -1, :].float()
            return [lg[b] for b in range(n)]
        finally:
            handle.remove()

    def _splice(outp, V):
        hs = outp[0] if isinstance(outp, tuple) else outp
        hs = hs.clone()
        for b in range(V.shape[0]):
            hs[b, -1, :] = V[b].to(hs.dtype)
        return ((hs,) + tuple(outp[1:])) if isinstance(outp, tuple) else hs

    def patch_forward(prompt_ids, node, vec):
        """把 prompt 最后位置在 node 层的残差换成 vec，返回该位置 logits"""
        handle = None
        if node is not None:
            def hook(_m, _i, outp):
                hs = outp[0] if isinstance(outp, tuple) else outp
                hs = hs.clone()
                hs[:, -1, :] = vec.to(hs.dtype)
                return ((hs,) + tuple(outp[1:])) if isinstance(outp, tuple) else hs
            handle = layers[node - 1].register_forward_hook(hook)
        try:
            enc = as_enc(prompt_ids)
            return model(**enc).logits[0, -1].float()
        finally:
            if handle is not None:
                handle.remove()

    def top1(lg):
        return int(torch.argmax(lg))

    # ── 题干改数字：确定性规则 + 打印核对 ──────────────────────────────
    def corrupt_problem(prob):
        """取题干里最后一个整数 n，改成题干里没出现过的 n+1（否则 n+2）。确定性。"""
        nums = re.findall(r"\d+", prob)
        if not nums:
            return None, None
        last = nums[-1]
        n = int(last)
        present = set(nums)
        new = n + 1 if str(n + 1) not in present else n + 2
        # 只替换**最后一次出现**，避免误伤题干里重复的数字
        i = prob.rfind(last)
        out = prob[:i] + str(new) + prob[i + len(last):]
        return out, (prob[max(0, i - 40):i] + last + prob[i + len(last):i + len(last) + 25],
                     prob[max(0, i - 40):i] + str(new) + prob[i + len(last):i + len(last) + 25])

    # ── 描述对照：logit lens（自己算，不读产物） ────────────────────────
    def lens_argmax(vec):
        h = model.model.norm(vec.view(1, 1, -1).to(model.dtype))
        return top1(model.lm_head(h)[0, -1])

    # ── 主循环 ────────────────────────────────────────────────────────
    per_problem, g0_fail, g1_steps, g1_ok = [], [], 0, 0
    g_nm_fail = []          # 幅度配平自证：对照与该臂的偏离量必须逐节点相等
    t_start = time.time()
    for idx, it in enumerate(items):
        pid, k, f = it["pid"], it["k"], it["npz"]
        z = np.load(f)
        g_ids = [int(x) for x in z["control_ids"]]      # paired_v2 的干净臂生成
        text = prod_build_prompt(tok, it["problem"])
        p_ids = tok(text, return_tensors="pt")["input_ids"]
        base_ids = torch.cat([p_ids[0],
                              torch.tensor(g_ids[:k], dtype=p_ids.dtype)]).view(1, -1)

        # G1：干净臂重跑，与录制一致吗
        replay = gen(text, k)
        agree = sum(int(a == b) for a, b in zip(replay, g_ids[:k]))
        g1_steps += k; g1_ok += agree
        log(f"\n[{idx+1}/{len(items)}] {pid}  k={k}  G1 一致 {agree}/{k}"
            f"  被解释 token={g_ids[k]}({tok.decode([g_ids[k]])!r})"
            f"  prompt {p_ids.shape[1]} tok")

        # 三臂残差
        clean_res, clean_lg = resid(base_ids)
        clean_tok = top1(clean_lg)

        cprob, diff = (None, None) if SKIP_NUM else corrupt_problem(it["problem"])
        arm_label_note = "num"
        if cprob is None:
            log(f"   ⚠ {arm_label_note} 臂不可用（"
                + ("SKIP_NUM=1，按 G2[num] 已判 na 而裁掉" if arm_label_note == "num"
                   else "题干的改写规则没命中") + "）")
            content_res = content_lg = None
        else:
            ctext = prod_build_prompt(tok, cprob)
            ctoks = gen(ctext, k)
            c_ids = torch.cat([tok(ctext, return_tensors="pt")["input_ids"][0],
                               torch.tensor(ctoks, dtype=torch.long)]).view(1, -1)
            content_res, content_lg = resid(c_ids)
            log(f"   content 改题：…{diff[0]!r} → …{diff[1]!r}")
            log(f"   content 重生成前 44 字：{''.join(tok.decode(ctoks))[:44]!r}")
        content_tok = top1(content_lg) if content_lg is not None else None

        arm_label_note = "word"
        # ── word 臂：改说法（人写表，取数前定死，逐条打印核对） ──────────
        wprob, wdiff = apply_word_edit(it["pid"], it["problem"])
        if wprob is None:
            log(f"   ⚠ {pid} 没有词表条目，word 臂不可用")
            word_res = word_lg = None
        else:
            wtext = prod_build_prompt(tok, wprob)
            wtoks = gen(wtext, k)
            w_ids = torch.cat([tok(wtext, return_tensors="pt")["input_ids"][0],
                               torch.tensor(wtoks, dtype=torch.long)]).view(1, -1)
            word_res, word_lg = resid(w_ids)
            log(f"   word   改说法：{wdiff[0]!r}")
            log(f"              → {wdiff[1]!r}")
            log(f"   word   重生成前 44 字：{''.join(tok.decode(wtoks))[:44]!r}")
        word_tok = top1(word_lg) if word_lg is not None else None

        nb = items[(idx + 1) % len(items)]
        nz = np.load(nb["npz"])
        n_p = tok(prod_build_prompt(tok, nb["problem"]), return_tensors="pt")["input_ids"]
        n_g = [int(x) for x in nz["control_ids"][:k]]
        n_ids = torch.cat([n_p[0], torch.tensor(n_g, dtype=n_p.dtype)]).view(1, -1)
        null_res, null_lg = resid(n_ids)
        null_tok = top1(null_lg)
        log(f"   null = {nb['pid']}  同一步序号 k={k}")

        clean_lp = torch.log_softmax(clean_lg, -1)
        token2expl = int(g_ids[k])
        logp_clean = float(clean_lp[token2expl])

        rows = []
        for node in range(1, nL + 1):
            # ── 一次前向同时打 8 个补丁 ──────────────────────────
            # 顺序固定：恒等 / num / word / null / num的两个配平对照 / word的两个配平对照
            vecs, slots = [clean_res[node]], ["id"]
            if content_res is not None: vecs.append(content_res[node]); slots.append("num")
            if word_res is not None:    vecs.append(word_res[node]);    slots.append("word")
            vecs.append(null_res[node]); slots.append("null")
            for arm_name, res in (("num", content_res), ("word", word_res)):
                if res is None:
                    # ⚠ 占位向量**必须补齐**，否则 slots 比 vecs 长，
                    #   后面的 dict(zip(slots, lgs)) 整体错位：措辞臂会拿到
                    #   换题臂的残差，而 G0 恒等自证照样绿（第一个槽位是对齐的）
                    #   —— 全绿的判据恰好掩盖了这个 bug。
                    slots += [f"nm_{arm_name}0", f"nm_{arm_name}1"]
                    vecs += [clean_res[node], clean_res[node]]
                    continue
                dev = res[node] - clean_res[node]
                for si, sd in enumerate(NM_SEEDS):
                    g = torch.Generator().manual_seed(int(sd) * 1000 + node)
                    u = torch.randn(model.config.hidden_size, generator=g)
                    u = u / (u.norm() + 1e-9)
                    vecs.append(clean_res[node] + dev.norm() * u)
                    slots.append(f"nm_{arm_name}{si}")
            # 槽位与向量必须一一对应。长度不等就当场炸，
            # 不许它错位之后靠「某个门还是绿的」蒙混过去。
            assert len(vecs) == len(slots), (pid, node, len(vecs), len(slots))
            lgs = dict(zip(slots, patch_forward_batch(base_ids, node, vecs)))
            missing = [k for k in slots if k not in lgs]
            assert not missing, (pid, node, "槽位没拿到结果", missing)

            id_ok = top1(lgs["id"]) == clean_tok
            if not id_ok:
                g0_fail.append({"pid": pid, "node": node})
            lg_c, lg_w, lg_n = lgs.get("num"), lgs.get("word"), lgs["null"]

            def probe(lg, arm_tok):
                """记录原 token 的 logp、该臂自己 token 的 logp、top1。

                v1 的教训：只记原 token 的 logp，量到的其实是「这个补丁有多陌生」，
                不是「这个补丁带来了什么内容」。两个都记，主量在判据里选。
                """
                if lg is None:
                    return None
                lp = torch.log_softmax(lg, -1)
                return {"logp_target": float(lp[token2expl]),
                        "logp_arm": float(lp[arm_tok]) if arm_tok is not None else None,
                        "top1": top1(lg),
                        "max_abs_dlogit": float((lg - clean_lg).abs().max())}

            pc = probe(lg_c, content_tok)
            pw = probe(lg_w, word_tok)
            pn = probe(lg_n, null_tok)
            pm = {arm: [probe(lgs.get(f"nm_{arm}{si}"), t) for si in (0, 1)]
                  for arm, t in (("num", content_tok), ("word", word_tok))}

            def cos(x, y):
                """该臂残差与干净臂的余弦 = 陌生度的直接读数。
                不印这个数，读者没法判断幅度配平到底有没有必要。"""
                if x is None:
                    return None
                return float(torch.nn.functional.cosine_similarity(
                    x.view(1, -1).float(), y.view(1, -1).float()))
            base_lp = pn["logp_target"]
            rows.append({
                "node": node,
                "identity_top1_ok": id_ok,
                "lens_agree": int(lens_argmax(clean_res[node]) == token2expl),
                "lens_logit_target": float(
                    model.lm_head(model.model.norm(
                        clean_res[node].view(1, 1, -1).to(model.dtype)))[0, -1, token2expl]),
                "clean_norm": float(clean_res[node].norm()),
                "num_norm": float(content_res[node].norm()) if content_res else None,
                "word_norm": float(word_res[node].norm()) if word_res else None,
                "null_norm": float(null_res[node].norm()),
                # 陌生度：同题臂与换题臂各自离 clean 有多远。
                # G6 抓到的就是「null 天生更陌生」，这个数把它摆到台面上。
                "cos_num": cos(content_res[node] if content_res else None, clean_res[node]),
                "cos_word": cos(word_res[node] if word_res else None, clean_res[node]),
                "cos_null": cos(null_res[node], clean_res[node]),
                "num": pc, "word": pw, "null": pn,
                "flip_num": int(pc["top1"] == content_tok) if pc else None,
                "flip_word": int(pw["top1"] == word_tok) if pw else None,
                "flip_null": int(pn["top1"] == null_tok),
                # 旧量（v1 用的那个）：扣的是「补丁有多陌生」
                "excess_num": (float(base_lp - pc["logp_target"]) if pc else None),
                "excess_word": (float(base_lp - pw["logp_target"]) if pw else None),
                # 新量：换上该臂的残差后，**该臂自己的 token** 相对换上外来残差
                # 抬升了多少。两者都记，判决门两个都跑，分歧要报。
                "transfer_num": (float(pc["logp_arm"] - pn["logp_arm"]) if pc and content_tok is not None else None),
                "transfer_word": (float(pw["logp_arm"] - pn["logp_arm"]) if pw and word_tok is not None else None),
                # 幅度配平对照的实测：偏离 clean 的范数必须与该臂逐节点相等
                "nm_num": [x["logp_arm"] if x else None for x in pm["num"]],
                "nm_word": [x["logp_arm"] if x else None for x in pm["word"]],
                "nm_num_top1": [x["top1"] if x else None for x in pm["num"]],
                "nm_word_top1": [x["top1"] if x else None for x in pm["word"]],
                "dev_norm_num": float((content_res[node] - clean_res[node]).norm()) if content_res else None,
                "dev_norm_word": float((word_res[node] - clean_res[node]).norm()) if word_res else None,
                # 主量：与两个幅度配平随机对照取均值比。
                # 两个对照与该臂补丁偏离 clean 的范数**逐节点相等**，
                # 所以这个差只可能来自方向，不可能来自幅度。
                # pm[arm] 装的是 probe 字典，取 logp_arm 才是可比��标量。
                # 上一版把 pm 当浮点求和，TypeError 当场炸 —— 总比悄悄算错强。
                "excessm_num": (float(pc["logp_arm"]
                                      - sum(x["logp_arm"] for x in pm["num"]) / len(pm["num"]))
                                if pc and content_tok is not None
                                and pm["num"] and all(x is not None for x in pm["num"]) else None),
                "excessm_word": (float(pw["logp_arm"]
                                       - sum(x["logp_arm"] for x in pm["word"]) / len(pm["word"]))
                                 if pw and word_tok is not None
                                 and pm["word"] and all(x is not None for x in pm["word"]) else None),
            })
            # 幅度配平的自证：对照残差与干净臂的距离必须与该臂补丁**逐节点相等**
            for arm, res in (("num", content_res), ("word", word_res)):
                if res is None:
                    continue
                a_, b_ = (res[node] - clean_res[node]).norm(), rows[-1][f"dev_norm_{arm}"]
                if abs(float(a_) - float(b_)) > 1e-3:
                    g_nm_fail.append({"pid": pid, "node": node, "arm": arm,
                                      "dev": float(a_), "ctrl": float(b_)})
            if node % 7 == 0:
                log(f"     节点 {node}/{nL}  ({time.time()-t_start:.0f}s)")
        per_problem.append({
            "pid": pid, "k": k, "npz": os.path.basename(f),
            "token_explained": token2expl,
            "token_text": tok.decode([token2expl]),
            "clean_top1": clean_tok, "clean_top1_text": tok.decode([clean_tok]),
            "clean_logp_target": logp_clean,
            "g1_agree": agree, "g1_steps": k,
            "num_top1": content_tok,
            "num_top1_text": tok.decode([content_tok]) if content_tok is not None else None,
            "num_differs": int(content_tok is not None and content_tok != clean_tok),
            "num_edit": diff,
            "word_top1": word_tok,
            "word_top1_text": tok.decode([word_tok]) if word_tok is not None else None,
            "word_differs": int(word_tok is not None and word_tok != clean_tok),
            "word_edit": wdiff,
            "null_pid": nb["pid"],
            "null_top1": null_tok, "null_top1_text": tok.decode([null_tok]),
            "rows": rows,
        })
        json.dump({"prereg": os.path.basename(__file__) + " + PATH_PATCHING_PREREG.md",
                   "model": MODEL, "n_layers": nL,
                   "node_convention": "node i = output of layer i-1",
                   "partial": True, "n_done": len(per_problem),
                   "problems": per_problem},
                  open(OUT, "w"), ensure_ascii=False, indent=2)
        log(f"   clean={tok.decode([clean_tok])!r}  num={content_tok}  "
            f"word={word_tok}  null={tok.decode([null_tok])!r}   "
            f"[{time.time()-t_start:.0f}s]")

    json.dump({"prereg": os.path.basename(__file__) + " + PATH_PATCHING_PREREG.md",
               "model": MODEL, "n_layers": nL,
               "node_convention": "node i = output of layer i-1",
               "partial": False, "n_done": len(per_problem),
               "problems": per_problem},
              open(OUT, "w"), ensure_ascii=False, indent=2)
    log(f"\n明细 → {OUT}   总耗时 {time.time()-t_start:.0f}s")

    # ══ 七道门（全部照预登记表执行） ══════════════════════════════════
    log("\n" + "═" * 66)
    log("预登记判决门")
    log("═" * 66)

    def verdict(code, ok, msg):
        log(f"\n{code}  {'✅ 成立' if ok else '❌ 不成立'}")
        for line in msg:
            log(f"     {line}")
        return bool(ok)

    # G0 恒等
    n_nodes = sum(len(p["rows"]) for p in per_problem)
    verdict("G0 恒等自证", not g0_fail,
            [f"逐层换回自身：{n_nodes-len(g0_fail)}/{n_nodes} 顶 token 不变",
             f"失败层：{g0_fail[:8]}" if g0_fail else "补丁机制本身没引入偏差"])

    # G1 与录制一致
    r1 = g1_ok / max(g1_steps, 1)
    verdict("G1 与录制数据一致", r1 >= PREREG_G1_STEP,
            [f"贪心重跑与 npz 录制一致 {g1_ok}/{g1_steps} = {r1:.3f}"
             f"（门 ≥{PREREG_G1_STEP}）"])

    # G2 反事实存在（每个 content 臂各判一次）
    for arm in ARMS:
        n_cf = sum(p[f"{arm}_differs"] for p in per_problem)
        verdict(f"G2 反事实存在[{arm}]", n_cf >= PREREG_G2_PROB,
                [f"不打补丁时 {arm} 臂 top1 就与 clean 臂不同：{n_cf}/{len(per_problem)} 题"
                 f"（门 ≥{PREREG_G2_PROB}）",
                 "逐题 clean→" + arm + "：" + ", ".join(
                     f"{p['pid'][-5:]} {p['clean_top1_text']!r}→{p[arm + '_top1_text']!r}"
                     for p in per_problem)])

    import statistics as st
    for arm in ARMS:
        log(f"\n──── 以下 G3-G6 全部针对 {arm} 臂 ────")
        # 两个量都判：主量 transfer、次量 excess。结论相反要报出来。
        for MEAS, mname in (("excessm", "主量·幅度配平后臂 vs 配平随机对照"),
                            ("transfer", "次量·同题臂 vs 换题臂（陌生度失配）"),
                            ("excess", "次量·有多陌生")):
            allrows = [(p, r) for p in per_problem for r in p["rows"]
                       if r[f"{MEAS}_{arm}"] is not None]
            if not allrows:
                continue
            exc = [r[f"{MEAS}_{arm}"] for _, r in allrows]
            med = st.median(exc)

            def ctrl_flipped(r, arm):
                """对照臂**没有**把输出推去该臂自己的 token ⇒ 真方向性。
                主量用配平随机对照（v4）；次量仍用换题臂（陌生度失配，如实标注）。"""
                if MEAS != "excessm":
                    return r["flip_null"] == 0
                tops = [t for t in r.get("nm_%s_top1" % arm, []) if t is not None]
                return int(any(t == r[arm + "_top1"] for t in tops)) == 0

            dir_nodes = sorted({
                (r["node"], p["pid"]) for p, r in allrows
                if r.get("%s_%s" % (MEAS, arm)) is not None
                and r["%s_%s" % (MEAS, arm)] > 0
                and r["flip_%s" % arm] == 1
                and ctrl_flipped(r, arm)
            })
            verdict(f"G3 存在方向性层[{arm}/{MEAS}]", len(dir_nodes) > 0,
                    [f"「换{arm}翻盘 且 对照臂不翻 且 {MEAS}>0」的层-题对：{len(dir_nodes)}"
                     f"（对照 = " + ("幅度配平随机对照 nm1/nm2"
                                    if MEAS == "excessm" else "换题臂") + "）",
                     f"前 12 个：{[(n, p[-5:]) for n, p in dir_nodes[:12]]}"
                     if dir_nodes else "一个都没有"])
            W = sorted({r["node"] for _, r in allrows
                        if r.get(f"{MEAS}_{arm}") is not None and r[f"{MEAS}_{arm}"] > 0})
            span = (W[-1] - W[0] + 1) if W else 0
            verdict(f"G4 内容窗可定位[{arm}/{MEAS}]", len(W) >= PREREG_MIN_W and span <= PREREG_MAXSPAN,
                    [f"{MEAS}>0 的节点 {W}",
                     f"|W|={len(W)}（门 ≥{PREREG_MIN_W}）  span={span} 层（门 ≤{PREREG_MAXSPAN}）"])

            by_node = {}
            for p, r in allrows:
                by_node.setdefault(r["node"], []).append(r[f"{MEAS}_{arm}"])
            node_mean = {n: st.mean(v) for n, v in by_node.items()}
            top6 = sorted(node_mean, key=lambda n: -node_mean[n])[:PREREG_TOPK]
            ov = sorted(set(top6) & set(PREREG_WINDOW))
            verdict(f"G5 描述-因果重叠[{arm}/{MEAS}]", len(ov) >= 3,
                    [f"{MEAS} 前 {PREREG_TOPK} 层 = {sorted(top6)}",
                     f"预登记描述承诺窗 = {PREREG_WINDOW}，交集 = {ov}（门 ≥3）",
                     f"逐层均值：{ {n: round(node_mean[n], 3) for n in sorted(node_mean)} }"])

            verdict(f"G6 null 不等价[{arm}/{MEAS}]", med > 0,
                    [f"逐层 {MEAS}_{arm} 中位数 = {med:.4f}（门 >0）",
                     f"正值 {sum(1 for e in exc if e > 0)}/{len(exc)}，"
                     f"负值 {sum(1 for e in exc if e < 0)}/{len(exc)}"])

            log(f"     （该组用 {mname}）")

    verdict("G0b 幅度配平自证", not g_nm_fail,
            [f"配平对照与该臂补丁偏离 clean 的距离逐节点相等："
             + ("全部相等" if not g_nm_fail else f"{len(g_nm_fail)} 处不等"),
             f"前 3：{g_nm_fail[:3]}" if g_nm_fail else "主量成立的前提"])

    log("\n附：陌生度（该臂残差与干净臂的余弦，逐节点平均）")
    for arm in ARMS + ("null",):
        cs = {}
        for p in per_problem:
            for r in p["rows"]:
                v = r[f"cos_{arm}"]
                if v is not None:
                    cs.setdefault(r["node"], []).append(v)
        log(f"  {arm:<5} " + " ".join(f"N{n}:{st.mean(v):.3f}"
            for n, v in sorted(cs.items())))

    # 附：描述对照（本轮自算的 lens）
    lens_by_node = {}
    for p in per_problem:
        for r in p["rows"]:
            lens_by_node.setdefault(r["node"], []).append(r["lens_agree"])
    log("\n附：本轮自算的描述量（lens argmax 命中率 = 原 token）")
    log("  " + "  ".join(f"N{n}:{st.mean(v):.2f}" for n, v in sorted(lens_by_node.items())))


if __name__ == "__main__":
    main()