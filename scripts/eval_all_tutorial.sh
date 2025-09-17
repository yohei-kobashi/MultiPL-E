#!/usr/bin/env bash

set -euo pipefail

# Batch-evaluate all completion JSON(.gz) files under tutorial/
# Usage: scripts/eval_all_tutorial.sh [INPUT_ROOT=tutorial] [OUTPUT_BASE=scores] [WORKERS=8]

INPUT_ROOT=${1:-tutorial}
OUTPUT_BASE=${2:-scores}
WORKERS=${3:-8}

# Resolve to absolute paths to be robust against directory changes
INPUT_ROOT_ABS=$(realpath "$INPUT_ROOT")
OUTPUT_BASE_ABS=$(realpath -m "$OUTPUT_BASE")

mkdir -p "$OUTPUT_BASE_ABS"

# Collect unique directories that contain .json or .json.gz
mapfile -t JSON_DIRS < <(find "$INPUT_ROOT_ABS" -type f \( -name '*.json' -o -name '*.json.gz' \) -printf '%h\n' | sort -u)

if [[ ${#JSON_DIRS[@]} -eq 0 ]]; then
  echo "No completion files found under: $INPUT_ROOT_ABS" >&2
  exit 1
fi

echo "Found ${#JSON_DIRS[@]} directories with completion files."

# Run evaluator for each directory
for DIR in "${JSON_DIRS[@]}"; do
  BASENAME=$(basename "$DIR")
  OUTDIR="$OUTPUT_BASE_ABS/$BASENAME"
  echo "[Eval] $DIR -> $OUTDIR (workers=$WORKERS)"

  # Run from completion_eval_analysis so relative lang2url.json resolves
  (
    cd completion_eval_analysis
    python send_query_to_multipl_eval_server.py \
      --query_input_dir "$DIR" \
      --output_base_dir "$OUTPUT_BASE_ABS" \
      --num_workers "$WORKERS"
  )
done

echo "All evaluations submitted. Results saved under: $OUTPUT_BASE_ABS"

