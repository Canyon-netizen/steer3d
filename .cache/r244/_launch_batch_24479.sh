#!/bin/bash
# ⚖ 244.79：**固定剂量那一批**（336 次探针 = 168 格 × 2 臂），两臂**并行**
# ⚖ ⚠ 决策：**跑 336 而不是 308** ⇒ ⇒ 多出的 28 次**不是浪费**：
#   它们是旧批（10-17，pos_frac=0.5）那 28 格的**复测**
#   ⇒ ⇒ 白得一组**复现性对账**（旧批日志 `r244_warm_w.log` / `r244_warm_rand.log`）
#   ⇒ ⇒ 且**不用**实现「跳过可复用格 + 把旧读数拼进来」这种新机制
#   ⇒ ⇒ 全部 336 次来自**同一次跑批、同一把向量、同一个会话** ⇒ 内部可比性最大
# ⚖ ⛔ 全部按脚本文件 + setsid 起（⛔ 永不内联 ssh 起跑批）
set -u
B=/home/zhourui/steer3d_bpath
OUT=/dev/shm/_batch24479
mkdir -p $OUT
echo "=== 244.79 固定剂量批 启动 $(date '+%F %T') host=$(hostname) ==="

# ---- 前置逐条核对（⛔ 任何一条不对就不许起）----
fail=0
chk() { if [ "$2" = "$3" ]; then echo "OK   $1 = $2"; else echo "BAD  $1 = $2 (期望 $3)"; fail=1; fi; }
chk runner_md5       "$(md5sum $B/r244_warm_sweep.sh | cut -d' ' -f1)" "5d9cdffeafdbf5fe83195db183ee17a3"
chk cells_md5        "$(md5sum $B/warm_cells_fixed_dose.tsv | cut -d' ' -f1)" "b3de113e028720b3d0ee92f7cd0b9e99"
chk nmap_pf025_md5   "$(md5sum $B/n_eff_map_pf025.tsv | cut -d' ' -f1)" "942165e3c155f4d69eba4ed933a10eeb"
chk nmap_pf050_md5   "$(md5sum $B/n_eff_map_pf050.tsv | cut -d' ' -f1)" "c0d30d22226765b71107ba4db8a2f5af"
chk nmap_pf075_md5   "$(md5sum $B/n_eff_map_pf075.tsv | cut -d' ' -f1)" "8c865128a5fe73a54664be8f31a76659"
chk w_p2a_md5        "$(md5sum $B/w_p2a.npy | cut -d' ' -f1)" "d8e6a066d55a6e5196ff706bd59bcedb"
chk cells_data_rows  "$(($(wc -l < $B/warm_cells_fixed_dose.tsv) - 1))" "168"
chk cells_header     "$(head -1 $B/warm_cells_fixed_dose.tsv)" "$(printf 'tid\tscope\tn_sites\tpos_frac')"
if [ "$fail" != "0" ]; then echo "⛔ 前置不过 ⇒ 不起跑批"; exit 9; fi

# ---- 两臂并行（各一张空闲卡）----
# ⚖ 显式传 W_PATH = bpath 那份（⛔ 与 /tmp 那份逐字节相同 ⇒ 但 bpath 这份不会被清掉）
setsid nohup bash $B/r244_warm_sweep.sh GPU-2f39bcda-a2b4-0090-ef0a-cbee082cac9e \
    $B/warm_cells_fixed_dose.tsv $B/n_eff_map 168 _fd_w w 0.5 $B/w_p2a.npy \
    > $OUT/w_launch.log 2>&1 < /dev/null &
echo "w 臂 PID=$!"

setsid nohup bash $B/r244_warm_sweep.sh GPU-c80d6363-0d00-7086-6ecf-017c71940f3f \
    $B/warm_cells_fixed_dose.tsv $B/n_eff_map 168 _fd_rand rand 0.5 $B/w_p2a.npy \
    > $OUT/rand_launch.log 2>&1 < /dev/null &
echo "rand 臂 PID=$!"

sleep 5
echo "--- 起批参数（入收据）---"
date '+%F %T' > $OUT/launch_params.txt
cat >> $OUT/launch_params.txt <<EOF
runner=$B/r244_warm_sweep.sh  md5=5d9cdffeafdbf5fe83195db183ee17a3
cells=$B/warm_cells_fixed_dose.tsv  md5=b3de113e028720b3d0ee92f7cd0b9e99  data_rows=168
nmap_prefix=$B/n_eff_map  (pf025/pf050/pf075 三张)
w=$B/w_p2a.npy  md5=d8e6a066d55a6e5196ff706bd59bcedb
w_arm=GPU-2f39bcda-a2b4-0090-ef0a-cbee082cac9e  TAG=_fd_w
rand_arm=GPU-c80d6363-0d00-7086-6ecf-017c71940f3f  TAG=_fd_rand
EXPECT_CELLS=168  POS_FRAC_DEFAULT=0.5  ARM=w|rand
计划总探针数=336
EOF
cat $OUT/launch_params.txt
echo "=== 已起 ==="
