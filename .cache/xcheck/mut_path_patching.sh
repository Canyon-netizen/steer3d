#!/usr/bin/env bash
# 变异台：证明 verify_path_patching.py 的判据**能变红**。
# 全绿的判据等于没有判据。每条变异必须让指定判据转红，否则本脚本自己报红。
#
# ⚠ 这个文件里全是中文，**不要用 sed -i 改它** —— 本机 locale 下 BSD sed 会把
#   UTF-8 重新编码成乱码（踩过一次）。要改就整file 重写。
#
# 变异只写新文件到 .cache/xcheck/mut/，**不碰**原始产物。
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 2
V=.cache/xcheck/verify_path_patching.py
SRC=${SRC_RAW:-.cache/xcheck/path_patching.json}
PUB=${PUBLIC_ART:-frontend/public/latent/data/path_patching.json}
MUT=.cache/xcheck/mut
mkdir -p "$MUT"
[ -f "$SRC" ] || { echo "缺原始产物 $SRC，先跑探针"; exit 2; }

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
# ⚠⚠ 目标串在第二版全部重写。E 层从「verdict 该是 pass」改成
#   「我重算的 verdict 必须等于产物印的 verdict」之后，绝大多数变异
#   不再咬原来的行，而是咬 **E12 对账条**。这不是把目标串一改了事：
#   若只把 expect 换成 E12，E1/E2/E3/E4 这几条**行级自洽判据就没人验了**
#   —— 它们会悄悄退化成没人盯着的装饰。所以：
#     · 破坏「量与原始字段自洽」的，仍指向它自己那一条；
#     · 破坏「判决」的，指向 E12 —— 因为 E 层不再自己下判决，
#       它只判决「判决有没有被如实重算出来」。

# M1 把主量 excessm 整体变号（等价于「把配平对照换成更破坏的东西」）
#     => ① E1 必须红（excessm 与 nm_* 的定义对不上了）
#     => ② E12 必须红（重算的 G6 翻成 fail，产物还写着 pass）
run m1_excessm_flip "E1 三个量与各自的原始字段逐行自洽" '
for p in d["problems"]:
    for r in p["rows"]:
        for a in ("num", "word"):
            if r.get("excessm_" + a) is not None: r["excessm_" + a] = -r["excessm_" + a]
'

# M2 谎报幅度配平齐全（把配平对照删掉）=> E2 必须红。
run m2_drop_matched_control "E2 幅度配平" '
for p in d["problems"]:
    for r in p["rows"]:
        for a in ("num", "word"):
            r["nm_" + a] = [r["nm_" + a][0]] if r.get("nm_" + a) else []
'

# M3 只改 excessm，不改 nm_* 与臂的原始 logp => E1 必须红（产物自相矛盾）。
run m3_excessm_tamper "E1 三个量与各自的原始字段逐行自洽" '
for p in d["problems"]:
    for r in p["rows"]:
        for a in ("num", "word"):
            if r.get("excessm_" + a) is not None: r["excessm_" + a] += 0.4
'

# M4 谎报恒等全过（暗中改掉几层）=> E4 必须红。
run m4_identity_fake "E4 G0" '
for p in d["problems"]:
    for r in p["rows"]: r["identity_top1_ok"] = 1
    for r in p["rows"][:4]: r["identity_top1_ok"] = 0
'

# M5 谎报「没有反事实」=> E12 必须红。
#     改的是**判决的前提**：word 臂的 ncf 归零 ⇒ g2ok 变 False ⇒ 重算的
#     G2 变 fail、G3-G6 全变 na，而产物里它们分别写着 pass/fail ⇒ 对不上。
#     这条是 E12 牙齿最直接的证据：把「反事实存在」这个前提偷走，
#     产物上的判决就成了没人重算得出来的样子。
run m5_no_counterfactual "E12 独立重算的每道门与产物印的 verdict 逐条一致" '
for p in d["problems"]:
    p["num_top1"] = p["clean_top1"]; p["num_differs"] = 0
    p["word_top1"] = p["clean_top1"]; p["word_differs"] = 0
'

# M6 flip_* 谎报成恒 0 => E3 必须红。
run m6_flip_lie "E3" '
for p in d["problems"]:
    for r in p["rows"]:
        r["flip_num"] = 0; r["flip_word"] = 0
'

# M7 节点号整体后移 5 层 => 重算的 G5 重叠必须与产物对不上 => E12 红。
#     节点号错位是**不会让任何单行不自洽**的那一类故障：所有数都还在、
#     都还自洽，只有「层号」整体挪了位置。不对账就永远看不出来。
run m7_node_shift "E12 独立重算的每道门与产物印的 verdict 逐条一致" '
for p in d["problems"]:
    for r in p["rows"]: r["node"] = r["node"] + 5
'

echo
if [ ${fails} -eq 0 ]; then
  echo "全部变异都被判据抓住（判据有牙齿）${skipped:+，跳过 ${skipped} 条（目标条基线已红）}"
  exit 0
fi
echo "${fails} 条变异没被抓住"; exit 1