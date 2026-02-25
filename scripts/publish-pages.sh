#!/usr/bin/env bash
set -euo pipefail

# Publish the current event summary to GitHub Pages.
# Expected flow:
# 1) Edit event-summary.html
# 2) Run: ./scripts/publish-pages.sh "update message"
#
# This script copies event-summary.html -> index.html, commits, and pushes.

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

MSG="${1:-daily update}"

if [[ ! -f "event-summary.html" ]]; then
  echo "event-summary.html が見つかりません。"
  exit 1
fi

cp event-summary.html index.html

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
  echo "Gitリポジトリではありません。"
  exit 1
}

git add event-summary.html index.html

if git diff --cached --quiet; then
  echo "差分がないため push しません。"
  exit 0
fi

git commit -m "pages: ${MSG}"
git push

echo "Push完了。GitHub Pages を有効化済みなら index.html が公開されます。"
