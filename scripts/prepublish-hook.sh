#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

if [[ -n "${PREPUBLISH_DATE:-}" ]]; then
  python3 ./scripts/generate-summary.py --date "$PREPUBLISH_DATE"
else
  python3 ./scripts/generate-summary.py
fi
