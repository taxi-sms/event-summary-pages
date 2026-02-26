#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

DATE_ARG=()
if [[ -n "${PREPUBLISH_DATE:-}" ]]; then
  DATE_ARG=(--date "$PREPUBLISH_DATE")
fi

python3 ./scripts/generate-summary.py "${DATE_ARG[@]}"
