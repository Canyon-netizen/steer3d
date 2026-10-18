#!/bin/bash
# 修订 244.11 —— 跑批完成后的判决流水线（一条命令，每道闸可见）。
#
# ⚖⚖ 为什么固化成脚本而不是手工串五步：
# ⚖   ① **配对错误是最容易犯、且最难发现的错**。两臂各有两个文件
# ⚖      （日志 + 状态），配错一对**不会报错**，只会安静地给出一个
# ⚖      看起来正常的判决 —— 这正是 244.9.4 那个「拿同一份比自己还给出答案」的洞。
# ⚖   ② 五步里有三道闸，漏跑任何一道就等于把结论建在一个未验证的前提上。
# ⚖   ③ 判决要可复现：别人拿到同一批文件应当得到逐字节相同的报告。
#
# ⚠ 本脚本⛔ 不做任何判定，只负责「按顺序跑完并把每道闸的结果打出来」。
# ⚠ 判读仍由人做；脚本的输出末尾明写了它不能替你回答什么。
set -u
R=${1:?用法: verdict_pipeline.sh <远端主机> <远端基目录>}
HERE=$(cd "$(dirname "$0")" && pwd)
READER=$HERE/../mutbak/r227_kcurve.py
CELL_COUNT=${2:-137}
FAIL=0

step() { echo; echo "=== $1 ==="; }

step "0 前置：文件在不在"
if [ ! -f "$READER" ]; then
  echo "PRECOND_FAIL 读数器不在: $READER"; exit 2
fi

for f in r244_warm_w.log r244_warm_w_status.txt \
         r244_warm_rand.log r244_warm_rand_status.txt \
         r244_run274_launch.log; do
  if ! scp -q "$R:/home/zhourui/steer3d_bpath/$f" "$HERE/$f"; then
    echo "PRECOND_FAIL 拉不到 $f ⇒ 跑批可能还没完，或臂 2 没接上"
    echo "              ⛔ 不用旧日志顶替（那是 242.2 明令不许的「不回填既有日志」）"
    exit 2
  fi
done
echo "四个产物 + 启动日志已就位"
echo "--- 启动日志 ---"
cat "$HERE/r244_run274_launch.log"

step "1 两臂是否都跑完（ALLDONE）"
# ⚠⚠⚠ 修订 244.17：这一段原来**读了 ALLDONE 却从不拿它做判定** ——
# ⚖ 算出来的 n 只被 printf 打印，后面所有的 if 都没用它。
# ⚖ ⇒ 一份**没跑完**的状态文件（没有 ALLDONE）会一路穿过后面的闸，
# ⚖   直到读数器才拒 ⇒ 闸 1 的名字与它实际做的事**对不上**。
# ⚖⇒ 改成真判定：轮数必须恰为 1。⛔ 多于 1 同样拒 ——
# ⚖   多轮并集意味着「那一轮的戳被当成了整体」（244.16 记的那个错基准）。
for arm in w rand; do
  ST="$HERE/r244_warm_${arm}_status.txt"
  n=$(grep -c '^ALLDONE' "$ST" 2>/dev/null || true)
  n=${n:-0}
  cells=$(grep -c 'rc=' "$ST" 2>/dev/null || true)
  printf '  arm %-5s ALLDONE=%s  格数=%s\n' "$arm" "$n" "${cells:-0}"
  if [ "$n" -ne 1 ]; then
    echo "  ⛔ arm=$arm 的 ALLDONE 计数=$n，要求恰为 1"
    if [ "$n" -eq 0 ]; then
      echo "     ⇒ 该轮**没跑完**，或状态文件被截断"
    else
      echo "     ⇒ 多轮并集：那一轮的戳不能描述整体（见修订 244.16）"
    fi
    FAIL=1
  fi
done
W_N=$(grep -c "rc=" "$HERE/r244_warm_w_status.txt")
R_N=$(grep -c "rc=" "$HERE/r244_warm_rand_status.txt")
W_BAD=$(grep "rc=" "$HERE/r244_warm_w_status.txt" | grep -vc "rc=0")
R_BAD=$(grep "rc=" "$HERE/r244_warm_rand_status.txt" | grep -vc "rc=0")
echo "  非零 rc：w=$W_BAD rand=$R_BAD"
if [ "$W_N" -ne "$CELL_COUNT" ] || [ "$R_N" -ne "$CELL_COUNT" ]; then
  echo "ABORT 格数 w=$W_N rand=$R_N ≠ $CELL_COUNT"; FAIL=1
fi
if [ "$W_BAD" -ne 0 ] || [ "$R_BAD" -ne 0 ]; then
  echo "ABORT 有非零 rc"; FAIL=1
fi

step "2 BEGIN 行的 n_eff 覆盖率（新生产者是否真的写了独立来源）"
for arm in w rand; do
  tot=$(grep -c "### BEGIN" "$HERE/r244_warm_${arm}.log")
  witheff=$(grep -c "### BEGIN.*n_eff=" "$HERE/r244_warm_${arm}.log")
  printf '  arm %-5s BEGIN=%s  带 n_eff=%s\n' "$arm" "$tot" "$witheff"
  if [ "$witheff" -ne "$tot" ]; then
    echo "  ⛔ 有 BEGIN 缺 n_eff ⇒ 读数器会走同源回退分支（244.5 记的缺陷）"
    FAIL=1
  fi
done

step "3 规范化（闸：合规输入必须是恒等）"
for arm in w rand; do
  M=$(md5 -q "$HERE/r244_warm_${arm}.log")
  if python3 "$HERE/normalize_begin.py" --log "$HERE/r244_warm_${arm}.log" \
       --status "$HERE/r244_warm_${arm}_status.txt" \
       --out "$HERE/r244_warm_${arm}.norm.log" --expect-md5 "$M" \
       > "$HERE/norm_${arm}.txt" 2>&1; then
    if cmp -s "$HERE/r244_warm_${arm}.log" "$HERE/r244_warm_${arm}.norm.log"; then
      echo "  arm $arm: 闸全过，且转换是恒等（合规）"
    else
      echo "  arm $arm: ⚠ 闸过了但产物变了 ⇒ 生产者写的不是契约格式，查 norm_${arm}.txt"
      FAIL=1
    fi
  else
    echo "  arm $arm: ⛔ 规范化闸未过"; sed -n '1,6p' "$HERE/norm_${arm}.txt"
    FAIL=1
  fi
done

step "4 两臂各读各的（⛔ 不交叉配对）"
for arm in w rand; do
  echo "--- $arm ---"
  python3 "$READER" --log "$HERE/r244_warm_${arm}.norm.log" \
    --status "$HERE/r244_warm_${arm}_status.txt" \
    > "$HERE/read_${arm}.txt" 2>&1
  rc=$?
  echo "  读数器 rc=$rc"
  if [ "$rc" -ne 0 ]; then
    echo "  ⛔ 拒读："; tail -3 "$HERE/read_${arm}.txt"
    FAIL=1
  else
    # ⚖⚠ 修订 244.24：`n_eff 交叉校验能否红` 这行必须进流水线输出。
    # ⚖ 它是判断「BEGIN 的 n_eff 有没有独立来源证据」的唯一一处；只在读数器
    # ⚖ 自己的输出里、而流水线看不到 ⇒ 判读的人会以为那道交叉校验是真证据。
    grep -E "n_eff 交叉校验能否红" "$HERE/read_${arm}.txt"
    grep -E "n_eff=|无崩格|低于地板|贴地板" "$HERE/read_${arm}.txt" | head -4
  fi
done

step "5 跨臂判决"
python3 "$HERE/arm_verdict.py" --reader "$READER" \
  --w-log "$HERE/r244_warm_w.norm.log" --w-status "$HERE/r244_warm_w_status.txt" \
  --rand-log "$HERE/r244_warm_rand.norm.log" \
  --rand-status "$HERE/r244_warm_rand_status.txt" \
  --expect-cells "$CELL_COUNT"
rc=$?
[ "$rc" -ne 0 ] && { echo "  ⛔ 判决层拒绝出结论（rc=$rc）"; FAIL=1; }

step "6 两臂算力条件可比性（244.16 起为**必需**，不是可选补充）"
CC_OUT=$(python3 "$HERE/compute_conditions.py" --w-log "$HERE/r244_warm_w.norm.log" \
  --rand-log "$HERE/r244_warm_rand.norm.log")
rc=$?
echo "$CC_OUT"
[ "$rc" -ne 0 ] && FAIL=1
if ! grep -q "两臂算力条件" <<<"$CC_OUT"; then
  echo "  ⛔ 算力条件未量到 ⇒ 244.16.5 登记要求它必须与主统计量同报"
  FAIL=1
fi

step "7 ✅ 预登记的**主统计量**（修订 244.14.5 / 244.15）"
# ⚠⚠⚠ 这一步**必须在这里、必须自动跑**。它是**看到数据之前**定死的统计量。
# ⚖⚗ 第一版流水线**漏了它** ⇒ 跑完只能临时补算，而临时补算正是预登记要防的事：
# ⚖⚗   时间压力下最可能发生的不是「忘了跑」，而是「先看了别的数字再决定跑哪个」。
# ⚖⇒ 所以它不是可选的一步，而是**失败即中止**的一步。
python3 "$HERE/upmono_verdict.py" --reader "$READER" \
  --w-log "$HERE/r244_warm_w.norm.log" --w-status "$HERE/r244_warm_w_status.txt" \
  --rand-log "$HERE/r244_warm_rand.norm.log" \
  --rand-status "$HERE/r244_warm_rand_status.txt" \
  --expect-cells "$CELL_COUNT"
rc=$?
if [ "$rc" -ne 0 ]; then
  echo "  ⛔ 主统计量未产出（rc=$rc）⇒ 预登记的判据没跑出来，⛔ 不要用别的统计量顶替"
  FAIL=1
fi

step "8 两臂是否真是**两个实验**（跨臂判决的前提，此前从未单独验过）"
# ⚠⚠⚠ 修订 244.25 新增。这一闸问的是**前提**，不是读数：
# ⚖   跨臂判决（Fisher / 符号检验）要成立，两臂必须是两次不同的实验。
# ⚖⚗ 它此前只是**隐含**在「两臂 p 值不同」里 —— 而 p 不同也可以来自别的原因
# ⚖   （格数不同 / 少了几格 / 配对错位 / 把同一份日志当两臂传）。
# ⚖⚠ 最要命的一种：把同一份日志传两遍 ⇒ 逐位相同 ⇒ 判决是恒等式
# ⚖   ⇒ 所有 p 无意义，而报告看上去和正常情况一模一样。
# ⚖⚗ 关键一步：比之前**先剥掉 `arm` 字段** —— 不剥的话两臂必然「不同」，
# ⚖   而那个不同可能只由臂名解释，对「读数有没有变」零信息量。
python3 "$HERE/two_experiment_check.py" --label-a w --label-b rand \
  "$HERE/r244_warm_w.norm.log" "$HERE/r244_warm_rand.norm.log"
rc=$?
if [ "$rc" -ne 0 ]; then
  echo "  ⛔ 两臂未被证明是两个实验 ⇒ 跨臂判决（闸 5 / 闸 7 的 Fisher）**不成立**"
  FAIL=1
fi

step "9 按**机制**分层的敏感性分析（244.27.2 的直接后果）"
# ⚠⚠⚠ 修订 244.28 新增。为什么要一道闸：
# ⚖   244.27.2 查出读出在**最后一位**，而位点由种子 0 置换均匀挑出
# ⚖   ⇒ 某些档**直接**扰动读出位置、某些只经**传播**
# ⚖   ⇒ 「剂量—响应」曲线上不同点**不是同一个机制的两个剂量**。
# ⚖⚗ 实测：主判决的方向在两层一致（都是 w 侧高），**但幅度差 4.5 倍**
# ⚖   （直接 +64.3pp / 传播 +14.3pp），两层 Fisher p 差 1210 倍
# ⚖   ⇒ **效应几乎全部由「直接」层承载** ⇒ 引用通过率差时必须同报分层。
# ⚖⚠ 这是一条**事后**分析：⛔ 它不替换预登记主统计量（那是闸 7），
# ⚖   ⛔ 也⛔ 不得只报对自己有利的那一层。
# ⚖⇒ 只有「两层方向相反」才让流水线停（rc=1）；幅度差只报告不拦。
python3 "$HERE/mechanism_strat.py" --reader "$READER" \
  --w-log "$HERE/r244_warm_w.norm.log" --w-status "$HERE/r244_warm_w_status.txt" \
  --rand-log "$HERE/r244_warm_rand.norm.log" \
  --rand-status "$HERE/r244_warm_rand_status.txt" \
  --map "$HERE/n_eff_map.tsv" --expect-cells "$CELL_COUNT"
rc=$?
if [ "$rc" -ne 0 ]; then
  echo "  ⛔ 两层机制给出的方向相反（或某层未量到）⇒ 跨臂通过率差**对机制分层敏感**，⛔ 不得单独引用"
  FAIL=1
fi

echo
step "10 **剂量轴审计**：这套阶梯是否真在测剂量（零 GPU，244.31）"
# ⚠⚠⚠ 修订 244.31 新增。为什么要一道闸：
# ⚖   244.30 查出：真正的剂量阶梯（覆盖 ≤50%）单独看 Fisher p=0.7036 ⇒ 无差异。
# ⚖⚠⇒ 于是必须问一个**结构**问题：剂量轴与机制轴（是否直接扰动读出位点）
# ⚖   在这套阶梯里**是否可分离**。
# ⚖⚗ 实测（三条腿，修订 244.32）：
# ⚖   ① 总体梯度**存在**：rho(覆盖率, 原始响应) 两臂 14/14 正号，p=1.2e-4
# ⚖   ② 但**轨迹内成对台阶**才是干净的机制对比（prompt/问题固定）：
# ⚖      w 臂 14/14 正号（p=1.2e-4），中位比值 **11.84×**；
# ⚖      rand 臂 8/14（p=0.79），中位比值 **1.00×** ⇒ 台阶是 **w 特有**的。
# ⚖   ③ 而**层内**（机制固定）两臂都**看不到**强剂量梯度：
# ⚖      w 传播层 9/14（p=0.42）、直接层 6/7（p=0.125，7 条因档数<3 被剔）。
# ⚖⇒ ⚠⚠ **台阶跨了 Δcov 中位 0.25** ⇒ 它是「机制 + 剂量」的**合成**，
# ⚖   ⛔ 不可单独读成纯机制效应；而层内也没有剂量效应可减。
# ⚗⇒ 结论：这套阶梯的形状主要由**机制切换**决定，⛔ 不是一条剂量轴。
# ⚖⚠⚠ 本闸只报不拦。它**不替换**任何预登记统计量（那是闸 7）。
python3 "$HERE/dose_axis_audit.py" --w-log "$HERE/r244_warm_w.norm.log" \
  --rand-log "$HERE/r244_warm_rand.norm.log" \
  --probe "$HERE/../mutbak/r204_noise_probe.py"
rc=$?
if [ "$rc" -ne 0 ]; then
  echo "  ⛔ 剂量轴审计拒读（阶梯不可比 / 档口径自相矛盾 / 位点集不可用）⇒ 上面的剂量读数**全部作废**"
  FAIL=1
fi

echo
echo "=== 汇总 ==="
if [ "$FAIL" -ne 0 ]; then
  echo "⛔ 至少一道闸未过 ⛔ 上面的数字**不要**当判决读。"
  echo "   逐条处理：先修生产者/补数据，⛔ 不要为了让它变绿去放宽读数器。"
  exit 1
fi
# ⚖⚠ 修订 244.24：原文写「七道闸」，而 `grep -c '^step '` 实测 **8**（闸 0–7）
# ⚖ ⇒ 一个数错的总结句比没有更坏：读的人会以为少了一道。改为**数出来**，
# ⚖⛔ 不写死字面量 —— 以后加减闸，这个数自己跟着对。
echo "$(grep -c '^step ' "$0")道闸全过。下面是读数，不是判决："
echo "⚠ 它不回答：剂量响应对不对 / 阶梯排对了没有 / 共卡有没有改变读数。"
echo "⚖ 判读前先看 below_floor 与 knife_edge 两列 —— 它们决定有多少结论被噪声主导。"
