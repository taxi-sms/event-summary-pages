#!/usr/bin/env bash
set -euo pipefail

# Publish the current event summary to GitHub Pages.
# Usage:
#   ./scripts/publish-pages.sh "2026-02-26 update"
# If message is omitted, today's date is used.
# After push, it prints a cache-busting URL and optionally sends it to LINE.

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

BASE_URL="https://taxi-sms.github.io/event-summary-pages/"
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
  VERSION_STAMP="$(date +%Y%m%d-%H%M%S)"
  echo "確認用URL(キャッシュ回避): ${BASE_URL}?v=${VERSION_STAMP}"
  exit 0
fi

git commit -m "pages: ${MSG}"
git push

VERSION_STAMP="$(date +%Y%m%d-%H%M%S)"
CACHE_BUST_URL="${BASE_URL}?v=${VERSION_STAMP}"

echo "Push完了。公開URL: ${BASE_URL}"
echo "確認/共有URL(キャッシュ回避): ${CACHE_BUST_URL}"

if [[ -x "./scripts/send-line-url.sh" ]]; then
  if ! ./scripts/send-line-url.sh "$CACHE_BUST_URL" "イベントまとめを更新しました"; then
    echo "LINE送信は失敗しました（公開は完了しています）。"
  fi
fi
