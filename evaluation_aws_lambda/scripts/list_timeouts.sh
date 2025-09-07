#!/usr/bin/env bash

# List AWS Lambda timeout (seconds) for all language-specific container functions
# deployed by this repo. Tries to mirror deploy.sh conventions.
#
# Behavior:
# - Infers function names as: ${FUNCTION_PREFIX}-${lang}
# - Detects languages from subdirectories in ./lang that contain a Dockerfile
# - Verifies AWS login; if not logged in and using SSO, attempts `aws sso login`
# - Optionally uses lang2url.json to resolve functions when the naming pattern fails
#
# Usage:
#   scripts/list_timeouts.sh                  # Use defaults
#   FUNCTION_PREFIX=eval-fastapi-v2 scripts/list_timeouts.sh python go
#   PROFILE=your_sso_profile scripts/list_timeouts.sh
#   AWS_PROFILE=your_sso_profile scripts/list_timeouts.sh
#   AWS_REGION=ap-northeast-1 scripts/list_timeouts.sh

set -euo pipefail

: "${AWS_REGION:=ap-northeast-1}"
# Prefer AWS_PROFILE if provided, else fall back to PROFILE, else default used in deploy.sh
if [[ -n "${AWS_PROFILE:-}" ]]; then
  PROFILE="$AWS_PROFILE"
else
  : "${PROFILE:=288761745376_developer}"
  export AWS_PROFILE="$PROFILE"
fi

: "${FUNCTION_PREFIX:=eval-fastapi-v2}"

# Colors for better readability (fall back to empty if not a tty)
if [[ -t 1 ]]; then
  BOLD='\033[1m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; RED='\033[0;31m'; NC='\033[0m'
else
  BOLD=''; GREEN=''; YELLOW=''; RED=''; NC=''
fi

err() { echo -e "${RED}[ERROR]${NC} $*" >&2; }
info() { echo -e "${GREEN}[INFO]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }

# Determine list of languages (arguments override autodetect)
LANGS=()
if [[ $# -gt 0 ]]; then
  for a in "$@"; do LANGS+=("$a"); done
else
  if [[ -d lang ]]; then
    while IFS= read -r l; do
      [[ -f "lang/$l/Dockerfile" ]] && LANGS+=("$l")
    done < <(find lang -maxdepth 1 -mindepth 1 -type d -printf "%f\n" | sort)
  fi
fi

if [[ ${#LANGS[@]} -eq 0 ]]; then
  err "No languages found. Pass languages as args or ensure ./lang/*/Dockerfile exists."
  exit 1
fi

# Ensure AWS CLI is available
if ! command -v aws >/dev/null 2>&1; then
  err "aws CLI not found. Please install the AWS CLI."
  exit 1
fi

ensure_login() {
  local ident_out="" ident_rc=0
  ident_out=$(aws sts get-caller-identity --region "$AWS_REGION" --profile "${PROFILE}" 2>&1) || ident_rc=$?
  if [[ $ident_rc -eq 0 ]]; then
    return 0
  fi

  # Heuristic: if the message looks like SSO-related, try aws sso login automatically
  if echo "$ident_out" | grep -Eiq 'sso|SSO|login'; then
    warn "AWS SSO credential appears missing/expired for profile '${PROFILE}'. Running 'aws sso login'..."
    if aws sso login --profile "${PROFILE}"; then
      aws sts get-caller-identity --region "$AWS_REGION" --profile "${PROFILE}" >/dev/null && return 0
    else
      err "'aws sso login' failed for profile '${PROFILE}'."
    fi
  fi

  err "Unable to authenticate with AWS (profile='${PROFILE}', region='${AWS_REGION}')."
  err "If using SSO, run: aws sso login --profile '${PROFILE}'"
  err "Otherwise, configure credentials: aws configure --profile '${PROFILE}'"
  return 1
}

# Optionally read lang2url.json for URL mapping (used as fallback)
declare -A LANG_URL
if [[ -f lang2url.json ]]; then
  if command -v jq >/dev/null 2>&1; then
    # shellcheck disable=SC2207
    keys=( $(jq -r 'keys[]' lang2url.json 2>/dev/null || true) )
    for k in "${keys[@]:-}"; do
      v=$(jq -r --arg k "$k" '.[$k]' lang2url.json 2>/dev/null || true)
      [[ -n "$v" && "$v" != "null" ]] && LANG_URL["$k"]="$v"
    done
  elif command -v python3 >/dev/null 2>&1; then
    # Fallback: use python to parse JSON when jq is unavailable
    while IFS=$'\t' read -r k v; do
      [[ -n "$k" && -n "$v" ]] && LANG_URL["$k"]="$v"
    done < <(
      python3 - <<'PY' 2>/dev/null || true
import json, sys
try:
    with open('lang2url.json', 'r') as f:
        d = json.load(f)
    for k, v in (d or {}).items():
        if v:
            print(f"{k}\t{v}")
except Exception:
    pass
PY
    )
  else
    warn "lang2url.json found but neither 'jq' nor 'python3' is installed; skipping URL mapping fallback."
  fi
fi

find_func_by_url() {
  # $1 = target URL string
  local target_url="$1"
  [[ -z "$target_url" ]] && return 1

  # List functions and look for a matching Function URL
  # Note: This can be slow in large accounts but is acceptable here.
  local fn_names
  if ! fn_names=$(aws lambda list-functions --region "$AWS_REGION" --profile "$PROFILE" --query 'Functions[].FunctionName' --output text 2>/dev/null); then
    return 1
  fi
  for name in $fn_names; do
    local url
    url=$(aws lambda get-function-url-config --function-name "$name" --region "$AWS_REGION" --profile "$PROFILE" --query FunctionUrl --output text 2>/dev/null || true)
    if [[ -n "$url" && "$url" != "None" && "$url" == "$target_url" ]]; then
      echo "$name"
      return 0
    fi
  done
  return 1
}

ensure_login || exit 1

printf "%s\n" "${BOLD}Listing Lambda timeouts (region=${AWS_REGION}, profile=${PROFILE}, prefix=${FUNCTION_PREFIX})${NC}"
printf "%-10s  %-40s  %s\n" "LANG" "FUNCTION" "TIMEOUT(s)"
printf "%-10s  %-40s  %s\n" "----------" "----------------------------------------" "----------"

for lang in "${LANGS[@]}"; do
  func_name="${FUNCTION_PREFIX}-${lang}"
  timeout=""

  if timeout=$(aws lambda get-function-configuration \
      --function-name "$func_name" \
      --region "$AWS_REGION" --profile "$PROFILE" \
      --query 'Timeout' --output text 2>/dev/null); then
    :
  else
    # If direct naming failed, try resolving via lang2url.json mapping (if present)
    if [[ -n "${LANG_URL[${lang}]:-}" ]]; then
      resolved_name=$(find_func_by_url "${LANG_URL[$lang]}" || true)
      if [[ -n "$resolved_name" ]]; then
        func_name="$resolved_name"
        timeout=$(aws lambda get-function-configuration \
          --function-name "$func_name" \
          --region "$AWS_REGION" --profile "$PROFILE" \
          --query 'Timeout' --output text 2>/dev/null || echo "N/A")
      else
        timeout="N/A"
      fi
    else
      timeout="N/A"
    fi
  fi

  printf "%-10s  %-40s  %s\n" "$lang" "$func_name" "$timeout"
done
