#!/usr/bin/env bash

set -euo pipefail

# Run pass_k.py over all immediate subdirectories under a given root
# and aggregate results into a single CSV file.
#
# Usage: scripts/pass_k_all.sh [INPUT_ROOT=scores] [OUTPUT_CSV=passk_summary.csv] [K(optional)]
# - INPUT_ROOT: Root directory whose immediate subdirectories are evaluated.
# - OUTPUT_CSV: Path to the aggregated CSV output.
# - K: Optional k value to additionally report (pass_k.py -k K).
#
# Example:
#   bash scripts/pass_k_all.sh                      # scans ./scores/* and writes ./passk_summary.csv
#   bash scripts/pass_k_all.sh scores out.csv       # writes to out.csv
#   bash scripts/pass_k_all.sh scores out.csv 20    # also prints pass@20 rows

INPUT_ROOT=${1:-scores}
OUTPUT_CSV=${2:-passk_summary.csv}
K_VALUE=${3:-}

# Resolve absolute paths for robustness
INPUT_ROOT_ABS=$(realpath "$INPUT_ROOT")
OUTPUT_CSV_ABS=$(realpath -m "$OUTPUT_CSV")

if [[ ! -d "$INPUT_ROOT_ABS" ]]; then
  echo "Input root not found: $INPUT_ROOT_ABS" >&2
  exit 1
fi

# Collect immediate subdirectories that directly contain at least one .json/.json.gz
mapfile -t SUBDIRS < <(find "$INPUT_ROOT_ABS" -mindepth 1 -maxdepth 1 -type d -print | sort)

TARGET_DIRS=()
for DIR in "${SUBDIRS[@]}"; do
  if find "$DIR" -maxdepth 1 -type f \( -name '*.json' -o -name '*.json.gz' \) -print -quit | grep -q .; then
    TARGET_DIRS+=("$DIR")
  fi
done

if [[ ${#TARGET_DIRS[@]} -eq 0 ]]; then
  echo "No result directories with .json/.json.gz found under: $INPUT_ROOT_ABS" >&2
  exit 1
fi

# Prepare output: write header once
echo "Dataset,Pass@k,Estimate,NumProblems,MinCompletions,MaxCompletions" > "$OUTPUT_CSV_ABS"

echo "Aggregating pass@k for ${#TARGET_DIRS[@]} directories -> $OUTPUT_CSV_ABS"

# Aggregate per-directory rows into a temp file first
TMP_ROWS=$(mktemp)
trap 'rm -f "$TMP_ROWS"' EXIT

for DIR in "${TARGET_DIRS[@]}"; do
  if [[ -n "$K_VALUE" ]]; then
    python completion_eval_analysis/pass_k.py --suppress-header -k "$K_VALUE" "$DIR" >> "$TMP_ROWS"
  else
    python completion_eval_analysis/pass_k.py --suppress-header "$DIR" >> "$TMP_ROWS"
  fi
done

# Copy per-directory rows to the final CSV
cat "$TMP_ROWS" >> "$OUTPUT_CSV_ABS"

# Now compute per-benchmark totals (weighted by NumProblems) and append
# Benchmarks are identified by directory name prefixes: humaneval*, mbpp*
K_LIST=(1 10 100)
if [[ -n "$K_VALUE" ]]; then
  # Add K_VALUE if not already present
  if ! printf '%s\n' "${K_LIST[@]}" | grep -qx -- "$K_VALUE"; then
    K_LIST+=("$K_VALUE")
  fi
fi

for BENCH in humaneval mbpp; do
  for K in "${K_LIST[@]}"; do
    # Weighted average of Estimate by NumProblems; also aggregate counts and completion bounds
    awk -F',' -v pref="$BENCH" -v kval="$K" '
      $1 ~ ("^" pref) && $2 == kval {
        sum_est += ($3 * $4);
        sum_n   += $4;
        if (minc == "" || $5+0 < minc) { minc = $5+0 }
        if ($6+0 > maxc) { maxc = $6+0 }
      }
      END {
        if (sum_n > 0) {
          est = sum_est / sum_n;
          # Print with high precision to match python float formatting style
          printf "%s-total,%d,%.16f,%d,%d,%d\n", pref, kval, est, sum_n, minc, maxc;
        }
      }' "$TMP_ROWS" >> "$OUTPUT_CSV_ABS"
  done
done

echo "Done. CSV saved to: $OUTPUT_CSV_ABS"
