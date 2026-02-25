#!/usr/bin/env bash
set -euo pipefail

# Publish the current event summary to GitHub Pages.
# Usage:
#   ./scripts/publish-pages.sh "2026-02-26 update"
# If message is omitted, today's date is used.

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

MSG="${1:-$(date +%F) update}"

if [[ ! -f "event-summary.html" ]]; then
  echo "event-summary.html が見つかりません。"
  echo "テンプレートから作る場合: ./scripts/new-summary.sh"
  exit 1
fi

cp event-summary.html index.html

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
  echo "Gitリポジトリではありません。"
  exit 1
}

# Dedicated Pages repo想定のため、日々の変更をまとめて stage
# (HTML, 画像, scripts, README, archive除外したい場合は手動運用に切替)
git add -A

if git diff --cached --quiet; then
  echo "差分がないため push しません。"
  exit 0
fi

git commit -m "pages: ${MSG}"
git push

echo "Push完了。公開URL: https://taxi-sms.github.io/event-summary-pages/"
