#!/usr/bin/env bash
# Re-render the architecture figures from the Diagram IR JSONs.
# Usage: ./render_all.sh            # all figures
#        ./render_all.sh a f g      # selected figures
set -euo pipefail
cd "$(dirname "$0")"

FW="${FIREWORKS_PY:-/home/yf/.claude/skills/fireworks-tech-graph/scripts/fireworks.py}"

declare -A NAME=(
  [a]=fig_a_concept_architecture
  [b]=fig_b_seven_layer_view
  [e]=fig_e_diffusion_subsystem
  [f]=fig_f_npu_execution_path
  [c]=fig_c_mindiesd_cooperation
  [d]=fig_d_liteboost_cooperation
  [g]=fig_g_npu_gap_map
  [h]=fig_h_dit_call_chain
  [i]=fig_i_qwen3_tts_dataflow
  [j]=fig_j_startup_chain
)

KEYS=("$@")
[ ${#KEYS[@]} -eq 0 ] && KEYS=(a b e f c d g)

python3 build_specs.py "${KEYS[@]}" >/dev/null

for k in "${KEYS[@]}"; do
  out="../${NAME[$k]}.png"
  python3 "$FW" render architecture "fig_$k.json" "fig_$k.svg" --report "fig_${k}_layout.json" >/dev/null
  python3 "$FW" check "fig_$k.svg" >/dev/null
  python3 "$FW" export-png "fig_$k.svg" "$out" --width 1920 >/dev/null
  echo "fig_$k -> $out"
done
