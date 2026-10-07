#!/usr/bin/env bash
# 变异台：证明 verify_ltv.py 的判据**能变红**。
# 全绿的判据等于没有判据。每条变异必须让指定判据转红，否则本脚本自己报红。
#
# ⚠ 这个文件里全是中文，**不要用 sed -i 改它** —— 本机 locale 下 BSD sed 会把
#   UTF-8 重新编码成乱码（踩过一次）。要改就整文件重写。
#
# 变异只写新文件到 .cache/xcheck/mutltv/，**不碰**原始产物。
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 2
V=.cache/xcheck/verify_ltv.py
B=.cache/xcheck/build_ltv.py
SRC=${SRC_RAW:-.cache/xcheck/ltv.json}
PUB=${PUBLIC_ART:-frontend/public/latent/data/ltv.json}
MUT=.cache/xcheck/mutltv
mkdir -p "$MUT"
[ -f "$SRC" ] || { echo "缺原始产物 $SRC，先跑 probe_ltv.py"; exit 2; }

# 基线：原样跑一遍，记下**绿的那批**。
# 只看「变异后有没有红」不够 —— 基线本来就红的门，变异后照样红，那种「抓住」是假的。
# 真正要证明的是：**基线里绿的条，变异后必须变少**。
base_out="${MUT}/_baseline.json"
cp "${SRC}" "${base_out}"
base_log=$(ARTIFACT="${base_out}" PUBLIC="${PUB}" python3 "${V}" 2>&1)
base_pass=$(echo "${base_log}" | grep -c "^  \[PASS\]")
echo "基线：绿 ${base_pass} 条（每条变异都必须让这个数变小）"

fails=0
skipped=0
run() {
  local nm="$1" expect="$2"; shift 2
  local out="$MUT/${nm}.json"
  rm -f "${out}"
  ARTIFACT="$SRC" OUT="${out}" python3 - "${out}" <<PYEOF
import json, os
d = json.load(open(os.environ["ARTIFACT"], encoding="utf-8"))
out = os.environ["OUT"]
$*
json.dump(d, open(out, "w"), ensure_ascii=False)
PYEOF
  # ⚠⚠ **不许重建产物。** 第一版在这里加了 `python3 build_ltv.py`，
  #   理由写的是「产物陈了」。那个理由是**反的**：
  #   变异台的整个机制就是「原始层变了、产物没变 ⇒ 判据必须发现两者对不上」。
  #   一重建，产物跟着变，两边重新一致 ⇒ 实测 6 条变异里 5 条「没咬住」。
  #   ⇒ 变异只动原始层；判据靠 G 层（产物 vs 原始）把它抓出来。
  #   实测：把 m_p 减半、不重建 ⇒ 三条判据同时转红（17 → 14）。
  local lg; lg=$(ARTIFACT="${out}" PUBLIC="$PUB" python3 "$V" 2>&1)
  local np; np=$(echo "${lg}" | grep -c "^  \[PASS\]")
  local hit="no"
  echo "${lg}" | grep -qF -- "${expect}" && hit="yes"
  # 目标条在基线**已经红**的变异无法证伪：改坏了也看不出变化。
  # 这不是判据没牙齿，是这批数据里没有它能咬的东西。明说，别含糊报红。
  if echo "${base_log}" | grep "^  \[FAIL\]" | grep -q -- "${expect}"; then
    echo "[略] ${nm}：目标条在基线已红，本变异在这批数据上无法证伪"
    skipped=$((skipped+1))
  elif [ "${np}" -ge "${base_pass}" ]; then
    echo "[红] ${nm}：变异后绿条 ${np} 条，基线 ${base_pass} 条 ⇒ 判据**没**咬住"
    echo "       （基线里绿的条在变异后仍然绿 = 这一条是假绿）"
    echo "${lg}" | grep -A2 "^  \[FAIL\]" | head -8
    fails=$((fails+1))
  elif [ "${hit}" = "yes" ]; then
    echo "[绿] ${nm}：绿条 ${base_pass} → ${np}，且命中 '${expect}'"
  else
    echo "[绿] ${nm}：绿条 ${base_pass} → ${np}（命中的是别的条）"
  fi
}

echo "变异台（原始产物 → 变异产物 → 判据必须报红）"

# ⚠⚠ run_pub：篡改**公开产物**的变异。
#   run() 只动原始层（原始变、产物不变 ⇒ 判据靠「产物 vs 原始」抓）。
#   有一类洞它打不到：**产物自己内部不自洽** —— 没有任何原始层改动能暴露它。
#   最典型的就是本轮真实踩到的那个：构建器把 top_k_energy 写成
#   Σ c_k²‖d_k‖²（基向量自身的能量，而不是重建的能量），实测印出 **207.562%**。
#   那个数没有任何原始层篡改能暴露它 —— 它自己就不合量纲。
#   ⇒ 必须有一支直接改产物、让判据去判「这个产物自己站不站得住」。
run_pub() {
  local nm="$1" expect="$2"; shift 2
  local out="$MUT/${nm}.pub.json"
  rm -f "${out}"
  python3 - "${PUB}" "${out}" <<PYEOF
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
$*
json.dump(d, open(sys.argv[2], "w"), ensure_ascii=False)
PYEOF
  local lg; lg=$(ARTIFACT="${SRC}" PUBLIC="${out}" python3 "$V" 2>&1)
  local np; np=$(echo "${lg}" | grep -c "^  \[PASS\]")
  local hit="no"; echo "${lg}" | grep -qF -- "${expect}" && hit="yes"
  if [ "${np}" -ge "${base_pass}" ]; then
    echo "[红] ${nm}：变异后绿条 ${np} 条，基线 ${base_pass} 条 ⇒ 判据**没**咬住"
    fails=$((fails+1))
  elif [ "${hit}" = "yes" ]; then
    echo "[绿] ${nm}：绿条 ${base_pass} → ${np}，且命中 '${expect}'"
  else
    echo "[绿] ${nm}：绿条 ${base_pass} → ${np}（命中的是别的条）"
  fi
}

# L1 把整条 gap 曲线翻号（等价于「杠杆方向取反」）=> 拟合出的 g_v 反号，
#    预测与实测必然对不上，G-a 的 E 层计数必须变。
run l1_gap_flip "独立重算的 G-a 计数与公开产物逐条一致" '
for c in d["contexts"]:
    for a in list(c["arm_gap"].keys()):
        c["arm_gap"][a] = -c["arm_gap"][a]
'

# L2 偷改 m_p（决胜间距）=> 预测 α* 整体平移，E3 必须红。
#    ⚠ 这一条只改 raw 的 m_p，不改 gap ⇒ 装置自洽检查先红，
#       正因为如此才值得测：**改一个数能不能被独立重算抓到**。
run l2_margin_tamper "独立重算的 G-a 计数与公开产物逐条一致" '
for c in d["contexts"]:
    c["m_p"] = c["m_p"] * 0.5
'

# L3 把对照的 α* 抄成与臂相同（把「幅度配平随机对照」换成同方向的替身）
#    => 「有牙齿」这件事被伪造出来，G-b 的分数必须变。
run l3_control_copied "独立重算的 G-b 打分与公开产物一致" '
for c in d["contexts"]:
    a = c["arm_alpha_star"]
    for k in c["ctl_alpha_star"]:
        c["ctl_alpha_star"][k] = a
'

# L4 把拟合窗内的 gap 强行做成单调（抹掉「先微升再塌」那些位置）
#    => 非单调上下文数变 0，适用率门 G-a0 与 E1 都必须红。
#    这一条专打「靠剔除让门变好看」那个动作。
run l4_force_monotone "独立重算的适用率与 G-a0 的判决一致" '
import math
for c in d["contexts"]:
    ys = [float(c["arm_gap"][str(a)]) for a in (0.05, 0.1, 0.2)]
    m = min(ys)
    for i, a in enumerate((0.05, 0.1, 0.2)):
        c["arm_gap"][str(a)] = m + 0.001 * (2 - i)
'

# L5 谎报恒等自证（批量前向是否真的没改结果）=> 判据的装置自证条必须红。
#    ⚠ 第一版打的是**构建器**里那条 S1，而 verify_ltv 当时**没有复算它**
#    ⇒ 变异打在一个不存在的条上，等于没打。verify 侧已补上对应检查。
run l5_identity_lie "恒等自证" '
for c in d["contexts"]:
    c["identity_top1_ok"] = 0
'

# L6 把实测 α* 全部改成同一个值（等价于「阈值与上下文无关」）
#    => G1 层对账（产物 vs 原始）必须红。
#    ⚠ 第一版打的是「G-c 必须是 na」，而变异改的是 `split` ——
#    那条判据读的是**产物**里的 G-c verdict，原始层根本改不到它 ⇒ 变异打空了。
#    ⇒ 改成打原始层真有的字段。verify 侧的 G-c na 检查保留，
#      它该由「篡改产物」那一类变异去打，不该由篡改原始来打。
run l6_alpha_star_flat "逐上下文字段" '
for c in d["contexts"]:
    c["arm_alpha_star"] = 1.0
'

# L7 篡改原始层的留出划分（把 holdout 抄成 extract）—— 这是本轮真实缺陷的**反向**：
#    磁盘上那份公开产物的 split 曾经是 extract 6 / holdout 0，而原始层是 3/3。
#    当时的判据叫「与原始层的每个数相符」，却只对账逐上下文字段，
#    顶层 split 落在缺口里 ⇒ 一句假话在 GREEN 18/18 下原样发了出去。
#    这一条专打那个缺口。
run l7_split_tamper "顶层字段" '
d["split"] = {"extract": d["split"]["extract"] + d["split"]["holdout"],
              "holdout": []}
'

# L8 换掉切片成员（把抽取题挪进留出集）⇒ 判决口径与产物声明的切片不再一致。
#    专打「产物自己说自己是 holdout，但没人拿原始 split 去对」那个洞。
run l8_slice_swapped "独立重算的 G-b" '
d["split"]["holdout"] = d["split"]["extract"] + d["split"]["holdout"]
d["split"]["extract"] = []
'

# ⚠⚠ 以下三条打的是 **① 稀疏分解**。这一整块上一轮**根本不存在** ——
#   探针只算出 11 条 d_k 就收工，没有 c_k、没有选子集，
#   而产物与第 8 屏都按「这些句子是这个向量的分解」呈现它。
#   补算之后实测：全解只解释 7.807%，|c_k| 前 8 条里有 **2 条负对照**。
#   ⇒ 「①②③ 三个组成部分」里的第一个，本轮**没有交付**。
#   判据侧对应 I2 / I4 / I5 三条独立重算。

# L9 把原始层第一条句子方向**整个反号** —— 语义是「原始层被改了一个轴，
#    而产物里的 c_k / cos 是按改动前那份算的」。
#    ⚠ 这一条同时打 l1 类问题的老洞：判据若只信产物里的 decomp，
#      它永远绿。I2/I4 的存在意义就是「从原始层的 vec 现算，不信产物」。
run l9_axis_flip "独立重算" '
v = d["sentence_diffs"][0]["vec"]
d["sentence_diffs"][0]["vec"] = [-x for x in v]
d["sentence_diffs"][0]["norm"] = -d["sentence_diffs"][0]["norm"]
'

# L10 把**两条轴的向量对调，名字留在原位** —— 这是「命名是事后贴的」最字面的形态：
#     `confident` 这个名字底下压着 `late_chain` 的方向，反之亦然。
#     ⇒ |c_k| 的排序跟着变，而产物里的 top_k 还是按旧排序挑的。
#     这一条专打「K_MAX 只是被搬了三个文件却没有任何东西读它」那个洞：
#     上一版 top_k = 全部 11 条也能一路绿灯放行。
#     ⚠⚠ 第一版把 `key`/`S`/`vec` **整条一起**对调，结果只是把前两项重排 ——
#     {d_k} 这个集合压根没变，独立重算逐位相同 ⇒ 变异自己打空了。
#     「变异打空」和「判据没牙齿」长得很像，必须分开看：
#     这里绿条一条没少，说明**这一条不是判据的问题，是变异构造错了**。
run l10_axis_swap "K_MAX 真的用于选子集" '
a, b = d["sentence_diffs"][0], d["sentence_diffs"][1]
d["sentence_diffs"][0]["vec"] = b["vec"]
d["sentence_diffs"][0]["norm"] = b["norm"]
d["sentence_diffs"][1]["vec"] = a["vec"]
d["sentence_diffs"][1]["norm"] = a["norm"]
'

# L11 原始层少给一条轴（模拟「分解只用了部分句子」）⇒ 产物的 c_k 数量
#     与独立重算对不上。I4 判的是「逐轴逐条相符」，
#     所以少一条不是靠判「条数」而是被判成「这一条在产物里没有」。
run l11_axis_dropped "逐轴的 c_k 与 cos" '
d["sentence_diffs"] = d["sentence_diffs"][:-1]
'

# ── 篡改公开产物的一支（run_pub）────────────────────────────────────────

# L12 把 top_k_energy 写成 >100%（复刻构建器第一版那个 Σc_k²‖d_k‖² 的错）。
#     这一条**任何原始层篡改都打不到**：它不是「产物与原始对不上」，
#     它是「产物自己不合量纲」。只有直接改产物 + 判一条量纲体检才咬得住。
#     这条判据（I3）在第一版不存在 —— 那个 207.562% 一路绿灯进了公开页面。
run_pub l12_energy_over_100 "能量在量纲上说得通" '
d["decomp"]["top_k_energy"] = 2.0756
d["decomp"]["explained_energy"] = 0.0780697335313475
'

# L13 top_k 变成全部 11 条（K_MAX 又变回装饰品）——
#     产物内部看着自洽（长度对了轴数），但与独立重算的 |c_k| 排序对不上。
run_pub l13_topk_all_axes "K_MAX 真的用于选子集" '
d["decomp"]["top_k"] = [a["key"] for a in d["decomp"]["axes"]]
'

# L14 把披露那条 caveat 删掉（解释率只有 7.807% 却一个字不提「① 从未执行过」）
#     —— 复刻「产物不说自己哪里没交付」的原始形态。
run_pub l14_caveat_dropped "已被 caveats 披露" '
d["caveats"] = [c for c in d["caveats"] if "从未被执行过" not in c]
'

# ── G-c：判决不能是**写死**的 ───────────────────────────────────────────────

# L15 把 G-c 判成 pass，却把三条子判据的读数删掉 —— 「结论对、证据空」。
#     G3 要求 pass/fail 时 c1_direction / c2_per_problem / c3_negative_control
#     三个键必须都在（verify_ltv.py:491）。这一条证明 G3 对**真判决**也有牙齿，
#     而不只是当初那句「na 必须带理由」。
run_pub l15_gc_pass_no_evidence "G-c 若报 na 必须带理由" '
g = d["gates"]["G-c"]; g["verdict"] = "pass"; g.pop("why_na", None)
for k in ("c1_direction", "c2_per_problem", "c3_negative_control"):
    g["evidence"].pop(k, None)
'

# L16 反过来：判成 na 却把理由删掉 —— 复刻「na 却不说明为什么」。
run_pub l16_gc_na_no_why "G-c 若报 na 必须带理由" '
g = d["gates"]["G-c"]; g["verdict"] = "na"; g.pop("why_na", None)
'

# ── build 层：判决**真的**由行为数据推出（不是硬编码，不是恒真）──────────────
#
# ⚠ 上面 L15/L16 只能证明 verify 认得证据缺失。真正的风险是**反过来**的：
#   build_ltv 里那句 put("G-c", ..., "na", ...) 本来就是写死的 na，
#   就算 verify 查了证据，判决也永远不会随数据变。
#   ⇒ 这一支不看绿条，直接跑 build、断言 G-c 的**判决值**等于预期。
#   三份行为数据是合成的（与真实那一跑无关），目的是证明判决随输入移动。

_gc_cases=0
_gc_fail=0
run_build() {
  local nm="$1" expect="$2" mode="$3"
  local beh="${MUT}/${nm}.beh.json"
  local pub="${MUT}/${nm}.built.json"
  rm -f "${beh}" "${pub}"
  python3 - "${beh}" "${mode}" <<'PYBEH'
import json, sys
sys.path.insert(0, ".cache/xcheck")
import ltv_behavior as LB
out, mode = sys.argv[1], sys.argv[2]
ALPHAS = (0.35, 1.0, 4.0); PIDS = ("p1", "p2", "p3")
rows = []
for a in ALPHAS:
    for p in PIDS:
        for arm in ("arm", "rand", "zero"):
            sha = ("SAME" if mode == "same" and p == "p2" and a == 4.0
                   else p + str(a) + arm)
            r = {"pid": p, "alpha": a, "arm": arm, "n_words": 100, "sha1": sha}
            for k in LB.FEATURES:
                if mode == "pass":
                    r[k] = {"arm": 10.0, "rand": 1.0, "zero": 2.0}[arm] if k == LB.PRIMARY_KEY \
                        else (1.0 if k in LB.NEGATIVE_KEYS and arm == "arm" else 0.0)
                elif mode == "flat":
                    r[k] = 5.0 if arm in ("arm", "rand") else 1.0   # arm==rand ⇒ c1 不成立
                else:                                             # mode == "same"
                    r[k] = 1.0
            rows.append(r)
beh = {"schema": "steer3d.ltv_behavior/1", "n_runs": len(rows), "per_run": rows,
       "primary_key": LB.PRIMARY_KEY, "negative_keys": list(LB.NEGATIVE_KEYS),
       "pooled_by_problem": {p: {str(a): {} for a in ALPHAS} for p in PIDS}}
json.dump(beh, open(out, "w"))
PYBEH
  ARTIFACT="${SRC}" PUBLIC="${pub}" BEHAVIOR="${beh}" \
    python3 "${B}" >/dev/null 2>&1
  local got; got=$(python3 -c "
import json,sys
try:
    print((json.load(open(sys.argv[1],encoding='utf-8')).get('gates') or {}).get('G-c',{}).get('verdict'))
except Exception as e:
    print('ERR:'+type(e).__name__)" "${pub}")
  _gc_cases=$((_gc_cases+1))
  if [ "${got}" = "${expect}" ]; then
    echo "[绿] ${nm}：G-c 判决 = ${got}（预期 ${expect}）⇒ 判决随数据移动"
  else
    echo "[红] ${nm}：G-c 判决 = ${got}，预期 ${expect} ⇒ 判决**没**跟着数据走"
    _gc_fail=$((_gc_fail+1))
  fi
}

# 三份数据、三种判决：全过 / arm==rand ⇒ 方向性不成立 / 有逐字相同格 ⇒ 不可判
run_build b1_gc_pass   "pass" "pass"
run_build b2_gc_flat   "fail" "flat"
run_build b3_gc_undec  "na"   "same"

# ── J 层自己的牙齿 ────────────────────────────────────────────────────────
# ⚠ J1~J4 是**新加的**，而新加的判据最容易变成一条永远绿的装饰。
#   这一支证明它们能变红：篡 ltv_gen.json（生成原文），
#   J2 从原文重数的率会与 ltv_behavior.json 对不上，J4 的判决也会跟着变。
_j_cases=0
_j_fail=0
# ⚠ 前提守卫：J 层只在 ltv_gen.json **和** ltv_behavior.json 都在时才走那条路。
#   只缺行为文件时 J1 会走「前提缺失」分支，篡改生成原文**打不到**任何东西 ——
#   那是「变异打空」，不是「判据没牙齿」。两者必须分开报，否则会误判 J 层无效。
if [ ! -f .cache/xcheck/ltv_behavior.json ] || [ ! -f .cache/xcheck/ltv_gen.json ]; then
  echo "[跳过] J 层变异：ltv_behavior.json 或 ltv_gen.json 不存在 ⇒ 前提不满足（不是判据没牙齿）"
  _j_cases=$((_j_cases+2))
else
run_j() {
  local nm="$1" expect="$2" snippet="$3"
  local gen="${MUT}/${nm}.gen.json"
  rm -f "${gen}"
  python3 - .cache/xcheck/ltv_gen.json "${gen}" <<PYJEOF
import json, hashlib, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
$snippet
json.dump(d, open(sys.argv[2], "w"), ensure_ascii=False)
PYJEOF
  local lg; lg=$(ARTIFACT="${SRC}" PUBLIC="${PUB}" BEHAVIOR=.cache/xcheck/ltv_behavior.json \
                  GEN_ART="${gen}" python3 "$V" 2>&1)
  local np; np=$(echo "${lg}" | grep -c "^  \[PASS\]")
  local hit="no"; echo "${lg}" | grep -qF -- "${expect}" && hit="yes"
  _j_cases=$((_j_cases+1))
  if [ "${hit}" = "yes" ]; then
    echo "[绿] ${nm}：绿条 ${base_pass} → ${np}，且 '${expect}' 转红"
  else
    echo "[红] ${nm}：篡改 ltv_gen.json 后 '${expect}' 仍是绿的 ⇒ J 层**没牙齿**"
    _j_fail=$((_j_fail+1))
  fi
}

# J1 把所有生成文本清空 ⇒ 从原文重数的率全变 0，与行为文件对不上 ⇒ J2 转红
run_j j1_blank_text "J2 从 ltv_gen.json" '
for r in d["runs"]:
    r["text"] = ""
'

# J2 让每一格的 arm 文本与 rand **逐字相同**（sha1 也一起改）
#    ⇒ 独立重算认定「不可判 ⇒ na」，而产物报的是别的 ⇒ J4 转红
run_j j2_arm_equals_rand "J4 整道 G-c 的判决值" '
for r in d["runs"]:
    if r["arm"] == "arm":
        src = next(x for x in d["runs"] if x["pid"] == r["pid"]
                   and x["alpha"] == r["alpha"] and x["arm"] == "rand")
        r["text"] = src["text"]
        r["text_sha_1"] = src["text_sha_1"]
'
fi

echo
if [ ${fails} -eq 0 ] && [ ${_gc_fail} -eq 0 ] && [ ${_j_fail} -eq 0 ]; then
  echo "全部变异都被判据抓住（判据有牙齿）${skipped:+，跳过 ${skipped} 条（目标条基线已红）}"
  exit 0
fi
echo "${fails} 条变异没被抓住；build 层 ${_gc_fail}/${_gc_cases} 条没跟着数据走；J 层 ${_j_fail}/${_j_cases} 条没牙齿"
exit 1