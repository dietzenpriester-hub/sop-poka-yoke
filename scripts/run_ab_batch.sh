#!/usr/bin/env bash
# 动作识别 A/B 批量实验：两个场景 × 单帧/多帧/自适应 × 多次重复。
# 重复跑在产线温度 0.1 下进行，用于量化模型采样噪声对指标的影响。
#
# MODES 取值：
#   1     全步骤单帧（对照）
#   4     全步骤 4 帧，关闭自适应（对照上一轮幻觉）
#   4a    4 帧窗口 + place 类降为单帧（本轮优化）
set -u

PY=packages/edge/.venv/bin/python
REPEATS=${REPEATS:-3}
FIRST_REP=${FIRST_REP:-1}
COOLDOWN=${COOLDOWN:-0.5}
IDLE_MAX=${IDLE_MAX:-1.5}
TEMP=${TEMP:-0.1}
MODES=${MODES:-"1 4 4a"}
# 已有结果默认跳过，便于中断后续跑
SKIP_EXISTING=${SKIP_EXISTING:-1}

run() {
  local scene=$1 video=$2 timeline=$3 template=$4 mode=$5 rep=$6
  local window=${mode%a}
  local adaptive_flag=()
  case "$mode" in
    *a) ;;  # 4a：默认自适应，place 类降为单帧
    *) adaptive_flag=(--no-adaptive-window) ;;
  esac
  local label="${scene}_w${mode}_r${rep}"
  if [ "$SKIP_EXISTING" = "1" ] && [ -s "eval/results/${label}_summary.json" ]; then
    echo "[$(date +%H:%M:%S)] skip ${label}（已有结果）"
    return
  fi
  $PY scripts/eval_action_recognition.py \
    --video "$video" --timeline "$timeline" --template "$template" \
    --frame-window "$window" --no-reference \
    --gate-cooldown "$COOLDOWN" --idle-max "$IDLE_MAX" --temperature "$TEMP" \
    ${adaptive_flag[@]+"${adaptive_flag[@]}"} \
    --label "$label" > "/tmp/ab_${label}.log" 2>&1
  echo "[$(date +%H:%M:%S)] done ${label}"
}

for rep in $(seq "$FIRST_REP" "$REPEATS"); do
  for mode in $MODES; do
    run desk \
      data/clips/12345_step2_STEP_NG_20260331_183429.mp4 \
      eval/annotations/deskclip_timeline.csv \
      eval/sop_template.deskclip.json "$mode" "$rep"
    run pickup \
      data/clips/AUTO-20260402-154649_step1_STEP_NG_20260402_154901.mp4 \
      eval/annotations/pickup_timeline.csv \
      eval/sop_template.pickup.json "$mode" "$rep"
  done
done
echo "ALL DONE"
