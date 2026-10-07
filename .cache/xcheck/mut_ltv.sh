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

echo
if [ ${fails} -eq 0 ]; then
  echo "全部变异都被判据抓住（判据有牙齿）${skipped:+，跳过 ${skipped} 条（目标条基线已红）}"
  exit 0
fi
echo "${fails} 条变异没被抓住"; exit 1