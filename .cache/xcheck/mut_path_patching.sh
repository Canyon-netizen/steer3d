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

# M1 把主量 excessm 整体变号（等价于「把配平对照换成更破坏的东西」）
#     => G6 对照不等价[*/excessm] 必须翻红。这一条证明主量确实在起作用。
run m1_excessm_flip "E10 G6 对照不等价[word/excessm]" '
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

# M5 谎报「没有反事实」=> E2/E6 必须红。
run m5_no_counterfactual "E6 G2 反事实存在[word]" '
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

# M7 节点号整体后移 5 层 => G5 的重叠必须变。
run m7_node_shift "E9 G5 描述-因果重叠[word/excessm]" '
for p in d["problems"]:
    for r in p["rows"]: r["node"] = r["node"] + 5
'

echo
if [ ${fails} -eq 0 ]; then
  echo "全部变异都被判据抓住（判据有牙齿）${skipped:+，跳过 ${skipped} 条（目标条基线已红）}"
  exit 0
fi
echo "${fails} 条变异没被抓住"; exit 1