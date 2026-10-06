#!/usr/bin/env python3
"""path patching 的产物层判据。**不复用探针的任何计算**，只从原始行重算。

第三层防护：探针自己算一遍 → 这里从它写下的原始字段独立算一遍 → 两边必须一致。
共用同一份中间量 ⇒ 一处错则处处绿。

三个量都重算（预登记表 v4）：
  excessm  主量：臂补丁 vs 幅度配平随机对照
  transfer 次量：同题臂 vs 换题臂
  excess   次量：原 token 的 logp 差

用法:
  python3 .cache/xcheck/verify_path_patching.py
  ARTIFACT=/path/to/other.json python3 .cache/xcheck/verify_path_patching.py
"""
import json
import os
import statistics as st
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 默认读**原始探针产物**（含 rows 的未加工字段）。独立重算必须在最原始的那层做，
# 否则就是拿产物自己的中间量验它自己 —— 那不叫独立。
ART = os.environ.get("ARTIFACT", os.path.join(REPO, ".cache", "xcheck", "path_patching.json"))
# 公开产物单独查：它是读者与页面上看到的那份，必须与原始层逐数相符。
PUBLIC = os.environ.get(
    "PUBLIC",
    os.path.join(REPO, "frontend", "public", "latent", "data", "path_patching.json"))
PREREG = os.path.join(REPO, ".cache", "xcheck", "PATH_PATCHING_PREREG.md")

WINDOW = [17, 18, 19, 20, 21, 22]
TOPK, MAXSPAN, MINW, G1_STEP, G2_PROB = 6, 12, 2, 0.8, 4
ARMS = ("num", "word")
MEASURES = ("excessm", "transfer", "excess")
PRIMARY = "excessm"

fails, warns, _total = [], [], [0]


def check(name, ok, detail):
    _total[0] += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    for x in detail:
        print(f"         {x}")
    if not ok:
        fails.append(name)


def main():
    if not os.path.exists(ART):
        print(f"产物不存在：{ART}")
        sys.exit(2)
    d = json.load(open(ART, encoding="utf-8"))
    P = d["problems"]
    print(f"原始产物 {ART}\n题 {len(P)} 道  节点约定 {d.get('node_convention')}")
    if d.get("partial"):
        warns.append(f"原始产物是**部分**结果（{d.get('n_done')}/{len(P)} 题）—— "
                     f"拿它下结论等于只跑了一半还当跑完了")
    print("\nE 层 · 从原始行独立重算")

    # E1 三个量与各自的原始字段自洽
    bad, n = [], 0
    for p in P:
        for r in p["rows"]:
            for arm in ARMS:
                if r.get(arm) is None:
                    continue
                n += 1
                if r.get("excess_" + arm) is not None and abs(
                        r["excess_" + arm]
                        - (r["null"]["logp_target"] - r[arm]["logp_target"])) > 1e-9:
                    bad.append((p["pid"], r["node"], arm, "excess"))
                if r.get("transfer_" + arm) is not None and abs(
                        r["transfer_" + arm]
                        - (r[arm]["logp_arm"] - r["null"]["logp_arm"])) > 1e-9:
                    bad.append((p["pid"], r["node"], arm, "transfer"))
                nm = [x for x in (r.get("nm_" + arm) or []) if x is not None]
                if r.get("excessm_" + arm) is not None and nm and abs(
                        r["excessm_" + arm]
                        - (r[arm]["logp_arm"] - sum(nm) / len(nm))) > 1e-9:
                    bad.append((p["pid"], r["node"], arm, "excessm"))
    check("E1 三个量与各自的原始字段逐行自洽", not bad,
          [f"核对 {n} 行（两臂），{len(bad)} 行不自洽", f"前 3：{bad[:3]}"])

    # E2 幅度配平：对照个数、dev_norm 齐全
    bad2 = [ (p["pid"], r["node"], arm) for p in P for r in p["rows"] for arm in ARMS
             if r.get(arm) is not None
             and (len(r.get("nm_" + arm) or []) != 2 or r.get("dev_norm_" + arm) is None) ]
    check("E2 幅度配平对照齐全（每臂每节点两个对照 + 偏离量）", not bad2,
          [f"{len(bad2)} 行不齐", f"前 3：{bad2[:3]}"])

    # E3 flip_* 与两臂 top1 自洽
    bad3 = []
    for p in P:
        for r in p["rows"]:
            for arm in ARMS:
                if r.get(arm) is None:
                    continue
                if r.get("flip_" + arm) != int(r[arm]["top1"] == p[f"{arm}_top1"]):
                    bad3.append((p["pid"], r["node"], arm))
            if r.get("flip_null") != int(r["null"]["top1"] == p["null_top1"]):
                bad3.append((p["pid"], r["node"], "null"))
    check("E3 flip_* 与两臂 top1 自洽", not bad3,
          [f"{len(bad3)} 行不自洽", f"前 3：{bad3[:3]}"])

    # E4 G0 恒等
    tot = sum(len(p["rows"]) for p in P)
    idok = sum(1 for p in P for r in p["rows"] if r["identity_top1_ok"])
    check("E4 G0 恒等自证", idok == tot, [f"换回自身后顶 token 不变 {idok}/{tot}"])

    # E5 G1
    s_, o_ = 0, 0
    for p in P:
        s_ += p["g1_steps"]; o_ += p["g1_agree"]
    r1 = o_ / max(s_, 1)
    check("E5 G1 与录制数据一致", r1 >= G1_STEP,
          [f"{o_}/{s_} = {r1:.3f}（门 ≥{G1_STEP}）",
           f"逐题：{[(p['pid'][-5:], p['g1_agree'], p['g1_steps']) for p in P]}"])

    # ── E6..E10 独立重算 → 与产物里印的 verdict 对账 ──────────────────
    # ⚠⚠⚠ 这一段第一版**方向写反了**。它问的是「verdict 是不是 pass」，
    #   而本文件 docstring 写的是「两边必须一致」。三个后果，一个比一个隐蔽：
    #
    #   ① **科学没成立会把判据弄红**。G4 判「不是窗、只是弥散，附近有峰」
    #      是本轮的真实结论，页面已经诚实印着。审计器跟着红，就把
    #      「审计器坏了」和「科学没成立」压成同一个字样 ——
    #      与「判据返回 False 但不证明任何事」是同一个坑。
    #   ② **它永远红**。一条永远红的判据与一条永远绿的判据同样没有信息量，
    #      而且更隐蔽：全链退出码会恒为 1，此后**任何真故障都被淹在这条
    #      恒红里**，而恒红是最容易被当成「已知问题」继续往下走的那一种。
    #   ③ **判据与产品对同一件事给了相反答案**。num 臂被 SKIP_NUM 裁掉，
    #      产物按预登记规则标 `na` 并带理由（没跑 ≠ 跑过没过），
    #      而 E 层却独立判它 FAIL —— 这正是我写构建器时刻意避免的那个错，
    #      在自己身上又犯了一遍。
    #   ⇒ 这里重算的是「verdict 等于多少」，**只有「重算 ≠ 产物」才红**。
    #     变异台仍然咬得住：改产物里的数就对不上（m3/m4/m6 干的就是这个）。
    #     注意这**不是**把 E 层降格成复读机 —— 独立重算的代码在这里，
    #     产物是另一个人（构建器）算的，两边不一致正是要抓的东西。
    pub_gates = {}
    if os.path.exists(PUBLIC):
        pub_gates = (json.load(open(PUBLIC, encoding="utf-8"))
                     .get("gates") or {})

    recomp, no_recomp = {}, {}
    for arm in ARMS:
        ncf = sum(p[f"{arm}_differs"] for p in P)
        ran = any(p.get(f"{arm}_top1_text") for p in P)
        g2ok = ran and ncf >= G2_PROB
        recomp[f"G2[{arm}]"] = "na" if not ran else ("pass" if g2ok else "fail")
        if not ran:
            no_recomp[f"G2[{arm}]"] = "该臂本轮未测（无任何 top1 文本）"
        print(f"  [重算] E6 G2[{arm}] → {recomp[f'G2[{arm}]']}"
              f"　反事实 {ncf}/{len(P)}（门 ≥{G2_PROB}）"
              f"{'　ran=False' if not ran else ''}")
        print("         逐题：" + ", ".join(
            f"{p['pid'][-5:]} {p['clean_top1_text']!r}→{p[arm + '_top1_text']!r}"
            for p in P))

        # E7-E10 G3-G6：每臂 × 每量
        for meas in MEASURES:
            key4 = f"[{arm}/{meas}]"
            tag = key4 + ("（主量）" if meas == PRIMARY else "（次量）")
            if not ran or not g2ok:
                # 装置前提不成立 ⇒ 全部 na。**这里必须跟着产物走 na**：
                # 独立算一遍「它该是 fail」是拿「没测」冒充「测了没过」。
                for g in ("G3", "G4", "G5", "G6"):
                    recomp[f"{g}{key4}"] = "na"
                    no_recomp[f"{g}{key4}"] = (
                        "该臂本轮未测" if not ran else
                        f"G2[{arm}] 未过（{ncf}/{len(P)}）⇒ 无从测起")
                print(f"  [重算] E7..E10 {tag} → 全部 na"
                      f"（{'臂未跑' if not ran else 'G2 未过'}）")
                continue
            rows = [(p, r) for p in P for r in p["rows"]
                    if r.get(f"{meas}_{arm}") is not None]
            if not rows:
                # 没数据 ≠ 不成立。SKIP_NUM 裁掉的臂在这里必须报「本轮不适用」，
                # 报成 FAIL 等于把「没测」写成「测了没过」。
                recomp[f"G3{key4}"] = "na"
                no_recomp[f"G3{key4}"] = "该量在本轮没有可用数据"
                print(f"  [略过] E7..E10 {tag}：本轮该臂该量无数据"
                      f"（G2 未过或臂被裁掉），不判成立也不判不成立")
                continue
            isp = meas == PRIMARY
            exc = [r[f"{meas}_{arm}"] for _, r in rows]

            # 该臂自己的 token 是**题级**字段（p["word_top1"]），不是行级。
            # 上一版写成 r[f"{arm}_top1"]，跑到第一个非空行就 KeyError。
            def no_ctrl(r, pr, _isp=isp, _arm=arm):
                if _isp:
                    want = pr.get(_arm + "_top1")
                    tops = [t for t in (r.get("nm_" + _arm + "_top1") or [])
                            if t is not None]
                    return int(any(t == want for t in tops)) == 0
                return r["flip_null"] == 0

            dirset = sorted({(r["node"], p["pid"]) for p, r in rows
                             if r[f"{meas}_{arm}"] > 0 and r[f"flip_{arm}"] == 1
                             and no_ctrl(r, p)})
            v3 = "pass" if len(dirset) > 0 else "fail"
            recomp[f"G3{key4}"] = v3
            print(f"  [重算] E7 G3{tag} → {v3}"
                  f"　层-题对 {len(dirset)} 个，对照="
                  + ("幅度配平随机对照" if isp else "换题臂"))

            W = sorted({r["node"] for _, r in rows if r[f"{meas}_{arm}"] > 0})
            span = (W[-1] - W[0] + 1) if W else 0
            v4 = "pass" if (len(W) >= MINW and span <= MAXSPAN) else "fail"
            recomp[f"G4{key4}"] = v4
            print(f"  [重算] E8 G4{tag} → {v4}"
                  f"　|{meas}>0 的层|={len(W)}（门 ≥{MINW}） span={span}（门 ≤{MAXSPAN}）")

            byn = {}
            for p, r in rows:
                byn.setdefault(r["node"], []).append(r[f"{meas}_{arm}"])
            nmv = {x: st.mean(v) for x, v in byn.items()}
            top6 = sorted(nmv, key=lambda x: -nmv[x])[:TOPK]
            ov = sorted(set(top6) & set(WINDOW))
            v5 = "pass" if len(ov) >= 3 else "fail"
            recomp[f"G5{key4}"] = v5
            print(f"  [重算] E9 G5{tag} → {v5}"
                  f"　前 {TOPK} 层 {sorted(top6)} ∩ 预登记窗 {WINDOW} = {ov}（门 ≥3）")

            med = st.median(exc)
            v6 = "pass" if med > 0 else "fail"
            recomp[f"G6{key4}"] = v6
            print(f"  [重算] E10 G6{tag} → {v6}"
                  f"　中位 {med:.4f}（门 >0）　正 {sum(1 for e in exc if e > 0)}"
                  f" / 负 {sum(1 for e in exc if e < 0)} / 共 {len(exc)}")

    mism, absent = [], []
    for k, v in sorted(recomp.items()):
        got = (pub_gates.get(k) or {}).get("verdict")
        if got is None:
            absent.append(k)
        elif got != v:
            mism.append((k, v, got))
    check("E12 独立重算的每道门与产物印的 verdict 逐条一致"
          "（判据审计的是**自洽**，科学红绿由产物与页面负责）",
          not mism,
          [f"重算了 {len(recomp)} 道，产物里缺 {len(absent)} 道（{absent[:6]}）",
           f"不一致 {len(mism)} 处",
           f"前 3（门键, 重算, 产物）：{mism[:3]}" if mism
           else "逐条一致（na 也一致：没测在两边都写着没测）"])

    # E11 陌生度：主量成立的前提是「配平对照替代换题臂」
    cos = {}
    for p in P:
        for r in p["rows"]:
            for arm in ARMS + ("null",):
                c = r.get(f"cos_{arm}")
                if c is not None:
                    cos.setdefault(arm, []).append(c)
    print("\nE11 层 · 三臂残差与干净臂的余弦（陌生度）")
    for arm, v in cos.items():
        print(f"    {arm:<5} 中位 {st.median(v):.3f}  范围 "
              f"{min(v):.3f} ~ {max(v):.3f}")
    if "null" in cos and any(k in cos for k in ARMS):
        _ref = next((k for k in ARMS if k in cos), None)
        if _ref and st.median(cos["null"]) > st.median(cos[_ref]):
            warns.append("换题臂余弦中位 %.3f **高于** %s 臂 %.3f ⇒ "
                         "预登记里「换题臂更陌生」的前提不成立，请复核"
                         % (st.median(cos["null"]), _ref, st.median(cos[_ref])))

    # E13 主量的量级体检。
    # ⚠ 幅度配平只对齐了**偏离幅度**，没对齐「破坏程度」。随机方向在 2048 维里
    #   几乎落在数据流形之外，同幅度的随机扰动可能把表示打烂 —— 那样的话
    #   任何内容补丁在它面前都好看，excessm 会**平凡地**为正。
    #   这里把量级摆出来：> 5 nats 就明说「对照可能过度破坏，主量的正号不可单独采信」。
    print("\nE13 层 · 主量量级体检（配平对照是否过度破坏）")
    for arm in ARMS:
        vals = [r[f"{PRIMARY}_{arm}"] for p in P for r in p["rows"]
                if r.get(f"{PRIMARY}_{arm}") is not None]
        if not vals:
            print(f"    {arm:<5} 本轮没有主量数据")
            continue
        med = st.median(vals)
        pos = sum(1 for v in vals if v > 0)
        print(f"    {arm:<5} 主量中位 {med:.3f} nats，正 {pos}/{len(vals)}")
        if med > 5.0:
            warns.append(f"{arm} 臂主量中位 {med:.2f} nats **偏大** ⇒ 配平随机对照"
                         f"很可能过度破坏（随机方向在流形外）。主量为正不等于"
                         f"「有内容效应」，只能说明「内容补丁比同幅度随机扰动好」。"
                         f"G4/G5 问的是形状，仍有效。")

    # E12 描述量
    lens = {}
    for p in P:
        for r in p["rows"]:
            lens.setdefault(r["node"], []).append(r["lens_agree"])
    print("\nE12 层 · 描述对照（本轮自算的 lens argmax 命中率）")
    print("    " + " ".join(f"{x}:{st.mean(v):.2f}" for x, v in sorted(lens.items())))

    # F 层
    print("\nF 层 · 预登记与实现是否漂移")
    if os.path.exists(PREREG):
        t = open(PREREG, encoding="utf-8").read()
        for label, pat in [("G1 一致率门 0.8", "0.8"),
                           ("G2 题数门 4", "4"),
                           ("G4 span 门 12", "≤ 12"),
                           ("G5 topK 6", "前 6 层"),
                           ("G5 预登记窗 17-22", "17..22"),
                           ("G4 min width 2", "≥ 2"),
                           ("主量 excessm", "excessm"),
                           ("配平对照定义", "配平"),
                           ("两个随机对照", "nm1")]:
            check(f"F1 {label}", pat in t, [f"在预登记表里查 {pat!r}"])
    else:
        fails.append("预登记表缺失")

    # G 层：公开产物必须与原始层逐数相符。
    # 页面读的是公开产物；它若自己长了一套数，页面上就全是错的。
    print("\nG 层 · 公开产物与原始层对账")
    if not os.path.exists(PUBLIC):
        warns.append(f"公开产物不存在：{PUBLIC}")
    else:
        pub = json.load(open(PUBLIC, encoding="utf-8"))
        pp = pub.get("problems", [])
        bad_pub = []
        if len(pp) != len(P):
            bad_pub.append([f"题数 公开 {len(pp)} ≠ 原始 {len(P)}"])
        for i, p in enumerate(P):
            if i >= len(pp):
                break
            if pp[i]["pid"] != p["pid"]:
                bad_pub.append([p["pid"], f"pid {pp[i]['pid']}"]); continue
            pn_ = pp[i]["nodes"]
            for j, r in enumerate(p["rows"]):
                if j >= len(pn_):
                    break
                q = pn_[j]
                if q["node"] != r["node"]:
                    bad_pub.append([p["pid"], f"节点 {q['node']}≠{r['node']}"]); break
                for arm in ARMS:
                    for meas in MEASURES:
                        raw = r.get(f"{meas}_{arm}")
                        pubv = q.get(f"{meas}_{arm}")
                        if raw is None and pubv is None:
                            continue
                        if raw is None or pubv is None or abs(raw - pubv) > 1e-6:
                            bad_pub.append([p["pid"], r["node"],
                                            f"{meas}_{arm}: 原始 {raw} ≠ 公开 {pubv}"])
        check("G1 公开产物与原始层的每个数相符（页面读的那份必须是对的）",
              not bad_pub,
              [f"题 {len(pp)} / 节点 {sum(len(x['nodes']) for x in pp)}",
               f"不符 {len(bad_pub)} 处",
               f"前 3：{bad_pub[:3]}"] if bad_pub else ["逐数一致"])
        gp = {k: v for k, v in (pub.get("gates") or {}).items()}
        need = [k for k in (pub.get("gate_order") or []) if k in gp]
        check("G2 公开产物的每道门都有唯一 verdict，且 na 带理由",
              all(gp[k]["verdict"] in ("pass", "fail", "na")
                  and (gp[k]["verdict"] != "na" or gp[k].get("why_na"))
                  for k in need) if need else False,
              [f"门数 {len(need)}",
               f"三态计数 "
               + json.dumps({x: sum(1 for k in need if gp[k]["verdict"] == x)
                             for x in ("pass", "fail", "na")})])

    print("\n" + "=" * 60)
    # ⚠⚠ 汇总行**必须**是 `RESULT <名>  <RED|GREEN>  N/M 条通过`。
    #   第一版这里印的是自创的 `❌ 8 条红：[…]`，而 run_chain.sh 只认
    #   `^RESULT` 或 `^=== N/M` ⇒ 我这条判据在全链里被判成 **NORUN**，
    #   而 NORUN 的读法是「一条都没跑」—— **判据红与判据没跑长得一样**。
    #   更糟的是它 exit=1 也没用：串联器判决只从汇总行读，退出码只查装置崩。
    #   ⇒ 房里有两套模板（python 用 RESULT，node 用 === N/M passed ===），
    #     新判据不许自创第三套。
    print("\nRESULT verify_patching  %s  %d/%d 条通过"
          % ("RED" if fails else "GREEN", _total[0] - len(fails), _total[0]))
    for f in fails:
        print("   [FAIL] " + f)
    for w in warns:
        print("⚠ " + w)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()