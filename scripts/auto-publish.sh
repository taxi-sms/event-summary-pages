#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"
export TZ="Asia/Tokyo"
mkdir -p logs

LOG_FILE="logs/auto-publish.log"
STAMP_START="$(date '+%Y-%m-%d %H:%M:%S')"

{
  echo "[$STAMP_START] auto-publish start"

  # Optional hook: put extraction/update logic here in the future.
  if [[ -x "./scripts/prepublish-hook.sh" ]]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] running prepublish hook"
    ./scripts/prepublish-hook.sh
  else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] prepublish hook skipped (scripts/prepublish-hook.sh not found)"
  fi

  ./scripts/publish-pages.sh "auto $(date +%F)"

  echo "[$(date '+%Y-%m-%d %H:%M:%S')] auto-publish done"
  echo
} >> "$LOG_FILE" 2>&1
