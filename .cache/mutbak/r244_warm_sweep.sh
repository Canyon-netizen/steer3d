#!/bin/bash
# 修订 244：`w` 臂跑批（141→137 格）。⚖ 与 rand 臂之间**只差 `--arm`**。
#
# ⚠⚠⚠ 发这批之前必须先过的 Phase-0（已过，见账本 §244.1）：
#   新探针 `r241_probe.py` 与旧探针 `r226_probe.py` 在**显式传 --inject-scope** 时
#   读数**逐字节相同**（diff_bytes=0）。
#   ⚖⇒ 不验这条，w 与 rand 之间就不止一个变量变了。
#   ⚖ ⚗ 本轮第一版没验就差点发，且两次栽在「假绿」上（见 §244.2）。
#
# ⚠⚠⚠ 三条纪律（每条都是本轮用教训换来的）：
#   ① **格清单从文件读**（由 r227_status.txt 机器解析生成，137 行），
#      ⛔ 不手打 —— 修订 232 的纪律：绝不手工拼接。
#   ② **新日志**：r244_warm.log / r244_warm_status.txt，⛔ 不追加进 r227_*。
#   ③ **脚本文件 + GPU UUID 作启动参数**：远端跑批一律不内联
#      （本轮第三版内联 $C 在远端没展开，报「required arguments are missing」）。
#
# ⚖⚖⚖⚖⚖ **修订 244.77（固定剂量那一批）**：格清单改成 **4 列**（含 `pos_frac`）＋ **带表头**
#   ⇒ ⇒ 四处改动 ＋ 一处表头处理（**向后兼容**：旧的 3 列清单仍能跑）：
#   ① **表头显式跳 ＋ 显式验**（⛔ 表头不符 ⇒ ABORT；⛔ 表头**绝不**被当成一格去探）
#   ② **`--pos-frac` 从 `$C` 里挪进循环**（⛔ 否则它还是写死的单一真源）
#   ③ **n_eff 映射表按 `(tid, pos_frac)` 命中**（三个 `pos_frac` ⇒ 三张表）
#   ④ **格数闸数「数据行」**（⛔ 不是文件行数 ⇒ 表头不该被算进去）
#   ⑤ **`POS_FRAC` 常量降级为「旧 3 列清单的显式默认」**（⛔ 新 4 列清单不用它）
#   ⑥ **`--w` 路径参数化**（第 8 个位置参数，⛔ **默认值一字不改**：`/tmp/w_p2a.npy`）
#   ⑦ **来源戳格式恢复成契约格式**（⛔ 行首严格 `NMAP rows=<N> md5=<32hex>`）
#      ⚖ 为什么：读数器靠这一行判断「BEGIN 里的 n_eff 来自跑批前的映射表」⇒
#      ⇒ 一旦行首多了 `mode=`，戳**不被认** ⇒ 读数器就判「n_eff 交叉校验
#      **可能是恒等式**」⇒ ⇒ 那道守卫**从「能红」退化成「不能红」**。
#      ⇒ 前缀形态（三张表）⇒ **合成一个戳**（⛔ 两个不同戳 ⇒ 读数器 HardFail）。
#      ⚖ 为什么：244.77 的 **1 格端到端烟测**需要**一个**向量，而账本登记的那个
#      （`new_p2a` = `/tmp/w_p2a.npy`）**已经不在机器上了** ⇒ ⇒ 烟测必须能指定别的路径。
#      ⚖⚠ **⛔ 绝不许把替身向量放到 `/tmp/w_p2a.npy`** ⇒ 那会让「路径可覆盖」变成
#      「路径被偷换」⇒ ⇒ 事后无法分辨那一批用的是真向量还是替身。
#      ⇒ 替身走**显式**参数 ⇒ 日志里**逐字可见**（`W_PATH=…`）⇒ 可审计。
#   ⚖ **K23（修订 238：两臂扫描参数逐字相同）仍然成立**：两臂读**同一份**清单 ⇒
#      `--pos-frac "$PF"` 两臂**逐字相同** ⇒ ⇒ 两臂仍**只差 `--arm`** ⇒ ⇒ 改完**必须复核**。
set -u
PY=/home/zhourui/miniconda3/envs/easysteer/bin/python
B=/home/zhourui/steer3d_bpath
GPU_UUID=${1:?用法: r244_warm_sweep.sh <GPU-UUID> <cells-file> <n-eff-map> [EXPECT_CELLS] [TAG] [ARM] [POS_FRAC_DEFAULT] [W_PATH]}
CELLS=${2:-$B/warm_cells.txt}
NMAP=${3:-$B/n_eff_map.tsv}
# ⚖ 单一真源：--pos-frac 只从这里出。⚗ 之前它硬编码在 $C 里，而 n_eff 映射表
# ⚖   是用另一处的 0.5 生成的 —— 两处不一致时，t 会静默错且没有任何守卫会响。
# ⚖⚖⚖ 244.77：这条**只对旧的 3 列清单**成立（⛔ 旧的 137 行清单没有第 4 列）
#   ⇒ ⇒ 新 4 列清单的 `pos_frac` 单一真源是**清单本身**（⛔ 下面按格取）
#   ⇒ ⇒ 这里降级成「旧清单的**显式**默认」，⛔ 默认 0.5，且**每次都印进日志**
POS_FRAC_DEFAULT=${7:-0.5}
# ⚖ 修订 244.8：格数闸与日志名参数化，**默认值不变**。
# ⚖⚗ 存在的唯一理由：新 BEGIN 格式（带 n_eff=）要先过 1 格端到端烟测，
# ⚖   而原来的硬编码 137 会让烟测当场 exit 9。默认值仍是 137，
# ⚖   且实际期望值与 TAG 都进 $LOG ⇒ 事后可核对当时按哪个闸跑的。
# ⚖ ⛔ 不接受「把闸放宽到能跑」这种用法：那是事后把红改成绿。
EXPECT_CELLS=${4:-137}
TAG=${5:-}
# ⚖ 修订 244.8：臂作为参数，⛔ 不另写一份 rand 版脚本。
# ⚖⚗ 242 的硬条件是「两臂之间只差 --arm」—— 复制脚本就会引入第二个可能漂的变量。
ARM=${6:-w}
# ⚖⚖⚖ 244.77 ⑥：**`--w` 路径参数化**（⛔ **默认值一字不改** ⇒ 不传就还是 `/tmp/w_p2a.npy`）
# ⚖ 理由：1 格端到端烟测需要**一个**向量，而账本登记的 `new_p2a` 已不在机器上。
# ⚖ ⛔ 替身**绝不许**放到 `/tmp/w_p2a.npy`（那会把「路径可覆盖」变成「路径被偷换」）。
# ⚖ ⇒ 替身走**显式**参数 ⇒ 日志里逐字可见 ⇒ 事后可审计。
W_PATH=${8:-/tmp/w_p2a.npy}
LOG=$B/r244_warm${TAG}.log
ST=$B/r244_warm${TAG}_status.txt
export CUDA_VISIBLE_DEVICES=GPU-$GPU_UUID
: > "$LOG"; : > "$ST"
# ⚠⚠⚠ 修订 244.1：**状态文件的契约是「每格一行 + ALLDONE」**。
# ⚖ `r227_kcurve.parse_status` 遇到读不出 rc 的行会 **HardFail**，
# ⚖ 而那道守卫是**对的** ⇒ ⛔ **不许为了让它绿而去放宽读数器**，
# ⚖ ⚗ 那是「事后把红改成绿」。⇒ 改**生产者**。
# ⚖ 第一版我在 $ST 里写了 `PINNED GPU=…` 头行 ⇒ 读数器当场 HardFail。
# ⚖⇒ PINNED / ABORT / 一切非格行，**只许进 $LOG**。
echo "PINNED GPU=$GPU_UUID  CELLS=$CELLS  NMAP=$NMAP  POS_FRAC_DEFAULT=$POS_FRAC_DEFAULT  EXPECT_CELLS=$EXPECT_CELLS  TAG=${TAG:-none}  ARM=$ARM  W_PATH=$W_PATH  $(date +%T)" >> "$LOG"

# ⚖⚖⚖⚖⚖ 244.77 ①：**表头显式跳 ＋ 显式验**（格式的**第二个**维度，不止列数）
#   ⚖ 为什么：分析侧（`read_cells`）**要**表头；生产侧**不要**（它把每行都当一格）
#   ⇒ ⇒ ⛔ 表头必须**显式剥掉**（否则会去探一格假格 `tid/scope/n_sites`）
#   ⇒ ⇒ ⛔ 表头还必须**显式验**（⛔ 列名不对 ⇒ 后面每一格都会错）
#   ⚖ ⚠ **向后兼容**：旧的 137 行清单**没有表头** ⇒ ⇒ 第一行不是表头 ⇒ ⇒ 原样当数据行用
HEADER=$(head -1 "$CELLS" 2>/dev/null || true)
HEADER_KIND=legacy_no_header
TMP_CELLS=$(mktemp "${TMPDIR:-/tmp}/r244_cells.XXXXXX")
# ⚖⚖⚖ 判别按**首行的字段数**（⛔ 不是按「有没有换行」⇒ 那对 `head -1` 取出来的行**恒为 0**⇒ ⇒ 会把旧清单也判成坏表头）
HEADER_NF=$(printf '%s' "$HEADER" | awk -F'\t' '{print NF}')
if [ "$HEADER_NF" -eq 4 ]; then
  if [ "$HEADER" = "$(printf 'tid\tscope\tn_sites\tpos_frac')" ]; then
    HEADER_KIND=header4
    tail -n +2 "$CELLS" > "$TMP_CELLS"
  else
    # ⚠⚠⚠ ⛔ **四列但表头不对** ⇒ ⇒ 那是**坏表头** ⇒ ⇒ 中止
    #   （⛔ 不许「当作没有表头」⇒ 那会把列名错的那一批照跑 ⇒ ⇒ 跑出来的格子全是错的）
    echo "ABORT 格清单是四列但表头不对（期望 tid/scope/n_sites/pos_frac）：$HEADER" >> "$LOG"
    echo "ALLDONE $(date +%T) ABORTED" >> "$LOG"
    echo "ALLDONE $(date +%T)" >> "$ST"
    rm -f "$TMP_CELLS"
    exit 9
  fi
else
  # ⚖ **旧清单**（3 列 / 无表头）⇒ ⇒ `pos_frac` 用**显式**默认（⛔ 印进日志 ⇒ 事后可核对）
  HEADER_KIND=legacy_no_header
  cp "$CELLS" "$TMP_CELLS"
fi
echo "CELLS header=$HEADER_KIND  header_nf=$HEADER_NF  data_rows=$(grep -c . "$TMP_CELLS" 2>/dev/null || echo 0)  $(date +%T)" >> "$LOG"

# ⚠⚠⚠ 修订 244.8：n_eff 映射表闸。⛔ 表不存在 / 为空 / pos_frac 不符 ⇒ 中止整批。
# ⚖ 理由：244.5 记录的缺陷是「BEGIN 无独立 n_eff ⇒ 读数器退回同源回退」。
# ⚖⚗ 本闸是那道死结的另一端：⛔ 不许「表没有就照跑」。
# ⚖⚖⚖ 244.77：**两种形态**（⛔ 靠后缀区分，不许猜）：
#   · `*.tsv` ⇒ **单表**（旧形态）⇒ ⇒ **只允许 `pos_frac = 0.5`**（⛔ 那张表的 `t`
#     是按 0.5 算的 ⇒ ⇒ 别的 `pos_frac` 用它 ⇒ `t` 会静默错 ⇒ ⇒ 下面会 ABORT）
#   · 其它 ⇒ **前缀** ⇒ ⇒ 按格拼 `${NMAP}_pf025 / _pf050 / _pf075`（⛔ 命名约定钉死）
if [ "${NMAP##*.}" = "tsv" ]; then
  NMAP_MODE=single
  if [ ! -s "$NMAP" ]; then
    echo "ABORT n_eff 映射表缺失或为空：$NMAP" >> "$LOG"
    echo "ALLDONE $(date +%T) ABORTED" >> "$LOG"
    echo "ALLDONE $(date +%T)" >> "$ST"
    rm -f "$TMP_CELLS"
    exit 9
  fi
  MAP_ROWS=$(($(wc -l < "$NMAP") - 1))
  MAP_MD5=$(md5sum "$NMAP" | cut -d' ' -f1)
  # ⚖⚖⚖ 244.77 ⑥：**来源戳的格式是契约**（⛔ 读数器认的是行首严格的
  #   `NMAP rows=<N> md5=<32hex>`）⇒ ⇒ **模式信息必须另起一行**，
  #   ⛔ 把 `mode=` 塞在行首 ⇒ 戳**不被认** ⇒ 读数器就判「n_eff 交叉校验
  #   **可能是恒等式**」⇒ ⇒ 那道守卫**从「能红」退化成「不能红」**。
  #   ⚖ ⚗ 本轮**一度**就是这样坏掉的 ⇒ ⇒ 由 1 格烟测 + 读数器读日志抓到。
  echo "NMAP rows=$MAP_ROWS md5=$MAP_MD5  $(date +%T)" >> "$LOG"
  echo "NMAP mode=$NMAP_MODE path=$NMAP  $(date +%T)" >> "$LOG"
else
  NMAP_MODE=prefix
  # ⚖⚖⚖ 244.77 ⑥：前缀形态 ⇒ **按清单里实际用到的 pos_frac** 收集那些表的
  #   rows 与 md5 ⇒ ⇒ 合成**一个**戳（⛔ 读数器遇到**两个不同**的戳会 HardFail
  #   「来源不可分辨」⇒ ⇒ 必须是**一个**戳）。
  #   ⚖ 合成口径：`rows` = 用到的表的数据行数之和；`md5` = 按 pos_frac 升序
  #   把 `pf<key>=<md5>` 拼起来再取 md5（⛔ 口径写死在这一处，别处不许另算）。
  MAP_ROWS=0
  MAP_PARTS=""
  MAP_TABLES=""
  # ⚖⚠ **逐格算实际生效的 pos_frac**（⛔ 第 4 列缺 ⇒ 用**显式**默认）
  #   ⇒ ⇒ 旧 3 列清单也能凑出戳（⛔ 向后兼容不许破）
  PFSET=$(awk -F'\t' -v DEF="$POS_FRAC_DEFAULT" \
            'NF>0 && $1!="" {pf=($4!=""?$4:DEF); printf "%.2f\n", pf}' "$TMP_CELLS" \
          | sort -u)
  for PFS in $PFSET; do
    PFKEY=$(printf '%.2f' "$PFS" | tr -d '.')
    T="${NMAP}_pf${PFKEY}.tsv"
    if [ ! -s "$T" ]; then
      echo "ABORT n_eff 表缺失或为空：$T" >> "$LOG"
      echo "ALLDONE $(date +%T) ABORTED" >> "$LOG"
      echo "ALLDONE $(date +%T)" >> "$ST"
      rm -f "$TMP_CELLS"
      exit 9
    fi
    R=$(($(wc -l < "$T") - 1))
    M=$(md5sum "$T" | cut -d' ' -f1)
    MAP_ROWS=$((MAP_ROWS + R))
    MAP_PARTS="${MAP_PARTS}pf${PFKEY}=${M}|"
    MAP_TABLES="${MAP_TABLES} pf${PFKEY}(rows=$R md5=$M)"
  done
  if [ -z "$MAP_PARTS" ]; then
    echo "ABORT 清单里一个 pos_frac 都没有 ⇒ 凑不出来源戳，拒绝跑" >> "$LOG"
    echo "ALLDONE $(date +%T) ABORTED" >> "$LOG"
    echo "ALLDONE $(date +%T)" >> "$ST"
    rm -f "$TMP_CELLS"
    exit 9
  fi
  MAP_MD5=$(printf '%s' "$MAP_PARTS" | md5sum | cut -d' ' -f1)
  echo "NMAP rows=$MAP_ROWS md5=$MAP_MD5  $(date +%T)" >> "$LOG"
  echo "NMAP mode=$NMAP_MODE prefix=$NMAP  tables:${MAP_TABLES}  composite=md5(${MAP_PARTS%|})  $(date +%T)" >> "$LOG"
fi

# ⛔ 格数闸：清单**数据行**不是 $EXPECT_CELLS ⇒ 中止，别跑半份。
# ⚖⚖⚖ 244.77：数**数据行**（⛔ 不是文件行数 ⇒ 表头不该被算进去 ⇒ 否则 168 会被数成 169）
N=$(grep -c . "$TMP_CELLS" 2>/dev/null || echo 0)
if [ "$N" -ne "$EXPECT_CELLS" ]; then
  echo "ABORT 格数=$N ≠ EXPECT_CELLS=$EXPECT_CELLS（清单可能没传对）" >> "$LOG"
  echo "ALLDONE $(date +%T) ABORTED" >> "$LOG"
  echo "ALLDONE $(date +%T)" >> "$ST"
  rm -f "$TMP_CELLS"
  exit 9
fi

# ⚖⚠ 扫描参数与 rand 臂**逐字相同**（修订 238 的 K23 会查一致性）。
# ⚖ 唯一改动：--arm rand → --arm w。
# ⚖⚖⚖ 244.77：⛔ **`--pos-frac` 从这里移走**（⇒ 它挪进循环 ⇒ 按格取 ⇒ 单一真源 = 清单）
C="--cell --npz-dir $B/gen_b2_max32768/aime --sidecar-dir $B/gen_b2_max32768/aime --labels $B/r182_1015_003713_label.json --w $W_PATH --gap 113.47440338134766 --n-steps 60 --alpha-max 120 --band 60 --gpu-uuid $GPU_UUID --arm $ARM --inject-nested"

i=0
PF_FALLBACK_LOGGED=0
# ⚖⚖⚖ 244.77 ②：**读 4 字段**（⛔ 旧清单第 4 列为空 ⇒ ⇒ 用**显式**默认，⛔ 只记一次）
while IFS=$'\t' read -r TID KIND VAL PF; do
  [ -n "$TID" ] || continue
  i=$((i+1))
  if [ -z "$PF" ]; then
    PF=$POS_FRAC_DEFAULT
    if [ "$PF_FALLBACK_LOGGED" -eq 0 ]; then
      PF_FALLBACK_LOGGED=1
      echo "CELLS pos_frac=**清单没给第 4 列** ⇒ 全批用**显式**默认 $PF（⚠ 这份清单是旧 3 列形态）" >> "$LOG"
    fi
  fi
  if [ "$KIND" = "k" ]; then
    SCOPE_ARGS="--inject-scope k --inject-n-sites $VAL"
  else
    SCOPE_ARGS="--inject-scope $VAL"
  fi
  # ⚖⚖⚖ 244.77 ③：**n_eff 表按 `pos_frac` 选**（⛔ 单表形态只许 0.5 ⇒ 别的 pos_frac ⇒ ABORT）
  if [ "$NMAP_MODE" = "single" ]; then
    if [ "$PF" != "0.5" ]; then
      echo "ABORT 第 $i 格 pos_frac=$PF，但 n_eff 表是**单表**（那张表的 t 按 0.5 算）⇒ 拒绝跑 t 会静默错的批" >> "$LOG"
      echo "ALLDONE $(date +%T) ABORTED" >> "$LOG"
      echo "ALLDONE $(date +%T)" >> "$ST"
      rm -f "$TMP_CELLS"
      exit 9
    fi
    NMAP_USED=$NMAP
  else
    PF_KEY=$(printf '%.2f' "$PF" | tr -d '.')
    # ⚖⚠ **命名约定**：`${前缀}_pf<KEY>.tsv`（⛔ 别名 `.tsv` ⇒ 拼出来的路径会找不到表）
    NMAP_USED="${NMAP}_pf${PF_KEY}.tsv"
    if [ ! -s "$NMAP_USED" ]; then
      echo "ABORT 第 $i 格 pos_frac=$PF 的 n_eff 表缺失或为空：$NMAP_USED" >> "$LOG"
      echo "ALLDONE $(date +%T) ABORTED" >> "$LOG"
      echo "ALLDONE $(date +%T)" >> "$ST"
      rm -f "$TMP_CELLS"
      exit 9
    fi
  fi
  # ⚠⚠⚠ 修订 244.8：BEGIN 行现在带 `n_eff=`，来源是**跑批之前**独立算出的
  # ⚖   P = len(tokenizer(chat_template_input))  ← 重编码，不读侧车自报字段
  # ⚖   t = max(1, int(len(npz token_ids) * pos_frac))
  # ⚖⇒ 读数器 `b["n_eff"] != pt_sum`（r227_kcurve.py:214）**第一次变成可红的**：
  # ⚖   BEGIN 的独立值 vs 探针自报的 P+t，两者不一致就 HardFail。
  # ⚖ ⛔ 244.5 判 r232 那种「从上一轮读数回填」为恒绿守卫并明令不许用。
  # ⚖ ⚗ 若此处查不到 tid ⇒ **中止整批**，⛔ 绝不回退成「不写 n_eff=」——
  # ⚖    静默缺字段会让读数器退回同源回退路径，那正是 244.5 记录的缺陷。
  NEFF=$(awk -F'\t' -v t="$TID" '$1==t {print $6; found=1} END{if(!found) exit 1}' "$NMAP_USED")
  if [ -z "$NEFF" ]; then
    echo "ABORT 第 $i 格 tid=$TID 不在 n_eff 映射表里（表 $NMAP_USED）⇒ 拒绝跑无独立来源的批" >> "$LOG"
    echo "ALLDONE $(date +%T) ABORTED" >> "$LOG"
    echo "ALLDONE $(date +%T)" >> "$ST"
    rm -f "$TMP_CELLS"
    exit 9
  fi
  # ⚠⚠⚠ 修订 244.1 修复：**tid 必须是 `### BEGIN` 后的第一个 token**。
  # ⚖ `r227_kcurve.BEGIN_RE` 契约是
  #     ^###\s+BEGIN\s+(?P<tid>\S+)(?P<rest>.*?)\s\s+(?P<time>\d\d:\d\d:\d\d)\s*$
  # ⚖ 第一版把 `[i/n]` 印在 tid **之前** ⇒ 读数器把 `[1/137]` 当 tid，
  # ⚖    立刻 HardFail「第 1 格 tid 对不上」。
  # ⚖⇒ 序号移到 **rest 内**（读数器 `rest` 不解析它，无害），
  # ⚖   同时保留「第几格」的可见性。END 行同理，读数器不解析 END。
  # ⚖ ⚗ 本脚本已产出过 2026-10-17 那份日志（用了旧的错写法）；
  # ⚖  本次只改**未来**跑批的写法，⛔ 不去改已落盘的产物
  # ⚖    （改产物会让「脚本说的」与「产物是的」不一致）。
  echo "### BEGIN $TID [$i/$EXPECT_CELLS] n_eff=$NEFF $SCOPE_ARGS  $(date +%T)" >> "$LOG"
  # ⚖⚖⚖ 244.77 ②：`--pos-frac` **按格**传（⛔ 两臂仍逐字相同 ⇒ ⇒ K23 仍成立）
  $PY $B/r241_probe.py $C --pos-frac "$PF" --tid "$TID" $SCOPE_ARGS >> "$LOG" 2>&1
  rc=$?
  # ⚖ 状态行与 r227_status.txt 同形，便于读数器对账
  if [ "$KIND" = "k" ]; then
    echo "$TID k=$VAL rc=$rc" >> "$ST"
  else
    echo "$TID scope=$VAL rc=$rc" >> "$ST"
  fi
  echo "### END   [$i/$EXPECT_CELLS] $TID rc=$rc  $(date +%T)" >> "$LOG"
done < "$TMP_CELLS"
rm -f "$TMP_CELLS"
echo "SWEEPDONE cells=$i  $(date +%T)" >> "$LOG"
echo "ALLDONE $(date +%T)" >> "$ST"
