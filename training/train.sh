#!/usr/bin/env bash
# Fine-tune the router. Reproducible end to end:
#
#   ./training/train.sh
#   python evals/run_routing.py --router tuned --compare evals/results/llm-llama31-8b-v2.json
#
# LoRA rather than full fine-tuning: a 6-label classifier needs a small nudge to
# the output distribution, not new knowledge, and the adapter is ~14MB against a
# multi-GB model. 4-bit base keeps it inside 16GB with room to spare.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT/.venv/bin/python"

MODEL="${MODEL:-mlx-community/Llama-3.2-3B-Instruct-4bit}"
ITERS="${ITERS:-400}"
BATCH="${BATCH:-4}"
LAYERS="${LAYERS:-8}"          # top-N layers get adapters; more isn't better on 256 examples
LR="${LR:-1e-4}"

"$PYTHON" "$ROOT/training/prepare_data.py"

echo
echo "Fine-tuning $MODEL — $ITERS iters, batch $BATCH, $LAYERS layers, lr $LR"
"$PYTHON" -m mlx_lm lora \
  --model "$MODEL" \
  --train \
  --data "$ROOT/training/data" \
  --iters "$ITERS" \
  --batch-size "$BATCH" \
  --num-layers "$LAYERS" \
  --learning-rate "$LR" \
  --steps-per-report 25 \
  --steps-per-eval 100 \
  --adapter-path "$ROOT/training/adapters"

echo
echo "Adapter written to training/adapters/"
echo "Evaluate:  $PYTHON evals/run_routing.py --router tuned --compare evals/results/llm-llama31-8b-v2.json"
